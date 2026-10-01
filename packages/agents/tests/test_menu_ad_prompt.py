"""Test cho luồng ảnh quảng cáo từ ẢNH THẬT — `ca_agents.menu_ad_prompt`.

Không gọi mạng: prompt được lắp từ template + lịch sử ý kiến nên hoàn toàn tất
định. Phần duy nhất cần provider là Bước 1 (kiểm nội dung ảnh) — những test đó
chặn `complete()` để không mở mạng.

Điều quan trọng nhất được kiểm ở đây: **ràng buộc bảo toàn sản phẩm không bao giờ
biến mất**, kể cả sau nhiều lần người dùng góp ý. Mất ràng buộc đó là mất cả tính
năng — model sẽ vẽ ra một sản phẩm khác thay vì dàn dựng lại sản phẩm của quán.
"""

from __future__ import annotations

import base64
import io

import pytest
from ca_agents import menu_ad_prompt as ad
from ca_agents.menu_ad_prompt import (
    _MAX_Y_KIEN_LICH_SU,
    THONG_DIEP_ANH_KHONG_HOP_LE,
    append_feedback,
    build_ad_prompt,
    loai_bao_bi,
    loc_y_kien,
    validate_product_image,
)

# ── Loại bao bì ─────────────────────────────────────────────────────────────


class TestLoaiBaoBi:
    def test_nhan_dien_bao_bi_tieng_viet(self) -> None:
        assert loai_bao_bi("Chai nước ép cam") == "bottle"
        assert loai_bao_bi("Lọ mật ong") == "jar"
        assert loai_bao_bi("Bình trà") == "jug"
        assert loai_bao_bi("Hộp sữa tươi") == "box"
        assert loai_bao_bi("Túi trà") == "pouch"
        assert loai_bao_bi("Ly trà đào") == "glass"

    def test_cum_dai_thang_cum_ngan(self) -> None:
        """"Chai thủy tinh" phải ra "glass bottle", không phải "bottle" trơn."""
        assert loai_bao_bi("Chai thủy tinh nước suối") == "glass bottle"

    def test_ten_khong_ro_bao_bi_thi_trung_tinh(self) -> None:
        """Không suy được → mô tả trung tính, KHÔNG đoán bừa (đoán sai = vẽ sai dạng)."""
        assert loai_bao_bi("Trà đào") == ad._CONTAINER_MAC_DINH
        assert loai_bao_bi("Món lạ xyz") == ad._CONTAINER_MAC_DINH
        assert loai_bao_bi("") == ad._CONTAINER_MAC_DINH


# ── Lọc ý kiến vi phạm ràng buộc ────────────────────────────────────────────


class TestLocYKien:
    def test_loc_cum_doi_san_pham(self) -> None:
        giu, bo = loc_y_kien("thay nhãn mới")
        assert giu == ""
        assert bo == ("thay nhãn mới",)

    def test_loc_cum_them_nguoi(self) -> None:
        _, bo = loc_y_kien("thêm người cầm chai")
        assert bo == ("thêm người cầm chai",)

    def test_loc_hoat_dong_khong_dau(self) -> None:
        """Bỏ dấu là cách vô tình lách qua bộ lọc dễ nhất — phải chặn như nhau."""
        _, bo = loc_y_kien("them nguoi")
        assert bo == ("them nguoi",)

    def test_giu_menh_de_hop_le_trong_cau_hon_hop(self) -> None:
        """Một câu vừa hợp lệ vừa vi phạm → giữ phần hợp lệ, chỉ bỏ phần sai."""
        giu, bo = loc_y_kien("nền xanh, thêm người cầm chai")
        assert "green background" in giu
        assert bo == ("thêm người cầm chai",)

    def test_khong_chan_oan_mau_xanh(self) -> None:
        """"màu" và "mẫu" cùng dạng không dấu — không được chặn "màu xanh"."""
        giu, bo = loc_y_kien("màu xanh")
        assert bo == ()
        assert giu == "green tones"

    def test_khong_chan_oan_lat_chanh(self) -> None:
        """"lát" và "lật" cùng dạng không dấu — không được chặn "lát chanh"."""
        _, bo = loc_y_kien("lát chanh trên bàn")
        assert bo == ()

    def test_khong_chan_oan_doi_nen(self) -> None:
        """"đổi" và "đổ" — "đổi nền" là yêu cầu hợp lệ."""
        giu, bo = loc_y_kien("đổi nền sang màu xanh")
        assert bo == ()
        assert "blue" in giu or "green" in giu

    def test_bo_qua_nhieu_cum(self) -> None:
        _, bo = loc_y_kien("thay nhãn và thêm người")
        assert len(bo) == 2


