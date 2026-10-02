# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Unit tests for Meeting Action Items Context Clarification and Staff Schedule Resolution."""

import concurrent.futures
import io
import unicodedata
import uuid

import pytest
from ca_agents.ag_meeting.clarify import (
    clarify_single_action,
    classify_action_type,
    resolve_staff_shifts,
)
from ca_agents.ag_meeting.extract import (
    _is_grounded_in_transcript,
    extract_meeting,
    resolve_staff_id,
    resolve_staff_id_with_meta,
)
from ca_api.interfaces.http.main import app
from ca_api.persist import audit_list, kv_get, kv_mutate
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


@pytest.fixture(autouse=True)
def _pin_replay_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CA_AGENT_MODE", "replay")


def test_resolve_staff_shifts_lookup() -> None:
    ca_list = [
        {"id": "c1", "thu": "T2", "khung": "sang", "bat_dau": "06:00", "ket_thuc": "11:00"},
        {"id": "c2", "thu": "T2", "khung": "chieu", "bat_dau": "11:00", "ket_thuc": "16:00"},
        {"id": "c3", "thu": "T3", "khung": "toi", "bat_dau": "16:00", "ket_thuc": "22:00"},
    ]
    phan_cong = {
        "c1": ["nv_01", "nv_02"],
        "c2": ["nv_01"],
        "c3": ["nv_03"],
    }

    # nv_01 has c1 and c2
    shifts = resolve_staff_shifts("nv_01", phan_cong, ca_list)
    assert len(shifts) == 2
    assert shifts[0]["thu"] == "T2"
    assert shifts[0]["khung"] == "sang"
    assert "Thứ Hai · Ca Sáng" in shifts[0]["label"]

    # nv_03 has c3
    shifts_03 = resolve_staff_shifts("nv_03", phan_cong, ca_list)
    assert len(shifts_03) == 1
    assert "Thứ Ba · Ca Tối" in shifts_03[0]["label"]

    # unknown nv has none
    shifts_none = resolve_staff_shifts("nv_99", phan_cong, ca_list)
    assert len(shifts_none) == 0


def test_classify_action_type() -> None:
    assert classify_action_type("Nhớ cười tươi và chào khách thân thiện", "") == "gop_y"
    assert classify_action_type("Theo dõi chất lượng trà đào trong tuần này", "") == "nhieu_ca"
    assert classify_action_type("Thay ron máy pha số 2 trước 16h", "") == "1_ca"


def test_clarify_single_action_missing_assignee() -> None:
    action = {
        "id": "act_1",
        "tieu_de": "Dọn dẹp lại khu vực quầy bar",
        "ten_nguoi_nhan": "Chưa rõ",
        "noi_dung_chi_tiet": "",
    }
    staff_list = [{"id": "nv_01", "ten": "Tuấn"}, {"id": "nv_02", "ten": "My"}]
    res = clarify_single_action(action, staff_list=staff_list, phan_cong={}, ca_list=[])

    assert res["can_lam_ro"] is True
    assert "chưa có người chịu trách nhiệm chính" in res["cau_hoi_lam_ro"].lower()
    assert len(res["goi_y_xu_ly"]) >= 1


def test_clarify_single_action_no_scheduled_shifts() -> None:
    action = {
        "id": "act_2",
        "tieu_de": "Kiểm tra tủ đá",
        "ten_nguoi_nhan": "Tuấn",
        "noi_dung_chi_tiet": "",
    }
    staff_list = [{"id": "nv_01", "ten": "Tuấn"}]
    phan_cong = {"c1": ["nv_02"]}  # Tuấn not assigned
    ca_list = [{"id": "c1", "thu": "T2", "khung": "sang"}]

    res = clarify_single_action(action, staff_list=staff_list, phan_cong=phan_cong, ca_list=ca_list)
    assert res["can_lam_ro"] is True
    assert "không có ca làm việc" in res["cau_hoi_lam_ro"].lower()


