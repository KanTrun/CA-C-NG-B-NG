# Runbook: TikTok scraping (TikWM primary + Apify fallback)

## Tổng quan

Hệ thống cào TikTok có **3 nguồn thật + 1 tầng tĩnh last-resort**, hoạt động theo thứ tự ưu tiên (mode `auto`):

```
┌─────────────────┐
│  User request   │
│  /trends?p=tiktok│
└────────┬────────┘
         ▼
┌─────────────────────────────┐
│  PRIMARY: TikWM Direct API  │
│  (miễn phí, không quota)    │ ─── fail / rỗng ──────────┐
└────────┬────────────────────┘                              │
         │ OK                                                ▼
         ▼                                   ┌──────────────────────────────┐
   ┌──────────┐                              │  TIER 2: Camoufox            │
   │  Return  │                              │  (browser thật, 0đ,          │
   │  items   │                              │   khó bị chặn, ~3-10s)       │
   └──────────┘                              └───────────────┬──────────────┘
                                                             │ fail (hoặc chưa cài)
                                                             ▼
                                                   ┌─────────────────────────────┐
                                                   │  TIER 3: Apify backup       │
                                                   │  (tốn CU — clockworks/      │
                                                   │   tiktok-scraper)           │
                                                   └──────────────┬──────────────┘
                                                                  │ fail
                                                                  ▼
                                                   ┌─────────────────────────────┐
                                                   │  LAST RESORT: static topics │
                                                   │  (is_live_scraped=False)    │
                                                   └─────────────────────────────┘
```

**Nguyên tắc:**
- TikWM = primary (miễn phí 100%, tiết kiệm quota Apify)
- Camoufox = tier trung gian (browser thật chống-detect, 0đ) — chỉ chạy khi TikWM fail và server đã cài (`camoufox fetch`). Chi tiết: `docs/runbooks/camoufox-scraping.md`
- Apify = backup, chỉ chạy khi cả TikWM lẫn Camoufox lỗi
- Static topics = last resort khi MỌI tầng thật fail — `is_live_scraped=False` để downstream phân biệt (plan §3.4)
- Mode `apify_force` trên UI: đảo chiều — Apify trước, TikWM backup
- Mode `direct_only`: chỉ TikWM, không bao giờ tốn CU Apify
- Mode `browser`: Camoufox first (plan §3.5)

### Đặc tính TikWM đã đo thật (2026-09-24, cập nhật 2026-09-25)

| Đặc tính | Giá trị | Ảnh hưởng code |
|---|---|---|
| Thời gian phản hồi | 0.4s – 9.3s (biến động mạnh) | Timeout đặt **20s** (`_TIKTOKWM_TIMEOUT_S`); timeout 6s cũ cắt ngang phần lớn request |
| Host | `tikwm.com` và `www.tikwm.com` **đều sống** nhưng hay lỗi tạm (timeout / HTTP 531) | `_fetch_tikwm_feed()` thử **lần lượt 2 host** trước khi bỏ |
| Rate limit | **1 request/giây** (`code=-1 "Free Api Limit: 1 request/second."`) | `_fetch_tikwm_comments()` tự chờ đủ nhịp 1.1s; chỉ cào comment cho **2 video đầu** |
| Shape response | **`data` là LIST PHẲNG** (không bọc `{"videos": [...]}`) | `parse_tikwm_feed()` hỗ trợ cả 2 dạng, từ chối `code != 0` (ADR-008) |

### ⚠️ `region=VN` KHÔNG phải bộ lọc thật — phải tự lọc

**Đo live 2026-09-25 (80–100 video qua 4–5 lần gọi):**

```
{'VN': 40, 'MM': 15, 'TH': 7, 'PK': 5, 'ID': 3, 'US': 3, 'PH': 2, 'KR': 1, 'JP': 1, 'UG': 1, 'SG': 1, 'GB': 1}
→ Tỷ lệ VN: 40/80 = 50%
```

Lần khác chỉ **21%** (21/100), có lần **1/20**, có lần **0/20**. Nghĩa là video
Thái Lan / Myanmar / Pakistan lẫn vào "TikTok Việt Nam" đúng như người dùng thấy.

| Cách thử lọc | Kết quả |
|---|---|
| `?region=VN` | Chỉ là gợi ý — **không ràng buộc** |
| `?region=VN&lang=vi` | VN=45% — không tốt hơn |
| `?region=VN&country=VN` | HTTP 531 |
| `?region=VN&city=ho chi minh` | HTTP 531 |
| `?region=VN&type=1` | VN=30% |
| `?region=vn` (chữ thường) | HTTP 531 |
| `/api/feed/search?keywords=...` | **403 Forbidden** (không dùng được) |

