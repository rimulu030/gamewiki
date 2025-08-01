"""
Direct entry point for running as module: python -m game_wiki_tooltip
This ensures splash screen appears immediately.
"""

import sys
import os

# Minimal check
if sys.platform != "win32":
    print("This tool only works on Windows.")
    sys.exit(1)

# Check if we should use bootstrap (for packaged exe)
if hasattr(sys, '_MEIPASS') or os.environ.get('GAMEWIKI_USE_BOOTSTRAP'):
    # Use bootstrap for immediate splash in packaged mode
    from .ui.qt_app_bootstrap import main
else:
    # Use normal entry for development
    from .ui.qt_app import main

if __name__ == '__main__':
    main()