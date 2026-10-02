# Nối Facebook Page (Page quán)

Không giả lập bài/comment. Chỉ nối khi đã có Page thật.

## 1. Tạo Page

1. Facebook → tạo **Trang** (Page) cho quán.
2. Bạn phải là admin Page.

## 2. Meta App

1. [https://developers.facebook.com](https://developers.facebook.com) → tạo app loại Business.
2. Thêm sản phẩm **Messenger** + **Webhooks**.
3. Quyền tối thiểu: `pages_messaging`, `pages_manage_metadata`, `pages_read_engagement` (đăng bài cần `pages_manage_posts`).
4. App Review có thể bắt buộc trước khi public — trước đó chỉ test với admin Page.

## 3. Token

1. Graph API Explorer hoặc Business settings → **Page access token** dài hạn.
2. Lưu Page ID.

## 4. `.env` (không commit)

```env
CA_AGENT_MODE=live
NHIPQUAN_FB_PAGE_TOKEN=...
NHIPQUAN_FB_PAGE_ID=...
NHIPQUAN_PAGE_MODE=live
NHIPQUAN_FB_WEBHOOK_VERIFY=chuoi-bi-mat-cua-ban
NHIPQUAN_FB_APP_SECRET=...          # BẮT BUỘC — xem giải thích bên dưới
NHIPQUAN_FB_AUTO_SEND=1             # 1 = bot tự gửi, 0 = mọi tin chờ duyệt
NHIPQUAN_AUTO_RESERVATION=1         # 1 = bot tự chốt bàn, 0 = QL duyệt
```

> ### ⚠️ `NHIPQUAN_FB_APP_SECRET` — thiếu là Page KHÔNG nhận tin
>
> Lấy ở **Meta App Dashboard → App Settings → Basic → App Secret** (bấm *Show*).
>
> Webhook verify chữ ký `X-Hub-Signature-256` bằng App Secret. **Thiếu biến này →
> mọi event thật của Meta đều bị trả 403**, Page đứng yên "không nhận được tin" mà
> log chỉ ghi một dòng warning. Cố tình fail-closed (không đoán chữ ký).
>
> Kiểm tra nhanh: `GET /api/v1/page/status` → `webhook_secret_present: true`.
> Sửa `.env` xong phải restart stack.

Các cờ vận hành:

| Biến | Tắt (mặc định an toàn) | Bật | Ý nghĩa |
| --- | --- | --- | --- |
| `NHIPQUAN_FB_AUTO_SEND` | `0` | `1` | Bot tự gửi tin. Tắt ⇒ mọi tin nằm hộp thư chờ duyệt. |
| `NHIPQUAN_AUTO_RESERVATION` | `0` | `1` | Bot tự chạy state-machine đặt bàn. Tắt ⇒ tin đặt bàn vào hộp thư với lý do `reservation_auto_disabled` (câu hỏi STK vẫn tự trả lời). |
| `CA_AGENT_MODE` | `replay` | `live` | `replay` không gọi LLM ⇒ chỉ trả lời được template (giờ/địa chỉ/menu/STK). |

Hai cờ đầu **bật/tắt được từ UI** ở `/page-quan/fb-inbox` (ghi KV `fb_policy_runtime`,
không cần restart). `CA_AGENT_MODE` chỉ đổi được bằng `.env` + restart.

Compose đã truyền các biến này vào `api` / `worker`. Sau khi sửa `.env`:

```bash
python scripts/docker_stack.py up
```

## 5. Kiểm tra trong NHỊP QUÁN

- UI: `/page-quan` — hiện «Đã nối Page» khi Graph `/{page-id}` OK.
- `GET /api/v1/page/status` → `connected: true`, `graph_ok: true`, `page_name`.
  Kèm 4 cờ chẩn đoán: `webhook_secret_present`, `auto_send_enabled`,
  `auto_reservation_enabled`, `llm_mode`. Trang `/page-quan` hiện banner đỏ
  nếu `webhook_secret_present: false` hoặc Page chưa nối — **đừng bỏ qua banner**,
  đó là nguyên nhân "Page không nhận tin" phổ biến nhất.
- Quản lý bấm **Đồng bộ hội thoại từ Facebook** → `POST /api/v1/page/sync`.
- Duyệt nháp bài khi live → đăng lên feed Page (cần quyền posts).
- Trả lời thread có `psid` → gửi Messenger thật.

## 6. Webhook HTTPS (tin realtime)

1. Mở tunnel tới API, ví dụ ngrok: `https://<domain> → localhost:8000`.
2. Meta App → Webhooks → Callback URL:

```text
https://<domain>/api/v1/channels/facebook/webhook
```

3. Verify token = đúng `NHIPQUAN_FB_WEBHOOK_VERIFY` trong `.env`.
4. Subscribe field **messages** (và `messaging_postbacks` nếu cần) cho Page.
   - **Bắt buộc thêm field `feed`** để nhận comment trên bài viết (`item == "comment"`).
     Thiếu `feed` → Meta không gửi comment → bot không trả lời được comment công khai.
   - Có thể chạy `python scripts/fb_exchange_and_subscribe.py <USER_TOKEN>` để subscribe
     đủ các field (messages + feed + ...).
5. **Bắt buộc có `NHIPQUAN_FB_APP_SECRET`** ở `.env` (§4), nếu không Meta gửi event
   về mà webhook trả `403 invalid_signature` cho tất cả — Page không nhận tin.
   Sau khi bật webhook, nhắn thử 1 tin và kiểm tra hàng đã vào `/page-quan/fb-inbox`.

## 6b. Comment tự trả lời (auto-send)

- Comment an toàn (chào hỏi, giờ/địa chỉ, menu/giá, khuyến mãi, đặt bàn —
  `COMMENT_SAFE_INTENTS` + conf ≥ `AUTO_THRESHOLD_COMMENT`) **luôn tự trả lời
  công khai, không phụ thuộc cờ auto-send** (quyết định của Chủ quán).
  Cờ `NHIPQUAN_FB_AUTO_SEND` / nút hộp thư chỉ giữ cho tin nhắn Messenger.
- Comment không an toàn (khiếu nại, nhạy cảm, đòi người thật...) → **vẫn queue cho
  Quản lý duyệt tay** (ADR-008).
- Tự trả lời FAQ và cảm biến Jev **mặc định BẬT** (thiếu env = bật). Tắt tường minh
  bằng `NHIPQUAN_FB_AUTO_SEND=0` / `JEV_ENABLED=0` hoặc nút của Chủ quán trên hộp thư.

Mỗi lần đổi URL ngrok phải cấu hình webhook lại trên Meta.

## 7. Ranh giới sản phẩm

- Không CRM giữ chân khách cá nhân (ADR-011).
- Thread khó xử → **Tạo việc treo**, không auto-marketing.
- Token đã lộ chat/log → **thu hồi và cấp lại** trên Meta ngay.
