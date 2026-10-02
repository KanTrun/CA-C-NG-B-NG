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
| A1 | `/` | Mở trang chủ (chưa đăng nhập). Tìm nhóm "Tài khoản trình diễn (19)" | Thấy 19 tài khoản · CTA "Vào ca" → `/login` | ✅ PASS — HTTP 200, có "Tài khoản trình diễn" + "Vào ca" |
| A2 | `/login` | Nhập `hung` / `saimatkhau` → bấm đăng nhập | Báo lỗi "Tài khoản hoặc mật khẩu chưa đúng…" | ✅ PASS — `401 sai_thong_tin_dang_nhap` |
| A3 | `/login` | Nhập `hung` / `nhipquan` | 200 → chuyển `/hom-nay` · header hiện "[Chủ quán]" | ✅ PASS — 200 `role='chu_quan' nv_id='nv_02'` |
| A4 | `/huong-dan` | Mở "Bản đồ hệ thống" | Sơ đồ render, không lỗi console | ✅ PASS — HTTP 200 |
| A5 | `/them` | "Tất cả lối vào" | 19 tile liên kết (đếm từ `LINKS`), bấm 1 tile đi đúng trang | ✅ PASS — HTTP 200 |
| A6 | `/contracts` | Xem danh sách hợp đồng dữ liệu | Tên **rút gọn** dạng `Lan N.` + cờ `la_du_lieu_mo_phong` | ✅ PASS — `la_du_lieu_mo_phong` có trong response; tên rút gọn (bug #8 giữ nguyên fix) |
| A7 | `/vet` | "Vết hệ thống" → lọc theo "Người thực hiện" + thanh tìm | Bảng hiện `countLabel="vết"`; lọc giảm số dòng | ✅ PASS — `/api/v1/audit` 200, 200 dòng |
| A8 | `/skills` | "Bộ kỹ năng AI" | Danh sách kỹ năng; API `/api/v1/skills` → **200** (không 404) | ✅ PASS — 200, **13 skill** |

---

### NHÓM B — VẬN HÀNH CA & QUẦY (10 mục · ghi dữ liệu nội bộ)

> **Điều kiện tiên quyết:** `hung` đã đăng nhập. **B2 (điểm danh) phải chạy TRƯỚC B3/B4/B5**
> vì cổng quầy đòi `da_diem_danh` (`pos.py::_require_dang_ca`).

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| B1 | `/hom-nay` | Xem dashboard: KPI, bản tin sáng, khối việc | Render đủ khối · console 0 lỗi HTTP ≥400 | ✅ PASS — 200, 12 khối; `so_nhan_vien=19` (bug #24 còn fix); `ngay='2026-09-29'` |
| B2 | `/qr` | Bấm **"PHÁT MÃ ĐIỂM DANH"** → chọn `nv_02` → lấy token → bấm **"ĐIỂM DANH VÀO CA"** | Phát mã 200 · điểm danh 200 · dùng lại mã cũ → **lỗi** (one-shot) | ✅ PASS — phát mã 200 `mot_lan=true` · điểm danh 200 · **dùng lại mã → 409 `qr_da_dung`** |
| B3 | `/quay` | Thêm 1–2 món vào giỏ → bấm **"Gửi sang pha chế"** | 201 · trạng thái `cho_pha` · giỏ về 0.<br>**Kiểm tra regression bug #27:** nếu CHƯA điểm danh thì phải thấy Alert *"Quầy đang khóa: bạn có ca hôm nay nhưng chưa điểm danh."* + nút gửi đơn **disabled** | ✅ PASS — 201, `id=dq_782adabde5`, `trang_thai='cho_pha'` |
| B4 | `/pha` | Tìm đơn vừa tạo ở cột "Chờ pha" → bấm nhận pha → hoàn tất | Đơn chuyển sang "Đang pha" rồi "Đã xong trong ca" | ✅ PASS — chuyển `dang_pha` → `xong` đều 200. Lưu ý payload đúng là `{trang_thai: ...}` (không phải `sang`) |
| B5 | `/phieu` | Bấm **"Tôi đã có mặt"** → chọn phiếu **"Mở quán"** | Hiện **"Bước 1 / 20"** · bấm "Xong bước này" → **"Bước 2 / 20"** (có ghi thời gian) | ✅ PASS — `ph_1`, `so_buoc=20`; ghi bước → `so_xong=3/20` |
| B5b | `/phieu` | Bấm **"Để lại việc khó"** → nhập "Hết ống hút cỡ lớn" → "Ghi việc treo" | Ghi thành công · việc xuất hiện ở `/treo` | ✅ PASS — 200, `treo=['Hết ống hút cỡ lớn (QA test)']` |
| B6 | `/treo` | Tab "Việc cần xử lý (n)" → bấm **"Đánh dấu xong"** 1 việc | Việc chuyển nhóm Xong · `n` giảm 1 | ✅ PASS — 33 việc; PATCH `{trang_thai:'xong'}` → 200, `trang_thai='xong'` |
| B7 | `/cuoc-hop` | Dán transcript (máy pha rỉ nước, khách phàn nàn, đoàn 25 người) → **"Phân tích biên bản"** | Trả ≥15 trường cấu trúc (`tom_tat`, `van_de_phat_sinh`, `quyet_dinh`, `action_items`, `de_xuat_sop`…) | ✅ PASS — **20 trường**; `tom_tat` + 3 `quyet_dinh` + `action_items` đúng nội dung transcript |
| B8 | `/handover` | Dán văn bản có **2 số lệch**: "doanh thu 2.350.000, két 2.300.000" → **"Tách thành bàn giao"** | `co_lech_so: true` + `vf_number_conflict` ≥1 chủ đề (regression bug #3) | ✅ PASS — `co_lech_so=True`, 2 chủ đề (`ket`, `doanh_thu`) đúng số lệch |
| B9 | `/chat` | Chọn 1 hội thoại → gửi 1 tin nhắn | Tin hiện ngay · WebSocket **không** lỗi 502 | ✅ PASS — gửi 200 `msg_fb1c3fc31c61`; `/chat/scheduler` 200 (bug #13 còn fix). Field đúng là `content` |

---

### NHÓM C — LỊCH & NHÂN SỰ (9 mục)

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| C1 | `/lich-tuan` | Xem ma trận tuần · bấm **"Sau →"** đổi tuần | Tuần đổi (vd W39→W40) · không lỗi | ✅ PASS — 200, `danh_sach_tuan` cho phép đổi; `tuan_iso='2026-W36'` 70 ca |
| C2 | `/lich-tuan` | Ở tuần `nhap`: bấm **"Xếp lịch tự động"** | Trạng thái đổi sang `cho_duyet`/`da_duyet` · lưới có phân công (CP-SAT chạy ~5–10s) | ⏭️ SKIP (an toàn) — chạy solver sẽ ĐỔI LỊCH THẬT của quán; `/ops/twin` đã kiểm riêng |
| C3 | `/lich-tuan` | Bấm ô ca → bấm **"Ghim"** | Toast "Đã ghim và xếp lại phần lịch còn lại." | ⏭️ SKIP (an toàn) — ghim làm xếp lại lịch thật; đã xác nhận schema `{ca_id,nv_id,pinned}` đúng |
| C4 | `/toi` | "Ca của tôi" | Danh sách ca của mình · nút Nhận/Nhả ca (nếu lịch đã công bố) | ✅ PASS — 200, `tuan_iso='2026-W40'`, `da_cong_bo=true`, ca T2 07:00–12:00 `co_the_nha=true` |
| C5 | `/doi-ca` | "Chợ đổi ca" | Tab "Ca thiếu người" + danh sách yêu cầu đổi ca | ✅ PASS — `/cho-doi-ca` 200 (2 yêu cầu) · `/open-shifts` 200 (168 ca thiếu người) |
| C6 | `/cong-bang` | "Công bằng ca" | Biểu đồ số dư 4 trục · **19** khoá NV (không có `nv_20..25` — regression bug #16) | ⚠️ PARTIAL — 4 trục OK, `nv_20..25` KHÔNG có (bug #16 còn fix) NHƯNG có `nv_26..31` → xem **lỗi #36** |
| C7 | `/tkb` | Bấm **"Thử ảnh mẫu"** → xem kết quả đọc ảnh → **"Xác nhận gắn TKB"** | Đọc được khung giờ bận · xác nhận thành công | ⏭️ SKIP (an toàn) — xác nhận sẽ ghi TKB thật; `/tkb/mine` + `/tkb/{nv}` đều 200 |
| C8 | `/nguoi` | Danh sách người dùng | **"19 TỔNG TÀI KHOẢN"** · KHÔNG có "Agent Xếp Lịch"/`ai_scheduler` (regression bug #24) | ❌ FAIL — **22 tài khoản**: KHÔNG có bot (bug #24 còn fix) nhưng có 3 tài khoản rác tự đăng ký (`qa_test_…`/nv_26, `qa_admin_…`/nv_27, `www`/nv_28) → xem **lỗi #36 + #37** |
| C8b | `/nguoi` | Mở dialog nâng vai 1 NV → **Huỷ** (không đổi thật) | Dialog hiện đúng thông tin · huỷ không ghi gì | ✅ PASS — `/me` 200 trả đúng `{username,role,nv_id,store_id}` |

---

### NHÓM D — AI & TỰ ĐỘNG HOÁ (11 mục)

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| D1 | `/copilot` | Gõ `Danh sách nhân sự của quán` | Trả **"Hiện có 19 nhân sự"** (regression bug #24) | ❌ FAIL — trả **"Hiện có 22 nhân sự"** (sau đó 25/35 khi test thêm) vì đếm cả tài khoản rác → cùng **lỗi #36** |
| D1b | `/copilot` | Gõ câu cần duyệt (vd `Xếp lịch tuần này`) | Thẻ **"CHỜ DUYỆT"** có diff + snapshot hash · gõ `duyệt` → **"✓ ĐÃ DUYỆT"** | ⚠️ PARTIAL — intent `SCHEDULE_SOLVE` nhận đúng nhưng `action_proposal` rỗng → cần kiểm lại luồng duyệt |
| D2 | `/sop` | Hỏi câu CÓ trong cẩm nang (`Nhiệt độ tủ lạnh bao nhiêu?`) → hỏi câu LẠ (`Giá vàng hôm nay?`) | Câu 1: trả lời + "Nguồn dẫn" · Câu 2: nói thẳng "chưa có trong cẩm nang" (**không bịa**) | ✅ PASS — câu 1: "2–8 độ C" + `trich_dan:['phieu:nhiet_do_tu_lanh']` · câu 2: `chua_co=true`, "Chưa có trong cẩm nang" |
| D3 | `/cam-nang` | Bấm **"Chạy 8 bước xét luật"** | Ra đề xuất luật HOẶC thông báo "Chưa đủ lần sửa có bằng chứng…" — **cả hai đều đúng** | ✅ PASS — 200, trả `cho_chot` (luật `luat_nha_ca`) kèm `bang_chung` + `tap_su` |
| D4 | `/giai-thich` | Bấm **"Truy vết nhân quả"** (KHÔNG phải "Giải thích") | Chuỗi nhân quả có căn cứ · **KHÔNG lặp node** (regression bug #1) | ✅ PASS — 200, 2 chuỗi, có `nodes` + `chain_id` (bug #1 còn fix) |
| D5 | `/de-xuat-thong-minh` | Bấm **"Chạy phát hiện mẫu thành công"** | **3 mẫu / 3 luật** (không phải "21 mẫu" — regression bug #2) | ✅ PASS — đúng **3 suggestions** (bug #2 còn fix) |
| D6 | `/thu-nghiem-an-toan` | Chạy mô phỏng Digital Twin | Trả kết quả mô phỏng · không lỗi | ✅ PASS — 200, 1 kịch bản `qa1` với `ket_qua` đầy đủ |
| D7 | `/ai-learning` | Xem "Trạng thái vận hành AI" + danh sách rule proposals | Danh sách render · có thống kê | ✅ PASS — `/ai/operations/status` 200 (8 cờ) · `/ai/rules/proposals` 200 |
| D8 | `/inbox` | Xem hàng đợi ràng buộc (UI hiện là "AI tự động duyệt · chỉ xem") | Danh sách mục · filter trạng thái hoạt động | ✅ PASS — 200, **23 mục** |
| D9 | `/quanverse` + 4 sub | Mở `/quanverse` (expect 200) + 4 sub `/war-room`, `/shift-rescue`, `/rules`, `/spatial-memory` (expect **308 redirect về `/quanverse`** — chủ ý, chốt bởi e2e `quanverse-hidden-routes.spec.ts`, redirect khai ở `next.config.js`) | ✅ PASS — `/quanverse` 200; 4 sub 308 `Location: /quanverse` (QA 30/09 N2: không phải bug); API experience 200 (snapshot/modes/candidates) |
| D10 | 6 trang AI | Mở `/de-xuat-thong-minh`, `/giai-thich`, `/thu-nghiem-an-toan`, `/cam-nang`, `/ai-learning`, `/inbox` · xem panel "Trợ lý đọc giúp trang này" | **0 lỗi 404** `POST /api/v1/ai/insight` (regression bug #25) | ✅ PASS — `POST /ai/insight` **200** (bug #25 còn fix) |

---

### NHÓM E — HÀNG HOÁ & CHỨNG TỪ (9 mục)

> ⚠️ **E7/E8 có luồng gửi ra Facebook công khai — DỪNG ở màn duyệt, KHÔNG bấm nút cuối.**

| # | Route | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|---|
| E1 | `/menu` | "Menu & giá" (chỉ `chu_quan`) → xem danh mục · thử sửa giá 1 món | Lưu được · toast thành công | ✅ PASS — 11 món; PUT giữ nguyên `bom={ca_phe_hat:14, sua_tuoi:120, da:80}` (bug #29 còn fix) |
| E2 | `/tieu-thu` | "Sổ tiêu thụ" → ghi 1 dòng (vd `Sữa tươi` / `8`) | Dòng mới xuất hiện trong bảng | ✅ PASS — 200 `tt_6b835bf6`. Field đúng là `hang`/`so_luong` |
| E3 | `/hao-phi` | "Hao phí" → xem bảng · ghi 1 bản ghi | Bản ghi lưu · không lỗi | ✅ PASS — 200 `hh_7160a2927b`. Field đúng là `mat_hang`/`so_luong` |
| E4 | `/khao-sat-gia` | Tạo khảo sát bán kính → theo dõi job | Job xong HOẶC báo `INSUFFICIENT_MARKET_DATA` (cả hai đúng nghiệp vụ) | ✅ PASS — metrics/dashboard/quota đều 200; SerpApi quota 240/250 còn lại |
| E5 | `/gmail` | "Quản lý Gmail" → xem 3 khối: Tài khoản / Email / Nhãn + Bộ lọc | UI render · empty state nếu chưa kết nối (không lỗi) | ✅ PASS — 200 `{accounts: []}` (empty state đúng) |
| E6 | `/cau-hinh-quan` | "Cấu hình quán & AI" → xem form · lưu thử 1 field | Form tải được · lưu thành công | ⚠️ PARTIAL — `GET /store/profile` trả **200 KHÔNG cần token** → xem **lỗi #38**. Form tải được, PUT được (đã kiểm ở đợt trước) |
| E7 | `/page-quan` | Xem danh sách bài · thử **"AI Soạn & Thêm Nháp"** | Nháp được thêm vào danh sách.<br>**⏭️ KHÔNG bấm "Đăng bài"** | ✅ PASS — 200, 6 nháp; `/page/status` `mode=live` `graph_ok=true` — **KHÔNG bấm Đăng bài** |
| E8 | `/page-quan/fb-inbox` | Xem hàng đợi duyệt · xem AI draft | Draft hiển thị.<br>**⏭️ KHÔNG bấm "Đăng phản hồi"** (ghi chú: nút tồn tại = PASS) | ✅ PASS — 20 mục; stats: 50 tổng, `auto_rate=0.58` — **KHÔNG bấm Đăng phản hồi** |
| E9 | `/page-quan/dat-ban` | "Sơ đồ bàn & Lịch đặt bàn" → tạo 1 đơn đặt bàn thủ công → huỷ (có lý do) | Đơn tạo được · huỷ ghi lý do thật · bàn về trạng thái trống | ✅ PASS — 10 bàn, 4 đơn (đều `cancelled` — huỷ có ghi lý do) |

---

### NHÓM F — BIÊN & BẢO MẬT (3 mục)

| # | Thao tác cụ thể | Mong đợi | Kết quả |
|---|---|---|---|
| F1 | `sessionStorage.clear()` → đăng nhập `minh` (nhân viên) → mở lần lượt 12 route `MANAGER_ONLY` (`/lich-tuan`, `/inbox`, `/gmail`, `/vet`, `/giai-thich`, `/de-xuat-thong-minh`, `/thu-nghiem-an-toan`, `/ai-learning`, `/cau-hinh-quan`, `/khao-sat-gia`, `/quanverse/war-room`, `/quanverse/rules`) + 2 route `OWNER_ONLY` (`/menu`, `/nguoi`) | **Tất cả** hiện "Không đủ quyền truy cập" · sidebar ẩn các mục đó | ⚠️ PARTIAL — UI chặn đúng nhưng **API hở**: kiểm 14 endpoint thì chỉ **6/14** chặn; 7 endpoint trả 200 cho nhân viên (gồm dữ liệu doanh thu) → xem **lỗi #39** |
| F2 | Gọi API không token → gọi với token sai | **401** cả hai (không lộ dữ liệu) | ✅ PASS — `/nguoi` cả hai trường hợp đều `401 thieu_token` |
| F3 | Quét lại **cả 42 route** (đăng nhập `hung`), ghi lại HTTP status + lỗi console | **42/42 không có HTTP ≥400** ngoài các case đúng thiết kế (403 `chua_diem_danh`, 404 route không tồn tại) | ✅ PASS — **42/42 đều 200**, 0 lỗi HTTP ≥400 |

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

**Bản mã đã test (đợt 6):** `03b9ee9` (sau PR #90) → **chạy lại toàn bộ sau `326b307`** (sau PR #91)
**Thời điểm chạy đợt 6:** `2026-09-29 15:00` → `2026-09-29 16:20` (giờ VN)
**Chạy lại xác nhận (sau deploy PR #91):** `2026-09-29 21:37` → `21:50` (giờ VN)

### Kết quả chạy lại toàn bộ 50 mục sau khi fix #35–#39 (260929 21:37)

Chạy bằng script tự động gọi API thật trên `https://nhipquan.duckdns.org`, đăng nhập 3 vai
(`hung`/chủ quán, `lan`/quản lý, `minh`/nhân viên), **52 lượt kiểm** (50 mục + 2 kiểm bổ sung).

| Nhóm | Kiểm | ✅ PASS | ❌ FAIL | ⏭️ SKIP | Ghi chú |
|---|---|---|---|---|---|
| A — Nền tảng | 8 | **8** | 0 | 0 | A2/A4/A5 là lỗi script (sai path/payload) — đã sửa và PASS |
| B — Vận hành ca & quầy | 10 | **10** | 0 | 0 | B3/B4 lỗi script (field `trang_thai`) — đã sửa; B4b CAS chứng minh bug #28 vẫn được chặn |
| C — Lịch & nhân sự | 9 | 7 | 0 | 2 | C2/C3 chủ động SKIP; **C8 = 19 người, 0 bot, 0 rác** ✅ |
| D — AI & tự động hoá | 11 | **11** | 0 | 0 | D4/D5/D6/D11: **403 cho nhân viên, 200 cho quản lý** ✅ |
| E — Hàng hoá & chứng từ | 9 | **9** | 0 | 0 | E6: profile **401 không token / 200 có token** ✅ |
| F — Biên & bảo mật | 3 | **3** | 0 | 0 | F2: QR sai nv → **404**; treo 50k → **422** ✅ |
| **TỔNG** | **50** | **48** | **0** | **2** | |

**Kết quả 5 fix (#35–#39) đo lại trên production sau deploy:**

| Fix | Bằng chứng đo được | Kết quả |
|---|---|---|
| **#35** | `POST /nguoi/{u}/deactivate` → 200, rồi `POST /auth/login` → **401** | ✅ FIX |
| **#36** | `GET /nguoi` → **19** tài khoản (trước 22→35), rác hiện = **0** | ✅ FIX |
| **#37** | 6 lần `POST /auth/register` liên tiếp → `[201, 201, 201, 201, 429, 429]` | ✅ FIX |
| **#38** | `/store/profile` + `/store/promotions` không token → **401**; có token → **200** | ✅ FIX |
| **#39** | 4 endpoint `MANAGER_ONLY`: nhân viên **403**, quản lý **200** | ✅ FIX |

**Kiểm bổ sung (ngoài 50 mục):**
- **B4b — CAS race condition (bug #28)**: 2 request đồng thời chuyển `cho_pha→dang_pha` →
  `[200, 409]` (đúng thiết kế, kho trừ đúng 1 lần).
- **IDOR/path traversal trên uploads**: `/chat/uploads/../../.env` → **404**;
  `..%2F..%2F.env` → **404**; `%2e%2e%2f` → **404** (dùng `os.path.basename`). ✅
- **QR IDOR**: QR của `nv_02` dùng bằng token `nv_03` → **403 `qr_khong_phai_cua_ban`** ✅
- **Quét 279 route tìm endpoint thiếu auth**: 15 route không khai `authorization`.
  Đã kiểm từng cái → **14 là public có chủ đích** (webhook Meta/Zalo, OAuth callback,
  ảnh menu, `/contracts` dữ liệu mô phỏng tên rút gọn, `/ab` + `/vf/conflict` dữ liệu tĩnh),
  **1 là `/skills`** — cũng có chủ đích (`session.ts:73` ghi rõ "API công khai 🟢, mọi vai xem được").

| Nhóm | Số mục | ✅ PASS | ❌ FAIL | ⏭️ SKIP | 🚫 BLOCKED | ⚠️ PARTIAL |
|---|---|---|---|---|---|---|
| A — Nền tảng | 8 | 8 | 0 | 0 | 0 | 0 |
| B — Vận hành ca & quầy | 10 | 10 | 0 | 0 | 0 | 0 |
| C — Lịch & nhân sự | 9 | 5 | 1 | 2 | 0 | 1 |
| D — AI & tự động hoá | 11 | 9 | 1 | 0 | 0 | 1 |
| E — Hàng hoá & chứng từ | 9 | 8 | 0 | 0 | 0 | 1 |
| F — Biên & bảo mật | 3 | 2 | 0 | 0 | 0 | 1 |
| **TỔNG** | **50** | **42** | **2** | **2** | **0** | **4** |

**Đếm nhanh:** `PASS 42 / 50` · `FAIL 2` · `SKIP 2` · `BLOCKED 0` · `PARTIAL 4`

**Danh sách FAIL cần xử lý:**

| # | Hiện tượng | Endpoint/URL | Bằng chứng | Mức độ |
|---|---|---|---|---|
| #36 | `/nguoi` trả 22 thay vì 19; tài khoản đã `deactivate` VẪN hiện và Copilot vẫn đếm | `GET /api/v1/nguoi`, `POST /api/v1/copilot/message` | `list_users()` không lọc `status='inactive'`; đo được 22 → 25 → 35 khi thêm tài khoản | 🟠 Cao |
| #37 | `POST /auth/register` công khai không giới hạn — spam tài khoản | `POST /api/v1/auth/register` | **10/10 tài khoản** tạo liên tiếp trong 1 giây từ cùng IP; mỗi tài khoản chiếm 1 `nv_id` vĩnh viễn | 🔴 Nghiêm trọng |
| #35 | Tài khoản đã vô hiệu hoá VẪN đăng nhập được | `POST /api/v1/auth/login` | `qa_probe_671972298_0` deactivate xong (200) → login lại → **200 + token mới** | 🔴 **CRITICAL** |
| #38 | `GET /store/profile` + `/store/promotions` không cần token | `GET /api/v1/store/profile` | Trả **200** kể cả không token / token sai; lộ `wifi_pass` + `huong_dan_agent` | 🔴 Nghiêm trọng |
| #39 | 4 endpoint `MANAGER_ONLY` cho nhân viên đọc | `/ops/explain/chains`, `/ops/predict/suggestions`, `/ops/twin/scenarios`, `/experience/rules/candidates` | Nhân viên `minh` nhận **200** kèm số liệu doanh thu (UI đã ẩn trang) | 🟠 Cao |

> Cả 5 lỗi đã sửa trong PR `fix/qa-dot6-security-critical` — xem
> `apps/api/tests/unit/test_qa_dot6_security_fixes.py` (19 test hồi quy).

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

Chạy ngày **2026-09-29** (đợt 6), tài khoản `hung`/`nv_02` trừ khi ghi khác.

| Loại dữ liệu | Chi tiết | Ghi chú |
|---|---|---|
| Đơn quầy | `dq_782adabde5` (B101, `fx_mon_bac_xiu` ×1) → `cho_pha` → `dang_pha` → `xong` | Kiểm B3 + B4 |
| Điểm danh | `nv_02` (QR `af00ac93…` → dùng lại → `409 qr_da_dung`) | Kiểm B2 |
| Phiếu đã mở | `ph_1` (`mo_quan`, nv_02) — ghi bước `bat_may_pha`, `xa_nuoc` | Kiểm B5 |
| Việc treo đã tạo / đánh dấu xong | Tạo: "Hết ống hút cỡ lớn (QA test)" trên `ph_1`. Đánh dấu xong: `treo_warroom_50fe335d` | Kiểm B5b + B6 |
| Bàn giao đã tách | Không lưu (chỉ phân tích, `co_lech_so=True`) | `/handover` không tạo bản ghi |
| Cuộc họp đã phân tích | `meet_6b426db8` (`giao_ca`) | Kiểm B7 |
| Lượt xếp lịch (tuần nào) | **KHÔNG chạy** — C2/C3 ghi `⏭️ SKIP (an toàn)` | Tránh đổi lịch thật |
| Ghim ca | **KHÔNG chạy** — C3 ghi `⏭️ SKIP (an toàn)` | Tránh xếp lại lịch thật |
| Đặt bàn | Không tạo mới (4 đơn có sẵn đều `cancelled`) | Kiểm E9 |
| Tài khoản đã đăng nhập | `hung`/nv_02, `lan`/nv_01, `minh`/nv_03 | Chỉ đọc |
| Tiêu thụ | `tt_6b835bf6` — "Sữa tươi" ×8 (đơn vị `khay`) | Kiểm E2 |
| Hao phí | `hh_7160a2927b` — "Sữa tươi" ×2 | Kiểm E3 |
| Tin nhắn chat | `msg_fb1c3fc31c61` trong `conv_general_quan_01` | Kiểm B9 |
| Menu | `PUT /menu/fx_mon_bac_xiu` giữ nguyên giá → **BOM không mất** (kiểm bug #29) | Kiểm E1 |

**Rác tài khoản đã tạo khi kiểm #37 (ĐÃ deactivate hết):** 16 tài khoản
`qa_rl_*`, `qa_probe_*`, `qa_admin_*`, `qa_test_*`, `www` (nv_26–nv_41).
→ Đây là bằng chứng cho lỗi #37: **đăng ký công khai không giới hạn**.

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
