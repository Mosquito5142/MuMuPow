"""ตัวรันมาโครแบบไม่พึ่ง GUI — ใช้ได้ทั้งแอป Tkinter เดิมและแอปเว็บ (pywebview)
พอร์ตตรรกะหลักจาก MuMuGUI.execute_device_macro/_step_* มาไว้ที่เดียว ไม่แตะ gui.py

ใช้ callback ส่งออก: log(text, kind) และ progress(device, **state)
และ running_check() คืน False เมื่อสั่งหยุด — worker จะเลิกเอง
"""
import os
import sys
import copy
import time
import base64
import queue
import random
import json
import threading
import datetime
from concurrent.futures import ThreadPoolExecutor

from mumu_controller import (find_tesseract,
                             available_tesseract_langs, ocr_text_tesseract,
                             find_highlighted_stage, find_swipe_glow, in_match_autoplay,
                             ocr_find_button, png_similarity, gemini_tap_suggestion,
                             find_element_center, find_yellow_frame)


DEFAULT_SWIPE_DURATION = 300


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def account_display_name(acc):
    """ชื่อที่ใช้ 'แสดงผล' ในล็อก/รายงาน — ต้องตรงกับ gui.py's account_display_name เป๊ะ:
    save_web_game_title (ชื่อดิบจากตอน import เว็บ ไม่โดนแก้ทับ) ก่อนเสมอ แล้วค่อย title/ingamename/name/email"""
    if not acc:
        return "-"
    return (acc.get("save_web_game_title") or acc.get("title") or acc.get("ingamename")
            or acc.get("name") or acc.get("email") or "-")


def substitute_account(text, account):
    """แทน {EMAIL}/{PASSWORD}/{NAME} ด้วยข้อมูลบัญชีรอบนี้"""
    if not account:
        return text
    return (str(text)
            .replace("{EMAIL}", account.get("email", "") or "")
            .replace("{PASSWORD}", account.get("password", "") or "")
            .replace("{NAME}", account.get("name", "") or account.get("ingamename", "") or ""))


def templates_dir():
    return os.path.join(base_dir(), "templates")


def parse_ui_query(query):
    """แยกคำค้น element: ขึ้นต้น 'id:' = ค้นจาก resource-id, ไม่งั้นค้นจาก text"""
    query = (query or "").strip()
    if query.lower().startswith("id:"):
        return None, query[3:].strip()
    return query, None


