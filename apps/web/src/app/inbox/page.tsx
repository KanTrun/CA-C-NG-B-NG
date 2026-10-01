"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { apiGet, apiSend } from "../../lib/api";
import {
  agentLabel,
  formatLuc,
  inboxLabel,
  inboxTone,
  kenhLabel,
  khungLabel,
  rangBuocLabel,
  replaceNvIdsInText,
  safeText,
  thuLabel,
  yDinhLabel,
} from "../../lib/present";
import { matchExact, matchSearch, matchTime, TIME_FILTER_OPTIONS, uniqueSorted, type TimeFilter } from "../../lib/list-filters";
import { getToken, isChuQuan } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  Confidence,
  Empty,
  FixtureChip,
  Group,
  Loading,
  Notice,
  PageGrid,
  PageHeader,
  PagedList,
  Row,
  StatusChip,
} from "../../ui/kit";
import { FilteredEmpty, ListToolbar } from "../../ui/list-filters";
import { useStaffNameMap } from "../../ui/ops-pickers";
import { AiInsightPanel } from "../../ui/ai/AiInsightPanel";
import { AskAiBox } from "../../ui/ai/AskAiBox";

type Lifecycle = {
  tuan_iso?: string;
  trang_thai?: string;
  solver?: {
    status?: string;
    ok?: boolean;
    danh_sach_xung_dot?: string[];
  };
};

type AutoScheduleResult = {
  ok?: boolean;
  skipped?: boolean;
  status?: string;
  detail?: string;
  tong_so_o_ca?: number;
  so_o_ca_da_xep?: number;
};

type Item = {
  id: string;
  tom_tat: string;
  trang_thai: string;
  agent: string;
  y_dinh?: string;
  do_tin_cay?: number;
  created_at?: string;
  nguon?: string;
  noi_dung_goc?: string;
  nv_id?: string;
  can_xac_minh?: boolean;
  doi_tac_khong_ro?: boolean;
  khan_cap?: boolean;
  ly_do_quyet?: string;
  hieu_luc?: { loai?: string; ghi?: string; swap_id?: string; tuan_id?: string };
  tu_dong_xep_lich?: AutoScheduleResult;
  rang_buoc?: {
    loai?: string;
    thu?: string;
    khung?: string;
    start?: string;
    end?: string;
    tuan_id?: string;
    ca_id?: string;
    doi_tac?: string;
    doi_tac_khong_ro?: boolean;
    can_xac_minh?: boolean;
  };
};

const THU_TU = ["cho_duyet", "moi", "duyet", "tu_choi"];

const TEN_NHOM: Record<string, string> = {
  cho_duyet: "AI đang xử lý",
  moi: "Mới vào hộp thư",
  duyet: "AI đã duyệt",
  tu_choi: "AI đã từ chối",
};

/** Diễn đạt mục đích ràng buộc bằng một câu người đọc hiểu ngay. */
function mucDichCau(it: Item): string {
  const y = it.y_dinh ?? "khac";
  const rb = it.rang_buoc ?? {};
  const thuFull = rb.thu ? thuLabel(rb.thu) : "";
  switch (y) {
    case "xin_nghi":
      if (!thuFull) return "Xin nghỉ một ca (chưa rõ ngày)";
      // Có khung giờ = nghỉ ĐÚNG ca đó, KHÔNG phải cả ngày.
      return rb.start && rb.end
        ? `Xin nghỉ ca ${thuFull} (${rb.start}–${rb.end})`
        : `Xin nghỉ cả ngày ${thuFull}`;
    case "doi_ca":
      return "Đổi ca sang người khác trong tuần";
    case "nhan_ca":
      return "Nhận thêm ca trong tuần";
    case "bao_tre":
      return rb.start
        ? `Báo đến trễ từ ${rb.start} ngày ${thuFull || "ca này"}`
        : "Báo đến trễ trong ca";
    case "cap_nhat_tkb":
      return rb.start && rb.end
        ? `Lịch bận ${thuFull || "ngày"} khung ${rb.start}–${rb.end}`
        : "Cập nhật lịch bận (thời khóa biểu)";
    default:
      return "Ghi nhận việc trong ca, không đổi lịch";
  }
}

/** Diễn đạt lý do bị ràng buộc — từ nội dung gốc hoặc hiệu lực đã ghi. */
function lyDoCau(it: Item): string {
  if (it.hieu_luc?.ghi) return it.hieu_luc.ghi;
  const goc = it.noi_dung_goc?.trim();
  if (goc) return goc.length > 160 ? `${goc.slice(0, 160)}…` : goc;
  return it.tom_tat;
}

