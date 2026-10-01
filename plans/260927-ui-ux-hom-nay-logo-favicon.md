# 260927 — UI/UX `/hom-nay`: logo · favicon · phân cấp khối · chiều thời gian

**Nhánh:** `feat/web-hom-nay-ui-ux` (tạo từ `origin/main`, quy ước §1 `docs/github-operating-model.md`)
**Vùng:** D — `feat/web-*`
**Phạm vi đụng tới:** `apps/web/src/app/hom-nay/**`, `apps/web/src/ui/hom-nay/**`,
`apps/web/src/ui/Logo.tsx`, `apps/web/src/app/layout.tsx`, `apps/web/src/app/globals.css`,
`apps/web/src/lib/status.ts`, `apps/web/public/**`, `scripts/gen_app_icons.py`.
**KHÔNG đụng:** `apps/api/**`, `packages/**`, mọi contract dữ liệu. Xem §6.

---

## 0. Bằng chứng đo được trước khi sửa

Đo trực tiếp trên cây làm việc, không suy đoán.

### 0.1 Vì sao favicon không hiện

| Đo | Giá trị thật |
|---|---|
| `apps/web/public/favicon.ico` | 246.110 byte |
| Header ICO | `00 00 01 00 01 00` → **đúng 1 entry** |
| Entry #1 width | `00` → theo ICONDIR là **256** |
| Entry #1 height | `e9` → byte unsigned = 233, signed = **−23** (âm) |
| Entry #1 bpp | `00 20` = 32bpp |
| Entry #1 payload | `48 c1 03 00` = **246.088 byte** |
| Kích thước suy ra | **256 × 233 — KHÔNG vuông** |

Hai khiếm khuyết độc lập, cùng một nguyên nhân:

1. **Chỉ 1 entry.** Windows/Chrome/Edge cần ≥ 2 entry (16 và 32) trong một `.ico`
   để chọn đúng bản cho từng ngữ cảnh (tab, bookmark, taskbar). Một entry 256px
   bị **downscale** — ở 16px đường nét nhoè.
2. **Không vuông (256×233).** ICO chuẩn khai báo cạnh bằng **một byte**, nên tỉ lệ
   khác 1:1 không biểu diễn được. Nguồn của nó `docs/hinh/logo.png` cũng **không
   vuông** → đây là gốc rễ. Layout đã khai `/favicon.ico`, file có thật, không 404 —
   vấn đề **nằm ở nội dung file**, không nằm ở proxy: `infra/oracle/Caddyfile` dùng
   `handle { reverse_proxy web:3000 }` cho mọi path mặc định, `Dockerfile.web` có
   `COPY --from=builder /app/public ./public`, và `.dockerignore` **không** loại
   `public/`. Vậy asset được phục vụ đúng chỗ.

### 0.2 `manifest.webmanifest` thiếu khoá `icons`

File hiện chỉ có 7 khoá: `name`, `short_name`, `start_url`, `display`,
`background_color`, `theme_color`, `lang`. **Không có `icons`** → Android/Chrome
không có nguồn icon nào khi "Thêm vào màn hình chính".

### 0.3 Hai thương hiệu khác nhau trên cùng một sản phẩm

- `apps/web/src/ui/Logo.tsx` vẽ `d="M 30 70 L 30 30 L 50 70 L 70 30 L 70 70"` —
  chữ **M/N** zigzag, không đọc ra ly cà phê.
- `docs/hinh/logo.png` (nguồn favicon) là **ly cà phê có đường nhịp tim**.
- Không có file vector nào (`file_search **/*logo*.{svg,ai,eps}` → rỗng), nên phần
  `<motion.path>` hiện tại vốn không phải bản vector hoá của logo quán — nó là hình
  vẽ tay độc lập.

### 0.4 Số liệu bị nói lặp

`hom-nay/page.tsx:191-197` in `Brief sáng {ngay}: {so_ca} ca · {so_treo_mo} việc treo
đang mở · tồn cảnh báo: …`. Bốn số đó trùng: `so_treo_mo` = KPI #1 (Việc treo),
`ton_canh_bao` = KPI #3 (Cảnh báo tồn). Chỉ `so_ca` là thông tin **mới**.

### 0.5 Cột aside không tiêu đề

`hom-nay/page.tsx:253-301` — `<aside className="nq-dash-aside">` chứa **3 khối
không cùng chủ đề** mà không có `<h2>` tổng: cảnh báo tồn (một `<Alert>` **hoặc**
một `<p>`), hao hụt (một `<Alert>` **hoặc** một `<Link>`), và `SuaTimeline` (đã có
`<h3>` riêng). Người dùng đọc ra ba mẩu rời rạc.

### 0.6 Bốn thẻ KPI đều nhau

`globals.css:3263-3271` — `.nq-dash-kpi-cell { grid-column: span 6 }`, rồi
`@media (min-width: 768px) { grid-column: span 3 }`. Cả bốn thẻ **luôn** span 3.
`data-highlight` đã có (`kpi-card.tsx:52`) nhưng **chỉ** đổi hiệu ứng nghiêng
(`useHighlightTilt`) và lớp `nq-dash-kpi--pulse-hi` — không đổi kích thước.

