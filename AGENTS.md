# AGENTS.md — quy tắc làm việc cho agent (và cho người hướng dẫn AI) trong repo này

Ghi lại những sai lầm đã mắc phải, để lần sau không lặp lại. Mỗi mục đều là một
sự cố đã xảy ra thật, không phải giả định.

## 1. Lệnh chạy lâu (>2 phút): chạy NỀN, không chạy trực tiếp

Sự cố: chạy `pytest` toàn bộ (~10 phút) trực tiếp, không in dòng nào ra, nhìn
như treo và bị interrupt.

Cách làm đúng — dùng 2 script trong `scripts/`:

```powershell
# 1. Chạy nền (lệnh về NGAY LẬP TỨC, không chặn)
& scripts/run_bg.ps1 -Name t1 -Command "& '.\.venv312\Scripts\python.exe' -m pytest ... -q"

# 2. Poll với -WaitAll: chờ tới khi xong, KHÔNG đặt hạn giờ đoán.
#    Có heartbeat mỗi 30s + in thời gian thực khi xong.
& scripts/poll_bg.ps1 -Name t1 -WaitAll
```

**Không còn chuyện đoán số giây nữa** — cả hai script đo và tự ghi:

- `run_bg.ps1` ghi mốc bắt đầu, và in ra `LAN TRUOC job nay mat ~Ns` nếu tên job
  từng chạy (dữ liệu ở `%TEMP%/opencode-jobs/durations.log`).
- `poll_bg.ps1 -WaitAll` chờ tới khi có exit code, in `thoi gian thuc: Ns`, và
  heartbeat `--- con chay Ns | <dong log cuoi>` để không im lặng.
- Dùng **cùng tên job** cho cùng một loại lệnh là tự có mốc thời gian để tham
  chiếu (vd `-Name py_agents`, `-Name py_api`, `-Name push`).

Cấm dùng `Start-Sleep <số đoán>` rồi poll: số đó tùy ý, job xong sớm thì chờ
phí, job lâu hơn thì phải poll lại.

Còn hai nguyên tắc cũ:

- **Không mắc `Select-Object -First/-Last` trong lệnh nền** — nó buffer tới cuối
  mới ghi, nên log 0 byte suốt 10 phút và tưởng như treo.
- Chia nhỏ test theo `-k` để mỗi lần <2 phút khi có thể.

Nếu cần hạn thời gian cứng thì lấy từ `durations.log`, không đoán:
```powershell
Get-Content "$env:TEMP\opencode-jobs\durations.log" | Sort-Object { [int]($_ -split ' ')[-1] } -Descending | Select-Object -First 10
```

## 2. Test Docker: LUÔN dùng `scripts/docker_stack.py`

Sự cố: tự dựng image, tự viết script E2E HTTP, mất ~10 phút build, và tệ hơn là
chạy nhầm **code cũ**.

Repo đã có sẵn toàn bộ tooling:

```powershell
python scripts/docker_stack.py up        # build + khởi động, chờ healthy
python scripts/docker_stack.py smoke     # smoke trong container api
python scripts/docker_stack.py seed-ops  # nạp dữ liệu vận hành
python scripts/docker_stack.py reset     # down -v rồi up lại từ trắng
python scripts/docker_stack.py down
```

Bộ test copilot chuẩn của repo (đừng tự viết lại):

- `scripts/e2e_http_copilot.py` — E2E qua HTTP: 33 intent, phân quyền, SSE
- `scripts/smoke_docker.py` — smoke toàn tuyến
- `scripts/test_docker_safety.py` — chốt chặn chạy nhầm live mode

### Bẫy: `docker compose up` KHÔNG rebuild

`docker compose ... up` dùng lại image có sẵn cục bộ. Đã từng test nhầm image build
từ 7 ngày trước và tưởng fix chưa áp dụng, trong khi code trên máy đã sửa xong.

Luôn kiểm tra image nào container đang chạy:

```powershell
docker inspect -f "{{.Config.Image}} created={{.Created}}" nhipquan-api-1
```

`created=` phải là **mới hơn** thời điểm sửa code. `scripts/docker_stack.py up`
đã gọi build nên dùng nó là đủ.

