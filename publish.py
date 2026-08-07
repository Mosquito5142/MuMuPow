"""ปล่อยรีลีสขึ้น GitHub — สร้าง ZIP 2 แบบให้ลูกค้าเลือกตามสถานการณ์

  update.zip  = โปรแกรม + สคริปต์ (ไม่มีไฟล์ข้อมูลของลูกค้าอยู่ข้างในเลย)
                ลูกค้าเก่าแตกทับโฟลเดอร์เดิมได้เลย ไม่ต้องก็อปอะไรกลับ
  full.zip    = update.zip + ค่าตั้งต้น (presets/diamond_ocr/guild_ocr) สำหรับเครื่องที่ลงใหม่

เหตุผลที่แยกสองแบบ: ไฟล์อย่าง diamond_ocr.json ลูกค้าลากกรอบตั้งเอง ถ้าใส่ใน ZIP อัปเดต
ทุกครั้งที่อัปเดตค่าที่เขาตั้งจะโดนรีเซ็ตกลับเป็นของเรา — แต่เครื่องลงใหม่ก็ยังต้องมีค่าตั้งต้น
"""
import os
import sys
import shutil
import zipfile
import subprocess

import sync_scripts
from release_manifest import (SHIP_FILES, SHIP_DIRS, SEED_FILES,
                              USER_DATA_FILES, USER_DATA_DIRS, is_user_data)

# build ลงโฟลเดอร์แยก ไม่ยุ่งกับ dist/ เพราะเครื่องที่ใช้งานจริงเก็บ accounts.json /
# macros/ / error_reports/ ไว้ใน dist/ — ของเดิม rmtree('dist') ทิ้งทั้งโฟลเดอร์
# ซึ่งลบข้อมูลจริงหายหมดโดยไม่ถามอะไรสักคำ
BUILD_OUT = "release_build"
WORK_DIR = "release_work"
RELEASE_DIR = "release_zip"


def run_cmd(command, shell=True):
    print(f"\n> Running: {command}")
    result = subprocess.run(command, shell=shell, text=True)
    if result.returncode != 0:
        print(f"❌ Error: Command failed with exit code {result.returncode}")
        return False
    return True


def check_gh_installed():
    try:
        r = subprocess.run("gh --version", shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True)
        return r.returncode == 0
    except Exception:
        return False


def check_gh_auth():
    try:
        r = subprocess.run("gh auth status", shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True)
        return "Logged in to github.com" in (r.stdout + r.stderr)
    except Exception:
        return False


def suggest_next_version():
    try:
        r = subprocess.run("git describe --tags --abbrev=0", shell=True,
                           stdout=subprocess.PIPE, text=True)
        if r.returncode != 0:
            return ""
        last = r.stdout.strip()
        print(f"Latest Git Tag found: {last}")
        if last.startswith("v"):
            parts = last[1:].split(".")
            if len(parts) == 3 and parts[2].isdigit():
                parts[2] = str(int(parts[2]) + 1)
                return "v" + ".".join(parts)
    except Exception:
        pass
    return ""


def build_exes():
    """คอมไพล์ทั้งสองแอปลง release_build/ (ไม่แตะ dist/)"""
    for folder in (BUILD_OUT, WORK_DIR):
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)

    for spec in ("MuMupow.spec", "MuMupow_web.spec"):
        if not os.path.exists(spec):
            print(f"⚠️  ไม่พบ {spec} — ข้าม")
            continue
        print(f"\n🔨 กำลังคอมไพล์จาก {spec} ...")
        if not run_cmd(f'python -m PyInstaller --clean --distpath "{BUILD_OUT}" '
                       f'--workpath "{WORK_DIR}" {spec}'):
            print(f"❌ คอมไพล์ {spec} ไม่สำเร็จ")
            return False
    return True


def collect_ship_items():
    """หาไฟล์/โฟลเดอร์ที่จะใส่ ZIP — .exe เอาจาก release_build/ ก่อน ถ้าไม่มีค่อยใช้ของราก
    คืน list ของ (พาธจริงบนดิสก์, ชื่อที่จะใช้ใน ZIP)"""
    items = []
    for name in SHIP_FILES:
        built = os.path.join(BUILD_OUT, name)
        src = built if os.path.exists(built) else name
        if os.path.exists(src):
            items.append((src, name))
        else:
            print(f"⚠️  ไม่พบ {name} — ZIP จะไม่มีไฟล์นี้")

    for d in SHIP_DIRS:
        if not os.path.isdir(d):
            print(f"⚠️  ไม่พบโฟลเดอร์ {d}/ — ZIP จะไม่มีโฟลเดอร์นี้")
            continue
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in USER_DATA_DIRS and not x.startswith(".")]
            for f in files:
                full = os.path.join(root, f)
                items.append((full, os.path.relpath(full, ".").replace("\\", "/")))
    return items


