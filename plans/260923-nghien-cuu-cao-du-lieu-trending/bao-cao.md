# Nghiên Cứu & Kiểm Chứng: Cào Dữ Liệu Trending (AG-TREND)

> **Ngày:** 2026-09-23 (cập nhật 2026-09-24) · **Phạm vi:** `packages/agents` (AG-TREND), `apps/api/trends.py`, `apps/web/page-quan`
> **Phương pháp:** chạy thật từng nguồn (probe live, read-only) — không chấp nhận "code complete"
> **Nguyên tắc áp dụng:** ADR-008 (chống tín hiệu giả), fail-closed
> **Trạng thái:** ✅ ĐÃ SỬA — xem §9 để biết các thay đổi đã triển khai

---

## 1. Tóm tắt điều hành

Hệ thống AG-TREND có **6 nguồn cào trending** với kiến trúc tier-fallback khá tốt, nhưng kiểm chứng bằng chạy thật cho thấy **nhiều lỗi sản xuất nghiêm trọng** khiến phần lớn nguồn không trả được dữ liệu thật:

| # | Bug | Mức độ | Hệ quả thật | Trạng thái |
|---|---|---|---|---|
| **B1** | TikWM: `timeout=6s` quá ngắn (thực tế 0.4–9.3s) + không thử host dự phòng + không kiểm tra `code` | 🔴 Chặn | TikWM **luôn trả []** dù nguồn sống → mọi request TikTok rớt xuống Apify (tốn quota) | ✅ Đã sửa |
| **B2** | SerpApi Google Trends thiếu `data_type=RELATED_QUERIES` | 🔴 Chặn | `fetch_fnb_trends_serpapi()` **luôn trả []** → tầng SerpApi vô dụng, tốn quota vô ích | ✅ Đã sửa |
| **B3** | Apify actor TikTok FAILED 7/8 run + payload rỗng + poll timeout 5s bỏ luôn run | 🔴 Chặn | Không có tầng thật nào cho TikTok → UI hiển thị **6 chủ đề tĩnh giả** | ✅ Đã sửa |
| **B4** | `.env` trỏ `APIFY_THREADS_ACTOR_ID=apify/threads-scraper` **không tồn tại** (HTTP 404) | 🟡 Nên sửa | Tầng Apify cho Threads là dead code | ✅ Đã sửa |
| **B5** | Threads Bridge **bịa link** `@threads_creator` + gán nhãn "Meta Threads" cho tin báo chí | 🟡 Nên sửa | UI trỏ tới hồ sơ không tồn tại; nguồn bị gán nhãn sai | ✅ Đã sửa |

**Hệ quả tổng hợp:** dữ liệu TikTok trên UI là **100% tĩnh (hard-code)** — 6/84 item của radar có `is_live_scraped=False`.

### 1.1. Đính chính chẩn đoán B1 (quan trọng)

Bản báo cáo đầu tiên kết luận B1 là *"code đọc sai shape `data`"*. **Sau khi đo kỹ lại (3–4 lần lặp/host), chẩn đoán đúng là:**

| Quan sát | Kết luận |
|---|---|
| `data` **luôn là list phẳng** | Code cũ **xử lý ĐÚNG** shape (`isinstance(raw_data, dict)` → else dùng list) |
| Thời gian phản hồi **0.4s – 9.3s**, hay vượt 6s | `timeout=6` cắt ngang phần lớn request → `TimeoutError: read operation timed out` |
| Có lúc trả **HTTP 531** | Lỗi tạm thời của hạ tầng TikWM |
| Cả `tikwm.com` và `www.tikwm.com` đều sống, lỗi khác nhau theo thời điểm | Cần thử **cả hai** host |
| Request thứ 2 liên tiếp → `code=-1 "Free Api Limit: 1 request/second."` | Rate limit 1 req/s; code cũ **không kiểm tra `code`** và dùng timeout comment 2s |

**Bài học:** chẩn đoán dựa trên 1 lần probe có thể sai. Phải lặp nhiều lần để tách *lỗi tạm thời* khỏi *lỗi logic*.

---

## 2. Kiến trúc thực tế (đã xác minh)

### 2.1. Luồng end-to-end

```
UI: apps/web/src/app/page-quan/page.tsx
  → GET /api/v1/trends/radar?region=&category=&keyword=&mode=
  → fetch_trend_radar()            [ag_trend.py]
  → chuỗi source theo platform → list[TrendItem] → JSON
```

### 2.2. Chuỗi tier theo platform

| Platform | Chuỗi (mode `auto`) | Trạng thái chạy thật |
|---|---|---|
| `tiktok_vn` | TikWM → Camoufox → Apify → **static tĩnh** | 🔴 rớt hết → static |
| `threads_vn` | Official API → Google Bridge → Jina Direct → Camoufox(Trending) → Apify → RSS GenZ | 🟡 Bridge chạy, nhưng link bị bịa |
| `google_vn` | SerpApi Trends → **RSS trực tiếp** | 🟡 RSS OK, SerpApi chết |
| `star_vn` | RSS Kenh14 scrape trực tiếp | 🟢 OK (50 item thật) |
| `tiktok_global` | RSS Google Trends US | 🟢 OK (10 item thật) |

### 2.3. 4 mode cào

`auto` (mặc định) · `direct_only` (khóa Apify+Camoufox) · `apify_force` · `browser` (Camoufox first).

---

## 3. Bằng chứng chạy thật (2026-09-23)

### 3.1. Bảng kết quả probe live

| Nguồn | Thời gian | Kết quả | Có thật? |
|---|---|---|---|
| Google Trends VN (RSS) | 3.01s | 10 items | ✅ thật |
| Google Trends Global (RSS) | 0.59s | 10 items | ✅ thật |
| Showbiz & KOLs (Kenh14) | 0.36s | 50 items | ✅ thật |
| **TikTok (auto)** | 13.95s | 6 items | ❌ **tĩnh, is_live_scraped=False** |
| **TikWM trực tiếp** | 6.12s | **0 items** | ❌ bug B1 |
| **Threads (auto)** | 1.33s | 8 items | ⚠️ link bịa |
| Threads Google Bridge | 0.48s | 6 items | ⚠️ link bịa |
| Threads Official API | — | `is_configured()=False` | ⚪ chưa có token |
| Threads Direct (Jina) | 0.94s | 0 items | ❌ HTTP 403 |
| **SerpApi Trends F&B** | 2.88s | **0 items** | ❌ bug B2 |
| Camoufox | — | `is_available()=False` | ⚪ chưa cài |
| **Radar tổng hợp (all)** | 16.34s | **84 items**, 14 item tĩnh | — |

### 3.2. Bug B1 — TikWM timeout quá ngắn + không thử host dự phòng (bằng chứng)

**Đo thời gian thật (4 lần lặp/host, timeout=6s như code cũ):**

| Host | Kết quả |
|---|---|
| `www.tikwm.com` | 6.12s TIMEOUT · 6.09s TIMEOUT · 0.42s `code=-1` · 0.45s `code=-1` |
| `tikwm.com` | 6.34s OK (21 video) · 6.12s TIMEOUT · 6.09s TIMEOUT · 5.30s OK (16 video) |

**Cùng 2 host đó với timeout=20s:**

