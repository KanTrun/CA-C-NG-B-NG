import os
import cv2
import numpy as np
import math
from PIL import Image, ImageDraw, ImageFont
import shutil

base_dir = r"D:\Crew-Operations\hinh"
trans_dir = os.path.join(base_dir, 'transitions')

actions = ['idle', 'blink', 'greeting', 'listening', 'processing', 'speaking', 'success', 'alert', 'error', 'sleepy', 'poke']

print("Loading 86 pristine, spine-stabilized clean keyframe sprites...")
frames_cache = {}
for act in actions:
    fdir = os.path.join(base_dir, act)
    fnames = sorted([f for f in os.listdir(fdir) if f.startswith(f"{act}_") and f.endswith(".png")])
    frames_cache[act] = [cv2.imread(os.path.join(fdir, f), cv2.IMREAD_UNCHANGED) for f in fnames]
    print(f"  Loaded {len(frames_cache[act])} clean frames for '{act}'")

# Load progressive arm transitions (Zero Ghosting)
trans_cache = {
    'raise_step1_lift': cv2.imread(os.path.join(trans_dir, 'transition_raise_01.png'), cv2.IMREAD_UNCHANGED),
    'raise_step2_waist': cv2.imread(os.path.join(trans_dir, 'transition_raise_02.png'), cv2.IMREAD_UNCHANGED),
    'raise_step3_chest': cv2.imread(os.path.join(trans_dir, 'transition_raise_03.png'), cv2.IMREAD_UNCHANGED),
}

CANVAS_W, CANVAS_H = 720, 720
FPS = 30

# Base gradient background: Deep cyber slate gradient
base_gradient = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
for y in range(CANVAS_H):
    r_val = int(12 + (24 - 12) * (y / CANVAS_H))
    g_val = int(18 + (34 - 18) * (y / CANVAS_H))
    b_val = int(32 + (52 - 32) * (y / CANVAS_H))
    base_gradient[y, :] = [b_val, g_val, r_val]