### 0.7 Tiêu đề việc treo bị cắt cứng

- `apps/api/.../sprint45.py:1327` cắt `str(t.get("noi_dung") or "")[:120]` — cắt
  bằng substring, có thể đứt giữa từ.
- `.nq-item-title` (`globals.css:6079`) chỉ có `margin` + `font-weight: 600`:
  **không** clamp, **không** overflow. Với tiêu đề dài, `title` attribute cũng
  **chưa có**.
- **Phát hiện thêm (chặn demo):** có **9 chỗ ghi** vào cùng một danh sách `treo` với
  **5 tên khoá khác nhau cho cùng một khái niệm "nội dung"**:
  `noi_dung` (sprint3, chat, copilot, meeting, shift_rescue, war_room, fixture
  `treo_fx*`), `mo_ta` (`channels.py:2100`, và `seed_19_staff.py`),
  `tieu_de` (`seed_19_staff.py` — dùng cho **phiếu 95 việc** ở `/treo`,
  hiển thị qua khoá `v.noi_dung` ở `treo/page.tsx:48,233…` → cũng rỗng nếu không vá).
  `sprint45.py:1327` **chỉ** đọc `noi_dung` → với `make seed-demo`, 4 việc treo của
  `seed_19_staff` hiện **tiêu đề TRỐNG** trên `/hom-nay`.

### 0.8 Biểu đồ chỉ là ảnh chụp một thời điểm

- `TonBarChart` / `TreoDonutChart` (`dashboard-charts.tsx`) có hover/click, có
  `useReducedMotion` — **giữ nguyên cơ chế**, chỉ thêm.
- `TonBarChart` **không có** link. `TreoDonutChart` **không có** link.
  `SuaTimeline` **không có** link. Khối "Việc treo gần nhất" thì có
  (`<Link href="/treo">Xem tất cả (N)</Link>`) — không nhất quán.
- `/api/v1/hao-hut?ky=tuan` (`LossSummary`) **không có** trường nào là chuỗi theo
  thời gian; `ky` là từ vựng đóng `hom_nay|tuan|thang|all`. `/api/v1/hom-nay` cũng
  **không** có series. → Không thể vẽ sparkline hao hụt/tồn mà không sửa backend.
- **Nhưng item-level CÓ mốc thời gian**, đủ để bucket ở client:
  `/api/v1/viec-treo` → `created_at` (7 nguồn ghi) + `xong_luc`; `/api/v1/tieu-thu`
  → `luc`.

### 0.9 Cảnh báo dữ liệu thật (quyết định chọn cửa sổ)

| Nguồn seed | Khoá thời gian | Giá trị thật | So với "hôm nay" 2026-09-27 |
|---|---|---|---|
| `data/seed/sample.json` (`treo_fx01…18`) | `created_at` | `2026-01-05T07:00:00` … `2026-01-09` | **lệch ~9 tháng** |
| `scripts/seed_19_staff.py:245` (4 việc) | `tao_luc` (**không phải** `created_at`) | `2026-09-11T17:05:00Z` | **lệch 16 ngày** |
| `data/seed/sample.json` (`tieu_thu`) | `luc` | `2026-03-01T22:00:00` | lệch ~7 tháng |

→ Cửa sổ "7 ngày gần nhất tính đến hôm nay" sẽ ra **toàn số 0** trên dữ liệu seed.
Theo nguyên tắc fail-closed của repo (ADR-008; `loss.py` ghi rõ "`None ≠ 0.0`"),
đường 0 phẳng là **nói dối**: "không có dữ liệu" khác "có dữ liệu và bằng 0".
**Quyết định:** cửa sổ 7 ngày **neo vào mốc mới nhất có dữ liệu**, và nhãn ghi rõ
khoảng thật (không giả vờ là tuần này).

---

## 1. Wireframe sau khi sửa

