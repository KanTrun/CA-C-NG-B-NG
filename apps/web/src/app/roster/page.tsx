"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Alert, AuthGate, Btn, Loading, Summary } from "../../ui/kit";
import { canEdit, clearSession, getNvId, getRole, getToken, isManager, lifeLabel } from "../../lib/session";
import { ApiError, apiGet, apiSend } from "../../lib/api";
import { matchSearch } from "../../lib/list-filters";
import { viError } from "../../lib/present";
import type { KhungGio } from "../../lib/roster";
import { shiftRowLabel } from "../../lib/roster";
import { FilteredEmpty, ListToolbar } from "../../ui/list-filters";
import { KhungConfigPanel } from "./KhungConfigPanel";
import { RosterGrid } from "./RosterGrid";
import { ShiftChangeLog } from "./ShiftChangeLog";
import { CopilotPane } from "../../ui/copilot/CopilotPane";
import { Icon } from "../../ui/icons";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Shift = {
  id: string;
  thu: string;
  khung: "sang" | "chieu" | "toi" | string;
  bat_dau?: string;
  ket_thuc?: string;
  vi_tri?: string;
  so_nguoi_toi_thieu?: number;
};

type NhanVien = {
  id: string;
  ten: string;
};

type UnconfirmedStaff = {
  id: string;
  ten: string;
  vai?: string;
  so_ca_du_kien: number;
  ca_ids?: string[];
};

type OnCallStaff = {
  id: string;
  ten: string;
  vai?: string;
};

type LichData = {
  nguon?: string;
  nguon_lich?: string;
  tuan_iso?: string;
  so_tuan?: number;
  danh_sach_tuan?: string[];
  trang_thai?: string;
  ca?: Shift[];
  nhan_vien?: NhanVien[];
  phan_cong?: Record<string, string[]>;
  khung_gio?: KhungGio;
  solver?: { ok?: boolean | null; status?: string | null; elapsed_s?: number | null };
  schedule_run?: {
    id: string;
    status: string;
    fingerprint: string;
    version: number;
  } | null;
  open_shifts?: OpenShift[];
  chua_xac_nhan?: UnconfirmedStaff[];
  du_bi?: OnCallStaff[];
  nv_status_map?: Record<string, string>;
  pins?: Array<{ ca_id: string; nv_id: string }>;
  kiem_tra?: {
    hard?: { passed?: boolean; gates?: string[]; violations?: string[] };
    vf?: { applies_to_solver?: boolean; message?: string; gates?: string[] };
    coverage?: { passed?: boolean; filled?: number; total?: number };
  };
};

type OpenShift = {
  id: string;
  schedule_run_id: string;
  tuan_iso: string;
  ca_id: string;
  status: string;
  deadline_at: string;
  claimed_by?: string | null;
};

type ScheduleNotification = {
  id: string;
  tieu_de: string;
  noi_dung: string;
  url: string;
  tuan_iso: string;
  da_xem?: number;
  created_at: string;
};

const KHUNG_TEN: Record<string, string> = {
  sang: "Ca sáng",
  chieu: "Ca chiều",
  toi: "Ca tối",
};

const VI_TRI_LABEL: Record<string, string> = {
  barista: "Pha chế",
  pha_che: "Pha chế",
  thu_ngan: "Thu ngân",
  phuc_vu: "Phục vụ",
  chay_ban: "Chạy bàn",
  kho: "Kho",
};

const TRANG_THAI_NEXT: Record<string, { label: string; next: string }> = {
  may_sinh: { label: "Chuyển sang nháp", next: "nhap" },
  nhap: { label: "Xếp lịch tự động", next: "dang_giai" },
  dang_giai: { label: "Đang xếp lịch", next: "" },
  cho_duyet: { label: "Duyệt và công bố", next: "da_duyet" },
  da_duyet: { label: "Mở lại để điều chỉnh", next: "nhap" },
  da_cong_bo: { label: "Mở lại để điều chỉnh", next: "nhap" },
  da_dong: { label: "Mở lại để điều chỉnh", next: "nhap" },
};

const LIFECYCLE_CONFLICTS: Record<string, string> = {
  authoritative_schedule_run_required: "Tuần này chưa có kết quả xếp lịch chính thức. Bấm Xếp lịch tự động trước khi duyệt.",
  stale_schedule_run: "Dữ liệu lịch bận hoặc ràng buộc đã thay đổi sau lần xếp gần nhất. Hãy xếp lịch tự động lại rồi duyệt.",
  schedule_has_unresolved_gaps: "Lịch còn ca thiếu người. Phân công hoặc xử lý các ca thiếu rồi chạy lại lịch.",
  invalid_schedule_run: "Kết quả xếp lịch chưa hợp lệ. Chạy lại lịch và xử lý các xung đột được hiển thị.",
  schedule_has_open_shifts: "Vẫn còn ca đang mở hoặc đã có người nhận nhưng chưa được quản lý xử lý. Hoàn tất các ca này rồi duyệt lại.",
};

function lifecycleError(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === "string") {
    return LIFECYCLE_CONFLICTS[error.detail] ?? viError(error, { doing: "cập nhật trạng thái lịch" });
  }
  return viError(error, { doing: "cập nhật trạng thái lịch" });
}

const TRANG_THAI_COLOR: Record<string, string> = {
  may_sinh: "warn",
  nhap: "default",
  cho_duyet: "warn",
  da_duyet: "ok",
  da_cong_bo: "ok",
  da_dong: "default",
};

function viTriLabel(vt?: string): string {
  if (!vt) return "Chung";
  return VI_TRI_LABEL[vt] ?? vt;
}

const DEFAULT_KHUNG_GIO: KhungGio = {
  sang: { bat_dau: "07:00", ket_thuc: "12:00" },
  chieu: { bat_dau: "12:00", ket_thuc: "17:00" },
  toi: { bat_dau: "17:00", ket_thuc: "22:00" },
};

function isoWeekToMonday(week: string): Date {
  const m = week.match(/^(\d{4})-W(\d{2})$/);
  if (!m) return new Date();
  const year = parseInt(m[1]);
  const wk = parseInt(m[2]);
  const jan4 = new Date(year, 0, 4);
  const mon = new Date(jan4);
  mon.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7) + (wk - 1) * 7);
  return mon;
}

