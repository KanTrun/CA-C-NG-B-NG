"""AG-MEETING Clarification Engine — Context validation, staff shift resolution, and AI Clarifier Agent."""

from __future__ import annotations

from typing import Any

from ca_agents.ag_meeting.extract import resolve_staff_id

_KHUNG_LABEL = {
    "sang": "Ca Sáng",
    "chieu": "Ca Chiều",
    "toi": "Ca Tối",
    "dem": "Ca Đêm",
}

_THU_FULL = {
    "T2": "Thứ Hai",
    "T3": "Thứ Ba",
    "T4": "Thứ Tư",
    "T5": "Thứ Năm",
    "T6": "Thứ Sáu",
    "T7": "Thứ Bảy",
    "CN": "Chủ Nhật",
}

# Keywords indicating coaching / general feedback rather than a concrete hanging task
_GOP_Y_KEYWORDS = [
    "góp ý",
    "lưu ý",
    "nhắc nhở",
    "cười tươi",
    "thái độ",
    "tác phong",
    "nhẹ tay",
    "cẩn thận",
    "chú ý",
    "chào khách",
    "thân thiện",
    "nụ cười",
    "giao tiếp",
    "khen ngợi",
    "động viên",
]

# Keywords indicating long-running or multi-shift task
_NHIEU_CA_KEYWORDS = [
    "nhiều ca",
    "các ca",
    "trong tuần",
    "tuần này",
    "hàng ngày",
    "mỗi ngày",
    "theo dõi",
    "quan sát",
    "3 ngày",
    "7 ngày",
    "liên ca",
    "xuyên suốt",
    "định kỳ",
]