```
┌─ HERO ──────────────────────────────────────────────────────────────────────┐
│  .nq-dash-hero  (nền: hoạ tiết CÀ PHÊ + NHỊP TIM, opacity thấp, --nq-accent) │
│ ┌──────────────────────────────────────┐ ┌────────────────────────────────┐ │
│ │ .nq-dash-strip                       │ │ OpsPulse (3D ≥1024px,          │ │
│ │  NHỊP QUÁN HÔM NAY        (h1)       │ │           Lite <1024/reduced)   │ │
│ │  {hero: "Lịch đã công bố · 4 việc treo"}                                  │ │
│ │  {meta: "Ngày 27/09 · 3 ca hôm nay"} │ │  ← MỤC 2: brief gộp vào đây     │ │
│ └──────────────────────────────────────┘ └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

┌─ "Việc của bạn" (nền accent-soft) ─────────────────────────  [giữ nguyên] ─┐
│  HÀNG ĐỢI HÔM NAY (eyebrow) → Việc của bạn (h2)                             │
│  ▸ {tiêu đề}                          {chi tiết}                        →  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─ KPI BENTO (12 cột) ───────────────────────────────────── MỤC 4 ────────────┐
│ CÓ thẻ AI đánh dấu (highlightKpi ≠ "ok"):                                   │
│ ┌─────────────────────── span 6 ─────┐ ┌─ s2 ─┐ ┌─ s2 ─┐ ┌─ s2 ─┐           │
│ │ ★ 4                 ← .nq-dash-kpi--hi (viền dày + nổi cao nhất)         │
│ │   VIỆC TREO          (value to hơn 1 bậc)  │  3  │ │  2  │ │  27 │       │
│ │                                            │INBOX│ │ TỒN │ │THÁNG│       │
│ └────────────────────────────────────────────┴─────┴─────┴─────┘           │
│ KHÔNG có thẻ nào nổi (quán yên ổn): cả 4 về span 3 như cũ — trạng thái      │
│ "yên" đọc ra được từ CHÍNH việc không có thẻ nào phình to.                  │
│ < 768px: mọi thẻ span 6 (2×2), thẻ nổi span 12 (1 cột dọc).                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─ .nq-dash-body ─────────────────────────────────────────────────────────────┐
│ ┌─ main (minmax(0,1fr)) ──────────────────┐ ┌─ aside (min 320px) MỤC 3 ───┐ │
│ │  DÒNG THỜI GIAN (mục 6)   ← MỚI (chỉ khi có ≥2 mốc)                     │ │
│ │  ┌───────────────────────────────────────┐                              │ │
│ │  │ XU HƯỚNG VIỆC TREO  7 mốc gần nhất    │                              │ │
│ │  │  ╱╲___╱▔╲___   sparkline SVG          │                              │ │
│ │  │  ▁▂▅▃▇▆▄  cột mở/xong theo ngày       │                              │ │
│ │  │  Xem tất cả việc treo →  (/treo)      │                              │ │
│ │  └───────────────────────────────────────┘                              │ │
│ │  ┌─ .nq-dash-charts ─────────────────────┐                              │ │
│ │  │ ┌─ .nq-dash-chart ──┐ ┌─────────────┐ │  ← <h2 class="nq-block-title">│
│ │  │ │ (h2) Kho & tiêu thụ│ │(h2) Việc treo│ │    thay <h3 nq-dash-chart- │
│ │  │ │ hover từng hàng    │ │ click lát    │ │    title> (cấp h3)          │
│ │  │ │ Tồn kho theo hàng  │ │ theo trạng   │ │                              │
│ │  │ │ (h3 nhỏ hơn)       │ │ thái         │ │                              │
│ │  │ │ Xem sổ tiêu thụ →  │ │ Xem việc treo│ │  ← MỤC 6: 2 link rõ ràng   │
│ │  │ └────────────────────┘ └─────────────┘ │    (trước chỉ 1 khối có)    │
│ │  └────────────────────────────────────────┘                              │ │
│ │  ┌─ (h2) Việc treo gần nhất ─────────────┐                              │ │
│ │  │  Danh sách có "Xem tất cả (N) →"       │                              │ │
│ │  │  {tiêu đề clamp 2 dòng, title=full}    │  ← MỤC 5                     │ │
│ │  └────────────────────────────────────────┘                              │ │
│ └──────────────────────────────────────────┘                              │ │
│                                            ┌─ (h2) Cảnh báo cần xử lý ────┐ │
│                                            │ ▸ Tồn dưới ngưỡng: …         │ │
│                                            │   [Mở sổ tiêu thụ]           │ │
│                                            │ ▸ Hao hụt cần xem: …         │ │
│                                            │   [Mở bảng hao hụt]          │ │
│                                            │ (rỗng → 1 câu "Chưa có cảnh  │ │
│                                            │  báo nào — quán đang trong   │ │
│                                            │  ngưỡng.")                    │ │
│                                            └──────────────────────────────┘ │
│                                            ┌─ (h2) Nhật ký thay đổi ──────┐ │
│                                            │ ● Sửa lịch  · 26/09 14:05     │ │
│                                            │   Lan Nguyễn                  │ │
│                                            │ Xem tab ghi nhận sửa → (/treo)│ │
│                                            └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Phân tầng nổi (mục 7)** — mỗi cấp một bậc, không hai khối cùng cấp đứng cạnh nhau
mà không có gì phân biệt:

| Cấp | Thành phần | Nổi |
|---|---|---|
| 1 — quan trọng nhất | `.nq-dash-kpi--hi` | viền accent dày + `--nq-shadow-float` |
| 2 — khối cần đọc | hero strip · ops-pulse · `--warn` · `--ok` | `--nq-shadow-bubble` (giữ) |
| 3 — khối nội dung | `.nq-dash-chart` (kể cả khối sparkline mới) | **hạ xuống `--nq-elev-1`** |

Lý do hạ cấp 3: hiện `.nq-dash-chart` dùng `--nq-shadow-bubble` = `--nq-elev-2`,
**cùng bậc** với hero strip và ops-pulse. Ba khối cạnh nhau cùng độ nổi thì mắt
không biết chỗ nào quan trọng — đúng mục 7.

---

## 2. Danh sách file sẽ đổi

| # | File | Việc |
|---|---|---|
| 1 | `apps/web/public/favicon.ico` | **sinh lại**: 2 entry 16+32, đúng chuẩn ICO |
| 2 | `apps/web/public/favicon-16x16.png` | mới |
| 3 | `apps/web/public/favicon-32x32.png` | mới |
| 4 | `apps/web/public/apple-touch-icon.png` | mới, 180×180 |
| 5 | `apps/web/public/icon-192.png` | mới |
| 6 | `apps/web/public/icon-512.png` | mới |
| 7 | `apps/web/public/icon-512-maskable.png` | mới, vùng an toàn 80% (Android cắt tới 20% mỗi cạnh) |
| 8 | `apps/web/public/icon.svg` | mới — cùng dữ liệu path với `Logo.tsx` ⇒ hai nơi không thể lệch |
| 9 | `apps/web/public/manifest.webmanifest` | thêm `icons` (3 entry, có `purpose: maskable`) |
| 10 | `apps/web/src/app/layout.tsx` | `metadata.icons` đủ size + `appleWebApp` |
| 11 | `apps/web/src/ui/Logo.tsx` | thay `<motion.path>` bằng path ly + nhịp tim (**hướng (a)**) |
| 12 | `apps/web/src/ui/hom-nay/dashboard-charts.tsx` | `nq-block-title` cho 2 chart · 2 link chi tiết · `TreoTrendSpark` mới · giữ nguyên hover/click |
| 13 | `apps/web/src/ui/hom-nay/kpi-card.tsx` | `StatusStrip` nhận `meta` (đã có prop, chưa ai dùng) · `KpiCard` nhận `hi` |
| 14 | `apps/web/src/app/hom-nay/page.tsx` | mục 2 · 3 · 4 · 5 · 6 |
| 15 | `apps/web/src/app/globals.css` | `.nq-dash-kpi-cell--hi` · `.nq-block--quiet` · `.nq-clamp-2` · `.nq-dash-hero__motif` · tầng nổi khối chart |
| 16 | `apps/web/src/lib/status.ts` | sửa `todayMetaLine` để tái dùng (hiện chưa ai gọi) |
| 17 | `scripts/gen_app_icons.py` | **mới** — sinh bộ icon từ `docs/hinh/logo.png` bằng Pillow |

---

## 3. Quyết định đã chốt với chủ dự án

| Câu hỏi | Chốt |
|---|---|
| Hướng logo | **(a)** vector hoá ly + nhịp tim từ `docs/hinh/logo.png` |
| Dòng brief | **Gộp vào `StatusStrip` qua prop `meta`, chỉ giữ số KHÔNG trùng** (`so_ca`) |
| Bố cục KPI | **(A)** nổi thì mới to: có `highlight` → span 6; không → span 3 như cũ |
| Chiều thời gian | **(A)** làm ở frontend: `/viec-treo` → bucket theo **ngày** (giờ ICT), cửa sổ neo mốc mới nhất có dữ liệu, có trạng thái "chưa đủ dữ liệu" |
| Nhánh | `feat/web-hom-nay-ui-ux` từ `origin/main` |

---

## 4. Chi tiết kỹ thuật

### 4.1 Nhất quán thời gian — dùng `Intl` với `timeZone: "Asia/Ho_Chi_Minh"`

`/api/v1/hom-nay` trả `ngay` theo **UTC** (`sprint45.py:1437`), và mọi
`created_at` là UTC. Bucket ở client phải theo **ICT**, không theo giờ máy: máy
dev ở múi khác sẽ ra cột lệch. `Intl.DateTimeFormat("en-CA", { timeZone:
"Asia/Ho_Chi_Minh" })` cho `YYYY-MM-DD` trực tiếp; `"vi-VN"` cho `DD/MM`.
**Không** dùng `new Date().toLocaleDateString()` trần (phụ thuộc múi máy), và
**không** viết offset cứng `+7` (ICT không có DST *hiện nay*, nhưng viết theo tên
vùng thì không phải bảo trì khi chính sách đổi — cùng lý do
`ag_waste/loss.py:528` dùng `ZoneInfo("Asia/Ho_Chi_Minh")`).

### 4.2 Khoá `noi_dung` — vá ở frontend, không sửa backend

`hom-nay/page.tsx` đọc `v.noi_dung || v.mo_ta || v.tieu_de`. Thêm `mo_ta`/
`tieu_de` vào type `TreoPreview`. Chọn **không** sửa `sprint45.py:1327` để giữ
đúng phạm vi "không đụng `apps/api`". Việc dài hạn (chuẩn hoá 5 tên khoá) ghi ở §6.

### 4.3 Favicon — sinh tất định, không gọi mạng

`scripts/gen_app_icons.py` dùng **Pillow** (đã có trong `docs/THIRD_PARTY.md` dòng
17 và 27, khai ở `packages/agents/pyproject.toml`; không thêm thư viện mới ⇒
không phát sinh yêu cầu ghi THIRD_PARTY).

Đầu vào `docs/hinh/logo.png` **không vuông** → bước 1 bắt buộc là **pad về vuông**
nền trong suốt (hoặc nền `--nq-bg #070d12` cho bản maskable), **không** kéo giãn
(stretch) — kéo giãn là cách chắc chắn nhất để logo méo, và nhiều khả năng đó
chính là cách file ICO cũ ra đời.

