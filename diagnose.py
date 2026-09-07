"""ตรวจว่าเครื่องนี้เซ็ตครบพร้อมใช้งานหรือยัง (ใช้คู่กับ README.md ขั้นที่ 7)

จุดสำคัญ: "กดจอได้" ไม่ได้แปลว่า "เช็ครูปได้"

    ขั้นแตะ    ใช้แค่  adb shell input tap x y
    ขั้นเช็ครูป ต้องผ่าน 3 ชั้น:
        [1] ถ่ายภาพจากจอ   adb exec-out screencap -p   -> PNG bytes
        [2] แปลงเป็นรูป     cv2.imdecode                -> numpy array
        [3] เทียบรูป        cv2.matchTemplate           -> คะแนน 0..1 (ผ่านที่ 0.8)

ชั้น 1-3 พังได้โดยที่ขั้นแตะยังทำงานปกติ ตัวนี้เลยตรวจแยกให้ทีละชั้น

วิธีใช้:
    python diagnose.py              # ตรวจเต็ม (ต่อจอจริง + ถ่ายภาพจริง)
    python diagnose.py --offline    # ตรวจเฉพาะไลบรารีกับไฟล์ ไม่แตะจอ
    python diagnose.py --device 127.0.0.1:16384   # ระบุจอเอง

ไม่แก้ไขไฟล์อะไรทั้งนั้น อ่านอย่างเดียว รันซ้ำกี่รอบก็ได้
"""
import argparse
import base64
import glob
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
FINDINGS = []          # (ระดับ, หัวข้อ, วิธีแก้)


def hr(title):
    print("\n" + "=" * 66)
    print("  " + title)
    print("=" * 66)


def ok(msg):
    print("  [ ผ่าน ] " + msg)


def bad(msg, fix=""):
    print("  [ ตก  ] " + msg)
    FINDINGS.append(("ตก", msg, fix))


def warn(msg, fix=""):
    print("  [ เตือน] " + msg)
    FINDINGS.append(("เตือน", msg, fix))


def info(msg):
    print("          " + msg)


# ---------------------------------------------------------------- 1. ไลบรารี
def check_libs():
    hr("1. ไลบรารีที่ระบบภาพต้องใช้")
    mods = {}
    for name, pip in (("cv2", "opencv-python"), ("numpy", "numpy")):
        try:
            m = __import__(name)
            mods[name] = m
            ok(f"{name} {getattr(m, '__version__', '?')}")
        except Exception as e:
            mods[name] = None
            bad(f"import {name} ไม่ได้: {e}",
                f"รัน:  pip install {pip}\n"
                "ถ้าขึ้น DLL load failed ให้ลง Microsoft Visual C++ Redistributable (x64) ก่อน\n"
                "https://aka.ms/vs/17/release/vc_redist.x64.exe")
    if mods.get("cv2") is None:
        info("*** ถ้าเป็นการรันจากไฟล์ .exe แล้วบรรทัดนี้ตก แปลว่า exe พัง ให้ build ใหม่ ***")
    return mods.get("cv2"), mods.get("numpy")


