"use client";

/**
 * QUÁNVERSE — G. AI COPILOT.
 *
 * Trả lời: quán đang có vấn đề gì · ưu tiên gì · vì sao cảnh báo này có · khu
 * vực nào tải cao · 15 phút tới chú ý gì · dữ liệu nào đang thiếu.
 *
 * ─── RANH GIỚI (bắt buộc giữ) ─────────────────────────────────────────────
 *
 * 1. AI KHÔNG ghi DB và KHÔNG tự xác nhận thay đổi. Khối này chỉ ĐỌC.
 * 2. Mọi kết luận phải kèm NGUỒN. Không có nguồn ⇒ hiện thẳng
 *    "Chưa có bản ghi hậu thuẫn." thay vì trình bày như dữ kiện chắc chắn.
 * 3. Backend KHÔNG trả "độ tin cậy" dạng số — chỉ có `grounded` (có căn cứ /
 *    không). Hợp đồng ở đây phản ánh đúng thực tế đó; thêm trường khi backend có.
 */

import { Icon } from "../../../icons";
import {
  CHUA_CO_DU_LIEU,
  type QuanverseCopilot,
  type QuanverseProvenance,
} from "../quanverse-contract";
import { Card, CardHead, NguonChip } from "./kit";

export default function AiCopilot({
  copilot,
  provenance,
}: {
  copilot: QuanverseCopilot | null;
  provenance: readonly QuanverseProvenance[];
}) {
  const thieuNguon = provenance.filter((p) => !p.ok).map((p) => p.label);

  return (
    <Card className="nq-qvai" label="AI Copilot" testId="quanverse-copilot">
      <CardHead
        title="AI Copilot"
        icon="info"
        trailing={
          copilot ? (
            <span
              className={`nq-qvai__grounded${copilot.grounded ? " is-grounded" : ""}`}
              data-testid="copilot-grounded"
            >
              {copilot.grounded ? "Có căn cứ" : "Chưa có căn cứ"}
            </span>
          ) : null
        }
      />

      {!copilot ? (
        <p className="nq-qv-trong" data-testid="copilot-empty">
          <span className="nq-qv-trong__text">{CHUA_CO_DU_LIEU}</span>
          <span className="nq-qv-trong__hint">
            Chưa lấy được bản tóm tắt cho trạng thái hiện tại.
          </span>
        </p>
      ) : (
        <>
          <p className="nq-qvai__headline" data-testid="copilot-headline">
            {copilot.headline}
          </p>

          {copilot.reasons.length > 0 ? (
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
            {copilot.citations.length > 0 ? (
              <ul className="nq-qvai__citations" data-testid="copilot-citations">
                {copilot.citations.map((c) => (
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

          {copilot.suggestedActions.length > 0 ? (
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
              <p className="nq-qvai__disclaimer">
                Đây là đề xuất — người quản lý quyết định và thực hiện.
              </p>
            </div>
          ) : null}

          {copilot.unsupportedClaims.length > 0 ? (
            <p className="nq-qvai__weak" data-testid="copilot-weak">
              Chưa đủ căn cứ cho: {copilot.unsupportedClaims.join(" · ")}
            </p>
          ) : null}

          <p className="nq-qvai__provider">
            Nguồn sinh: {copilot.provider === "replay" ? "tất định (không gọi LLM)" : copilot.provider}
          </p>
        </>
      )}

      {thieuNguon.length > 0 ? (
        <p className="nq-qvai__missing" data-testid="copilot-missing">
          <Icon name="warn" size={13} />
          Dữ liệu đang thiếu: {thieuNguon.join(", ")}.
        </p>
      ) : null}
    </Card>
  );
}
