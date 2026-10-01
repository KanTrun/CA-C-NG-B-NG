"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, apiGet, apiSend } from "../../lib/api";
import { formatRelativeTime } from "../../lib/date";
import { loiKetNoiGmail, loiOAuthGmail, viError } from "../../lib/present";
import { getRole, getToken, isChuQuan } from "../../lib/session";
import { Icon } from "../../ui/icons";
import {
  Alert,
  AuthGate,
  Badge,
  Btn,
  ConfirmDialog,
  Empty,
  Input,
  Loading,
  Notice,
  OpsCard,
  PageHeader,
  Select,
  StatusChip,
  TabBar,
  TabButton,
  Table,
  Tooltip,
} from "../../ui/kit";
import { fieldLabel, formatFieldValue } from "../../lib/labels";
import { useStaffNameMap } from "../../ui/ops-pickers";

function objectChips(value: unknown): ReactNode {
  if (value == null || value === "") return "—";
  if (typeof value !== "object") return <StatusChip>{String(value)}</StatusChip>;
  const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return "—";
  return (
    <span className="flex flex-wrap gap-1.5">
      {entries.map(([k, v]) => (
        <StatusChip key={k} tone="info">
          {fieldLabel(k)}: {formatFieldValue(v)}
        </StatusChip>
      ))}
    </span>
  );
}

type GmailAccount = {
  id: string;
  store_id: string;
  nv_id: string;
  email: string;
  display_name: string;
  is_primary: boolean;
  is_active: boolean;
  has_tokens?: boolean;
  token_expires_at?: string | null;
  token_broken?: boolean;
  sync_state?: GmailSyncState | null;
  created_at: string;
  updated_at: string;
};

type GmailSyncState = {
  account_id: string;
  last_history_id: string | null;
  last_sync_at: string | null;
  sync_cursor: string | null;
  total_messages: number;
  unread_count: number;
  updated_at: string;
};

type GmailMessage = {
  id: string;
  account_id: string;
  thread_id: string;
  label_ids: string[];
  snippet: string;
  from_email: string;
  to_emails: string[];
  cc_emails: string[];
  subject: string;
  internal_date: string;
  is_read: boolean;
  is_starred: boolean;
  has_attachment: boolean;
};

type GmailLabel = {
  id: string;
  account_id: string;
  name: string;
  label_type: string;
  message_list_visibility: string;
  label_list_visibility: string;
  color_background: string | null;
  color_text: string | null;
  total_messages: number;
  unread_messages: number;
};