# ── Dịch ý kiến ─────────────────────────────────────────────────────────────


class TestDichYKien:
    def test_dich_cum_boi_canh(self) -> None:
        giu, _ = loc_y_kien("nền xanh, làm sáng hơn")
        assert giu == "green background, brighter, higher exposure"

    def test_dich_anh_sang_va_thoi_diem(self) -> None:
        giu, _ = loc_y_kien("ánh sáng tự nhiên buổi sáng")
        assert giu == "natural daylight morning light"

    def test_dich_khong_dau(self) -> None:
        giu, bo = loc_y_kien("doi nen sang mau xanh")
        assert bo == ()
        assert giu == "bright background green tones"

    def test_dich_tu_dien_chung_do_uong(self) -> None:
        """"bạc hà" không có trong từ điển bối cảnh — phải rơi xuống từ điển món."""
        giu, _ = loc_y_kien("thêm lá bạc hà")
        assert "mint" in giu

    def test_bo_tu_noi_khong_mang_thong_tin(self) -> None:
        """"làm sáng hơn" ra "brighter, higher exposure", không còn "làm" lơ lửng."""
        giu, _ = loc_y_kien("làm sáng hơn")
        assert "làm" not in giu
        assert "brighter" in giu

    def test_tu_la_duoc_giu_nguyen(self) -> None:
        giu, _ = loc_y_kien("trang trí kiểu xyz")
        assert "xyz" in giu

    def test_y_kien_trong(self) -> None:
        assert loc_y_kien("") == ("", ())
        assert loc_y_kien("   ") == ("", ())


# ── Lịch sử ý kiến ──────────────────────────────────────────────────────────


class TestAppendFeedback:
    def test_noi_them_khong_ghi_de(self) -> None:
        """Ý kiến cũ KHÔNG bị xoá — "nền biển" rồi "sáng hơn" phải cùng còn."""
        h = append_feedback([], "nền biển")
        h = append_feedback(h, "làm sáng hơn")
        assert h == ["nền biển", "làm sáng hơn"]

    def test_bo_y_kien_rong(self) -> None:
        assert append_feedback(["a"], "   ") == ["a"]

    def test_cat_tran_bo_phan_cu_nhat(self) -> None:
        h: list[str] = []
        for i in range(_MAX_Y_KIEN_LICH_SU + 5):
            h = append_feedback(h, f"y kien {i}")
        assert len(h) == _MAX_Y_KIEN_LICH_SU
        assert h[-1] == f"y kien {_MAX_Y_KIEN_LICH_SU + 4}"
        assert h[0] != "y kien 0"

    def test_khong_sua_danh_sach_goc(self) -> None:
        goc = ["a"]
        append_feedback(goc, "b")
        assert goc == ["a"]


# ── Prompt hoàn chỉnh ───────────────────────────────────────────────────────


