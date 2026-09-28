"""HTTP entry — health, login, roster, Sprint 3–5 ops."""

from __future__ import annotations

import json
import logging
import os

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, cast

# Inject real data sources into AG-COPILOT tool registry (hexagonal boundary).
# Agents không được import ca_api/ca_playbook trực tiếp (test_architecture) —
# nên API layer cung cấp dữ liệu thật qua configure_data_sources().
from ca_agents.ag_copilot.tool_registry import configure_data_sources
from ca_agents.ag_mailwriter import draft_email as _draft_email
from ca_agents.ag_pricing.job_manager import get_job_store as _get_job_store
from ca_agents.ag_sop import answer as _sop_answer
from ca_agents.ag_tkb.extract import extract_tkb as _extract_tkb
from ca_agents.ag_waste import cluster as _waste_cluster
from ca_agents.ag_waste import tinh_tu_nguon as _loss_engine
from ca_agents.clients.serpapi_client import (
    get_circuit_breaker as _get_circuit_breaker,
)
from ca_agents.clients.serpapi_client import (
    get_quota_status as _get_quota_status,
)
from ca_contracts import (
    Ca,
    DongDon,
    DonQuay,
    LichTuan,
    MonNuoc,
    NhanVien,
    PhieuMau,
    RangBuocTrichXuat,
)
from ca_ops.engine import load_template as _load_template
from ca_playbook import record_sua
from ca_playbook.sua import list_sua as _list_sua
from ca_playbook.vong_doi import de_xuat as _de_xuat
from ca_playbook.vong_doi import list_luat as _list_luat
from ca_playbook.vong_doi import tim_mau as _tim_mau
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ca_api.ai_learning.rollout import select_active_rules
from ca_api.ai_learning.security import configure_data_protection, minimal_data_mode
from ca_api.context_providers import (
    get_active_mail_rules_for_store,
    get_mail_style_for_store,
    get_ops_context_for_mail,
)
from ca_api.interfaces.http.ai_insight import router as ai_insight_router
from ca_api.interfaces.http.ai_learning import router as ai_learning_router
from ca_api.interfaces.http.channels import router as channels_router
from ca_api.interfaces.http.chat import router as chat_router
from ca_api.interfaces.http.copilot import router as copilot_router
from ca_api.interfaces.http.copilot_voice import router as copilot_voice_router
from ca_api.interfaces.http.experience import router as experience_router
from ca_api.interfaces.http.experience_rules import router as experience_rules_router
from ca_api.interfaces.http.gmail import router as gmail_router
from ca_api.interfaces.http.hao_hut import router as hao_hut_router
from ca_api.interfaces.http.mail import router as mail_router
from ca_api.interfaces.http.meeting import router as meeting_router
from ca_api.interfaces.http.ops_explain import router as ops_explain_router
from ca_api.interfaces.http.ops_predict import router as ops_predict_router
from ca_api.interfaces.http.pos import router as pos_router
from ca_api.interfaces.http.quanverse import router as quanverse_router

try:
    from ca_api.interfaces.http.pricing_radar import (
        router as pricing_radar_router,
    )
    from ca_api.interfaces.http.pricing_radar import (
        system_router as serpapi_system_router,
    )
except ImportError:
    pricing_radar_router = None  # type: ignore[assignment]
    serpapi_system_router = None  # type: ignore[assignment]
from ca_api.interfaces.http.reservations import router as reservations_router
from ca_api.interfaces.http.shift_rescue import router as shift_rescue_router
from ca_api.interfaces.http.skills import router as skills_router
from ca_api.interfaces.http.spatial_memory import router as spatial_memory_router
from ca_api.interfaces.http.sprint3 import router as sprint3_router
from ca_api.interfaces.http.sprint45 import _SHARED_ALLOWED
from ca_api.interfaces.http.sprint45 import router as sprint45_router
from ca_api.interfaces.http.trends import router as trends_router
from ca_api.interfaces.http.war_room import router as war_room_router
from ca_api.nhan_vien import list_nhan_vien_ops
from ca_api.persist import (
    DangKyLoi,
    audit_add,
    audit_list,
    audit_request_begin,
    audit_request_end,
    audit_request_had_entry,
    don_get,
    don_list,
    get_user_emails,
    kv_get,
    kv_get_many,
    kv_mutate,
    kv_set,
    list_users,
    menu_list,
    schedule_run_latest,
)
from ca_api.persist import login as persist_login
from ca_api.persist import logout as persist_logout
from ca_api.persist import register as persist_register
from ca_api.persist import session as auth_session
from ca_api.services.chat_ws import login_ip_limiter, notify_ops_changed


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown: cấu hình bảo vệ dữ liệu + đóng Redis Pub/Sub sạch sẽ."""
    configure_data_protection()
    yield
    from ca_api.services.chat_ws import pubsub_backend

    aclose = getattr(pubsub_backend, "aclose", None)
    if aclose is not None:
        await aclose()


app = FastAPI(
    title="NHIP QUAN API",
    version="0.2.0",
    lifespan=_lifespan,
    # Swagger mặc định BẬT (hội đồng/demo cần xem /docs). Khi vận hành quán thật,
    # đặt NHIPQUAN_PUBLIC_API_DOCS=0 để tắt /docs, /redoc và /openapi.json —
    # tránh phơi toàn bộ schema API ra Internet (QA 2026-09-26 finding #10).
    docs_url="/docs" if os.environ.get("NHIPQUAN_PUBLIC_API_DOCS", "1").strip() != "0" else None,
    redoc_url="/redoc" if os.environ.get("NHIPQUAN_PUBLIC_API_DOCS", "1").strip() != "0" else None,
    openapi_url="/openapi.json"
    if os.environ.get("NHIPQUAN_PUBLIC_API_DOCS", "1").strip() != "0"
    else None,
)

# CORS: mặc định 3 origin dev local. Khi deploy (Postgres, domain thật) đặt
# NHIPQUAN_CORS_ORIGINS — danh sách origin cách nhau bởi dấu phẩy — để thay
# toàn bộ danh sách này; bỏ trống thì giữ mặc định bên dưới.
_cors_origins = [
    origin.strip()
    for origin in os.environ.get("NHIPQUAN_CORS_ORIGINS", "").split(",")
    if origin.strip()
] or [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://[::1]:3000",
    "http://[::1]:3001",
    "http://[::1]:3002",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Any) -> Any:
    """Thêm header bảo mật cho mọi response (QA 2026-09-26 phát hiện thiếu).

    - `X-Content-Type-Options: nosniff` — chặn trình duyệt đoán MIME (chống XSS
      từ file upload bị phục vụ sai kiểu).
    - `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` — chống clickjacking.
    - `Referrer-Policy` — không rò URL nội bộ (có token/ID) sang bên thứ ba.
    - `Permissions-Policy` — tắt camera/mic/geolocation cho tài liệu (API không cần).
    - HSTS: chỉ gửi khi request đã qua HTTPS (qua proxy set `x-forwarded-proto`).

    API trả JSON nên CSP tối giản (`default-src 'none'`) là đủ; trang HTML do
    Next.js phục vụ có CSP riêng ở tầng web.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
    )
    proto = request.headers.get("x-forwarded-proto", "")
    if proto.split(",")[0].strip() == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response

