"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { beat } from "../../lib/motion";

/**
 * Xu hướng việc treo theo ngày — góc nhìn THỜI GIAN cho bảng Hôm nay.
 *
 * ── Vì sao cần ──
 * Hai biểu đồ của trang (`TonBarChart`, `TreoDonutChart`) đều là **ảnh chụp một
 * thời điểm**: chúng trả lời "đang có bao nhiêu", không trả lời "đang đi lên hay
 * đi xuống". Không có chiều thời gian thì người quản lý không phân biệt được
 * "4 việc treo vì hôm nay mới phát sinh" với "4 việc treo vì tồn lại ba tuần".
 *
 * ── Vì sao dựng ở CLIENT, không xin backend ──
 * `/api/v1/hom-nay` và `/api/v1/hao-hut?ky=tuan` **không** có trường chuỗi theo
 * thời gian nào (đã kiểm: `LossSummary` chỉ có tổng hợp, `ky` là từ vựng đóng
 * `hom_nay|tuan|thang|all`). Nhưng mỗi item của `/api/v1/viec-treo` **có** mốc
 * thời gian (`created_at`, `xong_luc`) nên gộp theo ngày được ngay tại đây, không
 * phải chạm `apps/api` và không phải đổi contract. Đề xuất bổ sung
 * `treo_theo_ngay` cho backend đã ghi trong `plans/260927-*` mục 6 để làm sau.
 *
 * ── Ba quyết định về tính trung thực của số liệu ──
 * 1. **Neo cửa sổ vào mốc MỚI NHẤT có dữ liệu, không phải "hôm nay".** Dữ liệu
 *    seed của repo có mốc cũ (việc treo fixture ở `2026-01`, việc của
 *    `seed_19_staff` ở `2026-09-11`) trong khi "hôm nay" là `2026-09-27`. Cửa sổ
 *    "7 ngày gần nhất tính đến hôm nay" sẽ ra **toàn số 0** — một đường phẳng.
 *    Đường phẳng đó NÓI DỐI: "không có việc nào phát sinh" khác hẳn "không có
 *    dữ liệu để biết". Nên cửa sổ neo vào mốc thật, và nhãn bên dưới ghi rõ
 *    khoảng ngày thật.
 * 2. **Không đủ 2 ngày khác nhau thì không vẽ.** Không vẽ trục, không vẽ cột 0 —
 *    chỉ một câu nói thẳng là chưa kết luận được. Cùng nguyên tắc `None ≠ 0.0` mà
 *    `packages/contracts/src/ca_contracts/loss.py` đặt ra cho hao hụt.
 * 3. **Mọi mốc quy về giờ ICT.** `created_at` là UTC; cắt chuỗi `[:10]` là cắt
 *    theo UTC, và 7 giờ cuối mỗi ngày Việt Nam sẽ rơi sang cột hôm sau — sai âm
 *    thầm, không ai thấy. Xem `dayKeyICT`.
 *
 * ── Vì sao KHÔNG phải "số việc treo đang mở luỹ kế" ──
 * Đường luỹ kế cần biết thời điểm ĐÓNG của mọi việc đã đóng. Dữ liệu cũ thiếu
 * `xong_luc` (nhiều bản ghi `null`, và 4 việc của `seed_19_staff` dùng khoá khác
 * hẳn), nên luỹ kế sẽ ra một đường vẽ từ dữ liệu khuyết mà trông vẫn "có vẻ
 * đúng" — kiểu sai nguy hiểm nhất. Hai chuỗi **phát sinh** và **đã xong** thì mỗi
 * cột chỉ phụ thuộc một bản ghi có thật.
 */

/** Một item thô từ `/api/v1/viec-treo` — chỉ các mốc thời gian là cần. */
export type TreoTimeItem = {
  created_at?: string | null;
  xong_luc?: string | null;
  /** Khoá cũ của `seed_19_staff.py` (4 việc treo demo) — không phải `created_at`. */
  tao_luc?: string | null;
};

const ICT = "Asia/Ho_Chi_Minh";
const WINDOW_DAYS = 7;

/**
 * ISO (UTC) → khoá ngày theo GIỜ VIỆT NAM, dạng `YYYY-MM-DD`.
 *
 * `en-CA` vì locale đó cho đúng thứ tự `YYYY-MM-DD`; `vi-VN` sẽ ra `DD/MM/YYYY`
 * và phải đảo lại. `timeZone` là tham số quyết định — bỏ nó là lấy múi của máy
 * chạy (máy dev ở múi khác sẽ ra cột lệch, và CI ở UTC sẽ lệch khỏi production).
 */
