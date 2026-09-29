# KẾ HOẠCH TEST TOÀN BỘ CHỨC NĂNG — NHỊP QUÁN

> **Mục đích:** Cho AI Agent chạy **hết 50 mục test** trên production theo thứ tự an toàn
> tăng dần, và **đánh dấu ngay tại chỗ** phần đã test.
>
> **Ngày lập:** 2026-09-28 · **Bản mã khi lập:** `225f573` (= `origin/main`)
> **Nguồn dữ liệu (trích từ mã, KHÔNG bịa):**
> - 42 route: `apps/web/src/app/AppShell.tsx` → `GROUPS`
> - RBAC: `apps/web/src/lib/session.ts` → `STAFF_ACCESS` / `MANAGER_ONLY` / `OWNER_ONLY`
> - Nhãn UI: `kicker=` / `title=` / `placeholder=` trong từng `page.tsx`
> - Field API: `/openapi.json` + payload đã kiểm chứng thật ở các phiên QA trước
>
> **Kế hoạch này THAY THẾ** `DEMO_BROWSER_PLAN.md` (đã lỗi thời — nhắc `/roster`, `/vet`,
> `/inbox` như route chính trong khi sidebar hiện tại dùng `/lich-tuan`, và bảng nhãn nút
> của nó không còn khớp UI).

---

## 0. QUY ƯỚC ĐÁNH DẤU

| Ký hiệu | Nghĩa |
|---|---|
| ☐ | Chưa test |
| ✅ PASS | Đúng như cột "Mong đợi" |
| ❌ FAIL | Có bug → **ghi rõ hiện tượng + URL/endpoint + bằng chứng** |
| ⏭️ SKIP (an toàn) | Cố ý bỏ vì rủi ro gửi ra ngoài |
| 🚫 BLOCKED | Không chạy được (thiếu quyền / thiếu dữ liệu / route không tồn tại) |
| ⚠️ PARTIAL | Chạy được nhưng có điểm sai nhỏ |

**Cách dùng:** mỗi mục có ô `Kết quả` ở cuối hàng. Agent điền `✅/❌/⏭️/🚫/⚠️` + ghi chú
ngắn. Cuối tài liệu có **§5 bảng tổng hợp** để tick lại lần cuối + đếm.

---

## 1. MÔI TRƯỜNG & TÀI KHOẢN

| Mục | Giá trị |
|---|---|
| Site | `https://nhipquan.duckdns.org` |
| Bản mã cần khớp | `git rev-parse origin/main` → ghi lại hash thực tế vào §5 |
| Tài khoản | 19 acc · mật khẩu chung `nhipquan` |
| Vai dùng test | `hung` = `chu_quan` · `lan` = `quan_ly` · `minh` = `nhan_vien` |
| API docs | `/openapi.json` (nếu 404 → đã tắt bằng `NHIPQUAN_PUBLIC_API_DOCS=0`) |

### 1.1. Cách lấy token (dùng cho mọi test API)

```js
// Chạy trong Console của browser tại site production
const r = await fetch('/api/v1/auth/login', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({username: 'hung', password: 'nhipquan'})
});
const j = await r.json();
sessionStorage.setItem('nq_token', j.token);
sessionStorage.setItem('nq_role', j.role);
sessionStorage.setItem('nq_nv', j.nv_id);
```

Sau đó gọi API kèm header `Authorization: Bearer <token>`.
**Đăng xuất:** `sessionStorage.clear()` rồi tải lại trang.

### 1.2. Ma trận phân quyền (nguồn: `session.ts`)

