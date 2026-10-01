"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiGet } from "../lib/api";
import { canAccess, clearSession, getName, getToken, isKnownPath, roleLabel } from "../lib/session";
import { CommandPalette, flattenNavGroups } from "../ui/CommandPalette";
import { Logo } from "../ui/Logo";
import { CopilotPane } from "../ui/copilot/CopilotPane";
import { Icon, iconForHref } from "../ui/icons";
import { Tour } from "../ui/tour";

const COLLAPSE_KEY = "nq_side_collapsed";
/** Khoá lưu nhóm nào đang mở. Giá trị là JSON map `{ [groupId]: true }`. */
const GROUPS_KEY = "nq_side_groups";

/**
 * Một mục điều hướng.
 *
 * `group` chỉ dùng để đánh dấu mục thuộc "Trải nghiệm AI" — chúng vẫn nằm trong
 * nhóm logic của mình (AI & tự động hoá), chỉ thêm một chấm accent để người
 * dùng quen với cách phân vùng cũ còn nhận ra.
 */
type LinkItem = { href: string; label: string; badge?: string };

type NavGroup = { id: string; title: string; items: LinkItem[] };

/**
 * Bốn nhóm theo CÁCH DÙNG, không theo thứ tự chữ cái.
 *
 * Nhóm là thứ người vận hành nhớ được: "việc mình làm hằng ngày" khác "việc
 * lịch và nhân sự" khác "phần máy tự làm". Nhãn nhóm viết như việc, không viết
 * như danh mục kỹ thuật — không có nhóm nào tên "Cấu hình" chứa lẫn lộn menu,
 * người dùng và hợp đồng dữ liệu.
 */
const GROUPS: NavGroup[] = [
  {
    id: "van-hanh",
    title: "Vận hành hằng ngày",
    items: [
      { href: "/hom-nay", label: "Hôm nay" },
      { href: "/quay", label: "Ghi đơn quầy" },
      { href: "/pha", label: "Pha chế" },
      { href: "/phieu", label: "Phiếu trong ca" },
      { href: "/treo", label: "Việc treo" },
      { href: "/cuoc-hop", label: "Họp & giao ca" },
      { href: "/handover", label: "Bàn giao ca" },
      { href: "/chat", label: "Trao đổi nội bộ" },
    ],
  },
  {
    id: "lich-nhan-su",
    title: "Lịch & nhân sự",
    items: [
      { href: "/lich-tuan", label: "Lịch tuần" },
      { href: "/toi", label: "Ca của tôi" },
      { href: "/doi-ca", label: "Chợ đổi ca" },
      { href: "/qr", label: "Điểm danh QR" },
      { href: "/cong-bang", label: "Công bằng ca" },
      { href: "/tkb", label: "Lịch bận (ảnh)" },
      { href: "/nguoi", label: "Người dùng" },
    ],
  },
  {
    id: "ai-tu-dong-hoa",
    title: "AI & tự động hoá",
    items: [
      { href: "/copilot", label: "Trợ lý điều hành" },
      { href: "/sop", label: "Hỏi quy trình" },
      { href: "/cam-nang", label: "Cẩm nang quán" },
      { href: "/skills", label: "Năng lực Trợ lý AI" },
      { href: "/ai-learning", label: "Học từ phản hồi" },
      { href: "/de-xuat-thong-minh", label: "Đề xuất thông minh" },
      { href: "/giai-thich", label: "Hệ thống tự giải thích" },
      { href: "/thu-nghiem-an-toan", label: "Thử nghiệm an toàn" },
      { href: "/inbox", label: "Hộp thư ràng buộc" },
      { href: "/quanverse", label: "Quánverse · Trung tâm điều hành" },
    ],
  },
  {
    id: "hang-hoa-chung-tu",
    title: "Hàng hoá & chứng từ",
    items: [
      { href: "/menu", label: "Menu & giá" },
      { href: "/tieu-thu", label: "Sổ tiêu thụ" },
      { href: "/hao-phi", label: "Hao phí" },
      { href: "/khao-sat-gia", label: "Khảo sát giá" },
      { href: "/page-quan", label: "Page quán" },
      { href: "/page-quan/fb-inbox", label: "Bình luận & Inbox duyệt" },
      { href: "/page-quan/dat-ban", label: "Sơ đồ & đặt bàn" },
      { href: "/gmail", label: "Quản lý Gmail" },
      { href: "/cau-hinh-quan", label: "Cấu hình quán & AI" },
    ],
  },
  {
    id: "he-thong",
    title: "Hệ thống",
    items: [
      { href: "/vet", label: "Vết hệ thống" },
      { href: "/contracts", label: "Hợp đồng dữ liệu" },
      { href: "/huong-dan", label: "Bản đồ hệ thống" },
      { href: "/them", label: "Tất cả lối vào" },
    ],
  },
];

