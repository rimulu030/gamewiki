"""
PyQt6-based system tray icon implementation.
"""

import logging
import sys
from typing import Optional, Callable

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QObject, pyqtSignal

from src.game_wiki_tooltip.core.utils import package_file
from src.game_wiki_tooltip.core.i18n import t

logger = logging.getLogger(__name__)


class QtTrayIcon(QObject):
    """PyQt6 implementation of system tray icon"""
    
    # Signals
    settings_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray_icon = None
        self._init_tray()
        
    def _init_tray(self):
        """Initialize system tray icon"""
        # Create tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Set icon
        icon_path = package_file("app.ico")
        self.tray_icon.setIcon(QIcon(str(icon_path)))
        
        # Create context menu
        menu = QMenu()
        
        
        # Settings action
        settings_action = QAction(t("tray_settings"), self)
        settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(settings_action)
        
        # Separator
        menu.addSeparator()
        
        # Exit action
        exit_action = QAction(t("tray_exit"), self)
        exit_action.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_action)
        
        # Set menu
        self.tray_icon.setContextMenu(menu)
        
        # Set tooltip
        self.tray_icon.setToolTip(t("tray_tooltip"))
        
        # Double click to open settings
        self.tray_icon.activated.connect(self._on_activated)
        
    def _on_activated(self, reason):
        """Handle tray icon activation"""
        try:
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
                self.settings_requested.emit()
        except Exception as e:
            # Handle PyQt6 enum compatibility issue
            if int(reason) == 2:  # DoubleClick = 2
                self.settings_requested.emit()
    
    def update_text(self):
        """Update tray icon text with current language"""
        if self.tray_icon:
            menu = self.tray_icon.contextMenu()
            if menu:
                actions = menu.actions()
                if len(actions) >= 3:
                    # Settings is at index 0
                    # Exit is at index 2 (after separator)
                    actions[0].setText(t("tray_settings"))  # Settings
                    actions[2].setText(t("tray_exit"))      # Exit
            
            # Update tooltip
            self.tray_icon.setToolTip(t("tray_tooltip"))
            
    def show(self):
        """Show tray icon"""
        if self.tray_icon:
            self.tray_icon.show()
            
    def hide(self):
        """Hide tray icon"""
        if self.tray_icon:
            self.tray_icon.hide()
            
    def update_toggle_text(self, is_visible: bool):
        """Update toggle action text based on visibility state - deprecated"""
        # This method is deprecated and no longer needed
        pass
            
    def show_notification(self, title: str, message: str):
        """Show system notification"""
        if self.tray_icon and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
            
    def cleanup(self):
        """Clean up resources"""
        if self.tray_icon:
            self.tray_icon.hide() 