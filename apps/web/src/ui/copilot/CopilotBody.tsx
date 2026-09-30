// UI body chat (header + messages + quick prompts + input) dùng chung cho
// CopilotPane (floating) và trang /copilot (full-page).
//
// Props:
//  - chat: state từ useCopilotChat
//  - onClose?: callback cho header nút ✕ (pane)
//  - onOpenFullPage?: callback mở /copilot trong tab/cửa sổ mới (pane)
//  - showHeaderAccent: true = pane (có nút expand), false = page (chỉ header)

"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { chatSounds } from "../../lib/chat-sound";
import { ActionProposalCard } from "./ActionProposalCard";
import { Avatar2D, type AvatarMood } from "./Avatar2D";
import { ChatText } from "./ChatText";
import type { ChatMessage, Mode } from "./useCopilotChat";
import { useCopilotVoice, type VoiceInputMode, type VoiceState } from "./useCopilotVoice";
import { useAvatarLipSync } from "./useAvatarLipSync";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const VOICE_ENABLED = process.env.NEXT_PUBLIC_GEMINI_LIVE_VOICE_ENABLED !== "false";
const VOICE_CONSENT_KEY = "ag_voice_consent_v1";
const VOICE_MODE_KEY = "ag_voice_input_mode";
const VOICE_MIC_KEY = "ag_voice_mic_device_id";
const VOICE_TOGGLE_KEY = "ag_voice_enabled_v1";

