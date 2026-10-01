"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { viError } from "../../lib/present";
import { getToken, isManager } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  Empty,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  ProgressBar,
  TechnicalDrawer,
  Textarea,
  Toasts,
  useToasts,
} from "../../ui/kit";
import { Icon } from "../../ui/icons";

type Status = {
  connected: boolean;
  page_name?: string;
  follower_count?: number;
  unread_thread_count?: number;
  unreviewed_draft_count?: number;
};

type Thread = {
  id: string;
  psid?: string;
  from?: string;
  customer_name?: string;
  status?: string;
  unread?: boolean;
  last_message?: string;
  sender_name: string;
  sender_avatar?: string;
  last_message_at?: string;
  last_message_ts?: number;
  is_within_24h?: boolean;
  needs_action?: boolean;
  pending_approval?: boolean;
  tom_tat?: string;
  intent?: string;
  suggested_reply?: string;
  customer_profile?: {
    ten_khach?: string;
    visit_count?: number;
    is_vip_or_regular?: boolean;
    favorite_drinks?: string[];
    special_notes?: string[];
  };
  replies?: Array<{
    id: string;
    text: string;
    by: string;
    at?: string;
    mock?: boolean;
  }>;
};

type Draft = {
  id: string;
  noi_dung: string;
  ngay_tao: string;
  nguoi_tao: string;
  trang_thai: "cho_duyet" | "da_duyet" | "tu_choi";
};

type StoreProfile = {
  ten_quan: string;
  slogan?: string;
  dia_chi: string;
  dia_chi_chi_tiet?: string;
  phuong_xa?: string;
  phuong_xa_code?: string;
  quan_huyen?: string;
  quan_huyen_code?: string;
  tinh?: string;
  tinh_code?: string;
  thanh_pho?: string;
  toa_do_lat?: string;
  toa_do_lon?: string;
  google_maps_url?: string;
  lat?: number | null;
  lon?: number | null;
  hotline: string;
  hotline_phu?: string;
  email?: string;
  website?: string;
  fanpage_url?: string;
  gio_mo_cua: string;
  gio_mo_cua_chi_tiet?: string;
  khoang_gia?: string;
  tien_ich?: string;
  wifi_ssid?: string;
  wifi_pass?: string;
  ngan_hang?: string;
  stk_ngan_hang?: string;
  chu_tai_khoan?: string;
  mo_ta?: string;
  chinh_sach_dat_ban?: string;
  huong_dan_agent?: string;
};

type Promotion = {
  id?: string;
  tieu_de: string;
  chi_tiet: string;
  hieu_luc: string;
};

type ApifyUsage = {
  has_token: boolean;
  username?: string;
  plan: string;
  plan_id?: string | null;
  monthly_limit_usd: number | null;
  usage_usd: number | null;
  remaining_usd: number | null;
  usage_percent: number | null;
  status_label: string;
  usage_measured: boolean;
  usage_source?: string;
  usage_cycle_end_at?: string | null;
  cu_limit?: number | null;
  cu_used?: number | null;
  active_actors: string[];
  note?: string;
  cached?: boolean;
  quota_exhausted?: boolean;
};

type TrendItem = {
  id: string;
  tieu_de: string;
  cum_tu_khoa_viral: string;
  nguon_goc: string;
  loai_xu_huong: string;
  danh_muc: string;
  vong_doi: string;
  diem_nhan_dac_biet: string;
  nguon_goc_chi_tiet: string;
  ngu_canh_su_dung: string;
  tam_ly_gioi_tre: string;
  toc_do_tang_truong_24h: number;
  diem_tiem_nang_viral: number;
  du_bao_thoi_gian: string;
  link_goc?: string;
  tiktok_url?: string;
  tiktok_tag_url?: string;
  thoi_gian_cao?: string;
  luot_tiep_can?: string;
  is_live_scraped?: boolean;
  trich_doan_noi_dung_that?: string;
  binh_luan_that_tiktok?: string[];
  nen_tang_lan_toa: string[];
  tu_khoa_hashtag: string[];
};