def resolve_staff_shifts(
    nv_id: str | None,
    phan_cong: dict[str, list[str]] | None,
    ca_list: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Retrieve scheduled upcoming shifts for an employee from roster assignments."""
    if not nv_id or not phan_cong or not ca_list:
        return []

    ca_by_id = {str(c.get("id")): c for c in ca_list if isinstance(c, dict)}
    shifts: list[dict[str, Any]] = []

    target_nv = str(nv_id).strip().lower()
    for ca_id, nv_list in phan_cong.items():
        is_assigned = False
        if isinstance(nv_list, str):
            is_assigned = (nv_list.strip().lower() == target_nv)
        elif isinstance(nv_list, (list, tuple, set)):
            is_assigned = any(str(x).strip().lower() == target_nv for x in nv_list)

        if is_assigned and str(ca_id) in ca_by_id:
            c = ca_by_id[str(ca_id)]
            thu = str(c.get("thu") or "")
            khung = str(c.get("khung") or "")
            bat_dau = str(c.get("bat_dau") or "")
            ket_thuc = str(c.get("ket_thuc") or "")

            thu_text = _THU_FULL.get(thu, thu)
            khung_text = _KHUNG_LABEL.get(khung, f"Ca {khung}")
            time_text = f" ({bat_dau} - {ket_thuc})" if bat_dau and ket_thuc else ""
            label = f"{thu_text} · {khung_text}{time_text}"

            shifts.append(
                {
                    "ca_id": str(ca_id),
                    "thu": thu,
                    "khung": khung,
                    "bat_dau": bat_dau,
                    "ket_thuc": ket_thuc,
                    "label": label,
                }
            )

    # Sort shifts by day order T2..CN then khung sang/chieu/toi/dem
    thu_order = {"T2": 0, "T3": 1, "T4": 2, "T5": 3, "T6": 4, "T7": 5, "CN": 6}
    khung_order = {"sang": 0, "chieu": 1, "toi": 2, "dem": 3}
    shifts.sort(
        key=lambda s: (
            thu_order.get(s["thu"], 9),
            khung_order.get(s["khung"], 9),
        )
    )
    return shifts


def classify_action_type(title: str, detail: str = "") -> str:
    """Classify action item into 1_ca (immediate 1-shift), nhieu_ca (multi-shift), or gop_y (coaching/feedback)."""
    text = f"{title} {detail}".lower()

    # If it is clearly feedback/attitude/manner and doesn't mention a physical repair or formula update
    if any(k in text for k in _GOP_Y_KEYWORDS) and not any(
        k in text for k in ["sửa", "thay", "dán", "kiểm tra tủ", "vệ sinh máy", "công thức"]
    ):
        return "gop_y"

    if any(k in text for k in _NHIEU_CA_KEYWORDS):
        return "nhieu_ca"

    return "1_ca"


def clarify_single_action(
    action: dict[str, Any],
    staff_list: list[dict[str, Any]] | None,
    phan_cong: dict[str, list[str]] | None,
    ca_list: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Inspect a single action item, resolve staff shifts, detect context gaps, and generate questions."""
    res = dict(action)
    title = str(res.get("tieu_de") or "").strip()
    detail = str(res.get("noi_dung_chi_tiet") or "").strip()
    assignee = str(res.get("ten_nguoi_nhan") or "Chưa rõ").strip()

    # 1. Dynamically resolve staff ID from latest assignee name
    resolved_id = resolve_staff_id(assignee, staff_list) if staff_list else None
    nv_id = resolved_id if resolved_id is not None else (res.get("nhan_vien_id") if assignee != "Chưa rõ" else None)
    res["nhan_vien_id"] = nv_id

    # 2. Look up shifts for this employee
    shifts = resolve_staff_shifts(nv_id, phan_cong, ca_list) if nv_id else []
    shift_labels = [s["label"] for s in shifts]
    res["ca_du_kien"] = shift_labels

    # 3. Detect / keep work type
    work_type = res.get("loai_cong_viec")
    if not work_type or work_type not in ("1_ca", "nhieu_ca", "gop_y"):
        work_type = classify_action_type(title, detail)
    res["loai_cong_viec"] = work_type

    # 4. Context gap detection & AI Clarifier Question generation
    can_lam_ro = False
    van_de = ""
    cau_hoi = ""
    goi_y: list[str] = []

    # Priority Guardrails: Hallucination or STT Near-Miss
    if res.get("khong_co_can_cu"):
        can_lam_ro = True
        van_de = res.get("van_de_ngu_canh") or "Việc này chưa thấy trong ghi chép thoại, cần xác nhận lại"
        cau_hoi = (
            res.get("cau_hoi_lam_ro")
            or f"Nội dung '{title}' không xuất hiện trong biên bản thoại. Bạn có chắc chắn muốn giao việc này không?"
        )
        goi_y = ["Vẫn giữ việc này", "Xóa bỏ công việc"]
    elif res.get("stt_near_miss"):
        can_lam_ro = True
        van_de = res.get("van_de_ngu_canh") or "STT nghe gần đúng tên nhân sự, vui lòng xác nhận"
        cau_hoi = (
            res.get("cau_hoi_lam_ro")
            or f"Hệ thống nhận diện '{assignee}' (có thể do STT nghe gần đúng âm vị). Bạn có xác nhận giao việc cho {assignee} không?"
        )
        goi_y = [f"Xác nhận giao cho {assignee}", "Đổi sang người khác"]
    # Case A: Content is actually a feedback / reminder note
    elif work_type == "gop_y":
        can_lam_ro = True
        van_de = "Nội dung mang tính chất nhắc nhở / góp ý tác phong hơn là một công việc phân công cụ thể."
        cau_hoi = f"Nội dung '{title}' mang tính chất góp ý/nhắc nhở. Bạn có muốn chuyển mục này sang 'Góp ý & Lưu ý nội bộ' thay vì tạo việc treo giao ca?"
        goi_y = [
            "Chuyển sang Góp ý nội bộ",
            "Giữ lại làm công việc 1 ca",
        ]

    # Case B: Assignee is missing or vague ("Chưa rõ", "Mọi người", "Nhóm")
    elif assignee in ("Chưa rõ", "Mọi người", "Tất cả", "Nhóm ca", ""):
        can_lam_ro = True
        van_de = "Chưa xác định đích danh nhân viên phụ trách."
        cau_hoi = f"Công việc '{title}' chưa có người chịu trách nhiệm chính. Bạn muốn phân công cụ thể cho ai?"
        top_staff = [str(nv.get("ten")) for nv in (staff_list or [])[:3] if nv.get("ten")]
        goi_y = [f"Giao cho {name}" for name in top_staff] if top_staff else ["Giao cho quản lý ca"]
        goi_y.append("Chuyển thành việc chung cả ca")

    # Case C2: Assignee is a concrete name but resolves to NO staff member —
    # trước đây nv_id None làm nhánh này bị tua qua, clarify vẫn báo "đầy đủ
    # thông tin" trong khi việc treo được tạo không gắn được người nhận.
    elif nv_id is None and len(shifts) == 0:
        can_lam_ro = True
        van_de = f"Tên '{assignee}' không khớp nhân viên nào trong danh sách quán."
        cau_hoi = f"Không tìm thấy '{assignee}' trong danh sách nhân sự. Bạn muốn giao việc này cho ai?"
        top_staff = [str(nv.get("ten")) for nv in (staff_list or [])[:3] if nv.get("ten")]
        goi_y = [f"Giao cho {name}" for name in top_staff] if top_staff else ["Giao cho quản lý ca"]
        goi_y.append("Chuyển thành việc chung của quán")

    # Case C: Assignee exists but has NO scheduled shifts this week
    elif nv_id and len(shifts) == 0:
        can_lam_ro = True
        van_de = f"Nhân viên {assignee} hiện không có ca làm việc nào trong lịch tuần này."
        cau_hoi = f"{assignee} không có ca làm việc trong lịch tuần. Bạn muốn giao việc này cho nhân viên khác có ca trực, hay vẫn giao chờ đến khi {assignee} có ca?"
        goi_y = [
            f"Vẫn giao cho {assignee} (chờ ca sau)",
            "Chuyển sang nhân viên đang trực ca hôm nay",
            "Chuyển thành việc chung của quán",
        ]

    # Case D: Assignee has shifts, but deadline or shift is unclear
    elif work_type == "1_ca":
        if not res.get("ca_thuc_hien") and shifts:
            res["ca_thuc_hien"] = shifts[0]["label"]

        due = str(res.get("han_chot") or "").strip().lower()
        has_time = any(ch.isdigit() for ch in due) or any(k in title.lower() for k in ["trước", "lúc", "hạn"])

        if not has_time and shifts:
            can_lam_ro = True
            first_shift = shifts[0]
            van_de = f"Chưa rõ mốc giờ hoàn thành cụ thể trong {first_shift['label']}."
            cau_hoi = f"Việc '{title}' giao cho {assignee} vào {first_shift['label']}. Bạn muốn yêu cầu hoàn thành vào lúc nào?"
            end_time = first_shift.get("ket_thuc")
            goi_y = [
                f"Hoàn thành trước khi hết ca ({end_time or 'kết ca'})",
                f"Làm ngay đầu ca ({first_shift.get('bat_dau', 'đầu ca')})",
                "Chuyển sang theo dõi nhiều ca",
            ]

    elif work_type == "nhieu_ca":
        if not res.get("ca_thuc_hien") and shifts:
            res["ca_thuc_hien"] = "Xuyên suốt các ca tuần này"

    res["can_lam_ro"] = can_lam_ro
    res["van_de_ngu_canh"] = van_de
    res["cau_hoi_lam_ro"] = cau_hoi
    res["goi_y_xu_ly"] = goi_y

    return res


def clarify_meeting_actions(
    actions: list[dict[str, Any]],
    staff_list: list[dict[str, Any]] | None,
    phan_cong: dict[str, list[str]] | None,
    ca_list: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Enrich and clarify all action items for a meeting."""
    return [
        clarify_single_action(
            action=act,
            staff_list=staff_list,
            phan_cong=phan_cong,
            ca_list=ca_list,
        )
        for act in actions
    ]
