import os
import cv2
import sys

# Add root folder to path so we can import MuMuController
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mumu_controller import MuMuController

def test_matching():
    device_id = "127.0.0.1:16384"
    local_path = "temp_screen.png"
    template_path = r"c:\Users\PC\Desktop\CODE\MuMupow\dist\templates\close_btn.png"
    
    controller = MuMuController()
    print(f"Using ADB Path: {controller.adb_path}")
    
    print(f"Taking screenshot from {device_id}...")
    success, out = controller.take_screenshot(device_id, local_path)
    if not success:
        print(f"Fail to capture: {out}")
        return
        
    print(f"Screenshot saved to {local_path}.")
    
    # Run matching
    screen = cv2.imread(local_path)
    template = cv2.imread(template_path)
    
    if screen is None or template is None:
        print("Error: screen or template is None!")
        print("Screen exists:", os.path.exists(local_path))
        print("Template exists:", os.path.exists(template_path))
        return
        
    print(f"Screen shape: {screen.shape}")
    print(f"Template shape: {template.shape}")
    
    res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    print(f"Matching Max Value (Confidence): {max_val:.4f}")
    
    h, w, _ = template.shape
    click_x = int(max_loc[0] + w / 2)
    click_y = int(max_loc[1] + h / 2)
    print(f"Proposed click coordinate: ({click_x}, {click_y})")
    
    # Save a copy with drawn box
    cv2.rectangle(screen, max_loc, (max_loc[0] + w, max_loc[1] + h), (0, 255, 0), 2)
    result_path = "match_result.png"
    cv2.imwrite(result_path, screen)
    print(f"Saved match visualization to {result_path}")

if __name__ == "__main__":
    test_matching()
