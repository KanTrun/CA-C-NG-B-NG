"use client";

/**
 * StationBoard — tải + hàng chờ theo khu vực, TỪ DỮ LIỆU THẬT (`/quanverse/stations`).
 *
 * Không bịa số: khi chưa có đơn quầy, `co_du_lieu=false` và hiện nhãn "chưa có
 * dữ liệu" thay vì vẽ số giả. Cảnh báo (quá tải / chú ý) tính từ ngưỡng hiển thị.
 */

import { Icon } from "../../icons";
import { ExpEmpty } from "../exp-kit";

export interface Station {
  zone_id: string;
  ten: string;
  kind: string;
  tai: number;
  hang_cho: number;
  muc_day: number;
  canh_bao: "binh_thuong" | "chu_y" | "qua_tai";
}

export interface StationsPayload {
  co_du_lieu: boolean;
  gio: number;
  tuan_iso: string;
  stations: Station[];
  chi_so: {
    don_hom_nay: number;
    don_dang_xu_ly: number;
    don_da_xong: number;
    nhan_su_trong_ca: number;
    so_ca_phu_khung_gio: number;
  };
  nguon: string;
}

const CANH_BAO_NHAN: Record<Station["canh_bao"], string> = {
  binh_thuong: "Bình thường",
  chu_y: "Chú ý",
  qua_tai: "Quá tải",
};

export default function StationBoard({ data }: { data: StationsPayload | null }) {
  if (!data) {
    return <ExpEmpty icon="location" title="Đang tải tải khu vực…" hint="" />;
  }
  if (!data.co_du_lieu) {
    return (
      <ExpEmpty
        icon="location"
        title="Chưa có đơn quầy để tính tải"
        hint="Tải khu vực tính từ đơn thật. Ghi vài đơn ở /quay để bảng này tự chạy."
      />
    );
  }
  return (
    <div className="nq-stations">
      <ul className="nq-stations__grid" data-testid="quanverse-stations">
        {data.stations.map((s) => {
          const pct = Math.min(100, Math.round((s.tai / Math.max(1, s.muc_day)) * 100));
          return (
            <li
              key={s.zone_id}
              className={`nq-station nq-station--${s.canh_bao}`}
              data-zone={s.zone_id}
              data-canh-bao={s.canh_bao}
            >
              <div className="nq-station__head">
                <span className="nq-station__ten">{s.ten}</span>
                <span className={`nq-station__chip nq-station__chip--${s.canh_bao}`}>
                  <Icon name={s.canh_bao === "qua_tai" ? "warn" : "info"} size={12} />
                  {CANH_BAO_NHAN[s.canh_bao]}
                </span>
              </div>
              <div className="nq-station__bars">
                <div className="nq-station__bar" aria-hidden="true">
                  <span className="nq-station__fill" style={{ width: `${pct}%` }} />
                </div>
                <span className="nq-station__nums">
                  <strong>{s.tai}</strong>/{s.muc_day} đơn · chờ {s.hang_cho}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      <dl className="nq-stations__kpi">
        <div>
          <dt>Đơn hôm nay</dt>
          <dd>{data.chi_so.don_hom_nay}</dd>
        </div>
        <div>
          <dt>Đang xử lý</dt>
          <dd>{data.chi_so.don_dang_xu_ly}</dd>
        </div>
        <div>
          <dt>Đã xong</dt>
          <dd>{data.chi_so.don_da_xong}</dd>
        </div>
        <div>
          <dt>Nhân sự trong ca</dt>
          <dd>{data.chi_so.nhan_su_trong_ca}</dd>
        </div>
        <div>
          <dt>Ca phủ giờ {String(data.gio).padStart(2, "0")}h</dt>
          <dd>{data.chi_so.so_ca_phu_khung_gio}</dd>
        </div>
      </dl>
    </div>
  );
}
