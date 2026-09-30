"use client";

/**
 * PreferenceConsent — sở thích khách: đề xuất → đồng ý → lưu → xoá.
 *
 * Bản trước là ngõ cụt: chỉ có nút "Không đồng ý, xoá đi", không có nhánh đồng
 * ý, và máy chủ luôn trả `stored: false` nên dù khách muốn lưu cũng không có
 * đường nào. Bản này nối đủ vòng đời thật, và liệt kê sở thích đã lưu để khách
 * thấy đúng thứ hệ thống đang giữ về mình — quyền riêng tư phải nhìn thấy được,
 * không chỉ được hứa.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../../lib/api";
import { viError } from "../../../lib/present";
import { Icon } from "../../icons";
import { ExpEmpty } from "../exp-kit";

type Stage = "idle" | "awaiting_consent";

interface StoredPreference {
  preference_id: string;
  content: string;
  consent_status: string;
  created_at?: string;
}

const COPY = {
  propose: { doing: "ghi nhận sở thích này" },
  list: { doing: "đọc được sở thích đã lưu" },
  consent: { doing: "lưu sở thích này" },
  remove: { doing: "xoá sở thích này" },
} as const;

export default function PreferenceConsent() {
  const [content, setContent] = useState("");
  const [proposal, setProposal] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** Lỗi ĐỌC danh sách — khác `error` (lỗi thao tác), và phải hiện riêng. */
  const [listError, setListError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stored, setStored] = useState<StoredPreference[]>([]);

  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const token =
    typeof window !== "undefined" &&
    (window.sessionStorage.getItem("nq_token") ||
      window.localStorage.getItem("nq_token"));
  const tokenStr = typeof token === "string" ? token : "";

  const authHeaders = useCallback(
    (json = false): Record<string, string> => ({
      ...(json ? { "Content-Type": "application/json" } : {}),
      ...(tokenStr ? { Authorization: `Bearer ${tokenStr}` } : {}),
    }),
    [tokenStr],
  );

  const loadStored = useCallback(async () => {
    setListError(null);
    try {
      const res = await fetch(`${base}/api/v1/experience/quanverse/preferences`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new ApiError(res.status);
      const body = (await res.json()) as { preferences: StoredPreference[] };
      // Chỉ hiện bản đã đồng thuận; bản đang chờ nằm ở khối đồng thuận riêng.
      setStored(
        (body.preferences ?? []).filter((p) => p.consent_status === "granted"),
      );
    } catch (e) {
      // Không chặn luồng gửi mới vì lỗi đọc danh sách — NHƯNG phải nói rõ là
      // chưa đọc được. Bản trước `setStored([])` rồi hiện "Chưa lưu sở thích
      // nào": người dùng tưởng hệ thống không giữ gì về mình, trong khi thật ra
      // máy chủ không trả lời được. Với dữ liệu cá nhân, im lặng thành "sạch"
      // là câu trả lời sai có hại — họ có thể thôi quan tâm tới việc thu hồi.
      setStored([]);
      setListError(viError(e, COPY.list));
    }
  }, [authHeaders, base]);

  useEffect(() => {
    void loadStored();
  }, [loadStored]);

  async function propose() {
    if (!content.trim()) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const res = await fetch(`${base}/api/v1/experience/quanverse/preferences/propose`, {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify({ content: content.trim() }),
      });
      if (!res.ok) throw new ApiError(res.status);
      const body = (await res.json()) as {
        preference_proposal_id: string;
        needs_consent: boolean;
      };
      setProposal(body.preference_proposal_id);
      setStage(body.needs_consent ? "awaiting_consent" : "idle");
      setNotice("Đã ghi nhận. Cần bạn đồng ý trước khi lưu vào hồ sơ.");
      setContent("");
    } catch (e) {
      setError(viError(e, COPY.propose));
    } finally {
      setBusy(false);
    }
  }

  /** Đồng ý lưu — nhánh mà bản trước hoàn toàn thiếu. */
  async function grant() {
    if (!proposal) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const res = await fetch(
        `${base}/api/v1/experience/quanverse/preferences/${proposal}/consent`,
        { method: "POST", headers: authHeaders(true), body: JSON.stringify({ grant: true }) },
      );
      if (!res.ok) throw new ApiError(res.status);
      setNotice("Đã lưu sở thích vào hồ sơ của bạn.");
      setProposal(null);
      setStage("idle");
      await loadStored();
    } catch (e) {
      setError(viError(e, COPY.consent));
    } finally {
      setBusy(false);
    }
  }

  async function remove(prefId: string) {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const res = await fetch(
        `${base}/api/v1/experience/quanverse/preferences/${prefId}`,
        { method: "DELETE", headers: authHeaders() },
      );
      if (!res.ok) throw new ApiError(res.status);
      setNotice("Đã xoá sở thích — thao tác có lưu vết kiểm toán.");
      setProposal(null);
      setStage("idle");
      await loadStored();
    } catch (e) {
      setError(viError(e, COPY.remove));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="nq-pref" aria-label="Sở thích khách">
      <div className="nq-exp-section__head">
        <Icon name="pin" size={16} />
        <h3 className="nq-exp-section__title">Sở thích khách</h3>
        <span className="nq-exp-section__spacer" />
        <span className={`nq-stagechip nq-stagechip--${stage}`}>
          {stage === "awaiting_consent" ? "Chờ đồng ý" : `${stored.length} đã lưu`}
        </span>
      </div>

      <p className="nq-pref__privacy">
        <Icon name="info" size={14} />
        Sở thích là dữ liệu cá nhân: chỉ nhân viên phục vụ ca của bạn thấy, và bạn xoá được bất cứ lúc nào.
      </p>

      {stage !== "awaiting_consent" ? (
        <div className="nq-pref__row">
          <input
            type="text"
            value={content}
            data-testid="pref-input"
            placeholder="vd: thích bàn cửa sổ yên tĩnh"
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") propose();
            }}
          />
          <button
            type="button"
            className="nq-btn-compact nq-modebtn"
            data-testid="pref-propose"
            disabled={busy || !content.trim()}
            onClick={propose}
          >
            Đề xuất
          </button>
        </div>
      ) : (
        <div className="nq-consentbox">
          <p>
            Bạn muốn lưu sở thích này cho các lần ghé sau? Không đồng ý thì hệ thống quên ngay.
          </p>
          <div className="nq-consentbox__actions">
            <button
              type="button"
              className="nq-btn-compact nq-modebtn"
              data-testid="pref-grant"
              disabled={busy}
              onClick={grant}
            >
              <Icon name="check" size={14} />
              Đồng ý lưu
            </button>
            <button
              type="button"
              className="nq-btn-compact nq-modebtn"
              data-testid="pref-delete"
              disabled={busy}
              onClick={() => proposal && remove(proposal)}
            >
              <Icon name="trash" size={14} />
              Không đồng ý, xoá đi
            </button>
            <span className="nq-consentbox__hint">
              Mặc định: không lưu nếu bạn không bấm gì.
            </span>
          </div>
        </div>
      )}

      {error ? (
        <div className="nq-alert nq-alert--error" role="alert">
          {error}
        </div>
      ) : null}
      {notice ? (
        <p className="nq-pref__notice" role="status">
          {notice}
        </p>
      ) : null}

      {/* Danh sách đã lưu: khách thấy đúng thứ hệ thống đang giữ về mình. */}
      <h4 className="nq-pref__subhead">Đang lưu về bạn</h4>
      {listError ? (
        // Chưa đọc được ≠ không có gì. Với dữ liệu cá nhân, hiện "Chưa lưu sở
        // thích nào" khi máy chủ không trả lời là nói sai — người dùng có thể
        // tưởng hệ thống không giữ gì và thôi quan tâm việc thu hồi.
        <div className="nq-alert nq-alert--warn" role="alert" data-testid="pref-list-error">
          {listError}
          <button type="button" className="nq-linkbtn" onClick={() => void loadStored()}>
            <Icon name="refresh" size={14} />
            Đọc lại
          </button>
        </div>
      ) : stored.length === 0 ? (
        <ExpEmpty
          icon="pin"
          title="Chưa lưu sở thích nào"
          hint="Sở thích chỉ được lưu sau khi bạn đồng ý, và bạn xoá được bất cứ lúc nào."
        />
      ) : (
        <ul className="nq-pref__list" data-testid="pref-stored">
          {stored.map((p) => (
            <li key={p.preference_id} className="nq-pref__item">
              <span className="nq-pref__content">{p.content}</span>
              <button
                type="button"
                className="nq-linkbtn"
                data-testid={`pref-remove-${p.preference_id}`}
                disabled={busy}
                onClick={() => remove(p.preference_id)}
              >
                <Icon name="trash" size={14} />
                Xoá
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}