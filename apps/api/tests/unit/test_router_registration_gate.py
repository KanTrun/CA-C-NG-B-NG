# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Gate: mọi file router trong `interfaces/http/` phải được đăng ký vào app.

Bug QA đợt 6 (2026-09-28): `ai_insight.py` tồn tại đầy đủ (2 endpoint, có
docstring, có test ở nơi khác) nhưng **không được import và không được
`app.include_router`** trong `main.py`. Hệ quả: **6 trang web** gọi
`POST /api/v1/ai/insight` đều nhận 404 — người dùng thấy khung "AI phân tích"
trống, không có lỗi rõ ràng nào hiện ra.

Loại lỗi này KHÔNG bị bắt bởi test hiện có vì:
- Không có lỗi import (file hợp lệ, chỉ là không ai gọi).
- Không có lỗi type (ruff/mypy thấy file "không được dùng" nhưng không phải lỗi).
- Test endpoint không tồn tại thì không ai viết.

Gate này phát hiện router mồ côi bằng cách quét TĨNH: đối chiếu danh sách file
`*_router`-có-thật trong thư mục với những gì `main.py` thực sự import.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HTTP_DIR = _REPO_ROOT / "apps" / "api" / "src" / "ca_api" / "interfaces" / "http"
_MAIN = _HTTP_DIR / "main.py"

# File trong thư mục KHÔNG phải router độc lập (không cần include).
_KHONG_PHAI_ROUTER = {
    "__init__",
    "main",
    # Khai báo router con dùng lại, không tự include.
    "pricing_radar",  # có system_router riêng, include có điều kiện ở main.py
}


def _cac_file_co_router() -> dict[str, set[str]]:
    """Trả {tên_file: {tên_biến_router}} cho mọi file khai `router = APIRouter(...)`."""
    ket_qua: dict[str, set[str]] = {}
    for path in sorted(_HTTP_DIR.glob("*.py")):
        ten = path.stem
        if ten in _KHONG_PHAI_ROUTER:
            continue
        noi_dung = path.read_text(encoding="utf-8")
        # Bắt `router = APIRouter(` và `xxx_router = APIRouter(`
        bien = set(re.findall(r"^(\w*router)\s*=\s*APIRouter\(", noi_dung, re.MULTILINE))
        if bien:
            ket_qua[ten] = bien
    return ket_qua


def test_moi_file_router_deu_duoc_import_trong_main() -> None:
    """Mọi file khai APIRouter phải có dòng `from ...http.<file> import` trong main.py.

    Trước fix: `ai_insight.py` có `router = APIRouter(...)` nhưng KHÔNG xuất hiện
    trong `main.py` → 2 endpoint của nó trả 404 trên production.
    """
    main_txt = _MAIN.read_text(encoding="utf-8")
    thieu: list[str] = []
    for ten in sorted(_cac_file_co_router()):
        if f"from ca_api.interfaces.http.{ten} import" not in main_txt:
            thieu.append(ten)
    assert not thieu, (
        "Router MỒ CÔI (có file nhưng main.py không import) → endpoint của nó trả 404: "
        f"{thieu}. Thêm `from ca_api.interfaces.http.<file> import router as <x>_router` "
        "VÀ `app.include_router(<x>_router)` trong main.py."
    )


def test_moi_router_import_deu_duoc_include() -> None:
    """Mọi biến `<x>_router` được import trong main.py phải được `include_router`.

    Bắt trường hợp import rồi nhưng QUÊN include — cũng gây 404 y hệt.
    """
    main_txt = _MAIN.read_text(encoding="utf-8")
    imported = set(re.findall(r"from ca_api\.interfaces\.http\.\w+ import router as (\w+)", main_txt))
    # `app.include_router(x)` — có thể nằm trong block `if`.
    included = set(re.findall(r"app\.include_router\((\w+)\)", main_txt))
    thieu = sorted(imported - included)
    assert not thieu, (
        f"Router được import nhưng KHÔNG include → endpoint không tồn tại: {thieu}. "
        "Thêm `app.include_router(<tên>)` trong main.py."
    )


def test_ai_insight_duoc_dang_ky_va_co_trong_openapi() -> None:
    """Chốt cụ thể bug đợt 6: `/api/v1/ai/insight` phải có trong OpenAPI.

    6 trang web (Đề xuất thông minh, Tự giải thích, Thử nghiệm an toàn, Cẩm nang,
    Học từ phản hồi, Hộp thư ràng buộc) gọi endpoint này qua `AiInsightPanel`.
    """
    from ca_api.interfaces.http.main import app

    spec = app.openapi()
    paths = set(spec.get("paths", {}))
    assert "/api/v1/ai/insight" in paths, "AiInsightPanel của 6 trang web sẽ 404"
    assert "/api/v1/ai/insight/ask" in paths, "AskAiBox của các trang AI sẽ 404"
