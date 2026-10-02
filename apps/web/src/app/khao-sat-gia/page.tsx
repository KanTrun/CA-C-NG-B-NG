"use client";

/**
 * `/khao-sat-gia` — Khảo sát giá & định vị thị trường theo bán kính.
 *
 * Plan `260913-1455-khao-sat-gia-fb-online-dinein-substitutes` mục 6. Bốn màn hình
 * theo đúng thứ tự luồng người dùng: nhập liệu → tiến trình → review thủ công →
 * dashboard kết quả.
 *
 * Ba ràng buộc không được "làm gọn":
 *  - ADR-008: màn hình review là ĐIỂM DỪNG THẬT. Job đứng ở `needs_review` cho tới
 *    khi người dùng gửi xác nhận; không có đường nào tự động duyệt thay.
 *  - Mục 5.2: `Idempotency-Key` sinh MỘT lần cho mỗi ý định khảo sát và được DÙNG
 *    LẠI khi bấm lại — mỗi job tốn chi phí proxy + Vision thật, gửi trùng là đốt tiền.
 *  - Mục 6.2: `sample_size` cạnh mọi con số, Sweet Spot luôn là khoảng, không tô
 *    đỏ/xanh nhị phân.
 *
 * Plan mục 6.1 có nhắc "autocomplete Google Places". Repo chưa có khoá Places API
 * (không có trong `docs/THIRD_PARTY.md`), nên trang dùng toạ độ + nút lấy vị trí
 * hiện tại của trình duyệt thay vì gọi một dịch vụ chưa được cấp phép.
 */

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, apiGet, apiSend, apiSendHeaders } from "../../lib/api";
import {
  danhMucLabel,
  dinhViLabel,
  formatLuc,
  giaVnd,
  kenhGiaLabel,
  khaoSatLoiLabel,
  khaoSatTrangThaiLabel,
  loaiKhuVucLabel,
  lyDoReviewLabel,
  safeNumber,
  safeText,
  viError,
} from "../../lib/present";
import { getToken, isManager } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  Empty,
  Field,
  Input,
  Loading,
  NextSteps,
  OpsCard,
  PageHeader,
  ProgressBar,
  Select,
  Stat,
  StatGrid,
  StatusChip,
  TechnicalDrawer,
} from "../../ui/kit";
import { GiaGauge, PhanViBars, type HangPhanVi } from "../../ui/khao-sat-gia/bieu-do-gia";

/* ── Kiểu dữ liệu khớp `ca_contracts.catchment_survey_v2` ── */

type StoreProfile = {
  ten_quan?: string;
  dia_chi?: string;
  dia_chi_chi_tiet?: string;
  phuong_xa?: string;
  quan_huyen?: string;
  tinh?: string;
  thanh_pho?: string;
  toa_do_lat?: string;
  toa_do_lon?: string;
  lat?: number | null;
  lon?: number | null;
};

type StoreLocationInfo = {
  tenQuan: string;
  diaChi: string;
  latitude: string;
  longitude: string;
  nguon: "gps" | "dia_chi";
};

type Progress = { step: number; total: number; label: string };

type PendingReview = {
  store_id: string;
  store_name?: string;
  image_url?: string;
  name?: string;
  raw_text?: string;
  reason?: string;
};

type JobStatus = {
  job_id: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  error_code?: string | null;
  error_message?: string | null;
  stores_flagged_for_review?: string[];
  pending_review?: PendingReview[];
  reviewed_by?: string | null;
  progress?: Progress;
};

type PhanVi = {
  p25: number;
  p50: number;
  p75: number;
  sample_size: number;
  insufficient_data: boolean;
};

type NhomThayThe = { category_name: string; stats: PhanVi };

type SoSanh = {
  core_category: string;
  positioning_tier: string;
  core_stats: PhanVi;
  substitutes: NhomThayThe[];
  ambi: number;
  sweet_spot_low_display: number;
  sweet_spot_high_display: number;
  min_viable_price?: number | null;
  cost_plus_warning: boolean;
};

type KetQua = {
  job_id: string;
  status: string;
  online_stats?: PhanVi | null;
  dinein_stats?: PhanVi | null;
  substitute_comparison?: SoSanh | null;
  area_context?: { area_type?: string | null; competitive_intensity?: number } | null;
  survey_captured_at: string;
  generated_at: string;
};

type Envelope<T> = { ok: boolean; data: T };

/* ── Hằng số hiển thị ── */

/** Preset bán kính theo mật độ đô thị — `config/khao-sat-gia-tham-so.yaml`. */
const RADIUS_PRESETS: Array<{ ma: string; nhan: string; moTa: string; dineIn: number; delivery: number }> = [
  { ma: "dense_urban", nhan: "Trung tâm dày đặc", moTa: "Quận lõi, quán san sát", dineIn: 1, delivery: 3 },
  { ma: "suburban", nhan: "Vùng ven", moTa: "Mật độ quán vừa phải", dineIn: 2, delivery: 7 },
  { ma: "rural", nhan: "Ngoại thành", moTa: "Quán thưa, khách đi xa", dineIn: 3, delivery: 10 },
];

const DINH_VI_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Để hệ thống gợi ý theo quán lân cận" },
  { value: "street_food", label: "Bình dân / vỉa hè" },
  { value: "casual_dine_in", label: "Quán ngồi thoải mái" },
  { value: "branded_chain", label: "Chuỗi thương hiệu" },
];

const KENH_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "hybrid", label: "Cả hai kênh — đối chiếu đầy đủ nhất" },
  { value: "delivery_platform", label: "Chỉ kênh giao hàng" },
  { value: "dine_in_vision", label: "Chỉ quán tại chỗ (đọc ảnh thực đơn)" },
];

const DANH_MUC_GOI_Y = [
  "cơm tấm",
  "cơm sườn",
  "phở bò",
  "bún bò huế",
  "bún thịt nướng",
  "hủ tiếu",
  "bánh mì",
  "cà phê",
  "trà sữa",
];

