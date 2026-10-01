# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test HTTP cho luồng ảnh quảng cáo từ ẢNH THẬT — quy trình 4 bước.

Các endpoint:
  * `POST /api/v1/menu/{id}/anh/kiem-tra`       — Bước 1, kiểm ảnh đầu vào
  * `POST /api/v1/menu/{id}/anh/prompt-quang-cao` — Bước 3/4, lắp prompt từ ý kiến
  * `POST /api/v1/menu/{id}/anh/generate`       — sinh ảnh từ ảnh thật (2 chế độ)
  * `POST /api/v1/menu/{id}/anh/luu`            — lưu ảnh đang hiện làm ảnh món

Không gọi mạng: Bước 1 được neo bằng cách chặn `validate_product_image` (nó mới
là chỗ gọi AI thị giác), còn prompt là tất định.
"""

from __future__ import annotations

import io

import pytest
from ca_api.interfaces.http.main import app
from ca_api.persist import kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)

_STYLE_KV = "menu_anh_phong_cach"
_DEFAULT_KV = "menu_anh_phong_cach_mac_dinh"

_MON = "mon_ad_flow"


def _reset_styles() -> None:
    """Xoá phong cách đã lưu để test không phụ thuộc thứ tự chạy."""
    kv_set(_STYLE_KV, None)
    kv_set(_DEFAULT_KV, "")


def _tao_mon(ten: str = "Chai nước ép cam", mon_id: str = _MON) -> dict[str, str]:
    _reset_styles()
    hung = headers(client, "hung")
    client.put(
        f"/api/v1/menu/{mon_id}",
        json={"ten": ten, "gia": 35000, "bom": {"ly": 1}},
        headers=hung,
    )
    return hung


def _png_bytes(w: int = 600, h: int = 600) -> bytes:
    """PNG thật cỡ ``w×h`` — Pillow đọc được nên qua được kiểm tra kỹ thuật."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 90, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _png_b64(w: int = 600, h: int = 600) -> str:
    import base64

    return base64.b64encode(_png_bytes(w, h)).decode("ascii")


