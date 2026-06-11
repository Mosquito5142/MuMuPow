import cv2
import numpy as np

# Load temp_screen
screen = cv2.imread("temp_screen.png")
if screen is None:
    print("Cannot find temp_screen.png")
    exit()

# Let's crop around where the orange cross button is
# The orange cross is at the top right of the white window.
# Based on the screenshot:
# Width of screen: 960, Height: 540
# The announcement window starts around X=70 to 890, Y=110 to 470
# The orange cross is at X=860 to 900, Y=120 to 160
crop = screen[120:165, 860:905]
cv2.imwrite("orange_cross_on_screen.png", crop)
print("Crop shape:", crop.shape)
