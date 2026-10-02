<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:3E2723,50:6F4E37,100:C68B59&height=200&section=header&text=Crew%20Operations&fontSize=54&fontColor=ffffff&animation=fadeIn&fontAlignY=36&desc=NHIP%20QUAN&descAlignY=58&descSize=20" width="100%" alt="Crew Operations banner" />

<img src="./docs/hinh/logo.png" alt="NHỊP QUÁN — Crew Operations" width="150" />

# NHỊP QUÁN

### AI agent system for coffee-shop operations

> **An AI agent system that assists F&B (food & beverage) businesses with shift scheduling, daily operations, customer interactions, and business management.**
> Not an ML training project — the value is in the **agent + tool + workflow** layer running on a deterministic core.

**Ca làm việc là hạt nhân** &nbsp;·&nbsp; **Cẩm nang tự viết là bộ nhớ** &nbsp;·&nbsp; **Điều phối lõi không dùng LLM**

<br/>

<p align="center">
  <a href="https://nhipquan.duckdns.org/">
    <img src="https://img.shields.io/badge/🚀_Truy_cập_trực_tiếp-nhipquan.duckdns.org-6F4E37?style=for-the-badge&logo=globe&logoColor=white" alt="Truy cập trực tiếp" />
  </a>
</p>

<br/>

