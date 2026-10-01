"use client";

/**
 * QUÁNVERSE — panel chi tiết khu vực (hoặc hướng dẫn chọn khi chưa chọn).
 * Luôn chiếm chỗ dưới map — không để cột map trống nửa dưới.
 */

import { Icon } from "../../../icons";
import {
  CHUA_CO_DU_LIEU,
  type QuanverseZone,
  type QuanverseZoneStatus,
  formatSo,
} from "../quanverse-contract";
import { MucDoChip, ThanhTai } from "./kit";

const NHAN: Record<QuanverseZoneStatus, string> = {
  on_dinh: "Ổn định",
  chu_y: "Đang chú ý",
  qua_tai: "Đang tải cao",
  chua_co_du_lieu: CHUA_CO_DU_LIEU,
};

export default function ZoneFocus({
  zone,
  zones,
  onClear,
  onAsk,
  onFocusActions,
  onPickZone,
}: {
  zone: QuanverseZone | null;
  zones: readonly QuanverseZone[];
  onClear: () => void;
  onAsk: (question: string) => void;
  onFocusActions: () => void;
  onPickZone: (zoneId: string) => void;
}) {
  if (!zone) {
    const goiY = zones.slice(0, 4);
    return (
      <div className="nq-qvfocus nq-qvfocus--idle" data-testid="quanverse-zone-focus">
        <div className="nq-qvfocus__head">
          <strong className="nq-qvfocus__ten">Chọn khu vực trên bản đồ</strong>
        </div>
        <p className="nq-qvfocus__idle">
          Bấm một khu vực để lọc việc cần xử lý, sự kiện và hỏi AI đúng ngữ cảnh.
        </p>
        {goiY.length > 0 ? (
          <div className="nq-qvfocus__cta">
            {goiY.map((z) => (
              <button
                key={z.zoneId}
                type="button"
                className="nq-qvfocus__btn nq-qvfocus__btn--ghost"
                data-testid={`zone-focus-pick-${z.zoneId}`}
                onClick={() => onPickZone(z.zoneId)}
              >
                {z.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  const severity =
    zone.status === "qua_tai" ? "danger" : zone.status === "chu_y" ? "warn" : "ok";

  return (
    <div className="nq-qvfocus" data-testid="quanverse-zone-focus" data-zone={zone.zoneId}>
      <div className="nq-qvfocus__head">
        <MucDoChip severity={severity} />
        <strong className="nq-qvfocus__ten">{zone.label}</strong>
        <span className="nq-qvfocus__status">{NHAN[zone.status]}</span>
        <button
          type="button"
          className="nq-qvfocus__clear"
          data-testid="zone-focus-clear"
          onClick={onClear}
        >
          Bỏ chọn
        </button>
      </div>

      <dl className="nq-qvfocus__facts">
        <div>
          <dt>Tải</dt>
          <dd>
            {formatSo(zone.load)}
            {zone.threshold !== null ? ` / ${formatSo(zone.threshold)}` : ""}
          </dd>
        </div>
        <div>
          <dt>Hàng chờ</dt>
          <dd>{formatSo(zone.queue)}</dd>
        </div>
        <div>
          <dt>Nhân sự</dt>
          <dd>
            {formatSo(zone.assignedStaff)}
            {zone.assignedNames.length > 0
              ? ` · ${zone.assignedNames.join(", ")}`
              : ""}
          </dd>
        </div>
      </dl>

      <ThanhTai load={zone.load} threshold={zone.threshold} />

      {zone.alerts[0] ? (
        <p className="nq-qvfocus__alert">{zone.alerts[0].message}</p>
      ) : null}

      <div className="nq-qvfocus__cta">
        <button
          type="button"
          className="nq-qvfocus__btn"
          data-testid="zone-focus-ask"
          onClick={() =>
            onAsk(`Vì sao ${zone.label} đang ${NHAN[zone.status].toLowerCase()}?`)
          }
        >
          <Icon name="info" size={13} />
          Hỏi AI về khu vực
        </button>
        <button
          type="button"
          className="nq-qvfocus__btn nq-qvfocus__btn--ghost"
          data-testid="zone-focus-actions"
          onClick={onFocusActions}
        >
          Xem việc liên quan
        </button>
      </div>
    </div>
  );
}
