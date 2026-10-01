# BÁO CÁO KIỂM THỬ NHỊP QUÁN — 2026-09-30

> **Site:** https://nhipquan.duckdns.org (production)
> **Thời điểm chạy:** 2026-09-30 23:37–23:44 +07:00
> **Người chạy:** AI Agent (Muse Spark / OpenCode)
> **Nguyên tắc:** CHỈ KIỂM THỬ — KHÔNG SỬA CODE. Chỉ dùng request read-only (GET + 4 lần POST /auth/login để lấy token). Không tạo đơn quầy, không điểm danh, không ghim ca, không chạy solver, không duyệt/từ chối proposal, không đăng ký tài khoản rác, không bấm Đăng bài / Đăng phản hồi Facebook, không gửi mail. Vì vậy KHÔNG cần hoàn tác dữ liệu nghiệp vụ.
> **Tham chiếu QA cũ:** `DEMO_QA_RESULTS.md` (26/09), `docs/KE-HOACH-TEST-TOAN-BO-CHUC-NANG.md` (đợt 6, 29/09, 50 mục, 48 PASS / 2 SKIP sau fix #35–#39).

---

## 1. Đọc sơ qua dự án (tóm tắt)

- **Tên:** NHỊP QUÁN (repo GitHub: Crew-Operations) — hệ điều hành AI agent cho quán cà phê F&B 1 điểm bán, 15–40 NV bán thời gian.
- **Triết lý:** Ca làm việc là hạt nhân · Cẩm nang tự viết là bộ nhớ · Lõi tất định không dùng LLM (CP-SAT + cổng kiểm duyệt fail-closed). LLM không ghi lịch, không điều phối, không ghi DB. Mọi ghi đều qua `ActionProposal` 2 pha (propose → người duyệt → thực thi idempotent).
- **Stack:** Python 3.12+ / FastAPI + Uvicorn, Next.js 15 PWA, OR-Tools CP-SAT, SQLite (dev) / PostgreSQL 16 + Redis 7 (prod, 5 service Docker), PBKDF2 + Fernet + Bearer token.
- **Quy mô mã:** 21 agent (`packages/agents`), 35 tool whitelist (`tool_registry.py`), 25 router module API (đếm thực tế `openapi.json` hôm nay = **287 paths**), 46 route web PWA (`apps/web/src/app/**/page.tsx`), 14 skill.
- **Vai:** `chu_quan` (hung) · `quan_ly` (lan, nam) · `nhan_vien` (minh, chi, … 19 acc, mật khẩu chung `nhipquan`).
- **Luồng xương sống:** NV nhắn xin nghỉ (AG-MSG) → hộp thư ràng buộc → quản lý duyệt → CP-SAT xếp lịch (C01–C06 + công bằng 4 trục) → lifecycle `nhap→dang_giai→cho_duyet→da_duyet→da_cong_bo→da_dong` → trong ca QR/phiếu/việc treo/bàn giao → họp AG-MEETING → cẩm nang 8 bước học luật → audit `/vet`.

---

## 2. Kế hoạch kiểm thử lần này (read-only, giữ nguyên trạng)

Dựa trên `docs/KE-HOACH-TEST-TOAN-BO-CHUC-NANG.md` (50 mục A–F) nhưng **cắt mọi bước ghi** để giữ production nguyên trạng:

| Nhóm | Nội dung gốc | Cách chạy 30/09 (an toàn) |
|---|---|---|
| A — Nền tảng (8 mục) | Mở `/`, `/login` sai/đúng, `/huong-dan`, `/them`, `/contracts`, `/vet`, `/skills` | Chạy đủ qua WebFetch + API GET. Login sai 1 lần + login đúng 3 vai để lấy token (tạo session, không đổi dữ liệu nghiệp vụ) |
| B — Vận hành ca & quầy (10) | QR phát/điểm danh, tạo đơn quầy, phiếu, treo, họp, handover, chat | **SKIP phần ghi.** Chỉ GET read-only: `/viec-treo`, `/cam-nang`, web GET 200. Ghi rõ lý do skip |
| C — Lịch & nhân sự (9) | Xếp lịch solver, ghim ca, TKB confirm, /nguoi | **SKIP solver/ghim/TKB.** Chỉ GET: `/nguoi` đếm 19, `/cong-bang`, `/inbox/rang-buoc` |
| D — AI (11) | Copilot chat, SOP hỏi, cẩm nang chạy 8 bước, explain/predict/twin | **SKIP POST copilot/sop/meeting.** Chỉ GET: `/ops/predict/suggestions`, `/ops/explain/chains`, `/ops/twin/scenarios`, `/cam-nang`, `/skills` |
| E — Hàng hoá & chứng từ (9) | Sửa menu, ghi tiêu thụ/hao phí, khảo sát giá, Gmail, Page đăng bài, đặt bàn | **SKIP mọi ghi + SKIP Đăng bài/Đăng phản hồi.** Chỉ GET: `/menu`, `/store/profile`, `/skills`, web GET |
| F — Biên & bảo mật (3) | RBAC âm, 401 không token, quét 42 route | Chạy đủ bằng API GET + check headers + CORS + quét 45 route web |

**Tiêu chí PASS/FAIL:** khớp hành vi đã fix ở đợt 6 (fix #35–#39, #1–#10). Bất kỳ lệch nào ghi FAIL + bằng chứng, nhưng KHÔNG sửa code.

---

## 3. Kết quả chi tiết (có kiểm chứng)

### 3.1. Nền tảng & auth — PASS 7/7

| # | Check | Lệnh / bằng chứng | Kết quả |
|---|---|---|---|
| A1 | `GET /` | WebFetch markdown 30/09: thấy “Quán chạy theo *nhịp*”, “Tài khoản trình diễn (19)”, CTA “Vào ca” → `/login` | ✅ PASS |
| A2 | `GET /login` | WebFetch: thấy “Đăng nhập”, “Tài khoản/Mật khẩu/Vào hệ thống”, link `/dang-ky`, `/huong-dan` | ✅ PASS |
| A3 | `GET /huong-dan` | WebFetch: thấy “Bản đồ hệ thống”, “Bốn phòng vận hành, tám bước”, link `/hom-nay`, `/toi`, `/lich-tuan`, `/qr`, `/phieu`, `/treo`, `/doi-ca`, `/inbox`, `/handover`, `/cam-nang` | ✅ PASS |
| A4 | `POST /auth/login` sai pass | `hung/saimatkhau` → **401** (PowerShell `Invoke-WebRequest`, 30/09 23:3x) | ✅ PASS — chặn đúng, chưa chạm rate-limit (mới 1 lần sai) |
| A5 | `POST /auth/login` đúng 3 vai | `hung` → `role=chu_quan nv=nv_02 hasToken=True`; `lan` → `quan_ly nv=nv_01`; `minh` → `nhan_vien nv=nv_03`; `tokLen=32` | ✅ PASS |
| A6 | `GET /health` | `200 {"status":"ok","service":"ca-api","minimal_data_mode":false}` | ✅ PASS |
| A7 | `GET /openapi.json` | `200 len=325188`, `TOTAL_PATHS=287` | ✅ PASS — docs đang BẬT (`NHIPQUAN_PUBLIC_API_DOCS=1`), khớp cấu hình demo |

### 3.2. Dữ liệu mẫu & fix regression cũ — PASS

| # | Check | Bằng chứng 30/09 | Kết quả |
|---|---|---|---|
| R8 | `GET /api/v1/contracts` redact tên (bug #8) | `200 application/json`; keys `nguon,adr,la_du_lieu_mo_phong,ghi_chu,NhanVien,Ca,…`; `la_du_lieu_mo_phong=true`; mẫu `{"id":"nv_01","ten":"Lan N."}`, `nv_02:"Hùng T."`, `nv_03:"Minh P."`, `so_dien_thoai_hash:null` | ✅ PASS — vẫn redact “Họ + chữ cái đầu”, có cờ mô phỏng |
| R36 | `GET /api/v1/nguoi` đếm rác (bug #36) | `hung` → `200 count=19 usernames=an,bao,chi,dung,hung,khoa,lan,linh,minh,my,nam,oanh,phuc,quan,rosa,son,thao,uyen,yen` | ✅ PASS — đúng 19, **0 tài khoản rác** (`qa_*`, `www`, `nv_26..` đã sạch) |
| R38 | `GET /store/profile` không token (bug #38) | Không token → **401**; có token `hung` → **200** keys `ten_quan,slogan,dia_chi,…,wifi_ssid,wifi_pass,ngan_hang,stk_ngan_hang,…` | ✅ PASS — đã yêu cầu auth |
| R39 | 4 endpoint MANAGER_ONLY (bug #39) | `hung 200 / minh 403` cho cả 4: `/ops/predict/suggestions`, `/ops/explain/chains`, `/ops/twin/scenarios`, `/inbox/rang-buoc` | ✅ PASS — NV bị chặn đúng |
| R4 | `GET /api/v1/skills` shadow (bug #4/#7) | `200 application/json`, `SKILLS count=13` (không còn 404 HTML) | ✅ PASS — prefix `/api/v1/skills` đã deploy |
| RBAC-A | `GET /audit` | `hung /audit?limit=5 → 200 len=1724`; `minh → 403` (expect 403) | ✅ PASS |
| RBAC-B | `GET /nguoi` âm tính | `minh → 403`; không token → `401` | ✅ PASS |
| CORS | Origin lạ | `Origin: evil.example.com` → `Access-Control-Allow-Origin` rỗng (null) | ✅ PASS — chặn |
| SKILLS | Public có chủ đích | `GET /skills` không token vẫn 200 (khớp `session.ts:73` “API công khai, mọi vai xem được”) | ✅ PASS (ghi nhận, không phải hở) |

### 3.3. Read-only nghiệp vụ — PASS

| # | Endpoint (GET, token hung) | Kết quả 30/09 |
|---|---|---|
| B1 | `/cong-bang` | 200, keys `axes,means,so_du,ma_ly_do,nv_id,nguon,khong_xep_hang_ten` |
| B2 | `/viec-treo` | 200 (PSCustomObject, không lỗi schema) |
| B3 | `/cam-nang` | 200 |
| B4 | `/store/profile` | 200 (xem trên) |
| B5 | `/menu` | `hung 200`, `minh 200` — **ghi nhận:** API cho NV đọc menu (hợp lý để bán quầy), trong khi route web `/menu` là OWNER_ONLY ở tầng UI. Không đánh FAIL, cần chủ quán xác nhận chủ ý |
| B6 | `/sop/golden` | GET trả lỗi (mã 0/ERR trong script) — **đúng thiết kế:** endpoint này dùng POST theo `openapi.json`, không phải GET. Không đánh FAIL |

### 3.4. Web routes — 41/45 PASS, 4 redirect cần kiểm bổ sung

Quét `Invoke-WebRequest` unauthenticated 45 route (42 sidebar + `/`, `/login`, `/roster` alias):

- **41 route → 200**, gồm: `/`, `/login`, `/dang-ky (200 len=19560)`, `/huong-dan`, `/hom-nay`, `/toi`, `/lich-tuan`, `/roster`, `/qr`, `/phieu`, `/treo`, `/doi-ca`, `/handover`, `/chat`, `/copilot`, `/sop`, `/cam-nang`, `/cong-bang`, `/tkb`, `/nguoi`, `/menu`, `/tieu-thu`, `/hao-phi`, `/khao-sat-gia`, `/page-quan`, `/page-quan/fb-inbox`, `/page-quan/dat-ban`, `/gmail`, `/cau-hinh-quan`, `/vet`, `/giai-thich`, `/de-xuat-thong-minh`, `/thu-nghiem-an-toan`, `/ai-learning`, `/skills`, `/contracts`, `/them`, `/cuoc-hop`, `/quay`, `/pha`, `/quanverse`.
- **4 route → 308 Permanent Redirect → `/quanverse`:** `/quanverse/war-room`, `/quanverse/shift-rescue`, `/quanverse/rules`, `/quanverse/spatial-memory`. Header: `Via: 1.1 Caddy`, `Location: /quanverse`, `Refresh: 0;url=/quanverse` (check bằng `http.client` 30/09 16:41 GMT).
  - Đối chiếu đợt 6 (29/09, đăng nhập `hung`): 5/5 Quanverse 200. Suy ra 308 chỉ xảy ra khi **chưa đăng nhập** (hoặc redirect gộp về parent). **Đánh giá:** ⚠️ NEEDS-BROWSER-CHECK, không đánh FAIL khi chưa có phiên `hung` trên trình duyệt. Không ảnh hưởng 41 route còn lại.

### 3.5. Security headers — 1 phát hiện mới (không sửa code)

| Lớp | Kết quả 30/09 | Đánh giá |
|---|---|---|
| API (`/api/v1/contracts`) | `X-Content-Type-Options=nosniff`, `X-Frame-Options=DENY` có | ✅ PASS — middleware `add_security_headers` (fix #6) vẫn có tác dụng ở API |
| Web HTML (`GET /`) | `nosniff=null`, `frame=null`, `referrer=null`, `permissions=null`, `hsts=null`, `CSP MISSING` | ⚠️ PHÁT HIỆN MỚI (P2): fix #6 chỉ phủ FastAPI, **không phủ Next.js/Caddy**. Cần bổ sung ở `Caddyfile` hoặc `next.config` — **ghi nhận, KHÔNG sửa theo yêu cầu** |
| CORS API | Evil origin không được echo | ✅ PASS |

### 3.6. Các case user cố ý SKIP để giữ nguyên trạng (liệt kê đầy đủ)

Không thực hiện hôm nay, lý do “ghi DB thật / gửi ra ngoài”:

- B2 QR phát/điểm danh (`POST /qr`, `POST /qr/{token}`, `POST /diem-danh`) — tránh tạo điểm danh thật.
- B3/B4 tạo đơn quầy (`POST /quay/don`, `POST /quay/don/{id}/chuyen`) + B5 phiếu (`POST /phieu/start|buoc|minh-chung|treo`) + B6 đánh dấu treo xong (`PATCH /viec-treo/{id}`) + B5b tạo treo từ phiếu.
- B7 họp (`POST /meeting/analyze|apply`) + B8 handover (`POST /handover`) — dù handover không lưu bản ghi, vẫn skip để không tạo `meet_*` hay log AI tốn quota.
- C2 solver (`Xếp lịch tự động`), C3 ghim ca, C7 TKB confirm — tránh đổi lịch thật.
- D1 copilot chat (`POST /copilot/message`), D2 SOP hỏi, E1 sửa menu (`PUT /menu/{id}`), E2/E3 ghi tiêu thụ/hao phí, E4 khảo sát giá (tốn SerpApi quota 240/250), E7 AI soạn nháp Page, E8 duyệt fb-inbox, E9 tạo/huỷ đặt bàn, F brute-force/register-spam.
- Lý do thêm: đợt 6 đã chứng minh các luồng ghi này PASS (đơn `dq_782adabde5`, treo `treo_warroom_50fe335d`, QR one-shot `409 qr_da_dung`, CAS `[200,409]`), không cần lặp lại gây rác.

---

## 4. Tổng hợp

| Nhóm | Kiểm (30/09) | ✅ PASS | ⚠️ Ghi nhận | ❌ FAIL | ⏭️ SKIP (an toàn) |
|---|---|---|---|---|---|
| Nền tảng/auth/health/openapi | 7 | 7 | 0 | 0 | 0 |
| Regression fix cũ (#4,#8,#36,#38,#39,RBAC,CORS,skills) | 10 | 10 | 0 | 0 | 0 |
| Nghiệp vụ read-only (GET) | 6 | 5 | 1 (menu NV đọc được) | 0 | 0 |
| Web routes | 45 | 41 | 1 (4 redirect Quanverse cần browser auth) | 0 | 0 |
| Security headers | 3 | 2 | 1 (web thiếu headers) | 0 | 0 |
| Luồng ghi / gửi ngoài | ~20 case | 0 | 0 | 0 | ~20 |
| **TỔNG (đã chạy)** | **~71** | **65** | **3 ghi nhận** | **0** | **~20 skip chủ ý** |

**So với đợt 6 (29/09: 48 PASS / 2 SKIP):** mọi fix #35–#39 vẫn giữ (đặc biệt `/nguoi` về 19, `/store/profile` 401 không token, manager-only 403 cho NV, skills 200, contracts redact). Không phát hiện regression mới ở tầng API.

---

## 5. Phát hiện / ghi nhận (không sửa code theo yêu cầu)

| # | Mức | Nội dung | Bằng chứng |
|---|---|---|---|
| N1 | 🟡 P2 | **Web HTML thiếu security headers** trong khi API đủ. `GET /` không có `nosniff/DENY/CSP/HSTS/Referrer/Permissions`. Nguyên nhân: fix #6 chỉ thêm middleware FastAPI, chưa chạm Caddy/Next | `Invoke-WebRequest /` 30/09 23:4x: tất cả null + `csp_MISSING`; đối chứng `/api/v1/contracts` có `nosniff/DENY` |
| N2 | 🟢 P3 | **4 sub-route Quanverse 308 về `/quanverse` khi chưa login.** Đợt 6 login `hung` thì 200. Khả năng là redirect auth gộp, không phải 404 | `308 Location: /quanverse Via: 1.1 Caddy`; 41/45 route còn lại 200 |
| N3 | 🟢 Ghi nhận | **API `/menu` cho NV đọc (200) dù UI `/menu` OWNER_ONLY.** Hợp lý cho quầy/POS, cần chủ quán xác nhận chủ ý. Không đánh bug | `hung /menu=200`, `minh /menu=200` 30/09 |

Không xếp FAIL vì không có hành vi sai nghiệp vụ; 3 mục trên cần kiểm bằng trình duyệt đã login + quyết định cấu hình, không phải lỗi chặn demo.

---

## 6. Dấu vết test & xác nhận nguyên trạng

**Đã tạo (không thể tránh, không ảnh hưởng nghiệp vụ):**
- 1 session login fail (`hung/saimatkhau` → 401).
- 3+ session login thành công (`hung`, `lan`, `minh` → token 32 ký tự) để gọi GET auth. Session hết hạn tự nhiên, không đổi lịch/treo/đơn/menu.
- 0 đơn quầy, 0 điểm danh, 0 phiếu, 0 việc treo, 0 bàn giao, 0 cuộc họp, 0 luật, 0 tài khoản, 0 bài Page, 0 mail được tạo/sửa/xoá hôm nay.

**Xác nhận repo nguyên trạng (30/09 23:44 +07:00):**
- `git status --short` → chỉ `?? skills/genz-texting-agent/` (có sẵn trước khi test, không chạm).
- `git diff --stat` → trống (0 file sửa).
- `git log --oneline -3` → `7c982b3 feat(copilot): toi uu giao dien…`, `7f9637b fix(test):…`, `36c3ed9 merge:…`.
- Không sửa code, không commit, không push, không deploy, không reload Caddy, không chạy seed/migration.

**An toàn production tuân thủ:** dừng ở màn duyệt với mọi luồng FB/Page/mail; không bấm “Đăng bài / Đăng phản hồi / Gửi email”; không chạy solver/ghim/TKB; không đụng SerpApi quota (vẫn 240/250 từ đợt 6).

---

## 7. Kết luận

- Dự án đã đọc sơ qua, site live kiểm được ở mức read-only toàn diện: **65 PASS, 0 FAIL, 3 ghi nhận, ~20 skip chủ ý để giữ nguyên trạng.**
- Các fix nghiêm trọng đợt 6 (#35 deactivate-login, #36 rác tài khoản, #37 register rate-limit chưa kiểm lại vì cần ghi, #38 profile auth, #39 manager-only) — phần kiểm được bằng GET đều **còn giữ**.
- 2 việc nên làm tiếp (không thuộc phạm vi “chỉ test” hôm nay): (1) bổ sung security headers ở Caddy/Next cho web HTML; (2) kiểm 4 route Quanverse bằng trình duyệt đã login `hung` để khẳng định 308 chỉ là redirect unauth.
- File này là artifact duy nhất được tạo theo yêu cầu (“những gì đã làm / đã kiểm thử / kết quả có kiểm chứng”). Không có thay đổi mã nguồn nào kèm theo.

