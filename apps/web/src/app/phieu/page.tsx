"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  Empty,
  FixedBottomBar,
  Hint,
  inputClassName,
  OpsCard,
  PageActions,
  PageHeader,
  ProgressBar,
  StepDone,
  Textarea,
} from "../../ui/kit";
import { CopilotPane } from "../../ui/copilot/CopilotPane";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PHIEU_ID_KEY = "nq_phieu_dang_lam";

type MauPhieu = {
  ma: string;
  ten: string;
  so_buoc?: number;
  mo_khi?: string;
  han_hoan_thanh_phut?: number;
  gan_voi?: string;
  bat_buoc?: boolean;
};

type BuocState = {
  ma: string;
  ten: string;
  loai: string;
  hoan_thanh: boolean;
  gia_tri?: string;
};

type PhieuData = {
  id: string;
  mau: string;
  trang_thai: "dang_lam" | "hoan_thanh" | string;
  buoc_hien_tai?: string;
  buocs: BuocState[];
  treo?: { id: string; noi_dung: string }[];
  signals?: {
    timing_ms?: Record<string, number>;
    anti_fake?: string[];
    escalate?: string | null;
  };
};

/** Nén ảnh client-side: canvas ≤1024px, JPEG 0.7 — tránh lỗi anh_qua_lon. */
function nenAnh(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("doc_anh"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("khong_phai_anh"));
      img.onload = () => {
        const max = 1024;
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        const ctx = canvas.getContext("2d");
        if (!ctx) return reject(new Error("canvas"));
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", 0.7));
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  });
}

const MO_KHI_VI: Record<string, string> = {
  nhan_vien_da_diem_danh: "sau khi có mặt",
  ca_ket_thuc: "cuối ca",
};
const GAN_VOI_VI: Record<string, string> = {
  ca_dau_ngay: "đầu ngày",
  ca_cuoi_ngay: "cuối ngày",
  giao_ca: "lúc giao ca",
};

