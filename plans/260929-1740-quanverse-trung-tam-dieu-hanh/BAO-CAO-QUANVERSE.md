# BÁO CÁO — Quánverse thành Trung tâm Điều hành Quán

- **Kế hoạch**: `260929-1740-quanverse-trung-tam-dieu-hanh`
- **Ngày thực hiện**: 2026-09-29
- **Nhánh**: `main` (đã push) · `fa4b05f..8631122`
- **9 commit** (6 tính năng + 3 fix CI): `fd1f7a6` → `8631122`

---

## 1. Các file đã thay đổi

### Thêm mới (backend)

| File | Nội dung |
|---|---|
| `apps/api/src/ca_api/interfaces/http/quanverse_fixtures.py` | Ba route mock chỉ-đọc, ba kịch bản, `include_in_schema=False`. **Tên file KHÔNG được là `test_*.py`** — xem §7.6 |
| `apps/api/tests/unit/test_quanverse_test_api.py` | 19 test: hình dạng, tính nhất quán, ẩn khỏi OpenAPI |

### Thêm mới (frontend)

| File | Nội dung |
|---|---|
| `apps/web/src/ui/experience/quanverse/quanverse-contract.ts` | `QuanverseViewModel` + quy ước `null`/`0` + `formatSo`/`soHoacNull` |
| `.../quanverse/quanverse-contract.test.ts` | 32 test quy ước số |
| `.../quanverse/repository/types.ts` | Interface `QuanverseRepository` |
| `.../quanverse/repository/mappers.ts` | Bộ chuẩn hoá dùng chung (thuần) |
| `.../quanverse/repository/mappers.test.ts` | 26 test đọc tên trường thật |
| `.../quanverse/repository/real.ts` | Adapter 6 nguồn, cô lập lỗi từng nguồn |
| `.../quanverse/repository/mock.ts` | Adapter mô phỏng |
| `.../quanverse/repository/mock-data.ts` | Ba kịch bản nhất quán nội bộ |
| `.../quanverse/repository/mock-data.test.ts` | 47 test tính nhất quán |
| `.../quanverse/repository/index.ts` | Factory + cổng an toàn production |
| `.../quanverse/ops/*.tsx` (10 file) | Tám khối + `kit.tsx` dùng chung |
| `apps/web/src/app/quanverse.css` | CSS riêng cho màn điều hành |
| `apps/web/vitest.config.ts` | Vitest (`environment: node`) |
| `apps/web/e2e/quanverse*.spec.ts` (5 file mới) | mô phỏng · dữ liệu thật · rỗng · route ẩn |

### Sửa

| File | Thay đổi |
|---|---|
| `apps/web/src/app/quanverse/page.tsx` | Viết lại: 485 → 220 dòng, vỏ mỏng |
| `apps/web/src/app/layout.tsx` | Đăng ký `quanverse.css` |
| `apps/web/src/app/AppShell.tsx` | Bỏ 4 mục nav; đổi nhãn `/quanverse` |
| `apps/web/src/lib/session.ts` | Bỏ 4 path khỏi `MANAGER_ONLY`/`KNOWN_PATHS`, 1 khỏi `STAFF_ACCESS`, bỏ nhánh route ma |
| `apps/web/next.config.js` | Thêm 4 redirect vĩnh viễn |
| `apps/web/src/app/experience.css` | Xoá 629 rule chết (**2110 → 283 dòng**) |
| `apps/web/package.json` / `tsconfig.json` | Thêm vitest; loại `*.test.ts` khỏi `tsc` |
| `apps/web/e2e/quanverse.spec.ts`, `quanverse-mobile.spec.ts`, `ui-audit.spec.ts` | Viết lại |
| `apps/api/tests/unit/test_capability_coverage.py` | 3 exclusion mới |
| `apps/api/tests/unit/test_qa_dot5_fixes.py` | Đổi path đã chết sang path còn thật |
| `.github/workflows/ci.yml` | Bước `Vitest (web unit)` ở job 01 |

### Xoá

