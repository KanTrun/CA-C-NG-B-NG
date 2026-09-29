"use client";

/**
 * GuestJourney — hành trình khách CHẠY ĐƯỢC: order → pha chế → trả → phản hồi.
 *
 * Đây là mô phỏng có TƯƠNG TÁC (bấm để chạy từng bước), không phải hình tĩnh.
 * Nếu có đơn thật (`/quanverse/stations` cho biết số đơn), hành trình phản ánh
 * đúng trạng thái vận hành; nếu chưa có, chạy kịch bản mẫu có NHÃN rõ.
 *
 * Không mutation: chỉ mô phỏng luồng, không ghi vào đơn/lịch thật.
 */

import { useCallback, useEffect, useState } from "react";
import { Icon } from "../../icons";

const BUOC = [
  { id: "order", ten: "Đặt món", desc: "Khách chọn món, gửi đơn xuống quầy." },
  { id: "pha", ten: "Pha chế", desc: "Pha chế nhận đơn, chuẩn bị đồ uống." },
  { id: "tra", ten: "Trả khách", desc: "Thu ngân gọi tên, giao đồ uống." },
  { id: "phan_hoi", ten: "Phản hồi", desc: "Khách để lại cảm nhận cho quán." },
] as const;

type BuocId = (typeof BUOC)[number]["id"];

export default function GuestJourney({ coDonThat }: { coDonThat: boolean }) {
  const [step, setStep] = useState(0); // 0..BUOC.length (length = xong)
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const advance = useCallback(() => {
    setStep((s) => {
      if (s >= BUOC.length) return s;
      const b = BUOC[s];
      setLog((l) => [`${new Date().toLocaleTimeString("vi-VN")} · ${b.ten}`, ...l].slice(0, 6));
      return s + 1;
    });
  }, []);

  // Tự chạy từng bước khi bật "chạy tự động".
  useEffect(() => {
    if (!running) return;
    if (step >= BUOC.length) {
      setRunning(false);
      return;
    }
    const t = setTimeout(advance, 900);
    return () => clearTimeout(t);
  }, [running, step, advance]);

  const reset = useCallback(() => {
    setStep(0);
    setRunning(false);
    setLog([]);
  }, []);

  return (
    <div className="nq-journey">
      <p className="nq-journey__note">
        {coDonThat
          ? "Phản ánh luồng đơn thật của quán hôm nay."
          : "Chưa có đơn thật — đang chạy kịch bản MẪU (bấm để xem luồng)."}
      </p>
      <ol className="nq-journey__steps" data-testid="guest-journey">
        {BUOC.map((b, i) => {
          const done = i < step;
          const active = i === step;
          return (
            <li
              key={b.id}
              className={`nq-journey__step${done ? " is-done" : ""}${active ? " is-active" : ""}`}
              data-buoc={b.id satisfies BuocId}
            >
              <span className="nq-journey__num">
                {done ? <Icon name="check" size={13} /> : i + 1}
              </span>
              <span className="nq-journey__body">
                <span className="nq-journey__ten">{b.ten}</span>
                <span className="nq-journey__desc">{b.desc}</span>
              </span>
            </li>
          );
        })}
      </ol>
      <div className="nq-journey__actions">
        <button
          type="button"
          className="nq-btn-compact"
          onClick={advance}
          disabled={step >= BUOC.length}
          data-testid="journey-next"
        >
          <Icon name="arrow-right" size={13} />
          {step >= BUOC.length ? "Đã xong" : `Bước tiếp: ${BUOC[step].ten}`}
        </button>
        <button
          type="button"
          className="nq-linkbtn"
          onClick={() => setRunning((r) => !r)}
          disabled={step >= BUOC.length}
        >
          {running ? "Tạm dừng" : "Chạy tự động"}
        </button>
        <button type="button" className="nq-linkbtn" onClick={reset}>
          Chạy lại
        </button>
      </div>
      {log.length > 0 ? (
        <ul className="nq-journey__log" aria-label="Nhật ký chạy">
          {log.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