export function dayKeyICT(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: ICT,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

/** `YYYY-MM-DD` → `DD/MM` cho nhãn trục, không qua `Date` nên không lệch múi. */
function nhan(ngay: string): string {
  const m = ngay.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}` : ngay;
}

/** Cộng/trừ ngày trên khoá `YYYY-MM-DD` bằng UTC — khoá đã là ngày rồi, không đổi múi nữa. */
function shiftDay(ngay: string, delta: number): string {
  const t = Date.parse(`${ngay}T00:00:00Z`);
  if (Number.isNaN(t)) return ngay;
  return new Date(t + delta * 86_400_000).toISOString().slice(0, 10);
}

export type TreoSeries = {
  /** Các mốc ngày tăng dần, phần tử cuối là ngày có dữ liệu mới nhất. */
  ngay: string[];
  /** Số việc phát sinh mỗi ngày (theo `created_at` / `tao_luc`). */
  moi: number[];
  /** Số việc đóng mỗi ngày (theo `xong_luc`). */
  xong: number[];
  /** Ngày mới nhất có dữ liệu — nhãn phải ghi khoảng thật theo mốc này. */
  mocCuoi: string;
  /** Tổng số mốc có thật (dùng để quyết định "chưa đủ dữ liệu"). */
  soMoc: number;
};

/**
 * Gộp danh sách việc treo thành chuỗi theo ngày, cửa sổ 7 ngày neo mốc mới nhất.
 *
 * Trả `null` khi **không dựng được chuỗi có nghĩa**: ít hơn 2 ngày khác nhau, hoặc
 * không mốc nào hợp lệ. Bên gọi hiển thị câu "chưa đủ dữ liệu" thay vì vẽ trục.
 */
export function buildTreoSeries(items: TreoTimeItem[]): TreoSeries | null {
  const moiTheoNgay = new Map<string, number>();
  const xongTheoNgay = new Map<string, number>();

  for (const it of items) {
    const tao = dayKeyICT(it.created_at ?? it.tao_luc);
    if (tao) moiTheoNgay.set(tao, (moiTheoNgay.get(tao) ?? 0) + 1);
    const xong = dayKeyICT(it.xong_luc);
    if (xong) xongTheoNgay.set(xong, (xongTheoNgay.get(xong) ?? 0) + 1);
  }

  const all = [...new Set([...moiTheoNgay.keys(), ...xongTheoNgay.keys()])].sort();
  if (all.length < 2) return null;

  const mocCuoi = all[all.length - 1];
  const ngay: string[] = [];
  for (let i = WINDOW_DAYS - 1; i >= 0; i -= 1) ngay.push(shiftDay(mocCuoi, -i));

  return {
    ngay,
    moi: ngay.map((d) => moiTheoNgay.get(d) ?? 0),
    xong: ngay.map((d) => xongTheoNgay.get(d) ?? 0),
    mocCuoi,
    soMoc: all.length,
  };
}

const MAU_MOI = "var(--nq-warn)";
const MAU_XONG = "var(--nq-ok)";

/**
 * Cột đôi theo ngày: mỗi ngày hai cột mảnh (phát sinh / đã xong).
 *
 * Chọn cột thay vì đường vì số ngày chỉ 7 và giá trị là số nguyên nhỏ — đường nối
 * 7 điểm số nguyên gợi ý một độ liên tục và một độ chính xác không có thật.
 */
export function TreoTrendSpark({ series }: { series: TreoSeries }) {
  const reduced = useReducedMotion() ?? false;
  const max = Math.max(1, ...series.moi, ...series.xong);
  const W = 100;
  const H = 34;
  const pad = 1.5;
  const slot = (W - pad * 2) / series.ngay.length;
  const barW = Math.max(1.6, slot * 0.30);
  const gap = Math.max(0.7, slot * 0.10);
  const h = (n: number) => (n / max) * (H - pad * 2);

  return (
    <svg
      className="nq-spark"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Việc treo phát sinh và đã xong theo ngày, ${series.ngay.length} mốc gần nhất`}
    >
      {series.ngay.map((d, i) => {
        const x = pad + i * slot;
        const cm = series.moi[i];
        const cx = series.xong[i];
        const total = cm + cx;
        return (
          <g key={d}>
            {/* Vệt nền: cho thấy mỗi ngày là một khe, kể cả ngày 0 việc. Không có
                nó thì ngày trống biến mất và trục thời gian trông như bị nén lại. */}
            <rect x={x} y={pad} width={slot - gap} height={H - pad * 2} fill="var(--nq-surface)" opacity={0.35} rx={0.6} />
            <title>{`${nhan(d)}: ${cm} phát sinh, ${cx} đã xong`}</title>
            <motion.rect
              className="nq-spark__bar"
              x={x + (slot - gap - barW * 2 - gap) / 2}
              y={H - pad - h(cm)}
              width={barW}
              height={Math.max(cm > 0 ? 0.8 : 0, h(cm))}
              rx={0.5}
              fill={MAU_MOI}
              initial={reduced ? false : { scaleY: 0 }}
              animate={{ scaleY: 1, opacity: total === 0 ? 0.35 : 1 }}
              transition={beat("focus", i * 0.03)}
              style={{ transformOrigin: `${x}px ${H - pad}px` }}
            />
            <motion.rect
              className="nq-spark__bar"
              x={x + (slot - gap - barW * 2 - gap) / 2 + barW + gap}
              y={H - pad - h(cx)}
              width={barW}
              height={Math.max(cx > 0 ? 0.8 : 0, h(cx))}
              rx={0.5}
              fill={MAU_XONG}
              initial={reduced ? false : { scaleY: 0 }}
              animate={{ scaleY: 1, opacity: total === 0 ? 0.35 : 1 }}
              transition={beat("focus", i * 0.03)}
              style={{ transformOrigin: `${x}px ${H - pad}px` }}
            />
          </g>
        );
      })}
    </svg>
  );
}

