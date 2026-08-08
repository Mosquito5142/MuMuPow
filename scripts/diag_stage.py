"""วิเคราะห์ว่าทำไม Story Auto แตะด่านไม่ตรงบนเครื่องหนึ่ง แต่ตรงบนอีกเครื่อง

ใช้: python scripts/diag_stage.py ภาพหน้าเลือกด่าน.png [อีกรูป.png ...]

บอกว่า find_highlighted_stage เจอ "กรอบเลือกด่าน" กี่ข้าง — เพราะนั่นคือตัวตัดสิน:
  เจอ 2 ข้าง -> จุดแตะ = กึ่งกลางระหว่างกรอบ (แม่น)
  เจอ 1 ข้าง -> จุดแตะ = เดาบวก/ลบ half_card_w (100 px)  <-- ต้นเหตุของ "กดไม่ค่อยตรง"

และรายงานค่า HSV จริงของพิกเซลสว่างสุดในโซนสีเหลือง เทียบกับเกณฑ์ที่โค้ดใช้
(H 26-34, S 110-180, V>=246) จะได้รู้ว่าเครื่องนั้น "หลุดเกณฑ์ไปกี่หน่วย"
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mumu_controller import find_highlighted_stage, find_yellow_frame

# ต้องตรงกับค่าใน find_highlighted_stage เป๊ะ
H_LO, H_HI = 26, 34
S_LO, S_HI = 110, 180
V_LO = 246
MIN_H, MIN_W, MAX_W, MIN_AREA = 45, 18, 50, 600
HALF_CARD_W, THUMB_UP = 100, 45


def brackets_of(img):
    """ทำซ้ำขั้นตอนใน find_highlighted_stage เพื่อดูว่ามันเห็นกรอบอะไรบ้าง"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (H_LO, S_LO, V_LO), (H_HI, S_HI, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 25))
    dil = cv2.dilate(mask, kernel, iterations=1)
    n, _lbl, stats, cent = cv2.connectedComponentsWithStats(dil, connectivity=8)

    kept, rejected = [], []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        item = {"x": int(x), "y": int(y), "w": int(w), "h": int(h), "area": int(area),
                "cx": int(cent[i][0]), "cy": int(cent[i][1])}
        if h >= MIN_H and MIN_W <= w <= MAX_W and area >= MIN_AREA:
            kept.append(item)
        elif area >= 200:      # เก็บเฉพาะอันที่ "เกือบผ่าน" มาโชว์ว่าตกเพราะอะไร
            why = []
            if h < MIN_H:
                why.append(f"สูงไม่พอ h={h}<{MIN_H}")
            if not (MIN_W <= w <= MAX_W):
                why.append(f"กว้างผิดช่วง w={w} (ต้อง {MIN_W}-{MAX_W})")
            if area < MIN_AREA:
                why.append(f"เล็กไป area={area}<{MIN_AREA}")
            item["why"] = " · ".join(why)
            rejected.append(item)
    return kept, rejected, hsv


def yellow_stats(hsv):
    """ค่า HSV จริงของพิกเซลเหลืองสว่างสุด — ดูว่าห่างเกณฑ์ V>=246 แค่ไหน"""
    hue_ok = cv2.inRange(hsv, (H_LO, 80, 150), (H_HI, 255, 255))
    ys, xs = np.where(hue_ok > 0)
    if len(ys) == 0:
        return None
    v = hsv[ys, xs, 2]
    s = hsv[ys, xs, 1]
    top = np.argsort(v)[-max(1, len(v) // 200):]     # 0.5% ที่สว่างสุด
    return {"n": len(ys), "v_max": int(v.max()), "v_top_mean": float(v[top].mean()),
            "s_at_top": float(s[top].mean()), "v_p99": int(np.percentile(v, 99))}


def analyse(path):
    img = cv2.imread(path)
    if img is None:
        print(f"อ่านรูปไม่ได้: {path}")
        return
    h, w = img.shape[:2]
    print("=" * 70)
    print(f"ไฟล์: {os.path.basename(path)}   ขนาดจอ: {w}x{h}")

    kept, rejected, hsv = brackets_of(img)
    print(f"\n[1] กรอบเลือกด่านที่ผ่านเกณฑ์: {len(kept)} อัน")
    for b in sorted(kept, key=lambda b: b["cx"]):
        print(f"      cx={b['cx']:4} cy={b['cy']:4}  w={b['w']:3} h={b['h']:3} area={b['area']:5}")

    if rejected:
        print(f"\n    เกือบผ่านแต่ตก {len(rejected)} อัน (ถ้าอันที่ควรเป็นกรอบอยู่ในนี้ = เกณฑ์คับไป):")
        for b in sorted(rejected, key=lambda b: -b["area"])[:6]:
            print(f"      cx={b['cx']:4} cy={b['cy']:4}  w={b['w']:3} h={b['h']:3} "
                  f"area={b['area']:5}  <- {b['why']}")

    # จุดแตะจริงที่ตัวรันจะใช้
    found, cx, cy = find_highlighted_stage(cv2.imencode(".png", img)[1].tobytes())
    print(f"\n[2] จุดที่ Story Auto จะแตะ: ", end="")
    if not found:
        print("ไม่เจอด่านเลย -> จะไม่แตะ (จอนี้จะค้าง/ไล่กู้)")
    else:
        print(f"({cx}, {cy})")
        if len(kept) >= 2:
            same = [b for b in kept if abs(b["cy"] - max(kept, key=lambda z: z["area"])["cy"]) < 15]
            l, r = min(same, key=lambda b: b["cx"]), max(same, key=lambda b: b["cx"])
            if r["cx"] - l["cx"] > 80:
                print(f"      โหมด: กึ่งกลางระหว่าง 2 กรอบ (ห่าง {r['cx'] - l['cx']} px) = แม่นยำ ✅")
            else:
                print(f"      โหมด: กรอบ 2 อันชิดกันเกินไป ({r['cx'] - l['cx']} px <= 80) "
                      f"-> ตกไปใช้การเดา ±{HALF_CARD_W} px ⚠️")
        else:
            print(f"      โหมด: เจอกรอบเดียว -> เดาว่าการ์ดอยู่ห่างออกไป {HALF_CARD_W} px ⚠️")
            print("      *** นี่คือสาเหตุของ 'กดไม่ค่อยตรง' ***")

    st = yellow_stats(hsv)
    print(f"\n[3] ความสว่างสีเหลืองบนจอนี้ (เกณฑ์ที่โค้ดต้องการ: V >= {V_LO})")
    if st is None:
        print("      ไม่เจอโซนสีเหลืองเลย")
    else:
        flag = "ผ่าน ✅" if st["v_top_mean"] >= V_LO else f"ไม่ผ่าน ❌ (ขาดอีก {V_LO - st['v_top_mean']:.1f})"
        print(f"      V สูงสุด={st['v_max']}  V เฉลี่ยของ 0.5% ที่สว่างสุด={st['v_top_mean']:.1f}  -> {flag}")
        print(f"      S ตรงจุดสว่างสุด={st['s_at_top']:.1f}  (เกณฑ์ต้องอยู่ {S_LO}-{S_HI}) ", end="")
        print("ผ่าน ✅" if S_LO <= st["s_at_top"] <= S_HI else "ไม่ผ่าน ❌")

    yf, yx, yy, box = find_yellow_frame(cv2.imencode(".png", img)[1].tobytes())
    print(f"\n[4] ตัวสำรอง find_yellow_frame: ", end="")
    print(f"เจอที่ ({yx},{yy}) กล่อง={box}" if yf else "ไม่เจอ")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p in sys.argv[1:]:
        analyse(p)