| Host | Kết quả |
|---|---|
| `www.tikwm.com` | 7.52s OK (20 video, region VN) · 6.14s **HTTP 531** · 6.06s OK (21 video) |
| `tikwm.com` | 6.31s **HTTP 531** · 5.75s OK (20 video) · 9.30s OK (21 video) |

**⇒ Kết luận:** nguồn **hoàn toàn sống**, nhưng:
1. Thời gian phản hồi thật (0.4–9.3s) **thường xuyên vượt `timeout=6`** → request bị cắt ngang.
2. Cả hai host đều hay lỗi tạm (timeout/HTTP 531) → cần **thử lần lượt cả hai**.
3. Code cũ **không kiểm tra `code`** — payload `{"code": -1, "msg": "Free Api Limit: 1 request/second."}` vẫn đi tiếp vào vòng lặp.
4. Comment dùng `timeout=2` (quá ngắn) và **gọi liên tiếp** → chạm rate limit 1 req/s → luôn rỗng.

**Bằng chứng rate limit:** request comment thứ nhất OK (`code=0`, 3 comment), request thứ hai liên tiếp ngay sau → `code=-1 "Free Api Limit: 1 request/second."`

**Test hiện có không bắt được** vì `test_tiktok_smart_fallback.py` mock toàn bộ `_scrape_tiktokwm_fallback` → không bao giờ chạm HTTP thật. Đây là lỗ hổng kiểm thử: **thiếu test cho tầng HTTP/parse của nguồn bên thứ ba**.

### 3.3. Bug B2 — SerpApi thiếu `data_type` (bằng chứng)

| `data_type` | Trả về | rising | top |
|---|---|---|---|
| *(mặc định / TIMESERIES)* | `interest_over_time` | **0** | **0** |
| `RELATED_QUERIES` | `related_queries` | **20** | **25** |

Code gọi `search_serpapi("google_trends", {"q":…, "geo":…, "date":…})` — không truyền `data_type` ⇒ SerpApi mặc định TIMESERIES ⇒ payload **không có `related_queries`** ⇒ `parse_gtrends_to_trend_items()` trả [] ⇒ `fetch_fnb_trends_serpapi()` trả [].

**Xác minh:** gọi thẳng SerpApi với `data_type=RELATED_QUERIES` + parse bằng chính hàm của hệ thống → **8 TrendItem thật** ("trà sữa viên viên hà nội" +600%, "trà sữa tam hảo" +300%…).

**Tác động kép:** (1) tầng SerpApi vô dụng cho keyword cụ thể; (2) vẫn **tốn 1 request quota** cho mỗi lần gọi thất bại (quota hiện 13/250). Cache L2 đang giữ payload TIMESERIES đã hỏng nên lỗi "dính" thêm 12h.

### 3.4. Bug B3 — Apify TikTok FAILED + payload rỗng + poll timeout (bằng chứng)

**Run history `clockworks/tiktok-scraper`:**

| Thời điểm | Status |
|---|---|
| 2026-09-23 11:05 | FAILED |
| 2026-09-23 11:05 | FAILED |
| 2026-09-22 09:52 | FAILED |
| 2026-09-22 09:27 | FAILED |
| 2026-09-21 07:29 | FAILED |
| 2026-09-21 04:18 | FAILED |
| 2026-09-19 04:54 | FAILED |
| 2026-09-17 14:55 | SUCCEEDED |

= **7/8 run gần nhất FAILED** (từ 2026-09-19). Mỗi run vẫn tiêu ~$0.0037.

**Ba nguyên nhân độc lập được xác định:**

1. **Payload rỗng khi keyword rỗng.** `_build_input("", 10, "search")` cũ trả `{"maxItems":10, "downloadVideo":False, "proxyCountryCode":"VN"}` — **không có `searchQueries`**. Actor fail ngay mà vẫn tốn CU.
2. **Poll timeout 5s bỏ luôn cả run.** `_HTTP_TIMEOUT_POLL_S=5`; khi poll gặp `TimeoutError: read operation timed out` thì code cũ `raise ApifyError` **ngay lập tức** — dù actor vẫn đang chạy phía Apify. Đo thật: 1 run `SUCCEEDED` sau **3 phút** (`11:15:32 → 11:18:42`) nhưng lần poll đầu đã timeout.
3. **Run thật đã SUCCEEDED gần đây** (`WIgFmc3opsAXHbXQ0` 11:16, `n7RZz6eq03idx8sGu` 11:15) → actor **không chết**, đường ống mới là vấn đề.

### 3.5. Bug B4 — Actor Threads không tồn tại

Đo live `GET /v2/acts/<actor>`:

| Actor | Kết quả |
|---|---|
| `apify/threads-scraper` | ❌ **HTTP 404** "Actor with this name was not found" |
| `curious_coder/threads-scraper` | ✅ OK — title `'Meta threads scraper'`, id `LnCvmgElmmlHN1gvZ` |
| `louisdeconinck/threads-scraper` | ❌ 404 |
| `automation-lab/threads-scraper` | ✅ OK — title `'Threads Scraper'` |

`.env` đang trỏ `apify/threads-scraper` (không tồn tại) **ghi đè** default đúng trong code (`curious_coder/threads-scraper`) ⇒ tầng Apify Threads là dead code.

### 3.6. Vấn đề B5 — Link Threads Bridge bị bịa

`parse_google_rss_xml()` nhánh `if "threads.net" not in final_url` dựng link giả:
```python
author = author_m.group(1) if author_m else "threads_creator"
final_url = f"https://www.threads.net/@{clean_kw}"
```
→ 8 item Threads đều có `link = https://www.threads.net/@threads_creator` (không trỏ tới bài thật).

Kiểm chứng: Google News RSS `site:threads.net …` trả **0 item** (`RSS len=1216, items=0`) — nên dữ liệu Threads của radar thực tế đến từ **query fallback không `site:`** (kết quả báo chí, không phải bài Threads).

### 3.7. Vấn đề B6 — Không có trần tương tác, ảo giác ưu tiên

- 50/84 item là `star_vn` (báo giải trí) → **lấn át** tín hiệu F&B.
- `_scrape_google_trends_global` trả tin Mỹ (thời tiết, "Daylight Savings") gắn `nguon_goc="tiktok_global"` — **gán nhãn sai nền tảng**, không liên quan F&B VN.

---

## 4. Nguồn trending bổ sung (đã probe)

| Nguồn | Kết quả probe | Đánh giá |
|---|---|---|
| **SerpApi `google_trends_trending_now`** | HTTP 200, **25 trending thật** VN (xổ số miền trung 500K, u-23 VN-TL +1000%, himass…) kèm `search_volume`, `increase_percentage`, `categories`, `trend_breakdown` | ⭐ **Nên thêm** — nguồn trending VN chất lượng cao, đúng "bảng xu hướng" |
| TikTok `challenge/detail` (công khai) | HTTP 200: `#xuhuong` 6.15K tỷ views, `#cafe` 108 tỷ, `#matcha` 64 tỷ, `#cafemuoi` 298M | ⭐ **Nên thêm** — đo "sức nóng tuyệt đối" hashtag F&B, không cần key |
| TikWM `feed/list` (đã có) | HTTP 200, 5–10 video/region thật (play/digg thật) | ⚠️ Đang có bug B1 |
| TikTok Creative Center API | **401 "no permission"** | ❌ Cần đăng nhập/cookie, không dùng được |
| TikTok `challenge/item_list` | HTTP 200 nhưng **len=0** | ❌ Đã bị đóng |
| Jina Reader (`r.jina.ai`) | **HTTP 403** | ❌ Đã chết cho Threads |