function resolveMediaUrl(url: string): string {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("blob:")) {
    return url;
  }
  return `${API_BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}

interface Props {
  chat: ReturnType<typeof import("./useCopilotChat").useCopilotChat>;
  mode: Mode;
  onClose?: () => void;
  onOpenFullPage?: () => void;
  onClearHistory?: () => void;
}

export function CopilotBody({ chat, mode, onClose, onOpenFullPage, onClearHistory }: Props) {
  const {
    profile,
    messages,
    setMessages,
    input,
    setInput,
    loading,
    streamingId,
    send,
    uploadAttachment,
    updateProposal,
    clearHistory,
  } = chat;

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeVoiceTurnRef = useRef<{ id: string; role: "user" | "copilot" } | null>(null);
  // Khi nhận voice:proposal (reply + ActionProposal từ pipeline), bỏ qua
  // outputAudioTranscription tiếp theo của Gemini để tránh tin nhắn copilot
  // trùng lặp (một từ proposal, một từ transcript audio).
  const skipNextCopilotTranscriptRef = useRef(false);
  const [showConsentModal, setShowConsentModal] = useState(false);
  const [voiceMode, setVoiceMode] = useState<VoiceInputMode>("open_mic");
  const [selectedMicId, setSelectedMicId] = useState<string>("");
  const [voiceEnabled, setVoiceEnabled] = useState<boolean>(VOICE_ENABLED);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  useEffect(() => {
    try {
      const savedMode = window.localStorage.getItem(VOICE_MODE_KEY);
      if (savedMode === "open_mic" || savedMode === "push_to_talk") {
        setVoiceMode(savedMode);
      }
      const savedMic = window.localStorage.getItem(VOICE_MIC_KEY);
      if (savedMic) {
        setSelectedMicId(savedMic);
      }
      const savedToggle = window.localStorage.getItem(VOICE_TOGGLE_KEY);
      if (savedToggle === "true" || savedToggle === "false") {
        setVoiceEnabled(savedToggle === "true");
      }
    } catch {}
  }, []);

  const handleVoiceToggleEnabled = () => {
    setVoiceEnabled((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(VOICE_TOGGLE_KEY, String(next));
      } catch {}
      if (!next && isVoiceActive) {
        voice.stop();
        activeVoiceTurnRef.current = null;
      }
      return next;
    });
  };

  const handleTranscript = useCallback(
    (role: "user" | "copilot", chunk: string, isFinal: boolean) => {
      if (!chunk.trim()) return;
      // Bỏ qua transcript copilot của reply đã hiển thị qua voice:proposal.
      if (role === "copilot" && skipNextCopilotTranscriptRef.current) {
        if (isFinal) skipNextCopilotTranscriptRef.current = false;
        return;
      }
      const now = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });

      setMessages((prev) => {
        const active = activeVoiceTurnRef.current;
        if (active && active.role === role) {
          const updated = prev.map((m) => {
            if (m.id === active.id) {
              const currentText = m.text || "";
              const nextText = currentText
                ? (chunk.startsWith(" ") || currentText.endsWith(" ") ? currentText + chunk : currentText + " " + chunk)
                : chunk;
              return {
                ...m,
                text: nextText,
              };
            }
            return m;
          });
          if (isFinal) {
            activeVoiceTurnRef.current = null;
          }
          return updated;
        } else {
          const newId = `voice_${role}_${Date.now()}`;
          if (!isFinal) {
            activeVoiceTurnRef.current = { id: newId, role };
          } else {
            activeVoiceTurnRef.current = null;
          }
          const newMsg: ChatMessage = {
            id: newId,
            sender: role,
            text: chunk.trim(),
            agent_mode: role === "copilot" ? "live" : undefined,
            timestamp: now,
          };
          return [...prev, newMsg];
        }
      });
    },
    [setMessages]
  );

  const handleInterrupted = useCallback(() => {
    activeVoiceTurnRef.current = null;
  }, []);

  const handleVoiceProposal = useCallback(
    (data: import("./useCopilotVoice").VoiceProposalData) => {
      if (!data.reply_text.trim()) return;
      const now = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      const newId = `voice_proposal_${Date.now()}`;
      const newMsg: ChatMessage = {
        id: newId,
        sender: "copilot",
        text: data.reply_text,
        action_proposal: data.action_proposal ?? null,
        citations: data.citations?.length ? data.citations : null,
        agent_mode: data.agent_mode || "live",
        timestamp: now,
      };
      setMessages((prev) => [...prev, newMsg]);
      // Đánh dấu bỏ qua transcript copilot tiếp theo (audio của reply này).
      skipNextCopilotTranscriptRef.current = true;
    },
    [setMessages]
  );

  const voice = useCopilotVoice({
    onTranscript: handleTranscript,
    onInterrupted: handleInterrupted,
    onProposal: handleVoiceProposal,
    inputMode: voiceMode,
    deviceId: selectedMicId || undefined,
  });

  // Lip-sync avatar: mức mở miệng theo amplitude audio trợ lý đang phát.
  const isSpeaking = voice.state === "speaking";
  const isListening = voice.state === "listening";
  const mouthOpen = useAvatarLipSync(voice.audioLevel, isSpeaking);

  // Phản hồi âm thanh khi trạng thái voice thay đổi:
  // - Bắt đầu nghe → bíp nhẹ (báo micro đã mở).
  // - Trả lời xong (speaking → listening) → ting nhẹ (báo đã nghe xong).
  const prevVoiceStateRef = useRef<VoiceState | null>(null);
  useEffect(() => {
    const prev = prevVoiceStateRef.current;
    prevVoiceStateRef.current = voice.state;
    if (prev === voice.state) return;
    if (voice.state === "listening" && prev === "speaking") {
      chatSounds.playVoiceEnd();
    } else if (voice.state === "listening" && (prev === "idle" || prev === "connecting")) {
      chatSounds.playVoiceStart();
    }
  }, [voice.state]);

  const [attachedFile, setAttachedFile] = useState<{
    file: File;
    previewUrl?: string;
    isImage: boolean;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    const isImage = file.type.startsWith("image/");
    const previewUrl = isImage ? URL.createObjectURL(file) : undefined;
    setAttachedFile({ file, previewUrl, isImage });
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleRemoveAttachment = () => {
    if (attachedFile?.previewUrl) {
      URL.revokeObjectURL(attachedFile.previewUrl);
    }
    setAttachedFile(null);
    setUploadError(null);
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading || Boolean(streamingId) || uploading) return;
    if (!input.trim() && !attachedFile) return;

    if (attachedFile) {
      setUploading(true);
      setUploadError(null);
      try {
        const uploaded = await uploadAttachment(attachedFile.file);
        handleRemoveAttachment();
        await send(input.trim() || "Đã gửi tệp đính kèm", [uploaded]);
      } catch (err: any) {
        setUploadError(err?.message || "Lỗi tải tệp lên");
      } finally {
        setUploading(false);
      }
    } else {
      send();
    }
  };

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input khi mở
  useEffect(() => {
    const t = window.setTimeout(() => inputRef.current?.focus(), 200);
    return () => window.clearTimeout(t);
  }, []);

  const isVoiceActive =
    voice.state === "connecting" ||
    voice.state === "listening" ||
    voice.state === "processing" ||
    voice.state === "speaking";

  const isVoiceError =
    voice.state === "error" ||
    voice.state === "mic_denied" ||
    voice.state === "mic_not_found" ||
    voice.state === "superseded" ||
    voice.state === "idle_timeout";

  // Suy luận mood tổng hợp cho cả Text Chat và Voice:
  const chatMood: AvatarMood = (() => {
    if (isVoiceActive) {
      if (voice.state === "speaking") return "speaking";
      if (voice.state === "listening") return "listening";
      if (voice.state === "processing") return "processing";
      if (voice.state === "error") return "error";
    }
    if (loading && !streamingId) return "processing";
    if (Boolean(streamingId)) return "speaking";

    const lastMsg = messages[messages.length - 1];
    if (lastMsg && lastMsg.sender === "copilot") {
      if (lastMsg.action_proposal?.status === "executed") return "success";
      const txt = lastMsg.text.toLowerCase();
      if (txt.includes("lỗi") || txt.includes("thất bại") || txt.includes("không thể")) return "error";
      if (txt.includes("cảnh báo") || txt.includes("chú ý") || txt.includes("thiếu ca")) return "alert";
      if (txt.includes("xin chào") || txt.includes("chào Ký chủ") || txt.includes("chào bạn") || txt.includes("hello") || txt.startsWith("chào")) return "greeting";
      if (txt.includes("tuyệt vời") || txt.includes("hoàn tất") || txt.includes("chúc mừng") || txt.includes("xuất sắc")) return "happy";
    }
    if (messages.length === 0) return "greeting";
    return "idle";
  })();

  const handleVoiceToggle = () => {
    if (isVoiceActive) {
      voice.stop();
      activeVoiceTurnRef.current = null;
      return;
    }
    try {
      if (typeof window !== "undefined" && window.localStorage.getItem(VOICE_CONSENT_KEY) === "true") {
        void voice.start();
      } else {
        setShowConsentModal(true);
      }
    } catch {
      void voice.start();
    }
  };

  const handleModeChange = (newMode: VoiceInputMode) => {
    setVoiceMode(newMode);
    try {
      window.localStorage.setItem(VOICE_MODE_KEY, newMode);
    } catch {}
  };

  const handleMicChange = (newMicId: string) => {
    setSelectedMicId(newMicId);
    void voice.changeMic(newMicId);
    try {
      window.localStorage.setItem(VOICE_MIC_KEY, newMicId);
    } catch {}
  };

  return (
    <div
      className="relative flex h-full flex-col bg-[var(--nq-bg)] text-[var(--nq-fg)]"
      style={{ ["--accent" as any]: profile.accent }}
    >
      {/* Consent Modal for Decree 13/2023/ND-CP */}
      {showConsentModal && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-sm nq-surface-block border-[var(--nq-accent)] p-5 shadow-2xl">
            <div className="flex items-center gap-2 text-[var(--nq-accent)]">
              <Icon name="microphone" size={18} />
              <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-fg)]">
                Bảo vệ quyền riêng tư giọng nói
              </h4>
            </div>
            <div className="mt-3 space-y-2.5 text-2xs leading-relaxed text-[var(--nq-dim)]">
              <p>
                Theo <strong>Nghị định 13/2023/NĐ-CP</strong>, AG-COPILOT cần sự đồng thuận của anh/chị trước khi tiếp nhận âm thanh từ micro để hỗ trợ tra cứu và điều hành qua giọng nói.
              </p>
              <div className="border border-[var(--nq-dim)]/40 bg-[var(--nq-bg)] p-2.5 text-2xs text-[var(--nq-fg)]">
                <p className="font-semibold text-[var(--nq-st-ok-ink)]">Cam kết an toàn dữ liệu:</p>
                <ul className="mt-1 list-disc pl-4 space-y-0.5 text-[var(--nq-dim)]">
                  <li>Không lưu trữ tệp ghi âm giọng nói thô trên hệ thống.</li>
                  <li>Chỉ lưu bản ghi văn bản (transcript) trong lịch sử hội thoại.</li>
                  <li>Có thể dừng phiên voice bất kỳ lúc nào để chuyển sang chat text.</li>
                </ul>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowConsentModal(false)}
                className="border border-[var(--nq-dim)] px-3 py-1.5 text-2xs font-bold uppercase text-[var(--nq-dim)] transition hover:border-[var(--nq-fg)] hover:text-[var(--nq-fg)]"
              >
                Để sau
              </button>
              <button
                type="button"
                onClick={() => {
                  try {
                    window.localStorage.setItem(VOICE_CONSENT_KEY, "true");
                  } catch {}
                  setShowConsentModal(false);
                  void voice.start();
                }}
                className="border border-[var(--nq-accent)] bg-[var(--nq-accent)] px-3.5 py-1.5 text-2xs font-bold uppercase text-[var(--nq-accent-ink)] transition hover:brightness-110"
              >
                Đồng ý & Bắt đầu
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--nq-line)] bg-[var(--nq-surface)] p-3 sm:p-4">
        <div className="flex items-center gap-2.5">
          <div className="shrink-0 -my-1">
            <Avatar2D
              size={42}
              speaking={isSpeaking || Boolean(streamingId)}
              listening={isListening}
              mouthOpen={mouthOpen}
              mood={chatMood}
            />
          </div>
          <div>
            <h3 className="text-sm font-bold uppercase text-[var(--nq-fg)] leading-tight">{profile.label}</h3>
            <p className="flex items-center gap-1.5 text-2xs text-[var(--nq-dim)]">
              <span className={`h-1.5 w-1.5 rounded-full ${
                chatMood === "processing" ? "bg-amber-400 animate-ping" :
                chatMood === "speaking" ? "bg-cyan-400 animate-pulse" :
                chatMood === "alert" || chatMood === "error" ? "bg-rose-400" :
                "bg-[var(--nq-st-ok)]"
              }`} />
              {chatMood === "processing"
                ? "Đang tính toán & tra cứu quy trình…"
                : chatMood === "speaking"
                ? "Đang phản hồi Ký chủ…"
                : chatMood === "alert"
                ? "Cảnh báo ca làm việc!"
                : chatMood === "error"
                ? "Hệ thống gặp sự cố"
                : chatMood === "success"
                ? "Nhiệm vụ hoàn thành xuất sắc!"
                : "Sẵn sàng hỗ trợ · AI trả lời kèm đề xuất"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleVoiceToggleEnabled}
            title={voiceEnabled ? "Tắt voice (chỉ dùng chat text)" : "Bật voice (nói chuyện với trợ lý)"}
            className={`flex items-center gap-1 border px-2 py-1 text-2xs font-bold uppercase transition ${
              voiceEnabled
                ? "border-[var(--nq-accent)] bg-[var(--nq-accent)]/10 text-[var(--nq-accent)] hover:brightness-110"
                : "border-[var(--nq-dim)] text-[var(--nq-dim)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
            }`}
          >
            <Icon name="microphone" size={13} />
            {voiceEnabled ? "Voice: Bật" : "Voice: Tắt"}
          </button>
          {onClearHistory ? (
            <button
              onClick={onClearHistory ?? clearHistory}
              title="Xoá lịch sử hội thoại"
              className="border border-transparent px-2 py-1 text-2xs font-bold uppercase text-[var(--nq-dim)] transition hover:border-[var(--nq-red)] hover:text-[var(--nq-red)]"
            >
              Xoá
            </button>
          ) : null}
          {onOpenFullPage ? (
            <button
              onClick={onOpenFullPage}
              title="Mở trợ lý ở trang riêng"
              className="border border-transparent px-2 py-1 text-2xs font-bold uppercase text-[var(--nq-dim)] transition hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
            >
              Mở rộng
            </button>
          ) : null}
          {onClose ? (
            <button
              onClick={onClose}
              title="Đóng"
              className="border border-transparent px-2 py-1 text-2xs font-bold uppercase text-[var(--nq-dim)] transition hover:border-[var(--nq-accent)] hover:text-[var(--nq-fg)]"
            >
              Đóng
            </button>
          ) : null}
        </div>
      </div>

      {/* Empty role */}
      {profile.quickPrompts.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-[var(--nq-dim)]">
          {profile.emptyMessage ?? profile.greeting}
        </div>
      ) : (
        <>
          {/* Messages */}
          <div
            onScroll={(e) => {
              const target = e.currentTarget;
              const isUp = target.scrollHeight - target.scrollTop - target.clientHeight > 120;
              setShowScrollBottom(isUp);
            }}
            className="relative flex-1 space-y-4 overflow-y-auto p-4 text-xs"
          >
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${
                  msg.sender === "user" ? "items-end" : "items-start"
                }`}
              >
                <div
                  className={`max-w-[85%] sm:max-w-[72%] rounded-lg border p-3 ${
                    msg.sender === "user"
                      ? "border-[var(--nq-accent)] bg-[var(--nq-accent)] text-[var(--nq-accent-ink)]"
                      : "border-[var(--nq-dim)] bg-[var(--nq-surface)] text-[var(--nq-fg)]"
                  }`}
                >
                  {msg.sender === "copilot" && msg.id !== "welcome" && (
                    <span className="mb-1.5 inline-flex items-center gap-1 rounded bg-[var(--nq-bg-elevated)] px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wider text-[var(--nq-accent)]">
                      {msg.agent_mode === "live" ? "AI trực tiếp" : msg.agent_mode === "replay" ? "Bản ghi mẫu" : "Trợ lý"}
                    </span>
                  )}
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="mb-2 space-y-1.5">
                      {msg.attachments.map((att, idx) => {
                        const mediaUrl = resolveMediaUrl(att.url);
                        const isImg =
                          att.mime_type?.startsWith("image/") ||
                          /\.(png|jpe?g|webp|gif)$/i.test(att.url);
                        if (isImg) {
                          return (
                            <div key={idx} className="overflow-hidden rounded-md border border-black/20 max-w-[240px]">
                              <a href={mediaUrl} target="_blank" rel="noreferrer">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                  src={mediaUrl}
                                  alt={att.filename || "Đính kèm"}
                                  className="max-h-44 w-auto object-cover rounded hover:opacity-90 transition"
                                />
                              </a>
                            </div>
                          );
                        }
                        return (
                          <a
                            key={idx}
                            href={mediaUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center gap-2 rounded bg-black/10 px-2 py-1 text-2xs transition hover:bg-black/20"
                          >
                            <Icon name="attachment" size={14} />
                            <span className="truncate max-w-[180px] font-medium">
                              {att.filename || "Tệp đính kèm"}
                            </span>
                            <Icon name="download" size={12} />
                          </a>
                        );
                      })}
                    </div>
                  )}
                  {/* Trạng thái đang xử lý: hiện khi bong bóng CHƯA có chữ. */}
                  {msg.sender === "copilot" && !msg.text && msg.pending_status ? (
                    <p className="nq-copilot-pending" data-role="copilot-pending">
                      <span className="nq-copilot-pending__dot" aria-hidden="true" />
                      {msg.pending_status}
                    </p>
                  ) : null}
                  <p className="whitespace-pre-wrap leading-relaxed">
                    <ChatText text={msg.text} />
                    {streamingId === msg.id && (
                      <span className="ml-0.5 inline-block w-1.5 h-3 align-middle bg-[var(--nq-st-warn)] animate-pulse" />
                    )}
                  </p>

                  {/* Nút sao chép nội dung tin nhắn của AI */}
                  {msg.sender === "copilot" && msg.text && msg.id !== "welcome" && (
                    <div className="mt-2 pt-1 border-t border-[var(--nq-dim)]/20 flex justify-end">
                      <button
                        type="button"
                        onClick={() => {
                          if (typeof navigator !== "undefined" && navigator.clipboard) {
                            navigator.clipboard.writeText(msg.text);
                          }
                          setCopiedId(msg.id);
                          setTimeout(() => setCopiedId(null), 2000);
                        }}
                        className="flex items-center gap-1 text-[10px] text-[var(--nq-dim)] hover:text-[var(--nq-fg)] transition px-1.5 py-0.5 rounded hover:bg-black/10"
                        title="Sao chép nội dung tin nhắn"
                      >
                        {copiedId === msg.id ? (
                          <>
                            <span className="text-emerald-400 font-bold">✓</span>
                            <span className="text-emerald-400 font-medium">Đã chép</span>
                          </>
                        ) : (
                          <>
                            <Icon name="clipboard" size={11} />
                            <span>Sao chép</span>
                          </>
                        )}
                      </button>
                    </div>
                  )}

                  {msg.sender === "copilot" &&
                    msg.id === "welcome" &&
                    profile.capabilities.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-[var(--nq-line)]">
                        <p className="text-2xs uppercase tracking-wider text-[var(--nq-ink-muted)] mb-1">
                          Em làm được gì cho anh/chị
                        </p>
                        <ul className="flex flex-wrap gap-1">
                          {profile.capabilities.map((cap, i) => (
                            <li
                              key={`cap-${i}`}
                              className="text-2xs px-1.5 py-0.5 rounded bg-[var(--nq-surface)] border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] text-[var(--nq-st-ok-ink)]"
                            >
                              {cap}
                            </li>
                          ))}
                        </ul>
                        {profile.deniedNote ? (
                          <p className="text-2xs text-[var(--nq-ink-muted)] mt-1.5 italic">
                            {profile.deniedNote}
                          </p>
                        ) : null}

                        {/* Thẻ thao tác nhanh tiện lợi gợi ý ngay dưới lời chào */}
                        {profile.quickPrompts.length > 0 && (
                          <div className="mt-3 pt-2 border-t border-[var(--nq-line)] space-y-1.5">
                            <p className="text-2xs font-bold uppercase tracking-wider text-[var(--nq-accent)] flex items-center gap-1">
                              <span>⚡</span> Thao tác nhanh cho ca trực:
                            </p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                              {profile.quickPrompts.slice(0, 4).map((qp, idx) => (
                                <button
                                  key={`hero-qp-${idx}`}
                                  type="button"
                                  onClick={() => send(qp)}
                                  disabled={loading || Boolean(streamingId)}
                                  className="flex items-center gap-2 rounded border border-[var(--nq-dim)]/40 bg-[var(--nq-bg)] p-2 text-left text-2xs text-[var(--nq-fg)] transition hover:border-[var(--nq-accent)] hover:bg-[var(--nq-accent)]/10 hover:text-[var(--nq-accent)] disabled:opacity-50 group"
                                >
                                  <span className="shrink-0 text-amber-400 group-hover:scale-110 transition">
                                    {idx === 0 ? "📅" : idx === 1 ? "⚠️" : idx === 2 ? "🥛" : "✨"}
                                  </span>
                                  <span className="line-clamp-2 leading-tight font-medium">{qp}</span>
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

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
                              className="text-2xs px-1.5 py-0.5 rounded bg-[var(--nq-surface)] border"
                              style={{
                                color: profile.accent,
                                borderColor: `color-mix(in srgb, ${profile.accent} 20%, transparent)`,
                              }}
                            >
                              {c}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                  {msg.action_proposal && profile.allowActionApproval && (
                    <ActionProposalCard
                      proposal={msg.action_proposal}
                      onExecuted={(updated) => updateProposal(msg.id, updated)}
                    />
                  )}
                  {msg.action_proposal && !profile.allowActionApproval && (
                    <div className="mt-2 pt-2 border-t border-[var(--nq-line)] text-2xs text-[var(--nq-ink-muted)] italic">
                      Đề xuất: {msg.action_proposal.intent} — nhờ quản lý duyệt trong
                      <a className="underline ml-1" href="/inbox">
                        Hộp thư
                      </a>
                      .
                    </div>
                  )}
                </div>
                <span className="mt-1 px-1 text-2xs text-[var(--nq-dim)]">{msg.timestamp}</span>
              </div>
            ))}
            {loading && (
              <div className="flex w-fit items-center gap-2 border border-[var(--nq-dim)] bg-[var(--nq-surface)] p-2 text-xs italic text-[var(--nq-dim)]">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--nq-accent)]" />
                Đang xử lý yêu cầu…
              </div>
            )}
            {showScrollBottom && (
              <div className="sticky bottom-2 flex justify-center z-10 pointer-events-none">
                <button
                  type="button"
                  onClick={() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })}
                  className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-[var(--nq-accent)] bg-[var(--nq-bg-elevated)] px-3 py-1 text-2xs font-semibold text-[var(--nq-accent)] shadow-xl backdrop-blur-md transition hover:scale-105 active:scale-95 animate-in fade-in slide-in-from-bottom-2"
                >
                  <span>↓</span>
                  <span>Xuống tin nhắn mới nhất</span>
                </button>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Prompts */}
          <div className="flex shrink-0 gap-1.5 overflow-x-auto border-t border-[var(--nq-dim)] bg-[var(--nq-surface)] px-4 py-2">
            {profile.quickPrompts.map((qp, idx) => (
              <button
                key={idx}
                onClick={() => send(qp)}
                disabled={loading || Boolean(streamingId)}
                className="whitespace-nowrap border border-[var(--nq-dim)] bg-[var(--nq-bg)] px-2.5 py-1 text-2xs text-[var(--nq-dim)] transition hover:border-[var(--nq-accent)] hover:text-[var(--nq-fg)] disabled:opacity-50"
              >
                {qp}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="shrink-0 border-t border-[var(--nq-line)] bg-[var(--nq-surface)] p-3">
            {/* Thanh xem trước đính kèm trước khi gửi */}
            {attachedFile && (
              <div className="mb-2 flex items-center justify-between rounded border border-[var(--nq-dim)] bg-[var(--nq-bg)] p-2 text-xs">
                <div className="flex items-center gap-2 truncate">
                  {attachedFile.isImage && attachedFile.previewUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={attachedFile.previewUrl}
                      alt="Xem trước"
                      className="h-8 w-8 rounded object-cover border border-[var(--nq-dim)] shrink-0"
                    />
                  ) : (
                    <div className="flex h-8 w-8 items-center justify-center rounded bg-[var(--nq-dim)]/20 text-[var(--nq-accent)] shrink-0">
                      <Icon name="attachment" size={16} />
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-[var(--nq-fg)] text-2xs">{attachedFile.file.name}</p>
                    <p className="text-2xs text-[var(--nq-dim)]">{(attachedFile.file.size / 1024).toFixed(1)} KB</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleRemoveAttachment}
                  disabled={uploading}
                  className="p-1 text-xs font-bold text-[var(--nq-dim)] transition hover:text-[var(--nq-st-danger-ink)] shrink-0"
                  title="Xóa tệp đính kèm"
                >
                  ✕
                </button>
              </div>
            )}
            {uploadError && (
              <p className="mb-2 text-2xs text-[var(--nq-st-danger-ink)]">{uploadError}</p>
            )}
            {voiceEnabled && (
              <div className="mb-2 space-y-1.5">
                {/* Audio controls: Mode switcher & Mic dropdown */}
                <div className="flex items-center justify-between gap-2 px-1 text-2xs">
                  <div className="inline-flex rounded border border-[var(--nq-dim)] bg-[var(--nq-bg)] p-0.5">
                    <button
                      type="button"
                      onClick={() => handleModeChange("open_mic")}
                      className={`px-2 py-0.5 font-bold uppercase transition rounded-sm ${
                        voiceMode === "open_mic"
                          ? "bg-[var(--nq-accent)] text-[var(--nq-accent-ink)]"
                          : "text-[var(--nq-dim)] hover:text-[var(--nq-fg)]"
                      }`}
                      title="Thu âm liên tục rảnh tay"
                    >
                      Mic mở
                    </button>
                    <button
                      type="button"
                      onClick={() => handleModeChange("push_to_talk")}
                      className={`px-2 py-0.5 font-bold uppercase transition rounded-sm ${
                        voiceMode === "push_to_talk"
                          ? "bg-[var(--nq-accent)] text-[var(--nq-accent-ink)]"
                          : "text-[var(--nq-dim)] hover:text-[var(--nq-fg)]"
                      }`}
                      title="Giữ nút khi nói, chống nhiễu quán ăn"
                    >
                      Giữ để nói (PTT)
                    </button>
                  </div>

                  {voice.availableMics.length > 1 && (
                    <select
                      value={selectedMicId}
                      onChange={(e) => handleMicChange(e.target.value)}
                      className="max-w-[160px] truncate rounded border border-[var(--nq-dim)] bg-[var(--nq-bg)] px-1.5 py-0.5 text-2xs text-[var(--nq-dim)] hover:text-[var(--nq-fg)] focus:text-[var(--nq-fg)] focus:outline-none"
                      title="Chọn thiết bị micro"
                    >
                      <option value="">Micro mặc định</option>
                      {voice.availableMics.map((mic) => (
                        <option key={mic.deviceId} value={mic.deviceId}>
                          {mic.label}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {/* Banner avatar — hiện khi voice đang hoạt động (kết nối/nghe/xử lý/nói).
                    Avatar nhép miệng theo giọng nói trợ lý. */}
                {isVoiceActive && (
                  <div
                    className="flex items-center gap-3 rounded border border-[var(--nq-dim)]/40 bg-[var(--nq-bg)] px-3 py-2"
                    role="status"
                    aria-live="polite"
                  >
                    <Avatar2D
                      mouthOpen={mouthOpen}
                      speaking={isSpeaking}
                      listening={isListening}
                      mood={
                        voice.state === "speaking"
                          ? "speaking"
                          : voice.state === "listening"
                          ? "listening"
                          : voice.state === "processing"
                          ? "processing"
                          : voice.state === "error"
                          ? "error"
                          : "idle"
                      }
                      size={72}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--nq-accent)]">
                        {profile.label}
                      </p>
                      <p className="mt-0.5 text-[11px] text-[var(--nq-dim)]">
                        {voice.state === "connecting" && "Đang kết nối voice trực tiếp…"}
                        {voice.state === "listening" && (
                          voiceMode === "push_to_talk" ? (
                            voice.isPttSpeaking
                              ? "Đang ghi âm giọng nói… Thả nút để gửi đi."
                              : "Sẵn sàng. Nhấn giữ nút micro bên dưới để nói."
                          ) : (
                            "Đang nghe… Anh/chị có thể nói hoặc gõ bất cứ lúc nào."
                          )
                        )}
                        {voice.state === "processing" && "Đang xử lý yêu cầu…"}
                        {voice.state === "speaking" && "Trợ lý đang nói… Có thể nói chen ngang để ngắt lời."}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        voice.stop();
                        activeVoiceTurnRef.current = null;
                      }}
                      className="shrink-0 border border-transparent px-1.5 py-0.5 text-[9px] font-bold uppercase text-[var(--nq-dim)] hover:border-rose-400 hover:text-rose-400 transition"
                      title="Dừng phiên voice"
                    >
                      Đóng
                    </button>
                  </div>
                )}

                {/* Banner lỗi — chỉ hiện khi có lỗi, tách khỏi banner avatar */}
                {isVoiceError && (
                  <div
                    className="flex items-center justify-between gap-2 rounded border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-300"
                    role="status"
                    aria-live="polite"
                  >
                    <p className="flex-1">
                      {voice.state === "mic_denied" && "Trình duyệt chưa cấp quyền micro. Vui lòng mở quyền micro trong cài đặt trình duyệt, rồi bấm nút micro để thử lại."}
                      {voice.state === "mic_not_found" && "Không tìm thấy thiết bị micro. Vui lòng kiểm tra cổng cắm hoặc cài đặt micro."}
                      {voice.state === "superseded" && "Phiên voice đã được chuyển sang tab/thiết bị khác của anh/chị."}
                      {voice.state === "idle_timeout" && "Phiên voice tạm ngưng sau 60 giây im lặng. Bấm micro để nói lại."}
                      {voice.state === "error" && "Voice chưa sẵn sàng. Bấm nút micro để thử lại, hoặc tiếp tục dùng chat text."}
                    </p>
                  </div>
                )}
              </div>
            )}

            <form
              onSubmit={handleFormSubmit}
              className="flex items-center gap-2"
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                accept="image/png,image/jpeg,image/webp,image/gif,application/pdf"
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading || Boolean(streamingId) || uploading}
                className="nq-surface-row bg-[var(--nq-bg)] p-2 text-[var(--nq-dim)] transition hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)] disabled:opacity-40"
                title="Đính kèm ảnh hoặc tài liệu"
              >
                <Icon name="attachment" size={16} />
              </button>
              <div className="relative flex-1">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={attachedFile ? "Thêm ghi chú cho tệp đính kèm..." : "Nhập câu hỏi hoặc chọn thao tác nhanh..."}
                  disabled={loading || Boolean(streamingId) || uploading}
                  className="w-full border border-[var(--nq-line-control)] rounded bg-[var(--nq-bg)] pl-3.5 pr-8 py-2 text-xs text-[var(--nq-fg)] placeholder:text-[var(--nq-dim)] focus:outline-none focus:border-[var(--nq-accent)] disabled:opacity-50 transition"
                />
                {input.trim().length > 0 && (
                  <button
                    type="button"
                    onClick={() => setInput("")}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-[var(--nq-dim)] hover:text-[var(--nq-fg)] transition"
                    title="Xóa nội dung đang nhập"
                  >
                    ✕
                  </button>
                )}
              </div>
              {voiceEnabled && (
                <button
                  type="button"
                  onClick={voiceMode === "open_mic" || !isVoiceActive ? handleVoiceToggle : undefined}
                  onPointerDown={
                    voiceMode === "push_to_talk" && isVoiceActive
                      ? (e) => {
                          e.preventDefault();
                          voice.startPttTalk();
                        }
                      : undefined
                  }
                  onPointerUp={
                    voiceMode === "push_to_talk" && isVoiceActive
                      ? (e) => {
                          e.preventDefault();
                          voice.stopPttTalk();
                        }
                      : undefined
                  }
                  onPointerLeave={
                    voiceMode === "push_to_talk" && isVoiceActive
                      ? () => {
                          if (voice.isPttSpeaking) voice.stopPttTalk();
                        }
                      : undefined
                  }
                  onPointerCancel={
                    voiceMode === "push_to_talk" && isVoiceActive
                      ? () => {
                          if (voice.isPttSpeaking) voice.stopPttTalk();
                        }
                      : undefined
                  }
                  disabled={loading || Boolean(streamingId) || uploading || voice.state === "connecting"}
                  className={`flex items-center gap-1.5 border-2 px-2.5 py-2 text-[11px] font-bold uppercase transition select-none disabled:opacity-40 ${
                    voiceMode === "push_to_talk" && isVoiceActive
                      ? voice.isPttSpeaking
                        ? "border-[var(--nq-st-danger)] bg-[var(--nq-st-danger)] text-[var(--nq-accent-ink)] animate-pulse scale-105"
                        : "border-[var(--nq-st-warn)] bg-[var(--nq-st-warn-soft)] text-[var(--nq-st-warn-ink)] hover:brightness-110"
                      : isVoiceActive
                      ? "border-[var(--nq-st-danger)] bg-[var(--nq-st-danger)] text-[var(--nq-accent-ink)] animate-pulse"
                      : "border-[var(--nq-line-control)] bg-[var(--nq-bg)] text-[var(--nq-dim)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
                  }`}
                  title={
                    voiceMode === "push_to_talk"
                      ? isVoiceActive
                        ? voice.isPttSpeaking
                          ? "Đang giữ để nói (thả ra để gửi)"
                          : "Nhấn và giữ để nói (Push-to-Talk)"
                        : "Bật phiên Voice Push-to-Talk"
                      : isVoiceActive
                      ? "Dừng phiên voice"
                      : "Bắt đầu nói với trợ lý"
                  }
                >
                  <Icon name="microphone" size={16} />
                  <span className="hidden sm:inline">
                    {voiceMode === "push_to_talk" && isVoiceActive
                      ? voice.isPttSpeaking
                        ? "Đang nói…"
                        : "Giữ để nói"
                      : isVoiceActive
                      ? "Dừng"
                      : "Nói"}
                  </span>
                </button>
              )}
              <button
                type="submit"
                disabled={loading || Boolean(streamingId) || uploading || (!input.trim() && !attachedFile)}
                className="rounded border border-[var(--nq-accent)] bg-[var(--nq-accent)] px-3.5 py-2 text-xs font-bold uppercase text-[var(--nq-accent-ink)] transition disabled:cursor-not-allowed disabled:opacity-40"
              >
                {uploading ? "Đang tải…" : "Gửi"}
              </button>
            </form>
            {voiceEnabled && voice.state === "idle" && (
              <p className="mt-1.5 text-center text-[10px] text-[var(--nq-dim)]" role="status" aria-live="polite">
                Bấm nút micro để nói chuyện với trợ lý.
              </p>
            )}
            <p className="mt-1.5 text-center text-[10px] text-[var(--nq-dim)]">
              Ctrl/Cmd+K mở hoặc đóng · Esc thu nhỏ
            </p>
          </div>
        </>
      )}
    </div>
  );
}