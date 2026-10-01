"use client";

/**
 * QUÁNVERSE — G. AI COPILOT + Ask grounded.
 *
 * Brief tĩnh luôn hiện. Ô hỏi gọi repository.askQuestion — câu trả lời kèm
 * citations / unsupportedClaims / grounded. AI không ghi DB.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "../../../icons";
import {
  CHUA_CO_DU_LIEU,
  type QuanverseAskResult,
  type QuanverseCopilot,
  type QuanverseProvenance,
} from "../quanverse-contract";
import { Card, CardHead, NguonChip } from "./kit";

export default function AiCopilot({
  copilot,
  provenance,
  askResult,
  askBusy,
  askPrefill,
  suggestions,
  onAsk,
  onClearAsk,
  onFocusZone,
}: {
  copilot: QuanverseCopilot | null;
  provenance: readonly QuanverseProvenance[];
  askResult: QuanverseAskResult | null;
  askBusy: boolean;
  askPrefill: string;
  suggestions: readonly string[];
  onAsk: (question: string) => void;
  onClearAsk: () => void;
  onFocusZone?: (zoneId: string) => void;
}) {
  const [draft, setDraft] = useState("");
  useEffect(() => {
    if (askPrefill) setDraft(askPrefill);
  }, [askPrefill]);
  const thieuNguon = provenance.filter((p) => !p.ok).map((p) => p.label);
  const question = draft.trim();

  return (
    <Card className="nq-qvai" label="AI Copilot" testId="quanverse-copilot">
      <CardHead
        title="AI Copilot"
        icon="info"
        trailing={
          copilot || askResult ? (
            <span
              className={`nq-qvai__grounded${
                (askResult?.grounded ?? copilot?.grounded) ? " is-grounded" : ""
              }`}
              data-testid="copilot-grounded"
            >
              {(askResult?.grounded ?? copilot?.grounded)
                ? "Có căn cứ"
                : "Chưa có căn cứ"}
            </span>
          ) : null
        }
      />

      {!copilot && !askResult ? (
        <p className="nq-qv-trong" data-testid="copilot-empty">
          <span className="nq-qv-trong__text">{CHUA_CO_DU_LIEU}</span>
          <span className="nq-qv-trong__hint">
            Chưa lấy được bản tóm tắt cho trạng thái hiện tại.
          </span>
        </p>
      ) : (
        <>
          <p className="nq-qvai__headline" data-testid="copilot-headline">
            {askResult?.answer ?? copilot?.headline}
          </p>

          {askResult ? (
            <div className="nq-qvai__ask-meta" data-testid="copilot-ask-result">
              <span className="nq-qvai__ask-q">Hỏi: {askResult.question}</span>
              <button
                type="button"
                className="nq-linkbtn"
                data-testid="copilot-clear-ask"
                onClick={onClearAsk}
              >
                Xem lại tóm tắt
              </button>
            </div>
          ) : null}

          {!askResult && copilot && copilot.reasons.length > 0 ? (
            <div className="nq-qvai__section">
              <h3 className="nq-qvai__sub">Lý do</h3>
              <ul className="nq-qvai__reasons" data-testid="copilot-reasons">
                {copilot.reasons.map((r, i) => (
                  <li key={`${i}-${r.slice(0, 12)}`}>{r}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="nq-qvai__section">
            <h3 className="nq-qvai__sub">Nguồn</h3>
            {(askResult?.citations ?? copilot?.citations ?? []).length > 0 ? (
              <ul className="nq-qvai__citations" data-testid="copilot-citations">
                {(askResult?.citations ?? copilot?.citations ?? []).map((c) => (
                  <li key={c}>
                    <NguonChip>{c}</NguonChip>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="nq-qvai__nocite" data-testid="copilot-no-citations">
                Chưa có bản ghi hậu thuẫn.
              </p>
            )}
          </div>

          {!askResult && copilot && copilot.suggestedActions.length > 0 ? (
            <div className="nq-qvai__section">
              <h3 className="nq-qvai__sub">Đề xuất</h3>
              <ul className="nq-qvai__suggest" data-testid="copilot-suggestions">
                {copilot.suggestedActions.map((s, i) => (
                  <li key={`${i}-${s.slice(0, 12)}`}>
                    <Icon name="arrow-right" size={12} />
                    {s}
                  </li>
                ))}
              </ul>
              {(() => {
                const links =
                  copilot.actionLinks && copilot.actionLinks.length > 0
                    ? copilot.actionLinks
                    : copilot.suggestedActions
                        .map((s) => {
                          const t = s.toLowerCase();
                          let href: string | null = null;
                          let zoneId: string | null = null;
                          if (t.includes("phân công") || t.includes("lịch tuần") || t.includes("điều người")) href = "/lich-tuan";
                          else if (t.includes("sop") || t.includes("vệ sinh") || t.includes("máy pha")) href = "/sop";
                          else if (t.includes("tồn kho") || t.includes("tiêu thụ") || t.includes("nguyên liệu")) href = "/tieu-thu";
                          else if (t.includes("treo")) href = "/treo";
                          if (t.includes("quầy pha")) zoneId = "quay_pha";
                          else if (t.includes("thu ngân")) zoneId = "quay_thu_ngan";
                          else if (t.includes("khu bàn")) zoneId = "khu_ban";
                          else if (/\bkho\b/.test(t)) zoneId = "kho";
                          return href || zoneId ? { label: s, href, zoneId } : null;
                        })
                        .filter((x): x is NonNullable<typeof x> => x !== null);
                return links.length > 0 ? (
                <div className="nq-qvcmd__chips" data-testid="copilot-action-links">
                  {links.map((l) => (
                    <span key={l.label} className="nq-qvcmd__chips">
                      {l.href ? (
                        <Link className="nq-qvact__cta" href={l.href}>
                          {l.href === "/lich-tuan" ? "Mở Lịch tuần" : l.href === "/sop" ? "Mở SOP" : l.href === "/tieu-thu" ? "Mở Tiêu thụ" : "Mở trang"}: {l.label.slice(0, 40)}
                        </Link>
                      ) : null}
                      {l.zoneId && onFocusZone ? (
                        <button
                          type="button"
                          className="nq-qvcmd__cite"
                          onClick={() => onFocusZone(l.zoneId as string)}
                        >
                          Xem {l.zoneId} →
                        </button>
                      ) : null}
                    </span>
                  ))}
                </div>
                ) : null;
              })()}
              <p className="nq-qvai__disclaimer">
                Đây là đề xuất — người quản lý quyết định và thực hiện.
              </p>
            </div>
          ) : null}

          {(askResult?.unsupportedClaims ?? copilot?.unsupportedClaims ?? [])
            .length > 0 ? (
            <p className="nq-qvai__weak" data-testid="copilot-weak">
              Chưa đủ căn cứ cho:{" "}
              {(askResult?.unsupportedClaims ?? copilot?.unsupportedClaims ?? []).join(
                " · ",
              )}
            </p>
          ) : null}

          <p className="nq-qvai__provider">
            Nguồn sinh:{" "}
            {(askResult?.provider ?? copilot?.provider) === "replay"
              ? "tất định (không gọi LLM)"
              : (askResult?.provider ?? copilot?.provider)}
          </p>
        </>
      )}

      <form
        className="nq-qvai__ask"
        data-testid="copilot-ask-form"
        onSubmit={(e) => {
          e.preventDefault();
          const q = question.trim();
          if (!q || askBusy) return;
          onAsk(q);
          setDraft("");
        }}
      >
        <label className="nq-qvai__ask-label" htmlFor="qv-ask-input">
          Hỏi về trạng thái quán
        </label>
        <div className="nq-qvai__ask-row">
          <input
            id="qv-ask-input"
            className="nq-qvai__ask-input"
            data-testid="copilot-ask-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ví dụ: khu vực nào đang quá tải?"
            maxLength={500}
            disabled={askBusy}
          />
          <button
            type="submit"
            className="nq-qvai__ask-go"
            data-testid="copilot-ask-submit"
            disabled={askBusy || !question}
          >
            {askBusy ? "…" : "Hỏi"}
          </button>
        </div>
        {suggestions.length > 0 ? (
          <ul className="nq-qvai__chips" data-testid="copilot-suggestions-chips">
            {suggestions.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  className="nq-qvai__chip"
                  disabled={askBusy}
                  onClick={() => onAsk(s)}
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </form>

      {thieuNguon.length > 0 ? (
        <p className="nq-qvai__missing" data-testid="copilot-missing">
          <Icon name="warn" size={13} />
          Dữ liệu đang thiếu: {thieuNguon.join(", ")}.
        </p>
      ) : null}
    </Card>
  );
}