# Dynamic Sci-Fi background generator matching Web Hologram UI
# Dynamic Sci-Fi background generator matching Web Hologram UI
def draw_dynamic_background(frame_idx, hover_dy, fps=30, badge_color=(56, 189, 248), is_speaking=False, is_listening=False, title=''):
    bg = base_gradient.copy()
    cx, cy = CANVAS_W // 2, 380
    
    # Extract mood tint in BGR format
    mr, mg, mb = badge_color
    b_tint, g_tint, r_tint = int(mb), int(mg), int(mr)
    
    # 1. Floor energy reflection shadow that reacts to hover height
    shadow_scale = max(0.65, 1.0 - (hover_dy / 25.0))
    ow = int(230 * shadow_scale)
    oh = int(40 * shadow_scale)
    shadow_overlay = bg.copy()
    cv2.ellipse(shadow_overlay, (cx, 600), (ow, oh), 0, 0, 360, 
                (int(b_tint * 0.45), int(g_tint * 0.45), int(r_tint * 0.45)), -1)
    cv2.addWeighted(shadow_overlay, 0.42, bg, 0.58, 0, bg)
    
    # Core contact shadow
    cw = int(170 * shadow_scale)
    ch = int(26 * shadow_scale)
    cv2.ellipse(bg, (cx, 600), (cw, ch), 0, 0, 360, (20, 16, 12), -1)
    
    # 2. Ambient Holographic Energy Halo (2.8s pulse cycle)
    glow_pulse = 0.5 + 0.5 * math.sin((frame_idx / fps) * 2.8)
    glow_color = (int(b_tint * 0.35 * glow_pulse), int(g_tint * 0.35 * glow_pulse), int(r_tint * 0.35 * glow_pulse))
    cv2.circle(bg, (cx, cy), 185, glow_color, 2, cv2.LINE_AA)
    
    # 3. Dual Holographic Tech Rings
    # Outer dashed ring (clockwise, speed depending on active state)
    is_processing = "PROCESSING" in title.upper()
    rot_speed_outer = 4.0 if is_processing else (7.0 if (is_speaking or is_listening) else 14.0)
    theta_outer = (frame_idx / fps) * (2 * math.pi / rot_speed_outer)
    r_outer = 250
    n_outer = 24
    for i in range(n_outer):
        a1 = theta_outer + (i * 2 * math.pi / n_outer)
        a2 = a1 + (math.pi / n_outer) * 0.65
        p1 = (int(cx + r_outer * math.cos(a1)), int(cy + r_outer * math.sin(a1)))
        p2 = (int(cx + r_outer * math.cos(a2)), int(cy + r_outer * math.sin(a2)))
        cv2.line(bg, p1, p2, (b_tint, g_tint, r_tint), 2, cv2.LINE_AA)
        
    # 4 Cardinal Diamond Nodes orbiting on outer ring
    for k in range(4):
        ang = theta_outer + k * (math.pi / 2.0)
        px = int(cx + r_outer * math.cos(ang))
        py = int(cy + r_outer * math.sin(ang))
        cv2.circle(bg, (px, py), 4, (b_tint, g_tint, r_tint), -1, cv2.LINE_AA)
        cv2.circle(bg, (px, py), 2, (255, 255, 255), -1, cv2.LINE_AA)
        
    # Inner dotted ring (counter-clockwise)
    rot_speed_inner = rot_speed_outer * 0.75
    theta_inner = -(frame_idx / fps) * (2 * math.pi / rot_speed_inner)
    r_inner = 215
    n_inner = 36
    for j in range(n_inner):
        ang = theta_inner + (j * 2 * math.pi / n_inner)
        px = int(cx + r_inner * math.cos(ang))
        py = int(cy + r_inner * math.sin(ang))
        cv2.circle(bg, (px, py), 1, (int(b_tint * 0.7), int(g_tint * 0.7), int(r_tint * 0.7)), -1, cv2.LINE_AA)
        
    # 4. Acoustic Resonance Waves (When Speaking or Listening)
    if is_speaking or is_listening:
        t_wave = (frame_idx / fps) % 1.6
        wave_r1 = int(140 + t_wave * 115)
        wave_alpha1 = max(0.0, 1.0 - (t_wave / 1.6))
        cv2.circle(bg, (cx, cy), wave_r1, 
                   (int(b_tint * wave_alpha1), int(g_tint * wave_alpha1), int(r_tint * wave_alpha1)), 2, cv2.LINE_AA)
        
        t_wave2 = ((frame_idx / fps) + 0.8) % 1.6
        wave_r2 = int(140 + t_wave2 * 115)
        wave_alpha2 = max(0.0, 1.0 - (t_wave2 / 1.6))
        cv2.circle(bg, (cx, cy), wave_r2, 
                   (int(b_tint * wave_alpha2), int(g_tint * wave_alpha2), int(r_tint * wave_alpha2)), 1, cv2.LINE_AA)
                   
    # 5. Floating Twinkling Mana Sparkles (Stardust crystals)
    sparkle_phases = [0.0, 1.1, 2.3, 3.6, 4.4, 5.2]
    sparkle_radii = [145, 185, 225, 160, 240, 195]
    sparkle_speeds = [0.5, -0.45, 0.4, -0.6, 0.5, -0.35]
    for sp_idx in range(6):
        sp_ang = sparkle_phases[sp_idx] + (frame_idx / fps) * sparkle_speeds[sp_idx]
        sp_r = sparkle_radii[sp_idx] + math.sin((frame_idx / fps) * 2.2 + sp_idx) * 14.0
        sx = int(cx + sp_r * math.cos(sp_ang))
        sy = int(cy + sp_r * math.sin(sp_ang) * 0.72)
        twinkle = max(0.25, min(1.0, 0.6 + 0.4 * math.sin((frame_idx / fps) * 3.8 + sp_idx * 1.6)))
        sp_col = (int(min(255, b_tint * 1.4 * twinkle)), int(min(255, g_tint * 1.4 * twinkle)), int(min(255, r_tint * 1.4 * twinkle)))
        cv2.line(bg, (sx - 3, sy), (sx + 3, sy), sp_col, 1, cv2.LINE_AA)
        cv2.line(bg, (sx, sy - 3), (sx, sy + 3), sp_col, 1, cv2.LINE_AA)
        cv2.circle(bg, (sx, sy), 1, (255, 255, 255), -1)
        
    return bg

