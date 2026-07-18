import subprocess
import os
import sys
import shutil
import tempfile
import re
import time
import json
import base64
import unicodedata
import cv2
import numpy as np
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor


_TESSERACT_CMD = None


def find_tesseract():
    """หา tesseract.exe: ข้างๆ โปรแกรม (โฟลเดอร์ tesseract/) -> ที่ติดตั้งมาตรฐาน -> PATH.
    คืน path ของ tesseract.exe หรือ None ถ้าไม่พบ (แคชผลไว้)"""
    global _TESSERACT_CMD
    if _TESSERACT_CMD is not None:
        return _TESSERACT_CMD or None
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(app_dir, "tesseract", "tesseract.exe"),  # ฝังมากับแอป (ถ้ามี)
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
    ]
    which = shutil.which("tesseract")
    if which:
        candidates.append(which)
    for c in candidates:
        if c and os.path.exists(c):
            _TESSERACT_CMD = c
            return c
    _TESSERACT_CMD = ""
    return None


# ===== ตัวประเมินขีดจำกัดการรัน MuMu บนเครื่องนี้ (Capacity Estimator) =====
# โปรไฟล์มาตรฐาน 1 จอ (ตามที่ลูกค้าใช้): CPU 2 คอร์, RAM 3GB, 540x960 DPI160, FPS 15
# 540x960 + FPS 15 = โหลดต่อจอเบามาก -> คอขวดจริงมักเป็น RAM ไม่ใช่ CPU
DEFAULT_MUMU_PROFILE = {
    "ram_per_instance_gb": 3.0,   # RAM ที่ตั้งให้ MuMu 1 จอ
    "cores_per_instance": 2,      # คอร์ที่ตั้งให้ MuMu 1 จอ
    "host_reserve_ram_gb": 2.5,   # กัน RAM ไว้ให้ Windows + MuMupow + ตัวจัดการ MuMu
    "host_reserve_cores": 2,      # กัน logical core ไว้ให้ระบบ
    "cpu_oversubscribe": 1.5,     # จอ FPS-cap เบา แชร์คอร์ได้ (1.0 = ไม่ oversubscribe)
}


def get_host_specs():
    """อ่านสเปกเครื่องจริงด้วย psutil. คืน dict (มี available_ok=False ถ้า psutil ใช้ไม่ได้)"""
    try:
        import psutil
    except Exception as e:
        return {"available_ok": False, "error": str(e)}
    try:
        vm = psutil.virtual_memory()
        return {
            "available_ok": True,
            "logical_cores": psutil.cpu_count(logical=True) or 0,
            "physical_cores": psutil.cpu_count(logical=False) or 0,
            "total_ram_gb": round(vm.total / (1024 ** 3), 2),
            "available_ram_gb": round(vm.available / (1024 ** 3), 2),
        }
    except Exception as e:
        return {"available_ok": False, "error": str(e)}


def estimate_mumu_capacity(specs, profile=None):
    """คำนวณว่ารัน MuMu ได้กี่จอจากสเปกเครื่อง (pure math — เทสได้)

    specs: dict จาก get_host_specs() (ต้องมี logical_cores, total_ram_gb, available_ram_gb)
    profile: dict override DEFAULT_MUMU_PROFILE (เช่น ram_per_instance_gb)

    คืน dict: recommended (เต็มประสิทธิภาพ), ram_limit, cpu_limit, bottleneck,
    open_now (เปิดเพิ่มได้อีกกี่จอ ณ RAM ว่างตอนนี้), และค่ากลางที่ใช้คำนวณ
    """
    p = dict(DEFAULT_MUMU_PROFILE)
    if profile:
        p.update({k: v for k, v in profile.items() if v is not None})

    ram_each = float(p["ram_per_instance_gb"]) or 3.0
    cores_each = max(1, int(p["cores_per_instance"]))
    reserve_ram = float(p["host_reserve_ram_gb"])
    reserve_cores = int(p["host_reserve_cores"])
    oversub = float(p["cpu_oversubscribe"]) or 1.0

    logical = int(specs.get("logical_cores", 0) or 0)
    total_ram = float(specs.get("total_ram_gb", 0) or 0)
    avail_ram = float(specs.get("available_ram_gb", 0) or 0)

    # คอขวด RAM: RAM ที่ใช้ได้จริงหารต่อจอ
    ram_limit = int(max(0, (total_ram - reserve_ram) // ram_each))
    # คอขวด CPU: คอร์ที่เหลือ * ตัวคูณ oversubscribe หารต่อจอ
    usable_cores = max(0, logical - reserve_cores)
    cpu_limit = int(max(0, (usable_cores * oversub) // cores_each))

    recommended = min(ram_limit, cpu_limit)
    bottleneck = "RAM" if ram_limit <= cpu_limit else "CPU"

    # เปิดเพิ่มได้อีกกี่จอจาก RAM ว่าง 'ตอนนี้' (กันเผื่อ 0.5GB) — ไม่เกินค่าแนะนำ
    open_now = int(max(0, (avail_ram - 0.5) // ram_each))
    open_now = min(open_now, recommended)

    return {
        "recommended": recommended,
        "ram_limit": ram_limit,
        "cpu_limit": cpu_limit,
        "bottleneck": bottleneck,
        "open_now": open_now,
        "ram_each": ram_each,
        "cores_each": cores_each,
        "reserve_ram": reserve_ram,
        "reserve_cores": reserve_cores,
        "oversub": oversub,
        "logical_cores": logical,
        "total_ram_gb": total_ram,
        "available_ram_gb": avail_ram,
    }


# ===== ตัวช่วยดึงรายชื่อสมาชิกชมรม (Guild Member Grabber) =====
def stitch_png_vertically(png_list, max_width=1080, gap=8):
    """ต่อภาพ PNG หลายรูปเป็นรูปเดียวแนวตั้ง (เลียนแบบ stitch ฝั่งเว็บ guild-check)

    png_list: list ของ bytes (PNG). คืน PNG bytes ของภาพรวม หรือ None ถ้าไม่มีรูปใช้ได้
    ย่อรูปที่กว้างเกิน max_width ลง แล้ววางกึ่งกลางบนพื้นขาว เว้นช่อง gap ระหว่างรูป
    """
    imgs = []
    for b in png_list:
        if not b:
            continue
        im = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
        if im is None:
            continue
        h, w = im.shape[:2]
        if w > max_width:
            ratio = max_width / float(w)
            im = cv2.resize(im, (max_width, max(1, int(h * ratio))), interpolation=cv2.INTER_AREA)
        imgs.append(im)
    if not imgs:
        return None

    width = max(im.shape[1] for im in imgs)
    total_h = sum(im.shape[0] for im in imgs) + gap * (len(imgs) - 1)
    canvas = np.full((total_h, width, 3), 255, dtype=np.uint8)  # พื้นขาว
    y = 0
    for im in imgs:
        h, w = im.shape[:2]
        x = (width - w) // 2
        canvas[y:y + h, x:x + w] = im
        y += h + gap

    ok, buf = cv2.imencode(".png", canvas)
    return buf.tobytes() if ok else None


def png_similarity(a, b, tol=12):
    """คืนค่าความเหมือนของสอง PNG เป็นสัดส่วน 0..1 (พิกเซลเทาที่ต่างกันน้อยกว่า tol)

    ใช้เช็คว่าเลื่อนจอแล้วภาพเปลี่ยนไหม — ถ้าเหมือนเกือบ 1.0 แปลว่าเลื่อนไม่ไปแล้ว (สุดล่าง)
    """
    ia = cv2.imdecode(np.frombuffer(a, np.uint8), cv2.IMREAD_GRAYSCALE) if a else None
    ib = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_GRAYSCALE) if b else None
    if ia is None or ib is None:
        return 0.0
    if ia.shape != ib.shape:
        ib = cv2.resize(ib, (ia.shape[1], ia.shape[0]))
    diff = cv2.absdiff(ia, ib)
    same = int(np.count_nonzero(diff < tol))
    return same / float(diff.size)


def find_yellow_frame(screen_bytes, min_area_frac=0.008, h_lo=18, h_hi=34,
                      s_min=110, v_min=120):
    """หา 'กรอบสีเหลือง' ของด่านถัดไปบนหน้าเลือกด่าน (Story map)

    คืน (found, cx, cy, (x, y, w, h)). ตรวจด้วย HSV mask สีเหลือง-ส้ม แล้วหากล่องครอบที่
    ใหญ่พอ (กันสับสนกับ ⭐ ดาวเหลืองดวงเล็ก ด้วย min_area_frac) — เลือกกล่องที่ใหญ่สุด
    คืนจุดกึ่งกลางไว้แตะ

    รับเป็น PNG bytes (จาก capture_screenshot_bytes). ปรับช่วงสีได้ผ่านพารามิเตอร์
    """
    if not screen_bytes:
        return False, 0, 0, None
    img = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return False, 0, 0, None
    sh, sw = img.shape[:2]
    screen_area = float(sh * sw)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (h_lo, s_min, v_min), (h_hi, 255, 255))
    # ปิดช่องว่างของกรอบ (กรอบเป็นเส้นขอบ ไม่ตัน) ให้กลายเป็นบล็อกเดียว
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < min_area_frac * screen_area:
            continue  # เล็กเกินไป (น่าจะเป็นดาว/ไอคอน ไม่ใช่กรอบด่าน)
        if w < 50 or h < 50:
            continue  # บาง/เล็กเกินไป (แถบ UI สีเหลือง ไม่ใช่กรอบด่าน)
        if area > best_area:
            best_area = area
            best = (x, y, w, h)

    if best is None:
        return False, 0, 0, None
    x, y, w, h = best
    return True, x + w // 2, y + h // 2, best


def find_highlighted_stage(screen_bytes, half_card_w=100, thumb_up=45):
    """หา 'ด่านที่ถูกไฮไลท์' บนหน้าเลือกด่าน โดยไม่พึ่ง AI — แม่นยำแม้ภาพประกอบด่านอื่น
    มีโทนส้ม/เหลือง (ที่ทำให้ find_yellow_frame เลือกผิด)

    หลักการ: 'กรอบเลือก' ของเกมเป็นสีเหลือง UI สว่างจัดมาก (V≈254) ซึ่งสว่างกว่าสีเหลือง
    ในภาพศิลป์ (V≤243) — ใช้ threshold V สูงคัดเฉพาะกรอบ UI ออกมา แล้ว dilate แนวตั้งเชื่อม
    'แขนกรอบมุมตัว L/[' ให้เป็นแท่งสูง ๆ (กรอบเลือกจะสูง h≥45; ดาวรางวัล/ไอคอนจะเตี้ย h<40)

    - เจอกรอบซ้าย+ขวา (ด่านกลางจอ): จุดแตะ = กึ่งกลางระหว่างสองกรอบ
    - เจอกรอบเดียว (ด่านริมจอถูกตัดขอบ): ดูแกนตั้งว่าเป็น '[' หรือ ']' แล้ว offset เข้าการ์ด

    คืน (found, cx, cy)
    """
    if not screen_bytes:
        return False, 0, 0
    img = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return False, 0, 0
    sh, sw = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # เหลือง UI สว่างจัด: H 26-34, S 110-180, V≥246 (ตัดเหลืองภาพศิลป์ที่ V ต่ำกว่าออก)
    mask = cv2.inRange(hsv, (26, 110, 246), (34, 180, 255))
    # dilate แนวตั้งมาก แนวนอนน้อย -> เชื่อมแขนกรอบ '[' เป็นแท่งเดียว แต่ไม่รวมดาวที่เรียงแนวนอน
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 25))
    dil = cv2.dilate(mask, kernel, iterations=1)

    n, _lbl, stats, cent = cv2.connectedComponentsWithStats(dil, connectivity=8)
    brackets = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        # กรอบเลือกเป็นเส้น '[' สูงและ 'มีแขน' (หนา): h≥45, กว้าง 18-50 (กรอบจริงวัดได้ w≈26-28
        # ทุกจอ เพราะมีแขนบน/ล่าง) และ area≥600 — ตัด 'เส้นพื้นไม้/รอยต่อกระเบื้อง' ในคัตซีนที่เป็น
        # เส้นตั้งบางๆ (w≈9, area≈350) ซึ่งเคยถูกจับผิดเป็นกรอบเดียวจนแตะกลางจอผิดด่าน
        if h >= 45 and 18 <= w <= 50 and area >= 600:
            brackets.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h),
                             "area": int(area), "cx": int(cent[i][0]), "cy": int(cent[i][1])})
    if not brackets:
        return False, 0, 0

    # เลือก 'กรอบหลัก' = อันที่ area ใหญ่สุด (กรอบเลือกจริงมักหนา/ใหญ่กว่าจุดสว่างในภาพศิลป์)
    tallest = max(brackets, key=lambda b: b["area"])
    # จัดกลุ่มกรอบของ 'การ์ดเดียวกัน': ต้อง cy ใกล้กันจริง (<15) และ cx ห่างไม่เกินความกว้างการ์ด
    # (<260) — กัน false-positive จุดสว่างในภาพด่านอื่นถูกจับรวมจนจุดกึ่งกลางเพี้ยนไปคนละด่าน
    same = [b for b in brackets
            if abs(b["cy"] - tallest["cy"]) < 15 and abs(b["cx"] - tallest["cx"]) < 260]
    left = min(same, key=lambda b: b["cx"])
    right = max(same, key=lambda b: b["cx"])

    if right["cx"] - left["cx"] > 80:
        # เจอทั้งกรอบซ้ายและขวา -> การ์ดอยู่ตรงกลาง
        card_cx = (left["cx"] + right["cx"]) // 2
    else:
        # เจอกรอบเดียว -> ดูว่าแกนตั้ง (spine) อยู่ซ้ายหรือขวาของกล่อง
        b = tallest
        col_sum = mask[b["y"]:b["y"] + b["h"], b["x"]:b["x"] + b["w"]].sum(axis=0)
        spine = int(np.argmax(col_sum)) if col_sum.size else 0
        if spine < b["w"] / 2:      # spine ซ้าย = '[' -> การ์ดอยู่ทางขวา
            card_cx = b["cx"] + half_card_w
        else:                        # spine ขวา = ']' -> การ์ดอยู่ทางซ้าย
            card_cx = b["cx"] - half_card_w

    card_cx = max(20, min(sw - 20, card_cx))
    tap_y = max(20, tallest["cy"] - thumb_up)  # ขยับขึ้นเข้าหา thumbnail (พ้น label bar)
    return True, card_cx, tap_y


