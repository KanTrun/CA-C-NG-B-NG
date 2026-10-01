"use client";

/**
 * Cấu hình quán & hướng dẫn AI agent — nơi quản lý/chủ quán nhập THÔNG TIN THẬT
 * (địa chỉ chuẩn hóa qua Address API, giờ mở cửa, hotline, wifi, ngân hàng, tiện ích)
 * và HƯỚNG DẪN RIÊNG cho AI agent thay vì để bot dùng số liệu mặc định trong code (ADR-008).
 *
 * Lưu vào KV `store_profile` / `store_promotions` qua
 * GET/PUT /api/v1/store/profile và /api/v1/store/promotions.
 * Mọi agent khách-facing (AG-FBPAGE, AG-CONCIERGE, comment, mail) đọc từ đây.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiSend, ApiError } from "../../lib/api";
import { viError, type ErrorCopy } from "../../lib/present";
import { getToken } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Badge,
  Btn,
  Field,
  Input,
  Loading,
  PageHeader,
  ProgressBar,
  Select,
  TabBar,
  TabButton,
  Textarea,
  useToasts,
  Toasts,
} from "../../ui/kit";
import { Icon } from "../../ui/icons";
import { AddressSelector, type AddressData } from "./AddressSelector";

export type StoreProfile = {
  ten_quan: string;
  slogan: string;
  dia_chi: string;
  dia_chi_chi_tiet: string;
  phuong_xa: string;
  phuong_xa_code: string;
  quan_huyen: string;
  quan_huyen_code: string;
  tinh: string;
  tinh_code: string;
  thanh_pho: string;
  toa_do_lat: string;
  toa_do_lon: string;
  google_maps_url: string;
  lat: number | null;
  lon: number | null;
  hotline: string;
  hotline_phu: string;
  email: string;
  website: string;
  fanpage_url: string;
  gio_mo_cua: string;
  gio_mo_cua_chi_tiet: string;
  khoang_gia: string;
  tien_ich: string;
  wifi_ssid: string;
  wifi_pass: string;
  ngan_hang: string;
  stk_ngan_hang: string;
  chu_tai_khoan: string;
  mo_ta: string;
  chinh_sach_dat_ban: string;
  huong_dan_agent: string;
};

export type Promotion = {
  id?: string;
  tieu_de: string;
  chi_tiet: string;
  hieu_luc: string;
};

const EMPTY_PROFILE: StoreProfile = {
  ten_quan: "",
  slogan: "",
  dia_chi: "",
  dia_chi_chi_tiet: "",
  phuong_xa: "",
  phuong_xa_code: "",
  quan_huyen: "",
  quan_huyen_code: "",
  tinh: "",
  tinh_code: "",
  thanh_pho: "",
  toa_do_lat: "",
  toa_do_lon: "",
  google_maps_url: "",
  lat: null,
  lon: null,
  hotline: "",
  hotline_phu: "",
  email: "",
  website: "",
  fanpage_url: "",
  gio_mo_cua: "",
  gio_mo_cua_chi_tiet: "",
  khoang_gia: "",
  tien_ich: "",
  wifi_ssid: "",
  wifi_pass: "",
  ngan_hang: "",
  stk_ngan_hang: "",
  chu_tai_khoan: "",
  mo_ta: "",
  chinh_sach_dat_ban: "",
  huong_dan_agent: "",
};

const POPULAR_BANKS = [
  "Vietcombank",
  "MB Bank",
  "Techcombank",
  "ACB",
  "BIDV",
  "VietinBank",
  "TPBank",
  "VPBank",
  "VIB",
  "Sacombank",
  "Khác",
];

const POPULAR_AMENITIES = [
  "Máy lạnh / Điều hòa",
  "Wifi tốc độ cao",
  "Chỗ đỗ ô tô",
  "Chỗ để xe máy miễn phí",
  "Ổ cắm sạc laptop",
  "Thanh toán QR / Thẻ",
  "Khu vực ngoài trời",
  "Thân thiện thú cưng",
  "Bàn làm việc nhóm",
  "Nhận đặt tiệc / sự kiện",
];

const AI_PROMPT_SUGGESTIONS = [
  "Luôn xưng \"em\", gọi khách là \"mình\" như đang trò chuyện thân mật.",
  "Nếu quán hết món, báo thật và gợi ý món thay thế tương đương, không hứa suông.",
  "Ưu tiên tư vấn các món đặc trưng và combo sáng ưu đãi.",
  "Khuyến khích khách đặt bàn trước nếu nhóm đi từ 4 người trở lên.",
  "Không nhắc đến đối thủ cạnh tranh trong khu vực lân cận.",
  "Không tự ý hứa hẹn giảm giá ngoài các chương trình khuyến mãi hiện có.",
];

const COPY_LOAD: ErrorCopy = { doing: "đọc được cấu hình quán" };

type ConfigTab = "general" | "address" | "contact" | "operations" | "ai" | "promotions";

type FbStatus = {
  connected?: boolean;
  webhook_secret_present?: boolean;
  auto_send_enabled?: boolean;
  auto_reservation_enabled?: boolean;
  llm_mode?: string;
};

/**
 * Banner nói rõ chatbot Messenger đang chạy hay không.
 *
 * Chủ quán sửa hướng dẫn AI rồi tưởng bot đã dùng — nhưng nếu thiếu App Secret
 * thì webhook chặn mọi tin, hoặc auto-send đang tắt thì bot không gửi gì.
 * Hiện ngay trong tab AI để khỏi tưởng "cấu hình chưa chạy".
 */