const COPILOT_LAUNCHER_ROUTES = new Set([
  "/lich-tuan",
  "/roster",
  "/qr",
  "/phieu",
  "/treo",
  "/cong-bang",
  "/tkb",
  "/handover",
  "/doi-ca",
  "/cam-nang",
]);

/** `data-tour` để tour hướng dẫn trỏ vào đúng lối vào của từng việc. */
function tourId(href: string): string {
  return `nav-${href.replace(/^\//, "")}`;
}

export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [token, setToken] = useState("");
  /** Thu gọn sidebar. Mặc định mở: người mới cần thấy hết lối vào trước khi
   *  tự quyết định thu gọn. Lưu vào localStorage để giữ nguyên giữa các trang —
   *  sidebar tự thu lại sau mỗi lần điều hướng thì không ai dùng. */
  const [collapsed, setCollapsed] = useState(false);
  /** Sidebar trượt ra ở màn hẹp. Tách khỏi `collapsed` vì hai trạng thái này
   *  độc lập: màn rộng thu gọn còn icon, màn hẹp đóng hẳn. */
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  /** Nhóm nào đang mở. `null` = chưa đọc localStorage (lần đầu). */
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean> | null>(null);
  const burgerRef = useRef<HTMLButtonElement>(null);
  const sideRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let cancelled = false;
    const storedToken = getToken();
    const storedName = getName();
    setToken(storedToken);
    setName(storedName);
    setReady(false);

    if (!storedToken) {
      setRole("");
      setReady(true);
      return () => {
        cancelled = true;
      };
    }

    apiGet<{ role: string; nv_id: string }>("/api/v1/me")
      .then((me) => {
        if (cancelled) return;
        // Quyền từ máy chủ là nguồn sự thật. Không dùng vai trò cũ trong
        // localStorage để mở một trang quản trị.
        setRole(me.role);
        sessionStorage.setItem("nq_role", me.role);
        sessionStorage.setItem("nq_nv", me.nv_id);
        localStorage.setItem("nq_role", me.role);
        localStorage.setItem("nq_nv", me.nv_id);
      })
      .catch(() => {
        // Không xác minh được thì đóng quyền, không tin dữ liệu vai trò cũ.
        if (!cancelled) setRole("__unverified__");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [path]);

  /** Đọc trạng thái thu gọn SAU khi gắn, không trong `useState` khởi tạo:
   *  đọc localStorage lúc render đầu làm HTML máy chủ và HTML máy khách khác
   *  nhau → React báo hydration mismatch và giao diện nhảy một nhịp. */
  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* Chế độ riêng tư chặn localStorage — dùng mặc định, không sập trang. */
    }
  }, []);

  /** Đọc trạng thái mở/đóng nhóm SAU khi gắn — cùng lý do với `collapsed`:
   *  đọc localStorage lúc render đầu làm HTML máy chủ và máy khách lệch nhau. */
  useEffect(() => {
    let stored: Record<string, boolean> | null = null;
    try {
      const raw = localStorage.getItem(GROUPS_KEY);
      if (raw) {
        const parsed: unknown = JSON.parse(raw);
        if (parsed && typeof parsed === "object") stored = parsed as Record<string, boolean>;
      }
    } catch {
      /* JSON hỏng hoặc localStorage bị chặn — rơi về mặc định bên dưới. */
    }
    setExpandedGroups((current) => current ?? stored ?? {});
  }, []);

  /** Nhóm chứa trang đang xem — mặc định MỞ để mục đang dùng không bị giấu sau
   *  một tiêu đề đóng. Fallback về nhóm đầu khi không nhóm nào khớp. */
  const activeGroupId = useMemo(() => {
    const hit = GROUPS.find((g) => g.items.some((l) => l.href === path));
    return hit?.id ?? GROUPS[0]?.id ?? "";
  }, [path]);

  /** Nhóm CHƯA từng được người dùng bấm thì mở sẵn: nhóm đang xem và nhóm đầu.
   *  `null` = chưa đọc localStorage (SSR + render đầu), cũng coi như mở hết để
   *  lần vẽ đầu tiên có đủ lối vào và các cổng e2e tìm thấy link ngay. */
  const defaultOpen = useCallback(
    (id: string) => id === activeGroupId || id === GROUPS[0]?.id,
    [activeGroupId],
  );

  /** Nhóm có đang mở không. Trạng thái người dùng đã chọn LUÔN thắng mặc định —
   *  kể cả nhóm đang xem: bấm thu nhóm chứa trang hiện tại vẫn phải thu được,
   *  nếu không thì nút tiêu đề nhóm thành nút chết. */
  const isGroupOpen = useCallback(
    (id: string) => {
      if (expandedGroups) return expandedGroups[id] ?? defaultOpen(id);
      return true;
    },
    [expandedGroups, defaultOpen],
  );

  const toggleGroup = useCallback(
    (id: string) => {
      setExpandedGroups((current) => {
        const openNow = current ? (current[id] ?? defaultOpen(id)) : true;
        const next = { ...(current ?? {}), [id]: !openNow };
        try {
          localStorage.setItem(GROUPS_KEY, JSON.stringify(next));
        } catch {
          /* Không lưu được thì thôi; trạng thái vẫn đúng trong phiên này. */
        }
        return next;
      });
    },
    [defaultOpen],
  );

  /** Đóng drawer mỗi khi đổi trang: người dùng vừa chọn xong một mục, giữ
   *  drawer mở nghĩa là nội dung mới bị che ngay sau cú bấm. */
  useEffect(() => {
    setDrawerOpen(false);
  }, [path]);

  /** Đóng drawer bằng Escape, và chặn cuộn nền khi drawer đang mở. */
  useEffect(() => {
    if (!drawerOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setDrawerOpen(false);
        burgerRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [drawerOpen]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((v) => {
      const next = !v;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* Không lưu được thì thôi; trạng thái vẫn đúng trong phiên này. */
      }
      return next;
    });
  }, []);

  const hideFloatingCopilot =
    path === "/copilot" ||
    path === "/chat" ||
    path.startsWith("/quanverse") ||
    COPILOT_LAUNCHER_ROUTES.has(path);

  function logout() {
    clearSession();
    router.push("/login");
  }

  return (
    <div
      className="nq-app min-h-screen font-sans"
      data-collapsed={collapsed ? "1" : "0"}
    >
      <CommandPalette
        open={cmdOpen}
        onClose={() => setCmdOpen(false)}
        items={flattenNavGroups(GROUPS)}
        role={role || null}
      />
      {/* Nút mở sidebar — chỉ hiện ở màn hẹp (điều khiển bằng CSS). */}
      <button
        ref={burgerRef}
        type="button"
        className="nq-side__burger"
        onClick={() => setDrawerOpen(true)}
        aria-label="Mở điều hướng"
        aria-expanded={drawerOpen}
        aria-controls="nq-side"
      >
        <Icon name="menu" size={20} />
      </button>

      {/* Màn chắn: chỉ hiện ở màn hẹp khi drawer mở. Là <button> để bấm được
          bằng bàn phím và công cụ hỗ trợ, không phải <div onClick>. */}
      <button
        type="button"
        className="nq-side__scrim"
        data-shown={drawerOpen ? "1" : "0"}
        aria-label="Đóng điều hướng"
        tabIndex={drawerOpen ? 0 : -1}
        onClick={() => setDrawerOpen(false)}
      />

      <aside
        id="nq-side"
        ref={sideRef}
        className="nq-side"
        data-collapsed={collapsed ? "1" : "0"}
        data-open={drawerOpen ? "1" : "0"}
        aria-label="Điều hướng chính"
      >
        <div className="nq-side__head">
          <Logo href={token ? "/hom-nay" : "/"} />
          <button
            type="button"
            className="nq-side__toggle"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Mở rộng điều hướng" : "Thu gọn điều hướng"}
            aria-pressed={collapsed}
            title={collapsed ? "Mở rộng" : "Thu gọn"}
          >
            <Icon name={collapsed ? "arrow-right" : "arrow-left"} size={18} />
          </button>
        </div>

        <nav className="nq-side__scroll" aria-label="Các khu vực">
          {GROUPS.map((g) => {
            // Lọc theo quyền TRƯỚC khi vẽ: một nhóm rỗng không được để lại
            // tiêu đề trơ trọi — người dùng đọc tiêu đề nhóm rồi mới biết ruột
            // trống là tín hiệu sai về hệ thống.
            const allowed = g.items.filter((x) => canAccess(role, x.href));
            if (!allowed.length) return null;
            const open = isGroupOpen(g.id);
            const panelId = `nq-side-grp-${g.id}`;
            return (
              <Fragment key={g.id}>
                {/* Tiêu đề nhóm là NÚT: bấm để mở/thu nhóm đó. Nhóm chứa trang
                    đang xem luôn mở (xem `isGroupOpen`) nên mục đang dùng không
                    bao giờ bị giấu. */}
                <button
                  type="button"
                  className="nq-side__group-btn"
                  data-open={open ? "1" : "0"}
                  onClick={() => toggleGroup(g.id)}
                  aria-expanded={open}
                  aria-controls={panelId}
                  title={collapsed ? g.title : undefined}
                >
                  <span className="nq-side__group-label">{g.title}</span>
                  <Icon name="chevron-down" size={14} className="nq-side__group-chevron" />
                </button>
                <div className="nq-side__group-items" id={panelId} hidden={!open}>
                  {allowed.map((l) => {
                    const on = path === l.href;
                    const exp = l.href.startsWith("/quanverse");
                    return (
                      <Link
                        key={l.href}
                        href={l.href}
                        className="nq-side__link"
                        data-tour={tourId(l.href)}
                        aria-current={on ? "page" : undefined}
                        /* `title` cho chế độ thu gọn: nhãn bị ẩn bằng CSS nhưng
                           vẫn nằm trong DOM nên trình đọc màn hình đọc được;
                           title phục vụ người dùng chuột khi chỉ thấy icon. */
                        title={collapsed ? l.label : undefined}
                      >
                        <Icon name={exp ? "cube" : iconForHref(l.href)} size={18} />
                        <span className="nq-side__label">{l.label}</span>
                        {exp ? <span className="nq-side__dot" aria-hidden="true" /> : null}
                      </Link>
                    );
                  })}
                </div>
              </Fragment>
            );
          })}
        </nav>

        <div className="nq-side__foot">
          {ready && token ? (
            <>
              <div className="nq-side__user">
                <Icon name="user" size={16} />
                <span className="nq-side__user-name">
                  {name}{" "}
                  <span className="nq-side__user-role">[{roleLabel(role)}]</span>
                </span>
              </div>
              <button
                type="button"
                onClick={logout}
                className="nq-cta nq-cta--ghost nq-cta--sm nq-side__logout"
                title="Thoát"
                aria-label="Thoát"
              >
                <Icon name="door" size={16} />
                <span className="nq-side__label">Thoát</span>
              </button>
              <button
                type="button"
                className="nq-side__cmd"
                onClick={() => setCmdOpen(true)}
                title="Tìm trang nhanh (Ctrl+K)"
              >
                <Icon name="filter" size={14} />
                <span className="nq-side__label">Tìm nhanh</span>
                <kbd className="nq-side__kbd">Ctrl+K</kbd>
              </button>
            </>
          ) : (
            <Link href="/login" className="nq-cta nq-cta--primary nq-cta--sm">
              Đăng nhập
            </Link>
          )}
        </div>
      </aside>

      {/* KHÔNG đặt `mx-auto` ở đây: `margin-left` đã do `.nq-main` khai để
          nhường chỗ sidebar, mà `mx-auto` ghi `margin-right: auto` — cặp
          `margin-left: 258px` + `margin-right: auto` trên phần tử rộng 100%
          đẩy nội dung vượt 258px khỏi màn hình (đo được `scrollWidth 1698`
          trên khung 1440). Việc canh giữa nội dung do khối bên trong lo, còn
          vùng `main` chỉ cần chừa lề trái cho sidebar. */}
      <main className="nq-main" id="nq-content">
        <div className="nq-main__inner">
          {!ready ? (
            <div className="nq-page nq-page--center py-16 text-center" role="status">
              <p className="nq-muted" style={{ margin: 0 }}>Đang kiểm tra quyền truy cập…</p>
            </div>
          ) : token && role && !isKnownPath(path) ? (
            /* Gõ sai URL phải nói ĐÚNG là không có trang, không được đổ cho
               phân quyền — trước đây hai trường hợp dùng chung một thông báo
               "Không đủ quyền truy cập" nên người dùng tưởng bị khoá quyền. */
            <div className="nq-page nq-page--center py-16 text-center">
              <h1 className="nq-gate-title">Không tìm thấy trang</h1>
              <p className="nq-muted mx-auto" style={{ margin: "var(--nq-s3) auto 0", maxWidth: "46ch" }}>
                Đường dẫn <code>{path}</code> không tồn tại trong hệ thống. Kiểm tra lại địa chỉ,
                hoặc mở «Bản đồ hệ thống» ở menu để tìm đúng mục.
              </p>
              <p style={{ marginTop: "var(--nq-s4)" }}>
                <a href="/huong-dan" className="nq-btn nq-btn-ghost">
                  Mở bản đồ hệ thống
                </a>
              </p>
            </div>
          ) : token && role && !canAccess(role, path) ? (
            <div className="nq-page nq-page--center py-16 text-center">
              <h1 className="nq-gate-title">Không đủ quyền truy cập</h1>
              <p className="nq-muted mx-auto" style={{ margin: "var(--nq-s3) auto 0", maxWidth: "46ch" }}>
                {path === "/vet"
                  ? "Bạn không được uỷ quyền để xem vết hệ thống. Chỉ Quản lý và Chủ quán được phép truy cập."
                  : "Tài khoản hiện tại không có quyền truy cập trang này."}
              </p>
            </div>
          ) : (
            children
          )}
        </div>
      </main>

      {token && !hideFloatingCopilot ? <CopilotPane /> : null}
      <Tour active={Boolean(token) && path === "/hom-nay"} />
    </div>
  );
}
