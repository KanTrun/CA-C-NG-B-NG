"""Generate synthetic seed (25 NV, role-slot week pattern, 8 weeks) + golden fixtures.

All outputs are labeled synthetic — not real cafe PII.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed"
GOLDEN_MSG = ROOT / "data" / "golden" / "messages"
GOLDEN_TKB = ROOT / "data" / "golden" / "tkb"
RNG = random.Random(42)

SKILLS = ["pha_che", "thu_ngan", "phuc_vu", "kho"]
# Tên hiển thị demo — không phải PII thật; đủ để UI lịch/ca đọc được.
TEN_NHAN_VIEN = (
    "Lan Nguyễn",
    "Hùng Trần",
    "Minh Phạm",
    "An Lê",
    "Bảo Hoàng",
    "Chi Vũ",
    "Dũng Đặng",
    "Em Bùi",
    "Giang Hồ",
    "Hạnh Mai",
    "Khoa Đỗ",
    "Linh Ngô",
    "My Tạ",
    "Nam Lý",
    "Oanh Phan",
    "Phúc Trịnh",
    "Quân Lương",
    "Rosa Võ",
    "Sơn Hà",
    "Thảo Dương",
    "Uyên Cao",
    "Vy Đinh",
    "Xuân Lâm",
    "Yến Kiều",
    "Khôi Nhật",
)
INTENTS = [
    "xin_nghi",
    "doi_ca",
    "nhan_ca",
    "bao_tre",
    "cap_nhat_tkb",
    "khac",
]

# ── Mốc thời gian fixture ────────────────────────────────────────────────
# Tất định: KHÔNG lấy giờ hệ thống. Tuần 1 bắt đầu thứ Hai 2026-01-05.
BASE_NGAY = date(2026, 1, 5)
# Mốc dùng để nói một việc treo là "quá hạn" hay "đang chờ". Ghi thẳng vào
# dữ liệu để người đọc không phải đoán theo giờ máy.
MOC_XEM = "2026-02-28T22:00:00"
THU_TEN = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
NGUON_FIXTURE = "mo_phong_fixture"

# 8 mặt hàng trong `danh_muc` của mẫu phiếu mo_quan / dong_quan.
DANH_MUC = ["sua_tuoi", "ca_phe_hat", "tra", "duong", "ly_nhua", "ong_hut", "banh", "da"]
TEN_HANG = {
    "sua_tuoi": ("sữa tươi", "hộp"),
    "ca_phe_hat": ("cà phê hạt", "kg"),
    "tra": ("trà", "gói"),
    "duong": ("đường", "kg"),
    "ly_nhua": ("ly nhựa", "cái"),
    "ong_hut": ("ống hút", "cái"),
    "banh": ("bánh", "cái"),
    "da": ("đá", "bao"),
}
# (tồn đầu ca, tiêu thụ min, tiêu thụ max, nhập min, nhập max)
MUC_HANG = {
    "sua_tuoi": (24, 6, 14, 0, 12),
    "ca_phe_hat": (8, 1, 3, 0, 4),
    "tra": (12, 1, 4, 0, 6),
    "duong": (10, 1, 3, 0, 5),
    "ly_nhua": (300, 60, 140, 0, 200),
    "ong_hut": (400, 50, 160, 0, 200),
    "banh": (40, 8, 26, 0, 30),
    "da": (20, 4, 12, 0, 15),
}
# Cột đếm tay độc lập chỉ có ở tuần 1, cho 5 mặt hàng — đủ để tính sai số #9
# trên một tuần, không giả vờ rằng cả 8 tuần đều được đếm tay.
TUAN_DEM_TAY = 1
HANG_DEM_TAY = DANH_MUC[:5]


def _ngay(tuan: int, ngay_offset: int) -> date:
    return BASE_NGAY + timedelta(days=(tuan - 1) * 7 + (ngay_offset - 1))


def _luc(tuan: int, ngay_offset: int, gio: str) -> str:
    return f"{_ngay(tuan, ngay_offset).isoformat()}T{gio}:00"


def build_staff(n: int = 25) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        ten = TEN_NHAN_VIEN[i - 1] if i <= len(TEN_NHAN_VIEN) else f"Nhân viên {i:02d}"
        out.append(
            {
                "id": f"nv_{i:02d}",
                "ten": ten,
                "ky_nang": RNG.sample(SKILLS, k=RNG.randint(1, 3)),
                "la_sinh_vien": i <= 20,
                "synthetic": True,
            }
        )
    return out


def build_shifts_for_week(week: int) -> list[dict]:
    """Role-slot / tuần: 7 ngày × 3 khung × nhiều vai trò.

    Mỗi khung giờ có nhiều vai trò cùng lúc — mỗi vai trò là một role-slot
    riêng để solver C01/C02 khớp kỹ năng và đếm đủ người THEO VAI TRÒ.
    Quán cà phê nên pha_che luôn là vai trò chính của mọi khung (2 người);
    khung sáng/chiều thêm thu_ngan + phuc_vu, khung tối thêm cả kho
    (kiểm kê cuối ngày). 21 role-slot đầu (w{week}_c01..c21) giữ đúng
    thứ tự 3 vai trò đầu mỗi khung — ID không đổi để tests, seed demo và
    fixture professional (fx_ca_01..21) vẫn khớp; kho tối từ c22.
    """
    slots = [("sang", "07:00", "12:00"), ("chieu", "12:00", "17:00"), ("toi", "17:00", "22:00")]
    phu_theo_khung = {
        "sang": [("thu_ngan", 1), ("phuc_vu", 1)],
        "chieu": [("thu_ngan", 1), ("phuc_vu", 1)],
        "toi": [("thu_ngan", 1), ("phuc_vu", 1), ("kho", 1)],
    }
    out = []
    idx = 1
    for d in range(1, 8):
        for ten, start, end in slots:
            # Vai trò chính: pha_che — quán cà phê không thể mở ca không ai pha.
            out.append(
                {
                    "id": f"w{week}_c{idx:02d}",
                    "ngay_offset": d,
                    "khung": ten,
                    "bat_dau": start,
                    "ket_thuc": end,
                    "vi_tri": "pha_che",
                    "so_nguoi_toi_thieu": 2,
                    "synthetic": True,
                }
            )
            idx += 1
            # Vai trò phụ của khung.
            for vi_tri, so_nguoi in phu_theo_khung[ten]:
                out.append(
                    {
                        "id": f"w{week}_c{idx:02d}",
                        "ngay_offset": d,
                        "khung": ten,
                        "bat_dau": start,
                        "ket_thuc": end,
                        "vi_tri": vi_tri,
                        "so_nguoi_toi_thieu": so_nguoi,
                        "synthetic": True,
                    }
                )
                idx += 1
    return out


def build_history(staff: list[dict], weeks: int = 8) -> list[dict]:
    hist = []
    for w in range(1, weeks + 1):
        shifts = build_shifts_for_week(w)
        assign = {}
        for sh in shifts:
            # Chỉ xếp NV có kỹ năng khớp vai trò của role-slot — lịch sử 8 tuần
            # phải là lịch khả thi để nợ công bằng phản ánh đúng nghiệp vụ.
            eligible = [c for c in staff if sh["vi_tri"] in c.get("ky_nang", [])]
            pool = eligible if eligible else staff
            need = sh["so_nguoi_toi_thieu"]
            chosen = RNG.sample(pool, k=min(need, len(pool)))
            assign[sh["id"]] = [c["id"] for c in chosen]
        hist.append({"tuan": w, "tuan_iso": f"2026-W{w:02d}", "ca": shifts, "phan_cong": assign})
    return hist


def build_messages(n: int = 200) -> list[dict]:
    templates = {
        "xin_nghi": "em xin nghỉ ca {khung} ngày {thu} ạ",
        "doi_ca": "anh cho em đổi ca {khung} với bạn được không",
        "nhan_ca": "em nhận ca {khung} bị thiếu người nhé",
        "bao_tre": "em xin phép đến trễ 15 phút ca {khung}",
        "cap_nhat_tkb": "tuần này em học {thu} sáng, nhờ cập nhật TKB",
        "khac": "máy pha bên em hơi kêu lạ ca {khung}",
    }
    thu = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    khung = ["sang", "chieu", "toi"]
    rows = []
    for i in range(1, n + 1):
        intent = INTENTS[i % len(INTENTS)]
        text = templates[intent].format(khung=RNG.choice(khung), thu=RNG.choice(thu))
        rows.append(
            {
                "id": f"msg_{i:03d}",
                "text": text,
                "intent": intent,
                "annotator_a": intent,
                "annotator_b": intent if i % 17 else "khac",
                "synthetic": True,
            }
        )
    agree = sum(1 for r in rows if r["annotator_a"] == r["annotator_b"])
    kappa_proxy = agree / len(rows)
    meta = {
        "n": n,
        "simple_agreement": round(kappa_proxy, 3),
        "note": "synthetic dual labels — not real Cohen kappa from humans",
        "synthetic": True,
    }
    return rows, meta


def build_tkb(n: int = 50) -> None:
    GOLDEN_TKB.mkdir(parents=True, exist_ok=True)
    index = []
    for i in range(1, n + 1):
        nv = f"nv_{(i % 25) + 1:02d}"
        # synthetic busy blocks Mon/Wed/Fri mornings
        blocks = [
            {"thu": "T2", "start": "07:30", "end": "11:00"},
            {"thu": "T4", "start": "07:30", "end": "11:00"},
            {"thu": "T6", "start": "13:00", "end": "16:30"},
        ]
        if i % 2 == 0:
            blocks.append({"thu": "T7", "start": "08:00", "end": "11:30"})
        svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'>
<rect width='100%' height='100%' fill='#f7f2ea'/>
<text x='24' y='40' font-size='20' font-family='sans-serif'>TKB synthetic {i:02d} — {nv}</text>
"""
        y = 80
        for b in blocks:
            label = f"{b['thu']} {b['start']}-{b['end']}"
            svg += f"<text x='24' y='{y}' font-size='16' font-family='monospace'>{label}</text>\n"
            y += 28
        svg += "</svg>\n"
        name = f"tkb_{i:02d}.svg"
        (GOLDEN_TKB / name).write_text(svg, encoding="utf-8")
        gt = {
            "id": f"tkb_{i:02d}",
            "file": name,
            "nhan_vien_id": nv,
            "khoang_ban": blocks,
            "synthetic": True,
        }
        (GOLDEN_TKB / f"tkb_{i:02d}.json").write_text(
            json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        index.append(gt)
    # Giữ lại mục do người thêm tay (ví dụ `tkb_blur_01` — ảnh mờ để cổng
    # VF-TRACE có việc làm). Bản trước ghi đè `index.json` nên mỗi lần chạy
    # `make seed` là mục đó bay mất, kéo số #11 từ 1/51 xuống 0/50 mà không ai
    # sửa gì. Bộ sinh chỉ được quyền ghi lại mục nó tự sinh.
    da_sinh = {str(x["id"]) for x in index}
    them_tay: list[dict[str, Any]] = []
    cu = GOLDEN_TKB / "index.json"
    if cu.exists():
        try:
            truoc = json.loads(cu.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            truoc = {}
        them_tay = [
            x
            for x in (truoc.get("items") or [])
            if isinstance(x, dict) and str(x.get("id")) not in da_sinh
        ]
    items = [*index, *them_tay]
    cu.write_text(
        json.dumps(
            {"n": len(items), "items": items, "them_tay": len(them_tay), "synthetic": True},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# ── Việc treo ────────────────────────────────────────────────────────────
TREO_NOI_DUNG = [
    "Máy pha kêu lạ khi xay, cần gọi bảo trì trước ca tối",
    "Hết ống hút cỡ lớn, phải mượn tạm quán bên",
    "Tủ mát tầng dưới không đủ lạnh, sữa tươi để ngoài 2 tiếng",
    "Khách để quên áo khoác ở bàn 4, đã cất vào kho",
    "Vòi rửa bồn trong kêu và chảy yếu, cần thợ xem",
    "Bảng giá món mới chưa in, vẫn dùng bảng cũ",
    "Máy tính tiền in mờ, sắp phải thay giấy in",
    "Thùng rác sau quán chưa ai mang ra, để lại cho ca sau",
    "Ổ điện góc quầy bị lỏng, tạm dán băng dính cảnh báo",
    "Đèn bảng hiệu nhấp nháy từ 19h, chưa gọi được điện",
    "Hộp sữa lô mới có mùi lạ, đã tách riêng chờ đổi",
    "Khay đá bị nứt, đá chảy nước xuống sàn",
    "Cân cà phê lệch 20g so với lần trước, cần chuẩn lại",
    "Cửa kính mặt tiền dính vết dầu, chưa lau kịp",
    "Wifi khu bàn ngoài mất sóng, khách phàn nàn 3 lần",
    "Nhà vệ sinh hết giấy, đã lấy tạm 1 cuộn từ kho",
    "Thẻ giữ xe số 12 mất, đang dùng phiếu viết tay",
    "Bình ủ trà giữ nhiệt kém, trà nguội sau 1 tiếng",
]
TREO_TRANG_THAI = ["xong", "dang_cho", "qua_han"]
TREO_MAU = ["mo_quan", "ban_giao_ca", "dong_quan"]


def build_viec_treo(staff: list[dict], ca21: list[dict]) -> list[dict[str, Any]]:
    """18 việc treo, đủ 3 trạng thái: đã xong · đang chờ · quá hạn.

    Ba nhóm đúng như số #8 cần đọc:
    - `xong` — ca sau đã nhận và đã làm xong (`ca_sau_nhan_luc` + `xong_luc`);
    - `dang_cho` — một nửa đã có ca sau nhận nhưng chưa làm xong, nửa còn lại
      vẫn còn mở, chưa ai nhận (`ca_sau_nhan_luc = None`);
    - `qua_han` — hạn đã trôi qua mốc `MOC_XEM` mà chưa ai nhận.
    """
    out: list[dict[str, Any]] = []
    for i, noi_dung in enumerate(TREO_NOI_DUNG):
        # Bước 5 nguyên tố cùng nhau với 21 nên 18 việc rơi vào 18 ca khác nhau;
        # bước 3 (bản trước) chỉ chạm 7 ca, trang /treo trông như dồn một chỗ.
        ca = ca21[(i * 5) % len(ca21)]
        nguoi = staff[(i * 2) % len(staff)]
        nhan = staff[(i * 2 + 7) % len(staff)]
        off = int(ca["ngay_offset"])
        trang_thai = TREO_TRANG_THAI[i % 3]
        ca_sau_nhan_luc: str | None = None
        if trang_thai == "xong":
            han = _luc(1, off, "18:00")
            xong_luc: str | None = _luc(1, off, "17:20")
            ca_sau_nhan_luc = _luc(1, off, "17:05")
        elif trang_thai == "dang_cho":
            han = _luc(10, off, "18:00")
            xong_luc = None
            # Một nửa số việc đang chờ đã có ca sau nhận, nửa kia còn bỏ ngỏ.
            if i % 2 == 0:
                ca_sau_nhan_luc = _luc(1, off, "17:05")
        else:
            han = _luc(1, off, "18:00")
            xong_luc = None
        out.append(
            {
                "id": f"treo_fx{i + 1:02d}",
                "phieu_id": f"ph_fx{i + 1:02d}",
                "mau": TREO_MAU[i % len(TREO_MAU)],
                "ca_id": ca["id"],
                "khung": ca["khung"],
                "thu": THU_TEN[off],
                "nv_id": nguoi["id"],
                "nhan_vien": nguoi["id"],
                "nguoi_nhan": nhan["id"],
                "noi_dung": noi_dung,
                "han": han,
                "trang_thai": trang_thai,
                "tre_han": trang_thai == "qua_han",
                "moc_tinh_han": MOC_XEM,
                "created_at": _luc(1, off, ca["bat_dau"][:5]),
                "ca_sau_da_nhan": ca_sau_nhan_luc is not None,
                "ca_sau_nhan_luc": ca_sau_nhan_luc,
                "xong_luc": xong_luc,
                "nguon": NGUON_FIXTURE,
                "synthetic": True,
            }
        )
    return out


# ── Hộp thư ràng buộc ────────────────────────────────────────────────────
# (agent, tóm tắt, loại ràng buộc, ý định AG-MSG)
# `y_dinh` là nhãn AG-MSG *thật* của câu tóm tắt: bộ kiểm
# `test_inbox_du_sau_y_dinh_ag_msg` chấm lại bằng `ca_agents.ag_msg.classify`,
# nên không thể dán nhãn cho đẹp mà câu chữ không khớp từ khoá.
# Đủ 6 ý định: xin_nghi · doi_ca · nhan_ca · bao_tre · cap_nhat_tkb · khac.
INBOX_MUC = [
    ("ag_msg", "Bạn nv_04 xin nghỉ ca tối thứ Sáu vì có lịch thi", "khong_xep", "xin_nghi"),
    (
        "ag_handover",
        "Ca sáng bàn giao: máy pha cần vệ sinh sâu trước ca chiều",
        "buoc_them",
        "khac",
    ),
    (
        "ag_tkb",
        "TKB mới của nv_07: sáng T2 và T4 đi học, không xếp được",
        "khong_xep",
        "cap_nhat_tkb",
    ),
    (
        "ag_waste",
        "Ghi chú hao phí lặp ở thứ Ba — đề nghị giảm lượng nhập sữa",
        "nguong_ton",
        "khac",
    ),
    ("ag_msg", "nv_11 nhận ca chiều Chủ nhật nếu còn thiếu người", "co_the_xep", "nhan_ca"),
    ("ag_handover", "Bàn giao ca tối: còn 3 bàn chưa dọn, đã nhắc ca sau", "buoc_them", "khac"),
    (
        "ag_tkb",
        "nv_02 cập nhật TKB: chiều T6 đi học, ca chiều T6 nên tránh",
        "khong_xep",
        "cap_nhat_tkb",
    ),
    ("ag_msg", "nv_15 xin đổi ca sáng T7 với nv_18, hai bên đã đồng ý", "doi_ca", "doi_ca"),
    ("ag_waste", "Đá chảy nhiều vào ca trưa — xem lại giờ nhập đá", "nguong_ton", "khac"),
    ("ag_handover", "Ca chiều báo thiếu 1 người pha chế mỗi thứ Bảy", "nhu_cau_ca", "khac"),
    ("ag_msg", "nv_09 báo đến trễ 15 phút ca sáng vì xe hỏng", "bao_tre", "bao_tre"),
    ("ag_tkb", "TKB nv_21 trống cả tuần — có thể xếp linh hoạt", "co_the_xep", "cap_nhat_tkb"),
    ("ag_waste", "Bánh còn dư cuối ca tối 4 ngày liền, giảm nhập bánh", "nguong_ton", "khac"),
    ("ag_msg", "nv_06 xin không xếp ca tối liên tiếp 3 ngày", "khong_xep", "khac"),
]
# ≥2 mục `cho_duyet` để trang hộp thư luôn có việc cho người quyết.
INBOX_TRANG_THAI = [
    "cho_duyet",
    "duyet",
    "cho_duyet",
    "duyet",
    "tu_choi",
    "duyet",
    "cho_duyet",
    "duyet",
    "cho_duyet",
    "cho_duyet",
    "tu_choi",
    "duyet",
    "cho_duyet",
    "duyet",
]


def build_inbox(ca21: list[dict]) -> list[dict[str, Any]]:
    """~14 ràng buộc trích từ tin nhắn / bàn giao, chờ người quyết."""
    out: list[dict[str, Any]] = []
    for i, (agent, tom_tat, loai, y_dinh) in enumerate(INBOX_MUC):
        ca = ca21[(i * 5) % len(ca21)]
        out.append(
            {
                "id": f"in_fx{i + 1:02d}",
                "agent": agent,
                "tom_tat": tom_tat,
                "y_dinh": y_dinh,
                "do_tin_cay": round(RNG.uniform(0.55, 0.95), 2),
                "trang_thai": INBOX_TRANG_THAI[i],
                "rang_buoc": {
                    "loai": loai,
                    "ca_id": ca["id"],
                    "thu": THU_TEN[int(ca["ngay_offset"])],
                    "khung": ca["khung"],
                },
                "ca_id": ca["id"],
                "created_at": _luc(1, int(ca["ngay_offset"]), "08:30"),
                "nguon": NGUON_FIXTURE,
                "synthetic": True,
            }
        )
    return out


# ── Luật cẩm nang ────────────────────────────────────────────────────────
# `loai` dùng đúng enum máy đọc trong ca_gates.vf_rule.LOAI_HOP_LE;
# `loai_ho_so` giữ tên dài trong hồ sơ §9.1 để tra ngược.
LOAI_HO_SO = {
    "nhu_cau_ca": "nhu_cau_ca",
    "nguong_ton": "nguong_ton",
    "buoc_phieu": "buoc_phieu",
    "ghep_ky_nang": "ghep_ky_nang",
    "hao_hut": "nguyen_nhan_hao_hut",
}

LUAT_MAU: list[dict[str, Any]] = [
    {
        "id": "luat_fx_t7_chieu_pha_che",
        "loai": "nhu_cau_ca",
        "cau": "Thứ Bảy ca chiều cần 3 người pha chế, không phải 2",
        "dieu_kien": {"thu": "T7", "khung": "chieu", "vi_tri": "pha_che", "so_nguoi": 3},
        "trang_thai": "hieu_luc",
        "tap_su": 5,
        "dung": 9,
        "ghi_de": 1,
    },
    {
        "id": "luat_fx_cn_toi_thieu_nguoi",
        "loai": "nhu_cau_ca",
        "cau": "Chủ nhật ca tối hay đông, xếp thêm 1 người phục vụ",
        "dieu_kien": {"thu": "CN", "khung": "toi", "vi_tri": "phuc_vu", "so_nguoi": 3},
        "trang_thai": "cho_chu_quan",
        "tap_su": 5,
        "dung": 6,
        "ghi_de": 1,
    },
    {
        "id": "luat_fx_nguong_sua_tuoi",
        "loai": "nguong_ton",
        "cau": "Sữa tươi còn dưới 6 hộp thì đặt thêm ngay trong ca sáng",
        "dieu_kien": {"nguong": 6},
        "trang_thai": "hieu_luc",
        "tap_su": 5,
        "dung": 11,
        "ghi_de": 1,
    },
    {
        "id": "luat_fx_nguong_ly_nhua",
        "loai": "nguong_ton",
        "cau": "Ly nhựa còn dưới 80 cái thì nhắc nhập trước ca tối",
        "dieu_kien": {"nguong": 80},
        "trang_thai": "qua_vf_rule",
        "tap_su": 0,
        "dung": 0,
        "ghi_de": 0,
    },
    {
        "id": "luat_fx_buoc_kiem_ke_dau_ca",
        "loai": "buoc_phieu",
        "cau": "Ca sáng phải kiểm kê 8 mặt hàng trước khi mở bán",
        "dieu_kien": {"ma_buoc": "kiem_ke", "khung": "sang"},
        "trang_thai": "hieu_luc",
        "tap_su": 5,
        "dung": 13,
        "ghi_de": 2,
    },
    {
        "id": "luat_fx_buoc_can_hat",
        "loai": "buoc_phieu",
        "cau": "Cân cà phê hạt còn lại vào cuối mỗi ca tối",
        "dieu_kien": {"ma_buoc": "can_hat", "khung": "toi"},
        "trang_thai": "tu_choi",
        "tap_su": 4,
        "dung": 0,
        "ghi_de": 0,
    },
    {
        "id": "luat_fx_ghep_ca_toi",
        "loai": "ghep_ky_nang",
        "cau": "Ca tối cần ít nhất một người đã làm trên 3 tháng",
        "dieu_kien": {"khung": "toi", "thang_kinh_nghiem": 3},
        "trang_thai": "hieu_luc",
        "tap_su": 5,
        "dung": 12,
        "ghi_de": 1,
    },
    {
        "id": "luat_fx_thai_do_bi_loai",
        "loai": "ghep_ky_nang",
        "cau": "Bạn nv_03 lười nên đừng xếp ca cuối tuần",
        "dieu_kien": {"thu": "T7", "khung": "chieu"},
        "trang_thai": "loai",
        "vf_rule": "luat_ve_nguoi",
        "tap_su": 0,
        "dung": 0,
        "ghi_de": 0,
    },
    {
        "id": "luat_fx_truong_la_bi_loai",
        "loai": "nguong_ton",
        "cau": "Khi tồn bánh thấp thì ưu tiên bạn quen tay nhất đứng quầy",
        "dieu_kien": {"nguong": 5, "ten_nhan_vien": "nv_07"},
        "trang_thai": "loai",
        "vf_rule": "truong_khong_ton_tai:['ten_nhan_vien']",
        "tap_su": 0,
        "dung": 0,
        "ghi_de": 0,
    },
    {
        "id": "luat_fx_hao_hut_thu_ba",
        "loai": "hao_hut",
        "cau": "Thứ Ba hay hao sữa tươi, giảm lượng nhập buổi sáng",
        "dieu_kien": {"thu": "T3", "nguong": 4},
        "trang_thai": "tu_tat",
        "tap_su": 5,
        "dung": 3,
        "ghi_de": 2,
    },
    {
        "id": "luat_fx_hao_hut_da_trua",
        "loai": "hao_hut",
        "cau": "Đá chảy nhiều vào ca chiều, nhập đá hai lần trong ngày",
        "dieu_kien": {"khung": "chieu", "nguong": 3},
        "trang_thai": "qua_vf_rule",
        "tap_su": 0,
        "dung": 0,
        "ghi_de": 0,
    },
    {
        "id": "luat_fx_buoc_ban_giao_anh",
        "loai": "buoc_phieu",
        "cau": "Bàn giao ca phải có ảnh quầy trước khi đóng phiếu",
        "dieu_kien": {"ma_buoc": "anh_quay"},
        "trang_thai": "de_xuat",
        "tap_su": 0,
        "dung": 0,
        "ghi_de": 0,
    },
]

BUOC_THEO_TRANG_THAI = {
    "de_xuat": 3,
    "loai": 4,
    "qua_vf_rule": 4,
    "truot_tap_su": 5,
    "du_tap_su": 5,
    "cho_chu_quan": 6,
    "tu_choi": 6,
    "hieu_luc": 7,
    "tu_tat": 8,
}


def build_luat(ghi_nhan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """12 luật, đủ 5 loại §9.1 và rải trên mọi trạng thái vòng đời 8 bước."""
    out: list[dict[str, Any]] = []
    tong_bang_chung = max(len(ghi_nhan), 4)
    for i, mau in enumerate(LUAT_MAU):
        tap_su_tong = 5
        tap_su_dung = int(mau["tap_su"])
        tap_su = [
            {
                "he_thong": "gia_tri_de_xuat",
                "nguoi": "gia_tri_de_xuat" if k < tap_su_dung else "nguoi_ghi_de",
                "dung": k < tap_su_dung,
            }
            for k in range(tap_su_tong if tap_su_dung else 0)
        ]
        dung = int(mau["dung"])
        ghi_de = int(mau["ghi_de"])
        tong = dung + ghi_de
        so_bang_chung = 3 + (i % 3)
        luat: dict[str, Any] = {
            "id": mau["id"],
            "loai": mau["loai"],
            "loai_ho_so": LOAI_HO_SO[str(mau["loai"])],
            "cau": mau["cau"],
            "dieu_kien": dict(mau["dieu_kien"]),
            "bang_chung": [str((i * 3 + k) % tong_bang_chung) for k in range(so_bang_chung)],
            "buoc": BUOC_THEO_TRANG_THAI[str(mau["trang_thai"])],
            "trang_thai": mau["trang_thai"],
            "vf_rule": mau.get("vf_rule", "dat"),
            "tap_su": tap_su,
            "tap_su_dung": tap_su_dung,
            "tap_su_tong": tap_su_tong,
            "da_ap_dung": dung,
            "bi_ghi_de": ghi_de,
            "ap_dung": tong,
            "ghi_de": ghi_de,
            "ti_le_dung": round(dung / tong, 3) if tong else 1.0,
            "nguon": NGUON_FIXTURE,
            "synthetic": True,
        }
        if mau["trang_thai"] in {"hieu_luc", "tu_tat"}:
            luat["nguoi_duyet"] = "chu_quan"
            luat["tham_so_loi"] = dict(mau["dieu_kien"])
        if mau["trang_thai"] == "tu_choi":
            luat["nguoi_duyet"] = "quan_ly"
            luat["ly_do_tu_choi"] = "Quán chưa muốn thêm bước vào ca tối"
        out.append(luat)
    return out


# ── Hao phí ──────────────────────────────────────────────────────────────
NGUYEN_NHAN = [
    "pha sai",
    "roi_do",
    "het_han",
    "khach_doi_mon",
    "dem_sai_dau_ca",
    "quen_tat_may",
]
# Nguyên nhân GẮN VỚI THỨ, không rải theo chỉ số: AG-WASTE gom cụm theo thứ
# (`ag_waste.extract.cluster`), nên muốn nó có việc làm thì cùng một thứ phải
# lặp lại cùng một nguyên nhân — đúng kiểu quán thật ("thứ Ba nào cũng hao sữa").
NGUYEN_NHAN_THEO_THU = {
    "T2": "dem_sai_dau_ca",
    "T3": "roi_do",
    "T4": "het_han",
    "T5": "quen_tat_may",
    "T6": "khach_doi_mon",
    "T7": "pha sai",
    "CN": "roi_do",
}
# Câu ghi chú đi theo nguyên nhân, không đi theo chỉ số — để câu chữ và nhãn
# không nói hai chuyện khác nhau. Mỗi câu đều chứa "hao"/"dư"/"hết" nên đều
# vào tầm ngắm của bộ gom cụm.
HAO_PHI_CAU = {
    "pha sai": "Đổ bỏ {n} {dv} {ten} vì pha sai, coi như hao trong ca",
    "roi_do": "Hao {n} {dv} {ten} do rơi khay lúc bàn giao ca",
    "het_han": "Bỏ {n} {dv} {ten} hết hạn dùng, ghi hao trong ca",
    "khach_doi_mon": "Khách đổi món nên dư {n} {dv} {ten}, đành bỏ",
    "dem_sai_dau_ca": "Đếm sai đầu ca nên lệch {n} {dv} {ten}, ghi hao cho khớp",
    "quen_tat_may": "Quên tắt máy qua đêm, {n} {dv} {ten} phải bỏ, tính hao",
}


def build_hao_phi(ca21: list[dict], n: int = 20) -> list[dict[str, Any]]:
    """~20 ghi chú hao phí — câu tự do, đủ để AG-WASTE gom cụm theo thứ."""
    out: list[dict[str, Any]] = []
    for i in range(n):
        ca = ca21[(i * 4 + 1) % len(ca21)]
        thu = THU_TEN[int(ca["ngay_offset"])]
        hang = DANH_MUC[i % len(DANH_MUC)]
        ten, dv = TEN_HANG[hang]
        so_luong = RNG.randint(1, 6)
        nguyen_nhan = NGUYEN_NHAN_THEO_THU[thu]
        cau = HAO_PHI_CAU[nguyen_nhan].format(n=so_luong, dv=dv, ten=ten)
        out.append(
            {
                "id": f"hp_fx{i + 1:02d}",
                "ca_id": ca["id"],
                "thu": thu,
                "khung": ca["khung"],
                "mat_hang": hang,
                "so_luong": so_luong,
                "don_vi": dv,
                "nguyen_nhan": nguyen_nhan,
                "ghi_chu": cau,
                "nv_id": f"nv_{(i % 25) + 1:02d}",
                "created_at": _luc(1, int(ca["ngay_offset"]), "20:10"),
                "nguon": NGUON_FIXTURE,
                "synthetic": True,
            }
        )
    return out


# ── Kiểm kê ──────────────────────────────────────────────────────────────
def build_kiem_ke(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kiểm kê 8 mặt hàng cho mỗi ca sáng và ca tối của 8 tuần.

    Công thức §4.3: tiêu thụ = đầu ca + nhập trong ca − cuối ca − hao hụt ghi.
    Bộ sinh đi ngược: chọn tiêu thụ thực rồi suy ra `cuoi_ca`, nên bốn cột luôn
    khớp công thức. Cột `dem_tay_doc_lap` chỉ có ở tuần 1 cho 5 mặt hàng.
    Kiểm kê theo KHUNG (một bản ghi mỗi ngày × khung sáng/tối), không theo
    role-slot — kho kiểm đếm mặt hàng một lần mỗi ca, không phải mỗi vai trò.
    """
    out: list[dict[str, Any]] = []
    for tuan_doc in history:
        tuan = int(tuan_doc["tuan"])
        phan_cong = tuan_doc.get("phan_cong", {})
        da_kiem: set[tuple[int, str]] = set()
        for ca in tuan_doc["ca"]:
            if ca["khung"] not in {"sang", "toi"}:
                continue
            khoa = (int(ca["ngay_offset"]), ca["khung"])
            if khoa in da_kiem:
                continue
            da_kiem.add(khoa)
            off = int(ca["ngay_offset"])
            nguoi = (phan_cong.get(ca["id"]) or [f"nv_{(tuan % 25) + 1:02d}"])[0]
            muc: list[dict[str, Any]] = []
            for hang in DANH_MUC:
                ton, tt_min, tt_max, nh_min, nh_max = MUC_HANG[hang]
                dau_ca = ton + RNG.randint(-2, 2) if ton > 12 else ton
                nhap = RNG.randint(nh_min, nh_max)
                hao = RNG.randint(0, 2)
                tieu_thu = RNG.randint(tt_min, tt_max)
                con = dau_ca + nhap - hao - tieu_thu
                if con < 0:
                    tieu_thu = max(0, tieu_thu + con)
                    con = dau_ca + nhap - hao - tieu_thu
                dem_tay: int | None = None
                if tuan == TUAN_DEM_TAY and hang in HANG_DEM_TAY:
                    # Lệch chỉ đặt ở mặt hàng đếm theo lô lớn. Mặt hàng đếm
                    # từng đơn vị (cà phê hạt, đường, trà) thì người đếm khó
                    # sai — nhét lệch vào đó chỉ tạo sai số 100% vô nghĩa.
                    lech = RNG.choice([-1, 0, 0, 1]) if tieu_thu >= 6 else 0
                    dem_tay = max(0, tieu_thu + lech)
                muc.append(
                    {
                        "mat_hang": hang,
                        "don_vi": TEN_HANG[hang][1],
                        "dau_ca": dau_ca,
                        "nhap_trong_ca": nhap,
                        "cuoi_ca": con,
                        "hao_hut_ghi": hao,
                        "tieu_thu_suy_ra": tieu_thu,
                        "dem_tay_doc_lap": dem_tay,
                    }
                )
            out.append(
                {
                    "id": f"kk_{ca['id']}",
                    "tuan": tuan,
                    "tuan_iso": tuan_doc["tuan_iso"],
                    "ca_id": ca["id"],
                    "ngay": _ngay(tuan, off).isoformat(),
                    "thu": THU_TEN[off],
                    "khung": ca["khung"],
                    "nguoi_dem": nguoi,
                    "cong_thuc": "tieu_thu = dau_ca + nhap_trong_ca - cuoi_ca - hao_hut_ghi",
                    "co_dem_tay": tuan == TUAN_DEM_TAY,
                    "muc": muc,
                    "nguon": NGUON_FIXTURE,
                    "synthetic": True,
                }
            )
    return out


# ── Ghi nhận sửa ─────────────────────────────────────────────────────────
def build_ghi_nhan_sua(staff: list[dict], ca21: list[dict]) -> list[dict[str, Any]]:
    """30 lần sửa lịch. Có 4 lần cùng một mẫu (thêm người vào ca chiều T7)."""
    out: list[dict[str, Any]] = []
    t7_chieu = [c for c in ca21 if c["khung"] == "chieu" and int(c["ngay_offset"]) == 6]
    ca_t7 = t7_chieu[0] if t7_chieu else ca21[0]

    def them(
        loai: str,
        ca: dict[str, Any],
        truoc: list[str],
        sau: list[str],
        ai: str,
        tuan: int,
        gio: str,
        mau_lap: str | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "id": f"gns_fx{len(out) + 1:02d}",
            "loai": loai,
            "truoc": {"ca_id": ca["id"], "nv": truoc},
            "sau": {"ca_id": ca["id"], "nv": sau},
            "ai": ai,
            "at": _luc(tuan, int(ca["ngay_offset"]), gio),
            "ca_id": ca["id"],
            "thu": THU_TEN[int(ca["ngay_offset"])],
            "khung": ca["khung"],
            "nguon": NGUON_FIXTURE,
            "synthetic": True,
        }
        if mau_lap:
            row["mau_lap"] = mau_lap
        out.append(row)

    # 4 lần cùng một mẫu: quản lý ghim thêm 1 pha chế vào ca chiều T7.
    for k in range(4):
        goc = [staff[k]["id"], staff[k + 5]["id"]]
        them(
            "pin_ca",
            ca_t7,
            goc,
            [*goc, staff[k + 10]["id"]],
            "lan",
            k + 1,
            "09:00",
            mau_lap="them_1_pha_che_t7_chieu",
        )
    # Còn lại rải trên 4 loại để bảng ghi nhận sửa có mặt đủ nhãn.
    loai_vong = ["nha_ca", "nhan_ca", "sua_lich", "pin_ca"]
    for i in range(26):
        ca = ca21[(i * 7 + 2) % len(ca21)]
        loai = loai_vong[i % len(loai_vong)]
        a = staff[(i * 3) % len(staff)]["id"]
        b = staff[(i * 3 + 4) % len(staff)]["id"]
        truoc = [a, b]
        if loai == "nha_ca":
            sau = [b]
            ai = a
        elif loai == "nhan_ca":
            truoc = [b]
            sau = [b, a]
            ai = a
        elif loai == "sua_lich":
            sau = [b, staff[(i * 3 + 9) % len(staff)]["id"]]
            ai = "lan"
        else:
            sau = [*truoc, staff[(i * 3 + 12) % len(staff)]["id"]]
            ai = "lan"
        them(loai, ca, truoc, sau, ai, (i % 8) + 1, f"{10 + (i % 8):02d}:30")
    return out


def build_tieu_thu(kiem_ke: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sổ tồn cuối tuần 8 — lấy `cuoi_ca` của ca tối cuối cùng, theo mặt hàng."""
    cuoi = [x for x in kiem_ke if x["khung"] == "toi"]
    if not cuoi:
        return []
    ca = cuoi[-1]
    out: list[dict[str, Any]] = []
    for m in ca["muc"]:
        out.append(
            {
                "id": f"tt_fx_{m['mat_hang']}",
                "hang": m["mat_hang"],
                "ten": TEN_HANG[str(m["mat_hang"])][0],
                "so_luong": float(m["cuoi_ca"]),
                "don_vi": m["don_vi"],
                "duoi_nguong": float(m["cuoi_ca"]) < 2,
                "ai": "quan_ly",
                "luc": f"{ca['ngay']}T22:00:00",
                "ca_id": ca["ca_id"],
                "nguon": NGUON_FIXTURE,
                "synthetic": True,
            }
        )
    return out


def build_van_hanh(
    staff: list[dict], ca21: list[dict], history: list[dict[str, Any]]
) -> dict[str, Any]:
    """Sáu bề mặt vận hành. Gọi SAU mọi bộ sinh đang có để không xê dịch RNG."""
    viec_treo = build_viec_treo(staff, ca21)
    inbox = build_inbox(ca21)
    ghi_nhan_sua = build_ghi_nhan_sua(staff, ca21)
    luat = build_luat(ghi_nhan_sua)
    hao_phi = build_hao_phi(ca21)
    kiem_ke = build_kiem_ke(history)
    return {
        "viec_treo": viec_treo,
        "inbox_rang_buoc": inbox,
        "luat_cam_nang": luat,
        "hao_phi": hao_phi,
        "kiem_ke": kiem_ke,
        "ghi_nhan_sua": ghi_nhan_sua,
        "tieu_thu": build_tieu_thu(kiem_ke),
    }


def main() -> None:
    SEED.mkdir(parents=True, exist_ok=True)
    GOLDEN_MSG.mkdir(parents=True, exist_ok=True)
    staff = build_staff(25)
    history = build_history(staff, 8)
    # 21 ca reference = week 1 pattern
    ca21 = build_shifts_for_week(1)
    # Golden là dữ liệu kiểm định đã được chăm sóc thủ công (hard cases
    # ec86189, TKB blur) — KHÔNG ghi đè khi đã có. build_messages vẫn LUÔN
    # chạy để giữ chuỗi RNG tất định cho build_van_hanh phía sau (test
    # test_bo_sinh_khop_voi_sample_da_ghi đối chiếu theo đúng chuỗi này).
    sinh_golden = "--golden" in sys.argv
    msgs, meta = build_messages(200)
    if sinh_golden or not (GOLDEN_MSG / "messages.jsonl").exists():
        (GOLDEN_MSG / "messages.jsonl").write_text(
            "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs) + "\n",
            encoding="utf-8",
        )
        (GOLDEN_MSG / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        build_tkb(50)
    # Dữ liệu vận hành sinh CUỐI CÙNG: chuỗi RNG của các phần đang có không đổi,
    # nên messages/tkb/lịch sử vẫn y hệt bản trước.
    van_hanh = build_van_hanh(staff, ca21, history)
    payload = {
        "synthetic": True,
        "nhan_vien": staff,
        "ca_mau_21": ca21,
        "lich_su_8_tuan": history,
        "ghi_chu": "Fixture seed — Quán Fixture NHỊP QUÁN (ADR-012)",
        "ghi_chu_van_hanh": (
            "Sáu bề mặt vận hành dựng lại, nguồn `mo_phong_fixture`, "
            f"mốc tính hạn {MOC_XEM}. Không phải dữ liệu quán thật."
        ),
        **van_hanh,
    }
    (SEED / "sample.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("seed", len(staff), "staff", len(ca21), "role-slots", len(history), "weeks")
    if sinh_golden or not (GOLDEN_MSG / "messages.jsonl").exists():
        print("golden messages", 200, "tkb", 50)
    else:
        print("golden: giu nguyen (dung --golden de tai sinh)")
    for k, v in van_hanh.items():
        print("van_hanh", k, len(v))


if __name__ == "__main__":
    main()
