# Kết nối Gmail qua OAuth 2.0 (quản lý hộp thư)

Runbook này dành cho **quản lý hộp thư Gmail** trong NHỊP QUÁN: đọc email, tạo nhãn,
tạo bộ lọc, đồng bộ hộp thư, gửi email qua Gmail API.

> Nếu bạn chỉ cần **gửi** thông báo phân ca cho nhân viên, xem
> [`gmail-smtp-connect.md`](./gmail-smtp-connect.md) — đơn giản hơn, không cần OAuth.

---

## 1. Khi nào dùng OAuth thay vì SMTP?

| Nhu cầu | Dùng |
|---------|------|
| Gửi thông báo ca/đổi ca cho nhân viên | SMTP (App Password) |
| Đọc hộp thư trong app, đánh dấu đã đọc, gắn sao | **OAuth (runbook này)** |
| Tạo/sửa nhãn Gmail theo nghiệp vụ quán | **OAuth** |
| Tạo bộ lọc tự động (vd: gắn nhãn "Đơn hàng" cho mail từ ShopeeFood) | **OAuth** |
| Trả lời email khách ngay trong khung hội thoại | **OAuth** |

Cả hai cách dùng chung tài khoản Gmail, nhưng OAuth không cần App Password và có thể
thu hồi quyền bất kỳ lúc nào từ phía Google.

---

## 2. Tạo OAuth client trên Google Cloud Console

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/) và tạo (hoặc chọn)
   một project — ví dụ `Nhip Quan Operations`.
2. **Bật Gmail API**:
   - Menu → **APIs & Services** → **Library**
   - Tìm `Gmail API` → **Enable**
3. **Cấu hình OAuth consent screen** (màn hình đồng ý):
   - Menu → **APIs & Services** → **OAuth consent screen**
   - User type: **External** (hoặc **Internal** nếu dùng Google Workspace của quán)
   - Điền tên ứng dụng, email hỗ trợ, email liên hệ
   - **Scopes**: thêm các quyền sau
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.send`
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/gmail.labels`
     - `https://www.googleapis.com/auth/gmail.settings.basic`
   - **Test users**: thêm địa chỉ Gmail của quán (bắt buộc khi app còn ở chế độ Testing)
4. **Tạo OAuth client ID**:
   - Menu → **APIs & Services** → **Credentials** → **Create credentials** →
     **OAuth client ID**
   - Application type: **Web application**
   - **Authorized redirect URIs**: thêm
     ```
     http://localhost:8000/api/v1/gmail/oauth/callback
     ```
     (đổi domain khi chạy production)
   - Nhấn **Create**, sao chép **Client ID** và **Client Secret**.

---

## 3. Cấu hình file `.env`

```env
# OAuth client (mục 2)
NHIPQUAN_GMAIL_CLIENT_ID=1234567890-abcxyz.apps.googleusercontent.com
NHIPQUAN_GMAIL_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
NHIPQUAN_GMAIL_REDIRECT_URI=http://localhost:8000/api/v1/gmail/oauth/callback

# Mã hoá token lưu trong DB (BẮT BUỘC — xem cảnh báo bên dưới)
NHIPQUAN_ENCRYPTION_KEY=<key sinh bằng lệnh dưới>
```

Sinh khoá mã hoá:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> [!NOTE]
> API tự nạp file `.env` khi khởi động (ROOT/.env trước, rồi `apps/api/.env`;
> biến môi trường sẵn có như Docker `--env-file` luôn được ưu tiên). Sửa
> `.env` xong vẫn phải **restart API** — `uvicorn --reload` chỉ theo dõi code.
> Key mã hoá cũng chỉ đọc lúc dùng, nên đặt key trước lần Connect đầu tiên
> là token dùng đúng key đó sau mọi lần restart.

> [!WARNING]
> **Thiếu `NHIPQUAN_ENCRYPTION_KEY`** ⇒ hệ thống sinh khoá tạm mỗi lần khởi động.
> Token đã lưu sẽ **không đọc lại được** sau khi restart, và bạn phải kết nối lại OAuth.
> Đặt biến này trước khi kết nối tài khoản đầu tiên.

> [!NOTE]
> Đổi `NHIPQUAN_ENCRYPTION_KEY` sau khi đã có token ⇒ mọi token cũ hỏng. Phải
> ngắt kết nối (`Thu hồi`) rồi kết nối lại từng tài khoản.

