"""ตัวรันมาโครแบบไม่พึ่ง GUI — ใช้ได้ทั้งแอป Tkinter เดิมและแอปเว็บ (pywebview)
พอร์ตตรรกะหลักจาก MuMuGUI.execute_device_macro/_step_* มาไว้ที่เดียว ไม่แตะ gui.py

ใช้ callback ส่งออก: log(text, kind) และ progress(device, **state)
และ running_check() คืน False เมื่อสั่งหยุด — worker จะเลิกเอง
"""
import os
import sys
import time
import base64
import queue
import random
import json
import threading
import datetime
from concurrent.futures import ThreadPoolExecutor

from mumu_controller import (find_tesseract, names_match,
                             available_tesseract_langs, ocr_text_tesseract,
                             find_highlighted_stage, find_swipe_glow, in_match_autoplay,
                             ocr_find_button, png_similarity, gemini_tap_suggestion)


DEFAULT_SWIPE_DURATION = 300


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def account_display_name(acc):
    if not acc:
        return "-"
    return acc.get("title") or acc.get("ingamename") or acc.get("name") or acc.get("email", "-")


def substitute_account(text, account):
    """แทน {EMAIL}/{PASSWORD}/{NAME} ด้วยข้อมูลบัญชีรอบนี้"""
    if not account:
        return text
    return (str(text)
            .replace("{EMAIL}", account.get("email", "") or "")
            .replace("{PASSWORD}", account.get("password", "") or "")
            .replace("{NAME}", account.get("name", "") or account.get("ingamename", "") or ""))