# ------------------------------------------------------------------- 2. ADB
def check_adb():
    hr("2. ADB (ตัวคุยกับจอ)")
    adb = None
    cfg = os.path.join(BASE, "adb_config.json")
    if os.path.exists(cfg):
        try:
            adb = (json.load(open(cfg, encoding="utf-8")) or {}).get("adb_path")
            if adb:
                info(f"adb_config.json ชี้ไปที่: {adb}")
        except Exception as e:
            warn(f"อ่าน adb_config.json ไม่ได้: {e}")
    if not adb or not os.path.exists(adb):
        try:
            r = subprocess.run(["where", "adb"], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                adb = r.stdout.strip().splitlines()[0]
                info(f"เจอ adb ใน PATH: {adb}")
        except Exception:
            pass
    if not adb:
        for cand in (os.path.join(os.path.expanduser("~"), "AppData", "Local", "Android",
                                  "Sdk", "platform-tools", "adb.exe"),
                     r"C:\LDPlayer\LDPlayer9\adb.exe"):
            if os.path.exists(cand):
                adb = cand
                info(f"เจอ adb ที่: {adb}")
                break
    if not adb:
        bad("หา adb.exe ไม่เจอเลย",
            "เปิดโปรแกรม > ตั้งค่า > 'ที่อยู่ไฟล์ ADB.exe' แล้วชี้ไปที่ adb.exe ของ MuMu\n"
            r"ปกติอยู่ที่  C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe")
        return None

    try:
        r = subprocess.run([adb, "version"], capture_output=True, text=True, timeout=15)
        ver = (r.stdout or "").strip().splitlines()[0] if r.stdout else "?"
        ok(f"{ver}")
        num = "".join(ch for ch in ver if ch.isdigit() or ch == ".")
        if "1.0." in ver:
            try:
                minor = int(ver.split("1.0.")[1].split()[0].split(".")[0])
                if minor < 32:
                    bad(f"adb เก่าเกินไป (1.0.{minor}) — คำสั่ง exec-out ที่ใช้ถ่ายภาพเพิ่งมีใน 1.0.32",
                        "ใช้ adb.exe ของ MuMu รุ่นใหม่ หรือโหลด platform-tools ล่าสุดจาก\n"
                        "https://developer.android.com/tools/releases/platform-tools")
            except (ValueError, IndexError):
                pass
    except Exception as e:
        bad(f"สั่ง adb version ไม่ได้: {e}")
        return None
    return adb


def list_devices(adb):
    hr("3. จอที่ต่ออยู่")
    try:
        r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=20)
        lines = [l.strip() for l in (r.stdout or "").splitlines()[1:] if l.strip()]
        devs = [l.split()[0] for l in lines if l.endswith("device")]
        for l in lines:
            print("          " + l)
        if not devs:
            bad("ไม่มีจอที่ต่ออยู่",
                "เปิด MuMu ให้เข้าหน้าโฮมก่อน แล้วกด 'สแกนพอร์ต' ในโปรแกรม")
        else:
            ok(f"ต่ออยู่ {len(devs)} จอ")
        return devs
    except Exception as e:
        bad(f"สั่ง adb devices ไม่ได้: {e}")
        return []


# ------------------------------------------------- 4. ถ่ายภาพ (ชั้นที่พังบ่อยสุด)
def check_screencap(adb, dev, cv2, np):
    hr(f"4. ถ่ายภาพจากจอ {dev}  <-- ชั้นที่พังบ่อยที่สุด")
    import time
    t0 = time.time()
    try:
        r = subprocess.run([adb, "-s", dev, "exec-out", "screencap", "-p"],
                           capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        bad(f"[{dev}] ถ่ายภาพค้างเกิน 30 วิ",
            "จอช้าเกินไป มักเกิดตอนยังไม่ได้เปิด VT (Virtualization) ใน BIOS\n"
            "เช็คใน Task Manager > Performance > CPU > Virtualization ต้องเป็น Enabled\n"
            "ถ้า Disabled ให้เข้า BIOS เปิด Intel VT-x / AMD-V")
        return None
    except Exception as e:
        bad(f"[{dev}] สั่งถ่ายภาพไม่ได้: {e}")
        return None
    dt = time.time() - t0
    data = r.stdout or b""

    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "ignore").strip()
        bad(f"[{dev}] adb คืน error: {err or 'ไม่ระบุ'}",
            "ถ้าขึ้น 'unknown command exec-out' = adb เก่าเกินไป ให้เปลี่ยน adb.exe")
        return None
    if not data:
        bad(f"[{dev}] ถ่ายภาพได้ 0 ไบต์ (ว่างเปล่า)",
            "MuMu บางรุ่นบล็อก screencap ตอนใช้โหมดกราฟิกบางแบบ\n"
            "ลองเข้า MuMu > ตั้งค่า > จอภาพ แล้วสลับ renderer เป็น DirectX หรือ OpenGL แล้วรีสตาร์ทจอ")
        return None
    ok(f"ได้ภาพ {len(data):,} ไบต์ ใช้เวลา {dt:.1f} วิ")
    if dt > 8:
        warn(f"ถ่ายภาพช้ามาก ({dt:.1f} วิ) — ตอนรันจริงอาจ timeout",
             "เปิด VT ใน BIOS และเพิ่ม CPU/RAM ให้ MuMu")
    if not data[:8].startswith(b"\x89PNG"):
        bad(f"[{dev}] ข้อมูลที่ได้ไม่ใช่ไฟล์ PNG (ขึ้นต้นด้วย {data[:8]!r})",
            "มักเกิดจาก adb แปลง \\n เป็น \\r\\n ทำให้ PNG เสีย — ให้เปลี่ยนไปใช้ adb.exe ของ MuMu เอง")
        return None

    if cv2 is None or np is None:
        warn("ข้ามการตรวจ decode เพราะไม่มี cv2/numpy")
        return None
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        bad(f"[{dev}] cv2 แปลง PNG เป็นรูปไม่ได้ (ไฟล์เสีย)")
        return None
    h, w = img.shape[:2]
    ok(f"แปลงเป็นรูปได้: {w} x {h} พิกเซล")

    std = float(img.std())
    if std < 3.0:
        bad(f"[{dev}] ภาพที่ได้เป็นสีเดียวล้วน (ความต่างสี {std:.1f}) — น่าจะเป็นจอดำ",
            "*** นี่คือสาเหตุที่ 'เช็ครูปไม่เจอ' ทั้งที่กดจอได้ ***\n"
            "ADB ถ่ายภาพได้แต่ได้จอดำ เพราะ MuMu เรนเดอร์ผ่าน GPU overlay\n"
            "แก้: MuMu > ตั้งค่า > จอภาพ > โหมดการเรนเดอร์ ลองสลับเป็น DirectX / OpenGL / Vulkan\n"
            "     แล้วรีสตาร์ทจอ ทดสอบใหม่ทีละแบบจนกว่าภาพจะไม่ดำ")
    else:
        ok(f"ภาพมีรายละเอียดจริง (ความต่างสี {std:.1f}) ไม่ใช่จอดำ")
    return img


