"""Test migration 0019 trên SQLite thật — không cần PostgreSQL.

Vì sao không chạy `alembic upgrade` trong test: migration 0001 khai `TEXT[]`,
`TIMESTAMPTZ`, `NOW()` — chỉ PostgreSQL chạy được, nên chuỗi migration không bao
giờ đi hết trên SQLite. Thay vào đó test này dựng đúng hai bảng 0019 chạm tới
(`menu_mon`, `kv`) rồi gọi thẳng `upgrade()` / `downgrade()` với `op.get_bind`
bị thay bằng connection SQLite.

Lỗi mà test này chặn
--------------------
- Bỏ sót dòng hỏng trong `kv.tieu_thu` → `/tieu-thu` lại hiện ô trống.
- Quên quy `cafe_g`/`Ca phe hat`/`Ly giay` về một mã → sổ lại trùng mặt hàng.
- ẩn `an=1` nhầm món chủ quán tự thêm (người dùng đã chốt chỉ ẩn theo id fixture
  và trùng tên).
- `ALIAS`/`TEN_BI_DANH` trong migration lệch với `ca_api.nguyen_lieu` → sửa một
  bên, bên kia vẫn sinh dữ liệu cũ.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "apps" / "api" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from ca_api import nguyen_lieu  # noqa: E402

_PATH = ROOT / "apps" / "api" / "alembic" / "versions" / "0019_tieu_thu_va_menu_chuan_hoa.py"


def _nap_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0019", _PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _nap_migration()

_COT = (
    "CREATE TABLE menu_mon (id TEXT PRIMARY KEY, ten TEXT NOT NULL, gia INTEGER NOT NULL,"
    " an INTEGER NOT NULL DEFAULT 0, bom TEXT NOT NULL DEFAULT '{}',"
    " hinh_url TEXT NOT NULL DEFAULT '', nhom TEXT NOT NULL DEFAULT '')"
)


@pytest.fixture()
def db(tmp_path: Path):
    """SQLite có `menu_mon` + `kv`, kèm `op.get_bind` trỏ vào đó."""
    f = tmp_path / "t0019.db"
    raw = sqlite3.connect(f)
    raw.executescript(_COT)
    raw.execute("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    raw.commit()
    raw.close()

    engine = sa.create_engine(f"sqlite:///{f.as_posix()}")
    conn = engine.connect()
    original_op = mod.op
    mod.op = SimpleNamespace(get_bind=lambda: conn)
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()
        engine.dispose()
        mod.op = original_op


def _them(conn, mid: str, ten: str, *, bom: str, an: int = 0, nhom: str = "") -> None:
    conn.execute(
        sa.text(
            "INSERT INTO menu_mon (id,ten,gia,an,bom,hinh_url,nhom)"
            " VALUES (:id,:ten,10000,:an,:bom,'',:nhom)"
        ),
        {"id": mid, "ten": ten, "an": an, "bom": bom, "nhom": nhom},
    )


def _menu(conn) -> dict[str, dict[str, Any]]:
    return {
        str(r["id"]): dict(r)
        for r in conn.execute(sa.text("SELECT id,ten,nhom,an,bom FROM menu_mon")).mappings()
    }


def _tt(conn) -> list[dict[str, Any]]:
    row = conn.execute(sa.text("SELECT v FROM kv WHERE k='tieu_thu'")).fetchone()
    return json.loads(row[0]) if row else []


# ── Đồng nhất hai bảng bí danh ────────────────────────────────────────────────


def test_alias_va_ten_bi_danh_dong_nhat_voi_nguyen_lieu() -> None:
    """Migration copy `ALIAS`/`TEN_BI_DANH` chứ không import app được."""
    assert mod.ALIAS == nguyen_lieu.ALIAS
    assert mod.TEN_BI_DANH == nguyen_lieu.TEN_BI_DANH


def test_muc_tieu_cua_migration_nam_trong_danh_muc() -> None:
    assert mod.DANH_MUC.exists(), mod.DANH_MUC
    dm = json.loads(mod.DANH_MUC.read_text(encoding="utf-8"))
    assert len(dm["mon"]) >= 40
    assert len(dm["nguyen_lieu"]) >= 15


# ── upgrade ───────────────────────────────────────────────────────────────────


def test_chen_mon_thieu_khong_dung_mon_da_co(db) -> None:
    _them(db, "ca_phe_den", "Cà phê đen", bom='{"ca_phe_hat": 18, "ly": 1}', nhom="ca_phe")
    _them(db, "my_mon", "Trà đào thủ công", bom='{"tra": 5}', nhom="tra")

    mod.upgrade()
    menu = _menu(db)
    so_mon_dm = len(json.loads(mod.DANH_MUC.read_text(encoding="utf-8"))["mon"])

    # 49 món danh mục + 1 món chủ quán; `ca_phe_den` đã có nên không bị thêm bản sao.
    assert len(menu) == so_mon_dm + 1
    assert menu["ca_phe_den"]["ten"] == "Cà phê đen"
    # Món mới nạp đủ tên có dấu và nhóm.
    assert menu["ca_phe_sua"]["ten"] == "Cà phê sữa"
    assert menu["ca_phe_sua"]["nhom"] == "ca_phe"
    # Món của chủ quán còn nguyên, kể cả khi nó trùng một món trong danh mục.
    assert menu["my_mon"]["ten"] == "Trà đào thủ công"


def test_an_bao_bia_theo_danh_muc_va_khong_bao_gio_bat_lai(db) -> None:
    _them(db, "goi_ca_phe_250", "Gói cà phê hạt 250g", bom='{"ca_phe_hat": 250}', nhom="nguyen_lieu")
    # Chủ quán đã ẩn một món TRONG danh mục — migration không được bật lại.
    _them(db, "espresso", "Espresso", bom='{"ca_phe_hat": 18}', an=1, nhom="ca_phe")

    mod.upgrade()
    menu = _menu(db)

    assert menu["goi_ca_phe_250"]["an"] == 1, "món bao bì trong danh mục phải bị ẩn"
    assert menu["espresso"]["an"] == 1, "ẩn của chủ quán phải giữ nguyên"
    # 8 món bao bì được chèn mới cũng ẩn luôn.
    assert menu["bich_ly_50"]["an"] == 1
    assert menu["bich_ong_hut_100"]["an"] == 1


def test_chi_an_theo_id_fixture_hoac_trung_ten_khong_an_mon_chu_quan(db) -> None:
    _them(db, "fx_mon_ca_phe_den", "Ca phe den", bom='{"cafe_g": 18}')
    # Món tiếng Anh ngoài danh mục — KHÔNG được ẩn (đúng hai nhánh người dùng chốt).
    _them(db, "my_mon", "Pizza pho mai", bom='{"banh": 1}')
    # Món gõ không dấu nhưng TRÙNG tên một món trong danh mục → bản sao → ẩn.
    _them(db, "copy_mon", "Ca phe den", bom='{"ca_phe_hat": 18}')

    mod.upgrade()
    menu = _menu(db)

    assert menu["fx_mon_ca_phe_den"]["an"] == 1, "id fixture phải ẩn"
    assert menu["my_mon"]["an"] == 0, "món tiếng Anh của chủ quán không được ẩn"
    assert menu["copy_mon"]["an"] == 1, "bản sao trùng tên phải ẩn"


def test_chua_dau_ten_chi_khi_la_ban_bo_dau(db) -> None:
    _them(db, "ca_phe_den", "Ca phe den", bom='{"ca_phe_hat": 18}', nhom="ca_phe")
    _them(db, "my_mon", "Trà đào flavoured", bom='{"tra": 5}')

    mod.upgrade()
    menu = _menu(db)

    assert menu["ca_phe_den"]["ten"] == "Cà phê đen"
    # Tên khác nghĩa — chủ quán đã đặt lại, không được sửa.
    assert menu["my_mon"]["ten"] == "Trà đào flavoured"
    assert menu["my_mon"]["an"] == 0


def test_dong_bom_legacy_ve_ma_chuan_va_cong_dinh_muc(db) -> None:
    _them(db, "my_mon", "Cà phê sữa", bom='{"cafe_g": 16, "ca_phe_hat": 4, "sua_ml": 40, "ly": 1}')

    mod.upgrade()
    bom = json.loads(_menu(db)["my_mon"]["bom"])

    assert bom == {"ca_phe_hat": 20, "sua_tuoi": 40, "ly": 1}


def test_dien_nhom_khi_de_trong(db) -> None:
    _them(db, "ca_phe_den", "Cà phê đen", bom='{"ca_phe_hat": 18}', nhom="")

    mod.upgrade()

    assert _menu(db)["ca_phe_den"]["nhom"] == "ca_phe"


def test_kv_tieu_thu_bo_dong_hong_va_quy_hang_ve_ma_chuan(db) -> None:
    rows = [
        {"order_id": "fx_don_003", "status": "posted", "items": {"ca_phe_hat": 18}},
        {"id": "a1", "hang": "cafe_g", "so_luong": 18, "don_vi": "don vi"},
        {"id": "a2", "hang": "Ca phe hat", "so_luong": 24, "don_vi": "g"},
        {"id": "a3", "hang": "Ly giay", "so_luong": 12, "don_vi": "phan"},
        {"id": "a4", "hang": "Sua tuoi", "so_luong": 3, "don_vi": "ml"},
        {"id": "a5", "hang": "Sua dac nha", "so_luong": 5, "don_vi": "g"},
        {"id": "a6", "hang": "ly", "so_luong": 2},
        {"id": "a7", "hang": "duong", "so_luong": "xx"},
        "khong phai dict",
    ]
    db.execute(sa.text("INSERT INTO kv (k,v) VALUES ('tieu_thu', :v)"), {"v": json.dumps(rows)})

    mod.upgrade()
    sach = _tt(db)

    # 2 dòng hỏng (hình legacy + số không đọc được) bị bỏ, đúng 6 dòng còn.
    assert [r["id"] for r in sach] == ["a1", "a2", "a3", "a4", "a5", "a6"]
    assert [r["hang"] for r in sach] == [
        "ca_phe_hat",
        "ca_phe_hat",
        "ly",
        "sua_tuoi",
        "Sua dac nha",
        "ly",
    ]


def test_kv_tieu_thu_khong_co_khong_roi(db) -> None:
    mod.upgrade()

    assert _tt(db) == []


def test_chay_lai_vo_hai(db) -> None:
    _them(db, "fx_mon_x", "Ca phe den", bom='{"cafe_g": 18}')
    _them(db, "my_mon", "Trà đào", bom='{"tra": 5}', nhom="tra")
    db.execute(
        sa.text("INSERT INTO kv (k,v) VALUES ('tieu_thu', :v)"),
        {"v": json.dumps([{"id": "a", "hang": "Ca phe hat", "so_luong": 1}])},
    )
    db.commit()

    mod.upgrade()
    lan_mot = (_menu(db), _tt(db))
    mod.upgrade()
    lan_hai = (_menu(db), _tt(db))

    assert lan_hai == lan_mot


# ── backup + downgrade ────────────────────────────────────────────────────────


def test_downgrade_khoi_phuc_duoc_ban_truoc(db) -> None:
    _them(db, "fx_mon_x", "Ca phe den", bom='{"cafe_g": 18}', nhom="")
    _them(db, "my_mon", "Pizza", bom='{"banh": 1}', nhom="banh")
    truoc = _menu(db)
    db.execute(
        sa.text("INSERT INTO kv (k,v) VALUES ('tieu_thu', :v)"),
        {"v": json.dumps([{"order_id": "x", "items": {}}])},
    )
    db.commit()

    mod.upgrade()
    assert _menu(db) != truoc
    mod.downgrade()

    assert _menu(db) == truoc
    assert _tt(db) == [{"order_id": "x", "items": {}}]
    # Bảng backup phải được dọn, không để rác sau downgrade.
    tables = [
        r[0]
        for r in db.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%0019'")
        )
    ]
    assert tables == []
