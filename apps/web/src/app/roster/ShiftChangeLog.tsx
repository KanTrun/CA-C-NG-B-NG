"use client";

/**
 * Nhật ký thay đổi ca — "ai đổi ca với ai", đọc được bằng mắt thường.
 *
 * Vì sao tách thành component riêng: cùng một câu hỏi được hỏi ở hai chỗ —
 * `/lich-tuan` (sau khi xếp tự động) và `/doi-ca` (sau khi chốt phiếu đổi ca).
 * Hai nơi tự vẽ thì sẽ có hai cách trình bày khác nhau cho cùng một dữ liệu, và
 * người dùng phải học lại cách đọc ở mỗi trang.
 *
 * Nguyên tắc trình bày (theo đúng phàn nàn của người dùng):
 *  - In TÊN người, không in mã `nv_xx`.
 *  - Phân biệt RÕ ba chuyện khác nhau: CA đổi người · NGƯỜI chuyển ca · LƯỢT
 *    vào/ra lẻ. Gộp chúng lại thành "3 thay đổi" là vô nghĩa với người đọc.
 *  - Không có gì đổi thì nói thẳng "không có gì đổi", đừng hiện bảng rỗng.
 *  - Thiếu dữ liệu thì nói "chưa đủ dữ liệu", KHÔNG nói "không có gì đổi".
 *  - Panel mở sẵn trên `/lich-tuan` — không chôn trong `<details>` đóng.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet } from "../../lib/api";
import { getToken } from "../../lib/session";
import { Empty, Loading, StatusChip } from "../../ui/kit";
import type { Diff, HoanDoi } from "./shift-change-types";

export type { Diff, ChuyenCa, DongThayDoi, HoanDoi } from "./shift-change-types";

type BanGhi = {
  luc: string;
  nguon: string;
  tuan_iso: string;
  diff: Diff;
  tom_tat?: string;
};

const NGUON_LABEL: Record<string, string> = {
  xep_tu_dong: "Xếp tự động",
  tkb: "Lịch bận (TKB)",
  doi_ca: "Chợ đổi ca",
  gap: "Bù ca thiếu",
  cu_bi: "Trực dự bị",
};

type FilterMode = "tat_ca" | "hoan_doi";

function gioHienThi(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function tenTrongDiff(diff: Diff | undefined): string[] {
  if (!diff) return [];
  const names = new Set<string>();
  for (const h of diff.hoan_doi ?? []) {
    for (const r of h.ra) names.add(r.ten);
    for (const v of h.vao) names.add(v.ten);
  }
  for (const c of diff.doi_giua_hai_ca ?? []) names.add(c.ten);
  for (const t of diff.them ?? []) names.add(t.ten);
  for (const b of diff.bot ?? []) names.add(b.ten);
  return [...names];
}

function thuTrongDiff(diff: Diff | undefined): string[] {
  if (!diff) return [];
  const days = new Set<string>();
  for (const h of diff.hoan_doi ?? []) {
    if (h.ca.thu) days.add(h.ca.thu);
  }
  for (const t of [...(diff.them ?? []), ...(diff.bot ?? [])]) {
    if (t.ca.thu) days.add(t.ca.thu);
  }
  return [...days];
}

/** Một dòng phẳng: ngày · khung giờ · A → B · nguồn · lúc */
function FlatHoanDoiRow({
  h,
  nguon,
  luc,
}: {
  h: HoanDoi;
  nguon: string;
  luc: string;
}) {
  return (
    <li className="nq-shiftlog__flat-row" data-kind="hoan-doi">
      <span className="nq-shiftdiff__when">
        {h.ca.thu || "—"} · {h.ca.gio || h.ca.khung || "—"}
      </span>
      <span className="nq-shiftdiff__who">
        <span className="nq-shiftdiff__out">{h.ra.map((r) => r.ten).join(", ")}</span>
        <span className="nq-shiftdiff__arrow">→</span>
        <span className="nq-shiftdiff__in">{h.vao.map((v) => v.ten).join(", ")}</span>
      </span>
      <StatusChip tone="info">{NGUON_LABEL[nguon] ?? nguon}</StatusChip>
      <span className="nq-shiftlog__time">{gioHienThi(luc)}</span>
    </li>
  );
}

