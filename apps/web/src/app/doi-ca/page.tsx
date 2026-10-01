"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { getRole, getToken } from "../../lib/session";
import { caHumanLabel, nvLabel, nvTenHienThi, safeText, swapLabel, thuLabel, viError, viTriLabel } from "../../lib/present";
import { matchExact, matchSearch, uniqueSorted } from "../../lib/list-filters";
import { useOpsPickers } from "../../lib/ops-context";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  ConfirmDialog,
  Empty,
  Loading,
  OpsCard,
  PageActions,
  PageHeader,
  PagedList,
  StatusChip,
} from "../../ui/kit";
import { FilteredEmpty, ListToolbar } from "../../ui/list-filters";
import { ShiftSelect } from "../../ui/ops-pickers";
import { CopilotPane } from "../../ui/copilot/CopilotPane";
import { ShiftChangeLog } from "../roster/ShiftChangeLog";

type Swap = {
  id: string;
  a: string;
  b: string;
  ca_id: string;
  trang_thai: string;
  dong_y?: string[];
  tuan_id?: string;
  da_duyet_boi?: string;
  rui_ro?: RuiRo;
  la_nguoi_tham_gia?: boolean;
};

/** Phép ĐO rủi ro kẹt ca do server trả — không phải lời khuyên. */
type RuiRo = {
  tuan_id: string;
  ca_id: string;
  ca: { thu: string; gio: string; vi_tri: string };
  nguoi_nhuong_dang_trong_ca: boolean;
  nguoi_nhan: string;
  nguoi_nhan_dang_trung: Array<{ ca_id: string; thu: string; gio: string }>;
  co_the_nhan: boolean;
  ly_do_chan: string;
  can_quan_ly_duyet: boolean;
};

const LY_DO_CHAN_LABEL: Record<string, string> = {
  ca_khong_trong_phan_cong_cua_nguoi_nhuong:
    "Người nhường không còn trực ca này — phiếu không thực hiện được.",
  nguoi_nhan_dang_co_ca_trung_gio: "Người nhận đang có ca khác trùng giờ.",
};

type OpenShift = {
  id: string;
  schedule_run_id: string;
  tuan_iso: string;
  ca_id: string;
  status: string;
  deadline_at: string;
  claimed_by?: string | null;
  claimed_at?: string | null;
  escalated_at?: string | null;
};

const OPEN_SHIFT_STATUS: Record<string, string> = {
  open: "Đang chờ người nhận",
  claimed: "Đã có người nhận",
  resolved: "Đã xử lý",
};

function isoWeekMonday(week: string): Date | null {
  const match = /^(\d{4})-W(\d{2})$/.exec(week);
  if (!match) return null;
  const year = Number(match[1]);
  const weekNumber = Number(match[2]);
  const januaryFourth = new Date(year, 0, 4);
  const monday = new Date(januaryFourth);
  monday.setHours(0, 0, 0, 0);
  monday.setDate(januaryFourth.getDate() - ((januaryFourth.getDay() + 6) % 7) + (weekNumber - 1) * 7);
  return monday;
}

function openShiftDate(week: string, weekday?: string): string {
  const offsets: Record<string, number> = { T2: 0, T3: 1, T4: 2, T5: 3, T6: 4, T7: 5, CN: 6 };
  const monday = isoWeekMonday(week);
  const offset = weekday ? offsets[weekday] : undefined;
  if (!monday || offset === undefined) return "Ngày chưa xác định";
  monday.setDate(monday.getDate() + offset);
  return monday.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function validDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateTimeLabel(value?: string | null): string {
  return validDate(value)?.toLocaleString("vi-VN") ?? "Chưa có thời gian";
}

function currentISOWeek(): string {
  const now = new Date();
  const date = new Date(now);
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + 3 - ((date.getDay() + 6) % 7));
  const weekOne = new Date(date.getFullYear(), 0, 4);
  const week = 1 + Math.round(((date.getTime() - weekOne.getTime()) / 86400000 - 3 + ((weekOne.getDay() + 6) % 7)) / 7);
  return `${date.getFullYear()}-W${String(week).padStart(2, "0")}`;
}