_LOG = logging.getLogger(__name__)
_REALTIME_SKIP_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/chat/",
    # Các endpoint đổi ca phát sự kiện sau khi audit đã commit để /vet tải
    # đúng bản ghi mới, tránh broadcast chung đến sớm hoặc phát hai lần.
    "/api/v1/cho-doi-ca",
    "/api/v1/doi-ca",
    "/api/v1/channels/telegram/webhook",
    "/api/v1/channels/zalo/webhook",
)
_REALTIME_SKIP_PATHS = {
    "/api/v1/lich-tuan/pin",
    "/api/v1/lich-tuan/lifecycle",
    "/api/v1/lich/lifecycle",
    "/api/v1/lich-tuan/nv-status",
    "/api/v1/lich-tuan/xac-nhan-lich",
}
_AUDIT_SKIP_PATHS = {
    # Hai endpoint này tự ghi loại log chuyên biệt, và chưa có session đầu vào.
    "/api/v1/auth/register",
    "/api/v1/auth/login",
}


@app.middleware("http")
async def broadcast_successful_mutation(request: Request, call_next: Any) -> Any:
    audit_token = audit_request_begin()
    path = request.url.path
    method = request.method.upper()
    is_mutation_method = method in {"POST", "PUT", "PATCH", "DELETE"}
    actor_session = (
        auth_session(request.headers.get("authorization"))
        if is_mutation_method
        and path not in _AUDIT_SKIP_PATHS
        and request.headers.get("authorization")
        else None
    )
    generic_audit_added = False
    try:
        response = await call_next(request)
        successful_mutation = (
            is_mutation_method
            and response.status_code < 400
        )

        # Mọi mutation thành công của người đã đăng nhập phải có ít nhất một
        # vết. Endpoint có audit nghiệp vụ sẽ tự đánh dấu; endpoint còn thiếu
        # nhận vết dự phòng không chứa body, token hay dữ liệu nhạy cảm.
        if (
            successful_mutation
            and actor_session
            and path not in _AUDIT_SKIP_PATHS
            and not audit_request_had_entry()
        ):
            route = request.scope.get("route")
            route_path = str(getattr(route, "path", path))
            await run_in_threadpool(
                audit_add,
                datetime.now(UTC).isoformat(),
                str(actor_session.get("nv_id") or actor_session.get("username") or actor_session["role"]),
                "operation.mutation",
                {
                    "entity_type": "operation",
                    "method": method,
                    "route": route_path,
                    "status": response.status_code,
                },
            )
            generic_audit_added = True

        should_broadcast = successful_mutation and (
            generic_audit_added
            or (
                path not in _REALTIME_SKIP_PATHS
                and not path.startswith(_REALTIME_SKIP_PREFIXES)
            )
        )
        if should_broadcast:
            try:
                await notify_ops_changed(
                    "audit:mutation" if generic_audit_added else "http:mutation",
                    details={"path": path, "status": response.status_code},
                )
            except Exception:
                _LOG.exception("Operational realtime notification failed for %s", path)
        return response
    finally:
        audit_request_end(audit_token)


app.include_router(sprint3_router)
app.include_router(sprint45_router)
app.include_router(hao_hut_router)
app.include_router(channels_router)
app.include_router(copilot_router)
app.include_router(copilot_voice_router)
app.include_router(pos_router)
app.include_router(quanverse_router)
app.include_router(meeting_router)
app.include_router(ops_explain_router)
app.include_router(ops_predict_router)
app.include_router(experience_router)
app.include_router(experience_rules_router)
app.include_router(war_room_router)
app.include_router(trends_router)
if pricing_radar_router:
    app.include_router(pricing_radar_router)
if serpapi_system_router:
    app.include_router(serpapi_system_router)
app.include_router(mail_router)
app.include_router(gmail_router)
app.include_router(ai_learning_router)
# Khung "AI phân tích" dùng chung cho 6 trang AI & tự động hoá (Đề xuất thông
# minh, Tự giải thích, Thử nghiệm an toàn, Cẩm nang, Học từ phản hồi, Hộp thư
# ràng buộc). Router này từng bị MỒ CÔI — file có, endpoint có, nhưng không
# import/include nên mọi trang gọi `/api/v1/ai/insight` đều 404 (QA đợt 6).
app.include_router(ai_insight_router)
app.include_router(chat_router)
app.include_router(reservations_router)
app.include_router(shift_rescue_router)
app.include_router(spatial_memory_router)
app.include_router(skills_router)



ROOT = Path(__file__).resolve().parents[6]
SEED = ROOT / "data" / "seed" / "sample.json"


def _lich_tuan_out() -> Path:
    """Output solver — đồng bộ sprint45._lich_out(). Đọc env MỖI LẦN GỌI
    vì conftest set NHIPQUAN_LICH_TUAN_OUT per-test sau khi import module. """
    env = os.environ.get("NHIPQUAN_LICH_TUAN_OUT")
    if env:
        return Path(env)
    return ROOT / "data" / "out" / "lich_tuan.json"

# Pins persist in SQLite kv


def _week_value(key: str, week: str, default: Any) -> Any:
    raw = kv_get(key, None)
    if isinstance(raw, dict) and raw:
        return raw.get(week, default)
    legacy = kv_get(key.removesuffix("_by_week"), None) if key.endswith("_by_week") else None
    return legacy if legacy is not None else default


def _pin_map(tuan_iso: str) -> dict[tuple[str, str], bool]:
    raw = _week_value("pins_by_week", tuan_iso, {})
    out: dict[tuple[str, str], bool] = {}
    for key, val in raw.items():
        if "|" in str(key):
            ca_id, nv_id = str(key).split("|", 1)
            out[(ca_id, nv_id)] = bool(val)
    return out


def _set_pin(tuan_iso: str, ca_id: str, nv_id: str, pinned: bool) -> bool:
    state: dict[str, bool] = {"prev": False}

    def mut_all(all_weeks: dict[str, Any]) -> dict[str, Any]:
        raw = all_weeks.setdefault(tuan_iso, {})
        key = f"{ca_id}|{nv_id}"
        state["prev"] = bool(raw.get(key, False))
        if pinned:
            raw[key] = True
        else:
            raw.pop(key, None)
        return all_weeks

    kv_mutate("pins_by_week", mut_all, {})
    return state["prev"]


class LoginBody(BaseModel):
    username: str
    password: str


class RegisterBody(BaseModel):
    username: str
    password: str
    display_name: str


class LoginOut(BaseModel):
    token: str
    role: str
    display_name: str
    nv_id: str
    store_id: str


class PinBody(BaseModel):
    ca_id: str
    nv_id: str
    pinned: bool
    tuan_iso: str = "2026-W36"
    xep_lai: bool = True


class NvStatusBody(BaseModel):
    tuan_iso: str
    nv_id: str
    hanh_dong: str  # "xac_nhan" | "du_bi" | "bo_ca" | "dat_lai"


class XacNhanLichBody(BaseModel):
    tuan_iso: str


def _seed() -> dict[str, Any]:
    if not SEED.exists():
        return {"nhan_vien": [], "ca_mau_21": [], "lich_su_8_tuan": []}
    return cast(dict[str, Any], json.loads(SEED.read_text(encoding="utf-8")))


def _list_ca_meta() -> dict[str, dict[str, Any]]:
    """Trả map ca_id -> {thu, khung, bat_dau, ket_thuc} từ seed ca_mau_21."""
    seed = _seed()
    thu_map = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
    return {
        c["id"]: {
            "thu": thu_map.get(int(c.get("ngay_offset", 1)), "T2"),
            "khung": c.get("khung", ""),
            "bat_dau": c.get("bat_dau", "07:00"),
            "ket_thuc": c.get("ket_thuc", "12:00"),
        }
        for c in seed.get("ca_mau_21", [])
    }


def _resolve_role(authorization: str | None) -> str | None:
    s = auth_session(authorization)
    return None if s is None else s["role"]