- **4 route page**: `app/quanverse/{war-room,shift-rescue,rules,spatial-memory}/page.tsx`
- **3D (2 file)**: `LivingMap3d.tsx`, `LivingMap.tsx`
- **Bề mặt khách hàng (4 file)**: `GuestJourney`, `FlavorUniverse`, `PreferenceConsent`, `ArLiteOverlay`
- **Module mồ côi (13 file)**: `ui/experience/{war-room,shift-rescue,rules,spatial}/` (11), `Scene3d.tsx`, `useCapability3d.ts` — và `exp-kit.tsx`, `exp-present.ts`, `experience-api.ts`
- **Component cũ của Quánverse (9 file)**: `LivingMap2d`, `MemoryInline`, `PageAssistant`, `RoleProjection`, `quanverse-model.ts`, `living-plan.ts`, `ZoneDetail`, `ModeRail`, `HorizonTimeline`, `StationBoard`, `ForecastChart`
- **6 e2e spec cũ**: 4 spec của route đã rút + `grand-experience-replay` + `quanverse-assistant`

---

## 2. Các route đã ẩn / chuyển hướng

Bốn route chuyển hướng **vĩnh viễn (308)** về `/quanverse` — đã đo bằng `Invoke-WebRequest`:

```
/quanverse/war-room        → 308  location: /quanverse
/quanverse/shift-rescue    → 308  location: /quanverse
/quanverse/rules           → 308  location: /quanverse
/quanverse/spatial-memory  → 308  location: /quanverse
```

Điều hướng (`AppShell.tsx`) chỉ còn **một** mục Quánverse. Route ma `/quanverse/tour/<id>` (được `isKnownPath` whitelist nhưng **chưa bao giờ có file page**) đã bỏ khỏi whitelist.

`/quanverse` là **điểm vào duy nhất**. `next build` không còn entry route nào cho bốn path cũ.

---

## 3. Component đã xoá / loại khỏi Quánverse

| Nhóm | Component | Lý do |
|---|---|---|
| **3D** | `LivingMap3d`, `LivingMap` (vỏ 2 lớp), `Scene3d`, `useCapability3d` | Quánverse chỉ 2D/DOM. Nhánh 3D **chưa từng được test** (`hasRealWebGL()` từ chối SwiftShader → mọi e2e headless rơi vào nhánh 2D) |
| **Khách hàng** | `GuestJourney`, `FlavorUniverse`, `PreferenceConsent`, `ArLiteOverlay` | Mô hình hoá KHÁCH, không phải VẬN HÀNH. Backend vẫn sống |
| **Route phụ** | `ui/experience/{war-room,shift-rescue,rules,spatial}/` (11 file) | Không còn route nào trỏ tới; đã kiểm grep toàn `src/` |
| **Trợ giúp** | `exp-kit`, `exp-present`, `experience-api` | Không còn importer. `experience-api.ts` còn import `./war-room/war-room-model` (đã xoá) nên `next build` đỏ |
| **Trùng lặp** | `LivingMap2d`, `RoleProjection`, `quanverse-model.ts`, `living-plan.ts` | Bị khối `ops/OperationalMap2d` thay thế; `RoleId`/`ZoneUI` từng bị khai **3 lần** |
| **Đã gộp** | `ZoneDetail`, `ModeRail`, `HorizonTimeline`, `StationBoard`, `ForecastChart`, `MemoryInline`, `PageAssistant` | Chức năng nằm trong `ops/` + `repository/` |

**GIỮ NGUYÊN** (không phải component): package `three`, `@types/three`, `@react-three/fiber`, `@react-three/drei` — `ui/hom-nay/ops-pulse.tsx` (trang `/hom-nay`) vẫn cần.

**KHÔNG chạm backend** của bốn tính năng đã rút: router, agent, contract, fixture và 5 file pytest còn nguyên.

---

## 4. Hợp đồng dữ liệu mới

`apps/web/src/ui/experience/quanverse/quanverse-contract.ts`

```
QuanverseViewModel
├─ dataSource: "real" | "mock"        scenario / scenarioLabel
├─ role: khach|nhan_vien|quan_ly|chu_quan   (MÁY CHỦ cắt, client không tự lọc)
├─ header:      QuanverseStoreHeader   storeName · dateISO · shiftLabel
│                                      onShiftNames[] · onShiftCount · systemStatus · updatedAt
├─ kpis[]:      QuanverseKpi           6 ô: staff · zones · orders · queue · alerts · upcoming
├─ zones[]:     QuanverseZone          load · threshold · queue · assignedStaff · alerts[]
├─ actions[]:   QuanverseActionItem    severity · reason · source · at · ctaLabel · ctaHref
├─ timeline[]:  QuanverseTimelineItem  at · title · kind · source · status
├─ capacity:    QuanverseCapacity      points[] · hasHistory · daysOfData · peaks[]
├─ copilot:     QuanverseCopilot|null  headline · reasons[] · citations[] · grounded · provider
├─ events[]:    QuanverseEvent         typeLabel · occurredAt · sourceLabel · zoneLabel
├─ dataQuality[]: { code, level, message }
└─ provenance[]:  { label, endpoint, ok, status?, missingFields? }
```

