# Danh sách lỗi phát hiện — NHỊP QUÁN

**Hệ thống:** https://nhipquan.duckdns.org (production)
**Ngày:** 2026-10-01 · **Không sửa code, chỉ kiểm thử và báo cáo**

Tìm được **12 lỗi**: 4 nghiêm trọng, 2 trung bình, 6 nhẹ.

| # | Mức | Lỗi | Ảnh hưởng |
|---|---|---|---|
| 1 | 🔴 | AI Copilot trả lời được không cần đăng nhập | Mất tiền LLM, lộ dữ liệu quán |
| 2 | 🔴 | Panel Copilot che nút bấm trên 14 trang | Người dùng không làm được việc |
| 3 | 🔴 | Ô nhập giá xoá dấu trừ | Ghi sai giá, không ai báo |
| 4 | 🔴 | Trang web không có header bảo mật | Clickjacking, không chặn script |
| 5 | 🟠 | `/api/v1/trends/radar` mất 115 giây | Trang `/page-quan` treo 2 phút |
| 6 | 🟠 | 502 ngắt quãng khi có tải | Trang lỗi khi nhiều người dùng |
| 7 | 🟡 | Không có service worker dù khai báo PWA | Offline không dùng được |
| 8 | 🟡 | Đăng nhập không phân biệt hoa/thường, khoảng trắng | Gõ nhầm tài khoản mà không biết |
| 9 | 🟡 | `/docs` và `/openapi.json` công khai | Lộ bản đồ 287 endpoint |
| 10 | 🟡 | Ô tìm kiếm lịch tuần lọc quá mạnh | Tưởng mất dữ liệu |
| 11 | 🟡 | Quản lý/chủ quán bị chặn ở `/quay` và `/pha` | Không dùng được chức năng lõi |
| 12 | 🟡 | `/chat/messages/{id}` trả 405 thay vì 404 | Lộ đường dẫn API |

---

## 🔴 1. AI Copilot trả lời được không cần đăng nhập

**Bằng chứng**
```bash
curl -X POST https://nhipquan.duckdns.org/api/v1/copilot/message \
  -H 'content-type: application/json' -d '{"message":"don gia ca phe tuyen"}'
# → 200, trả lời tiếng Việt dài 399 byte
```

**Nguyên nhân** `apps/api/src/ca_api/interfaces/http/copilot.py:96` — `_get_verified_user()` fallback về tài khoản `guest` thay vì dùng `_require_user()`.

**Hệ quả**
- Gọi thẳng LLM live → tiêu tiền của quán. Đo 35 lượt không cần token.
- Mọi khách vãng lai dùng chung `user_id = "nv_guest"` → một người gọi 30 lượt là **chặn cả nhân viên thật**.
- Sau khi khách hỏi, `/api/v1/copilot/audit` **không ghi dòng nào** → không truy vết được.

**Sửa:** đổi `_get_verified_user` → `_require_user` trong `copilot_message` và `copilot_message_stream`. Tách rate limit theo IP.

---

## 🔴 2. Panel Copilot nổi che nút bấm trên 14 trang

**Bằng chứng** — đo `document.elementFromPoint()` tại tâm nút, click chuột thật, ở cả 1440×1100 và 1366×768:

| Trang | Nút bị che |
|---|---|
| `/menu` | ô giá, **Xóa dòng**, chọn nguyên liệu, ô số lượng, **+ THÊM DÒNG NGUYÊN LIỆU** |
| `/page-quan/dat-ban` | **Hoàn tất**, **Đã hủy**, **Không đến**, Tải lại dữ liệu |
| `/cau-hinh-quan` | ô slogan, **LƯU THÔNG TIN QUÁN** |
| `/quay` | **Thêm Combo sang**, Bớt Combo sang |
| `/page-quan` | **Quét Chủ Đề Này**, Ép dùng Apify (tốn hạn mức) |
| `/nguoi` | **Hạ xuống nhân viên** |
| `/sop` | liên kết "Mở cẩm nang" |
| `/hom-nay` | liên kết "0 CẢNH BÁO TỒN" |

