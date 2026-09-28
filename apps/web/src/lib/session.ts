export type Role = "quan_ly" | "chu_quan" | "nhan_vien" | string;

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("nq_token") || localStorage.getItem("nq_token") || "";
}

export function getRole(): Role {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("nq_role") || localStorage.getItem("nq_role") || "";
}

export function getName(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("nq_name") || localStorage.getItem("nq_name") || "";
}

export function setSession(token: string, role: string, name: string, nvId: string): void {
  try {
    sessionStorage.setItem("nq_token", token);
    sessionStorage.setItem("nq_role", role);
    sessionStorage.setItem("nq_name", name);
    sessionStorage.setItem("nq_nv", nvId);
  } catch {}
  try {
    // Token chỉ sống trong sessionStorage (không sống qua tab, không đọng trên đĩa).
    // role/name/nv vẫn ghi localStorage để UX khôi phục sau khi đăng nhập lại.
    localStorage.setItem("nq_role", role);
    localStorage.setItem("nq_name", name);
    localStorage.setItem("nq_nv", nvId);
  } catch {}
}

export function getNvId(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("nq_nv") || localStorage.getItem("nq_nv") || "";
}

export function isManager(role = getRole()): boolean {
  return role === "quan_ly" || role === "chu_quan";
}

export function isChuQuan(role = getRole()): boolean {
  return role === "chu_quan";
}

export function canEdit(role = getRole()): boolean {
  return isManager(role);
}

const STAFF_ACCESS = new Set([
  "/",
  "/hom-nay",
  "/cuoc-hop",
  "/quay",
  "/pha",
  "/phieu",
  "/toi",
  "/treo",
  "/doi-ca",
  "/handover",
  "/hao-phi",
  "/tieu-thu",
  "/cong-bang",
  "/sop",
  "/tkb",
  "/qr",
  "/cam-nang",
  "/copilot",
  "/them",
  "/contracts",
  "/chat",
  // Thư viện Kỹ năng đã kiểm định — API `/api/v1/skills` công khai (🟢), mọi vai xem được.
  "/skills",
  // Grand AI Experience — HỒN QUÁN Spatial Memory + Living Map mở cho mọi vai trò
  "/quanverse",
  "/quanverse/spatial-memory",
]);
const MANAGER_ONLY = new Set([
  "/lich-tuan",
  "/roster",
  "/inbox",
  "/page-quan",
  "/page-quan/fb-inbox",
  "/ai-learning",
  // Quản lý hộp thư Gmail (OAuth, nhãn, bộ lọc, gửi) — README ghi Quản lý/chủ quán.
  "/gmail",
  // Cấu hình quán & hướng dẫn AI — kv store_profile, API đòi `_require_manager`.
  "/cau-hinh-quan",
  // Mỗi lượt khảo sát tốn chi phí proxy + Vision thật, nên khớp với `_require_manager`
  // ở `apps/api/src/ca_api/interfaces/http/pricing_radar.py`.
  "/khao-sat-gia",
  "/vet",
  // Hệ sinh thái AI agent (Self-Explaining, Predictive Playbook, Digital Twin)
  "/giai-thich",
  "/de-xuat-thong-minh",
  "/thu-nghiem-an-toan",
  // Grand AI Experience Portfolio — War Room / Shift Rescue / luật là manager-only
  "/quanverse/war-room",
  "/quanverse/shift-rescue",
  "/quanverse/rules",
]);
const OWNER_ONLY = new Set(["/menu", "/nguoi"]);

/**
 * Mọi đường dẫn HỢP LỆ của app (khớp `GROUPS` trong `AppShell.tsx` + route
 * ngoài sidebar). Dùng để phân biệt "bị chặn quyền" với "không có trang này":
 * trước đây gõ sai URL vẫn hiện "Không đủ quyền truy cập" — thông báo sai làm
 * người dùng tưởng mình bị khoá quyền trong khi thật ra trang không tồn tại.
 */
const KNOWN_PATHS = new Set<string>([
  "/",
  "/login",
  "/dang-ky",
  "/hom-nay",
  "/quay",
  "/pha",
  "/phieu",
  "/treo",
  "/cuoc-hop",
  "/handover",
  "/chat",
  "/lich-tuan",
  "/roster",
  "/toi",
  "/doi-ca",
  "/qr",
  "/cong-bang",
  "/tkb",
  "/nguoi",
  "/copilot",
  "/sop",
  "/cam-nang",
  "/skills",
  "/ai-learning",
  "/de-xuat-thong-minh",
  "/giai-thich",
  "/thu-nghiem-an-toan",
  "/inbox",
  "/quanverse",
  "/quanverse/war-room",
  "/quanverse/shift-rescue",
  "/quanverse/rules",
  "/quanverse/spatial-memory",
  "/menu",
  "/tieu-thu",
  "/hao-phi",
  "/khao-sat-gia",
  "/page-quan",
  "/page-quan/fb-inbox",
  "/page-quan/dat-ban",
  "/gmail",
  "/cau-hinh-quan",
  "/vet",
  "/contracts",
  "/huong-dan",
  "/them",
]);

/** Trang có tồn tại trong app không (bỏ qua phần đuôi con của /quanverse). */
export function isKnownPath(path: string): boolean {
  if (KNOWN_PATHS.has(path)) return true;
  // `/quanverse/tour/<id>` là route con hợp lệ.
  return path.startsWith("/quanverse/tour/");
}

/** Client-side gate for navigation and hand-typed URLs. API remains authoritative. */
export function canAccess(role: Role, path: string): boolean {
  if (OWNER_ONLY.has(path)) return role === "chu_quan";
  if (path.startsWith("/page-quan")) return isManager(role);
  if (MANAGER_ONLY.has(path)) return isManager(role);
  return STAFF_ACCESS.has(path) && Boolean(role);
}

export function clearSession(): void {
  try {
    sessionStorage.removeItem("nq_token");
    sessionStorage.removeItem("nq_role");
    sessionStorage.removeItem("nq_name");
    sessionStorage.removeItem("nq_nv");
  } catch {}
  try {
    localStorage.removeItem("nq_token");
    localStorage.removeItem("nq_role");
    localStorage.removeItem("nq_name");
    localStorage.removeItem("nq_nv");
  } catch {}
}

export function roleLabel(role: string): string {
  if (role === "quan_ly") return "Quản lý";
  if (role === "chu_quan") return "Chủ quán";
  if (role === "nhan_vien") return "Nhân viên";
  return role || "Chưa đăng nhập";
}

export function lifeLabel(state: string): string {
  const map: Record<string, string> = {
    may_sinh: "Tự sinh — chờ rà soát",
    nhap: "Nháp",
    dang_giai: "Đang giải",
    cho_duyet: "Chờ duyệt",
    da_duyet: "Đã duyệt",
    da_cong_bo: "Đã công bố",
    da_dong: "Đã đóng",
  };
  return map[state] ?? state.replace(/_/g, " ");
}
