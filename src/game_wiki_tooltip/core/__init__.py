"""
Core module for game wiki tooltip application.
Contains configuration, internationalization, history management and utilities.
"""

from .config import SettingsManager, GameConfigManager, LLMConfig
from .i18n import init_translations, t
from .history_manager import WebHistoryManager
from .utils import (
    APPDATA_DIR, 
    package_file,
    get_foreground_title,
    show_cursor_until_visible
)

__all__ = [
    'SettingsManager',
    'GameConfigManager', 
    'LLMConfig',
    'init_translations',
    't',
    'WebHistoryManager',
    'APPDATA_DIR',
    'package_file',
    'get_foreground_title',
    'show_cursor_until_visible'
]