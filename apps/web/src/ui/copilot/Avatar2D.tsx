"use client";

import React, { useState, useEffect, useRef, useMemo, memo } from "react";

export type AvatarMood =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "happy"
  | "worried"
  | "success"
  | "error"
  | "greeting"
  | "sleepy"
  | "poke"
  | "alert";

export interface AvatarProps {
  mouthOpen?: number;
  speaking: boolean;
  listening: boolean;
  mood?: AvatarMood;
  size?: number;
  useSprites?: boolean;
  showBadge?: boolean;
  showFloorShadow?: boolean;
  showHoloRing?: boolean;
  showSparkles?: boolean;
  showTooltip?: boolean;
  /** Ép tắt toàn bộ animation (dùng cho list tin nhắn). Mặc định: size < 48 tự tắt. */
  animated?: boolean;
  /** Ưu tiên tải ảnh (header/live). List dùng lazy. */
  priority?: boolean;
}

// Fallback tĩnh khi không dùng sprite
const MOOD_IMAGES: Record<string, string> = {
  idle: "/copilot/fairy/fairy-idle.webp",
  greeting: "/copilot/fairy/fairy-greeting.webp",
  listening: "/copilot/fairy/fairy-listening.webp",
  processing: "/copilot/fairy/fairy-processing.webp",
  speaking: "/copilot/fairy/fairy-speaking.webp",
  happy: "/copilot/fairy/fairy-happy.webp",
  success: "/copilot/fairy/fairy-success.webp",
  worried: "/copilot/fairy/fairy-worried.webp",
  alert: "/copilot/fairy/fairy-worried.webp",
  error: "/copilot/fairy/fairy-error.webp",
  sleepy: "/copilot/fairy/fairy-sleepy.webp",
  poke: "/copilot/fairy/fairy-happy.webp",
};

const MOOD_LABELS: Record<string, string> = {
  idle: "Hệ thống AG",
  greeting: "Xin chào Ký chủ",
  listening: "Đang nghe Ký chủ",
  processing: "Đang tính toán…",
  speaking: "Hệ thống đang nói",
  happy: "Ký chủ xuất sắc!",
  success: "Nhiệm vụ hoàn thành",
  worried: "Cảnh báo Ký chủ",
  alert: "Cảnh báo ca trực",
  error: "Hệ thống lỗi",
  sleepy: "Hệ thống nghỉ ngơi",
  poke: "Yêu Ký chủ!",
};

interface MoodTheme {
  glowBg: string;
  ringBorder: string;
  dotColor: string;
  badgeBorder: string;
  badgeBg: string;
  badgeText: string;
  shadowColor: string;
}