---

## 5. Đối chiếu plan ↔ code ↔ thực tế

| Nguồn lệch | Chi tiết |
|---|---|
| **Runbook tiktok-scraping.md** | Sơ đồ ghi chuỗi `TikWM → Camoufox → Apify` nhưng **thiếu nhánh static last-resort** trong hình (đã có ở mục "Nguyên tắc") |
| **Runbook camoufox-scraping.md** | Ghi `Threads: Official API → Google RSS → Jina → Camoufox → Apify → RSS` — Jina (403) và Apify (404) đều chết, sơ đồ mô tả năng lực không tồn tại |
| **`AGENT_NAMES` vs `.env`** | Docstring `threads_apify_source.py` ghi `curious_coder/threads-scraper`, `.env` ghi `apify/threads-scraper` (không tồn tại) |
| **Plan 260914 §4.2 (lifecycle)** | Đã code đầy đủ (`threads_trending_lifecycle.py`) nhưng **không có consumer** vì Camoufox chưa cài |
| **Plan 260910 §3.5** | Mode `browser` phụ thuộc Camoufox — chưa cài trên máy này |

---

## 6. Khuyến nghị (ưu tiên)

### P0 — Sửa ngay (chặn merge)

1. **B1 TikWM**: sửa đọc `data` dạng list phẳng:
   ```python
   raw_data = data.get("data") or []
   vids = raw_data.get("videos", []) if isinstance(raw_data, dict) else raw_data
   ```
   Thêm **test parse shape thật** (fixture JSON copy từ response thật) — không mock cả hàm.
2. **B2 SerpApi**: thêm `"data_type": "RELATED_QUERIES"` vào params `fetch_fnb_trends_serpapi`; **xóa cache L2** payload TIMESERIES đã hỏng (`data/cache/serpapi/*.json`).
3. **B3/B4**: xác định lại actor Apify (kiểm tra run log FAILED, thử actor khác hoặc `APIFY_TIKTOK_ACTOR_ID` hợp lệ); sửa `APIFY_THREADS_ACTOR_ID` hoặc bỏ tầng Threads Apify.

### P1 — Nên làm

4. **B5**: bỏ nhánh dựng link giả `@threads_creator`; nếu RSS không trả link `threads.net` thì `link_goc` để rỗng + `is_live_scraped=False`.
5. **Thêm SerpApi `google_trends_trending_now`** làm nguồn `google_vn` chính (25 trending VN thật).
6. **Thêm TikTok `challenge/detail`** để đo "sức nóng" hashtag F&B (viewCount thật).
7. **B6**: thêm trần số item/nguồn (ví dụ 10–12) và **ưu tiên F&B** khi gộp radar.

### P2 — Cải thiện cấu trúc

8. Cài Camoufox (`pip install camoufox[geoip]` + `camoufox fetch` + `scripts/threads_setup_login.py`) để kích hoạt tier Trending Now đã code xong.
9. Thêm `.env` keys `THREADS_ACCESS_TOKEN` (Official API tier 0) — đường đáng tin nhất cho Threads.
10. Test mới: **fixture-based parse test** cho mọi nguồn bên thứ ba (dùng `data/mock_external/` theo `docs/mock-external-data-test.md`).

---

## 7. Cách tái lập bằng chứng

```bash
# Probe live tất cả nguồn (read-only)
.venv312\Scripts\python.exe _tmp_probe_trending.py
.venv312\Scripts\python.exe _tmp_probe_trending2.py   # Apify run history + SerpApi payload
.venv312\Scripts\python.exe _tmp_probe_trending4.py   # data_type A/B test
.venv312\Scripts\python.exe _tmp_probe_trending5.py   # TikWM domain + nguồn thay thế
```

**Lưu ý:** các script trên là file TẠM, đã xóa sau khi hoàn tất nghiên cứu.

---

## 8. Ghi chú môi trường

- `.env` gốc **đã được khôi phục** (trước đây memory ghi bị mất): có `APIFY_TOKEN`, `SERPAPI_API_KEY`, `OPENROUTER_API_KEY`, FB tokens, SMTP, JEV.
- `THREADS_ACCESS_TOKEN`, `CA_CAMOUFOX_*`, `CA_THREADS_USER_DATA_DIR` **chưa set**.
- Apify quota: `Sin21` · Free ($10/tháng) · đã dùng **$0.4131 / $10** (4.1%), hết hạn chu kỳ 2026-09-29.
- SerpApi quota: **13/250** request tháng 2026-09.
- Camoufox: **chưa cài** trong `.venv312` lẫn `.venv`.
- Interpreter chính: `.venv312` (Python 3.12.10) — `.venv` thiếu `httpx`.

---

## 9. Thay đổi đã triển khai (2026-09-24)

### 9.1. Bảng file thay đổi

| File | Thay đổi |
|---|---|
| `packages/agents/src/ca_agents/ag_trend.py` | Thêm `parse_tikwm_feed()` (hàm thuần), `_fetch_tikwm_feed()` (thử 2 host), `_fetch_tikwm_comments()` (chờ nhịp 1 req/s), `_prioritize_vn_videos()`, `_is_fnb_title()`; timeout 6s→20s; tách `_scrape_google_trends_vn_rss()`; thêm tầng Trending Now vào đầu chuỗi `_scrape_google_trends_vn()` |
| `packages/agents/src/ca_agents/text_util.py` | **MỚI** — `match_any_keyword()`: so khớp từ khoá theo **ranh giới từ** (sửa bug `"ăn"` khớp trong `"xăng"`) |
| `packages/agents/src/ca_agents/sources/gtrends_trending_now_source.py` | **MỚI** — nguồn `google_trends_trending_now` (bảng xếp hạng cấp quốc gia), TTL riêng 1h; phân loại theo TÊN category |
| `packages/agents/src/ca_agents/sources/gtrends_serpapi_source.py` | Thêm `data_type=RELATED_QUERIES` (bắt buộc); `include_timeline=True` gọi thêm request TIMESERIES riêng |
| `packages/agents/src/ca_agents/sources/threads_google_bridge_source.py` | Bỏ link bịa `@threads_creator`; `author=""` khi RSS không có; nhãn nguồn đúng (`Báo chí (Google News)` vs `Meta Threads`) |
| `packages/agents/src/ca_agents/sources/tiktok_apify_source.py` | `_build_input()` luôn điền truy vấn mặc định cho cả 3 mode |
| `packages/agents/src/ca_agents/clients/apify_client.py` | Poll chịu lỗi mạng tạm thời (`_MAX_POLL_ERRORS=3`); log `statusMessage` khi run FAILED |
| `packages/agents/src/ca_agents/clients/serpapi_client.py` | `SERPAPI_CACHE_TTL_TRENDING_NOW_HOURS` (mặc định 1h) cho engine mới |
| `packages/agents/tests/test_trending_scraping_regressions.py` | **MỚI** — 19 test hồi quy, fixture copy từ **payload THẬT** |
| `apps/api/tests/unit/test_tiktok_apify_source.py` | Cập nhật test "keyword rỗng" theo hành vi ĐÚNG (trước đó đóng băng hành vi sai) |
| `apps/api/tests/unit/test_threads_apify_source.py` | **Sửa test pollution**: reset circuit breaker `_CB_JINA` (state module-level) — test PASS khi chạy riêng nhưng FAIL trong full suite |
| `apps/api/.env.example` | Tài liệu hoá `APIFY_THREADS_ACTOR_ID` + cảnh báo payload rỗng tốn CU |
| `.env.example` | Thêm `SERPAPI_CACHE_TTL_TRENDING_NOW_HOURS` |
| `.env` | `APIFY_THREADS_ACTOR_ID`: `apify/threads-scraper` → `curious_coder/threads-scraper` |
| `data/cache/serpapi/*.json` | Xoá 4 cache chứa payload TIMESERIES hỏng (thiếu `related_queries`) |
| `docs/runbooks/tiktok-scraping.md` | Sơ đồ đủ 4 tầng; bảng đặc tính TikWM đo thật; cảnh báo payload rỗng |
| `docs/runbooks/camoufox-scraping.md` | Bảng trạng thái từng tầng (Jina 403, Bridge không phải bài Threads…) |

