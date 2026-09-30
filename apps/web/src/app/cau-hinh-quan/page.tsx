"use client";

/**
 * Cấu hình quán & hướng dẫn AI agent — nơi quản lý/chủ quán nhập THÔNG TIN THẬT
 * (địa chỉ, giờ mở cửa, hotline, wifi) và HƯỚNG DẪN RIÊNG cho AI agent thay vì
 * để bot dùng số liệu mặc định trong code (ADR-008 — không dữ liệu giả).
 *
 * Lưu vào KV `store_profile` / `store_promotions` qua
 * GET/PUT /api/v1/store/profile và /api/v1/store/promotions.
 * Mọi agent khách-facing (AG-FBPAGE, AG-CONCIERGE, comment, mail) đọc từ đây.
 */

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend, ApiError } from "../../lib/api";
import { viError, type ErrorCopy } from "../../lib/present";
import { getToken } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  Field,
  Input,
  Loading,
  PageHeader,
  Textarea,
  useToasts,
  Toasts,
} from "../../ui/kit";

type StoreProfile = {
  ten_quan: string;
  dia_chi: string;
  tinh: string;
  thanh_pho: string;
  hotline: string;
  gio_mo_cua: string;
  wifi_ssid: string;
  wifi_pass: string;
  mo_ta: string;
  chinh_sach_dat_ban: string;
  huong_dan_agent: string;
};

type Promotion = {
  id?: string;
  tieu_de: string;
  chi_tiet: string;
  hieu_luc: string;
};

const EMPTY_PROFILE: StoreProfile = {
  ten_quan: "",
  dia_chi: "",
  tinh: "",
  thanh_pho: "",
  hotline: "",
  gio_mo_cua: "",
  wifi_ssid: "",
  wifi_pass: "",
  mo_ta: "",
  chinh_sach_dat_ban: "",
  huong_dan_agent: "",
};

/** Nhắc mẫu cho textarea hướng dẫn AI — đặt thành placeholder, ghi đè. */
const HUONG_DAN_GOI_Y =
  "Ví dụ:\n" +
  "- Luôn xưng \"em\", gọi khách là \"mình\" như đang chat thân mật.\n" +
  "- Nếu quán hết món, nói thật và gợi ý món thay thế, đừng hứa suông.\n" +
  "- Không nhắc đến đối thủ cạnh tranh trong khu vực.\n" +
  "- Khuyến khích khách thử đặt bàn nếu nhóm ≥ 4 người.";

const COPY_LOAD: ErrorCopy = { doing: "đọc được cấu hình quán" };

