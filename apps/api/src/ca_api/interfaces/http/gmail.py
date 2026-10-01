"""Gmail management HTTP API — quản lý tài khoản Gmail, hộp thư, nhãn, bộ lọc.

Kiến trúc:
- `ca_agents.ag_gmail` — gọi Gmail API (không chạm DB).
- `ca_api.services.gmail_sync` — điều phối + ghi DB.
- Router này — HTTP surface, xác thực theo pattern `Header()` + `auth_session`
  giống mọi router khác trong repo (không dùng `Depends`).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any
from urllib.parse import urlencode

from ca_agents.ag_gmail import (
    GmailService,
    build_authorization_url,
    exchange_code_for_tokens,
    new_pkce_verifier,
    revoke_token,
)
from ca_contracts import (
    GmailAccountCreateRequest,
    GmailAccountUpdateRequest,
    GmailFilterCreateRequest,
    GmailLabelCreateRequest,
    GmailLabelUpdateRequest,
    GmailOAuthCallbackRequest,
    GmailSendMessageRequest,
    GmailSyncRequest,
)
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import RedirectResponse

from ca_api.interfaces.http.origins import resolve_web_base
from ca_api.persist import (
    gmail_account_create,
    gmail_account_delete,
    gmail_account_get,
    gmail_account_list,
    gmail_account_update,
    gmail_filter_delete,
    gmail_filter_upsert,
    gmail_filters_list,
    gmail_label_delete,
    gmail_label_upsert,
    gmail_labels_list,
    gmail_message_get,
    gmail_message_mark_read,
    gmail_message_star,
    gmail_messages_list,
    gmail_sync_state_get,
    gmail_token_delete,
    gmail_token_get,
    gmail_token_health,
    gmail_token_save,
    gmail_token_status,
    gmail_token_status_bulk,
    kv_mutate,
)
from ca_api.persist import (
    session as auth_session,
)
from ca_api.services.gmail_sync import GmailSyncError, sync_account, sync_all_accounts

router = APIRouter(tags=["gmail"])

# ── Xác thực: Gmail CHỈ dành cho chủ quán ─────────────────────────────────
#
# Quy định vận hành: quản lý/nhân viên không được thấy mail của quán. Mọi
# endpoint dưới đây (trừ GET callback do Google điều hướng — request đó không
# kèm phiên, nhưng `state` dùng một lần và chỉ chủ quán mới tạo được ở bước
# authorize) đều đòi vai `chu_quan` TRƯỚC mọi logic khác.
#
# Tài khoản Gmail gắn với đúng người tạo (`nv_id`): chủ quán tự thêm những
# mail mình muốn theo dõi; mỗi tài khoản là một hộp thư độc lập, không lẫn.


def _owner(authorization: str | None) -> dict[str, str]:
    """Phiên chủ quán hiện tại. 401 thiếu/không hợp lệ, 403 sai vai."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    if s.get("role") != "chu_quan":
        raise HTTPException(status_code=403, detail="chi_danh_cho_chu_quan")
    return s


def _owned_account(account_id: str, caller: dict[str, str]) -> dict[str, Any]:
    """Tài khoản Gmail do CHÍNH người gọi thêm.

    Không tồn tại, khác quán, hay của người khác ⇒ 404 (không tiết lộ).
    """
    account = gmail_account_get(account_id)
    if not account or account["store_id"] != caller.get("store_id", "quan_01"):
        raise HTTPException(status_code=404, detail="khong_tim_thay_tai_khoan")
    if account["nv_id"] != caller.get("nv_id"):
        raise HTTPException(status_code=404, detail="khong_tim_thay_tai_khoan")
    return account


def _service_for(account_id: str) -> GmailService:
    """Khởi tạo GmailService từ token đã lưu. Ném 400 nếu chưa kết nối OAuth."""
    tokens = gmail_token_get(account_id)
    if not tokens or not tokens.get("access_token"):
        raise HTTPException(status_code=400, detail="tai_khoan_chua_ket_noi_oauth")
    return GmailService(str(tokens["access_token"]), tokens.get("refresh_token"))


