# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['openrouter_monitor_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('opr.ico', '.'), ('OPR_ban_2.png', '.'), ('OPR_ICO.png', '.'), ('.env.example', '.'), ('README.md', '.')],
    hiddenimports=['customtkinter', 'PIL', 'PIL._tkinter_finder', 'win10toast', 'pystray', 'requests', 'dotenv'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'tkinter.test', 'lib2to3', 'unittest', 'urllib.tests'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [('O', None, 'OPTION'), ('O', None, 'OPTION')],
    name='OpenRouter Monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['opr.ico'],
)
