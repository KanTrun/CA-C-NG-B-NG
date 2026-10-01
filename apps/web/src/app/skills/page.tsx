"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "../../lib/api";
import { viError } from "../../lib/present";
import { getToken, isChuQuan, isManager } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  Dialog,
  Empty,
  Loading,
  Notice,
  OpsCard,
  PageHeader,
  StatusChip,
  Summary,
  TechnicalDrawer,
  inputClassName,
  textareaClassName,
} from "../../ui/kit";

type SkillSummary = {
  skill_id: string;
  name: string;
  description?: string;
  path?: string;
  relative_path?: string;
  scripts: string[];
  references: string[];
  content_sha256?: string;
  sha256?: string;
};

type SkillDetail = {
  skill_id: string;
  name: string;
  content: string;
  scripts: string[];
  references: string[];
  content_sha256: string;
  prompt_context_sample: string;
};

type VerifyResponse = {
  skill_id: string;
  verified: boolean;
  status: string;
  script_results: Record<
    string,
    {
      passed: boolean;
      return_code?: number;
      output?: string;
      error?: string;
    }
  >;
};

type SkillMeta = {
  title: string;
  category: "pha-che" | "nhan-su" | "van-hanh" | "kho" | "thu-ngan" | "mxh" | "an-toan";
  categoryLabel: string;
  icon: string;
  triggers: string[];
  benefit: string;
  samplePrompt: string;
};

const SKILL_CAT_MAP: Record<
  string,
  { label: string; count?: number }
> = {
  all: { label: "Tất cả năng lực" },
  "nhan-su": { label: "Nhân sự & Lịch làm" },
  "van-hanh": { label: "Vận hành ca" },
  "pha-che": { label: "Pha chế & Nguyên liệu" },
  kho: { label: "Kho & Hàng hóa" },
  "thu-ngan": { label: "Thu ngân & Két tiền" },
  mxh: { label: "Mạng xã hội & Khách hàng" },
  "an-toan": { label: "An toàn hệ thống" },
};

