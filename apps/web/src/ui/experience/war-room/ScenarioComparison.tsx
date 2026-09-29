"use client";

/**
 * So sánh baseline + phương án. Mọi số phải có nhãn "Mô phỏng"/"Ước tính".
 *
 * Bản trước in `option_id` thô làm tiêu đề phương án — người vận hành phải đọc
 * `opt_crisis_rain_scn` để biết đó là "Mưa lớn". Bản này dùng bảng nhãn và chỉ
 * giữ mã trong `data-option` cho kiểm thử.
 */

import { Icon } from "../../icons";
import { formatVnd } from "../experience-api";
import { eventStatusLabel, warOptionTitle } from "../exp-present";
import type { WarRoomOption } from "./war-room-model";

interface Props {
  baseline: Record<string, string | number | boolean>;
  options: WarRoomOption[];
  selectedOptionId: string | null;
  onSelect: (optionId: string) => void;
  onPropose: (optionId: string) => void;
  onShowEvidence: (option: WarRoomOption) => void;
  proposing: boolean;
}

/** Số tiền chênh so với baseline — chỉ hiện khi baseline thật sự có số. */
function deltaText(baselineVnd: number, optionVnd: number | null | undefined): string {
  if (optionVnd === null || optionVnd === undefined || !Number.isFinite(optionVnd)) {
    return "Không có số dự kiến";
  }
  if (!Number.isFinite(baselineVnd) || baselineVnd <= 0) return "Chưa có mốc so sánh";
  const diff = optionVnd - baselineVnd;
  const sign = diff >= 0 ? "+" : "−";
  return `${sign}${formatVnd(Math.abs(diff))} so với ca thường`;
}

export default function ScenarioComparison({
  baseline,
  options,
  selectedOptionId,
  onSelect,
  onPropose,
  onShowEvidence,
  proposing,
}: Props) {
  const baselineVnd = Number(baseline.doanh_thu_tb_ca ?? 0);

  return (
    <section className="nq-war-compare" aria-label="So sánh phương án">
      <div className="nq-war-compare__baseline">
        <h3>Hiện trạng (dữ liệu đang có)</h3>
        <dl>
          <dt>Nhân viên khả dụng</dt>
          <dd>{String(baseline.nhan_vien_available ?? "—")}</dd>
          <dt>Doanh thu TB ca</dt>
          <dd>{formatVnd(baselineVnd)}</dd>
        </dl>
      </div>

      <div className="nq-war-compare__rail">
        {options.length === 0 ? (
          <p className="nq-war-compare__empty">
            Không dựng được phương án nào từ các kịch bản đã chọn.
          </p>
        ) : null}
        {options.map((opt) => {
          const blocked = (opt.constraint_violations?.length ?? 0) > 0;
          const title = warOptionTitle(opt.option_id, "Phương án");
          return (
            <div
              key={opt.option_id}
              data-option={opt.option_id}
              className={`nq-war-compare__option${selectedOptionId === opt.option_id ? " is-selected" : ""}${blocked ? " is-blocked" : ""}`}
            >
              <button
                type="button"
                className="nq-war-compare__head"
                aria-pressed={selectedOptionId === opt.option_id}
                onClick={() => onSelect(opt.option_id)}
              >
                {title}
              </button>

              <dl className="nq-war-compare__nums">
                <div>
                  <dt>Doanh thu dự kiến</dt>
                  <dd>{formatVnd(opt.outputs?.doanh_thu_du_kien ?? null)}</dd>
                </div>
                <div>
                  <dt>Chênh ca thường</dt>
                  <dd>{deltaText(baselineVnd, opt.outputs?.doanh_thu_du_kien ?? null)}</dd>
                </div>
                <div>
                  <dt>Công bằng delta</dt>
                  <dd>
                    {typeof opt.fairness_impact?.delta === "number"
                      ? opt.fairness_impact.delta.toFixed(2)
                      : "—"}
                  </dd>
                </div>
              </dl>

              <div className="nq-war-compare__flags">
                {blocked ? (
                  <span className="nq-war-compare__blocked">
                    <Icon name="warn" size={12} />
                    Vi phạm ràng buộc cứng
                  </span>
                ) : (
                  <span className="nq-war-compare__sim">
                    <Icon name="info" size={12} />
                    Ước tính từ mô phỏng
                  </span>
                )}
                {opt.stale_data ? (
                  <span className="nq-war-compare__stale">Dữ liệu nền đã cũ</span>
                ) : null}
              </div>

              {opt.reason ? (
                <p className="nq-war-compare__reason" data-reason={opt.option_id}>
                  <Icon name="info" size={12} /> {opt.reason}
                </p>
              ) : null}

              <div className="nq-war-compare__actions">
                <button
                  type="button"
                  className="nq-btn-compact nq-modebtn"
                  data-testid="why-btn"
                  onClick={() => onShowEvidence(opt)}
                >
                  <Icon name="info" size={13} />
                  Vì sao
                </button>
                <button
                  type="button"
                  className="nq-btn nq-btn-primary"
                  data-testid="propose-btn"
                  disabled={blocked || proposing}
                  onClick={() => onPropose(opt.option_id)}
                >
                  {proposing ? "Đang xử lý…" : "Đề xuất"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}