Viết `.ico` nhiều entry: Pillow hỗ trợ trực tiếp
`img.save("favicon.ico", sizes=[(16,16),(32,32)])` — ghi đúng `ICONDIR` nhiều
entry, khắc phục đúng lỗi "chỉ 1 entry".

### 4.4 Sparkline — neo vào mốc mới nhất, không vẽ đường 0 giả

`TreoTrendSpark` nhận `items: {created_at?, xong_luc?, tao_luc?}[]`:

1. Gom mọi mốc có thật; nếu **< 2 ngày** khác nhau → render câu "Chưa đủ dữ liệu
   theo ngày…", **không** vẽ trục.
2. Ngày xa nhất có dữ liệu = `max`, cửa sổ `[max-6d, max]`.
3. Nếu `max` lệch "hôm nay" > 1 ngày → nhãn ghi rõ khoảng thật, **không** gọi là
   "7 ngày qua". Không bịa trục.
4. Hai chuỗi: **mở mới** (`created_at`/`tao_luc`) và **đã xong** (`xong_luc`),
   vẽ cùng hệ trục; chú thích nói rõ mốc nào là mốc nào.
5. `useReducedMotion` → không animate. Không vòng lặp vô hạn (cổng
   `scripts/audit_motion_tokens.py` có `check_infinite_loops`).