const MOOD_THEMES: Record<string, MoodTheme> = {
  idle: {
    glowBg: "radial-gradient(circle, rgba(56,189,248,0.3) 0%, rgba(56,189,248,0.08) 55%, transparent 75%)",
    ringBorder: "rgba(56,189,248,0.35)",
    dotColor: "#38bdf8",
    badgeBorder: "border-sky-400/50",
    badgeBg: "bg-slate-900/90",
    badgeText: "text-sky-300",
    shadowColor: "rgba(56,189,248,0.4)",
  },
  greeting: {
    glowBg: "radial-gradient(circle, rgba(125,211,252,0.35) 0%, rgba(56,189,248,0.1) 55%, transparent 75%)",
    ringBorder: "rgba(125,211,252,0.45)",
    dotColor: "#7dd3fc",
    badgeBorder: "border-sky-400/60",
    badgeBg: "bg-slate-900/90",
    badgeText: "text-sky-200",
    shadowColor: "rgba(125,211,252,0.4)",
  },
  listening: {
    glowBg: "radial-gradient(circle, rgba(52,211,153,0.35) 0%, rgba(52,211,153,0.1) 55%, transparent 75%)",
    ringBorder: "rgba(52,211,153,0.45)",
    dotColor: "#34d399",
    badgeBorder: "border-emerald-400/70",
    badgeBg: "bg-emerald-950/90",
    badgeText: "text-emerald-200",
    shadowColor: "rgba(52,211,153,0.4)",
  },
  processing: {
    glowBg: "radial-gradient(circle, rgba(251,191,36,0.4) 0%, rgba(251,191,36,0.12) 55%, transparent 75%)",
    ringBorder: "rgba(251,191,36,0.55)",
    dotColor: "#fbbf24",
    badgeBorder: "border-amber-400/70",
    badgeBg: "bg-amber-950/90",
    badgeText: "text-amber-200",
    shadowColor: "rgba(251,191,36,0.45)",
  },
  speaking: {
    glowBg: "radial-gradient(circle, rgba(34,211,238,0.45) 0%, rgba(34,211,238,0.15) 55%, transparent 75%)",
    ringBorder: "rgba(34,211,238,0.6)",
    dotColor: "#22d3ee",
    badgeBorder: "border-cyan-400/80 ring-1 ring-cyan-400/40",
    badgeBg: "bg-cyan-950/90",
    badgeText: "text-cyan-200",
    shadowColor: "rgba(34,211,238,0.5)",
  },
  success: {
    glowBg: "radial-gradient(circle, rgba(245,158,11,0.45) 0%, rgba(245,158,11,0.15) 55%, transparent 75%)",
    ringBorder: "rgba(245,158,11,0.6)",
    dotColor: "#f59e0b",
    badgeBorder: "border-amber-400/80 ring-1 ring-amber-400/30",
    badgeBg: "bg-amber-950/90",
    badgeText: "text-amber-300",
    shadowColor: "rgba(245,158,11,0.5)",
  },
  happy: {
    glowBg: "radial-gradient(circle, rgba(245,158,11,0.45) 0%, rgba(245,158,11,0.15) 55%, transparent 75%)",
    ringBorder: "rgba(245,158,11,0.6)",
    dotColor: "#f59e0b",
    badgeBorder: "border-amber-400/80 ring-1 ring-amber-400/30",
    badgeBg: "bg-amber-950/90",
    badgeText: "text-amber-300",
    shadowColor: "rgba(245,158,11,0.5)",
  },
  poke: {
    glowBg: "radial-gradient(circle, rgba(244,114,182,0.45) 0%, rgba(244,114,182,0.15) 55%, transparent 75%)",
    ringBorder: "rgba(244,114,182,0.6)",
    dotColor: "#f472b6",
    badgeBorder: "border-pink-400/80 ring-1 ring-pink-400/40",
    badgeBg: "bg-pink-950/90",
    badgeText: "text-pink-300",
    shadowColor: "rgba(244,114,182,0.5)",
  },
  alert: {
    glowBg: "radial-gradient(circle, rgba(244,63,94,0.4) 0%, rgba(244,63,94,0.12) 55%, transparent 75%)",
    ringBorder: "rgba(244,63,94,0.6)",
    dotColor: "#f43f5e",
    badgeBorder: "border-rose-400/80",
    badgeBg: "bg-rose-950/90",
    badgeText: "text-rose-300",
    shadowColor: "rgba(244,63,94,0.45)",
  },
  worried: {
    glowBg: "radial-gradient(circle, rgba(244,63,94,0.4) 0%, rgba(244,63,94,0.12) 55%, transparent 75%)",
    ringBorder: "rgba(244,63,94,0.6)",
    dotColor: "#f43f5e",
    badgeBorder: "border-rose-400/80",
    badgeBg: "bg-rose-950/90",
    badgeText: "text-rose-300",
    shadowColor: "rgba(244,63,94,0.45)",
  },
  error: {
    glowBg: "radial-gradient(circle, rgba(239,68,68,0.45) 0%, rgba(239,68,68,0.15) 55%, transparent 75%)",
    ringBorder: "rgba(239,68,68,0.65)",
    dotColor: "#ef4444",
    badgeBorder: "border-red-400/80",
    badgeBg: "bg-red-950/90",
    badgeText: "text-red-300",
    shadowColor: "rgba(239,68,68,0.5)",
  },
  sleepy: {
    glowBg: "radial-gradient(circle, rgba(129,140,248,0.3) 0%, rgba(129,140,248,0.08) 55%, transparent 75%)",
    ringBorder: "rgba(129,140,248,0.4)",
    dotColor: "#818cf8",
    badgeBorder: "border-indigo-400/60",
    badgeBg: "bg-indigo-950/90",
    badgeText: "text-indigo-300",
    shadowColor: "rgba(129,140,248,0.35)",
  },
};

