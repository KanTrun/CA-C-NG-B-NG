"use client";

import { useMemo, useState } from "react";
import { Icon } from "../../ui/icons";
import {
  Btn,
  Empty,
  MeetingList,
  MeetingListItem,
  MeetingMetaRow,
  MeetingResultTabs,
  MeetingSection,
  StatusChip,
  inputClassName,
  propLabel,
  propTone,
  sopRankTone,
  vanDeLabel,
  vanDeTone,
  type ResultTab,
} from "./meeting-ui";

type ActionItem = {
  id: string;
  tieu_de: string;
  noi_dung_chi_tiet?: string;
  tinh_chat?: "bat_buoc" | "tuy_chon" | "khuyen_khich";
  ten_nguoi_giao?: string;
  nhan_vien_id?: string | null;
  ten_nguoi_nhan: string | null;
  pham_vi?: "ca_nhan" | "nhom";
  thoi_gian_bat_dau?: string;
  han_chot?: string;
  muc_do_uu_tien?: "cao" | "trung_binh" | "thap";
  do_tin_cay: number;
  da_chon?: boolean;
  loai_cong_viec?: "1_ca" | "nhieu_ca" | "gop_y";
  ca_thuc_hien?: string;
  ca_du_kien?: string[];
  can_lam_ro?: boolean;
  van_de_ngu_canh?: string;
  cau_hoi_lam_ro?: string;
  goi_y_xu_ly?: string[];
  stt_near_miss?: boolean;
  khong_co_can_cu?: boolean;
  nguon_cau_noi?: string;
};

type CuocHop = {
  id?: string;
  tieu_de: string;
  nguon_am_thanh?: string | null;
  transcript_thoai?: { nguoi_noi: string; noi_dung: string }[];
  tom_tat: string;
  phien_ban?: number;
  last_modified_at?: string;
  ngay_ghi_am?: string;
  van_de_phat_sinh?: { van_de: string; trang_thai: string; ghi_chu?: string }[];
  quyet_dinh?: string[];
  de_xuat_sop?: {
    quy_trinh_lien_quan: string;
    buoc_so?: number | null;
    noi_dung_thay_doi: string;
    ly_do?: string;
  }[];
  de_xuat_phe_duyet?: {
    id: string;
    loai_de_xuat: string;
    tieu_de: string;
    nguoi_de_xuat?: string;
    nguoi_phe_duyet?: string;
    noi_dung: string;
    ly_do?: string;
    trang_thai: string;
    quy_trinh_lien_quan?: string | null;
  }[];
  action_items: ActionItem[];
  gop_y_luu_y?: {
    id: string;
    nguoi_gop_y?: string;
    nguoi_nhan?: string;
    chu_de?: string;
    tinh_chat?: string;
    noi_dung: string;
    ghi_chu?: string;
  }[];
  audit_sop?: {
    diem_tuan_thu: number;
    xep_hang: string;
    // Backend gán thẳng giá trị LLM trả về (`extract.py` → `norm_audit`) nên
    // `tieu_chi` có thể là None dù kiểu khai là bắt buộc. Khai nullable để
    // TS buộc phải guard — trước đây `meeting.audit_sop.tieu_chi?.length`
    // vẫn ném TypeError khi gặp null và làm trắng cả pane kết quả.
    tieu_chi?: { ten_tieu_chi: string; dat: boolean; chi_tiet?: string }[] | null;
    canh_bao_do?: string[] | null;
    nhan_xet_chung?: string | null;
  } | null;
  ban_tin_ca?: {
    ban_vip?: string[];
    luu_y_di_ung_khach?: string[];
    su_co_thiet_bi_khan?: string[];
    danh_sach_mon_86?: string[];
    noi_dung_tin_nhan_gui_nhom?: string;
  };
  huan_luyen_quan_ly?: {
    ty_le_noi_quan_ly_pct: number;
    ty_le_noi_nhan_vien_pct: number;
    diem_tuong_tac_2_chieu: number;
    diem_truyen_cam_hung: number;
    phong_cach_dieu_hanh?: string;
    loi_khuyen_ai_coaching?: string[];
  };
  dieu_chinh_lich?: {
    id: string;
    nhan_vien_id?: string | null;
    ten_nhan_vien?: string;
    loai: string;
    thu?: string;
    khung?: string;
    ca_id?: string;
    tuan_iso?: string;
    ly_do?: string;
    trang_thai?: string;
  }[];
  do_tin_cay_tong_the?: number;
  khong_lien_quan?: boolean;
  trang_thai?: string;
  duyet_boi?: string;
  duyet_luc?: string;
};

function fbLabel(tinh_chat?: string): string {
  if (tinh_chat === "khen_ngoi") return "Khen ngợi";
  if (tinh_chat === "nhac_nho") return "Nhắc nhở";
  if (tinh_chat === "kinh_nghiem") return "Kinh nghiệm";
  return "Góp ý";
}

function fbTopic(chu_de?: string): string {
  if (chu_de === "thai_do_phuc_vu") return "Thái độ phục vụ";
  if (chu_de === "ky_nang_pha_che") return "Kỹ năng pha chế";
  if (chu_de === "ve_sinh_an_toan") return "Vệ sinh & an toàn";
  if (chu_de === "dong_vien_khen_ngoi") return "Động viên";
  return "Lưu ý chung";
}

