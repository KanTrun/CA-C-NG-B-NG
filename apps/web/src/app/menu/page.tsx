"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiSend, apiUpload, ApiError } from "../../lib/api";
import { menuImageUrl } from "../../lib/menu-image";
import { viError } from "../../lib/present";
import { getToken } from "../../lib/session";
import { BomEditor, bomToRows, rowsToBom, type BomRow } from "../../ui/bom-editor";
import {
  Alert,
  Btn,
  Empty,
  Field,
  Input,
  Loading,
  NextSteps,
  PageHeader,
  Textarea,
} from "../../ui/kit";

type Mon = { id: string; ten: string; gia: number; an: boolean; bom: Record<string, number>; hinh_url?: string };

type FormState = {
  id: string;
  ten: string;
  gia: string;
  an: boolean;
  bomRows: BomRow[];
  hinh_url: string;
};

const EMPTY: FormState = {
  id: "",
  ten: "",
  gia: "",
  an: false,
  bomRows: bomToRows({ ly: 1 }),
  hinh_url: "",
};

// Types cho tính năng sinh ảnh quảng cáo.
// Prompt dựng tất định ở server từ tên món + phong cách (không gọi AI để viết
// prompt), nên response chỉ có prompt và lỗi — không còn "phân tích ảnh".
type PromptResult = {
  ok: boolean;
  prompt_en?: string;
  prompt_vi?: string;
  error?: string;
  provider?: string;
  /** Cụm ý kiến bị lọc vì phá ràng buộc bảo toàn sản phẩm (chỉ có ở prompt quảng cáo). */
  bo_qua?: string[];
  /** Loại bao bì suy từ tên món ("bottle", "jar"…). */
  bao_bi?: string;
};

/** Bước 1 — kết quả kiểm ảnh có phải sản phẩm đựng chất lỏng, rõ nét không. */
type CheckKetQua = {
  ok: boolean;
  /** `false` = chưa kiểm được nội dung (thiếu khoá AI thị giác), ảnh vẫn hợp lệ. */
  da_kiem: boolean;
  bao_bi: string;
  /** Câu hiển thị cho người dùng khi ảnh không đạt — nguyên văn từ quy trình. */
  thong_diep: string;
  ly_do?: string;
  ghi?: string;
  error?: string;
};

type ImageGenState = {
  step: "idle" | "prompt" | "generating" | "generated";
  promptEn: string;
  promptVi: string;
  busy: boolean;
  error: string | null;
  generatedUrl: string | null;
  generatedProvider: string;
  generatedModel: string;
  generatedSeed: number | null;
  styleSlug: string;
  aspectRatio: string;
  moTa: string;
  /** Ba cách tạo ảnh — xem `MenuImageGenerateBody.mode` ở API. */
  mode: "from_prompt" | "edit_photo" | "keep_drink";
  /** Ảnh thật của quán — cần cho `edit_photo` và `keep_drink`.
   *  Chọn ảnh ở Bước 1 thì chuyển sang "Luồng ảnh quảng cáo" (xem `adFlow`). */
  photoFile: File | null;
  photoPreviewUrl: string | null;
  /**
   * Luồng ảnh quảng cáo 4 bước có đang bật không.
   *
   * Bật ngay khi người dùng chọn ảnh sản phẩm (Bước 1). Khi đó prompt được lắp
   * bằng template bảo toàn sản phẩm + lịch sử ý kiến, KHÔNG phải mô tả món bằng
   * lời — nhờ vậy chai/lọ của quán ra đúng là chai/lọ của quán.
   */
  adFlow: boolean;
  /** Bước 1 đã qua chưa (ảnh đạt kiểm tra, hoặc chưa kiểm được vì thiếu khoá). */
  checked: boolean;
  /** Ảnh không đạt Bước 1 — hiện câu hướng dẫn gửi lại ảnh. */
  checkError: string | null;
  /** Chưa kiểm được nội dung ảnh (thiếu khoá AI thị giác) — hiện ghi chú cho thật. */
  checkNote: string;
  /** `user_feedback_history` của quy trình — lịch sử ý kiến trong phiên, theo món. */
  feedbackHistory: string[];
  /** Ô nhập ý kiến mới ở Bước 2 và Bước 4. */
  feedbackDraft: string;
  /** Cụm ý kiến bị lọc ở lần lắp prompt gần nhất. */
  boQua: string[];
  /** Người dùng đã bấm "Chốt ảnh" — kết thúc phiên chỉnh sửa. */
  chotAnh: boolean;
};

/** Phong cách thiết kế đã lưu — áp chung cho mọi ảnh quảng cáo của quán. */
type MenuStyle = {
  slug: string;
  ten: string;
  mo_ta: string;
  scene: string;
  lighting: string;
  palette: string;
  lens: string;
};

type StyleCatalog = {
  items: MenuStyle[];
  mac_dinh: string;
  tuy_chon: Record<string, Record<string, string>>;
};

const SCENE_LABEL: Record<string, string> = {
  cafe_wood: "Bàn gỗ quán",
  marble_bar: "Quầy đá marble",
  linen_cloth: "Khăn linen",
  concrete_loft: "Bê tông loft",
  outdoor_garden: "Bàn ngoài vườn",
  studio_paper: "Nền studio",
};

const LIGHT_LABEL: Record<string, string> = {
  golden_hour: "Nắng vàng",
  window_soft: "Sáng cửa sổ",
  moody_low_key: "Tối moody",
  bright_high_key: "Sáng đều",
  neon_evening: "Neon buổi tối",
};

const PALETTE_LABEL: Record<string, string> = {
  warm_wood: "Nâu gỗ ấm",
  sage_green: "Xanh sage",
  terracotta: "Đất nung",
  monochrome_ink: "Đen trắng",
  pastel_dawn: "Pastel hồng",
  deep_emerald: "Xanh ngọc",
};

const LENS_LABEL: Record<string, string> = {
  shallow_85mm: "Xóa phông sâu",
  tight_50mm: "Cận tự nhiên",
  wide_35mm: "Rộng có cảnh",
  macro_detail: "Macro chi tiết",
};

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("doc_file_that_bai"));
    reader.readAsDataURL(file);
  });
}

function emptyImgGen(): ImageGenState {
  return {
    step: "idle",
    promptEn: "",
    promptVi: "",
    busy: false,
    error: null,
    generatedUrl: null,
    generatedProvider: "",
    generatedModel: "",
    generatedSeed: null,
    styleSlug: "",
    aspectRatio: "1:1",
    moTa: "",
    mode: "from_prompt",
    photoFile: null,
    photoPreviewUrl: null,
    adFlow: false,
    checked: false,
    checkError: null,
    checkNote: "",
    feedbackHistory: [],
    feedbackDraft: "",
    boQua: [],
    chotAnh: false,
  };
}

/**
 * Lỗi do NGƯỜI DÙNG chưa làm đủ bước (chưa chọn ảnh, chưa nhập tên…).
 *
 * Khác `ImageGenError` (lỗi từ máy chủ/provider): `message` ở đây do chính UI viết
 * nên đã là câu tiếng Việt chỉ đúng bước còn thiếu. Tách lớp để chỗ bắt lỗi không
 * phải đoán qua nội dung chuỗi.
 */
class ThieuBuocError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ThieuBuocError";
  }
}

