"use client";

/**
 * AI FORECAST — khối thời tiết hôm nay trên /hom-nay.
 *
 * Một section một việc: vị trí quán · thời tiết hiện tại · timeline giờ ·
 * ảnh hưởng vận hành → link /quanverse. Không vẽ dữ liệu giả khi thiếu địa chỉ.
 */

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../../lib/api";
import { beat } from "../../lib/motion";
import { viError } from "../../lib/present";
import { Icon, type IconName } from "../icons";
import { BtnLink } from "../kit";

export type WeatherNhom = "nang" | "may" | "mua" | "mua_to" | "bao" | "suong";

export type ThoiTietHomNay = {
  co_du_lieu: boolean;
  ly_do?: string;
  can_cau_hinh?: boolean;
  vi_tri?: {
    thanh_pho?: string;
    tinh?: string;
    lat?: number;
    lon?: number;
    nguon?: string;
  } | null;
  hien_tai?: {
    nhiet_do?: number | null;
    nhom?: WeatherNhom | string;
    mo_ta?: string;
    mua_mm?: number | null;
    do_am?: number | null;
  } | null;
  theo_gio?: {
    gio: number;
    nhiet_do?: number | null;
    nhom?: WeatherNhom | string;
    mo_ta?: string;
    mua_mm?: number | null;
  }[];
  anh_huong_quan?: {
    tom_tat?: string;
    yeu_to?: string[];
    de_xuat_mode?: string;
    de_xuat_mode_label?: string;
    de_xuat_mode_href?: string;
    tone?: string;
    he_so_ngoai_troi?: number;
  } | null;
  cap_nhat_luc?: string;
  nguon?: string;
  ngay?: string;
  tu_cache?: boolean;
};

function iconForNhom(nhom: string | undefined): IconName {
  switch (nhom) {
    case "nang":
      return "sun";
    case "may":
      return "cloud";
    case "mua":
      return "cloud-rain";
    case "mua_to":
      return "cloud-rain";
    case "bao":
      return "storm";
    case "suong":
      return "fog";
    default:
      return "cloud-sun";
  }
}

function viTriLabel(v: ThoiTietHomNay["vi_tri"]): string {
  if (!v) return "";
  const parts = [v.thanh_pho, v.tinh].map((x) => (x || "").trim()).filter(Boolean);
  return parts.join(", ");
}

function formatCapNhat(iso: string | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Ho_Chi_Minh",
    });
  } catch {
    return "";
  }
}

