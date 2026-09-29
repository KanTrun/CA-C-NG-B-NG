/**
 * QUÁNVERSE — điểm vào DUY NHẤT của tầng đọc dữ liệu.
 *
 * UI gọi `getQuanverseRepository(...)` rồi `.getViewModel(...)`. Nó KHÔNG bao giờ
 * `import` `real.ts` hay `mock.ts` trực tiếp — nhờ vậy đổi nguồn không phải sửa
 * một dòng nào trong component.
 */

import type { QuanverseDataSource } from "../quanverse-contract";
import { MockQuanverseRepository } from "./mock";
import { RealQuanverseRepository } from "./real";
import type { QuanverseRepository, QuanverseScenario } from "./types";

export type { QuanverseReadOptions, QuanverseRepository, QuanverseScenario } from "./types";
export { QUANVERSE_SCENARIOS, QUANVERSE_SCENARIO_LABEL } from "./types";

/**
 * Có được phép mở chế độ mô phỏng không.
 *
 * CHỈ bật ở môi trường phát triển/demo. Trên production, mô phỏng tắt hẳn để
 * không bao giờ trộn số bịa vào màn vận hành thật — kể cả khi người dùng cố
 * truyền `?nguon=mock`.
 *
 * Bật tường minh trên bản build bằng `NEXT_PUBLIC_QUANVERSE_DEMO=1` (dùng cho
 * bản trình diễn hội đồng).
 */
export function mockChoPhep(): boolean {
  if (process.env.NEXT_PUBLIC_QUANVERSE_DEMO === "1") return true;
  return process.env.NODE_ENV !== "production";
}

export interface QuanverseRepositoryOptions {
  source: QuanverseDataSource;
  scenario?: QuanverseScenario;
}

/**
 * Dựng repository theo nguồn yêu cầu, có CỔNG AN TOÀN: ở production, yêu cầu
 * `mock` bị hạ xuống `real` thay vì báo lỗi — màn hình vẫn dùng được.
 */
export function getQuanverseRepository(
  opts: QuanverseRepositoryOptions,
): QuanverseRepository {
  const wantMock = opts.source === "mock";
  if (wantMock && mockChoPhep()) {
    return new MockQuanverseRepository(opts.scenario);
  }
  return new RealQuanverseRepository();
}