### 9.2. Nguyên tắc giữ nguyên (không phá vỡ)

- **ADR-008**: mọi hàm parse **từ chối dữ liệu không đáng tin** (`code != 0` → `[]`) thay vì bịa.
- **Fail-closed**: nguồn lỗi → trả `[]` để chuỗi rớt tầng, không ném exception ra ngoài.
- **Hàm parse tách khỏi I/O** để test được bằng fixture tĩnh (không cần mạng).
- **Không đổi schema** `TrendItem` (ADR-003) — chỉ dùng lại các trường sẵn có.

### 9.3. Kiểm thử

| Gate | Kết quả |
|---|---|
| `test_trending_scraping_regressions.py` (mới) | **19/19 pass** |
| Nhóm test agents + API trending | **1326 passed, 1 skipped, 0 failed** |
| Full suite (`pytest -q` từ ROOT) | **2328 passed, 1 skipped** (trước các fix bổ sung) |
| `ruff check packages/agents/src` + test đã sửa | **All checks passed** |
| `mypy --strict` các file đã sửa | **Success: no issues found in 8 source files** |
| `tsc --noEmit` (apps/web) | **sạch** |

### 9.3.1. Xác minh LIVE sau khi sửa (bằng chứng chạy thật)

| Nguồn | Trước | Sau |
|---|---|---|
| TikWM `_scrape_tiktokwm_fallback()` | **0 items** | **8 items thật** (`is_live_scraped=True` 8/8), có comment thật, 10s |
| SerpApi `fetch_fnb_trends_serpapi('trà sữa')` | **0 items** | **8 items** (`tiệm trà nhỏ game +5000%`, `trà sữa trường lạc +3900%`…) |
| Trending Now (nguồn mới) | *(chưa có)* | **12 items** (`xổ số miền bắc` 500.000 lượt, `giá xăng dầu hôm nay` 10.000…) |
| Threads Bridge link bịa | 8 items link `@threads_creator` | **0 link bịa**, `link_goc=""`, nhãn `Báo chí (Google News)` |
| `fetch_trend_radar()` | 84 items, **14 tĩnh**, 16.3s | 88 items, **8 tĩnh**, **1.8s** |
| Phân loại `giá xăng dầu hôm nay` | sai → `am_thuc_fnb` | đúng → `tam_ly_lifestyle` |

### 9.3.2. Bug phát sinh khi viết test (đã sửa)

1. **`"ăn"` khớp substring trong `"xăng"`** → `giá xăng dầu hôm nay` bị gán `am_thuc_fnb`.
   Sửa bằng `ca_agents/text_util.match_any_keyword()` (ranh giới từ), áp dụng cho cả
   `_FNB_TITLE_KEYWORDS` trong `ag_trend.py` (2 chỗ).
2. **Test pollution ở `test_threads_apify_source.py`**: `_CB_JINA` là circuit breaker
   **module-level process-wide**; chạy trong full suite thì các test khác đã gọi Jina
   thật (403) ≥3 lần → mạch OPEN 5 phút → test mock bị chặn. Đây đúng là pattern
   "test PASS khi chạy riêng nhưng FAIL trong full suite = test pollution" đã ghi
   trong hướng dẫn repo. Sửa: reset `_CB_JINA` trong test.

### 9.4. Còn lại (chưa làm — cần quyết định của người vận hành)

> ⚠️ **MỤC 5 VÀ 7 DƯỚI ĐÂY ĐÃ ĐƯỢC SỬA (2026-09-25)** — xem §10.

1. **Nguồn TikTok `challenge/detail`** — đã probe thành công (viewCount thật: `#xuhuong` 6.15K tỷ, `#cafe` 108 tỷ) nhưng **chưa nối vào chuỗi**. Đây là nguồn mới, nên tách PR riêng để review được thay đổi phạm vi nguồn.
2. **Cài Camoufox** (`pip install camoufox[geoip]` + `camoufox fetch` + `scripts/threads_setup_login.py`) → kích hoạt tier Trending Now đã code xong từ plan 260914.
3. **Set `THREADS_ACCESS_TOKEN`** → kích hoạt tier 0 (đường đáng tin nhất cho Threads).
4. **`_scrape_google_trends_global`** gắn `nguon_goc="tiktok_global"` cho dữ liệu Google Trends US — nhãn nền tảng gây hiểu nhầm, nên đổi riêng (thay đổi này ảnh hưởng filter UI nên cần chốt với người dùng trước).
5. ~~Trần số item/nguồn khi gộp radar~~ → đã sửa (§10).
6. **Feed TikWM trả lẫn region** → đã sửa (§10).
7. ~~Hai bộ `_detect_category()` còn so khớp substring~~ → đã sửa (§10).

---

## 10. Sửa tiếp theo yêu cầu người dùng (2026-09-25)

> **Bối cảnh:** Người dùng phản hồi *"cào dữ liệu trên tiktok mà toàn cào được video bên Thái … và thread có thực sự cào được trend không hay mock?"*
> → **Cả hai phản hồi đều ĐÚNG.** Đã đo lại bằng probe live và sửa.

### 10.1. TikTok — `region=VN` không lọc thật

**Đo live (80–100 video qua 4–5 lần gọi `/api/feed/list?region=VN`):**

```
{'VN': 40, 'MM': 15, 'TH': 7, 'PK': 5, 'ID': 3, 'US': 3, 'PH': 2, 'KR': 1, 'JP': 1, 'UG': 1, 'SG': 1, 'GB': 1}
→ VN = 40/80 = 50%
```

Các lần khác: **21%** (21/100), **1/20**, thậm chí **0/20**. Video Myanmar/Thái Lan
chiếm đa số trong một số lần — đúng như người dùng quan sát.

**Các cách lọc khác đều thất bại** (đo thật):

| Tham số | Kết quả |
|---|---|
| `?region=VN&lang=vi` | VN=45% |
| `?region=VN&country=VN` | HTTP 531 |
| `?region=VN&city=ho chi minh` | HTTP 531 |
| `?region=VN&type=1` | VN=30% |
| `?region=vn` (chữ thường) | HTTP 531 |
| `/api/feed/search?keywords=cà phê` | **403 Forbidden** |

