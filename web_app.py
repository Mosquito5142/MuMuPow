"""POC หน้าแรก (pywebview) — แสดง UI ดีไซน์ Claude Design จริง (HTML/CSS) ในหน้าต่างเดสก์ท็อป
แล้วเชื่อมกับ backend เดิม (MuMuController + โปรไฟล์/บัญชี) ให้เห็นว่า 'ตรงแป๊ะ' + ทำงานจริงได้

เป้าหมาย POC: พิสูจน์ 2 อย่าง
  1) ดีไซน์ render ตรง 100% (เพราะเป็น HTML/CSS ชุดเดียวกับที่ Claude Design ออกให้)
  2) ปุ่มบนเว็บเรียก Python เดิมได้จริง (สแกน/เชื่อม/เลือกจอ/โหลดโปรไฟล์ = ข้อมูลจริง)

ยังไม่ทำในรอบ POC: การรันมาโครเต็มรูป (ผูก run_macro_task เดิม) — ทำต่อหลังอนุมัติทิศทาง
"""
import os
import sys
import glob
import json
import threading
import datetime

import webview

from mumu_controller import MuMuController


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class Api:
    def __init__(self):
        self.controller = MuMuController()
        self.devices = []          # รายชื่อจอที่เชื่อมต่อ (addr)
        self.selected = set()      # จอที่ติ๊กเลือก
        self.profiles = {}         # ชื่อโปรไฟล์ -> path ไฟล์
        self.current_profile = None
        self.macro_steps = []
        self.window = None         # ตั้งค่าโดย main หลังสร้างหน้าต่าง
        self._log = []
        self._load_profiles()

    # ---------- helpers ----------
    def _load_profiles(self):
        self.profiles = {}
        for f in glob.glob(os.path.join(base_dir(), "macros", "*.json")):
            try:
                d = json.load(open(f, encoding="utf-8"))
                name = d.get("name", os.path.basename(f)[:-5])
                self.profiles[name] = f
            except Exception:
                pass

    def _accounts(self):
        try:
            return json.load(open(os.path.join(base_dir(), "accounts.json"), encoding="utf-8"))
        except Exception:
            return []

    def _push_log(self, text, kind="info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.append({"ts": ts, "text": text, "kind": kind})
        self._log = self._log[-200:]
        if self.window:
            try:
                self.window.evaluate_js(f"window.onLog && window.onLog({json.dumps({'ts': ts, 'text': text, 'kind': kind})})")
            except Exception:
                pass

    # ---------- state ที่ JS ดึงไปวาด ----------
    def get_state(self):
        accts = self._accounts()
        return {
            "devices": [{"addr": d, "selected": d in self.selected} for d in self.devices],
            "connected": len(self.devices),
            "selectedCount": len(self.selected),
            "profiles": list(self.profiles.keys()),
            "currentProfile": self.current_profile,
            "steps": len(self.macro_steps),
            "accountsTotal": len(accts),
            "accountsChecked": sum(1 for a in accts if a.get("checked", True)),
            "log": self._log[-1:] if self._log else [],
        }

    # ---------- actions (เรียกจากปุ่มบนเว็บ) ----------
    def scan(self):
        self._push_log("กำลังสแกนและเชื่อมต่อ Emulator…", "info")
        try:
            ports = self.controller.load_ports()
            if not ports:
                self._push_log("ยังไม่มีพอร์ตให้สแกน (ไปตั้งค่า > พอร์ต ADB)", "warn")
            devices, _log = self.controller.scan_and_connect_all()
            self.devices = devices
            self.selected = set(devices)
            self._push_log(f"เชื่อมต่อสำเร็จ {len(devices)} จอ", "ok")
        except Exception as e:
            self._push_log(f"สแกนล้มเหลว: {e}", "err")
        return self.get_state()

    def connect_manual(self, addr):
        addr = (addr or "").strip()
        if not addr:
            return self.get_state()
        try:
            ok, out = self.controller.connect_device(addr)
            self.devices = self.controller.get_connected_devices()
            self.selected |= set(self.devices)
            self._push_log(f"เชื่อมต่อ {addr}: {'สำเร็จ' if ok else out}", "ok" if ok else "err")
        except Exception as e:
            self._push_log(f"เชื่อมต่อ {addr} ล้มเหลว: {e}", "err")
        return self.get_state()

    def toggle_device(self, addr):
        if addr in self.selected:
            self.selected.discard(addr)
        else:
            self.selected.add(addr)
        return self.get_state()

    def remove_device(self, addr):
        try:
            self.controller.disconnect_device(addr)
        except Exception:
            pass
        self.devices = [d for d in self.devices if d != addr]
        self.selected.discard(addr)
        self._push_log(f"เอาจอ {addr} ออกจากลิสต์", "info")
        return self.get_state()

    def select_profile(self, name):
        fp = self.profiles.get(name)
        if fp:
            try:
                d = json.load(open(fp, encoding="utf-8"))
                self.macro_steps = d.get("steps", [])
                self.current_profile = name
                self._push_log(f"โหลดสคริปต์ '{name}' ({len(self.macro_steps)} สเต็ป)", "ok")
            except Exception as e:
                self._push_log(f"โหลดสคริปต์ล้มเหลว: {e}", "err")
        return self.get_state()

    def run(self):
        # POC: ยังไม่ผูกตัวรันมาโครเต็ม — แค่ยืนยันว่าเรียก Python ได้จริง + เช็คความพร้อม
        if not self.selected:
            self._push_log("ยังไม่ได้เลือกจอ", "warn")
        elif not self.macro_steps:
            self._push_log("ยังไม่ได้เลือกสคริปต์", "warn")
        else:
            self._push_log(f"[POC] พร้อมรัน '{self.current_profile}' บน {len(self.selected)} จอ "
                           f"— (ตัวรันจริงจะต่อในเฟสถัดไป)", "ok")
        return self.get_state()

    def stop(self):
        self._push_log("[POC] สั่งหยุด", "info")
        return self.get_state()


def main():
    api = Api()
    html_path = os.path.join(base_dir(), "webui", "index.html")
    window = webview.create_window(
        "MuMupow",
        url=html_path,
        js_api=api,
        width=1200,
        height=780,
        min_size=(1000, 680),
        background_color="#070A11",
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
