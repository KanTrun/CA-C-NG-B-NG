"""Quầy nội bộ: menu, đơn pha chế và số tiêu thụ ước lượng.

Không có khách hàng hay cổng thanh toán trong router này.  Mọi đơn đều do
người đang làm ca ghi tại quầy và luôn có nhãn ``quay_noi_bo``.
"""

from __future__ import annotations

import re
import uuid

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from ca_agents import (
    MenuImageResult,
    MenuStyle,
    default_styles,
    edit_image,
    find_style,
    generate_background_redesign,
    generate_menu_prompt,
    image_edit_available,
    normalize_slug,
    parse_style,
    style_options,
)
from ca_agents.image_gen import generate_image
from ca_contracts import DongDon, DonQuay, MonNuoc
from fastapi import APIRouter, File, Header, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ca_api.interfaces.http.sprint3 import _require_chu_quan, _require_manager, _require_role
from ca_api.persist import (
    NangVaiLoi,
    audit_add,
    da_diem_danh,
    db_path,
    don_chuyen_trang_thai,
    don_get,
    don_insert,
    don_list,
    don_update,
    ha_vai,
    kv_get,
    kv_set,
    list_users,
    menu_get,
    menu_list,
    menu_set_hinh,
    menu_upsert,
    set_role,
    tieu_thu_append,
    user_deactivate,
)
from ca_api.persist import (
    session as auth_session,
)
from ca_api.services.menu_image import bytes_anh

router = APIRouter()

_MON_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_STATUS_NEXT = {
    "cho_pha": {"dang_pha", "huy"},
    "dang_pha": {"xong", "huy"},
    "xong": set(),
    "huy": set(),
}
_DON_VI_BOM = {
    "cafe_g": "g",
    "sua_ml": "ml",
    "dao_lat": "lát",
    "ly": "ly",
}

# Thứ tự nhóm chuẩn của quán, dùng cho menu quầy. Món chưa khai `nhom` được suy
# từ BOM để menu cũ vẫn phân mục được thay vì dồn hết vào "khác".
_NHOM_HOP_LE = ("ca_phe", "tra", "sinh_to", "banh", "nuoc_dong_chai", "nguyen_lieu")


class MonBody(BaseModel):
    ten: str = Field(min_length=1, max_length=120)
    gia: int = Field(ge=0, le=10_000_000)
    an: bool = False
    hinh_url: str = Field(default="", max_length=500)
    nhom: str = Field(default="", max_length=40)
    # `bom` (định mức nguyên liệu) là tuỳ chọn: client cũ chỉ sửa giá/tên không
    # gửi lên. Phân biệt "không gửi" với "gửi rỗng" để không xoá mất định mức.
    bom: dict[str, float] | None = None


class DongDatBody(BaseModel):
    mon_id: str = Field(min_length=2, max_length=64)
    so_luong: int = Field(ge=1, le=99)


class TaoDonBody(BaseModel):
    dong: list[DongDatBody] = Field(min_length=1, max_length=30)
    thanh_toan: Literal["tien_mat", "da_ck", "chua_thu"] = "chua_thu"


class ChuyenDonBody(BaseModel):
    trang_thai: Literal["dang_pha", "xong", "huy"]
    ly_do_huy: str = Field(default="", max_length=300)


class ChinhDonBody(BaseModel):
    dong: list[DongDatBody] = Field(min_length=1, max_length=30)
    thanh_toan: Literal["tien_mat", "da_ck", "chua_thu"]


class NangVaiBody(BaseModel):
    role: Literal["quan_ly"] = "quan_ly"


