"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { fieldLabel } from "../../lib/labels";
import { viError } from "../../lib/present";
import { getToken, isChuQuan, isManager } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  Empty,
  Loading,
  Notice,
  OpsCard,
  PageGrid,
  PageHeader,
  StatusChip,
} from "../../ui/kit";
import { AiInsightPanel } from "../../ui/ai/AiInsightPanel";
import { AskAiBox } from "../../ui/ai/AskAiBox";

type Generation = {
  id: string;
  channel: "gmail" | "facebook";
  created_at: string;
  policy_action: string;
  rule_version: string;
  draft?: { subject?: string; body?: string };
};

type Proposal = {
  id: string;
  channel: string;
  status: string;
  evidence_count: number;
  rule?: { text?: string; priority?: number };
  updated_at: string;
  rejection_reason?: string | null;
};

type Summary = {
  evaluation_count: number;
  average_score: number;
  passed_count: number;
  feedback_by_type: Record<string, number>;
};

type OperationStatus = {
  flags: Record<string, boolean>;
  retention_days: number;
  breakers?: {
    gmail?: boolean;
    facebook?: boolean;
  };
};

const STATUS_LABEL: Record<string, string> = {
  active: "Đang dùng",
  approved: "Đã duyệt",
  pending: "Chờ duyệt",
  conflict_pending: "Xung đột — chờ duyệt",
  rejected: "Từ chối",
  paused: "Tạm dừng",
  rolled_back: "Đã hoàn tác",
};

const STATUS_TONE: Record<string, "default" | "warn" | "danger" | "ok" | "info"> = {
  active: "ok",
  approved: "ok",
  pending: "warn",
  conflict_pending: "danger",
  rejected: "danger",
  paused: "warn",
  rolled_back: "danger",
};

const CHANNEL_LABEL: Record<string, string> = {
  gmail: "Gmail",
  facebook: "Facebook",
  fb: "Facebook",
};

const POLICY_LABEL: Record<string, string> = {
  send: "Gửi",
  draft: "Bản nháp",
  block: "Chặn",
  rewrite: "Viết lại",
  escalate: "Chuyển duyệt",
  auto_approve: "Tự duyệt",
  hold: "Giữ lại",
};

const FLAG_LABEL: Record<string, string> = {
  NHIPQUAN_FB_AUTO_SEND: "Tự gửi tin Facebook",
  NHIPQUAN_FB_LEARNING_ENABLED: "Học từ Facebook",
  NHIPQUAN_MAIL_QUALITY_GATE: "Cổng chất lượng email",
  NHIPQUAN_MAIL_AUTO_APPROVE: "Tự duyệt email",
  NHIPQUAN_MAIL_REFLECTION_ENABLED: "Phản chiếu Gmail",
  NHIPQUAN_RULE_AUTO_APPLY: "Tự áp dụng quy tắc",
  NHIPQUAN_AI_CIRCUIT_BREAKER: "Ngắt mạch AI",
  NHIPQUAN_AI_CANARY_ENABLED: "Canary AI",
};

function policyLabel(code: string): string {
  return POLICY_LABEL[code] ?? fieldLabel(code);
}

