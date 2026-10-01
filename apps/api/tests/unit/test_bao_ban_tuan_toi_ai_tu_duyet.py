# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Hồi quy: "nhân viên báo bận MỘT CA Ở TUẦN TỚI → AI tự duyệt + xếp lịch đúng".

Kịch bản nghiệp vụ được khoá ở đây (người dùng yêu cầu kiểm thử):

  1. Nhân viên nhắn tin (Zalo/Telegram/Facebook) báo bận **một ca** ở **tuần tới**.
  2. AI tự duyệt (autopilot) — KHÔNG cần quản lý bấm nút.
  3. Lượt xếp lịch của **tuần tới** phải thấy ràng buộc đó: nhân viên KHÔNG bị
     xếp vào đúng ca bị bận, và **ca khác trong cùng ngày vẫn xếp được** (bận 1
     ca không được biến thành nghỉ cả ngày).

Hai lỗi thật đã từng chặn quy trình này:

  A. `channels.process_inbound` gọi `classify(...)` mà KHÔNG truyền
     `base_iso_week` → `_extract_tuan` rơi về mốc mặc định cứng "2026-W01",
     nên "tuần sau" luôn ra "2026-W02" bất kể hôm nay là tuần nào. Ràng buộc
     được ghi vào một tuần vô nghĩa, lượt xếp lịch thật của tuần tới không thấy
     → nhân viên vẫn bị xếp đúng ca đã báo bận.
     (Đường web `/api/v1/msg/classify` đã truyền mốc này từ trước — bug QA đợt 4
     — nhưng đường kênh tin thì chưa.)

  B. `_decide_inbox_item` xét cổng khoá theo trạng thái của TUẦN ĐANG LÀM VIỆC
     thay vì TUẦN ĐÍCH của ràng buộc. Khi lịch tuần này đã công bố mà nhân viên
     báo bận cho tuần sau (còn nháp), AI trả `LIFECYCLE_LOCKED` và không xếp lại
     tuần đích — dù tuần đó hoàn toàn được phép xếp lại.

  C. Cách nói tự nhiên nhất — "em bận ca sáng thứ 5" — KHÔNG khớp từ khoá
     tier-1 nào (không có chữ "nghỉ"), nên rơi về `khac` và tin nhắn bị bỏ qua
     hoàn toàn. Đã bổ sung `_BAO_BAN_REGEX` CÓ RÀNG BUỘC trong `ag_msg.extract`
     để vừa bắt được câu báo bận, vừa không đổi nhãn câu "…chiều đó đổi với Huy"
     (nhãn vàng `doi_ca`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ca_agents.ag_msg.extract import classify
from ca_agents.messaging import InboundMessage
from ca_api.interfaces.http.channels import process_inbound
from ca_api.interfaces.http.main import app
from ca_api.interfaces.http.sprint45 import _run_solver
from ca_api.persist import kv_get, kv_mutate, kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

# Nặng solver CP-SAT thật — chạy ở job unit-slow.
pytestmark = pytest.mark.slow

client = TestClient(app)


def _iso_week(offset_weeks: int = 0) -> str:
    """Tuần ISO thật của đồng hồ (offset theo tuần) — không hardcode."""
    day = datetime.now(UTC).date() + timedelta(weeks=offset_weeks)
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _clear_week_state(*weeks: str) -> None:
    """Dọn state của đúng các tuần sẽ dùng, để kết quả không phụ thuộc thứ tự bài."""
    for khoa in (
        "nghi_phep",
        "nghi_phep_by_week",
        "phan_cong",
        "phan_cong_by_week",
        "tkb_nv",
        "tkb_nv_by_week",
        "lich_tuan_lifecycle_by_week",
        "lich_tuan_results_by_week",
        "pins_by_week",
        "roster_nv_status",
    ):
        kv_mutate(
            khoa,
            lambda d, ws=set(weeks): {k: v for k, v in d.items() if k not in ws}
            if isinstance(d, dict)
            else d,
            {},
        )


def _bind(nv_user: str, external_id: str) -> str:
    """Kết nối kênh cho một tài khoản, trả về nv_id đã bind."""
    h = headers(client, nv_user)
    code = client.post("/api/v1/channels/bind/issue", headers=h).json()["code"]
    bound = process_inbound(
        InboundMessage(text=f"/bind {code}", channel="zalo", external_user_id=external_id),
        reply_backend="replay",
    )
    assert bound["ok"] is True and bound["hanh"] == "bind"
    return str(bound["nv_id"])


def test_kenh_tin_tuan_sau_tinh_tu_tuan_hien_tai() -> None:
    """LỖI A: tin nhắn kênh phải neo "tuần sau" vào tuần THẬT, không phải W01.

    Chạy trước khi sửa: ràng buộc mang `tuan_id = "2026-W02"` bất kể hôm nay là
    tuần nào (vì `classify` mặc định mốc cứng "2026-W01").
    """
    cur, nxt = _iso_week(0), _iso_week(1)
    assert cur != nxt

    r = classify("Tuần sau em bận ca sáng thứ 5", base_iso_week=cur)
    assert r.rang_buoc["tuan_id"] == nxt, (
        f"kỳ vọng tuần sau = {nxt}, nhận {r.rang_buoc['tuan_id']}"
    )

    # Đường KÊNH TIN thật (không phải chỉ hàm classify) phải cho cùng kết quả.
    _clear_week_state(cur, nxt)
    nv_id = _bind("minh", "z_tuan_that")
    enq = process_inbound(
        InboundMessage(
            text="Tuần sau em bận ca sáng thứ 5, xin nghỉ ca đó ạ",
            channel="zalo",
            external_user_id="z_tuan_that",
        ),
        reply_backend="replay",
    )
    assert enq["hanh"] == "enqueue", enq
    item = enq["item"]
    assert item["nv_id"] == nv_id
    assert item["rang_buoc"]["tuan_id"] == nxt, (
        "kênh tin ghi ràng buộc vào tuần SAI — lượt xếp lịch tuần tới sẽ không thấy nó"
    )
    assert item["rang_buoc"]["thu"] == "T5"
    assert (item["rang_buoc"].get("start"), item["rang_buoc"].get("end")) == ("07:00", "12:00")


def test_ai_tu_duyet_va_xep_lich_tuan_toi_khong_trung_ca_ban(
    monkeypatch: pytest.MonkeyPatch,
    _du_nhan_vien_xep_lich: None,
) -> None:
    """LUỒNG ĐẦY ĐỦ: báo bận 1 ca tuần tới → AI tự duyệt → xếp lịch không trùng ca đó.

    Bất biến được khẳng định:
      (a) AI tự duyệt, KHÔNG cần quản lý bấm nút (trang hộp thư chỉ còn để xem);
      (b) nhân viên KHÔNG nằm trong đúng ca bị bận ở tuần tới;
      (c) nhân viên VẪN có ca khác trong cùng ngày — bận 1 ca ≠ nghỉ cả ngày.
    """
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    cur, nxt = _iso_week(0), _iso_week(1)
    _clear_week_state(cur, nxt)

    nv_id = _bind("minh", "z_full_flow")
    enq = process_inbound(
        InboundMessage(
            text="Tuần sau em bận ca sáng thứ 5, xin nghỉ ca đó ạ",
            channel="zalo",
            external_user_id="z_full_flow",
        ),
        reply_backend="replay",
    )
    item_id = enq["item"]["id"]

    # (a) AI đã tự duyệt ngay khi ghi vào hộp thư — không cần ai bấm nút.
    item = next(t for t in kv_get("inbox_rang_buoc", []) if t.get("id") == item_id)
    assert item["trang_thai"] == "duyet", (
        "AI chưa tự duyệt — nhân viên sẽ thấy yêu cầu treo ở hộp thư"
    )
    hieu_luc = item["hieu_luc"]
    assert hieu_luc["loai"] == "rang_buoc_cho_solver"
    assert hieu_luc["tuan_id"] == nxt
    assert (hieu_luc.get("start"), hieu_luc.get("end")) == ("07:00", "12:00")

    # (b)+(c) Lượt xếp lịch của TUẦN TỚI phải tôn trọng ràng buộc.
    sol = _run_solver(nxt)
    assert sol["ok"] is True, sol.get("danh_sach_xung_dot")

    from ca_solver import build_lich_input

    inp = build_lich_input()
    phan = (kv_get("phan_cong_by_week", {}) or {}).get(nxt) or {}
    assert phan, f"không có phân công cho {nxt}"

    t5 = [c for c, m in inp.ca_meta.items() if m.get("thu") == "T5"]
    ca_sang_t5 = [c for c in t5 if str(inp.ca_meta[c].get("bat_dau") or "").startswith("07")]
    ca_khac_t5 = [c for c in t5 if c not in ca_sang_t5]
    assert ca_sang_t5 and ca_khac_t5, "fixture phải có cả ca sáng và ca khác trong ngày T5"

    for ca_id in ca_sang_t5:
        assert nv_id not in (phan.get(ca_id) or []), (
            f"{nv_id} vẫn bị xếp vào ca sáng T5 {ca_id} dù đã báo bận"
        )

    # KHÔNG khẳng định "nhân viên phải có mặt ở ca khác trong ngày T5": CP-SAT
    # chỉ ràng buộc tối thiểu người/ca, không ràng buộc "mỗi người phải có ca",
    # nên đòi hỏi đó sẽ là test giòn (phụ thuộc nghiệm solver chọn). Điều kiện
    # thật của yêu cầu — "bận 1 ca KHÔNG được thành nghỉ cả ngày" — được khoá ở
    # `test_ban_mot_ca_chi_chan_dung_khung_do_o_tang_solver_input` bên dưới, nơi
    # kiểm trực tiếp dữ liệu nạp vào solver thay vì đoán qua nghiệm.


def test_ban_mot_ca_chi_chan_dung_khung_do_o_tang_solver_input(
    monkeypatch: pytest.MonkeyPatch,
    _du_nhan_vien_xep_lich: None,
) -> None:
    """Bất biến cốt lõi ở TẦNG INPUT: bận MỘT ca chỉ chặn đúng khung đó.

    Vì sao kiểm ở đây thay vì nhìn nghiệm solver: yêu cầu "nhân viên vẫn làm được
    ca khác trong cùng ngày" phụ thuộc dữ liệu nạp vào CP-SAT, không phải vào
    việc nghiệm tối ưu có chọn đúng người đó hay không (CP-SAT không bắt buộc
    mỗi nhân viên phải có ca). Kiểm ở input là vừa chắc chắn, vừa không giòn.

    Chạy trước khi sửa: ràng buộc "xin_nghi có khung giờ" bị ép về `nghi_phep`
    theo (nv, ngày) → xoá CẢ NGÀY, nhân viên mất luôn ca chiều/tối cùng ngày.
    """
    from ca_api.services import solver_adapter
    from ca_solver.model import LichInput, SolveResult

    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    cur, nxt = _iso_week(0), _iso_week(1)
    _clear_week_state(cur, nxt)

    nv_id = _bind("minh", "z_tang_input")
    enq = process_inbound(
        InboundMessage(
            text="Tuần sau em bận ca sáng thứ 5, xin nghỉ ca đó ạ",
            channel="zalo",
            external_user_id="z_tang_input",
        ),
        reply_backend="replay",
    )
    assert enq["item"]["rang_buoc"]["tuan_id"] == nxt

    captured: list[LichInput] = []

    def capture(data: LichInput, *, time_limit_s: float) -> SolveResult:
        del time_limit_s
        captured.append(data)
        return SolveResult(ok=False, status="CAPTURED")

    monkeypatch.setattr(solver_adapter, "solve_cpsat", capture)
    _run_solver(nxt)

    assert captured, "solver không được gọi cho tuần đích"
    data = captured[0]

    # (1) KHÔNG bị coi là nghỉ cả ngày.
    assert (nv_id, "T5") not in data.nghi_phep, (
        f"{nv_id} bị đánh dấu nghỉ CẢ NGÀY T5 — bận 1 ca không được xoá cả ngày"
    )
    # (2) Khung bận được nạp đúng một khoảng, đúng ca sáng.
    blocks_t5 = [b for b in data.tkb.get(nv_id, []) if b[0] == "T5"]
    assert ("T5", "07:00", "12:00") in blocks_t5, (
        f"khung bận ca sáng T5 không được nạp vào solver: {blocks_t5}"
    )
    # (3) Khung bận chỉ phủ ca sáng — ca chiều/tối cùng ngày vẫn khả dụng.
    for thu, start, end in blocks_t5:
        assert thu == "T5" and start == "07:00" and end == "12:00"


def test_bao_ban_tuan_sau_khong_bi_chan_boi_lich_tuan_nay_da_cong_bo(
    monkeypatch: pytest.MonkeyPatch,
    _du_nhan_vien_xep_lich: None,
) -> None:
    """LỖI B: tuần này đã công bố KHÔNG được chặn việc xếp lại TUẦN SAU còn nháp.

    Chạy trước khi sửa: `tuan_dong_xep_lich.status == "LIFECYCLE_LOCKED"` và
    không có phân công nào cho tuần đích — AI từ chối xếp lịch dù tuần đó nháp.

    Lưu ý tầng: `tu_dong_xep_lich` nằm trong GIÁ TRỊ TRẢ VỀ của quyết định
    (`_decide_inbox_item` → `auto_process`), không được ghi vào bản ghi kv của
    hộp thư — nên phải đọc từ kết quả gọi, không đọc `kv_get`.
    """
    from ca_api.services.inbox_autopilot import auto_process

    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    cur, nxt = _iso_week(0), _iso_week(1)
    _clear_week_state(cur, nxt)

    # Tuần hiện tại: ĐÃ công bố (lịch thật đang chạy). Tuần tới: còn nháp.
    kv_set(
        "lich_tuan_lifecycle_by_week",
        {
            cur: {"tuan_iso": cur, "trang_thai": "da_cong_bo", "nguon": "quan"},
            nxt: {"tuan_iso": nxt, "trang_thai": "nhap", "nguon": "quan"},
        },
    )
    kv_set("lich_tuan_lifecycle", {"tuan_iso": cur, "trang_thai": "da_cong_bo", "nguon": "quan"})
    kv_set("lifecycle", {"tuan_iso": cur, "trang_thai": "da_cong_bo", "nguon": "quan"})

    item_id = "test_bao_ban_tuan_sau_qua_cong"
    kv_set(
        "inbox_rang_buoc",
        [
            {
                "id": item_id,
                "agent": "ag_msg",
                "tom_tat": "Tuần sau bận ca sáng T5",
                "trang_thai": "cho_duyet",
                "nguon": "zalo",
                "y_dinh": "xin_nghi",
                "do_tin_cay": 0.86,
                "nv_id": "nv_01",
                "rang_buoc": {"thu": "T5", "start": "07:00", "end": "12:00", "tuan_id": nxt},
            }
        ],
    )

    decisions = auto_process()
    assert decisions and decisions[0]["ok"] is True, decisions

    item = next(t for t in kv_get("inbox_rang_buoc", []) if t.get("id") == item_id)
    assert item["trang_thai"] == "duyet"

    solver = (decisions[0].get("result") or {}).get("tu_dong_xep_lich") or {}
    assert solver.get("status") != "LIFECYCLE_LOCKED", (
        "tuần ĐÍCH còn nháp nhưng AI vẫn bị chặn bởi trạng thái tuần hiện tại"
    )
    assert solver.get("ok") is True, solver

    phan = (kv_get("phan_cong_by_week", {}) or {}).get(nxt) or {}
    assert phan, f"tuần đích {nxt} không được xếp lịch"

    # Tuần đích chuyển sang chờ duyệt, còn tuần đang công bố GIỮ NGUYÊN.
    by_week = kv_get("lich_tuan_lifecycle_by_week", {}) or {}
    assert by_week[nxt]["trang_thai"] == "cho_duyet"
    assert by_week[cur]["trang_thai"] == "da_cong_bo", (
        "trạng thái tuần đang công bố bị ghi đè khi xếp lịch cho tuần khác"
    )
    # Con trỏ tuần làm việc (khoá toàn cục) cũng không được nhảy sang tuần đích.
    assert str((kv_get("lich_tuan_lifecycle", {}) or {}).get("tuan_iso")) == cur, (
        "con trỏ 'tuần hiện tại' bị đổi sang tuần đích"
    )

    # Và LỊCH THẬT của tuần đang công bố không bị solver ghi đè.
    vi_pham = [
        c for c, nvs in ((kv_get("phan_cong_by_week", {}) or {}).get(cur) or {}).items() if nvs
    ]
    assert not vi_pham, f"lịch tuần đã công bố bị thay đổi: {vi_pham[:3]}"


def test_lich_tuan_da_cong_bo_van_bi_chan_dung_nhu_thiet_ke(
    monkeypatch: pytest.MonkeyPatch,
    _du_nhan_vien_xep_lich: None,
) -> None:
    """Chốt ngược: ràng buộc thuộc CHÍNH tuần đã công bố thì VẪN bị khoá.

    Đảm bảo việc sửa LỖI B không nới lỏng bảo vệ "không tự sửa lịch đã công bố".
    """
    from ca_api.services.inbox_autopilot import auto_process

    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    cur = _iso_week(0)
    _clear_week_state(cur)

    kv_set(
        "lich_tuan_lifecycle_by_week",
        {cur: {"tuan_iso": cur, "trang_thai": "da_cong_bo", "nguon": "quan"}},
    )
    kv_set("lich_tuan_lifecycle", {"tuan_iso": cur, "trang_thai": "da_cong_bo", "nguon": "quan"})
    kv_set("lifecycle", {"tuan_iso": cur, "trang_thai": "da_cong_bo", "nguon": "quan"})

    item_id = "test_bao_ban_tuan_nay_khoa"
    kv_set(
        "inbox_rang_buoc",
        [
            {
                "id": item_id,
                "agent": "ag_msg",
                "tom_tat": "Bận ca sáng T5 tuần này",
                "trang_thai": "cho_duyet",
                "nguon": "zalo",
                "y_dinh": "xin_nghi",
                "do_tin_cay": 0.86,
                "nv_id": "nv_01",
                "rang_buoc": {"thu": "T5", "start": "07:00", "end": "12:00", "tuan_id": cur},
            }
        ],
    )

    decisions = auto_process()

    item = next(t for t in kv_get("inbox_rang_buoc", []) if t.get("id") == item_id)
    # Yêu cầu VẪN được duyệt (ràng buộc có hiệu lực cho lượt xếp sau)…
    assert item["trang_thai"] == "duyet"
    # …nhưng KHÔNG tự sửa lịch đã công bố.
    solver = (decisions[0].get("result") or {}).get("tu_dong_xep_lich") or {}
    assert solver.get("status") == "LIFECYCLE_LOCKED", solver
    assert solver.get("ok") is False
    assert not ((kv_get("phan_cong_by_week", {}) or {}).get(cur) or {}), (
        "lịch đã công bố bị solver ghi đè"
    )
