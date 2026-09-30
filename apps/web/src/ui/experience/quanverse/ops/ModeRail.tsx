"use client";

/**
 * QUÁNVERSE — Cafe Modes: đề xuất → xác nhận → tắt.
 *
 * Human-in-the-loop: không tự ghi lịch/nhân sự. Chỉ manager mới confirm/deactivate.
 */

import { Icon } from "../../../icons";
import type { QuanverseMode, QuanverseModesState } from "../quanverse-contract";
import { Card, CardHead } from "./kit";

const NHAN_TT: Record<QuanverseMode["status"], string> = {
  off: "Đang tắt",
  draft: "Chờ duyệt",
  active: "Đang bật",
};

export default function ModeRail({
  modesState,
  busyMode,
  onPropose,
  onConfirm,
  onDeactivate,
}: {
  modesState: QuanverseModesState | null;
  busyMode: string | null;
  onPropose: (mode: string) => void;
  onConfirm: (mode: string) => void;
  onDeactivate: (mode: string) => void;
}) {
  const modes = modesState?.modes ?? [];
  const canActivate = modesState?.canActivate === true;

  return (
    <Card className="nq-qvmode" label="Chế độ quán" testId="quanverse-modes">
      <CardHead
        title="Chế độ quán"
        icon="info"
        trailing={
          <span className="nq-qv-card__count">
            {modes.filter((m) => m.active).length} đang bật
          </span>
        }
      />

      {modes.length === 0 ? (
        <p className="nq-qv-trong" data-testid="modes-empty">
          <span className="nq-qv-trong__text">Chưa đọc được chế độ quán</span>
          <span className="nq-qv-trong__hint">
            Nguồn chế độ tạm thời không phản hồi.
          </span>
        </p>
      ) : (
        <ul className="nq-qvmode__list">
          {modes.map((m) => {
            const busy = busyMode === m.mode;
            return (
              <li
                key={m.mode}
                className={`nq-qvmode__item nq-qvmode__item--${m.status}`}
                data-testid={`mode-${m.mode}`}
                data-status={m.status}
              >
                <div className="nq-qvmode__meta">
                  <span className="nq-qvmode__label">{m.label}</span>
                  <span className={`nq-qvmode__chip nq-qvmode__chip--${m.status}`}>
                    {NHAN_TT[m.status]}
                  </span>
                </div>
                {m.effect ? <p className="nq-qvmode__effect">{m.effect}</p> : null}
                <div className="nq-qvmode__actions">
                  {m.status === "off" ? (
                    <button
                      type="button"
                      className="nq-qvmode__btn"
                      disabled={!canActivate || busy}
                      data-testid={`mode-propose-${m.mode}`}
                      onClick={() => onPropose(m.mode)}
                    >
                      Đề xuất bật
                    </button>
                  ) : null}
                  {m.status === "draft" ? (
                    <button
                      type="button"
                      className="nq-qvmode__btn nq-qvmode__btn--primary"
                      disabled={!canActivate || busy}
                      data-testid={`mode-confirm-${m.mode}`}
                      onClick={() => onConfirm(m.mode)}
                    >
                      <Icon name="check" size={12} />
                      Xác nhận
                    </button>
                  ) : null}
                  {m.status === "active" ? (
                    <button
                      type="button"
                      className="nq-qvmode__btn"
                      disabled={!canActivate || busy}
                      data-testid={`mode-off-${m.mode}`}
                      onClick={() => onDeactivate(m.mode)}
                    >
                      Tắt chế độ
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {!canActivate ? (
        <p className="nq-qvmode__note">
          Chỉ quản lý / chủ quán mới đề xuất và xác nhận chế độ.
        </p>
      ) : (
        <p className="nq-qvmode__note">
          Đề xuất → xác nhận. Hệ thống không tự đổi lịch hay nhân sự.
        </p>
      )}
    </Card>
  );
}