---

## 4. Kết nối tài khoản qua giao diện

1. Đăng nhập NHỊP QUÁN bằng vai **chủ quán** (quản lý/nhân viên không thấy mục Gmail).
2. Mở `/gmail` (menu **Thêm** → **Quản lý Gmail**, hoặc gõ trực tiếp đường dẫn).
3. Tab **Tài khoản** → **Kết nối Gmail qua OAuth**.
4. Google hiện màn hình đồng ý: chọn tài khoản quán → **Cho phép**.
5. Trình duyệt tự quay về `/gmail`, hiện thông báo **Đã kết nối Gmail: …** và tài khoản có nhãn **Đã kết nối**.

Tài khoản đầu tiên tự động được đánh dấu **Chính**.

> [!NOTE]
> **Về `state` chống CSRF:** khi bấm *Kết nối Gmail*, hệ thống sinh một mã `state`
> ngẫu nhiên, gắn với tài khoản nhân viên + hạn 10 phút, rồi lưu lại. Khi Google
> chuyển hướng về, mã đó được kiểm tra và **dùng một lần**. Nhờ vậy kẻ tấn công
> không thể lừa bạn hoàn tất OAuth cho tài khoản Gmail của họ. Vì thế đừng mở lại
> đường dẫn callback cũ (sẽ báo `state_oauth_khong_hop_le`) hay để màn hình đồng ý
> treo quá 10 phút.

---

## 5. Đồng bộ hộp thư

Tab **Đồng bộ** của tài khoản:

- **Đồng bộ thay đổi mới** — lấy email mới, email đã xoá, và thay đổi nhãn kể từ
  lần đồng bộ trước (dùng `historyId`). Chạy hằng ngày, nhanh và ít tốn quota.
- **Đồng bộ toàn bộ** — tải lại toàn bộ hộp thư + nhãn + bộ lọc. Dùng lần đầu,
  hoặc khi dữ liệu lệch.

Trạng thái hiển thị: lần đồng bộ cuối, `History ID`, tổng email, số chưa đọc.

> [!NOTE]
> **Trạng thái đọc và gắn sao bám theo Gmail.** Gmail biểu diễn "chưa đọc" bằng
> nhãn `UNREAD` và "có sao" bằng `STARRED`. Khi đồng bộ thay đổi mới, hệ thống
> cập nhật cả nhãn lẫn hai trạng thái này; email bị xoá bên Gmail cũng bị xoá
> khỏi hộp thư trong app. Vì vậy sau khi đồng bộ, những gì bạn thấy trong app
> khớp với Gmail.

---

## 6. Xử lý sự cố

| Hiện tượng | Nguyên nhân | Cách xử lý |
|-----------|-------------|-----------|
| `/gmail` báo **503 chua_cau_hinh_oauth_gmail** | Thiếu `NHIPQUAN_GMAIL_CLIENT_ID`/`_SECRET` | Điền vào `.env`, khởi động lại API |
| Google báo **redirect_uri_mismatch** | Redirect URI trong Console khác biến `.env` | Sửa cho khớp tuyệt đối (kể cả dấu `/`) |
| Google báo **access_blocked** | App ở chế độ Testing, email chưa nằm trong Test users | Thêm email vào **Test users** ở consent screen |
| Sau khi đồng ý, quay về `/gmail` kèm `error=state_oauth_het_han` | Mở màn hình đồng ý quá 10 phút mới bấm Cho phép | Bấm **Kết nối Gmail** lại |
| Quay về kèm `error=state_oauth_khong_hop_le` | Mở lại link callback cũ (state dùng một lần) | Bấm **Kết nối Gmail** lại từ đầu |
| Đồng bộ trả **dong_bo_that_bai** | Token hết hạn và không làm mới được | Tab Tài khoản → **Thu hồi** → kết nối lại |
| Đọc email lỗi **tai_khoan_chua_ket_noi_oauth** | Tài khoản thêm thủ công, chưa qua OAuth | Kết nối OAuth cho tài khoản đó |
| Nhãn **Cần kết nối lại** (đỏ) trên tài khoản | Token cũ không giải mã được — `NHIPQUAN_ENCRYPTION_KEY` đã đổi | Đặt key cố định, **Thu hồi** rồi kết nối lại |
| Sau khi restart, mọi token hỏng | `NHIPQUAN_ENCRYPTION_KEY` thay đổi hoặc chưa cố định | Đặt key cố định, kết nối lại |

