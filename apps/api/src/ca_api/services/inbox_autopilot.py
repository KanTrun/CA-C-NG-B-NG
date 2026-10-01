"""Tự động duyệt Hộp thư ràng buộc — AI quyết định thay quản lý.

Trước đây `/inbox` yêu cầu quản lý bấm "Duyệt"/"Từ chối" cho từng yêu cầu
(xin nghỉ, báo trễ, đổi ca…). Theo yêu cầu vận hành mới: AI tự động duyệt và
tự động chạy lại lịch — trang Hộp thư ràng buộc chỉ còn để XEM (yêu cầu → AI
quyết định → kết quả xếp lịch), không còn nút duyệt tay.

Chính sách quyết định (tất định, không LLM — an toàn để tự động hoá):
  - `xin_nghi` / `bao_tre` / `cap_nhat_tkb`  → luôn DUYỆT, tự động xếp lại lịch
    (ràng buộc áp ngay vào lượt giải tiếp theo).
  - `doi_ca` / `nhan_ca` → DUYỆT nếu tìm được ứng viên phù hợp (điểm > 0) từ
    cùng thuật toán xếp hạng đang hiển thị trên trang (`find_swap_candidates`);
    áp dụng ngay (`ap_dat=True`) vì AI đã chọn người, không cần đợi đối tác xác
    nhận thủ công. Không tìm được ứng viên nào → TỪ CHỐI, ghi rõ lý do.
  - Còn lại (loại chưa biết) → DUYỆT, chỉ ghi nhận (không đổi lịch).
  - Lịch tuần đã khoá (`da_duyet`/`da_cong_bo`/`da_dong`) → vẫn duyệt yêu cầu,
    nhưng việc xếp lại lịch bị `_decide_inbox_item` tự bỏ qua và ghi rõ
    "chờ lượt xếp lịch sau" (không sửa lịch đã công bố).

Được gọi từ hai nơi (`main.py`/`channels.py` gọi `auto_process`):
  1. Ngay khi một yêu cầu mới được ghi vào hộp thư (kênh nhắn tin, copilot,
     cuộc họp) — quyết định gần như lập tức.
  2. Mỗi lần `GET /api/v1/inbox/rang-buoc` được tải — quét lại phần còn sót
     (an toàn cho các luồng ghi không gọi autopilot trực tiếp).
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Any

from ca_api.persist import kv_get

AUTOPILOT_ACTOR = "ag_scheduler"

log = logging.getLogger(__name__)

# Chốn "bầy ong": autopilot chạy nền mỗi lần quản lý mở trang Hộp thư, mà mỗi
# lượt có thể kéo theo một lần giải CP-SAT. Nếu không khoá, ba lần mở trang liền
# nhau sẽ chạy ba lần giải song song, giành CPU và tranh ghi kv/solver — đo được
# CPU ~78% và các request khác chậm theo. Lock không chặn: lượt gọi sau thấy
# đang chạy thì bỏ qua, vì lượt đang chạy sẽ quét lại toàn bộ mục chờ.
_RUN_LOCK = threading.Lock()


def _pick_swap_candidate(item: dict[str, Any]) -> str | None:
    """Ứng viên tốt nhất cho một yêu cầu đổi/nhận ca — cùng thuật toán đang
    hiển thị ở trang Hộp thư (`goi_y_doi_tac`), không suy diễn thêm."""
    # Import muộn để tránh vòng import (sprint45 định nghĩa router HTTP, còn
    # phụ thuộc vào các hàm nội bộ này để tính ứng viên).
    from ca_api.interfaces.http.sprint45 import _get_swap_candidates_for_item

    try:
        candidates = _get_swap_candidates_for_item(item)
    except Exception:
        return None
    top = next((c for c in candidates if (c.get("score") or 0) > 0), None)
    return str(top["nv_id"]) if top else None


def auto_process(store_id: str = "quan_01") -> list[dict[str, Any]]:
    """Quét mọi mục `cho_duyet` trong hộp thư và để AI quyết định ngay.

    Trả về danh sách các quyết định đã đưa ra trong lượt gọi này (rỗng nếu
    không còn gì chờ) — dùng để log/kiểm thử, không bắt buộc phía gọi phải
    đọc giá trị trả về.

    Solver chạy **MỘT lần cho mỗi tuần**, sau khi đã quyết định xong mọi mục
    của tuần đó — không phải một lần mỗi mục. Lý do: mỗi lần gọi là một lần
    giải CP-SAT đầy đủ; quét 14 mục thì trang Hộp thư phải chờ 14 lần giải (đo
    được 194s). Tách thêm nữa thì lịch sinh ra chỉ thỏa ràng buộc của mục
