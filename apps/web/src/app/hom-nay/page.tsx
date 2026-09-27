"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet } from "../../lib/api";
import { computeOpsPulse } from "../../lib/ops-pulse";
import {
  formatLuc,
  ghiNhanLabel,
  matHangLabel,
  safeText,
  treoLabel,
  treoTone,
  viError,
} from "../../lib/present";
import { getRole, getToken, isChuQuan, isManager } from "../../lib/session";
import { todayHeroLine, todayMetaLine, todayTechnicalDetail } from "../../lib/status";
import { SuaTimeline, TonBarChart, TreoDonutChart } from "../../ui/hom-nay/dashboard-charts";
import { useActorName } from "../../ui/ops-pickers";
import { HeroMotif, KpiCard, StatusStrip } from "../../ui/hom-nay/kpi-card";
import { OpsPulseLite } from "../../ui/hom-nay/ops-pulse-lite";
import { TreoTrendBlock, buildTreoSeries, dayKeyICT, type TreoTimeItem } from "../../ui/hom-nay/treo-trend";
import { Alert, AuthGate, Btn, BtnLink, FixtureChip, Loading, PageActions, StatusChip, TechnicalDrawer } from "../../ui/kit";

const OpsPulse3d = dynamic(() => import("../../ui/hom-nay/ops-pulse").then((m) => m.OpsPulse), {
  ssr: false,
  loading: () => <div className="nq-ops-pulse nq-ops-pulse--loading" aria-busy="true" />,
});

type TreoPreview = {
  id: string;
  noi_dung?: string;
  /** Hai khoá cùng nghĩa "nội dung" mà các nguồn ghi khác dùng — xem `tieuDeTreo`. */
  mo_ta?: string;
  tieu_de?: string;
  trang_thai?: string;
  nhan_vien?: string;
};
type SuaPreview = { loai?: string; luc?: string; ai?: string };
type TonRow = { hang?: string; so_luong?: number; don_vi?: string; duoi_nguong?: boolean };
type TreoBreakdown = { trang_thai: string; so_luong: number };

/** Rút gọn hao hụt hôm nay — máy chủ dùng CÙNG hàm với /hao-phi và agent mẹ. */
type HaoHut = {
  co_du_lieu?: boolean;
  tong_dong?: number;
  so_nghiem_trong?: number;
  so_canh_bao?: number;
  so_thieu_du_lieu?: number;
  ty_le_trung_binh?: number | null;
  mat_hang_vuot?: { ten: string; ty_le: number | null; muc_do: string }[];
  nguyen_nhan_hang_dau?: { ten: string; so_lan: number }[];
  ly_do?: string;
};

type Today = {
  ngay: string;
  lich: { trang_thai?: string; nguon?: string; solver?: { status?: string } };
  so_treo?: number;
  so_inbox_cho?: number;
  so_luat?: number;
  canh_bao_ton?: string[];
  so_nhan_vien?: number;
  treo_preview?: TreoPreview[];
  treo_theo_trang_thai?: TreoBreakdown[];
  sua_gan_day?: SuaPreview[];
  ton_tom_tat?: TonRow[];
  hao_hut?: HaoHut;
  co_du_lieu_mau?: boolean;
  viec_cho_toi?: { id: string; tieu_de: string; chi_tiet: string; link: string; muc?: number }[];
  brief_hom_nay?: { ngay: string; so_ca: number; so_treo_mo: number; ton_canh_bao?: string[]; treo_dau?: string[] } | null;
};

function soAnToan(v: unknown): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

/**
 * Tiêu đề của một việc treo, chấp nhận CẢ BA tên khoá đang tồn tại trong store.
 *
 * Vì sao phải chấp nhận ba: có 9 chỗ ghi vào cùng danh sách `treo` và chúng không
 * thống nhất tên khoá cho cùng một khái niệm —
 *   `noi_dung`  sprint3 · chat · copilot · meeting · shift_rescue · war_room · fixture `treo_fx*`
 *   `mo_ta`     channels.py, và `seed_19_staff.py` (4 việc treo demo)
 *   `tieu_de`   `seed_19_staff.py` (phiếu)
 * `apps/api` đọc **chỉ** `noi_dung` (`sprint45.py:1353`), nên với `make seed-demo`
 * bốn việc treo của `seed_19_staff` hiện ra **tiêu đề TRỐNG** — một ô rỗng bấm
 * được, trông như lỗi giao diện.
 *
 * Vá ở đây chứ không sửa `apps/api`: đọc thêm khoá là thay đổi thuần hiển thị,
 * không đổi dữ liệu và không đổi contract. Việc chuẩn hoá 5 tên khoá (kèm
 * `nhan_vien`/`nguoi_nhan`, `tao_luc`/`created_at`) là thay đổi ở tầng ghi — đã
 * ghi thành đề xuất backend riêng trong `plans/260927-*` mục 6, chờ duyệt.
 */
