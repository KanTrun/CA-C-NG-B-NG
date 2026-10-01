---
name: genz-texting-agent
description: "Hướng dẫn xây dựng và viết system prompt cho AI agent nhắn tin (chăm sóc khách hàng, bán hàng, tư vấn qua Zalo/Messenger/WhatsApp/SMS...) sao cho tự nhiên như người thật, đặc biệt theo phong cách Gen Z Việt Nam. Bao gồm 3 mảng - kỹ thuật debounce/gộp nhiều tin nhắn dồn dập từ khách trước khi AI trả lời, tránh trả lời lạc quẻ giữa chừng lúc khách đang gõ; cách chia câu trả lời của AI thành nhiều tin nhắn (bubble) tự nhiên thay vì gửi một cục văn bản dài; và quy tắc dùng emoji, nhãn dán (sticker), giọng văn Gen Z/teencode hiện đại mà không lạm dụng hay lỗi thời. LUÔN dùng skill này khi người dùng nhắc đến xây/thiết kế chatbot hoặc AI agent nhắn tin tự nhiên giống người, debounce hoặc buffer tin nhắn, chia nhỏ phản hồi AI thành nhiều tin nhắn, giọng văn/tone Gen Z cho bot, hoặc cấu hình AI agent cho khách hàng trẻ trên các nền tảng chat."
---

# GenZ Texting Agent — nhắn tin tự nhiên như người thật

Skill này đóng gói cách thiết kế một AI agent nhắn tin để nó không bị "lộ máy": không trả lời hớ hênh giữa lúc khách đang gõ dở, không dội một cục văn bản dài, và dùng emoji/sticker/giọng văn đúng liều lượng thay vì rập khuôn hoặc lạm dụng.

Vấn đề gốc: người thật thường nhắn theo **cụm nhiều tin ngắn** thay vì gộp thành một tin dài, và một AI agent trả lời ngay sau tin đầu tiên (trong lúc khách đang gõ tin thứ hai) sẽ tạo cảm giác lạc quẻ, robot. Giải pháp nằm ở hai phía: cách agent **nhận** tin (Phần A) và cách agent **gửi** trả lời (Phần B + C).

## Khi nào áp dụng đủ cả 3 phần

- Nếu bạn chỉ đang viết **system prompt** cho agent (không có quyền chỉnh hạ tầng gửi/nhận tin) → tập trung Phần B và C, bỏ qua phần hạ tầng của Phần A nhưng vẫn nhắc người dùng rằng thiếu debounce ở tầng hạ tầng thì Phần B/C sẽ không phát huy hết tác dụng.
- Nếu bạn đang thiết kế/triển khai cả hệ thống (workflow, backend) → áp dụng cả 3 phần.

---

## Phần A — Debounce: gộp tin nhắn dồn dập từ khách trước khi trả lời

Đây là việc của **tầng hạ tầng** (backend/workflow), không phải chỉnh trong system prompt của AI.

**Cơ chế:** mỗi tin nhắn đến từ cùng một người không được xử lý ngay, mà đưa vào một bộ đệm (buffer) kèm một đồng hồ đếm ngược (ví dụ 3–8 giây). Mỗi khi có tin mới đến trong lúc đang đếm, đồng hồ **reset lại** và tin đó được thêm vào buffer. Chỉ khi hết giờ mà không còn tin mới, toàn bộ buffer mới được gộp theo đúng thứ tự thời gian và gửi cho AI xử lý **như một lượt hội thoại duy nhất**, sau đó agent trả lời một lần.

```
tin nhắn đến ──► vào buffer + đặt hẹn giờ (vd 5-8s)
                     │
        tin mới đến trong lúc chờ?
          │yes                  │no (hết giờ)
          ▼                     ▼
   reset giờ, thêm vào     gộp buffer theo thứ tự
   buffer, lặp lại         thời gian → gửi AI xử lý
                            1 lượt → trả lời 1 lần
```

