# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Kiểm thử API v2 cho Catchment Price Radar (async job, plan mục 5).

`TestClient` của Starlette chạy `BackgroundTasks` ĐỒNG BỘ sau khi trả response,
nên khi job được tạo qua `POST /catchment-survey` thì `GET status` đã thấy trạng
thái cuối. Trên production (uvicorn nhiều worker) điều đó KHÔNG còn đúng — xem
nhóm test `POST .../{job_id}/run`, nơi trạng thái được đọc lại tại chính worker
đang chạy job.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from ca_agents.ag_pricing import orchestrator_v2
from ca_agents.ag_pricing.vision_menu_extractor import VisionExtractionResult
from ca_api.interfaces.http.main import app
from ca_api.interfaces.http.pricing_radar import reset_survey_runtime
from ca_contracts.catchment_survey import DishItem, StoreCandidate
from ca_contracts.catchment_survey_v2 import (
    ChannelMode,
    MenuSnapshotV2,
    SurveyErrorCode,
)
from fastapi.testclient import TestClient

SURVEY_URL = "/api/v1/market/catchment-survey"

_ONLINE = "ca_agents.ag_pricing.orchestrator_v2.scrape_delivery_stores_camoufox"
_DINEIN = "ca_agents.ag_pricing.orchestrator_v2.scrape_gmaps_menu_images_camoufox"
_DOWNLOAD = "ca_agents.ag_pricing.orchestrator_v2._download_image"
_VISION = "ca_agents.ag_pricing.orchestrator_v2.extract_menu_from_image"


