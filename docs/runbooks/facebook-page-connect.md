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
```

Compose đã truyền các biến này vào `api` / `worker`. Sau khi sửa `.env`:

```bash
python scripts/docker_stack.py up
```

## 5. Kiểm tra trong NHỊP QUÁN

- UI: `/page-quan` — hiện «Đã nối Page» khi Graph `/{page-id}` OK.
- `GET /api/v1/page/status` → `connected: true`, `graph_ok: true`, `page_name`.
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
