"use client";

import Link from "next/link";
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";
import type { MouseEvent, ReactNode } from "react";
import { beat, springFor } from "../../lib/motion";

/**
 * Nghiêng theo con trỏ — chỉ dành cho thẻ được AI chọn là việc gấp nhất.
 *
 * Vì sao không áp cho mọi thẻ: bản cũ nghiêng cả bốn thẻ KPI như nhau, nên "thẻ
 * nào quan trọng" không đọc ra được từ chuyển động — mọi thứ đều động thì không
 * gì nổi bật. Nay đúng một thẻ mỗi trang có khoảnh khắc này, và nó trùng với
 * thẻ mà `computeOpsPulse` đánh dấu `highlightKpi`. Chuyển động trở thành một
 * kênh thông tin (chỗ này quan trọng) thay vì trang trí.
 *
 * Biên độ 4° là biên độ đọc được: lớn hơn thì chữ trên thẻ biến dạng, nhỏ hơn
 * thì không ai nhận ra có chuyển động. Độ cứng và damping lấy từ
 * `springFor("settle")` — suy ra từ chính `--nq-beat-settle`, và là tắt dần tới
 * hạn nên không bao giờ vượt đích: bảng số liệu không được rung khi người dùng
 * chỉ đang rê chuột qua.
 */
const TILT_DEG = 4;
const TILT_SPRING = springFor("settle");

function useHighlightTilt(enabled: boolean) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotateX = useSpring(useTransform(y, [-0.5, 0.5], [TILT_DEG, -TILT_DEG]), TILT_SPRING);
  const rotateY = useSpring(useTransform(x, [-0.5, 0.5], [-TILT_DEG, TILT_DEG]), TILT_SPRING);

  const onMove = (e: MouseEvent<HTMLElement>) => {
    if (!enabled) return;
    const rect = e.currentTarget.getBoundingClientRect();
    x.set((e.clientX - rect.left) / rect.width - 0.5);
    y.set((e.clientY - rect.top) / rect.height - 0.5);
  };
  const onLeave = () => {
    x.set(0);
    y.set(0);
  };
  return { rotateX, rotateY, onMove, onLeave };
}

export function KpiCard({
  value,
  label,
  href,
  accent,
  delay = 0,
  "data-highlight": dataHighlight,
}: {
  value: ReactNode;
  label: string;
  href?: string;
  accent?: "warn" | "ok" | "default";
  delay?: number;
  "data-highlight"?: string;
}) {
  const reduced = useReducedMotion() ?? false;
  const isHighlight = dataHighlight === "on";
  const tilt = useHighlightTilt(isHighlight && !reduced);
  const tileCls =
    accent === "warn"
      ? "nq-bento-tile nq-dash-kpi nq-dash-kpi--warn nq-ink-on-solid"
      : accent === "ok"
        ? "nq-bento-tile nq-dash-kpi nq-dash-kpi--ok nq-ink-on-solid"
        : "nq-bento-tile nq-dash-kpi";
  const highlightCls = isHighlight ? " nq-dash-kpi--pulse-hi" : "";

  const inner = (
    <>
      <strong className="nq-bento-value nq-dash-kpi-value">{value}</strong>
      <span className="nq-bento-label nq-dash-kpi-label">{label}</span>
    </>
  );

  // Thẻ thường: chỉ vào nhẹ + phản hồi bấm. Thẻ được đánh dấu: thêm nghiêng.
  const motionProps = reduced
    ? {}
    : isHighlight
      ? {
          initial: { opacity: 0, y: 10 },
          animate: { opacity: 1, y: 0 },
          transition: beat("focus", delay),
          style: { rotateX: tilt.rotateX, rotateY: tilt.rotateY, transformPerspective: 900 },
          onMouseMove: tilt.onMove,
          onMouseLeave: tilt.onLeave,
          whileHover: { scale: 1.015, transition: beat("settle") },
          whileTap: { scale: 0.985 },
        }
      : {
          initial: { opacity: 0, y: 10 },
          animate: { opacity: 1, y: 0 },
          transition: beat("focus", delay),
          whileTap: { scale: 0.985 },
        };

  // `--hi` đổi KÍCH THƯỚC ô lưới, không chỉ hiệu ứng. Xem globals.css: khi một
  // thẻ được AI đánh dấu, nó chiếm nửa lưới (span 6) và ba thẻ còn lại chia nửa
  // kia (span 2) — phân cấp đọc ra được cả khi không rê chuột, và cả khi người
  // dùng đã tắt chuyển động (lúc đó `data-highlight` vẫn còn tác dụng).
  const cellCls = `nq-dash-kpi-cell${isHighlight ? " nq-dash-kpi-cell--hi" : ""}`;

  if (href) {
    return (
      <motion.div className={cellCls} {...motionProps}>
        <Link href={href} className={tileCls + highlightCls}>
          {inner}
        </Link>
      </motion.div>
    );
  }

  return (
    <motion.div className={`${cellCls} ${tileCls}${highlightCls}`} {...motionProps}>
      {inner}
    </motion.div>
  );
}