6. Chỉ gọi `/api/v1/viec-treo` (mọi vai gọi được — `_require_role`), **không**
   gọi `/api/v1/audit` (chỉ `quan_ly`/`chu_quan` ⇒ nhân viên sẽ thấy lỗi).
7. Lỗi mạng → ẩn khối (đây là phần phụ, không được làm sập bảng hôm nay — cùng
   nguyên tắc `try/except` mà `sprint45.py:1358` áp cho phần hao hụt).

---

## 5. Rủi ro

| # | Rủi ro | Mức | Xử lý |
|---|---|---|---|
| 1 | Path vector hoá vẽ tay **lệch** ảnh gốc → hai nơi lại khác nhau lần nữa | **cao** | Bắt buộc so cạnh nhau ở **36px** (sidebar) và **16px** (tab) trước khi chốt; dùng **cùng dữ liệu path** cho `icon.svg` để favicon SVG không thể lệch `Logo.tsx` |
| 2 | Vẽ lại logo là vùng **nhạy cảm thương hiệu** | cao | Chỉ dùng nét hình học, không nhuộm lại; **không** đổi bảng màu gold/near-black (yêu cầu mục 7) |
| 3 | `outline` của `--pulse-hi` chỉ **một** màu ⇒ chỉ một thẻ được nổi | trung bình | Đã chốt: chỉ `highlightKpi ≠ "ok"` mới nổi; `ok` → không thẻ nào phình (cả 4 span 3) |
| 4 | Màn 768–1023px: thẻ nổi span 6 + 3 thẻ span 2 = tiêu đề chữ hoa bị ngắt 2 dòng | trung bình | Đo ở 768/1024/1440; nếu ngắt xấu thì mốc chuyển sang span 6/6/4-4-4 hoặc cho thẻ nổi span 12 ở dải này |
| 5 | Sparkline làm **tràn ngang** → `ui-system.spec.ts` đỏ (`horizontalOverflow ≤ 1px`) | trung bình | SVG `viewBox` + `width:100%`, không `min-width` cứng; đo ở 375/768/1440 |
| 6 | `globals.css` có **2 chỗ** khai `.nq-alert` (470 và 3701) và 1 chỗ `.nq-dash-kpi-cell` (3263, 3458) | trung bình | Chỉ **thêm**, không sửa/xoá chỗ cũ; kiểm bằng mắt sau khi đổi; ghi chú lý do tại dòng |
| 7 | Thêm CSS phá `prefers-reduced-motion` | thấp | Khối `@media` cuối file (9451) phải vẫn là cuối; **không** thêm `animation` vô hạn |
| 8 | Sửa `todayMetaLine` (hiện chưa ai gọi) làm vỡ test ẩn | thấp | `grep` lại trước khi sửa; giữ chữ ký tương thích |
| 9 | Đổi `Logo.tsx` ảnh hưởng **3 màn** dùng chung (`AppShell`, `/login`, `/`) | trung bình | Kiểm bằng mắt cả 3 sau khi sửa |
| 10 | Sparkline gọi thêm 1 API ⇒ **+1 request** khi tải `/hom-nay` | thấp | Chỉ dữ liệu `created_at`/`xong_luc`/`tao_luc` được đọc; hỏng thì ẩn khối; không chặn render chính |

---

## 6. Đề xuất diff BACKEND — **chưa làm, chờ duyệt riêng**

Ghi lại theo đúng yêu cầu mục 6 ("liệt kê rõ field cần bổ sung và dừng lại"),
**không** nằm trong phạm vi nhánh này.

