"""Tk root ตัวเดียวใช้ร่วมกันทั้งชุดเทส

บน Windows การสร้าง tk.Tk() แล้ว destroy หลายรอบใน process เดียวทำให้ Tcl หมดทรัพยากร
แล้วสร้าง root ใหม่ไม่ได้ (TclError ตอน setup fixture) — เดิมแต่ละไฟล์เทสสร้าง MuMuGUI
ของตัวเอง ไฟล์ที่รันทีหลังจึงล้มแบบสุ่มประมาณ 1 ใน 4 รอบเมื่อรันทั้งชุดพร้อมกัน

fixture นี้สร้าง MuMuGUI ครั้งเดียวต่อ session แล้วให้ทุกไฟล์ยืมไปใช้ — ไฟล์ที่ใช้ต้อง
รีเซ็ตสถานะที่ตัวเองสนใจ (controller/macro_steps/ฯลฯ) เองในแต่ละเทสตามเดิม
"""
import os
import sys
import tempfile
import unittest.mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolate_error_reports(tmp_path, monkeypatch):
    """ทุกเทส: ให้ MacroRunner เขียนรายงานจุดที่ติด/ไฟล์ log ลง tmp_path แทน error_reports จริง
    (เดิมเทสเขียนบรรทัดปลอม device ':7555' / ภาพ 6 ไบต์ ปนลงรายงานจริงของผู้ใช้)"""
    import macro_runner
    d = str(tmp_path / "error_reports")
    monkeypatch.setattr(macro_runner, "error_reports_dir", lambda: d)
    yield d
    macro_runner.close_file_log()   # ปิดไฟล์ log ก่อน — Windows ลบโฟลเดอร์ที่มีไฟล์เปิดค้างไม่ได้


@pytest.fixture(scope="session")
def gui_app():
    import gui as G
    # ตัด I/O ตอนบูตทิ้ง: ห้ามแตะ accounts.json จริง และไม่ต้องสแกนหาจอ
    with unittest.mock.patch.object(G.MuMuGUI, "load_accounts", lambda self: None), \
         unittest.mock.patch.object(G.MuMuGUI, "scan_devices", lambda self: None):
        app = G.MuMuGUI()
    app.error_reports_dir = tempfile.mkdtemp()   # รายงานจุดที่ติดต้องไม่ปนของจริง
    yield app
    app.destroy()
