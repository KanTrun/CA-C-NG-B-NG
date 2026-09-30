# Ke Hoach Chi Tiet Tao Bo Anh Animation Tinh Linh He Thong (Fairy System AI)

Muc tieu: Tao bo Sprite Sheet chuyen dong muot ma (10-12 FPS) cho AG-Copilot trong ung dung Crew-Operations.
Quy cach ky thuat bat buoc:
- Phong nen: Phong xanh la cay thuan nhat (Pure Green Screen #00FF00) de tach nen 100% sach se, khong bi thung vay trang hoac tat trang va khong bi lem vien canh.
- Ti le va goc nhin: Goc chinh dien truc dien (Front-view), nhan vat dung giua khung hinh, kich thuoc hien thi dong bo.
- Tong so khung hinh (Frames): 80 frames chia deu cho 11 hanh dong.

---

## 1. BANG TONG HOP 11 HANH DONG (80 FRAMES)

| STT | Hanh dong / Trang thai | Ma hieu (Folder/Prefix) | So Frame | Thoi luong | Kieu chuyen dong |
| :---: | :--- | :--- | :---: | :---: | :--- |
| 1 | Lo lung va tho tu nhien | idle_floating | 8 | 1.0s | Lap vo tan (Loop) |
| 2 | Chop mat tu nhien | blink | 5 | 0.4s | Chay 1 lan (One-shot) moi 3-4s |
| 3 | Vay tay chao Ky chu | greeting | 10 | 1.2s | Chay khi mo app / drawer |
| 4 | Dang lang nghe Ky chu noi | listening | 6 | 0.8s | Lap theo nhip noi (Loop) |
| 5 | Dang tinh toan / Tra cuu | processing | 8 | 1.0s | Vong du lieu xoay deu (Loop) |
| 6 | Dang noi chuyen (Lip-sync) | speaking | 6 | 0.6s | Doi frame theo am luong Web Audio |
| 7 | Hoan thanh / Duyet ca | success | 10 | 1.2s | Nhay mung, tung sao vang |
| 8 | Canh bao thieu ca / Ton kho | alert_worried | 8 | 1.0s | Run ray, toat mo hoi, nhay Alert |
| 9 | Gap loi / Micro bi chan | error | 6 | 0.8s | Gai dau boi roi, icon 404 |
| 10 | Ngu gat khi bo quen app | sleepy | 8 | 1.2s | Om goi ngu, chu Zzz bay bong |
| 11 | Cham / Click vao nhan vat | poke_react | 5 | 0.5s | Giat nay minh roi ban tim |
| Tong | TONG CONG | | 80 | | |

---

## 2. KICH BAN CHI TIET TUNG FRAME

### 2.1. Hanh Dong: Lo Lung va Tho Tu Nhien (idle_floating - 8 Frames)
Chuyen dong hinh sin: Len cao nhat o Frame 4, ha xuong thap nhat o Frame 8, lap tuan hoan.
- Frame 1: Vi tri can bang ban dau. Hai tay khe buong tu nhien, canh mo 45 do, vay xuoi nhe, mat mo to mim cuoi.
- Frame 2: Bat dau dang nguoi len khoang 4px. Doi canh hoi vo nhe xuong duoi de tao luc nang, mep vay hoi xoe.
- Frame 3: Dang len tiep khoang 8px. Canh mo rong toi da, toc mai bong nhe len theo huong gio nang.
- Frame 4 (Dinh cao nhat): Nguoi o vi tri cao nhat (khoang 12px). Vay bong nhe nhat, anh sang tren halo va canh phat sang em diu.
- Frame 5: Bat dau ha xuong khoang 8px. Doi canh khe khep lai mot nhip, vay bat dau xuoi dan.
- Frame 6: Ha xuong tiep khoang 4px. Than nguoi chung nhe tu nhien.
- Frame 7 (Day thap nhat): Nguoi o vi tri thap nhat (-2px). Canh hoi co lai, dau goi hoi chung nhe.
- Frame 8: Nang nguoi tro lai vi tri can bang (noi tiep muot ma vao Frame 1).

### 2.2. Hanh Dong: Chop Mat Tu Nhien (blink - 5 Frames)
Chen vao giua trang thai idle: Giu nguyen tu the than, chi chuyen dong mi mat.
- Frame 1: Mat mo to tron, con nguoi sang long lanh (100% mo).
- Frame 2: Mi mat tren bat dau sup xuong (70% mo).
- Frame 3: Mi mat khep lai mot nua (30% mo).
- Frame 4 (Nham tit): Mat nham hoan toan thanh mot duong cong mong hinh vong cung mem mai.
- Frame 5: Mat mo he nhanh tro lai (60% mo, sau do chuyen ve Frame 1 mo to).

### 2.3. Hanh Dong: Vay Tay Chao Ky Chu (greeting - 10 Frames)
- Frame 1: Tay phai bat dau gap cui cho, nang tu hong len ngang nguc.
- Frame 2: Tay phai gio cao qua vai, long ban tay huong ve phia truoc.
- Frame 3: Canh tay vuon thang, ban tay nghieng sang phai mot goc 20 do, dau hoi nghieng sang trai, mat cuoi.
- Frame 4: Ban tay vay nghieng sang trai goc 20 do, cac ngon tay mem mai chuyen dong theo quan tinh.
- Frame 5: Ban tay vay nguoc lai sang phai lan 2.
- Frame 6: Ban tay vay sang trai lan 2, hai ma ung hong chao don Ky chu.
- Frame 7: Ban tay vay sang phai lan 3 nhe nhang ket thuc nhip vay.
- Frame 8: Ban tay dua ve vi tri giua, hai ngon tay lam dang chu V (Peace sign).
- Frame 9: Tay bat dau ha dan tu tren cao xuong ngang nguc.
- Frame 10: Tay ha ve lai canh suon, dung mim cuoi tu nhien.

### 2.4. Hanh Dong: Dang Lang Nghe Ky Chu (listening - 6 Frames)
Hien thi khi Ky chu bam giu micro hoac dang noi chuyen.
- Frame 1: Dau hoi nghieng ve phia truoc, hai mat mo to tap trung, hai ban tay khe dat nhe truoc nguc.
- Frame 2: Xuat hien 1 dai song am mau xanh da quang thanh manh ben tai phai.
- Frame 3: Dai song am ben tai trai xuat hien, doi canh da quang sang ruc len 1 nhip.
- Frame 4: Song am lan toa thanh vong tron hologram gon song quanh dau.
- Frame 5: Song am thu nho dan, doi canh khe rung rinh tiep nhan du lieu.
- Frame 6: Anh sang hao quang diu lai, san sang chuyen tiep sang trang thai xu ly.

### 2.5. Hanh Dong: Dang Tinh Toan / Suy Nghi (processing - 8 Frames)
Hien thi khi AI dang tra cuu lich ca, tinh cong hoac doc du lieu quan.
- Frame 1: Tay phai dua len chong cam, mat liec sang goc tren ben phai, mieng mim nhe suy nghi.
- Frame 2: Xuat hien vong tron ma phap so hoc / thuoc do du lieu hologram mau xanh xoay 45 do quanh nguoi.
- Frame 3: Vong du lieu xoay tiep 90 do, cac ky tu nhi phan / so lieu ca lam viec li ti phat sang.
- Frame 4: Vong xoay den 135 do, tren dinh dau xuat hien mot bieu tuong banh rang xoay nhe.
- Frame 5: Vong xoay den 180 do, banh rang bien thanh hinh bong den y tuong phat sang mo.
- Frame 6: Vong xoay den 270 do, bong den y tuong loe sang mau vang kim lap lanh.
- Frame 7: Vong xoay hoan tat 360 do, ngon tay tro gio len nhu vua tim ra loi giai.
- Frame 8: Khuon mat rang ro, chuan bi chuyen sang noi cau tra loi cho Ky chu.

### 2.6. Hanh Dong: Dang Noi Chuyen / Khau Hinh Mieng (speaking - 6 Frames)
Dung de ghep khop giong noi theo Web Audio API.
- Frame 1 (Ngam): Mieng khep tu nhien, mim cuoi nhe.
- Frame 2 (Khau hinh A): Mieng mo vua theo chieu doc, nhin thay hang rang tren.
- Frame 3 (Khau hinh O): Mieng tron xoe chu O nho, mat mo to bieu cam nhan manh tu ngu.
- Frame 4 (Khau hinh E/I): Khoe mieng keo dai sang hai ben, rang khep ho cuoi tuoi tan.
- Frame 5 (Khau hinh U): Mieng chum chim tron nho nho ve phia truoc.
- Frame 6 (Noi to / Cuoi lon): Mieng mo rong bien do toi da, luoi va rang lo ro sinh dong.

### 2.7. Hanh Dong: Thanh Cong / Duyet Ca Hoan Tat (success - 10 Frames)
Hien thi khi duyet xong ca lam, hoan tat cham cong, xep lich thanh cong.
- Frame 1: Be hoi chung hai dau goi lay da, hai tay nam chat dua truoc nguc day hao huc.
- Frame 2: Dap chan bat nguoi bay vut len khong trung, ta vay bay phap phoi.
- Frame 3: Hai tay gio cao hinh chu V, doi canh mo rong toi da, nguoi o diem cao nhat.
- Frame 4: Nu cuoi rang ro het co, xung quanh bung toa 6 ngoi sao vang kim 4 canh lap lanh.
- Frame 5: Bang thong bao hologram vang ong hien ra truoc nguc: [QUEST COMPLETE!] hoac [HOAN TAT!].
- Frame 6: Phao giay Confetti da sac mau (vang, hong, xanh) bay lo lung xung quanh.
- Frame 7: Than nguoi tu tu ha cham xuong, canh vo nhe ham da roi.
- Frame 8: Tiep dat nhe nhang, ta vay ru xuong em ai.
- Frame 9: Hai tay chap truoc nguc, dau cui nhe 15 do cam on Ky chu.
- Frame 10: Ngang dau len, nhay mat tinh nghich ban tim chuc mung.

### 2.8. Hanh Dong: Canh Bao Thieu Ca / Ton Kho Thap (alert_worried - 8 Frames)
Hien thi khi quan co su co, thieu nguoi lam, phat hien trung lich.
- Frame 1: Giat nay minh, hai mat mo to het co, dong tu co nho lai kinh ngac.
- Frame 2: Hai ban tay dua voi len om lay hai ma, mieng ha hoc hinh chu nhat uon song hoang hot.
- Frame 3: Xuat hien bang tam giac canh bao mau do neon phat sang nhap nhay: [ALERT!].
- Frame 4: Mot giot mo hoi hoat hinh to tron xuat hien ben thai duong, hai vai hoi run ray.
- Frame 5: Giot mo hoi chay lan nhe xuong ma, bang Alert chop sang do lan 2.
- Frame 6: Be lac nhe dau boi roi, mat rom rom lo lang nhin Ky chu.
- Frame 7: Hai tay chap lai truoc nguc voi anh mat cau cuu Ky chu mau xu ly.
- Frame 8: Dung run nhe trong tu the san sang nhan lenh dieu phoi tu Ky chu.

### 2.9. Hanh Dong: Gap Loi / Khong Nhan Micro (error - 6 Frames)
Hien thi khi rot mang, trinh duyet chan mic hoac server 500.
- Frame 1: Dau hoi nghieng sang mot ben, long may nhiu lai kho hieu.
- Frame 2: Mot tay dua ra sau gay gai dau, mieng cuoi tru guong gao.
- Frame 3: Mat bien thanh hinh xoan oc chong mat (@_@), tren dau xuat hien icon 404 ?!.
- Frame 4: Bieu tuong 404 ?! nay nhe len mot nhip, giot mo hoi roi xuong toc.
- Frame 5: Mat tro lai binh thuong nhung ve mat hoi hoi loi, hai tay xua xua truoc nguc.
- Frame 6: Hai tay chap lai cui dau xin loi Ky chu vi su co ky thuat.

### 2.10. Hanh Dong: Ngu Gat Khi Bo Quen App (sleepy - 8 Frames)
Kich hoat khi nguoi dung khong tuong tac qua 60 giay.
- Frame 1: Mat lo do nua nham nua mo, mot tay dua len che mieng ngap dai.
- Frame 2: Dau guc xuong mot nhip, mi mat khep lai hoan toan, hai vai tha long.
- Frame 3: Be trieu hoi mot chiec goi nho mem mai om vao long, nghieng nguoi bay lo lung.
- Frame 4: Nguc phap phong tho nhe, chu Z nho mau lam phat sang bay len tu dau.
- Frame 5: Chu Z nho bay len cao hon, xuat hien them chu z thu hai.
- Frame 6: Ca cum chu Zzz lon bay bong len khong trung roi mo dan.
- Frame 7: Be khe tro minh om chat chiec goi, mieng mim cuoi say sua.
- Frame 8: Nhip tho deu dan (chay lap tu Frame 4 den 8 tao thanh vong lap ngu thu thai).

### 2.11. Hanh Dong: Tuong Tac Khi Cham Vao Nhan Vat (poke_react - 5 Frames)
Kich hoat khi Ky chu lay chuot click truc tiep vao nhan vat.
- Frame 1: Bi ngon tay hoac chuot cham trung: Than nguoi giat nay lui ve sau 5px, hai mat tron tron ngac nhien (o_O).
- Frame 2: Nhan ra la Ky chu dang treu minh: Hai ma lap tuc ung hong do bung then thung.
- Frame 3: Mat hip lai cuoi tit cong nhu vang trang khuyet, hai tay om nguc.
- Frame 4: Dua ban tay phai ra phia truoc, ngon cai va ngon tro bat cheo tao thanh hinh trai tim nho (Finger-heart).
- Frame 5: Trai tim nho mau hong lap lanh bay ra tang Ky chu, nguoi tu tu tro lai tu the idle.

---

## 3. CONG THUC PROMPT CHUAN DE TAO ANH (MIDJOURNEY / STABLE DIFFUSION)

De tao ra dai anh chuyen dong khong bi lech mau hay bien dang, nen tao theo dang Sprite Sheet dai ngang (Horizontal Sequence) voi phong xanh la:

Mau prompt:
`2D anime animation sprite sheet, 6 to 8 sequential frames in horizontal sequence from left to right, [TEN HANH DONG VA MO TA FRAME], cute chibi anime system AI fairy with light blue hair, glowing digital wings, white and gold sci-fi armor dress, solid pure bright green background, chroma key screen, clean flat #00FF00 background, no shadows on background, consistent character model, high resolution 2D illustration.`

---

## 4. QUY UOC DAT TEN FILE

Luu anh sau khi tach phong vao thu muc: apps/web/public/copilot/sprites/

- idle_01.png den idle_08.png
- blink_01.png den blink_05.png
- greeting_01.png den greeting_10.png
- listening_01.png den listening_06.png
- processing_01.png den processing_08.png
- speaking_01.png den speaking_06.png
- success_01.png den success_10.png
- alert_01.png den alert_08.png
- error_01.png den error_06.png
- sleepy_01.png den sleepy_08.png
- poke_01.png den poke_05.png

---

## 5. TIEN DO THUC HIEN VA KET QUA TRIEN KHAI (HOAN TAT 100%)

Tat ca 11 hanh dong voi tong cong 83 frames da duoc tao bang AI theo dang Horizontal Sprite Sheet tren phong xanh #00FF00, tach nen bang thuat toan Chroma-key Despill RGB + Gaussian Alpha, chuan hoa tren canvas 640x640px voi chieu cao nhan vat dong bo 540px (y: 50 -> 590px).

| STT | Hanh dong | Folder trong `hinh/` | So Frame | File chuan hoa 640x640 | Web Public Assets (`apps/web/public/copilot/sprites/`) |
| :---: | :--- | :--- | :---: | :--- | :--- |
| 1 | **idle** (Lo lung & tho) | `hinh/idle` | 8 | `idle_01.png` - `idle_08.png` (va `1.png` - `8.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 2 | **blink** (Chop mat) | `hinh/blink` | 8 | `blink_01.png` - `blink_08.png` (va `1.png` - `8.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 3 | **greeting** (Vay tay chao) | `hinh/greeting` | 10 | `greeting_01.png` - `greeting_10.png` (va `1.png` - `10.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 4 | **listening** (Dang nghe) | `hinh/listening` | 6 | `listening_01.png` - `listening_06.png` (va `1.png` - `6.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 5 | **processing** (Tinh toan) | `hinh/processing` | 8 | `processing_01.png` - `processing_08.png` (va `1.png` - `8.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 6 | **speaking** (Khau hinh noi) | `hinh/speaking` | 6 | `speaking_01.png` - `speaking_06.png` (va `1.png` - `6.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 7 | **success** (Thanh cong / Duyet ca) | `hinh/success` | 10 | `success_01.png` - `success_10.png` (va `1.png` - `10.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 8 | **alert** (Canh bao / Hoang hot) | `hinh/alert` (va `hinh/alert_worried`) | 8 | `alert_01.png` - `alert_08.png` (va `1.png` - `8.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 9 | **error** (Loi / 404 / Boi roi) | `hinh/error` | 6 | `error_01.png` - `error_06.png` (va `1.png` - `6.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 10 | **sleepy** (Ngu gat / Zzz) | `hinh/sleepy` | 8 | `sleepy_01.png` - `sleepy_08.png` (va `1.png` - `8.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 11 | **poke** (Tuong tac / Ban tim) | `hinh/poke` (va `hinh/poke_react`) | 5 | `poke_01.png` - `poke_05.png` (va `1.png` - `5.png`) | Da dong bo vao `apps/web/public/copilot/sprites/` |
| 12 | **transitions** (Khung hinh chuyen tiep In-between) | `hinh/transitions` | 3 | `arm_raise_01.png` - `arm_raise_03.png` | Da dong bo vao `apps/web/public/copilot/sprites/transition_raise_01..03.png` |
| Tong | **TONG CONG** | | **86** | **83 Frames hanh dong + 3 Frames chuyen tiep In-between** | **Da dong bo toan bo vao web public** |

---

## 6. QUY TAC CHUYEN DONG CHUYEN TIEP (IN-BETWEENING KINEMATICS)

Nham xoa bo triet de hien tuong tay nhan vat "dich chuyen tuc thoi" (teleporting) khi chuyen tu trang thai nghi sang hanh dong va nguoc lai:

1. **Chuoi nang tay chao (Idle -> Greeting Ingress):**
   - `idle_01`: Hai tay xuoi nhe ben hong.
   - `transition_raise_01`: Khuy tay mo khoa nhe, ban tay bat dau nang tu dui len ngang eo.
   - `transition_raise_02`: Khuy tay gap nhe, ban tay nang tiep len ngang nguc.
   - `transition_raise_03`: Canh tay vuon len ngang vai, mo long ban tay huong ve truoc.
   - `greeting_02`: Tay gio cao qua dau bat dau nhip vay.
   - **Ket qua:** Tay nhan vat duoc cam nhan nang len tu tu, mem mai theo quy dao dong luc hoc (kinematic arc) lien mach.

2. **Chuoi ha tay ket thuc (Greeting -> Idle Egress):**
   - `greeting_07` (Peace sign): Giu nu cuoi va dang chu V.
   - `transition_raise_03`: Ha tay tu tren cao ve ngang vai.
   - `transition_raise_02`: Ha tay ve ngang nguc.
   - `transition_raise_01`: Ha tay tiep ve ngang eo.
   - `idle_01`: Tay tha long hoan toan ve canh hong, tro lai nhip tho tu nhien.

3. **Thu hoi tay sau Ban tim & Cui chao (Poke & Success Recovery):**
   - Ap dung `transition_raise_02` va `transition_raise_01` de ha tay tu nguc ve lai hong, giup ket thuc dong tac ngot ngao, khong bao gio bi cat phat dot ngot.

