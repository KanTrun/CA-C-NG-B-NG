// CopilotPane: pane nổi, neo ổn định ở góc phải dưới và có thể thu nhỏ.
//
// Dùng được ở AppShell và các page riêng (controlled mode như trước).

"use client";

import React, {
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
} from "react";
import { CopilotBody } from "./CopilotBody";
import { useCopilotChat } from "./useCopilotChat";
import { Avatar2D } from "./Avatar2D";
import type { Role } from "../../lib/session";

const POS_KEY = "ag_copilot_pane_pos_v2";
const BUBBLE_KEY = "ag_copilot_bubble_dismissed_v1";
const ROOT_REF = "nq-copilot-root";

interface PaneState {
  /** 0 = collapsed (chỉ chip), 1 = small, 2 = large */
  size: 0 | 1 | 2;
  /** Size của pane khi size>0. */
  w: number;
  h: number;
}

const DEFAULT_STATE: PaneState = {
  size: 1,
  w: 430,
  h: 640,
};

function loadState(): PaneState {
  if (typeof window === "undefined") return DEFAULT_STATE;
  try {
    const raw = window.localStorage.getItem(POS_KEY);
    if (!raw) {
      if (window.innerWidth < 640) {
        return { ...DEFAULT_STATE, size: 0 };
      }
      return DEFAULT_STATE;
    }
    const s = JSON.parse(raw) as Partial<PaneState>;
    return { ...DEFAULT_STATE, ...s };
  } catch {
    return DEFAULT_STATE;
  }
}

function saveState(s: PaneState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(POS_KEY, JSON.stringify(s));
  } catch {/* ignore */}
}

interface Props {
  /** Controlled mode: nếu truyền `open` thì pane dùng giá trị này. */
  open?: boolean;
  /** Controlled mode: callback đóng. */
  onClose?: () => void;
}