**→ Giải pháp trong code:** `_filter_vn_videos()` **CHỈ giữ `region == "VN"`** (bỏ hẳn
video nước ngoài), và `_fetch_tikwm_feed_vn()` gọi **3 lần** để tích luỹ + khử trùng
theo `video_id` (1 lần gọi không đủ: đo thật 4 lần → 24 video VN unique; có lần 0 video VN).

⚠️ **Hệ quả cần biết:** khi TikWM trả quá ít video VN, kết quả TikTok sẽ **ít hoặc rỗng**
(và rớt xuống Camoufox → Apify). Đây là hành vi ĐÚNG (fail-closed): thà rỗng còn hơn
hiển thị video Thái/Myanmar dưới nhãn "TikTok Việt Nam".

### ⚠️ Apify: payload rỗng làm actor FAILED ngay nhưng VẪN tốn CU

Đo thật 2026-09-24: `clockworks/tiktok-scraper` FAILED **7/8 run** gần nhất, mỗi run
vẫn tiêu ~**$0.0037** Compute Units. Một nguyên nhân là payload **không có
`searchQueries`/`hashtags`/`profiles`** khi keyword rỗng.

→ `_build_input()` nay luôn điền truy vấn mặc định (`xuhuong`, `tiktok vietnam`…)
cho cả 3 mode. **Không bao giờ** để actor nhận payload rỗng.

→ Poll status của Apify nay chịu được lỗi mạng tạm thời (`_MAX_POLL_ERRORS=3`):
trước đây **1 lần poll timeout 5s** là bỏ luôn cả actor run dù run vẫn đang chạy
phía Apify (vừa mất data thật, vừa vẫn bị tính CU).

## Setup ban đầu

### 1. Đăng ký Apify

1. Vào https://console.apify.com/sign-up
2. Đăng ký bằng email (gói Free — hạn mức thật xem ở `/page-quan` hoặc `GET /api/v1/trends/apify-usage`)
3. Vào **Settings → Integrations → Token** → copy token

### 2. Cấu hình `.env`

Thêm 3 dòng vào `apps/api/.env` (không commit file này):

```bash
APIFY_TOKEN=apify_api_xxxxxxxxxxxxxxxx
APIFY_TIKTOK_ACTOR_ID=clockworks/tiktok-scraper
TIKTOK_APIFY_TIMEOUT_S=90
```

> **Actor Threads cũng cần ID tồn tại thật**: `APIFY_THREADS_ACTOR_ID`. Giá trị
> `apify/threads-scraper` **KHÔNG tồn tại** (HTTP 404 khi gọi API) — dùng
> `curious_coder/threads-scraper` (đã xác minh tồn tại). Kiểm tra nhanh:
> `https://api.apify.com/v2/acts/<owner~name>?token=<token>`

### 3. Verify

```bash
python scripts/smoke_tiktok_apify.py
```

Kết quả mong đợi:
- `✅ Source : tiktokwm` + N items (TikWM OK, không tốn quota Apify)
- Nếu TikWM fail → `✅ Source : apify` (backup kích hoạt)
- Nếu in `Source : unknown` → dữ liệu giả/cũ, báo dev check id prefix

## Theo dõi hàng ngày

### Log cần quan sát

| Log event | Ý nghĩa |
|---|---|
| `tiktok_source_tikwm_primary` | TikWM OK, đếm `items_count` |
| `tiktok_source_tikwm_empty` | TikWM fail/rỗng → đang chuyển sang Apify backup |
| `apify_tiktok_source_ok` | Apify backup OK, đếm `items_count` |
| `tiktok_apify_backup_also_failed` | Cả hai nguồn fail → trả `[]` |

### Metric (nếu có Prometheus)

| Metric | Ý nghĩa | Alert khi |
|---|---|---|
| `tiktok_source_total{source="tikwm_direct"}` | Số lần TikWM OK | < 80% tổng / 1h |
| `tiktok_source_total{source="apify"}` | Số lần rơi vào Apify backup (tốn CU) | > 5 / 1h |
| `tiktok_fallback_total{reason="apify_error:quota"}` | Hết quota Apify | ≥ 1 / 24h |

### Apify Console

- Quota: https://console.apify.com/billing
- Usage log: https://console.apify.com/actors/runs

## Sự cố thường gặp

### 🔴 Log: `ApifyError: APIFY_TOKEN chưa cấu hình`

**Nguyên nhân:** Token rỗng / chưa set trong `.env`

**Cách xử lý:**
1. Mở `apps/api/.env`
2. Kiểm tra `APIFY_TOKEN=apify_api_...` không rỗng
3. Restart API: `systemctl restart ca-api`
4. Chạy lại `scripts/smoke_tiktok_apify.py`

