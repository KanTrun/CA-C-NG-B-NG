"""Hồi quy QA đợt 6 — 5 lỗi phát hiện khi chạy 50 mục kiểm thử trên production.

Bối cảnh: kế hoạch `docs/KE-HOACH-TEST-TOAN-BO-CHUC-NANG.md` được chạy đủ 50 mục
(2026-09-29) và phát hiện 5 lỗi MỚI (ngoài 7 lỗi đợt 5 đã sửa ở PR #89/#90):

- **#35 (Critical)** `login()` bỏ qua `status` → tài khoản đã `deactivate` VẪN
  đăng nhập được. `session()` cũng không kiểm tra → token cũ tiếp tục dùng được.
  Offboarding vô hiệu trên thực tế: đo được `qa_probe_...` deactivate xong vẫn
  login 200 và nhận token mới.
- **#36** `list_users()` không lọc `status` → tài khoản đã vô hiệu hoá vẫn hiện
  trong `/nguoi`, `/cong-bang`, và Copilot `LIST_STAFF`. Đo được `/nguoi` = 35
  tài khoản trong khi quán chỉ có 19 người thật.
- **#37** `POST /auth/register` công khai không giới hạn → đo được **10/10** tài
  khoản tạo liên tiếp trong 1 giây từ cùng một IP; mỗi tài khoản chiếm 1 `nv_id`
  vĩnh viễn và lọt vào mọi danh sách nhân sự.
- **#38** `GET /store/profile` + `GET /store/promotions` KHÔNG nhận
  `authorization` → không token/token sai đều đọc được toàn bộ hồ sơ quán, gồm
  `wifi_pass` và `huong_dan_agent` (hướng dẫn nội bộ cho AI).
- **#39** 4 endpoint GET thuộc `MANAGER_ONLY` của giao diện nhưng backend chỉ đòi
  token: `/ops/explain/chains`, `/ops/predict/suggestions`,
  `/ops/twin/scenarios`, `/experience/rules/candidates`. Nhân viên gọi thẳng API
  vẫn đọc được chuỗi nhân quả + đề xuất kèm số liệu doanh thu.
"""

from __future__ import annotations

import pytest
from ca_api.interfaces.http.main import app
from ca_api.persist import list_users, login, register, session, user_deactivate
from fastapi.testclient import TestClient

from unit.auth_util import headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── #35: tài khoản đã vô hiệu hoá không được đăng nhập ───────────────────────


def test_login_tu_choi_tai_khoan_da_vo_hieu_hoa() -> None:
    """Đăng ký → deactivate → login phải trả None (không cấp token mới).

    Đo trên production trước khi sửa: deactivate xong vẫn đăng nhập 200.
    """
    reg = register("qa_h35_login", "MatKhau123456", "QA H35")
    assert reg is not None
    nv_id = reg["nv_id"]
    assert login("qa_h35_login", "MatKhau123456") is not None, "phải login được TRƯỚC khi vô hiệu hoá"

    assert user_deactivate(nv_id) is True

    assert login("qa_h35_login", "MatKhau123456") is None, (
        "BUG #35 tái phát: tài khoản đã vô hiệu hoá vẫn đăng nhập được"
    )


def test_session_tu_choi_token_cua_tai_khoan_da_vo_hieu_hoa() -> None:
    """Token còn trong `sessions` của tài khoản đã vô hiệu hoá phải bị từ chối.

    LƯU Ý cách dựng test: `user_deactivate` CÓ xoá `sessions`, nên nếu chỉ
    đăng ký → deactivate → gọi `session()` thì test xanh một cách vô tình
    (row không tồn tại, chưa từng chạm nhánh kiểm `status`). Muốn chứng minh
    nhánh đó hoạt động phải CHÈN LẠI session row cho user `inactive` — mô
    phỏng đúng tình huống thật khi bản ghi session còn sót (token phát trước
    khi offboarding hoàn tất, hoặc tạo lại qua đường khác).
    """
    import uuid
    from datetime import UTC, datetime

    from ca_api.persist import _conn

    reg = register("qa_h35_session", "MatKhau123456", "QA H35b")
    assert reg is not None
    nv_id = reg["nv_id"]
    username = "qa_h35_session"

    user_deactivate(nv_id)

    # Chèn lại session HỢP LỆ về hình thức (token thật, chưa hết hạn) cho user
    # đã `inactive` → chỉ có nhánh kiểm `status` mới chặn được.
    token_sot = uuid.uuid4().hex
    with _conn() as cx:
        cx.execute(
            "INSERT INTO sessions(token, username, role, nv_id, store_id, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (token_sot, username, "nhan_vien", nv_id, "quan_01", datetime.now(UTC).isoformat()),
        )

    assert session(f"Bearer {token_sot}") is None, (
        "BUG #35 tái phát: token của tài khoản đã vô hiệu hoá vẫn qua được session()"
    )
    # Và phải bị XOÁ luôn, không để tồn tại cho lần gọi sau.
    with _conn() as cx:
        con = cx.execute("SELECT 1 FROM sessions WHERE token=?", (token_sot,)).fetchone()
    assert con is None, "session rác của tài khoản inactive phải bị xoá khỏi DB"


