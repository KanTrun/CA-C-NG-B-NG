"""HTTP Router cho Khảo sát giá thị trường (Catchment Price Radar) và Quản trị SerpApi.

Plan `260913-1455-khao-sat-gia-fb-online-dinein-substitutes` mục 5:
- 5.1 Async Job: `POST /catchment-survey` trả **202 + job_id**; trạng thái/kết
  quả đọc qua các endpoint con. Job chạy nền, KHÔNG block request.
- 5.2 `Idempotency-Key` bắt buộc cho POST; rate limit 10 job/giờ theo **cả IP
  lẫn tài khoản** vì mỗi job tốn chi phí thật (proxy + Gemini Vision).
- 5.3 Error taxonomy: 400 INVALID_RADIUS / 409 SCHEMA_VERSION_MISMATCH /
  422 INSUFFICIENT_MARKET_DATA / 429 RATE_LIMITED / 502 SOURCE_BLOCKED /
  503 VISION_QUOTA_EXCEEDED.

ADR-008: `NEEDS_REVIEW` là điểm dừng thật — chỉ `POST .../{job_id}/review` do
người dùng gọi mới đưa job sang tổng hợp. Không có auto-approve.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Annotated, Any

from ca_agents.ag_pricing.cost_dashboard import tong_hop_dashboard
from ca_agents.ag_pricing.job_manager import SurveyJob, get_job_store, reset_job_store
from ca_agents.ag_pricing.orchestrator_v2 import (
    SurveyExecutionError,
    SurveyOrchestrator,
    get_pricing_metrics,
    reset_pricing_metrics,
)
from ca_agents.clients.serpapi_client import get_quota_status, get_serpapi_metrics
from ca_agents.sources.gmaps_menu_source import get_source_block_stats
from ca_contracts.catchment_survey_v2 import (
    SUPPORTED_SCHEMA_MAJORS,
    CatchmentSurveyRequest,
    CatchmentSurveyResponse,
    SurveyErrorCode,
    SurveyJobStatus,
    SurveyReviewSubmission,
    schema_major,
)
from fastapi import APIRouter, BackgroundTasks, Body, Header, HTTPException, Request
from pydantic import ValidationError

from ca_api.persist import kv_get, kv_set
from ca_api.persist import session as auth_session

router = APIRouter(prefix="/api/v1/market", tags=["market"])
system_router = APIRouter(prefix="/api/system", tags=["system"])

# ── Rate limiting + idempotency (plan mục 5.2) ───────────────────────────────

_RATE_LIMIT_LOCK = threading.Lock()
_JOB_TIMESTAMPS: dict[str, list[float]] = {}
_USER_REQUEST_TIMESTAMPS: dict[str, list[float]] = {}
_IDEMPOTENCY_INDEX: dict[str, str] = {}
_WINDOW_S = 3600.0


def _max_jobs_per_hour() -> int:
    try:
        return max(1, int(os.getenv("PRICING_SURVEY_MAX_JOBS_PER_HOUR", "10")))
    except ValueError:
        return 10


def _check_job_rate_limit(*keys: str) -> None:
    """Cửa sổ trượt 1 giờ cho TỪNG khóa — IP và tài khoản tính riêng."""
    limit = _max_jobs_per_hour()
    with _RATE_LIMIT_LOCK:
        now = time.time()
        stale = [
            k for k, ts in _JOB_TIMESTAMPS.items() if not ts or (now - ts[-1]) >= _WINDOW_S
        ]
        for k in stale:
            _JOB_TIMESTAMPS.pop(k, None)

        for key in keys:
            recent = [t for t in _JOB_TIMESTAMPS.get(key, []) if (now - t) < _WINDOW_S]
            if len(recent) >= limit:
                _JOB_TIMESTAMPS[key] = recent
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": SurveyErrorCode.RATE_LIMITED.value,
                        "message": (
                            f"Đã đạt giới hạn {limit} lượt khảo sát/giờ. "
                            "Mỗi lượt khảo sát tốn chi phí proxy và Vision API thật."
                        ),
                    },
                )
            recent.append(now)
            _JOB_TIMESTAMPS[key] = recent


def _check_rate_limit(user_id: str, limit: int = 3, window_s: float = 60.0) -> None:
    """Cửa sổ trượt window_s giây cho request của user, tự động dọn dẹp inactive user.

    Dùng ts[-1] (timestamp gần nhất, chronological) thay vì all(...) để tránh
    O(N×M) iteration: chỉ check phần tử cuối cùng của list đã sort tăng dần.
    """
    with _RATE_LIMIT_LOCK:
        now = time.time()
        # Dọn dẹp user không còn request nào trong window_s (chronological check)
        stale = [
            k for k, ts in _USER_REQUEST_TIMESTAMPS.items()
            if not ts or (now - ts[-1]) >= window_s
        ]
        for k in stale:
            _USER_REQUEST_TIMESTAMPS.pop(k, None)

        recent = [t for t in _USER_REQUEST_TIMESTAMPS.get(user_id, []) if (now - t) < window_s]
        if len(recent) >= limit:
            _USER_REQUEST_TIMESTAMPS[user_id] = recent
            raise HTTPException(
                status_code=429,
                detail=f"rate_limit_exceeded: max {limit} requests per minute",
            )
        recent.append(now)
        _USER_REQUEST_TIMESTAMPS[user_id] = recent


def clear_rate_limits() -> None:
    """Xóa bộ đếm rate limit + idempotency (dùng khi test)."""
    with _RATE_LIMIT_LOCK:
        _JOB_TIMESTAMPS.clear()
        _IDEMPOTENCY_INDEX.clear()
        _USER_REQUEST_TIMESTAMPS.clear()


def reset_survey_runtime() -> None:
    """Đặt lại toàn bộ trạng thái runtime của pricing radar (dùng khi test)."""
    global _ORCHESTRATOR  # noqa: PLW0603
    clear_rate_limits()
    reset_job_store()
    reset_pricing_metrics()
    with _ORCHESTRATOR_LOCK:
        _ORCHESTRATOR = None


# ── Auth / phân quyền ────────────────────────────────────────────────────────


def _require_auth(authorization: str | None) -> dict[str, Any]:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="chua_dang_nhap")
    return s


def _require_manager(user: dict[str, Any]) -> None:
    """Chỉ quản lý / chủ quán được tạo và duyệt khảo sát (plan mục 7)."""
    role = str(user.get("role") or "").lower()
    if role == "nhan_vien":
        raise HTTPException(
            status_code=403,
            detail="Tính năng khảo sát đối thủ chỉ dành cho Quản lý hoặc Chủ quán",
        )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


# ── Validate thủ công để trả đúng error taxonomy (plan mục 5.3) ──────────────

_MAX_DINE_IN_KM = 3.0
_MAX_DELIVERY_KM = 10.0


def _parse_request(payload: Any) -> CatchmentSurveyRequest:
    """Validate payload thô → contract v2, ánh xạ lỗi sang đúng mã của plan.

    Không khai báo `CatchmentSurveyRequest` làm body model: FastAPI sẽ trả 422
    chung cho MỌI lỗi field, trong khi plan mục 5.3 yêu cầu 400 cho bán kính
    và 409 cho schema version.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload phai la object")

    version = str(payload.get("schema_version") or "").strip()
    if version and schema_major(version) not in SUPPORTED_SCHEMA_MAJORS:
        raise HTTPException(
            status_code=409,
            detail={
                "code": SurveyErrorCode.SCHEMA_VERSION_MISMATCH.value,
                "message": (
                    f"schema_version '{version}' không được hỗ trợ; "
                    f"các bản chấp nhận: {sorted(SUPPORTED_SCHEMA_MAJORS)}"
                ),
            },
        )

    radius = payload.get("radius_profile")
    if isinstance(radius, dict):
        for field_name, ceiling in (
            ("dine_in_km", _MAX_DINE_IN_KM),
            ("delivery_km", _MAX_DELIVERY_KM),
        ):
            value = radius.get(field_name)
            if isinstance(value, (int, float)) and not (0 < float(value) <= ceiling):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": SurveyErrorCode.INVALID_RADIUS.value,
                        "message": (
                            f"{field_name} phải trong khoảng (0, {ceiling}] km, nhận {value}"
                        ),
                    },
                )

    try:
        return CatchmentSurveyRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


