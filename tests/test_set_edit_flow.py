"""เทสความสมูทของการแก้ 'ชุดคำสั่งย่อย' (Script Sets)

อาการที่ผู้ใช้เจอ:
  1. กด "แก้ไขสเต็ป" แล้วไม่ไปหน้าสคริปต์ และผังไม่รีเฟรช ต้องกดสลับลิสต์↔โฟลว์เอง
  2. บันทึกชุดเสร็จแล้วไม่กลับสคริปต์เดิม ต้องไปเลือกสคริปต์อื่นแล้วเลือกกลับมาใหม่

และกับดักที่ยังไม่เจอแต่เสียหายหนัก:
  3. ระหว่างแก้ชุด ช่องชื่อสคริปต์ยังโชว์ชื่อเดิมและปุ่ม "บันทึก" ยังกดได้
     -> กดแล้วสคริปต์จริง (เป็นร้อยขั้น) โดนทับด้วยขั้นของชุดสั้น ๆ ทันที
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "base_dir", lambda: str(tmp_path))
    (tmp_path / "macros").mkdir()
    (tmp_path / "script_sets").mkdir()

    def write(folder, name, steps):
        p = tmp_path / folder / f"{name}.json"
        p.write_text(json.dumps({"name": name, "steps": steps}, ensure_ascii=False), encoding="utf-8")

    write("macros", "สคริปต์หลัก", [{"type": "tap", "x": str(i), "y": "1"} for i in range(20)])
    write("script_sets", "ชุดย่อย", [{"type": "keyevent", "code": 4} for _ in range(3)])

    a = web_app.Api.__new__(web_app.Api)
    a._push_log = lambda *x, **k: None
    a._log = []
    a.macro_steps = []
    a.current_profile = ""
    a.editing_set = None
    a._set_edit_prev_profile = ""
    a.devices, a.selected, a.profiles = [], set(), {}
    a._load_profiles()
    a.select_profile("สคริปต์หลัก")
    return a


# ---------- จำสคริปต์เดิม + กลับให้อัตโนมัติ ----------

def test_entering_set_edit_remembers_the_open_script(api):
    assert len(api.macro_steps) == 20
    r = api.load_set_to_editor("ชุดย่อย")

    assert r["ok"] is True
    assert api.editing_set == "ชุดย่อย"
    assert len(api.macro_steps) == 3                 # ตัวแก้ไขถือขั้นของชุดแล้ว
    assert r["prevProfile"] == "สคริปต์หลัก"          # แต่จำสคริปต์เดิมไว้


def test_exiting_set_edit_reloads_the_previous_script(api):
    api.load_set_to_editor("ชุดย่อย")
    r = api.exit_set_edit()

    assert r["profile"] == "สคริปต์หลัก"
    assert len(api.macro_steps) == 20                # กลับมาครบ ไม่ต้องเลือกใหม่เอง
    assert api.editing_set is None


def test_editing_a_second_set_keeps_the_original_script_to_return_to(api):
    """กดแก้ชุดอื่นต่อจากในโหมด ต้องไม่เอา 'ชุดแรก' มาเป็นจุดกลับ"""
    api.load_set_to_editor("ชุดย่อย")
    api.load_set_to_editor("ชุดย่อย")                 # เข้าซ้ำ
    assert api._set_edit_prev_profile == "สคริปต์หลัก"
    api.exit_set_edit()
    assert len(api.macro_steps) == 20


def test_exit_without_a_previous_script_is_harmless(api):
    api.current_profile = ""
    api._set_edit_prev_profile = ""
    api.editing_set = "ชุดย่อย"
    r = api.exit_set_edit()
    assert r["ok"] is True and api.editing_set is None


# ---------- กันเขียนทับสคริปต์ด้วยขั้นของชุด ----------

def test_saving_the_script_is_blocked_while_editing_a_set(api, tmp_path):
    """กับดักหลัก: ปุ่ม 'บันทึก' ยังกดได้ระหว่างแก้ชุด — ถ้าปล่อยไว้สคริปต์ 20 ขั้นจะเหลือ 3 ขั้น"""
    api.load_set_to_editor("ชุดย่อย")
    api.save_profile("สคริปต์หลัก")

    saved = json.loads((tmp_path / "macros" / "สคริปต์หลัก.json").read_text(encoding="utf-8"))
    assert len(saved["steps"]) == 20, "สคริปต์เดิมโดนทับด้วยขั้นของชุด"


def test_saving_the_script_works_again_after_exiting(api, tmp_path):
    api.load_set_to_editor("ชุดย่อย")
    api.exit_set_edit()
    api.macro_steps.append({"type": "tap", "x": "99", "y": "99"})
    api.save_profile("สคริปต์หลัก")

    saved = json.loads((tmp_path / "macros" / "สคริปต์หลัก.json").read_text(encoding="utf-8"))
    assert len(saved["steps"]) == 21


def test_saving_the_set_itself_still_works(api, tmp_path):
    api.load_set_to_editor("ชุดย่อย")
    api.macro_steps.append({"type": "keyevent", "code": 4})
    r = api.save_script_set_steps("ชุดย่อย")

    assert r["ok"] is True
    saved = json.loads((tmp_path / "script_sets" / "ชุดย่อย.json").read_text(encoding="utf-8"))
    assert len(saved["steps"]) == 4


# ---------- ฝั่งหน้าเว็บ ----------

def _js(name):
    return io.open(os.path.join(ROOT, "webui", name), encoding="utf-8").read()


def _code_only(js):
    """ตัดบรรทัดคอมเมนต์ออก — เทสนี้สนใจ 'โค้ดที่รันจริง' ไม่ใช่คำที่พูดถึงในคอมเมนต์"""
    return chr(10).join(ln for ln in js.splitlines() if not ln.strip().startswith("//"))


def test_no_call_to_a_function_that_does_not_exist():
    """บั๊กเดิม: เรียก showPage() ซึ่งไม่มีในโปรแกรม แถมมี typeof ครอบไว้เลยเงียบสนิท
    ผลคือกด 'แก้ไขสเต็ป' แล้วไม่เคยพาไปหน้าสคริปต์เลย"""
    all_js = _code_only(_js("app.js") + _js("flow.js") + _js("tools.js"))
    assert "showPage(" not in all_js, "ยังมีการเรียก showPage ที่ไม่มีอยู่จริง"
    assert "function switchPage" in all_js


def test_central_refresher_exists_and_covers_both_views():
    js = _js("flow.js")
    assert "async function refreshScriptView" in js
    i = js.index("async function refreshScriptView")
    body = js[i:i + 400]
    assert "renderSteps" in body and "renderFlow" in body, "ต้องวาดใหม่ทั้งลิสต์และโฟลว์"


def test_script_mutations_refresh_the_flow_too():
    """ทุกจุดที่แก้ข้อมูลสคริปต์ต้องผ่านตัวรีเฟรชกลาง ไม่ใช่ renderSteps() ตรง ๆ
    ไม่งั้นคนที่อยู่โหมดโฟลว์เห็นของเก่าค้าง ต้องกดสลับมุมมองเองแบบที่ผู้ใช้เจอ"""
    js = _js("app.js")
    for marker in ("PY.update_step", "PY.add_step", "PY.delete_step", "PY.move_step"):
        i = js.index(marker)
        line = js[i:js.index("\n", i)]
        assert "refreshScriptView" in line, f"{marker} ยังไม่รีเฟรชผัง: {line.strip()[:90]}"


def test_editing_a_set_switches_page_and_refreshes():
    js = _js("tools.js")
    i = js.index("async function editSetInEditor")
    body = js[i:i + 900]
    assert "switchPage('script')" in body
    assert "refreshScriptView" in body


def test_saving_a_set_returns_to_the_previous_script():
    js = _js("app.js")
    i = js.index("async function saveCurrentEditingSet")
    body = js[i:i + 900]
    assert "exitSetEditMode" in body, "บันทึกชุดเสร็จต้องพากลับสคริปต์เดิม"

    j = js.index("async function exitSetEditMode")
    exit_body = js[j:j + 700]
    assert "PY.exit_set_edit" in exit_body
    assert "refreshScriptView" in exit_body