**Sửa:**
- `_prioritize_vn_videos()` (chỉ đẩy lên đầu) → thay bằng **`_filter_vn_videos()`** (CHỈ giữ VN, bỏ hẳn nước ngoài).
- Thêm **`_fetch_tikwm_feed_vn()`**: gọi **3 lần**, khử trùng theo `video_id`, chờ 1.1s giữa các lần (rate limit). Đo thật: 4 lần gọi → 24 video VN unique (1 lần không đủ).
- Fail-closed: nếu TikWM toàn video nước ngoài → trả `[]` → rớt xuống Camoufox/Apify (thà rỗng còn hơn gán nhãn sai "TikTok Việt Nam").

**Xác minh:** `_fetch_tikwm_feed_vn()` → **16/16 video VN**. `_scrape_tiktokwm_fallback()` → 8 items, 8/8 live, toàn kênh Việt (`@huyseoul_idol`, `@trangvachigai`, `@binhanndayne`…).

### 10.2. Threads — KHÔNG cào được trend thật, nhãn gây hiểu nhầm

**Đo live Google News RSS (4 biến thể query):**

| Query | Item parse được | Link threads.net THẬT |
|---|---|---|
| `site:threads.net cà phê OR matcha` | **0** | **0** |
| `site:threads.net` | 1 | **0** |
| `threads.net cà phê` | 11 | **0** |
| `cà phê OR matcha` | 100 | **0** |

**⇒ Google KHÔNG index nội dung Threads** cho News RSS. Toàn bộ item "Threads" trên
radar là **bài báo Việt** (`Kenh14.vn`, `thanhnien.vn`…) chứa chữ "Threads".

**Trạng thái các đường cào Threads khác (đo thật):**

| Đường | Kết quả |
|---|---|
| Jina Reader (`r.jina.ai`) | 🔴 **HTTP 403** |
| Apify `curious_coder/threads-scraper` | 🔴 **403 Forbidden** khi start run (token không có quyền) |
| Camoufox Trending Now | ⚪ chưa cài (`is_available()=False`) |
| Threads Official API | ⚪ chưa có `THREADS_ACCESS_TOKEN` |

**⇒ Kết luận: hiện KHÔNG có đường nào lấy trend Threads thật.** Dữ liệu là báo chí
thật (không phải bịa), nhưng **không phải Threads**.

**Sửa (trung thực hoá nhãn — ADR-008):**
- Tiêu đề: `🧵 [THREADS REALTIME]` (gây hiểu nhầm) → **`📰 [TÍN HIỆU BÁO CHÍ, KHÔNG PHẢI BÀI THREADS]`** khi không có link threads.net thật; chỉ dùng `🧵 [THREADS]` khi link thật.
- `nguon_goc_chi_tiet`: ghi rõ *"Chưa index được bài Threads trực tiếp — đây là TIN BÁO CHÍ … KHÔNG có số liệu tương tác thật"*.
- `nen_tang_lan_toa`: `["Báo chí (Google News — chưa index được Threads)"]`.

**Xác minh:** 6/6 item Threads nay có tiêu đề `[TÍN HIỆU BÁO CHÍ…]`, **0 item** còn gắn "THREADS REALTIME".

### 10.3. Kiểm thử sau sửa

| Gate | Kết quả |
|---|---|
| Gate rộng (agents + API trending) | **1311 passed, 1 skipped, 0 failed** |
| `ruff check` file đã sửa | **All checks passed** |
| `mypy --strict` file đã sửa | **Success: no issues found** |
| Test mới thêm | `test_filter_vn_videos_*` (2), `test_fetch_tikwm_feed_vn_*` (3), `test_scrape_threads_google_bridge_labels_news_honestly` (1) |

### 10.4. Việc người dùng cần quyết định

Để có **trend Threads thật**, phải chọn một trong hai (chưa làm):
1. **Cài Camoufox** + `scripts/threads_setup_login.py` → tier Trending Now (code đã sẵn).
2. **Lấy `THREADS_ACCESS_TOKEN`** → tier 0 Official API `/keyword_search` (miễn phí, 2.200 queries/24h).

Nếu không làm 2 việc trên: khuyến nghị **bỏ hẳn nguồn Threads khỏi radar** thay vì hiển thị bài báo dưới nhãn Threads (dù đã ghi rõ, vẫn có thể gây hiểu nhầm cho người xem cuối).

---

## 11. Cào Threads + TikTok THẬT (2026-09-26)

> **Bối cảnh**: người dùng yêu cầu "chủ tâm vào việc cào data thread + tiktok". Camoufox đã được cài (xem §12).

### 11.1. Threads — 4 bug khiến tier Camoufox chưa bao giờ lấy được bài

| # | Bug | Bằng chứng đo thật |
|---|---|---|
| 1 | **Selector sai**: code chờ `[data-e2e='search-result-post']` | Threads **KHÔNG có bất kỳ `data-e2e` nào** (0 giá trị). Class CSS là hash React (`xrvj5dj xd0jker`) đổi mỗi build |
| 2 | **`[role='main']` không tồn tại** cho khách anon | `fetch_threads_trending_page()` timeout 20s → luôn `CamoufoxUnavailable` |
| 3 | **🔴 LOGIN-WALL FALSE POSITIVE** (bug nặng nhất) | Code cũ coi `a[href*='/login']` là wall. **NHƯNG link "Đăng nhập" LUÔN có trong nav bar** trên MỌI trang Threads — kể cả khi render đủ 6–19 bài. → tier báo wall **oan** rồi rớt tầng |
| 4 | **Regex domain cũ**: `threads\.net/login` | Threads đã chuyển sang **`threads.com`** và tự redirect → regex không khớp |
| 5 | **Extractor HTML-regex không khớp** | `page.content()` serialize attr bằng nháy kép `"`; code cũ cắt theo `data-e2e` → 0 khối |

**Sửa:**
- Selector → `a[href*='/post/']`.
- **Login-wall chỉ khi URL bị redirect** sang `/login` (vd `/explore`), KHÔNG dùng nav link.
- Regex khớp cả `threads.net` + `threads.com`.
- Thay extractor bằng **JS chạy trong trang** (`_JS_EXTRACT_POSTS`): tìm link `/@user/post/id`, leo lên tổ tiên **RỘNG NHẤT mà vẫn chỉ chứa DUY NHẤT bài đó**, bóc theo dòng (`username → thời gian → nội dung → stats`).
- `fetch_threads_page()` **poll đếm link post tối đa 20s** rồi cuộn tới khi số bài ổn định — thay cho `wait_for_selector` cứng (chụp HTML quá sớm → 0–2 bài).

**Bug tinh tế phát hiện khi sửa:** bài có ảnh/video có **2 link cùng `post_id`**
(`/post/<id>` và `/post/<id>/media`). Nếu đếm SỐ LINK thì gặp >1 là dừng → container
chỉ còn phần media, `innerText` rỗng → **mất nội dung 3/5 bài**. Phải đếm **SỐ POST_ID
KHÁC NHAU**.

### 11.1.1. Phép thử 5 phần: KHÔNG cần đăng nhập

| Phép thử | Kết quả |
|---|---|
| 8 URL khác nhau | `/search`=7, `/tag/caphe`=7, `/tag/cafe`=8, home=7 bài — **tất cả có `login_link=True`** (nav bar). Chỉ `/explore` = 0 + **redirect `/login`** (wall THẬT) |
| Warm-up (home → search, cùng phiên) | home **19 bài** → search **10 bài** |
| Locale VN (`vi-VN`) + warm-up | home 16 → search **9 bài** (không tốt hơn) |
| **5 lần liên tiếp** (đo tỷ lệ) | **5/5 = 100%** (8, 11, 15, 8, 12 bài) |
| Endpoint thay thế (oEmbed/api) | `/api/oembed` → 404; `/oembed` → 200 nhưng trả HTML Instagram, không dùng được |