def write_zip(path, items, note_name, note_text, allow=()):
    """เขียน ZIP + ใส่ไฟล์อ่านก่อนภาษาไทยไว้บนสุด

    กันพลาดชั้นสุดท้าย: ถ้ามีไฟล์ของลูกค้าหลุดเข้ามา ให้หยุดทันทีแทนที่จะปล่อยไป
    allow = ไฟล์ที่ 'ตั้งใจ' ให้มีได้ทั้งที่เป็นของลูกค้า — ใช้กับ full.zip เท่านั้น
    (ค่าตั้งต้นสำหรับเครื่องที่ยังไม่มีไฟล์นั้น) ZIP อัปเดตต้องไม่ส่ง allow มาเลย"""
    allow = set(allow)
    for _src, arc in items:
        if is_user_data(arc) and arc not in allow:
            raise RuntimeError(f"ไฟล์ของลูกค้าหลุดเข้า ZIP: {arc} — ตรวจ release_manifest.py")

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in items:
            z.write(src, arc)
        z.writestr(note_name, note_text)
    size = os.path.getsize(path) / 1024 / 1024
    print(f"   ✅ {path}  ({size:.1f} MB, {len(items) + 1} ไฟล์)")


UPDATE_NOTE = """วิธีอัปเดต (ไฟล์ข้อมูลของคุณจะไม่หาย)

1. ปิดโปรแกรม MuMupow ให้สนิทก่อน
2. แตกไฟล์ ZIP นี้ทับลงในโฟลเดอร์เดิมที่คุณใช้อยู่
3. ถ้า Windows ถามว่าจะแทนที่ไฟล์ไหม -> กด "แทนที่ไฟล์ในปลายทาง"
4. เปิดโปรแกรมได้เลย

** ไม่ต้องก็อปอะไรทั้งนั้น **
ใน ZIP นี้ไม่มีไฟล์ข้อมูลของคุณอยู่เลย จึงไม่มีอะไรไปทับได้:
  - accounts.json  (รหัสทั้งหมดของคุณ)
  - ports.json     (พอร์ตจอของเครื่องคุณ)
  - adb_config.json (พาธ adb ของเครื่องคุณ)
  - ค่าพื้นที่อ่านเพชร / พรีเซ็ตพิกัด ที่คุณตั้งเอง

ถ้านี่คือการติดตั้งครั้งแรก ให้โหลดไฟล์ full.zip แทน
"""

FULL_NOTE = """วิธีติดตั้งครั้งแรก

1. แตกไฟล์ ZIP นี้ลงในโฟลเดอร์ที่ต้องการ (เช่น D:\\MuMupow)
2. เปิด MuMupow_new.exe
3. ไปหน้า "ตั้งค่า" -> ตั้งพาธ adb แล้วกดสแกนหาจอ
4. ไปหน้า "บัญชี" -> เพิ่มรหัสของคุณ

ครั้งต่อไปที่อัปเดต ให้โหลด update.zip แทน (ข้อมูลของคุณจะไม่โดนทับ)
"""


def build_zips(version):
    if os.path.exists(RELEASE_DIR):
        shutil.rmtree(RELEASE_DIR, ignore_errors=True)
    os.makedirs(RELEASE_DIR, exist_ok=True)

    items = collect_ship_items()
    if not items:
        print("❌ ไม่มีไฟล์ให้แพ็กเลย")
        return []

    print("\n📦 กำลังสร้าง ZIP...")
    update_zip = os.path.join(RELEASE_DIR, f"MuMupow-{version}-update.zip")
    write_zip(update_zip, items, "อ่านก่อน-วิธีอัปเดต.txt", UPDATE_NOTE)

    seeds = [(f, f) for f in SEED_FILES if os.path.exists(f)]
    for f in SEED_FILES:
        if not os.path.exists(f):
            print(f"⚠️  ไม่พบค่าตั้งต้น {f} — เครื่องที่ลงใหม่จะต้องตั้งเอง")
    full_zip = os.path.join(RELEASE_DIR, f"MuMupow-{version}-full.zip")
    write_zip(full_zip, items + seeds, "อ่านก่อน-วิธีติดตั้ง.txt", FULL_NOTE,
              allow=SEED_FILES)

    return [update_zip, full_zip]