### Quy ước số (bất biến, chốt bằng test)

```
null  = CHƯA CÓ DỮ LIỆU   → UI hiện "—"
0     = CÓ dữ liệu, bằng 0 → UI hiện "0"
```

Hai chốt duy nhất: `formatSo()` và `soHoacNull()`.

`soHoacNull` từ chối **mọi** kiểu không phải số — kể cả mảng và boolean, vì `Number([]) === 0` và `Number(true) === 1` đều là "0 giả" nếu lọt qua. Đồng bộ với quy ước đã dùng ở hợp đồng hao hụt (`ca_contracts/loss.py`).

### Trường KHÔNG có (vì backend không có)

- **`confidence`**: backend chỉ trả `grounded: boolean`, không có độ tin cậy dạng số. Hợp đồng không bịa thêm.
- **Nhân sự trong ca theo tên**: xem §9.

---

## 5. Mock mode hoạt động thế nào

### Phía backend — `/api/v1/test/quanverse/*`

```
GET /api/v1/test/quanverse/snapshot?scenario=
GET /api/v1/test/quanverse/stations?scenario=
GET /api/v1/test/quanverse/forecast?scenario=
```

Ba kịch bản: `binh_thuong` · `cao_diem` · `qua_tai_pha`.

- Trả **đúng khoá** của route thật → adapter thật/mock dùng chung một bộ đọc.
- **Nhất quán nội bộ** (chốt bằng test): `chi_so.don_dang_xu_ly` == tổng `tai` 4 khu vực; `don_hom_nay` == `dang_xu_ly + da_xong`; mọi `action` gắn khu vực phải trỏ tới khu vực có thật.
- Tự khai nguồn gốc: `nguon: "fixture_mock"` / `data_quality[].code == "fixture_mock"`.
- `include_in_schema=False` → **không phơi ra `/openapi.json`** (không phải hợp đồng sản phẩm).
- Không cần token, không đọc DB, không gọi LLM, không ghi.
- `?scenario=` sai → 404 `scenario_khong_ton_tai`.

### Phía frontend — `MockQuanverseRepository`

- Fixture TS (`mock-data.ts`) cùng ba kịch bản, trả **cùng** `QuanverseViewModel`.
- Dùng được cả khi **API tắt hoàn toàn** — đúng mục tiêu "demo ngay".
- `getQuanverseRepository()` là **cổng an toàn**: ở production, yêu cầu `mock` bị hạ xuống `real` thay vì báo lỗi.
- Bộ chọn nguồn **chỉ hiện** khi `NEXT_PUBLIC_QUANVERSE_DEMO=1` hoặc `NODE_ENV !== "production"`.

### Nhãn nguồn (câu hỏi "dữ liệu này thật hay mô phỏng?")

| Nguồn | Nhãn |
|---|---|
| Thật | `● Dữ liệu thật · Cập nhật 17:32` |
| Mô phỏng | `◉ Mô phỏng · Kịch bản: "Giờ cao điểm"` |

**Không dùng chữ "live"** — backend đọc theo yêu cầu, không đẩy realtime.

---

## 6. Real mode lấy dữ liệu từ API nào

`RealQuanverseRepository` ghép **sáu** nguồn đang có sẵn. Mỗi nguồn nằm trong `try/catch` **riêng**:

| Nguồn | Endpoint | Cung cấp |
|---|---|---|
| Bản chiếu vận hành | `GET /api/v1/experience/quanverse/snapshot?replay_role=` | zones · events · next_horizon · role · data_quality |
| Tải theo khu vực | `GET /api/v1/experience/quanverse/stations` | tải · hàng chờ · `chi_so` (**đọc đơn THẬT**) |
| Dự báo nhu cầu | `GET /api/v1/experience/quanverse/forecast` | chuỗi 16 giờ (**lịch sử đơn THẬT**) |
| Tóm tắt cho AI | `GET /api/v1/experience/quanverse/brief/living_map` | headline · facts · risks · next_actions · grounded_refs |
| Phân công tuần | `GET /api/v1/lich-tuan` | suy **tên** nhân sự đang trực |
| Việc và cảnh báo | `GET /api/v1/hom-nay` | `canh_bao_ton` · `treo_preview` · `viec_cho_toi` |