export default function AiLearningPage() {
  const [mounted, setMounted] = useState(false);
  const [token, setToken] = useState("");
  const [manager, setManager] = useState(false);
  const [owner, setOwner] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [operations, setOperations] = useState<OperationStatus | null>(null);
  const [generations, setGenerations] = useState<Generation[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setToken(getToken());
    setManager(isManager());
    setOwner(isChuQuan());
    setMounted(true);
    if (!getToken()) setLoading(false);
  }, []);

  const load = useCallback(async () => {
    if (!getToken()) return;
    setLoading(true);
    try {
      const [nextSummary, nextOperations, nextGenerations, nextProposals] = await Promise.all([
        apiGet<Summary>("/api/v1/ai/evaluations/summary"),
        apiGet<OperationStatus>("/api/v1/ai/operations/status"),
        apiGet<{ items: Generation[] }>("/api/v1/ai/generations?channel=gmail"),
        apiGet<{ items: Proposal[] }>("/api/v1/ai/rules/proposals"),
      ]);
      setSummary(nextSummary);
      setOperations(nextOperations);
      setGenerations(nextGenerations.items ?? []);
      setProposals(nextProposals.items ?? []);
      setError(null);
    } catch (cause) {
      setError(viError(cause, { doing: "đọc vòng học AI" }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  async function act(id: string, path: string, success: string) {
    setBusy(`${id}:${path}`);
    setError(null);
    setNotice(null);
    try {
      const res = await apiSend<{ ok?: boolean; reason?: string }>(path);
      if (res && res.ok === false) {
        if (res.reason === "rule_conflict") {
          setError(
            "Phát hiện xung đột với quy tắc hiện có. Đề xuất đã chuyển sang 'Xung đột — chờ duyệt'.",
          );
        } else {
          setError(`Thao tác không thành công: ${res.reason || "Lỗi không xác định"}`);
        }
      } else {
        setNotice(success);
      }
      await load();
    } catch (cause) {
      setError(
        viError(cause, {
          doing: "cập nhật quy tắc AI",
          forbidden: "Chỉ chủ quán có thể thực hiện thao tác này.",
        }),
      );
    } finally {
      setBusy(null);
    }
  }

  async function runReflection() {
    setBusy("reflection");
    setError(null);
    setNotice(null);
    try {
      const result = await apiSend<{ proposal_id?: string | null }>("/api/v1/ai/reflection/gmail/run");
      setNotice(
        result.proposal_id
          ? "Đã tạo đề xuất Gmail mới để chủ quán duyệt."
          : "Đã phân tích phản hồi; chưa đủ bằng chứng lặp lại để tạo quy tắc.",
      );
      await load();
    } catch (cause) {
      setError(viError(cause, { doing: "chạy phản chiếu Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  const isGmailBlocked = Boolean(operations?.breakers?.gmail);

  async function toggleBreaker() {
    setBusy("breaker");
    setError(null);
    setNotice(null);
    const nextOpen = !isGmailBlocked;
    try {
      await apiSend("/api/v1/ai/operations/circuit-breaker", { channel: "gmail", open: nextOpen });
      setNotice(
        nextOpen
          ? "Đã dừng gửi Gmail bằng AI. Các lệnh gửi mới sẽ bị chặn trước khi gửi đi."
          : "Đã mở lại kênh gửi Gmail AI.",
      );
      await load();
    } catch (cause) {
      setError(
        viError(cause, {
          doing: nextOpen ? "dừng kênh Gmail" : "mở lại kênh Gmail",
          forbidden: "Chỉ chủ quán có thể thao tác ngắt mạch.",
        }),
      );
    } finally {
      setBusy(null);
    }
  }

  if (!mounted) {
    return (
      <div className="nq-page nq-page--ai-learning">
        <PageHeader
          kicker="Vòng học AI"
          title="Học từ phản hồi"
          meta="Theo dõi chất lượng vòng học và tạo đề xuất quy tắc từ phản hồi đã kiểm duyệt."
        />
        <Loading skeleton="stats">Đang tải dữ liệu học AI…</Loading>
      </div>
    );
  }

  if (!token) return <AuthGate />;
  if (!manager) {
    return (
      <div className="nq-page">
        <PageHeader kicker="AI vận hành" title="Không đủ quyền truy cập" />
        <Notice>Trang này dành cho Quản lý và Chủ quán.</Notice>
      </div>
    );
  }

  const feedbackTotal = Object.values(summary?.feedback_by_type ?? {}).reduce(
    (total, value) => total + value,
    0,
  );
  const noLearningData =
    !error &&
    summary !== null &&
    (summary.evaluation_count ?? 0) === 0 &&
    (summary.passed_count ?? 0) === 0 &&
    feedbackTotal === 0 &&
    generations.length === 0 &&
    proposals.length === 0;

  return (
    <div className="nq-page nq-page--ai-learning">
      <PageHeader
        kicker="Vòng học AI"
        title="Học từ phản hồi"
        meta="Theo dõi chất lượng vòng học và tạo đề xuất quy tắc từ phản hồi đã kiểm duyệt."
      />
      <Notice>
        AI chỉ học khi quản lý hoặc chủ quán duyệt / sửa nội dung AI đề xuất — không tự bật quy tắc.
        Mọi quy tắc phải qua chủ quán duyệt.
      </Notice>
      {error ? <Alert>{error}</Alert> : null}
      {notice ? <Alert kind="ok">{notice}</Alert> : null}

      <PageGrid
        main={
          loading ? (
            <Loading skeleton="stats">Đang tải dữ liệu học AI…</Loading>
          ) : (
            <>
              <section className="nq-ai-metrics" aria-label="Chỉ số vòng học">
                <Metric label="Lần đánh giá" value={String(summary?.evaluation_count ?? 0)} />
                <Metric label="Điểm trung bình" value={`${Math.round((summary?.average_score ?? 0) * 100)}%`} />
                <Metric label="Đạt cổng chất lượng" value={String(summary?.passed_count ?? 0)} />
                <Metric label="Phản hồi đã ghi" value={String(feedbackTotal)} />
              </section>

              {noLearningData ? (
                <OpsCard title="Bắt đầu vòng học" eyebrow="Chưa có dữ liệu">
                  <p className="nq-ai-copy">
                    Vòng học bắt đầu khi quản lý gửi email qua Trợ lý hoặc duyệt tin khách ở Hộp thư Fanpage.
                    Mỗi lần duyệt/sửa, hệ thống ghi lại bản sinh và phản hồi; lặp đủ 3 lần cùng kiểu, chạy
                    Phản chiếu sẽ sinh đề xuất quy tắc.
                  </p>
                  <div className="nq-ai-actions">
                    <BtnLink href="/copilot">Gửi mail qua Trợ lý</BtnLink>
                    <BtnLink href="/page-quan/fb-inbox" variant="ghost">
                      Duyệt tin Fanpage
                    </BtnLink>
                  </div>
                </OpsCard>
              ) : null}

              <OpsCard
                title="Tạo đề xuất từ các lần sửa email"
                eyebrow="Phản chiếu Gmail"
                action={
                  <Btn onClick={runReflection} busy={busy === "reflection"} disabled={Boolean(busy)}>
                    Chạy phản chiếu
                  </Btn>
                }
              >
                <p className="nq-ai-copy">
                  Chỉ các mẫu có bằng chứng lặp lại mới trở thành đề xuất. Không có quy tắc nào tự được kích hoạt.
                </p>
              </OpsCard>

              <OpsCard
                title="Đề xuất và phiên bản đang dùng"
                eyebrow="Quy tắc"
                count={proposals.length}
                countLabel="đề xuất"
              >
                {proposals.length === 0 ? (
                  <Empty title="Chưa có đề xuất">Chạy phản chiếu khi đã có các chỉnh sửa email lặp lại.</Empty>
                ) : (
                  <div className="nq-ai-list">
                    {proposals.map((proposal) => (
                      <article key={proposal.id} className="nq-ai-card">
                        <div className="nq-ai-card__top">
                          <div className="nq-ai-card__tags">
                            <StatusChip tone={STATUS_TONE[proposal.status] ?? "default"}>
                              {STATUS_LABEL[proposal.status] ?? fieldLabel(proposal.status)}
                            </StatusChip>
                            <StatusChip>{CHANNEL_LABEL[proposal.channel] ?? proposal.channel}</StatusChip>
                            <span className="nq-ai-meta">{proposal.evidence_count} bằng chứng</span>
                          </div>
                          {owner ? (
                            <div className="nq-ai-card__actions">
                              {proposal.status === "pending" || proposal.status === "conflict_pending" ? (
                                <>
                                  <Btn
                                    size="sm"
                                    onClick={() =>
                                      act(
                                        proposal.id,
                                        `/api/v1/ai/rules/proposals/${proposal.id}/approve`,
                                        "Đã duyệt đề xuất.",
                                      )
                                    }
                                    busy={busy === `${proposal.id}:/api/v1/ai/rules/proposals/${proposal.id}/approve`}
                                    disabled={Boolean(busy)}
                                  >
                                    Duyệt
                                  </Btn>
                                  <Btn
                                    size="sm"
                                    variant="ghost"
                                    onClick={() =>
                                      act(
                                        proposal.id,
                                        `/api/v1/ai/rules/proposals/${proposal.id}/reject`,
                                        "Đã từ chối đề xuất.",
                                      )
                                    }
                                    busy={busy === `${proposal.id}:/api/v1/ai/rules/proposals/${proposal.id}/reject`}
                                    disabled={Boolean(busy)}
                                  >
                                    Từ chối
                                  </Btn>
                                </>
                              ) : null}
                              {proposal.status === "approved" ? (
                                <>
                                  <Btn
                                    size="sm"
                                    onClick={() =>
                                      act(
                                        proposal.id,
                                        `/api/v1/ai/rules/proposals/${proposal.id}/activate`,
                                        "Đã kích hoạt quy tắc.",
                                      )
                                    }
                                    busy={busy === `${proposal.id}:/api/v1/ai/rules/proposals/${proposal.id}/activate`}
                                    disabled={Boolean(busy)}
                                  >
                                    Kích hoạt
                                  </Btn>
                                  <Btn
                                    size="sm"
                                    variant="ghost"
                                    onClick={() =>
                                      act(
                                        proposal.id,
                                        `/api/v1/ai/rules/proposals/${proposal.id}/reject`,
                                        "Đã từ chối đề xuất.",
                                      )
                                    }
                                    busy={busy === `${proposal.id}:/api/v1/ai/rules/proposals/${proposal.id}/reject`}
                                    disabled={Boolean(busy)}
                                  >
                                    Từ chối
                                  </Btn>
                                </>
                              ) : null}
                              {proposal.status === "active" ? (
                                <>
                                  <Btn
                                    size="sm"
                                    variant="ghost"
                                    onClick={() =>
                                      act(
                                        proposal.id,
                                        `/api/v1/ai/rules/${proposal.id}/pause`,
                                        "Đã tạm dừng quy tắc.",
                                      )
                                    }
                                    busy={busy === `${proposal.id}:/api/v1/ai/rules/${proposal.id}/pause`}
                                    disabled={Boolean(busy)}
                                  >
                                    Tạm dừng
                                  </Btn>
                                  <Btn
                                    size="sm"
                                    variant="danger"
                                    onClick={() =>
                                      act(
                                        proposal.id,
                                        `/api/v1/ai/rules/${proposal.id}/rollback`,
                                        "Đã hoàn tác quy tắc.",
                                      )
                                    }
                                    busy={busy === `${proposal.id}:/api/v1/ai/rules/${proposal.id}/rollback`}
                                    disabled={Boolean(busy)}
                                  >
                                    Hoàn tác
                                  </Btn>
                                </>
                              ) : null}
                              {proposal.status === "paused" ? (
                                <>
                                  <Btn
                                    size="sm"
                                    onClick={() =>
                                      act(
                                        proposal.id,
                                        `/api/v1/ai/rules/proposals/${proposal.id}/activate`,
                                        "Đã kích hoạt lại quy tắc.",
                                      )
                                    }
                                    busy={busy === `${proposal.id}:/api/v1/ai/rules/proposals/${proposal.id}/activate`}
                                    disabled={Boolean(busy)}
                                  >
                                    Kích hoạt lại
                                  </Btn>
                                  <Btn
                                    size="sm"
                                    variant="danger"
                                    onClick={() =>
                                      act(
                                        proposal.id,
                                        `/api/v1/ai/rules/${proposal.id}/rollback`,
                                        "Đã hoàn tác quy tắc.",
                                      )
                                    }
                                    busy={busy === `${proposal.id}:/api/v1/ai/rules/${proposal.id}/rollback`}
                                    disabled={Boolean(busy)}
                                  >
                                    Hoàn tác
                                  </Btn>
                                </>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                        <p className="nq-ai-card__body">{proposal.rule?.text ?? "Quy tắc không có nội dung"}</p>
                        {proposal.rejection_reason ? (
                          <p className="nq-ai-meta text-[var(--nq-st-danger-ink)]">
                            Lý do từ chối: {proposal.rejection_reason}
                          </p>
                        ) : null}
                        <p className="nq-ai-meta">
                          Ưu tiên {proposal.rule?.priority ?? 0} · cập nhật{" "}
                          {proposal.updated_at ? new Date(proposal.updated_at).toLocaleString("vi-VN") : "—"}
                        </p>
                      </article>
                    ))}
                  </div>
                )}
              </OpsCard>

              <section className="nq-ai-split">
                <OpsCard title="Bản sinh email gần đây" eyebrow="Gmail">
                  {generations.length === 0 ? (
                    <Empty title="Chưa có bản ghi">Email được kiểm duyệt sẽ xuất hiện tại đây.</Empty>
                  ) : (
                    <div className="nq-ai-list">
                      {generations.slice(0, 8).map((generation) => (
                        <article key={generation.id} className="nq-ai-gen">
                          <p className="nq-ai-gen__title">{generation.draft?.subject ?? "Không có tiêu đề"}</p>
                          <p className="nq-ai-gen__body">{generation.draft?.body ?? ""}</p>
                          <p className="nq-ai-meta">
                            {policyLabel(generation.policy_action)} · phiên bản quy tắc{" "}
                            {generation.rule_version || "—"}
                          </p>
                        </article>
                      ))}
                    </div>
                  )}
                </OpsCard>

                <OpsCard title="Lớp bảo vệ đang bật" eyebrow="Vận hành">
                  <div className="nq-ai-flags">
                    {Object.entries(operations?.flags ?? {}).map(([name, enabled]) => (
                      <div key={name} className="nq-ai-flag">
                        <span className="nq-ai-flag__label">
                          {FLAG_LABEL[name] ?? fieldLabel(name.replace(/^NHIPQUAN_/, ""))}
                        </span>
                        <StatusChip tone={enabled ? "ok" : "default"}>{enabled ? "Bật" : "Tắt"}</StatusChip>
                      </div>
                    ))}
                  </div>
                  <p className="nq-ai-copy nq-ai-copy--tight">
                    Giữ dữ liệu học {operations?.retention_days ?? 180} ngày. Chỉ chạy thử, không xóa tự động.
                  </p>
                  {owner ? (
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      <Btn
                        variant={isGmailBlocked ? "primary" : "danger"}
                        onClick={toggleBreaker}
                        busy={busy === "breaker"}
                        disabled={Boolean(busy)}
                      >
                        {isGmailBlocked ? "Mở lại Gmail AI" : "Dừng Gmail AI"}
                      </Btn>
                      {isGmailBlocked ? <StatusChip tone="danger">Đang ngắt mạch</StatusChip> : null}
                    </div>
                  ) : (
                    <p className="nq-ai-copy nq-ai-copy--tight">Chủ quán có thể dừng khẩn cấp kênh Gmail AI.</p>
                  )}
                </OpsCard>
              </section>
            </>
          )
        }
        aside={
          <>
            <AiInsightPanel page="ai-learning" />
            <AskAiBox page="ai-learning" />
          </>
        }
      />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="nq-ai-metric">
      <p className="nq-ai-metric__label">{label}</p>
      <p className="nq-ai-metric__value">{value}</p>
    </div>
  );
}
