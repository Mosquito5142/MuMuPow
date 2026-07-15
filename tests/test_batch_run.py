"""เทส: ช่อง 'ความถี่เช็ค Anchor' และ checkbox 'หยุดรอตรวจทานทีละชุด' ต้องมีผลจริงตอนรัน
(บั๊กเดิม: ทั้งสองเป็นแค่ HTML ตกแต่ง ไม่เคยถูกอ่านโดย run() เลย)"""
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app


class MockController:
    """ไม่แตะ ADB จริง — ใช้แทนเพื่อทดสอบ orchestration ของ Api.run()"""

    def __init__(self):
        self.taps = []

    def capture_screenshot_bytes(self, d):
        return True, b"SCREEN"

    def tap(self, d, x, y):
        self.taps.append((d, x, y))

    def find_image_in_bytes(self, data, path, threshold=0.8):
        return False, 0, 0, "no"

    def match_template_bytes(self, data, tmpl, thr):
        return False, 0, 0, "no"


def _api_with_temp_accounts(n_accounts=4):
    tmp = tempfile.mkdtemp()
    tmp_acc = os.path.join(tmp, "accounts.json")
    accts = [{"email": f"a{i}@x.com", "password": "p", "checked": True, "name": f"acc{i}"}
             for i in range(n_accounts)]
    json.dump(accts, open(tmp_acc, "w", encoding="utf-8"))
    api = web_app.Api()
    api._accounts_path = lambda: tmp_acc   # กัน แตะ accounts.json จริงเด็ดขาด
    api.controller = MockController()
    api.devices = [":7555", ":7556"]
    api.selected = {":7555", ":7556"}
    api.macro_steps = [{"type": "tap", "x": "1", "y": "2", "delay": 0}]
    api.current_profile = "TestProfile"
    return api, tmp


def test_anchor_poll_value_is_read_and_used():
    api, tmp = _api_with_temp_accounts(2)
    try:
        r = api.run(anchor_poll="1.75", pause_between_batches=False)
        assert r["ok"] is True
        assert api._anchor_poll == 1.75
        api._run_thread.join(timeout=5)
        assert api._runner.anchor_poll == 1.75
    finally:
        shutil.rmtree(tmp)


def test_anchor_poll_blank_falls_back_to_default():
    api, tmp = _api_with_temp_accounts(2)
    try:
        api.run(anchor_poll="", pause_between_batches=False)
        assert api._anchor_poll == 2.0
        api._run_thread.join(timeout=5)
    finally:
        shutil.rmtree(tmp)


def test_pause_between_batches_stops_after_first_batch():
    # 4 บัญชี, 2 จอ -> ชุดแรก = 2 บัญชี, เหลือ 2 บัญชีรอชุดถัดไป
    api, tmp = _api_with_temp_accounts(4)
    try:
        r = api.run(anchor_poll="0.5", pause_between_batches=True)
        assert r["ok"] is True
        api._run_thread.join(timeout=5)
        assert api._running is False
        assert api._awaiting_next_batch is True
        assert len(api._batch_pending) == 2
        st = api.get_run_state()
        assert st["awaitingNextBatch"] is True
        assert st["remainingBatch"] == 2
        assert len(api.controller.taps) == 2   # ชุดแรกกดแล้ว 2 ครั้ง (2 จอ x 1 tap/บัญชี)
    finally:
        shutil.rmtree(tmp)


def test_continue_batch_runs_remaining_and_finishes():
    api, tmp = _api_with_temp_accounts(4)
    try:
        api.run(anchor_poll="0.5", pause_between_batches=True)
        api._run_thread.join(timeout=5)
        assert api._awaiting_next_batch is True

        r = api.continue_batch()
        assert r["ok"] is True
        api._run_thread.join(timeout=5)

        assert api._awaiting_next_batch is False
        assert api._running is False
        assert len(api._batch_pending) == 0
        assert len(api.controller.taps) == 4   # ครบทั้ง 4 บัญชีแล้ว
    finally:
        shutil.rmtree(tmp)


def test_continue_batch_noop_when_not_awaiting():
    api, tmp = _api_with_temp_accounts(2)
    try:
        r = api.continue_batch()
        assert r["ok"] is False   # ยังไม่เคยรัน -> ไม่มีอะไรให้ต่อ
    finally:
        shutil.rmtree(tmp)


def test_stop_during_batch_pause_clears_pending():
    api, tmp = _api_with_temp_accounts(4)
    try:
        api.run(anchor_poll="0.5", pause_between_batches=True)
        api._run_thread.join(timeout=5)
        assert api._awaiting_next_batch is True

        api.stop()
        assert api._awaiting_next_batch is False
        assert api._batch_pending == []
        # กด "รันชุดถัดไป" หลังหยุดแล้วต้องไม่ทำอะไร
        r = api.continue_batch()
        assert r["ok"] is False
    finally:
        shutil.rmtree(tmp)


def test_normal_run_still_uses_full_queue_not_batches():
    """โหมดปกติ (pause_between_batches=False) ต้องรันครบทุกบัญชีรวดเดียว ไม่ใช่ทีละชุด"""
    api, tmp = _api_with_temp_accounts(4)
    try:
        api.run(anchor_poll="0.5", pause_between_batches=False)
        api._run_thread.join(timeout=5)
        assert api._awaiting_next_batch is False
        assert api._running is False
        assert len(api.controller.taps) == 4
    finally:
        shutil.rmtree(tmp)