export function AiForecastBlock() {
  const [data, setData] = useState<ThoiTietHomNay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reduced = useReducedMotion() ?? false;

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    apiGet<ThoiTietHomNay>("/api/v1/thoi-tiet/hom-nay")
      .then(setData)
      .catch((e) => setError(viError(e, { doing: "đọc được dự báo thời tiết" })))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !data) {
    return (
      <section className="nq-aiforecast nq-aiforecast--loading" data-testid="ai-forecast" aria-busy="true">
        <p className="nq-eyebrow">AI Forecast</p>
        <h2 className="nq-block-title">Thời tiết hôm nay</h2>
        <p className="nq-aiforecast__hint">Đang đọc dự báo theo địa chỉ quán…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="nq-aiforecast nq-aiforecast--empty" data-testid="ai-forecast">
        <p className="nq-eyebrow">AI Forecast</p>
        <h2 className="nq-block-title">Thời tiết hôm nay</h2>
        <p className="nq-aiforecast__hint">{error}</p>
        <button type="button" className="nq-aiforecast__retry" onClick={load}>
          Thử lại
        </button>
      </section>
    );
  }

  if (!data?.co_du_lieu) {
    return (
      <section className="nq-aiforecast nq-aiforecast--empty" data-testid="ai-forecast">
        <p className="nq-eyebrow">AI Forecast</p>
        <h2 className="nq-block-title">Thời tiết hôm nay</h2>
        <p className="nq-aiforecast__hint">
          {data?.ly_do || "Chưa có dữ liệu thời tiết cho quán."}
        </p>
        {data?.can_cau_hinh ? (
          <BtnLink href="/cau-hinh-quan" variant="ghost">
            Cấu hình địa chỉ quán
          </BtnLink>
        ) : null}
      </section>
    );
  }

  const hienTai = data.hien_tai;
  const nhom = String(hienTai?.nhom || "may");
  const icon = iconForNhom(nhom);
  const viTri = viTriLabel(data.vi_tri);
  const capNhat = formatCapNhat(data.cap_nhat_luc);
  const impact = data.anh_huong_quan;
  const hours = data.theo_gio ?? [];
  const nowHour = new Date().toLocaleString("en-US", {
    hour: "numeric",
    hour12: false,
    timeZone: "Asia/Ho_Chi_Minh",
  });
  const currentHour = Number.parseInt(nowHour, 10);

  return (
    <section
      className={`nq-aiforecast nq-aiforecast--${nhom}`}
      data-testid="ai-forecast"
      data-nhom={nhom}
    >
      <div className="nq-aiforecast__head">
        <div>
          <p className="nq-eyebrow">AI Forecast</p>
          <h2 className="nq-block-title">Thời tiết hôm nay</h2>
          {viTri ? (
            <p className="nq-aiforecast__loc" data-testid="ai-forecast-location">
              <Icon name="location" size={14} />
              <span>{viTri}</span>
              {capNhat ? <span className="nq-aiforecast__meta">· cập nhật {capNhat}</span> : null}
            </p>
          ) : null}
        </div>
        <motion.div
          className="nq-aiforecast__now"
          data-testid="ai-forecast-now"
          initial={reduced ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={beat("settle")}
        >
          <span
            className={`nq-aiforecast__icon${reduced ? "" : " nq-aiforecast__icon--live"}`}
            aria-hidden="true"
            data-nhom={nhom}
          >
            <Icon name={icon} size={36} />
          </span>
          <div>
            <strong className="nq-aiforecast__temp">
              {typeof hienTai?.nhiet_do === "number" ? `${Math.round(hienTai.nhiet_do)}°` : "—"}
            </strong>
            <span className="nq-aiforecast__desc">{hienTai?.mo_ta || "—"}</span>
          </div>
        </motion.div>
      </div>

      {hours.length > 0 ? (
        <div className="nq-aiforecast__hours" data-testid="ai-forecast-hours" role="list">
          {hours.map((h, i) => {
            const active = h.gio === currentHour;
            return (
              <motion.div
                key={h.gio}
                className={`nq-aiforecast__hour${active ? " is-now" : ""}`}
                role="listitem"
                initial={reduced ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={reduced ? undefined : beat("settle", Math.min(i * 0.03, 0.35))}
              >
                <span className="nq-aiforecast__hour-label">{String(h.gio).padStart(2, "0")}h</span>
                <Icon name={iconForNhom(String(h.nhom))} size={16} />
                <span className="nq-aiforecast__hour-temp">
                  {typeof h.nhiet_do === "number" ? `${Math.round(h.nhiet_do)}°` : "—"}
                </span>
              </motion.div>
            );
          })}
        </div>
      ) : null}

      {impact?.tom_tat ? (
        <div className="nq-aiforecast__impact" data-testid="ai-forecast-impact">
          <p className="nq-aiforecast__impact-title">Ảnh hưởng quán</p>
          <p className="nq-aiforecast__impact-sum">{impact.tom_tat}</p>
          {impact.yeu_to && impact.yeu_to.length > 0 ? (
            <ul className="nq-aiforecast__impact-list">
              {impact.yeu_to.slice(0, 3).map((y) => (
                <li key={y}>{y}</li>
              ))}
            </ul>
          ) : null}
          <div className="nq-aiforecast__cta">
            <Link href="/quanverse" className="nq-aiforecast__link">
              Xem hiện trạng Quánverse
              <Icon name="arrow-right" size={14} />
            </Link>
            {impact.de_xuat_mode ? (
              <span className="nq-aiforecast__mode-chip" data-testid="ai-forecast-mode-hint">
                Gợi ý: chế độ {impact.de_xuat_mode_label || impact.de_xuat_mode} (cần duyệt)
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