# Helper for drawing UI HUD
def draw_ui(img_bgr, chapter_num, title, subtitle, status_desc, badge_color=(56, 189, 248)):
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_im = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_im)
    
    # Header bar
    draw.rectangle([20, 16, CANVAS_W - 20, 46], fill=(15, 23, 42), outline=(56, 189, 248), width=1)
    draw.text((32, 23), "AG-COPILOT  |  TINH LINH HE THONG (FAIRY SYSTEM AI)", fill=(125, 211, 252))
    draw.text((CANVAS_W - 240, 23), "FACE-LOCKED ZERO JITTER ENGINE", fill=(244, 114, 182))
    
    # Bottom HUD Card
    card_top = CANVAS_H - 100
    draw.rectangle([20, card_top, CANVAS_W - 20, CANVAS_H - 18], fill=(15, 23, 42), outline=(56, 189, 248), width=1)
    
    # Chapter & Badge
    draw.rectangle([32, card_top + 10, 185, card_top + 34], fill=badge_color)
    draw.text((40, card_top + 14), f"CH {chapter_num}: {title}", fill=(0, 0, 0))
    
    # Subtitle
    draw.text((200, card_top + 13), subtitle, fill=(241, 245, 249))
    
    # Status description
    draw.text((32, card_top + 48), status_desc, fill=(148, 163, 184))
    
    return cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)

def composite_char_subpixel_rotated(bg, char_rgba, ox=40.0, oy=18.0, angle_deg=0.0):
    cx_char, cy_char = 320.0, 320.0
    M = cv2.getRotationMatrix2D((cx_char, cy_char), angle_deg, 1.0)
    M[0, 2] += ox
    M[1, 2] += oy
    char_warped = cv2.warpAffine(char_rgba, M, (CANVAS_W, CANVAS_H),
                                flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT,
                                borderValue=(0, 0, 0, 0))
    alpha = (char_warped[:, :, 3:4].astype(float) / 255.0)
    rgb = char_warped[:, :, :3].astype(float)
    bg_f = bg.astype(float)
    out = (rgb * alpha + bg_f * (1.0 - alpha)).astype(np.uint8)
    return out

print("Building Master Timeline with Continuous Physics...")

timeline = []
# Format: (char_rgba, duration_ticks, ch_num, title, subtitle, status_desc, badge_color)

# =========================================================================
# CHAPTER 1: KHOI DONG & CHAO DON KY CHU (Idle Breathing -> Crisp Blink -> Smooth Wave)
# =========================================================================
# 1. Natural Idle Hover Breathing (1 full cycle = 8 frames x 4 ticks = 32 ticks ~ 1.07s)
for idx in range(len(frames_cache['idle'])):
    timeline.append((frames_cache['idle'][idx], 4, 1, 'IDLE', 'Trang thai san sang', 
                     f'Nhip tho & dap canh tu nhien ({idx+1}/8)', (52, 211, 153)))

# 2. Super Natural Eye Blink (8 frames full flight flap-blink cycle = 24 ticks ~ 0.80s)
for idx in range(len(frames_cache['blink'])):
    timeline.append((frames_cache['blink'][idx], 3, 1, 'IDLE', 'Trang thai san sang', 
                     f'Chop mat tu nhien theo nhip dap canh ({idx+1}/8)', (167, 139, 250)))

# 3. Complete wing stroke return to neutral (idle_01) before greeting
timeline.append((frames_cache['idle'][0], 4, 1, 'IDLE', 'Trang thai san sang', 
                 'Nhip tho em diu on dinh', (52, 211, 153)))

