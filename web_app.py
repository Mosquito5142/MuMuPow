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

from mumu_controller import MuMuController, get_host_specs, estimate_mumu_capacity
from macro_runner import MacroRunner, StoryRunner, account_display_name


def base_dir():
    # โฟลเดอร์ข้อมูลผู้ใช้ (macros/, accounts.json ฯลฯ) — อยู่ข้าง .exe ตอน build
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    # โฟลเดอร์ asset ที่ถูกบันเดิลมากับ exe (webui/) — อยู่ใน _MEIPASS ตอน onefile
    return getattr(sys, "_MEIPASS", None) or base_dir()


class Api:
    def __init__(self):
        self.controller = MuMuController()
        self.devices = []          # รายชื่อจอที่เชื่อมต่อ (addr)
        self.selected = set()      # จอที่ติ๊กเลือก
        self.profiles = {}         # ชื่อโปรไฟล์ -> path ไฟล์
        self.current_profile = None
        self.macro_steps = []
        self._log = []
        # สถานะการรัน (อ่านผ่าน get_run_state แบบ polling จากฝั่งเว็บ)
        self._running = False
        self._run_state = {}       # device -> dict (status/account/step/done ...)
        self._run_log = []         # log ระหว่างรัน (ts/text/kind)
        self._run_thread = None
        self._load_profiles()

    # หา window object โดยไม่เก็บ ref ไว้บน self (กัน circular ref api<->window ที่ทำ pywebview
    # วน repr ไม่จบ -> 'maximum recursion depth' ตอนมัน log error เล็กๆ ภายใน)
    @staticmethod
    def _win():
        try:
            return webview.windows[0]
        except Exception:
            return None

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

    def _accounts_path(self):
        return os.path.join(base_dir(), "accounts.json")

    def _accounts(self):
        try:
            return json.load(open(self._accounts_path(), encoding="utf-8"))
        except Exception:
            return []

    def _save_accounts(self, accts):
        try:
            with open(self._accounts_path(), "w", encoding="utf-8") as f:
                json.dump(accts, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self._push_log(f"บันทึกบัญชีล้มเหลว: {e}", "err")
            return False

    @staticmethod
    def _acct_dot(acc):
        st = (acc.get("last_status") or "").lower()
        if st == "completed":
            return "#38BDF8"
        if st in ("device_error", "macro_error", "error"):
            return "#F87171"
        return "#58677E"

    def _push_log(self, text, kind="info"):
        # แค่สะสม log — ไม่เรียก evaluate_js จากใน handler (เสี่ยง deadlock/recursion)
        # JS จะอ่าน log ล่าสุดจากค่าที่ handler return (get_state ใส่ log[-1] มาให้)
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.append({"ts": ts, "text": text, "kind": kind})
        self._log = self._log[-200:]

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

    # ================= ตัวรันจริง (MacroRunner) =================
    _RUN_STY = {
        "running": ("กำลังรัน", "#38BDF8", "#38BDF8"),
        "queued":  ("รอคิว", "#7C8CA3", "#58677E"),
        "done":    ("เสร็จแล้ว", "#34D399", "#34D399"),
        "stuck":   ("ติด · บันทึกแล้ว", "#F87171", "#F87171"),
        "stopped": ("หยุดแล้ว", "#7C8CA3", "#58677E"),
    }

    def _load_reset_cfg(self):
        try:
            return json.load(open(os.path.join(base_dir(), "game_reset.json"), encoding="utf-8"))
        except Exception:
            return {}

    def _load_diamond_cfg(self):
        try:
            return json.load(open(os.path.join(base_dir(), "diamond_ocr.json"), encoding="utf-8"))
        except Exception:
            return {}

    def _persist_diamonds(self, rows, log_cb):
        """เขียนผลอ่านเพชรตอนจบรัน: ไฟล์ diamonds_export.json + อัปเดตจำนวนล่าสุดลง accounts.json"""
        if not rows:
            return
        try:
            with open(os.path.join(base_dir(), "diamonds_export.json"), "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_cb(f"เขียน diamonds_export.json ไม่ได้: {e}", "warn")
        try:
            by_email = {r["email"]: r for r in rows if r.get("email")}
            accts = self._accounts()
            for a in accts:
                r = by_email.get(a.get("email"))
                if r:
                    a["diamonds"] = r["diamonds"]
                    a["diamond_time"] = r["time"]
            self._save_accounts(accts)
        except Exception as e:
            log_cb(f"อัปเดตเพชรลงบัญชีไม่ได้: {e}", "warn")
        log_cb(f"บันทึกเพชร {len(rows)} รายการ → diamonds_export.json", "ok")

    def run(self):
        if self._running:
            self._push_log("กำลังรันอยู่แล้ว", "warn")
            return {"ok": False}
        devices = [d for d in self.devices if d in self.selected]
        if not devices:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        if not self.macro_steps:
            self._push_log("ยังไม่ได้เลือกสคริปต์", "warn"); return {"ok": False}
        accounts = [a for a in self._accounts() if a.get("checked", True)]

        self._running = True
        self._run_state = {}
        self._run_log = []

        def log_cb(text, kind="info"):
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self._run_log.append({"ts": ts, "text": text, "kind": kind})
            self._run_log = self._run_log[-300:]

        def progress_cb(device, **st):
            cur = self._run_state.setdefault(device, {})
            cur.update(st)

        def running_check():
            return self._running

        try:
            poll = float(self._anchor_poll) if hasattr(self, "_anchor_poll") else 0.5
        except Exception:
            poll = 0.5
        runner = MacroRunner(self.controller, self.macro_steps, log_cb=log_cb,
                             progress_cb=progress_cb, running_check=running_check,
                             anchor_poll=poll, reset_cfg=self._load_reset_cfg(),
                             diamond_cfg=self._load_diamond_cfg())

        def worker():
            try:
                log_cb(f"เริ่มรัน '{self.current_profile}' · {len(accounts)} รหัส บน {len(devices)} จอ", "ok")
                runner.run_queue(devices, accounts)
                self._persist_diamonds(runner.diamond_rows, log_cb)
                if self._running:
                    log_cb("รันครบทุกบัญชีแล้ว 🎉", "ok")
            except Exception as e:
                log_cb(f"ระบบรันขัดข้อง: {e}", "err")
            finally:
                self._running = False

        self._run_thread = threading.Thread(target=worker, daemon=True)
        self._run_thread.start()
        return {"ok": True}

    def stop(self):
        if self._running:
            self._running = False
            self._push_log("สั่งหยุด — กำลังยุติการทำงาน…", "warn")
        return {"ok": True}

    def start_story(self, interval=2.5):
        if self._running:
            self._push_log("กำลังทำงานอยู่แล้ว", "warn"); return {"ok": False}
        devices = [d for d in self.devices if d in self.selected]
        if not devices:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}

        self._running = True
        self._run_state = {}
        self._run_log = []

        def log_cb(text, kind="info"):
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self._run_log.append({"ts": ts, "text": text, "kind": kind})
            self._run_log = self._run_log[-300:]

        def progress_cb(device, **st):
            self._run_state.setdefault(device, {}).update(st)

        gem = ""
        try:
            gem = json.load(open(os.path.join(base_dir(), "gemini_config.json"), encoding="utf-8")).get("api_key", "")
        except Exception:
            pass
        try:
            iv = float(interval)
        except Exception:
            iv = 2.5
        story = StoryRunner(self.controller, log_cb=log_cb, progress_cb=progress_cb,
                            running_check=lambda: self._running, gemini_key=gem, scan_interval=iv)

        def worker():
            try:
                log_cb(f"เริ่ม Story Auto บน {len(devices)} จอ (ความถี่เช็ค {iv:g} วิ)", "ok")
                story.run_all(devices)
            except Exception as e:
                log_cb(f"Story Auto ขัดข้อง: {e}", "err")
            finally:
                self._running = False

        self._run_thread = threading.Thread(target=worker, daemon=True)
        self._run_thread.start()
        return {"ok": True}

    def get_run_state(self):
        """ฝั่งเว็บเรียก polling ทุก ~1 วิ ระหว่างรัน — คืนความคืบหน้าต่อจอ + log ล่าสุด"""
        prog = []
        for dev, s in self._run_state.items():
            label, color, dot = self._RUN_STY.get(s.get("status", "queued"), ("—", "#7C8CA3", "#58677E"))
            idx, tot = s.get("step_idx", 0), s.get("step_total", 0)
            pct = int(idx / tot * 100) if tot else 0
            port = dev.split(":")[-1]
            prog.append({
                "n": "จอ " + port, "addr": ":" + port, "label": label, "color": color, "dot": dot,
                "acct": s.get("account_name", "-"),
                "step": (f"{s.get('step_desc','')} ({idx}/{tot})" if tot else s.get("step_desc", "")),
                "pct": pct, "bar": dot,
                "done": f"{s.get('done_count',0)} / {s.get('total_accounts',0)}",
            })
        return {"running": self._running, "progress": prog, "log": self._run_log[-30:]}

    # ================= หน้าบัญชี =================
    def get_accounts_grouped(self, search=""):
        accts = self._accounts()
        q = (search or "").strip().lower()
        groups = {}
        for a in accts:
            name = a.get("ingamename") or a.get("name") or a.get("title") or a.get("email", "")
            grp = (a.get("group") or "ทั่วไป").strip()
            if q and q not in (name + " " + a.get("email", "") + " " + grp).lower():
                continue
            tok = (a.get("refresh_token") or "")[:14]
            groups.setdefault(grp, []).append({
                "email": a.get("email", ""), "name": name, "grp": grp,
                "tok": (tok + "…") if tok else "—",
                "checked": a.get("checked", True), "dot": self._acct_dot(a),
            })
        return {"groups": [{"name": g, "count": len(items), "accounts": items} for g, items in groups.items()]}

    def toggle_account(self, email):
        accts = self._accounts()
        for a in accts:
            if a.get("email") == email:
                a["checked"] = not a.get("checked", True)
                break
        self._save_accounts(accts)
        return self.get_accounts_grouped()

    def delete_account(self, email):
        accts = [a for a in self._accounts() if a.get("email") != email]
        self._save_accounts(accts)
        self._push_log(f"ลบบัญชี {email}", "info")
        return self.get_accounts_grouped()

    def del_selected_accounts(self):
        accts = self._accounts()
        keep = [a for a in accts if not a.get("checked", True)]
        n = len(accts) - len(keep)
        self._save_accounts(keep)
        self._push_log(f"ลบบัญชีที่เลือก {n} รหัส", "warn")
        return self.get_accounts_grouped()

    def select_accounts_by_status(self, kind):
        fail = {"device_error", "macro_error", "error"}
        accts = self._accounts()
        for a in accts:
            st = (a.get("last_status") or "").lower()
            a["checked"] = (st in fail) if kind == "failed" else (st != "completed")
        self._save_accounts(accts)
        return self.get_accounts_grouped()

    def save_account(self, payload):
        email = (payload.get("email") or "").strip()
        if not email:
            self._push_log("ต้องกรอกอีเมล/ไอดี", "warn")
            return self.get_accounts_grouped()
        accts = self._accounts()
        found = None
        for a in accts:
            if a.get("email") == email:
                found = a
                break
        target = found if found else {}
        target.update({
            "email": email, "name": payload.get("name", ""),
            "password": payload.get("password", ""), "group": payload.get("group") or "ทั่วไป",
            "refresh_token": payload.get("token", ""),
        })
        target.setdefault("checked", True)
        if not found:
            accts.append(target)
        self._save_accounts(accts)
        self._push_log(f"{'แก้ไข' if found else 'เพิ่ม'}บัญชี {email}", "ok")
        return self.get_accounts_grouped()

    # ================= หน้าสคริปต์ =================
    _STEP_TH = {"tap": "แตะ", "swipe": "ปัด", "text": "พิมพ์", "keyevent": "ปุ่มระบบ", "sleep": "รอเวลา",
                "start_app": "เปิดแอป", "stop_app": "ปิดแอป", "detect_image": "เจอรูปกด",
                "wait_for_image": "รอรูป", "tap_text": "กดตามข้อความ", "read_diamond": "อ่านเพชร",
                "story_auto": "เล่นเนื้อเรื่อง", "run_set": "ชุดคำสั่ง", "keyboard": "คีย์บอร์ด"}
    _STEP_ICON = {"tap": "mouse-pointer-click", "text": "type", "keyevent": "smartphone", "swipe": "move",
                  "sleep": "clock", "start_app": "power", "read_diamond": "gem"}

    def get_steps(self):
        out = []
        for i, s in enumerate(self.macro_steps):
            t = s.get("type", "tap")
            anchored = bool(s.get("anchor_img"))
            if t == "tap":
                detail = f"({s.get('x','?')}, {s.get('y','?')})" if not anchored else (s.get("desc") or "")
            elif t == "text":
                detail = s.get("text", "")
            elif t == "keyevent":
                detail = str(s.get("code", s.get("keycode", "")))
            elif t == "start_app":
                detail = s.get("package", "")
            else:
                detail = s.get("desc", "")
            icon = "image" if anchored else self._STEP_ICON.get(t, "circle")
            typ = ("anchor + " + self._STEP_TH.get(t, t)) if anchored else self._STEP_TH.get(t, t)
            delay = s.get("delay", 0)
            out.append({"no": f"{i+1:02d}", "type": typ, "icon": icon,
                        "detail": detail, "delay": (f"{float(delay):g}s" if delay else "-"),
                        "x": s.get("x", "-"), "y": s.get("y", "-"), "desc": s.get("desc", "-")})
        return {"steps": out, "count": len(out), "name": self.current_profile or "—"}

    def save_profile(self, name):
        name = (name or self.current_profile or "").strip()
        if not name:
            self._push_log("ต้องระบุชื่อสคริปต์", "warn"); return self.get_steps()
        slug = name.lower().replace(" ", "_")
        fp = os.path.join(base_dir(), "macros", f"{slug}.json")
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                json.dump({"name": name, "steps": self.macro_steps}, f, ensure_ascii=False, indent=2)
            self._load_profiles()
            self.current_profile = name
            self._push_log(f"บันทึกสคริปต์ '{name}' ({len(self.macro_steps)} สเต็ป)", "ok")
        except Exception as e:
            self._push_log(f"บันทึกสคริปต์ล้มเหลว: {e}", "err")
        return self.get_steps()

    def delete_profile(self):
        fp = self.profiles.get(self.current_profile)
        if fp and os.path.exists(fp):
            try:
                os.remove(fp)
                self._push_log(f"ลบสคริปต์ '{self.current_profile}'", "warn")
            except Exception as e:
                self._push_log(f"ลบล้มเหลว: {e}", "err")
        self.macro_steps = []
        self.current_profile = None
        self._load_profiles()
        return self.get_steps()

    def update_step(self, idx, patch):
        try:
            s = self.macro_steps[idx]
            for k, v in (patch or {}).items():
                s[k] = v
            self._push_log(f"อัปเดตขั้น {idx+1}", "info")
        except Exception:
            pass
        return self.get_steps()

    def add_step(self, after_idx):
        try:
            i = int(after_idx)
        except Exception:
            i = len(self.macro_steps) - 1
        self.macro_steps.insert(i + 1, {"type": "tap", "x": "0", "y": "0", "delay": 0.5,
                                        "desc": "ขั้นใหม่ (แก้พิกัด)"})
        return self.get_steps()

    def delete_step(self, idx):
        try:
            self.macro_steps.pop(int(idx))
        except Exception:
            pass
        return self.get_steps()

    def move_step(self, idx, direction):
        try:
            i = int(idx); j = i + int(direction)
            if 0 <= j < len(self.macro_steps):
                self.macro_steps[i], self.macro_steps[j] = self.macro_steps[j], self.macro_steps[i]
        except Exception:
            pass
        return self.get_steps()

    def test_step(self, idx):
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        try:
            step = self.macro_steps[int(idx)]
        except Exception:
            return {"ok": False}
        if step.get("type") not in ("tap", "swipe"):
            self._push_log(f"ทดสอบได้เฉพาะ tap/swipe (ขั้นนี้เป็น {step.get('type')})", "warn")
            return {"ok": False}
        dev = devs[0]
        try:
            x, y = int(float(step["x"])), int(float(step["y"]))
            if step.get("anchor_tap") and step.get("anchor_img") and step.get("anchor_region"):
                import base64
                ok, data = self.controller.capture_screenshot_bytes(dev)
                if ok:
                    found, ax, ay, _ = self.controller.match_template_bytes(
                        data, base64.b64decode(step["anchor_img"]), float(step.get("anchor_threshold", 0.8) or 0.8))
                    if found:
                        reg = step["anchor_region"]
                        x = int(round(ax + (x - (reg["x"] + reg["w"] / 2.0))))
                        y = int(round(ay + (y - (reg["y"] + reg["h"] / 2.0))))
                        self._push_log(f"[{dev}] เจอ anchor → จุดกดจริง ({x},{y})", "info")
            self.controller.tap(dev, x, y)
            self._push_log(f"[{dev}] ทดสอบแตะขั้น {int(idx)+1} ที่ ({x},{y})", "warn")
        except Exception as e:
            self._push_log(f"ทดสอบล้มเหลว: {e}", "err")
        return {"ok": True}

    def import_save_web_game(self):
        w = self._win()
        files = None
        try:
            if w:
                files = w.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                             file_types=("JSON (*.json)", "All files (*.*)"))
        except Exception as e:
            self._push_log(f"เปิดหน้าต่างเลือกไฟล์ไม่ได้: {e}", "err"); return {"ok": False}
        if not files:
            return {"ok": False}
        path = files[0]
        try:
            from save_web_game_import import import_save_web_game_accounts
            res = import_save_web_game_accounts(path, self._accounts_path())
            self._push_log(f"นำเข้า Save Web Game สำเร็จ ({res})", "ok")
        except Exception as e:
            self._push_log(f"นำเข้าล้มเหลว: {e}", "err")
        return {"ok": True}

    # ================= หน้าอื่นๆ (แมนนวล) =================
    def _selected_list(self):
        return [d for d in self.devices if d in self.selected] or list(self.selected)

    def manual_click(self, x, y):
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        try:
            self.controller.run_parallel_action(devs, self.controller.tap, int(x), int(y))
            self._push_log(f"ส่งคลิก ({x},{y}) ไป {len(devs)} จอ", "ok")
        except Exception as e:
            self._push_log(f"ส่งคลิกล้มเหลว: {e}", "err")
        return {"ok": True}

    def manual_type(self, text):
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        try:
            self.controller.run_parallel_action(devs, self.controller.input_text, text)
            self._push_log(f"ส่งข้อความไป {len(devs)} จอ", "ok")
        except Exception as e:
            self._push_log(f"ส่งข้อความล้มเหลว: {e}", "err")
        return {"ok": True}

    def manual_key(self, code):
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        try:
            self.controller.run_parallel_action(devs, self.controller.keyevent, int(code))
            self._push_log(f"ส่งปุ่ม {code} ไป {len(devs)} จอ", "ok")
        except Exception as e:
            self._push_log(f"ส่งปุ่มล้มเหลว: {e}", "err")
        return {"ok": True}

    def manual_screenshot(self):
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        d = datetime.datetime.now().strftime("%Y%m%d")
        outdir = os.path.join(base_dir(), "screenshots", d)
        os.makedirs(outdir, exist_ok=True)
        n = 0
        for dev in devs:
            try:
                p = os.path.join(outdir, f"shot_{dev.replace(':','_')}_{datetime.datetime.now().strftime('%H%M%S')}.png")
                ok, _ = self.controller.take_screenshot(dev, p)
                n += 1 if ok else 0
            except Exception:
                pass
        self._push_log(f"ถ่ายจอ {n}/{len(devs)} จอ -> screenshots/{d}/", "ok")
        return {"ok": True}

    def adb_shell(self, cmd):
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        try:
            out = ""
            for dev in devs:
                ok, res = self.controller.run_adb_cmd(["-s", dev, "shell"] + cmd.split())
                out = str(res)[:120]
            self._push_log(f"ADB '{cmd}' [{devs[0]}]: {out}", "ok")
        except Exception as e:
            self._push_log(f"ADB shell ล้มเหลว: {e}", "err")
        return {"ok": True}

    # ================= หน้าตั้งค่า =================
    def get_settings(self):
        gem = ""
        try:
            gem = json.load(open(os.path.join(base_dir(), "gemini_config.json"), encoding="utf-8")).get("api_key", "")
        except Exception:
            pass
        ports = self.controller.load_ports() or []
        prange = f"{min(ports)} – {max(ports)}" if ports else "—"
        return {"adb": self.controller.adb_path, "ports": prange,
                "gemini": ("AIza" + "•" * 16) if gem else ""}

    def save_adb(self, path):
        path = (path or "").strip()
        if not path:
            return self.get_settings()
        self.controller.adb_path = path
        try:
            self.controller.persist_adb_path(path)
            self._push_log("บันทึกพาธ ADB แล้ว (จำถาวร)", "ok")
        except Exception as e:
            self._push_log(f"บันทึก ADB ล้มเหลว: {e}", "err")
        return self.get_settings()

    def save_gemini(self, key):
        try:
            with open(os.path.join(base_dir(), "gemini_config.json"), "w", encoding="utf-8") as f:
                json.dump({"api_key": (key or "").strip()}, f)
            self._push_log("บันทึก Gemini API Key แล้ว", "ok")
        except Exception as e:
            self._push_log(f"บันทึก Gemini ล้มเหลว: {e}", "err")
        return self.get_settings()

    def check_capacity(self):
        try:
            specs = get_host_specs()
            if not specs.get("available_ok"):
                return {"cap": f"ตรวจไม่ได้: {specs.get('error','psutil?')}"}
            est = estimate_mumu_capacity(specs)
            msg = (f"RAM {specs.get('total_ram_gb','?')}GB · {specs.get('logical_cores','?')} เธรด "
                   f"→ แนะนำ ~{est.get('recommended','?')} จอ (คอขวด {est.get('bottleneck','?')})")
            self._push_log(msg, "ok")
            return {"cap": msg}
        except Exception as e:
            return {"cap": f"ตรวจไม่ได้: {e}"}

    # ---------- ปุ่มหน้าต่าง (frameless -> ต้องสั่งเอง) ----------
    def win_min(self):
        w = self._win()
        if w:
            try:
                w.minimize()
            except Exception:
                pass

    def win_max(self):
        w = self._win()
        if w:
            try:
                w.toggle_fullscreen()
            except Exception:
                pass

    def win_close(self):
        w = self._win()
        if w:
            try:
                w.destroy()
            except Exception:
                pass


def main():
    api = Api()
    html_path = os.path.join(resource_dir(), "webui", "index.html")
    webview.create_window(
        "MuMupow",
        url=html_path,
        js_api=api,
        width=1200,
        height=780,
        min_size=(1000, 680),
        background_color="#070A11",
    )
    webview.start()


if __name__ == "__main__":
    main()