/**
 * Lỗi từ provider sinh ảnh. Giữ mã kỹ thuật ở `code` (không hiển thị) và tạo
 * sẵn `message` tiếng Việt để UI không bao giờ đẩy JSON thô ra màn hình.
 */
class ImageGenError extends Error {
  readonly code: string;
  constructor(code: string, provider: string) {
    super(anhLoiTiengViet(code, provider));
    this.name = "ImageGenError";
    this.code = code;
  }
}

/**
 * Dịch mã lỗi provider sinh ảnh thành câu người vận hành hiểu + việc cần làm.
 *
 * Mã đến từ `ca_agents/image_gen.py`: `http_<code>:<json>`, `timeout`, `net:...`,
 * `empty_prompt`, `thieu_key_sua_anh`… Chỉ khớp TIỀN TỐ để không phụ thuộc phần
 * JSON chi tiết của provider (họ đổi thường xuyên).
 */
function anhLoiTiengViet(code: string, provider: string): string {
  const c = code.toLowerCase();
  // Tên nguồn hiển thị cho người vận hành. Cloudflare là provider chính; NVIDIA
  // đã bỏ nhưng vẫn dịch được nếu log cũ còn giữ mã `nvidia`.
  const TEN_NGUON: Record<string, string> = {
    cloudflare: "máy vẽ AI (Cloudflare)",
    nvidia: "máy vẽ AI (NVIDIA)",
  };
  const nguon = TEN_NGUON[provider] ?? (provider || "máy vẽ AI");
  if (c.includes("thieu_ten_mon")) {
    return "Món này chưa có tên nên chưa dựng được ảnh quảng cáo. Nhập tên món ở ô “Tên món hiển thị” rồi lưu lại.";
  }
  if (c.includes("anh_khong_phai_san_pham_nuoc")) {
    return "Ảnh bạn gửi không phải là ảnh sản phẩm dạng nước (chai/lọ/bình chứa chất lỏng). Vui lòng gửi lại ảnh sản phẩm rõ nét để mình xử lý.";
  }
  if (c.includes("thieu_key_sua_anh")) {
    return "Chưa có khoá để AI sửa ảnh thật. Vào phần cài đặt dán khoá Cloudflare miễn phí (hoặc dùng chế độ “AI vẽ mới”), rồi thử lại.";
  }
  if (c.includes("http_401") || c.includes("http_403") || c.includes("unauthorized")) {
    return `Chưa được phép gọi ${nguon}. Kiểm tra lại khoá API trong phần cài đặt rồi thử lại; nếu vẫn vậy báo quản lý.`;
  }
  if (c.includes("http_429") || c.includes("rate limit") || c.includes("quota")) {
    return `${nguon} đang hết hạn mức. Chờ vài phút rồi bấm “Tạo lại ảnh khác”; nếu vẫn vậy báo quản lý.`;
  }
  if (c.includes("http_404")) {
    return `Máy vẽ AI không có mẫu này nữa. Báo quản lý để đổi mẫu trong phần cài đặt.`;
  }
  if (c.includes("timeout") || c.includes("net:")) {
    return `Máy vẽ AI phản hồi chậm hoặc mạng đang chập. Chờ một lát rồi bấm “Tạo lại ảnh khác”.`;
  }
  if (c.startsWith("http_5") || c.includes("bad_json") || c.includes("no_image")) {
    return `${nguon} đang lỗi nên chưa ra ảnh. Thử lại sau ít phút; nếu vẫn vậy báo quản lý.`;
  }
  return `Không tạo được ảnh quảng cáo. Bấm “Tạo lại ảnh khác”; nếu vẫn vậy báo quản lý.`;
}

/**
 * Chọn câu hiển thị cho lỗi của khu tạo ảnh.
 *
 * Hai lớp lỗi đã có sẵn câu tiếng Việt đúng ngữ cảnh (UI tự viết, hoặc dịch từ mã
 * provider); các lỗi còn lại (ApiError, mạng) đi qua `viError` để dịch theo mã HTTP.
 */
function loiTaoAnh(e: unknown, doing: string): string {
  if (e instanceof ThieuBuocError || e instanceof ImageGenError) return e.message;
  return viError(e, { doing });
}

function slugFromName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48);
}

function MenuThumb({ mon, selected }: { mon: Mon; selected: boolean }) {
  const [err, setErr] = useState(false);
  const src = menuImageUrl(mon.id, mon.hinh_url);
  return (
    <div className="relative aspect-square w-full overflow-hidden rounded-[var(--nq-radius-bubble)] border border-[var(--nq-line)] bg-[var(--nq-surface-hi)]">
      {!err ? (
        <img src={src} alt="" className="h-full w-full object-cover" onError={() => setErr(true)} />
      ) : (
        <div className="flex h-full items-center justify-center text-xs font-mono uppercase tracking-widest text-[var(--nq-dim)]">
          {mon.ten.slice(0, 2)}
        </div>
      )}
      {selected ? (
        <span className="absolute inset-x-0 bottom-0 bg-[var(--nq-accent)] py-0.5 text-center text-2xs font-bold uppercase text-black">
          Đang sửa
        </span>
      ) : null}
    </div>
  );
}