# ── Serialization & KV Persistence (đa worker) ───────────────────────────────


def _serialize_survey_job(job: SurveyJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "request": job.request.model_dump(mode="json"),
        "status": job.status.value,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "response": job.response.model_dump(mode="json") if job.response else None,
        "error_code": job.error_code.value if job.error_code else None,
        "error_message": job.error_message,
        "stores_flagged_for_review": list(job.stores_flagged_for_review),
        "pending_review": list(job.meta.get("pending_review", [])),
        "reviewed_by": job.meta.get("reviewed_by"),
        "meta": {
            k: v
            for k, v in job.meta.items()
            if isinstance(v, (str, int, float, bool, list, dict)) or v is None
        },
    }


def _deserialize_survey_job(d: dict[str, Any]) -> SurveyJob:
    req = CatchmentSurveyRequest.model_validate(d["request"])
    resp = CatchmentSurveyResponse.model_validate(d["response"]) if d.get("response") else None
    err_code = SurveyErrorCode(d["error_code"]) if d.get("error_code") else None
    meta = dict(d.get("meta") or {})
    if "pending_review" in d and "pending_review" not in meta:
        meta["pending_review"] = d["pending_review"]
    if "reviewed_by" in d and "reviewed_by" not in meta:
        meta["reviewed_by"] = d["reviewed_by"]
    return SurveyJob(
        job_id=d["job_id"],
        request=req,
        status=SurveyJobStatus(d["status"]),
        created_at=d.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        updated_at=d.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        response=resp,
        error_code=err_code,
        error_message=d.get("error_message"),
        stores_flagged_for_review=list(d.get("stores_flagged_for_review") or []),
        meta=meta,
    )