function swapHaystack(it: Swap, personLabel: (id: string) => string): string {
  return [it.id, it.a, it.b, it.ca_id, swapLabel(it.trang_thai), personLabel(it.a), personLabel(it.b)].join(" ");
}

export default function DoiCaPage() {
  const [token, setToken] = useState("");
  const [items, setItems] = useState<Swap[]>([]);
  const [openShifts, setOpenShifts] = useState<OpenShift[]>([]);
  const [openShiftWeek, setOpenShiftWeek] = useState(currentISOWeek());
  const [openShiftLoading, setOpenShiftLoading] = useState(true);
  const [claimingShift, setClaimingShift] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [b, setB] = useState("");
  const [ca, setCa] = useState("");
  // Ca TÔI đang giữ trong tuần đang xem — để dropdown "Ca cần đổi" chỉ hiện
  // ca của chính mình, không phải toàn bộ 70 ca của quán.
  const [myShiftIds, setMyShiftIds] = useState<string[] | null>(null);

  useEffect(() => {
    if (!token) return;
    setMyShiftIds(null);
    apiGet<{ ca_ids?: string[] }>(`/api/v1/toi/lich?tuan=${encodeURIComponent(openShiftWeek)}`)
      .then((d) => setMyShiftIds(Array.isArray(d.ca_ids) ? d.ca_ids : []))
      // Lỗi tải thì KHÔNG lọc (tránh kẹt form); backend vẫn chặn phiếu sai.
      .catch(() => setMyShiftIds(null));
  }, [token, openShiftWeek]);

  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusF, setStatusF] = useState("all");
  const [personF, setPersonF] = useState("all");
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [laQuanLy, setLaQuanLy] = useState(false);
  const [xacNhanNhan, setXacNhanNhan] = useState<Swap | null>(null);
  const { data: pickers } = useOpsPickers(!!token);
  const meNv = pickers?.me_nv_id ?? null;
  const employeeMode = getRole() === "nhan_vien";

  // Người nhận: loại chính mình (tự đổi cho mình là vô nghĩa — backend cũng 422).
  // Giữ "Mọi người" = phiếu mở, ai nhanh tay nhận trước thì giữ chỗ.
  const recipientOptions = useMemo(
    () => (pickers?.nhan_vien ?? []).filter((n) => n.id !== meNv),
    [pickers, meNv],
  );
  const myShifts = useMemo(() => {
    const all = pickers?.ca ?? [];
    if (myShiftIds === null) return all;
    const mine = new Set(myShiftIds);
    return all.filter((c) => mine.has(c.id));
  }, [pickers, myShiftIds]);

  useEffect(() => {
    setToken(getToken());
    if (!getToken()) setLoading(false);
  }, []);

  const load = useCallback(() => {
    if (!getToken()) return;
    setLoading(true);
    apiGet<{ items: Swap[]; toi_la_quan_ly?: boolean }>("/api/v1/cho-doi-ca")
      .then((d) => {
        setItems((d.items ?? []).filter((x) => x && typeof x.id === "string"));
        setLaQuanLy(Boolean(d.toi_la_quan_ly));
        setError(null);
      })
      .catch((e) => setError(viError(e, { doing: "tải được chợ đổi ca" })))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  const loadOpenShifts = useCallback(() => {
    if (!getToken()) return;
    setOpenShiftLoading(true);
    apiGet<{ items: OpenShift[] }>(`/api/v1/open-shifts?tuan_iso=${encodeURIComponent(openShiftWeek)}`)
      .then((payload) => {
        setOpenShifts((payload.items ?? []).filter((item) => item && typeof item.id === "string"));
        setError(null);
      })
      .catch((e) => setError(viError(e, { doing: "tải ca đang cần người" })))
      .finally(() => setOpenShiftLoading(false));
  }, [openShiftWeek]);

  useEffect(() => {
    if (token) loadOpenShifts();
  }, [token, loadOpenShifts]);

  const statusOptions = useMemo(() => {
    const statuses = uniqueSorted(items.map((i) => i.trang_thai));
    return [{ value: "all", label: "Mọi trạng thái" }, ...statuses.map((s) => ({ value: s, label: swapLabel(s) }))];
  }, [items]);

  const personOptions = useMemo(() => {
    const people = uniqueSorted(items.flatMap((i) => [i.a, i.b]));
    return [
      { value: "all", label: "Mọi người" },
      ...people.map((p) => {
        const hit = pickers?.nhan_vien.find((x) => x.id === p);
        return { value: p, label: hit ? nvTenHienThi(hit.ten, p) : nvLabel(p) };
      }),
    ];
  }, [items, pickers]);

  // Trạng thái phiếu đã xong — mặc định ẩn để đỡ rác, bật toggle mới hiện.
  const DONG_TRANG_THAI = useMemo(() => new Set(["dong_y", "da_duyet", "tu_choi", "huy"]), []);
  const [showClosed, setShowClosed] = useState(false);

  // Server đã lọc theo người tham gia (nhân viên chỉ thấy phiếu của mình).
  // Ở đây loại phiếu đã xong khỏi danh sách đang mở.
  const available = useMemo(() => {
    return items.filter((it) => !DONG_TRANG_THAI.has(it.trang_thai));
  }, [items, DONG_TRANG_THAI]);
  const closedCount = items.length - available.length;

  const filtered = useMemo(() => {
    const nguon = showClosed ? items : available;
    return nguon.filter((it) => {
      if (!matchSearch(swapHaystack(it, personLabel), search)) return false;
      if (!matchExact(it.trang_thai, statusF)) return false;
      if (personF !== "all" && ![it.a, it.b].includes(personF)) return false;
      return true;
    });
  }, [showClosed, items, available, search, statusF, personF, pickers]);

  const filterActive = search.length > 0 || statusF !== "all" || personF !== "all";

  function clearFilters() {
    setSearch("");
    setStatusF("all");
    setPersonF("all");
  }

  const dayDu = meNv && b.trim() && ca.trim();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMsg(null);
    if (!dayDu) {
      setError("Chọn người nhận và ca rồi mới mở được lệnh đổi.");
      return;
    }
    setBusy(true);
    try {
      await apiSend("/api/v1/cho-doi-ca", { a: meNv, b: b.trim(), ca_id: ca.trim(), tuan: openShiftWeek });
      setB("");
      setMsg("Đã mở phiếu đổi ca.");
      load();
    } catch (e) {
      setError(
        viError(e, {
          doing: "mở được lệnh đổi ca",
          missing: "Ca hoặc người không hợp lệ. Chọn lại từ danh sách.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  async function dongY(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/v1/cho-doi-ca/${encodeURIComponent(id)}/dong-y`, {});
      setMsg("Đã ghi nhận đồng ý của bạn.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "ghi nhận đồng ý đổi ca" }));
    } finally {
      setBusy(false);
    }
  }

  async function tuChoi(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/v1/cho-doi-ca/${encodeURIComponent(id)}/tu-choi`, {});
      setMsg("Đã từ chối lệnh đổi ca.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "từ chối đổi ca" }));
    } finally {
      setBusy(false);
    }
  }

  /** Quản lý duyệt phiếu: đây mới là bước thực sự đổi phân công. */
  async function duyet(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/v1/cho-doi-ca/${encodeURIComponent(id)}/duyet`, {});
      setMsg("Đã duyệt và áp dụng phiếu đổi ca.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "duyệt phiếu đổi ca" }));
    } finally {
      setBusy(false);
    }
  }

  async function claimOpenShift(openShift: OpenShift) {
    setClaimingShift(openShift.id);
    setError(null);
    setMsg(null);
    try {
      await apiSend("/api/v1/open-shifts/claim", { open_shift_id: openShift.id });
      setMsg("Bạn đã nhận ca thành công. Quản lý sẽ thấy thay đổi khi chạy lại lịch.");
      loadOpenShifts();
    } catch (e) {
      setError(viError(e, { doing: "nhận ca mở" }));
    } finally {
      setClaimingShift(null);
    }
  }

  function caLabel(caId: string) {
    const hit = pickers?.ca.find((x) => x.id === caId);
    return caHumanLabel(hit, caId);
  }

  function openShiftSchedule(openShift: OpenShift) {
    const shift = pickers?.ca.find((item) => item.id === openShift.ca_id);
    return {
      date: openShiftDate(openShift.tuan_iso, shift?.thu),
      weekday: shift?.thu ? thuLabel(shift.thu) : "Chưa rõ thứ",
    };
  }

  function personLabel(id: string) {
    const hit = pickers?.nhan_vien.find((x) => x.id === id);
    return hit ? nvTenHienThi(hit.ten, id) : nvLabel(id);
  }

  if (!token) return <AuthGate />;

  return (
    <div className="nq-page nq-page--run">
      <PageHeader
        kicker="Điều phối nhân sự"
        title="Ca mở & đổi ca"
        meta="Ca thiếu do hệ thống mở và phiếu đổi giữa nhân viên là hai quy trình riêng."
      />
      <PageActions>
        <Btn variant="ghost" onClick={() => setCopilotOpen(true)}>
          Hỏi trợ lý vận hành
        </Btn>
      </PageActions>
      {error ? <Alert>{error}</Alert> : null}
      {msg ? <Alert kind="ok">{msg}</Alert> : null}

      <OpsCard eyebrow="Hệ thống tự động mở" title="Ca thiếu người" count={openShifts.length} countLabel="ca">
        <div className="mb-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(12rem,18rem)] sm:items-end">
          <p className="text-sm text-[var(--nq-dim)]">
            Các ca này phát sinh khi lịch tự động chưa đủ người. Đây không phải phiếu một nhân viên nhả ca cho người khác.
          </p>
          <label className="block text-sm text-[var(--nq-dim)]">
          Tuần cần xem
          <input
            type="week"
            value={openShiftWeek}
            onChange={(event) => { setOpenShiftWeek(event.target.value); setCa(""); }}
            className="mt-1 block min-h-10 w-full border border-[var(--nq-line)] bg-[var(--nq-panel)] px-3 text-[var(--nq-text)]"
          />
          </label>
        </div>
        {openShiftLoading ? <Loading skeleton="list">Đang tải ca thiếu người…</Loading> : null}
        {!openShiftLoading && openShifts.length === 0 ? (
          <Empty title="Không có ca thiếu người">Tuần này không còn ca tự động mở cần xử lý.</Empty>
        ) : null}
        {!openShiftLoading ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {openShifts.map((openShift) => {
              const schedule = openShiftSchedule(openShift);
              const deadline = validDate(openShift.deadline_at);
              const expired = deadline ? deadline.getTime() <= Date.now() : false;
              const escalated = Boolean(openShift.escalated_at);
              const claimed = openShift.status === "claimed";
              const actionable = employeeMode && openShift.status === "open" && !expired && !escalated;
              const statusTone = claimed ? "ok" : expired || escalated ? "danger" : "warn";
              return (
                <article key={openShift.id} className="nq-item min-w-0">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="nq-item-title">{caLabel(openShift.ca_id)}</p>
                      <p className="nq-item-sub">
                        Tuần {openShift.tuan_iso} · {schedule.weekday}, {schedule.date}
                      </p>
                    </div>
                    <StatusChip tone={statusTone}>
                      {escalated ? "Quá hạn · đã báo quản lý" : expired ? "Đã hết hạn" : OPEN_SHIFT_STATUS[openShift.status] ?? safeText(openShift.status, "Chưa rõ")}
                    </StatusChip>
                  </div>

                  <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-xs text-[var(--nq-dim)]">Hạn nhận ca</dt>
                      <dd className={expired ? "font-semibold text-[var(--nq-red)]" : "font-semibold"}>
                        {dateTimeLabel(openShift.deadline_at)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-[var(--nq-dim)]">Trạng thái xử lý</dt>
                      <dd className="font-semibold">
                        {claimed
                          ? `${openShift.claimed_by ? personLabel(openShift.claimed_by) : "Đã có nhân viên"} nhận lúc ${dateTimeLabel(openShift.claimed_at)}`
                          : escalated
                            ? `Chờ quản lý xử lý từ ${dateTimeLabel(openShift.escalated_at)}`
                            : expired
                              ? "Hết thời gian tự nhận, cần quản lý xử lý"
                              : "Đang trong thời gian nhân viên nhận ca"}
                      </dd>
                    </div>
                  </dl>

                  <div className="mt-3 border-t border-[var(--nq-line)] pt-3">
                    {actionable ? (
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <p className="text-xs text-[var(--nq-dim)]">
                          Bạn có thể nhận nếu đã xác nhận khả dụng tuần này và chưa được xếp vào ca.
                        </p>
                        <Btn
                          variant="primary"
                          busy={claimingShift === openShift.id}
                          disabled={claimingShift !== null}
                          onClick={() => void claimOpenShift(openShift)}
                        >
                          Nhận ca này
                        </Btn>
                      </div>
                    ) : (
                      <p className="text-xs font-semibold text-[var(--nq-dim)]">
                        {claimed
                          ? "Quản lý cần chốt nhân sự và chạy lại lịch để giải quyết ca thiếu."
                          : expired || escalated
                            ? "Không còn nhận trực tiếp. Quản lý cần phân công và xử lý trên lịch tuần."
                            : employeeMode
                              ? "Ca này hiện không thể nhận."
                              : "Chỉ tài khoản nhân viên mới có thể nhận ca đang mở."}
                      </p>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}
      </OpsCard>

      <OpsCard eyebrow="Nhân viên đổi với nhau · Khu vực 1" title="Mở phiếu đổi ca">
        <form onSubmit={onSubmit}>
          <p className="nq-muted mb-3">Người nhả ca: {meNv ? personLabel(meNv) : "Đang tải tài khoản…"} · Phiếu mở cho tuần {openShiftWeek}</p>
          <select className="nq-select mb-3" value={b} onChange={(e) => setB(e.target.value)} aria-label="Người nhận ca">
            <option value="">Chọn người nhận…</option>
            <option value="all">Mọi người — ai nhanh tay nhận trước</option>
            {recipientOptions.map((n) => (
              <option key={n.id} value={n.id}>{nvTenHienThi(n.ten, n.id)}</option>
            ))}
          </select>
          <ShiftSelect
            value={ca}
            onChange={setCa}
            label="Ca cần đổi (ca bạn đang giữ)"
            shifts={myShifts}
            hint={
              myShiftIds !== null && myShiftIds.length === 0
                ? "Tuần này bạn không giữ ca nào — không mở được phiếu."
                : "Chỉ hiện ca bạn đang giữ trong tuần trên. Chọn tên cụ thể = chỉ định, chọn Mọi người = ai nhận trước thì giữ chỗ."
            }
          />
          <Btn type="submit" variant="primary" disabled={busy}>
            {busy ? "Đang mở lệnh…" : "Mở lệnh đổi ca"}
          </Btn>
        </form>
      </OpsCard>

      <OpsCard eyebrow="Nhân viên đổi với nhau · Khu vực 2" title="Phiếu đổi đang mở" count={filtered.length} countLabel="phiếu">
        <ListToolbar
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder="Tìm người, ca, trạng thái…"
          status={statusF}
          onStatusChange={setStatusF}
          statusOptions={statusOptions}
          person={personF}
          onPersonChange={setPersonF}
          personOptions={personOptions}
          shown={filtered.length}
          total={showClosed ? items.length : available.length}
          filtered={filterActive}
        />
        {closedCount > 0 ? (
          <label className="mb-3 flex items-center gap-2 text-sm text-[var(--nq-dim)]">
            <input
              type="checkbox"
              checked={showClosed}
              onChange={(e) => setShowClosed(e.target.checked)}
            />
            Hiện cả phiếu đã xong ({closedCount})
          </label>
        ) : null}
        {loading ? <Loading skeleton="list">Đang tải lệnh đổi ca…</Loading> : null}
        {!loading && !error && filtered.length === 0 && (showClosed ? items.length : available.length) === 0 ? (
          <Empty title="Chưa có lệnh">Chưa có lệnh đổi ca nào đang mở.</Empty>
        ) : null}
        {!loading && filtered.length === 0 && (showClosed ? items.length : available.length) > 0 ? <FilteredEmpty onClear={clearFilters} /> : null}
        <div className="nq-list">
          <PagedList
            items={filtered}
            pageSize={10}
            renderItem={(it) => {
              const agreed = new Set(it.dong_y ?? []);
              const rr = it.rui_ro;
              const daDuyet = it.trang_thai === "da_duyet";
              // Phiếu hỏng: người nhường không còn giữ ca → duyệt cũng vô nghĩa.
              const hong = Boolean(rr && !rr.co_the_nhan && rr.ly_do_chan === "ca_khong_trong_phan_cong_cua_nguoi_nhuong");
              // Phiếu của tuần đã qua → ca đã trôi, không còn gì để nhận/duyệt.
              const hetHan = Boolean(it.tuan_id && it.tuan_id < openShiftWeek);
              // Đủ đồng ý = backend đã chốt pha đồng thuận (`dong_y`). Chỉ đếm
              // số lượt thì phiếu mở cho mọi người (1 lượt nhận là xong) kẹt mãi.
              const du = it.trang_thai === "dong_y" || agreed.size >= 2;
              const recipient = it.b === "all" || it.b === meNv;
              const canAgree = !hetHan && !hong && meNv && recipient && it.a !== meNv && !agreed.has(meNv) && !daDuyet;
              // Nói rõ đang chờ ai thay vì câu chung chung.
              const choAi = [it.a, it.b === "all" ? null : it.b].filter(
                (p): p is string => typeof p === "string" && p.length > 0 && !agreed.has(p),
              );
              const caChiTiet = rr?.ca?.gio
                ? `${thuLabel(rr.ca.thu)} · ${rr.ca.gio}${rr.ca.vi_tri ? ` · ${viTriLabel(rr.ca.vi_tri)}` : ""}`
                : caLabel(it.ca_id);
              return (
                <article key={it.id} className="nq-item">
                  <p className="nq-item-title">
                    {personLabel(it.a)} nhả · {it.b === "all" ? "Mọi người" : `${personLabel(it.b)} nhận`}
                  </p>
                  <p className="nq-item-sub">
                    <StatusChip tone={daDuyet ? "ok" : it.trang_thai === "dong_y" ? "info" : hetHan || hong ? "danger" : "warn"}>
                      {hetHan ? "Hết hạn" : swapLabel(it.trang_thai)}
                    </StatusChip>
                    {it.tuan_id ? ` · Tuần ${it.tuan_id}` : ""}
                    {` · ${caChiTiet}`}
                  </p>
                  {agreed.size > 0 && !daDuyet ? (
                    <p className="nq-item-sub text-xs mt-1">
                      Đã đồng ý: {[...agreed].map(personLabel).join(", ")}
                    </p>
                  ) : null}

                  {hetHan && !daDuyet ? (
                    <p className="nq-item-sub text-xs mt-1" data-rui-ro="het-han">
                      Tuần này đã qua — phiếu hết hiệu lực, không nhận/duyệt nữa.
                    </p>
                  ) : null}
                  {/* Cảnh báo kẹt ca — trả lời "họ có bị kẹt ở ca nào không". */}
                  {!hetHan && rr && !rr.co_the_nhan ? (
                    <div className="mt-2" data-rui-ro="chan">
                      <Alert kind="err">
                        {LY_DO_CHAN_LABEL[rr.ly_do_chan] ?? "Phiếu này chưa thực hiện được."}
                        {rr.nguoi_nhan_dang_trung.length > 0 ? (
                          <span className="block mt-1 font-mono text-xs">
                            Trùng:{" "}
                            {rr.nguoi_nhan_dang_trung
                              .map((c) => `${thuLabel(c.thu)} ${c.gio}`)
                              .join(", ")}
                          </span>
                        ) : null}
                      </Alert>
                    </div>
                  ) : null}

                  <div className="flex flex-wrap gap-2 mt-2">
                    {canAgree ? (
                      <>
                        <Btn variant="primary" busy={busy} onClick={() => setXacNhanNhan(it)}>
                          Tôi nhận ca
                        </Btn>
                        <Btn variant="danger" disabled={busy} onClick={() => void tuChoi(it.id)}>
                          Từ chối
                        </Btn>
                      </>
                    ) : null}
                    {/* Quản lý duyệt: chỉ hiện khi đã đủ hai bên đồng ý và chưa duyệt. */}
                    {laQuanLy && !daDuyet && !hetHan && !hong && du ? (
                      <Btn variant="primary" busy={busy} onClick={() => void duyet(it.id)}>
                        Duyệt &amp; áp dụng
                      </Btn>
                    ) : null}
                    {laQuanLy && !daDuyet && !hetHan && !hong && !du ? (
                      <span className="text-xs text-[var(--nq-dim)] self-center">
                        {choAi.length > 0 ? `Chờ: ${choAi.map(personLabel).join(", ")}` : "Chờ người nhận đầu tiên."}
                      </span>
                    ) : null}
                    {/* Phiếu hỏng / hết hạn: quản lý đóng để dọn chợ, khỏi tồn mãi. */}
                    {laQuanLy && !daDuyet && (hong || hetHan) ? (
                      <Btn variant="danger" disabled={busy} onClick={() => void tuChoi(it.id)}>
                        {hong ? "Đóng phiếu hỏng" : "Đóng phiếu hết hạn"}
                      </Btn>
                    ) : null}
                    {daDuyet ? (
                      <span className="text-xs text-[var(--nq-dim)] self-center">
                        Đã duyệt{it.da_duyet_boi ? ` bởi ${personLabel(it.da_duyet_boi)}` : ""} — phân công đã
                        đổi.
                      </span>
                    ) : null}
                  </div>
                </article>
              );
            }}
          />
        </div>
      </OpsCard>

      {/* Bằng chứng đổi ca THẬT: sau khi quản lý duyệt, phân công đổi ở đây. */}
      {!loading ? (
        <details className="nq-constraint-panel mb-4" data-panel="nhat-ky-doi-ca">
          <summary>Ai đổi ca với ai — lần thay đổi gần nhất</summary>
          <div className="mt-3">
            <ShiftChangeLog tuanIso={openShiftWeek} compact />
          </div>
        </details>
      ) : null}

      <OpsCard density="compact" eyebrow="Đổi ca giữa hai người" title="Phiếu được chốt thế nào?">
        <p className="mb-2 text-sm text-[var(--nq-dim)]">
          Người <strong>nhả</strong> mở phiếu cho một người nhận hoặc mọi người. Người nhận xem
          tên người nhả <em>và rủi ro kẹt ca</em> trước khi nhận.
        </p>
        <p className="mb-3 text-sm text-[var(--nq-dim)]">
          Lịch còn <strong>nháp</strong> thì chưa đổi ca được. Lịch đã <strong>công bố</strong> thì
          cần đủ hai bên đồng ý <em>và</em> một lượt <strong>quản lý duyệt</strong> mới thực sự đổi
          phân công — vì người khác đang chạy theo lịch đó.
        </p>
        <div className="flex flex-wrap gap-3">
          <BtnLink href="/inbox">Hộp thư duyệt →</BtnLink>
          <BtnLink href="/cong-bang" variant="ghost">Xem công bằng</BtnLink>
        </div>
      </OpsCard>

      <ConfirmDialog
        open={xacNhanNhan !== null}
        title="Nhận ca này?"
        confirmLabel="Tôi nhận ca"
        cancelLabel="Để sau"
        busy={busy}
        onCancel={() => setXacNhanNhan(null)}
        onConfirm={() => {
          const target = xacNhanNhan;
          setXacNhanNhan(null);
          if (target) void dongY(target.id);
        }}
        body={
          <div>
            <p>
              Bạn nhận ca do <strong>{xacNhanNhan ? personLabel(xacNhanNhan.a) : ""}</strong> nhả ra
              {xacNhanNhan?.tuan_id ? ` ở tuần ${xacNhanNhan.tuan_id}` : ""}
              {xacNhanNhan?.rui_ro?.ca?.gio ? ` (${xacNhanNhan.rui_ro.ca.gio})` : ""}.
            </p>
            <p className="mt-2 text-sm text-[var(--nq-dim)]">
              Đồng ý của bạn được ghi nhận ngay, nhưng phân công chỉ đổi sau khi quản lý duyệt.
            </p>
          </div>
        }
      />

      <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}