def test_vo_hieu_hoa_khong_lam_chet_nguoi_khac() -> None:
    """Chốt chống hồi quy ngược: người đang làm việc vẫn đăng nhập bình thường."""
    reg = register("qa_h35_ok", "MatKhau123456", "QA H35c")
    assert reg is not None
    assert login("qa_h35_ok", "MatKhau123456") is not None


# ── #36: danh sách nhân sự ẩn tài khoản đã vô hiệu hoá ───────────────────────


def test_list_users_an_tai_khoan_da_vo_hieu_hoa() -> None:
    """`/nguoi` và mọi bề mặt đếm người phải bỏ qua tài khoản `inactive`."""
    truoc = {u["username"] for u in list_users()}
    reg = register("qa_h36_an", "MatKhau123456", "QA H36")
    assert reg is not None
    assert "qa_h36_an" in {u["username"] for u in list_users()}, "tài khoản mới phải hiện"

    user_deactivate(reg["nv_id"])

    sau = {u["username"] for u in list_users()}
    assert "qa_h36_an" not in sau, (
        "BUG #36 tái phát: tài khoản đã vô hiệu hoá vẫn nằm trong list_users()"
    )
    assert truoc <= sau, "không được ẩn nhầm người đang hoạt động"


def test_list_users_include_inactive_khi_duoc_hoi_ro() -> None:
    """Màn quản trị cần thấy cả người đã nghỉ → cờ `include_inactive=True`."""
    reg = register("qa_h36_hien", "MatKhau123456", "QA H36b")
    assert reg is not None
    user_deactivate(reg["nv_id"])

    tat_ca = {u["username"] for u in list_users(include_inactive=True)}
    assert "qa_h36_hien" in tat_ca, (
        "include_inactive=True phải trả cả tài khoản đã vô hiệu hoá"
    )


def test_api_nguoi_khong_dem_tai_khoan_da_vo_hieu_hoa(client: TestClient) -> None:
    """Qua HTTP thật: `/api/v1/nguoi` không được liệt kê tài khoản `inactive`."""
    qq = headers(client, "hung")
    reg = register("qa_h36_api", "MatKhau123456", "QA H36c")
    assert reg is not None
    user_deactivate(reg["nv_id"])

    r = client.get("/api/v1/nguoi", headers=qq)
    assert r.status_code == 200, r.text
    ten = {u["username"] for u in r.json()["items"]}
    assert "qa_h36_api" not in ten, (
        "BUG #36 tái phát ở tầng HTTP: /nguoi vẫn trả tài khoản đã vô hiệu hoá"
    )


# ── #37: đăng ký công khai phải bị giới hạn ─────────────────────────────────


