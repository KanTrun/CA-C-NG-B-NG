"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiSend } from "../../../lib/api";
import { safeText, viError } from "../../../lib/present";
import { getToken, isChuQuan, isManager } from "../../../lib/session";
import { subscribeRealtime } from "../../../lib/realtime";
import {
  Alert,
  AuthGate,
  Btn,
  Confidence,
  Empty,
  Field,
  Loading,
  Notice,
  PageHeader,
  Select,
  StatusChip,
  Textarea,
  Toasts,
  useToasts,
} from "../../../ui/kit";

type FbItem = {
  id: number;
  source: string;
  external_psid: string;
  external_thread_id?: string | null;
  post_id?: string | null;
  external_user_name?: string | null;
  message_text: string;
  detected_intent: string;
  confidence: number;
  policy_action: string;
  assigned_role?: string | null;
  proposed_response?: string | null;
  flagged_reasons?: string[];
  status: string;
  created_at: string;
  expires_at?: string | null;
  // Comment-specific fields
  sentiment?: {
    sentiment: "positive" | "negative" | "neutral";
    score: number;
    keywords_found: string[];
    confidence: number;
  };
  comment_action?: "reply_public" | "hide_and_dm" | "hide_silent" | "escalate_owner";
  // Attachment-specific fields
  attachment_type?: string;
  attachment_url?: string | null;
};

type Stats = {
  by_status: Record<string, number>;
  total: number;
  auto_sent: number;
  auto_rate: number;
  escalation_unacked: number;
};

type Policy = {
  auto_send_enabled: boolean;
  jev_enabled?: boolean;
};

type StatusFilter = "pending" | "approved" | "rejected" | "all";
type SourceFilter = "all" | "comment" | "messenger";

const INTENT_LABEL: Record<string, string> = {
  chao_hoi: "Chào hỏi",
  hoi_gio_dia_chi: "Giờ / Địa chỉ",
  hoi_menu_gia: "Menu / Giá",
  hoi_khuyen_mai: "Khuyến mãi",
  dat_ban: "Đặt bàn",
  khieu_nai_gop_y: "Khiếu nại / Góp ý",
  tu_van_mon: "Tư vấn món",
  yeu_cau_dac_biet: "Yêu cầu đặc biệt",
  blocked_injection: "Chặn bảo mật",
  khac: "Khác",
};

const ACTION_LABEL: Record<string, string> = {
  queue_review: "Chờ duyệt",
  priority_review: "Ưu tiên",
  escalate_owner: "Báo chủ quán",
};

function actionTone(a: string): "warn" | "danger" | "default" {
  if (a === "escalate_owner") return "danger";
  if (a === "priority_review") return "warn";
  return "default";
}

function slaLeft(expiresAt?: string | null): { label: string; overdue: boolean } | null {
  if (!expiresAt) return null;
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(expiresAt);
  const end = new Date(hasTimezone ? expiresAt : `${expiresAt}Z`).getTime();
  if (!Number.isFinite(end)) return null;
  const diff = Math.round((end - Date.now()) / 1000);
  if (diff <= 0) return { label: "QUÁ HẠN", overdue: true };
  const m = Math.floor(diff / 60);
  const s = diff % 60;
  return { label: `${m}:${s.toString().padStart(2, "0")}`, overdue: false };
}

function formatCreated(iso?: string | null): string {
  if (!iso) return "";
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  const t = new Date(hasTimezone ? iso : `${iso}Z`);
  if (!Number.isFinite(t.getTime())) return "";
  const hh = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dd = t.toLocaleDateString([], { day: "2-digit", month: "2-digit" });
  return `${hh} · ${dd}`;
}

function commentActionLabel(a: string): string {
  if (a === "reply_public") return "Trả lời công khai";
  if (a === "hide_and_dm") return "Ẩn + nhắn tin riêng";
  if (a === "hide_silent") return "Ẩn im lặng";
  if (a === "escalate_owner") return "Báo chủ quán";
  return a;
}

function attachmentLabel(t: string): string {
  if (t === "image") return "Ảnh";
  if (t === "audio") return "Âm thanh";
  if (t === "video") return "Video";
  if (t === "file") return "Tệp";
  return t;
}