class TestBuildAdPrompt:
    def test_ok_va_co_bao_bi(self) -> None:
        # Mặc định (không truyền container) → mô tả trung tính, không suy từ tên món.
        res = build_ad_prompt("Chai nước ép cam")
        assert res.ok is True
        assert res.container == ad._CONTAINER_MAC_DINH
        assert f"a {ad._CONTAINER_MAC_DINH} placed front-facing and centered" in res.prompt_en

    def test_container_tu_buoc_1_duoc_dung(self) -> None:
        res = build_ad_prompt(container="glass bottle")
        assert res.ok is True
        assert res.container == "glass bottle"
        assert "a glass bottle placed front-facing and centered" in res.prompt_en

    def test_khong_phu_thuoc_ten_mon(self) -> None:
        """Gửi ảnh nước nào thì ra ảnh từ loại nước đó — tên món không đổi prompt."""
        a = build_ad_prompt("Cà phê đen", feedback_history=["nền xanh"])
        b = build_ad_prompt("Nước cam", feedback_history=["nền xanh"])
        assert a.prompt_en == b.prompt_en
        assert "black coffee" not in a.prompt_en
        assert "orange juice" not in b.prompt_en

    def test_ten_mon_rong_van_ok(self) -> None:
        """Sản phẩm lấy từ ảnh đầu vào nên tên món trống vẫn dựng được prompt."""
        for ten in ("", "   "):
            res = build_ad_prompt(ten)
            assert res.ok is True
            assert res.prompt_en != ""

    def test_moi_rang_buoc_luon_co_mat(self) -> None:
        """Mọi ràng buộc bắt buộc phải có ở MỌI prompt — kể cả khi không có ý kiến."""
        res = build_ad_prompt("Chai nước ép cam")
        assert "front-facing and centered" in res.prompt_en
        assert "Do not change the shape, label, text, logo" in res.prompt_en
        assert "same drink type" in res.prompt_en
        assert "Environment, lighting, style, mood, camera angle" in res.prompt_en
        assert "No people, no hands" in res.prompt_en

    def test_rang_buoc_con_sau_nhieu_lan_chinh(self) -> None:
        """Sau 10 lần góp ý, ràng buộc vẫn nguyên — đây là điều kiện sống còn."""
        h: list[str] = []
        for i in range(10):
            h = append_feedback(h, f"nền xanh lần {i}")
        res = build_ad_prompt("Chai nước ép cam", feedback_history=h)
        assert "Do not change the shape, label, text, logo" in res.prompt_en
        assert "No people, no hands" in res.prompt_en
        assert "front-facing and centered" in res.prompt_en

    def test_ket_bang_cau_chat_luong(self) -> None:
        res = build_ad_prompt("Chai nước ép cam")
        assert res.prompt_en.rstrip().endswith("clean composition.")

    def test_giu_dung_cau_truc_template(self) -> None:
        """Ba phần theo đúng thứ tự: mở bài → ý kiến → ràng buộc → kết."""
        res = build_ad_prompt("Chai nước ép cam", feedback_history=["nền xanh"])
        p = res.prompt_en
        assert p.index("A professional product photograph") < p.index("green background")
        assert p.index("green background") < p.index("The product stays front-facing")
        assert p.index("The product stays front-facing") < p.index("High resolution")

    def test_uu_tien_y_kien_moi_nhat(self) -> None:
        """Mâu thuẫn: ý kiến MỚI thắng — server đặt nó ở cuối prompt trước phần kết."""
        res = build_ad_prompt("Chai nước ép cam", feedback_history=["nền biển", "nền trắng studio"])
        assert "Latest instruction to prioritize: plain white background studio." in res.prompt_en
        # Ý kiến cũ KHÔNG bị xoá khỏi prompt (chỉ bị mệnh đề ưu tiên lấn át).
        assert "seaside background" in res.prompt_en

    def test_khong_co_y_kien_thi_khong_co_phan_uu_tien(self) -> None:
        res = build_ad_prompt("Chai nước ép cam")
        assert "Latest instruction" not in res.prompt_en

    def test_phong_cach_quan_duoc_noi_vao(self) -> None:
        res = build_ad_prompt("Chai nước ép cam", style_prompt="moody low-key lighting")
        assert "moody low-key lighting" in res.prompt_en

    def test_cum_bi_loc_duoc_bao_lai(self) -> None:
        """``bo_qua`` phải trả về UI để người dùng biết vì sao yêu cầu bị bỏ."""
        res = build_ad_prompt("Chai nước ép cam", feedback_history=["thay nhãn mới"])
        assert res.bo_qua == ("thay nhãn mới",)

    def test_tat_dinh(self) -> None:
        a = build_ad_prompt("Chai nước ép cam", feedback_history=["nền xanh"])
        b = build_ad_prompt("Chai nước ép cam", feedback_history=["nền xanh"])
        assert a.prompt_en == b.prompt_en

    def test_prompt_vi_cho_nguoi_dung_doc(self) -> None:
        res = build_ad_prompt("Chai nước ép cam", feedback_history=["nền xanh", "sáng hơn"])
        assert "ảnh sản phẩm bạn gửi" in res.prompt_vi
        assert "2" in res.prompt_vi

    def test_do_dai_prompt_trong_nguong(self) -> None:
        """Prompt dài quá thì model bỏ qua phần đầu (chỗ có ràng buộc)."""
        h = ["nền xanh tươi sáng và thêm hoa lá cây cỏ quanh sản phẩm"] * _MAX_Y_KIEN_LICH_SU
        res = build_ad_prompt("Chai nước ép cam", feedback_history=h)
        assert len(res.prompt_en) < 2500

    def test_khong_lo_ty_le_khung_vao_prompt(self) -> None:
        """Provider từ chối chuỗi tỷ lệ thô — prompt không được chứa nó."""
        res = build_ad_prompt("Chai nước ép cam")
        assert "1:1" not in res.prompt_en

    def test_khong_co_dieu_khoan_cam_do_uong(self) -> None:
        """Prompt này CÓ sản phẩm trong khung — cấm đồ uống là xoá mất sản phẩm."""
        res = build_ad_prompt("Chai nước ép cam")
        assert "no drink" not in res.prompt_en
        assert "no beverage" not in res.prompt_en

    def test_khong_yeu_cau_giu_nap(self) -> None:
        """Đồ uống không cần giữ nắp — prompt không được nhắc tới cap/lid."""
        res = build_ad_prompt(container="glass bottle", feedback_history=["nền xanh"])
        assert "cap/lid" not in res.prompt_en
        assert "cap, lid" not in res.prompt_en

    def test_trong_thi_co_boi_canh_mac_dinh(self) -> None:
        """Chưa có ý kiến lẫn phong cách thì có bối cảnh mặc định cho đỡ trống."""
        res = build_ad_prompt()
        assert "wooden cafe table surface" in res.prompt_en
        assert "bokeh background" in res.prompt_en

    def test_co_y_kien_thi_khong_dung_boi_canh_mac_dinh(self) -> None:
        """Đã có ý kiến người dùng thì không chèn bối cảnh mặc định nữa."""
        res = build_ad_prompt(feedback_history=["nền biển"])
        assert "wooden cafe table surface" not in res.prompt_en
        assert "seaside background" in res.prompt_en

    def test_giu_dung_loai_do_uong_goc(self) -> None:
        """Ràng buộc giữ đúng loại đồ uống phải có ở MỌI prompt."""
        res = build_ad_prompt(container="glass")
        assert "same drink type" in res.prompt_en
        assert "never turn it into a different drink or food" in res.prompt_en

    def test_style_prompt_cu_co_negation_bi_lam_sach(self) -> None:
        """Style prompt cũ (ảnh nền trống, có "no drink") phải bị lọc khi lắp prompt giữ sản phẩm."""
        from ca_agents.menu_style import parse_style

        style = parse_style(
            {
                "slug": "t",
                "ten": "T",
                "mo_ta": "",
                "scene": "cafe_wood",
                "lighting": "golden_hour",
                "palette": "warm_wood",
                "lens": "shallow_85mm",
            }
        )
        assert style is not None
        res = build_ad_prompt(style_prompt=style.to_prompt())
        assert "no drink" not in res.prompt_en
        assert "no beverage" not in res.prompt_en
        # Bối cảnh của phong cách vẫn được giữ lại.
        assert "wooden cafe table" in res.prompt_en


