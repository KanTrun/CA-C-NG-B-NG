"use client";

/**
 * QUÁNVERSE — War-room lite "Nếu thì ngày mai" (P3).
 *
 * Read-only, không gọi server, không ghi DB. Mọi số suy từ `capacity` +
 * `zones` đã tải (đơn thật hoặc mô phỏng có nhãn) — không bịa thêm.
 * Hành động thật (đổi ca/mode) đi qua trang chuyên trách + propose/confirm.
 */

import Link from "next/link";
import { useState } from "react";
import type { QuanverseCapacity, QuanverseZone } from "../quanverse-contract";
import { formatSo } from "../quanverse-contract";
import { Card, CardHead, NguonChip } from "./kit";

type Preset = "mua_lon" | "doan_20" | "thieu_1nv";

const PRESETS: Array<{ id: Preset; label: string }> = [
  { id: "mua_lon", label: "Mưa lớn" },
  { id: "doan_20", label: "Đoàn 20 khách" },
  { id: "thieu_1nv", label: "Thiếu 1 nhân sự" },
];

export default function WarRoomLite({
  capacity,
  zones,
  isMock,
}: {
  capacity: QuanverseCapacity;
  zones: readonly QuanverseZone[];
  isMock: boolean;
}) {
  const [preset, setPreset] = useState<Preset | null>(null);

  const points = capacity.points;
  const dinh = points.length > 0 ? Math.max(...points.map((p) => p.demand ?? 0), 0) : 0;
  const gioDinh = points.filter((p) => (p.demand ?? 0) === dinh && dinh > 0).map((p) => p.hour);
  const pha = zones.find((z) => z.zoneId === "quay_pha");
  const nguongPha = pha?.threshold ?? 5;
  const taiPha = pha?.load ?? null;

  function ketQua(): string | null {
    if (!preset) return null;
    if (!capacity.hasHistory) return "Chưa đủ lịch sử đơn để ước tính — cần thêm ngày có đơn thật.";
    if (preset === "mua_lon") {
      const du = dinh * 1.25;
      const qua = taiPha !== null ? taiPha + Math.round(du - dinh) : null;
      return (
        `Mưa lớn thường dồn khách vào giờ cao điểm (${gioDinh.length > 0 ? gioDinh.map((h) => `${String(h).padStart(2, "0")}:00`).join(", ") : "—"}). ` +
        `Nhu cầu ước tính ${formatSo(dinh)} → ${formatSo(Math.round(du * 10) / 10)} đơn/giờ. ` +
        (qua !== null ? `Quầy pha từ ${formatSo(taiPha)} lên ~${qua} đơn (ngưỡng ${formatSo(nguongPha)}). ` : "") +
        "Nên chuẩn bị người trực quầy pha trước giờ đỉnh."
      );
    }
    if (preset === "doan_20") {
      return (
        `Đoàn 20 khách ≈ +20 đơn dồn vào 1–2 giờ tới. ` +
        `Giờ đỉnh hiện ${formatSo(dinh)} đơn/giờ sẽ lên ~${formatSo(dinh + 10)} đơn/giờ nếu đoàn tới đúng đỉnh. ` +
        "Nên tách đơn đoàn thành 2 đợt và báo trước cho quầy pha."
      );
    }
    const tongNv = zones.reduce((s, z) => s + (z.assignedStaff ?? 0), 0);
    return (
      `Thiếu 1 nhân sự trên tổng ${formatSo(tongNv)} người đang phân khu. ` +
      "Khu vực tải cao nhất nên được ưu tiên giữ người; khu bàn rảnh có thể điều 1 người sang quầy pha. " +
      "Quyết định điều người thực hiện ở Lịch tuần."
    );
  }

  const kq = ketQua();

  return (
    <Card className="nq-qvwr" label="Nếu thì ngày mai" testId="quanverse-warroom-lite">
      <CardHead
        title="Nếu thì ngày mai"
        icon="info"
        trailing={
          isMock ? (
            <span className="nq-qv-badge-mock">Dữ liệu mô phỏng</span>
          ) : (
            <NguonChip>Ước tính từ dự báo</NguonChip>
          )
        }
      />

      <div className="nq-qvwr__presets" role="group" aria-label="Chọn tình huống giả định">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`nq-qvwr__preset${preset === p.id ? " is-on" : ""}`}
            aria-pressed={preset === p.id}
            data-testid={`warroom-preset-${p.id}`}
            onClick={() => setPreset((cur) => (cur === p.id ? null : p.id))}
          >
            {p.label}
          </button>
        ))}
      </div>

      {kq ? (
        <>
          <p className="nq-qvwr__result" data-testid="warroom-result">
            {kq}
          </p>
          <p className="nq-qvai__disclaimer">
            Ước tính đọc thêm — không phải lệnh điều hành.{" "}
            <Link className="nq-linkbtn" href="/lich-tuan">
              Mở Lịch tuần để hành động
            </Link>
          </p>
        </>
      ) : (
        <p className="nq-qv-trong" data-testid="warroom-empty">
          <span className="nq-qv-trong__text">Chọn một tình huống để xem ước tính</span>
          <span className="nq-qv-trong__hint">
            Mưa lớn · Đoàn 20 khách · Thiếu 1 nhân sự — số suy từ dự báo đang hiện.
          </span>
        </p>
      )}
    </Card>
  );
}