Gọi song song (`Promise.all`). Nguyên tắc chịu lỗi:

- Một nguồn hỏng ⇒ trường của nó `null`/`[]`, ghi vào `provenance[]` với `ok:false`, thêm một mục `dataQuality` mức `warning`.
- Trang **không sập** và **không hiện 0 giả**.
- Khối `ProvenancePanel` liệt kê endpoint lỗi + trường thiếu.

Không dựng API trùng lặp. Không ghi gì. Không gọi LLM cho phần số.

---

## 7. Test đã chạy

| Cổng | Kết quả |
|---|---|
| **pytest** (toàn bộ, từ ROOT) | **2716 passed, 33 failed, 1 skipped** — *33 lỗi đều thuộc `test_menu_style_http.py`, xem §9* |
| pytest — nhóm trực tiếp liên quan | **57 passed** (mock · capability gate · router gate · qa_dot5 · qa_dot6) |
| **vitest** | **84 passed / 84** (hợp đồng · chuẩn hoá · nhất quán fixture) |
| **tsc --noEmit** | sạch |
| **next build** | thành công; `/quanverse` = 13.2 kB (140 kB first load) |
| **playwright** (`quanverse*`) | **34 passed, 3 skipped** |

### 5 spec e2e mới
| Spec | Chốt điều gì |
|---|---|
| `quanverse.spec.ts` | 8 khối có mặt · KHÔNG tab War Room/Cứu ca · KHÔNG bề mặt khách · KHÔNG `<canvas>` · bản đồ 2D click + `aria-pressed` · legend · copilot có trích dẫn |
| `quanverse-mock.spec.ts` | Nhãn mô phỏng + kịch bản · badge timeline · đổi kịch bản đổi số · KPI không rỗng |
| `quanverse-real-shape.spec.ts` | Giả lập `/api/v1/**` bằng **hình dạng thật** để bắt lỗi "adapter lệch hợp đồng" |
| `quanverse-emptydata.spec.ts` | Chặn mọi nguồn → KPI hiện `—` **không** `0` · trạng thái trống nói rõ · dự báo không vẽ đường |
| `quanverse-hidden-routes.spec.ts` | 4 path cũ trả **308** (đọc mã trạng thái, không chỉ URL cuối) |
| `quanverse-mobile.spec.ts` | Không tràn ngang · KPI trong màn đầu · 1 cột · đích chạm ≥ 44px |

### Điều test bắt được (không phải test tự khen)

1. **`soHoacNull("  ")` trả 0** — chuỗi khoảng trắng bị `Number()` ép thành 0. Đã chặn.
2. **`Number([]) === 0`** — mảng lọt qua thành "0 giả". Đã siết chỉ nhận số và chuỗi số.
3. **Dải KPI ở 933px trên mobile** — header 6 mục xếp 1 cột đẩy dưới màn 844px. Đã sửa: 2 cột + thanh điều khiển thu gọn.
4. **Thứ tự `page.route()`** — route tổng đăng ký sau nuốt route cụ thể. Đã đảo.
5. **Khối dự báo có HAI trạng thái trống hợp lệ** — test cũ giả định một. Đã nhận cả hai.

### 6. Lỗi CHỈ LỘ Ở CI — file router đặt tên `test_*.py`

CI job `02 unit` (lần chạy đầu) đỏ 3 bài, tất cả ở **chính file router mock**:

```
FAILED .../http/test_quanverse.py::test_quanverse_stations
FAILED .../http/test_quanverse.py::test_quanverse_forecast
FAILED .../http/test_quanverse.py::test_quanverse_snapshot
  HTTPException: 404 scenario_khong_ton_tai
```

**Nguyên nhân:** `pyproject.toml` khai `testpaths = ["apps", "packages"]` và dùng quy ước mặc định `python_files = test_*.py`. File đặt tên `test_quanverse.py` nằm trong `apps/` nên bị pytest **thu như module test** và gọi thẳng ba hàm route với **fixture** của pytest — tham số `scenario` nhận object `Query(...)` thay vì chuỗi `"cao_diem"`, rồi `_lay_kich_ban` ném 404.

**Vì sao chỉ lộ ở CI:** chạy `pytest <đúng file test>` thì xanh — file router không nằm trong đường dẫn được chỉ định. Chỉ khi CI quét cả `apps/` mới thấy.

