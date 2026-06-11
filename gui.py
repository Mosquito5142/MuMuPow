import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import glob
import sys
from mumu_controller import MuMuController

# จานสีสำหรับธีมมืดระดับพรีเมียม (Premium Dark Theme Color Palette)
BG_DARK = "#121212"
BG_PANEL = "#1c1c1c"
BG_CARD = "#262626"
BG_INPUT = "#333333"
FG_WHITE = "#FFFFFF"
FG_MUTED = "#AAAAAA"
ACCENT_BLUE = "#007ACC"
ACCENT_HOVER = "#0098FF"
ACCENT_GREEN = "#2ECC71"
ACCENT_RED = "#E74C3C"
ACCENT_ORANGE = "#E67E22"

class ModernButton(tk.Button):
    """ปุ่มกดสไตล์โมเดิร์นพร้อมแอนิเมชันตอนเอาเมาส์ชี้"""
    def __init__(self, parent, text, command=None, bg=ACCENT_BLUE, fg=FG_WHITE, activebg=ACCENT_HOVER, **kwargs):
        button_font = kwargs.pop("font", ("Segoe UI", 10, "bold"))
        px = kwargs.pop("padx", 10)
        py = kwargs.pop("pady", 5)
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
        self.bind("<Enter>", lambda e: self.configure(bg=activebg))
        self.bind("<Leave>", lambda e: self.configure(bg=bg))

class ModernEntry(tk.Entry):
    """ช่องกรอกข้อความสไตล์โมเดิร์น"""
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            bg=BG_INPUT,
            fg=FG_WHITE,
            insertbackground=FG_WHITE,
            relief="flat",
            bd=1,
            highlightthickness=1,
            highlightbackground="#444444",
            highlightcolor=ACCENT_BLUE,
            font=("Segoe UI", 10),
            **kwargs
        )

class MuMuGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MuMupow - โปรแกรมควบคุมและบอทจำลองหน้าจอพร้อมกันหลายจอ")
        self.geometry("1100x700")
        self.configure(bg=BG_DARK)

        # เริ่มต้นโมดูลควบคุม
        self.controller = MuMuController()
        self.macro_thread = None
        self.macro_running = False

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
        self.templates_dir = os.path.join(base_dir, "templates")
        os.makedirs(self.templates_dir, exist_ok=True)

        # ตัวแปรสำหรับการรันแบบแบ่งเซ็ต
        self.pause_between_sets = tk.BooleanVar(value=False)
        self.is_paused_waiting_for_next_set = False
        self.remaining_accounts = []
        self.active_devices_for_run = []

        # ตัวแปรสำหรับการจัดการบัญชีผู้ใช้
        self.accounts = []
        self.accounts_file = os.path.join(base_dir, "accounts.json")
        self.ports_file = os.path.join(base_dir, "ports.json")
        self.account_checkboxes = {} # email -> BooleanVar
        self.group_checkboxes = {}   # group_name -> BooleanVar
        self.load_accounts()

        # ตัวแปรสำหรับการเลือกอุปกรณ์ Emulator
        self.device_checkboxes = {} # device_id -> BooleanVar
        self.device_frames = {}     # device_id -> tk.Frame

        # กำหนดสไตล์วิดเจ็ตมาตรฐาน
        self.setup_styles()

        # สร้างโครงสร้างหน้าตาโปรแกรม
        self.build_layout()

        # แก้ไขปัญหาคีย์บอร์ดไทยไม่รองรับ Ctrl+C / Ctrl+V
        self.setup_thai_hotkeys()

        # ตรวจสอบ ADB และสแกนอุปกรณ์เริ่มต้น
        self.write_log(f"⚡ เริ่มต้นระบบควบคุม MuMupow แล้ว เส้นทาง ADB: {self.controller.adb_path}", "success")
        self.scan_devices()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("default")
        
        # ปรับแต่งแถบแท็บ (Notebook)
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", 
                        background=BG_PANEL, 
                        foreground=FG_MUTED, 
                        padding=[15, 6], 
                        font=("Segoe UI", 10, "bold"),
                        borderwidth=0)
        style.map("TNotebook.Tab", 
                  background=[("selected", BG_DARK)], 
                  foreground=[("selected", FG_WHITE)])

        # ปรับแต่งแถบเลื่อน (Scrollbar)
        style.configure("TScrollbar", gripcount=0, background=BG_PANEL, troughcolor=BG_DARK, borderwidth=0)

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
        header = tk.Frame(self, bg=BG_PANEL, height=60)
        header.pack(fill="x", side="top")
        
        title_lbl = tk.Label(header, text="ระบบควบคุม Emulator หลายจอพร้อมกัน (MuMupow)", bg=BG_PANEL, fg=FG_WHITE, font=("Segoe UI", 16, "bold"))
        title_lbl.pack(side="left", padx=20, pady=15)
        
        subtitle_lbl = tk.Label(header, text="พิกัดหน้าจอเป้าหมาย: กว้าง 960 / สูง 540 | DPI: 160", bg=BG_PANEL, fg=ACCENT_BLUE, font=("Segoe UI", 10, "italic"))
        subtitle_lbl.pack(side="left", pady=22)

        # 2. พื้นที่เนื้อหาหลัก (แบ่งเป็น แถบซ้ายมือ และ แผงฟังก์ชันหลักขวามือ)
        content_frame = tk.Frame(self, bg=BG_DARK)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # สร้างแถบด้านซ้ายจัดการอุปกรณ์
        self.build_sidebar(content_frame)

        # สร้างแถบแท็บด้านขวาสำหรับฟังก์ชันต่างๆ
        self.build_tabs_panel(content_frame)

        # 3. แผงคอนโซล Log บันทึกระบบด้านล่างสุด
        self.build_log_panel()

    def build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=BG_PANEL, width=280)
        sidebar.pack(fill="y", side="left", padx=(0, 10))
        sidebar.pack_propagate(False)

        # หัวข้อแถบซ้าย
        lbl = tk.Label(sidebar, text="จัดการอุปกรณ์ Emulator", bg=BG_PANEL, fg=FG_WHITE, font=("Segoe UI", 12, "bold"))
        lbl.pack(fill="x", padx=15, pady=(15, 10), anchor="w")

        # ปุ่มแสกนพอร์ตหลัก
        btn_frame = tk.Frame(sidebar, bg=BG_PANEL)
        btn_frame.pack(fill="x", padx=15, pady=5)

        scan_btn = ModernButton(btn_frame, text="🔍 สแกนพอร์ตอัตโนมัติ", command=self.scan_devices, bg=ACCENT_BLUE, activebg=ACCENT_HOVER)
        scan_btn.pack(fill="x", side="top", pady=2)

        # กล่องสำหรับระบุพอร์ตเองแมนนวล
        conn_frame = tk.Frame(sidebar, bg=BG_PANEL)
        conn_frame.pack(fill="x", padx=15, pady=10)
        
        tk.Label(conn_frame, text="เชื่อมต่อด้วย IP:Port เอง", bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        self.manual_port_entry = ModernEntry(conn_frame)
        self.manual_port_entry.pack(fill="x", side="left", expand=True, pady=5, padx=(0, 5))
        self.manual_port_entry.insert(0, "127.0.0.1:7555")

        connect_btn = ModernButton(conn_frame, text="เชื่อมต่อ", command=self.manual_connect, bg=ACCENT_GREEN, activebg="#2ecc71")
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
        
        self.device_canvas.create_window((0, 0), window=self.device_scroll_frame, anchor="nw", width=230)
        self.device_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.device_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(self.device_canvas)

    def build_tabs_panel(self, parent):
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True, side="right")

        # แท็บ 1: ระบบจัดการบอทมาโครแบบกำหนดเอง
        macro_tab = tk.Frame(self.notebook, bg=BG_DARK)
        self.notebook.add(macro_tab, text=" 📥 บอทล็อกอินและปิดโฆษณา ")
        self.build_macro_tab(macro_tab)

        # แท็บ 2: แผงจัดการบัญชีผู้ใช้
        accounts_tab = tk.Frame(self.notebook, bg=BG_DARK)
        self.notebook.add(accounts_tab, text=" 👥 จัดการบัญชี ")
        self.build_accounts_tab(accounts_tab)

        # แท็บ 3: แผงควบคุมแมนนวลแบบ Broadcast
        sync_tab = tk.Frame(self.notebook, bg=BG_DARK)
        self.notebook.add(sync_tab, text=" 🖱️ สั่งการพร้อมกันแบบแมนนวล ")
        self.build_sync_tab(sync_tab)

        # แท็บ 4: ตั้งค่าระบบ
        settings_tab = tk.Frame(self.notebook, bg=BG_DARK)
        self.notebook.add(settings_tab, text=" ⚙️ ตั้งค่าโปรแกรม ")
        self.build_settings_tab(settings_tab)

    def build_macro_tab(self, parent):
        parent.configure(bg=BG_DARK)
        
        main_pane = tk.Frame(parent, bg=BG_DARK)
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)
        
        # ฝั่งซ้าย: รายการขั้นตอนในโปรไฟล์บอท (Left Panel)
        left_panel = tk.LabelFrame(main_pane, text=" 📜 ลำดับขั้นตอนคำสั่งมาโคร ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=10, pady=10)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        # การเลือกโปรไฟล์เก็บข้อมูล
        prof_lbl_frame = tk.Frame(left_panel, bg=BG_DARK)
        prof_lbl_frame.pack(fill="x", pady=(0, 5))
        
        tk.Label(prof_lbl_frame, text="เลือกโปรไฟล์มาโคร:", bg=BG_DARK, fg=FG_WHITE).pack(side="left", anchor="w")
        
        self.profile_cb = ttk.Combobox(prof_lbl_frame, state="readonly", width=20)
        self.profile_cb.pack(side="left", padx=5)
        self.profile_cb.bind("<<ComboboxSelected>>", self.on_profile_select)
        
        # ฟิลด์ป้อนชื่อบันทึกโปรไฟล์
        prof_act_frame = tk.Frame(left_panel, bg=BG_DARK)
        prof_act_frame.pack(fill="x", pady=5)
        
        tk.Label(prof_act_frame, text="ชื่อโปรไฟล์:", bg=BG_DARK, fg=FG_WHITE).pack(side="left")
        self.profile_name_entry = ModernEntry(prof_act_frame, width=15)
        self.profile_name_entry.pack(side="left", padx=5)
        self.profile_name_entry.insert(0, "default_login_ads")
        
        ModernButton(prof_act_frame, text="💾 บันทึก", command=self.save_profile, bg=ACCENT_GREEN, activebg="#2ecc71").pack(side="left", padx=2)
        ModernButton(prof_act_frame, text="🗑️ ลบไฟล์", command=self.delete_profile, bg=ACCENT_RED, activebg="#c0392b").pack(side="left", padx=2)
        
        # ลิสต์ขั้นตอนการทำงาน (Listbox)
        list_frame = tk.Frame(left_panel, bg=BG_DARK)
        list_frame.pack(fill="both", expand=True, pady=5)
        
        self.step_listbox = tk.Listbox(list_frame, bg=BG_PANEL, fg=FG_WHITE, selectbackground=ACCENT_BLUE, selectforeground=FG_WHITE, bd=0, highlightthickness=0, font=("Consolas", 10))
        self.step_listbox.pack(side="left", fill="both", expand=True)
        self.step_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.step_listbox.yview)
        self.step_listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        
        # ปุ่มจัดลำดับย้ายขึ้น/ลง
        reorder_frame = tk.Frame(left_panel, bg=BG_DARK)
        reorder_frame.pack(fill="x", pady=(5, 0))
        
        ModernButton(reorder_frame, text="▲ เลื่อนขึ้น", command=lambda: self.move_step(-1), bg=BG_INPUT, activebg="#444444").pack(side="left", fill="x", expand=True, padx=2)
        ModernButton(reorder_frame, text="▼ เลื่อนลง", command=lambda: self.move_step(1), bg=BG_INPUT, activebg="#444444").pack(side="left", fill="x", expand=True, padx=2)
        ModernButton(reorder_frame, text="❌ ลบขั้นตอนนี้", command=self.delete_step, bg=ACCENT_RED, activebg="#c0392b").pack(side="right", padx=2)
        
        # ฝั่งขวา: ฟอร์มป้อน/แก้ไขขั้นตอนคำสั่งการบอท (Right Panel)
        right_panel = tk.Frame(main_pane, bg=BG_DARK, width=340)
        right_panel.pack(side="right", fill="both")
        right_panel.pack_propagate(False)
        
        # เพิ่ม scrollable canvas ให้กับ right_panel เพื่อให้เลื่อนดูฟอร์มและปุ่มรันด้านล่างได้หากความสูงหน้าจอต่ำ
        right_canvas = tk.Canvas(right_panel, bg=BG_DARK, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=right_canvas.yview)
        
        right_scroll_frame = tk.Frame(right_canvas, bg=BG_DARK)
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
                "ล้างข้อมูลแอป (Clear App Data)",
                "ตรวจจับรูปภาพ (Image Match)"
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
        self.form_sleep.insert(0, "0.5")
        
        # คำอธิบายขั้นตอน
        tk.Label(form_panel, text="คำอธิบายขั้นตอน:", bg=BG_DARK, fg=FG_WHITE).grid(row=6, column=0, sticky="w", pady=5)
        self.form_desc = ModernEntry(form_panel, width=20)
        self.form_desc.grid(row=6, column=1, sticky="w", padx=10, pady=5)
        self.form_desc.insert(0, "คลิกช่อง Email")
        
        # ปุ่มดำเนินการฟอร์ม
        form_btn_frame = tk.Frame(form_panel, bg=BG_DARK)
        form_btn_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=15)
        
        ModernButton(form_btn_frame, text="➕ เพิ่มขั้นตอน", command=self.add_step, bg=ACCENT_BLUE, activebg=ACCENT_HOVER).pack(side="left", fill="x", expand=True, padx=2)
        ModernButton(form_btn_frame, text="✏️ อัปเดตขั้นตอนที่เลือก", command=self.update_step, bg=ACCENT_ORANGE, activebg="#d35400").pack(side="left", fill="x", expand=True, padx=2)
        ModernButton(form_btn_frame, text="🧹 ล้าง", command=self.clear_form, bg=BG_INPUT, activebg="#444444").pack(side="right", padx=2)
        
        form_panel.columnconfigure(0, weight=1)
        form_panel.columnconfigure(1, weight=2)
        
        # ปุ่มสำหรับสั่งรันคำสั่งบอทมาโคร
        run_card = tk.Frame(right_scroll_frame, bg=BG_DARK)
        run_card.pack(fill="x")
        
        self.pause_chk = tk.Checkbutton(
            run_card,
            text="⏸️ หยุดรอตรวจทานทีละชุด (Pause between sets)",
            variable=self.pause_between_sets,
            bg=BG_DARK,
            fg=FG_WHITE,
            activebackground=BG_DARK,
            activeforeground=FG_WHITE,
            selectcolor=BG_DARK,
            relief="flat",
            font=("Segoe UI", 10)
        )
        self.pause_chk.pack(anchor="w", pady=5)
        
        self.run_macro_btn = ModernButton(
            run_card, 
            text="🚀 รันคำสั่งบอทมาโครที่เลือก", 
            command=self.start_macro_flow, 
            bg=ACCENT_GREEN, 
            activebg="#2ecc71",
            font=("Segoe UI", 11, "bold"),
            height=2
        )
        self.run_macro_btn.pack(fill="x", pady=2)
        
        self.stop_macro_btn = ModernButton(
            run_card, 
            text="🛑 หยุดการทำงานของบอททันที", 
            command=self.stop_macro_flow, 
            bg=ACCENT_RED, 
            activebg="#c0392b",
            font=("Segoe UI", 11, "bold"),
            height=2
        )
        self.stop_macro_btn.pack(fill="x", pady=2)
        self.stop_macro_btn.configure(state="disabled")
        
        # ปรับสถานะฟอร์มตามดร็อปดาวน์เริ่มต้น
        self.on_step_type_change()
        
        # โหลดรายชื่อโปรไฟล์จากโฟลเดอร์เก็บข้อมูลมาโคร
        self.load_profiles()

    def build_accounts_tab(self, parent):
        parent.configure(bg=BG_DARK)
        
        main_pane = tk.Frame(parent, bg=BG_DARK)
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)
        
        # ฝั่งซ้าย: รายการบัญชีบอททั้งหมด (Left Panel)
        left_panel = tk.LabelFrame(main_pane, text=" 👥 รายการบัญชีบอททั้งหมด ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=10, pady=10)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        # กล่องรายการบัญชีพร้อม Scrollbar
        list_container = tk.Frame(left_panel, bg=BG_DARK, bd=0)
        list_container.pack(fill="both", expand=True, pady=5)
        
        self.acc_canvas = tk.Canvas(list_container, bg=BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.acc_canvas.yview)
        
        self.acc_scroll_frame = tk.Frame(self.acc_canvas, bg=BG_DARK)
        self.acc_scroll_frame.bind(
            "<Configure>", 
            lambda e: self.acc_canvas.configure(scrollregion=self.acc_canvas.bbox("all"))
        )
        
        self.acc_canvas.create_window((0, 0), window=self.acc_scroll_frame, anchor="nw", width=340)
        self.acc_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.acc_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(self.acc_canvas)
        
        # ฝั่งขวา: ฟอร์มเพิ่มบัญชีใหม่และคู่มือรันบอทวนลูป (Right Panel)
        right_panel = tk.Frame(main_pane, bg=BG_DARK, width=340)
        right_panel.pack(side="right", fill="both")
        right_panel.pack_propagate(False)
        
        # เพิ่ม scrollable canvas ให้กับ right_panel เพื่อให้เลื่อนดูฟอร์มและคู่มือด้านล่างได้หากความสูงหน้าจอต่ำ
        right_canvas = tk.Canvas(right_panel, bg=BG_DARK, highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=right_canvas.yview)
        
        right_scroll_frame = tk.Frame(right_canvas, bg=BG_DARK)
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
        add_box = tk.LabelFrame(right_scroll_frame, text=" ➕ เพิ่มบัญชีใหม่ ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        add_box.pack(fill="x", pady=(0, 15))
        
        tk.Label(add_box, text="อีเมล / ไอดีเกม:", bg=BG_DARK, fg=FG_WHITE).grid(row=0, column=0, sticky="w", pady=5)
        self.new_acc_email = ModernEntry(add_box, width=22)
        self.new_acc_email.grid(row=0, column=1, padx=10, pady=5)
        self.new_acc_email.insert(0, "test_user02@gmail.com")
        
        tk.Label(add_box, text="รหัสผ่าน (Password):", bg=BG_DARK, fg=FG_WHITE).grid(row=1, column=0, sticky="w", pady=5)
        self.new_acc_pass = ModernEntry(add_box, width=22)
        self.new_acc_pass.grid(row=1, column=1, padx=10, pady=5)
        self.new_acc_pass.insert(0, "test_pass02")

        tk.Label(add_box, text="กลุ่มบัญชี (Group):", bg=BG_DARK, fg=FG_WHITE).grid(row=2, column=0, sticky="w", pady=5)
        self.new_acc_group = ModernEntry(add_box, width=22)
        self.new_acc_group.grid(row=2, column=1, padx=10, pady=5)
        self.new_acc_group.insert(0, "ทั่วไป")
        
        ModernButton(add_box, text="➕ เพิ่มบัญชีเข้าคิว", command=self.add_account, bg=ACCENT_GREEN, activebg="#2ecc71").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(15, 0))
        
        add_box.columnconfigure(0, weight=1)
        add_box.columnconfigure(1, weight=2)
        
        # คู่มือการรันวนลูปหลายรหัส
        info_box = tk.LabelFrame(right_scroll_frame, text=" 🔄 คู่มือการรันวนลูปหลายรหัส ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        info_box.pack(fill="both", expand=True)
        
        info_text = (
            "1. เพิ่มอีเมลและรหัสผ่านทั้งหมดที่คุณต้องการรันบอทในช่องด้านบน\n\n"
            "2. ติ๊กเลือกที่เครื่องหมายถูกหน้าไอดีที่คุณต้องการสั่งให้บอทรันในรายการฝั่งซ้าย\n\n"
            "3. ในสคริปต์มาโครของคุณ (หน้าแท็บแรก) ให้ใช้ข้อความแทนตัวแปรดังนี้:\n"
            "   - ใช้คำว่า {EMAIL} ในขั้นตอนการกรอกอีเมล\n"
            "   - ใช้คำว่า {PASSWORD} ในขั้นตอนการกรอกรหัสผ่าน\n"
            "   *โปรแกรมจะดึงรหัสที่ติ๊กไว้มาสลับพิมพ์ให้ทีละรอบอัตโนมัติ*\n\n"
            "4. แนะนำให้ใส่ขั้นตอน 'ล้างข้อมูลแอป' หรือ 'เปิดแอป' ในสคริปต์มาโคร เพื่อเป็นการรีเซ็ตหน้าจอเกมเตรียมตัวสำหรับการเข้าสู่ระบบรหัสถัดไปในรอบใหม่\n\n"
            "5. ติ๊กหน้าจอ Emulator ด้านซ้ายสุดที่ต้องการควบคุม แล้วกดรันมาโครได้เลย!"
        )
        tk.Label(info_box, text=info_text, bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9), justify="left", wraplength=300).pack(anchor="w")
        
        # วาดรายการบัญชีที่มีอยู่
        self.refresh_accounts_ui()

    def build_sync_tab(self, parent):
        # สร้าง Canvas และ Scrollbar เพื่อให้แท็บควบคุมแมนนวลเลื่อนขึ้น-ลงได้
        canvas = tk.Canvas(parent, bg=BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        
        # แท็บสำหรับการคลิก/พิมพ์ แบบเรียลไทม์
        sync_frame = tk.Frame(canvas, bg=BG_DARK, padx=20, pady=20)
        sync_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        window_id = canvas.create_window((0, 0), window=sync_frame, anchor="nw")
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window_id, width=event.width))
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_canvas_mousewheel(canvas)

        # รายละเอียดคำอธิบายแท็บ
        desc_lbl = tk.Label(sync_frame, text="ควบคุมหน้าจอแบบแมนนวลพร้อมกัน", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 12, "bold"))
        desc_lbl.pack(anchor="w", pady=(0, 5))
        
        info_lbl = tk.Label(sync_frame, text="คำสั่งด้านล่างนี้จะส่งไปทำงานพร้อมกันบน Emulator ทุกเครื่องที่คุณเลือกไว้ในแถบเช็คลิสต์ด้านซ้ายมือ", bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 10))
        info_lbl.pack(anchor="w", pady=(0, 20))

        # ส่วนของแผงดำเนินการ Grid
        control_grid = tk.Frame(sync_frame, bg=BG_DARK)
        control_grid.pack(fill="x", pady=10)

        # 1. กล่องจำลองคลิกพิกัด
        tap_box = tk.LabelFrame(control_grid, text=" 🎯 จำลองการคลิกพิกัด ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        tap_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        
        tk.Label(tap_box, text="พิกัด X:", bg=BG_DARK, fg=FG_WHITE).grid(row=0, column=0, sticky="w", pady=5)
        self.manual_x = ModernEntry(tap_box, width=10)
        self.manual_x.grid(row=0, column=1, padx=5, pady=5)
        self.manual_x.insert(0, "450")

        tk.Label(tap_box, text="พิกัด Y:", bg=BG_DARK, fg=FG_WHITE).grid(row=1, column=0, sticky="w", pady=5)
        self.manual_y = ModernEntry(tap_box, width=10)
        self.manual_y.grid(row=1, column=1, padx=5, pady=5)
        self.manual_y.insert(0, "320")

        ModernButton(tap_box, text="💥 ส่งคำสั่งคลิกหน้าจอ", command=self.send_manual_click).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        # 2. กล่องจำลองการพิมพ์ข้อความ
        txt_box = tk.LabelFrame(control_grid, text=" ⌨️ จำลองการพิมพ์ข้อความ ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        txt_box.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        tk.Label(txt_box, text="พิมพ์ข้อความภาษาอังกฤษ/ตัวเลข:", bg=BG_DARK, fg=FG_WHITE).pack(anchor="w", pady=5)
        self.manual_txt_entry = ModernEntry(txt_box, width=30)
        self.manual_txt_entry.pack(fill="x", pady=5)
        self.manual_txt_entry.insert(0, "Hello World")
        
        ModernButton(txt_box, text="⌨️ ส่งคำสั่งพิมพ์ข้อความ", command=self.send_manual_text).pack(fill="x", pady=(18, 0))

        # 3. จำลองกดปุ่มระบบมือถือ
        key_box = tk.LabelFrame(control_grid, text=" 🖱️ จำลองการกดปุ่มระบบ ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        key_box.grid(row=0, column=2, sticky="nsew", padx=(10, 0), pady=10)

        ModernButton(key_box, text="⬅️ ปุ่มย้อนกลับ (BACK)", command=lambda: self.send_manual_key(4), bg=BG_INPUT, activebg="#444444").pack(fill="x", pady=3)
        ModernButton(key_box, text="🏠 ปุ่มหน้าแรก (HOME)", command=lambda: self.send_manual_key(3), bg=BG_INPUT, activebg="#444444").pack(fill="x", pady=3)
        ModernButton(key_box, text="📋 ปุ่มเมนู (MENU)", command=lambda: self.send_manual_key(82), bg=BG_INPUT, activebg="#444444").pack(fill="x", pady=3)

        control_grid.columnconfigure(0, weight=1)
        control_grid.columnconfigure(1, weight=1)
        control_grid.columnconfigure(2, weight=1)

        # 4. กล่องรันคำสั่ง ADB แบบแมนนวลเอง
        raw_box = tk.LabelFrame(sync_frame, text=" 💻 รันคำสั่ง ADB Shell เองแบบกำหนดเอง ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        raw_box.pack(fill="x", pady=10)

        tk.Label(raw_box, text="คำสั่งระบบ: adb -s [device_id] shell ... (ไม่ต้องใส่คำว่า adb -s [device_id] shell)", bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic")).pack(anchor="w")
        
        cmd_input_frame = tk.Frame(raw_box, bg=BG_DARK)
        cmd_input_frame.pack(fill="x", pady=5)

        self.custom_cmd_entry = ModernEntry(cmd_input_frame)
        self.custom_cmd_entry.pack(fill="x", side="left", expand=True, padx=(0, 10))
        self.custom_cmd_entry.insert(0, "wm size")

        ModernButton(cmd_input_frame, text="⚡ รันคำสั่งทันที", command=self.send_custom_cmd).pack(side="right")

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

        tk.Label(settings_frame, text="ตั้งค่าโปรแกรมเพิ่มเติม", bg=BG_DARK, fg=FG_WHITE, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 15))

        # ที่อยู่ ADB.exe
        path_box = tk.LabelFrame(settings_frame, text=" 💾 ตั้งค่าเส้นทางไฟล์ที่จำเป็น ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        path_box.pack(fill="x", pady=10)

        tk.Label(path_box, text="ที่อยู่ไฟล์ ADB.exe (Path):", bg=BG_DARK, fg=FG_WHITE).pack(anchor="w")
        
        adb_path_frame = tk.Frame(path_box, bg=BG_DARK)
        adb_path_frame.pack(fill="x", pady=5)
        
        self.adb_path_entry = ModernEntry(adb_path_frame)
        self.adb_path_entry.pack(fill="x", side="left", expand=True, padx=(0, 10))
        self.adb_path_entry.insert(0, self.controller.adb_path)

        ModernButton(adb_path_frame, text="บันทึกและโหลดใหม่", command=self.save_adb_path).pack(side="right")

        # ตั้งค่าพอร์ต ADB (ADB Port Settings)
        port_box = tk.LabelFrame(settings_frame, text=" 🔌 ตั้งค่าพอร์ต ADB (ADB Port Settings) ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        port_box.pack(fill="x", pady=10)

        tk.Label(port_box, text="ระบุหรือนำเข้าข้อมูลพอร์ตของ Emulator สำหรับสแกนและควบคุม (ใช้เมื่อมีจำนวนจอเยอะหรือพอร์ตแปลก):", bg=BG_DARK, fg=FG_WHITE).pack(anchor="w")

        port_btn_frame = tk.Frame(port_box, bg=BG_DARK)
        port_btn_frame.pack(fill="x", pady=5)

        ModernButton(port_btn_frame, text="🔌 นำเข้าพอร์ตจาก JSON (AI)", command=self.open_port_config_dialog, bg=ACCENT_BLUE, activebg=ACCENT_HOVER).pack(side="left", padx=(0, 10))
        
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

        ModernButton(port_btn_frame, text="📋 คัดลอกพร้อมต์ถาม AI", command=copy_ai_prompt, bg=ACCENT_ORANGE, activebg="#d35400").pack(side="left", padx=(0, 10))

        def show_current_ports():
            ports = self.controller.load_ports()
            msg = f"พอร์ตที่โปรแกรมกำลังสแกนอยู่ในปัจจุบัน:\n\n{ports}\n\nจำนวนทั้งหมด: {len(ports)} พอร์ต"
            messagebox.showinfo("พอร์ตที่ใช้สแกน", msg)

        ModernButton(port_btn_frame, text="🔍 แสดงรายชื่อพอร์ตปัจจุบัน", command=show_current_ports, bg=BG_INPUT, activebg="#444444").pack(side="left")

        # ระบบตรวจสอบความเหมาะสมของขนาดจอและ DPI
        diag_box = tk.LabelFrame(settings_frame, text=" 📊 ระบบตรวจสอบขนาดหน้าจอ Emulator ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        diag_box.pack(fill="x", pady=10)

        ModernButton(diag_box, text="ตรวจสอบความละเอียดและค่า DPI ของ Emulator ที่เลือก", command=self.validate_resolutions, bg=ACCENT_GREEN, activebg="#2ecc71").pack(anchor="w")
        
        diag_lbl = tk.Label(
            diag_box, 
            text="หมายเหตุ: พิกัดมาโครทั้งหมดถูกคำนวณบนขนาดหน้าจอเป้าหมาย กว้าง 960 / สูง 540 และค่า DPI 160 หากตั้งค่า Emulator ไม่ตรง คำสั่งคลิกอาจคลาดเคลื่อนไม่ตรงปุ่มจริง ปุ่มนี้จะช่วยสแกนขนาดหน้าจอปัจจุบันและรายงานให้ทราบความเข้ากันได้", 
            bg=BG_DARK, 
            fg=FG_MUTED, 
            font=("Segoe UI", 9, "italic"),
            justify="left",
            wraplength=700
        )
        diag_lbl.pack(anchor="w", pady=(10, 0))

        # ตัวช่วยวิเคราะห์พิกัดมาโคร (Pointer Location Helper)
        helper_box = tk.LabelFrame(settings_frame, text=" 🛠️ ตัวช่วยวิเคราะห์และหาพิกัดหน้าจอ (Pointer Location) ", bg=BG_DARK, fg=ACCENT_BLUE, font=("Segoe UI", 10, "bold"), bd=1, padx=15, pady=15)
        helper_box.pack(fill="x", pady=10)

        btn_row = tk.Frame(helper_box, bg=BG_DARK)
        btn_row.pack(anchor="w", pady=5)

        ModernButton(btn_row, text="🎯 เปิดแสดงเส้นพิกัดการจิ้ม", command=lambda: self.toggle_pointer_location(True), bg=ACCENT_BLUE, activebg=ACCENT_HOVER).pack(side="left", padx=(0, 10))
        ModernButton(btn_row, text="❌ ปิดแสดงเส้นพิกัดการจิ้ม", command=lambda: self.toggle_pointer_location(False), bg=BG_INPUT, activebg="#444444").pack(side="left")

        helper_lbl = tk.Label(
            helper_box, 
            text="คำแนะนำ: เมื่อเปิดใช้งานแล้ว ให้ลองใช้เมาส์คลิกบนหน้าจอ Emulator จะมีแถบข้อความแสดงพิกัด X/Y จริงที่ด้านบนสุดของจอ Emulator ทันที! ช่วยให้หาพิกัดกรอกรหัสและปุ่มกดเกมได้แม่นยำ 100%", 
            bg=BG_DARK, 
            fg=FG_MUTED, 
            font=("Segoe UI", 9, "italic"),
            justify="left",
            wraplength=700
        )
        helper_lbl.pack(anchor="w", pady=(5, 0))

    def build_log_panel(self):
        log_frame = tk.Frame(self, bg=BG_PANEL, height=150)
        log_frame.pack(fill="both", side="bottom", padx=10, pady=(0, 10))
        log_frame.pack_propagate(False)

        # แถบหัวข้อคอนโซล Log
        log_header = tk.Frame(log_frame, bg=BG_PANEL)
        log_header.pack(fill="x", side="top", padx=10, pady=2)
        
        tk.Label(log_header, text="คอนโซลบันทึกการทำงานของระบบ (Log Console)", bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 9, "bold")).pack(side="left")
        ModernButton(log_header, text="ล้างบันทึก", command=self.clear_logs, bg=BG_INPUT, activebg="#444444", font=("Segoe UI", 8)).pack(side="right")

        # ตัวแสดงผลข้อความล็อก
        self.log_txt = tk.Text(
            log_frame, 
            bg=BG_DARK, 
            fg=FG_WHITE, 
            font=("Consolas", 9), 
            relief="flat", 
            bd=0, 
            state="disabled",
            wrap="word"
        )
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_txt.yview)
        
        self.log_txt.configure(yscrollcommand=scroll.set)
        self.log_txt.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))
        scroll.pack(side="right", fill="y", padx=(0, 10), pady=(0, 10))

        # กำหนดแท็กเพื่อแสดงสีของตัวอักษร
        self.log_txt.tag_configure("info", foreground=FG_WHITE)
        self.log_txt.tag_configure("success", foreground=ACCENT_GREEN)
        self.log_txt.tag_configure("error", foreground=ACCENT_RED)
        self.log_txt.tag_configure("warning", foreground=ACCENT_ORANGE)

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

    def save_adb_path(self):
        new_path = self.adb_path_entry.get().strip()
        if not new_path:
            messagebox.showerror("ข้อผิดพลาด", "พาร์ท ADB ว่างเปล่าไม่ได้")
            return
        self.controller.adb_path = new_path
        self.write_log(f"บันทึกเส้นทาง ADB ใหม่เรียบร้อยแล้ว: {new_path}", "warning")
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

    def refresh_accounts_ui(self):
        """วาดการ์ดลิสต์รายชื่อไอดีแบบจัดกลุ่มบนแท็บจัดการบัญชีใหม่"""
        for widget in self.acc_scroll_frame.winfo_children():
            widget.destroy()
            
        self.account_checkboxes.clear()
        self.group_checkboxes.clear()
        
        if not self.accounts:
            lbl = tk.Label(self.acc_scroll_frame, text="ไม่มีบัญชีในคิวระบบ\nกรุณาเพิ่มบัญชีเกมด้านขวามือ", bg=BG_DARK, fg=FG_MUTED, font=("Segoe UI", 9, "italic"), justify="center")
            lbl.pack(pady=30, fill="x")
            return

        # 1. จัดกลุ่มบัญชี
        grouped_accounts = {}
        for acc in self.accounts:
            grp = acc.get("group", "ทั่วไป").strip()
            if not grp:
                grp = "ทั่วไป"
            if grp not in grouped_accounts:
                grouped_accounts[grp] = []
            grouped_accounts[grp].append(acc)

        # 2. วาดแต่ละกลุ่ม
        for grp, acc_list in grouped_accounts.items():
            # สร้างกล่องจัดกลุ่ม
            group_box = tk.Frame(self.acc_scroll_frame, bg=BG_DARK, bd=0)
            group_box.pack(fill="x", pady=(10, 5), padx=2)

            # หัวข้อกลุ่ม
            group_header = tk.Frame(group_box, bg=BG_PANEL, bd=1, relief="solid", highlightthickness=0)
            group_header.configure(highlightbackground="#444444")
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
                pwd = acc.get("password")
                checked = acc.get("checked", True)

                frame = tk.Frame(group_box, bg=BG_CARD, bd=1, relief="solid", highlightthickness=0)
                frame.configure(highlightbackground="#333333")
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

                chk = tk.Checkbutton(
                    frame,
                    text=email,
                    variable=var,
                    command=on_single_click,
                    bg=BG_CARD,
                    fg=FG_WHITE,
                    activebackground=BG_CARD,
                    activeforeground=FG_WHITE,
                    selectcolor=BG_DARK,
                    relief="flat",
                    font=("Segoe UI", 9)
                )
                chk.pack(side="left", padx=5, pady=5)

                # พรางรหัสผ่านเพื่อความสวยงาม
                masked_pwd = "*" * min(8, len(pwd))
                lbl_pwd = tk.Label(frame, text=f"({masked_pwd})", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 8))
                lbl_pwd.pack(side="left", padx=5)

                # ปุ่มลบบัญชี
                del_btn = tk.Button(
                    frame,
                    text="X",
                    command=lambda e=email: self.delete_account(e),
                    bg="#E74C3C",
                    fg=FG_WHITE,
                    activebackground="#c0392b",
                    activeforeground=FG_WHITE,
                    relief="flat",
                    bd=0,
                    font=("Segoe UI", 8, "bold"),
                    width=2
                )
                del_btn.pack(side="right", padx=5, pady=5)

    def add_account(self):
        email = self.new_acc_email.get().strip()
        pwd = self.new_acc_pass.get().strip()
        group = self.new_acc_group.get().strip() or "ทั่วไป"
        
        if not email or not pwd:
            messagebox.showwarning("คำเตือน", "กรุณากรอกอีเมลและรหัสผ่านให้ครบถ้วน!")
            return
            
        if any(acc.get("email") == email for acc in self.accounts):
            messagebox.showwarning("คำเตือน", "บัญชีอีเมลนี้มีอยู่แล้วในคิว!")
            return
            
        self.accounts.append({"email": email, "password": pwd, "checked": True, "group": group})
        self.save_accounts()
        self.refresh_accounts_ui()
        self.write_log(f"เพิ่มบัญชี {email} ลงในกลุ่ม {group} สำเร็จ", "success")
        
        self.new_acc_email.delete(0, tk.END)
        self.new_acc_pass.delete(0, tk.END)
        self.new_acc_group.delete(0, tk.END)
        self.new_acc_group.insert(0, "ทั่วไป")

    def delete_account(self, email):
        confirm = messagebox.askyesno("ลบบัญชี", f"คุณต้องการลบบัญชี {email} หรือไม่?")
        if confirm:
            self.accounts = [acc for acc in self.accounts if acc.get("email") != email]
            self.save_accounts()
            self.refresh_accounts_ui()
            self.write_log(f"ลบบัญชี {email} เรียบร้อยแล้ว", "warning")

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
            except Exception as e:
                self.write_log(f"โหลดโปรไฟล์ผิดพลาด: {e}", "error")

    def refresh_listbox(self):
        """อัปเดตลิสต์ในกล่องสคริปต์ขั้นตอน (Listbox) ใหม่"""
        self.step_listbox.delete(0, tk.END)
        for idx, step in enumerate(self.macro_steps):
            t = step.get("type", "tap").upper()
            desc = step.get("desc", "")
            
            # แปลงประเภทคำสั่งเป็นภาษาไทยเพื่อให้อ่านง่ายในลิสต์บล็อก
            t_thai = "คลิก"
            if t == "TAP":
                t_thai = "คลิก"
                details = f"({step.get('x')}, {step.get('y')})"
            elif t == "SWIPE":
                t_thai = "ลากจอ"
                details = f"({step.get('x')},{step.get('y')} -> {step.get('x2')},{step.get('y2')})"
            elif t == "TEXT":
                t_thai = "พิมพ์"
                details = f"'{step.get('text')}'"
            elif t == "KEYEVENT":
                t_thai = "ปุ่มกด"
                details = f"รหัส {step.get('code')}"
            elif t == "SLEEP":
                t_thai = "รอเวลา"
                details = f"{step.get('seconds')} วินาที"
            elif t == "START_APP":
                t_thai = "เปิดแอป"
                details = f"'{step.get('text')}'"
            elif t == "STOP_APP":
                t_thai = "ปิดแอป"
                details = f"'{step.get('text')}'"
            elif t == "CLEAR_APP":
                t_thai = "ล้างข้อมูล"
                details = f"'{step.get('text')}'"
            elif t == "DETECT_IMAGE":
                t_thai = "รูปภาพ"
                details = f"หา '{step.get('text')}'"
            else:
                details = ""
                
            # ดึงค่าดีเลย์ถ้ามี
            delay_info = ""
            if t != "SLEEP":
                delay_val = step.get("delay")
                if delay_val is not None:
                    delay_info = f" (หน่วง {delay_val} วิ)"
                else:
                    if t == "TAP" or t == "SWIPE":
                        delay_info = " (หน่วง 0.5 วิ)"
                    elif t == "TEXT":
                        delay_info = " (หน่วง 0.5 วิ)"
                    elif t == "KEYEVENT":
                        delay_info = " (หน่วง 0.3 วิ)"
                    else:
                        delay_info = " (หน่วง 1.0 วิ)"
                        
            self.step_listbox.insert(tk.END, f"{idx+1:02d}. [{t_thai}] {details}{delay_info} - {desc}")

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
        elif t == "clear_app":
            self.form_type.set("ล้างข้อมูลแอป (Clear App Data)")
        elif t == "detect_image":
            self.form_type.set("ตรวจจับรูปภาพ (Image Match)")
            
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
            self.form_sleep.insert(0, step.get("delay", "0.5"))
        elif t == "swipe":
            self.form_x.insert(0, step.get("x", ""))
            self.form_y.insert(0, step.get("y", ""))
            self.form_x2.insert(0, step.get("x2", ""))
            self.form_y2.insert(0, step.get("y2", ""))
            self.form_sleep.insert(0, step.get("delay", "0.5"))
        elif t in ["text", "start_app", "stop_app", "clear_app", "detect_image"]:
            self.form_text.insert(0, step.get("text", ""))
            self.form_sleep.insert(0, step.get("delay", "0.5" if t == "text" else "1.0"))
        elif t == "keyevent":
            self.form_code.insert(0, step.get("code", ""))
            self.form_sleep.insert(0, step.get("delay", "0.3"))
        elif t == "sleep":
            self.form_sleep.insert(0, step.get("seconds", "1.0"))

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
        elif "Image Match" in t:
            self.form_sleep_label.configure(text="หน่วงหลังคลิก (วินาที):")
            self.form_x_label.configure(fg=FG_MUTED)
            self.form_x.configure(state="disabled")
            self.form_y.configure(state="disabled")
            self.form_x2.configure(state="disabled")
            self.form_y2.configure(state="disabled")
            self.form_x2_label.configure(fg=FG_MUTED)
            self.form_code.configure(state="disabled")

    def clear_form(self):
        self.form_x.delete(0, tk.END)
        self.form_y.delete(0, tk.END)
        self.form_x2.delete(0, tk.END)
        self.form_y2.delete(0, tk.END)
        self.form_text.delete(0, tk.END)
        self.form_code.delete(0, tk.END)
        self.form_sleep.delete(0, tk.END)
        self.form_desc.delete(0, tk.END)

    def add_step(self):
        t_label = self.form_type.get()
        t = "tap"
        if "Text" in t_label:
            t = "text"
        elif "Keyevent" in t_label:
            t = "keyevent"
        elif "Swipe" in t_label:
            t = "swipe"
        elif "Sleep" in t_label:
            t = "sleep"
        elif "Start App" in t_label:
            t = "start_app"
        elif "Stop App" in t_label:
            t = "stop_app"
        elif "Clear App Data" in t_label:
            t = "clear_app"
        elif "Image Match" in t_label:
            t = "detect_image"
            
        desc = self.form_desc.get().strip()
        step = {"type": t, "desc": desc}
        
        try:
            if t == "tap":
                step["x"] = self.form_x.get().strip()
                step["y"] = self.form_y.get().strip()
                if not step["x"] or not step["y"]: raise ValueError("พิกัดห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "0.5")
            elif t == "swipe":
                step["x"] = self.form_x.get().strip()
                step["y"] = self.form_y.get().strip()
                step["x2"] = self.form_x2.get().strip()
                step["y2"] = self.form_y2.get().strip()
                if not step["x"] or not step["y"] or not step["x2"] or not step["y2"]:
                    raise ValueError("พิกัดจุดเริ่มหรือจุดปลายห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "0.5")
            elif t in ["text", "start_app", "stop_app", "clear_app", "detect_image"]:
                step["text"] = self.form_text.get()
                if t in ["start_app", "stop_app", "clear_app", "detect_image"] and not step["text"]:
                    raise ValueError("ชื่อไฟล์รูปภาพต้นแบบห้ามว่างเปล่า" if t == "detect_image" else "ชื่อสัญลักษณ์แพ็คเกจ/แอปห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or ("0.5" if t == "text" else "1.0"))
            elif t == "keyevent":
                step["code"] = self.form_code.get().strip()
                if not step["code"]: raise ValueError("รหัสปุ่มกดคีย์เวนท์ห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "0.3")
            elif t == "sleep":
                step["seconds"] = float(self.form_sleep.get().strip())
        except ValueError as e:
            messagebox.showerror("ข้อมูลไม่ถูกต้อง", f"การตรวจสอบความถูกต้องการป้อนข้อมูลล้มเหลว: {e}")
            return
            
        self.macro_steps.append(step)
        self.refresh_listbox()
        self.write_log(f"เพิ่มขั้นตอนสำเร็จ: {desc}", "info")

    def update_step(self):
        selection = self.step_listbox.curselection()
        if not selection:
            messagebox.showwarning("คำเตือน", "กรุณาคลิกเลือกขั้นตอนในรายการฝั่งซ้ายที่ต้องการอัปเดตก่อน!")
            return
        idx = selection[0]
        
        t_label = self.form_type.get()
        t = "tap"
        if "Text" in t_label:
            t = "text"
        elif "Keyevent" in t_label:
            t = "keyevent"
        elif "Swipe" in t_label:
            t = "swipe"
        elif "Sleep" in t_label:
            t = "sleep"
        elif "Start App" in t_label:
            t = "start_app"
        elif "Stop App" in t_label:
            t = "stop_app"
        elif "Clear App Data" in t_label:
            t = "clear_app"
        elif "Image Match" in t_label:
            t = "detect_image"
            
        desc = self.form_desc.get().strip()
        step = {"type": t, "desc": desc}
        
        try:
            if t == "tap":
                step["x"] = self.form_x.get().strip()
                step["y"] = self.form_y.get().strip()
                if not step["x"] or not step["y"]: raise ValueError("พิกัดห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "0.5")
            elif t == "swipe":
                step["x"] = self.form_x.get().strip()
                step["y"] = self.form_y.get().strip()
                step["x2"] = self.form_x2.get().strip()
                step["y2"] = self.form_y2.get().strip()
                if not step["x"] or not step["y"] or not step["x2"] or not step["y2"]:
                    raise ValueError("พิกัดจุดเริ่มหรือจุดปลายห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "0.5")
            elif t in ["text", "start_app", "stop_app", "clear_app", "detect_image"]:
                step["text"] = self.form_text.get()
                if t in ["start_app", "stop_app", "clear_app", "detect_image"] and not step["text"]:
                    raise ValueError("ชื่อไฟล์รูปภาพต้นแบบห้ามว่างเปล่า" if t == "detect_image" else "ชื่อสัญลักษณ์แพ็คเกจ/แอปห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or ("0.5" if t == "text" else "1.0"))
            elif t == "keyevent":
                step["code"] = self.form_code.get().strip()
                if not step["code"]: raise ValueError("รหัสปุ่มกดคีย์เวนท์ห้ามว่างเปล่า")
                step["delay"] = float(self.form_sleep.get().strip() or "0.3")
            elif t == "sleep":
                step["seconds"] = float(self.form_sleep.get().strip())
        except ValueError as e:
            messagebox.showerror("ข้อมูลไม่ถูกต้อง", f"การตรวจสอบความถูกต้องการป้อนข้อมูลล้มเหลว: {e}")
            return
            
        self.macro_steps[idx] = step
        self.refresh_listbox()
        self.step_listbox.selection_set(idx)
        self.write_log(f"อัปเดตขั้นตอนลำดับที่ {idx+1} สำเร็จแล้ว", "info")

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
        
        if checked_accounts:
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

        # ล็อคปุ่มสับเปลี่ยนสถานะ
        self.macro_running = True
        self.run_macro_btn.configure(state="disabled", bg=BG_INPUT)
        self.stop_macro_btn.configure(state="normal")
        
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
            was_paused = self.is_paused_waiting_for_next_set
            self.is_paused_waiting_for_next_set = False
            self.remaining_accounts = []
            self.write_log("⚠️ ส่งสัญญาณยกเลิก! กำลังหยุดการทำงานมาโครโปรดรอสักครู่...", "warning")
            if was_paused:
                self.run_macro_btn.configure(state="normal", bg=ACCENT_GREEN, text="🚀 รันคำสั่งบอทมาโครที่เลือก")
                self.stop_macro_btn.configure(state="disabled")
                self.write_log("⏹️ หยุดการทำงานของบอทและเคลียร์คิวเรียบร้อยแล้ว", "success")

    def run_macro_task(self, devices, checked_accounts):
        import queue
        from concurrent.futures import ThreadPoolExecutor

        try:
            # ตรวจสอบว่าต้องไฮไลท์ขั้นตอนที่ลิสต์บ็อกซ์หรือไม่ (ทำเฉพาะตอนรันจอเดียวเพื่อไม่ให้กะพริบแย่งกัน)
            highlight = (len(devices) == 1)

            if not checked_accounts:
                self.write_log(f"🏁 เริ่มต้นการรันมาโคร 1 รอบพร้อมกันบน Emulator ทั้งหมด {len(devices)} จอ (ไม่มีบัญชีไอดี)...", "warning")
                
                # รันมาโครพร้อมกันทีละจอใน ThreadPool
                def worker(dev):
                    self.execute_device_macro(dev, None, highlight)

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
                        self.write_log(f"🔄 [{dev}] หยิบบัญชี: {email} มารันมาโคร...", "warning")
                        self.execute_device_macro(dev, acc, highlight)

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

                    # ฟังก์ชันการทำงานของแต่ละจอ
                    def device_worker(dev):
                        while self.macro_running:
                            try:
                                acc = account_queue.get_nowait()
                            except queue.Empty:
                                break
                            
                            email = acc.get("email")
                            self.write_log(f"🔄 [{dev}] หยิบบัญชี: {email} มารันมาโคร...", "warning")
                            self.execute_device_macro(dev, acc, highlight)
                            account_queue.task_done()

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
                self.after(0, lambda: self.run_macro_btn.configure(state="normal", bg=ACCENT_GREEN, text="🚀 รันคำสั่งบอทมาโครที่เลือก"))
                self.after(0, lambda: self.stop_macro_btn.configure(state="disabled"))

    def run_macro_task_resume(self):
        from concurrent.futures import ThreadPoolExecutor
        try:
            highlight = (len(self.active_devices_for_run) == 1)
            devices = self.active_devices_for_run
            batch_size = len(devices)
            current_batch = self.remaining_accounts[:batch_size]
            self.remaining_accounts = self.remaining_accounts[batch_size:]
            
            self.write_log(f"🏁 รันต่อ: เริ่มรันชุดบัญชีคู่ขนานจำนวน {len(current_batch)} ไอดี ลงบน Emulator...", "warning")
            
            # จับคู่ อุปกรณ์ กับ บัญชี
            paired = list(zip(devices, current_batch))
            
            def batch_worker(pair):
                dev, acc = pair
                email = acc.get("email")
                self.write_log(f"🔄 [{dev}] หยิบบัญชี: {email} มารันมาโคร...", "warning")
                self.execute_device_macro(dev, acc, highlight)

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
                self.after(0, lambda: self.run_macro_btn.configure(state="normal", bg=ACCENT_GREEN, text="🚀 รันคำสั่งบอทมาโครที่เลือก"))
                self.after(0, lambda: self.stop_macro_btn.configure(state="disabled"))

    def execute_device_macro(self, device, account, highlight=True):
        """รันสคริปต์มาโครบน Emulator จอเดียวกับบัญชีที่กำหนด"""
        for idx, step in enumerate(self.macro_steps):
            if not self.macro_running:
                return
            
            t = step.get("type", "tap")
            desc = step.get("desc", f"ขั้นตอนที่ {idx+1}")
            email_log = f" ({account['email']})" if account else ""
            self.write_log(f"   👉 [{device}]{email_log} ขั้นที่ {idx+1}/{len(self.macro_steps)}: {desc}...", "info")
            
            # ไฮไลท์การทำงานบนลิสต์บ็อกซ์ GUI เฉพาะกรณีที่ระบุไฮไลท์
            if highlight:
                self.after(0, lambda i=idx: self.step_listbox.selection_clear(0, tk.END))
                self.after(0, lambda i=idx: self.step_listbox.selection_set(i))
                self.after(0, lambda i=idx: self.step_listbox.see(i))
            
            # ดึงค่าหน่วงเวลาเฉพาะของขั้นตอนนี้ (ถ้าไม่มีให้ดึงค่าดีฟอลต์มาใช้)
            step_delay = step.get("delay")
            if step_delay is None:
                if t == "tap" or t == "swipe":
                    step_delay = 0.5
                elif t == "text":
                    step_delay = 0.5
                elif t == "keyevent":
                    step_delay = 0.3
                elif t in ["start_app", "stop_app", "clear_app", "detect_image"]:
                    step_delay = 1.0
                else:
                    step_delay = 0.0
            else:
                step_delay = float(step_delay)

            # ประมวลผลคำสั่งมาโคร
            if t == "tap":
                self.controller.tap(device, step["x"], step["y"])
                time.sleep(step_delay)  # หน่วงเวลาหลังคลิกเพื่อให้ระบบ Android ทำงานทัน
            elif t == "swipe":
                self.controller.swipe(device, step["x"], step["y"], step["x2"], step["y2"])
                time.sleep(step_delay)  # หน่วงเวลาหลังลากจอ
            elif t == "text":
                text_to_send = step["text"]
                if account:
                    # แทนที่ตัวแปร {EMAIL} และ {PASSWORD} ด้วยไอดีรอบนี้
                    text_to_send = text_to_send.replace("{EMAIL}", account["email"])
                    text_to_send = text_to_send.replace("{PASSWORD}", account["password"])
                self.controller.input_text(device, text_to_send)
                time.sleep(step_delay)  # หน่วงเวลาหลังพิมพ์ข้อความ
            elif t == "keyevent":
                self.controller.keyevent(device, step["code"])
                time.sleep(step_delay)  # หน่วงเวลาหลังคีย์อีเวนท์
            elif t == "start_app":
                self.controller.start_app(device, step["text"])
                if step_delay > 0:
                    time.sleep(step_delay)
            elif t == "stop_app":
                self.controller.stop_app(device, step["text"])
                if step_delay > 0:
                    time.sleep(step_delay)
            elif t == "clear_app":
                self.controller.clear_app(device, step["text"])
                if step_delay > 0:
                    time.sleep(step_delay)
            elif t == "detect_image":
                template_file = step["text"]
                template_path = os.path.join(self.templates_dir, template_file)
                if not os.path.exists(template_path):
                    self.write_log(f"   ⚠️ [{device}] ไม่พบไฟล์เทมเพลต: {template_file}", "warning")
                else:
                    safe_device = device.replace(":", "_").replace(".", "_")
                    temp_screenshot = os.path.join(self.templates_dir, f"temp_{safe_device}.png")
                    
                    # ถ่ายภาพหน้าจอของจอนี้
                    success, err = self.controller.take_screenshot(device, temp_screenshot)
                    if not success:
                        self.write_log(f"   ❌ [{device}] ถ่ายภาพหน้าจอล้มเหลว: {err}", "error")
                    else:
                        # ค้นหาตำแหน่งภาพ
                        found, match_x, match_y, msg = self.controller.find_image_on_screen(temp_screenshot, template_path, threshold=0.8)
                        
                        # ลบภาพแคปหน้าจอชั่วคราวทิ้งทันที
                        if os.path.exists(temp_screenshot):
                            try:
                                os.remove(temp_screenshot)
                            except Exception:
                                pass
                        
                        if found:
                            self.write_log(f"   🎯 [{device}] พบรูป '{template_file}' พิกัด ({match_x}, {match_y}) -> กำลังคลิก", "success")
                            self.controller.tap(device, match_x, match_y)
                            if step_delay > 0:
                                time.sleep(step_delay)
                        else:
                            self.write_log(f"   🔍 [{device}] ไม่พบรูป '{template_file}' บนจอ -> ข้ามขั้นตอนนี้", "info")
            elif t == "sleep":
                sleep_time = float(step["seconds"])
                slices = int(sleep_time / 0.1)
                for _ in range(slices):
                    if not self.macro_running:
                        return
                    time.sleep(0.1)
                time.sleep(sleep_time % 0.1)
