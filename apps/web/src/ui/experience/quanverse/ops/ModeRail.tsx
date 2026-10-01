"use client";

/**
 * QUÁNVERSE — Cafe Modes: đề xuất → xác nhận → tắt.
 *
 * Human-in-the-loop: không tự ghi lịch/nhân sự. Chỉ manager mới confirm/deactivate.
 * Khi draft/active: hiện checklist vận hành từ effect + affectedProjections.
 */

import { Icon } from "../../../icons";
import type { QuanverseMode, QuanverseModesState } from "../quanverse-contract";
import { Card, CardHead } from "./kit";

const NHAN_TT: Record<QuanverseMode["status"], string> = {
  off: "Đang tắt",
  draft: "Chờ duyệt",
  active: "Đang bật",
};

const NHAN_PROJECTION: Record<string, string> = {
  khu_ngoai_troi: "Giảm tải khu ngoài trời",
  khach_vao: "Điều phối khách vào",
  den_bao_mua: "Đèn / báo mưa gần cửa",
  quay_pha_che: "Quầy pha chế",
  thu_ngan: "Thu ngân",
  nhan_su: "Nhân sự / ca",
  ban_lon: "Bàn lớn / gom bàn",
  kho: "Kho / chuẩn bị",
  dich_vu: "Dịch vụ bàn",
  nang_luc: "Năng lực phục vụ",
  crisis: "Luồng cứu ca",
  khong_gian: "Không gian quán",
  den: "Đèn",
  nhac: "Nhạc",
  am_nhac: "Âm nhạc",
  bar: "Quầy bar / sân khấu",
};

function checklist(m: QuanverseMode): string[] {
  const items: string[] = [];
  if (m.effect.trim()) items.push(m.effect.trim());
  for (const code of m.affectedProjections) {
    const label = NHAN_PROJECTION[code] ?? code;
    if (!items.includes(label)) items.push(label);
  }
  return items.slice(0, 4);
}

export default function ModeRail({
  modesState,
  busyMode,
  highlightMode,
  onPropose,
  onConfirm,
  onDeactivate,
}: {
  modesState: QuanverseModesState | null;
  busyMode: string | null;
  /** Mode được gợi ý từ thời tiết — nhấn mạnh trên rail. */
  highlightMode?: string | null;
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
            const showChecklist = m.status === "draft" || m.status === "active";
            const items = showChecklist ? checklist(m) : [];
            const highlighted = highlightMode === m.mode && m.status === "off";
            return (
              <li
                key={m.mode}
                className={`nq-qvmode__item nq-qvmode__item--${m.status}${
                  highlighted ? " nq-qvmode__item--suggest" : ""
                }`}
                data-testid={`mode-${m.mode}`}
                data-status={m.status}
              >
                <div className="nq-qvmode__meta">
                  <span className="nq-qvmode__label">{m.label}</span>
                  <span className={`nq-qvmode__chip nq-qvmode__chip--${m.status}`}>
                    {NHAN_TT[m.status]}
                  </span>
                </div>
                {m.effect && m.status === "off" ? (
                  <p className="nq-qvmode__effect">{m.effect}</p>
                ) : null}
                {items.length > 0 ? (
                  <ul
                    className="nq-qvmode__checklist"
                    data-testid={`mode-checklist-${m.mode}`}
                  >
                    {items.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="nq-qvmode__actions">
                  {m.status === "off" ? (
                    <button
                      type="button"
                      className={`nq-qvmode__btn${highlighted ? " nq-qvmode__btn--primary" : ""}`}
                      disabled={!canActivate || busy}
                      data-testid={`mode-propose-${m.mode}`}
                      onClick={() => onPropose(m.mode)}
                    >
                      {highlighted ? "Đề xuất (theo thời tiết)" : "Đề xuất bật"}
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