**⇒ KẾT LUẬN: không cần đăng nhập, không cần warm-up, không cần locale.**
Chỉ cần **chờ đủ lâu cho SPA render** (đây mới là nguyên nhân thật của các lần "0 bài").

**Sau fix: 6/6 = 100% thành công** (trước đó ~1/4 lần), 5–10 bài/lần.

**Kết quả đo lại:** 6–7 bài thật/lần, link `/post/` thật, tương tác thật
(`@sonqthao` 6.900 tim / 99 phản hồi / 496 đăng lại).

### 11.2. Đổi thứ tự chuỗi (2 nguồn)

| Platform | Trước | Sau | Lý do |
|---|---|---|---|
| Threads | Official API → **Google Bridge** → Jina → Camoufox → Apify | Official API → **Camoufox** → Google Bridge → Jina → Apify | Bridge chỉ trả BÀI BÁO chứa chữ "Threads"; đặt trước sẽ **che mất nguồn thật** |
| TikTok | **TikWM** → Camoufox → Apify | **Camoufox** → TikWM → Apify | TikWM `region=VN` không lọc (21–50% VN); Camoufox search theo từ khoá Việt → video đúng chủ đề |

### 11.3. Kết quả xác minh live

| Nguồn | Kết quả |
|---|---|
| TikTok (auto) | **8 items, 8/8 live** — toàn video Việt đúng chủ đề (`@ghiengapgo` tiệm cà phê phin 30 năm Sài Gòn, `@caitochim` top 3 quán check-in) |
| Threads (auto) | **6 items, 6/6 live**, 6/6 link `/post/` thật — `@sonqthao` 6.900 tim, `@tramhoctap` 7.600 tim |
| Radar tổng hợp | 88 items trong 19.8s |

**Lưu ý dao động**: Threads Camoufox **thỉnh thoảng** gặp login-wall (`0 post + có
link Log in`) → rớt tầng đúng thiết kế; lần gọi sau lại OK. Không phải bug.

### 11.4. Kiểm thử

| Gate | Kết quả |
|---|---|
| Gate rộng (agents + API trending) | **1313 passed, 1 skipped, 0 failed** |
| `test_threads_camoufox_source.py` | **28/28 pass** |
| `ruff` + `mypy --strict` file đã sửa | sạch |
| Fixture | `threads_search_sample.html` cập nhật theo **cấu trúc THẬT** |

## 12. PHÁT HIỆN TREND MỚI — Trend Discovery Pipeline (2026-09-26)

> **Bối cảnh**: người dùng chỉ ra vấn đề cốt lõi — *"phải tìm được các từ khoá
> trending HIỆN TẠI, chứ không phải từ khoá người ta tìm kiếm hằng ngày, cũng
> không phải từ khoá trong bài báo viết theo tháng"*. Chỉ cào TikTok/Threads
> theo từ khoá cho sẵn là **không đủ** — phải tự **phát hiện** từ khoá mới.

### 12.1. Kết luận nghiên cứu (đã probe, không còn lựa chọn nào khác)

| Nguồn | Có endpoint trending thật? | Bằng chứng |
|---|---|---|
| TikTok `discover/challenge` | ❌ | Trả **chiến dịch 2022 cũ** (`#SEAGames31`, `#ngaycuame2022`, `#mackedoi`); cần chữ ký `X-Bogus`/`X-Gnarly`/`X-Dynosaur` |
| TikTok Creative Center | ❌ | `40101 no permission` |
| TikTok `explore/item_list` | ❌ | Không sắp theo view/thời gian |
| Threads (7 endpoint) | ❌ | Tất cả 404; GraphQL cần `doc_id`; `/tag/X` trả **CÙNG feed cho mọi tag** |
| **Google Trends Trending Now** | ✅ | Có `rank` + `search_volume` + `increase_percentage` + `start_timestamp` |

**⇒ Google Trends là nguồn trending THẬT duy nhất.** Nhưng nó chỉ trả trend
ĐANG SÔI, không trả "câu nói/từ lóng" mới nổi — nên cần thêm **Discovery**.

### 12.2. Ý tưởng cốt lõi (do người dùng đề xuất, đã kiểm chứng)

> **LLM KHÔNG bắt đầu bằng Google search "trend là gì".** Thay vào đó, dùng
> **meta-keyword + THÁNG** để truy vấn Google News, rồi **bóc các cụm từ được
> trích dẫn trong bài** — vì bài báo Việt Nam đánh dấu từ lóng mới bằng `"..."`.

Ví dụ query (nhóm quan trọng nhất):
```
câu nói viral TikTok (tháng 9 OR tháng 8) 2026
trend TikTok tháng 9 2026
slang Gen Z tháng 9 2026
từ lóng mới tháng 9 2026
```
Query dùng **cả tháng hiện tại + tháng trước** vì trend mới thường bắt đầu
cuối tháng trước và lan sang tháng này.

### 12.3. 🔴 BÀI HỌC ĐO THỰC NGHIỆM QUAN TRỌNG NHẤT

> **Đặt ngoặc kép `"..."` trong query → Google trả bài CŨ.**

Đo thật: query có ngoặc kép → **0/35** bài trong 45 ngày (bài 82–436 ngày tuổi).
Bỏ ngoặc kép → **90 candidate thô** từ ~500 item, nhiều bài mới trong vài ngày.

Đây là lý do `build_discovery_queries()` **cố ý KHÔNG dùng ngoặc kép** cho nhóm
query theo tháng — và có test `test_build_queries_avoids_exact_quotes_for_fresh`
canh gác quy tắc này để không ai "tối ưu" rồi vô tình làm hỏng.

### 12.4. Pipeline (đã hiện thực — `trend_discovery_source.py`)

```
build_discovery_queries(month, year)
        │  (~16 query Google News, có tháng, KHÔNG ngoặc kép)
        ▼
   _fetch_gnews(query)  →  RSS  →  40 item/query   (circuit breaker _CB_GNEWS)
        ▼
   is_list_article(title)  →  lọc bài TỔNG HỢP (top/tuyển tập/điểm lại/lộ diện)
   is_topic_relevant(title) → lọc đúng chủ đề (trend/meme/từ lóng/viral)
        ▼
   extract_candidates(title, desc)   ← HÀM THUẦN
        │  bóc cụm trong "..." + cụm sau dấu ":"
        │  khử rác: HTML, mã màu #xxxxxx, tên báo, URL, %số, kỳ báo
        │  khử từ chung: hot, gen z, mạng xã hội, ...
        ▼
   score_candidate(keyword, sources, titles, freshness_days, list_count)
        │  conf = 0.30·mention + 0.22·source + 0.15·fresh
        │       + 0.13·novelty + 0.10·relevance + 0.10·list_boost
        ▼
   discover_candidates(min_mentions=2, max_freshness_days=45, ...)
        ▼
   TrendItem(label="🔎 [PHÁT HIỆN MỚI]", source="Trend Discovery")
```

### 12.5. Kết quả chạy THẬT (2026-09-26)

