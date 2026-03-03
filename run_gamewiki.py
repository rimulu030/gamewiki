#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bootstrap entry for packaged exe. Catches startup errors, prints to console,
shows a GUI message box, and keeps console open so user can read output.
"""
import sys


def _show_error(msg: str, keep_console_open: bool = True):
    """Print to console, show Windows message box, optionally wait so console stays open."""
    print(msg, file=sys.stderr)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            msg,
            "GameWiki Assistant - 启动错误",
            0x10,  # MB_ICONHAND
        )
    except Exception:
        pass
    if keep_console_open:
        try:
            input("\n按 Enter 键关闭...")
        except Exception:
            pass


def main():
    if sys.platform != "win32":
        _show_error("本程序仅支持 Windows。")
        sys.exit(1)

    try:
        from src.game_wiki_tooltip.qt_app import main as qt_main
        qt_main()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        _show_error(f"启动失败：\n\n{e}\n\n（详细信息已输出到控制台）", keep_console_open=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
