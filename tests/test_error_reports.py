"""เทสระบบรายงานจุดที่ติด (error_reports/) ที่ปรับให้ดูแล้วรู้ทันทีว่าพังตรงไหน

1) อยู่ในบล็อกกันพังแล้วขั้นย่อยหา anchor ไม่เจอ → ต้องบันทึกขั้นย่อยนั้นด้วย (path เต็ม เช่น 0.set.0)
   และบรรทัด block_failed ต้องอ้าง inner_path/inner_reason
2) ฟิลด์เสริม: step_no, set_name, attempt, x, y, template, threshold, best_score, timeout, on_fail,
   resolution, app_version, run_id (ใส่เฉพาะที่มีค่า)
3) log ข้อความลงไฟล์ error_reports/logs/run.log (RotatingFileHandler) + แนบ tail 30 บรรทัด
4) หมุน report.jsonl รายเดือน / ลบโฟลเดอร์ภาพ YYYYMMDD ที่เก่ากว่า 30 วัน (เฉพาะชื่อที่ตรงรูปแบบ)
5) เทสต้องไม่เขียนลง error_reports จริง (conftest ชี้ไป tmp_path)
"""
import base64
import datetime
import json
import os
import sys
from logging.handlers import RotatingFileHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import macro_runner as M

B64 = base64.b64encode(b"TMPL").decode()


class Ctl:
    """ภาพไม่เคยเจอ (คืนค่าความเหมือน 0.42) — บันทึกการกด"""

    def __init__(self):
        self.calls = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def match_template_bytes(self, data, tmpl, thr=0.8):
        return (False, 0, 0, "No match found (best confidence: 0.42)")

    def find_image_in_bytes(self, data, path, threshold=0.8):
        return (False, 0, 0, "No match found (best confidence: 0.42)")

    def get_resolution(self, d):
        return "1280x720"

    def tap(self, d, x, y):
        self.calls.append(("tap", int(float(x)), int(float(y))))
        return True, ""

    def keyevent(self, d, code):
        return True, ""


def _records(d):
    p = os.path.join(d, "report.jsonl")
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


SETS = {
    "work": [{"type": "tap", "x": "10", "y": "20"},
             {"type": "tap", "x": "622", "y": "439", "anchor_img": B64, "anchor_timeout": 0.001,
              "anchor_threshold": 0.85, "desc": "ปุ่มยืนยัน"}],
    "home": [{"type": "keyevent", "code": 4}],
}


def _block_runner(retries=1):
    steps = [{"type": "run_set", "set": "work", "block_on_fail": "home_retry",
              "block_home": "home", "block_retries": retries, "desc": "ทำงานหลัก"}]
    r = M.MacroRunner(Ctl(), steps, log_cb=lambda t, k="info": None, anchor_poll=0.01,
                      script_sets=SETS)
    r.profile_name = "รับของใหม่"
    return r


# ---------- 1) ขั้นย่อยในบล็อก ----------

def test_failed_sub_step_in_block_is_reported_with_full_path(_isolate_error_reports):
    r = _block_runner(retries=1)
    assert r.execute_one(":7555", {"email": "a@b.c"}) == "device_error"
    recs = _records(_isolate_error_reports)
    inner = [x for x in recs if x["reason"] == "anchor_missing_in_block"]
    assert len(inner) == 2                              # 2 รอบ (ครั้งแรก + ลองใหม่ 1)
    assert inner[0]["step_path"] == "0.set.1"
    assert inner[0]["step_no"] == "1.2"                 # เลขแบบ UI เริ่มที่ 1
    assert inner[0]["set_name"] == "work"
    assert [x["attempt"] for x in inner] == ["1/2", "2/2"]


def test_block_failed_line_points_at_inner_step(_isolate_error_reports):
    r = _block_runner(retries=0)
    r.execute_one(":7555", None)
    recs = _records(_isolate_error_reports)
    last = recs[-1]
    assert last["reason"] == "block_failed:work"
    assert last["step_path"] == "0" and last["step_no"] == "1"
    assert last["inner_path"] == "0.set.1"
    assert last["inner_reason"] == "anchor_missing_in_block"
    assert "best_score" not in last                     # บรรทัดบล็อกไม่ใช่ขั้นเทียบภาพ


# ---------- 2) ฟิลด์เสริม ----------

def test_inner_record_has_coordinates_image_and_score(_isolate_error_reports):
    r = _block_runner(retries=0)
    r.execute_one(":7555", None)
    rec = [x for x in _records(_isolate_error_reports) if x["reason"] == "anchor_missing_in_block"][0]
    assert rec["x"] == 622 and rec["y"] == 439
    assert rec["template"].startswith("anchor_img:") and len(rec["template"]) == len("anchor_img:") + 8
    assert rec["threshold"] == 0.85
    assert rec["timeout"] == 0.001
    assert rec["best_score"] == 0.42
    assert rec["resolution"] == "1280x720"
    assert rec["app_version"]
    assert rec["run_id"] == r.run_id
    assert rec["profile"] == "รับของใหม่"


def test_tap_image_failure_records_file_template_and_on_fail(_isolate_error_reports, tmp_path, monkeypatch):
    (tmp_path / "ok.png").write_bytes(b"png")
    monkeypatch.setattr(M, "templates_dir", lambda: str(tmp_path))
    step = {"type": "tap_image", "text": "ok.png", "timeout": 0, "threshold": 0.9,
            "on_fail": "fail", "delay": 0}
    r = M.MacroRunner(Ctl(), [step], log_cb=lambda t, k="info": None)
    r._run_steps(":7555", None, r.steps, lambda **k: None)
    rec = _records(_isolate_error_reports)[-1]
    assert rec["step_type"] == "tap_image"
    assert rec["template"] == "ok.png"
    assert rec["on_fail"] == "fail" and rec["threshold"] == 0.9 and rec["timeout"] == 0
    assert rec["best_score"] == 0.42
    assert "set_name" not in rec and "attempt" not in rec and "x" not in rec   # ไม่เกี่ยว = ไม่ใส่