# 4. Chao don Ky chu & Vay tay tuoi vui (Coherent Anime Greeting Wave & Peace Sign)
# Transition from idle: rest pose establishes presence
timeline.append((frames_cache['greeting'][9], 6, 1, 'GREETING', 'Xin chao Ky chu!', 'Dung mim cuoi ngoan ngoan chao don', (56, 189, 248)))
# Greet 1: Tay dua nhe len nguc (Polite anime gesture)
timeline.append((frames_cache['greeting'][0], 6, 1, 'GREETING', 'Xin chao Ky chu!', 'Tay dua nhe len nguc chao don Ky chu', (56, 189, 248)))
# Greet 2 & 7: Waving right hand back and forth naturally (3 cycles = 24 ticks ~ 0.8s)
for wave_loop in range(3):
    timeline.append((frames_cache['greeting'][1], 4, 1, 'GREETING', 'Xin chao Ky chu!', 'Vay tay phai chao Ky chu tuoi vui', (56, 189, 248)))
    timeline.append((frames_cache['greeting'][6], 4, 1, 'GREETING', 'Xin chao Ky chu!', 'Vay tay phai nhe nhang mim cuoi', (56, 189, 248)))
# Greet 8: Victory Peace Sign (V-Sign) hold! Adorable anime payoff!
timeline.append((frames_cache['greeting'][7], 26, 1, 'GREETING', 'Xin chao Ky chu!', 'Lam dang chu V (Peace sign) tuoi cuoi rang ro!', (56, 189, 248)))
# Greet 9 & 10: Ha tay tu nhien ve hong
timeline.append((frames_cache['greeting'][8], 5, 1, 'GREETING', 'Xin chao Ky chu!', 'Ha tay nhe nhang ve suon', (56, 189, 248)))
timeline.append((frames_cache['greeting'][9], 6, 1, 'GREETING', 'Xin chao Ky chu!', 'Tay ve sat hong, mim cuoi cho lenh', (56, 189, 248)))
timeline.append((frames_cache['idle'][0], 10, 1, 'GREETING', 'Xin chao Ky chu!', 'Dung mim cuoi ngoan ngoan ben canh Ky chu', (56, 189, 248)))

# =========================================================================
# CHAPTER 2: LANG NGHE & SUY NGHI & THOAI (Voice Interaction & Dialogue)
# =========================================================================
for loop in range(2):
    for idx in range(len(frames_cache['listening'])):
        timeline.append((frames_cache['listening'][idx], 4, 2, 'LISTENING', 'Dang lang nghe Ky chu...', 
                         f'Song am hologram lan toa ({idx+1}/6)', (56, 189, 248)))

# Processing: Pondering -> Idea Spark -> Eureka Celebration!
timeline.append((frames_cache['processing'][0], 10, 2, 'PROCESSING', 'Dang suy nghi & tra cuu...', 'Nghieng dau suy nghi, phan tich yeu cau', (251, 191, 36)))
timeline.append((frames_cache['processing'][1], 10, 2, 'PROCESSING', 'Dang suy nghi & tra cuu...', 'Doc du lieu ca truc va quy trinh', (251, 191, 36)))
timeline.append((frames_cache['processing'][2], 8, 2, 'PROCESSING', 'Dang suy nghi & tra cuu...', 'Truy van he thong va tinh toan', (251, 191, 36)))
timeline.append((frames_cache['processing'][3], 6, 2, 'PROCESSING', 'Dang suy nghi & tra cuu...', 'Tia sang y tuong bat dau loe sang', (251, 191, 36)))
timeline.append((frames_cache['processing'][4], 8, 2, 'PROCESSING', 'Dang suy nghi & tra cuu...', 'Bong den y tuong hinh thanh', (251, 191, 36)))
timeline.append((frames_cache['processing'][5], 12, 2, 'PROCESSING', 'Dang suy nghi & tra cuu...', 'Bong den toa sang: Dinh! Da hieu!', (251, 191, 36)))
timeline.append((frames_cache['processing'][6], 24, 2, 'PROCESSING', 'Eureka! Da tim ra giai phap!', 'Vong ma thuat phat quang chuc mung!', (251, 191, 36)))
timeline.append((frames_cache['processing'][7], 14, 2, 'PROCESSING', 'San sang tra loi', 'Khuon mat rang ro, san sang truyen dat', (251, 191, 36)))