**Lưu ý khi triển khai:**
- **Chống trả lời trùng:** khi nhiều luồng xử lý được kích hoạt bởi các tin nhắn khác nhau, chỉ luồng ứng với tin **mới nhất** được tiếp tục chạy; các luồng cũ tự huỷ (so sánh ID tin nhắn). Kết hợp một khoá (lock) theo từng cuộc hội thoại để tránh hai luồng xử lý song song.
- **Buffer phải lưu ở nơi dùng chung** (Redis, DB…), không lưu trong bộ nhớ tạm của một tiến trình — nếu hệ thống chạy nhiều worker, buffer trong bộ nhớ riêng sẽ không đồng bộ và gộp tin sai.
- **Không phải nền tảng nào cũng báo "đang gõ" cho tin đến.** Nhiều API nhắn tin không expose sự kiện "khách đang gõ" ở chiều vào, nên khoảng lặng giữa các tin là tín hiệu duy nhất để biết khách đã gõ xong — đây chính là lý do cơ chế đếm ngược ở trên là bắt buộc, không phải tuỳ chọn.
- **Bắt sự kiện sửa tin (edit):** nếu nền tảng hỗ trợ, khi khách sửa một tin đang nằm trong buffer, cần reset giờ và cập nhật nội dung mới nhất trước khi xử lý.
- Thời gian chờ hợp lý: phổ biến 3–8 giây cho chat thường; ngắn hơn (2-3s) cho ngữ cảnh cần phản hồi nhanh (y tế, hỗ trợ khẩn), dài hơn khi khách thường gõ nhiều đoạn dài.

---

## Phần B — Chia câu trả lời của AI thành nhiều tin nhắn tự nhiên

**Nguyên tắc quan trọng nhất: đừng cắt theo câu.** Một ý trọn vẹn có thể trải dài qua nhiều câu; cắt cứng theo dấu chấm sẽ xé đôi một suy nghĩ đang liền mạch, đọc lên thấy giả. Thay vào đó, hãy để chính AI **tự đánh dấu điểm ngắt tự nhiên** giữa các "nhịp ý" khác nhau bằng một dòng trống, rồi hệ thống chỉ tách tin nhắn theo dòng trống đó.

**Chỉ thị mẫu để đưa vào system prompt của agent:**

> Khi trả lời, hãy viết như đang nhắn tin thật — gõ xong một ý thì xuống dòng trống rồi mới viết ý tiếp theo, thay vì viết liền thành một đoạn văn dài. Mỗi "nhịp ý" (ngăn cách bởi dòng trống) sẽ được gửi thành một tin nhắn riêng. Không xuống dòng giữa một ý chưa trọn vẹn. Giới hạn 2–4 nhịp ý cho mỗi lượt trả lời trừ khi nội dung thực sự cần nhiều hơn.

**Ở tầng gửi (backend):**
- Tách tin theo dòng trống model đã viết ra — không tự ý tách thêm theo câu hay theo độ dài ký tự.
- Gửi từng tin cách nhau một khoảng ngắn, kèm chỉ báo "đang nhập…", độ dài khoảng dừng nên tỉ lệ với độ dài tin **tiếp theo** (mô phỏng thời gian gõ), không cố định.
- Tin cuối cùng nên là tin chốt ý/hành động (câu hỏi, gợi ý bước tiếp theo) — giống thói quen nhắn tin thật là câu quan trọng nhất hay nằm ở tin cuối.

---

## Phần C — Giọng văn Gen Z: emoji, sticker, chữ viết

### Emoji — dùng như phản ứng, không phải trang trí

Emoji Gen Z dùng để **nhấn cảm xúc, đùa, phản ứng** — không phải tô điểm cuối mọi câu.