/**
 * Khối "Xu hướng việc treo" — vỏ + nhãn khoảng ngày + chân khối có lối đi.
 *
 * Tách khỏi `TreoTrendSpark` để `page.tsx` chỉ lo dữ liệu: mọi quyết định về
 * "có vẽ hay không" và "nhãn ghi gì cho trung thực" nằm gọn trong một tệp.
 */
export function TreoTrendBlock({
  series,
  loading,
  soNgayLech,
}: {
  /** `null` = chưa đủ dữ liệu để dựng chuỗi có nghĩa. */
  series: TreoSeries | null;
  loading: boolean;
  /** Số ngày giữa mốc mới nhất và hôm nay — để nhãn nói thật về phạm vi. */
  soNgayLech: number;
}) {
  const reduced = useReducedMotion() ?? false;

  return (
    <motion.section className="nq-dash-chart" {...(reduced ? {} : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: beat("focus") })}>
      <h2 className="nq-block-title nq-dash-chart-title">Xu hướng việc treo</h2>

      {loading ? (
        <p className="nq-spark-empty">Đang đọc lịch sử việc treo…</p>
      ) : series ? (
        <>
          <div className="nq-spark-row">
            <span className="nq-spark-key">
              <span className="nq-spark-key__swatch" style={{ background: MAU_MOI }} />
              Phát sinh: {series.moi.reduce((a, b) => a + b, 0)}
            </span>
            <span className="nq-spark-key">
              <span className="nq-spark-key__swatch" style={{ background: MAU_XONG }} />
              Đã xong: {series.xong.reduce((a, b) => a + b, 0)}
            </span>
          </div>
          <TreoTrendSpark series={series} />
          <div className="nq-spark-axis">
            <span>{nhan(series.ngay[0])}</span>
            <span>{nhan(series.mocCuoi)}</span>
          </div>
          {/* Nhãn phải nói THẬT đang vẽ khoảng nào. Gọi nó là "7 ngày qua" khi mốc
              mới nhất đã cũ là để người dùng đọc sai thời điểm — mà họ không có
              cách nào biết. */}
          <p className="nq-block-foot__note" style={{ marginTop: "var(--nq-s3)", display: "block" }}>
            {soNgayLech > 1
              ? `${series.ngay.length} mốc gần nhất có dữ liệu — mốc mới nhất cách hôm nay ${soNgayLech} ngày (dữ liệu mẫu/ngưng nhập).`
              : `${series.ngay.length} ngày gần nhất, tính đến ${nhan(series.mocCuoi)}.`}
          </p>
        </>
      ) : (
        <p className="nq-spark-empty">
          Chưa đủ dữ liệu theo ngày để vẽ xu hướng — cần ít nhất hai mốc ngày khác nhau trong sổ việc treo.
        </p>
      )}

      <div className="nq-block-foot">
        <span className="nq-block-foot__note">Nguồn: sổ việc treo</span>
        <Link href="/treo">Xem việc treo →</Link>
      </div>
    </motion.section>
  );
}
