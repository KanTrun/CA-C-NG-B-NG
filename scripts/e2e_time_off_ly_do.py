#!/usr/bin/env python
"""E2E qua HTTP thật: nhân viên xin nghỉ 1 buổi — lý do phải rõ, ràng buộc phải áp.

Bổ sung cho `scripts/e2e_http_copilot.py` (bộ phủ 33 intent + phân quyền, chạy
với tài khoản QUẢN LÝ): script này đi đúng vai NHÂN VIÊN và kiểm chứng chuỗi
hai lượt — lượt 1 copilot phải HỎI LÝ DO, lượt 2 mới ra đề xuất — cùng việc lý
do có tới tay quản lý trong hộp thư và có thực sự loại nv khỏi ca đó trong lịch.

Cách chạy (stack đã dựng bằng `scripts/docker_stack.py up`):

    docker cp scripts/e2e_time_off_ly_do.py nhipquan-api-1:/tmp/
    docker exec nhipquan-api-1 python /tmp/e2e_time_off_ly_do.py

Lưu ý: `/api/v1/inbox/rang-buoc` chỉ QUẢN LÝ được đọc (nhân viên gọi là 403).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("E2E_BASE", "http://localhost:8000").rstrip("/")
PASSWORD = os.environ.get("NHIPQUAN_E2E_PASSWORD", "nhipquan")

# (ngay_offset) -> thứ trong tuần, theo cách sinh lịch của repo: offset 1 = T2.
_OFFSET_TO_THU = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}


def call(
    path: str,
    body: dict | None = None,
    token: str | None = None,
    method: str = "POST",
    timeout: int = 120,
) -> tuple[int, dict]:
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def login(username: str) -> str:
    _, out = call("/api/v1/auth/login", {"username": username, "password": PASSWORD})
    return str(out.get("token") or out.get("access_token") or "")


def ca_theo_thu_khung(ca: list, thu: str, khung: str) -> list[str]:
    return [
        str(c.get("id"))
        for c in ca
        if isinstance(c, dict)
        and _OFFSET_TO_THU.get(c.get("ngay_offset")) == thu
        and c.get("khung") == khung
    ]


def main() -> int:
    nhan_vien, quan_ly = login("minh"), login("lan")
    print(f"== dang nhap == nhan_vien={bool(nhan_vien)} quan_ly={bool(quan_ly)}")
    if not nhan_vien or not quan_ly:
        print("FAIL: khong dang nhap duoc (da seed du lieu chua?)")
        return 1

    results: dict[str, bool] = {}

    # ── 1. NV xin nghỉ nhưng KHÔNG nêu lý do → copilot phải hỏi, không tạo đơn.
    print("\n== 1. 'Tôi bận buổi chiều thứ 5' (chưa nêu lý do) ==")
    _, r1 = call(
        "/api/v1/copilot/message",
        {"message": "Tôi bận buổi chiều thứ 5", "channel": "web"},
        nhan_vien,
    )
    print(f"   intent={r1.get('intent')}  proposal={'CO' if r1.get('action_proposal') else 'KHONG CO'}")
    print(f"   reply={str(r1.get('reply_text') or '')[:130]}")
    results["thieu_ly_do_phai_hoi"] = (
        r1.get("action_proposal") is None and "lý do" in str(r1.get("reply_text") or "")
    )

    # ── 2. NV trả lời lý do ở lượt 2 → ra đề xuất, giữ ngày + ca của lượt 1.
    print("\n== 2. 'di kham bệnh' (lượt trả lời) ==")
    _, r2 = call(
        "/api/v1/copilot/message",
        {
            "message": "di kham bệnh",
            "channel": "web",
            "recent_messages": ["Tôi bận buổi chiều thứ 5"],
            "cho_phep_noi_ly_do": True,
        },
        nhan_vien,
    )
    proposal = r2.get("action_proposal")
    print(f"   intent={r2.get('intent')}  proposal={'CO' if proposal else 'KHONG CO'}")
    diff = proposal.get("payload_diff") if proposal else {}
    print(f"   payload: thu={diff.get('thu')!r} {diff.get('start')}-{diff.get('end')} ly_do={diff.get('ly_do')!r}")
    results["giu_ngay_ca_va_ly_do"] = bool(
        proposal
        and diff.get("thu") == "T5"
        and (diff.get("start"), diff.get("end")) == ("12:00", "17:30")
        and diff.get("ly_do") == "di kham bệnh"
    )

    # ── 3. Duyệt → đơn phải tới hộp thư với lý do THẬT (không phải "bận").
    print("\n== 3. duyệt đơn, xem hộp thư bằng tài khoản quản lý ==")
    if proposal:
        st, _ = call(
            "/api/v1/copilot/execute-action",
            {"action_id": proposal["action_id"], "decision": "approve"},
            nhan_vien,
            timeout=600,
        )
        t0 = time.time()
        st, inbox = call("/api/v1/inbox/rang-buoc", method="GET", token=quan_ly, timeout=600)
        print(f"   execute={st}  GET inbox/rang-buoc={time.time() - t0:.1f}s")
        items = [i for i in inbox.get("items", []) if i.get("nguon") == "copilot"]
        for it in items[-2:]:
            print(f"   - {it.get('y_dinh')} | {it.get('trang_thai')} | {it.get('tom_tat')}")
        results["ly_do_that_den_quan_ly"] = any(
            "di kham bệnh" in str(i.get("tom_tat") or "") for i in items
        )
    else:
        results["ly_do_that_den_quan_ly"] = False

    # ── 4. Lý do phải SẠCH: không lẫn cụm ca/ngày.
    print("\n== 4. 'Tôi xin nghỉ ca sáng thứ 3 vì con ốm' ==")
    _, r4 = call(
        "/api/v1/copilot/message",
        {"message": "Tôi xin nghỉ ca sáng thứ 3 vì con ốm", "channel": "web"},
        nhan_vien,
    )
    p4 = r4.get("action_proposal")
    ly_do = (p4 or {}).get("payload_diff", {}).get("ly_do")
    print(f"   ly_do={ly_do!r}")
    results["ly_do_khong_lonn_ca_ngay"] = ly_do == "con ốm"

    # ── 5. Ràng buộc phải THỰC SỰ loại nv khỏi ca chiều T5 trong lịch xếp.
    print("\n== 5. lịch xếp có tránh nv_03 ở ca chiều T5 không? ==")
    _, lich = call(f"/api/v1/lich-tuan?tuan={diff.get('tuan_id')}", method="GET", token=quan_ly)
    ca, phan_cong = lich.get("ca") or [], lich.get("phan_cong") or {}
    nguoi = [n for cid in ca_theo_thu_khung(ca, "T5", "chieu") for n in (phan_cong.get(cid) or [])]
    nv_id = str(diff.get("nv_id") or "")
    print(f"   ca chiều T5 có: {nguoi}")
    results["lich_tranh_cao_chi_nhay_vien"] = bool(nv_id) and nv_id not in nguoi
    # Không được xoá luôn ca sáng cùng ngày — nghỉ 1 buổi KHÔNG phải nghỉ cả ngày.
    sang = [n for cid in ca_theo_thu_khung(ca, "T5", "sang") for n in (phan_cong.get(cid) or [])]
    print(f"   ca sáng T5 có: {sang}")
    results["khong_xoa_ca_sang_cung_ngay"] = bool(nv_id) and nv_id in sang

    print("\n" + "=" * 60)
    for name, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in results.items() if not ok]
    print(f"\nTONG: {len(results) - len(failed)}/{len(results)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())