def _draft_mail_with_active_rules(**kwargs: Any) -> Any:
    """Inject only the deterministic rollout slice of owner-active Gmail rules."""
    store_id = str(kwargs.get("store_id") or "quan_01")
    identities = list(kwargs.get("to_nv_ids") or kwargs.get("direct_emails") or [])
    selected, rollout_bucket = select_active_rules(
        get_active_mail_rules_for_store(store_id),
        store_id=store_id,
        identity=str(identities[0]) if identities else str(kwargs.get("recipient_name") or "default"),
    )
    draft = _draft_email(active_style_rules=selected, **kwargs)
    draft.rule_version = ",".join(str(rule["id"]) for rule in selected) or "none"
    draft.rollout_bucket = rollout_bucket
    return draft


def _adapted_serpapi_quota() -> dict[str, Any]:
    """Adapter chuyển đổi schema get_quota_status → contract mà tool_registry.py expect.

    serpapi_client trả về keys: used_requests, total_limit, remaining_usable, ...
    tool_registry.py expect keys: used_count, monthly_limit, remaining.
    Adapter này là boundary duy nhất giữa hai schema — không được bỏ qua.
    """
    raw = _get_quota_status() or {}
    cb = _get_circuit_breaker()
    return {
        "used_count": raw.get("used_requests", 0),
        "monthly_limit": raw.get("total_limit", 250),
        "remaining": raw.get("remaining_usable", 250),
        "circuit_breaker_state": cb.state,
        "enabled": raw.get("enabled", False),
        "warning_level": raw.get("warning_level", "NORMAL"),
        "month": raw.get("year_month", ""),
    }


configure_data_sources(
    kv_get=kv_get,
    # Đọc nhiều khoá trong MỘT connection — dùng cho tool cần ≥3 khoá
    # (`tool_get_schedule` đọc 6). Thiếu hàm này thì tool tự fallback về
    # `kv_get` tuần tự và mất hết lợi ích về độ trễ.
    kv_get_many=kv_get_many,
    list_luat=_list_luat,
    load_template=_load_template,
    list_sua=_list_sua,
    tim_mau=_tim_mau,
    de_xuat=_de_xuat,
    sop_answer=_sop_answer,
    waste_cluster=_waste_cluster,
    # Động cơ hao hụt: CÙNG hàm mà GET /api/v1/hao-hut gọi, nên câu trả lời của
    # agent mẹ và con số trên trang Hao phí không thể lệch nhau.
    loss_engine=_loss_engine,
    list_ca_meta=_list_ca_meta,
    draft_mail=_draft_mail_with_active_rules,
    get_user_emails=get_user_emails,
    get_ops_context=get_ops_context_for_mail,
    get_mail_style=get_mail_style_for_store,
    # PR9 read providers — không trả email/PII qua chat
    list_users=lambda: [
        {"nv_id": u["nv_id"], "ten": u["display_name"], "role": u["role"]}
        for u in list_users()
    ],
    list_nhan_vien_ops=list_nhan_vien_ops,
    menu_list=menu_list,
    # QUERY_AUDIT provider — vết hệ thống (tenant-scoped, đã redact ở tool)
    audit_list=audit_list,
    # PR11 admin providers — đơn quầy cho snapshot/validate
    don_list=don_list,
    don_get=don_get,
    # PR12 external channel provider — trạng thái Page (đã redact token)
    page_status=lambda: {
        "mode": os.environ.get("NHIPQUAN_PAGE_MODE", "replay").strip().lower() or "replay",
        "connected": False,
    },
    extract_tkb=_extract_tkb,
    # Khảo sát thị trường & SerpApi providers (plan 260913-2340 v2.0)
    # Dùng _adapted_serpapi_quota() để chuẩn hóa schema: serpapi_client trả
    # keys (used_requests, total_limit) nhưng tool_registry expect (used_count,
    # monthly_limit). _adapted_serpapi_quota là boundary adapter duy nhất.
    get_serpapi_quota=_adapted_serpapi_quota,
    get_circuit_breaker_state=lambda: _get_circuit_breaker().state,
    get_store_survey_count_today=lambda sid: _get_job_store().count_today(sid),
    get_latest_survey=lambda sid="": _get_job_store().get_latest_completed_job(sid),
)


def _require_write_role(authorization: Annotated[str | None, Header()] = None) -> str:
    """Dependency: require quan_ly or chu_quan for write endpoints."""
    role = _resolve_role(authorization)
    if role not in {"quan_ly", "chu_quan"}:
        raise HTTPException(status_code=403, detail="forbidden — requires quan_ly or chu_quan")
    return role


def _require_authenticated_role(authorization: Annotated[str | None, Header()] = None) -> str:
    """Dependency: require login token for read endpoints."""
    role = _resolve_role(authorization)
    if not role:
        raise HTTPException(status_code=401, detail="unauthorized — login required")
    return role


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {"status": "ok", "service": "ca-api", "minimal_data_mode": minimal_data_mode()}


# ── Lich tuan ─────────────────────────────────────────────────────────────────

THU_MAP = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}


_KHUNG_DEFAULTS: dict[str, dict[str, str]] = {
    "sang": {"bat_dau": "07:00", "ket_thuc": "12:00"},
    "chieu": {"bat_dau": "12:00", "ket_thuc": "17:00"},
    "toi": {"bat_dau": "17:00", "ket_thuc": "22:00"},
}


def _khung_template() -> dict[str, dict[str, str]]:
    stored = kv_get("khung_gio", None)
    if not isinstance(stored, dict):
        return {k: dict(v) for k, v in _KHUNG_DEFAULTS.items()}
    out: dict[str, dict[str, str]] = {}
    for key, default in _KHUNG_DEFAULTS.items():
        slot = stored.get(key)
        if not isinstance(slot, dict):
            out[key] = dict(default)
            continue
        out[key] = {
            "bat_dau": str(slot.get("bat_dau", default["bat_dau"])),
            "ket_thuc": str(slot.get("ket_thuc", default["ket_thuc"])),
        }
    return out


