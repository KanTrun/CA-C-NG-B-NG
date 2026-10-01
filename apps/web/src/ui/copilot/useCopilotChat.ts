// Logic chat chung cho cả Drawer (pane) và /copilot page.
// Tách ra để 2 nơi cùng dùng: role-aware, streaming, history, action proposal.

import { useCallback, useEffect, useRef, useState } from "react";
import { getNvId, getRole, getToken } from "../../lib/session";
import { getCopilotProfile } from "./profile";
import type { ActionProposalData } from "./ActionProposalCard";

export interface ChatAttachment {
  url: string;
  filename: string;
  mime_type?: string;
  size?: number;
  upload_id?: string;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "copilot";
  text: string;
  attachments?: ChatAttachment[];
  action_proposal?: ActionProposalData | null;
  citations?: string[] | null;
  agent_mode?: string | null;
  /**
   * Trạng thái đang xử lý ("Đang tra cứu dữ liệu…") — hiện trong bong bóng khi
   * chưa có chữ nào. Có nó thì người dùng biết trợ lý ĐANG làm việc, thay vì
   * nhìn bong bóng trống và tưởng nó im lặng không trả lời được.
   */
  pending_status?: string | null;
  timestamp: string;
}

export type Mode = "pane" | "page";

const STORAGE_KEY = "ag_copilot_history_v1";
const MAX_HISTORY = 200;
const TYPING_CHARS_PER_TICK = 2;
const TYPING_TICK_MS = 30;
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Text-based Approval Detection (Fix #1) ───────────────────────────────────
// Khi người dùng nhắn một trong các cụm dưới đây VÀ có ActionProposal đang
// chờ duyệt trong lịch sử chat → tự động gọi execute-action thay vì gửi AI.
const APPROVAL_KEYWORDS = new Set([
  // Tiếng Việt phổ biến
  "duyệt", "duyet", "duyệt đi", "duyet di", "duyệt nha", "duyet nha",
  "duyệt nhé", "duyet nhe", "duyệt luôn", "duyet luon",
  "đồng ý", "dong y", "đồng ý nhé", "dong y nhe", "đồng ý nha", "dong y nha",
  "chấp thuận", "chap thuan",
  "xác nhận", "xac nhan", "xác nhận nha", "xac nhan nha",
  "ok", "oke", "ok đi", "oke đi", "ok luôn", "oke luôn",
  "ok em", "oke em", "ok nha", "oke nha", "ok nhé", "oke nhé",
  "ừ duyệt", "u duyet", "ừ", "u",
  "vâng", "vang", "vâng duyệt", "vang duyet",
  "thì duyệt đi", "thi duyet di",
  "cho duyệt", "cho duyet",
  "làm đi", "lam di",
  // Tiếng Anh
  "approve", "yes", "confirm",
]);

const REJECT_KEYWORDS = new Set([
  "từ chối", "tu choi", "không duyệt", "khong duyet",
  "hủy", "huy", "hủy đi", "huy di",
  "thôi", "thoi", "bỏ", "bo",
  "không", "khong", "không cần", "khong can",
  "không làm nữa", "khong lam nua",
  "reject", "no", "cancel",
]);

/**
 * Tìm ActionProposal đang chờ duyệt gần nhất trong lịch sử chat.
 * Trả về { msgId, proposal } hoặc null nếu không có.
 */
function findPendingProposal(
  messages: ChatMessage[]
): { msgId: string; proposal: ActionProposalData } | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (
      msg.sender === "copilot" &&
      msg.action_proposal &&
      (msg.action_proposal.status === "ready_for_approval" ||
        msg.action_proposal.status === "amendment_ready")
    ) {
      return { msgId: msg.id, proposal: msg.action_proposal };
    }
  }
  return null;
}


// Mỗi nhân viên có lịch sử riêng; không đọc khóa chung cũ để tránh lộ hội thoại.
function storageKey(mode: Mode, nvId: string): string | null {
  const employeeId = nvId.trim();
  return employeeId ? `${STORAGE_KEY}_${employeeId}_${mode}` : null;
}

