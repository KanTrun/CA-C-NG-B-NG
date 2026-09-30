import cv2
import numpy as np

def run_verification():
    video_path = r"D:\Crew-Operations\hinh\demo_animation_smoothing.mp4"
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"=== AUTOMATED VERIFICATION: {total_frames} frames at {fps} FPS ===")
    
    prev_cx = None
    prev_cy = None
    prev_w = None
    
    max_dcx = 0.0
    max_dcy = 0.0
    max_dw = 0
    
    jitter_issues = []
    scale_issues = []
    
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Inspect character torso and head (exclude HUD)
        # Upper body region: y in [100, 500], x in [240, 480]
        char_crop = frame[100:500, 240:480]
        hsv = cv2.cvtColor(char_crop, cv2.COLOR_BGR2HSV)
        
        # Segment character foreground
        is_char = (hsv[:, :, 2] > 70) & ((hsv[:, :, 1] > 20) | (hsv[:, :, 2] > 120))
        
        # Sample spine / torso around center y in [200, 350], x in [50, 190]
        torso_mask = is_char[200:350, 50:190]
        ys_t, xs_t = np.where(torso_mask)
        
        if len(xs_t) > 50:
            cx = np.mean(xs_t) + 50 + 240
            cy = np.mean(ys_t) + 200 + 100
            w = xs_t.max() - xs_t.min() + 1
            
            if prev_cx is not None:
                dcx = abs(cx - prev_cx)
                dcy = abs(cy - prev_cy)
                dw = abs(w - prev_w)
                
                max_dcx = max(max_dcx, dcx)
                max_dcy = max(max_dcy, dcy)
                max_dw = max(max_dw, dw)
                
                # Flag sudden horizontal jump > 2.0px or vertical jump > 2.5px
                if dcx > 2.0 or dcy > 2.5:
                    jitter_issues.append((frame_idx, dcx, dcy))
                
                # Flag sudden width pop > 8px
                if dw > 8:
                    scale_issues.append((frame_idx, dw))
                    
            prev_cx = cx
            prev_cy = cy
            prev_w = w
            
        frame_idx += 1
        
    cap.release()
    
    print("\n--- VERIFICATION METRICS ---")
    print(f"Max adjacent horizontal displacement (max dcx): {max_dcx:.2f} px")
    print(f"Max adjacent vertical displacement (max dcy): {max_dcy:.2f} px")
    print(f"Max adjacent torso width change (max dw): {max_dw} px")
    print(f"Total Jitter Issues (dcx > 2.0px or dcy > 2.5px): {len(jitter_issues)}")
    print(f"Total Scale Popping Issues (dw > 8px): {len(scale_issues)}")
    
    if len(jitter_issues) == 0 and len(scale_issues) == 0:
        print("\n>>> RESULT: 100% STABLE, ZERO JITTER, ZERO SCALE POPPING! VERIFICATION PASSED! <<<")
        return True
    else:
        print(f"\n>>> RESULT: FAILED! Found {len(jitter_issues)} jitter frames and {len(scale_issues)} scale pop frames.")
        return False

if __name__ == '__main__':
    run_verification()
