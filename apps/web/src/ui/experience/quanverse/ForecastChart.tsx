"use client";

/**
 * ForecastChart — nhu cầu/hàng đợi theo GIỜ, từ `/quanverse/forecast`.
 *
 * Thanh SVG thuần (không thêm thư viện); mọi số đọc từ API. Chưa có lịch sử →
 * hiện nhãn "chưa đủ dữ liệu" thay vì vẽ đường giả.
 */

import { ExpEmpty } from "../exp-kit";

export interface ForecastPoint {
  gio: number;
  nhu_cau: number;
  hang_doi_du_bao: number;
}

export interface ForecastPayload {
  co_du_lieu: boolean;
  so_ngay_du_lieu: number;
  series: ForecastPoint[];
  giao_dich_nhat: number[];
  nguon: string;
}

export default function ForecastChart({ data }: { data: ForecastPayload | null }) {
  if (!data) return <ExpEmpty icon="info" title="Đang tính dự báo…" hint="" />;
  if (!data.co_du_lieu || data.series.length === 0) {
    return (
      <ExpEmpty
        icon="info"
        title="Chưa đủ dữ liệu để dự báo"
        hint="Dự báo tính từ lịch sử đơn quầy. Ghi vài đơn để đường nhu cầu tự hiện."
      />
    );
  }
  const max = Math.max(1, ...data.series.map((s) => s.nhu_cau));
  const w = 100;
  const h = 100;
  const stepX = w / Math.max(1, data.series.length - 1);
  const points = data.series
    .map((s, i) => `${(i * stepX).toFixed(2)},${(h - (s.nhu_cau / max) * h).toFixed(2)}`)
    .join(" ");
  const diemNhat = new Set(data.giao_dich_nhat);

  return (
    <div className="nq-forecast">
      <div className="nq-forecast__chart" role="img" aria-label="Nhu cầu theo giờ">
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="nq-forecast__svg">
          <polyline points={points} className="nq-forecast__line" vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
      <ul className="nq-forecast__axis" aria-hidden="true">
        {data.series.map((s) => (
          <li
            key={s.gio}
            className={`nq-forecast__tick${diemNhat.has(s.gio) ? " is-peak" : ""}`}
            title={`${s.gio}h · nhu cầu ${s.nhu_cau} · chờ ${s.hang_doi_du_bao}`}
          >
            <span className="nq-forecast__gio">{s.gio}h</span>
          </li>
        ))}
      </ul>
      <p className="nq-forecast__meta">
        {data.so_ngay_du_lieu} ngày dữ liệu
        {data.giao_dich_nhat.length > 0
          ? ` · cao điểm ${data.giao_dich_nhat.map((g) => `${g}h`).join(", ")}`
          : ""}
      </p>
    </div>
  );
}
