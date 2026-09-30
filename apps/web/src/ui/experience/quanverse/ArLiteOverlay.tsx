"use client";

/**
 * ArLiteOverlay — AR mức nhẹ: mã QR + neo chọn tay, không nhận diện khuôn mặt.
 *
 * Bản trước in thẳng mã nội bộ `map_or_qr_text` ra UI — vi phạm quy tắc công bố
 * của dự án (mã trạng thái phải qua bảng nhãn). Bản này: mã vẫn còn nhưng nằm
 * trong `data-fallback` cho kiểm thử, người dùng đọc câu tiếng Việt; đồng thời
 * có khung xem trước lớp phủ và các neo mẫu bấm được, thay vì bắt gõ tay.
 *
 * Cam kết quyền riêng tư giữ nguyên và được nói ngay trên đầu khối.
 */

import { useState } from "react";
import { ApiError } from "../../../lib/api";
import { viError } from "../../../lib/present";
import { Icon } from "../../icons";
import { arFallbackLabel } from "../exp-present";

/** Neo mẫu theo thiết bị thật trong quán — bấm là điền, khỏi gõ. */
const SAMPLE_ANCHORS = ["blender-02", "espresso-machine-01", "window_table"];

interface ArResult {
  anchor_target: string;
  fallback: string;
}

const COPY = { start: { doing: "mở lớp phủ AR cho neo này" } } as const;

export default function ArLiteOverlay() {
  const [qr, setQr] = useState("");
  const [result, setResult] = useState<ArResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const token =
    typeof window !== "undefined" &&
    (window.sessionStorage.getItem("nq_token") ||
      window.localStorage.getItem("nq_token"));
  const tokenStr = typeof token === "string" ? token : "";

  async function start() {
    if (!qr.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${base}/api/v1/experience/quanverse/ar-session`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tokenStr ? { Authorization: `Bearer ${tokenStr}` } : {}),
        },
        body: JSON.stringify({ qr: qr.trim() }),
      });
      if (!res.ok) throw new ApiError(res.status);
      setResult((await res.json()) as ArResult);
    } catch (e) {
      // Máy chủ từ chối (mã sai, mất mạng) → nói thẳng, KHÔNG hiện lớp phủ
      // giả. Bản trước bắt mọi lỗi rồi vẫn vẽ "Đã gắn neo X" — người dùng
      // tưởng neo hợp lệ trong khi máy chủ chưa hề xác nhận.
      setResult(null);
      setError(viError(e, COPY.start));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="nq-ar" aria-label="AR-lite">
      <div className="nq-exp-section__head">
        <Icon name="cube" size={16} />
        <h3 className="nq-exp-section__title">AR-lite</h3>
        <span className="nq-exp-section__spacer" />
        <span className="nq-rolechip">
          <Icon name="qr" size={13} />
          Chỉ QR + neo chọn tay
        </span>
      </div>

      <p className="nq-ar__note">
        Không nhận diện khuôn mặt, không quét SLAM. Bạn tự chọn neo — hệ thống chỉ hiện lớp phủ theo neo đó.
      </p>

      <div className="nq-ar__samples" role="group" aria-label="Neo mẫu">
        {SAMPLE_ANCHORS.map((a) => (
          <button
            key={a}
            type="button"
            className={`nq-anchorchip${qr === a ? " is-on" : ""}`}
            onClick={() => setQr(a)}
          >
            <Icon name="qr" size={13} />
            {a}
          </button>
        ))}
      </div>

      <div className="nq-ar__row">
        <input
          type="text"
          value={qr}
          data-testid="ar-qr"
          placeholder="vd: blender-02"
          onChange={(e) => setQr(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") start();
          }}
        />
        <button
          type="button"
          className="nq-btn-compact nq-modebtn"
          data-testid="ar-start"
          disabled={busy || !qr.trim()}
          onClick={start}
        >
          <Icon name="play" size={14} />
          {busy ? "Đang mở…" : "Mở lớp phủ"}
        </button>
      </div>

      {error ? (
        <div className="nq-alert nq-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {result ? (
        <div
          className="nq-ar__stage"
          data-testid="ar-result"
          data-fallback={result.fallback}
          data-anchor={result.anchor_target}
        >
          {/* Khung xem trước: thước ngắm đặt trên neo, không phải camera thật. */}
          <div className="nq-ar__viewport" aria-hidden="true">
            <span className="nq-ar__crosshair" />
            <span className="nq-ar__anchorbox" />
            <span className="nq-ar__anchorlabel">{result.anchor_target}</span>
          </div>
          <div className="nq-ar__readout">
            <span className="nq-ar__badge">
              <Icon name="check" size={13} />
              Đã gắn neo {result.anchor_target}
            </span>
            <p className="nq-ar__fallback">
              <Icon name="map" size={14} />
              Dự phòng khi thiết bị không mở được camera: {arFallbackLabel(result.fallback)}.
            </p>
          </div>
        </div>
      ) : (
        <p className="nq-ar__prompt">
          <Icon name="info" size={14} /> Chọn một neo mẫu hoặc gõ mã trên thiết bị để mở lớp phủ.
        </p>
      )}
    </section>
  );
}