// Cấu hình danh sách frame của từng hành động (86 frame đã ổn định trục cơ thể và bổ sung in-between)
interface ActionSequence {
  frames: string[];
  frameInterval: number;
  loop: boolean;
}

const ACTION_SEQUENCES: Record<string, ActionSequence> = {
  idle: {
    frames: ["idle_01", "idle_02", "idle_03", "idle_04", "idle_05", "idle_06", "idle_07", "idle_08"],
    frameInterval: 125,
    loop: true,
  },
  blink: {
    // Chớp mắt nhịp nhàng trọn vẹn theo 8 frame chu kỳ vỗ cánh (tránh đứt gãy sải cánh)
    frames: ["blink_01", "blink_02", "blink_03", "blink_04", "blink_05", "blink_06", "blink_07", "blink_08"],
    frameInterval: 80,
    loop: false,
  },
  greeting: {
    // Chuỗi chào hỏi anime tự nhiên: Đưa tay lên ngực -> Vẫy tay chào vui tươi -> Tạo dáng Peace chiến thắng -> Hạ tay về hông
    frames: [
      "greeting_10", "greeting_01",
      "greeting_02", "greeting_07", "greeting_02", "greeting_07",
      "greeting_08", "greeting_08", "greeting_08",
      "greeting_09", "greeting_10"
    ],
    frameInterval: 120,
    loop: false,
  },
  listening: {
    frames: ["listening_01", "listening_02", "listening_03", "listening_04", "listening_05", "listening_06"],
    frameInterval: 140,
    loop: true,
  },
  processing: {
    // FIX 2026-10: bỏ processing_04/05/06 (lạc costume váy teal giữa bộ giáp trắng/gold,
    // review contact-sheet thấy nhấp nháy mỗi vòng). Giữ 01-03 tụ lực + 07-08 tung chiêu.
    frames: ["processing_01", "processing_02", "processing_03", "processing_02", "processing_07", "processing_08", "processing_07", "processing_08"],
    frameInterval: 110,
    loop: true,
  },
  speaking: {
    frames: ["speaking_01", "speaking_02", "speaking_03", "speaking_04", "speaking_05", "speaking_06"],
    frameInterval: 110,
    loop: true,
  },
  happy: {
    // Nhảy chân sáo tươi vui, hai tay vung vẫy chúc mừng rạng rỡ (g_03 & g_04)
    frames: [
      "greeting_10", "greeting_03", "greeting_04", "greeting_03", "greeting_04", "greeting_03", "greeting_04",
      "greeting_08", "greeting_08", "greeting_09", "greeting_10"
    ],
    frameInterval: 120,
    loop: false,
  },
  success: {
    frames: ["success_01", "success_02", "success_03", "success_04", "success_05", "success_06", "success_07", "success_08", "success_09", "success_10", "greeting_09", "greeting_10"],
    frameInterval: 120,
    loop: false,
  },
  worried: {
    // FIX 2026-10: bỏ alert_05 (tóc hồng 1 frame đơn lẻ giữa 7 frame tóc xanh,
    // loop sẽ chớp đỏ như glitch). Giữ alert_04 2 nhịp tạo điểm dừng lo lắng tự nhiên.
    frames: ["alert_01", "alert_02", "alert_03", "alert_04", "alert_04", "alert_06", "alert_07", "alert_08"],
    frameInterval: 130,
    loop: true,
  },
  alert: {
    frames: ["alert_01", "alert_02", "alert_03", "alert_04", "alert_04", "alert_06", "alert_07", "alert_08"],
    frameInterval: 130,
    loop: true,
  },
  error: {
    frames: ["error_01", "error_02", "error_03", "error_04", "error_05", "error_06", "greeting_09", "greeting_10"],
    frameInterval: 140,
    loop: false,
  },
  sleepy: {
    frames: ["sleepy_01", "sleepy_02", "sleepy_03", "sleepy_04", "sleepy_05", "sleepy_06", "sleepy_07", "sleepy_08"],
    frameInterval: 160,
    loop: true,
  },
  poke: {
    // Bắn tim e thẹn rồi hạ tay mềm mại về hông
    frames: ["poke_01", "poke_02", "poke_03", "poke_04", "poke_05", "poke_04", "greeting_09", "greeting_10"],
    frameInterval: 130,
    loop: false,
  },
};