### Mã lỗi thường gặp trong log

| Mã | Nghĩa |
|----|-------|
| `thieu_state_oauth` | Request callback thiếu tham số `state` |
| `state_oauth_khong_hop_le` | `state` không tồn tại, đã dùng, hoặc do người khác tạo |
| `state_oauth_het_han` | `state` quá 10 phút |
| `state_oauth_sai_nguoi` | `state` của một nhân viên khác |
| `doi_ma_oauth_that_bai` | Không đổi được mã uỷ quyền với Google |
| `khong_doc_duoc_ho_so_gmail` | Token đổi được nhưng không đọc được profile |
| `tai_khoan_chua_ket_noi_oauth` | Tài khoản chưa có token dùng được |
| `dong_bo_that_bai` | Lỗi khi gọi Gmail API trong lúc đồng bộ |

### Kiểm tra quota Gmail API

Gmail API có hạn mức **1 tỷ quota units/ngày/project** và **250 units/user/giây**.
Đồng bộ lần đầu một hộp thư lớn (chục nghìn email) tốn nhiều quota; các lần sau
dùng đồng bộ tăng dần nên không đáng kể. Theo dõi tại **APIs & Services → Quotas**
trong Google Cloud Console.

### Bảng dữ liệu trên PostgreSQL (production)

8 bảng Gmail được tạo bằng **migration Alembic `0015_add_gmail_tables.py`**.
Container API tự chạy `alembic upgrade head` trước khi khởi uvicorn, nên chỉ cần
`make docker-up` là bảng tự có.

Nếu nâng cấp một deployment **đang chạy** (không rebuild), áp migration thủ công:

```bash
docker exec -w /app/apps/api <ten-container-api> alembic -c alembic/alembic.ini upgrade head
docker exec -w /app/apps/api <ten-container-api> alembic -c alembic/alembic.ini current
# → phải in ra: 0015 (head)
```

Kiểm tra bảng đã tồn tại:

```bash
docker exec nhipquan-postgres-1 psql -U nhipquan -d nhipquan -c "\dt gmail*"
```

> [!IMPORTANT]
> **Triệu chứng khi thiếu migration:** mọi endpoint `/api/v1/gmail/*` trả **500**
> kèm log `psycopg.errors.UndefinedTable: relation "gmail_accounts" does not exist`.
> Chạy lệnh `alembic upgrade head` ở trên để khắc phục.
>
> Gate `apps/api/tests/unit/test_migrations_complete.py` tự động chặn regression:
> mọi bảng mới thêm vào DDL SQLite mà thiếu migration sẽ làm CI đỏ.

---

## 7. Thu hồi quyền truy cập

Cách 1 — trong app: tab **Tài khoản** → **Thu hồi** (hoặc **Xoá** tài khoản).
Thao tác này gọi endpoint thu hồi của Google rồi xoá token khỏi DB.

Cách 2 — từ phía Google: [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
→ chọn ứng dụng → **Xoá quyền truy cập**. Sau đó vào app **Thu hồi** để dọn token local.

---

## 8. Bảo mật

- Token được mã hoá bằng Fernet trước khi ghi DB (`gmail_oauth_tokens`).
- **Chỉ chủ quán:** mọi endpoint `/api/v1/gmail/*` đòi vai `chu_quan`
  (403 `chi_danh_cho_chu_quan`); quản lý/nhân viên không thấy mục Gmail.
  Mỗi tài khoản gắn với đúng chủ quán đã thêm (`nv_id`) — hỏi tài khoản của
  người khác trả **404** để không tiết lộ sự tồn tại.
- Chỉ tài khoản do chính mình thêm mới được gửi mail / sửa nhãn / xoá.
- `state` OAuth chống CSRF: ngẫu nhiên, gắn người dùng, hạn 10 phút, dùng một lần.
- Thông báo lỗi dùng mã kỹ thuật (`state_oauth_het_han`…), không lộ chi tiết nội bộ.
- Khi khoá mã hoá đổi, tài khoản được đánh dấu **Cần kết nối lại** thay vì làm
  sập trang — bạn vẫn mở được `/gmail` để xử lý.
- Gửi mail **từ Copilot** vẫn đi qua quality gate và audit của `ag_mailwriter` —
  xem [`gmail-reflection.md`](./gmail-reflection.md).