export function CopilotPane({ open, onClose }: Props = {}) {
  const isControlled = open !== undefined;
  const [internalOpen, setInternalOpen] = useState(true);
  const isOpen = isControlled ? Boolean(open) : internalOpen;

  const [state, setState] = useState<PaneState>({ size: 0, w: 430, h: 640 });
  const [hydrated, setHydrated] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [bubbleDismissed, setBubbleDismissed] = useState(true);

  useEffect(() => {
    const checkMobile = () => setIsMobile(typeof window !== "undefined" && window.innerWidth < 640);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  useEffect(() => {
    setState(loadState());
    try {
      const dismissed = typeof window !== "undefined" && window.localStorage.getItem(BUBBLE_KEY) === "1";
      setBubbleDismissed(dismissed);
    } catch {
      setBubbleDismissed(false);
    }
    setHydrated(true);
  }, []);

  const dismissBubble = useCallback((e?: React.MouseEvent) => {
    e?.stopPropagation();
    setBubbleDismissed(true);
    try {
      window.localStorage.setItem(BUBBLE_KEY, "1");
    } catch {/* ignore */}
  }, []);

  useEffect(() => {
    if (hydrated) saveState(state);
  }, [state, hydrated]);

  useEffect(() => {
    if (isControlled && open) {
      setState((current) => current.size === 0 ? { ...current, size: 1 } : current);
    }
  }, [isControlled, open]);

  const closePane = useCallback(() => {
    if (isControlled) {
      onClose?.();
    } else {
      // Khi bấm đóng ở chế độ thông thường, thu nhỏ về Tinh Linh lơ lửng để luôn đồng hành
      setState((s) => ({ ...s, size: 0 }));
      // Đã mở pane tương tác thì không hiển thị lại bong bóng chào mời gây phiền
      dismissBubble();
    }
  }, [isControlled, onClose, dismissBubble]);

  /**
   * QA 2026-10-01 LỖI 11: pane nổi là `position: fixed` 430×640 ở góc phải dưới
   * và MỞ SẴN trên mọi trang desktop (`DEFAULT_STATE.size = 1`). Nó đè lên nội
   * dung trang, nên 20 control trên 14 trang không bấm được — kể cả nút lưu cấu
   * hình quán và nút thêm món. Người dùng bấm mãi không có phản hồi, không hề
   * biết vì sao.
   *
   * Cách sửa: người dùng chạm vào PHẦN TRANG (ngoài pane) là tín hiệu rõ ràng
   * "tôi muốn làm việc với trang" ⇒ tự thu nhỏ về Tinh Linh để không chắn tay.
   * Bấm vào avatar là mở lại. Không cần dành chỗ trống cố định trong layout vì
   * pane vốn đã ở vị trí phủ và có thể kéo.
   */
  useEffect(() => {
    if (state.size === 0) return;
    function onPointerDown(e: PointerEvent) {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      // Bấm trong pane thì không đụng tới.
      if (target.closest(`#${ROOT_REF}`)) return;
      // Lớp phủ toàn màn hình của hộp thoại/lệnh (CommandPalette, Tour, modal):
      // để các lớp đó quyết định, không tự thu nhỏ theo.
      if (target.closest("[role='dialog'][aria-modal='true']")) return;
      setState((s) => (s.size === 0 ? s : { ...s, size: 0 }));
    }
    // `true` để bắt cả pointerdown ngoài pane mà không chặn propagation.
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => window.removeEventListener("pointerdown", onPointerDown, true);
  }, [state.size]);

  // Phím tắt Ctrl/Cmd+K mở nhanh pane hoặc chuyển đổi giữa Tinh Linh và cửa sổ
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isToggle = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k";
      if (isToggle) {
        e.preventDefault();
        if (isControlled) {
          if (isOpen) onClose?.();
        } else {
          setState((s) => ({ ...s, size: s.size === 0 ? 1 : 0 }));
        }
        return;
      }
      if (e.key === "Escape" && isOpen && state.size > 0) {
        // Thu nhỏ về Tinh Linh thay vì đóng hẳn
        setState((s) => ({ ...s, size: 0 }));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isControlled, isOpen, onClose, state.size]);

  // Neo pane ở vị trí tối ưu; hỗ trợ Full Drawer / Bottom Sheet trên Mobile
  const style: CSSProperties = (() => {
    if (isMobile && state.size > 0) {
      return {
        left: 0,
        right: 0,
        bottom: 0,
        width: "100%",
        height: "92vh",
        maxHeight: "92vh",
        position: "fixed",
        zIndex: 60,
        borderTopLeftRadius: "24px",
        borderTopRightRadius: "24px",
      };
    }
    const viewportWidth = typeof window === "undefined" ? 440 + 32 : window.innerWidth;
    const viewportHeight = typeof window === "undefined" ? 640 + 32 : window.innerHeight;
    const maxWidth = Math.max(320, viewportWidth - 32);
    const maxHeight = Math.max(400, viewportHeight - 32);
    const w = state.size === 0 ? 84 : Math.min(state.size === 2 ? 720 : state.w, maxWidth);
    const h = state.size === 0 ? 84 : Math.min(state.size === 2 ? Math.min(860, viewportHeight - 40) : state.h, maxHeight);
    const margin = 20;
    return {
      right: margin,
      bottom: margin,
      width: w,
      height: h,
      position: "fixed",
      zIndex: 50,
      borderRadius: "20px",
    };
  })();

  const chat = useCopilotChat("pane");

  if (!isOpen) return null;

  // Chế độ thu nhỏ (Tinh Linh đồng hành): Tinh Linh 2D bay lơ lửng luôn đi theo người dùng
  if (state.size === 0) {
    return (
      <div
        id={ROOT_REF}
        style={{
          right: isMobile ? 16 : 24,
          bottom: isMobile ? 16 : 24,
          position: "fixed",
          zIndex: 50,
        }}
        className="relative group select-none"
      >
        {/* Bong bóng chào mời tương tác phong cách nhân vật ảo */}
        {!bubbleDismissed && (
          <div className="absolute right-0 bottom-full mb-3 flex flex-col items-end pointer-events-none transition-all duration-300 group-hover:scale-105 animate-in fade-in slide-in-from-bottom-2">
            <div className="relative w-64 max-w-[calc(100vw-2.5rem)] rounded-2xl border border-amber-400/40 bg-slate-950/95 px-4 py-2.5 text-xs text-amber-200 shadow-2xl backdrop-blur-md pointer-events-auto">
              <div className="flex items-center justify-between gap-1.5 font-bold text-amber-300 mb-1">
                <div className="flex items-center gap-1.5 whitespace-nowrap">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                  </span>
                  <span className="whitespace-nowrap">Tinh Linh Trợ Lý</span>
                </div>
                <div className="flex items-center gap-1">
                  <kbd className="hidden sm:inline-block rounded bg-amber-950/80 border border-amber-500/30 px-1.5 py-0.5 text-[9px] font-mono text-amber-300 whitespace-nowrap">
                    Ctrl+K
                  </kbd>
                  <button
                    type="button"
                    onClick={dismissBubble}
                    className="flex h-5 w-5 items-center justify-center rounded-md text-slate-400 hover:text-amber-200 hover:bg-white/10 active:scale-95 transition cursor-pointer"
                    title="Tắt bảng tinh linh trợ lý"
                    aria-label="Tắt bảng tinh linh trợ lý"
                  >
                    <span className="text-xs leading-none">✕</span>
                  </button>
                </div>
              </div>
              <p
                onClick={() => setState((s) => ({ ...s, size: 1 }))}
                className="text-[11px] text-slate-300 leading-snug cursor-pointer hover:text-white transition-colors"
              >
                Chào Ký chủ! Bấm vào em để nhắn tin hoặc <strong className="text-emerald-400 font-semibold">Gọi Live</strong> trực tiếp nhé ✨
              </p>
              {/* Đuôi bong bóng thoại chĩa xuống Tinh Linh */}
              <div className="absolute -bottom-1.5 right-8 h-3 w-3 rotate-45 border-r border-b border-amber-400/40 bg-slate-950 pointer-events-none" />
            </div>
          </div>
        )}

        {/* Nút bấm hình Tinh Linh 2D lơ lửng */}
        <button
          type="button"
          onClick={() => setState((s) => ({ ...s, size: 1 }))}
          className="relative flex items-center justify-center transition-all duration-300 hover:scale-110 active:scale-95 focus:outline-none rounded-full"
          title="Trò chuyện với Tinh Linh Trợ Lý (Ctrl+K)"
          aria-label="Mở Trợ lý Tinh Linh Hệ Thống"
        >
          {/* Hào quang phát sáng mềm mại xung quanh Tinh Linh */}
          <div className="absolute -inset-2 rounded-full bg-gradient-to-r from-amber-500/30 via-sky-400/30 to-emerald-400/30 blur-lg pointer-events-none group-hover:opacity-100 opacity-70 transition duration-500 animate-pulse" />
          <Avatar2D
            size={isMobile ? 74 : 84}
            speaking={false}
            listening={false}
            mood="idle"
            showBadge={false}
            showSparkles={true}
            showTooltip={false}
          />
        </button>
      </div>
    );
  }

  return (
    <div
      id={ROOT_REF}
      style={style}
      role="complementary"
      aria-label="Trợ lý Tinh Linh"
      className={`flex flex-col overflow-hidden bg-slate-950/95 border border-amber-500/40 shadow-[0_25px_60px_rgba(0,0,0,0.7)] transition-all duration-300 ease-out backdrop-blur-xl ${
        isMobile ? "rounded-t-3xl border-b-0" : "rounded-3xl"
      }`}
    >
      {/* Header bar điều khiển cửa sổ nhỏ gọn, tinh tế */}
      <div className="flex h-8 shrink-0 items-center justify-between border-b border-slate-800/80 bg-slate-900/60 px-3 select-none">
        <div className="flex items-center gap-2">
          {isMobile ? (
            <div className="mx-auto h-1 w-12 rounded-full bg-slate-600/70 -mt-0.5 mb-1" />
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                AG-Copilot · Companion
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1" onMouseDown={(e) => e.stopPropagation()}>
          <button
            onClick={() => setState((s) => ({ ...s, size: 0 }))}
            title="Thu nhỏ về Tinh Linh lơ lửng (Ctrl+K hoặc Esc)"
            aria-label="Thu nhỏ về Tinh Linh"
            className="flex h-5 w-5 items-center justify-center rounded border border-slate-700/50 bg-slate-800/60 text-xs text-slate-400 hover:border-amber-400 hover:text-amber-300 transition active:scale-95"
          >
            –
          </button>
          {!isMobile && (
            <button
              onClick={() =>
                setState((s) => ({
                  ...s,
                  size: s.size === 2 ? 1 : 2,
                  w: s.size === 2 ? 430 : Math.min(720, window.innerWidth - 40),
                  h: s.size === 2 ? 640 : Math.min(860, window.innerHeight - 40),
                }))
              }
              title={state.size === 2 ? "Kích thước vừa" : "Mở rộng không gian làm việc"}
              aria-label={state.size === 2 ? "Kích thước vừa" : "Mở rộng"}
              className="flex h-5 w-5 items-center justify-center rounded border border-slate-700/50 bg-slate-800/60 text-xs text-slate-400 hover:border-amber-400 hover:text-amber-300 transition active:scale-95"
            >
              {state.size === 2 ? "▢" : "▣"}
            </button>
          )}
          <button
            onClick={closePane}
            title="Đóng về Tinh Linh"
            aria-label="Đóng"
            className="flex h-5 w-5 items-center justify-center rounded border border-slate-700/50 bg-slate-800/60 text-xs text-slate-400 hover:border-rose-400 hover:text-rose-400 transition active:scale-95"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="relative h-full min-h-0 flex-1">
        <CopilotBody
          chat={chat}
          mode="pane"
          onClose={closePane}
          onOpenFullPage={() => window.open("/copilot", "_blank", "noopener")}
          onClearHistory={() => chat.clearHistory()}
        />
      </div>
    </div>
  );
}