### 🔴 Log: `ApifyError: status=FAILED` liên tục

**Nguyên nhân:** Actor bị lỗi hoặc TikTok chặn proxy Apify

**Cách xử lý:**
1. Vào https://console.apify.com/actors/runs xem chi tiết run fail
2. Nếu là do TikTok chặn → chờ 1-2h rồi retry
3. Nếu là bug actor → check actor repo: https://github.com/clockworks/tiktok-scraper
4. Fallback TikWM đang chạy tạm → user vẫn có data (dù chất lượng thấp hơn)

### 🟡 Log: `ApifyError: timeout sau 90s`

**Nguyên nhân:** Apify chậm (bình thường 10-30s, có khi tới 90s)

**Cách xử lý:**
1. Tăng `TIKTOK_APIFY_TIMEOUT_S=180` trong `.env`
2. Restart API
3. Nếu vẫn timeout → check Apify status: https://status.apify.com/

### 🔴 Metric `tiktok_fallback_total` > 5 lần / phút

**Nguyên nhân:** Hết quota $5/tháng hoặc token bị revoke

**Cách xử lý:**
1. Check quota: https://console.apify.com/billing
2. Nếu hết quota → đợi reset tháng sau hoặc nạp thêm
3. Nếu token bị revoke → tạo token mới, update `.env`

### 🟡 Log: `unexpected:KeyError`

**Nguyên nhân:** Apify actor đổi schema output

**Cách xử lý:**
1. Vào Apify Console → xem JSON mẫu mới nhất
2. Báo dev update `packages/agents/src/ca_agents/sources/tiktok_apify_source.py`
3. Pin version actor trong `.env` nếu cần (vd `clockworks/tiktok-scraper~1.2.0`)

### 🔴 Cả Apify lẫn TikWM đều fail → UI mất data

**Nguyên nhân:** Cả 2 nguồn đều chết

**Cách xử lý:**
1. Verify Apify: `python scripts/smoke_tiktok_apify.py`
2. Check internet connection từ server
3. Nếu cần kíp: dùng mode `apify_force` trên UI để ép Apify (nếu quota còn)
4. Liên hệ dev để tìm nguồn thay thế

> ⚠️ **KHÔNG bật mock data dự phòng** — vi phạm ADR-008 anti-fake-signals. Khi cả 2 nguồn fail, hệ thống trả `[]` và hiển thị "không có dữ liệu" là hành vi đúng.

## Khi nào cần dev can thiệt

| Tình huống | Action của dev |
|---|---|
| Schema break (KeyError, missing field) | Update mapping trong `tiktok_apify_source.py` |
| Actor deprecated | Đổi `APIFY_TIKTOK_ACTOR_ID`, có thể viết adapter mới |
| TikWM chết hẳn | Tìm fallback mới (RapidAPI TikTok scraper, scraperapi.com,...) |
| Cần thêm use case (hashtag, profile, music) | Extend `scrape_tiktok_apify()` với `mode` param mới |

## Cost reference

| Hoạt động | Compute Units (CU) ước tính |
|---|---|
| Search 12 videos | ~0.5 CU |
| Search 50 videos | ~2 CU |
| Lấy full comment 1 video | ~0.3 CU |
| Quét 1 profile (50 video) | ~3 CU |

**Free tier:** $5 = ~1000 CU / tháng (tùy actor pricing).

**Estimate với traffic hiện tại:**
- ~200 requests/ngày × 0.5 CU = 100 CU/ngày
- ~3000 CU/tháng → vượt free tier → cần plan $29 hoặc giảm traffic

Nếu vượt → check log `apify_tiktok_source_ok` để tối ưu (cache, batch).

## Reference

- Plan: `plans/260830-0930-tiktok-apify-primary-tiktokwm-fallback/plan.md`
- Code: `packages/agents/src/ca_agents/clients/apify_client.py`
- Code: `packages/agents/src/ca_agents/sources/tiktok_apify_source.py`
- Code: `packages/agents/src/ca_agents/ag_trend.py::_scrape_tiktok_smart`
- Smoke test: `scripts/smoke_tiktok_apify.py`
- Apify Console: https://console.apify.com/
- Apify docs: https://docs.apify.com/

## Lịch sử thay đổi

| Ngày | Tác giả | Thay đổi |
|---|---|---|
| 2026-08-30 | AI assistant | Tạo runbook ban đầu (kèm plan refactor Apify primary + TikWM fallback) |
| 2026-09-10 | AI assistant | Thêm tier Camoufox vào chuỗi (giữa Apify và TikWM), kèm plan tích hợp AG-TREND |