def _apply_khung_template(ca_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tmpl = _khung_template()
    out: list[dict[str, Any]] = []
    for c in ca_list:
        c_copy = dict(c)
        khung = str(c_copy.get("khung", ""))
        if khung in tmpl:
            c_copy["bat_dau"] = tmpl[khung]["bat_dau"]
            c_copy["ket_thuc"] = tmpl[khung]["ket_thuc"]
        out.append(c_copy)
    return out


def _format_ca_list(ca_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in ca_list:
        c_copy = dict(c)
        if "thu" not in c_copy or not c_copy["thu"]:
            c_copy["thu"] = THU_MAP.get(int(c_copy.get("ngay_offset", 1)), "T2")
        out.append(c_copy)
    return _apply_khung_template(out)


def _tuan_list(base_tuan: str, so_tuan: int) -> list[str]:
    """Sinh danh sách các tuần ISO liên tiếp từ tuần bắt đầu."""
    import re

    m = re.match(r"^(\d{4})-W(\d{2})$", base_tuan)
    if not m:
        return [base_tuan]
    y, w = int(m.group(1)), int(m.group(2))
    weeks = []
    for offset in range(max(1, min(4, so_tuan))):
        cur_w = w + offset
        cur_y = y
        if cur_w > 52:
            cur_w -= 52
            cur_y += 1
        weeks.append(f"{cur_y}-W{cur_w:02d}")
    return weeks


def _detect_staff_availability(
    tuan_iso: str,
    phan_cong: dict[str, list[str]],
    nhan_vien_list: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    status_store = kv_get("roster_nv_status", {})
    week_decisions = status_store.get(tuan_iso, {}) if isinstance(status_store, dict) else {}

    inbox_items = kv_get("inbox_rang_buoc", [])
    inbox_submitted_nv: set[str] = set()
    if isinstance(inbox_items, list):
        for it in inbox_items:
            if not isinstance(it, dict):
                continue
            rb = cast(dict[str, Any], it.get("rang_buoc")) if isinstance(it.get("rang_buoc"), dict) else {}
            hl = cast(dict[str, Any], it.get("hieu_luc")) if isinstance(it.get("hieu_luc"), dict) else {}
            it_tuan = rb.get("tuan_id") or hl.get("tuan_id") or it.get("tuan_id")
            if it_tuan == tuan_iso:
                nvid = it.get("nv_id") or hl.get("nv_id")
                if nvid:
                    inbox_submitted_nv.add(str(nvid))

    tkb_by_week = kv_get("tkb_nv_by_week", {})
    tkb_nv = tkb_by_week.get(tuan_iso, {}) if isinstance(tkb_by_week, dict) else {}
    tkb_confirmed_nv: set[str] = set()
    if isinstance(tkb_nv, dict):
        tkb_confirmed_nv.update(str(nvid) for nvid in tkb_nv)
    legacy_tkb = kv_get("tkb_nv", {})
    if isinstance(legacy_tkb, dict):
        for nvid, entry in legacy_tkb.items():
            if isinstance(entry, dict) and entry.get("tuan_iso") == tuan_iso:
                tkb_confirmed_nv.add(str(nvid))

    assigned_count: dict[str, int] = {}
    assigned_shifts: dict[str, list[str]] = {}
    for ca_id, nv_ids in phan_cong.items():
        if isinstance(nv_ids, list):
            for nvid in nv_ids:
                s_nid = str(nvid)
                assigned_count[s_nid] = assigned_count.get(s_nid, 0) + 1
                assigned_shifts.setdefault(s_nid, []).append(str(ca_id))

    chua_xac_nhan: list[dict[str, Any]] = []
    du_bi: list[dict[str, Any]] = []
    nv_status_map: dict[str, str] = {}

    for nv in nhan_vien_list:
        nvid = str(nv.get("id", ""))
        if not nvid:
            continue
        ten = str(nv.get("ten") or nv.get("username") or nvid)
        vai = str(nv.get("vai") or "nhan_vien")
        decision = week_decisions.get(nvid)

        if decision == "du_bi":
            nv_status_map[nvid] = "du_bi"
            du_bi.append({
                "id": nvid,
                "ten": ten,
                "vai": vai,
            })
        elif decision == "bo_ca":
            nv_status_map[nvid] = "bo_ca"
        elif decision == "xac_nhan":
            nv_status_map[nvid] = "xac_nhan"
        else:
            if nvid in inbox_submitted_nv or nvid in tkb_confirmed_nv:
                nv_status_map[nvid] = "xac_nhan"
            else:
                nv_status_map[nvid] = "chua_xac_nhan"
                if assigned_count.get(nvid, 0) > 0:
                    chua_xac_nhan.append({
                        "id": nvid,
                        "ten": ten,
                        "vai": vai,
                        "so_ca_du_kien": assigned_count[nvid],
                        "ca_ids": assigned_shifts.get(nvid, []),
                    })

    return chua_xac_nhan, du_bi, nv_status_map


def _loc_phan_cong_theo_nhan_su(
    phan_cong: dict[str, list[str]], nhan_vien: list[dict[str, Any]]
) -> None:
    """Bỏ mọi nv_id trong `phan_cong` không còn là nhân sự của quán (sửa tại chỗ).

    Vì sao cần: `phan_cong` đến từ ẢNH CHỤP LƯU LẠI (solver, ghim) — ghi ở thời
    điểm khác với lúc đọc. Nhân sự bị xoá sau đó vẫn nằm trong ảnh chụp, nên id
    của họ (ví dụ `nv_26`…`nv_38` do `_nv_id_ke_tiep` cấp cho tài khoản đã đăng
    ký rồi bị xoá) lọt ra giao diện và `nvName()` in nguyên chuỗi `nv_26`.

    Nguồn sự thật về "ai đang làm ở quán" là `nhan_vien`, không phải ảnh chụp.
    Lọc ở tầng dữ liệu (không ở giao diện) để số đếm nhân sự, chấm "đủ/thiếu" và
    mọi bề mặt dùng chung đều đúng theo.

    KHÔNG áp cho lịch sử seed: xem ghi chú ở `_build_lich_tuan_from_seed`.
    """
    hop_le = {str(nv.get("id")) for nv in nhan_vien}
    for ca_id, nv_ids in phan_cong.items():
        phan_cong[ca_id] = [nid for nid in nv_ids if str(nid) in hop_le]


def _build_lich_tuan_from_seed(
    seed: dict[str, Any], tuan: str | None, so_tuan: int = 1
) -> dict[str, Any]:
    """Build the roster from seeded assignments when solver output is absent."""
    nhan_vien = list_nhan_vien_ops()
    ca_raw = seed.get("ca_mau_21", [])
    ca_list = _format_ca_list(ca_raw)
    tuan_iso = tuan or "2026-W36"
    phan_cong: dict[str, list[str]] = {
        str(ca_id): list(nv_ids)
        for ca_id, nv_ids in (_week_value("phan_cong_by_week", tuan_iso, {}) or {}).items()
    }
    for (ca_id, nv_id), pinned in _pin_map(tuan_iso).items():
        if pinned:
            if nv_id not in phan_cong.setdefault(ca_id, []):
                phan_cong[ca_id].append(nv_id)
        elif nv_id in phan_cong.get(ca_id, []):
            phan_cong[ca_id].remove(nv_id)

    status_store = kv_get("roster_nv_status", {})
    week_decisions = status_store.get(tuan_iso, {}) if isinstance(status_store, dict) else {}
    for ca_id, nv_ids in phan_cong.items():
        phan_cong[ca_id] = [nid for nid in nv_ids if week_decisions.get(nid) not in {"du_bi", "bo_ca"}]

    # KHÔNG lọc theo `nhan_vien` ở nhánh này.
    #
    # Nhánh này chỉ chạy khi CHƯA có kết quả solver, và nguồn lịch sử duy nhất là
    # fixture demo (`data/seed/sample.json`) — dữ liệu tham chiếu được biên soạn
    # tay, không phải ảnh chụp sinh tự động. Nhân sự trong đó (`nv_07`, `nv_19`…)
    # KHÔNG nằm trong bảng `users` của môi trường test/demo, nên lọc theo
    # `nhan_vien` sẽ xoá sạch lịch sử thật (test
    # `test_lich_output_rong_fallback_phan_cong_seed_history` bắt đúng lỗi này).
    #
    # "Id ma" chỉ sinh ra từ ẢNH CHỤP SOLVER, nên chỉ nhánh solver cần chốt.

    chua_xac_nhan, du_bi, nv_status_map = _detect_staff_availability(tuan_iso, phan_cong, nhan_vien)

    return {
        "nguon": "quan",
        "nguon_lich": "chua_xep",
        "tuan_iso": tuan_iso,
        "so_tuan": so_tuan,
        "danh_sach_tuan": _tuan_list(tuan_iso, so_tuan),
        "trang_thai": "nhap",
        "nhan_vien": nhan_vien,
        "ca": ca_list,
        "phan_cong": phan_cong,
        "chua_xac_nhan": chua_xac_nhan,
        "du_bi": du_bi,
        "nv_status_map": nv_status_map,
    }


def _seeded_history_assignments(seed: dict[str, Any], tuan_iso: str) -> dict[str, list[str]]:
    histories = seed.get("lich_su_8_tuan", [])
    matching = next((item for item in histories if item.get("tuan_iso") == tuan_iso), None)
    source = matching or next((item for item in histories if item.get("phan_cong")), None)
    if not source:
        return {}
    return {
        str(ca_id): list(nv_ids)
        for ca_id, nv_ids in (source.get("phan_cong", {}) or {}).items()
        if isinstance(nv_ids, list)
    }


@app.get("/api/v1/lich-tuan")
def get_lich_tuan(
    tuan: Annotated[str | None, Query(description="ISO week e.g. 2026-W36")] = None,
    so_tuan: Annotated[int, Query(ge=1, le=4, description="Số tuần xếp lịch: 1, 2, 3 hoặc 4")] = 1,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Lịch tuần đang hiệu lực của quán. Yêu cầu đăng nhập (quan_ly trở lên)."""
    _require_write_role(authorization)
    tuan_iso = tuan or "2026-W36"
    current_session = auth_session(authorization) or {}
    store_id = str(current_session.get("store_id") or "quan_01")
    schedule_run = schedule_run_latest(store_id, tuan_iso)
    # Nguồn DUY NHẤT cho "ca thiếu người thật" — xem `current_open_shifts`:
    # chỉ ca của lần xếp gần nhất, và (nếu biết phân công) chỉ ca chưa đủ người.
    # Lọc theo `phan_cong` được làm SAU khi dựng xong phân công bên dưới.
    from ca_api.services.scheduling_service import current_open_shifts

    open_shifts = current_open_shifts(store_id, tuan_iso)

    data = _week_value("lich_tuan_results_by_week", tuan_iso, None)
    if not isinstance(data, dict):
        lich_out = _lich_tuan_out()
        if lich_out.exists():
            candidate = json.loads(lich_out.read_text(encoding="utf-8"))
            candidate_week = candidate.get("tuan_iso")
            data = candidate if not candidate_week or candidate_week == tuan_iso else None
    if isinstance(data, dict):
        seed = _seed()
        ca_list = _format_ca_list(seed.get("ca_mau_21", []))
        solver_assignments = data.get("phan_cong", {})
        seeded_assignments = dict(_week_value("phan_cong_by_week", tuan_iso, {}) or {})
        valid_ca_ids = {str(shift.get("id")) for shift in ca_list}
        phan_cong = {
            str(ca_id): list(nv_ids)
            for ca_id, nv_ids in solver_assignments.items()
            if str(ca_id) in valid_ca_ids
        }
        for ca_id, nv_ids in seeded_assignments.items():
            if str(ca_id) not in phan_cong:
                phan_cong[str(ca_id)] = list(nv_ids)
        # `tu_seed_lich_su` = lịch sử fixture biên soạn tay, KHÔNG phải ảnh chụp
        # solver. Nhánh này lọc theo `nhan_vien` được, còn lịch sử seed thì không
        # (xem ghi chú ở `_build_lich_tuan_from_seed`).
        tu_seed_lich_su = False
        if not phan_cong:
            phan_cong = _seeded_history_assignments(seed, tuan_iso)
            tu_seed_lich_su = bool(phan_cong)
        for (ca_id, nv_id), pinned in _pin_map(tuan_iso).items():
            if pinned and nv_id not in phan_cong.get(ca_id, []):
                phan_cong.setdefault(ca_id, []).append(nv_id)

        status_store = kv_get("roster_nv_status", {})
        week_decisions = status_store.get(tuan_iso, {}) if isinstance(status_store, dict) else {}
        for ca_id, nv_ids in phan_cong.items():
            phan_cong[ca_id] = [nid for nid in nv_ids if week_decisions.get(nid) not in {"du_bi", "bo_ca"}]

        nhan_vien = list_nhan_vien_ops()

        # CHỐT TOÀN VẸN THAM CHIẾU — chỉ cho dữ liệu từ ẢNH CHỤP.
        #
        # `phan_cong` ghép từ ảnh chụp solver + ghim, ghi ở thời điểm khác lúc đọc.
        # Nhân sự bị xoá sau đó vẫn còn trong ảnh chụp → id lọt ra UI và `nvName()`
        # in nguyên chuỗi `nv_26`. Xem `_loc_phan_cong_theo_nhan_su`.
        #
        # KHÔNG áp khi `phan_cong` đến từ lịch sử seed: nhân sự trong fixture demo
        # không nằm trong bảng `users` của môi trường test, lọc sẽ xoá sạch lịch sử.
        if not tu_seed_lich_su:
            _loc_phan_cong_theo_nhan_su(phan_cong, nhan_vien)

        chua_xac_nhan, du_bi, nv_status_map = _detect_staff_availability(tuan_iso, phan_cong, nhan_vien)

        # Bỏ ca thiếu ĐÃ ĐƯỢC LẤP (đủ người trong `phan_cong` hiện tại) — dùng
        # chung `current_open_shifts` với chợ đổi ca để hai bề mặt không lệch.
        open_shifts = current_open_shifts(
            store_id, tuan_iso, phan_cong=phan_cong, ca_list=ca_list,
        )

        lifecycle = _week_value("lich_tuan_lifecycle_by_week", tuan_iso, {})
        return {
            "nguon": "quan",
            "nguon_lich": "solver",
            "tuan_iso": tuan_iso,
            "so_tuan": so_tuan,
            "danh_sach_tuan": _tuan_list(tuan_iso, so_tuan),
            "trang_thai": lifecycle.get("trang_thai", "nhap"),
            "nhan_vien": nhan_vien,
            "ca": ca_list,
            "phan_cong": phan_cong,
            "khung_gio": _khung_template(),
            "solver": {
                "ok": data.get("ok"),
                "elapsed_s": data.get("elapsed_s"),
                "status": data.get("status"),
            },
            "schedule_run": schedule_run,
            "open_shifts": open_shifts,
            "pins": [
                {"ca_id": ca_id, "nv_id": nv_id}
                for (ca_id, nv_id), pinned in _pin_map(tuan_iso).items()
                if pinned
            ],
            "kiem_tra": data.get("kiem_tra"),
            "chua_xac_nhan": chua_xac_nhan,
            "du_bi": du_bi,
            "nv_status_map": nv_status_map,
        }
    lifecycle = _week_value("lich_tuan_lifecycle_by_week", tuan_iso, {})
    result = _build_lich_tuan_from_seed(_seed(), tuan_iso, so_tuan)
    result["trang_thai"] = lifecycle.get("trang_thai", result.get("trang_thai", "nhap"))
    result["khung_gio"] = _khung_template()
    result["schedule_run"] = schedule_run
    # `open_shifts` đã được `current_open_shifts` neo theo lần xếp gần nhất ở
    # đầu hàm; nhánh seed dùng nguyên danh sách đó.
    result["open_shifts"] = open_shifts
    return result


class KhungSlotBody(BaseModel):
    bat_dau: str
    ket_thuc: str


class KhungGioBody(BaseModel):
    sang: KhungSlotBody | None = None
    chieu: KhungSlotBody | None = None
    toi: KhungSlotBody | None = None


def _valid_hhmm(value: str) -> bool:
    import re

    return bool(re.match(r"^\d{2}:\d{2}$", value))


def _minutes_hhmm(value: str) -> int:
    h, m = value.split(":", 1)
    return int(h) * 60 + int(m)


@app.patch("/api/v1/lich-tuan/khung-gio")
def patch_khung_gio(
    body: KhungGioBody,
    _role: Annotated[str, Depends(_require_write_role)],
) -> dict[str, Any]:
    """Cập nhật template giờ cho 3 khung ca (sáng/chiều/tối)."""
    current = _khung_template()
    updates = {
        "sang": body.sang,
        "chieu": body.chieu,
        "toi": body.toi,
    }
    for key, slot in updates.items():
        if slot is None:
            continue
        if not _valid_hhmm(slot.bat_dau) or not _valid_hhmm(slot.ket_thuc):
            raise HTTPException(status_code=422, detail="invalid_time_format")
        if _minutes_hhmm(slot.bat_dau) >= _minutes_hhmm(slot.ket_thuc):
            raise HTTPException(status_code=422, detail="bat_dau_must_be_before_ket_thuc")
        current[key] = {"bat_dau": slot.bat_dau, "ket_thuc": slot.ket_thuc}
    kv_set("khung_gio", current)
    record_sua(
        loai="khung_gio",
        truoc={},
        sau=current,
        ai=_role,
        now_iso=datetime.now(UTC).isoformat(),
    )
    return {"ok": True, "khung_gio": current}


@app.post("/api/v1/lich-tuan/pin")
async def pin_assignment(
    body: PinBody,
    request: Request,
    _role: Annotated[str, Depends(_require_write_role)],
) -> dict[str, Any]:
    """Pin or unpin a nhan_vien to a ca. Requires quan_ly or chu_quan token."""
    # NV hợp lệ = pool xếp lịch (users thật + seed nếu bật) — không chỉ seed:
    # pin từ chối users thật sẽ ẩn lỗi sau modal roster (đã sửa 2026-09-07).
    seed = _seed()
    ca = next((c for c in seed.get("ca_mau_21", []) if c["id"] == body.ca_id), None)
    nv_pool = {n["id"]: n for n in list_nhan_vien_ops()}
    if ca is None or body.nv_id not in nv_pool:
        raise HTTPException(status_code=404, detail="ca_or_nv_not_found")
    # Ghim phải khớp kỹ năng vị trí ca — nếu không, C01 cắt biến khi giải lại
    # và C02 thiếu ứng viên → INFEASIBLE toàn lịch vì một lần pin sai.
    vi_tri = str(ca.get("vi_tri") or "")
    ky_nang = set(nv_pool[body.nv_id].get("ky_nang") or [])
    if body.pinned and vi_tri and vi_tri not in ky_nang and "da_nang" not in ky_nang:
        raise HTTPException(
            status_code=422,
            detail=f"nv_thieu_ky_nang — ca cần {vi_tri}, NV chỉ có {', '.join(sorted(ky_nang)) or 'không rõ'}",
        )
    from ca_api.interfaces.http.sprint45 import _life
    from ca_api.services.solver_adapter import run_solver

    session = auth_session(request.headers.get("authorization")) or {}
    store_id = str(session.get("store_id") or "quan_01")
    life = _life(body.tuan_iso, store_id=store_id)
    if life.get("trang_thai") not in {"nhap", "cho_duyet"}:
        raise HTTPException(status_code=409, detail="chi_ghim_khi_lich_nhap_hoac_cho_duyet")

    solver_result: dict[str, Any] | None = None
    if body.pinned:
        # Chạy thử với pin mới: đây là kiểm tra đồng thời C01–C06, không chỉ kỹ năng.
        solver_result = run_solver(body.tuan_iso, extra_pin=(body.ca_id, body.nv_id), store_id=store_id)
        if not solver_result.get("ok"):
            baseline = run_solver(body.tuan_iso, store_id=store_id)
            if baseline.get("ok"):
                detail = solver_result.get("danh_sach_xung_dot") or [
                    "Ghim làm lịch vi phạm ràng buộc cứng"
                ]
                raise HTTPException(
                    status_code=422,
                    detail={"code": "pin_xung_dot", "reasons": detail},
                )

    prev = _set_pin(body.tuan_iso, body.ca_id, body.nv_id, body.pinned)
    if body.xep_lai and not body.pinned:
        solver_result = run_solver(body.tuan_iso, store_id=store_id)
    record_sua(
        loai="pin_ca",
        truoc={"ca_id": body.ca_id, "nv_id": body.nv_id, "pinned": prev},
        sau={
            "tuan_iso": body.tuan_iso,
            "ca_id": body.ca_id,
            "nv_id": body.nv_id,
            "pinned": body.pinned,
        },
        ai=_role,
        now_iso=datetime.now(UTC).isoformat(),
    )
    await notify_ops_changed("roster:pin", body.tuan_iso)
    return {
        "ok": True,
        "tuan_iso": body.tuan_iso,
        "ca_id": body.ca_id,
        "nv_id": body.nv_id,
        "pinned": body.pinned,
        "solver": solver_result,
    }


_LIFECYCLE_STATES = ("nhap", "dang_giai", "cho_duyet", "da_duyet", "da_cong_bo", "da_dong")

# Ma trận chuyển tiếp NGUỒN DUY NHẤT — nằm trong `sprint45`, cả hai đường dùng chung.
#
# Vì sao phải gom về một chỗ: trước đây `main.py` và `sprint45.py` mỗi bên khai một
# bản, và chúng ĐÃ LỆCH THẬT ở đúng một ô — `da_cong_bo -> nhap`. Hệ quả: "mở lại
# lịch đã công bố" chạy được qua `POST /lich/lifecycle` nhưng trả 409
# `illegal:da_cong_bo->nhap` qua `PATCH /lich-tuan/lifecycle`. UI hiện gọi đúng
# đường (dùng POST khi cần lý do) nên người dùng chưa thấy, nhưng bất kỳ client
# API, test hay agent nào chọn nhầm đường đều nhận lỗi cho một thao tác mà đường
# kia cho phép — đúng loại lỗi "lúc được lúc không" khó truy nhất.
#
# Alias `_LIFECYCLE_ALLOWED` giữ nguyên tên cũ để không phá import nào đang dùng.
_LIFECYCLE_ALLOWED: dict[str, set[str]] = _SHARED_ALLOWED


class LifecycleBody(BaseModel):
    trang_thai: str
    tuan_iso: str | None = None


@app.patch("/api/v1/lich-tuan/lifecycle")
async def patch_lifecycle(
    body: LifecycleBody,
    _role: Annotated[str, Depends(_require_write_role)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Quản lý/Chủ quán cập nhật trạng thái và mốc tuần lịch.

    Chuyển trạng thái hợp lệ: may_sinh → nhap → dang_giai → cho_duyet → da_duyet
    → da_cong_bo → da_dong, kèm mở lại về `nhap` (xem `_LIFECYCLE_ALLOWED`).
    `dang_giai` chạy solver CP-SAT ngay (như POST /lich/lifecycle) — UI một nút.
    Chỉ chu_quan mới có thể cập nhật tuan_iso (chuyển sang tuần khác).

    Cùng state machine với `POST /api/v1/lich/lifecycle` — dùng CHUNG một ma trận
    (`_LIFECYCLE_ALLOWED is sprint45._ALLOWED`). Khác biệt duy nhất có chủ đích:
    đường POST nhận `ly_do` trong body và ghi audit, còn PATCH đòi lý do qua cổng
    `mo_lai_phai_co_ly_do` — cả hai đều KHÔNG cho mở lại lịch đã chốt mà không có lý do.
    """
    if body.trang_thai not in _LIFECYCLE_STATES:
        raise HTTPException(
            status_code=422,
            detail=f"trang_thai_khong_hop_le — cho phep: {', '.join(_LIFECYCLE_STATES)}",
        )
    if body.trang_thai == "da_dong" and _role != "chu_quan":
        raise HTTPException(status_code=403, detail="chi_chu_quan_dong_lich")
    from ca_api.interfaces.http.sprint45 import (
        _guard_authoritative_lifecycle,
        _life,
        _publish_schedule_notification,
        _save_life,
    )
    from ca_api.services.scheduling_service import run_authoritative_schedule

    week = body.tuan_iso or "2026-W36"
    session = auth_session(authorization)
    store_id = str((session or {}).get("store_id") or "quan_01")
    doc = _life(week, store_id=store_id)
    cur = doc.get("trang_thai", "nhap")

    # Mở lại lịch ĐÃ CHỐT (đã duyệt / công bố / đóng) về nháp là thao tác phá một
    # quyết định đã ban hành, nên phải có lý do ghi lại. `POST /lich/lifecycle`
    # đã ép điều này từ trước; PATCH thiếu, và vì ma trận PATCH trước đây không
    # cho `da_cong_bo -> nhap` nên lỗ hổng bị che. Nay hai ma trận hợp nhất thì
    # PHẢI bổ sung, không thì mở lại lịch công bố qua PATCH sẽ đi qua im lặng.
    if cur in {"da_duyet", "da_cong_bo", "da_dong"} and body.trang_thai == "nhap":
        raise HTTPException(status_code=409, detail="mo_lai_phai_co_ly_do")

    if body.trang_thai not in _LIFECYCLE_ALLOWED.get(cur, set()):
        raise HTTPException(
            status_code=409,
            detail=f"illegal:{cur}->{body.trang_thai}",
        )

    effective_state = "da_cong_bo" if body.trang_thai == "da_duyet" else body.trang_thai
    if effective_state == "da_cong_bo":
        _guard_authoritative_lifecycle(week, effective_state, store_id)

    def chuyen(trang_thai: str) -> dict[str, Any]:
        doc["trang_thai"] = trang_thai
        doc["tuan_iso"] = week
        doc["cap_nhat_luc"] = datetime.now(UTC).isoformat()
        doc["cap_nhat_boi"] = _role
        _save_life(doc, store_id=store_id)
        return doc

    solver_ket_qua: dict[str, Any] | None = None
    authoritative: dict[str, Any] | None = None
    if body.trang_thai == "dang_giai":
        from ca_api.services.scheduling_service import authoritative_input_fingerprint
        _, fingerprint = authoritative_input_fingerprint(store_id, week)
        authoritative = run_authoritative_schedule(
            store_id=store_id, tuan_iso=week, actor_id=_role,
            idempotency_key=f"lifecycle:{week}:solve:{fingerprint[:16]}",
        )
        solver_ket_qua = authoritative.get("result") or {}
        if not solver_ket_qua.get("ok"):
            new_state = chuyen("nhap")
            return {"ok": True, **new_state, "solver": solver_ket_qua}

    new_state = chuyen("cho_duyet" if body.trang_thai == "dang_giai" else effective_state)
    record_sua(
        loai="lifecycle",
        truoc={},
        sau={"trang_thai": body.trang_thai, "tuan_iso": body.tuan_iso},
        ai=_role,
        now_iso=datetime.now(UTC).isoformat(),
    )

    if effective_state == "da_cong_bo":
        _publish_schedule_notification(week, store_id)

    if body.trang_thai == "dang_giai":
        record_sua(
            loai="lifecycle",
            truoc={"trang_thai": "dang_giai"},
            sau={"trang_thai": "cho_duyet", "tu_solver": True},
            ai=_role,
            now_iso=datetime.now(UTC).isoformat(),
        )

    await notify_ops_changed("roster:lifecycle", body.tuan_iso)
    return {"ok": True, **new_state, "solver": solver_ket_qua}


@app.get("/api/v1/lich-tuan/thay-doi")
def get_lich_thay_doi(
    _role: Annotated[str, Depends(_require_write_role)],
    tuan_iso: str = Query(default="2026-W36"),
) -> dict[str, Any]:
    """Nhật ký thay đổi ca của một tuần — bằng chứng "ai đổi ca với ai".

    Vì sao cần endpoint riêng thay vì nhét diff vào `GET /lich-tuan`: lịch tuần
    được gọi lại RẤT thường xuyên (mỗi lần đổi tuần, mỗi lần có sự kiện realtime).
    Diff chỉ cần khi người dùng chủ động hỏi "vì sao lịch đổi", nên tách ra để
    không làm nặng đường đọc chính.

    Trả bản MỚI NHẤT trước. Mỗi bản đã ở dạng đọc được (diff có tên người), UI
    không phải tự ghép id.
    """
    raw = kv_get("lich_thay_doi_by_week", {})
    items = raw.get(tuan_iso, []) if isinstance(raw, dict) else []
    if not isinstance(items, list):
        items = []
    return {
        "tuan_iso": tuan_iso,
        "so_ban_ghi": len(items),
        "items": list(reversed(items)),
    }


@app.post("/api/v1/lich-tuan/nv-status")
async def post_nv_status(
    body: NvStatusBody,
    _role: Annotated[str, Depends(_require_write_role)],
) -> dict[str, Any]:
    """Cập nhật trạng thái xác nhận ca tuần cho một nhân sự.

    Hành động:
    - `xac_nhan`: Quản lý xác nhận giữ các ca dự kiến cho nhân viên này.
    - `du_bi`: Tháo nhân viên khỏi các ca cố định tuần này, đưa vào danh sách Trực dự bị On-call.
    - `bo_ca`: Tháo nhân viên khỏi các ca tuần này (không phân công tuần này).
    - `dat_lai`: Xóa quyết định thủ công để hệ thống tự tính lại.
    """
    valid_actions = {"xac_nhan", "du_bi", "bo_ca", "dat_lai"}
    if body.hanh_dong not in valid_actions:
        raise HTTPException(
            status_code=422,
            detail=f"hanh_dong_khong_hop_le — cho phep: {', '.join(sorted(valid_actions))}",
        )

    def mut_status(store: dict[str, Any]) -> dict[str, Any]:
        week_data = store.setdefault(body.tuan_iso, {})
        if body.nv_id == "all":
            all_nvs = list_nhan_vien_ops()
            for nv in all_nvs:
                nid = str(nv.get("id") or "")
                if nid:
                    if body.hanh_dong == "dat_lai":
                        week_data.pop(nid, None)
                    else:
                        week_data[nid] = body.hanh_dong
        elif body.hanh_dong == "dat_lai":
            week_data.pop(body.nv_id, None)
        else:
            week_data[body.nv_id] = body.hanh_dong
        return store

    kv_mutate("roster_nv_status", mut_status, {})

    if body.hanh_dong in {"du_bi", "bo_ca"}:
        def mut_pc(cur: dict[str, Any]) -> dict[str, Any]:
            for cid, nv_ids in list(cur.items()):
                if isinstance(nv_ids, list):
                    if body.nv_id == "all":
                        cur[cid] = []
                    elif body.nv_id in nv_ids:
                        cur[cid] = [x for x in nv_ids if x != body.nv_id]
            return cur

        def mut_pc_weeks(all_weeks: dict[str, Any]) -> dict[str, Any]:
            week_pc = all_weeks.setdefault(body.tuan_iso, {})
            all_weeks[body.tuan_iso] = mut_pc(week_pc)
            return all_weeks

        kv_mutate("phan_cong_by_week", mut_pc_weeks, {})

        lich_out = _lich_tuan_out()
        if lich_out.exists():
            try:
                out_data = json.loads(lich_out.read_text(encoding="utf-8"))
                if out_data.get("tuan_iso") == body.tuan_iso:
                    pc = out_data.get("phan_cong", {})
                    changed = False
                    for cid, nv_ids in pc.items():
                        if isinstance(nv_ids, list):
                            if body.nv_id == "all":
                                pc[cid] = []
                                changed = True
                            elif body.nv_id in nv_ids:
                                pc[cid] = [x for x in nv_ids if x != body.nv_id]
                                changed = True
                    if changed:
                        lich_out.write_text(
                            json.dumps(out_data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
            except Exception:
                pass

        def mut_pins(cur: dict[str, Any]) -> dict[str, Any]:
            week_pins = cur.setdefault(body.tuan_iso, {})
            for k in list(week_pins.keys()):
                if body.nv_id == "all" or f"|{body.nv_id}" in str(k):
                    week_pins.pop(k, None)
            return cur

        kv_mutate("pins_by_week", mut_pins, {})

    record_sua(
        loai="roster_nv_status",
        truoc={},
        sau={"tuan_iso": body.tuan_iso, "nv_id": body.nv_id, "hanh_dong": body.hanh_dong},
        ai=_role,
        now_iso=datetime.now(UTC).isoformat(),
    )
    await notify_ops_changed("roster:nv-status", body.tuan_iso)

    return {
        "ok": True,
        "tuan_iso": body.tuan_iso,
        "nv_id": body.nv_id,
        "hanh_dong": body.hanh_dong,
    }


@app.post("/api/v1/lich-tuan/xac-nhan-lich")
async def post_nv_self_confirm(
    body: XacNhanLichBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Nhân viên tự bấm xác nhận sẵn sàng đi làm theo ca được xếp cho tuần này."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    nv_id = s.get("nv_id")
    if not nv_id:
        raise HTTPException(status_code=400, detail="khong_tim_thay_nv_id")

    def mut_status(store: dict[str, Any]) -> dict[str, Any]:
        week_data = store.setdefault(body.tuan_iso, {})
        week_data[nv_id] = "xac_nhan"
        return store

    kv_mutate("roster_nv_status", mut_status, {})
    record_sua(
        loai="nv_tu_xac_nhan_lich",
        truoc={},
        sau={"tuan_iso": body.tuan_iso, "nv_id": nv_id},
        ai=nv_id,
        now_iso=datetime.now(UTC).isoformat(),
    )
    await notify_ops_changed("roster:nv-status", body.tuan_iso)
    return {"ok": True, "tuan_iso": body.tuan_iso, "nv_id": nv_id, "hanh_dong": "xac_nhan"}


# ── Auth ──────────────────────────────────────────────────────────────────────


@app.post("/api/v1/auth/register", response_model=LoginOut, status_code=201)
def register(body: RegisterBody) -> LoginOut:
    """Tạo tài khoản nhân viên mới rồi mở phiên luôn.

    Vai trò luôn là `nhan_vien` (xem `persist.VAI_TU_DANG_KY`): tự đăng ký mà
    lấy được vai quản lý thì ai cũng duyệt được ràng buộc và phát được mã điểm
    danh. Nâng vai là việc của chủ quán, làm ngoài luồng này.
    """
    try:
        row = persist_register(body.username, body.password, body.display_name)
    except DangKyLoi as exc:
        raise HTTPException(status_code=409, detail=exc.ma) from exc
    audit_add(
        datetime.now(UTC).isoformat(),
        row["nv_id"],
        "user.register",
        {
            "entity_type": "user",
            "entity_id": body.username.strip().lower(),
            "username": body.username.strip().lower(),
            "role": row["role"],
        },
    )
    return LoginOut(**row)


def _client_ip(request: Request) -> str:
    """IP client cho rate limit — ưu tiên header proxy, fallback về client trực tiếp."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.post("/api/v1/auth/login", response_model=LoginOut)
async def login(body: LoginBody, request: Request) -> LoginOut:
    # Chống dò mật khẩu hàng loạt: quá 5 lần sai trong 10 phút từ 1 IP → khóa tạm.
    ip = _client_ip(request)
    if await login_ip_limiter.is_blocked(ip):
        raise HTTPException(status_code=429, detail="thu_qua_nhieu_lan_thu_lai_sau")
    # persist_login băm PBKDF2 và đọc SQLite — đều chặn. Handler là async nên phải
    # đẩy sang threadpool, chạy thẳng trên event loop sẽ đứng toàn bộ server
    # (kể cả WebSocket) suốt thời gian băm.
    row = await run_in_threadpool(persist_login, body.username, body.password)
    if not row:
        await login_ip_limiter.record_failure(ip)
        raise HTTPException(status_code=401, detail="sai_thong_tin_dang_nhap")
    await login_ip_limiter.clear(ip)
    return LoginOut(
        token=row["token"],
        role=row["role"],
        display_name=row["display_name"],
        nv_id=row["nv_id"],
        store_id=row["store_id"],
    )


@app.post("/api/v1/auth/logout")
def logout(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    """Đăng xuất: thu hồi token hiện tại. Không lỗi nếu token đã hết hạn."""
    s = auth_session(authorization)
    if s:
        audit_add(
            datetime.now(UTC).isoformat(),
            s["nv_id"],
            "user.logout",
            {"entity_type": "session", "username": s["username"]},
        )
    ok = persist_logout(authorization or "")
    return {"ok": ok}


@app.get("/api/v1/me")
def me(authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    return {
        "username": s["username"],
        "role": s["role"],
        "nv_id": s["nv_id"],
        "store_id": s["store_id"],
    }


@app.get("/api/v1/contracts")
def five_contracts() -> dict[str, object]:
    """5 hợp đồng dữ liệu mẫu (ADR-012) — trang tra cứu công khai.

    Bảo mật (QA 2026-09-26): endpoint không cần đăng nhập nên **không trả họ tên
    đầy đủ** của nhân viên. Tên được rút gọn còn họ + chữ cái đầu ("Lan N.") —
    vẫn minh hoạ đúng cấu trúc hợp đồng mà không phơi danh tính. Mọi bản ghi
    đều là dữ liệu mô phỏng (`la_du_lieu_mo_phong: true`), không phải người thật.
    """
    seed = _seed()

    def _rut_gon_ten(ten: str) -> str:
        parts = str(ten).split()
        if len(parts) <= 1:
            return str(ten)
        return f"{parts[0]} {parts[-1][0]}."

    nv = [
        NhanVien.model_validate(
            {
                **x,
                "ten": _rut_gon_ten(x.get("ten", "")),
                "ky_nang": x.get("ky_nang", []),
            }
        )
        for x in seed.get("nhan_vien", [])[:5]
    ]
    ca_rows = []
    for x in seed.get("ca_mau_21", [])[:5]:
        ca_rows.append(
            Ca(
                id=x["id"],
                ngay=f"2026-01-{x.get('ngay_offset', 1):02d}",
                bat_dau=x["bat_dau"],
                ket_thuc=x["ket_thuc"],
                vi_tri=x["vi_tri"],
                so_nguoi_toi_thieu=x.get("so_nguoi_toi_thieu", 1),
            )
        )
    lich = LichTuan(tuan_iso="2026-W01", trang_thai="nhap", phan_cong={})
    phieu = PhieuMau(ma="mo_quan", ten="Mở quán", buoc=[])
    rb = RangBuocTrichXuat(
        id="rb_01",
        nguon="tkb",
        noi_dung="T2 ca sáng — ràng buộc từ TKB",
        do_tin_cay=0.9,
    )
    mon = MonNuoc(id="mon_den", ten="Cà phê đen", gia=25000, bom={"cafe_g": 18, "ly": 1})
    don = DonQuay(
        id="dq_demo",
        nv_id="nv_03",
        dong=[DongDon(mon_id=mon.id, ten=mon.ten, so_luong=1, gia=mon.gia)],
        luc="2026-01-01T07:00:00Z",
    )
    return {
        "nguon": "quan",
        "adr": "ADR-012",
        "la_du_lieu_mo_phong": True,
        "ghi_chu": "Dữ liệu mẫu để minh hoạ cấu trúc hợp đồng — tên nhân viên đã được rút gọn.",
        "NhanVien": [x.model_dump() for x in nv],
        "Ca": [x.model_dump() for x in ca_rows],
        "LichTuan": lich.model_dump(),
        "PhieuMau": phieu.model_dump(),
        "RangBuocTrichXuat": rb.model_dump(),
        "MonNuoc": mon.model_dump(),
        "DonQuay": don.model_dump(),
        "schemas": [
            "NhanVien",
            "Ca",
            "LichTuan",
            "PhieuMau",
            "RangBuocTrichXuat",
            "MonNuoc",
            "DongDon",
            "DonQuay",
        ],
    }


@app.get("/api/v1/demo/contracts")
def demo_contracts() -> dict[str, object]:
    return five_contracts()
