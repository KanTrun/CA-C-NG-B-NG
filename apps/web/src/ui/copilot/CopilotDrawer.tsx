"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { getToken } from "../../lib/session";
import { beat } from "../../lib/motion";
import { ActionProposalCard, ActionProposalData } from "./ActionProposalCard";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ChatMessage {
  id: string;
  sender: "user" | "copilot";
  text: string;
  action_proposal?: ActionProposalData | null;
  citations?: string[] | null;
  timestamp: string;
}

const QUICK_PROMPTS = [
  "Xếp lịch tuần sau, ưu tiên Lan ca sáng",
  "Tóm tắt bản tin sáng hôm nay",
  "Kiểm tra tồn kho và cảnh báo hết hàng",
  "Quy trình mở quán gồm các bước nào?",
  "Báo cáo hao hụt sữa hôm nay",
];

const STORAGE_KEY = "ag_copilot_history_v1";
const MAX_HISTORY = 200;
const TYPING_CHARS_PER_TICK = 2; // số ký tự / 30ms — mô phỏng streaming
const TYPING_TICK_MS = 30;

function loadHistory(): ChatMessage[] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ChatMessage[];
    if (!Array.isArray(parsed)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveHistory(messages: ChatMessage[]) {
  if (typeof window === "undefined") return;
  try {
    const trimmed = messages.slice(-MAX_HISTORY);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // hết quota hoặc bị chặn — bỏ qua, không vỡ UI
  }
}

const WELCOME_MSG: ChatMessage = {
  id: "welcome",
  sender: "copilot",
  text: "Xin chào! Em là AG-COPILOT — Trợ lý điều hành ảo của quán. Anh/chị cần em hỗ trợ xếp lịch, duyệt ca hay kiểm tra vận hành gì ạ? (Bấm Ctrl+K để mở/đóng, Esc để thoát)",
  timestamp: "Bây giờ",
};

interface CopilotDrawerProps {
  /** Controlled mode — nếu truyền, drawer dùng giá trị này thay vì tự quản lý. */
  open?: boolean;
  /** Controlled mode — callback khi đóng (backdrop / Esc / nút ✕). */
  onClose?: () => void;
}

export function CopilotDrawer({ open, onClose }: CopilotDrawerProps = {}) {
  // Tôn trọng ý muốn giảm chuyển động: ngăn kéo vẫn mở/đóng và vẫn che nền,
  // chỉ bỏ phần trượt. Che nền là chức năng (chặn bấm xuyên xuống), không phải
  // trang trí, nên nó ở lại — chỉ chuyển động đi.
  const reduced = useReducedMotion() ?? false;
  const isControlled = open !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const isOpen = isControlled ? Boolean(open) : internalOpen;

  const setOpen = useCallback(
    (v: boolean | ((prev: boolean) => boolean)) => {
      if (isControlled) {
        // Trong controlled mode, chỉ phản hồi "đóng" lên parent.
        if (!v) onClose?.();
        return;
      }
      setInternalOpen((prev) => (typeof v === "function" ? v(prev) : v));
    },
    [isControlled, onClose]
  );

  const [inputMessage, setInputMessage] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MSG]);
  // Loại làm rõ của lượt gần nhất, đọc từ CỜ server gửi (`clarification_kind`).
  const [lastClarification, setLastClarification] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const typingTimers = useRef<Record<string, number>>({});

  // Khôi phục lịch sử từ localStorage khi mount
  useEffect(() => {
    const saved = loadHistory();
    if (saved && saved.length > 0) {
      setMessages(saved);
    }
    setHydrated(true);
  }, []);

  // Lưu lịch sử mỗi khi messages thay đổi (sau khi đã hydrate)
  useEffect(() => {
    if (!hydrated) return;
    saveHistory(messages);
  }, [messages, hydrated]);

  // Auto-scroll khi mở hoặc có tin nhắn mới
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen]);

  // Phím tắt: Ctrl/Cmd+K mở/đóng, Esc đóng
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isToggle = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k";
      if (isToggle) {
        e.preventDefault();
        // Controlled: chỉ cho phép mở (parent quyết đóng)
        if (isControlled) {
          if (!isOpen) onClose?.();
          return;
        }
        setOpen((v) => !v);
        return;
      }
      if (e.key === "Escape" && isOpen) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, isControlled, onClose, setOpen]);

  // Focus input khi mở drawer
  useEffect(() => {
    if (isOpen) {
      const t = window.setTimeout(() => inputRef.current?.focus(), 250);
      return () => window.clearTimeout(t);
    }
  }, [isOpen]);

  const clearHistory = useCallback(() => {
    if (typeof window === "undefined") return;
    const ok = window.confirm("Xoá toàn bộ lịch sử hội thoại với AG-COPILOT?");
    if (!ok) return;
    setMessages([WELCOME_MSG]);
  }, []);

  // Streaming "typing" cho 1 message: tách text theo ký tự rồi nạp dần
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

  useEffect(() => {
    return () => {
      // cleanup timers khi unmount
      Object.values(typingTimers.current).forEach((t) => window.clearTimeout(t));
      typingTimers.current = {};
    };
  }, []);

  async function handleSendMessage(textToSend?: string) {
    const text = (textToSend || inputMessage).trim();
    if (!text || loading || streamingId) return;

    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      sender: "user",
      text,
      timestamp: now,
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputMessage("");
    setLoading(true);

    // Tạo placeholder message cho copilot (text="") để typing effect có chỗ ghi vào
    const copilotId = `copilot_${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: copilotId, sender: "copilot", text: "", timestamp: now },
    ]);

    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/v1/copilot/message`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: text,
          channel: "web",
          recent_messages: messages.slice(-3).map((m) => m.text),
          // Lượt trước copilot hỏi lý do nghỉ → câu này là câu trả lời. Đọc CỜ
          // `clarification_kind` từ response, không so chuỗi trong reply_text.
          cho_phep_noi_ly_do: lastClarification === "thieu_ly_do",
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Không thể kết nối với AG-COPILOT");
      }

      const replyText: string =
        data.reply_text || "Dạ em đã xử lý xong yêu cầu của anh/chị.";
      setLastClarification(
        typeof data.clarification_kind === "string" ? data.clarification_kind : null,
      );
      const citations: string[] | null = Array.isArray(data.citations)
        ? data.citations
        : null;

      // Cập nhật action_proposal + citations cho message placeholder
      setMessages((prev) =>
        prev.map((m) =>
          m.id === copilotId
            ? { ...m, action_proposal: data.action_proposal ?? null, citations }
            : m
        )
      );

      // Bắt đầu typing
      startTyping(copilotId, replyText);
    } catch (err: any) {
      const errText = `⚠️ Lỗi: ${err.message || "Không thể xử lý yêu cầu."}`;
      // Nếu lỗi thì ghi thẳng, không cần typing
      setMessages((prev) =>
        prev.map((m) =>
          m.id === copilotId ? { ...m, text: errText } : m
        )
      );
    } finally {
      setLoading(false);
    }
  }

  function handleVoiceInput() {
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      alert("Trình duyệt không hỗ trợ nhận diện giọng nói (Web Speech API).");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRec();
      recognition.lang = "vi-VN";
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setInputMessage(transcript);
        }
      };

      recognition.start();
    } catch (e) {
      setIsListening(false);
    }
  }

  return (
    <>
      {/* Floating Trigger Button */}
      <button
        onClick={() => setOpen(!isOpen)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-2.5 rounded-full bg-[var(--nq-st-warn)] hover:brightness-110 text-[var(--nq-accent-ink)] font-bold shadow-[var(--nq-elev-4)] transition transform hover:scale-105 active:scale-95"
        title="Mở Trợ lý AG-COPILOT"
      >
        <span className="text-lg">✨</span>
        <span className="text-sm font-semibold tracking-wide">AG-COPILOT</span>
      </button>

      {/* Drawer Overlay & Panel */}
      <AnimatePresence>
        {isOpen && (
          <div className="fixed inset-0 z-50 flex justify-end pointer-events-none">
            {/* Backdrop */}
            <motion.div
              initial={reduced ? {} : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={reduced ? {} : { opacity: 0 }}
              transition={beat("settle")}
              onClick={() => setOpen(false)}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm pointer-events-auto"
            />

            {/* Chat Drawer */}
            <motion.div
              initial={reduced ? {} : { x: "100%" }}
              animate={{ x: 0 }}
              exit={reduced ? {} : { x: "100%" }}
              transition={beat("focus")}
              className="relative w-full md:max-w-md bg-[var(--nq-bg)] md:border-l border-[var(--nq-line)] shadow-2xl flex flex-col h-full pointer-events-auto"
            >
              {/* Header */}
              <div className="flex items-center justify-between p-4 border-b border-[var(--nq-line)] bg-[var(--nq-bg-elevated)]">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-[var(--nq-st-warn-soft)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] flex items-center justify-center text-[var(--nq-st-warn-ink)] font-bold text-sm">
                    ✨
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--nq-ink)]">AG-COPILOT</h3>
                    <p className="text-2xs text-[var(--nq-st-ok-ink)] flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--nq-st-ok)]"></span>{" "}
                      Trực tuyến · Điều hành 1-Click
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={clearHistory}
                    title="Xoá lịch sử hội thoại"
                    className="p-1.5 rounded-lg text-[var(--nq-ink-muted)] hover:text-[var(--nq-st-danger-ink)] hover:bg-[var(--nq-surface)] transition text-xs"
                  >
                    🗑
                  </button>
                  <button
                    onClick={() => setOpen(false)}
                    title="Đóng (Esc)"
                    className="p-1.5 rounded-lg text-[var(--nq-ink-muted)] hover:text-[var(--nq-ink)] hover:bg-[var(--nq-surface)] transition text-sm"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {/* Messages Body */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
                  >
                    <div
                      className={`max-w-[85%] p-3 rounded-2xl ${
                        msg.sender === "user"
                          ? "bg-[var(--nq-st-warn)] text-[var(--nq-accent-ink)] rounded-br-none"
                          : "bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] text-[var(--nq-ink)] rounded-bl-none"
                      }`}
                    >
                      <p className="whitespace-pre-wrap leading-relaxed">
                        {msg.text}
                        {streamingId === msg.id && (
                          <span className="ml-0.5 inline-block w-1.5 h-3 align-middle bg-[var(--nq-st-warn)] animate-pulse" />
                        )}
                      </p>

                      {/* Citation/nguồn trích dẫn — slot sẵn, render nếu có */}
                      {msg.sender === "copilot" &&
                        msg.citations &&
                        msg.citations.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-[var(--nq-line)]">
                            <p className="text-2xs uppercase tracking-wider text-[var(--nq-ink-muted)] mb-1">
                              Nguồn tham chiếu
                            </p>
                            <ul className="flex flex-wrap gap-1">
                              {msg.citations.map((c, i) => (
                                <li
                                  key={`${msg.id}-cit-${i}`}
                                  className="text-2xs px-1.5 py-0.5 rounded bg-[var(--nq-surface)] text-[var(--nq-st-warn-ink)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))]"
                                >
                                  📎 {c}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                      {msg.action_proposal && (
                        <ActionProposalCard
                          proposal={msg.action_proposal}
                          onExecuted={(updated) => {
                            setMessages((prev) =>
                              prev.map((m) =>
                                m.id === msg.id ? { ...m, action_proposal: updated } : m
                              )
                            );
                          }}
                        />
                      )}
                    </div>
                    <span className="text-2xs text-[var(--nq-ink-muted)] mt-1 px-1">{msg.timestamp}</span>
                  </div>
                ))}
                {loading && (
                  <div className="flex items-center gap-2 text-[var(--nq-ink-muted)] text-xs italic bg-[var(--nq-bg-elevated)] p-2 rounded-xl border border-[var(--nq-line)] w-fit">
                    <span className="animate-spin text-[var(--nq-st-warn-ink)]">⏳</span> AG-COPILOT đang suy nghĩ và kiểm tra solver...
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Quick Prompts */}
              <div className="px-4 py-2 border-t border-[var(--nq-line)] bg-[var(--nq-bg-elevated)] overflow-x-auto flex gap-1.5 no-scrollbar">
                {QUICK_PROMPTS.map((qp, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(qp)}
                    disabled={loading || Boolean(streamingId)}
                    className="whitespace-nowrap text-2xs px-2.5 py-1 rounded-full bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] text-[var(--nq-ink-muted)] hover:text-[var(--nq-st-warn-ink)] hover:border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] transition disabled:opacity-50"
                  >
                    {qp}
                  </button>
                ))}
              </div>

              {/* Input Footer */}
              <div className="p-3 border-t border-[var(--nq-line)] bg-[var(--nq-bg-elevated)]">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSendMessage();
                  }}
                  className="flex items-center gap-2"
                >
                  <input
                    ref={inputRef}
                    type="text"
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    placeholder="Nhập lệnh hoặc hỏi quy trình..."
                    disabled={loading || Boolean(streamingId)}
                    className="flex-1 px-3.5 py-2 text-xs bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] rounded-xl text-[var(--nq-ink)] placeholder-zinc-500 focus:outline-none focus:border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] disabled:opacity-50"
                  />
                  <button
                    type="button"
                    onClick={handleVoiceInput}
                    title="Nhập bằng giọng nói"
                    className={`p-2 rounded-xl border transition ${
                      isListening
                        ? "bg-[var(--nq-st-danger)] text-[var(--nq-accent-ink)] border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] animate-pulse"
                        : "bg-[var(--nq-surface)] hover:bg-[var(--nq-line)] text-[var(--nq-ink)] border-[var(--nq-line)]"
                    }`}
                  >
                    🎙️
                  </button>
                  <button
                    type="submit"
                    disabled={loading || Boolean(streamingId) || !inputMessage.trim()}
                    className="px-3.5 py-2 rounded-xl bg-[var(--nq-st-warn)] hover:bg-[var(--nq-st-warn)] text-[var(--nq-accent-ink)] font-semibold text-xs transition disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Gửi
                  </button>
                </form>
                <p className="mt-1.5 text-2xs text-[var(--nq-ink-muted)] text-center">
                  Ctrl/Cmd+K mở·đóng · Esc thoát
                </p>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
