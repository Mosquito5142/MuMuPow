# -*- mode: python ; coding: utf-8 -*-
# Build ตัว UI ใหม่ (pywebview) เป็น .exe แยก ไม่ทับ MuMupow.exe เดิม
from PyInstaller.utils.hooks import collect_all

datas = [('webui', 'webui')]      # บันเดิลไฟล์ดีไซน์เข้าไปในตัว exe
binaries = []
hiddenimports = ['clr', 'webview.platforms.edgechromium']

# เก็บ dependency ของ pywebview (webview data/js, pythonnet loader ฯลฯ) ให้ครบ
for pkg in ('webview', 'clr_loader', 'proxy_tools', 'bottle'):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ['web_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MuMupow_new',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.ico',
)