/** Bảng chứng minh đổi ca cho MỘT bản ghi diff. */
export function ShiftChangeDiff({ diff }: { diff: Diff }) {
  if (diff.khong_so_sanh_duoc) {
    return (
      <p className="nq-shiftdiff__empty">
        Chưa đủ dữ liệu để so sánh hai bản phân công (một bên chưa có lịch).
      </p>
    );
  }
  const rong =
    diff.hoan_doi.length === 0 &&
    diff.doi_giua_hai_ca.length === 0 &&
    diff.them.length === 0 &&
    diff.bot.length === 0;

  if (rong) {
    return <p className="nq-shiftdiff__empty">Không có ca nào thay đổi.</p>;
  }

  return (
    <div className="nq-shiftdiff">
      {diff.hoan_doi.length > 0 ? (
        <section className="nq-shiftdiff__block">
          <h4 className="nq-shiftdiff__title">Ca đổi người</h4>
          <ul className="nq-shiftdiff__list">
            {diff.hoan_doi.map((h) => (
              <li key={h.ca.ca_id} className="nq-shiftdiff__row">
                <span className="nq-shiftdiff__when">
                  {h.ca.thu} · {h.ca.gio}
                </span>
                <span className="nq-shiftdiff__who">
                  <span className="nq-shiftdiff__out">{h.ra.map((r) => r.ten).join(", ")}</span>
                  <span className="nq-shiftdiff__arrow">→</span>
                  <span className="nq-shiftdiff__in">{h.vao.map((v) => v.ten).join(", ")}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {diff.doi_giua_hai_ca.length > 0 ? (
        <section className="nq-shiftdiff__block">
          <h4 className="nq-shiftdiff__title">Người chuyển sang ca khác (không mất ca)</h4>
          <ul className="nq-shiftdiff__list">
            {diff.doi_giua_hai_ca.map((c) => (
              <li key={c.nv_id} className="nq-shiftdiff__row">
                <span className="nq-shiftdiff__who">
                  <strong>{c.ten}</strong>
                  <span className="nq-shiftdiff__arrow">
                    {c.tu_ca.map((t) => `${t.thu} ${t.gio}`).join(", ")} →{" "}
                    {c.den_ca.map((d) => `${d.thu} ${d.gio}`).join(", ")}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {diff.bot.length > 0 || diff.them.length > 0 ? (
        <section className="nq-shiftdiff__block">
          <h4 className="nq-shiftdiff__title">Lượt vào / ra ca</h4>
          <ul className="nq-shiftdiff__tags">
            {diff.bot.map((b) => (
              <li key={`ra-${b.ca.ca_id}-${b.nv_id}`} data-chieu="ra">
                {b.ten} ra khỏi {b.ca.thu} {b.ca.gio}
              </li>
            ))}
            {diff.them.map((t) => (
              <li key={`vao-${t.ca.ca_id}-${t.nv_id}`} data-chieu="vao">
                {t.ten} vào {t.ca.thu} {t.ca.gio}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="nq-shiftdiff__keep">
        Giữ nguyên {diff.giu_nguyen} lượt phân công không đổi.
      </p>
    </div>
  );
}

/**
 * Panel nhật ký: tự tải `/api/v1/lich-tuan/thay-doi` cho một tuần.
 *
 * `compact` dùng cho chỗ chật (trang /doi-ca) — chỉ hiện bản mới nhất.
 * Chỉ quản lý/chủ mới gọi được endpoint; nhân viên sẽ nhận 403 và panel tự ẩn
 * (không hiện lỗi đỏ vì đây không phải hành động của họ).
 *
 * `refreshKey` tăng sau xếp/duyệt/swap để buộc tải lại mà không cần đổi tuần.
 */
export function ShiftChangeLog({
  tuanIso,
  compact = false,
  refreshKey = 0,
}: {
  tuanIso: string;
  compact?: boolean;
  refreshKey?: number;
}) {
  const [items, setItems] = useState<BanGhi[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [filterMode, setFilterMode] = useState<FilterMode>("tat_ca");
  const [filterThu, setFilterThu] = useState("all");
  const [filterNguoi, setFilterNguoi] = useState("all");

  const load = useCallback(() => {
    if (!getToken() || !tuanIso) return;
    setLoading(true);
    setHidden(false);
    apiGet<{ items?: BanGhi[] }>(`/api/v1/lich-tuan/thay-doi?tuan_iso=${encodeURIComponent(tuanIso)}`)
      .then((d) => setItems(d.items ?? []))
      .catch(() => setHidden(true))
      .finally(() => setLoading(false));
  }, [tuanIso]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const nguoiOptions = useMemo(() => {
    const set = new Set<string>();
    for (const b of items ?? []) {
      for (const ten of tenTrongDiff(b.diff)) set.add(ten);
    }
    return [...set].sort((a, b) => a.localeCompare(b, "vi"));
  }, [items]);

  const thuOptions = useMemo(() => {
    const set = new Set<string>();
    for (const b of items ?? []) {
      for (const thu of thuTrongDiff(b.diff)) set.add(thu);
    }
    return [...set];
  }, [items]);

  const filtered = useMemo(() => {
    const list = items ?? [];
    return list.filter((b) => {
      if (filterMode === "hoan_doi" && !(b.diff?.hoan_doi?.length > 0)) return false;
      if (filterThu !== "all" && !thuTrongDiff(b.diff).includes(filterThu)) return false;
      if (filterNguoi !== "all" && !tenTrongDiff(b.diff).includes(filterNguoi)) return false;
      return true;
    });
  }, [items, filterMode, filterThu, filterNguoi]);

  if (hidden) return null;
  if (loading && items === null) return <Loading skeleton="rows">Đang tải nhật ký…</Loading>;
  if (!items || items.length === 0) {
    if (compact) return null;
    return (
      <section className="nq-shiftlog" data-panel="nhat-ky-doi-ca" aria-label="Nhật ký đổi ca">
        <header className="nq-shiftlog__panel-head">
          <h3 className="nq-shiftlog__panel-title">Ai đổi ca với ai — tuần {tuanIso}</h3>
        </header>
        <Empty>
          Chưa có thay đổi tuần này — xếp lần đầu hoặc duyệt đổi ca sẽ xuất hiện ở đây.
        </Empty>
      </section>
    );
  }

  const hienThi = compact ? filtered.slice(0, 1) : filtered;
  const flatHoanDoi = !compact
    ? hienThi.flatMap((b) =>
        (b.diff?.hoan_doi ?? []).map((h) => ({
          key: `${b.luc}-${h.ca.ca_id}`,
          h,
          nguon: b.nguon,
          luc: b.luc,
        })),
      )
    : [];

  return (
    <section className="nq-shiftlog" data-panel="nhat-ky-doi-ca" aria-label="Nhật ký đổi ca">
      {!compact ? (
        <header className="nq-shiftlog__panel-head">
          <h3 className="nq-shiftlog__panel-title">Ai đổi ca với ai — tuần {tuanIso}</h3>
          <p className="nq-shiftlog__panel-hint">
            Mỗi dòng: ngày · khung giờ · người ra → người vào · nguồn · lúc.
          </p>
          <div className="nq-shiftlog__filters" role="group" aria-label="Lọc nhật ký">
            <label>
              <span className="sr-only">Loại</span>
              <select
                value={filterMode}
                onChange={(e) => setFilterMode(e.target.value as FilterMode)}
                aria-label="Lọc theo loại thay đổi"
              >
                <option value="tat_ca">Mọi thay đổi</option>
                <option value="hoan_doi">Chỉ hoán đổi A → B</option>
              </select>
            </label>
            <label>
              <span className="sr-only">Ngày</span>
              <select
                value={filterThu}
                onChange={(e) => setFilterThu(e.target.value)}
                aria-label="Lọc theo ngày"
              >
                <option value="all">Mọi ngày</option>
                {thuOptions.map((thu) => (
                  <option key={thu} value={thu}>
                    {thu}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="sr-only">Người</span>
              <select
                value={filterNguoi}
                onChange={(e) => setFilterNguoi(e.target.value)}
                aria-label="Lọc theo người"
              >
                <option value="all">Mọi người</option>
                {nguoiOptions.map((ten) => (
                  <option key={ten} value={ten}>
                    {ten}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </header>
      ) : null}

      {flatHoanDoi.length > 0 ? (
        <ul className="nq-shiftlog__flat-list" aria-label="Hoán đổi nhanh">
          {flatHoanDoi.map((row) => (
            <FlatHoanDoiRow key={row.key} h={row.h} nguon={row.nguon} luc={row.luc} />
          ))}
        </ul>
      ) : null}

      {hienThi.length === 0 ? (
        <Empty>Không có thay đổi khớp bộ lọc hiện tại.</Empty>
      ) : (
        hienThi.map((b) => (
          <article key={`${b.luc}-${b.tom_tat ?? ""}`} className="nq-shiftlog__entry">
            <header className="nq-shiftlog__head">
              <StatusChip tone="info">{NGUON_LABEL[b.nguon] ?? b.nguon}</StatusChip>
              <span className="nq-shiftlog__time">{gioHienThi(b.luc)}</span>
            </header>
            {b.tom_tat ? <p className="nq-shiftlog__summary">{b.tom_tat}</p> : null}
            {b.diff ? <ShiftChangeDiff diff={b.diff} /> : null}
          </article>
        ))
      )}
      {compact && items.length > 1 ? (
        <p className="nq-shiftlog__more">Còn {items.length - 1} lần thay đổi khác trong tuần này.</p>
      ) : null}
    </section>
  );
}