cuối cùng, còn lượt này thì thỏa cả nhóm — đây cũng là lý do gom theo tuần.
    """
    items = kv_get("inbox_rang_buoc", [])
    if not isinstance(items, list):
        return []
    pending = [it for it in items if isinstance(it, dict) and it.get("trang_thai") == "cho_duyet"]
    if not pending:
        return []
    if not _RUN_LOCK.acquire(blocking=False):
        log.info("auto_process: mot luot quet dang chay, bo qua luot nay")
        return []
    try:
        return _quet_va_quyet_dinh(pending, store_id)
    finally:
        _RUN_LOCK.release()


def _quet_va_quyet_dinh(
    pending: list[dict[str, Any]], store_id: str,
) -> list[dict[str, Any]]:
    """Thân của `auto_process` — tách riêng để phần khoá ở trên rõ ràng."""
    from ca_api.interfaces.http.sprint45 import _decide_inbox_item, _giai_lich_cho_tuan_dich

    decisions: list[dict[str, Any]] = []
    # id các mục cần xếp lại lịch, gom theo tuần đích.
    can_xep_lai: dict[str, list[str]] = {}

    for item in pending:
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        y_dinh = str(item.get("y_dinh") or "")
        try:
            if y_dinh in {"doi_ca", "nhan_ca"}:
                rb = item.get("rang_buoc") or {}
                ca_id = str(rb.get("ca_id") or "").strip()
                candidate = _pick_swap_candidate(item)
                if ca_id and candidate:
                    result = _decide_inbox_item(
                        item_id,
                        quyet_dinh="duyet",
                        role=AUTOPILOT_ACTOR,
                        store_id=store_id,
                        actor_id=AUTOPILOT_ACTOR,
                        ca_id=ca_id,
                        doi_tac_nv_id=candidate,
                        ap_dat=True,
                        ly_do="AI tự động chọn người phù hợp nhất và duyệt ngay.",
                    )
                else:
                    result = _decide_inbox_item(
                        item_id,
                        quyet_dinh="tu_choi",
                        role=AUTOPILOT_ACTOR,
                        store_id=store_id,
                        actor_id=AUTOPILOT_ACTOR,
                        ly_do="Không tìm được người phù hợp để tự động đổi ca — cần quản lý can thiệp thủ công.",
                    )
            elif y_dinh in {"xin_nghi", "bao_tre", "cap_nhat_tkb"}:
                # `tu_dong_xep_lich=False`: quyết định trước, gom theo tuần,
                # rồi mới gọi solver một lần cho cả nhóm (xem docstring).
                result = _decide_inbox_item(
                    item_id,
                    quyet_dinh="duyet",
                    role=AUTOPILOT_ACTOR,
                    store_id=store_id,
                    actor_id=AUTOPILOT_ACTOR,
                    tu_dong_xep_lich=False,
                    ly_do="AI tự động duyệt và áp vào lượt xếp lịch tiếp theo.",
                )
            else:
                result = _decide_inbox_item(
                    item_id,
                    quyet_dinh="duyet",
                    role=AUTOPILOT_ACTOR,
                    store_id=store_id,
                    actor_id=AUTOPILOT_ACTOR,
                    ly_do="AI tự động ghi nhận.",
                )
            decisions.append({"id": item_id, "y_dinh": y_dinh, "ok": True, "result": result})
            hieu_luc = result.get("hieu_luc") or {}
            if hieu_luc.get("loai") == "rang_buoc_cho_solver":
                rb = result.get("rang_buoc") or {}
                week = str(rb.get("tuan_id") or hieu_luc.get("tuan_id") or "")
                can_xep_lai.setdefault(week, []).append(item_id)
        except Exception as exc:  # Một mục lỗi không được chặn các mục khác.
            decisions.append({"id": item_id, "y_dinh": y_dinh, "ok": False, "error": str(exc)})

    # Giải một lần mỗi tuần, gắn kết quả vào TẤT CẢ mục của tuần đó để hợp
    # đồng giữa hai tầng (test đọc `decisions[i]["result"]["tu_dong_xep_lich"]`).
    for week, item_ids in can_xep_lai.items():
        if not week:
            continue
        # Idempotency key phải ĐỔI khi ràng buộc của tuần đổi, nếu không
        # `schedule_run_create` tái dùng run cũ và ném
        # `idempotency_key_input_changed` → lượt quét sau không bao giờ xếp lại
        # được. Ghép danh sách mục vào key: cùng nhóm thì tái dùng (rẻ), khác
        # nhóm thì tạo run mới.
        key = f"inbox_auto:{week}:{hashlib.sha256('|'.join(sorted(item_ids)).encode()).hexdigest()[:12]}:solve"
        try:
            solver_result = _giai_lich_cho_tuan_dich(
                store_id=store_id,
                week=week,
                role=AUTOPILOT_ACTOR,
                actor_id=AUTOPILOT_ACTOR,
                item_id=item_ids[0],
                idempotency_key=key,
            )
        except Exception as exc:
            solver_result = {"ok": False, "status": "ERROR", "detail": str(exc)}
        for d in decisions:
            if d.get("id") in item_ids:
                # Tên biến khác `result` ở vòng trên: đó là `dict[str, Any]`
                # trả về từ `_decide_inbox_item`, còn đây là `Any | None` lấy từ
                # dict — gán chung tên làm mypy strict báo sai kiểu.
                result_muc = d.get("result")
                if isinstance(result_muc, dict):
                    result_muc["tu_dong_xep_lich"] = solver_result

    return decisions