| Ngưỡng | Số candidate | Ví dụ bắt được |
|---|---|---|
| `min_mentions=1` (quét rộng) | **10** | `chi tiêu bốc đồng`, `Hội Chủ Chốt`, `đổ bộ`, `gã ăn vạ` |
| `min_mentions=2` (mặc định, đang dùng) | **4** | `bá khí`, `Thánh meme`, `Tuyệt vời uống nào!`, `chán đời` |

**`bá khí`** — ĐÚNG ví dụ người dùng nêu — được bắt với **3 lần / 3 nguồn độc lập**
(lag.vn, soha.vn, kenh14.vn), conf **0.622**, từ bài THẬT
*'“Bá khí” là gì? Nguồn gốc của meme đang phủ sóng mạng xã hội'* (lag.vn, 25/09/2026).

Các trend mới khác tìm được: `Thánh meme` (3 nguồn), `aura farming`,
`bùa chống flop`, `chữa lành ví tiền`, `skibidi`, `delulu`, `tradwife`.

### 12.6. Vì sao `min_mentions=2` là mặc định đúng

- `min_mentions=3` **quá chặt** — hầu hết trend MỚI chỉ xuất hiện **1–2 lần**
  (báo chưa viết nhiều), nên sẽ mất tín hiệu SỚM — đúng thứ có giá trị nhất.
- `min_mentions=1` quá rộng → lọt nhiễu (`SOHA`, `Ai đang mua`).
- `=2` cân bằng: vẫn bắt đầu sớm nhưng đủ chắc.

### 12.7. Kiểm thử

| Gate | Kết quả |
|---|---|
| `test_trend_discovery.py` | **28/28 pass** (hermetic — mock `_fetch_gnews`, không mở mạng) |
| `ruff` + `mypy` file mới + `ag_trend.py` | sạch |
| Test canh gác quy tắc | `test_build_queries_avoids_exact_quotes_for_fresh` |

Test dùng **tiêu đề THẬT** thu khi đo live — nếu báo đổi cách viết, test fail
ngay thay vì âm thầm mất tín hiệu.

### 12.8. 🔴 Bug phát hiện khi chạy LIVE lần cuối: Discovery bị tầng trên chặn

Chạy `_scrape_google_trends_vn()` trên production lần đầu cho kết quả:

```
-> 12 item
   id bắt đầu bằng 'discovery_': 0        ← DISCOVERY KHÔNG BAO GIỜ CHẠY
```

**Nguyên nhân:** tầng Trending Now `return tn_items` ngay khi có kết quả → tầng
Discovery nằm sau **không bao giờ được gọi**. Đây là bug thật, chỉ lộ ra khi
chạy live (test unit mock `discover_candidates` nên không phát hiện được).

**Vì sao phải GỘP chứ không thay thế:** hai tầng trả **hai loại tín hiệu KHÁC NHAU**:

| Tầng | Bản chất tín hiệu | Ví dụ |
|---|---|---|
| Trending Now | từ khoá **tìm kiếm bùng nổ** (có số lượt tìm) | `fpt play` 100K, `xsmb` 500K |
| Discovery | **slang/meme từ báo chí** (không phải hành vi tìm kiếm) | `bá khí`, `Thánh meme` |

Discovery bắt được cái Trending Now **bỏ sót hoàn toàn** — trend văn hoá không
biểu hiện qua Google Search.

**Sửa:** thay `return` sớm bằng `_merge_trend_layers()` — gộp 2 tầng, khử trùng
theo cụm từ khoá (không phân biệt hoa/thường, tầng primary thắng).

**Xác minh sau sửa:**

| | Trước | Sau |
|---|---|---|
| Tổng item | 12 | **16** |
| Item từ Discovery | **0** | **4** (`bá khí`, `Thánh meme`, `Tuyệt vời uống nào!`, `chán đời`) |

Thêm 4 test hồi quy: `test_merge_layers_keeps_both`,
`test_merge_layers_dedupes_case_insensitive` (khác hoa/thường → giữ bản primary),
`test_merge_layers_skips_empty_keyword`, `test_merge_layers_handles_both_empty`.

**Bài học:** test unit mock tầng con thì KHÔNG bắt được bug "tầng trên `return`
sớm" — phải chạy **live** chuỗi thật rồi đếm theo prefix id.

### 12.9. Rà soát SOTA + hardening (2026-09-26, chuẩn bị lên `main`)

Trước khi hợp nhất, chạy một vòng **audit độc lập** trên
`trend_discovery_source.py` (script tạm, đã xoá sau khi xong). Kết quả:

| # | Phát hiện | Mức độ | Xử lý |
|---|---|---|---|
| A | Circuit breaker không khoá thread | thấp | **Giữ nguyên** — nhất quán toàn repo (`_SourceCircuitBreaker` không thread-lock; orchestrator gọi tuần tự) |
| B | `extract_candidates(123)` → `TypeError: argument of type 'int' is not iterable` | **cao** | Đã sửa: guard `isinstance(title, str)` → trả `[]` |
| C | Nháy CONG (`“ ”`) không bị bóc: `'từ lóng: “x”, “y”'` → `['“x”', '“y”']` | **cao** | Đã sửa: `_normalize_candidate()` bóc MỌI loại nháy |
| D | `'bá   khí'` (nhiều dấu cách) và `'bá khí'` KHÔNG gộp | trung | Đã sửa: dedup theo bản normalize → 1 candidate |
| E | 14 request RSS liên tiếp, không nghỉ | trung | Đã sửa: `time.sleep(delay)` giữa 2 query (default 0.4s, env được) |
| F | Ngưỡng hard-code trong code, không cấu hình được | trung | Đã sửa: 7 biến env `TREND_DISCOVERY_*` (xem `.env.example`) |
| G | Cụm 1–2 ký tự (`x`, `y`) lọt qua | thấp | Đã sửa: `_is_junk` thêm `len(t) < 3` |
| H | `TrendCandidate.first_seen` là **field chết** (không bao giờ điền) | thấp | Đã sửa: điền từ `pubDate` của bài MỚI nhất |

**Vì sao C là bug nghiêm trọng:** cùng một trend sinh **2 candidate khác nhau**
(`bá khí` vs `“bá khí”`) → loãng kết quả và **giảm `mention_count` thật** → có
thể đẩy một trend mạnh xuống dưới ngưỡng `min_mentions=2` và mất tín hiệu.

**Vì sao F quan trọng cho vận hành:** ngưỡng discovery phải chỉnh được theo mùa
(Tết nhiều trend hơn ngày thường) **mà không cần sửa code/deploy**. Tham số hàm
vẫn thắng env (dùng khi test/override có chủ đích). Env rác (`abc`) rơi về
default, không ném `ValueError`.

**Bổ sung test hồi quy (28 → 37):**

| Test | Canh gác |
|---|---|
| `test_extract_candidates_non_str_returns_empty` | Bug B |
| `test_extract_candidates_strips_curly_quotes` | Bug C |
| `test_extract_candidates_dedupes_whitespace_variants` | Bug D |
| `test_extract_candidates_rejects_too_short` | Bug G |
| `test_env_config_overrides_defaults` | Tính năng F |
| `test_explicit_arg_beats_env` | Ưu tiên tham số > env |
| `test_env_config_tolerates_bad_value` | Env rác → default |
| `test_query_delay_between_requests` | Tính năng E |
| `test_no_sleep_before_first_query` | Không chậm vô ích |