def _menu_image_dir() -> Path:
    base = db_path().parent / "menu_images"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _detect_image_suffix(raw: bytes) -> str | None:
    """Nhận diện định dạng ảnh từ magic bytes — không tin đuôi file client gửi.

    Trả đuôi file (`.jpg`/`.png`/`.gif`/`.webp`) hoặc None nếu không phải ảnh.
    """
    if raw[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    return None


def _detect_image_mime(raw: bytes) -> str:
    """MIME của ảnh từ magic bytes — mặc định jpeg khi không nhận diện được.

    Cần khi gửi ảnh gốc lên provider image-to-image: khai sai MIME làm provider
    từ chối ảnh dù nội dung hợp lệ.
    """
    suffix = _detect_image_suffix(raw)
    return {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix or "", "image/jpeg")


def _menu_image_path(mon_id: str) -> Path | None:
    mid = mon_id.strip().lower()
    if not _MON_ID.fullmatch(mid):
        return None
    base = _menu_image_dir().resolve()
    for ext in (".webp", ".jpg", ".jpeg", ".png", ".gif"):
        p = (base / f"{mid}{ext}").resolve()
        if p.is_file() and p.is_relative_to(base):
            return p
    return None


def _session(authorization: str | None) -> dict[str, str]:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    return s


def _require_dang_ca(authorization: str | None) -> dict[str, str]:
    s = _session(authorization)
    if not da_diem_danh(s["nv_id"]):
        raise HTTPException(status_code=403, detail="chua_diem_danh")
    return s


def _audit(ai: str, hanh: str, payload: dict[str, Any]) -> None:
    audit_add(datetime.now(UTC).isoformat(), ai, hanh, payload)


def _dong_theo_menu(rows: list[DongDatBody]) -> list[dict[str, Any]]:
    dong: list[dict[str, Any]] = []
    for row in rows:
        mon = menu_get(row.mon_id)
        if not mon or mon["an"]:
            raise HTTPException(status_code=404, detail="mon_khong_ban")
        dong.append(
            DongDon(
                mon_id=mon["id"], ten=mon["ten"], so_luong=row.so_luong, gia=mon["gia"]
            ).model_dump()
        )
    return dong


def _can_cham_don(don: dict[str, Any], authorization: str | None) -> dict[str, str]:
    s = _require_dang_ca(authorization)
    if s["role"] == "nhan_vien" and don["nv_id"] != s["nv_id"]:
        raise HTTPException(status_code=403, detail="khong_phai_don_ca_minh")
    return s


def _ghi_tieu_thu_uoc_luong(don: dict[str, Any], ai: str) -> None:
    """Ghi một dòng cho từng thành phần BOM, chỉ tại chuyển trạng thái sang xong."""
    for dong in don["dong"]:
        mon = menu_get(str(dong["mon_id"]))
        if not mon:
            continue
        for hang, mot_don_vi in mon["bom"].items():
            try:
                so_luong = float(mot_don_vi) * int(dong["so_luong"])
            except (TypeError, ValueError):
                continue
            if so_luong <= 0:
                continue
            tieu_thu_append(
                {
                    "id": f"ttq_{uuid.uuid4().hex[:10]}",
                    "hang": hang,
                    "so_luong": so_luong,
                    "don_vi": _DON_VI_BOM.get(hang, "đơn vị"),
                    "duoi_nguong": False,
                    "ai": ai,
                    "luc": datetime.now(UTC).isoformat(),
                    "nguon": "uoc_luong_tu_quay",
                    "don_quay_id": don["id"],
                    "ghi": "Ước lượng từ quầy nội bộ, không phải số Grab.",
                }
            )


def _don_cho_role(
    authorization: str | None, *, trang_thai: str | None = None
) -> list[dict[str, Any]]:
    s = _require_dang_ca(authorization)
    items = don_list(trang_thai=trang_thai)
    if s["role"] == "nhan_vien":
        return [x for x in items if x["nv_id"] == s["nv_id"]]
    return items


@router.get("/api/v1/menu")
def menu(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Menu quầy cho mọi vai đã đăng nhập (QA 2026-09-30 N3: chủ ý, không phải hở).

    Nhân viên cần ĐỌC menu để bán ở `/quay` (`quay/page.tsx` gọi endpoint này
    không phân biệt vai). Model `MonNuoc` chỉ có id/tên/giá/ẩn/ảnh/nhóm/BOM —
    không có giá vốn hay dữ liệu nhạy cảm — nên cho đọc là an toàn.
    Phân biệt với trang quản trị web `/menu` (OWNER_ONLY ở `session.ts`) và
    `PUT /api/v1/menu/{mon_id}` + `GET /api/v1/menu/quan-tri` (đòi
    `_require_chu_quan`): đọc thì mở, sửa thì khoá.
    """
    _require_role(authorization)
    items = []
    for mon in menu_list():
        nhom = str(mon.get("nhom") or "")
        items.append({**mon, "nhom": nhom or _nhom_suy_tu_bom(mon.get("bom"))})
    return {
        "items": items,
        "nhom": list(_NHOM_HOP_LE),
        "nguon": "quan",
        "ghi": "Menu quầy nội bộ, không phải storefront khách.",
    }


@router.get("/api/v1/menu/quan-tri")
def menu_quan_tri(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_chu_quan(authorization)
    return {"items": menu_list(gom_an=True), "nguon": "quan"}


@router.put("/api/v1/menu/{mon_id}")
def menu_luu(
    mon_id: str,
    body: MonBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_chu_quan(authorization)
    mid = mon_id.strip().lower()
    if not _MON_ID.fullmatch(mid):
        raise HTTPException(status_code=422, detail="ma_mon_khong_hop_le")
    cu = menu_get(mid)
    du_lieu = body.model_dump()
    # PUT không gửi `bom`/`nhom`/`hinh_url` thì GIỮ giá trị đang có, không xoá.
    # Bug QA đợt 5: quản lý chỉ sửa giá nhưng `bom` về `{}` → mất định mức
    # nguyên liệu, tiêu thụ BOM ngừng ghi cho món đó. Chỉ khi món CHƯA tồn tại
    # mới thực sự rỗng.
    if du_lieu.get("bom") is None:
        du_lieu["bom"] = (cu or {}).get("bom") or {}
    if not str(du_lieu.get("nhom") or "").strip():
        du_lieu["nhom"] = str((cu or {}).get("nhom") or "")
    if not str(du_lieu.get("hinh_url") or "").strip():
        du_lieu["hinh_url"] = str((cu or {}).get("hinh_url") or "")
    try:
        mon = MonNuoc(id=mid, **du_lieu).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="mon_khong_hop_le") from exc
    if not mon.get("nhom"):
        mon["nhom"] = _nhom_suy_tu_bom(mon.get("bom"))
    out = menu_upsert(mon)
    _audit(role, "menu_luu", {"id": mid, "an": out["an"], "gia": out["gia"]})
    return {**out, "nguon": "quan"}


@router.get("/api/v1/nguoi")
def nguoi_list(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_chu_quan(authorization)
    return {"items": list_users(), "nguon": "quan"}


@router.post("/api/v1/nguoi/{username}/nang-vai")
def nguoi_nang_vai(
    username: str,
    body: NangVaiBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_chu_quan(authorization)
    try:
        out = set_role(username, body.role)
    except NangVaiLoi as exc:
        raise HTTPException(status_code=409, detail=exc.ma) from exc
    _audit(role, "role.promote", {"entity_type": "user", "entity_id": out["username"], "username": out["username"], "role": out["role"]})
    return {**out, "nguon": "quan"}


@router.post("/api/v1/nguoi/{username}/ha-vai")
def nguoi_ha_vai(
    username: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_chu_quan(authorization)
    try:
        out = ha_vai(username)
    except NangVaiLoi as exc:
        raise HTTPException(status_code=409, detail=exc.ma) from exc
    _audit(role, "role.demote", {"entity_type": "user", "entity_id": out["username"], "username": out["username"], "role": out["role"]})
    return {**out, "nguon": "quan"}


@router.post("/api/v1/nguoi/{username}/deactivate")
def nguoi_deactivate(
    username: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Offboarding: vô hiệu hóa tài khoản — chỉ chủ quán, không tự sa thải chính mình."""
    role = _require_chu_quan(authorization)
    s = _session(authorization)
    if s["username"].strip().lower() == username.strip().lower():
        raise HTTPException(status_code=409, detail="khong_the_vo_hieu_hoa_chinh_minh")
    users = {str(u.get("username") or "").strip().lower(): u for u in list_users()}
    target = users.get(username.strip().lower())
    if not target:
        raise HTTPException(status_code=404, detail="khong_tim_thay_nguoi")
    if not user_deactivate(str(target.get("nv_id") or "")):
        raise HTTPException(status_code=409, detail="vo_hieu_hoa_that_bai")
    _audit(role, "user.deactivate", {"entity_type": "user", "entity_id": target.get("username"), "username": target.get("username"), "nv_id": target.get("nv_id")})
    return {"ok": True, "username": target.get("username"), "status": "inactive", "nguon": "quan"}


@router.get("/api/v1/menu/{mon_id}/anh")
def menu_anh_get(mon_id: str) -> Response:
    """Ảnh món — public read để `<img>` không cần Bearer.

    Ba bậc, theo thứ tự ưu tiên:

    1. Ảnh quán tự tải lên (mọi định dạng đã nhận) — luôn thắng ảnh tự sinh.
    2. Ảnh tự sinh `menu_images/<id>.png` (do `scripts/sinh_anh_mon.py` ghi).
    3. Sinh **tại chỗ** bằng Pillow, không gọi mạng.

    Bậc 3 là chỗ chốt ràng buộc demo offline (§14.9): máy chưa chạy script sinh
    ảnh vẫn phải trả ảnh thật, không để lưới menu rơi về chữ cái đầu. Vì hàm vẽ
    dùng chung `ca_api.services.menu_image`, ảnh ở bậc 2 và bậc 3 giống hệt nhau.
    """
    path = _menu_image_path(mon_id)
    if path:
        return FileResponse(path)

    mid = mon_id.strip().lower()
    if not _MON_ID.fullmatch(mid):
        raise HTTPException(status_code=404, detail="khong_co_anh")
    mon = menu_get(mid)
    if not mon:
        raise HTTPException(status_code=404, detail="khong_co_anh")

    cay = {
        "id": mid,
        "ten": mon.get("ten") or mid,
        "gia": mon.get("gia"),
        "nhom": _nhom_suy_tu_bom(mon.get("bom")),
    }
    return Response(
        content=bytes_anh(cay),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _nhom_suy_tu_bom(bom: Any) -> str:
    """Suy nhóm sản phẩm từ công thức để chọn hình đại diện.

    Món không khai nhóm (đường PUT chỉ nhận tên/giá/bom) nên phải suy: có cà phê
    là nhóm cà phê, có trà/matcha là nhóm trà, chỉ có bánh/kem là nhóm bánh, còn
    lại mặc định nhóm ly nước. Chỉ ảnh hưởng hình vẽ, không tham gia phép tính.
    """
    khoa = {str(k) for k in (bom or {}) if isinstance(bom, dict)}
    if khoa & {"ca_phe_hat", "ca_phe", "cafe_g"}:
        return "ca_phe"
    if khoa & {"tra", "matcha", "tra_g"}:
        return "tra"
    if khoa & {"banh", "kem"} and not khoa & {"ly"}:
        return "banh"
    if "nuoc_dong_chai" in khoa:
        return "nuoc_dong_chai"
    return "tra"


@router.post("/api/v1/menu/{mon_id}/anh")
async def menu_anh_upload(
    mon_id: str,
    file: UploadFile = File(...),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_chu_quan(authorization)
    mid = mon_id.strip().lower()
    if not _MON_ID.fullmatch(mid):
        raise HTTPException(status_code=422, detail="ma_mon_khong_hop_le")
    if not menu_get(mid):
        raise HTTPException(status_code=404, detail="mon_khong_co")
    raw = await file.read()
    if len(raw) > 4_000_000:
        raise HTTPException(status_code=413, detail="anh_qua_lon")
    suffix = _detect_image_suffix(raw)
    if suffix is None:
        raise HTTPException(status_code=415, detail="khong_phai_anh_hop_le")
    dest = _menu_image_dir() / f"{mid}{suffix}"
    for old in _menu_image_dir().glob(f"{mid}.*"):
        if old != dest:
            old.unlink(missing_ok=True)
    dest.write_bytes(raw)
    url = f"/api/v1/menu/{mid}/anh"
    out = menu_set_hinh(mid, url)
    return {**(out or {}), "hinh_url": url, "nguon": "quan"}


# Khoá lưu danh sách phong cách thiết kế của quán (kv store, dùng chung mọi món).
_STYLE_KV = "menu_anh_phong_cach"
# Khoá lưu phong cách đang chọn làm mặc định cho ảnh mới.
_STYLE_DEFAULT_KV = "menu_anh_phong_cach_mac_dinh"
# Giới hạn số phong cách để dropdown không phình vô hạn.
_MAX_STYLES = 30


def _all_styles() -> list[MenuStyle]:
    """Phong cách của quán: bản lưu trong kv, hoặc preset mặc định nếu chưa có.

    Preset không được ghi vào store — chỉ hiện ra như lựa chọn ban đầu. Khi chủ
    quán sửa/lưu, danh sách đã sửa mới được ghi.
    """
    raw = kv_get(_STYLE_KV, None)
    if not isinstance(raw, list):
        return default_styles()
    out: list[MenuStyle] = []
    for item in raw:
        parsed = parse_style(item)
        if parsed is not None:
            out.append(parsed)
    return out or default_styles()


def _style_default_slug() -> str:
    raw = kv_get(_STYLE_DEFAULT_KV, "")
    return str(raw) if isinstance(raw, str) else ""


def _resolve_style(slug: str | None) -> MenuStyle | None:
    """Tìm phong cách theo slug; None (→ prompt tự động) nếu slug trống.

    Slug không tồn tại là LỖI 422 ở tầng endpoint, không âm thầm dùng mặc định —
    nếu không, người dùng chọn "moody" mà nhận ảnh phong cách khác.
    """
    if not slug or not slug.strip():
        return None
    return find_style(_all_styles(), slug)


class MenuStyleBody(BaseModel):
    """Body lưu một phong cách thiết kế.

    Các trường scene/lighting/palette/lens phải khớp bảng hợp lệ ở
    ``ca_agents.menu_style`` — kiểm tra và trả 422 nếu không.
    """

    slug: str = Field(default="", max_length=48)
    ten: str = Field(min_length=1, max_length=60)
    mo_ta: str = Field(default="", max_length=200)
    scene: str = Field(min_length=1, max_length=40)
    lighting: str = Field(min_length=1, max_length=40)
    palette: str = Field(min_length=1, max_length=40)
    lens: str = Field(min_length=1, max_length=40)


class MenuImagePromptBody(BaseModel):
    """Body cho dựng prompt sinh ảnh từ tên món + phong cách.

    Không cần ảnh tải lên: prompt được lắp tất định từ dữ liệu menu
    (:func:`ca_agents.menu_prompt.build_menu_prompt`), không gọi LLM.
    """
    mo_ta: str = Field(default="", max_length=300)
    aspect_ratio: Literal["1:1", "4:5", "9:16", "16:9"] = "1:1"
    style_slug: str = Field(default="", max_length=48)


class MenuImageGenerateBody(BaseModel):
    """Body cho sinh ảnh thật từ prompt, tuỳ chọn kèm ẢNH THẬT người dùng tải lên.

    ``mode``:
      - ``"from_prompt"`` (mặc định): AI vẽ ảnh mới hoàn toàn từ ``prompt_en``.
      - ``"edit_photo"``: AI **sửa ảnh thật** trong ``original_base64`` theo
        ``prompt_en`` (image-to-image). Ảnh gốc là nguồn, không chỉ tham khảo —
        dùng khi quán đã chụp ly nước và muốn AI dàn dựng lại thành ảnh quảng cáo.
      - ``"keep_drink"``: tách ly nước (100% pixel gốc) rồi AI vẽ nền mới và ghép
        lại bằng Pillow. Không cần provider image-to-image.

    ``prompt_en`` trống thì server tự dựng từ tên món + ``style_slug``.
    """
    prompt_en: str = Field(default="", max_length=2000)
    aspect_ratio: Literal["1:1", "4:5", "9:16", "16:9"] = "1:1"
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    save_as_menu_image: bool = False
    style_slug: str = Field(default="", max_length=48)
    mode: Literal["from_prompt", "edit_photo", "keep_drink"] = "from_prompt"
    original_base64: str | None = Field(default=None, max_length=8_000_000)


def _menu_image_result_to_response(result: MenuImageResult, mon_id: str) -> dict[str, Any]:
    """Chuyển MenuImageResult thành response dict."""
    base: dict[str, Any] = {
        "ok": result.ok,
        "provider": result.provider,
        "mon_id": mon_id,
    }
    if not result.ok:
        base["error"] = result.error
        return base
    base["prompt_en"] = result.prompt_en
    base["prompt_vi"] = result.prompt_vi
    return base


@router.post("/api/v1/menu/{mon_id}/anh/prompt")
def menu_anh_prompt(
    mon_id: str,
    body: MenuImagePromptBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Dựng prompt sinh ảnh cho một món — tất định, không gọi AI.

    Trả về ngay (không mạng, không chờ) nên UI hiện được prompt để người dùng
    đọc/sửa trước khi bấm tạo ảnh.
    """
    _require_chu_quan(authorization)
    mid = mon_id.strip().lower()
    if not _MON_ID.fullmatch(mid):
        raise HTTPException(status_code=422, detail="ma_mon_khong_hop_le")
    mon = menu_get(mid)
    if not mon:
        raise HTTPException(status_code=404, detail="mon_khong_co")

    # Kiểm tra slug TRƯỚC khi dựng prompt: nếu để sau, người dùng gõ sai slug sẽ
    # nhận prompt của phong cách mặc định kèm lỗi 422 — khó hiểu và tốn công.
    style_slug = body.style_slug.strip()
    if style_slug and _resolve_style(style_slug) is None:
        raise HTTPException(status_code=422, detail="phong_cach_khong_ton_tai")

    result = generate_menu_prompt(
        str(mon.get("ten") or ""),
        mo_ta=body.mo_ta,
        style=_resolve_style(style_slug or _style_default_slug()),
        aspect_ratio=body.aspect_ratio,
    )
    return _menu_image_result_to_response(result, mid)


@router.get("/api/v1/menu/anh/kha-dung")
def menu_anh_kha_dung(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Chế độ tạo ảnh nào đang chạy được — để UI khoá lựa chọn không khả thi.

    Trả về ngay (chỉ đọc biến môi trường, không gọi mạng) nên UI gọi được lúc mở
    form. Nhờ vậy người dùng không chọn xong mới biết là thiếu khoá.
    """
    _require_chu_quan(authorization)
    sua_duoc, ly_do = image_edit_available()
    return {
        "che_do": {
            "from_prompt": {"kha_dung": True, "ly_do": ""},
            "keep_drink": {"kha_dung": True, "ly_do": ""},
            "edit_photo": {"kha_dung": sua_duoc, "ly_do": ly_do},
        },
        "nguon": "quan",
    }


@router.get("/api/v1/menu/anh/phong-cach")
def menu_phong_cach_list(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Danh sách phong cách thiết kế + bảng giá trị hợp lệ cho UI.

    Trả kèm ``tuy_chon`` (scene/lighting/palette/lens) để form "tạo phong cách"
    dựng dropdown từ MỘT nguồn sự thật, không hard-code ở web.
    """
    _require_chu_quan(authorization)
    styles = _all_styles()
    return {
        "items": [s.to_dict() for s in styles],
        "mac_dinh": _style_default_slug() or (styles[0].slug if styles else ""),
        "tuy_chon": style_options(),
        "nguon": "quan",
        "ghi": "Phong cách áp cho toàn bộ ảnh quảng cáo của quán.",
    }


@router.put("/api/v1/menu/anh/phong-cach")
def menu_phong_cach_luu(
    body: MenuStyleBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tạo hoặc cập nhật một phong cách thiết kế (upsert theo slug).

    Kiểm tra giá trị theo bảng hợp lệ trước khi lưu: sai một trường → 422 kèm
    danh sách trường sai, KHÔNG âm thầm thay bằng mặc định (nếu thay, ảnh sinh ra
    sẽ khác phong cách người dùng chọn mà không ai biết).
    """
    role = _require_chu_quan(authorization)
    slug = normalize_slug(body.slug or body.ten)
    if slug is None:
        raise HTTPException(status_code=422, detail="ten_phong_cach_khong_hop_le")
    parsed = parse_style({**body.model_dump(), "slug": slug})
    if parsed is None:
        allowed = style_options()
        raise HTTPException(
            status_code=422,
            detail={
                "loi": "gia_tri_khong_hop_le",
                "scene": sorted(allowed["scene"]),
                "lighting": sorted(allowed["lighting"]),
                "palette": sorted(allowed["palette"]),
                "lens": sorted(allowed["lens"]),
            },
        )

    styles = [s for s in _all_styles() if s.slug != parsed.slug]
    styles.append(parsed)
    if len(styles) > _MAX_STYLES:
        raise HTTPException(status_code=409, detail="qua_nhieu_phong_cach")
    kv_set(_STYLE_KV, [s.to_dict() for s in styles])
    if not _style_default_slug():
        kv_set(_STYLE_DEFAULT_KV, parsed.slug)
    _audit(role, "menu.phong_cach.luu", {"slug": parsed.slug, "ten": parsed.ten})
    return {"ok": True, "item": parsed.to_dict(), "nguon": "quan"}


@router.delete("/api/v1/menu/anh/phong-cach/{slug}")
def menu_phong_cach_xoa(
    slug: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xoá một phong cách. Không cho xoá phong cách cuối cùng."""
    role = _require_chu_quan(authorization)
    target = normalize_slug(slug)
    if target is None:
        raise HTTPException(status_code=422, detail="ma_phong_cach_khong_hop_le")
    styles = _all_styles()
    kept = [s for s in styles if s.slug != target]
    if len(kept) == len(styles):
        raise HTTPException(status_code=404, detail="khong_tim_thay_phong_cach")
    if not kept:
        raise HTTPException(status_code=409, detail="can_it_nhat_mot_phong_cach")
    kv_set(_STYLE_KV, [s.to_dict() for s in kept])
    if _style_default_slug() == target:
        kv_set(_STYLE_DEFAULT_KV, kept[0].slug)
    _audit(role, "menu.phong_cach.xoa", {"slug": target})
    return {"ok": True, "con_lai": len(kept), "nguon": "quan"}


@router.post("/api/v1/menu/anh/phong-cach/{slug}/mac-dinh")
def menu_phong_cach_mac_dinh(
    slug: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chọn phong cách mặc định cho ảnh mới — "giữ phong cách này cho các ly khác"."""
    role = _require_chu_quan(authorization)
    target = normalize_slug(slug)
    if target is None:
        raise HTTPException(status_code=422, detail="ma_phong_cach_khong_hop_le")
    if find_style(_all_styles(), target) is None:
        raise HTTPException(status_code=404, detail="khong_tim_thay_phong_cach")
    kv_set(_STYLE_DEFAULT_KV, target)
    _audit(role, "menu.phong_cach.mac_dinh", {"slug": target})
    return {"ok": True, "mac_dinh": target, "nguon": "quan"}


@router.post("/api/v1/menu/{mon_id}/anh/generate")
def menu_anh_generate(
    mon_id: str,
    body: MenuImageGenerateBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Sinh ảnh quảng cáo thật từ prompt.

    Trả về ảnh JPEG/PNG base64. Nếu để trống ``prompt_en``, server tự dựng prompt
    tất định từ tên món + phong cách (không cần gọi AI để viết prompt).
    Nếu ``save_as_menu_image=true`` thì lưu luôn làm ảnh đại diện món.
    """
    import base64

    _require_chu_quan(authorization)
    mid = mon_id.strip().lower()
    if not _MON_ID.fullmatch(mid):
        raise HTTPException(status_code=422, detail="ma_mon_khong_hop_le")
    mon = menu_get(mid)
    if not mon:
        raise HTTPException(status_code=404, detail="mon_khong_co")

    seed = body.seed
    if seed is None:
        seed = uuid.uuid4().int % 2_147_483_647

    # Phong cách: slug gửi lên → phong cách mặc định của quán → None (prompt mặc định).
    style_slug = body.style_slug.strip() or _style_default_slug()
    style = _resolve_style(style_slug)
    if body.style_slug.strip() and style is None:
        raise HTTPException(status_code=422, detail="phong_cach_khong_ton_tai")

    # Prompt: ưu tiên prompt người dùng gửi (đã xem/sửa ở UI); trống thì dựng lại
    # tất định từ tên món + phong cách — UI chỉ cần gửi style_slug là có ảnh.
    full_prompt = body.prompt_en.strip()
    if not full_prompt:
        built = generate_menu_prompt(
            str(mon.get("ten") or ""),
            style=style,
            aspect_ratio=body.aspect_ratio,
        )
        if not built.ok:
            raise HTTPException(status_code=422, detail=built.error)
        full_prompt = built.prompt_en

    # Ảnh gốc: chỉ giải mã khi chế độ cần — tránh tốn CPU và tránh nhận ảnh hỏng
    # ở chế độ không dùng tới.
    original_bytes: bytes | None = None
    if body.mode in {"edit_photo", "keep_drink"}:
        if not body.original_base64:
            raise HTTPException(status_code=422, detail="can_anh_goc")
        b64 = body.original_base64
        if b64.startswith("data:"):
            # Bỏ tiền tố data-URL: "data:image/jpeg;base64,...."
            _, _, b64 = b64.partition(",")
        try:
            original_bytes = base64.b64decode(b64, validate=True)
        except Exception:  # noqa: BLE001 — base64 hỏng → 422 rõ ràng
            raise HTTPException(status_code=422, detail="anh_goc_khong_giai_ma_duoc") from None
        if not original_bytes:
            raise HTTPException(status_code=422, detail="anh_goc_trong")

    if body.mode == "edit_photo":
        # AI sửa chính ảnh thật người dùng gửi (image-to-image).
        assert original_bytes is not None  # đã chặn ở trên
        # Chặn TRƯỚC khi gọi provider: nếu chưa có khoá nào thì mọi lượt gọi đều
        # hỏng, báo ngay kèm cách khắc phục thay vì để người dùng chờ 30 giây rồi
        # nhận lỗi khó hiểu.
        kha_dung, ly_do = image_edit_available()
        if not kha_dung:
            raise HTTPException(status_code=422, detail=ly_do)
        result = edit_image(
            original_bytes,
            full_prompt,
            image_mime=_detect_image_mime(original_bytes),
            timeout_s=180.0,
            image_filename=f"{mid}{_detect_image_suffix(original_bytes) or '.jpg'}",
        )
    elif body.mode == "keep_drink":
        # Giữ 100% pixel ly nước gốc; AI chỉ vẽ nền mới rồi ghép bằng Pillow.
        assert original_bytes is not None  # đã chặn ở trên
        result = generate_background_redesign(
            original_bytes,
            full_prompt,
            original_mime=_detect_image_mime(original_bytes),
            aspect_ratio=body.aspect_ratio,
            seed=seed,
            style=style,
        )
    else:
        result = generate_image(
            full_prompt,
            aspect_ratio=body.aspect_ratio,
            seed=seed,
        )
    if not result.ok:
        return {
            "ok": False,
            "error": result.error,
            "provider": result.provider,
            "model": result.model,
            "mon_id": mid,
            "ghi": result.text or None,
        }

    payload: dict[str, Any] = {
        "ok": True,
        "provider": result.provider,
        "model": result.model,
        "mon_id": mid,
        "seed": seed,
        "aspect_ratio": body.aspect_ratio,
        "mode": body.mode,
        "prompt_en": full_prompt,
        "image_mime": result.image_mime,
        "image_base64": base64.b64encode(result.image_bytes).decode("ascii"),
        "phong_cach": style.slug if style is not None else "",
        "phong_cach_ten": style.ten if style is not None else "",
    }

    if body.save_as_menu_image:
        suffix = _detect_image_suffix(result.image_bytes) or ".jpg"
        dest = _menu_image_dir() / f"{mid}{suffix}"
        for old in _menu_image_dir().glob(f"{mid}.*"):
            if old != dest:
                old.unlink(missing_ok=True)
        dest.write_bytes(result.image_bytes)
        url = f"/api/v1/menu/{mid}/anh"
        menu_set_hinh(mid, url)
        payload["hinh_url"] = url
        payload["saved"] = True

    return payload


@router.get("/api/v1/quay/don")
def quay_don_list(
    trang_thai: Literal["cho_pha", "dang_pha", "xong", "huy"] | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    return {"items": _don_cho_role(authorization, trang_thai=trang_thai), "nguon": "quay_noi_bo"}


@router.post("/api/v1/quay/don", status_code=201)
def quay_don_tao(
    body: TaoDonBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    s = _require_dang_ca(authorization)
    raw = {
        "id": f"dq_{uuid.uuid4().hex[:10]}",
        "nv_id": s["nv_id"],
        "trang_thai": "cho_pha",
        "thanh_toan": body.thanh_toan,
        "dong": _dong_theo_menu(body.dong),
        "luc": datetime.now(UTC).isoformat(),
    }
    don = DonQuay.model_validate(raw).model_dump()
    don_insert(don)
    _audit(s["role"], "quay_tao_don", {"id": don["id"], "nv_id": don["nv_id"]})
    return cast(dict[str, Any], don)


@router.post("/api/v1/quay/don/{don_id}/chuyen")
def quay_don_chuyen(
    don_id: str,
    body: ChuyenDonBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    don = don_get(don_id)
    if not don:
        raise HTTPException(status_code=404, detail="don_khong_tim_thay")
    s = _can_cham_don(don, authorization)
    cur = don["trang_thai"]
    if body.trang_thai not in _STATUS_NEXT.get(cur, set()):
        raise HTTPException(status_code=409, detail=f"chuyen_khong_hop_le:{cur}->{body.trang_thai}")
    if body.trang_thai == "huy" and not body.ly_do_huy.strip():
        raise HTTPException(status_code=422, detail="can_ly_do_huy")

    # Đổi trạng thái bằng COMPARE-AND-SWAP: chỉ thắng khi DB vẫn đang ở `cur`.
    # Hai request đồng thời (double-click, retry mạng) thì đúng MỘT request
    # giành được; request thua nhận `None` → 409. Nhờ vậy khối ghi tiêu thụ BOM
    # bên dưới chỉ chạy một lần, kho không bị trừ gấp đôi.
    moi = don_chuyen_trang_thai(
        don_id,
        tu=cur,
        sang=body.trang_thai,
        ly_do_huy=body.ly_do_huy.strip() if body.trang_thai == "huy" else None,
    )
    if moi is None:
        raise HTTPException(
            status_code=409, detail=f"chuyen_khong_hop_le:{cur}->{body.trang_thai}"
        )
    if body.trang_thai == "xong":
        _ghi_tieu_thu_uoc_luong(moi, s["role"])
    _audit(s["role"], "quay_chuyen_don", {"id": don_id, "from": cur, "to": body.trang_thai})
    return moi


@router.post("/api/v1/quay/don/{don_id}/chinh")
def quay_don_chinh(
    don_id: str,
    body: ChinhDonBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    s = _require_dang_ca(authorization)
    if s["role"] not in {"quan_ly", "chu_quan"}:
        raise HTTPException(status_code=403, detail="forbidden")
    don = don_get(don_id)
    if not don:
        raise HTTPException(status_code=404, detail="don_khong_tim_thay")
    if don["trang_thai"] in {"xong", "huy"}:
        raise HTTPException(status_code=409, detail="don_da_ket_thuc")
    don["dong"] = _dong_theo_menu(body.dong)
    don["thanh_toan"] = body.thanh_toan
    don_update(don)
    _audit(s["role"], "quay_chinh_don", {"id": don_id})
    return don


@router.get("/api/v1/quay/bao-cao")
def quay_bao_cao(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_manager(authorization)
    items = [x for x in don_list() if x["trang_thai"] != "huy"]
    tong_ly = sum(int(row["so_luong"]) for don in items for row in don["dong"])
    tong_tien = sum(int(row["so_luong"]) * int(row["gia"]) for don in items for row in don["dong"])
    chua_thu = sum(
        int(row["so_luong"]) * int(row["gia"])
        for don in items
        if don["thanh_toan"] == "chua_thu"
        for row in don["dong"]
    )
    return {
        "so_don": len(items),
        "tong_ly": tong_ly,
        "tong_tien": tong_tien,
        "chua_thu": chua_thu,
        "nguon": "quay_noi_bo",
        "ghi": "Đơn ghi tại quầy nội bộ; không phải số Grab.",
    }