Chuỗi phủ lên: `DIV.nq-surface-block` (position: fixed) ← `DIV.nq-app` ← `BODY`

**Nguyên nhân:** panel là `position: fixed` góc phải dưới, không kiểm tra trước khi chồng lên nội dung trang.

**Hệ quả:** chủ quân không thêm được món, quản lý không lưu được cấu hình quán, không huỷ được đơn đặt bàn. Nút nhìn bình thường, bấm không ăn, **không có bất kỳ thông báo nào**.

Cách vòng: bấm "ĐÓNG" trên panel là bấm được ngay.

**Sửa:** `pointer-events: none` cho vùng trống của panel, `pointer-events: auto` chỉ trên chính panel. Hoặc tự thu gọn khi cuộn.

---

## 🔴 3. Ô nhập giá xoá dấu trừ, biến số sai

**Bằng chứng**

| Người dùng gõ | Ô hiển thị | Lưu xuống |
|---|---|---|
| `-100` | `100` | `{"ten":"QA Probe -100","gia":100}` |
| `-50000` | `50000` | — |
| `1e3` | `13` | — |

**Nguyên nhân** `apps/web/src/app/menu/page.tsx:732`

```js
onChange={(e) => setForm({ ...form, gia: e.target.value.replace(/\D/g, "") })}
```

`\D` xoá mọi ký tự không phải số, **kể cả dấu trừ**.

**Hệ quả**
- Validate `gia < 0` ở dòng 654 **không bao giờ chạy được** — UI không tạo ra giá trị âm.
- `1e3` → `13`: gõ 1.000 kiểu khoa học lưu thành 13.000đ, sai 100 lần, không cảnh báo.
- Người dùng nhìn thấy `100` và tin là mình vừa nhập `100`.

**Sửa:** dùng `type="number" min="0"` để trình duyệt chặn và hiện thông báo. Không tự sửa dữ liệu người dùng vừa gõ.

---

## 🔴 4. Trang web không có header bảo mật nào

**Bằng chứng** — header thật từ server:

```
GET /          → 200, x-powered-by: Next.js, via: 1.1 Caddy
GET /hom-nay   → 200
   KHÔNG có CSP, X-Frame-Options, X-Content-Type-Options,
   Referrer-Policy, Permissions-Policy, Strict-Transport-Security

GET /health    → 200
   content-security-policy: default-src 'none'; frame-ancestors 'none'
   strict-transport-security: max-age=31536000; includeSubDomains
   x-frame-options: DENY
   ... (đủ cả 6)
```

**Nguyên nhân:** `apps/web/next.config.js` và `infra/oracle/Caddyfile` đã khai báo header nhưng đang có thay đổi **chưa commit, chưa deploy**. Production vẫn chạy bản cũ.

**Hệ quả:** không có `X-Frame-Options` ⇒ nhúng trang vào `<iframe>` trên site kẻ xấu để clickjacking lên nút "Duyệt", "Công bố lịch".

**Sửa:** deploy lại 2 file đã sửa, rồi đo lại header thật.

---

## 🟠 5. `/api/v1/trends/radar` mất 115 giây

**Bằng chứng**

```
4 lần đo với giới hạn 40s  → 4/4 hết giờ
nới lên 300s  → 200, 115 giây, 137.081 byte
/api/v1/sop/golden          → 200,  25 giây
/api/v1/trends/apify-usage  → 200, vài giây
```

**Hệ quả:** mở trang `/page-quan` phải chờ hơn 2 phút.

**Sửa:** cache 15–30 phút (radar thay đổi chậm), hoặc chạy nền rồi trả cache.

---

## 🟠 6. 502 ngắt quãng khi có tải

**Bằng chứng** — probe 133 endpoint với 8 luồng song song:

```
/api/v1/lich/ics        [owner]  → 502 (11.470ms)
/api/v1/lich/thong-bao  [owner]  → 502 (11.172ms)
/api/v1/toi/lich        [owner]  → 502 (11.416ms)
```

Thử lại **tuần tự** → tất cả 200 trong 0,3–1,7 giây. Nên là lỗi tải, không phải lỗi logic.