export default function MenuPage() {
  const [token, setToken] = useState("");
  const [items, setItems] = useState<Mon[]>([]);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // Image generation state
  const [imgGen, setImgGen] = useState<ImageGenState>(emptyImgGen());
  // Danh mục phong cách thiết kế — nạp một lần, dùng cho mọi ảnh trong menu.
  const [styles, setStyles] = useState<StyleCatalog>({ items: [], mac_dinh: "", tuy_chon: {} });
  // Chế độ tạo ảnh nào chạy được (máy chủ đọc key có sẵn). Nạp một lần lúc mở
  // trang để UI khoá lựa chọn không khả thi — người dùng không phải chọn xong mới
  // biết là thiếu khoá.
  const [modeInfo, setModeInfo] = useState<Record<string, { kha_dung: boolean; ly_do: string }>>({});

  const isExisting = useMemo(
    () => Boolean(form.id && items.some((m) => m.id === form.id)),
    [form.id, items],
  );

  const load = useCallback(async () => {
    if (!getToken()) return;
    setLoading(true);
    try {
      const out = await apiGet<{ items: Mon[] }>("/api/v1/menu/quan-tri");
      setItems(out.items ?? []);
      setError(null);
    } catch (e) {
      setError(viError(e, { doing: "mở menu quản trị" }));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStyles = useCallback(async () => {
    if (!getToken()) return;
    try {
      const out = await apiGet<StyleCatalog>("/api/v1/menu/anh/phong-cach");
      setStyles({
        items: out.items ?? [],
        mac_dinh: out.mac_dinh ?? "",
        tuy_chon: out.tuy_chon ?? {},
      });
      setImgGen((s) => ({ ...s, styleSlug: s.styleSlug || out.mac_dinh || "" }));
    } catch {
      // Không chặn trang menu chỉ vì không nạp được danh mục phong cách.
      setStyles({ items: [], mac_dinh: "", tuy_chon: {} });
    }
  }, []);

  /** Nạp chế độ nào chạy được. Lỗi mạng → coi như chạy được hết (máy chủ sẽ chặn sau). */
  const loadModeInfo = useCallback(async () => {
    if (!getToken()) return;
    try {
      const out = await apiGet<{ che_do: Record<string, { kha_dung: boolean; ly_do: string }> }>(
        "/api/v1/menu/anh/kha-dung",
      );
      setModeInfo(out.che_do ?? {});
    } catch {
      setModeInfo({});
    }
  }, []);

  useEffect(() => setToken(getToken()), []);
  useEffect(() => {
    if (token) void load();
  }, [load, token]);
  useEffect(() => {
    if (token) void loadStyles();
  }, [loadStyles, token]);
  useEffect(() => {
    if (token) void loadModeInfo();
  }, [loadModeInfo, token]);

  /** Lý do chế độ không chạy được (rỗng = chạy được). */
  function modeBlocked(mode: ImageGenState["mode"]): string {
    const info = modeInfo[mode];
    if (!info || info.kha_dung) return "";
    return info.ly_do || "Chế độ này chưa dùng được.";
  }

  async function setDefaultStyle(slug: string) {
    try {
      await apiSend(`/api/v1/menu/anh/phong-cach/${slug}/mac-dinh`, {}, "POST");
      setStyles((s) => ({ ...s, mac_dinh: slug }));
      setMsg(`Đã chọn phong cách mặc định cho ảnh mới.`);
    } catch (e) {
      setError(viError(e, { doing: "đặt phong cách mặc định" }));
    }
  }

  function select(mon: Mon) {
    setForm({
      id: mon.id,
      ten: mon.ten,
      gia: String(mon.gia),
      an: mon.an,
      bomRows: bomToRows(mon.bom),
      hinh_url: mon.hinh_url ?? "",
    });
    // Reset image generation state when selecting new item
    setImgGen(emptyImgGen());
    setMsg(null);
  }

  function resetForm() {
    setForm(EMPTY);
    setImgGen(emptyImgGen());
    setMsg(null);
  }

  async function onImage(file: File | null) {
    if (!file || !isExisting) {
      setError("Lưu món lần đầu trước, sau đó mới tải ảnh được.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const out = await apiUpload<{ hinh_url?: string }>(`/api/v1/menu/${form.id.trim()}/anh`, fd);
      setForm((f) => ({ ...f, hinh_url: out.hinh_url ?? f.hinh_url }));
      setMsg("Đã tải ảnh món.");
      await load();
    } catch (e) {
      setError(viError(e, { doing: "tải ảnh món" }));
    } finally {
      setBusy(false);
    }
  }

  // ── Sinh ảnh quảng cáo ─────────────────────────────────────────────────
  // Hai luồng, khác nhau ở chỗ prompt có mô tả SẢN PHẨM hay không:
  //
  // * "AI vẽ mới" (không ảnh): prompt mô tả món bằng lời → model vẽ lại sản phẩm.
  // * "Ảnh quảng cáo từ ảnh thật" (4 bước): ảnh gốc là nguồn sự thật về sản phẩm,
  //   prompt CHỈ tả bối cảnh + ràng buộc bảo toàn (hình dáng, nhãn, chữ, logo,
  //   màu, nắp). Nhờ vậy chai/lọ của quán ra đúng là chai/lọ của quán.
  //
  // Cả hai dựng prompt TẤT ĐỊNH ở server — bấm là ra ngay, không gọi AI viết prompt.

  /** POST JSON tới API rồi trả JSON; dịch lỗi mạng/HTTP thành ApiError. */
  async function postJson<T>(path: string, body: unknown): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify(body),
      });
    } catch {
      // Mất mạng / API chưa chạy → ApiError(0) để `viError` nhắc kiểm tra kết nối.
      throw new ApiError(0);
    }
    if (!res.ok) {
      const errData = (await res.json().catch(() => ({}))) as { detail?: unknown };
      throw new ApiError(res.status, errData.detail);
    }
    return (await res.json()) as T;
  }

  /** Gọi server dựng prompt (nhanh, không mạng ra ngoài) để hiện cho người dùng. */
  async function buildPrompt(
    overrides: Partial<Pick<ImageGenState, "styleSlug" | "aspectRatio" | "moTa">> = {},
  ): Promise<PromptResult> {
    const styleSlug = overrides.styleSlug ?? imgGen.styleSlug;
    const aspectRatio = overrides.aspectRatio ?? imgGen.aspectRatio;
    const moTa = overrides.moTa ?? imgGen.moTa;
    const data = await postJson<PromptResult>(`/api/v1/menu/${form.id.trim()}/anh/prompt`, {
      mo_ta: moTa,
      aspect_ratio: aspectRatio,
      ...(styleSlug ? { style_slug: styleSlug } : {}),
    });
    if (!data.ok) {
      throw new ImageGenError(String(data.error ?? "unknown"), String(data.provider ?? ""));
    }
    return data;
  }

  /**
   * BƯỚC 3 + BƯỚC 4 — lắp prompt ảnh quảng cáo từ lịch sử ý kiến.
   *
   * Gửi TOÀN BỘ `feedback_history` (không phải chỉ ý mới nhất): ý kiến cũ không
   * liên quan (ánh sáng, góc chụp…) phải còn trong prompt khi người dùng đổi ý
   * khác. Server tự đặt ý kiến mới nhất ở cuối prompt để nó thắng khi mâu thuẫn.
   */
  async function buildAdPrompt(
    overrides: Partial<Pick<ImageGenState, "styleSlug" | "feedbackHistory">> = {},
  ): Promise<PromptResult> {
    const styleSlug = overrides.styleSlug ?? imgGen.styleSlug;
    const history = overrides.feedbackHistory ?? imgGen.feedbackHistory;
    const data = await postJson<PromptResult>(
      `/api/v1/menu/${form.id.trim()}/anh/prompt-quang-cao`,
      {
        feedback_history: history,
        ...(styleSlug ? { style_slug: styleSlug } : {}),
      },
    );
    if (!data.ok) {
      throw new ImageGenError(String(data.error ?? "unknown"), String(data.provider ?? ""));
    }
    return data;
  }

  /**
   * BƯỚC 1 — kiểm ảnh gửi lên có phải sản phẩm đựng chất lỏng, nhìn rõ không.
   *
   * Trả về `null` khi mất mạng/lỗi máy chủ: chặn ở đây là chặn oan, vì lỗi hạ
   * tầng không nói gì về ảnh. Người dùng vẫn đi tiếp và nhận `checkNote` nói rõ
   * là chưa kiểm được nội dung.
   */
  async function checkProductImage(file: File): Promise<CheckKetQua | null> {
    try {
      const dataUrl = await fileToDataUrl(file);
      return await postJson<CheckKetQua>(`/api/v1/menu/${form.id.trim()}/anh/kiem-tra`, {
        original_base64: dataUrl,
      });
    } catch {
      return null;
    }
  }

  /** Mở khu sinh ảnh và hiện prompt ngay (không cần ảnh gốc). */
  async function openImageGen() {
    if (!isExisting) {
      setImgGen((s) => ({ ...s, error: "Lưu món lần đầu trước." }));
      return;
    }
    setImgGen((s) => ({ ...s, step: "prompt", busy: true, error: null }));
    try {
      const data = await buildPrompt();
      setImgGen((s) => ({
        ...s,
        step: "prompt",
        busy: false,
        promptEn: data.prompt_en ?? "",
        promptVi: data.prompt_vi ?? "",
      }));
    } catch (e) {
      setImgGen((s) => ({
        ...s,
        step: "idle",
        busy: false,
        error: loiTaoAnh(e, "dựng prompt"),
      }));
    }
  }

  /** Đổi phong cách/mô tả → dựng lại prompt ngay để người dùng thấy trước. */
  async function refreshPrompt(next: Partial<Pick<ImageGenState, "styleSlug" | "aspectRatio" | "moTa">>) {
    setImgGen((s) => ({ ...s, ...next }));
    if (!isExisting) return;
    // Ở luồng ảnh thật, prompt do Bước 3 dựng từ lịch sử ý kiến — gọi lại đây chỉ
    // để đồng bộ phong cách, KHÔNG dựng lại từ tên món (làm vậy là mất ràng buộc
    // bảo toàn sản phẩm và model sẽ vẽ lại chai thành một sản phẩm khác).
    if (imgGen.adFlow) {
      try {
        const data = await buildAdPrompt({ ...next, feedbackHistory: imgGen.feedbackHistory });
        setImgGen((s) => ({
          ...s,
          promptEn: data.prompt_en ?? s.promptEn,
          promptVi: data.prompt_vi ?? s.promptVi,
          boQua: data.bo_qua ?? [],
          error: null,
        }));
      } catch (e) {
        setImgGen((s) => ({ ...s, error: loiTaoAnh(e, "dựng prompt") }));
      }
      return;
    }
    try {
      const data = await buildPrompt(next);
      setImgGen((s) => ({
        ...s,
        promptEn: data.prompt_en ?? s.promptEn,
        promptVi: data.prompt_vi ?? s.promptVi,
        error: null,
      }));
    } catch (e) {
      setImgGen((s) => ({
        ...s,
        error: loiTaoAnh(e, "dựng prompt"),
      }));
    }
  }

  /**
   * BƯỚC 2 / BƯỚC 4 — ghi nhận một ý kiến vào `user_feedback_history` rồi lắp lại
   * prompt. Không yêu cầu người dùng gửi lại ảnh gốc: ảnh đã nằm trong phiên.
   */
  async function submitFeedback() {
    const moi = imgGen.feedbackDraft.trim();
    if (!moi) return;
    // Ý kiến mới được NỐI vào lịch sử (không ghi đè). Mâu thuẫn với ý cũ do
    // server xử lý: ý kiến mới nhất đứng cuối prompt nên thắng.
    const history = [...imgGen.feedbackHistory, moi].slice(-12);
    setImgGen((s) => ({ ...s, feedbackHistory: history, feedbackDraft: "", busy: true }));
    try {
      const data = await buildAdPrompt({ feedbackHistory: history });
      setImgGen((s) => ({
        ...s,
        busy: false,
        promptEn: data.prompt_en ?? "",
        promptVi: data.prompt_vi ?? "",
        boQua: data.bo_qua ?? [],
        error: null,
      }));
    } catch (e) {
      setImgGen((s) => ({ ...s, busy: false, error: loiTaoAnh(e, "dựng prompt") }));
    }
  }

  /** Gọi sinh ảnh. `extra` dùng khi lưu ảnh (ghim seed + bật lưu). */
  async function requestGenerateImage(
    extra: Record<string, unknown> = {},
    promptOverride?: string,
  ) {
    const body: Record<string, unknown> = {
      // Gửi prompt đang hiện trên UI (người dùng có thể đã sửa tay); trống thì
      // server tự dựng lại — theo luồng ảnh quảng cáo nếu `prompt_quang_cao`.
      prompt_en: promptOverride ?? imgGen.promptEn,
      aspect_ratio: imgGen.aspectRatio,
      mode: imgGen.mode,
      ...(imgGen.styleSlug ? { style_slug: imgGen.styleSlug } : {}),
      // Ở luồng ảnh thật, prompt trống thì server dựng từ template + lịch sử ý
      // kiến (không phải từ tên món) — nên phải gửi kèm cả hai.
      ...(imgGen.adFlow && imgGen.mode !== "from_prompt"
        ? { prompt_quang_cao: true, feedback_history: imgGen.feedbackHistory }
        : {}),
      ...extra,
    };
    // Hai chế độ cần ảnh thật: edit_photo (AI sửa ảnh) và keep_drink (giữ sản phẩm).
    if (imgGen.mode !== "from_prompt") {
      if (!imgGen.photoFile) {
        // Lỗi do người dùng chưa làm đủ bước — phải nói RÕ bước còn thiếu, không
        // để rơi vào câu chung chung "không tạo được ảnh".
        throw new ThieuBuocError(
          "Chế độ này cần ảnh sản phẩm thật. Bấm ô “Ảnh sản phẩm thật tại quán” ở trên để chọn ảnh, hoặc đổi sang chế độ “AI vẽ mới”.",
        );
      }
      body.original_base64 = await fileToDataUrl(imgGen.photoFile);
    }
    let res: Response;
    try {
      res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/api/v1/menu/${form.id.trim()}/anh/generate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify(body),
        },
      );
    } catch {
      // `fetch` ném TypeError khi mất mạng / API chưa chạy — KHÔNG phải ApiError.
      // Bọc thành ApiError(0) để `viError` chọn đúng câu "chưa nối được máy chủ";
      // ném nguyên TypeError thì status = -1 và người dùng nhận câu chung chung.
      throw new ApiError(0);
    }
    if (!res.ok) {
      // Ném ApiError (không phải Error thường) để `viError` đọc được `status` và
      // dịch thành câu tiếng Việt. Ném Error thường làm `status = -1` → câu chung
      // chung vô nghĩa, hoặc lộ JSON thô của provider ra UI.
      const errData = (await res.json().catch(() => ({}))) as { detail?: unknown };
      throw new ApiError(res.status, errData.detail);
    }
    const data = await res.json();
    if (!data.ok) {
      // Lỗi từ provider ảnh (Cloudflare/Gemini/Pollinations): `error` là mã kỹ
      // thuật (`http_429:{...json...}`). Dịch thành câu người vận hành hiểu được
      // thay vì đẩy nguyên JSON ra màn hình.
      throw new ImageGenError(String(data.error ?? "unknown"), String(data.provider ?? ""));
    }
    return data;
  }

  async function handleGenerateImage() {
    setImgGen((s) => ({ ...s, step: "generating", busy: true, error: null, chotAnh: false }));
    try {
      const data = await requestGenerateImage();
      setImgGen((s) => ({
        ...s,
        step: "generated",
        busy: false,
        generatedUrl: `data:${data.image_mime};base64,${data.image_base64}`,
        generatedProvider: data.provider ?? "",
        generatedModel: data.model ?? "",
        generatedSeed: data.seed ?? null,
      }));
    } catch (e) {
      setImgGen((s) => ({
        ...s,
        step: "prompt",
        busy: false,
        error: loiTaoAnh(e, "tạo ảnh quảng cáo"),
      }));
    }
  }

  async function handleSaveGeneratedImage() {
    if (!imgGen.generatedUrl) return;
    setImgGen((s) => ({ ...s, busy: true, error: null }));
    try {
      // Sinh LẠI với đúng seed đang hiện để ảnh lưu trùng ảnh đã xem, rồi lưu
      // luôn làm ảnh đại diện món trong cùng một lượt gọi.
      const data = await requestGenerateImage({
        seed: imgGen.generatedSeed,
        save_as_menu_image: true,
      });
      setForm((f) => ({ ...f, hinh_url: data.hinh_url ?? f.hinh_url }));
      setMsg("Đã lưu ảnh quảng cáo làm ảnh đại diện món.");
      setImgGen((s) => ({ ...emptyImgGen(), styleSlug: s.styleSlug, aspectRatio: s.aspectRatio }));
      void load();
    } catch (e) {
      setImgGen((s) => ({
        ...s,
        busy: false,
        error: loiTaoAnh(e, "lưu ảnh quảng cáo"),
      }));
    }
  }

  /** Chọn ảnh thật của quán: tạo preview + nhớ file, rồi chạy BƯỚC 1 (kiểm ảnh). */
  function handlePickPhoto(file: File | null) {
    setImgGen((s) => {
      if (s.photoPreviewUrl) URL.revokeObjectURL(s.photoPreviewUrl);
      if (!file) {
        // Bỏ ảnh = thoát luồng ảnh quảng cáo, quay về "AI vẽ mới".
        return {
          ...s,
          photoFile: null,
          photoPreviewUrl: null,
          adFlow: false,
          checked: false,
          checkError: null,
          checkNote: "",
          feedbackHistory: [],
          feedbackDraft: "",
          boQua: [],
        };
      }
      // Chọn ảnh xong thì chuyển sang chế độ dùng ảnh — nhưng CHỈ khi chế độ đó
      // chạy được. Tự chuyển sang chế độ thiếu khoá thì người dùng bấm là hỏng
      // ngay, dù họ không hề chọn nó.
      let mode = s.mode;
      if (mode === "from_prompt") {
        mode = !modeBlocked("edit_photo")
          ? "edit_photo"
          : !modeBlocked("keep_drink")
            ? "keep_drink"
            : "from_prompt";
      }
      // Có ảnh sản phẩm → bật luồng ảnh quảng cáo (Bước 1 đang chạy). Lịch sử ý
      // kiến reset vì đây là sản phẩm/ảnh khác.
      return {
        ...s,
        photoFile: file,
        photoPreviewUrl: URL.createObjectURL(file),
        mode,
        adFlow: true,
        checked: false,
        checkError: null,
        checkNote: "",
        feedbackHistory: [],
        feedbackDraft: "",
        boQua: [],
        chotAnh: false,
        error: null,
      };
    });
    if (!file) return;
    // BƯỚC 1 — chạy nền: người dùng vẫn thấy preview ngay, không phải chờ AI.
    void (async () => {
      const ketQua = await checkProductImage(file);
      setImgGen((s) => {
        // Người dùng đã đổi ảnh khác trong lúc chờ → kết quả này không còn giá trị.
        if (s.photoFile !== file) return s;
        if (ketQua === null) {
          return {
            ...s,
            checked: false,
            checkError: null,
            checkNote: "Chưa kiểm được ảnh (chưa nối được máy chủ). Vẫn dùng được ảnh này.",
          };
        }
        if (!ketQua.ok) {
          return {
            ...s,
            checked: false,
            checkError: ketQua.thong_diep || "Ảnh không hợp lệ.",
            checkNote: "",
          };
        }
        return {
          ...s,
          checked: true,
          checkError: null,
          checkNote: ketQua.ghi ?? "",
        };
      });
    })();
  }

  /** Xác nhận chốt ảnh — kết thúc phiên chỉnh sửa (Bước 4). */
  function handleChotAnh() {
    setImgGen((s) => ({ ...s, chotAnh: true, error: null }));
    setMsg("Đã chốt ảnh. Bấm “Lưu làm ảnh đại diện món” để dùng ảnh này cho menu.");
  }

  function handleCloseImageGen() {
    if (imgGen.photoPreviewUrl) URL.revokeObjectURL(imgGen.photoPreviewUrl);
    // Giữ phong cách, tỷ lệ khung và chế độ giữa các lần mở — làm nhiều món liên
    // tiếp không phải chọn lại từ đầu.
    setImgGen({
      ...emptyImgGen(),
      styleSlug: imgGen.styleSlug,
      aspectRatio: imgGen.aspectRatio,
      mode: imgGen.mode,
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const ten = form.ten.trim();
    if (!ten) {
      setError("Nhập tên món.");
      return;
    }

    const id = isExisting ? form.id.trim() : slugFromName(ten);
    if (!id) {
      setError("Tên món cần có ít nhất một chữ hoặc số.");
      return;
    }

    const bom = rowsToBom(form.bomRows);
    if (Object.keys(bom).length === 0) {
      setError("Thêm ít nhất một nguyên liệu và nhập số lượng lớn hơn 0.");
      return;
    }

    const gia = Number(form.gia);
    if (!Number.isInteger(gia) || gia < 0) {
      setError("Giá bán cần là số nguyên (ví dụ: 35000).");
      return;
    }

    setBusy(true);
    try {
      await apiSend(`/api/v1/menu/${id}`, { ten, gia, an: form.an, bom, hinh_url: form.hinh_url }, "PUT");
      setForm((f) => ({ ...f, id }));
      setMsg(isExisting ? "Đã cập nhật món." : "Đã thêm món mới. Bạn có thể tải ảnh ngay bên dưới.");
      await load();
    } catch (err) {
      setError(viError(err, { doing: "lưu món" }));
    } finally {
      setBusy(false);
    }
  }

  if (!token) return null;

  return (
    <section className="nq-page nq-page--wide">
      <PageHeader
        kicker="Admin quán"
        title="Menu & giá"
        meta="Chọn món bên trái để sửa, hoặc điền form bên phải để thêm món mới."
      />
      {error ? <Alert>{error}</Alert> : null}
      {msg ? <Alert kind="ok">{msg}</Alert> : null}

      <div className="nq-split nq-split--menu">
        <div>
          <h2 className="mb-4 text-sm font-mono uppercase tracking-widest text-[var(--nq-dim)]">Danh mục món</h2>
          {loading ? <Loading skeleton="list">Đang tải menu…</Loading> : null}
          {!loading && items.length === 0 ? <Empty>Chưa có món nào.</Empty> : null}
          <div className="nq-card-grid">
            {items.map((mon) => (
              <button
                key={mon.id}
                type="button"
                className={`nq-menu-card ${form.id === mon.id ? "nq-menu-card--on" : ""}`}
                onClick={() => select(mon)}
              >
                <MenuThumb mon={mon} selected={form.id === mon.id} />
                <div>
                  <strong className="block text-sm">{mon.ten}</strong>
                  <p className="nq-muted text-xs">
                    {mon.gia.toLocaleString("vi-VN")}đ · {mon.an ? "ẩn trên quầy" : "đang bán"}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>

        <aside className="nq-sticky-panel nq-menu-form space-y-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-mono uppercase tracking-widest">{isExisting ? "Sửa món" : "Thêm món mới"}</h2>
            {form.ten || form.id ? (
              <Btn variant="ghost" onClick={resetForm}>
                Làm mới
              </Btn>
            ) : null}
          </div>

          <form className="space-y-5" onSubmit={(e) => void submit(e)}>
            <Field label="Tên món hiển thị" hint="Tên khách và nhân viên thấy trên quầy.">
              <Input
                value={form.ten}
                onChange={(e) => setForm({ ...form, ten: e.target.value })}
                placeholder="Ví dụ: Trà đào"
                required
              />
            </Field>

            <Field label="Giá bán" hint="Nhập số tiền bằng đồng, không cần dấu chấm.">
              <Input
                value={form.gia}
                onChange={(e) => setForm({ ...form, gia: e.target.value.replace(/\D/g, "") })}
                inputMode="numeric"
                placeholder="35000"
                required
              />
            </Field>

            {isExisting ? (
              <p className="text-xs text-[var(--nq-ink-muted)]">
                Mã trong hệ thống: <span className="font-mono text-[var(--nq-ink)]">{form.id}</span>
              </p>
            ) : null}

            <section className="nq-menu-form__section" aria-labelledby="menu-bom-title">
              <h3 id="menu-bom-title" className="nq-menu-form__section-title">
                Nguyên liệu ước lượng
              </h3>
              <BomEditor rows={form.bomRows} onChange={(bomRows) => setForm({ ...form, bomRows })} />
            </section>

            <Field label="Ảnh món">
              <input
                type="file"
                className="nq-input"
                accept="image/jpeg,image/png,image/webp,image/gif"
                onChange={(e) => void onImage(e.target.files?.[0] ?? null)}
                disabled={!isExisting || busy}
              />
              <p className="nq-muted mt-1 text-xs">
                {isExisting
                  ? "JPG/PNG/WebP, tối đa 4MB."
                  : "Lưu món lần đầu trước, sau đó quay lại để tải ảnh."}
              </p>
            </Field>

            {/* AI Image Generation Section */}
            {isExisting && (
              <section className="nq-menu-form__section" aria-labelledby="menu-aigen-title">
                <h3 id="menu-aigen-title" className="nq-menu-form__section-title">
                  Tạo ảnh quảng cáo (AI)
                </h3>

                {imgGen.step === "idle" && (
                  <div className="space-y-3">
                    <p className="text-sm text-[var(--nq-dim)]">
                      Chụp ảnh chai/lọ/ly nước tại quán rồi để AI dàn dựng lại thành ảnh quảng cáo
                      chuyên nghiệp — giữ nguyên hình dáng, nhãn, chữ, logo và màu của sản phẩm.
                    </p>
                    <Btn variant="primary" onClick={() => void openImageGen()} busy={imgGen.busy} block>
                      Tạo ảnh quảng cáo (AI)
                    </Btn>
                    <p className="nq-muted text-xs">
                      Cần ảnh sản phẩm thật. Muốn AI tự vẽ ảnh mới từ tên món (không cần ảnh) thì
                      chọn chế độ &ldquo;AI vẽ mới&rdquo; ở bước sau.
                    </p>
                  </div>
                )}

                {(imgGen.step === "prompt" || imgGen.busy) && (
                  <div className="space-y-4">
                    {/* BƯỚC 1 — ảnh sản phẩm + kết quả kiểm ảnh */}
                    <div className="rounded-[var(--nq-radius-bubble)] border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-3 space-y-3">
                      <div>
                        <label className="nq-muted text-xs" htmlFor="aigen-photo">
                          Bước 1 — Ảnh sản phẩm thật tại quán
                        </label>
                        <input
                          id="aigen-photo"
                          type="file"
                          className="nq-input w-full mt-1"
                          accept="image/jpeg,image/png,image/webp"
                          disabled={imgGen.busy}
                          onChange={(e) => {
                            handlePickPhoto(e.target.files?.[0] ?? null);
                            e.target.value = "";
                          }}
                        />
                        <p className="nq-muted mt-1 text-xs">
                          JPG/PNG/WebP, cạnh ngắn từ 200px. Chọn ảnh thì AI dàn dựng từ ảnh thật;
                          bỏ trống thì AI vẽ mới theo tên món.
                        </p>
                      </div>

                      {imgGen.photoPreviewUrl ? (
                        <div className="relative aspect-square max-w-[140px] overflow-hidden rounded-[var(--nq-radius-bubble)] border border-[var(--nq-line)]">
                          <img
                            src={imgGen.photoPreviewUrl}
                            alt="Ảnh sản phẩm đã chọn"
                            className="h-full w-full object-cover"
                          />
                          <button
                            type="button"
                            className="absolute right-1 top-1 rounded bg-black/60 px-2 py-0.5 text-xs text-white"
                            onClick={() => handlePickPhoto(null)}
                            disabled={imgGen.busy}
                          >
                            Bỏ
                          </button>
                        </div>
                      ) : null}

                      {/* Ảnh không đạt → chặn ngay, không cho sang Bước 2. Câu do máy chủ
                          trả về là nguyên văn của quy trình nên hai nơi không lệch nhau. */}
                      {imgGen.checkError ? (
                        <Alert>{imgGen.checkError}</Alert>
                      ) : null}
                      {/* Ghi chú hiện ở MỌI trường hợp có nội dung: khi chưa kiểm được
                          (thiếu khoá AI thị giác), người dùng cần biết là ảnh chưa được
                          AI xác nhận nội dung — không phải "đã kiểm và đạt". */}
                      {imgGen.checkNote ? (
                        <p className="nq-muted text-xs">{imgGen.checkNote}</p>
                      ) : null}

                      <div>
                        <label className="nq-muted text-xs" htmlFor="aigen-mode">
                          AI xử lý thế nào
                        </label>
                        <select
                          id="aigen-mode"
                          className="nq-input w-full mt-1"
                          value={imgGen.mode}
                          disabled={imgGen.busy}
                          onChange={(e) =>
                            setImgGen((s) => ({
                              ...s,
                              mode: e.target.value as ImageGenState["mode"],
                            }))
                          }
                        >
                          <option value="edit_photo" disabled={Boolean(modeBlocked("edit_photo"))}>
                            Dàn dựng lại ảnh thật (khuyến nghị)
                            {modeBlocked("edit_photo") ? " — chưa dùng được" : ""}
                          </option>
                          <option value="keep_drink" disabled={Boolean(modeBlocked("keep_drink"))}>
                            Giữ nguyên sản phẩm, AI chỉ vẽ nền
                            {modeBlocked("keep_drink") ? " — chưa dùng được" : ""}
                          </option>
                          <option value="from_prompt">AI vẽ mới hoàn toàn (không dùng ảnh)</option>
                        </select>
                        <p className="nq-muted mt-1 text-xs">
                          {imgGen.mode === "edit_photo"
                            ? "AI dựng lại chính ảnh bạn chụp: đổi ánh sáng, nền, bố cục — nhưng giữ nguyên hình dáng, nhãn, chữ, logo và màu sản phẩm."
                            : imgGen.mode === "keep_drink"
                              ? "Sản phẩm giữ 100% pixel gốc (không AI vẽ lại), chỉ nền thay bằng cảnh mới kèm bóng đổ."
                              : "Không dùng ảnh chụp; AI vẽ từ tên món (nhanh nhất, 1–4 giây) — không đảm bảo giống sản phẩm thật."}
                        </p>
                        {/* Nói rõ VÌ SAO chế độ đang chọn không chạy được + cách khắc phục. */}
                        {modeBlocked(imgGen.mode) ? (
                          <p className="mt-2 rounded-[var(--nq-radius-bubble)] border border-[var(--nq-line)] bg-[var(--nq-surface)] p-2 text-xs text-[var(--nq-dim)]">
                            {modeBlocked(imgGen.mode)}
                          </p>
                        ) : null}
                      </div>
                    </div>

                    {/* Tỷ lệ khung + phong cách: đổi là prompt dựng lại ngay */}
                    <div className="rounded-[var(--nq-radius-bubble)] border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-3 space-y-3">
                      <div>
                        <label className="nq-muted text-xs" htmlFor="aigen-ratio">
                          Tỷ lệ khung
                        </label>
                        <select
                          id="aigen-ratio"
                          className="nq-input w-full mt-1"
                          value={imgGen.aspectRatio}
                          disabled={imgGen.busy}
                          onChange={(e) => void refreshPrompt({ aspectRatio: e.target.value })}
                        >
                          <option value="1:1">1:1 — vuông (Facebook, Zalo)</option>
                          <option value="4:5">4:5 — dọc (Instagram, menu)</option>
                          <option value="9:16">9:16 — dọc cao (Story, Reels)</option>
                          <option value="16:9">16:9 — ngang (banner, website)</option>
                        </select>
                      </div>

                      {styles.items.length > 0 ? (
                        <div>
                          <div className="flex items-center justify-between gap-2">
                            <label className="nq-muted text-xs" htmlFor="aigen-style">
                              Phong cách thiết kế
                            </label>
                            {imgGen.styleSlug && imgGen.styleSlug !== styles.mac_dinh ? (
                              <button
                                type="button"
                                className="text-xs font-mono uppercase text-[var(--nq-copper)] hover:underline"
                                onClick={() => void setDefaultStyle(imgGen.styleSlug)}
                                disabled={imgGen.busy}
                              >
                                Đặt làm mặc định
                              </button>
                            ) : (
                              <span className="text-xs font-mono uppercase text-[var(--nq-dim)]">
                                Mặc định của quán
                              </span>
                            )}
                          </div>
                          <select
                            id="aigen-style"
                            className="nq-input w-full mt-1"
                            value={imgGen.styleSlug}
                            disabled={imgGen.busy}
                            onChange={(e) => void refreshPrompt({ styleSlug: e.target.value })}
                          >
                            {styles.items.map((st) => (
                              <option key={st.slug} value={st.slug}>
                                {st.ten}
                                {st.slug === styles.mac_dinh ? " (mặc định)" : ""}
                              </option>
                            ))}
                          </select>
                          {(() => {
                            const cur = styles.items.find((st) => st.slug === imgGen.styleSlug);
                            if (!cur) return null;
                            return (
                              <p className="nq-muted mt-1 text-xs">
                                {cur.mo_ta ? `${cur.mo_ta} · ` : ""}
                                {SCENE_LABEL[cur.scene] ?? cur.scene} · {LIGHT_LABEL[cur.lighting] ?? cur.lighting} ·{" "}
                                {PALETTE_LABEL[cur.palette] ?? cur.palette} · {LENS_LABEL[cur.lens] ?? cur.lens}
                              </p>
                            );
                          })()}
                          <p className="nq-muted mt-1 text-xs">
                            &ldquo;Đặt làm mặc định&rdquo; để mọi món khác trong menu ra cùng một tông —
                            nhìn như cùng một quán.
                          </p>
                        </div>
                      ) : null}

                      {/* Ô này chỉ có tác dụng ở chế độ "AI vẽ mới" (mô tả thêm cho prompt
                          vẽ lại sản phẩm). Ở luồng ảnh quảng cáo, ý kiến đi qua khối
                          Bước 2/4 bên dưới — hiện thêm ô này sẽ là một điều khiển
                          không làm gì, người dùng gõ vào rồi thắc mắc sao ảnh không đổi. */}
                      {!imgGen.adFlow ? (
                        <div>
                          <label className="nq-muted text-xs" htmlFor="aigen-mota">
                            Mô tả thêm (tùy chọn)
                          </label>
                          <Input
                            id="aigen-mota"
                            className="mt-1"
                            value={imgGen.moTa}
                            placeholder="Ví dụ: thêm lá bạc hà và đá viên"
                            disabled={imgGen.busy}
                            onChange={(e) => setImgGen((s) => ({ ...s, moTa: e.target.value }))}
                            onBlur={() => void refreshPrompt({})}
                          />
                        </div>
                      ) : null}
                    </div>

                    {/* BƯỚC 2 (lần đầu) / BƯỚC 4 (chỉnh sửa) — thu ý kiến bằng lời thường.
                        Người dùng KHÔNG cần viết prompt kỹ thuật: chỉ mô tả ý tưởng, phần
                        dịch sang tiếng Anh và ràng buộc bảo toàn sản phẩm do máy chủ lo. */}
                    {imgGen.adFlow ? (
                      <div className="rounded-[var(--nq-radius-bubble)] border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-3 space-y-3">
                        <div>
                          <label className="nq-muted text-xs" htmlFor="aigen-feedback">
                            {imgGen.generatedUrl
                              ? "Bước 4 — Muốn chỉnh gì thêm cho ảnh này?"
                              : "Bước 2 — Bạn muốn ảnh sản phẩm này trông như thế nào?"}
                          </label>
                          <Input
                            id="aigen-feedback"
                            className="mt-1"
                            value={imgGen.feedbackDraft}
                            placeholder="Ví dụ: nền xanh, nắng sớm, thêm hoa cạnh sản phẩm"
                            disabled={imgGen.busy}
                            onChange={(e) => setImgGen((s) => ({ ...s, feedbackDraft: e.target.value }))}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                void submitFeedback();
                              }
                            }}
                          />
                          <p className="nq-muted mt-1 text-xs">
                            Mô tả bằng lời thường (bối cảnh, ánh sáng, phong cách, tâm trạng).
                            Sản phẩm luôn giữ nguyên hình dáng, nhãn, chữ, logo, màu và nắp.
                          </p>
                        </div>
                        <Btn
                          variant="primary"
                          onClick={() => void submitFeedback()}
                          busy={imgGen.busy}
                          busyLabel="Đang dựng prompt…"
                          disabled={!imgGen.feedbackDraft.trim()}
                          block
                        >
                          {imgGen.generatedUrl ? "Áp dụng ý kiến và tạo lại" : "Ghi nhận ý kiến"}
                        </Btn>

                        {imgGen.feedbackHistory.length > 0 ? (
                          <div>
                            <p className="nq-muted text-xs">
                              Ý kiến đã ghi nhận ({imgGen.feedbackHistory.length}) — ý kiến sau cùng
                              được ưu tiên khi mâu thuẫn:
                            </p>
                            <ol className="mt-1 space-y-1 text-xs text-[var(--nq-dim)]">
                              {imgGen.feedbackHistory.map((yk, i) => (
                                <li key={`${i}-${yk}`}>
                                  {i + 1}. {yk}
                                </li>
                              ))}
                            </ol>
                          </div>
                        ) : null}

                        {/* Nói RÕ vì sao một yêu cầu không được áp dụng — âm thầm bỏ thì
                            người dùng tưởng AI lờ mình. */}
                        {imgGen.boQua.length > 0 ? (
                          <p className="rounded-[var(--nq-radius-bubble)] border border-[var(--nq-line)] bg-[var(--nq-surface)] p-2 text-xs text-[var(--nq-dim)]">
                            Không áp dụng được: {imgGen.boQua.join("; ")} — ảnh quảng cáo phải giữ
                            nguyên sản phẩm và không thêm người.
                          </p>
                        ) : null}

                        {imgGen.checked ? (
                          <p className="nq-muted text-xs">
                            Ảnh đã qua kiểm tra: đúng là sản phẩm dạng nước và nhìn rõ.
                          </p>
                        ) : null}
                      </div>
                    ) : null}

                    {/* Prompt: xem và sửa tay trước khi tạo ảnh */}
                    <details className="group" open>
                      <summary className="flex items-center gap-2 cursor-pointer text-sm font-medium text-[var(--nq-fg)]">
                        <span className="font-mono text-[var(--nq-copper)]">▸</span>
                        Prompt tạo ảnh (EN) — sửa được nếu muốn
                      </summary>
                      <div className="mt-2">
                        <Textarea
                          value={imgGen.promptEn}
                          onChange={(e) => setImgGen((s) => ({ ...s, promptEn: e.target.value }))}
                          rows={5}
                          className="font-mono text-xs"
                          disabled={imgGen.busy}
                        />
                        <div className="mt-1 flex items-center justify-between gap-2">
                          <p className="nq-muted text-xs">{imgGen.promptVi}</p>
                          <button
                            type="button"
                            className="text-[var(--nq-dim)] hover:text-[var(--nq-copper)] text-xs font-mono uppercase shrink-0"
                            onClick={() => {
                              void navigator.clipboard.writeText(imgGen.promptEn);
                              setMsg("Đã chép prompt vào clipboard!");
                            }}
                          >
                            Copy
                          </button>
                        </div>
                      </div>
                    </details>

                    <div className="flex gap-2 pt-2 border-t border-[var(--nq-line)]">
                      <Btn
                        variant="primary"
                        onClick={() => void handleGenerateImage()}
                        busy={imgGen.busy}
                        busyLabel="Đang vẽ ảnh…"
                        disabled={Boolean(imgGen.checkError)}
                        block
                      >
                        Tạo ảnh (AI)
                      </Btn>
                      <Btn variant="ghost" onClick={handleCloseImageGen} disabled={imgGen.busy}>
                        Đóng
                      </Btn>
                    </div>

                    {imgGen.error && <Alert>{imgGen.error}</Alert>}
                  </div>
                )}

                {imgGen.step === "generating" && (
                  <div className="space-y-3 text-center py-6">
                    <div className="inline-flex items-center gap-2 text-[var(--nq-copper)] font-mono text-sm">
                      <span className="nq-spin" aria-hidden="true"></span>
                      Đang vẽ ảnh quảng cáo...
                    </div>
                    <p className="nq-muted text-xs">AI đang dựng ảnh từ prompt. Thường mất 2–10 giây.</p>
                  </div>
                )}

                {imgGen.step === "generated" && imgGen.generatedUrl && (
                  <div className="space-y-4">
                    <div className="relative max-w-sm mx-auto overflow-hidden rounded-[var(--nq-radius-bubble)] border-2 border-[var(--nq-copper)] bg-[var(--nq-surface-hi)]">
                      <img src={imgGen.generatedUrl} alt="Ảnh quảng cáo AI" className="h-full w-full object-cover" />
                      <span className="absolute inset-x-0 bottom-0 bg-[var(--nq-copper)] py-1 text-center text-xs font-bold text-black">
                        Ảnh quảng cáo AI{imgGen.chotAnh ? " — đã chốt" : ""}
                      </span>
                    </div>
                    <p className="nq-muted text-xs text-center">
                      Nguồn: {imgGen.generatedProvider || "AI"}
                      {imgGen.generatedModel ? ` · ${imgGen.generatedModel}` : ""}
                      {(() => {
                        const cur = styles.items.find((st) => st.slug === imgGen.styleSlug);
                        return cur ? ` · ${cur.ten}` : "";
                      })()}
                      {imgGen.generatedSeed !== null ? ` · seed ${imgGen.generatedSeed}` : ""}
                    </p>

                    {/* BƯỚC 4 — hỏi người dùng có muốn chỉnh thêm không, và lặp lại
                        Bước 2→3 cho tới khi họ chốt. Ảnh gốc vẫn nằm trong phiên nên
                        người dùng KHÔNG phải gửi lại ảnh. */}
                    {imgGen.adFlow ? (
                      <div className="rounded-[var(--nq-radius-bubble)] border border-[var(--nq-line)] bg-[var(--nq-surface-hi)] p-3 space-y-3">
                        {imgGen.chotAnh ? (
                          <p className="text-sm text-[var(--nq-fg)]">
                            Đã chốt ảnh. Bấm &ldquo;Lưu làm ảnh đại diện món&rdquo; để dùng ảnh này
                            cho menu — hoặc nhập ý kiến mới nếu muốn chỉnh tiếp.
                          </p>
                        ) : (
                          <p className="text-sm text-[var(--nq-fg)]">
                            Bạn có muốn chỉnh sửa thêm gì cho ảnh này không? Nhập ý kiến ở ô
                            &ldquo;Bước 4&rdquo; phía trên rồi bấm &ldquo;Áp dụng ý kiến và tạo
                            lại&rdquo; — hoặc chốt ảnh nếu đã hài lòng.
                          </p>
                        )}
                        <Btn
                          variant={imgGen.chotAnh ? "ghost" : "primary"}
                          onClick={handleChotAnh}
                          disabled={imgGen.busy || imgGen.chotAnh}
                          block
                        >
                          {imgGen.chotAnh ? "Đã chốt ảnh này" : "Không cần chỉnh gì thêm — chốt ảnh"}
                        </Btn>
                      </div>
                    ) : null}

                    <div className="flex flex-col gap-2 pt-2 border-t border-[var(--nq-line)]">
                      <Btn variant="primary" onClick={() => void handleSaveGeneratedImage()} busy={imgGen.busy} block>
                        Lưu làm ảnh đại diện món
                      </Btn>
                      <div className="flex gap-2">
                        <Btn variant="ghost" onClick={() => void handleGenerateImage()} disabled={imgGen.busy} block>
                          Tạo lại ảnh khác
                        </Btn>
                        <Btn
                          variant="ghost"
                          onClick={() => setImgGen((s) => ({ ...s, step: "prompt", generatedUrl: null }))}
                          disabled={imgGen.busy}
                          block
                        >
                          Quay lại chỉnh prompt
                        </Btn>
                      </div>
                      <Btn variant="ghost" onClick={handleCloseImageGen} disabled={imgGen.busy} block>
                        Đóng
                      </Btn>
                    </div>

                    {imgGen.error && <Alert>{imgGen.error}</Alert>}
                  </div>
                )}
              </section>
            )}

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.an} onChange={(e) => setForm({ ...form, an: e.target.checked })} />
              Ẩn món khỏi quầy (khách không đặt được)
            </label>

            <Btn type="submit" busy={busy} block>
              {isExisting ? "Cập nhật món" : "Thêm món"}
            </Btn>
          </form>
        </aside>
      </div>

      <NextSteps title="Làm gì tiếp" note="Công thức ở đây là cơ sở tính hao hụt">
        <Link href="/hao-phi" className="nq-btn nq-btn-ghost">
          Xem hao hụt theo nguyên liệu
        </Link>
        <Link href="/tieu-thu" className="nq-btn nq-btn-ghost">
          Gõ phiếu kiểm kê
        </Link>
      </NextSteps>
    </section>
  );
}