@pytest.fixture(autouse=True)
def _clean_runtime() -> Any:
    reset_survey_runtime()
    yield
    reset_survey_runtime()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, username: str = "lan") -> dict[str, str]:
    res = client.post("/api/v1/auth/login", json={"username": username, "password": "nhipquan"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    return _login(client)


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "latitude": 10.7769,
        "longitude": 106.7009,
        "core_category": "cơm tấm",
        "channel_mode": ChannelMode.DELIVERY_PLATFORM.value,
        "radius_profile": {"dine_in_km": 1.0, "delivery_km": 5.0},
        "min_review_count": 50,
        "min_rating": 4.2,
    }
    base.update(overrides)
    return base


def _headers(auth: dict[str, str], key: str | None = None) -> dict[str, str]:
    out = dict(auth)
    out["Idempotency-Key"] = key or uuid.uuid4().hex
    return out


def _online_stores(count: int = 3) -> list[StoreCandidate]:
    """3 quán × 3 món = 9 mẫu — đủ vượt ngưỡng min_sample_size=5."""
    return [
        StoreCandidate(
            id=f"sf_{i}",
            name=f"Cơm Tấm {i}",
            distance_km=0.5 + i,
            rating=4.6,
            review_count=300,
            dishes=[
                DishItem(name="Cơm tấm sườn", price=45000 + i * 1000),
                DishItem(name="Cơm tấm bì", price=40000 + i * 1000),
                DishItem(name="Cơm tấm chả", price=50000 + i * 1000),
            ],
        )
        for i in range(count)
    ]


def _post(client: TestClient, auth: dict[str, str], body: dict[str, Any], key: str | None = None):
    return client.post(SURVEY_URL, headers=_headers(auth, key), json=body)


# ── Xác thực & phân quyền ────────────────────────────────────────────────────


def test_requires_auth(client: TestClient) -> None:
    res = client.post(SURVEY_URL, json=_payload(), headers={"Idempotency-Key": "k1"})
    assert res.status_code == 401


def test_missing_idempotency_key_is_400(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = client.post(SURVEY_URL, headers=auth_headers, json=_payload())
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "MISSING_IDEMPOTENCY_KEY"


def test_staff_role_is_forbidden(client: TestClient) -> None:
    staff = _login(client, "minh")
    with patch(_ONLINE, return_value=_online_stores()):
        res = _post(client, staff, _payload())
    assert res.status_code == 403


# ── Error taxonomy (plan mục 5.3) ────────────────────────────────────────────


def test_schema_version_mismatch_is_409(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = _post(client, auth_headers, _payload(schema_version="1.0"))
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "SCHEMA_VERSION_MISMATCH"


def test_invalid_radius_is_400(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = _post(
        client,
        auth_headers,
        _payload(radius_profile={"dine_in_km": 9.0, "delivery_km": 5.0}),
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "INVALID_RADIUS"


def test_invalid_latitude_is_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = _post(client, auth_headers, _payload(latitude=150.0))
    assert res.status_code == 422


def test_insufficient_market_data_surfaces_as_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    with patch(_ONLINE, return_value=_online_stores(1)):
        created = _post(client, auth_headers, _payload())
    assert created.status_code == 202
    job_id = created.json()["data"]["job_id"]

    res = client.get(f"{SURVEY_URL}/{job_id}/result", headers=auth_headers)
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INSUFFICIENT_MARKET_DATA"


def test_source_blocked_surfaces_as_502(client: TestClient, auth_headers: dict[str, str]) -> None:
    from ca_agents.clients.camoufox_client import CamoufoxUnavailable

    with patch(_ONLINE, side_effect=CamoufoxUnavailable("camoufox_khong_kha_dung")):
        created = _post(client, auth_headers, _payload())
    job_id = created.json()["data"]["job_id"]

    res = client.get(f"{SURVEY_URL}/{job_id}/result", headers=auth_headers)
    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "SOURCE_BLOCKED"


# ── 202 + job_id + polling ───────────────────────────────────────────────────


def test_create_returns_202_with_job_id(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(_ONLINE, return_value=_online_stores()):
        res = _post(client, auth_headers, _payload())
    assert res.status_code == 202
    data = res.json()["data"]
    assert data["status"] == "queued"
    assert data["idempotent_replay"] is False
    assert data["job_id"]


def test_status_then_result_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(_ONLINE, return_value=_online_stores()):
        job_id = _post(client, auth_headers, _payload()).json()["data"]["job_id"]

    status = client.get(f"{SURVEY_URL}/{job_id}", headers=auth_headers)
    assert status.status_code == 200
    body = status.json()["data"]
    assert body["status"] == "completed"
    assert body["progress"] == {"step": 5, "total": 5, "label": "Hoàn tất"}

    result = client.get(f"{SURVEY_URL}/{job_id}/result", headers=auth_headers)
    assert result.status_code == 200
    data = result.json()["data"]
    assert data["job_id"] == job_id
    assert data["online_stats"]["sample_size"] == 9
    assert data["online_stats"]["insufficient_data"] is False
    assert data["dinein_stats"] is None
    assert data["substitute_comparison"]["core_stats"]["sample_size"] == 9
    assert data["survey_captured_at"]
    assert data["generated_at"]


def test_unknown_job_is_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get(f"{SURVEY_URL}/khong-co", headers=auth_headers).status_code == 404
    assert client.get(f"{SURVEY_URL}/khong-co/result", headers=auth_headers).status_code == 404


# ── Chạy job tại chính worker đang phục vụ request (sự cố 2026-10-02) ────────
#
# Sự cố: `POST /catchment-survey` đẩy job sang background task; mọi bước chuyển
# trạng thái lại do worker khác thực hiện nên `GET /{job_id}` đọc snapshot cũ và
# job nằm im ở `scraping_online` vĩnh viễn dù đã chạy xong. Bộ test dưới đây khoá
# lại hợp đồng: `POST .../{job_id}/run` PHẢI trả về trạng thái cuối cùng.


def test_run_endpoint_drives_job_to_terminal_status(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    with patch(_ONLINE, return_value=_online_stores()):
        job_id = _post(client, auth_headers, _payload()).json()["data"]["job_id"]
        res = client.post(f"{SURVEY_URL}/{job_id}/run", headers=auth_headers)

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "completed"
    assert data["progress"] == {"step": 5, "total": 5, "label": "Hoàn tất"}

    # Snapshot đã ghi phải đọc lại được bằng `GET` mà không cần chạy thêm.
    status = client.get(f"{SURVEY_URL}/{job_id}", headers=auth_headers).json()["data"]
    assert status["status"] == "completed"


def test_run_endpoint_does_not_rerun_finished_job(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Job đã kết thúc gọi lại `/run` là vô hại — không chạy lại, không đổi kết quả."""
    with patch(_ONLINE, return_value=_online_stores()) as online:
        job_id = _post(client, auth_headers, _payload()).json()["data"]["job_id"]
        client.post(f"{SURVEY_URL}/{job_id}/run", headers=auth_headers)
        so_lan_dau = online.call_count
        res = client.post(f"{SURVEY_URL}/{job_id}/run", headers=auth_headers)

    assert res.status_code == 200
    assert res.json()["data"]["status"] == "completed"
    assert online.call_count == so_lan_dau


def test_run_endpoint_resumes_needs_review_job(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """`NEEDS_REVIEW` là điểm dừng THẬT: `/run` không được tự duyệt thay (ADR-008)."""
    with (
        patch(_ONLINE, return_value=[]),
        patch(_DINEIN, return_value=_dinein_stores()),
        patch(_DOWNLOAD, return_value=b"x" * 512),
        patch(_VISION, return_value=_vision_with_review()),
    ):
        job_id = _post(
            client, auth_headers, _payload(channel_mode=ChannelMode.DINE_IN_VISION.value)
        ).json()["data"]["job_id"]
        res = client.post(f"{SURVEY_URL}/{job_id}/run", headers=auth_headers)

    assert res.status_code == 200
    assert res.json()["data"]["status"] == "needs_review"


def test_run_endpoint_requires_manager(client: TestClient) -> None:
    staff = _login(client, "minh")
    res = client.post(f"{SURVEY_URL}/bat-ky/run", headers=staff)
    assert res.status_code == 403


def test_run_endpoint_unknown_job_is_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.post(f"{SURVEY_URL}/khong-co/run", headers=auth_headers).status_code == 404


def test_run_endpoint_requires_auth(client: TestClient) -> None:
    assert client.post(f"{SURVEY_URL}/bat-ky/run").status_code == 401


def test_run_endpoint_times_out_instead_of_hanging(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cào nguồn treo quá ngân sách → job PHẢI kết thúc ở FAILED, không nằm im.

    Ngân sách ép về 1 giây (giá trị nhỏ nhất `_JobDeadline` chấp nhận): đủ để
    `_JobDeadline` hết hạn trước khi bước cào đầu tiên kịp bắt đầu.
    """
    monkeypatch.setenv("CA_SURVEY_JOB_BUDGET_S", "1")
    with (
        patch("ca_agents.ag_pricing.orchestrator_v2._JobDeadline", _DeadlineHetHan),
        patch(_ONLINE, return_value=_online_stores()),
    ):
        job_id = _post(client, auth_headers, _payload()).json()["data"]["job_id"]
        res = client.post(f"{SURVEY_URL}/{job_id}/run", headers=auth_headers)

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == SurveyErrorCode.SOURCE_BLOCKED.value


class _DeadlineHetHan(orchestrator_v2._JobDeadline):  # noqa: SLF001 — test cố ý
    """Deadline đã cạn ngay khi được tạo, để test hết hạn mà không phải chờ."""

    def __init__(self, tong_giay: float | None = None) -> None:
        super().__init__(tong_giay)
        self.ep_het_han()


def test_result_before_completion_is_409(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Job NEEDS_REVIEW chưa có kết quả — phải trả 409, không bịa số liệu."""
    with (
        patch(_ONLINE, return_value=[]),
        patch(_DINEIN, return_value=_dinein_stores()),
        patch(_DOWNLOAD, return_value=b"x" * 512),
        patch(_VISION, return_value=_vision_with_review()),
    ):
        job_id = _post(
            client, auth_headers, _payload(channel_mode=ChannelMode.DINE_IN_VISION.value)
        ).json()["data"]["job_id"]

    res = client.get(f"{SURVEY_URL}/{job_id}/result", headers=auth_headers)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "JOB_NOT_COMPLETED"


# ── Idempotency (plan mục 5.2) ───────────────────────────────────────────────


def test_same_idempotency_key_returns_same_job(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    key = uuid.uuid4().hex
    with patch(_ONLINE, return_value=_online_stores()):
        first = _post(client, auth_headers, _payload(), key)
        second = _post(client, auth_headers, _payload(), key)

    assert first.json()["data"]["job_id"] == second.json()["data"]["job_id"]
    assert second.json()["data"]["idempotent_replay"] is True


def test_different_keys_create_different_jobs(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    with patch(_ONLINE, return_value=_online_stores()):
        a = _post(client, auth_headers, _payload()).json()["data"]["job_id"]
        b = _post(client, auth_headers, _payload()).json()["data"]["job_id"]
    assert a != b


# ── Rate limit (plan mục 5.2) ────────────────────────────────────────────────


def test_rate_limit_blocks_after_hourly_quota(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRICING_SURVEY_MAX_JOBS_PER_HOUR", "3")
    with patch(_ONLINE, return_value=_online_stores()):
        for _ in range(3):
            assert _post(client, auth_headers, _payload()).status_code == 202
        blocked = _post(client, auth_headers, _payload())

    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "RATE_LIMITED"


def test_idempotent_replay_does_not_consume_quota(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRICING_SURVEY_MAX_JOBS_PER_HOUR", "1")
    key = uuid.uuid4().hex
    with patch(_ONLINE, return_value=_online_stores()):
        assert _post(client, auth_headers, _payload(), key).status_code == 202
        # Cùng key → trả job cũ, không đụng hạn mức
        assert _post(client, auth_headers, _payload(), key).status_code == 202
        # Key mới → hết hạn mức
        assert _post(client, auth_headers, _payload()).status_code == 429


# ── NEEDS_REVIEW là điểm dừng thật (ADR-008) ─────────────────────────────────


def _dinein_stores(count: int = 3) -> list[StoreCandidate]:
    return [
        StoreCandidate(
            id=f"gm_{i}",
            name=f"Quán Tại Chỗ {i}",
            distance_km=0.3 + i,
            rating=4.5,
            review_count=200,
            menu_image_urls=[f"https://example.test/menu{i}.jpg"],
        )
        for i in range(count)
    ]


def _vision_with_review() -> VisionExtractionResult:
    """Snapshot CÓ món đọc được + 1 dòng giá mờ phải chờ người xác nhận."""
    from ca_contracts.catchment_survey_v2 import MenuItemPrice

    snapshot = MenuSnapshotV2(
        store_id="gm_0",
        extracted_items=[
            MenuItemPrice(
                item_name_raw=f"Cơm tấm {i}",
                item_name_normalized=f"com tam {i}",
                original_price_vnd=45000 + i * 5000,
                effective_price_vnd=45000 + i * 5000,
                source_channel=ChannelMode.DINE_IN_VISION,
            )
            for i in range(5)
        ],
        captured_at="2026-09-13T10:00:00+00:00",
    )
    return VisionExtractionResult(
        snapshot=snapshot,
        needs_review=[
            {
                "name": "Cơm tấm sườn",
                "raw_text": "4?.000",
                "reason": "price_unreadable",
            }
        ],
    )


def _vision_ok() -> VisionExtractionResult:
    from ca_contracts.catchment_survey_v2 import MenuItemPrice

    snapshot = MenuSnapshotV2(
        store_id="gm_0",
        extracted_items=[
            MenuItemPrice(
                item_name_raw=f"Cơm tấm {i}",
                item_name_normalized=f"com tam {i}",
                original_price_vnd=45000 + i * 5000,
                effective_price_vnd=45000 + i * 5000,
                source_channel=ChannelMode.DINE_IN_VISION,
            )
            for i in range(5)
        ],
        captured_at="2026-09-13T10:00:00+00:00",
    )
    return VisionExtractionResult(snapshot=snapshot, needs_review=[])


def test_needs_review_stops_the_job(client: TestClient, auth_headers: dict[str, str]) -> None:
    with (
        patch(_ONLINE, return_value=[]),
        patch(_DINEIN, return_value=_dinein_stores(1)),
        patch(_DOWNLOAD, return_value=b"x" * 512),
        patch(_VISION, return_value=_vision_with_review()),
    ):
        job_id = _post(
            client, auth_headers, _payload(channel_mode=ChannelMode.DINE_IN_VISION.value)
        ).json()["data"]["job_id"]

    status = client.get(f"{SURVEY_URL}/{job_id}", headers=auth_headers).json()["data"]
    assert status["status"] == "needs_review"
    assert status["stores_flagged_for_review"] == ["gm_0"]
    assert status["pending_review"][0]["reason"] == "price_unreadable"
    assert status["progress"]["label"] == "Chờ bạn xác nhận giá"


def test_review_submission_completes_the_job(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    with (
        patch(_ONLINE, return_value=_online_stores()),
        patch(_DINEIN, return_value=_dinein_stores(1)),
        patch(_DOWNLOAD, return_value=b"x" * 512),
        patch(_VISION, return_value=_vision_with_review()),
    ):
        job_id = _post(
            client, auth_headers, _payload(channel_mode=ChannelMode.HYBRID.value)
        ).json()["data"]["job_id"]

    review = client.post(
        f"{SURVEY_URL}/{job_id}/review",
        headers=auth_headers,
        json={
            "reviewed_by": "lan",
            "items": [
                {
                    "store_id": "gm_0",
                    "item_name_raw": "Cơm tấm sườn",
                    "original_price_vnd": 48000,
                    "effective_price_vnd": 48000,
                }
            ],
            "approve_all_remaining": False,
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["data"]["status"] == "completed"
    assert review.json()["data"]["reviewed_by"] == "lan"
    assert review.json()["data"]["stores_flagged_for_review"] == []

    data = client.get(f"{SURVEY_URL}/{job_id}/result", headers=auth_headers).json()["data"]
    assert data["status"] == "completed"
    # 5 món OCR đọc được + 1 dòng chủ quán vừa xác nhận tay
    assert data["dinein_stats"]["sample_size"] == 6
    assert data["stores_flagged_for_review"] == []


def test_review_on_completed_job_is_409(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(_ONLINE, return_value=_online_stores()):
        job_id = _post(client, auth_headers, _payload()).json()["data"]["job_id"]

    res = client.post(
        f"{SURVEY_URL}/{job_id}/review", headers=auth_headers, json={"items": []}
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "JOB_NOT_NEEDS_REVIEW"


def test_review_requires_auth(client: TestClient) -> None:
    res = client.post(f"{SURVEY_URL}/bat-ky/review", json={"items": []})
    assert res.status_code == 401


# ── Metrics & SerpApi ────────────────────────────────────────────────────────


def test_survey_metrics_endpoint(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(_ONLINE, return_value=_online_stores()):
        _post(client, auth_headers, _payload())

    res = client.get("/api/v1/market/catchment-survey-metrics", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["jobs_created"] == 1
    assert data["jobs_completed"] == 1
    assert data["jobs_failed"] == 0


def test_survey_metrics_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/market/catchment-survey-metrics").status_code == 401


def test_system_serpapi_integration_api(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = client.get("/api/system/integrations/serpapi", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    for field in ("status", "quota", "circuit_breaker", "cache_hit_rate_pct"):
        assert field in data


def test_serpapi_quota_endpoint(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = client.get("/api/v1/market/serpapi/quota", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["ok"] is True