class MacroRunner:
    # ชนิด step ที่ตัวรันใหม่ยังไม่รองรับ (จะ log แล้วข้าม ไม่ให้พังทั้งรอบ)
    _UNSUPPORTED = {"story_auto", "clear_ads_loop", "fetch_otp",
                    "run_set", "keyboard", "tap_text", "wait_for_text",
                    "wait_for_image", "find_yellow_stage"}

    def __init__(self, controller, steps, log_cb=None, progress_cb=None,
                 running_check=None, anchor_poll=0.5, reset_cfg=None, diamond_cfg=None):
        self.controller = controller
        self.steps = steps or []
        self.log = log_cb or (lambda t, k="info": None)
        self.progress = progress_cb or (lambda dev, **kw: None)
        self.running = running_check or (lambda: True)
        self.anchor_poll = float(anchor_poll or 0.5)
        self.reset_cfg = reset_cfg or {}
        self.diamond_cfg = diamond_cfg or {}
        self.diamond_rows = []          # ผลอ่านเพชร (Api เอาไปเขียนไฟล์/บัญชีตอนจบรัน)
        self._dlock = threading.Lock()
        self.total_accounts = 0
        self._done = {}

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
            while self.running():
                try:
                    acc = q.get_nowait()
                except queue.Empty:
                    break
                self.log(f"[{dev}] เริ่มบัญชี: {account_display_name(acc)}", "info")
                self.execute_one(dev, acc)
                q.task_done()
            self.progress(dev, status="done" if self.running() else "stopped", step_desc="")

        with ThreadPoolExecutor(max_workers=len(devices)) as ex:
            list(ex.map(worker, devices))

    def _one_and_close(self, dev, acc):
        self.execute_one(dev, acc)
        self.progress(dev, status="done" if self.running() else "stopped", step_desc="")

    # ---------- รันมาโคร 1 บัญชี บน 1 จอ ----------
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
        status = "completed"

        for idx, step in enumerate(self.steps):
            if not self.running():
                return "stopped"
            t = step.get("type", "tap")
            desc = step.get("desc") or f"ขั้น {idx + 1}"
            prog(step_idx=idx + 1, step_total=total, step_desc=desc)

            # ---- Anchor gate: รอภาพก่อนกด (กันจอมั่ว) ----
            anchor_hit = None
            if step.get("anchor_img"):
                gate, ax, ay = self._wait_anchor(device, step)
                if gate == "stopped":
                    return "stopped"
                if gate == "found" and ax is not None:
                    anchor_hit = (ax, ay)
                if gate == "missing":
                    pol = step.get("anchor_on_fail", "abort")
                    if pol == "skip":
                        self.log(f"[{device}] ไม่เจอภาพขั้น {idx + 1} → ข้าม", "warn")
                        continue
                    elif pol == "tap":
                        self.log(f"[{device}] ไม่เจอภาพขั้น {idx + 1} → กดพิกัดเดิม (เสี่ยง)", "warn")
                    else:
                        self.log(f"[{device}] ไม่เจอภาพขั้น {idx + 1} ({desc}) → หยุดจอนี้ กันรันมั่ว", "err")
                        status = "device_error"
                        break

            try:
                self._dispatch(device, account, step, anchor_hit)
            except Exception as e:
                self.log(f"[{device}] ขั้น {idx + 1} ล้มเหลว: {e}", "err")
                status = "device_error"
                break

        if status == "completed":
            self._done[device] += 1
            self.log(f"[{device}] {who} เสร็จ ({self._done[device]}/{self.total_accounts})", "ok")
            prog(status="running", step_idx=total, step_total=total, step_desc="เสร็จ")
        else:
            # ติดปัญหา → รีเซ็ตเกมให้จอกลับมาสะอาด กันโดมิโน่บัญชีถัดไป
            self.progress(device, status="stuck", account_name=who,
                          done_count=self._done[device], total_accounts=self.total_accounts,
                          step_desc="ติดปัญหา · รีเซ็ตเกม")
            self.log(f"[{device}] {who} ล็อกอิน/ทำงานไม่ผ่าน — รีเซ็ตเกมไปบัญชีถัดไป", "err")
            self._reset_device(device)
        return status

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
                x = int(round(anchor_hit[0] + (float(step["x"]) - acx)))
                y = int(round(anchor_hit[1] + (float(step["y"]) - acy)))
            c.tap(device, x, y)
        elif t == "swipe":
            dur = int(float(step.get("duration", DEFAULT_SWIPE_DURATION)))
            c.swipe(device, step["x"], step["y"], step["x2"], step["y2"], dur)
        elif t == "text":
            txt = substitute_account(step["text"], account)
            (c.input_text if str(txt).isascii() else c.input_text_unicode)(device, txt)
        elif t == "keyevent":
            c.keyevent(device, step.get("code", step.get("keycode")))
        elif t == "start_app":
            c.start_app(device, step["text"])
        elif t == "stop_app":
            c.stop_app(device, step["text"])
        elif t == "sleep":
            time.sleep(float(step.get("seconds", step.get("delay", 1)) or 0))
            return  # sleep คุมเวลาเอง
        elif t == "detect_image":
            self._detect_image(device, step)
        elif t == "read_diamond":
            self._read_diamond(device, account)
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

    # ---------- อ่านเพชร (พอร์ตจาก _step_read_diamond + _verify_diamond_identity) ----------
    def _read_diamond(self, device, account):
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
        # ยาม Layer A: ยืนยันชื่อในเกมตรงบัญชีก่อนเขียน (กันเขียนผิดบัญชี)
        vok, data = self._verify_identity(device, account, who, data)
        if not vok:
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

    def _verify_identity(self, device, account, who, data):
        cfg = self.diamond_cfg or {}
        if not cfg.get("verify_name", True):
            return True, data
        expected = (account.get("ingamename") or account.get("name") or "").strip()
        if not expected:
            self.log(f"[{device}] {who}: บัญชีไม่มี ingamename → ข้ามการยืนยัน (best-effort)", "warn")
            return True, data
        name_region = cfg.get("name_region") or {"x": 90, "y": 18, "w": 140, "h": 26}
        min_ratio = float(cfg.get("name_match_ratio", 0.72) or 0.72)
        lang = "tha+eng" if "tha" in available_tesseract_langs() else "eng"
        last_seen = ""
        for attempt in range(3):
            ok, txt, _ = ocr_text_tesseract(data, region=name_region, lang=lang, psm=7, scale=3)
            seen = (txt or "").strip().replace("\n", " ")
            if seen:
                last_seen = seen
            if ok and seen and names_match(expected, seen, min_ratio=min_ratio):
                return True, data
            if attempt < 2:
                time.sleep(1.5)
                cok, cdata = self.controller.capture_screenshot_bytes(device)
                if cok:
                    data = cdata
        self.log(f"[{device}] {who}: ชื่อในเกมไม่ตรง (คาด '{expected}' เห็น '{last_seen or '—'}') "
                 f"→ ไม่เขียนเพชร กันข้อมูลเพี้ยน", "err")
        return False, data

    # ---------- anchor gate (พอร์ตจาก _wait_for_step_anchor) ----------
    def _wait_anchor(self, device, step):
        b64 = step.get("anchor_img") or ""
        try:
            tmpl = base64.b64decode(b64)
        except Exception:
            return "found", None, None
        if not tmpl:
            return "found", None, None
        timeout = float(step.get("anchor_timeout", 8.0) or 8.0)
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