# ------------------------------------------------------- 5. เทียบภาพด้วย OpenCV
def check_matching(cv2, np, img, dev):
    hr(f"5. การเทียบภาพ (matchTemplate) — จอ {dev}")
    if img is None:
        warn("ข้าม เพราะยังไม่มีภาพจากขั้นที่ 4")
        return
    h, w = img.shape[:2]
    # ตัดชิ้นส่วนจากภาพตัวเอง แล้วเอาไปหาในภาพเดิม -> ต้องเจอคะแนนเกือบ 1.00 เสมอ
    ch, cw = min(80, h // 4), min(160, w // 4)
    y0, x0 = h // 2, w // 3
    crop = img[y0:y0 + ch, x0:x0 + cw]
    try:
        res = cv2.matchTemplate(img, crop, cv2.TM_CCOEFF_NORMED)
        score = float(cv2.minMaxLoc(res)[1])
    except Exception as e:
        bad(f"matchTemplate พังทันที: {e}",
            "OpenCV ติดตั้งไม่สมบูรณ์ — ลง Visual C++ Redistributable x64 แล้ว pip install --force-reinstall opencv-python")
        return
    if score > 0.95:
        ok(f"เทียบภาพทำงานถูกต้อง (คะแนน {score:.3f} จากเต็ม 1.000)")
    else:
        bad(f"เทียบภาพผิดปกติ ได้คะแนนแค่ {score:.3f} ทั้งที่ควรได้ ~1.000",
            "OpenCV ทำงานเพี้ยน ให้ pip install --force-reinstall opencv-python")


# ------------------------- 6. ภาพในสคริปต์จริง เทียบกับขนาดจอปัจจุบัน
def collect_script_images():
    """ดึงภาพ base64 ทั้งหมดที่ฝังอยู่ในสคริปต์ออกมา"""
    out = []
    for path in glob.glob(os.path.join(BASE, "macros", "*.json")) + \
                glob.glob(os.path.join(BASE, "script_sets", "*.json")):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        steps = d.get("steps", d) if isinstance(d, dict) else d
        if not isinstance(steps, list):
            continue

        def walk(lst):
            for s in lst:
                if not isinstance(s, dict):
                    continue
                for key in ("anchor_img", "wait_img", "find_img"):
                    if s.get(key):
                        out.append((os.path.basename(path), s.get("desc") or s.get("type"), key, s[key]))
                for br in ("then", "else"):
                    if isinstance(s.get(br), list):
                        walk(s[br])
        walk(steps)
    return out


def check_script_images(cv2, np, img):
    hr("6. ภาพที่ฝังอยู่ในสคริปต์ เทียบกับขนาดจอตอนนี้")
    imgs = collect_script_images()
    if not imgs:
        warn("ไม่พบภาพฝังในสคริปต์เลย (macros/ กับ script_sets/ ว่างหรือหายไป?)",
             "ก็อปโฟลเดอร์ macros/ และ script_sets/ มาจากเครื่องเดิมให้ครบ")
        return
    ok(f"เจอภาพฝังในสคริปต์ {len(imgs)} รูป")
    if cv2 is None or np is None:
        return

    bad_decode, sizes, too_big = 0, [], []
    sh, sw = (img.shape[:2] if img is not None else (0, 0))
    for fname, desc, key, b64 in imgs:
        try:
            raw = base64.b64decode(b64)
            t = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            t = None
        if t is None:
            bad_decode += 1
            continue
        th, tw = t.shape[:2]
        sizes.append((tw, th))
        if sh and (th > sh or tw > sw):
            too_big.append((fname, desc, tw, th))

    if bad_decode:
        bad(f"{bad_decode} รูปแปลงไม่ได้ (ข้อมูลในสคริปต์เสีย)",
            "ก็อปไฟล์ใน macros/ และ script_sets/ มาจากเครื่องเดิมใหม่")
    else:
        ok("ทุกรูปแปลงเป็นภาพได้ปกติ")

    if sh:
        info(f"ขนาดจอตอนนี้: {sw} x {sh}")
        if sizes:
            mw = max(w for w, _ in sizes)
            mh = max(h for _, h in sizes)
            info(f"รูปในสคริปต์ใหญ่สุด: {mw} x {mh}")
        if too_big:
            bad(f"{len(too_big)} รูป ใหญ่กว่าจอปัจจุบัน -> เทียบไม่ได้เลย (OpenCV หาไม่ได้ถ้ารูปใหญ่กว่าจอ)",
                "*** นี่คือสาเหตุที่ 'เช็ครูปไม่เจอ' ทั้งที่กดจอได้ ***\n"
                "รูปพวกนี้ถูกจับมาตอนจอความละเอียดสูงกว่าตอนนี้\n"
                f"แก้: ตั้งความละเอียด MuMu ให้ตรงกับเครื่องเดิม (ต้องอย่างน้อย {mw} x {mh})\n"
                "     MuMu > ตั้งค่า > จอภาพ > ความละเอียด (กำหนดเอง)")
            for f, d, w, h in too_big[:5]:
                info(f"  - {f} / {d}  ({w} x {h})")


# --------------------------------------------------- 7. ความละเอียดจอ + ของอื่น
def check_resolution(adb, dev):
    hr(f"7. ความละเอียดจอ {dev}")
    for cmd, label in ((["shell", "wm", "size"], "ความละเอียด"),
                       (["shell", "wm", "density"], "ความหนาแน่นพิกเซล")):
        try:
            r = subprocess.run([adb, "-s", dev] + cmd, capture_output=True, text=True, timeout=15)
            info(f"{label}: {(r.stdout or '').strip() or '?'}")
        except Exception as e:
            warn(f"อ่าน {label} ไม่ได้: {e}")
    info("*** ต้องตั้งให้ตรงกับเครื่องเดิมเป๊ะ ๆ ไม่งั้นทั้งพิกัดกดและการเทียบรูปจะเพี้ยน ***")


def check_extras():
    hr("8. ไฟล์ประกอบอื่น ๆ")
    for d, why in (("macros", "สคริปต์หลัก"),
                   ("script_sets", "ชุดคำสั่งย่อย"),
                   ("templates", "รูปเทียบแบบไฟล์ (ใช้เฉพาะสคริปต์เก่า)"),
                   ("tessdata", "ข้อมูลภาษาของ Tesseract (ใช้ตอนอ่านเพชร)")):
        p = os.path.join(BASE, d)
        n = len(os.listdir(p)) if os.path.isdir(p) else -1
        if n < 0:
            warn(f"ไม่มีโฟลเดอร์ {d}/ ({why})",
                 f"ก็อปโฟลเดอร์ {d}/ มาวางข้าง MuMupow_new.exe")
        else:
            ok(f"{d}/ มี {n} ไฟล์ ({why})")

    apk = os.path.join(BASE, "ADBKeyboard.apk")
    if os.path.exists(apk):
        ok("ADBKeyboard.apk (คีย์บอร์ดไทย)")
    else:
        warn("ไม่มี ADBKeyboard.apk — จะพิมพ์ภาษาไทยเข้าเกมไม่ได้ (ภาษาอังกฤษ/ตัวเลขยังพิมพ์ได้)",
             "ถ้าสคริปต์ต้องพิมพ์ไทย ให้ก็อป ADBKeyboard.apk มาวางข้างโปรแกรม\n"
             "แล้วกดในโปรแกรม: ตั้งค่า > เปิดคีย์บอร์ดไทย")

    acc = os.path.join(BASE, "accounts.json")
    if os.path.exists(acc):
        try:
            n = len(json.load(open(acc, encoding="utf-8")))
            ok(f"accounts.json มี {n} รหัส")
        except Exception as e:
            bad(f"accounts.json เสีย อ่านไม่ได้: {e}",
                "ดูไฟล์สำรอง accounts.json.bak ข้าง ๆ กัน")
    else:
        info("ยังไม่มี accounts.json (ปกติถ้าเพิ่งลงใหม่ - โปรแกรมจะสร้างให้เอง)")

    try:
        from mumu_controller import find_tesseract
        t = find_tesseract()
        if t:
            ok(f"Tesseract: {t}")
        else:
            warn("ไม่เจอ Tesseract — เฉพาะฟีเจอร์อ่านเพชร/อ่านชื่อกิลด์จะใช้ไม่ได้ "
                 "(ขั้นเช็ครูปไม่เกี่ยว)",
                 "โหลดจาก https://github.com/UB-Mannheim/tesseract/wiki")
    except Exception:
        pass


# ------------------------------------------------------------------- สรุปผล
def summary():
    hr("สรุป")
    fails = [f for f in FINDINGS if f[0] == "ตก"]
    warns = [f for f in FINDINGS if f[0] == "เตือน"]
    if not fails and not warns:
        print("  ทุกอย่างผ่านหมด ระบบภาพน่าจะใช้งานได้ปกติ")
        print("  ถ้ายังใช้ไม่ได้ ให้ลองรันสคริปต์จริงแล้วก็อป log จากคอนโซลล่างของโปรแกรมมาดู")
        return
    if fails:
        print(f"\n  พบปัญหาที่ต้องแก้ {len(fails)} ข้อ:\n")
        for i, (_lv, msg, fix) in enumerate(fails, 1):
            print(f"  {i}) {msg}")
            for line in (fix or "ยังไม่มีวิธีแก้อัตโนมัติ").splitlines():
                print("     " + line)
            print()
    if warns:
        print(f"  ข้อควรระวังอีก {len(warns)} ข้อ:\n")
        for i, (_lv, msg, fix) in enumerate(warns, 1):
            print(f"  {i}) {msg}")
            for line in (fix or "").splitlines():
                if line.strip():
                    print("     " + line)
            print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="ไม่ต่อจอ ตรวจแค่ไลบรารีกับไฟล์")
    ap.add_argument("--device", help="ระบุจอเอง เช่น 127.0.0.1:16384")
    a = ap.parse_args()

    print("ตรวจระบบภาพของ MuMupow")
    print("โฟลเดอร์:", BASE)
    print("Python:", sys.version.split()[0])

    cv2, np = check_libs()
    check_extras()

    if a.offline:
        hr("โหมด --offline: ข้ามการต่อจอทั้งหมด")
        summary()
        return

    adb = check_adb()
    if not adb:
        summary()
        return
    devs = [a.device] if a.device else list_devices(adb)
    for dev in devs[:2]:                      # ตรวจแค่ 2 จอพอ ไม่ต้องทั้งหมด
        img = check_screencap(adb, dev, cv2, np)
        check_matching(cv2, np, img, dev)
        check_script_images(cv2, np, img)
        check_resolution(adb, dev)
        break                                  # จอเดียวก็พอสรุปได้แล้ว
    summary()


if __name__ == "__main__":
    main()