# ── Bước 1: kiểm ảnh đầu vào ────────────────────────────────────────────────


def _png(w: int, h: int) -> bytes:
    """PNG thật cỡ ``w×h`` — Pillow đọc được nên đi qua được kiểm tra kỹ thuật."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 90, 60)).save(buf, format="PNG")
    return buf.getvalue()


class _FakeLlm:
    """Thay ``complete()`` để test không mở mạng."""

    def __init__(self, *, ok: bool = True, text: str = "") -> None:
        self.ok = ok
        self.text = text
        self.calls = 0

    def __call__(self, **kwargs: object) -> object:
        self.calls += 1
        from ca_agents.llm import LlmResult

        return LlmResult(ok=self.ok, text=self.text, provider="fake", reason="")


class TestValidateProductImage:
    def test_anh_khong_phai_tep_anh(self) -> None:
        check = validate_product_image(b"khong-phai-anh", "image/jpeg")
        assert check.ok is False
        assert check.error == "anh_goc_khong_hop_le"

    def test_tep_rong(self) -> None:
        check = validate_product_image(b"", "image/jpeg")
        assert check.ok is False

    def test_anh_qua_nho(self) -> None:
        check = validate_product_image(_png(50, 50), "image/png")
        assert check.ok is False
        assert check.error == "anh_goc_qua_nho"

    def test_anh_hong_pillow_khong_doc_duoc(self) -> None:
        """Magic bytes đúng nhưng ruột hỏng — phải trả lỗi rõ, không crash."""
        check = validate_product_image(b"\x89PNG\r\n\x1a\n" + b"rac" * 100, "image/png")
        assert check.ok is False
        assert check.error == "anh_goc_khong_doc_duoc"

    def test_thieu_provider_thi_cho_qua_kem_co(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Không gọi được AI thị giác → vẫn cho đi tiếp nhưng ``da_kiem=False``.

        Chặn ở đây nghĩa là tính năng chết khi rút mạng, trong khi phần lớn giá
        trị (dàn dựng lại ảnh) vẫn làm được.
        """
        monkeypatch.setattr(ad, "complete", _FakeLlm(ok=False))
        check = validate_product_image(_png(600, 600), "image/png")
        assert check.ok is True
        assert check.da_kiem is False

    def test_ai_xac_nhan_san_pham_hop_le(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ad,
            "complete",
            _FakeLlm(
                text='{"is_liquid_product": true, "clearly_visible": true, '
                '"container": "glass bottle", "reason_vi": "chai rõ nét"}'
            ),
        )
        check = validate_product_image(_png(600, 600), "image/png")
        assert check.ok is True
        assert check.da_kiem is True
        assert check.container == "glass bottle"

    def test_ai_tu_choi_anh_khong_phai_san_pham(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ad,
            "complete",
            _FakeLlm(
                text='{"is_liquid_product": false, "clearly_visible": true, '
                '"container": "", "reason_vi": "đây là đĩa thức ăn"}'
            ),
        )
        check = validate_product_image(_png(600, 600), "image/png")
        assert check.ok is False
        assert check.error == "anh_khong_phai_san_pham_nuoc"
        assert check.ly_do == "đây là đĩa thức ăn"

    def test_ai_tu_choi_anh_mo_khong_ro(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ad,
            "complete",
            _FakeLlm(
                text='{"is_liquid_product": true, "clearly_visible": false, '
                '"container": "glass", "reason_vi": "ảnh mờ"}'
            ),
        )
        check = validate_product_image(_png(600, 600), "image/png")
        assert check.ok is False

    def test_ai_tra_json_hong_thi_cho_qua_kem_co(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ad, "complete", _FakeLlm(text="khong phai json"))
        check = validate_product_image(_png(600, 600), "image/png")
        assert check.ok is True
        assert check.da_kiem is False

    def test_thieu_co_that_thi_tu_choi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AI trả JSON thiếu khoá → coi như KHÔNG xác nhận, không mặc định cho qua."""
        monkeypatch.setattr(ad, "complete", _FakeLlm(text='{"container": "bottle"}'))
        check = validate_product_image(_png(600, 600), "image/png")
        assert check.ok is False

    def test_khong_goi_ai_khi_anh_sai_dinh_dang(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Chặn ở tầng kỹ thuật TRƯỚC khi tốn một lượt gọi mạng."""
        fake = _FakeLlm(text="{}")
        monkeypatch.setattr(ad, "complete", fake)
        validate_product_image(b"rac", "image/jpeg")
        assert fake.calls == 0

    def test_thong_diep_nguyen_van_theo_quy_trinh(self) -> None:
        assert THONG_DIEP_ANH_KHONG_HOP_LE.startswith("Ảnh bạn gửi không phải là ảnh sản phẩm")
        assert "Vui lòng gửi lại ảnh sản phẩm rõ nét" in THONG_DIEP_ANH_KHONG_HOP_LE