function loadHistory(mode: Mode, nvId: string): ChatMessage[] | null {
  if (typeof window === "undefined") return null;
  const key = storageKey(mode, nvId);
  if (!key) return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ChatMessage[];
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function saveHistory(messages: ChatMessage[], mode: Mode, nvId: string) {
  if (typeof window === "undefined") return;
  const key = storageKey(mode, nvId);
  if (!key) return;
  try {
    window.localStorage.setItem(
      key,
      JSON.stringify(messages.slice(-MAX_HISTORY))
    );
  } catch {
    /* quota / blocked — bỏ qua */
  }
}

export function useCopilotChat(mode: Mode = "pane") {
  const profile = getCopilotProfile(getRole() as any);
  const nvId = getNvId();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      sender: "copilot",
      text: profile.greeting,
      timestamp: "Bây giờ",
    },
  ]);
  const [hydrated, setHydrated] = useState(false);
  const [hydratedStorageKey, setHydratedStorageKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const typingTimers = useRef<Record<string, number>>({});
  const messagesRef = useRef<ChatMessage[]>(messages);
  // Loại làm rõ của lượt gần nhất ("thieu_ly_do" | "thieu_thu" | …). Lưu theo
  // CỜ do server gửi, không so chuỗi trong `reply_text`.
  const clarifRef = useRef<string | null>(null);

  // Cập nhật ref mỗi render để handleSendMessage có state mới nhất
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Khôi phục lịch sử
  useEffect(() => {
    Object.values(typingTimers.current).forEach((timer) => window.clearTimeout(timer));
    typingTimers.current = {};
    setHydrated(false);
    setHydratedStorageKey(null);
    const saved = loadHistory(mode, nvId);
    setMessages(saved && saved.length > 0 ? saved : [{
      id: "welcome",
      sender: "copilot",
      text: profile.greeting,
      timestamp: "Bây giờ",
    }]);
    setLoading(false);
    setStreamingId(null);
    setHydratedStorageKey(storageKey(mode, nvId));
    setHydrated(true);
  }, [mode, nvId, profile.greeting]);

  // Lưu lịch sử
  useEffect(() => {
    if (!hydrated || hydratedStorageKey !== storageKey(mode, nvId)) return;
    saveHistory(messages, mode, nvId);
  }, [messages, hydrated, hydratedStorageKey, mode, nvId]);

  // Cleanup timers khi unmount
  useEffect(() => {
    const timers = typingTimers.current;
    return () => {
      Object.values(timers).forEach((t) => window.clearTimeout(t));
      Object.keys(timers).forEach((k) => delete timers[k]);
    };
  }, []);

  const startTyping = useCallback((msgId: string, fullText: string) => {
    setStreamingId(msgId);
    const chars = Array.from(fullText);
    let i = 0;
    const tick = () => {
      i = Math.min(chars.length, i + TYPING_CHARS_PER_TICK);
      const partial = chars.slice(0, i).join("");
      setMessages((prev) =>
        prev.map((m) => (m.id === msgId ? { ...m, text: partial } : m))
      );
      if (i < chars.length) {
        typingTimers.current[msgId] = window.setTimeout(tick, TYPING_TICK_MS);
      } else {
        setStreamingId((cur) => (cur === msgId ? null : cur));
        delete typingTimers.current[msgId];
      }
    };
    typingTimers.current[msgId] = window.setTimeout(tick, TYPING_TICK_MS);
  }, []);

  const uploadAttachment = useCallback(async (file: File): Promise<ChatAttachment> => {
    const formData = new FormData();
    formData.append("file", file);
    const token = getToken();
    const res = await fetch(`${API_BASE}/api/v1/copilot/upload`, {
      method: "POST",
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Lỗi tải tệp lên");
    }
    const data = await res.json();
    const rawUrl = data.url || "";
    const fullUrl = rawUrl.startsWith("http")
      ? rawUrl
      : `${API_BASE}${rawUrl.startsWith("/") ? "" : "/"}${rawUrl}`;
    return {
      url: fullUrl,
      filename: data.filename || file.name,
      mime_type: data.mime_type || file.type,
      size: data.size || file.size,
      upload_id: data.upload_id,
    };
  }, []);

  const send = useCallback(
    async (textToSend?: string, attachmentsToSend?: ChatAttachment[]) => {
      const text = (textToSend ?? input).trim();
      const attachments = attachmentsToSend && attachmentsToSend.length > 0 ? attachmentsToSend : undefined;
      if ((!text && !attachments) || loading || streamingId) return;

      const now = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      const userMsg: ChatMessage = {
        id: `user_${Date.now()}`,
        sender: "user",
        text,
        attachments,
        timestamp: now,
      };

      setMessages((prev) => [...prev, userMsg]);
      if (!textToSend) setInput("");
      setLoading(true);

      // ── Text-based Approval (Fix #1) ──────────────────────────────────────
      // Kiểm tra tin nhắn có phải lệnh duyệt/từ chối không. Nếu có pending
      // proposal → tự động gọi execute-action, không gửi lên AI.
      const normalizedText = text.toLowerCase().trim();
      const pendingResult = findPendingProposal(messagesRef.current);

      if (pendingResult && !attachments) {
        const isApprove = APPROVAL_KEYWORDS.has(normalizedText);
        const isReject = REJECT_KEYWORDS.has(normalizedText);

        if (isApprove || isReject) {
          const decision = isApprove ? "approve" : "reject";
          const copilotId = `copilot_${Date.now()}`;
          setMessages((prev) => [
            ...prev,
            { id: copilotId, sender: "copilot", text: "⏳ Đang xử lý...", timestamp: now },
          ]);

          try {
            const token = getToken();
            const idempotencyKey = `${decision}_${pendingResult.proposal.action_id}_${Date.now()}`;
            const res = await fetch(`${API_BASE}/api/v1/copilot/execute-action`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({
                action_id: pendingResult.proposal.action_id,
                decision,
                idempotency_key: idempotencyKey,
              }),
            });

            const data = await res.json();
            let replyText: string;
            let updatedProposal: ActionProposalData = {
              ...pendingResult.proposal,
              status: "executed",
            };

            if (res.ok && data.ok) {
              if (decision === "approve") {
                replyText = `✅ Dạ em đã duyệt xong rồi ạ! ${data.message || "Hành động đã được thực thi thành công."}`
                  + (data.result_link ? ` Anh/chị xem kết quả tại **${data.result_link}** nhé!` : "");
              } else {
                replyText = "✅ Dạ em đã hủy đề xuất theo yêu cầu của anh/chị rồi ạ!";
                updatedProposal = { ...pendingResult.proposal, status: "rejected" };
              }
            } else {
              const detail = String(data.detail || "");
              if (detail.includes("stale_rejected")) {
                replyText = "⚠️ Dữ liệu đã bị thay đổi trước khi anh/chị duyệt. Anh/chị yêu cầu lại để em tạo đề xuất mới nhé!";
                updatedProposal = { ...pendingResult.proposal, status: "stale_rejected" };
              } else if (detail.includes("expired")) {
                replyText = "⚠️ Đề xuất đã hết hạn rồi ạ. Anh/chị nhắn lại lệnh để em tạo đề xuất mới nhé!";
                updatedProposal = { ...pendingResult.proposal, status: "expired" };
              } else {
                replyText = `⚠️ Có lỗi xảy ra: ${data.detail || "Không thể thực thi. Anh/chị thử bấm nút trực tiếp trên thẻ đề xuất nhé!"}`;
                updatedProposal = { ...pendingResult.proposal };
              }
            }

            // Cập nhật trạng thái proposal trong message cũ
            setMessages((prev) =>
              prev.map((m) =>
                m.id === pendingResult.msgId
                  ? { ...m, action_proposal: updatedProposal }
                  : m.id === copilotId
                  ? { ...m, text: replyText }
                  : m
              )
            );
          } catch (err: any) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === copilotId
                  ? { ...m, text: `⚠️ Lỗi kết nối: ${err.message || "Không thể thực thi. Anh/chị thử bấm nút trên thẻ đề xuất nhé!"}` }
                  : m
              )
            );
          } finally {
            setLoading(false);
          }
          return; // Không gọi AI sau khi đã xử lý approval
        }
      }
      // ─────────────────────────────────────────────────────────────────────

      const copilotId = `copilot_${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        { id: copilotId, sender: "copilot", text: "", timestamp: now },
      ]);

      try {
        const token = getToken();
        // Chỉ lấy tin của NGƯỜI DÙNG: `recent_messages` là ngữ cảnh để agent
        // hiểu câu lệnh trước, tin của copilot không phải lệnh của NV.
        const ganDay = messagesRef.current.filter((m) => m.sender === "user");
        const recent = ganDay.slice(-3).map((m) => m.text);
        // Lượt trước copilot đã hỏi "lý do xin nghỉ là gì?" → câu này là câu TRẢ
        // LỜI. Dùng cờ `clarification_kind` từ response thay vì so chuỗi trong
        // `reply_text`: đổi câu chữ là hỏng ngay, và không phân biệt được
        // "hỏi lý do" với các câu hỏi làm rõ khác.
        const choPhepNoiLyDo = clarifRef.current === "thieu_ly_do";
        const payload = JSON.stringify({
          message: text,
          channel: mode === "page" ? "web-page" : "web",
          recent_messages: recent,
          cho_phep_noi_ly_do: choPhepNoiLyDo,
          attachments: attachments || [],
        });

        // Ưu tiên SSE streaming; nếu thất bại fallback về POST /message (JSON).
        const streamed = await streamCopilot(
          payload,
          token,
          (delta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === copilotId
                  ? { ...m, text: (m.text || "") + delta, pending_status: null }
                  : m
              )
            );
          },
          (status) => {
            // Trạng thái "đang tra cứu" — hiện trong bong bóng cho tới khi có chữ.
            setMessages((prev) =>
              prev.map((m) =>
                m.id === copilotId && !m.text ? { ...m, pending_status: status } : m
              )
            );
          }
        );

        if (streamed.ok) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === copilotId
                ? {
                    ...m,
                    action_proposal: streamed.action_proposal ?? null,
                    citations: streamed.citations,
                    agent_mode: streamed.agent_mode ?? null,
                  }
                : m
            )
          );
          return;
        }

        // Fallback: POST /message (không stream).
        const res = await fetch(`${API_BASE}/api/v1/copilot/message`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: payload,
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Không thể kết nối với trợ lý vận hành");
        }

        const replyText: string =
          data.reply_text || "Dạ em đã xử lý xong yêu cầu của anh/chị.";
        const citations: string[] | null = Array.isArray(data.citations)
          ? data.citations
          : null;
        clarifRef.current =
          typeof data.clarification_kind === "string"
            ? data.clarification_kind
            : null;

        setMessages((prev) =>
          prev.map((m) =>
            m.id === copilotId
              ? {
                  ...m,
                  action_proposal: data.action_proposal ?? null,
                  citations,
                  agent_mode: data.agent_mode ?? null,
                }
              : m
          )
        );

        startTyping(copilotId, replyText);
      } catch (err: any) {
        const errText = `⚠️ Lỗi: ${err.message || "Không thể xử lý yêu cầu."}`;
        setMessages((prev) =>
          prev.map((m) => (m.id === copilotId ? { ...m, text: errText } : m))
        );
      } finally {
        setLoading(false);
      }
    },
    [input, loading, streamingId, mode, startTyping]
  );

  const clearHistory = useCallback(() => {
    if (typeof window === "undefined") return;
    const ok = window.confirm("Xoá toàn bộ lịch sử hội thoại với trợ lý vận hành?");
    if (!ok) return;
    const key = storageKey(mode, nvId);
    if (key) window.localStorage.removeItem(key);
    setMessages([
      {
        id: "welcome",
        sender: "copilot",
        text: profile.greeting,
        timestamp: "Bây giờ",
      },
    ]);
  }, [mode, nvId, profile.greeting]);

  const updateProposal = useCallback(
    (msgId: string, updated: ActionProposalData) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, action_proposal: updated } : m
        )
      );
    },
    []
  );

  return {
    profile,
    messages,
    setMessages,
    input,
    setInput,
    loading,
    streamingId,
    send,
    uploadAttachment,
    clearHistory,
    updateProposal,
  };
}

// ── SSE streaming helper ────────────────────────────────────────────────────
interface StreamResult {
  ok: boolean;
  action_proposal?: ActionProposalData | null;
  citations?: string[] | null;
  agent_mode?: string | null;
}

/** Đọc SSE từ /api/v1/copilot/message/stream và gọi onDelta cho từng chunk text. */
async function streamCopilot(
  payload: string,
  token: string,
  onDelta: (delta: string) => void,
  onStatus?: (status: string) => void
): Promise<StreamResult> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/copilot/message/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: payload,
    });

    if (!res.ok || !res.body) {
      return { ok: false };
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let meta: { action_proposal?: ActionProposalData | null; citations?: string[] | null; agent_mode?: string | null } = {};

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Mỗi event SSE kết thúc bằng "\n\n".
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const lines = rawEvent.split("\n");
        let eventName = "message";
        for (const line of lines) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) {
            const dataStr = line.slice(5).trim();
            try {
              const data = JSON.parse(dataStr);
              if (eventName === "meta") {
                clarifRef.current =
                  typeof data.clarification_kind === "string"
                    ? data.clarification_kind
                    : null;
                meta = {
                  action_proposal: data.action_proposal ?? null,
                  citations: Array.isArray(data.citations) ? data.citations : null,
                  agent_mode: data.agent_mode ?? null,
                };
              } else if (eventName === "status") {
                // Server báo đang tra cứu TRƯỚC khi có chữ → UI hết khoảng lặng.
                if (onStatus && typeof data.message === "string") onStatus(data.message);
              } else if (eventName === "delta") {
                onDelta(data.text || "");
              }
            } catch {
              /* bỏ qua chunk không parse được */
            }
          }
        }
      }
    }
    return { ok: true, ...meta };
  } catch {
    return { ok: false };
  }
}