# ── OAuth ─────────────────────────────────────────────────────────────────


@router.get("/api/v1/gmail/oauth/authorize")
async def gmail_oauth_authorize(
    state: str | None = Query(None),
    authorization: Annotated[str | None, Header()] = None,
    origin: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Trả URL uỷ quyền Google kèm `state` chống CSRF.

    `state` được LƯU kèm nv_id + hạn dùng, và bắt buộc khớp khi callback. Không
    kiểm tra `state` ⇒ kẻ tấn công lừa được nạn nhân hoàn tất OAuth cho tài
    khoản Gmail của kẻ tấn công (login CSRF), rồi đọc mail qua tài khoản đó.

    Chưa cấu hình `NHIPQUAN_GMAIL_CLIENT_ID`/`_SECRET` ⇒ 503 kèm mã lý do,
    KHÔNG để `RuntimeError` nổi lên thành 500 che mất nguyên nhân. Lỗi bất ngờ
    khác (vd thư viện Google cũ không hỗ trợ PKCE) ⇒ 500 kèm mã RIÊNG
    `loi_tao_url_oauth` để nhìn log/Network là phân biệt được ngay với 503.
    """
    caller = _owner(authorization)
    oauth_state = state or uuid.uuid4().hex
    # PKCE: verifier sinh ở đây phải được LƯU và dùng lại khi đổi mã, vì bước
    # callback là request khác (xem `new_pkce_verifier`).
    code_verifier = new_pkce_verifier()
    try:
        auth_url = build_authorization_url(state=oauth_state, code_verifier=code_verifier)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="chua_cau_hinh_oauth_gmail") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — lỗi lạ: giữ mã riêng để dễ chẩn đoán
        raise HTTPException(status_code=500, detail="loi_tao_url_oauth") from exc

    _remember_oauth_state(oauth_state, caller, code_verifier=code_verifier, origin=origin)
    return {"authorization_url": auth_url, "state": oauth_state}


def _remember_oauth_state(
    state: str,
    caller: dict[str, str],
    *,
    code_verifier: str | None = None,
    origin: str | None = None,
) -> None:
    """Ghi `state` vào kv kèm nv_id + store_id và hạn 10 phút.

    Lưu cả store_id vì luồng trình duyệt (GET) không có phiên HTTP để tra lại.
    Lưu thêm `code_verifier` (PKCE) và `origin` của web (để chuyển hướng về
    đúng cổng — xem `resolve_web_base`).
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    deadline = now + timedelta(minutes=10)
    kv_mutate(
        "gmail_oauth_states",
        lambda bag: {
            **{k: v for k, v in bag.items() if v.get("deadline", "") > now.isoformat()},
            state: {
                "nv_id": caller.get("nv_id", ""),
                "store_id": caller.get("store_id", "quan_01"),
                "deadline": deadline.isoformat(),
                "code_verifier": code_verifier or "",
                # Origin chỉ được lưu khi nằm trong danh sách cho phép (CORS);
                # origin lạ giữ chuỗi rỗng ⇒ callback dùng đường dẫn tương đối.
                "web_base": resolve_web_base(origin),
            },
        },
        {},
    )


def _consume_oauth_state(state: str, expected_nv: str | None) -> dict[str, str]:
    """Xác minh `state` chưa dùng, chưa hết hạn; trả về dữ liệu đã gắn vào nó.

    Trả `{nv_id, store_id, code_verifier, web_base}`. `expected_nv=None` dùng
    cho luồng trình duyệt (Google redirect về bằng GET, KHÔNG kèm header
    `Authorization`) — khi đó chính `state` là bằng chứng phiên, nên không cần
    so với người gọi. Khi có header thì so chặt.
    """
    from datetime import UTC, datetime

    if not state:
        raise HTTPException(status_code=400, detail="thieu_state_oauth")

    found: dict[str, Any] = {}

    def _pop(bag: dict[str, Any]) -> dict[str, Any]:
        hit = bag.get(state)
        if isinstance(hit, dict):
            found.update(hit)
        return {k: v for k, v in bag.items() if k != state}

    kv_mutate("gmail_oauth_states", _pop, {})

    if not found:
        raise HTTPException(status_code=400, detail="state_oauth_khong_hop_le")
    if str(found.get("deadline", "")) < datetime.now(UTC).isoformat():
        raise HTTPException(status_code=400, detail="state_oauth_het_han")
    owner = str(found.get("nv_id", ""))
    if expected_nv is not None and owner != expected_nv:
        raise HTTPException(status_code=400, detail="state_oauth_sai_nguoi")
    return {
        "nv_id": owner,
        "store_id": str(found.get("store_id", "quan_01")),
        "code_verifier": str(found.get("code_verifier", "")),
        "web_base": str(found.get("web_base", "")),
    }


def _oauth_redirect(
    *,
    web_base: str = "",
    account: str | None = None,
    email: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Chuyển hướng trình duyệt về `/gmail` kèm kết quả trên query string.

    `web_base` là origin của web PWA (vd `http://localhost:3000`). Bỏ trống ⇒
    dùng đường dẫn tương đối `/gmail`, đúng cho production sau reverse-proxy
    (web và API cùng origin). Khi chạy local, API ở cổng 8000 còn web ở 3000 —
    nếu trả về tương đối thì trình duyệt nhảy vào API và nhận 404.
    """
    params: dict[str, str] = {}
    if account:
        params["account_id"] = account
    if email:
        params["email"] = email
    if error:
        params["error"] = error
    target = "/gmail"
    if params:
        target = f"{target}?{urlencode(params)}"
    return RedirectResponse(url=resolve_web_base(web_base) + target, status_code=302)


def _caller_for_nv(nv_id: str) -> dict[str, str] | None:
    """Dựng `caller` tối thiểu cho luồng trình duyệt (không có phiên HTTP)."""
    return {"nv_id": nv_id, "store_id": "quan_01", "role": "", "username": ""} if nv_id else None


async def _complete_oauth(
    code: str, *, caller: dict[str, str], code_verifier: str | None = None
) -> dict[str, Any]:
    """Đổi mã uỷ quyền → lưu token → tạo/cập nhật tài khoản Gmail.

    Dùng chung cho cả POST (JSON API) và GET (trình duyệt do Google điều hướng).
    `code_verifier` phải là giá trị đã dùng khi dựng authorization URL (PKCE).
    """
    try:
        tokens = await exchange_code_for_tokens(code, code_verifier=code_verifier or None)
    except Exception as exc:  # noqa: BLE001 — lỗi mạng/Google, quy về 400
        raise HTTPException(status_code=400, detail="doi_ma_oauth_that_bai") from exc

    store_id = caller.get("store_id", "quan_01")
    nv_id = caller.get("nv_id", "")
    access_token = str(tokens["access_token"])
    refresh_token = tokens.get("refresh_token")
    expires_at = str(tokens.get("expires_at", ""))
    scope = str(tokens.get("scope", ""))
    token_type = str(tokens.get("token_type", "Bearer"))

    # Lấy địa chỉ email thật từ profile Gmail.
    try:
        service = GmailService(access_token, refresh_token)
        profile = service.get_profile()
    except Exception as exc:  # noqa: BLE001 — token vừa đổi mà gọi lỗi ⇒ từ chối
        raise HTTPException(status_code=400, detail="khong_doc_duoc_ho_so_gmail") from exc

    email = str(profile.get("emailAddress", ""))
    if not email:
        raise HTTPException(status_code=400, detail="khong_lay_duoc_email_gmail")

    existing = gmail_account_list(store_id, nv_id)
    account = next((a for a in existing if a["email"].lower() == email.lower()), None)

    if account:
        account_id = str(account["id"])
        gmail_account_update(account_id, is_active=True)
        # Google KHÔNG gửi lại `refresh_token` khi người dùng đã cấp quyền trước đó
        # (chỉ trả ở lần consent ĐẦU TIÊN, hoặc khi có `prompt=consent` mà vẫn
        # cấp mới). Ghi đè bằng None sẽ XOÁ refresh token cũ ⇒ tài khoản mất khả
        # năng tự làm mới access token, hỏng sau ~1 giờ. Giữ lại bản cũ.
        if not refresh_token:
            previous = gmail_token_get(account_id) or {}
            refresh_token = previous.get("refresh_token")
    else:
        created = gmail_account_create(
            store_id=store_id,
            nv_id=nv_id,
            email=email,
            display_name=str(profile.get("name", "")),
            is_primary=len(existing) == 0,
        )
        account_id = str(created["id"])

    gmail_token_save(
        account_id,
        access_token=access_token,
        refresh_token=str(refresh_token) if refresh_token else None,
        expires_at=expires_at,
        scope=scope,
        token_type=token_type,
    )

    return {"ok": True, "account_id": account_id, "email": email, "message": "Đã kết nối Gmail"}


@router.get("/api/v1/gmail/oauth/callback")
async def gmail_oauth_callback_get(
    state: Annotated[str | None, Query()] = None,
    code: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
    origin: Annotated[str | None, Header()] = None,
) -> RedirectResponse:
    """Đích `redirect_uri` mà GOOGLE điều hướng trình duyệt tới (GET, không header).

    Trước đây chỉ có POST + bắt buộc header `Authorization`, nên trình duyệt
    nhận 405 và người dùng không bao giờ kết nối được Gmail. Ở đây `state`
    (đã lưu kèm nv_id, dùng một lần) là bằng chứng phiên.

    Mọi nhánh lỗi đều CHUYỂN HƯỚNG về `/gmail?error=...` kèm mã tiếng Việt, không
    bao giờ trả 4xx/5xx thô cho trình duyệt: người dùng đang ở giữa luồng Google
    nên trang lỗi JSON chỉ làm họ mất phương hướng.
    """
    # State giải mã trước để biết origin/cổng của web cần quay về, kể cả khi
    # Google trả về lỗi (khi đó ta VẪN phải tiêu thụ state — dùng một lần).
    web_base = resolve_web_base(origin)
    try:
        owner = _consume_oauth_state(state or "", None)
    except HTTPException as exc:
        return _oauth_redirect(web_base=web_base, error=str(exc.detail))

    web_base = owner.get("web_base") or web_base

    # Người dùng bấm "Huỷ" ở màn hình đồng ý ⇒ Google trả `error=access_denied`
    # và KHÔNG kèm `code`. Đây là hành vi bình thường, không phải sự cố.
    if error:
        return _oauth_redirect(web_base=web_base, error=f"google_tu_choi:{error}")
    if not code:
        return _oauth_redirect(web_base=web_base, error="thieu_ma_oauth")

    try:
        caller = _caller_for_nv(owner["nv_id"])
        if caller is None:
            return _oauth_redirect(web_base=web_base, error="khong_tim_thay_tai_khoan")
        caller = {**caller, "store_id": owner["store_id"]}
        result = await _complete_oauth(
            code, caller=caller, code_verifier=owner.get("code_verifier") or None
        )
    except HTTPException as exc:
        return _oauth_redirect(web_base=web_base, error=str(exc.detail))

    return _oauth_redirect(
        web_base=web_base,
        account=str(result.get("account_id", "")),
        email=str(result.get("email", "")),
    )


@router.post("/api/v1/gmail/oauth/callback")
async def gmail_oauth_callback(
    body: GmailOAuthCallbackRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Callback dạng JSON API (frontend gọi trực tiếp). Yêu cầu token phiên."""
    caller = _owner(authorization)
    owner = _consume_oauth_state(body.state, caller.get("nv_id"))
    return await _complete_oauth(
        body.code, caller=caller, code_verifier=owner.get("code_verifier") or None
    )


@router.post("/api/v1/gmail/oauth/revoke")
async def gmail_oauth_revoke(
    account_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Thu hồi token Google và xoá token lưu local."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)

    tokens = gmail_token_get(account_id)
    if tokens and tokens.get("access_token"):
        try:
            await revoke_token(str(tokens["access_token"]))
        except Exception:  # noqa: BLE001 — thu hồi phía Google là best-effort
            pass

    gmail_token_delete(account_id)
    return {"ok": True, "message": "Đã thu hồi quyền truy cập Gmail"}


# ── Tài khoản ─────────────────────────────────────────────────────────────


@router.post("/api/v1/gmail/accounts")
async def create_gmail_account(
    body: GmailAccountCreateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Thêm tài khoản Gmail thủ công (chưa có token — dùng khi OAuth chưa xong)."""
    caller = _owner(authorization)
    store_id = caller.get("store_id", "quan_01")
    nv_id = caller.get("nv_id", "")

    existing = gmail_account_list(store_id, nv_id)
    if any(a["email"].lower() == body.email.lower() for a in existing):
        raise HTTPException(status_code=409, detail="email_da_ton_tai")

    return gmail_account_create(
        store_id=store_id,
        nv_id=nv_id,
        email=body.email,
        display_name=body.display_name,
        is_primary=body.is_primary and not existing,
    )


@router.get("/api/v1/gmail/accounts")
async def list_gmail_accounts(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Liệt kê tài khoản Gmail do CHÍNH chủ quán đang đăng nhập thêm.

    Mỗi tài khoản kèm trạng thái đồng bộ để tab Tài khoản hiện số chưa đọc
    mà không cần mở từng hộp thư. Chủ quán khác nhau không thấy mail nhau.
    """
    caller = _owner(authorization)
    store_id = caller.get("store_id", "quan_01")

    accounts = gmail_account_list(store_id, caller.get("nv_id", ""))

    # Một truy vấn cho TẤT CẢ tài khoản thay vì 2 query mỗi tài khoản: danh sách
    # dài sẽ thành N+1 và làm chậm trang. Trạng thái này KHÔNG giải mã token —
    # token hỏng không được làm sập danh sách, nếu không người dùng không mở
    # được /gmail để kết nối lại.
    ids = [str(a["id"]) for a in accounts]
    statuses = gmail_token_status_bulk(ids)
    for acc in accounts:
        acc_id = str(acc["id"])
        status = statuses.get(acc_id)
        acc["has_tokens"] = status is not None
        acc["token_expires_at"] = status.get("expires_at") if status else None
        acc["token_broken"] = (
            gmail_token_health(acc_id) == "broken" if status is not None else False
        )
        # Hộp thư của TÀI KHOẢN NÀO hiện số của tài khoản đó — không lẫn nhau.
        # Chủ quán tự thêm vài mail nên lặp vài query ở đây là chấp nhận được.
        acc["sync_state"] = gmail_sync_state_get(acc_id)

    return {"accounts": accounts}


@router.get("/api/v1/gmail/accounts/{account_id}")
async def get_gmail_account(
    account_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chi tiết tài khoản kèm trạng thái token và đồng bộ."""
    caller = _owner(authorization)
    account = _owned_account(account_id, caller)

    status = gmail_token_status(account_id)
    account["has_tokens"] = status is not None
    account["token_expires_at"] = status.get("expires_at") if status else None
    account["token_broken"] = gmail_token_health(account_id) == "broken"
    account["sync_state"] = gmail_sync_state_get(account_id)
    return account


@router.patch("/api/v1/gmail/accounts/{account_id}")
async def update_gmail_account(
    account_id: str,
    body: GmailAccountUpdateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đổi tên hiển thị / tài khoản chính / trạng thái hoạt động."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)

    updated = gmail_account_update(
        account_id,
        display_name=body.display_name,
        is_primary=body.is_primary,
        is_active=body.is_active,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="khong_tim_thay_tai_khoan")
    return updated


@router.delete("/api/v1/gmail/accounts/{account_id}")
async def delete_gmail_account(
    account_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xoá tài khoản (cascade token, email, nhãn, bộ lọc)."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)

    tokens = gmail_token_get(account_id)
    if tokens and tokens.get("access_token"):
        try:
            await revoke_token(str(tokens["access_token"]))
        except Exception:  # noqa: BLE001 — thu hồi best-effort trước khi xoá
            pass

    if not gmail_account_delete(account_id):
        raise HTTPException(status_code=404, detail="khong_tim_thay_tai_khoan")
    return {"ok": True, "message": "Đã xoá tài khoản Gmail"}


# ── Hộp thư ───────────────────────────────────────────────────────────────


@router.get("/api/v1/gmail/accounts/{account_id}/messages")
async def list_gmail_messages(
    account_id: str,
    label_ids: Annotated[list[str] | None, Query()] = None,
    query: Annotated[str | None, Query()] = None,
    is_read: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Liệt kê email đã đồng bộ, lọc theo nhãn/từ khoá/trạng thái đọc."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)

    messages = gmail_messages_list(
        account_id,
        label_ids=label_ids,
        query=query,
        is_read=is_read,
        limit=limit,
        offset=offset,
    )
    return {"messages": messages, "limit": limit, "offset": offset}


@router.get("/api/v1/gmail/accounts/{account_id}/messages/{message_id}")
async def get_gmail_message(
    account_id: str,
    message_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chi tiết một email."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)

    message = gmail_message_get(account_id, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="khong_tim_thay_email")
    return message


@router.post("/api/v1/gmail/accounts/{account_id}/messages/{message_id}/read")
async def mark_message_read(
    account_id: str,
    message_id: str,
    is_read: bool = True,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đánh dấu đã đọc / chưa đọc (chỉ local)."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)

    if not gmail_message_mark_read(account_id, message_id, is_read):
        raise HTTPException(status_code=404, detail="khong_tim_thay_email")
    return {"ok": True, "message_id": message_id, "is_read": is_read}


@router.post("/api/v1/gmail/accounts/{account_id}/messages/{message_id}/star")
async def star_message(
    account_id: str,
    message_id: str,
    is_starred: bool = True,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Gắn / bỏ gắn sao (chỉ local)."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)

    if not gmail_message_star(account_id, message_id, is_starred):
        raise HTTPException(status_code=404, detail="khong_tim_thay_email")
    return {"ok": True, "message_id": message_id, "is_starred": is_starred}


# ── Nhãn ──────────────────────────────────────────────────────────────────


@router.get("/api/v1/gmail/accounts/{account_id}/labels")
async def list_gmail_labels(
    account_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Liệt kê nhãn đã đồng bộ."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    return {"labels": gmail_labels_list(account_id)}


def _persist_label(account_id: str, raw: dict[str, Any]) -> None:
    """Ghi nhãn trả về từ Gmail API vào DB local."""
    parsed = GmailService.parse_label(raw, account_id)
    gmail_label_upsert(
        account_id=account_id,
        label_id=parsed.id,
        name=parsed.name,
        label_type=parsed.label_type,
        message_list_visibility=parsed.message_list_visibility,
        label_list_visibility=parsed.label_list_visibility,
        color_background=parsed.color_background,
        color_text=parsed.color_text,
        total_messages=parsed.total_messages,
        unread_messages=parsed.unread_messages,
    )


@router.post("/api/v1/gmail/accounts/{account_id}/labels")
async def create_gmail_label(
    account_id: str,
    body: GmailLabelCreateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tạo nhãn mới trên Gmail rồi ghi lại local."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    service = _service_for(account_id)

    try:
        result = service.create_label(
            name=body.name,
            label_list_visibility=body.label_list_visibility,
            message_list_visibility=body.message_list_visibility,
            color_background=body.color_background,
            color_text=body.color_text,
        )
    except Exception as exc:  # noqa: BLE001 — lỗi Google API ⇒ 400 cho người dùng
        raise HTTPException(status_code=400, detail="tao_nhan_that_bai") from exc

    _persist_label(account_id, result)
    return result


@router.patch("/api/v1/gmail/accounts/{account_id}/labels/{label_id}")
async def update_gmail_label(
    account_id: str,
    label_id: str,
    body: GmailLabelUpdateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đổi tên / màu / hiển thị của nhãn."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    service = _service_for(account_id)

    try:
        result = service.update_label(
            label_id,
            name=body.name,
            label_list_visibility=body.label_list_visibility,
            message_list_visibility=body.message_list_visibility,
            color_background=body.color_background,
            color_text=body.color_text,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="sua_nhan_that_bai") from exc

    _persist_label(account_id, result)
    return result


@router.delete("/api/v1/gmail/accounts/{account_id}/labels/{label_id}")
async def delete_gmail_label(
    account_id: str,
    label_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xoá nhãn trên Gmail rồi xoá local."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    service = _service_for(account_id)

    try:
        service.delete_label(label_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="xoa_nhan_that_bai") from exc

    gmail_label_delete(account_id, label_id)
    return {"ok": True, "label_id": label_id}


# ── Bộ lọc ────────────────────────────────────────────────────────────────


@router.get("/api/v1/gmail/accounts/{account_id}/filters")
async def list_gmail_filters(
    account_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Liệt kê bộ lọc đã đồng bộ."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    return {"filters": gmail_filters_list(account_id)}


@router.post("/api/v1/gmail/accounts/{account_id}/filters")
async def create_gmail_filter(
    account_id: str,
    body: GmailFilterCreateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tạo bộ lọc trên Gmail rồi ghi lại local."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    service = _service_for(account_id)

    try:
        result = service.create_filter(criteria=body.criteria, action=body.action)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="tao_bo_loc_that_bai") from exc

    gmail_filter_upsert(
        account_id=account_id,
        filter_id=str(result["id"]),
        criteria=body.criteria,
        action=body.action,
    )
    return result


@router.delete("/api/v1/gmail/accounts/{account_id}/filters/{filter_id}")
async def delete_gmail_filter(
    account_id: str,
    filter_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xoá bộ lọc trên Gmail rồi xoá local."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    service = _service_for(account_id)

    try:
        service.delete_filter(filter_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="xoa_bo_loc_that_bai") from exc

    gmail_filter_delete(account_id, filter_id)
    return {"ok": True, "filter_id": filter_id}


# ── Đồng bộ ───────────────────────────────────────────────────────────────


@router.post("/api/v1/gmail/sync")
async def sync_gmail(
    body: GmailSyncRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đồng bộ một tài khoản hoặc mọi tài khoản của CHÍNH chủ quán gọi."""
    caller = _owner(authorization)
    store_id = caller.get("store_id", "quan_01")

    try:
        if body.account_id:
            _owned_account(body.account_id, caller)
            return await sync_account(body.account_id, full_sync=body.full_sync)
        return {
            "results": await sync_all_accounts(
                store_id, nv_id=caller.get("nv_id", ""), full_sync=body.full_sync
            )
        }
    except GmailSyncError as exc:
        raise HTTPException(status_code=400, detail="dong_bo_that_bai") from exc


@router.get("/api/v1/gmail/accounts/{account_id}/sync-state")
async def get_sync_state(
    account_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Trạng thái đồng bộ gần nhất."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    return gmail_sync_state_get(account_id) or {}


# ── Gửi qua Gmail API ─────────────────────────────────────────────────────


@router.post("/api/v1/gmail/accounts/{account_id}/send")
async def send_gmail_message(
    account_id: str,
    body: GmailSendMessageRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Gửi email qua Gmail API. Chỉ chủ quán, từ tài khoản do chính mình thêm."""
    caller = _owner(authorization)
    _owned_account(account_id, caller)
    service = _service_for(account_id)

    try:
        result = service.send_message(
            to=body.to,
            subject=body.subject,
            body_text=body.body_text,
            body_html=body.body_html,
            cc=body.cc,
            bcc=body.bcc,
            thread_id=body.thread_id,
            in_reply_to=body.in_reply_to,
            references=body.references,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="gui_email_that_bai") from exc

    return {"ok": True, "message_id": result.get("id"), "thread_id": result.get("threadId")}