RELEASE_BODY = """### ดาวน์โหลดตัวไหนดี

| สถานการณ์ | โหลดไฟล์ |
|---|---|
| **ใช้อยู่แล้ว อยากอัปเดต** | `MuMupow-{v}-update.zip` |
| **ลงเครื่องใหม่ครั้งแรก** | `MuMupow-{v}-full.zip` |

### วิธีอัปเดต (ข้อมูลไม่หาย)

1. ปิดโปรแกรมให้สนิท
2. แตก `update.zip` **ทับลงโฟลเดอร์เดิม** ที่ใช้อยู่
3. Windows ถามว่าแทนที่ไหม → กด **"แทนที่ไฟล์ในปลายทาง"**
4. เปิดโปรแกรมได้เลย

**ไม่ต้องก็อป `accounts.json` / `ports.json` / `adb_config.json` อีกต่อไป** —
ไฟล์พวกนี้ไม่ได้อยู่ใน ZIP จึงไม่มีอะไรไปทับข้อมูลของคุณ
ค่าพื้นที่อ่านเพชรและพรีเซ็ตพิกัดที่ตั้งเองไว้ก็อยู่ครบเหมือนเดิม
"""


def main():
    print("=" * 46)
    print("🚀 MuMupow Release Publisher")
    print("=" * 46)

    if not check_gh_installed():
        print("❌ ยังไม่ได้ติดตั้ง GitHub CLI ('gh')")
        print("💡 ติดตั้งด้วย: winget install --id GitHub.cli")
        sys.exit(1)

    if not check_gh_auth():
        print("⚠️ ยังไม่ได้ล็อกอิน gh — กำลังเรียก 'gh auth login'")
        if not run_cmd("gh auth login"):
            print("❌ ล็อกอินไม่สำเร็จ")
            sys.exit(1)

    default_version = suggest_next_version()
    prompt = (f"ใส่เลขเวอร์ชัน (เช่น v1.0.1) [{default_version}]: "
              if default_version else "ใส่เลขเวอร์ชัน (เช่น v1.0.0): ")
    version = input(prompt).strip() or default_version
    if not version:
        print("❌ ต้องระบุเลขเวอร์ชัน")
        sys.exit(1)
    if not version.startswith("v"):
        version = "v" + version

    if input("คอมไพล์ .exe ใหม่ก่อนไหม? (y/n) [y]: ").strip().lower() in ("", "y", "yes"):
        if not build_exes():
            sys.exit(1)
    else:
        print("ℹ️  ข้ามการคอมไพล์ — จะใช้ .exe ที่มีอยู่")

    # ดึงสคริปต์ตัวจริงจากโฟลเดอร์ที่ใช้งานจริงกลับเข้า repo ก่อนแพ็ก
    # ถ้าข้ามขั้นนี้ ZIP จะได้แต่สคริปต์ตัวอย่างที่ค้างอยู่ใน repo (ลูกค้าเปิดได้แต่ใช้งานไม่ได้)
    if not sync_scripts.sync():
        if input("\nสคริปต์ใน repo ยังไม่ตรงกับตัวที่ใช้งานจริง — ปล่อยต่อทั้งอย่างนี้ไหม? "
                 "(y/n) [n]: ").strip().lower() not in ("y", "yes"):
            print("ℹ️  ยกเลิก — รัน 'python sync_scripts.py' แล้วค่อยลองใหม่")
            sys.exit(0)

    try:
        zips = build_zips(version)
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    if not zips:
        sys.exit(1)

    print("\nสรุปสิ่งที่จะปล่อย:")
    for z in zips:
        print(f"   • {os.path.basename(z)}")
    print(f"\nไฟล์ของลูกค้าที่ถูกกันออกไป: {', '.join(USER_DATA_FILES)}")
    if input("\nยืนยันปล่อยขึ้น GitHub? (y/n) [y]: ").strip().lower() not in ("", "y", "yes"):
        print(f"ℹ️  ยกเลิกการปล่อย — ไฟล์ ZIP ยังอยู่ที่ {RELEASE_DIR}/")
        sys.exit(0)

    is_prerelease = input("เป็น Pre-release ไหม? (y/n) [n]: ").strip().lower() in ("y", "yes")

    notes_path = os.path.join(RELEASE_DIR, "notes.md")
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write(RELEASE_BODY.format(v=version))

    assets = " ".join(f'"{z}"' for z in zips)
    cmd = (f'gh release create {version} {assets} --title "{version}" '
           f'--notes-file "{notes_path}"')
    if is_prerelease:
        cmd += " --prerelease"

    print("\n🚀 กำลังสร้าง GitHub Release...")
    if not run_cmd(cmd):
        print("❌ ปล่อยรีลีสไม่สำเร็จ")
        sys.exit(1)

    print(f"\n🎉 ปล่อยเวอร์ชัน {version} เรียบร้อย!")
    try:
        r = subprocess.run("git config --get remote.origin.url", shell=True,
                           stdout=subprocess.PIPE, text=True)
        if r.returncode == 0:
            url = r.stdout.strip()
            if url.endswith(".git"):
                url = url[:-4]
            if url.startswith("git@github.com:"):
                url = "https://github.com/" + url[15:]
            print(f"🔗 {url}/releases/tag/{version}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