/** Ưu tiên webp (nhẹ ~5x so với png) — fallback png khi webp chưa có. */
function getSpriteCandidates(frameName: string): string[] {
  return [`/copilot/sprites/${frameName}.webp`, `/copilot/sprites/${frameName}.png`];
}

function getSpritePath(frameName: string): string {
  return `/copilot/sprites/${frameName}.png`;
}

// Cache preload để không tạo Image trùng cho cùng 1 src.
const PRELOADED = new Set<string>();
function preloadSrc(src: string) {
  if (typeof window === "undefined" || PRELOADED.has(src)) return;
  PRELOADED.add(src);
  const img = new window.Image();
  img.decoding = "async";
  img.src = src;
}

export function preloadAvatarMood(mood: AvatarMood) {
  const seq = ACTION_SEQUENCES[mood] || ACTION_SEQUENCES.idle;
  // Chỉ preload frame đầu + toàn bộ sequence của mood hiện tại (tránh tải 20MB một lúc).
  seq.frames.forEach((f) => preloadSrc(getSpritePath(f)));
}

/** Preload các mood nóng (idle đã có sẵn) khi trình duyệt rảnh — chuyển mood không giật frame đầu. */
export function preloadAvatarHot() {
  (["speaking", "listening", "processing", "greeting"] as AvatarMood[]).forEach(preloadAvatarMood);
}

/**
 * Avatar tĩnh cho list tin nhắn / typing — 0 interval, 0 keyframes, 0 re-render.
 * Dùng webp nhẹ, lazy-load, không gắn hiệu ứng nặng.
 */
export const AvatarStatic = memo(function AvatarStatic({
  mood = "idle",
  size = 34,
  label,
}: {
  mood?: AvatarMood;
  size?: number;
  label?: string;
}) {
  const theme = MOOD_THEMES[mood] || MOOD_THEMES.idle;
  const text = label || MOOD_LABELS[mood] || "Hệ thống AG";
  return (
    <span
      className="relative inline-flex shrink-0 select-none items-center justify-center overflow-hidden rounded-full"
      style={{ width: size, height: size, background: theme.glowBg }}
      role="img"
      aria-label={text}
      title={text}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={MOOD_IMAGES[mood] || MOOD_IMAGES.idle}
        alt=""
        width={size}
        height={size}
        loading="lazy"
        decoding="async"
        draggable={false}
        className="h-full w-full object-contain"
        data-fallback="1"
        onError={(e) => {
          const target = e.currentTarget;
          if (target.dataset.fbk === "1") return;
          target.dataset.fbk = "1";
          // webp lỗi (chưa có file) -> thử png cùng tên, cuối cùng về idle.
          const src = target.src;
          if (src.endsWith(".webp")) {
            target.src = src.replace(".webp", ".png");
          } else if (!src.endsWith("fairy-idle.webp")) {
            target.src = MOOD_IMAGES.idle;
          }
        }}
      />
    </span>
  );
});

/**
 * Avatar Tinh Linh Hệ Thống (Fairy System AI) cho AG-COPILOT.
 *
 * Tối ưu P0:
 * - Keyframes dùng chung trong globals.css (`.nq-fairy-*`), không còn <style jsx> mỗi instance.
 * - size < 48 (list chat) tự render AvatarStatic — 0 setInterval.
 * - Không còn setState trong updater (bug StrictMode); frame speaking suy trực tiếp từ mouthOpen.
 * - Ảnh thử webp trước, png sau; guard onError chống loop vô hạn.
 * - Holo ring chỉ bật từ size >= 40 (giữ header 44, tắt list 32-34).
 */
