"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "../../lib/session";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INPUT_RATE = 16000;
const OUTPUT_RATE = 24000;

export type VoiceState =
  | "idle"
  | "connecting"
  | "listening"
  | "processing"
  | "speaking"
  | "error"
  | "mic_denied"
  | "mic_not_found"
  | "superseded"
  | "idle_timeout";

export type VoiceInputMode = "open_mic" | "push_to_talk";

export interface MicDeviceInfo {
  deviceId: string;
  label: string;
}

export interface VoiceProposalData {
  reply_text: string;
  intent: string;
  action_proposal: import("./ActionProposalCard").ActionProposalData | null;
  citations: string[];
  agent_mode: string;
}

export interface UseCopilotVoiceOptions {
  onTranscript?: (role: "user" | "copilot", text: string, isFinal: boolean) => void;
  onInterrupted?: () => void;
  onProposal?: (data: VoiceProposalData) => void;
  inputMode?: VoiceInputMode;
  deviceId?: string;
  noiseFloor?: number;
  /** Callback nhận mức amplitude (0-1) của audio trợ lý đang phát, dùng cho lip-sync avatar. */
  onAudioLevel?: (level: number) => void;
}

// Ngưỡng cũ (0.01) bỏ luôn cả tiếng nói nhỏ/xa mic: frame dưới ngưỡng bị
// drop hoàn toàn nên Gemini nhận khoảng lặng nhân tạo giữa câu và tưởng user
// đã nói xong. Hạ xuống 0.004 — vẫn cắt được hum/rumble nhưng không cắt giọng.
export const DEFAULT_NOISE_FLOOR = 0.004;

// Sau khi có tiếng nói, vẫn gửi audio trong khoảng này kể cả dưới ngưỡng.
// Nhờ vậy đuôi câu và khoảng nghỉ ngắn giữa các từ không bị cắt vụn.
const GATE_HOLD_MS = 700;

function voiceUrl(): string {
  return `${API_BASE.replace(/^http/, "ws")}/api/v1/copilot/voice`;
}

function rms(frame: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < frame.length; i += 1) {
    sum += frame[i] * frame[i];
  }
  return Math.sqrt(sum / frame.length);
}

async function acquireMicStream(deviceId?: string): Promise<MediaStream> {
  const baseConstraints: MediaTrackConstraints = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
    sampleRate: 16000,
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
  };

  const chromeExtraConstraints = {
    ...baseConstraints,
    googNoiseSuppression: true,
    googHighpassFilter: true, // Cut AC hum, fan rumble
    googEchoCancellation: true,
  } as MediaTrackConstraints;

  try {
    return await navigator.mediaDevices.getUserMedia({ audio: chromeExtraConstraints });
  } catch {
    return await navigator.mediaDevices.getUserMedia({ audio: baseConstraints });
  }
}

async function enumerateMics(): Promise<MicDeviceInfo[]> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
    return [];
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices
      .filter((d) => d.kind === "audioinput")
      .map((d, index) => ({
        deviceId: d.deviceId,
        label: d.label || `Microphone ${index + 1}`,
      }));
  } catch {
    return [];
  }
}

