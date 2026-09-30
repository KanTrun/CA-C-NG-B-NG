/**
 * QUÁNVERSE — hợp đồng của TẦNG ĐỌC DỮ LIỆU (repository).
 *
 * UI chỉ biết `QuanverseRepository`. Nó không biết dữ liệu đến từ API thật hay
 * từ fixture mô phỏng, và không bao giờ `import` một adapter cụ thể.
 */

import type {
  QuanverseAskResult,
  QuanverseDataSource,
  QuanverseModesState,
  QuanverseRole,
  QuanverseScenario,
  QuanverseViewModel,
} from "../quanverse-contract";

/** Kịch bản mô phỏng — nguồn chân lý ở hợp đồng, re-export cho tầng đọc. */
export type { QuanverseScenario } from "../quanverse-contract";

export const QUANVERSE_SCENARIOS: readonly QuanverseScenario[] = [
  "binh_thuong",
  "cao_diem",
  "qua_tai_pha",
];

export const QUANVERSE_SCENARIO_LABEL: Record<QuanverseScenario, string> = {
  binh_thuong: "Ca thường",
  cao_diem: "Giờ cao điểm",
  qua_tai_pha: "Quầy pha quá tải",
};

/** Nhãn đọc được cho mã mode backend. */
export const QUANVERSE_MODE_LABEL: Record<string, string> = {
  gio_cao_diem: "Giờ cao điểm",
  troi_mua: "Trời mưa",
  khach_doan: "Khách đoàn",
  thieu_nhan_su: "Thiếu nhân sự",
  quan_yen_tinh: "Quán yên tĩnh",
  dem_nhac: "Đêm nhạc",
};

export interface QuanverseReadOptions {
  role: QuanverseRole;
  /** Chỉ dùng ở chế độ mô phỏng. */
  scenario?: QuanverseScenario;
}

export interface QuanverseAskOptions {
  question: string;
  page?: "living_map";
}

export interface QuanverseRepository {
  readonly dataSource: QuanverseDataSource;
  getViewModel(opts: QuanverseReadOptions): Promise<QuanverseViewModel>;
  /** Hỏi AI grounded — không ghi DB. */
  askQuestion(opts: QuanverseAskOptions): Promise<QuanverseAskResult>;
  /** Đọc trạng thái cafe modes. */
  listModes(): Promise<QuanverseModesState>;
  /** Đề xuất bật mode (chưa kích hoạt). */
  proposeMode(mode: string): Promise<QuanverseModesState>;
  /** Xác nhận mode đã đề xuất (manager). */
  confirmMode(mode: string): Promise<QuanverseModesState>;
  /** Tắt mode đang bật (manager). */
  deactivateMode(mode: string): Promise<QuanverseModesState>;
}
