"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { STAGGER_S, beat } from "../../lib/motion";
import { matHangLabel, treoLabel } from "../../lib/present";

type TonRow = { hang?: string; so_luong?: number; don_vi?: string; duoi_nguong?: boolean };
type TreoBreakdown = { trang_thai: string; so_luong: number };
type SuaPreview = { loai?: string; luc?: string; ai?: string };

const TON_COLORS = { ok: "var(--nq-ok)", warn: "var(--nq-warn)" };
/* Bảng màu cho các lát của biểu đồ việc treo. Xếp từ "cần xử lý ngay" tới
   "chờ đủ điều kiện": đỏ → cam → ngọc → xanh dương → xám. Mỗi lát phải khác
   nhau về cả SẮC lẫn ĐỘ SÁNG vì người dùng phân biệt lát bằng cả hai, và in
   đen trắng vẫn phải tách được. */
const TREO_COLORS = ["#ef4444", "#f59e0b", "#d4af37", "#e8d48a", "#7c8a99", "#8a7228"];

function chartMotion(reduced: boolean) {
  return reduced
    ? { className: "" }
    : {
      initial: { opacity: 0, y: 8 },
      animate: { opacity: 1, y: 0 },
      transition: beat("focus"),
    };
}

/**
 * Chân khối: một dòng "Xem chi tiết →".
 *
 * Vì sao tách thành component: trước đây chỉ khối "Việc treo gần nhất" có lối đi
 * rõ ràng, ba khối còn lại (hai biểu đồ, nhật ký sửa) không có gì — người dùng
 * thấy số liệu mà không biết bấm vào đâu để xem đầy đủ, hoặc phải đoán qua menu
 * bên trái. `note` để nói rõ phạm vi số liệu khi nó KHÔNG phải "hôm nay" (ví dụ
 * sparkline neo vào mốc dữ liệu cũ nhất có thật).
 */
function BlockFoot({ href, label, note }: { href: string; label: string; note?: string }) {
  return (
    <div className="nq-block-foot">
      {note ? <span className="nq-block-foot__note">{note}</span> : <span />}
      <Link href={href}>{label} →</Link>
    </div>
  );
}

export function TonBarChart({ rows }: { rows: TonRow[] }) {
  const reduced = useReducedMotion() ?? false;
  const [hovered, setHovered] = useState<number | null>(null);
  const data = rows.filter((r) => r.hang).slice(0, 8);
  const max = Math.max(1, ...data.map((r) => Number(r.so_luong) || 0));

  if (data.length === 0) {
    return (
      <motion.div className="nq-dash-chart" {...chartMotion(reduced)}>
        <h2 className="nq-block-title nq-dash-chart-title">Kho &amp; tiêu thụ</h2>
        <p className="nq-dash-chart-empty">Chưa có dữ liệu tồn trong sổ tiêu thụ.</p>
        <BlockFoot href="/tieu-thu" label="Mở sổ tiêu thụ" />
      </motion.div>
    );
  }

  return (
    <motion.div className="nq-dash-chart nq-dash-chart--interactive" {...chartMotion(reduced)}>
      <h2 className="nq-block-title nq-dash-chart-title">Kho &amp; tiêu thụ</h2>
      {/* Tiêu đề khối nói PHẠM VI ("Kho & tiêu thụ"), không lặp lại tên hàng. Dòng
          dưới nói CHÍNH XÁC đang vẽ gì — trước đây cả hai việc dồn vào một câu
          "Tồn kho hôm nay" vừa trùng với nhãn trục vừa không nói số đang là gì. */}
      <p className="nq-dash-chart-hint">Tồn ghi nhận gần nhất theo từng nguyên liệu · di chuột để xem đơn vị</p>
      <ul className="nq-dash-bars" role="list">
        {data.map((row, i) => {
          const qty = Number(row.so_luong) || 0;
          const pct = Math.round((qty / max) * 100);
          const warn = Boolean(row.duoi_nguong);
          const ten = matHangLabel(row.hang);
          const donVi = row.don_vi || "đơn vị";
          const active = hovered === i;
          return (
            <li
              key={`${row.hang}-${i}`}
              className={`nq-dash-bar-row${active ? " nq-dash-bar-row--active" : ""}${warn ? " nq-dash-bar-row--warn" : ""}`}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(i)}
              onBlur={() => setHovered(null)}
              tabIndex={0}
            >
              <span className="nq-dash-bar-label">{ten}</span>
              <div className="nq-dash-bar-track">
                <motion.span
                  className="nq-dash-bar-fill"
                  style={{ background: warn ? TON_COLORS.warn : TON_COLORS.ok }}
                  initial={reduced ? { width: `${pct}%` } : { width: 0 }}
                  animate={{ width: `${pct}%`, opacity: active ? 1 : 0.85 }}
                  transition={beat("focus", i * STAGGER_S)}
                />
              </div>
              <span className="nq-dash-bar-val" title={`${qty} ${donVi}`}>
                {qty} <span className="nq-dash-bar-unit">{donVi}</span>
              </span>
            </li>
          );
        })}
      </ul>
      <BlockFoot href="/tieu-thu" label="Mở sổ tiêu thụ" />
    </motion.div>
  );
}