function FbRuntimeBanner() {
  const [st, setSt] = useState<FbStatus | null>(null);

  useEffect(() => {
    if (!getToken()) return;
    let alive = true;
    apiGet<FbStatus>("/api/v1/page/status")
      .then((d) => {
        if (alive) setSt(d);
      })
      .catch(() => {
        // Không đọc được status (chưa đăng nhập / 403) → không hiện banner.
        if (alive) setSt(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!st) return null;

  const rows: string[] = [];
  if (st.webhook_secret_present === false) {
    rows.push(
      "Thiếu NHIPQUAN_FB_APP_SECRET trong .env — webhook chặn mọi tin của Meta (403). Lấy ở Meta App Dashboard → App Settings → Basic → App Secret, xem docs/runbooks/facebook-page-connect.md §4.",
    );
  }
  if (st.connected === false) {
    rows.push("Page chưa nối — tin khách nằm hộp thư chờ duyệt, bot không trả lời. Làm theo docs/runbooks/facebook-page-connect.md.");
  }
  if (st.auto_send_enabled === false) {
    rows.push("Tự trả lời đang TẮT — mọi tin vào hộp thư chờ duyệt tay ở /page-quan/fb-inbox.");
  }
  if (st.auto_reservation_enabled === false) {
    rows.push("Đặt bàn tự động đang TẮT — tin đặt bàn chờ quản lý duyệt (câu hỏi số tài khoản vẫn bot trả lời ngay).");
  }
  if (st.llm_mode === "replay") {
    rows.push("CA_AGENT_MODE=replay — không gọi LLM, chỉ trả lời được câu hỏi có sẵn trong template.");
  }
  if (rows.length === 0) return null;

  return (
    <div
      role="status"
      className="rounded-lg border-2 border-[var(--nq-warn)] bg-[var(--nq-st-warn-soft)] px-4 py-3 text-sm text-[var(--nq-st-warn-ink)]"
    >
      <strong className="font-bold">Chatbot Messenger chưa chạy đúng như bạn nghĩ:</strong>
      <ul className="mt-1 list-disc space-y-1 pl-5">
        {rows.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

export default function CauHinhQuanPage() {
  const { toasts, push, dismiss } = useToasts();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<ConfigTab>("general");
  const [showWifiPass, setShowWifiPass] = useState(false);
  const [profile, setProfile] = useState<StoreProfile>(EMPTY_PROFILE);
  const [promos, setPromos] = useState<Promotion[]>([]);
  const [error, setError] = useState("");
  const [gpsBusy, setGpsBusy] = useState(false);
  const [gpsMsg, setGpsMsg] = useState("");
  const [savedSnapshot, setSavedSnapshot] = useState<{ profile: StoreProfile; promos: Promotion[] } | null>(null);

  const dirty =
    savedSnapshot !== null &&
    (JSON.stringify(profile) !== JSON.stringify(savedSnapshot.profile) ||
      JSON.stringify(promos) !== JSON.stringify(savedSnapshot.promos));

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [p, pr] = await Promise.all([
        apiGet<StoreProfile>("/api/v1/store/profile"),
        apiGet<Promotion[]>("/api/v1/store/promotions"),
      ]);
      const mergedProfile = { ...EMPTY_PROFILE, ...p };
      setProfile(mergedProfile);
      setPromos(Array.isArray(pr) ? pr : []);
      setSavedSnapshot({ profile: mergedProfile, promos: Array.isArray(pr) ? [...pr] : [] });
    } catch (e) {
      setError(viError(e, COPY_LOAD));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Dirty guard: cảnh báo khi rời trang nếu chưa lưu
  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  // Đánh giá mức độ hoàn thiện hồ sơ quán
  const completionScore = useMemo(() => {
    let score = 0;
    // Nhận diện cơ bản (40 điểm)
    if (profile.ten_quan.trim()) score += 10;
    if (profile.dia_chi.trim()) score += 10;
    if (profile.hotline.trim()) score += 10;
    if (profile.gio_mo_cua.trim()) score += 10;

    // Địa chỉ chuẩn hóa theo API (15 điểm)
    if (profile.tinh.trim()) score += 5;
    if (profile.quan_huyen.trim()) score += 5;
    if (profile.phuong_xa.trim()) score += 5;

    // Kênh truyền thông & Liên hệ (15 điểm)
    if (profile.email.trim()) score += 5;
    if (profile.fanpage_url.trim() || profile.website.trim()) score += 5;
    if (profile.hotline_phu.trim()) score += 5;

    // Tiện ích & Thanh toán (15 điểm)
    if (profile.ngan_hang.trim() && profile.stk_ngan_hang.trim()) score += 7;
    if (profile.wifi_ssid.trim()) score += 4;
    if (profile.tien_ich.trim()) score += 4;

    // Huấn luyện AI & Vận hành (15 điểm)
    if (profile.mo_ta.trim()) score += 5;
    if (profile.chinh_sach_dat_ban.trim()) score += 5;
    if (profile.huong_dan_agent.trim()) score += 5;

    return Math.min(score, 100);
  }, [profile]);

  const missingItems = useMemo(() => {
    const list: { label: string; tab: ConfigTab }[] = [];
    if (!profile.ten_quan.trim()) list.push({ label: "Tên quán", tab: "general" });
    if (!profile.dia_chi.trim()) list.push({ label: "Địa chỉ", tab: "address" });
    if (!profile.tinh.trim() || !profile.quan_huyen.trim()) list.push({ label: "Chuẩn hóa Tỉnh/Quận", tab: "address" });
    if (!profile.hotline.trim()) list.push({ label: "Hotline", tab: "contact" });
    if (!profile.gio_mo_cua.trim()) list.push({ label: "Giờ mở cửa", tab: "operations" });
    if (!profile.stk_ngan_hang.trim()) list.push({ label: "STK ngân hàng", tab: "operations" });
    if (!profile.wifi_ssid.trim()) list.push({ label: "Wifi quán", tab: "operations" });
    if (!profile.email.trim()) list.push({ label: "Email liên hệ", tab: "contact" });
    if (!profile.huong_dan_agent.trim()) list.push({ label: "Hướng dẫn AI", tab: "ai" });
    return list;
  }, [profile]);

  async function saveProfile() {
    // Validate trước khi submit
    if (profile.email.trim() && (!profile.email.includes("@") || profile.email.trim().length < 5)) {
      push("Email liên hệ chưa đúng định dạng.", "err");
      setTab("contact");
      return;
    }
    if (profile.hotline.trim() && !/^[0-9+().\-\s]{6,40}$/.test(profile.hotline.trim())) {
      push("Số điện thoại hotline chính chưa hợp lệ.", "err");
      setTab("contact");
      return;
    }
    if (profile.hotline_phu.trim() && !/^[0-9+().\-\s]{6,40}$/.test(profile.hotline_phu.trim())) {
      push("Số điện thoại hotline phụ chưa hợp lệ.", "err");
      setTab("contact");
      return;
    }

    setSaving(true);
    try {
      const cleaned: StoreProfile = {
        ...profile,
        ten_quan: profile.ten_quan.trim(),
        slogan: profile.slogan.trim(),
        dia_chi: profile.dia_chi.trim(),
        dia_chi_chi_tiet: profile.dia_chi_chi_tiet.trim(),
        phuong_xa: profile.phuong_xa.trim(),
        phuong_xa_code: profile.phuong_xa_code.trim(),
        quan_huyen: profile.quan_huyen.trim(),
        quan_huyen_code: profile.quan_huyen_code.trim(),
        tinh: profile.tinh.trim(),
        tinh_code: profile.tinh_code.trim(),
        thanh_pho: (profile.quan_huyen || profile.tinh || profile.thanh_pho).trim(),
        toa_do_lat: profile.toa_do_lat.trim(),
        toa_do_lon: profile.toa_do_lon.trim(),
        google_maps_url: profile.google_maps_url.trim(),
        lat: profile.lat,
        lon: profile.lon,
        hotline: profile.hotline.trim(),
        hotline_phu: profile.hotline_phu.trim(),
        email: profile.email.trim(),
        website: profile.website.trim(),
        fanpage_url: profile.fanpage_url.trim(),
        gio_mo_cua: profile.gio_mo_cua.trim(),
        gio_mo_cua_chi_tiet: profile.gio_mo_cua_chi_tiet.trim(),
        khoang_gia: profile.khoang_gia.trim(),
        tien_ich: profile.tien_ich.trim(),
        wifi_ssid: profile.wifi_ssid.trim(),
        wifi_pass: profile.wifi_pass.trim(),
        ngan_hang: profile.ngan_hang.trim(),
        stk_ngan_hang: profile.stk_ngan_hang.trim(),
        chu_tai_khoan: profile.chu_tai_khoan.trim(),
        mo_ta: profile.mo_ta.trim(),
        chinh_sach_dat_ban: profile.chinh_sach_dat_ban.trim(),
        huong_dan_agent: profile.huong_dan_agent.trim(),
      };
      setProfile(cleaned);
      await apiSend("/api/v1/store/profile", cleaned, "PUT");
      setSavedSnapshot((prev) => ({ profile: cleaned, promos: prev?.promos ?? promos }));

      const criticalMissing = ["dia_chi", "gio_mo_cua", "hotline"].filter((k) => !cleaned[k as keyof StoreProfile]);
      push(
        criticalMissing.length === 0
          ? "Đã lưu thành công! AI bot giờ trả lời khách bằng đúng thông tin này."
          : `Đã lưu, nhưng còn thiếu ${criticalMissing.join(", ")} — bot sẽ trả “chưa cập nhật” khi khách hỏi.`,
        criticalMissing.length === 0 ? "ok" : "err"
      );
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 403
          ? "Chỉ quản lý hoặc chủ quán mới được sửa cấu hình quán."
          : viError(e, { doing: "lưu thông tin quán" });
      push(msg, "err");
    } finally {
      setSaving(false);
    }
  }

  async function savePromos() {
    setSaving(true);
    try {
      const cleaned = promos
        .map((p, i) => ({ ...p, id: p.id || `km_ui_${i + 1}` }))
        .filter((p) => p.tieu_de.trim() || p.chi_tiet.trim());
      await apiSend("/api/v1/store/promotions", cleaned, "PUT");
      setPromos(cleaned);
      setSavedSnapshot((prev) => ({ profile: prev?.profile ?? profile, promos: cleaned }));
      push("Đã lưu chương trình khuyến mãi thành công.", "ok");
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 403
          ? "Chỉ quản lý hoặc chủ quán mới được sửa cấu hình."
          : viError(e, { doing: "lưu khuyến mãi" });
      push(msg, "err");
    } finally {
      setSaving(false);
    }
  }

  function setField<K extends keyof StoreProfile>(key: K, value: StoreProfile[K]) {
    setProfile((prev) => ({ ...prev, [key]: value }));
  }

  function handleAddressChange(patch: Partial<AddressData>) {
    setProfile((prev) => ({
      ...prev,
      ...patch,
    }));
  }

  function toggleAmenity(item: string) {
    const current = profile.tien_ich
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const exists = current.includes(item);
    const updated = exists ? current.filter((x) => x !== item) : [...current, item];
    setField("tien_ich", updated.join(", "));
  }

  function appendAiSuggestion(text: string) {
    const cur = profile.huong_dan_agent.trim();
    const addition = `- ${text}`;
    if (!cur) {
      setField("huong_dan_agent", addition);
    } else if (!cur.includes(text)) {
      setField("huong_dan_agent", `${cur}\n${addition}`);
    }
  }

  function layViTriGps() {
    if (!navigator.geolocation) {
      setGpsMsg("Trình duyệt không cho lấy vị trí. Nhập địa chỉ bên dưới.");
      return;
    }
    setGpsBusy(true);
    setGpsMsg("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = Number(pos.coords.latitude.toFixed(6));
        const lon = Number(pos.coords.longitude.toFixed(6));
        setProfile((prev) => ({
          ...prev,
          lat,
          lon,
          toa_do_lat: String(lat),
          toa_do_lon: String(lon),
          // Xoá nhãn tỉnh/thành cũ — thời tiết reverse-geocode từ GPS.
          tinh: "",
          thanh_pho: "",
        }));
        setGpsMsg("Đã lấy vị trí GPS. Bấm Lưu thông tin quán để áp dụng cho thời tiết.");
        setGpsBusy(false);
      },
      () => {
        setGpsMsg("Không lấy được vị trí. Nhập địa chỉ quán bên dưới.");
        setGpsBusy(false);
      },
      { timeout: 10000 },
    );
  }

  function updatePromo(index: number, patch: Partial<Promotion>) {
    setPromos((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  if (!getToken()) return <AuthGate />;

  if (loading) {
    return (
      <>
        <Loading skeleton="form">Đang tải cấu hình quán…</Loading>
        <Toasts toasts={toasts} onDismiss={dismiss} />
      </>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-4 pb-32 pt-8">
      <PageHeader
        kicker="Cấu hình hệ thống"
        title="Thông tin quán & Trợ lý AI"
        meta="Nhập thông tin thực tế của quán — AI agent và các trợ lý chăm sóc khách đọc trực tiếp từ đây (ADR-008)."
      />

      {error ? (
        <div className="mb-6">
          <Alert kind="err">{error}</Alert>
        </div>
      ) : null}

      {/* Profile Completion Quality Meter */}
      <section className="mb-8 rounded-2xl border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
          <div>
            <h2 className="text-sm font-bold text-[var(--nq-fg)] flex items-center gap-2">
              <Icon name="zap" className="h-4 w-4 text-[var(--nq-copper)]" />
              Độ hoàn thiện hồ sơ quán
            </h2>
            <p className="text-xs text-[var(--nq-muted)] mt-0.5">
              Hồ sơ càng đầy đủ thì AI agent càng trả lời chính xác, tránh trường hợp phải nói &quot;chưa cập nhật&quot;.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-lg font-black text-[var(--nq-copper)]">
              {completionScore}%
            </span>
            <Badge
              variant={
                completionScore >= 80
                  ? "success"
                  : completionScore >= 50
                    ? "primary"
                    : "warning"
              }
            >
              {completionScore >= 80
                ? "Rất đầy đủ"
                : completionScore >= 50
                  ? "Khá đầy đủ"
                  : "Chưa đầy đủ"}
            </Badge>
          </div>
        </div>

        <ProgressBar value={completionScore} max={100} className="h-2 rounded-full" />

        {missingItems.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 pt-2 text-xs">
            <span className="text-[var(--nq-muted)]">Gợi ý bổ sung:</span>
            {missingItems.map((item, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setTab(item.tab)}
                className="inline-flex items-center gap-1 rounded-full border border-[var(--nq-line)] bg-[var(--nq-bg)] px-2.5 py-0.5 text-[11px] text-[var(--nq-muted)] hover:border-[var(--nq-copper)] hover:text-[var(--nq-copper)] transition-colors"
              >
                <span>+ {item.label}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Tab Navigation */}
      <div className="mb-6">
        <TabBar label="Danh mục cấu hình quán">
          <TabButton active={tab === "general"} onClick={() => setTab("general")}>
            <span className="flex items-center gap-1.5">
              <Icon name="coffee" className="h-4 w-4" />
              <span>1. Thông tin chung</span>
            </span>
          </TabButton>
          <TabButton active={tab === "address"} onClick={() => setTab("address")}>
            <span className="flex items-center gap-1.5">
              <Icon name="location" className="h-4 w-4" />
              <span>2. Địa chỉ & Bản đồ</span>
            </span>
          </TabButton>
          <TabButton active={tab === "contact"} onClick={() => setTab("contact")}>
            <span className="flex items-center gap-1.5">
              <Icon name="phone" className="h-4 w-4" />
              <span>3. Kênh liên hệ</span>
            </span>
          </TabButton>
          <TabButton active={tab === "operations"} onClick={() => setTab("operations")}>
            <span className="flex items-center gap-1.5">
              <Icon name="clock" className="h-4 w-4" />
              <span>4. Giờ mở & Tiện ích</span>
            </span>
          </TabButton>
          <TabButton active={tab === "ai"} onClick={() => setTab("ai")}>
            <span className="flex items-center gap-1.5">
              <Icon name="bot" className="h-4 w-4" />
              <span>5. Huấn luyện AI</span>
            </span>
          </TabButton>
          <TabButton active={tab === "promotions"} onClick={() => setTab("promotions")}>
            <span className="flex items-center gap-1.5">
              <Icon name="tag" className="h-4 w-4" />
              <span>6. Khuyến mãi</span>
            </span>
          </TabButton>
        </TabBar>
      </div>

      {/* TAB 1: THÔNG TIN CHUNG & NHẬN DIỆN */}
      {tab === "general" && (
        <section className="space-y-6 rounded-2xl border border-[var(--nq-line)] bg-[var(--nq-surface)] p-6 shadow-sm">
          <div>
            <h2 className="text-base font-bold text-[var(--nq-fg)] flex items-center gap-2">
              <Icon name="coffee" className="h-5 w-5 text-[var(--nq-copper)]" />
              Thông tin nhận diện quán
            </h2>
            <p className="text-xs text-[var(--nq-muted)] mt-1">
              Tên thương hiệu, khẩu hiệu và phong cách phục vụ của quán.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tên quán *" hint="Tên thương hiệu chính thức xuất hiện trong mọi hội thoại">
              <Input
                value={profile.ten_quan}
                onChange={(e) => setField("ten_quan", e.target.value)}
                placeholder="VD: Nhịp Quán Specialty Coffee"
              />
            </Field>

            <Field label="Khẩu hiệu / Slogan" hint="Thông điệp nổi bật hoặc định vị của quán">
              <Input
                value={profile.slogan}
                onChange={(e) => setField("slogan", e.target.value)}
                placeholder="VD: Cà phê mộc, không gian làm việc tĩnh lặng"
              />
            </Field>
          </div>

          <Field
            label="Mô tả phong cách quán"
            hint="Giới thiệu ngắn về quán để AI tư vấn khi khách hỏi không gian, mục đích gặp gỡ"
          >
            <Textarea
              value={profile.mo_ta}
              onChange={(e) => setField("mo_ta", e.target.value)}
              placeholder="VD: Quán cà phê yên tĩnh tại trung tâm, thích hợp làm việc nhóm, đọc sách, gặp gỡ đối tác. Menu đồ uống chuyên cà phê pha thủ công và bánh ngọt homemade."
              rows={3}
            />
          </Field>

          <Field
            label="Khoảng giá đồ uống"
            hint="Để bot thông tin nhanh khi khách hỏi giá trung bình"
          >
            <Input
              value={profile.khoang_gia}
              onChange={(e) => setField("khoang_gia", e.target.value)}
              placeholder="VD: 35.000đ - 75.000đ"
            />
          </Field>
        </section>
      )}

      {/* TAB 2: ĐỊA CHỈ & HÀNH CHÍNH (TÍCH HỢP ADDRESS API) */}
      {tab === "address" && (
        <section className="space-y-6 rounded-2xl border border-[var(--nq-line)] bg-[var(--nq-surface)] p-6 shadow-sm">
          <div>
            <h2 className="text-base font-bold text-[var(--nq-fg)] flex items-center gap-2">
              <Icon name="location" className="h-5 w-5 text-[var(--nq-copper)]" />
              Địa chỉ & Định vị hành chính
            </h2>
            <p className="text-xs text-[var(--nq-muted)] mt-1">
              Tích hợp danh mục địa chính Việt Nam (Tỉnh/Thành → Quận/Huyện → Phường/Xã) giúp chuẩn hóa địa chỉ, hỗ trợ tính năng định vị thời tiết và chỉ đường cho khách.
            </p>
          </div>

          <AddressSelector
            data={{
              dia_chi: profile.dia_chi,
              dia_chi_chi_tiet: profile.dia_chi_chi_tiet,
              phuong_xa: profile.phuong_xa,
              phuong_xa_code: profile.phuong_xa_code,
              quan_huyen: profile.quan_huyen,
              quan_huyen_code: profile.quan_huyen_code,
              tinh: profile.tinh,
              tinh_code: profile.tinh_code,
              thanh_pho: profile.thanh_pho,
              google_maps_url: profile.google_maps_url,
            }}
            onChange={handleAddressChange}
          />

          <div className="rounded-xl border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-4 space-y-3">
            <div>
              <h3 className="text-xs font-bold text-[var(--nq-fg)]">Toạ độ GPS (Dành cho AI Forecast thời tiết & Quánverse)</h3>
              <p className="mt-1 text-xs text-[var(--nq-muted)]">
                Lấy toạ độ GPS trực tiếp từ trình duyệt (hệ thống tự động dùng toạ độ này để dự báo thời tiết Open-Meteo chuẩn xác nhất).
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Btn type="button" variant="ghost" disabled={gpsBusy} onClick={layViTriGps}>
                {gpsBusy ? "Đang lấy vị trí…" : "Lấy vị trí GPS"}
              </Btn>
              {profile.lat != null && profile.lon != null ? (
                <span className="text-sm font-mono text-[var(--nq-accent)]" data-testid="cau-hinh-gps-coords">
                  GPS: {profile.lat.toFixed(4)}, {profile.lon.toFixed(4)}
                </span>
              ) : (
                <span className="text-sm text-[var(--nq-muted)]">Chưa có toạ độ GPS</span>
              )}
            </div>
            {gpsMsg ? <p className="text-xs text-[var(--nq-muted)]">{gpsMsg}</p> : null}
          </div>
        </section>
      )}

      {/* TAB 3: KÊNH LIÊN HỆ & MẠNG XÃ HỘI */}
      {tab === "contact" && (
        <section className="space-y-6 rounded-2xl border border-[var(--nq-line)] bg-[var(--nq-surface)] p-6 shadow-sm">
          <div>
            <h2 className="text-base font-bold text-[var(--nq-fg)] flex items-center gap-2">
              <Icon name="phone" className="h-5 w-5 text-[var(--nq-copper)]" />
              Kênh liên hệ & Mạng xã hội
            </h2>
            <p className="text-xs text-[var(--nq-muted)] mt-1">
              Số hotline thật, email và các kênh tiếp nhận phản hồi của khách hàng.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Hotline chính *" hint="Số điện thoại gọi đặt bàn hoặc hỗ trợ khẩn cấp">
              <Input
                value={profile.hotline}
                onChange={(e) => setField("hotline", e.target.value)}
                placeholder="VD: 0901234567"
              />
            </Field>

            <Field label="Hotline phụ / Số quản lý" hint="Số dự phòng khi máy bận">
              <Input
                value={profile.hotline_phu}
                onChange={(e) => setField("hotline_phu", e.target.value)}
                placeholder="VD: 0909888999"
              />
            </Field>
            <Field label="Email liên hệ của quán" hint="Tiếp nhận hóa đơn, khiếu nại hoặc hợp tác">
              <Input
                type="email"
                value={profile.email}
                onChange={(e) => setField("email", e.target.value)}
                placeholder="VD: contact@nhipquan.vn hoặc quan.cskh@gmail.com"
              />
            </Field>

            <Field label="Website quán" hint="Trang web chính thức nếu có">
              <Input
                value={profile.website}
                onChange={(e) => setField("website", e.target.value)}
                placeholder="VD: https://nhipquan.vn"
              />
            </Field>
          </div>

          <Field
            label="Facebook Fanpage / Zalo OA"
            hint="Đường link fanpage để bot gửi cho khách khi cần kết nối mạng xã hội"
          >
            <Input
              value={profile.fanpage_url}
              onChange={(e) => setField("fanpage_url", e.target.value)}
              placeholder="VD: https://facebook.com/nhipquancoffee"
            />
          </Field>
        </section>
      )}

      {/* TAB 4: GIỜ HOẠT ĐỘNG, TIỆN ÍCH & THANH TOÁN */}
      {tab === "operations" && (
        <section className="space-y-6 rounded-2xl border border-[var(--nq-line)] bg-[var(--nq-surface)] p-6 shadow-sm">
          <div>
            <h2 className="text-base font-bold text-[var(--nq-fg)] flex items-center gap-2">
              <Icon name="clock" className="h-5 w-5 text-[var(--nq-copper)]" />
              Vận hành, Tiện ích & Thông tin thanh toán
            </h2>
            <p className="text-xs text-[var(--nq-muted)] mt-1">
              Giờ phục vụ, chính sách đặt bàn, wifi và số tài khoản ngân hàng nhận chuyển khoản cọc bàn.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Giờ mở cửa tóm tắt *" hint="Bot đọc dòng này khi khách hỏi giờ hoạt động">
              <Input
                value={profile.gio_mo_cua}
                onChange={(e) => setField("gio_mo_cua", e.target.value)}
                placeholder="VD: 07:00 - 22:30 (tất cả các ngày)"
              />
            </Field>

            <Field label="Giờ mở cửa chi tiết (tùy chọn)" hint="Khung giờ ngày thường vs cuối tuần">
              <Input
                value={profile.gio_mo_cua_chi_tiet}
                onChange={(e) => setField("gio_mo_cua_chi_tiet", e.target.value)}
                placeholder="VD: T2 - T6: 07:00 - 22:00 | T7 - CN: 06:30 - 23:00"
              />
            </Field>
          </div>

          <Field
            label="Chính sách nhận đặt bàn"
            hint="Quy định giữ bàn bao lâu, nhóm tối thiểu, yêu cầu cọc nếu nhóm đông"
          >
            <Input
              value={profile.chinh_sach_dat_ban}
              onChange={(e) => setField("chinh_sach_dat_ban", e.target.value)}
              placeholder="VD: Nhận giữ chỗ tối đa 15 phút. Nhóm trên 6 người vui lòng đặt cọc trước."
            />
          </Field>

          {/* Tiện ích quán */}
          <div className="rounded-xl border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-4 space-y-3">
            <label className="text-xs font-bold text-[var(--nq-fg)] flex items-center justify-between">
              <span>Tiện ích nổi bật của quán</span>
              <span className="text-[11px] font-normal text-[var(--nq-muted)]">
                Bấm để chọn nhanh các tiện ích có sẵn
              </span>
            </label>
            <div className="flex flex-wrap gap-2">
              {POPULAR_AMENITIES.map((item) => {
                const isSelected = profile.tien_ich.includes(item);
                return (
                  <button
                    key={item}
                    type="button"
                    onClick={() => toggleAmenity(item)}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition-colors border ${
                      isSelected
                        ? "border-[var(--nq-copper)] bg-[var(--nq-copper)]/10 text-[var(--nq-copper)] font-medium"
                        : "border-[var(--nq-line)] bg-[var(--nq-bg)] text-[var(--nq-muted)] hover:border-[var(--nq-line-hover)] hover:text-[var(--nq-fg)]"
                    }`}
                  >
                    <Icon name={isSelected ? "check" : "plus"} className="h-3 w-3" />
                    <span>{item}</span>
                  </button>
                );
              })}
            </div>
            <Input
              value={profile.tien_ich}
              onChange={(e) => setField("tien_ich", e.target.value)}
              placeholder="Hoặc tự gõ thêm tiện ích khác cách nhau bởi dấu phẩy..."
            />
          </div>

          {/* Mạng Wifi */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tên mạng Wifi (SSID)" hint="Tên mạng phát trong quán">
              <Input
                value={profile.wifi_ssid}
                onChange={(e) => setField("wifi_ssid", e.target.value)}
                placeholder="VD: NhipQuan_Guest"
              />
            </Field>

            <Field label="Mật khẩu Wifi" hint="Để trống nếu là mạng mở không mật khẩu">
              <div className="relative">
                <Input
                  type={showWifiPass ? "text" : "password"}
                  value={profile.wifi_pass}
                  onChange={(e) => setField("wifi_pass", e.target.value)}
                  placeholder="Mật khẩu wifi thật"
                />
                <button
                  type="button"
                  onClick={() => setShowWifiPass(!showWifiPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--nq-muted)] hover:text-[var(--nq-fg)]"
                >
                  {showWifiPass ? "Ẩn" : "Hiện"}
                </button>
              </div>
            </Field>
          </div>

          {/* Thông tin tài khoản ngân hàng chuyển khoản */}
          <div className="rounded-xl border border-[var(--nq-line)] p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[var(--nq-fg)]">
                  Tài khoản chuyển khoản / Đặt cọc bàn
                </h3>
                <p className="text-xs text-[var(--nq-muted)]">
                  Khi khách hỏi STK cọc hoặc thanh toán online, AI bot sẽ cung cấp chính xác thông tin này.
                </p>
              </div>
              <Badge variant="primary">Thanh toán</Badge>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Ngân hàng">
                <Select
                  value={
                    POPULAR_BANKS.includes(profile.ngan_hang)
                      ? profile.ngan_hang
                      : profile.ngan_hang
                        ? "Khác"
                        : ""
                  }
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val === "Khác") {
                      setField("ngan_hang", "");
                    } else {
                      setField("ngan_hang", val);
                    }
                  }}
                >
                  <option value="">-- Chọn ngân hàng --</option>
                  {POPULAR_BANKS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </Select>
                {(!POPULAR_BANKS.slice(0, -1).includes(profile.ngan_hang) ||
                  profile.ngan_hang === "") && (
                  <div className="mt-2">
                    <Input
                      value={profile.ngan_hang}
                      onChange={(e) => setField("ngan_hang", e.target.value)}
                      placeholder="Nhập tên ngân hàng khác..."
                    />
                  </div>
                )}
              </Field>

              <Field label="Số tài khoản">
                <Input
                  value={profile.stk_ngan_hang}
                  onChange={(e) => setField("stk_ngan_hang", e.target.value)}
                  placeholder="VD: 0071001234567"
                />
              </Field>

              <Field label="Tên chủ tài khoản">
                <Input
                  value={profile.chu_tai_khoan}
                  onChange={(e) => setField("chu_tai_khoan", e.target.value.toUpperCase())}
                  placeholder="VD: NGUYEN VAN A"
                />
              </Field>
            </div>
          </div>
        </section>
      )}

      {/* TAB 5: HUẤN LUYỆN AI AGENT & SIMULATOR */}
      {tab === "ai" && (
        <section className="space-y-6 rounded-2xl border border-[var(--nq-line)] bg-[var(--nq-surface)] p-6 shadow-sm">
          <FbRuntimeBanner />
          <div>
            <h2 className="text-base font-bold text-[var(--nq-fg)] flex items-center gap-2">
              <Icon name="bot" className="h-5 w-5 text-[var(--nq-copper)]" />
              Hướng dẫn riêng cho AI Agent & Mô phỏng trả lời
            </h2>
            <p className="text-xs text-[var(--nq-muted)] mt-1">
              Chỉ đạo giọng văn, nguyên tắc ứng xử và điều cấm kỵ. Lời nhắc này sẽ được chèn trực tiếp vào prompt của mọi agent trả lời khách.
            </p>
          </div>

          {/* Quick preset chips */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-[var(--nq-fg)]">
              Gợi ý nguyên tắc phổ biến (Bấm để thêm vào lời nhắc):
            </label>
            <div className="flex flex-wrap gap-2">
              {AI_PROMPT_SUGGESTIONS.map((sug, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => appendAiSuggestion(sug)}
                  className="rounded-lg border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] px-2.5 py-1 text-xs text-[var(--nq-muted)] hover:border-[var(--nq-copper)] hover:text-[var(--nq-copper)] text-left transition-colors"
                >
                  + {sug}
                </button>
              ))}
            </div>
          </div>

          <Field
            label="Nội dung hướng dẫn riêng cho AI"
            hint="Viết tự do theo gạch đầu dòng. AI sẽ nghiêm túc tuân thủ mọi nguyên tắc ở đây."
          >
            <Textarea
              value={profile.huong_dan_agent}
              onChange={(e) => setField("huong_dan_agent", e.target.value)}
              placeholder="VD:&#10;- Luôn xưng em, gọi khách là mình.&#10;- Giới thiệu cà phê Robusta mộc nếu khách hỏi gu đậm.&#10;- Không hứa hẹn giảm giá ngoài các ưu đãi đang chạy."
              rows={8}
            />
          </Field>

          {/* LIVE BOT PREVIEW / SIMULATOR */}
          <div className="rounded-xl border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-[var(--nq-fg)] flex items-center gap-2">
                <Icon name="chat" className="h-4 w-4 text-[var(--nq-copper)]" />
                Mô phỏng trả lời thực tế của AI Bot
              </h3>
              <Badge variant="outline">Live Preview</Badge>
            </div>

            <div className="space-y-3 font-sans text-xs">
              {/* Question 1: Dia chi */}
              <div className="rounded-lg border border-[var(--nq-line)] bg-[var(--nq-bg)] p-3">
                <p className="font-semibold text-[var(--nq-copper)]">
                  Khách: &ldquo;Quán ở đâu vậy em?&rdquo;
                </p>
                <p className="mt-1 text-[var(--nq-fg)]">
                  {profile.dia_chi ? (
                    <>
                      Dạ quán em ở tại{" "}
                      <strong>{profile.dia_chi}</strong>
                      {profile.google_maps_url ? " (mình có thể xem chỉ đường trên Google Maps nhé ạ)." : "."}
                    </>
                  ) : (
                    <span className="text-[var(--nq-st-err)] font-italic">
                      (Chưa cập nhật địa chỉ — Bot sẽ trả lời: &ldquo;Dạ hiện tại thông tin địa chỉ quán chưa được cập nhật, mình vui lòng liên hệ hotline ạ&rdquo;)
                    </span>
                  )}
                </p>
              </div>

              {/* Question 2: Gio mo cua & Tien ich */}
              <div className="rounded-lg border border-[var(--nq-line)] bg-[var(--nq-bg)] p-3">
                <p className="font-semibold text-[var(--nq-copper)]">
                  Khách: &ldquo;Quán mở cửa mấy giờ và có chỗ để xe không?&rdquo;
                </p>
                <p className="mt-1 text-[var(--nq-fg)]">
                  Dạ quán mở cửa{" "}
                  <strong>{profile.gio_mo_cua || "(chưa cập nhật giờ)"}</strong>.
                  {profile.tien_ich ? (
                    <> Quán có các tiện ích: {profile.tien_ich}.</>
                  ) : (
                    <> Về tiện ích giữ xe, quán chưa cập nhật chi tiết ạ.</>
                  )}
                </p>
              </div>

              {/* Question 3: Thanh toan & STK */}
              <div className="rounded-lg border border-[var(--nq-line)] bg-[var(--nq-bg)] p-3">
                <p className="font-semibold text-[var(--nq-copper)]">
                  Khách: &ldquo;Cho mình xin số tài khoản chuyển khoản cọc bàn nhé&rdquo;
                </p>
                <p className="mt-1 text-[var(--nq-fg)]">
                  {profile.ngan_hang && profile.stk_ngan_hang ? (
                    <>
                      Dạ mình có thể chuyển khoản qua Ngân hàng{" "}
                      <strong>{profile.ngan_hang}</strong>, STK:{" "}
                      <strong>{profile.stk_ngan_hang}</strong>
                      {profile.chu_tai_khoan ? ` (Chủ TK: ${profile.chu_tai_khoan})` : ""} ạ.
                    </>
                  ) : (
                    <span className="text-[var(--nq-st-err)] font-italic">
                      (Chưa cấu hình tài khoản ngân hàng — Bot sẽ hướng dẫn khách liên hệ hotline)
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* TAB 6: KHUYẾN MÃI */}
      {tab === "promotions" && (
        <section className="space-y-6 rounded-2xl border border-[var(--nq-line)] bg-[var(--nq-surface)] p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-[var(--nq-fg)] flex items-center gap-2">
                <Icon name="tag" className="h-5 w-5 text-[var(--nq-copper)]" />
                Chương trình khuyến mãi & Ưu đãi
              </h2>
              <p className="text-xs text-[var(--nq-muted)] mt-1">
                Bot sẽ liệt kê các ưu đãi này khi khách hỏi khuyến mãi, combo hoặc giảm giá.
              </p>
            </div>
            <Btn
              variant="secondary"
              size="sm"
              onClick={() =>
                setPromos((prev) => [...prev, { tieu_de: "", chi_tiet: "", hieu_luc: "" }])
              }
            >
              <Icon name="plus" className="h-4 w-4 mr-1" />
              Thêm khuyến mãi
            </Btn>
          </div>

          {promos.length === 0 ? (
            <Alert kind="info">
              Hiện chưa có chương trình khuyến mãi nào được cấu hình. Bấm nút &quot;Thêm khuyến mãi&quot; để tạo ưu đãi mới.
            </Alert>
          ) : (
            <div className="grid gap-4">
              {promos.map((p, i) => (
                <div
                  key={p.id || `km_${i}`}
                  className="grid gap-3 rounded-xl border border-[var(--nq-line)] bg-[var(--nq-bg)] p-4 shadow-sm"
                >
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Tiêu đề ưu đãi *">
                      <Input
                        value={p.tieu_de}
                        onChange={(e) => updatePromo(i, { tieu_de: e.target.value })}
                        placeholder="VD: Combo Sáng Tỉnh Táo"
                      />
                    </Field>
                    <Field label="Thời gian hiệu lực">
                      <Input
                        value={p.hieu_luc}
                        onChange={(e) => updatePromo(i, { hieu_luc: e.target.value })}
                        placeholder="VD: 07:00 - 09:30 từ Thứ 2 đến Thứ 6"
                      />
                    </Field>
                  </div>
                  <Field label="Chi tiết chương trình">
                    <Input
                      value={p.chi_tiet}
                      onChange={(e) => updatePromo(i, { chi_tiet: e.target.value })}
                      placeholder="VD: Giảm 15% khi mua 01 cà phê sữa đá kèm 01 bánh mì pate"
                    />
                  </Field>
                  <div className="flex justify-end pt-1">
                    <Btn
                      variant="danger"
                      size="sm"
                      onClick={() => setPromos((prev) => prev.filter((_, j) => j !== i))}
                    >
                      <Icon name="trash" className="h-3.5 w-3.5 mr-1" />
                      Xóa ưu đãi
                    </Btn>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* STICKY BOTTOM ACTION BAR */}
      <div className="fixed bottom-4 left-4 right-4 z-20 mx-auto max-w-4xl rounded-2xl border border-[var(--nq-line)] bg-[var(--nq-surface)]/95 backdrop-blur-md p-4 shadow-xl flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {dirty ? (
            <span className="flex items-center gap-1.5 rounded-full bg-[var(--nq-copper)]/10 px-3 py-1 text-xs font-medium text-[var(--nq-copper)]">
              <span className="h-2 w-2 rounded-full bg-[var(--nq-copper)] animate-pulse" />
              Có thay đổi chưa lưu
            </span>
          ) : (
            <span className="text-xs text-[var(--nq-muted)] flex items-center gap-1.5">
              <Icon name="check" className="h-4 w-4 text-[var(--nq-st-ok)]" />
              Dữ liệu đã được lưu
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Btn variant="ghost" onClick={() => void load()} disabled={saving}>
            <Icon name="refresh" className="h-4 w-4 mr-1" />
            Tải lại
          </Btn>
          {tab === "promotions" ? (
            <Btn
              variant="primary"
              onClick={() => void savePromos()}
              busy={saving}
              busyLabel="Đang lưu…"
            >
              Lưu khuyến mãi
            </Btn>
          ) : (
            <Btn
              variant="primary"
              onClick={() => void saveProfile()}
              busy={saving}
              busyLabel="Đang lưu…"
            >
              Lưu thông tin quán
            </Btn>
          )}
        </div>
      </div>

      <Toasts toasts={toasts} onDismiss={dismiss} />
    </main>
  );
}
