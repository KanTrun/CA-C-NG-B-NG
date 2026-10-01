"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, apiSend, apiUpload } from "../../lib/api";
import { viError } from "../../lib/present";
import { getToken, isManager } from "../../lib/session";
import { useMeetingStream } from "../../lib/useMeetingStream";
import {
  Alert,
  AuthGate,
  Btn,
  Empty,
  Field,
  Loading,
  OpsCard,
  PageHeader,
  TabBar,
  TabButton,
  Textarea,
} from "../../ui/kit";
import { MeetingResults } from "./MeetingResults";

interface ActionItem {
  id: string;
  tieu_de: string;
  noi_dung_chi_tiet?: string;
  tinh_chat?: "bat_buoc" | "tuy_chon" | "khuyen_khich";
  ten_nguoi_giao?: string;
  nhan_vien_id?: string | null;
  ten_nguoi_nhan: string;
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
}

interface DeXuatPheDuyet {
  id: string;
  loai_de_xuat: "quy_trinh_sop" | "mua_sam_vat_tu" | "chinh_sach_nhan_su" | "dieu_chinh_lich" | "khac";
  tieu_de: string;
  nguoi_de_xuat?: string;
  nguoi_phe_duyet?: string;
  noi_dung: string;
  ly_do?: string;
  trang_thai: "da_duyet" | "cho_duyet" | "tu_choi";
  quy_trinh_lien_quan?: string | null;
  buoc_so?: number | null;
  chi_tiet_lich?: {
    id?: string;
    nhan_vien_id?: string | null;
    ten_nhan_vien?: string;
    loai?: "xin_nghi" | "ghim_ca" | "doi_ca" | "uu_tien";
    thu?: string;
    khung?: string;
    ca_id?: string;
    tuan_iso?: string;
    ly_do?: string;
  };
}

interface DeXuatSop {
  quy_trinh_lien_quan: string;
  buoc_so?: number | null;
  noi_dung_thay_doi: string;
  ly_do?: string;
}

interface DoanThoai {
  nguoi_noi: string;
  bat_dau_s?: number;
  ket_thuc_s?: number;
  noi_dung: string;
}

interface VanDePhatSinh {
  van_de: string;
  trang_thai: "da_giai_quyet" | "can_hanh_dong" | "theo_doi";
  ghi_chu?: string;
}

interface GopYLuuY {
  id: string;
  nguoi_gop_y?: string;
  nguoi_nhan?: string;
  chu_de?: "thai_do_phuc_vu" | "ky_nang_pha_che" | "ve_sinh_an_toan" | "dong_vien_khen_ngoi" | "luu_y_chung";
  tinh_chat?: "nhac_nho" | "khen_ngoi" | "kinh_nghiem" | "gop_y";
  noi_dung: string;
  ghi_chu?: string;
}

interface TieuChiAudit {
  ma: string;
  ten_tieu_chi: string;
  dat: boolean;
  chi_tiet?: string;
}

interface AuditTuanThuSop {
  diem_tuan_thu: number;
  xep_hang: "A" | "B" | "C" | "D";
  tieu_chi: TieuChiAudit[];
  canh_bao_do?: string[];
  nhan_xet_chung?: string;
}

interface BanTinCaKhan {
  ban_vip?: string[];
  luu_y_di_ung_khach?: string[];
  su_co_thiet_bi_khan?: string[];
  danh_sach_mon_86?: string[];
  noi_dung_tin_nhan_gui_nhom?: string;
}

interface HuanLuyenQuanLy {
  ty_le_noi_quan_ly_pct: number;
  ty_le_noi_nhan_vien_pct: number;
  diem_tuong_tac_2_chieu: number;
  diem_truyen_cam_hung: number;
  phong_cach_dieu_hanh?: string;
  loi_khuyen_ai_coaching?: string[];
}

interface CuocHop {
  id: string;
  tieu_de: string;
  loai_hop: "giao_ca" | "hop_tuan" | "dao_tao" | "khac";
  thoi_gian?: string;
  nguon_am_thanh?: "google_meet_tab" | "microphone" | "file_upload" | "ghi_chep_tay";
  transcript_thoai?: DoanThoai[];
  khong_lien_quan?: boolean;
  tom_tat: string;
  van_de_phat_sinh?: VanDePhatSinh[];
  quyet_dinh?: string[];
  de_xuat_phe_duyet?: DeXuatPheDuyet[];
  action_items: ActionItem[];
  gop_y_luu_y?: GopYLuuY[];
  audit_sop?: AuditTuanThuSop;
  ban_tin_ca?: BanTinCaKhan;
  huan_luyen_quan_ly?: HuanLuyenQuanLy;
  de_xuat_sop?: DeXuatSop[];
  dieu_chinh_lich?: {
    id: string;
    nhan_vien_id?: string | null;
    ten_nhan_vien?: string;
    loai: "xin_nghi" | "ghim_ca" | "doi_ca" | "uu_tien";
    thu?: string;
    khung?: string;
    ca_id?: string;
    tuan_iso?: string;
    ly_do?: string;
    trang_thai?: string;
  }[];
  do_tin_cay_tong_the?: number;
  trang_thai?: "cho_duyet" | "da_duyet" | "tu_choi";
  duyet_boi?: string;
  duyet_luc?: string;
  phien_ban?: number;
  last_modified_at?: string;
  ngay_ghi_am?: string;
}





