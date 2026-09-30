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

interface PaneState {
  /** 0 = collapsed (chỉ chip), 1 = small, 2 = large */
  size: 0 | 1 | 2;
  /** Size của pane khi size>0. */
  w: number;
  h: number;
}

const DEFAULT_STATE: PaneState = {
  size: 1,
  w: 380,
  h: 540,
};

function loadState(): PaneState {
  if (typeof window === "undefined") return DEFAULT_STATE;
  try {
    const raw = window.localStorage.getItem(POS_KEY);
    if (!raw) return DEFAULT_STATE;
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

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
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

  const [state, setState] = useState<PaneState>({ size: 0, w: 400, h: 580 });
  const [hydrated, setHydrated] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(typeof window !== "undefined" && window.innerWidth < 640);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  useEffect(() => {
    setState(loadState());
    setHydrated(true);
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
      // Khi bấm đóng ở chế độ thông thường, thu nhỏ về chip Tinh Linh lơ lửng để luôn sẵn sàng
      setState((s) => ({ ...s, size: 0 }));
    }
  }, [isControlled, onClose]);

  // Phím tắt Ctrl/Cmd+K mở nhanh pane hoặc chuyển đổi giữa chip và cửa sổ
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
        // Thu nhỏ về chip thay vì đóng hẳn
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
        borderTopLeftRadius: "20px",
        borderTopRightRadius: "20px",
      };
    }
    const viewportWidth = typeof window === "undefined" ? 400 + 32 : window.innerWidth;
    const viewportHeight = typeof window === "undefined" ? 580 + 32 : window.innerHeight;
    const maxWidth = Math.max(280, viewportWidth - 32);
    const maxHeight = Math.max(360, viewportHeight - 32);
    const w = state.size === 0 ? 68 : Math.min(state.size === 2 ? 680 : state.w, maxWidth);
    const h = state.size === 0 ? 68 : Math.min(state.size === 2 ? Math.min(820, viewportHeight - 40) : state.h, maxHeight);
    const margin = 20;
    return {
      right: margin,
      bottom: margin,
      width: w,
      height: h,
      position: "fixed",
      zIndex: 50,
      borderRadius: "16px",
    };
  })();

  const chat = useCopilotChat("pane");

  if (!isOpen) return null;

  // Chế độ thu nhỏ (chip): Tinh Linh Hệ Thống bay lơ lửng ở góc màn hình
  if (state.size === 0) {
    return (
      <div
        style={{
          right: 20,
          bottom: 20,
          position: "fixed",
          zIndex: 50,
        }}
        className="relative group select-none"
      >
        {/* Bong bóng gợi ý mở trợ lý với phím tắt Ctrl+K */}
        <div className="absolute right-0 bottom-full mb-3 hidden group-hover:flex items-center gap-2 whitespace-nowrap rounded-xl border border-sky-400/40 bg-slate-950/95 px-3.5 py-2 text-xs text-sky-200 shadow-2xl backdrop-blur-md pointer-events-none transition-all duration-300 group-hover:scale-105 animate-in fade-in slide-in-from-bottom-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-sky-500" />
          </span>
          <span className="font-semibold text-sky-100">AG-Copilot</span>
          <span className="text-sky-300/80">· Bấm để mở trợ lý</span>
          <kbd className="hidden sm:inline-block rounded bg-sky-950/80 border border-sky-500/30 px-1.5 py-0.5 text-[10px] font-mono text-sky-300">
            Ctrl+K
          </kbd>
        </div>

        {/* Nút bấm hình Tinh Linh 2D lơ lửng */}
        <button
          type="button"
          onClick={() => setState((s) => ({ ...s, size: 1 }))}
          className="relative flex items-center justify-center transition-all duration-300 hover:scale-110 active:scale-95 focus:outline-none rounded-full"
          title="Mở Trợ lý Tinh Linh Hệ Thống (Ctrl+K)"
          aria-label="Mở Trợ lý Tinh Linh Hệ Thống"
        >
          {/* Hào quang phát sáng mềm mại */}
          <div className="absolute -inset-1.5 rounded-full bg-gradient-to-r from-sky-500/20 via-cyan-400/20 to-indigo-500/20 blur-md pointer-events-none group-hover:opacity-100 opacity-60 transition duration-500" />
          <Avatar2D
            size={76}
            speaking={false}
            listening={false}
            mood="idle"
            showBadge={false}
            showSparkles={true}
          />
        </button>
      </div>
    );
  }

  return (
    <div
      style={style}
      className={`nq-surface-block flex flex-col overflow-hidden bg-[var(--nq-bg-elevated)] border border-[var(--nq-accent)]/60 shadow-[0_20px_50px_rgba(0,0,0,0.5)] transition-all duration-300 ease-out backdrop-blur-md ${
        isMobile ? "rounded-t-2xl border-b-0" : "rounded-2xl"
      }`}
    >
      {/* Header bar điều khiển cửa sổ */}
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-[var(--nq-line)] bg-[var(--nq-surface-hi)] px-3 select-none">
        <div className="flex items-center gap-2">
          {isMobile ? (
            <div className="mx-auto h-1 w-10 rounded-full bg-[var(--nq-dim)]/50 -mt-1 mb-1" />
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-2xs font-bold uppercase tracking-wider text-[var(--nq-fg)]">
                AG-Copilot
              </span>
              <span className="text-[10px] text-[var(--nq-dim)] hidden sm:inline">· Trợ lý AI</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1" onMouseDown={(e) => e.stopPropagation()}>
          <button
            onClick={() => setState((s) => ({ ...s, size: 0 }))}
            title="Thu nhỏ về Tinh Linh lơ lửng (Ctrl+K hoặc Esc)"
            aria-label="Thu nhỏ về Tinh Linh"
            className="flex h-6 w-6 items-center justify-center rounded border border-[var(--nq-dim)]/30 bg-[var(--nq-surface)] text-xs text-[var(--nq-dim)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-fg)] transition active:scale-95"
          >
            –
          </button>
          {!isMobile && (
            <button
              onClick={() =>
                setState((s) => ({
                  ...s,
                  size: s.size === 2 ? 1 : 2,
                  w: s.size === 2 ? 400 : Math.min(680, window.innerWidth - 40),
                  h: s.size === 2 ? 580 : Math.min(820, window.innerHeight - 40),
                }))
              }
              title={state.size === 2 ? "Kích thước vừa" : "Mở rộng không gian làm việc"}
              aria-label={state.size === 2 ? "Kích thước vừa" : "Mở rộng"}
              className="flex h-6 w-6 items-center justify-center rounded border border-[var(--nq-dim)]/30 bg-[var(--nq-surface)] text-xs text-[var(--nq-dim)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-fg)] transition active:scale-95"
            >
              {state.size === 2 ? "▢" : "▣"}
            </button>
          )}
          <button
            onClick={closePane}
            title="Đóng về Tinh Linh"
            aria-label="Đóng"
            className="flex h-6 w-6 items-center justify-center rounded border border-[var(--nq-dim)]/30 bg-[var(--nq-surface)] text-xs text-[var(--nq-dim)] hover:border-rose-400 hover:text-rose-400 transition active:scale-95"
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