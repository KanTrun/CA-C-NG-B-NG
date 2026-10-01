# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Tests — feature flag auto-send + endpoint /api/v1/page/fb-policy (kế hoạch §5.5).

Flag OFF (mặc định): pipeline ghi auto_sent nhưng webhook KHÔNG gửi thật.
Flag ON: chỉ nhánh policy auto + supervisor pass mới gửi.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from unit.auth_util import headers


@pytest.fixture()
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    monkeypatch.setenv("NHIPQUAN_PAGE_MODE", "live")
    monkeypatch.setenv("NHIPQUAN_FB_PAGE_TOKEN", "tok_test")
    monkeypatch.setenv("NHIPQUAN_FB_PAGE_ID", "page_1")
    monkeypatch.setenv("NHIPQUAN_FB_APP_SECRET", "secret_test")
    monkeypatch.setenv("NHIPQUAN_FB_AUTO_SEND", "0")
    monkeypatch.setenv("NHIPQUAN_DB", str(tmp_path / f"t_{uuid.uuid4().hex[:8]}.db"))

    import ca_api.persist as persist

    monkeypatch.setattr(persist, "_INITIALIZED", False)

    from ca_api.interfaces.http import channels as ch
    from ca_api.interfaces.http.main import app as fastapi_app

    sent: list[tuple[str, str]] = []

    def fake_send(psid: str, text: str, **kw: object) -> dict[str, object]:
        sent.append((psid, text))
        return {"ok": True}

    monkeypatch.setattr(ch, "send_messenger_text", fake_send)
    client = TestClient(fastapi_app)
    original_send = client.send

    def signed_send(request, *args, **kwargs):
        if request.method == "POST" and request.url.path.endswith("/facebook/webhook"):
            digest = hmac.new(b"secret_test", request.content, hashlib.sha256).hexdigest()
            request.headers["x-hub-signature-256"] = f"sha256={digest}"
        return original_send(request, *args, **kwargs)

    client.send = signed_send  # type: ignore[method-assign]
    client.sent_calls = sent  # type: ignore[attr-defined]
    return client


def _post(client: TestClient, mid: str, text: str, psid: str = "psid_flag") -> object:
    return client.post(
        "/api/v1/channels/facebook/webhook",
        json={
            "entry": [
                {
                    "id": "page_1",
                    "messaging": [
                        {"sender": {"id": psid}, "message": {"mid": mid, "text": text}}
                    ],
                }
            ]
        },
    )


def test_policy_get_requires_manager(api: TestClient) -> None:
    assert api.get("/api/v1/page/fb-policy", headers=headers(api, "minh")).status_code == 403
    r = api.get("/api/v1/page/fb-policy", headers=headers(api, "lan"))
    assert r.status_code == 200
    body = r.json()
    assert body["auto_send_enabled"] is False  # mặc định OFF
    assert body["auto_price_cap_vnd"] == 100000