export default function PageQuanPage() {
  const [token, setToken] = useState("");
  const [manager, setManager] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [draftText, setDraftText] = useState("");
  const [replyDraft, setReplyDraft] = useState<Record<string, string>>({});
  const [aiTopic, setAiTopic] = useState("");
  const [aiTone, setAiTone] = useState("than thien");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [tab, setTab] = useState<"threads" | "drafts" | "trends" | "saved_trends" | "config" | "reflection">("trends");
  const [profile, setProfile] = useState<StoreProfile | null>(null);
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [reflectionReport, setReflectionReport] = useState<any | null>(null);
  const [reflectionLoading, setReflectionLoading] = useState(false);

  // Trend Intelligence State
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [regionFilter, setRegionFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [selectedTrend, setSelectedTrend] = useState<TrendItem | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [scanStatusText, setScanStatusText] = useState("");

  // Apify Usage & Scraping Mode State
  const [apifyUsage, setApifyUsage] = useState<ApifyUsage | null>(null);
  const [usageRefreshing, setUsageRefreshing] = useState(false);
  const [scrapeMode, setScrapeMode] = useState<"auto" | "direct_only" | "apify_force" | "browser">("auto");

  // Keyword / Topic Filter State (Chức năng 1)
  const [keywordInput, setKeywordInput] = useState("");
  const [activeKeyword, setActiveKeyword] = useState("");

  // Bookmark / Saved Trends State (Chức năng 3)
  const [savedTrends, setSavedTrends] = useState<TrendItem[]>([]);
  const [showSavedOnly, setShowSavedOnly] = useState(false);

  // Auto-Scan State (Chức năng 4)
  const [autoScanEnabled, setAutoScanEnabled] = useState(false);
  const [scanIntervalMinutes, setScanIntervalMinutes] = useState(30);
  const [customMinutesInput, setCustomMinutesInput] = useState("30");
  const [countdownSeconds, setCountdownSeconds] = useState(30 * 60);

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { toasts, push, dismiss } = useToasts();

  // Hội thoại Messenger: hội thoại đang chọn & bộ lọc
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [threadFilter, setThreadFilter] = useState<"all" | "needs_action" | "within_24h">("all");
  const [sendingReplyId, setSendingReplyId] = useState<string | null>(null);

  // Load Saved Trends from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem("nhp_saved_trends_v2");
      if (stored) {
        setSavedTrends(JSON.parse(stored));
      }
    } catch {
      // Ignore localstorage errors
    }
  }, []);

  const toggleSaveTrend = (item: TrendItem, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setSavedTrends((prev) => {
      const exists = prev.some((t) => t.id === item.id);
      let updated: TrendItem[];
      if (exists) {
        updated = prev.filter((t) => t.id !== item.id);
        push(`Đã bỏ lưu xu hướng "${item.cum_tu_khoa_viral}"`);
      } else {
        updated = [item, ...prev];
        push(`Đã lưu xu hướng "${item.cum_tu_khoa_viral}" vào kế hoạch quán!`);
      }
      try {
        localStorage.setItem("nhp_saved_trends_v2", JSON.stringify(updated));
      } catch {
        // Ignore
      }
      return updated;
    });
  };

  useEffect(() => {
    setToken(getToken());
    setManager(isManager());
    if (!getToken()) setLoading(false);
  }, []);

  // Fetch Trends function (Quét xong 100% mới cập nhật 1 lượt)
  const fetchTrendsData = useCallback(
    async (region: string, category: string, kw: string, mode?: "auto" | "direct_only" | "apify_force" | "browser", showToast = false) => {
      setIsScanning(true);
      const effectiveMode = mode || scrapeMode;
      const sourceName =
        region === "tiktok_vn"
          ? "TikTok Việt Nam"
          : region === "threads_vn"
          ? "Meta Threads"
          : region === "google_vn"
          ? "Google Trends VN"
          : region === "star_vn"
          ? "Showbiz & KOLs"
          : region === "tiktok_global"
          ? "Quốc tế (Global)"
          : "Tất cả nguồn";
      const modeLabel =
        effectiveMode === "direct_only"
          ? "100% Miễn phí"
          : effectiveMode === "apify_force"
          ? "Ép dùng Apify"
          : effectiveMode === "browser"
          ? "Camoufox Browser"
          : "Tự động";

      setScanStatusText(
        kw.trim()
          ? `Đang quét chuyên sâu chủ đề "${kw.trim()}" từ ${sourceName} (${modeLabel})...`
          : `Đang cào dữ liệu độc quyền thời gian thực từ ${sourceName}...`
      );

      try {
        const queryParams = new URLSearchParams({
          region,
          category,
          keyword: kw.trim(),
          mode: effectiveMode,
        });
        const res = await apiGet<{ trends: TrendItem[]; total: number }>(`/api/v1/trends/radar?${queryParams.toString()}`);
        const freshTrends = res.trends ?? [];
        
        // Quét xong hết mới nạp dữ liệu lên 1 lượt
        setTrends(freshTrends);
        if (freshTrends.length > 0) {
          setSelectedTrend((curr) => {
            const stillExists = freshTrends.find((t) => t.id === curr?.id);
            return stillExists || freshTrends[0];
          });
        } else {
          setSelectedTrend(null);
        }
        setError(null);
        if (freshTrends.length > 0) {
          setScanStatusText(`Quét hoàn tất: Đã nạp ${freshTrends.length} xu hướng thật!`);
        } else if (effectiveMode === "browser") {
          setScanStatusText(
            "Browser thật không trả kết quả — kiểm tra server đã cài Camoufox (camoufox fetch) chưa, hoặc nguồn đang chặn."
          );
        } else {
          setScanStatusText("Quét hoàn tất: Đã nạp 0 xu hướng — thử nguồn hoặc từ khóa khác.");
        }
        if (showToast) {
          push(`Đã cào thành công ${freshTrends.length} xu hướng từ ${sourceName}!`);
        }
      } catch (e) {
        setError(viError(e, { doing: "cào dữ liệu xu hướng" }));
        setScanStatusText("Lỗi khi cào dữ liệu. Vui lòng thử lại.");
      } finally {
        setIsScanning(false);
      }
    },
    [scrapeMode, push]
  );

  const load = useCallback(() => {
    if (!getToken()) return;
    setLoading(true);
    Promise.all([
      apiGet<Status>("/api/v1/page/status"),
      apiGet<{ items: Thread[] }>("/api/v1/page/threads"),
      apiGet<{ items: Draft[] }>("/api/v1/page/drafts"),
      apiGet<StoreProfile>("/api/v1/store/profile").catch(() => null),
      apiGet<Promotion[]>("/api/v1/store/promotions").catch(() => []),
      apiGet<{ ok: boolean; usage: ApifyUsage }>("/api/v1/trends/apify-usage").catch(() => null),
    ])
      .then(([st, th, dr, prof, promos, usageRes]) => {
        setStatus(st);
        setThreads(th.items ?? []);
        setDrafts(dr.items ?? []);
        if (prof) setProfile(prof);
        if (promos) setPromotions(promos);
        if (usageRes?.usage) setApifyUsage(usageRes.usage);
        setError(null);
      })
      .catch((e) => setError(viError(e, { doing: "mở được Page quán" })))
      .finally(() => setLoading(false));

    fetchTrendsData(regionFilter, categoryFilter, activeKeyword, scrapeMode);
  }, [regionFilter, categoryFilter, activeKeyword, scrapeMode, fetchTrendsData]);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  // Bộ đếm Tự Động Quét theo chu kỳ tùy chỉnh (Chức năng 4)
  useEffect(() => {
    if (!autoScanEnabled || !token) return;

    setCountdownSeconds(scanIntervalMinutes * 60);

    const timer = setInterval(() => {
      // Chỉ chạy khi tab đang hiển thị (Tab Visibility Check để chống quá tải)
      if (document.hidden) return;

      setCountdownSeconds((prev) => {
        if (prev <= 1) {
          fetchTrendsData(regionFilter, categoryFilter, activeKeyword, scrapeMode, false);
          return scanIntervalMinutes * 60;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [autoScanEnabled, scanIntervalMinutes, regionFilter, categoryFilter, activeKeyword, scrapeMode, token, fetchTrendsData]);

  const handleApplyKeywordSearch = (kw: string) => {
    setActiveKeyword(kw);
    setKeywordInput(kw);
    setShowSavedOnly(false);
    fetchTrendsData(regionFilter, categoryFilter, kw, scrapeMode, true);
  };

  const handleClearKeyword = () => {
    setKeywordInput("");
    setActiveKeyword("");
    fetchTrendsData(regionFilter, categoryFilter, "", scrapeMode, true);
  };

  const handleRegionChange = (newRegion: string) => {
    setRegionFilter(newRegion);
    setShowSavedOnly(false);
    fetchTrendsData(newRegion, categoryFilter, activeKeyword, scrapeMode, true);
  };

  const handleCategoryChange = (newCategory: string) => {
    setCategoryFilter(newCategory);
    fetchTrendsData(regionFilter, newCategory, activeKeyword, scrapeMode, true);
  };

  // Messenger Thread operations
  async function reply(id: string) {
    const text = (replyDraft[id] ?? "").trim();
    if (!text) return;
    setSendingReplyId(id);
    try {
      await apiSend(`/api/v1/page/threads/${id}/reply`, { text });
      push("Đã gửi trả lời cho khách.");
      setReplyDraft((m) => ({ ...m, [id]: "" }));
      load();
    } catch (e) {
      setError(viError(e, { doing: "gửi được trả lời" }));
    } finally {
      setSendingReplyId(null);
    }
  }

  async function approveSuggestion(th: Thread) {
    const text = (replyDraft[th.id] || th.suggested_reply || "").trim();
    if (!text) return;
    setSendingReplyId(th.id);
    try {
      await apiSend(`/api/v1/page/threads/${th.id}/approve`, {
        final_reply: text,
        tag: !th.is_within_24h ? "CONFIRMED_EVENT_UPDATE" : undefined,
      });
      push("Đã duyệt & gửi câu trả lời.");
      setReplyDraft((m) => ({ ...m, [th.id]: "" }));
      load();
    } catch (e) {
      setError(viError(e, { doing: "duyệt trả lời" }));
    } finally {
      setSendingReplyId(null);
    }
  }

  async function loadReflection() {
    setReflectionLoading(true);
    try {
      const res = await apiGet<{ ok: boolean; report: any }>("/api/v1/page/audit/reflection/latest");
      if (res && res.report) {
        setReflectionReport(res.report);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setReflectionLoading(false);
    }
  }

  async function triggerReflection() {
    setReflectionLoading(true);
    try {
      const res = await apiSend<{ ok: boolean; report: any }>("/api/v1/page/audit/reflection", {});
      if (res && res.report) {
        setReflectionReport(res.report);
        push("Đã hoàn tất phân tích tự đánh giá CSKH hôm nay!");
      }
    } catch (e) {
      setError(viError(e, { doing: "chạy tự đánh giá" }));
    } finally {
      setReflectionLoading(false);
    }
  }

  async function applyRuleProposal(p: any) {
    try {
      await apiSend("/api/v1/page/audit/reflection/apply-proposal", {
        proposal_id: p.proposal_id,
        title: p.title,
        suggested_rule: p.suggested_rule,
        topic: p.topic,
      });
      push(`Đã thêm "${p.title}" vào cẩm nang quán thành công!`);
      setReflectionReport((r: any) => {
        if (!r) return r;
        return {
          ...r,
          playbook_rule_proposals: r.playbook_rule_proposals.map((item: any) =>
            item.proposal_id === p.proposal_id ? { ...item, status: "da_ap_dung" } : item
          ),
        };
      });
    } catch (e) {
      setError(viError(e, { doing: "áp dụng đề xuất cẩm nang" }));
    }
  }

  async function saveProfile() {
    if (!profile) return;
    try {
      await apiSend("/api/v1/store/profile", profile, "PUT");
      push("Đã lưu thông tin quán.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "lưu thông tin quán" }));
    }
  }

  async function createDraft() {
    if (!draftText.trim()) return;
    try {
      await apiSend("/api/v1/page/drafts", { noi_dung: draftText.trim() });
      setDraftText("");
      push("Đã lưu nháp bài.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "lưu được nháp bài", forbidden: "Chỉ quản lý mới soạn bài page." }));
    }
  }

  async function decideDraft(id: string, quyet_dinh: "duyet" | "tu_choi") {
    try {
      await apiSend(`/api/v1/page/drafts/${id}`, { quyet_dinh });
      push(quyet_dinh === "duyet" ? "Đã duyệt & Đăng bài." : "Đã từ chối nháp.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "quyết được nháp bài" }));
    }
  }

  async function generateAiDraft(customTopic?: string) {
    const topic = (customTopic || aiTopic).trim();
    if (!topic) {
      push("Vui lòng nhập chủ đề bài đăng cho AI.", "err");
      return;
    }
    try {
      setAiGenerating(true);
      await apiSend("/api/v1/page/drafts/ai-generate", { topic, tone: aiTone });
      push("AI đã soạn xong bài viết và lưu vào danh sách nháp!");
      setAiTopic("");
      load();
    } catch (e) {
      setError(viError(e, { doing: "AI soạn thảo bài viết", forbidden: "Chỉ quản lý mới yêu cầu AI soạn bài." }));
    } finally {
      setAiGenerating(false);
    }
  }

  function useTrendForDraft(trend: TrendItem) {
    setTab("drafts");
    setAiTopic(`Bắt trend món: ${trend.cum_tu_khoa_viral || trend.tieu_de}`);
  }

  if (!token) return <AuthGate />;
  if (!manager) {
    return (
      <div className="nq-page">
        <PageHeader kicker="Page quán" title="Không đủ quyền truy cập" />
        <Notice>Bạn cần là Quản lý hoặc Chủ quán để truy cập trang này.</Notice>
      </div>
    );
  }

  const connected = Boolean(status?.connected);

  const formatCountdown = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // ── Hội thoại Messenger: tiện ích hiển thị ────────────────────────────────
  const threadTime = (th: Thread): string => {
    const raw =
      th.last_message_at ||
      (th.replies && th.replies.length > 0 ? th.replies[th.replies.length - 1].at : "") ||
      "";
    if (!raw) return "";
    const t = new Date(raw.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`);
    if (Number.isNaN(t.getTime())) return "";
    const now = new Date();
    const sameDay = t.toDateString() === now.toDateString();
    if (sameDay) {
      return t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return t.toLocaleDateString([], { day: "2-digit", month: "2-digit" });
  };

  const avatarFor = (th: Thread): { fallback: string; src?: string } => {
    const name = th.sender_name || "Khách";
    const fallback = name.trim().charAt(0).toUpperCase();
    return { fallback, src: th.sender_avatar || undefined };
  };

  const isCustomerMsg = (th: Thread, m: NonNullable<Thread["replies"]>[number]): boolean => {
    const by = String(m.by || "");
    if (by === th.psid || by === th.id || by.startsWith("fb_")) return true;
    const profTen = th.customer_profile?.ten_khach;
    if (profTen && by === profTen) return true;
    // Tin do nhân viên/QL/chatbot gửi đi — không phải khách
    if (by.includes("Quản lý") || by.includes("Chatbot") || by.includes("Copilot") || by.includes("Agent")) return false;
    // Có thời điểm tin nhắn `at` nhưng sender lạ — ưu tiên xem là khách khi chưa khớp ai
    return !by || by === th.sender_name || by === th.from;
  };

  const filteredThreads = threads.filter((th) => {
    if (threadFilter === "needs_action") return Boolean(th.needs_action || th.pending_approval);
    if (threadFilter === "within_24h") return th.is_within_24h !== false;
    return true;
  });

  const activeThread = filteredThreads.find((t) => t.id === activeThreadId) || null;

  const displayedTrends = showSavedOnly ? savedTrends : trends;

  const currentSourceLabel =
    regionFilter === "tiktok_vn"
      ? "TikTok VN"
      : regionFilter === "threads_vn"
      ? "Threads & Gen Z"
      : regionFilter === "google_vn"
      ? "Google Trends VN"
      : regionFilter === "star_vn"
      ? "Showbiz & KOLs"
      : regionFilter === "tiktok_global"
      ? "Quốc tế"
      : "Tất cả nguồn";

  return (
    <div className="nq-page">
      <PageHeader
        kicker="Trí Tuệ Thị Trường & Kênh Khách Hàng"
        title="Page Quán & Radar Trí Tuệ Xu Hướng Viral"
        meta="Cào độc quyền từng nền tảng, quét chủ đề ngách F&B, lưu trữ kịch bản marketing và bắt nhịp video/bình luận triệu view."
      />

      <Toasts toasts={toasts} onDismiss={dismiss} />

      {error ? <Alert>{error}</Alert> : null}
      {loading ? <Loading skeleton="list">Đang đọc dữ liệu xu hướng…</Loading> : null}

      <div className="mb-6 flex flex-wrap gap-2 border-b border-[var(--nq-line)] pb-2">
        <Btn
          variant={tab === "trends" ? "primary" : "ghost"}
          onClick={() => {
            setTab("trends");
            setShowSavedOnly(false);
          }}
        >
          Radar Trí Tuệ Xu Hướng ({trends.length})
        </Btn>
        <Btn
          variant={tab === "saved_trends" ? "primary" : "ghost"}
          onClick={() => {
            setTab("saved_trends");
            if (savedTrends.length > 0) setSelectedTrend(savedTrends[0]);
          }}
        >
          Kho Xu Hướng Đã Lưu ({savedTrends.length})
        </Btn>
        <Btn variant={tab === "threads" ? "primary" : "ghost"} onClick={() => setTab("threads")}>
          Hội thoại Messenger ({threads.length})
          {threads.filter((t) => t.needs_action || t.pending_approval).length > 0 ? (
            <span className="ml-1.5 rounded-full bg-[var(--nq-accent)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--nq-accent-ink)]">
              {threads.filter((t) => t.needs_action || t.pending_approval).length}
            </span>
          ) : null}
        </Btn>
        <Btn variant={tab === "drafts" ? "primary" : "ghost"} onClick={() => setTab("drafts")}>
          Nháp bài Fanpage ({drafts.length})
        </Btn>
        {manager ? (
          <Btn variant={tab === "config" ? "primary" : "ghost"} onClick={() => setTab("config")}>
            Cấu hình Thông tin quán
          </Btn>
        ) : null}
        <Btn
          variant={tab === "reflection" ? "primary" : "ghost"}
          onClick={() => {
            setTab("reflection");
            loadReflection();
          }}
        >
          Tự Đánh Giá CSKH {reflectionReport ? `(${reflectionReport.csat_score})` : ""}
        </Btn>
      </div>

      {/* TAB 1: RADAR TRÍ TUỆ XU HƯỚNG & GIẢI MÃ TỪ KHÓA VIRAL */}
      {tab === "trends" && (
        <div className="space-y-6">
          {/* KHỐI 0: PHƯƠNG THỨC CÀO DỮ LIỆU + HẠN MỨC APIFY */}
          <section className="bg-[var(--nq-surface-hi)] border-2 border-[var(--nq-dim)] p-4 md:p-5">
            {/* Chọn phương thức — việc chính, đặt trước; hạn mức là ngữ cảnh đi kèm */}
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm nq-block-title text-[var(--nq-fg)]">
                  Phương thức cào dữ liệu
                </h3>
                <p className="mt-1 text-xs text-[var(--nq-dim)]">
                  Miễn phí là mặc định. Chỉ tốn hạn mức Apify khi bạn chọn ép hoặc khi nguồn
                  miễn phí trả rỗng.
                </p>
              </div>
              <Btn
                variant="ghost"
                onClick={async () => {
                  setUsageRefreshing(true);
                  try {
                    const res = await apiGet<{ ok: boolean; usage: ApifyUsage }>(
                      "/api/v1/trends/apify-usage?refresh=true"
                    );
                    if (res.usage) {
                      setApifyUsage(res.usage);
                      push(
                        res.usage.usage_measured
                          ? "Đã cập nhật hạn mức Apify."
                          : "Apify không trả số liệu — xem console.apify.com để biết số chính xác."
                      );
                    }
                  } catch (e) {
                    push(viError(e, { doing: "đọc hạn mức Apify" }));
                  } finally {
                    setUsageRefreshing(false);
                  }
                }}
                busy={usageRefreshing}
                busyLabel="Đang kiểm tra…"
                className="rounded-full border-2 border-[var(--nq-dim)] bg-transparent px-4 py-2 text-xs font-bold uppercase tracking-widest text-[var(--nq-fg)] transition-all hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)] disabled:opacity-50"
                title="Đọc lại hạn mức & mức sử dụng mới nhất từ Apify"
              >
                Kiểm tra số dư
              </Btn>
            </div>

            {/* Bốn phương thức — chip chọn một, mô tả nằm ngay dưới nhãn */}
            <ul className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {(
                [
                  {
                    id: "auto",
                    title: "Tự động",
                    tag: "Khuyên dùng",
                    desc: "TikWM & Google trước (0đ), chỉ gọi Apify khi nguồn miễn phí trả rỗng",
                  },
                  {
                    id: "direct_only",
                    title: "Chỉ nguồn miễn phí",
                    tag: "0đ",
                    desc: "Không gọi Apify trong mọi trường hợp — an toàn nhất về chi phí",
                  },
                  {
                    id: "browser",
                    title: "Trình duyệt thật",
                    tag: "Camoufox",
                    desc: "Firefox chống phát hiện, miễn phí, chậm hơn (~3–10 giây mỗi lượt)",
                  },
                  {
                    id: "apify_force",
                    title: "Ép dùng Apify",
                    tag: "Tốn hạn mức",
                    desc: "Cào sâu qua Apify trước — chỉ dùng khi cần dữ liệu đầy đủ nhất",
                  },
                ] as const
              ).map((m) => {
                const active = scrapeMode === m.id;
                return (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setScrapeMode(m.id);
                        push(`Đã chuyển sang: ${m.title}`);
                        fetchTrendsData(regionFilter, categoryFilter, activeKeyword, m.id, true);
                      }}
                      aria-pressed={active}
                      className={`h-full w-full rounded-[var(--nq-radius-bubble)] border-2 p-3 text-left transition-all ${
                        active
                          ? "border-[var(--nq-accent)] bg-[var(--nq-accent-soft)]"
                          : "border-[var(--nq-dim)] bg-[var(--nq-surface)] hover:border-[var(--nq-accent)]"
                      }`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-xs nq-block-title text-[var(--nq-fg)]">
                          {m.title}
                        </span>
                        <span className="text-[10px] font-mono text-[var(--nq-dim)]">{m.tag}</span>
                      </span>
                      <span className="mt-1 block text-[11px] leading-relaxed text-[var(--nq-dim)]">
                        {m.desc}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>

            {/* Hạn mức Apify — luôn hiện, đây là thứ người quán cần thấy */}
            <div className="mt-4 border-t-2 border-dashed border-[var(--nq-dim)] pt-3">
              {apifyUsage === null ? (
                <p className="text-xs font-mono text-[var(--nq-dim)]">Đang đọc hạn mức Apify…</p>
              ) : (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs">
                    <span className="font-bold uppercase tracking-widest text-[var(--nq-dim)]">
                      Hạn mức Apify
                    </span>
                    <span className="text-[var(--nq-dim)]">
                      <strong className="font-mono text-[var(--nq-fg)]">
                        {apifyUsage.username || "—"}
                      </strong>{" "}
                      · {apifyUsage.plan}
                    </span>
                  </div>

                  {apifyUsage.usage_measured ? (
                    <>
                      <div className="flex flex-wrap items-baseline gap-2 font-mono text-sm">
                        <span className="text-[var(--nq-fg)]">
                          ${(apifyUsage.usage_usd ?? 0).toFixed(2)}
                        </span>
                        {apifyUsage.monthly_limit_usd !== null && (
                          <span className="text-[var(--nq-dim)]">
                            / ${apifyUsage.monthly_limit_usd.toFixed(2)} ({apifyUsage.usage_percent}
                            %)
                          </span>
                        )}
                        {apifyUsage.remaining_usd !== null && (
                          <span className="text-[var(--nq-dim)]">
                            · còn ${apifyUsage.remaining_usd.toFixed(2)}
                          </span>
                        )}
                      </div>

                      {apifyUsage.usage_percent !== null && (
                        <ProgressBar value={apifyUsage.usage_percent} max={100} />
                      )}

                      {apifyUsage.quota_exhausted && (
                        <Alert kind="err">
                          Đã chạm trần hạn mức tháng. Apify sẽ từ chối lượt cào mới cho tới khi sang
                          chu kỳ kế tiếp — nên chuyển sang &ldquo;Chỉ nguồn miễn phí&rdquo;.
                        </Alert>
                      )}

                      {apifyUsage.usage_cycle_end_at && (
                        <p className="text-[11px] font-mono text-[var(--nq-dim)]">
                          Chu kỳ làm mới:{" "}
                          {new Date(apifyUsage.usage_cycle_end_at).toLocaleDateString("vi-VN")}
                        </p>
                      )}

                      {apifyUsage.note && (
                        <TechnicalDrawer
                          summary="Chi tiết kỹ thuật hạn mức"
                          lines={[apifyUsage.note]}
                        />
                      )}
                    </>
                  ) : (
                    <Alert kind="info">
                      <span className="block">
                        {apifyUsage.note ||
                          "Apify không trả số liệu sử dụng cho tài khoản này."}
                      </span>
                      <span className="mt-1 block text-xs">
                        Số chính xác luôn xem được tại{" "}
                        <a
                          href="https://console.apify.com/billing/historical-usage"
                          target="_blank"
                          rel="noreferrer"
                          className="underline decoration-dotted hover:text-[var(--nq-accent)]"
                        >
                          Apify Console → Billing
                        </a>
                        .
                      </span>
                    </Alert>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* KHỐI 1: TÙY CHỈNH TỰ ĐỘNG QUÉT & BẢO VỆ CHỐNG QUÁ TẢI (Chức năng 4) */}
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg nq-surface-block p-4">
            <div className="flex items-center gap-3">
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoScanEnabled}
                  onChange={(e) => {
                    setAutoScanEnabled(e.target.checked);
                    if (e.target.checked) {
                      push(`Đã bật tự động quét mỗi ${scanIntervalMinutes} phút.`);
                    } else {
                      push("Đã tắt tự động quét.");
                    }
                  }}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-[var(--nq-dim)] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-[var(--nq-line-strong)] after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--nq-st-ok)]"></div>
              </label>
              <div>
                <span className="text-xs font-bold text-[var(--nq-primary)]">
                  Tự động quét định kỳ:{" "}
                  <strong className={autoScanEnabled ? "text-[var(--nq-st-ok-ink)]" : "text-[var(--nq-muted)]"}>
                    {autoScanEnabled ? "ĐANG BẬT" : "TẮT"}
                  </strong>
                </span>
                {autoScanEnabled && (
                  <p className="text-2xs text-[var(--nq-st-ok-ink)] font-mono">
                    Quét lại sau: <strong>{formatCountdown(countdownSeconds)}</strong> (Tự ngủ khi ẩn tab)
                  </p>
                )}
              </div>
            </div>

            {/* Tùy chỉnh số phút quét */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-[var(--nq-muted)] font-medium">Chu kỳ quét:</span>
              {[5, 15, 30, 60].map((mins) => (
                <button
                  key={mins}
                  onClick={() => {
                    setScanIntervalMinutes(mins);
                    setCustomMinutesInput(mins.toString());
                    setCountdownSeconds(mins * 60);
                    push(`Đã đổi chu kỳ quét sang ${mins} phút.`);
                  }}
                  className={`rounded px-2.5 py-1 text-xs font-bold transition cursor-pointer ${
                    scanIntervalMinutes === mins
                      ? "bg-[var(--nq-accent)] text-[var(--nq-accent-ink)] shadow-sm"
                      : "bg-[var(--nq-surface)] text-[var(--nq-muted)] hover:bg-[var(--nq-dim)]"
                  }`}
                >
                  {mins} phút
                </button>
              ))}

              <div className="flex items-center gap-1 ml-2">
                <input
                  type="number"
                  min="1"
                  max="720"
                  value={customMinutesInput}
                  onChange={(e) => setCustomMinutesInput(e.target.value)}
                  className="w-14 rounded border border-[var(--nq-dim)] bg-[var(--nq-surface)] px-1.5 py-1 text-center text-xs text-[var(--nq-primary)]"
                />
                <button
                  onClick={() => {
                    const val = parseInt(customMinutesInput, 10);
                    if (val > 0 && val <= 720) {
                      setScanIntervalMinutes(val);
                      setCountdownSeconds(val * 60);
                      push(`Đã áp dụng chu kỳ quét tùy chỉnh: ${val} phút.`);
                    }
                  }}
                  className="rounded bg-[var(--nq-surface)] px-2 py-1 text-2xs font-bold text-[var(--nq-primary)] hover:bg-[var(--nq-dim)] hover:text-[var(--nq-fg)] transition cursor-pointer"
                >
                  Đặt phút
                </button>
              </div>
            </div>
          </div>

          {/* KHỐI 2: CÀO THEO CHỦ ĐỀ / TỪ KHÓA NGÁCH QUAN TÂM (Chức năng 1) */}
          <div className="space-y-3 rounded-lg border-2 border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] bg-[var(--nq-st-warn-soft)] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-xs font-bold uppercase tracking-wider text-[var(--nq-st-warn-ink)]">
                Quét Sâu Chủ Đề / Từ Khóa Bạn Quan Tâm (F&B, Cà phê, Trà sữa...)
              </span>
              {activeKeyword && (
                <span className="text-xs text-[var(--nq-st-warn-ink)] font-mono bg-[var(--nq-st-warn-soft)] px-2 py-0.5 rounded border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))]">
                  Đang lọc từ khóa: &quot;{activeKeyword}&quot;
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <div className="flex-1 min-w-[240px] flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Nhập chủ đề muốn quét (VD: matcha, cà phê muối, trà mãng cầu, checkin...)"
                  value={keywordInput}
                  onChange={(e) => setKeywordInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleApplyKeywordSearch(keywordInput);
                  }}
                  className="w-full rounded border border-[var(--nq-dim)] bg-[var(--nq-surface)] px-3 py-2 text-xs text-[var(--nq-primary)] placeholder:text-[var(--nq-muted)] focus:border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] focus:outline-none"
                />
              </div>
              <button
                onClick={() => handleApplyKeywordSearch(keywordInput)}
                disabled={isScanning}
                className="inline-flex items-center gap-1 rounded border border-[var(--nq-accent)] bg-[var(--nq-accent)] px-4 py-2 text-xs font-bold text-[var(--nq-accent-ink)] hover:brightness-110 transition shadow cursor-pointer disabled:opacity-50"
              >
                Quét Chủ Đề Này
              </button>
              {activeKeyword && (
                <button
                  onClick={handleClearKeyword}
                  className="rounded border border-[var(--nq-dim)] bg-[var(--nq-surface)] px-3 py-2 text-xs font-bold text-[var(--nq-muted)] hover:text-white transition cursor-pointer"
                >
                  Xóa Lọc
                </button>
              )}
            </div>

            {/* Quick Keyword Chips */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1 text-xs">
              <span className="text-2xs text-[var(--nq-muted)] font-medium">Gợi ý nhanh cho quán:</span>
              {[
                { tag: "matcha", label: "#matcha" },
                { tag: "cà phê muối", label: "#cà phê muối" },
                { tag: "trà sữa", label: "#trà sữa" },
                { tag: "check in quán", label: "#check-in" },
                { tag: "đồ ăn vặt", label: "#đồ ăn vặt" },
                { tag: "drama", label: "#drama" },
                { tag: "gen z", label: "#gen z" },
              ].map((k) => (
                <button
                  key={k.tag}
                  onClick={() => handleApplyKeywordSearch(k.tag)}
                  className="rounded bg-[var(--nq-surface)] px-2 py-0.5 text-2xs font-mono text-[var(--nq-primary)] hover:border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] hover:text-[var(--nq-st-warn-ink)] border border-[var(--nq-dim)] transition cursor-pointer"
                >
                  {k.label}
                </button>
              ))}
            </div>
          </div>

          {/* KHỐI 3: BỘ LỌC NGUỒN CÀO ĐỘC QUYỀN (Targeted Scraping) & BOOKMARK */}
          <div className="space-y-3 rounded-lg nq-surface-block p-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--nq-dim)] pb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-[var(--nq-accent)]">
                Nền Tảng Cào Dữ Liệu (Chọn Độc Quyền Theo Nhu Cầu):
              </span>

              {/* Nút Cào Độc Quyền theo Nguồn */}
              <button
                onClick={() => fetchTrendsData(regionFilter, categoryFilter, activeKeyword, scrapeMode, true)}
                disabled={isScanning}
                className="inline-flex items-center gap-1.5 rounded border border-[var(--nq-accent)] bg-[var(--nq-accent)] px-4 py-1.5 text-xs font-bold text-[var(--nq-accent-ink)] shadow-md hover:brightness-110 transition-all cursor-pointer disabled:opacity-50"
              >
                Cào Dữ Liệu {currentSourceLabel}
              </button>
            </div>

            {/* Thanh trạng thái loading toàn bộ dữ liệu */}
            {isScanning && (
              <div className="rounded border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] bg-[var(--nq-st-ok-soft)] p-3 text-xs text-[var(--nq-st-ok-ink)] font-mono flex items-center justify-between animate-pulse">
                <span>{scanStatusText}</span>
                <span className="text-2xs">Đang tải trọn gói...</span>
              </div>
            )}

            {/* Nút Lọc Theo Nền Tảng */}
            <div className="flex flex-wrap gap-2 pt-1">
              {[
                { id: "all", label: "Tất cả nguồn" },
                { id: "tiktok_vn", label: "TikTok Việt Nam" },
                { id: "threads_vn", label: "Meta Threads" },
                { id: "google_vn", label: "Google Trends" },
                { id: "star_vn", label: "Showbiz & Báo chí" },
                { id: "tiktok_global", label: "Quốc tế (Global)" },
              ].map((p) => (
                <button
                  key={p.id}
                  onClick={() => handleRegionChange(p.id)}
                  className={`rounded border px-3 py-1.5 text-xs font-bold transition-all cursor-pointer ${
                    regionFilter === p.id && !showSavedOnly
                      ? "border-[var(--nq-accent)] bg-[var(--nq-accent)] text-[var(--nq-accent-ink)] shadow-md"
                      : "border-[var(--nq-line-strong)] bg-[var(--nq-surface)] text-[var(--nq-ink-muted)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
                  }`}
                >
                  {p.label}
                </button>
              ))}

              {/* Tab Đã Lưu (Bookmark - Chức năng 3) */}
              <button
                onClick={() => {
                  setShowSavedOnly(true);
                  if (savedTrends.length > 0) {
                    setSelectedTrend(savedTrends[0]);
                  }
                }}
                className={`rounded border px-3 py-1.5 text-xs font-bold transition-all cursor-pointer ${
                  showSavedOnly
                    ? "border-[var(--nq-accent)] bg-[var(--nq-accent-soft)] text-[var(--nq-accent)] shadow-md"
                    : "border-[var(--nq-line-strong)] bg-[var(--nq-surface)] text-[var(--nq-ink-muted)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
                }`}
              >
                Xu Hướng Đã Lưu ({savedTrends.length})
              </button>
            </div>

            {/* Nút Lọc Theo Lĩnh Vực */}
            {!showSavedOnly && (
              <div className="flex flex-wrap items-center gap-2 border-t border-[var(--nq-dim)] pt-3 text-xs">
                <span className="font-bold text-[var(--nq-muted)]">Lĩnh vực:</span>
                {[
                  { id: "all", label: "Tất cả lĩnh vực" },
                  { id: "am_thuc_fnb", label: "Ẩm thực & Đồ uống F&B" },
                  { id: "tam_ly_lifestyle", label: "Tâm lý & Lifestyle Gen Z" },
                  { id: "meme_cau_noi", label: "Meme & Câu cửa miệng" },
                  { id: "trao_luu_pop_culture", label: "Pop Culture & Showbiz" },
                ].map((c) => (
                  <button
                    key={c.id}
                    onClick={() => handleCategoryChange(c.id)}
                    className={`rounded border px-2.5 py-1 transition-all cursor-pointer ${
                      categoryFilter === c.id
                        ? "border-[var(--nq-accent)] bg-[var(--nq-accent)] font-bold text-[var(--nq-accent-ink)] shadow-sm"
                        : "border-[var(--nq-line)] bg-[var(--nq-surface)] text-[var(--nq-ink-muted)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* GRID HIỂN THỊ DANH SÁCH & PHÂN TÍCH CHUYÊN SÂU — không khóa max-height để Tín Hiệu không bị cắt */}
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-12 items-start">
            {/* Cột Trái: Danh sách Trend */}
            <div className="space-y-3 xl:col-span-5">
              <div className="flex items-center justify-between py-1">
                <h3 className="text-sm font-bold uppercase tracking-wider text-[var(--nq-accent)]">
                  {showSavedOnly
                    ? `Danh Sách Đã Lưu (${savedTrends.length})`
                    : `Tín Hiệu Cào Thật (${displayedTrends.length})`}
                </h3>
                <span className="text-xs text-[var(--nq-accent)] font-mono">
                  {showSavedOnly ? "Kế hoạch quán" : "● Dữ liệu cào độc quyền"}
                </span>
              </div>

              {displayedTrends.length === 0 ? (
                <Empty>
                  {showSavedOnly
                    ? "Chưa có xu hướng nào được lưu. Hãy bấm nút Lưu trên các xu hướng để lưu vào đây!"
                    : "Không tìm thấy xu hướng nào theo bộ lọc hoặc từ khóa đã chọn."}
                </Empty>
              ) : (
                displayedTrends.map((t) => {
                  const isSelected = selectedTrend?.id === t.id;
                  const isBookmarked = savedTrends.some((st) => st.id === t.id);

                  const platformBadge =
                    t.nguon_goc === "threads_vn"
                      ? "Threads"
                      : t.nguon_goc === "tiktok_vn"
                      ? "TikTok VN"
                      : t.nguon_goc === "google_vn"
                      ? "Google VN"
                      : t.nguon_goc === "star_vn"
                      ? "Showbiz"
                      : "Global";

                  const lifecycleBadge =
                    t.vong_doi === "moi_nhu"
                      ? { text: "MỚI NỔI 24H", cls: "bg-[var(--nq-st-ok-soft)] text-[var(--nq-st-ok-ink)] border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))]" }
                      : t.vong_doi === "dang_dinh"
                      ? { text: "ĐANG ĐỈNH CAO", cls: "bg-[var(--nq-st-warn-soft)] text-[var(--nq-st-warn-ink)] border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))]" }
                      : { text: "BÃO HÒA", cls: "bg-[var(--nq-line-control)] text-[var(--nq-ink-muted)] border-[var(--nq-line-control)]" };

                  return (
                    <div
                      key={t.id}
                      onClick={() => setSelectedTrend(t)}
                      className={`cursor-pointer nq-surface-tile p-4 transition-all relative ${
                        isSelected
                          ? "border-[var(--nq-accent)] bg-[var(--nq-surface-hi)] shadow-md ring-1 ring-[var(--nq-accent)]"
                          : "border-[var(--nq-line)] bg-[var(--nq-surface)] hover:border-[var(--nq-accent)]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-bold text-[var(--nq-ink)] text-sm">{t.tieu_de}</span>
                        <div className="flex flex-col items-end gap-1 shrink-0">
                          <span className="inline-block rounded border border-[var(--nq-line-strong)] bg-[var(--nq-accent-soft)] px-2 py-0.5 text-xs font-mono font-bold text-[var(--nq-accent)]">
                            {platformBadge}
                          </span>
                          <span className={`inline-block rounded border px-1.5 py-0.2 text-2xs font-bold ${lifecycleBadge.cls}`}>
                            {lifecycleBadge.text}
                          </span>
                        </div>
                      </div>

                      {/* Tag Từ khóa cửa miệng */}
                      <div className="mt-2 inline-flex items-center gap-1 rounded border border-[var(--nq-line-strong)] bg-[var(--nq-surface-hi)] px-2 py-0.5 text-xs font-mono font-bold text-[var(--nq-accent)]">
                        &quot;{t.cum_tu_khoa_viral}&quot;
                      </div>

                      <p className="mt-2 text-xs text-[var(--nq-ink-muted)] line-clamp-2">{t.diem_nhan_dac_biet}</p>

                      <div className="mt-3 flex items-center justify-between border-t border-[var(--nq-line)] pt-2 text-xs">
                        <span className="font-mono text-[var(--nq-accent)] font-bold">
                          +{t.toc_do_tang_truong_24h}% tăng trưởng
                        </span>
                        
                        <div className="flex items-center gap-2">
                          <button
                            onClick={(e) => toggleSaveTrend(t, e)}
                            className={`px-2 py-0.5 rounded border text-xs font-bold transition cursor-pointer ${
                              isBookmarked
                                ? "border-[var(--nq-accent)] bg-[var(--nq-accent)] text-[var(--nq-accent-ink)]"
                                : "border-[var(--nq-line-strong)] bg-[var(--nq-surface)] text-[var(--nq-ink-muted)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
                            }`}
                            title={isBookmarked ? "Bỏ lưu" : "Lưu vào kế hoạch quán"}
                          >
                            {isBookmarked ? "Đã lưu" : "Lưu"}
                          </button>
                          <span className="rounded border border-[var(--nq-line-strong)] bg-[var(--nq-surface-hi)] px-2 py-0.5 text-[var(--nq-accent)] font-bold">
                            Viral: {t.diem_tiem_nang_viral}/100
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Cột Phải: Bảng Phân Tích Chuyên Sâu Cốt Lõi Trend */}
            <div className="space-y-4 nq-surface-block p-6 xl:col-span-7">
              {selectedTrend ? (
                <>
                  {/* Header: Cụm từ khóa cửa miệng cốt lõi & Nút Bookmark */}
                  <div className="rounded nq-surface-block border-[var(--nq-accent)] p-4 shadow-sm">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-[var(--nq-accent)]">
                        Cụm Từ Khóa Cửa Miệng Viral (Bắt Sóng Ngay)
                      </span>
                      <div className="flex items-center gap-2 flex-wrap">
                        <button
                          type="button"
                          onClick={() => useTrendForDraft(selectedTrend)}
                          className="px-2.5 py-1 rounded border border-[var(--nq-accent)] bg-[var(--nq-accent)] text-xs font-bold transition cursor-pointer flex items-center gap-1 text-[var(--nq-accent-ink)] shadow"
                          title="Tạo bài viết Fanpage ăn theo xu hướng này với AI"
                        >
                          AI Viết Bài
                        </button>
                        <button
                          onClick={() => toggleSaveTrend(selectedTrend)}
                          className={`px-2.5 py-1 rounded border text-xs font-bold transition cursor-pointer flex items-center gap-1 ${
                            savedTrends.some((st) => st.id === selectedTrend.id)
                              ? "border-[var(--nq-accent)] bg-[var(--nq-accent-soft)] text-[var(--nq-accent)] shadow"
                              : "border-[var(--nq-line-strong)] bg-[var(--nq-surface)] text-[var(--nq-ink-muted)] hover:border-[var(--nq-accent)] hover:text-[var(--nq-accent)]"
                          }`}
                        >
                          {savedTrends.some((st) => st.id === selectedTrend.id) ? "Đã Lưu Kế Hoạch" : "Lưu Xu Hướng Này"}
                        </button>
                        <span className="text-xs font-bold text-[var(--nq-accent)] font-mono">
                          {selectedTrend.du_bao_thoi_gian}
                        </span>
                      </div>
                    </div>
                    <div className="mt-2 text-2xl font-semibold text-[var(--nq-accent)]">
                      &quot;{selectedTrend.cum_tu_khoa_viral}&quot;
                    </div>
                    <p className="mt-1 text-xs text-[var(--nq-muted)]">
                      Chỉ cần nhắc đến cụm từ này trong video, bài viết hoặc comment là cộng đồng mạng hiểu ngay ngữ cảnh.
                    </p>
                  </div>

                  {/* Banner Bằng Chứng & Link Gốc từ Internet */}
                  {selectedTrend.link_goc && (
                    <div className="rounded border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] bg-[var(--nq-st-ok-soft)] p-3 shadow-sm space-y-2">
                      <div className="flex items-center justify-between text-xs text-[var(--nq-st-ok-ink)]">
                        <span className="font-bold flex items-center gap-1">
                          Bằng Chứng & Dữ Liệu Gốc Cào Thật Từ Internet
                        </span>
                        <span className="text-2xs opacity-80">
                          {selectedTrend.thoi_gian_cao || "Vừa cập nhật"} | {selectedTrend.luot_tiep_can || "Lưu lượng cao"}
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-2 pt-1 border-t border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))]">
                        {selectedTrend.link_goc?.includes("threads.net") ? (
                          <a
                            href={selectedTrend.link_goc}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 rounded bg-[var(--nq-bg-elevated)] px-3 py-1 text-xs font-bold text-white border border-[var(--nq-line)] hover:bg-[var(--nq-surface)] transition"
                          >
                            Mở Trên Threads ↗
                          </a>
                        ) : selectedTrend.link_goc?.includes("tiktok.com") ? (
                          <a
                            href={selectedTrend.link_goc}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded bg-[#fe2c55] px-3 py-1 text-xs font-bold text-white hover:bg-[#e0264b] transition"
                          >
                            Mở Trên TikTok ↗
                          </a>
                        ) : (
                          <a
                            href={selectedTrend.link_goc}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded bg-[var(--nq-surface)] px-3 py-1 text-xs font-bold text-[var(--nq-primary)] border border-[var(--nq-dim)] hover:bg-[var(--nq-dim)] transition"
                          >
                            Xem Nguồn Gốc ↗
                          </a>
                        )}
                        {selectedTrend.tiktok_url && !selectedTrend.link_goc?.includes("tiktok.com") && !selectedTrend.link_goc?.includes("threads.net") && (
                          <a
                            href={selectedTrend.tiktok_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded bg-[#fe2c55] px-3 py-1 text-xs font-bold text-white hover:bg-[#e0264b] transition"
                          >
                            Tìm Trên TikTok ↗
                          </a>
                        )}
                        {selectedTrend.tiktok_tag_url && (
                          <a
                            href={selectedTrend.tiktok_tag_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded bg-[var(--nq-surface)] px-3 py-1 text-xs font-bold text-[var(--nq-primary)] border border-[var(--nq-dim)] hover:bg-[var(--nq-dim)] transition"
                          >
                            {selectedTrend.nguon_goc === "threads_vn" ? "Hashtag Threads ↗" : "Hashtag TikTok ↗"}
                          </a>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Khối 1: Điểm nhấn đặc biệt & Nguồn gốc */}
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="space-y-1 rounded border border-[var(--nq-dim)] bg-[var(--nq-surface)] p-3.5">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-muted)]">
                        Điểm Nhấn / Thống Kê Thật
                      </h4>
                      <p className="text-sm font-semibold text-[var(--nq-primary)]">
                        {selectedTrend.diem_nhan_dac_biet}
                      </p>
                    </div>

                    <div className="space-y-1 rounded border border-[var(--nq-dim)] bg-[var(--nq-surface)] p-3.5">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-muted)]">
                        Nguồn Gốc Xuất Phát
                      </h4>
                      <p className="text-sm text-[var(--nq-primary)]">
                        {selectedTrend.nguon_goc_chi_tiet}
                      </p>
                    </div>
                  </div>

                  {/* Khối 2–3: Trích đoạn + bình luận — trải ngang khi đủ chỗ */}
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  {selectedTrend.trich_doan_noi_dung_that && (
                    <div className="space-y-2 rounded border border-[var(--nq-line-strong)] bg-[var(--nq-surface-hi)] p-4">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-accent)]">
                          Nội Dung & Trích Đoạn Gốc Cào Thật Từ Internet
                        </h4>
                        <span className="text-2xs text-[var(--nq-accent)] font-mono">100% Dữ liệu cào thật</span>
                      </div>
                      <p className="text-sm leading-relaxed text-[var(--nq-ink)] italic">
                        &quot;{selectedTrend.trich_doan_noi_dung_that}&quot;
                      </p>
                    </div>
                  )}

                  {selectedTrend.binh_luan_that_tiktok && selectedTrend.binh_luan_that_tiktok.length > 0 && (
                    <div className="space-y-2 rounded border border-[var(--nq-line-strong)] bg-[var(--nq-surface-hi)] p-4">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-accent)]">
                          {selectedTrend.nguon_goc === "threads_vn"
                            ? "Top Thảo Luận & Phản Hồi Thật Từ Threads"
                            : selectedTrend.nguon_goc === "tiktok_vn"
                            ? "Top Bình Luận Thật Cào Trực Tiếp Từ TikTok"
                            : "Thảo Luận Thật Từ Người Dùng"}
                        </h4>
                        <span className="text-2xs text-[var(--nq-accent)] font-mono bg-[var(--nq-accent-soft)] px-2 py-0.5 rounded border border-[var(--nq-line-strong)]">
                          100% Cào từ {selectedTrend.nguon_goc === "threads_vn" ? "Threads" : selectedTrend.nguon_goc === "tiktok_vn" ? "TikTok" : "Nền tảng"}
                        </span>
                      </div>
                      <div className="space-y-1.5 max-h-[22rem] overflow-y-auto pr-1">
                        {selectedTrend.binh_luan_that_tiktok.map((cmt, idx) => (
                          <div
                            key={idx}
                            className="rounded border border-[var(--nq-line)] bg-[var(--nq-surface)] p-2.5 text-xs text-[var(--nq-ink)] font-mono"
                          >
                            {cmt}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  </div>

                  {/* Khối 4–5: Tâm lý + ngữ cảnh — trải ngang */}
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="space-y-1 rounded border border-[var(--nq-line-strong)] bg-[var(--nq-accent-soft)] p-4">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-accent)]">
                        Giải Mã Tâm Lý Khách Hàng / Giới Trẻ
                      </h4>
                      <p className="text-sm leading-relaxed text-[var(--nq-ink)]">
                        {selectedTrend.tam_ly_gioi_tre}
                      </p>
                    </div>

                    <div className="space-y-1 rounded border border-[var(--nq-line-strong)] bg-[var(--nq-surface-hi)] p-4">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-accent)]">
                        Ngữ Cảnh Sử Dụng & Gợi Ý Bắt Trend Tại Quán
                      </h4>
                      <p className="text-sm leading-relaxed text-[var(--nq-ink)]">
                        {selectedTrend.ngu_canh_su_dung}
                      </p>
                    </div>
                  </div>

                  {/* Hashtag & Nền tảng */}
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--nq-dim)] pt-4 text-xs">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-bold text-[var(--nq-muted)]">Hashtags:</span>
                      {selectedTrend.tu_khoa_hashtag.map((tag, idx) => (
                        <span
                          key={idx}
                          className="rounded bg-[var(--nq-surface)] px-2 py-0.5 font-mono text-[var(--nq-primary)] border border-[var(--nq-dim)]"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>

                    <div className="flex items-center gap-1.5 text-[var(--nq-muted)]">
                      <span>Nền tảng cào dữ liệu:</span>
                      <strong className="text-[var(--nq-st-ok-ink)] font-bold bg-[var(--nq-st-ok-soft)] px-2.5 py-0.5 rounded border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))]">
                        {selectedTrend.nen_tang_lan_toa?.[0] || (selectedTrend.nguon_goc === "threads_vn" ? "Meta Threads" : selectedTrend.nguon_goc === "tiktok_vn" ? "TikTok Việt Nam" : "Google Trends")}
                      </strong>
                    </div>
                  </div>
                </>
              ) : (
                <Empty>Chọn một xu hướng ở danh sách bên trái để xem phân tích chi tiết.</Empty>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 1.5: KHO XU HƯỚNG ĐÃ LƯU (DEDICATED SAVED TRENDS PAGE) */}
      {tab === "saved_trends" && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] bg-[var(--nq-st-warn-soft)] p-5 shadow-[var(--nq-elev-1)]">
            <div className="flex items-center gap-3">
              <div>
                <h3 className="text-base font-bold text-[var(--nq-st-warn-ink)]">
                  Kho Xu Hướng Đã Lưu Cho Kế Hoạch Quán ({savedTrends.length})
                </h3>
                <p className="text-xs text-[var(--nq-ink-muted)]">
                  Danh mục các trào lưu, video và công thức bạn đã đánh dấu để chuẩn bị menu, sự kiện hoặc bài đăng Fanpage.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {savedTrends.length > 0 && (
                <button
                  onClick={() => {
                    if (confirm("Bạn có chắc muốn xóa tất cả xu hướng đã lưu?")) {
                      setSavedTrends([]);
                      localStorage.removeItem("nhp_saved_trends_v2");
                      push("Đã xóa toàn bộ xu hướng đã lưu.");
                    }
                  }}
                  className="rounded-lg border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] bg-[var(--nq-st-danger-soft)] px-3 py-1.5 text-xs font-bold text-[var(--nq-st-danger-ink)] hover:bg-[var(--nq-st-danger-soft)] transition cursor-pointer"
                >
                  Xóa Tất Cả
                </button>
              )}
              <button
                onClick={() => setTab("trends")}
                className="rounded-lg bg-[var(--nq-st-warn)] px-4 py-1.5 text-xs font-bold text-black hover:bg-[var(--nq-st-warn)] transition cursor-pointer shadow"
              >
                + Khám Phá Thêm Xu Hướng Mới
              </button>
            </div>
          </div>

          {savedTrends.length === 0 ? (
            <div className="rounded-xl border-2 border-dashed border-[var(--nq-line)] p-12 text-center space-y-4">
              <h4 className="text-base font-bold text-[var(--nq-ink)]">Kho lưu trữ xu hướng đang trống</h4>
              <p className="text-xs text-[var(--nq-ink-muted)] max-w-md mx-auto">
                Khi lướt trên tab <strong>&quot;Radar Trí Tuệ Xu Hướng&quot;</strong>, hãy bấm nút Lưu trên bất kỳ bài viết nào để lưu vào kho này và tiện xem lại bất cứ lúc nào!
              </p>
              <button
                onClick={() => setTab("trends")}
                className="rounded-lg bg-[var(--nq-primary)] px-5 py-2 text-xs font-bold text-black hover:opacity-90 transition cursor-pointer"
              >
                Đến Radar Cào Xu Hướng Ngay
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              {/* Danh sách Trend đã lưu */}
              <div className="space-y-3 lg:col-span-5 max-h-[820px] overflow-y-auto pr-1">
                {savedTrends.map((t) => {
                  const isSelected = selectedTrend?.id === t.id;
                  const platformBadge =
                    t.nguon_goc === "threads_vn"
                      ? "Threads"
                      : t.nguon_goc === "tiktok_vn"
                      ? "TikTok VN"
                      : t.nguon_goc === "google_vn"
                      ? "Google VN"
                      : t.nguon_goc === "star_vn"
                      ? "Showbiz"
                      : "Global";

                  return (
                    <div
                      key={t.id}
                      onClick={() => setSelectedTrend(t)}
                      className={`nq-surface-tile relative p-4 transition-all cursor-pointer ${
                        isSelected
                          ? "border-[var(--nq-accent)] bg-[var(--nq-surface-hi)] shadow-[var(--nq-elev-2-hover)]"
                          : "bg-[var(--nq-surface)] hover:border-[var(--nq-accent)] hover:bg-[var(--nq-surface-hi)]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="rounded bg-[var(--nq-dim)] px-2 py-0.5 text-2xs font-bold text-[var(--nq-primary)] font-mono">
                            {platformBadge}
                          </span>
                          <span className="rounded bg-[var(--nq-st-warn-soft)] text-[var(--nq-st-warn-ink)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] px-2 py-0.5 text-2xs font-bold">
                            ĐÃ LƯU
                          </span>
                        </div>

                        <button
                          onClick={(e) => toggleSaveTrend(t, e)}
                          className="text-[var(--nq-st-warn-ink)] hover:text-[var(--nq-st-warn-ink)] text-xs p-0.5 transition cursor-pointer"
                          title="Bỏ lưu khỏi kho"
                        >
                          Bỏ lưu
                        </button>
                      </div>

                      <h4 className="mt-2 text-sm font-bold text-[var(--nq-primary)] line-clamp-2">
                        {t.tieu_de}
                      </h4>

                      <p className="mt-1 text-xs text-[var(--nq-muted)] line-clamp-2 italic">
                        &quot;{t.trich_doan_noi_dung_that || t.diem_nhan_dac_biet}&quot;
                      </p>

                      <div className="mt-3 flex items-center justify-between border-t border-[var(--nq-dim)] pt-2 text-2xs">
                        <span className="font-mono text-[var(--nq-st-ok-ink)] font-bold">
                          {t.luot_tiep_can || "Tương tác cao"}
                        </span>
                        <span className="font-bold text-[var(--nq-st-warn-ink)]">
                          Điểm viral: {t.diem_tiem_nang_viral}/100
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Chi tiết Trend đã chọn */}
              <div className="space-y-4 rounded-lg nq-surface-block p-5 lg:col-span-7">
                {selectedTrend ? (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--nq-dim)] pb-3">
                      <div>
                        <h3 className="text-base font-bold text-[var(--nq-primary)]">
                          {selectedTrend.tieu_de}
                        </h3>
                        <p className="text-xs text-[var(--nq-muted)] mt-0.5">
                          Từ khóa chính: <strong className="text-[var(--nq-st-warn-ink)]">#{selectedTrend.cum_tu_khoa_viral}</strong>
                        </p>
                      </div>

                      <button
                        onClick={(e) => toggleSaveTrend(selectedTrend, e)}
                        className="rounded border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] bg-[var(--nq-st-warn-soft)] px-3 py-1 text-xs font-bold text-[var(--nq-st-warn-ink)] hover:bg-[var(--nq-st-warn-soft)] transition cursor-pointer"
                      >
                        Bỏ Lưu Xu Hướng Này
                      </button>
                    </div>

                    {/* Nội dung chi tiết & Trích đoạn */}
                    {selectedTrend.trich_doan_noi_dung_that && (
                      <div className="space-y-2 rounded border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] bg-[var(--nq-st-ok-soft)] p-4">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-st-ok-ink)]">
                          Trích Đoạn Nội Dung Gốc
                        </h4>
                        <p className="text-sm leading-relaxed text-[var(--nq-primary)] italic">
                          &quot;{selectedTrend.trich_doan_noi_dung_that}&quot;
                        </p>
                      </div>
                    )}

                    {/* Ngữ Cảnh Sử Dụng & Gợi Ý Cho Quán */}
                    <div className="space-y-1 rounded border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))] bg-[var(--nq-st-info-soft)] p-4">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-st-info-ink)]">
                        Ngữ Cảnh Sử Dụng & Kế Hoạch Áp Dụng Cho Quán
                      </h4>
                      <p className="text-sm leading-relaxed text-[var(--nq-primary)]">
                        {selectedTrend.ngu_canh_su_dung}
                      </p>
                    </div>

                    {/* Tâm lý khách hàng */}
                    <div className="space-y-1 rounded border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))] bg-[var(--nq-st-info-soft)] p-4">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--nq-st-info-ink)]">
                        Giải Mã Tâm Lý Khách Hàng / Giới Trẻ
                      </h4>
                      <p className="text-sm leading-relaxed text-[var(--nq-primary)]">
                        {selectedTrend.tam_ly_gioi_tre}
                      </p>
                    </div>

                    {/* Nút hành động trực tiếp */}
                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--nq-dim)] pt-4">
                      <div className="flex items-center gap-1.5 text-xs text-[var(--nq-muted)]">
                        <span>Nguồn gốc:</span>
                        <strong className="text-[var(--nq-st-ok-ink)] font-bold bg-[var(--nq-st-ok-soft)] px-2 py-0.5 rounded">
                          {selectedTrend.nen_tang_lan_toa?.[0] || (selectedTrend.nguon_goc === "threads_vn" ? "Meta Threads" : "TikTok Việt Nam")}
                        </strong>
                      </div>

                      {selectedTrend.link_goc && (
                        <a
                          href={selectedTrend.link_goc}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded bg-[var(--nq-surface)] px-3 py-1.5 text-xs font-bold text-[var(--nq-primary)] border border-[var(--nq-dim)] hover:bg-[var(--nq-dim)] transition"
                        >
                          Mở Link Bài Gốc ↗
                        </a>
                      )}
                    </div>
                  </>
                ) : (
                  <Empty>Chọn một xu hướng đã lưu ở danh sách bên trái để xem chi tiết.</Empty>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: HỘI THOẠI MESSENGER */}
      {tab === "threads" && (
        <div className="space-y-4">
          {/* Thanh trạng thái kết nối + bộ lọc */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border-2 border-[var(--nq-dim)] bg-[var(--nq-surface-hi)] px-4 py-3">
            <div className="flex items-center gap-3">
              <span
                className={`inline-block h-2.5 w-2.5 rounded-full ${
                  connected ? "bg-[var(--nq-st-ok)]" : "bg-[var(--nq-danger)]"
                }`}
                aria-hidden="true"
              />
              <span className="text-sm font-bold text-[var(--nq-primary)]">
                {connected ? `Đã nối ${status?.page_name || "Messenger"}` : "Chưa nối Fanpage"}
              </span>
              {connected ? (
                <span className="hidden sm:inline-block rounded border border-[color-mix(in_srgb,var(--nq-st-ok)_30%,transparent)] bg-[var(--nq-st-ok-soft)] px-2 py-0.5 text-[11px] font-mono text-[var(--nq-st-ok-ink)]">
                  {threads.filter((t) => t.needs_action || t.pending_approval).length} cần xử lý
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-lg border border-[var(--nq-dim)] overflow-hidden text-xs">
                {(
                  [
                    { id: "all", label: "Tất cả" },
                    { id: "needs_action", label: "Cần xử lý" },
                    { id: "within_24h", label: "Trong 24h" },
                  ] as const
                ).map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setThreadFilter(f.id)}
                    className={`px-3 py-1.5 font-bold transition cursor-pointer ${
                      threadFilter === f.id
                        ? "bg-[var(--nq-accent)] text-[var(--nq-accent-ink)]"
                        : "text-[var(--nq-muted)] hover:bg-[var(--nq-dim)] hover:text-white"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <Btn variant="ghost" onClick={load}>
                Làm mới
              </Btn>
            </div>
          </div>

          {filteredThreads.length === 0 ? (
            <Empty title="Chưa có hội thoại">
              {connected
                ? "Không có hội thoại nào khớp bộ lọc. Bấm Làm mới để đồng bộ tin mới từ Messenger."
                : "Chưa nối Fanpage nên chưa có tin nhắn. Xem hướng dẫn kết nối trong docs/runbooks/facebook-page-connect.md."}
            </Empty>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* CỘT TRÁI: DANH SÁCH HỘI THOẠI */}
              <div
                className={`${
                  activeThread ? "hidden lg:flex" : "flex"
                } lg:col-span-4 flex-col rounded-lg border-2 border-[var(--nq-dim)] bg-[var(--nq-surface)] overflow-hidden max-h-[70vh]`}
              >
                <div className="flex items-center justify-between border-b border-[var(--nq-dim)] bg-[var(--nq-surface-hi)] px-4 py-3">
                  <span className="text-xs font-bold uppercase tracking-widest text-[var(--nq-accent)]">
                    Hội thoại ({filteredThreads.length})
                  </span>
                  <span className="text-[11px] font-mono text-[var(--nq-muted)]">
                    {threads.filter((t) => t.is_within_24h).length} trong 24h
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto divide-y divide-[var(--nq-dim)]/40">
                  {filteredThreads.map((th) => {
                    const isActive = activeThread?.id === th.id;
                    const { fallback, src } = avatarFor(th);
                    const lastMsg = (th.replies && th.replies[th.replies.length - 1]) || null;
                    const isCustLastMsg = lastMsg ? isCustomerMsg(th, lastMsg) : true;
                    return (
                      <button
                        key={th.id}
                        type="button"
                        onClick={() => setActiveThreadId(th.id)}
                        className={`w-full flex items-start gap-3 px-4 py-3 text-left transition cursor-pointer ${
                          isActive
                            ? "bg-[var(--nq-accent-soft)] border-l-4 border-[var(--nq-accent)]"
                            : "hover:bg-[var(--nq-bg)] border-l-4 border-transparent"
                        }`}
                      >
                        {/* Avatar */}
                        <span className="relative shrink-0">
                          {src ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={src}
                              alt=""
                              className="w-11 h-11 rounded-full object-cover border border-[var(--nq-dim)]"
                              loading="lazy"
                            />
                          ) : (
                            <span className="w-11 h-11 rounded-full bg-[var(--nq-accent)] text-[var(--nq-accent-ink)] font-semibold flex items-center justify-center text-base border border-[var(--nq-accent-dim)]">
                              {fallback}
                            </span>
                          )}
                          {(th.needs_action || th.pending_approval) && (
                            <span
                              className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-[var(--nq-accent)] border-2 border-[var(--nq-surface)]"
                              title="Cần xử lý"
                              aria-label="Cần xử lý"
                            />
                          )}
                        </span>

                        {/* Tên + tin cuối */}
                        <span className="flex-1 min-w-0">
                          <span className="flex items-center justify-between gap-1">
                            <span className="font-bold text-xs text-[var(--nq-fg)] truncate">
                              {th.sender_name}
                            </span>
                            <span className="shrink-0 text-[10px] font-mono text-[var(--nq-muted)]">
                              {threadTime(th)}
                            </span>
                          </span>
                          <span className="flex items-center gap-1.5 mt-0.5">
                            {th.customer_profile?.is_vip_or_regular && (
                              <span className="rounded-full bg-amber-500/20 px-1.5 py-px text-[9px] font-bold text-amber-300 border border-amber-500/40 whitespace-nowrap">
                                Quen · {th.customer_profile.visit_count}
                              </span>
                            )}
                            <span className="text-[11px] text-[var(--nq-muted)] truncate leading-tight">
                              {th.tom_tat || (lastMsg ? lastMsg.text : "")}
                            </span>
                          </span>
                          <span className="flex items-center gap-1.5 mt-1">
                            {th.is_within_24h ? (
                              <span className="text-[10px] font-mono text-[var(--nq-st-ok-ink)]/90">● trong 24h</span>
                            ) : (
                              <span className="text-[10px] font-mono text-[var(--nq-muted)]">hết 24h — cần tag</span>
                            )}
                            {th.intent ? (
                              <span className="rounded bg-[var(--nq-dim)]/50 px-1.5 py-px text-[9px] text-[var(--nq-primary)]">
                                {th.intent.replace(/_/g, " ")}
                              </span>
                            ) : null}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* CỘT PHẢI: KHUNG HỘI THOẠI CHI TIẾT */}
              {activeThread ? (
                <div className={`${activeThread ? "flex" : "hidden"} lg:col-span-8 lg:flex flex-col rounded-lg border-2 border-[var(--nq-dim)] bg-[var(--nq-bg)] overflow-hidden max-h-[70vh]`}>
                  {/* Header hội thoại */}
                  <div className="flex items-center gap-3 border-b border-[var(--nq-dim)] bg-[var(--nq-surface-hi)] px-4 py-3">
                    <button
                      type="button"
                      onClick={() => setActiveThreadId(null)}
                      className="lg:hidden shrink-0 rounded border border-[var(--nq-dim)] px-2 py-1 text-xs font-bold text-[var(--nq-muted)] hover:bg-[var(--nq-dim)] hover:text-white transition cursor-pointer"
                      aria-label="Quay lại danh sách"
                    >
                      ← Quay lại
                    </button>
                    {(() => {
                      const { fallback, src } = avatarFor(activeThread);
                      return src ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={src}
                          alt=""
                          className="w-10 h-10 rounded-full object-cover border border-[var(--nq-dim)]"
                        />
                      ) : (
                        <span className="w-10 h-10 rounded-full bg-[var(--nq-accent)] text-[var(--nq-accent-ink)] font-semibold flex items-center justify-center text-sm">
                          {fallback}
                        </span>
                      );
                    })()}
                    <div className="flex-1 min-w-0">
                      <h3 className="font-bold text-sm text-[var(--nq-fg)] truncate">{activeThread.sender_name}</h3>
                      <p className="text-[11px] text-[var(--nq-muted)] truncate">
                        {activeThread.customer_profile?.ten_khach
                          ? `Hồ sơ: ${activeThread.customer_profile.ten_khach}`
                          : activeThread.psid
                          ? `PSID ····${activeThread.psid.slice(-4)}`
                          : activeThread.id}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-bold border ${
                        activeThread.is_within_24h
                          ? "bg-[var(--nq-st-ok-soft)] text-[var(--nq-st-ok-ink)] border-[color-mix(in_srgb,var(--nq-st-ok)_30%,transparent)]"
                          : "bg-[var(--nq-st-warn-soft)] text-[var(--nq-st-warn-ink)] border-[color-mix(in_srgb,var(--nq-st-warn)_30%,transparent)]"
                      }`}
                    >
                      {activeThread.is_within_24h ? "Trong 24h" : "Hết 24h · tag"}
                    </span>
                    {(activeThread.needs_action || activeThread.pending_approval) && (
                      <span className="shrink-0 rounded-full bg-[var(--nq-accent)] text-[var(--nq-accent-ink)] px-2.5 py-1 text-[10px] font-bold">
                        Cần xử lý
                      </span>
                    )}
                  </div>

                  {/* Hồ sơ khách gọn (khách quen / món quen / lưu ý) */}
                  {activeThread.customer_profile &&
                    (activeThread.customer_profile.is_vip_or_regular ||
                      (activeThread.customer_profile.favorite_drinks || []).length > 0 ||
                      (activeThread.customer_profile.special_notes || []).length > 0) && (
                      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--nq-dim)] bg-[var(--nq-surface)] px-4 py-2">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--nq-accent)]">
                          Hồ sơ khách
                        </span>
                        {activeThread.customer_profile.is_vip_or_regular && (
                          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300 border border-amber-500/40">
                            Khách quen · {activeThread.customer_profile.visit_count} lần
                          </span>
                        )}
                        {(activeThread.customer_profile.favorite_drinks || []).map((d) => (
                          /* "Món ruột" là THÔNG TIN (không phải cảnh báo, không phải lỗi)
                             → dùng hệ token info (accent-2) qua .nq-badge, không màu rời.
                             Icon SVG thay emoji ☕: emoji do hệ điều hành vẽ nên hình
                             khác nhau trên từng máy và không ăn màu trạng thái. */
                          <span key={d} className="nq-badge nq-badge--info nq-badge--sm">
                            <Icon name="coffee" size={12} />
                            {d}
                          </span>                        ))}
                        {(activeThread.customer_profile.special_notes || []).map((n) => (
                          /* "Lưu ý đặc biệt" cần phân biệt được với "món ruột" → dùng
                             hệ accent (thương hiệu) thay vì xanh dương. */
                          <span key={n} className="nq-badge nq-badge--primary nq-badge--sm">
                            {n}
                          </span>
                        ))}
                      </div>
                    )}

                  {/* Chuỗi tin nhắn */}
                  <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {(activeThread.replies ?? []).map((m) => {
                      const fromCustomer = isCustomerMsg(activeThread, m);
                      return (
                        <div
                          key={m.id || `${m.at}-${m.text}-${m.by}`}
                          className={`flex items-end gap-2 ${fromCustomer ? "" : "flex-row-reverse"}`}
                        >
                          {fromCustomer ? (
                            (() => {
                              const { fallback, src } = avatarFor(activeThread);
                              return src ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img
                                  src={src}
                                  alt=""
                                  className="w-7 h-7 rounded-full object-cover border border-[var(--nq-dim)] shrink-0"
                                />
                              ) : (
                                <span className="w-7 h-7 rounded-full bg-[var(--nq-accent)] text-[var(--nq-accent-ink)] font-bold text-[10px] flex items-center justify-center shrink-0">
                                  {fallback}
                                </span>
                              );
                            })()
                          ) : null}
                          <div
                            className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-xs leading-relaxed shadow-sm ${
                              fromCustomer
                                ? "bg-[var(--nq-surface)] border border-[var(--nq-dim)] text-[var(--nq-fg)] rounded-bl-sm"
                                : "bg-[var(--nq-accent)] text-[var(--nq-accent-ink)] rounded-br-sm font-medium"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-3 mb-0.5">
                              <span
                                className={`text-[9px] font-bold uppercase tracking-wider ${
                                  fromCustomer ? "text-[var(--nq-accent)]" : "text-[var(--nq-accent-ink)]/70"
                                }`}
                              >
                                {fromCustomer ? activeThread.sender_name : m.by || "Quán"}
                              </span>
                              {m.at ? (
                                <span
                                  className={`text-[9px] font-mono ${
                                    fromCustomer ? "text-[var(--nq-dim)]" : "text-[var(--nq-accent-ink)]/60"
                                  }`}
                                >
                                  {(() => {
                                    const raw = String(m.at || "");
                                    const t = new Date(raw.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`);
                                    return Number.isNaN(t.getTime())
                                      ? ""
                                      : t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                                  })()}
                                </span>
                              ) : null}
                            </div>
                            <p className="whitespace-pre-wrap break-words">{m.text}</p>
                            {m.mock ? (
                              <span className="block mt-1 text-[9px] font-mono opacity-60 italic">(mock — replay)</span>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Gợi ý trả lời của AI */}
                  {activeThread.suggested_reply ? (
                    <div className="border-t border-[var(--nq-dim)] bg-[var(--nq-surface-hi)] px-4 py-3">
                      <div className="flex items-start gap-2.5">
                        {/* Nhãn "AI" đánh dấu nội dung do máy soạn — phải KHÁC hệ màu
                            với nội dung người gửi (accent = thương hiệu/người gửi),
                            nên dùng hệ info (accent-2). */}
                        <span className="mt-0.5 shrink-0 nq-badge nq-badge--info nq-badge--xs">
                          AI
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-[11px] text-[var(--nq-primary)] leading-relaxed">
                            {activeThread.suggested_reply}
                          </p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <Btn
                              variant="primary"
                              busy={sendingReplyId === activeThread.id}
                              onClick={() => approveSuggestion(activeThread)}
                            >
                              Duyệt & gửi
                            </Btn>
                            <Btn
                              variant="ghost"
                              onClick={() => setReplyDraft((d) => ({ ...d, [activeThread.id]: activeThread.suggested_reply || "" }))}
                            >
                              Chỉnh trước khi gửi
                            </Btn>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {/* Hộp soạn trả lời */}
                  <div className="flex items-end gap-2 border-t border-[var(--nq-dim)] bg-[var(--nq-surface-hi)] px-4 py-3">
                    <textarea
                      rows={2}
                      className="nq-input flex-1 resize-none text-xs"
                      placeholder="Nhập nội dung trả lời cho khách…"
                      value={replyDraft[activeThread.id] ?? ""}
                      onChange={(e) => setReplyDraft({ ...replyDraft, [activeThread.id]: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          reply(activeThread.id);
                        }
                      }}
                    />
                    <Btn
                      variant="primary"
                      disabled={!String(replyDraft[activeThread.id] ?? "").trim()}
                      busy={sendingReplyId === activeThread.id}
                      onClick={() => reply(activeThread.id)}
                    >
                      Gửi
                    </Btn>
                    {!activeThread.is_within_24h ? (
                      <span
                        className="hidden md:inline-block max-w-[140px] text-[10px] leading-tight text-[var(--nq-muted)]"
                        title="Gửi ngoài 24h sẽ tự gắn tag CONFIRMED_EVENT_UPDATE trên Messenger"
                      >
                        Hết 24h — hệ thống tự gắn tag khi gửi
                      </span>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="hidden lg:block lg:col-span-8">
                  <Empty title="Chọn hội thoại">
                    Chọn một hội thoại bên trái để đọc tin nhắn và trả lời khách.
                  </Empty>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: NHÁP BÀI FANPAGE */}
      {tab === "drafts" && (
        <div className="space-y-4">
          {/* AI Auto-generator Box */}
          <div className="border-2 border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))] bg-gradient-to-r from-[var(--nq-st-info)] to-[var(--nq-st-info)] p-4 rounded shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-[var(--nq-st-info-ink)] flex items-center gap-2">
                AI Tự Động Soạn Thảo Bài Đăng (Gemini AI)
              </h3>
              <span className="text-xs text-[var(--nq-muted)] bg-[var(--nq-st-info-soft)] px-2 py-0.5 rounded border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))]">
                Tự động chuẩn hóa văn phong, emoji & Call-To-Action
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              <div className="md:col-span-2">
                <Field label="Chủ đề / Ý tưởng bài viết">
                  <Input
                    placeholder="VD: Cà phê trứng mùa thu, Khuyến mãi combo sáng, Bắt trend matcha..."
                    value={aiTopic}
                    onChange={(e) => setAiTopic(e.target.value)}
                  />
                </Field>
              </div>
              <div>
                <Field label="Giọng điệu">
                  <select
                    className="w-full bg-[var(--nq-bg)] border border-[var(--nq-dim)] text-xs text-[var(--nq-primary)] p-2 rounded"
                    value={aiTone}
                    onChange={(e) => setAiTone(e.target.value)}
                  >
                    <option value="than thien">Thân thiện, gần gũi</option>
                    <option value="truyen cam hung">Truyền cảm hứng, nghệ thuật</option>
                    <option value="hai huoc">Hài hước, Gen Z, bắt trend</option>
                    <option value="trang trong">Trang trọng, thông báo</option>
                  </select>
                </Field>
              </div>
            </div>
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
              <div className="flex flex-wrap gap-1.5 text-xs items-center">
                <span className="text-[var(--nq-muted)] mr-1">Gợi ý nhanh:</span>
                {[
                  "Cà phê specialty rang xay",
                  "Combo bánh ngọt & trà thơm",
                  "Không gian yên tĩnh làm việc",
                  "Khuyến mãi cuối tuần",
                ].map((sug) => (
                  <button
                    key={sug}
                    type="button"
                    onClick={() => setAiTopic(sug)}
                    className="px-2 py-0.5 bg-[var(--nq-dim)]/60 hover:bg-[var(--nq-st-info-soft)] text-[var(--nq-muted)] hover:text-[var(--nq-st-info-ink)] rounded text-xs transition-colors"
                  >
                    + {sug}
                  </button>
                ))}
              </div>
              <Btn
                variant="primary"
                onClick={() => generateAiDraft()}
                disabled={aiGenerating || !aiTopic.trim()}
                className="bg-[var(--nq-st-info)] hover:bg-[var(--nq-st-info)] text-[var(--nq-accent-ink)] font-semibold"
              >
                {aiGenerating ? "Đang sinh bài..." : "AI Soạn & Thêm Nháp"}
              </Btn>
            </div>
          </div>

          <div className="nq-surface-block p-4">
            <h3 className="mb-2 text-sm font-bold">Soạn nháp bài đăng thủ công</h3>
            <Field label="Nội dung bài đăng">
              <Textarea
                rows={4}
                placeholder="Nhập nội dung bài đăng nếu muốn tự viết..."
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
              />
            </Field>
            <Btn variant="primary" onClick={createDraft}>
              Lưu nháp
            </Btn>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-bold">Danh sách nháp bài ({drafts.length})</h3>
            {drafts.length === 0 ? (
              <Empty>Chưa có bài nháp nào.</Empty>
            ) : (
              drafts.map((d: any) => (
                <div key={d.id} className="border border-[var(--nq-dim)] p-3 rounded">
                  <div className="flex items-center justify-between text-xs text-[var(--nq-muted)]">
                    <span>Người tạo: <strong className="text-[var(--nq-primary)]">{d.nguoi_tao || d.by || "Hệ thống"}</strong></span>
                    <span className="px-2 py-0.5 rounded bg-[var(--nq-dim)]/40 font-mono text-2xs">
                      {d.trang_thai === "da_dang" ? "Đã đăng live" : d.trang_thai === "da_dang_mock" ? "Đã đăng (Mock)" : d.trang_thai === "da_duyet" ? "Đã duyệt" : d.trang_thai === "tu_choi" ? "Đã từ chối" : "Chờ duyệt"}
                    </span>
                  </div>
                  <p className="my-2 text-xs text-[var(--nq-primary)] whitespace-pre-line leading-relaxed border-l-2 border-[var(--nq-line-strong)] pl-3 py-1">
                    {d.noi_dung}
                  </p>
                  {manager && (d.trang_thai === "cho_duyet" || d.trang_thai === "nhap") ? (
                    <div className="flex gap-2 pt-2 border-t border-[var(--nq-dim)]/50">
                      <Btn variant="primary" onClick={() => decideDraft(d.id, "duyet")}>
                        Duyệt & Đăng
                      </Btn>
                      <Btn variant="ghost" onClick={() => decideDraft(d.id, "tu_choi")}>
                        Từ chối
                      </Btn>
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* TAB 4: CẤU HÌNH THÔNG TIN QUÁN */}
      {tab === "config" && manager && (
        <div className="nq-surface-block space-y-4 p-4">
          <h3 className="text-sm font-bold">Cấu hình thông tin trả lời khách</h3>
          <p className="text-xs text-[var(--nq-muted)]">
            Trường nào trống thì bot trả “chưa cập nhật” — thay vì đoán. Bạn cũng
            có thể sửa đầy đủ hơn tại trang &nbsp;
            <Link href="/cau-hinh-quan" className="text-[var(--nq-copper)] underline">
              Cấu hình quán & AI
            </Link>
            .
          </p>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="text-xs text-[var(--nq-muted)]">Tên quán</label>
              <input
                type="text"
                className="nq-input w-full text-xs"
                value={profile?.ten_quan ?? ""}
                onChange={(e) => setProfile((p) => (p ? { ...p, ten_quan: e.target.value } : null))}
              />
            </div>
            <div>
              <label className="text-xs text-[var(--nq-muted)]">Địa chỉ</label>
              <input
                type="text"
                className="nq-input w-full text-xs"
                value={profile?.dia_chi ?? ""}
                onChange={(e) => setProfile((p) => (p ? { ...p, dia_chi: e.target.value } : null))}
              />
            </div>
            <div>
              <label className="text-xs text-[var(--nq-muted)]">Số điện thoại</label>
              <input
                type="text"
                className="nq-input w-full text-xs"
                value={profile?.hotline ?? ""}
                onChange={(e) => setProfile((p) => (p ? { ...p, hotline: e.target.value } : null))}
              />
            </div>
            <div>
              <label className="text-xs text-[var(--nq-muted)]">Giờ mở cửa</label>
              <input
                type="text"
                className="nq-input w-full text-xs"
                value={profile?.gio_mo_cua ?? ""}
                onChange={(e) => setProfile((p) => (p ? { ...p, gio_mo_cua: e.target.value } : null))}
              />
            </div>
          </div>
          <Btn variant="primary" onClick={saveProfile}>
            Lưu cấu hình
          </Btn>
        </div>
      )}

      {/* TAB 5: BÁO CÁO TỰ ĐÁNH GIÁ & TIẾN HÓA CSKH (AI REFLECTION) */}
      {tab === "reflection" && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))] bg-[var(--nq-st-info-soft)] p-4">
            <div>
              <h2 className="text-base font-bold text-[var(--nq-st-info-ink)] flex items-center gap-2">
                Báo Cáo Tự Đánh Giá & Tiến Hóa CSKH (Nightly Reflection)
              </h2>
              <p className="text-xs text-[var(--nq-st-info-ink)] mt-1">
                AG-SUPERVISOR tự động soi lại toàn bộ hội thoại của quán, chấm điểm chất lượng và đề xuất luật mới vào Cẩm nang.
              </p>
            </div>
            <Btn
              variant="primary"
              disabled={reflectionLoading}
              onClick={triggerReflection}
              className="bg-[var(--nq-st-info)] hover:bg-[var(--nq-st-info)] font-semibold text-[var(--nq-accent-ink)]"
            >
              {reflectionLoading ? "Đang phân tích..." : "Chạy Tự Đánh Giá Ngay"}
            </Btn>
          </div>

          {reflectionLoading && !reflectionReport && (
            <Loading skeleton="list">Đang phân tích dữ liệu hội thoại CSKH...</Loading>
          )}

          {reflectionReport && (
            <div className="space-y-6">
              {/* Metrics Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="rounded-xl border border-[var(--nq-dim)] bg-[var(--nq-surface)] p-4 text-center">
                  <span className="text-xs text-[var(--nq-muted)] block mb-1">Điểm Hài Lòng (CSAT Dự Đoán)</span>
                  <div className="text-3xl font-semibold text-[var(--nq-st-warn-ink)] flex items-center justify-center gap-1">
                    <span>{reflectionReport.csat_score}</span>
                    <span className="text-base text-[var(--nq-st-warn-ink)]">/ 10.0</span>
                  </div>
                </div>

                <div className="rounded-xl border border-[var(--nq-dim)] bg-[var(--nq-surface)] p-4 text-center">
                  <span className="text-xs text-[var(--nq-muted)] block mb-1">Tuân Thủ Chuẩn H.E.A.R</span>
                  <div className="text-3xl font-semibold text-[var(--nq-st-ok-ink)]">
                    {reflectionReport.hear_compliance_rate}%
                  </div>
                  <span className="text-2xs text-[var(--nq-muted)] block mt-1">Xin lỗi - Lấy SĐT - Quản lý gọi lại</span>
                </div>

                <div className="rounded-xl border border-[var(--nq-dim)] bg-[var(--nq-surface)] p-4 text-center">
                  <span className="text-xs text-[var(--nq-muted)] block mb-1">Tổng Cuộc Hội Thoại</span>
                  <div className="text-3xl font-semibold text-[var(--nq-st-info-ink)]">
                    {reflectionReport.total_conversations}
                  </div>
                  <span className="text-2xs text-[var(--nq-muted)] block mt-1">
                    Tích cực: {reflectionReport.sentiment_breakdown?.positive || 0} · Cần cải thiện:{" "}
                    {reflectionReport.sentiment_breakdown?.negative || 0}
                  </span>
                </div>
              </div>

              {/* Recommendations */}
              <div className="rounded-xl border border-[var(--nq-dim)] bg-[var(--nq-surface)] p-4 space-y-2">
                <h3 className="text-xs font-bold text-[var(--nq-st-warn-ink)] uppercase tracking-wider flex items-center gap-1.5">
                  Bài Học & Khuyến Nghị Tự Hoàn Thiện
                </h3>
                <ul className="space-y-1.5 text-xs text-[var(--nq-primary)]">
                  {reflectionReport.learning_recommendations?.map((rec: string, idx: number) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-[var(--nq-st-warn-ink)] font-bold">•</span>
                      <span>{rec}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Unresolved Inquiries (Lỗ hổng tri thức) */}
              {reflectionReport.unresolved_inquiries && reflectionReport.unresolved_inquiries.length > 0 && (
                <div className="rounded-xl border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] bg-[var(--nq-st-danger-soft)] p-4 space-y-3">
                  <h3 className="text-xs font-bold text-[var(--nq-st-danger-ink)] uppercase tracking-wider flex items-center gap-1.5">
                    Câu Hỏi Khách Hỏi Nhiều Mà Quán Chưa Có Dữ Liệu
                  </h3>
                  <div className="space-y-2">
                    {reflectionReport.unresolved_inquiries.map((un: any, idx: number) => (
                      <div key={idx} className="rounded-lg border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] bg-[var(--nq-bg)] p-3 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-[var(--nq-st-danger-ink)]">{un.title}</span>
                          <span className="rounded-full bg-[var(--nq-st-danger-soft)] px-2 py-0.5 text-2xs font-bold text-[var(--nq-st-danger-ink)] border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))]">
                            {un.count} lượt hỏi
                          </span>
                        </div>
                        {un.sample_questions && un.sample_questions.length > 0 && (
                          <div className="mt-2 text-2xs text-[var(--nq-ink-muted)] italic">
                            &quot;{un.sample_questions[0]}&quot;
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Playbook Rule Proposals */}
              {reflectionReport.playbook_rule_proposals && reflectionReport.playbook_rule_proposals.length > 0 && (
                <div className="rounded-xl border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))] bg-[var(--nq-st-info-soft)] p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-[var(--nq-st-info-ink)] uppercase tracking-wider flex items-center gap-1.5">
                      Đề Xuất Cập Nhật Cẩm Nang Quán (1-Click Apply)
                    </h3>
                  </div>
                  <div className="space-y-3">
                    {reflectionReport.playbook_rule_proposals.map((p: any) => (
                      <div
                        key={p.proposal_id}
                        className="rounded-lg border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))] bg-[var(--nq-bg)] p-3.5 space-y-2 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-[var(--nq-st-info-ink)]">{p.title}</span>
                          {p.status === "da_ap_dung" ? (
                            <span className="text-2xs text-[var(--nq-st-ok-ink)] font-bold">Đã thêm vào cẩm nang</span>
                          ) : (
                            <Btn
                              variant="ghost"
                              onClick={() => applyRuleProposal(p)}
                              className="text-2xs text-[var(--nq-st-info-ink)] hover:bg-[var(--nq-st-info-soft)] border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))] px-2 py-1"
                            >
                              Thêm vào Cẩm Nang
                            </Btn>
                          )}
                        </div>
                        <p className="text-2xs text-[var(--nq-ink)] leading-relaxed bg-[var(--nq-bg-elevated)] p-2 rounded border border-[var(--nq-line)]">
                          {p.suggested_rule}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
