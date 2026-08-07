"""เทสตัวกันข้อมูลลูกค้าหายตอนอัปเดต

ZIP อัปเดตถูกออกแบบให้ลูกค้า "แตกทับโฟลเดอร์เดิม" ได้เลยโดยไม่ต้องก็อปอะไรกลับ
ซึ่งจะปลอดภัยก็ต่อเมื่อไฟล์ข้อมูลของลูกค้าไม่ได้อยู่ใน ZIP ตั้งแต่แรก
ถ้าวันหนึ่งมีคนเผลอเพิ่ม accounts.json เข้า SHIP_FILES ลูกค้าทุกคนจะเสียรหัสทั้งหมด
ตอนอัปเดตครั้งถัดไป — เทสชุดนี้มีไว้ให้แดงก่อนที่จะไปถึงตรงนั้น
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import release_manifest as R


CRITICAL = ["accounts.json", "ports.json", "adb_config.json"]


@pytest.mark.parametrize("name", CRITICAL)
def test_critical_user_files_are_never_shipped(name):
    """3 ไฟล์นี้คือของที่ลูกค้าเคยต้องก็อปเองทุกครั้ง — ต้องไม่มีทางหลุดเข้า ZIP"""
    assert name in R.USER_DATA_FILES
    assert name not in R.SHIP_FILES
    assert R.is_user_data(name)


def test_user_data_and_ship_lists_never_overlap():
    assert set(R.SHIP_FILES) & set(R.USER_DATA_FILES) == set()


def test_ship_dirs_are_not_user_data_dirs():
    assert set(R.SHIP_DIRS) & set(R.USER_DATA_DIRS) == set()


def test_seed_files_are_user_data():
    """ไฟล์ค่าตั้งต้นต้องถูกจัดเป็นของลูกค้า ไม่งั้นมันจะไปทับค่าที่ลูกค้าตั้งเองตอนอัปเดต"""
    for f in R.SEED_FILES:
        assert f in R.USER_DATA_FILES, f"{f} ต้องอยู่ใน USER_DATA_FILES ด้วย"


def test_build_output_dirs_are_excluded():
    """dist/ ของเครื่องที่ใช้งานจริงมี accounts.json + macros/ + error_reports/ อยู่
    ห้ามถูกกวาดเข้า ZIP เด็ดขาด"""
    for d in ("dist", "build", "__pycache__"):
        assert d in R.USER_DATA_DIRS


def test_is_user_data_matches_paths_inside_excluded_dirs():
    assert R.is_user_data("error_reports/20260806/x.png")
    assert R.is_user_data("dist/accounts.json")
    assert R.is_user_data("./ports.json")
    assert R.is_user_data("screenshots\\a\\b.png")   # พาธแบบ Windows ต้องจับได้ด้วย


def test_is_user_data_lets_shipped_content_through():
    assert not R.is_user_data("macros/รับของเก่า.json")
    assert not R.is_user_data("script_sets/ข้ามhotzone.json")
    assert not R.is_user_data("templates/lobby.png")
    assert not R.is_user_data("MuMupow.exe")


def test_update_zip_rejects_user_data(tmp_path):
    """ด่านสุดท้ายใน publish.write_zip ต้องหยุดการปล่อย ไม่ใช่เตือนแล้วปล่อยผ่าน"""
    import publish
    fake = tmp_path / "accounts.json"
    fake.write_text("[]", encoding="utf-8")

    with pytest.raises(RuntimeError, match="หลุดเข้า ZIP"):
        publish.write_zip(str(tmp_path / "out.zip"), [(str(fake), "accounts.json")],
                          "note.txt", "x")


def test_full_zip_allows_seed_files_only(tmp_path):
    """full.zip ใส่ค่าตั้งต้นได้ (ตั้งใจ) แต่ต้องยังกัน accounts.json อยู่"""
    import publish
    seed = tmp_path / "presets.json"
    seed.write_text("{}", encoding="utf-8")
    acc = tmp_path / "accounts.json"
    acc.write_text("[]", encoding="utf-8")

    out = str(tmp_path / "full.zip")
    publish.write_zip(out, [(str(seed), "presets.json")], "n.txt", "x", allow=R.SEED_FILES)
    assert os.path.exists(out)

    with pytest.raises(RuntimeError):
        publish.write_zip(str(tmp_path / "bad.zip"), [(str(acc), "accounts.json")],
                          "n.txt", "x", allow=R.SEED_FILES)