# Speaking cadence
for idx in [0, 1, 2, 4, 2, 1]:
    timeline.append((frames_cache['speaking'][idx], 3, 2, 'SPEAKING', 'Bao cao ket qua cho Ky chu', 
                     'Khau hinh phat am tu nhien', (34, 211, 238)))

timeline.append((frames_cache['speaking'][0], 10, 2, 'SPEAKING', 'Bao cao ket qua cho Ky chu', 
                 'Nghi hoi nhe nhang giua 2 ve cau', (34, 211, 238)))

for idx in [1, 3, 4, 5, 3, 2, 1, 0]:
    timeline.append((frames_cache['speaking'][idx], 3, 2, 'SPEAKING', 'Bao cao ket qua cho Ky chu', 
                     'Khau hinh phat am tu nhien', (34, 211, 238)))

timeline.append((frames_cache['speaking'][0], 16, 2, 'SPEAKING', 'Bao cao ket qua cho Ky chu', 
                 'Mim cuoi ngoan ngoan cho phan hoi', (34, 211, 238)))

for idx in range(len(frames_cache['idle'])):
    timeline.append((frames_cache['idle'][idx], 4, 2, 'IDLE', 'Hoan tat bao cao', 
                     'Tro ve nhip tho em diu', (52, 211, 153)))

