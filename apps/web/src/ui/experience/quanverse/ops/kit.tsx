"use client";

/**
 * QUÁNVERSE — khối dùng chung của trang điều hành.
 *
 * Gom ở đây thay vì rải mỗi khối một file: những mảnh này chỉ có nghĩa BÊN
 * TRONG một thẻ vận hành (nhãn mục, chip nguồn, dòng trống, thanh tải), nên
 * tách file riêng chỉ làm tăng số lần nhảy file mà không tăng ranh giới thật.
 */

import type { ReactNode } from "react";
import { Icon } from "../../../icons";
import { KHONG_CO_DU_LIEU } from "../quanverse-contract";

export type Tone = "neutral" | "ok" | "warn" | "danger";

/** Nhãn đầu một thẻ vận hành: tiêu đề + nguồn + khe co giãn. */
export function CardHead({
  title,
  source,
  icon,
  trailing,
}: {
  title: string;
  source?: string | null;
  icon?: Parameters<typeof Icon>[0]["name"];
  trailing?: ReactNode;
}) {
  return (
    <div className="nq-qv-card__head">
      {icon ? <Icon name={icon} size={15} /> : null}
      <h2 className="nq-qv-card__title">{title}</h2>
      {source ? <span className="nq-qv-card__source">{source}</span> : null}
      <span className="nq-qv-card__spacer" />
      {trailing}
    </div>
  );
}

/** Thẻ vận hành — đơn vị bố cục duy nhất của trang. */
export function Card({
  children,
  tone = "neutral",
  className = "",
  testId,
  label,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  testId?: string;
  label?: string;
}) {
  return (
    <section
      className={`nq-qv-card nq-qv-card--${tone} ${className}`.trim()}
      data-testid={testId}
      aria-label={label}
    >
      {children}
    </section>
  );
}

/** Nhãn mức độ (severity) — chữ, không chỉ màu. */
export function MucDoChip({ severity }: { severity: Tone }) {
  const nhan: Record<Tone, string> = {
    danger: "Khẩn",
    warn: "Chú ý",
    ok: "Ổn",
    neutral: "Thông tin",
  };
  return (
    <span className={`nq-qv-sev nq-qv-sev--${severity}`}>{nhan[severity]}</span>
  );
}

/** Nguồn dữ liệu — luôn hiện để người đọc biết số này từ đâu ra. */
export function NguonChip({ children }: { children: ReactNode }) {
  return <span className="nq-qv-nguon">{children}</span>;
}

/**
 * Trạng thái TRỐNG.
 *
 * Luôn nói RÕ chưa có dữ liệu — tuyệt đối không để chỗ trống im lặng khiến
 * người đọc tưởng là "không có việc gì".
 */
export function Trong({ text, hint }: { text: string; hint?: string }) {
  return (
    <p className="nq-qv-trong">
      <span className="nq-qv-trong__text">{text}</span>
      {hint ? <span className="nq-qv-trong__hint">{hint}</span> : null}
    </p>
  );
}

/**
 * Thanh tải của một khu vực.
 *
 * `load === null` ⇒ KHÔNG vẽ thanh (vẽ thanh 0% là nói dối "khu vực rảnh").
 */
export function ThanhTai({
  load,
  threshold,
}: {
  load: number | null;
  threshold: number | null;
}) {
  if (load === null || threshold === null || threshold <= 0) {
    return <span className="nq-qv-tai__unknown">{KHONG_CO_DU_LIEU}</span>;
  }
  const pct = Math.min(100, Math.round((load / threshold) * 100));
  return (
    <span className="nq-qv-tai" aria-hidden="true">
      <span className="nq-qv-tai__fill" style={{ width: `${pct}%` }} />
    </span>
  );
}