1. **`GET /api/v1/hom-nay` — thêm `treo_theo_ngay`** *(ưu tiên cao)*
   `list[{ngay: "YYYY-MM-DD" (ICT), so_mo: int, so_xong: int}]`, 7 ngày, tăng dần,
   phần tử cuối = hôm nay. Lý do: hôm nay client phải tự bucket từ **toàn bộ**
   danh sách `treo` (không phân trang) — vừa phí băng thông vừa phụ thuộc việc mọi
   nguồn ghi đều có mốc thời gian. Neo theo **ICT** (không UTC như `ngay` hiện tại
   — xem ghi chú "lệch 7 giờ cuối ngày" trong báo cáo điều tra).

2. **Chuẩn hoá khoá nội dung việc treo** *(ưu tiên cao — đang gây bug thật)*
   9 chỗ ghi đang dùng 5 tên khoá: `noi_dung` · `mo_ta` · `tieu_de` (chưa kể
   `nhan_vien`/`nguoi_nhan`, `tao_luc`/`created_at`). Đề xuất: chọn **một** khoá
   chuẩn (`noi_dung`, `created_at`), ghi thêm ở tầng `persist` để tương thích
   ngược, và thêm test bất biến chặn ghi sai khoá.
   **Hệ quả đang thấy:** `sprint45.py:1327` chỉ đọc `noi_dung` ⇒ tiêu đề **rỗng**
   trên `/hom-nay` với `make seed-demo`; `/treo` có cùng lỗi với khoá `tieu_de`.

3. **`GET /api/v1/hao-hut` — thêm cửa sổ ngày + chuỗi theo ngày**
   `tu_ngay`/`den_ngay` (`YYYY-MM-DD`), và `LossSummary.chuoi:
   list[{ngay, ty_le_trung_binh: float|None}]`. Bắt buộc giữ bất biến `None ≠ 0.0`
   của `loss.py` — bucket rỗng phải là `null`, **không** `0.0`, nếu không sparkline
   vẽ đường phẳng giả. Lý do cần: `ky` hiện là **từ vựng đóng**
   (`hom_nay|tuan|thang|all`) và `LossLine` **không có** trường ngày ⇒ không thể
   dựng chuỗi hao hụt theo ngày từ client.

4. **Tồn kho theo ngày** *(ưu tiên trung bình)*
   `data/fixtures/professional/pos.json` đã có `inventory_snapshots`
   (`{item_id, date, opening, received, closing, waste, status}`, 8 dòng, toàn bộ
   `2026-08-29`) nhưng `seed_demo_data.py:43` ghi nó vào kv **`kiem_ke`** — sai
   khoá **và** sai hình dạng (`tinh_tu_kiem_ke` ở `loss.py:434` đọc
   `dau_ca`/`nhap_trong_ca`/`cuoi_ca`/`hao_hut_ghi`, **không có** ⇒ âm thầm thành
   `0.0`). Đề xuất: kv riêng `ton_ngay` + `GET /api/v1/ton-lich-su?tu_ngay&den_ngay`.
   **Không** dùng để vẽ sparkline tồn trước khi sửa, vì số sẽ sai chứ không rỗng.

5. **`GET /api/v1/tieu-thu` — thêm `tu_ngay`/`den_ngay`/`limit`**
   Hiện **không có** tham số nào và trả **toàn bộ** lịch sử. Thêm `limit` (mặc
   định 500, giống `/api/v1/audit` `limit≤1000`) trước khi ai đó dựng biểu đồ trên
   danh sách không giới hạn.

6. **Bảo trì: `tong_ket_ngay` bị ghi đè mỗi đêm** (`worker.py:211` `kv_set` một
   khoá duy nhất) ⇒ **mất lịch sử**. Nếu đổi thành append có trần (30 ngày) thì
   mọi chuỗi theo ngày ở trên có nguồn **đã tính sẵn**, không phải quét lại.

---

## 7. Kiểm chứng sau khi code (bước 3)

1. `cd apps/web && npx tsc --noEmit` — xanh (đây cũng là `npm run lint` của repo).
2. `python scripts/audit_motion_tokens.py` — xanh (không thời lượng/đường cong
   cứng ngoài `motion.ts`; không vòng lặp vô hạn; `reduced-motion` còn nguyên).
3. `python scripts/audit_page_patterns.py --only hom-nay` + `python
   scripts/verify_ui_changes.py` — so **trước/sau**.
4. `make seed-demo` (idempotent) rồi `npm run dev`, mở `/hom-nay` ở **3 vai**:
   `lan` (quản lý) · `hung` (chủ quán) · `minh` (nhân viên).
5. Đo ở **375 / 768 / 1440px**: không tràn ngang, 1 `<h1>`, cỡ chữ thuộc thang.
6. Bật `prefers-reduced-motion` → mọi animation đứng yên, **nội dung không đổi**.
7. Mở `/`, `/login` để chắc `Logo` mới không vỡ ở 3 màn dùng chung.
8. Kiểm tab trình duyệt hiện logo đúng (16px + 32px) và `/manifest.webmanifest` có
   `icons`.