function pcm16AtRate(input: Float32Array, sourceRate: number, targetRate: number): ArrayBuffer {
  if (sourceRate === targetRate) {
    const direct = new ArrayBuffer(input.length * 2);
    const directView = new DataView(direct);
    for (let i = 0; i < input.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, input[i] ?? 0));
      directView.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }
    return direct;
  }
  // Lấy mẫu theo tỉ lệ + trung bình cộng các mẫu nguồn trong khoảng tương ứng.
  // Cách cũ (nearest-neighbor) gây aliasing → Gemini nghe méo, nhận dạng sai.
  const ratio = sourceRate / targetRate;
  const length = Math.max(1, Math.round(input.length / ratio));
  const output = new ArrayBuffer(length * 2);
  const view = new DataView(output);
  for (let index = 0; index < length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(input.length, Math.max(start + 1, Math.floor((index + 1) * ratio)));
    let sum = 0;
    for (let i = start; i < end; i += 1) sum += input[i] ?? 0;
    const sample = Math.max(-1, Math.min(1, sum / (end - start)));
    view.setInt16(index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return output;
}

function playPcm16(
  data: string,
  context: AudioContext,
  nextTime: { value: number },
  sources: Set<AudioBufferSourceNode>,
  onQueueEnded: () => void,
  analyser?: AnalyserNode,
): void {
  const binary = atob(data);
  const samples = new Int16Array(binary.length / 2);
  for (let index = 0; index < samples.length; index += 1) {
    samples[index] = (binary.charCodeAt(index * 2) | (binary.charCodeAt(index * 2 + 1) << 8));
  }
  const buffer = context.createBuffer(1, samples.length, OUTPUT_RATE);
  const channel = buffer.getChannelData(0);
  for (let index = 0; index < samples.length; index += 1) channel[index] = samples[index] / 0x8000;
  const source = context.createBufferSource();
  source.buffer = buffer;
  // Chèn AnalyserNode vào đường audio để đo amplitude cho lip-sync avatar.
  // LƯU Ý: analyser đã được connect tới destination MỘT LẦN tại lúc tạo
  // (trong start()). Ở đây chỉ connect source → analyser, KHÔNG connect
  // analyser → destination nữa để tránh audio bị phát gấp đôi.
  if (analyser) {
    source.connect(analyser);
  } else {
    source.connect(context.destination);
  }
  sources.add(source);
  source.onended = () => {
    sources.delete(source);
    if (sources.size === 0) onQueueEnded();
  };
  nextTime.value = Math.max(nextTime.value, context.currentTime);
  source.start(nextTime.value);
  nextTime.value += buffer.duration;
}

export function useCopilotVoice(options?: UseCopilotVoiceOptions) {
  const [state, setState] = useState<VoiceState>("idle");
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const inputModeRef = useRef<VoiceInputMode>(options?.inputMode || "open_mic");
  inputModeRef.current = options?.inputMode || "open_mic";
  const deviceIdRef = useRef<string | undefined>(options?.deviceId);
  deviceIdRef.current = options?.deviceId;
  const noiseFloorRef = useRef<number>(options?.noiseFloor ?? DEFAULT_NOISE_FLOOR);
  noiseFloorRef.current = options?.noiseFloor ?? DEFAULT_NOISE_FLOOR;
  const onAudioLevelRef = useRef<((level: number) => void) | undefined>(options?.onAudioLevel);
  onAudioLevelRef.current = options?.onAudioLevel;
  const isPttSpeakingRef = useRef(false);
  const [availableMics, setAvailableMics] = useState<MicDeviceInfo[]>([]);
  const [isPttSpeaking, setIsPttSpeaking] = useState(false);

  useEffect(() => {
    void enumerateMics().then((mics) => {
      if (mics.length > 0) setAvailableMics(mics);
    });
  }, []);

  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const inputContextRef = useRef<AudioContext | null>(null);
  const outputContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const nextOutputTimeRef = useRef({ value: 0 });
  const outputSourcesRef = useRef(new Set<AudioBufferSourceNode>());
  const turnCompleteRef = useRef(false);
  const failedRef = useRef(false);
  const userStoppedRef = useRef(false);
  const tabHiddenRef = useRef(false);
  // Mốc thời gian frame cuối có tiếng nói — dùng cho noise gate "hold".
  const lastVoiceAtRef = useRef(0);
  // Lip-sync: AnalyserNode đo amplitude audio trợ lý đang phát.
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioLevelRef = useRef(0);
  const levelTimerRef = useRef<number | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);

  // Pause audio sending when tab is hidden for > 15s to save quota.
  // Khi quay lại tab, hạ cờ NGAY và bỏ hẳn frame đang dở — nếu không thì
  // đoạn hội thoại đầu tiên sau khi quay lại bị mất im lặng.
  useEffect(() => {
    let hideTimer: ReturnType<typeof setTimeout> | null = null;
    const handleVisibilityChange = () => {
      if (document.hidden) {
        hideTimer = setTimeout(() => {
          tabHiddenRef.current = true;
        }, 15000);
      } else {
        if (hideTimer) clearTimeout(hideTimer);
        tabHiddenRef.current = false;
        // Mốc gate cũ đã lỗi thời sau khi tab ẩn → tránh gửi nhầm frame cũ.
        lastVoiceAtRef.current = 0;
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      if (hideTimer) clearTimeout(hideTimer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  const stop = useCallback(() => {
    userStoppedRef.current = true;
    if (socketRef.current) {
      socketRef.current.onclose = null;
      socketRef.current.onmessage = null;
      socketRef.current.onerror = null;
      socketRef.current.onopen = null;
    }
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ event: "stop" }));
    }
    socketRef.current?.close();
    socketRef.current = null;
    processorRef.current?.disconnect();
    processorRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    for (const source of outputSourcesRef.current) source.stop();
    outputSourcesRef.current.clear();
    turnCompleteRef.current = false;
    nextOutputTimeRef.current.value = 0;
    if (levelTimerRef.current) {
      window.clearInterval(levelTimerRef.current);
      levelTimerRef.current = null;
    }
    analyserRef.current = null;
    audioLevelRef.current = 0;
    setAudioLevel(0);
    void inputContextRef.current?.close();
    void outputContextRef.current?.close();
    inputContextRef.current = null;
    outputContextRef.current = null;
    isPttSpeakingRef.current = false;
    setIsPttSpeaking(false);
    setState("idle");
  }, []);

  const start = useCallback(async () => {
    if (
      state !== "idle" &&
      state !== "error" &&
      state !== "mic_denied" &&
      state !== "mic_not_found" &&
      state !== "superseded" &&
      state !== "idle_timeout"
    ) {
      return;
    }
    const token = getToken();
    if (!token) {
      setState("error");
      return;
    }
    userStoppedRef.current = false;
    failedRef.current = false;
    setState("connecting");
    try {
      // Xin quyền micro TRƯỚC TIÊN, ngay trong ngữ cảnh click của người dùng.
      // Nếu gọi sau khi await WebSocket + chờ voice:ready, transient activation
      // đã hết hạn → trình duyệt từ chối im lặng (NotAllowedError) mà KHÔNG hiện
      // hộp thoại hỏi quyền micro.
      const stream = await acquireMicStream(deviceIdRef.current);
      void enumerateMics().then((mics) => {
        if (mics.length > 0) setAvailableMics(mics);
      });

      const socket = new WebSocket(voiceUrl());
      socket.binaryType = "arraybuffer";
      socketRef.current = socket;
      const inputContext = new AudioContext();
      const outputContext = new AudioContext();
      inputContextRef.current = inputContext;
      outputContextRef.current = outputContext;
      // Lip-sync: tạo AnalyserNode trên đường audio phát để đo amplitude.
      // Connect analyser → destination đúng MỘT LẦN; các audio chunk chỉ
      // connect source → analyser (xem playPcm16).
      const analyser = outputContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.6;
      analyser.connect(outputContext.destination);
      analyserRef.current = analyser;
      const levelBuffer = new Uint8Array(analyser.frequencyBinCount);
      // Dọn interval cũ (nếu có) trước khi tạo mới để tránh chồng chất.
      if (levelTimerRef.current) {
        window.clearInterval(levelTimerRef.current);
        levelTimerRef.current = null;
      }
      const LEVEL_UPDATE_THRESHOLD = 0.02;
      let lastReported = 0;
      const levelTimer = window.setInterval(() => {
        if (analyserRef.current !== analyser) return;
        analyser.getByteTimeDomainData(levelBuffer);
        let peak = 0;
        for (let i = 0; i < levelBuffer.length; i += 1) {
          const v = Math.abs(levelBuffer[i] - 128) / 128;
          if (v > peak) peak = v;
        }
        // Làm mượt: giữ mức cao hơn một chút để miệng không nhấp nháy quá nhanh.
        const smoothed = Math.max(peak, audioLevelRef.current * 0.7);
        audioLevelRef.current = smoothed;
        // Chỉ báo trạng thái khi có thay đổi đáng kể để tránh re-render liên tục.
        if (Math.abs(smoothed - lastReported) >= LEVEL_UPDATE_THRESHOLD) {
          lastReported = smoothed;
          setAudioLevel(smoothed);
          onAudioLevelRef.current?.(smoothed);
        }
      }, 40);
      levelTimerRef.current = levelTimer;
      await new Promise<void>((resolve, reject) => {
        let ready = false;
        const fail = (reason: string) => {
          if (!ready) {
            reject(new Error(reason));
          } else {
            failedRef.current = true;
            stop();
            setState("error");
          }
        };
        socket.onopen = () => {
          socket.send(JSON.stringify({ event: "auth", token }));
        };
        socket.onmessage = (message) => {
          let payload: { event?: string; data?: any };
          try {
            payload = JSON.parse(String(message.data)) as { event?: string; data?: any };
          } catch {
            fail("voice_invalid_response");
            return;
          }
          if (payload.event === "voice:ready") {
            ready = true;
            setState("listening");
            resolve();
          } else if (payload.event === "voice:error") {
            fail(payload.data?.code || "voice_error");
          } else if (payload.event === "voice:ended") {
            if (payload.data?.code === "max_duration_reached") {
              stop();
            }
          } else if (payload.event === "voice:proposal") {
            // Kết quả pipeline nghiệp vụ (reply + ActionProposal) từ server.
            optionsRef.current?.onProposal?.(payload.data as VoiceProposalData);
          } else if (payload.event === "voice:upstream") {
            const event = payload.data || {};
            const serverContent = event.serverContent || {};
            if (serverContent.interrupted === true) {
              for (const source of outputSourcesRef.current) source.stop();
              outputSourcesRef.current.clear();
              nextOutputTimeRef.current.value = outputContext.currentTime;
              turnCompleteRef.current = false;
              setState("listening");
              optionsRef.current?.onInterrupted?.();
              return;
            }

            const isTurnComplete = Boolean(serverContent.turnComplete);

            // User speech transcript from Gemini Live
            const inputTranscription = serverContent.inputAudioTranscription?.text;
            if (inputTranscription && optionsRef.current?.onTranscript) {
              optionsRef.current.onTranscript("user", inputTranscription, isTurnComplete);
            }

            // Assistant speech transcript
            const outputTranscription = serverContent.outputAudioTranscription?.text;
            if (outputTranscription && optionsRef.current?.onTranscript) {
              optionsRef.current.onTranscript("copilot", outputTranscription, isTurnComplete);
            }

            const status =
              serverContent.interactionStatus ||
              serverContent.interaction_status ||
              event.interactionStatus ||
              event.interaction_status;
            if (
              status === "thinking" ||
              status === "processing" ||
              status === "in_progress" ||
              status === "IN_PROGRESS"
            ) {
              turnCompleteRef.current = false;
              setState("processing");
            }
            if (serverContent.turnComplete === true) {
              turnCompleteRef.current = true;
              if (outputSourcesRef.current.size === 0) setState("listening");
            }
            const parts = serverContent.modelTurn?.parts || [];
            for (const part of parts) {
              if (part.text && !outputTranscription && optionsRef.current?.onTranscript) {
                optionsRef.current.onTranscript("copilot", part.text, isTurnComplete);
              }
              const audio = part.inlineData?.data || part.inline_data?.data;
              if (audio) {
                setState("speaking");
                playPcm16(
                  audio,
                  outputContext,
                  nextOutputTimeRef.current,
                  outputSourcesRef.current,
                  () => {
                    if (turnCompleteRef.current) setState("listening");
                  },
                  analyser,
                );
              }
            }
          }
        };
        socket.onerror = () => fail("voice_connection_failed");
        socket.onclose = (ev) => {
          if (userStoppedRef.current) {
            setState("idle");
          } else if (ev.code === 4002) {
            setState("superseded");
          } else if (ev.code === 4005) {
            setState("idle_timeout");
          } else if (!ready) {
            reject(new Error("voice_connection_closed"));
          } else if (!failedRef.current) {
            stop();
          }
        };
      });

      if (socketRef.current !== socket || socket.readyState !== WebSocket.OPEN) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      await Promise.all([inputContext.resume(), outputContext.resume()]);
      const source = inputContext.createMediaStreamSource(stream);
      const processor = inputContext.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (event) => {
        if (socket.readyState !== WebSocket.OPEN || tabHiddenRef.current) {
          return;
        }
        // In push_to_talk mode, only stream audio when user is actively holding the button
        if (inputModeRef.current === "push_to_talk" && !isPttSpeakingRef.current) {
          return;
        }
        const channelData = event.inputBuffer.getChannelData(0);
        // Noise gate có "hold": khi đang có tiếng nói thì vẫn gửi audio thêm
        // GATE_HOLD_MS kể cả frame yên tĩnh, để không cắt vụn đuôi câu và
        // khoảng nghỉ ngắn giữa các từ.
        const now = performance.now();
        if (rms(channelData) >= noiseFloorRef.current) {
          lastVoiceAtRef.current = now;
        }
        if (now - lastVoiceAtRef.current > GATE_HOLD_MS) {
          return;
        }
        socket.send(pcm16AtRate(channelData, inputContext.sampleRate, INPUT_RATE));
      };
      source.connect(processor);
      // Mute node to prevent microphone feedback loop back into speakers
      const muteNode = inputContext.createGain();
      muteNode.gain.value = 0;
      processor.connect(muteNode);
      muteNode.connect(inputContext.destination);
      processorRef.current = processor;
    } catch (err: any) {
      if (userStoppedRef.current) return;
      failedRef.current = true;
      stop();
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        setState("mic_denied");
      } else if (err instanceof DOMException && err.name === "NotFoundError") {
        setState("mic_not_found");
      } else {
        setState("error");
      }
    }
  }, [state, stop]);

  const startPttTalk = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      isPttSpeakingRef.current = true;
      setIsPttSpeaking(true);
      socketRef.current.send(JSON.stringify({ event: "activity_start" }));
    }
  }, []);

  const stopPttTalk = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      isPttSpeakingRef.current = false;
      setIsPttSpeaking(false);
      socketRef.current.send(JSON.stringify({ event: "activity_end" }));
    }
  }, []);

  const changeMic = useCallback(async (newDeviceId: string) => {
    deviceIdRef.current = newDeviceId;
    if (streamRef.current && inputContextRef.current && processorRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      try {
        const newStream = await acquireMicStream(newDeviceId);
        streamRef.current = newStream;
        const newSource = inputContextRef.current.createMediaStreamSource(newStream);
        newSource.connect(processorRef.current);
      } catch {
        // Leave existing if failed
      }
    }
  }, []);

  useEffect(() => stop, [stop]);

  return {
    state,
    start,
    stop,
    startPttTalk,
    stopPttTalk,
    isPttSpeaking,
    availableMics,
    changeMic,
    audioLevel,
  };
}
