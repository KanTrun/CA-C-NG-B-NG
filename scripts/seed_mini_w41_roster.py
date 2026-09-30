#!/usr/bin/env python3
"""Seed fixture 4 NV + tuần 2026-W41 để tự kiểm /lich-tuan.

Chạy:
  python3 scripts/seed_mini_w41_roster.py

Hoặc qua API (đã đăng nhập quản lý):
  POST /api/v1/lich-tuan/demo-mini-w41
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "apps" / "api" / "src"),
    str(ROOT / "packages" / "contracts" / "src"),
    str(ROOT / "packages" / "solver" / "src"),
    str(ROOT / "packages" / "agents" / "src"),
    str(ROOT / "packages" / "playbook" / "src"),
]


def main() -> int:
    from ca_api.services.mini_w41_fixture import seed_mini_w41_roster

    result = seed_mini_w41_roster()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nChecklist:")
    for step in result.get("huong_dan") or []:
        print(f"  [ ] {step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