const DISCLAIMER =
  "Đây là mức giá thị trường chấp nhận, không phải là mức giá đảm bảo có lời. Vui lòng đối chiếu với giá vốn thực tế của quán trước khi quyết định.";

const COST_PLUS_CANH_BAO =
  "Vùng giá thị trường thấp hơn ngưỡng có lợi tối thiểu của bạn — cân nhắc giảm giá vốn, tăng khẩu phần cảm nhận, hoặc định vị lại phân khúc.";

const POLL_MS = 3000;

/** Trạng thái job còn đang chạy — phải tiếp tục poll (khớp `_DANG_CHAY` ở API). */
const DANG_CHAY = new Set([
  "queued",
  "scraping_online",
  "scraping_dinein",
  "ocr_processing",
  "aggregating",
]);

type ManHinh = "nhap" | "chay" | "review" | "ket-qua";

type FormState = {
  latitude: string;
  longitude: string;
  coreCategory: string;
  positioningTier: string;
  channelMode: string;
  dineInKm: string;
  deliveryKm: string;
  minReviewCount: string;
  minRating: string;
  cogs: string;
  giaQuan: string;
};

const FORM_MAC_DINH: FormState = {
  latitude: "10.7769",
  longitude: "106.7009",
  coreCategory: "cơm tấm",
  positioningTier: "",
  channelMode: "hybrid",
  dineInKm: "1",
  deliveryKm: "5",
  minReviewCount: "50",
  minRating: "4.2",
  cogs: "",
  giaQuan: "",
};

type ReviewRow = {
  storeId: string;
  tenMon: string;
  giaGoc: string;
  giaKhuyenMai: string;
  rejected: boolean;
};

/** Số nguyên không âm từ ô input; chuỗi rỗng/rác → `null` (không phải 0). */
function soNguyen(raw: string): number | null {
  const text = raw.trim();
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : null;
}

