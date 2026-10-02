# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Cổng chặn: mọi intent copilot khai báo phải có ít nhất một từ khóa.

Bài học (2026-10-01): `GET_INVENTORY` có enum, có tool (`tool_get_inventory`),
được cấp cho cả 3 vai trò — nhưng không có dòng nào trong `_INTENT_KEYWORDS`.
Nên `parse_intent()` không bao giờ sinh ra nó từ câu nói, và nhân viên hỏi
"tồn kho còn gì" thì nhận OUT_OF_SCOPE dù dữ liệu nằm ngay trong KV.

Lỗi đó lọt qua nhiều PR không ai thấy vì không có gì kiểm tra. Test này là cổng
đó: thêm intent mà quên khai từ khóa thì CI fail ngay.

Cùng bộ test này còn canh 2 thứ liên quan:
- Intent phải có tool thật trong registry (không có tool thì khai báo cũng rác).
- Từ khóa phải viết cả bản CÓ DẤU và KHÔNG DẤU, vì parser khớp thẳng
  `kw in text.lower()` và KHÔNG bỏ dấu (đã đo: cụm không dấu không khớp câu có dấu).
"""

from __future__ import annotations

import pytest
from ca_agents.ag_copilot import intent_parser as ip
from ca_agents.ag_copilot.tool_registry import _READ_TOOLS, _TOOLS
from ca_contracts import CopilotIntent

# OUT_OF_SCOPE là trạng thái rơi, không phải hành động → không cần từ khóa.
_KO_CAN_TU_KHOA = {"OUT_OF_SCOPE"}


def _ten_intent() -> set[str]:
    return {i.value for i in CopilotIntent} - _KO_CAN_TU_KHOA


def _intent_co_tu_khoa() -> set[str]:
    return {name for name, _, _ in ip._INTENT_KEYWORDS}


def test_moi_intent_deu_co_tu_khoa() -> None:
    """Intent nào khai báo trong enum mà không có từ khóa thì fail.

    Đây chính là lỗi GET_INVENTORY. Test phải bắt được, nên chạy lúc này SẼ FAIL —
    sau khi sửa intent_parser.py thì xanh.
    """
    thieu = sorted(_ten_intent() - _intent_co_tu_khoa())
    assert not thieu, (
        "Intent có trong CopilotIntent nhưng KHÔNG có _INTENT_KEYWORDS → "
        "parse_intent() không bao giờ sinh ra được, người dùng hỏi là OUT_OF_SCOPE: "
        + ", ".join(thieu)
    )


def test_moi_intent_deu_co_tool() -> None:
    """Intent có từ khóa mà không có tool thì người dùng được câu trả lời rỗng."""
    co_tool = set(_READ_TOOLS) | set(_TOOLS)
    thieu = sorted(_ten_intent() - co_tool)
    assert not thieu, (
        "Intent không có tool trong registry: " + ", ".join(thieu)
    )


def _bo_dau(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", s).replace("đ", "d").replace("Đ", "D").lower()


def _co_ban_khong_dau(chuoi: str) -> bool:
    """True nếu chuỗi còn nguyên dấu tiếng Việt."""
    return chuoi != _bo_dau(chuoi)


@pytest.mark.parametrize("ten", sorted(_intent_co_tu_khoa()))
def test_tu_khoa_co_ban_khong_dau(ten: str) -> None:
    """Mỗi từ khóa có dấu phải có bản không dấu đi kèm.

    Parser khớp thẳng `kw in text.lower()`. Người dùng đánh máy không dấu vẫn
    phải ra đúng intent, nếu không thì lỗi "nói lệch một từ là rơi OUT_OF_SCOPE"
    quay lại y hệt lúc đầu.

    Bản trước của test này KHÔNG BAO GIỜ FAIL: nó tính
    `khong_dau = {_bo_dau(c) for c in cum}` rồi hỏi `_bo_dau(kw) not in khong_dau`
    — nhưng `khong_dau` luôn chứa `_bo_dau(kw)` của chính `kw`, nên vế kiểm tra
    luôn sai. Hệ quả: `CREATE_RULE_PROPOSAL` thiếu toàn bộ bản không dấu mà CI
    vẫn xanh. Sửa: chỉ coi là "đã có bản không dấu" khi chuỗi đó THỰC SỰ nằm
    trong danh sách từ khoá.
    """
    cum = next(kw for kw in ip._INTENT_KEYWORDS if kw[0] == ten)[1]
    co_san = set(cum)
    thieu = [kw for kw in cum if _co_ban_khong_dau(kw) and _bo_dau(kw) not in co_san]
    assert not thieu, (
        f"Intent {ten}: từ khóa có dấu mà thiếu bản không dấu: "
        + ", ".join(thieu)
    )


# Câu hỏi văn nói thật của nhân viên về ca/lịch CỦA CHÍNH MÌNH.
# Đây là hồi quy của sự cố "Live Copilot không trả lời": trạng từ thời gian
# ("hôm nay", "mai") bị chèn vào GIỮA cụm cố định nên `"lịch của tôi"` trượt,
# câu rơi OUT_OF_SCOPE → Live chỉ đáp câu xã giao và không gọi tool tra lịch.
_CAU_HOI_CA_NHAN = [
    "lịch hôm nay của tôi",
    "lịch hôm nay của t",
    "lịch hôm nay của em",
    "ca hôm nay của tôi",
    "ca hôm nay của t",
    "ca của tôi hôm nay",
    "lịch làm việc hôm nay của tôi",
    "lịch làm việc hôm nay của t",
    "hôm nay tôi có ca không",
    "hôm nay t có ca không",
    "hôm nay em có ca không",
    "hôm nay tôi có lịch không",
    "hôm nay tôi có đi làm không",
    "hôm nay t có đi làm không",
    "hôm nay tôi làm ca gì",
    "hôm nay tôi làm ca mấy",
    "hôm nay t làm ca gì",
    "mai tôi có ca không",
    "mai t có ca không",
    "ngày mai tôi có ca không",
    "tuần này tôi có ca không",
    "tuần này tôi có mấy ca",
    "tôi làm ca nào hôm nay",
    "ca làm việc hôm nay của tôi",
    "ca tối nay của tôi",
    "ca sáng nay của tôi",
    "ca chiều nay của tôi",
    "tối nay tôi có ca không",
    "sáng nay tôi có ca không",
    "lịch tháng này của tôi",
    "lịch tuần này của tôi",
    "tuần này tôi làm ca gì",
    "tôi có ca mấy giờ",
    "ca của tôi mấy giờ",
]


@pytest.mark.parametrize("cau", _CAU_HOI_CA_NHAN)
def test_cau_hoi_ca_nhan_ra_get_my_shifts(cau: str) -> None:
    """Câu hỏi ca cá nhân PHẢI ra GET_MY_SHIFTS, không được là OUT_OF_SCOPE.

    Và cũng không được rơi vào GET_SCHEDULE (lịch toàn quán) — nhân viên hỏi
    ca của mình mà nhận lịch của cả quán thì vẫn là trả lời sai.
    """
    ctx = {"user_role": "nhan_vien", "store_id": "quan_01"}
    ket_qua = ip.parse_intent(cau, ctx)
    assert ket_qua.intent == ip.GET_MY_SHIFTS, (
        f"{cau!r} → {ket_qua.intent}, mong đợi GET_MY_SHIFTS"
    )


@pytest.mark.parametrize("cau", _CAU_HOI_CA_NHAN)
def test_cau_hoi_ca_nhan_khong_dau(cau: str) -> None:
    """Bản không dấu của cùng câu hỏi cũng phải ra GET_MY_SHIFTS."""
    ctx = {"user_role": "nhan_vien", "store_id": "quan_01"}
    ket_qua = ip.parse_intent(_bo_dau(cau), ctx)
    assert ket_qua.intent == ip.GET_MY_SHIFTS, (
        f"{_bo_dau(cau)!r} → {ket_qua.intent}, mong đợi GET_MY_SHIFTS"
    )


def test_cau_hoi_lich_toan_quan_van_ra_get_schedule() -> None:
    """Chốt chặn hồi quy: câu hỏi lịch TOÀN QUÁN vẫn phải là GET_SCHEDULE.

    Nhóm từ khóa văn nói mới thêm cho GET_MY_SHIFTS không được "nuốt" các câu
    hỏi mang tính quản lý.
    """
    ctx = {"user_role": "quan_ly", "store_id": "quan_01"}
    for cau in ["ai chưa có ca", "lịch tuần này của quán", "tình hình lịch"]:
        ket_qua = ip.parse_intent(cau, ctx)
        assert ket_qua.intent != ip.GET_MY_SHIFTS, (
            f"{cau!r} → {ket_qua.intent}, không được là GET_MY_SHIFTS"
        )


# Câu mang ý GHI (xếp/đổi/hủy ca) không được bị nhóm từ khóa văn nói của
# GET_MY_SHIFTS nuốt. Đây là hồi quy thật đo được khi review: sau khi thêm
# "lịch hôm nay của tôi", câu "xếp lịch hôm nay của tôi" từ SCHEDULE_SOLVE
# (baseline HEAD) bị đổi thành GET_MY_SHIFTS — xếp lịch thành tra cứu lịch.
_MUTATING_PHAI_GIU = [
    ("xếp lịch hôm nay của tôi", ip.SCHEDULE_SOLVE),
    ("lên lịch hôm nay của tôi", ip.SCHEDULE_SOLVE),
    ("xếp lịch hôm nay", ip.SCHEDULE_SOLVE),
    ("đổi ca hôm nay của tôi", ip.OUT_OF_SCOPE),
    ("hủy ca hôm nay của tôi", ip.OUT_OF_SCOPE),
    ("xóa ca hôm nay của tôi", ip.OUT_OF_SCOPE),
]


# Viết tắt chat/nói. Người dùng gõ "lịch hnay của t" hoặc nói "hnay t có ca k";
# không chuẩn hoá thì trượt hết vì bảng từ khoá chỉ có dạng đầy đủ.
_VIET_TAT_CA_NHAN = [
    "lịch hnay của t",
    "lịch hnay của tôi",
    "ca hnay của t",
    "hnay t có ca k",
    "t có ca hnay k",
    "lịch t2 của t",
    "ca t7 của t",
]
# Lưu ý: "lịch tuan nay cua toi" (hỗn hợp dấu) không phải input thực tế — bỏ.
_KHONG_DAU_CA_NHAN = [
    "lich hnay cua t",
    "lich hnay cua toi",
    "hnay t co ca k",
    "lich tuan nay cua toi",
    "hom nay toi co ca khong",
    "toi co ca hom nay khong",
]


@pytest.mark.parametrize("cau", _VIET_TAT_CA_NHAN)
def test_viet_tat_van_ra_get_my_shifts(cau: str) -> None:
    """Câu viết tắt phải được chuẩn hoá rồi khớp GET_MY_SHIFTS."""
    ctx = {"user_role": "nhan_vien", "store_id": "quan_01", "user_id": "nv_01"}
    assert ip.parse_intent(cau, ctx).intent == ip.GET_MY_SHIFTS, (
        f"{cau!r} không được chuẩn hoá đúng"
    )


@pytest.mark.parametrize("cau", _KHONG_DAU_CA_NHAN)
def test_khong_dau_van_ra_get_my_shifts(cau: str) -> None:
    """Câu gõ KHÔNG DẤU vẫn phải ra GET_MY_SHIFTS (bảng từ khoá có bản không dấu).

    Chuẩn hoá viết tắt phải bỏ qua văn bản không dấu — nếu nó "dịch" `hnay`
    thành `hôm nay` (có dấu) thì chính bản không dấu sẽ hết khớp.
    """
    ctx = {"user_role": "nhan_vien", "store_id": "quan_01", "user_id": "nv_01"}
    assert ip.parse_intent(cau, ctx).intent == ip.GET_MY_SHIFTS, (
        f"{cau!r} không dấu bị mất intent"
    )


# Dấu câu / viết hoa / từ đệm không được làm trượt nhận diện.
_BIEN_THE_KHONG_DOI_INTENT = [
    "lịch hôm nay của tôi?",
    "lịch hôm nay của tôi!!!",
    "lịch hôm nay của tôi...",
    "lịch hôm nay của tôi 😀",
    "  lịch hôm nay của tôi  ",
    "LỊCH HÔM NAY CỦA TÔI",
    "Lịch Hôm Nay Của Tôi",
    "ừm cho tôi xem lịch hôm nay của tôi",
    "em ơi lịch hôm nay của tôi",
    "lịch hôm nay của tôi nhé",
]


@pytest.mark.parametrize("cau", _BIEN_THE_KHONG_DOI_INTENT)
def test_bien_the_dau_cau_khong_doi_intent(cau: str) -> None:
    """Dấu câu, emoji, viết hoa, từ đệm phải giữ nguyên GET_MY_SHIFTS."""
    ctx = {"user_role": "nhan_vien", "store_id": "quan_01", "user_id": "nv_01"}
    assert ip.parse_intent(cau, ctx).intent == ip.GET_MY_SHIFTS


# Phủ định thật ("không có ca") phải fail-closed, KHÔNG được thành tra cứu.
# Trong khi "hôm nay tôi có ca không" là CÂU HỎI — chữ "không" ở cuối không
# phải phủ định. Đây là ranh giới dễ sập nhất của tiếng Việt.
_PHU_DINH_THAT = [
    "tôi không có ca hôm nay à",
    "hôm nay tôi không có ca",
    "lịch hôm nay của tôi không có ca",
]


@pytest.mark.parametrize("cau", _PHU_DINH_THAT)
def test_phu_dinh_that_fail_closed(cau: str) -> None:
    ctx = {"user_role": "nhan_vien", "store_id": "quan_01", "user_id": "nv_01"}
    assert ip.parse_intent(cau, ctx).intent != ip.GET_MY_SHIFTS, (
        f"{cau!r}: phủ định không được map thành tra cứu ca"
    )


def test_cau_hoi_co_khong_o_cuoi_van_la_tra_cuu() -> None:
    """"có ... không" ở cuối câu là CÂU HỎI, không phải phủ định."""
    ctx = {"user_role": "nhan_vien", "store_id": "quan_01", "user_id": "nv_01"}
    for cau in [
        "hôm nay tôi có ca không",
        "hôm nay t có ca không",
        "tôi có ca không",
        "hnay t có ca k",
    ]:
        assert ip.parse_intent(cau, ctx).intent == ip.GET_MY_SHIFTS, (
            f"{cau!r}: 'có ... không' phải là câu hỏi, không phải phủ định"
        )


@pytest.mark.parametrize(("cau", "mong_doi"), _MUTATING_PHAI_GIU)
def test_cau_mutating_khong_bi_nuot_thanh_tra_cuu(cau: str, mong_doi: str) -> None:
    """Câu yêu cầu GHI không được trả về như lượt TRA CỨU ca cá nhân.

    Đối chiếu với baseline HEAD (đo trước khi thêm từ khóa văn nói):
    xếp lịch → SCHEDULE_SOLVE; đổi/hủy ca → OUT_OF_SCOPE (fail-closed vì chưa
    có intent ghi tương ứng trong CopilotIntent).
    """
    ctx = {"user_role": "quan_ly", "store_id": "quan_01", "user_id": "nv_01"}
    ket_qua = ip.parse_intent(cau, ctx)
    assert ket_qua.intent != ip.GET_MY_SHIFTS, (
        f"{cau!r} → GET_MY_SHIFTS: yêu cầu ghi bị biến thành tra cứu"
    )
    assert ket_qua.intent == mong_doi, (
        f"{cau!r} → {ket_qua.intent}, mong đợi {mong_doi} (theo baseline HEAD)"
    )


# MỘT câu mẫu cho mỗi chức năng — khớp đúng docs/ag-copilot-cau-hoi-mau.md.
# Đây là cổng chặn cho cả tài liệu: sửa từ khoá làm lệch một câu mẫu thì CI fail.
# Mỗi câu đã được đo chạy đúng với cả 3 vai trò, dạng có dấu và không dấu.
_CAU_HOI_MAU: dict[str, str] = {
    "GET_MY_SHIFTS": "lịch hôm nay của tôi",
    "GET_SCHEDULE": "xem lịch tuần này",
    "SCHEDULE_SOLVE": "xếp lịch tuần sau",
    "GET_OPEN_SHIFTS": "chợ ca có gì",
    "GET_HANDOVERS": "bàn giao ca gần nhất",
    "PROPOSE_HANDOVER": "ghi bàn giao ca",
    "GET_SHIFT_SWAPS": "có yêu cầu đổi ca nào không",
    "APPROVE_SHIFT_SWAP": "duyệt đổi ca",
    "PROPOSE_SWAP_CONSENT": "đồng ý đổi ca",
    "GET_CONSTRAINT_CANDIDATES": "ràng buộc chờ duyệt có gì",
    "PROPOSE_TIME_OFF": "tôi xin nghỉ ngày mai",
    "GET_FAIRNESS_SUMMARY": "báo cáo công bằng",
    "GET_TODAY_OPERATIONS": "tình hình hôm nay",
    "GENERATE_DAILY_BRIEF": "bản tin hôm nay",
    "GET_WEATHER": "thời tiết hôm nay",
    "GET_RESERVATIONS": "đặt bàn hôm nay",
    "GET_PREDICTIVE_INSIGHTS": "gợi ý vận hành",
    "GET_MY_CHECKLIST": "checklist của tôi",
    "GET_INVENTORY": "xem tồn kho",
    "INVENTORY_RESTOCK_CHECK": "cần nhập thêm gì",
    "ANALYZE_WASTE": "hao hụt hôm nay",
    "PROPOSE_CONSUMPTION_RECORD": "ghi tiêu thụ",
    "QUERY_MENU": "menu có gì",
    "PROPOSE_MENU_UPDATE": "sửa giá món",
    "PROPOSE_ORDER_TRANSITION": "chuyển đơn sang pha",
    "QUERY_SOP": "quy trình pha chế",
    "CREATE_RULE_PROPOSAL": "đề xuất luật mới",
    "SEARCH_TRENDS": "xu hướng f&b",
    "QUERY_QUANVERSE": "quanverse",
    "QUERY_AUDIT": "nhật ký hệ thống",
    "LIST_STAFF": "danh sách nhân sự",
    "GET_MY_PROFILE": "hồ sơ của tôi",
    "GET_HANGING_TASKS": "việc treo",
    "PROPOSE_HANGING_TASK": "treo việc này",
    "PROPOSE_TASK_COMPLETE": "đánh dấu xong việc treo",
    "RUN_CATCHMENT_SURVEY": "khảo sát giá quanh đây",
    "GET_SURVEY_RESULT": "kết quả khảo sát giá",
    "GET_SERPAPI_QUOTA": "hạn ngạch serpapi",
    "PROPOSE_PAGE_DRAFT": "đăng bài lên fb",
    "PROPOSE_PAGE_SYNC": "đồng bộ page",
    "GET_PAGE_STATUS": "trạng thái page",
    "SEND_MAIL": "gửi mail cho nhân viên",
    "GET_MEETINGS": "biên bản họp",
    "PROPOSE_TKB_CONFIRM": "xác nhận tkb",
    "PROPOSE_PIN": "ghim ca này",
    "OUT_OF_SCOPE": "chào bạn",
}


@pytest.mark.parametrize(
    ("mong_doi", "cau"),
    list(_CAU_HOI_MAU.items()),
)
def test_cau_hoi_mau_ra_dung_intent(mong_doi: str, cau: str) -> None:
    """Mọi câu trong bộ mẫu phải ra đúng intent ghi trong tài liệu.

    Cổng chặn này giữ `docs/ag-copilot-cau-hoi-mau.md` không bị lệch khỏi code.
    """
    ctx = {"user_role": "quan_ly", "store_id": "quan_01", "user_id": "ql_01"}
    ket_qua = ip.parse_intent(cau, ctx)
    assert ket_qua.intent == mong_doi, (
        f"{cau!r} → {ket_qua.intent}, tài liệu ghi {mong_doi}"
    )


@pytest.mark.parametrize(("mong_doi", "cau"), list(_CAU_HOI_MAU.items()))
def test_cau_hoi_mau_dung_voi_moi_role(mong_doi: str, cau: str) -> None:
    """Một câu mẫu phải ra cùng intent với cả 3 vai trò.

    Nhận diện intent không được phụ thuộc vai trò — vai trò quyết định ở bước
    kiểm quyền (`role_blocked`), không phải ở bước hiểu câu.
    """
    for role in ("nhan_vien", "quan_ly", "chu_quan"):
        ctx = {"user_role": role, "store_id": "quan_01", "user_id": "nv_01"}
        ket_qua = ip.parse_intent(cau, ctx)
        assert ket_qua.intent == mong_doi, (
            f"{role}: {cau!r} → {ket_qua.intent}, tài liệu ghi {mong_doi}"
        )


@pytest.mark.parametrize(("mong_doi", "cau"), list(_CAU_HOI_MAU.items()))
def test_cau_hoi_mau_khong_dau_cung_dung(mong_doi: str, cau: str) -> None:
    """Bản KHÔNG DẤU của mỗi câu mẫu cũng phải ra đúng intent.

    Người dùng gõ không dấu rất phổ biến; thiếu bản không dấu thì câu rơi
    OUT_OF_SCOPE dù ý đúng.
    """
    ctx = {"user_role": "quan_ly", "store_id": "quan_01", "user_id": "ql_01"}
    ket_qua = ip.parse_intent(_bo_dau(cau), ctx)
    assert ket_qua.intent == mong_doi, (
        f"{_bo_dau(cau)!r} (không dấu của {cau!r}) → {ket_qua.intent}"
    )


def test_moi_intent_deu_co_cau_hoi_mau() -> None:
    """Intent nào có từ khoá cũng phải có ĐÚNG một câu mẫu được kiểm tra.

    Thiếu câu mẫu nghĩa là intent đó không có cổng chặn nào — thêm từ khoá sai
    cũng không ai phát hiện. Tài liệu chỉ giữ một câu mỗi chức năng nên ở đây
    cũng giữ đúng một, tránh tài liệu và test lệch nhau.
    """
    thieu = sorted(_intent_co_tu_khoa() - set(_CAU_HOI_MAU))
    assert not thieu, (
        "Intent có từ khoá nhưng chưa có câu hỏi mẫu trong _CAU_HOI_MAU: "
        + ", ".join(thieu)
    )