# ---------- ดึง OTP จากอีเมล (พอร์ตจาก MuMuGUI.fetch_otp_* — ไม่พึ่ง GUI) ----------
def _fetch_otp_via_readmail_api(log, mail_address, refresh_token, client_id, pattern_str):
    """ดึงอีเมลผ่าน API read-mail.me ด้วย OAuth2 token"""
    import urllib.request
    import re
    url = "https://read-mail.me/get_data.php"
    payload = {"email": mail_address, "refresh_token": refresh_token,
               "client_id": client_id, "api_type": "graph_api"}
    headers = {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRF-Token': 'rm_8Xk2pQwZ9vNjL5hTdYcA3sE7uBfM4oR',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                     headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=20) as response:
            res = json.loads(response.read().decode('utf-8'))
        if res.get("status") and "messages" in res:
            for msg in res["messages"][:5]:
                body = msg.get("_body") or msg.get("message") or ""
                m = re.search(pattern_str, body)
                if m:
                    log(f"[{mail_address}] [API] เจอเมล '{msg.get('subject','')}' → ดึง OTP สำเร็จ", "ok")
                    return m.group(0)
            log(f"[{mail_address}] [API] สแกนเมลแล้วไม่พบ OTP ตามแพทเทิร์น '{pattern_str}'", "warn")
        else:
            log(f"[{mail_address}] [API] ดึงข้อมูลไม่สำเร็จ: {res.get('error') or 'ไม่พบข้อความ'}", "warn")
    except Exception as e:
        log(f"[{mail_address}] [API] ผิดพลาด: {e}", "err")
    return None


def fetch_otp_from_mail(log, mail_address, mail_password, pattern_str=None,
                        refresh_token="", client_id=""):
    """ดึง OTP ล่าสุด: ลอง API (ถ้ามี token) ก่อน แล้ว fallback เป็น IMAP (Outlook)"""
    import imaplib
    import email
    import re
    from email.header import decode_header

    if not pattern_str or pattern_str.strip() in ["", "{EMAIL}", "{PASSWORD}"]:
        pattern_str = r'\b\d{6}\b'

    if refresh_token and client_id:
        log(f"[{mail_address}] พบโทเคน OAuth2 → ดึงผ่าน API read-mail.me", "info")
        code = _fetch_otp_via_readmail_api(log, mail_address, refresh_token, client_id, pattern_str)
        if code:
            return code
        log(f"[{mail_address}] API ล้มเหลว → ลองผ่าน IMAP สำรอง", "warn")

    try:
        mail = imaplib.IMAP4_SSL("outlook.office365.com")
        mail.login(mail_address, mail_password)
        status, messages = mail.select("inbox")
        if status != "OK":
            log(f"[{mail_address}] เปิดกล่อง Inbox ไม่ได้", "err")
            return None
        num = int(messages[0])
        if num == 0:
            log(f"[{mail_address}] ไม่มีอีเมลในกล่อง", "warn")
            return None
        for seq in range(num, max(0, num - 5), -1):
            status, data = mail.fetch(str(seq), "(RFC822)")
            if status != "OK" or not data:
                continue
            msg = email.message_from_bytes(data[0][1])
            try:
                sub_dec, enc = decode_header(msg.get("Subject", ""))[0]
                subject = sub_dec.decode(enc or "utf-8", errors="ignore") if isinstance(sub_dec, bytes) else sub_dec
            except Exception:
                subject = str(msg.get("Subject", ""))
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    cd = str(part.get("Content-Disposition"))
                    if ct in ["text/plain", "text/html"] and "attachment" not in cd:
                        try:
                            body += part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", errors="ignore")
                        except Exception:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode(
                        msg.get_content_charset() or "utf-8", errors="ignore")
                except Exception:
                    pass
            m = re.search(pattern_str, body)
            if m:
                log(f"[{mail_address}] เจอเมล '{subject}' → ดึง OTP สำเร็จ", "ok")
                mail.logout()
                return m.group(0)
        mail.logout()
        log(f"[{mail_address}] สแกน 5 เมลล่าสุดแล้วไม่พบ OTP '{pattern_str}'", "warn")
    except Exception as e:
        log(f"[{mail_address}] เชื่อมต่อกล่องเมลผิดพลาด: {e}", "err")
    return None


# ---------- ส่งปุ่มคีย์บอร์ดจริงเข้าหน้าต่าง MuMu (พอร์ตจาก execute_keyboard_input) ----------
_VK_CODES = {
    "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
    "space": 0x20, "enter": 0x0D, "escape": 0x1B,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f": 0x46, "g": 0x47, "h": 0x48, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "z": 0x5A, "x": 0x58, "c": 0x43, "v": 0x56, "b": 0x42, "n": 0x4E, "m": 0x4D,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
    "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def send_keyboard_input(log, device, ordered_devices, key_name, action):
    """โพสต์ WM_KEYDOWN/UP เข้าหน้าต่าง MuMu ที่ตรงกับ device (จับคู่ตามลำดับ)"""
    import ctypes
    user32 = ctypes.windll.user32
    found = []

    def foreach_window(hwnd, _l):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buff, n + 1)
            title = buff.value
            if any(k in title.lower() for k in ["mumu player", "nemu", "มูมู่"]):
                found.append((hwnd, title))
        return True

    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(proc(foreach_window), 0)
    if not found:
        log("ไม่พบหน้าต่าง Emulator บน Windows เพื่อส่งปุ่มกด", "warn")
        return

    sorted_devs = sorted(d for d in (ordered_devices or []) if d)
    sorted_wins = sorted(found, key=lambda w: w[1])
    target = None
    for i, dev in enumerate(sorted_devs):
        if dev == device and i < len(sorted_wins):
            target = sorted_wins[i][0]
            break
    if not target:
        target = sorted_wins[0][0]

    vk = _VK_CODES.get(key_name)
    if not vk:
        if len(key_name) == 1:
            vk = ord(key_name.upper())
        else:
            log(f"ไม่รู้จักปุ่ม '{key_name}'", "warn")
            return

    child = []

    def enum_child(hwnd, _l):
        child.append(hwnd)
        return True

    cproc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumChildWindows(target, cproc(enum_child), 0)
    hwnds = [target] + child

    WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
    post = user32.PostMessageW
    if action == "down":
        for h in hwnds:
            post(h, WM_KEYDOWN, vk, 0)
    elif action == "up":
        for h in hwnds:
            post(h, WM_KEYUP, vk, 0)
    else:  # press
        for h in hwnds:
            post(h, WM_KEYDOWN, vk, 0)
        time.sleep(0.05)
        for h in hwnds:
            post(h, WM_KEYUP, vk, 0)


class MacroRunner:
    # ชนิด step ที่ตัวรันใหม่ยังไม่รองรับ (จะ log แล้วข้าม ไม่ให้พังทั้งรอบ)
    # หมายเหตุ: run_set ถูกขยายทิ้งไปตั้งแต่ __init__ แล้ว จึงไม่โผล่ถึง _dispatch
    _UNSUPPORTED = {"story_auto"}

    def __init__(self, controller, steps, log_cb=None, progress_cb=None,
                 running_check=None, anchor_poll=2.0, reset_cfg=None, diamond_cfg=None):
        self.controller = controller
        self.log = log_cb or (lambda t, k="info": None)
        self.steps = self._expand_sets(steps or [])
        self.progress = progress_cb or (lambda dev, **kw: None)
        self.running = running_check or (lambda: True)
        # จำกัดช่วง 0.1–10 วิ เหมือนฝั่ง Tkinter (gui._update_anchor_poll) — สำคัญเรื่องความปลอดภัย:
        # ค่าติดลบทำให้ลูปหน่วงใน _wait_anchor ไม่ทำงานเลย กลายเป็น busy loop แคปจอรัวไม่หยุด
        # (วัดได้ ~6 ล้านครั้ง/วิ) กิน CPU + ADB จนจอค้างทั้งเครื่อง; ค่ามากเกินก็ทำให้เช็คแทบไม่ทัน timeout
        self.anchor_poll = min(10.0, max(0.1, float(anchor_poll or 2.0)))
        self.reset_cfg = reset_cfg or {}
        self.diamond_cfg = diamond_cfg or {}
        self.diamond_rows = []          # ผลอ่านเพชร (Api เอาไปเขียนไฟล์/บัญชีตอนจบรัน)
        self.account_results = []       # ผลรายบัญชี (status/error/device) — เขียน last_status ตอนจบรัน
        self.profile_name = ""          # ชื่อสคริปต์ (ใส่ในรายงานจุดที่ติด)
        self._dlock = threading.Lock()
        self.total_accounts = 0
        self._done = {}

    @staticmethod
    def _tree_has_run_set(steps):
        """เช็คว่ามี run_set ที่ไหนสักแห่ง (รวมในกิ่ง then/else ของ if_image)"""
        for s in steps:
            if s.get("type") == "run_set":
                return True
            for k in ("then", "else"):
                if s.get(k) and MacroRunner._tree_has_run_set(s[k]):
                    return True
        return False

    @staticmethod
    def _is_block(step):
        """run_set ที่ตั้งเป็น 'บล็อกกันพัง' = ถ้าพังให้กลับหน้าแรกแล้วรัน set นั้นใหม่
        (มาร์กด้วย block_on_fail=='home_retry') — ต่างจาก run_set ธรรมดาที่ถูกคลี่แบนทิ้ง"""
        return step.get("type") == "run_set" and step.get("block_on_fail") == "home_retry"

    def _expand_sets(self, steps):
        """ขยายขั้น run_set ให้กลายเป็นขั้นย่อยจริง (โหลดชุดจาก script_sets/*.json)
        recurse เข้ากิ่ง then/else ของ if_image ด้วย — cycle detection อยู่ใน expand_steps_with_sets

        ยกเว้น run_set ที่เป็น 'บล็อกกันพัง' (block_on_fail=='home_retry') — จะไม่คลี่แบน แต่เก็บไว้
        เป็นบล็อกตอนรัน โดย pre-resolve ขั้นย่อยของ set (_block_steps) และ set กลับหน้าแรก (_home_steps)
        ติดไว้กับ step เลย เพื่อให้ตอนรัน 'ถ้าพัง → เล่น _home_steps → เริ่ม _block_steps ใหม่' ได้
        ถ้าพัง คืน steps เดิมพร้อม log เตือน"""
        if not self._tree_has_run_set(steps):
            return steps
        try:
            from script_sets import load_script_set, expand_steps_with_sets
            import glob as _glob
            sets = {}
            for f in _glob.glob(os.path.join(base_dir(), "script_sets", "*.json")):
                try:
                    d = load_script_set(f)
                    sets[d["name"]] = d["steps"]
                except Exception:
                    pass
            resolver = lambda name: sets.get(name)

            def flatten(lst):
                """คลี่ run_set ธรรมดาทั้งหมดให้เป็นขั้นย่อยจริง (recurse เข้ากิ่ง if_image ด้วย)"""
                flat = expand_steps_with_sets(lst, resolver)
                for s in flat:
                    if s.get("type") == "if_image":
                        for k in ("then", "else"):
                            if s.get(k):
                                s[k] = flatten(s[k])
                return flat

            def build(lst):
                """เก็บ run_set แบบบล็อกไว้ (pre-resolve ขั้นย่อย+set กลับหน้าแรก) ที่เหลือคลี่แบนตามเดิม"""
                out = []
                for step in lst:
                    if self._is_block(step):
                        blk = copy.deepcopy(step)
                        set_name = str(step.get("set") or step.get("text") or "").strip()
                        sub = sets.get(set_name)
                        if sub is None:
                            self.log(f"ไม่พบชุดคำสั่ง '{set_name}' (บล็อกกันพัง) → ข้ามบล็อกนี้", "warn")
                            continue
                        blk["_block_steps"] = flatten(sub)
                        home_name = str(step.get("block_home") or "").strip()
                        if home_name:
                            if sets.get(home_name) is not None:
                                blk["_home_steps"] = flatten(sets[home_name])
                            else:
                                self.log(f"ไม่พบชุด 'กลับหน้าแรก' ชื่อ '{home_name}' → บล็อกจะลองใหม่โดยไม่กลับหน้าแรก", "warn")
                        out.append(blk)
                    elif step.get("type") == "if_image":
                        s2 = copy.deepcopy(step)
                        for k in ("then", "else"):
                            if s2.get(k):
                                s2[k] = build(s2[k])
                        out.append(s2)
                    else:
                        out.extend(flatten([step]))
                return out

            return build(steps)
        except Exception as e:
            self.log(f"ขยายชุดคำสั่ง (run_set) ไม่สำเร็จ: {e} → ใช้สคริปต์เดิม", "warn")
            return steps

    # ---------- orchestration ----------
    def run_queue(self, devices, accounts):
        """กระจายบัญชีลงจอแบบคิวต่อเนื่อง (จอว่าง = หยิบบัญชีถัดไป) เหมือน device_worker เดิม"""
        self.total_accounts = len(accounts)
        for d in devices:
            self._done[d] = 0
            self.progress(d, status="queued", account_name="-", step_idx=0, step_total=0,
                          step_desc="รอคิว", done_count=0, total_accounts=self.total_accounts)

        if not accounts:
            with ThreadPoolExecutor(max_workers=len(devices)) as ex:
                list(ex.map(lambda d: self._one_and_close(d, None), devices))
            return

        q = queue.Queue()
        for a in accounts:
            q.put(a)

        def worker(dev):
            paused = False
            while self.running():
                try:
                    acc = q.get_nowait()
                except queue.Empty:
                    break
                self.log(f"[{dev}] เริ่มบัญชี: {account_display_name(acc)}", "info")
                status = self.execute_one(dev, acc)
                if status == "paused":
                    # จอนี้ค้างรอผู้ใช้แก้ไข — เลิกหยิบคิวต่อ (บัญชีนี้ยังไม่เสร็จ รอกด 'รันต่อ' เอง)
                    # จออื่นใน ex.map ไม่โดนกระทบ ยังทำงานต่อตามปกติ
                    paused = True
                    break
                q.task_done()
            if not paused:
                self.progress(dev, status="done" if self.running() else "stopped", step_desc="")

        with ThreadPoolExecutor(max_workers=len(devices)) as ex:
            list(ex.map(worker, devices))

    def _one_and_close(self, dev, acc):
        status = self.execute_one(dev, acc)
        if status != "paused":
            self.progress(dev, status="done" if self.running() else "stopped", step_desc="")

    def run_batch_once(self, devices, accounts):
        """รัน 1 ชุด (จับคู่จอ↔บัญชีตามลำดับ) แบบขนานแล้วคืนทันทีที่ชุดนี้เสร็จ — ไม่หยิบคิวต่อเอง
        ใช้กับโหมด 'หยุดรอตรวจทานทีละชุด' (ผู้ใช้เช็คจอเองก่อนค่อยสั่งชุดถัดไป)"""
        self.total_accounts = len(accounts)
        pairs = list(zip(devices, accounts))
        for d, _a in pairs:
            self._done.setdefault(d, 0)
        with ThreadPoolExecutor(max_workers=max(1, len(pairs))) as ex:
            list(ex.map(lambda p: self._one_and_close(p[0], p[1]), pairs))

    # ---------- รันมาโคร 1 บัญชี บน 1 จอ ----------
    MAX_BRANCH_DEPTH = 5   # กันกิ่ง if_image ซ้อนวนไม่รู้จบ

    def execute_one(self, device, account):
        who = account_display_name(account)
        self._done.setdefault(device, 0)
        total = len(self.steps)

        def prog(**kw):
            base = {"status": "running", "account_name": who,
                    "done_count": self._done[device], "total_accounts": self.total_accounts}
            base.update(kw)
            self.progress(device, **base)

        prog(step_idx=0, step_total=total, step_desc="กำลังเริ่ม…")
        status = self._run_steps(device, account, self.steps, prog, path="", depth=0, disp="")

        if status == "paused":
            # รอผู้ใช้แก้ไข+กด 'รันต่อ' เอง — ยังไม่ถือว่าจบ ไม่บันทึกผลบัญชี/ไม่รีเซ็ตจอ/ไม่นับว่าเสร็จ
            # (progress+ภาพหน้าจอค้าง ถูกส่งออกไปแล้วจาก _pause_checkpoint ก่อนคืนสถานะนี้)
            return "paused"

        # เก็บผลรายบัญชี (ให้ Api เขียน last_status ลง accounts.json ตอนจบรัน — เหมือนแอปเดิม)
        if account:
            with self._dlock:
                self.account_results.append({
                    "email": account.get("email", ""),
                    "status": "completed" if status == "completed" else
                              ("stopped" if status == "stopped" else "device_error"),
                    "error": "" if status == "completed" else status,
                    "device": device,
                })
        if status == "stopped":
            return "stopped"

        if status == "completed":
            self._done[device] += 1
            self.log(f"[{device}] {who} เสร็จ ({self._done[device]}/{self.total_accounts})", "ok")
            prog(status="running", step_idx=total, step_total=total, step_desc="เสร็จ")
        else:
            # ติดปัญหาแบบไม่ใช่ pause (เช่น เลือก 'หยุดจอนี้' ตรงๆ, วนครบรอบแล้วยังไม่เจอ, หรือคำสั่งพัง)
            # เดิมจุดนี้จะรีเซ็ตเกม (ออกแล้วเข้าใหม่) ให้จอสะอาดก่อนไปบัญชีถัดไปเสมอ — เอาออกแล้ว เพราะ
            # เปลี่ยนไปใช้ระบบ 'เรียนรู้ทีละจอ' (anchor_on_fail='pause', เป็นค่าเริ่มต้นใหม่แทน 'abort') เป็นหลัก
            # ตั้งแต่นี้ไม่มีขั้นไหนรีเซ็ตเกมอัตโนมัติอีกแล้ว (รวม 'abort' ด้วย) — ปล่อยจอไว้ตามสภาพ ให้ผู้ใช้
            # ไปดูรายงานปัญหา/แก้สคริปต์เอง
            self.progress(device, status="stuck", account_name=who,
                          done_count=self._done[device], total_accounts=self.total_accounts,
                          step_desc="ติดปัญหา · บันทึกแล้ว")
            self.log(f"[{device}] {who} ล็อกอิน/ทำงานไม่ผ่าน — ไปบัญชีถัดไป (ไม่รีเซ็ตเกมอัตโนมัติแล้ว)", "err")
        return status

    def _run_steps(self, device, account, steps, prog, path="", depth=0, disp="", block_mode=False):
        """รันลิสต์ขั้นตอน — เรียกซ้ำตัวเองเข้าไปในกิ่ง then/else ของ if_image ได้
        path = ตำแหน่งกิ่ง เช่น "" (เส้นหลัก), "2.then" — ใช้รายงานว่ารันถึงไหน
        disp = เลขขั้นแบบอ่านง่ายสำหรับ log เช่น "" หรือ "4.เจอ." (1-based)
        block_mode = True เมื่อกำลังรันขั้นย่อยที่อยู่ใน 'บล็อกกันพัง' — ถ้าเจอ anchor ไม่เจอ ให้ถือว่า
          'บล็อกนี้พัง' (คืน device_error ทันที) แทนการหยุดรอ/วนเอง เพราะบล็อกจัดการกลับหน้าแรก+ลองใหม่เอง
        คืน "completed" | "stopped" | "device_error" | "paused"

        ใช้ while + ตัวชี้ idx เดินเอง (ไม่ใช่ for) เพราะ anchor_on_fail="retry" ต้อง
        กระโดดตัวชี้ถอยหลังไปขั้นก่อนหน้าในลิสต์เดียวกันได้ (วนทำซ้ำ ไม่ใช่แค่ไล่หน้าเดียว)
        """
        if depth > self.MAX_BRANCH_DEPTH:
            self.log(f"[{device}] กิ่งซ้อนเกิน {self.MAX_BRANCH_DEPTH} ชั้น → ข้ามกิ่งนี้ (กันวนไม่รู้จบ)", "warn")
            return "completed"
        total = len(self.steps)  # ตัวเลข x/y บนการ์ดอิงเส้นหลักเสมอ (กิ่งใช้ desc นำหน้า ↳ บอกแทน)
        in_branch = bool(path)
        retry_counts = {}  # idx ของขั้นนี้ -> จำนวนรอบที่วนไปแล้ว (รีเซ็ตใหม่ทุกครั้งที่เรียกฟังก์ชันนี้)
        pause_self_healed = set()  # idx ที่เคยลองย้อนไปกดขั้นก่อนหน้าซ้ำแล้ว (นโยบาย pause) — กันวนซ้ำไม่รู้จบ

        idx = 0
        while idx < len(steps):
            if not self.running():
                return "stopped"
            step = steps[idx]
            t = step.get("type", "tap")
            here = f"{path}.{idx}" if path else str(idx)
            num = f"{disp}{idx + 1}"      # เลขขั้นให้คนอ่าน เช่น "4" หรือ "4.เจอ.1"
            desc = step.get("desc") or f"ขั้น {idx + 1}"
            if in_branch:
                prog(step_desc=f"↳ {desc}", step_path=here)
            else:
                prog(step_idx=idx + 1, step_total=total, step_desc=desc, step_path=here)

            # log รายขั้นแบบแอปเดิม — ก็อปไปดูได้ว่าทำถึงไหน ทำอะไร
            detail = ""
            if t == "tap":
                detail = f" ({step.get('x')},{step.get('y')})"
            elif t == "swipe":
                detail = f" ({step.get('x')},{step.get('y')})→({step.get('x2')},{step.get('y2')})"
            elif t in ("text", "start_app", "stop_app", "detect_image", "wait_for_image",
                       "tap_text", "wait_for_text"):
                detail = f" '{step.get('text', '')}'"
            self.log(f"[{device}] 👉 ขั้น {num}"
                     f"{f'/{total}' if not in_branch else ''}: {desc} [{t}]{detail}", "info")

            # ---- บล็อกกันพัง: รัน set นี้จนจบ ถ้าพัง → กลับหน้าแรก → เริ่ม set นี้ใหม่ (จำกัดรอบ) ----
            if self._is_block(step):
                r = self._run_block(device, account, step, prog, here, num, depth)
                if r != "completed":
                    return r
                idx += 1
                continue

            # ---- บล็อกทางเลือก: เจอภาพ → กิ่ง then จนจบ แล้วกลับมาต่อเส้นนี้ / ไม่เจอ → กิ่ง else ----
            if t == "if_image":
                branch = self._eval_if_image(device, step)
                if branch == "stopped":
                    return "stopped"
                sub = step.get(branch) or []
                bname = "เจอ" if branch == "then" else "ไม่เจอ"
                if sub:
                    self.log(f"[{device}] 🔀 ขั้น {num}: เข้ากิ่ง '{bname}' ({len(sub)} ขั้น)", "info")
                    r = self._run_steps(device, account, sub, prog,
                                        path=f"{here}.{branch}", depth=depth + 1,
                                        disp=f"{num}.{bname}.", block_mode=block_mode)
                    if r != "completed":
                        return r
                    self.log(f"[{device}] ↩ ขั้น {num}: จบกิ่ง '{bname}' → กลับเส้นหลัก", "info")
                else:
                    self.log(f"[{device}] 🔀 ขั้น {num}: กิ่ง '{bname}' ว่าง (ไม่มีขั้นให้ทำ) → ไปต่อ", "warn")
                d = self._delay(step)
                if d > 0:
                    time.sleep(d)
                idx += 1
                continue

            # ---- Anchor gate: รอภาพก่อนกด (กันจอมั่ว) ----
            anchor_hit = None
            if step.get("anchor_img"):
                gate, ax, ay = self._wait_anchor(device, step)
                if gate == "stopped":
                    return "stopped"
                if gate == "found" and ax is not None:
                    anchor_hit = (ax, ay)
                if gate == "missing":
                    # อยู่ในบล็อกกันพัง: ไม่เจอภาพ = ถือว่า 'set นี้พัง' ทันที คืน device_error ให้ตัวจัดการบล็อก
                    # ไปกลับหน้าแรก+เริ่ม set ใหม่เอง (ไม่หยุดรอ/ไม่วนเองในนี้ เพราะบล็อกคุมการลองใหม่แล้ว)
                    if block_mode:
                        self.log(f"[{device}] ไม่เจอภาพขั้น {num} ({desc}) → ถือว่าชุดคำสั่งนี้พัง (จะกลับหน้าแรกแล้วลองใหม่)", "warn")
                        return "device_error"
                    # ค่าเริ่มต้นเป็น 'pause' (เรียนรู้ทีละจอ) แทน 'abort' เดิม — วนกลับ (retry) ยังคง
                    # เป็นเครื่องมือที่ต้องตั้งเองเท่านั้น ไม่ใช่ค่าเริ่มต้น ตรงตามที่ผู้ใช้ต้องการ
                    pol = step.get("anchor_on_fail", "pause")
                    if pol == "retry":
                        target = step.get("anchor_retry_target")
                        limit = int(step.get("anchor_retry_limit", 3) or 3)
                        cnt = retry_counts.get(idx, 0)
                        if target is not None and 0 <= int(target) < len(steps) and cnt < limit:
                            retry_counts[idx] = cnt + 1
                            self.log(f"[{device}] ไม่เจอภาพขั้น {num} → วนกลับไปทำขั้นที่ {int(target) + 1} ใหม่ "
                                     f"(รอบที่ {cnt + 1}/{limit})", "warn")
                            idx = int(target)
                            continue
                        reason = "ยังไม่ได้ตั้งขั้นเป้าหมายให้วนกลับ" if target is None else f"วนครบ {limit} รอบแล้วยังไม่เจอ"
                        self.log(f"[{device}] ไม่เจอภาพขั้น {num} ({desc}) → {reason} → หยุดจอนี้ กันรันมั่ว", "err")
                        self._save_failure_report(device, account, here, step, "anchor_missing_retry_exhausted")
                        return "device_error"
                    elif pol == "skip":
                        self.log(f"[{device}] ไม่เจอภาพขั้น {num} → ข้ามสเต็ปนี้ไป", "warn")
                        idx += 1
                        continue
                    elif pol == "pause":
                        # ก่อนหยุดรอจริง ลองย้อนไปทำขั้นก่อนหน้าซ้ำอีก 1 ที (เผื่อกดตอนนั้นแล้วจอ/เครื่องค้าง
                        # เลยไม่ขยับมาจอนี้จริง ๆ) แล้วเช็ค anchor ใหม่ — ถ้าลองแล้วยังไม่เจอจริง ๆ ค่อยหยุดรอ
                        if idx > 0 and idx not in pause_self_healed:
                            pause_self_healed.add(idx)
                            self.log(f"[{device}] ไม่เจอภาพขั้น {num} ({desc}) → ลองย้อนไปทำขั้นก่อนหน้าซ้ำ "
                                     f"(เผื่อจอค้าง) แล้วเช็คใหม่", "warn")
                            idx -= 1
                            continue
                        self.log(f"[{device}] ไม่เจอภาพขั้น {num} ({desc}) → หยุดรอแก้ไข (ไม่รีเซ็ตเกม เก็บจอไว้ตามที่ค้าง)", "warn")
                        self._pause_checkpoint(device, account, here, step, prog)
                        return "paused"
                    elif pol == "tap":
                        self.log(f"[{device}] ไม่เจอภาพขั้น {num} → กดตามพิกัดเดิม (เสี่ยง)", "warn")
                    else:
                        self.log(f"[{device}] ไม่เจอภาพขั้น {num} ({desc}) → หยุดจอนี้ กันรันมั่ว", "err")
                        self._save_failure_report(device, account, here, step, "anchor_missing")
                        return "device_error"

            try:
                self._dispatch(device, account, step, anchor_hit)
            except Exception as e:
                self.log(f"[{device}] ขั้น {num} ล้มเหลว: {e}", "err")
                self._save_failure_report(device, account, here, step, str(e))
                return "device_error"

            idx += 1

        return "completed"

    def _run_block(self, device, account, step, prog, here, num, depth):
        """รัน 'บล็อกกันพัง' 1 บล็อก: รันขั้นย่อยของ set (block_mode=True) จนจบ
        ถ้าพัง (device_error) → เล่นชุด 'กลับหน้าแรก' → เริ่ม set นี้ใหม่ทั้งชุด จำกัดจำนวนรอบ (block_retries)
        คืน 'completed' | 'stopped' | 'device_error'
          - completed = set ทำจนจบสำเร็จ (ในรอบใดรอบหนึ่ง)
          - stopped   = ผู้ใช้กดหยุด
          - device_error = ลองครบทุกรอบแล้วยังพัง (บันทึกจุดที่ติดไว้แล้ว)"""
        set_name = str(step.get("set") or step.get("text") or "").strip() or "ชุดคำสั่ง"
        sub_steps = step.get("_block_steps") or []
        home_steps = step.get("_home_steps") or []
        try:
            retries = max(0, int(step.get("block_retries", 3) or 0))
        except (TypeError, ValueError):
            retries = 3
        total_rounds = retries + 1  # ครั้งแรก + ลองซ้ำอีก retries รอบ

        for attempt in range(1, total_rounds + 1):
            if not self.running():
                return "stopped"
            self.log(f"[{device}] ▶ เริ่มชุด '{set_name}' (รอบ {attempt}/{total_rounds})", "info")
            r = self._run_steps(device, account, sub_steps, prog,
                                path=f"{here}.set", depth=depth + 1, disp=f"{num}.", block_mode=True)
            if r == "stopped":
                return "stopped"
            if r == "completed":
                self.log(f"[{device}] ✔ ชุด '{set_name}' สำเร็จ", "ok")
                return "completed"
            # r == device_error/paused → ชุดนี้พังในรอบนี้
            if attempt >= total_rounds:
                self.log(f"[{device}] ⛔ ชุด '{set_name}' พังครบ {total_rounds} รอบแล้ว → หยุด (บันทึกจุดที่ติดไว้)", "err")
                self._save_failure_report(device, account, here, step, f"block_failed:{set_name}")
                return "device_error"
            # ยังมีรอบเหลือ → กลับหน้าแรกก่อนเริ่มใหม่
            if home_steps:
                self.log(f"[{device}] ↺ ชุด '{set_name}' พัง → กลับหน้าแรกแล้วเริ่มใหม่ (รอบถัดไป {attempt + 1}/{total_rounds})", "warn")
                hr = self._run_steps(device, account, home_steps, prog,
                                     path=f"{here}.home", depth=depth + 1, disp=f"{num}.กลับ.", block_mode=False)
                if hr == "stopped":
                    return "stopped"
            else:
                self.log(f"[{device}] ↺ ชุด '{set_name}' พัง → เริ่มใหม่ (ไม่ได้ตั้งชุดกลับหน้าแรก) รอบถัดไป {attempt + 1}/{total_rounds}", "warn")
        return "device_error"

    def _eval_if_image(self, device, step):
        """ประเมินเงื่อนไข if_image: เจอภาพภายใน timeout → 'then' ไม่เจอ → 'else'
        ภาพเงื่อนไขมาจาก anchor_img (base64 ที่ลากกรอบ) หรือ text (ไฟล์ใน templates/)"""
        threshold = float(step.get("threshold", 0.8) or 0.8)
        timeout = float(step.get("timeout", 2.0) or 2.0)

        tmpl_bytes, tmpl_path = None, None
        b64 = step.get("anchor_img") or ""
        if b64:
            try:
                tmpl_bytes = base64.b64decode(b64) or None
            except Exception:
                tmpl_bytes = None
        if tmpl_bytes is None:
            tf = (step.get("text") or "").strip()
            p = os.path.join(templates_dir(), tf) if tf else ""
            if p and os.path.exists(p):
                tmpl_path = p
        if tmpl_bytes is None and tmpl_path is None:
            self.log(f"[{device}] if_image: ไม่ได้ตั้งภาพเงื่อนไข → ถือว่า 'ไม่เจอ'", "warn")
            return "else"

        deadline = time.time() + timeout
        while True:
            if not self.running():
                return "stopped"
            ok, data = self.controller.capture_screenshot_bytes(device)
            if ok:
                if tmpl_bytes is not None:
                    found, _x, _y, _m = self.controller.match_template_bytes(data, tmpl_bytes, threshold)
                else:
                    found, _x, _y, _m = self.controller.find_image_in_bytes(data, tmpl_path, threshold=threshold)
                if found:
                    self.log(f"[{device}] เงื่อนไข '{step.get('desc') or 'if_image'}' → ✅ เจอ", "info")
                    return "then"
            if time.time() >= deadline:
                self.log(f"[{device}] เงื่อนไข '{step.get('desc') or 'if_image'}' → ❌ ไม่เจอ", "info")
                return "else"
            if not self._interruptible_sleep(0.4):
                return "stopped"

    def _save_failure_report(self, device, account, step_path, step, reason):
        """บันทึก 'จุดที่ติด' (พอร์ตจาก gui._save_failure_report): แคปภาพ ณ ตอนติด +
        ข้อมูลบัญชี/สเต็ป/เหตุผล ลง error_reports/ ไว้ย้อนดูภายหลัง"""
        try:
            now = datetime.datetime.now()
            folder = os.path.join(base_dir(), "error_reports", now.strftime("%Y%m%d"))
            os.makedirs(folder, exist_ok=True)
            port = str(device).split(":")[-1]
            img_path = os.path.join(folder, f"{now.strftime('%H%M%S')}_{port}_step{step_path.replace('.', '-')}.png")
            saved = ""
            ok, data = self.controller.capture_screenshot_bytes(device)
            if ok and data:
                with open(img_path, "wb") as f:
                    f.write(data)
                saved = img_path
            rec = {
                "time": now.strftime("%Y-%m-%d %H:%M:%S"), "device": device,
                "email": (account or {}).get("email", ""),
                "name": account_display_name(account) if account else "",
                "profile": getattr(self, "profile_name", ""),
                "step_path": step_path,
                "step_type": step.get("type", ""), "step_desc": step.get("desc", ""),
                "reason": reason, "image": saved,
            }
            with open(os.path.join(base_dir(), "error_reports", "report.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.log(f"[{device}] บันทึกจุดที่ติด: ขั้น {step_path} '{step.get('desc', '')}' ({reason})", "warn")
        except Exception as e:
            self.log(f"[{device}] บันทึกรายงานปัญหาไม่สำเร็จ: {e}", "warn")

    def _pause_checkpoint(self, device, account, step_path, step, prog):
        """anchor_on_fail='pause': ต่างจาก _save_failure_report ตรงที่นี่ไม่ใช่ 'ความล้มเหลว' แต่เป็น
        จุดที่ 'รอผู้ใช้มาสอนเพิ่ม' — ไม่บันทึกลงไฟล์ log ถาวร แต่ส่งภาพหน้าจอ ณ ตอนค้าง + บัญชีที่ค้างไว้
        ผ่าน progress callback (คีย์ขึ้นต้น _ กันชื่อชนกับฟิลด์แสดงผลปกติ) ให้ฝั่งเว็บเก็บไว้แสดงในแผง
        'จอที่รอแก้ไข' และใช้ตอนกด 'รันต่อจากขั้นนี้' — จอไม่ถูกแตะต้องต่อ (ไม่รีเซ็ต ไม่กดต่อ) กันข้อมูล
        ที่ผู้ใช้ต้องดูเพื่อสร้างเงื่อนไขใหม่หายไปก่อน"""
        shot_b64 = None
        try:
            ok, data = self.controller.capture_screenshot_bytes(device)
            if ok and data:
                shot_b64 = base64.b64encode(data).decode("ascii")
        except Exception:
            pass
        prog(status="paused", step_desc=f"⏸ รอแก้ไข: {step.get('desc') or step_path}", step_path=step_path,
             _pause_shot=shot_b64, _pause_account=account)

    @staticmethod
    def _as_int(v):
        """ADB 'input tap/swipe' รับได้เฉพาะเลขจำนวนเต็ม — พิกัดที่มาจากฟอร์ม/ลากกรอบอาจเป็น
        ทศนิยม (เช่น '293.5') ถ้าส่งตรงๆ คำสั่งจะพังเงียบๆ (ไม่มี exception แต่ ADB คืน error)"""
        return int(round(float(v)))

    def _check(self, device, label, ret):
        """เช็คผล (ok, msg) จาก controller — พอร์ตจาก ctx.record ของแอปเดิม
        ถ้า ADB ล้มเหลว (เช่น พิกัดพัง/จอหลุด) ต้อง raise ให้ _run_steps จับ แล้วบันทึกจุดที่ติด
        ไม่ใช่เดินหน้าทำขั้นถัดไปทั้งที่ขั้นนี้ไม่ได้กดจริง"""
        try:
            ok, msg = ret
        except (TypeError, ValueError):
            return ret
        if not ok:
            raise RuntimeError(f"คำสั่ง {label} ล้มเหลว: {msg}")
        return ret

    # ---------- dispatch ต่อชนิด step ----------
    def _dispatch(self, device, account, step, anchor_hit):
        t = step.get("type", "tap")
        c = self.controller
        delay = self._delay(step)

        if t == "tap":
            x, y = step.get("x"), step.get("y")
            reg = step.get("anchor_region")
            if step.get("anchor_tap") and anchor_hit and reg:
                acx = reg["x"] + reg["w"] / 2.0
                acy = reg["y"] + reg["h"] / 2.0
                x = anchor_hit[0] + (float(step["x"]) - acx)
                y = anchor_hit[1] + (float(step["y"]) - acy)
            self._check(device, "tap", c.tap(device, self._as_int(x), self._as_int(y)))
        elif t == "swipe":
            dur = int(float(step.get("duration", DEFAULT_SWIPE_DURATION)))
            self._check(device, "swipe", c.swipe(device, self._as_int(step["x"]), self._as_int(step["y"]),
                                                 self._as_int(step["x2"]), self._as_int(step["y2"]), dur))
        elif t == "text":
            txt = substitute_account(step["text"], account)
            fn = c.input_text if str(txt).isascii() else c.input_text_unicode
            self._check(device, "text", fn(device, txt))
        elif t == "keyevent":
            self._check(device, "keyevent", c.keyevent(device, step.get("code", step.get("keycode"))))
        elif t == "start_app":
            self._check(device, "start_app", c.start_app(device, step["text"]))
        elif t == "stop_app":
            self._check(device, "stop_app", c.stop_app(device, step["text"]))
        elif t == "sleep":
            time.sleep(float(step.get("seconds", step.get("delay", 1)) or 0))
            return  # sleep คุมเวลาเอง
        elif t == "detect_image":
            self._detect_image(device, step)
        elif t == "read_diamond":
            self._read_diamond(device, account)
        elif t == "wait_for_image":
            self._wait_for_image(device, step); return
        elif t == "tap_text":
            self._tap_text(device, account, step); return
        elif t == "wait_for_text":
            self._wait_for_text(device, account, step); return
        elif t == "fetch_otp":
            self._fetch_otp(device, account, step); return
        elif t == "clear_ads_loop":
            self._clear_ads_loop(device, step); return
        elif t == "keyboard":
            self._keyboard(device, step); return
        elif t == "find_yellow_stage":
            self._find_yellow_stage(device, step); return
        elif t in self._UNSUPPORTED:
            self.log(f"[{device}] ชนิด '{t}' ยังไม่รองรับในตัวรันใหม่ → ข้าม", "warn")
        else:
            self.log(f"[{device}] ไม่รู้จักชนิด '{t}' → ข้าม", "warn")

        if delay > 0:
            time.sleep(delay)

    def _detect_image(self, device, step):
        import os as _os
        tf = step.get("text", "")
        tp = _os.path.join(base_dir(), "templates", tf)
        if not _os.path.exists(tp):
            self.log(f"[{device}] ไม่พบเทมเพลต {tf} → ข้าม", "warn")
            return
        ok, data = self.controller.capture_screenshot_bytes(device)
        if not ok:
            return
        found, mx, my, _msg = self.controller.find_image_in_bytes(data, tp, threshold=0.8)
        if found:
            self.controller.tap(device, mx, my)

    def _sleep_delay(self, step):
        d = self._delay(step)
        if d > 0:
            time.sleep(d)

    def _interruptible_sleep(self, seconds):
        """นอนแบบยกเลิกได้ทันทีที่สั่งหยุด — คืน False ถ้าถูกสั่งหยุดระหว่างรอ"""
        waited = 0.0
        while waited < seconds:
            if not self.running():
                return False
            time.sleep(min(0.1, seconds - waited))
            waited += 0.1
        return True

    # ---------- รอภาพก่อนทำต่อ (พอร์ตจาก _step_wait_for_image) ----------
    def _wait_for_image(self, device, step):
        tf = (step.get("text") or "").strip()
        if not tf:
            self.log(f"[{device}] wait_for_image: ไม่ได้ระบุไฟล์รูป → ข้าม", "warn")
            return
        tp = os.path.join(templates_dir(), tf)
        if not os.path.exists(tp):
            self.log(f"[{device}] ไม่พบเทมเพลต {tf} → ข้าม", "warn")
            return
        timeout = float(step.get("timeout", 30) or 30)
        interval = float(step.get("interval", 1.0) or 1.0)
        threshold = float(step.get("threshold", 0.8) or 0.8)
        click = step.get("click", True)
        self.log(f"[{device}] รอจนเจอรูป '{tf}' (สูงสุด {timeout:g} วิ)…", "info")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.running():
                return
            ok, data = self.controller.capture_screenshot_bytes(device)
            if ok:
                found, mx, my, _m = self.controller.find_image_in_bytes(data, tp, threshold=threshold)
                if found:
                    self.log(f"[{device}] เจอรูป '{tf}' ({mx},{my})", "ok")
                    if click:
                        self.controller.tap(device, mx, my)
                    self._sleep_delay(step)
                    return
            if not self._interruptible_sleep(interval):
                return
        self.log(f"[{device}] รอครบ {timeout:g} วิ ยังไม่เจอรูป '{tf}'", "warn")

    # ---------- แตะ element ตามข้อความ/id (พอร์ตจาก _step_tap_text) ----------
    def _tap_text(self, device, account, step):
        query = substitute_account(step.get("text", ""), account)
        text, rid = parse_ui_query(query)
        if not text and not rid:
            self.log(f"[{device}] tap_text: ไม่ได้ระบุข้อความ/id → ข้าม", "warn")
            return
        ok, xml = self.controller.dump_ui(device)
        if not ok:
            self.log(f"[{device}] อ่าน UI ไม่ได้: {xml}", "warn")
            return
        found, x, y, info = find_element_center(xml, text=text, resource_id=rid)
        if found:
            self.log(f"[{device}] เจอ element ({info}) ({x},{y}) → แตะ", "ok")
            self.controller.tap(device, x, y)
            self._sleep_delay(step)
        else:
            self.log(f"[{device}] ไม่พบ element: {info} → ข้าม", "info")

    # ---------- รอ element (พอร์ตจาก _step_wait_for_text) ----------
    def _wait_for_text(self, device, account, step):
        query = substitute_account(step.get("text", ""), account)
        text, rid = parse_ui_query(query)
        if not text and not rid:
            self.log(f"[{device}] wait_for_text: ไม่ได้ระบุข้อความ/id → ข้าม", "warn")
            return
        timeout = float(step.get("timeout", 30) or 30)
        interval = float(step.get("interval", 1.0) or 1.0)
        click = step.get("click", True)
        self.log(f"[{device}] รอจนเจอ element '{query}' (สูงสุด {timeout:g} วิ)…", "info")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.running():
                return
            ok, xml = self.controller.dump_ui(device)
            if ok:
                found, x, y, info = find_element_center(xml, text=text, resource_id=rid)
                if found:
                    self.log(f"[{device}] เจอ element ({info}) ({x},{y})", "ok")
                    if click:
                        self.controller.tap(device, x, y)
                    self._sleep_delay(step)
                    return
            if not self._interruptible_sleep(interval):
                return
        self.log(f"[{device}] รอครบ {timeout:g} วิ ยังไม่เจอ '{query}'", "warn")

    # ---------- ดึง OTP จากเมลแล้วกรอกลงจอ (พอร์ตจาก _step_fetch_otp) ----------
    def _fetch_otp(self, device, account, step):
        account = account or {}
        if not account:
            self.log(f"[{device}] ข้ามดึง OTP (รันแบบไม่มีบัญชี)", "warn")
            return
        email_addr = (account.get("email") or "").strip()
        code = fetch_otp_from_mail(
            self.log, email_addr, (account.get("password") or "").strip(),
            (step.get("text") or "").strip(),
            refresh_token=(account.get("refresh_token") or "").strip(),
            client_id=(account.get("client_id") or "").strip())
        if code:
            self.log(f"[{device}] ดึง OTP สำเร็จ: {code} → กรอกลงจอ", "ok")
            self.controller.input_text(device, code)
            self._sleep_delay(step)
        else:
            self.log(f"[{device}] ดึง OTP ไม่ได้หลังสแกนกล่องเมล", "err")

    # ---------- ลูปเคลียร์โฆษณา (พอร์ตจาก _step_clear_ads_loop) ----------
    def _clear_ads_loop(self, device, step):
        step_delay = self._delay(step)
        step_text = (step.get("text") or "").strip()
        lobby_template, ad_templates = "", []
        if "|" in step_text:
            parts = step_text.split("|")
            lobby_template = parts[0].strip()
            ad_templates = [p.strip() for p in parts[1].split(",") if p.strip()]
        elif step_text.endswith(".png"):
            lobby_template = step_text
        elif step_text:
            ad_templates = [p.strip() for p in step_text.split(",") if p.strip()]

        tdir = templates_dir()
        if not ad_templates:
            import glob as _glob
            all_pngs = [os.path.basename(f) for f in _glob.glob(os.path.join(tdir, "*.png"))]
            ad_templates = [f for f in all_pngs
                            if f != lobby_template and not f.startswith("temp_")
                            and not any(k in f.lower() for k in ["lobby", "home", "main", "start"])]

        self.log(f"[{device}] เริ่มลูปเคลียร์โฆษณา (หน้าหลัก: '{lobby_template or 'ไม่ตั้ง'}')", "info")
        max_attempts = 15
        for attempt in range(max_attempts):
            if not self.running():
                return
            ok, data = self.controller.capture_screenshot_bytes(device)
            if not ok:
                self.log(f"[{device}] แคปจอล้มเหลว → หยุดลูป", "err")
                return
            if lobby_template:
                lp = os.path.join(tdir, lobby_template)
                if os.path.exists(lp):
                    found_lobby, _lx, _ly, _lm = self.controller.find_image_in_bytes(data, lp, threshold=0.7)
                    if found_lobby:
                        self.log(f"[{device}] รอบ {attempt+1}: ถึงหน้าหลัก → เคลียร์โฆษณาหมดแล้ว", "ok")
                        return
            found_ad = False
            for tf in ad_templates:
                tp = os.path.join(tdir, tf)
                if not os.path.exists(tp):
                    continue
                found, mx, my, _m = self.controller.find_image_in_bytes(data, tp, threshold=0.7)
                if found:
                    self.log(f"[{device}] รอบ {attempt+1}: พบปุ่มปิด '{tf}' ({mx},{my}) → แตะ", "ok")
                    self.controller.tap(device, mx, my)
                    found_ad = True
                    if step_delay > 0:
                        time.sleep(step_delay)
                    break
            if not found_ad:
                if lobby_template:
                    self.log(f"[{device}] รอบ {attempt+1}: ไม่เจอหน้าหลัก/ปุ่มปิด → กด BACK", "warn")
                    self.controller.keyevent(device, 4)
                    if step_delay > 0:
                        time.sleep(step_delay)
                else:
                    self.log(f"[{device}] เคลียร์โฆษณาเสร็จ (ไม่พบโฆษณาบนจอ)", "ok")
                    return
        self.log(f"[{device}] ลูปเคลียร์โฆษณาครบ {max_attempts} รอบ (สิ้นสุด)", "warn")

    # ---------- หาด่านเหลืองแล้วแตะ (พอร์ตจาก _step_find_yellow_stage) ----------
    def _find_yellow_stage(self, device, step):
        ok, data = self.controller.capture_screenshot_bytes(device)
        if not ok:
            self.log(f"[{device}] แคปจอไม่ได้ → ข้าม", "err")
            return
        found, cx, cy, _box = find_yellow_frame(data)
        if found:
            self.log(f"[{device}] เจอด่านเหลือง ({cx},{cy}) → แตะ", "ok")
            self.controller.tap(device, cx, cy)
        else:
            self.log(f"[{device}] ไม่พบด่านเหลืองบนจอ", "warn")
        self._sleep_delay(step)

    # ---------- ส่งปุ่มคีย์บอร์ดจริง (พอร์ตจาก _step_keyboard) ----------
    def _keyboard(self, device, step):
        key_name = (step.get("key") or "").strip().lower()
        action = (step.get("action") or "").strip().lower()
        self.log(f"[{device}] ส่งปุ่มคีย์บอร์ด: '{key_name}' ({action})", "info")
        try:
            ordered = self.controller.get_connected_devices()
        except Exception:
            ordered = [device]
        try:
            send_keyboard_input(self.log, device, ordered, key_name, action)
        except Exception as e:
            self.log(f"[{device}] ส่งปุ่มคีย์บอร์ดล้มเหลว: {e}", "err")
        self._sleep_delay(step)

    # ---------- อ่านเพชร (พอร์ตจาก _step_read_diamond) ----------
    def _read_diamond(self, device, account):
        # ไม่มีการยืนยันชื่อในเกมอีกต่อไป — ขั้นนี้มาถึงได้ก็ต่อเมื่อ anchor ของสคริปต์ยืนยันจอ/บัญชี
        # ที่ถูกต้องแล้วเท่านั้น (ผู้ใช้ยืนยันแล้วว่าลำดับ anchor รับประกันสิ่งนี้อยู่แล้ว การ OCR ชื่อซ้ำ
        # ซ้อนเข้าไปมีแต่ทำให้หลุดจาก false positive ตอน OCR อ่านเลขพลาดตัวเดียว)
        account = account or {}
        who = account_display_name(account)
        region = (self.diamond_cfg or {}).get("region") or {}
        if int(region.get("w", 0)) <= 0 or int(region.get("h", 0)) <= 0:
            self.log(f"[{device}] อ่านเพชร: ยังไม่ได้ตั้งพื้นที่ตัวเลขเพชร → ข้าม", "warn")
            return
        if not find_tesseract():
            self.log(f"[{device}] อ่านเพชร: ไม่พบ Tesseract OCR → ข้าม", "warn")
            return
        ok, data = self.controller.capture_screenshot_bytes(device)
        if not ok:
            self.log(f"[{device}] {who}: อ่านเพชรไม่ได้ (แคปจอพลาด) → ข้าม", "warn")
            return
        rok, number, _raw = self.controller.read_number_tesseract(data, region)
        if not rok or number is None:
            self.log(f"[{device}] {who}: OCR อ่านจำนวนเพชรไม่ได้ → ข้าม", "warn")
            return
        row = {
            "email": account.get("email", ""), "name": who,
            "save_web_game_id": (account.get("save_web_game_id") or "").strip(),
            "diamonds": number, "device": device,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self._dlock:
            self.diamond_rows.append(row)
        self.log(f"[{device}] {who}: 💎 {number} เพชร", "ok")

    # ---------- anchor gate (พอร์ตจาก _wait_for_step_anchor) ----------
    def _wait_anchor(self, device, step):
        b64 = step.get("anchor_img") or ""
        try:
            tmpl = base64.b64decode(b64)
        except Exception:
            return "found", None, None
        if not tmpl:
            return "found", None, None
        timeout = float(step.get("anchor_timeout", 30.0) or 30.0)
        threshold = float(step.get("anchor_threshold", 0.8) or 0.8)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.running():
                return "stopped", None, None
            ok, data = self.controller.capture_screenshot_bytes(device)
            if ok:
                found, cx, cy, _msg = self.controller.match_template_bytes(data, tmpl, threshold)
                if found:
                    return "found", cx, cy
            waited = 0.0
            while waited < self.anchor_poll:
                if not self.running():
                    return "stopped", None, None
                time.sleep(min(0.2, self.anchor_poll - waited))
                waited += 0.2
        return "missing", None, None

    # ---------- reset เกมเมื่อบัญชีติดปัญหา (เวอร์ชันย่อ) ----------
    def _reset_device(self, device):
        cfg = self.reset_cfg or {}
        pkg = cfg.get("package")
        if not cfg.get("enabled") or not pkg:
            return
        try:
            self.controller.stop_app(device, pkg)
            time.sleep(1.0)
            self.controller.launch_app_by_package(device, pkg)
            time.sleep(float(cfg.get("boot_wait", 10.0) or 10.0))
            # เล่นสเต็ปเปิดช่อง login (แตะพิกัด/รอ anchor) ถ้ามี
            for st in cfg.get("open_login_steps", []):
                if not self.running():
                    return
                if st.get("anchor_img"):
                    self._wait_anchor(device, st)
                try:
                    self.controller.tap(device, int(float(st["x"])), int(float(st["y"])))
                    time.sleep(float(st.get("delay", 1.0) or 1.0))
                except (TypeError, ValueError, KeyError):
                    continue
        except Exception as e:
            self.log(f"[{device}] รีเซ็ตเกมล้มเหลว: {e}", "warn")

    # ---------- helper ----------
    @staticmethod
    def _delay(step):
        try:
            d = float(step.get("delay") or 0)
        except (TypeError, ValueError):
            d = 0
        return d * random.uniform(0.8, 1.4) if d > 0 else 0


class StoryRunner:
    """เล่นเนื้อเรื่องอัตโนมัติ (พอร์ตจาก MuMuGUI.run_story_auto) — ไม่พึ่ง GUI
    ลูปเดียวรวมทุกสถานะ: หน้าเลือกด่าน→แตะด่าน / ในแมตช์→รอ / คัตซีน→กดปุ่ม/แตะ/ปัด/กู้"""

    _STORY_RECOVERY = [
        ("มุมข้ามขวาบน", 884, 32), ("แตะกลางจอ", 480, 270), ("ปุ่มล่างขวา", 834, 494),
        ("แตะล่างกลาง", 480, 480), ("มุมข้ามอีกจุด", 916, 30),
    ]

    def __init__(self, controller, log_cb=None, progress_cb=None, running_check=None,
                 gemini_key="", buttons_field="", scan_interval=2.5, threshold=0.7, max_stages=0):
        self.controller = controller
        self.log = log_cb or (lambda t, k="info": None)
        self.progress = progress_cb or (lambda dev, **kw: None)
        self.running = running_check or (lambda: True)
        self.gemini_key = gemini_key or ""
        self.buttons_field = buttons_field or ""
        self.scan_interval = float(scan_interval or 2.5)
        self.threshold = float(threshold or 0.7)
        self.max_stages = int(max_stages or 0)
        self._last_ai_rescue_ts = 0.0

    def run_all(self, devices):
        for d in devices:
            self.progress(d, status="running", account_name="Story", step_idx=0, step_total=0,
                          step_desc="เริ่มเล่นเนื้อเรื่อง", done_count=0, total_accounts=0)
        with ThreadPoolExecutor(max_workers=len(devices)) as ex:
            list(ex.map(self.run_story, devices))

    def _btn_templates(self):
        import glob
        tdir = os.path.join(base_dir(), "templates")
        names = [b.strip() for b in self.buttons_field.split(",") if b.strip()]
        if not names:
            names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(tdir, "story_*.png")))
        out = []
        for n in names:
            p = os.path.join(tdir, n)
            if os.path.exists(p) and n != "story_map.png":
                out.append((n, p))
        return out

    def _swipe_dirs(self, gx, screen_w=960):
        to_right = gx < screen_w / 2
        primary = ("ขวา", 1.0, 0.0) if to_right else ("ซ้าย", -1.0, 0.0)
        secondary = ("ซ้าย", -1.0, 0.0) if to_right else ("ขวา", 1.0, 0.0)
        sgn = 1.0 if to_right else -1.0
        return [primary, secondary, ("ทแยงลง", sgn * 0.7, 0.7), ("ทแยงขึ้น", sgn * 0.7, -0.7),
                ("ทแยงลงกลับ", -sgn * 0.7, 0.7), ("ทแยงขึ้นกลับ", -sgn * 0.7, -0.7),
                ("ลง", 0.0, 1.0), ("ขึ้น", 0.0, -1.0)]

    def _swipe(self, device, gx, gy, attempt, length=340):
        dirs = self._swipe_dirs(gx)
        name, dx, dy = dirs[attempt % len(dirs)]
        ex = max(20, min(940, int(gx + dx * length)))
        ey = max(20, min(520, int(gy + dy * length)))
        self.controller.swipe(device, gx, gy, ex, ey, duration=450)

    def _recover(self, device, data, step):
        if self.gemini_key and (time.time() - self._last_ai_rescue_ts) > 25.0:
            self._last_ai_rescue_ts = time.time()
            gok, gx, gy, greason = gemini_tap_suggestion(data, self.gemini_key, 960, 540)
            if gok:
                self.log(f"[{device}] กันค้าง (AI): {greason} → tap ({gx},{gy})", "warn")
                self.controller.tap(device, gx, gy)
                return
        ocr_ok, ox, oy, oword = ocr_find_button(data)
        if ocr_ok:
            self.log(f"[{device}] กันค้าง: OCR เจอ '{oword}' → tap", "warn")
            self.controller.tap(device, ox, oy)
            return
        name, rx, ry = self._STORY_RECOVERY[step % len(self._STORY_RECOVERY)]
        self.log(f"[{device}] กันค้าง: แตะ{name} ({rx},{ry})", "warn")
        self.controller.tap(device, rx, ry)

    def run_story(self, device):
        btn_paths = self._btn_templates()
        c = self.controller

        def cap():
            ok, d = c.capture_screenshot_bytes(device)
            return d if ok else None

        cleared = 0
        in_stage = False
        left_map = False
        tap_ts = 0.0
        swipe_prev = None
        swipe_attempt = 0
        prev = None
        last_change = time.time()
        recover_step = 0
        STUCK = 12.0

        while self.running():
            if self.max_stages and cleared >= self.max_stages:
                break
            data = cap()
            if data is None:
                time.sleep(2.0)
                continue
            if prev is not None:
                sim = png_similarity(data, prev)
                if sim < 0.95:
                    last_change = time.time()
                if sim < 0.85:
                    recover_step = 0
            prev = data

            if in_stage:
                handled = False
                for name, path in btn_paths:
                    fnd, mx, my, _ = c.find_image_in_bytes(data, path, threshold=self.threshold)
                    if fnd:
                        self.log(f"[{device}] กดปุ่ม '{name}'", "info")
                        c.tap(device, mx, my)
                        handled = True; left_map = True; last_change = time.time()
                        time.sleep(0.8); break
                if handled:
                    continue

            hf, hx, hy = find_highlighted_stage(data)
            if hf and find_swipe_glow(data)[0]:
                hf = False
            if hf:
                if in_stage and left_map:
                    cleared += 1
                    self.progress(device, done_count=cleared, step_desc=f"เคลียร์ {cleared} ด่าน")
                    self.log(f"[{device}] ด่านจบ → กลับหน้าเลือกด่าน (รวม {cleared})", "ok")
                    in_stage = False; left_map = False
                if in_stage and (time.time() - tap_ts) < 6.0:
                    time.sleep(self.scan_interval); continue
                time.sleep(0.5)
                d2 = cap()
                h2, hx2, hy2 = find_highlighted_stage(d2) if d2 is not None else (False, 0, 0)
                if not h2 or abs(hx2 - hx) > 30 or abs(hy2 - hy) > 30:
                    continue
                self.log(f"[{device}] แตะด่านเหลือง ({hx2},{hy2})", "info")
                c.tap(device, hx2, hy2)
                in_stage = True; left_map = False; tap_ts = time.time(); last_change = time.time()
                swipe_prev = None; swipe_attempt = 0
                time.sleep(1.5); continue

            if in_stage:
                left_map = True
            if in_match_autoplay(data):
                time.sleep(self.scan_interval); continue

            tapped = False
            for name, path in btn_paths:
                fnd, mx, my, _ = c.find_image_in_bytes(data, path, threshold=self.threshold)
                if fnd:
                    self.log(f"[{device}] กดปุ่ม '{name}'", "info")
                    c.tap(device, mx, my); tapped = True; time.sleep(0.8); break
            if not tapped:
                gl_ok, gx, gy = find_swipe_glow(data)
                if gl_ok:
                    if swipe_prev and abs(gx - swipe_prev[0]) < 25 and abs(gy - swipe_prev[1]) < 25:
                        swipe_attempt += 1
                    else:
                        swipe_attempt = 0
                    swipe_prev = (gx, gy)
                    if swipe_attempt == 0:
                        c.tap(device, gx, gy)
                    else:
                        self._swipe(device, gx, gy, swipe_attempt - 1)
                    tapped = True; time.sleep(0.8)
                else:
                    swipe_prev = None
            if not tapped:
                ocr_ok, ox, oy, oword = ocr_find_button(data)
                if ocr_ok:
                    c.tap(device, ox, oy); tapped = True; time.sleep(0.8)
            if not tapped:
                time.sleep(self.scan_interval)

            if (time.time() - last_change) > STUCK:
                self._recover(device, data, recover_step)
                recover_step += 1
                last_change = time.time() - (STUCK - 4.0)
                time.sleep(1.0)

        self.progress(device, status="done" if self.running() else "stopped",
                      step_desc=f"หยุด — เคลียร์ {cleared} ด่าน")
        self.log(f"[{device}] Story Auto หยุด — เคลียร์ {cleared} ด่าน", "ok")
        return cleared