type GmailFilter = {
  id: string;
  account_id: string;
  criteria: Record<string, unknown>;
  action: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type TabId = "accounts" | "messages" | "labels" | "filters" | "sync";

const TABS: { id: TabId; label: string }[] = [
  { id: "accounts", label: "Tài khoản" },
  { id: "messages", label: "Hộp thư" },
  { id: "labels", label: "Nhãn" },
  { id: "filters", label: "Bộ lọc" },
  { id: "sync", label: "Đồng bộ" },
];

const PAGE_SIZE = 50;

/**
 * Màu chấm phân biệt các hộp thư — một màu cho một địa chỉ Gmail.
 *
 * Vì sao cần: chủ quán theo dõi NHIỀU mail trong cùng một trang. Chấm màu
 * + địa chỉ email luôn đi cùng nhau (bảng tài khoản, hộp chọn, tiêu đề hộp
 * thư) để mắt không lẫn mail của hộp này sang hộp khác.
 *
 * KHÔNG `export`: Next.js App Router chỉ cho phép export mặc định + các field
 * quy ước (metadata…) ở file page — export helper sẽ làm `next build` đỏ với
 * lỗi `"accountColor" is not a valid Page export field`.
 */
function accountColor(email: unknown): string {
  const raw = typeof email === "string" ? email : "";
  let hue = 0;
  for (let i = 0; i < raw.length; i += 1) hue = (hue * 31 + raw.charCodeAt(i)) % 360;
  return `hsl(${hue} 70% 62%)`;
}

export default function GmailPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = (searchParams.get("tab") as TabId) || "accounts";
  const accountId = searchParams.get("account_id") || "";
  const staffName = useStaffNameMap();

  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [accounts, setAccounts] = useState<GmailAccount[]>([]);
  const [account, setAccount] = useState<GmailAccount | null>(null);
  const [messages, setMessages] = useState<GmailMessage[]>([]);
  const [labels, setLabels] = useState<GmailLabel[]>([]);
  const [filters, setFilters] = useState<GmailFilter[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [showAddForm, setShowAddForm] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const [messageQuery, setMessageQuery] = useState("");
  const [messageReadFilter, setMessageReadFilter] = useState("");
  const [messageLimit, setMessageLimit] = useState(PAGE_SIZE);

  const [labelName, setLabelName] = useState("");
  const [filterCriteria, setFilterCriteria] = useState("");
  const [filterAction, setFilterAction] = useState("");

  useEffect(() => {
    setToken(getToken());
    setRole(getRole());
  }, []);

  const navigate = useCallback(
    (tab: TabId, nextAccountId = accountId) => {
      const query = nextAccountId ? `?tab=${tab}&account_id=${nextAccountId}` : `?tab=${tab}`;
      router.push(`/gmail${query}`);
    },
    [accountId, router],
  );

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ accounts: GmailAccount[] }>("/api/v1/gmail/accounts");
      setAccounts(res.accounts ?? []);
      setError(null);
    } catch (cause) {
      setError(viError(cause, { doing: "đọc danh sách tài khoản Gmail" }));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAccountDetail = useCallback(
    async (id: string) => {
      setLoading(true);
      try {
        const [accountRes, messageRes, labelRes, filterRes] = await Promise.all([
          apiGet<GmailAccount>(`/api/v1/gmail/accounts/${id}`),
          apiGet<{ messages: GmailMessage[] }>(
            `/api/v1/gmail/accounts/${id}/messages?limit=${messageLimit}` +
              (messageQuery ? `&query=${encodeURIComponent(messageQuery)}` : "") +
              (messageReadFilter ? `&is_read=${messageReadFilter}` : ""),
          ),
          apiGet<{ labels: GmailLabel[] }>(`/api/v1/gmail/accounts/${id}/labels`),
          apiGet<{ filters: GmailFilter[] }>(`/api/v1/gmail/accounts/${id}/filters`),
        ]);
        setAccount(accountRes);
        setMessages(messageRes.messages ?? []);
        setLabels(labelRes.labels ?? []);
        setFilters(filterRes.filters ?? []);
        setError(null);
      } catch (cause) {
        setError(viError(cause, { doing: "đọc chi tiết tài khoản Gmail" }));
      } finally {
        setLoading(false);
      }
    },
    [messageLimit, messageQuery, messageReadFilter],
  );

  useEffect(() => {
    if (token) void loadAccounts();
  }, [token, loadAccounts]);

  useEffect(() => {
    if (token && accountId && activeTab !== "accounts") void loadAccountDetail(accountId);
  }, [token, accountId, activeTab, loadAccountDetail]);

  // Google redirect về /gmail?email=... hoặc ?error=... sau khi người dùng đồng ý.
  useEffect(() => {
    const connectedEmail = searchParams.get("email");
    const oauthError = searchParams.get("error");
    if (!connectedEmail && !oauthError) return;
    if (connectedEmail) {
      setNotice(`Đã kết nối Gmail: ${connectedEmail}`);
    } else if (oauthError) {
      setError(loiOAuthGmail(oauthError));
    }
    // Xoá query để thông báo không lặp lại khi tải lại trang.
    router.replace("/gmail?tab=accounts");
  }, [searchParams, router]);

  async function addAccount(e: React.FormEvent) {
    e.preventDefault();
    if (!newEmail.trim()) return;
    setBusy("add-account");
    setNotice(null);
    try {
      await apiSend("/api/v1/gmail/accounts", {
        email: newEmail.trim(),
        display_name: newName.trim(),
        is_primary: accounts.length === 0,
      });
      setNotice("Đã thêm tài khoản Gmail.");
      setNewEmail("");
      setNewName("");
      setShowAddForm(false);
      await loadAccounts();
    } catch (cause) {
      setError(viError(cause, { doing: "thêm tài khoản Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  async function connectOAuth() {
    setBusy("oauth");
    setNotice(null);
    try {
      const res = await apiGet<{ authorization_url: string }>("/api/v1/gmail/oauth/authorize");
      window.location.href = res.authorization_url;
    } catch (cause) {
      // 503 thiếu OAuth config có câu hành động riêng — không được báo thành
      // "máy chủ đang lỗi" (xem `loiKetNoiGmail`).
      setError(loiKetNoiGmail(cause) ?? viError(cause, { doing: "khởi tạo kết nối Gmail" }));
      setBusy(null);
    }
  }

  async function revokeOAuth() {
    if (!account) return;
    setBusy("revoke");
    setNotice(null);
    try {
      await apiSend(`/api/v1/gmail/oauth/revoke?account_id=${account.id}`);
      setNotice("Đã thu hồi quyền truy cập của tài khoản này.");
      await loadAccountDetail(account.id);
    } catch (cause) {
      setError(viError(cause, { doing: "thu hồi quyền Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  async function confirmDeleteAccount() {
    if (!pendingDelete) return;
    setBusy("delete");
    setNotice(null);
    try {
      await apiSend(`/api/v1/gmail/accounts/${pendingDelete}`, undefined, "DELETE");
      setNotice("Đã xoá tài khoản Gmail.");
      setPendingDelete(null);
      if (accountId === pendingDelete) navigate("accounts", "");
      await loadAccounts();
    } catch (cause) {
      setError(viError(cause, { doing: "xoá tài khoản Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  async function togglePrimary(target: GmailAccount) {
    setBusy(`primary:${target.id}`);
    setNotice(null);
    try {
      await apiSend(`/api/v1/gmail/accounts/${target.id}`, { is_primary: !target.is_primary }, "PATCH");
      setNotice(target.is_primary ? "Đã bỏ đánh dấu tài khoản chính." : "Đã đặt làm tài khoản chính.");
      await loadAccounts();
    } catch (cause) {
      setError(viError(cause, { doing: "cập nhật tài khoản Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  async function runSync(fullSync: boolean) {
    if (!account) return;
    setBusy(fullSync ? "sync-full" : "sync");
    setNotice(null);
    try {
      await apiSend("/api/v1/gmail/sync", { account_id: account.id, full_sync: fullSync });
      setNotice(fullSync ? "Đồng bộ toàn bộ hoàn tất." : "Đồng bộ thay đổi mới hoàn tất.");
      await loadAccountDetail(account.id);
    } catch (cause) {
      setError(viError(cause, { doing: "đồng bộ Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  async function toggleMessage(target: GmailMessage, action: "read" | "unread" | "star" | "unstar") {
    if (!account) return;
    setBusy(`${action}:${target.id}`);
    try {
      if (action === "read" || action === "unread") {
        await apiSend(
          `/api/v1/gmail/accounts/${account.id}/messages/${target.id}/read?is_read=${action === "read"}`,
        );
      } else {
        await apiSend(
          `/api/v1/gmail/accounts/${account.id}/messages/${target.id}/star?is_starred=${action === "star"}`,
        );
      }
      await loadAccountDetail(account.id);
    } catch (cause) {
      setError(viError(cause, { doing: "cập nhật trạng thái email" }));
    } finally {
      setBusy(null);
    }
  }

  async function createLabel(e: React.FormEvent) {
    e.preventDefault();
    if (!account || !labelName.trim()) return;
    setBusy("create-label");
    setNotice(null);
    try {
      await apiSend(`/api/v1/gmail/accounts/${account.id}/labels`, {
        name: labelName.trim(),
        label_list_visibility: "labelShow",
        message_list_visibility: "show",
      });
      setNotice("Đã tạo nhãn mới.");
      setLabelName("");
      await loadAccountDetail(account.id);
    } catch (cause) {
      setError(viError(cause, { doing: "tạo nhãn Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  async function deleteLabel(labelId: string) {
    if (!account) return;
    setBusy(`label:${labelId}`);
    setNotice(null);
    try {
      await apiSend(`/api/v1/gmail/accounts/${account.id}/labels/${labelId}`, undefined, "DELETE");
      setNotice("Đã xoá nhãn.");
      await loadAccountDetail(account.id);
    } catch (cause) {
      setError(viError(cause, { doing: "xoá nhãn Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  async function createFilter(e: React.FormEvent) {
    e.preventDefault();
    if (!account) return;
    setBusy("create-filter");
    setNotice(null);
    let criteria: Record<string, unknown>;
    let action: Record<string, unknown>;
    try {
      criteria = filterCriteria.trim() ? JSON.parse(filterCriteria) : {};
      action = filterAction.trim() ? JSON.parse(filterAction) : {};
    } catch {
      setError("Tiêu chí và hành động phải là JSON hợp lệ.");
      setBusy(null);
      return;
    }
    try {
      await apiSend(`/api/v1/gmail/accounts/${account.id}/filters`, { criteria, action });
      setNotice("Đã tạo bộ lọc mới.");
      setFilterCriteria("");
      setFilterAction("");
      await loadAccountDetail(account.id);
    } catch (cause) {
      setError(viError(cause, { doing: "tạo bộ lọc Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  async function deleteFilter(filterId: string) {
    if (!account) return;
    setBusy(`filter:${filterId}`);
    setNotice(null);
    try {
      await apiSend(`/api/v1/gmail/accounts/${account.id}/filters/${filterId}`, undefined, "DELETE");
      setNotice("Đã xoá bộ lọc.");
      await loadAccountDetail(account.id);
    } catch (cause) {
      setError(viError(cause, { doing: "xoá bộ lọc Gmail" }));
    } finally {
      setBusy(null);
    }
  }

  function openAccount(target: GmailAccount, tab: TabId = "messages") {
    navigate(tab, target.id);
  }

  if (!token) return <AuthGate />;

  // Gmail CHỈ dành cho chủ quán (AppShell cũng đã chặn ở `canAccess`, đây là
  // chốt thứ hai trong trang để không lộ cả khung UI khi gọi API trực tiếp).
  if (!isChuQuan(role)) {
    return (
      <div className="nq-page">
        <PageHeader
          kicker="Kênh liên lạc"
          title="Quản lý Gmail"
          meta="Kết nối hộp thư Gmail của quán, theo dõi email đến, quản lý nhãn và bộ lọc, và đồng bộ hộp thư theo thời gian."
        />
        <Empty title="Khu vực dành cho chủ quán">
          Chỉ chủ quán mới được thêm hộp thư Gmail và xem mail của quán. Nếu bạn cần xử lý email, nhờ chủ quán.
        </Empty>
      </div>
    );
  }

  const selectedAccount = accounts.find((a) => a.id === accountId) ?? account;

  function accountSwitcher() {
    if (activeTab === "accounts" || accounts.length === 0) return null;
    return (
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <span
          className="inline-block h-3 w-3 rounded-full"
          style={{ backgroundColor: accountColor(selectedAccount?.email) }}
          aria-hidden="true"
        />
        <Select
          value={accountId}
          onChange={(e) => navigate(activeTab, e.target.value)}
          className="w-80"
          aria-label="Chọn hộp thư Gmail đang xem"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.email}
              {typeof a.sync_state?.unread_count === "number" && a.sync_state.unread_count > 0
                ? ` · ${a.sync_state.unread_count} chưa đọc`
                : ""}
              {a.token_broken ? " · cần kết nối lại" : a.has_tokens ? "" : " · chưa kết nối"}
            </option>
          ))}
        </Select>
      </div>
    );
  }

  return (
    <div className="nq-page">
      <PageHeader
        kicker="Kênh liên lạc"
        title="Quản lý Gmail"
        meta="Kết nối hộp thư Gmail của quán, theo dõi email đến, quản lý nhãn và bộ lọc, và đồng bộ hộp thư theo thời gian."
      />

      {notice ? <Alert kind="ok">{notice}</Alert> : null}
      {error ? <Alert kind="err">{error}</Alert> : null}

      <TabBar>
        {TABS.map((tab) => (
          <TabButton
            key={tab.id}
            active={activeTab === tab.id}
            onClick={() => navigate(tab.id, accountId)}
          >
            {tab.label}
          </TabButton>
        ))}
      </TabBar>

      {activeTab === "accounts" ? (
        <section>
          <OpsCard
            eyebrow="Hộp thư Gmail"
            title="Tài khoản đã liên kết"
            count={accounts.length}
            countLabel="tài khoản"
          >
            {loading ? (
              <Loading skeleton="table" rows={3}>Đang tải tài khoản Gmail…</Loading>
            ) : accounts.length === 0 ? (
              <Empty title="Chưa có tài khoản Gmail">
                Thêm tài khoản và kết nối qua Google để hệ thống đọc được hộp thư.
              </Empty>
            ) : (
              <Table
                columns={[
                  {
                    key: "email",
                    header: "Địa chỉ Gmail",
                    render: (value, row) => (
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className="inline-block h-3 w-3 rounded-full"
                          style={{ backgroundColor: accountColor(value) }}
                          aria-hidden="true"
                        />
                        <span className="font-mono">{value}</span>
                        {row.is_primary ? <Badge variant="primary" size="sm">Chính</Badge> : null}
                        {row.token_broken ? (
                          <Badge variant="danger" size="sm">Cần kết nối lại</Badge>
                        ) : row.has_tokens ? (
                          <Badge variant="success" size="sm">Đã kết nối</Badge>
                        ) : (
                          <Badge variant="warning" size="sm">Chưa kết nối</Badge>
                        )}
                      </div>
                    ),
                  },
                  { key: "display_name", header: "Tên hiển thị" },
                  {
                    key: "nv_id",
                    header: "Nhân viên",
                    render: (value) => (value ? staffName(String(value)) : "—"),
                  },
                  {
                    key: "sync_state",
                    header: "Email chưa đọc",
                    align: "right",
                    render: (_, row) => row.sync_state?.unread_count ?? "—",
                  },
                  {
                    key: "id",
                    header: "Thao tác",
                    align: "right",
                    render: (value, row) => (
                      <div className="flex flex-nowrap items-center justify-end gap-2">
                        <Btn
                          variant="ghost"
                          className="nq-btn-compact"
                          onClick={() => openAccount(row, "messages")}
                        >
                          Mở hộp thư
                        </Btn>
                        <Btn
                          variant="ghost"
                          className="nq-btn-compact"
                          busy={busy === `primary:${value}`}
                          onClick={() => togglePrimary(row)}
                        >
                          {row.is_primary ? "Bỏ chính" : "Đặt chính"}
                        </Btn>
                        <Tooltip content="Xoá tài khoản này" position="left">
                          <Btn variant="danger" className="nq-btn-compact" onClick={() => setPendingDelete(value)}>
                            Xoá
                          </Btn>
                        </Tooltip>
                      </div>
                    ),
                  },
                ]}
                rows={accounts}
              />
            )}

            <div className="mt-6 flex flex-wrap gap-4">
              <Btn variant="ghost" onClick={() => setShowAddForm((v) => !v)}>
                {showAddForm ? "Đóng biểu mẫu" : "Thêm tài khoản"}
              </Btn>
              <Btn busy={busy === "oauth"} onClick={connectOAuth}>
                Kết nối qua Google
              </Btn>
            </div>

            {showAddForm ? (
              <form onSubmit={addAccount} className="mt-6 nq-surface-block p-6">
                <p className="nq-meta-line mb-4">
                  Ghi danh tài khoản trước, sau đó bấm &quot;Kết nối qua Google&quot; để cấp quyền đọc và gửi mail.
                </p>
                <Input
                  type="email"
                  placeholder="ten_hop_thu@gmail.com"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  required
                  className="mb-3 w-full"
                />
                <Input
                  placeholder="Tên hiển thị (không bắt buộc)"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="mb-3 w-full"
                />
                <Btn type="submit" busy={busy === "add-account"}>
                  Lưu tài khoản
                </Btn>
              </form>
            ) : null}
          </OpsCard>
        </section>
      ) : null}

      {activeTab !== "accounts" && !accountId ? (
        <Empty title="Chưa chọn tài khoản">
          Quay lại tab Tài khoản và bấm &quot;Mở hộp thư&quot; để chọn hộp thư cần xem.
        </Empty>
      ) : null}

      {activeTab === "messages" && accountId ? (
        <section>
          {accountSwitcher()}
          <OpsCard eyebrow={account?.email ?? "Hộp thư"} title="Email trong hộp thư" count={messages.length} countLabel="email">
            <div className="mb-6 flex flex-wrap items-end gap-3">
              <Input
                placeholder="Tìm theo chủ đề, người gửi hoặc nội dung"
                value={messageQuery}
                onChange={(e) => setMessageQuery(e.target.value)}
                className="w-72"
              />
              <Select
                value={messageReadFilter}
                onChange={(e) => setMessageReadFilter(e.target.value)}
                className="w-40"
              >
                <option value="">Tất cả</option>
                <option value="true">Đã đọc</option>
                <option value="false">Chưa đọc</option>
              </Select>
              <Select
                value={String(messageLimit)}
                onChange={(e) => setMessageLimit(Number(e.target.value))}
                className="w-40"
              >
                <option value="50">50 email</option>
                <option value="100">100 email</option>
                <option value="200">200 email</option>
              </Select>
            </div>

            {loading ? (
              <Loading skeleton="table" rows={5}>Đang tải hộp thư…</Loading>
            ) : messages.length === 0 ? (
              <Empty title="Không có email phù hợp">
                Thử đổi từ khoá tìm kiếm, hoặc chạy đồng bộ để lấy email mới nhất từ Google.
              </Empty>
            ) : (
              <Table
                columns={[
                  {
                    key: "is_starred",
                    header: "",
                    render: (value, row) => (
                      <Tooltip content={value ? "Bỏ gắn sao" : "Gắn sao"}>
                        <button
                          type="button"
                          className="min-h-8 min-w-8 text-[var(--nq-accent)]"
                          aria-label={value ? `Bỏ gắn sao email ${row.subject}` : `Gắn sao email ${row.subject}`}
                          onClick={() => toggleMessage(row, value ? "unstar" : "star")}
                        >
                          <Icon name="star" />
                        </button>
                      </Tooltip>
                    ),
                  },
                  { key: "from_email", header: "Người gửi" },
                  {
                    key: "subject",
                    header: "Chủ đề",
                    render: (value, row) => (
                      <span className={row.is_read ? "" : "font-bold"}>
                        {value || "(không có chủ đề)"}
                        {row.has_attachment ? " · có tệp đính kèm" : ""}
                      </span>
                    ),
                  },
                  { key: "snippet", header: "Trích đoạn" },
                  {
                    key: "internal_date",
                    header: "Nhận lúc",
                    render: (value) => formatRelativeTime(value),
                  },
                  {
                    key: "id",
                    header: "Thao tác",
                    render: (value, row) => (
                      <div className="flex flex-wrap gap-2">
                        <Btn
                          variant="ghost"
                          className="nq-btn-compact"
                          busy={busy === `${row.is_read ? "unread" : "read"}:${value}`}
                          onClick={() => toggleMessage(row, row.is_read ? "unread" : "read")}
                        >
                          {row.is_read ? "Đánh dấu chưa đọc" : "Đánh dấu đã đọc"}
                        </Btn>
                      </div>
                    ),
                  },
                ]}
                rows={messages}
              />
            )}

            <div className="mt-6 flex flex-wrap gap-4">
              <Btn variant="ghost" onClick={() => loadAccountDetail(accountId)} busy={loading}>
                Nạp lại hộp thư
              </Btn>
            </div>
          </OpsCard>
        </section>
      ) : null}

      {activeTab === "labels" && accountId ? (
        <section>
          {accountSwitcher()}
          <OpsCard eyebrow={account?.email ?? "Hộp thư"} title="Nhãn email" count={labels.length} countLabel="nhãn">
            <form onSubmit={createLabel} className="mb-6 flex flex-wrap items-end gap-3">
              <Input
                placeholder="Tên nhãn mới"
                value={labelName}
                onChange={(e) => setLabelName(e.target.value)}
                className="w-72"
              />
              <Btn type="submit" busy={busy === "create-label"}>
                Tạo nhãn
              </Btn>
            </form>

            {loading ? (
              <Loading skeleton="table" rows={4}>Đang tải nhãn…</Loading>
            ) : labels.length === 0 ? (
              <Empty title="Chưa có nhãn nào">Tạo nhãn để phân loại email theo chủ đề vận hành.</Empty>
            ) : (
              <Table
                columns={[
                  {
                    key: "name",
                    header: "Tên nhãn",
                    render: (value, row) => (
                      <span className="flex items-center gap-2">
                        {row.color_background ? (
                          <span
                            className="inline-block h-3 w-3"
                            style={{ backgroundColor: row.color_background }}
                            aria-hidden="true"
                          />
                        ) : null}
                        {value}
                        {row.label_type === "system" ? <Badge size="xs">Hệ thống</Badge> : null}
                      </span>
                    ),
                  },
                  { key: "total_messages", header: "Tổng email", align: "right" },
                  { key: "unread_messages", header: "Chưa đọc", align: "right" },
                  {
                    key: "id",
                    header: "Thao tác",
                    render: (value, row) =>
                      row.label_type === "system" ? (
                        <span className="text-[var(--nq-dim)]">Không xoá được</span>
                      ) : (
                        <Btn
                          variant="danger"
                          className="nq-btn-compact"
                          busy={busy === `label:${value}`}
                          onClick={() => deleteLabel(value)}
                        >
                          Xoá nhãn
                        </Btn>
                      ),
                  },
                ]}
                rows={labels}
              />
            )}
          </OpsCard>
        </section>
      ) : null}

      {activeTab === "filters" && accountId ? (
        <section>
          {accountSwitcher()}
          <OpsCard eyebrow={account?.email ?? "Hộp thư"} title="Bộ lọc tự động" count={filters.length} countLabel="bộ lọc">
            <form onSubmit={createFilter} className="mb-6 space-y-3">
              <Input
                placeholder='Tiêu chí JSON, ví dụ {"from": "nhacungcap@abc.com"}'
                value={filterCriteria}
                onChange={(e) => setFilterCriteria(e.target.value)}
                className="w-full"
              />
              <Input
                placeholder='Hành động JSON, ví dụ {"addLabelIds": ["Label_1"]}'
                value={filterAction}
                onChange={(e) => setFilterAction(e.target.value)}
                className="w-full"
              />
              <Btn type="submit" busy={busy === "create-filter"}>
                Tạo bộ lọc
              </Btn>
            </form>

            {loading ? (
              <Loading skeleton="table" rows={4}>Đang tải bộ lọc…</Loading>
            ) : filters.length === 0 ? (
              <Empty title="Chưa có bộ lọc nào">
                Bộ lọc giúp email từ nhà cung cấp hoặc kênh giao hàng tự vào đúng nhãn.
              </Empty>
            ) : (
              <Table
                columns={[
                  {
                    key: "criteria",
                    header: "Tiêu chí",
                    render: (value) => objectChips(value),
                  },
                  {
                    key: "action",
                    header: "Hành động",
                    render: (value) => objectChips(value),
                  },
                  {
                    key: "id",
                    header: "Thao tác",
                    render: (value) => (
                      <Btn
                        variant="danger"
                        className="nq-btn-compact"
                        busy={busy === `filter:${value}`}
                        onClick={() => deleteFilter(value)}
                      >
                        Xoá bộ lọc
                      </Btn>
                    ),
                  },
                ]}
                rows={filters}
              />
            )}
          </OpsCard>
        </section>
      ) : null}

      {activeTab === "sync" && accountId ? (
        <section>
          {accountSwitcher()}
          <OpsCard eyebrow={account?.email ?? "Hộp thư"} title="Đồng bộ hộp thư">
            <dl className="mb-6 grid gap-4 md:grid-cols-3">
              <div className="nq-surface-block p-4">
                <dt className="nq-eyebrow">Lần đồng bộ gần nhất</dt>
                <dd className="mt-2 text-lg font-bold">
                  {account?.sync_state?.last_sync_at ? formatRelativeTime(account.sync_state.last_sync_at) : "Chưa đồng bộ"}
                </dd>
              </div>
              <div className="nq-surface-block p-4">
                <dt className="nq-eyebrow">Tổng email đã lưu</dt>
                <dd className="mt-2 text-lg font-bold">{account?.sync_state?.total_messages ?? 0}</dd>
              </div>
              <div className="nq-surface-block p-4">
                <dt className="nq-eyebrow">Email chưa đọc</dt>
                <dd className="mt-2 text-lg font-bold">{account?.sync_state?.unread_count ?? 0}</dd>
              </div>
            </dl>

            <div className="flex flex-wrap gap-4">
              <Btn busy={busy === "sync"} onClick={() => runSync(false)}>
                Đồng bộ thay đổi mới
              </Btn>
              <Btn variant="ghost" busy={busy === "sync-full"} onClick={() => runSync(true)}>
                Đồng bộ toàn bộ
              </Btn>
              {account?.has_tokens ? (
                <Btn variant="danger" busy={busy === "revoke"} onClick={revokeOAuth}>
                  Thu hồi quyền Google
                </Btn>
              ) : null}
            </div>

            <Notice>
              Đồng bộ toàn bộ tải lại toàn hộp thư và có thể mất vài phút với hộp thư lớn. Đồng bộ thay đổi mới chỉ lấy email
              và nhãn thay đổi kể từ lần đồng bộ trước.
            </Notice>
            {account?.token_broken ? (
              <Alert kind="err">
                Quyền truy cập Google của tài khoản này không còn dùng được (khoá mã hoá đã thay đổi
                hoặc token bị thu hồi). Hãy thu hồi rồi kết nối lại để tiếp tục đồng bộ.
              </Alert>
            ) : null}
          </OpsCard>
        </section>
      ) : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Xoá tài khoản Gmail"
        body="Thao tác này xoá tài khoản, token đã cấp, email đã lưu, nhãn và bộ lọc liên quan. Không thể hoàn tác."
        confirmLabel="Xoá vĩnh viễn"
        variant="danger"
        busy={busy === "delete"}
        onConfirm={confirmDeleteAccount}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}