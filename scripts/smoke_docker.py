"""Smoke toàn tuyến trên Docker: auth → hôm nay → CP-SAT → công bằng → SOP → phiếu.

Chạy: make docker-smoke  (hoặc python scripts/smoke_docker.py --base http://localhost:8000)
Không mock: gọi đúng API đang chạy, in nguyên trạng thái trả về.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

if sys.platform == "win32":
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TIMEOUT = 180


def call(
    base: str, path: str, *, token: str | None = None, body: dict[str, Any] | None = None
) -> Any:
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {path}: {err_body}") from exc



def show(label: str, value: Any, limit: int = 300) -> None:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) > limit:
        text = text[:limit] + "…"
    print(f"  {label}: {text}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    failures: list[str] = []

    print("== 1. health ==")
    t0 = time.time()
    health_res = None
    while time.time() - t0 < 60:
        try:
            health_res = call(base, "/health")
            break
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(1)
    if health_res is None:
        health_res = call(base, "/health")
    show("health", health_res)

    print("== 2. đăng nhập (lan / quản lý) ==")
    login = call(base, "/api/v1/auth/login", body={"username": "lan", "password": "nhipquan"})
    token = login["token"]
    show("me", call(base, "/api/v1/me", token=token))

    print("== 3. hôm nay ==")
    show("hom-nay", call(base, "/api/v1/hom-nay", token=token))

    print("== 4. vòng đời lịch → dang_giai (CP-SAT thật) ==")
    hien_tai = call(base, "/api/v1/lich/lifecycle", token=token).get("trang_thai")
    if hien_tai != "nhap":
        show("bỏ qua — lịch đã ở trạng thái", hien_tai)
    else:
        t0 = time.time()
        try:
            life = call(base, "/api/v1/lich/lifecycle", token=token, body={"to": "dang_giai"})
            show("lifecycle", life)
            print(f"  giải xong sau {time.time() - t0:.1f}s")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            failures.append(f"lifecycle: HTTP {exc.code} {detail[:200]}")
            print(f"  LỖI lifecycle: {exc.code} {detail[:200]}")

    print("== 5. công bằng ==")
    show("cong-bang", call(base, "/api/v1/cong-bang", token=token))

    print("== 5b. phiếu mở quán (opsengine + template YAML) ==")
    try:
        call(base, "/api/v1/diem-danh", token=token, body={})
        started = call(base, "/api/v1/phieu/start", token=token, body={"mau": "mo_quan"})
        show("phieu/start", started)
        phieu_id = started.get("id") or started.get("run_id") or started.get("phieu_id")
        # Đẩy BƯỚC ĐANG DỞ, không phải bước đầu template. `phieu/start` trả về
        # phiếu đang chạy nếu đã có (chạy lại smoke lần hai sẽ trả `ph_1` đã
        # qua bước 1) — lấy `buoc[0]` thì gọi nhầm bước cũ và nhận
        # 400 `sai_thu_tu_buoc`, làm smoke không chạy lại được.
        buoc = started.get("buoc_hien_tai") or (started.get("hien_tai") or {}).get("ma")
        if not buoc:
            buoc = (started.get("buoc") or [{}])[0].get("ma")
        if phieu_id and buoc:
            show(
                "phieu/buoc",
                call(base, f"/api/v1/phieu/{phieu_id}/buoc", token=token, body={"ma": buoc}),
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        failures.append(f"phieu: HTTP {exc.code} {detail[:200]}")
        print(f"  LỖI phiếu: {exc.code} {detail[:200]}")

    print("== 6. SOP hỏi–đáp ==")
    try:
        sop = call(
            base,
            "/api/v1/sop",
            token=token,
            body={"question": "Máy pha bị nghẹt thì xử lý thế nào?"},
        )
        show("sop", sop)
    except urllib.error.HTTPError as exc:
        failures.append(f"sop: HTTP {exc.code}")
        print(f"  LỖI sop: {exc.code}")

    print("== 7. cẩm nang (luật) ==")
    show("cam-nang", call(base, "/api/v1/cam-nang", token=token))

    print("== 8. việc treo + inbox ==")
    show("viec-treo", call(base, "/api/v1/viec-treo", token=token))
    show("inbox", call(base, "/api/v1/inbox", token=token))

    if failures:
        print("\nKẾT QUẢ: ĐỎ")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nKẾT QUẢ: XANH — toàn tuyến backend chạy thật trên Docker")
    return 0


if __name__ == "__main__":
    sys.exit(main())