function shiftWeek(week: string, delta: number): string {
  const mon = isoWeekToMonday(week);
  mon.setDate(mon.getDate() + delta * 7);
  const tmp = new Date(mon);
  tmp.setHours(0, 0, 0, 0);
  tmp.setDate(tmp.getDate() + 3 - ((tmp.getDay() + 6) % 7));
  const week1 = new Date(tmp.getFullYear(), 0, 4);
  const wkNum = 1 + Math.round(((tmp.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7);
  return `${tmp.getFullYear()}-W${String(wkNum).padStart(2, "0")}`;
}

function dayDate(monday: Date, offset: number): string {
  const d = new Date(monday);
  d.setDate(d.getDate() + offset);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function dayTitle(d: string): string {
  const m: Record<string, string> = {
    T2: "Thứ 2",
    T3: "Thứ 3",
    T4: "Thứ 4",
    T5: "Thứ 5",
    T6: "Thứ 6",
    T7: "Thứ 7",
    CN: "Chủ Nhật",
  };
  return m[d] ?? d;
}

function currentISOWeek(): string {
  const now = new Date();
  const tmp = new Date(now);
  tmp.setHours(0, 0, 0, 0);
  tmp.setDate(tmp.getDate() + 3 - ((tmp.getDay() + 6) % 7));
  const week1 = new Date(tmp.getFullYear(), 0, 4);
  const wk = 1 + Math.round(((tmp.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7);
  return `${tmp.getFullYear()}-W${String(wk).padStart(2, "0")}`;
}

export default function RosterPage() {
  const [token, setToken] = useState("");
  const [role, setRole] = useState("nhan_vien");
  const [currentNvId, setCurrentNvId] = useState("");
  const [viewMode, setViewMode] = useState<"my_shifts" | "all">("all");
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const [soTuan, setSoTuan] = useState<number>(1);
  const [baseWeek, setBaseWeek] = useState(currentISOWeek());
  const [activeWeekIndex, setActiveWeekIndex] = useState<number>(0);
  const [data, setData] = useState<LichData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pinBusy, setPinBusy] = useState(false);
  const [nvStatusBusy, setNvStatusBusy] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [gapBusy, setGapBusy] = useState<string | null>(null);
  const [gapStaff, setGapStaff] = useState<Record<string, string>>({});
  const [lifecycleMsg, setLifecycleMsg] = useState<string | null>(null);
  const [reopenOpen, setReopenOpen] = useState(false);
  const [reopenReason, setReopenReason] = useState("");
  const [icsBusy, setIcsBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [filterKhung, setFilterKhung] = useState("all");
  const [filterViTri, setFilterViTri] = useState("all");
  const [showAllUnconfirmed, setShowAllUnconfirmed] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [scheduleNotifications, setScheduleNotifications] = useState<ScheduleNotification[]>([]);
  const rosterDialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = getToken();
    const r = getRole();
    const nv = getNvId();
    if (t) setToken(t);
    if (r) {
      setRole(r);
      setViewMode(isManager(r) ? "all" : "my_shifts");
    }
    if (nv) setCurrentNvId(nv);
    const requestedWeek = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("tuan") ?? ""
      : "";
    if (/^\d{4}-W\d{2}$/.test(requestedWeek)) setBaseWeek(requestedWeek);
  }, []);

  const authHeader = useCallback(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  );

  const loadLich = useCallback(
    async (week: string, weeksCount: number) => {
      setLoading(true);
      setError(null);
      setLifecycleMsg(null);
      try {
        const res = await fetch(`${API}/api/v1/lich-tuan?tuan=${week}&so_tuan=${weeksCount}`, {
          headers: authHeader(),
        });
        if (!res.ok) {
          if (res.status === 401) {
            clearSession();
            setToken("");
            return;
          }
          if (res.status === 403) {
            setError("Bạn không có quyền quản lý để xem bảng phân công toàn quán. Vui lòng vào trang 'Lịch của tôi' (/toi) để xem ca làm cá nhân.");
            return;
          }
          throw new Error("fetch_failed");
        }
        setData((await res.json()) as LichData);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          clearSession();
          setToken("");
          return;
        }
        if (error instanceof ApiError && error.status === 403) {
          setError("Bạn không có quyền quản lý để xem bảng phân công toàn quán. Vui lòng vào trang 'Lịch của tôi' (/toi) để xem ca làm cá nhân.");
          return;
        }
        setError("Không tải được lịch tuần.");
      } finally {
        setLoading(false);
      }
    },
    [authHeader],
  );

  useEffect(() => {
    if (token) void loadLich(baseWeek, soTuan);
  }, [token, loadLich, baseWeek, soTuan]);

  useEffect(() => {
    if (!token || typeof window === "undefined") return;
    const onOpsChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ week_iso?: string }>).detail;
      if (!detail?.week_iso || detail.week_iso === baseWeek) void loadLich(baseWeek, soTuan);
    };
    window.addEventListener("nq:ops-changed", onOpsChanged);
    return () => window.removeEventListener("nq:ops-changed", onOpsChanged);
  }, [token, baseWeek, soTuan, loadLich]);

  useEffect(() => {
    if (!token) return;
    void apiGet<{ notifications: ScheduleNotification[] }>("/api/v1/lich/thong-bao")
      .then((payload) => setScheduleNotifications(payload.notifications ?? []))
      .catch(() => setScheduleNotifications([]));
  }, [token]);

  async function acknowledgeScheduleNotification(notification: ScheduleNotification) {
    setScheduleNotifications((items) => items.map((item) => item.id === notification.id ? { ...item, da_xem: 1 } : item));
    await apiSend(`/api/v1/lich/thong-bao/${notification.id}/ack`, {}, "POST").catch(() => undefined);
  }

  useEffect(() => {
    if (!selectedDay) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedDay(null);
    };
    document.body.style.overflow = "hidden";
    rosterDialogRef.current?.focus();
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [selectedDay]);

  async function handlePin(caId: string, nvId: string, ghim: boolean) {
    setPinBusy(true);
    try {
      const res = await fetch(`${API}/api/v1/lich-tuan/pin`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({
          ca_id: caId,
          nv_id: nvId,
          pinned: ghim,
          tuan_iso: currentDisplayWeek,
          xep_lai: true,
        }),
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => null) as {
          detail?: string | { reasons?: string[] };
        } | null;
        const detail = payload?.detail;
        const reason = typeof detail === "string"
          ? detail
          : detail?.reasons?.join(" ");
        throw new Error(reason || "pin_failed");
      }
      setLifecycleMsg(
        ghim
          ? "Đã ghim và xếp lại phần lịch còn lại. Ca ghim được giữ nguyên."
          : "Đã bỏ ghim và xếp lại lịch. Nhân viên có thể vẫn được máy xếp chọn.",
      );
      await loadLich(baseWeek, soTuan);
    } catch (e) {
      setError(
        e instanceof Error && e.message !== "pin_failed"
          ? `Không thể ghim: ${e.message}`
          : "Không cập nhật được ghim.",
      );
    } finally {
      setPinBusy(false);
    }
  }

  async function handleNvStatus(nvId: string, action: "xac_nhan" | "du_bi" | "bo_ca" | "dat_lai") {
    setNvStatusBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/v1/lich-tuan/nv-status`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ tuan_iso: currentDisplayWeek, nv_id: nvId, hanh_dong: action }),
      });
      if (!res.ok) throw new Error("update_failed");
      const actionLabels = {
        xac_nhan: "Đã xác nhận giữ ca",
        du_bi: "Đã chuyển sang dự bị On-call",
        bo_ca: "Đã gỡ ca tuần này",
        dat_lai: "Đã hoàn tác trạng thái",
      };
      const msg = nvId === "all"
        ? (action === "xac_nhan" ? "Đã xác nhận giữ ca cho toàn bộ nhân sự tuần này." : `Đã cập nhật trạng thái (${actionLabels[action]}) cho tất cả nhân sự.`)
        : `${actionLabels[action]} cho nhân sự ${nvName(nvId)}.`;
      setLifecycleMsg(msg);
      await loadLich(baseWeek, soTuan);
    } catch {
      setError("Không cập nhật được trạng thái nhân sự.");
    } finally {
      setNvStatusBusy(false);
    }
  }

  async function handleSelfConfirm() {
    setNvStatusBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/v1/lich-tuan/xac-nhan-lich`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ tuan_iso: currentDisplayWeek }),
      });
      if (!res.ok) throw new Error("confirm_failed");
      setLifecycleMsg("Bạn đã xác nhận lịch làm việc tuần này thành công!");
      await loadLich(baseWeek, soTuan);
    } catch {
      setError("Không thể xác nhận lịch làm việc.");
    } finally {
      setNvStatusBusy(false);
    }
  }

  async function taiLich(format: "ics" | "xlsx" | "pdf") {
    setIcsBusy(true);
    setError(null);
    try {
      const downloadArg = format === "ics" ? "&download=true" : "";
      const res = await fetch(`${API}/api/v1/lich/${format}?tuan=${currentDisplayWeek}${downloadArg}`, {
        headers: authHeader(),
      });
      if (!res.ok) throw new Error("export_failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `lich_tuan_${currentDisplayWeek}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setLifecycleMsg(`Đã tải lịch tuần ${currentDisplayWeek} dạng .${format}.`);
    } catch {
      setError(`Không tải được tệp .${format}. Kiểm tra trạng thái công bố và thử lại.`);
    } finally {
      setIcsBusy(false);
    }
  }

  async function handleLifecycle(nextState: string, weekIso: string) {
    if (!nextState) return;
    // Mở lại lịch đã duyệt/công bố/đóng cần lý do — dùng modal tuỳ chỉnh thay window.prompt.
    if (["da_duyet", "da_cong_bo", "da_dong"].includes(trangThai) && nextState === "nhap") {
      setReopenReason("");
      setReopenOpen(true);
      return;
    }
    await runLifecycle(nextState, weekIso, null);
  }

  async function runLifecycle(nextState: string, weekIso: string, reopenReason: string | null) {
    setLifecycleBusy(true);
    setLifecycleMsg(null);
    try {
      if (reopenReason) {
        await apiSend(
          "/api/v1/lich/lifecycle",
          { to: nextState, ly_do: reopenReason, tuan_iso: weekIso },
          "POST",
        );
      } else {
        await apiSend(
          "/api/v1/lich-tuan/lifecycle",
          { trang_thai: nextState, tuan_iso: weekIso },
          "PATCH",
        );
      }
      setLifecycleMsg(nextState === "da_duyet" ? "Đã duyệt, công bố lịch và gửi thông báo cho nhân viên." : "Đã cập nhật trạng thái lịch.");
      await loadLich(baseWeek, soTuan);
    } catch (e) {
      setError(lifecycleError(e));
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function confirmReopen() {
    const reason = reopenReason.trim();
    if (!reason) {
      setError("Vui lòng ghi lý do mở lại lịch để điều chỉnh.");
      return;
    }
    setReopenOpen(false);
    await runLifecycle("nhap", currentDisplayWeek, reason);
  }

  async function resolveGap(openShift: OpenShift) {
    const run = data?.schedule_run;
    const nvId = gapStaff[openShift.id] ?? openShift.claimed_by;
    if (!run || !nvId) {
      setError("Chọn nhân sự trước khi chạy lại ca thiếu.");
      return;
    }
    setGapBusy(openShift.id);
    setError(null);
    setLifecycleMsg(null);
    try {
      await apiSend("/api/v1/lich/resolve-gaps", {
        schedule_run_id: run.id,
        tuan_iso: openShift.tuan_iso,
        expected_fingerprint: run.fingerprint,
        idempotency_key: `roster:${run.id}:${openShift.ca_id}:${nvId}`,
        ca_id: openShift.ca_id,
        nv_id: nvId,
      });
      setLifecycleMsg("Đã ghim nhân sự và chạy lại lịch. Kiểm tra các ca còn thiếu trước khi duyệt.");
      await loadLich(baseWeek, soTuan);
    } catch (e) {
      setError(viError(e, { doing: "xử lý ca còn thiếu" }));
    } finally {
      setGapBusy(null);
    }
  }

  function navigateBlock(delta: number) {
    const next = shiftWeek(baseWeek, delta * soTuan);
    setBaseWeek(next);
    setActiveWeekIndex(0);
  }

  const shiftsEarly = data?.ca ?? [];
  const nhanVienEarly = data?.nhan_vien ?? [];

  const viTriOptions = useMemo(() => {
    const set = new Set<string>();
    for (const s of shiftsEarly) {
      if (s.vi_tri) set.add(s.vi_tri);
    }
    return [
      { value: "all", label: "Mọi vị trí" },
      ...[...set].sort().map((v) => ({ value: v, label: viTriLabel(v) })),
    ];
  }, [shiftsEarly]);

  const matchCell = useCallback(
    (assigned: string[], shift: { khung?: string; vi_tri?: string; thu?: string }) => {
      if (filterKhung !== "all" && shift.khung !== filterKhung) return false;
      if (filterViTri !== "all" && (shift.vi_tri ?? "") !== filterViTri) return false;
      if (!search.trim()) return true;
      const hay = [
        ...assigned.map((id) => nhanVienEarly.find((x) => x.id === id)?.ten ?? id),
        viTriLabel(shift.vi_tri),
        shift.khung,
        shift.thu,
      ].join(" ");
      return matchSearch(hay, search);
    },
    [filterKhung, filterViTri, search, nhanVienEarly],
  );

  const rosterStats = useMemo(() => {
    const phanCongEarly = data?.phan_cong ?? {};
    const cells = new Map<string, { assigned: Set<string>; required: number }>();
    for (const s of shiftsEarly) {
      const key = `${s.thu}|${s.khung}`;
      const cell = cells.get(key) ?? { assigned: new Set<string>(), required: 0 };
      for (const id of phanCongEarly[s.id] ?? []) cell.assigned.add(id);
      cell.required += Number(s.so_nguoi_toi_thieu ?? 1);
      cells.set(key, cell);
    }
    const values = [...cells.values()];
    return {
      slots: values.length,
      staffed: values.filter((cell) => cell.assigned.size >= cell.required).length,
      thin: values.filter((cell) => cell.assigned.size < cell.required).length,
    };
  }, [shiftsEarly, data?.phan_cong]);

  if (!token) return <AuthGate />;

  const canWrite = canEdit(role);
  const days = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
  const dayOffsets = [0, 1, 2, 3, 4, 5, 6];
  const shifts = data?.ca ?? [];
  const weekList = data?.danh_sach_tuan && data.danh_sach_tuan.length > 0
    ? data.danh_sach_tuan
    : [baseWeek];

  const currentDisplayWeek = weekList[activeWeekIndex] ?? baseWeek;
  const monday = isoWeekToMonday(currentDisplayWeek);
  const trangThai = data?.trang_thai ?? "nhap";
  const nextAction = TRANG_THAI_NEXT[trangThai];
  const khungGio = data?.khung_gio ?? DEFAULT_KHUNG_GIO;
  const phanCong = data?.phan_cong ?? {};
  const pinSet = new Set((data?.pins ?? []).map((pin) => `${pin.ca_id}|${pin.nv_id}`));

  const khungOptions = [
    { value: "all", label: "Mọi khung" },
    { value: "sang", label: "Ca sáng" },
    { value: "chieu", label: "Ca chiều" },
    { value: "toi", label: "Ca tối" },
  ];

  const filteredActive = filterKhung !== "all" || filterViTri !== "all" || search.trim().length > 0;

  const dayLabelRows = days.map((d, i) => ({
    title: dayTitle(d),
    date: dayDate(monday, dayOffsets[i]),
  }));

  const byDay: Record<string, Shift[]> = {};
  for (const d of days) byDay[d] = [];
  const offsetToDay: Record<number, string> = { 1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN" };

  for (const s of shifts) {
    const rawOffset = (s as unknown as { ngay_offset?: number }).ngay_offset;
    const dayKey = s.thu || (rawOffset ? offsetToDay[Number(rawOffset)] : "") || "T2";
    if (byDay[dayKey]) byDay[dayKey].push({ ...s, thu: dayKey });
  }

  /** Tên nhân sự theo id. KHÔNG bao giờ trả về mã thô (`nv_01`) cho người dùng:
   *  tầng API đã lọc tham chiếu chết, nhưng nếu vì lý do nào đó còn sót thì trả
   *  chuỗi rỗng để nơi gọi tự bỏ qua, thay vì in `nv_26` lên lịch. */
  function nvName(id: string): string {
    const found = (data?.nhan_vien ?? []).find((x) => x.id === id);
    if (found) return found.ten;
    return /^nv_\w+$/i.test(id) ? "" : id;
  }

  // Resolve employee ID from session (e.g. nv_03 for Minh, nv_01 for Lan...)
  const myEmployee = (data?.nhan_vien ?? []).find(
    (nv) =>
      nv.id === currentNvId ||
      nv.id === `nv_${currentNvId}` ||
      (currentNvId && nv.ten.toLowerCase().includes(currentNvId.toLowerCase()))
  );
  const targetNvId = myEmployee ? myEmployee.id : currentNvId || "";

  // Calculate shifts assigned to current employee
  const myAssignedDays: { day: string; offset: number; dateStr: string; shifts: Array<{ shift: Shift; coworkers: string[] }> }[] = [];
  let totalMyShifts = 0;

  days.forEach((d, i) => {
    const dayShifts = byDay[d] ?? [];
    const matched: Array<{ shift: Shift; coworkers: string[] }> = [];
    dayShifts.forEach((s) => {
      const assigned = data?.phan_cong?.[s.id] ?? [];
      if (assigned.includes(targetNvId)) {
        matched.push({ shift: s, coworkers: assigned.filter((id) => id !== targetNvId) });
      }
    });

    if (matched.length > 0) {
      totalMyShifts += matched.length;
      myAssignedDays.push({
        day: d,
        offset: dayOffsets[i],
        dateStr: dayDate(monday, dayOffsets[i]),
        shifts: matched,
      });
    }
  });


  return (
    <div className="nq-page nq-page--wide">
      <header className="mb-6 ops-animate-in">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
          <div>
            <p className="nq-kicker">Vận hành tuần</p>
            <h1 className="nq-page-title text-[var(--nq-accent)]">
              {viewMode === "my_shifts" ? "Lịch đi làm của tôi" : "Lịch toàn quán"}
            </h1>
            <Btn variant="ghost" onClick={() => setCopilotOpen(true)}>
              Hỏi trợ lý vận hành
            </Btn>
          </div>

          {/* Mode Switcher: My Shifts vs Full Roster */}
          <div className="flex items-center gap-1.5 p-1 bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] rounded-lg">
            <button
              type="button"
              onClick={() => setViewMode("my_shifts")}
              className={`px-3 py-1.5 text-xs font-bold rounded transition-all ${
                viewMode === "my_shifts"
                  ? "bg-[var(--nq-st-warn)] text-[var(--nq-accent-ink)] shadow"
                  : "text-[var(--nq-ink-muted)] hover:text-[var(--nq-ink)]"
              }`}
            >
              Lịch của tôi ({totalMyShifts} ca)
            </button>
            <button
              type="button"
              onClick={() => setViewMode("all")}
              className={`px-3 py-1.5 text-xs font-bold rounded transition-all ${
                viewMode === "all"
                  ? "bg-[var(--nq-st-warn)] text-[var(--nq-accent-ink)] shadow"
                  : "text-[var(--nq-ink-muted)] hover:text-[var(--nq-ink)]"
              }`}
            >
              Toàn quán
            </button>
          </div>
        </div>

        {/* Chu kỳ 2-4 tuần ẩn: dữ liệu 21 ca lặp mỗi tuần — hiển thị gây hiểu lầm.
            Mở lại khi backend có ca thật theo từng tuần. */}

        {/* Điều hướng mốc tuần */}
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            className="nq-btn-outline px-3 py-1 text-sm"
            onClick={() => navigateBlock(-1)}
            disabled={loading}
          >
            ← Trước
          </button>
          <span className="text-base font-bold text-[var(--nq-accent)] min-w-[150px] text-center">
            {dayDate(monday, 0)} — {dayDate(monday, 6)}
          </span>
          <button
            type="button"
            className="nq-btn-outline px-3 py-1 text-sm"
            onClick={() => navigateBlock(1)}
            disabled={loading}
          >
            Sau →
          </button>
          <button
            type="button"
            className="nq-btn-outline px-3 py-1 text-sm"
            onClick={() => {
              setBaseWeek(currentISOWeek());
              setActiveWeekIndex(0);
            }}
            disabled={loading || baseWeek === currentISOWeek()}
          >
            Tuần này
          </button>
          <span className="text-[var(--nq-dim)] font-mono text-xs">
            Tuần {currentDisplayWeek}
          </span>
        </div>
      </header>

      {scheduleNotifications.length > 0 && (
        <section className="nq-item mb-5" aria-label="Thông báo cập nhật lịch">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--nq-accent)]">Thông báo cập nhật lịch</h2>
            <span className="text-xs text-[var(--nq-dim)]">
              {scheduleNotifications.filter((item) => !item.da_xem).length} chưa xem
            </span>
          </div>
          <div className="space-y-2">
            {scheduleNotifications.slice(0, 3).map((notification) => (
              <div key={notification.id} className={`flex flex-wrap items-center justify-between gap-3 border-l-2 pl-3 ${notification.da_xem ? "border-[var(--nq-dim)] opacity-70" : "border-[var(--nq-accent)]"}`}>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{notification.tieu_de}</p>
                  <p className="text-xs text-[var(--nq-dim)]">{notification.noi_dung}</p>
                </div>
                <a
                  href={notification.url}
                  onClick={() => void acknowledgeScheduleNotification(notification)}
                  className="nq-btn-outline shrink-0 px-3 py-1 text-xs"
                >
                  Mở lịch {notification.tuan_iso}
                </a>
              </div>
            ))}
          </div>
        </section>
      )}

      {canWrite && (
        <section className="nq-workflow mb-4" aria-label="Quy trình lịch tuần">
          {[
            ["nhap", "1. Chuẩn bị lịch"],
            ["cho_duyet", "2. Rà soát và xử lý ca thiếu"],
            ["da_cong_bo", "3. Đã duyệt và công bố"],
          ].map(([state, label]) => (
            <span
              key={state}
              className={`nq-workflow-step ${trangThai === state ? "nq-workflow-step--active" : ""}`}
            >
              {label}
            </span>
          ))}
          <p className="nq-muted text-xs basis-full">
            Duyệt cuối sẽ tự công bố và gửi thông báo. Muốn sửa lịch đã công bố, quản lý phải mở lại và ghi rõ lý do.
          </p>
        </section>
      )}

      {/* Trạng thái & nút duyệt của quản lý */}
      {canWrite && (
        <div className="nq-item mb-6 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm text-[var(--nq-dim)]">Trạng thái lịch:</span>
            <span
              className={`nq-chip nq-chip--${
                TRANG_THAI_COLOR[trangThai] ?? "default"
              } font-mono text-xs`}
            >
              {lifeLabel(trangThai)}
            </span>
            {nextAction?.next && (
              <button
                type="button"
                className={`nq-btn px-3 py-1 text-sm ${trangThai === "cho_duyet" ? "nq-btn-primary" : ""}`}
                disabled={lifecycleBusy}
                /* Cảnh báo TRƯỚC khi bấm: duyệt cần một lần xếp lịch chính thức
                   (`schedule_runs`) khớp dữ liệu hiện tại. Không có thì API trả
                   409 — nhưng nói trước vẫn hơn để người dùng bấm rồi mới biết.
                   Không `disabled` để vẫn bấm được (đường duyệt hợp lệ khi có
                   run), chỉ đổi nhãn cho đúng việc sắp xảy ra. */
                title={
                  trangThai === "cho_duyet" && !data?.schedule_run
                    ? "Chưa có lần xếp lịch chính thức cho tuần này — bấm 'Xếp lịch tự động' trước."
                    : undefined
                }
                onClick={() => void handleLifecycle(nextAction.next, currentDisplayWeek)}
              >
                {lifecycleBusy ? "Đang lưu…" : nextAction.label}
              </button>
            )}
            <details className="relative">
              <summary className="nq-btn px-3 py-1 text-sm cursor-pointer list-none">
                {icsBusy ? "Đang xuất…" : "Xuất lịch"}
              </summary>
              <div className="absolute right-0 z-20 mt-2 min-w-48 rounded border border-[var(--nq-line)] bg-[var(--nq-bg)] p-2 shadow-xl">
                {(["ics", "xlsx", "pdf"] as const).map((format) => (
                  <button
                    key={format}
                    type="button"
                    disabled={icsBusy}
                    onClick={() => void taiLich(format)}
                    className="block w-full rounded px-3 py-2 text-left text-sm text-[var(--nq-ink)] hover:bg-[var(--nq-surface)]"
                  >
                    {format === "ics" ? "Lịch điện tử (.ics)" : format === "xlsx" ? "Excel (.xlsx)" : "PDF (.pdf)"}
                  </button>
                ))}
              </div>
            </details>
            {lifecycleMsg && (
              <span className="text-sm text-[var(--nq-ok)]">{lifecycleMsg}</span>
            )}
          </div>
          {data?.nguon_lich === "chua_xep" ? (
            <p className="text-xs text-[var(--nq-dim)] max-w-2xl">
              Lịch tuần <strong>chưa được xếp</strong> — máy xếp (CP-SAT) chưa chạy cho tuần này.
              Bấm <strong>{nextAction?.label ?? "Gửi duyệt"}</strong> để hệ thống xếp lịch tự động,
              rồi duyệt và ghim người vào từng ca.
            </p>
          ) : trangThai === "may_sinh" ? (
            <p className="text-xs text-[var(--nq-ink-muted)] max-w-2xl">
              Lịch do hệ thống tự xếp. Quản lý rà soát, chỉnh nhân sự nếu cần, rồi bấm <strong>Chuyển sang nháp</strong> để bắt đầu quy trình duyệt.
            </p>
          ) : null}
          {data?.solver?.status ? (
            <p className="font-mono text-2xs text-[var(--nq-dim)]">
              Nguồn: máy xếp {data.solver.status}
              {data.solver.elapsed_s != null ? ` · ${data.solver.elapsed_s}s` : ""}
            </p>
          ) : null}
        </div>
      )}

      {/* Cảnh báo nhân sự chưa chốt lịch (Dành cho Quản lý) */}
      {canWrite && (data?.chua_xac_nhan?.length ?? 0) > 0 && (
        <div className="mb-6 p-4 rounded-xl bg-[var(--nq-st-warn-soft)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] shadow-md space-y-3 ops-animate-in">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2 text-[var(--nq-st-warn-ink)] font-bold text-sm">
              <Icon name="warn" size={16} />
              <span>
                Phát hiện {data?.chua_xac_nhan?.length} nhân sự chưa xác nhận lịch tuần {currentDisplayWeek}
              </span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                disabled={nvStatusBusy}
                onClick={() => void handleNvStatus("all", "xac_nhan")}
                className="py-1.5 px-3 rounded bg-[var(--nq-st-ok)] hover:bg-[var(--nq-st-ok)] text-[var(--nq-accent-ink)] text-xs font-bold transition-all shadow flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                title="Xác nhận giữ ca cho toàn bộ nhân sự đang chờ"
              >
                ✓ Xác nhận giữ ca cho tất cả ({data?.chua_xac_nhan?.length} nhân sự)
              </button>
              {(data?.chua_xac_nhan?.length ?? 0) > 6 && (
                <button
                  type="button"
                  onClick={() => setShowAllUnconfirmed(!showAllUnconfirmed)}
                  /* Hover đổi NỀN sang vàng đặc (sáng) nên phải đổi LUÔN màu chữ
                     sang bản đậm — nếu giữ chữ vàng nhạt trên nền vàng thì chỉ
                     còn 1.28:1. Cặp nền/chữ phải đổi cùng nhau ở mọi trạng thái. */
                  className="py-1.5 px-3 rounded border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] bg-[var(--nq-st-warn-soft)] hover:bg-[var(--nq-st-warn)] text-[var(--nq-st-warn-ink)] hover:text-[var(--nq-st-warn-ink-strong)] text-xs font-semibold transition-all cursor-pointer"
                >
                  {showAllUnconfirmed ? "▲ Thu gọn bớt" : `▼ Xem tất cả (${data?.chua_xac_nhan?.length})`}
                </button>
              )}
            </div>
          </div>

          <p className="text-xs text-[var(--nq-ink-muted)] italic">
            Đã xếp dự thảo theo ca mẫu/lịch sử — Quản lý có thể bấm xác nhận giữ ca tất cả hoặc điều chỉnh từng người:
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {(showAllUnconfirmed ? data?.chua_xac_nhan : data?.chua_xac_nhan?.slice(0, 6))?.map((nv) => (
              <div
                key={nv.id}
                className="p-3 rounded-lg bg-[var(--nq-bg-elevated)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] flex flex-col justify-between gap-2.5 shadow-sm"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-sm text-[var(--nq-ink)]">{nv.ten}</span>
                    <span className="text-2xs font-mono px-2 py-0.5 rounded bg-[var(--nq-st-warn-soft)] text-[var(--nq-st-warn-ink)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))]">
                      {nv.so_ca_du_kien} ca dự kiến
                    </span>
                  </div>
                  <p className="text-2xs text-[var(--nq-ink-muted)] mt-1">
                    Chưa đăng ký ca hoặc chưa gửi lịch bận tuần này.
                  </p>
                </div>

                <div className="flex items-center gap-1.5 pt-2 border-t border-[var(--nq-line)]">
                  <button
                    type="button"
                    disabled={nvStatusBusy}
                    onClick={() => void handleNvStatus(nv.id, "xac_nhan")}
                    className="flex-1 py-1 px-2 rounded bg-[var(--nq-st-ok-soft)] hover:bg-[var(--nq-st-ok)] text-[var(--nq-st-ok-ink)] text-xs font-bold transition-colors disabled:opacity-50 inline-flex items-center justify-center gap-1"
                    title="Xác nhận nhân viên này đồng ý làm các ca đã xếp"
                  >
                    <Icon name="check" size={12} /> Giữ ca
                  </button>
                  <button
                    type="button"
                    disabled={nvStatusBusy}
                    onClick={() => void handleNvStatus(nv.id, "du_bi")}
                    className="flex-1 py-1 px-2 rounded bg-[var(--nq-st-warn-soft)] hover:bg-[var(--nq-st-warn)] text-[var(--nq-st-warn-ink)] text-xs font-bold transition-colors disabled:opacity-50 inline-flex items-center justify-center gap-1"
                    title="Tháo khỏi ca cố định, đưa vào danh sách On-Call sẵn sàng thay ca"
                  >
                    <Icon name="call" size={12} /> Dự bị
                  </button>
                  <button
                    type="button"
                    disabled={nvStatusBusy}
                    onClick={() => void handleNvStatus(nv.id, "bo_ca")}
                    /* Nền nghỉ là `--nq-surface` (TỐI) nên chữ phải SÁNG — dùng
                       `--nq-ink`. Trước đây chữ là `--nq-accent-ink` (gần đen)
                       nên trên nền tối chỉ đạt 1.03:1, tức là không đọc được.
                       Khi hover, nền chuyển sang đỏ và chữ đổi sang bản sáng
                       của đỏ; cả hai trạng thái đều đạt ngưỡng. */
                    className="flex-1 py-1 px-2 rounded bg-[var(--nq-surface)] hover:bg-[var(--nq-st-danger)] text-[var(--nq-ink)] hover:text-[var(--nq-ink-on-danger)] text-xs font-bold transition-colors disabled:opacity-50 inline-flex items-center justify-center gap-1"
                    title="Không xếp ca cho nhân viên này tuần này"
                  >
                    <Icon name="x-mark" size={12} /> Bỏ ca
                  </button>
                </div>
              </div>
            ))}
          </div>

          {!showAllUnconfirmed && (data?.chua_xac_nhan?.length ?? 0) > 6 && (
            <div className="text-center pt-1">
              <button
                type="button"
                onClick={() => setShowAllUnconfirmed(true)}
                className="text-xs text-[var(--nq-st-warn-ink)] hover:text-[var(--nq-st-warn-ink)] underline font-medium cursor-pointer"
              >
                ... và còn {(data?.chua_xac_nhan?.length ?? 0) - 6} nhân sự khác chưa chốt. Bấm để xem toàn bộ danh sách.
              </button>
            </div>
          )}
        </div>
      )}

      {/* Danh sách nhân sự Dự bị On-Call tuần này */}
      {canWrite && (data?.du_bi?.length ?? 0) > 0 && (
        <div className="mb-6 p-3 rounded-lg bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] flex items-center justify-between flex-wrap gap-2 ops-animate-in">
          <div className="flex items-center gap-2 flex-wrap">
            <Icon name="phone" size={16} />
            <span className="text-xs font-bold text-[var(--nq-ink)]">
              Nhân sự Trực dự bị (On-Call) tuần {currentDisplayWeek} ({data?.du_bi?.length}):
            </span>
            <div className="flex flex-wrap gap-1.5">
              {data?.du_bi?.map((nv) => (
                <span
                  key={nv.id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[var(--nq-surface)] border border-[var(--nq-line)] text-xs text-[var(--nq-st-warn-ink)] font-medium"
                >
                  {nv.ten}
                  <button
                    type="button"
                    disabled={nvStatusBusy}
                    onClick={() => void handleNvStatus(nv.id, "dat_lai")}
                    title="Hoàn tác đưa về chưa xác nhận"
                    className="text-[var(--nq-ink-muted)] hover:text-[var(--nq-st-danger-ink)] ml-0.5 font-bold"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
          <p className="text-2xs text-[var(--nq-ink-muted)]">
            Sẵn sàng gọi tăng cường khi có người báo ốm hoặc bận đột xuất.
          </p>
        </div>
      )}

      {error ? <Alert kind="err">{error}</Alert> : null}
      {loading ? <Loading skeleton="table" rows={3}>Đang tải lịch tuần…</Loading> : null}

      {/* Bằng chứng đổi ca: trả lời "ai bị đổi ca với ai" sau mỗi lần xếp lịch.
          Trước đây solver ghi đè phân công im lặng — người dùng thấy lịch khác đi
          mà không có gì giải thích. Panel này chỉ hiện khi CÓ thay đổi. */}
      {!loading ? (
        <details className="nq-constraint-panel mb-4" data-panel="nhat-ky-doi-ca">
          <summary>Ai đổi ca với ai — nhật ký thay đổi tuần {currentDisplayWeek}</summary>
          <div className="mt-3">
            <ShiftChangeLog tuanIso={currentDisplayWeek} />
          </div>
        </details>
      ) : null}

      {!loading && viewMode === "all" && (
        <details className="nq-constraint-panel mb-4">
          <summary>Ràng buộc & kiểm tra lần xếp này</summary>
          <div className="grid gap-4 md:grid-cols-2 mt-3">
            <div>
              <h3>6 ràng buộc cứng — bắt buộc đạt</h3>
              <p>Không trùng lịch học; đủ người và kỹ năng; không trùng ca; đủ thời gian nghỉ; không vượt giờ tuần; tôn trọng nghỉ đã duyệt.</p>
              <p className={data?.kiem_tra?.hard?.passed ? "text-[var(--nq-st-ok-ink)]" : "text-[var(--nq-st-warn-ink)]"}>
                Kết quả: {data?.kiem_tra?.hard?.passed ? "Đạt C01–C06" : "Chưa có lần kiểm tra đạt"}
              </p>
            </div>
            <div>
              <h3>5 ràng buộc mềm — dùng để tối ưu</h3>
              <p>Nguyện vọng; chia đều tối/cuối tuần; ca liền mạch; ổn định tuần trước; ghép người mới với người có kinh nghiệm.</p>
              <p>
                Phủ ca: {data?.kiem_tra?.coverage?.filled ?? 0}/{data?.kiem_tra?.coverage?.total ?? 21} ô.
              </p>
            </div>
          </div>
          <div className="mt-3 border-t border-[var(--nq-line)] pt-3 text-xs text-[var(--nq-ink-muted)]">
            <strong className="text-[var(--nq-ink)]">VF không phải ràng buộc CP-SAT.</strong>{" "}
            {data?.kiem_tra?.vf?.message ?? "VF-SCHEMA, TRACE, CONF, CONFLICT kiểm dữ liệu agent; VF-NUM kiểm lời giải thích; VF-RULE kiểm luật học."}
          </div>
        </details>
      )}

      {/* ========================================================================= */}
      {/* 1. CHẾ ĐỘ NHÂN VIÊN: CHỈ HIỆN NHỮNG NGÀY ĐI LÀM CỦA CÁ NHÂN             */}
      {/* ========================================================================= */}
      {!loading && viewMode === "my_shifts" && (
        <div className="space-y-4">
          {/* Employee self-confirmation banner */}
          {data?.nv_status_map?.[targetNvId] === "chua_xac_nhan" && totalMyShifts > 0 && (
            <div className="p-4 rounded-lg bg-[var(--nq-st-warn-soft)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] flex items-center justify-between flex-wrap gap-3">
              <div>
                <h4 className="text-sm font-bold text-[var(--nq-st-warn-ink)] flex items-center gap-1.5">
                  <Icon name="warn" size={16} />
                  Bạn chưa xác nhận lịch đi làm tuần này
                </h4>
                <p className="text-xs text-[var(--nq-ink)] mt-0.5">
                  Hệ thống đã xếp dự thảo <strong>{totalMyShifts} ca</strong> cho bạn. Bấm xác nhận bên cạnh để Quản lý chốt lịch chính thức.
                </p>
              </div>
              <button
                type="button"
                disabled={nvStatusBusy}
                onClick={() => void handleSelfConfirm()}
                className="px-4 py-2 rounded bg-[var(--nq-st-ok)] hover:bg-[var(--nq-st-ok)] text-[var(--nq-accent-ink)] text-xs font-bold shadow transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                {nvStatusBusy ? "Đang lưu…" : <><Icon name="check" size={14} /> Xác nhận đi làm các ca trên</>}
              </button>
            </div>
          )}

          {/* Summary Card */}
          <div className="p-4 rounded-lg bg-[var(--nq-st-ok-soft)] border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] flex items-center justify-between flex-wrap gap-3">
            <div>
              <h3 className="text-sm font-bold text-[var(--nq-st-ok-ink)]">
                Tuần {currentDisplayWeek} của bạn
              </h3>
              <p className="text-xs text-[var(--nq-ink)] mt-0.5">
                Bạn có <strong>{myAssignedDays.length} ngày đi làm</strong> với tổng cộng <strong>{totalMyShifts} ca làm việc</strong>.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setViewMode("all")}
              className="text-xs font-mono px-3 py-1.5 rounded bg-[var(--nq-st-ok-soft)] text-[var(--nq-st-ok-ink)] border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] hover:bg-[var(--nq-st-ok)]"
            >
              Xem lịch toàn quán →
            </button>
          </div>

          {/* List of Working Days */}
          {myAssignedDays.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {myAssignedDays.map((item) => (
                <div
                  key={item.day}
                  className="p-4 rounded-lg bg-[var(--nq-bg-elevated)] border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] shadow-sm hover:border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] transition-all space-y-3"
                >
                  <div className="flex justify-between items-center pb-2 border-b border-[var(--nq-line)]">
                    <span className="font-bold text-base text-[var(--nq-st-ok-ink)]">
                      {dayTitle(item.day)}
                    </span>
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-[var(--nq-surface)] text-[var(--nq-ink)]">
                      {item.dateStr}
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    {item.shifts.map(({ shift, coworkers }, sIdx) => (
                        <div key={sIdx} className="p-2.5 rounded bg-[var(--nq-bg)] border border-[var(--nq-line)] space-y-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-bold text-[var(--nq-ink)]">
                              {shiftRowLabel(shift, shift.khung ?? "", khungGio)}
                            </span>
                            <span className="text-2xs font-mono px-2 py-0.5 rounded bg-[var(--nq-st-ok-soft)] text-[var(--nq-st-ok-ink)] font-bold border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))]">
                              {viTriLabel(shift.vi_tri)}
                            </span>
                          </div>

                          {coworkers.length > 0 && (
                            <p className="text-2xs text-[var(--nq-ink-muted)]">
                              Cùng ca: {coworkers.map((id) => nvName(id)).join(", ")}
                            </p>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-8 text-center bg-[var(--nq-bg-elevated)] rounded-lg border border-[var(--nq-line)] space-y-2">
              <p className="text-[var(--nq-ink-muted)] text-sm">Tuần này bạn chưa có ca làm việc nào được phân công.</p>
              <button
                type="button"
                onClick={() => setViewMode("all")}
                className="text-xs font-bold text-[var(--nq-st-warn-ink)] hover:underline"
              >
                Nhấn vào đây để xem toàn bộ lịch quán
              </button>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. CHẾ ĐỘ QUẢN LÝ: HIỆN FULL 7 NGÀY & CLICK VÀO NGÀY ĐỂ XEM CHI TIẾT TỪNG CA */}
      {/* ========================================================================= */}
      {!loading && viewMode === "all" && shifts.length > 0 && (
        <div className="space-y-4">
          <Summary
            cells={[
              { n: rosterStats.slots, k: "Ô ca tuần" },
              { n: rosterStats.staffed, k: "Đã có người", tone: "ok" },
              { n: rosterStats.thin, k: "Thiếu định biên", tone: rosterStats.thin > 0 ? "warn" : "default" },
              { n: lifeLabel(trangThai), k: "Trạng thái lịch" },
            ]}
          />

          {canWrite && (data?.open_shifts?.length ?? 0) > 0 ? (
            <section className="border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] bg-[var(--nq-st-warn-soft)] p-4">
              <div className="mb-3">
                <h3 className="text-sm font-bold text-[var(--nq-st-warn-ink)]">Ca còn thiếu người</h3>
                <p className="mt-1 text-xs text-[var(--nq-ink-muted)]">
                  Lịch chưa thể duyệt khi còn ca mở. Chọn một nhân sự phù hợp để ghim và chạy lại lịch.
                </p>
              </div>
              <div className="space-y-2">
                {data?.open_shifts?.map((openShift) => {
                  const shift = shifts.find((item) => item.id === openShift.ca_id);
                  return (
                    <div key={openShift.id} className="grid gap-2 border-t border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] pt-3 sm:grid-cols-[1fr_minmax(12rem,18rem)_auto] sm:items-center">
                      <div>
                        <p className="text-sm font-semibold text-[var(--nq-ink)]">
                          {shift ? shiftRowLabel(shift, shift.khung, khungGio) : openShift.ca_id}
                        </p>
                        <p className="text-xs text-[var(--nq-ink-muted)]">Hạn nhận: {new Date(openShift.deadline_at).toLocaleString("vi-VN")}</p>
                      </div>
                      <select
                        aria-label={`Nhân sự cho ${openShift.ca_id}`}
                        value={gapStaff[openShift.id] ?? openShift.claimed_by ?? ""}
                        onChange={(event) => setGapStaff((current) => ({ ...current, [openShift.id]: event.target.value }))}
                        className="min-h-10 border border-[var(--nq-line)] bg-[var(--nq-bg)] px-3 text-sm text-[var(--nq-ink)]"
                      >
                        <option value="">Chọn nhân sự</option>
                        {data?.nhan_vien?.map((employee) => (
                          <option key={employee.id} value={employee.id}>{employee.ten}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={gapBusy !== null || !(gapStaff[openShift.id] ?? openShift.claimed_by) || !data?.schedule_run}
                        onClick={() => void resolveGap(openShift)}
                        className="min-h-10 bg-[var(--nq-st-warn)] px-4 text-xs font-bold text-[var(--nq-accent-ink)] hover:bg-[var(--nq-st-warn)] disabled:opacity-50"
                      >
                        {gapBusy === openShift.id ? "Đang chạy…" : openShift.claimed_by ? "Duyệt và chạy lại" : "Ghim và chạy lại"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>
          ) : null}

          {canWrite ? (
            <KhungConfigPanel
              template={khungGio}
              disabled={trangThai === "da_dong" || lifecycleBusy}
              onSaved={() => void loadLich(baseWeek, soTuan)}
            />
          ) : null}

          <ListToolbar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Tìm tên nhân viên, vị trí…"
            status={filterKhung}
            onStatusChange={setFilterKhung}
            statusOptions={khungOptions}
            statusLabel="Khung ca"
            person={filterViTri}
            onPersonChange={setFilterViTri}
            personOptions={viTriOptions}
            personLabel="Vị trí"
            shown={rosterStats.slots}
            total={rosterStats.slots}
            filtered={filteredActive}
          />

          <p className="nq-muted text-xs">
            Bấm <strong>tiêu đề ngày</strong> hoặc <strong>ô ca</strong> để mở chi tiết và ghim nhân sự.
          </p>

          <RosterGrid
            byDay={byDay}
            phanCong={phanCong}
            khungGio={khungGio}
            dayLabels={dayLabelRows}
            spotlightDay={selectedDay}
            filterKhung={filterKhung}
            filterViTri={filterViTri}
            searchNeedle={search}
            viTriLabel={viTriLabel}
            nvName={nvName}
            matchCell={matchCell}
            onSelectDay={setSelectedDay}
            nvStatusMap={data?.nv_status_map}
            pins={data?.pins}
          />

          {filteredActive && shifts.every((s) => !matchCell(phanCong[s.id] ?? [], s)) ? (
            <FilteredEmpty
              onClear={() => {
                setSearch("");
                setFilterKhung("all");
                setFilterViTri("all");
              }}
            />
          ) : null}
        </div>
      )}

      {selectedDay && typeof document !== "undefined" && createPortal(
        <div
          className="nq-roster-dialog-layer"
          onClick={() => setSelectedDay(null)}
        >
          <div
            ref={rosterDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="roster-day-title"
            tabIndex={-1}
            className="nq-roster-dialog-panel"
            onClick={(event) => event.stopPropagation()}
          >
            {/* Header — ngày dễ đọc + trạng thái lịch bằng lời */}
            <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--nq-line)] bg-[var(--nq-bg-elevated)] p-4 sm:p-6 sm:pb-4">
              <div>
                <h3 id="roster-day-title" className="text-lg font-bold text-[var(--nq-st-warn-ink)]">
                  {dayTitle(selectedDay)} · {dayDate(monday, dayOffsets[days.indexOf(selectedDay)])}
                </h3>
                <p className="text-xs text-[var(--nq-ink-muted)]">
                  Trạng thái lịch: <strong className="text-[var(--nq-ink)]">{lifeLabel(trangThai)}</strong>
                  {data?.nguon_lich === "chua_xep"
                    ? " — chưa chạy máy xếp, lịch đang trống"
                    : data?.solver?.status
                      ? ` — máy xếp đã chạy (${data.solver.status})`
                      : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedDay(null)}
                className="px-3 py-1 text-xs font-bold uppercase tracking-widest text-[var(--nq-ink-muted)] hover:text-[var(--nq-st-warn-ink)] inline-flex items-center gap-1"
              >
                Đóng <Icon name="close" size={14} />
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">

            {/* Kết quả thao tác hiện NGAY trong modal — không bao giờ bị che */}
            {error ? (
              <div className="p-3 rounded-lg bg-[var(--nq-st-danger-soft)] border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] text-[var(--nq-st-danger-ink)] text-sm">
                {error}
              </div>
            ) : null}
            {lifecycleMsg ? (
              <div className="p-3 rounded-lg bg-[var(--nq-st-ok-soft)] border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] text-[var(--nq-st-ok-ink)] text-sm">
                {lifecycleMsg}
              </div>
            ) : null}

            {/* Mỗi ca đúng 1 hàng: giờ → trạng thái lời → người (kèm ×) → nút thêm */}
            <div className="space-y-3">
              {(["sang", "chieu", "toi"] as const).map((khung) => {
                const shifts = (byDay[selectedDay] ?? []).filter((c) => c.khung === khung);
                return (
                  <div key={khung} className="space-y-3">
                    {shifts.length === 0 ? (
                      <div className="p-4 rounded-lg bg-[var(--nq-bg)] border border-[var(--nq-line)]">
                        <span className="font-bold text-sm text-[var(--nq-ink)]">{KHUNG_TEN[khung]}</span>
                        <span className="shrink-0 text-xs text-[var(--nq-ink-muted)] italic">
                          Không có ca này trong mẫu tuần
                        </span>
                      </div>
                    ) : shifts.map((shift) => {
                      const assigned = data?.phan_cong?.[shift.id] ?? [];
                      const can = shift.so_nguoi_toi_thieu ?? 2;
                      const soNguoi = assigned.length;
                      const khacCa = data?.nhan_vien?.filter((nv) => !assigned.includes(nv.id)) ?? [];
                      return (
                        <div key={shift.id} className="p-4 rounded-lg bg-[var(--nq-bg)] border border-[var(--nq-line)] space-y-3">
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="font-bold text-sm text-[var(--nq-ink)] truncate">
                                {shiftRowLabel(shift, khung, khungGio)}
                              </span>
                              <span className="shrink-0 text-2xs font-mono px-2 py-0.5 rounded bg-[var(--nq-surface)] text-[var(--nq-ink)] uppercase">
                                {viTriLabel(shift.vi_tri)}
                              </span>
                            </div>
                            {soNguoi >= can ? (
                              <span className="shrink-0 text-xs font-mono px-2 py-0.5 rounded bg-[var(--nq-st-ok-soft)] text-[var(--nq-st-ok-ink)] border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))]">Đủ {soNguoi}/{can} người</span>
                            ) : soNguoi > 0 ? (
                              <span className="shrink-0 text-xs font-mono px-2 py-0.5 rounded bg-[var(--nq-st-warn-soft)] text-[var(--nq-st-warn-ink)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))]">Thiếu {can - soNguoi} (cần {can})</span>
                            ) : (
                              <span className="shrink-0 text-xs font-mono px-2 py-0.5 rounded bg-[var(--nq-st-danger-soft)] text-[var(--nq-st-danger-ink)] border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))]">Chưa có ai (cần {can})</span>
                            )}
                          </div>

                          {assigned.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {assigned.map((nv_id) => (
                          <span
                            key={nv_id}
                            className="inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] text-xs text-[var(--nq-ink)] font-medium"
                          >
                            {nvName(nv_id)}
                            {pinSet.has(`${shift.id}|${nv_id}`) ? (
                              <span className="text-2xs text-[var(--nq-st-warn-ink)]">Đã ghim</span>
                            ) : null}
                            {data?.nv_status_map?.[nv_id] === "chua_xac_nhan" && (
                              <span
                                className="inline-flex items-center gap-1 text-2xs font-mono px-1.5 py-0.5 rounded bg-[var(--nq-st-warn)] text-[var(--nq-st-warn-ink)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))]"
                                title="Nhân viên chưa gửi lịch bận / xác nhận đi làm tuần này"
                              >
                                <Icon name="warn" size={10} /> Chưa chốt
                              </span>
                            )}
                            {canWrite && ["nhap", "cho_duyet"].includes(trangThai) ? (
                              <button
                                type="button"
                                disabled={pinBusy}
                                title={pinSet.has(`${shift.id}|${nv_id}`) ? "Bỏ cố định ca" : "Cố định người này ở ca"}
                                onClick={() => handlePin(
                                  shift.id,
                                  nv_id,
                                  !pinSet.has(`${shift.id}|${nv_id}`),
                                )}
                                className="rounded bg-[var(--nq-surface)] px-2 py-1 text-2xs text-[var(--nq-ink)] hover:text-[var(--nq-st-warn-ink)]"
                              >
                                {pinSet.has(`${shift.id}|${nv_id}`) ? "Bỏ ghim" : "Ghim"}
                              </button>
                            ) : null}
                          </span>
                        ))}
                      </div>
                    ) : null}

                        {canWrite && ["nhap", "cho_duyet"].includes(trangThai) ? (
                      <div className="pt-2 border-t border-[var(--nq-line)]">
                        <details className="group">
                          <summary className="cursor-pointer text-xs font-bold text-[var(--nq-st-warn-ink)] hover:text-[var(--nq-st-warn-ink)] list-none inline-flex items-center gap-1">
                            <Icon name="plus" size={14} /> Thêm người vào ca
                          </summary>
                          <div className="mt-2 flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
                            {khacCa.length === 0 ? (
                              <p className="text-xs text-[var(--nq-ink-muted)] italic">Mọi nhân viên đã ở trong ca này.</p>
                            ) : (
                              khacCa.map((nv) => (
                                <button
                                  key={nv.id}
                                  type="button"
                                  disabled={pinBusy}
                                  onClick={() => handlePin(shift.id, nv.id, true)}
                                  className="px-2.5 py-1 rounded-full bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] text-xs text-[var(--nq-ink)] hover:border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] hover:text-[var(--nq-st-warn-ink)] transition-colors disabled:opacity-50"
                                >
                                  + {nv.ten || nv.id}
                                </button>
                              ))
                            )}
                          </div>
                        </details>
                      </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>

            </div>

            {/* Footer: điều hướng ngày + 1 hành động lifecycle duy nhất */}
            <div className="flex shrink-0 items-center justify-between gap-2 border-t border-[var(--nq-line)] bg-[var(--nq-bg-elevated)] p-4 sm:px-6">
              <button
                type="button"
                onClick={() => {
                  const currentIdx = days.indexOf(selectedDay);
                  setSelectedDay(days[(currentIdx - 1 + days.length) % days.length]);
                }}
                className="px-3 py-1.5 text-xs font-bold rounded bg-[var(--nq-surface)] text-[var(--nq-ink)] hover:bg-[var(--nq-line)]"
              >
                ← {dayTitle(days[(days.indexOf(selectedDay) - 1 + days.length) % days.length])}
              </button>

              {nextAction?.next && canWrite ? (
                <button
                  type="button"
                  disabled={lifecycleBusy}
                  onClick={() => void handleLifecycle(nextAction.next, currentDisplayWeek)}
                  className="px-4 py-1.5 text-xs font-bold rounded bg-[var(--nq-st-warn)] hover:bg-[var(--nq-st-warn)] text-[var(--nq-accent-ink)] disabled:opacity-50"
                >
                  {nextAction.label}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setSelectedDay(null)}
                  className="px-4 py-1.5 text-xs font-bold rounded bg-[var(--nq-st-warn)] hover:bg-[var(--nq-st-warn)] text-[var(--nq-accent-ink)]"
                >
                  Đóng
                </button>
              )}

              <button
                type="button"
                onClick={() => {
                  const currentIdx = days.indexOf(selectedDay);
                  setSelectedDay(days[(currentIdx + 1) % days.length]);
                }}
                className="px-3 py-1.5 text-xs font-bold rounded bg-[var(--nq-surface)] text-[var(--nq-ink)] hover:bg-[var(--nq-line)]"
              >
                {dayTitle(days[(days.indexOf(selectedDay) + 1) % days.length])} →
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}

      {reopenOpen && typeof document !== "undefined" && createPortal(
        <div
          className="nq-roster-dialog-layer"
          onClick={() => setReopenOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="roster-reopen-title"
            tabIndex={-1}
            className="nq-roster-dialog-panel nq-reopen-panel"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--nq-line)] bg-[var(--nq-bg-elevated)] p-4 sm:p-6 sm:pb-4">
              <div>
                <h3 id="roster-reopen-title" className="text-lg font-bold text-[var(--nq-st-warn-ink)]">
                  Mở lại lịch để điều chỉnh
                </h3>
                <p className="text-xs text-[var(--nq-ink-muted)]">
                  Tuần {currentDisplayWeek} · {lifeLabel(trangThai)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setReopenOpen(false)}
                className="px-3 py-1 text-xs font-bold uppercase tracking-widest text-[var(--nq-ink-muted)] hover:text-[var(--nq-st-warn-ink)] inline-flex items-center gap-1"
              >
                Đóng <Icon name="close" size={14} />
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
              <p className="text-sm text-[var(--nq-ink)]">
                Lịch đã được duyệt/công bố. Để mở lại và chỉnh sửa, vui lòng ghi rõ lý do.
                Thao tác này sẽ được ghi lại trong nhật ký hệ thống.
              </p>
              <label className="block">
                <span className="mb-1.5 block text-xs font-bold uppercase tracking-wide text-[var(--nq-ink-muted)]">
                  Lý do mở lại lịch
                </span>
                <textarea
                  value={reopenReason}
                  onChange={(event) => setReopenReason(event.target.value)}
                  rows={3}
                  autoFocus
                  placeholder="VD: Có nhân viên xin nghỉ, cần sắp xếp lại ca…"
                  className="w-full rounded-lg border border-[var(--nq-line)] bg-[var(--nq-bg)] p-3 text-sm text-[var(--nq-ink)] placeholder:text-[var(--nq-ink-muted)] focus:border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] focus:outline-none"
                />
              </label>
            </div>

            <div className="flex shrink-0 items-center justify-end gap-2 border-t border-[var(--nq-line)] bg-[var(--nq-bg-elevated)] p-4 sm:px-6">
              <button
                type="button"
                onClick={() => setReopenOpen(false)}
                className="px-4 py-1.5 text-xs font-bold rounded bg-[var(--nq-surface)] text-[var(--nq-ink)] hover:bg-[var(--nq-line)]"
              >
                Huỷ
              </button>
              <button
                type="button"
                disabled={lifecycleBusy || !reopenReason.trim()}
                onClick={() => void confirmReopen()}
                className="px-4 py-1.5 text-xs font-bold rounded bg-[var(--nq-st-warn)] hover:bg-[var(--nq-st-warn)] text-[var(--nq-accent-ink)] disabled:opacity-50"
              >
                {lifecycleBusy ? "Đang lưu…" : "Mở lại lịch"}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}

      <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}