const SKILL_METAS: Record<string, SkillMeta> = {
  "barista-waste-audit": {
    title: "Đối soát hao hụt pha chế",
    category: "pha-che",
    categoryLabel: "Pha chế & Nguyên liệu",
    icon: "☕",
    triggers: ["hao hụt", "lãng phí", "pha chế", "công thức", "định lượng"],
    benefit: "Tự động so sánh số ly bán trên POS với định mức nguyên liệu thực tế, cảnh báo ngay khi hao hụt vượt ngưỡng 5%.",
    samplePrompt: "Kiểm tra hao hụt sữa và cà phê ca sáng nay",
  },
  "customer-memory-voc": {
    title: "Ghi nhớ khách quen & Phản hồi",
    category: "mxh",
    categoryLabel: "Khách hàng & Dịch vụ",
    icon: "👥",
    triggers: ["khách quen", "khen chê", "đánh giá khách", "ít ngọt"],
    benefit: "Tự ghi nhớ khẩu vị riêng (ít đá, đổi sữa hạt) và phân tích cảm xúc từ phản hồi khách để nâng cao dịch vụ.",
    samplePrompt: "Khách quen anh Nam hay uống món gì và có lưu ý gì không?",
  },
  "daily-brief-generator": {
    title: "Tạo bản tin giao ban ca",
    category: "van-hanh",
    categoryLabel: "Vận hành ca",
    icon: "📋",
    triggers: ["bản tin", "giao ban", "mục tiêu ca"],
    benefit: "Tổng hợp nhanh nhân sự đi làm, mục tiêu doanh số và danh sách việc tồn từ ca trước chỉ trong 1 giây.",
    samplePrompt: "Tạo bản tin giao ban nhanh cho ca chiều nay",
  },
  "fbpage-concierge": {
    title: "Trực Fanpage & Hỗ trợ đặt bàn",
    category: "mxh",
    categoryLabel: "Mạng xã hội & Khách hàng",
    icon: "💬",
    triggers: ["fanpage", "inbox", "menu", "giá", "đặt bàn", "giờ mở cửa"],
    benefit: "Tự động tra cứu menu, giá bán và sơ đồ bàn trống để trả lời khách và giữ bàn qua tin nhắn Messenger.",
    samplePrompt: "Khách nhắn hỏi giá combo cà phê và đặt bàn 4 người tối nay",
  },
  "genz-texting-agent": {
    title: "Tư vấn tự nhiên & Gộp tin nhắn",
    category: "mxh",
    categoryLabel: "Mạng xã hội & Khách hàng",
    icon: "✨",
    triggers: ["gộp tin nhắn", "giọng gen z", "teencode", "debounce"],
    benefit: "Gộp các dòng chat liên tục của khách trước khi trả lời, tạo cảm giác trò chuyện tự nhiên và thân thiện.",
    samplePrompt: "Tư vấn cho bạn khách trẻ vừa nhắn 3 tin hỏi menu quán",
  },
  "handover-reconciliation": {
    title: "Đối soát tiền két & Bàn giao ca",
    category: "thu-ngan",
    categoryLabel: "Thu ngân & Két tiền",
    icon: "💵",
    triggers: ["bàn giao", "giao ca", "tiền két", "đối soát", "lệch tiền"],
    benefit: "Tự tính toán tiền mặt trong két so với doanh thu ca, phát hiện ngay nếu có chênh lệch và lập biên bản giao việc.",
    samplePrompt: "Đối soát tiền két và tạo phiếu giao ca cho ca sáng",
  },
  "inventory-restock-check": {
    title: "Cảnh báo đặt hàng & Tồn kho",
    category: "kho",
    categoryLabel: "Kho & Hàng hóa",
    icon: "📦",
    triggers: ["nhập hàng", "hết hàng", "tồn kho", "đặt hàng"],
    benefit: "Theo dõi lượng tồn kho nguyên liệu quan trọng và cảnh báo quản lý khi chạm điểm cần nhập thêm (ROP).",
    samplePrompt: "Kiểm tra xem nguyên liệu nào sắp hết cần đặt hàng gấp",
  },
  "mailwriter-notification": {
    title: "Soạn email gửi nhà cung cấp",
    category: "kho",
    categoryLabel: "Đối tác & Kho",
    icon: "✉️",
    triggers: ["soạn mail", "email", "thư", "nhà cung cấp"],
    benefit: "Tự điền thông tin đơn hàng thiếu hụt vào mẫu thư chuẩn gửi nhà cung cấp nguyên vật liệu.",
    samplePrompt: "Soạn email gửi nhà cung cấp hạt cà phê báo thiếu 10kg Robusta",
  },
  "meeting-memo-extractor": {
    title: "Trích xuất việc cần làm từ cuộc họp",
    category: "van-hanh",
    categoryLabel: "Vận hành ca",
    icon: "📝",
    triggers: ["biên bản", "họp ca", "cuộc họp", "việc cần làm"],
    benefit: "Chuyển biên bản họp hoặc ghi chú ngắn thành danh sách đầu việc có người phụ trách và hạn chót rõ ràng.",
    samplePrompt: "Trích xuất việc cần làm từ biên bản họp giao ban tuần này",
  },
  "rule-mining-lifecycle": {
    title: "Đề xuất quy tắc từ thói quen",
    category: "van-hanh",
    categoryLabel: "Tối ưu vận hành",
    icon: "⚙️",
    triggers: ["luật mới", "đề xuất luật", "lỗi lặp lại"],
    benefit: "Tự động phát hiện các chỉnh sửa lịch ca lặp lại nhiều lần của quản lý để gợi ý ban hành quy tắc mới.",
    samplePrompt: "Phân tích xem có thói quen đổi ca nào nên đưa thành quy tắc của quán không",
  },
  "smart-swap-recommender": {
    title: "Gợi ý người thế ca tối ưu",
    category: "nhan-su",
    categoryLabel: "Nhân sự & Lịch làm",
    icon: "🔄",
    triggers: ["đổi ca", "thế ca", "bù ca", "vắng mặt"],
    benefit: "Tìm nhân viên có cùng kỹ năng (Pha chế/Thu ngân) đang rảnh và chấm điểm người phù hợp nhất để bù ca.",
    samplePrompt: "Tìm người thế ca cho bạn Lan bị ốm ca tối thứ 6",
  },
  "solver-scheduling": {
    title: "Xếp lịch ca tự động (Bộ giải toán)",
    category: "nhan-su",
    categoryLabel: "Nhân sự & Lịch làm",
    icon: "📅",
    triggers: ["xếp ca", "lịch", "tkb", "phân công"],
    benefit: "Kích hoạt thuật toán CP-SAT xếp lịch cả tuần chỉ trong 3 giây, đảm bảo công bằng và đúng luật lao động.",
    samplePrompt: "Chạy xếp lịch tự động cho tuần sau",
  },
  "sop-execution": {
    title: "Giám sát thực thi quy trình ca",
    category: "van-hanh",
    categoryLabel: "Vận hành ca",
    icon: "✅",
    triggers: ["mở ca", "đóng ca", "vệ sinh", "cẩm nang", "checklist"],
    benefit: "Hướng dẫn nhân viên kiểm tra quầy kệ, máy móc và ghi nhận checklist hoàn thành trước khi mở/đóng ca.",
    samplePrompt: "Kiểm tra xem ca sáng đã hoàn thành checklist mở ca chưa",
  },
  "vf-gates-audit": {
    title: "Cổng kiểm duyệt an toàn hành động",
    category: "an-toan",
    categoryLabel: "An toàn hệ thống",
    icon: "🛡️",
    triggers: ["kiểm duyệt", "cổng", "thẩm định", "fail-closed"],
    benefit: "Tự động chặn đứng các đề xuất sai quy định hoặc vượt quyền trước khi áp dụng vào dữ liệu quán.",
    samplePrompt: "Thẩm định đề xuất đổi ca này có vi phạm quy định an toàn không",
  },
};