export function StatusStrip({ status, meta }: { status: ReactNode; meta?: ReactNode }) {
  const reduced = useReducedMotion() ?? false;
  return (
    <motion.header
      className="nq-dash-strip"
      aria-label="Tình trạng quán"
      initial={reduced ? {} : { opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={beat("focus")}
    >
      <div className="nq-dash-strip-glow" aria-hidden />
      <div className="nq-dash-strip-text">
        <h1 className="nq-dash-strip-kicker">NHỊP QUÁN HÔM NAY</h1>
        <p className="nq-dash-strip-status">{status}</p>
        {/* `meta` là dòng phụ: ngày + số ca. Chỉ số KHÔNG trùng thẻ KPI —
            xem `lib/status.ts::todayMetaLine` để biết vì sao. */}
        {meta ? <p className="nq-dash-strip-meta">{meta}</p> : null}
      </div>
    </motion.header>
  );
}

/**
 * Hoạ tiết nền cho vùng hero: hạt cà phê + đường nhịp tim, nét rất nhạt.
 *
 * Vì sao cần một hoạ tiết thay vì chỉ chữ trên orb gradient: hero hiện tại là
 * "tiêu đề + orb" — đúng khuôn mẫu mà bất kỳ dashboard nào cũng dán được, không
 * nói lên đây là quán cà phê. Hạt cà phê và đường nhịp tim là hai hình đã có sẵn
 * trong dấu quán (`logo-path.ts`), nên hoạ tiết này nối trang chủ với thương hiệu
 * thay vì thêm một hình mới lạ.
 *
 * Đây là **trang trí có chủ đích**, không phải icon trong câu văn — nên nó nằm
 * trong `<svg aria-hidden>`, một hình duy nhất ở tầng nền, không phải chuỗi biểu
 * tượng rắc khắp giao diện (quy ước UI của repo: không lạm dụng icon).
 *
 * Không có chuyển động: hero hiện ở **mọi lần mở trang Hôm nay**, tức là mọi ca
 * làm việc. Nền động ở đây là thứ người dùng không tắt được và không mang tin gì.
 */
export function HeroMotif() {
  return (
    <div className="nq-dash-hero__motif" aria-hidden>
      <svg viewBox="0 0 420 120" fill="none" preserveAspectRatio="xMidYMid slice">
        {/* Đường nhịp tim: một nhịp duy nhất chạy ngang, đúng dáng trong dấu quán
            (lên thẳng rồi xuống sâu rồi về đường nền). */}
        <path
          d="M-10 74H96l14-16 15 34 13-62 16 66 12-22h300"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.30"
        />
        {/* Hạt cà phê: ellipse nghiêng + rãnh giữa. Rải lệch nhau để đọc ra "hạt"
            chứ không ra "lưới chấm". */}
        {[
          { x: 44, y: 30, r: -24, s: 1 },
          { x: 150, y: 88, r: 18, s: 0.82 },
          { x: 236, y: 28, r: -12, s: 0.92 },
          { x: 330, y: 84, r: 26, s: 0.78 },
          { x: 396, y: 34, r: -30, s: 0.86 },
        ].map((b) => (
          <g key={`${b.x}-${b.y}`} transform={`translate(${b.x} ${b.y}) rotate(${b.r}) scale(${b.s})`}>
            <ellipse rx="11" ry="16" stroke="currentColor" strokeWidth="2" opacity="0.28" />
            <path d="M0-15c-4 6-4 24 0 30" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.28" />
          </g>
        ))}
      </svg>
    </div>
  );
}