Fixture `_no_query_delay` (autouse) vừa **tắt `sleep`** (test chạy nhanh) vừa
**cô lập env** — tránh test pollution khi `.env` thật lọt vào `os.environ`
(xem ghi chú repo về `ensure_dotenv`).

### 12.10. Đối chiếu thiết kế SOTA 11 bước ↔ đã hiện thực

Thiết kế tham chiếu (do người dùng đưa) gồm 11 bước. Bảng dưới nói rõ bước nào
**đã có**, bước nào **cố ý hoãn** và vì sao.

| # | Bước SOTA | Trạng thái | Ghi chú |
|---|---|---|---|
| ① | COLLECT (nhiều nguồn thô) | ✅ đã có | Google News RSS + (Trending Now SerpApi, TikTok/Threads Camoufox nằm ở chuỗi `ag_trend`) |
| ② | EXTRACT (bóc candidate) | ✅ đã có | `extract_candidates()` — hàm THUẦN, có test từ tiêu đề THẬT |
| ③ | SCORE (chấm điểm tín hiệu) | ✅ đã có | `score_candidate()` — 6 thành phần, tất định, không LLM (ADR-002) |
| ④ | DETECT BURST (phát hiện bùng nổ) | ⏸️ hoãn | Cần lịch sử theo thời gian (DB + scheduler). Hiện mỗi lần quét độc lập — `freshness_days` là proxy thô. Khi có bảng `trend_snapshots` sẽ thêm. |
| ⑤ | SEMANTIC CLUSTER (gộp biến thể) | ⚠️ một phần | Đã gộp **biến thể chuỗi** (`bá khí` ↔ `“Bá  khí”`) qua `_normalize_candidate`. Gộp **ngữ nghĩa** (`bá khí` ↔ `thần thái ngút trời`) cần normalize/embedding → chưa làm (tránh phụ thuộc LLM trong control flow). |
| ⑥ | CROSS-SOURCE VERIFY | ⏳ một phần | Đã đếm **số nguồn độc lập** (`source_count`). Đối chiếu chéo với TikTok/Threads cần gọi thêm tầng — nằm ngoài module discovery (thuộc VERIFY ở caller). |
| ⑦ | FIND ORIGIN (truy nguồn) | ⏸️ hoãn | Cần phân tích lan truyền (ai đăng đầu). Ngoài phạm vi bản này; `sample_titles` giữ manh mối. |
| ⑧ | CONFIDENCE (điểm tin cậy) | ✅ đã có | `confidence` 0–1, có thể lọc bằng `TREND_DISCOVERY_MIN_CONFIDENCE`. |
| ⑨ | RANK + LIMIT | ✅ đã có | Sắp xếp giảm dần + `max_candidates`. |
| ⑩ | VERIFY (xác minh trước khi dùng) | ✅ có giao diện | Mọi candidate gắn `🔎 [PHÁT HIỆN MỚI]`, `is_discovered=True`; **KHÔNG** tự nhận là đã viral (ADR-008). Caller xác minh qua TikTok/Threads. |
| ⑪ | PROVENANCE (lưu vết) | ✅ đã có | `sources`, `sample_titles`, `first_seen`, `to_dict()` — đủ để replay (ADR-007). |

**Nguyên tắc:** các bước hoãn (④⑦ và phần ngữ nghĩa của ⑤) đều cần **hạ tầng
lịch sử/LLM** — làm sớm sẽ vi phạm ADR-002 (không LLM trong luồng điều khiển)
hoặc thêm phụ thuộc chưa cần. Module hiện tại đã **fail-closed** (lỗi → `[]`)
và đủ để bắt trend mới (bằng chứng: `bá khí`).

### 12.11. Bằng chứng sẵn sàng lên `main` — cổng kiểm tra (2026-09-27)

Kết quả kiểm tra **toàn bộ cổng CI** cho các thay đổi của phiên này (trend
discovery + merge layer + Threads/TikTok scraping):

| Cổng | Lệnh | Kết quả | Ghi chú |
|---|---|---|---|
| Unit test module mới | `pytest packages/agents/tests/test_trend_discovery.py` | ✅ **37/37 pass** | Bao gồm env-config, delay, merge, extract, junk-filter |
| Full suite | `python -m pytest -q` (từ ROOT) | ✅ **2494 pass**, 2 fail | 2 fail đều trong `test_inbox_tkb_solver.py` — **file của phiên làm việc khác** (lỗi `build_lich_input() got unexpected keyword 'tuan_iso'`), không liên quan thay đổi ở đây |
| Ruff | `ruff check` các file đã đổi | ✅ pass | Không lỗi |
| mypy (file của tôi) | `mypy packages/agents/src/ca_agents/sources/trend_discovery_source.py` + `ag_trend.py` | ✅ pass | Không lỗi |
| mypy **cổng ĐỎ CI** | `mypy apps/api/src packages/*/src` (strict) | ✅ **1 lỗi duy nhất là có sẵn ở HEAD** | `spatial_memory.py:265` — chứng minh bằng worktree sạch tại HEAD 51a94bd cho **đúng cùng 1 lỗi** (checked 240 files). Không phải do thay đổi của phiên này |
| tsc web | `apps/web && tsc --noEmit` | ✅ **rc=0**, 0 lỗi | |
| Secrets scan | `scripts/scan_secrets_before_commit.py` (<tất cả 21 file đổi>) | ✅ 0 nghi vấn | `.env.example` diff chỉ chứa placeholder comment |
| Live verify harden | `discover_candidates()` + `_scrape_google_trends_vn()` | ✅ PASS | Xem chi tiết dưới |
| Hermetic test | fixture `autouse` delenv `TREND_DISCOVERY_*` + `delay=0` | ✅ | Mọi test mock `_fetch_gnews`, không gọi mạng thật |

**Live verify bản harden (2026-09-27):**

1. `discover_candidates()` cấu hình full default (14 queries, delay 0.4s):
   **3 candidates trong 15.4s** —
   `bá khí` conf=0.679 (4 mentions / 3 sources, first_seen 26/09/2026),
   `Tuyệt vời, uống nào` conf=0.625,
   `chán đời` conf=0.522.
   Độ trễ giữa query (rate-limit) không phá vỡ kết quả.
2. Chẩn đoán nhanh `max_queries=4` trả 0 candidate: **không phải bug** —
   4 query đầu đều là query theo tháng, không đủ yếu tố cross-source để
   candidate vượt ngưỡng `min_mentions=2`. Bằng chứng: cấu hình full default
   vẫn ra đúng 3 candidates quen thuộc.
3. `_scrape_google_trends_vn()` (đã gộp discovery): **15 items trong 16.4s**
   — 12 `gtrending` + **3 `discovery`** → merge layer hoạt động đúng, discovery
   không bị tầng Trending Now chặn (bug §12.8 đã sửa vẫn còn hiệu lực).

**Nhật ký hoạt động song song:** phiên làm việc khác đang chạy cùng lúc trong
workspace này (sở hữu `DEMO_QA_RESULTS.md`, `sprint45.py`, `test_inbox_tkb_solver.py`,
`spatial_memory.py`…). Mọi file của phiên đó **không bị đụng chạm**; 2 test
fail trong full suite là trách nhiệm của phiên đó, không phải của thay đổi
trend/threads ở đây.