| Tập | Route | Ý nghĩa |
|---|---|---|
| `STAFF_ACCESS` | `/` `/hom-nay` `/cuoc-hop` `/quay` `/pha` `/phieu` `/toi` `/treo` `/doi-ca` `/handover` `/hao-phi` `/tieu-thu` `/cong-bang` `/sop` `/tkb` `/qr` `/cam-nang` `/copilot` `/them` `/contracts` `/chat` `/skills` `/quanverse` `/quanverse/spatial-memory` | Mọi vai đã đăng nhập |
| `MANAGER_ONLY` | `/lich-tuan` `/roster` `/inbox` `/page-quan` `/page-quan/fb-inbox` `/ai-learning` `/gmail` `/cau-hinh-quan` `/khao-sat-gia` `/vet` `/giai-thich` `/de-xuat-thong-minh` `/thu-nghiem-an-toan` `/quanverse/war-room` `/quanverse/shift-rescue` `/quanverse/rules` | `quan_ly` + `chu_quan` |
| `OWNER_ONLY` | `/menu` `/nguoi` | Chỉ `chu_quan` |

> **Ghi chú:** `canAccess()` còn có luật `path.startsWith("/page-quan")` → manager.
> `/lich-tuan` là **alias** re-export của `/roster` (`apps/web/src/app/lich-tuan/page.tsx`).

---

## 2. QUY TẮC AN TOÀN (BẮT BUỘC)

| # | Quy tắc |
|---|---|
| S1 | **KHÔNG bấm nút gửi ra NGOÀI hệ thống.** Production đang bật `NHIPQUAN_FB_AUTO_SEND=1` + `NHIPQUAN_PAGE_MODE=live` → bấm "Đăng bài"/"Đăng phản hồi" là **đăng THẬT** lên Page công khai. Dừng ở màn duyệt, ghi `⏭️ SKIP (an toàn)`. |
| S2 | **Được ghi dữ liệu nội bộ** (đơn quầy, điểm danh, phiếu, việc treo, bàn giao, cuộc họp, xếp lịch) — nhưng **BẮT BUỘC liệt kê mọi thứ đã tạo** vào §6 để không nhầm là bug về sau. |
| S3 | **Trước khi test nhóm E** (`.env` có FB live): nếu có toggle "Tắt tự trả lời" thì bật trước. |
| S4 | **Không sửa dữ liệu bằng DevTools/SQL.** Chỉ dùng UI hoặc API công khai. |
| S5 | **Đổi tài khoản:** dùng `sessionStorage.clear()` + tải lại, hoặc quick-login ở `/`. |

---

## 3. SỔ ĐĂNG KÝ 50 MỤC TEST (theo thứ tự thực thi)

> **Thứ tự chạy:** A → B → C → D → E → F. Nhóm A chỉ đọc (0 rủi ro), B–D ghi dữ liệu nội bộ,
> E có luồng ra ngoài (cẩn trọng nhất), F kiểm biên/bảo mật sau cùng (dùng lại phiên đã đăng nhập).

---

### NHÓM A — NỀN TẢNG (8 mục · chỉ đọc · 0 rủi ro)

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| A1 | `/` | Mở trang chủ (chưa đăng nhập). Tìm nhóm "Tài khoản trình diễn (19)" | Thấy 19 tài khoản · CTA "Vào ca" → `/login` | ☐ |
| A2 | `/login` | Nhập `hung` / `saimatkhau` → bấm đăng nhập | Báo lỗi "Tài khoản hoặc mật khẩu chưa đúng…" | ☐ |
| A3 | `/login` | Nhập `hung` / `nhipquan` | 200 → chuyển `/hom-nay` · header hiện "[Chủ quán]" | ☐ |
| A4 | `/huong-dan` | Mở "Bản đồ hệ thống" | Sơ đồ render, không lỗi console | ☐ |
| A5 | `/them` | "Tất cả lối vào" | 19 tile liên kết (đếm từ `LINKS`), bấm 1 tile đi đúng trang | ☐ |
| A6 | `/contracts` | Xem danh sách hợp đồng dữ liệu | Tên **rút gọn** dạng `Lan N.` + cờ `la_du_lieu_mo_phong` | ☐ |
| A7 | `/vet` | "Vết hệ thống" → lọc theo "Người thực hiện" + thanh tìm | Bảng hiện `countLabel="vết"`; lọc giảm số dòng | ☐ |
| A8 | `/skills` | "Bộ kỹ năng AI" | Danh sách kỹ năng; API `/api/v1/skills` → **200** (không 404) | ☐ |

---

