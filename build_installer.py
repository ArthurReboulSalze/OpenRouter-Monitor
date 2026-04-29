#!/usr/bin/env python3
"""
Build the Windows installer using Inno Setup.
Requires: Inno Setup (ISCC.exe) installed or available in PATH.
"""

import subprocess
import sys
import uuid
from pathlib import Path

def find_iscc():
    """Find Inno Setup Compiler (ISCC.exe)."""
    paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
    ]
    for p in paths:
        if Path(p).exists():
            return p
    import shutil
    iscc = shutil.which('ISCC.exe')
    return iscc

def generate_guid():
    """Generate a new GUID for AppId."""
    return str(uuid.uuid4()).upper()

def update_iss_with_guid(iss_path, guid):
    """Replace GUID placeholder in ISS file."""
    content = iss_path.read_text(encoding='utf-8')
    new_content = content.replace('{{GENERATE-GUID-HERE}}', guid)
    return new_content

def main():
    print("=" * 60)
    print("OpenRouter Monitor - Installer Builder")
    print("=" * 60 + "\n")

    # Check ISS script
    iss_path = Path("installer.iss")
    if not iss_path.exists():
        print(f"ERROR: {iss_path} not found")
        sys.exit(1)

    # Generate GUID
    guid = generate_guid()
    print(f"Generated AppId GUID: {guid}")

    # Update ISS file with GUID
    print("Updating installer script...")
    iss_content = update_iss_with_guid(iss_path, guid)

    # Write to temporary file for compilation
    temp_iss = Path("installer_temp.iss")
    temp_iss.write_text(iss_content, encoding='utf-8')

    # Find ISCC
    iscc = find_iscc()
    if not iscc:
        print("ERROR: Inno Setup Compiler (ISCC.exe) not found!")
        print("Download from: https://jrsoftware.org/isinfo.php")
        sys.exit(1)

    print(f"Using: {iscc}")

    # Compile
    print("Compiling installer...")
    result = subprocess.run([iscc, str(temp_iss)], capture_output=False)

    if result.returncode == 0:
        print("\n[OK] Installer build successful!")
        exe = Path("Output") / "OpenRouterMonitorSetup.exe"
        if exe.exists():
            size_mb = exe.stat().st_size / 1024 / 1024
            print(f"Installer: {exe.absolute()}")
            print(f"Size: {size_mb:.2f} MB")
        # Clean temp
        temp_iss.unlink(missing_ok=True)
        return 0
    else:
        print(f"\n[FAIL] Installer build failed (code {result.returncode})")
        temp_iss.unlink(missing_ok=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())