/** Số thực từ ô input; chuỗi rỗng/rác → `null`. */
function soThuc(raw: string): number | null {
  const text = raw.trim();
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

/**
 * Lỗi khảo sát → câu tiếng Việt.
 *
 * Ưu tiên `detail.code` vì plan mục 5.3 định nghĩa taxonomy riêng: 422 ở đây là
 * "thiếu mẫu thị trường" chứ không phải "nhập sai ô", và `viError()` gộp cả hai
 * thành một câu nên người dùng sẽ đi sửa nhầm chỗ.
 */
function loiKhaoSat(err: unknown, doing: string): string {
  if (err instanceof ApiError) {
    const detail = err.detail as { code?: unknown } | undefined;
    const code = detail && typeof detail === "object" ? detail.code : undefined;
    if (typeof code === "string" && code) return khaoSatLoiLabel(code);
  }
  return viError(err, { doing });
}

export default function KhaoSatGiaPage() {
  const [token, setToken] = useState("");
  const [form, setForm] = useState<FormState>(FORM_MAC_DINH);
  const [manHinh, setManHinh] = useState<ManHinh>("nhap");
  const [jobId, setJobId] = useState("");
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [ketQua, setKetQua] = useState<KetQua | null>(null);
  const [reviewRows, setReviewRows] = useState<ReviewRow[]>([]);
  const [approveAll, setApproveAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [storeLocation, setStoreLocation] = useState<StoreLocationInfo | null>(null);
  const [loadingLocation, setLoadingLocation] = useState(false);
  const [tuyChinhToaDo, setTuyChinhToaDo] = useState(false);

  /**
   * Khoá idempotency cho MỘT ý định khảo sát. Sinh khi bấm "Khảo sát", giữ nguyên
   * qua các lần bấm lại để máy chủ trả đúng job cũ thay vì tạo job mới.
   */
  const idemKeyRef = useRef<string>("");

  useEffect(() => setToken(getToken()), []);

  const manager = useMemo(() => isManager(), [token]);

  /**
   * Tự động lấy địa chỉ và toạ độ quán đã cấu hình sẵn (/cau-hinh-quan).
   * Ưu tiên toạ độ GPS nếu quán đã lưu; nếu chỉ có địa chỉ chữ thì lấy toạ độ giải mã;
   * nếu hoàn toàn chưa cấu hình thì hiển thị cảnh báo và cho phép nhập thủ công / lấy GPS.
   */
  useEffect(() => {
    if (!token || !manager) return;
    let active = true;
    setLoadingLocation(true);

    async function docViTriQuan() {
      try {
        const profile = await apiGet<StoreProfile>("/api/v1/store/profile").catch(() => null);
        if (!active) return;

        const tenQuan = profile?.ten_quan?.trim() || "";
        const diaChi =
          profile?.dia_chi?.trim() ||
          [profile?.dia_chi_chi_tiet, profile?.phuong_xa, profile?.quan_huyen, profile?.tinh]
            .filter(Boolean)
            .map((s) => String(s).trim())
            .join(", ");

        const latGps = profile?.lat != null ? profile.lat : (profile?.toa_do_lat ? Number(profile.toa_do_lat) : null);
        const lonGps = profile?.lon != null ? profile.lon : (profile?.toa_do_lon ? Number(profile.toa_do_lon) : null);

        // 1. Quán đã có toạ độ GPS hợp lệ trong cấu hình
        if (latGps != null && lonGps != null && !isNaN(latGps) && !isNaN(lonGps) && latGps !== 0) {
          const latStr = latGps.toFixed(6);
          const lonStr = lonGps.toFixed(6);
          const loc: StoreLocationInfo = {
            tenQuan,
            diaChi: diaChi || "Vị trí GPS đã lưu",
            latitude: latStr,
            longitude: lonStr,
            nguon: "gps",
          };
          setStoreLocation(loc);
          setForm((f) => ({ ...f, latitude: latStr, longitude: lonStr }));
          setLoadingLocation(false);
          return;
        }

        // 2. Quán có địa chỉ nhưng chưa lấy GPS -> giải mã toạ độ qua API địa lý / thời tiết
        if (diaChi) {
          const geoRes = await apiGet<{ found?: boolean; lat?: number; lon?: number }>(
            `/api/v1/geo/geocode?address=${encodeURIComponent(diaChi)}`
          ).catch(() => null);

          let latVal = geoRes?.found && geoRes?.lat != null ? geoRes.lat : null;
          let lonVal = geoRes?.found && geoRes?.lon != null ? geoRes.lon : null;

          if (latVal == null || lonVal == null) {
            const thoiTiet = await apiGet<{
              vi_tri?: { lat?: number; lon?: number; thanh_pho?: string; tinh?: string };
            }>("/api/v1/thoi-tiet/hom-nay").catch(() => null);
            if (thoiTiet?.vi_tri?.lat != null && thoiTiet?.vi_tri?.lon != null) {
              latVal = thoiTiet.vi_tri.lat;
              lonVal = thoiTiet.vi_tri.lon;
            }
          }

          if (active && latVal != null && lonVal != null) {
            const latStr = Number(latVal).toFixed(6);
            const lonStr = Number(lonVal).toFixed(6);
            const loc: StoreLocationInfo = {
              tenQuan,
              diaChi,
              latitude: latStr,
              longitude: lonStr,
              nguon: "dia_chi",
            };
            setStoreLocation(loc);
            setForm((f) => ({ ...f, latitude: latStr, longitude: lonStr }));
            setLoadingLocation(false);
            return;
          }
        }

        // 3. Quán chưa cấu hình địa chỉ / toạ độ
        setStoreLocation(null);
        setTuyChinhToaDo(true);
      } catch {
        setStoreLocation(null);
        setTuyChinhToaDo(true);
      } finally {
        if (active) setLoadingLocation(false);
      }
    }

    void docViTriQuan();
    return () => {
      active = false;
    };
  }, [token, manager]);

  function khoiPhucViTriQuan() {
    if (storeLocation) {
      set("latitude", storeLocation.latitude);
      set("longitude", storeLocation.longitude);
      setMsg("Đã khôi phục toạ độ theo địa chỉ quán đã cấu hình.");
    }
  }

  /**
   * Sửa form = ý định mới, nên huỷ khoá idempotency cũ. Giữ khoá cũ thì máy chủ
   * sẽ trả lại đúng job đã tạo với THAM SỐ CŨ (plan mục 5.2) — người dùng tưởng
   * đã khảo sát bán kính mới nhưng nhận kết quả của lần trước.
   */
  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    idemKeyRef.current = "";
    setForm((f) => ({ ...f, [key]: value }));
  }

  /* ── Đọc trạng thái job ── */

  const docTrangThai = useCallback(async (id: string): Promise<JobStatus | null> => {
    const res = await apiGet<Envelope<JobStatus>>(`/api/v1/market/catchment-survey/${id}`);
    return res.data;
  }, []);


  const docKetQua = useCallback(async (id: string): Promise<void> => {
    const res = await apiGet<Envelope<KetQua>>(`/api/v1/market/catchment-survey/${id}/result`);
    setKetQua(res.data);
    setManHinh("ket-qua");
  }, []);

  /** Đưa job về đúng màn hình theo trạng thái hiện tại. */
  const dongBoManHinh = useCallback(
    async (id: string, job: JobStatus): Promise<void> => {
      setStatus(job);
      if (job.status === "needs_review") {
        const pending = job.pending_review ?? [];
        setReviewRows(
          pending.map((p) => ({
            storeId: p.store_id,
            tenMon: p.name ?? "",
            giaGoc: "",
            giaKhuyenMai: "",
            rejected: false,
          })),
        );
        setApproveAll(false);
        setManHinh("review");
        return;
      }
      if (job.status === "completed") {
        await docKetQua(id);
        return;
      }
      if (job.status === "failed") {
        setManHinh("nhap");
        setError(khaoSatLoiLabel(job.error_code, "Khảo sát không chạy được. Thử lại sau ít phút."));
        return;
      }
      setManHinh("chay");
    },
    [docKetQua],
  );

  /* ── Poll khi job đang chạy ── */

  const [pollRetryTrigger, setPollRetryTrigger] = useState(0);

  useEffect(() => {
    if (!token || manHinh !== "chay" || !jobId) return;
    let huy = false;
    let consecutiveErrors = 0;

    void docTrangThai(jobId)
      .then((job) => {
        if (huy || !job) return;
        consecutiveErrors = 0;
        setError(null);
        void dongBoManHinh(jobId, job);
      })
      .catch((e) => {
        if (huy) return;
        consecutiveErrors++;
        if (consecutiveErrors >= 3) {
          setManHinh("nhap");
          setError(loiKhaoSat(e, "theo dõi được khảo sát"));
        }
      });

    const timer = setInterval(() => {
      // Tab ẩn thì dừng gọi: job vẫn chờ ở máy chủ, không cần đốt request.
      if (document.hidden) return;
      void docTrangThai(jobId)
        .then((job) => {
          if (huy || !job) return;
          consecutiveErrors = 0;
          setError(null);
          if (!DANG_CHAY.has(job.status)) {
            clearInterval(timer);
            void dongBoManHinh(jobId, job);
          } else {
            setStatus(job);
          }
        })
        .catch((e) => {
          if (huy) return;
          consecutiveErrors++;
          if (consecutiveErrors >= 3) {
            clearInterval(timer);
            setManHinh("nhap");
            setError(loiKhaoSat(e, "theo dõi được khảo sát"));
          }
        });
    }, POLL_MS);

    return () => {
      huy = true;
      clearInterval(timer);
    };
  }, [token, manHinh, jobId, docTrangThai, dongBoManHinh, pollRetryTrigger]);

  /* ── Màn 1: nhập liệu ── */

  function layViTriHienTai() {
    if (!navigator.geolocation) {
      setError("Trình duyệt không cho lấy vị trí. Nhập toạ độ quán bằng tay.");
      return;
    }
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        set("latitude", pos.coords.latitude.toFixed(6));
        set("longitude", pos.coords.longitude.toFixed(6));
        setMsg("Đã lấy vị trí hiện tại. Kiểm tra lại trước khi khảo sát.");
      },
      () => setError("Không lấy được vị trí. Nhập toạ độ quán bằng tay."),
      { timeout: 10000 },
    );
  }

  function apPreset(preset: (typeof RADIUS_PRESETS)[number]) {
    idemKeyRef.current = "";
    setForm((f) => ({ ...f, dineInKm: String(preset.dineIn), deliveryKm: String(preset.delivery) }));
  }

  function kiemTraNhap(): string | null {
    const lat = soThuc(form.latitude);
    const lng = soThuc(form.longitude);
    if (lat == null || lat < -90 || lat > 90) return "Vĩ độ phải là số từ −90 đến 90.";
    if (lng == null || lng < -180 || lng > 180) return "Kinh độ phải là số từ −180 đến 180.";
    if (!form.coreCategory.trim()) return "Nhập danh mục món chính của quán.";
    const dineIn = soThuc(form.dineInKm);
    if (dineIn == null || dineIn <= 0 || dineIn > 3) return "Bán kính tại chỗ phải lớn hơn 0 và tối đa 3 km.";
    const delivery = soThuc(form.deliveryKm);
    if (delivery == null || delivery <= 0 || delivery > 10) return "Bán kính giao hàng phải lớn hơn 0 và tối đa 10 km.";
    const rating = soThuc(form.minRating);
    if (rating == null || rating < 0 || rating > 5) return "Ngưỡng đánh giá phải từ 0 đến 5 sao.";
    const reviews = soNguyen(form.minReviewCount);
    if (reviews == null || reviews < 0) return "Ngưỡng số lượt đánh giá phải là số không âm.";
    if (form.cogs.trim() && soNguyen(form.cogs) == null) return "Giá vốn phải là số đồng Việt Nam không âm.";
    return null;
  }

  /** Payload gửi `POST /catchment-survey` — khớp `CatchmentSurveyRequest`. */
  function taoPayload() {
    const cogs = soNguyen(form.cogs);
    return {
      latitude: Number(form.latitude),
      longitude: Number(form.longitude),
      core_category: form.coreCategory.trim(),
      positioning_tier: form.positioningTier || null,
      channel_mode: form.channelMode,
      include_substitutes: true,
      radius_profile: {
        dine_in_km: Number(form.dineInKm),
        delivery_km: Number(form.deliveryKm),
      },
      max_menu_images_per_store: 5,
      min_review_count: Number(form.minReviewCount),
      min_rating: Number(form.minRating),
      cost_plus_check: cogs == null ? null : { estimated_cogs_vnd: cogs },
    };
  }

  async function batDauKhaoSat(e?: FormEvent) {
    e?.preventDefault();
    const loiNhap = kiemTraNhap();
    if (loiNhap) {
      setError(loiNhap);
      return;
    }
    setError(null);
    setMsg(null);
    setBusy(true);
    // Ý định mới → khoá mới. Bấm lại khi đang lỗi mạng thì giữ khoá cũ.
    if (!idemKeyRef.current) {
      idemKeyRef.current = `ks-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    }
    try {
      const res = await apiSendHeaders<Envelope<{ job_id: string; status: string; idempotent_replay: boolean }>>(
        "/api/v1/market/catchment-survey",
        taoPayload(),
        { "Idempotency-Key": idemKeyRef.current },
      );
      const id = res.data.job_id;
      setJobId(id);
      setKetQua(null);
      setMsg(res.data.idempotent_replay ? "Đang mở lại khảo sát bạn vừa tạo." : null);
      const job = await docTrangThai(id);
      if (job) await dongBoManHinh(id, job);
    } catch (err) {
      setError(loiKhaoSat(err, "tạo được khảo sát"));
    } finally {
      setBusy(false);
    }
  }

  function khaoSatMoi() {
    idemKeyRef.current = "";
    setJobId("");
    setStatus(null);
    setKetQua(null);
    setReviewRows([]);
    setApproveAll(false);
    setError(null);
    setMsg(null);
    setManHinh("nhap");
  }

  /* ── Màn 3: review thủ công (ADR-008) ── */

  function capNhatRow(i: number, patch: Partial<ReviewRow>) {
    setReviewRows((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  async function guiXacNhan() {
    const thieu = reviewRows.some((r) => !r.rejected && soNguyen(r.giaGoc) == null);
    if (thieu) {
      setError("Mỗi dòng bạn giữ lại cần một mức giá đúng. Dòng không đọc được thì đánh dấu loại bỏ.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const items = reviewRows.map((r) => {
        const goc = soNguyen(r.giaGoc);
        const km = soNguyen(r.giaKhuyenMai);
        return {
          store_id: r.storeId,
          item_name_raw: r.tenMon,
          original_price_vnd: r.rejected ? null : goc,
          effective_price_vnd: r.rejected ? 0 : (km ?? goc ?? 0),
          is_combo: false,
          rejected: r.rejected,
        };
      });
      const res = await apiSend<Envelope<JobStatus>>(
        `/api/v1/market/catchment-survey/${jobId}/review`,
        { items, approve_all_remaining: approveAll },
      );
      setMsg("Đã ghi nhận xác nhận của bạn.");
      await dongBoManHinh(jobId, res.data);
    } catch (err) {
      setError(loiKhaoSat(err, "gửi được xác nhận giá"));
    } finally {
      setBusy(false);
    }
  }

  /* ── Dữ liệu dẫn xuất cho dashboard ── */

  const soSanh = ketQua?.substitute_comparison ?? null;
  const giaQuan = soThuc(form.giaQuan);

  const hangPhanVi = useMemo<HangPhanVi[]>(() => {
    if (!soSanh) return [];
    const rows: HangPhanVi[] = [{ ten: soSanh.core_category, stats: soSanh.core_stats, laCore: true }];
    for (const s of soSanh.substitutes ?? []) {
      rows.push({ ten: s.category_name, stats: s.stats });
    }
    return rows;
  }, [soSanh]);

  if (!token) return <AuthGate />;

  const progress = status?.progress;
  const pending = status?.pending_review ?? [];

  return (
    <div className="nq-page">
      <PageHeader
        kicker="Định vị giá theo bán kính"
        title="Khảo sát giá"
        tourId="khao-sat-gia"
        meta={
          manager
            ? "So giá quán bạn với các quán cùng phân khúc quanh đây — cả kênh giao hàng lẫn quán tại chỗ."
            : "Tính năng này dành cho quản lý hoặc chủ quán. Nhờ quản lý mở giúp bạn."
        }
      />

      {error ? <Alert>{error}</Alert> : null}
      {msg ? <Alert kind="ok">{msg}</Alert> : null}

      {!manager ? (
        <Empty title="Cần vai quản lý">
          Khảo sát đối thủ dùng chi phí thật (proxy và đọc ảnh thực đơn) nên chỉ quản lý hoặc chủ quán
          mới mở được.
        </Empty>
      ) : null}

      {manager && manHinh === "nhap" ? (
        <MangNhap
          form={form}
          set={set}
          busy={busy}
          onSubmit={batDauKhaoSat}
          onLayViTri={layViTriHienTai}
          onPreset={apPreset}
          storeLocation={storeLocation}
          loadingLocation={loadingLocation}
          tuyChinhToaDo={tuyChinhToaDo}
          setTuyChinhToaDo={setTuyChinhToaDo}
          onKhoiPhucViTriQuan={khoiPhucViTriQuan}
        />
      ) : null}

      {manager && manHinh === "chay" ? (
        <OpsCard eyebrow="Đang chạy" title="Tiến trình khảo sát">
          <ProgressBar value={progress?.step ?? 0} max={progress?.total ?? 5} className="mb-4" />
          <p className="nq-muted mb-2">{safeText(progress?.label, khaoSatTrangThaiLabel(status?.status))}</p>
          <p className="nq-muted">
            Trang tự cập nhật mỗi {POLL_MS / 1000} giây. Khảo sát thường xong trong vài phút; bạn có thể
            để trang này mở và làm việc khác.
          </p>
          <div className="mt-6">
            <Loading skeleton="rows" rows={4}>Đang lấy dữ liệu thị trường…</Loading>
          </div>
          <div className="mt-6 flex flex-wrap gap-3 pt-4 border-t border-[var(--nq-line)]">
            <Btn variant="ghost" onClick={() => setPollRetryTrigger((n) => n + 1)}>
              Thử kết nối lại
            </Btn>
            <Btn variant="ghost" onClick={khaoSatMoi}>
              Quay lại thiết lập khảo sát
            </Btn>
          </div>
        </OpsCard>
      ) : null}

      {manager && manHinh === "review" ? (
        <OpsCard
          eyebrow="Cần bạn quyết định"
          title="Xác nhận giá đọc từ ảnh"
          count={reviewRows.length}
          countLabel="dòng"
        >
          <Alert kind="info">
            Máy đọc ảnh không chắc chắn về {reviewRows.length} dòng giá. Số này chỉ được tính vào thống kê
            sau khi bạn xác nhận — hệ thống không tự duyệt thay.
          </Alert>

          {pending.length === 0 ? <Empty title="Không có dòng chờ">Tải lại trang để lấy danh sách mới.</Empty> : null}

          <ul className="space-y-6">
            {pending.map((p, i) => {
              const row = reviewRows[i];
              if (!row) return null;
              return (
                <li key={`${p.store_id}-${p.name}-${i}`} className="nq-record">
                  <div className="flex flex-col gap-4 md:flex-row">
                    {p.image_url ? (
                      // Ảnh gốc để chủ quán đối chiếu bằng mắt — đây là lý do màn này tồn tại.
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={p.image_url}
                        alt={`Ảnh thực đơn của ${safeText(p.store_name, "quán")}`}
                        className="h-56 w-full object-contain md:w-72"
                        style={{
                          background: "var(--nq-bg-elevated)",
                          border: "1px solid var(--nq-line)",
                          borderRadius: "var(--nq-radius)",
                        }}
                      />
                    ) : null}
                    <div className="flex-1">
                      <p className="nq-record__title">{safeText(p.name, "Món chưa đọc được tên")}</p>
                      <p className="nq-record__meta">
                        {safeText(p.store_name, p.store_id)} · máy đọc thành “{safeText(p.raw_text, "không rõ")}” ·{" "}
                        {lyDoReviewLabel(p.reason)}
                      </p>

                      <label className="mt-4 flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={row.rejected}
                          onChange={(e) => capNhatRow(i, { rejected: e.target.checked })}
                        />
                        Loại dòng này khỏi mẫu (không phải món đang khảo sát, hoặc ảnh không đọc được)
                      </label>

                      {!row.rejected ? (
                        <div className="mt-4 grid gap-4 sm:grid-cols-2">
                          <Field label="Giá đúng (VNĐ)" hint="Giá in trên thực đơn, chưa trừ khuyến mãi.">
                            <Input
                              type="number"
                              min={0}
                              step={1000}
                              value={row.giaGoc}
                              onChange={(e) => capNhatRow(i, { giaGoc: e.target.value })}
                              placeholder="45000"
                            />
                          </Field>
                          <Field label="Giá khuyến mãi (nếu có)" hint="Bỏ trống nếu quán không giảm giá.">
                            <Input
                              type="number"
                              min={0}
                              step={1000}
                              value={row.giaKhuyenMai}
                              onChange={(e) => capNhatRow(i, { giaKhuyenMai: e.target.value })}
                              placeholder="Bỏ trống"
                            />
                          </Field>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          {reviewRows.length > 0 ? (
            <label className="mt-6 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={approveAll} onChange={(e) => setApproveAll(e.target.checked)} />
              Giữ lại mọi dòng còn lại như máy đọc — chỉ chọn nếu bạn đã đối chiếu ảnh
            </label>
          ) : null}

          <div className="mt-6 flex flex-col gap-4 sm:flex-row">
            <Btn variant="primary" busy={busy} busyLabel="Đang gửi…" onClick={() => void guiXacNhan()}>
              Xác nhận và tổng hợp
            </Btn>
            <Btn variant="ghost" onClick={khaoSatMoi} disabled={busy}>
              Bỏ khảo sát này
            </Btn>
          </div>
        </OpsCard>
      ) : null}

      {manager && manHinh === "ket-qua" && ketQua ? (
        <>
          <MangKetQua
            ketQua={ketQua}
            soSanh={soSanh}
            hangPhanVi={hangPhanVi}
            giaQuan={giaQuan}
            onGiaQuanChange={(v) => set("giaQuan", v)}
          />
          <NextSteps
            title="Làm gì tiếp"
            note="Kết quả là tham chiếu thị trường, quyết định giá vẫn là của bạn"
          >
            <BtnLink href="/menu" variant="primary">
              Mở menu để chỉnh giá
            </BtnLink>
            <Btn variant="ghost" onClick={khaoSatMoi}>
              Khảo sát khu vực khác
            </Btn>
          </NextSteps>
        </>
      ) : null}
    </div>
  );
}

/* ── Màn 1: nhập liệu ── */

function MangNhap({
  form,
  set,
  busy,
  onSubmit,
  onLayViTri,
  onPreset,
  storeLocation,
  loadingLocation,
  tuyChinhToaDo,
  setTuyChinhToaDo,
  onKhoiPhucViTriQuan,
}: {
  form: FormState;
  set: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  busy: boolean;
  onSubmit: (e: FormEvent) => void;
  onLayViTri: () => void;
  onPreset: (preset: (typeof RADIUS_PRESETS)[number]) => void;
  storeLocation: StoreLocationInfo | null;
  loadingLocation: boolean;
  tuyChinhToaDo: boolean;
  setTuyChinhToaDo: (val: boolean) => void;
  onKhoiPhucViTriQuan: () => void;
}) {
  return (
    <form onSubmit={onSubmit}>
      <OpsCard eyebrow="Bước 1" title="Quán của bạn ở đâu">
        {loadingLocation ? (
          <p className="nq-muted text-sm py-2">Đang tải vị trí quán đã cấu hình…</p>
        ) : storeLocation ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-4 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-[var(--nq-fg)]">
                      {storeLocation.tenQuan || "Địa chỉ quán của bạn"}
                    </span>
                    <span className="rounded px-2 py-0.5 text-xs font-semibold bg-[var(--nq-accent-subtle)] text-[var(--nq-accent)]">
                      {storeLocation.nguon === "gps" ? "Toạ độ GPS quán" : "Địa chỉ cấu hình"}
                    </span>
                  </div>
                  <p className="text-sm text-[var(--nq-dim)]">
                    {storeLocation.diaChi}
                  </p>
                  <p className="font-mono text-xs text-[var(--nq-muted)]">
                    Toạ độ đang dùng: {form.latitude}, {form.longitude}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  <Btn
                    variant="ghost"
                    type="button"
                    onClick={() => setTuyChinhToaDo(!tuyChinhToaDo)}
                  >
                    {tuyChinhToaDo ? "Ẩn tuỳ chỉnh toạ độ" : "Đổi toạ độ khác"}
                  </Btn>
                  {tuyChinhToaDo &&
                  (form.latitude !== storeLocation.latitude || form.longitude !== storeLocation.longitude) ? (
                    <Btn
                      variant="ghost"
                      type="button"
                      onClick={onKhoiPhucViTriQuan}
                    >
                      Khôi phục toạ độ quán
                    </Btn>
                  ) : null}
                </div>
              </div>
            </div>

            {tuyChinhToaDo ? (
              <div className="rounded-xl border border-dashed border-[var(--nq-line)] p-4 space-y-4">
                <p className="text-xs text-[var(--nq-muted)]">
                  Chỉ chỉnh sửa nếu bạn muốn khảo sát thị trường quanh một toạ độ khác ngoài quán của bạn:
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Vĩ độ" hint="Số thập phân, vd 10.7769.">
                    <Input
                      type="number"
                      step="0.000001"
                      min={-90}
                      max={90}
                      value={form.latitude}
                      onChange={(e) => set("latitude", e.target.value)}
                    />
                  </Field>
                  <Field label="Kinh độ" hint="Số thập phân, vd 106.7009.">
                    <Input
                      type="number"
                      step="0.000001"
                      min={-180}
                      max={180}
                      value={form.longitude}
                      onChange={(e) => set("longitude", e.target.value)}
                    />
                  </Field>
                </div>
                <Btn variant="ghost" type="button" onClick={onLayViTri}>
                  Lấy vị trí GPS hiện tại
                </Btn>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="space-y-4">
            <Alert kind="info">
              Quán chưa được thiết lập địa chỉ hoặc toạ độ. Vui lòng nhập toạ độ quán bên dưới, bấm lấy vị trí hiện tại của trình duyệt, hoặc{" "}
              <Link href="/cau-hinh-quan" className="underline font-bold text-[var(--nq-accent)]">
                vào Cấu hình quán
              </Link>{" "}
              để thiết lập địa chỉ dùng chung cho toàn hệ thống.
            </Alert>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Vĩ độ" hint="Số thập phân, vd 10.7769.">
                <Input
                  type="number"
                  step="0.000001"
                  min={-90}
                  max={90}
                  value={form.latitude}
                  onChange={(e) => set("latitude", e.target.value)}
                  placeholder="10.7769"
                />
              </Field>
              <Field label="Kinh độ" hint="Số thập phân, vd 106.7009.">
                <Input
                  type="number"
                  step="0.000001"
                  min={-180}
                  max={180}
                  value={form.longitude}
                  onChange={(e) => set("longitude", e.target.value)}
                  placeholder="106.7009"
                />
              </Field>
            </div>
            <Btn variant="ghost" type="button" onClick={onLayViTri}>
              Lấy vị trí hiện tại
            </Btn>
          </div>
        )}
      </OpsCard>

      <OpsCard eyebrow="Bước 2" title="Bán kính khảo sát" tourId="khao-sat-gia-ban-kinh">
        <p className="nq-muted mb-4">
          Chọn preset theo mật độ khu vực, hoặc tự kéo hai con số. Tại chỗ tối đa 3 km, giao hàng tối đa 10 km.
        </p>
        <div className="mb-6 flex flex-wrap gap-2">
          {RADIUS_PRESETS.map((p) => {
            const dangChon = Number(form.dineInKm) === p.dineIn && Number(form.deliveryKm) === p.delivery;
            return (
              <button
                key={p.ma}
                type="button"
                onClick={() => onPreset(p)}
                className="nq-filter-clear"
                aria-pressed={dangChon}
                title={p.moTa}
                style={dangChon ? { borderColor: "var(--nq-accent)", color: "var(--nq-accent)" } : undefined}
              >
                {p.nhan} · {p.dineIn}/{p.delivery} km
              </button>
            );
          })}
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          <Field label={`Quán tại chỗ: ${safeNumber(form.dineInKm, 1)} km`}>
            <input
              type="range"
              min={0.3}
              max={3}
              step={0.1}
              value={Number(form.dineInKm) || 1}
              onChange={(e) => set("dineInKm", e.target.value)}
              className="w-full"
              aria-label="Bán kính quán tại chỗ theo km"
            />
          </Field>
          <Field label={`Kênh giao hàng: ${safeNumber(form.deliveryKm, 1)} km`}>
            <input
              type="range"
              min={1}
              max={10}
              step={0.5}
              value={Number(form.deliveryKm) || 5}
              onChange={(e) => set("deliveryKm", e.target.value)}
              className="w-full"
              aria-label="Bán kính kênh giao hàng theo km"
            />
          </Field>
        </div>
      </OpsCard>

      <OpsCard eyebrow="Bước 3" title="Món và phân khúc">
        <Field label="Danh mục món chính" hint="Món bạn muốn so giá, vd “cơm tấm”.">
          <Input
            list="nq-danh-muc-goi-y"
            value={form.coreCategory}
            onChange={(e) => set("coreCategory", e.target.value)}
            placeholder="cơm tấm"
          />
          <datalist id="nq-danh-muc-goi-y">
            {DANH_MUC_GOI_Y.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </Field>

        <Field
          label="Phân khúc quán bạn"
          hint="Giá được tính riêng theo từng phân khúc — quán vỉa hè không bị so với chuỗi thương hiệu."
        >
          <Select value={form.positioningTier} onChange={(e) => set("positioningTier", e.target.value)}>
            {DINH_VI_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Kênh lấy giá">
          <Select value={form.channelMode} onChange={(e) => set("channelMode", e.target.value)}>
            {KENH_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </Field>

        <details className="mt-4">
          <summary className="cursor-pointer font-bold uppercase tracking-widest text-sm text-[var(--nq-dim)]">
            Nâng cao — ngưỡng lọc quán
          </summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Số lượt đánh giá tối thiểu" hint="Quán ít lượt hơn sẽ bị loại khỏi mẫu.">
              <Input
                type="number"
                min={0}
                step={10}
                value={form.minReviewCount}
                onChange={(e) => set("minReviewCount", e.target.value)}
              />
            </Field>
            <Field label="Điểm đánh giá tối thiểu" hint="Từ 0 đến 5 sao.">
              <Input
                type="number"
                min={0}
                max={5}
                step={0.1}
                value={form.minRating}
                onChange={(e) => set("minRating", e.target.value)}
              />
            </Field>
          </div>
        </details>
      </OpsCard>

      <OpsCard eyebrow="Tuỳ chọn" title="Giá vốn một phần ăn">
        <p className="nq-muted mb-4">
          Không bắt buộc. Khai giá vốn thì trang sẽ đối chiếu vùng giá thị trường với ngưỡng có lời tối
          thiểu của bạn và cảnh báo nếu thị trường thấp hơn ngưỡng đó.
        </p>
        <Field label="Giá vốn nguyên liệu mỗi phần (VNĐ)" hint="Bỏ trống nếu chưa muốn khai.">
          <Input
            type="number"
            min={0}
            step={1000}
            value={form.cogs}
            onChange={(e) => set("cogs", e.target.value)}
            placeholder="Bỏ trống"
          />
        </Field>
      </OpsCard>

      <Alert kind="info">{DISCLAIMER}</Alert>

      <div className="mt-6 flex flex-col gap-4 sm:flex-row">
        <Btn type="submit" variant="primary" busy={busy} busyLabel="Đang tạo khảo sát…">
          Bắt đầu khảo sát
        </Btn>
      </div>
    </form>
  );
}

/* ── Màn 4: dashboard kết quả ── */

function MangKetQua({
  ketQua,
  soSanh,
  hangPhanVi,
  giaQuan,
  onGiaQuanChange,
}: {
  ketQua: KetQua;
  soSanh: SoSanh | null;
  hangPhanVi: HangPhanVi[];
  giaQuan: number | null;
  onGiaQuanChange: (value: string) => void;
}) {
  const nguon = ketQua.area_context;
  const online = ketQua.online_stats ?? null;
  const dinein = ketQua.dinein_stats ?? null;

  return (
    <>
      <StatGrid>
        <Stat value={soSanh ? giaVnd(soSanh.ambi) : "—"} label="AMBI khu vực" />
        <Stat
          value={soSanh ? `${giaVnd(soSanh.sweet_spot_low_display)}–${giaVnd(soSanh.sweet_spot_high_display)}` : "—"}
          label="Sweet Spot"
        />
        <Stat
          value={safeNumber(nguon?.competitive_intensity ?? null, 1)}
          label="Quán đạt chuẩn / km²"
        />
        <Stat value={loaiKhuVucLabel(nguon?.area_type)} label="Loại khu vực" />
      </StatGrid>

      {soSanh?.cost_plus_warning ? (
        // Plan mục 6.1: banner VÀNG/CAM, không phải đỏ báo lỗi — đây là đánh đổi
        // kinh doanh, không phải sự cố. Không được ẩn cho "gọn".
        <div
          role="status"
          className="nq-notice"
          style={{ borderColor: "var(--nq-warn)", background: "color-mix(in srgb, var(--nq-warn) 14%, transparent)" }}
        >
          <strong style={{ color: "var(--nq-warn)" }}>Đối chiếu giá vốn: </strong>
          {COST_PLUS_CANH_BAO}
          {soSanh.min_viable_price != null ? (
            <span className="block mt-1 font-mono text-xs">
              Ngưỡng có lời tối thiểu của bạn: {giaVnd(soSanh.min_viable_price)}
            </span>
          ) : null}
        </div>
      ) : null}

      <OpsCard eyebrow="Kết quả" title="Giá theo kênh" tourId="khao-sat-gia-ket-qua">
        <p className="nq-muted mb-4">
          Phân khúc: <strong>{dinhViLabel(soSanh?.positioning_tier)}</strong> · Món chính:{" "}
          <strong>{danhMucLabel(soSanh?.core_category)}</strong>
        </p>
        <div className="nq-table-wrap">
          <table className="nq-table">
            <thead>
              <tr>
                <th scope="col">Kênh</th>
                <th scope="col">P25</th>
                <th scope="col">P50</th>
                <th scope="col">P75</th>
                <th scope="col">Số mẫu</th>
              </tr>
            </thead>
            <tbody>
              <DongPhanVi ten={kenhGiaLabel("delivery_platform")} stats={online} />
              <DongPhanVi ten={kenhGiaLabel("dine_in_vision")} stats={dinein} />
            </tbody>
          </table>
        </div>
        <p className="nq-muted mt-4">
          Kênh không có dòng nghĩa là chưa đủ mẫu tối thiểu ở kênh đó — không phải giá bằng 0.
        </p>
      </OpsCard>

      <div className="nq-dash-charts">
        <PhanViBars rows={hangPhanVi} />
        {soSanh ? (
          <GiaGauge
            ambi={soSanh.ambi}
            sweetLow={soSanh.sweet_spot_low_display}
            sweetHigh={soSanh.sweet_spot_high_display}
            minViablePrice={soSanh.min_viable_price}
            giaQuan={giaQuan}
            sampleSize={soSanh.core_stats.sample_size}
          />
        ) : null}
      </div>

      <OpsCard eyebrow="Đối chiếu" title="Giá quán bạn đang bán">
        <p className="nq-muted mb-4">
          Con số này chỉ dùng để vẽ trên đồng hồ ở trang bạn đang xem — không gửi lên máy chủ, không lưu vào
          kết quả khảo sát.
        </p>
        <Field label="Giá món tương đương tại quán bạn (VNĐ)">
          <Input
            type="number"
            min={0}
            step={1000}
            value={giaQuan == null ? "" : String(giaQuan)}
            onChange={(e) => onGiaQuanChange(e.target.value)}
            placeholder="45000"
          />
        </Field>
      </OpsCard>

      <Alert kind="info">{DISCLAIMER}</Alert>

      <p className="nq-muted mt-4">
        Dữ liệu thị trường ghi nhận lúc <strong>{formatLuc(ketQua.survey_captured_at)}</strong>. Giá và menu
        quán đối thủ đổi theo tuần — khảo sát này là ảnh chụp một thời điểm, không phải mặt bằng giá cố định.
      </p>

      <TechnicalDrawer
        summary="Chi tiết kỹ thuật của lần khảo sát"
        lines={[
          `job_id: ${safeText(ketQua.job_id)}`,
          `trạng thái: ${khaoSatTrangThaiLabel(ketQua.status)}`,
          `sinh kết quả lúc: ${formatLuc(ketQua.generated_at)}`,
          soSanh ? `tầng định vị: ${safeText(soSanh.positioning_tier)}` : "tầng định vị: —",
          online ? `mẫu kênh giao hàng: ${online.sample_size}` : "mẫu kênh giao hàng: 0",
          dinein ? `mẫu kênh tại chỗ: ${dinein.sample_size}` : "mẫu kênh tại chỗ: 0",
        ]}
      />
    </>
  );
}

/** Một dòng bảng phân vị. `sample_size` luôn đi kèm con số (plan mục 6.2). */
function DongPhanVi({ ten, stats }: { ten: string; stats: PhanVi | null }) {
  if (!stats || stats.insufficient_data) {
    return (
      <tr>
        <th scope="row">{ten}</th>
        <td colSpan={3} className="nq-muted">
          Chưa đủ mẫu tối thiểu
        </td>
        <td>{stats?.sample_size ?? 0}</td>
      </tr>
    );
  }
  return (
    <tr>
      <th scope="row">{ten}</th>
      <td>{giaVnd(stats.p25)}</td>
      <td>{giaVnd(stats.p50)}</td>
      <td>{giaVnd(stats.p75)}</td>
      <td>
        {stats.sample_size} <StatusChip tone={stats.sample_size < 10 ? "warn" : "default"}>mẫu</StatusChip>
      </td>
    </tr>
  );
}
