"""Intent Parser & Prompt Injection Guard cho AG-COPILOT.

Phân loại câu tiếng Việt thành intent trong danh sách whitelist, kèm trích tham số
và chống prompt injection.

Cơ chế nhận diện: `_INTENT_KEYWORDS` là tầng TẤT ĐỊNH (35 intent / 611 từ khóa,
khớp bằng `kw in lower`) — đường này chạy ở mọi chế độ, kể cả replay/CI nên
test tất định. Đổi lại nó không nhận diện được cách nói không nằm trong từ khóa;
xem `docs`/ghi chú về đường LLM để mở rộng.

Ghi chú: số "7 intent" trong docstring cũ đã lệch — hiện có 35 intent whitelist
cộng `OUT_OF_SCOPE`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ca_agents.ag_copilot.timeoff_parse import (
    CA_RANGE,
    parse_ca_range,
    parse_thu,
    parse_thu_tuong_doi,
    trich_ly_do,
)

# Intent enum string constants
SCHEDULE_SOLVE = "SCHEDULE_SOLVE"
APPROVE_SHIFT_SWAP = "APPROVE_SHIFT_SWAP"
GENERATE_DAILY_BRIEF = "GENERATE_DAILY_BRIEF"
QUERY_SOP = "QUERY_SOP"
ANALYZE_WASTE = "ANALYZE_WASTE"
CREATE_RULE_PROPOSAL = "CREATE_RULE_PROPOSAL"
INVENTORY_RESTOCK_CHECK = "INVENTORY_RESTOCK_CHECK"
SEND_MAIL = "SEND_MAIL"
# PR9 read intents — chỉ đọc, không side effect
GET_MY_PROFILE = "GET_MY_PROFILE"
LIST_STAFF = "LIST_STAFF"
QUERY_MENU = "QUERY_MENU"
GET_INVENTORY = "GET_INVENTORY"
GET_SHIFT_SWAPS = "GET_SHIFT_SWAPS"
GET_HANGING_TASKS = "GET_HANGING_TASKS"
GET_HANDOVERS = "GET_HANDOVERS"
# Xin nghỉ / báo bận — NV nói tự nhiên "tôi bận thứ 5", "không đi được ca tối"
PROPOSE_TIME_OFF = "PROPOSE_TIME_OFF"
# PR10 self-service mutating intents — R2_CONFIRM
PROPOSE_HANGING_TASK = "PROPOSE_HANGING_TASK"
PROPOSE_TASK_COMPLETE = "PROPOSE_TASK_COMPLETE"
PROPOSE_CONSUMPTION_RECORD = "PROPOSE_CONSUMPTION_RECORD"
# PR11 admin mutating intents — R2_CONFIRM (quan_ly/chu_quan)
PROPOSE_MENU_UPDATE = "PROPOSE_MENU_UPDATE"
PROPOSE_ORDER_TRANSITION = "PROPOSE_ORDER_TRANSITION"
PROPOSE_PIN = "PROPOSE_PIN"
# PR12 external channel intents
GET_PAGE_STATUS = "GET_PAGE_STATUS"
PROPOSE_PAGE_SYNC = "PROPOSE_PAGE_SYNC"
PROPOSE_PAGE_DRAFT = "PROPOSE_PAGE_DRAFT"
# PR13 read intents bổ sung — lịch tuần / ca cá nhân / ràng buộc chờ duyệt
GET_SCHEDULE = "GET_SCHEDULE"
GET_MY_SHIFTS = "GET_MY_SHIFTS"
GET_CONSTRAINT_CANDIDATES = "GET_CONSTRAINT_CANDIDATES"
# PR10 còn lại (R2_CONFIRM): xác nhận TKB, đồng ý đổi ca, ghi bàn giao ca
PROPOSE_TKB_CONFIRM = "PROPOSE_TKB_CONFIRM"
PROPOSE_SWAP_CONSENT = "PROPOSE_SWAP_CONSENT"
PROPOSE_HANDOVER = "PROPOSE_HANDOVER"
# Khảo sát thị trường & SerpApi
RUN_CATCHMENT_SURVEY = "RUN_CATCHMENT_SURVEY"
GET_SERPAPI_QUOTA = "GET_SERPAPI_QUOTA"
GET_SURVEY_RESULT = "GET_SURVEY_RESULT"
# Audit / vết hệ thống — chỉ quản lý & chủ quán (R0_READ, tenant-scoped)
QUERY_AUDIT = "QUERY_AUDIT"
# Hỏi về 4 mặt Trải nghiệm AI (Living Map / War Room / Cứu ca / Hồn quán)
QUERY_QUANVERSE = "QUERY_QUANVERSE"
# Mở rộng năng lực vận hành (R0_READ)
GET_WEATHER = "GET_WEATHER"
GET_TODAY_OPERATIONS = "GET_TODAY_OPERATIONS"
GET_FAIRNESS_SUMMARY = "GET_FAIRNESS_SUMMARY"
GET_MY_CHECKLIST = "GET_MY_CHECKLIST"
SEARCH_TRENDS = "SEARCH_TRENDS"
GET_RESERVATIONS = "GET_RESERVATIONS"
GET_OPEN_SHIFTS = "GET_OPEN_SHIFTS"
GET_MEETINGS = "GET_MEETINGS"
GET_PREDICTIVE_INSIGHTS = "GET_PREDICTIVE_INSIGHTS"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
# Patterns detecting attempts to bypass two-phase approval
_BYPASS_PATTERNS = [
    r"bỏ\s*qua\s*(bước\s*)?duyệt",
    r"ghi\s*luôn\s*(không\s*cần\s*(hỏi|duyệt|xác\s*nhận))?",
    r"tự\s*động\s*duyệt\s*hộ",
    r"xóa\s*hết\s*lịch.*ghi\s*đè\s*luôn",
    r"override\s*(auth|permission|approval|security)",
    r"ignore\s*(all\s*)?(previous\s*)?(instructions|rules)",
    r"từ\s*giờ\s*bạn\s*là\s*(admin|root|system|developer)",
]
_BYPASS_REGEX = re.compile("|".join(_BYPASS_PATTERNS), re.IGNORECASE)

# Stop words để ngăn multi-turn inference quá agresif
_CONVERSATIONAL_STOP_WORDS = frozenset({
    "không phải", "khong phai", "t kêu", "t keu", "tao kêu", "tao keu",
    "đâu phải", "dau phai", "nhầm", "nham", "thôi", "thoi", "hủy", "huy",
    "cảm ơn", "cam on", "thank", "thanks", "tks", "ok", "oke", "được rồi", "duoc roi",
    "xong rồi", "xong roi", "dạ vâng", "da vang", "vâng", "vang", "dạ", "da",
    "chào", "chao", "alo", "hi", "hello", "sao vậy", "sao vay", "tại sao", "tai sao",
    "thế nào", "the nao", "là sao", "la sao", "là gì", "la gi", "?", "ngáo", "kỳ vậy",
    "quán", "quan", "ai làm", "ai lam"
})

# Trần chờ của tầng-2 LLM. Số này CHƯA được tối ưu — đo thật p50/p95 trên câu hỏi
# của nhân viên trước khi chốt. Hiện tạm lấy bằng timeout chat đang dùng
# (`copilot_agent._generate_conversational_reply` dùng 15.0).
_LLM_TIER2_TIMEOUT_S = 15.0

# Intent matching keywords
# PR9 read intents đặt ĐẦU danh sách: cụm hỏi đọc cụ thể ("đổi ca nào",
# "việc treo") phải thắng từ chung của mutating intents ("đổi ca").
_INTENT_KEYWORDS: list[tuple[str, list[str], float]] = [
    # PR10 còn lại — đặt ĐẦU danh sách: cụm hành động cụ thể ("đồng ý đổi ca
    # sw_xxx") phải thắng từ chung của GET_SHIFT_SWAPS/APPROVE_SHIFT_SWAP
    # ("đổi ca"), và "bàn giao ca" phải thắng GET_HANDOVERS ("bàn giao").
    (
        PROPOSE_SWAP_CONSENT,
        ["đồng ý đổi ca", "dong y doi ca", "đồng ý nhận ca", "dong y nhan ca", "xác nhận nhận ca", "xac nhan nhan ca", "em đồng ý", "em dong y", "tôi đồng ý", "toi dong y"],
        0.9,
    ),
    (
        PROPOSE_TKB_CONFIRM,
        ["xác nhận tkb", "xac nhan tkb", "xác nhận lịch bận", "xac nhan lich ban", "tkb bận", "tkb ban", "gán tkb", "gan tkb", "chốt tkb", "chot tkb"],
        0.9,
    ),
    # Câu hỏi ĐỌC bàn giao đặt TRƯỚC PROPOSE_HANDOVER: "bàn giao ca gần nhất"
    # là câu hỏi đọc, không phải hành động ghi. Các cụm câu hỏi cụ thể phải
    # thắng từ chung "bàn giao ca" của PROPOSE_HANDOVER.
    #
    # Danh sách này từng chỉ có các cụm cố định ("bàn giao ca gần nhất", "lịch sử
    # bàn giao"...). Vì `parse_intent` khớp bằng `kw in lower` (khớp chuỗi con),
    # cách nói tự nhiên lệch một chữ là trượt hết: "Xem các bàn giao gần đây" —
    # có "các" và "gần đây" — rơi vào OUT_OF_SCOPE, copilot trả lời "em có thể hỗ
    # trợ..." thay vì mở danh sách bàn giao. Bổ sung các biến thể đọc rõ nghĩa.
    # KHÔNG thêm cụm trần "bàn giao" hay "bàn giao ca" vào đây: hai cụm đó là dấu
    # hiệu GHI bàn giao của PROPOSE_HANDOVER, thêm vào sẽ biến mọi câu ghi thành câu đọc.
    (
        GET_HANDOVERS,
        [
            "bàn giao ca gần nhất", "ban giao ca gan nhat",
            "bàn giao gần nhất", "ban giao gan nhat",
            "bàn giao gần đây", "ban giao gan day",
            "các bàn giao", "cac ban giao",
            "danh sách bàn giao", "danh sach ban giao",
            "bàn giao nào", "ban giao nao",
            "xem bàn giao ca", "xem ban giao ca",
            "xem bàn giao", "xem ban giao",
            "bàn giao ca nào", "ban giao ca nao",
            "lịch sử bàn giao", "lich su ban giao",
            "bàn giao ca hôm qua", "ban giao ca hom qua",
            "bàn giao ca hôm nay", "ban giao ca hom nay",
            "lịch sử sửa", "lich su sua", "bản ghi sửa", "ban ghi sua",
        ],
        0.9,
    ),
    (
        PROPOSE_HANDOVER,
        ["bàn giao ca", "ban giao ca", "ghi bàn giao", "ghi ban giao", "soạn bàn giao", "soan ban giao", "gửi bàn giao", "gui ban giao"],
        0.9,
    ),
    # QUERY_AUDIT — tra cứu vết hệ thống / nhật ký thay đổi (chỉ quản lý & chủ quán).
    # Đặt TRƯỚC các intent đọc khác để "nhật ký đổi ca" không rơi vào GET_SHIFT_SWAPS.
    (
        QUERY_AUDIT,
        [
            "nhật ký", "nhat ky", "nhật kí", "nhat ki",
            "audit log", "audit trail", "nhật ký hệ thống", "nhat ky he thong",
            "lịch sử thao tác", "lich su thao tac", "lịch sử hệ thống", "lich su he thong",
            "vết hệ thống", "vet he thong", "vết audit", "vet audit",
            "lịch sử thay đổi", "lich su thay doi", "lịch sử đổi ca", "lich su doi ca",
            "lịch sử xuất nhập kho", "lich su xuat nhap kho", "xuất nhập kho", "xuat nhap kho",
            "ai sửa", "ai sua", "ai thay đổi", "ai thay doi",
            "tra cứu vết", "tra cuu vet", "xem vết", "xem vet", "xem nhật ký", "xem nhat ky",
            "kiểm tra nhật ký", "kiem tra nhat ky", "kiểm tra vết", "kiem tra vet",
        ],
        0.9,
    ),
    # QUERY_QUANVERSE — hỏi về 4 mặt Trải nghiệm AI (Living Map / War Room / Cứu ca /
    # Hồn quán). Đặt TRƯỚC các intent đọc khác để câu hỏi về các trang này không
    # rơi nhầm vào lịch/tồn kho.
    (
        QUERY_QUANVERSE,
        [
            "quanverse", "quán vũ trụ", "quan vu tru", "trải nghiệm ai", "trai nghiem ai",
            "living map", "bản đồ sống", "ban do song", "war room", "phòng chiến", "phong chien",
            "cứu ca", "cuu ca", "ca vắng", "ca vang", "thiếu người", "thieu nguoi",
            "hồn quán", "hon quan", "ký ức quán", "ky uc quan", "tour quán", "tour quan",
            "mô phỏng kịch bản", "mo phong kich ban", "kịch bản nào", "kich ban nao",
        ],
        0.88,
    ),
    (
        GET_WEATHER,
        [
            "thời tiết hôm nay", "thoi tiet hom nay",
            "thời tiết thế nào", "thoi tiet the nao",
            "thời tiết quán", "thoi tiet quan",
            "dự báo thời tiết", "du bao thoi tiet",
            "thời tiết", "thoi tiet",
            "trời mưa không", "troi mua khong",
            "trời có mưa không", "troi co mua khong",
            "hôm nay có mưa không", "hom nay co mua khong",
            "nhiệt độ hôm nay", "nhiet do hom nay",
            "khuyến nghị thời tiết", "khuyen nghi thoi tiet",
        ],
        0.92,
    ),
    (
        GET_TODAY_OPERATIONS,
        [
            "tình hình hôm nay", "tinh hinh hom nay",
            "vận hành hôm nay", "van hanh hom nay",
            "tình hình quán hôm nay", "tinh hinh quan hom nay",
            "hôm nay quán thế nào", "hom nay quan the nao",
            "tổng quan hôm nay", "tong quan hom nay",
            "doanh thu hôm nay", "doanh thu hom nay",
            "hôm nay bán được bao nhiêu", "hom nay ban duoc bao nhieu",
            "bán được bao nhiêu", "ban duoc bao nhieu",
            "bao nhiêu đơn hôm nay", "bao nhieu don hom nay",
            "dashboard hôm nay", "dashboard hom nay",
        ],
        0.90,
    ),
    (
        GET_FAIRNESS_SUMMARY,
        [
            "báo cáo công bằng", "bao cao cong bang",
            "công bằng lịch ca", "cong bang lich ca",
            "ai bị thiệt ca", "ai bi thiet ca",
            "ai bị thiệt", "ai bi thiet",
            "phân bổ ca có đều không", "phan bo ca co deu khong",
            "ai làm nhiều nhất", "ai lam nhieu nhat",
            "ai làm ít nhất", "ai lam it nhat",
            "so sánh giờ làm", "so sanh gio lam",
            "độ lệch công bằng", "do lech cong bang",
            "thiếu giờ làm", "thieu gio lam",
            "phân bổ giờ làm", "phan bo gio lam",
        ],
        0.90,
    ),
    (
        GET_MY_CHECKLIST,
        [
            "checklist của tôi", "checklist cua toi",
            "phiếu của tôi", "phieu cua toi",
            "việc của tôi hôm nay", "viec cua toi hom nay",
            "việc của tôi", "viec cua toi",
            "checklist hôm nay", "checklist hom nay",
            "đầu việc hôm nay", "dau viec hom nay",
            "việc ca này của tôi", "viec ca nay cua toi",
            "đầu việc của tôi", "dau viec cua toi",
            "checklist ca", "checklist ca",
            "phiếu ca", "phieu ca",
            "mẫu phiếu", "mau phieu",
            "đầu việc ca này", "dau viec ca nay",
        ],
        0.90,
    ),
    (
        SEARCH_TRENDS,
        [
            "xu hướng", "xu huong",
            "xu hướng f&b", "xu huong f&b",
            "trend món mới", "trend mon moi", "trend f&b", "xu hướng món mới", "xu huong mon moi",
            "món hot", "mon hot",
            "món trending", "mon trending",
            "trend đồ uống", "trend do uong",
            "đồ uống hot trend", "do uong hot trend",
            "món đang viral", "mon dang viral",
            "thị trường đang hot món gì", "thi truong dang hot mon gi",
            "món mới viral", "mon moi viral",
        ],
        0.90,
    ),
    (
        GET_RESERVATIONS,
        [
            "đặt bàn hôm nay", "dat ban hom nay",
            "danh sách đặt bàn", "danh sach dat ban",
            "khách đặt bàn", "khach dat ban",
            "có ai đặt bàn không", "co ai dat ban khong",
            "ai đặt bàn", "ai dat ban",
            "bàn đặt hôm nay", "ban dat hom nay",
            "bàn nào đặt", "ban nao dat",
            "bàn đặt", "ban dat",
            "sơ đồ bàn", "so do ban",
            "bàn trống", "ban trong",
            "bàn còn trống", "ban con trong",
            "kiểm tra bàn", "kiem tra ban",
            "đặt bàn", "dat ban",
            "đặt chỗ", "dat cho",
        ],
        0.91,
    ),
    (
        GET_OPEN_SHIFTS,
        [
            "chợ ca", "cho ca",
            "ca mở", "ca mo",
            "ca trống", "ca trong",
            "ca thiếu người", "ca thieu nguoi",
            "có ca nào trống không", "co ca nao trong khong",
            "danh sách ca mở", "danh sach ca mo",
            "danh sách chợ ca", "danh sach cho ca",
            "open shift", "open shifts",
            "nhận thêm ca", "nhan them ca",
            "ca cần người", "ca can nguoi",
        ],
        0.91,
    ),
    (
        GET_PREDICTIVE_INSIGHTS,
        [
            "gợi ý vận hành", "goi y van hanh",
            "đề xuất tối ưu", "de xuat toi uu",
            "dự báo tuần tới", "du bao tuan toi",
            "dự báo tuần sau", "du bao tuan sau",
            "dự đoán tuần tới", "du doan tuan toi",
            "cần chú ý gì tuần tới", "can chu y gi tuan toi",
            "dự báo vận hành", "du bao van hanh",
            "playbook vận hành", "playbook van hanh",
            "luật tích cực", "luat tich cuc",
            "đề xuất luật tích cực", "de xuat luat tich cuc",
            "gợi ý tối ưu", "goi y toi uu",
            "predictive suggestions", "predictive playbook",
        ],
        0.90,
    ),
    (
        GET_SHIFT_SWAPS,
        [
            "đổi ca nào", "doi ca nao", "yêu cầu đổi ca nào", "yeu cau doi ca nao",
            "chợ đổi ca", "cho doi ca", "danh sách đổi ca", "danh sach doi ca",
            "ai đổi ca", "ai doi ca", "ai xin đổi ca", "ai xin doi ca",
            "có ai đổi ca", "co ai doi ca", "xem đổi ca", "xem doi ca",
            "kèo đổi ca", "keo doi ca", "ai muốn đổi ca", "ai muon doi ca",
            "danh sách yêu cầu đổi ca", "danh sach yeu cau doi ca",
        ],
        0.9,
    ),
    (
        GET_MY_PROFILE,
        ["hồ sơ của tôi", "ho so cua toi", "tôi là ai", "toi la ai", "thông tin của tôi", "thong tin cua toi"],
        0.9,
    ),
    # Xin nghỉ/bận đặt TRƯỚC các intent đọc: "tôi bận thứ 5" là HÀNH ĐỘNG
    # xin nghỉ, không phải câu hỏi — phải thắng từ khóa đọc nếu trùng.
    (
        PROPOSE_TIME_OFF,
        [
            "tôi bận",
            "toi ban",
            "tôi không rảnh",
            "toi khong ranh",
            "không rảnh",
            "khong ranh",
            "bận học",
            "ban hoc",
            "xin nghỉ",
            "xin nghi",
            "nghỉ ca",
            "nghi ca",
            "không đi làm",
            "khong di lam",
            "không đi được",
            "khong di duoc",
            "bận việc",
            "ban viec",
            "có việc bận",
            "co viec ban",
        ],
        0.92,
    ),
    (
        LIST_STAFF,
        [
            "danh sách nhân sự", "danh sach nhan su",
            "danh sách nhân viên", "danh sach nhan vien",
            "có bao nhiêu nhân viên", "co bao nhieu nhan vien",
            "quán có bao nhiêu nhân viên", "quan co bao nhieu nhan vien",
            "bao nhiêu nhân sự", "bao nhieu nhan su",
            "tổng số nhân viên", "tong so nhan vien",
            "liệt kê nhân viên", "liet ke nhan vien",
            "danh sách nhân", "danh sach nhan",
            "nhân sự hôm nay", "nhan su hom nay",
            "nhân sự của quán", "nhan su cua quan",
            "nhân sự hiện tại", "nhan su hien tai",
            "ai đang làm", "ai dang lam",
            "ai làm ca", "ai lam ca",
            "ai làm hôm nay", "ai lam hom nay",
            "hôm nay ai đi làm", "hom nay ai di lam",
            "nhân viên nào làm", "nhan vien nao lam",
        ],
        0.9,
    ),
    (
        PROPOSE_MENU_UPDATE,
        ["sửa giá", "sua gia", "đổi giá", "doi gia", "cập nhật giá", "cap nhat gia", "ẩn món", "an mon", "bỏ món", "bo mon", "thêm món", "them mon", "thêm món mới", "them mon moi"],
        0.9,
    ),
    # PR11 admin mutating — đặt TRƯỚC QUERY_MENU: "sửa giá món X" (hành động)
    # phải thắng "menu"/"giá món" (đọc).
    (
        PROPOSE_ORDER_TRANSITION,
        ["chuyển đơn", "chuyen don", "đơn đang pha", "don dang pha", "hủy đơn", "huy don", "xác nhận đơn", "xac nhan don", "đơn xong", "don xong"],
        0.9,
    ),
    (
        PROPOSE_PIN,
        ["ghim ca", "pin ca", "ghim lịch", "ghim lich"],
        0.9,
    ),    # PR12 external channels
    (
        PROPOSE_PAGE_DRAFT,
        [
            "đăng bài lên fb", "dang bai len fb",
            "đăng bài lên page", "dang bai len page",
            "đăng bài fb", "dang bai fb",
            "đăng bài page", "dang bai page",
            "đăng bài facebook", "dang bai facebook",
            "đăng bài", "dang bai",
            "post bài lên fb", "post bai len fb",
            "post bài lên page", "post bai len page",
            "post bài", "post bai",
            "viết bài đăng", "viet bai dang",
            "viết bài lên fb", "viet bai len fb",
            "viết bài lên page", "viet bai len page",
            "viết bài fb", "viet bai fb",
            "soạn bài fb", "soan bai fb",
            "soạn bài đăng", "soan bai dang",
            "bài đăng fanpage", "bai dang fanpage",
            "bài viết page", "bai viet page",
        ],
        0.92,
    ),
    (
        PROPOSE_PAGE_SYNC,
        ["đồng bộ page", "dong bo page", "sync page", "đồng bộ fanpage", "dong bo fanpage", "kéo tin nhắn page", "keo tin nhan page"],
        0.9,
    ),
    (
        GET_PAGE_STATUS,
        ["trạng thái page", "trang thai page", "page có sống", "page co song", "fanpage còn nối", "fanpage con noi", "kết nối page", "ket noi page"],
        0.9,
    ),    (
        QUERY_MENU,
        ["menu", "món gì", "mon gi", "có bán", "co ban", "giá món", "gia mon", "bảng giá", "bang gia"],
        0.9,
    ),
    # PR10 self-service mutating — đặt TRƯỚC GET_HANGING_TASKS: cụm hành động
    # ("đánh dấu xong việc treo", "treo việc X") phải thắng cụm đọc ("việc treo").
    (
        PROPOSE_TASK_COMPLETE,
        ["đánh dấu xong việc treo", "danh dau xong viec treo", "xong việc treo", "xong viec treo", "hoàn thành việc treo", "hoan thanh viec treo"],
        0.9,
    ),
    (
        PROPOSE_HANGING_TASK,
        ["treo việc", "treo viec", "treoviệc", "treoviec", "tạo việc treo", "tao viec treo", "ghi việc treo", "ghi viec treo"],
        0.9,
    ),
    (
        PROPOSE_CONSUMPTION_RECORD,
        ["ghi tiêu thụ", "ghi tieu thu", "ghi tồn kho", "ghi ton kho", "nhập tiêu thụ", "nhap tieu thu"],
        0.9,
    ),
    (
        GET_HANGING_TASKS,
        ["việc treo", "viec treo", "treo việc nào", "treo viec nao", "công việc đang treo", "cong viec dang treo"],
        0.9,
    ),
    # PR13 read — ràng buộc chờ duyệt / lịch cá nhân phải thắng từ chung của
    # mutating intents ("đổi ca"). GET_SCHEDULE đặt TRƯỚC SCHEDULE_SOLVE để các
    # cụm phủ định ("chưa dc xếp lịch") match đúng intent đọc. Post-match override
    # bên dưới sẽ sửa thành SCHEDULE_SOLVE khi có động từ hành động ("xếp lịch").
    (
        GET_MY_SHIFTS,
        [
            "lịch của tôi", "lich cua toi", "ca của tôi", "ca cua toi",
            "lịch làm việc của tôi", "lich lam viec cua toi",
            "ca của mình", "ca cua minh", "lịch tôi", "lich toi",
            "lịch của em", "lich cua em", "ca tôi làm", "ca toi lam",
            # Khẩu ngữ văn nói (voice): người dùng chèn trạng từ thời gian vào
            # GIỮA cụm ("lịch hôm nay của tôi") nên các cụm cố định ở trên trượt.
            # Thiếu nhóm này, câu nói qua mic rơi vào OUT_OF_SCOPE và Live
            # Copilot không gọi tool tra cứu lịch — chỉ đáp câu xã giao.
            "lịch hôm nay của tôi", "lich hom nay cua toi",
            "lịch hnay của tôi", "lich hnay cua toi",
            "lịch hnay của t", "lich hnay cua t",
            "lịch hôm nay của t", "lich hom nay cua t",
            "lịch hôm nay của em", "lich hom nay cua em",
            "lịch hôm nay của mình", "lich hom nay cua minh",
            "lịch làm việc hôm nay của tôi", "lich lam viec hom nay cua toi",
            "lịch làm việc hôm nay của t", "lich lam viec hom nay cua t",
            "ca hôm nay của tôi", "ca hom nay cua toi",
            "ca hôm nay của t", "ca hom nay cua t",
            "ca hôm nay của em", "ca hom nay cua em",
            "ca của tôi hôm nay", "ca cua toi hom nay",
            "ca của t hôm nay", "ca cua t hom nay",
            "lịch của tôi hôm nay", "lich cua toi hom nay",
            "hôm nay tôi có ca không", "hom nay toi co ca khong",
            "hnay toi co ca khong", "hnay t co ca khong",
            "hnay toi co ca k", "hnay t co ca k",
            "hôm nay t có ca không", "hom nay t co ca khong",
            "hôm nay em có ca không", "hom nay em co ca khong",
            "hôm nay tôi có lịch không", "hom nay toi co lich khong",
            "hôm nay tôi có đi làm không", "hom nay toi co di lam khong",
            "hôm nay t có đi làm không", "hom nay t co di lam khong",
            "hôm nay tôi làm ca gì", "hom nay toi lam ca gi",
            "hôm nay tôi làm ca mấy", "hom nay toi lam ca may",
            "hôm nay t làm ca gì", "hom nay t lam ca gi",
            "hôm nay tôi làm gì", "hom nay toi lam gi",
            "hôm nay tôi có phải đi làm", "hom nay toi co phai di lam",
            "mai tôi có ca không", "mai toi co ca khong",
            "mai t có ca không", "mai t co ca khong",
            "ngày mai tôi có ca không", "ngay mai toi co ca khong",
            "tuần này tôi có ca không", "tuan nay toi co ca khong",
            "tuần này tôi có mấy ca", "tuan nay toi co may ca",
            "lịch ngày mai của tôi", "lich ngay mai cua toi",
            "lịch ngày mai của t", "lich ngay mai cua t",
            "lịch mai của tôi", "lich mai cua toi",
            "lịch mai của t", "lich mai cua t",
            "ca ngày mai của tôi", "ca ngay mai cua toi",
            "ngày mai tôi có ca không", "ngay mai toi co ca khong",
            "thứ hai tôi có ca không", "thu hai toi co ca khong",
            "thứ bảy tôi có ca không", "thu bay toi co ca khong",
            "lịch thứ hai của tôi", "lich thu hai cua toi",
            "lịch thứ ba của tôi", "lich thu ba cua toi",
            "lịch thứ tư của tôi", "lich thu tu cua toi",
            "lịch thứ năm của tôi", "lich thu nam cua toi",
            "lịch thứ sáu của tôi", "lich thu sau cua toi",
            "lịch thứ bảy của tôi", "lich thu bay cua toi",
            "lịch chủ nhật của tôi", "lich chu nhat cua toi",
            "lịch tuần sau của tôi", "lich tuan sau cua toi",
            "lịch tuần trước của tôi", "lich tuan truoc cua toi",
            "lịch tháng sau của tôi", "lich thang sau cua toi",
            "lịch tháng trước của tôi", "lich thang truoc cua toi",
            "lịch tuần này của tôi", "lich tuan nay cua toi",
            "lịch tháng này của tôi", "lich thang nay cua toi",
            "lịch tháng này của t", "lich thang nay cua t",
            "lịch tuần sau của t", "lich tuan sau cua t",
            "lịch chủ nhật này của tôi", "lich chu nhat nay cua toi",
            "tôi có ca thứ hai không", "toi co ca thu hai khong",
            "ca thứ hai của tôi", "ca thu hai cua toi",
            "tôi có ca không", "toi co ca khong",
            "em có ca không", "em co ca khong",
            "tôi có lịch không", "toi co lich khong",
            "tôi có ca chứ", "toi co ca chu",
            "tôi có ca hôm nay không", "toi co ca hom nay khong",
            "tôi có ca hôm nay chứ", "toi co ca hom nay chu",
            "em có ca hôm nay không", "em co ca hom nay khong",
            "tôi có lịch hôm nay không", "toi co lich hom nay khong",
            "ca thứ ba của tôi", "ca thu ba cua toi",
            "ca thứ tư của tôi", "ca thu tu cua toi",
            "ca thứ năm của tôi", "ca thu nam cua toi",
            "ca thứ sáu của tôi", "ca thu sau cua toi",
            "ca thứ bảy của tôi", "ca thu bay cua toi",
            "ca chủ nhật của tôi", "ca chu nhat cua toi",
            "tôi làm ca nào hôm nay", "toi lam ca nao hom nay",
            "ca làm việc hôm nay của tôi", "ca lam viec hom nay cua toi",
            "ca tối nay của tôi", "ca toi nay cua toi",
            "ca sáng nay của tôi", "ca sang nay cua toi",
            "ca chiều nay của tôi", "ca chieu nay cua toi",
            "tối nay tôi có ca không", "toi nay toi co ca khong",
            "sáng nay tôi có ca không", "sang nay toi co ca khong",
            "lịch tháng này của tôi", "lich thang nay cua toi",
            "lịch tuần này của tôi", "lich tuan nay cua toi",
            "tuần này tôi làm ca gì", "tuan nay toi lam ca gi",
            "tôi có ca mấy giờ", "toi co ca may gio",
            "ca của tôi mấy giờ", "ca cua toi may gio",
            "lịch làm việc tuần này của tôi", "lich lam viec tuan nay cua toi",
            "lịch làm việc tuần này của t", "lich lam viec tuan nay cua t",
            "lịch làm việc tháng này của tôi", "lich lam viec thang nay cua toi",
            "lịch làm việc của tôi", "lich lam viec cua toi",
            "lịch làm việc của t", "lich lam viec cua t",
            "lịch làm việc của em", "lich lam viec cua em",
            "tôi làm ca nào tuần này", "toi lam ca nao tuan nay",
            "tuần này tôi có ca nào", "tuan nay toi co ca nao",
        ],
        0.9,
    ),
    (
        GET_CONSTRAINT_CANDIDATES,
        [
            "ràng buộc chờ duyệt", "rang buoc cho duyet", "ràng buộc nào", "rang buoc nao",
            "xin nghỉ chờ", "xin nghi cho", "inbox ràng buộc", "inbox rang buoc",
            "danh sách ràng buộc", "danh sach rang buoc", "ràng buộc chưa duyệt", "rang buoc chua duyet",
            "ai có thể thay ca", "ai co the thay ca", "ai thay ca",
            "ai có thể thay", "ai co the thay", "ai thay được ca", "ai thay duoc ca",
            "ai thay ca tối nay", "ai thay ca toi nay", "ai có thể thay ca tối nay", "ai co the thay ca toi nay",
            "ai thay ca tuần này", "ai thay ca tuan nay", "ai có thể thay ca tuần này", "ai co the thay ca tuan nay",
        ],
        0.9,
    ),
    (
        GET_SERPAPI_QUOTA,
        [
            "hạn ngạch serpapi", "han ngach serpapi", "quota serpapi", "kiểm tra quota", "kiem tra quota",
            "lượt tìm kiếm còn lại", "luot tim kiem con lai", "hạn mức serpapi", "han muc serpapi",
            "hạn ngạch tìm kiếm", "han ngach tim kiem", "quota tìm kiếm", "quota tim kiem",
        ],
        0.92,
    ),
    (
        GET_SURVEY_RESULT,
        [
            "kết quả khảo sát giá", "ket qua khao sat gia", "báo cáo đối thủ gần nhất", "bao cao doi thu gan nhat",
            "kết quả radar giá", "ket qua radar gia", "kết quả khảo sát đối thủ", "ket qua khao sat doi thu",
            "xem khảo sát giá", "xem khao sat gia", "báo cáo khảo sát giá", "bao cao khao sat gia",
        ],
        0.91,
    ),
    (
        GET_SCHEDULE,
        [
            # Trạng thái chưa xếp / chưa duyệt (priority cao)
            "chưa được xếp lịch", "chua duoc xep lich",
            "chưa dc xếp lịch", "chua dc xep lich",
            "chưa được xếp ca", "chua duoc xep ca",
            "chưa dc xếp ca", "chua dc xep ca",
            "chưa có ca", "chua co ca",
            "chưa có lịch", "chua co lich",
            "chưa xếp lịch", "chua xep lich",
            "chưa xếp ca", "chua xep ca",
            "chưa duyệt lịch", "chua duyet lich",
            "chưa xác nhận lịch", "chua xac nhan lich",
            "chưa chốt lịch", "chua chot lich",
            "chưa được duyệt", "chua duoc duyet",
            "ai chưa có ca", "ai chua co ca",
            "ai chưa có lịch", "ai chua co lich",
            "ai chưa được xếp", "ai chua duoc xep",
            "ai chưa dc xếp", "ai chua dc xep",
            "ai chưa duyệt", "ai chua duyet",
            "ai chưa xác nhận", "ai chua xac nhan",
            "ai chưa chốt", "ai chua chot",
            "ai chưa xếp", "ai chua xep",
            "nhân viên nào chưa", "nhan vien nao chua",
            "nhân sự nào chưa", "nhan su nao chua",
            "có ai chưa có ca", "co ai chua co ca",
            "có ai chưa duyệt", "co ai chua duyet",
            "có ai chưa được xếp", "co ai chua duoc xep",
            "có nhân viên nào chưa", "co nhan vien nao chua",
            # Tra cứu lịch tổng quát (priority thấp hơn nhưng cùng intent)
            "xem lịch tuần", "xem lich tuan",
            "lịch tuần này", "lich tuan nay",
            "lịch làm việc", "lich lam viec",
            "xem lịch", "xem lich",
            "lịch ca", "lich ca",
            "tình hình lịch", "tinh hinh lich",
            "trạng thái lịch", "trang thai lich",
            "roster",
        ],
        0.92,
    ),
    (
        SCHEDULE_SOLVE,
        [
            "xếp lịch", "xep lich", "chia ca", "xếp ca", "xep ca", "lên lịch", "len lich",
            "chạy solver", "chay solver", "phân công ca", "phan cong ca", "tạo lịch", "tao lich",
            "lên kế hoạch", "len ke hoach", "lập kế hoạch", "lap ke hoach",
            "lập lịch", "lap lich", "kế hoạch lịch", "ke hoach lich",
            "kế hoạch ca", "ke hoach ca", "kế hoạch xếp ca", "ke hoach xep ca",
            "kế hoạch tuần", "ke hoach tuan",
            "xếp lịch từ cuộc họp", "xep lich tu cuoc hop",
            "lập lịch từ cuộc họp", "lap lich tu cuoc hop",
            "lên kế hoạch từ cuộc họp", "len ke hoach tu cuoc hop",
            "kế hoạch từ cuộc họp", "ke hoach tu cuoc hop",
            "lấy thông tin cuộc họp để lên kế hoạch", "lay thong tin cuoc hop de len ke hoach",
            "lấy thông tin cuộc họp để xếp lịch", "lay thong tin cuoc hop de xep lich",
        ],
        0.92,
    ),
    (
        GET_MEETINGS,
        [
            "biên bản họp", "bien ban hop",
            "họp giao ban", "hop giao ban",
            "cuộc họp gần nhất", "cuoc hop gan nhat",
            "kết quả cuộc họp", "ket qua cuoc hop",
            "kết quả họp", "ket qua hop",
            "nội dung cuộc họp", "noi dung cuoc hop",
            "nội dung họp", "noi dung hop",
            "biên bản cuộc họp", "bien ban cuoc hop",
            "tóm tắt cuộc họp", "tom tat cuoc hop",
            "cuộc họp", "cuoc hop",
        ],
        0.89,
    ),
    (
        APPROVE_SHIFT_SWAP,
        [
            "duyệt đổi ca", "duyet doi ca",
            "duyệt ca", "duyet ca",
            "xem xét duyệt đổi ca", "xem xet duyet doi ca",
            "phê duyệt đổi ca", "phe duyet doi ca",
            "đồng ý cho đổi ca", "dong y cho doi ca",
            "chấp thuận đổi ca", "chap thuan doi ca",
            "duyệt đơn đổi ca", "duyet don doi ca",
            "duyệt yêu cầu đổi ca", "duyet yeu cau doi ca",
            "xác nhận duyệt đổi ca", "xac nhan duyet doi ca",
            "đổi ca cho", "doi ca cho",
            "nhường ca cho", "nhuong ca cho",
        ],
        0.90,
    ),
    (
        GENERATE_DAILY_BRIEF,
        [
            "bản tin", "ban tin", "tin sáng", "tin sang", "tóm tắt đầu ngày", "tom tat dau ngay",
            "tình hình hôm nay", "tinh hinh hom nay", "tình hình ca sáng", "tinh hinh ca sang",
            "quán hôm nay thế nào", "quan hom nay the nao",
            "tình hình quán", "tinh hinh quan",
            "tổng kết hôm nay", "tong ket hom nay",
            "tổng quan hôm nay", "tong quan hom nay",
        ],
        0.95,
    ),
    (
        QUERY_SOP,
        [
            "quy trình", "quy trinh", "cẩm nang", "cam nang", "hướng dẫn", "huong dan",
            "mở quán", "mo quan", "đóng quán", "dong quan",
            "vệ sinh", "ve sinh", "cách làm", "cach lam", "sop",
            "cách pha", "cach pha", "công thức", "cong thuc",
            "hướng dẫn pha", "huong dan pha", "quy trình pha", "quy trinh pha",
            "cách nấu", "cach nau", "pha chế", "pha che",
        ],
        0.90,
    ),
    (
        ANALYZE_WASTE,
        [
            # Cụm gốc — giữ nguyên để không đổi hành vi cũ.
            "hao hụt", "hao hut", "hàng hủy", "hang huy", "lãng phí", "lang phi",
            "sữa hỏng", "sua hong", "đổ bọt", "do bot", "báo cáo hủy", "bao cao huy",
            # Cụm của câu hỏi định lượng: người quán hỏi "hao bao nhiêu", "nguyên liệu
            # nào hao", "lệch kiểm kê" chứ không chỉ nói "hao hụt". Không thêm thì
            # những câu đó rơi vào OUT_OF_SCOPE dù đúng thẩm quyền của intent này.
            "thất thoát", "that thoat",
            "hao phí", "hao phi",
            "lệch kiểm kê", "lech kiem ke",
            "lệch kho", "lech kho",
            "chênh lệch nguyên liệu", "chenh lech nguyen lieu",
            "nguyên liệu nào hao", "nguyen lieu nao hao",
            "hao bao nhiêu", "hao bao nhieu",
            "tiêu hao nguyên liệu", "tieu hao nguyen lieu",
            "tỷ lệ hao", "ty le hao",
            "mức hao", "muc hao",
        ],
        0.91,
    ),
    (
        CREATE_RULE_PROPOSAL,
        [
            "đề xuất luật", "de xuat luat",
            "đề xuất luật mới", "de xuat luat moi",
            "luật mới", "luat moi",
            "cẩm nang sống", "cam nang song",
            "tạo luật", "tao luat",
            "học luật", "hoc luat",
            "thêm quy tắc", "them quy tac",
        ],
        0.90,
    ),
    # GET_INVENTORY (đọc tồn kho) đặt TRƯỚC INVENTORY_RESTOCK_CHECK: "xem tồn kho"
    # là câu hỏi, còn "kiểm tồn kho" là mệnh lệnh kiểm kê. Cùng một từ "tồn kho" nhưng
    # hai intent khác nhau — nếu để restock trước thì câu hỏi bị nuốt mất.
    # Chỉ dùng cụm có nghĩa "XEM", tránh bare "tồn kho" để không cướp mất câu kiểm kê.
    (
        GET_INVENTORY,
        [
            "xem tồn kho", "xem ton kho",
            "danh sách tồn kho", "danh sach ton kho",
            "tồn kho còn", "ton kho con",
            "còn bao nhiêu hàng", "con bao nhieu hang",
            "hàng còn trong kho", "hang con trong kho",
            "kho còn bao nhiêu", "kho con bao nhieu",
            "trong kho còn", "trong kho con",
            "tồn kho hiện tại", "ton kho hien tai",
            "còn bao nhiêu trong kho", "con bao nhieu trong kho",
            "hàng còn bao nhiêu", "hang con bao nhieu",
            "nguyên liệu còn bao nhiêu", "nguyen lieu con bao nhieu",
            "xem kho", "xem còn gì trong kho", "xem con gi trong kho",
        ],
        0.92,
    ),
    (
        INVENTORY_RESTOCK_CHECK,
        ["kiểm kho", "kiem kho", "tồn kho", "ton kho", "sắp hết hàng", "sap het hang", "hết sữa", "het sua",
         "đặt hàng", "dat hang", "nhập hàng", "nhap hang", "ngưỡng tồn", "nguong ton", "restock",
         "cần nhập thêm gì", "can nhap them gi", "cần nhập gì", "can nhap gi",
         "nhập thêm gì", "nhap them gi", "mua thêm gì", "mua them gi",
         "nguyên liệu nào sắp hết", "nguyen lieu nao sap het",
         "cần đặt thêm gì", "can dat them gi",
        ],
        0.90,
    ),
    (
        RUN_CATCHMENT_SURVEY,
        [
            "khảo sát giá", "khao sat gia",
            "quét giá đối thủ", "quet gia doi thu",
            "quét đối thủ", "quet doi thu",
            "quét giá", "quet gia",
            "phân tích giá khu vực", "phan tich gia khu vuc",
            "radar định giá", "radar dinh gia",
            "radar giá", "radar gia",
            "khảo sát đối thủ", "khao sat doi thu",
            "so sánh giá khu vực", "so sanh gia khu vuc",
            "khảo sát thị trường", "khao sat thi truong",
            "báo cáo đối thủ quanh", "bao cao doi thu quanh",
        ],
        0.90,
    ),
    (
        SEND_MAIL,
        [
            "gửi mail",
            "gui mail",
            "gửi email",
            "gui email",
            "gửi gmail",
            "gui gmail",
            "email cho",
            "mail cho",
            "nhắn qua email",
            "nhan qua email",
            "gửi thông báo qua email",
            "gui thong bao qua email",
            "soạn mail",
            "soan mail",
            "soạn email",
            "soan email",
            "soạn gmail",
            "soan gmail",
            "viết mail",
            "viet mail",
            "viết email",
            "viet email",
            "viết gmail",
            "viet gmail",
            "nhờ soạn mail",
            "nho soan mail",
            "nhờ viết mail",
            "nho viet mail",
        ],
        0.92,
    ),
]


@dataclass
class IntentParseResult:
    intent: str
    confidence: float
    params: dict[str, Any]
    clarification_needed: bool = False
    clarification_question: str | None = None
    security_flag: str | None = None
    # Tên tham số đang thiếu khiến phải hỏi lại (vd "thieu_ly_do"). Để client
    # biết lượt sau có cần coi câu của người dùng là câu TRẢ LỜI hay không,
    # thay vì so chuỗi trong câu hỏi.
    clarification_kind: str | None = None


def _iso_week(d: Any) -> str:
    """Trả về ISO week dạng 'YYYY-Wnn'. Không hardcode."""
    from datetime import date

    if not isinstance(d, date):
        d = date.today()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _add_week(d: Any, n: int = 1) -> Any:
    """Cộng n tuần (giữ nguyên kiểu date)."""
    from datetime import date, timedelta

    if not isinstance(d, date):
        d = date.today()
    return d + timedelta(weeks=n)


def _ngay_hom_nay_vn(active_date: Any | None = None) -> str:
    """Ngày hôm nay theo giờ VN (UTC+7) — hoặc active_date nếu context gắn sẵn.

    Tự tính UTC+7 tại chỗ: không import `ag_waste` (kiến trúc agent không gọi agent).
    """
    from datetime import date, datetime, timedelta, timezone

    if isinstance(active_date, date) and not isinstance(active_date, datetime):
        # Context test gắn active_date tường minh → tôn trọng, không lệch TZ.
        return active_date.isoformat()
    vn = timezone(timedelta(hours=7))
    return datetime.now(vn).date().isoformat()


def _tuan_tuong_doi(lower: str, active_date: Any) -> dict[str, Any] | None:
    """Nhận diện tuần tương đối trên MỘT câu — không lẫn lịch sử chat."""
    from datetime import date

    if any(k in lower for k in ("hôm nay", "hom nay")):
        ngay = _ngay_hom_nay_vn(active_date)
        try:
            d = date.fromisoformat(ngay)
            tuan = _iso_week(d)
        except ValueError:
            tuan = _iso_week(active_date)
        return {"tuan": tuan, "ngay_hom_nay": ngay}
    if any(k in lower for k in ("tuần sau", "tuan sau", "tuần tới", "tuan toi")):
        return {"tuan": _iso_week(_add_week(active_date, 1))}
    if any(k in lower for k in ("tuần này", "tuan nay")):
        return {"tuan": _iso_week(active_date)}
    return None


def _tuan_tuong_minh(lower: str, active_date: Any) -> dict[str, Any] | None:
    """Nhận diện `2026-W41` / `W41` / `tuần 41`."""
    m_iso = re.search(r"\b(\d{4})-w(\d{1,2})\b", lower)
    if m_iso:
        return {"tuan": f"{int(m_iso.group(1)):04d}-W{int(m_iso.group(2)):02d}"}
    m_w = re.search(r"\bw(\d{1,2})\b", lower)
    if m_w:
        return {"tuan": f"{active_date.year}-W{int(m_w.group(1)):02d}"}
    m_tuan_so = re.search(r"\btu[aầ]n\s*(\d{1,2})\b", lower)
    if m_tuan_so:
        return {"tuan": f"{active_date.year}-W{int(m_tuan_so.group(1)):02d}"}
    return None


def parse_tuan_tu_van_ban(
    text: str,
    *,
    active_date: Any | None = None,
    mac_dinh_tuan_sau: bool = False,
    uu_tien: str | None = None,
) -> dict[str, Any]:
    """Parser tuần thống nhất cho SCHEDULE_SOLVE / GET_SCHEDULE / TIME_OFF.

    Nhận: `tuần sau` · `tuần này` · `hôm nay` · `2026-W41` · `W41` · `tuần 41`.
    `uu_tien` = câu hiện tại (ưu tiên tương đối trước khi đọc lịch sử chat trong
    `text`, tránh «tuần sau nhé» bị dính W41 của tin trước).
    """
    from datetime import date

    if not isinstance(active_date, date):
        active_date = _active_date({})
    current = (uu_tien or "").lower()
    combined = (text or "").lower()

    for blob in (current, combined):
        if not blob:
            continue
        hit = _tuan_tuong_doi(blob, active_date)
        if hit:
            return hit
        hit = _tuan_tuong_minh(blob, active_date)
        if hit:
            return hit

    if mac_dinh_tuan_sau:
        return {"tuan": _iso_week(_add_week(active_date, 1))}
    return {"tuan": _iso_week(active_date)}


# ── Parse xin nghỉ / báo bận ────────────────────────────────────────────────
# Logic nằm trong `timeoff_parse` để `tool_registry` dùng CHUNG — trước đây có
# hai bản `_parse_thu`/`_parse_ca_range` copy-paste, lệch nhau theo thời gian nên
# cùng một câu có thể ra hai kết quả tuỳ chỗ gọi. Các tên bên dưới giữ lại để
# không phá vỡ import cũ (test + `tool_registry`).
_parse_thu = parse_thu
_parse_ca_range = parse_ca_range
_parse_thu_tuong_doi = parse_thu_tuong_doi
_CA_RANGE_INTENT = CA_RANGE



def _active_date(context: dict[str, Any]) -> Any:
    from datetime import date

    raw = str(context.get("active_date") or "").strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return date.today()


def _extract_survey_params(text: str) -> tuple[dict[str, Any], str | None]:
    """Trích xuất tham số khảo sát giá từ câu nói người dùng (plan v2.0 mục 4.2).

    Returns:
        (params, clarification_question): nếu thiếu thông tin hoặc vượt ngưỡng,
        clarification_question sẽ có nội dung hỏi lại thay vì đoán mò.
    """
    lower = text.lower()

    # 1. Trích xuất bán kính (km)
    m_r = re.search(
        r"(?:bán\s*kính|ban\s*kinh|trong\s*vòng|trong\s*vong|phạm\s*vi|pham\s*vi)?\s*(\d+(?:[.,]\d+)?)\s*(?:km|cây|cay|kilomet|kilômét)\b",
        lower,
    )
    radius_km = 3.0
    if m_r:
        try:
            r_val = float(m_r.group(1).replace(",", "."))
            if r_val > 10.0:
                return {}, f"Dạ bán kính khảo sát tối đa là 10.0km (đang yêu cầu {r_val}km). Anh/chị vui lòng chọn bán kính từ 0.5km đến 10.0km nhé!"
            if r_val < 0.5:
                return {}, f"Dạ bán kính khảo sát tối thiểu là 0.5km (đang yêu cầu {r_val}km). Anh/chị vui lòng chọn bán kính từ 0.5km đến 10.0km nhé!"
            radius_km = r_val
        except ValueError:
            pass

    # 2. Trích xuất kênh (channel_mode)
    channel_mode = "hybrid"
    if any(k in lower for k in ["tại quán", "tai quan", "tại chỗ", "tai cho", "dine in", "dine-in", "menu ảnh", "menu anh"]):
        channel_mode = "dine_in_vision"
    elif any(k in lower for k in ["online", "trên sàn", "tren san", "delivery", "shopeefood", "grabfood", "giao hàng", "giao hang"]):
        channel_mode = "delivery_platform"

    # 3. Trích xuất danh mục / món
    category: str | None = None
    canonical_dishes = {
        "cơm tấm": "cơm tấm", "com tam": "cơm tấm",
        "cơm sườn": "cơm sườn", "com suon": "cơm sườn",
        "bún bò": "bún bò", "bun bo": "bún bò",
        "cà phê": "cà phê", "ca phe": "cà phê",
        "bạc xỉu": "bạc xỉu", "bac xiu": "bạc xỉu",
        "cà phê sữa": "cà phê sữa", "ca phe sua": "cà phê sữa",
        "cà phê đen": "cà phê đen", "ca phe den": "cà phê đen",
        "đen đá": "đen đá", "den da": "đen đá",
        "espresso": "espresso", "latte": "latte", "cappuccino": "cappuccino", "americano": "americano",
        "trà sữa": "trà sữa", "tra sua": "trà sữa",
        "trà đào": "trà đào", "tra dao": "trà đào",
        "trà trái cây": "trà trái cây", "tra trai cay": "trà trái cây",
        "trà chanh": "trà chanh", "tra chanh": "trà chanh",
        "trà ô long": "trà ô long", "tra o long": "trà ô long", "tra oolong": "trà ô long",
        "matcha": "matcha", "cacao": "cacao",
        "phở bò": "phở bò", "pho bo": "phở bò",
        "phở gà": "phở gà", "pho ga": "phở gà",
        "hủ tiếu": "hủ tiếu", "hu tieu": "hủ tiếu",
        "bánh mì": "bánh mì", "banh mi": "bánh mì",
        "bánh ngọt": "bánh ngọt", "banh ngot": "bánh ngọt",
        "croissant": "croissant",
        "bún chả": "bún chả", "bun cha": "bún chả",
        "bún riêu": "bún riêu", "bun rieu": "bún riêu",
        "mì quảng": "mì quảng", "mi quang": "mì quảng",
        "bánh cuốn": "bánh cuốn", "banh cuon": "bánh cuốn",
        "nước ép": "nước ép", "nuoc ep": "nước ép",
        "sinh tố": "sinh tố", "sinh to": "sinh tố",
    }
    for d, canonical in canonical_dishes.items():
        if re.search(r"\b" + re.escape(d) + r"\b", lower):
            category = canonical
            break

    if not category:
        # Regex trích xuất danh mục sau các từ khóa khảo sát (bao gồm cả biến thể)
        m_cat = re.search(
            r"(?:khảo\s*sát\s*thị\s*trường|khao\s*sat\s*thi\s*truong|khảo\s*sát\s*giá|khao\s*sat\s*gia|radar\s*định\s*giá|quét\s*giá|quet\s*gia|quét\s*đối\s*thủ|quet\s*doi\s*thu|giá\s*món|gia\s*mon|giá)\s+([a-zA-ZÀ-ỹ0-9\s]+?)(?:\s+(?:quanh|trong|ở|tai|tại|bán\s*kính|với|theo)|\s*$)",
            text,
            re.IGNORECASE,
        )
        if m_cat:
            cand = m_cat.group(1).strip()
            cand = re.sub(r"^(?:của|cho|về|ngành|món)\s+", "", cand, flags=re.IGNORECASE).strip()
            # Lọc bỏ các token chỉ khoảng cách (ví dụ 2km, 3m)
            cand = re.sub(r"\d+(?:\.\d+)?\s*(?:km|m|cay)\b", "", cand, flags=re.IGNORECASE).strip()
            # Bỏ các từ không phải món
            if (
                cand.lower() not in ["thị trường", "khu vực", "đối thủ", "quán", "quanh quán", "bán kính", ""]
                and 2 <= len(cand) <= 40
                and len(cand.split()) <= 4
            ):
                category = cand

    # Nếu không trích xuất được danh mục -> yêu cầu làm rõ theo Non-Goal §1.3
    if not category:
        return {}, "Dạ anh/chị muốn khảo sát giá cho món ăn hoặc ngành hàng nào (ví dụ: bún bò, cà phê, cơm tấm...) ạ?"

    return {
        "category_keyword": category,
        "radius_km": radius_km,
        "channel_mode": channel_mode,
        "include_substitutes": True,
    }, None


# ── Làm rõ (clarification) khi thiếu tham số bắt buộc ────────────────────────
# Các intent mutating đã từ lâu set cờ `thieu_*` trong `params` (thieu_noi_dung,
# thieu_treo_id, thieu_thong_tin, thieu_khoang_ban, thieu_swap_id…) nhưng KHÔNG
# có bước nào đọc chúng: `clarification_needed` chỉ bật qua ngưỡng confidence.
# Hệ quả là khi thiếu thông tin, copilot vẫn chạy tool, tool fail-closed rồi
# người dùng nhận câu "chưa tạo được đề xuất" — vòng vo, không biết phải bổ
# sung gì. Nay có bước chung: thấy cờ thiếu thì hỏi lại đúng thứ đang thiếu.

CAU_HOI_TIME_OFF_LY_DO = (
    "Dạ cho em xin lý do xin nghỉ với ạ? Anh/chị nói giúp em cụ thể "
    "(vd: «vì đi khám bệnh», «vì việc gia đình») để em lập đề xuất cho quản lý duyệt ạ."
)
CAU_HOI_TIME_OFF_NGAY = (
    "Dạ anh/chị cho em biết cụ thể ngày nào bận ạ "
    "(vd: «thứ 5», «buổi chiều thứ 5», «ngày mai») ạ?"
)
CAU_HOI_TIME_OFF_CA_NHAY = (
    "Dạ anh/chị cho em biết ngày nào bận và lý do xin nghỉ với ạ? "
    "Anh/chị nói một câu tự nhiên là được, vd: «thứ 5 buổi chiều, vì đi khám bệnh» ạ."
)

_CAU_HOI_LAM_RO: dict[str, dict[str, str]] = {
    PROPOSE_HANGING_TASK: {
        "thieu_noi_dung": "Dạ anh/chị treo việc gì ạ? Anh/chị mô tả ngắn nội dung việc để em ghi lại ạ.",
    },
    PROPOSE_HANDOVER: {
        "thieu_noi_dung": "Dạ anh/chị gửi nội dung bàn giao ca giúp em ạ.",
    },
    PROPOSE_TASK_COMPLETE: {
        "thieu_treo_id": "Dạ việc treo cần đánh dấu xong có mã (vd: «treo_a1b2») — anh/chị gửi em mã nhé ạ?",
    },
    PROPOSE_MENU_UPDATE: {
        "thieu_thong_tin": (
            "Dạ anh/chị muốn làm gì với món nào ạ? "
            "Vd: «sửa giá bún bò thành 35000», «ẩn món cà phê», «thêm món bạc xỉu giá 45000» ạ."
        ),
    },
    PROPOSE_ORDER_TRANSITION: {
        "thieu_thong_tin": (
            "Dạ anh/chị cho em mã đơn và muốn chuyển sang trạng thái nào ạ "
            "(vd: «đơn dq_a1b2 chuyển sang đang pha» hoặc «hủy đơn dq_a1b2» vì khách đổi ý) ạ?"
        ),
    },
    PROPOSE_PIN: {
        "thieu_thong_tin": "Dạ anh/chị muốn ghim ca nào cho nhân viên nào ạ? (vd: «ghim ca w1_c01 cho Minh»)",
    },
    PROPOSE_TKB_CONFIRM: {
        "thieu_khoang_ban": (
            "Dạ anh/chị cho em khoảng bận cụ thể ạ? "
            "Vd: «T2 07:00-12:00, T4 18:00-22:00» hoặc gửi ảnh thời khóa biểu ạ."
        ),
    },
    PROPOSE_SWAP_CONSENT: {
        "thieu_swap_id": "Dạ anh/chị cho em mã yêu cầu đổi ca cần đồng ý (vd: «sw_a1b2c3») ạ?",
    },
    PROPOSE_CONSUMPTION_RECORD: {
        "thieu_so_luong": (
            "Dạ anh/chị ghi giúp em số lượng và tên hàng ạ? "
            "Vd: «3 khay sữa tươi», «còn 2 hộp bánh mì» ạ."
        ),
    },
}


def copilot_dang_hoi_ly_do(reply_text: str) -> bool:
    """`reply_text` của copilot có phải câu hỏi xin lý do nghỉ không?

    Cổng `cho_phep_noi_ly_do` cần biết chính xác lượt trước copilot có đang
    hỏi lý do không — nếu bật hời, mọi câu ngắn sau một lượt xin nghỉ đều bị
    bắt thành lý do ("hieu roi", "ok"…) và copilot tự bịa đơn nghỉ.
    """
    t = " ".join(str(reply_text or "").lower().split())
    return bool(t) and t == _chuan_hoa_cau_hoi(CAU_HOI_TIME_OFF_LY_DO)


def _chuan_hoa_cau_hoi(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _parse_intent_llm(text: str) -> tuple[str, float] | None:
    """Tầng-2: nhờ LLM đoán intent khi tầng từ khóa không khớp. Trả None nếu không dùng được.

    Fail-closed ở mọi nhánh: không có key, không phải live, provider lỗi, timeout,
    JSON hỏng, hoặc LLM trả intent ngoài whitelist → None → rơi về OUT_OF_SCOPE
    đúng như trước khi có tầng này. Không bao giờ để LLM tự thêm intent mới.

    An toàn KHÔNG phụ thuộc ở đây: RBAC (`copilot_agent.copilot_role_can_use_intent`),
    chặn prompt-injection, ngưỡng confidence cuối hàm, và `requires_confirmation`
    của từng tool đều chạy SAU parse. LLM đoán đúng intent vẫn bị chặn nếu vượm
    quyền, và intent ghi vẫn ra ActionProposal chờ người duyệt.
    """
    import os

    if os.environ.get("CA_AGENT_MODE", "replay").strip().lower() != "live":
        return None
    try:
        from ca_agents.llm import complete, parse_json_object, provider_status

        if not any(provider_status().values()):
            return None
        # Whitelist chính là _INTENT_KEYWORDS — LLM chỉ được chọn trong đó, không
        # được chọn thêm intent chưa khai báo từ khóa (giữ đúng bất biến tier-1).
        hop_le = sorted({name for name, _, _ in _INTENT_KEYWORDS})
        res = complete(
            system=(
                "Phân loại câu hỏi nhân viên quán cà phê vào ĐÚNG MỘT intent trong danh sách.\n"
                f"Danh sách hợp lệ: {hop_le}\n"
                "Trả JSON {\"intent\": <một tên trong danh sách>, \"confidence\": <số 0..1>}.\n"
                "Nếu câu không thuộc nghiệp vụ quán, hoặc không chắc, trả intent='OUT_OF_SCOPE'.\n"
                "Không suy diễn thông tin không có trong câu."
            ),
            user=text,
            task="text:ag_copilot_intent",
            json_mode=True,
            timeout_s=_LLM_TIER2_TIMEOUT_S,
        )
        if not res.ok:
            return None
        parsed = parse_json_object(res.text)
        if not isinstance(parsed, dict):
            return None
        intent = str(parsed.get("intent") or "").strip()
        conf = parsed.get("confidence")
        if intent not in hop_le or not isinstance(conf, (int, float)):
            return None
        # confidence thấp vẫn trả về: hàm gọi sẽ tự rơi xuống nhánh hỏi lại
        # (0.5 <= conf < 0.75) thay vì đoán bừa.
        return intent, max(0.0, min(float(conf), 1.0))
    except Exception:  # noqa: BLE001 — tier-2 hỏng không được làm sập tier-1
        return None


def _cau_hoi_lam_ro(intent: str, params: dict[str, Any]) -> tuple[str, str] | None:
    """`(loại_thiếu, câu_hỏi)` cho intent khi `params` còn thiếu thông tin bắt buộc."""
    if intent == PROPOSE_TIME_OFF:
        thieu_ngay = bool(params.get("thieu_thu"))
        thieu_ly_do = bool(params.get("thieu_ly_do"))
        if thieu_ngay and thieu_ly_do:
            return "thieu_ly_do", CAU_HOI_TIME_OFF_CA_NHAY
        if thieu_ngay:
            return "thieu_thu", CAU_HOI_TIME_OFF_NGAY
        if thieu_ly_do:
            return "thieu_ly_do", CAU_HOI_TIME_OFF_LY_DO
        return None
    for flag, question in _CAU_HOI_LAM_RO.get(intent, {}).items():
        if params.get(flag):
            return flag, question
    return None


# Viết tắt chat/teencode phổ biến → dạng đầy đủ để khớp bảng từ khoá.
# Chỉ thay thế theo ranh giới từ (\b) để không phá các từ chứa chuỗi con:
# "t" phải khớp riêng, không được biến "tôi" hay "tháng" thành "toii"/"tháng".
_VIET_TAT: dict[str, str] = {
    "hnay": "hôm nay",
    "h.nay": "hôm nay",
    "hnya": "hôm nay",
    "hum nay": "hôm nay",
    "hôm qua": "hôm qua",
    "mai": "mai",
    "ngmai": "ngày mai",
    "ngay mai": "ngày mai",
    "t2": "thứ hai",
    "t3": "thứ ba",
    "t4": "thứ tư",
    "t5": "thứ năm",
    "t6": "thứ sáu",
    "t7": "thứ bảy",
    "cn": "chủ nhật",
    "tuan": "tuần",
    "thang": "tháng",
}

# "t" / "k" / "ko" / "hok" chỉ thay khi đứng riêng như một từ.
_VIET_TAT_DON: dict[str, str] = {
    "t": "tôi",
    "k": "không",
    "ko": "không",
    "hok": "không",
    "mn": "mọi người",
    "nv": "nhân viên",
    "dc": "được",
    "đc": "được",
    "vs": "với",
    "ck": "chị",
    "a": "anh",
    "e": "em",
}


def _chuan_hoa_viet_tat(text: str) -> str:
    """Chuẩn hoá viết tắt để câu chat/nói lệch từ vẫn khớp được.

    Chỉ áp dụng khi từ xuất hiện nguyên vẹn (ranh giới từ), nên "t" trong "tôi"
    hay "tháng" không bị thay. Trả nguyên văn nếu không có gì để đổi.

    Giữ nguyên văn bản KHÔNG DẤU: bảng từ khoá có cả bản không dấu, và nếu ta
    "dịch" `hnay` → `hôm nay` (có dấu) thì bản không dấu `hnay` sẽ hết khớp.
    Chỉ chuẩn hoá khi câu gốc có dấu tiếng Việt.
    """
    if not text:
        return text
    if not _co_dau_tieng_viet(text):
        return text
    ket_qua = text
    for tat, day_du in _VIET_TAT.items():
        if tat in ket_qua:
            ket_qua = re.sub(rf"(?<!\w){re.escape(tat)}(?!\w)", day_du, ket_qua)
    for tat, day_du in _VIET_TAT_DON.items():
        if f" {tat} " in f" {ket_qua} ":
            ket_qua = re.sub(rf"(?<!\w){re.escape(tat)}(?!\w)", day_du, ket_qua)
    return ket_qua


def _co_dau_tieng_viet(text: str) -> bool:
    """True nếu `text` còn ký tự có dấu tiếng Việt."""
    return any(ch in "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ" for ch in text)


# Gộp lý do giữa hai lượt khi NV trả lời câu hỏi làm rõ.
def _trich_ly_do_time_off(text: str, recent_text: str) -> str:
    """Lý do nghỉ của lượt này, có tính tới lượt trước khi NV chỉ trả lời.

    `recent_text` rỗng = không được phép mượn lượt trước. Nối hai lượt bằng
    DẤU PHẨY để `trich_ly_do` lấy đúng đoạn sau dấu phẩy làm lý do (đoạn trước
    là lệnh xin nghỉ + ngày đã nói ở lượt trước).
    """
    ly_do = trich_ly_do(text)
    if ly_do or not recent_text.strip():
        return ly_do
    return trich_ly_do(f"{recent_text}, {text}")


def parse_intent(message: str, context: dict[str, Any] | None = None) -> IntentParseResult:
    """Parse intent from user message with confidence rules and injection checks."""
    text = (message or "").strip()
    if not text:
        return IntentParseResult(
            intent=OUT_OF_SCOPE,
            confidence=0.0,
            params={},
            clarification_needed=False,
            security_flag="empty_message",
        )

    # 1. Security Check: Prompt Injection / Bypass Approval
    if _BYPASS_REGEX.search(text):
        return IntentParseResult(
            intent=OUT_OF_SCOPE,
            confidence=0.99,
            params={},
            clarification_needed=False,
            security_flag="bypass_approval_rejected",
        )

    context = context or {}
    recent_messages = [
        str(item).strip() for item in context.get("recent_messages", [])[-3:]
        if str(item).strip()
    ]
    recent_text = " ".join(recent_messages).lower()

    # 2. Check for vague / ambiguous input unless recent context supplies intent.
    lower = text.lower()
    # Chuẩn hoá viết tắt chat/teencode TRƯỚC khi khớp từ khoá. Người dùng gõ
    # "lịch hnay của t" hoặc nói "hnay t có ca k" — không chuẩn hoá thì trượt
    # hết vì bảng từ khoá chỉ có dạng đầy đủ.
    lower = _chuan_hoa_viet_tat(lower)
    if lower in ("xếp lịch", "xep lich", "xếp lịch đi", "lên lịch đi") and not any(
        keyword in recent_text for _, keywords, _ in _INTENT_KEYWORDS for keyword in keywords
    ):
        return IntentParseResult(
            intent=SCHEDULE_SOLVE,
            confidence=0.60,
            params={},
            clarification_needed=True,
            clarification_question="Dạ anh/chị muốn em xếp lịch cho tuần này hay tuần sau ạ?",
        )

    # 3. Match against Whitelisted Intents
    matched_intent = OUT_OF_SCOPE
    matched_conf = 0.3
    params: dict[str, Any] = {}

    for intent_name, keywords, base_conf in _INTENT_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                matched_intent = intent_name
                matched_conf = base_conf
                break
        if matched_intent != OUT_OF_SCOPE:
            break

    # Post-match override: GET_SCHEDULE có thể match trước do substring ("chưa dc xếp lịch"
    # chứa "xếp lịch"), nhưng nếu câu có động từ hành động rõ ràng và KHÔNG có từ phủ định
    # thì phải override thành SCHEDULE_SOLVE.
    #
    # GET_MY_SHIFTS cũng phải bị soát: nhóm từ khóa văn nói ("lịch hôm nay của tôi")
    # khớp cả câu mang ý ĐỔI/HỦY ca ("hủy ca hôm nay của tôi"). Trả về GET_MY_SHIFTS
    # cho một yêu cầu ghi là sai — người dùng xin hủy ca mà nhận bảng lịch.
    if matched_intent in (GET_SCHEDULE, GET_MY_SHIFTS):
        original_intent = matched_intent
        action_verbs = ["xếp lịch", "xep lich", "lên lịch", "len lich", "tạo lịch", "tao lich",
                       "chia ca", "phân công ca", "phan cong ca", "lập lịch", "lap lich"]
        # "hủy/bỏ/xóa ca" không có intent ghi tương ứng trong CopilotIntent, và baseline
        # để OUT_OF_SCOPE. Ép về GET_MY_SHIFTS sẽ biến yêu cầu hủy ca thành lượt tra cứu.
        destructive_words = ["hủy", "huy", "bỏ ca", "bo ca", "xóa ca", "xoa ca", "xóa lịch", "xoa lich"]
        # "đổi ca" thuộc luồng trao đổi ca riêng (GET_SHIFT_SWAPS/PROPOSE_SWAP_CONSENT).
        # Câu "đổi ca hôm nay của tôi" khớp nhóm từ khóa văn nói mới nên sẽ bị nhận
        # nhầm thành tra cứu ca; baseline để OUT_OF_SCOPE và giữ nguyên như vậy.
        swap_words = ["đổi ca", "doi ca", "hoán ca", "hoan ca", "đổi lịch", "doi lich"]
        # "không/khong" chỉ là PHỦ ĐỊNH khi đi kèm "có/chưa" ở thế khẳng định phía
        # sau ("không có ca", "chưa có ca"). Còn "hôm nay tôi có ca không" là CÂU HỎI —
        # chữ "không" nằm cuối câu, không phải phủ định. Dùng regex thay vì `in`.
        #
        # LƯU Ý: phải có cả dạng ĐÃ CHUẨN HOÁ ("chưa được") lẫn dạng gốc ("chua dc"),
        # vì `_chuan_hoa_viet_tat` đổi `dc` → `được` trước khi tới đây.
        negation_words = [
            "ai chưa", "ai chua",
            "chưa dc", "chua dc",
            "chưa được", "chua duoc",
            "chưa đc", "chua đc",
        ]
        negation_regex = re.compile(
            r"(?:không|khong|chưa|chua)\s+(?:có|co)\s*(?:ca|ca làm|lich|lịch)?"
            r"|(?:không|khong)\s+(?:được|duoc|có|co)"
        )
        has_action = any(verb in lower for verb in action_verbs)
        has_destructive = any(word in lower for word in destructive_words)
        has_swap = any(word in lower for word in swap_words)
        has_negation = (
            any(neg in lower for neg in negation_words)
            or negation_regex.search(lower) is not None
        )
        if has_action and not has_negation:
            matched_intent = SCHEDULE_SOLVE
            matched_conf = 0.92
        elif has_destructive or has_swap:
            # Giữ fail-closed: không map bừa sang intent đọc.
            matched_intent = OUT_OF_SCOPE
            matched_conf = 0.85
        elif has_negation and original_intent == GET_MY_SHIFTS:
            # "lịch hôm nay của tôi không có ca" là câu hỏi về trạng thái chưa xếp ca,
            # không phải tra ca cá nhân đã có → fail-closed.
            #
            # CHỈ áp cho GET_MY_SHIFTS. Câu "…nhân viên nào chưa dc xếp lịch" khớp
            # GET_SCHEDULE từ trước và phải GIỮ NGUYÊN — đó là tra cứu lịch toàn quán,
            # không được hạ xuống OUT_OF_SCOPE (đã gây hồi quy ở test_pr13).
            matched_intent = OUT_OF_SCOPE
            matched_conf = 0.85

    # Nếu câu hỏi mang tính chất xin lời khuyên / tư vấn / hỏi ý kiến mở:
    # KHÔNG ép vào các intent mutating (sửa DB/thêm món/xếp lịch) mà để LLM trò chuyện & tư vấn.
    is_advisory = any(
        w in lower for w in [
            "nghĩ xem", "nghi xem", "gợi ý", "goi y", "tư vấn", "tu van",
            "có nên", "co nen", "làm sao để", "lam sao de", "làm thế nào để", "lam the nao de",
            "kinh nghiệm", "kinh nghiem", "ý kiến", "y kien", "đánh giá", "danh gia"
        ]
    )
    if is_advisory and matched_intent in (PROPOSE_MENU_UPDATE, SCHEDULE_SOLVE, PROPOSE_ORDER_TRANSITION):
        matched_intent = OUT_OF_SCOPE
        matched_conf = 0.85

    # Fix W6: Ranh giới QUERY_MENU (chứa "giá món") và RUN_CATCHMENT_SURVEY
    if matched_intent == QUERY_MENU:
        if any(w in lower for w in ["quanh", "bán kính", "ban kinh", "khảo sát", "khao sat", "đối thủ", "doi thu", "thị trường"]):
            matched_intent = RUN_CATCHMENT_SURVEY
            matched_conf = 0.9

    # GET_WEATHER: chỉ phục vụ thời tiết tại quán; câu hỏi thời tiết địa phương ngoài quán -> OUT_OF_SCOPE
    if matched_intent == GET_WEATHER:
        other_locations = [
            "ở đà lạt", "o da lat", "ở hà nội", "o ha noi", "ở đà nẵng", "o da nang",
            "ở huế", "o hue", "ở nha trang", "o nha trang", "ở cần thơ", "o can tho",
            "ở sapa", "o sapa", "ở hải phòng", "o hai phong", "ở vũng tàu", "o vung tau",
        ]
        if any(loc in lower for loc in other_locations):
            matched_intent = OUT_OF_SCOPE
            matched_conf = 0.5

    # Regex linh hoạt cho lệnh đăng/viết bài lên Fanpage/Facebook
    if matched_intent == OUT_OF_SCOPE:
        if re.search(r"(?:đăng|dang|viết|viet|soạn|soan|post).*(?:bài|bai).*(?:fb|facebook|page|fanpage)", lower) or \
           re.search(r"(?:đăng|dang|post).*(?:lên|len).*(?:fb|facebook|page|fanpage)", lower):
            matched_intent = PROPOSE_PAGE_DRAFT
            matched_conf = 0.92
        # Nhận diện linh hoạt cho xếp lịch ca — giới hạn .{0,30}? để tránh match xuyên câu;
        # loại trừ "lịch sử" (history) và các từ phủ định.
        elif re.search(r"(?:xếp|lên|tạo|chia|phân công|lập)\s*(?:giúp|hộ|dùm|giùm|cho)?.{0,30}?(?:lịch(?! sử)|ca\b)", lower) and \
             not any(neg in lower for neg in ["không", "khong", "hủy", "huy", "đổi ca", "doi ca", "chưa", "chua", "ai chưa", "ai chua", "lịch sử", "lich su"]):
            matched_intent = SCHEDULE_SOLVE
            matched_conf = 0.90
        # Nhận diện linh hoạt cho tra cứu ai chưa có ca / chưa xếp lịch / chưa duyệt
        elif any(w in lower for w in ["chưa", "chua"]) and any(w in lower for w in ["lịch", "lich", "ca", "xếp", "xep", "duyệt", "duyet"]):
            matched_intent = GET_SCHEDULE
            matched_conf = 0.90
        # Nhận diện linh hoạt cho tra cứu đổi ca
        elif re.search(r"(?:ai|có ai|danh sách|kèo|chợ|xem).*(?:đổi ca|nhận ca)", lower):
            matched_intent = GET_SHIFT_SWAPS
            matched_conf = 0.90
        # Nhận diện linh hoạt cho quy trình / cẩm nang
        elif re.search(r"(?:cách|hướng dẫn|công thức|quy trình).*(?:pha|nấu|làm|mở quán|đóng quán|vệ sinh)", lower):
            matched_intent = QUERY_SOP
            matched_conf = 0.90
        # Nhận diện linh hoạt cho bản tin hôm nay (phải liên quan rõ ràng tới quán/ca, không bắt thời tiết hay hao hụt)
        elif re.search(r"(?:tình hình quán|quán hôm nay thế nào|tổng kết quán)", lower):
            matched_intent = GENERATE_DAILY_BRIEF
            matched_conf = 0.90

    # ── Tầng-2: SAU CÙNG mới gọi LLM ──────────────────────────────────────
    # Đặt sau tầng từ khóa VÀ sau toàn bộ regex cứu vãn ở trên, để LLM chỉ xử lý
    # phần đuôi thật sự không xác định được — không bao giờ cạnh tranh với một
    # đường tất định đã chạy được. Bắt chước y hệt mẫu `ag_msg.extract` (AGENTS.md §6).
    if matched_intent == OUT_OF_SCOPE:
        from_tier2 = _parse_intent_llm(text)
        if from_tier2 is not None:
            matched_intent, matched_conf = from_tier2
            params["rang_buoc"] = {"nguon": "llm", "can_xac_minh": True}

    # Multi-turn context inference:
    # CHỈ áp dụng khi câu mới mang tham số bổ sung cụ thể cho intent trước (SCHEDULE_SOLVE, SEND_MAIL).
    # KHÔNG suy diễn khi câu mới là chào hỏi, cảm ơn, đóng hội thoại, thắc mắc chung ("sao vậy", "?", "alo", v.v.).
    inferred_from_context = False
    is_conversational_or_stop = any(w in lower for w in _CONVERSATIONAL_STOP_WORDS)

    if matched_intent == OUT_OF_SCOPE and bool(recent_messages) and not is_conversational_or_stop:
        # Kiểm tra xem câu hiện tại có chứa tham số bổ sung hay lệnh tiếp tục rõ ràng không
        has_schedule_signal = any(
            w in lower for w in [
                "tuần", "tuan", "ca ", "ca_", "ưu tiên", "uu tien",
                "xếp đi", "xep di", "chạy đi", "chay di", "lên lịch đi", "len lich di",
                "làm đi", "lam di", "đồng ý", "dong y", "xác nhận", "xac nhan"
            ]
        )
        has_mail_signal = any(
            w in lower for w in [
                "gửi", "gui", "cho ", "@", "mail", "email", "nhắc", "nhac",
                "nội dung", "noi dung", "tiêu đề", "tieu de"
            ]
        )

        if has_schedule_signal and any(kw in recent_text for iname, keywords, _ in _INTENT_KEYWORDS if iname == SCHEDULE_SOLVE for kw in keywords):
            matched_intent = SCHEDULE_SOLVE
            matched_conf = 0.88
            inferred_from_context = True
        elif has_mail_signal and any(kw in recent_text for iname, keywords, _ in _INTENT_KEYWORDS if iname == SEND_MAIL for kw in keywords):
            matched_intent = SEND_MAIL
            matched_conf = 0.88
            inferred_from_context = True
        elif (
            context.get("cho_phep_noi_ly_do")
            and any(
                kw in recent_text
                for iname, keywords, _ in _INTENT_KEYWORDS
                if iname == PROPOSE_TIME_OFF
                for kw in keywords
            )
            and "?" not in lower
        ):
            # NV đang TRẢ LỜI câu hỏi "lý do nghỉ là gì ạ?" của lượt trước.
            # Cổng `cho_phep_noi_ly_do` do API/đồng UI bật khi lượt trước copilot
            # thực sự hỏi lý do — không bật thì câu này rơi vào OUT_OF_SCOPE và
            # lý do NV vừa cung cấp bị bỏ rơi.
            matched_intent = PROPOSE_TIME_OFF
            matched_conf = 0.88
            inferred_from_context = True

    # Nếu có đính kèm ảnh và người dùng hỏi về lịch/TKB hoặc chỉ gửi ảnh
    attachments = list(context.get("attachments") or [])
    has_image_att = any(
        "image" in str(a.get("mime_type", "")) or str(a.get("url", "")).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
        for a in attachments
    )
    if matched_intent == OUT_OF_SCOPE and has_image_att:
        has_tkb_cue = any(k in lower for k in ["tkb", "lịch", "lich", "thời khóa biểu", "thoi khoa bieu", "lịch học", "lich hoc", "bận", "ban", "rảnh", "ranh", "đính kèm", "dinh kem"])
        if has_tkb_cue or lower in ("đã gửi tệp đính kèm", "da gui tep dinh kem", "gửi ảnh", "gui anh", ""):
            matched_intent = PROPOSE_TKB_CONFIRM
            matched_conf = 0.92

    # Extract common parameters
    if matched_intent == SCHEDULE_SOLVE:
        # Week detection thống nhất với GET_SCHEDULE (W41 / tuần sau / hôm nay).
        active_date = _active_date(context)
        combined_lower = f"{recent_text} {lower}"
        params.update(
            parse_tuan_tu_van_ban(
                combined_lower,
                active_date=active_date,
                mac_dinh_tuan_sau=True,
                uu_tien=lower,
            )
        )
        # Preference detection
        lan_match = re.search(r"ưu\s*tiên\s*(\w+)\s*ca\s*(\w+)", lower)
        if lan_match:
            params["uu_tien_nhan_su"] = {lan_match.group(1).title(): f"ca_{lan_match.group(2)}"}

        # Meeting context detection
        if any(w in combined_lower for w in ["cuộc họp", "cuoc hop", "họp", "hop", "biên bản", "bien ban", "giao ca"]):
            params["nguon_cuoc_hop"] = True

    elif matched_intent == GET_SCHEDULE:
        active_date = _active_date(context)
        combined_lower = f"{recent_text} {lower}"
        params.update(
            parse_tuan_tu_van_ban(
                combined_lower,
                active_date=active_date,
                mac_dinh_tuan_sau=False,
                uu_tien=lower,
            )
        )

    elif matched_intent == QUERY_SOP:
        params["cau_hoi"] = text

    elif matched_intent == QUERY_QUANVERSE:
        params["cau_hoi"] = text

    elif matched_intent == GET_WEATHER:
        params["cau_hoi"] = text

    elif matched_intent == GET_TODAY_OPERATIONS:
        params["ngay"] = _active_date(context).isoformat()

    elif matched_intent == GET_FAIRNESS_SUMMARY:
        params["cau_hoi"] = text

    elif matched_intent == GET_MY_CHECKLIST:
        params["cau_hoi"] = text

    elif matched_intent == SEARCH_TRENDS:
        params["cau_hoi"] = text

    elif matched_intent in (GET_RESERVATIONS, GET_OPEN_SHIFTS, GET_MEETINGS, GET_PREDICTIVE_INSIGHTS):
        params["cau_hoi"] = text

    elif matched_intent == PROPOSE_TIME_OFF:
        # Trích thứ + khung giờ + lý do từ chính câu nói ("tôi bận thứ 5, có thi").
        active_date = _active_date(context)
        # Lượt này đã nêu ngày/ca thì lấy ngay lượt này — KHÔNG đụng lịch sử, để
        # "xin nghỉ thứ 7" không bị lượt trước nhắc "thứ 5" kéo theo. Chỉ khi
        # lượt này KHÔNG có gì (NV đang trả lời câu hỏi "lý do là gì?") mới
        # mượn ngày/ca từ lượt trước qua `recent_text`.
        if _parse_thu(lower) or _parse_ca_range(lower):
            nguon = lower
        else:
            nguon = f"{recent_text} {lower}"
        thu = _parse_thu(nguon)
        # "xin nghỉ buổi chiều nay" không có "thứ X" → suy thứ từ ngày quán.
        if not thu:
            thu = _parse_thu_tuong_doi(nguon, active_date)
        if thu:
            params["thu"] = thu
        # Nêu ca/khung giờ → chỉ bận khung đó, KHÔNG nghỉ cả ngày.
        ca_range = _parse_ca_range(nguon)
        if ca_range:
            params["start"], params["end"] = ca_range
        # Gắn tuan_id — trước đây thiếu nên ràng buộc nghỉ rơi tuần sai.
        tuan_params = parse_tuan_tu_van_ban(
            f"{recent_text} {lower}",
            active_date=active_date,
            mac_dinh_tuan_sau=False,
            uu_tien=lower,
        )
        params["tuan_id"] = tuan_params.get("tuan")
        # Lý do: lấy đúng phần NV nói, KHÔNG tự điền "bận". Trước đây thiếu lý
        # do thì điền "bận" → đơn tới tay quản lý mang lý do vô nghĩa, và cụm
        # ca/ngày ("buổi chiều thứ 5") lọt vào lý do làm lý do thật bị chôn.
        # Chỉ gộp lượt trước khi đang trả lời câu hỏi làm rõ — nếu gộp vô điều
        # kiện thì "xin nghỉ thứ 7" sẽ mượn nhầm lý do của "thứ 5" ở lượt trước.
        params["ly_do"] = _trich_ly_do_time_off(
            text, recent_text if inferred_from_context else ""
        )
        params["thieu_ly_do"] = not params["ly_do"]
        params["thieu_thu"] = not thu

    elif matched_intent == GENERATE_DAILY_BRIEF:
        params["ngay"] = _active_date(context).isoformat()
    elif matched_intent == ANALYZE_WASTE:
        params["khoang_ngay"] = "hom_nay"

    elif matched_intent == INVENTORY_RESTOCK_CHECK:
        params["nguong_canh_bao"] = 10.0

    elif matched_intent == SEND_MAIL:
        param_text = " ".join((*recent_messages, text)) if inferred_from_context else text
        current_lower = text.lower()
        current_has_recipient = bool(
            re.search(r"(?:@|\bnv_\d+\b|\b(?:minh|lan|hùng|hung)\b)", current_lower)
        )
        recipient_text = text if current_has_recipient else param_text
        recipient_lower = recipient_text.lower()
        # Direct email extraction
        email_pattern = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
        found_emails = email_pattern.findall(recipient_text)

        # Trích xuất tên nhân viên thường gặp
        staff_map = {
            "minh": "nv_03",
            "lan": "nv_01",
            "hùng": "nv_02",
            "hung": "nv_02",
        }
        to_nv_ids: list[str] = []
        recip_names: list[str] = []
        for name, nv_id in staff_map.items():
            if re.search(r"\b" + re.escape(name) + r"\b", recipient_lower):
                if nv_id not in to_nv_ids:
                    to_nv_ids.append(nv_id)
                    recip_names.append(name.capitalize())

        # Trích xuất mã nv_XX nếu có
        for m in re.findall(r"\bnv_\d+\b", recipient_lower):
            if m not in to_nv_ids:
                to_nv_ids.append(m)
                recip_names.append(m.upper())

        params["raw_request"] = param_text
        params["to_nv_ids"] = to_nv_ids
        params["direct_emails"] = found_emails
        params["recipient_names"] = recip_names
        params["subject"] = param_text if len(param_text) <= 120 else param_text[:120]
        params["body"] = param_text

    elif matched_intent == PROPOSE_HANGING_TASK:
        # Trích nội dung việc treo: phần sau "treo việc"/"tạo việc treo".
        m = re.search(
            r"(?:treo\s*việc|treo\s*viec|tạo\s*việc\s*treo|tao\s*viec\s*treo|ghi\s*việc\s*treo|ghi\s*viec\s*treo)\s*(?:là|la|:|—|-)?\s*(.+)",
            text,
            re.IGNORECASE,
        )
        noi_dung = (m.group(1).strip() if m else "").strip()
        params["noi_dung"] = noi_dung[:200]
        params["thieu_noi_dung"] = not noi_dung

    elif matched_intent == PROPOSE_TASK_COMPLETE:
        # Trích treo_id: dạng treo_<alnum> (hex từ route web hoặc test ID).
        m = re.search(r"\b(treo_[a-z0-9]{4,20})\b", text, re.IGNORECASE)
        params["treo_id"] = m.group(1).lower() if m else ""
        params["thieu_treo_id"] = not params["treo_id"]

    elif matched_intent == PROPOSE_CONSUMPTION_RECORD:
        # Trích: "<số lượng> <đơn vị?> <hàng>" hoặc "hàng <hàng> còn <số>".
        so_luong: float | None = None
        don_vi = "khay"
        hang = ""
        m = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(hộp|hop|khay|gói|goi|chai|lon|túi|tui|kg|gram|g)?\s*(?:của\s*)?(.+)",
            text,
            re.IGNORECASE,
        )
        if m:
            so_luong = float(m.group(1).replace(",", "."))
            if m.group(2):
                don_vi = m.group(2).lower()
            hang = m.group(3).strip()[:60]
        params["so_luong"] = so_luong
        params["don_vi"] = don_vi
        params["hang"] = hang
        params["thieu_so_lieu"] = so_luong is None or not hang

    elif matched_intent == PROPOSE_MENU_UPDATE:
        # Trích: "sửa giá <món> thành <số>" | "ẩn món <món>" | "thêm món <món> giá <số>".
        gia: int | None = None
        an: bool | None = None
        ten_mon = ""
        m_gia = re.search(
            r"(?:sửa|sua|đổi|doi|cập\s*nhật|cap\s*nhat)\s*giá\s*(?:món\s*)?(.+?)\s*(?:thành|thanh|lên|len|:)\s*(\d+(?:[.,]\d+)?)",
            text,
            re.IGNORECASE,
        )
        m_an = re.search(r"(?:ẩn|an|bỏ|bo)\s*món\s*(.+)", text, re.IGNORECASE)
        m_them = re.search(
            r"(?:thêm|them)\s*món\s*(?:mới\s*|moi\s*)?(.+?)(?:\s*giá\s*|\s*gia\s*)(\d+(?:[.,]\d+)?)",
            text,
            re.IGNORECASE,
        )
        if m_gia:
            ten_mon = m_gia.group(1).strip()[:60]
            gia = int(float(m_gia.group(2).replace(",", ".")))
            an = False
        elif m_an:
            ten_mon = m_an.group(1).strip()[:60]
            an = True
        elif m_them:
            ten_mon = m_them.group(1).strip()[:60]
            gia = int(float(m_them.group(2).replace(",", ".")))
            an = False
        params["ten_mon"] = ten_mon
        params["gia"] = gia
        params["an"] = an
        params["thieu_thong_tin"] = not ten_mon or (gia is None and an is None)

    elif matched_intent == PROPOSE_ORDER_TRANSITION:
        # Trích don_id (dq_xxx) và trạng thái đích từ động từ.
        m_id = re.search(r"\b(dq_[a-z0-9]{4,20})\b", text, re.IGNORECASE)
        lower = text.lower()
        trang_thai = ""
        if re.search(r"(hủy|huy)\s*đơn|đơn.*(hủy|huy)", lower):
            trang_thai = "huy"
        elif re.search(r"(xong|hoàn\s*thành|hoan\s*thanh)", lower):
            trang_thai = "xong"
        elif re.search(r"(đang\s*pha|dang\s*pha|bắt\s*đầu\s*pha|bat\s*dau\s*pha)", lower):
            trang_thai = "dang_pha"
        params["don_id"] = m_id.group(1).lower() if m_id else ""
        params["trang_thai"] = trang_thai
        params["ly_do_huy"] = ""
        params["thieu_thong_tin"] = not params["don_id"] or not trang_thai

    elif matched_intent == PROPOSE_PIN:
        # Trích ca_id (w1_c01...), nv_id (nv_XX hoặc tên nhân viên), pinned.
        m_ca = re.search(r"\b([a-z]\d+_[a-z]\d{1,3})\b", text, re.IGNORECASE)
        lower = text.lower()
        pinned = not bool(re.search(r"(bỏ\s*ghim|bo\s*ghim|un\s*pin|gỡ\s*ghim|go\s*ghim)", lower))
        m_nv = re.search(r"\b(nv_\d+)\b", text, re.IGNORECASE)
        nv_id = m_nv.group(1).lower() if m_nv else ""
        if not nv_id:
            staff_map = {"minh": "nv_03", "lan": "nv_01", "hùng": "nv_02", "hung": "nv_02"}
            for name, nv in staff_map.items():
                if re.search(r"\b" + re.escape(name) + r"\b", lower):
                    nv_id = nv
                    break
        params["ca_id"] = m_ca.group(1).lower() if m_ca else ""
        params["nv_id"] = nv_id
        params["pinned"] = pinned
        params["thieu_thong_tin"] = not params["ca_id"] or not nv_id

    elif matched_intent == PROPOSE_TKB_CONFIRM:
        # Trích khoảng bận: "T2 07:00-12:00, T4 18:00-22:00" (thứ T2..T8/CN).
        khoang_ban: list[tuple[str, str, str]] = []
        for m in re.finditer(
            r"\b(T[2-8]|CN)\s+(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})",
            text,
            re.IGNORECASE,
        ):
            thu = m.group(1).upper()
            khoang_ban.append((thu, m.group(2), m.group(3)))
        active_date = _active_date(context)
        combined_lower = f"{recent_text} {lower}"
        explicit_week = re.search(r"\b(\d{4})-w(\d{1,2})\b", combined_lower, re.IGNORECASE)
        short_week = re.search(r"\bw(\d{1,2})\b", combined_lower, re.IGNORECASE)
        if explicit_week:
            params["tuan_iso"] = (
                f"{int(explicit_week.group(1)):04d}-W{int(explicit_week.group(2)):02d}"
            )
        elif short_week:
            params["tuan_iso"] = f"{active_date.year}-W{int(short_week.group(1)):02d}"
        elif "tuần sau" in combined_lower or "tuan sau" in combined_lower:
            params["tuan_iso"] = _iso_week(_add_week(active_date, 1))
        else:
            params["tuan_iso"] = _iso_week(active_date)
        # nv_id: mặc định người nói (executor sẽ chốt ownership); cho phép
        # nv_XX hoặc tên nhân viên nếu quản lý xác nhận hộ.
        m_nv = re.search(r"\b(nv_\d+)\b", text, re.IGNORECASE)
        nv_id = m_nv.group(1).lower() if m_nv else ""
        if not nv_id:
            staff_map = {"minh": "nv_03", "lan": "nv_01", "hùng": "nv_02", "hung": "nv_02"}
            for name, nv in staff_map.items():
                if re.search(r"\b" + re.escape(name) + r"\b", lower):
                    nv_id = nv
                    break
        params["khoang_ban"] = khoang_ban
        params["nv_id"] = nv_id
        # Hỗ trợ ảnh đính kèm (upload_id hoặc image_path)
        first_img = next(
            (
                a for a in attachments
                if "image" in str(a.get("mime_type", ""))
                or str(a.get("url", "")).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
            ),
            None,
        )
        if first_img:
            params["upload_id"] = str(first_img.get("upload_id") or "")
            params["image_path"] = str(first_img.get("local_path") or first_img.get("url") or "")
            params["attachment_url"] = str(first_img.get("url") or "")
            params["attachment_filename"] = str(first_img.get("filename") or "")
        params["thieu_khoang_ban"] = not khoang_ban and not params.get("image_path") and not params.get("upload_id")

    elif matched_intent == PROPOSE_SWAP_CONSENT:
        # Trích swap_id (sw_xxx) — thiếu ID thì tool fail-closed.
        m = re.search(r"\b(sw_[a-z0-9]{4,24})\b", text, re.IGNORECASE)
        params["swap_id"] = m.group(1).lower() if m else ""
        params["thieu_swap_id"] = not params["swap_id"]

    elif matched_intent == PROPOSE_HANDOVER:
        # Toàn bộ text là nội dung bàn giao (SBAR) — tool yêu cầu không rỗng.
        params["text"] = text[:2000]
        params["thieu_noi_dung"] = not text.strip()

    elif matched_intent == PROPOSE_PAGE_DRAFT:
        # Trích chủ đề bài viết: loại bỏ các từ chỉ kênh mạng xã hội
        cleaned = re.sub(r"\b(lên|tren|vào|vao)?\s*(fb|facebook|page|fanpage)\b", "", text, flags=re.IGNORECASE)
        m = re.search(
            r"(?:đăng\s*bài|dang\s*bai|viết\s*bài|viet\s*bai|soạn\s*bài|soan\s*bai|post\s*bài|post\s*bai|tạo\s*bài|tao\s*bai)(?:\s*đăng|\s*viết)?\s*(?:về|ve|chủ\s*đề|chu\s*de|cho|:|-)?\s*(.+)",
            cleaned,
            re.IGNORECASE,
        )
        topic = (m.group(1).strip() if m else "").strip()
        if not topic:
            topic = text.strip()
        tone = "than thien"
        lower = text.lower()
        if any(w in lower for w in ["hài hước", "hai huoc", "gen z", "bắt trend", "bat trend"]):
            tone = "hai huoc"
        elif any(w in lower for w in ["nghệ thuật", "nghe thuat", "truyền cảm hứng", "truyen cam hung", "chill"]):
            tone = "truyen cam hung"
        elif any(w in lower for w in ["trang trọng", "trang trong", "thông báo", "thong bao"]):
            tone = "trang trong"
        params["topic"] = topic
        params["tone"] = tone

    elif matched_intent == RUN_CATCHMENT_SURVEY:
        survey_params, clarif_q = _extract_survey_params(text)
        if clarif_q is not None:
            return IntentParseResult(
                intent=RUN_CATCHMENT_SURVEY,
                confidence=0.70,
                params={},
                clarification_needed=True,
                clarification_question=clarif_q,
            )
        params.update(survey_params)

    elif matched_intent == GET_SURVEY_RESULT:
        # Nếu có nói rõ món/bán kính thì trích xuất kèm
        survey_params, _ = _extract_survey_params(text)
        if survey_params:
            params.update(survey_params)

    elif matched_intent == GET_SERPAPI_QUOTA:
        pass

    # 4. Thiếu tham số bắt buộc → hỏi lại đúng thứ đang thiếu.
    # Đặt TRƯỚC ngưỡng confidence: câu nhận diện intent chắc chắn (0.92) vẫn
    # phải hỏi khi thiếu lý do/ngày — đây là chỗ cũ để lọt "tự điền bận".
    cau_hoi = _cau_hoi_lam_ro(matched_intent, params)
    if cau_hoi is not None:
        loai, cau = cau_hoi
        return IntentParseResult(
            intent=matched_intent,
            confidence=matched_conf,
            params=params,
            clarification_needed=True,
            clarification_question=cau,
            clarification_kind=loai,
        )

    # 5. Confidence thresholds:
    # >= 0.75: regular
    # 0.5 <= conf < 0.75: clarification
    # < 0.5: OUT_OF_SCOPE
    if matched_conf >= 0.75:
        return IntentParseResult(
            intent=matched_intent,
            confidence=matched_conf,
            params=params,
            clarification_needed=False,
        )
    elif 0.5 <= matched_conf < 0.75:
        return IntentParseResult(
            intent=matched_intent,
            confidence=matched_conf,
            params=params,
            clarification_needed=True,
            clarification_question="Dạ anh/chị có thể nói rõ hơn thao tác cần hỗ trợ không ạ?",
        )
    else:
        return IntentParseResult(
            intent=OUT_OF_SCOPE,
            confidence=matched_conf,
            params={},
            clarification_needed=False,
        )
