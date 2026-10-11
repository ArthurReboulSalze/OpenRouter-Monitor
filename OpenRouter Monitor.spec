# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('opr.ico', '.'), ('OPR_ban_2.png', '.'), ('OPR_ICO.png', '.'), ('MEDIAS/openrouter-monitor.ico', 'MEDIAS'), ('MEDIAS/Emblème néon doré sur badge sombre.png', 'MEDIAS'), ('MEDIAS/Baniere OpenRouter Monitor avec planète orbitale lumineuse.png', 'MEDIAS'), ('.env.example', '.'), ('README.md', '.')]
datas += collect_data_files('customtkinter')


a = Analysis(
    ['openrouter_monitor_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    icon=['MEDIAS/openrouter-monitor.ico'],
)