## 8. Câu hỏi mở

1. **Fidelity của path vector hoá.** Tôi vẽ lại bằng nét hình học suy từ ảnh gốc;
   nếu cần khớp **chính xác từng điểm**, cho tôi file vector gốc (`.ai`/`.svg`) —
   hiện repo **không có** file vector nào.
2. **Bản maskable.** Tôi để nền `--nq-bg #070d12` và co logo vào 80%; nếu muốn nền
   khác (trắng, hoặc trong suốt) thì nói trước khi deploy.
3. **Có thay `favicon.png` cũ bằng `apple-touch-icon.png` không?** Kế hoạch này
   **thay** tham chiếu trong `metadata.icons.apple`; file `favicon.png` cũ sẽ
   **giữ lại** (chưa xoá) để tránh phá tham chiếu ngoài repo. Muốn xoá thì xác nhận.
4. **Sparkline "đã xong" (mở vs xong).** Hiện chỉ có `trang_thai="xong"` +
   `xong_luc`. Tôi vẽ **2 chuỗi** (mở mới / đã xong). Muốn gộp 1 chuỗi "đang mở
   luỹ kế" thì đổi — nhưng luỹ kế cần biết **thời điểm đóng** của mọi việc, mà dữ
   liệu cũ thiếu `xong_luc` ⇒ dễ ra đường sai.

---

## 9. KẾT QUẢ THỰC HIỆN (2026-09-27)

### 9.1 Ba phát hiện làm đổi kế hoạch giữa đường

**(a) `docs/hinh/logo.png` VUÔNG (160×160), thủ phạm là `favicon.png` (338×307).**
Kế hoạch ban đầu giả định ảnh gốc không vuông. Đo lại: `logo.png` và `logo_bold.png`
đều **160×160 vuông**; chỉ `apps/web/public/favicon.png` là **338×307** — và
256 × (307/338) = **233**, đúng bằng chiều cao entry ICO. Vậy tệp `.ico` hỏng được
sinh từ **favicon.png**, không phải từ logo gốc. Không cần pad ảnh gốc.

**(b) Còn một dấu thương hiệu THỨ BA.** `favicon.png` không phải logo nâu — nó là
hình **khác** trên nền kem `#f3f3f3` + mực navy `rgb(15,31,56)`, hai màu **không
tồn tại** trong `logo.png`. Vậy trên sản phẩm có **ba** dấu: zigzag trong `Logo.tsx`,
ly nâu trong `logo.png`, và hình navy/kem trong `favicon.png`.

**(c) Nâu `#432012` KHÔNG đọc được trên nền tối — đo được 1.25:1.**
Bảng đo tương phản WCAG (mực trên nền, ở đúng cỡ hiển thị):

| Nền | 16px | 32px | 192px |
|---|---|---|---|
| sáng `#ffffff` | 4.68:1 | 5.50:1 | 9.81:1 |
| tối `#070d12` | **1.25:1** | **1.27:1** | **1.40:1** |

Chrome/Edge/Safari vẽ favicon trên **cả** thanh tab sáng và tối. Nâu trên nền tối
gần như tàng hình ⇒ nền trong suốt không phải lựa chọn đúng. **Cách chữa:** đặt mực
lên **đĩa nền sáng** `--nq-accent-50` `#faf6e8` (bậc sáng nhất của chính dải gold
trong hệ token), tô kín ô cho `apple-touch-icon` (iOS bỏ alpha) và bản maskable.

**(d) Trace tự động thay vì vẽ tay.** Kế hoạch §5 rủi ro #1 là "path vẽ tay lệch ảnh
gốc". Đã **loại bỏ rủi ro đó bằng đo lường**: thử vẽ tay trước, đo IoU chỉ **0.42**;
rồi viết tracer (marching squares + làm mượt Gaussian + Douglas-Peucker, chỉ dùng
Pillow/numpy/scipy — **cv2 không phải dependency của repo**) đạt IoU **0.816–0.834**.
Số điểm giảm nhờ **làm mượt biên TRƯỚC khi lấy contour** — đúng cách potrace làm.

**(e) `fill-rule` phải là `evenodd`.** Hầu hết vòng contour trace ra **cùng chiều
quấn**, nên `nonzero` (mặc định) tô đặc ruột thay vì khoét lỗ ⇒ hình thành một khối.
`evenodd` cho IoU 0.89 (so với 0.82) và giữ được khe hở của nét vẽ.

**(f) Bug tiêu đề việc treo trống — vá được ở frontend.** `sprint45.py` chỉ đọc
`t.get("noi_dung")`, nhưng `seed_19_staff.py` ghi khoá **`mo_ta`** ⇒ **4 việc treo
đầu danh sách hiện tiêu đề TRỐNG** với `make seed-demo`. Đã vá `v.noi_dung ||
v.mo_ta || v.tieu_de`. **Không** sửa backend (đúng phạm vi).

### 9.2 Bảng đối chiếu yêu cầu → kết quả đo

