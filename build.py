#!/usr/bin/env python3
"""
Build script for creating Windows executable using PyInstaller.
Creates a standalone, optimized executable with all dependencies bundled.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# Configuration
APP_NAME = "OpenRouter Monitor"
APP_VERSION = "1.1.0"
MAIN_SCRIPT = "openrouter_monitor_gui.py"
ICON_FILE = "MEDIAS/openrouter-monitor.ico"
LOGO_FILE = "MEDIAS/Emblème néon doré sur badge sombre.png"
BANNER_FILE = "MEDIAS/Baniere OpenRouter Monitor avec planète orbitale lumineuse.png"
DIST_DIR = "dist"
BUILD_DIR = "build"
SPEC_FILE = f"{APP_NAME}.spec"

# Ensure we're on Windows
if sys.platform != 'win32':
    print("This build script is for Windows only.")
    sys.exit(1)

def clean_build_dirs():
    """Clean previous build artifacts."""
    print("Cleaning previous build artifacts...")
    project_dir = Path(__file__).resolve().parent
    build_path = (project_dir / BUILD_DIR).resolve()
    if not build_path.is_relative_to(project_dir):
        raise ValueError("Build directory must stay inside the project")
    if build_path.exists():
        shutil.rmtree(build_path)
    # Keep previous release ZIPs in dist; PyInstaller replaces only the executable.
    print("[OK] Clean complete")

def create_icon():
    """Convert the supplied logo to a Windows icon at all standard resolutions."""
    from PIL import Image
    with Image.open(LOGO_FILE) as source:
        image = source.convert('RGBA')
        bounds = image.getchannel('A').getbbox()
        if bounds:
            image = image.crop(bounds)
        canvas = Image.new('RGBA', (256, 256))
        image.thumbnail((240, 240), Image.Resampling.LANCZOS)
        canvas.alpha_composite(image, ((256 - image.width) // 2, (256 - image.height) // 2))
        canvas.save(ICON_FILE, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ICON_FILE

def build_executable():
    """Build executable with PyInstaller."""
    print("Building executable with PyInstaller...")

    # PyInstaller command with optimizations
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',                    # Single executable
        '--windowed',                   # No console window
        '--name', APP_NAME,
        '--clean',                      # Clean cache
        '--noconfirm',                  # Overwrite without confirmation
    ]

    # Add icon if exists
    icon = create_icon()
    if icon:
        cmd.extend(['--icon', icon])

    # Add version info
    version_file = 'version_info.txt'
    if Path(version_file).exists():
        cmd.extend(['--version-file', version_file])

    # Add data files (images, resources)
    data_files = []
    for img in ['opr.ico', 'OPR_ban_2.png', 'OPR_ICO.png']:
        if Path(img).exists():
            data_files.append(f'--add-data={img};.')
    for resource in [ICON_FILE, LOGO_FILE, BANNER_FILE]:
        data_files.append(f'--add-data={resource};MEDIAS')
    # Include .env.example for user reference
    if Path('.env.example').exists():
        data_files.append('--add-data=.env.example;.')
    # Include README.md
    if Path('README.md').exists():
        data_files.append('--add-data=README.md;.')

    cmd.extend(data_files)

    # Hidden imports (modules imported dynamically)
    cmd.extend(['--collect-data=customtkinter'])
    hidden_imports = [
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'win10toast',
        'pystray',
        'requests',
        'dotenv',
    ]
    for imp in hidden_imports:
        cmd.append(f'--hidden-import={imp}')

    # Exclude unnecessary modules to reduce size
    # Only exclude heavy scientific/ML libraries - keep stdlib intact
    excludes = [
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'tkinter.test',
        'lib2to3',
        'unittest',
        'urllib.tests',
    ]
    for exc in excludes:
        cmd.append(f'--exclude-module={exc}')

    # Optimization flags
    cmd.extend([
        '--optimize=2',                 # Python optimization level
        '--noupx',                      # Disable UPX (can be toggled)
    ])

    # Optionally enable UPX if available
    # UPX_PATH = r"C:\upx"  # Uncomment and set path if UPX installed
    # if Path(UPX_PATH).exists():
    #     cmd.extend(['--upx-dir', UPX_PATH])

    # Add the main script
    cmd.append(MAIN_SCRIPT)

    # Run PyInstaller
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print("\n[OK] Build successful!")
        exe_path = Path(DIST_DIR) / f"{APP_NAME}.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / 1024 / 1024
            print(f"Executable created: {exe_path.absolute()}")
            print(f"Size: {size_mb:.2f} MB")
            return True
    else:
        print(f"[FAIL] Build failed with code {result.returncode}")
        return False

    return False

def create_version_info():
    """Create version info resource file."""
    version_tuple = ', '.join([*APP_VERSION.split('.'), '0'])
    version_content = f"""
# UTF-8
#
# This file is used by the version resource compiler to embed version info.
# For more info, see:
# https://docs.microsoft.com/en-us/windows/win32/menurc/versioninfo-resource
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({version_tuple}),
    prodvers=({version_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{APP_NAME}'),
        StringStruct('FileDescription', 'OpenRouter AI Model Monitor'),
        StringStruct('FileVersion', '{APP_VERSION}'),
        StringStruct('InternalName', '{APP_NAME}'),
        StringStruct('LegalCopyright', 'Copyright (c) 2024 {APP_NAME}'),
        StringStruct('OriginalFilename', '{APP_NAME}.exe'),
        StringStruct('ProductName', '{APP_NAME}'),
        StringStruct('ProductVersion', '{APP_VERSION}')])
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open('version_info.txt', 'w', encoding='utf-8') as f:
        f.write(version_content)
    print("[OK] Version info created")

def main():
    """Main build process."""
    print(f"\n{'='*60}")
    print(f"  {APP_NAME} - Build Script")
    print(f"{'='*60}\n")

    # Check PyInstaller
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("ERROR: PyInstaller not installed. Run: pip install pyinstaller")
        sys.exit(1)

    # Clean
    clean_build_dirs()

    # Create version info
    create_version_info()

    # Build
    if build_executable():
        print("\nBuild complete!")
        print("\nTo create an installer, open installer.iss in Inno Setup and compile.")
        print("Or run: python build_installer.py")
        return 0
    else:
        print("\nBuild failed!")
        return 1

if __name__ == '__main__':
    sys.exit(main())