export default function PhieuPage() {
  const [token, setToken] = useState("");
  const [mauList, setMauList] = useState<MauPhieu[]>([]);
  const [phieu, setPhieu] = useState<PhieuData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [treoText, setTreoText] = useState("");
  const [showTreo, setShowTreo] = useState(false);
  const [inputVal, setInputVal] = useState("");
  const [done, setDone] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [daCoMat, setDaCoMat] = useState(false);
  const [anhPreview, setAnhPreview] = useState<string | null>(null);
  const [anhChoGui, setAnhChoGui] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const authHeader = useCallback(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  );

  useEffect(() => {
    const t = sessionStorage.getItem("nq_token");
    if (t) setToken(t);
  }, []);

  // Khôi phục phiếu dở khi reload — hết vòng "tạo phiếu liên tục".
  useEffect(() => {
    if (!token) return;
    const savedId = sessionStorage.getItem(PHIEU_ID_KEY);
    if (!savedId) return;
    fetch(`${API}/api/v1/phieu/${savedId}`, { headers: authHeader() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: PhieuData | null) => {
        if (d && d.trang_thai === "dang_lam") setPhieu(d);
        else sessionStorage.removeItem(PHIEU_ID_KEY);
      })
      .catch(() => sessionStorage.removeItem(PHIEU_ID_KEY));
  }, [token, authHeader]);

  // Load danh sách mẫu — không còn fallback hard-code.
  // Phải chờ có token: effect chạy ở lần render đầu khi `token` còn rỗng sẽ gửi
  // `Authorization: Bearer ` (rỗng) → API trả 401 (QA đợt 6).
  useEffect(() => {
    if (!token) return;
    fetch(`${API}/api/v1/phieu/mau`, { headers: authHeader() })
      .then(async (r) => {
        if (!r.ok) throw new Error("load_mau");
        return r.json() as Promise<MauPhieu[] | { items: MauPhieu[] }>;
      })
      .then((d) => setMauList(Array.isArray(d) ? d : d.items ?? []))
      .catch(() => setMauList([]));
  }, [token, authHeader]);

  async function xacNhanCoMat() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/v1/diem-danh`, {
        method: "POST",
        headers: authHeader(),
      });
      if (!r.ok) throw new Error("diem_danh");
      setDaCoMat(true);
      setOkMsg("Đã ghi có mặt — chọn phiếu để bắt đầu ca.");
    } catch {
      setError("Không ghi được điểm danh. Thử lại giúp quán.");
    } finally {
      setBusy(false);
    }
  }

  async function startPhieu(ma: string) {
    setBusy(true);
    setError(null);
    setOkMsg(null);
    try {
      const r = await fetch(`${API}/api/v1/phieu/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ mau: ma }),
      });
      if (!r.ok) {
        const d = (await r.json().catch(() => null)) as { detail?: string } | null;
        if (d?.detail === "chua_diem_danh") {
          setError("Chưa có mặt hôm nay — bấm «Tôi đã có mặt» trước đã nha.");
          setDaCoMat(false);
          return;
        }
        throw new Error("start_failed");
      }
      const data = (await r.json()) as PhieuData;
      setPhieu(data);
      setDone(false);
      sessionStorage.setItem(PHIEU_ID_KEY, data.id);
    } catch {
      setError("Không mở được phiếu. Thử lại.");
    } finally {
      setBusy(false);
    }
  }

  async function completeBuoc(ma: string, gia_tri?: string) {
    if (!phieu) return;
    setBusy(true);
    setError(null);
    setOkMsg(null);
    try {
      const body: Record<string, unknown> = { ma };
      if (gia_tri !== undefined) body.gia_tri = gia_tri;
      const r = await fetch(`${API}/api/v1/phieu/${phieu.id}/buoc`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error("buoc_failed");
      const updated = (await r.json()) as PhieuData;
      setPhieu(updated);
      setInputVal("");
      setAnhPreview(null);
      setAnhChoGui(null);
      if (updated.trang_thai === "hoan_thanh") {
        setDone(true);
        sessionStorage.removeItem(PHIEU_ID_KEY);
      } else {
        const af = updated.signals?.anti_fake ?? [];
        if (af.length > 0) setOkMsg(null);
      }
    } catch {
      setError("Không lưu được bước. Thử lại.");
    } finally {
      setBusy(false);
    }
  }

  async function guiAnh(buocMa: string, dataUrl: string) {
    if (!phieu) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/v1/phieu/${phieu.id}/minh-chung`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ buoc_ma: buocMa, data_url: dataUrl }),
      });
      if (!r.ok) {
        const d = (await r.json().catch(() => null)) as { detail?: string } | null;
        if (d?.detail === "anh_qua_lon") throw new Error("anh_qua_lon");
        throw new Error("photo_failed");
      }
      const updated = (await r.json()) as PhieuData;
      setPhieu(updated);
      setAnhPreview(null);
      setAnhChoGui(null);
      if (updated.trang_thai === "hoan_thanh") {
        setDone(true);
        sessionStorage.removeItem(PHIEU_ID_KEY);
      }
    } catch (e) {
      setError(e instanceof Error && e.message === "anh_qua_lon"
        ? "Ảnh vẫn quá lớn dù đã nén — thử chụp lại gần hơn."
        : "Không gửi được ảnh. Thử chụp lại.");
    } finally {
      setBusy(false);
    }
  }

  async function handleTreo() {
    if (!phieu || !treoText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/v1/phieu/${phieu.id}/treo`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ noi_dung: treoText }),
      });
      if (!r.ok) throw new Error("treo_failed");
      const updated = (await r.json()) as PhieuData;
      setPhieu(updated);
      setTreoText("");
      setShowTreo(false);
      setOkMsg("Đã ghi việc treo — quản lý sẽ thấy trong mục Việc treo.");
    } catch {
      setError("Không treo được việc. Thử lại.");
    } finally {
      setBusy(false);
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>, buocMa: string) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Cần ảnh thật, không nhận file khác.");
      return;
    }
    try {
      const dataUrl = await nenAnh(file);
      setAnhPreview(dataUrl);
      setAnhChoGui(dataUrl);
    } catch {
      setError("Không đọc được ảnh — thử chụp lại.");
    }
  }

  function boPhieu() {
    sessionStorage.removeItem(PHIEU_ID_KEY);
    setPhieu(null);
    setDone(false);
    setOkMsg(null);
  }

  const currentBuocIndex = phieu
    ? phieu.buocs.findIndex((b) => !b.hoan_thanh)
    : -1;
  const currentBuoc = currentBuocIndex >= 0 ? phieu!.buocs[currentBuocIndex] : null;
  const completed = phieu ? phieu.buocs.filter((b) => b.hoan_thanh).length : 0;
  const total = phieu ? phieu.buocs.length : 0;
  const buocKe = currentBuocIndex >= 0 ? phieu!.buocs.slice(currentBuocIndex + 1, currentBuocIndex + 4) : [];
  const antiFake = phieu?.signals?.anti_fake ?? [];

  if (!token) return <AuthGate />;

  if (done || phieu?.trang_thai === "hoan_thanh") {
    const times = Object.values(phieu?.signals?.timing_ms ?? {});
    const tongGiay = times.length
      ? Math.round(times.reduce((a, b) => a + (b || 0), 0) / 1000)
      : 0;
    return (
      <div className="nq-page nq-page--center">
        <PageHeader
          kicker="Xong phiếu"
          title="Hoàn thành phiếu"
          meta={`Phiếu «${phieu?.mau}» đã xong — ${total} bước trong khoảng ${tongGiay}s.`}
        />
        <div className="flex flex-col gap-3">
          <BtnLink href="/hom-nay" variant="primary">
            Về Hôm nay
          </BtnLink>
          <Btn variant="ghost" onClick={() => { setPhieu(null); setDone(false); }}>
            Làm phiếu khác
          </Btn>
        </div>
        <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
      </div>
    );
  }

  return (
    <div className="nq-page nq-page--run-has-bar">
      <PageHeader
        kicker="Một tay · một bước"
        title={phieu ? `Phiếu «${phieu.mau}»` : "Phiếu ca làm việc"}
        meta={
          phieu
            ? `Bước ${Math.min(completed + 1, total)} / ${total}`
            : "Chọn phiếu cho ca hôm nay rồi đi từng bước."
        }
      />
      <PageActions>
        <Btn variant="ghost" onClick={() => setCopilotOpen(true)}>
          Hỏi trợ lý vận hành
        </Btn>
      </PageActions>

      {error ? <Alert>{error}</Alert> : null}
      {okMsg ? <Alert kind="ok">{okMsg}</Alert> : null}
      {antiFake.length > 0 ? (
        <Alert kind="info">Dấu hiệu cần lưu ý: {antiFake.join(", ")} — quản lý sẽ kiểm lại.</Alert>
      ) : null}

      {!phieu ? (
        <>
          {!daCoMat && mauList.some((m) => m.mo_khi === "nhan_vien_da_diem_danh") ? (
            <OpsCard eyebrow="Tùy theo phiếu" title="Xác nhận có mặt">
              <p className="mb-3 text-sm text-[var(--nq-dim)]">
                Chỉ các phiếu cần có mặt mới yêu cầu bước này. Bàn giao ca vẫn có thể mở khi cần.
              </p>
              <Btn variant="ghost" busy={busy} onClick={xacNhanCoMat}>
                Tôi đã có mặt
              </Btn>
            </OpsCard>
          ) : null}
          <OpsCard eyebrow="Theo cấu hình quán" title="Chọn phiếu cho ca" count={mauList.length} countLabel="mẫu">
              {mauList.length === 0 ? (
                <Empty title="Chưa tải được danh sách phiếu">
                  Kiểm tra kết nối rồi bấm thử lại.
                  <Btn className="mt-3" variant="ghost" onClick={() => location.reload()}>
                    Thử lại
                  </Btn>
                </Empty>
              ) : (
                <div className="flex flex-col gap-3">
                  {mauList.map((m) => (
                    <button
                      key={m.ma}
                      type="button"
                      disabled={busy}
                      onClick={() => startPhieu(m.ma)}
                      className="nq-surface-row p-4 text-left transition-colors hover:border-[var(--nq-accent)] disabled:opacity-50"
                    >
                      <span className="block text-base font-semibold text-[var(--nq-fg)]">{m.ten || m.ma}</span>
                      <span className="mt-1 block text-xs text-[var(--nq-dim)]">
                        {m.so_buoc ? `${m.so_buoc} bước · ` : ""}
                        {m.mo_khi ? `mở ${MO_KHI_VI[m.mo_khi] ?? m.mo_khi} · ` : ""}
                        {m.bat_buoc ? "bắt buộc · " : "tùy chọn · "}
                        {m.han_hoan_thanh_phut ? `nên xong trong ${m.han_hoan_thanh_phut} phút` : ""}
                      </span>
                    </button>
                  ))}
                </div>
              )}
          </OpsCard>
        </>
      ) : null}

      {phieu && !done ? (
        <>
          <OpsCard
            eyebrow="Tiến độ"
            title="Các bước đã qua"
            count={total - completed}
            countLabel="bước còn lại"
          >
            <ProgressBar value={completed} max={total} className="mb-4" />
            {phieu.buocs.filter((b) => b.hoan_thanh).map((b) => (
              <StepDone key={b.ma} label={b.ten} timingMs={phieu.signals?.timing_ms?.[b.ma]} />
            ))}
            {buocKe.length > 0 ? (
              <div className="mt-4 border-t border-[var(--nq-dim)] pt-3">
                <p className="mb-2 font-mono text-2xs uppercase tracking-widest text-[var(--nq-dim)]">
                  Tiếp theo
                </p>
                {buocKe.map((b) => (
                  <p key={b.ma} className="py-0.5 text-sm text-[var(--nq-dim)] opacity-60">
                    · {b.ten}
                  </p>
                ))}
              </div>
            ) : null}
          </OpsCard>

          {currentBuoc ? (
            <OpsCard
              eyebrow={`Bước ${completed + 1}`}
              title={currentBuoc.ten}
            >
              <p className="mb-3 text-sm text-[var(--nq-dim)]">
                {currentBuoc.loai === "photo"
                  ? "Chụp ảnh minh chứng — xem trước rồi gửi."
                  : currentBuoc.loai === "text"
                    ? "Nhập số đọc được rồi bấm xong."
                    : "Bấm xong khi đã làm."}
              </p>
              {(currentBuoc.loai === "text" || currentBuoc.loai === "nhap") && (
                <>
                  <input
                    type="text"
                    className={inputClassName}
                    value={inputVal}
                    onChange={(e) => setInputVal(e.target.value)}
                    placeholder={
                      currentBuoc.ten.toLowerCase().includes("nhiệt độ")
                        ? "Ví dụ: 4.5 (ngưỡng hợp lệ 2–8°C)"
                        : "Nhập giá trị…"
                    }
                  />
                  {currentBuoc.ten.toLowerCase().includes("nhiệt độ") ? (
                    <Hint>Ngưỡng tủ lạnh 2–8°C — số ngoài ngưỡng sẽ được đánh dấu kiểm tra.</Hint>
                  ) : null}
                </>
              )}
              {currentBuoc.loai === "photo" && (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="hidden"
                    onChange={(e) => handleFileChange(e, currentBuoc.ma)}
                  />
                  {anhPreview ? (
                    <div className="space-y-3">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={anhPreview}
                        alt="Xem trước ảnh minh chứng"
                        className="max-h-64 w-full border border-[var(--nq-line)] rounded-lg object-contain"
                      />
                      <div className="flex flex-wrap gap-2">
                        <Btn
                          variant="primary"
                          busy={busy}
                          disabled={!anhChoGui}
                          onClick={() => anhChoGui && guiAnh(currentBuoc.ma, anhChoGui)}
                        >
                          Gửi ảnh này
                        </Btn>
                        <Btn variant="ghost" onClick={() => { setAnhPreview(null); setAnhChoGui(null); }}>
                          Chụp lại
                        </Btn>
                      </div>
                    </div>
                  ) : (
                    <Btn variant="ghost" disabled={busy} onClick={() => fileInputRef.current?.click()}>
                      Chụp ảnh minh chứng
                    </Btn>
                  )}
                </>
              )}
            </OpsCard>
          ) : null}

          {phieu.treo && phieu.treo.length > 0 ? (
            <OpsCard eyebrow="Đã để lại" title="Việc treo lần phiếu này" count={phieu.treo.length} countLabel="việc">
              {phieu.treo.map((t) => (
                <p key={t.id} className="border-l-2 border-[var(--nq-accent)] pl-3 py-1 text-sm">
                  {t.noi_dung}
                </p>
              ))}
              <Hint>
                Quản lý xem và xử lý những việc này trong mục Việc treo.{" "}
                <a href="/treo" className="underline text-[var(--nq-accent)]">Mở Việc treo →</a>
              </Hint>
            </OpsCard>
          ) : null}

          {showTreo ? (
            <OpsCard eyebrow="Cần người khác lo" title="Để lại việc khó">
              <p className="mb-3 text-sm text-[var(--nq-dim)]">
                Ghi việc mình không làm xong — quản lý sẽ nhận và xử lý, không mất đi.
              </p>
              <Textarea
                className="min-h-[6rem]"
                value={treoText}
                onChange={(e) => setTreoText(e.target.value)}
                placeholder="Ví dụ: Hết ống hút cỡ lớn, cần mua trước ca tối…"
                rows={4}
              />
              <div className="flex flex-wrap gap-2 mt-4">
                <Btn variant="danger" disabled={busy || !treoText.trim()} onClick={handleTreo}>
                  Ghi việc treo
                </Btn>
                <Btn variant="ghost" onClick={() => setShowTreo(false)}>
                  Hủy
                </Btn>
              </div>
            </OpsCard>
          ) : null}
        </>
      ) : null}

      {phieu && !done && currentBuoc ? (
        <FixedBottomBar>
          {currentBuoc.loai !== "photo" ? (
            <Btn
              variant="primary"
              block
              busy={busy}
              busyLabel="Đang lưu…"
              disabled={
                (currentBuoc.loai === "text" || currentBuoc.loai === "nhap") &&
                inputVal.trim().length === 0
              }
              onClick={() =>
                completeBuoc(
                  currentBuoc.ma,
                  currentBuoc.loai === "text" || currentBuoc.loai === "nhap" ? inputVal : undefined,
                )
              }
            >
              Xong bước này
            </Btn>
          ) : null}
          <Btn variant="ghost" onClick={() => setShowTreo((s) => !s)} title="Để lại việc khó cho quản lý">
            Để lại việc khó
          </Btn>
          <Btn variant="ghost" onClick={boPhieu} title="Bỏ phiếu này, về chọn mẫu">
            Bỏ phiếu
          </Btn>
        </FixedBottomBar>
      ) : null}
      <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}
