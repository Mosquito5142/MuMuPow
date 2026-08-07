"""เทสตัวซิงค์สคริปต์จากโฟลเดอร์ที่ใช้งานจริงกลับเข้า repo

ความเสี่ยงที่ต้องกัน 2 อย่าง:
  1. ลืมซิงค์ -> ลูกค้าได้สคริปต์ตัวอย่าง เปิดโปรแกรมได้แต่ทำงานไม่ได้
  2. ซิงค์แล้วเผลอลาก accounts.json เข้า repo -> รหัสลูกค้าหลุดขึ้น git
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sync_scripts as S


@pytest.fixture
def live(tmp_path, monkeypatch):
    """สร้าง repo ปลอม + โฟลเดอร์ที่ใช้งานจริงปลอม แล้วย้าย cwd ไปที่ repo ปลอม"""
    repo = tmp_path / "repo"
    (repo / "macros").mkdir(parents=True)
    (repo / "script_sets").mkdir()
    (repo / "dist" / "macros").mkdir(parents=True)
    (repo / "dist" / "script_sets").mkdir()
    monkeypatch.chdir(repo)
    return repo


def w(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_detects_new_scripts_made_in_the_app(live):
    w(live / "dist/script_sets/ข้ามhotzone.json", '{"name":"x"}')
    added, changed, removed = S.plan("dist")
    assert "script_sets/ข้ามhotzone.json" in added
    assert changed == [] and removed == []


def test_detects_edited_scripts(live):
    w(live / "macros/รับของเก่า.json", '{"v":1}')
    w(live / "dist/macros/รับของเก่า.json", '{"v":2}')
    added, changed, removed = S.plan("dist")
    assert changed == ["macros/รับของเก่า.json"]
    assert added == []


def test_detects_scripts_deleted_from_the_app(live):
    w(live / "macros/เก่า.json", "{}")
    added, changed, removed = S.plan("dist")
    assert removed == ["macros/เก่า.json"]


def test_identical_content_is_not_flagged(live):
    w(live / "macros/a.json", '{"same":1}')
    w(live / "dist/macros/a.json", '{"same":1}')
    assert S.plan("dist") == ([], [], [])


def test_walks_nested_template_folders(live):
    """templates/รับของ/1.HOME.png — โฟลเดอร์ซ้อนต้องถูกเก็บด้วย ไม่ใช่แค่ชั้นบนสุด"""
    w(live / "dist/templates/รับของ/1.HOME.png", "png")
    added, _c, _r = S.plan("dist")
    assert "templates/รับของ/1.HOME.png" in added


def test_apply_copies_content_into_repo(live):
    w(live / "dist/script_sets/ใหม่.json", '{"steps":[]}')
    added, changed, removed = S.plan("dist")
    S.apply(added, changed, removed, "dist")
    assert (live / "script_sets/ใหม่.json").read_text(encoding="utf-8") == '{"steps":[]}'


def test_apply_removes_stale_repo_files(live):
    w(live / "macros/ลบแล้ว.json", "{}")
    added, changed, removed = S.plan("dist")
    S.apply(added, changed, removed, "dist")
    assert not (live / "macros/ลบแล้ว.json").exists()


def test_apply_refuses_user_data(live):
    """ด่านกันพลาด: ต่อให้มีคนเพิ่ม accounts.json เข้า SYNC_* ก็ต้องไม่ยอมลากเข้า repo"""
    w(live / "dist/accounts.json", "[]")
    with pytest.raises(RuntimeError, match="ข้อมูลของผู้ใช้"):
        S.apply(["accounts.json"], [], [], "dist")


def test_sync_returns_false_when_out_of_date(live):
    """publish.py ใช้ค่านี้ตัดสินใจว่าจะหยุดก่อนปล่อยไหม"""
    w(live / "dist/macros/ใหม่.json", "{}")
    assert S.sync("dist", check_only=True) is False


def test_sync_returns_true_when_already_in_sync(live):
    assert S.sync("dist", check_only=True) is True


def test_sync_survives_missing_live_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert S.sync("ไม่มีโฟลเดอร์นี้") is True


def test_sync_dirs_are_shipped_dirs():
    """ของที่ซิงค์เข้ามาต้องอยู่ในรายการที่จะแพ็กลง ZIP ด้วย ไม่งั้นซิงค์ฟรี"""
    import release_manifest as R
    for d in R.SYNC_DIRS:
        assert d in R.SHIP_DIRS, f"{d} ถูกซิงค์แต่ไม่ได้ถูกแพ็กลง ZIP"
    for f in R.SYNC_FILES:
        assert f in R.SHIP_FILES, f"{f} ถูกซิงค์แต่ไม่ได้ถูกแพ็กลง ZIP"
