"use client";

/**
 * QUÁNVERSE — panel chi tiết khu vực đang chọn (con trỏ hệ thống).
 *
 * Hiện ngay dưới bản đồ khi có selectedZone. Không card lồng card: panel nằm
 * trong cột map, chỉ là khối thông tin + CTA hỏi AI / xem việc.
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
  onClear,
  onAsk,
  onFocusActions,
}: {
  zone: QuanverseZone | null;
  onClear: () => void;
  onAsk: (question: string) => void;
  onFocusActions: () => void;
}) {
  if (!zone) return null;

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