**Sửa** (`ae50b6b`): đổi tên `test_quanverse.py` → `quanverse_fixtures.py`. Tên mới cũng đúng nghĩa hơn — đây là bề mặt **fixture**, không phải test. Kèm ghi chú trong docstring để không ai đổi lại. Đã tái hiện bằng `pytest --collect-only -q` **trước** khi sửa.

**Bài học:** không đặt tên file nguồn/route là `test_*.py` dưới `apps/`. Và: **chạy pytest đúng file test không chứng minh suite xanh** — tương tác giữa `testpaths` và tên file là loại lỗi chỉ cổng CI đầy đủ bắt được.

---

## 8. Build result

```
✓ Compiled successfully
✓ Linting and checking validity of types
Route (app)
├ ƒ /quanverse          13.2 kB   140 kB
└  (KHÔNG còn entry nào cho war-room / shift-rescue / rules / spatial-memory)

+ First Load JS shared by all   102 kB
```

- `tsc --noEmit`: **0 lỗi**
- Không thêm dependency nào ngoài `vitest` (devDependency) — **không** gỡ `three`/`@react-three/*`
- CSS: `experience.css` **2110 → 283 dòng** (629 rule chết); số ngoặc cân bằng 0 → 0; bài kiểm tra lại: **0 rule chết còn sót**

### CI

- **Run `36609562876`** (sau fix Ruff) — xem `gh run list --branch main`.
- Lịch sử vòng lặp CI trong phiên này:

| Run | Commit | Kết quả | Ghi chú |
|---|---|---|---|
| `36606553057` | `714c755` | ❌ `02 unit` đỏ 3 bài | file router tên `test_*.py` bị pytest thu |
| `36608128600` | `ae50b6b` | ✅ `02 unit` (10m23s) · ✅ `08 e2e` (6m5s) · ❌ `01 lint` (Ruff I001) | rename đúng; còn lỗi thứ tự import |
| `36609562876` | `8631122` | (đang chạy) | sửa thứ tự import |

- Bước mới thêm vào job 01: `Vitest (web unit)` — chạy 84 test hợp đồng/mock.

### 7. Bài học về quy trình (tự đánh giá)

Hai lỗi CI trong phiên này **lẽ ra bắt được ở máy**:

1. **File router tên `test_*.py`** — chỉ lộ khi quét cả `apps/`. Tôi đã chạy
   `pytest <đúng file test>` và thấy xanh, rồi kết luận suite xanh. **Sai.**
   Cách đúng: chạy `pytest --collect-only -q` hoặc chạy suite đầy đủ từ ROOT.
2. **Thứ tự import Ruff** — tôi chạy `tsc`, `vitest`, `pytest`, `next build`,
   `playwright` nhưng **thiếu `ruff`**, vốn là cổng ĐỎ (hard) trong CI. Một
   lệnh một giây (`ruff check apps/api/src packages scripts`) đã chặn được cả
   vòng CI 10 phút.

**Bổ sung vào danh sách cổng phải chạy trước khi push:**

```
ruff check apps/api/src packages scripts
mypy apps/api/src packages/*/src        (glob phải tự expand trên PowerShell)
pytest -q                                (từ ROOT, không phải apps/api)
tsc --noEmit && vitest run && next build && playwright test
```


---

## 9. Phần backend chưa đủ dữ liệu thật để hoàn thiện

Đây là các khoảng trống **đã kiểm chứng bằng cách đọc source**, không phải phỏng đoán. UI hiện xử lý trung thực (hiện `—` / "Chưa có dữ liệu"), nhưng muốn hoàn thiện thì cần bổ sung backend.

### 9.1 KHÔNG có endpoint "ai đang trực ngay bây giờ"

- `stations.chi_so.nhan_su_trong_ca` chỉ là **một con số**.
- Tên nhân sự hiện được **suy ra phía client** từ `/api/v1/lich-tuan` (phân công tuần + danh mục ca), lọc theo giờ hiện tại (UTC+7).
- Khi không khớp được ca nào → tên để **RỖNG** và số về `null` → UI hiện `—`. Không đoán.
- Hệ quả: bản chiếu nhân sự có thể lệch nếu lịch tuần chưa được xếp cho tuần hiện tại.
- **Đề xuất**: thêm `GET /api/v1/experience/quanverse/staff-on-shift` tính tại máy chủ từ `phan_cong_by_week` + `ca_mau_21`.