export default function FbInboxPage() {
  const [token, setToken] = useState("");
  const [manager, setManager] = useState(false);
  const [chuQuan, setChuQuan] = useState(false);
  const [items, setItems] = useState<FbItem[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [query, setQuery] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [webhookReady, setWebhookReady] = useState<boolean | null>(null);
  const [webhookDetail, setWebhookDetail] = useState("");
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [policyBusy, setPolicyBusy] = useState(false);
  const { toasts, push, dismiss } = useToasts();

  useEffect(() => {
    setToken(getToken());
    setManager(isManager());
    setChuQuan(isChuQuan());
    if (!getToken()) setLoading(false);
  }, []);

  const load = useCallback(() => {
    if (!getToken()) return;
    const statusQuery = statusFilter === "all" ? "" : `status=${statusFilter}&`;
    apiGet<{ items: FbItem[] }>(`/api/v1/page/fb-inbox?${statusQuery}limit=100`)
      .then((d) => setItems(d.items ?? []))
      .catch((e) => setError(viError(e, { doing: "đọc hộp thư Facebook" })))
      .finally(() => setLoading(false));
    apiGet<Stats>("/api/v1/page/fb-inbox/stats")
      .then((s) => setStats(s))
      .catch(() => {});
    apiGet<Policy>("/api/v1/page/fb-policy")
      .then((p) => setPolicy(p))
      .catch(() => {});
    apiGet<{ webhook_ready?: boolean; webhook_detail?: string }>("/api/v1/page/status")
      .then((s) => {
        if (typeof s.webhook_ready === "boolean") setWebhookReady(s.webhook_ready);
        if (s.webhook_detail) setWebhookDetail(s.webhook_detail);
      })
      .catch(() => {});
  }, [statusFilter]);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  const statusFilterRef = useRef(statusFilter);
  statusFilterRef.current = statusFilter;

  // Real-time subscription for fb-inbox updates
  useEffect(() => {
    if (!token) return;
    const unsubscribe = subscribeRealtime((packet) => {
      if (packet.event === "fb_inbox:new") {
        const newItem = packet.data as FbItem;
        const currentFilter = statusFilterRef.current;
        // Only add if matches current filter
        if (currentFilter === "all" || currentFilter === newItem.status) {
          setItems((prev) => {
            // Avoid duplicates
            if (prev.some((it) => it.id === newItem.id)) return prev;
            return [newItem, ...prev];
          });
        }
        // Refresh stats
        apiGet<Stats>("/api/v1/page/fb-inbox/stats").then((s) => setStats(s)).catch(() => {});
      } else if (packet.event === "fb_inbox:update") {
        const update = packet.data as { id: number; status?: string; final_response?: string; decided_by?: string; decided_at?: string; sent?: boolean };
        setItems((prev) =>
          prev.map((it) => {
            if (it.id !== update.id) return it;
            return {
              ...it,
              status: update.status ?? it.status,
              proposed_response: update.final_response ?? it.proposed_response,
            };
          })
        );
        // Refresh stats
        apiGet<Stats>("/api/v1/page/fb-inbox/stats").then((s) => setStats(s)).catch(() => {});
      }
    });
    return () => unsubscribe();
  }, [token]);

  async function decide(item: FbItem, quyet_dinh: string, noi_dung?: string, ly_do?: string) {
    setBusy(item.id);
    setError(null);
    try {
      const res = await apiSend<{ sent: boolean }>(
        `/api/v1/page/fb-inbox/${item.id}/decide`,
        { quyet_dinh, noi_dung, ly_do },
      );
      push(
        res.sent
          ? "Đã gửi phản hồi cho khách."
          : quyet_dinh === "tu_choi"
            ? "Đã từ chối tin này."
            : "Đã ghi nhận quyết định.",
      );
      setEditing(null);
      setDraft("");
      load();
    } catch (e) {
      setError(viError(e, { doing: "xử lý tin nhắn", conflict: "Tin này vừa được người khác duyệt." }));
    } finally {
      setBusy(null);
    }
  }

  if (!token) return <AuthGate />;
  if (!manager) {
    return (
      <div className="nq-page">
        <PageHeader kicker="Kiểm duyệt" title="Không đủ quyền truy cập" />
        <Notice>Bạn cần là Quản lý hoặc Chủ quán để duyệt tin nhắn Fanpage.</Notice>
      </div>
    );
  }

  return (
    <div className="nq-page">
      <Toasts toasts={toasts} onDismiss={dismiss} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 16 }}>
        <PageHeader
          kicker="AG-FBPAGE · Kiểm duyệt chỉn chu"
          title="Hộp thư Fanpage chờ duyệt"
          meta="Bình luận trên bài viết/ảnh Page và tin nhắn Messenger chờ duyệt tập trung ở đây. Agent tự trả lời chào hỏi, menu, địa chỉ và giờ mở cửa đã niêm yết. Quản lý chỉ duyệt khiếu nại, đặt bàn, đổi giờ đặc biệt và việc nhạy cảm."
        />
        <a
          href="/page-quan/dat-ban"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "8px 16px",
            borderRadius: 8,
            /* `--nq-ok` (#22c55e) trên chữ trắng chỉ đạt 2.28:1; nền xanh đậm hơn
               giữ nguyên sắc nhưng đạt 5.02:1. Đây là lối vào màn hình đặt bàn —
               nút duy nhất trên khối này, không được để chữ mờ. */
            background: "#15803d",
            color: "#fff",
            fontWeight: 600,
            textDecoration: "none",
            fontSize: "0.9rem",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            whiteSpace: "nowrap",
            marginTop: 8,
          }}
        >
          Sơ đồ & Lịch đặt bàn
        </a>
      </div>

      {policy ? (
        <Notice>
          {policy.auto_send_enabled
            ? "Đang bật tự trả lời FAQ (chào hỏi, menu, địa chỉ, giờ niêm yết). Khiếu nại, đặt bàn, đổi giờ đặc biệt vẫn chờ duyệt."
            : "Đang tắt tự gửi Messenger — tin nhắn FAQ vào hộp thư này. Bình luận công khai an toàn vẫn tự trả lời (không phụ thuộc công tắc này)."}
          {chuQuan ? (
            <span style={{ display: "inline-block", marginLeft: 12 }}>
              <Btn
                variant={policy.auto_send_enabled ? "ghost" : undefined}
                busy={policyBusy}
                onClick={async () => {
                  setPolicyBusy(true);
                  try {
                    const next = await apiSend<Policy>(
                      "/api/v1/page/fb-policy",
                      { auto_send_enabled: !policy.auto_send_enabled, note: "inbox_toggle" },
                      "PUT",
                    );
                    setPolicy(next);
                    push(next.auto_send_enabled ? "Đã bật tự trả lời FAQ." : "Đã tắt tự gửi.");
                  } catch (e) {
                    setError(viError(e, { doing: "cập nhật chính sách tự trả lời" }));
                  } finally {
                    setPolicyBusy(false);
                  }
                }}
              >
                {policy.auto_send_enabled ? "Tắt tự trả lời" : "Bật tự trả lời FAQ"}
              </Btn>
            </span>
          ) : null}
        </Notice>
      ) : null}
      {policy ? (
        <Notice>
          {policy.jev_enabled
            ? "Đang bật cảm biến Jev (TypeSafe) để phát hiện nguy cơ sức khỏe/pháp lý/gay gắt bổ trợ regex."
            : "Đang tắt cảm biến Jev — chỉ dùng regex làm lưới an toàn. Chủ quán bật để Jev hỗ trợ phát hiện cách diễn đạt khéo mà regex bỏ lọt."}
          {chuQuan ? (
            <span style={{ display: "inline-block", marginLeft: 12 }}>
              <Btn
                variant={policy.jev_enabled ? "ghost" : undefined}
                busy={policyBusy}
                onClick={async () => {
                  setPolicyBusy(true);
                  try {
                    const next = await apiSend<Policy>(
                      "/api/v1/page/fb-policy",
                      { jev_enabled: !policy.jev_enabled, note: "inbox_jev_toggle" },
                      "PUT",
                    );
                    setPolicy(next);
                    push(next.jev_enabled ? "Đã bật cảm biến Jev." : "Đã tắt cảm biến Jev.");
                  } catch (e) {
                    setError(viError(e, { doing: "cập nhật trạng thái cảm biến Jev" }));
                  } finally {
                    setPolicyBusy(false);
                  }
                }}
              >
                {policy.jev_enabled ? "Tắt Jev" : "Bật Jev"}
              </Btn>
            </span>
          ) : null}
        </Notice>
      ) : null}

      {error ? <Alert>{error}</Alert> : null}
      {loading ? <Loading skeleton="list">Đang tải hộp thư…</Loading> : null}

      {webhookReady === false ? (
        <Alert kind="err">
          Webhook Facebook chưa sẵn sàng ({webhookDetail || "thiếu cấu hình"}) — bình luận trên bài
          viết/ảnh Page không vào được hộp thư này. Cần điền NHIPQUAN_FB_APP_SECRET +
          NHIPQUAN_FB_WEBHOOK_VERIFY rồi subscribe field feed trên Meta App.
        </Alert>
      ) : null}
      {webhookReady !== false ? (
        <Notice>
          Bình luận đã tự trả lời (intent an toàn) không nằm ở “Chờ duyệt” — chuyển lọc Trạng thái sang “Tất
          cả” để thấy toàn bộ.
        </Notice>
      ) : null}

      {stats ? (
        <div className="mb-8 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCell label="Chờ duyệt" value={String(stats.by_status.pending ?? 0)} />
          <StatCell label="Tự động gửi" value={String(stats.auto_sent)} />
          <StatCell label="Báo chủ chưa xác nhận" value={String(stats.escalation_unacked)} danger={stats.escalation_unacked > 0} />
          <StatCell label="Tổng xử lý" value={String(stats.total)} />
        </div>
      ) : null}

      <label className="block max-w-xs mb-4">
        <span className="block text-sm font-bold uppercase tracking-widest text-[var(--nq-dim)] mb-2">
          Trạng thái
        </span>
        <Select
          value={statusFilter}
          onChange={(event) => {
            setLoading(true);
            setStatusFilter(event.target.value as StatusFilter);
          }}
        >
          <option value="pending">Chờ duyệt</option>
          <option value="approved">Đã duyệt</option>
          <option value="rejected">Đã từ chối</option>
          <option value="all">Tất cả</option>
        </Select>
      </label>

      {/* Lọc nguồn + tìm kiếm (lọc phía client, không đổi API nên không vỡ e2e) */}
      <div className="mb-6 flex flex-wrap items-center gap-2">
        {(
          [
            { id: "all", label: `Tất cả (${items.length})` },
            { id: "comment", label: `Bình luận (${items.filter((i) => i.source === "comment").length})` },
            { id: "messenger", label: `Messenger (${items.filter((i) => i.source !== "comment").length})` },
          ] as const
        ).map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setSourceFilter(f.id)}
            aria-pressed={sourceFilter === f.id}
            className={`rounded-full border px-3 py-1.5 text-xs font-bold transition cursor-pointer ${
              sourceFilter === f.id
                ? "border-[var(--nq-accent)] bg-[var(--nq-accent)] text-[var(--nq-accent-ink)]"
                : "border-[var(--nq-dim)] text-[var(--nq-muted)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
            }`}
          >
            {f.label}
          </button>
        ))}
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm tên khách / nội dung / bản nháp…"
          aria-label="Tìm trong hộp thư"
          className="min-w-[220px] flex-1 rounded-full border border-[var(--nq-dim)] bg-[var(--nq-surface)] px-3 py-1.5 text-xs text-[var(--nq-primary)] placeholder:text-[var(--nq-muted)] focus:border-[var(--nq-accent)] focus:outline-none sm:max-w-xs sm:flex-none"
        />
        <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-[var(--nq-muted)]">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(e) => setOverdueOnly(e.target.checked)}
            className="accent-[var(--nq-red)]"
          />
          Chỉ quá hạn SLA
        </label>
      </div>

      {(() => {
        const q = query.trim().toLowerCase();
        const visible = items.filter((it) => {
          if (sourceFilter === "comment" && it.source !== "comment") return false;
          if (sourceFilter === "messenger" && it.source === "comment") return false;
          if (overdueOnly && !slaLeft(it.expires_at)?.overdue) return false;
          if (q) {
            const hay = `${it.external_user_name ?? ""} ${it.message_text} ${it.proposed_response ?? ""}`.toLowerCase();
            if (!hay.includes(q)) return false;
          }
          return true;
        });
        // Quá hạn SLA lên trước, còn lại giữ thứ tự mới nhất của API.
        const ordered = [...visible].sort((a, b) => {
          const ao = slaLeft(a.expires_at)?.overdue ? 0 : 1;
          const bo = slaLeft(b.expires_at)?.overdue ? 0 : 1;
          return ao - bo;
        });
        return (
          <>
            {ordered.length === 0 && !loading ? (
              <Empty>
                {sourceFilter === "comment"
                  ? "Chưa có bình luận nào ở trạng thái này. Bình luận trên bài viết/ảnh Page sẽ hiện ở đây sau khi webhook feed (field feed + item comment) được bật."
                  : "Không có tin nhắn ở trạng thái đã chọn."}
              </Empty>
            ) : null}

      <div className="space-y-4">
        {ordered.map((it) => {
          const ownerOnly = it.assigned_role === "chu_quan" && !chuQuan;
          const sla = slaLeft(it.expires_at);
          const canAct = it.status === "pending" && !ownerOnly;
          return (
            <article
              key={it.id}
              className={`nq-surface-block bg-[var(--nq-surface)] p-5 ${
                sla?.overdue ? "border-[var(--nq-red)]" : ""
              }`}
            >
              {/* Dòng 1: nguồn + mức độ + SLA — quét 1 giây biết phải làm gì */}
              <div className="mb-2 flex flex-wrap items-center gap-2">
                {it.source === "comment" ? (
                  <StatusChip tone="default">Bình luận</StatusChip>
                ) : (
                  <StatusChip>Messenger</StatusChip>
                )}
                {it.status !== "pending" ? <StatusChip>{safeText(it.status)}</StatusChip> : null}
                <StatusChip tone={actionTone(it.policy_action)}>
                  {ACTION_LABEL[it.policy_action] ?? safeText(it.policy_action)}
                </StatusChip>
                {sla ? (
                  <span className={`font-mono text-xs ${sla.overdue ? "text-[var(--nq-red)] font-bold" : "text-[var(--nq-dim)]"}`}>
                    SLA {sla.label}
                  </span>
                ) : null}
                {ownerOnly ? <span className="text-xs text-[var(--nq-red)] uppercase tracking-widest">Chỉ chủ quán duyệt</span> : null}
              </div>

              {/* Dòng 2: ai nói + khi nào + ở đâu */}
              <div className="mb-0.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <p className="text-[var(--nq-fg)] text-base font-bold">
                  {safeText(it.external_user_name, "Khách hàng")}
                </p>
                <span className="font-mono text-[11px] text-[var(--nq-dim)]">{formatCreated(it.created_at)}</span>
                {it.source === "comment" && it.post_id ? (
                  <a
                    href={`https://facebook.com/${it.post_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] font-bold text-[var(--nq-accent)] underline decoration-dotted underline-offset-2"
                    title={`Bài gốc: ${it.post_id} · bình luận: ${it.external_thread_id ?? ""}`}
                  >
                    Xem bài gốc ↗
                  </a>
                ) : null}
              </div>
              <p className="mb-2 text-[11px] text-[var(--nq-dim)]">
                {INTENT_LABEL[it.detected_intent] ?? safeText(it.detected_intent)}
                {it.source === "comment" ? " · bình luận trên bài viết/ảnh Page" : " · tin nhắn Messenger"}
              </p>
              <div className="mb-2">
                <Confidence value={it.confidence} />
              </div>

              <p className="text-[var(--nq-fg)] mb-3 whitespace-pre-wrap break-words text-[15px] leading-relaxed">
                {safeText(it.message_text)}
              </p>

              {it.proposed_response ? (
                <div className="mb-3 rounded-r border-l-4 border-[var(--nq-accent)] bg-[var(--nq-bg)] px-3 py-2">
                  <p className="text-xs font-mono uppercase tracking-widest text-[var(--nq-dim)] mb-1">
                    Bản nháp của agent
                  </p>
                  <p className="text-[var(--nq-fg)] text-sm whitespace-pre-wrap break-words">
                    {safeText(it.proposed_response)}
                  </p>
                </div>
              ) : null}

              {Array.isArray(it.flagged_reasons) && it.flagged_reasons.length > 0 ? (
                <p className="mb-2 text-xs text-[var(--nq-st-warn-ink)]">
                  Cờ kiểm duyệt: {it.flagged_reasons.join(", ")}
                </p>
              ) : null}

              {/* Cảm xúc + hướng xử lý comment — gộp 1 dòng, không chiếm cả hộp */}
              {it.source === "comment" && (it.sentiment || it.comment_action) ? (
                <p className="mb-2 text-xs text-[var(--nq-dim)]">
                  {it.sentiment ? (
                    <>
                      Cảm xúc:{" "}
                      <strong>
                        {it.sentiment.sentiment === "positive" ? "Tích cực" :
                         it.sentiment.sentiment === "negative" ? "Tiêu cực" : "Trung tính"}
                      </strong>
                      {Array.isArray(it.sentiment.keywords_found) && it.sentiment.keywords_found.length > 0 ? (
                        <> · từ khóa: {it.sentiment.keywords_found.slice(0, 5).join(", ")}</>
                      ) : null}
                      {it.comment_action ? " · " : null}
                    </>
                  ) : null}
                  {it.comment_action ? (
                    <>Xử lý: <strong>{commentActionLabel(it.comment_action)}</strong></>
                  ) : null}
                </p>
              ) : null}

              {/* Đính kèm — gộp 1 dòng */}
              {it.attachment_type && it.attachment_type !== "unknown" ? (
                <p className="mb-2 text-xs text-[var(--nq-dim)]">
                  Đính kèm: <strong>{attachmentLabel(it.attachment_type)}</strong>
                  {it.attachment_url ? (
                    <>
                      {" · "}
                      <a
                        href={it.attachment_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[var(--nq-accent)] underline"
                      >
                        Xem đính kèm
                      </a>
                    </>
                  ) : null}
                </p>
              ) : null}

              {editing === it.id ? (
                <div className="mb-4">
                  <Field label="Sửa nội dung trước khi gửi">
                    <Textarea
                      value={draft}
                      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDraft(e.target.value)}
                      rows={3}
                    />
                  </Field>
                  <div className="flex gap-3 mt-3">
                    <Btn
                      onClick={() => decide(it, "sua_gui", draft)}
                      busy={busy === it.id}
                      disabled={!draft.trim()}
                    >
                      Gửi bản đã sửa
                    </Btn>
                    <Btn variant="ghost" onClick={() => { setEditing(null); setDraft(""); }}>
                      Hủy
                    </Btn>
                  </div>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-3">
                <Btn
                  disabled={!canAct}
                  busy={busy === it.id}
                  onClick={() => decide(it, "duyet")}
                  title={it.proposed_response ? "Gửi đúng bản nháp" : "Cần bản nháp để duyệt"}
                >
                  Duyệt &amp; gửi
                </Btn>
                <Btn
                  variant="ghost"
                  disabled={!canAct || !it.proposed_response}
                  onClick={() => { setEditing(it.id); setDraft(it.proposed_response ?? ""); }}
                >
                  Sửa rồi gửi
                </Btn>
                <Btn
                  variant="danger"
                  disabled={!canAct}
                  onClick={() => decide(it, "tu_choi", undefined, "Từ chối khi duyệt")}
                >
                  Từ chối
                </Btn>
                {it.assigned_role !== "chu_quan" ? (
                  <Btn
                    variant="ghost"
                    disabled={!canAct}
                    onClick={() => decide(it, "chuyen_cap", undefined, "Chuyển chủ quán duyệt")}
                    title="Chuyển mục này lên chủ quán duyệt"
                  >
                    Chuyển chủ quán
                  </Btn>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
          </>
        );
      })()}
    </div>
  );
}

function StatCell({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="nq-surface-row bg-[var(--nq-surface)] p-4 block">
      <p className="text-xs font-mono uppercase tracking-widest text-[var(--nq-dim)] mb-1">{label}</p>
      <p className={`tabular-nums text-3xl font-semibold ${danger ? "text-[var(--nq-red)]" : "text-[var(--nq-fg)]"}`}>{value}</p>
    </div>
  );
}
