import cv2
import numpy as np

screen = cv2.imread("temp_screen.png")
template = cv2.imread(r"c:\Users\PC\Desktop\CODE\MuMupow\dist\templates\close_btn.png")

if screen is None or template is None:
    print("Error loading images")
    exit()

best_score = 0
best_scale = 0
best_loc = (0, 0)

# Try scales from 1.0 to 4.0
for scale in np.linspace(1.0, 4.0, 31):
    w = int(template.shape[1] * scale)
    h = int(template.shape[0] * scale)
    if w <= 0 or h <= 0:
        continue
        
    resized_template = cv2.resize(template, (w, h), interpolation=cv2.INTER_LINEAR)
    
    # Check if resized template fits in the screen
    if resized_template.shape[0] > screen.shape[0] or resized_template.shape[1] > screen.shape[1]:
        continue
        
    res = cv2.matchTemplate(screen, resized_template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    if max_val > best_score:
        best_score = max_val
        best_scale = scale
        best_loc = max_loc

print(f"Best matching score: {best_score:.4f} at scale {best_scale:.2f}x at location {best_loc}")
# Let's crop around best location with the scaled template size to see what it is matching
w = int(template.shape[1] * best_scale)
h = int(template.shape[0] * best_scale)
crop = screen[best_loc[1]:best_loc[1]+h, best_loc[0]:best_loc[0]+w]
cv2.imwrite("best_match_crop.png", crop)
print("Saved crop to best_match_crop.png")