// Browser SpeechRecognition Type Definition
interface ISpeechRecognitionEvent {
  resultIndex: number;
  results: {
    [index: number]: {
      [index: number]: {
        transcript: string;
      };
      isFinal?: boolean;
    };
    length: number;
  };
}

interface ISpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: ISpeechRecognitionEvent) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

export default function MeetingPage() {
  const [token, setToken] = useState("");
  const [manager, setManager] = useState(false);
  const [inputMode, setInputMode] = useState<"meet" | "mic" | "upload" | "text">("mic");
  const [meetingType, setMeetingType] = useState<"giao_ca" | "hop_tuan" | "dao_tao">("giao_ca");

  // Streaming realtime (Google Meet / micro trực tiếp)
  const stream = useMeetingStream();
  const streamSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamProcessorRef = useRef<ScriptProcessorNode | null>(null);

  // Recording & Live Subtitles State
  const [isRecording, setIsRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [liveTranscript, setLiveTranscript] = useState("");
  const liveTranscriptRef = useRef("");
  const [interimText, setInterimText] = useState("");
  const [volumeLevel, setVolumeLevel] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const speechRecognitionRef = useRef<ISpeechRecognition | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animFrameRef = useRef<number | null>(null);

  // Manual Text / Upload State
  const [rawText, setRawText] = useState(
    "Quản lý: Chào ca chiều, máy pha số 2 đang bị rỉ nước ở ron cao su. Khách bàn 4 phàn nàn trà sữa đào ngọt gắt.\n" +
    "Tuấn: Dạ em sẽ thay ron máy pha và lau họng máy trước 16h.\n" +
    "Quản lý: Tốt. Từ nay đổi định lượng trà đào xuống còn 20ml syrup đào.\n" +
    "My: Dạ em sẽ dán bảng công thức mới ở quầy bar trước 17h.\n" +
    "Quản lý: Nhất trí. Tuấn nhớ kiểm tra thêm tủ đá trước 18h nhé."
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Processing & Results
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [meeting, setMeeting] = useState<CuocHop | null>(null);
  const [pastMeetings, setPastMeetings] = useState<CuocHop[]>([]);
  const [copiedBroadcast, setCopiedBroadcast] = useState(false);

  function handleCopyBroadcast(text: string) {
    if (!text) return;
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedBroadcast(true);
      setTimeout(() => setCopiedBroadcast(false), 3000);
    }
  }

  useEffect(() => {
    setToken(getToken());
    setManager(isManager());
    loadHistory();
  }, []);


  async function loadHistory() {
    try {
      const res = await apiGet<{ items: CuocHop[] }>("/api/v1/meetings");
      setPastMeetings(res.items || []);
    } catch {
      // Ignored if offline
    }
  }

  // Setup Live Web Speech Recognition (Vietnamese)
  function initLiveSpeechRecognition() {
    if (typeof window === "undefined") return;
    const SpeechRecognitionClass =
      (window as unknown as { SpeechRecognition?: new () => ISpeechRecognition }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: new () => ISpeechRecognition }).webkitSpeechRecognition;

    if (!SpeechRecognitionClass) return;

    try {
      const recognition = new SpeechRecognitionClass();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "vi-VN";

      recognition.onresult = (event: ISpeechRecognitionEvent) => {
        let finalStr = "";
        let interimStr = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcriptChunk = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalStr += transcriptChunk + " ";
          } else {
            interimStr += transcriptChunk;
          }
        }
        if (finalStr) {
          liveTranscriptRef.current = liveTranscriptRef.current
            ? liveTranscriptRef.current + " " + finalStr.trim()
            : finalStr.trim();
          setLiveTranscript(liveTranscriptRef.current);
        }
        setInterimText(interimStr);
      };

      recognition.onerror = () => {
        // Fallback gracefully
      };

      speechRecognitionRef.current = recognition;
      recognition.start();
    } catch {
      // Browser does not support Web Speech API
    }
  }

  // Setup Volume Meter Visualizer
  function setupAudioMeter(stream: MediaStream, existingCtx?: AudioContext) {
    try {
      const audioCtx =
        existingCtx ||
        audioContextRef.current ||
        new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      audioContextRef.current = audioCtx;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateMeter = () => {
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const avg = sum / dataArray.length;
        setVolumeLevel(Math.min(100, Math.round((avg / 128) * 100)));
        animFrameRef.current = requestAnimationFrame(updateMeter);
      };
      updateMeter();
    } catch {
      // Ignored if audio context not permitted
    }
  }

  // 1. Google Meet Tab Audio Capture
  async function startMeetCapture() {
    setError(null);
    setSuccess(null);
    audioChunksRef.current = [];
    liveTranscriptRef.current = "";
    setLiveTranscript("");
    setInterimText("");

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getDisplayMedia) {
      setError(
        "Trình duyệt hiện tại không hỗ trợ bắt âm thanh từ tab Google Meet (thiếu getDisplayMedia). " +
        "Vui lòng dùng Chrome hoặc Edge trên máy tính để thu trực tiếp từ tab, hoặc chuyển sang tab 'Micro' / 'Tải file' bên cạnh."
      );
      return;
    }

    try {
      const displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
        } as MediaTrackConstraints,
      });

      const videoTrack = displayStream.getVideoTracks()[0];
      if (videoTrack) {
        videoTrack.onended = () => {
          stopRecording();
        };
      }

      let micStream: MediaStream | null = null;
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch {
        // Continue with tab audio only
      }

      const audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      audioContextRef.current = audioCtx;
      const dest = audioCtx.createMediaStreamDestination();

      const tabAudioTracks = displayStream.getAudioTracks();
      if (tabAudioTracks.length === 0) {
        throw new Error("Bạn chưa tích chọn 'Chia sẻ âm thanh của thẻ (Share tab audio)' khi chọn tab Google Meet.");
      }

      const tabSource = audioCtx.createMediaStreamSource(new MediaStream(tabAudioTracks));
      tabSource.connect(dest);

      if (micStream && micStream.getAudioTracks().length > 0) {
        const micSource = audioCtx.createMediaStreamSource(micStream);
        micSource.connect(dest);
      }

      const mixedStream = dest.stream;
      setupAudioMeter(mixedStream, audioCtx);
      initLiveSpeechRecognition();

      // Streaming realtime transcript
      stream.onTranscript((text, isFinal) => {
        if (isFinal) {
          liveTranscriptRef.current = liveTranscriptRef.current
            ? liveTranscriptRef.current + " " + text.trim()
            : text.trim();
          setLiveTranscript(liveTranscriptRef.current);
          setInterimText("");
        } else {
          setInterimText(text);
        }
      });
      startStreaming(mixedStream);

      const recorder = new MediaRecorder(mixedStream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm",
        audioBitsPerSecond: 32000,
      });

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        displayStream.getTracks().forEach((t) => t.stop());
        if (micStream) micStream.getTracks().forEach((t) => t.stop());
        stopStreaming();
        if (audioContextRef.current) {
          try { audioContextRef.current.close(); } catch {}
          audioContextRef.current = null;
        }
        if (animFrameRef.current) {
          cancelAnimationFrame(animFrameRef.current);
          animFrameRef.current = null;
        }
        setVolumeLevel(0);
        if (speechRecognitionRef.current) {
          try { speechRecognitionRef.current.stop(); } catch {}
          speechRecognitionRef.current = null;
        }

        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        await handleAudioBlob(audioBlob, "google_meet_tab");
      };

      mediaRecorderRef.current = recorder;
      recorder.start(1000);
      setIsRecording(true);
      setRecordSeconds(0);

      timerRef.current = setInterval(() => {
        setRecordSeconds((s) => s + 1);
      }, 1000);
    } catch (e: unknown) {
      if (e instanceof Error && (e.name === "NotAllowedError" || e.message.toLowerCase().includes("permission denied"))) {
        setError("Bạn chưa cấp quyền chia sẻ âm thanh hoặc đã hủy thao tác. Vui lòng thử lại và chọn tab Google Meet cùng tùy chọn chia sẻ âm thanh.");
      } else if (
        e instanceof Error &&
        (e.name === "NotSupportedError" || e.message.toLowerCase().includes("not supported"))
      ) {
        setError(
          "Trình duyệt hiện tại không hỗ trợ bắt âm thanh từ tab Google Meet (Not supported). " +
          "Vui lòng dùng Chrome hoặc Edge trên máy tính để thu trực tiếp từ tab Google Meet, hoặc chuyển sang tab 'Micro' / 'Tải file'."
        );
      } else {
        setError(e instanceof Error ? e.message : "Không thể bắt luồng âm thanh Google Meet.");
      }
    }
  }

  // Streaming realtime: chuyển audio stream sang PCM16 16kHz, gửi qua WebSocket
  function startStreaming(mediaStream: MediaStream) {
    stream.connect();
    const audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    audioContextRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(mediaStream);
    streamSourceRef.current = source;
    // ScriptProcessor để lấy PCM16 16kHz
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    streamProcessorRef.current = processor;
    source.connect(processor);
    processor.connect(audioCtx.destination);
    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        pcm[i] = Math.max(-1, Math.min(1, input[i])) * 0x7fff;
      }
      stream.sendAudio(pcm.buffer);
    };
  }

  function stopStreaming() {
    if (streamProcessorRef.current) {
      try { streamProcessorRef.current.disconnect(); } catch {}
      streamProcessorRef.current = null;
    }
    if (streamSourceRef.current) {
      try { streamSourceRef.current.disconnect(); } catch {}
      streamSourceRef.current = null;
    }
    stream.stop();
  }

  // 2. Microphone Recording
  async function startMicRecording() {
    setError(null);
    setSuccess(null);
    audioChunksRef.current = [];
    liveTranscriptRef.current = "";
    setLiveTranscript("");
    setInterimText("");

    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setupAudioMeter(mediaStream);
      initLiveSpeechRecognition();

      // Streaming realtime transcript
      stream.onTranscript((text, isFinal) => {
        if (isFinal) {
          liveTranscriptRef.current = liveTranscriptRef.current
            ? liveTranscriptRef.current + " " + text.trim()
            : text.trim();
          setLiveTranscript(liveTranscriptRef.current);
          setInterimText("");
        } else {
          setInterimText(text);
        }
      });
      startStreaming(mediaStream);

      const recorder = new MediaRecorder(mediaStream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm",
        audioBitsPerSecond: 32000,
      });

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        mediaStream.getTracks().forEach((t) => t.stop());
        stopStreaming();
        if (audioContextRef.current) {
          try { audioContextRef.current.close(); } catch {}
          audioContextRef.current = null;
        }
        if (animFrameRef.current) {
          cancelAnimationFrame(animFrameRef.current);
          animFrameRef.current = null;
        }
        setVolumeLevel(0);
        if (speechRecognitionRef.current) {
          try { speechRecognitionRef.current.stop(); } catch {}
          speechRecognitionRef.current = null;
        }

        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        await handleAudioBlob(audioBlob, "microphone");
      };

      mediaRecorderRef.current = recorder;
      recorder.start(1000);
      setIsRecording(true);
      setRecordSeconds(0);

      timerRef.current = setInterval(() => {
        setRecordSeconds((s) => s + 1);
      }, 1000);
    } catch (e: unknown) {
      if (e instanceof Error && (e.name === "NotAllowedError" || e.message.toLowerCase().includes("permission denied"))) {
        setError("Trình duyệt đang chặn quyền Micro (Permission denied). Vui lòng bấm vào biểu tượng cài đặt / ổ khoá ở đầu thanh địa chỉ và bật 'Microphone' thành 'Cho phép' (Allow), sau đó tải lại trang.");
      } else if (e instanceof Error && (e.name === "NotFoundError" || e.name === "DevicesNotFoundError")) {
        setError("Không tìm thấy thiết bị Microphone nào được cắm vào máy tính.");
      } else {
        setError(e instanceof Error ? e.message : "Không thể mở Microphone trên thiết bị.");
      }
    }
  }

  function stopRecording() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }

  // Handle Audio Blob Upload
  async function handleAudioBlob(blob: Blob, source: "google_meet_tab" | "microphone") {
    setBusy(true);
    setStatusMsg("Đang truyền âm thanh & bóc băng thoại với Gemini Transcribe...");
    try {
      const form = new FormData();
      form.append("file", blob, "meeting_recording.webm");
      form.append("meeting_type", meetingType);
      form.append("audio_source", source);
      const transcriptToSend = (liveTranscriptRef.current || liveTranscript).trim();
      form.append("live_transcript", transcriptToSend);

      setStatusMsg("Đang phân tích Action Items & Đề xuất Cẩm nang quán...");
      const res = await apiUpload<CuocHop>("/api/v1/meeting/process-audio", form);
      
      // If the backend transcript is empty, fallback to captured live browser speech
      if ((!res.transcript_thoai || res.transcript_thoai.length === 0) && transcriptToSend) {
        res.transcript_thoai = [{ nguoi_noi: "Giao ca", noi_dung: transcriptToSend }];
      }

      setMeeting(res);
      setSuccess("Bóc băng và phân tích cuộc họp hoàn tất!");
    } catch (e) {
      setError(
        viError(e, {
          doing: "xử lý âm thanh cuộc họp",
          invalid: "Bản thu quá ngắn hoặc không có tiếng nói để bóc băng. Ghi âm dài hơn rồi bấm Hoàn tất & trích xuất lại.",
        }),
      );
    } finally {
      setBusy(false);
      setStatusMsg("");
    }
  }

  // 3. Analyze Free Text
  async function analyzeText() {
    if (!rawText.trim()) {
      setError("Vui lòng nhập nội dung cuộc họp.");
      return;
    }
    setError(null);
    setSuccess(null);
    setBusy(true);
    setStatusMsg("AG-MEETING đang bóc tách việc và quyết định...");
    try {
      const res = await apiSend<CuocHop>("/api/v1/meeting/analyze", {
        text: rawText.trim(),
        meeting_type: meetingType,
        audio_source: "ghi_chep_tay",
      });
      setMeeting(res);
      setSuccess("Phân tích cuộc họp hoàn tất!");
    } catch (e) {
      setError(viError(e, { doing: "phân tích văn bản cuộc họp" }));
    } finally {
      setBusy(false);
      setStatusMsg("");
    }
  }

  // 4. Upload Audio File
  async function uploadFile() {
    if (!selectedFile) {
      setError("Vui lòng chọn file âm thanh.");
      return;
    }
    setError(null);
    setSuccess(null);
    setBusy(true);
    setStatusMsg("Đang tải file lên & gọi Gemini 3.5 Transcribe...");
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      form.append("meeting_type", meetingType);
      form.append("audio_source", "file_upload");

      const res = await apiUpload<CuocHop>("/api/v1/meeting/process-audio", form);
      setMeeting(res);
      setSuccess("Bóc băng file âm thanh thành công!");
    } catch (e) {
      setError(
        viError(e, {
          doing: "xử lý file âm thanh",
          invalid: "File âm thanh quá ngắn hoặc không có tiếng nói. Vui lòng chọn file ghi âm rõ tiếng hơn.",
        }),
      );
    } finally {
      setBusy(false);
      setStatusMsg("");
    }
  }

  // 5. Apply Decisions (Human-in-the-loop)
  async function applyDecisions() {
    if (!meeting) return;
    setError(null);
    setSuccess(null);

    // Kiểm tra: Không cho phép duyệt các việc đã chọn mà không có người phụ trách
    const actionsWithoutAssignee = (meeting.action_items || []).filter(
      (a) =>
        a.da_chon &&
        a.loai_cong_viec !== "gop_y" &&
        (!a.ten_nguoi_nhan ||
          a.ten_nguoi_nhan.trim() === "" ||
          a.ten_nguoi_nhan.trim().toLowerCase() === "chưa rõ"),
    );
    if (actionsWithoutAssignee.length > 0) {
      setError(
        `Còn ${actionsWithoutAssignee.length} công việc chưa có người nhận (đang để trống hoặc "Chưa rõ"). ` +
          "Vui lòng điền tên người nhận ở ô 'Giao cho' hoặc bỏ tick chọn trước khi duyệt.",
      );
      return;
    }

    setBusy(true);
    setStatusMsg("Đang đẩy việc treo vào ca & cập nhật Cẩm nang...");
    try {
      const res = await apiSend<{ ok: boolean; tasks_created: number; sop_proposals: number; schedule_adjustments?: number }>(
        "/api/v1/meeting/apply",
        meeting,
      );
      if (res.ok) {
        const schedMsg = res.schedule_adjustments ? `, và ${res.schedule_adjustments} điều chỉnh lịch ca vào Solver` : "";
        setSuccess(`Đã duyệt! Tạo thành công ${res.tasks_created} việc treo vào ca, ${res.sop_proposals} đề xuất Cẩm nang${schedMsg}.`);
        setMeeting({
          ...meeting,
          trang_thai: "da_duyet",
          duyet_boi: manager ? "Quản lý" : "Nhân viên",
          duyet_luc: new Date().toISOString(),
        });
        loadHistory();
      }
    } catch (e) {
      setError(viError(e, { doing: "phê duyệt cuộc họp" }));
    } finally {
      setBusy(false);
      setStatusMsg("");
    }
  }

  function toggleActionItem(id: string) {
    if (!meeting) return;
    setMeeting({
      ...meeting,
      action_items: meeting.action_items.map((it) =>
        it.id === id ? { ...it, da_chon: !it.da_chon } : it
      ),
    });
  }

  function updateActionAssignee(id: string, name: string) {
    if (!meeting) return;
    setMeeting({
      ...meeting,
      action_items: meeting.action_items.map((it) =>
        it.id === id ? { ...it, ten_nguoi_nhan: name } : it
      ),
    });
  }

  function updateActionDue(id: string, due: string) {
    if (!meeting) return;
    setMeeting({
      ...meeting,
      action_items: meeting.action_items.map((it) =>
        it.id === id ? { ...it, han_chot: due } : it
      ),
    });
  }

  function updateActionTitle(id: string, title: string) {
    if (!meeting) return;
    setMeeting({
      ...meeting,
      action_items: meeting.action_items.map((it) =>
        it.id === id ? { ...it, tieu_de: title } : it
      ),
    });
  }

  function addActionItem() {
    if (!meeting) return;
    const newItem: ActionItem = {
      id: `act_${Date.now().toString().slice(-4)}`,
      tieu_de: "Việc mới cần làm",
      noi_dung_chi_tiet: "",
      ten_nguoi_nhan: "Chưa rõ",
      loai_cong_viec: "1_ca",
      tinh_chat: "bat_buoc",
      pham_vi: "ca_nhan",
      han_chot: "Hết ca",
      muc_do_uu_tien: "trung_binh",
      do_tin_cay: 1.0,
      da_chon: true,
      can_lam_ro: true,
      van_de_ngu_canh: "Công việc mới thêm cần chỉ định người phụ trách và ca làm việc",
      cau_hoi_lam_ro: "Bạn muốn phân công việc mới này cho ai và vào ca trực nào?",
      goi_y_xu_ly: ["Giao cho nhân viên ca hiện tại", "Giao cho Quản lý", "Chuyển thành việc chung cả ca"],
    };
    setMeeting({
      ...meeting,
      action_items: [newItem, ...meeting.action_items],
    });
  }

  function removeActionItem(id: string) {
    if (!meeting) return;
    setMeeting({
      ...meeting,
      action_items: meeting.action_items.filter((it) => it.id !== id),
    });
  }

  function updateActionWorkType(id: string, type: "1_ca" | "nhieu_ca" | "gop_y") {
    if (!meeting) return;
    setMeeting({
      ...meeting,
      action_items: meeting.action_items.map((it) =>
        it.id === id ? { ...it, loai_cong_viec: type } : it
      ),
    });
  }

  function updateActionCaThucHien(id: string, ca: string) {
    if (!meeting) return;
    setMeeting({
      ...meeting,
      action_items: meeting.action_items.map((it) =>
        it.id === id ? { ...it, ca_thuc_hien: ca } : it
      ),
    });
  }

  function convertActionToFeedback(id: string) {
    if (!meeting) return;
    const item = meeting.action_items.find((a) => a.id === id);
    if (!item) return;
    const newFb = {
      id: `fb_${Date.now().toString().slice(-4)}`,
      nguoi_gop_y: item.ten_nguoi_giao || (manager ? "Quản lý" : "Giao ca"),
      nguoi_nhan: item.ten_nguoi_nhan || "Tất cả",
      chu_de: "luu_y_chung" as const,
      tinh_chat: "gop_y" as const,
      noi_dung: item.tieu_de,
      ghi_chu: item.noi_dung_chi_tiet || "Chuyển từ việc giao sang góp ý làm việc",
    };
    setMeeting({
      ...meeting,
      action_items: meeting.action_items.filter((a) => a.id !== id),
      gop_y_luu_y: [newFb, ...(meeting.gop_y_luu_y || [])],
    });
    setSuccess(`Đã chuyển việc "${item.tieu_de}" sang mục Góp ý & lưu ý nội bộ!`);
  }

  async function clarifyActions() {
    if (!meeting || !meeting.action_items || meeting.action_items.length === 0) return;
    setBusy(true);
    setStatusMsg("AI đang rà soát ngữ cảnh & đối soát lịch ca nhân sự...");
    try {
      const res = await apiSend<{ ok: boolean; action_items: ActionItem[] }>(
        "/api/v1/meeting/clarify-actions",
        {
          action_items: meeting.action_items,
          transcript: liveTranscript || "",
        }
      );
      if (res.ok && res.action_items) {
        setMeeting({
          ...meeting,
          action_items: res.action_items,
        });
        setSuccess("AI đã rà soát xong ngữ cảnh phân công và lịch ca!");
      }
    } catch (e) {
      setError(viError(e, { doing: "rà soát ngữ cảnh phân công" }));
    } finally {
      setBusy(false);
      setStatusMsg("");
    }
  }

  function resolveClarification(id: string, solution: string) {
    if (!meeting) return;
    const sol = solution.trim();
    const solLower = sol.toLowerCase();

    if (
      solLower.includes("chuyển sang góp ý") ||
      solLower.includes("góp ý nội bộ") ||
      solLower.includes("chuyển thành góp ý")
    ) {
      convertActionToFeedback(id);
      return;
    }

    setMeeting({
      ...meeting,
      action_items: meeting.action_items.map((it) => {
        if (it.id !== id) return it;

        let newDue = it.han_chot;
        let newCa = it.ca_thuc_hien;
        let newType = it.loai_cong_viec || "1_ca";
        let newAssignee = it.ten_nguoi_nhan;

        // Detect deadline cues
        if (solLower.includes("hết ca")) {
          const matchTime = sol.match(/\(([^)]+)\)/);
          newDue = matchTime ? `Trước ${matchTime[1]}` : "Trước khi hết ca";
        } else if (solLower.includes("đầu ca")) {
          const matchTime = sol.match(/\(([^)]+)\)/);
          newDue = matchTime ? `Lúc ${matchTime[1]}` : "Đầu ca";
        } else if (/\b\d{1,2}:\d{2}\b/.test(sol)) {
          const m = sol.match(/\b\d{1,2}:\d{2}\b/);
          if (m) newDue = m[0];
        } else if (/\b\d{1,2}h\b/.test(solLower)) {
          const m = solLower.match(/\b\d{1,2}h\b/);
          if (m) newDue = m[0];
        }

        // Detect multi-shift / scope cues
        if (
          solLower.includes("nhiều ca") ||
          solLower.includes("xuyên suốt") ||
          solLower.includes("định kỳ") ||
          solLower.includes("trong tuần")
        ) {
          newType = "nhieu_ca";
          newCa = "Xuyên suốt các ca tuần này";
        }

        // Detect assignee cues: "Giao cho Lan", "chuyển cho Tuấn", "Quản lý"
        if (solLower.includes("giao cho") || solLower.includes("chuyển cho")) {
          const match = sol.match(/(?:giao cho|chuyển cho)\s+([^\s,(]+)/i);
          if (match && match[1]) newAssignee = match[1];
        } else if (solLower.includes("quản lý")) {
          newAssignee = "Quản lý";
        }

        return {
          ...it,
          ten_nguoi_nhan: newAssignee,
          han_chot: newDue,
          ca_thuc_hien: newCa,
          loai_cong_viec: newType,
          can_lam_ro: false,
        };
      }),
    });
    setSuccess(`Đã áp dụng làm rõ: "${solution}"`);
  }

  function updateProposalStatus(id: string, status: "da_duyet" | "cho_duyet" | "tu_choi") {
    if (!meeting) return;
    setMeeting({
      ...meeting,
      de_xuat_phe_duyet: (meeting.de_xuat_phe_duyet || []).map((p) =>
        p.id === id ? { ...p, trang_thai: status } : p
      ),
    });
  }

  async function deleteMeeting(id: string) {
    if (typeof window !== "undefined" && !window.confirm("Bạn có chắc chắn muốn xoá biên bản cuộc họp này khỏi lịch sử?")) {
      return;
    }
    setBusy(true);
    try {
      await apiSend(`/api/v1/meetings/${encodeURIComponent(id)}`, null, "DELETE");
      setSuccess("Đã xoá cuộc họp thành công!");
      if (meeting?.id === id) {
        setMeeting(null);
      }
      loadHistory();
    } catch (e) {
      setError(viError(e, { doing: "xoá cuộc họp" }));
    } finally {
      setBusy(false);
    }
  }

  const formatTimer = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  if (!token) return <AuthGate />;

  return (
    <div className="nq-page nq-page--wide space-y-6">
      <PageHeader
        kicker="Ghi nhận · tổng hợp · gửi nhóm"
        title="Họp & giao ca"
        meta="Thu âm hoặc tải ghi chép, trích xuất việc cần làm và soạn nội dung để gửi vào nhóm của quán."
      />

      {error && <Alert kind="err">{error}</Alert>}
      {success && <Alert kind="ok">{success}</Alert>}

      {/* 1. INPUT HUB */}
      <OpsCard title="Thu thập cuộc họp">
        <div className="space-y-4">
          <TabBar>
            <TabButton active={inputMode === "mic"} onClick={() => { setInputMode("mic"); setError(null); }}>
              Micro giao ca
            </TabButton>
            <TabButton active={inputMode === "meet"} onClick={() => { setInputMode("meet"); setError(null); }}>
              Google Meet
            </TabButton>
            <TabButton active={inputMode === "upload"} onClick={() => { setInputMode("upload"); setError(null); }}>
              Tải audio
            </TabButton>
            <TabButton active={inputMode === "text"} onClick={() => { setInputMode("text"); setError(null); }}>
              Dán ghi chép
            </TabButton>
          </TabBar>

          <div className="flex flex-wrap items-center gap-2 justify-end">
              <span className="text-xs opacity-75 font-mono uppercase">Loại họp:</span>
              <select
                value={meetingType}
                onChange={(e) => setMeetingType(e.target.value as "giao_ca" | "hop_tuan" | "dao_tao")}
                className="bg-[var(--nq-surface)] text-white text-sm p-1.5 rounded border border-[var(--nq-line)] font-mono"
              >
                <option value="giao_ca">Họp Giao ca (Standup)</option>
                <option value="hop_tuan">Họp Tuần / Vận hành</option>
                <option value="dao_tao">Đào tạo / Phổ biến SOP</option>
              </select>
            </div>

          {/* Mode 1: Microphone Live Recording */}
          {inputMode === "mic" && (
            <div className={`nq-meeting-input ${isRecording ? "nq-meeting-input--live" : ""} space-y-3`}>
              <div className="text-sm">
                <p className="font-bold">Ghi âm trực tiếp tại quầy</p>
                <p className="nq-muted mt-1 text-sm">
                  Bấm bắt đầu và nói tự nhiên. Lời nói chuyển thành văn bản thời gian thực trên màn hình.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4 pt-2">
                {!isRecording ? (
                  <Btn variant="primary" onClick={startMicRecording} disabled={busy}>
                    Bắt đầu ghi âm giao ca
                  </Btn>
                ) : (
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="animate-ping w-3 h-3 rounded-full bg-[var(--nq-st-danger)] inline-block" />
                    <span className="font-mono text-[var(--nq-st-danger-ink)] font-bold text-lg">ĐANG THU: {formatTimer(recordSeconds)}</span>
                    
                    {/* Audio Level Indicator */}
                    <div className="flex items-center gap-1.5 bg-[var(--nq-bg-elevated)] px-3 py-1.5 rounded border border-[var(--nq-line)]">
                      <span className="text-xs font-mono opacity-60">ÂM LƯỢNG:</span>
                      <div className="w-20 bg-[var(--nq-surface)] h-2 rounded overflow-hidden">
                        <div
                          className="bg-[var(--nq-st-ok)] h-full transition-all duration-100"
                          style={{ width: `${volumeLevel}%` }}
                        />
                      </div>
                    </div>

                    <Btn variant="danger" onClick={stopRecording}>
                      Hoàn tất & trích xuất
                    </Btn>
                  </div>
                )}
              </div>

              {/* Live Speech Recognition Subtitle Box */}
              {isRecording && (
                <div className="nq-meeting-live space-y-1">
                  <div className="flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-widest text-[var(--nq-accent)]">
                    <span className="h-2 w-2 rounded-full bg-[var(--nq-accent)]" />
                    Văn bản đang nói trực tiếp
                  </div>
                  <p className="min-h-[2.5rem] text-sm italic">
                    {liveTranscript} <span className="text-[var(--nq-accent)] underline">{interimText}</span>
                    {!liveTranscript && !interimText && "Đang lắng nghe giọng nói qua micro…"}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Mode 2: Google Meet Tab Audio Capture */}
          {inputMode === "meet" && (
            <div className={`nq-meeting-input ${isRecording ? "nq-meeting-input--live" : ""} space-y-3`}>
              <div className="text-sm">
                <p className="font-bold">Bắt âm thanh từ tab Google Meet</p>
                <p className="nq-muted mt-1 text-sm">
                  Khi bắt đầu, chọn tab <strong>Google Meet</strong> và tích{" "}
                  <strong>Chia sẻ âm thanh thẻ</strong>. Hệ thống gộp âm thanh phòng họp và giọng của bạn.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4 pt-2">
                {!isRecording ? (
                  <Btn variant="primary" onClick={startMeetCapture} disabled={busy}>
                    Bắt đầu theo dõi Google Meet
                  </Btn>
                ) : (
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="animate-ping w-3 h-3 rounded-full bg-[var(--nq-st-danger)] inline-block" />
                    <span className="font-mono text-[var(--nq-st-danger-ink)] font-bold text-lg">ĐANG GHI ÂM: {formatTimer(recordSeconds)}</span>

                    <div className="flex items-center gap-1.5 bg-[var(--nq-bg-elevated)] px-3 py-1.5 rounded border border-[var(--nq-line)]">
                      <span className="text-xs font-mono opacity-60">ÂM LƯỢNG:</span>
                      <div className="w-20 bg-[var(--nq-surface)] h-2 rounded overflow-hidden">
                        <div
                          className="bg-[var(--nq-st-info)] h-full transition-all duration-100"
                          style={{ width: `${volumeLevel}%` }}
                        />
                      </div>
                    </div>

                    <Btn variant="danger" onClick={stopRecording}>
                      Dừng & phân tích AI
                    </Btn>
                  </div>
                )}
              </div>

              {isRecording && (
                <div className="nq-meeting-live space-y-1">
                  <div className="flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-widest text-[var(--nq-accent)]">
                    <span className="h-2 w-2 rounded-full bg-[var(--nq-accent)]" />
                    Văn bản thu từ cuộc họp
                  </div>
                  <p className="min-h-[2.5rem] text-sm italic">
                    {liveTranscript} <span className="text-[var(--nq-accent)] underline">{interimText}</span>
                    {!liveTranscript && !interimText && "Đang lắng nghe âm thanh từ Google Meet…"}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Mode 3: File Upload */}
          {inputMode === "upload" && (
            <div className="nq-meeting-input space-y-3">
              <Field label="Chọn file âm thanh (.mp3, .m4a, .wav, .webm)">
                <input
                  type="file"
                  accept="audio/*,.mp3,.m4a,.wav,.webm"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  className="text-sm text-[var(--nq-ink)] file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-copper file:text-white hover:file:opacity-90"
                />
              </Field>
              <Btn variant="primary" onClick={uploadFile} disabled={busy || !selectedFile}>
                Tải lên & phân tích
              </Btn>
            </div>
          )}

          {/* Mode 4: Text Input */}
          {inputMode === "text" && (
            <div className="nq-meeting-input space-y-4">
              <Field label="Nội dung ghi chép cuộc họp" hint="Dán biên bản hoặc nội dung trao đổi. Mỗi dòng nên ghi rõ người nói.">
                <Textarea
                  rows={10}
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  placeholder={"Quản lý: …\nNhân viên: …"}
                />
              </Field>
              <Btn variant="primary" onClick={analyzeText} disabled={busy}>
                Phân tích biên bản
              </Btn>
            </div>
          )}

          {busy && (
            <div className="nq-meeting-input flex items-center gap-3">
              <Loading />
              <span className="text-sm font-mono text-[var(--nq-ink-muted)]">{statusMsg || "Đang xử lý…"}</span>
            </div>
          )}
        </div>
      </OpsCard>

      {/* 2. RESULTS */}
      {meeting ? (
        <OpsCard title={`Kết quả phân tích: ${meeting.tieu_de}`}>
          <MeetingResults
            meeting={meeting}
            liveTranscript={liveTranscript}
            manager={manager}
            busy={busy}
            copiedBroadcast={copiedBroadcast}
            onCopyBroadcast={handleCopyBroadcast}
            onToggleAction={toggleActionItem}
            onUpdateAssignee={updateActionAssignee}
            onUpdateDue={updateActionDue}
            onUpdateActionTitle={updateActionTitle}
            onAddActionItem={addActionItem}
            onRemoveActionItem={removeActionItem}
            onUpdateProposalStatus={updateProposalStatus}
            onUpdateWorkType={updateActionWorkType}
            onUpdateCaThucHien={updateActionCaThucHien}
            onConvertToFeedback={convertActionToFeedback}
            onClarifyActions={clarifyActions}
            onResolveClarification={resolveClarification}
            onApply={applyDecisions}
          />
        </OpsCard>
      ) : null}

      {/* 3. PAST MEETINGS HISTORY */}
      {pastMeetings.length > 0 && (
        <OpsCard title="Lịch sử cuộc họp đã duyệt">
          <div className="nq-meeting-list">
            {pastMeetings.map((m) => (
              <div key={m.id} className="nq-meeting-list__item flex items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="nq-meeting-list__title">{m.tieu_de}</h4>
                    <span className="text-2xs px-2 py-0.5 rounded font-mono bg-[var(--nq-st-ok-soft)] text-[var(--nq-st-ok-ink)] border border-[color-mix(in_srgb,var(--nq-st-ok)_46%,var(--nq-line))]">
                      ĐÃ DUYỆT
                    </span>
                  </div>
                  <p className="nq-meeting-list__meta line-clamp-1">{m.tom_tat}</p>
                  <div className="mt-1 flex flex-wrap gap-3 text-2xs font-mono text-[var(--nq-ink-muted)]">
                    <span>Loại: {m.loai_hop}</span>
                    <span>Việc: {m.action_items?.length || 0}</span>
                    <span>Nguồn: {m.nguon_am_thanh}</span>
                    {m.duyet_luc && (
                      <span>Duyệt: {new Date(m.duyet_luc).toLocaleDateString("vi-VN")}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Btn
                    variant="ghost"
                    onClick={() => {
                      setMeeting(m);
                      window.scrollTo({ top: 400, behavior: "smooth" });
                    }}
                  >
                    Xem lại
                  </Btn>
                  {manager && (
                    <Btn
                      variant="danger"
                      onClick={() => deleteMeeting(m.id)}
                      disabled={busy}
                    >
                      Xoá
                    </Btn>
                  )}
                </div>
              </div>
            ))}
          </div>
        </OpsCard>
      )}
    </div>
  );
}
