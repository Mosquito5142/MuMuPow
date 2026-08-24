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
import shutil
import time
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


def _get_effective_status(acc):
    st = (acc.get("last_status") or "").lower()
    last_run_str = acc.get("last_run")
    if not last_run_str:
        return ""
    try:
        last_run_dt = datetime.datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return st
    
    now = datetime.datetime.now()
    if now.hour >= 5:
        farming_start = now.replace(hour=5, minute=0, second=0, microsecond=0)
    else:
        yesterday = now - datetime.timedelta(days=1)
        farming_start = yesterday.replace(hour=5, minute=0, second=0, microsecond=0)
        
    if last_run_dt < farming_start:
        return ""
    return st


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
        self._anchor_poll = 2.0
        # โหมด 'หยุดรอตรวจทานทีละชุด' (pause_between_batches)
        self._awaiting_next_batch = False
        self._batch_devices = []
        self._batch_pending = []
        self._runner = None
        # จอที่หยุดรอผู้ใช้แก้ไข (anchor_on_fail='pause') — device -> {account, step_path, shot_b64, ts, desc}
        self._paused = {}
        # จอที่กำลัง 'รันต่อ' อยู่ (resume_paused) — device -> {"running": bool} (ให้ stop() สั่งหยุดได้)
        self._active_resumes = {}
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
        # โหลดสคริปต์ดีฟอลต์อัตโนมัติตอนยังไม่มีอันไหนโหลด (เปิดแอปครั้งแรก) — ให้หน้าสคริปต์
        # และ dropdown หน้าแรกตรงกัน ไม่ต้องเลือกก่อนถึงจะเห็นขั้นตอน
        if not self.current_profile and self.profiles:
            default = next((n for n in self.profiles if "Default" in n or "รับของ" in n), None) \
                or list(self.profiles)[0]
            self._load_profile_steps(default)

    def _load_profile_steps(self, name):
        fp = self.profiles.get(name)
        if not fp:
            return False
        try:
            d = json.load(open(fp, encoding="utf-8"))
            self.macro_steps = d.get("steps", [])
            self.current_profile = name
            return True
        except Exception:
            return False

    def _accounts_path(self):
        return os.path.join(base_dir(), "accounts.json")

    # ล็อกกันหลายเธรดเขียน accounts.json ทับกัน — ตอนกด 'หยุด' เธรดของทุกจอที่กำลัง resume
    # จะหลุดออกจากลูปพร้อมกันแล้ววิ่งเข้า _persist_* ทีเดียว ถ้าไม่มีล็อกไฟล์จะพัง
    _accounts_lock = threading.RLock()

    def _read_accounts_raw(self):
        """อ่าน accounts.json — คืน (อ่านสำเร็จไหม, รายการบัญชี)

        แยก 'ไฟล์ว่างจริง' ออกจาก 'อ่านไม่ได้' ให้ชัด เพราะโค้ดที่เขียนทับทั้งไฟล์ต้องรู้ว่า
        ห้ามเขียนตอนอ่านไม่ได้ ไม่งั้นไฟล์เสียชั่วคราวจะกลายเป็นบัญชีหายถาวร
        """
        p = self._accounts_path()
        # ล็อกร่วมกับฝั่งเขียน — กันอ่านคาบเกี่ยวจังหวะที่กำลังสลับไฟล์อยู่
        with self._accounts_lock:
            if not os.path.exists(p):
                return True, []                  # ยังไม่เคยมีไฟล์ = ว่างจริง
            # บน Windows ระหว่าง os.replace ไฟล์อาจเปิดไม่ได้ชั่วขณะ (sharing violation)
            # ซึ่งไม่ใช่ไฟล์เสียจริง — ต้องลองใหม่สั้น ๆ ก่อน ไม่งั้นจะรายงานว่า 'ไม่มีบัญชี' มั่ว
            last_err = None
            for attempt in range(4):
                try:
                    with open(p, encoding="utf-8") as f:
                        data = json.load(f)
                    return (True, data) if isinstance(data, list) else (False, [])
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return False, []             # ไฟล์เสียจริง ลองใหม่ก็ไม่ช่วย
                except OSError as e:
                    last_err = e
                    time.sleep(0.05 * (attempt + 1))
            self._push_log(f"เปิด accounts.json ไม่ได้: {last_err}", "warn")
            return False, []

    def _accounts(self):
        ok, data = self._read_accounts_raw()
        if not ok:
            self._push_log("อ่าน accounts.json ไม่ได้ (ไฟล์อาจเสีย) — ดูไฟล์สำรอง accounts.json.bak", "err")
        return data

    def _save_accounts(self, accts, allow_empty=False):
        """เขียน accounts.json แบบ 'ทั้งหมดหรือไม่เลย'

        เขียนลงไฟล์ชั่วคราวก่อนแล้วค่อย os.replace ทับ — replace เป็น atomic ระดับ OS
        ผู้อ่านจึงเห็นได้แค่ไฟล์เก่าเต็ม ๆ หรือไฟล์ใหม่เต็ม ๆ ไม่มีสภาพครึ่ง ๆ กลาง ๆ
        (ของเดิมใช้ open(...,'w') ซึ่งล้างไฟล์เป็น 0 ไบต์ก่อนเขียน = มีช่วงที่ไฟล์ว่าง)

        allow_empty=False กันเคส 'อ่านไฟล์ไม่ได้เลยได้ลิสต์ว่าง แล้วเขียนทับ' ซึ่งลบบัญชีทิ้งหมด
        การลบบัญชีจริงจากหน้าจอต้องส่ง allow_empty=True มาเอง
        """
        if not isinstance(accts, list):
            self._push_log("บันทึกบัญชีล้มเหลว: ข้อมูลไม่ใช่รายการ", "err")
            return False
        with self._accounts_lock:
            if not accts and not allow_empty:
                ok, cur = self._read_accounts_raw()
                if not ok or cur:
                    self._push_log("ยกเลิกการบันทึก: กำลังจะเขียนทับบัญชีทั้งหมดด้วยข้อมูลว่าง", "err")
                    return False
            path = self._accounts_path()
            tmp = path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(accts, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())         # ให้ข้อมูลลงดิสก์จริงก่อนสลับไฟล์
                if os.path.exists(path):
                    try:
                        shutil.copy2(path, path + ".bak")   # สำรองตัวเดิมไว้ให้กู้ได้
                    except Exception:
                        pass
                os.replace(tmp, path)
                return True
            except Exception as e:
                self._push_log(f"บันทึกบัญชีล้มเหลว: {e}", "err")
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                return False

    def _update_accounts(self, mutate, log_cb=None):
        """อ่าน→แก้→เขียน accounts.json ทั้งชุดภายใต้ล็อกเดียว

        ทุกที่ที่แก้บัญชีจากเธรดเบื้องหลัง (ผลรัน/เพชร) ต้องผ่านทางนี้ ไม่งั้นสองเธรดจะอ่าน
        ไฟล์เดียวกันคนละจังหวะแล้วเขียนทับกัน ทำให้ผลของเธรดที่เขียนก่อนหายไปเงียบ ๆ

        mutate(accts) -> True ถ้ามีการแก้จริง (False = ไม่ต้องเขียน)
        """
        say = log_cb or (lambda t, k="info": self._push_log(t, k))
        with self._accounts_lock:
            ok, accts = self._read_accounts_raw()
            if not ok:
                say("ข้ามการบันทึกลงบัญชี: อ่าน accounts.json ไม่ได้ (กันข้อมูลหาย)", "err")
                return False
            try:
                changed = mutate(accts)
            except Exception as e:
                say(f"แก้ข้อมูลบัญชีไม่สำเร็จ: {e}", "warn")
                return False
            if not changed:
                return False
            return self._save_accounts(accts, allow_empty=True)

    @staticmethod
    def _acct_dot(acc):
        st = _get_effective_status(acc)
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
        self._log = self._log[-600:]

    def get_logs(self):
        """คืน log ทั้งหมดตามลำดับจริง — ให้หน้าคอนโซลเต็ม/ปุ่มคัดลอก
        (log ตอนรันถูก append เข้า self._log ด้วย จึงไม่หายตอนเริ่มรันรอบใหม่)"""
        return {"logs": self._log[-600:]}

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
            # ต้องกรองจอซ้ำ (เครื่องจริงเดียวกันอาจโผล่หลายพอร์ต) เหมือน scan() —
            # ตัวนี้เคยลืมเรียก get_unique_devices ทำให้กดเชื่อมต่อเองแล้วจอซ้ำโผล่ในลิสต์
            connected = self.controller.get_connected_devices()
            self.devices = self.controller.get_unique_devices(connected)
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
        if self._load_profile_steps(name):
            self._push_log(f"โหลดสคริปต์ '{name}' ({len(self.macro_steps)} สเต็ป)", "ok")
        else:
            self._push_log(f"โหลดสคริปต์ '{name}' ไม่ได้", "err")
        return self.get_state()

    # ================= ตัวรันจริง (MacroRunner) =================
    _RUN_STY = {
        "running": ("กำลังรัน", "#38BDF8", "#38BDF8"),
        "queued":  ("รอคิว", "#7C8CA3", "#58677E"),
        "done":    ("เสร็จแล้ว", "#34D399", "#34D399"),
        "stuck":   ("ติด · บันทึกแล้ว", "#F87171", "#F87171"),
        "stopped": ("หยุดแล้ว", "#7C8CA3", "#58677E"),
        "paused":  ("⏸ รอแก้ไข", "#FBBF24", "#FBBF24"),
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

    def _load_stuck_mode(self):
        """โหมดเมื่อจอติด — เก็บใน game_reset.json เพราะเป็นเรื่องเดียวกับการรีเซ็ตเกม
        'next' = ไปไอดีถัดไป (รีเซ็ตเกมกลับหน้า login ให้) · 'pause' = จอดรอคนมาแก้"""
        cfg = self._load_reset_cfg()
        return "next" if str(cfg.get("on_stuck", "next")) == "next" else "pause"

    def save_stuck_mode(self, mode):
        cfg = self._load_reset_cfg()
        cfg["on_stuck"] = "next" if str(mode) == "next" else "pause"
        try:
            with open(os.path.join(base_dir(), "game_reset.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self._push_log("บันทึกโหมดเมื่อจอติดแล้ว", "ok")
        except Exception as e:
            self._push_log(f"บันทึกโหมดไม่ได้: {e}", "err")
        return {"on_stuck": cfg["on_stuck"]}

    def get_stuck_mode(self):
        return {"on_stuck": self._load_stuck_mode()}

    def _load_gemini_key(self):
        """คีย์ Gemini (ตัวกู้จอด้วย AI ของ Story Auto) — ว่างได้ ระบบจะข้ามส่วน AI ไปเอง"""
        try:
            return json.load(open(os.path.join(base_dir(), "gemini_config.json"),
                                  encoding="utf-8")).get("api_key", "")
        except Exception:
            return ""

    def _persist_diamonds(self, rows, log_cb):
        """เขียนผลอ่านเพชรตอนจบรัน: ไฟล์ export + อัปเดตจำนวนล่าสุดลง accounts.json
        + ส่งเข้าเว็บ Save Web Game อัตโนมัติ (พอร์ตจาก gui._write_and_push_diamonds ให้ทำงานตรงกัน)

        ชื่อไฟล์ export อ่านจาก diamond_ocr.json ('export_path') เหมือนฝั่ง Tkinter เป๊ะ ดีฟอลต์
        'diamond_export.json' — เดิมฝั่งนี้ hardcode 'diamonds_export.json' (มี s เกิน) ทำให้สลับแอป
        แล้วเห็นคนละไฟล์"""
        if not rows:
            return
        cfg = self._load_diamond_cfg()
        export_name = (cfg.get("export_path") or "diamond_export.json").strip()
        try:
            with open(os.path.join(base_dir(), export_name), "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_cb(f"เขียน {export_name} ไม่ได้: {e}", "warn")
        by_email = {r["email"]: r for r in rows if r.get("email")}

        def apply_diamonds(accts):
            hit = False
            for a in accts:
                r = by_email.get(a.get("email"))
                if r:
                    a["diamonds"] = r["diamonds"]
                    a["diamond_time"] = r["time"]
                    hit = True
            return hit

        self._update_accounts(apply_diamonds, log_cb)
        log_cb(f"บันทึกเพชร {len(rows)} รายการ → {export_name}", "ok")
        self._auto_push_diamonds(rows, cfg, log_cb)

    def _auto_push_diamonds(self, rows, cfg, log_cb):
        """ส่งเพชรที่เพิ่งอ่านได้เข้าเว็บ Save Web Game อัตโนมัติตอนจบรัน (ถ้าเปิด auto_push + ตั้ง URL ไว้)
        จับคู่ด้วย save_web_game_id ที่ติดมากับ row (มาจากบัญชีตอนอ่าน) — เหมือน Tkinter ทุกประการ
        ต่างจากปุ่ม push_diamonds_web ที่ส่ง 'ทุกบัญชีที่มีเพชร' — อันนี้ส่งเฉพาะที่เพิ่งอ่านรอบนี้"""
        from save_web_game_import import push_diamonds_to_web
        url = (cfg.get("web_base_url") or "").strip()
        if not cfg.get("auto_push", True):
            return
        if not url:
            log_cb("ยังไม่ได้ตั้ง URL เว็บ — ข้ามการส่งเพชรเข้าเว็บ (ตั้งได้ที่การ์ดระบบเพชร)", "info")
            return
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        updates = [
            {"id": r["save_web_game_id"], "diamonds": r["diamonds"], "lastFarmDate": today}
            for r in rows
            if (r.get("save_web_game_id") or "").strip() and r.get("diamonds") is not None
        ]
        if not updates:
            log_cb("ไม่มีบัญชีที่มี id เว็บ (save_web_game_id) ให้ส่ง — ข้ามการส่งเข้าเว็บ", "warn")
            return
        log_cb(f"กำลังส่งเพชรเข้าเว็บ {len(updates)} บัญชี → {url}", "info")
        try:
            results, stats = push_diamonds_to_web(url, updates)
            log_cb(f"ส่งเข้าเว็บ: สำเร็จ {stats['sent']} · พลาด {stats['failed']}",
                   "ok" if not stats["failed"] else "warn")
            for acc_id, (ok, msg) in results.items():
                if not ok:
                    log_cb(f"[web {acc_id}] {msg}", "err")
        except Exception as e:
            log_cb(f"ส่งเพชรเข้าเว็บล้มเหลว: {e}", "err")

    def _persist_run_results(self, results, log_cb):
        """เขียนผลรายบัญชีลง accounts.json (last_status/last_error/last_device/last_run)
        + สรุปยอดลง log — พอร์ตจาก finalize_run_results ของแอปเดิม"""
        if not results:
            return
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        by_email = {}
        for r in results:
            em = (r.get("email") or "").strip().lower()
            if em:
                by_email[em] = r  # ไอดีเดียวรันหลายรอบ → ใช้ผลล่าสุด
        def apply_results(accts):
            changed = False
            for a in accts:
                em = (a.get("email") or "").strip().lower()
                if em in by_email:
                    r = by_email[em]
                    a["last_status"] = r.get("status", "")
                    a["last_error"] = r.get("error", "")
                    a["last_device"] = r.get("device", "")
                    a["last_run"] = stamp
                    changed = True
            return changed

        self._update_accounts(apply_results, log_cb)
        done = sum(1 for r in results if r.get("status") == "completed")
        stuck = sum(1 for r in results if r.get("status") == "device_error")
        stopped = sum(1 for r in results if r.get("status") == "stopped")
        parts = [f"เสร็จ {done}"]
        if stuck:
            parts.append(f"ติดปัญหา {stuck} (ดูรายงานจุดที่ติดได้)")
        if stopped:
            parts.append(f"ถูกหยุด {stopped}")
        log_cb("สรุปผลรอบนี้: " + " · ".join(parts), "ok" if not stuck else "warn")

    def run(self, anchor_poll=None, pause_between_batches=False, sequential=False,
            sequential_gap=None, on_stuck=None):
        if self._running:
            self._push_log("กำลังรันอยู่แล้ว", "warn")
            return {"ok": False}
        devices = [d for d in self.devices if d in self.selected]
        if not devices:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        if not self.macro_steps:
            self._push_log("ยังไม่ได้เลือกสคริปต์", "warn"); return {"ok": False}
        accounts = [a for a in self._accounts() if a.get("checked", True)]

        try:
            poll = float(anchor_poll) if anchor_poll not in (None, "") else 2.0
        except (TypeError, ValueError):
            poll = 2.0
        self._anchor_poll = poll
        # จอติดแล้วทำยังไง — จำค่าไว้ใช้กับ runner ที่สร้างทีหลัง (resume/คิวต่อ) ให้เหมือนกันทั้งรอบ
        self._on_stuck = "next" if str(on_stuck or self._load_stuck_mode()) == "next" else "pause"

        self._running = True
        self._run_state = {}
        self._run_log = []
        self._awaiting_next_batch = False
        self._sequential = bool(sequential)
        self._batch_devices = devices
        self._batch_pending = list(accounts)

        runner = MacroRunner(self.controller, self.macro_steps, log_cb=self._run_log_cb,
                             progress_cb=self._run_progress_cb, running_check=lambda: self._running,
                             anchor_poll=poll, reset_cfg=self._load_reset_cfg(),
                             diamond_cfg=self._load_diamond_cfg(),
                             gemini_key=self._load_gemini_key(),
                             on_stuck=self._on_stuck)
        runner.profile_name = self.current_profile or ""
        self._runner = runner

        if sequential:
            # ทีละจอ ไม่ขนาน — ช้ากว่ามากแต่ไม่โดนแคปช่าจากการยิงพร้อมกันหลายจอ
            try:
                gap = (float(sequential_gap[0]), float(sequential_gap[1])) if sequential_gap else (8.0, 20.0)
            except (TypeError, ValueError, IndexError):
                gap = (8.0, 20.0)

            def worker():
                try:
                    self._run_log_cb(f"เริ่มรันแบบทีละจอ '{self.current_profile}' · {len(accounts)} รหัส "
                                     f"บน {len(devices)} จอ (ยิงทีละเครื่อง เว้นจังหวะ "
                                     f"{gap[0]:g}–{gap[1]:g} วิ กันแคปช่า)", "ok")
                    runner.run_sequential(devices, accounts, gap=gap)
                    self._persist_diamonds(runner.diamond_rows, self._run_log_cb)
                    self._persist_run_results(runner.account_results, self._run_log_cb)
                    if self._running:
                        if self._paused:
                            self._run_log_cb(f"หยุดรอผู้ใช้แก้ไข {len(self._paused)} จอ — ดูแผง 'จอที่รอแก้ไข' ด้านบน", "warn")
                        else:
                            self._run_log_cb("รันครบทุกบัญชีแล้ว 🎉", "ok")
                except Exception as e:
                    self._run_log_cb(f"ระบบรันขัดข้อง: {e}", "err")
                finally:
                    self._running = False
            self._run_thread = threading.Thread(target=worker, daemon=True)
        elif pause_between_batches:
            self._run_log_cb(f"เริ่มรันแบบทีละชุด '{self.current_profile}' · {len(accounts)} รหัส "
                             f"บน {len(devices)} จอ (ชุดละ {len(devices)} ไอดี — หยุดรอตรวจทานหลังแต่ละชุด)", "ok")
            self._run_thread = threading.Thread(target=self._run_next_batch, daemon=True)
        else:
            def worker():
                try:
                    self._run_log_cb(f"เริ่มรัน '{self.current_profile}' · {len(accounts)} รหัส บน {len(devices)} จอ", "ok")
                    runner.run_queue(devices, accounts)
                    self._persist_diamonds(runner.diamond_rows, self._run_log_cb)
                    self._persist_run_results(runner.account_results, self._run_log_cb)
                    if self._running:
                        if self._paused:
                            self._run_log_cb(f"หยุดรอผู้ใช้แก้ไข {len(self._paused)} จอ — ดูแผง 'จอที่รอแก้ไข' ด้านบน", "warn")
                        else:
                            self._run_log_cb("รันครบทุกบัญชีแล้ว 🎉", "ok")
                except Exception as e:
                    self._run_log_cb(f"ระบบรันขัดข้อง: {e}", "err")
                finally:
                    self._running = False
            self._run_thread = threading.Thread(target=worker, daemon=True)
        self._run_thread.start()
        return {"ok": True}

    def _run_log_cb(self, text, kind="info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {"ts": ts, "text": text, "kind": kind}
        self._run_log.append(entry)
        self._run_log = self._run_log[-300:]
        self._log.append(entry)          # เก็บเข้า history รวมด้วย — ดูย้อน/คัดลอกได้
        self._log = self._log[-600:]

    def _run_progress_cb(self, device, **st):
        # _pause_shot/_pause_account มาจาก MacroRunner._pause_checkpoint เท่านั้น (ตอน anchor_on_fail
        # ='pause') — pop ออกก่อนเก็บลง _run_state กัน state ที่ถูก poll ทุก 1 วิ อุ้ยภาพ/รหัสผ่านค้างไปด้วย
        pause_shot = st.pop("_pause_shot", None)
        pause_account = st.pop("_pause_account", None)
        self._run_state.setdefault(device, {}).update(st)
        if st.get("status") == "paused":
            self._paused[device] = {
                "account": pause_account, "step_path": st.get("step_path", ""),
                "shot_b64": pause_shot, "ts": datetime.datetime.now().strftime("%H:%M:%S"),
                "desc": st.get("step_desc", ""),
            }
        elif st.get("status") in ("done", "stopped", "running"):
            # กลับมาทำงานตามปกติ (เช่น resume แล้วเดินหน้าต่อผ่านจุดเดิมได้แล้ว) -> เคลียร์ค้างเก่าออก
            self._paused.pop(device, None)

    def _run_next_batch(self):
        """รัน 1 ชุด (โหมด 'หยุดรอตรวจทานทีละชุด') แล้วหยุดรอผู้ใช้ตรวจจอ+กด 'รันชุดถัดไป'
        พอร์ตจาก run_macro_task/run_macro_task_resume ของแอปเดิม"""
        devices = self._batch_devices
        batch = self._batch_pending[:len(devices)]
        self._batch_pending = self._batch_pending[len(devices):]
        try:
            self._run_log_cb(f"🏁 เริ่มรันชุดคู่ขนาน {len(batch)} ไอดี บน {len(devices)} จอ…", "ok")
            self._runner.run_batch_once(devices, batch)
            if not self._running:
                return  # ผู้ใช้กดหยุดกลางชุด — ไม่ต้องถามชุดถัดไป
            paused_note = f" (มี {len(self._paused)} จอรอแก้ไข — ดูแผง 'จอที่รอแก้ไข')" if self._paused else ""
            if self._batch_pending:
                self._awaiting_next_batch = True
                self._running = False  # ไม่ใช่ "กำลังรัน" แล้ว แต่ยังไม่ปิดจริง — รอกด "รันชุดถัดไป"
                self._run_log_cb(f"⏸️ ชุดนี้เสร็จแล้ว (เหลืออีก {len(self._batch_pending)} ไอดี){paused_note} "
                                 f"กรุณาตรวจสอบหน้าจอ Emulator แล้วกด 'รันชุดถัดไป'", "warn")
            else:
                self._persist_diamonds(self._runner.diamond_rows, self._run_log_cb)
                self._persist_run_results(self._runner.account_results, self._run_log_cb)
                if self._paused:
                    self._run_log_cb(f"หยุดรอผู้ใช้แก้ไข {len(self._paused)} จอ — ดูแผง 'จอที่รอแก้ไข' ด้านบน", "warn")
                else:
                    self._run_log_cb("รันครบทุกบัญชีแล้ว 🎉", "ok")
                self._running = False
        except Exception as e:
            self._run_log_cb(f"ระบบรันขัดข้อง: {e}", "err")
            self._running = False

    def continue_batch(self):
        """ปุ่ม 'รันชุดถัดไป' — ทำงานต่อจากที่ค้างไว้ในโหมดทีละชุด"""
        if self._running or not self._awaiting_next_batch:
            return {"ok": False}
        self._awaiting_next_batch = False
        self._running = True
        self._run_state = {}
        self._run_thread = threading.Thread(target=self._run_next_batch, daemon=True)
        self._run_thread.start()
        return {"ok": True}

    def stop(self):
        if self._running or self._awaiting_next_batch:
            self._running = False
            self._awaiting_next_batch = False
            self._batch_pending = []
            self._push_log("สั่งหยุด — กำลังยุติการทำงาน…", "warn")
        if self._active_resumes:
            for flag in self._active_resumes.values():
                flag["running"] = False
            self._push_log("สั่งหยุดจอที่กำลัง 'รันต่อ' (resume) ด้วย", "warn")
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

        gem = self._load_gemini_key()
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
                "path": s.get("step_path", ""),   # ตำแหน่งบล็อกปัจจุบัน — หน้าโฟลว์ใช้ไฮไลต์สด
            })
        return {"running": self._running, "progress": prog, "log": self._run_log[-30:],
                "awaitingNextBatch": self._awaiting_next_batch,
                "remainingBatch": len(self._batch_pending),
                "pausedCount": len(self._paused),
                "activeResumes": len(self._active_resumes)}

    def list_paused(self):
        """แผง 'จอที่รอแก้ไข' โพลอันนี้คู่กับ get_run_state ทุก ~1 วิ — คืนจอที่ anchor_on_fail='pause'
        ทำให้ค้าง พร้อมภาพหน้าจอ ณ ตอนติด (base64) ให้กดดูแล้วไปสร้างเงื่อนไข/if ใหม่ได้ทันที"""
        items = []
        for dev, info in self._paused.items():
            acct = info.get("account") or {}
            items.append({
                "device": dev, "port": dev.split(":")[-1],
                "email": acct.get("email", ""), "name": account_display_name(acct) if acct else "-",
                "step_path": info.get("step_path", ""), "desc": info.get("desc", ""),
                "ts": info.get("ts", ""), "shot": info.get("shot_b64") or "",
                "resuming": dev in self._active_resumes,
            })
        items.sort(key=lambda x: x["port"])
        return {"ok": True, "items": items}

    def _continue_queue_execution(self, device, flag):
        import queue
        main_runner = self._runner
        if not main_runner or not hasattr(main_runner, "queue") or not main_runner.queue:
            return
        
        while flag["running"]:
            if self._runner != main_runner:
                # มีการเริ่มรันรอบใหม่แล้ว -> ให้หยุดการดึงคิวของรอบเก่าทันที
                self._run_log_cb(f"[{device}] หยุดดึงคิวรอบเก่าเนื่องจากมีการเริ่มรันรอบใหม่", "warn")
                break
                
            try:
                account = main_runner.queue.get_nowait()
            except queue.Empty:
                break
            
            self._run_log_cb(f"[{device}] เริ่มบัญชีถัดมาจากคิวหลัก: {account_display_name(account)}", "info")
            
            # ใช้ latest macro_steps เสมอ
            runner = MacroRunner(self.controller, self.macro_steps, log_cb=self._run_log_cb,
                                 progress_cb=self._run_progress_cb, running_check=lambda: flag["running"],
                                 anchor_poll=self._anchor_poll, reset_cfg=self._load_reset_cfg(),
                                 diamond_cfg=self._load_diamond_cfg(),
                                 gemini_key=self._load_gemini_key(),
                                 on_stuck=getattr(self, "_on_stuck", "pause"))
            runner.profile_name = self.current_profile or ""
            runner.total_accounts = main_runner.total_accounts
            
            # ดึงจำนวนที่รันสำเร็จของจอนี้มาจาก main_runner เพื่อให้แสดงผล x/y ถูกต้อง
            runner._done[device] = main_runner._done.get(device, 0)
            
            status = runner.execute_one(device, account)
            self._persist_diamonds(runner.diamond_rows, self._run_log_cb)
            self._persist_run_results(runner.account_results, self._run_log_cb)
            
            # เขียนจำนวนกลับคืน main_runner
            main_runner._done[device] = runner._done.get(device, 0)
            main_runner.queue.task_done()
            
            if status == "paused":
                break
                
        if not flag["running"]:
            self._run_progress_cb(device, status="stopped", step_desc="")
        elif not self._paused.get(device):
            self._run_progress_cb(device, status="done", step_desc="")

    def resume_paused(self, device):
        """ปุ่ม 'รันต่อจากขั้นนี้' — รันสคริปต์ (เวอร์ชันล่าสุดที่แก้ไขแล้ว) ต่อจากบล็อกระดับเส้นหลักที่
        ครอบจุดที่ค้างไว้ ด้วยบัญชีเดิมบนจอเดิม โดยไม่แตะ self._running กลาง (จอ/บัญชีอื่นที่กำลังรัน
        คู่ขนานอยู่ไม่โดนกระทบ) — ประเมิน if_image ที่บล็อกนั้นใหม่ตั้งแต่ต้น ซึ่งถูกต้องแล้วเพราะผู้ใช้
        เพิ่งแก้/เพิ่มเงื่อนไขเพื่อให้รอบนี้ผ่านไปได้"""
        def fail(msg):
            # ต้องส่งออกทาง _run_log_cb ด้วย — คอนโซลตอนรันอ่านจาก self._run_log ไม่ใช่ self._log
            # ของเดิมใช้ _push_log อย่างเดียว ข้อความเลยไม่โผล่ที่ไหนเลย กดปุ่มแล้วเงียบสนิท
            self._run_log_cb(f"[{device}] รันต่อไม่ได้: {msg}", "warn")
            return {"ok": False, "error": msg}

        info = self._paused.get(device)
        if not info:
            return fail("ไม่มีจุดค้างของจอนี้แล้ว (อาจถูกยกเลิกหรือรันต่อไปแล้ว)")

        # เคลียร์สถานะ 'กำลังรันต่อ' ที่ค้างจากรอบก่อน ถ้าเธรดนั้นตายไปแล้ว
        # ไม่งั้นจอนี้จะกดรันต่อไม่ได้อีกเลยทั้งรอบ โดยไม่มีอะไรบอก
        old = self._active_resumes.get(device)
        if old is not None:
            th = old.get("thread")
            if th is None or not th.is_alive():
                self._active_resumes.pop(device, None)
            else:
                return fail("จอนี้กำลังรันต่ออยู่แล้ว รอให้รอบนี้จบก่อน")

        try:
            root_idx = max(0, int(str(info.get("step_path", "0")).split(".")[0]))
        except Exception:
            root_idx = 0
        # ส่ง 'สคริปต์เต็ม + ขั้นที่จะเริ่ม' ไม่ใช่ตัดลิสต์มาให้ — ถ้าตัด เลขขั้นจะเลื่อนหมด
        # ทำให้จุดที่ค้างรอบถัดไปถูกรายงานผิดขั้น (กดรันต่ออีกทีจะเริ่มใหม่ตั้งแต่ขั้น 1)
        # และ anchor_retry_target ที่อ้างดัชนีของสคริปต์เต็มจะชี้ผิดขั้นด้วย
        steps = self.macro_steps
        if not steps:
            return fail("ยังไม่ได้โหลดสคริปต์ — เลือกสคริปต์ที่หน้า 'สคริปต์' ก่อน")
        if root_idx >= len(steps):
            return fail(f"สคริปต์ที่โหลดอยู่มีแค่ {len(steps)} ขั้น แต่จุดที่ค้างคือขั้น {root_idx + 1} "
                        f"— น่าจะสลับสคริปต์ไปแล้ว ให้เลือกสคริปต์เดิมกลับมาก่อน")
        account = info.get("account")

        # เก็บ thread ไว้ด้วย เพื่อให้รอบหน้าตรวจได้ว่า 'กำลังรันต่ออยู่' นั้นจริงหรือค้างเป็นซาก
        flag = {"running": True, "thread": None}
        self._active_resumes[device] = flag
        self._paused.pop(device, None)

        runner = MacroRunner(self.controller, steps, log_cb=self._run_log_cb,
                             progress_cb=self._run_progress_cb, running_check=lambda: flag["running"],
                             anchor_poll=self._anchor_poll, reset_cfg=self._load_reset_cfg(),
                             diamond_cfg=self._load_diamond_cfg(),
                             gemini_key=self._load_gemini_key(),
                             on_stuck=getattr(self, "_on_stuck", "pause"))
        runner.profile_name = self.current_profile or ""
        runner.total_accounts = 1   # รันต่อแค่บัญชีเดียว (ของเดิมที่ค้างไว้) กันการ์ดโชว์ "X / 0" ที่หน้าเว็บ

        def worker():
            try:
                self._run_log_cb(f"[{device}] ▶ รันต่อจากขั้น {root_idx + 1} (แก้ไขสคริปต์แล้ว)", "ok")
                status = runner.execute_one(device, account, start_index=root_idx)
                self._persist_diamonds(runner.diamond_rows, self._run_log_cb)
                self._persist_run_results(runner.account_results, self._run_log_cb)
                
                # หากยังเป็น paused หรือ user สั่ง stop -> จบการรันต่อ
                if status == "paused" or not flag["running"]:
                    return
                
                # หากทำบัญชีที่ค้างเสร็จเรียบร้อยและไม่โดนหยุด -> เช็คคิวที่เหลือ
                main_runner = self._runner
                if main_runner and hasattr(main_runner, "queue") and main_runner.queue:
                    self._continue_queue_execution(device, flag)
                else:
                    self._run_progress_cb(device, status="done", step_desc="")
                    
                # เช็คการสิ้นสุดคิวเพื่อแสดงความยินดี
                is_empty = True
                if main_runner and hasattr(main_runner, "queue") and main_runner.queue:
                    is_empty = main_runner.queue.empty()
                if is_empty and not self._paused and len(self._active_resumes) <= 1:
                    self._run_log_cb("รันครบทุกบัญชีแล้ว 🎉", "ok")
            except Exception as e:
                self._run_log_cb(f"[{device}] รันต่อขัดข้อง: {e}", "err")
            finally:
                self._active_resumes.pop(device, None)

        th = threading.Thread(target=worker, daemon=True)
        flag["thread"] = th
        th.start()
        return {"ok": True}

    def dismiss_paused(self, device):
        """ยกเลิกจุดค้าง โดยไม่รันต่อ (เช่น เปลี่ยนใจ ไม่ต้องแก้จุดนี้แล้ว)"""
        self._paused.pop(device, None)
        return {"ok": True}

    # ================= หน้าบัญชี =================
    def get_accounts_grouped(self, search=""):
        accts = self._accounts()
        q = (search or "").strip().lower()
        groups = {}
        for a in accts:
            # ลำดับต้องตรงกับ gui.py's account_display_name เป๊ะ: ชื่อที่ตั้งบนเว็บ (save_web_game_title,
            # ค่าดิบตอน import ไม่โดนแก้ทับ) ก่อนเสมอ แล้วค่อย title/ingamename/name/email
            # (เดิมเรียงผิด เอา ingamename ขึ้นก่อน เลยเห็นชื่อในเกมแทนชื่อที่ตั้งในเว็บ)
            name = (a.get("save_web_game_title") or a.get("title") or a.get("ingamename")
                    or a.get("name") or a.get("email", ""))
            grp = (a.get("group") or "ทั่วไป").strip()
            if q and q not in (name + " " + a.get("email", "") + " " + grp).lower():
                continue
            tok = (a.get("refresh_token") or "")[:14]
            # 'name'/'tok' = ค่าไว้ "โชว์" ในลิสต์เท่านั้น (name อาจมาจาก save_web_game_title,
            # tok ถูกหั่นให้สั้น) — ห้ามเอาไปเขียนกลับลงไฟล์เด็ดขาด
            # ฟอร์มแก้ไขต้องใช้ 'rawname'/'token'/'password' = ค่าดิบจากไฟล์ ไม่งั้นกดบันทึกแล้วข้อมูลพัง
            groups.setdefault(grp, []).append({
                "email": a.get("email", ""), "name": name, "grp": grp,
                "tok": (tok + "…") if tok else "—",
                "rawname": a.get("name", ""),
                "password": a.get("password", ""),
                "token": a.get("refresh_token") or "",
                "checked": a.get("checked", True), "dot": self._acct_dot(a),
            })
        group_names = sorted({(a.get("group") or "ทั่วไป").strip() for a in accts}) or ["ทั่วไป"]
        accounts_checked = sum(1 for a in accts if a.get("checked", True))
        return {"groups": [{"name": g, "count": len(items), "accounts": items,
                            "allChecked": all(it["checked"] for it in items)}
                           for g, items in groups.items()],
                "groupNames": group_names,
                "accountsTotal": len(accts),
                "accountsChecked": accounts_checked}

    def toggle_group(self, group, checked):
        accts = self._accounts()
        for a in accts:
            if (a.get("group") or "ทั่วไป").strip() == group:
                a["checked"] = bool(checked)
        self._save_accounts(accts)
        return self.get_accounts_grouped()

    def move_selected_to_group(self, target_group):
        target_group = (target_group or "ทั่วไป").strip() or "ทั่วไป"
        accts = self._accounts()
        n = 0
        for a in accts:
            if a.get("checked", True):
                a["group"] = target_group
                n += 1
        self._save_accounts(accts)
        self._push_log(f"ย้ายบัญชีที่เลือก {n} รหัส ไปกลุ่ม '{target_group}'", "ok")
        return self.get_accounts_grouped()

    def delete_group(self, group):
        accts = [a for a in self._accounts() if (a.get("group") or "ทั่วไป").strip() != group]
        self._save_accounts(accts, allow_empty=True)
        self._push_log(f"ลบกลุ่ม '{group}' ทั้งหมด", "warn")
        return self.get_accounts_grouped()

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
        self._save_accounts(accts, allow_empty=True)
        self._push_log(f"ลบบัญชี {email}", "info")
        return self.get_accounts_grouped()

    def del_selected_accounts(self):
        accts = self._accounts()
        keep = [a for a in accts if not a.get("checked", True)]
        n = len(accts) - len(keep)
        self._save_accounts(keep, allow_empty=True)
        self._push_log(f"ลบบัญชีที่เลือก {n} รหัส", "warn")
        return self.get_accounts_grouped()

    def select_accounts_by_status(self, kind):
        fail = {"device_error", "macro_error", "error"}
        accts = self._accounts()
        for a in accts:
            st = _get_effective_status(a)
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

        # ค่าลับ (รหัสผ่าน/โทเคน) ที่ส่งมาว่าง = "ไม่แก้" ไม่ใช่ "ล้างทิ้ง" — กันบัญชีเดิมพัง
        # ตอนแก้แค่ชื่อ/กลุ่ม (ฝั่ง Tkinter กันด้วยการบังคับกรอกรหัสผ่านก่อนบันทึก)
        def keep(new_val, key):
            new_val = (new_val or "").strip()
            return new_val if new_val else (target.get(key) or "")

        target.update({
            "email": email, "name": payload.get("name", ""),
            "password": keep(payload.get("password"), "password"),
            "group": payload.get("group") or "ทั่วไป",
            "refresh_token": keep(payload.get("token"), "refresh_token"),
        })
        target.setdefault("checked", True)
        if not found:
            accts.append(target)
        self._save_accounts(accts)
        self._push_log(f"{'แก้ไข' if found else 'เพิ่ม'}บัญชี {email}", "ok")
        return self.get_accounts_grouped()

    def batch_import_accounts(self, raw_text, group_name="ทั่วไป"):
        """นำเข้าบัญชีทีละหลายบรรทัด: แต่ละบรรทัด = 1 บัญชี คั่นด้วย | , ; หรือ TAB
        รูปแบบ: อีเมล|รหัสผ่าน[|refresh_token][|client_id] — พอร์ตจาก open_batch_import_dialog เดิม"""
        import re as _re
        raw_text = (raw_text or "").strip()
        group_name = (group_name or "").strip() or "ทั่วไป"
        if not raw_text:
            self._push_log("ยังไม่ได้วางข้อมูลบัญชี", "warn")
            return {"ok": False, "imported": 0, "duplicate": 0, "invalid": 0}

        accts = self._accounts()
        existing_emails = {a.get("email") for a in accts}
        uuid_re = _re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

        imported = duplicate = invalid = 0
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = []
            for sep in ("|", ",", ";", "\t"):
                if sep in line:
                    parts = [p.strip() for p in line.split(sep)]
                    break
            else:
                parts = [p.strip() for p in line.split() if p.strip()]
            if len(parts) < 2:
                invalid += 1
                continue
            email, pwd = parts[0], parts[1]
            refresh_token = client_id = ""
            for p in parts[2:]:
                if uuid_re.match(p):
                    client_id = p
                elif len(p) > 50:
                    refresh_token = p
            if not email or not pwd or "@" not in email:
                invalid += 1
                continue
            if email in existing_emails:
                duplicate += 1
                continue
            accts.append({"email": email, "name": "", "password": pwd,
                          "refresh_token": refresh_token, "client_id": client_id,
                          "checked": True, "group": group_name})
            existing_emails.add(email)
            imported += 1

        if imported:
            self._save_accounts(accts)
            self._push_log(f"นำเข้าบัญชีแบบกลุ่มสำเร็จ: {imported} ไอดี (กลุ่ม: {group_name}) "
                           f"· ซ้ำ {duplicate} · ไม่ถูกต้อง {invalid}", "ok")
        else:
            self._push_log(f"ไม่มีบัญชีใหม่ถูกนำเข้า · ซ้ำ {duplicate} · ไม่ถูกต้อง {invalid}", "warn")
        return {"ok": bool(imported), "imported": imported, "duplicate": duplicate, "invalid": invalid}

    @staticmethod
    def _norm_name(value):
        """ปรับชื่อให้เทียบกันง่าย: รวบช่องว่างซ้ำ ตัดหัวท้าย ตัวพิมพ์เล็ก
        (ใช้สูตรเดียวกับ save_web_game_import._norm_name ให้จับคู่ชื่อตรงกันเป๊ะ)"""
        return " ".join(str(value or "").split()).strip().lower()

    @staticmethod
    def _parse_pasted_select_line(ln):
        """แยกบรรทัดที่วางมา: รองรับทั้ง 'gameAccountId|ชื่อ' (จากปุ่มคัดลอกในเว็บฟาม —
        แม่นสุดเพราะจับคู่ด้วย id) และชื่อเปล่าๆ บรรทัดเดียว (พิมพ์เอง/รูปแบบเก่า)"""
        ln = ln.strip()
        if not ln:
            return None
        if "|" in ln:
            gid, _, label = ln.partition("|")
            gid = gid.strip()
            label = label.strip() or gid
            return {"gid": gid, "label": label}
        return {"gid": "", "label": ln}

    def select_by_pasted_names(self, raw_text):
        """วางรายชื่อ/รหัสที่คัดลอกจากหน้า 'ยังไม่ฟาม' ของเว็บ Save Web Game (บรรทัดละ 1 รายการ)
        → ติ๊กเฉพาะบัญชีที่ตรง ส่วนที่เหลือถอนติ๊กออกให้หมด ทำให้กดรันแล้วฟามได้เฉพาะรหัสที่ยังไม่ฟามจริงๆ

        จับคู่ 2 ชั้น: (1) save_web_game_id ตรงเป๊ะ (แม่นสุด — มาจากตอน import JSON) ก่อนเสมอ
        (2) ถ้าบัญชีนั้นยังไม่เคย import id เข้ามา ค่อย fallback ไปเทียบชื่อ (name/ingamename/email)"""
        raw_text = (raw_text or "").strip()
        if not raw_text:
            self._push_log("ยังไม่ได้วางรายชื่อ", "warn")
            return {"ok": False, "matched": 0, "unmatched": []}

        lines = [x for x in (self._parse_pasted_select_line(ln) for ln in raw_text.splitlines()) if x]
        if not lines:
            self._push_log("ไม่พบรายชื่อที่วางมา", "warn")
            return {"ok": False, "matched": 0, "unmatched": []}

        id_set = {x["gid"] for x in lines if x["gid"]}
        name_set = {self._norm_name(x["label"]) for x in lines}

        accts = self._accounts()
        matched_ids, matched_names = set(), set()
        for a in accts:
            gid = str(a.get("save_web_game_id") or "").strip()
            hit = bool(gid and gid in id_set)
            if hit:
                matched_ids.add(gid)
            else:
                keys = {self._norm_name(a.get("name")), self._norm_name(a.get("ingamename")),
                        self._norm_name(a.get("email"))}
                keys.discard("")
                overlap = keys & name_set
                if overlap:
                    hit = True
                    matched_names |= overlap
            a["checked"] = hit

        self._save_accounts(accts)
        unmatched = [x["label"] for x in lines
                    if not (x["gid"] and x["gid"] in matched_ids)
                    and self._norm_name(x["label"]) not in matched_names]
        matched = len(lines) - len(unmatched)
        by_id = len(matched_ids)
        self._push_log(f"เลือกจากรายชื่อที่วาง: ติ๊กแล้ว {matched}/{len(lines)} รหัส"
                       + (f" (จับด้วย id {by_id})" if by_id else "")
                       + (f" · หาไม่เจอ {len(unmatched)}" if unmatched else ""),
                       "ok" if not unmatched else "warn")
        return {"ok": True, "matched": matched, "total": len(lines), "unmatched": unmatched}

    # ================= หน้าสคริปต์ =================
    _STEP_TH = {"tap": "แตะ", "swipe": "ปัด", "text": "พิมพ์", "keyevent": "ปุ่มระบบ", "sleep": "รอเวลา",
                "start_app": "เปิดแอป", "stop_app": "ปิดแอป", "detect_image": "เจอรูปกด",
                "wait_for_image": "รอรูป", "tap_text": "กดตามข้อความ", "wait_for_text": "รอข้อความ",
                "clear_ads_loop": "เคลียร์โฆษณา", "fetch_otp": "กรอก OTP", "screenshot": "ถ่ายภาพ",
                "read_diamond": "อ่านเพชร", "story_auto": "เล่นเนื้อเรื่อง", "run_set": "ชุดคำสั่ง",
                "keyboard": "คีย์บอร์ด", "find_yellow_stage": "ด่านเหลือง",
                "tap_until_image": "กดรัวจนเจอรูป",
                "tap_around_until_image": "กดรอบๆ การ์ดจนเจอรูป",
                "if_image": "ทางเลือก (ถ้าเจอภาพ)"}
    _STEP_ICON = {"tap": "mouse-pointer-click", "text": "type", "keyevent": "smartphone", "swipe": "move",
                  "sleep": "clock", "start_app": "power", "stop_app": "power-off", "detect_image": "image",
                  "wait_for_image": "image", "tap_text": "text-cursor-input", "wait_for_text": "search",
                  "clear_ads_loop": "x-circle", "fetch_otp": "mail", "screenshot": "camera",
                  "run_set": "layers", "keyboard": "keyboard", "read_diamond": "gem",
                  "if_image": "git-branch", "story_auto": "clapperboard",
                  "tap_until_image": "mouse-pointer-2",
                  "tap_around_until_image": "scan-search"}

    # ชนิด step -> ฟิลด์ที่ใช้จริง (ตัวอื่นถูกล้างทิ้งเมื่อเปลี่ยนชนิด) — อิงจาก _build_step_from_form เดิม
    STEP_FIELDS = {
        "tap": ["x", "y", "delay"],
        "swipe": ["x", "y", "x2", "y2", "duration", "delay"],
        "text": ["text", "delay"],
        "keyevent": ["code", "delay"],
        "sleep": ["seconds"],
        "start_app": ["text", "delay"],
        "stop_app": ["text", "delay"],
        "detect_image": ["text", "threshold", "click", "delay"],
        "wait_for_image": ["text", "timeout", "threshold", "click", "delay"],
        "tap_until_image": ["x", "y", "text", "interval", "timeout", "threshold", "delay"],
        "tap_around_until_image": ["x", "y", "text", "radius", "interval", "timeout", "threshold", "delay"],
        "tap_text": ["text", "delay"],
        "wait_for_text": ["text", "timeout", "delay"],
        "clear_ads_loop": ["text", "delay"],
        "fetch_otp": ["text", "delay"],
        "read_diamond": ["delay"],
        "run_set": ["set", "block_on_fail", "block_home", "block_retries"],
        "keyboard": ["key", "action", "delay"],
        "screenshot": ["text", "delay"],
        "find_yellow_stage": ["delay"],
        "if_image": ["text", "threshold", "timeout", "delay"],
        "story_auto": ["text", "threshold", "max_stages", "delay"],
    }
    # ค่าเริ่มต้นเมื่อสร้างขั้นใหม่/เปลี่ยนชนิด
    STEP_DEFAULTS = {
        "tap": {"x": "0", "y": "0", "delay": 1.0},
        "swipe": {"x": "0", "y": "0", "x2": "0", "y2": "0", "duration": 300, "delay": 1.0},
        "text": {"text": "", "delay": 1.0},
        "keyevent": {"code": "4", "delay": 0.3},
        "sleep": {"seconds": 1.0},
        "start_app": {"text": "", "delay": 1.0},
        "stop_app": {"text": "", "delay": 1.0},
        # click=True: เจอแล้วแตะตรงจุดที่เจอเลย (ตรงกับค่าดีฟอลต์ของตัวรัน)
        "detect_image": {"text": "", "threshold": 0.8, "click": True, "delay": 1.0},
        "wait_for_image": {"text": "", "timeout": 30, "threshold": 0.8, "click": True, "delay": 0},
        # กดรัวข้ามโฆษณา: 0.5 วิ/ครั้ง คือจังหวะที่เกมส่วนใหญ่รับไหวโดยไม่หลุด
        "tap_until_image": {"x": "0", "y": "0", "text": "", "interval": 0.5,
                            "timeout": 30, "threshold": 0.8, "delay": 0},
        # radius = ใช้เมื่อไม่ได้ตั้งภาพการ์ด (กดรอบพิกัด x,y แทน)
        "tap_around_until_image": {"x": "0", "y": "0", "text": "", "radius": 60, "interval": 0.5,
                                   "timeout": 30, "threshold": 0.8, "delay": 0},
        "tap_text": {"text": "", "delay": 1.0},
        "wait_for_text": {"text": "", "timeout": 30, "delay": 0},
        "clear_ads_loop": {"text": "", "delay": 1.0},
        "fetch_otp": {"text": r"\d{6}", "delay": 1.0},
        "read_diamond": {"delay": 1.0},
        "run_set": {"set": ""},
        "keyboard": {"key": "space", "action": "press", "delay": 0.1},
        "screenshot": {"text": "screenshots/{DATE}/{NAME}_{TIME}.png", "delay": 1.0},
        "find_yellow_stage": {"delay": 1.0},
        "if_image": {"text": "", "threshold": 0.8, "timeout": 2.0, "then": [], "else": []},
        # text = รายชื่อไฟล์ปุ่มที่จะกวาด (คั่นด้วย ,) เว้นว่าง = ใช้ templates/story_*.png ทั้งหมด
        "story_auto": {"text": "", "threshold": 0.78, "max_stages": 30, "delay": 1.0},
    }

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
            elif t == "if_image":
                detail = (s.get("desc") or "ทางเลือก") + \
                    f" (เจอ {len(s.get('then') or [])} ขั้น / ไม่เจอ {len(s.get('else') or [])} ขั้น)"
            else:
                detail = s.get("desc", "")
            icon = "image" if anchored else self._STEP_ICON.get(t, "circle")
            typ = ("anchor + " + self._STEP_TH.get(t, t)) if anchored else self._STEP_TH.get(t, t)
            delay = s.get("delay", 0)
            # raw = ค่าจริงทุกฟิลด์ที่แก้ได้ (ให้ฟอร์มฝั่งเว็บเติมค่าเข้า input ตามชนิด)
            raw = {"type": t, "desc": s.get("desc", ""),
                   "x": s.get("x", ""), "y": s.get("y", ""),
                   "x2": s.get("x2", ""), "y2": s.get("y2", ""),
                   "duration": s.get("duration", ""),
                   "text": s.get("text", ""), "code": s.get("code", s.get("keycode", "")),
                   "seconds": s.get("seconds", ""), "timeout": s.get("timeout", ""),
                   "key": s.get("key", ""), "action": s.get("action", ""),
                   "set": s.get("set", ""), "threshold": s.get("threshold", ""),
                   "delay": delay}
            out.append({"no": f"{i+1:02d}", "type": typ, "icon": icon,
                        "detail": detail, "delay": (f"{float(delay):g}s" if delay else "-"),
                        "x": s.get("x", "-"), "y": s.get("y", "-"), "desc": s.get("desc", "-"),
                        "raw": raw})
        return {"steps": out, "count": len(out), "name": self.current_profile or "—",
                "typeOptions": self._step_type_options()}

    def _step_type_options(self):
        """รายชื่อชนิด step สำหรับ dropdown (ค่า+ป้ายไทย) — เรียงตามที่ใช้บ่อย"""
        order = ["tap", "swipe", "text", "if_image", "keyevent", "sleep", "start_app", "stop_app",
                 "detect_image", "wait_for_image", "tap_text", "wait_for_text",
                 "clear_ads_loop", "fetch_otp", "read_diamond", "run_set", "keyboard",
                 "screenshot", "find_yellow_stage", "story_auto", "tap_until_image",
                 "tap_around_until_image"]
        return [{"value": t, "label": f"{self._STEP_TH.get(t, t)} ({t})"} for t in order]

    def _canonical_step(self, t, merged, existing=None):
        """สร้าง step dict สะอาด: เก็บเฉพาะฟิลด์ของชนิด t + desc + ค่า anchor เดิม
        (ล้างฟิลด์ค้างจากชนิดก่อนหน้าออก เวลาเปลี่ยนชนิด)"""
        step = {"type": t, "desc": (merged.get("desc") or "").strip()}
        for k in self.STEP_FIELDS.get(t, []):
            if k in merged and merged[k] != "":
                step[k] = merged[k]
            elif k in self.STEP_DEFAULTS.get(t, {}):
                step[k] = self.STEP_DEFAULTS[t][k]
        # keyboard: คีย์/สถานะ เก็บเป็นตัวพิมพ์เล็กเสมอ (ให้ตรง _VK_CODES / _step เดิม)
        if t == "keyboard":
            if "key" in step:
                step["key"] = str(step["key"]).strip().lower()
            if "action" in step:
                step["action"] = str(step["action"]).strip().lower()
        # if_image: คงกิ่ง then/else เดิมไว้เสมอ (ฟอร์มแก้แค่ field อื่น ไม่แตะลูก)
        if t == "if_image" and existing:
            for k in ("then", "else"):
                if k in existing:
                    step[k] = existing[k]
        if t == "if_image":
            step.setdefault("then", [])
            step.setdefault("else", [])
        # คงค่าที่ไม่ได้อยู่ในฟอร์มไว้ ไม่ให้หายตอนแก้: ภาพ anchor, ภาพช่วยจำจุดที่กด
        # และภาพต้นแบบของ 'รอรูป'/'เจอรูปกด' ที่ลากกรอบไว้
        for k, v in (existing or {}).items():
            if k.startswith("anchor") or k in ("preview_img", "wait_img", "wait_region",
                                               "find_img", "find_region"):
                step[k] = v
        return step

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
            i = int(idx)
            existing = self.macro_steps[i]
            merged = dict(existing)
            merged.update(patch or {})
            t = (patch or {}).get("type") or existing.get("type", "tap")
            # แปลง delay/duration/seconds/timeout เป็นตัวเลขถ้าใส่มาเป็นสตริง
            for numk in ("delay", "duration", "seconds", "timeout"):
                if numk in merged and merged[numk] not in ("", None):
                    try:
                        merged[numk] = float(merged[numk])
                        if merged[numk].is_integer() and numk == "duration":
                            merged[numk] = int(merged[numk])
                    except (TypeError, ValueError):
                        pass
            self.macro_steps[i] = self._canonical_step(t, merged, existing)
            self._push_log(f"อัปเดตขั้น {i+1} ({t})", "info")
        except Exception as e:
            self._push_log(f"อัปเดตขั้นล้มเหลว: {e}", "warn")
        return self.get_steps()

    def extract_range_to_block(self, start, end, set_name, home="", retries="", make_block=True):
        """ตัดช่วงขั้น [start..end] (เลข 1-based, รวมปลายทั้งสอง) ออกไปเก็บเป็นชุดคำสั่งใหม่ชื่อ set_name
        แล้วแทนที่ช่วงนั้นในสคริปต์ปัจจุบันด้วย run_set 1 ขั้น (ติ๊ก 'บล็อกกันพัง' ถ้า make_block=True)
        — ให้ผู้ใช้แบ่งสคริปต์ยาว ๆ ที่ทำไว้แล้วเป็นบล็อกทีหลังได้ โดยไม่ต้องสร้างใหม่
        (แก้ในหน่วยความจำ ผู้ใช้กด 'บันทึกสคริปต์' เพื่อเซฟลงไฟล์ตามปกติ)"""
        try:
            s = int(start); e = int(end)
        except (TypeError, ValueError):
            self._push_log("ช่วงขั้นไม่ถูกต้อง (ต้องเป็นตัวเลข)", "warn"); return self.get_steps()
        name = (set_name or "").strip()
        if not name:
            self._push_log("ต้องตั้งชื่อชุดใหม่ก่อน", "warn"); return self.get_steps()
        n = len(self.macro_steps)
        if s > e:
            s, e = e, s
        i0 = max(0, s - 1)     # 1-based -> 0-based
        i1 = min(n, e)         # e รวมปลาย -> ใช้เป็น slice end ตรง ๆ
        if i0 >= i1:
            self._push_log(f"ช่วง {s}–{e} ไม่ถูกต้อง (สคริปต์มี {n} ขั้น)", "warn"); return self.get_steps()
        chunk = self.macro_steps[i0:i1]
        from script_sets import save_script_set, safe_set_slug
        path = os.path.join(base_dir(), "script_sets", f"{safe_set_slug(name)}.json")
        try:
            save_script_set(path, name, chunk)
        except Exception as ex:
            self._push_log(f"บันทึกชุดคำสั่งล้มเหลว: {ex}", "err"); return self.get_steps()
        block = {"type": "run_set", "set": name, "desc": f"บล็อก: {name}"}
        if make_block:
            block["block_on_fail"] = "home_retry"
            h = (home or "").strip()
            if h:
                block["block_home"] = h
            r = str(retries or "").strip()
            if r:
                block["block_retries"] = r
        self.macro_steps[i0:i1] = [block]
        self._push_log(f"ตัดขั้น {s}–{e} ({len(chunk)} ขั้น) เป็นบล็อก '{name}' แล้ว — อย่าลืมกด 'บันทึกสคริปต์'", "ok")
        return self.get_steps()

    def add_step(self, after_idx, step_type="tap"):
        try:
            i = int(after_idx)
        except Exception:
            i = len(self.macro_steps) - 1
        t = step_type if step_type in self.STEP_FIELDS else "tap"
        step = {"type": t, "desc": "ขั้นใหม่"}
        step.update(self.STEP_DEFAULTS.get(t, {}))
        self.macro_steps.insert(i + 1, step)
        return self.get_steps()

    def duplicate_step(self, idx):
        """คัดลอกขั้นนี้แล้ววางต่อท้ายทันที (ใช้ก็อปปุ่ม/พิกัดเดิมเวลาต้องสแปมกดซ้ำๆ
        ไม่ต้องตั้งค่าใหม่ทุกครั้ง) — deep copy กันกิ่ง then/else ของ if_image ใช้ list ร่วมกัน"""
        try:
            i = int(idx)
            copy = json.loads(json.dumps(self.macro_steps[i]))
            self.macro_steps.insert(i + 1, copy)
            self._push_log(f"คัดลอกขั้น {i+1} แล้ว", "ok")
        except Exception as e:
            self._push_log(f"คัดลอกขั้นไม่สำเร็จ: {e}", "warn")
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

    # ================= Flow Editor (ผังบล็อก + กิ่ง if_image) =================
    def _locate(self, path):
        """แปลง path เช่น [2] หรือ [2,'then',0] → (ลิสต์แม่, ดัชนีในลิสต์นั้น)
        เลข = ดัชนีบล็อกในลิสต์ปัจจุบัน, ข้อความ 'then'/'else' = มุดเข้ากิ่งของบล็อกนั้น"""
        cur = self.macro_steps
        node = None
        for j, tok in enumerate(path):
            if isinstance(tok, str):
                if node is None or tok not in ("then", "else"):
                    raise ValueError(f"path ผิดรูป: {path}")
                node.setdefault(tok, [])
                cur = node[tok]
            else:
                i = int(tok)
                if j == len(path) - 1:
                    return cur, i
                node = cur[i]
        raise ValueError(f"path ว่าง/ผิดรูป: {path}")

    def get_flow(self):
        """คืน tree ดิบทั้งก้อน (รวมกิ่ง then/else) ให้หน้าโฟลว์เรนเดอร์/แก้"""
        return {"name": self.current_profile or "—", "steps": self.macro_steps,
                "typeOptions": self._step_type_options()}

    def flow_add(self, path, step_type="tap"):
        """แทรกบล็อกใหม่ที่ตำแหน่ง path (ดัชนีท้าย = จุดแทรกในลิสต์นั้น)"""
        t = step_type if step_type in self.STEP_FIELDS else "tap"
        step = {"type": t, "desc": ""}
        step.update(json.loads(json.dumps(self.STEP_DEFAULTS.get(t, {}))))  # deep copy กัน then/else ใช้ list ร่วม
        try:
            lst, i = self._locate(path)
            i = max(0, min(i, len(lst)))
            lst.insert(i, step)
        except Exception as e:
            self._push_log(f"เพิ่มบล็อกไม่ได้: {e}", "warn")
        return self.get_flow()

    def flow_update(self, path, patch):
        try:
            lst, i = self._locate(path)
            existing = lst[i]
            merged = dict(existing)
            merged.update(patch or {})
            t = (patch or {}).get("type") or existing.get("type", "tap")
            for numk in ("delay", "duration", "seconds", "timeout", "threshold"):
                if numk in merged and merged[numk] not in ("", None):
                    try:
                        merged[numk] = float(merged[numk])
                    except (TypeError, ValueError):
                        pass
            lst[i] = self._canonical_step(t, merged, existing)
        except Exception as e:
            self._push_log(f"แก้บล็อกไม่ได้: {e}", "warn")
        return self.get_flow()

    def flow_delete(self, path):
        try:
            lst, i = self._locate(path)
            lst.pop(i)
        except Exception as e:
            self._push_log(f"ลบบล็อกไม่ได้: {e}", "warn")
        return self.get_flow()

    def flow_duplicate(self, path):
        """คัดลอกบล็อกนี้ (รวมกิ่ง then/else ถ้าเป็นบล็อกทางเลือก) วางต่อท้ายในเลนเดียวกันทันที"""
        try:
            lst, i = self._locate(path)
            copy = json.loads(json.dumps(lst[i]))   # deep copy กัน then/else อ้าง list ร่วมกัน
            lst.insert(i + 1, copy)
            self._push_log("คัดลอกบล็อกแล้ว", "ok")
        except Exception as e:
            self._push_log(f"คัดลอกบล็อกไม่ได้: {e}", "warn")
        return self.get_flow()

    def flow_move(self, path, direction):
        try:
            lst, i = self._locate(path)
            j = i + int(direction)
            if 0 <= j < len(lst):
                lst[i], lst[j] = lst[j], lst[i]
        except Exception as e:
            self._push_log(f"ย้ายบล็อกไม่ได้: {e}", "warn")
        return self.get_flow()

    @staticmethod
    def _is_inside(src, dst):
        """dst อยู่ 'ข้างใน' บล็อก src ไหม — ใช้กันย้ายบล็อกเข้าไปในกิ่งของตัวเอง
        ซึ่งจะทำให้บล็อกนั้นหายไปทั้งก้อน (ตัดออกมาแล้วไม่มีที่ให้วางกลับ)"""
        return len(dst) > len(src) and list(dst[:len(src)]) == list(src)

    def _depth_of(self, path):
        """ความลึกของกิ่ง ณ path นี้ (เส้นหลัก = 0) — นับจากจำนวน 'then'/'else' ที่ผ่าน"""
        return sum(1 for tok in path if isinstance(tok, str))

    @staticmethod
    def _tree_depth(step, base=0):
        """ความลึกสูงสุดของกิ่งที่ซ้อนอยู่ในบล็อกนี้ (บล็อกธรรมดา = base)"""
        deepest = base
        for k in ("then", "else"):
            for child in (step.get(k) or []):
                deepest = max(deepest, Api._tree_depth(child, base + 1))
        return deepest

    def flow_move_to(self, src_path, dst_path):
        """ย้ายบล็อกจาก src_path ไปแทรกที่ dst_path — ข้ามเข้า/ออกกิ่ง then/else ได้

        dst_path ใช้กติกาเดียวกับ flow_add (ดัชนีท้าย = จุดแทรกในลิสต์นั้น) จุด '+' บนผัง
        จึงเป็นเป้าวางได้เลยโดยไม่ต้องคิดพิกัดใหม่

        เดิมย้ายได้แค่สลับกับเพื่อนบ้านในลิสต์เดียวกัน (flow_move) ถ้าจะเอาบล็อกที่ทำไว้แล้ว
        ยัดเข้าเงื่อนไข if ต้องไปแก้ JSON เอง — เมธอดนี้ทำให้ทำบนผังได้ตรง ๆ
        """
        src, dst = list(src_path or []), list(dst_path or [])
        try:
            if not src or not dst:
                raise ValueError("ต้องระบุทั้งต้นทางและปลายทาง")
            if self._is_inside(src, dst):
                raise ValueError("ย้ายบล็อกเข้าไปในกิ่งของตัวเองไม่ได้")

            src_lst, si = self._locate(src)
            if not (0 <= si < len(src_lst)):
                raise ValueError("ไม่พบบล็อกต้นทาง")

            # เช็คความลึกก่อนย้ายจริง: บล็อกที่มีกิ่งซ้อนอยู่แล้ว ถ้าย้ายเข้าไปลึกอีกอาจทะลุเพดาน
            # แล้วขั้นข้างในจะถูกข้ามตอนรัน (MAX_BRANCH_DEPTH) — กันไว้ตั้งแต่ตอนแก้ผังจะชัดกว่า
            final_depth = self._tree_depth(src_lst[si], self._depth_of(dst[:-1]))
            if final_depth > MacroRunner.MAX_BRANCH_DEPTH:
                raise ValueError(f"ย้ายแล้วกิ่งจะซ้อนเกิน {MacroRunner.MAX_BRANCH_DEPTH} ชั้น")

            step = src_lst.pop(si)
            # การดึงบล็อกออกทำให้ทุกอย่างที่อยู่ 'หลังมัน ในลิสต์เดียวกัน' เลื่อนขึ้น 1 ช่อง
            # ปลายทางอาจโดนผลนี้ได้ 2 แบบ: เป็นตำแหน่งในลิสต์เดียวกันตรง ๆ หรือ 'มุดผ่าน'
            # พี่น้องที่อยู่หลังต้นทาง (เช่น ย้าย [0] ไป [1,'then',0] -> ต้องกลายเป็น [0,'then',0])
            k = len(src) - 1
            if len(dst) > k and list(dst[:k]) == list(src[:k]) \
                    and isinstance(dst[k], int) and dst[k] > si:
                dst[k] -= 1

            dst_lst, di = self._locate(dst)
            di = max(0, min(int(di), len(dst_lst)))
            dst_lst.insert(di, step)
            return {"ok": True, "path": dst[:-1] + [di], "flow": self.get_flow()}
        except Exception as e:
            self._push_log(f"ย้ายบล็อกไม่ได้: {e}", "warn")
            return {"ok": False, "error": str(e), "flow": self.get_flow()}

    def flow_move_range(self, start_path, end_path, dst_path):
        """ย้ายบล็อกหลายอันที่ติดกัน (ช่วง start..end ในลิสต์เดียวกัน) ไปวางที่ dst_path

        สคริปต์จริงยาวหลายสิบขั้น ถ้าจะยัดเข้าเงื่อนไขต้องย้ายทีละอันคงไม่ไหว
        ช่วงต้องอยู่ 'ลิสต์เดียวกัน' เท่านั้น (พี่น้องกัน) — ตรงกับที่ผู้ใช้เห็นว่าเป็นชุดต่อเนื่อง
        และทำให้ลำดับหลังย้ายคาดเดาได้ ไม่ต้องเดาว่าบล็อกจากคนละกิ่งจะเรียงยังไง
        """
        s, e, dst = list(start_path or []), list(end_path or []), list(dst_path or [])
        try:
            if not s or not e or not dst:
                raise ValueError("ต้องระบุช่วงและปลายทาง")
            if s[:-1] != e[:-1]:
                raise ValueError("เลือกได้เฉพาะบล็อกที่อยู่ระดับเดียวกัน")
            lo, hi = sorted((int(s[-1]), int(e[-1])))
            parent = s[:-1]

            src_lst, _ = self._locate(parent + [lo])
            if not (0 <= lo <= hi < len(src_lst)):
                raise ValueError("ช่วงที่เลือกไม่ถูกต้อง")

            # ห้ามวางลงในกิ่งของบล็อกที่กำลังย้ายเอง (บล็อกจะหายทั้งชุด)
            for i in range(lo, hi + 1):
                if self._is_inside(parent + [i], dst):
                    raise ValueError("วางลงในกิ่งของบล็อกที่กำลังย้ายไม่ได้")

            base_depth = self._depth_of(dst[:-1])
            for i in range(lo, hi + 1):
                if self._tree_depth(src_lst[i], base_depth) > MacroRunner.MAX_BRANCH_DEPTH:
                    raise ValueError(f"ย้ายแล้วกิ่งจะซ้อนเกิน {MacroRunner.MAX_BRANCH_DEPTH} ชั้น")

            chunk = src_lst[lo:hi + 1]
            del src_lst[lo:hi + 1]

            # ดึงออกทีเดียวหลายอัน ปลายทางที่อยู่หลังช่วงจึงเลื่อนขึ้นเท่าจำนวนที่ดึง
            k = len(parent)
            n = len(chunk)
            if len(dst) > k and list(dst[:k]) == parent and isinstance(dst[k], int):
                if dst[k] > hi:
                    dst[k] -= n
                elif dst[k] > lo:      # ปลายทางตกอยู่กลางช่วงที่ย้าย -> วางคืนที่เดิม
                    dst[k] = lo

            dst_lst, di = self._locate(dst)
            di = max(0, min(int(di), len(dst_lst)))
            dst_lst[di:di] = chunk
            return {"ok": True, "path": dst[:-1] + [di], "count": n, "flow": self.get_flow()}
        except Exception as e_:
            self._push_log(f"ย้ายหลายบล็อกไม่ได้: {e_}", "warn")
            return {"ok": False, "error": str(e_), "flow": self.get_flow()}

    def flow_branch_targets(self, src_path):
        """จุดวางแบบ 'เข้ากิ่ง' ที่ใช้ได้กับบล็อกนี้ — เอาไว้ทำปุ่มลัดย้ายเข้า if ที่อยู่ติดกัน
        คืนรายการ if_image ที่เป็นพี่น้องกับบล็อกนี้ พร้อม path ปลายทางของกิ่ง then/else"""
        out = []
        try:
            lst, i = self._locate(list(src_path or []))
            parent = list(src_path)[:-1]
            for j, s in enumerate(lst):
                if j == i or s.get("type") != "if_image":
                    continue
                for br, label in (("then", "เจอ"), ("else", "ไม่เจอ")):
                    out.append({
                        "label": f"{s.get('desc') or 'ทางเลือก'} → กิ่ง '{label}'",
                        "path": parent + [j, br, len(s.get(br) or [])],
                        "count": len(s.get(br) or []),
                    })
        except Exception as e:
            self._push_log(f"หากิ่งปลายทางไม่ได้: {e}", "warn")
        return {"targets": out}

    def flow_get_step(self, path):
        try:
            lst, i = self._locate(path)
            return {"ok": True, "step": lst[i]}
        except Exception:
            return {"ok": False}

    # ขนาดกรอบรอบจุดกด (พิกเซลบนจอจริง) และขนาดสูงสุดของภาพย่อที่เก็บลงไฟล์สคริปต์
    # ต้องเล็กพอที่สคริปต์ 100 ขั้นจะไม่บวมจนเปิดช้า แต่ยังพอให้คนดูออกว่าเป็นปุ่มอะไร
    PREVIEW_BOX = 150
    PREVIEW_MAX = 96

    def _tap_preview_b64(self, data_uri, x, y):
        """ครอปภาพรอบ ๆ จุดที่กด + วางกากบาทตรงจุดกดจริง คืน base64 JPEG (ย่อแล้ว)

        เก็บไว้ดูอย่างเดียว ตัวรันไม่เคยอ่านฟิลด์นี้ — ต่างจาก anchor_img ที่ทำให้ตัวรัน
        'รอจนเจอภาพนั้น' ก่อนกด ถ้าเอาไปปนกันจะกลายเป็นเปลี่ยนพฤติกรรมสคริปต์โดยไม่ตั้งใจ
        """
        import base64 as _b64
        try:
            import cv2
            import numpy as np
            raw = data_uri.split(",", 1)[1] if "," in (data_uri or "") else (data_uri or "")
            img = cv2.imdecode(np.frombuffer(_b64.b64decode(raw), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return ""
            ih, iw = img.shape[:2]
            cx, cy = int(round(float(x))), int(round(float(y)))
            half = self.PREVIEW_BOX // 2
            x0, y0 = max(0, cx - half), max(0, cy - half)
            x1, y1 = min(iw, cx + half), min(ih, cy + half)
            crop = img[y0:y1, x0:x1].copy()
            if crop.size == 0:
                return ""

            # กากบาทบอกจุดกดจริงในกรอบ (เผื่อปุ่มใหญ่กว่ากรอบ จะได้รู้ว่ากดตรงไหนของปุ่ม)
            mx, my = cx - x0, cy - y0
            cv2.line(crop, (mx - 7, my), (mx + 7, my), (0, 0, 255), 1, cv2.LINE_AA)
            cv2.line(crop, (mx, my - 7), (mx, my + 7), (0, 0, 255), 1, cv2.LINE_AA)
            cv2.circle(crop, (mx, my), 3, (0, 0, 255), 1, cv2.LINE_AA)

            ch, cw = crop.shape[:2]
            scale = min(1.0, float(self.PREVIEW_MAX) / max(ch, cw))
            if scale < 1.0:
                crop = cv2.resize(crop, (max(1, int(cw * scale)), max(1, int(ch * scale))),
                                  interpolation=cv2.INTER_AREA)
            # JPEG ไม่ใช่ PNG: ภาพเกมเป็นภาพถ่าย PNG บีบไม่ลง (วัดได้ ~20 KB/ขั้น = สคริปต์
            # 105 ขั้นโต 2 MB) ภาพนี้ใช้ดูอย่างเดียว ไม่ได้เอาไปเทียบ จึงยอมให้ lossy ได้
            enc = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 72])[1]
            return _b64.b64encode(enc.tobytes()).decode("ascii")
        except Exception as e:
            self._push_log(f"เก็บภาพจุดที่กดไม่สำเร็จ: {e}", "warn")
            return ""

    def flow_set_xy(self, path, x, y, x2=None, y2=None, shot=None):
        """ตั้งพิกัดจากตัวช่วยภาพจอ (คลิกบนภาพ)

        ถ้าส่งภาพจอที่ผู้ใช้คลิก (shot) มาด้วย จะเก็บภาพย่อรอบจุดกดไว้ในฟิลด์ preview_img
        เพื่อให้ตอนกลับมาแก้สคริปต์ทีหลังดูออกว่าขั้นนี้กดปุ่มอะไร โดยไม่ต้องเปิดจอเทียบ
        """
        try:
            lst, i = self._locate(path)
            lst[i]["x"] = str(int(round(float(x))))
            lst[i]["y"] = str(int(round(float(y))))
            if x2 is not None and y2 is not None:
                lst[i]["x2"] = str(int(round(float(x2))))
                lst[i]["y2"] = str(int(round(float(y2))))
            if shot:
                prev = self._tap_preview_b64(shot, x, y)
                if prev:
                    lst[i]["preview_img"] = prev
            self._push_log(f"ตั้งพิกัดบล็อกจากภาพจอแล้ว ({lst[i]['x']},{lst[i]['y']})", "ok")
        except Exception as e:
            self._push_log(f"ตั้งพิกัดไม่ได้: {e}", "warn")
        return self.get_flow()

    def flow_clear_preview(self, path):
        """ลบภาพช่วยจำของบล็อกนี้ (ไม่กระทบการทำงาน แค่ทำให้ไฟล์เล็กลง)"""
        try:
            lst, i = self._locate(path)
            lst[i].pop("preview_img", None)
            self._push_log("ลบภาพจุดที่กดแล้ว", "ok")
        except Exception as e:
            self._push_log(f"ลบภาพไม่ได้: {e}", "warn")
        return self.get_flow()

    def flow_set_image(self, path, b64, region, mode="cond"):
        """ตั้งภาพจากการลากกรอบบนภาพจอ:
        mode='cond'   → ภาพเงื่อนไขของ if_image (anchor_img)
        mode='anchor' → ภาพ anchor gate ของ tap/swipe (รอเห็นภาพก่อนกด)
        mode='wait'   → ภาพต้นแบบของ 'รอรูป'/'เจอรูปกด' (wait_img) แทนการพิมพ์ชื่อไฟล์เอง

        'wait' ต้องเก็บคนละฟิลด์กับ anchor เพราะ step พวกนี้ยังมีด่าน anchor ของตัวเองได้
        ถ้าเขียนทับ anchor_img จะกลายเป็นเปลี่ยนความหมายเป็น 'รอภาพนี้ก่อนเริ่ม step'
        """
        try:
            lst, i = self._locate(path)
            s = lst[i]
            if mode == "find":
                s["find_img"] = b64
                if region:
                    s["find_region"] = {k: int(region[k]) for k in ("x", "y", "w", "h")}
                self._push_log("ตั้งภาพการ์ดที่จะกดรอบๆ แล้ว", "ok")
                return self.get_flow()
            if mode == "wait":
                s["wait_img"] = b64
                if region:
                    s["wait_region"] = {k: int(region[k]) for k in ("x", "y", "w", "h")}
                self._push_log("ตั้งภาพต้นแบบจากการลากกรอบแล้ว", "ok")
                return self.get_flow()
            s["anchor_img"] = b64
            if region:
                s["anchor_region"] = {k: int(region[k]) for k in ("x", "y", "w", "h")}
            if mode == "anchor":
                s.setdefault("anchor_timeout", 8.0)
                s.setdefault("anchor_threshold", 0.8)
                s.setdefault("anchor_on_fail", "pause")  # ค่าเริ่มต้นใหม่: เรียนรู้ทีละจอ แทน abort เดิม
            self._push_log("บันทึกภาพจากการลากกรอบแล้ว", "ok")
        except Exception as e:
            self._push_log(f"ตั้งภาพไม่ได้: {e}", "warn")
        return self.get_flow()

    def flow_clear_image(self, path):
        """ลบภาพ anchor/เงื่อนไขออกจากบล็อก"""
        try:
            lst, i = self._locate(path)
            for k in ("anchor_img", "anchor_region", "anchor_tap", "anchor_timeout",
                      "anchor_threshold", "anchor_on_fail", "anchor_retry_target", "anchor_retry_limit"):
                lst[i].pop(k, None)
        except Exception as e:
            self._push_log(f"ลบภาพไม่ได้: {e}", "warn")
        return self.get_flow()

    def list_siblings(self, path):
        """คืนขั้นทั้งหมดในลิสต์เดียวกับ path (ให้เลือก 'ขั้นเป้าหมาย' ตอนวนกลับ — จำกัดแค่ระดับ
        เดียวกัน ไม่ข้ามกิ่ง/ไม่ข้ามไปเส้นหลัก กันสับสนว่าวนกลับไปที่ไหนกันแน่)"""
        try:
            lst, i = self._locate(path)
            return {"ok": True, "current": i,
                    "steps": [{"idx": j, "desc": s.get("desc") or f"ขั้น {j + 1}", "type": s.get("type", "tap")}
                             for j, s in enumerate(lst)]}
        except Exception as e:
            self._push_log(f"อ่านรายการขั้นไม่ได้: {e}", "warn")
            return {"ok": False, "steps": []}

    def flow_set_anchor_opts(self, path, on_fail=None, timeout=None, anchor_tap=None,
                             retry_target=None, retry_limit=None):
        """ตั้งค่า anchor gate: ไม่เจอทำอะไร (pause/skip/tap/retry/abort) / รอสูงสุด / กดตรงที่เจอภาพ
        pause (ค่าเริ่มต้น) = หยุดจอนี้รอผู้ใช้แก้ไข เก็บจอไว้ตามที่ค้าง — ดูแผง 'จอที่รอแก้ไข'
        retry = วนกลับไปทำขั้นที่ retry_target ใหม่ (ในลิสต์เดียวกัน) สูงสุด retry_limit รอบ ก่อน fallback ไปหยุดจอ (ต้องตั้งเอง ไม่ใช่ค่าเริ่มต้น)
        abort = หยุดจอนี้เฉยๆ ไม่รอ/ไม่วน — ตั้งแต่นี้ไม่มีนโยบายไหนรีเซ็ตเกมอัตโนมัติอีกแล้ว (เดิม abort เคยรีเซ็ตเกม)"""
        try:
            lst, i = self._locate(path)
            s = lst[i]
            if on_fail in ("abort", "skip", "tap", "retry", "pause"):
                s["anchor_on_fail"] = on_fail
            if timeout is not None:
                s["anchor_timeout"] = float(timeout)
            if anchor_tap is not None:
                s["anchor_tap"] = bool(anchor_tap)
            if retry_target is not None and str(retry_target) != "":
                s["anchor_retry_target"] = int(retry_target)
            if retry_limit is not None and str(retry_limit) != "":
                s["anchor_retry_limit"] = max(1, int(retry_limit))
        except Exception as e:
            self._push_log(f"ตั้งค่า anchor ไม่ได้: {e}", "warn")
        return self.get_flow()

    def crop_image_b64(self, data_uri, x, y, w, h):
        """ครอปภาพจาก data URI ที่ผู้ใช้เห็น (ไม่แคปใหม่ กันจอเปลี่ยนระหว่างลากกรอบ)
        คืน base64 PNG ล้วน (ไม่มี prefix) ไว้เก็บเป็น anchor_img"""
        import base64 as _b64
        try:
            raw = data_uri.split(",", 1)[1] if "," in (data_uri or "") else (data_uri or "")
            data = _b64.b64decode(raw)
            import cv2
            import numpy as np
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            ih, iw = img.shape[:2]
            x = max(0, min(int(x), iw - 1)); y = max(0, min(int(y), ih - 1))
            w = max(1, min(int(w), iw - x)); h = max(1, min(int(h), ih - y))
            crop = img[y:y + h, x:x + w]
            enc = cv2.imencode(".png", crop)[1].tobytes()
            return {"ok": True, "img": _b64.b64encode(enc).decode("ascii")}
        except Exception as e:
            self._push_log(f"ครอปภาพไม่สำเร็จ: {e}", "err")
            return {"ok": False}

    def test_anchor_match(self, b64, threshold=0.8):
        """ทดสอบว่าภาพที่ลากกรอบไว้ เจอบนจอจริงตอนนี้ไหม (เหมือนปุ่มทดสอบ match แอปเดิม)"""
        import base64 as _b64
        devs = self._selected_list()
        if not devs:
            return {"ok": False, "error": "ยังไม่ได้เลือกจอ"}
        try:
            tmpl = _b64.b64decode(b64 or "")
        except Exception:
            return {"ok": False, "error": "ภาพไม่ถูกต้อง"}
        ok, data = self.controller.capture_screenshot_bytes(devs[0])
        if not ok:
            return {"ok": False, "error": "แคปจอไม่ได้"}
        found, x, y, msg = self.controller.match_template_bytes(data, tmpl, float(threshold or 0.8))
        return {"ok": True, "found": bool(found), "x": x, "y": y, "msg": str(msg)}

    def flow_test_step(self, path):
        """ทดสอบบล็อกที่เลือกในโหมดโฟลว์ (ตาม path — ใช้ได้ทั้งบล็อกในกิ่ง):
        tap/swipe = กดจริงบนจอแรกที่เลือก, if_image = เช็คว่าเจอภาพไหม"""
        import base64 as _b64
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        try:
            lst, i = self._locate(path)
            step = lst[i]
        except Exception:
            self._push_log("หาบล็อกที่เลือกไม่เจอ", "warn"); return {"ok": False}
        dev = devs[0]
        t = step.get("type", "tap")
        if t == "if_image":
            r = self.test_anchor_match(step.get("anchor_img") or "",
                                       step.get("threshold", 0.8)) if step.get("anchor_img") else None
            if r is None:
                tf = (step.get("text") or "").strip()
                tp = os.path.join(base_dir(), "templates", tf) if tf else ""
                if tp and os.path.exists(tp):
                    ok, data = self.controller.capture_screenshot_bytes(dev)
                    if ok:
                        found, x, y, _m = self.controller.find_image_in_bytes(data, tp, threshold=float(step.get("threshold", 0.8) or 0.8))
                        r = {"ok": True, "found": found, "x": x, "y": y}
                if r is None:
                    self._push_log("บล็อกทางเลือกนี้ยังไม่ได้ตั้งภาพเงื่อนไข", "warn"); return {"ok": False}
            if r.get("found"):
                self._push_log(f"[{dev}] ทดสอบเงื่อนไข: ✅ เจอ ที่ ({r.get('x')},{r.get('y')}) → ตอนรันจะเข้ากิ่ง 'เจอ'", "ok")
            else:
                self._push_log(f"[{dev}] ทดสอบเงื่อนไข: ❌ ไม่เจอ → ตอนรันจะเข้ากิ่ง 'ไม่เจอ'", "warn")
            return {"ok": True}
        if t not in ("tap", "swipe"):
            self._push_log(f"ทดสอบกดได้เฉพาะบล็อก แตะ/ปัด/ทางเลือก (บล็อกนี้เป็น {t})", "warn")
            return {"ok": False}
        try:
            x, y = int(float(step["x"])), int(float(step["y"]))
            if step.get("anchor_tap") and step.get("anchor_img") and step.get("anchor_region"):
                ok, data = self.controller.capture_screenshot_bytes(dev)
                if ok:
                    found, ax, ay, _ = self.controller.match_template_bytes(
                        data, _b64.b64decode(step["anchor_img"]),
                        float(step.get("anchor_threshold", 0.8) or 0.8))
                    if found:
                        reg = step["anchor_region"]
                        x = int(round(ax + (x - (reg["x"] + reg["w"] / 2.0))))
                        y = int(round(ay + (y - (reg["y"] + reg["h"] / 2.0))))
            if t == "swipe":
                self.controller.swipe(dev, step["x"], step["y"], step.get("x2", x), step.get("y2", y),
                                      int(float(step.get("duration", 300))))
                self._push_log(f"[{dev}] ทดสอบปัดจริงแล้ว", "warn")
            else:
                self.controller.tap(dev, x, y)
                self._push_log(f"[{dev}] ทดสอบแตะจริงที่ ({x},{y}) แล้ว", "warn")
        except Exception as e:
            self._push_log(f"ทดสอบล้มเหลว: {e}", "err")
        return {"ok": True}

    def run_from(self, root_idx):
        """ทดสอบรันตั้งแต่บล็อก (ระดับเส้นหลัก) ที่เลือกจนจบ บนจอแรกที่เลือก — ไม่ผูกบัญชี"""
        if self._running:
            self._push_log("กำลังรันอยู่แล้ว", "warn"); return {"ok": False}
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        try:
            i = max(0, int(root_idx))
            steps = self.macro_steps[i:]
        except Exception:
            return {"ok": False}
        if not steps:
            self._push_log("ไม่มีบล็อกให้รันจากจุดนี้", "warn"); return {"ok": False}
        dev = devs[0]
        self._running = True
        self._run_state = {}
        self._run_log = []

        def log_cb(text, kind="info"):
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            entry = {"ts": ts, "text": text, "kind": kind}
            self._run_log.append(entry)
            self._run_log = self._run_log[-300:]
            self._log.append(entry)
            self._log = self._log[-600:]

        def progress_cb(device, **st):
            self._run_state.setdefault(device, {}).update(st)

        runner = MacroRunner(self.controller, steps, log_cb=log_cb,
                             progress_cb=progress_cb, running_check=lambda: self._running,
                             diamond_cfg=self._load_diamond_cfg(),
                             gemini_key=self._load_gemini_key())
        runner.profile_name = self.current_profile or ""

        def worker():
            try:
                log_cb(f"▶ ทดสอบรันจากบล็อก {i + 1} บน [{dev}]", "warn")
                runner._one_and_close(dev, None)
                log_cb("ทดสอบรันจบแล้ว", "ok")
            except Exception as e:
                log_cb(f"ทดสอบรันขัดข้อง: {e}", "err")
            finally:
                self._running = False

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "offset": i}

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

    def _pair_devices_with_accounts(self, devs):
        """จับคู่จอ↔บัญชี สำหรับงานที่ต้องรู้ว่าจอไหนคือบัญชีไหน (เช่น แคปเพชรแมนนวล) — พอร์ตให้ตรง
        กับ Tkinter (capture_and_read_diamonds): ใช้บัญชีที่ 'รันล่าสุดบนจอนั้น' (accounts.last_device)
        ก่อน ถ้าไม่มีค่อย fallback เป็นบัญชีที่ติ๊กไว้ตามลำดับจอ — กันกรณีไม่เคยรันผ่านแอปนี้
        คืน list ของ (device, account|None)"""
        accts = self._accounts()
        by_device = {}
        for a in accts:
            ld = (a.get("last_device") or "").strip()
            if ld:
                by_device[ld] = a  # บัญชีล่าสุดที่รันบนจอนี้ (มี save_web_game_id ให้ push เข้าเว็บ)
        checked = [a for a in accts if a.get("checked", True)]
        pairs = []
        for i, dev in enumerate(devs):
            acc = by_device.get(dev) or (checked[i] if i < len(checked) else None)
            pairs.append((dev, acc))
        return pairs

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

    # ================= เครื่องมือช่าง (อื่นๆ) =================
    def read_diamond_manual(self):
        """อ่านเพชรบนจอที่เลือกทันที (ไม่ต้องรันสคริปต์) → เขียน export + ส่งเข้าเว็บอัตโนมัติ

        ต้องจับคู่จอ↔บัญชีก่อนอ่าน (เดิมส่ง account=None → row ไม่มี save_web_game_id → _auto_push
        กรองทิ้งหมด → 'ไม่ส่งเข้าเว็บ' ต่างจาก Tkinter ที่จับคู่บัญชีแล้วส่งทันที)"""
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False, "rows": []}
        from macro_runner import MacroRunner
        runner = MacroRunner(self.controller, [], log_cb=self._push_log,
                             diamond_cfg=self._load_diamond_cfg())
        for dev, acc in self._pair_devices_with_accounts(devs):
            runner._read_diamond(dev, acc)
        self._persist_diamonds(runner.diamond_rows, self._push_log)
        return {"ok": True, "rows": runner.diamond_rows}

    def inspect_ui(self):
        """อ่าน element บนจอเครื่องแรกที่เลือก → รายการ (ช่วยตั้ง tap_text/wait_for_text)"""
        from mumu_controller import list_ui_elements
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False, "elements": []}
        dev = devs[0]
        ok, xml = self.controller.dump_ui(dev)
        if not ok:
            self._push_log(f"[{dev}] อ่าน UI ไม่ได้: {xml}", "warn")
            return {"ok": False, "elements": [], "error": str(xml)}
        els = list_ui_elements(xml)
        out = [{"text": e["text"], "id": e["resource_id"], "desc": e["content_desc"],
                "clickable": e["clickable"],
                "cx": e["center"][0] if e["center"] else None,
                "cy": e["center"][1] if e["center"] else None} for e in els]
        self._push_log(f"[{dev}] อ่าน element ได้ {len(out)} รายการ", "ok")
        return {"ok": True, "device": dev, "elements": out}

    def setup_adb_keyboard(self):
        """ติดตั้ง(ถ้ายังไม่มี)+เปิด ADBKeyboard บนจอที่เลือก (พิมพ์ไทย/Unicode ได้)"""
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        apk = os.path.join(base_dir(), "ADBKeyboard.apk")
        n = 0
        for dev in devs:
            if not self.controller.is_adb_keyboard_installed(dev):
                if not os.path.exists(apk):
                    self._push_log(f"[{dev}] ไม่พบ ADBKeyboard.apk ข้างโปรแกรม → ข้าม", "err"); continue
                self._push_log(f"[{dev}] กำลังติดตั้ง ADBKeyboard…", "info")
                iok, out = self.controller.install_adb_keyboard(dev, apk)
                if not iok:
                    self._push_log(f"[{dev}] ติดตั้งไม่สำเร็จ: {out}", "err"); continue
            eok, out = self.controller.enable_adb_keyboard(dev)
            if eok:
                n += 1; self._push_log(f"[{dev}] เปิดคีย์บอร์ดไทยแล้ว", "ok")
            else:
                self._push_log(f"[{dev}] ตั้งคีย์บอร์ดไม่สำเร็จ: {out}", "err")
        return {"ok": True, "count": n}

    def restore_keyboard(self):
        """คืนคีย์บอร์ดเดิม (ime reset) บนจอที่เลือก"""
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        n = 0
        for dev in devs:
            ok, out = self.controller.reset_ime(dev)
            if ok:
                n += 1; self._push_log(f"[{dev}] คืนคีย์บอร์ดเดิมแล้ว", "ok")
            else:
                self._push_log(f"[{dev}] คืนคีย์บอร์ดไม่สำเร็จ: {out}", "err")
        return {"ok": True, "count": n}

    @staticmethod
    def _png_dims(data):
        """อ่านขนาดจริงจากไฟล์ PNG (IHDR) — เชื่อภาพจริง ไม่เชื่อ wm size
        (wm size อาจรายงานแนวตั้ง 540x960 ทั้งที่เกมแสดงแนวนอน 960x540 → พิกัดคลิกเพี้ยนสลับแกน)"""
        try:
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                import struct
                w, h = struct.unpack(">II", data[16:24])
                return int(w), int(h)
        except Exception:
            pass
        return 0, 0

    def screenshot_b64(self):
        """แคปจอเครื่องแรกที่เลือก คืนเป็น data URI + ขนาดจริงของภาพ (ให้ตัวช่วยหาพิกัด/ตั้งพื้นที่)"""
        import base64 as _b64
        import re as _re
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False}
        dev = devs[0]
        ok, data = self.controller.capture_screenshot_bytes(dev)
        if not ok:
            self._push_log(f"[{dev}] แคปจอไม่ได้", "err"); return {"ok": False}
        # ขนาดจากภาพจริงก่อน (พื้นที่พิกัดเดียวกับ input tap) — wm size ไว้เป็นสำรองเท่านั้น
        w, h = self._png_dims(data)
        if not w or not h:
            res = self.controller.get_resolution(dev)
            m = _re.match(r"(\d+)x(\d+)", res or "")
            w, h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        return {"ok": True, "device": dev, "w": w, "h": h,
                "img": "data:image/png;base64," + _b64.b64encode(data).decode("ascii")}

    def _load_guild_cfg(self):
        try:
            return json.load(open(os.path.join(base_dir(), "guild_ocr.json"), encoding="utf-8"))
        except Exception:
            return {"region": {"x": 0, "y": 0, "w": 0, "h": 0}}

    def get_guild_region(self):
        return (self._load_guild_cfg().get("region") or {"x": 0, "y": 0, "w": 0, "h": 0})

    def save_guild_region(self, x, y, w, h):
        cfg = self._load_guild_cfg()
        cfg["region"] = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        try:
            with open(os.path.join(base_dir(), "guild_ocr.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self._push_log(f"ตั้งพื้นที่ชื่อชมรม {int(w)}x{int(h)} แล้ว", "ok")
        except Exception as e:
            self._push_log(f"บันทึกพื้นที่ชื่อไม่ได้: {e}", "err")
        return {"ok": True}

    def grab_guild_members(self):
        """เลื่อนหน้าสมาชิกชมรม + แคปทีละหน้า → OCR → รายชื่อ (ตัดซ้ำ)"""
        import re as _re
        from mumu_controller import (find_tesseract, guild_ocr_langs, ocr_text_tesseract,
                                     extract_guild_member_names, png_similarity)
        devs = self._selected_list()
        if not devs:
            self._push_log("ยังไม่ได้เลือกจอ", "warn"); return {"ok": False, "names": []}
        dev = devs[0]
        if not find_tesseract():
            self._push_log("ไม่พบ Tesseract OCR → ดึงรายชื่อไม่ได้", "err")
            return {"ok": False, "names": [], "error": "no_tesseract"}
        region = (self._load_guild_cfg().get("region") or {})
        has_region = int(region.get("w", 0)) > 0 and int(region.get("h", 0)) > 0
        res = self.controller.get_resolution(dev)
        m = _re.match(r"(\d+)x(\d+)", res or "")
        w, h = (int(m.group(1)), int(m.group(2))) if m else (960, 540)
        sx = int(w * 0.6); y1, y2 = int(h * 0.82), int(h * 0.30)
        self._push_log(f"[{dev}] เริ่มดึงรายชื่อสมาชิกชมรม (จอ {w}x{h})", "warn")
        shots, prev = [], None
        for i in range(40):
            ok, data = self.controller.capture_screenshot_bytes(dev)
            if ok:
                if prev is not None and png_similarity(prev, data) >= 0.992:
                    self._push_log(f"[{dev}] ถึงล่างสุด หยุดที่ {len(shots)} หน้า", "ok"); break
                shots.append(data); prev = data
            self.controller.swipe(dev, sx, y1, sx, y2, duration=700)
            time.sleep(0.9)
        if not shots:
            self._push_log(f"[{dev}] แคปรายชื่อไม่ได้", "err"); return {"ok": False, "names": []}
        lang = guild_ocr_langs(); crop = region if has_region else None
        scale = 3 if has_region else 2
        texts = []
        for i, data in enumerate(shots):
            ok, txt, _ = ocr_text_tesseract(data, region=crop, lang=lang, psm=6, scale=scale)
            if ok and txt:
                texts.append(txt)
        names = extract_guild_member_names("\n".join(texts))
        self._push_log(f"[{dev}] OCR ได้ {len(names)} ชื่อ (ตัดซ้ำ) จาก {len(shots)} หน้า", "ok")
        return {"ok": True, "names": names, "device": dev, "region_used": has_region}

    # ---------- Export/Import แพ็กเกจโปรไฟล์ (.mmpow zip) ----------
    def export_profile(self):
        import zipfile
        from script_sets import safe_set_slug
        w = self._win()
        name = self.current_profile
        fp = self.profiles.get(name)
        if not fp or not os.path.exists(fp):
            self._push_log("ยังไม่มีโปรไฟล์ที่โหลด/บันทึก — เลือกหรือบันทึกก่อน", "warn")
            return {"ok": False}
        try:
            profile_data = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            self._push_log(f"อ่านไฟล์โปรไฟล์ไม่ได้: {e}", "err"); return {"ok": False}
        ref_imgs, ref_sets = set(), set()
        ssdir = os.path.join(base_dir(), "script_sets")

        def scan(steps):
            for s in steps:
                t = s.get("type", "")
                if t in ("detect_image", "wait_for_image", "if_image") and s.get("text", "").strip():
                    ref_imgs.add(s["text"].strip())
                elif t == "clear_ads_loop" and s.get("text", "").strip():
                    for part in s["text"].split("|"):
                        for img in part.split(","):
                            if img.strip():
                                ref_imgs.add(img.strip())
                elif t == "run_set":
                    sn = (s.get("set") or s.get("text") or "").strip()
                    if sn and sn not in ref_sets:
                        ref_sets.add(sn)
                        sf = os.path.join(ssdir, f"{safe_set_slug(sn)}.json")
                        if os.path.exists(sf):
                            try:
                                scan(json.load(open(sf, encoding="utf-8")).get("steps", []))
                            except Exception:
                                pass
                # กิ่งของบล็อกทางเลือก — ไล่เก็บรูป/ชุดคำสั่งข้างในด้วย
                for k in ("then", "else"):
                    if s.get(k):
                        scan(s[k])
        scan(profile_data.get("steps", []))
        save_path = None
        try:
            if w:
                save_path = w.create_file_dialog(
                    webview.SAVE_DIALOG, save_filename=f"{name.lower().replace(' ', '_')}_package.mmpow",
                    file_types=("MuMupow Package (*.mmpow)", "Zip (*.zip)"))
        except Exception as e:
            self._push_log(f"เปิดหน้าต่างบันทึกไม่ได้: {e}", "err"); return {"ok": False}
        if not save_path:
            return {"ok": False}
        if isinstance(save_path, (list, tuple)):
            save_path = save_path[0]
        try:
            tdir = os.path.join(base_dir(), "templates")
            manifest = {"profile_name": name, "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "profile_file": os.path.basename(fp),
                        "script_sets": list(ref_sets), "templates": list(ref_imgs)}
            with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                z.write(fp, "profile.json")
                for sn in ref_sets:
                    sf = os.path.join(ssdir, f"{safe_set_slug(sn)}.json")
                    if os.path.exists(sf):
                        z.write(sf, f"script_sets/{os.path.basename(sf)}")
                for img in ref_imgs:
                    ip = os.path.join(tdir, img)
                    if os.path.exists(ip):
                        z.write(ip, f"templates/{img}")
            self._push_log(f"ส่งออกแพ็กเกจ '{name}' → {os.path.basename(save_path)}", "ok")
        except Exception as e:
            self._push_log(f"ส่งออกไม่สำเร็จ: {e}", "err"); return {"ok": False}
        return {"ok": True}

    def import_profile(self):
        import zipfile
        w = self._win()
        files = None
        try:
            if w:
                files = w.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                             file_types=("MuMupow Package (*.mmpow)", "Zip (*.zip)",
                                                         "All files (*.*)"))
        except Exception as e:
            self._push_log(f"เปิดหน้าต่างเลือกไฟล์ไม่ได้: {e}", "err"); return {"ok": False}
        if not files:
            return {"ok": False}
        path = files[0]
        macros_dir = os.path.join(base_dir(), "macros")
        ssdir = os.path.join(base_dir(), "script_sets")
        tdir = os.path.join(base_dir(), "templates")
        os.makedirs(ssdir, exist_ok=True); os.makedirs(tdir, exist_ok=True)
        try:
            with zipfile.ZipFile(path, "r") as z:
                names = z.namelist()
                if "manifest.json" not in names or "profile.json" not in names:
                    self._push_log("ไฟล์แพ็กเกจไม่ถูกต้อง", "err"); return {"ok": False}
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
                pname = manifest.get("profile_name", "Imported Profile")
                ti = si = 0
                for fn in names:
                    if fn.startswith("templates/") and not fn.endswith("/"):
                        with open(os.path.join(tdir, os.path.basename(fn)), "wb") as f:
                            f.write(z.read(fn)); ti += 1
                    elif fn.startswith("script_sets/") and not fn.endswith("/"):
                        with open(os.path.join(ssdir, os.path.basename(fn)), "wb") as f:
                            f.write(z.read(fn)); si += 1
                pfile = manifest.get("profile_file", f"{pname.lower().replace(' ', '_')}.json")
                with open(os.path.join(macros_dir, pfile), "wb") as f:
                    f.write(z.read("profile.json"))
            self._load_profiles(); self._load_profile_steps(pname)
            self._push_log(f"นำเข้าแพ็กเกจ '{pname}' (รูป {ti}, ชุดคำสั่ง {si})", "ok")
        except Exception as e:
            self._push_log(f"นำเข้าไม่สำเร็จ: {e}", "err"); return {"ok": False}
        return {"ok": True, "profile": pname}

    # ---------- จัดการชุดคำสั่งย่อย (Script Sets) ----------
    def list_script_sets(self):
        import glob as _glob
        from script_sets import load_script_set
        out = []
        for f in _glob.glob(os.path.join(base_dir(), "script_sets", "*.json")):
            try:
                d = load_script_set(f)
                out.append({"name": d["name"], "count": len(d["steps"])})
            except Exception:
                pass
        return {"sets": sorted(out, key=lambda s: s["name"])}

    def save_current_as_set(self, name):
        name = (name or "").strip()
        if not name:
            self._push_log("ต้องระบุชื่อชุดคำสั่ง", "warn"); return self.list_script_sets()
        if not self.macro_steps:
            self._push_log("ยังไม่มีขั้นตอนให้บันทึกเป็นชุด", "warn"); return self.list_script_sets()
        from script_sets import save_script_set, safe_set_slug
        path = os.path.join(base_dir(), "script_sets", f"{safe_set_slug(name)}.json")
        try:
            save_script_set(path, name, self.macro_steps)
            self._push_log(f"บันทึกชุดคำสั่ง '{name}' ({len(self.macro_steps)} ขั้น)", "ok")
        except Exception as e:
            self._push_log(f"บันทึกชุดคำสั่งล้มเหลว: {e}", "err")
        return self.list_script_sets()

    def delete_script_set(self, name):
        from script_sets import safe_set_slug
        path = os.path.join(base_dir(), "script_sets", f"{safe_set_slug(name)}.json")
        if os.path.exists(path):
            try:
                os.remove(path); self._push_log(f"ลบชุดคำสั่ง '{name}'", "warn")
            except Exception as e:
                self._push_log(f"ลบชุดคำสั่งล้มเหลว: {e}", "err")
        return self.list_script_sets()

    def get_script_set(self, name):
        from script_sets import load_script_set, safe_set_slug
        path = os.path.join(base_dir(), "script_sets", f"{safe_set_slug(name)}.json")
        if not os.path.exists(path):
            self._push_log(f"ไม่พบชุดคำสั่ง '{name}'", "warn")
            return {"ok": False, "name": name, "steps": []}
        try:
            d = load_script_set(path)
            return {"ok": True, "name": d["name"], "steps": d["steps"]}
        except Exception as e:
            self._push_log(f"อ่านชุดคำสั่ง '{name}' ไม่ได้: {e}", "err")
            return {"ok": False, "name": name, "steps": []}

    def load_set_to_editor(self, name):
        res = self.get_script_set(name)
        if not res["ok"]:
            return res
        self.macro_steps = res["steps"]
        self._push_log(f"โหลดชุดคำสั่ง '{name}' ({len(self.macro_steps)} ขั้น) เข้าสู่ Editor", "ok")
        return {"ok": True, "name": name, "steps": self.macro_steps, "state": self.get_state()}

    def save_script_set_steps(self, name, steps=None):
        name = (name or "").strip()
        if not name:
            self._push_log("ต้องระบุชื่อชุดคำสั่ง", "warn"); return {"ok": False}
        target_steps = steps if isinstance(steps, list) else self.macro_steps
        if not target_steps:
            self._push_log("ไม่มีขั้นตอนให้บันทึก", "warn"); return {"ok": False}
        from script_sets import save_script_set, safe_set_slug
        path = os.path.join(base_dir(), "script_sets", f"{safe_set_slug(name)}.json")
        try:
            save_script_set(path, name, target_steps)
            self._push_log(f"บันทึกชุดคำสั่ง '{name}' ({len(target_steps)} ขั้น) สำเร็จ", "ok")
            return {"ok": True, "name": name, "count": len(target_steps), "sets": self.list_script_sets()["sets"]}
        except Exception as e:
            self._push_log(f"บันทึกชุดคำสั่ง '{name}' ล้มเหลว: {e}", "err")
            return {"ok": False}

    # ---------- พรีเซ็ตพิกัด / สร้างเร็ว ----------
    def get_presets(self):
        try:
            d = json.load(open(os.path.join(base_dir(), "presets.json"), encoding="utf-8"))
            return {"presets": d.get("presets", [])}
        except Exception:
            return {"presets": []}

    def _preset_step(self, preset_name):
        """สร้าง step 'แตะ' จากพรีเซ็ตพิกัด — คืน None ถ้าไม่พบชื่อนั้น"""
        p = next((x for x in self.get_presets()["presets"] if x.get("name") == preset_name), None)
        if not p:
            self._push_log(f"ไม่พบพรีเซ็ต '{preset_name}'", "warn")
            return None
        from quick_builder import build_tap_step_from_preset
        return build_tap_step_from_preset(p)

    def quick_add(self, preset_name):
        """เพิ่มขั้นจากพรีเซ็ตต่อท้ายเส้นหลัก (ใช้จากมุมมองลิสต์)"""
        step = self._preset_step(preset_name)
        if step is None:
            return self.get_steps()
        self.macro_steps.append(step)
        self._push_log(f"เพิ่มขั้นจากพรีเซ็ต '{preset_name}'", "ok")
        return self.get_steps()

    def flow_add_set(self, path, set_name, as_block=False, block_home="", block_retries=""):
        """แทรกขั้น 'ใช้ชุดคำสั่งย่อย' (run_set) ที่ตำแหน่ง path บนผัง

        เดิมต้องเพิ่มบล็อก run_set เปล่าแล้วพิมพ์ชื่อชุดเองให้ตรงเป๊ะ พิมพ์ผิดตัวเดียว
        ตอนรันจะเจอ 'ไม่พบชุดคำสั่ง' — เลือกจากรายการชื่อจริงจึงพลาดไม่ได้

        as_block=True → ทำเป็น 'บล็อกกันพัง': ถ้าชุดนี้พัง ให้เล่นชุด block_home
        แล้วลองใหม่ (ตามจำนวน block_retries) ซึ่งเป็นวิธีที่สคริปต์จริงใช้อยู่แล้ว
        """
        name = str(set_name or "").strip()
        if not name:
            return {"ok": False, "error": "ยังไม่ได้เลือกชุดคำสั่ง", "flow": self.get_flow()}
        known = {s["name"] for s in self.list_script_sets()["sets"]}
        if name not in known:
            self._push_log(f"ไม่พบชุดคำสั่ง '{name}'", "warn")
            return {"ok": False, "error": f"ไม่พบชุดคำสั่ง '{name}'", "flow": self.get_flow()}

        step = {"type": "run_set", "set": name, "desc": f"ใช้ชุด: {name}"}
        if as_block:
            step["block_on_fail"] = "home_retry"
            step["desc"] = f"บล็อก: {name}"
            home = str(block_home or "").strip()
            if home:
                step["block_home"] = home
            try:
                r = int(block_retries)
                if r >= 0:
                    step["block_retries"] = r
            except (TypeError, ValueError):
                pass                              # เว้นว่าง = ใช้ค่าเริ่มต้นของตัวรัน (3)
        try:
            lst, i = self._locate(list(path or []))
            i = max(0, min(int(i), len(lst)))
            lst.insert(i, step)
            self._push_log(f"แทรกชุดคำสั่ง '{name}' แล้ว", "ok")
            return {"ok": True, "path": list(path)[:-1] + [i], "flow": self.get_flow()}
        except Exception as e:
            self._push_log(f"แทรกชุดคำสั่งไม่ได้: {e}", "warn")
            return {"ok": False, "error": str(e), "flow": self.get_flow()}

    def flow_add_preset(self, path, preset_name):
        """แทรกขั้นจากพรีเซ็ตที่ตำแหน่ง path บนผัง — วางในกิ่ง then/else ได้ด้วย

        เดิมพรีเซ็ตต่อท้ายเส้นหลักได้อย่างเดียว (quick_add ใช้ append) ถ้าอยากได้ตรงกลาง
        หรือในเงื่อนไข ต้องไปแก้ไฟล์ JSON เอง — เมธอดนี้ทำให้วางจากบนผังได้ตรง ๆ
        """
        step = self._preset_step(preset_name)
        if step is None:
            return {"ok": False, "flow": self.get_flow()}
        try:
            lst, i = self._locate(list(path or []))
            i = max(0, min(int(i), len(lst)))
            lst.insert(i, step)
            self._push_log(f"แทรกขั้นจากพรีเซ็ต '{preset_name}' แล้ว", "ok")
            return {"ok": True, "path": list(path)[:-1] + [i], "flow": self.get_flow()}
        except Exception as e:
            self._push_log(f"แทรกพรีเซ็ตไม่ได้: {e}", "warn")
            return {"ok": False, "error": str(e), "flow": self.get_flow()}

    # ---------- ตั้งค่าระบบอ่านเพชร (diamond_ocr.json) ----------
    def _save_diamond_cfg(self, cfg):
        with open(os.path.join(base_dir(), "diamond_ocr.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    def get_diamond_settings(self):
        cfg = self._load_diamond_cfg()
        return {
            "region": cfg.get("region") or {"x": 0, "y": 0, "w": 0, "h": 0},
            "web_base_url": cfg.get("web_base_url", ""),
            "auto_push": bool(cfg.get("auto_push", True)),
        }

    def save_diamond_region(self, x, y, w, h):
        cfg = self._load_diamond_cfg()
        cfg["region"] = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        try:
            self._save_diamond_cfg(cfg)
            self._push_log(f"บันทึกพื้นที่ตัวเลขเพชร {int(w)}x{int(h)} แล้ว", "ok")
        except Exception as e:
            self._push_log(f"บันทึกพื้นที่ไม่ได้: {e}", "err")
        return self.get_diamond_settings()

    def save_diamond_opts(self, web_base_url=None, auto_push=None):
        cfg = self._load_diamond_cfg()
        if web_base_url is not None:
            cfg["web_base_url"] = str(web_base_url).strip()
        if auto_push is not None:
            cfg["auto_push"] = bool(auto_push)
        try:
            self._save_diamond_cfg(cfg)
            self._push_log("บันทึกตั้งค่าระบบเพชรแล้ว", "ok")
        except Exception as e:
            self._push_log(f"บันทึกตั้งค่าเพชรไม่ได้: {e}", "err")
        return self.get_diamond_settings()

    # ---------- ตั้งค่ารีเซ็ตเกมเมื่อบัญชีติดปัญหา (game_reset.json) ----------
    def get_reset_settings(self):
        cfg = self._load_reset_cfg()
        return {"enabled": bool(cfg.get("enabled", True)),
                "package": cfg.get("package", ""),
                "boot_wait": float(cfg.get("boot_wait", 10.0) or 10.0),
                "steps": len(cfg.get("open_login_steps", []) or [])}

    def save_reset_settings(self, enabled, package, boot_wait):
        cfg = self._load_reset_cfg()
        cfg["enabled"] = bool(enabled)
        cfg["package"] = (package or "").strip()
        try:
            cfg["boot_wait"] = float(boot_wait)
        except (TypeError, ValueError):
            pass
        try:
            with open(os.path.join(base_dir(), "game_reset.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self._push_log("บันทึกตั้งค่ารีเซ็ตเกมแล้ว", "ok")
        except Exception as e:
            self._push_log(f"บันทึกตั้งค่ารีเซ็ตไม่ได้: {e}", "err")
        return self.get_reset_settings()

    # ---------- รายงานจุดที่ติด (error_reports/) ----------
    def list_error_reports(self, limit=30):
        path = os.path.join(base_dir(), "error_reports", "report.jsonl")
        rows = []
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            for ln in lines[-int(limit):]:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    pass
        except FileNotFoundError:
            pass
        except Exception as e:
            self._push_log(f"อ่านรายงานจุดที่ติดไม่ได้: {e}", "warn")
        rows.reverse()  # ล่าสุดขึ้นก่อน
        return {"reports": rows}

    def error_image_b64(self, img_path):
        """อ่านภาพจุดที่ติดเป็น data URI — จำกัดเฉพาะไฟล์ใต้ error_reports/ เท่านั้น"""
        import base64 as _b64
        root = os.path.abspath(os.path.join(base_dir(), "error_reports"))
        p = os.path.abspath(img_path or "")
        if not p.startswith(root) or not os.path.exists(p):
            return {"ok": False}
        try:
            with open(p, "rb") as f:
                return {"ok": True, "img": "data:image/png;base64," + _b64.b64encode(f.read()).decode("ascii")}
        except Exception:
            return {"ok": False}

    def open_error_folder(self):
        try:
            d = os.path.join(base_dir(), "error_reports")
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
        except Exception as e:
            self._push_log(f"เปิดโฟลเดอร์ไม่ได้: {e}", "warn")
        return {"ok": True}

    # ---------- จัดการพรีเซ็ตพิกัด (presets.json) ----------
    def _save_presets(self, presets):
        with open(os.path.join(base_dir(), "presets.json"), "w", encoding="utf-8") as f:
            json.dump({"presets": presets}, f, ensure_ascii=False, indent=2)

    def add_preset(self, name, x, y):
        name = (name or "").strip()
        if not name:
            self._push_log("ต้องตั้งชื่อพรีเซ็ต", "warn"); return self.get_presets()
        ps = self.get_presets()["presets"]
        ps = [p for p in ps if p.get("name") != name]  # ชื่อซ้ำ = เขียนทับ
        try:
            ps.append({"name": name, "x": float(x), "y": float(y)})
            self._save_presets(ps)
            self._push_log(f"บันทึกพรีเซ็ต '{name}' ({int(float(x))},{int(float(y))})", "ok")
        except Exception as e:
            self._push_log(f"บันทึกพรีเซ็ตไม่ได้: {e}", "err")
        return self.get_presets()

    def delete_preset(self, name):
        ps = [p for p in self.get_presets()["presets"] if p.get("name") != name]
        try:
            self._save_presets(ps)
            self._push_log(f"ลบพรีเซ็ต '{name}'", "warn")
        except Exception as e:
            self._push_log(f"ลบพรีเซ็ตไม่ได้: {e}", "err")
        return self.get_presets()

    # ---------- ส่งเพชรขึ้นเว็บ Save Web Game ----------
    def match_web_accounts(self):
        """ดึงบัญชีจากเว็บมาจับคู่ชื่อกับบัญชีในเครื่อง (เติม save_web_game_id ให้อัตโนมัติ)"""
        from save_web_game_import import fetch_web_accounts, match_accounts_to_web
        cfg = self._load_diamond_cfg()
        url = (cfg.get("web_base_url") or "").strip()
        if not url:
            self._push_log("ยังไม่ได้ตั้ง URL เว็บ (ในการ์ดระบบเพชร)", "warn")
            return {"ok": False, "matched": 0}
        try:
            web = fetch_web_accounts(url)
        except Exception as e:
            self._push_log(f"ดึงบัญชีจากเว็บไม่ได้: {e}", "err")
            return {"ok": False, "matched": 0}
        accts = self._accounts()
        pairs = match_accounts_to_web(accts, web)
        n = 0
        for p in pairs:
            em = (p.get("email") or "").strip().lower()
            wid = str(p.get("web_id") or "").strip()
            if not wid:
                continue
            for a in accts:
                if (a.get("email") or "").strip().lower() == em:
                    a["save_web_game_id"] = wid
                    n += 1
                    break
        if n:
            self._save_accounts(accts)
        self._push_log(f"จับคู่บัญชีกับเว็บได้ {n} รหัส (จากเว็บ {len(web)} บัญชี)", "ok" if n else "warn")
        return {"ok": True, "matched": n, "web_total": len(web)}

    def push_diamonds_web(self):
        """ส่งจำนวนเพชรล่าสุดของบัญชีที่มี save_web_game_id ขึ้นเว็บ"""
        from save_web_game_import import push_diamonds_to_web
        cfg = self._load_diamond_cfg()
        url = (cfg.get("web_base_url") or "").strip()
        if not url:
            self._push_log("ยังไม่ได้ตั้ง URL เว็บ (ในการ์ดระบบเพชร)", "warn")
            return {"ok": False}
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        updates = []
        for a in self._accounts():
            wid = (a.get("save_web_game_id") or "").strip()
            if wid and a.get("diamonds") is not None:
                updates.append({"id": wid, "diamonds": a["diamonds"], "lastFarmDate": today})
        if not updates:
            self._push_log("ไม่มีบัญชีที่มีทั้ง id เว็บและจำนวนเพชร — กด 'จับคู่ชื่อ' และอ่านเพชรก่อน", "warn")
            return {"ok": False}
        self._push_log(f"กำลังส่งเพชร {len(updates)} บัญชี → {url}", "info")
        try:
            _results, stats = push_diamonds_to_web(url, updates)
            self._push_log(f"ส่งเพชรขึ้นเว็บ: สำเร็จ {stats['sent']} · พลาด {stats['failed']}",
                           "ok" if not stats["failed"] else "warn")
            return {"ok": True, "sent": stats["sent"], "failed": stats["failed"]}
        except Exception as e:
            self._push_log(f"ส่งเพชรขึ้นเว็บพลาด: {e}", "err")
            return {"ok": False}

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
