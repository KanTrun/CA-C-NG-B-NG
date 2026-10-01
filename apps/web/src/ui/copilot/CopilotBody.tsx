// UI body chat phong cách Companion Instant Messenger (nhắn tin trực tiếp với Tinh Linh)
// tích hợp chế độ Gọi Live (Live Video Call) phóng to nhân vật 2D chân thực.
//
// Dùng chung cho CopilotPane (floating companion) và trang /copilot (toàn màn hình).

"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { chatSounds } from "../../lib/chat-sound";
import { ActionProposalCard } from "./ActionProposalCard";
import { Avatar2D, AvatarStatic, preloadAvatarHot, preloadAvatarMood, type AvatarMood } from "./Avatar2D";
import { ChatText } from "./ChatText";
import type { ChatMessage, Mode } from "./useCopilotChat";
import { useCopilotVoice, type VoiceProposalData } from "./useCopilotVoice";
import { useAvatarLipSync } from "./useAvatarLipSync";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const VOICE_CONSENT_KEY = "ag_voice_consent_v1";

function resolveMediaUrl(url: string): string {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("blob:")) {
    return url;
  }
  return `${API_BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
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
    clearHistory,
  } = chat;

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeVoiceTurnRef = useRef<{ id: string; role: "user" | "copilot" } | null>(null);
  const skipNextCopilotTranscriptRef = useRef(false);

  // Chế độ cuộc gọi Live trực tiếp ("cho nó bự lên rồi nói chuyện")
  const [isLiveCall, setIsLiveCall] = useState(false);
  const [callSeconds, setCallSeconds] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [showConsentModal, setShowConsentModal] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Phụ đề theo thời gian thực cho cuộc gọi Live
  const [latestUserTranscript, setLatestUserTranscript] = useState("");
  const [latestCopilotTranscript, setLatestCopilotTranscript] = useState("");

  // Quản lý tệp đính kèm
  const [attachedFile, setAttachedFile] = useState<{
    file: File;
    previewUrl: string;
    isImage: boolean;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    const checkMobile = () => setIsMobile(typeof window !== "undefined" && window.innerWidth < 640);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Bộ đếm thời gian cho cuộc gọi Live
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (isLiveCall) {
      interval = setInterval(() => {
        setCallSeconds((s) => s + 1);
      }, 1000);
    } else {
      setCallSeconds(0);
      setLatestUserTranscript("");
      setLatestCopilotTranscript("");
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isLiveCall]);

  // Xử lý phụ đề và văn bản trả lời từ Voice socket
  const handleTranscript = useCallback(
    (role: "user" | "copilot", chunk: string, isFinal: boolean) => {
      if (!chunk.trim()) return;
      if (role === "user") setLatestUserTranscript(chunk);
      if (role === "copilot") setLatestCopilotTranscript(chunk);

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
                ? chunk.startsWith(" ") || currentText.endsWith(" ")
                  ? currentText + chunk
                  : currentText + " " + chunk
                : chunk;
              return { ...m, text: nextText };
            }
            return m;
          });
          if (isFinal) activeVoiceTurnRef.current = null;
          return updated;
        } else {
          const newId = `voice_${role}_${Date.now()}`;
          if (!isFinal) activeVoiceTurnRef.current = { id: newId, role };
          else activeVoiceTurnRef.current = null;

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
    (data: VoiceProposalData) => {
      if (!data.reply_text.trim()) return;
      setLatestCopilotTranscript(data.reply_text);
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
      skipNextCopilotTranscriptRef.current = true;
      setMessages((prev) => [...prev, newMsg]);
    },
    [setMessages]
  );

  const voice = useCopilotVoice({
    onTranscript: handleTranscript,
    onInterrupted: handleInterrupted,
    onProposal: handleVoiceProposal,
    inputMode: "open_mic",
  });

  const isSpeaking = voice.state === "speaking" || Boolean(streamingId);
  const isListening = voice.state === "listening";
  const mouthOpen = useAvatarLipSync(voice.audioLevel, isSpeaking);

  const isVoiceActive =
    voice.state === "connecting" ||
    voice.state === "listening" ||
    voice.state === "processing" ||
    voice.state === "speaking";

  // Suy luận mood của Tinh Linh theo thời gian thực
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
      // "Không thể tìm phương án..." (INFEASIBLE) là kết quả nghiệp vụ của
      // solver, không phải sự cố hệ thống — nếu xếp vào "error" Tinh Linh đeo
      // mặt "Hệ thống lỗi" suốt ca (gặp thật 2026-10-01).
      if (txt.includes("lỗi") || txt.includes("thất bại")) return "error";
      if (txt.includes("không thể") || txt.includes("cảnh báo") || txt.includes("chú ý") || txt.includes("thiếu ca"))
        return "alert";
      if (txt.includes("xin chào") || txt.includes("chào ký chủ") || txt.includes("chào bạn") || txt.startsWith("chào"))
        return "greeting";
      if (txt.includes("tuyệt vời") || txt.includes("hoàn tất") || txt.includes("chúc mừng") || txt.includes("xuất sắc"))
        return "happy";
    }
    if (messages.length === 0) return "greeting";
    return "idle";
  })();

  // Preload sprite mood kế tiếp để chuyển mood không giật (chỉ tải theo mood, không tải 89 file).
  useEffect(() => {
    preloadAvatarMood(chatMood);
  }, [chatMood]);

  // Preload các mood nóng khi trình duyệt rảnh (lần đầu mở đã có speaking/listening/processing).
  useEffect(() => {
    const ric = (window as unknown as { requestIdleCallback?: (cb: () => void) => void })
      .requestIdleCallback;
    if (ric) ric(() => preloadAvatarHot());
    else {
      const t = window.setTimeout(() => preloadAvatarHot(), 1500);
      return () => window.clearTimeout(t);
    }
  }, []);

  // Bắt đầu cuộc gọi Live ("cho nó bự lên rồi nói chuyện")
  const handleStartLiveCall = useCallback(() => {
    try {
      const consented = typeof window !== "undefined" && window.localStorage.getItem(VOICE_CONSENT_KEY) === "true";
      if (consented) {
        chatSounds.playCallStart();
        setIsLiveCall(true);
        void voice.start();
      } else {
        setShowConsentModal(true);
      }
    } catch {
      chatSounds.playCallStart();
      setIsLiveCall(true);
      void voice.start();
    }
  }, [voice]);

  // Kết thúc cuộc gọi Live
  const handleEndLiveCall = useCallback(() => {
    chatSounds.playCallEnd();
    voice.stop();
    activeVoiceTurnRef.current = null;
    setIsLiveCall(false);
    const dur = formatDuration(callSeconds);
    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    setMessages((prev) => [
      ...prev,
      {
        id: `call_end_${Date.now()}`,
        sender: "copilot",
        text: `📞 Cuộc gọi trực tiếp với Tinh Linh đã hoàn tất (Thời lượng: ${dur}).`,
        timestamp: now,
      },
    ]);
  }, [callSeconds, setMessages, voice]);

  // Xử lý đính kèm tệp
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("Tệp quá lớn (tối đa 10MB)");
      return;
    }
    const isImage = file.type.startsWith("image/");
    const previewUrl = URL.createObjectURL(file);
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

  // Gửi tin nhắn văn bản
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

  // Tự động cuộn xuống tin nhắn mới nhất
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingId]);

  return (
    <div className="relative flex h-full w-full flex-col bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* ── CONSENT MODAL NGHỊ ĐỊNH 13/2023/NĐ-CP ── */}
      {showConsentModal && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-sm rounded-2xl border border-amber-500/50 bg-slate-900 p-5 shadow-2xl">
            <div className="flex items-center gap-2 text-amber-400">
              <Icon name="phone" size={18} />
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-100">
                Bảo vệ quyền riêng tư cuộc gọi
              </h4>
            </div>
            <div className="mt-3 space-y-2 text-xs leading-relaxed text-slate-300">
              <p>
                Theo <strong>Nghị định 13/2023/NĐ-CP</strong>, Tinh Linh cần quyền sử dụng micro để trò chuyện trực tiếp (Live Call) cùng bạn.
              </p>
              <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-2.5 text-[11px] text-slate-300">
                <p className="font-semibold text-emerald-400">Cam kết an toàn dữ liệu:</p>
                <ul className="mt-1 list-disc pl-4 space-y-0.5 text-slate-400">
                  <li>Không lưu trữ tệp ghi âm giọng nói thô trên máy chủ.</li>
                  <li>Bạn có thể ngắt kết nối cuộc gọi bất cứ lúc nào.</li>
                </ul>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowConsentModal(false)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-400 hover:text-slate-200 transition"
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
                  chatSounds.playCallStart();
                  setIsLiveCall(true);
                  void voice.start();
                }}
                className="rounded-lg bg-gradient-to-r from-emerald-500 to-teal-500 px-4 py-1.5 text-xs font-bold text-slate-950 shadow-md hover:brightness-110 transition"
              >
                Đồng ý & Bắt đầu
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── GIAO DIỆN CUỘC GỌI LIVE ("cho nó bự lên rồi nói chuyện") ── */}
      {isLiveCall && (
        <div className="absolute inset-0 z-40 flex flex-col justify-between bg-gradient-to-b from-slate-950 via-slate-900 to-indigo-950 text-white overflow-hidden animate-in fade-in zoom-in-95 duration-300">
          {/* Hào quang nền vũ trụ */}
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(56,189,248,0.15),transparent_60%)] pointer-events-none" />

          {/* Top Header cuộc gọi */}
          <div className="relative z-10 flex shrink-0 items-center justify-between border-b border-white/10 bg-slate-950/50 px-4 py-3 backdrop-blur-md">
            <div className="flex items-center gap-2.5">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-500 opacity-75" />
                <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-600" />
              </span>
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-rose-300 flex items-center gap-1.5">
                  LIVE CALL · TRỰC TIẾP
                </span>
                <span className="text-[11px] font-mono text-slate-300">
                  {formatDuration(callSeconds)}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="rounded-full bg-emerald-500/20 border border-emerald-400/30 px-2.5 py-0.5 text-[10px] font-medium text-emerald-300 hidden sm:inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                HD 24kHz
              </span>
              <button
                type="button"
                onClick={() => setIsLiveCall(false)}
                className="flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs text-slate-200 hover:bg-white/20 transition active:scale-95"
                title="Thu nhỏ về nhắn tin (cuộc gọi vẫn tiếp tục)"
              >
                <Icon name="chat" size={13} />
                <span>Nhắn tin</span>
              </button>
            </div>
          </div>

          {/* Hero Giant Avatar ("cho nó bự lên rồi nói chuyện") */}
          <div className="relative flex-1 flex flex-col items-center justify-center p-4 min-h-0 select-none z-10">
            {/* Vòng hào quang năng lượng phản hồi theo âm lượng */}
            <div
              className="absolute rounded-full bg-gradient-to-r from-sky-500/20 via-cyan-400/25 to-amber-500/20 blur-2xl pointer-events-none transition-all duration-150"
              style={{
                width: `${240 + Math.round(voice.audioLevel * 100)}px`,
                height: `${240 + Math.round(voice.audioLevel * 100)}px`,
                opacity: 0.5 + voice.audioLevel * 0.5,
              }}
            />

            {/* Vòng tròn Hologram */}
            <div
              className="absolute rounded-full border border-sky-400/30 pointer-events-none transition-all duration-300 animate-pulse"
              style={{
                width: `${280 + Math.round(voice.audioLevel * 50)}px`,
                height: `${280 + Math.round(voice.audioLevel * 50)}px`,
              }}
            />

            {/* Avatar Tinh Linh KHỔNG LỒ */}
            <div className="relative z-10 transition-transform duration-300 hover:scale-105">
              <Avatar2D
                size={isMobile ? 200 : 270}
                speaking={isSpeaking}
                listening={isListening}
                mouthOpen={mouthOpen}
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
                showBadge={false}
                showSparkles={true}
                showHoloRing={true}
                showFloorShadow={true}
                showTooltip={false}
                priority
              />
            </div>

            {/* Danh tính & Trạng thái lời nói */}
            <div className="mt-2.5 text-center z-10 px-4">
              <div className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2">
                <h4 className="text-base font-bold text-slate-100 whitespace-nowrap">
                  {profile.label}
                </h4>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-sky-500/20 border border-sky-400/40 text-sky-300 font-semibold whitespace-nowrap">
                  Bạn đồng hành AI
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-300/90 font-medium">
                {voice.state === "connecting" && "Đang kết nối âm thanh trực tiếp…"}
                {voice.state === "listening" && "🎙️ Tinh Linh đang nghe… Cứ nói tự nhiên nhé!"}
                {voice.state === "processing" && "🔮 Đang tra cứu quy trình ca trực…"}
                {voice.state === "speaking" && "✨ Tinh Linh đang trò chuyện cùng bạn…"}
                {voice.state === "idle" && "🌟 Đang kết nối · Nói bất cứ câu hỏi nào với Tinh Linh"}
                {voice.state === "error" && "⚠️ Lỗi âm thanh, bấm nút gác máy để thử lại"}
              </p>
            </div>

            {/* Equalizer sóng âm Realtime */}
            <div className="flex items-center justify-center gap-1 mt-3 h-7 z-10">
              {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15].map((idx) => {
                const height = Math.max(
                  4,
                  Math.min(
                    30,
                    Math.round(
                      voice.audioLevel * 30 * (0.6 + Math.sin(idx * 0.6) * 0.4) + (isVoiceActive ? 6 : 2)
                    )
                  )
                );
                return (
                  <span
                    key={idx}
                    className="w-1 rounded-full bg-gradient-to-t from-emerald-500 to-cyan-300 transition-all duration-75"
                    style={{ height: `${height}px` }}
                  />
                );
              })}
            </div>

            {/* Phụ đề trực tiếp (Live Captions) */}
            {(latestUserTranscript || latestCopilotTranscript) && (
              <div className="mt-3 w-full max-w-md rounded-2xl border border-white/10 bg-slate-950/75 p-3 text-xs shadow-2xl backdrop-blur-md z-10 transition-all animate-in fade-in slide-in-from-bottom-2">
                {latestUserTranscript && (
                  <p className="text-amber-300/95 line-clamp-2">
                    <strong className="text-amber-400">🗣️ Bạn:</strong> {latestUserTranscript}
                  </p>
                )}
                {latestCopilotTranscript && (
                  <p className="text-sky-200/95 mt-1 line-clamp-2">
                    <strong className="text-sky-300">✨ Tinh Linh:</strong> {latestCopilotTranscript}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Thanh điều khiển cuộc gọi dưới đáy */}
          <div className="relative z-10 flex shrink-0 items-center justify-center gap-6 p-4 border-t border-white/10 bg-slate-950/60 backdrop-blur-md">
            {/* Mute Mic */}
            <button
              type="button"
              onClick={() => setIsMuted((m) => !m)}
              className={`flex flex-col items-center gap-1.5 transition active:scale-95 ${
                isMuted ? "text-rose-400" : "text-slate-300 hover:text-white"
              }`}
              title={isMuted ? "Bật lại mic" : "Tắt mic"}
            >
              <div
                className={`flex h-11 w-11 items-center justify-center rounded-full border transition ${
                  isMuted
                    ? "border-rose-500 bg-rose-500/20 text-rose-400"
                    : "border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700"
                }`}
              >
                <Icon name="microphone" size={18} />
              </div>
              <span className="text-[10px] font-medium">{isMuted ? "Đã tắt mic" : "Micro"}</span>
            </button>

            {/* NÚT KẾT THÚC CUỘC GỌI TO ĐẸP */}
            <button
              type="button"
              onClick={handleEndLiveCall}
              className="flex flex-col items-center gap-1.5 group transition active:scale-95"
              title="Kết thúc cuộc gọi trực tiếp"
            >
              <div className="flex h-13 w-13 items-center justify-center rounded-full bg-rose-600 text-white shadow-xl shadow-rose-600/50 group-hover:bg-rose-500 group-hover:scale-105 transition">
                <Icon name="phone" size={24} />
              </div>
              <span className="text-[11px] font-bold text-rose-400">Gác máy</span>
            </button>

            {/* Chuyển về Chat */}
            <button
              type="button"
              onClick={() => setIsLiveCall(false)}
              className="flex flex-col items-center gap-1.5 text-slate-300 hover:text-white transition active:scale-95"
              title="Quay lại giao diện nhắn tin"
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700">
                <Icon name="chat" size={18} />
              </div>
              <span className="text-[10px] font-medium">Nhắn tin</span>
            </button>
          </div>
        </div>
      )}

      {/* ── GIAO DIỆN NHẮN TIN CHÍNH (COMPANION MESSENGER) ── */}
      {/* 1. Header bạn đồng hành */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-800/80 bg-slate-900/90 px-4 py-2.5 select-none backdrop-blur-md z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="relative shrink-0 -my-1">
            <Avatar2D
              size={44}
              speaking={isSpeaking || Boolean(streamingId)}
              listening={isListening}
              mouthOpen={mouthOpen}
              mood={chatMood}
              showBadge={false}
              showSparkles={false}
              showTooltip={false}
              priority
            />
            <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-slate-900 animate-pulse" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-bold text-slate-100 truncate flex items-center gap-1.5">
              {profile.label}
            </h3>
            <p className="text-[11px] text-slate-400 truncate flex items-center gap-1.5">
              {streamingId || loading ? (
                <span className="text-amber-300 font-medium animate-pulse">✨ Đang soạn tin nhắn...</span>
              ) : isSpeaking ? (
                <span className="text-cyan-300 font-medium animate-pulse">🎙️ Đang trả lời bạn...</span>
              ) : (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  <span>Sẵn sàng hỗ trợ ca trực</span>
                </>
              )}
            </p>
          </div>
        </div>

        {/* Cụm nút hành động: NÚT GỌI LIVE DUY NHẤT THEO YÊU CẦU NGƯỜI DÙNG */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={handleStartLiveCall}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500 text-slate-950 font-bold text-xs shadow-md shadow-emerald-500/25 hover:brightness-110 hover:scale-105 active:scale-95 transition-all duration-200"
            title="Bấm để gọi điện trực tiếp với Tinh Linh"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-slate-950 opacity-80" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-slate-950" />
            </span>
            <Icon name="phone" size={13} />
            <span>Gọi Live</span>
          </button>
        </div>
      </div>

      {/* 2. Danh sách tin nhắn phong cách Instant Messaging */}
      <div
        onScroll={(e) => {
          const target = e.currentTarget;
          const isUp = target.scrollHeight - target.scrollTop - target.clientHeight > 120;
          setShowScrollBottom(isUp);
        }}
        className="relative flex-1 space-y-4 overflow-y-auto p-4 text-xs"
      >
        {/* Phân cách ngày */}
        <div className="flex items-center justify-center my-1 select-none">
          <span className="rounded-full bg-slate-900 border border-slate-800 px-3 py-0.5 text-[10px] font-medium text-slate-400 shadow-sm">
            Hôm nay · Trợ lý Vận Hành
          </span>
        </div>

        {/* Danh sách tin nhắn */}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-2.5 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
          >
            {/* Avatar Tinh Linh bên cạnh tin nhắn AI — bản tĩnh (0 interval) để list 20 tin không lag */}
            {msg.sender === "copilot" && (
              <div className="shrink-0 -mt-1 select-none">
                <AvatarStatic size={34} mood={chatMood} />
              </div>
            )}

            {/* Bong bóng tin nhắn */}
            <div
              className={`relative max-w-[85%] sm:max-w-[78%] p-3.5 shadow-sm transition-all ${
                msg.sender === "user"
                  ? "rounded-2xl rounded-tr-sm bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-medium"
                  : "rounded-2xl rounded-tl-sm bg-slate-900 border border-slate-800 text-slate-100"
              }`}
            >
              {/* Nhãn nguồn chế độ */}
              {msg.sender === "copilot" && msg.id !== "welcome" && (
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1 rounded bg-slate-950/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-400">
                    {msg.agent_mode === "live" ? "AI trực tiếp" : msg.agent_mode === "replay" ? "Mẫu ca" : "Tinh Linh"}
                  </span>
                  <span className="text-[10px] text-slate-400">{msg.timestamp}</span>
                </div>
              )}

              {/* Tệp đính kèm */}
              {msg.attachments && msg.attachments.length > 0 && (
                <div className="mb-2 space-y-1.5">
                  {msg.attachments.map((att, idx) => {
                    const mediaUrl = resolveMediaUrl(att.url);
                    const isImg =
                      att.mime_type?.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/i.test(att.url);
                    if (isImg) {
                      return (
                        <div key={idx} className="overflow-hidden rounded-xl border border-black/20 max-w-[260px]">
                          <a href={mediaUrl} target="_blank" rel="noreferrer">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={mediaUrl}
                              alt={att.filename || "Đính kèm"}
                              className="max-h-48 w-auto object-cover rounded-xl hover:opacity-90 transition"
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
                        className="flex items-center gap-2 rounded-lg bg-black/10 px-2.5 py-1.5 text-xs transition hover:bg-black/20"
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

              {/* Nội dung tin nhắn */}
              <div className="whitespace-pre-wrap leading-relaxed text-[13px]">
                <ChatText text={msg.text} />
                {streamingId === msg.id && (
                  <span className="ml-1 inline-block w-1.5 h-3.5 align-middle bg-amber-400 animate-pulse" />
                )}
              </div>

              {/* Thẻ đề xuất hành động (Action Proposal) */}
              {msg.action_proposal && (
                <div className="mt-3">
                  <ActionProposalCard
                    proposal={msg.action_proposal}
                    onExecuted={(updated) => chat.updateProposal(msg.id, updated)}
                  />
                </div>
              )}

              {/* Gợi ý mở đầu kèm 4 Thao tác nhanh cho ca trực */}
              {msg.sender === "copilot" && msg.id === "welcome" && profile.quickPrompts.length > 0 && (
                <div className="mt-3 pt-2.5 border-t border-slate-800 space-y-2">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    <span>⚡</span> Thao tác nhanh cho ca trực:
                  </p>
                  <div className={mode === "page" ? "grid grid-cols-1 sm:grid-cols-2 gap-2" : "grid grid-cols-1 gap-1.5"}>
                    {profile.quickPrompts.slice(0, 4).map((qp, idx) => (
                      <button
                        key={`hero-qp-${idx}`}
                        type="button"
                        onClick={() => send(qp)}
                        disabled={loading || Boolean(streamingId)}
                        className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-950/70 p-2.5 text-left text-xs text-slate-200 transition hover:border-amber-400 hover:bg-amber-400/10 hover:text-amber-300 disabled:opacity-50 group"
                      >
                        <span className="shrink-0 text-amber-400 group-hover:scale-110 transition">
                          {idx === 0 ? "📅" : idx === 1 ? "⚠️" : idx === 2 ? "🥛" : "✨"}
                        </span>
                        <span className="leading-snug font-medium line-clamp-2">{qp}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Chân tin nhắn: Sao chép & thời gian */}
              <div
                className={`mt-2 flex items-center justify-between text-[10px] ${
                  msg.sender === "user" ? "text-slate-900/70" : "text-slate-400"
                }`}
              >
                <span>{msg.sender === "user" ? msg.timestamp : null}</span>
                {msg.sender === "copilot" && msg.text && msg.id !== "welcome" && (
                  <button
                    type="button"
                    onClick={() => {
                      if (typeof navigator !== "undefined" && navigator.clipboard) {
                        navigator.clipboard.writeText(msg.text);
                      }
                      setCopiedId(msg.id);
                      setTimeout(() => setCopiedId(null), 2000);
                    }}
                    className="flex items-center gap-1 hover:text-amber-400 transition ml-auto"
                    title="Sao chép nội dung tin nhắn"
                  >
                    {copiedId === msg.id ? (
                      <span className="text-emerald-400 font-bold">✓ Đã chép</span>
                    ) : (
                      <>
                        <Icon name="clipboard" size={11} />
                        <span>Sao chép</span>
                      </>
                    )}
                  </button>
                )}
                {msg.sender === "user" && <span className="ml-1 text-slate-900">✓✓</span>}
              </div>
            </div>
          </div>
        ))}

        {/* Typing indicator khi Tinh Linh đang soạn câu trả lời */}
        {(streamingId || (loading && !messages.some((m) => m.id === streamingId))) && (
          <div className="flex gap-2.5 justify-start items-end animate-in fade-in">
            <div className="shrink-0">
              <AvatarStatic size={32} mood="processing" />
            </div>
            <div className="rounded-2xl rounded-tl-sm bg-slate-900 border border-slate-800 px-4 py-3 flex items-center gap-1.5 shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce" />
              <span className="text-[11px] text-slate-400 ml-1.5">Tinh Linh đang soạn câu trả lời...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Nút FAB cuộn xuống tin nhắn mới nhất */}
      {showScrollBottom && (
        <button
          type="button"
          onClick={() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })}
          className="absolute bottom-20 right-5 z-20 flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-slate-900/90 px-3 py-1.5 text-xs text-amber-300 shadow-xl backdrop-blur-md hover:bg-slate-800 hover:scale-105 active:scale-95 transition"
        >
          <span>↓ Xuống tin nhắn mới</span>
        </button>
      )}

      {/* 3. Thanh nhập tin nhắn sạch đẹp phong cách Instant Messenger */}
      <div className="shrink-0 border-t border-slate-800/80 bg-slate-900/90 p-3 backdrop-blur-md z-10">
        {/* Preview file đính kèm nếu có */}
        {attachedFile && (
          <div className="mb-2 flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-950 p-2 text-xs">
            {attachedFile.isImage ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={attachedFile.previewUrl}
                alt="Xem trước"
                className="h-10 w-10 object-cover rounded-lg border border-slate-800"
              />
            ) : (
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-slate-300">
                <Icon name="attachment" size={18} />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-slate-200">{attachedFile.file.name}</p>
              <p className="text-[10px] text-slate-400">
                {(attachedFile.file.size / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              type="button"
              onClick={handleRemoveAttachment}
              className="p-1 text-slate-400 hover:text-rose-400 transition"
              title="Xóa tệp đính kèm"
            >
              ✕
            </button>
          </div>
        )}

        {uploadError && <p className="mb-2 text-xs text-rose-400 font-medium">{uploadError}</p>}

        <form onSubmit={handleFormSubmit} className="flex items-center gap-2">
          {/* File attachment input */}
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
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-slate-700/80 bg-slate-800/80 text-slate-300 hover:border-amber-400 hover:text-amber-300 transition disabled:opacity-40"
            title="Đính kèm ảnh hoặc tài liệu"
          >
            <Icon name="attachment" size={16} />
          </button>

          {/* Ô nhập tin nhắn phong cách messenger */}
          <div className="relative flex-1">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                attachedFile ? "Thêm ghi chú cho tệp đính kèm..." : "Nhắn tin cho Tinh Linh..."
              }
              disabled={loading || Boolean(streamingId) || uploading}
              className="w-full rounded-full border border-slate-700/80 bg-slate-800/90 pl-4 pr-9 py-2 text-xs text-slate-100 placeholder:text-slate-400 focus:outline-none focus:border-amber-400 focus:ring-1 focus:ring-amber-400 disabled:opacity-50 transition"
            />
            {input.trim().length > 0 && (
              <button
                type="button"
                onClick={() => setInput("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-100 transition"
                title="Xóa chữ đang gõ"
              >
                ✕
              </button>
            )}
          </div>

          {/* Nút gửi tin nhắn */}
          <button
            type="submit"
            disabled={loading || Boolean(streamingId) || uploading || (!input.trim() && !attachedFile)}
            className="flex h-9 px-4 shrink-0 items-center justify-center gap-1.5 rounded-full bg-gradient-to-r from-amber-400 to-amber-500 text-slate-950 font-bold text-xs shadow-md shadow-amber-500/20 hover:brightness-110 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {uploading ? (
              "Đang tải..."
            ) : (
              <>
                <span>Gửi</span>
                <Icon name="send" size={13} />
              </>
            )}
          </button>
        </form>

        <p className="mt-1.5 text-center text-[10px] text-slate-500">
          Nhấn Enter để gửi · Bấm nút <strong className="text-emerald-400 font-semibold">Gọi Live</strong> ở trên để nói chuyện trực tiếp
        </p>
      </div>
    </div>
  );
}