### 9.2 `stations` thiếu ngữ nghĩa nghiệp vụ

- Chỉ trả `tai`, `hang_cho`, `muc_day` (**hằng số 5**), `canh_bao`.
- **Không** trả: ngưỡng theo khu vực, độ ưu tiên, nguồn dữ liệu đã dùng.
- Hệ quả: ngưỡng "5" là số hiển thị cứng trong máy chủ, không phải luật nghiệp vụ cấu hình được. Quán đổi ngưỡng thì phải sửa code.

### 9.3 Không có trường "độ tin cậy" cho AI

- `/quanverse/brief/{page}` và `/quanverse/ask` trả `grounded: bool` + `citations[]` + `unsupported_claims[]`.
- **Không** có `confidence` dạng số. Hợp đồng phản ánh đúng thực tế đó.
- Hệ quả: UI chỉ nói được "Có căn cứ / Chưa có căn cứ", không phân biệt được mức tin cậy.

### 9.4 `experience_role_can()` chưa được router nào gọi

- `ExperienceCapability` + `experience_role_can` **có định nghĩa và có unit test** nhưng **không router nào gọi**.
- Mọi route experience đang gác bằng `_require_manager` / `_require_role` (vai từ token), không qua capability.
- Hệ quả: `capability_policy_version: "v1"` do `GET /experience/capabilities` trả ra **chưa được thực thi** ở đâu.

### 9.5 `/api/v1/experience/map` khai HAI lần

- `experience.py:40` và `spatial_memory.py:147` cùng path, **hai hình dạng khác nhau**.
- FastAPI phục vụ cái đăng ký trước; cả hai đều hiện trong OpenAPI.
- Hệ quả: tài liệu API nói hai điều khác nhau về cùng một endpoint.

### 9.6 Bug nhánh chết trong `services/quanverse_live.py`

- `_DA_XONG` chứa `"da_tra"`, nhưng `DonQuay.trang_thai` chỉ cho `cho_pha|dang_pha|xong|huy`.
- Hệ quả: nhánh `"da_tra"` **không bao giờ chạy**; `don_da_xong` có thể đếm thiếu nếu nghiệp vụ thật có trạng thái đó.

### 9.7 `QuanversePage` thiếu trang cho stations/forecast

- Enum chỉ có `living_map|war_room|shift_rescue|rules|spatial_memory`.
- **Không** có trang cho `stations`/`forecast`/`modes` → không xin được brief cho tải/dự báo. Phần này do adapter tự ghép.
- Hệ quả: AI Copilot **không** có brief riêng cho khối "Năng lực / tải vận hành".

### 9.8 `test_menu_style_http.py` — nợ CÓ SẴN, không phải do thay đổi này

- **33 test đỏ** trong `apps/api/tests/unit/test_menu_style_http.py`.
- Nguyên nhân: file test **có trong git**, nhưng module nó kiểm (`apps/api/src/ca_api/interfaces/http/menu_style.py`) **chưa từng được commit ở bất kỳ ref nào** (`git log --all` trả rỗng) và **không có trên đĩa**.
- Đây là bất nhất có sẵn của repo: test được commit mà source thì không.
- Thay đổi này **không chạm** file nào trong số đó. Đề xuất tách một đầu việc riêng: hoặc commit module, hoặc xoá file test.

---

## 10. Còn lại / việc tiếp theo

| # | Việc | Ghi chú |
|---|---|---|
| 1 | Bổ sung endpoint nhân sự-trong-ca (§9.1) | Cần cho Header/copilot chính xác |
| 2 | Cấu hình hoá ngưỡng tải theo khu vực (§9.2) | Bỏ hằng số 5 |
| 3 | Thực thi `experience_role_can` ở router (§9.4) | Đóng khoảng cách policy/implementation |
| 4 | Gộp `/experience/map` trùng (§9.5) | Sửa tài liệu API |
| 5 | Sửa `_DA_XONG` (§9.6) | Bug nhánh chết |
| 6 | Thêm brief cho `stations`/`forecast` (§9.7) | Hoặc mở rộng `QuanversePage` |
| 7 | Xử lý `test_menu_style_http.py` (§9.8) | Nợ có sẵn — commit module hoặc xoá test |
| 8 | Xoá backend của 4 tính năng đã rút | **Chủ ý hoãn**: yêu cầu là không chạm API dùng chung |
