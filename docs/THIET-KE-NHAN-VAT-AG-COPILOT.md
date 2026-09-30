# Thiết kế nhân vật AG-COPILOT — “Bé Phin”

> Vị trí: `apps/web/src/ui/copilot/Avatar2D.tsx` (hiện tại) → tiến hóa thành nhân vật cố định.
> Nguyên tắc: SVG inline nhẹ, không three.js mặc định. Giống 3D bằng gradient/shadow + prerender khi cần.
> Tuân thủ `docs/design-guidelines.md`: motion ops T0/T1, tôn trọng `prefers-reduced-motion`, màu gold `#b8942f`.

## 1. Nhân vật được chọn: Bé Phin

- **Concept:** Hạt cà phê + phin pha cà phê Việt Nam. Đầu hình hạt cà phê, đội nắp phin làm mũ.
- **Lý do chọn:** gốc quán cà phê, nguyên bản (tránh IP có bản quyền), dễ vẽ bằng SVG, dễ biểu cảm, hợp mọi role.
- **Tính cách:** lễ phép, nhanh nhẹn, nói ngắn, chỉ đề xuất — người duyệt mới làm (fail-closed).
- **Cách xưng hô:** “Em” với mọi role. Badge: “Trợ lý” / “Đang nghe” / “Đang nói” (giữ như cũ).

## 2. Visual cố định

- Mặt: `#e8b98a` viền `#c99a6a`, má hồng opacity 0.25 khi vui.
- Mũ phin: hình thang `#2a2a2e` + viền gold `#b8942f`, hơi nước khi processing.
- Mắt: ellipse trắng + con ngươi `#2a1a0a`. Nhìn theo cursor (±2px).
- Miệng: `mouthOpen` 0–1 từ `useAvatarLipSync` (giữ nguyên hook).
- Vòng trạng thái sau lưng: speaking gold/20 + ping, listening xanh-ok, idle dim/10.
- Size: 72 trong banner voice, 96 trong drawer. Không render khi voice không active (giữ logic `isVoiceActive` hiện tại).

## 3. Bộ biểu cảm (mood → tham số SVG)

| mood | Kích hoạt | Mắt | Mày | Miệng | Phụ |
|---|---|---|---|---|---|
| `idle` | voice idle | chớp 3–5s, thở scale 1±0.01 | ngang | ngậm 2px | — |
| `listening` | `listening=true` | mở to rx+1 | nhướn | mím | sóng âm 2 vạch |
| `processing` | state processing | nhìn lên 2px | chau nhẹ | mím lệch | hơi nước trên mũ |
| `speaking` | `speaking=true` | bình thường | ngang | lip-sync volume | rung nhẹ theo amplitude |
| `happy` | đủ ca / tra cứu xong | cong ^ ^ | cong | cười 8px | má hồng |
| `worried` | thiếu ca / tồn kho thấp | to + cao | xéo vào | mím xéo | mồ hôi 1 giọt |
| `success` | duyệt xong | nhắm cong | cong | cười to | confetti 6 hạt CSS |
| `error` | lỗi / mic denied | nửa nhắm | nhíu | mím | tay gãi đầu (path đơn) |
| `greeting` | lần đầu mở | chớp 1 cái | ngang | cười | vẫy tay 800ms |
| `sleepy` | idle >60s | nhắm + “Z” | ngang | ngáp | mũ nghiêng 5° |

## 4. Hành động

- Gật (duyệt xong), lắc nhẹ (từ chối/lỗi), vẫy chào (mở drawer), ngủ gật → tỉnh khi có tin mới.
- Mắt bám cursor trong pane; nhảy scale theo amplitude khi speaking.
- Skin theo role: nhân viên = tạp dề nâu; quản lý = headset; chủ quán = nơ gold.
- Skin sự kiện: Tết/mưa/đêm nhạc — chỉ đổi mũ/phụ, không đổi mặt.
- Chạm vào avatar: vẫy + 1 tip vận hành ngẫu nhiên (không autoplay âm thanh).

## 5. Kỹ thuật (nhẹ)

```ts
export type AvatarMood =
  | "idle" | "listening" | "processing" | "speaking"
  | "happy" | "worried" | "success" | "error"
  | "greeting" | "sleepy";

export interface AvatarProps {
  mouthOpen: number; speaking: boolean; listening: boolean;
  mood: AvatarMood; size?: number;
}
```

- Map `VoiceState` → mood: `listening→listening`, `processing→processing`, `speaking→speaking`, `error/mic_denied→error`, còn lại suy từ ngữ cảnh quán (thiếu ca→worried, duyệt xong→success 2s rồi về idle).
- Giữ `useAvatarLipSync` (rAF chỉ chạy khi active). Thêm `useAvatarBlink` + `useAvatarMoodTimeout` riêng, không gộp vào loop.
- Muốn giống 3D hơn: prerender 10 mood ra WebP/Lottie, swap `<img>` theo mood. Không dùng three.js trừ khi có trang showcase riêng (lazy `next/dynamic`, low-poly, cap DPR≤1.5, pause khi ẩn).
- Budget: +0KB JS (SVG thuần), <30KB nếu thêm WebP, 60fps transform/opacity only, CSS ≤320ms.

## 6. Việc tiếp theo

1. Đổi `Avatar2D` nhận thêm `mood` + vẽ mũ phin + má hồng + tay vẫy (1 file duy nhất).
2. Thêm map state→mood trong `CopilotBody.tsx` chỗ banner `isVoiceActive`.
3. E2E: chụp 3 mood (idle/speaking/worried), test reduced-motion tắt animation.