[![CI](https://github.com/KanTrun/Crew-Operations/actions/workflows/ci.yml/badge.svg)](https://github.com/KanTrun/Crew-Operations/actions/workflows/ci.yml)
[![Skills Verify](https://github.com/KanTrun/Crew-Operations/actions/workflows/skills-verify.yml/badge.svg)](https://github.com/KanTrun/Crew-Operations/actions/workflows/skills-verify.yml)
[![Docker GHCR](https://github.com/KanTrun/Crew-Operations/actions/workflows/docker-ghcr.yml/badge.svg)](https://github.com/KanTrun/Crew-Operations/actions/workflows/docker-ghcr.yml)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fnhipquan.duckdns.org%2F&style=for-the-badge&label=Website&color=6F4E37)](https://nhipquan.duckdns.org/)

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![OR-Tools](https://img.shields.io/badge/OR--Tools-CP--SAT-4285F4?style=for-the-badge&logo=google&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

<br/>

[**Tổng quan**](#gioi-thieu) &nbsp;•&nbsp;
[**Kiến trúc Agent**](#kien-truc-agent) &nbsp;•&nbsp;
[**Agent Tools**](#agent-tools) &nbsp;•&nbsp;
[**Cài đặt**](#cai-dat) &nbsp;•&nbsp;
[**API**](#api-reference) &nbsp;•&nbsp;
[**Trạng thái**](#trang-thai)

</div>

<br/>

<table align="center">
  <tr>
    <td align="center" width="120"><h2>21</h2><sub>AI agent</sub></td>
    <td align="center" width="120"><h2>35</h2><sub>agent tool (whitelist)</sub></td>
    <td align="center" width="120"><h2>14</h2><sub>kỹ năng đã kiểm định</sub></td>
    <td align="center" width="120"><h2>25</h2><sub>router API</sub></td>
    <td align="center" width="120"><h2>46</h2><sub>route web PWA</sub></td>
    <td align="center" width="120"><h2>5</h2><sub>dịch vụ Docker</sub></td>
  </tr>
</table>

<br/>

<table>
  <tr>
    <td width="50%">

**Sản phẩm** — NHỊP QUÁN
**Website** — [nhipquan.duckdns.org](https://nhipquan.duckdns.org/)
**Repository** — [KanTrun/Crew-Operations](https://github.com/KanTrun/Crew-Operations)
**Cuộc thi** — Xây dựng Hệ điều hành Doanh nghiệp số AI · Khoa CNTT HUTECH · 2026

</td>
    <td width="50%">

**Hồ sơ** — [`NHIP-QUAN-HO-SO-TONG-THE .md`](./NHIP-QUAN-HO-SO-TONG-THE%20.md)
**Kết quả đo §18.2** — [`docs/ket-qua-tong-hop.md`](./docs/ket-qua-tong-hop.md)
**Clone** — `git clone https://github.com/KanTrun/Crew-Operations.git`

</td>
  </tr>
</table>

> [!NOTE]
> **Tên repo vs tên sản phẩm:** GitHub là **Crew-Operations**; phần mềm và UI vẫn là **NHỊP QUÁN**. Tên thư mục clone trên máy (có thể có dấu tiếng Việt) **không** bắt buộc trùng tên repo.

---

## Mục lục

| | | |
|:--|:--|:--|
| 1. [Tổng quan](#gioi-thieu) | 11. [Cài đặt](#cai-dat) | 21. [Triển khai](#trien-khai) |
| 2. [Năng lực cốt lõi](#nang-luc) | 12. [Hướng dẫn chạy](#huong-dan-chay) | 22. [Trạng thái hiện tại](#trang-thai) |
| 3. [Kiến trúc AI Agent](#kien-truc-agent) | 13. [Tài khoản demo](#tai-khoan-demo) | 23. [Hạn chế](#han-che) |
| 4. [Agent Tools](#agent-tools) | 14. [Biến môi trường](#bien-moi-truong) | 24. [Roadmap](#roadmap) |
| 5. [Quy trình nghiệp vụ](#quy-trinh) | 15. [Makefile](#makefile) | 25. [Kiểm thử & đánh giá](#kiem-thu) |
| 6. [Ví dụ tương tác](#vi-du) | 16. [API Reference](#api-reference) | 26. [GitHub — nhánh & quy trình](#github) |
| 7. [Tech Stack](#tech-stack) | 17. [Packages Python](#packages) | 27. [Tài liệu](#tai-lieu) |
| 8. [Tích hợp](#tich-hop) | 18. [Agents](#agents) | |
| 9. [Cấu trúc thư mục](#cau-truc) | 19. [Thư viện Kỹ năng](#skills) | |
| 10. [Yêu cầu môi trường](#yeu-cau) | 20. [Bảo mật](#bao-mat) | |

> [Vấn đề](#van-de) và [Giải pháp](#giai-phap) là tiểu mục của phần Tổng quan.

---

<a id="gioi-thieu"></a>
## Tổng quan

**NHỊP QUÁN** (repo GitHub: **Crew-Operations**) là một **hệ thống AI Agent** hỗ trợ quản lý và vận hành quán F&B — cụ thể là quán cà phê. Đây **không** phải dự án huấn luyện mô hình học máy: giá trị của hệ thống nằm ở **lớp AI agent + tool + quy trình nghiệp vụ**, chạy trên một **lõi tất định** (CP-SAT + cổng kiểm duyệt fail-closed).

| Câu hỏi | Trả lời |
|:--------|:--------|
| **Là gì?** | AI Agent system điều hành vận hành quán: xếp ca, xử lý tin nhắn nhân viên, phiếu checklist trong ca, cẩm nang tự học, trực Page, khảo sát giá, báo cáo |
| **Dành cho ai?** | Chủ quán · quản lý ca · nhân viên phục vụ / pha chế của một quán cà phê |
| **Agent đóng vai trò gì?** | Trợ lý hội thoại **AG-COPILOT** phân tích câu lệnh ngôn ngữ tự nhiên → gọi **tool tất định** trong danh mục whitelist → tạo **đề xuất 2 pha** chờ người duyệt |
| **Ai có tiếng nói cuối?** | Con người. Agent chỉ trích xuất / đề xuất; quản lý và chủ quán duyệt mọi thay đổi lịch, luật cẩm nang, gửi mail, đăng bài |

<a id="van-de"></a>
### Vấn đề

Quán cà phê nhỏ vận hành thủ công gặp những điểm nghẽn mà hệ thống này nhắm tới:

- **Xếp ca thủ công** — cân bằng kỹ năng, tránh trùng ca, tôn trọng thời khoá biểu học và nguyện vọng nghỉ là bài toán nhiều ràng buộc; làm tay dễ sai và tốn thời gian.
- **Thông tin phân tán** — nhân viên xin nghỉ / đổi ca / báo trễ qua nhiều kênh (Telegram, Zalo, gọi điện); quản lý phải tự tổng hợp.
- **Nhắc việc & bàn giao rời rạc** — mở quán / đóng quán / kiểm kê thiếu checklist đối soát; việc treo dễ thất lạc giữa các ca.
- **Kinh nghiệm không được lưu lại** — cùng một lỗi lặp lại nhiều lần nhưng không có cơ chế biến nó thành luật vận hành.
- **Phản hồi khách chậm** — tin nhắn Page, đặt bàn và khảo sát giá đối thủ đều làm thủ công.

<a id="giai-phap"></a>
### Giải pháp

Một **lõi tất định** giữ sự thật nghiệp vụ; các **AI agent** chỉ làm phần "hiểu ngôn ngữ + đề xuất":

```mermaid
flowchart TB
    U["Chủ quán · Quản lý · Nhân viên<br/>Web PWA · Telegram · Zalo · Facebook Page"]
    U --> CH["Lớp kênh & API<br/>FastAPI + router theo vai"]
    CH --> COP["AG-COPILOT<br/>parse intent (whitelist)"]
    COP --> SCOPE["VF-SCOPE<br/>kiểm quyền role × intent"]
    SCOPE --> TOOLS["Tool Registry (whitelist)<br/>đọc dữ liệu thật · KHÔNG ghi DB trực tiếp"]
    TOOLS --> PROP["ActionProposal 2 pha<br/>propose → human approve"]
    PROP --> CORE
    subgraph CORE["Lõi tất định — nguồn sự thật"]
        direction LR
        S1["CP-SAT solver<br/>C01–C06 + fairness"]
        S2["opsengine<br/>phiếu · việc treo"]
        S3["playbook<br/>cẩm nang 8 bước"]
        S4["gates<br/>VF-SCHEMA/TRACE/CONF…"]
    end
    CORE --> DB["SQLite / PostgreSQL<br/>store duy nhất"]
    PROP --> U
    classDef core fill:#6F4E37,stroke:#3E2723,color:#fff
    classDef agent fill:#C68B59,stroke:#6F4E37,color:#fff
    class S1,S2,S3,S4 core
    class COP,SCOPE,TOOLS,PROP agent
```

**Nguyên tắc xuyên suốt:** LLM **không** viết lịch, **không** điều phối, **không** ghi CSDL. Khi LLM lỗi hoặc không chắc chắn, hệ thống **từ chối (fail-closed)** thay vì bịa dữ liệu.

---

<a id="nang-luc"></a>
## Năng lực cốt lõi

Các năng lực dưới đây **đã có trong mã nguồn** (không phải ý tưởng tương lai).

### Xếp lịch & nhân sự

| Năng lực | Chi tiết |
|:---------|:---------|
| Xếp ca tuần bằng CP-SAT | 6 ràng buộc cứng C01–C06 (kỹ năng, đủ người, không đè ca, khoảng nghỉ, trần giờ, TKB/nghỉ phép) + soft + công bằng 4 trục |
| Vòng đời lịch | `nhap → dang_giai → cho_duyet → da_duyet → da_cong_bo → da_dong`, có version + fingerprint + idempotency key |
| Ràng buộc từ tin nhắn | AG-MSG phân loại ý định → hộp thư ràng buộc chờ quản lý duyệt → nạp vào solver |
| Ca trống | Lưu `open_shift`, nhân viên nhận ca (claim transaction-safe), escalate theo SLA |
| Đổi ca 3 người | Phiếu đổi ca có đồng ý / từ chối của các bên tham gia |
| Trích TKB từ ảnh | AG-TKB (vision) đọc thời khoá biểu → xác nhận khoảng bận theo tuần |

### Vận hành trong ca

| Năng lực | Chi tiết |
|:---------|:---------|
| Điểm danh & phiếu checklist | Phiếu YAML trong `infra/templates/` (`mo_quan`, `dong_quan`, `ban_giao_ca`) theo đúng thứ tự bước |
| Anti-fake (ADR-008) | Chặn hoàn thành bước quá nhanh, ảnh minh chứng quá nhanh, số liệu vượt ngưỡng |
| Việc treo & escalate | Treo việc từ tin nhắn/phiếu; nhắc 2 cấp (nhân viên → chủ quán) |
| Bàn giao ca | AG-HANDOVER trích bàn giao + VF-NUM kiểm số liệu + phát hiện mâu thuẫn |
| Quầy POS & menu | Menu + BOM, tạo đơn quầy, luồng `cho_pha → dang_pha → xong/huy`, báo cáo quầy |
| Sổ tiêu thụ & hao phí | Ghi tiêu thụ nguyên liệu; AG-WASTE cụm hoá ghi chú hao phí |
| Hao hụt nguyên liệu | Đối chiếu **lý thuyết ↔ thực tế** theo mặt hàng, xếp hạng nguyên nhân, ngưỡng cấu hình (`config/nguong-hao-hut.yaml`) |

### Khách hàng & kênh

| Năng lực | Chi tiết |
|:---------|:---------|
| Đa kênh tin | Telegram · Zalo OA · Facebook Page — nhân viên nhắn tin, hệ thống phân loại ý định |
| Trực Page & moderation | AG-FBPAGE · AG-CONCIERGE soạn/duyệt phản hồi, hàng đợi moderation, chính sách, reflection |
| Đặt bàn | Sơ đồ bàn, check-in, no-show, hoàn tất, huỷ |
| Ghi nhớ khách quen | AG-VOC nhận diện khách quen, món quen, lưu ý dị ứng/thói quen |
| Khuyến mãi & hồ sơ quán | Hồ sơ quán và danh sách khuyến mãi |

### Trí tuệ vận hành

| Năng lực | Chi tiết |
|:---------|:---------|
| Cẩm nang tự viết | Lỗi lặp ≥ 3 lần → đề xuất luật qua **8 bước**, người duyệt chốt, `apply_luat` bơm lại solver |
| Tự giải thích | AG-EXPLAIN dịch mã lý do solver thành câu tiếng Việt có căn cứ |
| Dự đoán & Digital Twin | AG-PREDICT phát hiện mẫu thành công; AG-TWIN mô phỏng "nếu… thì…" bằng Math Layer |
| Khảo sát giá đối thủ | AG-PRICING quét giá quanh quán (SerpApi + Vision); giá không chắc chắn chờ người xác nhận |
| Học từ phản hồi | Ghi phản hồi người dùng, đánh giá, đề xuất luật AI, circuit breaker, retention |
| Xu hướng & reflection | Radar xu hướng TikTok/Threads (AG-TREND), reflection trên mail đã gửi và phản hồi Page |
| Khảo sát giá giao hàng | Đối chiếu giá món trên ShopeeFood và menu Google Maps, chuẩn hoá tên món trước khi so sánh |
| Ảnh thẻ sản phẩm | Sinh **tại máy** bằng Pillow (ADR-019), tất định theo `id` (SHA-256) — demo chạy trọn khi rút mạng. Ba bậc: ảnh tự tải lên → ảnh đã sinh → sinh tại chỗ |
| Ảnh quảng cáo AI | AG-MENU-IMAGE tạo ảnh quảng cáo với **prompt tất định**; chuỗi provider Cloudflare Workers AI → Gemini → Pollinations (không bắt buộc, có fallback) |

### AI Agent

| Năng lực | Chi tiết |
|:---------|:---------|
| Hội thoại ngôn ngữ tự nhiên | AG-COPILOT parse intent tiếng Việt → tool đề xuất hoặc câu trả lời trực tiếp |
| Tool calling có kiểm soát | 35 tool whitelist; LLM không thể gọi tool ngoài danh mục |
| Thực thi 2 pha | Mọi hành động ghi đều tạo `ActionProposal` → người duyệt → thực thi idempotent |
| Context-aware | Ngữ cảnh tối đa 3 tin nhắn gần nhất, phạm vi giới hạn theo `store_id` |
| Voice | Copilot Voice qua Gemini Live, có giới hạn phiên và timeout im lặng |

### Triết lý cốt lõi

<table>
  <tr>
    <td width="25%" valign="top">

#### Lõi không dùng LLM
Xếp ca bằng **CP-SAT** (Google OR-Tools), cổng kiểm duyệt fail-closed, orchestration tất định.

</td>
    <td width="25%" valign="top">

#### Người duyệt có tiếng nói cuối
Agent **chỉ trích xuất và đề xuất**. Mọi thay đổi lịch và hiệu lực ca đi qua quản lý / chủ quán.

</td>
    <td width="25%" valign="top">

#### Cẩm nang sống
Lỗi lặp lại **≥ 3 lần** tự sinh đề xuất luật, qua **8 bước** từ tìm mẫu đến gỡ luật.

</td>
    <td width="25%" valign="top">

#### Fail-closed
Khi LLM lỗi hoặc không chắc chắn, hệ thống **từ chối** thay vì bịa dữ liệu.

</td>
  </tr>
</table>

---

<a id="kien-truc-agent"></a>
## Kiến trúc AI Agent

### Các lớp

| Lớp | Thành phần | Vai trò |
|:----|:-----------|:--------|
| **1. Người dùng** | Web PWA (`apps/web`) · Telegram · Zalo OA · Facebook Page | Nhập yêu cầu, duyệt đề xuất |
| **2. Kênh & API** | `apps/api` (FastAPI) — 25 router module | Xác thực, phân quyền, chuẩn hoá request |
| **3. Agent** | `packages/agents` (`ca_agents`) | AG-COPILOT + các agent chuyên trách |
| **4. LLM Router** | `FreeTierRouter` | `groq → openrouter → bai → ollama`; vision: `gemini → openrouter → groq` |
| **5. Cổng kiểm duyệt** | `packages/gates` | VF-SCHEMA · VF-TRACE · VF-CONF · VF-RULE · VF-SCOPE · VF-STALE · VF-NUM |
| **6. Tool Registry** | `ag_copilot/tool_registry.py` | 35 tool whitelist, đọc dữ liệu thật, không ghi DB |
| **7. Dịch vụ nghiệp vụ** | `packages/solver` · `opsengine` · `playbook` | CP-SAT, phiếu / việc treo, cẩm nang 8 bước |
| **8. Dữ liệu** | SQLite (mặc định) hoặc PostgreSQL; Redis cho realtime | Store duy nhất — nguồn sự thật |
| **9. Dịch vụ ngoài** | Groq · Gemini · OpenRouter · B.ai · Ollama · SerpApi · Meta Graph · Google Gmail API · SMTP · Telegram · Zalo | Gọi qua adapter, fail-closed khi thiếu credential |

```mermaid
flowchart TB
    U["Người dùng<br/>PWA · Telegram · Zalo · FB Page"]
    U --> API["API / Kênh<br/>FastAPI · 25 router"]
    API --> AG["AI Agent<br/>AG-COPILOT"]
    AG --> LLM["LLM Router<br/>groq→openrouter→bai→ollama"]
    AG --> GATE["Cổng VF<br/>SCHEMA·TRACE·CONF·SCOPE·STALE"]
    GATE --> TR["Tool Registry<br/>35 tool whitelist"]
    TR --> SVC
    subgraph SVC["Dịch vụ nghiệp vụ"]
        direction LR
        B1["solver<br/>CP-SAT"]
        B2["opsengine<br/>phiếu · treo"]
        B3["playbook<br/>8 bước"]
        B4["agents chuyên trách<br/>MSG · TKB · PRICING…"]
    end
    SVC --> DB[("SQLite / PostgreSQL<br/>+ Redis realtime")]
    SVC --> EXT["Dịch vụ ngoài<br/>SerpApi · Meta · Gmail · SMTP"]
    AG --> PROP["ActionProposal<br/>2 pha"]
    PROP --> U
    classDef core fill:#6F4E37,stroke:#3E2723,color:#fff
    classDef agent fill:#C68B59,stroke:#6F4E37,color:#fff
    class B1,B2,B3,B4 core
    class AG,LLM,GATE,TR,PROP agent
```

### Agent chính — AG-COPILOT

| Thuộc tính | Thực tế trong code |
|:-----------|:-------------------|
| **Nhiệm vụ** | Phân tích câu lệnh tự nhiên → nhận diện 1 intent trong whitelist (hoặc `OUT_OF_SCOPE`) → gọi tool tất định |
| **File** | `packages/agents/src/ca_agents/ag_copilot/` (`copilot_agent.py`, `intent_parser.py`, `tool_registry.py`, `voice_session.py`) |
| **Memory** | Ngữ cảnh hội thoại hữu hạn: tối đa **3 tin nhắn gần nhất** (`recent_messages`), scope theo `store_id`, không có vector store |
| **Planning / reasoning** | Parser từ khoá + LLM parse intent (`intent_parser.py`), **không** có vòng lặp ReAct/agent tự trị |
| **Tool calling** | Có — nhưng **chỉ** tool trong whitelist; LLM không tự chọn tool tuỳ ý (xem [Agent Tools](#agent-tools)) |
| **Thực thi** | "Two-Phase Execution": Pha 1 đề xuất (`ActionProposal`), Pha 2 người duyệt → `execute-action` idempotent |
| **Từ chối** | `OUT_OF_SCOPE` khi confidence < 0.5; hỏi làm rõ khi 0.5 ≤ conf < 0.75; hành động khi conf ≥ 0.75 |
| **Kiểm soát** | `AG-SUPERVISOR` lọc rò rỉ dữ liệu nhạy cảm và lời hứa tài chính trái phép |

> [!NOTE]
> Repository này **không** phải multi-agent tự trị và **không** dùng RAG/vector retrieval. Đây là **một agent điều phối trung tâm (AG-COPILOT)** cùng một tập **agent chuyên trách theo tác vụ** (AG-TKB, AG-MSG, AG-SOP…), mỗi agent xử lý một bước nghiệp vụ độc lập và trả kết quả cho lớp tất định.

### Danh sách agent theo nhóm

| Nhóm | Agent | Vai trò |
|:-----|:------|:--------|
| **Điều phối** | **AG-COPILOT** | Trợ lý đầu não: parse intent, đề xuất 2 pha, audit, có kênh voice |
| **Hội thoại & kênh** | AG-MSG · AG-FBPAGE · AG-CONCIERGE · AG-GMAIL · AG-MAIL / AG-MAILWRITER | Phân loại tin nhắn, trực Page, đọc/gửi Gmail, soạn & gửi mail |
| **Nhân sự** | AG-TKB · AG-BRIEF | Trích thời khoá biểu từ ảnh, sinh bản tin giao ban |
| **Vận hành** | AG-HANDOVER · AG-WASTE · AG-BARISTA · AG-SUPERVISOR | Bàn giao ca, cụm hao phí, định mức pha, giám sát đầu ra |
| **Tri thức** | AG-RULE · AG-SOP | Đề xuất luật cẩm nang, hỏi đáp quy trình có trích dẫn |
| **Khách hàng & thị trường** | AG-VOC · AG-TREND · AG-MEETING | Ghi nhớ khách quen, radar xu hướng, trích biên bản họp |
| **Dự đoán & mô phỏng** | AG-PREDICT · AG-EXPLAIN · AG-TWIN · AG-PRICING | Phát hiện mẫu thành công, tự giải thích, digital twin, khảo sát giá |
| **Trải nghiệm & nội dung** | AG-WAR-ROOM · AG-SHIFT-RESCUE · AG-RULE-LEARNING · AG-SPATIAL-MEMORY · AG-QUANVERSE · AG-MENU-IMAGE | War Room twin, cứu ca đột xuất, quán tự viết luật, ký ức không gian, Living Cafe OS, sinh/sửa ảnh quảng cáo menu |

> 21 gói agent trong `ag_*/` (khớp badge đầu trang) cùng các mô-đun agent mở rộng dạng file đơn (`ag_barista.py`, `ag_concierge.py`, `ag_fbpage.py`, `ag_mail.py`, `ag_menu_image.py`, `ag_supervisor.py`, `ag_trend.py`). Quánverse (War Room · Shift Rescue · Rules · Spatial Memory) dùng chung nền **ADR-021** — LLM không bao giờ là nguồn số.

---

<a id="agent-tools"></a>
## Agent Tools

Toàn bộ tool nằm trong `packages/agents/src/ca_agents/ag_copilot/tool_registry.py`, được gọi qua `execute_whitelisted_tool(intent, params)`. **Rule #2** của registry: mỗi lời gọi tool phải khớp một intent trong `_TOOLS`; **Rule #3**: tool **không** ghi CSDL production — chỉ trả dữ liệu/diff để dựng `ActionProposal`.

Trong 35 tool, có **hai loại**:

- **Tool đọc** (`requires_confirmation=False`): trả dữ liệu sống, kèm `_provenance` (nguồn + thời điểm đọc + tenant scope).
- **Tool đề xuất** (`requires_confirmation=True`): sinh `ActionProposal` + snapshot hash để kiểm VF-STALE lúc duyệt.

### Tool đề xuất hành động (ghi — cần người duyệt)

| Tool | Purpose | Input | Output |
|:-----|:--------|:------|:-------|
| `tool_solve_weekly_schedule` | Chạy CP-SAT xếp lịch tuần, thu thập TKB + ràng buộc đã duyệt + ghim ca | `tuan`, `uu_tien_nhan_su` | `phan_cong`, `status`, `rules_applied`, `meeting_adjustments` |
| `tool_prepare_swap_approval` | Chuẩn bị duyệt đổi ca (kiểm không trùng ca) | `item_id`, `ca_dich`, `doi_tac_nv_id` | diff phân công trước/sau |
| `tool_propose_rule_from_recent_edits` | Đề xuất luật cẩm nang từ lịch sử sửa | (nguồn inject) | luật ứng viên + mẫu lặp |
| `tool_send_mail` | Soạn & gửi email điều hành | `to_nv_ids`/`to_emails`, `subject`, `body` | `ActionProposal` + snapshot người nhận |
| `tool_propose_catchment_survey` | Tạo job khảo sát giá đối thủ | `category_keyword`, `radius_km`, `channel_mode` | đề xuất + kiểm quota SerpApi |
| `tool_propose_hanging_task` | Đề xuất tạo việc treo | `noi_dung` | proposal |
| `tool_propose_task_complete` | Đề xuất đóng việc treo | `treo_id` | proposal + diff |
| `tool_propose_consumption_record` | Đề xuất ghi tiêu thụ nguyên liệu | `hang`, `so_luong`, `don_vi` | proposal + diff sổ tiêu thụ |
| `tool_propose_menu_update` | Đề xuất sửa món (tên, giá, ẩn, BOM) | `mon_id`, trường sửa | diff trước/sau |
| `tool_propose_order_transition` | Đề xuất chuyển trạng thái đơn quầy | `don_id`, trạng thái đích | proposal + diff đơn |
| `tool_propose_pin` | Ghim/bỏ ghim nhân viên vào ca | `ca_id`, `nv_id`, `pinned` | proposal + diff pins |
| `tool_propose_time_off` | Đề xuất ràng buộc nghỉ phép vào hộp thư | `thu`, `hieu_luc` | proposal |
| `tool_propose_tkb_confirm` | Đề xuất xác nhận khoảng bận TKB theo tuần | `tuan_iso`, `khoang_ban` | proposal + snapshot TKB |
| `tool_propose_swap_consent` | Đề xuất đồng ý tham gia đổi ca | `swap_id` | proposal |
| `tool_propose_handover` | Đề xuất tạo bàn giao ca | nội dung bàn giao | proposal + VF-NUM |
| `tool_propose_page_sync` | Đề xuất đồng bộ threads Facebook Page | — | proposal + trạng thái Page |
| `tool_propose_page_draft` | Đề xuất tạo/đăng bài viết Page | nội dung bài | proposal |

### Tool đọc dữ liệu (không cần duyệt)

| Tool | Purpose | Input | Output |
|:-----|:--------|:------|:-------|
| `tool_get_daily_brief` | Lấy bản tin sáng đã sinh | — | ca hôm nay, treo, tồn cảnh báo |
| `tool_query_sop_playbook` | Hỏi đáp quy trình (AG-SOP) | `question`, `ngu_canh` | câu trả lời + `trich_dan` + cờ `chua_co` |
| `tool_get_waste_summary` | Tổng hợp hao phí đã cụm | — | cụm hao phí + ghi chú gốc |
| `tool_check_inventory_restock` | Kiểm tồn kho / điểm đặt hàng lại | — | cảnh báo mặt hàng cần đặt |
| `tool_get_my_profile` | Hồ sơ của chính người hỏi | `user_id` | thông tin cá nhân |
| `tool_list_staff` | Danh sách nhân viên | — | danh sách nhân sự (tenant-scoped) |
| `tool_query_menu` | Truy vấn menu | `gom_an` | danh sách món |
| `tool_get_inventory` | Truy vấn tồn kho | — | tồn kho hiện tại |
| `tool_get_shift_swaps` | Danh sách phiếu đổi ca | — | các phiếu đổi ca |
| `tool_get_hanging_tasks` | Danh sách việc treo | — | việc treo đang mở |
| `tool_get_handovers` | Lịch sử bàn giao | — | các bản giao |
| `tool_get_schedule` | Lịch tuần | `tuan` | phân công, khung giờ, lifecycle |
| `tool_get_my_shifts` | Ca cá nhân | — | ca của người hỏi |
| `tool_get_constraint_candidates` | Ràng buộc chờ duyệt | — | danh sách ràng buộc + phạm vi vai |
| `tool_query_audit` | Vết hệ thống (chỉ quản lý & chủ quán) | bộ lọc | bản ghi audit |
| `tool_get_page_status` | Trạng thái Facebook Page | — | mode + connected (token đã redact) |
| `tool_get_serpapi_quota` | Hạn ngạch SerpApi còn lại | — | quota đã dùng / còn lại |
| `tool_get_latest_survey_result` | Kết quả khảo sát giá mới nhất | — | kết quả catchment survey |

<details>
<summary><b>Danh mục intent được whitelist (whitelist gốc trong registry)</b></summary>

<br/>

```python
WHITELISTED_INTENTS = {
    "SCHEDULE_SOLVE": "tool_solve_weekly_schedule",
    "APPROVE_SHIFT_SWAP": "tool_prepare_swap_approval",
    "GENERATE_DAILY_BRIEF": "tool_get_daily_brief",
    "QUERY_SOP": "tool_query_sop_playbook",
    "ANALYZE_WASTE": "tool_get_waste_summary",
    "CREATE_RULE_PROPOSAL": "tool_propose_rule_from_recent_edits",
    "INVENTORY_RESTOCK_CHECK": "tool_check_inventory_restock",
    "SEND_MAIL": "tool_send_mail",
    "RUN_CATCHMENT_SURVEY": "tool_propose_catchment_survey",
    "GET_SERPAPI_QUOTA": "tool_get_serpapi_quota",
    "GET_SURVEY_RESULT": "tool_get_latest_survey_result",
}
```

`_TOOLS` còn đăng ký thêm nhóm `GET_*` (đọc) và `PROPOSE_*` (đề xuất), tổng cộng **35 tool**.

</details>

### Ràng buộc kiến trúc của Tool Registry

- Tool **không** import agent khác, không import `ca_api` / `ca_playbook` / `ca_gates` — được **test `test_architecture.py`** cưỡng chế.
- Nguồn dữ liệu được **inject** từ lớp API qua `configure_data_sources()`; chạy standalone thì fallback đọc file JSON.
- Khi dữ liệu thật rỗng, tool trả **"không có dữ liệu"** trung thực thay vì bịa số (Rule #4).

---

<a id="quy-trinh"></a>
## Quy trình nghiệp vụ

### Luồng nghiệp vụ chính (lịch tuần)

```mermaid
flowchart LR
    NV["NV gửi tin<br/>Telegram · Zalo · FB"] --> MSG["AG-MSG<br/>phân loại ý định"]
    MSG --> INBOX["Hộp thư<br/>ràng buộc"]
    INBOX -->|"quản lý duyệt"| SOLVER["CP-SAT<br/>C01–C06 + soft<br/>+ công bằng 4 trục"]
    SOLVER --> LICH["Lịch tuần"]
    LICH --> CA["Trong ca<br/>điểm danh · phiếu<br/>việc treo · bàn giao"]
    CA -->|"lỗi lặp ≥ 3 lần"| CN["Cẩm nang<br/>8 bước"]
    CN -->|"apply_luat"| SOLVER

    style SOLVER fill:#6F4E37,stroke:#3E2723,color:#fff
    style CN fill:#C68B59,stroke:#6F4E37,color:#fff
```

<details>
<summary><b>Xem chi tiết 7 bước của luồng nghiệp vụ</b></summary>

<br/>

1. NV gửi tin qua kênh (Telegram/Zalo/FB) → AG-MSG phân loại ý định → vào **hộp thư ràng buộc** chờ duyệt.
2. Quản lý duyệt → ràng buộc nạp vào solver → CP-SAT xếp lịch tuần (C01–C06 cứng + soft + công bằng 4 trục).
3. Lịch qua lifecycle: `nhap → dang_giai → cho_duyet → da_duyet → da_cong_bo → da_dong`.
4. Trong ca: điểm danh → phiếu checklist (mở quán/đóng quán/bàn giao) → việc treo → bàn giao.
5. Lỗi lặp lại → cẩm nang 8 bước → luật hiệu lực → bơm lại solver (`apply_luat`).
6. Hệ thống tự giải thích ("tại sao") bằng chuỗi nhân quả, phát hiện mẫu thành công để đề xuất luật tích cực, và mô phỏng kịch bản "nếu… thì…" bằng Math Layer (Digital Twin).
7. Khảo sát giá đối thủ quanh quán (SerpApi + Vision) để hỗ trợ định giá.

</details>

### Workflow "Manager hỏi — Agent đề xuất"

```mermaid
sequenceDiagram
    participant M as Quản lý
    participant C as AG-COPILOT
    participant G as Cổng VF
    participant T as Tool Registry
    participant H as Người duyệt

    M->>C: "Xếp lịch tuần sau giúp em"
    C->>C: parse intent → SCHEDULE_SOLVE
    C->>G: VF-SCOPE (role × intent)
    G-->>C: hợp lệ (quan_ly)
    C->>T: tool_solve_weekly_schedule(tuan)
    T->>T: CP-SAT + luật + ràng buộc đã duyệt
    T-->>C: proposal + snapshot hash
    C-->>M: reply_text + ActionProposal (chờ duyệt)
    M->>H: (hoặc quản lý khác) xem & duyệt
    H->>C: execute-action(decision=approve)
    C->>G: VF-STALE (snapshot còn khớp?)
    G-->>C: còn mới → thực thi idempotent
```

### Vòng đời lịch tuần

```mermaid
stateDiagram-v2
    direction LR
    [*] --> nhap
    nhap --> dang_giai: chạy solver
    dang_giai --> cho_duyet
    cho_duyet --> da_duyet: quản lý duyệt
    da_duyet --> da_cong_bo: công bố
    da_cong_bo --> da_dong: chủ quán chốt
    da_dong --> [*]
```

### Cẩm nang 8 bước

```mermaid
flowchart LR
    S1["1. Tìm mẫu"] --> S2["2. Đề xuất"] --> S3["3. Kiểm chứng"] --> S4["4. Tập sự"] --> S5["5. Chốt"] --> S6["6. Hiệu lực"] --> S7["7. Áp dụng"] --> S8["8. Gỡ"]
```

Luật chỉ có hiệu lực khi có **người duyệt** (`duyet`) ở bước 6, và có thể **gỡ** ở bước 8. Luật hiệu lực được bơm lại solver bằng `apply_luat` — đây là cơ chế "bộ nhớ" của hệ thống.

---

<a id="vi-du"></a>
## Ví dụ tương tác

Các ví dụ dưới đây dùng **đúng intent và tool có trong registry**. Agent chạy `CA_AGENT_MODE=replay` khi test; `live` khi có key LLM.

```text
Quản lý:  "Xếp lịch tuần sau giúp em"
AG-COPILOT:  [intent=SCHEDULE_SOLVE] → tool_solve_weekly_schedule(tuan="2026-W36")
             → "Đã xếp thành công N lượt phân công cho tuần 2026-W36."
             → ActionProposal trạng thái chờ duyệt (không tự công bố)
```

```text
Quản lý:  "Hôm nay có việc gì cần chú ý không?"
AG-COPILOT:  [intent=GENERATE_DAILY_BRIEF] → tool_get_daily_brief()
             → ca hôm nay + việc treo + tồn cảnh báo (đọc từ kv brief_hom_nay)
```

```text
Nhân viên:  "Quy trình mở quán gồm những bước nào?"
AG-COPILOT:  [intent=QUERY_SOP] → tool_query_sop_playbook(question=...)
             → câu trả lời + trích dẫn [phieu:ma, luat:id]
             → nếu không có nguồn: "Chưa có trong cẩm nang của quán, hãy hỏi quản lý."
                (cờ chua_co=true — KHÔNG bịa)
```

```text
Quản lý:  "Tuần này hao phí nguyên liệu thế nào?"
AG-COPILOT:  [intent=ANALYZE_WASTE] → tool_get_waste_summary()
             → các cụm hao phí (AG-WASTE) + ghi chú gốc
```

```text
Quản lý:  "Khảo sát giá cà phê quanh quán bán kính 3km"
AG-COPILOT:  [intent=RUN_CATCHMENT_SURVEY]
             → tool_propose_catchment_survey(category_keyword=..., radius_km=3.0)
             → đề xuất + kiểm quota SerpApi; giá OCR không chắc chắn → NEEDS_REVIEW
```

```text
Nhân viên:  "Mai em xin nghỉ ca sáng"
AG-MSG:  [intent=xin_nghi] → hộp thư ràng buộc (chờ quản lý duyệt)
         → khi duyệt: ràng buộc nạp vào solver cho tuần tương ứng
```

---

<a id="tech-stack"></a>
## Tech Stack

| Nhóm | Công nghệ thực tế (đối chiếu mã nguồn & `compose.yml`) |
|:-----|:-----------------------------------------------------|
| **Ngôn ngữ** | Python 3.12+ (`requires-python = ">=3.12"`), TypeScript (strict) |
| **AI / LLM** | Groq · Google Gemini (vision + Live voice/STT) · OpenRouter · B.ai · Ollama (fallback local) |
| **LLM Router** | `FreeTierRouter` (tự viết) — `groq → openrouter → bai → ollama`; vision ưu tiên Gemini; hết provider → `tu_choi` |
| **Agent** | Custom implementation trong `ca_agents` (không dùng framework agent ngoài); prompt versioned + `SkillLoader` |
| **Backend** | FastAPI + Uvicorn; SQLAlchemy/Alembic cho migration; worker nền `ca_api.worker` |
| **Frontend** | Next.js 15 (App Router) · React 19 · Tailwind CSS · three.js / react-three-fiber · framer-motion; PWA |
| **Tối ưu tất định** | Google OR-Tools **CP-SAT** (`ca_solver`) |
| **Dữ liệu** | SQLite (mặc định, dev) hoặc PostgreSQL 16 (Docker/production); Redis 7 (Pub/Sub realtime chat) |
| **Bảo mật** | PBKDF2-HMAC-SHA256 (hash mật khẩu, có salt) · Fernet (mã hoá OAuth token) · token Bearer |
| **Hạ tầng** | Docker Compose (5 service: postgres · redis · api · worker · web) · GHCR image · runbook AWS / Oracle |
| **Test** | pytest (monorepo) · Playwright (e2e web) · ruff · mypy --strict · `tsc --noEmit` |
| **Tích hợp** | Telegram Bot API · Zalo OA · Facebook Page / Messenger Graph API · Google Gmail API (OAuth 2.0) · SMTP · SerpApi · Threads API · Camoufox (scraping tùy chọn) |

> [!NOTE]
> Repo có cấu hình cho nhiều provider LLM, nhưng chúng được dùng qua **router fail-closed**: thiếu key thì tự chuyển provider khác hoặc từ chối, không im lặng trả dữ liệu giả.

---

<a id="tich-hop"></a>
## Tích hợp

### Facebook Page / Messenger

```mermaid
flowchart LR
    FB["Khách nhắn Page"] --> WH["Webhook<br/>POST /api/v1/channels/facebook<br/>hoặc /api/v1/page/*"]
    WH --> MOD["fb_moderation<br/>sensor chain · rate limiter"]
    MOD --> AG["AG-FBPAGE · AG-CONCIERGE"]
    AG --> Q["Hàng đợi moderation<br/>/page-quan/fb-inbox"]
    Q -->|"quản lý quyết định"| REPLY["Phản hồi khách"]
    AG --> MEM["customer_memory<br/>khách quen"]
```

- **Xác thực:** Page access token (`NHIPQUAN_FB_PAGE_TOKEN`) + verify token webhook (`NHIPQUAN_FB_WEBHOOK_VERIFY`); `NHIPQUAN_PAGE_MODE` = `live` / `replay` / `disconnected`.
- **Data flow:** Tin khách → moderation (sentiment + rate limit) → agent soạn → hàng đợi chờ người duyệt → đăng phản hồi.
- Runbook: [`docs/runbooks/facebook-page-connect.md`](./docs/runbooks/facebook-page-connect.md) · [`fb-chatbot-moderation.md`](./docs/runbooks/fb-chatbot-moderation.md)

### Telegram / Zalo OA

```mermaid
flowchart LR
    NV["Nhân viên nhắn"] --> P{"MessagePort<br/>telegram / zalo"}
    P --> WEB["Webhook có secret/token"]
    P --> LP["Long-poll (Telegram)"]
    WEB --> CLS["AG-MSG phân loại"]
    LP --> CLS
    CLS --> IB["Hộp thư ràng buộc"]
```

- **Cổng tin:** `ca_agents.messaging.get_port(name)` chọn `replay` / `telegram` / `zalo` / `console`.
- **Telegram:** verify header `X-Telegram-Bot-Api-Secret-Token`; hỗ trợ long-poll (không cần public webhook).
- **Zalo OA:** kênh ưu tiên tại Việt Nam, dùng OA access token.
- Runbook: [`telegram-bot-connect.md`](./docs/runbooks/telegram-bot-connect.md) · [`zalo-oa-connect.md`](./docs/runbooks/zalo-oa-connect.md)

### Google Gmail (OAuth 2.0)

- Đọc / gửi mail, nhãn, bộ lọc, đồng bộ tăng dần theo `historyId`.
- Token OAuth được **mã hoá Fernet** trong DB, khoá qua `NHIPQUAN_ENCRYPTION_KEY`.
- UI: `/gmail` · Runbook: [`docs/runbooks/gmail-oauth-connect.md`](./docs/runbooks/gmail-oauth-connect.md) · [`gmail-smtp-connect.md`](./docs/runbooks/gmail-smtp-connect.md)

### SerpApi — khảo sát giá đối thủ (AG-PRICING)

- Dùng Google Maps / Trends / Reviews trong bán kính quán; Vision OCR đọc bảng giá từ ảnh.
- Đối chiếu chéo giá giao hàng (ShopeeFood) và menu Google Maps; `dish_name_normalizer` chuẩn hoá tên món trước khi so sánh.
- Có quota manager + circuit breaker + cache TTL; giá không chắc chắn chuyển `NEEDS_REVIEW`.
- Runbook: [`docs/runbooks/serpapi-integration.md`](./docs/runbooks/serpapi-integration.md)

### Xu hướng (AG-TREND)

Chuỗi tầng **fail-closed** — tầng trên hỏng thì rớt xuống tầng dưới, không crash:

```mermaid
flowchart LR
    A["Google Trends<br/>Trending Now VN"] --> B["SerpApi<br/>từ khoá theo chủ đề"]
    B --> C["RSS / TikTok / Threads<br/>theo từ khoá đã biết"]
```

| Tầng | Nguồn | Đặc điểm |
|:-----|:------|:---------|
| 1 | Google Trends **Trending Now** | Bảng xếp hạng quốc gia thật, có `search_volume` / `increase_percentage` |
| 2 | SerpApi `RELATED_QUERIES` | Từ khoá bứt phá theo chủ đề biết trước |
| 3 | TikTok / Threads / RSS | Cào chi tiết theo từ khoá; Camoufox là tier tuỳ chọn |

- Tier 0 Threads: Official API (`THREADS_ACCESS_TOKEN`).
- Tier tùy chọn: Camoufox (browser thật chống-detect) — thiếu thì tier tự rớt, không crash.
- Runbook: [`tiktok-scraping.md`](./docs/runbooks/tiktok-scraping.md) · [`camoufox-scraping.md`](./docs/runbooks/camoufox-scraping.md)

---

## Grand AI Experience Portfolio (replay demo)

Bên cạnh màn hình vận hành, NHỊP QUÁN có bề mặt **trải nghiệm AI** tại
`/quanverse` (routed riêng, đọc dữ liệu qua adapter — không import DB internals):

| Ý tưởng | Route | Nguyên tắc |
|---|---|---|
| War Room Digital Twin | `/quanverse/war-room` | Mô phỏng “nếu… thì…” tất định + baseline ≥2 option; proposal chờ duyệt |
| AI Shift Rescue | `/quanverse/shift-rescue` | Vắng đột xuất → candidate an toàn theo C01-C06; không broadcast |
| Quán tự viết luật | `/quanverse/rules` | Decision lặp lại ≥3 → shadow test → playbook 8 bước; không tự kích hoạt |
| HỒN QUÁN Spatial Memory | `/quanverse/spatial-memory` | Ký ức gắn anchor: consent, retention, citations grounded, voice/replay |
| QUÁNVERSE Living Cafe OS | `/quanverse` | Living map theo 4 vai trò (server-side projection), mode/flavor/AR-lite |

**Triết lý chung:** LLM chỉ lo lời; mọi số/recommendation/scoring là
deterministic; mọi mutation là proposal → consent/confirm → audit; 2D là
canonical (WebGL/voice/AR là progressive). Chạy demo replay:

```powershell
make contracts
$env:CA_AGENT_MODE='replay'; python scripts/demo_grand_experience.py
# UI: docs/runbook-grand-ai-experience.md (6 bước 5 phút)
```

Xem thêm: `docs/architecture-grand-ai-experience.md`,
`docs/adr/ADR-016|017|018-*.md`, plan `plans/260920-1442-*`.

> [!IMPORTANT]
> Nền tảng số của toàn bộ Quánverse là [ADR-021](./docs/adr/ADR-021-llm-khong-la-nguon-so.md): **LLM không bao giờ là nguồn số**. Mọi con số, điểm số, xếp hạng đều do lõi tất định tính; LLM chỉ diễn đạt lại.

---

<a id="cau-truc"></a>
## Cấu trúc thư mục

```text
Crew-Operations/
├── apps/
│   ├── api/                        # FastAPI service (package ca_api)
│   │   ├── src/ca_api/
│   │   │   ├── interfaces/http/     # 25 router module — mọi endpoint REST/WS
│   │   │   │                        #   main.py (app), sprint3, sprint45, hao_hut,
│   │   │   │                        #   channels, copilot, copilot_voice, pos,
│   │   │   │                        #   quanverse, meeting, ops_explain,
│   │   │   │                        #   ops_predict, experience, experience_rules,
│   │   │   │                        #   war_room, trends, pricing_radar,
│   │   │   │                        #   mail, gmail, ai_learning, ai_insight,
│   │   │   │                        #   chat, reservations, shift_rescue,
│   │   │   │                        #   spatial_memory, skills
│   │   │   ├── services/            # chat_ws (Redis), fb_moderation, gmail_sync,
│   │   │   │                        #   scheduling_service, table_reservation_service…
│   │   │   ├── orchestration/       # Clock, StateMachine, IdempotencyStore
│   │   │   ├── ai_learning/         # vòng phản hồi, rollout luật AI, retention
│   │   │   ├── domain/              # entities, policies
│   │   │   ├── persist.py           # store SQLite/Postgres + auth (PBKDF2, Fernet)
│   │   │   ├── audit_trace.py       # vết audit hệ thống
│   │   │   └── worker.py            # job nền: brief sáng, solver tuần, tổng kết ngày
│   │   ├── alembic/                 # migration Postgres
│   │   └── tests/                   # 77 file test
│   └── web/                        # Next.js 15 PWA (ca-web)
│       ├── src/app/                 # 46 route: roster, inbox, copilot, chat, page-quan,
│       │                            #   gmail, cam-nang, lich-tuan, quay, phieu, pos, tkb,
│       │                            #   hao-phi, tieu-thu, doi-ca, cong-bang, nguoi, menu,
│       │                            #   sop, treo, handover, giai-thich, cuoc-hop, vet,
│       │                            #   de-xuat-thong-minh, khao-sat-gia, cau-hinh-quan,
│       │                            #   thu-nghiem-an-toan, huong-dan, quanverse/*…
│       ├── src/lib/                 # api client, session, realtime, roster, present…
│       ├── src/ui/ · src/shared/    # component UI & dùng chung
│       └── e2e/                     # 23 spec Playwright
├── packages/
│   ├── contracts/              # ca_contracts — Pydantic schema chia sẻ (ADR-003/013)
│   ├── solver/                 # ca_solver — CP-SAT + C01–C06 + fairness 4 trục
│   ├── gates/                  # ca_gates — VF-SCHEMA/TRACE/CONF/RULE/SCOPE/STALE/NUM
│   ├── opsengine/              # ca_ops — phiếu YAML, việc treo, escalate
│   ├── playbook/               # ca_playbook — cẩm nang 8 bước, distiller SOP→Skill
│   └── agents/                 # ca_agents — 21 agent, router LLM, messaging ports
├── config/                     # tham số lao động · quy trình phiếu · taxonomy · ngưỡng hao hụt
├── data/
│   ├── seed/                   # sample.json — dữ liệu mẫu xếp lịch
│   ├── fixtures/ · golden/      # dữ liệu kiểm thử tất định
│   ├── uploads/                 # ảnh TKB, minh chứng upload
│   └── out/                     # KV runtime (lich_tuan, cam_nang, brief…)
├── infra/
│   ├── docker/                  # compose.yml — postgres·redis·api·worker·web
│   ├── templates/               # phiếu YAML: mo_quan, dong_quan, ban_giao_ca
│   ├── aws/ · oracle/           # runbook triển khai cloud
├── skills/                      # 13 skill + 1 router + skills_index.jsonl (SHA256)
├── scripts/                     # 143 script Python: demo, eval, seed, docker_stack.py, metrics…
├── plans/                       # kế hoạch & nhật ký triển khai theo phiên
└── docs/                        # 21 ADR · 16 runbook · hướng dẫn · hồ sơ
```

| Thành phần | Đường dẫn | Vai trò |
|:-----------|:----------|:--------|
| Hợp đồng dữ liệu | `packages/contracts` | Pydantic models + JSON Schema + TypeScript types |
| Solver | `packages/solver` | CP-SAT, ràng buộc cứng C01–C06, soft, công bằng 4 trục |
| Cổng VF | `packages/gates` | VF-TRACE, VF-CONF, VF-SCHEMA, VF-RULE, VF-SCOPE, VF-STALE, VF-NUM |
| Ops | `packages/opsengine` | Phiếu checklist, việc treo, nhắc quá hạn |
| Playbook | `packages/playbook` | Cẩm nang 8 bước, ghi nhận sửa, distiller |
| Agents | `packages/agents` | AG-COPILOT + 35 tool whitelist + agent chuyên trách + router LLM + messaging |
| API | `apps/api` | FastAPI · SQLite/Postgres · worker nền |
| Web | `apps/web` | Next.js PWA (quản lý, NV, inbox, page quán, gmail) |
| Infra | `infra/docker` | Compose 5 dịch vụ |
| Skills | `skills/` | 14 kỹ năng vận hành đã kiểm định (13 skill + 1 router) |

---

<a id="yeu-cau"></a>
## Yêu cầu môi trường

| Công cụ | Phiên bản | Ghi chú |
|:--------|:----------|:--------|
| ![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white) | ≥ 3.12 | Khuyến nghị dùng `uv` |
| ![Node](https://img.shields.io/badge/Node.js-339933?logo=nodedotjs&logoColor=white) | ≥ 20 | Cho web |
| ![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white) | Docker Desktop | Khuyến nghị demo toàn tuyến |
| `.env` | ở root | Copy từ `.env.example` — **không commit** |

---

<a id="cai-dat"></a>
## Cài đặt

### 1. Clone

```bash
git clone https://github.com/KanTrun/Crew-Operations.git
cd Crew-Operations
```

> [!WARNING]
> **Windows:** BuildKit có thể lỗi khi đường dẫn clone có ký tự non-ASCII. Clone/junction sang đường dẫn ASCII, ví dụ `mklink /J C:\nhipquan "D:\CA-CÔNG-BẰNG"` — chi tiết [`docs/runbook-demo.md`](./docs/runbook-demo.md).

### 2. Cấu hình môi trường

```bash
cp .env.example .env        # Windows: copy .env.example .env
# Mặc định CA_AGENT_MODE=live trong .env.example; đặt lại "replay" nếu muốn chạy offline.
# Điền key LLM / kênh tin / SerpApi nếu muốn bật tính năng tương ứng.
```

### 3. Cách A — Docker toàn tuyến (khuyến nghị)

```bash
make docker-up              # = python scripts/docker_stack.py up
make docker-ps              # chờ các container healthy
make docker-smoke           # kiểm toàn tuyến backend
make docker-seed-ops        # (tuỳ chọn) nạp 6 bề mặt vận hành
```

Web ở `http://localhost:3000`, API + OpenAPI ở `http://localhost:8000/docs`.

### 3. Cách B — Local (không Docker)

```bash
# 1. Cài Python packages (editable) + npm web
make setup                  # pip install -e ./packages/* -e ./apps/api + npm install

# 2. Seed dữ liệu demo (19 nhân viên, idempotent)
python scripts/seed_19_staff.py      # hoặc: make seed-demo (đầy đủ hơn)

# 3. Chạy API (terminal 1)
cd apps/api
uv run uvicorn ca_api.interfaces.http.main:app --reload --port 8000
#   (không dùng uv: python -m uvicorn ca_api.interfaces.http.main:app --reload --port 8000)

# 4. Chạy worker nền (terminal 2)
python -m ca_api.worker

# 5. Chạy web (terminal 3)
cd apps/web && npm run dev
```

> [!TIP]
> Nếu không đặt `DATABASE_URL`, hệ thống dùng **SQLite** mặc định (`data/quan.db`) — không cần Postgres để chạy local.

<details>
<summary><b>Migration Postgres (Alembic)</b></summary>

<br/>

```bash
# File cấu hình: apps/api/alembic/alembic.ini
export DATABASE_URL=postgresql+psycopg://nhipquan:nhipquan@localhost:5433/nhipquan
cd apps/api
uv run alembic -c alembic/alembic.ini upgrade head         # áp mọi migration
uv run alembic -c alembic/alembic.ini downgrade -1          # lùi 1 bước
uv run alembic -c alembic/alembic.ini revision -m "mo_ta"   # tạo migration mới
```

</details>

---

<a id="huong-dan-chay"></a>
## Hướng dẫn chạy

### Dịch vụ & URL

| Dịch vụ | URL / cổng |
|:--------|:-----------|
| 🌐 **Web PWA (production)** | [https://nhipquan.duckdns.org/](https://nhipquan.duckdns.org/) |
| Web PWA (local Docker) | http://localhost:3000 |
| API + OpenAPI docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Postgres | `localhost:5433` (container 5432) |
| Redis | `localhost:6379` |

Dừng: `make docker-down` · Xóa volume: `make docker-reset`

### Chạy local từng phần

| Việc | Lệnh |
|:-----|:-----|
| API dev | `uvicorn ca_api.interfaces.http.main:app --reload --port 8000` (từ `apps/api`) |
| Worker nền | `python -m ca_api.worker` |
| Web dev | `cd apps/web && npm run dev` |
| Demo API script | `make demo-local` (`python scripts/demo_api.py`) |
| Seed 6 bề mặt vận hành | `make seed-ops` |
| Seed toàn bộ demo | `make seed-demo` |
| Reset demo Docker | `make demo-reset` |

### Worker nền làm gì

`ca_api.worker` chạy việc định kỳ (mỗi job một khoá mốc, idempotent):

| Giờ | Job | Kết quả |
|:----|:----|:--------|
| 06:00 | `brief_sang` | Sinh bản tin sáng (ca hôm nay, treo, tồn cảnh báo) → kv `brief_hom_nay` |
| 22:00 Chủ nhật | `solver_tuan` | CP-SAT tuần sau → kv `worker_de_xuat_lich` **chờ quản lý duyệt** (worker không tự công bố) |
| 23:00 | `tong_ket_ngay` | Gom tiêu thụ/hao phí trong ngày |

<details>
<summary><b>Chi tiết hành vi của worker & ca trống</b></summary>

<br/>

- Nhắc phiếu quá hạn 2 cấp (nhắc NV → báo chủ quán), mỗi cặp (phiếu, cấp) chỉ nhắn một lần.
- Ca thiếu sau CP-SAT được lưu thành `open_shift`; nhân viên nhận qua `POST /api/v1/open-shifts/claim` với xác nhận availability đúng tuần. Claim đầu tiên được bảo vệ bằng transaction.
- Mỗi lần chạy lịch tạo một `schedule_run` có version, snapshot input, fingerprint và idempotency key; chạy lại cùng key với input khác sẽ bị từ chối.
- Quản lý xử lý ca thiếu bằng `POST /api/v1/lich/resolve-gaps`; hệ thống revalidate ràng buộc, chạy lại CP-SAT và lưu assignment authoritative trước khi chuyển sang chờ duyệt.
- Chỉ run authoritative còn mới và đầy đủ mới được chuyển `da_duyet` hoặc `da_cong_bo`; khi công bố, thông báo được gửi tới nhân viên của đúng tuần.
- `GET /api/v1/chat/scheduler` trả về hội thoại riêng duy nhất giữa nhân viên và `ai_scheduler`.
- Worker đánh dấu và báo quản lý các open shift quá hạn; SLA mặc định 120 phút, cấu hình bằng `OPEN_SHIFT_SLA_MINUTES`.

</details>

---

<a id="tai-khoan-demo"></a>
## Tài khoản demo

> [!IMPORTANT]
> Mật khẩu mọi tài khoản: **`nhipquan`**. Danh sách đầy đủ 19 NV: [`docs/runbook-demo.md`](./docs/runbook-demo.md).

| Tài khoản | Vai trò | Dùng để |
|:----------|:--------|:--------|
| `lan` | `quan_ly` | Người phê duyệt chính — inbox, duyệt đổi ca, xếp lịch |
| `hung` | `chu_quan` | Nâng/hạ vai, audit, chốt luật cẩm nang |
| `minh` | `nhan_vien` | Ca sáng, bind Telegram demo |
| `chi` | `nhan_vien` | TKB xung đột T2, bind Zalo demo |
| `rosa` | `nhan_vien` | Mới đăng ký — demo onboarding |

Đăng nhập lấy token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"lan","password":"nhipquan"}'
# → {"token":"...","role":"quan_ly","nv_id":"nv_01",...}
# Dùng: Authorization: Bearer <token>
```

---

<a id="bien-moi-truong"></a>
## Biến môi trường

> Danh sách đầy đủ nằm ở [`.env.example`](./.env.example) (~161 dòng, có chú thích). Copy sang `.env` rồi điền. **Không** commit file `.env`.

<details open>
<summary><b>Lõi hệ thống & LLM</b></summary>

<br/>

| Biến | Mục đích |
|:-----|:---------|
| `CA_AGENT_MODE` | `replay` (mặc định, CI) hoặc `live` (LLM thật) |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` / `BAI_API_KEY` | Router LLM khi live |
| `GROQ_MODEL` / `GEMINI_MODEL` / `OPENROUTER_MODEL` / `BAI_MODEL` | Chọn model từng provider |
| `GEMINI_TRANSCRIBE_MODEL` | Model Gemini cho STT (biên bản họp) |
| `BAI_BASE_URL` | Base URL B.ai (mặc định `https://api.b.ai/v1`) |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Fallback local (tuỳ chọn) |
| `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` | Cloudflare Workers AI — provider **chính** sinh/sửa ảnh quảng cáo menu; free 10.000 neurons/ngày (cần **cả hai** biến) |
| `CLOUDFLARE_IMAGE_MODEL` | Model sinh ảnh Cloudflare (trống = `@cf/black-forest-labs/flux-2-klein-4b`) |
| `GEMINI_IMAGE_MODEL` | Model ảnh Gemini (dự phòng khi thiếu Cloudflare) |
| `POLLINATIONS_API_KEY` / `POLLINATIONS_IMAGE_MODEL` | Pollinations — phương án hai cho chế độ sửa ảnh thật (`edit_photo`, image-to-image) |
| `POLLINATIONS_MODEL` | Model text-to-image Pollinations (mặc định `flux`; ghim để tắt fallback `turbo`) |
| `DATABASE_URL` | Postgres (mặc định SQLite `data/quan.db`) |
| `REDIS_URL` | Redis Pub/Sub realtime |
| `NEXT_PUBLIC_API_URL` | Base URL API cho web |
| `NEXT_PUBLIC_GEMINI_LIVE_VOICE_ENABLED` | Bật Copilot Voice trên web |
| `DOMAIN` | Domain production (dùng cho reverse proxy / CORS) |
| `NHIPQUAN_CORS_ORIGINS` | Danh sách origin cách nhau dấu phẩy (điền sẽ **ghi đè** mặc định dev — để trống khi chạy local) |
| `NHIPQUAN_PUBLIC_API_DOCS` | `0` để tắt `/docs`, `/redoc`, `/openapi.json` khi vận hành thật (mặc định bật cho demo) |
| `NHIPQUAN_SEED_DEMO` | Seed dữ liệu demo khi khởi động (tắt ở quán thật) |
| `NHIPQUAN_LOI_GIAI_SEED` | Thêm NV mẫu ADR-012 vào pool xếp lịch (chỉ dev/demo) |
| `NHIPQUAN_INBOX_SEED_FIXTURE` / `NHIPQUAN_PAGE_SEED_FIXTURE` | Nhồi fixture inbox/Page (chỉ CI) |
| `OPEN_SHIFT_SLA_MINUTES` | SLA trước khi escalate open shift, mặc định `120` |
| `NHIPQUAN_PBKDF2_VONG` | Số vòng PBKDF2 băm mật khẩu |

</details>

<details open>
<summary><b>Kênh tin & Page</b></summary>

<br/>

| Biến | Mục đích |
|:-----|:---------|
| `NHIPQUAN_MSG_BACKEND` | `telegram` · `zalo` · `console` |
| `NHIPQUAN_ZALO_ENABLED` / `NHIPQUAN_ZALO_OA_ACCESS_TOKEN` | Zalo OA (kênh ưu tiên VN) |
| `NHIPQUAN_TELEGRAM_BOT_TOKEN` / `NHIPQUAN_TELEGRAM_WEBHOOK_SECRET` | Telegram bot |
| `NHIPQUAN_FB_PAGE_TOKEN` / `NHIPQUAN_FB_PAGE_ID` | Facebook Page |
| `NHIPQUAN_FB_APP_SECRET` | App secret Meta (verify chữ ký) |
| `NHIPQUAN_FB_AUTO_SEND` | Tự động gửi phản hồi Page (`0`/`1`) |
| `NHIPQUAN_PAGE_MODE` | `live` khi nối Meta, `replay`/`disconnected` |
| `NHIPQUAN_FB_WEBHOOK_VERIFY` | Verify token webhook Messenger |
| `NHIPQUAN_SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_FROM` | Gửi Gmail qua SMTP (App Password) |
| `NHIPQUAN_GMAIL_CLIENT_ID` / `NHIPQUAN_GMAIL_CLIENT_SECRET` | OAuth 2.0 — quản lý hộp thư Gmail (`/gmail`) |
| `NHIPQUAN_GMAIL_REDIRECT_URI` | Redirect URI khai trên Google Cloud Console |
| `NHIPQUAN_ENCRYPTION_KEY` | Khoá Fernet mã hoá OAuth token trong DB (**bắt buộc** nếu dùng Gmail OAuth) |
| `NHIPQUAN_ALLOW_MSG_REPLAY` | Chỉ bật khi pytest kênh tin |

</details>

<details open>
<summary><b>Khảo sát giá, xu hướng & Copilot Voice</b></summary>

<br/>

| Biến | Mục đích |
|:-----|:---------|
| `SERPAPI_API_KEY` | Khóa SerpApi (**bắt buộc** cho AG-PRICING) |
| `SERPAPI_ENABLED` | Bật/tắt SerpApi (`true`/`false`) |
| `SERPAPI_MONTHLY_LIMIT` | Giới hạn request SerpApi mỗi tháng (ví dụ `250`) |
| `SERPAPI_SAFETY_MARGIN` / `SERPAPI_WARN_THRESHOLD` / `SERPAPI_INFO_THRESHOLD` | Ngưỡng cảnh báo quota |
| `SERPAPI_CIRCUIT_BREAKER_FAILURE_THRESHOLD` / `_OPEN_SECONDS` | Circuit breaker |
| `SERPAPI_CACHE_TTL_MAPS_HOURS` / `_PHOTOS_DAYS` / `_TRENDS_HOURS` / `_TRENDING_NOW_HOURS` | TTL cache theo từng loại truy vấn |
| `THREADS_ACCESS_TOKEN` | Threads Official API — tier 0 tìm kiếm xu hướng |
| `CA_CAMOUFOX_ENABLED` / `_HEADLESS` / `_TIMEOUT_S` / `_MAX_CONCURRENT` / `_CACHE_TTL_S` | Tier cào browser-thật (tuỳ chọn) |
| `JEV_API_KEY` / `JEV_ENABLED` | Sensor xác suất JEV (**mặc định tắt**, fail-closed) |
| `VOICE_IDLE_TIMEOUT_SECONDS` | Ngắt phiên Copilot Voice khi im lặng (ví dụ `60`) |
| `VOICE_SESSION_MAX_SECONDS` | Thời lượng tối đa một phiên Copilot Voice (ví dụ `300`) |

```bash
# Khảo sát giá thị trường (AG-PRICING)
SERPAPI_API_KEY=
SERPAPI_ENABLED=true
SERPAPI_MONTHLY_LIMIT=250

# Copilot Voice (Gemini Live)
VOICE_IDLE_TIMEOUT_SECONDS=60
VOICE_SESSION_MAX_SECONDS=300
```

</details>

**Runbook kết nối:** [Telegram](./docs/runbooks/telegram-bot-connect.md) · [Zalo](./docs/runbooks/zalo-oa-connect.md) · [Facebook Page](./docs/runbooks/facebook-page-connect.md) · [Gmail OAuth](./docs/runbooks/gmail-oauth-connect.md) · [SerpApi](./docs/runbooks/serpapi-integration.md)

---

<a id="makefile"></a>
## Makefile

| Lệnh | Mô tả |
|:-----|:------|
| `make setup` | Cài Python editable + npm web |
| `make dev` | Chạy API dev (reload) |
| `make test` / `test-unit` | Pytest toàn monorepo (`CA_AGENT_MODE=replay`) |
| `make lint` | Ruff + `tsc --noEmit` web |
| `make bench` | Solver tuần + `verify_hard` |
| `make eval` | AG-TKB, AG-MSG, nhóm A §18.2 |
| `make ab` / `make replay PHIEN=<key>` | Báo cáo A/B / replay orchestration |
| `make metrics` | 7 con số §18.2 trên fixture ADR-012 |
| `make seed` / `seed-ops` / `seed-demo` / `seed-danh-muc` | Sinh fixture / 6 bề mặt / toàn bộ demo / danh mục món |
| `make docker-up/down/ps/logs/smoke/reset/seed-ops` | Stack Docker qua `scripts/docker_stack.py` |
| `make demo` / `demo-local` / `demo-reset` | Demo API / demo local / reset Docker |
| `make test-fb` / `test-fb-post` | Kiểm tra / đăng Facebook Page |
| `make canary` | Canary tier scraping bên thứ ba (không chặn merge, luôn exit 0) |
| `make budget` | Nhắc ngân sách request/quota dịch vụ ngoài (stub — xem [`docs/THIRD_PARTY.md`](./docs/THIRD_PARTY.md)) |
| `make review` / `review-fast` | Bộ cổng kiểm tra trước khi merge |
| `make contracts` | Sinh hợp đồng dữ liệu (Pydantic → JSON Schema + TS types) |
| `make install-hooks` | Cài git hook (commitlint + secret scan) |
| `make migrate-neon` | Migration lên Postgres (Neon) |
| `make sinh-anh` | Sinh ảnh sản phẩm tại máy (ADR-019) |

> [!CAUTION]
> Gọi Docker qua `scripts/docker_stack.py` (wrapper tắt BuildKit, ghim tên project ASCII) — **không** gọi `docker compose` trực tiếp.

---

<a id="api-reference"></a>
## API Reference

**Base URL:** `http://localhost:8000` · **OpenAPI:** [`/docs`](http://localhost:8000/docs) · **Auth:** `Authorization: Bearer <token>` từ `/api/v1/auth/login`

**Chú giải quyền:**

| 🟢 | 🔵 | 🟡 | 🔴 |
|:--:|:--:|:--:|:--:|
| Công khai | Mọi vai đã đăng nhập | `quan_ly` + `chu_quan` | `chu_quan` |

> Bấm vào từng nhóm bên dưới để mở rộng.

<details>
<summary><b>Health & Auth</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/health` | 🟢 | Trạng thái service + `minimal_data_mode` |
| POST | `/api/v1/auth/register` | 🟢 | Đăng ký NV mới (luôn vai `nhan_vien`), trả token luôn. Body: `username`, `password`, `display_name` |
| POST | `/api/v1/auth/login` | 🟢 | Đăng nhập → `token`, `role`, `nv_id`, `store_id` |
| GET | `/api/v1/me` | 🔵 | Thông tin phiên hiện tại |
| GET | `/api/v1/contracts` | 🟢 | 5 hợp đồng dữ liệu mẫu (ADR-012) |

</details>

<details>
<summary><b>Lịch tuần (roster)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/lich-tuan?tuan=2026-W36&so_tuan=1..4` | 🟡 | Lịch tuần hiệu lực: phân công, khung giờ, trạng thái lifecycle, solver meta |
| PATCH | `/api/v1/lich-tuan/khung-gio` | 🟡 | Sửa template giờ 3 khung (sáng/chiều/tối). Body: `{sang:{bat_dau,ket_thuc},…}` |
| POST | `/api/v1/lich-tuan/pin` | 🟡 | Ghim/bỏ ghim NV vào ca. Body: `ca_id`, `nv_id`, `pinned` |
| PATCH | `/api/v1/lich-tuan/lifecycle` | 🟡 | Chuyển trạng thái lịch; `dang_giai` chạy solver ngay rồi sang `cho_duyet`. Chỉ 🔴 đổi `tuan_iso` |
| GET | `/api/v1/lich/lifecycle` | 🔵 | Trạng thái lifecycle hiện tại |
| POST | `/api/v1/lich/lifecycle` | 🟡 | Chuyển trạng thái theo ma trận hợp lệ; `da_dong`/mở lại cần 🔴 + lý do |
| GET | `/api/v1/lich/ics` | 🔵 | Xuất lịch dạng iCalendar |
| GET | `/api/v1/lich/xlsx` | 🔵 | Xuất lịch dạng Excel |
| GET | `/api/v1/lich/pdf` | 🔵 | Xuất lịch dạng PDF |
| GET | `/api/v1/ops/pickers` | 🔵 | NV + ca cho dropdown |

</details>

<details>
<summary><b>Ca trống (Open Shifts)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/api/v1/open-shifts` | 🟡 | Tạo ca trống |
| GET | `/api/v1/open-shifts` | 🔵 | Danh sách ca trống |
| POST | `/api/v1/open-shifts/claim` | 🔵 | Nhận ca (transaction-safe — claim đầu tiên thắng) |

</details>

<details>
<summary><b>Phiếu & điểm danh (opsengine)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/api/v1/diem-danh` | 🔵 | Điểm danh NV trong ca |
| GET | `/api/v1/phieu/mau` | 🟢 | Liệt kê mọi mẫu phiếu trong `infra/templates/` |
| POST | `/api/v1/phieu/start` | 🔵 | Bắt đầu phiếu (yêu cầu đã điểm danh). Body: `mau`, `ca_id` |
| GET | `/api/v1/phieu/{phieu_id}` | chủ phiếu/🟡 | Trạng thái phiếu + tín hiệu escalate |
| POST | `/api/v1/phieu/{phieu_id}/buoc` | chủ phiếu/🟡 | Hoàn thành bước theo đúng thứ tự. Body: `ma`, `gia_tri` |
| POST | `/api/v1/phieu/{phieu_id}/minh-chung` | chủ phiếu/🟡 | Nộp ảnh minh chứng (data URL ≤ 400KB) |
| POST | `/api/v1/phieu/{phieu_id}/treo` | chủ phiếu/🟡 | Treo việc từ phiếu. Body: `noi_dung` |
| GET | `/api/v1/viec-treo` | 🔵 | Danh sách việc treo |
| PATCH | `/api/v1/viec-treo/{treo_id}` | 🟡 | Đóng việc treo (`trang_thai: xong`) |
| POST | `/api/v1/orc/dispatch` | 🟡 | Dispatch N task song song, idempotent theo `key` |

</details>

<details>
<summary><b>Hộp thư & ràng buộc</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/inbox` | 🟡 | Hộp thư tin nhắn nội bộ |
| POST | `/api/v1/inbox` | 🟡 | Thêm mục hộp thư. Body: `tom_tat`, `agent` |
| POST | `/api/v1/msg/classify` | 🔵 | AG-MSG phân loại tin. Body: `text`, `backend` |
| GET | `/api/v1/inbox/rang-buoc` | 🟡 | Hộp thư ràng buộc ca (kèm gợi ý đổi ca) |
| POST | `/api/v1/inbox/rang-buoc/{item_id}` | 🟡 | Duyệt/từ chối; duyệt đổi ca cần `ca_id`+`doi_tac_nv_id` |
| GET | `/api/v1/inbox/candidates/{item_id}` | 🟡 | Xếp hạng ứng viên đổi ca |
| POST | `/api/v1/inbox/rang-buoc/{item_id}/smart-approve` | 🟡 | Duyệt 1-chạm với ứng viên AI đề xuất |

</details>

<details>
<summary><b>TKB (thời khoá biểu)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/api/v1/tkb/extract` | 🔵 | AG-TKB trích TKB từ ảnh. Body: `image_path_or_id` |
| POST | `/api/v1/tkb/upload` | 🔵 | Upload ảnh TKB (≤ 8MB) hoặc dùng `fixture_id` → extract |
| POST | `/api/v1/tkb/confirm` | 🔵 | Xác nhận khoảng bận theo `tuan_iso`, gắn vào NV (NV chỉ gắn cho mình) |

</details>

<details>
<summary><b>Công bằng & hôm nay</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/cong-bang` | 🔵 | Số dư công bằng 4 trục (cuối tuần/đêm/giờ/short); NV chỉ thấy mình |
| GET | `/api/v1/cong-bang/bao-cao` | 🔵 | Báo cáo text/plain, không xếp hạng tên |
| GET | `/api/v1/hom-nay` | 🔵 | Tổng quan hôm nay: lịch, treo, inbox chờ, tồn, `viec_cho_toi` |
| GET | `/api/v1/tieu-thu` | 🔵 | Sổ tiêu thụ nguyên liệu |
| POST | `/api/v1/tieu-thu` | 🟡 | Ghi tiêu thụ. Body: `hang`, `so_luong`, `don_vi` |
| POST | `/api/v1/waste` | 🔵 | Ghi chú hao phí. Body: `thu`, `ghi_chu` |
| GET | `/api/v1/waste` | 🔵 | Cụm hao phí (AG-WASTE) + ghi chú gốc |

> Hao hụt nguyên liệu (lý thuyết ↔ thực tế): xem mục **Hao hụt nguyên liệu** bên dưới.

</details>

<details>
<summary><b>Bàn giao & cẩm nang</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/handover` | 🔵 | Lịch sử bàn giao |
| POST | `/api/v1/handover` | 🔵 | Trích bàn giao (AG-HANDOVER) + VF-NUM + phát hiện mâu thuẫn |
| GET | `/api/v1/cam-nang` | 🔵 | Luật cẩm nang + mẫu + pipeline snapshot |
| POST | `/api/v1/cam-nang/chay-8-buoc` | 🟡 | Chạy pipeline 8 bước từ lần sửa thật (≥ 3 mẫu) |
| POST | `/api/v1/cam-nang/duyet` | chốt cần 🔴 | Duyệt/từ chối luật `cho_chu_quan`. Body: `id`, `ok` |
| POST | `/api/v1/cam-nang/go` | 🔴 | Gỡ luật hiệu lực. Body: `id` |
| POST | `/api/v1/sop` | 🔵 | Hỏi đáp SOP (AG-SOP). Body: `question`, `ngu_canh` |
| GET | `/api/v1/sop/golden` | 🔵 | Chạy bộ câu hỏi golden — mọi câu có nguồn hoặc `chua_co` |

</details>

<details>
<summary><b>Tự giải thích (Self-Explaining System) — AG-EXPLAIN</b></summary>

<br/>

Prefix: `/api/v1/ops/explain`. Agent: **AG-EXPLAIN** — dịch mã lý do của solver thành câu tiếng Việt có căn cứ (grounded).

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/explain` | 🔵 | Chuỗi nhân quả cho câu hỏi "tại sao" |
| GET | `/chains` | 🔵 | Danh sách chuỗi nhân quả |
| POST | `/episodes` | 🔵 | Ghi episode |
| POST | `/reflect` | 🔵 | Reflection |

</details>

<details>
<summary><b>Playbook dự đoán & Digital Twin — AG-PREDICT · AG-TWIN</b></summary>

<br/>

Prefix: `/api/v1/ops`. Agents: **AG-PREDICT** (phát hiện mẫu thành công → đề xuất luật tích cực) và **AG-TWIN** (mô phỏng "nếu… thì…" bằng Math Layer).

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/predict/suggestions` | 🔵 | Đề xuất luật tích cực |
| POST | `/predict/run` | 🟡 | Trigger phát hiện mẫu |
| POST | `/predict/{rule_id}/approve` | 🟡 | Duyệt luật tích cực |
| POST | `/twin/simulate` | 🟡 | Mô phỏng kịch bản |
| GET | `/twin/scenarios` | 🔵 | Danh sách kịch bản |
| POST | `/twin/virtual-staff` | 🟡 | Mô phỏng nhân sự ảo |

</details>

<details>
<summary><b>Khảo sát giá thị trường — AG-PRICING</b></summary>

<br/>

Prefix: `/api/v1/market`. Agent: **AG-PRICING** (SerpApi + Vision). Job chạy bất đồng bộ; giá OCR không chắc chắn chuyển `NEEDS_REVIEW` chờ người xác nhận.

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/catchment-survey` | 🟡 | Tạo job khảo sát (trả `202` + `job_id`) |
| GET | `/catchment-survey/{job_id}` | 🔵 | Trạng thái job |
| GET | `/catchment-survey/{job_id}/result` | 🔵 | Kết quả khảo sát |
| POST | `/catchment-survey/{job_id}/review` | 🟡 | Xác nhận giá OCR (`NEEDS_REVIEW`) |
| GET | `/catchment-survey-metrics` | 🔵 | Chi phí Vision & nguồn dữ liệu |
| GET | `/catchment-survey-dashboard` | 🔵 | Dashboard tổng hợp |
| GET | `/serpapi/quota` | 🔵 | Hạn ngạch SerpApi còn lại (đầy đủ: `/api/v1/market/serpapi/quota`) |

</details>

<details>
<summary><b>Hao hụt nguyên liệu (lý thuyết ↔ thực tế)</b></summary>

<br/>

Đối chiếu định mức tiêu hao với thực tế ghi nhận, xếp hạng nguyên nhân. Ngưỡng đọc từ `config/nguong-hao-hut.yaml`.

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/hao-hut` | 🔵 | Hao hụt theo nguyên liệu: lý thuyết ↔ thực tế, mức độ, xếp hạng nguyên nhân. `?ky=hom_nay\|tuan\|thang\|all` |
| POST | `/api/v1/hao-hut` | 🔵 | Ghi hao hụt có mặt hàng + nguyên nhân (có vết audit). Body: `mat_hang`, `so_luong`, `don_vi`, `nguyen_nhan`, `thu` |
| GET | `/api/v1/hao-hut/nguong` | 🔵 | Ngưỡng hao hụt đang áp dụng |
| GET | `/api/v1/hao-hut/danh-muc` | 🟡 | Mã mặt hàng gợi ý, gộp từ kiểm kê + ghi chú + công thức món |

UI: `/hao-phi` · e2e: `apps/web/e2e/hao-hut.spec.ts`

</details>

<details>
<summary><b>QR & đổi ca</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/api/v1/qr` | 🟡 | Phát mã QR điểm danh một lần. Body: `nv_id`, `ca_id` |
| POST | `/api/v1/qr/{token}` | 🔵 | Dùng mã QR (chủ NV, một lần) |
| POST | `/api/v1/cho-doi-ca` | người tham gia | Mở phiếu đổi ca 3 người. Body: `a`, `b`, `c`, `ca_id` |
| GET | `/api/v1/cho-doi-ca` | 🔵 | Danh sách phiếu đổi ca |
| POST | `/api/v1/cho-doi-ca/{swap_id}/dong-y` | người tham gia | Đồng ý tham gia đổi ca |
| POST | `/api/v1/cho-doi-ca/{swap_id}/tu-choi` | người tham gia | Từ chối đổi ca |

</details>

<details>
<summary><b>Menu & quầy POS</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/menu` | 🔵 | Menu đang bán |
| GET | `/api/v1/menu/quan-tri` | 🟡 | Menu toàn bộ (kèm ẩn) |
| PUT | `/api/v1/menu/{mon_id}` | 🟡 | Sửa món (tên, giá, ẩn, BOM) |
| GET | `/api/v1/menu/{mon_id}/anh` | 🟢 | Ảnh món |
| POST | `/api/v1/menu/{mon_id}/anh` | 🟡 | Upload ảnh món |
| GET | `/api/v1/quay/don` | 🔵 | Đơn quầy nội bộ |
| POST | `/api/v1/quay/don` | 🔵 (đã điểm danh) | Tạo đơn theo menu. Body: `dong:[{mon_id,so_luong}]` |
| POST | `/api/v1/quay/don/{don_id}/chuyen` | chủ đơn/🟡 | Chuyển trạng thái (`cho_pha→dang_pha→xong/huy`) |
| POST | `/api/v1/quay/don/{don_id}/chinh` | chủ đơn/🟡 | Sửa số lượng dòng |
| GET | `/api/v1/quay/bao-cao` | 🔵 | Báo cáo quầy |

</details>

<details>
<summary><b>Người dùng & vai trò</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/nguoi` | 🔵 | Danh sách người dùng |
| POST | `/api/v1/nguoi/{username}/nang-vai` | 🔴 | Nâng vai (VD `nhan_vien→quan_ly`) |
| POST | `/api/v1/nguoi/{username}/ha-vai` | 🔴 | Hạ vai |

</details>

<details>
<summary><b>Chat nội bộ (realtime)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| WS | `/ws/chat` | 🔵 (auth trong 5s) | WebSocket chat: `{"event":"auth","token":…}` → `auth:ack` |
| GET | `/api/v1/chat/conversations` | 🔵 | Hội thoại của tôi |
| POST | `/api/v1/chat/conversations` | 🔵 | Tạo hội thoại |
| GET | `/api/v1/chat/conversations/{conv_id}` | thành viên | Chi tiết hội thoại |
| GET | `/api/v1/chat/conversations/{conv_id}/messages` | thành viên | Tin nhắn (phân trang) |
| POST | `/api/v1/chat/conversations/{conv_id}/messages` | thành viên | Gửi tin nhắn |
| POST | `/api/v1/chat/messages/{message_id}/pin` | thành viên | Ghim/bỏ ghim |
| PATCH | `/api/v1/chat/messages/{message_id}` | người gửi | Sửa tin nhắn |
| DELETE | `/api/v1/chat/messages/{message_id}` | người gửi | Xóa tin nhắn |
| POST | `/api/v1/chat/messages/{message_id}/treo` | thành viên | Chuyển tin nhắn thành việc treo |
| POST | `/api/v1/chat/messages/{message_id}/reactions` | thành viên | Thả reaction |
| POST | `/api/v1/chat/conversations/{conv_id}/read` | thành viên | Đánh dấu đã đọc |
| POST | `/api/v1/chat/conversations/{conv_id}/mute` | thành viên | Tắt/bật thông báo |
| GET | `/api/v1/chat/search?q=` | 🔵 | Tìm tin nhắn |
| GET | `/api/v1/chat/online` | 🔵 | NV đang online |
| POST | `/api/v1/chat/upload` | 🔵 | Upload file đính kèm |
| GET | `/api/v1/chat/uploads/{filename}` | 🔵 | Tải file đính kèm |
| GET | `/api/v1/chat/scheduler` | 🔵 | Hội thoại riêng giữa NV và `ai_scheduler` |
| POST | `/api/v1/chat/availability/{id}/confirm` | 🔵 | Xác nhận khả dụng |
| POST | `/api/v1/chat/availability/{id}/correct` | 🔵 | Sửa khả dụng |

</details>

<details>
<summary><b>AG-COPILOT (trợ lý hội thoại)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/api/v1/copilot/message` | 🔵 | Gửi chỉ dẫn ngôn ngữ tự nhiên → `CopilotResponse` (intent, proposal, citations) |
| POST | `/api/v1/copilot/message/stream` | 🔵 | Bản SSE: event `meta` → `delta` → `done` |
| WS | `/api/v1/copilot/voice` | 🔵 | Phiên voice với Gemini Live (giới hạn bởi `VOICE_IDLE_TIMEOUT_SECONDS`, `VOICE_SESSION_MAX_SECONDS`) |
| POST | `/api/v1/copilot/execute-action` | 🔵 | Duyệt/từ chối đề xuất 2 pha. Body: `action_id`, `decision`, `idempotency_key` |
| POST | `/api/v1/copilot/action/{action_id}/amend` | 🔵 | Sửa đề xuất trước khi duyệt (`correction_diff` theo intent) |
| GET | `/api/v1/copilot/action/{action_id}` | 🔵 | Xem đề xuất + snapshot |
| GET | `/api/v1/copilot/audit` | 🔵 | Audit trail copilot |
| GET | `/api/v1/copilot/permissions` | 🔵 | Ma trận role × intent |
| GET | `/api/v1/copilot/capabilities` | 🔵 | Danh mục năng lực theo vai |
| POST | `/api/v1/copilot/navigate` | 🔵 | Đề xuất điều hướng UI |

</details>

<details>
<summary><b>Kênh tin (Telegram / Zalo)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/api/v1/channels/bind/issue` | 🔵 | Phát mã bind NV (nhắn `/bind <mã>` trên kênh) |
| POST | `/api/v1/channels/bind` | 🟡 | Bind thủ công. Body: `channel`, `external_user_id`, `nv_id` |
| GET | `/api/v1/channels/bind` | 🔵 | Danh sách bind (NV chỉ thấy mình) |
| GET | `/api/v1/channels/status` | 🔵 | Trạng thái nối kênh thật — không giả lập |
| POST | `/api/v1/channels/replay` | 🟡 + env | Replay inbound (chỉ CI/test, cần `NHIPQUAN_ALLOW_MSG_REPLAY=1`) |
| POST | `/api/v1/channels/telegram/webhook` | 🟢 + secret | Webhook Telegram (verify `X-Telegram-Bot-Api-Secret-Token`) |
| POST | `/api/v1/channels/zalo/webhook` | 🟢 + token | Webhook Zalo OA |

</details>

<details>
<summary><b>Page quán (Facebook)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/page/status` | 🔵 | Trạng thái Page (mode, connected — token đã redact) |
| POST | `/api/v1/page/sync` | 🟡 | Đồng bộ threads từ Meta |
| GET | `/api/v1/page/threads` | 🔵 | Threads khách nhắn Page |
| POST | `/api/v1/page/threads/{thread_id}/reply` | 🟡 | Soạn/đăng phản hồi (qua moderation) |
| POST | `/api/v1/page/threads/{thread_id}/approve` | 🟡 | Duyệt phản hồi do AI soạn |
| GET | `/api/v1/page/fb-inbox` | 🔵 | Inbox moderation queue |
| GET | `/api/v1/page/fb-inbox/stats` | 🔵 | Thống kê moderation |
| GET | `/api/v1/page/fb-inbox/{item_id}` | 🔵 | Chi tiết một mục |
| POST | `/api/v1/page/fb-inbox/{item_id}/decide` | 🟡 | Quyết định moderation (đăng/sửa/leo thang) |
| GET/PUT | `/api/v1/page/fb-policy` | 🔵/🟡 | Chính sách moderation |
| POST | `/api/v1/page/audit/reflection` | 🟡 | Chạy reflection AI trên audit |
| GET | `/api/v1/page/audit/reflection/latest` | 🔵 | Kết quả reflection gần nhất |
| GET/POST | `/api/v1/page/drafts` | 🔵/🟡 | Danh sách / tạo bài đăng nháp |
| POST | `/api/v1/page/drafts/ai-generate` | 🟡 | AI soạn bài đăng |
| POST | `/api/v1/page/drafts/{id}` | 🟡 | Đăng bài nháp |

</details>

<details>
<summary><b>Hồ sơ quán & khuyến mãi</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET/PUT | `/api/v1/store/profile` | 🔵/🟡 | Hồ sơ quán |
| GET/PUT | `/api/v1/store/promotions` | 🔵/🟡 | Khuyến mãi |

</details>

<details>
<summary><b>Cuộc họp — AG-MEETING</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| POST | `/api/v1/meeting/transcribe` | 🔵 | Audio base64 → transcript diarization |
| POST | `/api/v1/meeting/analyze` | 🔵 | Transcript → hợp đồng `CuocHop` (AG-MEETING) |
| POST | `/api/v1/meeting/process-audio` | 🔵 | 1 bước: upload file → STT → trích xuất |
| POST | `/api/v1/meeting/apply` | 🟡 | Human-in-the-loop: áp action items → việc treo + SOP đề xuất |
| GET | `/api/v1/meetings` | 🔵 | Danh sách cuộc họp đã lưu |

</details>

<details>
<summary><b>Mail</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/me/profile` | 🔵 | Hồ sơ cá nhân |
| PATCH | `/api/v1/me/profile/email` | 🔵 | Cập nhật email cá nhân |
| GET | `/api/v1/users/emails` | 🔵 | Email đồng nghiệp (không PII khác) |
| POST | `/api/v1/mail/send` | 🔵 | Gửi mail (AG-MAILWRITER + quality gate + idempotent) |

</details>

<details>
<summary><b>Đặt bàn</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/reservations?date=&status=` | 🔵 | Danh sách đặt bàn |
| GET | `/api/v1/reservations/tables` | 🔵 | Sơ đồ bàn |
| GET | `/api/v1/reservations/{res_id}` | 🔵 | Chi tiết đơn |
| POST | `/api/v1/reservations/{res_id}/check-in` | 🔵 | Khách nhận bàn (`seated`) |
| POST | `/api/v1/reservations/{res_id}/no-show` | 🔵 | Khách không đến |
| POST | `/api/v1/reservations/{res_id}/complete` | 🔵 | Hoàn tất, giải phóng bàn |
| POST | `/api/v1/reservations/{res_id}/cancel` | 🔵 | Hủy đặt bàn |

</details>

<details>
<summary><b>Skills (thư viện kỹ năng)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/skills` | 🟢 | Danh mục 14 kỹ năng + SHA256 |
| GET | `/api/v1/skills/{skill_id}` | 🟢 | Nội dung SKILL.md + scripts + references |
| POST | `/api/v1/skills/{skill_id}/verify` | 🟢 | Chạy smoke test kỹ năng ngay |
| POST | `/api/v1/skills/distill-sop` | 🟡 | Chưng cất SOP → Skill (Hybrid mode) |

</details>

<details>
<summary><b>AI Learning (học từ phản hồi)</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/ai/rules/proposals` | 🔵 | Đề xuất luật AI chờ duyệt |
| GET | `/api/v1/ai/generations` | 🔵 | Lịch sử sinh nội dung AI |
| POST | `/api/v1/ai/feedback` | 🔵 | Ghi phản hồi người dùng (đã sửa/chưa) |
| GET | `/api/v1/ai/evaluations/summary` | 🔵 | Tổng hợp đánh giá |
| GET | `/api/v1/ai/operations/status` | 🔵 | Trạng thái vận hành AI |
| POST | `/api/v1/ai/operations/circuit-breaker` | 🟡 | Bật/tắt circuit breaker |
| GET | `/api/v1/ai/retention/dry-run` | 🔴 | Xem trước dữ liệu sẽ bị xóa theo retention |
| POST | `/api/v1/ai/reflection/gmail/run` | 🟡 | Reflection trên mail đã gửi |
| POST | `/api/v1/ai/reflection/facebook/run` | 🟡 | Reflection trên phản hồi Page |
| POST | `/api/v1/ai/rules/proposals/{id}/approve` | 🟡 | Duyệt đề xuất luật |
| POST | `/api/v1/ai/rules/proposals/{id}/activate` | 🟡 | Kích hoạt luật |
| POST | `/api/v1/ai/rules/proposals/{id}/reject` | 🟡 | Từ chối đề xuất |
| POST | `/api/v1/ai/rules/{id}/pause` | 🟡 | Tạm dừng luật |
| POST | `/api/v1/ai/rules/{id}/rollback` | 🟡 | Rollback luật |

</details>

<details>
<summary><b>Quản lý Gmail (OAuth — hộp thư, nhãn, bộ lọc)</b></summary>

<br/>

Xem [`docs/runbooks/gmail-oauth-connect.md`](./docs/runbooks/gmail-oauth-connect.md).
Giao diện: `/gmail`.

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/gmail/oauth/authorize` | 🔵 | Lấy URL uỷ quyền Google (503 nếu chưa cấu hình client) |
| GET | `/api/v1/gmail/oauth/callback` | 🟢 | Google chuyển hướng trình duyệt về đây (không cần token — `state` chống CSRF là bằng chứng phiên); tự redirect về `/gmail` |
| POST | `/api/v1/gmail/oauth/callback` | 🔵 | Cùng luồng nhưng dạng JSON cho app gọi trực tiếp |
| POST | `/api/v1/gmail/oauth/revoke` | 🟡 | Thu hồi quyền truy cập Google |
| GET | `/api/v1/gmail/accounts` | 🔵 | Danh sách tài khoản (NV chỉ thấy của mình) |
| POST | `/api/v1/gmail/accounts` | 🔵 | Thêm tài khoản thủ công (chưa có token) |
| GET | `/api/v1/gmail/accounts/{id}` | 🔵 | Chi tiết tài khoản + trạng thái token/đồng bộ |
| PATCH | `/api/v1/gmail/accounts/{id}` | 🟡 | Đổi tên hiển thị / tài khoản chính |
| DELETE | `/api/v1/gmail/accounts/{id}` | 🟡 | Xoá tài khoản (cascade token, mail, nhãn, bộ lọc) |
| GET | `/api/v1/gmail/accounts/{id}/messages` | 🔵 | Hộp thư đã đồng bộ (lọc nhãn/từ khoá/đã đọc) |
| GET | `/api/v1/gmail/accounts/{id}/messages/{msg}` | 🔵 | Chi tiết một email |
| POST | `/api/v1/gmail/accounts/{id}/messages/{msg}/read` | 🔵 | Đánh dấu đã đọc / chưa đọc |
| POST | `/api/v1/gmail/accounts/{id}/messages/{msg}/star` | 🔵 | Gắn / bỏ gắn sao |
| GET | `/api/v1/gmail/accounts/{id}/labels` | 🔵 | Danh sách nhãn |
| POST | `/api/v1/gmail/accounts/{id}/labels` | 🟡 | Tạo nhãn trên Gmail |
| PATCH | `/api/v1/gmail/accounts/{id}/labels/{label}` | 🟡 | Sửa nhãn (tên, màu, hiển thị) |
| DELETE | `/api/v1/gmail/accounts/{id}/labels/{label}` | 🟡 | Xoá nhãn |
| GET | `/api/v1/gmail/accounts/{id}/filters` | 🔵 | Danh sách bộ lọc |
| POST | `/api/v1/gmail/accounts/{id}/filters` | 🟡 | Tạo bộ lọc trên Gmail |
| DELETE | `/api/v1/gmail/accounts/{id}/filters/{filter}` | 🟡 | Xoá bộ lọc |
| POST | `/api/v1/gmail/sync` | 🟡 | Đồng bộ tăng dần hoặc toàn bộ (một tài khoản / cả quán) |
| GET | `/api/v1/gmail/accounts/{id}/sync-state` | 🔵 | Trạng thái đồng bộ (`historyId`, số mail, chưa đọc) |
| POST | `/api/v1/gmail/accounts/{id}/send` | 🟡 | Gửi email qua Gmail API |

</details>

<details>
<summary><b>Trends & audit</b></summary>

<br/>

| Method | Endpoint | Quyền | Mô tả |
|:-------|:---------|:-----:|:------|
| GET | `/api/v1/trends/apify-usage` | 🔵 | Dùng lượng Apify |
| GET | `/api/v1/trends/radar` | 🔵 | Radar xu hướng TikTok |
| GET | `/api/v1/trends/{trend_id}` | 🔵 | Chi tiết một trend |
| GET | `/api/v1/audit` | 🔴 | Audit trail toàn hệ thống |
| GET | `/api/v1/ab` | 🟢 | Bảng A/B (chưa đo live) |
| GET | `/api/v1/vf/conflict` | 🟢 | Demo phát hiện mâu thuẫn bàn giao |

</details>

---

<a id="packages"></a>
## Packages Python — API nội bộ

<details>
<summary><b><code>ca_contracts</code></b> — packages/contracts</summary>

<br/>

Schema Pydantic chia sẻ: `NhanVien`, `Ca`, `LichTuan`, `PhieuMau`, `RangBuocTrichXuat`, `MonNuoc`, `DongDon`, `DonQuay`, `DoanThoaiTranscript`, `ActionItem`, `CopilotIntent`, `CopilotResponse`, `ActionProposal`, `CAPABILITY_REGISTRY`, `COPILOT_ROLE_INTENT_MATRIX`.

</details>

<details>
<summary><b><code>ca_solver</code></b> — packages/solver</summary>

<br/>

| Hàm | Mô tả |
|:----|:------|
| `solve_cpsat(data, time_limit_s=60)` | Giải lịch tuần CP-SAT: C01 kỹ năng, C02 đủ người, C03 không đè ca, C04 khoảng nghỉ, C05 trần giờ, C06 TKB/nghỉ phép + soft + minimize max debt |
| `solve_hard_only(data)` | Chỉ kiểm 6 ràng buộc cứng, không giải |
| `build_lich_input(nhan_vien_ngoai=…)` | Dựng `LichInput` từ seed + pool NV thật |
| `load_seed()` | Đọc `data/seed/sample.json` |
| `apply_luat(inp, luat)` | Bơm luật hiệu lực cẩm nang vào input solver |
| `sinh_ly_do(…)` / `sinh_ly_do_toan_lich(…)` | Sinh mã lý do từng phân công / toàn lịch |
| `update_debt_from_assignment` / `zero_debt` | Cập nhật số dư công bằng 4 trục (AXES) |

</details>

<details>
<summary><b><code>ca_gates</code></b> — packages/gates</summary>

<br/>

| Hàm | Mô tả |
|:----|:------|
| `run_vf_pipeline(extraction, evidence, schema_keys, …)` | Chạy VF-SCHEMA → VF-TRACE → VF-CONF một lượt, trả `GateResult` |
| `validate_schema` / `validate_trace` / `validate_conf` | 3 cổng lọc trích xuất (fail-closed, retry một lần) |
| `validate_rule` / `validate_scope` / `validate_stale` | Cổng luật, phạm vi vai, snapshot stale |
| `validate_num` | Cổng số liệu bàn giao |
| `present_conflict(a, b)` | Trình bày mâu thuẫn claim |
| `compute_snapshot_hash` | Hash snapshot cho VF-STALE |

</details>

<details>
<summary><b><code>ca_ops</code></b> — packages/opsengine</summary>

<br/>

| Hàm | Mô tả |
|:----|:------|
| `load_template(ma)` | Đọc phiếu YAML từ `infra/templates/` |
| `start_phieu(run_id, mau, nv_id, ca_id, now_ms, diem_danh)` | Khởi tạo `PhieuRun` (chặn nếu chưa điểm danh) |
| `complete_buoc(run, ma, gia_tri, now_ms)` | Hoàn thành bước đúng thứ tự + anti-fake (nhanh, ảnh quá nhanh, ngưỡng số) |
| `add_treo(run, noi_dung)` | Thêm việc treo |
| `escalate(run, now_ms, han_phut=30)` | Nhắc 2 cấp: `nhac_nhan_vien` → `bao_chu_quan` |
| `dump_run` / `load_run` / `run_to_dict` | Serialize phiếu |

</details>

<details>
<summary><b><code>ca_playbook</code></b> — packages/playbook</summary>

<br/>

| Hàm | Mô tả |
|:----|:------|
| `record_sua(loai, truoc, sau, ai, now_iso)` | Ghi nhận lần sửa ca |
| `list_sua(include_synthetic=…)` | Danh sách lần sửa |
| `tim_mau(sua)` | Bước 1: tìm mẫu lỗi lặp ≥ 3 lần |
| `de_xuat(mau, sua_rows, ban_nhap)` | Bước 3: dựng luật ứng viên (không bịa — không nguồn trả None) |
| `kiem_chung(luat)` | Bước 4: VF-RULE kiểm chứng |
| `tap_su_tu_sua(luat, sua)` | Bước 5: tập sự từ lần sửa thật |
| `duyet(luat, ok, ai)` / `go_luat(luat, ai)` | Bước 6 chốt / bước 8 gỡ |
| `list_luat` / `save_luat` / `theo_doi` | Quản lý luật |
| `derive_rule_from_edits(mau, sua_rows)` | Suy tất định luật từ lần sửa |
| `pipeline_snapshot()` / `count_luat_that_quan` / `enrich_luat_ui` | Snapshot pipeline + đếm luật quán thật |
| `parse_sop_markdown` / `generate_skill_content` / `distill_sop_to_dir` | Chưng cất SOP → Skill |

</details>

<details>
<summary><b><code>ca_agents</code></b> — packages/agents</summary>

<br/>

| Thành phần | Mô tả |
|:-----------|:------|
| `FreeTierRouter` | Route groq → gemini → openrouter → ollama (vision: gemini trước); hết → `tu_choi` |
| `complete()` / `parse_json_object()` (llm.py) | Gọi LLM fail-closed, không bịa payload |
| `agent_mode()` | Đọc `CA_AGENT_MODE` (replay mặc định) |
| `AgentRuntime` / `SkillLoader` / `SkillRef` | Runtime prompt versioned + cache + nạp skill theo trigger |
| `get_port(name)` (messaging.py) | Cổng tin: `replay` / `telegram` / `zalo` / `console` |
| `run_copilot(message, context)` | AG-COPILOT: parse intent → VF-SCOPE → tool whitelist → proposal 2 pha |
| `classify(text, mode, staff)` (ag_msg) | 6 intents 2 tầng + trích ràng buộc có cấu trúc |
| `extract_tkb(source, mode)` (ag_tkb) | Trích TKB từ ảnh (replay fixture / live vision) |
| `find_swap_candidates(…)` (smart_swap) | Xếp hạng ứng viên thế ca |
| `propose_rule` (ag_rule) · `answer` (ag_sop) · `cluster` (ag_waste) · `extract` (ag_handover) | Agent chuyên trách |
| `ag_pricing` — `job_manager`, `orchestrator_v2`, `cost_dashboard`, `vision_menu_extractor`… | AG-PRICING: quản lý job khảo sát giá, điều phối SerpApi + Vision, dashboard chi phí |
| `ag_predict` — `detect_success_patterns`, `de_xuat_luat_tich_cuc` | AG-PREDICT: phát hiện mẫu thành công, đề xuất luật tích cực |
| `ag_explain` — `build_causal_chain`, `answer_reflection` | AG-EXPLAIN: dựng chuỗi nhân quả, trả lời reflection (grounded) |
| `ag_twin` — `simulate_scenario`, `simulate_virtual_staff` | AG-TWIN: mô phỏng kịch bản và nhân sự ảo bằng Math Layer |

</details>

---

<a id="agents"></a>
## Agents

Danh sách đầy đủ agent theo nhóm, cùng vai trò và file triển khai, xem mục [**Kiến trúc AI Agent → Danh sách agent theo nhóm**](#kien-truc-agent). Mỗi agent nằm trong `packages/agents/src/ca_agents/`.

Các agent chuyên trách chính và nơi triển khai:

| Agent | File / thư mục |
|:------|:---------------|
| AG-COPILOT | `ag_copilot/` |
| AG-MSG | `ag_msg/` |
| AG-TKB | `ag_tkb/` |
| AG-RULE · AG-SOP | `ag_rule/` · `ag_sop/` |
| AG-BRIEF · AG-MEETING | `ag_brief/` · `ag_meeting/` |
| AG-MAILWRITER · AG-MAIL | `ag_mailwriter/` · `ag_mail.py` |
| AG-WASTE · AG-HANDOVER | `ag_waste/` · `ag_handover/` |
| AG-PRICING · AG-PREDICT | `ag_pricing/` · `ag_predict/` |
| AG-EXPLAIN · AG-TWIN | `ag_explain/` · `ag_twin/` |
| AG-FBPAGE · AG-GMAIL | `ag_fbpage.py` · `ag_gmail/` |
| AG-VOC · AG-BARISTA · AG-TREND · AG-SUPERVISOR · AG-CONCIERGE | `ag_voc/` · `ag_barista.py` · `ag_trend.py` · `ag_supervisor.py` · `ag_concierge.py` |
| AG-WAR-ROOM · AG-SHIFT-RESCUE · AG-RULE-LEARNING | `ag_war_room/` · `ag_shift_rescue/` · `ag_rule_learning/` |
| AG-SPATIAL-MEMORY · AG-QUANVERSE | `ag_spatial_memory/` · `ag_quanverse/` |
| AG-MENU-IMAGE | `ag_menu_image.py` |

---

<a id="skills"></a>
## Thư viện Kỹ năng (Skills)

**14 kỹ năng** = 13 skill chưng cất (Repo-To-Skill / Playbook-To-Skill) + 1 Skill Router, tuân chuẩn [Agent Skills Format](https://github.com/agentskills/agentskills). Mỗi skill gồm `SKILL.md` + `references/` + `scripts/` (smoke test offline). Xem [`skills/README.md`](./skills/README.md) và index [`skills/skills_index.jsonl`](./skills/skills_index.jsonl).

> [!TIP]
> **Skill Router** giữ context **≤ 1.500 tokens** bằng Progressive Disclosure — chỉ nạp skill khớp trigger từ khóa.

| Skill | Mô tả |
|:------|:------|
| `solver-scheduling` | Chuẩn bị dữ liệu & kích hoạt CP-SAT, ràng buộc C01–C06 |
| `rule-mining-lifecycle` | Phát hiện mẫu lặp ≥ 3 lần → đề xuất luật theo Cẩm nang 8 bước |
| `barista-waste-audit` | Kiểm định công thức pha chế, tính tỷ lệ hao hụt nguyên vật liệu |
| `customer-memory-voc` | Phân tích cảm xúc VOC, ghi nhớ sở thích khách quen |
| `daily-brief-generator` | Sinh bản tin giao ban ca (nhân sự, mục tiêu, việc treo) |
| `fbpage-concierge` | Trực fanpage: menu, giá, giờ mở cửa, hỗ trợ đặt bàn |
| `handover-reconciliation` | Đối soát tiền két & bàn giao việc treo giữa ca |
| `inventory-restock-check` | Dự báo & cảnh báo đặt hàng khi chạm điểm đặt hàng lại |
| `mailwriter-notification` | Soạn email điều hành gửi nhà cung cấp / thông báo nội bộ |
| `meeting-memo-extractor` | Trích biên bản họp thành action item có người phụ trách + hạn |
| `smart-swap-recommender` | Đề xuất người thế ca tối ưu khi có người xin nghỉ đột xuất |
| `sop-execution` | Xác minh & hướng dẫn thực thi SOP theo Cẩm nang 8 bước |
| `vf-gates-audit` | Thẩm định đề xuất AI qua cổng fail-closed (VF-SCHEMA/TRACE/CONF) |
| *Skill Router* | Khớp trigger từ khóa, chỉ nạp skill phù hợp (tiết kiệm context) |

| Thành phần | Cách hoạt động |
|:-----------|:---------------|
| Skill Router | Khớp **trigger từ khóa** của yêu cầu với metadata từng skill, chỉ nạp skill phù hợp |
| Ngân sách context | ≤ 1.500 tokens (Progressive Disclosure: metadata trước, nội dung đầy đủ khi khớp) |
| Nạp trong code | `SkillLoader` / `SkillRef` (`ca_agents`) |
| Chưng cất mới | `POST /skills/distill-sop` (Hybrid mode) · `distill_sop_to_dir` (`ca_playbook`) |
| Kiểm định | CI `skills-verify.yml` + `POST /api/v1/skills/{id}/verify` (SHA256 trong `skills_index.jsonl`) |

---

<a id="bao-mat"></a>
## Bảo mật

| Cơ chế | Triển khai thực tế |
|:-------|:-------------------|
| **Xác thực** | Token Bearer phát từ `POST /api/v1/auth/login`; đăng ký mới luôn gán vai `nhan_vien` |
| **Phân quyền** | 4 vai: công khai · đã đăng nhập · `quan_ly`/`chu_quan` · `chu_quan`. Kiểm 2 lớp: pre-check trong agent (`run_copilot`) + `VF-SCOPE` tại pha Confirm |
| **Ma trận role × intent** | Nguồn duy nhất `COPILOT_ROLE_INTENT_MATRIX` trong `ca_contracts`; fail-closed: role thiếu/lạ → coi như `nhan_vien` |
| **Mật khẩu** | PBKDF2-HMAC-SHA256 có salt riêng từng tài khoản (hỗ trợ nâng cấp từ hash SHA256 cũ) |
| **Secrets** | Chỉ đọc từ biến môi trường; `.env` bị gitignore; `scripts/scan_secrets_before_commit.py` chặn commit lộ secret |
| **Token OAuth** | Mã hoá **Fernet (AES-128-GCM)** trước khi lưu DB; khoá qua `NHIPQUAN_ENCRYPTION_KEY` |
| **Webhook verification** | Telegram: `X-Telegram-Bot-Api-Secret-Token`; Facebook: verify token `NHIPQUAN_FB_WEBHOOK_VERIFY` |
| **Guardrails đầu vào** | `sanitize_input` + `check_input_guardrail` + `is_tool_allowed` (`ca_agents/guardrails.py`); phát hiện mẫu prompt-injection bỏ qua bước duyệt |
| **Chống rò rỉ** | AG-SUPERVISOR lọc dữ liệu nhạy cảm và lời hứa tài chính trái phép; audit `role_blocked` cho mọi lượt bị chặn quyền |
| **Rate limit** | Rate limiter riêng cho luồng Facebook; circuit breaker cho SerpApi |
| **Tenant scope** | Tool đọc dữ liệu giới hạn theo `store_id` của tài khoản đăng nhập |

> [!IMPORTANT]
> **Không** commit file `.env`. README này **không** chứa secret thật. Mọi biến môi trường dưới đây để trống giá trị.

---

<a id="trien-khai"></a>
## Triển khai

### Docker Compose (5 service)

`infra/docker/compose.yml` định nghĩa: `postgres` (16-alpine) · `redis` (7-alpine) · `api` · `worker` · `web`.

- Cổng: web `3000`, api `8000`, postgres `5433` (container `5432`), redis `6379`.
- API tự chạy `alembic upgrade head` trước khi khởi uvicorn.
- Healthcheck: `pg_isready` · `redis-cli ping` · `curl /health`.
- `worker` phụ thuộc `api` healthy.

```bash
make docker-up        # = python scripts/docker_stack.py up
make docker-ps        # trạng thái container
make docker-smoke     # kiểm toàn tuyến backend
make docker-logs      # log stack
make docker-down      # dừng
make docker-reset     # dừng + xoá volume
```

> [!CAUTION]
> Gọi Docker qua `scripts/docker_stack.py` (wrapper tắt BuildKit, ghim tên project ASCII) — **không** gọi `docker compose` trực tiếp.

### Migration (Alembic)

```bash
export DATABASE_URL=postgresql+psycopg://nhipquan:nhipquan@localhost:5433/nhipquan
cd apps/api
uv run alembic -c alembic/alembic.ini upgrade head
```

### Cloud / VPS

- Runbook: [`docs/runbook-aws.md`](./docs/runbook-aws.md) · [`docs/runbook-oracle.md`](./docs/runbook-oracle.md) · [`docs/deployment.md`](./docs/deployment.md)
- Ảnh Docker có thể build & đẩy lên GHCR qua workflow `docker-ghcr.yml`; triển khai AWS qua `deploy-aws.yml`.
- Production: dùng PostgreSQL + Redis + reverse proxy (web PWA demo hiện chạy tại [nhipquan.duckdns.org](https://nhipquan.duckdns.org/)).

---

<a id="trang-thai"></a>
## Trạng thái hiện tại

### Đã triển khai (Implemented)

- **Lõi tất định:** CP-SAT solver với C01–C06 + soft + công bằng 4 trục; gates VF-*; opsengine phiếu / việc treo; playbook 8 bước.
- **Agent:** AG-COPILOT + 35 tool whitelist, thực thi 2 pha, audit, voice (Gemini Live); 20+ agent chuyên trách khác.
- **Vòng đời lịch:** state machine đầy đủ, version + fingerprint + idempotency, open shifts, đổi ca 3 người, xuất ICS/XLSX/PDF.
- **Kênh:** Telegram (webhook + long-poll), Zalo OA, Facebook Page (moderation + đặt bàn + bài đăng), chat nội bộ realtime qua WebSocket + Redis.
- **Tích hợp:** Gmail OAuth 2.0 (đọc/gửi/nhãn/bộ lọc), SMTP, SerpApi (AG-PRICING + giá giao hàng ShopeeFood + menu Google Maps), Threads API, Camoufox (tùy chọn).
- **Web PWA:** 46 route (roster, inbox, copilot, chat, page-quán, gmail, cam-nang, lich-tuan, quay, phieu, tkb, khao-sat-gia, ai-learning, skills, hao-phi, tieu-thu, doi-ca, cong-bang, menu, sop, treo, handover, giai-thich, cuoc-hop, vet, cau-hinh-quan, thu-nghiem-an-toan, quanverse/*…).
- **Thư viện Skills:** 14 kỹ năng đã kiểm định, có SHA256 + smoke test.
- **AI Learning:** vòng phản hồi, đề xuất luật, circuit breaker, retention.
- **Hạ tầng:** Docker Compose 5 service, migration Alembic, CI/CD GitHub Actions.

### Đang phát triển (In Progress)

- Dựa trên `plans/` và nhánh đang mở: hoàn thiện **Digital Twin / Predictive Playbook** (AG-PREDICT, AG-TWIN) và rollout có kiểm soát (xem [`docs/runbooks/ag-copilot-rollout.md`](./docs/runbooks/ag-copilot-rollout.md)).
- Sensor JEV (cảm biến xác suất) — hiện **mặc định tắt** (`JEV_ENABLED=false`), fail-closed khi thiếu key.

### Dự kiến (Planned)

Các hướng được nêu trong tài liệu kế hoạch, **chưa** phải tính năng hiện có — xem [Roadmap](#roadmap).

<a id="adr-quan-trong"></a>
### ADR gần đây cần biết

| ADR | Nguyên tắc |
|:----|:-----------|
| [ADR-019](./docs/adr/ADR-019-anh-san-pham-sinh-tai-may.md) | Ảnh sản phẩm sinh tại máy, **không** gọi API ảnh đám mây |
| [ADR-020](./docs/adr/ADR-020-doi-ca-dong-thuan-va-cong-cong-bo.md) | Đổi ca phải có **đồng thuận** của các bên + qua cổng công bố |
| [ADR-021](./docs/adr/ADR-021-llm-khong-la-nguon-so.md) | **LLM không bao giờ là nguồn số** — mọi con số đến từ lõi tất định |

---

<a id="han-che"></a>
## Hạn chế

- **Phụ thuộc LLM bên ngoài:** các tác vụ hiểu ngôn ngữ cần provider free-tier (Groq / Gemini / OpenRouter / B.ai); hạn mức có thể thay đổi, chất lượng phụ thuộc model.
- **Memory hữu hạn:** AG-COPILOT chỉ giữ tối đa 3 tin nhắn gần nhất; hệ thống **không** có vector store / RAG.
- **Không tự trị:** agent không tự thực thi thay đổi — mọi hành động ghi đều chờ người duyệt (2 pha). Đây là **thiết kế có chủ đích (fail-closed)**, đồng thời là giới hạn về mức độ tự động hoá.
- **Phạm vi một quán:** hiện giới hạn theo một `store_id`; chưa có multi-quán / franchise.
- **Kênh thật cần credential:** thiếu token thì kênh ở trạng thái `disconnected`/`replay` và hệ thống **không** giả lập đã kết nối.
- **Scraping phụ thuộc bên thứ ba:** tier cào dữ liệu (Camoufox / Threads / TikTok / ShopeeFood / Google Maps) có thể hỏng khi nền tảng đổi UI — vì vậy `make canary` tách khỏi luồng chặn merge, chỉ báo cáo.
- **Chưa có monitoring production đầy đủ:** chưa tích hợp APM/observability chuyên sâu; quan sát chủ yếu qua log, `/health` và audit trail.

---

<a id="roadmap"></a>
## Roadmap

> [!NOTE]
> Phần này là **định hướng tương lai**, không phải tính năng hiện có. Thứ tự có thể thay đổi.

```text
Phase 1 — Lõi & Agent nền tảng        ✅ (đã có)
  CP-SAT solver · gates VF-* · opsengine · playbook 8 bước · AG-COPILOT + tool whitelist

Phase 2 — Vận hành F&B                ✅ (đã có)
  Lịch tuần · phiếu trong ca · việc treo · bàn giao · quầy POS · đặt bàn

Phase 3 — Đa kênh                     ✅ (đã có)
  Telegram · Zalo OA · Facebook Page · chat realtime · Gmail OAuth

Phase 4 — Phân tích & tự động hoá     🔄 (đang làm)
  Digital Twin / Predictive Playbook · rollout có kiểm soát · sensor JEV

Phase 4b — Trải nghiệm & vận hành      ✅ (đã có)
  Quánverse (War Room · Shift Rescue · Rules · Spatial Memory)
  Hao hụt nguyên liệu lý thuyết ↔ thực tế · ảnh thẻ sản phẩm sinh tại máy

Phase 5 — Quy mô sản xuất             ⬜ (dự kiến)
  Multi-quán / franchise · quan sát & cảnh báo production · mở rộng tự động hoá có người duyệt
```

---

<a id="kiem-thu"></a>
## Kiểm thử & đánh giá

```bash
make test          # pytest toàn monorepo (CA_AGENT_MODE=replay)
make lint          # ruff + tsc
make bench         # solver tuần + verify_hard
make eval          # eval AG-TKB, AG-MSG, nhóm A §18.2
make metrics       # 7 con số §18.2 (tất định, fixture ADR-012)
cd apps/web && npm run test:e2e   # Playwright e2e
```

**Phạm vi test hiện có** (đếm từ repo):

| Loại | Số lượng / vị trí |
|:-----|:------------------|
| Test API (pytest) | 77 file trong `apps/api/tests/` |
| Test packages (pytest) | 131 file khớp `*test*.py` trong `packages/` |
| Test e2e (Playwright) | 23 spec trong `apps/web/e2e/` (`flows`, `lich-tuan`, `phieu-timing`, `vet`, `predict-twin`, `khao-sat-gia-review`, `hao-hut`, `war-room`, `shift-rescue`, `spatial-memory`, `quanverse`…) |
| Kiến trúc | `test_architecture.py` cưỡng chế ranh giới import của Tool Registry |

> Pytest lấy `testpaths = ["apps", "packages"]` từ `pyproject.toml` gốc.
>
> [!NOTE]
> Mọi bản ghi fixture mang nhãn nguồn `mo_phong_fixture`; UI gắn nhãn dữ liệu mẫu qua `co_du_lieu_mau`.

**CI/CD** chạy trên GitHub Actions:

| Workflow | Vai trò |
|:---------|:--------|
| [![CI](https://github.com/KanTrun/Crew-Operations/actions/workflows/ci.yml/badge.svg)](https://github.com/KanTrun/Crew-Operations/actions/workflows/ci.yml) | `ci.yml` — lint + test |
| [![Skills Verify](https://github.com/KanTrun/Crew-Operations/actions/workflows/skills-verify.yml/badge.svg)](https://github.com/KanTrun/Crew-Operations/actions/workflows/skills-verify.yml) | `skills-verify.yml` — kiểm định kỹ năng |
| [![Docker GHCR](https://github.com/KanTrun/Crew-Operations/actions/workflows/docker-ghcr.yml/badge.svg)](https://github.com/KanTrun/Crew-Operations/actions/workflows/docker-ghcr.yml) | `docker-ghcr.yml` — build & đẩy image lên GHCR |
| `ai-code-review.yml` | GitHub Copilot code review tự động theo `.github/copilot-instructions.md` |
| `canary-nguon.yml` | Canary tier scraping nguồn ngoài (theo lịch, không chặn merge) |
| `deploy-aws.yml` | Triển khai lên AWS ([`docs/runbook-aws.md`](./docs/runbook-aws.md)) |

---

<a id="github"></a>
## GitHub — nhánh & quy trình

**Remote:** `https://github.com/KanTrun/Crew-Operations.git` · Chi tiết: [`docs/github-operating-model.md`](./docs/github-operating-model.md)

### Nhánh gốc

```mermaid
gitGraph
    commit id: "init"
    commit id: "feat(core)"
    commit id: "feat(sprint1-2)"
    branch release/semifinal
    commit id: "semifinal" tag: "v0.1.0-semifinal"
    checkout main
    commit id: "feat(sprint3-5)"
    branch release/final
    commit id: "final" tag: "v1.0.0-final"
    checkout main
```

| Nhánh | Vai trò |
|:------|:--------|
| `main` | Nguồn sự thật — luôn xanh, luôn demo được |
| `release/semifinal` | Đóng băng tuần 6 → tag `v0.1.0-semifinal` |
| `release/final` | Đóng băng tuần 8 → tag `v1.0.0-final` |

### Bốn vùng sở hữu (tiền tố nhánh)

| Người | Tiền tố nhánh | Sở hữu chính |
|:-----:|:--------------|:-------------|
| **A** | `feat/solver-*` `feat/gates-*` `feat/ops-*` `feat/playbook-*` | solver, gates, opsengine, playbook |
| **B** | `feat/api-*` `feat/orc-*` `ci/*` `chore/infra-*` | api, orchestration, CI, infra, Docker |
| **C** | `feat/agents-*` `feat/router-*` `feat/eval-*` | agents, router, eval, messaging |
| **D** | `feat/web-*` `feat/tpl-*` `docs/*` | Next.js PWA, YAML templates, docs |

**Luật:** nhánh `feat/*` ≤ 3 ngày · ≤ 2 nhánh mở/người · `git pull --rebase origin main` hằng ngày · vào `main` chỉ qua **squash merge** + PR. WIP: `wip/a|b|c|d/...` — cấm PR thẳng vào `main`.

### Quy tắc bất biến

1. Hợp đồng dữ liệu trước, mã nguồn sau
2. `main` luôn xanh và luôn demo được
3. Không vào `main` nếu không qua PR được duyệt
4. Không LLM ghi lịch / điều phối

---

<a id="tai-lieu"></a>
## Tài liệu

| Tài liệu | Nội dung |
|:---------|:---------|
| [`docs/runbook-demo.md`](./docs/runbook-demo.md) | Demo, tài khoản mẫu, kịch bản demo |
| [`docs/huong-dan-demo-thi.md`](./docs/huong-dan-demo-thi.md) | Hướng dẫn demo thi |
| [`docs/phan-cong-nhanh.md`](./docs/phan-cong-nhanh.md) | Chia việc nhánh, thứ tự merge |
| [`docs/github-operating-model.md`](./docs/github-operating-model.md) | PR, CI gates, commits |
| [`docs/ket-qua-tong-hop.md`](./docs/ket-qua-tong-hop.md) | Kết quả đo hồ sơ |
| [`docs/runbooks/`](./docs/runbooks/) | 16 runbook: Telegram · Zalo · Facebook · Gmail · SerpApi · Camoufox · AI incident… |
| [`docs/adr/`](./docs/adr/) | 21 Architecture Decision Records (ADR-001 → ADR-021) |
| [`docs/THIRD_PARTY.md`](./docs/THIRD_PARTY.md) | Phụ thuộc & license (kèm free-tier) |
| [`docs/deployment.md`](./docs/deployment.md) | Triển khai |
| [`docs/design-guidelines.md`](./docs/design-guidelines.md) | Quy ước thiết kế UI |

---

## Tác giả & License

**Đội ngũ:** xem [`docs/team.md`](./docs/team.md) · **Cuộc thi:** Xây dựng Hệ điều hành Doanh nghiệp số AI · Khoa CNTT HUTECH · 2026.

Repo **không** kèm file `LICENSE` riêng. Quyền và giấy phép của từng thành phần bên thứ ba (FastAPI, Next.js, OR-Tools, PostgreSQL, Redis, các provider LLM, Meta / Zalo / Telegram / Google API…) được liệt kê kèm hạn mức free-tier tại [`docs/THIRD_PARTY.md`](./docs/THIRD_PARTY.md).

<div align="center">

<br/>

**NHỊP QUÁN** — *Ca làm việc là hạt nhân · Cẩm nang tự viết là bộ nhớ · Lõi không dùng LLM*

<sub>Xây dựng Hệ điều hành Doanh nghiệp số AI · Khoa CNTT HUTECH · 2026</sub>

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:C68B59,50:6F4E37,100:3E2723&height=120&section=footer" width="100%" alt="footer" />

</div>