export const Avatar2D = memo(function Avatar2D({
  mouthOpen = 0,
  speaking,
  listening,
  mood: explicitMood,
  size = 96,
  useSprites = true,
  showBadge,
  showFloorShadow,
  showHoloRing,
  showSparkles,
  showTooltip = true,
  animated,
  priority = false,
}: AvatarProps) {
  const shouldAnimate = animated ?? size >= 48;

  // Suy luận mood — useMemo để message list memo so sánh được.
  const activeMood: AvatarMood = useMemo(() => {
    // isPoked xử lý ở state bên dưới; ở đây chỉ suy từ props.
    return (
      explicitMood || (speaking ? "speaking" : listening ? "listening" : "idle")
    );
  }, [explicitMood, speaking, listening]);

  // Tôn trọng reduced-motion: sprite swapping cũng là animation — đứng yên hẳn.
  // useState initializer chạy 1 lần, đặt trước mọi return nên không phạm luật hooks.
  const [reducedMotion] = useState(
    () =>
      typeof window !== "undefined" &&
      !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );

  // Avatar nhỏ trong list / reduced-motion: render tĩnh, không gắn interval/effect nặng.
  if (!shouldAnimate || reducedMotion) {
    return <AvatarStatic mood={activeMood} size={size} />;
  }

  return (
    <AvatarAnimated
      mouthOpen={mouthOpen}
      speaking={speaking}
      listening={listening}
      activeMood={activeMood}
      size={size}
      useSprites={useSprites}
      showBadge={showBadge}
      showFloorShadow={showFloorShadow}
      showHoloRing={showHoloRing}
      showSparkles={showSparkles}
      showTooltip={showTooltip}
      priority={priority}
    />
  );
});

const SYSTEM_TIPS = [
  "Đinh! Ký chủ cần hỗ trợ kiểm tra ca làm việc không?",
  "Hệ thống luôn sẵn sàng nhận lệnh từ Ký chủ!",
  "Hôm nay các bạn Barista đang hoạt động rất tốt!",
  "Ký chủ nhớ duyệt bảng lương và chốt ca đúng giờ nhé!",
];

