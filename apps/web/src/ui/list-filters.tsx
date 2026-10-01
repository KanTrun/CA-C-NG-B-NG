"use client";

import { ReactNode } from "react";
import { filterSummary } from "../lib/list-filters";

export type FilterOption = { value: string; label: string };

export type ListToolbarProps = {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  status?: string;
  onStatusChange?: (value: string) => void;
  statusOptions?: FilterOption[];
  statusLabel?: string;
  person?: string;
  onPersonChange?: (value: string) => void;
  personOptions?: FilterOption[];
  personLabel?: string;
  time?: string;
  onTimeChange?: (value: string) => void;
  timeOptions?: FilterOption[];
  timeLabel?: string;
  shown?: number;
  total?: number;
  filtered?: boolean;
  /**
   * Tiền tố cho `id` của các ô điều khiển. PHẢI khác nhau khi trang đặt nhiều
   * thanh lọc: `id` là duy nhất trong trang, và `<label for>` trỏ nhầm sẽ khiến
   * bấm nhãn "Trạng thái" lại nhảy con trỏ sang bộ lọc kia thay vì bộ lọc của
   * nó. `/quay` đặt cùng lúc thanh lọc menu và thanh lọc đơn.
   */
  idPrefix?: string;
  children?: ReactNode;
};

function SelectFilter({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (v: string) => void;
}) {
  if (!options.length) return null;
  return (
    <label className="nq-filter-field" htmlFor={id}>
      <span className="nq-filter-label">{label}</span>
      <select id={id} className="nq-select" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Thanh lọc + tìm kiếm cho trang danh sách — dùng token nq-input / nq-select. */
export function ListToolbar({
  search,
  onSearchChange,
  searchPlaceholder = "Tìm trong danh sách…",
  status = "all",
  onStatusChange,
  statusOptions = [],
  statusLabel = "Trạng thái",
  person = "all",
  onPersonChange,
  personOptions = [],
  personLabel = "Người liên quan",
  time = "all",
  onTimeChange,
  timeOptions = [],
  timeLabel = "Thời gian",
  shown,
  total,
  filtered = false,
  idPrefix = "nq-filter",
  children,
}: ListToolbarProps) {
  const countText =
    typeof shown === "number" && typeof total === "number"
      ? filterSummary(shown, total, filtered)
      : null;

  return (
    <div className="nq-list-toolbar" role="search">
      <div className="nq-list-toolbar-row">
        <label className="nq-filter-field nq-filter-field--grow" htmlFor={`${idPrefix}-search`}>
          <span className="nq-filter-label">Tìm kiếm</span>
          <input
            id={`${idPrefix}-search`}
            type="search"
            className="nq-input"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            autoComplete="off"
          />
        </label>
        {onStatusChange ? (
          <SelectFilter
            id={`${idPrefix}-status`}
            label={statusLabel}
            value={status}
            options={statusOptions}
            onChange={onStatusChange}
          />
        ) : null}
        {onPersonChange ? (
          <SelectFilter
            id={`${idPrefix}-person`}
            label={personLabel}
            value={person}
            options={personOptions}
            onChange={onPersonChange}
          />
        ) : null}
        {onTimeChange ? (
          <SelectFilter
            id={`${idPrefix}-time`}
            label={timeLabel}
            value={time}
            options={timeOptions}
            onChange={onTimeChange}
          />
        ) : null}
      </div>
      {(countText || children) && (
        <div className="nq-list-toolbar-meta">
          {countText ? <span className="nq-filter-count">{countText}</span> : null}
          {children}
        </div>
      )}
    </div>
  );
}

/** Empty khi lọc không ra kết quả — khác với Empty danh sách trống thật. */
export function FilteredEmpty({ onClear }: { onClear?: () => void }) {
  return (
    <div className="nq-filtered-empty">
      <p className="nq-filtered-empty-title">Không có mục khớp bộ lọc</p>
      <p className="nq-muted">Thử đổi từ khóa hoặc mở rộng trạng thái / thời gian.</p>
      {onClear ? (
        <button type="button" className="nq-filter-clear" onClick={onClear}>
          Xóa bộ lọc
        </button>
      ) : null}
    </div>
  );
}