def test_clarify_actions_http_endpoint() -> None:
    ql = headers(client, "lan")
    res = client.post(
        "/api/v1/meeting/clarify-actions",
        json={
            "action_items": [
                {
                    "id": "act_1",
                    "tieu_de": "Lưu ý chào khách niềm nở hơn",
                    "ten_nguoi_nhan": "Lan",
                },
                {
                    "id": "act_2",
                    "tieu_de": "Thay ron máy pha",
                    "ten_nguoi_nhan": "Chưa rõ",
                },
            ]
        },
        headers=ql,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    items = body["action_items"]
    assert len(items) == 2
    # act_1 detected as gop_y
    assert items[0]["loai_cong_viec"] == "gop_y"
    assert items[0]["can_lam_ro"] is True
    # act_2 missing assignee
    assert items[1]["can_lam_ro"] is True


def test_apply_routes_gop_y_to_meeting_notes_instead_of_treo() -> None:
    ql = headers(client, "lan")

    # Analyze a meeting first
    res = client.post(
        "/api/v1/meeting/analyze",
        json={
            "text": "Quản lý: Tuấn thay ron máy pha trước 16h.",
            "meeting_type": "giao_ca",
        },
        headers=ql,
    ).json()

    # Add a gop_y item and an action task
    res["action_items"] = [
        {
            "id": "act_task",
            "tieu_de": "Vệ sinh khay hứng nước máy pha",
            "ten_nguoi_nhan": "Tuấn",
            "loai_cong_viec": "1_ca",
            "ca_thuc_hien": "Ca Chiều",
            "han_chot": "16:00",
            "da_chon": True,
            "do_tin_cay": 0.95,
        },
        {
            "id": "act_coaching",
            "tieu_de": "Pha chế nhớ kiểm tra nhiệt độ sữa trước khi đánh bọt",
            "ten_nguoi_nhan": "Tuấn",
            "loai_cong_viec": "gop_y",
            "da_chon": True,
            "do_tin_cay": 0.9,
        },
    ]

    apply_res = client.post("/api/v1/meeting/apply", json=res, headers=ql)
    assert apply_res.status_code == 200, apply_res.text
    apply_body = apply_res.json()
    assert apply_body["ok"] is True
    # Only act_task should be created in treo, not act_coaching!
    assert apply_body["tasks_created"] == 1

    # Check treo
    treo = kv_get("treo", [])
    task_items = [t for t in treo if "Vệ sinh khay hứng nước" in t.get("noi_dung", "")]
    assert len(task_items) == 1
    assert task_items[0]["ca_thuc_hien"] == "Ca Chiều"
    assert "[Ca: Ca Chiều]" in task_items[0]["noi_dung"]

    # Verify act_coaching did NOT create a treo task
    coaching_in_treo = [t for t in treo if "nhiệt độ sữa" in t.get("noi_dung", "")]
    assert len(coaching_in_treo) == 0

    # Verify act_coaching WAS saved into meeting's gop_y_luu_y
    meetings = kv_get("meetings", [])
    saved_m = next((m for m in meetings if m.get("id") == res["id"]), None)
    assert saved_m is not None
    fbs = [f for f in saved_m.get("gop_y_luu_y", []) if "nhiệt độ sữa" in f.get("noi_dung", "")]
    assert len(fbs) == 1


def test_tc29_bypass_role_authorization_forbidden() -> None:
    """TC-29: Bypass phân quyền — Nhân viên gọi thẳng API apply bị trả về 403 Forbidden."""
    nv = headers(client, "minh")  # role: nhan_vien
    payload = {
        "id": "meet_test_tc29",
        "tieu_de": "Họp thử nghiệm phân quyền",
        "loai_hop": "giao_ca",
        "tom_tat": "Tóm tắt cuộc họp thử nghiệm phân quyền",
        "action_items": [
            {
                "id": "act_hacked",
                "tieu_de": "Task bất hợp pháp",
                "ten_nguoi_nhan": "Tuấn",
                "da_chon": True,
            }
        ],
    }
    res = client.post("/api/v1/meeting/apply", json=payload, headers=nv)
    assert res.status_code == 403
    assert "Chỉ Quản lý hoặc Chủ quán mới có quyền duyệt phân công" in res.json()["detail"]

    # Verify no task was created in treo
    treo = kv_get("treo", [])
    assert not any("Task bất hợp pháp" in t.get("noi_dung", "") for t in treo)


def test_tc30_cross_meeting_deduplication() -> None:
    """TC-30: Chống trùng lặp việc treo xuyên nhiều cuộc họp (Cross-meeting Deduplication)."""
    ql = headers(client, "lan")
    # Meeting 1 assigns task to Tuấn
    meet1 = {
        "id": "meet_m1_unique",
        "tieu_de": "Giao ca sáng",
        "loai_hop": "giao_ca",
        "tom_tat": "Giao ca sáng ngày làm việc",
        "action_items": [
            {
                "id": "act_m1",
                "tieu_de": "Thay ron máy pha trước 16h",
                "nhan_vien_id": "nv_01",
                "ten_nguoi_nhan": "Tuấn",
                "loai_cong_viec": "1_ca",
                "ca_thuc_hien": "Ca Chiều",
                "han_chot": "16:00",
                "da_chon": True,
            }
        ],
    }
    r1 = client.post("/api/v1/meeting/apply", json=meet1, headers=ql)
    assert r1.status_code == 200
    assert r1.json()["tasks_created"] == 1

    # Meeting 2 (30 mins later or different meeting) repeats the identical task for Tuấn
    meet2 = {
        "id": "meet_m2_unique",
        "tieu_de": "Giao ca bổ sung",
        "loai_hop": "giao_ca",
        "tom_tat": "Giao ca bổ sung buổi chiều",
        "action_items": [
            {
                "id": "act_m2",
                "tieu_de": "Thay ron máy pha trước 16h",
                "nhan_vien_id": "nv_01",
                "ten_nguoi_nhan": "Tuấn",
                "loai_cong_viec": "1_ca",
                "ca_thuc_hien": "Ca Chiều",
                "han_chot": "16:00",
                "da_chon": True,
            }
        ],
    }
    r2 = client.post("/api/v1/meeting/apply", json=meet2, headers=ql)
    assert r2.status_code == 200
    # Duplicate task across meetings was skipped
    assert r2.json()["tasks_created"] == 0

    # Verify only 1 instance exists in treo
    treo = kv_get("treo", [])
    tuan_tasks = [t for t in treo if "Thay ron máy pha" in t.get("noi_dung", "")]
    assert len(tuan_tasks) == 1


def test_tc31_accent_insensitive_mobile_matching() -> None:
    """TC-31: Tên nhân viên gõ không dấu / gõ tắt trên mobile ('tuan', 'my', 'lan')."""
    staff_list = [
        {"id": "nv_01", "ten": "Nguyễn Văn Tuấn"},
        {"id": "nv_02", "ten": "Trà My"},
        {"id": "nv_03", "ten": "Đặng Thị Lan"},
    ]
    # No accents typed on mobile
    assert resolve_staff_id("tuan", staff_list) == "nv_01"
    assert resolve_staff_id("my", staff_list) == "nv_02"
    assert resolve_staff_id("lan", staff_list) == "nv_03"
    # Accented variations and extra whitespace
    assert resolve_staff_id("  tuấn  ", staff_list) == "nv_01"
    assert resolve_staff_id("Trà My", staff_list) == "nv_02"
    # Unknown name returns None
    assert resolve_staff_id("nguoi_la", staff_list) is None


def test_display_name_with_role_suffix_still_resolves() -> None:
    """display_name thật của users hay kèm chức danh 'Minh Phạm — Trưởng pha chế (PT)'.

    Bug gặp thật 2026-10-01: AG-MEETING trích tên 'Minh Phạm' từ biên bản nhưng
    resolve_staff_id so nguyên chuỗi hiển thị nên không khớp, mọi việc giao ca
    đều mất nhan_vien_id và banner vẫn báo 'đầy đủ thông tin nhân sự'.
    """
    staff_list = [
        {"id": "nv_01", "ten": "Lan Nguyễn — Cửa hàng trưởng (SM)"},
        {"id": "nv_02", "ten": "Minh Phạm — Trưởng pha chế (PT)"},
        {"id": "nv_03", "ten": "Mỹ Tạ — Nhân viên ca sáng"},
    ]
    # Tên cốt lõi trước dấu gạch ngang — đủ cả tên đầy đủ và tên gọi
    assert resolve_staff_id("Minh Phạm", staff_list) == "nv_02"
    assert resolve_staff_id("Minh", staff_list) == "nv_02"
    assert resolve_staff_id("Mỹ Tạ", staff_list) == "nv_03"
    assert resolve_staff_id("Lan Nguyễn", staff_list) == "nv_01"
    # Không dấu vẫn khớp
    assert resolve_staff_id("my ta", staff_list) == "nv_03"
    # Không nhầm phần chức danh thành tên người
    assert resolve_staff_id("cửa hàng trưởng", staff_list) is None


def test_clarify_flags_unresolvable_assignee_name() -> None:
    """Tên người nhận cụ thể nhưng không khớp nhân viên nào phải bật can_lam_ro.

    Trước đây nhánh Case C yêu cầu nv_id thật nên tên lạ làm cờ bị tua qua:
    banner xanh 'đầy đủ thông tin' trong khi việc treo sẽ không gắn được người.
    """
    action = {
        "id": "act_x",
        "tieu_de": "Vệ sinh dàn nóng máy ép lạnh",
        "ten_nguoi_nhan": "Minh Phạm",
        "noi_dung_chi_tiet": "",
    }
    # Danh sách nhân sự KHÔNG có ai khớp "Minh Phạm"
    res = clarify_single_action(
        action,
        staff_list=[{"id": "nv_01", "ten": "Lan Nguyễn"}],
        phan_cong={},
        ca_list=[],
    )
    assert res["can_lam_ro"] is True
    assert "minh phạm" in res["van_de_ngu_canh"].lower()
    assert res["nhan_vien_id"] is None


def test_apply_skips_unassigned_action_item_does_not_create_empty_treo() -> None:
    """Khi duyệt, action item chưa có người nhận (hoặc 'Chưa rõ') không được tạo việc treo rỗng.

    Bug gặp thật 2026-10-01: duyệt việc tạo treo_item với nv_id rỗng hoặc không có
    người nhận.
    """
    ql = headers(client, "lan")
    payload = {
        "id": f"meet_unassigned_{uuid.uuid4().hex[:6]}",
        "tieu_de": "Họp thử nghiệm việc rỗng",
        "loai_hop": "giao_ca",
        "tom_tat": "Tóm tắt cuộc họp",
        "action_items": [
            {
                "id": "act_empty_1",
                "tieu_de": "Việc chưa giao cho ai",
                "ten_nguoi_nhan": "Chưa rõ",
                "da_chon": True,
            },
            {
                "id": "act_empty_2",
                "tieu_de": "Việc để trống người nhận hoàn toàn",
                "ten_nguoi_nhan": "",
                "da_chon": True,
            },
            {
                "id": "act_valid_3",
                "tieu_de": "Việc giao cho Lan",
                "ten_nguoi_nhan": "Lan",
                "da_chon": True,
            },
        ],
    }
    res = client.post("/api/v1/meeting/apply", json=payload, headers=ql)
    assert res.status_code == 200, res.text
    body = res.json()
    # Chỉ act_valid_3 được tạo
    assert body["tasks_created"] == 1

    treo = kv_get("treo", [])
    # Việc rỗng không có trong treo
    assert not any("Việc chưa giao cho ai" in t.get("noi_dung", "") for t in treo)
    assert not any("Việc để trống người nhận" in t.get("noi_dung", "") for t in treo)
    # Việc giao cho Lan có trong treo và có nv_id hợp lệ
    lan_task = next((t for t in treo if "Việc giao cho Lan" in t.get("noi_dung", "")), None)
    assert lan_task is not None
    assert lan_task["nv_id"] is not None
    assert lan_task["nv_id"] != ""


def test_tc33_corrupted_audio_file_returns_400_not_500() -> None:
    """TC-33: File âm thanh sai định dạng (.mov đổi đuôi .mp3) hoặc hỏng trả 400 rõ ràng."""
    ql = headers(client, "lan")
    # Disguised .mov container payload
    fake_mov_bytes = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00corrupted_stream_content"
    res = client.post(
        "/api/v1/meeting/process-audio",
        files={"file": ("meeting_audio.mp3", io.BytesIO(fake_mov_bytes), "audio/mp3")},
        data={"meeting_type": "giao_ca"},
        headers=ql,
    )
    assert res.status_code == 400
    assert "Không thể đọc file âm thanh, vui lòng kiểm tra lại định dạng" in res.json()["detail"]


def test_tc34_code_switching_loanwords_action_extraction() -> None:
    """TC-34: Trộn mã Việt-Anh ('check', 'update status', 'follow up') trích xuất đúng việc."""
    staff_list = [
        {"id": "nv_01", "ten": "Tuấn"},
        {"id": "nv_02", "ten": "My"},
        {"id": "nv_03", "ten": "Lan"},
    ]
    transcript = (
        "Quản lý: Tuấn nhớ update status của table 5 trước 17h nhé.\n"
        "Quản lý: My follow up vụ syrup đào với supplier nhé.\n"
        "Quản lý: Lan check giúp anh order này."
    )
    extracted = extract_meeting(text=transcript, staff_list=staff_list, meeting_type="giao_ca")
    actions = extracted.get("action_items", [])
    assert len(actions) >= 3
    titles = [a["tieu_de"] for a in actions]
    assert any("update status" in t.lower() for t in titles)
    assert any("follow up" in t.lower() for t in titles)
    assert any("check" in t.lower() for t in titles)


def test_tc35_server_side_concurrent_race_condition() -> None:
    """TC-35: Race condition thực sự — 2 phiên Quản lý khác nhau gửi apply song song."""
    ql1 = headers(client, "lan")  # Manager 1
    ql2 = headers(client, "hung")  # Manager 2 (Store owner)

    meeting_payload = {
        "id": "meet_concurrent_race",
        "tieu_de": "Họp khẩn cấp giải quyết sự cố",
        "loai_hop": "giao_ca",
        "tom_tat": "Họp khẩn cấp bảo trì máy pha",
        "action_items": [
            {
                "id": "act_race_1",
                "tieu_de": "Thay thế phin lọc cà phê khẩn cấp",
                "nhan_vien_id": "nv_01",
                "ten_nguoi_nhan": "Tuấn",
                "loai_cong_viec": "1_ca",
                "ca_thuc_hien": "Ca Tối",
                "han_chot": "19:00",
                "da_chon": True,
            }
        ],
    }

    def send_apply(auth_header: dict[str, str]) -> int:
        r = client.post("/api/v1/meeting/apply", json=meeting_payload, headers=auth_header)
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(send_apply, ql1)
        f2 = executor.submit(send_apply, ql2)
        status1 = f1.result()
        status2 = f2.result()

    assert status1 == 200
    assert status2 == 200

    # Ensure idempotency: only 1 task created in treo despite 2 parallel managers
    treo = kv_get("treo", [])
    race_tasks = [t for t in treo if "Thay thế phin lọc cà phê khẩn cấp" in t.get("noi_dung", "")]
    assert len(race_tasks) == 1


def test_tc08_khong_lien_quan_meeting_creates_no_junk_tasks() -> None:
    """TC-08: Nội dung không liên quan vận hành quán (World Cup / phim ảnh) không tạo việc rác."""
    ql = headers(client, "lan")
    # Irrelevant meeting conversation
    payload = {
        "text": "Lan: Hôm qua trận bóng đá Real Madrid đá cuốn quá mày ơi.\nTuấn: Ừ tao coi hết hiệp phụ luôn.",
        "meeting_type": "khac",
    }
    extracted = extract_meeting(text=payload["text"], staff_list=[], meeting_type="khac")
    assert extracted.get("khong_lien_quan") is True
    assert len(extracted.get("action_items", [])) == 0
    # Apply meeting with empty or unselected action items
    apply_payload = {
        "id": "meet_irrelevant_football",
        "tieu_de": "Tán gẫu bóng đá",
        "loai_hop": "khac",
        "tom_tat": "Nhân viên tán gẫu về bóng đá, không liên quan vận hành",
        "action_items": [],
    }
    res = client.post("/api/v1/meeting/apply", json=apply_payload, headers=ql)
    assert res.status_code == 200
    assert res.json()["tasks_created"] == 0


def test_tc14_unicode_nfd_nfc_normalization() -> None:
    """TC-14: Chuẩn hóa Unicode tiếng Việt (NFC vs NFD) và khoảng trắng thừa."""
    staff_list = [{"id": "nv_01", "ten": "Nguyễn Văn Tuấn"}]
    # Decomposed NFD string
    nfd_tuan = unicodedata.normalize("NFD", "Tuấn")
    assert resolve_staff_id(nfd_tuan, staff_list) == "nv_01"
    # Extra trailing and leading whitespace
    assert resolve_staff_id("   Tuấn   ", staff_list) == "nv_01"


def test_tc15_xss_injection_payload_handled_safely() -> None:
    """TC-15: Phòng chống Injection Payload (XSS / SQLi trong tên người nhận hoặc tiêu đề)."""
    ql = headers(client, "lan")
    xss_title = "<script>alert('xss_injection')</script>"
    payload = {
        "id": "meet_sec_xss_test",
        "tieu_de": "Kiểm thử bảo mật XSS",
        "loai_hop": "giao_ca",
        "tom_tat": "Kiểm thử phòng chống mã độc",
        "action_items": [
            {
                "id": "act_xss_1",
                "tieu_de": xss_title,
                "nhan_vien_id": "nv_01",
                "ten_nguoi_nhan": "Tuấn",
                "loai_cong_viec": "1_ca",
                "da_chon": True,
            }
        ],
    }
    res = client.post("/api/v1/meeting/apply", json=payload, headers=ql)
    assert res.status_code == 200
    treo = kv_get("treo", [])
    xss_task = next((t for t in treo if xss_title in t.get("noi_dung", "")), None)
    assert xss_task is not None
    # Stored as text safely without crashing or database corruption
    assert xss_task["trang_thai"] == "dang_cho"


def test_tc36_relative_time_anchored_to_recording_timestamp() -> None:
    """TC-36: Mốc thời gian tương đối phải neo theo lúc ghi âm (thoi_gian), không phải datetime.now() của server."""
    # Meeting recorded on Monday Aug 17, 2026 at 09:00 (2026-08-17 is Monday)
    record_time = "2026-08-17T09:00:00+07:00"
    staff_list = [
        {"id": "nv_01", "ten": "Nguyễn Văn Tuấn"},
        {"id": "nv_02", "ten": "Đặng Thị My"},
    ]

    # 1. Spoken cue: "mai làm" / "sáng mai" -> should resolve to Tuesday Aug 18, 2026
    text_tmr = "Tuấn nhớ sáng mai bảo dưỡng máy pha cà phê nhé."
    res_tmr = extract_meeting(
        text_tmr,
        meeting_type="giao_ca",
        staff_list=staff_list,
        thoi_gian=record_time,
    )
    items_tmr = res_tmr.get("action_items", [])
    assert len(items_tmr) >= 1
    assert "2026-08-18 (Thứ Ba)" in items_tmr[0]["han_chot"]

    # 2. Spoken cue: relative weekday "Thứ Năm" -> Monday Aug 17 + 3 days = Thursday Aug 20
    text_thu = "My nhớ Thứ Năm kiểm tra lại tồn kho sirô đào nhé."
    res_thu = extract_meeting(
        text_thu,
        meeting_type="giao_ca",
        staff_list=staff_list,
        thoi_gian=record_time,
    )
    items_thu = res_thu.get("action_items", [])
    assert len(items_thu) >= 1
    assert "2026-08-20 (Thứ Năm)" in items_thu[0]["han_chot"]

    # 3. HTTP Analyze endpoint passing thoi_gian preserves anchor
    ql = headers(client, "lan")
    http_res = client.post(
        "/api/v1/meeting/analyze",
        json={"text": text_tmr, "meeting_type": "giao_ca", "thoi_gian": record_time},
        headers=ql,
    )
    assert http_res.status_code == 200
    body = http_res.json()
    assert body["thoi_gian"] == record_time
    assert "2026-08-18 (Thứ Ba)" in body["action_items"][0]["han_chot"]


def test_tc37_stt_near_miss_levenshtein_matching() -> None:
    """TC-37: STT phiên âm sai gần đúng (near-miss) với khoảng cách Levenshtein."""
    staff_list = [
        {"id": "nv_01", "ten": "Nguyễn Văn Tuấn"},
        {"id": "nv_02", "ten": "Trần Thị Lan"},
    ]

    # Direct helper checks
    # "Toán" vs "Tuấn" (Levenshtein distance = 1 on unaccented "toan" vs "tuan")
    sid, is_near = resolve_staff_id_with_meta("Toán", staff_list, allow_fuzzy_stt=True)
    assert sid == "nv_01"
    assert is_near is True

    # "Loan" vs "Lan" (Levenshtein distance = 1 on "loan" vs "lan")
    sid_lan, is_near_lan = resolve_staff_id_with_meta("Loan", staff_list, allow_fuzzy_stt=True)
    assert sid_lan == "nv_02"
    assert is_near_lan is True

    # When allow_fuzzy_stt=False (manual typing / text log), do NOT match near-miss
    sid_manual, is_near_manual = resolve_staff_id_with_meta("Toán", staff_list, allow_fuzzy_stt=False)
    assert sid_manual is None
    assert is_near_manual is False

    # In extract_meeting via microphone
    spoken_text = "Toán kiểm tra nhiệt độ tủ đông nhé."
    res = extract_meeting(
        spoken_text,
        staff_list=staff_list,
        audio_source="microphone",
    )
    items = res.get("action_items", [])
    assert len(items) >= 1
    item = items[0]
    assert item["nhan_vien_id"] == "nv_01"
    assert item["stt_near_miss"] is True
    assert item["can_lam_ro"] is True
    assert "STT nghe gần đúng" in item["van_de_ngu_canh"]


def test_tc38_multi_action_compound_sentence_splitting() -> None:
    """TC-38: Tách câu phức hợp phân công nhiều người trong 1 câu (Multi-action Compound Line)."""
    staff_list = [
        {"id": "nv_01", "ten": "Nguyễn Văn Tuấn"},
        {"id": "nv_02", "ten": "Trần Thị Lan"},
        {"id": "nv_03", "ten": "Đặng Thị My"},
    ]
    compound_text = "Tuấn thay ron máy pha cà phê, Lan lau kính quầy bar, My kiểm tra tủ mát."
    res = extract_meeting(
        compound_text,
        staff_list=staff_list,
    )
    items = res.get("action_items", [])
    # Must be split into 3 distinct tasks
    assert len(items) == 3
    assignees = [it["nhan_vien_id"] for it in items]
    assert "nv_01" in assignees
    assert "nv_02" in assignees
    assert "nv_03" in assignees
    assert any("thay ron" in it["tieu_de"] for it in items)
    assert any("lau kính" in it["tieu_de"] for it in items)
    assert any("kiểm tra tủ mát" in it["tieu_de"] for it in items)


def test_tc39_spoken_self_correction_assignee() -> None:
    """TC-39: Phát hiện câu nói đính chính / sửa miệng giữa câu (Spoken self-correction)."""
    staff_list = [
        {"id": "nv_01", "ten": "Nguyễn Văn Tuấn"},
        {"id": "nv_02", "ten": "Trần Thị Lan"},
        {"id": "nv_03", "ten": "Đặng Thị My"},
    ]

    # Pattern 1: "à thôi để..."
    text_1 = "Tuấn dọn bàn khu A... à thôi để Lan dọn nhé."
    res_1 = extract_meeting(text_1, staff_list=staff_list)
    items_1 = res_1.get("action_items", [])
    assert len(items_1) >= 1
    # Assignee must be Lan (nv_02), NOT Tuấn (nv_01)!
    assert items_1[0]["nhan_vien_id"] == "nv_02"
    assert items_1[0]["ten_nguoi_nhan"] == "Lan"

    # Pattern 2: "thôi nhầm để..."
    text_2 = "Giao cho Tuấn kiểm kho, thôi nhầm để My kiểm tra tủ lạnh."
    res_2 = extract_meeting(text_2, staff_list=staff_list)
    items_2 = res_2.get("action_items", [])
    assert len(items_2) >= 1
    # Assignee must be My (nv_03)
    assert items_2[0]["nhan_vien_id"] == "nv_03"


def test_tc40_hallucination_grounding_guardrail() -> None:
    """TC-40: Hallucination Guardrail — Action Item phải có căn cứ trong transcript thoại."""
    transcript = "Hôm nay giao ca bình thường, Tuấn nhớ lau máy pha cà phê trước 16h."

    # Check grounding helper
    assert _is_grounded_in_transcript("Tuấn lau máy pha cà phê", transcript) is True
    assert _is_grounded_in_transcript("Sơn lại tường phòng lạnh và lắp điều hòa mới", transcript) is False

    # Check extract_meeting action item metadata
    res = extract_meeting(transcript, staff_list=[{"id": "nv_01", "ten": "Nguyễn Văn Tuấn"}])
    items = res.get("action_items", [])
    assert len(items) >= 1
    assert items[0]["khong_co_can_cu"] is False
    assert items[0]["nguon_cau_noi"] != ""


def test_tc41_audit_trail_recorded_on_apply() -> None:
    """TC-41: Tự động ghi chép Audit Trail (audit_add / audit_list) khi áp dụng biên bản cuộc họp."""
    ql = headers(client, "lan")
    meet_id = "meet_audit_test_tc41"
    apply_payload = {
        "id": meet_id,
        "tieu_de": "Họp thử nghiệm Audit Trail",
        "loai_hop": "giao_ca",
        "tom_tat": "Họp thử nghiệm ghi nhận vết kiểm toán hệ thống",
        "action_items": [
            {
                "id": "act_audit_1",
                "tieu_de": "Vệ sinh khay hứng nước máy pha",
                "nhan_vien_id": "nv_01",
                "ten_nguoi_nhan": "Tuấn",
                "loai_cong_viec": "1_ca",
                "ca_thuc_hien": "Ca Sáng",
                "da_chon": True,
            }
        ],
    }
    res = client.post("/api/v1/meeting/apply", json=apply_payload, headers=ql)
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Verify audit log in SQLite
    logs = audit_list()
    apply_entry = next(
        (
            entry
            for entry in logs
            if entry.get("hanh") == "meeting.approve"
            and entry.get("payload", {}).get("meeting_id") == meet_id
        ),
        None,
    )
    assert apply_entry is not None
    assert apply_entry["ai"] in ("lan", "nv_01")
    assert apply_entry["payload"]["tasks_created"] == 1
    assert "at" in apply_entry


def test_tc42_meeting_rollback_recalls_tasks_and_proposals() -> None:
    """TC-42: Rollback biên bản cuộc họp (POST /api/v1/meetings/{id}/rollback)."""
    ql = headers(client, "lan")
    meet_id = "meet_rollback_tc42"
    apply_payload = {
        "id": meet_id,
        "tieu_de": "Họp giao ca cần rollback",
        "loai_hop": "giao_ca",
        "tom_tat": "Cuộc họp áp dụng nhầm nội dung",
        "action_items": [
            {
                "id": "act_rb_1",
                "tieu_de": "Việc cần thu hồi 1",
                "nhan_vien_id": "nv_01",
                "ten_nguoi_nhan": "Tuấn",
                "loai_cong_viec": "1_ca",
                "da_chon": True,
            },
            {
                "id": "act_rb_2",
                "tieu_de": "Việc đã làm xong trước rollback",
                "nhan_vien_id": "nv_01",
                "ten_nguoi_nhan": "Tuấn",
                "loai_cong_viec": "1_ca",
                "da_chon": True,
            },
        ],
        "de_xuat_sop": [
            {
                "id": "sop_rb_1",
                "quy_trinh_lien_quan": "Pha chế Trà Sen",
                "noi_dung_thay_doi": "Giảm đường",
                "ly_do": "Khách chê ngọt",
            }
        ],
        "de_xuat_phe_duyet": [
            {
                "id": "prop_leave_rb_1",
                "loai_de_xuat": "dieu_chinh_lich",
                "tieu_de": "Xin nghỉ ca",
                "noi_dung": "Xin nghỉ ca sáng T4 bận thi",
                "chi_tiet_lich": {
                    "nhan_vien_id": "nv_01",
                    "loai": "xin_nghi",
                    "thu": "T4",
                    "khung": "sang",
                    "ly_do": "Bận thi",
                },
            }
        ],
    }
    r_apply = client.post("/api/v1/meeting/apply", json=apply_payload, headers=ql)
    assert r_apply.status_code == 200

    # Mark act_rb_2 as completed in treo
    def mark_done(cur: list) -> list:
        for t in cur:
            if isinstance(t, dict) and "Việc đã làm xong trước rollback" in t.get("noi_dung", ""):
                t["trang_thai"] = "da_xong"
        return cur

    kv_mutate("treo", mark_done, [])

    # 1. Non-manager forbidden
    nv = headers(client, "minh")
    r_forbid = client.post(f"/api/v1/meetings/{meet_id}/rollback", headers=nv)
    assert r_forbid.status_code == 403

    # 2. Manager rolls back successfully
    r_rb = client.post(f"/api/v1/meetings/{meet_id}/rollback", headers=ql)
    assert r_rb.status_code == 200
    rb_data = r_rb.json()
    assert rb_data["ok"] is True
    assert rb_data["recalled_tasks"] == 1  # only unfinished task recalled
    assert rb_data["recalled_sop"] == 1
    assert rb_data["recalled_leaves"] == 1

    # Verify unfinished task removed from treo
    treo = kv_get("treo", [])
    assert not any("Việc cần thu hồi 1" in t.get("noi_dung", "") for t in treo)

    # Verify finished task preserved with note
    done_task = next(
        (t for t in treo if "Việc đã làm xong trước rollback" in t.get("noi_dung", "")),
        None,
    )
    assert done_task is not None
    assert "Biên bản cuộc họp đã rollback" in done_task.get("ghi_chu", "")

    # Verify SOP proposal removed
    sop_list = kv_get("sop_de_xuat", [])
    assert not any(s.get("meeting_id") == meet_id for s in sop_list)

    # Verify inbox leaves removed
    inbox = kv_get("inbox_rang_buoc", [])
    assert not any(isinstance(x, dict) and x.get("meeting_id") == meet_id for x in inbox)

    # Verify audit log contains rollback_cuoc_hop
    logs = audit_list()
    rb_entry = next(
        (
            entry
            for entry in logs
            if entry.get("hanh") == "meeting.rollback"
            and entry.get("payload", {}).get("meeting_id") == meet_id
        ),
        None,
    )
    assert rb_entry is not None


def test_tc43_dynamic_24h_night_shift_template() -> None:
    """TC-43: Ma trận ca động cho quán 24h (Ca Đêm) & kiểm tra ngày lễ đóng cửa."""
    ca_24h = [
        {"id": "c_sang", "thu": "T2", "khung": "sang", "bat_dau": "06:00", "ket_thuc": "12:00"},
        {"id": "c_chieu", "thu": "T2", "khung": "chieu", "bat_dau": "12:00", "ket_thuc": "18:00"},
        {"id": "c_toi", "thu": "T2", "khung": "toi", "bat_dau": "18:00", "ket_thuc": "24:00"},
        {"id": "c_dem", "thu": "T2", "khung": "dem", "bat_dau": "00:00", "ket_thuc": "06:00"},
    ]
    phan_cong = {
        "c_sang": ["nv_01"],
        "c_dem": ["nv_night"],
    }
    shifts = resolve_staff_shifts("nv_night", phan_cong, ca_24h)
    assert len(shifts) == 1
    assert shifts[0]["khung"] == "dem"
    assert "Ca Đêm" in shifts[0]["label"]

    # Clarify action for night shift staff
    act_night = {
        "id": "act_night_1",
        "tieu_de": "Kiểm tra hệ thống lạnh lúc 3h sáng",
        "nhan_vien_id": "nv_night",
        "ten_nguoi_nhan": "Kỳ",
        "loai_cong_viec": "1_ca",
    }
    clarified = clarify_single_action(
        act_night,
        staff_list=[{"id": "nv_night", "ten": "Nguyễn Văn Kỳ"}],
        phan_cong=phan_cong,
        ca_list=ca_24h,
    )
    assert "Ca Đêm" in clarified["ca_thuc_hien"]
    assert clarified["can_lam_ro"] is False


def test_tc44_optimistic_locking_draft_conflict_409() -> None:
    """TC-44: Xung đột phiên bản đồng thời (Optimistic Locking & 409 Conflict)."""
    ql = headers(client, "lan")
    meet_id = "meet_concurrent_draft_tc44"

    # Setup draft at version 1
    initial_draft = {
        "id": meet_id,
        "tieu_de": "Bản thảo cuộc họp ban đầu",
        "loai_hop": "giao_ca",
        "tom_tat": "Tóm tắt ban đầu",
        "phien_ban": 1,
        "action_items": [],
    }
    r0 = client.put(f"/api/v1/meetings/{meet_id}/draft", json=initial_draft, headers=ql)
    assert r0.status_code == 200
    assert r0.json()["phien_ban"] == 1

    # User A updates draft with version 1 -> succeeds, increments to version 2
    update_a = {
        "id": meet_id,
        "tieu_de": "Bản thảo đã sửa bởi User A",
        "loai_hop": "giao_ca",
        "tom_tat": "Tóm tắt sửa đổi bởi User A",
        "phien_ban": 1,
        "action_items": [],
    }
    r_a = client.put(f"/api/v1/meetings/{meet_id}/draft", json=update_a, headers=ql)
    assert r_a.status_code == 200
    assert r_a.json()["phien_ban"] == 2

    # User B tries to save with stale version 1 -> 409 Conflict
    update_b = {
        "id": meet_id,
        "tieu_de": "Bản thảo xung đột bởi User B",
        "loai_hop": "giao_ca",
        "tom_tat": "Tóm tắt sửa đổi bởi User B",
        "phien_ban": 1,
        "action_items": [],
    }
    r_b = client.put(f"/api/v1/meetings/{meet_id}/draft", json=update_b, headers=ql)
    assert r_b.status_code == 409
    assert "Xung đột phiên bản" in r_b.json()["detail"]

    # User B fetches/accepts version 2 and re-submits -> succeeds, increments to version 3
    update_b["phien_ban"] = 2
    r_b_retry = client.put(f"/api/v1/meetings/{meet_id}/draft", json=update_b, headers=ql)
    assert r_b_retry.status_code == 200
    assert r_b_retry.json()["phien_ban"] == 3