def test_policy_put_chu_quan_only(api: TestClient) -> None:
    denied = api.put(
        "/api/v1/page/fb-policy",
        json={"auto_send_enabled": True},
        headers=headers(api, "lan"),
    )
    assert denied.status_code == 403
    ok = api.put(
        "/api/v1/page/fb-policy",
        json={"auto_send_enabled": True, "note": "bật thử"},
        headers=headers(api, "hung"),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["auto_send_enabled"] is True


def test_policy_put_survives_env_off(api: TestClient, monkeypatch) -> None:
    """Chủ quán bật trên UI được ghi KV — env Docker = 0 không tắt lại."""
    ok = api.put(
        "/api/v1/page/fb-policy",
        json={"auto_send_enabled": True, "note": "persist"},
        headers=headers(api, "hung"),
    )
    assert ok.status_code == 200
    monkeypatch.setenv("NHIPQUAN_FB_AUTO_SEND", "0")
    body = api.get("/api/v1/page/fb-policy", headers=headers(api, "lan")).json()
    assert body["auto_send_enabled"] is True


def test_policy_put_negative_price_rejected(api: TestClient) -> None:
    r = api.put(
        "/api/v1/page/fb-policy",
        json={"auto_price_cap_vnd": -1},
        headers=headers(api, "hung"),
    )
    assert r.status_code == 400


def test_policy_put_price_cap_applies_without_restart(api: TestClient) -> None:
    from ca_api.services.fb_moderation import moderate_fb_message

    updated = api.put(
        "/api/v1/page/fb-policy",
        json={"auto_price_cap_vnd": 10_000},
        headers=headers(api, "hung"),
    )
    assert updated.status_code == 200

    result = moderate_fb_message(
        psid="runtime_cap_psid",
        text="Cà phê muối bao nhiêu tiền?",
        message_id="runtime_cap_mid",
        timestamp=1000.0,
        public_context={
            "profile": {},
            "menu": [{"ten": "Cà phê muối", "gia": 30_000}],
        },
    )

    assert result["action"] != "auto_send"
    assert result["reason"] == "fact_not_in_kb_or_price_limit"


def test_flag_off_auto_becomes_queue(api: TestClient) -> None:
    """Flag OFF: tin 'auto-able' KHÔNG gửi — phải vào queue cho QL duyệt."""
    from ca_api.services import fb_moderation as fm

    fm._RATE_LIMITER = type(fm._RATE_LIMITER)(now_fn=lambda: 1000.0)
    _post(api, "flag_off_1", "Quán mở cửa mấy giờ ạ?")
    calls = getattr(api, "sent_calls", [])
    assert len(calls) == 0, "flag OFF nhưng vẫn gửi thật!"
    items = api.get(
        "/api/v1/page/fb-inbox?status=pending", headers=headers(api, "lan")
    ).json()["items"]
    assert any("mở cửa mấy giờ" in str(i["message_text"]) for i in items)


def test_flag_on_auto_sends_for_safe_intent(api: TestClient, monkeypatch) -> None:
    """Flag ON: policy auto + supervisor pass → gửi thật qua Messenger."""
    monkeypatch.setenv("NHIPQUAN_FB_AUTO_SEND", "1")
    from ca_api.services import fb_moderation as fm

    fm._RATE_LIMITER = type(fm._RATE_LIMITER)(now_fn=lambda: 2000.0)
    _post(api, "flag_on_1", "Cà phê muối bao nhiêu tiền vậy ạ?")
    calls = getattr(api, "sent_calls", [])
    assert len(calls) >= 1, f"flag ON nhưng không gửi: {calls}"
    psid, text = calls[0]
    assert psid == "psid_flag"
    # Nội dung phản hồi chứa thông tin menu (không khớp cứng định dạng)
    all_text = " ".join(t for _, t in calls)
    assert "menu" in all_text.lower() or "đ" in all_text


def test_flag_on_provider_failure_queues_manual_retry(api: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("NHIPQUAN_FB_AUTO_SEND", "1")
    from ca_api.interfaces.http import channels as ch
    from ca_api.services import fb_moderation as fm

    fm._RATE_LIMITER = type(fm._RATE_LIMITER)(now_fn=lambda: 2500.0)
    monkeypatch.setattr(
        ch,
        "send_messenger_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("graph_unavailable")),
    )

    result = _post(api, "flag_on_fail_1", "Cà phê muối bao nhiêu tiền vậy ạ?")

    assert result.status_code == 200
    items = api.get(
        "/api/v1/page/fb-inbox?status=pending", headers=headers(api, "lan")
    ).json()["items"]
    failed = next(i for i in items if i["message_text"] == "Cà phê muối bao nhiêu tiền vậy ạ?")
    assert failed["status"] == "pending"
    stats = api.get(
        "/api/v1/page/fb-inbox/stats", headers=headers(api, "lan")
    ).json()
    assert stats["auto_sent"] == 0


def test_flag_on_greeting_auto_sends(api: TestClient, monkeypatch) -> None:
    """Chào hỏi 'hi' phải tự gửi khi flag ON — không đẩy hộp thư QL."""
    monkeypatch.setenv("NHIPQUAN_FB_AUTO_SEND", "1")
    from ca_api.services import fb_moderation as fm

    fm._RATE_LIMITER = type(fm._RATE_LIMITER)(now_fn=lambda: 2800.0)
    _post(api, "flag_on_hi", "hi", psid="psid_hi")
    calls = getattr(api, "sent_calls", [])
    assert len(calls) == 1, f"chào hỏi không tự gửi: {calls}"
    assert calls[0][0] == "psid_hi"


def test_flag_on_escalate_still_not_auto(api: TestClient, monkeypatch) -> None:
    """Flag ON nhưng tin escalate KHÔNG BAO GIỜ tự gửi — phải qua Chủ quán."""
    monkeypatch.setenv("NHIPQUAN_FB_AUTO_SEND", "1")
    from ca_api.services import fb_moderation as fm

    fm._RATE_LIMITER = type(fm._RATE_LIMITER)(now_fn=lambda: 3000.0)
    _post(api, "flag_on_esc", "Hôm qua uống bị ngộ độc quá")
    calls = getattr(api, "sent_calls", [])
    assert len(calls) == 0, "escalate bị tự gửi — NGUY HIỂM!"


def test_policy_get_exposes_jev_enabled(api: TestClient) -> None:
    """GET fb-policy phải expose `jev_enabled` (kill-switch Jev)."""
    body = api.get("/api/v1/page/fb-policy", headers=headers(api, "lan")).json()
    assert "jev_enabled" in body


def test_policy_put_jev_enabled_kill_switch(api: TestClient, monkeypatch) -> None:
    """Chủ quán tắt Jev qua API → fb_jev_enabled() trả False ngay (không deploy)."""
    from ca_api.services import fb_moderation as fm

    # Bật trước qua env (giả lập production có key).
    monkeypatch.setenv("JEV_ENABLED", "1")
    assert fm.fb_jev_enabled() is True

    # Tắt qua API (Chủ quán) → kill-switch hoạt động.
    ok = api.put(
        "/api/v1/page/fb-policy",
        json={"jev_enabled": False, "note": "tắt gấp do nghi ngờ lộ dữ liệu"},
        headers=headers(api, "hung"),
    )
    assert ok.status_code == 200
    assert ok.json()["jev_enabled"] is False

    # env vẫn bật nhưng KV thắng → tắt.
    monkeypatch.setenv("JEV_ENABLED", "1")
    assert fm.fb_jev_enabled() is False

    # Bật lại qua API.
    ok2 = api.put(
        "/api/v1/page/fb-policy",
        json={"jev_enabled": True},
        headers=headers(api, "hung"),
    )
    assert ok2.status_code == 200
    assert fm.fb_jev_enabled() is True

# ── Nhiem vu C: het im lang — treo claim + "nuot" tin khi page chua live ───────


def _pending(api: TestClient, user: str = "lan") -> list[dict[str, object]]:
    r = api.get("/api/v1/page/fb-inbox?status=pending", headers=headers(api, user))
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


def test_policy_put_auto_reservation_enabled(api: TestClient) -> None:
    """Chu quan bat/tat dat ban tu dong qua API, khong can sua env + restart."""
    from ca_api.services import table_reservation_service as trs

    got = api.get("/api/v1/page/fb-policy", headers=headers(api, "lan"))
    assert got.json()["auto_reservation_enabled"] is True

    off = api.put(
        "/api/v1/page/fb-policy",
        json={"auto_reservation_enabled": False, "note": "dat ban cho quan ly duyet"},
        headers=headers(api, "hung"),
    )
    assert off.status_code == 200, off.text
    assert off.json()["auto_reservation_enabled"] is False
    assert trs.auto_reservation_enabled() is False

    on = api.put(
        "/api/v1/page/fb-policy",
        json={"auto_reservation_enabled": True},
        headers=headers(api, "hung"),
    )
    assert on.status_code == 200
    assert trs.auto_reservation_enabled() is True


def test_webhook_page_chua_live_vao_hoi_thu_khong_nuat(
    api: TestClient, monkeypatch
) -> None:
    """Page chua live: tin DA xac thuc phai nam trong hop thu, khong bi nuot mat.

    Truoc day tra {"ok": false, "detail": "page_chua_live"} => mat hoan toan.
    """
    monkeypatch.setenv("NHIPQUAN_PAGE_MODE", "disconnected")
    monkeypatch.setenv("NHIPQUAN_FB_PAGE_TOKEN", "")

    r = _post(api, "mid_notlive_1", "cho em xin so tai khoan de dat ban")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["detail"] == "page_chua_live"
    assert body["n"] == 1

    pending = _pending(api)
    assert len(pending) == 1, pending
    assert "page_chua_live" in pending[0]["flagged_reasons"]
    # Khong co token Page => tuyet doi khong gui gi ra ngoai.
    assert api.sent_calls == []


def test_webhook_page_chua_live_idempotent_khong_trung(
    api: TestClient, monkeypatch
) -> None:
    """Meta retry cung mot mid khi page chua live => chi mot hang trong hop thu."""
    monkeypatch.setenv("NHIPQUAN_PAGE_MODE", "disconnected")
    monkeypatch.setenv("NHIPQUAN_FB_PAGE_TOKEN", "")

    _post(api, "mid_notlive_dup", "cho em xin so tai khoan de dat ban")
    r2 = _post(api, "mid_notlive_dup", "cho em xin so tai khoan de dat ban")
    assert r2.json()["n"] == 0
    assert len(_pending(api)) == 1


def test_treo_claim_tra_ve_pending_thay_vi_im_lang(
    api: TestClient, monkeypatch
) -> None:
    """Moderation da claim auto_send (approved) nhung pipeline queue lai.

    Truoc PR nay hang approved duc yen trong DB: khach khong nhan gi, quan ly
    cung khong thay trong hop thu => im lang tuyet doi. Phai tra ve pending.
    """
    from ca_api.interfaces.http import channels as ch

    monkeypatch.setenv("NHIPQUAN_FB_AUTO_SEND", "1")
    # Circuit breaker mo => pipeline chuyen queue_to_inbox SAU khi moderation
    # da claim auto_send. Day la duong dan treo claim that.
    monkeypatch.setattr(ch, "circuit_breaker_open", lambda *a, **k: True)

    r = _post(api, "mid_treo_claim", "hi quan")
    assert r.status_code == 200, r.text
    # Khong duoc gui ra ngoai (pipeline chon queue).
    assert api.sent_calls == []

    pending = _pending(api)
    assert len(pending) == 1, pending
    assert pending[0]["status"] == "pending"
    # Ban nhap phai con de quan ly sua roi gui.
    assert pending[0]["proposed_response"]


def test_page_status_bao_cao_co_ngay_tu_dang(
    api: TestClient, monkeypatch
) -> None:
    """/page/status phai loi 4 co boi canh de UI hien banner thay vi im lang 403."""
    from ca_api.interfaces.http import channels as ch

    monkeypatch.setenv("NHIPQUAN_FB_APP_SECRET", "secret_test")
    monkeypatch.setenv("NHIPQUAN_FB_AUTO_SEND", "1")
    monkeypatch.setenv("NHIPQUAN_AUTO_RESERVATION", "0")
    body = api.get("/api/v1/page/status", headers=headers(api, "lan")).json()
    assert body["webhook_secret_present"] is True
    assert body["auto_send_enabled"] is True
    assert body["auto_reservation_enabled"] is False
    assert body["llm_mode"] == "replay"

    # Khong co App Secret => co phai False (khong duoc gia True khi vang).
    monkeypatch.setenv("NHIPQUAN_FB_APP_SECRET", "")
    body2 = api.get("/api/v1/page/status", headers=headers(api, "lan")).json()
    assert body2["webhook_secret_present"] is False
    assert ch._fb_auto_reservation_enabled() is False