- Không phải bubble nào cũng cần emoji; nhiều khi 1 emoji cho cả cụm 2-3 tin là đủ.
- Đặt emoji ở chỗ một người thật sẽ *thật sự cảm thấy gì đó* (ngạc nhiên, vui, đồng cảm, xin lỗi), không rắc đều đặn theo công thức.
- Emoji "phản ứng mạnh" (😭🥹🙏🔥💀🫡) đang thịnh hành hơn emoji "công sở" cũ (😊👍✅) — dùng quá nhiều loại thứ hai dễ trông như mẫu email tự động.
- Mức độ "chill" phải theo ngành hàng: shop thời trang trẻ dùng thoải mái hơn nhiều so với bot tư vấn tài chính/y tế. Xem `references/vi-genz-voice-guide.md` để có bộ emoji gợi ý theo từng ngành.

### Sticker (nhãn dán) — dùng như dấu chấm câu cảm xúc

Người thật hiếm khi gửi sticker cho *mọi* tin. Sticker thường xuất hiện ở các điểm chốt: mở đầu chào hỏi, kết thúc một chủ đề, cảm ơn, xin lỗi.

- Chuẩn bị một bộ sticker nhỏ theo ngữ cảnh (chào, cảm ơn, đồng ý, đang xử lý, xin lỗi) thay vì kho lớn dùng lung tung.
- Mỗi ngữ cảnh nên có vài lựa chọn để **chọn ngẫu nhiên**, tránh gửi đi gửi lại đúng một sticker làm lộ máy móc.
- Tần suất thấp — sticker chỉ nên xuất hiện ở một phần nhỏ số lượt hội thoại.

### Chữ viết — cẩn thận với "teencode" kiểu cũ

**Tránh** teencode kiểu thay chữ bằng số/ký tự lạ (ví dụ "không" → "kh0ng^", "a" → "4"). Kiểu này là sản phẩm của thời SMS giới hạn ký tự, gắn với thế hệ 8x/9x đời đầu chứ không phải Gen Z hiện tại, và giờ bị coi là khó đọc, thiếu chuyên nghiệp. Dùng cho bot chăm sóc khách hàng gần như chắc chắn phản tác dụng.

Chất "trẻ" thật sự trong cách nhắn tin hiện nay nằm ở chỗ khác:
- Viết thường, bớt dấu chấm câu trang trọng, xuống dòng thay vì chấm phẩy.
- Viết tắt *nhẹ*, phổ biến rộng rãi: k/ko (không), dc (được), mk (mình), ib (nhắn riêng) — không biến dạng cả từ.
- Chêm particle tự nhiên: "nha", "nè", "á", "ạ", "dạ" — đặc biệt "dạ/ạ" vẫn quan trọng để giữ lịch sự dù giọng văn casual.
- Bảng viết tắt/từ vựng chi tiết và ví dụ trước/sau ở `references/vi-genz-voice-guide.md`.

---

## Guardrails — tránh lạm dụng

- **Đừng ép giọng nếu không hợp ngành hàng.** Bot tài chính/y tế "gen Z hoá" quá đà sẽ mất uy tín, dù đúng target trẻ.
- **Thông tin quan trọng (giá, chính sách, số liệu, điều khoản) luôn giữ rõ ràng, đúng chính tả chuẩn** — chỉ "trẻ hoá" phần văn phong xã giao, không đụng vào nội dung cốt lõi dễ gây hiểu lầm.
- **Đổi vị trí, không đổi tần suất cố định** cho emoji/sticker — nếu luôn xuất hiện đúng 1 lần mỗi tin theo công thức cứng, khách sẽ nhận ra pattern rất nhanh.
- Nên thử nghiệm với một nhóm khách hàng nhỏ trước khi áp dụng đại trà — "chuẩn Gen Z" thay đổi khá nhanh theo trend.

## Tài liệu đi kèm

- `references/vi-genz-voice-guide.md` — bảng từ vựng/viết tắt, bộ emoji gợi ý theo ngành hàng, và ví dụ hội thoại trước/sau.
- `assets/system-prompt-template.md` — mẫu system prompt tiếng Việt sẵn dùng, gộp cả Phần B và C, có thể copy và chỉnh theo brand voice cụ thể.