# =========================================================================
# CHAPTER 3: DUYET CA THANH CONG (Celebration with Dignified Bow)
# =========================================================================
timeline.append((frames_cache['success'][0], 3, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Lay da bat nguoi bay len', (251, 191, 36)))
timeline.append((frames_cache['success'][1], 3, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Bay vut len khong trung', (251, 191, 36)))
timeline.append((frames_cache['success'][2], 3, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Ngoi sao lap lanh xuat hien', (251, 191, 36)))
timeline.append((frames_cache['success'][3], 3, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Ngoi sao vang kim toa sang', (251, 191, 36)))
timeline.append((frames_cache['success'][4], 20, 3, 'SUCCESS', 'Duyet ca thanh cong!', '[SUCCESS!] Bang hologram chuc mung', (251, 191, 36)))
timeline.append((frames_cache['success'][5], 16, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Phao giay confetti ruc ro bay luon', (251, 191, 36)))
timeline.append((frames_cache['success'][6], 4, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Canh vo nhe tiep dat', (251, 191, 36)))
timeline.append((frames_cache['success'][7], 20, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Cui nguoi cam on Ky chu', (251, 191, 36)))
timeline.append((frames_cache['success'][8], 16, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Hai tay chap truoc nguc chan thanh biet on', (251, 191, 36)))
timeline.append((frames_cache['success'][9], 24, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Nhay mat tinh nghich chuc mung Ky chu', (251, 191, 36)))
timeline.append((frames_cache['greeting'][8], 4, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Nang nguoi day, tay tha long tu nguc', (251, 191, 36)))
timeline.append((frames_cache['greeting'][9], 4, 3, 'SUCCESS', 'Duyet ca thanh cong!', 'Tay ha xuoi sat canh suon', (251, 191, 36)))

# =========================================================================
# CHAPTER 4: TUONG TAC CHAM VAO BE (Poke Flinch -> Blushing -> Heart Climax)
# =========================================================================
timeline.append((frames_cache['poke'][0], 3, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Giat minh lui lai ngac nhien (o_O)', (244, 114, 182)))
timeline.append((frames_cache['poke'][1], 3, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Hai tay thu ve, mat tron xoe', (244, 114, 182)))
timeline.append((frames_cache['poke'][2], 18, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Hai ma ung hong do bung then thung (*^.^*)', (244, 114, 182)))
timeline.append((frames_cache['poke'][3], 4, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Cuoi tit mat va tao dang ban tim', (244, 114, 182)))
timeline.append((frames_cache['poke'][4], 28, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Trai tim hong lap lanh bay tang Ky chu! (♥_♥)', (244, 114, 182)))
timeline.append((frames_cache['poke'][3], 8, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Trai tim tan dan, ha tay nhe nhang', (244, 114, 182)))
timeline.append((frames_cache['poke'][2], 12, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Mim cuoi then thung, ma hong giam dan', (244, 114, 182)))
timeline.append((frames_cache['greeting'][8], 4, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Tay ha ve ngang eo', (244, 114, 182)))
timeline.append((frames_cache['greeting'][9], 4, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Tay xuoi sat canh suon', (244, 114, 182)))
timeline.append((frames_cache['idle'][0], 12, 4, 'POKE REACT', 'Ky chu cham vao be!', 'Mim cuoi ngoan ngoan ben canh Ky chu', (244, 114, 182)))

# =========================================================================
# CHAPTER 5: CANH BAO & SU CO (Alert & Error Investigation & Apology)
# =========================================================================
timeline.append((frames_cache['alert'][0], 4, 5, 'ALERT', 'Canh bao thieu ca lam!', 'Giat minh hai mat tron xoe', (244, 63, 94)))
timeline.append((frames_cache['alert'][1], 3, 5, 'ALERT', 'Canh bao thieu ca lam!', 'Phat hien ca truc bi trong', (244, 63, 94)))
timeline.append((frames_cache['alert'][2], 18, 5, 'ALERT', 'Canh bao thieu ca lam!', 'Bang tam giac do chop sang [WARNING!]', (244, 63, 94)))

for idx in [3, 4, 5, 6]:
    timeline.append((frames_cache['alert'][idx], 3, 5, 'ALERT', 'Canh bao thieu ca lam!', 'Mo hoi chay lan, hai vai run nhe', (244, 63, 94)))

timeline.append((frames_cache['alert'][7], 18, 5, 'ALERT', 'Canh bao thieu ca lam!', 'Chap tay cau cuu Ky chu bo sung ca gap', (244, 63, 94)))

timeline.append((frames_cache['error'][0], 8, 5, 'ERROR', 'Su co ky thuat', 'Kiem tra nhat ky he thong bi loi', (251, 113, 133)))
timeline.append((frames_cache['error'][1], 8, 5, 'ERROR', 'Su co ky thuat', 'Quet ma loi va phan tich nguyen nhan', (251, 113, 133)))
timeline.append((frames_cache['error'][2], 10, 5, 'ERROR', 'Su co ky thuat', 'Mat xoan oc (@_@) loi 404 du lieu', (251, 113, 133)))
timeline.append((frames_cache['error'][3], 14, 5, 'ERROR', 'Su co ky thuat', 'Hoang hot va chay mo hoi lo lang', (251, 113, 133)))
timeline.append((frames_cache['error'][4], 12, 5, 'ERROR', 'Su co da khac phuc', 'Hai tay gio len nhe nhom: Da sua xong!', (251, 113, 133)))
timeline.append((frames_cache['error'][5], 22, 5, 'ERROR', 'Su co da khac phuc', 'Hai tay chap lai cui dau xin loi Ky chu', (251, 113, 133)))
timeline.append((frames_cache['greeting'][8], 5, 5, 'ERROR', 'Su co da khac phuc', 'Nang dau day, cuoi nhe nhe nhom', (251, 113, 133)))
timeline.append((frames_cache['greeting'][9], 5, 5, 'ERROR', 'Su co da khac phuc', 'Ha tay ve suon, tro lai binh thuong', (251, 113, 133)))

# =========================================================================
# CHAPTER 6: CHE DO NGU SAY KHI BO QUEN & THUC GIAC (Sleepy & Wake Up)
# =========================================================================
# Falling asleep gracefully
timeline.append((frames_cache['sleepy'][0], 20, 6, 'SLEEPY', 'Bo quen app > 60 giay', 'Mat lo do, che mieng ngap dai thu thai', (129, 140, 248)))
timeline.append((frames_cache['sleepy'][1], 10, 6, 'SLEEPY', 'Bo quen app > 60 giay', 'Dau guc xuong, mat lim dan ngu gat', (129, 140, 248)))
timeline.append((frames_cache['sleepy'][2], 10, 6, 'SLEEPY', 'Bo quen app > 60 giay', 'Ngu gat nhe nhang, chu z bay len', (129, 140, 248)))

# Deep cloud pillow slumber
timeline.append((frames_cache['sleepy'][3], 8, 6, 'SLEEPY', 'Bo quen app > 60 giay', 'Om chiec goi may bong benh em ai', (129, 140, 248)))
timeline.append((frames_cache['sleepy'][4], 8, 6, 'SLEEPY', 'Che do ngu say', 'Vao giac mong em diu cung goi may', (129, 140, 248)))
timeline.append((frames_cache['sleepy'][5], 10, 6, 'SLEEPY', 'Che do ngu say', 'Tho deu em ai, chu Zzz bay bong', (129, 140, 248)))
timeline.append((frames_cache['sleepy'][6], 14, 6, 'SLEEPY', 'Che do ngu say', 'Nu cuoi man nguyen trong giac mo dep', (129, 140, 248)))
timeline.append((frames_cache['sleepy'][7], 18, 6, 'SLEEPY', 'Che do ngu say', 'Ngu say nong am, nang luong hoi phuc', (129, 140, 248)))

# Gentle breathing loop with cloud pillow (zero pillow popping)
for loop in range(2):
    timeline.append((frames_cache['sleepy'][6], 10, 6, 'SLEEPY', 'Che do ngu say', 'Nhip tho deu dan thu thai', (129, 140, 248)))
    timeline.append((frames_cache['sleepy'][5], 10, 6, 'SLEEPY', 'Che do ngu say', 'Nang luong he thong nap day', (129, 140, 248)))
    timeline.append((frames_cache['sleepy'][6], 10, 6, 'SLEEPY', 'Che do ngu say', 'Giac mo ngot ngao ben goi may', (129, 140, 248)))
    timeline.append((frames_cache['sleepy'][7], 14, 6, 'SLEEPY', 'Che do ngu say', 'Ngu say ngon giac', (129, 140, 248)))

# Wake up sequence: gently releasing pillow, rubbing eyes, stretching up to fly
timeline.append((frames_cache['sleepy'][6], 8, 6, 'WAKE UP', 'Ky chu da quay lai!', 'Bat giac mim cuoi tinh giac', (52, 211, 153)))
timeline.append((frames_cache['sleepy'][3], 8, 6, 'WAKE UP', 'Ky chu da quay lai!', 'Tam biet goi may, tinh tao tro lai', (52, 211, 153)))
timeline.append((frames_cache['sleepy'][1], 8, 6, 'WAKE UP', 'Ky chu da quay lai!', 'Dui dui mat chop chop tinh ngu', (52, 211, 153)))
timeline.append((frames_cache['sleepy'][0], 12, 6, 'WAKE UP', 'Ky chu da quay lai!', 'Vuon vai tinh tao sang khoai', (52, 211, 153)))
timeline.append((frames_cache['greeting'][9], 4, 6, 'WAKE UP', 'Ky chu da quay lai!', 'Dap canh nhe nhang bay len', (52, 211, 153)))
timeline.append((frames_cache['blink'][2], 3, 6, 'WAKE UP', 'Ky chu da quay lai!', 'Chop mat tinh tao trong sang', (52, 211, 153)))
timeline.append((frames_cache['blink'][6], 3, 6, 'WAKE UP', 'Ky chu da quay lai!', 'Hai mat sang bung rang ro', (52, 211, 153)))
timeline.append((frames_cache['idle'][0], 28, 6, 'READY', 'San sang phuc vu!', 'Tinh tao rang ro, san sang dong hanh cung Ky chu!', (52, 211, 153)))

print(f"Timeline constructed with {len(timeline)} segments.")

# Render frames with Face-Stabilized subpixel alignment and C-infinity floating curve
rendered_frames = []
global_frame_idx = 0

prev_char_rgba = None
prev_bcolor = None
prev_title = None

for seg_idx, item in enumerate(timeline):
    char_rgba = item[0]
    duration_ticks = item[1]
    ch_num = item[2]
    title = item[3]
    subtitle = item[4]
    status_desc = item[5]
    bcolor = item[6]
    
    is_action_shift = (prev_title is not None and title != prev_title)
    
    for t in range(duration_ticks):
        # 1. 100% mathematically continuous organic floating curve (sway X + float Y + micro tilt)
        hover_dy = math.sin((global_frame_idx / FPS) * 1.85) * 4.5
        hover_dx = math.cos((global_frame_idx / FPS) * 0.95) * 1.2
        hover_rot = math.sin((global_frame_idx / FPS) * 1.85) * 0.4
        
        is_speaking = title == 'SPEAKING'
        is_listening = title == 'LISTENING'
        
        # Smooth cross-dissolve bridge on action shifts (2 frames = 66ms, eliminating hard jump cuts)
        if is_action_shift and t < 2 and prev_char_rgba is not None:
            blend_w = (t + 1) / 3.0 # 0.33, 0.67
            active_char = (char_rgba.astype(float) * blend_w + prev_char_rgba.astype(float) * (1.0 - blend_w)).astype(np.uint8)
            active_bcolor = tuple(int(c2 * blend_w + c1 * (1.0 - blend_w)) for c1, c2 in zip(prev_bcolor, bcolor))
        else:
            active_char = char_rgba
            active_bcolor = bcolor
        
        # 2. Dynamic background with reacting shadow, dual tech rings, and mana sparkles
        bg = draw_dynamic_background(
            global_frame_idx,
            hover_dy=hover_dy,
            fps=FPS,
            badge_color=active_bcolor,
            is_speaking=is_speaking,
            is_listening=is_listening,
            title=title
        )
        
        # 3. High-precision subpixel affine composite with micro-tilt rotation
        composed = composite_char_subpixel_rotated(
            bg, active_char,
            ox=40.0 + hover_dx,
            oy=18.0 + hover_dy,
            angle_deg=hover_rot
        )
        
        # 4. HUD overlay
        frame_final = draw_ui(composed, ch_num, title, subtitle, status_desc, badge_color=active_bcolor)
        
        rendered_frames.append(frame_final)
        global_frame_idx += 1

    prev_char_rgba = char_rgba
    prev_bcolor = bcolor
    prev_title = title

total_frames = len(rendered_frames)
duration_sec = total_frames / FPS
print(f"Total rendered frames: {total_frames} ({duration_sec:.1f} seconds at {FPS} FPS)")

# Save MP4 video
out_mp4 = r"D:\Crew-Operations\hinh\demo_animation_smoothing.mp4"
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
writer = cv2.VideoWriter(out_mp4, fourcc, FPS, (CANVAS_W, CANVAS_H))
for frame in rendered_frames:
    writer.write(frame)
writer.release()
print(f"Saved MP4 video to {out_mp4} ({os.path.getsize(out_mp4)} bytes)")

# Also copy to web public
web_mp4 = r"D:\Crew-Operations\apps\web\public\copilot\demo_animation_smoothing.mp4"
shutil.copy2(out_mp4, web_mp4)
print(f"Copied to {web_mp4}")

# Save preview GIF (downsampled to 360x360 at 15 FPS)
out_gif = r"D:\Crew-Operations\hinh\demo_animation_smoothing.gif"
gif_imgs = []
step = 2 # every 2nd frame = 15 FPS
for i in range(0, total_frames, step):
    resized = cv2.resize(rendered_frames[i], (360, 360), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    gif_imgs.append(Image.fromarray(rgb))

gif_imgs[0].save(
    out_gif,
    save_all=True,
    append_images=gif_imgs[1:],
    duration=66,
    loop=0,
    optimize=False
)
print(f"Saved preview GIF to {out_gif} ({os.path.getsize(out_gif)} bytes)")

# Copy to artifacts directory
art_gif = r"C:\Users\84788\.gemini\antigravity\brain\dff9b800-18c9-4a2f-93c2-da59d6f0d8a2\demo_animation_smoothing.gif"
shutil.copy2(out_gif, art_gif)
print("COPIED TO ARTIFACT DIR!")
print("FACE-LOCKED ZERO JITTER MASTER ANIMATION RENDERING COMPLETE!")
