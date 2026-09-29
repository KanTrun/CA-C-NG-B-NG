/**
 * QUÁNVERSE — hợp đồng của TẦNG ĐỌC DỮ LIỆU (repository).
 *
 * UI chỉ biết `QuanverseRepository`. Nó không biết dữ liệu đến từ API thật hay
 * từ fixture mô phỏng, và không bao giờ `import` một adapter cụ thể.
 */

import type {
  QuanverseDataSource,
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

export interface QuanverseReadOptions {
  role: QuanverseRole;
  /** Chỉ dùng ở chế độ mô phỏng. */
  scenario?: QuanverseScenario;
}

export interface QuanverseRepository {
  readonly dataSource: QuanverseDataSource;
  getViewModel(opts: QuanverseReadOptions): Promise<QuanverseViewModel>;
}
