"use client";

import type { KhungGio, RosterShift } from "../../lib/roster";
import { khungOrder, rosterCellSummary, shiftRowParts, shortNameParts } from "../../lib/roster";
import { Icon } from "../../ui/icons";

const KHUNGS = ["sang", "chieu", "toi"] as const;
const DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"] as const;
/**
 * Trần số người hiện trong một ô trước khi gom "+N nữa".
 *
 * Ô lịch chỉ rộng ~150px, nên một ca đông vẫn cần một giới hạn để không đẩy
 * cả lưới cao vọt. Trần này đặt CAO (10) có chủ đích: ca bar phổ biến 3–6
 * người luôn hiện đủ, chỉ ca đặc biệt mới nén lại — và khi nén thì số người bị
 * ẩn vẫn nằm ở tooltip.
 */
const CREW_VISIBLE = 10;

type DayLabel = { title: string; date: string; isToday?: boolean };

type Props = {
  byDay: Record<string, RosterShift[]>;
  phanCong: Record<string, string[]>;
  khungGio?: KhungGio;
  dayLabels: DayLabel[];
  spotlightDay: string | null;
  filterKhung: string;
  filterViTri: string;
  searchNeedle: string;
  viTriLabel: (vt?: string) => string;
  nvName: (id: string) => string;
  matchCell: (assigned: string[], shift: RosterShift) => boolean;
  onSelectDay: (day: string) => void;
  nvStatusMap?: Record<string, string>;
  pins?: Array<{ ca_id: string; nv_id: string }>;
};

function countLabel(assigned: number, required: number, tone: "ok" | "warn" | "empty"): string {
  if (tone === "empty") return "Trống ca";
  if (assigned > required) return `Dư · ${assigned}/${required}`;
  if (tone === "ok") return `Đủ · ${assigned}/${required}`;
  return `Thiếu · ${assigned}/${required}`;
}