def _save_survey_job_kv(job: SurveyJob) -> None:
    try:
        kv_set(f"survey_job:{job.job_id}", _serialize_survey_job(job))
    except Exception:
        pass


def _load_survey_job_kv(job_id: str) -> SurveyJob | None:
    try:
        raw = kv_get(f"survey_job:{job_id}", None)
        if isinstance(raw, dict):
            return _deserialize_survey_job(raw)
    except Exception:
        pass
    return None


# ── Orchestrator singleton ───────────────────────────────────────────────────

_ORCHESTRATOR: SurveyOrchestrator | None = None
_ORCHESTRATOR_LOCK = threading.Lock()


def _orchestrator() -> SurveyOrchestrator:
    """Orchestrator luôn gắn với JobStore toàn cục HIỆN HÀNH."""
    global _ORCHESTRATOR  # noqa: PLW0603 — singleton có khóa
    with _ORCHESTRATOR_LOCK:
        store = get_job_store()
        store.set_hooks(on_save=_save_survey_job_kv, on_load=_load_survey_job_kv)
        if _ORCHESTRATOR is None or _ORCHESTRATOR.job_store is not store:
            _ORCHESTRATOR = SurveyOrchestrator(job_store=store)
        return _ORCHESTRATOR


def _get_job_or_404(job_id: str) -> SurveyJob:
    job = get_job_store().get_job(job_id)
    if job is None:
        job = _load_survey_job_kv(job_id)
        if job is not None:
            get_job_store().update_job(job)
    if job is None:
        raise HTTPException(status_code=404, detail="job_khong_ton_tai")
    return job


_PROGRESS: dict[SurveyJobStatus, tuple[int, str]] = {
    SurveyJobStatus.QUEUED: (0, "Đang xếp hàng"),
    SurveyJobStatus.SCRAPING_ONLINE: (1, "Đang quét kênh delivery"),
    SurveyJobStatus.SCRAPING_DINEIN: (2, "Đang quét quán tại chỗ"),
    SurveyJobStatus.OCR_PROCESSING: (3, "Đang đọc ảnh thực đơn"),
    SurveyJobStatus.NEEDS_REVIEW: (4, "Chờ bạn xác nhận giá"),
    SurveyJobStatus.AGGREGATING: (4, "Đang tổng hợp"),
    SurveyJobStatus.COMPLETED: (5, "Hoàn tất"),
    SurveyJobStatus.FAILED: (5, "Thất bại"),
}
_PROGRESS_TOTAL = 5