export default function SkillsPage() {
  const [token, setToken] = useState("");
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("all");

  // Live verification state per skill
  const [verifying, setVerifying] = useState<Record<string, boolean>>({});
  const [verifyResults, setVerifyResults] = useState<Record<string, VerifyResponse>>({});

  // Skill detail modal
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailData, setDetailData] = useState<SkillDetail | null>(null);

  // Distill SOP form state (collapsed by default in Technical Drawer)
  const [sopId, setSopId] = useState("");
  const [sopTitle, setSopTitle] = useState("");
  const [sopMarkdown, setSopMarkdown] = useState("");
  const [distilling, setDistilling] = useState(false);

  useEffect(() => {
    setToken(getToken());
    if (!getToken()) setLoading(false);
  }, []);

  const loadSkills = useCallback(async () => {
    if (!getToken()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<SkillSummary[]>("/api/v1/skills");
      setSkills(data);
    } catch (err) {
      setError(viError(err, { doing: "tải danh mục năng lực trợ lý" }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) loadSkills();
  }, [token, loadSkills]);

  const handleVerify = async (skillId: string) => {
    setVerifying((prev) => ({ ...prev, [skillId]: true }));
    setError(null);
    try {
      const res = await apiSend<VerifyResponse>(`/api/v1/skills/${skillId}/verify`, {}, "POST");
      setVerifyResults((prev) => ({ ...prev, [skillId]: res }));
      const meta = SKILL_METAS[skillId];
      const displayName = meta ? meta.title : skillId;
      if (res.verified) {
        setNotice(`Đã kiểm tra năng lực "${displayName}": Logic tính toán hoạt động chính xác 100%.`);
      } else {
        setError(`Kiểm tra năng lực "${displayName}": Phát hiện lỗi trong kịch bản kiểm thử.`);
      }
    } catch (err) {
      setError(viError(err, { doing: `kiểm tra trực tiếp năng lực ${skillId}` }));
    } finally {
      setVerifying((prev) => ({ ...prev, [skillId]: false }));
    }
  };

  const handleViewDetail = async (skillId: string) => {
    setSelectedSkillId(skillId);
    setDetailLoading(true);
    try {
      const detail = await apiGet<SkillDetail>(`/api/v1/skills/${skillId}`);
      setDetailData(detail);
    } catch (err) {
      setError(viError(err, { doing: `đọc chi tiết năng lực ${skillId}` }));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDistillSop = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sopId.trim() || !sopTitle.trim() || !sopMarkdown.trim()) {
      setError("Vui lòng điền đầy đủ Mã định danh, Tiêu đề và Nội dung quy trình.");
      return;
    }
    setDistilling(true);
    setError(null);
    try {
      const res = await apiSend<{ success: boolean; message: string }>("/api/v1/skills/distill-sop", {
        sop_id: sopId.trim(),
        title: sopTitle.trim(),
        markdown_content: sopMarkdown.trim(),
      });
      setNotice(res.message);
      setSopId("");
      setSopTitle("");
      setSopMarkdown("");
      await loadSkills();
    } catch (err) {
      setError(viError(err, { doing: "tạo năng lực mới từ cẩm nang" }));
    } finally {
      setDistilling(false);
    }
  };

  const filteredSkills = useMemo(() => {
    let result = skills;

    // Filter by category
    if (activeCategory !== "all") {
      result = result.filter((s) => {
        const meta = SKILL_METAS[s.skill_id];
        return meta && meta.category === activeCategory;
      });
    }

    // Filter by search text
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((s) => {
        const meta = SKILL_METAS[s.skill_id];
        const titleMatch = meta?.title.toLowerCase().includes(q);
        const triggerMatch = meta?.triggers.some((t) => t.toLowerCase().includes(q));
        const descMatch = (s.description || meta?.benefit || "").toLowerCase().includes(q);
        const idMatch = s.skill_id.toLowerCase().includes(q);
        return titleMatch || triggerMatch || descMatch || idMatch;
      });
    }

    return result;
  }, [skills, activeCategory, search]);

  const verifiedCount = useMemo(() => {
    return Object.values(verifyResults).filter((v) => v.verified).length;
  }, [verifyResults]);

  if (!token) return <AuthGate />;

  const isPrivileged = isManager() || isChuQuan();
  const selectedMeta = selectedSkillId ? SKILL_METAS[selectedSkillId] : null;

  return (
    <div className="nq-page space-y-6">
      <PageHeader
        kicker="TRỢ LÝ COPILOT · HỘP CÔNG CỤ TỰ ĐỘNG HÓA"
        title="DANH MỤC NĂNG LỰC TRỢ LÝ AI"
        meta="Tổng hợp các nghiệp vụ tính toán, đối soát và tự động hóa ca trực mà Trợ lý Copilot được trang bị để phục vụ nhân sự và quản lý quán."
      />

      {notice ? <Notice>{notice}</Notice> : null}
      {error ? <Alert kind="err">{error}</Alert> : null}

      {/* Dải tóm tắt nghiệp vụ */}
      <Summary
        cells={[
          {
            n: `${skills.length} NĂNG LỰC`,
            k: "Sẵn sàng phục vụ",
            tone: "ok",
          },
          {
            n: "100%",
            k: "Thuật toán tất định",
            tone: "ok",
          },
          {
            n: "TỰ ĐỘNG",
            k: "Bảo vệ an toàn ca",
            tone: "ok",
          },
          {
            n: verifiedCount > 0 ? `${verifiedCount} ĐÃ KIỂM THỬ` : "24/7 TRỰC TUYẾN",
            k: "Độ chính xác dữ liệu",
            tone: verifiedCount > 0 ? "ok" : "default",
          },
        ]}
      />

      {/* Bộ lọc Danh mục & Ô Tìm kiếm */}
      <div className="nq-surface-row p-4 space-y-4 shadow-[var(--nq-elev-2)]">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div className="w-full sm:w-96">
            <input
              type="text"
              placeholder="Tìm theo tên nghiệp vụ, từ khóa gọi trợ lý…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={inputClassName}
            />
          </div>

          <div className="flex items-center gap-2">
            <Btn variant="ghost" onClick={loadSkills} disabled={loading}>
              Tải lại
            </Btn>
            <BtnLink href="/copilot" variant="primary">
              Mở Trợ lý Copilot ↗
            </BtnLink>
          </div>
        </div>

        {/* Category Pills */}
        <div className="flex flex-wrap gap-2 pt-2 border-t border-[var(--nq-line)]">
          {Object.entries(SKILL_CAT_MAP).map(([key, cat]) => {
            const isActive = activeCategory === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setActiveCategory(key)}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-colors ${
                  isActive
                    ? "bg-[var(--nq-accent)] text-white shadow-sm"
                    : "bg-[var(--nq-surface-hi)] text-[var(--nq-dim)] hover:text-[var(--nq-fg)] border border-[var(--nq-line)]"
                }`}
              >
                {cat.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Danh sách thẻ Năng lực AI */}
      <OpsCard
        eyebrow="Hộp công cụ Copilot"
        title="Danh sách năng lực tự động hóa"
        count={filteredSkills.length}
        countLabel="năng lực"
      >
        {loading ? (
          <Loading skeleton="list">Đang nạp danh mục năng lực…</Loading>
        ) : filteredSkills.length === 0 ? (
          <Empty title="Không tìm thấy năng lực phù hợp">
            Không có năng lực nào khớp với từ khóa tìm kiếm hoặc danh mục đã chọn.
          </Empty>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredSkills.map((skill) => {
              const meta = SKILL_METAS[skill.skill_id];
              const verifyRes = verifyResults[skill.skill_id];
              const isVerifying = verifying[skill.skill_id];

              const title = meta ? meta.title : skill.name;
              const icon = meta?.icon || "⚡";
              const categoryLabel = meta?.categoryLabel || "Vận hành chung";
              const benefitText =
                meta?.benefit || skill.description || "Tự động hóa nghiệp vụ ca làm việc.";
              const samplePrompt = meta?.samplePrompt || `Hỗ trợ ${title.toLowerCase()}`;
              const triggers = meta?.triggers || [];

              return (
                <div
                  key={skill.skill_id}
                  className="bg-[var(--nq-surface)] nq-surface-tile hover:border-[var(--nq-accent)] p-5 flex flex-col justify-between transition-all shadow-[var(--nq-elev-2)] rounded-lg"
                >
                  <div className="space-y-3">
                    {/* Header: Category Badge + Status */}
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-2xs font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-[var(--nq-surface-hi)] text-[var(--nq-accent)] border border-[var(--nq-line)]">
                        {categoryLabel}
                      </span>
                      {verifyRes ? (
                        <StatusChip tone={verifyRes.verified ? "ok" : "danger"}>
                          {verifyRes.verified ? "ĐÃ KIỂM THỬ" : "CÓ LỖI"}
                        </StatusChip>
                      ) : (
                        <StatusChip tone="ok">SẴN SÀNG</StatusChip>
                      )}
                    </div>

                    {/* Title with Icon */}
                    <div>
                      <h4 className="font-bold text-base text-[var(--nq-fg)] leading-snug flex items-center gap-2">
                        <span className="text-lg">{icon}</span>
                        <span>{title}</span>
                      </h4>
                      <p className="text-2xs font-mono text-[var(--nq-dim)] mt-0.5">
                        #{skill.skill_id}
                      </p>
                    </div>

                    {/* Business Benefit (What it does for you) */}
                    <p className="text-xs text-[var(--nq-fg)] leading-relaxed">
                      {benefitText}
                    </p>

                    {/* Triggers: How to summon via Chat */}
                    {triggers.length > 0 && (
                      <div className="pt-2 border-t border-[var(--nq-line)] space-y-1">
                        <span className="text-2xs uppercase tracking-wider font-semibold text-[var(--nq-dim)] block">
                          Từ khóa nhận diện khi chat:
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {triggers.slice(0, 4).map((trig) => (
                            <span
                              key={trig}
                              className="text-2xs px-1.5 py-0.5 rounded bg-[var(--nq-bg)] text-[var(--nq-dim)] border border-[var(--nq-line)]"
                            >
                              "{trig}"
                            </span>
                          ))}
                          {triggers.length > 4 && (
                            <span className="text-2xs text-[var(--nq-dim)] self-center">
                              +{triggers.length - 4}
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Verification result summary if verified */}
                    {verifyRes && (
                      <div className="bg-[var(--nq-bg)] p-2 rounded border border-[var(--nq-line)] text-xs space-y-1">
                        <p className="font-semibold text-2xs text-[var(--nq-dim)] uppercase">
                          Trạng thái kiểm tra logic:
                        </p>
                        <p className={verifyRes.verified ? "text-[var(--nq-green)] font-medium" : "text-[var(--nq-red)] font-medium"}>
                          {verifyRes.verified
                            ? "✓ Dữ liệu và thuật toán khớp 100%"
                            : "✗ Kịch bản kiểm thử không đạt"}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Actions footer */}
                  <div className="pt-4 mt-4 border-t border-[var(--nq-line)] flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => handleViewDetail(skill.skill_id)}
                      className="text-xs font-semibold text-[var(--nq-accent)] hover:underline"
                    >
                      Xem chi tiết
                    </button>

                    <div className="flex items-center gap-1.5">
                      <Btn
                        variant="ghost"
                        onClick={() => handleVerify(skill.skill_id)}
                        disabled={isVerifying}
                        busy={isVerifying}
                        busyLabel="Đang thử…"
                        className="text-2xs py-1 px-2.5"
                      >
                        Chạy thử
                      </Btn>
                      <BtnLink
                        href={`/copilot?q=${encodeURIComponent(samplePrompt)}`}
                        variant="ghost"
                        className="text-2xs py-1 px-2.5 text-[var(--nq-accent)] hover:bg-[var(--nq-surface-hi)]"
                      >
                        Gọi AI ↗
                      </BtnLink>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </OpsCard>

      {/* Advanced Admin Section: Thu gọn hẳn vào Drawer kỹ thuật để không cạnh tranh với Cẩm nang */}
      {isPrivileged && (
        <div className="mt-8">
          <TechnicalDrawer summary="Dành cho Quản trị viên: Huấn luyện năng lực mới từ Cẩm nang SOP (Nâng cao)">
            <div className="p-4 bg-[var(--nq-surface)] border border-[var(--nq-line)] rounded-lg space-y-4">
              <div>
                <h4 className="font-bold text-sm text-[var(--nq-fg)] uppercase">
                  Biên dịch cẩm nang thành công cụ tự động (Distill Engine)
                </h4>
                <p className="text-xs text-[var(--nq-dim)] mt-1">
                  Khi bạn nhập nội dung quy trình tại đây, hệ thống sẽ tự động sinh mã kịch bản kiểm tra độc lập và nạp vào danh mục năng lực của Copilot.
                </p>
              </div>

              <form onSubmit={handleDistillSop} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-2xs font-mono uppercase text-[var(--nq-dim)] mb-1">
                      Mã định danh (slug viết liền, vd: sop-ve-sinh-may)
                    </label>
                    <input
                      type="text"
                      value={sopId}
                      onChange={(e) => setSopId(e.target.value)}
                      placeholder="sop-ve-sinh-may"
                      className={inputClassName}
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-2xs font-mono uppercase text-[var(--nq-dim)] mb-1">
                      Tên nghiệp vụ
                    </label>
                    <input
                      type="text"
                      value={sopTitle}
                      onChange={(e) => setSopTitle(e.target.value)}
                      placeholder="Quy trình vệ sinh máy pha espresso cuối ca"
                      className={inputClassName}
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-2xs font-mono uppercase text-[var(--nq-dim)] mb-1">
                    Nội dung quy trình chi tiết (Markdown)
                  </label>
                  <textarea
                    rows={5}
                    value={sopMarkdown}
                    onChange={(e) => setSopMarkdown(e.target.value)}
                    placeholder="## Mục tiêu&#10;Đảm bảo máy pha sạch bã cà phê...&#10;&#10;## Các bước thực hiện&#10;1. Xả họng pha 10s...&#10;2. Dùng chổi cọ lưới lọc..."
                    className={textareaClassName}
                    required
                  />
                </div>

                <div className="flex justify-end gap-2">
                  <Btn variant="primary" type="submit" busy={distilling} busyLabel="Đang biên dịch…">
                    Tạo & Kiểm định năng lực mới
                  </Btn>
                </div>
              </form>
            </div>
          </TechnicalDrawer>
        </div>
      )}

      {/* Modal Chi tiết Năng lực */}
      <Dialog
        open={Boolean(selectedSkillId)}
        title={selectedMeta ? `${selectedMeta.icon} ${selectedMeta.title}` : `Năng lực: ${selectedSkillId}`}
        onClose={() => {
          setSelectedSkillId(null);
          setDetailData(null);
        }}
        footer={
          <div className="flex justify-between items-center w-full">
            {selectedMeta ? (
              <BtnLink
                href={`/copilot?q=${encodeURIComponent(selectedMeta.samplePrompt)}`}
                variant="primary"
              >
                Mở Copilot gọi lệnh này ↗
              </BtnLink>
            ) : <span />}
            <Btn
              variant="ghost"
              onClick={() => {
                setSelectedSkillId(null);
                setDetailData(null);
              }}
            >
              Đóng
            </Btn>
          </div>
        }
      >
        {detailLoading ? (
          <Loading skeleton="text">Đang nạp thông tin chi tiết…</Loading>
        ) : detailData ? (
          <div className="space-y-5">
            {/* Business summary */}
            <div className="space-y-2 bg-[var(--nq-surface-hi)] p-4 rounded border border-[var(--nq-line)]">
              <span className="text-2xs font-bold uppercase tracking-wider text-[var(--nq-accent)]">
                Lợi ích nghiệp vụ cho quán
              </span>
              <p className="text-sm text-[var(--nq-fg)] leading-relaxed">
                {selectedMeta?.benefit || detailData.content.slice(0, 200)}
              </p>
            </div>

            {/* Triggers and sample chat query */}
            {selectedMeta && (
              <div className="space-y-2">
                <span className="text-2xs font-bold uppercase tracking-wider text-[var(--nq-dim)]">
                  Cách nhân viên gọi Trợ lý thực hiện:
                </span>
                <div className="p-3 bg-[var(--nq-bg)] rounded border border-[var(--nq-line)] flex items-center justify-between gap-2">
                  <span className="text-xs text-[var(--nq-fg)] font-medium">
                    💬 "{selectedMeta.samplePrompt}"
                  </span>
                  <BtnLink
                    href={`/copilot?q=${encodeURIComponent(selectedMeta.samplePrompt)}`}
                    variant="ghost"
                    className="text-2xs py-1 px-2 text-[var(--nq-accent)]"
                  >
                    Thử ngay
                  </BtnLink>
                </div>
                <div className="flex flex-wrap gap-1 pt-1">
                  <span className="text-2xs text-[var(--nq-dim)] mr-1 self-center">Các từ khóa kích hoạt:</span>
                  {selectedMeta.triggers.map((t) => (
                    <span
                      key={t}
                      className="text-2xs px-2 py-0.5 rounded bg-[var(--nq-surface)] text-[var(--nq-dim)] border border-[var(--nq-line)]"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Technical Drawer (Files, Scripts, SHA-256) - strictly collapsed for developers */}
            <TechnicalDrawer summary="Thông tin Kỹ thuật & Kiểm định hệ thống (Dành cho Lập trình viên)">
              <div className="space-y-3 pt-2 text-xs">
                <div className="grid grid-cols-2 gap-2 p-2 bg-[var(--nq-bg)] rounded border border-[var(--nq-line)] font-mono text-2xs">
                  <div>
                    <span className="text-[var(--nq-dim)]">Mã định danh:</span> {detailData.skill_id}
                  </div>
                  <div>
                    <span className="text-[var(--nq-dim)]">Kịch bản (Scripts):</span> {detailData.scripts.length > 0 ? detailData.scripts.join(", ") : "Không có"}
                  </div>
                  <div>
                    <span className="text-[var(--nq-dim)]">Tài liệu tham chiếu:</span> {detailData.references.length > 0 ? detailData.references.join(", ") : "Không có"}
                  </div>
                  <div className="truncate">
                    <span className="text-[var(--nq-dim)]">Mã băm SHA256:</span> {detailData.content_sha256}
                  </div>
                </div>

                <TechnicalDrawer summary="Xem mã nguồn định nghĩa kỹ năng (SKILL.md)">
                  <div className="nq-prose-block text-2xs">{detailData.content}</div>
                </TechnicalDrawer>
                <TechnicalDrawer summary="Xem ngữ cảnh đưa vào trợ lý (Prompt Context)">
                  <div className="nq-prose-block nq-prose-block--muted text-2xs">{detailData.prompt_context_sample}</div>
                </TechnicalDrawer>
              </div>
            </TechnicalDrawer>
          </div>
        ) : (
          <Empty title="Không tìm thấy">Không đọc được thông tin chi tiết năng lực này.</Empty>
        )}
      </Dialog>
    </div>
  );
}