# ---------- 3) ไฟล์ log + tail ----------

def test_text_log_goes_to_rotating_file_and_tail_is_attached(_isolate_error_reports):
    r = _block_runner(retries=0)
    r.execute_one(":7555", None)
    log_path = os.path.join(_isolate_error_reports, "logs", "run.log")
    hs = [h for h in M._file_logger.handlers if isinstance(h, RotatingFileHandler)]
    assert hs and hs[0].maxBytes == 5 * 1024 * 1024 and hs[0].backupCount == 5
    for h in hs:
        h.flush()
    with open(log_path, encoding="utf-8") as f:
        assert "[:7555]" in f.read()
    rec = _records(_isolate_error_reports)[-1]
    assert 0 < len(rec["tail"]) <= 30
    assert all("[:7555]" in l for l in rec["tail"])


def test_tail_only_keeps_lines_of_that_device():
    r = M.MacroRunner(Ctl(), [], log_cb=lambda t, k="info": None)
    for i in range(40):
        r.log(f"[A] a{i}")
        r.log(f"[B] b{i}")
    t = r._tail_for("A")
    assert len(t) == 30 and all("[A]" in l for l in t) and t[-1].endswith("a39")


def test_user_log_callback_still_receives_everything():
    got = []
    r = M.MacroRunner(Ctl(), [], log_cb=lambda t, k="info": got.append((k, t)))
    r.log("[X] hello", "warn")
    assert got == [("warn", "[X] hello")]


def test_error_reports_dir_follows_base_dir(monkeypatch, tmp_path):
    monkeypatch.undo()   # ใช้ของจริง (ไม่ผ่าน conftest) เพื่อเช็คว่าอิง base_dir()
    monkeypatch.setattr(M, "base_dir", lambda: str(tmp_path))
    assert M.error_reports_dir() == os.path.join(str(tmp_path), "error_reports")


# ---------- 4) หมุน report.jsonl / ลบภาพเก่า ----------

def _set_mtime(p, dt):
    ts = dt.timestamp()
    os.utime(p, (ts, ts))


def test_report_rotates_when_month_changes(tmp_path):
    p = tmp_path / "report.jsonl"
    p.write_text('{"a":1}\n', encoding="utf-8")
    _set_mtime(p, datetime.datetime(2026, 10, 31, 23, 0))
    dst = M.rotate_report_monthly(str(p), now=datetime.datetime(2026, 11, 1, 0, 5))
    assert os.path.basename(dst) == "report_202610.jsonl"
    assert not p.exists() and (tmp_path / "report_202610.jsonl").read_text(encoding="utf-8") == '{"a":1}\n'


def test_report_does_not_rotate_within_same_month(tmp_path):
    p = tmp_path / "report.jsonl"
    p.write_text("x\n", encoding="utf-8")
    _set_mtime(p, datetime.datetime(2026, 10, 2))
    assert M.rotate_report_monthly(str(p), now=datetime.datetime(2026, 10, 29)) is None
    assert p.exists()


def test_report_rotation_never_overwrites_existing_archive(tmp_path):
    (tmp_path / "report_202610.jsonl").write_text("old\n", encoding="utf-8")
    p = tmp_path / "report.jsonl"
    p.write_text("new\n", encoding="utf-8")
    _set_mtime(p, datetime.datetime(2026, 10, 30))
    dst = M.rotate_report_monthly(str(p), now=datetime.datetime(2026, 11, 2))
    assert os.path.basename(dst) == "report_202610_2.jsonl"
    assert (tmp_path / "report_202610.jsonl").read_text(encoding="utf-8") == "old\n"


def test_cleanup_deletes_only_old_strict_date_folders(tmp_path):
    today = datetime.date(2026, 10, 29)
    keep = ["20261029", "20260929",            # วันนี้ / ครบ 30 วันพอดี (ยังไม่เกิน)
            "logs", "2026092", "202609011", "20261399", "x20260901", "2026-09-01"]
    gone = ["20260928", "20250101"]
    for n in keep + gone:
        (tmp_path / n).mkdir()
        (tmp_path / n / "a.png").write_bytes(b"1")
    (tmp_path / "20200101").write_text("ไฟล์ ไม่ใช่โฟลเดอร์", encoding="utf-8")
    (tmp_path / "report.jsonl").write_text("x\n", encoding="utf-8")
    removed = M.cleanup_old_error_images(days=30, today=today, root=str(tmp_path))
    assert sorted(removed) == sorted(gone)
    for n in keep:
        assert (tmp_path / n).is_dir(), n
    assert (tmp_path / "20200101").is_file() and (tmp_path / "report.jsonl").is_file()


def test_cleanup_missing_folder_is_harmless(tmp_path):
    assert M.cleanup_old_error_images(root=str(tmp_path / "nope")) == []


def test_web_app_main_runs_cleanup_on_start():
    import inspect
    import web_app
    src = inspect.getsource(web_app.main)
    assert "cleanup_old_error_images()" in src
    assert src.index("cleanup_old_error_images()") < src.index("Api()")


# ---------- 5) เทสไม่แตะ error_reports จริง ----------

def test_conftest_points_reports_to_tmp(_isolate_error_reports):
    real = os.path.join(M.base_dir(), "error_reports")
    assert M.error_reports_dir() == _isolate_error_reports
    assert os.path.abspath(_isolate_error_reports) != os.path.abspath(real)
