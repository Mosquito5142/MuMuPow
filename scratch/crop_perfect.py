import cv2
import os

screen = cv2.imread("temp_screen.png")
if screen is None:
    print("Cannot find temp_screen.png")
    exit()

# Crop the orange cross button at the exact match location (852, 72) with size 27x28
# We will crop Y from 72 to 100, X from 852 to 879
# To make it clean, we can crop a slightly tight boundary:
# Let's crop Y: 72 to 100, X: 852 to 879
crop = screen[72:100, 852:879]

# Save to templates directories
dest1 = r"c:\Users\PC\Desktop\CODE\MuMupow\templates\close_btn_perfect.png"
dest2 = r"c:\Users\PC\Desktop\CODE\MuMupow\dist\templates\close_btn_perfect.png"

os.makedirs(os.path.dirname(dest1), exist_ok=True)
os.makedirs(os.path.dirname(dest2), exist_ok=True)

cv2.imwrite(dest1, crop)
cv2.imwrite(dest2, crop)
print("Saved perfect crop to:")
print(" -", dest1)
print(" -", dest2)

# Verify matching score using the new perfect template!
res = cv2.matchTemplate(screen, crop, cv2.TM_CCOEFF_NORMED)
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
print(f"Verify Matching Confidence with close_btn_perfect.png: {max_val:.4f}")