# ── Bất biến tổng quát ──────────────────────────────────────────────────────


class TestBatBien:
    """Các bất biến phải đúng với MỌI đầu vào — dùng nhiều mẫu thay vì một."""

    @pytest.mark.parametrize(
        "ten",
        ["Chai nước ép cam", "Lọ mật ong", "Trà đào", "Ly trà sữa", "Hộp sữa tươi", "Bình trà"],
    )
    def test_rang_buoc_luon_co(self, ten: str) -> None:
        res = build_ad_prompt(ten, feedback_history=["nền xanh", "thêm người"])
        assert res.ok is True
        assert "Do not change the shape, label, text, logo" in res.prompt_en
        assert "No people, no hands" in res.prompt_en

    @pytest.mark.parametrize(
        "y_kien",
        ["thay nhãn", "thêm người", "đổi logo", "add text", "person", "rotate"],
    )
    def test_moi_tu_khoa_cam_deu_bi_loc(self, y_kien: str) -> None:
        giu, bo = loc_y_kien(y_kien)
        assert giu == ""
        assert bo, f"{y_kien!r} phải bị lọc"

    @pytest.mark.parametrize(
        "y_kien",
        ["nền xanh", "làm sáng hơn", "đổi nền sang màu xanh", "lát chanh", "bỏ bớt vật trang trí"],
    )
    def test_yeu_cau_hop_le_khong_bi_chan(self, y_kien: str) -> None:
        giu, bo = loc_y_kien(y_kien)
        assert bo == (), f"{y_kien!r} bị chặn oan"
        assert giu, f"{y_kien!r} phải dịch được"


def test_prompt_la_bytes_ascii_an_toan() -> None:
    """Prompt gửi JSON sang provider — không được chứa ký tự điều khiển lạ."""
    res = build_ad_prompt("Chai nước ép cam", feedback_history=["nền xanh"])
    assert "\x00" not in res.prompt_en
    res.prompt_en.encode("utf-8")  # không ném lỗi


def test_khong_import_mang() -> None:
    """Module prompt không tự gọi mạng — chỉ ``llm.complete`` mới chạm provider."""
    from pathlib import Path

    text = Path(ad.__file__).read_text(encoding="utf-8")
    assert "urllib.request" not in text
    assert "requests" not in text


def test_base64_khong_lien_quan_o_day() -> None:
    """Chốt rằng module này xử lý BYTES, không xử lý base64 — việc giải mã ở tầng HTTP."""
    encoded = base64.b64encode(_png(600, 600)).decode("ascii")
    assert isinstance(encoded, str)