_ERROR_HTTP: dict[SurveyErrorCode, int] = {
    SurveyErrorCode.INVALID_RADIUS: 400,
    SurveyErrorCode.SCHEMA_VERSION_MISMATCH: 409,
    SurveyErrorCode.INSUFFICIENT_MARKET_DATA: 422,
    SurveyErrorCode.RATE_LIMITED: 429,
    SurveyErrorCode.SOURCE_BLOCKED: 502,
    SurveyErrorCode.VISION_QUOTA_EXCEEDED: 503,
}


def _job_status_payload(job: SurveyJob) -> dict[str, Any]:
    step, label = _PROGRESS.get(job.status, (0, job.status.value))
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "error_code": job.error_code.value if job.error_code else None,
        "error_message": job.error_message,
        "stores_flagged_for_review": list(job.stores_flagged_for_review),
        "pending_review": list(job.meta.get("pending_review", [])),
        "reviewed_by": job.meta.get("reviewed_by"),
        "progress": {"step": step, "total": _PROGRESS_TOTAL, "label": label},
    }


def _raise_job_error(job: SurveyJob) -> None:
    code = job.error_code or SurveyErrorCode.SOURCE_BLOCKED
    raise HTTPException(
        status_code=_ERROR_HTTP.get(code, 502),
        detail={"code": code.value, "message": job.error_message or ""},
    )


def _run_job_safely(job_id: str) -> None:
    """Chạy job trong threadpool nền; orchestrator đã tự bắt mọi lỗi nghiệp vụ."""
    try:
        _orchestrator().execute_job(job_id)
    except Exception:  # noqa: BLE001 — background task không được ném ra Starlette
        pass
    finally:
        job = get_job_store().get_job(job_id)
        if job is not None:
            _save_survey_job_kv(job)


# ── 5.1 Endpoints ────────────────────────────────────────────────────────────


