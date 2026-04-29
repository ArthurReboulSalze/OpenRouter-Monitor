#!/usr/bin/env python3
"""
OpenRouter Monitor - Launcher
Wraps the main application with proper error handling and logging.
"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    # Import and run main app
    from openrouter_monitor_gui import main
    sys.exit(main())

except ImportError as e:
    print(f"ERROR: Missing dependencies: {e}")
    print("\nPlease install dependencies:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
