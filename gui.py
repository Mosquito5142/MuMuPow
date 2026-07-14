import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
import time
import random
import json
import os
import glob
import sys
import hashlib
import re
from mumu_controller import (
    MuMuController, find_element_center, list_ui_elements, find_tesseract,
    get_host_specs, estimate_mumu_capacity, DEFAULT_MUMU_PROFILE,
    stitch_png_vertically, png_similarity,
    ocr_text_tesseract, extract_guild_member_names, available_tesseract_langs, names_match,
    set_tessdata_dir, guild_ocr_langs,
    find_yellow_frame, find_highlighted_stage, find_swipe_glow, in_match_autoplay,
    ocr_find_button, gemini_tap_suggestion,
)
from quick_builder import (
    DEFAULT_COORDINATE_PRESETS,
    DEFAULT_ACTION_DELAY,
    DEFAULT_SWIPE_DURATION,
    build_key_step,
    build_sleep_step,
    build_swipe_step,
    build_tap_step_from_preset,
    build_text_step,
    normalize_coordinate_presets,
    normalize_coordinate_preset,
)
from script_sets import (
    build_run_set_step,
    expand_steps_with_sets,
    load_script_set,
    safe_set_slug,
    save_script_set,
)
from save_web_game_import import (
    import_save_web_game_accounts,
    push_diamonds_to_web,
    fetch_web_accounts,
    match_accounts_to_web,
)

# จานสีสำหรับธีมมืดระดับพรีเมียม (Premium Dark Theme Color Palette)
BG_DARK = "#080D16"
BG_PANEL = "#0C1422"
BG_CARD = "#0D1523"
BG_SURFACE = "#121D2E"
BG_INPUT = "#0A111D"
BG_HOVER = "#18243A"
FG_WHITE = "#E6EDF7"
FG_MUTED = "#8DA0B8"
FG_DIM = "#64748B"
LINE_SOFT = "#223046"
ACCENT_BLUE = "#38BDF8"
ACCENT_HOVER = "#0EA5E9"
ACCENT_GREEN = "#0F766E"
ACCENT_RED = "#7F1D1D"
ACCENT_ORANGE = "#A16207"

BUTTON_VARIANTS = {
    "neutral": {"bg": "#18243A", "hover": "#24344B", "fg": FG_WHITE},
    "primary": {"bg": ACCENT_GREEN, "hover": "#115E59", "fg": FG_WHITE},
    "accent": {"bg": "#0F2F4A", "hover": "#164E72", "fg": FG_WHITE},
    "danger": {"bg": ACCENT_RED, "hover": "#991B1B", "fg": FG_WHITE},
    "warning": {"bg": ACCENT_ORANGE, "hover": "#854D0E", "fg": FG_WHITE},
    "subtle": {"bg": BG_SURFACE, "hover": BG_HOVER, "fg": FG_WHITE},
}


def get_button_colors(variant="neutral"):
    return BUTTON_VARIANTS.get(variant, BUTTON_VARIANTS["neutral"])


def build_macro_step_summary(idx, step):
    step_type = (step.get("type") or "").lower()
    label_map = {
        "tap": "Tap",
        "text": "Text",
        "keyevent": "Key",
        "swipe": "Swipe",
        "sleep": "Sleep",
        "start_app": "Start App",
        "stop_app": "Stop App",
        "detect_image": "Image Match",
        "wait_for_image": "Wait Image",
        "tap_text": "Tap Text",
        "wait_for_text": "Wait Text",
        "clear_ads_loop": "Ads Loop",
        "fetch_otp": "Auto OTP",
        "run_set": "Run Set",
        "screenshot": "Screenshot",
        "keyboard": "Keyboard",
        "read_diamond": "อ่านเพชร",
    }
    label = label_map.get(step_type, step_type.title() or "Step")

    if step_type == "tap":
        detail = f"{step.get('x', '')}, {step.get('y', '')}"
    elif step_type == "swipe":
        detail = f"{step.get('x', '')},{step.get('y', '')} -> {step.get('x2', '')},{step.get('y2', '')}"
    elif step_type == "keyevent":
        detail = str(step.get("code") or step.get("text") or "")
    elif step_type == "sleep":
        detail = f"wait {step.get('seconds', step.get('duration', step.get('delay', '')))}"
    elif step_type == "run_set":
        detail = str(step.get("set") or step.get("set_name") or step.get("text") or "")
    elif step_type == "keyboard":
        action = step.get("action") or ""
        key = step.get("key") or step.get("text") or ""
        detail = " ".join(part for part in (action, key) if part)
    else:
        detail = str(step.get("text") or step.get("set_name") or "")

    delay = step.get("delay")
    if delay is None:
        delay_text = ""
    else:
        delay_text = f"{delay:g}s" if isinstance(delay, (int, float)) else f"{delay}s"

    desc = step.get("desc") or ""
    # 🎯 = กดตรงที่เจอภาพ (ตามปุ่มที่ขยับ), 📷 = แค่รอภาพยืนยันหน้าแล้วกดพิกัดเดิม
    anchor_mark = "🎯" if step.get("anchor_tap") else ("📷" if step.get("anchor_img") else "  ")
    return f"{idx + 1:02d}{anchor_mark}{label:<12}  {detail:<28}  {delay_text:<6}  {desc}"


def account_display_name(account):
    """ชื่อที่ใช้ 'แสดงผล' ในโปรแกรม/ล็อก/รายงาน — ใช้ title (จาก Save_Web_Game) ก่อน
    แล้วค่อย ingamename / name / email ตามลำดับ

    หมายเหตุ: นี่คือชื่อสำหรับ 'แสดงให้คนอ่าน' เท่านั้น ไม่ใช่ชื่อที่พิมพ์ลงเกม
    (placeholder {NAME} ในสเต็ปยังใช้ name/ingamename เหมือนเดิม)
    """
    if not account:
        return "-"
    return (account.get("save_web_game_title")
            or account.get("title")
            or account.get("ingamename")
            or account.get("name")
            or account.get("email")
            or "-")


def build_account_summary(account):
    name = account_display_name(account)
    email = account.get("email") or "-"
    group = account.get("group") or "ทั่วไป"
    otp = "OTP" if account.get("refresh_token") else ""
    card_count = account.get("card_count")
    cards = f"Cards:{card_count}" if isinstance(card_count, int) and card_count > 0 else ""
    return f"{name:<16}  {email:<32}  {group:<12}  {cards:<9}  {otp}"

def build_status_summary(total_devices, selected_devices, total_accounts, selected_accounts, macro_steps, profile_name, is_running):
    profile = profile_name.strip() if profile_name else "Custom"
    state = "Running" if is_running else "Ready"
    return (
        f"Emulator: {selected_devices}/{total_devices}  |  "
        f"Accounts: {selected_accounts}/{total_accounts}  |  "
        f"Steps: {macro_steps}  |  "
        f"Profile: {profile}  |  "
        f"Status: {state}"
    )


def build_sequential_macro_pairs(devices, accounts):
    if not devices:
        return []

    if not accounts:
        total = len(devices)
        return [(device, None, idx, total) for idx, device in enumerate(devices)]

    total = len(accounts)
    return [
        (devices[idx % len(devices)], account, idx, total)
        for idx, account in enumerate(accounts)
    ]


# จับคู่ข้อความบางส่วนใน dropdown -> ชนิด step ภายใน (ตรวจตามลำดับ)
STEP_LABEL_MATCHERS = [
    # หมายเหตุ: "Tap Text"/"Wait Text" มีคำว่า "Text" จึงต้องตรวจก่อน matcher "Text"
    ("Tap Text", "tap_text"),
    ("Wait Text", "wait_for_text"),
    ("Text", "text"),
    ("Keyevent", "keyevent"),
    ("Swipe", "swipe"),
    ("Sleep", "sleep"),
    ("Start App", "start_app"),
    ("Stop App", "stop_app"),
    ("Wait Image", "wait_for_image"),
    ("Image Match", "detect_image"),
    ("Clear Ads Loop", "clear_ads_loop"),
    ("Auto Fill OTP", "fetch_otp"),
    ("Read Diamond", "read_diamond"),
    ("อ่านเพชร", "read_diamond"),
    ("Run Set", "run_set"),
    ("ใช้ชุดคำสั่ง", "run_set"),
    ("Story Auto", "story_auto"),
    ("เล่นเนื้อเรื่อง", "story_auto"),
    ("Yellow Stage", "find_yellow_stage"),
    ("ด่านเหลือง", "find_yellow_stage"),
]


def label_to_step_type(label):
    """แปลง label จาก dropdown -> ชนิด step (ค่าเริ่มต้น tap)"""
    for needle, step_type in STEP_LABEL_MATCHERS:
        if needle in label:
            return step_type
    return "tap"


# ค่าหน่วงเวลาเริ่มต้น (วินาที) ต่อชนิด step เมื่อ step ไม่ได้ระบุ delay เอง
DEFAULT_STEP_DELAYS = {
    "tap": 5.0,
    "swipe": 5.0,
    "text": 5.0,
    "keyevent": 0.3,
    "start_app": 1.0,
    "stop_app": 1.0,
    "detect_image": 1.0,
    "wait_for_image": 1.0,
    "tap_text": 1.0,
    "wait_for_text": 1.0,
    "clear_ads_loop": 1.0,
    "fetch_otp": 1.0,
    "screenshot": 1.0,
    "read_diamond": 1.0,
    "story_auto": 1.0,
    "find_yellow_stage": 1.0,
}


# ป้ายไทยของนโยบาย 'ถ้าไม่เจอภาพ anchor' — โชว์ให้ผู้ใช้อ่านเข้าใจ แต่ยังเก็บค่าเดิม (abort/skip/tap)
# ในไฟล์สคริปต์ เพื่อไม่ให้ตัวรัน (gui + macro_runner + เว็บ) หรือสคริปต์เก่าพัง
ANCHOR_ONFAIL_LABELS = [
    ("abort", "หยุดจอนี้ (กันกดมั่ว)"),
    ("skip", "ข้ามสเต็ปนี้ไป"),
    ("tap", "กดตามพิกัดเดิม (เสี่ยง)"),
    ("retry", "วนกลับไปทำขั้นที่เลือกใหม่ (ลองซ้ำ)"),
]
ANCHOR_ONFAIL_TO_LABEL = {v: l for v, l in ANCHOR_ONFAIL_LABELS}
ANCHOR_ONFAIL_FROM_LABEL = {l: v for v, l in ANCHOR_ONFAIL_LABELS}


class ModernButton(tk.Button):
    """ปุ่มกดสไตล์โมเดิร์นพร้อมแอนิเมชันตอนเอาเมาส์ชี้"""
    def __init__(
        self,
        parent,
        text,
        command=None,
        bg=None,
        fg=None,
        activebg=None,
        variant="neutral",
        **kwargs,
    ):
        colors = get_button_colors(variant)
        bg = bg or colors["bg"]
        fg = fg or colors["fg"]
        activebg = activebg or colors["hover"]
        button_font = kwargs.pop("font", ("Segoe UI", 10, "bold"))
        px = kwargs.pop("padx", 12)
        py = kwargs.pop("pady", 7)
        super().__init__(
            parent, 
            text=text, 
            command=command, 
            bg=bg, 
            fg=fg, 
            activebackground=activebg, 
            activeforeground=fg,
            relief="flat", 
            bd=0, 
            cursor="hand2",
            font=button_font,
            padx=px,
            pady=py,
            **kwargs
        )
        self._normal_bg = bg
        self._hover_bg = activebg
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=self._normal_bg))

class ModernEntry(tk.Entry):
    """ช่องกรอกข้อความสไตล์โมเดิร์น"""
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            bg=BG_INPUT,
            fg=FG_WHITE,
            insertbackground=FG_WHITE,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#2B3C55",
            highlightcolor=ACCENT_BLUE,
            font=("Segoe UI", 10),
            **kwargs
        )

class MuMuGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MuMupow - โปรแกรมควบคุมและบอทจำลองหน้าจอพร้อมกันหลายจอ")
        self.geometry("1280x760")
        self.minsize(1180, 720)
        self.configure(bg=BG_DARK)

        # เริ่มต้นโมดูลควบคุม
        self.controller = MuMuController()
        self.macro_thread = None
        self.macro_running = False
        self.editing_email = None

        # หาโฟลเดอร์รันโปรแกรม (รองรับการแปลงเป็นไฟล์ .exe)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        # ตัวแปรสำหรับการจัดการมาโคร
        self.macro_steps = []
        self.profiles = {}
        self.macros_dir = os.path.join(base_dir, "macros")
        os.makedirs(self.macros_dir, exist_ok=True)
        self.script_sets_dir = os.path.join(base_dir, "script_sets")
        os.makedirs(self.script_sets_dir, exist_ok=True)
        self.script_sets = {}
        self.templates_dir = os.path.join(base_dir, "templates")
        os.makedirs(self.templates_dir, exist_ok=True)
        # โฟลเดอร์เก็บ 'รายงานจุดที่ติด' ตอนรัน auto (ภาพหน้าจอ + ข้อมูลขั้น) ไว้ย้อนดูภายหลัง
        self.error_reports_dir = os.path.join(base_dir, "error_reports")
        self._active_profile_name = ""  # ชื่อสคริปต์ที่กำลังรัน (สแนปช็อตตอนกดรัน ให้ worker อ่านได้)
        # สถานะรันสดต่อจอ (device -> status/account/step/done_count) ให้การ์ดความคืบหน้าหน้าแรกอ่านได้
        # เขียนจาก worker thread แต่ key ของแต่ละจอแยกกัน (ไม่มี thread ไหนแก้ key เดียวกันพร้อมกัน) จึงไม่ต้อง lock
        self._device_run_state = {}

        # ตัวแปรสำหรับการรันแบบแบ่งเซ็ต
        self.pause_between_sets = tk.BooleanVar(value=False)
        self.run_sequentially = tk.BooleanVar(value=False)
        self.is_paused_waiting_for_next_set = False
        self.remaining_accounts = []
        self.active_devices_for_run = []
        self.device_active_accounts = {}

        # ระบบ Checkpoint รันต่อจากที่ค้าง (resume) — เก็บความคืบหน้าระดับบัญชีลงไฟล์
        self.run_checkpoint_file = os.path.join(base_dir, "run_checkpoint.json")
        self.run_checkpoint = None
        self.run_checkpoint_lock = None

        # ตัวแปรสำหรับการจัดการบัญชีผู้ใช้
        self.accounts = []
        self.accounts_file = os.path.join(base_dir, "accounts.json")
        self.ports_file = os.path.join(base_dir, "ports.json")
        self.presets_file = os.path.join(base_dir, "presets.json")
        self.coordinate_presets = self.load_coordinate_presets()
        # ระบบอ่านจำนวนเพชร (Diamond OCR) — พื้นที่ครอป + เทมเพลตเลข 0-9
        self.diamond_config_file = os.path.join(base_dir, "diamond_ocr.json")
        self.diamond_digits_dir = os.path.join(self.templates_dir, "diamond_digits")
        self.diamond_config = self.load_diamond_config()
        # ระบบดึงรายชื่อสมาชิกชมรม — พื้นที่คอลัมน์ชื่อสำหรับครอปก่อน OCR
        self.guild_config_file = os.path.join(base_dir, "guild_ocr.json")
        self.guild_config = self.load_guild_config()
        # ระบบรีเซ็ตเกมเมื่อบัญชีติดปัญหา (ปิดเกม+เปิดใหม่+เปิดช่อง login) กันโดมิโน่ในคิว
        self.game_reset_file = os.path.join(base_dir, "game_reset.json")
        self.game_reset_config = self.load_game_reset_config()
        # tessdata ของแอปเอง (มี tha/jpn/kor/chi_sim/chi_tra ที่โหลดเพิ่ม) — ให้ Tesseract อ่านชื่อหลายภาษาได้
        self.guild_tessdata_dir = os.path.join(base_dir, "tessdata")
        try:
            if os.path.isdir(self.guild_tessdata_dir) and glob.glob(
                os.path.join(self.guild_tessdata_dir, "*.traineddata")
            ):
                set_tessdata_dir(self.guild_tessdata_dir)
        except Exception:
            pass
        # Gemini API key สำหรับ Story Auto fallback (ลำดับ: ไฟล์ config -> env -> ว่าง), บันทึกได้จาก Settings
        self.gemini_config_file = os.path.join(base_dir, "gemini_config.json")
        self.gemini_api_key = self._load_gemini_api_key()
        self.account_checkboxes = {} # email -> BooleanVar
        self.group_checkboxes = {}   # group_name -> BooleanVar
        self.load_accounts()

        # ตัวแปรสำหรับการเลือกอุปกรณ์ Emulator
        self.device_checkboxes = {} # device_id -> BooleanVar
        self.device_frames = {}     # device_id -> tk.Frame
        self.device_dot_labels = {} # device_id -> tk.Label (จุดสถานะสดข้างชื่อจอ)
        self.log_expanded = tk.BooleanVar(value=True)

        # กำหนดสไตล์วิดเจ็ตมาตรฐาน
        self.setup_styles()

        # สร้างโครงสร้างหน้าตาโปรแกรม
        self.build_layout()

        # แก้ไขปัญหาคีย์บอร์ดไทยไม่รองรับ Ctrl+C / Ctrl+V
        self.setup_thai_hotkeys()

        # ตรวจสอบ ADB และสแกนอุปกรณ์เริ่มต้น
        self.write_log(f"⚡ เริ่มต้นระบบควบคุม MuMupow แล้ว เส้นทาง ADB: {self.controller.adb_path}", "success")
        self.scan_devices()

        # แจ้งเตือนถ้ามีการรันค้างจากครั้งก่อน (resume)
        self._check_startup_checkpoint()

        # จัดการตอนกดปิดหน้าต่าง (X) ให้ process จบจริง ไม่ค้างใน Task Manager
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

    def on_app_close(self):
        """ปิดโปรแกรมให้สะอาด: หยุด thread + เซฟ + บังคับจบ process

        จำเป็นต้องบังคับจบเพราะโปรแกรมใช้ ThreadPoolExecutor หลายจุด ซึ่ง Python จะ
        join worker รอจนเสร็จตอนปิด ถ้ามี thread ค้าง (เช่น แคปจอ/adb/มาโครยังรัน)
        การ join จะบล็อกค้าง ทำให้หน้าต่างหายแต่ process ยังอยู่
        """
        try:
            if self.macro_running:
                if not messagebox.askyesno(
                    "ปิดโปรแกรม",
                    "บอทกำลังทำงานอยู่ ต้องการปิดโปรแกรมเลยหรือไม่?\n"
                    "(ความคืบหน้าถูกบันทึกไว้แล้ว เปิดใหม่กดรันต่อได้)",
                ):
                    return
        except Exception:
            pass

        # ส่งสัญญาณให้ thread งานหยุด แล้วเซฟสถานะล่าสุด
        self.macro_running = False
        try:
            self.save_accounts()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        # บังคับจบทันที ข้ามการ join ของ ThreadPoolExecutor ที่อาจค้าง
        os._exit(0)

    def make_panel(self, parent, title=None, fill="both", expand=False, padx=0, pady=0, manager="pack"):
        """Create a styled panel; use manager=None when the caller will grid/place/pack it."""
        panel = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=LINE_SOFT)
        if manager == "pack":
            panel.pack(fill=fill, expand=expand, padx=padx, pady=pady)
        elif manager is not None:
            raise ValueError("Unsupported panel manager")
        if title:
            header = tk.Frame(panel, bg=BG_PANEL, height=38)
            header.pack(fill="x")
            header.pack_propagate(False)
            tk.Label(
                header,
                text=title,
                bg=BG_PANEL,
                fg=FG_WHITE,
                font=("Segoe UI", 10, "bold"),
            ).pack(side="left", padx=12)
            body = tk.Frame(panel, bg=BG_CARD, padx=12, pady=12)
            body.pack(fill="both", expand=True)
            return panel, body
        return panel, panel

    def make_toolbar(self, parent):
        toolbar = tk.Frame(parent, bg=BG_CARD)
        toolbar.pack(fill="x", pady=(0, 10))
        return toolbar

    def make_checkbutton(self, parent, text, variable, **kwargs):
        return tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bg=kwargs.pop("bg", BG_CARD),
            fg=kwargs.pop("fg", FG_WHITE),
            activebackground=kwargs.pop("activebackground", BG_CARD),
            activeforeground=kwargs.pop("activeforeground", FG_WHITE),
            selectcolor=kwargs.pop("selectcolor", BG_INPUT),
            relief="flat",
            font=kwargs.pop("font", ("Segoe UI", 10)),
            **kwargs,
        )

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("default")
        
        # ปรับแต่งแถบแท็บ (Notebook)
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG_PANEL,
            foreground=FG_MUTED,
            padding=[14, 8],
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_CARD)],
            foreground=[("selected", FG_WHITE)],
        )

        # ปรับแต่งแถบเลื่อน (Scrollbar)
        style.configure(
            "TScrollbar",
            gripcount=0,
            background=BG_PANEL,
            troughcolor=BG_DARK,
            borderwidth=0,
            arrowcolor=FG_MUTED,
        )

        # ปรับแต่งเส้นแบ่งลากได้ (PanedWindow) ให้เข้ากับธีมมืด แทนสีเทาอ่อนดีฟอลต์
        style.configure("TPanedwindow", background=BG_DARK)
        style.configure("Sash", sashthickness=6, gripcount=0)

    def setup_thai_hotkeys(self):
        """แก้ไขปัญหาปุ่มลัด Ctrl+C, Ctrl+V, Ctrl+A, Ctrl+X ไม่ทำงานเมื่อผู้ใช้เปลี่ยนเป็นคีย์บอร์ดภาษาไทย"""
        def handle_entry_ctrl(event):
            # บน Windows keycode: 65=A, 67=C, 86=V, 88=X (ทำงานได้ทั้งโหมดไทยและอังกฤษ)
            if event.keycode == 65: # Select All (เลือกทั้งหมด)
                event.widget.select_range(0, tk.END)
                event.widget.icursor(tk.END)
                return "break"
            elif event.keycode == 67: # Copy (คัดลอก)
                event.widget.event_generate("<<Copy>>")
                return "break"
            elif event.keycode == 86: # Paste (วาง)
                event.widget.event_generate("<<Paste>>")
                return "break"
            elif event.keycode == 88: # Cut (ตัด)
                event.widget.event_generate("<<Cut>>")
                return "break"

        def handle_text_ctrl(event):
            if event.keycode == 65: # Select All (เลือกทั้งหมด)
                event.widget.tag_add("sel", "1.0", "end")
                return "break"
            elif event.keycode == 67: # Copy (คัดลอก)
                event.widget.event_generate("<<Copy>>")
                return "break"
            elif event.keycode == 86: # Paste (วาง)
                event.widget.event_generate("<<Paste>>")
                return "break"
            elif event.keycode == 88: # Cut (ตัด)
                event.widget.event_generate("<<Cut>>")
                return "break"

        self.bind_class("Entry", "<Control-KeyPress>", handle_entry_ctrl)
        self.bind_class("Text", "<Control-KeyPress>", handle_text_ctrl)

    def bind_canvas_mousewheel(self, canvas):
        """Binds mouse wheel scrolling to the canvas and all its children."""
        def _on_mousewheel(event):
            curr = event.widget
            while curr:
                if curr == canvas:
                    if event.delta:
                        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    elif event.num == 4:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(1, "units")
                    return "break"
                try:
                    curr = curr.master
                except AttributeError:
                    break
        
        self.bind_all("<MouseWheel>", _on_mousewheel, add="+")
        self.bind_all("<Button-4>", _on_mousewheel, add="+")
        self.bind_all("<Button-5>", _on_mousewheel, add="+")

    def build_layout(self):
        # 1. แถบส่วนหัวโปรแกรม (Header)
        header = tk.Frame(self, bg=BG_PANEL, height=58)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_lbl = tk.Label(
            header,
            text="MuMupow",
            bg=BG_PANEL,
            fg=FG_WHITE,
            font=("Segoe UI", 16, "bold"),
        )
        title_lbl.pack(side="left", padx=(20, 12), pady=14)

        subtitle_lbl = tk.Label(
            header,
            text="คุมและบอทหลายจอพร้อมกัน",
            bg=BG_PANEL,
            fg=FG_MUTED,
            font=("Segoe UI", 10),
        )
        subtitle_lbl.pack(side="left", pady=18)

        self.build_status_bar()

        # 2. พื้นที่เนื้อหาหลัก + คอนโซล Log ด้านล่าง — ห่อด้วย PanedWindow แนวตั้งเพื่อให้ลากปรับความสูง
        #    ของแผง Log ได้ (เส้นแบ่งลากได้), ส่วนแนวนอนข้างในก็ห่อด้วย PanedWindow เช่นกัน
        #    เพื่อให้ลากปรับความกว้างแถบซ้าย/เนื้อหาหลักได้ตามที่แต่ละคนต้องการ
        root_paned = ttk.PanedWindow(self, orient="vertical")
        root_paned.pack(fill="both", expand=True, padx=10, pady=10)
        self._root_paned = root_paned

        content_frame = tk.Frame(root_paned, bg=BG_DARK)
        root_paned.add(content_frame, weight=5)

        # แถบไอคอนซ้ายสุด (สลับหน้า) — ความกว้างคงที่ ไม่ต้องลากปรับ
        self.build_nav_rail(content_frame)

        # แถบจัดการอุปกรณ์ (ลากปรับได้) -> เนื้อหาหลัก (ลากปรับได้)
        content_h_paned = ttk.PanedWindow(content_frame, orient="horizontal")
        content_h_paned.pack(fill="both", expand=True, side="left")
        self._content_h_paned = content_h_paned

        sidebar = self.build_sidebar(content_h_paned)
        content_h_paned.add(sidebar, weight=0)
        tabs_panel = self.build_tabs_panel(content_h_paned)
        content_h_paned.add(tabs_panel, weight=1)

        # 3. แผงคอนโซล Log บันทึกระบบด้านล่างสุด (ลากปรับความสูงได้)
        self.build_log_panel(root_paned)
        root_paned.add(self.log_frame, weight=0)

        self.after(200, self._init_sash_positions)
        self.update_status_summary()

    def _init_sash_positions(self):
        """ตั้งตำแหน่งเส้นแบ่งเริ่มต้นให้ใกล้เคียงของเดิม (ลากปรับต่อได้อิสระหลังจากนี้)
        ต้องบังคับ update_idletasks() ก่อนอ่าน winfo_height() ไม่งั้นค่าที่ได้อาจยังเป็นขนาด
        ตอนเพิ่งสร้าง widget (เล็กกว่าจริง) ทำให้เส้นแบ่งเด้งไปผิดตำแหน่ง (แผง log บวมเต็มจอ)"""
        self.update_idletasks()
        try:
            self._content_h_paned.sashpos(0, 260)
        except Exception:
            pass
        try:
            total_h = self._root_paned.winfo_height()
            if total_h < 200:  # ยังไม่ได้ขนาดจริง (เช่น ยังไม่วาดเสร็จ) -> ลองใหม่อีกครั้ง
                self.after(200, self._init_sash_positions)
                return
            self._root_paned.sashpos(0, max(80, total_h - 130))
        except Exception:
            pass

    def build_status_bar(self):
        status_frame = tk.Frame(self, bg=BG_PANEL, height=34)
        status_frame.pack(fill="x", side="top")
        status_frame.pack_propagate(False)

        self.status_summary_lbl = tk.Label(
            status_frame,
            text="",
            bg=BG_PANEL,
            fg=FG_WHITE,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.status_summary_lbl.pack(side="left", fill="x", expand=True, padx=20)

        self.status_hint_lbl = tk.Label(
            status_frame,
            text="เลือก Emulator + บัญชี + มาโคร แล้วกดรัน",
            bg=BG_PANEL,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
            anchor="e",
        )
        self.status_hint_lbl.pack(side="right", padx=20)

    def update_status_summary(self):
        if not hasattr(self, "status_summary_lbl"):
            return

        total_devices = len(self.device_checkboxes)
        selected_devices = sum(1 for var in self.device_checkboxes.values() if var.get())
        total_accounts = len(self.accounts)

        if self.account_checkboxes:
            selected_accounts = sum(1 for var in self.account_checkboxes.values() if var.get())
        else:
            selected_accounts = sum(1 for acc in self.accounts if acc.get("checked", True))

        profile_name = ""
        if hasattr(self, "profile_cb"):
            profile_name = self.profile_cb.get()

        self.status_summary_lbl.configure(
            text=build_status_summary(
                total_devices=total_devices,
                selected_devices=selected_devices,
                total_accounts=total_accounts,
                selected_accounts=selected_accounts,
                macro_steps=len(self.macro_steps),
                profile_name=profile_name,
                is_running=self.macro_running,
            )
        )

        # ป้ายเชื่อมต่อจอในแถบซ้าย (เช็คว่าต่อ MuMu ครบยัง)
        if hasattr(self, "conn_status_lbl"):
            if total_devices > 0:
                self.conn_status_lbl.configure(
                    text=f"🟢 เชื่อมต่อ {total_devices} จอ (เลือก {selected_devices})", fg=ACCENT_GREEN)
            else:
                self.conn_status_lbl.configure(text="🔌 ยังไม่พบจอ — กดสแกนพอร์ต", fg=ACCENT_ORANGE)

        # การ์ด 'พร้อมรันไหม?' บนหน้าแรก
        if hasattr(self, "_pf_devices"):
            steps = len(self.macro_steps)
            ok_c, no_c = ACCENT_GREEN, ACCENT_ORANGE
            self._pf_devices.configure(text=f"{'✓' if selected_devices else '✗'} จอที่เลือก: {selected_devices} จอ",
                                       fg=ok_c if selected_devices else no_c)
            self._pf_accounts.configure(text=f"{'✓' if selected_accounts else '✗'} บัญชีที่จะทำ: {selected_accounts} รหัส",
                                        fg=ok_c if selected_accounts else no_c)
            self._pf_script.configure(text=f"{'✓' if steps else '✗'} สคริปต์: {profile_name or '-'} · {steps} สเต็ป",
                                      fg=ok_c if steps else no_c)
            warns = []
            if not selected_devices: warns.append("ยังไม่เลือกจอ (ติ๊กทางซ้าย)")
            if not selected_accounts: warns.append("ยังไม่เลือกบัญชี (แท็บบัญชี)")
            if not steps: warns.append("ยังไม่มีสคริปต์")
            self._pf_warn.configure(text=("⚠️ " + " · ".join(warns)) if warns else "✅ พร้อมรันแล้ว",
                                    fg=no_c if warns else ok_c)


    def build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=BG_PANEL, width=260)

        # หัวข้อแถบซ้าย
        lbl = tk.Label(sidebar, text="จัดการอุปกรณ์ Emulator", bg=BG_PANEL, fg=FG_WHITE, font=("Segoe UI", 12, "bold"))
        lbl.pack(fill="x", padx=15, pady=(15, 10), anchor="w")

        # ปุ่มแสกนพอร์ตหลัก
        btn_frame = tk.Frame(sidebar, bg=BG_PANEL)
        btn_frame.pack(fill="x", padx=15, pady=5)

        scan_btn = ModernButton(btn_frame, text="สแกนพอร์ต", command=self.scan_devices, variant="accent")
        scan_btn.pack(fill="x", side="top", pady=2)

        # ป้ายสถานะการเชื่อมต่อจอ (เช็คได้ทันทีว่าต่อ MuMu ครบยัง)
        self.conn_status_lbl = tk.Label(sidebar, text="🔌 ยังไม่พบจอ", bg=BG_PANEL, fg=ACCENT_ORANGE,
                                        font=("Segoe UI", 10, "bold"), anchor="w")
        self.conn_status_lbl.pack(fill="x", padx=15, pady=(6, 0))

        # กล่องสำหรับระบุพอร์ตเองแมนนวล
        conn_frame = tk.Frame(sidebar, bg=BG_PANEL)
        conn_frame.pack(fill="x", padx=15, pady=10)
        
        tk.Label(conn_frame, text="เชื่อมต่อด้วย IP:Port เอง", bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        self.manual_port_entry = ModernEntry(conn_frame)
        self.manual_port_entry.pack(fill="x", side="left", expand=True, pady=5, padx=(0, 5))
        self.manual_port_entry.insert(0, "127.0.0.1:7555")

        connect_btn = ModernButton(conn_frame, text="เชื่อมต่อ", command=self.manual_connect, variant="primary")
        connect_btn.pack(side="right")

        # กล่องเลือกจอที่จะควบคุม
        tk.Label(sidebar, text="เลือก Emulator ที่จะควบคุม:", bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(10, 2))

        # คอนเทนเนอร์สำหรับจัดกลุ่มเช็คลิสต์
        list_container = tk.Frame(sidebar, bg=BG_DARK, bd=0)
        list_container.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Canvas และสกรอลบาร์สำหรับลิสต์รายชื่อจอ
        self.device_canvas = tk.Canvas(list_container, bg=BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.device_canvas.yview)
        
        self.device_scroll_frame = tk.Frame(self.device_canvas, bg=BG_DARK)
        self.device_scroll_frame.bind(
            "<Configure>", 
            lambda e: self.device_canvas.configure(scrollregion=self.device_canvas.bbox("all"))
        )
        
        device_window_id = self.device_canvas.create_window((0, 0), window=self.device_scroll_frame, anchor="nw")
        # ปรับความกว้างของลิสต์ให้เต็มขนาด canvas เสมอ — สำคัญเพราะตอนนี้แถบซ้ายลากปรับความกว้างได้
        # (ถ้าไม่ทำ ลิสต์จะค้างความกว้าง 230px เดิม ล้นหรือแคบเกินความจริงตอนลากปรับ)
        self.device_canvas.bind("<Configure>", lambda e: self.device_canvas.itemconfigure(device_window_id, width=e.width))
        self.device_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.device_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(self.device_canvas)
        return sidebar

    # นิยามหน้า: key -> (ไอคอน, ป้ายชื่อ, ฟังก์ชันสร้างเนื้อหา, ปักไว้ล่างแถบไหม)
    _NAV_PAGES = [
        ("home", "▶", "หน้าแรก", "build_home_tab", False),
        ("accounts", "👥", "บัญชี", "build_accounts_tab", False),
        ("script", "✏️", "สคริปต์", "build_macro_tab", False),
        ("other", "🔧", "อื่นๆ", "build_sync_tab", False),
        ("settings", "⚙️", "ตั้งค่า", "build_settings_tab", True),
    ]

    def build_tabs_panel(self, parent):
        """สร้างพื้นที่เนื้อหาหลัก — สลับหน้าด้วยแถบไอคอนซ้าย (build_nav_rail) แทนแท็บบน
        เก็บเป็น Frame ธรรมดาต่อหน้า (ไม่ใช้ ttk.Notebook) โชว์/ซ่อนเองผ่าน select_page()"""
        content = tk.Frame(parent, bg=BG_DARK)

        self._pages = {}
        self._page_order = [k for k, *_ in self._NAV_PAGES]
        for key, _icon, _label, builder_name, _pin_bottom in self._NAV_PAGES:
            page = tk.Frame(content, bg=BG_DARK)
            getattr(self, builder_name)(page)
            self._pages[key] = page
        self.settings_tab = self._pages["settings"]     # เผื่อโค้ดเดิมอ้างชื่อนี้
        self._accounts_tab_widget = self._pages["accounts"]

        self.select_page("home")
        return content

    def select_page(self, key):
        """สลับไปแสดงหน้า key (ซ่อนหน้าอื่นทั้งหมด) + ไฮไลท์ปุ่มแถบไอคอนซ้ายให้ตรง"""
        if key not in self._pages:
            return
        self._current_page = key
        for k, page in self._pages.items():
            if k == key:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        for k, (frame, icon_lbl, text_lbl) in getattr(self, "_nav_items", {}).items():
            active = (k == key)
            bg = BG_HOVER if active else BG_PANEL
            fg = ACCENT_BLUE if active else FG_MUTED
            frame.configure(bg=bg)
            icon_lbl.configure(bg=bg, fg=fg)
            text_lbl.configure(bg=bg, fg=fg)
        # สลับมาแท็บบัญชีตอนกำลังรันอยู่ -> รีเฟรชจุดสถานะ 🔵กำลังทำ ให้ตรงปัจจุบัน
        if key == "accounts" and self.macro_running:
            self.refresh_accounts_ui()

    def build_nav_rail(self, parent):
        """แถบไอคอนซ้ายสุด (แทนแท็บบน) — คลิกสลับหน้า, 'ตั้งค่า' ปักไว้ล่างสุด"""
        rail = tk.Frame(parent, bg=BG_PANEL, width=72)
        rail.pack(fill="y", side="left", padx=(0, 12))
        rail.pack_propagate(False)

        mark = tk.Label(rail, text="🎮", bg=BG_PANEL, fg=ACCENT_BLUE, font=("Segoe UI", 18))
        mark.pack(pady=(16, 10))

        self._nav_items = {}

        def add_item(key, icon, label, side="top"):
            item = tk.Frame(rail, bg=BG_PANEL, cursor="hand2")
            item.pack(fill="x", side=side, pady=2)
            icon_lbl = tk.Label(item, text=icon, bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 15))
            icon_lbl.pack(pady=(8, 0))
            text_lbl = tk.Label(item, text=label, bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 8))
            text_lbl.pack(pady=(0, 8))
            for w in (item, icon_lbl, text_lbl):
                w.bind("<Button-1>", lambda e, k=key: self.select_page(k))
            self._nav_items[key] = (item, icon_lbl, text_lbl)

        for key, icon, label, _builder, pin_bottom in self._NAV_PAGES:
            add_item(key, icon, label, side="bottom" if pin_bottom else "top")

    def build_home_tab(self, parent):
        """หน้าแรก: เลือกสคริปต์ที่จะรัน + ปุ่มรัน/หยุด + ความคืบหน้าต่อจอ (เรียก logic เดิม)"""
        parent.configure(bg=BG_DARK)
        main_pane = ttk.PanedWindow(parent, orient="horizontal")
        main_pane.pack(fill="both", expand=True)

        # ซ้าย: เลือกสคริปต์ + ปุ่มรัน/หยุด + ตัวเลือกการรัน
        left = tk.Frame(main_pane, bg=BG_CARD, width=380, highlightthickness=1, highlightbackground=LINE_SOFT)
        main_pane.add(left, weight=3)

        # ปุ่มรัน/หยุดต้องเห็นตลอดเวลาไม่ว่าจะบีบแผง/หน้าต่างแคบแค่ไหน -> แพคก่อนเป็นอันดับแรก
        # (จองพื้นที่จากขอบล่างก่อน) ส่วนเนื้อหาด้านบนที่อาจยาวเกินพื้นที่เหลือ ห่อด้วย canvas เลื่อนได้
        # แทน — เดิมแพคทุกอย่างต่อกันตรงๆ ไม่มีสกรอล พอหน้าต่างถูกย่อ ปุ่มรัน/หยุดที่แพคทีหลังเลย
        # โดนตัดจนมองไม่เห็น (pack ให้พื้นที่ตามลำดับแพค ไม่ใช่ตาม side เพียงอย่างเดียว)
        self.build_run_controls(left)

        top_canvas = tk.Canvas(left, bg=BG_CARD, highlightthickness=0)
        top_scrollbar = ttk.Scrollbar(left, orient="vertical", command=top_canvas.yview)
        top_inner = tk.Frame(top_canvas, bg=BG_CARD)
        top_inner.bind("<Configure>", lambda e: top_canvas.configure(scrollregion=top_canvas.bbox("all")))
        top_window_id = top_canvas.create_window((0, 0), window=top_inner, anchor="nw")
        top_canvas.bind("<Configure>", lambda e: top_canvas.itemconfigure(top_window_id, width=e.width))
        top_canvas.configure(yscrollcommand=top_scrollbar.set)
        top_canvas.pack(side="top", fill="both", expand=True)
        top_scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(top_canvas)

        pad = tk.Frame(top_inner, bg=BG_CARD); pad.pack(fill="x", padx=16, pady=16)
        tk.Label(pad, text="เลือกสคริปต์ที่จะรัน", bg=BG_CARD, fg=FG_WHITE,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(pad, text="1) ติ๊กจอทางซ้าย   2) เลือกสคริปต์   3) กดรัน", bg=BG_CARD, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 10))
        self.profile_cb = ttk.Combobox(pad, state="readonly", font=("Segoe UI", 11))
        self.profile_cb.pack(fill="x", ipady=4)
        self.profile_cb.bind("<<ComboboxSelected>>", self.on_profile_select)

        # การ์ด 'พร้อมรันไหม?' — เช็คก่อนกดว่าตั้งครบ (เติมช่องว่าง + กันกดรันแล้วไม่มีอะไรเกิด)
        pf = tk.Frame(top_inner, bg=BG_PANEL, highlightthickness=1, highlightbackground=LINE_SOFT)
        pf.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(pf, text="พร้อมรันไหม?", bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
        self._pf_devices = tk.Label(pf, text="", bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 10), anchor="w")
        self._pf_devices.pack(fill="x", padx=12, pady=1)
        self._pf_accounts = tk.Label(pf, text="", bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 10), anchor="w")
        self._pf_accounts.pack(fill="x", padx=12, pady=1)
        self._pf_script = tk.Label(pf, text="", bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 10), anchor="w")
        self._pf_script.pack(fill="x", padx=12, pady=1)
        self._pf_warn = tk.Label(pf, text="", bg=BG_PANEL, fg=ACCENT_ORANGE, font=("Segoe UI", 9),
                                 anchor="w", wraplength=330, justify="left")
        self._pf_warn.pack(fill="x", padx=12, pady=(4, 10))
        self._bind_responsive_wraplength(self._pf_warn, pf, padding=24)

        # ขวา: ความคืบหน้าต่อจอ (จำลองสถานะให้ดูระหว่างรัน)
        right = tk.Frame(main_pane, bg=BG_CARD, width=320, highlightthickness=1, highlightbackground=LINE_SOFT)
        right.pack_propagate(False)
        main_pane.add(right, weight=1)
        tk.Label(right, text="ความคืบหน้าต่อจอ", bg=BG_CARD, fg=FG_WHITE,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(14, 2))
        tk.Label(right, text="แต่ละจอทำรหัสไหน/สถานะ (ดูรายละเอียดเต็มที่ Log)", bg=BG_CARD,
                 fg=FG_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(0, 6))
        ModernButton(right, text="📁 เปิดรายงานปัญหา (ภาพจุดที่ติด)", command=self.open_error_reports_folder,
                     variant="subtle", font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(0, 8))

        # รายการความคืบหน้าอาจยาวเกินพื้นที่ (เช่นเลือกหลายสิบจอ) -> ห่อด้วย canvas เลื่อนได้เช่นกัน
        progress_canvas = tk.Canvas(right, bg=BG_CARD, highlightthickness=0)
        progress_scrollbar = ttk.Scrollbar(right, orient="vertical", command=progress_canvas.yview)
        self.home_progress_frame = tk.Frame(progress_canvas, bg=BG_CARD)
        self.home_progress_frame.bind("<Configure>", lambda e: progress_canvas.configure(scrollregion=progress_canvas.bbox("all")))
        progress_window_id = progress_canvas.create_window((0, 0), window=self.home_progress_frame, anchor="nw")
        progress_canvas.bind("<Configure>", lambda e: progress_canvas.itemconfigure(progress_window_id, width=e.width))
        progress_canvas.configure(yscrollcommand=progress_scrollbar.set)
        progress_canvas.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=(0, 12))
        progress_scrollbar.pack(side="right", fill="y", pady=(0, 12))
        self.bind_canvas_mousewheel(progress_canvas)
        self._home_progress_sig = None
        self._tick_home_progress()

    def build_run_controls(self, parent):
        """การ์ดปุ่มรัน + ตัวเลือกการรัน (stagger/anchor/pause/sequential/run/stop) —
        แยกออกมาให้หน้าแรกเรียกใช้ ปุ่ม/ตัวแปรยังเป็น self.* เดิม โค้ดรันไม่ต้องแก้"""
        run_card = tk.Frame(parent, bg=BG_PANEL, highlightthickness=1, highlightbackground=LINE_SOFT, padx=12, pady=12)
        run_card.pack(side="bottom", fill="x", padx=12, pady=(12, 12))

        # หมายเหตุ: ตัดช่อง 'หน่วงเริ่มแต่ละจอ' + 'รันทีละจอ' ออก (เคยไว้ชะลอตอนสมัคร แต่ captcha
        # เด้งที่ 5 ครั้งอยู่ดี เลยไร้ผล) — logic เบื้องหลังยังอยู่ (self.run_sequentially ดีฟอลต์ False
        # = รันขนานปกติ, ส่วน stagger มี hasattr guard ในตัวรัน) เผื่ออยากเปิดคืนภายหลัง
        anchor_frame = tk.Frame(run_card, bg=BG_PANEL)
        anchor_frame.pack(fill="x", pady=2)
        tk.Label(anchor_frame, text="🖼️ ความถี่เช็ค Anchor (วิ):", bg=BG_PANEL, fg=FG_WHITE,
                 font=("Segoe UI", 10)).pack(side="left")
        self._anchor_poll_interval = 0.5
        self._anchor_poll_var = tk.StringVar(value="0.5")
        self._anchor_poll_var.trace_add("write", lambda *a: self._update_anchor_poll())
        ModernEntry(anchor_frame, textvariable=self._anchor_poll_var, width=8).pack(side="left", padx=10)
        tk.Label(anchor_frame, text="มาก = กิน CPU น้อยลง แนะนำ 1-2 ถ้ารันหลายจอ",
                 bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 9, "italic")).pack(side="left")

        self.pause_chk = self.make_checkbutton(run_card,
            "⏸️ หยุดรอตรวจทานทีละชุด (Pause between sets)",
            variable=self.pause_between_sets, bg=BG_PANEL, activebackground=BG_PANEL)
        self.pause_chk.pack(anchor="w", pady=(5, 8))

        self.run_macro_btn = ModernButton(run_card, text="▶  รัน", command=self.start_macro_flow,
                 variant="primary", font=("Segoe UI", 12, "bold"), height=2)
        self.run_macro_btn.pack(fill="x", pady=2)
        self.stop_macro_btn = ModernButton(run_card, text="■  หยุดทันที", command=self.stop_macro_flow,
                 variant="danger", font=("Segoe UI", 12, "bold"), height=2)
        self.stop_macro_btn.pack(fill="x", pady=2)
        self.stop_macro_btn.configure(state="disabled")

    # สถานะ -> (label ไทย, สีจุด, สีตัวหนังสือสถานะ)
    _STATUS_STYLE = {
        "queued":  ("รอคิว", FG_MUTED, FG_MUTED),
        "running": ("กำลังรัน", ACCENT_BLUE, ACCENT_BLUE),
        "done":    ("เสร็จแล้ว", ACCENT_GREEN, "#2DD4A7"),
        "stopped": ("หยุดแล้ว", FG_MUTED, FG_MUTED),
        "stuck":   ("ติด · บันทึกแล้ว", ACCENT_RED, "#F87171"),
    }

    def _bind_responsive_wraplength(self, label, container, padding=24, minimum=120):
        """ผูก wraplength ของ label ให้ตามความกว้างจริงของ container เสมอ — กันข้อความล้นออกนอกแผง
        ตอนผู้ใช้ลากปรับแผงให้แคบลง (แต่เดิม wraplength เป็นเลขคงที่ ไม่รู้จักขนาดแผงที่ลากปรับได้แล้ว)"""
        def _update(event=None):
            w = container.winfo_width()
            if w > 1:
                label.configure(wraplength=max(minimum, w - padding))
        container.bind("<Configure>", _update, add="+")
        label.after(50, _update)

    def _mini_bar(self, parent, frac, color, width=140, height=6):
        """แถบความคืบหน้าบางๆ (ไม่มี widget bar สำเร็จรูปใน Tkinter — ประกอบเองจาก Frame ซ้อน)"""
        frac = max(0.0, min(1.0, frac))
        track = tk.Frame(parent, bg=BG_PANEL, width=width, height=height)
        track.pack_propagate(False)
        if frac > 0:
            tk.Frame(track, bg=color, width=max(2, int(width * frac)), height=height).place(x=0, y=0)
        return track

    def _tick_home_progress(self):
        """รีเฟรชการ์ดความคืบหน้าต่อจอบนหน้าแรก (รีสร้างเฉพาะตอนข้อมูลเปลี่ยน กันกระพริบ)
        แสดงละเอียดแบบ: สถานะ/บัญชี/ขั้นที่กำลังทำ (N/total)/จำนวนบัญชีที่ทำสำเร็จ/แถบความคืบหน้า"""
        if not hasattr(self, "home_progress_frame") or not self.home_progress_frame.winfo_exists():
            return
        self._refresh_device_dots()
        devices = [d for d, v in self.device_checkboxes.items() if v.get()] or list(self.device_checkboxes)
        active = getattr(self, "device_active_accounts", {}) or {}
        run_state = getattr(self, "_device_run_state", {}) or {}
        sig = (self.macro_running, tuple(devices), tuple(
            (run_state.get(d, {}).get("status"), run_state.get(d, {}).get("account_name"),
             run_state.get(d, {}).get("step_idx"), run_state.get(d, {}).get("done_count"),
             account_display_name(active.get(d)) if active.get(d) else "")
            for d in devices))
        if sig != self._home_progress_sig:
            self._home_progress_sig = sig
            for w in self.home_progress_frame.winfo_children():
                w.destroy()
            if not devices:
                tk.Label(self.home_progress_frame, text="ยังไม่ได้เลือกจอ — ติ๊กจอทางซ้าย",
                         bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=4)
            for d in devices:
                st = run_state.get(d)
                acc = active.get(d)
                if st:  # โหมดรันที่เดินสถานะละเอียดไว้ (คิวปกติ)
                    label, dot, status_fg = self._STATUS_STYLE.get(st["status"], ("-", FG_MUTED, FG_MUTED))
                    who = st.get("account_name") or "-"
                    step_idx, step_total = st.get("step_idx", 0), st.get("step_total", 0)
                    step_desc = st.get("step_desc", "")
                    done_c, total_c = st.get("done_count", 0), st.get("total_accounts", 0)
                    frac = (step_idx / step_total) if step_total else 0.0
                else:  # โหมดอื่น (sequential/pause-between-sets) — ยังไม่เดินสถานะละเอียด ใช้ข้อมูลย่อ
                    running = self.macro_running and acc is not None
                    label = "กำลังรัน" if running else ("รอคิว" if self.macro_running else "ยังไม่เริ่ม")
                    dot = ACCENT_BLUE if running else FG_MUTED
                    status_fg = dot
                    who = account_display_name(acc) if acc else "-"
                    step_idx = step_total = done_c = total_c = 0
                    step_desc = ""
                    frac = 0.0

                card = tk.Frame(self.home_progress_frame, bg=BG_INPUT, highlightthickness=1, highlightbackground=LINE_SOFT)
                card.pack(fill="x", pady=3)
                top = tk.Frame(card, bg=BG_INPUT); top.pack(fill="x", padx=8, pady=(6, 0))
                tk.Label(top, text="●", bg=BG_INPUT, fg=dot, font=("Segoe UI", 10)).pack(side="left")
                tk.Label(top, text=d.replace("127.0.0.1:", "จอ "), bg=BG_INPUT, fg=FG_WHITE,
                         font=("Segoe UI", 9, "bold")).pack(side="left", padx=(4, 6))
                tk.Label(top, text=label, bg=BG_INPUT, fg=status_fg, font=("Segoe UI", 8, "bold")).pack(side="left")
                if total_c:
                    tk.Label(top, text=f"{done_c} / {total_c}", bg=BG_INPUT, fg=FG_MUTED,
                             font=("Segoe UI", 8)).pack(side="right")

                mid = tk.Frame(card, bg=BG_INPUT); mid.pack(fill="x", padx=8, pady=(1, 4))
                step_txt = f"{who} · {step_desc} ({step_idx}/{step_total})" if step_total else who
                # การ์ดนี้ถูกสร้างใหม่ทุกรอบรีเฟรชอยู่แล้ว -> คำนวณ wraplength จากความกว้างจริงของแผง
                # ตอนนั้นเลย ไม่ต้องผูก <Configure> เพิ่ม (กันข้อความล้นตอนแผงขวาถูกลากแคบ/กว้าง)
                panel_w = self.home_progress_frame.winfo_width()
                wrap = max(120, panel_w - 90) if panel_w > 1 else 260
                tk.Label(mid, text=step_txt, bg=BG_INPUT, fg=FG_MUTED, font=("Segoe UI", 8),
                         anchor="w", wraplength=wrap).pack(side="left", fill="x", expand=True)
                if step_total:
                    self._mini_bar(mid, frac, dot).pack(side="right", padx=(6, 0))
        self.after(1200 if self.macro_running else 2500, self._tick_home_progress)

    def build_macro_tab(self, parent):
        parent.configure(bg=BG_DARK)

        main_pane = ttk.PanedWindow(parent, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=0, pady=0)

        # ฝั่งซ้าย: จัดการโปรไฟล์และรายการคำสั่ง (Left Panel)
        left_panel = tk.Frame(main_pane, bg=BG_CARD, width=360, highlightthickness=1, highlightbackground=LINE_SOFT)
        main_pane.add(left_panel, weight=3)
        
        # (ตัวเลือกโปรไฟล์ 'เลือกสคริปต์ที่จะรัน' ย้ายไปหน้าแรก — ที่นี่เหลือแค่บันทึก/แก้ไข)
        tk.Label(left_panel, text="แก้ไขสคริปต์ที่โหลดอยู่ (เลือกสคริปต์ได้ที่หน้าแรก)",
                 bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic")).pack(anchor="w", pady=(5, 2))

        # ฟิลด์ป้อนชื่อบันทึกโปรไฟล์
        prof_act_frame = tk.Frame(left_panel, bg=BG_CARD)
        prof_act_frame.pack(fill="x", pady=2)
        
        tk.Label(prof_act_frame, text="ชื่อโปรไฟล์:", bg=BG_CARD, fg=FG_WHITE).pack(side="left")
        self.profile_name_entry = ModernEntry(prof_act_frame)
        self.profile_name_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.profile_name_entry.insert(0, "default_login_ads")
        
        # ตารางปุ่มดำเนินการโปรไฟล์และแพ็คเกจ (2x2 Grid) เพื่อความเรียบร้อยและประหยัดพื้นที่
        profile_actions_frame = self.make_toolbar(left_panel)
        ModernButton(profile_actions_frame, text="บันทึก", command=self.save_profile, variant="primary").pack(side="left", padx=(0, 6))
        ModernButton(profile_actions_frame, text="ลบ", command=self.delete_profile, variant="danger").pack(side="left", padx=(0, 6))
        ModernButton(profile_actions_frame, text="Export", command=self.export_profile_package, variant="neutral").pack(side="left", padx=(0, 6))
        ModernButton(profile_actions_frame, text="Import", command=self.import_profile_package, variant="neutral").pack(side="left", padx=(0, 6))

        quick_builder_frame = self.make_toolbar(left_panel)
        ModernButton(quick_builder_frame, text="สร้างสคริปต์เร็ว", command=self.open_quick_builder_dialog, variant="warning").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(quick_builder_frame, text="จัดการ Sets", command=self.open_script_sets_dialog, variant="accent").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(quick_builder_frame, text="🔀 ผังงาน", command=self.open_flow_view, variant="primary").pack(side="left", fill="x", expand=True)
        
        # ลิสต์ขั้นตอนการทำงาน (Listbox) - ป้องกันการหลุดการเลือกด้วย exportselection=False
        list_frame = tk.Frame(left_panel, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True, pady=5)
        
        self.step_listbox = tk.Listbox(
            list_frame,
            bg=BG_INPUT,
            fg=FG_WHITE,
            selectbackground="#102F48",
            selectforeground=FG_WHITE,
            bd=0,
            highlightthickness=1,
            highlightbackground=LINE_SOFT,
            font=("Consolas", 10),
            activestyle="none",
            exportselection=False,
        )
        self.step_listbox.pack(side="left", fill="both", expand=True)
        self.step_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.step_listbox.yview)
        self.step_listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        
        # ปุ่มจัดลำดับย้ายขึ้น/ลง
        reorder_frame = tk.Frame(left_panel, bg=BG_CARD)
        reorder_frame.pack(fill="x", pady=(5, 0))
        
        ModernButton(reorder_frame, text="▲ ขึ้น", command=lambda: self.move_step(-1), variant="subtle").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(reorder_frame, text="▼ ลง", command=lambda: self.move_step(1), variant="subtle").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(reorder_frame, text="ลบขั้นตอน", command=self.delete_step, variant="danger").pack(side="right")
        
        # ฝั่งขวา: ฟอร์มป้อน/แก้ไขขั้นตอนคำสั่งการบอท (Right Panel)
        right_panel = tk.Frame(main_pane, bg=BG_CARD, width=340, highlightthickness=1, highlightbackground=LINE_SOFT)
        right_panel.pack_propagate(False)
        main_pane.add(right_panel, weight=1)

        # (ปุ่มรัน + ตัวเลือกการรัน ย้ายไปหน้าแรกแล้ว — build_run_controls)

        # เพิ่ม scrollable canvas ให้กับ right_panel เพื่อให้เลื่อนดูฟอร์มได้
        right_canvas = tk.Canvas(right_panel, bg=BG_CARD, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=right_canvas.yview)
        
        right_scroll_frame = tk.Frame(right_canvas, bg=BG_CARD)
        right_scroll_frame.bind(
            "<Configure>",
            lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        )
        
        right_window_id = right_canvas.create_window((0, 0), window=right_scroll_frame, anchor="nw")
        right_canvas.bind('<Configure>', lambda event: right_canvas.itemconfigure(right_window_id, width=event.width))
        
        right_canvas.configure(yscrollcommand=right_scrollbar.set)
        right_canvas.pack(side="left", fill="both", expand=True)
        right_scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(right_canvas)
        
        form_panel = tk.LabelFrame(right_scroll_frame, text=" ➕ เพิ่ม / แก้ไขขั้นตอนคำสั่ง ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=10)
        form_panel.pack(fill="both", expand=True, pady=(0, 10))
        
        # ตัวเลือกประเภทคำสั่ง
        tk.Label(form_panel, text="ประเภทคำสั่ง:", bg=BG_DARK, fg=FG_WHITE).grid(row=0, column=0, sticky="w", pady=5)
        
        self.form_type = ttk.Combobox(
            form_panel, 
            values=[
                "คลิกหน้าจอ (Tap)", 
                "พิมพ์ข้อความ (Text)", 
                "กดปุ่มระบบ (Keyevent)", 
                "ลาก/เลื่อนหน้าจอ (Swipe)",
                "รอเวลา (Sleep)",
                "เปิดแอป (Start App)",
                "ปิดแอป (Stop App)",
                "ตรวจจับรูปภาพ (Image Match)",
                "รอจนเจอรูป (Wait Image)",
                "กดตามข้อความ (Tap Text)",
                "รอจนเจอข้อความ (Wait Text)",
                "ลูปปิดโฆษณา (Clear Ads Loop)",
                "กรอก OTP อัตโนมัติ (Auto Fill OTP)",
                "ใช้ชุดคำสั่ง (Run Set)",
                "แคปหน้าจอ (Screenshot)",
                "คีย์บอร์ด (Keyboard)",
                "อ่านเพชร (Read Diamond)"
            ],
            state="readonly", 
            width=22
        )
        self.form_type.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        self.form_type.set("คลิกหน้าจอ (Tap)")
        self.form_type.bind("<<ComboboxSelected>>", self.on_step_type_change)
        
        # พิกัดคลิกหน้าจอ หรือ จุดเริ่ม X1 / Y1
        self.form_x_label = tk.Label(form_panel, text="พิกัดคลิก (X Y):", bg=BG_DARK, fg=FG_WHITE)
        self.form_x_label.grid(row=1, column=0, sticky="w", pady=5)
        coords_frame = tk.Frame(form_panel, bg=BG_DARK)
        coords_frame.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        self.form_x = ModernEntry(coords_frame, width=6)
        self.form_x.pack(side="left")
        self.form_x.insert(0, "450")
        tk.Label(coords_frame, text="Y:", bg=BG_DARK, fg=FG_WHITE).pack(side="left", padx=5)
        self.form_y = ModernEntry(coords_frame, width=6)
        self.form_y.pack(side="left")
        self.form_y.insert(0, "320")

        # พิกัดลากหน้าจอจุดปลาย X2 / Y2 (ใช้เฉพาะ Swipe)
        self.form_x2_label = tk.Label(form_panel, text="จุดปลาย (X2 Y2):", bg=BG_DARK, fg=FG_WHITE)
        self.form_x2_label.grid(row=2, column=0, sticky="w", pady=5)
        coords2_frame = tk.Frame(form_panel, bg=BG_DARK)
        coords2_frame.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        self.form_x2 = ModernEntry(coords2_frame, width=6)
        self.form_x2.pack(side="left")
        self.form_x2.insert(0, "450")
        tk.Label(coords2_frame, text="Y2:", bg=BG_DARK, fg=FG_WHITE).pack(side="left", padx=5)
        self.form_y2 = ModernEntry(coords2_frame, width=6)
        self.form_y2.pack(side="left")
        self.form_y2.insert(0, "150")
        
        # พิมพ์ข้อความ / หรือใส่ Package Name สำหรับคำสั่งแอป
        tk.Label(form_panel, text="ข้อความ / แอป:", bg=BG_DARK, fg=FG_WHITE).grid(row=3, column=0, sticky="w", pady=5)
        self.form_text = ModernEntry(form_panel, width=20)
        self.form_text.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        self.form_text.insert(0, "{EMAIL}")
        
        # กดคีย์บอร์ด / ปุ่มกดมือถือระบบ
        tk.Label(form_panel, text="รหัสปุ่มกด (Keycode):", bg=BG_DARK, fg=FG_WHITE).grid(row=4, column=0, sticky="w", pady=5)
        self.form_code = ModernEntry(form_panel, width=10)
        self.form_code.grid(row=4, column=1, sticky="w", padx=10, pady=5)
        self.form_code.insert(0, "4")
        
        # สลีปหน่วงเวลาก่อนทำขั้นต่อไป
        self.form_sleep_label = tk.Label(form_panel, text="หน่วงหลังทำเสร็จ (วินาที):", bg=BG_DARK, fg=FG_WHITE)
        self.form_sleep_label.grid(row=5, column=0, sticky="w", pady=5)
        self.form_sleep = ModernEntry(form_panel, width=10)
        self.form_sleep.grid(row=5, column=1, sticky="w", padx=10, pady=5)
        self.form_sleep.insert(0, "5.0")
        
        # คำอธิบายขั้นตอน
        tk.Label(form_panel, text="คำอธิบายขั้นตอน:", bg=BG_DARK, fg=FG_WHITE).grid(row=6, column=0, sticky="w", pady=5)
        self.form_desc = ModernEntry(form_panel, width=20)
        self.form_desc.grid(row=6, column=1, sticky="w", padx=10, pady=5)
        self.form_desc.insert(0, "คลิกช่อง Email")
        
        # ปุ่มดำเนินการฟอร์ม
        form_btn_frame = tk.Frame(form_panel, bg=BG_DARK)
        form_btn_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=15)
        
        primary_step_row = tk.Frame(form_btn_frame, bg=BG_DARK)
        primary_step_row.pack(fill="x", pady=(0, 5))
        secondary_step_row = tk.Frame(form_btn_frame, bg=BG_DARK)
        secondary_step_row.pack(fill="x")

        ModernButton(primary_step_row, text="เพิ่มขั้นตอน", command=self.add_step, variant="accent").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(primary_step_row, text="อัปเดต", command=self.update_step, variant="warning").pack(side="left", fill="x", expand=True)
        
        ModernButton(secondary_step_row, text="บันทึกพิกัดด้วยภาพ", command=self.open_visual_recorder, variant="primary").pack(fill="x", pady=(6, 4))

        ModernButton(secondary_step_row, text="🧪 ทดสอบสเต็ปนี้ (แตะจริงบนจอ)", command=self.test_selected_step, variant="warning").pack(fill="x", pady=(6, 2))

        anchor_row = tk.Frame(secondary_step_row, bg=BG_DARK)
        anchor_row.pack(fill="x", pady=2)
        ModernButton(anchor_row, text="📷 Anchor รอบจุดกด", command=self.capture_step_anchor, variant="subtle").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(anchor_row, text="🖼️ เลือกพื้นที่เอง", command=self.open_step_anchor_setup, variant="subtle").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ModernButton(anchor_row, text="ลบ", command=self.clear_step_anchor, variant="subtle").pack(side="right")

        ModernButton(secondary_step_row, text="ล้างฟอร์ม", command=self.clear_form, variant="subtle").pack(fill="x", pady=2)
        
        form_panel.columnconfigure(0, weight=1)
        form_panel.columnconfigure(1, weight=2)
        
        # ปรับสถานะฟอร์มตามดร็อปดาวน์เริ่มต้น
        self.on_step_type_change()
        
        # โหลดรายชื่อโปรไฟล์จากโฟลเดอร์เก็บข้อมูลมาโคร
        self.load_script_sets()
        self.load_profiles()

    def build_accounts_tab(self, parent):
        parent.configure(bg=BG_DARK)
        
        main_pane = ttk.PanedWindow(parent, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)

        # ฝั่งซ้าย: รายการบัญชีบอททั้งหมด (Left Panel)
        left_panel = tk.Frame(main_pane, bg=BG_CARD, highlightthickness=1, highlightbackground=LINE_SOFT)
        main_pane.add(left_panel, weight=3)

        left_header = tk.Frame(left_panel, bg=BG_PANEL, height=40)
        left_header.pack(fill="x")
        left_header.pack_propagate(False)
        tk.Label(left_header, text="บัญชีทั้งหมด", bg=BG_PANEL, fg=FG_WHITE, font=("Segoe UI", 10, "bold")).pack(side="left", padx=12)
        
        # แผงจัดการกลุ่มและค้นหา (Search & Batch Action Panel)
        control_panel = tk.Frame(left_panel, bg=BG_CARD, padx=12, pady=12)
        control_panel.pack(fill="x")
        
        # 1. แถบค้นหา
        search_frame = tk.Frame(control_panel, bg=BG_CARD)
        search_frame.pack(fill="x", pady=(0, 8))
        tk.Label(search_frame, text="ค้นหา", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        self.acc_search_entry = ModernEntry(search_frame)
        self.acc_search_entry.pack(side="left", fill="x", expand=True)
        self.acc_search_entry.bind("<KeyRelease>", lambda e: self.refresh_accounts_ui())
        
        # 2. แถบจัดการแบบกลุ่ม (Batch Operations)
        batch_frame = tk.Frame(control_panel, bg=BG_CARD)
        batch_frame.pack(fill="x", pady=2)
        
        ModernButton(batch_frame, text="ลบที่เลือก", command=self.delete_selected_accounts, variant="danger", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        
        tk.Label(batch_frame, text="ย้ายกลุ่มไป:", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9)).pack(side="left", padx=5)
        self.batch_move_group_entry = ModernEntry(batch_frame, width=12)
        self.batch_move_group_entry.pack(side="left", padx=2)
        self.batch_move_group_entry.insert(0, "ทั่วไป")
        
        ModernButton(batch_frame, text="ย้ายกลุ่ม", command=self.move_selected_accounts, variant="accent", font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)

        # แถวเลือกด่วนตามสถานะรอบก่อน — รันซ้ำเฉพาะที่ตกได้ทันที
        filter_frame = tk.Frame(left_panel, bg=BG_CARD)
        filter_frame.pack(fill="x", pady=2)
        tk.Label(filter_frame, text="เลือกด่วน:", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        ModernButton(filter_frame, text="🔴 ที่พลาด", command=lambda: self.select_accounts_by_status("failed"),
                     variant="subtle", font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        ModernButton(filter_frame, text="⚪ ที่ยังไม่เสร็จ", command=lambda: self.select_accounts_by_status("pending"),
                     variant="subtle", font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        tk.Label(filter_frame, text="🟢เสร็จ 🔴พลาด 🔵กำลังทำ ⚪ยังไม่ทำ", bg=BG_CARD, fg=FG_MUTED,
                 font=("Segoe UI", 8)).pack(side="right")

        # กล่องรายการบัญชีพร้อม Scrollbar
        list_container = tk.Frame(left_panel, bg=BG_CARD, bd=0)
        list_container.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        
        self.acc_canvas = tk.Canvas(list_container, bg=BG_CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.acc_canvas.yview)
        
        self.acc_scroll_frame = tk.Frame(self.acc_canvas, bg=BG_CARD)
        self.acc_scroll_frame.bind(
            "<Configure>", 
            lambda e: self.acc_canvas.configure(scrollregion=self.acc_canvas.bbox("all"))
        )
        
        acc_window_id = self.acc_canvas.create_window((0, 0), window=self.acc_scroll_frame, anchor="nw")
        # ปรับความกว้างรายการบัญชีให้เต็ม canvas เสมอ — กันค้างที่ 340px ตอนลากปรับช่องซ้าย/ขวา
        self.acc_canvas.bind("<Configure>", lambda e: self.acc_canvas.itemconfigure(acc_window_id, width=e.width))
        self.acc_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.acc_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(self.acc_canvas)
        
        # ฝั่งขวา: ฟอร์มเพิ่มบัญชีใหม่และคู่มือรันบอทวนลูป (Right Panel)
        right_panel = tk.Frame(main_pane, bg=BG_CARD, width=340, highlightthickness=1, highlightbackground=LINE_SOFT)
        right_panel.pack_propagate(False)
        main_pane.add(right_panel, weight=1)

        # เพิ่ม scrollable canvas ให้กับ right_panel เพื่อให้เลื่อนดูฟอร์มและคู่มือด้านล่างได้หากความสูงหน้าจอต่ำ
        right_canvas = tk.Canvas(right_panel, bg=BG_CARD, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=right_canvas.yview)
        
        right_scroll_frame = tk.Frame(right_canvas, bg=BG_CARD)
        right_scroll_frame.bind(
            "<Configure>",
            lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        )
        
        right_window_id = right_canvas.create_window((0, 0), window=right_scroll_frame, anchor="nw")
        right_canvas.bind('<Configure>', lambda event: right_canvas.itemconfigure(right_window_id, width=event.width))
        
        right_canvas.configure(yscrollcommand=right_scrollbar.set)
        right_canvas.pack(side="left", fill="both", expand=True)
        right_scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(right_canvas)
        
        # ฟอร์มเพิ่มบัญชี
        add_box_outer, add_box = self.make_panel(right_scroll_frame, "เพิ่ม / แก้ไขบัญชี", fill="x", pady=(0, 12))
        
        tk.Label(add_box, text="อีเมล / ไอดีเกม:", bg=BG_CARD, fg=FG_WHITE).grid(row=0, column=0, sticky="w", pady=5)
        self.new_acc_email = ModernEntry(add_box, width=22)
        self.new_acc_email.grid(row=0, column=1, padx=10, pady=5)
        self.new_acc_email.insert(0, "test_user02@gmail.com")

        tk.Label(add_box, text="ชื่อเรียกไอดี (Name):", bg=BG_CARD, fg=FG_WHITE).grid(row=1, column=0, sticky="w", pady=5)
        self.new_acc_name = ModernEntry(add_box, width=22)
        self.new_acc_name.grid(row=1, column=1, padx=10, pady=5)
        
        tk.Label(add_box, text="รหัสผ่าน (Password):", bg=BG_CARD, fg=FG_WHITE).grid(row=2, column=0, sticky="w", pady=5)
        self.new_acc_pass = ModernEntry(add_box, width=22)
        self.new_acc_pass.grid(row=2, column=1, padx=10, pady=5)
        self.new_acc_pass.insert(0, "test_pass02")

        tk.Label(add_box, text="กลุ่มบัญชี (Group):", bg=BG_CARD, fg=FG_WHITE).grid(row=3, column=0, sticky="w", pady=5)
        self.new_acc_group = ModernEntry(add_box, width=22)
        self.new_acc_group.grid(row=3, column=1, padx=10, pady=5)
        self.new_acc_group.insert(0, "ทั่วไป")

        tk.Label(add_box, text="โทเคน (OAuth2 Token):", bg=BG_CARD, fg=FG_WHITE).grid(row=4, column=0, sticky="w", pady=5)
        self.new_acc_token = ModernEntry(add_box, width=22)
        self.new_acc_token.grid(row=4, column=1, padx=10, pady=5)

        tk.Label(add_box, text="ไคลเอนต์ไอดี (Client ID):", bg=BG_CARD, fg=FG_WHITE).grid(row=5, column=0, sticky="w", pady=5)
        self.new_acc_client_id = ModernEntry(add_box, width=22)
        self.new_acc_client_id.grid(row=5, column=1, padx=10, pady=5)
        
        self.save_acc_btn = ModernButton(add_box, text="เพิ่มบัญชีเข้าคิว", command=self.add_account, variant="primary")
        self.save_acc_btn.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(15, 0))
        
        self.batch_import_btn = ModernButton(add_box, text="นำเข้าบัญชีแบบกลุ่ม", command=self.open_batch_import_dialog, variant="accent")
        self.batch_import_btn.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.save_web_game_import_btn = ModernButton(add_box, text="Import Save Web Game JSON", command=self.import_save_web_game_file, variant="subtle")
        self.save_web_game_import_btn.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        
        add_box.columnconfigure(0, weight=1)
        add_box.columnconfigure(1, weight=2)
        
        # คู่มือการรันวนลูปหลายรหัส
        info_box_outer, info_box = self.make_panel(right_scroll_frame, "คู่มือบัญชี", fill="both", expand=True)
        
        info_text = (
            "ใช้ {EMAIL}, {PASSWORD}, {NAME}, {GROUP} ในมาโครเพื่อแทนค่าจากบัญชีที่เลือก "
            "ระบบจะหยิบบัญชีตามคิวและกระจายลง Emulator ที่เลือกไว้"
        )
        info_lbl = tk.Label(info_box, text=info_text, bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9), justify="left", wraplength=300)
        info_lbl.pack(anchor="w")
        self._bind_responsive_wraplength(info_lbl, info_box, padding=20)
        
        # วาดรายการบัญชีที่มีอยู่
        self.refresh_accounts_ui()

    def _scroll_subtab(self, notebook, title):
        """สร้างแท็บย่อยที่เลื่อนขึ้น-ลงได้ คืน 'เฟรมเนื้อหา' ข้างใน (ใช้แยกหมวดในแท็บอื่นๆ)"""
        outer = tk.Frame(notebook, bg=BG_DARK)
        notebook.add(outer, text=title)
        canvas = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_DARK, padx=20, pady=20)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        wid = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(wid, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(canvas)
        return inner

    def build_sync_tab(self, parent):
        # จัดเป็นแท็บย่อย 3 หมวด ลดความรกจากสกรอลยาว: แมนนวล / เครื่องมือ / Story Auto
        sub = ttk.Notebook(parent)
        sub.pack(fill="both", expand=True)
        sync_frame = self._scroll_subtab(sub, " 🖱️ แมนนวล + ถ่ายจอ ")
        tools_frame = self._scroll_subtab(sub, " 🛠️ เครื่องมือ ")
        story_frame = self._scroll_subtab(sub, " 📖 Story Auto ")

        tk.Label(sync_frame, text="ส่งคำสั่งเดียวกันไปทุกจอที่เลือกทางซ้าย (คลิก/พิมพ์/ปุ่ม/ถ่ายจอ)",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 14))

        # ส่วนของแผงดำเนินการ Grid
        control_grid = tk.Frame(sync_frame, bg=BG_DARK)
        control_grid.pack(fill="x", pady=10)

        # 1. กล่องจำลองคลิกพิกัด
        tap_outer, tap_box = self.make_panel(control_grid, "คลิกพิกัด", manager=None)
        tap_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        
        tk.Label(tap_box, text="พิกัด X:", bg=BG_CARD, fg=FG_WHITE).grid(row=0, column=0, sticky="w", pady=5)
        self.manual_x = ModernEntry(tap_box, width=10)
        self.manual_x.grid(row=0, column=1, padx=5, pady=5)
        self.manual_x.insert(0, "450")

        tk.Label(tap_box, text="พิกัด Y:", bg=BG_CARD, fg=FG_WHITE).grid(row=1, column=0, sticky="w", pady=5)
        self.manual_y = ModernEntry(tap_box, width=10)
        self.manual_y.grid(row=1, column=1, padx=5, pady=5)
        self.manual_y.insert(0, "320")

        ModernButton(tap_box, text="ส่งคลิก", command=self.send_manual_click, variant="primary").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        # 2. กล่องจำลองการพิมพ์ข้อความ
        txt_outer, txt_box = self.make_panel(control_grid, "พิมพ์ข้อความ", manager=None)
        txt_outer.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        tk.Label(txt_box, text="ข้อความ:", bg=BG_CARD, fg=FG_WHITE).pack(anchor="w", pady=5)
        self.manual_txt_entry = ModernEntry(txt_box, width=30)
        self.manual_txt_entry.pack(fill="x", pady=5)
        self.manual_txt_entry.insert(0, "Hello World")
        
        ModernButton(txt_box, text="ส่งข้อความ", command=self.send_manual_text, variant="primary").pack(fill="x", pady=(18, 0))

        # 3. จำลองกดปุ่มระบบมือถือ
        key_outer, key_box = self.make_panel(control_grid, "ปุ่มระบบ", manager=None)
        key_outer.grid(row=0, column=2, sticky="nsew", padx=(10, 0), pady=10)

        ModernButton(key_box, text="BACK", command=lambda: self.send_manual_key(4), variant="subtle").pack(fill="x", pady=3)
        ModernButton(key_box, text="HOME", command=lambda: self.send_manual_key(3), variant="subtle").pack(fill="x", pady=3)
        ModernButton(key_box, text="MENU", command=lambda: self.send_manual_key(82), variant="subtle").pack(fill="x", pady=3)

        control_grid.columnconfigure(0, weight=1)
        control_grid.columnconfigure(1, weight=1)
        control_grid.columnconfigure(2, weight=1)

        # 4. ถ่ายภาพหน้าจอพร้อมกัน
        screenshot_outer, screenshot_box = self.make_panel(control_grid, "ถ่ายภาพหน้าจอ", manager=None)
        screenshot_outer.grid(row=1, column=0, columnspan=3, sticky="ew", pady=10)
        
        tk.Label(screenshot_box, text="ชื่อไฟล์ (รองรับ {NAME}, {GROUP}, {EMAIL}, {DEVICE}, {DATE}, {TIME}):", bg=BG_CARD, fg=FG_WHITE).pack(anchor="w", pady=2)
        
        screenshot_input_frame = tk.Frame(screenshot_box, bg=BG_CARD)
        screenshot_input_frame.pack(fill="x", pady=5)
        
        self.manual_screenshot_entry = ModernEntry(screenshot_input_frame)
        self.manual_screenshot_entry.pack(fill="x", side="left", expand=True, padx=(0, 10))
        self.manual_screenshot_entry.insert(0, "screenshots/{DATE}/screenshot_{NAME}_{TIME}.png")
        
        ModernButton(screenshot_input_frame, text="ถ่ายทุกเครื่อง", command=self.send_manual_screenshot, variant="accent").pack(side="right")

        # 4.1 ระบบอ่านจำนวนเพชร (Diamond OCR) — แคปจอ อ่านเลขเพชร แล้ว Export เป็น JSON
        tk.Label(
            screenshot_box,
            text="💎 อ่านจำนวนเพชร: แคปจอทุกเครื่องที่เลือก ตั้งชื่อตามรหัสที่ล็อกอินล่าสุด อ่านเลขเพชรบนหัวจอ แล้ว Export เป็น JSON",
            bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="left", wraplength=700,
        ).pack(anchor="w", pady=(12, 2))
        diamond_btn_frame = tk.Frame(screenshot_box, bg=BG_CARD)
        diamond_btn_frame.pack(fill="x", pady=2)
        ModernButton(diamond_btn_frame, text="💎 แคปจอ + อ่านเพชร (Export JSON)", command=self.capture_and_read_diamonds, variant="accent").pack(side="left")
        ModernButton(diamond_btn_frame, text="⚙️ ตั้งค่าพื้นที่เพชร", command=self.open_diamond_setup, variant="subtle").pack(side="left", padx=8)
        ModernButton(diamond_btn_frame, text="🔗 เติม id เว็บ (จับคู่ชื่อ)", command=self.backfill_web_ids, variant="subtle").pack(side="left", padx=8)

        # 5. กล่องรันคำสั่ง ADB แบบแมนนวลเอง (หมวดเครื่องมือ)
        raw_outer, raw_box = self.make_panel(tools_frame, "ADB Shell", fill="x", pady=10)

        tk.Label(raw_box, text="ใส่เฉพาะคำสั่งหลัง shell เช่น wm size", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic")).pack(anchor="w")
        
        cmd_input_frame = tk.Frame(raw_box, bg=BG_CARD)
        cmd_input_frame.pack(fill="x", pady=5)

        self.custom_cmd_entry = ModernEntry(cmd_input_frame)
        self.custom_cmd_entry.pack(fill="x", side="left", expand=True, padx=(0, 10))
        self.custom_cmd_entry.insert(0, "wm size")

        ModernButton(cmd_input_frame, text="รัน", command=self.send_custom_cmd, variant="warning").pack(side="right")

        # 6. ดู element บนจอ (UI Inspector) — เช็คว่าหน้าจอนี้ใช้ tap_text ได้ไหม
        ui_outer, ui_box = self.make_panel(tools_frame, "ดู Element บนจอ (UI Inspector)", fill="x", pady=10)
        tk.Label(
            ui_box,
            text="อ่าน element บนหน้าจอของเครื่องที่เลือก (เครื่องแรก) — ถ้าเห็นข้อความ/ปุ่ม = ใช้ step 'กดตามข้อความ' ได้, ถ้าว่าง = เป็นหน้าจอเกมต้องใช้รูป",
            bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="left", wraplength=700,
        ).pack(anchor="w")
        ModernButton(ui_box, text="ดู Element บนจอ", command=self.inspect_ui, variant="accent").pack(anchor="w", pady=(8, 0))

        # 7. ดึงรายชื่อสมาชิกชมรม (Guild Member Grabber) — เลื่อน+แคปจนสุด รวมเป็นรูปเดียวให้เว็บ
        guild_outer, guild_box = self.make_panel(tools_frame, "ดึงรายชื่อสมาชิกชมรม (ส่งเข้าเว็บ guild-check)", fill="x", pady=10)
        tk.Label(
            guild_box,
            text=("เปิดหน้า 'สมาชิกชมรม' ในเกม เลื่อนขึ้นบนสุด แล้วกดปุ่ม — ระบบจะเลื่อนลง+แคปทีละหน้าจนสุดล่าง "
                  "OCR เป็นรายชื่อ ตัดชื่อซ้ำให้ แล้วแสดงเป็นตัวอักษร (ก๊อปไปวางในเว็บ guild-check ช่อง 'วางรายชื่อเอง' ได้เลย)\n"
                  "แนะนำกด '⚙️ ตั้งพื้นที่ชื่อ' ลากครอบเฉพาะคอลัมน์ชื่อก่อนสักครั้ง จะอ่านแม่นและไม่ปนเลขอันดับ/เลเวล\n"
                  "หรือถ้าเลื่อน auto แล้วไม่ตรง ให้แคปเอง แล้วกด '🖼️ วางรูป → อ่านชื่อ' วางรูปด้วย Ctrl+V ได้เลย"),
            bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="left", wraplength=700,
        ).pack(anchor="w")
        guild_btn_row = tk.Frame(guild_box, bg=BG_CARD)
        guild_btn_row.pack(anchor="w", pady=(8, 0))
        ModernButton(guild_btn_row, text="⚙️ ตั้งพื้นที่ชื่อ", command=self.open_guild_region_setup, variant="accent").pack(side="left", padx=(0, 10))
        ModernButton(guild_btn_row, text="📋 ดึงรายชื่อ (เป็นตัวอักษร)", command=self.grab_guild_members, variant="primary").pack(side="left", padx=(0, 10))
        ModernButton(guild_btn_row, text="🖼️ วางรูป → อ่านชื่อ", command=self.open_guild_image_ocr, variant="subtle").pack(side="left")

        # 8. Story Auto — เล่นเนื้อเรื่องอัตโนมัติ (หาด่านเหลือง -> ลุยจนจบ -> วนซ้ำ)
        story_outer, story_box = self.make_panel(story_frame, "เล่นเนื้อเรื่องอัตโนมัติ (Story Auto)", fill="x", pady=10)
        tk.Label(
            story_box,
            text=("เปิดเกมค้างไว้ที่ 'หน้าเลือกด่าน' (ให้เห็นกรอบเหลืองของด่านถัดไป) แล้วกดเริ่ม — ระบบจะแตะด่านเหลือง "
                  "→ กวาดกดปุ่ม ข้าม/ไปต่อ/รับ → รอแมตช์เล่นเอง → กลับมาเลือกด่านถัดไป วนจนไม่มีด่านเหลือง (สุด story)\n"
                  "ปุ่มที่กวาด = ไฟล์ templates/story_*.png (แถมมาให้ story_skip.png แล้ว — เพิ่ม story_next/story_claim/story_close ได้)\n"
                  "แนะนำใส่ story_map.png (ครอปหัวข้อ 'บทที่..' หรือมุมจอหน้าเลือกด่าน) เพื่อยืนยัน 'กลับถึง map' ให้แม่นกว่ากรอบเหลือง · หยุดด้วยปุ่ม 'หยุดทันที'"),
            bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="left", wraplength=700,
        ).pack(anchor="w")

        interval_row = tk.Frame(story_box, bg=BG_CARD)
        interval_row.pack(anchor="w", fill="x", pady=(8, 0))
        tk.Label(interval_row, text="ความถี่เช็คจอ (วิ):", bg=BG_CARD, fg=FG_WHITE, font=("Segoe UI", 9)).pack(side="left")
        self._story_scan_interval_var = tk.StringVar(value="2.5")
        ModernEntry(interval_row, textvariable=self._story_scan_interval_var, width=6).pack(side="left", padx=(6, 0))
        tk.Label(interval_row, text="ยิ่งน้อย = ตอบสนองไวขึ้นแต่กิน CPU มากขึ้น (แนะนำ 2-3 วิ ถ้ารันหลายเครื่องพร้อมกัน)",
                 bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic")).pack(side="left", padx=(8, 0))

        ModernButton(story_box, text="🎮 เริ่ม Story Auto", command=self.start_story_auto, variant="primary").pack(anchor="w", pady=(8, 0))

    def start_story_auto(self):
        """เริ่มเล่นเนื้อเรื่องอัตโนมัติบนทุกเครื่องที่เลือก พร้อมกัน (คนละ thread ต่อเครื่อง)
        เหมือน pattern มาโครทั่วไป (ThreadPoolExecutor) — ก่อนหน้านี้ใช้แค่เครื่องแรกเสมอ"""
        from concurrent.futures import ThreadPoolExecutor
        if self.macro_running:
            messagebox.showwarning("กำลังทำงานอยู่", "มีงานกำลังรันอยู่ กรุณาหยุดก่อน")
            return
        devices = self.get_selected_devices()
        if not devices:
            messagebox.showwarning("ยังไม่ได้เลือกเครื่อง", "กรุณาติ๊กเลือก Emulator อย่างน้อย 1 เครื่องก่อน")
            return

        btns = self._story_button_templates("")
        if not btns:
            if not messagebox.askyesno(
                "ยังไม่มี template ปุ่ม",
                "ยังไม่พบไฟล์ปุ่ม story_*.png ในโฟลเดอร์ templates/\n"
                "ถ้าไม่มีปุ่มให้กวาด ระบบจะแตะด่านเหลืองแล้วได้แค่ 'รอ' (ข้ามคัตซีน/กดไปต่อไม่ได้)\n\n"
                "ต้องการเริ่มเลยไหม?"):
                return

        max_stages = simpledialog.askinteger(
            "Story Auto",
            "จะเล่นต่อเนื่องสูงสุดกี่ด่าน?\n(ใส่ 0 = ไม่จำกัด รันจนกว่าจะกดหยุด)",
            parent=self, initialvalue=0, minvalue=0, maxvalue=9999)
        if max_stages is None:  # กด Cancel
            return

        try:
            scan_interval = float(self._story_scan_interval_var.get())
            if scan_interval <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            scan_interval = 2.5
            self.write_log("⚠️ ค่าความถี่เช็คจอไม่ถูกต้อง -> ใช้ค่าเริ่มต้น 2.5 วิ", "warning")

        if not messagebox.askyesno(
            "เริ่ม Story Auto",
            f"จะเริ่มเล่นเนื้อเรื่องอัตโนมัติพร้อมกัน {len(devices)} เครื่อง สูงสุด {max_stages} ด่าน/เครื่อง "
            f"(เช็คจอทุก {scan_interval:g} วิ)\n\n"
            "ตรวจว่าทุกเครื่องอยู่ที่ 'หน้าเลือกด่าน' เห็นกรอบเหลืองของด่านถัดไปแล้ว\n"
            "หยุดได้ตลอดด้วยปุ่ม 'หยุดทันที' ที่แท็บมาโคร (หยุดทุกเครื่องพร้อมกัน)"):
            return

        self.macro_running = True
        self.run_macro_btn.configure(state="disabled", bg=BG_INPUT)
        self.stop_macro_btn.configure(state="normal")
        self.update_status_summary()

        def per_device(dev):
            try:
                self.run_story_auto(dev, max_stages=max_stages, scan_interval=scan_interval)
            except Exception as e:
                self.write_log(f"❌ [{dev}] Story Auto ผิดพลาด: {e}", "error")

        def worker():
            try:
                self.write_log(f"🎮 เริ่ม Story Auto พร้อมกัน {len(devices)} เครื่อง...", "warning")
                with ThreadPoolExecutor(max_workers=len(devices)) as executor:
                    executor.map(per_device, devices)
            finally:
                self.macro_running = False
                self.after(0, lambda: self.run_macro_btn.configure(state="normal", bg=ACCENT_GREEN, text="รันมาโคร"))
                self.after(0, lambda: self.stop_macro_btn.configure(state="disabled"))
                self.after(0, self.update_status_summary)

        self.macro_thread = threading.Thread(target=worker, daemon=True)
        self.macro_thread.start()

    def grab_guild_members(self):
        """เลื่อนหน้า 'สมาชิกชมรม' แล้วแคปทีละหน้าจนสุด -> OCR เป็นรายชื่อ -> ตัดซ้ำ -> โชว์เป็นตัวอักษร
        (ก๊อปไปวางในช่อง 'วางรายชื่อเอง' ของเว็บ guild-check ได้เลย)"""
        devices = self.get_selected_devices()
        if not devices:
            messagebox.showwarning("ยังไม่ได้เลือกเครื่อง", "กรุณาติ๊กเลือก Emulator อย่างน้อย 1 เครื่องก่อน")
            return
        device = devices[0]
        if not find_tesseract():
            messagebox.showwarning(
                "ไม่พบ Tesseract OCR",
                "ระบบดึงรายชื่อต้องใช้ Tesseract OCR ซึ่งยังไม่ได้ติดตั้ง\n\n"
                "ติดตั้งโดยเปิด PowerShell แล้วรัน:\n    winget install UB-Mannheim.TesseractOCR\n\n"
                "ติดตั้งเสร็จแล้วเปิดโปรแกรมนี้ใหม่")
            return

        region = (self.guild_config or {}).get("region") or {}
        has_region = int(region.get("w", 0)) > 0 and int(region.get("h", 0)) > 0
        region_note = ("✅ ตั้งพื้นที่คอลัมน์ชื่อไว้แล้ว (จะอ่านเฉพาะชื่อ)\n" if has_region
                       else "⚠️ ยังไม่ได้ตั้งพื้นที่ชื่อ จะ OCR ทั้งจอ (ชื่ออาจปนเลขอันดับ/เลเวล)\n"
                            "   แนะนำกด '⚙️ ตั้งพื้นที่ชื่อ' ก่อน จะแม่นกว่ามาก\n")
        if not messagebox.askyesno(
            "ดึงรายชื่อสมาชิกชมรม",
            f"จะดึงจากเครื่อง [{device}]\n\n{region_note}\n"
            "เตรียม: เปิดหน้า 'สมาชิกชมรม' ในเกม เลื่อนขึ้นบนสุด แล้วกดตกลง\n"
            "ระบบจะเลื่อนลง+แคป+OCR จนสุดล่าง แล้วโชว์รายชื่อเป็นตัวอักษรให้แก้ไข/คัดลอก",
        ):
            return

        def worker():
            from datetime import datetime
            base_dir = os.path.dirname(self.accounts_file)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join(base_dir, "guild_members", stamp)
            os.makedirs(out_dir, exist_ok=True)

            res = self.controller.get_resolution(device)
            m = re.match(r"(\d+)x(\d+)", res or "")
            w, h = (int(m.group(1)), int(m.group(2))) if m else (960, 540)
            sx = int(w * 0.6)
            y1, y2 = int(h * 0.82), int(h * 0.30)

            self.write_log(f"📋 [{device}] เริ่มดึงรายชื่อสมาชิกชมรม (จอ {w}x{h})...", "warning")

            max_pages = 40
            shots, prev = [], None
            for i in range(max_pages):
                ok, data = self.controller.capture_screenshot_bytes(device)
                if not ok:
                    self.write_log(f"   ⏭️ [{device}] แคปจอหน้า {i+1} ไม่สำเร็จ -> ข้าม", "warning")
                else:
                    if prev is not None and png_similarity(prev, data) >= 0.992:
                        self.write_log(f"   ✅ [{device}] ภาพไม่เลื่อนแล้ว (ถึงล่างสุด) หยุดที่ {len(shots)} หน้า", "success")
                        break
                    idx = len(shots) + 1
                    try:
                        with open(os.path.join(out_dir, f"page_{idx:02d}.png"), "wb") as f:
                            f.write(data)
                    except Exception:
                        pass
                    shots.append(data)
                    prev = data
                    self.write_log(f"   📸 [{device}] แคปหน้า {idx}", "info")
                self.controller.swipe(device, sx, y1, sx, y2, duration=700)
                time.sleep(0.9)

            if not shots:
                self.write_log(f"❌ [{device}] ไม่ได้รูปเลย", "error")
                self.after(0, lambda: messagebox.showerror("ไม่สำเร็จ", "แคปรายชื่อไม่ได้ ลองเปิดหน้าสมาชิกชมรมแล้วลองใหม่"))
                return

            # OCR ทุกหน้า -> รวมข้อความ -> แยกชื่อ + ตัดซ้ำ
            lang = guild_ocr_langs()
            crop = region if has_region else None
            scale = 3 if has_region else 2
            texts = []
            for i, data in enumerate(shots):
                ok, txt, _ = ocr_text_tesseract(data, region=crop, lang=lang, psm=6, scale=scale)
                if ok and txt:
                    texts.append(txt)
                self.write_log(f"   🔤 [{device}] OCR หน้า {i+1}/{len(shots)}", "info")

            names = extract_guild_member_names("\n".join(texts))
            members_path = os.path.join(out_dir, "members.txt")
            try:
                with open(members_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(names))
            except Exception:
                pass

            self.write_log(f"✅ [{device}] OCR ได้ {len(names)} ชื่อ (ตัดซ้ำแล้ว) จาก {len(shots)} หน้า", "success")
            self.after(0, lambda: self._show_guild_names_window(names, out_dir, device, has_region))

        threading.Thread(target=worker, daemon=True).start()

    def _show_guild_names_window(self, names, out_dir, device, has_region):
        """หน้าต่างแสดงรายชื่อสมาชิกที่ OCR ได้ (แก้ไขได้) + ปุ่มคัดลอกทั้งหมด/บันทึก"""
        win = tk.Toplevel(self)
        win.title(f"รายชื่อสมาชิกชมรม — {device}")
        win.configure(bg=BG_DARK)
        win.geometry("460x600")
        win.transient(self)

        tk.Label(win, text=f"ได้ {len(names)} ชื่อ (ตัดซ้ำแล้ว)", bg=BG_DARK, fg=FG_WHITE,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=18, pady=(16, 2))
        tip = ("แก้ไขชื่อที่ OCR อ่านเพี้ยนได้ในช่องนี้ แล้วกด 'คัดลอกทั้งหมด' ไปวางในเว็บ guild-check "
               "ช่อง 'วางรายชื่อเอง' (1 ชื่อ/บรรทัด)")
        if not has_region:
            tip += "\n💡 ถ้าชื่อปนเลขเยอะ ลองกด '⚙️ ตั้งพื้นที่ชื่อ' แล้วดึงใหม่จะแม่นขึ้น"
        tk.Label(win, text=tip, bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"),
                 justify="left", wraplength=420).pack(anchor="w", padx=18)

        text_frame = tk.Frame(win, bg=BG_DARK)
        text_frame.pack(fill="both", expand=True, padx=18, pady=10)
        txt = tk.Text(text_frame, bg=BG_INPUT, fg=FG_WHITE, relief="flat", bd=0, wrap="none",
                      font=("Consolas", 11), insertbackground=FG_WHITE)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        txt.insert("1.0", "\n".join(names))

        def copy_all():
            data = txt.get("1.0", "end-1c")
            try:
                self.clipboard_clear()
                self.clipboard_append(data)
                self.update()
                self.write_log("📋 คัดลอกรายชื่อสมาชิกชมรมลง Clipboard แล้ว", "success")
                messagebox.showinfo("คัดลอกแล้ว", "คัดลอกรายชื่อทั้งหมดแล้ว เอาไปวางในเว็บ guild-check ได้เลย", parent=win)
            except Exception as e:
                messagebox.showerror("ผิดพลาด", f"คัดลอกไม่สำเร็จ: {e}", parent=win)

        def save_txt():
            data = txt.get("1.0", "end-1c")
            try:
                with open(os.path.join(out_dir, "members.txt"), "w", encoding="utf-8") as f:
                    f.write(data)
                messagebox.showinfo("บันทึกแล้ว", f"บันทึก members.txt ใน:\n{out_dir}", parent=win)
            except Exception as e:
                messagebox.showerror("ผิดพลาด", f"บันทึกไม่สำเร็จ: {e}", parent=win)

        btns = tk.Frame(win, bg=BG_DARK)
        btns.pack(fill="x", padx=18, pady=(0, 16))
        ModernButton(btns, text="📋 คัดลอกทั้งหมด", command=copy_all, variant="primary").pack(side="left", padx=(0, 8))
        ModernButton(btns, text="💾 บันทึก .txt", command=save_txt, variant="accent").pack(side="left", padx=(0, 8))
        ModernButton(btns, text="📂 เปิดโฟลเดอร์", command=lambda: os.startfile(out_dir), variant="subtle").pack(side="left")

        # คัดลอกให้อัตโนมัติเลยตั้งแต่เปิด
        copy_all()

    def open_guild_image_ocr(self):
        """วางรูป (Ctrl+V) หรือเปิดไฟล์รูปหน้าสมาชิกชมรม -> ลากครอบเฉพาะคอลัมน์ชื่อ (ถ้าต้องการ)
        -> OCR เป็นรายชื่อ -> ตัดซ้ำ -> โชว์เป็นตัวอักษร (ก๊อปไปวางในเว็บ guild-check ได้เลย)

        ทางเลือกแทนการเลื่อน+แคป auto สำหรับกรณีที่แคปเองแล้วแม่นกว่า"""
        if not find_tesseract():
            messagebox.showwarning(
                "ไม่พบ Tesseract OCR",
                "ระบบอ่านรายชื่อต้องใช้ Tesseract OCR ซึ่งยังไม่ได้ติดตั้ง\n\n"
                "ติดตั้งโดยเปิด PowerShell แล้วรัน:\n    winget install UB-Mannheim.TesseractOCR\n\n"
                "ติดตั้งเสร็จแล้วเปิดโปรแกรมนี้ใหม่")
            return

        import io
        import cv2
        import numpy as np
        from PIL import ImageGrab

        dialog = tk.Toplevel(self)
        dialog.title("🖼️ วางรูปหน้าสมาชิกชมรม → อ่านชื่อ")
        dialog.configure(bg=BG_DARK)
        dialog.transient(self)
        dialog.grab_set()

        state = {"orig": None, "bytes": None, "sx": 1.0, "rect_id": None, "region": None}
        temp_disp = os.path.join(self.templates_dir, "guild_paste_disp.png")

        def on_close():
            try:
                if os.path.exists(temp_disp):
                    os.remove(temp_disp)
            except Exception:
                pass
            dialog.grab_release()
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW", on_close)

        left = tk.Frame(dialog, bg=BG_DARK)
        left.pack(side="left", padx=15, pady=15)
        canvas = tk.Canvas(left, width=860, height=560, bg="#000000", highlightthickness=1, highlightbackground=BG_PANEL)
        canvas.pack()
        tk.Label(left, text="วางรูปด้วย Ctrl+V หรือเปิดไฟล์ — 💡 แม่นสุดถ้าครอบ 'เฉพาะคอลัมน์ชื่อ ไม่เอา avatar' (ลากเมาส์คลุมสูงหลายแถว ชิดขวาพ้นไอคอน) ก่อนกดอ่าน",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), wraplength=840, justify="left").pack(anchor="w", pady=(6, 0))

        right = tk.Frame(dialog, bg=BG_DARK, padx=15, pady=15)
        right.pack(side="right", fill="both", expand=True)

        tk.Label(right, text="วิธีใช้:\n1) แคปหน้าสมาชิกชมรม (แคปเองให้ชัด/ตรง)\n2) กด Ctrl+V วางรูป หรือ 'เปิดไฟล์รูป'\n3) (ถ้าต้องการ) ลากครอบเฉพาะคอลัมน์ชื่อ\n4) กด 'ดึงรายชื่อ'",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 8))

        status = tk.Label(right, text="กด Ctrl+V เพื่อวางรูป หรือกด 'เปิดไฟล์รูป'", bg=BG_DARK, fg=ACCENT_ORANGE,
                          font=("Segoe UI", 9), wraplength=250, justify="left")
        status.pack(fill="x", pady=10)

        def render():
            img = state["orig"]
            if img is None:
                return
            oh, ow = img.shape[:2]
            sc = min(860.0 / ow, 560.0 / oh)
            state["sx"] = sc
            disp = cv2.resize(img, (max(1, int(ow * sc)), max(1, int(oh * sc))))
            dh, dw = disp.shape[:2]
            cv2.imwrite(temp_disp, disp)
            canvas.configure(width=dw, height=dh)
            photo = tk.PhotoImage(file=temp_disp)
            canvas.delete("all")
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.image = photo
            state["rect_id"] = None
            reg = state["region"]
            if reg and reg.get("w") and reg.get("h"):
                canvas.create_rectangle(reg["x"] * sc, reg["y"] * sc,
                                        (reg["x"] + reg["w"]) * sc, (reg["y"] + reg["h"]) * sc,
                                        outline=ACCENT_GREEN, width=2)

        def set_image(data):
            arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if arr is None:
                status.configure(text="❌ ถอดรหัสรูปไม่สำเร็จ ลองรูปอื่น", fg=ACCENT_RED)
                return
            state["bytes"] = data
            state["orig"] = arr
            state["region"] = None
            render()
            status.configure(text=f"🖼️ โหลดรูปแล้ว ({arr.shape[1]}x{arr.shape[0]}) — ลากครอบคอลัมน์ชื่อ (ถ้าต้องการ) แล้วกด 'ดึงรายชื่อ'", fg=ACCENT_GREEN)

        def load_from_clipboard(*_, auto=False):
            try:
                obj = ImageGrab.grabclipboard()
            except Exception as e:
                if not auto:
                    status.configure(text=f"❌ อ่าน Clipboard ไม่ได้: {e}", fg=ACCENT_RED)
                return
            if isinstance(obj, list):
                paths = [p for p in obj if isinstance(p, str) and os.path.isfile(p)]
                if not paths:
                    if not auto:
                        status.configure(text="❌ Clipboard เป็นไฟล์แต่ไม่พบไฟล์รูป", fg=ACCENT_RED)
                    return
                try:
                    with open(paths[0], "rb") as f:
                        set_image(f.read())
                except Exception as e:
                    status.configure(text=f"❌ เปิดไฟล์จาก Clipboard ไม่ได้: {e}", fg=ACCENT_RED)
                return
            if obj is None:
                if not auto:
                    status.configure(text="❌ ไม่มีรูปใน Clipboard — แคป/ก๊อปรูปก่อนแล้วกด Ctrl+V", fg=ACCENT_RED)
                return
            try:
                if obj.mode not in ("RGB", "RGBA"):
                    obj = obj.convert("RGB")
                buf = io.BytesIO()
                obj.save(buf, format="PNG")
                set_image(buf.getvalue())
            except Exception as e:
                status.configure(text=f"❌ แปลงรูปจาก Clipboard ไม่ได้: {e}", fg=ACCENT_RED)

        def load_from_file():
            path = filedialog.askopenfilename(
                parent=dialog, title="เลือกไฟล์รูปหน้าสมาชิกชมรม",
                filetypes=[("รูปภาพ", "*.png *.jpg *.jpeg *.bmp *.webp"), ("ทั้งหมด", "*.*")])
            if not path:
                return
            try:
                with open(path, "rb") as f:
                    set_image(f.read())
            except Exception as e:
                status.configure(text=f"❌ เปิดไฟล์ไม่ได้: {e}", fg=ACCENT_RED)

        press = {"x": 0, "y": 0}

        def on_press(e):
            press["x"], press["y"] = e.x, e.y
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
                state["rect_id"] = None

        def on_motion(e):
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
            state["rect_id"] = canvas.create_rectangle(press["x"], press["y"], e.x, e.y, outline=ACCENT_ORANGE, width=2)

        def on_release(e):
            if state["orig"] is None:
                status.configure(text="วางรูปก่อน", fg=ACCENT_RED)
                return
            sx = state["sx"] or 1.0
            x1, y1 = min(press["x"], e.x), min(press["y"], e.y)
            x2, y2 = max(press["x"], e.x), max(press["y"], e.y)
            rx, ry = int(x1 / sx), int(y1 / sx)
            rw, rh = int((x2 - x1) / sx), int((y2 - y1) / sx)
            if rw < 3 or rh < 3:
                state["region"] = None
                status.configure(text="ล้างกรอบแล้ว (จะอ่านทั้งรูป) — หรือลากครอบคอลัมน์ชื่อใหม่", fg=ACCENT_ORANGE)
                render()
                return
            state["region"] = {"x": rx, "y": ry, "w": rw, "h": rh}
            status.configure(text=f"✅ ครอบคอลัมน์ชื่อ: x={rx} y={ry} w={rw} h={rh}\nกด 'ดึงรายชื่อ'", fg=ACCENT_GREEN)
            render()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_motion)
        canvas.bind("<ButtonRelease-1>", on_release)
        dialog.bind("<Control-v>", load_from_clipboard)
        dialog.bind("<Control-V>", load_from_clipboard)

        def run_ocr():
            reg = state["region"]
            lang = guild_ocr_langs()
            # ปรับ scale ตามความกว้างของส่วนที่จะอ่าน — รูปคอลัมน์ชื่อมักแคบ (100-200px)
            # ต้องขยายเยอะให้ตัวหนังสือใหญ่พอ Tesseract ถึงจะอ่านแม่น
            src = state["orig"]
            w = reg["w"] if reg else (src.shape[1] if src is not None else 0)
            scale = max(2, min(6, round(480 / w))) if w else 4
            ok, txt, _ = ocr_text_tesseract(state["bytes"], region=reg, lang=lang, psm=6, scale=scale)
            names = extract_guild_member_names(txt) if ok else []
            return names

        def test_read():
            if state["bytes"] is None:
                status.configure(text="วางรูปก่อน (Ctrl+V) หรือเปิดไฟล์", fg=ACCENT_RED)
                return
            names = run_ocr()
            if names:
                preview = ", ".join(names[:6])
                status.configure(text=f"🔍 อ่านได้ {len(names)} ชื่อ:\n{preview}{' ...' if len(names) > 6 else ''}", fg=ACCENT_GREEN)
            else:
                status.configure(text="🔍 อ่านชื่อไม่ได้ — ลองครอบเฉพาะคอลัมน์ชื่อ (ไม่เอาไอคอน/เลเวล)", fg=ACCENT_RED)

        def do_grab():
            if state["bytes"] is None:
                status.configure(text="วางรูปก่อน (Ctrl+V) หรือเปิดไฟล์", fg=ACCENT_RED)
                return
            status.configure(text="⏳ กำลังอ่านชื่อ...", fg=ACCENT_ORANGE)
            dialog.update()

            def worker():
                from datetime import datetime
                names = run_ocr()
                base_dir = os.path.dirname(self.accounts_file)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_dir = os.path.join(base_dir, "guild_members", stamp)
                try:
                    os.makedirs(out_dir, exist_ok=True)
                    with open(os.path.join(out_dir, "page_01.png"), "wb") as f:
                        f.write(state["bytes"])
                    with open(os.path.join(out_dir, "members.txt"), "w", encoding="utf-8") as f:
                        f.write("\n".join(names))
                except Exception:
                    pass
                self.write_log(f"🖼️ อ่านรายชื่อจากรูปได้ {len(names)} ชื่อ (ตัดซ้ำแล้ว)", "success")

                def show():
                    if not names:
                        status.configure(text="🔍 อ่านชื่อไม่ได้ — ลองครอบเฉพาะคอลัมน์ชื่อ (ไม่เอาไอคอน/เลเวล)", fg=ACCENT_RED)
                        return
                    on_close()
                    self._show_guild_names_window(names, out_dir, "รูปที่วาง", bool(state["region"]))
                self.after(0, show)

            threading.Thread(target=worker, daemon=True).start()

        btns = tk.Frame(right, bg=BG_DARK)
        btns.pack(fill="x", pady=(14, 0))
        ModernButton(btns, text="📋 วางรูป (Ctrl+V)", command=load_from_clipboard, variant="accent").pack(fill="x", pady=3)
        ModernButton(btns, text="📂 เปิดไฟล์รูป", command=load_from_file, variant="subtle").pack(fill="x", pady=3)
        ModernButton(btns, text="🔍 ทดสอบอ่าน", command=test_read, variant="subtle").pack(fill="x", pady=3)
        ModernButton(btns, text="📋 ดึงรายชื่อ", command=do_grab, variant="primary").pack(fill="x", pady=3)

        # ลองวางจาก clipboard อัตโนมัติตอนเปิด (ถ้ามีรูปอยู่แล้ว — เงียบถ้าไม่มี)
        dialog.after(200, lambda: load_from_clipboard(auto=True))

    def open_guild_region_setup(self):
        """ตั้งพื้นที่คอลัมน์ชื่อสมาชิกชมรม: จับภาพหน้าสมาชิก -> ลากครอบเฉพาะคอลัมน์ชื่อ -> ทดสอบอ่าน -> บันทึก"""
        if self.macro_running:
            messagebox.showwarning("คำเตือน", "กรุณาปิดบอทมาโครก่อนตั้งค่า", parent=self)
            return
        if not find_tesseract():
            messagebox.showwarning(
                "ไม่พบ Tesseract OCR",
                "ต้องติดตั้ง Tesseract OCR ก่อน:\n    winget install UB-Mannheim.TesseractOCR")
            return
        selected_devices = self.get_selected_devices() or self.controller.get_connected_devices()
        if not selected_devices:
            messagebox.showerror("ไม่พบอุปกรณ์", "ไม่พบ Emulator ที่เชื่อมต่ออยู่! กรุณาเปิดและเชื่อมต่อก่อน", parent=self)
            return

        import cv2
        import numpy as np

        dialog = tk.Toplevel(self)
        dialog.title("⚙️ ตั้งพื้นที่คอลัมน์ชื่อสมาชิกชมรม")
        dialog.configure(bg=BG_DARK)
        dialog.transient(self)
        dialog.grab_set()

        state = {"orig": None, "bytes": None, "sx": 1.0, "rect_id": None}
        temp_disp = os.path.join(self.templates_dir, "guild_setup_disp.png")

        def on_close():
            try:
                if os.path.exists(temp_disp):
                    os.remove(temp_disp)
            except Exception:
                pass
            dialog.grab_release()
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW", on_close)

        left = tk.Frame(dialog, bg=BG_DARK)
        left.pack(side="left", padx=15, pady=15)
        canvas = tk.Canvas(left, width=800, height=450, bg="#000000", highlightthickness=1, highlightbackground=BG_PANEL)
        canvas.pack()
        tk.Label(left, text="ลากเมาส์ครอบ 'เฉพาะคอลัมน์ชื่อ' (ครอบสูงคลุมหลายแถว เอาเฉพาะชื่อ ไม่เอาเลเวล/เซิร์ฟ/อันดับ) แล้วกดทดสอบอ่าน",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), wraplength=780, justify="left").pack(anchor="w", pady=(6, 0))

        right = tk.Frame(dialog, bg=BG_DARK, padx=15, pady=15)
        right.pack(side="right", fill="both", expand=True)

        tk.Label(right, text="📱 เลือก Emulator:", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        dev_var = tk.StringVar(value=selected_devices[0])
        ttk.Combobox(right, textvariable=dev_var, values=selected_devices, state="readonly").pack(fill="x", pady=(2, 12))

        tk.Label(right, text="วิธีใช้:\n1) เปิดหน้าสมาชิกชมรมในเกม\n2) กดจับภาพ\n3) ลากครอบเฉพาะคอลัมน์ชื่อ\n4) กดทดสอบอ่าน\n5) กดบันทึก",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 8))

        status = tk.Label(right, text="กด '📸 จับภาพหน้าจอ' เพื่อเริ่ม", bg=BG_DARK, fg=ACCENT_ORANGE,
                          font=("Segoe UI", 9), wraplength=240, justify="left")
        status.pack(fill="x", pady=10)

        def render():
            img = state["orig"]
            if img is None:
                return
            oh, ow = img.shape[:2]
            sc = min(800.0 / ow, 450.0 / oh)
            state["sx"] = sc
            disp = cv2.resize(img, (int(ow * sc), int(oh * sc)))
            dh, dw = disp.shape[:2]
            cv2.imwrite(temp_disp, disp)
            canvas.configure(width=dw, height=dh)
            photo = tk.PhotoImage(file=temp_disp)
            canvas.delete("all")
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.image = photo
            state["rect_id"] = None
            reg = (self.guild_config or {}).get("region") or {}
            if reg.get("w") and reg.get("h"):
                canvas.create_rectangle(reg["x"] * sc, reg["y"] * sc,
                                        (reg["x"] + reg["w"]) * sc, (reg["y"] + reg["h"]) * sc,
                                        outline=ACCENT_GREEN, width=2)

        def capture():
            dev = dev_var.get()
            status.configure(text="⏳ กำลังจับภาพ...", fg=ACCENT_ORANGE)
            dialog.update()
            ok, data = self.controller.capture_screenshot_bytes(dev)
            if not ok:
                status.configure(text=f"❌ จับภาพล้มเหลว: {data}", fg=ACCENT_RED)
                return
            state["bytes"] = data
            state["orig"] = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if state["orig"] is None:
                status.configure(text="❌ ถอดรหัสภาพไม่สำเร็จ", fg=ACCENT_RED)
                return
            render()
            status.configure(text=f"📸 จับภาพสำเร็จ ({state['orig'].shape[1]}x{state['orig'].shape[0]}) — ลากครอบคอลัมน์ชื่อ", fg=ACCENT_GREEN)

        press = {"x": 0, "y": 0}

        def on_press(e):
            press["x"], press["y"] = e.x, e.y
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
                state["rect_id"] = None

        def on_motion(e):
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
            state["rect_id"] = canvas.create_rectangle(press["x"], press["y"], e.x, e.y, outline=ACCENT_ORANGE, width=2)

        def on_release(e):
            if state["orig"] is None:
                status.configure(text="กรุณาจับภาพก่อน", fg=ACCENT_RED)
                return
            sx = state["sx"] or 1.0
            x1, y1 = min(press["x"], e.x), min(press["y"], e.y)
            x2, y2 = max(press["x"], e.x), max(press["y"], e.y)
            rx, ry = int(x1 / sx), int(y1 / sx)
            rw, rh = int((x2 - x1) / sx), int((y2 - y1) / sx)
            if rw < 3 or rh < 3:
                status.configure(text="กรอบเล็กเกินไป ลองลากใหม่", fg=ACCENT_RED)
                return
            self.guild_config["region"] = {"x": rx, "y": ry, "w": rw, "h": rh}
            status.configure(text=f"✅ ตั้งพื้นที่: x={rx} y={ry} w={rw} h={rh}\nกด 'ทดสอบอ่านชื่อ'", fg=ACCENT_GREEN)
            render()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_motion)
        canvas.bind("<ButtonRelease-1>", on_release)

        def test_read():
            if state["bytes"] is None:
                status.configure(text="กรุณาจับภาพก่อน", fg=ACCENT_RED)
                return
            reg = (self.guild_config or {}).get("region") or {}
            if int(reg.get("w", 0)) <= 0 or int(reg.get("h", 0)) <= 0:
                status.configure(text="ยังไม่ได้ลากกรอบคอลัมน์ชื่อ", fg=ACCENT_RED)
                return
            lang = guild_ocr_langs()
            ok, txt, _ = ocr_text_tesseract(state["bytes"], region=reg, lang=lang, psm=6, scale=3)
            names = extract_guild_member_names(txt) if ok else []
            if names:
                preview = ", ".join(names[:6])
                status.configure(text=f"🔍 อ่านได้ {len(names)} ชื่อ:\n{preview}{' ...' if len(names) > 6 else ''}", fg=ACCENT_GREEN)
            else:
                status.configure(text="🔍 อ่านชื่อไม่ได้ — ลองครอบให้คลุมเฉพาะคอลัมน์ชื่อ ไม่เอาไอคอน/เลเวล", fg=ACCENT_RED)

        def save_and_close():
            self.save_guild_config()
            self.write_log("💾 บันทึกพื้นที่คอลัมน์ชื่อสมาชิกชมรมแล้ว", "success")
            on_close()

        btns = tk.Frame(right, bg=BG_DARK)
        btns.pack(fill="x", pady=(14, 0))
        ModernButton(btns, text="📸 จับภาพหน้าจอ", command=capture, variant="primary").pack(fill="x", pady=3)
        ModernButton(btns, text="🔍 ทดสอบอ่านชื่อ", command=test_read, variant="accent").pack(fill="x", pady=3)
        ModernButton(btns, text="💾 บันทึกการตั้งค่า", command=save_and_close, variant="primary").pack(fill="x", pady=3)

        dialog.after(200, capture)

    def inspect_ui(self):
        """อ่าน element บนหน้าจอของเครื่องที่เลือกตัวแรก แล้วแสดงรายการ (ช่วยเตรียม tap_text)"""
        devices = self.get_selected_devices()
        if not devices:
            messagebox.showwarning("ยังไม่ได้เลือกเครื่อง", "กรุณาติ๊กเลือก Emulator อย่างน้อย 1 เครื่องก่อน")
            return
        device = devices[0]
        self.write_log(f"🔎 [{device}] กำลังอ่าน element บนหน้าจอ...", "info")
        ok, xml = self.controller.dump_ui(device)
        if not ok:
            messagebox.showinfo("อ่าน UI ไม่ได้", f"[{device}] {xml}")
            return

        elements = list_ui_elements(xml)
        lines = []
        for el in elements:
            parts = []
            if el["text"]:
                parts.append(f"text='{el['text']}'")
            if el["resource_id"]:
                parts.append(f"id:{el['resource_id']}")
            if el["content_desc"]:
                parts.append(f"desc='{el['content_desc']}'")
            if el["clickable"]:
                parts.append("[คลิกได้]")
            if el["center"]:
                parts.append(f"@({el['center'][0]},{el['center'][1]})")
            lines.append("  •  ".join(parts))

        win = tk.Toplevel(self)
        win.title(f"UI Elements — {device}")
        win.configure(bg=BG_DARK)
        win.geometry("760x520")
        win.transient(self)

        tk.Label(
            win, text=f"พบ {len(elements)} element บนจอ [{device}]",
            bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(
            win, text="คัดลอกข้อความหรือ id (ขึ้นต้น id:) ไปใส่ใน step 'กดตามข้อความ' / 'รอจนเจอข้อความ'",
            bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"),
        ).pack(anchor="w", padx=20)

        text_frame = tk.Frame(win, bg=BG_DARK)
        text_frame.pack(fill="both", expand=True, padx=20, pady=10)
        txt = tk.Text(text_frame, bg=BG_INPUT, fg=FG_WHITE, relief="flat", bd=0, wrap="none", font=("Consolas", 9))
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        txt.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        txt.insert("1.0", "\n".join(lines) if lines else "(ไม่พบ element ที่มีข้อความ/id — น่าจะเป็นหน้าจอเกม ใช้การจับภาพแทน)")
        txt.configure(state="disabled")

        ModernButton(win, text="ปิด", command=win.destroy, variant="subtle").pack(anchor="e", padx=20, pady=(0, 16))
        self.write_log(f"✅ [{device}] อ่าน element ได้ {len(elements)} รายการ", "success")

    def build_settings_tab(self, parent):
        # สร้าง Canvas และ Scrollbar เพื่อให้หน้าต่างตั้งค่าเลื่อนขึ้น-ลงได้
        canvas = tk.Canvas(parent, bg=BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        
        # กล่องสำหรับใส่เนื้อหาทั้งหมด
        settings_frame = tk.Frame(canvas, bg=BG_DARK, padx=20, pady=20)
        settings_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        # วาดหน้าต่างเฟรมหลักภายใน Canvas
        window_id = canvas.create_window((0, 0), window=settings_frame, anchor="nw")
        
        # ปรับความกว้างของ settings_frame ให้เต็มขนาดของ canvas เสมอเมื่อมีขนาดเปลี่ยนไป
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window_id, width=event.width))
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(canvas)

        tk.Label(settings_frame, text="ตั้งค่า", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(settings_frame, text="ค่าระบบและการเชื่อมต่อ · ถูกจำถาวรลงไฟล์ config", bg=BG_DARK, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 12))

        # การ์ดตั้งค่าหลักจัดเป็นตาราง 2 คอลัมน์ (กระชับกว่าเรียงเต็มความกว้างทีละอัน)
        grid_frame = tk.Frame(settings_frame, bg=BG_DARK)
        grid_frame.pack(fill="x")
        grid_frame.columnconfigure(0, weight=1, uniform="settings_col")
        grid_frame.columnconfigure(1, weight=1, uniform="settings_col")
        WRAP = 320

        # ที่อยู่ ADB.exe
        path_outer, path_box = self.make_panel(grid_frame, "ไฟล์ระบบ", manager=None)
        path_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=6)

        tk.Label(path_box, text="ที่อยู่ไฟล์ ADB.exe (Path):", bg=BG_CARD, fg=FG_WHITE).pack(anchor="w")
        
        adb_path_frame = tk.Frame(path_box, bg=BG_CARD)
        adb_path_frame.pack(fill="x", pady=5)
        
        self.adb_path_entry = ModernEntry(adb_path_frame)
        self.adb_path_entry.pack(fill="x", side="left", expand=True, padx=(0, 10))
        self.adb_path_entry.insert(0, self.controller.adb_path)

        ModernButton(adb_path_frame, text="บันทึกและโหลดใหม่", command=self.save_adb_path, variant="primary").pack(side="right")

        # ตั้งค่าพอร์ต ADB (ADB Port Settings)
        port_outer, port_box = self.make_panel(grid_frame, "พอร์ต ADB", manager=None)
        port_outer.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=6)

        tk.Label(port_box, text="นำเข้าหรือดูพอร์ต Emulator สำหรับสแกนและควบคุม", bg=BG_CARD, fg=FG_WHITE).pack(anchor="w")

        port_btn_frame = tk.Frame(port_box, bg=BG_CARD)
        port_btn_frame.pack(fill="x", pady=5)

        ModernButton(port_btn_frame, text="นำเข้าพอร์ต JSON", command=self.open_port_config_dialog, variant="accent").pack(side="left", padx=(0, 10))
        
        def copy_ai_prompt():
            prompt_text = (
                "ช่วยอ่านค่าพอร์ต ADB ของ Android Device จากในรูปภาพที่แนบมานี้\n"
                "ให้ดึงเฉพาะตัวเลขพอร์ตทั้งหมด (ทั้งพอร์ต 5 หลัก และพอร์ต 4/5 หลักอื่นๆ เช่น 5555, 16384)\n"
                "แล้วแปลงผลลัพธ์ออกมาเป็น JSON Array ของตัวเลขเท่านั้น ห้ามมีคำอธิบายอื่นเพิ่มเติม ตัวอย่างเช่น:\n"
                "[\n"
                "  5555,\n"
                "  16384,\n"
                "  5557,\n"
                "  16416\n"
                "]"
            )
            self.clipboard_clear()
            self.clipboard_append(prompt_text)
            self.update()
            messagebox.showinfo("สำเร็จ", "คัดลอกพร้อมต์สำหรับส่งให้ AI ลง Clipboard เรียบร้อยแล้ว!\nสามารถนำไปวาง (Ctrl+V) ควบคู่กับรูปภาพในแชทบอท AI ได้ทันที")

        ModernButton(port_btn_frame, text="คัดลอกพร้อมต์ AI", command=copy_ai_prompt, variant="warning").pack(side="left", padx=(0, 10))

        def show_current_ports():
            ports = self.controller.load_ports()
            msg = f"พอร์ตที่โปรแกรมกำลังสแกนอยู่ในปัจจุบัน:\n\n{ports}\n\nจำนวนทั้งหมด: {len(ports)} พอร์ต"
            messagebox.showinfo("พอร์ตที่ใช้สแกน", msg)

        ModernButton(port_btn_frame, text="ดูพอร์ตปัจจุบัน", command=show_current_ports, variant="subtle").pack(side="left")

        # Gemini API Key สำหรับ Story Auto fallback
        gem_outer, gem_box = self.make_panel(grid_frame, "Gemini API Key (Story Auto)", manager=None)
        gem_outer.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=6)
        tk.Label(gem_box, text="ใส่ key เพื่อให้ AI ช่วย 'เฉพาะตอนระบบติดค้าง' (จอนิ่งเกิน 12 วิ) เท่านั้น\nเรียกไม่เกิน 1 ครั้ง/25 วิ จึงแทบไม่กิน quota — เว้นว่างเพื่อปิด (ใช้ CV+OCR ล้วน)",
                 bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="left", wraplength=WRAP).pack(anchor="w", pady=(0, 4))
        gem_row = tk.Frame(gem_box, bg=BG_CARD)
        gem_row.pack(fill="x")
        self._gemini_key_var = tk.StringVar(value=self.gemini_api_key)
        gem_entry = ModernEntry(gem_row, textvariable=self._gemini_key_var, show="*", width=50)
        gem_entry.pack(side="left", padx=(0, 8))

        def _save_gemini_key():
            self.gemini_api_key = self._gemini_key_var.get().strip()
            self._save_gemini_api_key_to_file()
            messagebox.showinfo("บันทึก", "บันทึก Gemini API Key แล้ว (อยู่ถาวร ไม่หายแม้ปิดแอป/build ใหม่)")
        ModernButton(gem_row, text="บันทึก", command=_save_gemini_key, variant="subtle").pack(side="left")

        def _toggle_gem_show():
            gem_entry.config(show="" if gem_entry.cget("show") else "*")
        ModernButton(gem_row, text="แสดง/ซ่อน", command=_toggle_gem_show, variant="subtle").pack(side="left", padx=(4, 0))

        # ขีดจำกัดเครื่อง — ตรวจว่ารัน MuMu ได้สูงสุดกี่จอ
        cap_outer, cap_box = self.make_panel(grid_frame, "ขีดจำกัดเครื่อง — รันได้กี่จอ", manager=None)
        cap_outer.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=6)

        p = DEFAULT_MUMU_PROFILE
        tk.Label(
            cap_box,
            text=(
                f"คำนวณจากสเปกต่อจอ: CPU {p['cores_per_instance']} คอร์ · RAM {p['ram_per_instance_gb']:g}GB · "
                f"540×960 · DPI 160 · FPS 15\n"
                f"กันทรัพยากรให้ระบบ: RAM {p['host_reserve_ram_gb']:g}GB + {p['host_reserve_cores']} คอร์ "
                f"(จอ FPS-cap เบา จึงเผื่อแชร์คอร์ได้ {p['cpu_oversubscribe']:g} เท่า)"
            ),
            bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic"),
            justify="left", wraplength=WRAP,
        ).pack(anchor="w", pady=(0, 8))

        ModernButton(cap_box, text="🖥️ ตรวจขีดจำกัดเครื่องนี้", command=self.check_machine_capacity, variant="primary").pack(anchor="w")

        self.capacity_result_lbl = tk.Label(
            cap_box, text="กดปุ่มด้านบนเพื่อตรวจสเปกเครื่องและจำนวนจอที่แนะนำ",
            bg=BG_CARD, fg=FG_WHITE, font=("Consolas", 10),
            justify="left", anchor="w", wraplength=WRAP,
        )
        self.capacity_result_lbl.pack(anchor="w", fill="x", pady=(10, 0))

        # ระบบตรวจสอบความเหมาะสมของขนาดจอและ DPI
        diag_outer, diag_box = self.make_panel(grid_frame, "ตรวจสอบ Emulator", manager=None)
        diag_outer.grid(row=2, column=0, sticky="nsew", padx=(0, 6), pady=6)

        ModernButton(diag_box, text="ตรวจสอบความละเอียดและ DPI", command=self.validate_resolutions, variant="primary").pack(anchor="w")

        diag_lbl = tk.Label(
            diag_box,
            text="หมายเหตุ: พิกัดมาโครทั้งหมดถูกคำนวณบนขนาดหน้าจอเป้าหมาย กว้าง 960 / สูง 540 และค่า DPI 160 หากตั้งค่า Emulator ไม่ตรง คำสั่งคลิกอาจคลาดเคลื่อนไม่ตรงปุ่มจริง ปุ่มนี้จะช่วยสแกนขนาดหน้าจอปัจจุบันและรายงานให้ทราบความเข้ากันได้",
            bg=BG_CARD,
            fg=FG_MUTED,
            font=("Segoe UI", 9, "italic"),
            justify="left",
            wraplength=WRAP
        )
        diag_lbl.pack(anchor="w", pady=(10, 0))

        # คีย์บอร์ดภาษาไทย/Unicode (ADBKeyboard) — ย้ายมาอยู่ในตาราง 2 คอลัมน์ (แถวเดียวกับตรวจสอบ Emulator)
        kb_outer, kb_box = self.make_panel(grid_frame, "พิมพ์ภาษาไทย/Unicode (ADBKeyboard)", manager=None)
        kb_outer.grid(row=2, column=1, sticky="nsew", padx=(6, 0), pady=6)

        kb_btn_row = tk.Frame(kb_box, bg=BG_CARD)
        kb_btn_row.pack(anchor="w", pady=5)
        ModernButton(kb_btn_row, text="เปิดใช้คีย์บอร์ดไทย", command=self.setup_adb_keyboard, variant="primary").pack(side="left", padx=(0, 10))
        ModernButton(kb_btn_row, text="คืนคีย์บอร์ดเดิม", command=self.restore_keyboard, variant="subtle").pack(side="left")

        tk.Label(
            kb_box,
            text=(
                "step 'พิมพ์ข้อความ' รองรับ ASCII ได้เลย แต่ภาษาไทย/Unicode ต้องเปิดใช้ ADBKeyboard ก่อน\n"
                "วิธี: วางไฟล์ ADBKeyboard.apk ไว้ในโฟลเดอร์เดียวกับโปรแกรม แล้วเลือกเครื่อง → กด 'เปิดใช้คีย์บอร์ดไทย'\n"
                "เล่นเองด้วยมือเมื่อไรให้กด 'คืนคีย์บอร์ดเดิม'"
            ),
            bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="left", wraplength=WRAP,
        ).pack(anchor="w", pady=(8, 0))

        # ตัวช่วยวิเคราะห์พิกัดมาโคร (Pointer Location Helper) — เต็มความกว้าง ใต้ตาราง 2 คอลัมน์
        helper_outer, helper_box = self.make_panel(settings_frame, "ตัวช่วยหาพิกัด", fill="x", pady=(6, 10))

        btn_row = tk.Frame(helper_box, bg=BG_CARD)
        btn_row.pack(anchor="w", pady=5)

        ModernButton(btn_row, text="เปิด Pointer", command=lambda: self.toggle_pointer_location(True), variant="accent").pack(side="left", padx=(0, 10))
        ModernButton(btn_row, text="ปิด Pointer", command=lambda: self.toggle_pointer_location(False), variant="subtle").pack(side="left")

        helper_lbl = tk.Label(
            helper_box, 
            text="คำแนะนำ: เมื่อเปิดใช้งานแล้ว ให้ลองใช้เมาส์คลิกบนหน้าจอ Emulator จะมีแถบข้อความแสดงพิกัด X/Y จริงที่ด้านบนสุดของจอ Emulator ทันที! ช่วยให้หาพิกัดกรอกรหัสและปุ่มกดเกมได้แม่นยำ 100%", 
            bg=BG_CARD, 
            fg=FG_MUTED, 
            font=("Segoe UI", 9, "italic"),
            justify="left",
            wraplength=700
        )
        helper_lbl.pack(anchor="w", pady=(5, 0))

    def _app_base_dir(self):
        """โฟลเดอร์ของโปรแกรม (รองรับทั้งรันสคริปต์และไฟล์ .exe ที่ build แล้ว)"""
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def setup_adb_keyboard(self):
        """ติดตั้ง (ถ้ายังไม่มี) + ตั้ง ADBKeyboard เป็นคีย์บอร์ดปัจจุบันบนเครื่องที่เลือก"""
        devices = self.get_selected_devices()
        if not devices:
            messagebox.showwarning("ยังไม่ได้เลือกเครื่อง", "กรุณาติ๊กเลือก Emulator อย่างน้อย 1 เครื่องก่อน")
            return

        apk_path = os.path.join(self._app_base_dir(), "ADBKeyboard.apk")

        def worker():
            for device in devices:
                if not self.controller.is_adb_keyboard_installed(device):
                    if not os.path.exists(apk_path):
                        self.write_log(f"❌ [{device}] ไม่พบไฟล์ ADBKeyboard.apk ในโฟลเดอร์โปรแกรม — ข้าม", "error")
                        continue
                    self.write_log(f"📦 [{device}] กำลังติดตั้ง ADBKeyboard...", "info")
                    ok, out = self.controller.install_adb_keyboard(device, apk_path)
                    if not ok:
                        self.write_log(f"❌ [{device}] ติดตั้ง ADBKeyboard ไม่สำเร็จ: {out}", "error")
                        continue
                ok, out = self.controller.enable_adb_keyboard(device)
                if ok:
                    self.write_log(f"✅ [{device}] เปิดใช้คีย์บอร์ดไทย (ADBKeyboard) แล้ว", "success")
                else:
                    self.write_log(f"❌ [{device}] ตั้งคีย์บอร์ดไม่สำเร็จ: {out}", "error")

        threading.Thread(target=worker, daemon=True).start()

    def restore_keyboard(self):
        """คืนคีย์บอร์ดเริ่มต้นของเครื่องที่เลือก (ime reset)"""
        devices = self.get_selected_devices()
        if not devices:
            messagebox.showwarning("ยังไม่ได้เลือกเครื่อง", "กรุณาติ๊กเลือก Emulator อย่างน้อย 1 เครื่องก่อน")
            return

        def worker():
            for device in devices:
                ok, out = self.controller.reset_ime(device)
                if ok:
                    self.write_log(f"↩️ [{device}] คืนคีย์บอร์ดเดิมแล้ว", "success")
                else:
                    self.write_log(f"❌ [{device}] คืนคีย์บอร์ดไม่สำเร็จ: {out}", "error")

        threading.Thread(target=worker, daemon=True).start()

    def build_log_panel(self, parent):
        self.log_frame = tk.Frame(parent, bg=BG_PANEL, height=130)
        self.log_frame.pack_propagate(False)

        # แถบหัวข้อคอนโซล Log
        log_header = tk.Frame(self.log_frame, bg=BG_PANEL)
        log_header.pack(fill="x", side="top", padx=10, pady=2)
        
        tk.Label(log_header, text="คอนโซลบันทึกการทำงานของระบบ (Log Console)", bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.log_toggle_btn = ModernButton(log_header, text="ย่อ", command=self.toggle_log_panel, bg=BG_INPUT, activebg="#444444", font=("Segoe UI", 8))
        self.log_toggle_btn.pack(side="right", padx=(5, 0))
        ModernButton(log_header, text="ล้างบันทึก", command=self.clear_logs, bg=BG_INPUT, activebg="#444444", font=("Segoe UI", 8)).pack(side="right")

        # ตัวแสดงผลข้อความล็อก
        self.log_txt = tk.Text(
            self.log_frame, 
            bg=BG_DARK, 
            fg=FG_WHITE, 
            font=("Consolas", 9), 
            relief="flat", 
            bd=0, 
            state="disabled",
            wrap="word"
        )
        self.log_scrollbar = ttk.Scrollbar(self.log_frame, orient="vertical", command=self.log_txt.yview)
        
        self.log_txt.configure(yscrollcommand=self.log_scrollbar.set)
        self.log_txt.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))
        self.log_scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=(0, 10))

        # กำหนดแท็กเพื่อแสดงสีของตัวอักษร
        self.log_txt.tag_configure("info", foreground=FG_WHITE)
        self.log_txt.tag_configure("success", foreground=ACCENT_GREEN)
        self.log_txt.tag_configure("error", foreground=ACCENT_RED)
        self.log_txt.tag_configure("warning", foreground=ACCENT_ORANGE)

    def toggle_log_panel(self):
        """ย่อ/ขยายแผง Log — ตอนนี้แผงถูกจัดการโดย PanedWindow (ลากปรับเองได้) จึงต้องสั่งย้าย
        ตำแหน่งเส้นแบ่ง (sashpos) แทนการสั่ง configure(height=) ตรงๆ แบบเดิม"""
        expanded = not self.log_expanded.get()
        self.log_expanded.set(expanded)

        if expanded:
            self.log_txt.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))
            self.log_scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=(0, 10))
            self.log_toggle_btn.configure(text="ย่อ")
            target_h = getattr(self, "_log_panel_expanded_height", 130) or 130
        else:
            self._log_panel_expanded_height = self._current_log_panel_height()
            self.log_txt.pack_forget()
            self.log_scrollbar.pack_forget()
            self.log_toggle_btn.configure(text="ขยาย")
            target_h = 42
        self._set_log_panel_height(target_h)

    def _current_log_panel_height(self):
        try:
            total_h = self._root_paned.winfo_height()
            pos = self._root_paned.sashpos(0)
            return max(42, total_h - pos)
        except Exception:
            return 130

    def _set_log_panel_height(self, height):
        def _apply():
            try:
                total_h = self._root_paned.winfo_height()
                if total_h > 10:
                    self._root_paned.sashpos(0, max(80, total_h - height))
            except Exception:
                pass
        self.after(10, _apply)

    # --- ฟังก์ชันช่วยเหลือเกี่ยวกับระบบ Log ---
    def write_log(self, message, log_type="info"):
        """บันทึกข้อความลงในคอนโซลแบบ Thread-Safe"""
        timestamp = time.strftime("[%H:%M:%S] ")
        full_msg = f"{timestamp}{message}\n"
        
        def run_gui_update():
            self.log_txt.configure(state="normal")
            self.log_txt.insert("end", full_msg, log_type)
            self.log_txt.see("end")
            self.log_txt.configure(state="disabled")
            
        self.after(0, run_gui_update)

    def clear_logs(self):
        self.log_txt.configure(state="normal")
        self.log_txt.delete("1.0", "end")
        self.log_txt.configure(state="disabled")

    def load_coordinate_presets(self):
        if not os.path.exists(self.presets_file):
            presets = normalize_coordinate_presets(DEFAULT_COORDINATE_PRESETS)
            self.save_coordinate_presets(presets)
            return presets

        try:
            with open(self.presets_file, "r", encoding="utf-8") as file:
                data = json.load(file)
            presets = data.get("presets", data if isinstance(data, list) else [])
            return normalize_coordinate_presets(presets)
        except Exception as e:
            if hasattr(self, "log_txt"):
                self.write_log(f"โหลด preset พิกัดล้มเหลว ใช้ค่าเริ่มต้นแทน: {e}", "warning")
            return normalize_coordinate_presets(DEFAULT_COORDINATE_PRESETS)

    def save_coordinate_presets(self, presets=None):
        presets_to_save = presets if presets is not None else self.coordinate_presets
        with open(self.presets_file, "w", encoding="utf-8") as file:
            json.dump({"presets": presets_to_save}, file, ensure_ascii=False, indent=2)

    def save_adb_path(self):
        new_path = self.adb_path_entry.get().strip()
        if not new_path:
            messagebox.showerror("ข้อผิดพลาด", "พาร์ท ADB ว่างเปล่าไม่ได้")
            return
        self.controller.adb_path = new_path
        ok, info = self.controller.persist_adb_path(new_path)
        if ok:
            self.write_log(f"บันทึกเส้นทาง ADB แล้ว (จำไว้ถาวร ไม่ต้องกรอกใหม่ทุกครั้ง): {new_path}", "success")
        else:
            self.write_log(f"ตั้งค่า ADB แล้ว แต่บันทึกไฟล์ไม่สำเร็จ (รอบหน้าอาจต้องกรอกใหม่): {info}", "warning")
        if not os.path.exists(new_path):
            messagebox.showwarning("เตือน", f"บันทึกแล้ว แต่ไม่พบไฟล์ตามพาธนี้จริง:\n{new_path}\nตรวจสอบว่าพิมพ์ถูกต้อง")
        self.scan_devices()

    def open_port_config_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("ตั้งค่าพอร์ต ADB (ADB Port Settings)")
        dialog.geometry("500x420")
        dialog.configure(bg=BG_DARK)
        dialog.resizable(True, True) # อนุญาตให้ผู้ใช้ยืดขยายหน้าต่างได้ตามต้องการ
        dialog.transient(self)
        dialog.grab_set()
        
        # Center the window
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")

        # สร้าง Canvas และ Scrollbar เพื่อให้หน้าต่างนี้เลื่อนขึ้น-ลงได้หากความละเอียดของจอผู้ใช้งานต่ำ
        canvas = tk.Canvas(dialog, bg=BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        
        scroll_frame = tk.Frame(canvas, bg=BG_DARK)
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window_id, width=event.width))
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(canvas)

        title_lbl = tk.Label(
            scroll_frame, 
            text="🔌 นำเข้าพอร์ต ADB จาก AI", 
            bg=BG_DARK, 
            fg=FG_WHITE, 
            font=("Segoe UI", 12, "bold")
        )
        title_lbl.pack(pady=(15, 5))

        desc_lbl = tk.Label(
            scroll_frame,
            text="กรุณาวางโค้ด JSON ที่ได้จาก AI (เช่น [5555, 16384, ...]) ในช่องด้านล่างนี้:",
            bg=BG_DARK,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
            justify="center",
            wraplength=450
        )
        desc_lbl.pack(pady=5)

        # เพิ่มปุ่มคัดลอกพร้อมต์ถาม AI ในป๊อปอัปด้วย
        def copy_ai_prompt_dialog():
            prompt_text = (
                "ช่วยอ่านค่าพอร์ต ADB ของ Android Device จากในรูปภาพที่แนบมานี้\n"
                "ให้ดึงเฉพาะตัวเลขพอร์ตทั้งหมด (ทั้งพอร์ต 5 หลัก และพอร์ต 4/5 หลักอื่นๆ เช่น 5555, 16384)\n"
                "แล้วแปลงผลลัพธ์ออกมาเป็น JSON Array ของตัวเลขเท่านั้น ห้ามมีคำอธิบายอื่นเพิ่มเติม ตัวอย่างเช่น:\n"
                "[\n"
                "  5555,\n"
                "  16384,\n"
                "  5557,\n"
                "  16416\n"
                "]"
            )
            dialog.clipboard_clear()
            dialog.clipboard_append(prompt_text)
            dialog.update()
            messagebox.showinfo("สำเร็จ", "คัดลอกพร้อมต์สำหรับส่งให้ AI ลง Clipboard เรียบร้อยแล้ว!", parent=dialog)

        ModernButton(scroll_frame, text="📋 คัดลอกพร้อมต์ส่งให้ AI", command=copy_ai_prompt_dialog, bg=ACCENT_ORANGE, activebg="#d35400", font=("Segoe UI", 9, "bold")).pack(pady=2)

        # Text Area for pasting JSON
        text_frame = tk.Frame(scroll_frame, bg=BG_DARK)
        text_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Standard Scrollbar + Text widget
        text_scrollbar = ttk.Scrollbar(text_frame)
        text_scrollbar.pack(side="right", fill="y")

        json_text = tk.Text(
            text_frame, 
            bg=BG_INPUT, 
            fg=FG_WHITE, 
            insertbackground=FG_WHITE,
            relief="flat", 
            bd=0, 
            font=("Consolas", 10),
            height=10, # ปรับความสูงกล่องป้อนข้อมูลลงเหลือ 10 บรรทัด เพื่อไม่ให้บีบขนาดกล่องจนล้นปุ่มกดออกนอกจอ
            yscrollcommand=text_scrollbar.set
        )
        json_text.pack(side="left", fill="both", expand=True)
        text_scrollbar.config(command=json_text.yview)

        # Load current ports JSON if file exists to pre-populate
        ports_file = self.ports_file
        if os.path.exists(ports_file):
            try:
                with open(ports_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    json_text.insert("1.0", content)
            except Exception:
                pass
        else:
            json_text.insert("1.0", "[\n  5555,\n  16384\n]")

        # Buttons frame
        btn_frame = tk.Frame(scroll_frame, bg=BG_DARK)
        btn_frame.pack(fill="x", side="bottom", padx=20, pady=20)

        def save_ports():
            raw_data = json_text.get("1.0", "end").strip()
            if not raw_data:
                messagebox.showerror("ข้อผิดพลาด", "กรุณากรอกข้อมูล JSON ก่อนบันทึก")
                return
            try:
                data = json.loads(raw_data)
                if not isinstance(data, list):
                    raise ValueError("JSON ต้องเป็นรายการ Array เช่น [5555, 16384]")
                
                # Filter valid port numbers
                ports = []
                for x in data:
                    try:
                        p = int(x)
                        if 1 <= p <= 65535:
                            ports.append(p)
                    except (ValueError, TypeError):
                        continue
                
                if not ports:
                    raise ValueError("ไม่พบพอร์ตที่ถูกต้องในช่วง 1-65535")
                
                # Keep unique and sorted
                ports = sorted(list(set(ports)))
                
                with open(ports_file, "w", encoding="utf-8") as f:
                    json.dump(ports, f, indent=2)
                
                self.write_log(f"นำเข้าและบันทึกพอร์ต ADB จำนวน {len(ports)} พอร์ตเรียบร้อยแล้ว: {ports}", "success")
                self.scan_devices()
                dialog.destroy()
                messagebox.showinfo("สำเร็จ", f"บันทึกพอร์ตเรียบร้อยแล้ว {len(ports)} พอร์ต และกำลังเริ่มสแกนใหม่")
            except Exception as e:
                messagebox.showerror("ข้อผิดพลาดในการวิเคราะห์ JSON", f"รูปแบบ JSON ไม่ถูกต้อง:\n{str(e)}")

        def clear_ports():
            if os.path.exists(ports_file):
                try:
                    os.remove(ports_file)
                except Exception as e:
                    self.write_log(f"ลบไฟล์ ports.json ล้มเหลว: {e}", "error")
            self.write_log("รีเซ็ตเป็นพอร์ตสแกนอัตโนมัติเริ่มต้นเรียบร้อยแล้ว", "warning")
            self.scan_devices()
            dialog.destroy()
            messagebox.showinfo("สำเร็จ", "รีเซ็ตพอร์ตเป็นค่าเริ่มต้น และกำลังเริ่มสแกนใหม่")

        ModernButton(btn_frame, text="💾 บันทึกพอร์ต", command=save_ports, bg=ACCENT_GREEN, activebg="#2ecc71").pack(side="left", fill="x", expand=True, padx=(0, 5))
        ModernButton(btn_frame, text="🧹 รีเซ็ตเป็นค่าเริ่มต้น", command=clear_ports, bg=ACCENT_ORANGE, activebg="#d35400").pack(side="left", fill="x", expand=True, padx=5)
        ModernButton(btn_frame, text="❌ ยกเลิก", command=dialog.destroy, bg=BG_INPUT, activebg="#444444").pack(side="right", padx=(5, 0))

    # --- ส่วนการสแกนอุปกรณ์ ---
    def scan_devices(self):
        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self):
        ports = self.controller.load_ports()
        if not ports:
            self.write_log("⚠️ ไม่พบรายชื่อพอร์ตที่จะสแกน กรุณาเปิดหน้าตั้งค่า (Settings) และนำเข้าพอร์ตจาก JSON (AI) ก่อน", "warning")
            self.after(0, lambda: self.update_device_checklist([]))
            return

        self.write_log("🔄 กำลังค้นหาและเชื่อมต่อ Emulator ของคุณ...", "info")
        devices, log_str = self.controller.scan_and_connect_all()
        if log_str:
            for line in log_str.split("\n"):
                # แปลงบันทึกการเชื่อมต่อเป็นภาษาไทยใน Log
                thai_line = line.replace("Starting auto-scan of common emulator ports...", "เริ่มค้นหาช่องทางเชื่อมต่อ Emulator ทั่วไป...")
                thai_line = thai_line.replace("Connected to", "เชื่อมต่อสำเร็จกับพอร์ต")
                thai_line = thai_line.replace("Current active devices:", "รายชื่อ Emulator ที่กำลังเชื่อมต่อตอนนี้:")
                thai_line = thai_line.replace("None", "ไม่พบ")
                
                if "✅" in line:
                    self.write_log(thai_line, "success")
                else:
                    self.write_log(thai_line, "info")

        # อัปเดตรายชื่อเช็คลิสต์บนหน้าต่างหลัก
        self.after(0, lambda: self.update_device_checklist(devices))

    def update_device_checklist(self, active_devices):
        # ล้างคอมโพเนนต์เช็คลิสต์อันเก่าออกก่อน
        for widget in self.device_scroll_frame.winfo_children():
            widget.destroy()

        self.device_checkboxes.clear()
        self.device_frames.clear()

        if not active_devices:
            lbl = tk.Label(self.device_scroll_frame, text="ไม่พบ Emulator ที่เปิดอยู่\nกรุณาเปิด Emulator ก่อน\nหรือเชื่อมต่อแบบแมนนวล", bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="center")
            lbl.pack(pady=20, fill="x")
            ModernButton(
                self.device_scroll_frame,
                text="ไปตั้งค่าพอร์ต",
                command=lambda: self.select_page("settings"),
                bg=BG_INPUT,
                activebg="#444444",
                font=("Segoe UI", 9, "bold")
            ).pack(fill="x", padx=10, pady=(0, 10))
            self.update_status_summary()
            return

        for idx, dev in enumerate(active_devices):
            frame = tk.Frame(self.device_scroll_frame, bg=BG_CARD, bd=1, relief="solid", highlightthickness=0)
            frame.configure(highlightbackground="#444444")
            frame.pack(fill="x", pady=4, padx=2)

            self.device_frames[dev] = frame

            # สร้างตัวแปรเช็คลิสต์และให้เลือกไว้โดยเริ่มต้น (True)
            chk_var = tk.BooleanVar(value=True)
            self.device_checkboxes[dev] = chk_var

            # วาดเช็คบ็อกซ์จอ
            lbl_text = dev
            if len(lbl_text) > 18:
                lbl_text = lbl_text[:16] + "..."
                
            chk = tk.Checkbutton(
                frame, 
                text=lbl_text, 
                variable=chk_var, 
                command=self.update_status_summary,
                bg=BG_CARD, 
                fg=FG_WHITE, 
                activebackground=BG_CARD, 
                activeforeground=FG_WHITE,
                selectcolor=BG_DARK, 
                relief="flat", 
                font=("Segoe UI", 10, "bold")
            )
            chk.pack(side="left", padx=5, pady=5)

            # ปุ่มกากบาทตัดการเชื่อมต่อทีละจอ
            disc_btn = tk.Button(
                frame,
                text="X",
                command=lambda d=dev: self.disconnect_one(d),
                bg="#E74C3C",
                fg=FG_WHITE,
                activebackground="#c0392b",
                activeforeground=FG_WHITE,
                relief="flat",
                bd=0,
                font=("Segoe UI", 8, "bold"),
                width=2
            )
            disc_btn.pack(side="right", padx=5, pady=5)

            # จุดสถานะสด (เขียว=ต่ออยู่เฉยๆ, ฟ้า=กำลังรัน, แดง=ติดปัญหาล่าสุด) — รีเฟรชสีเองใน _tick_home_progress
            dot = tk.Label(frame, text="●", bg=BG_CARD, fg=ACCENT_GREEN, font=("Segoe UI", 9))
            dot.pack(side="right", padx=(0, 4))
            self.device_dot_labels[dev] = dot

        self._refresh_device_dots()
        self.update_status_summary()

    def _refresh_device_dots(self):
        """อัปเดตสีจุดสถานะข้างชื่อจอในแถบซ้าย ให้ตรงกับสถานะรันสดล่าสุด (เรียกซ้ำได้บ่อยๆ แบบเบา
        เพราะแค่ reconfigure Label ที่มีอยู่แล้ว ไม่ต้องสร้าง widget ใหม่)"""
        run_state = getattr(self, "_device_run_state", {}) or {}
        for dev, dot in getattr(self, "device_dot_labels", {}).items():
            try:
                if not dot.winfo_exists():
                    continue
            except Exception:
                continue
            st = run_state.get(dev, {}).get("status")
            color = {"running": ACCENT_BLUE, "stuck": ACCENT_RED, "queued": FG_MUTED,
                     "stopped": FG_MUTED}.get(st, ACCENT_GREEN)
            dot.configure(fg=color)

    def disconnect_one(self, device_id):
        def worker():
            self.write_log(f"กำลังตัดการเชื่อมต่อกับ {device_id}...", "warning")
            self.controller.disconnect_device(device_id)
            self.scan_devices()
        threading.Thread(target=worker, daemon=True).start()

    def manual_connect(self):
        addr = self.manual_port_entry.get().strip()
        if not addr:
            return
            
        def worker():
            self.write_log(f"กำลังเชื่อมต่อแบบระบุพอร์ตไปยัง {addr}...", "info")
            success, output = self.controller.connect_device(addr)
            if success:
                self.write_log(f"ผลลัพธ์เชื่อมต่อ: {output}", "success")
            else:
                self.write_log(f"เชื่อมต่อล้มเหลว: {output}", "error")
            self.scan_devices()
            
        threading.Thread(target=worker, daemon=True).start()

    def get_selected_devices(self):
        selected = [dev for dev, var in self.device_checkboxes.items() if var.get()]
        if not selected:
            messagebox.showwarning("คำเตือน", "กรุณาเลือก Emulator ในลิสต์ซ้ายมืออย่างน้อย 1 จอ!")
        return selected

    # --- ตรวจสอบขนาดหน้าจอและ DPI ---
    def check_machine_capacity(self):
        """ตรวจสเปกเครื่อง แล้วบอกว่ารัน MuMu ได้สูงสุดกี่จอ (ภายใต้โปรไฟล์มาตรฐาน)"""
        specs = get_host_specs()
        if not specs.get("available_ok"):
            self.capacity_result_lbl.configure(
                text=f"❌ อ่านสเปกเครื่องไม่ได้: {specs.get('error', 'ไม่ทราบสาเหตุ')}",
                fg=ACCENT_RED)
            self.write_log("❌ ตรวจขีดจำกัดเครื่องไม่สำเร็จ (psutil ใช้ไม่ได้)", "error")
            return

        est = estimate_mumu_capacity(specs)
        rec = est["recommended"]
        bottleneck_txt = "RAM" if est["bottleneck"] == "RAM" else "CPU"

        lines = [
            f"🖥️  เครื่องนี้: CPU {specs['logical_cores']} คอร์ (จริง {specs['physical_cores']} คอร์)  ·  "
            f"RAM รวม {specs['total_ram_gb']:g}GB  ·  ว่างตอนนี้ {specs['available_ram_gb']:g}GB",
            "",
            f"✅ แนะนำให้รันสูงสุด: {rec} จอ  (เต็มประสิทธิภาพ)",
            f"     • คอขวดหลัก: {bottleneck_txt}",
            f"     • เพดานจาก RAM: {est['ram_limit']} จอ   (3GB/จอ, กันระบบ {est['reserve_ram']:g}GB)",
            f"     • เพดานจาก CPU: {est['cpu_limit']} จอ   (2 คอร์/จอ, กันระบบ {est['reserve_cores']} คอร์)",
            f"🔋 ตอนนี้ RAM ว่างพอเปิดเพิ่มได้อีกราว: {est['open_now']} จอ",
        ]

        warn = []
        if rec < 1:
            warn.append("⚠️ สเปกเครื่องไม่พอรันแม้แต่ 1 จอภายใต้ค่านี้ — ลด RAM/จอ หรือเพิ่ม RAM เครื่อง")
        if est["open_now"] < rec:
            warn.append("ℹ️ ปิดโปรแกรมอื่นที่กิน RAM อยู่ จะเปิดได้ใกล้เพดานแนะนำมากขึ้น")
        if warn:
            lines.append("")
            lines.extend(warn)

        color = ACCENT_RED if rec < 1 else (ACCENT_GREEN if rec >= 1 else ACCENT_ORANGE)
        self.capacity_result_lbl.configure(text="\n".join(lines), fg=color)
        self.write_log(
            f"🖥️ ขีดจำกัดเครื่อง: แนะนำ {rec} จอ (RAM≤{est['ram_limit']} / CPU≤{est['cpu_limit']}, "
            f"คอขวด {bottleneck_txt})", "success")

    def validate_resolutions(self):
        devices = self.get_selected_devices()
        if not devices:
            return
            
        def worker():
            self.write_log("📋 กำลังตรวจสอบขนาดหน้าจอและความหนาแน่น DPI...", "warning")
            for dev in devices:
                res = self.controller.get_resolution(dev)
                dpi = self.controller.get_dpi(dev)
                
                # เงื่อนไขตรวจสอบ
                is_correct_res = (res == "960x540" or res == "540x960")
                is_correct_dpi = (dpi == "160")
                
                status_res = "✅ ถูกต้อง" if is_correct_res else f"❌ ไม่ถูกต้อง (ต้องเป็น 960x540 แต่พบเป็น {res})"
                status_dpi = "✅ ถูกต้อง" if is_correct_dpi else f"❌ ไม่ถูกต้อง (ต้องเป็น 160 DPI แต่พบเป็น {dpi})"
                
                log_color = "success" if (is_correct_res and is_correct_dpi) else "error"
                self.write_log(f"อุปกรณ์: {dev} -> ขนาดหน้าจอ: {res} ({status_res}) | ความหนาแน่น: {dpi} DPI ({status_dpi})", log_color)
                
        threading.Thread(target=worker, daemon=True).start()

    def toggle_pointer_location(self, enable):
        devices = self.get_selected_devices()
        if not devices:
            return
            
        val = "1" if enable else "0"
        state_str = "เปิด" if enable else "ปิด"
        
        def worker():
            self.write_log(f"📋 กำลัง{state_str}การแสดงพิกัดจิ้ม (Pointer Location)...", "warning")
            for dev in devices:
                success, out = self.controller.run_adb_cmd(["-s", dev, "shell", "settings", "put", "system", "pointer_location", val])
                if success:
                    self.write_log(f"   [{dev}] {state_str}แสดงพิกัดเรียบร้อยแล้ว", "success")
                else:
                    self.write_log(f"   [{dev}] ตั้งค่าล้มเหลว: {out}", "error")
                    
        threading.Thread(target=worker, daemon=True).start()

    # --- ฟังก์ชันควบคุมแมนนวลพร้อมกัน ---
    def send_manual_click(self):
        devices = self.get_selected_devices()
        if not devices:
            return
        x = self.manual_x.get().strip()
        y = self.manual_y.get().strip()
        if not x or not y:
            return
            
        def worker():
            self.write_log(f"กำลังคลิกหน้าจอที่พิกัด ({x}, {y}) บนอุปกรณ์ที่เลือกทั้งหมด...", "info")
            results = self.controller.run_parallel_action(devices, self.controller.tap, x, y)
            for dev, (success, out) in results.items():
                if success:
                    self.write_log(f"   [{dev}] คลิกหน้าจอสำเร็จ", "info")
                else:
                    self.write_log(f"   [{dev}] คลิกหน้าจอล้มเหลว: {out}", "error")
        threading.Thread(target=worker, daemon=True).start()

    def send_manual_text(self):
        devices = self.get_selected_devices()
        if not devices:
            return
        txt = self.manual_txt_entry.get().strip()
        if not txt:
            return
            
        def worker():
            self.write_log(f"กำลังพิมพ์ข้อความ '{txt}' บนอุปกรณ์ที่เลือกทั้งหมด...", "info")
            results = self.controller.run_parallel_action(devices, self.controller.input_text, txt)
            for dev, (success, out) in results.items():
                if success:
                    self.write_log(f"   [{dev}] พิมพ์ข้อความสำเร็จ", "info")
                else:
                    self.write_log(f"   [{dev}] พิมพ์ข้อความล้มเหลว: {out}", "error")
        threading.Thread(target=worker, daemon=True).start()

    def send_manual_key(self, code):
        devices = self.get_selected_devices()
        if not devices:
            return
            
        def worker():
            self.write_log(f"กำลังจำลองกดปุ่มระบบ (รหัสปุ่ม: {code}) บนอุปกรณ์ที่เลือกทั้งหมด...", "info")
            results = self.controller.run_parallel_action(devices, self.controller.keyevent, code)
            for dev, (success, out) in results.items():
                if success:
                    self.write_log(f"   [{dev}] ส่งคำสั่งกดปุ่ม {code} สำเร็จ", "info")
                else:
                    self.write_log(f"   [{dev}] ส่งคำสั่งปุ่มล้มเหลว: {out}", "error")
        threading.Thread(target=worker, daemon=True).start()

    def send_custom_cmd(self):
        devices = self.get_selected_devices()
        if not devices:
            return
        raw_args = self.custom_cmd_entry.get().strip().split()
        if not raw_args:
            return
            
        def worker():
            full_args = ["shell"] + raw_args
            self.write_log(f"กำลังส่งคำสั่งระบบแบบบรอดแคสต์: adb shell {' '.join(raw_args)}", "warning")
            
            def run_single(dev):
                return self.controller.run_adb_cmd(["-s", dev] + full_args)
                
            results = self.controller.run_parallel_action(devices, run_single)
            for dev, (success, out) in results.items():
                if success:
                    self.write_log(f"   [{dev}] ผลลัพธ์: {out}", "success")
                else:
                    self.write_log(f"   [{dev}] ล้มเหลว: {out}", "error")
        threading.Thread(target=worker, daemon=True).start()

    def send_manual_screenshot(self):
        devices = self.get_selected_devices()
        if not devices:
            self.write_log("⚠️ ไม่สามารถถ่ายภาพหน้าจอได้: กรุณาเลือก Emulator ด้านซ้ายอย่างน้อย 1 เครื่อง!", "warning")
            return
            
        filename_pattern = self.manual_screenshot_entry.get().strip() or "screenshots/{DATE}/screenshot_{NAME}_{TIME}.png"
        checked_accounts = [acc for acc in self.accounts if acc.get("checked", True)]
        
        # ค้นหาคู่ของ emulator และบัญชี
        paired_list = []
        for idx, dev in enumerate(devices):
            acc = None
            if hasattr(self, 'device_active_accounts') and dev in self.device_active_accounts:
                acc = self.device_active_accounts[dev]
            else:
                acc = checked_accounts[idx] if idx < len(checked_accounts) else None
            paired_list.append((dev, acc))
            
        def worker():
            from concurrent.futures import ThreadPoolExecutor
            self.write_log(f"📸 กำลังบันทึกภาพหน้าจอแบบบรอดแคสต์จาก Emulator ทั้งหมด {len(devices)} เครื่อง...", "info")
            
            def capture_single(pair):
                dev, acc = pair
                filename = filename_pattern
                
                # ดึงวันและเวลา ณ ปัจจุบัน
                from datetime import datetime
                now = datetime.now()
                date_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%H-%M-%S")
                
                if acc:
                    filename = filename.replace("{EMAIL}", acc.get("email", "no_account"))
                    filename = filename.replace("{PASSWORD}", acc.get("password", "no_password"))
                    filename = filename.replace("{NAME}", acc.get("name", ""))
                    filename = filename.replace("{GROUP}", acc.get("group", "no_group"))
                else:
                    filename = filename.replace("{EMAIL}", "no_account")
                    filename = filename.replace("{PASSWORD}", "no_password")
                    filename = filename.replace("{NAME}", "no_name")
                    filename = filename.replace("{GROUP}", "no_group")
                
                filename = filename.replace("{DATE}", date_str)
                filename = filename.replace("{TIME}", time_str)
                
                # ปรับแต่งเครื่องหมายและอักขระที่ปลอดภัยสำหรับ Windows (รองรับภาษาไทย อังกฤษ ตัวเลข และสัญลักษณ์ที่ปลอดภัย)
                import string
                safe_device = dev.replace(":", "_").replace(".", "_")
                filename = filename.replace("{DEVICE}", safe_device)
                
                def is_safe_char(c):
                    return c.isalnum() or c in "-_.() /\\" or ('\u0e00' <= c <= '\u0e7f')
                
                filename = "".join(c for c in filename if is_safe_char(c))
                
                if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    filename += ".png"
                    
                screenshots_dir = os.path.dirname(os.path.abspath(filename))
                if screenshots_dir and not os.path.exists(screenshots_dir):
                    os.makedirs(screenshots_dir, exist_ok=True)
                    
                success, err = self.controller.take_screenshot(dev, filename)
                return dev, success, filename, err

            # รันการแคปจอพร้อมกันแบบขนาน (Parallel screenshot captures)
            with ThreadPoolExecutor(max_workers=max(1, len(paired_list))) as executor:
                results = list(executor.map(capture_single, paired_list))
                
            for dev, success, filename, err in results:
                if success:
                    self.write_log(f"   [{dev}] บันทึกสำเร็จ: '{filename}'", "success")
                else:
                    self.write_log(f"   [{dev}] บันทึกภาพล้มเหลว: {err}", "error")
                    
        threading.Thread(target=worker, daemon=True).start()

    # ===== ระบบอ่านจำนวนเพชร (Diamond OCR) =====
    def load_diamond_config(self):
        """โหลดการตั้งค่าระบบอ่านเพชร (พื้นที่ครอป + threshold + ที่อยู่ไฟล์ export) จาก diamond_ocr.json
        ถ้าไม่มีไฟล์หรืออ่านไม่ได้ จะคืนค่าดีฟอลต์ (พื้นที่เริ่มต้นเดาไว้สำหรับความละเอียด 960x540)"""
        defaults = {
            "region": {"x": 400, "y": 14, "w": 80, "h": 24},
            "threshold": 0.6,
            "export_path": "diamond_export.json",
            "web_base_url": "",
            "auto_push": True,
            # ยืนยันตัวตนก่อนเขียนเพชร (กันอ่านผิดจอ/เขียนผิดบัญชี):
            # OCR ชื่อในเกมมุมซ้ายบน เทียบกับ ingamename ของบัญชี ถ้าไม่ตรง -> ไม่เขียน
            "verify_name": True,
            "name_region": {"x": 90, "y": 18, "w": 140, "h": 26},
            "name_match_ratio": 0.72,
        }
        try:
            if os.path.exists(self.diamond_config_file):
                with open(self.diamond_config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    defaults.update(data)
        except Exception as e:
            self.write_log(f"โหลดการตั้งค่าระบบอ่านเพชรขัดข้อง: {e}", "warning")
        return defaults

    def save_diamond_config(self):
        """บันทึกการตั้งค่าระบบอ่านเพชรลงไฟล์ diamond_ocr.json"""
        try:
            with open(self.diamond_config_file, "w", encoding="utf-8") as f:
                json.dump(self.diamond_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.write_log(f"บันทึกการตั้งค่าระบบอ่านเพชรล้มเหลว: {e}", "error")

    def load_guild_config(self):
        """โหลดการตั้งค่าดึงรายชื่อสมาชิกชมรม (พื้นที่คอลัมน์ชื่อ) จาก guild_ocr.json"""
        defaults = {"region": {"x": 0, "y": 0, "w": 0, "h": 0}}
        try:
            if os.path.exists(self.guild_config_file):
                with open(self.guild_config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    defaults.update(data)
        except Exception as e:
            self.write_log(f"โหลดการตั้งค่าดึงรายชื่อชมรมขัดข้อง: {e}", "warning")
        return defaults

    def load_game_reset_config(self):
        """โหลดการตั้งค่ารีเซ็ตเกมเมื่อบัญชีติดปัญหา (game_reset.json)
        ดีฟอลต์: ปิด/เปิดเกม Kuroko + 3 ทาปเปิดช่อง login ที่ผู้ใช้ให้มา"""
        defaults = {
            "enabled": True,
            "package": "com.lmdgame.kuroko.sea",
            "boot_wait": 35.0,          # รอเกม boot หลังเปิดใหม่ (วินาที)
            "open_login_steps": [        # ลำดับกดจากหน้า home -> ช่องกรอก login โผล่
                {"type": "tap", "x": "925", "y": "96", "delay": 5.0, "desc": "ไอดี"},
                {"type": "tap", "x": "621", "y": "192", "delay": 1.0, "desc": "สลับ"},
                {"type": "tap", "x": "478", "y": "387", "delay": 1.0, "desc": "ใช้เมล"},
            ],
        }
        try:
            if os.path.exists(self.game_reset_file):
                with open(self.game_reset_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    defaults.update(data)
        except Exception as e:
            self.write_log(f"โหลดการตั้งค่ารีเซ็ตเกมขัดข้อง: {e}", "warning")
        return defaults

    def _reset_device_to_login(self, device):
        """รีเซ็ตเกมบนจอนี้ให้กลับมา 'ช่องกรอก login' (ใช้เมื่อบัญชีติดปัญหากลางคัน)
        ปิดเกม -> เปิดใหม่ -> รอ boot -> รันสเต็ปเปิดช่อง login -> พร้อมรับบัญชีถัดไป
        คืน True ถ้าทำครบ (ไม่การันตีว่าถึงหน้า login เป๊ะ แต่ทำให้จอไม่ค้างสภาพเดิม)"""
        cfg = self.game_reset_config or {}
        if not cfg.get("enabled", True):
            return False
        pkg = (cfg.get("package") or "").strip()
        if not pkg:
            self.write_log(f"   ⚠️ [{device}] ยังไม่ได้ตั้งชื่อ package เกม -> ข้ามการรีเซ็ต", "warning")
            return False
        try:
            self.write_log(f"   🔄 [{device}] รีเซ็ตเกม: ปิด {pkg} แล้วเปิดใหม่...", "warning")
            self.controller.stop_app(device, pkg)
            time.sleep(2.0)
            self.controller.launch_app_by_package(device, pkg)

            # รอ boot — poll จนแคปจอได้ต่อเนื่อง หรือครบ boot_wait
            boot_wait = float(cfg.get("boot_wait", 35.0) or 35.0)
            deadline = time.time() + boot_wait
            while time.time() < deadline:
                if not self.macro_running:
                    return False
                time.sleep(3.0)
                ok, _ = self.controller.capture_screenshot_bytes(device)
                if not ok:
                    # เผื่อ ADB หลุดชั่วคราวตอน restart -> ลองต่อใหม่ 1 ครั้ง (safety net)
                    self.controller.run_adb_cmd(["connect", device])
            # รันสเต็ปเปิดช่อง login — รองรับ anchor (รอจนเห็นภาพก่อนกด ไม่กดตาบอด)
            for st in cfg.get("open_login_steps", []):
                if not self.macro_running:
                    return False
                if st.get("anchor_img"):
                    gate, _ax, _ay = self._wait_for_step_anchor(device, st)
                    if gate == "stopped":
                        return False
                    if gate == "missing":
                        # หน้าไม่ตรง (boot ช้ากว่าคาด/สลับบัญชีไม่ขึ้น) -> กดต่อแบบ best-effort
                        self.write_log(f"   ⚠️ [{device}] รีเซ็ต: ไม่เจอ anchor '{st.get('desc','')}' -> กดตามพิกัด", "warning")
                try:
                    x, y = int(float(st.get("x"))), int(float(st.get("y")))
                    self.controller.tap(device, x, y)
                    time.sleep(float(st.get("delay", 1.0) or 1.0))
                except (TypeError, ValueError):
                    continue
            self.write_log(f"   ✅ [{device}] รีเซ็ตเกมเสร็จ -> พร้อมรับบัญชีถัดไป", "success")
            return True
        except Exception as e:
            self.write_log(f"   ❌ [{device}] รีเซ็ตเกมล้มเหลว: {e}", "error")
            return False

    def save_guild_config(self):
        """บันทึกการตั้งค่าดึงรายชื่อสมาชิกชมรมลงไฟล์ guild_ocr.json"""
        try:
            with open(self.guild_config_file, "w", encoding="utf-8") as f:
                json.dump(self.guild_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.write_log(f"บันทึกการตั้งค่าดึงรายชื่อชมรมล้มเหลว: {e}", "error")

    def _load_gemini_api_key(self):
        """โหลด Gemini API key: ไฟล์ gemini_config.json ก่อน -> env var GEMINI_API_KEY -> ว่าง"""
        try:
            if os.path.exists(self.gemini_config_file):
                with open(self.gemini_config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("api_key"):
                    return str(data["api_key"]).strip()
        except Exception:
            pass
        return os.environ.get("GEMINI_API_KEY", "")

    def _save_gemini_api_key_to_file(self):
        """บันทึก Gemini API key ปัจจุบันลงไฟล์ gemini_config.json ให้อยู่ถาวรข้ามการรีสตาร์ท"""
        try:
            with open(self.gemini_config_file, "w", encoding="utf-8") as f:
                json.dump({"api_key": self.gemini_api_key}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.write_log(f"บันทึก Gemini API Key ลงไฟล์ล้มเหลว: {e}", "error")

    def _build_screenshot_filename(self, pattern, account, device):
        """สร้างชื่อไฟล์ภาพจากแพทเทิร์น แทนที่ {EMAIL}/{PASSWORD}/{NAME}/{GROUP}/{DATE}/{TIME}/{DEVICE}
        และกรองอักขระให้ปลอดภัยกับ Windows (รองรับไทย/อังกฤษ/ตัวเลข/สัญลักษณ์ปลอดภัย)"""
        from datetime import datetime
        now = datetime.now()
        filename = pattern or "screenshots/{DATE}/screenshot_{NAME}_{TIME}.png"
        if account:
            filename = filename.replace("{EMAIL}", account.get("email", "no_account"))
            filename = filename.replace("{PASSWORD}", account.get("password", "no_password"))
            filename = filename.replace("{NAME}", account.get("name", ""))
            filename = filename.replace("{GROUP}", account.get("group", "no_group"))
        else:
            filename = filename.replace("{EMAIL}", "no_account")
            filename = filename.replace("{PASSWORD}", "no_password")
            filename = filename.replace("{NAME}", "no_name")
            filename = filename.replace("{GROUP}", "no_group")
        filename = filename.replace("{DATE}", now.strftime("%Y-%m-%d"))
        filename = filename.replace("{TIME}", now.strftime("%H-%M-%S"))
        filename = filename.replace("{DEVICE}", device.replace(":", "_").replace(".", "_"))

        def is_safe_char(c):
            return c.isalnum() or c in "-_.() /\\" or ('฀' <= c <= '๿')

        filename = "".join(c for c in filename if is_safe_char(c))
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            filename += ".png"
        return filename

    def capture_and_read_diamonds(self):
        """แคปจอทุกเครื่องที่เลือก เซฟรูปตั้งชื่อตามบัญชีที่ล็อกอินล่าสุด อ่านจำนวนเพชรบนหัวจอ
        แล้ว Export ผลเป็น JSON (รหัส/ชื่อ/จำนวนเพชร/เวลา) เพื่อเอาไปใช้ต่อ"""
        devices = self.get_selected_devices()
        if not devices:
            self.write_log("⚠️ อ่านเพชรไม่ได้: กรุณาเลือก Emulator ด้านซ้ายอย่างน้อย 1 เครื่อง!", "warning")
            return

        region = (self.diamond_config or {}).get("region") or {}

        # ตรวจว่าตั้งค่าพื้นที่แล้ว + มี Tesseract OCR แล้วหรือยัง
        if int(region.get("w", 0)) <= 0 or int(region.get("h", 0)) <= 0:
            messagebox.showwarning("ยังไม่ได้ตั้งค่า",
                "ยังไม่ได้กำหนดพื้นที่ตัวเลขเพชร\nกรุณากดปุ่ม '⚙️ ตั้งค่าพื้นที่เพชร' ก่อน", parent=self)
            return
        if not find_tesseract():
            messagebox.showwarning("ไม่พบ Tesseract OCR",
                "ระบบอ่านเพชรต้องใช้ Tesseract OCR (ตัวอ่านตัวอักษร) ซึ่งยังไม่ได้ติดตั้ง\n\n"
                "วิธีติดตั้ง: เปิด PowerShell แล้วรันคำสั่ง\n"
                "    winget install UB-Mannheim.TesseractOCR\n\n"
                "หรือดาวน์โหลดจาก https://github.com/UB-Mannheim/tesseract/wiki\n"
                "ติดตั้งเสร็จแล้วเปิดโปรแกรมนี้ใหม่", parent=self)
            return

        filename_pattern = self.manual_screenshot_entry.get().strip() or "screenshots/{DATE}/screenshot_{NAME}_{TIME}.png"
        checked_accounts = [acc for acc in self.accounts if acc.get("checked", True)]

        # จับคู่ emulator กับบัญชี (ตรรกะเดียวกับการแคปจอแมนนวล: ใช้บัญชีที่รันล่าสุดบนเครื่องนั้น)
        paired_list = []
        for idx, dev in enumerate(devices):
            acc = None
            if hasattr(self, 'device_active_accounts') and dev in self.device_active_accounts:
                acc = self.device_active_accounts[dev]
            else:
                acc = checked_accounts[idx] if idx < len(checked_accounts) else None
            paired_list.append((dev, acc))

        def worker():
            from concurrent.futures import ThreadPoolExecutor
            from datetime import datetime
            self.write_log(f"💎 กำลังแคปจอและอ่านเพชรจาก Emulator {len(devices)} เครื่อง...", "info")

            def process_single(pair):
                dev, acc = pair
                ok, data = self.controller.capture_screenshot_bytes(dev)
                if not ok:
                    return {"device": dev, "account": acc, "ok": False, "diamonds": None, "file": ""}
                # เซฟรูปตั้งชื่อตามบัญชี (ใช้ bytes ชุดเดียวกับที่อ่านเพชร — แคปครั้งเดียว)
                saved_file = ""
                try:
                    filename = self._build_screenshot_filename(filename_pattern, acc, dev)
                    out_dir = os.path.dirname(os.path.abspath(filename))
                    if out_dir and not os.path.exists(out_dir):
                        os.makedirs(out_dir, exist_ok=True)
                    with open(filename, "wb") as f:
                        f.write(data)
                    saved_file = filename
                except Exception as e:
                    self.write_log(f"   ⚠️ [{dev}] เซฟรูปไม่สำเร็จ: {e}", "warning")
                # อ่านเลขเพชรจาก bytes ด้วย Tesseract OCR
                rok, number, _raw = self.controller.read_number_tesseract(data, region)
                return {"device": dev, "account": acc, "ok": rok, "diamonds": number, "file": saved_file}

            with ThreadPoolExecutor(max_workers=max(1, len(paired_list))) as executor:
                results = list(executor.map(process_single, paired_list))

            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today = datetime.now().strftime("%Y-%m-%d")
            export_rows = []
            for r in results:
                acc = r.get("account") or {}
                email = acc.get("email", "")
                name = account_display_name(acc) if acc else ""
                web_id = (acc.get("save_web_game_id") or "").strip()
                diamonds = r.get("diamonds")
                export_rows.append({
                    "email": email, "name": name, "save_web_game_id": web_id,
                    "diamonds": diamonds, "device": r["device"], "time": stamp,
                })
                who = name or email or "no_account"
                if r["ok"]:
                    self.write_log(f"   💎 [{r['device']}] {who}: {diamonds} เพชร", "success")
                else:
                    self.write_log(f"   ❌ [{r['device']}] {who}: อ่านจำนวนเพชรไม่ได้ (ลองปรับพื้นที่ให้ครอบเฉพาะตัวเลข ไม่เอาไอคอน)", "error")

            self._write_and_push_diamonds(export_rows, show_summary=True)

        threading.Thread(target=worker, daemon=True).start()

    def _write_and_push_diamonds(self, export_rows, show_summary=True):
        """เขียนผลเพชรลง diamond_export.json แล้วส่งเข้าเว็บ Save_Web_Game อัตโนมัติ
        (ใช้ร่วมกันระหว่างปุ่ม '💎 แคปจอ + อ่านเพชร' กับ step 'อ่านเพชร' ตอนจบรันมาโคร)

        export_rows: list ของ dict {email, name, save_web_game_id, diamonds, device, time}
        คืน push_results (dict id -> (ok, msg))
        """
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        export_path = (self.diamond_config or {}).get("export_path") or "diamond_export.json"
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(export_rows, f, ensure_ascii=False, indent=2)
            self.write_log(f"📤 Export เพชรสำเร็จ: {os.path.abspath(export_path)} ({len(export_rows)} รายการ)", "success")
        except Exception as e:
            self.write_log(f"❌ เขียนไฟล์ Export ล้มเหลว: {e}", "error")

        # ส่งเพชรเข้าเว็บ Save_Web_Game อัตโนมัติ (จับคู่ด้วย save_web_game_id = id ของเว็บ)
        push_results = {}
        cfg = self.diamond_config or {}
        web_base_url = (cfg.get("web_base_url") or "").strip()
        if cfg.get("auto_push", True) and web_base_url:
            updates = [
                {"id": row["save_web_game_id"], "diamonds": row["diamonds"], "lastFarmDate": today}
                for row in export_rows
                if row.get("save_web_game_id") and row.get("diamonds") is not None
            ]
            if updates:
                self.write_log(f"🌐 กำลังส่งเพชรเข้าเว็บ {len(updates)} บัญชี -> {web_base_url}", "info")
                try:
                    push_results, push_stats = push_diamonds_to_web(web_base_url, updates)
                    self.write_log(
                        f"🌐 ส่งเข้าเว็บ: สำเร็จ {push_stats['sent']} / ล้มเหลว {push_stats['failed']}",
                        "success" if push_stats["failed"] == 0 else "warning")
                    for acc_id, (ok, msg) in push_results.items():
                        if not ok:
                            self.write_log(f"   ❌ [web {acc_id}] {msg}", "error")
                except Exception as e:
                    self.write_log(f"❌ ส่งเข้าเว็บล้มเหลว: {e}", "error")
            else:
                self.write_log("🌐 ไม่มีบัญชีที่มี id เว็บ (save_web_game_id) ให้ส่ง — ข้ามการส่งเข้าเว็บ", "warning")
        elif not web_base_url:
            self.write_log("🌐 ยังไม่ได้ตั้ง URL เว็บ — ข้ามการส่งเข้าเว็บ (ตั้งได้ที่ปุ่ม ⚙️ ตั้งค่าพื้นที่เพชร)", "info")

        if show_summary:
            self.after(0, lambda: self._show_diamond_summary(export_rows, export_path, push_results))
        return push_results

    def _flush_run_diamonds(self):
        """ตอนจบรันมาโคร: เอาเพชรที่ step 'อ่านเพชร' เก็บไว้ระหว่างรัน ไป export + push เข้าเว็บ
        ทำในเธรดเบื้องหลัง (เขียนไฟล์ + ยิงเน็ตเวิร์ก) เพื่อไม่ให้ค้าง GUI"""
        rows = list(getattr(self, "run_diamond_rows", []))
        if not rows:
            return
        self.write_log(f"💎 จบรัน: กำลังอัพเดทเพชร {len(rows)} บัญชีที่อ่านได้ระหว่างรัน...", "info")
        threading.Thread(
            target=lambda: self._write_and_push_diamonds(rows, show_summary=True),
            daemon=True,
        ).start()

    def backfill_web_ids(self):
        """ดึงบัญชีจากเว็บ แล้วจับคู่กับบัญชีใน MuMuPow ด้วยชื่อ เพื่อเติม save_web_game_id (id เว็บ)"""
        base = (self.diamond_config or {}).get("web_base_url", "").strip()
        if not base:
            messagebox.showwarning("ยังไม่ได้ตั้ง URL เว็บ",
                "กรุณาตั้ง URL เว็บก่อน — กดปุ่ม '⚙️ ตั้งค่าพื้นที่เพชร' แล้วใส่ในช่อง 🌐 URL เว็บ", parent=self)
            return

        def worker():
            self.write_log(f"🔗 กำลังดึงบัญชีจากเว็บเพื่อจับคู่ id -> {base}", "info")
            try:
                web_accounts = fetch_web_accounts(base)
            except Exception as e:
                self.write_log(f"❌ ดึงบัญชีจากเว็บล้มเหลว: {e}", "error")
                self.after(0, lambda e=e: messagebox.showerror("ผิดพลาด", f"ดึงบัญชีจากเว็บไม่ได้:\n{e}", parent=self))
                return
            proposals = match_accounts_to_web(self.accounts, web_accounts)
            self.write_log(f"🔗 บัญชีในเว็บ {len(web_accounts)} รายการ | จับคู่ได้ {len(proposals)}", "info")
            self.after(0, lambda: self._show_backfill_review(proposals, len(web_accounts)))

        threading.Thread(target=worker, daemon=True).start()

    def _show_backfill_review(self, proposals, web_count):
        """หน้าต่างตรวจการจับคู่ id เว็บ — คลิกแถวเพื่อติ๊ก/เอาออก แล้วยืนยันเติม save_web_game_id"""
        if not proposals:
            messagebox.showinfo("ไม่พบคู่ที่จับได้",
                f"ดึงบัญชีจากเว็บ {web_count} รายการ แต่จับคู่กับบัญชีใน MuMuPow (ที่ยังไม่มี id) ไม่ได้เลย\n"
                "ตรวจว่าชื่อบัญชี (name) ตรงกับ title หรือ ingamename ในเว็บไหม", parent=self)
            return
        win = tk.Toplevel(self)
        win.title("🔗 ตรวจการจับคู่ id เว็บ")
        win.configure(bg=BG_DARK)
        win.transient(self)
        win.geometry("780x520")

        tk.Label(win, text=f"จับคู่ได้ {len(proposals)} บัญชี — คลิกแถวเพื่อติ๊ก/เอาออก แล้วกด 'ยืนยันเติม id'",
                 bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=15, pady=(15, 5))

        cols = ("use", "name", "web", "by")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=16)
        tree.heading("use", text="เลือก")
        tree.heading("name", text="บัญชี MuMuPow")
        tree.heading("web", text="→ เว็บ (title | id)")
        tree.heading("by", text="จับด้วย")
        tree.column("use", width=50, anchor="center")
        tree.column("name", width=300)
        tree.column("web", width=330)
        tree.column("by", width=80, anchor="center")
        tree.pack(fill="both", expand=True, padx=15, pady=5)

        accepted = {}
        for i, p in enumerate(proposals):
            iid = str(i)
            accepted[iid] = True
            tree.insert("", "end", iid=iid,
                        values=("☑", p["mumupow_name"], f"{p['web_title']} | {p['web_id']}", p["by"]))

        def toggle(event):
            iid = tree.identify_row(event.y)
            if not iid:
                return
            accepted[iid] = not accepted.get(iid, True)
            vals = list(tree.item(iid, "values"))
            vals[0] = "☑" if accepted[iid] else "☐"
            tree.item(iid, values=vals)
        tree.bind("<Button-1>", toggle)

        def set_all(val):
            for iid in accepted:
                accepted[iid] = val
                vals = list(tree.item(iid, "values"))
                vals[0] = "☑" if val else "☐"
                tree.item(iid, values=vals)

        def confirm():
            by_email = {(a.get("email") or "").strip().lower(): a for a in self.accounts}
            n = 0
            for i, p in enumerate(proposals):
                if not accepted.get(str(i)):
                    continue
                acc = by_email.get((p["email"] or "").strip().lower())
                if acc is not None:
                    acc["save_web_game_id"] = p["web_id"]
                    n += 1
            if n:
                self.save_accounts()
                try:
                    self.refresh_accounts_ui()
                except Exception:
                    pass
            self.write_log(f"🔗 เติม id เว็บให้ {n} บัญชีแล้ว", "success")
            messagebox.showinfo("สำเร็จ", f"เติม save_web_game_id ให้ {n} บัญชีเรียบร้อย", parent=win)
            win.destroy()

        btn = tk.Frame(win, bg=BG_DARK)
        btn.pack(fill="x", padx=15, pady=12)
        ModernButton(btn, text="เลือกทั้งหมด", variant="subtle", command=lambda: set_all(True)).pack(side="left")
        ModernButton(btn, text="ไม่เลือกเลย", variant="subtle", command=lambda: set_all(False)).pack(side="left", padx=8)
        ModernButton(btn, text="✅ ยืนยันเติม id", variant="primary", command=confirm).pack(side="right")
        ModernButton(btn, text="ปิด", variant="subtle", command=win.destroy).pack(side="right", padx=8)

    def _show_diamond_summary(self, rows, export_path, push_results=None):
        """หน้าต่างสรุปผลการอ่านเพชร (บัญชี/จำนวนเพชร/เครื่อง/สถานะส่งเข้าเว็บ) + ปุ่มเปิดโฟลเดอร์/บันทึกเป็น"""
        push_results = push_results or {}
        win = tk.Toplevel(self)
        win.title("💎 สรุปผลการอ่านเพชร")
        win.configure(bg=BG_DARK)
        win.transient(self)
        win.geometry("700x440")

        ok_count = sum(1 for r in rows if r.get("diamonds") is not None)
        sent_count = sum(1 for v in push_results.values() if v[0])
        head = f"อ่านสำเร็จ {ok_count}/{len(rows)} รายการ"
        if push_results:
            head += f"  •  ส่งเข้าเว็บ {sent_count}/{len(push_results)}"
        tk.Label(win, text=head, bg=BG_DARK, fg=FG_WHITE,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=15, pady=(15, 5))

        cols = ("name", "diamonds", "device", "web")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=12)
        tree.heading("name", text="บัญชี / ชื่อในเกม")
        tree.heading("diamonds", text="เพชร")
        tree.heading("device", text="เครื่อง")
        tree.heading("web", text="เว็บ")
        tree.column("name", width=230)
        tree.column("diamonds", width=80, anchor="center")
        tree.column("device", width=150)
        tree.column("web", width=180)
        tree.pack(fill="both", expand=True, padx=15, pady=5)

        def web_status(r):
            wid = (r.get("save_web_game_id") or "").strip()
            if not wid:
                return "⏭️ ข้าม (ไม่มี id)"
            if r.get("diamonds") is None:
                return "—"
            if wid in push_results:
                ok, msg = push_results[wid]
                return "✅ ส่งแล้ว" if ok else f"❌ {msg[:24]}"
            return "ไม่ได้ส่ง"

        for r in rows:
            label = r.get("name") or r.get("email") or "ไม่ทราบบัญชี"
            diamonds = r.get("diamonds")
            dia_text = "อ่านไม่ได้" if diamonds is None else f"{diamonds:,}"
            tree.insert("", "end", values=(label, dia_text, r.get("device", ""), web_status(r)))

        tk.Label(win, text=f"ไฟล์: {os.path.abspath(export_path)}", bg=BG_DARK, fg=FG_MUTED,
                 font=("Segoe UI", 9), wraplength=660, justify="left").pack(anchor="w", padx=15, pady=(5, 0))

        btn_row = tk.Frame(win, bg=BG_DARK)
        btn_row.pack(fill="x", padx=15, pady=12)
        ModernButton(btn_row, text="เปิดโฟลเดอร์ไฟล์", variant="subtle",
                     command=lambda: self._open_in_explorer(export_path)).pack(side="left")
        ModernButton(btn_row, text="บันทึกเป็น...", variant="accent",
                     command=lambda: self._save_diamond_export_as(rows)).pack(side="left", padx=8)
        ModernButton(btn_row, text="ปิด", variant="subtle", command=win.destroy).pack(side="right")

    def _open_in_explorer(self, path):
        """เปิดโฟลเดอร์ที่เก็บไฟล์ใน File Explorer (Windows)"""
        try:
            os.startfile(os.path.dirname(os.path.abspath(path)))
        except Exception as e:
            self.write_log(f"เปิดโฟลเดอร์ไม่สำเร็จ: {e}", "warning")

    def _save_diamond_export_as(self, rows):
        """บันทึกผลการอ่านเพชรเป็นไฟล์ JSON ไปยังตำแหน่งที่ผู้ใช้เลือก"""
        from datetime import datetime
        default_name = f"diamond_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json",
            initialfile=default_name, filetypes=[("JSON", "*.json"), ("ทั้งหมด", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            self.write_log(f"📤 บันทึกไฟล์ Export: {path}", "success")
        except Exception as e:
            self.write_log(f"❌ บันทึกไฟล์ล้มเหลว: {e}", "error")

    def open_diamond_setup(self):
        """หน้าต่างตั้งค่าระบบอ่านเพชร: จับภาพหน้าจอ -> ลากเลือกพื้นที่ตัวเลข -> สอนเลข 0-9 -> ทดสอบอ่าน
        ทำงานคล้าย Visual Recorder (จับภาพ -> แสดงบน canvas -> map พิกัดลากกลับเป็นพิกัดจริงด้วย scale)"""
        if self.macro_running:
            messagebox.showwarning("คำเตือน", "กรุณาปิดบอทมาโครก่อนตั้งค่าระบบอ่านเพชร", parent=self)
            return
        selected_devices = self.get_selected_devices() or self.controller.get_connected_devices()
        if not selected_devices:
            messagebox.showerror("ไม่พบอุปกรณ์", "ไม่พบ Emulator ที่เชื่อมต่ออยู่! กรุณาเปิดและเชื่อมต่อ Emulator ก่อน", parent=self)
            return

        import cv2
        import numpy as np

        if not find_tesseract():
            messagebox.showwarning("ไม่พบ Tesseract OCR",
                "ระบบอ่านเพชรต้องใช้ Tesseract OCR (ตัวอ่านตัวอักษร) ซึ่งยังไม่ได้ติดตั้ง\n\n"
                "ติดตั้งโดยเปิด PowerShell แล้วรัน:\n    winget install UB-Mannheim.TesseractOCR\n\n"
                "หรือดาวน์โหลดจาก https://github.com/UB-Mannheim/tesseract/wiki\n"
                "ติดตั้งเสร็จแล้วเปิดโปรแกรมนี้ใหม่", parent=self)
            return

        dialog = tk.Toplevel(self)
        dialog.title("💎 ตั้งค่าระบบอ่านเพชร — กำหนดพื้นที่ตัวเลข")
        dialog.configure(bg=BG_DARK)
        dialog.transient(self)
        dialog.grab_set()

        # sx = สเกลแสดงผล (native = display / sx)
        state = {"orig": None, "bytes": None, "sx": 1.0, "rect_id": None}
        temp_disp = os.path.join(self.templates_dir, "diamond_setup_disp.png")

        def on_close():
            try:
                if os.path.exists(temp_disp):
                    os.remove(temp_disp)
            except Exception:
                pass
            dialog.grab_release()
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW", on_close)

        # ซ้าย: canvas แสดงภาพหน้าจอ
        left = tk.Frame(dialog, bg=BG_DARK)
        left.pack(side="left", padx=15, pady=15)
        canvas = tk.Canvas(left, width=800, height=450, bg="#000000", highlightthickness=1, highlightbackground=BG_PANEL)
        canvas.pack()
        tk.Label(left, text="ลากเมาส์ครอบ 'เฉพาะตัวเลขเพชร' (อย่าเอาไอคอนเพชรเข้ามา) แล้วกด 'ทดสอบอ่านเลข' — Tesseract จะอ่านตัวเลขให้เอง ไม่ต้องสอนเลข",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), wraplength=780, justify="left").pack(anchor="w", pady=(6, 0))

        # ขวา: แผงควบคุม
        right = tk.Frame(dialog, bg=BG_DARK, padx=15, pady=15)
        right.pack(side="right", fill="both", expand=True)

        tk.Label(right, text="📱 เลือก Emulator:", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        dev_var = tk.StringVar(value=selected_devices[0])
        ttk.Combobox(right, textvariable=dev_var, values=selected_devices, state="readonly").pack(fill="x", pady=(2, 12))

        tk.Label(right, text="วิธีใช้:\n1) กดจับภาพหน้าจอ\n2) ลากครอบเฉพาะตัวเลขเพชร\n3) กดทดสอบอ่านเลข\n4) กดบันทึก",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 8))

        # URL เว็บ Save_Web_Game — สำหรับส่งจำนวนเพชรเข้าเว็บอัตโนมัติ (จับคู่ด้วย id)
        tk.Label(right, text="🌐 URL เว็บ Save_Web_Game (ใส่ครั้งเดียว):", bg=BG_DARK, fg=FG_WHITE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        web_url_entry = ModernEntry(right)
        web_url_entry.pack(fill="x", pady=(2, 2))
        web_url_entry.insert(0, (self.diamond_config or {}).get("web_base_url", ""))
        tk.Label(right, text="เช่น https://your-app.vercel.app — เว้นว่าง = ไม่ส่งเข้าเว็บ",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 8), justify="left").pack(anchor="w", pady=(0, 8))

        status = tk.Label(right, text="กด '📸 จับภาพหน้าจอ' เพื่อเริ่ม", bg=BG_DARK, fg=ACCENT_ORANGE,
                          font=("Segoe UI", 9), wraplength=240, justify="left")
        status.pack(fill="x", pady=10)

        def render():
            """แสดงภาพหน้าจอเต็มบน canvas พร้อมกรอบพื้นที่ที่ตั้งไว้ (sx = สเกล: native = display/sx)"""
            img = state["orig"]
            if img is None:
                return
            oh, ow = img.shape[:2]
            sc = min(800.0 / ow, 450.0 / oh)
            state["sx"] = sc
            disp = cv2.resize(img, (int(ow * sc), int(oh * sc)))
            dh, dw = disp.shape[:2]
            cv2.imwrite(temp_disp, disp)
            canvas.configure(width=dw, height=dh)
            photo = tk.PhotoImage(file=temp_disp)
            canvas.delete("all")
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.image = photo
            state["rect_id"] = None
            reg = (self.diamond_config or {}).get("region") or {}
            if reg.get("w") and reg.get("h"):
                canvas.create_rectangle(reg["x"] * sc, reg["y"] * sc,
                                        (reg["x"] + reg["w"]) * sc, (reg["y"] + reg["h"]) * sc,
                                        outline=ACCENT_GREEN, width=2)

        def capture():
            dev = dev_var.get()
            status.configure(text="⏳ กำลังจับภาพ...", fg=ACCENT_ORANGE)
            dialog.update()
            ok, data = self.controller.capture_screenshot_bytes(dev)
            if not ok:
                status.configure(text=f"❌ จับภาพล้มเหลว: {data}", fg=ACCENT_RED)
                return
            state["bytes"] = data
            state["orig"] = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if state["orig"] is None:
                status.configure(text="❌ ถอดรหัสภาพไม่สำเร็จ", fg=ACCENT_RED)
                return
            render()
            status.configure(text=f"📸 จับภาพสำเร็จ ({state['orig'].shape[1]}x{state['orig'].shape[0]}) — ลากครอบเฉพาะตัวเลข", fg=ACCENT_GREEN)

        press = {"x": 0, "y": 0}

        def on_press(e):
            press["x"], press["y"] = e.x, e.y
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
                state["rect_id"] = None

        def on_motion(e):
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
            state["rect_id"] = canvas.create_rectangle(press["x"], press["y"], e.x, e.y, outline=ACCENT_ORANGE, width=2)

        def on_release(e):
            if state["orig"] is None:
                status.configure(text="กรุณาจับภาพก่อน", fg=ACCENT_RED)
                return
            sx = state["sx"] or 1.0
            x1, y1 = min(press["x"], e.x), min(press["y"], e.y)
            x2, y2 = max(press["x"], e.x), max(press["y"], e.y)
            rx, ry = int(x1 / sx), int(y1 / sx)
            rw, rh = int((x2 - x1) / sx), int((y2 - y1) / sx)
            if rw < 3 or rh < 3:
                status.configure(text="กรอบเล็กเกินไป ลองลากใหม่", fg=ACCENT_RED)
                return
            self.diamond_config["region"] = {"x": rx, "y": ry, "w": rw, "h": rh}
            status.configure(text=f"✅ ตั้งพื้นที่: x={rx} y={ry} w={rw} h={rh}\nกด 'ทดสอบอ่านเลข' เพื่อตรวจ", fg=ACCENT_GREEN)
            render()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_motion)
        canvas.bind("<ButtonRelease-1>", on_release)

        def test_read():
            if state["bytes"] is None:
                status.configure(text="กรุณาจับภาพก่อน", fg=ACCENT_RED)
                return
            reg = (self.diamond_config or {}).get("region") or {}
            if int(reg.get("w", 0)) <= 0 or int(reg.get("h", 0)) <= 0:
                status.configure(text="ยังไม่ได้ลากกรอบพื้นที่ตัวเลข", fg=ACCENT_RED)
                return
            # เซฟภาพพื้นที่ที่ครอปให้เปิดดูได้ว่าครอบโดนเฉพาะตัวเลขไหม
            preview_msg = ""
            try:
                img = state["orig"]
                sh, sw = img.shape[:2]
                rx, ry = max(0, int(reg["x"])), max(0, int(reg["y"]))
                rw, rh = int(reg["w"]), int(reg["h"])
                crop = img[ry:min(sh, ry + rh), rx:min(sw, rx + rw)]
                if crop.size:
                    pp = os.path.join(self.templates_dir, "diamond_region_preview.png")
                    cv2.imwrite(pp, crop)
                    preview_msg = f"\n📂 ภาพพื้นที่: {pp}"
            except Exception:
                pass
            ok, number, raw = self.controller.read_number_tesseract(state["bytes"], reg)
            if ok:
                status.configure(text=f"🔍 อ่านได้: {number}{preview_msg}", fg=ACCENT_GREEN)
            elif raw in ("no_tesseract", "no_pytesseract"):
                status.configure(text="❌ ไม่พบ Tesseract OCR — ต้องติดตั้งก่อน (winget install UB-Mannheim.TesseractOCR)", fg=ACCENT_RED)
            else:
                status.configure(text=f"🔍 อ่านไม่ได้ — ลองครอบให้เฉพาะตัวเลข ไม่เอาไอคอน/ขอบเข้ามา{preview_msg}", fg=ACCENT_RED)

        def save_and_close():
            self.diamond_config["web_base_url"] = web_url_entry.get().strip()
            self.save_diamond_config()
            self.write_log("💾 บันทึกการตั้งค่าระบบอ่านเพชรแล้ว", "success")
            on_close()

        btns = tk.Frame(right, bg=BG_DARK)
        btns.pack(fill="x", pady=(14, 0))
        ModernButton(btns, text="📸 จับภาพหน้าจอ", command=capture, variant="primary").pack(fill="x", pady=3)
        ModernButton(btns, text="🔍 ทดสอบอ่านเลข", command=test_read, variant="accent").pack(fill="x", pady=3)
        ModernButton(btns, text="💾 บันทึกการตั้งค่า", command=save_and_close, variant="primary").pack(fill="x", pady=3)

        dialog.after(200, capture)  # จับภาพอัตโนมัติครั้งแรก

    def open_visual_recorder(self):
        if self.macro_running:
            messagebox.showwarning("คำเตือน", "ไม่สามารถเปิดระบบบันทึกพิกัดด้วยภาพได้ขณะที่บอทมาโครกำลังทำงานอยู่!", parent=self)
            return

        selected_devices = self.get_selected_devices()
        if not selected_devices:
            selected_devices = self.controller.get_connected_devices()
            
        if not selected_devices:
            messagebox.showerror("ไม่พบอุปกรณ์", "ไม่พบ Emulator ที่เชื่อมต่ออยู่! กรุณาเปิดและเชื่อมต่อ Emulator ก่อนใช้งานระบบนี้", parent=self)
            return
            
        import cv2
        import numpy as np
        
        dialog = tk.Toplevel(self)
        dialog.title("🎯 Visual Coordinate Recorder & Tap Simulator")
        dialog.configure(bg=BG_DARK)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        canvas = None
        orig_w, orig_h = 960, 540
        scale = 1.0
        disp_w, disp_h = 800, 450
        temp_screenshot = os.path.join(self.templates_dir, "visual_recorder_temp.png")
        temp_disp_path = os.path.join(self.templates_dir, "visual_recorder_disp.png")
        dots_drawn = []
        
        def on_close():
            try:
                if os.path.exists(temp_screenshot):
                    os.remove(temp_screenshot)
                if os.path.exists(temp_disp_path):
                    os.remove(temp_disp_path)
            except Exception:
                pass
            dialog.grab_release()
            dialog.destroy()
            
        dialog.protocol("WM_DELETE_WINDOW", on_close)
        
        canvas_frame = tk.Frame(dialog, bg=BG_DARK)
        canvas_frame.pack(side="left", padx=15, pady=15)
        
        canvas = tk.Canvas(canvas_frame, width=800, height=450, bg="#000000", highlightthickness=1, highlightbackground=BG_PANEL)
        canvas.pack()
        
        right_panel = tk.Frame(dialog, bg=BG_DARK, padx=15, pady=15)
        right_panel.pack(side="right", fill="both", expand=True)
        
        tk.Label(right_panel, text="📱 เลือก Emulator เป้าหมาย:", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        dev_var = tk.StringVar(value=selected_devices[0])
        dev_combo = ttk.Combobox(right_panel, textvariable=dev_var, values=selected_devices, state="readonly", font=("Segoe UI", 10))
        dev_combo.pack(fill="x", pady=(0, 15))
        
        tk.Label(right_panel, text="⚙️ ตั้งค่าคำสั่งคลิก (Tap):", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        delay_frame = tk.Frame(right_panel, bg=BG_DARK)
        delay_frame.pack(fill="x", pady=2)
        tk.Label(delay_frame, text="หน่วงเวลาหลังกด (วิ):", bg=BG_DARK, fg=FG_WHITE).pack(side="left")
        delay_entry = ModernEntry(delay_frame, width=8)
        delay_entry.pack(side="right")
        delay_entry.insert(0, str(DEFAULT_ACTION_DELAY))

        swipe_duration_frame = tk.Frame(right_panel, bg=BG_DARK)
        swipe_duration_frame.pack(fill="x", pady=2)
        tk.Label(swipe_duration_frame, text="ระยะเวลาลาก (ms):", bg=BG_DARK, fg=FG_WHITE).pack(side="left")
        swipe_duration_entry = ModernEntry(swipe_duration_frame, width=8)
        swipe_duration_entry.pack(side="right")
        swipe_duration_entry.insert(0, str(DEFAULT_SWIPE_DURATION))
        
        desc_frame = tk.Frame(right_panel, bg=BG_DARK)
        desc_frame.pack(fill="x", pady=5)
        tk.Label(desc_frame, text="คำอธิบายนำหน้า:", bg=BG_DARK, fg=FG_WHITE).pack(side="left")
        desc_entry = ModernEntry(desc_frame, width=15)
        desc_entry.pack(side="right")
        desc_entry.insert(0, "จิ้มเนื้อเรื่อง")
        
        send_tap_var = tk.BooleanVar(value=True)
        send_tap_chk = tk.Checkbutton(right_panel, text="👉 ส่งคลิกเข้า Emulator จริงด้วย", variable=send_tap_var, bg=BG_DARK, fg=FG_WHITE, selectcolor=BG_DARK, activebackground=BG_DARK, activeforeground=FG_WHITE, relief="flat", font=("Segoe UI", 9))
        send_tap_chk.pack(anchor="w", pady=(10, 2))
        
        auto_refresh_var = tk.BooleanVar(value=True)
        auto_refresh_chk = tk.Checkbutton(right_panel, text="🔄 อัปเดตภาพจออัตโนมัติหลังกด", variable=auto_refresh_var, bg=BG_DARK, fg=FG_WHITE, selectcolor=BG_DARK, activebackground=BG_DARK, activeforeground=FG_WHITE, relief="flat", font=("Segoe UI", 9))
        auto_refresh_chk.pack(anchor="w", pady=2)
        
        status_lbl = tk.Label(right_panel, text="กำลังโหลดหน้าจอเครื่องเป้าหมาย...", bg=BG_DARK, fg=ACCENT_ORANGE, font=("Segoe UI", 9, "italic"), wraplength=220, justify="left")
        status_lbl.pack(fill="x", pady=15)
        
        def refresh_screen():
            nonlocal scale, disp_w, disp_h, orig_w, orig_h
            device = dev_var.get()
            status_lbl.configure(text="⏳ กำลังจับภาพหน้าจอ...", fg=ACCENT_ORANGE)
            dialog.update()
            
            if not os.path.exists(self.templates_dir):
                os.makedirs(self.templates_dir, exist_ok=True)
                
            success, err = self.controller.take_screenshot(device, temp_screenshot)
            if not success:
                status_lbl.configure(text=f"❌ แคปจอล้มเหลว: {err}", fg=ACCENT_RED)
                return
                
            img = cv2.imread(temp_screenshot)
            if img is None:
                status_lbl.configure(text="❌ ไม่สามารถเปิดไฟล์รูปภาพได้", fg=ACCENT_RED)
                return
                
            orig_h, orig_w = img.shape[:2]
            scale = min(800.0 / orig_w, 450.0 / orig_h)
            disp_w = int(orig_w * scale)
            disp_h = int(orig_h * scale)
            
            resized = cv2.resize(img, (disp_w, disp_h))
            cv2.imwrite(temp_disp_path, resized)
            
            canvas.configure(width=disp_w, height=disp_h)
            photo = tk.PhotoImage(file=temp_disp_path)
            canvas.delete("all")
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.image = photo
            
            dots_drawn.clear()
            status_lbl.configure(text=f"📸 อัปเดตหน้าจอสำเร็จ ({orig_w}x{orig_h})", fg=ACCENT_GREEN)
            
        press_x, press_y = 0, 0
        
        def on_press(event):
            nonlocal press_x, press_y
            press_x = event.x
            press_y = event.y
            
        def on_release(event):
            nonlocal scale
            device = dev_var.get()
            release_x = event.x
            release_y = event.y
            
            import math
            dist = math.sqrt((release_x - press_x)**2 + (release_y - press_y)**2)
            
            real_start_x = int(press_x / scale)
            real_start_y = int(press_y / scale)
            real_end_x = int(release_x / scale)
            real_end_y = int(release_y / scale)
            
            delay_val = DEFAULT_ACTION_DELAY
            try:
                delay_val = float(delay_entry.get().strip() or str(DEFAULT_ACTION_DELAY))
            except ValueError:
                pass
            swipe_duration = DEFAULT_SWIPE_DURATION
            try:
                swipe_duration = int(float(swipe_duration_entry.get().strip() or str(DEFAULT_SWIPE_DURATION)))
            except ValueError:
                pass
                
            prefix = desc_entry.get().strip() or "จิ้มพิกัด"
            
            if dist < 10:
                # ทำการ Tap (คลิกพิกัดเดียว)
                desc = f"{prefix} ({real_start_x}, {real_start_y})"
                step = {
                    "type": "tap",
                    "desc": desc,
                    "x": str(real_start_x),
                    "y": str(real_start_y),
                    "delay": delay_val
                }
                self.macro_steps.append(step)
                self.refresh_listbox()
                
                step_num = len(dots_drawn) + 1
                dot = canvas.create_oval(press_x - 6, press_y - 6, press_x + 6, press_y + 6, fill="#E74C3C", outline="#FFFFFF", width=1.5)
                text = canvas.create_text(press_x, press_y, text=str(step_num), fill="#FFFFFF", font=("Segoe UI", 7, "bold"))
                dots_drawn.append((dot, text, step))
                
                status_lbl.configure(text=f"🎯 บันทึก Tap: ({real_start_x}, {real_start_y}) | ขั้นที่ {step_num}", fg=ACCENT_GREEN)
                
                if send_tap_var.get():
                    def tap_worker():
                        self.controller.tap(device, real_start_x, real_start_y)
                        time.sleep(delay_val)
                        if auto_refresh_var.get():
                            self.after(0, lambda: refresh_screen())
                    threading.Thread(target=tap_worker, daemon=True).start()
            else:
                # ทำการ Swipe (ลากเลื่อนหน้าจอ)
                desc = f"ลากจอ ({real_start_x},{real_start_y} -> {real_end_x},{real_end_y})"
                step = {
                    "type": "swipe",
                    "desc": desc,
                    "x": str(real_start_x),
                    "y": str(real_start_y),
                    "x2": str(real_end_x),
                    "y2": str(real_end_y),
                    "duration": swipe_duration,
                    "delay": delay_val
                }
                self.macro_steps.append(step)
                self.refresh_listbox()
                
                step_num = len(dots_drawn) + 1
                dot = canvas.create_oval(press_x - 4, press_y - 4, press_x + 4, press_y + 4, fill="#2ECC71", outline="#FFFFFF", width=1)
                arrow = canvas.create_line(press_x, press_y, release_x, release_y, arrow=tk.LAST, fill="#2ECC71", width=3)
                text = canvas.create_text(press_x - 10, press_y - 10, text=str(step_num), fill="#2ECC71", font=("Segoe UI", 9, "bold"))
                dots_drawn.append(((dot, arrow), text, step))
                
                status_lbl.configure(text=f"↕️ บันทึก Swipe: {real_start_x},{real_start_y}->{real_end_x},{real_end_y} | ขั้นที่ {step_num}", fg=ACCENT_GREEN)
                
                if send_tap_var.get():
                    def swipe_worker():
                        self.controller.swipe(device, real_start_x, real_start_y, real_end_x, real_end_y, swipe_duration)
                        time.sleep(delay_val)
                        if auto_refresh_var.get():
                            self.after(0, lambda: refresh_screen())
                    threading.Thread(target=swipe_worker, daemon=True).start()
                    
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<ButtonRelease-1>", on_release)
        dev_combo.bind("<<ComboboxSelected>>", lambda e: refresh_screen())
        
        def undo_step():
            if not dots_drawn:
                status_lbl.configure(text="⚠️ ไม่มีขั้นตอนให้ย้อนกลับ", fg=ACCENT_ORANGE)
                return
            draw_objs, text, step = dots_drawn.pop()
            if isinstance(draw_objs, (tuple, list)):
                for obj in draw_objs:
                    canvas.delete(obj)
            else:
                canvas.delete(draw_objs)
            canvas.delete(text)
            if self.macro_steps and self.macro_steps[-1] == step:
                self.macro_steps.pop()
                self.refresh_listbox()
            status_lbl.configure(text="↩️ ยกเลิกขั้นตอนล่าสุดสำเร็จ", fg=ACCENT_ORANGE)
            
        ModernButton(right_panel, text="📸 ถ่ายรูปใหม่ (Refresh)", command=refresh_screen, bg=ACCENT_BLUE, activebg=ACCENT_HOVER).pack(fill="x", pady=5)
        ModernButton(right_panel, text="↩️ ย้อนกลับขั้นตอนล่าสุด (Undo)", command=undo_step, bg=ACCENT_ORANGE, activebg="#d35400").pack(fill="x", pady=5)
        ModernButton(right_panel, text="❌ ปิดหน้าต่างการบันทึก", command=on_close, bg=BG_INPUT, activebg="#444444").pack(fill="x", pady=(15, 0))
        
        self.after(100, refresh_screen)

    # --- บัญชีผู้ใช้ (Accounts Manager Database) ---
    def load_accounts(self):
        """โหลดข้อมูลบัญชีผู้ใช้จากไฟล์ accounts.json"""
        self.accounts.clear()
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, "r", encoding="utf-8") as f:
                    self.accounts = json.load(f)
            except Exception as e:
                self.write_log(f"โหลดข้อมูลบัญชีขัดข้อง: {e}", "error")

    def save_accounts(self):
        """บันทึกข้อมูลบัญชีลงไฟล์ accounts.json"""
        try:
            # อัปเดตสถานะติ๊กเลือกล่าสุดก่อนเซฟ
            for acc in self.accounts:
                email = acc.get("email")
                if email in self.account_checkboxes:
                    acc["checked"] = self.account_checkboxes[email].get()
            with open(self.accounts_file, "w", encoding="utf-8") as f:
                json.dump(self.accounts, f, indent=2)
        except Exception as e:
            self.write_log(f"บันทึกข้อมูลบัญชีล้มเหลว: {e}", "error")

    def select_accounts_by_status(self, kind):
        """ติ๊กเลือกบัญชีตามสถานะรอบก่อน — failed=ที่พลาด, pending=ที่ยังไม่เสร็จ (ยังไม่ทำ+พลาด+หยุด)
        ใช้รันซ้ำเฉพาะที่ตก โดยไม่ต้องไล่ติ๊กเอง"""
        fail = {"device_error", "macro_error", "error"}
        n = 0
        for a in self.accounts:
            st = (a.get("last_status") or "").lower()
            want = (st in fail) if kind == "failed" else (st != "completed")
            a["checked"] = want
            if want:
                n += 1
        self.save_accounts()
        self.refresh_accounts_ui()
        self.write_log(f"เลือกบัญชี{'ที่พลาด' if kind == 'failed' else 'ที่ยังไม่เสร็จ'} {n} รหัส", "info")

    def refresh_accounts_ui(self):
        """วาดการ์ดลิสต์รายชื่อไอดีแบบจัดกลุ่มบนแท็บจัดการบัญชีใหม่"""
        for widget in self.acc_scroll_frame.winfo_children():
            widget.destroy()

        self.account_checkboxes.clear()
        self.group_checkboxes.clear()
        # สแนปช็อตอีเมลที่ 'กำลังทำอยู่ตอนนี้' (จอไหนถืออยู่) ให้จุดสถานะ 🔵 ถูกต้อง ณ ตอนวาด
        self._active_account_emails = {
            (a.get("email") or "").strip().lower()
            for a in getattr(self, "device_active_accounts", {}).values() if a
        }
        
        if not self.accounts:
            lbl = tk.Label(self.acc_scroll_frame, text="ไม่มีบัญชีในคิวระบบ\nกรุณาเพิ่มบัญชีเกมด้านขวามือ", bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="center")
            lbl.pack(pady=30, fill="x")
            self.update_status_summary()
            return

        # 0. ค้นหา/กรองบัญชีตามช่องค้นหา
        search_query = self.acc_search_entry.get().strip().lower() if hasattr(self, "acc_search_entry") else ""

        # 1. จัดกลุ่มบัญชี
        grouped_accounts = {}
        for acc in self.accounts:
            email_lower = acc.get("email", "").lower()
            name_lower = account_display_name(acc).lower()
            group_lower = acc.get("group", "").lower()

            # ถ้ามีคำค้นหา ให้เช็คว่าคำค้นหาตรงกับ email, name(=ชื่อที่แสดง) หรือ group หรือไม่
            if search_query and (search_query not in email_lower and search_query not in name_lower and search_query not in group_lower):
                continue
                
            grp = acc.get("group", "ทั่วไป").strip()
            if not grp:
                grp = "ทั่วไป"
            if grp not in grouped_accounts:
                grouped_accounts[grp] = []
            grouped_accounts[grp].append(acc)

        if not grouped_accounts and search_query:
            lbl = tk.Label(self.acc_scroll_frame, text="ไม่พบข้อมูลบัญชีที่ค้นหา", bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="center")
            lbl.pack(pady=30, fill="x")
            self.update_status_summary()
            return

        # 2. วาดแต่ละกลุ่ม
        for grp, acc_list in grouped_accounts.items():
            # สร้างกล่องจัดกลุ่ม
            group_box = tk.Frame(self.acc_scroll_frame, bg=BG_CARD, bd=0)
            group_box.pack(fill="x", pady=(10, 5), padx=2)

            # หัวข้อกลุ่ม
            group_header = tk.Frame(group_box, bg=BG_PANEL, highlightthickness=1, highlightbackground=LINE_SOFT)
            group_header.pack(fill="x")

            # เช็คว่าทั้งหมดในกลุ่มถูกเลือกหรือไม่
            all_checked = all(a.get("checked", True) for a in acc_list)
            group_var = tk.BooleanVar(value=all_checked)
            self.group_checkboxes[grp] = group_var

            # ฟังก์ชันเมื่อคลิกหัวข้อกลุ่ม
            def on_group_click(g=grp, v=group_var, accs=acc_list):
                new_state = v.get()
                for a in accs:
                    email = a.get("email")
                    a["checked"] = new_state
                    if email in self.account_checkboxes:
                        self.account_checkboxes[email].set(new_state)
                self.save_accounts()
                self.update_status_summary()

            # ปุ่มลบกลุ่ม
            def delete_group_func(g=grp, accs=acc_list):
                confirm = messagebox.askyesno(
                    "ยืนยันการลบกลุ่ม",
                    f"คุณแน่ใจหรือไม่ที่จะลบบัญชีทั้งหมดในกลุ่ม '{g}' (จำนวน {len(accs)} บัญชี)?"
                )
                if confirm:
                    emails_to_delete = [a.get("email") for a in accs]
                    self.accounts = [a for a in self.accounts if a.get("email") not in emails_to_delete]
                    self.save_accounts()
                    self.refresh_accounts_ui()
                    self.write_log(f"ลบกลุ่มบัญชี '{g}' เรียบร้อยแล้ว", "warning")
            
            del_grp_btn = tk.Button(
                group_header,
                text="🗑️ ลบกลุ่ม",
                command=delete_group_func,
                bg=ACCENT_RED,
                fg=FG_WHITE,
                activebackground="#991B1B",
                activeforeground=FG_WHITE,
                relief="flat",
                bd=0,
                font=("Segoe UI", 9),
                padx=5,
                pady=2
            )
            del_grp_btn.pack(side="right", padx=5, pady=5)

            chk_grp = tk.Checkbutton(
                group_header, 
                text=f"📂 กลุ่ม: {grp} ({len(acc_list)} บัญชี)", 
                variable=group_var,
                command=on_group_click,
                bg=BG_PANEL,
                fg=FG_WHITE,
                activebackground=BG_PANEL,
                activeforeground=FG_WHITE,
                selectcolor=BG_DARK,
                relief="flat",
                font=("Segoe UI", 10, "bold")
            )
            chk_grp.pack(side="left", padx=5, pady=5)

            # บัญชีลูกภายใต้กลุ่มนี้
            for acc in acc_list:
                email = acc.get("email")
                checked = acc.get("checked", True)

                frame = tk.Frame(group_box, bg=BG_SURFACE, highlightthickness=1, highlightbackground=LINE_SOFT)
                frame.pack(fill="x", pady=2, padx=(15, 2))

                var = tk.BooleanVar(value=checked)
                self.account_checkboxes[email] = var

                def on_single_click(e=email, v=var, g=grp):
                    state = v.get()
                    for a in self.accounts:
                        if a.get("email") == e:
                            a["checked"] = state
                            break
                    self.save_accounts()

                    # ปรับเช็คบ็อกซ์กลุ่ม
                    grp_accs = [a for a in self.accounts if a.get("group", "ทั่วไป").strip() == g]
                    all_grp_checked = all(a.get("checked", True) for a in grp_accs)
                    if g in self.group_checkboxes:
                        self.group_checkboxes[g].set(all_grp_checked)
                    self.update_status_summary()

                # ปุ่มลบบัญชี
                del_btn = tk.Button(
                    frame,
                    text="X",
                    command=lambda e=email: self.delete_account(e),
                    bg=ACCENT_RED,
                    fg=FG_WHITE,
                    activebackground="#991B1B",
                    activeforeground=FG_WHITE,
                    relief="flat",
                    bd=0,
                    font=("Segoe UI", 8, "bold"),
                    width=2
                )
                del_btn.pack(side="right", padx=5, pady=5)

                # ปุ่มแก้ไขบัญชี
                edit_btn = tk.Button(
                    frame,
                    text="📝",
                    command=lambda acc=acc: self.start_edit_account(acc),
                    bg="#0F2F4A",
                    fg=FG_WHITE,
                    activebackground="#164E72",
                    activeforeground=FG_WHITE,
                    relief="flat",
                    bd=0,
                    font=("Segoe UI", 8),
                    width=2
                )
                edit_btn.pack(side="right", padx=2, pady=5)

                chk = tk.Checkbutton(
                    frame,
                    text="",
                    variable=var,
                    command=on_single_click,
                    bg=BG_SURFACE,
                    fg=FG_WHITE,
                    activebackground=BG_SURFACE,
                    activeforeground=FG_WHITE,
                    selectcolor=BG_INPUT,
                    relief="flat",
                    font=("Segoe UI", 9)
                )
                chk.pack(side="left", padx=5, pady=5)

                # จุดสถานะ: 🔵กำลังทำ (จอไหนกำลังรันบัญชีนี้อยู่ตอนนี้) ชนะสถานะเก่าเสมอ
                # ไม่งั้นดูรอบล่าสุด: 🟢เสร็จ 🔴พลาด ⚪ยังไม่ทำ (รวม 'หยุดกลางคัน' เข้าไว้ในนี้ด้วย)
                if self.macro_running and email and email.strip().lower() in getattr(self, "_active_account_emails", set()):
                    _dot = "🔵"
                else:
                    _st = (acc.get("last_status") or "").lower()
                    _dot = ("🟢" if _st == "completed" else
                            "🔴" if _st in ("device_error", "macro_error", "error") else "⚪")
                tk.Label(frame, text=_dot, bg=BG_SURFACE, font=("Segoe UI", 9)).pack(side="left", padx=(0, 2), pady=5)

                summary_lbl = tk.Label(
                    frame,
                    text=build_account_summary(acc),
                    bg=BG_SURFACE,
                    fg=FG_WHITE,
                    font=("Consolas", 9),
                    anchor="w",
                )
                summary_lbl.pack(side="left", fill="x", expand=True, padx=8)

        self.update_status_summary()

    def add_account(self):
        email = self.new_acc_email.get().strip()
        name = self.new_acc_name.get().strip()
        pwd = self.new_acc_pass.get().strip()
        group = self.new_acc_group.get().strip() or "ทั่วไป"
        token = self.new_acc_token.get().strip()
        client_id = self.new_acc_client_id.get().strip()
        
        if not email or not pwd:
            messagebox.showwarning("คำเตือน", "กรุณากรอกอีเมลและรหัสผ่านให้ครบถ้วน!")
            return
            
        if self.editing_email:
            # โหมดแก้ไขบัญชี
            if email != self.editing_email and any(acc.get("email") == email for acc in self.accounts):
                messagebox.showwarning("คำเตือน", "บัญชีอีเมลใหม่นี้มีอยู่แล้วในคิว!")
                return
                
            # อัปเดตข้อมูลในลิสต์
            for acc in self.accounts:
                if acc.get("email") == self.editing_email:
                    acc["email"] = email
                    acc["name"] = name
                    acc["password"] = pwd
                    acc["group"] = group
                    acc["refresh_token"] = token
                    acc["client_id"] = client_id
                    break
            
            self.editing_email = None
            primary_colors = get_button_colors("primary")
            self.save_acc_btn.configure(
                text="เพิ่มบัญชีเข้าคิว",
                bg=primary_colors["bg"],
                activebackground=primary_colors["hover"],
            )
            self.save_acc_btn._normal_bg = primary_colors["bg"]
            self.save_acc_btn._hover_bg = primary_colors["hover"]
            if hasattr(self, 'cancel_edit_btn'):
                self.cancel_edit_btn.grid_remove()
                
            self.batch_import_btn.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
            self.save_web_game_import_btn.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))
            self.write_log(f"แก้ไขบัญชี {email} สำเร็จ", "success")
        else:
            # โหมดเพิ่มบัญชีใหม่
            if any(acc.get("email") == email for acc in self.accounts):
                messagebox.showwarning("คำเตือน", "บัญชีอีเมลนี้มีอยู่แล้วในคิว!")
                return
                
            self.accounts.append({
                "email": email, 
                "name": name,
                "password": pwd, 
                "refresh_token": token,
                "client_id": client_id,
                "checked": True, 
                "group": group
            })
            self.write_log(f"เพิ่มบัญชี {email} ลงในกลุ่ม {group} สำเร็จ", "success")
            
        self.save_accounts()
        self.refresh_accounts_ui()
        
        # ล้างค่าในฟอร์ม
        self.new_acc_email.delete(0, tk.END)
        self.new_acc_name.delete(0, tk.END)
        self.new_acc_pass.delete(0, tk.END)
        self.new_acc_group.delete(0, tk.END)
        self.new_acc_group.insert(0, "ทั่วไป")
        self.new_acc_token.delete(0, tk.END)
        self.new_acc_client_id.delete(0, tk.END)

    def start_edit_account(self, acc):
        # เติมค่าใส่ฟอร์ม
        self.new_acc_email.delete(0, tk.END)
        self.new_acc_email.insert(0, acc.get("email", ""))
        
        self.new_acc_name.delete(0, tk.END)
        self.new_acc_name.insert(0, acc.get("name", ""))
        
        self.new_acc_pass.delete(0, tk.END)
        self.new_acc_pass.insert(0, acc.get("password", ""))
        
        self.new_acc_group.delete(0, tk.END)
        self.new_acc_group.insert(0, acc.get("group", "ทั่วไป"))
        
        self.new_acc_token.delete(0, tk.END)
        self.new_acc_token.insert(0, acc.get("refresh_token", ""))
        
        self.new_acc_client_id.delete(0, tk.END)
        self.new_acc_client_id.insert(0, acc.get("client_id", ""))
        
        self.editing_email = acc.get("email")
        
        # เปลี่ยนปุ่มหลักเป็นบันทึกการแก้ไข
        warning_colors = get_button_colors("warning")
        self.save_acc_btn.configure(
            text="บันทึกการแก้ไข",
            bg=warning_colors["bg"],
            activebackground=warning_colors["hover"],
        )
        self.save_acc_btn._normal_bg = warning_colors["bg"]
        self.save_acc_btn._hover_bg = warning_colors["hover"]
        
        # แสดงปุ่มยกเลิกการแก้ไข
        if not hasattr(self, 'cancel_edit_btn'):
            self.cancel_edit_btn = ModernButton(
                self.save_acc_btn.master, 
                text="ยกเลิกการแก้ไข", 
                command=self.cancel_edit_account, 
                variant="danger"
            )
        self.cancel_edit_btn.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        
        # เลื่อนปุ่มนำเข้าแบบกลุ่มลงไปแถว 8
        self.batch_import_btn.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.save_web_game_import_btn.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def cancel_edit_account(self):
        self.editing_email = None
        primary_colors = get_button_colors("primary")
        self.save_acc_btn.configure(
            text="เพิ่มบัญชีเข้าคิว",
            bg=primary_colors["bg"],
            activebackground=primary_colors["hover"],
        )
        self.save_acc_btn._normal_bg = primary_colors["bg"]
        self.save_acc_btn._hover_bg = primary_colors["hover"]
        if hasattr(self, 'cancel_edit_btn'):
            self.cancel_edit_btn.grid_remove()
            
        # เลื่อนปุ่มนำเข้าแบบกลุ่มกลับมาแถว 7
        self.batch_import_btn.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.save_web_game_import_btn.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        
        # ล้างค่าในฟอร์ม
        self.new_acc_email.delete(0, tk.END)
        self.new_acc_name.delete(0, tk.END)
        self.new_acc_pass.delete(0, tk.END)
        self.new_acc_group.delete(0, tk.END)
        self.new_acc_group.insert(0, "ทั่วไป")
        self.new_acc_token.delete(0, tk.END)
        self.new_acc_client_id.delete(0, tk.END)

    def import_save_web_game_file(self):
        file_path = filedialog.askopenfilename(
            title="Import Save Web Game JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not file_path:
            return

        try:
            stats = import_save_web_game_accounts(file_path, self.accounts_file)
            self.load_accounts()
            self.refresh_accounts_ui()
            self.write_log(
                (
                    "Save Web Game import: "
                    f"{stats.get('imported', 0)} imported, "
                    f"{stats.get('updated', 0)} updated, "
                    f"{stats.get('skipped', 0)} skipped"
                ),
                "success",
            )
            messagebox.showinfo(
                "Save Web Game Import",
                (
                    f"Imported: {stats.get('imported', 0)}\n"
                    f"Updated: {stats.get('updated', 0)}\n"
                    f"Skipped: {stats.get('skipped', 0)}"
                ),
            )
        except Exception as exc:
            self.write_log(f"Save Web Game import failed: {exc}", "error")
            messagebox.showerror("Save Web Game Import", str(exc))

    def open_batch_import_dialog(self):
        """เปิดหน้าต่างป๊อปอัปสำหรับป้อนบัญชีแบบกลุ่มและทำการจัดเรียงพาร์สข้อมูล"""
        dialog = tk.Toplevel(self)
        dialog.transient(self)
        dialog.grab_set()
        dialog.title("📥 นำเข้าบัญชีแบบกลุ่ม (Batch Import)")
        dialog.geometry("600x550")
        dialog.configure(bg=BG_DARK)
        
        # กึ่งกลางหน้าจอหลัก
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.winfo_x() + (self.winfo_width() // 2) - (width // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")

        lbl_title = tk.Label(
            dialog, 
            text="📥 นำเข้าบัญชีแบบกลุ่ม (Batch Import)", 
            bg=BG_DARK, 
            fg=FG_WHITE, 
            font=("Segoe UI", 12, "bold")
        )
        lbl_title.pack(pady=(15, 5))
        
        lbl_desc = tk.Label(
            dialog,
            text="วางข้อมูลแยกแต่ละบรรทัด คั่นด้วยเครื่องหมาย | , ; หรือ TAB\nรูปแบบ: อีเมล|รหัสผ่าน (ข้อมูลส่วนอื่นนอกจาก 2 ช่องแรกจะถูกข้ามอัตโนมัติ)",
            bg=BG_DARK,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
            justify="center"
        )
        lbl_desc.pack(pady=(0, 10))

        # พื้นที่พิมพ์ข้อความ
        text_frame = tk.Frame(dialog, bg=BG_DARK)
        text_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        text_scroll = ttk.Scrollbar(text_frame)
        text_scroll.pack(side="right", fill="y")
        
        text_area = tk.Text(
            text_frame, 
            bg=BG_INPUT, 
            fg=FG_WHITE, 
            insertbackground=FG_WHITE, 
            relief="flat", 
            bd=1, 
            font=("Consolas", 10),
            yscrollcommand=text_scroll.set
        )
        text_area.pack(side="left", fill="both", expand=True)
        text_scroll.config(command=text_area.yview)

        # ตั้งค่ากลุ่มบัญชีปลายทาง
        group_frame = tk.Frame(dialog, bg=BG_DARK)
        group_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(group_frame, text="กลุ่มบัญชีปลายทาง (Group Name):", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 10)).pack(side="left", padx=(0, 10))
        
        group_entry = ModernEntry(group_frame, width=25)
        group_entry.pack(side="left")
        group_entry.insert(0, "ทั่วไป")

        # ปุ่มตกลง/ยกเลิก
        btn_frame = tk.Frame(dialog, bg=BG_DARK)
        btn_frame.pack(fill="x", padx=20, pady=(5, 20))

        def do_import():
            raw_text = text_area.get("1.0", tk.END).strip()
            group_name = group_entry.get().strip() or "ทั่วไป"
            
            if not raw_text:
                messagebox.showwarning("คำเตือน", "กรุณาป้อนข้อมูลบัญชีก่อนกดยืนยัน!", parent=dialog)
                return
                
            lines = raw_text.splitlines()
            imported_count = 0
            duplicate_count = 0
            invalid_count = 0
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                parts = []
                for sep in ['|', ',', ';', '\t']:
                    if sep in line:
                        parts = [p.strip() for p in line.split(sep)]
                        break
                else:
                    parts = [p.strip() for p in line.split() if p.strip()]
                    
                if len(parts) < 2:
                    invalid_count += 1
                    continue
                    
                email = parts[0]
                pwd = parts[1]
                refresh_token = ""
                client_id = ""
                
                # พาร์สหาโทเคนและไคลเอนต์ไอดีในคอลัมน์อื่นๆ ถัดไป
                import re
                for p in parts[2:]:
                    # ค้นหา client_id (UUID)
                    if re.match(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', p):
                        client_id = p
                    # ค้นหา refresh_token
                    elif len(p) > 50:
                        refresh_token = p
                
                if not email or not pwd or "@" not in email:
                    invalid_count += 1
                    continue
                    
                if any(acc.get("email") == email for acc in self.accounts):
                    duplicate_count += 1
                    continue
                    
                self.accounts.append({
                    "email": email,
                    "name": "",
                    "password": pwd,
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "checked": True,
                    "group": group_name
                })
                imported_count += 1
                
            if imported_count > 0:
                self.save_accounts()
                self.refresh_accounts_ui()
                self.write_log(f"นำเข้าบัญชีแบบกลุ่มสำเร็จ: {imported_count} ไอดี (กลุ่ม: {group_name})", "success")
                messagebox.showinfo(
                    "นำเข้าสำเร็จ", 
                    f"นำเข้าบัญชีสำเร็จ: {imported_count} บัญชี\n"
                    f"ข้ามบัญชีซ้ำ: {duplicate_count} บัญชี\n"
                    f"รูปแบบไม่ถูกต้อง: {invalid_count} บัญชี",
                    parent=dialog
                )
                dialog.destroy()
            else:
                messagebox.showwarning(
                    "ผลการนำเข้า", 
                    f"ไม่มีบัญชีใหม่ถูกนำเข้า\n"
                    f"ข้ามบัญชีซ้ำ: {duplicate_count} บัญชี\n"
                    f"รูปแบบไม่ถูกต้อง: {invalid_count} บัญชี",
                    parent=dialog
                )

        btn_cancel = ModernButton(btn_frame, text="❌ ยกเลิก", command=dialog.destroy, bg=ACCENT_RED, activebg="#c0392b")
        btn_cancel.pack(side="right", padx=5)
        
        btn_import = ModernButton(btn_frame, text="📥 นำเข้าบัญชี", command=do_import, bg=ACCENT_GREEN, activebg="#2ecc71")
        btn_import.pack(side="right", padx=5)

    def delete_account(self, email):
        confirm = messagebox.askyesno("ลบบัญชี", f"คุณต้องการลบบัญชี {email} หรือไม่?")
        if confirm:
            self.accounts = [acc for acc in self.accounts if acc.get("email") != email]
            self.save_accounts()
            self.refresh_accounts_ui()
            self.write_log(f"ลบบัญชี {email} เรียบร้อยแล้ว", "warning")

    def delete_selected_accounts(self):
        # นับบัญชีที่ถูกติ๊กเลือก
        selected_emails = [acc.get("email") for acc in self.accounts if acc.get("checked", True)]
        if not selected_emails:
            messagebox.showwarning("คำเตือน", "กรุณาติ๊กเลือกบัญชีที่ต้องการลบก่อน!")
            return
            
        confirm = messagebox.askyesno(
            "ยืนยันการลบแบบกลุ่ม", 
            f"คุณแน่ใจหรือไม่ที่จะลบบัญชีที่เลือกทั้งหมดจำนวน {len(selected_emails)} บัญชี?"
        )
        if confirm:
            self.accounts = [acc for acc in self.accounts if acc.get("email") not in selected_emails]
            self.save_accounts()
            self.refresh_accounts_ui()
            self.write_log(f"ลบบัญชีแบบกลุ่มเสร็จสิ้น (ลบออก {len(selected_emails)} บัญชี)", "warning")

    def move_selected_accounts(self):
        target_group = self.batch_move_group_entry.get().strip()
        if not target_group:
            messagebox.showwarning("คำเตือน", "กรุณาระบุชื่อกลุ่มเป้าหมาย!")
            return
            
        selected_emails = [acc.get("email") for acc in self.accounts if acc.get("checked", True)]
        if not selected_emails:
            messagebox.showwarning("คำเตือน", "กรุณาติ๊กเลือกบัญชีที่ต้องการย้ายกลุ่มก่อน!")
            return
            
        for acc in self.accounts:
            if acc.get("email") in selected_emails:
                acc["group"] = target_group
                
        self.save_accounts()
        self.refresh_accounts_ui()
        self.write_log(f"ย้ายกลุ่มบัญชีจำนวน {len(selected_emails)} บัญชี ไปยังกลุ่ม '{target_group}' เรียบร้อยแล้ว", "success")

    # --- ระบบจัดการโปรไฟล์มาโครบอท ---
    def load_profiles(self):
        """ค้นหาและโหลดไฟล์โปรไฟล์ JSON ในโฟลเดอร์ macros/"""
        self.profiles.clear()
        search_pattern = os.path.join(self.macros_dir, "*.json")
        files = glob.glob(search_pattern)
        
        profile_names = []
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    name = data.get("name", os.path.basename(f).replace(".json", ""))
                    self.profiles[name] = f
                    profile_names.append(name)
            except Exception as e:
                self.write_log(f"พบปัญหาการอ่านไฟล์โปรไฟล์ {os.path.basename(f)}: {e}", "error")
                
        # อัปเดตรายชื่อในดร็อปดาวน์
        self.profile_cb["values"] = profile_names
        
        # เลือกโปรไฟล์ดีฟอลต์ (Default Login & Ads) เป็นหลักหากมี
        if "Default Login & Ads" in self.profiles:
            self.profile_cb.set("Default Login & Ads")
            self.on_profile_select()
        elif profile_names:
            self.profile_cb.set(profile_names[0])
            self.on_profile_select()

    def on_profile_select(self, event=None):
        name = self.profile_cb.get()
        filepath = self.profiles.get(name)
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    self.macro_steps = data.get("steps", [])
                    self.refresh_listbox()
                    self.profile_name_entry.delete(0, tk.END)
                    self.profile_name_entry.insert(0, name.lower().replace(" ", "_"))
                    self.write_log(f"โหลดโปรไฟล์มาโครเรียบร้อยแล้ว: {name} (จำนวนขั้นตอน: {len(self.macro_steps)} ขั้นตอน)", "success")
                    self.update_status_summary()
            except Exception as e:
                self.write_log(f"โหลดโปรไฟล์ผิดพลาด: {e}", "error")

    def load_script_sets(self):
        """ค้นหาและโหลดไฟล์ชุดคำสั่งย่อย (Script Sets) ในโฟลเดอร์ script_sets/"""
        self.script_sets.clear()
        search_pattern = os.path.join(self.script_sets_dir, "*.json")
        files = glob.glob(search_pattern)
        for f in files:
            try:
                data = load_script_set(f)
                name = data["name"]
                self.script_sets[name] = data["steps"]
            except Exception as e:
                self.write_log(f"พบปัญหาการอ่านไฟล์ชุดคำสั่งย่อย {os.path.basename(f)}: {e}", "error")

    def open_script_sets_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("🧩 จัดการชุดคำสั่งย่อย (Script Sets)")
        dialog.geometry("780x560")
        dialog.configure(bg=BG_DARK)
        dialog.transient(self)
        dialog.grab_set()

        # กึ่งกลางหน้าจอหลัก
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.winfo_x() + (self.winfo_width() // 2) - (width // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")

        # หัวข้อ
        tk.Label(
            dialog,
            text="🧩 จัดการชุดคำสั่งย่อย (Script Sets)",
            bg=BG_DARK,
            fg=FG_WHITE,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=20, pady=(15, 5))

        tk.Label(
            dialog,
            text="คุณสามารถบันทึกกลุ่มขั้นตอนมาโครเป็นเซ็ตย่อย (เหมือนเลโก้) แล้วนำมาประกอบกันในมาโครหลักได้",
            bg=BG_DARK,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=(0, 15))

        # เฟรมหลัก
        main_frame = tk.Frame(dialog, bg=BG_DARK)
        main_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        main_frame.columnconfigure(0, weight=1)  # แผงซ้าย (รายการเซ็ต)
        main_frame.columnconfigure(1, weight=1)  # แผงขวา (รายละเอียด / คำสั่งจัดการ)
        main_frame.rowconfigure(0, weight=1)

        # แผงซ้าย: รายชื่อเซ็ตที่มีอยู่
        left_box = tk.LabelFrame(
            main_frame,
            text=" รายชื่อชุดคำสั่งย่อยที่มีอยู่ ",
            bg=BG_DARK,
            fg=ACCENT_BLUE,
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10,
        )
        left_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        sets_list = tk.Listbox(
            left_box,
            bg=BG_PANEL,
            fg=FG_WHITE,
            selectbackground=ACCENT_BLUE,
            selectforeground=FG_WHITE,
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            exportselection=False,
        )
        
        left_scroll = ttk.Scrollbar(left_box, orient="vertical", command=sets_list.yview)
        sets_list.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side="right", fill="y")
        sets_list.pack(side="left", fill="both", expand=True)

        # แผงขวา: รายละเอียดของเซ็ตที่เลือก
        right_box = tk.LabelFrame(
            main_frame,
            text=" รายละเอียดและคำสั่งจัดการ ",
            bg=BG_DARK,
            fg=ACCENT_BLUE,
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10,
        )
        right_box.grid(row=0, column=1, sticky="nsew")

        tk.Label(right_box, text="ชื่อชุดคำสั่ง (Set Name):", bg=BG_DARK, fg=FG_WHITE).pack(anchor="w", pady=(0, 5))
        set_name_entry = ModernEntry(right_box, width=30)
        set_name_entry.pack(fill="x", pady=(0, 10))

        tk.Label(right_box, text="ขั้นตอนภายในชุดคำสั่งย่อยนี้:", bg=BG_DARK, fg=FG_WHITE).pack(anchor="w", pady=(0, 5))
        
        steps_list_frame = tk.Frame(right_box, bg=BG_DARK)
        steps_list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        steps_list = tk.Listbox(
            steps_list_frame,
            bg=BG_PANEL,
            fg=FG_WHITE,
            bd=0,
            highlightthickness=0,
            font=("Consolas", 9),
            height=10,
            exportselection=False,
        )
        
        right_scroll = ttk.Scrollbar(steps_list_frame, orient="vertical", command=steps_list.yview)
        steps_list.configure(yscrollcommand=right_scroll.set)
        right_scroll.pack(side="right", fill="y")
        steps_list.pack(side="left", fill="both", expand=True)

        # ฟังก์ชันรีเฟรชรายชื่อเซ็ต
        def refresh_sets_list(select_name=None):
            sets_list.delete(0, tk.END)
            self.load_script_sets()
            sorted_names = sorted(self.script_sets.keys())
            for name in sorted_names:
                sets_list.insert(tk.END, name)
            if select_name:
                if select_name in sorted_names:
                    idx = sorted_names.index(select_name)
                    sets_list.selection_set(idx)
                    sets_list.see(idx)
                    fill_selected_set()
            elif sorted_names:
                sets_list.selection_set(0)
                fill_selected_set()

        # แสดงรายละเอียดเมื่อเลือกเซ็ต
        def fill_selected_set(event=None):
            selection = sets_list.curselection()
            if not selection:
                set_name_entry.delete(0, tk.END)
                steps_list.delete(0, tk.END)
                return
            name = sets_list.get(selection[0])
            set_name_entry.delete(0, tk.END)
            set_name_entry.insert(0, name)

            steps_list.delete(0, tk.END)
            steps = self.script_sets.get(name, [])
            for i, step in enumerate(steps):
                t = step.get("type", "tap").upper()
                desc = step.get("desc", "")
                if t == "TAP":
                    info = f"คลิก ({step.get('x')}, {step.get('y')})"
                elif t == "SWIPE":
                    info = f"ลากจอ ({step.get('x')},{step.get('y')} -> {step.get('x2')},{step.get('y2')})"
                elif t == "TEXT":
                    info = f"พิมพ์ '{step.get('text')}'"
                elif t == "KEYEVENT":
                    info = f"ปุ่ม {step.get('code')}"
                elif t == "SLEEP":
                    info = f"รอ {step.get('seconds')} วิ"
                elif t == "START_APP":
                    info = f"เปิดแอป '{step.get('text')}'"
                elif t == "STOP_APP":
                    info = f"ปิดแอป '{step.get('text')}'"
                elif t == "CLEAR_APP":
                    info = f"ล้างแอป '{step.get('text')}'"
                elif t == "DETECT_IMAGE":
                    info = f"รูป '{step.get('text')}'"
                elif t == "CLEAR_ADS_LOOP":
                    info = f"ลูปปิดโฆษณา '{step.get('text') or ''}'"
                elif t == "FETCH_OTP":
                    info = f"ดึง OTP '{step.get('text') or ''}'"
                elif t == "RUN_SET":
                    info = f"ใช้เซ็ต '{step.get('set') or ''}'"
                elif t == "SCREENSHOT":
                    info = f"แคปจอ '{step.get('text') or ''}'"
                else:
                    info = t
                steps_list.insert(tk.END, f"{i+1:02d}. [{info}] {desc}")

        sets_list.bind("<<ListboxSelect>>", fill_selected_set)

        # บันทึกขั้นตอนหลักเป็นเซ็ตย่อย
        def save_current_as_set():
            name = set_name_entry.get().strip()
            if not name:
                messagebox.showerror("ข้อผิดพลาด", "กรุณาระบุชื่อชุดคำสั่งย่อย!", parent=dialog)
                return
            if not self.macro_steps:
                messagebox.showerror("ข้อผิดพลาด", "ไม่มีขั้นตอนในคิวหลักที่จะนำมาบันทึก!", parent=dialog)
                return

            slug = safe_set_slug(name)
            filepath = os.path.join(self.script_sets_dir, f"{slug}.json")
            try:
                # กรองไม่ให้เซ็ตย่อยเรียกตัวเองโดยตรง
                for s in self.macro_steps:
                    if s.get("type") == "run_set" and s.get("set") == name:
                        raise ValueError("ไม่สามารถบันทึกเซ็ตที่เรียกใช้ตัวเองเพื่อป้องกันการทำงานวนลูปไม่รู้จบ")
                
                save_script_set(filepath, name, self.macro_steps)
                self.write_log(f"บันทึกชุดคำสั่งย่อยสำเร็จ: {name} ({len(self.macro_steps)} ขั้นตอน)", "success")
                refresh_sets_list(name)
            except Exception as e:
                messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถบันทึกได้: {e}", parent=dialog)

        # ลบเซ็ตย่อย
        def delete_selected_set():
            selection = sets_list.curselection()
            if not selection:
                return
            name = sets_list.get(selection[0])
            slug = safe_set_slug(name)
            filepath = os.path.join(self.script_sets_dir, f"{slug}.json")

            confirm = messagebox.askyesno("ยืนยันการลบ", f"คุณแน่ใจหรือไม่ที่จะลบชุดคำสั่งย่อย '{name}'?", parent=dialog)
            if confirm:
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    self.write_log(f"ลบชุดคำสั่งย่อยสำเร็จ: {name}", "warning")
                    refresh_sets_list()
                except Exception as e:
                    messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถลบไฟล์ได้: {e}", parent=dialog)

        # แทรกเซ็ตเข้าไปในคิวขั้นตอนหลัก
        def insert_set_into_macro():
            selection = sets_list.curselection()
            if not selection:
                messagebox.showwarning("คำเตือน", "กรุณาเลือกชุดคำสั่งย่อยในรายการด้านซ้ายก่อน!", parent=dialog)
                return
            name = sets_list.get(selection[0])

            step = build_run_set_step(name)
            step["desc"] = f"ใช้ชุดคำสั่ง {name}"
            self.macro_steps.append(step)
            self.refresh_listbox()
            self.write_log(f"แทรกชุดคำสั่งย่อย '{name}' เข้าคิวหลักสำเร็จ", "success")
            dialog.destroy()

        # ส่วนปุ่มดำเนินการ
        actions_frame = tk.Frame(right_box, bg=BG_DARK)
        actions_frame.pack(fill="x", pady=(5, 0))

        ModernButton(actions_frame, text="📥 แทรกเข้าคิวสคริปต์หลัก", command=insert_set_into_macro, bg=ACCENT_BLUE, activebg=ACCENT_HOVER).pack(fill="x", pady=2)
        ModernButton(actions_frame, text="➕ บันทึกขั้นตอนหลักปัจจุบันเป็น Set นี้", command=save_current_as_set, bg=ACCENT_GREEN, activebg="#2ecc71").pack(fill="x", pady=2)
        ModernButton(actions_frame, text="🗑️ ลบชุดคำสั่งย่อยนี้", command=delete_selected_set, bg=ACCENT_RED, activebg="#c0392b").pack(fill="x", pady=2)

        # ปิด
        footer = tk.Frame(dialog, bg=BG_DARK)
        footer.pack(fill="x", padx=20, pady=(0, 15))
        ModernButton(footer, text="ปิดหน้าต่าง", command=dialog.destroy, bg=BG_INPUT, activebg="#444444").pack(side="right")

        refresh_sets_list()

    def refresh_listbox(self):
        """อัปเดตลิสต์ในกล่องสคริปต์ขั้นตอน (Listbox) ใหม่"""
        self.refresh_step_list()

    def refresh_step_list(self):
        self.step_listbox.delete(0, tk.END)
        for idx, step in enumerate(self.macro_steps):
            self.step_listbox.insert(tk.END, build_macro_step_summary(idx, step))
        self.update_status_summary()

    def save_profile(self):
        name_slug = self.profile_name_entry.get().strip()
        if not name_slug:
            messagebox.showerror("ข้อผิดพลาด", "กรุณาระบุชื่อโปรไฟล์ที่จะบันทึก!")
            return
            
        # สร้างชื่อแสดงผลเป็นฟอร์แมตสวยงาม
        display_name = name_slug.replace("_", " ").title()
        # แปลงชื่อโปรไฟล์เริ่มต้นให้ตรงกับ default
        if name_slug == "default_login_ads":
            display_name = "Default Login & Ads"
            
        filename = f"{name_slug.lower()}.json"
        filepath = os.path.join(self.macros_dir, filename)
        
        profile_data = {
            "name": display_name,
            "steps": self.macro_steps
        }
        
        try:
            with open(filepath, "w", encoding="utf-8") as file:
                json.dump(profile_data, file, indent=2)
            self.write_log(f"บันทึกไฟล์โปรไฟล์เรียบร้อยแล้ว: {filename}", "success")
            self.load_profiles()
            self.profile_cb.set(display_name)
        except Exception as e:
            self.write_log(f"การบันทึกโปรไฟล์ล้มเหลว: {e}", "error")

    def delete_profile(self):
        name = self.profile_cb.get()
        filepath = self.profiles.get(name)
        if not filepath or not os.path.exists(filepath):
            return
            
        confirm = messagebox.askyesno("ยืนยันการลบ", f"คุณแน่ใจหรือไม่ที่จะลบไฟล์โปรไฟล์ '{name}' จากไดรฟ์?")
        if confirm:
            try:
                os.remove(filepath)
                self.write_log(f"ลบไฟล์โปรไฟล์เรียบร้อยแล้ว: {name}", "warning")
                self.macro_steps = []
                self.refresh_listbox()
                self.load_profiles()
            except Exception as e:
                self.write_log(f"ลบไฟล์ไม่สำเร็จ: {e}", "error")

    def export_profile_package(self):
        import zipfile
        from tkinter import filedialog
        
        name = self.profile_cb.get()
        filepath = self.profiles.get(name)
        if not filepath or not os.path.exists(filepath):
            messagebox.showerror("ข้อผิดพลาด", "ไม่พบข้อมูลโปรไฟล์ที่เลือก กรุณาเลือกหรือบันทึกโปรไฟล์ก่อนส่งออก!")
            return
            
        # 1. อ่านข้อมูลโปรไฟล์
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                profile_data = json.load(f)
        except Exception as e:
            messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถอ่านไฟล์โปรไฟล์ได้: {e}")
            return
            
        steps = profile_data.get("steps", [])
        
        # 2. ค้นหารูปภาพและชุดคำสั่งย่อย (Script Sets) ที่เชื่อมโยง
        referenced_images = set()
        referenced_sets = set()
        
        # ฟังก์ชันค้นหาไฟล์เชื่อมโยงในรายการขั้นตอนแบบ recursive
        def scan_steps(step_list):
            for step in step_list:
                t = step.get("type", "")
                if t == "detect_image":
                    img_name = step.get("text", "").strip()
                    if img_name:
                        referenced_images.add(img_name)
                elif t == "clear_ads_loop":
                    img_text = step.get("text", "").strip()
                    if img_text:
                        # ตัวอย่าง format: lobby.png | close_btn.png,back.png
                        # หรือ close_btn.png,back.png
                        parts = img_text.split("|")
                        for part in parts:
                            images = part.split(",")
                            for img in images:
                                img = img.strip()
                                if img:
                                    referenced_images.add(img)
                elif t == "run_set":
                    set_name = (step.get("set") or step.get("text") or "").strip()
                    if set_name and set_name not in referenced_sets:
                        referenced_sets.add(set_name)
                        # โหลดสคริปต์ของ set นั้นมาค้นหาต่อแบบ recursive
                        set_file = os.path.join(self.script_sets_dir, f"{safe_set_slug(set_name)}.json")
                        if os.path.exists(set_file):
                            try:
                                with open(set_file, "r", encoding="utf-8") as sf:
                                    set_data = json.load(sf)
                                    scan_steps(set_data.get("steps", []))
                            except Exception:
                                pass
                                
        scan_steps(steps)
        
        # 3. ให้ผู้ใช้เลือกบันทึกไฟล์ปลายทาง (.mmpow หรือ .zip)
        save_path = filedialog.asksaveasfilename(
            title="📥 บันทึกไฟล์แพ็คเกจมาโคร",
            defaultextension=".mmpow",
            filetypes=[("MuMupow Package", "*.mmpow"), ("Zip File", "*.zip")],
            initialfile=f"{name.lower().replace(' ', '_')}_package"
        )
        if not save_path:
            return
            
        # 4. บีบอัดไฟล์ลงซิป
        try:
            # สร้างข้อมูล manifest.json เพื่อระบุชื่อไฟล์และรายการของในแพ็คเกจ
            manifest = {
                "profile_name": name,
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "profile_file": os.path.basename(filepath),
                "script_sets": list(referenced_sets),
                "templates": list(referenced_images)
            }
            
            with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                # เขียน manifest.json
                zipf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                
                # เขียน profile.json
                zipf.write(filepath, "profile.json")
                
                # เขียน script sets
                for s_name in referenced_sets:
                    s_file = os.path.join(self.script_sets_dir, f"{safe_set_slug(s_name)}.json")
                    if os.path.exists(s_file):
                        zipf.write(s_file, f"script_sets/{os.path.basename(s_file)}")
                        
                # เขียนรูปภาพใน templates
                for img_name in referenced_images:
                    img_file = os.path.join(self.templates_dir, img_name)
                    if os.path.exists(img_file):
                        zipf.write(img_file, f"templates/{img_name}")
                        
            self.write_log(f"📦 ส่งออกแพ็คเกจ '{name}' สำเร็จ -> {os.path.basename(save_path)}", "success")
            messagebox.showinfo("สำเร็จ", f"ส่งออกแพ็คเกจมาโคร '{name}' เรียบร้อยแล้ว!\nไฟล์ปลายทาง: {os.path.basename(save_path)}")
        except Exception as e:
            self.write_log(f"❌ เกิดข้อผิดพลาดในการส่งออกแพ็คเกจ: {e}", "error")
            messagebox.showerror("ข้อผิดพลาด", f"ส่งออกไม่สำเร็จ: {e}")

    def import_profile_package(self):
        import zipfile
        from tkinter import filedialog
        
        # 1. ให้ผู้ใช้เลือกไฟล์แพ็คเกจที่จะนำเข้า
        open_path = filedialog.askopenfilename(
            title="📤 เลือกไฟล์แพ็คเกจมาโครเพื่อนำเข้า",
            filetypes=[("MuMupow Package", "*.mmpow"), ("Zip File", "*.zip")]
        )
        if not open_path:
            return
            
        try:
            with zipfile.ZipFile(open_path, "r") as zipf:
                # ตรวจสอบไฟล์ภายในซิป
                namelist = zipf.namelist()
                if "manifest.json" not in namelist or "profile.json" not in namelist:
                    messagebox.showerror("ข้อผิดพลาด", "ไฟล์แพ็คเกจไม่ถูกต้อง (ไม่พบไฟล์ระบุข้อมูลหลัก)")
                    return
                    
                # อ่าน manifest.json
                manifest_data = json.loads(zipf.read("manifest.json").decode("utf-8"))
                profile_name = manifest_data.get("profile_name", "Imported Profile")
                
                # ตรวจสอบว่าโปรไฟล์มีอยู่เดิมหรือไม่ หากมีอยู่แล้ว ให้ยืนยันเขียนทับ
                if profile_name in self.profiles:
                    confirm = messagebox.askyesno(
                        "เขียนทับโปรไฟล์",
                        f"โปรไฟล์ชื่อ '{profile_name}' มีอยู่แล้วในเครื่อง คุณต้องการเขียนทับหรือไม่?"
                    )
                    if not confirm:
                        return
                        
                # 2. สกัดรูปภาพ templates
                templates_imported = 0
                for file_in_zip in namelist:
                    if file_in_zip.startswith("templates/") and not file_in_zip.endswith("/"):
                        img_name = os.path.basename(file_in_zip)
                        target_img_path = os.path.join(self.templates_dir, img_name)
                        # ดึงไฟล์และเขียนบันทึก
                        with open(target_img_path, "wb") as f:
                            f.write(zipf.read(file_in_zip))
                        templates_imported += 1
                        
                # 3. สกัดชุดคำสั่งย่อย script_sets
                sets_imported = 0
                for file_in_zip in namelist:
                    if file_in_zip.startswith("script_sets/") and not file_in_zip.endswith("/"):
                        set_filename = os.path.basename(file_in_zip)
                        target_set_path = os.path.join(self.script_sets_dir, set_filename)
                        # ดึงไฟล์และเขียนบันทึก
                        with open(target_set_path, "wb") as f:
                            f.write(zipf.read(file_in_zip))
                        sets_imported += 1
                        
                # 4. เขียนไฟล์โปรไฟล์หลัก
                target_profile_filename = manifest_data.get("profile_file", f"{profile_name.lower().replace(' ', '_')}.json")
                target_profile_path = os.path.join(self.macros_dir, target_profile_filename)
                
                with open(target_profile_path, "wb") as f:
                    f.write(zipf.read("profile.json"))
                    
            # 5. โหลดข้อมูลกลับเข้าโปรแกรม
            self.load_profiles()
            self.load_script_sets()
            self.profile_cb.set(profile_name)
            self.on_profile_select()
            
            self.write_log(
                f"📥 นำเข้าแพ็คเกจ '{profile_name}' สำเร็จ (นำเข้ารูปภาพ {templates_imported} รูป, ชุดคำสั่ง {sets_imported} ชุด)", 
                "success"
            )
            messagebox.showinfo(
                "นำเข้าสำเร็จ", 
                f"นำเข้าโปรไฟล์ '{profile_name}' เรียบร้อยแล้ว!\n"
                f"- นำเข้ารูปภาพสำหรับตรวจจับ: {templates_imported} รูป\n"
                f"- นำเข้าชุดคำสั่งย่อย: {sets_imported} ชุด"
            )
        except Exception as e:
            self.write_log(f"❌ เกิดข้อผิดพลาดในการนำเข้าแพ็คเกจ: {e}", "error")
            messagebox.showerror("ข้อผิดพลาด", f"นำเข้าไม่สำเร็จ: {e}")

    # --- การโต้ตอบกับกล่องขั้นตอนมาโครด้านซ้าย ---
    def on_listbox_select(self, event):
        selection = self.step_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        step = self.macro_steps[idx]
        
        # ถอดค่ากลับมาใส่ในฟอร์มแก้ไขฝั่งขวา
        t = step.get("type", "tap")
        if t == "tap":
            self.form_type.set("คลิกหน้าจอ (Tap)")
        elif t == "swipe":
            self.form_type.set("ลาก/เลื่อนหน้าจอ (Swipe)")
        elif t == "text":
            self.form_type.set("พิมพ์ข้อความ (Text)")
        elif t == "keyevent":
            self.form_type.set("กดปุ่มระบบ (Keyevent)")
        elif t == "sleep":
            self.form_type.set("รอเวลา (Sleep)")
        elif t == "start_app":
            self.form_type.set("เปิดแอป (Start App)")
        elif t == "stop_app":
            self.form_type.set("ปิดแอป (Stop App)")
        elif t == "detect_image":
            self.form_type.set("ตรวจจับรูปภาพ (Image Match)")
        elif t == "wait_for_image":
            self.form_type.set("รอจนเจอรูป (Wait Image)")
        elif t == "tap_text":
            self.form_type.set("กดตามข้อความ (Tap Text)")
        elif t == "wait_for_text":
            self.form_type.set("รอจนเจอข้อความ (Wait Text)")
        elif t == "clear_ads_loop":
            self.form_type.set("ลูปปิดโฆษณา (Clear Ads Loop)")
        elif t == "fetch_otp":
            self.form_type.set("กรอก OTP อัตโนมัติ (Auto Fill OTP)")
        elif t == "run_set":
            self.form_type.set("ใช้ชุดคำสั่ง (Run Set)")
        elif t == "screenshot":
            self.form_type.set("แคปหน้าจอ (Screenshot)")
        elif t == "keyboard":
            self.form_type.set("คีย์บอร์ด (Keyboard)")
        elif t == "read_diamond":
            self.form_type.set("อ่านเพชร (Read Diamond)")

        self.on_step_type_change()
        
        self.form_desc.delete(0, tk.END)
        self.form_desc.insert(0, step.get("desc", ""))
        
        # เคลียร์ค่าตัวเลข/ข้อมูลเก่าก่อนเริ่มใส่ใหม่
        self.form_x.delete(0, tk.END)
        self.form_y.delete(0, tk.END)
        self.form_x2.delete(0, tk.END)
        self.form_y2.delete(0, tk.END)
        self.form_text.delete(0, tk.END)
        self.form_code.delete(0, tk.END)
        self.form_sleep.delete(0, tk.END)

        if t == "tap":
            self.form_x.insert(0, step.get("x", ""))
            self.form_y.insert(0, step.get("y", ""))
            self.form_sleep.insert(0, step.get("delay", "5.0"))
        elif t == "swipe":
            self.form_x.insert(0, step.get("x", ""))
            self.form_y.insert(0, step.get("y", ""))
            self.form_x2.insert(0, step.get("x2", ""))
            self.form_y2.insert(0, step.get("y2", ""))
            self.form_sleep.insert(0, step.get("delay", "5.0"))
        elif t == "wait_for_image":
            self.form_text.insert(0, step.get("text", ""))
            self.form_sleep.insert(0, step.get("timeout", "30"))
        elif t == "tap_text":
            self.form_text.insert(0, step.get("text", ""))
            self.form_sleep.insert(0, step.get("delay", "1.0"))
        elif t == "wait_for_text":
            self.form_text.insert(0, step.get("text", ""))
            self.form_sleep.insert(0, step.get("timeout", "30"))
        elif t in ["text", "start_app", "stop_app", "detect_image", "clear_ads_loop", "fetch_otp", "screenshot", "read_diamond"]:
            self.form_text.insert(0, step.get("text", ""))
            self.form_sleep.insert(0, step.get("delay", "5.0" if t == "text" else "1.0"))
        elif t == "run_set":
            self.form_text.insert(0, step.get("set", ""))
        elif t == "keyevent":
            self.form_code.insert(0, step.get("code", ""))
            self.form_sleep.insert(0, step.get("delay", "0.3"))
        elif t == "sleep":
            self.form_sleep.insert(0, step.get("seconds", "1.0"))
        elif t == "keyboard":
            self.form_text.insert(0, step.get("key", ""))
            self.form_code.insert(0, step.get("action", ""))
            self.form_sleep.insert(0, step.get("delay", "0.1"))

    def on_step_type_change(self, event=None):
        t = self.form_type.get()
        # เปิดให้แก้ไขทั้งหมดก่อน
        self.form_x.configure(state="normal")
        self.form_y.configure(state="normal")
        self.form_x2.configure(state="normal")
        self.form_y2.configure(state="normal")
        self.form_text.configure(state="normal")
        self.form_code.configure(state="normal")
        self.form_sleep.configure(state="normal")
        
        self.form_x_label.configure(text="พิกัดคลิก (X Y):", fg=FG_WHITE)
        self.form_x2_label.configure(fg=FG_WHITE)
        self.form_sleep_label.configure(text="หน่วงหลังทำเสร็จ (วินาที):")
        
        # ปรับเปลี่ยนฉลากปุ่มและสถานะการปิดป้อน
        if "Tap" in t:
            self.form_text.configure(state="disabled")
            self.form_code.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
        elif "Swipe" in t:
            self.form_x_label.configure(text="จุดเริ่ม (X1 Y1):")
            self.form_text.configure(state="disabled")
            self.form_code.configure(state="disabled")
        elif "Text" in t:
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_code.configure(state="disabled")
        elif "Keyevent" in t:
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_text.configure(state="disabled")
        elif "Sleep" in t:
            self.form_sleep_label.configure(text="ระยะเวลารอ (วินาที):")
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_text.configure(state="disabled")
            self.form_code.configure(state="disabled")
        elif "Start App" in t or "Stop App" in t or "Clear App Data" in t:
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_code.configure(state="disabled")
        elif "Wait Image" in t or "Wait Text" in t:
            self.form_sleep_label.configure(text="ระยะเวลารอสูงสุด (วินาที):")
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_code.configure(state="disabled")
        elif "Tap Text" in t:
            self.form_sleep_label.configure(text="หน่วงหลังคลิก (วินาที):")
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_code.configure(state="disabled")
        elif "Image Match" in t or "Clear Ads Loop" in t or "Auto Fill OTP" in t:
            if "Auto Fill OTP" in t:
                self.form_sleep_label.configure(text="หน่วงหลังกรอก OTP (วินาที):")
            else:
                self.form_sleep_label.configure(text="หน่วงหลังคลิก (วินาที):")
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_code.configure(state="disabled")
        elif "Run Set" in t or "ใช้ชุดคำสั่ง" in t:
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_code.configure(state="disabled")
            self.form_sleep.configure(state="disabled")
        elif "Screenshot" in t or "แคปหน้าจอ" in t:
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_code.configure(state="disabled")
        elif "Read Diamond" in t or "อ่านเพชร" in t:
            # อ่านเพชรไม่ใช้พิกัด/ข้อความ — ใช้พื้นที่ตัวเลขเพชรที่ตั้งไว้แล้ว (ปุ่ม ⚙️ ตั้งค่าพื้นที่เพชร)
            self.form_sleep_label.configure(text="หน่วงหลังอ่าน (วินาที):")
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_text.configure(state="disabled")
            self.form_code.configure(state="disabled")
        elif "Keyboard" in t or "คีย์บอร์ด" in t:
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)

    def clear_form(self):
        self.form_x.delete(0, tk.END)
        self.form_y.delete(0, tk.END)
        self.form_x2.delete(0, tk.END)
        self.form_y2.delete(0, tk.END)
        self.form_text.delete(0, tk.END)
        self.form_code.delete(0, tk.END)
        self.form_sleep.delete(0, tk.END)
        self.form_desc.delete(0, tk.END)

    def append_quick_step(self, step):
        self.macro_steps.append(step)
        self.refresh_listbox()
        self.step_listbox.selection_clear(0, tk.END)
        self.step_listbox.selection_set(tk.END)
        self.step_listbox.see(tk.END)
        self.write_log(f"เพิ่มขั้นตอนจาก Quick Builder: {step.get('desc', step.get('type'))}", "info")

    def open_quick_builder_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("⚡ สร้างสคริปต์เร็ว")
        dialog.geometry("760x720")
        dialog.configure(bg=BG_DARK)
        dialog.transient(self)
        dialog.grab_set()

        x = self.winfo_x() + (self.winfo_width() // 2) - 380
        y = self.winfo_y() + (self.winfo_height() // 2) - 360
        dialog.geometry(f"+{x}+{y}")

        tk.Label(
            dialog,
            text="สร้างสคริปต์เร็วจากจุดกดที่จำไว้",
            bg=BG_DARK,
            fg=FG_WHITE,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 4))

        tk.Label(
            dialog,
            text="กด preset หรือปุ่มคำสั่งด้านขวาเพื่อเพิ่ม step เข้าโปรไฟล์มาโครทันที",
            bg=BG_DARK,
            fg=FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=18, pady=(0, 12))

        body = tk.Frame(dialog, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        preset_box = tk.LabelFrame(
            body,
            text=" จุดกดที่ใช้บ่อย ",
            bg=BG_DARK,
            fg=ACCENT_BLUE,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=10,
        )
        preset_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        preset_list = tk.Listbox(
            preset_box,
            bg=BG_PANEL,
            fg=FG_WHITE,
            selectbackground=ACCENT_BLUE,
            selectforeground=FG_WHITE,
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            height=9,
            exportselection=False,
        )
        preset_list.pack(fill="both", expand=True)

        fields = tk.Frame(preset_box, bg=BG_DARK)
        fields.pack(fill="x", pady=(10, 0))

        tk.Label(fields, text="ชื่อ:", bg=BG_DARK, fg=FG_WHITE).grid(row=0, column=0, sticky="w", pady=3)
        preset_name_entry = ModernEntry(fields, width=18)
        preset_name_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=3)

        tk.Label(fields, text="X:", bg=BG_DARK, fg=FG_WHITE).grid(row=1, column=0, sticky="w", pady=3)
        preset_x_entry = ModernEntry(fields, width=8)
        preset_x_entry.grid(row=1, column=1, sticky="w", padx=(8, 12), pady=3)

        tk.Label(fields, text="Y:", bg=BG_DARK, fg=FG_WHITE).grid(row=1, column=2, sticky="w", pady=3)
        preset_y_entry = ModernEntry(fields, width=8)
        preset_y_entry.grid(row=1, column=3, sticky="w", padx=(8, 0), pady=3)
        fields.columnconfigure(1, weight=1)

        def refresh_preset_list(select_index=None):
            preset_list.delete(0, tk.END)
            for preset in self.coordinate_presets:
                preset_list.insert(tk.END, f"{preset['name']}  ({preset['x']}, {preset['y']})")
            if select_index is not None and self.coordinate_presets:
                safe_index = max(0, min(select_index, len(self.coordinate_presets) - 1))
                preset_list.selection_set(safe_index)
                preset_list.see(safe_index)

        def fill_selected_preset(event=None):
            selection = preset_list.curselection()
            if not selection:
                return
            preset = self.coordinate_presets[selection[0]]
            preset_name_entry.delete(0, tk.END)
            preset_name_entry.insert(0, preset["name"])
            preset_x_entry.delete(0, tk.END)
            preset_x_entry.insert(0, str(preset["x"]))
            preset_y_entry.delete(0, tk.END)
            preset_y_entry.insert(0, str(preset["y"]))

        def add_selected_preset_step():
            selection = preset_list.curselection()
            if not selection:
                messagebox.showwarning("เลือกจุดก่อน", "กรุณาเลือก preset พิกัดที่ต้องการเพิ่ม", parent=dialog)
                return
            self.append_quick_step(build_tap_step_from_preset(self.coordinate_presets[selection[0]]))

        def save_preset_from_fields():
            try:
                preset = normalize_coordinate_preset({
                    "name": preset_name_entry.get(),
                    "x": preset_x_entry.get(),
                    "y": preset_y_entry.get(),
                })
            except ValueError as e:
                messagebox.showerror("Preset ไม่ถูกต้อง", str(e), parent=dialog)
                return

            existing_index = next((idx for idx, item in enumerate(self.coordinate_presets) if item["name"] == preset["name"]), None)
            if existing_index is None:
                self.coordinate_presets.append(preset)
                selected_index = len(self.coordinate_presets) - 1
            else:
                self.coordinate_presets[existing_index] = preset
                selected_index = existing_index

            self.save_coordinate_presets()
            refresh_preset_list(selected_index)
            self.write_log(f"บันทึก preset พิกัด: {preset['name']} ({preset['x']}, {preset['y']})", "success")

        def delete_selected_preset():
            selection = preset_list.curselection()
            if not selection:
                return
            preset = self.coordinate_presets.pop(selection[0])
            self.save_coordinate_presets()
            refresh_preset_list()
            self.write_log(f"ลบ preset พิกัด: {preset['name']}", "warning")

        preset_list.bind("<<ListboxSelect>>", fill_selected_preset)

        preset_actions = tk.Frame(preset_box, bg=BG_DARK)
        preset_actions.pack(fill="x", pady=(10, 0))
        ModernButton(preset_actions, text="➕ เพิ่มคลิกจาก preset", command=add_selected_preset_step, bg=ACCENT_GREEN, activebg="#2ecc71").pack(fill="x", pady=2)
        ModernButton(preset_actions, text="💾 บันทึก/แก้ไข preset", command=save_preset_from_fields, bg=ACCENT_BLUE, activebg=ACCENT_HOVER).pack(fill="x", pady=2)
        ModernButton(preset_actions, text="🗑️ ลบ preset", command=delete_selected_preset, bg=BG_INPUT, activebg="#444444").pack(fill="x", pady=2)

        command_box = tk.LabelFrame(
            body,
            text=" ปุ่มคำสั่งเร็ว ",
            bg=BG_DARK,
            fg=ACCENT_BLUE,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=10,
        )
        command_box.grid(row=0, column=1, sticky="nsew")

        def add_step_button(parent, text, step_factory, bg=ACCENT_BLUE):
            ModernButton(parent, text=text, command=lambda: self.append_quick_step(step_factory()), bg=bg, activebg=ACCENT_HOVER).pack(fill="x", pady=2)

        text_box = tk.LabelFrame(command_box, text=" ข้อมูลบัญชี ", bg=BG_DARK, fg=FG_MUTED, padx=8, pady=8)
        text_box.pack(fill="x", pady=(0, 8))
        add_step_button(text_box, "พิมพ์ {EMAIL}", lambda: build_text_step("{EMAIL}"))
        add_step_button(text_box, "พิมพ์ {PASSWORD}", lambda: build_text_step("{PASSWORD}"))

        timing_box = tk.LabelFrame(command_box, text=" หน่วงเวลา ", bg=BG_DARK, fg=FG_MUTED, padx=8, pady=8)
        timing_box.pack(fill="x", pady=(0, 8))
        for seconds in (0.3, 0.5, 1, 2):
            add_step_button(timing_box, f"รอ {seconds:g} วิ", lambda s=seconds: build_sleep_step(s), bg=BG_INPUT)

        nav_box = tk.LabelFrame(command_box, text=" ปุ่มระบบ / เลื่อนจอ ", bg=BG_DARK, fg=FG_MUTED, padx=8, pady=8)
        nav_box.pack(fill="x")
        add_step_button(nav_box, "กด BACK", lambda: build_key_step("BACK"), bg=BG_INPUT)
        add_step_button(nav_box, "กด HOME", lambda: build_key_step("HOME"), bg=BG_INPUT)
        add_step_button(nav_box, "กด ENTER", lambda: build_key_step("ENTER"), bg=BG_INPUT)
        add_step_button(nav_box, "เลื่อนขึ้น", lambda: build_swipe_step("up"), bg=ACCENT_ORANGE)
        add_step_button(nav_box, "เลื่อนลง", lambda: build_swipe_step("down"), bg=ACCENT_ORANGE)

        footer = tk.Frame(dialog, bg=BG_DARK)
        footer.pack(fill="x", padx=18, pady=(0, 12))
        ModernButton(footer, text="ปิด", command=dialog.destroy, bg=BG_INPUT, activebg="#444444").pack(side="right")

        refresh_preset_list(0)
        fill_selected_preset()

    def _build_step_from_form(self):
        """อ่านค่าจากฟอร์มสร้าง step dict (ใช้ร่วมกันระหว่างเพิ่ม/อัปเดต)

        คืน step dict ถ้าถูกต้อง หรือ None ถ้าข้อมูลไม่ผ่าน (แสดง error แล้ว)
        """
        t = label_to_step_type(self.form_type.get())
        desc = self.form_desc.get().strip()
        step = {"type": t, "desc": desc}

        try:
            if t == "tap":
                step["x"] = self.form_x.get().strip()
                step["y"] = self.form_y.get().strip()
                if not step["x"] or not step["y"]: raise ValueError("พิกัดห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "5.0")
            elif t == "swipe":
                step["x"] = self.form_x.get().strip()
                step["y"] = self.form_y.get().strip()
                step["x2"] = self.form_x2.get().strip()
                step["y2"] = self.form_y2.get().strip()
                if not step["x"] or not step["y"] or not step["x2"] or not step["y2"]:
                    raise ValueError("พิกัดจุดเริ่มหรือจุดปลายห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "5.0")
            elif t == "wait_for_image":
                step["text"] = self.form_text.get().strip()
                if not step["text"]:
                    raise ValueError("ชื่อไฟล์รูปภาพต้นแบบห้ามว่างเปล่า")
                # ช่อง "หน่วงเวลา" ใช้เป็นระยะเวลารอสูงสุด (timeout) สำหรับ step นี้
                step["timeout"] = float(self.form_sleep.get().strip() or "30")
            elif t == "tap_text":
                step["text"] = self.form_text.get().strip()
                if not step["text"]:
                    raise ValueError("ข้อความ/id ที่จะค้นหาห้ามว่างเปล่า (ขึ้นต้น id: เพื่อค้นจาก resource-id)")
                step["delay"] = float(self.form_sleep.get().strip() or "1.0")
            elif t == "wait_for_text":
                step["text"] = self.form_text.get().strip()
                if not step["text"]:
                    raise ValueError("ข้อความ/id ที่จะค้นหาห้ามว่างเปล่า (ขึ้นต้น id: เพื่อค้นจาก resource-id)")
                step["timeout"] = float(self.form_sleep.get().strip() or "30")
            elif t == "read_diamond":
                # อ่านเพชร: ไม่ต้องใส่พิกัด/ข้อความ มีแค่ค่าหน่วงหลังอ่าน
                step["delay"] = float(self.form_sleep.get().strip() or "1.0")
            elif t in ["text", "start_app", "stop_app", "detect_image", "clear_ads_loop", "fetch_otp", "screenshot"]:
                step["text"] = self.form_text.get()
                if t in ["start_app", "stop_app", "detect_image"] and not step["text"]:
                    raise ValueError("ชื่อไฟล์รูปภาพต้นแบบห้ามว่างเปล่า" if t == "detect_image" else "ชื่อสัญลักษณ์แพ็คเกจ/แอปห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or ("5.0" if t == "text" else "1.0"))
            elif t == "keyevent":
                step["code"] = self.form_code.get().strip()
                if not step["code"]: raise ValueError("รหัสปุ่มกดคีย์เวนท์ห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "0.3")
            elif t == "sleep":
                step["seconds"] = float(self.form_sleep.get().strip())
            elif t == "run_set":
                step["set"] = self.form_text.get().strip()
                if not step["set"]: raise ValueError("ชื่อชุดคำสั่งย่อยห้ามว่างเปล่า")
            elif t == "keyboard":
                step["key"] = self.form_text.get().strip().lower()
                step["action"] = self.form_code.get().strip().lower()
                if not step["key"] or not step["action"]: raise ValueError("คีย์และสถานะคีย์บอร์ดห้ามว่างเปล่า")
                if step["action"] not in ["down", "up", "press"]:
                    raise ValueError("สถานะคีย์บอร์ดต้องเป็น down, up หรือ press")
                step["delay"] = float(self.form_sleep.get().strip() or "0.1")
        except ValueError as e:
            messagebox.showerror("ข้อมูลไม่ถูกต้อง", f"การตรวจสอบความถูกต้องการป้อนข้อมูลล้มเหลว: {e}")
            return None

        return step

    def add_step(self):
        step = self._build_step_from_form()
        if step is None:
            return

        self.macro_steps.append(step)
        self.refresh_listbox()
        self.write_log(f"เพิ่มขั้นตอนสำเร็จ: {step['desc']}", "info")

    def update_step(self):
        selection = self.step_listbox.curselection()
        if not selection:
            messagebox.showwarning("คำเตือน", "กรุณาคลิกเลือกขั้นตอนในรายการฝั่งซ้ายที่ต้องการอัปเดตก่อน!")
            return
        idx = selection[0]

        step = self._build_step_from_form()
        if step is None:
            return

        # คงข้อมูล anchor (ภาพ+ตั้งค่า) ที่ไม่ได้อยู่ในฟอร์มไว้ ไม่ให้หายตอนอัปเดตสเต็ป
        old = self.macro_steps[idx] if idx < len(self.macro_steps) else {}
        for k in ("anchor_img", "anchor_region", "anchor_tap", "anchor_timeout", "anchor_threshold",
                  "anchor_on_fail", "anchor_retry_target", "anchor_retry_limit"):
            if k in old:
                step[k] = old[k]

        self.macro_steps[idx] = step
        self.refresh_listbox()
        self.step_listbox.selection_set(idx)
        self.write_log(f"อัปเดตขั้นตอนลำดับที่ {idx+1} สำเร็จแล้ว", "info")

    def test_selected_step(self):
        """ทดสอบสเต็ปที่เลือก — แตะ/ปัดพิกัดจริงบนจอทันที (ให้เห็นว่ากดตรงไหน)
        ถ้าสเต็ปมี anchor จะเช็คก่อนว่าตอนนี้เจอภาพบนจอไหม (ยืนยันว่าอยู่หน้าถูก)"""
        if self.macro_running:
            messagebox.showwarning("กำลังรันอยู่", "หยุดมาโครก่อนถึงจะทดสอบสเต็ปได้")
            return
        selection = self.step_listbox.curselection()
        if not selection:
            messagebox.showwarning("ยังไม่ได้เลือกสเต็ป", "คลิกเลือกสเต็ปในลิสต์ซ้ายก่อน แล้วค่อยกดทดสอบ")
            return
        idx = selection[0]
        step = self.macro_steps[idx]
        t = step.get("type", "")
        if t not in ("tap", "swipe"):
            messagebox.showinfo("ทดสอบได้เฉพาะ tap/swipe", f"สเต็ปชนิด '{t}' ยังไม่รองรับการทดสอบแบบแตะจริง\n(ใช้กับ tap/swipe ที่มีพิกัด)")
            return

        devices = self.get_selected_devices() or self.controller.get_connected_devices()
        if not devices:
            messagebox.showerror("ไม่พบอุปกรณ์", "ต้องมี Emulator เชื่อมต่อ + เปิดหน้าที่จะทดสอบไว้ก่อน")
            return
        device = devices[0]

        # ถ้ามี anchor -> รายงานว่าตอนนี้เจอภาพบนจอไหม (ให้รู้ว่าอยู่หน้าถูกหรือเปล่า)
        anchor_hit = None
        if step.get("anchor_img"):
            import base64
            try:
                tb = base64.b64decode(step["anchor_img"])
                ok, data = self.controller.capture_screenshot_bytes(device)
                if ok:
                    thr = float(step.get("anchor_threshold", 0.8) or 0.8)
                    found, ax, ay, msg = self.controller.match_template_bytes(data, tb, thr)
                    if found:
                        anchor_hit = (ax, ay)
                    icon = "✅ เจอภาพ anchor" if found else "❌ ไม่เจอภาพ anchor (อาจอยู่ผิดหน้า)"
                    self.write_log(f"   🔎 [{device}] ทดสอบ anchor สเต็ป {idx+1}: {icon} — {msg}", "info" if found else "warning")
            except Exception:
                pass

        try:
            if t == "tap":
                x, y = int(float(step["x"])), int(float(step["y"]))
                # โหมดกดตามภาพ: ย้ายจุดกดไปตรงที่เจอ anchor (เหมือนตอนรันจริง)
                reg = step.get("anchor_region")
                if step.get("anchor_tap") and anchor_hit and reg:
                    x = int(round(anchor_hit[0] + (x - (reg["x"] + reg["w"] / 2.0))))
                    y = int(round(anchor_hit[1] + (y - (reg["y"] + reg["h"] / 2.0))))
                    self.write_log(f"   🎯 [{device}] (โหมดกดตามภาพ) จุดกดจริง -> ({x},{y})", "info")
                self.write_log(f"   🧪 [{device}] ทดสอบแตะสเต็ป {idx+1} ที่ ({x},{y})", "warning")
                self.controller.tap(device, x, y)
            else:  # swipe
                x, y = int(float(step["x"])), int(float(step["y"]))
                x2, y2 = int(float(step["x2"])), int(float(step["y2"]))
                dur = int(float(step.get("duration", 300) or 300))
                self.write_log(f"   🧪 [{device}] ทดสอบปัดสเต็ป {idx+1} ({x},{y})→({x2},{y2})", "warning")
                self.controller.swipe(device, x, y, x2, y2, dur)
        except (TypeError, ValueError, KeyError) as e:
            messagebox.showerror("พิกัดไม่ถูกต้อง", f"สเต็ปนี้พิกัดไม่ครบ/ไม่ถูกต้อง: {e}")

    def open_flow_view(self):
        """มุมมองผังงาน (flowchart จริง): anchor = ข้าวหลามตัด 'เจอภาพ?' (เจอ→ลงล่างกด,
        ไม่เจอ→แยกออก ข้าม/หยุด), ขั้นปกติ = สี่เหลี่ยม, เริ่ม/จบ = แคปซูลเขียว, หยุด = แดง
        คลิกกล่อง = เลือกขั้นนั้น (ไปแก้ในฟอร์มหลัก) + แถบเครื่องมือ แทรก/ลบ/สลับ"""
        if not self.macro_steps:
            messagebox.showinfo("ยังไม่มีสคริปต์", "โหลด/สร้างสคริปต์ก่อน (เลือกที่หน้าแรก) แล้วค่อยเปิดผังงาน")
            return
        TYPE_TH = {
            "tap": "แตะ", "swipe": "ปัด", "text": "พิมพ์", "keyevent": "ปุ่มระบบ", "sleep": "รอเวลา",
            "start_app": "เปิดแอป", "stop_app": "ปิดแอป", "detect_image": "เจอรูปแล้วกด",
            "wait_for_image": "รอรูป", "tap_text": "กดตามข้อความ", "wait_for_text": "รอข้อความ",
            "screenshot": "ถ่ายจอ", "clear_ads_loop": "ปิดโฆษณาวน", "fetch_otp": "ดึง OTP",
            "keyboard": "คีย์บอร์ด", "read_diamond": "อ่านเพชร", "story_auto": "เล่นเนื้อเรื่อง",
            "find_yellow_stage": "ด่านเหลือง", "run_set": "ชุดคำสั่ง",
        }
        GREEN, ORANGE, BLUE, RED, GRAY, SEL = "#4CAF50", "#ED9F27", "#4472C4", "#E53935", "#8DA0B8", "#FFD54F"
        GOLD = "#FBBF24"  # สีเส้นวนกลับ (retry) — ใช้เฉดเดียวกับผังโฟลว์ฝั่งเว็บ ให้ดูเป็นระบบเดียวกัน

        dlg = tk.Toplevel(self)
        dlg.title("🔀 ผังงานสคริปต์")
        dlg.configure(bg=BG_DARK)
        dlg.geometry("740x820")
        dlg.transient(self)
        state = {"sel": None}

        tb = tk.Frame(dlg, bg=BG_PANEL); tb.pack(fill="x")
        sel_lbl = tk.Label(tb, text="คลิกกล่องในผังเพื่อเลือกขั้น", bg=BG_PANEL, fg=FG_WHITE,
                           font=("Segoe UI", 9, "bold"))
        sel_lbl.pack(side="left", padx=12, pady=6)

        def op(kind):
            i = state["sel"]
            if i is None:
                messagebox.showinfo("ยังไม่เลือก", "คลิกเลือกขั้นในผังก่อน", parent=dlg); return
            if kind == "ins":
                self.macro_steps.insert(i + 1, {"type": "tap", "x": "0", "y": "0", "delay": 0.5,
                                                "desc": "ขั้นใหม่ (แก้พิกัด/ชนิด)"})
                state["sel"] = i + 1
            elif kind == "del":
                self.macro_steps.pop(i)
                state["sel"] = (min(i, len(self.macro_steps) - 1) if self.macro_steps else None)
            elif kind in ("up", "down"):
                j = i + (-1 if kind == "up" else 1)
                if 0 <= j < len(self.macro_steps):
                    self.macro_steps[i], self.macro_steps[j] = self.macro_steps[j], self.macro_steps[i]
                    state["sel"] = j
            self.refresh_listbox()
            if state["sel"] is not None:
                select(state["sel"], center=False)
            else:
                draw()
        for txt, k in (("＋ แทรก", "ins"), ("▲", "up"), ("▼", "down"), ("🗑 ลบ", "del")):
            ModernButton(tb, text=txt, command=lambda kk=k: op(kk), variant="subtle",
                         font=("Segoe UI", 9)).pack(side="left", padx=3, pady=4)

        def test_sel():
            """ทดสอบขั้นที่เลือกในผัง — แตะจริงบนจอ (ดูการขยับ) ใช้ตัวเดียวกับปุ่มทดสอบในฟอร์ม"""
            if state["sel"] is None:
                messagebox.showinfo("ยังไม่เลือก", "คลิกเลือกกล่องในผังก่อน แล้วค่อยกดทดสอบ", parent=dlg)
                return
            try:
                self.step_listbox.selection_clear(0, tk.END)
                self.step_listbox.selection_set(state["sel"])
            except Exception:
                pass
            self.test_selected_step()
        ModernButton(tb, text="🧪 ทดสอบขั้นนี้ (แตะจริงบนจอ)", command=test_sel,
                     variant="warning", font=("Segoe UI", 9)).pack(side="right", padx=8, pady=4)

        wrap = tk.Frame(dlg, bg=BG_DARK); wrap.pack(fill="both", expand=True)
        cv = tk.Canvas(wrap, bg=BG_DARK, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        hsb = ttk.Scrollbar(dlg, orient="horizontal", command=cv.xview)
        cv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        hsb.pack(fill="x", side="bottom")
        cv.bind("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))

        CX = 300

        def select(i, center=True):
            state["sel"] = i
            s = self.macro_steps[i]
            sel_lbl.configure(text=f"เลือกขั้น {i + 1}: {(s.get('desc') or s.get('type',''))[:34]}")
            try:
                self.step_listbox.selection_clear(0, tk.END)
                self.step_listbox.selection_set(i)
                self.step_listbox.see(i)
                self.on_listbox_select(None)
            except Exception:
                pass
            draw()

        def shape(cx, cy, kind, fill, text, i, hw, hh):
            outline = SEL if (i is not None and state["sel"] == i) else fill
            ow = 3 if (i is not None and state["sel"] == i) else 1
            tag = f"n{i}"
            if kind == "diamond":
                cv.create_polygon(cx, cy - hh, cx + hw, cy, cx, cy + hh, cx - hw, cy,
                                  fill=fill, outline=outline, width=ow, tags=tag)
            else:
                cv.create_rectangle(cx - hw, cy - hh, cx + hw, cy + hh, fill=fill, outline=outline, width=ow, tags=tag)
            cv.create_text(cx, cy, text=text, fill="#ffffff", font=("Segoe UI", 9), width=hw * 2 - 12, tags=tag)
            if i is not None and i >= 0:
                cv.tag_bind(tag, "<Button-1>", lambda e, ix=i: select(ix))

        def down(y1, y2, label=None):
            cv.create_line(CX, y1, CX, y2, fill=GRAY, width=2, arrow=tk.LAST)
            if label:
                cv.create_text(CX + 16, (y1 + y2) // 2, text=label, fill=GRAY, font=("Segoe UI", 8), anchor="w")

        def draw():
            cv.delete("all")
            n = len(self.macro_steps)
            cys = [150 + i * 100 for i in range(n)]
            ye = 150 + n * 100
            shape(CX, 45, "pill", GREEN, "เริ่ม (บัญชีถัดไป)", -1, 95, 20)
            prev_bottom = 65
            for i, step in enumerate(self.macro_steps):
                cy = cys[i]
                # บล็อกทางเลือก (if_image) — เช็คก่อนเสมอ เพราะอาจมี anchor_img ติดมาด้วย (ภาพเงื่อนไข)
                # ไม่ใช่ anchor gate ของ tap/swipe จะปล่อยไหลไปวาดเป็นเพชร abort/skip/retry ผิดความหมาย
                # ผังนี้แสดงได้แค่ว่า "มีบล็อกทางเลือกตรงนี้" — แก้ไข/ดูเนื้อในกิ่งต้องใช้เว็บ (MuMupow_new)
                if step.get("type") == "if_image":
                    down(prev_bottom, cy - 30)
                    n_then, n_else = len(step.get("then") or []), len(step.get("else") or [])
                    label = f"{i + 1}. 🔀 {step.get('desc') or 'ถ้าเจอภาพ?'}"
                    shape(CX, cy, "diamond", GOLD, label, i, 105, 30)
                    cv.create_text(CX, cy + 42, text=f"เจอ={n_then} ขั้น · ไม่เจอ={n_else} ขั้น (แก้ไขที่เว็บ)",
                                  fill=GOLD, font=("Segoe UI", 8, "italic"))
                    prev_bottom = cy + 56
                    continue
                anchored = bool(step.get("anchor_img"))
                th = TYPE_TH.get(step.get("type", "tap"), step.get("type", ""))
                mark = ("🎯" if step.get("anchor_tap") else "📷") if anchored else ""
                label = f"{i + 1}. {mark}{step.get('desc') or th}"
                if anchored:
                    down(prev_bottom, cy - 34, "เจอ→ทำ")
                    shape(CX, cy, "diamond", ORANGE, label, i, 100, 34)
                    prev_bottom = cy + 34
                    onf = step.get("anchor_on_fail", "abort")
                    if onf == "abort":
                        cv.create_line(CX + 100, cy, 445, cy, fill=RED, width=2, arrow=tk.LAST)
                        cv.create_rectangle(445, cy - 20, 650, cy + 20, fill=RED, outline=RED)
                        cv.create_text(547, cy, text="หยุดจอ + รีเซ็ตเกม", fill="#fff", font=("Segoe UI", 9))
                        cv.create_text(420, cy - 11, text="No", fill=GRAY, font=("Segoe UI", 8))
                    elif onf == "skip":
                        nx = cys[i + 1] if i + 1 < n else ye
                        cv.create_line(CX + 100, cy, 430, cy, 430, nx, CX + 92, nx,
                                       fill=ORANGE, width=2, arrow=tk.LAST)
                        cv.create_text(440, cy - 11, text="No→ข้าม", fill=ORANGE, font=("Segoe UI", 8), anchor="w")
                    elif onf == "retry":
                        target = step.get("anchor_retry_target")
                        limit = step.get("anchor_retry_limit", 3)
                        if target is not None and 0 <= int(target) < n:
                            ty = cys[int(target)]
                            bulge = CX + 240
                            cv.create_line(CX + 100, cy, bulge, cy, bulge, ty, CX + 92, ty,
                                          fill=GOLD, width=2, arrow=tk.LAST, dash=(5, 3))
                            cv.create_text(bulge + 8, (cy + ty) // 2,
                                          text=f"No→วนขั้น {int(target) + 1} (สูงสุด {limit} รอบ)",
                                          fill=GOLD, font=("Segoe UI", 8), anchor="w")
                        else:
                            cv.create_text(CX + 108, cy, text="⚠ No→วนกลับ (ยังไม่ตั้งขั้นเป้าหมาย!)",
                                          fill=RED, font=("Segoe UI", 8), anchor="w")
                    else:
                        cv.create_text(CX + 108, cy, text="No→กดเลย", fill=BLUE, font=("Segoe UI", 8), anchor="w")
                else:
                    down(prev_bottom, cy - 22)
                    shape(CX, cy, "rect", BLUE, label, i, 88, 22)
                    prev_bottom = cy + 22
            down(prev_bottom, ye - 20)
            shape(CX, ye, "pill", GREEN, "จบ → บัญชีถัดไป", -1, 95, 20)
            bb = cv.bbox("all")
            if bb:
                cv.configure(scrollregion=(0, 0, max(bb[2] + 20, 720), bb[3] + 20))

        draw()

    def open_step_anchor_setup(self):
        """เลือกพื้นที่ anchor เอง (ลากกรอบบนภาพจริง) — แยกจากจุดกด
        ใช้ตอนจุดกดอยู่บนบริเวณที่ขยับได้ (เช่นตัวละครหน้า Home) แล้วอยากยืนยันหน้าด้วยจุดนิ่งแทน"""
        if self.macro_running:
            messagebox.showwarning("คำเตือน", "หยุดมาโครก่อนตั้งค่า", parent=self)
            return
        selection = self.step_listbox.curselection()
        if not selection:
            messagebox.showwarning("ยังไม่ได้เลือกสเต็ป", "คลิกเลือกสเต็ป tap/swipe ในลิสต์ซ้ายก่อน")
            return
        idx = selection[0]
        step = self.macro_steps[idx]
        if step.get("type") not in ("tap", "swipe"):
            messagebox.showwarning("ใช้ได้เฉพาะ tap/swipe", "Anchor ใช้กับสเต็ป tap/swipe เท่านั้น")
            return
        try:
            tap_x, tap_y = int(float(step.get("x"))), int(float(step.get("y")))
        except (TypeError, ValueError):
            tap_x, tap_y = None, None

        devices = self.get_selected_devices() or self.controller.get_connected_devices()
        if not devices:
            messagebox.showerror("ไม่พบอุปกรณ์", "ต้องมี Emulator เชื่อมต่อ + เปิดหน้าที่จะอัด anchor ไว้ก่อน")
            return

        import cv2, numpy as np, base64
        dialog = tk.Toplevel(self)
        dialog.title(f"🖼️ เลือกพื้นที่ Anchor — สเต็ป {idx+1}")
        dialog.configure(bg=BG_DARK)
        dialog.transient(self)
        dialog.grab_set()

        state = {"orig": None, "bytes": None, "sx": 1.0, "rect_id": None,
                 "region": None, "rect_shape": None}
        temp_disp = os.path.join(self.templates_dir, "anchor_setup_disp.png")

        def on_close():
            try:
                if os.path.exists(temp_disp):
                    os.remove(temp_disp)
            except Exception:
                pass
            dialog.grab_release()
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW", on_close)

        left = tk.Frame(dialog, bg=BG_DARK); left.pack(side="left", padx=15, pady=15)
        canvas = tk.Canvas(left, width=800, height=450, bg="#000000", highlightthickness=1, highlightbackground=BG_PANEL)
        canvas.pack()
        tk.Label(left, text="🔴 จุดแดง = ตำแหน่งที่จะกด | ลากกรอบเขียวครอบ 'จุดนิ่งที่ใช้ยืนยันหน้า' (ปุ่ม/ไอคอน/ข้อความ/เลข — อย่าเอาตัวละครที่ขยับ)",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), wraplength=790, justify="left").pack(anchor="w", pady=(6, 0))

        right = tk.Frame(dialog, bg=BG_DARK, padx=15, pady=15); right.pack(side="right", fill="both", expand=True)
        tk.Label(right, text="📱 Emulator:", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        dev_var = tk.StringVar(value=devices[0])
        ttk.Combobox(right, textvariable=dev_var, values=devices, state="readonly").pack(fill="x", pady=(2, 10))
        tk.Label(right, text=f"สเต็ป {idx+1}: {step.get('desc','')}\nจุดกด: ({tap_x},{tap_y})",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 8))
        status = tk.Label(right, text="ลากกรอบครอบจุดนิ่ง แล้วกด 'ทดสอบ match'", bg=BG_DARK, fg=ACCENT_ORANGE,
                          font=("Segoe UI", 9), wraplength=240, justify="left")
        status.pack(fill="x", pady=10)

        # โหมด 'กดตรงที่เจอภาพ': ให้ลากกรอบเขียวครอบ 'ตัวปุ่ม' เอง แล้วเวลารันจะกดตรงที่เจอปุ่ม
        # (ตามปุ่ม/ป็อปอัพที่เลื่อนตำแหน่งได้) แทนพิกัดแดงตายตัว — แม่นกว่ามากในหน้ารับของ
        anchor_tap_var = tk.BooleanVar(value=bool(step.get("anchor_tap")))
        self.make_checkbutton(right, "🎯 กดตรงที่เจอภาพนี้ (ตามปุ่มที่ขยับ ไม่ยึดพิกัดแดง)",
                              anchor_tap_var, bg=BG_DARK).pack(anchor="w", pady=(0, 4))
        tk.Label(right, text="เปิดโหมดนี้: ลากกรอบเขียวครอบ 'ปุ่มที่จะกด' โดยตรง", bg=BG_DARK,
                 fg=FG_MUTED, font=("Segoe UI", 8, "italic"), wraplength=240, justify="left").pack(anchor="w")

        def render():
            img = state["orig"]
            if img is None:
                return
            oh, ow = img.shape[:2]
            sc = min(800.0 / ow, 450.0 / oh)
            state["sx"] = sc
            disp = cv2.resize(img, (int(ow * sc), int(oh * sc)))
            dh, dw = disp.shape[:2]
            cv2.imwrite(temp_disp, disp)
            canvas.configure(width=dw, height=dh)
            photo = tk.PhotoImage(file=temp_disp)
            canvas.delete("all")
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.image = photo
            state["rect_id"] = None
            # จุดกด (แดง)
            if tap_x is not None:
                mx, my = tap_x * sc, tap_y * sc
                canvas.create_oval(mx - 6, my - 6, mx + 6, my + 6, outline="#ff3b3b", width=2)
                canvas.create_line(mx - 12, my, mx + 12, my, fill="#ff3b3b", width=1)
                canvas.create_line(mx, my - 12, mx, my + 12, fill="#ff3b3b", width=1)
            # กรอบ anchor ที่เลือกไว้ (เขียว)
            reg = state["region"]
            if reg:
                canvas.create_rectangle(reg["x"] * sc, reg["y"] * sc,
                                        (reg["x"] + reg["w"]) * sc, (reg["y"] + reg["h"]) * sc,
                                        outline=ACCENT_GREEN, width=2)

        def capture():
            ok, data = self.controller.capture_screenshot_bytes(dev_var.get())
            if not ok:
                status.configure(text=f"❌ จับภาพล้มเหลว: {data}", fg=ACCENT_RED); return
            state["bytes"] = data
            state["orig"] = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            render()
            status.configure(text="📸 จับภาพแล้ว — ลากกรอบครอบจุดนิ่ง", fg=ACCENT_GREEN)

        press = {"x": 0, "y": 0}

        def on_press(e):
            press["x"], press["y"] = e.x, e.y

        def on_motion(e):
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
            state["rect_id"] = canvas.create_rectangle(press["x"], press["y"], e.x, e.y, outline=ACCENT_ORANGE, width=2)

        def on_release(e):
            if state["orig"] is None:
                status.configure(text="จับภาพก่อน", fg=ACCENT_RED); return
            sx = state["sx"] or 1.0
            x1, y1 = min(press["x"], e.x), min(press["y"], e.y)
            x2, y2 = max(press["x"], e.x), max(press["y"], e.y)
            rx, ry = int(x1 / sx), int(y1 / sx)
            rw, rh = int((x2 - x1) / sx), int((y2 - y1) / sx)
            if rw < 8 or rh < 8:
                status.configure(text="กรอบเล็กเกินไป ลากใหม่", fg=ACCENT_RED); return
            state["region"] = {"x": rx, "y": ry, "w": rw, "h": rh}
            render()
            status.configure(text=f"✅ พื้นที่ anchor: x={rx} y={ry} w={rw} h={rh}\nกด 'ทดสอบ match' หรือ 'บันทึก'", fg=ACCENT_GREEN)

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_motion)
        canvas.bind("<ButtonRelease-1>", on_release)

        def _crop_bytes():
            reg = state["region"]
            if not reg or state["orig"] is None:
                return None
            img = state["orig"]
            c = img[reg["y"]:reg["y"] + reg["h"], reg["x"]:reg["x"] + reg["w"]]
            if c.size == 0:
                return None
            return cv2.imencode(".png", c)[1].tobytes()

        def test_match():
            tb = _crop_bytes()
            if tb is None:
                status.configure(text="ยังไม่ได้ลากกรอบ anchor", fg=ACCENT_RED); return
            ok, data = self.controller.capture_screenshot_bytes(dev_var.get())
            if not ok:
                status.configure(text="แคปจอทดสอบไม่ได้", fg=ACCENT_RED); return
            found, _x, _y, msg = self.controller.match_template_bytes(data, tb, 0.8)
            if found:
                status.configure(text=f"✅ match ผ่าน! {msg}\nพื้นที่นี้ใช้ได้ กด 'บันทึก'", fg=ACCENT_GREEN)
            else:
                status.configure(text=f"⚠️ {msg}\nถ้าจอไม่เปลี่ยนแต่ match ต่ำ = เลือกจุดที่ขยับ ลองเลือกจุดนิ่งกว่านี้", fg=ACCENT_ORANGE)

        # รายชื่อขั้นทั้งหมด (สำหรับตัวเลือก 'วนกลับไปขั้นที่...') — dialog เป็น modal (grab_set แล้ว)
        # self.macro_steps จะไม่ถูกแก้จากที่อื่นระหว่างเปิดอยู่ จึงสร้าง label ครั้งเดียวตรงนี้ได้เลย
        target_labels = [f"ขั้น {i + 1}: {(s.get('desc') or s.get('type', ''))[:30]}"
                         for i, s in enumerate(self.macro_steps)]

        def save_and_close():
            tb = _crop_bytes()
            if tb is None:
                status.configure(text="ยังไม่ได้ลากกรอบ anchor", fg=ACCENT_RED); return
            step["anchor_img"] = base64.b64encode(tb).decode("ascii")
            step["anchor_region"] = dict(state["region"])  # เก็บไว้เผื่อแก้ซ้ำ (โชว์กรอบเดิม)
            step["anchor_tap"] = bool(anchor_tap_var.get())  # กดตรงที่เจอภาพ (ตามปุ่มที่ขยับ)
            try:
                step["anchor_timeout"] = max(0.0, float(timeout_var.get()))
            except (TypeError, ValueError):
                step["anchor_timeout"] = 8.0
            step["anchor_on_fail"] = ANCHOR_ONFAIL_FROM_LABEL.get(onfail_var.get(), "abort")
            if step["anchor_on_fail"] == "retry":
                sel_label = retry_target_var.get()
                if sel_label in target_labels:
                    step["anchor_retry_target"] = target_labels.index(sel_label)
                try:
                    step["anchor_retry_limit"] = max(1, int(float(retry_limit_var.get())))
                except (TypeError, ValueError):
                    step["anchor_retry_limit"] = 3
            else:
                step.pop("anchor_retry_target", None)
                step.pop("anchor_retry_limit", None)
            step.setdefault("anchor_threshold", 0.8)
            self.refresh_listbox()
            self.step_listbox.selection_set(idx)
            self.write_log(f"📷 ตั้งพื้นที่ Anchor สเต็ป {idx+1} แล้ว (อย่าลืมกด 'บันทึกโปรไฟล์' เพื่อเก็บลงไฟล์)", "success")
            on_close()

        # ตั้งค่า anchor: ไม่เจอภาพแล้วทำยังไง + รอสูงสุดกี่วิ — ใช้ทำ 'if แบบลูกโซ่ skip' หรือ 'วนกลับลองใหม่'
        cfgf = tk.Frame(right, bg=BG_DARK); cfgf.pack(fill="x", pady=(10, 0))
        tk.Label(cfgf, text="ถ้าไม่เจอภาพ:", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        onfail_var = tk.StringVar(value=ANCHOR_ONFAIL_TO_LABEL.get(step.get("anchor_on_fail", "abort"), ANCHOR_ONFAIL_LABELS[0][1]))
        ttk.Combobox(cfgf, textvariable=onfail_var, state="readonly", width=22,
                     values=[l for _v, l in ANCHOR_ONFAIL_LABELS]).grid(row=0, column=1, sticky="w", padx=6)
        tk.Label(cfgf, text="รอสูงสุด(วิ):", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(5, 0))
        timeout_var = tk.StringVar(value=str(step.get("anchor_timeout", 8.0)))
        tk.Entry(cfgf, textvariable=timeout_var, width=8, bg=BG_INPUT, fg=FG_WHITE,
                 insertbackground=FG_WHITE, relief="flat").grid(row=1, column=1, sticky="w", padx=6, pady=(5, 0))

        # กล่อง 'วนกลับไปขั้นที่...' — โชว์เฉพาะตอนเลือกนโยบาย retry (ซ่อน/โชว์ผ่าน trace ของ onfail_var)
        retryf = tk.Frame(right, bg=BG_DARK)
        tk.Label(retryf, text="🔁 วนกลับไปขั้นที่:", bg=BG_DARK, fg="#FBBF24", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        cur_target = step.get("anchor_retry_target")
        retry_target_var = tk.StringVar(value=(
            target_labels[int(cur_target)] if (cur_target is not None and 0 <= int(cur_target) < len(target_labels))
            else (target_labels[0] if target_labels else "")))
        ttk.Combobox(retryf, textvariable=retry_target_var, state="readonly", width=28,
                     values=target_labels).grid(row=0, column=1, sticky="w", padx=6)
        tk.Label(retryf, text="วนได้สูงสุด(รอบ):", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(5, 0))
        retry_limit_var = tk.StringVar(value=str(step.get("anchor_retry_limit", 3)))
        tk.Entry(retryf, textvariable=retry_limit_var, width=8, bg=BG_INPUT, fg=FG_WHITE,
                 insertbackground=FG_WHITE, relief="flat").grid(row=1, column=1, sticky="w", padx=6, pady=(5, 0))
        tk.Label(retryf, text="ครบรอบแล้วยังไม่เจอ จะหยุดจอนี้เอง กันวนไม่รู้จบ", bg=BG_DARK, fg=FG_MUTED,
                 font=("Segoe UI", 8, "italic"), wraplength=240, justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))

        def _toggle_retry_fields(*_a):
            if onfail_var.get() == ANCHOR_ONFAIL_TO_LABEL.get("retry"):
                retryf.pack(fill="x", pady=(8, 0), after=cfgf)
            else:
                retryf.pack_forget()
        onfail_var.trace_add("write", _toggle_retry_fields)
        _toggle_retry_fields()

        tk.Label(right, text="🔀 if แบบลูกโซ่: ตั้ง 'ข้ามสเต็ปนี้ไป' + 'รอสั้น 1-2วิ' หลายสเต็ปต่อกัน (เจอแบบไหนกดแบบนั้น)",
                 bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 8, "italic"), wraplength=240, justify="left").pack(anchor="w", pady=(3, 0))

        btns = tk.Frame(right, bg=BG_DARK); btns.pack(fill="x", pady=(14, 0))
        ModernButton(btns, text="📸 จับภาพใหม่", command=capture, variant="primary").pack(fill="x", pady=3)
        ModernButton(btns, text="🔍 ทดสอบ match", command=test_match, variant="accent").pack(fill="x", pady=3)
        ModernButton(btns, text="💾 บันทึก Anchor", command=save_and_close, variant="primary").pack(fill="x", pady=3)

        # โหลดกรอบเดิม (ถ้าเคยตั้ง region ไว้) — เก็บ region ล่าสุดในสเต็ปด้วย เผื่อแก้ซ้ำ
        if step.get("anchor_region"):
            state["region"] = dict(step["anchor_region"])
        dialog.after(200, capture)

    def capture_step_anchor(self, box_w=170, box_h=90):
        """อัด 'ภาพ anchor' ให้สเต็ปที่เลือก — แคปจอจริงแล้วครอปรอบจุดที่กด
        ตอนรัน ระบบจะ 'รอจนเห็นภาพนี้บนจอ' ก่อนกด (จอช้า=รอ, จอไม่ตรง=หยุดกันมั่ว)"""
        import base64
        selection = self.step_listbox.curselection()
        if not selection:
            messagebox.showwarning("ยังไม่ได้เลือกสเต็ป", "คลิกเลือกสเต็ปในลิสต์ซ้ายก่อน แล้วค่อยกดอัด Anchor")
            return
        idx = selection[0]
        step = self.macro_steps[idx]
        t = step.get("type", "")
        if t not in ("tap", "swipe"):
            messagebox.showwarning("ใช้ได้เฉพาะ tap/swipe", "Anchor ใช้กับสเต็ป tap หรือ swipe (จุดที่กด) เท่านั้น")
            return
        try:
            cx = int(float(step.get("x")))
            cy = int(float(step.get("y")))
        except (TypeError, ValueError):
            messagebox.showerror("ไม่มีพิกัด", "สเต็ปนี้ไม่มีพิกัด x,y ที่ถูกต้อง")
            return

        devices = self.get_selected_devices() or self.controller.get_connected_devices()
        if not devices:
            messagebox.showerror("ไม่พบอุปกรณ์", "ต้องมี Emulator เชื่อมต่อ + เปิดหน้าที่จะอัดภาพไว้ก่อน")
            return
        device = devices[0]
        ok, data = self.controller.capture_screenshot_bytes(device)
        if not ok:
            messagebox.showerror("แคปจอไม่สำเร็จ", f"อ่านหน้าจอ [{device}] ไม่ได้: {data}")
            return
        try:
            import cv2, numpy as np
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            h, w = img.shape[:2]
            x1 = max(0, min(w - box_w, cx - box_w // 2))
            y1 = max(0, min(h - box_h, cy - box_h // 2))
            crop = img[y1:y1 + box_h, x1:x1 + box_w]
            enc = cv2.imencode(".png", crop)[1].tobytes()
            step["anchor_img"] = base64.b64encode(enc).decode("ascii")
            step.setdefault("anchor_timeout", 8.0)
            step.setdefault("anchor_threshold", 0.8)
            step.setdefault("anchor_on_fail", "abort")
        except Exception as e:
            messagebox.showerror("ครอปภาพล้มเหลว", str(e))
            return

        self.refresh_listbox()
        self.step_listbox.selection_set(idx)
        self.step_listbox.see(idx)
        self.write_log(f"📷 อัด Anchor ให้สเต็ป {idx+1} แล้ว (รอจนเห็นภาพนี้ก่อนกด | timeout 8วิ | ไม่เจอ=หยุดจอ)", "success")

    def clear_step_anchor(self):
        """ลบภาพ anchor ออกจากสเต็ปที่เลือก (กลับไปกดตามพิกัด/เวลาแบบเดิม)"""
        selection = self.step_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        step = self.macro_steps[idx]
        if not step.get("anchor_img"):
            return
        for k in ("anchor_img", "anchor_region", "anchor_tap", "anchor_timeout", "anchor_threshold",
                  "anchor_on_fail", "anchor_retry_target", "anchor_retry_limit"):
            step.pop(k, None)
        self.refresh_listbox()
        self.step_listbox.selection_set(idx)
        self.write_log(f"ลบ Anchor ของสเต็ป {idx+1} แล้ว", "warning")

    def delete_step(self):
        selection = self.step_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        self.macro_steps.pop(idx)
        self.refresh_listbox()
        
        # เลือกขั้นตอนตัวถัดไปในรายการให้อัตโนมัติเพื่อความสะดวก
        if self.macro_steps:
            new_idx = min(idx, len(self.macro_steps) - 1)
            self.step_listbox.selection_set(new_idx)
            self.on_listbox_select(None)
        self.write_log(f"ลบขั้นตอนลำดับที่ {idx+1} ออกแล้ว", "warning")

    def move_step(self, direction):
        """สลับตำแหน่งขั้นตอนการทำงานย้ายขึ้น/ลง"""
        selection = self.step_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        new_idx = idx + direction
        
        if 0 <= new_idx < len(self.macro_steps):
            # สลับตำแหน่งข้อมูลใน Array
            self.macro_steps[idx], self.macro_steps[new_idx] = self.macro_steps[new_idx], self.macro_steps[idx]
            self.refresh_listbox()
            self.step_listbox.selection_set(new_idx)
            self.step_listbox.see(new_idx)

    # --- เครื่องมือควบคุมการทำสคริปต์มาโครบอท ---
    def start_macro_flow(self):
        if self.is_paused_waiting_for_next_set:
            # ดำเนินการต่อจากชุดเดิมที่หยุดพักไว้
            self.is_paused_waiting_for_next_set = False
            self.run_macro_btn.configure(state="disabled", bg=BG_INPUT)
            self.stop_macro_btn.configure(state="normal")
            
            # เริ่มทำงานบอทแบบ Thread (ดำเนินการรันชุดถัดไป)
            self.macro_thread = threading.Thread(
                target=self.run_macro_task_resume,
                daemon=True
            )
            self.macro_thread.start()
            return

        devices = self.get_selected_devices()
        if not devices:
            return

        if not self.macro_steps:
            messagebox.showwarning("คำเตือน", "ไม่มีขั้นตอนในสคริปต์เลย! กรุณาเพิ่มขั้นตอนก่อนเปิดการทำงานบอท")
            return

        # ดึงบัญชีที่เลือก
        checked_accounts = [acc for acc in self.accounts if acc.get("checked", True)]
        profile_name = self.profile_cb.get() or "กำหนดเอง"
        self._active_profile_name = profile_name  # สแนปช็อตให้ worker/รายงานปัญหาใช้ (อ่าน Tk var ข้ามเธรดไม่ปลอดภัย)

        # ===== ตรวจ checkpoint: เสนอ 'รันต่อจากที่ค้าง' =====
        is_resume = False
        if checked_accounts:
            cp = self._load_run_checkpoint()
            if cp and cp.get("macro_signature") == self._macro_signature():
                statuses = cp.get("status_by_email", {})
                done = {em for em, st in statuses.items() if st == "completed"}
                pending_accounts = [a for a in checked_accounts
                                    if (a.get("email") or "").strip().lower() not in done]
                if done and pending_accounts:
                    total = len(statuses) or len(checked_accounts)
                    ans = messagebox.askyesnocancel(
                        "พบการรันค้าง",
                        f"พบ checkpoint ของ '{cp.get('profile_name','')}'\n"
                        f"เสร็จไปแล้ว {len(done)}/{total} ไอดี — เหลือ {len(pending_accounts)} ไอดี\n\n"
                        f"• Yes = รันต่อจากที่ค้าง (เฉพาะ {len(pending_accounts)} ไอดีที่เหลือ)\n"
                        f"• No = เริ่มใหม่ทั้งหมด\n"
                        f"• Cancel = ยกเลิก",
                    )
                    if ans is None:
                        return
                    if ans:
                        checked_accounts = pending_accounts
                        self.run_checkpoint = cp
                        self.run_checkpoint_lock = threading.Lock()
                        is_resume = True
                    else:
                        self._clear_run_checkpoint()

        if is_resume:
            confirm = True
        elif checked_accounts:
            confirm = messagebox.askyesno(
                "ยืนยันเปิดบอท",
                f"ยืนยันรันบอทมาโครโปรไฟล์ '{profile_name}' โดยกระจายบัญชี {len(checked_accounts)} ไอดี\n"
                f"ลงบน Emulator ทั้งหมด {len(devices)} จอ (ทำงานพร้อมกันแบบคู่ขนาน) ใช่หรือไม่?"
            )
        else:
            confirm = messagebox.askyesno(
                "ยืนยันเปิดบอท",
                f"คำเตือน: คุณยังไม่ได้ระบุหรือเลือกบัญชีในแท็บจัดการบัญชี ระบบจะรันสคริปต์ 1 รอบแบบไม่มีตัวแปรแทนที่\n"
                f"ยืนยันต้องการรันมาโครรอบเดียวต่อหรือไม่?"
            )

        if not confirm:
            return

        # บันทึกข้อมูลตั้งต้นสำหรับการรันแบบเซ็ต
        self.remaining_accounts = checked_accounts.copy()
        self.active_devices_for_run = devices.copy()

        # เริ่มเก็บผลลัพธ์การรันรอบใหม่ (สำหรับสรุปผล + export + รันซ้ำที่พลาด)
        self.run_results = []
        self.run_results_lock = threading.Lock()
        # เก็บผลอ่านเพชรระหว่างรัน (จาก step 'อ่านเพชร') เพื่อ export/push เข้าเว็บตอนจบรัน
        self.run_diamond_rows = []
        self.run_diamond_lock = threading.Lock()

        # สร้าง checkpoint ใหม่ (เฉพาะรันสด ไม่ใช่รันต่อ และต้องมีบัญชี)
        if not is_resume and checked_accounts:
            from datetime import datetime
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.run_checkpoint_lock = threading.Lock()
            self.run_checkpoint = {
                "macro_signature": self._macro_signature(),
                "profile_name": profile_name,
                "mode": ("sequential" if self.run_sequentially.get()
                         else "sets" if self.pause_between_sets.get() else "parallel"),
                "devices": devices.copy(),
                "started_at": now,
                "updated_at": now,
                "order": [a.get("email") for a in checked_accounts if a.get("email")],
                "status_by_email": {(a.get("email") or "").strip().lower(): "pending"
                                    for a in checked_accounts if a.get("email")},
                "last_device_by_email": {},
            }
            self._write_checkpoint_file()
        elif not checked_accounts:
            self.run_checkpoint = None

        # ล็อคปุ่มสับเปลี่ยนสถานะ
        self.macro_running = True
        self.run_macro_btn.configure(state="disabled", bg=BG_INPUT)
        self.stop_macro_btn.configure(state="normal")
        self.update_status_summary()
        
        # เริ่มทำงานบอทแบบ Thread (ทำงานเบื้องหลัง)
        self.macro_thread = threading.Thread(
            target=self.run_macro_task,
            args=(devices, checked_accounts),
            daemon=True
        )
        self.macro_thread.start()

    def stop_macro_flow(self):
        if self.macro_running or self.is_paused_waiting_for_next_set:
            self.macro_running = False
            self.update_status_summary()
            was_paused = self.is_paused_waiting_for_next_set
            self.is_paused_waiting_for_next_set = False
            self.remaining_accounts = []
            self.write_log("⚠️ ส่งสัญญาณยกเลิก! กำลังหยุดการทำงานมาโครโปรดรอสักครู่...", "warning")
            if was_paused:
                self.run_macro_btn.configure(state="normal", bg=ACCENT_GREEN, text="รันมาโคร")
                self.stop_macro_btn.configure(state="disabled")
                self.write_log("⏹️ หยุดการทำงานของบอทและเคลียร์คิวเรียบร้อยแล้ว", "success")
            # ถ้ายังมี checkpoint ค้าง โชว์ป้าย 'รันต่อได้' ไว้บนปุ่ม
            cp = getattr(self, "run_checkpoint", None) or self._load_run_checkpoint()
            if cp:
                statuses = cp.get("status_by_email", {})
                remaining = [em for em, st in statuses.items() if st != "completed"]
                if remaining:
                    self.run_macro_btn.configure(text=f"▶️ รันต่อได้ (เหลือ {len(remaining)})")

    # ===== ระบบ Checkpoint รันต่อจากที่ค้าง (resume) =====
    def _macro_signature(self):
        """ลายเซ็นของสคริปต์มาโครปัจจุบัน ใช้เช็คว่า checkpoint มาจากสคริปต์เดียวกันไหม"""
        try:
            raw = json.dumps(self.macro_steps, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(raw.encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def _load_run_checkpoint(self):
        """อ่าน checkpoint จากไฟล์ (คืน dict หรือ None)"""
        try:
            if os.path.exists(self.run_checkpoint_file):
                with open(self.run_checkpoint_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _write_checkpoint_file(self):
        """เขียน self.run_checkpoint ลงไฟล์ (ผู้เรียกต้องถือ lock เองถ้าจำเป็น)"""
        cp = getattr(self, "run_checkpoint", None)
        if not cp:
            return
        from datetime import datetime
        try:
            cp["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.run_checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(cp, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.write_log(f"⚠️ เขียน checkpoint ไม่สำเร็จ: {e}", "warning")

    def _clear_run_checkpoint(self):
        """ลบ checkpoint ทั้งในหน่วยความจำและไฟล์ (เรียกเมื่อรันครบทุกบัญชี)"""
        self.run_checkpoint = None
        try:
            if os.path.exists(self.run_checkpoint_file):
                os.remove(self.run_checkpoint_file)
        except Exception:
            pass

    def _mark_checkpoint_account(self, email, status, device=""):
        """อัปเดตสถานะบัญชีหนึ่งใน checkpoint แล้วเขียนไฟล์ทันที (thread-safe)
        status: 'completed' = สำเร็จไม่ต้องรันซ้ำ, อย่างอื่น = ค้าง/พลาด จะถูกรันต่อรอบหน้า"""
        cp = getattr(self, "run_checkpoint", None)
        if not cp or not email:
            return
        em = str(email).strip().lower()
        lock = getattr(self, "run_checkpoint_lock", None)
        if lock is not None:
            with lock:
                cp.setdefault("status_by_email", {})[em] = status
                if device:
                    cp.setdefault("last_device_by_email", {})[em] = device
                self._write_checkpoint_file()
        else:
            cp.setdefault("status_by_email", {})[em] = status
            if device:
                cp.setdefault("last_device_by_email", {})[em] = device
            self._write_checkpoint_file()

    def _check_startup_checkpoint(self):
        """ตอนเปิดโปรแกรม ถ้าพบ checkpoint ค้าง ให้แจ้งเตือน + เปลี่ยนป้ายปุ่มรัน"""
        cp = self._load_run_checkpoint()
        if not cp:
            return
        statuses = cp.get("status_by_email", {})
        remaining = [em for em, st in statuses.items() if st != "completed"]
        if remaining and hasattr(self, "run_macro_btn"):
            prof = cp.get("profile_name", "")
            self.write_log(
                f"💾 พบการรันค้างของ '{prof}' — เหลือ {len(remaining)} ไอดี "
                f"กด 'รันมาโคร' เพื่อเลือกรันต่อหรือเริ่มใหม่", "warning")
            try:
                self.run_macro_btn.configure(text=f"▶️ รันต่อได้ (เหลือ {len(remaining)})")
            except Exception:
                pass

    def run_macro_task(self, devices, checked_accounts):
        import queue
        from concurrent.futures import ThreadPoolExecutor

        try:
            # ตรวจสอบว่าต้องไฮไลท์ขั้นตอนที่ลิสต์บ็อกซ์หรือไม่ (ทำเฉพาะตอนรันจอเดียวเพื่อไม่ให้กะพริบแย่งกัน)
            highlight = (len(devices) == 1)

            stagger_delay = 0.0
            if hasattr(self, 'use_stagger_delay') and self.use_stagger_delay.get():
                if hasattr(self, 'stagger_delay_entry'):
                    try:
                        stagger_delay = float(self.stagger_delay_entry.get().strip() or "0")
                    except ValueError:
                        stagger_delay = 0.0

            def sleep_stagger(dev, idx):
                delay = idx * stagger_delay
                if delay > 0 and self.macro_running:
                    self.write_log(f"⏳ [{dev}] รอหน่วงเวลาเริ่มต้นรันบอท {delay:.1f} วินาที...", "info")
                    start_time = time.time()
                    while time.time() - start_time < delay:
                        if not self.macro_running:
                            return False
                        time.sleep(0.2)
                return True

            if self.run_sequentially.get():
                pairs = build_sequential_macro_pairs(devices, checked_accounts)
                self.write_log(
                    f"Sequential: เริ่มรันทีละจอจนจบทั้งหมด {len(pairs)} งาน "
                    f"(ไม่ใช้หน่วงเริ่มหลายจอและไม่รันคู่ขนาน)",
                    "warning",
                )

                for dev, acc, pair_idx, pair_total in pairs:
                    if not self.macro_running:
                        break

                    if acc:
                        email = acc.get("email")
                        self.write_log(
                            f"Sequential: เริ่มบัญชี {pair_idx + 1}/{pair_total} บน {dev}: {email}",
                            "warning",
                        )
                    else:
                        self.write_log(
                            f"Sequential: เริ่มจอ {pair_idx + 1}/{pair_total} บน {dev}",
                            "warning",
                        )

                    self._collect_result(self.execute_device_macro(dev, acc, highlight))

                    if self.macro_running:
                        if acc:
                            self.write_log(
                                f"Sequential: บัญชี {pair_idx + 1}/{pair_total} เสร็จแล้ว",
                                "success",
                            )
                        else:
                            self.write_log(
                                f"Sequential: จอ {pair_idx + 1}/{pair_total} เสร็จแล้ว",
                                "success",
                            )

                        if pair_idx < pair_total - 1:
                            between_pause = random.uniform(8, 20)
                            self.write_log(f"⏸️ พักก่อน account ถัดไป {between_pause:.1f} วินาที...", "info")
                            pause_start = time.time()
                            while time.time() - pause_start < between_pause and self.macro_running:
                                time.sleep(0.2)

                if self.macro_running:
                    self.write_log("🎉 Sequential: รันครบทุกบัญชีและทุกหน้าจอแล้ว!", "success")
                    messagebox.showinfo(
                        "เสร็จสิ้นการทำงาน",
                        "Sequential mode ทำงานตามสคริปต์มาโครครบแล้ว!",
                    )
                return

            if not checked_accounts:
                self.write_log(f"🏁 เริ่มต้นการรันมาโคร 1 รอบพร้อมกันบน Emulator ทั้งหมด {len(devices)} จอ (ไม่มีบัญชีไอดี)...", "warning")
                
                # รันมาโครพร้อมกันทีละจอใน ThreadPool
                def worker(dev):
                    idx = devices.index(dev)
                    if sleep_stagger(dev, idx):
                        self._collect_result(self.execute_device_macro(dev, None, highlight))

                with ThreadPoolExecutor(max_workers=len(devices)) as executor:
                    executor.map(worker, devices)
                
                if self.macro_running:
                    self.write_log("🎉 บอทรันมาโครเสร็จสิ้นครบทุกบัญชีและทุกหน้าจอแล้ว!", "success")
                    messagebox.showinfo("เสร็จสิ้นการทำงาน", "การทำงานตามสคริปต์มาโครเสร็จสมบูรณ์เรียบร้อยแล้ว!")
            else:
                if self.pause_between_sets.get():
                    # โหมดรันทีละชุด (Pause between sets)
                    # ดึงชุดแรกมาทำงาน
                    batch_size = len(devices)
                    current_batch = self.remaining_accounts[:batch_size]
                    self.remaining_accounts = self.remaining_accounts[batch_size:]
                    
                    self.write_log(f"🏁 เริ่มรันชุดบัญชีคู่ขนานจำนวน {len(current_batch)} ไอดี ลงบน Emulator...", "warning")
                    
                    # จับคู่ อุปกรณ์ กับ บัญชี
                    paired = list(zip(devices, current_batch))
                    
                    def batch_worker(pair):
                        dev, acc = pair
                        email = acc.get("email")
                        idx = paired.index(pair)
                        if sleep_stagger(dev, idx):
                            if self.macro_running:
                                self.write_log(f"🔄 [{dev}] หยิบบัญชี: {email} มารันมาโคร...", "warning")
                                self._collect_result(self.execute_device_macro(dev, acc, highlight))

                    with ThreadPoolExecutor(max_workers=len(paired)) as executor:
                        executor.map(batch_worker, paired)
                        
                    if self.macro_running:
                        if self.remaining_accounts:
                            self.is_paused_waiting_for_next_set = True
                            self.write_log(f"⏸️ รันชุดปัจจุบันเสร็จแล้ว (เหลืออีก {len(self.remaining_accounts)} ไอดี) กรุณาตรวจสอบหน้าจอ Emulator แล้วกด 'รันบัญชีชุดถัดไป'", "warning")
                            self.after(0, lambda: self.run_macro_btn.configure(
                                state="normal", 
                                bg=ACCENT_BLUE, 
                                text=f"▶️ รันบัญชีชุดถัดไป (เหลือ {len(self.remaining_accounts)} ไอดี)"
                            ))
                        else:
                            self.write_log("🎉 บอทรันมาโครเสร็จสิ้นครบทุกบัญชีและทุกหน้าจอแล้ว!", "success")
                            messagebox.showinfo("เสร็จสิ้นการทำงาน", "การทำงานตามสคริปต์มาโครเสร็จสมบูรณ์เรียบร้อยแล้ว!")
                else:
                    # โหมดรันปกติแบบคิวต่อเนื่อง
                    self.write_log(f"🏁 เริ่มต้นรันบอทมาโครกระจายบัญชี {len(checked_accounts)} ไอดี ลงบน {len(devices)} จอ...", "warning")
                    
                    # สร้าง Queue บัญชี
                    account_queue = queue.Queue()
                    for acc in checked_accounts:
                        account_queue.put(acc)

                    # ตั้งสถานะเริ่มต้นของทุกจอเป็น 'รอคิว' ให้การ์ดความคืบหน้าหน้าแรกเห็นทันทีตอนกดรัน
                    total_accounts = len(checked_accounts)
                    for dev in devices:
                        self._device_run_state[dev] = {"status": "queued", "account_name": "-",
                            "step_idx": 0, "step_total": 0, "step_desc": "รอคิว",
                            "done_count": 0, "total_accounts": total_accounts}

                    # ฟังก์ชันการทำงานของแต่ละจอ
                    def device_worker(dev):
                        idx = devices.index(dev)
                        if not sleep_stagger(dev, idx):
                            return
                        while self.macro_running:
                            try:
                                acc = account_queue.get_nowait()
                            except queue.Empty:
                                break

                            email = acc.get("email")
                            self.write_log(f"🔄 [{dev}] หยิบบัญชี: {email} มารันมาโคร...", "warning")
                            result = self.execute_device_macro(dev, acc, highlight)
                            self._collect_result(result)
                            if result.get("status") == "completed":
                                self._device_run_state[dev]["done_count"] += 1
                            account_queue.task_done()
                        # ไม่มีบัญชีเหลือ (หรือถูกสั่งหยุด) — ปิดสถานะจอนี้ให้ชัดเจน
                        self._device_run_state[dev]["status"] = "done" if self.macro_running else "stopped"
                        self._device_run_state[dev]["step_desc"] = ""

                    with ThreadPoolExecutor(max_workers=len(devices)) as executor:
                        executor.map(device_worker, devices)

                    if self.macro_running:
                        self.write_log("🎉 บอทรันมาโครเสร็จสิ้นครบทุกบัญชีและทุกหน้าจอแล้ว!", "success")
                        messagebox.showinfo("เสร็จสิ้นการทำงาน", "การทำงานตามสคริปต์มาโครเสร็จสมบูรณ์เรียบร้อยแล้ว!")

        except Exception as e:
            self.write_log(f"❌ ระบบประมวลผลมาโครพบปัญหา: {e}", "error")
            messagebox.showerror("ระบบขัดข้อง", f"เกิดข้อผิดพลาดในการรันบอทมาโคร: {e}")
        finally:
            if not self.is_paused_waiting_for_next_set:
                self.macro_running = False
                self.after(0, lambda: self.run_macro_btn.configure(state="normal", bg=ACCENT_GREEN, text="รันมาโคร"))
                self.after(0, lambda: self.stop_macro_btn.configure(state="disabled"))
                self.after(0, self.update_status_summary)
                self.after(0, self.finalize_run_results)

    def run_macro_task_resume(self):
        from concurrent.futures import ThreadPoolExecutor
        try:
            highlight = (len(self.active_devices_for_run) == 1)
            devices = self.active_devices_for_run
            batch_size = len(devices)
            current_batch = self.remaining_accounts[:batch_size]
            self.remaining_accounts = self.remaining_accounts[batch_size:]
            
            self.write_log(f"🏁 รันต่อ: เริ่มรันชุดบัญชีคู่ขนานจำนวน {len(current_batch)} ไอดี ลงบน Emulator...", "warning")

            stagger_delay = 0.0
            if hasattr(self, 'use_stagger_delay') and self.use_stagger_delay.get():
                if hasattr(self, 'stagger_delay_entry'):
                    try:
                        stagger_delay = float(self.stagger_delay_entry.get().strip() or "0")
                    except ValueError:
                        stagger_delay = 0.0

            def sleep_stagger(dev, idx):
                delay = idx * stagger_delay
                if delay > 0 and self.macro_running:
                    self.write_log(f"⏳ [{dev}] รอหน่วงเวลาเริ่มต้นรันบอท {delay:.1f} วินาที...", "info")
                    start_time = time.time()
                    while time.time() - start_time < delay:
                        if not self.macro_running:
                            return False
                        time.sleep(0.2)
                return True
            
            # จับคู่ อุปกรณ์ กับ บัญชี
            paired = list(zip(devices, current_batch))
            
            def batch_worker(pair):
                dev, acc = pair
                email = acc.get("email")
                idx = paired.index(pair)
                if sleep_stagger(dev, idx):
                    if self.macro_running:
                        self.write_log(f"🔄 [{dev}] หยิบบัญชี: {email} มารันมาโคร...", "warning")
                        self._collect_result(self.execute_device_macro(dev, acc, highlight))

            with ThreadPoolExecutor(max_workers=len(paired)) as executor:
                executor.map(batch_worker, paired)

            if self.macro_running:
                if self.remaining_accounts:
                    self.is_paused_waiting_for_next_set = True
                    self.write_log(f"⏸️ รันชุดปัจจุบันเสร็จแล้ว (เหลืออีก {len(self.remaining_accounts)} ไอดี) กรุณาตรวจสอบหน้าจอ Emulator แล้วกด 'รันบัญชีชุดถัดไป'", "warning")
                    self.after(0, lambda: self.run_macro_btn.configure(
                        state="normal", 
                        bg=ACCENT_BLUE, 
                        text=f"▶️ รันบัญชีชุดถัดไป (เหลือ {len(self.remaining_accounts)} ไอดี)"
                    ))
                else:
                    self.write_log("🎉 บอทรันมาโครเสร็จสิ้นครบทุกบัญชีและทุกหน้าจอแล้ว!", "success")
                    messagebox.showinfo("เสร็จสิ้นการทำงาน", "การทำงานตามสคริปต์มาโครเสร็จสมบูรณ์เรียบร้อยแล้ว!")
                    
        except Exception as e:
            self.write_log(f"❌ ระบบประมวลผลมาโครพบปัญหา: {e}", "error")
            messagebox.showerror("ระบบขัดข้อง", f"เกิดข้อผิดพลาดในการรันบอทมาโคร: {e}")
        finally:
            if not self.is_paused_waiting_for_next_set:
                self.macro_running = False
                self.after(0, lambda: self.run_macro_btn.configure(state="normal", bg=ACCENT_GREEN, text="รันมาโคร"))
                self.after(0, lambda: self.stop_macro_btn.configure(state="disabled"))
                self.after(0, self.update_status_summary)
                self.after(0, self.finalize_run_results)

    # ===== ระบบสรุปผลการรัน (Run Report) =====
    STATUS_META = {
        "completed": ("เสร็จสมบูรณ์", ACCENT_GREEN),
        "device_error": ("คำสั่งผิดพลาด", ACCENT_RED),
        "macro_error": ("สคริปต์ผิดพลาด", ACCENT_RED),
        "stopped": ("ถูกหยุดกลางคัน", ACCENT_ORANGE),
    }
    FAILED_STATUSES = ("device_error", "macro_error", "stopped")

    def _collect_result(self, res):
        """เก็บผลลัพธ์ของบัญชี/จอหนึ่งเข้ารายการรวม (thread-safe)"""
        if not res:
            return
        lock = getattr(self, "run_results_lock", None)
        if not hasattr(self, "run_results"):
            self.run_results = []
        if lock is not None:
            with lock:
                self.run_results.append(res)
        else:
            self.run_results.append(res)

        # อัปเดต checkpoint: บัญชีไหนเสร็จ/พลาด เพื่อให้รันต่อจากที่ค้างได้
        email = res.get("email")
        if email:
            cp_status = "completed" if res.get("status") == "completed" else "failed"
            self._mark_checkpoint_account(email, cp_status, res.get("device", ""))

    def finalize_run_results(self):
        """บันทึกสถานะล่าสุดลงบัญชี + เปิดหน้าต่างสรุปผลหลังรันจบ"""
        # อัพเดทเพชรที่ step 'อ่านเพชร' เก็บไว้ระหว่างรัน -> export + push เข้าเว็บ
        self._flush_run_diamonds()

        results = list(getattr(self, "run_results", []))
        if not results:
            return

        from datetime import datetime
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # เก็บผลล่าสุดต่ออีเมล (กรณีไอดีเดียวรันหลายครั้ง ใช้ผลล่าสุด)
        by_email = {}
        for res in results:
            em = (res.get("email") or "").strip().lower()
            if em:
                by_email[em] = res

        changed = False
        for acc in self.accounts:
            em = (acc.get("email") or "").strip().lower()
            if em in by_email:
                res = by_email[em]
                acc["last_status"] = res.get("status", "")
                acc["last_error"] = res.get("error", "")
                acc["last_device"] = res.get("device", "")
                acc["last_run"] = stamp
                changed = True

        if changed:
            self.save_accounts()
            self.refresh_accounts_ui()

        # จัดการ checkpoint: ครบทุกบัญชี -> ล้างทิ้ง, ยังเหลือ/ถูกหยุด -> เก็บไว้ให้รันต่อ
        cp = getattr(self, "run_checkpoint", None)
        if cp:
            statuses = cp.get("status_by_email", {})
            remaining = [em for em, st in statuses.items() if st != "completed"]
            if remaining:
                self.write_log(
                    f"💾 ยังเหลือ {len(remaining)} ไอดีที่ยังไม่สำเร็จ — เก็บ checkpoint ไว้ "
                    f"กด 'รันมาโคร' เพื่อรันต่อได้", "warning")
                self.after(0, lambda n=len(remaining): self.run_macro_btn.configure(
                    text=f"▶️ รันต่อได้ (เหลือ {n})"))
            else:
                self._clear_run_checkpoint()
                self.write_log("✅ รันครบทุกบัญชีแล้ว — ล้าง checkpoint", "success")

        self.show_run_summary(results)

    def show_run_summary(self, results):
        """หน้าต่างสรุปผล: นับผ่าน/พลาด + ตารางรายละเอียด + export + เลือกที่พลาด"""
        total = len(results)
        failed = [r for r in results if r.get("status") in self.FAILED_STATUSES]
        ok = total - len(failed)

        win = tk.Toplevel(self)
        win.title("สรุปผลการรันมาโคร")
        win.configure(bg=BG_DARK)
        win.geometry("760x520")
        win.transient(self)

        header = tk.Frame(win, bg=BG_DARK)
        header.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(header, text="สรุปผลการรัน", bg=BG_DARK, fg=FG_WHITE,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        summary_txt = f"ทั้งหมด {total} รายการ   ·   ✅ สำเร็จ {ok}   ·   ❌ พลาด {len(failed)}"
        tk.Label(header, text=summary_txt, bg=BG_DARK, fg=FG_MUTED,
                 font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 0))

        # ตารางผลลัพธ์
        table_frame = tk.Frame(win, bg=BG_DARK)
        table_frame.pack(fill="both", expand=True, padx=20, pady=10)

        cols = ("email", "device", "status", "duration", "error")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=12)
        headings = {
            "email": ("บัญชี / ไอดี", 220),
            "device": ("จอ", 110),
            "status": ("สถานะ", 110),
            "duration": ("เวลา (วิ)", 70),
            "error": ("ข้อผิดพลาด", 220),
        }
        for col, (label, width) in headings.items():
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="w")

        tree.tag_configure("fail", foreground="#F87171")
        tree.tag_configure("ok", foreground="#34D399")
        tree.tag_configure("warn", foreground="#FBBF24")

        for r in results:
            status = r.get("status", "")
            label, _ = self.STATUS_META.get(status, (status, FG_WHITE))
            if status in ("device_error", "macro_error"):
                tag = "fail"
            elif status == "stopped":
                tag = "warn"
            else:
                tag = "ok"
            tree.insert("", "end", tags=(tag,), values=(
                r.get("email") or "(ไม่มีบัญชี)",
                r.get("device", ""),
                label,
                r.get("duration", ""),
                (r.get("error", "") or "")[:80],
            ))

        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # ปุ่มจัดการ
        btns = tk.Frame(win, bg=BG_DARK)
        btns.pack(fill="x", padx=20, pady=(6, 16))

        def export_csv():
            from tkinter import filedialog
            import csv
            from datetime import datetime
            default_name = f"run_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            path = filedialog.asksaveasfilename(
                parent=win, defaultextension=".csv", initialfile=default_name,
                filetypes=[("CSV", "*.csv"), ("ทั้งหมด", "*.*")],
            )
            if not path:
                return
            try:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(["email", "name", "device", "status", "error", "duration"])
                    for r in results:
                        writer.writerow([
                            r.get("email", ""), r.get("name", ""), r.get("device", ""),
                            r.get("status", ""), r.get("error", ""), r.get("duration", ""),
                        ])
                messagebox.showinfo("สำเร็จ", f"บันทึกรายงานเรียบร้อย:\n{path}", parent=win)
            except Exception as e:
                messagebox.showerror("ผิดพลาด", f"บันทึกไฟล์ไม่สำเร็จ: {e}", parent=win)

        def select_failed():
            failed_emails = {(r.get("email") or "").strip().lower() for r in failed if r.get("email")}
            run_emails = {(r.get("email") or "").strip().lower() for r in results if r.get("email")}
            if not failed_emails:
                messagebox.showinfo("ไม่มีไอดีที่พลาด", "รอบนี้ไม่มีไอดีที่ต้องรันซ้ำ", parent=win)
                return
            # ติ๊กเฉพาะไอดีที่พลาด ส่วนไอดีที่รันรอบนี้และผ่านแล้วให้เอาเครื่องหมายออก
            for acc in self.accounts:
                em = (acc.get("email") or "").strip().lower()
                if em in failed_emails:
                    acc["checked"] = True
                elif em in run_emails:
                    acc["checked"] = False
            self.save_accounts()
            self.refresh_accounts_ui()
            self.update_status_summary()
            messagebox.showinfo("เลือกแล้ว", f"ติ๊กไอดีที่พลาด {len(failed_emails)} รายการเพื่อรันซ้ำ\nกดปิดหน้าต่างนี้แล้วกด 'รันมาโคร' ได้เลย", parent=win)

        ModernButton(btns, text="📄 Export CSV", command=export_csv, variant="accent").pack(side="left", padx=(0, 10))
        ModernButton(btns, text="🔁 เลือกเฉพาะที่พลาด", command=select_failed, variant="warning").pack(side="left", padx=(0, 10))
        ModernButton(btns, text="ปิด", command=win.destroy, variant="subtle").pack(side="right")

    def fetch_otp_via_readmail_api(self, mail_address, refresh_token, client_id, pattern_str=None):
        """ดึงข้อความอีเมลผ่าน API ของ read-mail.me โดยใช้ OAuth2 Token"""
        import urllib.request
        import json
        import re
        
        if not pattern_str or pattern_str.strip() in ["", "{EMAIL}", "{PASSWORD}"]:
            pattern_str = r'\b\d{6}\b'
            
        url = "https://read-mail.me/get_data.php"
        data = {
            "email": mail_address,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "api_type": "graph_api"
        }
        headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRF-Token': 'rm_8Xk2pQwZ9vNjL5hTdYcA3sE7uBfM4oR',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(data).encode('utf-8'), 
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                res_json = json.loads(response.read().decode('utf-8'))
                
                if res_json.get("status") and "messages" in res_json:
                    messages = res_json["messages"]
                    for msg in messages[:5]:
                        subject = msg.get("subject", "")
                        body = msg.get("_body") or msg.get("message") or ""
                        
                        otp_match = re.search(pattern_str, body)
                        if otp_match:
                            otp_code = otp_match.group(0)
                            self.write_log(f"   📨 [{mail_address}] [API] พบข้อความหัวข้อ: '{subject}' -> ดึงรหัสสำเร็จ", "success")
                            return otp_code
                            
                    self.write_log(f"   🔍 [{mail_address}] [API] สแกนจดหมายแล้วไม่พบรหัสตามแพทเทิร์น: '{pattern_str}'", "warning")
                else:
                    err = res_json.get("error") or "ไม่พบข้อความ"
                    self.write_log(f"   ⚠️ [{mail_address}] [API] ดึงข้อมูลไม่สำเร็จ: {err}", "warning")
        except Exception as e:
            self.write_log(f"   ❌ [{mail_address}] [API] เกิดข้อผิดพลาดทางเทคนิค: {e}", "error")
            
        return None

    def fetch_otp_from_mail(self, mail_address, mail_password, pattern_str=None, refresh_token="", client_id=""):
        """เชื่อมต่อไปยังกล่องจดหมาย Outlook/Hotmail เพื่อดึงรหัส OTP ล่าสุด"""
        if not pattern_str or pattern_str.strip() in ["", "{EMAIL}", "{PASSWORD}"]:
            pattern_str = r'\b\d{6}\b'

        if refresh_token and client_id:
            self.write_log(f"   📨 [{mail_address}] พบโทเคน OAuth2 -> กำลังดึงอีเมลผ่าน API read-mail.me...", "info")
            otp_code = self.fetch_otp_via_readmail_api(mail_address, refresh_token, client_id, pattern_str)
            if otp_code:
                return otp_code
            self.write_log(f"   ⚠️ [{mail_address}] ดึงผ่าน API ล้มเหลว -> กำลังลองเชื่อมต่อผ่าน IMAP ทางเลือกสำรอง...", "warning")

        import imaplib
        import email
        import re
            
        try:
            # เชื่อมต่อกับ Server ของ Outlook/Hotmail
            mail = imaplib.IMAP4_SSL("outlook.office365.com")
            mail.login(mail_address, mail_password)
            
            # เลือกกล่องขาเข้า
            status, messages = mail.select("inbox")
            if status != "OK":
                self.write_log(f"   ❌ [{mail_address}] ไม่สามารถเปิดกล่องจดหมาย Inbox ได้", "error")
                return None
                
            num_messages = int(messages[0])
            if num_messages == 0:
                self.write_log(f"   ⚠️ [{mail_address}] ไม่มีข้อความใดๆ ในกล่องจดหมาย", "warning")
                return None
                
            # ตรวจสอบจาก 5 ข้อความล่าสุด (เริ่มจากใหม่สุดย้อนหลัง)
            for seq_num in range(num_messages, max(0, num_messages - 5), -1):
                status, data = mail.fetch(str(seq_num), "(RFC822)")
                if status != "OK" or not data:
                    continue
                    
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # ดึงหัวข้อและผู้ส่งเพื่อบันทึก Log หรือเปรียบเทียบ
                subject = ""
                try:
                    from email.header import decode_header
                    sub_decoded, encoding = decode_header(msg.get("Subject", ""))[0]
                    if isinstance(sub_decoded, bytes):
                        subject = sub_decoded.decode(encoding or "utf-8", errors="ignore")
                    else:
                        subject = sub_decoded
                except Exception:
                    subject = str(msg.get("Subject", ""))

                # ดึงเนื้อความอีเมล
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))
                        if content_type in ["text/plain", "text/html"] and "attachment" not in content_disposition:
                            try:
                                payload = part.get_payload(decode=True)
                                charset = part.get_content_charset() or "utf-8"
                                body += payload.decode(charset, errors="ignore")
                            except Exception:
                                pass
                else:
                    try:
                        payload = msg.get_payload(decode=True)
                        charset = msg.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="ignore")
                    except Exception:
                        pass
                
                # ค้นหา OTP ด้วย Regex
                otp_match = re.search(pattern_str, body)
                if otp_match:
                    otp_code = otp_match.group(0)
                    self.write_log(f"   📨 [{mail_address}] พบข้อความหัวข้อ: '{subject}' -> ดึงรหัสสำเร็จ", "success")
                    mail.logout()
                    return otp_code
                    
            mail.logout()
            self.write_log(f"   🔍 [{mail_address}] สแกน 5 เมลล่าสุดแล้วไม่พบแพทเทิร์น OTP: '{pattern_str}'", "warning")
            
        except Exception as e:
            self.write_log(f"   ❌ [{mail_address}] เกิดข้อผิดพลาดเชื่อมต่อกล่องเมล: {e}", "error")
            
        return None

    def _save_failure_report(self, device, account, step_num, total, step, reason):
        """บันทึก 'จุดที่ติด' ตอนรัน auto: แคปภาพหน้าจอ ณ ตอนนั้น + ข้อมูล (บัญชี/สคริปต์/ขั้นที่เท่าไหร่/
        เหตุผล) ลง error_reports/ เพื่อย้อนดูภายหลังว่าติดตรงไหน ภาพตอนนั้นเป็นยังไง

        step_num = เลขขั้นแบบ 1-based พร้อมแสดงผลแล้ว (int ธรรมดา เช่น 4, หรือ str เช่น '4.เจอ.1'
        สำหรับขั้นที่อยู่ในกิ่ง if_image) — ฟังก์ชันนี้แค่ format แสดงผล ไม่มีการบวกเลขต่อแล้ว"""
        try:
            import datetime, json as _json
            now = datetime.datetime.now()
            folder = os.path.join(self.error_reports_dir, now.strftime("%Y%m%d"))
            os.makedirs(folder, exist_ok=True)
            port = str(device).split(":")[-1]
            safe_num = str(step_num).replace(".", "-")
            img_path = os.path.join(folder, f"{now.strftime('%H%M%S')}_{port}_step{safe_num}.png")
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
                "profile": getattr(self, "_active_profile_name", ""),
                "step": step_num, "total": total,
                "step_type": step.get("type", ""), "step_desc": step.get("desc", ""),
                "reason": reason, "image": saved,
            }
            with open(os.path.join(self.error_reports_dir, "report.jsonl"), "a", encoding="utf-8") as f:
                f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
            self.write_log(f"   📸 [{device}] บันทึกจุดที่ติด: ขั้น {step_num}/{total} "
                           f"'{step.get('desc','')}' ({reason}) -> {saved or 'แคปจอไม่ได้'}", "warning")
            return saved
        except Exception as e:
            self.write_log(f"   ⚠️ [{device}] บันทึกรายงานปัญหาไม่สำเร็จ: {e}", "warning")
            return ""

    def open_error_reports_folder(self):
        """เปิดโฟลเดอร์รายงานปัญหา (ภาพจุดที่ติดตอนรัน auto) ให้เลือกดูได้"""
        try:
            os.makedirs(self.error_reports_dir, exist_ok=True)
            os.startfile(self.error_reports_dir)
        except Exception as e:
            messagebox.showinfo("รายงานปัญหา", f"โฟลเดอร์: {self.error_reports_dir}\n({e})")

    def execute_device_macro(self, device, account, highlight=True):
        """รันสคริปต์มาโครบน Emulator จอเดียวกับบัญชีที่กำหนด

        คืนค่า dict สรุปผลของบัญชี/จอนี้: status, error, errors, duration
        เพื่อให้ระบบนำไปสรุปผลรวมและบันทึกสถานะลงบัญชีได้
        """
        if not hasattr(self, 'device_active_accounts'):
            self.device_active_accounts = {}
        self.device_active_accounts[device] = account
        # อัปเดตสถานะสดของจอนี้ (คงค่า done_count/total_accounts เดิมไว้ ถ้าเคยตั้งจากคิวหลัก)
        st = self._device_run_state.setdefault(device, {"done_count": 0, "total_accounts": 0})
        st.update({"status": "running", "account_name": account_display_name(account) if account else "-",
                   "step_idx": 0, "step_total": 0, "step_desc": "กำลังเริ่ม…"})

        run_start = time.time()
        result = {
            "email": (account.get("email") if account else "") or "",
            "name": account_display_name(account) if account else "",
            "device": device,
            "status": "completed",  # completed | device_error | stopped | macro_error
            "error": "",
            "errors": 0,
            "duration": 0.0,
        }

        def record(ret, label):
            """รับผลลัพธ์ (success, output) จาก controller — ถ้า fail ให้ log + นับ"""
            try:
                ok, out = ret
            except (TypeError, ValueError):
                ok, out = True, ""
            if not ok:
                result["errors"] += 1
                if not result["error"]:
                    result["error"] = f"{label}: {out}"
                self.write_log(f"   ❌ [{device}] คำสั่ง {label} ล้มเหลว: {out}", "error")
            return ok

        progress = {"num": None, "step": None, "total": 0}  # ขั้นล่าสุดที่ทำ (ให้รายงานปัญหารู้ว่าติดตรงไหน)

        def finish():
            result["duration"] = round(time.time() - run_start, 1)
            if result["errors"] and result["status"] == "completed":
                result["status"] = "device_error"
            # บัญชีนี้ติดปัญหา (ไม่ใช่ผู้ใช้กดหยุด) -> บันทึกจุดที่ติด (ภาพ+ข้อมูล) ก่อน แล้วรีเซ็ตเกม
            # กันโดมิโน่: ถ้าไม่รีเซ็ต บัญชีถัดไปในคิวจอนี้จะเริ่มจากจอค้าง แล้วพังต่อกันหมด
            if result["status"] in ("device_error", "macro_error"):
                if not result.get("_reported") and progress["step"] is not None:
                    self._save_failure_report(device, account, progress["num"], progress["total"],
                                              progress["step"], result.get("error") or "error")
                self._device_run_state.setdefault(device, {})["status"] = "stuck"
                self._reset_device_to_login(device)
            return result

        # ขยายขั้นตอนคำสั่งย่อย (Script Sets) ถ้ามี — ไล่เข้ากิ่ง then/else ของ if_image ด้วย
        resolver = lambda name: self.script_sets.get(name)
        try:
            steps_to_run = self._expand_steps_with_sets_recursive(self.macro_steps, resolver)
        except Exception as e:
            self.write_log(f"❌ เกิดข้อผิดพลาดในการขยายชุดคำสั่ง (Script Sets): {e}", "error")
            result["status"] = "macro_error"
            result["error"] = f"script_sets: {e}"
            return finish()

        # บริบทที่ส่งให้ handler แต่ละชนิด (device/account คงที่, step_delay อัปเดตทุก step)
        import types
        ctx = types.SimpleNamespace(device=device, account=account, record=record, step_delay=0.0)
        handlers = self._get_step_handlers()

        status = self._run_macro_steps(device, account, steps_to_run, ctx, handlers, result,
                                       progress, st, highlight)
        if status != "completed":
            result["status"] = status
        return finish()

    # จำกัดความลึกกิ่งซ้อนของ if_image (กันสคริปต์ตั้งวนอ้างตัวเองไม่รู้จบ) — ตรงกับ macro_runner.py
    MAX_BRANCH_DEPTH = 5

    def _tree_has_run_set(self, steps):
        """เช็คว่ามี run_set ที่ไหนสักแห่ง (รวมในกิ่ง then/else ของ if_image) — พอร์ตจาก macro_runner.py"""
        for s in steps:
            if s.get("type") == "run_set":
                return True
            for k in ("then", "else"):
                if s.get(k) and self._tree_has_run_set(s[k]):
                    return True
        return False

    def _expand_steps_with_sets_recursive(self, steps, resolver):
        """ขยาย run_set ให้กลายเป็นขั้นย่อยจริง รวมถึง run_set ที่ซ่อนอยู่ในกิ่ง then/else
        (expand_steps_with_sets เดิมรู้จักแค่ลิสต์แบน ไม่รู้จักโครงสร้างกิ่ง) — พอร์ตจาก macro_runner.py"""
        if not self._tree_has_run_set(steps):
            return steps
        flat = expand_steps_with_sets(steps, resolver)
        for s in flat:
            if s.get("type") == "if_image":
                for k in ("then", "else"):
                    if s.get(k):
                        s[k] = self._expand_steps_with_sets_recursive(s[k], resolver)
        return flat

    def _eval_if_image_gui(self, device, step):
        """ประเมินเงื่อนไข if_image: เจอภาพภายใน timeout -> 'then' ไม่เจอ -> 'else'
        ภาพเงื่อนไขมาจาก anchor_img (base64 ที่ลากกรอบ) หรือ text (ไฟล์ใน templates/)
        พอร์ตจาก macro_runner.MacroRunner._eval_if_image ให้พฤติกรรมตรงกันเป๊ะทั้งสองแอป"""
        import base64
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
            p = os.path.join(self.templates_dir, tf) if tf else ""
            if p and os.path.exists(p):
                tmpl_path = p
        if tmpl_bytes is None and tmpl_path is None:
            self.write_log(f"   ⚠️ [{device}] if_image: ไม่ได้ตั้งภาพเงื่อนไข -> ถือว่า 'ไม่เจอ'", "warning")
            return "else"

        deadline = time.time() + timeout
        while True:
            if not self.macro_running:
                return "stopped"
            ok, data = self.controller.capture_screenshot_bytes(device)
            if ok:
                if tmpl_bytes is not None:
                    found, _x, _y, _m = self.controller.match_template_bytes(data, tmpl_bytes, threshold)
                else:
                    found, _x, _y, _m = self.controller.find_image_in_bytes(data, tmpl_path, threshold=threshold)
                if found:
                    self.write_log(f"   🔀 [{device}] เงื่อนไข '{step.get('desc') or 'if_image'}' -> ✅ เจอ", "info")
                    return "then"
            if time.time() >= deadline:
                self.write_log(f"   🔀 [{device}] เงื่อนไข '{step.get('desc') or 'if_image'}' -> ❌ ไม่เจอ", "info")
                return "else"
            waited = 0.0
            while waited < 0.4:
                if not self.macro_running:
                    return "stopped"
                time.sleep(0.1)
                waited += 0.1

    def _run_macro_steps(self, device, account, steps, ctx, handlers, result, progress, st,
                         highlight, path="", depth=0, disp=""):
        """รันลิสต์ขั้นตอน — เรียกซ้ำตัวเองเข้าไปในกิ่ง then/else ของ if_image ได้ (พอร์ตจาก macro_runner.py
        MacroRunner._run_steps ให้ตัวรันทั้งสองแอปมีตรรกะเดียวกันเป๊ะ) mutate result[]/progress[] ให้ตรง
        ก่อน return เสมอ (ยกเว้น "completed") คืน "completed" | "stopped" | "device_error"

        ใช้ while + ตัวชี้ idx เดินเอง (ไม่ใช่ for) เพราะ anchor_on_fail="retry" ต้องกระโดด
        ตัวชี้ถอยหลังไปทำขั้นก่อนหน้าใหม่ในลิสต์เดียวกันได้ (วนทำซ้ำ ไม่ใช่แค่ไล่หน้าเดียว)
        """
        if depth > self.MAX_BRANCH_DEPTH:
            self.write_log(f"   ⚠️ [{device}] กิ่งซ้อนเกิน {self.MAX_BRANCH_DEPTH} ชั้น -> ข้ามกิ่งนี้ (กันวนไม่รู้จบ)", "warning")
            return "completed"

        total = len(steps)
        in_branch = bool(path)
        retry_counts = {}  # idx ของขั้นนี้ -> จำนวนรอบที่วนไปแล้ว (รีเซ็ตใหม่ทุกครั้งที่เรียกฟังก์ชันนี้)
        idx = 0
        while idx < total:
            if not self.macro_running:
                result["status"] = "stopped"
                return "stopped"

            step = steps[idx]
            t = step.get("type", "tap")
            here = f"{path}.{idx}" if path else str(idx)
            num = f"{disp}{idx + 1}"  # เลขขั้นให้คนอ่าน เช่น "4" หรือ "4.เจอ.1"
            desc = step.get("desc", f"ขั้นตอนที่ {idx+1}")
            if not in_branch:
                progress["num"], progress["step"], progress["total"] = num, step, total
                st.update({"step_idx": idx + 1, "step_total": total, "step_desc": desc})
            email_log = ""
            if account:
                acc_name = account_display_name(account)
                email_log = f" ({acc_name if acc_name and acc_name != '-' else account['email']})"
            self.write_log(f"   👉 [{device}]{email_log} ขั้นที่ {num}"
                           f"{f'/{total}' if not in_branch else ''}: {desc}...", "info")

            # ไฮไลท์การทำงานบนลิสต์บ็อกซ์ GUI เฉพาะเส้นหลัก (กิ่งไม่มีแถวใน listbox ให้ชี้)
            if highlight and not in_branch and idx < self.step_listbox.size():
                self.after(0, lambda i=idx: self.step_listbox.selection_clear(0, tk.END))
                self.after(0, lambda i=idx: self.step_listbox.selection_set(i))
                self.after(0, lambda i=idx: self.step_listbox.see(i))

            # ดึงค่าหน่วงเวลาเฉพาะของขั้นตอนนี้ (ถ้าไม่มีให้ดึงค่าดีฟอลต์มาใช้)
            step_delay = step.get("delay")
            if step_delay is None:
                step_delay = DEFAULT_STEP_DELAYS.get(t, 0.0)
            else:
                step_delay = float(step_delay)
            if step_delay > 0:
                step_delay = step_delay * random.uniform(0.8, 1.4)

            # ---- บล็อกทางเลือก: เจอภาพ -> กิ่ง then จนจบ แล้วกลับมาต่อเส้นนี้ / ไม่เจอ -> กิ่ง else ----
            if t == "if_image":
                branch = self._eval_if_image_gui(device, step)
                if branch == "stopped":
                    result["status"] = "stopped"
                    return "stopped"
                sub = step.get(branch) or []
                bname = "เจอ" if branch == "then" else "ไม่เจอ"
                if sub:
                    self.write_log(f"   🔀 [{device}] ขั้น {num}: เข้ากิ่ง '{bname}' ({len(sub)} ขั้น)", "info")
                    r = self._run_macro_steps(device, account, sub, ctx, handlers, result, progress, st,
                                              highlight, path=f"{here}.{branch}", depth=depth + 1,
                                              disp=f"{num}.{bname}.")
                    if r != "completed":
                        return r
                    self.write_log(f"   ↩️ [{device}] ขั้น {num}: จบกิ่ง '{bname}' -> กลับเส้นหลัก", "info")
                else:
                    self.write_log(f"   🔀 [{device}] ขั้น {num}: กิ่ง '{bname}' ว่าง (ไม่มีขั้นให้ทำ) -> ไปต่อ", "warning")
                if step_delay > 0:
                    time.sleep(step_delay)
                idx += 1
                continue

            # === Anchor gate (ชั้น B): ถ้าสเต็ปมีภาพ anchor -> 'รอจนเห็นภาพนั้นบนจอ' ก่อนทำ ===
            # กันปัญหาจอช้า/ค้างแล้วกดตาบอดจนมั่ว: จอช้า=รอจนตามทัน, จอไม่ตรง=ตามนโยบาย anchor_on_fail
            ctx.anchor_hit = None  # จุดกึ่งกลางที่ anchor เจอรอบนี้ (ให้ tap 'ตามภาพที่ขยับ' ได้)
            if step.get("anchor_img"):
                gate, ax, ay = self._wait_for_step_anchor(device, step)
                if gate == "found" and ax is not None:
                    ctx.anchor_hit = (ax, ay)
                if gate == "stopped":
                    result["status"] = "stopped"
                    return "stopped"
                if gate == "missing":
                    policy = step.get("anchor_on_fail", "abort")
                    if policy == "retry":
                        target = step.get("anchor_retry_target")
                        limit = int(step.get("anchor_retry_limit", 3) or 3)
                        cnt = retry_counts.get(idx, 0)
                        if target is not None and 0 <= int(target) < total and cnt < limit:
                            retry_counts[idx] = cnt + 1
                            self.write_log(f"   🔁 [{device}] ไม่เจอภาพ anchor ขั้น {num} -> วนกลับไปทำขั้นที่ {int(target)+1} ใหม่ "
                                          f"(รอบที่ {cnt+1}/{limit})", "warning")
                            idx = int(target)
                            continue
                        reason = "ยังไม่ได้ตั้งขั้นเป้าหมายให้วนกลับ" if target is None else f"วนครบ {limit} รอบแล้วยังไม่เจอ"
                        self.write_log(f"   ⛔ [{device}] ไม่เจอภาพ anchor ขั้น {num} ({desc}) -> {reason} -> หยุดจอนี้ กันรันมั่ว", "error")
                        self._save_failure_report(device, account, num, total, step, "ไม่เจอภาพ anchor (retry หมดรอบ)")
                        result["_reported"] = True
                        result["status"] = "device_error"
                        result["error"] = f"anchor_fail_retry_exhausted: ขั้น {num} {desc}"
                        return "device_error"
                    elif policy == "skip":
                        self.write_log(f"   ⏭️ [{device}] ไม่เจอภาพ anchor ขั้น {num} ({desc}) -> ข้ามขั้นนี้", "warning")
                        idx += 1
                        continue
                    elif policy == "tap":
                        self.write_log(f"   ⚠️ [{device}] ไม่เจอภาพ anchor ขั้น {num} -> กดตามพิกัดเดิม (เสี่ยง)", "warning")
                    else:  # abort — หยุดจอนี้ (กันรันมั่ว) จออื่นเดินต่อ + รายงานให้ตามเก็บ
                        self.write_log(f"   ⛔ [{device}] ไม่เจอภาพ anchor ขั้น {num} ({desc}) -> หยุดจอนี้ กันรันมั่ว", "error")
                        # บันทึกภาพหน้าจอ ณ จุดที่ติด ก่อนรีเซ็ต (ให้ย้อนดูได้ว่าจอตอนนั้นเป็นยังไง)
                        self._save_failure_report(device, account, num, total, step, "ไม่เจอภาพ anchor (abort)")
                        result["_reported"] = True
                        result["status"] = "device_error"
                        result["error"] = f"anchor_fail: ขั้น {num} {desc}"
                        return "device_error"

            # ประมวลผลคำสั่งมาโคร ผ่านตาราง dispatch (handler ต่อชนิด step)
            ctx.step_delay = step_delay
            handler = handlers.get(t)
            if handler is None:
                self.write_log(f"   ⚠️ [{device}] ไม่รู้จักชนิดขั้นตอน '{t}' -> ข้าม", "warning")
                idx += 1
                continue
            signal = handler(ctx, step)
            if signal == "stop":
                result["status"] = "stopped"
                return "stopped"

            idx += 1

        return "completed"

    def _update_anchor_poll(self):
        """อัปเดตค่าความถี่วนเช็ค anchor (เก็บเป็น float แยก) จากช่อง UI — ทำบนเธรดหลัก
        เพื่อให้ worker thread อ่าน self._anchor_poll_interval ได้โดยไม่แตะ Tk var (ไม่ปลอดภัยข้ามเธรด)"""
        try:
            v = float(self._anchor_poll_var.get())
        except (TypeError, ValueError):
            return
        self._anchor_poll_interval = min(10.0, max(0.1, v))

    def _wait_for_step_anchor(self, device, step):
        """รอจนเจอ 'ภาพ anchor' ของสเต็ปบนจอ (base64 ในฟิลด์ anchor_img)
        คืน (status, cx, cy) — cx,cy = จุดกึ่งกลางที่ match เจอ (None ถ้าไม่มี/anchor เสีย)
          - found   = เจอภายใน timeout -> ทำสเต็ปต่อได้ (cx,cy ใช้ relocate จุดกดได้)
          - missing = ครบ timeout ยังไม่เจอ (จอไม่ตรงที่คาด)
          - stopped = ผู้ใช้กดหยุดระหว่างรอ"""
        import base64
        b64 = step.get("anchor_img") or ""
        try:
            tmpl_bytes = base64.b64decode(b64)
        except Exception:
            return "found", None, None  # anchor เสีย -> ไม่กั้น (ทำต่อ)
        if not tmpl_bytes:
            return "found", None, None
        timeout = float(step.get("anchor_timeout", 8.0) or 8.0)
        threshold = float(step.get("anchor_threshold", 0.8) or 0.8)
        deadline = time.time() + timeout
        best = 0.0
        while time.time() < deadline:
            if not self.macro_running:
                return "stopped", None, None
            ok, data = self.controller.capture_screenshot_bytes(device)
            if ok:
                found, cx, cy, msg = self.controller.match_template_bytes(data, tmpl_bytes, threshold)
                if found:
                    return "found", cx, cy
                # เก็บค่าความคล้ายสูงสุดไว้ log (ดึงเลขจากข้อความ)
                m = re.search(r"([0-9]*\.?[0-9]+)", msg or "")
                if m:
                    best = max(best, float(m.group(1)))
            # รอช่วง poll ที่ตั้งได้จาก UI (คุม CPU) — แต่ยังเช็คปุ่มหยุดถี่ๆ ให้ยกเลิกได้ทันที
            poll = getattr(self, "_anchor_poll_interval", 0.5)
            waited = 0.0
            while waited < poll:
                if not self.macro_running:
                    return "stopped", None, None
                time.sleep(min(0.2, poll - waited))
                waited += 0.2
        self.write_log(f"   🔎 [{device}] anchor: รอ {timeout:g} วิ ยังไม่เจอ (คล้ายสุด {best:.2f}/{threshold:g})", "warning")
        return "missing", None, None

    # ===== Macro step handlers (dispatch table) =====
    def _get_step_handlers(self):
        """ตารางจับคู่ชนิด step -> เมธอด handler (สร้างครั้งเดียวแล้วแคชไว้)"""
        if not hasattr(self, "_step_handlers"):
            self._step_handlers = {
                "tap": self._step_tap,
                "swipe": self._step_swipe,
                "text": self._step_text,
                "keyevent": self._step_keyevent,
                "start_app": self._step_start_app,
                "stop_app": self._step_stop_app,
                "detect_image": self._step_detect_image,
                "wait_for_image": self._step_wait_for_image,
                "tap_text": self._step_tap_text,
                "wait_for_text": self._step_wait_for_text,
                "screenshot": self._step_screenshot,
                "clear_ads_loop": self._step_clear_ads_loop,
                "fetch_otp": self._step_fetch_otp,
                "sleep": self._step_sleep,
                "keyboard": self._step_keyboard,
                "read_diamond": self._step_read_diamond,
                "story_auto": self._step_story_auto,
                "find_yellow_stage": self._step_find_yellow_stage,
                # หมายเหตุ: if_image ไม่อยู่ในตารางนี้ — ถูกดักจัดการพิเศษใน _run_macro_steps
                # ก่อนถึงจุด dispatch เสมอ (ต้องแตกกิ่ง then/else ไม่ใช่ handler ปกติ)
            }
        return self._step_handlers

    # ===== Story Auto: เล่นเนื้อเรื่องอัตโนมัติ (หาด่านเหลือง -> ลุยจนจบ -> วนซ้ำ) =====
    def _story_button_templates(self, buttons_field=""):
        """คืน list ของ (ชื่อ, path) ปุ่มที่จะกวาดหาในแต่ละด่าน
        ถ้าไม่ระบุ -> ใช้ทุกไฟล์ templates/story_*.png"""
        import glob as _glob
        names = [b.strip() for b in (buttons_field or "").split(",") if b.strip()]
        if not names:
            names = sorted(os.path.basename(p) for p in _glob.glob(os.path.join(self.templates_dir, "story_*.png")))
        out = []
        for n in names:
            p = os.path.join(self.templates_dir, n)
            if os.path.exists(p):
                out.append((n, p))
        return out

    def _story_swipe_dirs(self, gx, screen_w=960):
        """ลำดับทิศปัด 'ตามที่เห็นบนจอ' — จากทุกจอปัดที่เก็บมา เป้าปลายทาง (ลูกบอลเงา)
        อยู่ฝั่งตรงข้ามกับบอลเรืองเสมอ (บอลซ้าย→ปัดขวา, บอลขวา→ปัดซ้าย)
        จึงเรียงทิศแนวนอนเข้าหาฝั่งตรงข้ามก่อน แล้วค่อยทแยง/ตั้ง (วนต่อถ้าทิศแรกไม่เวิร์ก)"""
        to_right = gx < screen_w / 2
        primary = ("ขวา", 1.0, 0.0) if to_right else ("ซ้าย", -1.0, 0.0)
        secondary = ("ซ้าย", -1.0, 0.0) if to_right else ("ขวา", 1.0, 0.0)
        sgn = 1.0 if to_right else -1.0
        return [
            primary, secondary,
            ("ทแยงลง", sgn * 0.7, 0.7), ("ทแยงขึ้น", sgn * 0.7, -0.7),
            ("ทแยงลงกลับ", -sgn * 0.7, 0.7), ("ทแยงขึ้นกลับ", -sgn * 0.7, -0.7),
            ("ลง", 0.0, 1.0), ("ขึ้น", 0.0, -1.0),
        ]

    def _story_swipe(self, device, gx, gy, attempt, length=340):
        """ปัดนิ้วจากไอคอน (gx,gy) ตามทิศลำดับที่ attempt (ทิศแรก = เข้าหาฝั่งตรงข้ามของจอ)"""
        dirs = self._story_swipe_dirs(gx)
        name, dx, dy = dirs[attempt % len(dirs)]
        ex = max(20, min(940, int(gx + dx * length)))
        ey = max(20, min(520, int(gy + dy * length)))
        self.write_log(f"   👉 [{device}] ปัดจากไอคอน ({gx},{gy}) ทิศ{name} -> ({ex},{ey})", "info")
        self.controller.swipe(device, gx, gy, ex, ey, duration=450)

    # ชุดกู้สถานการณ์เมื่อจอ 'ค้าง' (watchdog) — แตะจุดสากลที่มักเป็นปุ่มดำเนินต่อ วนไปทีละอย่าง
    # เคสที่เราไม่รู้จัก (ปุ่ม/คัตซีนแบบใหม่) จะได้หลุดเองโดยไม่ต้องไล่เพิ่ม template
    _STORY_RECOVERY = [
        ("มุมข้ามขวาบน", 884, 32),
        ("แตะกลางจอ", 480, 270),
        ("ปุ่มล่างขวา", 834, 494),
        ("แตะล่างกลาง", 480, 480),
        ("มุมข้ามอีกจุด", 916, 30),
    ]

    def _story_recover(self, device, data, step):
        """ทำ 1 การกู้สถานการณ์ (วนตาม step) เมื่อ watchdog ตรวจว่าจอค้าง:
        (1) ถาม Gemini ครั้งเดียว (ถ้าตั้ง key ไว้ — เรียกเฉพาะตอนติดแบบนี้เท่านั้น ไม่ถี่เกิน
            1 ครั้ง/25 วิ จึงแทบไม่กิน quota ต่างจากเดิมที่ยิงทุก 2 วิจนโดน 429)
        (2) OCR หาคำปุ่ม 'ข้าม/OK/ตกลง' บนจอ
        (3) แตะจุดสากลที่มักเป็นปุ่มดำเนินต่อ วนไปทีละจุด

        หมายเหตุ: throttle (_last_ai_rescue_ts) เป็นแบบ 'รวมทุกเครื่อง' โดยตั้งใจ — ตอนรัน
        Story Auto หลายเครื่องพร้อมกัน ถ้าแยก throttle ต่อเครื่องจะเสี่ยงยิง Gemini พร้อมกัน
        หลายครั้งตอนหลายเครื่องค้างพร้อมกัน จนโดน 429 (rate limit) เหมือนปัญหาที่เคยเจอมาก่อน"""
        if self.gemini_api_key and (time.time() - getattr(self, "_last_ai_rescue_ts", 0.0)) > 25.0:
            self._last_ai_rescue_ts = time.time()
            gok, gx, gy, greason = gemini_tap_suggestion(data, self.gemini_api_key, 960, 540)
            if gok:
                self.write_log(f"   🤖 [{device}] กันค้าง (AI): {greason} -> tap ({gx},{gy})", "warning")
                self.controller.tap(device, gx, gy)
                return
            self.write_log(f"   🤖 [{device}] กันค้าง (AI): ไม่ได้คำตอบ ({greason}) -> ใช้วิธีสำรอง", "info")
        ocr_ok, ox, oy, oword = ocr_find_button(data)
        if ocr_ok:
            self.write_log(f"   🛟 [{device}] กันค้าง: OCR เจอ '{oword}' ({ox},{oy}) -> tap", "warning")
            self.controller.tap(device, ox, oy)
            return
        name, rx, ry = self._STORY_RECOVERY[step % len(self._STORY_RECOVERY)]
        self.write_log(f"   🛟 [{device}] กันค้าง: แตะ{name} ({rx},{ry})", "warning")
        self.controller.tap(device, rx, ry)

    def run_story_auto(self, device, max_stages=30, stage_timeout=240.0,
                       threshold=0.7, scan_interval=1.2, buttons_field="",
                       running_check=None):
        """ลูปเล่นเนื้อเรื่อง: หา 'ด่านเหลือง' บนหน้าเลือกด่าน -> แตะเข้า -> กวาดกดปุ่ม
        (ข้าม/ไปต่อ/รับ) จนกลับมาหน้าเลือกด่าน (เหลืองโผล่อีก) -> วนด่านถัดไป
        จบเมื่อไม่พบด่านเหลือง (สุด story) หรือครบ max_stages

        running_check: callable คืน True ถ้ายังให้รันต่อ (ดีฟอลต์ = self.macro_running)
        คืนจำนวนด่านที่เคลียร์ได้
        """
        if running_check is None:
            running_check = lambda: self.macro_running

        btn_paths = self._story_button_templates(buttons_field)
        btn_paths = [(n, p) for (n, p) in btn_paths if n != "story_map.png"]
        limit_str = "ไม่จำกัด (กดหยุดเอง)" if not max_stages else f"สูงสุด {max_stages} ด่าน"
        self.write_log(
            f"   🎮 [{device}] Story Auto เริ่ม ({limit_str}) "
            f"ปุ่มที่กวาด: {', '.join(b for b, _ in btn_paths) or '— (ยังไม่มี template story_*.png)'} "
            f"| ตรวจหน้าเลือกด่านด้วยกรอบเลือก UI (ไม่พึ่ง AI)",
            "warning")

        def cap():
            ok, data = self.controller.capture_screenshot_bytes(device)
            return data if ok else None

        # ===== ลูปเดียวรวมทุกสถานะ =====
        # แต่ละรอบ 'ดูจอแล้วทำให้ถูกกับสิ่งที่เห็น' — ไม่แยกโหมด outer/inner (เดิมพอหลุด inner
        # ตอนคัตซีน จะกลับไป outer ที่หาแต่ด่าน ทำให้ไม่จัดการคัตซีนแล้วค้าง)
        # ลำดับ: (1) หน้าเลือกด่าน->แตะด่าน  (2) ในแมตช์->รอ  (3) คัตซีน/อื่นๆ->กดปุ่ม/แตะ/ปัด/กู้
        cleared = 0
        in_stage = False          # แตะด่านแล้ว (กำลังเล่นด่านอยู่)
        left_map_confirmed = False  # ยืนยันออกจากหน้าเลือกด่านแล้ว (กันนับซ้ำตอนจอ transition)
        tap_stage_ts = 0.0
        swipe_prev = None
        swipe_attempt = 0
        prev_frame = None
        last_change_ts = time.time()
        recover_step = 0
        last_idle_log = 0.0
        STUCK_SECONDS = 12.0

        while running_check():
            if max_stages and cleared >= int(max_stages):
                break
            data = cap()
            if data is None:
                self.write_log(f"   ⚠️ [{device}] แคปจอไม่ได้ -> รอแล้วลองใหม่", "warning")
                time.sleep(2.0)
                continue

            # Watchdog: จอเปลี่ยนไหม (2 ระดับ) — ขยับเล็ก (คัตซีนเล่นอยู่)=รีเซ็ตนาฬิกา, เปลี่ยนฉาก=รีเซ็ต recovery
            if prev_frame is not None:
                _sim = png_similarity(data, prev_frame)
                if _sim < 0.95:
                    last_change_ts = time.time()
                if _sim < 0.85:
                    recover_step = 0
            prev_frame = data

            # ===== (0) ระหว่างเล่นด่าน: ให้ปุ่ม action ชนะกรอบเลือกด่านเสมอ =====
            # กันเคส false-positive ของ find_highlighted_stage จากไอคอนสีเหลืองสว่างอื่นๆ
            # ในหน้ารายละเอียดด่าน/คัตซีน (เช่นไอคอนรางวัล EXP/เหรียญทอง ที่ทำให้ตรวจกรอบผิด
            # จนแตะด่านซ้ำที่เดิมไม่รู้จบ) — ถ้ากำลังอยู่ในด่านอยู่แล้วและเจอปุ่มจริง ให้กดปุ่มก่อนเสมอ
            if in_stage:
                btn_handled = False
                for name, path in btn_paths:
                    if "swipe" in name or "tap" in name:
                        continue
                    fnd, mx, my, _msg = self.controller.find_image_in_bytes(data, path, threshold=threshold)
                    if fnd:
                        self.write_log(f"   👆 [{device}] กดปุ่ม '{name}' ({mx},{my})", "info")
                        self.controller.tap(device, mx, my)
                        btn_handled = True
                        left_map_confirmed = True  # กดปุ่มสำเร็จ = ไม่ใช่หน้า map เปล่าแน่นอน
                        last_change_ts = time.time()
                        time.sleep(0.8)
                        break
                if btn_handled:
                    continue

            # ===== (1) หน้าเลือกด่าน: เจอกรอบเลือกด่าน =====
            # การ์ดกันพลาด: ถ้าจอนี้มี 'ลูกบอลเรืองแสง' = คัตซีนปัดนิ้ว ไม่ใช่หน้าเลือกด่านแน่นอน
            # -> ห้ามเชื่อกรอบเลือกด่าน (กัน false-positive จากเส้นพื้น/ไอคอนในคัตซีน) ให้ตกไปที่ glow handler
            hf, hx, hy = find_highlighted_stage(data)
            if hf and find_swipe_glow(data)[0]:
                hf = False
            if hf:
                # เพิ่งกลับจากด่าน (เคยเข้าด่าน + ออกจาก map แล้ว) = จบ 1 ด่าน
                if in_stage and left_map_confirmed:
                    cleared += 1
                    self.write_log(f"   🏁 [{device}] ด่านจบ -> กลับถึงหน้าเลือกด่าน (รวม {cleared} ด่าน)", "success")
                    in_stage = False
                    left_map_confirmed = False
                # เพิ่งแตะด่านไปแต่ยังไม่ทันออก map (< 6 วิ) = รอโหลด อย่าเพิ่งแตะซ้ำ
                if in_stage and (time.time() - tap_stage_ts) < 6.0:
                    time.sleep(scan_interval)
                    continue
                # ยืนยันตำแหน่งนิ่งก่อนแตะ (กันจับผิดตอนจอ transition)
                time.sleep(0.5)
                data2 = cap()
                h2, hx2, hy2 = find_highlighted_stage(data2) if data2 is not None else (False, 0, 0)
                if not h2 or abs(hx2 - hx) > 30 or abs(hy2 - hy) > 30:
                    continue
                self.write_log(f"   ▶️ [{device}] แตะด่านเหลือง ({hx2},{hy2})", "info")
                self.controller.tap(device, hx2, hy2)
                in_stage = True
                left_map_confirmed = False
                tap_stage_ts = time.time()
                last_change_ts = time.time()
                swipe_prev = None
                swipe_attempt = 0
                time.sleep(1.5)
                continue

            # ไม่อยู่หน้าเลือกด่านแล้ว -> ถ้าเคยแตะด่าน ถือว่าออกจาก map แล้ว (พร้อมนับจบเมื่อกลับ)
            if in_stage:
                left_map_confirmed = True

            # ===== (2) ในแมตช์ auto (เจอจอยสติ๊ก) -> รอเฉยๆ ห้ามแตะ =====
            if in_match_autoplay(data):
                time.sleep(scan_interval)
                continue

            # ===== (3) คัตซีน/หน้าอื่น -> กดปุ่ม/แตะ/ปัด =====
            tapped = False
            for name, path in btn_paths:
                if "swipe" in name or "tap" in name:
                    continue  # ลูกบอลแตะ/ปัด ยกให้ glow handler จัดการรวม
                fnd, mx, my, _msg = self.controller.find_image_in_bytes(data, path, threshold=threshold)
                if fnd:
                    self.write_log(f"   👆 [{device}] กดปุ่ม '{name}' ({mx},{my})", "info")
                    self.controller.tap(device, mx, my)
                    tapped = True
                    time.sleep(0.8)
                    break
            if not tapped:
                # ลูกบอลเรืองแสง (คัตซีนโต้ตอบ แตะ/ปัด): ครั้งที่ 0=แตะ, 1+=ปัดวนทีละทิศ
                # ลูกบอลยังอยู่ที่เดิม = วิธีก่อนไม่เวิร์ก -> เลื่อนไปวิธี/ทิศถัดไป
                gl_ok, gx, gy = find_swipe_glow(data)
                if gl_ok:
                    if swipe_prev and abs(gx - swipe_prev[0]) < 25 and abs(gy - swipe_prev[1]) < 25:
                        swipe_attempt += 1
                    else:
                        swipe_attempt = 0
                    swipe_prev = (gx, gy)
                    if swipe_attempt == 0:
                        self.write_log(f"   👆 [{device}] แตะไอคอนเรืองแสง ({gx},{gy})", "info")
                        self.controller.tap(device, gx, gy)
                    else:
                        self._story_swipe(device, gx, gy, swipe_attempt - 1)
                    tapped = True
                    time.sleep(0.8)
                else:
                    swipe_prev = None
            if not tapped:
                ocr_ok, ox, oy, oword = ocr_find_button(data)
                if ocr_ok:
                    self.write_log(f"   🔤 [{device}] OCR เจอปุ่ม '{oword}' ({ox},{oy}) -> tap", "info")
                    self.controller.tap(device, ox, oy)
                    tapped = True
                    time.sleep(0.8)
            if not tapped:
                time.sleep(scan_interval)

            # Watchdog: จอนิ่งนานเกิน (ไม่ใช่ map/แมตช์ และไม่มีปุ่ม/ไอคอน) = ติดเคสไม่รู้จัก
            # -> กู้สถานการณ์วนไป (แตะข้าม/กลางจอ ฯลฯ) ให้หลุดเอง; แจ้ง idle เป็นระยะ
            if (time.time() - last_change_ts) > STUCK_SECONDS:
                self._story_recover(device, data, recover_step)
                recover_step += 1
                last_change_ts = time.time() - (STUCK_SECONDS - 4.0)
                if time.time() - last_idle_log > 20:
                    self.write_log(f"   ⏳ [{device}] จอนิ่ง/ยังหาปุ่มไม่เจอ — กำลังลองกู้ (กดหยุดเองเมื่อพอ)", "info")
                    last_idle_log = time.time()
                time.sleep(1.0)

        self.write_log(f"   🎉 [{device}] Story Auto หยุด — เคลียร์ไป {cleared} ด่าน", "success")
        return cleared

    def _step_story_auto(self, ctx, step):
        """step: เล่นเนื้อเรื่องอัตโนมัติทั้งชุดบนเครื่องนี้"""
        self.run_story_auto(
            ctx.device,
            max_stages=int(step.get("max_stages", 30) or 30),
            stage_timeout=float(step.get("stage_timeout", 240) or 240),
            threshold=float(step.get("threshold", 0.78) or 0.78),
            buttons_field=(step.get("buttons") or step.get("text") or ""),
        )
        if ctx.step_delay > 0:
            time.sleep(ctx.step_delay)

    def _step_find_yellow_stage(self, ctx, step):
        """step: หา 'ด่านเหลือง' บนหน้าเลือกด่านแล้วแตะ (กดด่านถัดไป 1 ครั้ง)"""
        device = ctx.device
        ok, data = self.controller.capture_screenshot_bytes(device)
        if not ok:
            self.write_log(f"   ❌ [{device}] แคปจอไม่ได้ -> ข้าม", "error")
            return
        found, cx, cy, _box = find_yellow_frame(data)
        if found:
            self.write_log(f"   🎯 [{device}] เจอด่านเหลือง ({cx},{cy}) -> แตะ", "success")
            ctx.record(self.controller.tap(device, cx, cy), "find_yellow_stage")
        else:
            self.write_log(f"   ⏭️ [{device}] ไม่พบด่านเหลืองบนจอ", "warning")
        if ctx.step_delay > 0:
            time.sleep(ctx.step_delay)

    def _step_tap(self, ctx, step):
        x, y = step["x"], step["y"]
        # โหมด 'กดตรงที่เจอภาพ': ถ้าสเต็ปตั้ง anchor_tap และรอบนี้ anchor เจอ -> ย้ายจุดกดตามภาพ
        # ที่ขยับ โดยคงระยะห่างเดิม (จุดแดง) เทียบกับจุดกึ่งกลางกรอบ anchor (จุดเขียว) เอาไว้
        # => ปุ่ม/ป็อปอัพเลื่อนตำแหน่งนิดหน่อยก็ยังกดตรง (แม่นกว่าพิกัดตายตัว)
        hit = getattr(ctx, "anchor_hit", None)
        reg = step.get("anchor_region")
        if step.get("anchor_tap") and hit and reg:
            try:
                acx = reg["x"] + reg["w"] / 2.0
                acy = reg["y"] + reg["h"] / 2.0
                x = int(round(hit[0] + (float(step["x"]) - acx)))
                y = int(round(hit[1] + (float(step["y"]) - acy)))
                self.write_log(f"   🎯 [{ctx.device}] กดตามภาพที่เจอ -> ({x},{y})", "info")
            except (TypeError, ValueError, KeyError):
                x, y = step["x"], step["y"]
        ctx.record(self.controller.tap(ctx.device, x, y), "tap")
        time.sleep(ctx.step_delay)  # หน่วงเวลาหลังคลิกเพื่อให้ระบบ Android ทำงานทัน

    def _step_swipe(self, ctx, step):
        swipe_duration = int(float(step.get("duration", DEFAULT_SWIPE_DURATION)))
        ctx.record(self.controller.swipe(ctx.device, step["x"], step["y"], step["x2"], step["y2"], swipe_duration), "swipe")
        time.sleep(ctx.step_delay)  # หน่วงเวลาหลังลากจอ

    def _step_text(self, ctx, step):
        # แทนที่ตัวแปร {EMAIL}/{PASSWORD}/{NAME} ด้วยไอดีรอบนี้
        text_to_send = self._substitute_account(step["text"], ctx.account)
        if str(text_to_send).isascii():
            ctx.record(self.controller.input_text(ctx.device, text_to_send), "text")
        else:
            # มีอักขระไทย/Unicode -> ต้องผ่าน ADBKeyboard
            ctx.record(self.controller.input_text_unicode(ctx.device, text_to_send), "text")
        time.sleep(ctx.step_delay)  # หน่วงเวลาหลังพิมพ์ข้อความ

    def _step_keyevent(self, ctx, step):
        ctx.record(self.controller.keyevent(ctx.device, step["code"]), "keyevent")
        time.sleep(ctx.step_delay)  # หน่วงเวลาหลังคีย์อีเวนท์

    def _step_start_app(self, ctx, step):
        ctx.record(self.controller.start_app(ctx.device, step["text"]), "start_app")
        if ctx.step_delay > 0:
            time.sleep(ctx.step_delay)

    def _step_stop_app(self, ctx, step):
        ctx.record(self.controller.stop_app(ctx.device, step["text"]), "stop_app")
        if ctx.step_delay > 0:
            time.sleep(ctx.step_delay)

    def _step_detect_image(self, ctx, step):
        device = ctx.device
        template_file = step["text"]
        template_path = os.path.join(self.templates_dir, template_file)
        if not os.path.exists(template_path):
            self.write_log(f"   ⚠️ [{device}] ไม่พบไฟล์เทมเพลต: {template_file}", "warning")
            return

        # ถ่ายภาพหน้าจอตรงเข้าหน่วยความจำ (exec-out, ไม่มีไฟล์ชั่วคราว)
        success, data = self.controller.capture_screenshot_bytes(device)
        if not success:
            self.write_log(f"   ❌ [{device}] ถ่ายภาพหน้าจอล้มเหลว: {data}", "error")
            return

        # ค้นหาตำแหน่งภาพ
        found, match_x, match_y, msg = self.controller.find_image_in_bytes(data, template_path, threshold=0.8)

        if found:
            self.write_log(f"   🎯 [{device}] พบรูป '{template_file}' พิกัด ({match_x}, {match_y}) -> กำลังคลิก", "success")
            self.controller.tap(device, match_x, match_y)
            if ctx.step_delay > 0:
                time.sleep(ctx.step_delay)
        else:
            self.write_log(f"   🔍 [{device}] ไม่พบรูป '{template_file}' บนจอ -> ข้ามขั้นตอนนี้", "info")

    def _step_wait_for_image(self, ctx, step):
        """รอจนกว่าจะเจอรูปบนหน้าจอ (มี timeout) แล้วค่อยทำต่อ — แทน sleep แบบตายตัว

        params ใน step: text=ชื่อไฟล์เทมเพลต, timeout=วินาทีรอสูงสุด,
        interval=ช่วงเช็ค (ดีฟอลต์ 1.0), threshold=ความเหมือน (ดีฟอลต์ 0.8),
        click=คลิกเมื่อเจอ (ดีฟอลต์ True), on_timeout='continue'|'fail'
        """
        device = ctx.device
        template_file = (step.get("text") or "").strip()
        if not template_file:
            self.write_log(f"   ⚠️ [{device}] wait_for_image: ไม่ได้ระบุไฟล์รูปภาพต้นแบบ -> ข้าม", "warning")
            return
        template_path = os.path.join(self.templates_dir, template_file)
        if not os.path.exists(template_path):
            self.write_log(f"   ⚠️ [{device}] ไม่พบไฟล์เทมเพลต: {template_file} -> ข้าม", "warning")
            return

        timeout = float(step.get("timeout", 30) or 30)
        interval = float(step.get("interval", 1.0) or 1.0)
        threshold = float(step.get("threshold", 0.8) or 0.8)
        click = step.get("click", True)
        on_timeout = (step.get("on_timeout") or "continue").lower()

        self.write_log(f"   ⏳ [{device}] รอจนกว่าจะเจอรูป '{template_file}' (สูงสุด {timeout:g} วิ)...", "info")
        deadline = time.time() + timeout

        while time.time() < deadline:
            if not self.macro_running:
                return "stop"

            success, data = self.controller.capture_screenshot_bytes(device)
            if success:
                found, mx, my, msg = self.controller.find_image_in_bytes(data, template_path, threshold=threshold)
                if found:
                    self.write_log(f"   🎯 [{device}] เจอรูป '{template_file}' พิกัด ({mx}, {my})", "success")
                    if click:
                        self.controller.tap(device, mx, my)
                    if ctx.step_delay > 0:
                        time.sleep(ctx.step_delay)
                    return
            else:
                self.write_log(f"   ❌ [{device}] ถ่ายภาพหน้าจอล้มเหลว: {data}", "error")

            # รอช่วง interval ก่อนเช็คอีกครั้ง (ตรวจสถานะหยุดถี่ๆ เพื่อยกเลิกได้ทันที)
            waited = 0.0
            while waited < interval:
                if not self.macro_running:
                    return "stop"
                time.sleep(0.1)
                waited += 0.1

        # หมดเวลาแล้วยังไม่เจอ
        self.write_log(f"   ⌛ [{device}] รอครบ {timeout:g} วิ แล้วยังไม่เจอรูป '{template_file}'", "warning")
        if on_timeout == "fail":
            ctx.record((False, f"wait_for_image timeout: {template_file}"), "wait_for_image")

    @staticmethod
    def _substitute_account(text, account):
        """แทนที่ {EMAIL}/{PASSWORD}/{NAME} ในข้อความด้วยข้อมูลบัญชี (ถ้ามี)"""
        if not account:
            return text
        return (text
                .replace("{EMAIL}", account.get("email", ""))
                .replace("{PASSWORD}", account.get("password", ""))
                .replace("{NAME}", account.get("name", "")))

    @staticmethod
    def _parse_ui_query(query):
        """แยกคำค้น element: ขึ้นต้น 'id:' = ค้นจาก resource-id, ไม่งั้นค้นจาก text"""
        query = (query or "").strip()
        if query.lower().startswith("id:"):
            return None, query[3:].strip()
        return query, None

    def _step_tap_text(self, ctx, step):
        """กดปุ่ม/element ตามข้อความหรือ resource-id (หน้าจอ Android ปกติ ไม่ใช่ในเกม)"""
        device = ctx.device
        query = self._substitute_account(step.get("text", ""), ctx.account)
        text, rid = self._parse_ui_query(query)
        if not text and not rid:
            self.write_log(f"   ⚠️ [{device}] tap_text: ไม่ได้ระบุข้อความ/id ที่จะค้นหา -> ข้าม", "warning")
            return

        ok, xml = self.controller.dump_ui(device)
        if not ok:
            self.write_log(f"   ⚠️ [{device}] อ่าน UI ไม่ได้: {xml}", "warning")
            return

        found, x, y, info = find_element_center(xml, text=text, resource_id=rid)
        if found:
            self.write_log(f"   🎯 [{device}] เจอ element ({info}) พิกัด ({x}, {y}) -> กำลังคลิก", "success")
            ctx.record(self.controller.tap(device, x, y), "tap_text")
            if ctx.step_delay > 0:
                time.sleep(ctx.step_delay)
        else:
            self.write_log(f"   🔍 [{device}] ไม่พบ element: {info} -> ข้ามขั้นตอนนี้", "info")

    def _step_wait_for_text(self, ctx, step):
        """รอจน element (text/id) โผล่บนจอ แล้วค่อยทำต่อ (มี timeout) — เหมือน wait_for_image แต่ใช้ uiautomator"""
        device = ctx.device
        query = self._substitute_account(step.get("text", ""), ctx.account)
        text, rid = self._parse_ui_query(query)
        if not text and not rid:
            self.write_log(f"   ⚠️ [{device}] wait_for_text: ไม่ได้ระบุข้อความ/id -> ข้าม", "warning")
            return

        timeout = float(step.get("timeout", 30) or 30)
        interval = float(step.get("interval", 1.0) or 1.0)
        click = step.get("click", True)
        on_timeout = (step.get("on_timeout") or "continue").lower()

        self.write_log(f"   ⏳ [{device}] รอจนเจอข้อความ/element '{query}' (สูงสุด {timeout:g} วิ)...", "info")
        deadline = time.time() + timeout

        while time.time() < deadline:
            if not self.macro_running:
                return "stop"

            ok, xml = self.controller.dump_ui(device)
            if ok:
                found, x, y, info = find_element_center(xml, text=text, resource_id=rid)
                if found:
                    self.write_log(f"   🎯 [{device}] เจอ element ({info}) พิกัด ({x}, {y})", "success")
                    if click:
                        self.controller.tap(device, x, y)
                    if ctx.step_delay > 0:
                        time.sleep(ctx.step_delay)
                    return

            waited = 0.0
            while waited < interval:
                if not self.macro_running:
                    return "stop"
                time.sleep(0.1)
                waited += 0.1

        self.write_log(f"   ⌛ [{device}] รอครบ {timeout:g} วิ แล้วยังไม่เจอ '{query}'", "warning")
        if on_timeout == "fail":
            ctx.record((False, f"wait_for_text timeout: {query}"), "wait_for_text")

    def _step_screenshot(self, ctx, step):
        device = ctx.device
        account = ctx.account
        filename_pattern = step.get("text", "").strip() or "screenshots/{DATE}/screenshot_{NAME}_{TIME}.png"

        # แทนที่ตัวแปร {EMAIL}, {PASSWORD}, {NAME}, {GROUP}, {DATE}, {TIME} ในชื่อไฟล์ภาพ
        filename = filename_pattern

        from datetime import datetime
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H-%M-%S")

        if account:
            filename = filename.replace("{EMAIL}", account.get("email", "no_account"))
            filename = filename.replace("{PASSWORD}", account.get("password", "no_password"))
            filename = filename.replace("{NAME}", account.get("name", ""))
            filename = filename.replace("{GROUP}", account.get("group", "no_group"))
        else:
            filename = filename.replace("{EMAIL}", "no_account")
            filename = filename.replace("{PASSWORD}", "no_password")
            filename = filename.replace("{NAME}", "no_name")
            filename = filename.replace("{GROUP}", "no_group")

        filename = filename.replace("{DATE}", date_str)
        filename = filename.replace("{TIME}", time_str)

        # ทำความสะอาดชื่อไฟล์ให้ปลอดภัยสำหรับ Windows (รองรับภาษาไทย อังกฤษ ตัวเลข และสัญลักษณ์ที่ปลอดภัย)
        safe_device = device.replace(":", "_").replace(".", "_")
        filename = filename.replace("{DEVICE}", safe_device)

        def is_safe_char(c):
            return c.isalnum() or c in "-_.() /\\" or ('฀' <= c <= '๿')

        filename = "".join(c for c in filename if is_safe_char(c))

        # หากไม่มีนามสกุล .png หรือ .jpg ให้เติม .png
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            filename += ".png"

        # สร้างโฟลเดอร์สำหรับเก็บภาพสกรีนช็อต
        screenshots_dir = os.path.dirname(os.path.abspath(filename))
        if screenshots_dir and not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir, exist_ok=True)

        # ถ่ายภาพหน้าจอ
        self.write_log(f"   📸 [{device}] กำลังบันทึกภาพหน้าจอเป็น '{filename}'...", "info")
        success, err = self.controller.take_screenshot(device, filename)
        if success:
            self.write_log(f"   ✅ [{device}] บันทึกภาพหน้าจอสำเร็จ: '{filename}'", "success")
        else:
            self.write_log(f"   ❌ [{device}] บันทึกภาพหน้าจอล้มเหลว: {err}", "error")

        if ctx.step_delay > 0:
            time.sleep(ctx.step_delay)

    def _step_clear_ads_loop(self, ctx, step):
        device = ctx.device
        step_delay = ctx.step_delay
        step_text = step.get("text", "").strip()
        lobby_template = ""
        ad_templates = []

        if "|" in step_text:
            parts = step_text.split("|")
            lobby_template = parts[0].strip()
            ad_templates = [p.strip() for p in parts[1].split(",") if p.strip()]
        else:
            if step_text.endswith(".png"):
                lobby_template = step_text
            elif step_text:
                ad_templates = [p.strip() for p in step_text.split(",") if p.strip()]

        # ถ้าไม่ระบุรูปภาพปุ่มปิดโฆษณา ให้ดึงไฟล์ .png ทั้งหมดในโฟลเดอร์ยกเว้นรูปหน้าหลัก รูปชั่วคราว และรูปที่มีคีย์เวิร์ดบ่งบอกว่าเป็นหน้าหลัก
        if not ad_templates:
            import glob
            all_pngs = [os.path.basename(f) for f in glob.glob(os.path.join(self.templates_dir, "*.png"))]
            ad_templates = [
                f for f in all_pngs
                if f != lobby_template
                and not f.startswith("temp_")
                and not any(k in f.lower() for k in ["lobby", "home", "main", "start"])
            ]

        self.write_log(f"   🔄 [{device}] เริ่มรันลูปเคลียร์โฆษณา (หน้าจอหลักเป้าหมาย: '{lobby_template or 'ไม่ได้ตั้งค่า'}')", "info")
        if ad_templates:
            self.write_log(f"   🔍 [{device}] รายการรูปปุ่มปิดที่จะตรวจจับ: {', '.join(ad_templates)}", "info")

        max_attempts = 15
        for attempt in range(max_attempts):
            if not self.macro_running:
                break

            # ถ่ายภาพหน้าจอตรงเข้าหน่วยความจำ (exec-out, ไม่มีไฟล์ชั่วคราว)
            success, data = self.controller.capture_screenshot_bytes(device)
            if not success:
                self.write_log(f"   ❌ [{device}] ถ่ายภาพหน้าจอล้มเหลว: {data}", "error")
                break

            # 1. ตรวจสอบว่ามาถึงหน้าจอหลัก/เริ่มต้น (Lobby) หรือยัง
            reached_lobby = False
            lobby_msg = ""
            if lobby_template:
                lobby_path = os.path.join(self.templates_dir, lobby_template)
                if os.path.exists(lobby_path):
                    found_lobby, lx, ly, lmsg = self.controller.find_image_in_bytes(data, lobby_path, threshold=0.7)
                    lobby_msg = lmsg
                    if found_lobby:
                        self.write_log(f"   🎉 [{device}] รอบที่ {attempt+1}: ตรวจพบหน้าจอหลัก/เริ่มต้น '{lobby_template}' -> โฆษณาเคลียร์หมดแล้ว!", "success")
                        reached_lobby = True

            if reached_lobby:
                break

            # 2. ตรวจสอบปุ่มปิดโฆษณาเพื่อกดปิด
            found_ad = False
            for template_file in ad_templates:
                template_path = os.path.join(self.templates_dir, template_file)
                if not os.path.exists(template_path):
                    continue

                found, match_x, match_y, msg = self.controller.find_image_in_bytes(data, template_path, threshold=0.7)
                if found:
                    self.write_log(f"   🎯 [{device}] รอบที่ {attempt+1}: พบรูปปุ่มปิด '{template_file}' พิกัด ({match_x}, {match_y}) -> กำลังคลิก", "success")
                    self.controller.tap(device, match_x, match_y)
                    found_ad = True
                    if step_delay > 0:
                        time.sleep(step_delay)
                    break

            # 3. หากไม่พบปุ่มปิดใดๆ และยังไม่ถึงหน้าหลัก ให้ส่งปุ่ม BACK ย้อนกลับเป็นทางเลือกสำรอง
            if not found_ad:
                if lobby_template:
                    conf_info = ""
                    if "confidence:" in lobby_msg:
                        try:
                            conf_val = lobby_msg.split("confidence:")[1].strip().replace(")", "")
                            conf_info = f" (ความเหมือนสูงสุด: {conf_val})"
                        except Exception:
                            pass
                    self.write_log(f"   🔍 [{device}] รอบที่ {attempt+1}: ไม่พบหน้าหลัก '{lobby_template}'{conf_info} และไม่พบปุ่มปิด -> ส่งปุ่มย้อนกลับ (BACK)", "warning")
                    self.controller.keyevent(device, 4)
                    if step_delay > 0:
                        time.sleep(step_delay)
                else:
                    # ถ้าไม่ได้ตั้งรูปหน้าจอหลัก และไม่เจอปุ่มปิดใดๆ อีก ให้ถือว่าเคลียร์เสร็จสิ้น
                    self.write_log(f"   ✅ [{device}] เคลียร์โฆษณาเรียบร้อยแล้ว (ไม่พบโฆษณาบนจอ)", "success")
                    break
        else:
            self.write_log(f"   ⚠️ [{device}] ทำงานลูปเคลียร์โฆษณาครบ {max_attempts} รอบแล้ว (สิ้นสุดลูป)", "warning")

    def _step_fetch_otp(self, ctx, step):
        device = ctx.device
        account = ctx.account
        if not account:
            self.write_log(f"   ⚠️ [{device}] ข้ามขั้นตอนดึง OTP เนื่องจากรันแบบไม่มีบัญชีไอดี", "warning")
            return

        email_addr = account.get("email", "").strip()
        email_pass = account.get("password", "").strip()
        ref_token = account.get("refresh_token", "").strip()
        cli_id = account.get("client_id", "").strip()

        self.write_log(f"   📥 [{device}] กำลังเชื่อมต่อดึงรหัส OTP ของบัญชี {email_addr}...", "info")

        pattern_str = step.get("text", "").strip()
        otp_code = self.fetch_otp_from_mail(email_addr, email_pass, pattern_str, refresh_token=ref_token, client_id=cli_id)

        if otp_code:
            self.write_log(f"   ✅ [{device}] ดึงรหัส OTP สำเร็จ: {otp_code} -> กำลังกรอกรหัสลงบนจอ", "success")
            ctx.record(self.controller.input_text(device, otp_code), "fetch_otp")
            if ctx.step_delay > 0:
                time.sleep(ctx.step_delay)
        else:
            self.write_log(f"   ❌ [{device}] ไม่สามารถดึงรหัส OTP ได้หลังจากสแกนกล่องข้อความ", "error")

    def _step_sleep(self, ctx, step):
        sleep_time = float(step["seconds"]) * random.uniform(0.85, 1.2)
        slices = int(sleep_time / 0.1)
        for _ in range(slices):
            if not self.macro_running:
                return "stop"
            time.sleep(0.1)
        time.sleep(sleep_time % 0.1)

    def _step_keyboard(self, ctx, step):
        key_name = step.get("key", "").strip().lower()
        action = step.get("action", "").strip().lower()
        self.write_log(f"   ⌨️ [{ctx.device}] ส่งปุ่มคีย์บอร์ด: '{key_name}' ({action})", "info")
        self.execute_keyboard_input(ctx.device, key_name, action)
        if ctx.step_delay > 0:
            time.sleep(ctx.step_delay)

    def _verify_diamond_identity(self, device, account, who, data):
        """ยืนยันว่า 'จอนี้คือบัญชีที่ถูกต้อง และอยู่หน้า Home จริง' ก่อนเขียนเพชร
        OCR ชื่อในเกมมุมซ้ายบน เทียบกับ ingamename ของบัญชี — ลองซ้ำได้ (จออาจยังโหลด/ยังไม่นิ่ง)

        คืน (ok, data_ล่าสุด) — ok=False = ไม่ควรเขียนเพชร (log เหตุผลไว้แล้ว)
        ปิดการตรวจได้ด้วย diamond_config['verify_name']=False (หรือบัญชีไม่มี ingamename = เตือนแล้วปล่อยผ่าน)
        """
        cfg = self.diamond_config or {}
        if not cfg.get("verify_name", True):
            return True, data  # ปิดการตรวจ -> เขียนเลย (พฤติกรรมเดิม)

        expected = (account.get("ingamename") or account.get("name") or "").strip()
        if not expected:
            self.write_log(f"   ⚠️ [{device}] {who}: บัญชีไม่มี ingamename เทียบ -> ข้ามการยืนยัน (เขียนแบบ best-effort)", "warning")
            return True, data

        name_region = cfg.get("name_region") or {"x": 90, "y": 18, "w": 140, "h": 26}
        min_ratio = float(cfg.get("name_match_ratio", 0.72) or 0.72)
        langs = available_tesseract_langs()
        lang = "tha+eng" if "tha" in langs else "eng"

        last_seen = ""
        for attempt in range(3):
            ok, txt, _ = ocr_text_tesseract(data, region=name_region, lang=lang, psm=7, scale=3)
            seen = (txt or "").strip().replace("\n", " ")
            if seen:
                last_seen = seen
            if ok and seen and names_match(expected, seen, min_ratio=min_ratio):
                return True, data
            # ยังไม่ตรง -> รอจอนิ่งแล้วแคปใหม่ (สูงสุด 3 ครั้ง)
            if attempt < 2:
                time.sleep(1.5)
                cok, cdata = self.controller.capture_screenshot_bytes(device)
                if cok:
                    data = cdata

        self.write_log(
            f"   ⛔ [{device}] {who}: ชื่อในเกมไม่ตรงกับบัญชี (คาด '{expected}' เห็น '{last_seen or '—'}') "
            f"-> ไม่เขียนเพชร (กันข้อมูลเพี้ยน/ผิดบัญชี)", "error")
        return False, data

    def _step_read_diamond(self, ctx, step):
        """อ่านจำนวนเพชรของแอคเคานต์รอบนี้ แล้วเก็บไว้ (จะ export/push เข้าเว็บตอนจบรัน)

        ถ้าอ่านไม่ได้ (ยังไม่ตั้งพื้นที่ / ไม่มี Tesseract / แคปจอพลาด / OCR พลาด)
        จะ log แล้ว 'ข้าม' ไปทำ step ต่อไป — ไม่นับเป็น error ของบัญชีและไม่หยุดลูป
        """
        from datetime import datetime
        device = ctx.device
        account = ctx.account or {}
        region = (self.diamond_config or {}).get("region") or {}
        who = account_display_name(account) if account else "no_account"

        # เงื่อนไขที่อ่านไม่ได้ -> ข้าม (ไม่ใช้ ctx.record เพื่อไม่ให้บัญชีถูกตีว่า error)
        if int(region.get("w", 0)) <= 0 or int(region.get("h", 0)) <= 0:
            self.write_log(f"   ⏭️ [{device}] อ่านเพชร: ยังไม่ได้ตั้งพื้นที่ตัวเลขเพชร (ปุ่ม ⚙️ ตั้งค่าพื้นที่เพชร) -> ข้าม", "warning")
            return
        if not find_tesseract():
            self.write_log(f"   ⏭️ [{device}] อ่านเพชร: ไม่พบ Tesseract OCR -> ข้าม", "warning")
            return

        ok, data = self.controller.capture_screenshot_bytes(device)
        if not ok:
            self.write_log(f"   ⏭️ [{device}] {who}: อ่านเพชรไม่ได้ (แคปจอไม่สำเร็จ) -> ข้าม", "warning")
            return

        # ===== ยาม: ยืนยันตัวตนก่อนเขียนเพชร (กันอ่านผิดจอ/เขียนผิดบัญชี) =====
        # OCR ชื่อในเกมมุมซ้ายบน เทียบกับ ingamename ของบัญชีที่ควรอยู่จอนี้ — ลองซ้ำได้ (จออาจยังโหลด)
        verify_ok, data = self._verify_diamond_identity(device, account, who, data)
        if not verify_ok:
            return  # log อธิบายเหตุผลไว้ในเมธอดแล้ว (ไม่เขียนเพชร)

        rok, number, _raw = self.controller.read_number_tesseract(data, region)
        if not rok or number is None:
            self.write_log(f"   ⏭️ [{device}] {who}: OCR อ่านจำนวนเพชรไม่ได้ -> ข้าม", "warning")
            return

        row = {
            "email": account.get("email", ""),
            "name": account_display_name(account),
            "save_web_game_id": (account.get("save_web_game_id") or "").strip(),
            "diamonds": number,
            "device": device,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        lock = getattr(self, "run_diamond_lock", None)
        if not hasattr(self, "run_diamond_rows"):
            self.run_diamond_rows = []
        if lock is not None:
            with lock:
                self.run_diamond_rows.append(row)
        else:
            self.run_diamond_rows.append(row)
        self.write_log(f"   💎 [{device}] {who}: {number} เพชร (จะอัพเดทเข้าเว็บตอนจบรัน)", "success")
        if ctx.step_delay > 0:
            time.sleep(ctx.step_delay)

    def execute_keyboard_input(self, device, key_name, action):
        import ctypes
        
        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        GetWindowText = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible
        
        found_windows = []
        
        def foreach_window(hwnd, lParam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLength(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                title = buff.value
                title_lower = title.lower()
                if any(k in title_lower for k in ["mumu player", "nemu", "มูมู่"]):
                    found_windows.append((hwnd, title))
            return True
            
        EnumWindows(EnumWindowsProc(foreach_window), 0)
        
        if not found_windows:
            self.write_log("   ⚠️ ไม่พบหน้าต่างโปรแกรม Emulator บน Windows เพื่อส่งปุ่มกด", "warning")
            return
            
        selected_devices = self.get_selected_devices()
        if not selected_devices:
            selected_devices = self.controller.get_connected_devices()
            
        if not selected_devices:
            return
            
        sorted_devices = sorted(selected_devices)
        sorted_windows = sorted(found_windows, key=lambda w: w[1])
        
        target_hwnd = None
        for i, dev in enumerate(sorted_devices):
            if dev == device and i < len(sorted_windows):
                target_hwnd = sorted_windows[i][0]
                break
                
        if not target_hwnd:
            target_hwnd = sorted_windows[0][0]
            
        VK_CODES = {
            "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
            "space": 0x20, "enter": 0x0D, "escape": 0x1B,
            "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
            "f": 0x46, "g": 0x47, "h": 0x48, "j": 0x4A, "k": 0x4B, "l": 0x4C,
            "z": 0x5A, "x": 0x58, "c": 0x43, "v": 0x56, "b": 0x42, "n": 0x4E, "m": 0x4D,
            "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
            "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
            "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B
        }
        
        vk_code = VK_CODES.get(key_name)
        if not vk_code:
            if len(key_name) == 1:
                vk_code = ord(key_name.upper())
            else:
                self.write_log(f"   ⚠️ ไม่พบรหัสจำลองของปุ่ม '{key_name}' กรุณาใช้ปุ่มมาตรฐาน", "warning")
                return
                
        child_hwnds = []
        def enum_child_proc(hwnd, lParam):
            child_hwnds.append(hwnd)
            return True
        EnumChildWindows = ctypes.windll.user32.EnumChildWindows
        EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        EnumChildWindows(target_hwnd, EnumChildProc(enum_child_proc), 0)
        
        all_hwnds = [target_hwnd] + child_hwnds
        
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        PostMessage = ctypes.windll.user32.PostMessageW
        
        if action == "down":
            for h in all_hwnds:
                PostMessage(h, WM_KEYDOWN, vk_code, 0)
        elif action == "up":
            for h in all_hwnds:
                PostMessage(h, WM_KEYUP, vk_code, 0)
        else: # "press"
            for h in all_hwnds:
                PostMessage(h, WM_KEYDOWN, vk_code, 0)
            time.sleep(0.05)
            for h in all_hwnds:
                PostMessage(h, WM_KEYUP, vk_code, 0)
