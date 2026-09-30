"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";

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
    frames: ["processing_01", "processing_02", "processing_03", "processing_04", "processing_05", "processing_06", "processing_07", "processing_08"],
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
    frames: ["alert_01", "alert_02", "alert_03", "alert_04", "alert_05", "alert_06", "alert_07", "alert_08"],
    frameInterval: 130,
    loop: true,
  },
  alert: {
    frames: ["alert_01", "alert_02", "alert_03", "alert_04", "alert_05", "alert_06", "alert_07", "alert_08"],
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

function getSpritePath(frameName: string): string {
  return `/copilot/sprites/${frameName}.png`;
}

/**
 * Avatar Tinh Linh Hệ Thống (Fairy System AI) cho AG-COPILOT.
 *
 * Chuyển động lơ lửng (Anti-gravity floating), thở nhịp nhàng,
 * 86 sprite (83 frame gốc + 3 in-between nâng/hạ tay liền mạch),
 * chuyển đổi mượt mà giữa các trạng thái và tự động chớp mắt tự nhiên.
 */
export function Avatar2D({
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
}: AvatarProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [tipIndex, setTipIndex] = useState(0);
  const [isPoked, setIsPoked] = useState(false);
  const [isBlinking, setIsBlinking] = useState(false);
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);

  // Cấu hình linh hoạt hiển thị hiệu ứng theo kích cỡ nếu không truyền prop cụ thể
  const hasBadge = showBadge !== undefined ? showBadge : size >= 60;
  const hasFloorShadow = showFloorShadow !== undefined ? showFloorShadow : size >= 56;
  const hasHoloRing = showHoloRing !== undefined ? showHoloRing : true;
  const hasSparkles = showSparkles !== undefined ? showSparkles : size >= 68;

  // Suy luận mood tự động nếu không truyền explicitMood
  const activeMood: AvatarMood = isPoked
    ? "poke"
    : explicitMood ||
      (speaking
        ? "speaking"
        : listening
        ? "listening"
        : "idle");

  const label = MOOD_LABELS[activeMood] || "Hệ thống AG";
  const theme = MOOD_THEMES[activeMood] || MOOD_THEMES.idle;

  // Clamp mouthOpen 0-1 để rung nhẹ theo biên độ giọng nói
  const open = Math.max(0, Math.min(1, mouthOpen));
  const audioScale = speaking ? 1 + open * 0.08 : 1;

  // Quyết định sequence dựa trên mood và blink
  const currentAction = isBlinking && activeMood === "idle" ? "blink" : activeMood;
  const sequence = ACTION_SEQUENCES[currentAction] || ACTION_SEQUENCES.idle;

  // Tự động chớp mắt ngẫu nhiên sau mỗi 3.5 - 6 giây khi ở Idle
  useEffect(() => {
    if (activeMood !== "idle" || isPoked || isBlinking) return;

    const delay = 3500 + Math.random() * 2500;
    const timer = setTimeout(() => {
      setIsBlinking(true);
      setCurrentFrameIndex(0);
    }, delay);

    return () => clearTimeout(timer);
  }, [activeMood, isPoked, isBlinking]);

  // Vòng lặp khung hình (Frame stepping)
  useEffect(() => {
    if (!useSprites) return;

    // Riêng speaking: nếu có mouthOpen thì ánh xạ trực tiếp vào frame miệng
    if (activeMood === "speaking" && mouthOpen > 0) {
      const frameIdx = Math.min(5, Math.floor(open * 6));
      setCurrentFrameIndex(frameIdx);
      return;
    }

    const interval = setInterval(() => {
      setCurrentFrameIndex((prev) => {
        const next = prev + 1;
        if (next >= sequence.frames.length) {
          if (isBlinking) {
            setIsBlinking(false);
            return 0;
          }
          if (isPoked) {
            setIsPoked(false);
            return 0;
          }
          // Khi ngủ say: sau khi ngáp và ôm gối (frame 0-3), lặp êm dịu chu kỳ thở với gối mây (frame 3-7)
          if (activeMood === "sleepy" && sequence.frames.length >= 8) {
            return 3; // lặp lại từ sleepy_04 đến sleepy_08 với gối mây
          }
          return sequence.loop ? 0 : sequence.frames.length - 1;
        }
        return next;
      });
    }, sequence.frameInterval);

    return () => clearInterval(interval);
  }, [sequence, isBlinking, isPoked, activeMood, mouthOpen, open, useSprites]);

  // Reset frame khi đổi mood
  useEffect(() => {
    setCurrentFrameIndex(0);
  }, [activeMood]);

  // Lời thoại tip ngẫu nhiên khi Ký chủ bấm vào Tinh Linh
  const SYSTEM_TIPS = [
    "Đinh! Ký chủ cần hỗ trợ kiểm tra ca làm việc không?",
    "Hệ thống luôn sẵn sàng nhận lệnh từ Ký chủ!",
    "Hôm nay các bạn Barista đang hoạt động rất tốt!",
    "Ký chủ nhớ duyệt bảng lương và chốt ca đúng giờ nhé!",
  ];

  const handleClick = () => {
    setTipIndex((prev) => (prev + 1) % SYSTEM_TIPS.length);
    setIsPoked(true);
    setCurrentFrameIndex(0);
  };

  const currentFrameName = sequence.frames[currentFrameIndex] || sequence.frames[0] || "idle_01";
  const imageSrc = useSprites
    ? getSpritePath(currentFrameName)
    : MOOD_IMAGES[activeMood] || MOOD_IMAGES.idle;

  return (
    <div
      className="relative shrink-0 select-none group cursor-pointer"
      style={{ width: size, height: size }}
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title="Bấm để tương tác với Tinh Linh Hệ Thống"
      aria-label={label}
      role="img"
    >
      <style jsx>{`
        @keyframes fairyFloatOrganic {
          0%, 100% {
            transform: translate3d(0, 0, 0) rotate(0deg);
          }
          25% {
            transform: translate3d(1px, -3.5px, 0) rotate(0.4deg);
          }
          50% {
            transform: translate3d(0, -6px, 0) rotate(-0.3deg);
          }
          75% {
            transform: translate3d(-1px, -2.5px, 0) rotate(0.2deg);
          }
        }
        @keyframes floorShadowBreathe {
          0%, 100% {
            transform: translateX(-50%) scale(1);
            opacity: 0.45;
          }
          50% {
            transform: translateX(-50%) scale(0.72);
            opacity: 0.18;
            filter: blur(4px);
          }
        }
        @keyframes holoSpinCW {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }
        @keyframes holoSpinCCW {
          from {
            transform: rotate(360deg);
          }
          to {
            transform: rotate(0deg);
          }
        }
        @keyframes pulseGlowSoft {
          0%, 100% {
            opacity: 0.45;
            transform: scale(0.96);
          }
          50% {
            opacity: 0.85;
            transform: scale(1.06);
          }
        }
        @keyframes acousticRippleWave {
          0% {
            transform: scale(0.88);
            opacity: 0.8;
          }
          100% {
            transform: scale(1.45);
            opacity: 0;
          }
        }
        @keyframes manaDrift1 {
          0%, 100% {
            transform: translate3d(0, 0, 0) scale(0.85);
            opacity: 0.35;
          }
          50% {
            transform: translate3d(3px, -5px, 0) scale(1.2);
            opacity: 0.95;
          }
        }
        @keyframes manaDrift2 {
          0%, 100% {
            transform: translate3d(0, 0, 0) scale(1.1);
            opacity: 0.9;
          }
          50% {
            transform: translate3d(-3px, -4px, 0) scale(0.65);
            opacity: 0.25;
          }
        }
        @keyframes manaDrift3 {
          0%, 100% {
            transform: translate3d(0, 0, 0) scale(0.9);
            opacity: 0.4;
          }
          50% {
            transform: translate3d(2px, -6px, 0) scale(1.25);
            opacity: 1;
          }
        }
        .fairy-container {
          animation: fairyFloatOrganic 3.4s ease-in-out infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .fairy-container,
          .floor-shadow,
          .holo-outer,
          .holo-inner,
          .glow-halo,
          .acoustic-ripple,
          .mana-sparkle {
            animation: none !important;
          }
        }
      `}</style>

      {/* 1. Bóng năng lượng tiếp đất phản xạ (Floor energy reflection shadow) */}
      {hasFloorShadow && (
        <div
          className="floor-shadow absolute -bottom-1 left-1/2 pointer-events-none rounded-full"
          style={{
            width: `${size * 0.65}px`,
            height: `${Math.max(6, size * 0.12)}px`,
            background: `radial-gradient(ellipse at center, ${theme.shadowColor} 0%, rgba(0,0,0,0.6) 45%, transparent 75%)`,
            animation: "floorShadowBreathe 3.4s ease-in-out infinite",
          }}
        />
      )}

      {/* 2. Vòng hào quang năng lượng Hologram tỏa tròn phía sau */}
      <div
        className="glow-halo absolute inset-0 rounded-full blur-md pointer-events-none transition-all duration-500"
        style={{
          background: theme.glowBg,
          animation: "pulseGlowSoft 2.8s ease-in-out infinite",
        }}
      />

      {/* 3. Vòng ma pháp công nghệ đôi (Dual Holographic Tech Rings) */}
      {hasHoloRing && (
        <>
          {/* Vòng ngoài (Outer tech ring) - xoay theo chiều kim đồng hồ */}
          <div
            className="holo-outer absolute -inset-1.5 rounded-full pointer-events-none transition-all duration-500"
            style={{
              border: `1px dashed ${theme.ringBorder}`,
              animation: `holoSpinCW ${
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
            className="holo-inner absolute inset-0.5 rounded-full pointer-events-none transition-all duration-500"
            style={{
              border: `0.75px dotted ${theme.ringBorder}`,
              opacity: 0.65,
              animation: `holoSpinCCW ${
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
            className="acoustic-ripple absolute -inset-2 rounded-full pointer-events-none"
            style={{
              border: `1.5px solid ${theme.dotColor}`,
              animation: "acousticRippleWave 1.8s cubic-bezier(0, 0.2, 0.8, 1) infinite",
            }}
          />
          <div
            className="acoustic-ripple absolute -inset-2 rounded-full pointer-events-none"
            style={{
              border: `1px solid ${theme.dotColor}`,
              animation: "acousticRippleWave 1.8s cubic-bezier(0, 0.2, 0.8, 1) infinite 0.9s",
            }}
          />
        </>
      )}

      {/* 5. Tinh thể ma pháp bay bổng (Mana Sparkles) */}
      {hasSparkles && (
        <div className="absolute inset-0 pointer-events-none overflow-visible">
          <span
            className="mana-sparkle absolute select-none text-[8px] font-black"
            style={{
              top: "8%",
              right: "12%",
              color: theme.dotColor,
              filter: `drop-shadow(0 0 3px ${theme.dotColor})`,
              animation: "manaDrift1 3.2s ease-in-out infinite",
            }}
          >
            ✦
          </span>
          <span
            className="mana-sparkle absolute select-none text-[6px] font-black"
            style={{
              bottom: "22%",
              left: "10%",
              color: theme.dotColor,
              filter: `drop-shadow(0 0 3px ${theme.dotColor})`,
              animation: "manaDrift2 2.7s ease-in-out infinite 0.4s",
            }}
          >
            ✦
          </span>
          <span
            className="mana-sparkle absolute select-none text-[7px] font-black"
            style={{
              top: "30%",
              left: "8%",
              color: theme.dotColor,
              filter: `drop-shadow(0 0 3px ${theme.dotColor})`,
              animation: "manaDrift3 3.6s ease-in-out infinite 0.8s",
            }}
          >
            ✦
          </span>
        </div>
      )}

      {/* 6. Khung bay lơ lửng thuần CSS (Không bị React state can thiệp) */}
      <div className="fairy-container relative w-full h-full flex items-center justify-center pointer-events-none">
        {/* Lớp biến đổi kích thước theo âm thanh riêng biệt với chuyển động êm dịu */}
        <div
          className="w-full h-full flex items-center justify-center transition-transform duration-100 ease-out"
          style={{ transform: speaking && audioScale > 1 ? `scale(${audioScale})` : "scale(1)" }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageSrc}
            alt={`Tinh linh Hệ Thống - ${label}`}
            className="w-full h-full object-contain pointer-events-none"
            style={{
              transition: "none",
              filter: `drop-shadow(0 4px 14px ${theme.shadowColor})`,
            }}
            draggable={false}
            onError={(e) => {
              // Fallback nếu sprite chưa tải xong
              const target = e.currentTarget;
              if (target.src !== MOOD_IMAGES.idle) {
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