function tieuDeTreo(v: TreoPreview): string {
  return safeText(v.noi_dung || v.mo_ta || v.tieu_de, "(không có nội dung)");
}

function usePulse3d() {
  const [use3d, setUse3d] = useState(false);
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const wide = window.matchMedia("(min-width: 1024px)").matches;
    setUse3d(wide && !reduced);
  }, []);
  return use3d;
}

export default function HomNayPage() {
  const [token, setToken] = useState("");
  const [data, setData] = useState<Today | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manager, setManager] = useState(false);
  const [chuQuan, setChuQuan] = useState(false);
  const [treoHistory, setTreoHistory] = useState<TreoTimeItem[] | null>(null);
  const use3d = usePulse3d();
  const actorName = useActorName();

  useEffect(() => {
    setToken(getToken());
    setManager(isManager());
    setChuQuan(isChuQuan(getRole()));
  }, []);

  const load = useCallback(() => {
    if (!getToken()) return;
    setError(null);
    apiGet<Today>("/api/v1/hom-nay")
      .then(setData)
      .catch((e) => setError(viError(e, { doing: "đọc được bảng hôm nay" })));
  }, []);

  // Lịch sử việc treo cho sparkline — GỌI RIÊNG, và hỏng thì im lặng.
  //
  // Vì sao không gộp vào `/api/v1/hom-nay`: endpoint đó chỉ trả 5 việc mới nhất
  // (`treo_preview`) nên không đủ mốc để dựng chuỗi 7 ngày. `/api/v1/viec-treo` trả
  // đủ danh sách, và mọi vai đều gọi được (`_require_role`), khác `/api/v1/audit`
  // là endpoint chỉ `quan_ly`/`chu_quan` — dùng nhầm thì nhân viên thấy lỗi.
  //
  // Vì sao hỏng thì im lặng: đây là phần PHỤ của bảng Hôm nay, mà bảng Hôm nay là
  // trang mở đầu sau đăng nhập — hỏng nó là hỏng cả ca làm việc. Cùng nguyên tắc
  // `try/except` mà `sprint45.py` áp cho phần hao hụt. Khối sẽ tự hiện "chưa đủ
  // dữ liệu" thay vì một thông báo lỗi đỏ.
  const loadTreoHistory = useCallback(() => {
    if (!getToken()) return;
    apiGet<{ items: TreoTimeItem[] }>("/api/v1/viec-treo")
      .then((r) => setTreoHistory(Array.isArray(r?.items) ? r.items : []))
      .catch(() => setTreoHistory([]));
  }, []);

  useEffect(() => {
    if (token) {
      load();
      loadTreoHistory();
    }
  }, [token, load, loadTreoHistory]);

  const treo = soAnToan(data?.so_treo);
  const tonThapEarly = (data?.ton_tom_tat ?? []).filter((t) => t.duoi_nguong);
  const canhBaoCount = (data?.canh_bao_ton ?? []).length;
  const tonWarnEarly = canhBaoCount || tonThapEarly.length;

  const pulseModel = useMemo(() => {
    if (!data) return null;
    return computeOpsPulse({
      treo: soAnToan(data.so_treo),
      tonWarn: tonWarnEarly,
      inboxCho: chuQuan ? soAnToan(data.so_nhan_vien) : manager ? soAnToan(data.so_inbox_cho) : 0,
      lichState: data.lich?.trang_thai,
      solverStatus: data.lich?.solver?.status,
      role: chuQuan ? "chu_quan" : manager ? "quan_ly" : "nhan_vien",
    });
  }, [data, tonWarnEarly, manager, chuQuan]);

  if (!token) return <AuthGate />;

  const ngay = safeText(data?.ngay, "");
  const hero = data ? todayHeroLine(treo, data.lich?.trang_thai) : "Đang đọc nhịp quán…";
  const canhBao = (data?.canh_bao_ton ?? []).map((x) => matHangLabel(x)).filter(Boolean);
  const preview = data?.treo_preview ?? [];
  const treoBreakdown = data?.treo_theo_trang_thai ?? [];
  const sua = data?.sua_gan_day ?? [];
  const ton = data?.ton_tom_tat ?? [];
  const tonThap = ton.filter((t) => t.duoi_nguong);
  const tonWarn = canhBao.length || tonThap.length;
  const kpi2 = chuQuan ? soAnToan(data?.so_nhan_vien) : manager ? soAnToan(data?.so_inbox_cho) : soAnToan(data?.so_luat);
  const kpi2Label = chuQuan ? "Nhân viên chờ xem xét" : manager ? "Mục chờ duyệt" : "Luật cẩm nang";
  const kpi2Href = chuQuan ? "/nguoi" : manager ? "/inbox" : "/cam-nang";
  const highlight = pulseModel?.highlightKpi;
  const haoHut = data?.hao_hut;

  // Dòng phụ của dải trạng thái — CHỈ số không trùng thẻ KPI. Xem `todayMetaLine`.
  const stripMeta = todayMetaLine(ngay, data?.brief_hom_nay?.so_ca ?? null);

  // Chuỗi xu hướng việc treo. `null` = chưa đủ mốc để vẽ (không vẽ đường 0 giả).
  const treoSeries = treoHistory ? buildTreoSeries(treoHistory) : null;
  // Độ lệch giữa mốc mới nhất và hôm nay — để nhãn nói thật về phạm vi dữ liệu.
  // So theo ICT cho khớp `dayKeyICT`; lệch 0/1 ngày là bình thường.
  const homNayICT = dayKeyICT(new Date().toISOString());
  const soNgayLech =
    treoSeries && homNayICT
      ? Math.max(
          0,
          Math.round(
            (Date.parse(`${homNayICT}T00:00:00Z`) - Date.parse(`${treoSeries.mocCuoi}T00:00:00Z`)) /
              86_400_000,
          ),
        )
      : 0;

  // Trạng thái của khối "Cảnh báo cần xử lý" — gom cả hai nguồn (tồn + hao hụt)
  // vào MỘT khối vì chúng cùng trả lời một câu: "có gì cần tôi xử lý không".
  const coCanhBaoTon = canhBao.length > 0 || tonThap.length > 0;
  const haoHutCanXem = Boolean(haoHut?.co_du_lieu && ((haoHut.so_nghiem_trong ?? 0) || (haoHut.so_canh_bao ?? 0)));

  return (
    <div className="nq-page nq-page--dashboard">
      <div className="nq-dash-hero">
        <HeroMotif />
        <StatusStrip status={hero} meta={stripMeta} />
        {pulseModel ? use3d ? <OpsPulse3d model={pulseModel} /> : <OpsPulseLite model={pulseModel} /> : null}
      </div>

      {error ? (
        <>
          <Alert>{error}</Alert>
          <PageActions>
            <Btn variant="ghost" onClick={load}>
              Tải lại bảng
            </Btn>
          </PageActions>
        </>
      ) : null}

      {!data && !error ? <Loading skeleton="bento">Đang tải bảng hôm nay…</Loading> : null}

      {data ? (
        <>
          {data.co_du_lieu_mau ? (
            <p className="mb-4">
              <FixtureChip />
            </p>
          ) : null}
          {data.viec_cho_toi && data.viec_cho_toi.length > 0 ? (
            /* Khối "việc của bạn" được NHẤN bằng viền accent: đây là việc người
               dùng phải làm, khác hẳn các khối chỉ để đọc. Không tô nền accent —
               nền màu sau chữ là cách chắc chắn nhất để hạ tương phản. */
            <section className="mb-6 nq-surface-block nq-block--accent p-4 md:p-5">
              <p className="nq-eyebrow">Hàng đợi hôm nay</p>
              <h2 className="nq-block-title">Việc của bạn</h2>
              <ul className="mt-3 flex flex-col gap-2">
                {data.viec_cho_toi.map((v) => (
                  <li key={v.id}>
                    <a href={v.link} className="nq-action-row">
                      <span className="min-w-0">
                        <span className="nq-action-row__title">{v.tieu_de}</span>
                        <span className="nq-action-row__sub">{v.chi_tiet}</span>
                      </span>
                      <span className="nq-action-row__go" aria-hidden="true">→</span>
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {/* Dòng "Brief sáng … : N ca · N việc treo đang mở · tồn cảnh báo: …" đã
              BỎ khỏi đây. Hai trong bốn số của nó là số của thẻ KPI ngay bên dưới
              (`so_treo_mo` = "Việc treo", `ton_canh_bao` = "Cảnh báo tồn") và
              `treo_dau` trùng khối "Việc treo gần nhất" — màn hình nói cùng một
              chuyện hai lần. Số còn lại (`so_ca`) nay nằm trong dòng phụ của dải
              trạng thái, cạnh những gì nó thuộc về. */}
          <div className="nq-dash-kpis nq-bento">
            <KpiCard
              value={treo}
              label="Việc treo"
              accent={treo > 0 ? "warn" : "default"}
              href="/treo"
              delay={0}
              data-highlight={highlight === "treo" ? "on" : undefined}
            />
            <KpiCard
              value={kpi2}
              label={kpi2Label}
              href={kpi2Href}
              delay={0.05}
              data-highlight={highlight === "inbox" ? "on" : undefined}
            />
            <KpiCard
              value={tonWarn}
              label="Cảnh báo tồn"
              accent={canhBao.length > 0 ? "warn" : "default"}
              href="/tieu-thu"
              delay={0.1}
              data-highlight={highlight === "ton" ? "on" : undefined}
            />
            <KpiCard value={ngay ? ngay.slice(8, 10) : "—"} label={ngay ? `Tháng ${ngay.slice(5, 7)}` : "Ngày"} delay={0.15} />
          </div>

          <div className="nq-dash-body">
            <div className="nq-dash-main">
              {/* Xu hướng theo ngày đứng TRƯỚC hai biểu đồ ảnh-chụp-một-thời-điểm:
                  câu hỏi "đang đi lên hay xuống" quan trọng hơn "đang là bao nhiêu",
                  nên nó là thứ đầu tiên mắt gặp trong vùng nội dung. */}
              <TreoTrendBlock series={treoSeries} loading={treoHistory === null} soNgayLech={soNgayLech} />

              <div className="nq-dash-charts">
                <TonBarChart rows={ton} />
                <TreoDonutChart breakdown={treoBreakdown} total={treo} />
              </div>

              {preview.length > 0 ? (
                <section className="nq-ops-card nq-dash-treo-list">
                  <div className="nq-dash-section-head">
                    <h2>Việc treo gần nhất</h2>
                    <Link href="/treo">Xem tất cả ({treo})</Link>
                  </div>
                  <div className="nq-list nq-dash-compact-list">
                    {preview.map((v) => (
                      <Link key={v.id} href="/treo" className="nq-item block hover:opacity-90">
                        {/* Cắt 2 DÒNG bằng CSS (xem `.nq-item-title.nq-clamp-2`), và
                            `title` giữ nguyên văn để rê chuột xem hết. Không cắt
                            bằng `substring` ở JS: cắt theo ký tự đứt giữa từ và
                            thông tin mất hẳn khỏi DOM. */}
                        <p className="nq-item-title nq-clamp-2" title={tieuDeTreo(v)}>
                          {tieuDeTreo(v)}
                        </p>
                        <p className="nq-item-sub">
                          <StatusChip tone={treoTone(v.trang_thai)}>{treoLabel(v.trang_thai)}</StatusChip>
                        </p>
                      </Link>
                    ))}
                  </div>
                </section>
              ) : null}
            </div>

            {/* Cột phụ tách thành HAI khối có tiêu đề riêng.
                Bản trước là một `<aside>` chứa ba thứ khác chủ đề mà không có
                tiêu đề tổng nào — cảnh báo tồn, hao hụt, nhật ký sửa lịch. Đọc ra
                ba mẩu rời rạc và mắt không có chỗ bám.
                Cách chia: theo CÂU HỎI người dùng đang hỏi, không theo nguồn dữ
                liệu. "Có gì cần tôi xử lý?" (tồn + hao hụt gộp lại — cùng một câu
                hỏi, nên cùng một khối) và "Ai vừa đổi gì?" (nhật ký). */}
            <aside className="nq-dash-aside">
              <section className="nq-dash-aside-block">
                <h2 className="nq-block-title">Cảnh báo cần xử lý</h2>
                <div className="nq-dash-aside-block__body">
                  {coCanhBaoTon ? (
                    <Alert kind="info">
                      Tồn dưới ngưỡng: {(canhBao.length ? canhBao : tonThap.map((t) => matHangLabel(t.hang))).join(", ")}.
                      <BtnLink href="/tieu-thu" variant="ghost">
                        Mở sổ tiêu thụ
                      </BtnLink>
                    </Alert>
                  ) : null}

                  {/* Hao hụt: chỉ báo khi có chuyện. Dòng "chưa đủ dữ liệu" nói thẳng
                      là chưa kết luận được, không im lặng coi như đạt. */}
                  {haoHut && haoHut.co_du_lieu ? (
                    haoHutCanXem ? (
                      <Alert kind="info">
                        Hao hụt cần xem:{" "}
                        {(haoHut.mat_hang_vuot ?? [])
                          .map((x) => (x.ty_le === null ? x.ten : `${x.ten} ${x.ty_le}%`))
                          .join(", ") || `${(haoHut.so_nghiem_trong ?? 0) + (haoHut.so_canh_bao ?? 0)} nguyên liệu`}
                        .
                        {haoHut.so_thieu_du_lieu ? (
                          <span className="block mt-2">
                            {haoHut.so_thieu_du_lieu} nguyên liệu chưa kết luận được vì thiếu một vế.
                          </span>
                        ) : null}
                        <BtnLink href="/hao-phi" variant="ghost">
                          Mở bảng hao hụt
                        </BtnLink>
                      </Alert>
                    ) : null
                  ) : (
                    <p className="nq-dash-aside-clear">
                      Hao hụt chưa đủ dữ liệu để đối chiếu —{" "}
                      <Link href="/hao-phi">gõ phiếu kiểm kê →</Link>
                    </p>
                  )}

                  {/* "Không có gì" cũng là một câu trả lời, nhưng chỉ nói khi thật
                      sự không có gì. Trước đây trạng thái này bị bỏ trống nên khối
                      trông như đang tải lỗi. */}
                  {!coCanhBaoTon && haoHut && haoHut.co_du_lieu && !haoHutCanXem ? (
                    <p className="nq-dash-aside-clear">
                      Không có cảnh báo nào — tồn và hao hụt đang trong ngưỡng.
                    </p>
                  ) : null}
                </div>
              </section>

              {/* Khối nhật ký LUÔN có mặt, kể cả khi chưa có bản ghi.
                  Vì sao không ẩn khi rỗng: cột phụ được chia thành hai khối cố
                  định ("có gì cần xử lý?" và "ai vừa đổi gì?"). Ẩn khối thứ hai
                  khi rỗng thì lần đầu vào — hoặc trên store mới — cột phụ chỉ còn
                  một khối, và người dùng không biết chỗ đó LẼ RA có gì. Trạng thái
                  rỗng nói thẳng là rỗng (nhưng KHÔNG dùng dáng `.nq-alert`: đây
                  không phải chuyện cần chú ý). */}
              <section className="nq-dash-aside-block">
                <h2 className="nq-block-title">Nhật ký thay đổi</h2>
                <div className="nq-dash-aside-block__body">
                  {sua.length > 0 ? (
                    <SuaTimeline items={sua} formatLuc={formatLuc} ghiNhanLabel={ghiNhanLabel} actorLabel={actorName} />
                  ) : (
                    <p className="nq-dash-aside-clear">
                      Chưa có ghi nhận sửa lịch nào —{" "}
                      <Link href="/treo">xem tab ghi nhận sửa →</Link>
                    </p>
                  )}
                </div>
              </section>
            </aside>
          </div>

          <TechnicalDrawer lines={todayTechnicalDetail(data.lich ?? {})} />

          <div className="nq-dash-actions">
            <PageActions>
              {chuQuan ? (
                <>
                  <BtnLink href="/nguoi">Quản lý người dùng</BtnLink>
                  <BtnLink href="/cam-nang">Cẩm nang quán</BtnLink>
                  <BtnLink href="/menu" variant="ghost">
                    Menu & giá
                  </BtnLink>
                  <BtnLink href="/vet" variant="ghost">
                    Xem vết hệ thống
                  </BtnLink>
                </>
              ) : manager ? (
                <>
                  <BtnLink href="/lich-tuan">Xếp lịch tuần</BtnLink>
                  <BtnLink href="/inbox">Duyệt hộp thư</BtnLink>
                  <BtnLink href="/cam-nang" variant="ghost">
                    Chạy cẩm nang
                  </BtnLink>
                  <BtnLink href="/treo" variant="ghost">
                    Xem việc treo
                  </BtnLink>
                </>
              ) : (
                <>
                  <BtnLink href="/phieu">Mở phiếu ca</BtnLink>
                  <BtnLink href="/quay" variant="ghost">
                    Ghi đơn tại quầy
                  </BtnLink>
                  <BtnLink href="/toi" variant="ghost">
                    Ca của tôi
                  </BtnLink>
                  <BtnLink href="/sop" variant="ghost">
                    Hỏi cẩm nang
                  </BtnLink>
                </>
              )}
            </PageActions>
          </div>
        </>
      ) : null}
    </div>
  );
}