### Profile test: `compose.test.yml` ép `replay` + seed

`infra/docker/compose.test.yml` dùng `environment: !override` — cố ý, để không
kế thừa env live/demo của máy dev. Hệ quả: mọi biến phải khai lại tường minh,
kể cả `NHIPQUAN_SEED_DEMO`, nếu không thì volume trắng không có tài khoản nào và
mọi test đăng nhập đều 401.

`.env` của máy dev đang để `CA_AGENT_MODE=live`, `NHIPQUAN_PAGE_MODE=live`,
`NHIPQUAN_SEED_DEMO=false`. Chạy `docker_stack.py` (dùng `compose.yml`) thì
container chạy **live mode** → gọi LLM thật (script E2E sẽ treo ở
`SCHEDULE_SOLVE`) và `test_docker_safety.py` assert fail **đúng như thiết kế**.

Muốn chạy đúng điều kiện CI: dùng profile test

```powershell
docker compose -f infra/docker/compose.yml -f infra/docker/compose.test.yml up -d --wait
```

## 3. Trước khi kết luận "đã xong", đo lại thứ đo được

Sự cố: kết luận "sửa xong" rồi mới phát hiện endpoint mất 194s, và chưa chứng
minh được ràng buộc có thực sự áp vào lịch hay không.

- Với endpoint chậm: đo thời gian thật, đừng suy đoán.
- Với hành vi nghiệp vụ: đọc dữ liệu ghi ra, đừng chỉ tin mã 200 hay
  `action_proposal is not None`.
- Nói rõ phần nào **chưa** chứng minh được, thay vì im lặng bỏ qua.

## 4. `pytest` toàn bộ rất chậm — ưu tiên `-k`

Toàn bộ `apps/api/tests/unit` mất hàng chục phút. Khi sửa một phần, chạy các
file liên quan trước, chạy toàn bộ một lần trước khi commit.

## 5. Đừng tự điền dữ liệu thay người dùng

Sự cố: khi nhân viên xin nghỉ mà không nêu lý do, copilot tự điền `ly_do="bận"`,
tạo ra đơn nghỉ không biết lý do mà quản lý vẫn phải duyệt.

Nguyên tắc chung: thiếu thông tin bắt buộc thì **hỏi lại**, không bịa giá trị mặc
định rồi đẩy cho người khác xử lý. Cùng nguyên tắc này áp dụng cho `giao ca`,
`đổi ca`, `giá món`.

## 6. Nhận diện intent bằng TỪ KHÓA CỨNG: đây là QUYẾT ĐỊNH, không phải sơ suất

`_INTENT_KEYWORDS` trong `intent_parser.py` có 35 intent × 611 chuỗi khớp bằng
`kw in lower`. Nhân viên nói lệch một từ là rơi `OUT_OF_SCOPE`. Nghe như
nợ kỹ thuật, nhưng đã hỏi và **chủ dự án chốt giữ nguyên** (2026-10-01).

Lý do giữ được:
- Replay và CI **không có LLM**; tầng từ khóa giữ cho test tất định. Toàn bộ
  `e2e_http_copilot.py` dựa vào nó.
- `parse_intent` nằm trên đường intent → tool → phân quyền. Đặt LLM vào đây là
  thêm độ trễ và mất tính tất định đúng chỗ khó nhất.

**Jev KHÔNG phải câu trả lời.** `sensors/jev_sensor.py` là *cảm biến xác suất gọi
Jev (TypeSafe System One)* — trả về "có nên gọi ra hệ thống ngoài không", khác hẳn
"NV đang muốn cái gì". Nó còn đang là stub (`JEV_ENABLED` tắt mặc định, chưa có API
key, payload còn phải đối chiếu lại với docs). Đừng đề xuất cắm nó vào parse intent.

Nếu sau này chủ dự án đổi ý, mẫu đúng **đã có sẵn** trong repo:
`packages/agents/src/ca_agents/ag_msg/extract.py:214-222` — từ khóa tầng-1, lỡ
tầng-1 thì ở chế độ live mới gọi LLM trả `{intent, confidence}`, validate trong
whitelist rồi gắn `rang_buoc={"nguon":"llm"}`. Bắt chước y hệt, đừng phát minh.