function ngayRangBuoc(it: Item): string {
  const rb = it.rang_buoc ?? {};
  const parts: string[] = [];
  if (rb.thu) parts.push(thuLabel(rb.thu));
  if (rb.start && rb.end) parts.push(`${rb.start}–${rb.end}`);
  else if (rb.khung) parts.push(khungLabel(rb.khung) || "");
  if (rb.tuan_id) parts.push(`Tuần ${rb.tuan_id}`);
  return parts.filter(Boolean).join(" · ") || "Không rõ ngày";
}

function itemHaystack(it: Item): string {
  return [
    it.tom_tat,
    it.nguon,
    it.agent,
    it.nv_id,
    it.noi_dung_goc,
    it.hieu_luc?.ghi,
    inboxLabel(it.trang_thai),
    yDinhLabel(it.y_dinh),
  ]
    .filter(Boolean)
    .join(" ");
}

export default function InboxPage() {
  const [token, setToken] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusF, setStatusF] = useState("all");
  const [personF, setPersonF] = useState("all");
  const [timeF, setTimeF] = useState<TimeFilter>("all");
  const [life, setLife] = useState<Lifecycle | null>(null);
  const [chuQuan, setChuQuan] = useState(false);
  const [showReopenModal, setShowReopenModal] = useState(false);
  const [reopenReason, setReopenReason] = useState("");
  const [coMau, setCoMau] = useState(false);
  const staffName = useStaffNameMap();

  useEffect(() => {
    setToken(getToken());
    setChuQuan(isChuQuan());
    if (!getToken()) setLoading(false);
  }, []);

  const load = useCallback(() => {
    if (!getToken()) return;
    apiGet<{ items: Item[]; co_du_lieu_mau?: boolean }>("/api/v1/inbox/rang-buoc")
      .then((d) => {
        setItems(d.items ?? []);
        setCoMau(d.co_du_lieu_mau === true);
      })
      .catch(() => setError("Không tải được hộp thư."))
      .finally(() => setLoading(false));
    apiGet<Lifecycle>("/api/v1/lich/lifecycle")
      .then((l) => setLife(l))
      .catch(() => {});
  }, []);

  async function reopenWeek() {
    if (!reopenReason.trim()) {
      setError("Vui lòng nhập lý do mở lại lịch.");
      return;
    }
    setBusy("reopen");
    try {
      await apiSend("/api/v1/lich/lifecycle", { to: "nhap", ly_do: reopenReason.trim() });
      setShowReopenModal(false);
      setReopenReason("");
      load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Không thể mở lại lịch.";
      setError(msg);
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  useEffect(() => {
    if (!showReopenModal) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function closeDialog(event: KeyboardEvent) {
      if (event.key === "Escape") setShowReopenModal(false);
    }
    document.addEventListener("keydown", closeDialog);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeDialog);
    };
  }, [showReopenModal]);

  const personOptions = useMemo(
    () => [
      { value: "all", label: "Mọi người" },
      ...uniqueSorted(items.map((i) => i.nv_id)).map((v) => ({ value: v, label: staffName(v) })),
    ],
    [items, staffName],
  );

  const statusOptions = useMemo(
    () => [{ value: "all", label: "Mọi trạng thái" }, ...THU_TU.map((s) => ({ value: s, label: TEN_NHOM[s] ?? inboxLabel(s) }))],
    [],
  );

  const filtered = useMemo(() => {
    return items.filter((it) => {
      if (!matchSearch(itemHaystack(it), search)) return false;
      if (!matchExact(it.trang_thai, statusF)) return false;
      if (!matchExact(it.nv_id, personF)) return false;
      if (!matchTime(it.created_at, timeF)) return false;
      return true;
    });
  }, [items, search, statusF, personF, timeF]);

  const nhom = useMemo(() => {
    const buckets = new Map<string, Item[]>();
    for (const tt of THU_TU) buckets.set(tt, []);
    for (const it of filtered) {
      const key = buckets.has(it.trang_thai) ? it.trang_thai : "moi";
      buckets.get(key)!.push(it);
    }
    return THU_TU.map((tt) => [tt, buckets.get(tt)!] as const).filter(([, list]) => list.length > 0);
  }, [filtered]);

  const filterActive = search.length > 0 || statusF !== "all" || personF !== "all" || timeF !== "all";

  function clearFilters() {
    setSearch("");
    setStatusF("all");
    setPersonF("all");
    setTimeF("all");
  }

  if (!token) return <AuthGate />;

  return (
    <div className="nq-page nq-page--wide">
      <PageHeader
        kicker="AI tự động duyệt · chỉ xem"
        title="Hộp thư ràng buộc"
        meta="AI đọc từng yêu cầu, tự quyết định duyệt/từ chối và tự xếp lại lịch — trang này chỉ để xem lại quyết định."
      />
      {coMau ? (
        <p className="mb-4">
          <FixtureChip />
        </p>
      ) : null}
      {error ? <Alert>{error}</Alert> : null}
      {life?.solver && (!life.solver.ok || life.solver.status?.includes("INFEASIBLE")) ? (
        <div className="mb-4 p-4 border-2 border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] bg-[var(--nq-st-danger-soft)] text-[var(--nq-st-danger-ink)] rounded">
          <div className="font-bold uppercase tracking-wider mb-1 flex items-center gap-2">
            Lịch tuần này đang xung đột — Solver không khả thi
          </div>
          <p className="text-sm mb-2">
            Các ràng buộc xin nghỉ hoặc TKB đã duyệt khiến một số ca thiếu nhân sự tối thiểu. Chi tiết:
          </p>
          <ul className="list-disc list-inside text-xs space-y-1">
            {life.solver.danh_sach_xung_dot && life.solver.danh_sach_xung_dot.length > 0 ? (
              life.solver.danh_sach_xung_dot.map((c, i) => <li key={i}>{c}</li>)
            ) : (
              <li>Mâu thuẫn giữa ràng buộc nghỉ phép/TKB và yêu cầu số người của ca.</li>
            )}
          </ul>
        </div>
      ) : null}

      {life?.trang_thai === "da_dong" ? (
        <div className="nq-surface-row mb-4 p-4 border-[var(--nq-accent)] bg-[var(--nq-accent-dim,#332211)] text-[var(--nq-fg)] flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
          <div>
            <div className="font-bold uppercase tracking-wider">
              Lịch tuần {life.tuan_iso ?? ""} đã đóng băng
            </div>
            <div className="text-sm opacity-80">
              Đợt xếp lịch tuần này đã đóng. Chủ quán có thể mở lại đợt xếp tuần mới.
            </div>
          </div>
          {chuQuan ? (
            <Btn variant="primary" onClick={() => setShowReopenModal(true)}>
              Mở đợt xếp tuần mới
            </Btn>
          ) : null}
        </div>
      ) : null}

      <PageGrid
        main={
          <>
            <ListToolbar
              search={search}
              onSearchChange={setSearch}
              searchPlaceholder="Tìm tóm tắt, kênh, agent, mã NV…"
              status={statusF}
              onStatusChange={setStatusF}
              statusOptions={statusOptions}
              person={personF}
              onPersonChange={setPersonF}
              personOptions={personOptions}
              time={timeF}
              onTimeChange={(v) => setTimeF(v as TimeFilter)}
              timeOptions={TIME_FILTER_OPTIONS}
              shown={filtered.length}
              total={items.length}
              filtered={filterActive}
            />

            {loading ? (
              <Loading skeleton="rows" rows={4} groups={3}>
                Đang mở hộp thư…
              </Loading>
            ) : null}

            {!loading && !error && items.length === 0 ? (
              <Empty title="Hộp thư trống">Chưa có yêu cầu nào cần AI xử lý.</Empty>
            ) : null}

            {!loading && items.length > 0 && filtered.length === 0 ? <FilteredEmpty onClear={clearFilters} /> : null}

            {!loading &&
              nhom.map(([tt, list]) => (
                <Group key={tt} title={TEN_NHOM[tt] ?? inboxLabel(tt)} count={list.length} countLabel="mục">
                  <PagedList
                    items={list}
                    pageSize={10}
                    renderItem={(it) => (
                      <Row
                        key={it.id}
                        title={replaceNvIdsInText(safeText(it.tom_tat, "Ràng buộc chưa có tóm tắt"), staffName)}
                        sub={
                          <div className="space-y-2 text-sm leading-relaxed">
                            <p className="text-[var(--nq-fg)]">
                              {replaceNvIdsInText(safeText(it.noi_dung_goc, "Ràng buộc không kèm nội dung gốc"), staffName)}
                            </p>
                            {/* Dòng thời gian: Yêu cầu → AI quyết định → Kết quả xếp lịch */}
                            <ol className="nq-inbox-timeline">
                              <li>
                                <span className="nq-inbox-timeline__dot" aria-hidden="true" />
                                <span>
                                  <strong>Yêu cầu:</strong> {mucDichCau(it)} — {ngayRangBuoc(it)}
                                  {it.nv_id ? ` · ${staffName(it.nv_id)}` : ""} · {kenhLabel(it.nguon)}
                                  {it.created_at ? ` · ${formatLuc(it.created_at)}` : ""}
                                </span>
                              </li>
                              <li>
                                <span
                                  className="nq-inbox-timeline__dot"
                                  data-tone={it.trang_thai === "tu_choi" ? "danger" : it.trang_thai === "duyet" ? "ok" : "warn"}
                                  aria-hidden="true"
                                />
                                <span>
                                  <strong>AI quyết định:</strong>{" "}
                                  {it.trang_thai === "tu_choi"
                                    ? `Từ chối — ${replaceNvIdsInText(safeText(it.ly_do_quyet, "không đủ điều kiện tự động xử lý"), staffName)}`
                                    : it.trang_thai === "duyet"
                                      ? `Duyệt — ${replaceNvIdsInText(lyDoCau(it), staffName)}`
                                      : "Đang xử lý…"}
                                </span>
                              </li>
                              {it.trang_thai === "duyet" && (it.hieu_luc?.loai === "rang_buoc_cho_solver" || it.tu_dong_xep_lich) ? (
                                <li>
                                  <span
                                    className="nq-inbox-timeline__dot"
                                    data-tone={it.tu_dong_xep_lich?.ok ? "ok" : "warn"}
                                    aria-hidden="true"
                                  />
                                  <span>
                                    <strong>Kết quả xếp lịch:</strong>{" "}
                                    {it.tu_dong_xep_lich?.ok
                                      ? `Đã xếp đủ ${it.tu_dong_xep_lich.so_o_ca_da_xep ?? 0}/${it.tu_dong_xep_lich.tong_so_o_ca ?? 21} ô ca.`
                                      : it.tu_dong_xep_lich?.status === "LIFECYCLE_LOCKED"
                                        ? "Lịch tuần đã khoá — chờ áp vào lượt xếp lịch sau."
                                        : "Đã ghi hiệu lực — chờ áp vào lượt xếp lịch tới."}{" "}
                                    <Link href="/lich-tuan" className="underline">
                                      Xem lịch tuần →
                                    </Link>
                                  </span>
                                </li>
                              ) : null}
                              {it.trang_thai === "duyet" && (it.y_dinh === "doi_ca" || it.y_dinh === "nhan_ca") ? (
                                <li>
                                  <span className="nq-inbox-timeline__dot" data-tone="ok" aria-hidden="true" />
                                  <span>
                                    <strong>Kết quả:</strong> Đã ghi đổi ca vào lịch.{" "}
                                    <Link href="/doi-ca" className="underline">
                                      Xem chợ đổi ca →
                                    </Link>
                                  </span>
                                </li>
                              ) : null}
                            </ol>
                          </div>
                        }
                        side={
                          <>
                            <StatusChip tone={inboxTone(it.trang_thai)}>{inboxLabel(it.trang_thai)}</StatusChip>
                            <StatusChip>{kenhLabel(it.nguon)}</StatusChip>
                            <StatusChip>{yDinhLabel(it.y_dinh)}</StatusChip>
                            {it.khan_cap ? <StatusChip tone="danger">Khẩn cấp (&lt;24h)</StatusChip> : null}
                            {it.can_xac_minh || (it.do_tin_cay != null && it.do_tin_cay < 0.7) ? (
                              <StatusChip tone="danger">Cần xác minh</StatusChip>
                            ) : null}
                            <Confidence value={it.do_tin_cay} />
                          </>
                        }
                      />
                    )}
                  />
                </Group>
              ))}
          </>
        }
        aside={
          <>
            <AiInsightPanel page="inbox" />
            <AskAiBox page="inbox" />
          </>
        }
      />

      {showReopenModal && typeof document !== "undefined" ? createPortal(
        <div className="nq-inbox-dialog-layer">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="inbox-reopen-dialog-title"
            className="nq-inbox-dialog-panel nq-inbox-dialog-panel--compact nq-inbox-dialog-panel--accent"
          >
            <h3 id="inbox-reopen-dialog-title" className="text-lg font-bold uppercase tracking-wider mb-2 text-[var(--nq-fg)]">
              Mở lại đợt xếp lịch tuần mới
            </h3>
            <p className="text-sm opacity-80 mb-4 text-[var(--nq-fg)]">
              Chuyển lịch từ «Đã đóng» về «Bản nháp» để nạp các ràng buộc mới và chạy Solver. Bắt buộc nhập lý do (sẽ ghi vào Audit log).
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase mb-1 text-[var(--nq-fg)]">
                  Lý do mở lại
                </label>
                <input
                  type="text"
                  placeholder="Ví dụ: Mở đợt xếp lịch tuần mới hoặc chỉnh sửa gấp..."
                  value={reopenReason}
                  onChange={(e) => setReopenReason(e.target.value)}
                  className="nq-input w-full"
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <Btn variant="ghost" onClick={() => setShowReopenModal(false)}>
                Huỷ
              </Btn>
              <Btn
                variant="primary"
                disabled={!reopenReason.trim() || busy === "reopen"}
                busy={busy === "reopen"}
                onClick={reopenWeek}
              >
                Xác nhận mở lại
              </Btn>
            </div>
          </div>
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
