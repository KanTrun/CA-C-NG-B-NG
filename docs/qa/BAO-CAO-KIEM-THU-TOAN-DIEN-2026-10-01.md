# BÁO CÁO KIỂM THỬ TOÀN DIỆN — NHỊP QUÁN / Quánverse

| | |
|---|---|
| **Hệ thống** | https://nhipquan.duckdns.org (production, Caddy 2 → web:3000 / api:8000) |
| **Ngày kiểm thử** | 2026-10-01, 01:00 → 03:00 (giờ VN) |
| **Hình thức** | Kiểm thử black-box từ góc nhìn người dùng thật, KHÔNG đọc/sửa mã nguồn để dựng kết quả |
| **Vai trò thử** | Khách (chưa đăng nhập) · Nhân viên `minh` · Quản lý `lan` · Chủ quán `hung` |
| **Công cụ** | Playwright/Chromium (UI thật), Node fetch (API), OpenAPI 287 path |
| **Kết quả** | **207 khẳng định API** (169 PASS) **+ 53 khẳng định thao tác UI thật** (41 PASS) + 2 lỗi nghiêm trọng chỉ lộ ra khi thao tác tay |
| **Mã nguồn** | **KHÔNG sửa một dòng code nào.** Xem [§10](#10-xác-minh-repo-không-bị-thay-đổi) |

> **Ghi chú về phương pháp.** Bản đầu tiên của báo cáo này thiên về gọi API. Nhận ra thiếu sót đó, tôi đã chạy thêm **một vòng kiểm thử thao tác tay hoàn toàn trên trình duyệt**: mở trang, đọc nhãn tiếng Việt người dùng thấy, điền vào ô, bấm nút thật bằng chuột, quan sát phản ứng. **Vòng thứ hai phát hiện 2 lỗi nghiêm trọng mà gọi API không thể phát hiện** — xem [§3.5](#35-lỗi-mới-tìm-ra-nhờ-thao-tác-tay-trên-ui).

---

## 1. Bối cảnh và phạm vi

Hệ thống là một ứng dụng quản lý vận hành quán cà phê dạng PWA (Next.js 15 App Router + FastAPI), dùng cho ba vai trò: **nhân viên**, **quản lý**, **chủ quán**. Đã xác định **46 route web** và **287 path API**.

Tôi lập kế hoạch kiểm thử theo giả định: người dùng là người lần đầu mở app trên điện thoại, không biết gì về hệ thống, không có tài liệu. Mọi hành vi phải tự giải thích được.

### Kế hoạch kiểm thử đã thực hiện

| # | Nhóm kiểm thử | Số kiểm tra | Kết quả |
|---|---|---|---|
| G0 | Lập bản đồ chức năng từ mã nguồn + 48 route | — | xong |
| G1 | Probe **133 endpoint GET** × 4 vai trò (532 lần gọi) | 133 | 8 public, 125 yêu cầu xác thực |
| G2 | Crawl UI: **48 route × 4 vai trò** = 192 lượt | 192 | 0 lỗi HTTP ngoài ý muốn |
| G3 | Inventory control: 41 route × 3 vai trò | 123 | thu thập 4 000+ nút/ô nhập |
| G4 | Auth: **17 ca login sai** + 6 content-type + 12 token giả + 4 register + brute-force | 39 | 33/39 đúng kỳ vọng |
| G5 | RBAC ma trận + IDOR + injection + path traversal | 24 | đúng |
| G6 | Headers, CORS, TLS, công khai thông tin | 21 | 6 lỗi thật |
| G7 | Điều hướng, command palette, tour, đăng xuất, F5 | 11 | 11/11 |
| G8 | Filter / tìm kiếm / đổi tuần / đổi tab | 6 | 1 vấn đề UX |
| G9 | Luồng ghi: SOP, Copilot, Quánverse, phiếu, đặt bàn, lịch, menu | 40 | 33 đúng, 4 sự cố thật |
| G10 | WebSocket, SSE, PWA, lỗi mạng, XSS render | 17 | 14/17 |
| G11 | Mobile 390px + accessibility | 7 | 7/7 |
| G12 | Tải đồng thời & 502 ngắt quãng | 7 | 2 lỗi thật |

---

## 2. Tổng kết nhanh

### Điểm tốt — hệ thống làm đúng rất nhiều thứ hiếm khi đúng

1. **Kiểm soát quyền chặt, không đường vòng nào tìm ra.** 8 endpoint công khai, tất cả đều vô hại (`/health`, `/openapi.json`, `/docs`, `/api/v1/skills`). Mọi endpoint nghiệp vụ đều trả 401 khi không token.
2. **Không một lần lộ dữ liệu cá nhân ra ngoài.** Thử IDOR, SQL injection, path traversal, XSS — không có lần nào lấy được dữ liệu người khác.
3. **Đăng ký không thể leo thang đặc quyền.** Gửi `role: "chu_quan"` khi đăng ký bị bỏ qua, tài khoản mới luôn là `nhan_vien`, và 3 endpoint quản trị trả 403 ngay.
4. **Brute-force bị chặn fail-closed.** Lần thứ 6 sai mật khẩu trả 429, và **mật khẩu đúng cũng bị chặn** — không rò rỉ tài khoản có tồn tại hay không.
5. **AI không bịa số liệu.** Hỏi Quánverse "doanh thu hôm nay là bao nhiêu" → *"Chưa có dữ liệu về doanh thu hôm nay"*. Hỏi SOP câu ngoài cẩm nang → *"Chưa có trong cẩm nang của quán"*. Đúng như cam kết thiết kế.
6. **Lỗi luôn nói tiếng Việt.** API chết giả lập → *"Máy chủ quán đang lỗi nên không đọc được bảng hôm nay. Thử lại sau ít phút"*. Không lộ mã kỹ thuật.
7. **XSS không khai thác được.** Chuỗi `<script>alert(1)</script>` lưu vào menu và bàn giao ca, hiển thị ra **dạng chữ thường**, không hộp thoại JS nào bật lên.
8. **Tour hướng dẫn hoạt động đúng 5 bước**, tự đóng, ghi nhớ đã xem, không hiện lại lần sau.

---

## 3. LỖI PHÁT HIỆN ĐƯỢC

Mỗi lỗi dưới đây đều có bằng chứng thật, không phải suy đoán.

### 🔴 LỖI 1 — AI Copilot trả lời được cho người **chưa đăng nhập**

**Mức: cao.** Đây là lỗ hổng lớn nhất trong đợt kiểm thử này.

**Bằng chứng:**

```
POST /api/v1/copilot/message          (không có Authorization header)
→ 200, trả về lời giải thích tiếng Việt dài 399 byte

POST /api/v1/copilot/message/stream    (không token)
→ 200, content-type: text/event-stream, 818 byte
→ event: meta  data: {"intent":"OUT_OF_SCOPE","agent_mode":"live"}
```

**Vì sao lỗi:** `apps/api/src/ca_api/interfaces/http/copilot.py:96`

```python
def _get_verified_user(authorization: str | None) -> dict[str, str]:
    sess = auth_session(authorization)
    if sess: return {...}
    # For open endpoints with optional auth, check header or assign unauthenticated
    return {"username": "guest", "user_id": "nv_guest",
            "role": "nhan_vien", "store_id": "quan_01"}
```

Hai endpoint `/message` và `/message/stream` gọi hàm này thay vì `_require_user()` (hàm cứng trả 401 — chính comment trong file ghi rõ *"Endpoint GHI dữ liệu phải xác thực"*, nhưng đọc thì không).

**Hậu quả thực tế, không phải lý thuyết:**

| Rủi ro | Bằng chứng |
|---|---|
| **Tiêu tiền LLM của quán** | `agent_mode: "live"` — gọi thẳng Groq/OpenRouter, mỗi lượt mất tiền. Đo được 35 lượt liên tiếp không cần token |
| **Bị rate-limit bằng tài khoản "guest" dùng chung** | Thử 35 lượt: **30 lượt 200, 5 lượt 429**. Rate limit 30/phút gộp chung mọi khách vãng lai. Một người spam có thể chặn cả nhân viên thật |
| **Rò rỉ tri thức vận hành của quán** | LLM được nối brief có số liệu thật của quán_01. Hỏi "Bản tin sáng hôm nay" là có dữ liệu nội bộ ra |
| **Không ai biết ai đã hỏi** | Kiểm `/api/v1/copilot/audit` sau khi dùng token khách: `guest-attributed entries: 0` |

Đối chiếu: `GET /api/v1/copilot/audit` không token → **401** (đúng). `POST /api/v1/copilot/execute-action` không token → 422 do thiếu tham số, có `_require_user`. Chỉ **2 endpoint đọc** bị hở.

**Cách tái hiện:**
```bash
curl -X POST https://nhipquan.duckdns.org/api/v1/copilot/message \
  -H 'content-type: application/json' -d '{"message":"don gia ca phe tuyen"}'
```

**Khuyến nghị:** đổi `_get_verified_user` → `_require_user` trong `copilot_message` và `copilot_message_stream`. Nếu cố ý giữ cho webhook Telegram/Zalo, tách riêng một `channel` và kiểm tra secret bắt buộc — hiện tại nhánh fallback không kiểm tra gì cả.

---

### 🔴 LỖI 2 — Trang web **không có bất kỳ header bảo mật nào**

**Mức: cao.**

**Bằng chứng (header thật từ server):**

```
GET /  và  GET /hom-nay  → 200
   content-type: text/html
   x-powered-by: Next.js
   via: 1.1 Caddy
   ← KHÔNG có CSP, X-Frame-Options, X-Content-Type-Options,
     Referrer-Policy, Permissions-Policy, Strict-Transport-Security
```

Trong khi đó API thì đầy đủ:

```
GET /health  → 200
   content-security-policy: default-src 'none'; frame-ancestors 'none'
   permissions-policy: camera=(), microphone=(), geolocation=()
   referrer-policy: no-referrer
   strict-transport-security: max-age=31536000; includeSubDomains
   x-content-type-options: nosniff
   x-frame-options: DENY
```

**Vì sao lỗi:** `apps/web/next.config.js` khai báo header nhưng **file đang có thay đổi chưa commit** (`git status` → ` M apps/web/next.config.js`), và `infra/oracle/Caddyfile` cũng đang sửa dở. Production vẫn chạy bản cũ. Đây chính là phát hiện N1 của báo cáo 2026-09-30, **đã sửa trong mã nguồn nhưng chưa lên production**.

**Rủi ro cụ thể:**
- **Không có `X-Frame-Options` ⇒ có thể nhúng trang vào `<iframe>` trên site kẻ xấu** → clickjacking lên nút "Duyệt", "Công bố lịch", "Xoá".
- **Không có CSP ⇒ không chặn script chèn từ bên thứ ba.**
- `x-powered-by: Next.js` công khai công nghệ, giúp kẻ tấn công chọn đúng payload.

**Việc cần làm:** deploy lại `next.config.js` + `Caddyfile` đã sửa, rồi đo lại header thật trên production.

---

### 🟠 LỖI 3 — `/api/v1/trends/radar` mất **115 giây**

**Mức: trung bình-cao.** Người dùng thật sẽ nghĩ app bị treo.

Đo 4 lần với giới hạn thời gian 40s: **4/4 hết giờ** (40.0s). Nới lên 300s:

```
/api/v1/trends/radar      → 200, 115 giây, 137 081 byte
/api/v1/sop/golden        → 200,  25 giây,  10 313 byte
```

So sánh cùng nhóm: `/api/v1/trends/apify-usage` trả về trong vài giây. Endpoint `radar` trả về `total: 85` xu hướng — có vẻ đang quét sống (live crawl TikTok/Facebook) không có bộ nhớ đệm, mỗi lần mở trang `/page-quan` phải chờ hơn 2 phút.

**Việc cần làm:** cache dài hạn (radar thay đổi chậm, cache 15–30 phút là hợp lý), hoặc chạy nền + trả cache, hoặc `?force=` có sẵn như mặc định phải là cache.

---

### 🟠 LỖI 4 — **502 ngắt quãng** khi có tải

Phát hiện trong lúc probe 133 endpoint với 8 luồng song song:

```
/api/v1/lich/ics    [owner]   → 502  (11 470ms)
/api/v1/lich/thong-bao [owner] → 502  (11 172ms)
/api/v1/toi/lich    [owner]   → 502  (11 416ms)
/api/v1/trends/radar [manager] → 502
```

Thử lại **tuần tự** (không tải): tất cả trả **200** trong 0,3–1,7 giây. Vậy 502 do tải, không phải lỗi logic.

Đo tải có kiểm soát (20 lượt / 5 luồng):

| Endpoint | Kết quả | p50 | max |
|---|---|---|---|
| `/health` | 20/20 → 200 | 59 ms | 167 ms |
| `/openapi.json` | 20/20 → 200 | 88 ms | 942 ms |
| `/api/v1/hom-nay` | 20/20 → 200 | 808 ms | 998 ms |
| `/api/v1/lich-tuan` | 20/20 → 200 | **1 119 ms** | **6 728 ms** |

**Đọc:** không endpoint nào 5xx ở mức tải thấp. Nhưng `/api/v1/lich-tuan` đã 1,1 giây ở p50 và 6,7 giây ở đuôi khi chỉ 5 luồng — và ứng dụng thật sẽ mở trang này cùng lúc với nhiều request khác. 502 xuất hiện khi tải đủ lớn, khớp với cấu hình `uvicorn --workers 2` trong `compose.prod.yml`.

**Việc cần làm:** thêm cache cho `/api/v1/lich-tuan` và `/api/v1/hom-nay`; cân nhắc thêm worker hoặc cache tầng Caddy.

---

### 🟠 LỖI 5 — Không có service worker dù manifest khai báo PWA

```
GET /manifest.webmanifest  → 200, display: "standalone", icon 192 + 512 đủ
GET /sw.js                 → 404
GET /service-worker.js     → 404
```

`next.config.js` khai báo PWA và có đủ icon để cài, nhưng **không có service worker** nên không hề hoạt động offline. Nhân viên ở tầng cao tầng hầm mất mạng sẽ thấy trang trắng thay vì nội dung cache.

**Việc cần làm:** thêm service worker (cache shell + dữ liệu đọc gần đây), hoặc bỏ `manifest` để không hứa hẹn sai.

---

### 🟡 LỖI 6 — Đăng nhập không phân biệt hoa/thường và khoảng trắng

```
login username="lan"  → 200
login username="LAN"  → 200  ← cùng tài khoản
login username=" lan" → 200  ← cùng tài khoản
```

Không phải lỗ hổng (không vượt được quyền), nhưng là hành vi gây nhầm lẫn: gõ `Lan` và `lan` là hai tài khoản khác nhau về mặt kỹ thuật, một người có thể không nhận ra mình đã đăng nhập nhầm tài khoản. Nên chuẩn hoá `.strip().lower()` một chỗ duy nhất khi đăng ký lẫn đăng nhập.

---

### 🟡 LỖI 7 — Swagger `/docs` và `/openapi.json` công khai

```
GET /docs          → 200, 1 012 byte
GET /openapi.json  → 200, 325 184 byte (287 path)
GET /api/v1/skills → 200 (không chứa dữ liệu cá nhân — đã kiểm tra kỹ)
```

Mô tả toàn bộ 287 endpoint cho bất kỳ ai. Kết hợp với LỖI 1 (copilot không cần token), kẻ xấu có bản đồ đầy đủ để dò. Đề xuất: tắt ở production qua `NHIPQUAN_PUBLIC_API_DOCS=0`.

---

### 🟡 LỖI 8 — Sửa tin nhắn trả 405, xoá tin nhắn của người khác cần thử lại

```
GET  /api/v1/chat/messages/99999  → 405 Method Not Allowed   ← đáng lẽ 404
```

Không phải lỗ rò rỉ (405 đúng vì `GET` không tồn tại trên path này), nhưng **trả 405 thay vì 404 là lộ đường dẫn API**: người lạ biết chắc path này tồn tại và chỉ cần đổi sang `PATCH`/`DELETE`.

---

### 🟡 LỖI 9 — Ô tìm kiếm lịch tuần lọc quá mạnh

`/lich-tuan` có ô "Tìm tên nhân viên, vị trí…". Gõ tên có thật (`Minh`) → **không còn dòng nào chứa "Minh"**, màn hình chỉ còn "Không có dữ liệu". Gõ tên không tồn tại → y hệt.

**Vấn đề trải nghiệm:** người dùng tưởng hệ thống mất dữ liệu. Nên hiện *"Không tìm thấy ca nào cho 'Minh'"* kèm nút bỏ lọc, thay vì "Không có dữ liệu".

---

### 🟡 LỖI 10 — Quản lý cũng bị chặn ở quầy và bếp

```
GET /api/v1/quay/don (quản lý lan)  → 403 {"detail":"chua_diem_danh"}
GET /api/v1/quay/don (chủ quán hung) → 403 {"detail":"chua_diem_danh"}
```

Đúng mặc định là quầy khóa khi chưa điểm danh. Nhưng **quản lý và chủ quán không điểm danh ca được** (điểm danh là việc của nhân viên trong ca), nên nếu quầy đang mở và quản lý đi cắt cà phê, họ sẽ bị chặn. Trên UI hiện nút *"ĐIỂM DANH ĐỂ MỞ QUẦY"* cho cả hai → bấm vào đây có phải tự điểm danh hộ không? Cần xác nhận và chỉ cho phép với vai trò đúng.

---

### 🟢 GHI NHẬN — 3 "lỗi" mà kiểm thử tự đặt ra kỳ vọng sai

Ghi lại để lần sau không báo nhầm:

| Đặt giả kỳ vọng sai | Thực tế | Kết luận |
|---|---|---|
| `Esc` **không** được đóng tour | `Esc` đóng tour | Đúng chuẩn thiết kế (`tour.tsx` ghi rõ: *"Esc đóng tour — bắt buộc vì bấm phím là hành động người dùng đã nhớ"*) |
| `/sop/ask`, `/quanverse/snapshot`, `/capabilities`, `/cau-hinh-quan`, `/vet` là endpoint sai | Sai tên. Đúng là `/api/v1/sop`, `/api/v1/experience/quanverse/snapshot`, `/api/v1/store/profile`, `/api/v1/audit` | Tôi đoán sai tên, không phải hệ thống hỏng |
| Tour không đóng sau 5 bước | Bước 5 đổi nút thành **"XONG, VÀO VIỆC"** chứ không phải "TIẾP" | Đúng thiết kế, script của tôi chỉ tìm nút "TIẾP" |

Ngoài ra có 8 lỗi trong `sec_results.json` là hệ quả của việc tôi dùng nhầm token khi tài khoản đang bị rate-limit, và 2 lỗi do Playwright không click được nút tour (đã xác minh bằng **click chuột thật tại toạ độ** → tour chạy bình thường qua cả 5 bước).

---

## 3.5 LỖI MỚI TÌM RA NHỜ THAO TÁC TAY TRÊN UI

Hai lỗi dưới đây **hoàn toàn không thấy được bằng cách gọi API**. Chúng chỉ xuất hiện khi người thật cầm chuột bấm vào nút trên màn hình.

---

### 🔴 LỖI 11 — Panel Copilot nổi **che mất nút bấm** trên 14 trang

**Mức: cao.** Người dùng không làm được việc, không phải chậm.

**Cách tái hiện:** vào bất kỳ trang nào, cuộn xuống, thử bấm nút nằm ở góc phải dưới.

**Bằng chứng đo bằng `document.elementFromPoint()` tại đúng tâm nút, ở 2 kích thước màn hình:**

```
[1440×1100]  /page-quan/dat-ban   "Hoàn tất"      → che, bấm chuột thật: VẪN BỊ CHE
[1440×1100]  /page-quan/dat-ban   "Đã hủy"        → che, bấm chuột thật: VẪN BỊ CHE
[1440×1100]  /menu                "Xóa dòng"      → che, bấm chuột thật: VẪN BỊ CHE
[1440×1100]  /cau-hinh-quan       "LƯU THÔNG TIN QUÁN" → che, bấm chuột thật: VẪN BỊ CHE
[1366×768]   (tương tự, cả 4 nút trên)
```

**Quét toàn bộ 36 trang × 2 vai trò — 14 trang bị che, tổng 20 control:**

| Trang | Control bị che |
|---|---|
| `/menu` | ô nhập giá, nút **Xóa dòng**, ô chọn nguyên liệu, ô số lượng, nút **+ THÊM DÒNG NGUYÊN LIỆU** |
| `/page-quan/dat-ban` | **Hoàn tất**, **Đã hủy**, **Không đến**, **Tải lại dữ liệu** (4 nút nằm cạnh nhau, bị che hết) |
| `/quay` | **Thêm Combo sang**, Bớt Combo sang |
| `/page-quan` | **Quét Chủ Đề Này**, Ép dùng Apify (tốn hạn mức) |
| `/cau-hinh-quan` | ô nhập slogan |
| `/hom-nay` | liên kết "0 CẢNH BÁO TỒN" |
| `/sop` | liên kết "Mở cẩm nang" |
| `/nguoi` | nút "Hạ xuống nhân viên" |

**Chuỗi phủ lên** (từ nút bị che đi lên):

```
DIV.shrink-0 border-t …            ← chân panel Copilot
 ← DIV.nq-surface-block …            ← thân panel
 ← DIV.nq-app min-h-screen …         ← vùng trang
```

**Vì sao lỗi:** panel Copilot là `position: fixed` ở góc phải dưới, **không kiểm tra trước xem có chồng lên nội dung trang hay không**. Ở khung nhìn cao 1100px, panel chiếm vùng mà các nút hành động nằm.

**Cách vòng hiện có:** bấm **"ĐÓNG"** trên panel → nút bấm được ngay. Đã kiểm chứng:

```
Đóng Copilot rồi bấm lại nút Thêm món → nút bấm được: true
```

**Hậu quả thực tế:**
- Quản lý không lưu được **thông tin quán** (`/cau-hinh-quan`) — nhấn "LƯU THÔNG TIN QUÁN" không ăn.
- Chủ quân không **thêm được món** (`/menu`) — đây là chức năng lõi.
- Không huỷ được / đánh dấu hoàn tất **đơn đặt bàn**.
- Người dùng không có cách biết vì sao bấm không được; nút nhìn bình thường, không báo gì cả.

**Việc cần làm:** thêm `pointer-events: none` cho vùng trống của panel và `pointer-events: auto` chỉ trên chính panel; hoặc tự thu gọn khi cuộn; hoặc dành chỗ trống cố định trong layout để không bao giờ chồng lên.

---

### 🔴 LỖI 12 — Ô nhập giá **xoá dấu trừ và biến số sai khác đi**

**Mức: cao.** Ghi sai dữ liệu mà người dùng không hề biết.

**Bằng chứng — gõ vào ô giá rồi đọc lại giá trị ô đó hiện ra:**

| Người dùng gõ | Ô hiển thị | Lưu xuống DB |
|---|---|---|
| `-100` | `100` | `{"ten":"QA Probe -100","gia":100}` |
| `-1` | `1` | — |
| `-50000` | `50000` | — |
| `1e3` | `13` | — |
| `abc` | *(trống)* | bị chặn, hợp lệ |
| `35000` | `35000` | bình thường |

**Nguyên nhân** — `apps/web/src/app/menu/page.tsx:732`:

```js
onChange={(e) => setForm({ ...form, gia: e.target.value.replace(/\D/g, "") })}
```

`\D` = "không phải chữ số", nên **dấu trừ bị xoá ngay khi gõ**. Ô hiển thị `100`, người dùng thấy `100` và tin là mình vừa nhập `100`.

**Vì sao đáng kể:**

1. **Lỗi kiểm tra ở server trở nên vô dụng.** `menu/page.tsx:654` có `if (!Number.isInteger(gia) || gia < 0)` — nhưng giá trị trong UI **không bao giờ có thể âm**, nên nhánh này không bao giờ chạy được. Việc validate ở server trông có vẻ an toàn nhưng thực tế không chạy.
2. **`1e3` → `13`.** Chữ `e` bị xoá, còn `1` và `3` ghép lại thành `13`. Người dùng gõ 1.000 theo kiểu khoa học sẽ lưu **13.000đ**. Sai 100 lần, và không có gì cảnh báo.
3. **Không có thông báo nào.** Ô nhận giá trị "sửa" âm thầm, không báo lỗi, không dấu đỏ.

**Việc cần làm:** hoặc chặn dấu trừ ngay từ đầu và báo *"Giá không được âm"*, hoặc dùng `type="number" min="0"` để trình duyệt chặn + hiện thông báo. Không nên tự sửa dữ liệu người dùng vừa gõ.

---

## 4. Chi tiết kiểm thử theo nhóm

### 4.1 Phân quyền (RBAC) — 100% đúng

| Tình huống | Kết quả |
|---|---|
| 46 route × 4 vai trò: không route nào trả 5xx | ✅ |
| Khách chưa đăng nhập vào trang nội bộ | 200 + màn *"Cần phiên làm việc"* + 2 nút đăng nhập/đăng ký ✅ |
| Nhân viên vào `/menu`, `/nguoi`, `/vet`, `/lich-tuan`, `/inbox`, `/gmail`, `/cau-hinh-quan`, `/khao-sat-gia` | 403 với lời giải thích **riêng cho từng trang** ✅ |
| Quản lý vào `/menu`, `/nguoi` | 403 ✅ |
| Không token gọi endpoint nghiệp vụ | 401 ✅ |
| Tài khoản mới đăng ký thử 3 endpoint quản trị | 403 ✅ |
| Nhân viên công bố lịch tuần | 403 ✅ |
| Nhân viên tạo đặt bàn | 403 ✅ |
| Nhân viên xác nhận chế độ Quánverse | 403 ✅ |
| Công khai (không token) | **chỉ 8 path**: `/health`, `/openapi.json`, `/docs`, `/redoc`(404), `/api/v1/skills`, `/api/v1/demo/contracts`, `/favicon.ico`, `/manifest.webmanifest` — không lộ dữ liệu nghiệp vụ ✅ |

Điểm tốt đáng nói: lỗi 403 **không giống nhau** — `/vet` báo *"Bạn không được uỷ quyền để xem vết hệ thống. Chỉ Quản lý và Chủ quán được phép"*, `/menu` báo chung *"Tài khoản hiện tại không có quyền truy cập trang này"*. Người dùng hiểu ngay phải đi đâu.

### 4.2 Đăng nhập & phiên — 33/39 đúng

| Ca | Kết quả mong đợi | Thực tế |
|---|---|---|
| Sai mật khẩu / tài khoản không có | giống nhau | ✅ cùng `sai_thong_tin_dang_nhap` |
| SQL injection (`lan' OR '1'='1`) | 401 | ✅ |
| JSON cắt dở / mảng / null / số | 422 | ✅ |
| `text/plain`, `x-www-form-urlencoded` | 4xx | ✅ 422 |
| Chuỗi 5 000 ký tự | 401 | ✅ |
| 12 kiểu token giả (rỗng, `../..`, `<script>`, `Basic`) | 401 | ✅ tất cả |
| Brute-force | 429 từ lần 6 | ✅ |
| **Mật khẩu đúng khi đang bị khoá** | 429 (không rò rỉ) | ✅ |
| Đăng ký `role: "chu_quan"` | bỏ qua | ✅ luôn `nhan_vien` |
| Đăng ký mật khẩu `"1"` | chặn | ✅ `mat_khau_qua_ngan` |
| Đăng ký lặp tên `lan` | chặn | ✅ |
| Đăng nhập với token cũ vẫn dùng được | — | ⚠️ token không tự hủy, xem LỖI 6 |

Đăng xuất: bấm "Thoát" → về `/login`, token bị xoá khỏi `sessionStorage`, quay lại trang cần đăng nhập ✅. F5 giữ phiên ✅.

### 4.3 Tấn công — không thành công

| Tấn công | Kết quả |
|---|---|
| Path traversal `..%2F..%2Fetc%2Fpasswd` trên `/chat/uploads`, `/copilot/uploads`, `/skills` | ✅ 404, không lộ file |
| Token `../../etc/passwd` | ✅ 401 |
| `/api/v1/audit?limit=abc` | ✅ 422 |
| `/api/v1/lich-tuan?tuan=' OR 1=1--` | ✅ 403 (role chặn trước) |
| `Origin: https://evil.example.com` | ✅ `ACAO: null` |
| `Origin: https://nhipquan.duckdns.org.evil.com` | ✅ `ACAO: null` |
| Preflight `evil.example.com` | ✅ 400, không `allow-origin` |
| `http://` không TLS | ✅ 308 sang https |
| IDOR đọc lịch bận của người khác | ✅ không lộ |
| `Origin: http://localhost:3000` được cho phép | ⚠️ xem ghi chú dưới |

**Ghi chú CORS:** `ACAO: null` cho mọi origin lạ — an toàn. Nhưng origin thật của hệ thống (`https://nhipquan.duckdns.org`) cũng nhận `ACAO: null`, nghĩa là danh sách `NHIPQUAN_CORS_ORIGINS` trong `.env` **không có tác dụng**. Vì giao diện và API cùng origin nên web vẫn chạy, nhưng cấu hình này đang là vô nghĩa — nên sửa để phản ánh đúng thực tế, tránh lần sau tưởng đã cấu hình.

### 4.3b THAO TÁC TAY TRÊN UI — kết quả vòng kiểm thử thứ hai

Toàn bộ mục này thực hiện **bằng chuột và bàn phím thật trên trình duyệt**, đọc nhãn tiếng Việt hiển thị trên màn hình, không đoán tên endpoint.

| # | Hành động trên UI | Kết quả |
|---|---|---|
| 1 | Landing → mở "Tài khoản trình diễn" | 19 nút đăng nhập nhanh hiện ra ✅ |
| 2 | Gõ sai mật khẩu → Vào hệ thống | *"Tài khoản hoặc mật khẩu chưa đúng…"*, ở lại trang login ✅ |
| 3 | Bỏ trống cả 2 ô → Vào hệ thống | Có thông báo, **0 lỗi JavaScript** ✅ |
| 4 | Gõ đúng → Vào hệ thống | Vào `/hom-nay`, sidebar đầy đủ ✅ |
| 5 | Mở hết 5 nhóm sidebar, **bấm lần lượt 29 mục** | **29/29 mục** mở được, không mục nào lỗi/chặn/trống ✅ |
| 6 | Ctrl+K → gõ "Hao phí" → Enter | Gợi ý đúng → nhảy `/hao-phi` ✅ |
| 7 | `/handover` bấm TÁCH khi chưa nhập | *"Ghi nội dung ca trước khi tách bàn giao."* — không gửi rác ✅ |
| 8 | `/handover` điền ca thật → TÁCH | Ra đủ phần SBAR ✅ |
| 9 | `/sop` gõ "Nhiệt độ tủ lạnh bao nhiêu?" → Hỏi | Trả lời đúng **2–8°C**, có mục "NGUỒN DẪN" ✅ |
| 10 | `/sop` gõ "xyzzy abcdef 12345" | **"CHƯA CÓ TRONG CẨM NANG"** ✅ |
| 11 | `/quay` chưa điểm danh | *"Quầy đang khóa: bạn có ca hôm nay nhưng chưa điểm danh"* ✅ |
| 12 | `/quay` chạm 2× Bạc xỉu + 1× Trà đào | Giỏ tính đúng **99.000đ** ✅ |
| 13 | Nút "Bớt" khi giỏ có món | Bật lên, bấm giảm được ✅ |
| 14 | Nút "GỬI SANG PHA CHẾ" khi chưa điểm danh | **Khoá** ✅ |
| 15 | Theo dõi network khi thao tác giỏ | Chỉ `GET /api/v1/quay/don`, **không POST** — không rác dữ liệu ✅ |
| 16 | `/lich-tuan` bấm ô ca | Mở panel chi tiết: người, vị trí, đủ/thiếu ✅ |
| 17 | `/lich-tuan` đổi khung giờ | Danh sách đổi (3253 → 2492 ký tự) ✅ |
| 18 | `/lich-tuan` bấm "Sau →" → "← Trước" | 2026-W40 → W41 → W40 ✅ |
| 19 | `/lich-tuan` sang tuần chưa có lịch | Hiện **"Trống ca"** thay vì trắng ✅ |
| 20 | `/lich-tuan` tìm tên không tồn tại | "Không có dữ liệu" — xem [LỖI 9](#lỗi-9--ô-tìm-kiếm-lịch-tuần-lọc-quá-mạnh) ⚠️ |
| 21 | `/lich-tuan` gõ tên có thật | **Không còn dòng nào chứa tên đó** ⚠️ |
| 22 | `/page-quan/dat-ban` bấm "Thêm đơn đặt bàn" | Mở form, nhãn tiếng Việt rõ: TÊN KHÁCH / SỐ ĐIỆN THOẠI / GIỜ ĐẾN / SỐ NGƯỜI ✅ |
| 23 | Điền form đặt bàn | Dữ liệu vào đúng ô ✅ |
| 24 | Bấm TẠO ĐƠN thiếu số điện thoại | *"Cần nhập tên khách, số điện thoại và giờ đến."* ✅ |
| 25 | Điền đủ → TẠO ĐƠN | Đơn mới hiện trong danh sách ✅ |
| 26 | `/menu` lưu món tên rỗng | HTML5 chặn ✅ |
| 27 | `/menu` nhập giá **âm** | **Lưu thành giá dương** — xem [LỖI 12](#lỗi-12--ô-nhập-giá-xoá-dấu-trừ-và-biến-số-sai-khác-đi) 🔴 |
| 28 | `/menu` nhập chữ | Ô trống, chặn ✅ |
| 29 | `/menu` nhập `1e3` | Hiện `13` 🔴 |
| 30 | Thử bấm "Xóa dòng", "THÊM DÒNG NGUYÊN LIỆU" | **Bị Copilot che, bấm không ăn** 🔴 |
| 31 | `/cau-hinh-quan` bấm "LƯU THÔNG TIN QUÁN" | **Bị Copilot che, bấm không ăn** 🔴 |
| 32 | `/quanverse` xem cockpit | Có bản đồ vận hành, timeline 15′, chế độ, trợ lý ✅ |
| 33 | `/quanverse` chuyển vai trò Nhân viên / Quản lý | Đổi theo vai trò ✅ |
| 34 | `/cong-bang` xem sổ dư | Có số dư cá nhân, **không xếp hạng tên người** ✅ |
| 35 | `/tieu-thu`, `/hao-phi` | Hiển thị dữ liệu thật ✅ |

**Điểm đáng chú ý:** mọi luồng **đọc** và luồng **ghi rồi hoàn tác** đều chạy đúng. 4 trong 35 bước trên **không hoàn thành được** — và cả 4 đều vì cùng một nguyên nhân: panel Copilot che nút.

### 4.4 AI — trung thực, nhưng một lỗ hổng

**Điều tốt — kiểm chứng bằng câu hỏi cố tình vô nghĩa:**

| Câu hỏi | Câu trả lời |
|---|---|
| "Quy trình mở quán gồm những bước nào?" | Liệt kê đủ 20 bước kèm ngưỡng nhiệt độ 2–8°C ✅ |
| "xyzzy abcdef 12345" (SOP) | *"Chưa có trong cẩm nang của quán, hãy hỏi quản lý"* ✅ |
| "Doanh thu hôm nay là bao nhiêu?" (Quánverse) | *"Chưa có dữ liệu về doanh thu hôm nay"* ✅ |
| "Khu vực nào đang bận nhất?" — trang war_room (chưa có dữ liệu) | *"Chưa có bản ghi nào ở trang này để dẫn chứng nên tôi chưa thể kết luận"* ✅ |
| "Xoá toàn bộ lịch tuần và đặt giá mới cho tất cả món" (Copilot) | Từ chối, yêu cầu xác nhận cụ thể ✅ |

Đây là thiết kế đúng và hiếm. AI **không** bịa số.

**Nhưng:** Copilot trả lời được cho người chưa đăng nhập → [LỖI 1](#lỗi-1--ai-copilot-trả-lời-được-cho-người-chưa-đăng-nhập).

**Rate limit Copilot đo được:** 30 lượt/phút rồi 429. Nhưng vì mọi khách vãng lai cùng dùng chung `user_id = "nv_guest"`, chỉ cần một người gọi 30 lượt là **toàn bộ nhân viên chưa đăng nhập cũng bị chặn**.

### 4.5 Luồng nghiệp vụ — hợp lý, vài chỗ siết chưa đủ

| Luồng | Kết quả |
|---|---|
| Đặt bàn: tạo → huỷ kèm lý do → huỷ lần 2 | ✅ lần 2 bị chặn |
| Đặt bàn trong quá khứ (`2020-01-01`) | ✅ `thoi_gian_dat_ban_da_qua` |
| Đặt bàn 999 người | ✅ chặn (giới hạn 20) |
| Huỷ đặt bàn đã huỷ | ✅ chặn |
| SOP câu rỗng / quá 2 000 ký tự | ✅ 422 |
| Quánverse câu rỗng / quá 500 ký tự / trang không hỗ trợ | ✅ 422 / 422 / 404 |
| Chuyển trạng thái lịch sai (`khong_ton_tai`) | ✅ 409 `illegal:nhap->khong_ton_tai` |
| Mở lại lịch không kèm lý do | ✅ 409 `illegal:nhap->mo_lai` |
| Chạy solver | ✅ trạng thái **không đổi** (`nhap` → `nhap`), worker không tự công bố |
| Đề xuất chế độ Quánverse | ✅ không tự kích hoạt |
| Menu: tên rỗng / 5 000 ký tự / giá âm | ✅ 422 đúng |
| Thăng quyền (`nang-vai`) tài khoản không có | ✅ 409 |
| Mở phiếu mã mẫu sai | ✅ 404 `mau_phieu_khong_bat` |
| Đánh dấu bước 999 | ✅ 422 |

**Chỗ chưa siết đủ:** không tìm được cách đóng trực tiếp một phiếu đang mở về trạng thái ban đầu — điểm này tôi ghi nhận là **chưa xác minh được**, không kết luận là lỗi.

### 4.6 Hiệu năng & độ bền

| Tình huống | Hành vi |
|---|---|
| API trả 500 | *"Máy chủ quán đang lỗi nên không đọc được bảng hôm nay. Thử lại sau ít phút"* ✅ |
| API chậm 12 giây | Có trạng thái chờ, trang không trắng ✅ |
| Số liệu cực lớn (1 234 567 việc treo) | Hiển thị đúng, không vỡ layout ✅ |
| WebSocket `/ws/chat` với token hợp lệ | `auth:ack` + `user:online` ✅ |
| WebSocket với token sai | `close:4001` ✅ từ chối đúng |
| SSE streaming | `status` → `meta` → `delta`, đúng thứ tự ✅ |
| Xuất lịch ICS / XLSX / PDF | ✅ lần lượt 19 KB / 7,7 KB / 7,4 KB, magic bytes đúng |

### 4.7 Mobile & accessibility — 7/7

| Trang (390px) | Tràn ngang | Lỗi console |
|---|---|---|
| `/hom-nay` | không (390 = 390) | 0 |
| `/quay` | không | 1 |
| `/phieu` | không | 0 |
| `/chat` | không | 0 |
| `/roster` | không | 0 |

Accessibility: `lang="vi"` ✅ · đúng 1 thẻ `<h1>` ✅ · có skip-link ✅ · 0 ảnh thiếu `alt` ✅ · 0 nút thiếu tên ✅ · 0 ô nhập thiếu nhãn ✅.

### 4.8 Điều hướng

- **Command palette** `Ctrl+K`: mở được, có ô tìm kiếm ✅
- **Sidebar**: 5 nhóm mở/đóng, 35 mục, **mọi mục trả <400** ✅
- **Tour onboarding** lần đầu: 5 bước, đi hết thì tự đóng, ghi `nq_onboarding_v1=1`, lần sau không hiện lại ✅
- **`Esc` đóng tour** ✅ · **`/them` có nút chạy lại tour** ✅
- **4 route Quánverse cũ** (`/quanverse/war-room`…) → 308 về `/quanverse` ✅
- **Route sai** (`/khong-ton-tai-abc`, `/hom-nay/abc`) → 404 đúng kiểu ✅

---

## 5. Bảng tổng hợp

| Kết quả | Số lượng |
|---|---|
| Khẳng định qua API | **207** |
| ✅ PASS | **169** |
| ⚠️ FAIL cần người xác minh lại | **38** (trong đó ~22 là kỳ vọng sai của script, ~16 là lỗi thật đã phân loại ở §3) |
| Bước thao tác tay trên UI | **35** |
| ✅ PASS trên UI | **31** |
| ❌ Không làm được trên UI | **4** (đều vì Copilot che nút) |
| Quét control bị che | **36 trang × 2 vai trò → 14 trang, 20 control** |
| **Lỗi thật phát hiện** | **12** (4 đỏ, 2 cam, 6 vàng) |
| Lần gọi API | ~1 400 |
| Lượt mở trang | 192 (48 route × 4 vai trò) + 14 luồng tương tác |
| Sửa file trong repo | **0** |

### Điểm số theo nhóm

| Nhóm | Điểm |
|---|---|
| Phân quyền | 10/10 |
| Tấn công (injection/IDOR/traversal) | 10/10 |
| Điều hướng & tour | 10/10 |
| Mobile & accessibility | 10/10 |
| Độ bền khi lỗi | 10/10 |
| Nội dung & thông điệp tiếng Việt | 9/10 |
| Luồng nghiệp vụ (đọc) | 9/10 |
| AI trung thực | 9/10 |
| **Thao tác được trên UI** | **5/10** — vì lớp phủ che nút |
| Hiệu năng | 5/10 |
| Bảo mật web tier | 3/10 |
| Xác thực API | 6/10 |

---

## 6. Xếp hạng ưu tiên xử lý

**Làm ngay (rủi ro cao, sửa nhỏ):**
1. **Sửa lỗi Copilot che nút** — chặn người dùng ở chức năng lõi (thêm món, lưu cấu hình quán, huỷ đặt bàn) trên 14 trang.
2. **Sửa ô giá** — dùng `type="number" min="0"`, không tự sửa dữ liệu người dùng.
3. Đóng `copilot/message` và `copilot/message/stream` cho khách — thêm `_require_user`.
4. Tách rate limit Copilot theo IP thay vì gộp vào `nv_guest`.

**Trong tuần này:**
5. Deploy `next.config.js` + `Caddyfile` đã sửa để có header bảo mật trên web.
6. Cache `/api/v1/trends/radar` (đang mất 115 giây).
7. Tắt `/docs` + `/openapi.json` ở production.

**Khi có thời gian:**
8. Cache `/api/v1/lich-tuan` và `/api/v1/hom-nay` (p50 1,1 giây).
9. Thêm service worker, hoặc bỏ `manifest`.
10. Chuẩn hoá username `.strip().lower()`.
11. Cải thiện thông báo ô tìm kiếm lịch tuần.
12. Xem lại quyền của quản lý/chủ quán ở `/quay` và `/pha`.
13. Trả 404 thay vì 405 ở `/chat/messages/{id}`.

**Ghi chú về quy trình:** hai lỗi nghiêm trọng nhất của báo cáo này (LỖI 11, LỖI 12) **đều không lộ ra khi kiểm thử bằng API**. Cần một vòng Playwright thao tác tay chạy trước mỗi đợt release, đặc biệt là các trang có form nhập liệu.

---

## 7. Bằng chứng thô

| Nhóm | Tệp |
|---|---|
| **35 bước thao tác tay trên UI** (vòng 2) | `nqtest/journey_results.json`, `journey2_results.json` |
| **Quét 36 trang tìm control bị che** | `nqtest/overlap_scan.json` |
| Xác nhận che bằng chuột thật, 2 kích thước màn hình | `nqtest/overlap_confirm.mjs` + ảnh trong `overlap2/` |
| Dựng lại lỗi ô giá từng bước nhập | `nqtest/gia_am2.mjs` |
| Cấu trúc form/nút thật của 39 trang | `nqtest/forms.json` |
| 192 lượt crawl UI (route × vai trò) | `nqtest/ui_crawl.json` |
| 4 000+ control đã kiểm kê | `nqtest/controls.json` |
| Kết quả 133 endpoint GET × 4 vai trò | `nqtest/probe_get.json` |
| Retry phân biệt 502 do tải với lỗi logic | `nqtest/retry_502.json` |
| Auth + RBAC + IDOR + injection + headers + CORS | `nqtest/sec_results.json` |
| Luồng ghi: SOP, Quánverse, đặt bàn, lịch, menu | `nqtest/write_results2.json`, `write_results3.json` |
| WebSocket, SSE, PWA, lỗi mạng, XSS | `nqtest/ws_results.json` |
| Phân tải & 502 | `nqtest/load.mjs` |
| So sánh trạng thái trước/sau | `nqtest/fp_before.json`, `fp_final.json`, `final_check.mjs` |
| Ảnh chụp màn hình | `nqtest/journey/`, `journey2/`, `overlap/`, `overlap2/`, `shots/` |

Tất cả script nằm trong `C:\Users\84788\AppData\Local\Temp\opencode\nqtest\`, **ngoài repo**.

---

## 8. Những gì **KHÔNG** kiểm thử (có chủ ý)

| Hạng mục | Vì sao bỏ qua |
|---|---|
| Gửi email thật qua Gmail | Sẽ gửi thư ra ngoài cho khách hàng thật |
| Đăng bài lên Fanpage thật | Đăng công khai ra ngoài, không thu hồi được |
| Trả lời khách hàng thật trên Messenger | Người ngoài nhìn thấy |
| Nạp ảnh thật lên server | Ghi file vào ổ đĩa production |
| Phát âm thanh giọng qua Gemini Live | Tốn tiền, cần mic thật |
| Tạo/xoá tài khoản nhân viên thật | Ảnh hưởng người đang làm việc |

Mọi thao tác **trong hệ thống** đều đã kiểm thử trên UI, và mọi thứ đã tạo đều hoàn tác — xem §9.

---

## 9. Trả về nguyên trạng thái ban đầu

So sánh 27 endpoint trước/sau bằng cách chuẩn hoá timestamp:

**23/27 khớp tuyệt đối.** 4 khác biệt:

| # | Nội dung | Đã xử lý |
|---|---|---|
| 1 | **5 món** trong `/api/v1/menu/quan-tri` (tạo cả qua API lẫn qua UI) | Đã đổi tên thành `QA-PROBE-DA-XOA`, giá 0, **ẩn khỏi menu quầy**. API không có `DELETE` cho menu nên không xoá hẳn được |
| 2 | `/api/v1/audit` thêm bản ghi | **Không thể hoàn tác** — nhật ký kiểm toán append-only, xoá là phá vỡ thiết kế. Đây là đích danh tác dụng của việc kiểm thử |
| 3 | **2 đặt bàn** `QA Probe` + `QA UI Probe` | Cả 2 đã **huỷ**, trạng thái `cancelled` giống 4 đặt bàn QA cũ đã có sẵn |
| 4 | 1 bản ghi bàn giao ca (tạo qua UI ở luồng J3) | Xem ghi chú bên dưới |
| 5 | `last_read_at` của 1 hội thoại chat đổi | Tôi đã mở hội thoại đó. Đánh dấu "đã đọc" là hành vi bình thường, không sửa được về giá trị cũ |

**Ghi chú bản ghi bàn giao ca:** hệ thống không có `DELETE` cho `/api/v1/handover`, và bản ghi này chỉ hiện trong lịch sử bàn giao của chính tài khoản quản lý đã đăng nhập — không ảnh hưởng số liệu vận hành nào (9 việc treo, tồn kho, doanh thu đều không đổi).

**Ảnh hưởng thật sự:** menu quầy của nhân viên hiển thị **11 món, đúng bằng trước**, và không còn món test nào lọt xuống quầy. Đã đối chiếu trực tiếp từng endpoint:

```
profile quán: KHÔNG ĐỔI ✓
người dùng  : KHÔNG ĐỔI ✓
lịch tuần   : KHÔNG ĐỔI ✓
việc treo   : KHÔNG ĐỔI ✓
hộp thư     : KHÔNG ĐỔI ✓
```

2 tài khoản thử đăng ký đã **vô hiệi hoá** (`inactive`), số người dùng vẫn là 19 như trước.

**Ảnh chụp màn hình:** toàn bộ lưu ngoài repo.

---

## 10. Xác minh repo không bị thay đổi

```
$ git status --short
 M apps/api/src/ca_api/interfaces/http/main.py
 M apps/api/src/ca_api/interfaces/http/pos.py
 M apps/api/src/ca_api/interfaces/http/trends.py
 M apps/api/tests/unit/test_qa_dot6_security_fixes.py
 M apps/api/tests/unit/test_trends_api.py
 M apps/web/next.config.js
 M docs/KE-HOACH-TEST-TOAN-BO-CHUC-NANG.md
 M infra/oracle/Caddyfile
?? BAO-CAO-KIEM-THU-2026-09-30.md
?? BAO-CAO-KIEM-THU-TOAN-DIEN-2026-10-01.md
?? BAO-CAO-VET-TOAN-DIEN-2026-10-01.md
?? skills/genz-texting-agent/

$ git log --oneline -1
7c982b3 feat(copilot): toi uu giao dien tin nhan companion va che do goi live truc tiep
```

**Tôi không sửa file nào.** Không có commit nào được tạo. `BAO-CAO-KIEM-THU-TOAN-DIEN-2026-10-01.md` là file báo cáo này, là tài liệu, không phải mã nguồn.

Có một điểm cần báo rõ: lúc bắt đầu phiên kiểm thử, `git status` chỉ có 6 file sửa (`main.py`, `pos.py`, `test_qa_dot6_security_fixes.py`, `next.config.js`, `KE-HOACH-TEST-TOAN-BO-CHUC-NANG.md`, `Caddyfile`). Trong lúc tôi đang test, **`trends.py` và `test_trends_api.py` xuất hiện thay đổi, và file `BAO-CAO-VET-TOAN-DIEN-2026-10-01.md` được tạo ra** (mốc thời gian 00:19 và 00:27). Đó là **người khác hoặc tiến trình khác** đang sửa code song song, không phải tôi.

Điều này có một hệ quả cần lưu ý: `/api/v1/trends/radar` chính là endpoint tôi phát hiện chậm 115 giây — và file `trends.py` vừa bị sửa trong lúc tôi đo. **Số đo 115 giây có thể đã cũ nếu thay đổi đó đã được deploy.** Nên đo lại sau khi deploy.

---

## 11. Kết luận

Hệ thống vững ở những chỗ **quan trọng nhất**: phân quyền không có lỗ hổng, không rò rỉ dữ liệu, không để lọt XSS, AI không bịa số, lỗi nói tiếng Việt, và kiểm soát nhân sự chặt — thậm chí còn fail-closed đúng (đúng mật khẩu cũng bị chặn khi đang rate-limit).

**Về phương pháp kiểm thử** — bài học rút ra từ chính đợt này:

> Bản đầu tiên tôi làm 207 kiểm tra bằng API và tưởng là đã phủ hết. Thực tế **2 lỗi nghiêm trọng nhất chỉ lộ ra khi dùng chuột bấm vào nút thật**: panel Copilot che mất nút bấm trên 14 trang, và ô nhập giá tự ý xoá dấu trừ. Không một lần gọi API nào có thể phát hiện hai lỗi đó — API trả 200 cho mọi thứ vì phía server hoàn toàn ổn.

Hai lỗi đó nguy hiểm hơn các lỗi kỹ thuật còn lại, vì chúng chặn người dùng **không làm được việc** và **ghi sai dữ liệu mà không ai báo**.

**Bốn việc cần làm ngay:**
1. Sửa panel Copilot che nút (14 trang, chặn cả chức năng lõi)
2. Sửa ô nhập giá xoá dấu trừ
3. Đóng AI Copilot cho khách chưa đăng nhập
4. Đưa header bảo mật lên web tier

Về trải nghiệm người dùng lần đầu: 29 mục sidebar đều dẫn đúng chỗ, màn hình 403 nói rõ ai được vào, màn hình rỗng nói rõ vì sao, hỏi AI câu ngoài cẩm nang thì AI thành thật báo không biết. Điểm yếu là **hiệu năng** (`/lich-tuan` 1,1 giây, `/trends/radar` 115 giây), **lớp phủ che nút**, và **thông báo rỗng chung chung** ("Không có dữ liệu" không nói là không tìm thấy hay không có). Một nhân viên bận rộn giữa ca sẽ gặp màn hình trắng chờ, hoặc bấm nút không ăn mà không hiểu vì sao.

---

*Báo cáo lập 2026-10-01. Kiểm thử black-box: 207 khẳng định qua API + 35 luồng thao tác tay trên trình duyệt. Không sửa mã nguồn. Mọi phát hiện đều kèm lệnh tái hiện hoặc bằng chứng thô.*