def find_swipe_glow(screen_bytes):
    """หา 'ไอคอนบาสเรืองแสง' ของ cutscene แบบปัดนิ้ว (มีลูกศร >>>) — เชื่อถือได้กว่า template
    เพราะ glow สีฟ้าอมขาวคงที่เสมอ ไม่ขึ้นกับพื้นหลังที่เปลี่ยนทุกฉาก (template story_swipe.png
    match ไม่ค่อยติดเพราะพื้นหลังต่างกัน)

    ตัวไอคอนเป็น 'วงกลม' ฟ้าสว่างจัด — คัดด้วย: ทรงกลม (fill≥0.6, w/h≈1), ขนาด 42-75px,
    และอยู่ครึ่งล่างของจอ (y≥200 กันปุ่มย้อนกลับ ← สีฟ้ามุมซ้ายบน)

    สำคัญ: ต้องแยกจาก 'จอยสติ๊ก (ปุ่มเดิน)' ตอนแมตช์ ที่เป็นลูกบาสน้ำเงินในวงแหวนเช่นกัน —
    ตัวแยกคือ 'glow ฟ้าเรืองรอบลูกบอล' (halo): ไอคอนปัดมี halo cyan สูง (~0.22) ส่วนจอยสติ๊ก
    เป็นลูกบอลตันขอบขาว ไม่มี glow (halo~0.07) ถ้า halo ต่ำ = จอยสติ๊ก (อยู่ในแมตช์ auto) -> ข้าม

    คืน (found, cx, cy) จุดที่ควรเริ่มปัดนิ้ว
    """
    if not screen_bytes:
        return False, 0, 0
    img = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return False, 0, 0
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    glow = cv2.inRange(hsv, (85, 40, 235), (115, 255, 255))
    cnts, _ = cv2.findContours(glow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # mask cyan สว่าง (สำหรับวัด halo รอบลูกบอล)
    cyan = cv2.inRange(hsv, (85, 60, 225), (115, 255, 255)) > 0
    yy, xx = np.ogrid[:H, :W]

    best = None
    best_area = 0
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 450:             # ลูกบอลเรืองแสงมีหลายขนาด (บางฉากเล็กแค่ ~37px)
            continue
        x, y, w, h = cv2.boundingRect(c)
        if not (35 <= w <= 80 and 35 <= h <= 80):
            continue
        if not (0.65 <= w / h <= 1.5):
            continue
        # บางฉากลูกบอลเป็น 'วงแหวน' (ไส้ในเป็นลายบาส ไม่ใช่ฟ้า) fill ต่ำได้ -> ใช้แค่กันขยะจริงๆ
        if area / (w * h) < 0.1:
            continue
        cx = int(x + w / 2)
        cy = int(y + h / 2)
        if cy < 100:               # มุมบนสุด = ปุ่ม back (y~40) ไม่ใช่ไอคอนโต้ตอบ
            continue
        # วัด halo: สัดส่วนพิกเซล cyan สว่างในวงแหวนรัศมี 22-42px รอบลูกบอล
        dist = (xx - cx) ** 2 + (yy - cy) ** 2
        ring = (dist >= 22 * 22) & (dist <= 42 * 42)
        ring_n = int(ring.sum())
        halo = float((ring & cyan).sum()) / ring_n if ring_n else 0.0
        # halo ใช้แยก 'ลูกบอลปัด vs จอยสติ๊ก' ได้เฉพาะในโซนจอยสติ๊ก (ซ้ายล่าง) เท่านั้น —
        # จอยสติ๊ก (ปุ่มเดิน) อยู่มุมซ้ายล่างเสมอ ลูกบอลปัดที่อยู่ 'นอกโซนนั้น' (บน/ขวา/กลาง)
        # ไม่มีทางเป็นจอยสติ๊ก จึงไม่ต้องเข้มเรื่อง glow (ลูกเล็ก ~35px จะ halo ต่ำ 0.06 ทั้งที่
        # เรืองแสงจริง เพราะวงวัด halo 22-42px หลุดออกนอกตัวลูก) — เคยทำให้พลาดคัตซีน 'เก็บลูกบอล'
        in_joystick_zone = (cx < W * 0.42 and cy > H * 0.5)
        if halo < (0.085 if in_joystick_zone else 0.03):
            continue
        if area > best_area:
            best_area = area
            best = (cx, cy)
    if best is None:
        return False, 0, 0
    return True, best[0], best[1]


def in_match_autoplay(screen_bytes):
    """ตรวจว่าอยู่ใน 'แมตช์ที่กำลัง auto-play' ไหม โดยดู 'จอยสติ๊ก (ปุ่มเดิน)' มุมซ้ายล่าง
    = ลูกบาสน้ำเงินทรงกลม ขนาด ~44-60px แต่ 'ไม่มี glow ฟ้าเรือง' (halo ต่ำ) ต่างจากไอคอนปัด

    ระหว่างแมตช์ เกมเล่นเองอยู่แล้ว ไม่ควรแตะ/ปัด/เรียก AI อะไรเลย — ใช้เช็คเพื่อ 'รอเฉยๆ'
    คืน True ถ้าเจอจอยสติ๊ก (อยู่ในแมตช์)
    """
    if not screen_bytes:
        return False
    img = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return False
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    glow = cv2.inRange(hsv, (85, 40, 235), (115, 255, 255))
    cyan = cv2.inRange(hsv, (85, 60, 225), (115, 255, 255)) > 0
    cnts, _ = cv2.findContours(glow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    yy, xx = np.ogrid[:H, :W]
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 900:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if not (42 <= w <= 75 and 42 <= h <= 75):
            continue
        if not (0.7 <= w / h <= 1.4) or area / (w * h) < 0.6:
            continue
        cx, cy = int(x + w / 2), int(y + h / 2)
        # จอยสติ๊กอยู่มุมซ้ายล่าง
        if not (cx < W * 0.4 and cy > H * 0.55):
            continue
        dist = (xx - cx) ** 2 + (yy - cy) ** 2
        ring = (dist >= 22 * 22) & (dist <= 42 * 42)
        rn = int(ring.sum())
        halo = float((ring & cyan).sum()) / rn if rn else 0.0
        # ลูกบอลไม่มี glow ฟ้าเรือง (halo≈0.07) = จอยสติ๊ก; ถ้ามี glow = ไอคอนปัด (ไม่ใช่จอยสติ๊ก)
        # ใช้เกณฑ์ 0.095 เท่ากับ find_swipe_glow เพื่อไม่ให้ทับซ้อนกัน
        if halo < 0.095:
            return True
    return False


_TESS_LANGS = None
_TESSDATA_DIR = None

# ภาษาที่รองรับสำหรับอ่านชื่อสมาชิกชมรม (นอกจาก eng) — ไทย/ญี่ปุ่น/เกาหลี/จีน
_GUILD_OCR_LANG_ORDER = ["eng", "tha", "jpn", "kor", "chi_sim", "chi_tra"]


def set_tessdata_dir(path):
    """ชี้ให้ Tesseract ใช้ traineddata จากโฟลเดอร์นี้ (สำหรับภาษาที่โหลดเพิ่มเอง เช่น jpn/kor/chi).
    ส่ง None/"" เพื่อกลับไปใช้ tessdata มาตรฐานของระบบ"""
    global _TESSDATA_DIR, _TESS_LANGS
    _TESSDATA_DIR = path or None
    _TESS_LANGS = None  # ล้างแคชภาษา จะได้อ่านรายการใหม่จากโฟลเดอร์ที่ตั้ง


def _tessdata_args():
    return ["--tessdata-dir", _TESSDATA_DIR] if _TESSDATA_DIR else []


def guild_ocr_langs():
    """สตริงภาษาสำหรับ OCR รายชื่อชมรม รวมทุกภาษาที่ติดตั้งไว้ (eng ก่อนเสมอ).
    เช่น 'eng+tha+jpn+kor+chi_sim+chi_tra' — ถ้าไม่มีภาษาไหนก็ข้ามไป"""
    have = available_tesseract_langs()
    picked = [l for l in _GUILD_OCR_LANG_ORDER if l in have]
    return "+".join(picked) if picked else "eng"


def available_tesseract_langs():
    """คืน set ของภาษาที่ Tesseract มี (แคชไว้). ใช้เลือกว่าจะ OCR ด้วยภาษาใดบ้าง"""
    global _TESS_LANGS
    if _TESS_LANGS is not None:
        return _TESS_LANGS
    cmd = find_tesseract()
    langs = set()
    if cmd:
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            r = subprocess.run([cmd, *_tessdata_args(), "--list-langs"], capture_output=True, text=True,
                               startupinfo=si, timeout=10)
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line and " " not in line and ":" not in line:
                    langs.add(line)
        except Exception:
            pass
    _TESS_LANGS = langs
    return langs


def ocr_text_tesseract(screen_bytes, region=None, lang="eng", psm=6, scale=2):
    """OCR ข้อความทั่วไป (ไม่จำกัดเฉพาะตัวเลข) จากภาพ PNG หรือเฉพาะ region

    คืน (ok, text, raw). raw='no_tesseract' ถ้าไม่พบ tesseract.exe
    ใช้สำหรับอ่านรายชื่อสมาชิกชมรม — เทาภาพ + ขยาย แล้วส่งให้ tesseract อ่านทั้งบล็อก (psm 6)
    """
    cmd = find_tesseract()
    if not cmd:
        return False, "", "no_tesseract"
    tmp = None
    try:
        if not screen_bytes:
            return False, "", ""
        img = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return False, "", ""
        if region:
            sh, sw = img.shape[:2]
            x = max(0, int(region.get("x", 0)))
            y = max(0, int(region.get("y", 0)))
            w = int(region.get("w", 0))
            h = int(region.get("h", 0))
            if w > 0 and h > 0:
                img = img[y:min(sh, y + h), x:min(sw, x + w)]
                if img.size == 0:
                    return False, "", ""
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if scale and scale != 1:
            g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        fd, tmp = tempfile.mkstemp(suffix=".png", prefix="guild_ocr_")
        os.close(fd)
        cv2.imwrite(tmp, g)

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        res = subprocess.run(
            [cmd, *_tessdata_args(), tmp, "stdout", "-l", lang, "--psm", str(psm)],
            capture_output=True, startupinfo=si, timeout=60,
        )
        txt = res.stdout.decode("utf-8", errors="ignore")
        return True, txt, txt
    except Exception as e:
        return False, "", str(e)
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except Exception:
                pass


# ===== แยก/กรองชื่อสมาชิกชมรมจากข้อความ OCR (พอร์ตจาก lib/guild-ocr.ts ฝั่งเว็บ) =====
_GUILD_EXACT_LABELS = {
    "guild", "member", "members", "level", "status", "rank", "search",
    "weekly", "activity", "online", "offline",
    "สมาชิก", "เลเวล", "สถานะ", "แรงค์", "ค้นหา", "ชมรม",
}
_GUILD_THAI_STATUS = [
    "สมาชิก", "นาที", "ชั่วโมง", "ก่อน", "ออกจากชมรม", "กัปตัน", "ดาวรุ่ง", "แอคทีฟ",
    "โปรดใส่", "หน้าแรก", "เกมเพลย์", "บันทึกประจำวัน", "ข้ามเซิร์ฟ",
]
_GUILD_EN_TIME = re.compile(r"\b(?:minutes?|hours?|ago)\b", re.I)

# อักษร CJK/คานะ/ฮันกึล — ชื่อญี่ปุ่น/เกาหลี/จีน (นับเป็นตัวอักษรที่ยอมรับได้)
_CJK_CHARS = "぀-ヿ㐀-鿿가-힣"
# สคริปต์ที่ไม่มีช่องว่างในคำ (ไทย + CJK) — ใช้รวมช่องว่างที่ Tesseract แทรกผิด
_GUILD_NOSPACE = "฀-๿" + _CJK_CHARS
_GUILD_JOIN_SPACE = re.compile(r"(?<=[" + _GUILD_NOSPACE + r"])[ \t]+(?=[" + _GUILD_NOSPACE + r"])")
_GUILD_CJK = re.compile("[" + _CJK_CHARS + "]")
_GUILD_NAME_CHARS = re.compile(r"[A-Za-z0-9฀-๿" + _CJK_CHARS + "]")
# ตัวอักษร/เลขที่ "ไม่ใช่ไทย" (ละติน/เลขอารบิก/CJK) — ใช้ดูว่าบรรทัดเป็นไทยล้วนไหม
_NON_THAI_NAME = re.compile(r"[A-Za-z0-9" + _CJK_CHARS + "]")
# สระ/วรรณยุกต์ไทย — คำไทยจริงต้องมีอย่างน้อยหนึ่งตัว (อักษรมั่วจากเส้นคั่นมักเป็นพยัญชนะล้วน)
_THAI_VOWEL_MARK = set("ะัาำิีึืุูๅ็เแโใไ่้๊๋์ํ")
_THAI_LETTER = re.compile(r"[ก-ฮ]")


def _is_noise_line(line):
    """ตรวจบรรทัด 'อักษรมั่ว' ที่มักมาจากเส้นคั่น/พื้นหลัง ไม่ใช่ชื่อจริง:
    - อักษรตัวเดิมซ้ำๆ (เช่น 'รรรรรร', 'ーーーー', 'พรรรรร')
    - ไทยล้วนที่ไม่มีสระเลย (พยัญชนะมั่ว เช่น 'พพลดด๓')"""
    compact = re.sub(r"\s+", "", line)
    if len(compact) < 4:
        return False
    uniq = set(compact)
    if len(uniq) <= 2:
        return True
    if max(compact.count(c) for c in uniq) / len(compact) >= 0.55:
        return True
    # ไทยล้วน (ไม่มีละติน/เลข/CJK) แต่ไม่มีสระเลย -> อักษรมั่ว
    if _THAI_LETTER.search(compact) and not _NON_THAI_NAME.search(compact):
        if not any(c in _THAI_VOWEL_MARK for c in compact):
            return True
    return False


def normalize_guild_name(value):
    """ทำให้ชื่อเป็นรูปมาตรฐานเพื่อตัดซ้ำ (NFKC, ตัด zero-width, รวมช่องว่าง, ตัวพิมพ์เล็ก)"""
    v = unicodedata.normalize("NFKC", value or "")
    v = re.sub('[​-‍⁠﻿]', '', v)
    v = re.sub(r"\s+", " ", v.strip())
    return v.lower()


def _clean_ocr_line(line):
    s = unicodedata.normalize("NFKC", line)
    s = re.sub(r"^[|()\[\]{}\s]+|[|()\[\]{}\s]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Tesseract มักแทรกช่องว่างระหว่างตัวอักษรไทย/ญี่ปุ่น/เกาหลี/จีน — รวมกลับให้เป็นคำเดียว
    s = _GUILD_JOIN_SPACE.sub("", s)
    return s


def _extract_name_candidate(line):
    s = re.sub(r"\s+\d{1,2}\s+\d{1,2}\s+(?:online|offline)$", "", line, flags=re.I)
    s = re.sub(r"\s+\d{1,2}\s+\d{1,2}\s+\d+\s+(?:minutes?|hours?)\s+ago$", "", s, flags=re.I)
    s = re.sub(r"\s+\d{1,2}\s+\d{1,2}$", "", s)
    return s.strip()


def _is_likely_member_name(line):
    if not line:
        return False
    # ชื่อ CJK มักสั้น (2 ตัวก็เป็นชื่อจริง เช่น 小明) — ผ่อนความยาวขั้นต่ำเมื่อมีอักษร CJK
    min_len = 2 if _GUILD_CJK.search(line) else 3
    if len(line) < min_len or len(line) > 32:
        return False
    low = line.lower()
    if low in _GUILD_EXACT_LABELS:
        return False
    words = low.split()
    if words and all(w in _GUILD_EXACT_LABELS for w in words):
        return False
    if _GUILD_EN_TIME.search(line):
        return False
    if any(frag in line for frag in _GUILD_THAI_STATUS):
        return False
    if re.fullmatch(r"\d{1,2}", line):
        return False
    if re.fullmatch(r"[ivxlcdm]+", line, re.I):
        return False
    if _is_noise_line(line):
        return False
    # ต้องมีตัวอักษร/ตัวเลขอย่างน้อย 1 ตัว (ละติน/ไทย/เลข/ญี่ปุ่น/เกาหลี/จีน)
    if not _GUILD_NAME_CHARS.search(line):
        return False
    return True


def extract_guild_member_names(text):
    """แยกรายชื่อสมาชิกชมรมจากข้อความ OCR + ตัดบรรทัดขยะ/ป้ายกำกับ/เวลา + ตัดชื่อซ้ำ
    คืน list ของชื่อ (คงลำดับที่เจอครั้งแรก)"""
    seen = set()
    names = []
    for raw in re.split(r"\r?\n", text or ""):
        line = _extract_name_candidate(_clean_ocr_line(raw))
        if not _is_likely_member_name(line):
            continue
        norm = normalize_guild_name(line)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        names.append(line)
    return names


# Characters that the on-device shell (/system/bin/sh) interprets when running
# `input text ...`. They must be backslash-escaped or the text gets mangled /
# truncated silently. Space is sent as the special token %s (an `input` quirk).
_ADB_TEXT_SPECIAL = set(" '\"`$&|;<>()*\\!?#~{}[]^")


def escape_adb_text(text):
    """Escapes a string so `adb shell input text` sends it verbatim.

    Without this, passwords/emails containing shell metacharacters such as
    & ( ) < > | ; ' " $ ` are interpreted by the device shell and the account
    silently fails to log in. Returns the escaped token string.
    """
    out = []
    for ch in str(text):
        if ch == " ":
            out.append("%s")
        elif ch in _ADB_TEXT_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _parse_bounds(bounds):
    """Parses a uiautomator bounds string '[l,t][r,b]' into a center (x, y) point."""
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", bounds or "")
    if not m:
        return None
    left, top, right, bottom = (int(v) for v in m.groups())
    return (left + right) // 2, (top + bottom) // 2


def find_element_center(xml_text, text=None, resource_id=None, partial=True):
    """Finds a UI element by visible text or resource-id in a uiautomator XML dump.

    Returns (found, center_x, center_y, info). Searches `text` against the node's
    text and content-desc; `resource_id` against resource-id (exact or, if partial,
    substring). resource_id takes precedence when both are given.
    """
    if not xml_text:
        return False, 0, 0, "empty UI dump"
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return False, 0, 0, f"XML parse error: {e}"

    want_text = (text or "").strip()
    want_id = (resource_id or "").strip()
    if not want_text and not want_id:
        return False, 0, 0, "no search text/id given"

    for node in root.iter("node"):
        rid = node.get("resource-id", "")
        ntext = node.get("text", "")
        ndesc = node.get("content-desc", "")
        if want_id:
            matched = (rid == want_id) or (partial and bool(rid) and want_id in rid)
        else:
            candidates = [h for h in (ntext, ndesc) if h]
            matched = any(want_text in h for h in candidates) if partial else any(want_text == h for h in candidates)
        if matched:
            center = _parse_bounds(node.get("bounds", ""))
            if center:
                label = rid or ntext or ndesc
                return True, center[0], center[1], f"matched '{label}'"

    return False, 0, 0, f"no element matching '{want_id or want_text}'"


def list_ui_elements(xml_text):
    """Returns labelled/interactable elements from a uiautomator dump (for inspection)."""
    items = []
    if not xml_text:
        return items
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for node in root.iter("node"):
        text = node.get("text", "").strip()
        rid = node.get("resource-id", "").strip()
        desc = node.get("content-desc", "").strip()
        if not (text or rid or desc):
            continue
        items.append({
            "text": text,
            "resource_id": rid,
            "content_desc": desc,
            "clickable": node.get("clickable") == "true",
            "center": _parse_bounds(node.get("bounds", "")),
        })
    return items


class MuMuController:
    def __init__(self, adb_path=None):
        # ลำดับความสำคัญ: ค่าที่ส่งเข้ามา > พาธที่ผู้ใช้เคยบันทึกไว้ (จำข้ามการเปิดโปรแกรม) > ค้นหาอัตโนมัติ
        self.adb_path = adb_path or self.load_saved_adb_path() or self.find_adb()
        self.common_ports = self.load_ports()

    def _config_dir(self):
        """โฟลเดอร์ที่วางไฟล์ตั้งค่า (ข้างตัว .exe ตอน build, ข้างไฟล์ .py ตอน dev)"""
        import sys
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def load_saved_adb_path(self):
        """อ่านพาธ ADB ที่ผู้ใช้เคยบันทึกไว้จาก adb_config.json — คืน None ถ้ายังไม่เคยตั้ง"""
        f = os.path.join(self._config_dir(), "adb_config.json")
        if os.path.exists(f):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                p = (data or {}).get("adb_path")
                if isinstance(p, str) and p.strip():
                    return p.strip()
            except Exception as e:
                print(f"Error loading adb_config.json: {e}")
        return None

    def persist_adb_path(self, path):
        """บันทึกพาธ ADB ลงไฟล์ ให้จำข้ามการเปิด-ปิดโปรแกรม (ลูกค้าไม่ต้องกรอกใหม่ทุกครั้ง)
        คืน (ok, ไฟล์/ข้อความ error)"""
        f = os.path.join(self._config_dir(), "adb_config.json")
        try:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump({"adb_path": path}, fh, ensure_ascii=False, indent=2)
            return True, f
        except Exception as e:
            return False, str(e)

    def find_adb(self):
        """Attempts to find the ADB executable path."""
        # 1. Try system PATH
        try:
            res = subprocess.run(["where", "adb"], capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout.strip().split("\n")[0]
        except Exception:
            pass

        # 2. Try default Android SDK path
        user_home = os.path.expanduser("~")
        sdk_adb = os.path.join(user_home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe")
        if os.path.exists(sdk_adb):
            return sdk_adb

        # 3. Try standard LDPlayer path
        ld_adb = r"C:\LDPlayer\LDPlayer9\adb.exe"
        if os.path.exists(ld_adb):
            return ld_adb

        # Default fall back (assumes it might be on PATH or globally resolved)
        return "adb"

    def run_adb_cmd(self, args, timeout=10):
        """Helper to run a raw ADB command."""
        if not self.adb_path:
            return False, "ADB path not specified"
        
        cmd = [self.adb_path] + args
        try:
            # Running with shell=True on Windows to avoid console popup window flashing
            # and startupinfo to hide CMD window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            res = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                startupinfo=startupinfo,
                timeout=timeout,
                encoding='utf-8', 
                errors='ignore'
            )
            return (res.returncode == 0, res.stdout.strip() if res.returncode == 0 else res.stderr.strip())
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def run_adb_bytes(self, args, timeout=15):
        """Like run_adb_cmd but returns raw bytes (for binary output such as exec-out screencap).

        Returns (success, stdout_bytes) on success, or (False, error_string) on failure.
        """
        if not self.adb_path:
            return False, "ADB path not specified"

        cmd = [self.adb_path] + args
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            # No text/encoding -> stdout stays raw bytes (binary-safe)
            res = subprocess.run(
                cmd,
                capture_output=True,
                startupinfo=startupinfo,
                timeout=timeout,
            )
            if res.returncode == 0:
                return True, res.stdout
            return False, res.stderr.decode("utf-8", errors="ignore").strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def connect_device(self, ip_port):
        """Connects to a specific emulator port."""
        if not ip_port.startswith("127.0.0.1:"):
            if ":" not in ip_port:
                ip_port = f"127.0.0.1:{ip_port}"
        success, output = self.run_adb_cmd(["connect", ip_port])
        return success, output

    def disconnect_device(self, ip_port):
        """Disconnects a specific emulator port."""
        success, output = self.run_adb_cmd(["disconnect", ip_port])
        return success, output

    def get_connected_devices(self):
        """Lists all currently connected devices/emulators."""
        success, output = self.run_adb_cmd(["devices"])
        devices = []
        if success:
            lines = output.split("\n")
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r'\s+', line)
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])
        return devices

    def get_unique_devices(self, connected_devices):
        """Filters out duplicate connections to the same physical emulator."""
        unique_devices = []
        seen_serials = set()
        
        def get_device_serial(device_id):
            # Query device serial number with a low timeout (2 seconds)
            success, serial = self.run_adb_cmd(["-s", device_id, "shell", "getprop", "ro.serialno"], timeout=2)
            if success and serial.strip():
                return device_id, serial.strip()
            # Fallback to MAC address
            success, mac = self.run_adb_cmd(["-s", device_id, "shell", "cat", "/sys/class/net/wlan0/address"], timeout=2)
            if success and mac.strip():
                return device_id, mac.strip()
            return device_id, device_id # Fallback to itself

        if connected_devices:
            with ThreadPoolExecutor(max_workers=max(1, len(connected_devices))) as executor:
                results = list(executor.map(get_device_serial, connected_devices))

            for device_id, serial in results:
                if serial not in seen_serials:
                    seen_serials.add(serial)
                    unique_devices.append(device_id)
                else:
                    # Disconnect duplicate connection to keep ADB clean
                    self.disconnect_device(device_id)
        
        return unique_devices

    def load_ports(self):
        """Loads ports from ports.json if it exists, otherwise returns empty list."""
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        ports_file = os.path.join(base_dir, "ports.json")
        if os.path.exists(ports_file):
            try:
                with open(ports_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        custom_ports = []
                        for p in data:
                            try:
                                custom_ports.append(int(p))
                            except (ValueError, TypeError):
                                continue
                        if custom_ports:
                            return sorted(list(set(custom_ports)))
            except Exception as e:
                print(f"Error loading ports.json: {e}")
        
        return []

    def scan_and_connect_all(self):
        """Scans all common emulator ports and connects to open ones, disconnecting closed ones."""
        import socket
        
        # Reload ports from file or defaults dynamically
        self.common_ports = self.load_ports()

        def is_port_open(port):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    return s.connect_ex(('127.0.0.1', port)) == 0
            except Exception:
                return False

        logs = []
        logs.append("🔍 Starting auto-scan of common emulator ports...")
        
        # We run the connects/disconnects in parallel
        def process_port(port):
            addr = f"127.0.0.1:{port}"
            if is_port_open(port):
                success, out = self.connect_device(addr)
                if success and ("connected" in out.lower() or "already" in out.lower()):
                    return f"✅ Connected to {addr}", True
            else:
                # If port is closed but ADB thinks it is connected, disconnect it to clear ghost connection
                self.disconnect_device(addr)
            return None, False

        with ThreadPoolExecutor(max_workers=max(1, len(self.common_ports))) as executor:
            results = list(executor.map(process_port, self.common_ports))
            
        for log_msg, is_conn in results:
            if log_msg:
                logs.append(log_msg)
                
        connected = self.get_connected_devices()
        unique_connected = self.get_unique_devices(connected)
        logs.append(f"📱 Current active devices: {', '.join(unique_connected) if unique_connected else 'None'}")
        return unique_connected, "\n".join(logs)

    # Individual device shell commands
    def tap(self, device_id, x, y):
        """Taps coordinate (x, y) on the specified device."""
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "tap", str(x), str(y)])

    def swipe(self, device_id, x1, y1, x2, y2, duration=300):
        """Swipes from (x1, y1) to (x2, y2) on the specified device."""
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])

    def input_text(self, device_id, text):
        """Inputs text on the specified device, escaping shell metacharacters.

        See escape_adb_text(): emails/passwords with characters like
        & ( ) < > | ; ' " $ ` would otherwise be mangled by the device shell.
        Note: `input text` is ASCII-only — for Thai/Unicode use input_text_unicode().
        """
        escaped_text = escape_adb_text(text)
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "text", escaped_text])

    # --- Unicode / Thai text input via ADBKeyboard ---
    ADB_KEYBOARD_PKG = "com.android.adbkeyboard"
    ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"

    def current_ime(self, device_id):
        """Returns (success, current_default_input_method_id)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "settings", "get", "secure", "default_input_method"])

    def input_text_unicode(self, device_id, text):
        """Inputs text that may contain Unicode/Thai.

        ASCII text goes through the normal `input text`. Non-ASCII text requires
        ADBKeyboard to be the active IME and is sent as base64 via broadcast.
        Returns (success, message).
        """
        text = str(text)
        if text.isascii():
            return self.input_text(device_id, text)

        ok, ime = self.current_ime(device_id)
        if not ok or "adbkeyboard" not in (ime or "").lower():
            return False, "ต้องเปิดใช้ ADBKeyboard ก่อนถึงจะพิมพ์ภาษาไทย/Unicode ได้ (ปุ่มในแท็บตั้งค่า)"

        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return self.run_adb_cmd(["-s", device_id, "shell", "am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64])

    def is_adb_keyboard_installed(self, device_id):
        ok, out = self.run_adb_cmd(["-s", device_id, "shell", "pm", "list", "packages", self.ADB_KEYBOARD_PKG])
        return bool(ok and self.ADB_KEYBOARD_PKG in (out or ""))

    def install_adb_keyboard(self, device_id, apk_path):
        return self.run_adb_cmd(["-s", device_id, "install", "-r", apk_path], timeout=60)

    def enable_adb_keyboard(self, device_id):
        """Enables and activates ADBKeyboard as the current IME. Returns (success, msg)."""
        self.run_adb_cmd(["-s", device_id, "shell", "ime", "enable", self.ADB_KEYBOARD_IME])
        return self.run_adb_cmd(["-s", device_id, "shell", "ime", "set", self.ADB_KEYBOARD_IME])

    def reset_ime(self, device_id):
        """Restores the device's default keyboard (so manual play works normally again)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "ime", "reset"])

    def keyevent(self, device_id, code):
        """Sends keyevent code (e.g. 4 for Back, 3 for Home)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "keyevent", str(code)])

    def get_resolution(self, device_id):
        """Queries the screen size of the device."""
        success, out = self.run_adb_cmd(["-s", device_id, "shell", "wm", "size"])
        if success:
            match = re.search(r'Physical size:\s*(\d+x\d+)', out)
            if match:
                return match.group(1)
        return "Unknown"

    def get_dpi(self, device_id):
        """Queries the DPI density of the device."""
        success, out = self.run_adb_cmd(["-s", device_id, "shell", "wm", "density"])
        if success:
            match = re.search(r'Physical density:\s*(\d+)', out)
            if match:
                return match.group(1)
        return "Unknown"

    def start_app(self, device_id, package_activity):
        """Starts an application on the specified device (package/activity)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "am", "start", "-n", package_activity])

    def stop_app(self, device_id, package):
        """Stops an application on the specified device (package name)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "am", "force-stop", package])

    def launch_app_by_package(self, device_id, package):
        """เปิดแอปด้วยชื่อ package อย่างเดียว (ไม่ต้องรู้ activity) ผ่าน monkey LAUNCHER
        ใช้กับระบบรีเซ็ตเกม (ปิดแล้วเปิดใหม่) เวลาบัญชีติดปัญหา"""
        return self.run_adb_cmd(
            ["-s", device_id, "shell", "monkey", "-p", package,
             "-c", "android.intent.category.LAUNCHER", "1"])

    # Multi-device action runners (Parallelized)
    def run_parallel_action(self, devices, action_func, *args):
        """Runs action_func(device_id, *args) on all specified devices in parallel."""
        results = {}
        def worker(device_id):
            try:
                success, output = action_func(device_id, *args)
                return device_id, success, output
            except Exception as e:
                return device_id, False, str(e)

        with ThreadPoolExecutor(max_workers=max(1, len(devices))) as executor:
            fut_results = executor.map(worker, devices)

        for device_id, success, output in fut_results:
            results[device_id] = (success, output)
        return results

    def capture_screenshot_bytes(self, device_id):
        """Captures a screenshot straight to memory via `exec-out screencap -p`.

        Faster than take_screenshot(): one command, no on-device temp file, no pull.
        Returns (True, png_bytes) or (False, error_string).
        """
        success, data = self.run_adb_bytes(["-s", device_id, "exec-out", "screencap", "-p"])
        if not success:
            return False, data
        if not data:
            return False, "Empty screenshot output"
        return True, data

    def dump_ui(self, device_id):
        """Dumps the current screen's UI hierarchy as XML via uiautomator.

        Returns (True, xml_str) or (False, error_string). Returns a friendly error
        for game canvases (Unity/Cocos) where uiautomator sees no elements.
        """
        # Write the dump on-device, then read it back (more reliable than /dev/tty)
        self.run_adb_cmd(["-s", device_id, "shell", "uiautomator", "dump", "/sdcard/window_dump.xml"], timeout=15)
        ok, data = self.run_adb_bytes(["-s", device_id, "exec-out", "cat", "/sdcard/window_dump.xml"])
        if not ok:
            return False, data
        xml_text = data.decode("utf-8", errors="ignore") if isinstance(data, (bytes, bytearray)) else str(data)
        if "<hierarchy" not in xml_text and "<node" not in xml_text:
            return False, "ไม่พบ element บนหน้าจอนี้ (อาจเป็นหน้าจอเกมที่ uiautomator อ่านไม่ได้)"
        return True, xml_text

    def take_screenshot(self, device_id, local_path):
        """Saves a screenshot to local_path. Prefers in-memory exec-out, falls back to screencap+pull.

        Kept for callers that need a file on disk (e.g. user-requested screenshot step).
        """
        # Fast path: exec-out straight to file (no on-device temp file)
        success, data = self.capture_screenshot_bytes(device_id)
        if success:
            try:
                with open(local_path, "wb") as f:
                    f.write(data)
                return True, local_path
            except Exception as e:
                return False, f"Failed to write screenshot file: {e}"

        # Fallback: legacy screencap -> pull -> rm (for emulators without exec-out)
        safe_id = device_id.replace(":", "_").replace(".", "_")
        remote_path = f"/data/local/tmp/screen_{safe_id}.png"
        ok, out = self.run_adb_cmd(["-s", device_id, "shell", "screencap", "-p", remote_path])
        if not ok:
            return False, f"Failed to take screenshot: {out}"
        ok, out = self.run_adb_cmd(["-s", device_id, "pull", remote_path, local_path])
        self.run_adb_cmd(["-s", device_id, "shell", "rm", remote_path])
        return ok, out

    def _match_template(self, screen, template, threshold):
        """Core OpenCV matchTemplate on already-loaded images. Returns (found, x, y, msg)."""
        if screen is None or template is None:
            return False, 0, 0, "Failed to load screenshot or template image"
        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val >= threshold:
            h, w, _ = template.shape
            click_x = int(max_loc[0] + w / 2)
            click_y = int(max_loc[1] + h / 2)
            return True, click_x, click_y, f"Match found (confidence: {max_val:.2f})"
        return False, 0, 0, f"No match found (best confidence: {max_val:.2f})"

    def find_image_in_bytes(self, screen_bytes, template_path, threshold=0.8):
        """Finds template_path within a screenshot held in memory (PNG bytes)."""
        try:
            if not os.path.exists(template_path):
                return False, 0, 0, "Template image file not found"
            if not screen_bytes:
                return False, 0, 0, "Empty screenshot data"
            screen = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
            template = cv2.imread(template_path)
            return self._match_template(screen, template, threshold)
        except Exception as e:
            return False, 0, 0, str(e)

    def match_template_bytes(self, screen_bytes, template_bytes, threshold=0.8):
        """เทียบ 'ภาพ anchor' (PNG bytes) กับสกรีนช็อต (PNG bytes) — ทั้งคู่อยู่ในหน่วยความจำ
        ใช้กับระบบ anchor ที่เก็บภาพเป็น base64 ในสเต็ป (ไม่ต้องเขียนไฟล์)
        คืน (found, cx, cy, msg) — cx,cy = จุดกึ่งกลางที่ match เจอ (ไว้ relocate ถ้าต้องการ)"""
        try:
            if not screen_bytes or not template_bytes:
                return False, 0, 0, "Empty screenshot or template"
            screen = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
            template = cv2.imdecode(np.frombuffer(template_bytes, np.uint8), cv2.IMREAD_COLOR)
            return self._match_template(screen, template, threshold)
        except Exception as e:
            return False, 0, 0, str(e)

    def find_image_on_screen(self, screen_path, template_path, threshold=0.8):
        """Finds template_path image on a screenshot file using OpenCV matchTemplate."""
        try:
            if not os.path.exists(screen_path):
                return False, 0, 0, "Screenshot file not found"
            if not os.path.exists(template_path):
                return False, 0, 0, "Template image file not found"
            screen = cv2.imread(screen_path)
            template = cv2.imread(template_path)
            return self._match_template(screen, template, threshold)
        except Exception as e:
            return False, 0, 0, str(e)

    def read_number_in_region(self, screen_bytes, region, digits_dir, threshold=0.6):
        """Reads an integer from a fixed screen region using per-digit template matching.

        region: dict with x, y, w, h (pixels in the original screenshot resolution).
        digits_dir: folder holding digit templates 0.png .. 9.png (crops of the game font).
                    Only the digit templates that exist are matched.
        Returns (ok: bool, number: int|None, raw_str: str). raw_str is "" when nothing matched
        (or the exception text on error, for logging).

        Why template matching: the game renders the currency count in a fixed font at a fixed
        resolution, so each glyph is pixel-stable. Cropping to a tight region first is what keeps
        the many other on-screen numbers (gold, level, score) out of the read.

        Matching is done on GRAYSCALE so that the same white digit reads regardless of the colored
        bar behind it (the diamond bar is blue, the gold/score bars are other colors) — a color
        match would score the background differences and miss.
        """
        try:
            if not screen_bytes:
                return False, None, ""
            screen = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
            if screen is None:
                return False, None, ""

            # ครอปเฉพาะพื้นที่ตัวเลข (clamp ไม่ให้เกินขอบภาพ) แล้วแปลงเป็นเทา
            sh, sw = screen.shape[:2]
            x = max(0, int(region.get("x", 0)))
            y = max(0, int(region.get("y", 0)))
            w = int(region.get("w", 0))
            h = int(region.get("h", 0))
            if w <= 0 or h <= 0:
                return False, None, ""
            crop = screen[y:min(sh, y + h), x:min(sw, x + w)]
            if crop.size == 0:
                return False, None, ""
            crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            # จับคู่ทุกตัวเลข (0-9) ในพื้นที่ครอป เก็บทุกตำแหน่งที่คะแนนถึงเกณฑ์
            dets = []  # (px, digit, score, tpl_w)
            for d in range(10):
                tpl_path = os.path.join(digits_dir, f"{d}.png")
                if not os.path.exists(tpl_path):
                    continue
                tpl = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
                if tpl is None:
                    continue
                th, tw = tpl.shape[:2]
                if crop.shape[0] < th or crop.shape[1] < tw:
                    continue  # template ใหญ่กว่าพื้นที่ครอป ข้าม
                res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(res >= threshold)
                for px, py in zip(xs, ys):
                    dets.append((int(px), d, float(res[py, px]), int(tw)))

            if not dets:
                return False, None, ""

            # Non-max suppression ตามแกน x: เรียงคะแนนมาก->น้อย เก็บเฉพาะตัวที่ไม่ทับกับที่เก็บไว้
            # (กันการอ่านเลขตัวเดียวซ้ำ หรือเลขคนละตัวทับตำแหน่งเดียวกัน)
            dets.sort(key=lambda t: -t[2])
            kept = []
            for px, d, score, tw in dets:
                if all(abs(px - kpx) > tw * 0.5 for kpx, _, _, _ in kept):
                    kept.append((px, d, score, tw))

            # เรียงตามตำแหน่งซ้าย->ขวา แล้วต่อกันเป็นเลขจำนวนเต็ม
            kept.sort(key=lambda t: t[0])
            raw = "".join(str(d) for _, d, _, _ in kept)
            if not raw:
                return False, None, ""
            return True, int(raw), raw
        except Exception as e:
            return False, None, str(e)

    def read_number_tesseract(self, screen_bytes, region, scale=6, psm=7, sat_thresh=120):
        """อ่านเลขจากพื้นที่ที่กำหนดด้วย Tesseract OCR (เรียก tesseract.exe ตรง — ไม่พึ่ง pytesseract/PIL)

        region: dict {x,y,w,h} พิกัดในภาพต้นฉบับ — ควรครอบ 'เฉพาะตัวเลข' ไม่เอาไอคอน
        คืน (ok, number:int|None, raw:str). raw='no_tesseract' เมื่อไม่พบ tesseract.exe, '' เมื่ออ่านไม่ได้

        วิธี: ครอปพื้นที่ -> เทา -> ขยายภาพ (เลขในจอเล็ก ~7px ต้องขยายให้อ่านได้) -> เว้นขอบขาว ->
        เซฟ PNG ชั่วคราว -> ส่งให้ tesseract.exe อ่านแบบบรรทัดเดียว เฉพาะเลข 0-9 (ซ่อนหน้าต่าง cmd)
        """
        cmd = find_tesseract()
        if not cmd:
            return False, None, "no_tesseract"
        tmp = None
        try:
            if not screen_bytes:
                return False, None, ""
            screen = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
            if screen is None:
                return False, None, ""
            sh, sw = screen.shape[:2]
            x = max(0, int(region.get("x", 0)))
            y = max(0, int(region.get("y", 0)))
            w = int(region.get("w", 0))
            h = int(region.get("h", 0))
            if w <= 0 or h <= 0:
                return False, None, ""
            crop = screen[y:min(sh, y + h), x:min(sw, x + w)]
            if crop.size == 0:
                return False, None, ""
            g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            # ลบพิกเซลสีอิ่มสูง (ปุ่ม "+" สีฟ้า / ไอคอนเพชร) ออกเป็นขาว เพื่อไม่ให้ OCR อ่าน
            # ขอบปุ่ม "+" เป็นเลข "1" ต่อท้าย — ตัวเลขเพชรสีจาง (อิ่มสีต่ำ) จึงไม่ถูกลบ
            if sat_thresh and sat_thresh > 0:
                sat = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 1]
                g[sat > sat_thresh] = 255
            g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            g = cv2.copyMakeBorder(g, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)

            fd, tmp = tempfile.mkstemp(suffix=".png", prefix="diamond_ocr_")
            os.close(fd)
            cv2.imwrite(tmp, g)

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            res = subprocess.run(
                [cmd, tmp, "stdout", "--psm", str(psm), "-c", "tessedit_char_whitelist=0123456789"],
                capture_output=True, startupinfo=startupinfo, timeout=20,
            )
            txt = res.stdout.decode("utf-8", errors="ignore")
            digits = "".join(c for c in txt if c.isdigit())
            if not digits:
                return False, None, ""
            return True, int(digits), digits
        except Exception as e:
            return False, None, str(e)
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except Exception:
                    pass


# ===== Story Auto: OCR fallback (หาปุ่มจากข้อความ) =====
STORY_BUTTON_KEYWORDS = {
    # ไทย
    "ข้าม", "ตกลง", "ปิด", "รับ", "ไปต่อ", "ดำเนินการต่อ", "เริ่ม", "ถัดไป",
    "รับรางวัล", "รับของรางวัล", "ยืนยัน", "เล่นอีกครั้ง", "กลับ", "ลงทะเบียน",
    "เล่น", "เข้าสู่ระบบ", "เสร็จสิ้น", "สำเร็จ",
    # English
    "skip", "ok", "next", "close", "claim", "continue", "accept",
    "confirm", "start", "back", "done", "retry", "tap", "play",
    "finish", "complete", "proceed", "advance",
}


def ocr_find_button(screen_bytes, keywords=None, lang=None, scale=2):
    """OCR ทั้งจอ -> หาตำแหน่ง (cx,cy) ของคำที่น่าจะเป็นปุ่ม
    คืน (found, cx, cy, matched_word) โดยใช้ tesseract TSV output เพื่อได้ bounding box"""
    if keywords is None:
        keywords = STORY_BUTTON_KEYWORDS
    cmd = find_tesseract()
    if not cmd:
        return False, 0, 0, ""
    tmp = None
    try:
        if not screen_bytes:
            return False, 0, 0, ""
        img = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return False, 0, 0, ""
        orig_h, orig_w = img.shape[:2]

        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        actual_scale = scale if scale and scale != 1 else 1
        if actual_scale != 1:
            g = cv2.resize(g, None, fx=actual_scale, fy=actual_scale, interpolation=cv2.INTER_CUBIC)

        fd, tmp = tempfile.mkstemp(suffix=".png", prefix="story_ocr_")
        os.close(fd)
        cv2.imwrite(tmp, g)

        if lang is None:
            langs = available_tesseract_langs()
            lang = "tha+eng" if "tha" in langs else "eng"

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        res = subprocess.run(
            [cmd, *_tessdata_args(), tmp, "stdout", "-l", lang, "--psm", "11", "tsv"],
            capture_output=True, startupinfo=si, timeout=30,
        )
        tsv = res.stdout.decode("utf-8", errors="ignore")

        # parse TSV: level page_num block_num par_num line_num word_num left top width height conf text
        for line in tsv.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) < 12:
                continue
            try:
                conf = float(parts[10])
                word = parts[11].strip()
            except (ValueError, IndexError):
                continue
            if conf < 30 or not word:
                continue
            if word.lower() in keywords or word in keywords:
                left = int(parts[6])
                top = int(parts[7])
                w = int(parts[8])
                h = int(parts[9])
                # แปลงกลับเป็นพิกัดต้นฉบับ
                cx = int((left + w / 2) / actual_scale)
                cy = int((top + h / 2) / actual_scale)
                # clamp ให้อยู่ในจอ
                cx = max(0, min(orig_w - 1, cx))
                cy = max(0, min(orig_h - 1, cy))
                return True, cx, cy, word
        return False, 0, 0, ""
    except Exception:
        return False, 0, 0, ""
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except Exception:
                pass


# ===== Story Auto: Gemini Vision fallback =====
# รายชื่อโมเดลที่จะลองเรียง (ใหม่สุดก่อน) เผื่อบาง key/บาง region ไม่รองรับบางรุ่น
_GEMINI_MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
]
_GEMINI_WORKING_MODEL = None  # แคชโมเดลที่ใช้ได้จริงกับ key นี้ (ต่อโปรเซส)

# กัน rate-limit (429): เว้นช่วงขั้นต่ำระหว่างการเรียกแต่ละครั้ง + cooldown ยาวขึ้นถ้าโดน 429
_GEMINI_MIN_INTERVAL = 4.0
_GEMINI_LAST_CALL_TS = 0.0
_GEMINI_COOLDOWN_UNTIL = 0.0


def _extract_json_object(text):
    """ดึงก้อน JSON object ตัวแรกจากข้อความ (เผื่อ Gemini พ่นข้อความอื่นแถมมาหรือมี code fence)
    คืน dict หรือ None ถ้า parse ไม่ได้"""
    if not text:
        return None
    cleaned = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text.strip())
    m = re.search(r"\{.*\}", cleaned, re.S)
    candidate = m.group(0) if m else cleaned
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _gemini_call(prompt_text, screen_bytes, api_key, timeout=15):
    """เรียก Gemini Vision REST API ตรงๆ — ลองโมเดลใน _GEMINI_MODEL_CANDIDATES จนกว่าจะเจอตัวที่ใช้ได้
    (แคชผลไว้ใน _GEMINI_WORKING_MODEL กันเรียกซ้ำทุกครั้ง) มี throttle กัน 429 คืน (ok, text_or_error)"""
    global _GEMINI_WORKING_MODEL, _GEMINI_LAST_CALL_TS, _GEMINI_COOLDOWN_UNTIL
    import urllib.request, urllib.error

    now = time.time()
    if now < _GEMINI_COOLDOWN_UNTIL:
        return False, f"rate_limited (cooldown อีก {_GEMINI_COOLDOWN_UNTIL - now:.0f} วิ)"
    if now - _GEMINI_LAST_CALL_TS < _GEMINI_MIN_INTERVAL:
        return False, "rate_limited (throttle)"
    _GEMINI_LAST_CALL_TS = now

    b64 = base64.b64encode(screen_bytes).decode()

    models_to_try = [_GEMINI_WORKING_MODEL] if _GEMINI_WORKING_MODEL else list(_GEMINI_MODEL_CANDIDATES)
    last_err = ""
    for model in models_to_try:
        if not model:
            continue
        gen_config = {"temperature": 0, "maxOutputTokens": 300}
        if "2.5" in model:
            # thinkingBudget=0 ปิด thinking mode ของ gemini-2.5-* กันโดนกินโควต้า token ไปกับ
            # การคิดภายใน จนเหลือ token ไม่พอสำหรับ JSON คำตอบจริง (เจอปัญหา "ตัดกลางคัน" บ่อย)
            # รุ่นเก่า (1.5/2.0) ไม่รองรับฟิลด์นี้ เลยใส่แค่ตอนเรียกรุ่น 2.5 เท่านั้น
            gen_config["thinkingConfig"] = {"thinkingBudget": 0}
        payload = json.dumps({
            "contents": [{
                "parts": [
                    {"text": prompt_text},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ]
            }],
            "generationConfig": gen_config,
        }).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            _GEMINI_WORKING_MODEL = model  # เจอตัวที่ใช้ได้แล้ว จำไว้ใช้ต่อ
            return True, text
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.reason} ({model})"
            if e.code == 404:
                continue  # โมเดลนี้ไม่มี/ถูกเลิกใช้ -> ลองตัวถัดไป
            if e.code == 429:
                _GEMINI_COOLDOWN_UNTIL = time.time() + 30.0  # โดน quota -> พักยาวกันยิงรัว
            break  # error อื่น (เช่น 400/403 key ผิด/429) ไม่มีประโยชน์ที่จะลองโมเดลอื่น
        except Exception as e:
            last_err = str(e)
            break
    return False, last_err


def _gemini_parse_normalized_point(obj, screen_w, screen_h):
    """Gemini คืนพิกัดบนสเกล normalize 0-1000 เสมอ (ธรรมเนียมภายในของ Google เอง)
    ไม่ว่าใน prompt จะบอกขนาดจอเป็น pixel เท่าไหร่ก็ตาม — แปลงกลับเป็น pixel จริงตรงนี้ที่เดียว"""
    x = obj.get("x")
    y = obj.get("y")
    if x is None:
        return None, None
    x = int(round(int(x) / 1000.0 * screen_w))
    y = int(round(int(y) / 1000.0 * screen_h))
    x = max(0, min(screen_w - 1, x))
    y = max(0, min(screen_h - 1, y))
    return x, y


_GEMINI_TAP_NO_TARGET_UNTIL = 0.0  # หลัง Gemini ยืนยันว่า "ไม่มีปุ่ม/แมตช์เล่นเอง" -> พักไม่ถามซ้ำสักพัก


def gemini_tap_suggestion(screen_bytes, api_key, screen_w=960, screen_h=540):
    """ถาม Gemini Vision ว่าควร tap พิกัดไหนเพื่อเดินเรื่อง story ต่อ
    คืน (found, cx, cy, reason)  — ใช้ REST API โดยตรง (ไม่ต้อง install package)

    มี backoff: ถ้า Gemini เพิ่งยืนยันว่า 'ไม่มีปุ่ม/แมตช์กำลัง auto-play' จะไม่ถามซ้ำ
    ไปอีก ~15 วิ (ระหว่างนั้น template+OCR ที่ฟรีอยู่แล้วยังคอยเช็คทุกรอบตามปกติ ถ้าเจอ
    ปุ่มจะกดได้ทันทีไม่ต้องรอ Gemini) — กันยิง Gemini รัวๆ ทั้งที่คำตอบซ้ำเดิมตลอดช่วงแมตช์เล่นเอง"""
    global _GEMINI_TAP_NO_TARGET_UNTIL
    try:
        if not api_key or not screen_bytes:
            return False, 0, 0, "no_key"
        now = time.time()
        if now < _GEMINI_TAP_NO_TARGET_UNTIL:
            return False, 0, 0, f"auto-play ยืนยันแล้ว รออีก {_GEMINI_TAP_NO_TARGET_UNTIL - now:.0f} วิ"
        prompt = (
            "This is a screenshot from a mobile RPG game story mode. "
            "Identify the UI element I should tap to advance the story/cutscene. "
            "Look for: Skip button, Next button, OK/Close button, Claim reward button, "
            "or any interactive button/icon that progresses the narrative. "
            "If the match/battle is auto-playing (no button visible), reply with x=null. "
            "Return the tap point as x,y normalized to a 0-1000 scale (0,0 = top-left corner, "
            "1000,1000 = bottom-right corner of the image), NOT raw pixel coordinates. "
            "Reply with ONLY one line of compact JSON, no markdown, no extra text before or after. "
            'The reason field must be under 6 words with no quote characters inside it. '
            'Format: {"x": <int 0-1000|null>, "y": <int 0-1000>, "reason": "<short description>"}'
        )
        ok, text = _gemini_call(prompt, screen_bytes, api_key)
        if not ok:
            return False, 0, 0, text
        obj = _extract_json_object(text)
        if obj is None:
            return False, 0, 0, f"bad_json: {text[:80]}"
        reason = obj.get("reason", "")
        cx, cy = _gemini_parse_normalized_point(obj, screen_w, screen_h)
        if cx is None:
            _GEMINI_TAP_NO_TARGET_UNTIL = time.time() + 15.0
            return False, 0, 0, reason
        return True, cx, cy, reason
    except Exception as e:
        return False, 0, 0, str(e)


def gemini_find_stage(screen_bytes, api_key, screen_w=960, screen_h=540):
    """ถาม Gemini Vision ว่า 'ด่านไหนบนหน้าเลือกด่าน (map) ที่ถูกไฮไลท์เป็นด่านถัดไปที่เล่นได้'
    ใช้เมื่อ find_yellow_frame แยกไม่ออก (กรอบไฮไลท์ vs สีส้ม/เหลืองในภาพประกอบเอง)
    ขอพิกัดแบบ normalize 0-1000 แล้วแปลงกลับเป็น pixel เอง (ดู _gemini_parse_normalized_point) —
    แก้ปัญหาที่ Gemini เคยตอบพิกัดผิดสเกล (เช่น y เกินความสูงจอไปเยอะ)
    คืน (found, cx, cy, reason)"""
    try:
        if not api_key or not screen_bytes:
            return False, 0, 0, "no_key"
        prompt = (
            "This is a stage-select map screenshot from a mobile RPG game. "
            "Multiple stage thumbnails are shown, each with a number label. "
            "Exactly one stage is usually marked as the next playable stage — look for a "
            "glowing/highlighted GOLD OR YELLOW BORDER OUTLINE around its thumbnail frame, "
            "or a gold/yellow-filled number label badge (as opposed to a plain black/dark label). "
            "Do NOT be fooled by stages whose artwork itself happens to contain warm orange/yellow "
            "colors (like sunset or indoor lighting in the picture) — only the actual UI highlight "
            "border/badge overlay counts, not the artwork's own colors. "
            "Locked stages (with a padlock icon) are never the target. "
            "Return the tap point (center of the correct highlighted stage thumbnail) as x,y "
            "normalized to a 0-1000 scale (0,0 = top-left corner, 1000,1000 = bottom-right corner "
            "of the image), NOT raw pixel coordinates. "
            "If no stage appears highlighted, reply with x=null. "
            "Reply with ONLY one line of compact JSON, no markdown, no extra text before or after. "
            'The reason field must be under 6 words with no quote characters inside it. '
            'Format: {"x": <int 0-1000|null>, "y": <int 0-1000>, "reason": "<short description>"}'
        )
        ok, text = _gemini_call(prompt, screen_bytes, api_key)
        if not ok:
            return False, 0, 0, text
        obj = _extract_json_object(text)
        if obj is None:
            return False, 0, 0, f"bad_json: {text[:80]}"
        reason = obj.get("reason", "")
        cx, cy = _gemini_parse_normalized_point(obj, screen_w, screen_h)
        if cx is None:
            return False, 0, 0, reason
        return True, cx, cy, reason
    except Exception as e:
        return False, 0, 0, str(e)
