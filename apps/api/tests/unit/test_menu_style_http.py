# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test HTTP cho phong cách thiết kế ảnh menu — `/api/v1/menu/anh/phong-cach`.

Chỉ kiểm tra BLOCKING + trạng thái lưu trữ (không gọi mạng sinh ảnh). Ba điều
quan trọng: (1) chỉ chủ quán sửa được; (2) giá trị ngoài bảng hợp lệ → 422 kèm
danh sách cho phép; (3) phong cách mặc định đổi được để "áp cho các ly khác".
"""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from ca_api.persist import kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)

_STYLE_KV = "menu_anh_phong_cach"
_DEFAULT_KV = "menu_anh_phong_cach_mac_dinh"

_VALID_BODY = {
    "slug": "",
    "ten": "Phong cách kiểm thử",
    "mo_ta": "tạo trong test",
    "scene": "marble_bar",
    "lighting": "window_soft",
    "palette": "terracotta",
    "lens": "tight_50mm",
}


def _reset_styles() -> None:
    """Xoá phong cách đã lưu để test không phụ thuộc thứ tự chạy."""
    kv_set(_STYLE_KV, None)
    kv_set(_DEFAULT_KV, "")


# PNG 1×1 hợp lệ: magic bytes + IHDR tối thiểu. Đủ để `_detect_image_suffix` nhận
# ra `.png` và `base64.b64decode(validate=True)` chấp nhận. Dùng chung cho các test
# cần "ảnh gốc" mà không muốn đọc file thật từ đĩa.
_PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TestPermissions:
    def test_requires_chu_quan(self) -> None:
        _reset_styles()
        minh = headers(client, "minh")
        lan = headers(client, "lan")
        assert client.get("/api/v1/menu/anh/phong-cach", headers=minh).status_code == 403
        assert client.get("/api/v1/menu/anh/phong-cach", headers=lan).status_code == 403
        assert client.get("/api/v1/menu/anh/phong-cach").status_code == 401

    def test_put_requires_chu_quan(self) -> None:
        _reset_styles()
        lan = headers(client, "lan")
        assert (
            client.put("/api/v1/menu/anh/phong-cach", json=_VALID_BODY, headers=lan).status_code
            == 403
        )

    def test_delete_requires_chu_quan(self) -> None:
        _reset_styles()
        minh = headers(client, "minh")
        assert (
            client.delete("/api/v1/menu/anh/phong-cach/nhip_quan_classic", headers=minh).status_code
            == 403
        )


class TestList:
    def test_returns_presets_and_options(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        res = client.get("/api/v1/menu/anh/phong-cach", headers=hung)
        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["items"]) >= 3
        assert body["mac_dinh"]
        assert set(body["tuy_chon"]) == {"scene", "lighting", "palette", "lens"}
        assert "cafe_wood" in body["tuy_chon"]["scene"]

    def test_preset_fields_are_complete(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        items = client.get("/api/v1/menu/anh/phong-cach", headers=hung).json()["items"]
        for item in items:
            assert set(item) >= {"slug", "ten", "scene", "lighting", "palette", "lens"}


class TestSave:
    def test_creates_style_from_name_slug(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        res = client.put("/api/v1/menu/anh/phong-cach", json=_VALID_BODY, headers=hung)
        assert res.status_code == 200, res.text
        item = res.json()["item"]
        # Tên tiếng Việt có dấu → slug bỏ dấu, không rỗng.
        assert item["slug"] == "phong_cach_kiem_thu"
        assert item["scene"] == "marble_bar"

    def test_saved_style_appears_in_list(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        client.put("/api/v1/menu/anh/phong-cach", json=_VALID_BODY, headers=hung)
        slugs = {
            x["slug"]
            for x in client.get("/api/v1/menu/anh/phong-cach", headers=hung).json()["items"]
        }
        assert "phong_cach_kiem_thu" in slugs

    def test_upsert_same_slug_updates_not_duplicates(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        client.put("/api/v1/menu/anh/phong-cach", json=_VALID_BODY, headers=hung)
        updated = {**_VALID_BODY, "scene": "outdoor_garden"}
        set_default = client.post(
            "/api/v1/menu/anh/phong-cach/phong_cach_kiem_thu/mac-dinh", headers=hung
        )
        assert set_default.status_code == 200
        client.put("/api/v1/menu/anh/phong-cach", json=updated, headers=hung)
        items = client.get("/api/v1/menu/anh/phong-cach", headers=hung).json()["items"]
        matches = [x for x in items if x["slug"] == "phong_cach_kiem_thu"]
        assert len(matches) == 1
        assert matches[0]["scene"] == "outdoor_garden"

    def test_invalid_scene_rejected_with_allowed_values(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        bad = {**_VALID_BODY, "scene": "rung_banana"}
        res = client.put("/api/v1/menu/anh/phong-cach", json=bad, headers=hung)
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert detail["loi"] == "gia_tri_khong_hop_le"
        assert "cafe_wood" in detail["scene"]

    def test_invalid_lighting_rejected(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        bad = {**_VALID_BODY, "lighting": "nen_troi"}
        assert (
            client.put("/api/v1/menu/anh/phong-cach", json=bad, headers=hung).status_code == 422
        )

    def test_blank_name_rejected(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        bad = {**_VALID_BODY, "ten": "   ", "slug": "   "}
        res = client.put("/api/v1/menu/anh/phong-cach", json=bad, headers=hung)
        assert res.status_code == 422


class TestDefault:
    def test_set_default_changes_list_default(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        client.put("/api/v1/menu/anh/phong-cach", json=_VALID_BODY, headers=hung)
        res = client.post(
            "/api/v1/menu/anh/phong-cach/phong_cach_kiem_thu/mac-dinh", headers=hung
        )
        assert res.status_code == 200, res.text
        assert res.json()["mac_dinh"] == "phong_cach_kiem_thu"
        listed = client.get("/api/v1/menu/anh/phong-cach", headers=hung).json()
        assert listed["mac_dinh"] == "phong_cach_kiem_thu"

    def test_set_default_unknown_slug_404(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        res = client.post("/api/v1/menu/anh/phong-cach/khong_co_that/mac-dinh", headers=hung)
        assert res.status_code == 404


class TestDelete:
    def test_delete_removes_style(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        client.put("/api/v1/menu/anh/phong-cach", json=_VALID_BODY, headers=hung)
        res = client.delete("/api/v1/menu/anh/phong-cach/phong_cach_kiem_thu", headers=hung)
        assert res.status_code == 200, res.text
        slugs = {
            x["slug"]
            for x in client.get("/api/v1/menu/anh/phong-cach", headers=hung).json()["items"]
        }
        assert "phong_cach_kiem_thu" not in slugs

    def test_delete_unknown_404(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        assert (
            client.delete("/api/v1/menu/anh/phong-cach/khong_co_that", headers=hung).status_code
            == 404
        )

    def test_cannot_delete_last_style(self) -> None:
        """Xoá hết phong cách sẽ để UI không còn gì chọn → chặn ở phong cách cuối."""
        _reset_styles()
        hung = headers(client, "hung")
        items = client.get("/api/v1/menu/anh/phong-cach", headers=hung).json()["items"]
        for item in items[:-1]:
            assert (
                client.delete(
                    f"/api/v1/menu/anh/phong-cach/{item['slug']}", headers=hung
                ).status_code
                == 200
            )
        last = items[-1]["slug"]
        res = client.delete(f"/api/v1/menu/anh/phong-cach/{last}", headers=hung)
        assert res.status_code == 409
        # Sau khi bị chặn, danh sách vẫn còn đúng 1 phong cách.
        assert len(client.get("/api/v1/menu/anh/phong-cach", headers=hung).json()["items"]) == 1
        _reset_styles()


class TestGenerateGuards:
    """Các nhánh từ chối của endpoint generate — không cần gọi mạng."""

    def test_unknown_style_slug_rejected(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        client.put(
            "/api/v1/menu/tra_dao",
            json={"ten": "Trà đào", "gia": 35000, "bom": {"ly": 1}},
            headers=hung,
        )
        res = client.post(
            "/api/v1/menu/tra_dao/anh/generate",
            json={"prompt_en": "iced tea on a table", "style_slug": "khong_co_that"},
            headers=hung,
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "phong_cach_khong_ton_tai"

    def test_empty_prompt_and_name_rejected(self) -> None:
        """Không prompt, không tên món → 422 thay vì sinh ảnh từ prompt rỗng."""
        _reset_styles()
        hung = headers(client, "hung")
        client.put(
            "/api/v1/menu/mon_khong_ten",
            json={"ten": "   ", "gia": 10000, "bom": {"ly": 1}},
            headers=hung,
        )
        res = client.post(
            "/api/v1/menu/mon_khong_ten/anh/generate",
            json={"prompt_en": ""},
            headers=hung,
        )
        # Tên món toàn khoảng trắng bị contract MonNuoc từ chối (422 "mon_khong_hop_le")
        # hoặc lọt qua rồi thì prompt dựng ra rỗng → cũng 422. Cả hai đều là chặn.
        assert res.status_code == 422


class TestGenerateModes:
    """Hai chế độ tạo ảnh từ ảnh thật — chỉ kiểm tra nhánh CHẶN (không gọi mạng)."""

    _MON = "mon_che_do"

    def _tao_mon(self) -> dict[str, str]:
        _reset_styles()
        hung = headers(client, "hung")
        client.put(
            f"/api/v1/menu/{self._MON}",
            json={"ten": "Cà phê sữa đá", "gia": 25000, "bom": {"ly": 1}},
            headers=hung,
        )
        return hung

    def test_edit_photo_requires_original(self) -> None:
        hung = self._tao_mon()
        res = client.post(
            f"/api/v1/menu/{self._MON}/anh/generate",
            json={"prompt_en": "professional cafe ad", "mode": "edit_photo"},
            headers=hung,
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "can_anh_goc"

    def test_keep_drink_requires_original(self) -> None:
        hung = self._tao_mon()
        res = client.post(
            f"/api/v1/menu/{self._MON}/anh/generate",
            json={"prompt_en": "professional cafe ad", "mode": "keep_drink"},
            headers=hung,
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "can_anh_goc"

    def test_invalid_base64_rejected(self) -> None:
        """Base64 hỏng phải là 422 rõ ràng, không phải lỗi 500 khó hiểu."""
        hung = self._tao_mon()
        res = client.post(
            f"/api/v1/menu/{self._MON}/anh/generate",
            json={
                "prompt_en": "professional cafe ad",
                "mode": "edit_photo",
                "original_base64": "khong-phai-base64!!!",
            },
            headers=hung,
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "anh_goc_khong_giai_ma_duoc"

    def test_empty_original_rejected(self) -> None:
        hung = self._tao_mon()
        res = client.post(
            f"/api/v1/menu/{self._MON}/anh/generate",
            json={
                "prompt_en": "professional cafe ad",
                "mode": "edit_photo",
                "original_base64": "",
            },
            headers=hung,
        )
        # Chuỗi rỗng lọt qua `min_length` (không đặt) nhưng bị chặn ở tầng giải mã.
        assert res.status_code == 422
        assert res.json()["detail"] in {"can_anh_goc", "anh_goc_trong", "anh_goc_khong_giai_ma_duoc"}

    def test_unknown_mode_rejected(self) -> None:
        """Chế độ lạ phải 422 (contract Literal), không âm thầm rơi về mặc định."""
        hung = self._tao_mon()
        res = client.post(
            f"/api/v1/menu/{self._MON}/anh/generate",
            json={"prompt_en": "professional cafe ad", "mode": "che_do_khong_co"},
            headers=hung,
        )
        assert res.status_code == 422

    def test_data_url_prefix_accepted(self) -> None:
        """UI gửi data-URL (`data:image/png;base64,...`) — tiền tố phải được bóc."""
        hung = self._tao_mon()
        # Chế độ keep_drink: chặn sớm ở tách chủ thể với ảnh 1×1 (quá nhỏ) → 200 ok=False
        # hoặc lỗi provider. Điều cần khẳng định: KHÔNG phải 422 do base64 hỏng.
        res = client.post(
            f"/api/v1/menu/{self._MON}/anh/generate",
            json={
                "prompt_en": "professional cafe ad",
                "mode": "keep_drink",
                "original_base64": f"data:image/png;base64,{_PNG_1PX}",
            },
            headers=hung,
        )
        assert res.status_code == 200
        body = res.json()
        assert "anh_goc_khong_giai_ma_duoc" not in str(body.get("error", ""))


class TestModeAvailability:
    """`/anh/kha-dung` — UI biết TRƯỚC chế độ nào chạy được, không chọn xong mới lỗi."""

    @pytest.fixture(autouse=True)
    def _khong_co_khoa(self, monkeypatch: pytest.MonkeyPatch):
        """Neo trạng thái "CHƯA có khoá" cho mọi test trong lớp này.

        Không neo thì test phụ thuộc `.env` của máy đang chạy: máy dev có
        `CLOUDFLARE_ACCOUNT_ID` (key thật của quán) nên `kha_dung=true` và test
        đi nhánh `else` — PASS ở máy dev nhưng FAIL trên CI (CI không có `.env`,
        đi nhánh `assert` và so câu thông báo). Đúng loại "test pass riêng, fail
        trong suite" gây tốn thời gian nhất.

        Chặn ở tầng HÀM (`_cf_ready`) chứ không xoá biến môi trường:
        `_cf_ready` gọi `ensure_dotenv()` nạp LẠI key từ `.env`, nên xoá biến là
        không đủ.
        """
        from ca_agents import image_gen

        monkeypatch.delenv("POLLINATIONS_API_KEY", raising=False)
        monkeypatch.setattr(image_gen, "_cf_ready", lambda: None)

    def test_requires_chu_quan(self) -> None:
        assert client.get("/api/v1/menu/anh/kha-dung").status_code == 401
        minh = headers(client, "minh")
        assert client.get("/api/v1/menu/anh/kha-dung", headers=minh).status_code == 403

    def test_always_available_modes(self) -> None:
        """Chế độ giữ sản phẩm luôn khả dụng; không còn chế độ vẽ mới."""
        hung = headers(client, "hung")
        res = client.get("/api/v1/menu/anh/kha-dung", headers=hung)
        assert res.status_code == 200
        che_do = res.json()["che_do"]
        assert "from_prompt" not in che_do
        assert che_do["keep_drink"]["kha_dung"] is True

    def test_edit_photo_reports_reason_when_blocked(self) -> None:
        """Thiếu khoá → `kha_dung=false` kèm lý do có cách khắc phục.

        Khoá có thể bật chế độ: `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`
        (provider chính) hoặc `POLLINATIONS_API_KEY`. Fixture `_khong_co_khoa`
        đã neo trạng thái "chưa có khoá" nên test này luôn kiểm nhánh bị chặn.
        """
        hung = headers(client, "hung")
        che_do = client.get("/api/v1/menu/anh/kha-dung", headers=hung).json()["che_do"]
        edit = che_do["edit_photo"]
        assert edit["kha_dung"] is False
        # Lý do phải chỉ ĐÚNG nơi lấy khoá của provider chính (Cloudflare —
        # miễn phí, không cần thẻ) và gợi ý chế độ chạy được ngay.
        assert "CLOUDFLARE_ACCOUNT_ID" in edit["ly_do"]
        assert "dash.cloudflare.com" in edit["ly_do"]
        # Nhãn chế độ phải khớp UI hiện tại (chạy cho mọi bao bì, không riêng ly).
        assert "Giữ nguyên sản phẩm" in edit["ly_do"]

    def test_edit_photo_blocked_returns_422_with_reason(self) -> None:
        """Chọn chế độ thiếu khoá → 422 kèm lý do, KHÔNG gọi provider rồi mới lỗi."""
        hung = headers(client, "hung")
        client.put(
            "/api/v1/menu/mon_che_do_kha_dung",
            json={"ten": "Cà phê sữa đá", "gia": 25000, "bom": {"ly": 1}},
            headers=hung,
        )
        res = client.post(
            "/api/v1/menu/mon_che_do_kha_dung/anh/generate",
            json={
                "prompt_en": "professional cafe ad",
                "mode": "edit_photo",
                "original_base64": _PNG_1PX,
            },
            headers=hung,
        )
        assert res.status_code == 422
        detail = str(res.json()["detail"])
        assert "CLOUDFLARE_ACCOUNT_ID" in detail
        # Không được lộ mã kỹ thuật thô ra cho người vận hành.
        assert "Traceback" not in detail


class TestPromptEndpoint:
    """`/anh/prompt` (dựng prompt từ tên món) đã xoá — mọi prompt đều từ ảnh thật."""

    def test_prompt_theo_mon_da_bi_xoa(self) -> None:
        _reset_styles()
        hung = headers(client, "hung")
        client.put(
            "/api/v1/menu/tra_dao_cam_sa",
            json={"ten": "Trà đào cam sả", "gia": 45000, "bom": {"ly": 1}},
            headers=hung,
        )
        res = client.post(
            "/api/v1/menu/tra_dao_cam_sa/anh/prompt",
            json={"aspect_ratio": "4:5"},
            headers=hung,
        )
        # Endpoint không còn tồn tại → 404/405, không trả prompt vẽ mới theo tên món.
        assert res.status_code in (404, 405)
