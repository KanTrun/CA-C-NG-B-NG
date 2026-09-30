"use client";

/**
 * QUÁNVERSE — F. NĂNG LỰC / TẢI VẬN HÀNH (tương tác).
 *
 * SVG thuần: hover giờ, click peak/điểm → báo giờ chọn lên trang (để prefill AI).
 * Dual series: nhu cầu + hàng đợi dự báo. Empty trung thực khi chưa đủ lịch sử.
 */

import {
  CHUA_CO_DU_LIEU,
  type QuanverseCapacity,
  formatSo,
} from "../quanverse-contract";
import { Card, CardHead, NguonChip } from "./kit";

const W = 560;
const H = 150;
const PAD_X = 26;
const PAD_Y = 14;

export default function CapacityForecast({
  capacity,
  isMock,
  selectedHour,
  onSelectHour,
}: {
  capacity: QuanverseCapacity;
  isMock: boolean;
  selectedHour: number | null;
  onSelectHour: (hour: number | null) => void;
}) {
  const points = capacity.points;
  const coDuLieu = capacity.hasHistory && points.some((p) => p.demand !== null);

  const maxDemand = coDuLieu
    ? Math.max(
        ...points.map((p) => Math.max(p.demand ?? 0, p.backlog ?? 0)),
        1,
      )
    : 1;

  const x = (i: number) =>
    PAD_X + (i / Math.max(1, points.length - 1)) * (W - PAD_X * 2);
  const y = (v: number) => H - PAD_Y - (v / maxDemand) * (H - PAD_Y * 2);

  const duongDemand = coDuLieu
    ? points
        .map(
          (p, i) =>
            `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p.demand ?? 0).toFixed(1)}`,
        )
        .join(" ")
    : "";

  const duongBacklog = coDuLieu
    ? points
        .map(
          (p, i) =>
            `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p.backlog ?? 0).toFixed(1)}`,
        )
        .join(" ")
    : "";

  const selected = points.find((p) => p.hour === selectedHour) ?? null;

  return (
    <Card className="nq-qvcap" label="Năng lực vận hành" testId="quanverse-capacity">
      <CardHead
        title="Năng lực / tải vận hành"
        icon="info"
        trailing={
          isMock ? (
            <span className="nq-qv-badge-mock">Dữ liệu mô phỏng</span>
          ) : capacity.daysOfData !== null ? (
            <NguonChip>{`${capacity.daysOfData} ngày dữ liệu`}</NguonChip>
          ) : null
        }
      />

      {points.length === 0 ? (
        <div className="nq-qvcap__emptyfill" data-testid="capacity-empty">
          <p className="nq-qv-trong">
            <span className="nq-qv-trong__text">{CHUA_CO_DU_LIEU}</span>
            <span className="nq-qv-trong__hint">Chưa đọc được chuỗi dự báo.</span>
          </p>
          <ul className="nq-qvcap__empty-steps">
            <li>API `/forecast` cần phản hồi series 07:00–22:00</li>
            <li>Hoặc bật mô phỏng để xem biểu đồ tương tác đủ</li>
          </ul>
        </div>
      ) : !coDuLieu ? (
        <div className="nq-qvcap__emptyfill" data-testid="capacity-no-history">
          <p className="nq-qv-trong">
            <span className="nq-qv-trong__text">
              Chưa đủ dữ liệu lịch sử để dự báo
            </span>
            <span className="nq-qv-trong__hint">
              Cần thêm ngày có đơn thật để đường dự báo có nghĩa — không vẽ đường
              phẳng 0 giả.
            </span>
          </p>
          <ul className="nq-qvcap__empty-steps">
            <li>Ghi đơn quầy trong ngày → stations/forecast tự đầy</li>
            <li>Pitch ngay: bật Mô phỏng · Giờ cao điểm</li>
          </ul>
        </div>
      ) : (
        <>
          <div className="nq-qvcap__chart">
            <svg
              viewBox={`0 0 ${W} ${H}`}
              width="100%"
              role="img"
              aria-label={`Nhu cầu theo giờ, cao nhất ${formatSo(maxDemand)} đơn mỗi giờ`}
            >
              <line
                className="nq-qvcap__axis"
                x1={PAD_X}
                y1={H - PAD_Y}
                x2={W - PAD_X}
                y2={H - PAD_Y}
              />
              <line
                className="nq-qvcap__axis"
                x1={PAD_X}
                y1={PAD_Y}
                x2={PAD_X}
                y2={H - PAD_Y}
              />
              <path className="nq-qvcap__line nq-qvcap__line--backlog" d={duongBacklog} fill="none" />
              <path className="nq-qvcap__line" d={duongDemand} fill="none" />
              {points.map((p, i) => {
                const isPeak = capacity.peaks.includes(p.hour);
                const isSel = selectedHour === p.hour;
                return (
                  <g key={p.hour}>
                    <circle
                      className={`nq-qvcap__dot${isPeak ? " is-peak" : ""}${
                        isSel ? " is-selected" : ""
                      }`}
                      cx={x(i)}
                      cy={y(p.demand ?? 0)}
                      r={isSel ? 5 : isPeak ? 3.5 : 2.5}
                      data-testid={`cap-hour-${p.hour}`}
                      role="button"
                      tabIndex={0}
                      aria-label={`Giờ ${String(p.hour).padStart(2, "0")}:00, nhu cầu ${formatSo(p.demand)}`}
                      onClick={() =>
                        onSelectHour(isSel ? null : p.hour)
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onSelectHour(isSel ? null : p.hour);
                        }
                      }}
                    />
                  </g>
                );
              })}
            </svg>
          </div>

          <ul className="nq-qvcap__hours" aria-hidden="true">
            {points.map((p) => (
              <li
                key={p.hour}
                className={selectedHour === p.hour ? "is-selected" : undefined}
              >
                <button
                  type="button"
                  className="nq-qvcap__hourbtn"
                  onClick={() =>
                    onSelectHour(selectedHour === p.hour ? null : p.hour)
                  }
                >
                  {String(p.hour).padStart(2, "0")}
                </button>
              </li>
            ))}
          </ul>

          <div className="nq-qvcap__legend">
            <span className="nq-qvcap__legend-item nq-qvcap__legend-item--demand">
              Nhu cầu
            </span>
            <span className="nq-qvcap__legend-item nq-qvcap__legend-item--backlog">
              Hàng đợi dự báo
            </span>
          </div>

          {selected ? (
            <p className="nq-qvcap__selected" data-testid="capacity-selected">
              {String(selected.hour).padStart(2, "0")}:00 — nhu cầu{" "}
              {formatSo(selected.demand)}, hàng đợi {formatSo(selected.backlog)}
            </p>
          ) : capacity.peaks.length > 0 ? (
            <p className="nq-qvcap__peaks">
              Giờ đông nhất:{" "}
              {capacity.peaks
                .map((h) => `${String(h).padStart(2, "0")}:00`)
                .join(", ")}
              {" · "}
              <button
                type="button"
                className="nq-linkbtn"
                data-testid="capacity-peak-ask"
                onClick={() => onSelectHour(capacity.peaks[0] ?? null)}
              >
                Chọn giờ đỉnh
              </button>
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}