export function TreoDonutChart({ breakdown, total }: { breakdown: TreoBreakdown[]; total: number }) {
  const reduced = useReducedMotion() ?? false;
  const [activeStatus, setActiveStatus] = useState<string | null>(null);
  const slices = breakdown.filter((b) => b.so_luong > 0);
  const sum = slices.reduce((a, b) => a + b.so_luong, 0) || total || 1;
  let angle = -90;
  const r = 42;
  const cx = 52;
  const cy = 52;

  const arcs = slices.map((row, i) => {
    const n = row.so_luong;
    const sweep = (n / sum) * 360;
    const start = angle;
    angle += sweep;
    const rad = (deg: number) => (deg * Math.PI) / 180;
    const x1 = cx + r * Math.cos(rad(start));
    const y1 = cy + r * Math.sin(rad(start));
    const x2 = cx + r * Math.cos(rad(start + sweep));
    const y2 = cy + r * Math.sin(rad(start + sweep));
    const large = sweep > 180 ? 1 : 0;
    const d = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
    return { status: row.trang_thai, n, d, color: TREO_COLORS[i % TREO_COLORS.length] };
  });

  return (
    <motion.div className="nq-dash-chart nq-dash-chart--interactive" {...chartMotion(reduced)}>
      <h2 className="nq-block-title nq-dash-chart-title">Việc treo theo trạng thái</h2>
      <p className="nq-dash-chart-hint">Bấm từng mục để làm nổi bật</p>
      <div className="nq-dash-donut-wrap">
        <svg viewBox="0 0 104 104" className="nq-dash-donut" role="img" aria-label={`${total} việc treo`}>
          {arcs.length > 0 ? (
            arcs.map((a) => {
              const dim = activeStatus && activeStatus !== a.status;
              return (
                <motion.path
                  key={a.status}
                  d={a.d}
                  fill={a.color}
                  opacity={dim ? 0.35 : 1}
                  initial={reduced ? { opacity: dim ? 0.35 : 1 } : { opacity: 0, scale: 0.92 }}
                  animate={{ opacity: dim ? 0.35 : 1, scale: activeStatus === a.status ? 1.04 : 1 }}
                  transition={beat("settle")}
                  style={{ transformOrigin: `${cx}px ${cy}px`, cursor: "pointer" }}
                  onMouseEnter={() => setActiveStatus(a.status)}
                  onMouseLeave={() => setActiveStatus(null)}
                  onClick={() => setActiveStatus((s) => (s === a.status ? null : a.status))}
                />
              );
            })
          ) : (
            <circle cx={cx} cy={cy} r={r} fill="var(--nq-surface)" stroke="var(--nq-line)" />
          )}
          <circle cx={cx} cy={cy} r={26} fill="var(--nq-bg-elevated)" />
          <text x={cx} y={cy - 2} textAnchor="middle" className="nq-dash-donut-center">
            {total}
          </text>
          <text x={cx} y={cy + 12} textAnchor="middle" className="nq-dash-donut-sub">
            việc
          </text>
        </svg>
        <ul className="nq-dash-legend" role="list">
          {arcs.map((a) => (
            <li key={a.status}>
              <button
                type="button"
                className={`nq-dash-legend-btn${activeStatus === a.status ? " nq-dash-legend-btn--active" : ""}`}
                onMouseEnter={() => setActiveStatus(a.status)}
                onMouseLeave={() => setActiveStatus(null)}
                onClick={() => setActiveStatus((s) => (s === a.status ? null : a.status))}
              >
                <span className="nq-dash-legend-swatch" style={{ background: a.color }} />
                {treoLabel(a.status)} <span className="nq-dash-legend-n">({a.n})</span>
              </button>
            </li>
          ))}
          {arcs.length === 0 ? <li className="nq-muted">Chưa có việc treo</li> : null}
        </ul>
      </div>
      <BlockFoot href="/treo" label="Xem việc treo" />
    </motion.div>
  );
}

export function SuaTimeline({ items, formatLuc, ghiNhanLabel, actorLabel }: {
  items: SuaPreview[];
  formatLuc: (luc?: string) => string;
  ghiNhanLabel: (loai?: string) => string;
  actorLabel: (ai?: string) => string;
}) {
  const reduced = useReducedMotion() ?? false;
  if (items.length === 0) return null;

  return (
    <motion.section className="nq-dash-timeline nq-dash-chart" {...chartMotion(reduced)}>
      <h2 className="nq-block-title nq-dash-chart-title">Sửa lịch gần đây</h2>
      <ol className="nq-dash-timeline-list">
        {items.map((g, i) => (
          <motion.li
            key={`${g.luc}-${i}`}
            className="nq-dash-timeline-item"
            initial={reduced ? {} : { opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={beat("settle", i * STAGGER_S)}
            whileHover={reduced ? {} : { x: 4 }}
          >
            <span className="nq-dash-timeline-dot" aria-hidden />
            <div>
              <p className="nq-dash-timeline-title">{ghiNhanLabel(g.loai)}</p>
              <p className="nq-dash-timeline-sub">
                {actorLabel(g.ai)} · {formatLuc(g.luc)}
              </p>
            </div>
          </motion.li>
        ))}
      </ol>
      <BlockFoot href="/treo" label="Xem tab ghi nhận sửa" />
    </motion.section>
  );
}