@pytest.fixture
def _khong_goi_ai_thi_giac(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neo Bước 1: AI thị giác KHÔNG chạy được (mô phỏng chưa cấu hình khoá).

    Chặn ở tầng lời gọi LLM (``menu_ad_prompt.complete``) chứ **không** thay cả
    hàm ``validate_product_image``: nếu thay cả hàm thì các tầng kiểm tra KỸ
    THUẬT (file không phải ảnh, ảnh quá nhỏ, ảnh hỏng ruột) không bao giờ chạy,
    và test sẽ xanh kể cả khi tầng đó hỏng.

    Chặn ở đây cũng tránh ``llm.complete`` gọi ``ensure_dotenv()`` — nạp ``.env``
    THẬT vào ``os.environ`` làm test khác fail ngẫu nhiên theo thứ tự chạy.
    """
    from ca_agents.llm import LlmResult

    def _fake_complete(**kwargs: object) -> LlmResult:
        return LlmResult(ok=False, text="", provider="fake", reason="missing_key")

    monkeypatch.setattr("ca_agents.menu_ad_prompt.complete", _fake_complete)


@pytest.fixture
def _ai_thi_giac_tu_choi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neo Bước 1: AI thị giác trả lời ảnh KHÔNG phải sản phẩm dạng nước."""
    from ca_agents.llm import LlmResult

    def _fake_complete(**kwargs: object) -> LlmResult:
        return LlmResult(
            ok=True,
            text='{"is_liquid_product": false, "clearly_visible": true, '
            '"container": "", "reason_vi": "đây là đĩa thức ăn"}',
            provider="fake",
            reason="",
        )

    monkeypatch.setattr("ca_agents.menu_ad_prompt.complete", _fake_complete)


@pytest.fixture
def _ai_thi_giac_xac_nhan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neo Bước 1: AI thị giác xác nhận ảnh đúng là sản phẩm dạng nước, rõ nét."""
    from ca_agents.llm import LlmResult

    def _fake_complete(**kwargs: object) -> LlmResult:
        return LlmResult(
            ok=True,
            text='{"is_liquid_product": true, "clearly_visible": true, '
            '"container": "glass bottle", "reason_vi": "chai rõ nét"}',
            provider="fake",
            reason="",
        )

    monkeypatch.setattr("ca_agents.menu_ad_prompt.complete", _fake_complete)


# ── BƯỚC 1 — kiểm ảnh đầu vào ───────────────────────────────────────────────


class TestKiemTraAnh:
    def test_requires_chu_quan(self) -> None:
        _tao_mon()
        minh = headers(client, "minh")
        assert (
            client.post(
                f"/api/v1/menu/{_MON}/anh/kiem-tra",
                json={"original_base64": _png_b64()},
                headers=minh,
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/menu/{_MON}/anh/kiem-tra",
                json={"original_base64": _png_b64()},
            ).status_code
            == 401
        )

    def test_mon_khong_ton_tai_404(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        res = client.post(
            "/api/v1/menu/mon_khong_co_that/anh/kiem-tra",
            json={"original_base64": _png_b64()},
            headers=hung,
        )
        assert res.status_code == 404

    def test_ma_mon_sai_422(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        res = client.post(
            "/api/v1/menu/MON SAI/anh/kiem-tra",
            json={"original_base64": _png_b64()},
            headers=hung,
        )
        assert res.status_code == 422

    def test_base64_hong_422(self) -> None:
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/kiem-tra",
            json={"original_base64": "khong-phai-base64!!!"},
            headers=hung,
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "anh_goc_khong_giai_ma_duoc"

    def test_chap_nhan_tien_to_data_url(self, _khong_goi_ai_thi_giac) -> None:
        """UI gửi data-URL (`data:image/png;base64,...`) — tiền tố phải được bóc."""
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/kiem-tra",
            json={"original_base64": f"data:image/png;base64,{_png_b64()}"},
            headers=hung,
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_anh_dat_nhung_chua_kiem_duoc_thi_noi_ro(self, _khong_goi_ai_thi_giac) -> None:
        """Thiếu khoá AI thị giác → ok=true, da_kiem=false, kèm ghi chú cho người dùng."""
        hung = _tao_mon()
        body = client.post(
            f"/api/v1/menu/{_MON}/anh/kiem-tra",
            json={"original_base64": _png_b64()},
            headers=hung,
        ).json()
        assert body["ok"] is True
        assert body["da_kiem"] is False
        assert body["ghi"], "phải nói rõ là chưa kiểm được nội dung ảnh"

    def test_anh_khong_phai_san_pham_thi_chan(self, _ai_thi_giac_tu_choi) -> None:
        """Ảnh không đạt → ok=false + câu nguyên văn của quy trình."""
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/kiem-tra",
            json={"original_base64": _png_b64()},
            headers=hung,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False
        assert body["da_kiem"] is True
        assert body["ly_do"] == "đây là đĩa thức ăn"
        assert body["thong_diep"].startswith("Ảnh bạn gửi không phải là ảnh sản phẩm")
        assert "Vui lòng gửi lại ảnh sản phẩm rõ nét" in body["thong_diep"]

    def test_anh_khong_doc_duoc_van_tra_200_kem_loi(self, _khong_goi_ai_thi_giac) -> None:
        """Ảnh hỏng ruột: 200 kèm ok=false (không phải 500 khó hiểu).

        Chặn ở tầng KỸ THUẬT trước khi tốn một lượt gọi AI thị giác — fixture chỉ
        chặn lời gọi LLM nên tầng này chạy thật.
        """
        import base64

        hung = _tao_mon()
        rac = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"rac" * 100).decode("ascii")
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/kiem-tra",
            json={"original_base64": rac},
            headers=hung,
        )
        assert res.status_code == 200
        assert res.json()["ok"] is False
        assert res.json()["error"] == "anh_goc_khong_doc_duoc"

    def test_anh_qua_nho_bi_chan(self, _khong_goi_ai_thi_giac) -> None:
        """Ảnh 50×50 không đủ để làm ảnh quảng cáo — chặn ở tầng kỹ thuật."""
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/kiem-tra",
            json={"original_base64": _png_b64(50, 50)},
            headers=hung,
        )
        assert res.status_code == 200
        assert res.json()["ok"] is False
        assert res.json()["error"] == "anh_goc_qua_nho"

    def test_ai_xac_nhan_thi_da_kiem_true(self, _ai_thi_giac_xac_nhan) -> None:
        """AI thị giác xác nhận → da_kiem=true, và KHÔNG có ghi chú "chưa kiểm được"."""
        hung = _tao_mon()
        body = client.post(
            f"/api/v1/menu/{_MON}/anh/kiem-tra",
            json={"original_base64": _png_b64()},
            headers=hung,
        ).json()
        assert body["ok"] is True
        assert body["da_kiem"] is True
        assert body["bao_bi"] == "glass bottle"
        assert body["ghi"] == ""


# ── BƯỚC 3 — prompt ảnh quảng cáo ───────────────────────────────────────────


class TestPromptQuangCao:
    def test_requires_chu_quan(self) -> None:
        _tao_mon()
        minh = headers(client, "minh")
        assert (
            client.post(
                f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
                json={"feedback_history": []},
                headers=minh,
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
                json={"feedback_history": []},
            ).status_code
            == 401
        )

    def test_mon_khong_ton_tai_404(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        res = client.post(
            "/api/v1/menu/mon_khong_co_that/anh/prompt-quang-cao",
            json={"feedback_history": []},
            headers=hung,
        )
        assert res.status_code == 404

    def test_prompt_co_bao_bi_va_rang_buoc(self) -> None:
        hung = _tao_mon("Chai nước ép cam")
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": []},
            headers=hung,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["provider"] == "local-template"
        # Mặc định: mô tả trung tính, không suy từ tên món.
        assert body["bao_bi"] == "liquid product container"
        assert "a liquid product container placed front-facing and centered" in body[
            "prompt_en"
        ]
        # Ràng buộc bảo toàn sản phẩm — điều kiện sống còn của luồng này.
        assert "Do not change the shape, label, text, logo" in body["prompt_en"]
        assert "No people, no hands" in body["prompt_en"]

    def test_container_tu_buoc_1_duoc_dung(self) -> None:
        hung = _tao_mon("Cà phê đen")
        body = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": [], "container": "glass bottle"},
            headers=hung,
        ).json()
        assert body["bao_bi"] == "glass bottle"
        assert "a glass bottle placed front-facing and centered" in body["prompt_en"]

    def test_khong_phu_thuoc_ten_mon(self) -> None:
        """Chọn món cà phê đen nhưng gửi ảnh nước nào cũng ra loại nước đó."""
        hung = _tao_mon("Cà phê đen")
        a = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": ["nền xanh"]},
            headers=hung,
        ).json()["prompt_en"]
        hung = _tao_mon("Nước cam")
        b = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": ["nền xanh"]},
            headers=hung,
        ).json()["prompt_en"]
        assert a == b
        assert "black coffee" not in a
        assert "orange juice" not in b

    def test_prompt_khong_mo_ta_lai_san_pham(self) -> None:
        """Prompt phải KHÔNG chứa điều khoản cấm đồ uống (sẽ xoá sản phẩm khỏi ảnh)."""
        hung = _tao_mon()
        body = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": []},
            headers=hung,
        ).json()
        assert "no drink" not in body["prompt_en"]
        assert "no beverage" not in body["prompt_en"]

    def test_y_kien_nguoi_dung_duoc_dich(self) -> None:
        hung = _tao_mon()
        body = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": ["nền xanh, làm sáng hơn"]},
            headers=hung,
        ).json()
        assert "green background" in body["prompt_en"]
        assert "brighter" in body["prompt_en"]

    def test_y_kien_vi_pham_bi_loc_va_bao_lai(self) -> None:
        """`bo_qua` phải trả về UI để người dùng biết vì sao yêu cầu bị bỏ."""
        hung = _tao_mon()
        body = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": ["nền xanh", "thêm người cầm chai"]},
            headers=hung,
        ).json()
        assert body["bo_qua"] == ["thêm người cầm chai"]
        assert "green background" in body["prompt_en"]

    def test_uu_tien_y_kien_moi_nhat(self) -> None:
        """Ý kiến MỚI thắng khi mâu thuẫn — yêu cầu mới không bị yêu cầu cũ đè."""
        hung = _tao_mon()
        body = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": ["nền biển", "nền trắng studio"]},
            headers=hung,
        ).json()
        assert "Latest instruction to prioritize: plain white background studio." in body[
            "prompt_en"
        ]

    def test_tat_dinh(self) -> None:
        """Hai lần gọi cùng đầu vào phải ra cùng prompt."""
        hung = _tao_mon()
        body = {"feedback_history": ["nền xanh"]}
        a = client.post(f"/api/v1/menu/{_MON}/anh/prompt-quang-cao", json=body, headers=hung).json()
        b = client.post(f"/api/v1/menu/{_MON}/anh/prompt-quang-cao", json=body, headers=hung).json()
        assert a["prompt_en"] == b["prompt_en"]

    def test_phong_cach_slug_sai_422(self) -> None:
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": [], "style_slug": "khong_co_that"},
            headers=hung,
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "phong_cach_khong_ton_tai"

    def test_phong_cach_cua_quan_duoc_noi_vao(self) -> None:
        hung = _tao_mon()
        client.put(
            "/api/v1/menu/anh/phong-cach",
            json={
                "slug": "moody_test",
                "ten": "Moody test",
                "mo_ta": "",
                "scene": "concrete_loft",
                "lighting": "moody_low_key",
                "palette": "deep_emerald",
                "lens": "shallow_85mm",
            },
            headers=hung,
        )
        body = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": [], "style_slug": "moody_test"},
            headers=hung,
        ).json()
        assert "moody low-key" in body["prompt_en"]

    def test_qua_nhieu_y_kien_bi_chan(self) -> None:
        """Trần 12 ý kiến (contract) — vượt là 422, không âm thầm cắt."""
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/prompt-quang-cao",
            json={"feedback_history": ["nền xanh"] * 20},
            headers=hung,
        )
        assert res.status_code == 422

    def test_ten_mon_rong_van_dung_duoc_prompt(self) -> None:
        """Sản phẩm lấy từ ảnh đầu vào nên tên món không quyết định prompt."""
        _reset_styles()
        hung = headers(client, "hung")
        client.put(
            "/api/v1/menu/mon_ad_khong_ten",
            json={"ten": "Món test", "gia": 10000, "bom": {"ly": 1}},
            headers=hung,
        )
        res = client.post(
            "/api/v1/menu/mon_ad_khong_ten/anh/prompt-quang-cao",
            json={"feedback_history": []},
            headers=hung,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["prompt_en"] != ""


# ── Endpoint sinh ảnh chỉ còn hai chế độ dùng ảnh thật ─────────────────────


class TestGenerateVoiPromptQuangCao:
    """Sinh ảnh thật cần provider — chỉ kiểm nhánh CHẶN (không gọi mạng)."""

    def test_can_anh_goc_khi_thieu_anh(self) -> None:
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/generate",
            json={"mode": "edit_photo", "feedback_history": []},
            headers=hung,
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "can_anh_goc"

    def test_keep_drink_cung_can_anh_goc(self) -> None:
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/generate",
            json={"mode": "keep_drink", "feedback_history": []},
            headers=hung,
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "can_anh_goc"

    def test_prompt_rong_thi_tu_dung_tu_anh(self) -> None:
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/generate",
            json={"prompt_en": ""},
            headers=hung,
        )
        # Thiếu ảnh → 422 can_anh_goc (chặn trước khi dựng prompt/provider).
        assert res.status_code == 422
        assert res.json()["detail"] == "can_anh_goc"

    def test_qua_nhieu_y_kien_tren_generate_422(self) -> None:
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/generate",
            json={
                "feedback_history": ["nền xanh"] * 20,
                "mode": "edit_photo",
                "original_base64": _png_b64(),
            },
            headers=hung,
        )
        assert res.status_code == 422

    def test_mode_ve_moi_bi_loai_bo(self) -> None:
        """Chế độ `from_prompt` đã xoá — gửi lên phải 422, không rơi về mặc định."""
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/generate",
            json={"prompt_en": "x", "mode": "from_prompt", "original_base64": _png_b64()},
            headers=hung,
        )
        assert res.status_code == 422


# ── Lưu ảnh đang hiện làm ảnh đại diện món ─────────────────────────────────


class TestLuuAnh:
    """`POST /anh/luu` lưu TRỰC TIẾP bytes đã hiện (không sinh lại)."""

    def test_luu_anh_thanh_cong(self) -> None:
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/luu",
            json={"image_base64": _png_b64()},
            headers=hung,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["saved"] is True
        assert body["hinh_url"] == f"/api/v1/menu/{_MON}/anh"

    def test_chap_nhan_data_url(self) -> None:
        """UI gửi data-URL (`data:image/png;base64,…`) — tiền tố phải được bóc."""
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/luu",
            json={"image_base64": f"data:image/png;base64,{_png_b64()}"},
            headers=hung,
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_base64_hong_422(self) -> None:
        hung = _tao_mon()
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/luu",
            json={"image_base64": "khong-phai-base64!!!"},
            headers=hung,
        )
        assert res.status_code == 422

    def test_khong_phai_anh_422(self) -> None:
        import base64

        hung = _tao_mon()
        rac = base64.b64encode(b"day khong phai anh").decode("ascii")
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/luu",
            json={"image_base64": rac},
            headers=hung,
        )
        assert res.status_code == 422

    def test_mon_khong_ton_tai_404(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        res = client.post(
            "/api/v1/menu/mon_khong_co_that/anh/luu",
            json={"image_base64": _png_b64()},
            headers=hung,
        )
        assert res.status_code == 404

    def test_requires_chu_quan(self) -> None:
        _tao_mon()
        minh = headers(client, "minh")
        assert (
            client.post(
                f"/api/v1/menu/{_MON}/anh/luu",
                json={"image_base64": _png_b64()},
                headers=minh,
            ).status_code
            == 403
        )

    def test_luu_xong_doc_duoc_ngay_va_hien_trong_menu(self) -> None:
        """Lưu xong thì GET ảnh trả đúng bytes đã lưu + menu liệt kê hinh_url."""
        hung = _tao_mon()
        raw = _png_bytes(600, 600)
        import base64

        b64 = base64.b64encode(raw).decode("ascii")
        res = client.post(
            f"/api/v1/menu/{_MON}/anh/luu",
            json={"image_base64": b64},
            headers=hung,
        )
        assert res.json()["hinh_url"] == f"/api/v1/menu/{_MON}/anh"
        anh = client.get(f"/api/v1/menu/{_MON}/anh")
        assert anh.status_code == 200
        assert anh.content == raw
        items = client.get("/api/v1/menu/quan-tri", headers=hung).json()["items"]
        mon = next(m for m in items if m["id"] == _MON)
        assert mon["hinh_url"] == f"/api/v1/menu/{_MON}/anh"