export function RosterGrid({
  byDay,
  phanCong,
  khungGio,
  dayLabels,
  spotlightDay,
  filterKhung,
  onSelectDay,
  viTriLabel,
  nvName,
  matchCell,
  nvStatusMap,
  pins = [],
}: Props) {
  const visibleKhungs = filterKhung === "all" ? KHUNGS : KHUNGS.filter((k) => k === filterKhung);

  return (
    <>
      <ul className="nq-roster-legend" aria-label="Chú giải lịch tuần">
        <li>
          <span className="nq-roster-legend__swatch nq-roster-legend__swatch--ok" aria-hidden="true" />
          Đủ người
        </li>
        <li>
          <span className="nq-roster-legend__swatch nq-roster-legend__swatch--warn" aria-hidden="true" />
          Thiếu người
        </li>
        <li>
          <span className="nq-roster-legend__swatch nq-roster-legend__swatch--danger" aria-hidden="true" />
          Trống ca
        </li>
      </ul>
      <div className="nq-roster-wrap">
        <table
          className="nq-roster-table nq-roster-table--compact nq-roster-table--fit"
          style={{ ["--roster-rows" as string]: String(Math.max(visibleKhungs.length, 1)) }}
        >
          <caption className="nq-roster-caption">
            Lưới tuần — bấm ô hoặc tiêu đề ngày để mở chi tiết và chỉnh nhân sự
          </caption>
          {/* `table-layout: fixed` + colgroup: cột Khung cố định, 7 ngày chia đều.
              Dưới ~860px quay lại auto + cuộn ngang (xem globals). */}
          <colgroup>
            <col style={{ width: "9.5rem" }} />
            {DAYS.map((d) => (
              <col key={d} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className="nq-roster-corner">
                Khung
              </th>
              {DAYS.map((d, i) => {
                const dayShifts = byDay[d] ?? [];
                let total = 0;
                dayShifts.forEach((s) => {
                  total += (phanCong[s.id] ?? []).length;
                });
                const lit = spotlightDay === d;
                const isToday = Boolean(dayLabels[i]?.isToday);
                return (
                  <th
                    key={d}
                    scope="col"
                    className={`nq-roster-day-head${lit ? " nq-roster-day-head--spot" : ""}${isToday ? " nq-roster-day-head--today" : ""}`}
                  >
                    <button
                      type="button"
                      className="nq-roster-day-btn"
                      onClick={() => onSelectDay(d)}
                      aria-pressed={lit}
                      aria-current={isToday ? "date" : undefined}
                    >
                      <span className="nq-roster-day-title-row">
                        <span className="nq-roster-day-full">{dayLabels[i]?.title}</span>
                        <span className="nq-roster-day-short">{d}</span>
                        <span className="nq-roster-day-date">{dayLabels[i]?.date}</span>
                      </span>
                      <span className="nq-roster-day-meta">{total} NV</span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visibleKhungs.map((khung, rowIdx) => {
              const sample = DAYS.map((d) => (byDay[d] ?? []).find((c) => c.khung === khung)).find(Boolean);
              const parts = shiftRowParts(sample, khung, khungGio);
              const rowLabel = parts.time ? `${parts.title} · ${parts.time}` : parts.title;
              return (
                <tr
                  key={khung}
                  className={`nq-roster-band nq-roster-band--${khung} ${rowIdx % 2 === 0 ? "nq-roster-band--even" : "nq-roster-band--odd"}`}
                >
                  <th scope="row" className="nq-roster-row-label">
                    <span className="nq-roster-row-label__title">{parts.title}</span>
                    {parts.time ? <span className="nq-roster-row-label__time">{parts.time}</span> : null}
                  </th>
                  {DAYS.map((d) => {
                    const shifts = (byDay[d] ?? []).filter((c) => c.khung === khung);
                    const assigned = [...new Set(shifts.flatMap((shift) => phanCong[shift.id] ?? []))];
                    const visibleShifts = shifts.filter((shift) => matchCell(phanCong[shift.id] ?? [], shift));
                    const dimmed = shifts.length > 0 && visibleShifts.length === 0;
                    const lit = spotlightDay === d;
                    const roles = [...new Set(shifts.map((shift) => viTriLabel(shift.vi_tri)).filter(Boolean))];
                    const roleLabel = roles.length > 0 ? roles.join(" · ") : "Nhiều vị trí";
                    const required = shifts.reduce(
                      (sum, shift) => sum + Number(shift.so_nguoi_toi_thieu ?? 1),
                      0,
                    );
                    const summary = rosterCellSummary(assigned.length, roleLabel, assigned.length < required);
                    const hasUnconfirmed = assigned.some((id) => nvStatusMap?.[id] === "chua_xac_nhan");
                    const pinnedIds = new Set(
                      pins
                        .filter((pin) => shifts.some((shift) => shift.id === pin.ca_id))
                        .map((pin) => pin.nv_id),
                    );
                    const overflow = Math.max(0, assigned.length - CREW_VISIBLE);
                    const statusText = countLabel(assigned.length, required, summary.tone);

                    return (
                      <td
                        key={d}
                        className={`nq-roster-slot ${lit ? "nq-roster-slot--spot" : ""}`}
                        data-dimmed={dimmed ? "1" : undefined}
                      >
                        {shifts.length > 0 ? (
                          <button
                            type="button"
                            className={`nq-roster-slot-btn nq-roster-slot-btn--${summary.tone}`}
                            data-unconfirmed={hasUnconfirmed ? "1" : undefined}
                            onClick={() => onSelectDay(d)}
                            aria-label={`${dayLabels[DAYS.indexOf(d)]?.title} ${rowLabel}: ${statusText}, ${roleLabel}${hasUnconfirmed ? " (Có nhân sự chưa xác nhận lịch)" : ""}`}
                          >
                            <span
                              className={`nq-roster-slot-accent nq-roster-slot-accent--${summary.tone}`}
                              aria-hidden="true"
                            />
                            <span className="nq-roster-slot-body">
                              <span className="nq-roster-slot-head">
                                <span className="nq-roster-slot-count">{statusText}</span>
                                {hasUnconfirmed && (
                                  <span className="nq-roster-slot-flag" title="Có nhân sự chưa xác nhận lịch">
                                    <Icon name="warn" size={12} />
                                  </span>
                                )}
                              </span>
                              <span className="nq-roster-slot-crew">
                                {assigned.length > 0 ? (
                                  <>
                                    {/* Mỗi nhân sự là MỘT ô riêng có viền và nền.
                                        Trước đây tên nằm trần cạnh nhau nên
                                        người xếp lịch không đếm được ai với ai
                                        và chữ dính vào nhau khi cột hẹp. */}
                                    {assigned.slice(0, CREW_VISIBLE).map((id) => {
                                      const full = nvName(id);
                                      const { primary, role } = shortNameParts(full);
                                      const pinned = pinnedIds.has(id);
                                      return (
                                        <span
                                          key={id}
                                          className="nq-roster-crew-chip"
                                          data-pinned={pinned ? "1" : undefined}
                                          title={`${full}${role ? ` · ${role}` : ""}${pinned ? " · ghim ca" : ""}`}
                                        >
                                          <span className="nq-roster-crew-chip__who">{primary}</span>
                                          {role ? <span className="nq-roster-crew-chip__role">{role}</span> : null}
                                        </span>
                                      );
                                    })}
                                    {overflow > 0 && (
                                      <span
                                        className="nq-roster-crew-chip nq-roster-crew-chip--more"
                                        title={assigned.slice(CREW_VISIBLE).map((id) => nvName(id)).join(", ")}
                                      >
                                        +{overflow} nữa
                                      </span>
                                    )}
                                  </>
                                ) : (
                                  <span className="nq-roster-slot-none">Chưa xếp người</span>
                                )}
                              </span>
                            </span>
                          </button>
                        ) : (
                          <span className="nq-muted">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

export { DAYS as ROSTER_DAYS, KHUNGS as ROSTER_KHUNGS, khungOrder };
