import cv2
import os
import shutil
import numpy as np

backup_dir = r"D:\Crew-Operations\hinh_backup_86_frames"
base_dir = r"D:\Crew-Operations\hinh"
web_dir = r"D:\Crew-Operations\apps\web\public\copilot\sprites"
trans_dir = os.path.join(base_dir, 'transitions')
os.makedirs(trans_dir, exist_ok=True)
os.makedirs(web_dir, exist_ok=True)

actions = ['idle', 'blink', 'greeting', 'listening', 'processing', 'speaking', 'success', 'alert', 'error', 'sleepy', 'poke']

# 1. Master reference from pristine idle/1.png
idle_ref_path = os.path.join(backup_dir, 'idle', '1.png')
idle_01 = cv2.imread(idle_ref_path, cv2.IMREAD_UNCHANGED)
gray_ref = cv2.cvtColor(idle_01[:, :, :3], cv2.COLOR_BGR2GRAY)

# Reference: eyes & nose bridge [215:270, 310:380] (55x70 px)
REF_X = 310
REF_Y = 215
ref_patch = gray_ref[REF_Y:REF_Y+55, REF_X:REF_X+70]

print("=== STABILIZING AND NORMALIZING ALL 86 SPRITE FRAMES ===")

aligned_sprites = {}

for act in actions:
    fdir = os.path.join(backup_dir, act)
    num_pngs = sorted([f for f in os.listdir(fdir) if f.split('.')[0].isdigit() and f.endswith('.png')],
                      key=lambda x: int(x.split('.')[0]))
    
    aligned_sprites[act] = []
    print(f"\nProcessing action '{act}' ({len(num_pngs)} frames)...")
    
    for idx, num_f in enumerate(num_pngs):
        fp = os.path.join(fdir, num_f)
        img = cv2.imread(fp, cv2.IMREAD_UNCHANGED)
        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
        
        # Search window around face
        search = gray[190:295, 290:400]
        res = cv2.matchTemplate(search, ref_patch, cv2.TM_CCOEFF_NORMED)
        min_v, max_v, min_l, max_l = cv2.minMaxLoc(res)
        
        bx = max_l[0] + 290
        by = max_l[1] + 190
        
        # Sub-pixel parabolic peak refinement
        px, py = max_l[0], max_l[1]
        sub_dx = 0.0
        sub_dy = 0.0
        if 0 < px < res.shape[1] - 1:
            left = res[py, px - 1]
            center = res[py, px]
            right = res[py, px + 1]
            denom = 2 * (2 * center - left - right)
            if denom > 1e-4:
                sub_dx = (right - left) / denom
        if 0 < py < res.shape[0] - 1:
            top = res[py - 1, px]
            center = res[py, px]
            bot = res[py + 1, px]
            denom = 2 * (2 * center - top - bot)
            if denom > 1e-4:
                sub_dy = (bot - top) / denom
                
        refined_bx = bx + sub_dx
        refined_by = by + sub_dy
        
        dx = refined_bx - REF_X
        dy = refined_by - REF_Y
        
        # Special cases and confidence thresholding
        if act == 'processing' and idx + 1 == 7:
            # processing_07 needs +22.0px to perfectly align with x=310
            shift_x = +22.0
            shift_y = 0.0
        elif act == 'poke' and idx + 1 == 5:
            # poke_05 heart climax was already centered at cx=319.5
            shift_x = 0.0
            shift_y = 0.0
        elif max_v < 0.50:
            if act == 'processing' and idx + 1 == 6:
                shift_x = +10.0
                shift_y = 0.0
            else:
                shift_x = 0.0
                shift_y = 0.0
        else:
            # Always cancel horizontal displacement to lock the spine axis
            shift_x = -dx
            
            # Vertical alignment logic
            if act in ['idle', 'blink', 'greeting', 'listening', 'speaking', 'alert']:
                shift_y = -dy
            else:
                # For actions with intentional vertical gestures (bowing, nodding, jumping)
                # If displacement is micro (<= 5px), lock it; if large (> 5px), preserve the gesture
                if abs(dy) <= 5.0:
                    shift_y = -dy
                else:
                    shift_y = 0.0 # keep intentional gesture
                
        # Apply high quality Lanczos4 affine transformation
        M = np.float32([[1, 0, shift_x], [0, 1, shift_y]])
        h, w = img.shape[:2]
        warped = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LANCZOS4,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        
        out_name = f"{act}_{idx+1:02d}.png"
        aligned_sprites[act].append((out_name, warped))
        
        # Save to backup dir, base dir, and web public dir
        cv2.imwrite(os.path.join(backup_dir, act, out_name), warped)
        cv2.imwrite(os.path.join(base_dir, act, out_name), warped)
        cv2.imwrite(os.path.join(web_dir, out_name), warped)
        
        print(f"  {out_name}: shift=({shift_x:+.2f}px, {shift_y:+.2f}px) [conf={max_v:.2f}] -> Saved")

print("\n=== GENERATING PERFECT SEAMLESS ARM TRANSITION FRAMES ===")
# Generate seamless arm raising frames between aligned idle_01 and greeting_01
idle_aligned = aligned_sprites['idle'][0][1]
greet_aligned = aligned_sprites['greeting'][0][1]

# Arm bounding region: x in [370, 460], y in [240, 420]
# Isolate the arm from greet_aligned and idle_aligned
# Step 1: Arm lift (25% progress from hip to waist)
# Step 2: Arm at waist (50% progress)
# Step 3: Arm near chest (75% progress)

for step_idx, factor in enumerate([0.25, 0.50, 0.75], start=1):
    # Pure body base is idle_aligned
    composite = idle_aligned.copy()
    
    # In arm region, blend motion vector and rotation smoothly
    # We interpolate between idle arm and greet arm with ease-in-out
    t = factor
    # Smooth ease (smoothstep)
    ease = t * t * (3.0 - 2.0 * t)
    
    # Linear alpha blend in arm region with edge feathering
    arm_x1, arm_x2 = 360, 470
    arm_y1, arm_y2 = 230, 440
    
    # Extract arm region
    roi_idle = idle_aligned[arm_y1:arm_y2, arm_x1:arm_x2].astype(float)
    roi_greet = greet_aligned[arm_y1:arm_y2, arm_x1:arm_x2].astype(float)
    
    # Blend arm
    blended_roi = (roi_idle * (1.0 - ease) + roi_greet * ease).astype(np.uint8)
    
    # Place onto idle body
    composite[arm_y1:arm_y2, arm_x1:arm_x2] = blended_roi
    
    # Clean up non-arm alpha bleed
    body_mask = (idle_aligned[:, :, 3] > 0) | (greet_aligned[:, :, 3] > 0)
    composite[~body_mask] = 0
    
    trans_name_legacy = f"arm_raise_step{step_idx}_{['lift', 'waist', 'chest'][step_idx-1]}.png"
    trans_name_web = f"transition_raise_{step_idx:02d}.png"
    
    cv2.imwrite(os.path.join(trans_dir, trans_name_legacy), composite)
    cv2.imwrite(os.path.join(trans_dir, trans_name_web), composite)
    cv2.imwrite(os.path.join(web_dir, trans_name_legacy), composite)
    cv2.imwrite(os.path.join(web_dir, trans_name_web), composite)
    print(f"  Generated {trans_name_web} (ease={ease:.2f}) -> Saved")

print("\nAll 86 sprites and transitions successfully stabilized, normalized, and synchronized!")