function AvatarAnimated({
  mouthOpen = 0,
  speaking,
  listening,
  activeMood: moodProp,
  size = 96,
  useSprites = true,
  showBadge,
  showFloorShadow,
  showHoloRing,
  showSparkles,
  showTooltip = true,
  priority = false,
}: {
  mouthOpen?: number;
  speaking: boolean;
  listening: boolean;
  activeMood: AvatarMood;
  size?: number;
  useSprites?: boolean;
  showBadge?: boolean;
  showFloorShadow?: boolean;
  showHoloRing?: boolean;
  showSparkles?: boolean;
  showTooltip?: boolean;
  priority?: boolean;
}) {
  const [isHovered, setIsHovered] = useState(false);
  const [tipIndex, setTipIndex] = useState(0);
  const [isPoked, setIsPoked] = useState(false);
  const [isBlinking, setIsBlinking] = useState(false);
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const finishFlagRef = useRef<"blink" | "poke" | null>(null);

  // Cấu hình linh hoạt hiển thị hiệu ứng theo kích cỡ nếu không truyền prop cụ thể
  // P0: holo ring chỉ từ 40px (giữ header 44, tắt list 32-34 để đỡ compositing).
  const hasBadge = showBadge !== undefined ? showBadge : size >= 60;
  const hasFloorShadow = showFloorShadow !== undefined ? showFloorShadow : size >= 56;
  const hasHoloRing = showHoloRing !== undefined ? showHoloRing : size >= 40;
  const hasSparkles = showSparkles !== undefined ? showSparkles : size >= 68;

  const activeMood: AvatarMood = isPoked ? "poke" : moodProp;

  const label = MOOD_LABELS[activeMood] || "Hệ thống AG";
  const theme = MOOD_THEMES[activeMood] || MOOD_THEMES.idle;

  // Clamp mouthOpen 0-1 để rung nhẹ theo biên độ giọng nói
  const open = Math.max(0, Math.min(1, mouthOpen));
  const audioScale = speaking ? 1 + open * 0.08 : 1;

  // Quyết định sequence dựa trên mood và blink
  const currentAction = isBlinking && activeMood === "idle" ? "blink" : activeMood;
  const sequence = ACTION_SEQUENCES[currentAction] || ACTION_SEQUENCES.idle;
  const framesLen = sequence.frames.length;
  const frameInterval = sequence.frameInterval;
  const isLoop = sequence.loop;

  // Preload sequence của mood hiện tại (theo từng mood, không tải 89 file một lúc).
  useEffect(() => {
    if (!useSprites) return;
    // Idle + speaking/listening là nóng nhất — preload ngay khi đổi mood.
    const seq = ACTION_SEQUENCES[activeMood] || ACTION_SEQUENCES.idle;
    seq.frames.forEach((f) => preloadSrc(getSpritePath(f)));
  }, [activeMood, useSprites]);

  // Tự động chớp mắt ngẫu nhiên sau mỗi 3.5 - 6 giây khi ở Idle
  useEffect(() => {
    if (activeMood !== "idle" || isPoked || isBlinking) return;
    const delay = 3500 + Math.random() * 2500;
    const timer = setTimeout(() => {
      finishFlagRef.current = "blink";
      setIsBlinking(true);
      setCurrentFrameIndex(0);
    }, delay);
    return () => clearTimeout(timer);
  }, [activeMood, isPoked, isBlinking]);

  // Vòng lặp khung hình — chỉ recreate khi đổi sequence, KHÔNG theo mouthOpen (tránh churn 60fps).
  // Khi speaking có lip-sync, frame suy trực tiếp lúc render nên interval tự bỏ qua via ref.
  const lipSyncRef = useRef(false);
  lipSyncRef.current = activeMood === "speaking" && open > 0;
  useEffect(() => {
    if (!useSprites) return;
    const interval = setInterval(() => {
      if (lipSyncRef.current) return;
      if (typeof document !== "undefined" && document.hidden) return; // tab ẩn: đứng yên, đỡ tốn CPU + tránh burst khi quay lại
      setCurrentFrameIndex((prev) => {
        const next = prev + 1;
        if (next >= framesLen) {
          if (finishFlagRef.current === "blink") return 0; // reset ở effect dưới
          if (finishFlagRef.current === "poke") return 0;
          if (activeMood === "sleepy" && framesLen >= 8) return 3;
          return isLoop ? 0 : framesLen - 1;
        }
        return next;
      });
    }, frameInterval);
    return () => clearInterval(interval);
  }, [framesLen, frameInterval, isLoop, activeMood, useSprites]);

  // Hoàn tất blink/poke NGOÀI updater (fix bug setState trong updater).
  useEffect(() => {
    if (finishFlagRef.current === "blink" && currentFrameIndex === 0 && isBlinking) {
      // Đã quay về đầu sau 1 vòng blink -> tắt blink ở tick sau để mắt kịp mở.
      const t = setTimeout(() => {
        finishFlagRef.current = null;
        setIsBlinking(false);
      }, frameInterval);
      return () => clearTimeout(t);
    }
    if (finishFlagRef.current === "poke" && currentFrameIndex >= framesLen - 1) {
      finishFlagRef.current = null;
      setIsPoked(false);
      setCurrentFrameIndex(0);
    }
  }, [currentFrameIndex, framesLen, frameInterval, isBlinking]);

  // Khi blink chạy hết 1 vòng mà chưa tắt (loop=false giữ frame cuối), tự tắt.
  useEffect(() => {
    if (!isBlinking) return;
    if (currentFrameIndex >= framesLen - 1) {
      const t = setTimeout(() => {
        finishFlagRef.current = null;
        setIsBlinking(false);
        setCurrentFrameIndex(0);
      }, frameInterval);
      return () => clearTimeout(t);
    }
  }, [isBlinking, currentFrameIndex, framesLen, frameInterval]);

  // Đổi mood: sequence one-shot (greeting/success/poke) chạy lại từ đầu cho đúng story;
  // sequence loop (idle/listening/processing/...) giữ frame liên tục theo modulo
  // để không giật về frame 0 mỗi lần speaking<->processing đảo nhau khi streaming.
  useEffect(() => {
    const seq = ACTION_SEQUENCES[activeMood] || ACTION_SEQUENCES.idle;
    if (seq.loop) {
      setCurrentFrameIndex((prev) => prev % seq.frames.length);
    } else {
      setCurrentFrameIndex(0);
    }
  }, [activeMood]);

  const handleClick = () => {
    setTipIndex((prev) => (prev + 1) % SYSTEM_TIPS.length);
    if (!isPoked) {
      finishFlagRef.current = "poke";
      setIsPoked(true);
      setCurrentFrameIndex(0);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleClick();
    }
  };

  // Speaking + có amplitude: ánh xạ trực tiếp vào frame miệng, không qua state.
  const displayFrameIndex =
    activeMood === "speaking" && open > 0
      ? Math.min(sequence.frames.length - 1, Math.floor(open * sequence.frames.length))
      : currentFrameIndex;
  const currentFrameName =
    sequence.frames[displayFrameIndex] || sequence.frames[0] || "idle_01";
  const candidates = useMemo(
    () => (useSprites ? getSpriteCandidates(currentFrameName) : []),
    [useSprites, currentFrameName]
  );
  const imageSrc = useSprites
    ? candidates[0]
    : MOOD_IMAGES[activeMood] || MOOD_IMAGES.idle;

  return (
    <div
      className="relative shrink-0 select-none group cursor-pointer"
      style={{ width: size, height: size }}
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      title="Bấm để tương tác với Tinh Linh Hệ Thống"
      aria-label={label}
      role="button"
    >
      {/* 1. Bóng năng lượng tiếp đất phản xạ (Floor energy reflection shadow) */}
      {hasFloorShadow && (
        <div
          className="nq-fairy-shadow absolute -bottom-1 left-1/2 pointer-events-none rounded-full"
          style={{
            width: `${size * 0.65}px`,
            height: `${Math.max(6, size * 0.12)}px`,
            background: `radial-gradient(ellipse at center, ${theme.shadowColor} 0%, rgba(0,0,0,0.6) 45%, transparent 75%)`,
          }}
        />
      )}

      {/* 2. Vòng hào quang năng lượng Hologram tỏa tròn phía sau */}
      <div
        className="nq-fairy-halo absolute inset-0 rounded-full blur-md pointer-events-none transition-all duration-500"
        style={{ background: theme.glowBg }}
      />

      {/* 3. Vòng ma pháp công nghệ đôi (Dual Holographic Tech Rings) */}
      {hasHoloRing && (
        <>
          {/* Vòng ngoài (Outer tech ring) - xoay theo chiều kim đồng hồ */}
          <div
            className="absolute -inset-1.5 rounded-full pointer-events-none transition-all duration-500"
            style={{
              border: `1px dashed ${theme.ringBorder}`,
              animation: `nq-fairy-spin-cw ${
                activeMood === "processing" ? "4s" : speaking || listening ? "8s" : "16s"
              } linear infinite`,
            }}
          >
            {/* 4 Cardinal Nodes / Tech Pips */}
            <div
              className="absolute -top-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full"
              style={{ backgroundColor: theme.dotColor, boxShadow: `0 0 4px ${theme.dotColor}` }}
            />
            <div
              className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full"
              style={{ backgroundColor: theme.dotColor, boxShadow: `0 0 4px ${theme.dotColor}` }}
            />
            <div
              className="absolute top-1/2 -left-0.5 -translate-y-1/2 w-1 h-1 rounded-full"
              style={{ backgroundColor: theme.dotColor, boxShadow: `0 0 4px ${theme.dotColor}` }}
            />
            <div
              className="absolute top-1/2 -right-0.5 -translate-y-1/2 w-1 h-1 rounded-full"
              style={{ backgroundColor: theme.dotColor, boxShadow: `0 0 4px ${theme.dotColor}` }}
            />
          </div>

          {/* Vòng trong (Inner tech ring) - xoay ngược chiều kim đồng hồ */}
          <div
            className="absolute inset-0.5 rounded-full pointer-events-none transition-all duration-500"
            style={{
              border: `0.75px dotted ${theme.ringBorder}`,
              opacity: 0.65,
              animation: `nq-fairy-spin-ccw ${
                activeMood === "processing" ? "3s" : speaking || listening ? "6s" : "12s"
              } linear infinite`,
            }}
          />
        </>
      )}

      {/* 4. Sóng âm thanh cộng hưởng (Acoustic Resonance Ripples) khi nói hoặc lắng nghe */}
      {(speaking || listening) && (
        <>
          <div
            className="nq-fairy-ripple absolute -inset-2 rounded-full pointer-events-none"
            style={{ border: `1.5px solid ${theme.dotColor}` }}
          />
          <div
            className="nq-fairy-ripple absolute -inset-2 rounded-full pointer-events-none"
            style={{ border: `1px solid ${theme.dotColor}`, animationDelay: "0.9s" }}
          />
        </>
      )}

      {/* 5. Tinh thể ma pháp bay bổng (Mana Sparkles) */}
      {hasSparkles && (
        <div className="absolute inset-0 pointer-events-none overflow-visible">
          <span
            className="nq-fairy-mana-1 absolute select-none text-[8px] font-black"
            style={{
              top: "8%",
              right: "12%",
              color: theme.dotColor,
              filter: `drop-shadow(0 0 3px ${theme.dotColor})`,
            }}
          >
            ✦
          </span>
          <span
            className="nq-fairy-mana-2 absolute select-none text-[6px] font-black"
            style={{
              bottom: "22%",
              left: "10%",
              color: theme.dotColor,
              filter: `drop-shadow(0 0 3px ${theme.dotColor})`,
            }}
          >
            ✦
          </span>
          <span
            className="nq-fairy-mana-3 absolute select-none text-[7px] font-black"
            style={{
              top: "30%",
              left: "8%",
              color: theme.dotColor,
              filter: `drop-shadow(0 0 3px ${theme.dotColor})`,
            }}
          >
            ✦
          </span>
        </div>
      )}

      {/* 6. Khung bay lơ lửng thuần CSS (Không bị React state can thiệp) */}
      <div className="nq-fairy-container relative w-full h-full flex items-center justify-center pointer-events-none">
        {/* Lớp biến đổi kích thước theo âm thanh riêng biệt với chuyển động êm dịu */}
        <div
          className="w-full h-full flex items-center justify-center transition-transform duration-100 ease-out"
          style={{ transform: speaking && audioScale > 1 ? `scale(${audioScale})` : "scale(1)" }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageSrc}
            alt={`Tinh linh Hệ Thống - ${label}`}
            width={size}
            height={size}
            decoding="async"
            loading={priority ? "eager" : "lazy"}
            fetchPriority={priority ? "high" : "low"}
            className="w-full h-full object-contain pointer-events-none"
            style={{
              transition: "none",
              filter: `drop-shadow(0 4px 14px ${theme.shadowColor})`,
            }}
            draggable={false}
            data-fbk="0"
            data-frame={currentFrameName}
            onError={(e) => {
              const target = e.currentTarget;
              // Guard chống loop vô hạn khi cả webp/png đều 404.
              if (target.dataset.fbk === "2") return;
              const step = Number(target.dataset.fbk || "0");
              if (step === 0 && candidates[1]) {
                target.dataset.fbk = "1";
                target.src = candidates[1];
              } else {
                target.dataset.fbk = "2";
                target.src = MOOD_IMAGES[activeMood] || MOOD_IMAGES.idle;
              }
            }}
          />
        </div>
      </div>

      {/* 7. Huy hiệu trạng thái phong cách Hệ Thống - Ký Chủ */}
      {hasBadge && (
        <div
          className={`absolute -bottom-2.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full border px-2 py-0.5 text-[8.5px] font-bold tracking-wider uppercase transition-all duration-300 shadow-sm flex items-center gap-1 ${theme.badgeBorder} ${theme.badgeBg} ${theme.badgeText}`}
        >
          <span
            className="inline-block w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
            style={{ backgroundColor: theme.dotColor, boxShadow: `0 0 4px ${theme.dotColor}` }}
          />
          <span>{label}</span>
        </div>
      )}

      {/* 8. Popup tooltip lời thoại khi hover với glassmorphism và mũi tên chỉ báo */}
      {showTooltip && isHovered && (
        <div className="absolute -top-11 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg backdrop-blur-md bg-slate-900/95 border border-sky-400/50 px-3 py-1.5 text-[10px] text-sky-200 shadow-xl z-50 pointer-events-none animate-in fade-in zoom-in-95 duration-150 flex items-center gap-1.5">
          <span className="text-xs">💬</span>
          <span>{SYSTEM_TIPS[tipIndex]}</span>
          <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-900/95 border-r border-b border-sky-400/50 rotate-45" />
        </div>
      )}
    </div>
  );
}
