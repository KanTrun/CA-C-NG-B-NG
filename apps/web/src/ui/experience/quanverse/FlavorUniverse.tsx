"use client";

/**
 * FlavorUniverse — khách nói khẩu vị, hệ thống gợi ý kèm lý do.
 *
 * Bản trước là form thô: select + hai checkbox + ô text, kết quả chỉ là chữ.
 * Bản này dựng ba thứ mà người dùng thật sự cần thấy:
 *   1. Núm chọn độ ngọt dạng thanh trượt ba nấc (nhìn ra mức đang chọn),
 *   2. Chip khẩu vị bật/tắt được (có trạng thái thị giác, không chỉ dấu tick),
 *   3. Kết quả có điểm số trực quan + lý do, và một câu giải thích không tự bịa.
 *
 * Ô "Dị ứng" giữ nguyên là input text: đây là khai báo y tế, không được đoán
 * hộ, và dự án yêu cầu khai báo tường minh.
 */

import { useState } from "react";
import { ApiError } from "../../../lib/api";
import { viError } from "../../../lib/present";
import { Icon } from "../../icons";
import { ExpEmpty } from "../exp-kit";

interface Rec {
  mon_id: string;
  ten: string;
  score: number;
  reasons: string[];
}

const COPY = { recommend: { doing: "gợi ý món theo khẩu vị" } } as const;

const SWEETNESS = [
  { value: "it", label: "Ít ngọt", hint: "Nhẹ, hợp buổi sáng" },
  { value: "vua", label: "Vừa", hint: "Cân bằng" },
  { value: "ngot", label: "Ngọt", hint: "Đậm vị" },
];

export default function FlavorUniverse() {
  const [do_ngot, setDoNgot] = useState("vua");
  const [co_sua, setCoSua] = useState(true);
  const [huong_tra, setHuongTra] = useState(false);
  const [allergy, setAllergy] = useState("");
  const [result, setResult] = useState<Rec[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const token =
    typeof window !== "undefined" &&
    (window.sessionStorage.getItem("nq_token") ||
      window.localStorage.getItem("nq_token"));
  const tokenStr = typeof token === "string" ? token : "";

  async function recommend() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${base}/api/v1/experience/quanverse/flavor/recommend`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tokenStr ? { Authorization: `Bearer ${tokenStr}` } : {}),
        },
        body: JSON.stringify({
          do_ngot,
          co_sua,
          huong_tra,
          dietary_allergy: allergy.trim() ? [allergy.trim()] : [],
        }),
      });
      if (!res.ok) throw new ApiError(res.status);
      const body = (await res.json()) as { recommendations: Rec[] };
      setResult(body.recommendations);
    } catch (e) {
      // Lỗi kỹ thuật KHÔNG được in ra UI: `api_500` không nói gì với người
      // dùng. `viError` dịch mã HTTP thành câu tiếng Việt + việc cần làm.
      setError(viError(e, COPY.recommend));
    } finally {
      setBusy(false);
    }
  }

  // Điểm cao nhất để chuẩn hoá thanh điểm — thanh dài bằng tỉ lệ với món dẫn đầu.
  const topScore = result?.length ? Math.max(...result.map((r) => r.score)) : 1;

  return (
    <section className="nq-flavor" aria-label="Flavor Universe">
      <div className="nq-exp-section__head">
        <Icon name="coffee" size={16} />
        <h3 className="nq-exp-section__title">Flavor Universe</h3>
      </div>
      <p className="nq-flavor__note">
        Nói khẩu vị của bạn — gợi ý luôn kèm lý do, không có hộp đen.
      </p>

      <fieldset className="nq-flavor__fieldset">
        <legend className="nq-flavor__legend">Độ ngọt</legend>
        <div className="nq-stepper" role="radiogroup" aria-label="Độ ngọt">
          {SWEETNESS.map((s) => (
            <button
              key={s.value}
              type="button"
              role="radio"
              aria-checked={do_ngot === s.value}
              className={`nq-stepper__opt${do_ngot === s.value ? " is-on" : ""}`}
              data-testid={`flavor-ngot-${s.value}`}
              onClick={() => setDoNgot(s.value)}
            >
              <span className="nq-stepper__label">{s.label}</span>
              <span className="nq-stepper__hint">{s.hint}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <div className="nq-flavor__toggles">
        <label className="nq-tastechip">
          <input
            type="checkbox"
            checked={co_sua}
            data-testid="flavor-sua"
            onChange={(e) => setCoSua(e.target.checked)}
          />
          <span className={`nq-tastechip__face${co_sua ? " is-on" : ""}`}>
            <Icon name="coffee" size={14} />
            Có sữa
          </span>
        </label>
        <label className="nq-tastechip">
          <input
            type="checkbox"
            checked={huong_tra}
            data-testid="flavor-tra"
            onChange={(e) => setHuongTra(e.target.checked)}
          />
          <span className={`nq-tastechip__face${huong_tra ? " is-on" : ""}`}>
            <Icon name="coffee" size={14} />
            Thơm trà
          </span>
        </label>
      </div>

      <label className="nq-flavor__allergy">
        Dị ứng (khai báo tường minh, không tự đoán)
        <input
          type="text"
          value={allergy}
          data-testid="flavor-allergy"
          placeholder="vd: sữa"
          onChange={(e) => setAllergy(e.target.value)}
        />
      </label>

      <button
        type="button"
        className="nq-btn nq-btn-primary nq-btn-block"
        data-testid="flavor-go"
        disabled={busy}
        onClick={recommend}
      >
        <Icon name="bot" size={16} />
        {busy ? "Đang tìm món…" : "Gợi ý cho tôi"}
      </button>

      {error ? <div className="nq-alert nq-alert--error">{error}</div> : null}

      {result === null ? (
        <p className="nq-flavor__prompt">
          <Icon name="info" size={14} /> Chọn khẩu vị rồi bấm gợi ý — danh sách món kèm lý do sẽ hiện ở đây.
        </p>
      ) : result.length === 0 ? (
        <ExpEmpty
          icon="coffee"
          title="Chưa có món nào khớp khẩu vị này"
          hint="Thử bỏ bớt một điều kiện, hoặc xoá khai báo dị ứng nếu bạn gõ nhầm."
        />
      ) : (
        <ul className="nq-flavor__results" data-testid="flavor-results">
          {result.map((r, i) => (
            <li key={r.mon_id} className="nq-flavor__result" style={{ ["--nq-fv-i" as string]: i }}>
              <span className="nq-flavor__rank" aria-hidden="true">
                {i + 1}
              </span>
              <span className="nq-flavor__text">
                <span className="nq-flavor__name">{r.ten}</span>
                <span className="nq-flavor__meter" aria-hidden="true">
                  <span
                    className="nq-flavor__meter-fill"
                    style={{ width: `${Math.max(8, Math.round((r.score / (topScore || 1)) * 100))}%` }}
                  />
                </span>
                <ul className="nq-flavor__reasons">
                  {r.reasons.map((reason, ri) => (
                    <li key={ri}>
                      <Icon name="check" size={12} />
                      {reason}
                    </li>
                  ))}
                </ul>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}