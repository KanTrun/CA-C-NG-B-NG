"use client";

/**
 * AI FORECAST — khối thời tiết hôm nay trên /hom-nay.
 *
 * Vị trí: GPS quán (ưu tiên) hoặc một ô địa chỉ — không bắt điền tách tỉnh/thành.
 * Một section một việc: vị trí · thời tiết hiện tại · timeline giờ · ảnh hưởng
 * vận hành → link /quanverse. Không vẽ dữ liệu giả khi thiếu vị trí.
 */

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { beat } from "../../lib/motion";
import { viError } from "../../lib/present";
import { isManager } from "../../lib/session";
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

type StoreProfile = {
  ten_quan: string;
  dia_chi: string;
  tinh: string;
  thanh_pho: string;
  lat: number | null;
  lon: number | null;
  hotline: string;
  gio_mo_cua: string;
  wifi_ssid: string;
  wifi_pass: string;
  mo_ta: string;
  chinh_sach_dat_ban: string;
  huong_dan_agent: string;
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
  if (parts.length) return parts.join(", ");
  if (typeof v.lat === "number" && typeof v.lon === "number") {
    return `${v.lat.toFixed(3)}, ${v.lon.toFixed(3)}`;
  }
  return "";
}

function nguonLabel(nguon: string | undefined): string {
  if (nguon === "gps") return "GPS";
  if (nguon === "dia_chi") return "Địa chỉ";
  if (nguon === "tinh_thanh") return "Tỉnh/thành";
  return "";
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

async function luuViTriProfile(patch: Partial<StoreProfile>): Promise<void> {
  const current = await apiGet<StoreProfile>("/api/v1/store/profile");
  await apiSend(
    "/api/v1/store/profile",
    {
      ten_quan: current.ten_quan ?? "",
      dia_chi: current.dia_chi ?? "",
      tinh: current.tinh ?? "",
      thanh_pho: current.thanh_pho ?? "",
      lat: current.lat ?? null,
      lon: current.lon ?? null,
      hotline: current.hotline ?? "",
      gio_mo_cua: current.gio_mo_cua ?? "",
      wifi_ssid: current.wifi_ssid ?? "",
      wifi_pass: current.wifi_pass ?? "",
      mo_ta: current.mo_ta ?? "",
      chinh_sach_dat_ban: current.chinh_sach_dat_ban ?? "",
      huong_dan_agent: current.huong_dan_agent ?? "",
      ...patch,
    },
    "PUT",
  );
}

export function AiForecastBlock() {
  const [data, setData] = useState<ThoiTietHomNay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [gpsBusy, setGpsBusy] = useState(false);
  const [addrBusy, setAddrBusy] = useState(false);
  const [showAddr, setShowAddr] = useState(false);
  const [diaChi, setDiaChi] = useState("");
  const [locMsg, setLocMsg] = useState<string | null>(null);
  const [manager, setManager] = useState(false);
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
    setManager(isManager());
    load();
  }, [load]);

  const layGps = useCallback(() => {
    if (!navigator.geolocation) {
      setLocMsg("Trình duyệt không cho lấy vị trí. Nhập một địa chỉ bên dưới.");
      setShowAddr(true);
      return;
    }
    setGpsBusy(true);
    setLocMsg(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        void (async () => {
          try {
            await luuViTriProfile({
              lat: Number(pos.coords.latitude.toFixed(6)),
              lon: Number(pos.coords.longitude.toFixed(6)),
              // Xoá nhãn tỉnh/thành cũ — server reverse-geocode từ GPS.
              tinh: "",
              thanh_pho: "",
            });
            setLocMsg("Đã lưu vị trí GPS. Đang đọc dự báo…");
            load();
          } catch (e) {
            setLocMsg(viError(e, { doing: "lưu được vị trí quán" }));
          } finally {
            setGpsBusy(false);
          }
        })();
      },
      () => {
        setGpsBusy(false);
        setLocMsg("Không lấy được vị trí. Nhập một địa chỉ bên dưới.");
        setShowAddr(true);
      },
      { timeout: 10000 },
    );
  }, [load]);

  const luuDiaChi = useCallback(() => {
    const text = diaChi.trim();
    if (!text) {
      setLocMsg("Nhập một địa chỉ quán (ví dụ: 45 Nguyễn Huệ, Quận 1, TP. HCM).");
      return;
    }
    setAddrBusy(true);
    setLocMsg(null);
    void (async () => {
      try {
        await luuViTriProfile({ dia_chi: text });
        setLocMsg("Đã lưu địa chỉ. Đang đọc dự báo…");
        load();
      } catch (e) {
        setLocMsg(viError(e, { doing: "lưu được địa chỉ quán" }));
      } finally {
        setAddrBusy(false);
      }
    })();
  }, [diaChi, load]);

  if (loading && !data) {
    return (
      <section className="nq-aiforecast nq-aiforecast--loading" data-testid="ai-forecast" aria-busy="true">
        <p className="nq-eyebrow">AI Forecast</p>
        <h2 className="nq-block-title">Thời tiết hôm nay</h2>
        <p className="nq-aiforecast__hint">Đang đọc dự báo theo vị trí quán…</p>
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
        <p className="nq-aiforecast__hint" data-testid="ai-forecast-empty-hint">
          {data?.ly_do || "Chưa có dữ liệu thời tiết cho quán."}
        </p>
        {data?.can_cau_hinh && manager ? (
          <div className="nq-aiforecast__setup" data-testid="ai-forecast-setup">
            <button
              type="button"
              className="nq-aiforecast__retry"
              data-testid="ai-forecast-gps"
              disabled={gpsBusy}
              onClick={layGps}
            >
              {gpsBusy ? "Đang lấy vị trí…" : "Lấy vị trí hiện tại"}
            </button>
            {!showAddr ? (
              <button
                type="button"
                className="nq-aiforecast__linkbtn"
                data-testid="ai-forecast-show-addr"
                onClick={() => setShowAddr(true)}
              >
                Hoặc nhập một địa chỉ
              </button>
            ) : (
              <div className="nq-aiforecast__addr" data-testid="ai-forecast-addr-form">
                <label className="nq-aiforecast__addr-label" htmlFor="ai-forecast-dia-chi">
                  Địa chỉ quán
                </label>
                <input
                  id="ai-forecast-dia-chi"
                  className="nq-aiforecast__addr-input"
                  data-testid="ai-forecast-dia-chi"
                  value={diaChi}
                  onChange={(e) => setDiaChi(e.target.value)}
                  placeholder="VD: 45 Nguyễn Huệ, Quận 1, TP. HCM"
                />
                <button
                  type="button"
                  className="nq-aiforecast__retry"
                  data-testid="ai-forecast-save-addr"
                  disabled={addrBusy}
                  onClick={luuDiaChi}
                >
                  {addrBusy ? "Đang lưu…" : "Lưu địa chỉ & xem dự báo"}
                </button>
              </div>
            )}
            {locMsg ? <p className="nq-aiforecast__loc-msg">{locMsg}</p> : null}
          </div>
        ) : data?.can_cau_hinh ? (
          <BtnLink href="/cau-hinh-quan" variant="ghost">
            Cấu hình vị trí quán
          </BtnLink>
        ) : null}
      </section>
    );
  }

  const hienTai = data.hien_tai;
  const nhom = String(hienTai?.nhom || "may");
  const icon = iconForNhom(nhom);
  const viTri = viTriLabel(data.vi_tri);
  const nguon = nguonLabel(data.vi_tri?.nguon);
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
              {nguon ? <span className="nq-aiforecast__meta">· {nguon}</span> : null}
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
