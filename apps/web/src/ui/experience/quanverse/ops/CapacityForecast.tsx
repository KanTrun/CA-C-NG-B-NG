"use client";

/**
 * QUÁNVERSE — F. NĂNG LỰC / TẢI VẬN HÀNH.
 *
 * Biểu đồ SVG thuần (không thư viện chart). Khi chưa đủ lịch sử, khối nói
 * THẲNG "Chưa đủ dữ liệu lịch sử để dự báo" và KHÔNG vẽ đường — vẽ một đường
 * phẳng 0 sẽ trông y như dữ liệu thật và đánh lừa người đọc.
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
}: {
  capacity: QuanverseCapacity;
  isMock: boolean;
}) {
  const points = capacity.points;
  const coDuLieu = capacity.hasHistory && points.some((p) => p.demand !== null);

  const maxDemand = coDuLieu
    ? Math.max(...points.map((p) => p.demand ?? 0), 1)
    : 1;

  const x = (i: number) =>
    PAD_X + (i / Math.max(1, points.length - 1)) * (W - PAD_X * 2);
  const y = (v: number) => H - PAD_Y - (v / maxDemand) * (H - PAD_Y * 2);

  const duong = coDuLieu
    ? points
        .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p.demand ?? 0).toFixed(1)}`)
        .join(" ")
    : "";

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
        <p className="nq-qv-trong" data-testid="capacity-empty">
          <span className="nq-qv-trong__text">{CHUA_CO_DU_LIEU}</span>
          <span className="nq-qv-trong__hint">Chưa đọc được chuỗi dự báo.</span>
        </p>
      ) : !coDuLieu ? (
        <p className="nq-qv-trong" data-testid="capacity-no-history">
          <span className="nq-qv-trong__text">
            Chưa đủ dữ liệu lịch sử để dự báo
          </span>
          <span className="nq-qv-trong__hint">
            Cần thêm ngày có đơn thật để đường dự báo có nghĩa.
          </span>
        </p>
      ) : (
        <>
          <div className="nq-qvcap__chart">
            <svg
              viewBox={`0 0 ${W} ${H}`}
              width="100%"
              role="img"
              aria-label={`Nhu cầu theo giờ, cao nhất ${formatSo(maxDemand)} đơn mỗi giờ`}
            >
              <line className="nq-qvcap__axis" x1={PAD_X} y1={H - PAD_Y} x2={W - PAD_X} y2={H - PAD_Y} />
              <line className="nq-qvcap__axis" x1={PAD_X} y1={PAD_Y} x2={PAD_X} y2={H - PAD_Y} />
              <path className="nq-qvcap__line" d={duong} fill="none" />
              {points.map((p, i) =>
                capacity.peaks.includes(p.hour) ? (
                  <circle
                    key={p.hour}
                    className="nq-qvcap__peak"
                    cx={x(i)}
                    cy={y(p.demand ?? 0)}
                    r={3.5}
                  />
                ) : null,
              )}
            </svg>
          </div>

          <ul className="nq-qvcap__hours" aria-hidden="true">
            {points.map((p) => (
              <li key={p.hour}>{String(p.hour).padStart(2, "0")}</li>
            ))}
          </ul>

          {capacity.peaks.length > 0 ? (
            <p className="nq-qvcap__peaks">
              Giờ đông nhất:{" "}
              {capacity.peaks.map((h) => `${String(h).padStart(2, "0")}:00`).join(", ")}
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}
