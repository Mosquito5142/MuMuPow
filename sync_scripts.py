"""ดึงสคริปต์ตัวจริงจากโฟลเดอร์ที่ใช้งานจริง (dist/) กลับมาที่ repo ก่อนปล่อยรีลีส

ทำไมต้องมี: โปรแกรมอ่าน/เขียนสคริปต์ที่โฟลเดอร์ข้าง .exe ไม่ใช่ที่ repo
เวลาสร้าง/แก้สคริปต์ในตัวโปรแกรม ไฟล์จะไปอยู่ dist/macros/ กับ dist/script_sets/
ส่วนที่ repo ยังค้างเป็นไฟล์ตัวอย่างเก่า — ถ้าปล่อยรีลีสเลย ลูกค้าจะได้สคริปต์ตัวอย่าง
เปิดโปรแกรมได้แต่ทำงานไม่ได้ ตัวนี้เลยมีไว้ดึงของจริงกลับเข้า repo (git จะได้มีประวัติด้วย)

ใช้:  python sync_scripts.py          -> รายงานว่าจะเปลี่ยนอะไร แล้วถามยืนยัน
      python sync_scripts.py --check  -> ดูอย่างเดียว ไม่แก้ไฟล์
publish.py เรียกให้อัตโนมัติก่อนแพ็ก ZIP จะได้ไม่มีทางลืม
"""
import os
import shutil
import filecmp
import sys

from release_manifest import LIVE_DIR, SYNC_DIRS, SYNC_FILES, is_user_data


def _walk(base):
    """คืนพาธไฟล์ทั้งหมดใต้ base แบบสัมพัทธ์ (ไล่โฟลเดอร์ย่อยด้วย เช่น templates/รับของ/)"""
    out = set()
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for f in files:
            full = os.path.join(root, f)
            out.add(os.path.relpath(full, base).replace("\\", "/"))
    return out


def plan(live_dir=LIVE_DIR):
    """เทียบ repo กับโฟลเดอร์ที่ใช้งานจริง คืน (added, changed, removed)
    แต่ละรายการเป็นพาธสัมพัทธ์จากรากของ repo เช่น 'script_sets/ข้ามhotzone.json'"""
    added, changed, removed = [], [], []

    for d in SYNC_DIRS:
        live = os.path.join(live_dir, d)
        if not os.path.isdir(live):
            continue
        live_files = _walk(live)
        repo_files = _walk(d) if os.path.isdir(d) else set()

        for rel in sorted(live_files - repo_files):
            added.append(f"{d}/{rel}")
        for rel in sorted(live_files & repo_files):
            if not filecmp.cmp(os.path.join(live, rel), os.path.join(d, rel), shallow=False):
                changed.append(f"{d}/{rel}")
        for rel in sorted(repo_files - live_files):
            removed.append(f"{d}/{rel}")

    for f in SYNC_FILES:
        live = os.path.join(live_dir, f)
        if not os.path.exists(live):
            continue
        if not os.path.exists(f):
            added.append(f)
        elif not filecmp.cmp(live, f, shallow=False):
            changed.append(f)

    return added, changed, removed


def report(added, changed, removed, live_dir=LIVE_DIR):
    if not (added or changed or removed):
        print(f"✅ สคริปต์ที่ repo ตรงกับ {live_dir}/ อยู่แล้ว ไม่มีอะไรต้องซิงค์")
        return False
    print(f"\n📋 เทียบ repo กับ {live_dir}/ แล้วพบ:")
    for label, items, mark in (("เพิ่มเข้ามาใหม่", added, "+"),
                               ("เนื้อหาเปลี่ยน", changed, "~"),
                               ("จะถูกลบออกจาก repo", removed, "-")):
        if items:
            print(f"\n  {label} ({len(items)}):")
            for p in items:
                print(f"     {mark} {p}")
    if removed:
        print("\n  ⚠️  รายการ '-' คือไฟล์ที่มีใน repo แต่ไม่มีในโฟลเดอร์ที่ใช้งานจริงแล้ว")
        print("      (ปกติแปลว่าลบทิ้งไปจากในโปรแกรม) ถ้าไม่ตั้งใจลบ ให้ตอบ n แล้วเช็คก่อน")
    return True


def apply(added, changed, removed, live_dir=LIVE_DIR):
    """ก็อปจากโฟลเดอร์ที่ใช้งานจริงมาทับ repo ตามแผน"""
    for rel in added + changed:
        if is_user_data(rel):
            raise RuntimeError(f"กันไว้: {rel} เป็นไฟล์ข้อมูลของผู้ใช้ ห้ามดึงเข้า repo")
        src = os.path.join(live_dir, rel)
        os.makedirs(os.path.dirname(rel) or ".", exist_ok=True)
        shutil.copy2(src, rel)

    for rel in removed:
        try:
            os.remove(rel)
        except OSError as e:
            print(f"   ⚠️ ลบ {rel} ไม่สำเร็จ: {e}")

    print(f"\n✅ ซิงค์แล้ว: เพิ่ม {len(added)} · แก้ {len(changed)} · ลบ {len(removed)}")
    print("   อย่าลืม commit เข้า git เพื่อให้มีประวัติย้อนกลับได้")


def sync(live_dir=LIVE_DIR, assume_yes=False, check_only=False):
    """คืน True ถ้า repo พร้อมปล่อย (ตรงกันอยู่แล้ว หรือซิงค์สำเร็จ)"""
    if not os.path.isdir(live_dir):
        print(f"⚠️  ไม่พบโฟลเดอร์ {live_dir}/ — ข้ามการซิงค์")
        return True

    added, changed, removed = plan(live_dir)
    if not report(added, changed, removed, live_dir):
        return True
    if check_only:
        return False

    if not assume_yes:
        if input("\nดึงของจริงเข้า repo ตามนี้เลยไหม? (y/n) [y]: ").strip().lower() \
                not in ("", "y", "yes"):
            print("ℹ️  ข้ามการซิงค์ — repo ยังเป็นของเดิม")
            return False
    apply(added, changed, removed, live_dir)
    return True


if __name__ == "__main__":
    ok = sync(check_only="--check" in sys.argv, assume_yes="--yes" in sys.argv)
    sys.exit(0 if ok else 1)