export default function CauHinhQuanPage() {
  const { toasts, push, dismiss } = useToasts();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState<StoreProfile>(EMPTY_PROFILE);
  const [promos, setPromos] = useState<Promotion[]>([]);
  const [error, setError] = useState("");
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
      setProfile({ ...EMPTY_PROFILE, ...p });
      setPromos(Array.isArray(pr) ? pr : []);
      setSavedSnapshot({ profile: { ...EMPTY_PROFILE, ...p }, promos: Array.isArray(pr) ? [...pr] : [] });
    } catch (e) {
      setError(viError(e, COPY_LOAD));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // ── Dirty guard: rời trang khi chưa lưu → cảnh báo (trình duyệt hỏi). ──
  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (!dirty) return;
      e.preventDefault();
      // Chrome yêu cầu set returnValue để hiện hộp thoại xác nhận.
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  // Trường quan trọng trống → bot trả "chưa cập nhật" khi khách hỏi. Hiện chip
  // nhắc ngay trên form để quán biết bot chưa có gì để trả lời khách.
  const IMPORTANT_LABELS: Record<string, string> = {
    ten_quan: "tên quán",
    dia_chi: "địa chỉ",
    gio_mo_cua: "giờ mở cửa",
    hotline: "hotline",
  };
  const missingImportant = (["ten_quan", "dia_chi", "gio_mo_cua", "hotline"] as const)
    .filter((k) => !profile[k].trim())
    .map((k) => IMPORTANT_LABELS[k]);


  async function saveProfile() {
    setSaving(true);
    try {
      const cleaned: StoreProfile = {
        ...profile,
        ten_quan: profile.ten_quan.trim(),
        dia_chi: profile.dia_chi.trim(),
        tinh: profile.tinh.trim(),
        thanh_pho: profile.thanh_pho.trim(),
        hotline: profile.hotline.trim(),
        gio_mo_cua: profile.gio_mo_cua.trim(),
        wifi_ssid: profile.wifi_ssid.trim(),
        wifi_pass: profile.wifi_pass.trim(),
      };
      setProfile(cleaned);
      await apiSend("/api/v1/store/profile", cleaned, "PUT");
      setSavedSnapshot((prev) => ({ profile: cleaned, promos: prev?.promos ?? promos }));
      const missing = ["dia_chi", "gio_mo_cua", "hotline"].filter((k) => !cleaned[k as keyof StoreProfile]);
      push(
        missing.length === 0
          ? "Đã lưu. Bot giờ trả lời khách bằng đúng thông tin này."
          : `Đã lưu, nhưng còn ${missing.length} trường trống — bot sẽ trả “chưa cập nhật” khi khách hỏi.`,
        missing.length === 0 ? "ok" : "err",
      );
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 403
          ? "Chỉ quản lý hoặc chủ quán mới được sửa cấu hình."
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
      push("Đã lưu chương trình khuyến mãi.", "ok");
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

  function setField<K extends keyof StoreProfile>(key: K, value: string) {
    setProfile((prev) => ({ ...prev, [key]: value }));
  }

  function updatePromo(index: number, patch: Partial<Promotion>) {
    setPromos((prev) =>
      prev.map((p, i) => (i === index ? { ...p, ...patch } : p)),
    );
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
    <main className="mx-auto w-full max-w-3xl px-4 pb-24 pt-8">
      <PageHeader
        kicker="Cấu hình"
        title="Thông tin quán & Hướng dẫn AI"
        meta="Quản lý/chủ quán nhập thông tin thật — AI agent trả lời khách dựa trên đây, không tự bịa."
      />

        {error ? (
          <div className="mb-4">
            <Alert kind="err">{error}</Alert>
          </div>
        ) : null}
        {dirty ? (
          <div className="mb-4">
            <Alert kind="info">
              Bạn đang có thay đổi chưa lưu — bấm “Lưu thông tin quán”/“Lưu khuyến
              mãi” trước khi rời trang.
            </Alert>
          </div>
        ) : null}

        {missingImportant.length > 0 ? (
          <div className="mb-4">
            <Alert kind="err">
              Còn thiếu: {missingImportant.join(", ")} — khách hỏi những mục này
              bot sẽ trả “chưa cập nhật”.
            </Alert>
          </div>
        ) : null}

        <section className="mb-8">
          <h2 className="mb-1 text-lg font-bold">1. Thông tin quán</h2>
          <p className="mb-4 text-sm text-[var(--nq-fg-muted)]">
            Bot dùng các trường này khi khách hỏi giờ mở cửa, địa chỉ, wifi...
            Trường nào bỏ trống thì bot sẽ trả lời “chưa cập nhật” thay vì đoán.
          </p>
          <div className="grid gap-x-4 sm:grid-cols-2">
            <Field label="Tên quán">
              <Input
                value={profile.ten_quan}
                onChange={(e) => setField("ten_quan", e.target.value)}
                placeholder="Nhập tên quán"
              />
            </Field>
            <Field label="Hotline">
              <Input
                value={profile.hotline}
                onChange={(e) => setField("hotline", e.target.value)}
                placeholder="VD: 0901234567 (số thật)"
              />
            </Field>
            <Field label="Địa chỉ">
              <Input
                value={profile.dia_chi}
                onChange={(e) => setField("dia_chi", e.target.value)}
                placeholder="VD: 45 Nguyễn Huệ, P. Bến Nghé, Q. 1, TP. HCM"
              />
            </Field>
            <Field label="Thành phố / Quận">
              <Input
                value={profile.thanh_pho}
                onChange={(e) => setField("thanh_pho", e.target.value)}
                placeholder="VD: Quận 1 hoặc TP. Hồ Chí Minh"
              />
            </Field>
            <Field label="Tỉnh / Thành phố trực thuộc TW">
              <Input
                value={profile.tinh}
                onChange={(e) => setField("tinh", e.target.value)}
                placeholder="VD: Hồ Chí Minh, Hà Nội, Đà Nẵng"
              />
            </Field>
            <Field label="Giờ mở cửa">
              <Input
                value={profile.gio_mo_cua}
                onChange={(e) => setField("gio_mo_cua", e.target.value)}
                placeholder="VD: 07:00 - 22:30 (tất cả các ngày)"
              />
            </Field>
            <Field label="Chính sách đặt bàn">
              <Input
                value={profile.chinh_sach_dat_ban}
                onChange={(e) => setField("chinh_sach_dat_ban", e.target.value)}
                placeholder="VD: Nhận đặt trước cho nhóm từ 4 người"
              />
            </Field>
            <Field label="Wifi (tên mạng)">
              <Input
                value={profile.wifi_ssid}
                onChange={(e) => setField("wifi_ssid", e.target.value)}
                placeholder="VD: NhipQuan_Guest (tên wifi thật)"
              />
            </Field>
            <Field label="Wifi (mật khẩu)">
              <Input
                value={profile.wifi_pass}
                onChange={(e) => setField("wifi_pass", e.target.value)}
                placeholder="Để trống nếu không muốn cung cấp"
              />
            </Field>
          </div>
          <Field label="Mô tả quán">
            <Textarea
              value={profile.mo_ta}
              onChange={(e) => setField("mo_ta", e.target.value)}
              placeholder="VD: Cà phê sạch, không gian yên tĩnh làm việc và gặp gỡ bạn bè."
            />
          </Field>
        </section>

        <section className="mb-8">
          <h2 className="mb-1 text-lg font-bold">2. Hướng dẫn riêng cho AI agent</h2>
          <p className="mb-4 text-sm text-[var(--nq-fg-muted)]">
            Viết tự do — AI sẽ tuân theo khi trả lời khách qua Messenger/comment.
            Ví dụ: cách xưng hô, món nào ưu tiên tư vấn, câu nào cấm nói, cách xử
            lý khi hết món.
          </p>
          <Textarea
            value={profile.huong_dan_agent}
            onChange={(e) => setField("huong_dan_agent", e.target.value)}
            placeholder={HUONG_DAN_GOI_Y}
            rows={7}
          />
          <div className="mt-2">
            <Alert kind="info">
              Hướng dẫn này được chèn vào prompt của mọi agent trả lời khách
              (Messenger, comment, mail) và có hiệu lực ngay sau khi lưu.
            </Alert>
          </div>
        </section>

        <section className="mb-8">
          <div className="mb-1 flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold">3. Khuyến mãi</h2>
            <Btn
              variant="ghost"
              onClick={() =>
                setPromos((prev) => [...prev, { tieu_de: "", chi_tiet: "", hieu_luc: "" }])
              }
            >
              Thêm khuyến mãi
            </Btn>
          </div>
          <p className="mb-4 text-sm text-[var(--nq-fg-muted)]">
            Bot liệt kê các chương trình này khi khách hỏi ưu đãi. Bỏ trống tiêu
            đề sẽ không được lưu.
          </p>
          {promos.length === 0 ? (
            <Alert kind="info">Chưa có khuyến mãi nào.</Alert>
          ) : (
            <div className="grid gap-4">
              {promos.map((p, i) => (
                <div
                  key={p.id || `km_new_${i}`}
                  className="grid gap-3 rounded-xl border border-[var(--nq-line)] p-4"
                >
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Tiêu đề">
                      <Input
                        value={p.tieu_de}
                        onChange={(e) => updatePromo(i, { tieu_de: e.target.value })}
                        placeholder="VD: Combo Sáng Tỉnh Táo"
                      />
                    </Field>
                    <Field label="Hiệu lực">
                      <Input
                        value={p.hieu_luc}
                        onChange={(e) => updatePromo(i, { hieu_luc: e.target.value })}
                        placeholder="VD: 07:00 - 09:00 hàng ngày"
                      />
                    </Field>
                  </div>
                  <Field label="Chi tiết">
                    <Input
                      value={p.chi_tiet}
                      onChange={(e) => updatePromo(i, { chi_tiet: e.target.value })}
                      placeholder="VD: Giảm 10% khi mua cà phê sữa + bánh mì"
                    />
                  </Field>
                  <div className="flex justify-end">
                    <Btn
                      variant="danger"
                      onClick={() => setPromos((prev) => prev.filter((_, j) => j !== i))}
                    >
                      Xóa
                    </Btn>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="sticky bottom-4 z-10 flex flex-wrap items-center justify-end gap-3 rounded-xl border border-[var(--nq-line)] bg-[var(--nq-bg)] p-4 shadow-lg">
          <Btn variant="ghost" onClick={() => void load()} disabled={saving}>
            Tải lại
          </Btn>
          <Btn variant="ghost" onClick={() => void savePromos()} busy={saving} busyLabel="Đang lưu…">
            Lưu khuyến mãi
          </Btn>
          <Btn variant="primary" onClick={() => void saveProfile()} busy={saving} busyLabel="Đang lưu…">
            Lưu thông tin quán
          </Btn>
        </div>

        <Toasts toasts={toasts} onDismiss={dismiss} />
      </main>
  );
}
