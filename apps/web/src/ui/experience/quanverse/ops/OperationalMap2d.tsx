"use client";

/**
 * QUÁNVERSE — C. TRẠNG THÁI QUÁN HIỆN TẠI: bản đồ khu vực 2D.
 *
 * 2D / DOM / CSS thuần. KHÔNG Canvas, KHÔNG WebGL, KHÔNG thư viện bản đồ —
 * trang phải render được cả khi trình duyệt không có WebGL.
 *
 * Yêu cầu truy cập: mỗi khu vực là một `<button>` THẬT (Tab tới được, Enter/Space
 * kích hoạt), có `aria-pressed` và nhãn `aria-label` đọc được cả trạng thái.
 *
 * Màu CHỈ dùng để biểu đạt trạng thái; trạng thái luôn có chữ đi kèm nên người
 * không phân biệt màu vẫn đọc được.
 */

import { Icon } from "../../../icons";
import {
  CHUA_CO_DU_LIEU,
  KHONG_CO_DU_LIEU,
  type QuanverseZone,
  type QuanverseZoneStatus,
  formatSo,
} from "../quanverse-contract";
import { CardHead, Card, ThanhTai } from "./kit";

const NHAN_TRANG_THAI: Record<QuanverseZoneStatus, string> = {
  on_dinh: "Ổn định",
  chu_y: "Đang chú ý",
  qua_tai: "Đang tải cao",
  chua_co_du_lieu: CHUA_CO_DU_LIEU,
};

export default function OperationalMap2d({
  zones,
  selectedId,
  onSelect,
}: {
  zones: readonly QuanverseZone[];
  selectedId: string | null;
  onSelect: (zoneId: string | null) => void;
}) {
  const coCanhBao = zones.some((z) => z.status === "qua_tai");

  return (
    <Card className="nq-qvmap" label="Trạng thái quán hiện tại" testId="quanverse-map">
      <CardHead
        title="Trạng thái quán hiện tại"
        icon="location"
        trailing={
          <span className="nq-qvmap__legend" aria-label="Chú giải: Ổn định, Chú ý, Quá tải">
            <span className="nq-qvmap__legend-item nq-qvmap__legend-item--on_dinh" aria-hidden="true" /> Ổn định
            <span className="nq-qvmap__legend-item nq-qvmap__legend-item--chu_y" aria-hidden="true" /> Chú ý
            <span className="nq-qvmap__legend-item nq-qvmap__legend-item--qua_tai" aria-hidden="true" /> Quá tải
            <span className="nq-sr-only">Màu chỉ minh hoạ, trạng thái luôn có chữ đi kèm.</span>
          </span>
        }
      />

      {zones.length === 0 ? (
        <p className="nq-qv-trong">
          <span className="nq-qv-trong__text">{CHUA_CO_DU_LIEU}</span>
          <span className="nq-qv-trong__hint">
            Chưa đọc được danh sách khu vực từ hệ thống.
          </span>
        </p>
      ) : (
        <ul className="nq-qvmap__grid" role="list">
          {zones.map((z) => {
            const dangChon = selectedId === z.zoneId;
            const thieu = z.load === null && z.queue === null;
            return (
              <li key={z.zoneId}>
                <button
                  type="button"
                  className={`nq-qvzone nq-qvzone--${z.status}${
                    dangChon ? " is-selected" : ""
                  }`}
                  data-testid={`qv-zone-${z.zoneId}`}
                  data-trang-thai={z.status}
                  aria-pressed={dangChon}
                  aria-label={`${z.label} — ${NHAN_TRANG_THAI[z.status]}${
                    z.load !== null ? `, tải ${z.load}` : ", chưa rõ tải"
                  }${
                    z.threshold !== null ? ` trên ngưỡng ${z.threshold}` : ""
                  }${
                    z.queue !== null ? `, ${z.queue} đơn chờ` : ""
                  }`}
                  onClick={() => onSelect(dangChon ? null : z.zoneId)}
                >
                  <span className="nq-qvzone__top">
                    <span className="nq-qvzone__ten">{z.label}</span>
                    <span className="nq-qvzone__status">
                      {NHAN_TRANG_THAI[z.status]}
                    </span>
                  </span>

                  <span className="nq-qvzone__loai">{z.kind}</span>

                  <span className="nq-qvzone__tai">
                    <span className="nq-qvzone__tai-num">
                      {formatSo(z.load)}
                      {z.threshold !== null ? (
                        <span className="nq-qvzone__tai-nguong">
                          /{formatSo(z.threshold)}
                        </span>
                      ) : null}
                    </span>
                    <span className="nq-qvzone__tai-label">đơn đang xử lý</span>
                  </span>

                  <ThanhTai load={z.load} threshold={z.threshold} />

                  <span className="nq-qvzone__meta">
                    <span className="nq-qvzone__meta-item">
                      <Icon name="clock" size={12} />
                      {z.queue !== null
                        ? `${z.queue} đơn chờ`
                        : thieu
                          ? KHONG_CO_DU_LIEU
                          : "Không có hàng chờ"}
                    </span>
                    <span className="nq-qvzone__meta-item">
                      <Icon name="users" size={12} />
                      {z.assignedStaff !== null
                        ? `${z.assignedStaff} nhân sự`
                        : KHONG_CO_DU_LIEU}
                    </span>
                  </span>

                  {z.assignedNames.length > 0 ? (
                    <span className="nq-qvzone__names">{z.assignedNames.join(", ")}</span>
                  ) : null}

                  {z.alerts.length > 0 ? (
                    <span className="nq-qvzone__alert">{z.alerts[0].message}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {coCanhBao ? (
        <p className="nq-qvmap__foot">
          <Icon name="warn" size={13} />
          Có khu vực vượt ngưỡng tải — xem mục “Cần xử lý ngay”.
        </p>
      ) : null}
    </Card>
  );
}
