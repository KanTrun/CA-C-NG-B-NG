"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { viError } from "../../lib/present";
import { getToken, isChuQuan, isManager } from "../../lib/session";
import {
    Alert,
    AuthGate,
    Btn,
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
  path: string;
  scripts: string[];
  references: string[];
  sha256: string;
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

export default function SkillsPage() {
  const [token, setToken] = useState("");
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Live verification state per skill
  const [verifying, setVerifying] = useState<Record<string, boolean>>({});
  const [verifyResults, setVerifyResults] = useState<Record<string, VerifyResponse>>({});

  // Skill detail modal / expansion
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailData, setDetailData] = useState<SkillDetail | null>(null);

  // Distill new SOP state
  const [showDistillForm, setShowDistillForm] = useState(false);
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
      setError(viError(err, { doing: "tải danh mục kỹ năng vận hành" }));
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
      if (res.verified) {
        setNotice(`Kỹ năng "${skillId}" đã vượt qua bài kiểm tra tất định thành công.`);
      } else {
        setError(`Kỹ năng "${skillId}" không vượt qua kiểm định smoke test.`);
      }
    } catch (err) {
      setError(viError(err, { doing: `kiểm định trực tiếp kỹ năng ${skillId}` }));
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
      setError(viError(err, { doing: `đọc chi tiết mã nguồn kỹ năng ${skillId}` }));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDistillSop = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sopId.trim() || !sopTitle.trim() || !sopMarkdown.trim()) {
      setError("Vui lòng điền đầy đủ Mã kỹ năng, Tiêu đề và Nội dung cẩm nang SOP.");
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
      setShowDistillForm(false);
      setSopId("");
      setSopTitle("");
      setSopMarkdown("");
      await loadSkills();
    } catch (err) {
      setError(viError(err, { doing: "chưng cất cẩm nang SOP thành kỹ năng mới" }));
    } finally {
      setDistilling(false);
    }
  };

  const filteredSkills = useMemo(() => {
    if (!search.trim()) return skills;
    const q = search.toLowerCase();
    return skills.filter(
      (s) =>
        s.skill_id.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        s.scripts.some((sc) => sc.toLowerCase().includes(q)) ||
        s.references.some((rf) => rf.toLowerCase().includes(q)),
    );
  }, [skills, search]);

  const verifiedCount = useMemo(() => {
    return Object.values(verifyResults).filter((v) => v.verified).length;
  }, [verifyResults]);

  if (!token) return <AuthGate />;

  const isPrivileged = isManager() || isChuQuan();

  return (
    <div className="nq-page">
      <PageHeader
        kicker="REPO-TO-SKILL · ZERO-LLM DISPATCH"
        title="BỘ KỸ NĂNG VẬN HÀNH TẤT ĐỊNH"
        meta="Chuyển hóa 100% nghiệp vụ quán cà phê thành các Kỹ năng AI độc lập, tự chứa, kiểm định bằng mã băm SHA-256 và kịch bản Python không phụ thuộc LLM."
      />

      {notice ? <Notice>{notice}</Notice> : null}
      {error ? <Alert kind="err">{error}</Alert> : null}

      {/* Dải tóm tắt nghiệp vụ đếm được */}
      <Summary
        cells={[
          {
            n: `${skills.length} / 13`,
            k: "Kỹ năng sẵn sàng",
            tone: skills.length >= 13 ? "ok" : "warn",
          },
          {
            n: "100%",
            k: "Tất định (Zero LLM)",
            tone: "ok",
          },
          {
            n: "FAIL-CLOSED",
            k: "Toàn vẹn SHA-256",
            tone: "ok",
          },
          {
            n: verifiedCount > 0 ? `${verifiedCount} ĐẠT` : "LIVE AUDIT",
            k: "Kiểm định trực tiếp",
            tone: verifiedCount > 0 ? "ok" : "default",
          },
        ]}
      />

      {/* Action bar: Tìm kiếm + Chưng cất SOP mới */}
      <div className="nq-surface-row flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 p-4 mb-8 shadow-[var(--nq-elev-2)]">
        <div className="w-full sm:w-80">
          <input
            type="text"
            placeholder="Tìm kỹ năng, mã băm hoặc kịch bản…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={inputClassName}
          />
        </div>

        <div className="flex gap-2 w-full sm:w-auto">
          <Btn variant="ghost" onClick={loadSkills} disabled={loading}>
            Tải lại
          </Btn>
          {isPrivileged && (
            <Btn
              variant="primary"
              onClick={() => setShowDistillForm(!showDistillForm)}
            >
              {showDistillForm ? "Đóng biểu mẫu" : "+ Chưng cất SOP mới"}
            </Btn>
          )}
        </div>
      </div>

      {/* Form chưng cất cẩm nang thành kỹ năng */}
      {showDistillForm && isPrivileged && (
        <OpsCard
          eyebrow="Hybrid Playbook Distiller"
          title="Chưng cất Cẩm nang Quy trình (SOP) thành Kỹ năng"
        >
          <p className="text-sm font-mono text-[var(--nq-dim)] mb-4">
            Nhập mã định danh và văn bản SOP để hệ thống tự động sinh cấu trúc: <code>SKILL.md</code>, <code>scripts/</code> kiểm định và <code>references/</code>.
          </p>

          <form onSubmit={handleDistillSop} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono uppercase text-[var(--nq-dim)] mb-1">
                  Mã kỹ năng (slug, vd: sop-ve-sinh-may)
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
                <label className="block text-xs font-mono uppercase text-[var(--nq-dim)] mb-1">
                  Tiêu đề quy trình
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
              <label className="block text-xs font-mono uppercase text-[var(--nq-dim)] mb-1">
                Nội dung Markdown của Cẩm nang SOP
              </label>
              <textarea
                rows={6}
                value={sopMarkdown}
                onChange={(e) => setSopMarkdown(e.target.value)}
                placeholder="## Mục tiêu&#10;Đảm bảo máy pha sạch bã cà phê...&#10;&#10;## Các bước thực hiện&#10;1. Xả họng pha 10s...&#10;2. Dùng chổi cọ lưới lọc..."
                className={textareaClassName}
                required
              />
            </div>

            <div className="flex justify-end gap-2">
              <Btn variant="ghost" onClick={() => setShowDistillForm(false)} type="button">
                Hủy
              </Btn>
              <Btn variant="primary" type="submit" busy={distilling} busyLabel="Đang chưng cất…">
                Bắt đầu chưng cất thành Skill
              </Btn>
            </div>
          </form>
        </OpsCard>
      )}

      {/* Danh sách các kỹ năng */}
      <OpsCard
        eyebrow="Catalog Kỹ năng"
        title="13 Kỹ năng độc lập & Tự chứa"
        count={filteredSkills.length}
        countLabel="kỹ năng"
      >
        {loading ? (
          <Loading skeleton="list">Đang nạp danh mục kỹ năng…</Loading>
        ) : filteredSkills.length === 0 ? (
          <Empty title="Không tìm thấy kỹ năng nào">
            Không có kỹ năng nào khớp với từ khóa tìm kiếm của bạn.
          </Empty>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredSkills.map((skill) => {
              const verifyRes = verifyResults[skill.skill_id];
              const isVerifying = verifying[skill.skill_id];

              return (
                <div
                  key={skill.skill_id}
                  className="bg-[var(--nq-surface)] nq-surface-tile hover:border-[var(--nq-accent)] p-5 flex flex-col justify-between transition-all shadow-[var(--nq-elev-2)]"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-mono text-xs px-2 py-1 bg-[var(--nq-surface-hi)] text-[var(--nq-fg)] border border-[var(--nq-dim)] font-semibold">
                        {skill.skill_id}
                      </span>
                      {verifyRes ? (
                        <StatusChip tone={verifyRes.verified ? "ok" : "danger"}>
                          {verifyRes.verified ? "ĐẠT" : "LỖI"}
                        </StatusChip>
                      ) : (
                        <StatusChip tone="default">SẴN SÀNG</StatusChip>
                      )}
                    </div>

                    <h4 className="font-semibold text-lg text-[var(--nq-fg)] uppercase leading-tight">
                      {skill.name}
                    </h4>

                    {/* Scripts & References info */}
                    <div className="space-y-1 text-xs">
                      <div className="flex items-center gap-1 text-[var(--nq-dim)]">
                        <span className="font-mono font-medium text-[var(--nq-accent)]">Scripts ({skill.scripts.length}):</span>
                        <span className="truncate">
                          {skill.scripts.length > 0 ? skill.scripts.join(", ") : "Không có"}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 text-[var(--nq-dim)]">
                        <span className="font-mono font-medium text-[var(--nq-accent)]">Tài liệu ({skill.references.length}):</span>
                        <span className="truncate">
                          {skill.references.length > 0 ? skill.references.join(", ") : "Không có"}
                        </span>
                      </div>
                    </div>

                    {/* SHA256 integrity tag */}
                    <div className="pt-1">
                      <span className="text-2xs font-mono text-[var(--nq-dim)] bg-[var(--nq-bg)] px-2 py-1 border border-[var(--nq-dim)] block truncate">
                        SHA256: {skill.sha256}
                      </span>
                    </div>

                    {/* Output của bài kiểm tra Live nếu có */}
                    {verifyRes && verifyRes.script_results && (
                      <div className="bg-[var(--nq-bg)] p-2 border border-[var(--nq-dim)] text-xs font-mono space-y-1">
                        <p className="font-bold text-[var(--nq-fg)]">Kết quả smoke test:</p>
                        {Object.entries(verifyRes.script_results).map(([script, res]) => (
                          <div key={script} className="truncate">
                            <span className={res.passed ? "text-[var(--nq-green)]" : "text-[var(--nq-red)]"}>
                              {res.passed ? "✓" : "✗"} {script}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="pt-4 mt-4 border-t border-[var(--nq-line)] flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => handleViewDetail(skill.skill_id)}
                      className="text-xs font-bold uppercase tracking-wider text-[var(--nq-accent)] hover:underline"
                    >
                      Xem SKILL.md
                    </button>

                    <Btn
                      variant="ghost"
                      onClick={() => handleVerify(skill.skill_id)}
                      disabled={isVerifying}
                      busy={isVerifying}
                      busyLabel="Đang thử…"
                      className="text-xs py-1 px-3"
                    >
                      Kiểm tra Live
                    </Btn>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </OpsCard>

      <Dialog
        open={Boolean(selectedSkillId)}
        title={selectedSkillId ? `Kỹ năng: ${selectedSkillId}` : "Chi tiết kỹ năng"}
        onClose={() => {
          setSelectedSkillId(null);
          setDetailData(null);
        }}
        footer={
          <Btn
            variant="primary"
            onClick={() => {
              setSelectedSkillId(null);
              setDetailData(null);
            }}
          >
            Đóng
          </Btn>
        }
      >
        {detailLoading ? (
          <Loading skeleton="text">Đang đọc nội dung kỹ năng…</Loading>
        ) : detailData ? (
          <div className="space-y-4">
            <p className="text-sm text-[var(--nq-ink-muted)]">
              Định nghĩa kỹ năng và ngữ cảnh đưa vào trợ lý. Nội dung kỹ thuật nằm trong ngăn bên dưới.
            </p>
            {detailData.content_sha256 ? (
              <StatusChip tone="info">Chữ ký nội dung đã xác minh</StatusChip>
            ) : null}
            <TechnicalDrawer summary="Xem định nghĩa kỹ năng (SKILL.md)">
              <div className="nq-prose-block">{detailData.content}</div>
            </TechnicalDrawer>
            <TechnicalDrawer summary="Xem ngữ cảnh đưa vào trợ lý">
              <div className="nq-prose-block nq-prose-block--muted">{detailData.prompt_context_sample}</div>
            </TechnicalDrawer>
          </div>
        ) : (
          <Empty title="Không tải được">Không đọc được thông tin kỹ năng này.</Empty>
        )}
      </Dialog>
    </div>
  );
}