Đo có kiểm soát (20 lượt / 5 luồng):

| Endpoint | Kết quả | p50 | max |
|---|---|---|---|
| `/health` | 20/20 → 200 | 59 ms | 167 ms |
| `/api/v1/lich-tuan` | 20/20 → 200 | **1.119 ms** | **6.728 ms** |

**Sửa:** cache `/api/v1/lich-tuan` và `/api/v1/hom-nay`; cân nhắc thêm worker (hiện `uvicorn --workers 2`).

---

## 🟡 7. Không có service worker dù manifest khai báo PWA

```
GET /manifest.webmanifest → 200, display: "standalone", icon 192 + 512 đủ
GET /sw.js                → 404
GET /service-worker.js    → 404
```

Nhân viên mất mạng (tầng hầm) thấy trang trắng.

**Sửa:** thêm service worker, hoặc bỏ `manifest` để không hứa hẹn sai.

---

## 🟡 8. Đăng nhập không phân biệt hoa/thường và khoảng trắng

```
"lan"  → 200
"LAN"  → 200   ← cùng tài khoản
" lan" → 200   ← cùng tài khoản
```

Không phải lỗ hổng, nhưng gây nhầm: gõ `Lan` và `lan` là hai tài khoản khác nhau về kỹ thuật.

**Sửa:** chuẩn hoá `.strip().lower()` ở cả đăng ký và đăng nhập.

---

## 🟡 9. `/docs` và `/openapi.json` công khai

```
GET /docs          → 200, 1.012 byte (Swagger UI)
GET /openapi.json  → 200, 325.184 byte (287 path)
```

Kết hợp với lỗi 1 (Copilot không cần token), kẻ xấu có bản đồ đầy đủ để dò.

**Sửa:** đặt `NHIPQUAN_PUBLIC_API_DOCS=0` ở production.

---

## 🟡 10. Ô tìm kiếm lịch tuần lọc quá mạnh

`/lich-tuan`, gõ tên có thật (`Minh`) → **không còn dòng nào chứa "Minh"**, chỉ còn "Không có dữ liệu". Gõ tên không tồn tại → y hệt.

**Sửa:** hiện *"Không tìm thấy ca nào cho 'Minh'"* kèm nút bỏ lọc.

---

## 🟡 11. Quản lý và chủ quán bị chặn ở `/quay` và `/pha`

```
GET /api/v1/quay/don (quản lý lan)   → 403 {"detail":"chua_diem_danh"}
GET /api/v1/quay/don (chủ quán hung) → 403 {"detail":"chua_diem_danh"}
```

Quầy khóa khi chưa điểm danh là đúng. Nhưng quản lý **không điểm danh ca được** (việc của nhân viên trong ca), nên nếu đang mở quán và họ cần dùng thì bị chặn. UI vẫn hiện nút "ĐIỂM DANH ĐỂ MỞ QUẦY" cho cả hai.

**Cần xác minh:** bấm nút đó với quản lý thì có tự điểm danh hộ không.

---

## 🟡 12. `/chat/messages/{id}` trả 405 thay vì 404

```
GET /api/v1/chat/messages/99999 → 405 Method Not Allowed
```

Không rò rỉ dữ liệu, nhưng lộ đường dẫn: biết chắc path này tồn tại, chỉ cần đổi sang `PATCH`/`DELETE`.

**Sửa:** trả 404 cho method không hợp lệ trên path có thật.

---

## Ghi chú cho người đọc

**Lỗi 2 và 3 không thể phát hiện bằng cách gọi API.** Phía server trả 200 cho mọi thứ vì server hoàn toàn ổn — vấn đề nằm ở lớp trình duyệt. Đề xuất chạy một vòng Playwright thao tác tay trước mỗi đợt release, đặc biệt các trang có form.

**Ưu tiên xử lý:**

1. Sửa panel Copilot che nút (2)
2. Sửa ô giá (3)
3. Đóng Copilot cho khách (1)
4. Deploy header bảo mật (4)

Chi tiết đầy đủ kèm bằng chứng: `BAO-CAO-KIEM-THU-TOAN-DIEN-2026-10-01.md`