| # | Yêu cầu | Kết quả đo (3 vai × 3 bề rộng) |
|---|---|---|
| 1 | Favicon đúng ở production | ICO **3 entry vuông** 16/32/48 (cũ: 1 entry 256×233); `manifest` có `icons` (3 entry, có `maskable`); `layout.tsx` khai 5 size + `apple` + `appleWebApp` |
| 1 | Sidebar ∪ favicon cùng ý tưởng | `Logo.tsx` + `icon.svg` cùng đọc `LOGO_PATH_D` từ `src/ui/logo-path.ts` (script sinh) → **không thể lệch**; có cổng `--kiem-drift` |
| 2 | Hết số liệu lặp | `brief_hay` (chuỗi "Brief sáng") **không còn trong DOM** ở cả 9 tổ hợp; `meta` giữ `Ngày … · N ca hôm nay` (số `so_ca` **không** trùng KPI nào) |
| 3 | Mọi khối có heading | **7 `<h2>`**: Việc của bạn · Xu hướng việc treo · Kho & tiêu thụ · Việc treo theo trạng thái · Việc treo gần nhất · **Cảnh báo cần xử lý** · **Nhật ký thay đổi** — hai khối aside **luôn** hiện, kể cả khi rỗng |
| 4 | KPI phá đều tăm tắp | ≥768px: **[357/547, 108, 108, 108]px** — thẻ nổi span 6, ba thẻ span 2. 375px: 162×4 (2×2). Thẻ nổi: `outline` gold 2px + `--nq-shadow-float` (elev-4) — **cao nhất trang**; ba thẻ kia `outline-style: none` |
| 5 | Hết cắt giữa câu | `-webkit-line-clamp: 2` + `line-clamp: 2`; `title` == text đầy đủ, `jsCut: false` (không substring ở JS) |
| 6 | Giữ tương tác, thêm chiều thời gian | hover/click giữ nguyên; thêm **`TreoTrendSpark`**: 14 thanh = 7 ngày × (phát sinh, đã xong), trục `05/01 → 11/01`, nhãn thật *"7 mốc gần nhất có dữ liệu — mốc mới nhất cách hôm nay 259 ngày"* |
| 6 | "Xem chi tiết →" mỗi biểu đồ | 3 link: `/treo`, `/tieu-thu`, `/treo` (trước chỉ 1 khối có) |
| 7 | Hoạ tiết hero + phân tầng nổi | `.nq-dash-hero__motif` opacity 0.5 (hạt cà phê + đường nhịp tim, đúng `--nq-accent`); tầng nổi: elev-4 (thẻ AI) > elev-2 (hero/pulse) > **elev-1** (khối chart, đã hạ) |

**Kiểm chứng bổ sung:**

- `npx tsc --noEmit` → **exit 0**.
- **Không tràn ngang** ở **cả 9** tổ hợp (`overflow=0px`), đúng `<h1>` trên mỗi trang.
- **`prefers-reduced-motion`**: 10 animation → **0**, nội dung **không đổi**
  (4 KPI, 14 thanh sparkline, độ dài chữ còn **tăng** 2387→2507 vì khối nhật ký
  hiện trạng thái rỗng thay vì bị ẩn).
- **Link e2e giữ nguyên**: `a[href="/hao-phi"]` hiện và bấm được **kể cả khi phần hao
  hụt lỗi** (`body.hao_hut = {co_du_lieu: false, ly_do: "khong_doc_duoc"}`) — như
  `e2e/hao-hut.spec.ts` yêu cầu.
- **Không hex mới** trong `dashboard-charts.tsx` (6 hex là của bản cũ); ký tự bị
  `audit_ui_consistency` gắn cờ đều là `→` (U+2192) — quy ước "lối đi" có sẵn của repo.
- `python scripts/gen_app_icons.py --kiem-drift` → **exit 0**.
- **Phạm vi**: `git diff --name-only origin/main` **không** có `apps/api/**` hay
  `packages/**`.

### 9.3 Việc còn lại (chờ duyệt riêng)

1. **Xoá `public/favicon.png`** — nay không còn ai tham chiếu (`metadata.icons.apple`
   đã trỏ `apple-touch-icon.png`). Kế hoạch **giữ lại** để tránh phá tham chiếu ngoài
   repo; `grep` toàn repo cho `favicon.png` **chỉ ra** `layout.tsx` (đã sửa), nhưng
   chưa xoá vì cần bạn xác nhận.
2. **Cổng icon vào CI**: `gen_app_icons.py --kiem-drift` hiện chạy tay. Nếu muốn, thêm
   vào `.github/workflows/ci.yml` / `scripts/pre_push_review.py`.
3. **6 hex trong `dashboard-charts.tsx`** (bảng màu lát donut) là **có chủ đích** và
   đã có từ trước (xem chú thích trong tệp về "khác cả SẮC lẫn ĐỘ SÁNG"). Không đụng.
4. **7 vi phạm `audit_motion_tokens.py`** ở các tệp **không liên quan** (ha-phi, lich-tuan,
  chat…) — kiểm chứng bằng `git diff` là **rỗng** so với `origin/main`, tức có sẵn từ
   trước, và cổng này **chưa** nối vào CI. **Không** phải hồi quy của nhánh này.