function loaiDeXuatLabel(loai: string): string {
  if (loai === "quy_trinh_sop") return "Quy trình SOP";
  if (loai === "mua_sam_vat_tu") return "Mua sắm / vật tư";
  if (loai === "chinh_sach_nhan_su") return "Nhân sự";
  if (loai === "dieu_chinh_lich") return "Điều chỉnh lịch ca";
  return "Khác";
}

export function MeetingResults({
  meeting,
  liveTranscript,
  manager,
  busy,
  copiedBroadcast,
  onCopyBroadcast,
  onToggleAction,
  onUpdateAssignee,
  onUpdateDue,
  onUpdateActionTitle,
  onAddActionItem,
  onRemoveActionItem,
  onUpdateProposalStatus,
  onUpdateWorkType,
  onUpdateCaThucHien,
  onConvertToFeedback,
  onClarifyActions,
  onResolveClarification,
  onApply,
}: {
  meeting: CuocHop;
  liveTranscript: string;
  manager: boolean;
  busy: boolean;
  copiedBroadcast: boolean;
  onCopyBroadcast: (text: string) => void;
  onToggleAction: (id: string) => void;
  onUpdateAssignee: (id: string, name: string) => void;
  onUpdateDue: (id: string, due: string) => void;
  onUpdateActionTitle?: (id: string, title: string) => void;
  onAddActionItem?: () => void;
  onRemoveActionItem?: (id: string) => void;
  onUpdateProposalStatus?: (id: string, status: "da_duyet" | "cho_duyet" | "tu_choi") => void;
  onUpdateWorkType?: (id: string, type: "1_ca" | "nhieu_ca" | "gop_y") => void;
  onUpdateCaThucHien?: (id: string, ca: string) => void;
  onConvertToFeedback?: (id: string) => void;
  onClarifyActions?: () => void;
  onResolveClarification?: (id: string, solution: string) => void;
  onApply: () => void;
}) {
  const [tab, setTab] = useState<ResultTab>("overview");
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  const counts = useMemo(
    () => ({
      vanhanh: (meeting.van_de_phat_sinh?.length ?? 0) + (meeting.audit_sop ? 1 : 0),
      bantin:
        (meeting.ban_tin_ca ? 1 : 0) +
        (meeting.de_xuat_phe_duyet?.length ?? 0) +
        (meeting.de_xuat_sop?.length ?? 0) +
        (meeting.dieu_chinh_lich?.length ?? 0),
      viec: meeting.action_items.length,
      coaching: (meeting.gop_y_luu_y?.length ?? 0) + (meeting.huan_luyen_quan_ly ? 1 : 0),
    }),
    [meeting],
  );

  const transcriptCount = meeting.transcript_thoai?.length ?? 0;

  return (
    <div className="space-y-4">
      <MeetingResultTabs active={tab} onChange={setTab} counts={counts} />

      {tab === "overview" ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)]">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-mono uppercase text-[var(--nq-ink-muted)]">Trạng thái:</span>
              <StatusChip tone={meeting.trang_thai === "da_duyet" ? "ok" : "warn"}>
                {meeting.trang_thai === "da_duyet" ? "Đã duyệt vào ca" : "Chờ quản lý duyệt"}
              </StatusChip>
              {meeting.duyet_boi && (
                <span className="text-xs text-[var(--nq-ink-muted)]">
                  bởi <strong>{meeting.duyet_boi}</strong>
                  {meeting.duyet_luc ? ` (${new Date(meeting.duyet_luc).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })})` : ""}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs font-mono text-[var(--nq-ink-muted)]">
              <span>Nguồn: {meeting.nguon_am_thanh ?? "không rõ"}</span>
              <span>Độ tin cậy: {Math.round((meeting.do_tin_cay_tong_the ?? 0.9) * 100)}%</span>
            </div>
          </div>

          <div className="nq-meeting-transcript">
            <button
              type="button"
              className="nq-meeting-transcript__toggle"
              onClick={() => setTranscriptOpen((v) => !v)}
              aria-expanded={transcriptOpen}
            >
              <span>Bản bóc băng thoại</span>
              <span className="text-[var(--nq-ink-muted)]">
                {transcriptCount ? `${transcriptCount} đoạn` : "Ghi chép"} · {transcriptOpen ? "Thu gọn" : "Mở rộng"}
              </span>
            </button>
            {transcriptOpen ? (
              <div className="nq-meeting-transcript__body">
                {meeting.transcript_thoai && meeting.transcript_thoai.length > 0 ? (
                  meeting.transcript_thoai.map((t, idx) => (
                    <div key={idx} className="nq-meeting-transcript__line">
                      <span className="nq-meeting-transcript__speaker">{t.nguoi_noi || "Người nói"}</span>
                      <p className="m-0 text-sm leading-relaxed">{t.noi_dung}</p>
                    </div>
                  ))
                ) : (
                  <p className="m-0 text-sm text-[var(--nq-ink-muted)] italic">
                    {liveTranscript || "Đã trích xuất nội dung từ ghi chép cuộc họp."}
                  </p>
                )}
              </div>
            ) : null}
          </div>

          <div className="nq-meeting-grid-2">
            <article className="nq-meeting-panel">
              <h4 className="nq-meeting-panel__title">Tóm tắt cuộc họp</h4>
              <p className="nq-meeting-panel__body">{meeting.tom_tat}</p>
            </article>
            <article className="nq-meeting-panel">
              <h4 className="nq-meeting-panel__title">Quyết định đã chốt</h4>
              {meeting.quyet_dinh && meeting.quyet_dinh.length > 0 ? (
                <ul className="m-0 list-disc space-y-1 pl-5 text-sm leading-relaxed">
                  {meeting.quyet_dinh.map((q, idx) => (
                    <li key={idx}>{q}</li>
                  ))}
                </ul>
              ) : (
                <p className="nq-meeting-panel__body text-[var(--nq-ink-muted)] italic">
                  Duy trì đúng quy trình vận hành ca.
                </p>
              )}
            </article>
          </div>

        </div>
      ) : null}

      {tab === "vanhanh" ? (
        <div className="space-y-5">
          {meeting.van_de_phat_sinh && meeting.van_de_phat_sinh.length > 0 ? (
            <MeetingSection title="Vấn đề phát sinh" count={meeting.van_de_phat_sinh.length}>
              <MeetingList>
                {meeting.van_de_phat_sinh.map((vd, idx) => (
                  <MeetingListItem
                    key={idx}
                    title={vd.van_de}
                    badge={<StatusChip tone={vanDeTone(vd.trang_thai)}>{vanDeLabel(vd.trang_thai)}</StatusChip>}
                    meta={vd.ghi_chu}
                  />
                ))}
              </MeetingList>
            </MeetingSection>
          ) : (
            <Empty>Không có vấn đề phát sinh cần theo dõi.</Empty>
          )}

          {meeting.audit_sop ? (
            <MeetingSection
              title="Kiểm soát tuân thủ SOP ca"
              hint="Đối soát nội dung briefing với tiêu chuẩn vận hành"
            >
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <StatusChip tone={sopRankTone(meeting.audit_sop.xep_hang)}>
                  Hạng {meeting.audit_sop.xep_hang}
                </StatusChip>
                <StatusChip>{meeting.audit_sop.diem_tuan_thu}/100 điểm</StatusChip>
              </div>

              {meeting.audit_sop.canh_bao_do && meeting.audit_sop.canh_bao_do.length > 0 ? (
                <div className="nq-meeting-panel mb-3 border-[var(--nq-red)]">
                  <h4 className="nq-meeting-panel__title text-[var(--nq-red)]">Cảnh báo từ ban kiểm soát</h4>
                  <ul className="m-0 list-disc space-y-1 pl-5 text-sm">
                    {meeting.audit_sop.canh_bao_do.map((cb, i) => (
                      <li key={i}>{cb}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {meeting.audit_sop.tieu_chi && meeting.audit_sop.tieu_chi.length > 0 ? (
                <div className="nq-meeting-checklist">
                  {meeting.audit_sop.tieu_chi.map((tc, idx) => (
                    <div key={idx} className={`nq-meeting-check ${tc.dat ? "nq-meeting-check--ok" : ""}`}>
                      <span className="nq-meeting-check__mark">{tc.dat ? "Đạt" : "Bỏ sót"}</span>
                      <div>
                        <p className="m-0 font-semibold text-sm">{tc.ten_tieu_chi}</p>
                        {tc.chi_tiet ? <p className="m-0 mt-1 text-xs text-[var(--nq-ink-muted)]">{tc.chi_tiet}</p> : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}

              {meeting.audit_sop.nhan_xet_chung ? (
                <p className="mt-3 text-sm text-[var(--nq-ink-muted)]">
                  <strong className="text-[var(--nq-fg)]">Nhận xét:</strong> {meeting.audit_sop.nhan_xet_chung}
                </p>
              ) : null}
            </MeetingSection>
          ) : null}
        </div>
      ) : null}

      {tab === "bantin" ? (
        <div className="space-y-5">
          {meeting.ban_tin_ca ? (
            <MeetingSection title="Bản tin ca khẩn" hint="VIP, dị ứng, sự cố thiết bị, món hết">
              <div className="flex flex-wrap justify-end gap-2 mb-3">
                {meeting.ban_tin_ca.noi_dung_tin_nhan_gui_nhom ? (
                  <Btn
                    variant="ghost"
                    onClick={() => onCopyBroadcast(meeting.ban_tin_ca?.noi_dung_tin_nhan_gui_nhom || "")}
                  >
                    {copiedBroadcast ? "Đã sao chép" : "Sao chép tin nhắn nhóm"}
                  </Btn>
                ) : null}
              </div>
              <div className="nq-meeting-broadcast-grid">
                <BroadcastCard title="Bàn VIP / đặt trước" items={meeting.ban_tin_ca.ban_vip} empty="Không có" />
                <BroadcastCard title="Khách dị ứng / lưu ý" items={meeting.ban_tin_ca.luu_y_di_ung_khach} empty="Không có" />
                <BroadcastCard title="Sự cố thiết bị" items={meeting.ban_tin_ca.su_co_thiet_bi_khan} empty="Bình thường" />
                <BroadcastCard title="Món hết (86)" items={meeting.ban_tin_ca.danh_sach_mon_86} empty="Đủ món" />
              </div>
              {meeting.ban_tin_ca.noi_dung_tin_nhan_gui_nhom ? (
                <div className="nq-prose-block mt-3">
                  {meeting.ban_tin_ca.noi_dung_tin_nhan_gui_nhom}
                </div>
              ) : null}
            </MeetingSection>
          ) : (
            <Empty>Chưa có bản tin ca từ cuộc họp này.</Empty>
          )}

          {meeting.de_xuat_phe_duyet && meeting.de_xuat_phe_duyet.length > 0 ? (
            <MeetingSection title="Đề xuất cần phê duyệt" count={meeting.de_xuat_phe_duyet.length}>
              <MeetingList>
                {meeting.de_xuat_phe_duyet.map((prop) => (
                  <MeetingListItem
                    key={prop.id}
                    title={prop.tieu_de}
                    badge={
                      <div className="flex flex-wrap items-center gap-1.5">
                        <StatusChip tone={propTone(prop.trang_thai)}>{propLabel(prop.trang_thai)}</StatusChip>
                        <StatusChip>{loaiDeXuatLabel(prop.loai_de_xuat)}</StatusChip>
                        {manager && onUpdateProposalStatus ? (
                          <div className="flex items-center gap-1 ml-1">
                            {prop.trang_thai !== "da_duyet" && (
                              <button
                                type="button"
                                className="px-2 py-0.5 text-xs rounded bg-[var(--nq-st-ok)] hover:bg-[var(--nq-st-ok)] text-[var(--nq-st-ok-ink)] border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))] transition-colors"
                                onClick={() => onUpdateProposalStatus(prop.id, "da_duyet")}
                                title="Đồng ý duyệt đề xuất này"
                              >
                                Duyệt
                              </button>
                            )}
                            {prop.trang_thai !== "tu_choi" && (
                              <button
                                type="button"
                                className="px-2 py-0.5 text-xs rounded bg-[var(--nq-st-danger)] hover:bg-[var(--nq-st-danger)] text-[var(--nq-st-danger-ink)] border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] transition-colors"
                                onClick={() => onUpdateProposalStatus(prop.id, "tu_choi")}
                                title="Bác bỏ đề xuất này"
                              >
                                Bác bỏ
                              </button>
                            )}
                            {prop.trang_thai !== "cho_duyet" && (
                              <button
                                type="button"
                                className="px-2 py-0.5 text-xs rounded bg-[var(--nq-surface)] hover:bg-[var(--nq-line)] text-[var(--nq-ink)] border border-[var(--nq-line)] transition-colors"
                                onClick={() => onUpdateProposalStatus(prop.id, "cho_duyet")}
                                title="Chờ xem xét lại sau"
                              >
                                Chờ xét
                              </button>
                            )}
                          </div>
                        ) : null}
                      </div>
                    }
                    meta={
                      <>
                        <span>{prop.noi_dung}</span>
                        {prop.ly_do ? <span className="block mt-1 italic">Lý do: {prop.ly_do}</span> : null}
                        <MeetingMetaRow
                          items={[
                            ...(prop.nguoi_de_xuat ? [{ label: "Đề xuất", value: prop.nguoi_de_xuat }] : []),
                            ...(prop.nguoi_phe_duyet ? [{ label: "Duyệt", value: prop.nguoi_phe_duyet }] : []),
                            ...(prop.quy_trinh_lien_quan
                              ? [{ label: "Quy trình", value: prop.quy_trinh_lien_quan }]
                              : []),
                          ]}
                        />
                      </>
                    }
                  />
                ))}
              </MeetingList>
            </MeetingSection>
          ) : null}

          {meeting.de_xuat_sop && meeting.de_xuat_sop.length > 0 ? (
            <MeetingSection title="Đề xuất sửa cẩm nang" count={meeting.de_xuat_sop.length}>
              <MeetingList>
                {meeting.de_xuat_sop.map((sop, idx) => (
                  <MeetingListItem
                    key={idx}
                    title={`${sop.quy_trinh_lien_quan}${sop.buoc_so ? ` · bước ${sop.buoc_so}` : ""}`}
                    meta={
                      <>
                        <span>Nội dung sửa: {sop.noi_dung_thay_doi}</span>
                        {sop.ly_do ? <span className="block mt-1 italic">Lý do: {sop.ly_do}</span> : null}
                      </>
                    }
                  />
                ))}
              </MeetingList>
            </MeetingSection>
          ) : null}

          {meeting.dieu_chinh_lich && meeting.dieu_chinh_lich.length > 0 ? (
            <MeetingSection title="Điều chỉnh lịch ca" count={meeting.dieu_chinh_lich.length}>
              <MeetingList>
                {meeting.dieu_chinh_lich.map((dcl) => (
                  <MeetingListItem
                    key={dcl.id}
                    title={`${dcl.loai === "xin_nghi" ? "Xin nghỉ ca" : dcl.loai === "ghim_ca" ? "Ghim ca trực" : "Đổi ca"}: ${dcl.ten_nhan_vien || "Nhân viên"} (${dcl.thu || "trong tuần"})`}
                    badge={
                      <div className="flex items-center gap-1.5">
                        <StatusChip tone={dcl.trang_thai === "da_duyet" ? "ok" : "warn"}>
                          {dcl.trang_thai === "da_duyet" ? "Đã duyệt" : "Chờ duyệt"}
                        </StatusChip>
                        <StatusChip>{dcl.ca_id || dcl.khung || "Tất cả khung"}</StatusChip>
                      </div>
                    }
                    meta={
                      <>
                        <span>{dcl.ly_do || "Điều chỉnh theo thỏa thuận cuộc họp"}</span>
                        {dcl.tuan_iso ? <span className="block mt-1 text-xs text-[var(--nq-ink-muted)]">Áp dụng tuần: {dcl.tuan_iso}</span> : null}
                      </>
                    }
                  />
                ))}
              </MeetingList>
            </MeetingSection>
          ) : null}
        </div>
      ) : null}

      {tab === "viec" ? (
        <MeetingSection
          title="Công việc được giao"
          hint={`Độ tin cậy AI: ${Math.round((meeting.do_tin_cay_tong_the ?? 0.9) * 100)}%`}
          count={meeting.action_items.length}
        >
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <div className="text-xs">
              {(() => {
                // Banner phải trung thực: việc chọn mà chưa gắn được mã nhân viên
                // (nhan_vien_id rỗng) không được báo "đầy đủ thông tin" — đã gặp
                // thật 2026-10-01, duyệt xong việc treo không có người nhận.
                const daChon = meeting.action_items.filter((a) => a.da_chon);
                const soViecCanXuLy = daChon.filter(
                  (a) =>
                    a.can_lam_ro ||
                    !a.nhan_vien_id ||
                    !a.ten_nguoi_nhan ||
                    a.ten_nguoi_nhan.trim() === "" ||
                    a.ten_nguoi_nhan.trim().toLowerCase() === "chưa rõ",
                ).length;
                if (soViecCanXuLy > 0) {
                  return (
                    <span className="text-[var(--nq-st-warn-ink)] font-medium flex items-center gap-1.5">
                      <Icon name="warn" size={14} /> Có <strong>{soViecCanXuLy}</strong> việc cần
                      làm rõ ngữ cảnh hoặc bổ sung nhân sự trước khi giao
                    </span>
                  );
                }
                return (
                  <span className="text-[var(--nq-st-ok-ink)] font-medium flex items-center gap-1.5">
                    <span>✓</span> Toàn bộ công việc đã đầy đủ thông tin nhân sự và ca làm việc
                  </span>
                );
              })()}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {onClarifyActions && (
                <Btn variant="ghost" onClick={onClarifyActions} disabled={busy}>
                  <Icon name="bot" size={14} /> AI Rà soát ngữ cảnh & Lịch ca
                </Btn>
              )}
              {manager && onAddActionItem ? (
                <Btn variant="ghost" onClick={onAddActionItem}>
                  + Thêm việc mới
                </Btn>
              ) : null}
            </div>
          </div>

          {meeting.action_items.length === 0 ? (
            <Empty title="Không có việc giao">Không phát hiện công việc bắt buộc từ cuộc họp.</Empty>
          ) : (
            <div className="space-y-3">
              {meeting.action_items.map((it) => (
                <div
                  key={it.id}
                  className={`nq-meeting-action ${it.da_chon ? "" : "nq-meeting-action--off"} ${
                    it.can_lam_ro && it.da_chon ? "border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] bg-[var(--nq-st-warn-soft)]" : ""
                  }`}
                >
                  <div className="flex gap-3 items-start">
                    <input
                      type="checkbox"
                      checked={it.da_chon}
                      onChange={() => onToggleAction(it.id)}
                      className="mt-1.5 h-4 w-4 shrink-0 cursor-pointer accent-[var(--nq-accent)]"
                      aria-label={`Chọn việc ${it.tieu_de}`}
                    />
                    <div className="min-w-0 flex-1 space-y-2.5">
                      <div className="nq-meeting-list__row flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex-1 min-w-[200px]">
                          {onUpdateActionTitle ? (
                            <input
                              type="text"
                              className="w-full bg-transparent border-b border-dashed border-[var(--nq-line)] focus:border-copper text-sm font-semibold text-white outline-none py-0.5"
                              value={it.tieu_de}
                              onChange={(e) => onUpdateActionTitle(it.id, e.target.value)}
                              placeholder="Tên công việc..."
                            />
                          ) : (
                            <p className="nq-meeting-list__title">{it.tieu_de}</p>
                          )}
                        </div>

                        <div className="flex items-center gap-1.5 flex-wrap">
                          {/* Work Type Switcher */}
                          <div className="flex items-center gap-0.5 bg-[var(--nq-bg-elevated)] p-0.5 rounded border border-[var(--nq-line)] text-2xs font-medium">
                            <button
                              type="button"
                              onClick={() => onUpdateWorkType?.(it.id, "1_ca")}
                              className={`px-2 py-0.5 rounded transition-colors ${
                                !it.loai_cong_viec || it.loai_cong_viec === "1_ca"
                                  ? "bg-[var(--nq-st-warn-soft)] text-[var(--nq-st-warn-ink)] font-semibold border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))]"
                                  : "text-[var(--nq-ink-muted)] hover:text-[var(--nq-ink)]"
                              }`}
                              title="Làm ngay trong 1 ca (ca hiện tại hoặc ca kế tiếp)"
                            >
                              <Icon name="zap" size={13} /> 1 ca
                            </button>
                            <button
                              type="button"
                              onClick={() => onUpdateWorkType?.(it.id, "nhieu_ca")}
                              className={`px-2 py-0.5 rounded transition-colors ${
                                it.loai_cong_viec === "nhieu_ca"
                                  ? "bg-[var(--nq-st-info-soft)] text-[var(--nq-st-info-ink)] font-semibold border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))]"
                                  : "text-[var(--nq-ink-muted)] hover:text-[var(--nq-ink)]"
                              }`}
                              title="Kéo dài qua nhiều ca / theo dõi định kỳ"
                            >
                              <Icon name="refresh" size={13} /> Nhiều ca
                            </button>
                            <button
                              type="button"
                              onClick={() => onUpdateWorkType?.(it.id, "gop_y")}
                              className={`px-2 py-0.5 rounded transition-colors ${
                                it.loai_cong_viec === "gop_y"
                                  ? "bg-[var(--nq-st-info-soft)] text-[var(--nq-st-info-ink)] font-semibold border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))]"
                                  : "text-[var(--nq-ink-muted)] hover:text-[var(--nq-ink)]"
                              }`}
                              title="Chỉ là góp ý / nhắc nhở làm việc"
                            >
                              <Icon name="chat" size={14} /> Góp ý
                            </button>
                          </div>

                          <StatusChip tone={it.tinh_chat === "bat_buoc" || !it.tinh_chat ? "danger" : "default"}>
                            {it.tinh_chat === "bat_buoc" || !it.tinh_chat ? "Bắt buộc" : "Khuyến khích"}
                          </StatusChip>
                          <StatusChip tone={it.do_tin_cay >= 0.9 ? "ok" : it.do_tin_cay >= 0.75 ? "warn" : "danger"}>
                            {Math.round(it.do_tin_cay * 100)}% tin cậy
                          </StatusChip>
                          {manager && onRemoveActionItem && (
                            <button
                              type="button"
                              className="px-1.5 py-0.5 text-xs text-[var(--nq-st-danger-ink)] hover:text-[var(--nq-st-danger-ink)] hover:bg-[var(--nq-st-danger-soft)] rounded transition-colors"
                              onClick={() => onRemoveActionItem(it.id)}
                              title="Xoá việc này"
                            >
                              Xoá
                            </button>
                          )}
                        </div>
                      </div>

                      {it.noi_dung_chi_tiet ? (
                        <div className="nq-meeting-action__detail text-xs">
                          <strong>Chi tiết:</strong> {it.noi_dung_chi_tiet}
                        </div>
                      ) : null}

                      {/* Notice if marked as Gop Y */}
                      {it.loai_cong_viec === "gop_y" && (
                        <div className="p-2 rounded bg-[var(--nq-st-info-soft)] border border-[color-mix(in_srgb,var(--nq-st-info)_46%,var(--nq-line))] flex items-center justify-between gap-2 flex-wrap text-xs">
                          <span className="text-[var(--nq-st-info-ink)]">
                            <Icon name="info" size={14} /> Mục này mang tính chất góp ý/nhắc nhở, sẽ được lưu vào biên bản thay vì tạo việc treo.
                          </span>
                          {onConvertToFeedback && (
                            <button
                              type="button"
                              className="px-2 py-0.5 rounded bg-[var(--nq-st-info)] hover:bg-[var(--nq-st-info)] text-[var(--nq-accent-ink)] font-medium transition-colors"
                              onClick={() => onConvertToFeedback(it.id)}
                            >
                              Chuyển ngay sang tab Góp ý ➔
                            </button>
                          )}
                        </div>
                      )}

                      {/* Assignment and Schedule Details */}
                      <div className="nq-meeting-action__fields flex flex-wrap items-center gap-x-4 gap-y-2 pt-1">
                        <label className="flex items-center gap-1.5 text-xs">
                          Giao cho:
                          <input
                            type="text"
                            placeholder="Tên nhân viên"
                            className={`${inputClassName} nq-input--compact w-28`}
                            value={it.ten_nguoi_nhan || ""}
                            onChange={(e) => onUpdateAssignee(it.id, e.target.value)}
                          />
                        </label>

                        {/* Ca thực hiện */}
                        <div className="flex items-center gap-1.5 text-xs flex-wrap">
                          <span className="text-[var(--nq-ink-muted)]">Ca thực hiện:</span>
                          {it.ca_du_kien && it.ca_du_kien.length > 0 ? (
                            <select
                              className="bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] text-[var(--nq-st-warn-ink)] text-xs rounded px-2 py-1 font-mono focus:border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] outline-none max-w-[210px]"
                              value={it.ca_thuc_hien || it.ca_du_kien[0]}
                              onChange={(e) => onUpdateCaThucHien?.(it.id, e.target.value)}
                            >
                              {it.ca_du_kien.map((c, idx) => (
                                <option key={idx} value={c}>
                                  {c}
                                </option>
                              ))}
                              <option value="Xuyên suốt các ca tuần này">Xuyên suốt các ca tuần này</option>
                              <option value="Tự chọn thời điểm">Tự chọn thời điểm</option>
                            </select>
                          ) : (
                            <input
                              type="text"
                              placeholder="Nhập ca thực hiện"
                              className={`${inputClassName} nq-input--compact w-32`}
                              value={it.ca_thuc_hien || ""}
                              onChange={(e) => onUpdateCaThucHien?.(it.id, e.target.value)}
                            />
                          )}
                        </div>

                        {/* Schedule Badge */}
                        {it.ca_du_kien && it.ca_du_kien.length > 0 ? (
                          <span
                            className="text-2xs px-2 py-0.5 rounded bg-[var(--nq-bg-elevated)] text-[var(--nq-ink)] border border-[var(--nq-line)] font-mono"
                            title={it.ca_du_kien.join(" | ")}
                          >
                            <Icon name="calendar" size={14} /> Có {it.ca_du_kien.length} ca trực tuần này
                          </span>
                        ) : it.ten_nguoi_nhan &&
                          it.ten_nguoi_nhan !== "Chưa rõ" &&
                          it.ten_nguoi_nhan !== "Cả ca" ? (
                          <span className="text-2xs px-2 py-0.5 rounded bg-[var(--nq-st-danger-soft)] text-[var(--nq-st-danger-ink)] border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] font-mono">
                            <Icon name="warn" size={14} /> Không có ca trực tuần này
                          </span>
                        ) : null}

                        <label className="flex items-center gap-1.5 text-xs">
                          Hạn chót:
                          <input
                            type="text"
                            className={`${inputClassName} nq-input--compact w-24`}
                            value={it.han_chot || ""}
                            onChange={(e) => onUpdateDue(it.id, e.target.value)}
                            placeholder="vd: 16:00"
                          />
                        </label>
                      </div>

                      {/* AI Clarifier Agent Box */}
                      {it.can_lam_ro && it.cau_hoi_lam_ro && (
                        <div className="p-3 rounded-md bg-[var(--nq-st-warn-soft)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] space-y-2 mt-2">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <div className="flex items-center gap-1.5">
                              <span className="text-sm"><Icon name="bot" size={14} /></span>
                              <span className="text-xs font-bold font-mono uppercase tracking-wider text-[var(--nq-st-warn-ink)]">
                                Trợ lý AI làm rõ phân công
                              </span>
                            </div>
                            {it.van_de_ngu_canh && (
                              <span className="text-2xs px-2 py-0.5 rounded bg-[var(--nq-bg-elevated)] text-[var(--nq-st-warn-ink)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))]">
                                {it.van_de_ngu_canh}
                              </span>
                            )}
                          </div>

                          <p className="text-xs text-[var(--nq-ink)] m-0 leading-relaxed font-medium">
                            {it.cau_hoi_lam_ro}
                          </p>

                          {it.goi_y_xu_ly && it.goi_y_xu_ly.length > 0 && (
                            <div className="pt-1 flex flex-wrap items-center gap-1.5">
                              <span className="text-2xs text-[var(--nq-ink-muted)] font-mono">Gợi ý 1-chạm:</span>
                              {it.goi_y_xu_ly.map((sug, sIdx) => (
                                <button
                                  key={sIdx}
                                  type="button"
                                  onClick={() => onResolveClarification?.(it.id, sug)}
                                  className="px-2.5 py-0.5 text-xs rounded-full bg-[var(--nq-st-warn-soft)] hover:bg-[var(--nq-st-warn-soft)] text-[var(--nq-st-warn-ink)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] transition-colors cursor-pointer"
                                >
                                  ✓ {sug}
                                </button>
                              ))}
                            </div>
                          )}

                          {/* Custom Clarification Response Input */}
                          <div className="flex items-center gap-1.5 pt-1">
                            <input
                              type="text"
                              placeholder="Hoặc tự nhập hướng giải quyết (vd: Giao Lan làm trước 15:30)..."
                              className="bg-[var(--nq-bg-elevated)] border border-[var(--nq-line)] text-xs text-white rounded px-2.5 py-1 focus:border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] outline-none flex-1 font-sans"
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && e.currentTarget.value.trim()) {
                                  onResolveClarification?.(it.id, e.currentTarget.value.trim());
                                  e.currentTarget.value = "";
                                }
                              }}
                            />
                            <button
                              type="button"
                              className="px-2.5 py-1 text-xs rounded bg-[var(--nq-st-warn-soft)] hover:bg-[var(--nq-st-warn)] text-[var(--nq-st-warn-ink)] font-medium border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] transition-colors shrink-0"
                              onClick={(e) => {
                                const input = e.currentTarget.previousElementSibling as HTMLInputElement;
                                if (input && input.value.trim()) {
                                  onResolveClarification?.(it.id, input.value.trim());
                                  input.value = "";
                                }
                              }}
                            >
                              Gửi AI
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </MeetingSection>
      ) : null}

      {tab === "coaching" ? (
        <div className="space-y-5">
          {meeting.gop_y_luu_y && meeting.gop_y_luu_y.length > 0 ? (
            <MeetingSection title="Góp ý & lưu ý nội bộ" count={meeting.gop_y_luu_y.length}>
              <MeetingList>
                {meeting.gop_y_luu_y.map((fb) => (
                  <MeetingListItem
                    key={fb.id}
                    title={fb.noi_dung}
                    badge={
                      <>
                        <StatusChip>{fbLabel(fb.tinh_chat)}</StatusChip>
                        <StatusChip>{fbTopic(fb.chu_de)}</StatusChip>
                      </>
                    }
                    meta={
                      <>
                        {fb.nguoi_gop_y ? `Từ: ${fb.nguoi_gop_y}` : null}
                        {fb.nguoi_nhan ? ` · Gửi đến: ${fb.nguoi_nhan}` : null}
                        {fb.ghi_chu ? ` · ${fb.ghi_chu}` : null}
                      </>
                    }
                  />
                ))}
              </MeetingList>
            </MeetingSection>
          ) : (
            <Empty>Chưa có góp ý nội bộ từ cuộc họp.</Empty>
          )}

          {meeting.huan_luyen_quan_ly ? (
            <MeetingSection
              title="Huấn luyện quản lý"
              hint={meeting.huan_luyen_quan_ly.phong_cach_dieu_hanh || "Phong cách điều hành ca"}
            >
              <div className="nq-meeting-ratio">
                <div className="nq-meeting-ratio__labels">
                  <span>
                    Quản lý nói: <strong>{meeting.huan_luyen_quan_ly.ty_le_noi_quan_ly_pct}%</strong>
                  </span>
                  <span>
                    Nhân viên: <strong>{meeting.huan_luyen_quan_ly.ty_le_noi_nhan_vien_pct}%</strong>
                  </span>
                </div>
                <div className="nq-meeting-ratio__bar">
                  <div
                    className="nq-meeting-ratio__bar-mgr h-full"
                    style={{ width: `${meeting.huan_luyen_quan_ly.ty_le_noi_quan_ly_pct}%` }}
                  />
                  <div
                    className="nq-meeting-ratio__bar-staff h-full"
                    style={{ width: `${meeting.huan_luyen_quan_ly.ty_le_noi_nhan_vien_pct}%` }}
                  />
                </div>
                <p className="mt-2 mb-0 text-xs text-[var(--nq-ink-muted)]">
                  {meeting.huan_luyen_quan_ly.ty_le_noi_quan_ly_pct > 85
                    ? "Quản lý đang nói quá nhiều (>85%). Nên đặt thêm câu hỏi cho nhân viên."
                    : meeting.huan_luyen_quan_ly.ty_le_noi_quan_ly_pct < 50
                    ? "Quản lý nói ít (<50%). Cần dẫn dắt mục tiêu ca rõ hơn."
                    : "Tỷ lệ giao tiếp cân bằng giữa giao việc và lắng nghe."}
                </p>
              </div>

              <div className="grid gap-2 sm:grid-cols-2 mt-3">
                <div className="nq-meeting-panel flex items-center justify-between gap-3">
                  <div>
                    <p className="m-0 text-sm font-semibold">Tương tác 2 chiều</p>
                    <p className="m-0 mt-1 text-xs text-[var(--nq-ink-muted)]">Hỏi han & lắng nghe</p>
                  </div>
                  <StatusChip>{meeting.huan_luyen_quan_ly.diem_tuong_tac_2_chieu}/10</StatusChip>
                </div>
                <div className="nq-meeting-panel flex items-center justify-between gap-3">
                  <div>
                    <p className="m-0 text-sm font-semibold">Truyền cảm hứng</p>
                    <p className="m-0 mt-1 text-xs text-[var(--nq-ink-muted)]">Khen ngợi & động viên</p>
                  </div>
                  <StatusChip>{meeting.huan_luyen_quan_ly.diem_truyen_cam_hung}/10</StatusChip>
                </div>
              </div>

              {meeting.huan_luyen_quan_ly.loi_khuyen_ai_coaching &&
              meeting.huan_luyen_quan_ly.loi_khuyen_ai_coaching.length > 0 ? (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
                  {meeting.huan_luyen_quan_ly.loi_khuyen_ai_coaching.map((tip, idx) => (
                    <li key={idx}>{tip}</li>
                  ))}
                </ul>
              ) : null}
            </MeetingSection>
          ) : null}
        </div>
      ) : null}

      {meeting.khong_lien_quan ? (
        <p className="text-sm text-[var(--nq-ink-muted)]">
          Nội dung bóc băng không liên quan vận hành quán. AI không tạo việc giao — vui lòng kiểm tra nguồn âm thanh.
        </p>
      ) : null}

      <div className="nq-meeting-footer flex flex-wrap items-center justify-between gap-4">
        <div>
          {meeting.trang_thai === "da_duyet" ? (
            <p className="text-sm text-[var(--nq-st-ok-ink)] font-medium m-0">
              ✓ Biên bản đã được duyệt vào ca
              {meeting.duyet_boi ? ` bởi ${meeting.duyet_boi}` : ""}
              {meeting.duyet_luc ? ` lúc ${new Date(meeting.duyet_luc).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}.
            </p>
          ) : (
            <div className="space-y-1">
              <p className="nq-meeting-footer__note m-0">
                Sau khi duyệt, việc được chọn sẽ đẩy vào OpsEngine (việc treo ca); đề xuất cẩm nang ghi vào Playbook; điều chỉnh lịch ca được nạp thẳng vào Solver.
              </p>
              {(() => {
                const daChon = meeting.action_items.filter((a) => a.da_chon);
                const soViecChuaChuan = daChon.filter(
                  (a) =>
                    a.can_lam_ro ||
                    !a.nhan_vien_id ||
                    !a.ten_nguoi_nhan ||
                    a.ten_nguoi_nhan.trim() === "" ||
                    a.ten_nguoi_nhan.trim().toLowerCase() === "chưa rõ",
                ).length;
                if (soViecChuaChuan > 0) {
                  return (
                    <p className="text-xs text-[var(--nq-st-warn-ink)] font-medium m-0 flex items-center gap-1.5">
                      <Icon name="warn" size={14} /> Còn {soViecChuaChuan} việc chưa hoàn tất chỉ định nhân sự hoặc làm rõ ngữ cảnh. Cần điền người nhận trước khi duyệt vào ca.
                    </p>
                  );
                }
                return null;
              })()}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {meeting.trang_thai === "da_duyet" && (
            <a
              href="/lich-tuan"
              className="px-3 py-1.5 text-xs rounded font-medium bg-[var(--nq-surface)] hover:bg-[var(--nq-line)] text-[var(--nq-st-warn-ink)] border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] transition-colors inline-flex items-center gap-1.5 no-underline"
            >
              <Icon name="calendar" size={14} /> Sang Lịch tuần xếp ca (Solver)
            </a>
          )}
          <Btn variant="primary" onClick={onApply} disabled={busy || !manager}>
            {manager
              ? meeting.trang_thai === "da_duyet"
                ? "Cập nhật lại vào ca"
                : "Duyệt & phân công vào ca"
              : "Cần quyền quản lý để duyệt"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

function BroadcastCard({ title, items, empty }: { title: string; items?: string[]; empty: string }) {
  return (
    <article className="nq-meeting-broadcast-card">
      <h5>{title}</h5>
      {items && items.length > 0 ? (
        <ul>
          {items.map((v, i) => (
            <li key={i}>{v}</li>
          ))}
        </ul>
      ) : (
        <p className="m-0 text-xs text-[var(--nq-ink-muted)] italic">{empty}</p>
      )}
    </article>
  );
}