@router.post("/catchment-survey", status_code=202)
async def create_catchment_survey(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Annotated[Any, Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Tạo job khảo sát mới — trả `202 Accepted` + `job_id` (plan mục 5.1)."""
    user = _require_auth(authorization)
    _require_manager(user)

    key = (idempotency_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_IDEMPOTENCY_KEY",
                "message": "Header 'Idempotency-Key' là bắt buộc khi tạo khảo sát (plan mục 5.2)",
            },
        )
    if len(key) > 200:
        raise HTTPException(status_code=400, detail="Idempotency-Key qua dai (toi da 200 ky tu)")

    body = _parse_request(payload)
    body.idempotency_key = key

    account = str(user.get("username") or user.get("nv_id") or "anonymous")
    idem_scope = f"idem:{account}:{key}"

    with _RATE_LIMIT_LOCK:
        existing_job_id = _IDEMPOTENCY_INDEX.get(idem_scope)
    if not existing_job_id:
        try:
            existing_job_id = kv_get(idem_scope, None)
        except Exception:
            existing_job_id = None

    if existing_job_id:
        existing: SurveyJob | None = None
        try:
            existing = _get_job_or_404(existing_job_id)
        except Exception:
            existing = None
        if existing is not None:
            # Cùng key → trả đúng job cũ: KHÔNG tạo job mới, KHÔNG tính rate limit.
            return {
                "ok": True,
                "data": {
                    "job_id": existing.job_id,
                    "status": existing.status.value,
                    "idempotent_replay": True,
                },
            }

    _check_job_rate_limit(f"ip:{_client_ip(request)}", f"acct:{account}")

    job = _orchestrator().create_job(body)
    job.meta["store_id"] = str(user.get("store_id") or "quan_01")
    with _RATE_LIMIT_LOCK:
        _IDEMPOTENCY_INDEX[idem_scope] = job.job_id
    try:
        kv_set(idem_scope, job.job_id)
    except Exception:
        pass
    _save_survey_job_kv(job)

    background_tasks.add_task(_run_job_safely, job.job_id)

    return {
        "ok": True,
        "data": {
            "job_id": job.job_id,
            "status": job.status.value,
            "idempotent_replay": False,
            "poll_after_seconds": 3,
        },
    }


@router.get("/catchment-survey/{job_id}")
async def get_catchment_survey_status(
    job_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Trạng thái job theo State Machine (plan mục 2.4) — UI poll mỗi 3 giây."""
    _require_manager(_require_auth(authorization))
    return {"ok": True, "data": _job_status_payload(_get_job_or_404(job_id))}


@router.get("/catchment-survey/{job_id}/result")
async def get_catchment_survey_result(
    job_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Kết quả đầy đủ khi `status=completed` (plan mục 5.1)."""
    _require_manager(_require_auth(authorization))
    job = _get_job_or_404(job_id)

    if job.status == SurveyJobStatus.FAILED:
        _raise_job_error(job)
    if job.status != SurveyJobStatus.COMPLETED or job.response is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_NOT_COMPLETED",
                "message": f"job đang ở trạng thái {job.status.value}",
                "status": job.status.value,
            },
        )
    return {"ok": True, "data": job.response.model_dump(mode="json")}


@router.post("/catchment-survey/{job_id}/review")
async def review_catchment_survey(
    job_id: str,
    body: SurveyReviewSubmission,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chủ quán xác nhận/sửa các dòng `NEEDS_REVIEW` (ADR-008, plan mục 5.1)."""
    user = _require_auth(authorization)
    _require_manager(user)
    job = _get_job_or_404(job_id)

    if job.status != SurveyJobStatus.NEEDS_REVIEW:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_NOT_NEEDS_REVIEW",
                "message": f"job đang ở trạng thái {job.status.value}, không phải needs_review",
            },
        )

    if not body.reviewed_by:
        body.reviewed_by = str(user.get("username") or user.get("nv_id") or "")

    orch = _orchestrator()
    try:
        updated = await asyncio.to_thread(orch.resume_after_review, job_id, body)
    except SurveyExecutionError as exc:
        raise HTTPException(
            status_code=_ERROR_HTTP.get(exc.code, 502),
            detail={"code": exc.code.value, "message": exc.message},
        ) from exc

    if updated.status == SurveyJobStatus.FAILED:
        _raise_job_error(updated)
    return {"ok": True, "data": _job_status_payload(updated)}


@router.get("/catchment-survey-metrics")
async def get_catchment_survey_metrics(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Metrics thô: bộ đếm Vision/proxy/job + lỗi theo mã (plan mục 9)."""
    _require_auth(authorization)
    return {"ok": True, "data": get_pricing_metrics()}


@router.get("/catchment-survey-dashboard")
async def get_catchment_survey_dashboard(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Cost dashboard: chi phí quy ra tiền + KPI thí điểm + cảnh báo (plan mục 9, 12).

    Chỉ yêu cầu đăng nhập, không đòi vai quản lý: đây là số liệu vận hành để đội
    kỹ thuật giám sát, không phải quyết định giá của chủ quán.

    Đơn giá Vision/proxy đọc từ `config/khao-sat-gia-tham-so.yaml` — endpoint này
    KHÔNG tự đặt ra tỷ giá nào.
    """
    _require_auth(authorization)
    block = {
        nguon: {
            "total_requests": stats.total_requests,
            "blocked_count": stats.blocked_count,
            "block_rate": stats.block_rate,
            "last_blocked_at": stats.last_blocked_at,
        }
        for nguon, stats in get_source_block_stats().items()
    }
    data = tong_hop_dashboard(
        get_pricing_metrics(),
        get_job_store().list_jobs(limit=200),
        source_block=block,
    )
    data["nguon"] = block
    return {"ok": True, "data": data}


# ── SerpApi (giữ nguyên từ plan 260913-2045) ─────────────────────────────────


@router.get("/serpapi/quota")
async def get_serpapi_quota_info(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Lấy thông tin sử dụng hạn ngạch SerpApi trong tháng hiện tại."""
    _require_auth(authorization)
    return {"ok": True, "data": get_quota_status()}


@system_router.get("/integrations/serpapi")
async def get_system_serpapi_integration(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Endpoint giám sát: trạng thái tích hợp, Circuit Breaker, metrics SerpApi."""
    _require_auth(authorization)
    return {"ok": True, "data": get_serpapi_metrics()}