def test_register_bi_chan_sau_nhieu_lan_lien_tiep(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spam đăng ký từ CÙNG một IP phải bị chặn 429.

    Đo trên production trước khi sửa: 10/10 tài khoản tạo thành công trong 1 giây.
    Bộ đếm dùng chung khoá theo IP; TestClient luôn là `testclient` nên chỉ cần
    gọi liên tiếp là đủ kích hoạt.

    LƯU Ý: `apps/api/tests/conftest.py` đặt `NHIPQUAN_DISABLE_RATE_LIMIT=1` cho
    toàn suite (nếu không, hàng nghìn request test dùng chung IP `testclient` sẽ
    ăn 429 oan). Test này phải BẬT LẠI cơ chế để chứng minh nó thật sự hoạt động.
    """
    monkeypatch.delenv("NHIPQUAN_DISABLE_RATE_LIMIT", raising=False)

    ma: list[int] = []
    for i in range(8):
        r = client.post(
            "/api/v1/auth/register",
            json={
                "username": f"qa_h37_{i}",
                "password": "MatKhau123456",
                "display_name": f"QA H37 {i}",
            },
        )
        ma.append(r.status_code)
        if r.status_code == 429:
            break

    assert 429 in ma, (
        f"BUG #37 tái phát: đăng ký liên tiếp không bị giới hạn (mã nhận được: {ma})"
    )
    assert ma.count(201) < 8, "không được tạo hết 8 tài khoản"


# ── #38: hồ sơ quán phải yêu cầu đăng nhập ──────────────────────────────────


def test_store_profile_va_promotions_yeu_cau_dang_nhap(client: TestClient) -> None:
    """Không token / token sai đều 401 — hồ sơ quán không phải dữ liệu công khai."""
    for path in ("/api/v1/store/profile", "/api/v1/store/promotions"):
        r = client.get(path)
        assert r.status_code == 401, f"BUG #38 tái phát: GET {path} không token → {r.status_code}"
        r = client.get(path, headers={"Authorization": "Bearer token_bom"})
        assert r.status_code == 401, f"GET {path} với token sai → {r.status_code}"


def test_store_profile_van_tra_du_lieu_cho_nguoi_da_dang_nhap(client: TestClient) -> None:
    """Chốt chống hồi quy ngược: thêm auth KHÔNG được làm hỏng luồng thật."""
    ql = headers(client, "lan")
    r = client.get("/api/v1/store/profile", headers=ql)
    assert r.status_code == 200, r.text
    for key in ("ten_quan", "dia_chi", "hotline", "wifi_pass"):
        assert key in r.json(), f"thiếu trường {key}"

    r = client.get("/api/v1/store/promotions", headers=ql)
    assert r.status_code == 200, r.text


def test_nhan_vien_doc_duoc_ho_so_quan(client: TestClient) -> None:
    """Nhân viên cần hồ sơ quán để làm việc → chỉ đòi đăng nhập, không đòi quản lý."""
    nv = headers(client, "minh")
    r = client.get("/api/v1/store/profile", headers=nv)
    assert r.status_code == 200, f"nhân viên phải đọc được hồ sơ quán: {r.status_code}"


# ── #39: endpoint MANAGER_ONLY phải chặn nhân viên ─────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/ops/explain/chains",
        "/api/v1/ops/predict/suggestions",
        "/api/v1/ops/twin/scenarios",
        "/api/v1/experience/rules/candidates",
    ],
)
def test_endpoint_quan_ly_chan_nhan_vien(client: TestClient, path: str) -> None:
    """Bốn trang này nằm trong `MANAGER_ONLY` của giao diện → API phải khớp.

    Trước khi sửa, nhân viên gọi thẳng API vẫn nhận 200 kèm dữ liệu nội bộ.
    """
    nv = headers(client, "minh")
    r = client.get(path, headers=nv)
    assert r.status_code == 403, (
        f"BUG #39 tái phát: {path} không chặn nhân viên (nhận {r.status_code})"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/ops/explain/chains",
        "/api/v1/ops/predict/suggestions",
        "/api/v1/ops/twin/scenarios",
        "/api/v1/experience/rules/candidates",
    ],
)
def test_endpoint_quan_ly_van_mo_cho_quan_ly(client: TestClient, path: str) -> None:
    """Chốt chống hồi quy ngược: siết quyền KHÔNG được chặn nhầm quản lý."""
    ql = headers(client, "lan")
    r = client.get(path, headers=ql)
    assert r.status_code == 200, f"quản lý phải gọi được {path}, nhận {r.status_code}: {r.text[:200]}"


def test_endpoint_quan_ly_yeu_cau_token(client: TestClient) -> None:
    """Không token → 401 (không phải 403) để phân biệt 'chưa đăng nhập' và 'thiếu quyền'."""
    for path in ("/api/v1/ops/explain/chains", "/api/v1/ops/predict/suggestions"):
        assert client.get(path).status_code == 401, f"{path} không token phải là 401"