### NHÓM B — VẬN HÀNH CA & QUẦY (10 mục · ghi dữ liệu nội bộ)

> **Điều kiện tiên quyết:** `hung` đã đăng nhập. **B2 (điểm danh) phải chạy TRƯỚC B3/B4/B5**
> vì cổng quầy đòi `da_diem_danh` (`pos.py::_require_dang_ca`).

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| B1 | `/hom-nay` | Xem dashboard: KPI, bản tin sáng, khối việc | Render đủ khối · console 0 lỗi HTTP ≥400 | ☐ |
| B2 | `/qr` | Bấm **"PHÁT MÃ ĐIỂM DANH"** → chọn `nv_02` → lấy token → bấm **"ĐIỂM DANH VÀO CA"** | Phát mã 200 · điểm danh 200 · dùng lại mã cũ → **lỗi** (one-shot) | ☐ |
| B3 | `/quay` | Thêm 1–2 món vào giỏ → bấm **"Gửi sang pha chế"** | 201 · trạng thái `cho_pha` · giỏ về 0.<br>**Kiểm tra regression bug #27:** nếu CHƯA điểm danh thì phải thấy Alert *"Quầy đang khóa: bạn có ca hôm nay nhưng chưa điểm danh."* + nút gửi đơn **disabled** | ☐ |
| B4 | `/pha` | Tìm đơn vừa tạo ở cột "Chờ pha" → bấm nhận pha → hoàn tất | Đơn chuyển sang "Đang pha" rồi "Đã xong trong ca" | ☐ |
| B5 | `/phieu` | Bấm **"Tôi đã có mặt"** → chọn phiếu **"Mở quán"** | Hiện **"Bước 1 / 20"** · bấm "Xong bước này" → **"Bước 2 / 20"** (có ghi thời gian) | ☐ |
| B5b | `/phieu` | Bấm **"Để lại việc khó"** → nhập "Hết ống hút cỡ lớn" → "Ghi việc treo" | Ghi thành công · việc xuất hiện ở `/treo` | ☐ |
| B6 | `/treo` | Tab "Việc cần xử lý (n)" → bấm **"Đánh dấu xong"** 1 việc | Việc chuyển nhóm Xong · `n` giảm 1 | ☐ |
| B7 | `/cuoc-hop` | Dán transcript (máy pha rỉ nước, khách phàn nàn, đoàn 25 người) → **"Phân tích biên bản"** | Trả ≥15 trường cấu trúc (`tom_tat`, `van_de_phat_sinh`, `quyet_dinh`, `action_items`, `de_xuat_sop`…) | ☐ |
| B8 | `/handover` | Dán văn bản có **2 số lệch**: "doanh thu 2.350.000, két 2.300.000" → **"Tách thành bàn giao"** | `co_lech_so: true` + `vf_number_conflict` ≥1 chủ đề (regression bug #3) | ☐ |
| B9 | `/chat` | Chọn 1 hội thoại → gửi 1 tin nhắn | Tin hiện ngay · WebSocket **không** lỗi 502 | ☐ |

---

### NHÓM C — LỊCH & NHÂN SỰ (9 mục)

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| C1 | `/lich-tuan` | Xem ma trận tuần · bấm **"Sau →"** đổi tuần | Tuần đổi (vd W39→W40) · không lỗi | ☐ |
| C2 | `/lich-tuan` | Ở tuần `nhap`: bấm **"Xếp lịch tự động"** | Trạng thái đổi sang `cho_duyet`/`da_duyet` · lưới có phân công (CP-SAT chạy ~5–10s) | ☐ |
| C3 | `/lich-tuan` | Bấm ô ca → bấm **"Ghim"** | Toast "Đã ghim và xếp lại phần lịch còn lại." | ☐ |
| C4 | `/toi` | "Ca của tôi" | Danh sách ca của mình · nút Nhận/Nhả ca (nếu lịch đã công bố) | ☐ |
| C5 | `/doi-ca` | "Chợ đổi ca" | Tab "Ca thiếu người" + danh sách yêu cầu đổi ca | ☐ |
| C6 | `/cong-bang` | "Công bằng ca" | Biểu đồ số dư 4 trục · **19** khoá NV (không có `nv_20..25` — regression bug #16) | ☐ |
| C7 | `/tkb` | Bấm **"Thử ảnh mẫu"** → xem kết quả đọc ảnh → **"Xác nhận gắn TKB"** | Đọc được khung giờ bận · xác nhận thành công | ☐ |
| C8 | `/nguoi` | Danh sách người dùng | **"19 TỔNG TÀI KHOẢN"** · KHÔNG có "Agent Xếp Lịch"/`ai_scheduler` (regression bug #24) | ☐ |
| C8b | `/nguoi` | Mở dialog nâng vai 1 NV → **Huỷ** (không đổi thật) | Dialog hiện đúng thông tin · huỷ không ghi gì | ☐ |

---

### NHÓM D — AI & TỰ ĐỘNG HOÁ (11 mục)

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| D1 | `/copilot` | Gõ `Danh sách nhân sự của quán` | Trả **"Hiện có 19 nhân sự"** (regression bug #24) | ☐ |
| D1b | `/copilot` | Gõ câu cần duyệt (vd `Xếp lịch tuần này`) | Thẻ **"CHỜ DUYỆT"** có diff + snapshot hash · gõ `duyệt` → **"✓ ĐÃ DUYỆT"** | ☐ |
| D2 | `/sop` | Hỏi câu CÓ trong cẩm nang (`Nhiệt độ tủ lạnh bao nhiêu?`) → hỏi câu LẠ (`Giá vàng hôm nay?`) | Câu 1: trả lời + "Nguồn dẫn" · Câu 2: nói thẳng "chưa có trong cẩm nang" (**không bịa**) | ☐ |
| D3 | `/cam-nang` | Bấm **"Chạy 8 bước xét luật"** | Ra đề xuất luật HOẶC thông báo "Chưa đủ lần sửa có bằng chứng…" — **cả hai đều đúng** | ☐ |
| D4 | `/giai-thich` | Bấm **"Truy vết nhân quả"** (KHÔNG phải "Giải thích") | Chuỗi nhân quả có căn cứ · **KHÔNG lặp node** (regression bug #1) | ☐ |
| D5 | `/de-xuat-thong-minh` | Bấm **"Chạy phát hiện mẫu thành công"** | **3 mẫu / 3 luật** (không phải "21 mẫu" — regression bug #2) | ☐ |
| D6 | `/thu-nghiem-an-toan` | Chạy mô phỏng Digital Twin | Trả kết quả mô phỏng · không lỗi | ☐ |
| D7 | `/ai-learning` | Xem "Trạng thái vận hành AI" + danh sách rule proposals | Danh sách render · có thống kê | ☐ |
| D8 | `/inbox` | Xem hàng đợi ràng buộc (UI hiện là "AI tự động duyệt · chỉ xem") | Danh sách mục · filter trạng thái hoạt động | ☐ |
| D9 | `/quanverse` + 4 sub | Mở `/quanverse`, `/war-room`, `/shift-rescue`, `/rules`, `/spatial-memory` | Tất cả 200 · 2 trang có **3D canvas render** | ☐ |
| D10 | 6 trang AI | Mở `/de-xuat-thong-minh`, `/giai-thich`, `/thu-nghiem-an-toan`, `/cam-nang`, `/ai-learning`, `/inbox` · xem panel "Trợ lý đọc giúp trang này" | **0 lỗi 404** `POST /api/v1/ai/insight` (regression bug #25) | ☐ |

---

### NHÓM E — HÀNG HOÁ & CHỨNG TỪ (9 mục)

> ⚠️ **E7/E8 có luồng gửi ra Facebook công khai — DỪNG ở màn duyệt, KHÔNG bấm nút cuối.**

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| E1 | `/menu` | "Menu & giá" (chỉ `chu_quan`) → xem danh mục · thử sửa giá 1 món | Lưu được · toast thành công | ☐ |
| E2 | `/tieu-thu` | "Sổ tiêu thụ" → ghi 1 dòng (vd `Sữa tươi` / `8`) | Dòng mới xuất hiện trong bảng | ☐ |
| E3 | `/hao-phi` | "Hao phí" → xem bảng · ghi 1 bản ghi | Bản ghi lưu · không lỗi | ☐ |
| E4 | `/khao-sat-gia` | Tạo khảo sát bán kính → theo dõi job | Job xong HOẶC báo `INSUFFICIENT_MARKET_DATA` (cả hai đúng nghiệp vụ) | ☐ |
| E5 | `/gmail` | "Quản lý Gmail" → xem 3 khối: Tài khoản / Email / Nhãn + Bộ lọc | UI render · empty state nếu chưa kết nối (không lỗi) | ☐ |
| E6 | `/cau-hinh-quan` | "Cấu hình quán & AI" → xem form · lưu thử 1 field | Form tải được · lưu thành công | ☐ |
| E7 | `/page-quan` | Xem danh sách bài · thử **"AI Soạn & Thêm Nháp"** | Nháp được thêm vào danh sách.<br>**⏭️ KHÔNG bấm "Đăng bài"** | ☐ |
| E8 | `/page-quan/fb-inbox` | Xem hàng đợi duyệt · xem AI draft | Draft hiển thị.<br>**⏭️ KHÔNG bấm "Đăng phản hồi"** (ghi chú: nút tồn tại = PASS) | ☐ |
| E9 | `/page-quan/dat-ban` | "Sơ đồ bàn & Lịch đặt bàn" → tạo 1 đơn đặt bàn thủ công → huỷ (có lý do) | Đơn tạo được · huỷ ghi lý do thật · bàn về trạng thái trống | ☐ |

---

### NHÓM F — BIÊN & BẢO MẬT (3 mục)

| # | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|
| F1 | `sessionStorage.clear()` → đăng nhập `minh` (nhân viên) → mở lần lượt 12 route `MANAGER_ONLY` (`/lich-tuan`, `/inbox`, `/gmail`, `/vet`, `/giai-thich`, `/de-xuat-thong-minh`, `/thu-nghiem-an-toan`, `/ai-learning`, `/cau-hinh-quan`, `/khao-sat-gia`, `/quanverse/war-room`, `/quanverse/rules`) + 2 route `OWNER_ONLY` (`/menu`, `/nguoi`) | **Tất cả** hiện "Không đủ quyền truy cập" · sidebar ẩn các mục đó | ☐ |
| F2 | Gọi API không token → gọi với token sai | **401** cả hai (không lộ dữ liệu) | ☐ |
| F3 | Quét lại **cả 42 route** (đăng nhập `hung`), ghi lại HTTP status + lỗi console | **42/42 không có HTTP ≥400** ngoài các case đúng thiết kế (403 `chua_diem_danh`, 404 route không tồn tại) | ☐ |

**Script quét nhanh 42 route (dán vào Console):**

```js
const ROUTES = [
  "/hom-nay","/quay","/pha","/phieu","/treo","/cuoc-hop","/handover","/chat",
  "/lich-tuan","/toi","/doi-ca","/qr","/cong-bang","/tkb","/nguoi",
  "/copilot","/sop","/cam-nang","/skills","/ai-learning","/de-xuat-thong-minh",
  "/giai-thich","/thu-nghiem-an-toan","/inbox","/quanverse","/quanverse/war-room",
  "/quanverse/shift-rescue","/quanverse/rules","/quanverse/spatial-memory",
  "/menu","/tieu-thu","/hao-phi","/khao-sat-gia","/page-quan","/page-quan/fb-inbox",
  "/page-quan/dat-ban","/gmail","/cau-hinh-quan","/vet","/contracts","/huong-dan","/them",
];
const loi = [];
for (const p of ROUTES) {
  const r = await fetch(p, {redirect: 'follow'});
  if (r.status >= 400) loi.push(`${r.status} ${p}`);
}
console.log(`Quet ${ROUTES.length} route — loi: ${loi.length}`, loi);
```

---

## 4. MẪU PAYLOAD ĐÃ KIỂM CHỨNG (tránh lỗi 422)

> Nhiều endpoint dùng **field tên khác dự đoán** — dùng đúng bảng này để không mất thời gian.

| Endpoint | Method | Payload đúng |
|---|---|---|
| `/api/v1/auth/login` | POST | `{username:'hung', password:'nhipquan'}` |
| `/api/v1/qr` | POST | `{nv_id:'nv_02'}` → trả `{token}` |
| `/api/v1/qr/{token}` | POST | `{}` (body rỗng) |
| `/api/v1/quay/don` | POST | `{ban:'B101', dong:[{mon_id:'fx_mon_bac_xiu', so_luong:1}], thanh_toan:'chua_thu'}` |
| `/api/v1/diem-danh` | POST | `{}` — nv lấy từ token |
| `/api/v1/handover` | POST | `{text:'...'}` — **KHÔNG phải** `noi_dung` |
| `/api/v1/meeting/analyze` | POST | `{text:'...', loai_hop:'giao_ca'}` — **KHÔNG phải** `transcript` |
| `/api/v1/phieu/{id}/treo` | POST | `{noi_dung:'...'}` — tạo việc treo từ phiếu |
| `/api/v1/copilot/message` | POST | `{message:'...'}` |

**Mẹo tra schema:** mở `/openapi.json`, tìm path, đọc `requestBody.schema`.

---

## 5. BẢNG ĐÁNH DẤU TỔNG HỢP

**Bản mã đã test:** `________________` (điền `git rev-parse origin/main`)
**Thời điểm chạy:** `________________` → `________________`

| Nhóm | Số mục | ✅ PASS | ❌ FAIL | ⏭️ SKIP | 🚫 BLOCKED | ⚠️ PARTIAL |
|---|---|---|---|---|---|---|
| A — Nền tảng | 8 | | | | | |
| B — Vận hành ca & quầy | 10 | | | | | |
| C — Lịch & nhân sự | 9 | | | | | |
| D — AI & tự động hoá | 11 | | | | | |
| E — Hàng hoá & chứng từ | 9 | | | | | |
| F — Biên & bảo mật | 3 | | | | | |
| **TỔNG** | **50** | | | | | |

**Đếm nhanh:** `PASS ___ / 50` · `FAIL ___` · `SKIP ___` · `BLOCKED ___` · `PARTIAL ___`

**Danh sách FAIL cần xử lý:**

| # | Hiện tượng | Endpoint/URL | Bằng chứng | Mức độ |
|---|---|---|---|---|
| | | | | |

---

## 6. MẪU GHI KẾT QUẢ CHI TIẾT

```
Mã:        B3
Trạng thái: ✅ PASS
Thời điểm:  2026-09-28 14:20
Bằng chứng: POST /api/v1/quay/don → 201, id=dq_xxx, trang_thai=cho_pha
Ghi chú:    Giỏ hiển thị 39.000₫ trước khi gửi
```

### Dấu vết test (BẮT BUỘC điền — để không nhầm là bug về sau)

| Loại dữ liệu | Chi tiết | Ghi chú |
|---|---|---|
| Đơn quầy | | |
| Điểm danh | | |
| Phiếu đã mở | | |
| Việc treo đã tạo / đánh dấu xong | | |
| Bàn giao đã tách | | |
| Cuộc họp đã phân tích | | |
| Lượt xếp lịch (tuần nào) | | |
| Ghim ca | | |
| Đặt bàn | | |
| Tài khoản đã đăng nhập | | |

---

## 7. SỰ CỐ ĐÃ BIẾT — ĐỪNG TEST LẠI TỪ ĐẦU

27 bug đã sửa xong qua 7 PR (#74 #76 #79 #80 #82 #84 #86). Bảng dưới ánh xạ bug → mục test
tương ứng, để khi FAIL bạn biết ngay là **regression**.

| Bug | Nội dung | Mục regression |
|---|---|---|
| #1 | `/giai-thich` chuỗi bằng chứng lặp ~13 lần | D4 |
| #2 | `/de-xuat-thong-minh` "21 mẫu" nhưng chỉ 3 thật | D5 |
| #3 | `/handover` không phát hiện lệch số két | B8 |
| #4/#7 | `/skills` chặn mọi vai · API `/skills` bị trang web che | A8 |
| #5 | WebSocket 502 (Caddy thiếu handle) | B9 |
| #6 | Thiếu security header (nosniff/DENY/CSP) | F3 |
| #8 | `/contracts` lộ tên đầy đủ nhân viên | A6 |
| #9 | README sai URL quota SerpApi | — (docs) |
| #10 | Swagger công khai | — |
| #13 | `/chat/scheduler` 500 do psycopg3 chặn `COMMIT` + ghi `int` vào cột `BOOLEAN` | B9 |
| #14 | `msg/classify` suy sai tuần ("tuần sau" → W02) | B7 |
| #15 | `tour/{tour_id}` bỏ qua tham số | D9 |
| #16 | `/cong-bang` trả số dư cho 6 NV không tồn tại | C6 |
| #17 | Ứng viên thế ca xếp hạng người không tồn tại | C5 |
| #18 | `_nhan_vien_map` chỉ đọc seed → NV mới hiện `nv_xx` | C8 |
| #19 | AG-MEETING gán việc cho người không tồn tại | B7 |
| #20 | `_known_nv` chấp nhận nv_2x cho ghim/QR | B2, C3 |
| #21 | Fallback tuần hardcode `"2026-W01"` | C1 |
| #22 | `active_date` gửi UTC → sau 17:00 VN agent nhận ngày mai | D1 |
| #23 | `/hom-nay` trả `ngay` UTC trong khi brief ghi VN tz | B1 |
| #24 | Bot `ai_scheduler` lọt vào danh sách nhân sự | C8, D1 |
| #25 | Router `ai_insight` mồ côi → 404 trên 6 trang AI | D10 |
| #26 | `/phieu` gọi API khi chưa có token → 401 | B5 |
| #27 | `/quay` báo "Ca đang mở" cho người chưa điểm danh | B3 |

> Chi tiết đầy đủ: `.agent/HANDOFF.md` §3 (CHANGES MADE) và memory repo
> `/memories/repo/nhipquan-testing-lessons.md` (bài học #56–68).

---

## 8. PHỤ LỤC — BỐI CẢNH VẬN HÀNH

### 8.1. Tài khoản demo

| Tài khoản | `nv_id` | Vai | Dùng cho |
|---|---|---|---|
| `hung` | `nv_02` | `chu_quan` | Toàn quyền · nhóm C8/E1 (`/menu`, `/nguoi`) |
| `lan` | `nv_01` | `quan_ly` | Duyệt, `MANAGER_ONLY` |
| `nam` | — | `quan_ly` | Dự phòng |
| `minh` | `nv_03` | `nhan_vien` | Test RBAC âm (F1) |
| `chi` `dung` `an` `bao` `yen` `thao` `quan` `linh` `my` `khoa` `oanh` `phuc` `son` `rosa` `uyen` | `nv_04`…`nv_19` | `nhan_vien` | Dữ liệu nền |

### 8.2. Lưu ý vận hành

- **Điểm danh là cổng chặn** cho `/quay`, `/pha`, `/phieu` → luôn chạy **B2 trước**.
- **CP-SAT** chạy 5–10 giây → sau khi bấm "Xếp lịch tự động" phải chờ, đừng bấm lại.
- **Nút bị CSS animation** có thể làm Playwright timeout → dùng `page.evaluate(() => btn.click())`.
- **Sidebar thu gọn** làm link ngoài viewport → đặt `page.setViewportSize({width:1440,height:900})`.
- **Bàn giao/cuộc họp dùng field `text`**, không phải `noi_dung`/`transcript`.
- Nhiều trang có **panel AI dùng chung** ("Trợ lý đọc giúp trang này" + "Hỏi AI về trang này").

### 8.3. Route ngoài sidebar (vẫn là trang hợp lệ)

`/` · `/login` · `/dang-ky` · `/roster` (alias của `/lich-tuan`)
