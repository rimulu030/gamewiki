"""
PyQt6-based settings window with hotkey and API configuration.
"""

import logging
import os
import json
import shutil

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QCheckBox, QComboBox, QLineEdit,
    QFrame, QMessageBox, QGroupBox, QDialog,
    QListWidget, QListWidgetItem, QInputDialog, QProgressBar, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QWheelEvent

from src.game_wiki_tooltip.core.config import SettingsManager
from src.game_wiki_tooltip.core.utils import package_file, APPDATA_DIR
from src.game_wiki_tooltip.core.i18n import init_translations, t

# Import get_audio_input_devices at module level to catch import errors early
try:
    from src.game_wiki_tooltip.window_component import get_audio_input_devices
    AUDIO_DEVICES_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Could not import get_audio_input_devices: {e}")
    AUDIO_DEVICES_AVAILABLE = False
    get_audio_input_devices = None

logger = logging.getLogger(__name__)


class NoScrollComboBox(QComboBox):
    """ComboBox that ignores wheel events to prevent accidental value changes"""
    def wheelEvent(self, event: QWheelEvent):
        # Ignore wheel event to prevent scrolling
        event.ignore()


class ApiKeyMissingDialog(QDialog):
    """Custom dialog for handling API key missing notifications"""
    
    def __init__(self, missing_keys, parent=None):
        super().__init__(parent)
        self.missing_keys = missing_keys
        self.dont_remind = False
        self.open_settings = False
        self._init_ui()
        
    def _init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("GameWiki Assistant")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.setFixedSize(400, 220)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel(t("dialog_ai_unavailable_title"))
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #d32f2f;")
        layout.addWidget(title_label)

        # Message content
        message = t("dialog_ai_unavailable_msg", keys=', '.join(self.missing_keys))
        
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("font-size: 11px; line-height: 1.4;")
        layout.addWidget(message_label)
        
        # "Don't remind me again" checkbox
        self.dont_remind_checkbox = QCheckBox(t("checkbox_dont_remind"))
        self.dont_remind_checkbox.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.dont_remind_checkbox)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Configure button
        config_button = QPushButton(t("btn_configure_api_keys"))
        config_button.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
        """)
        config_button.clicked.connect(self._on_configure_clicked)
        button_layout.addWidget(config_button)
        
        # Later button
        later_button = QPushButton(t("btn_maybe_later"))
        later_button.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        later_button.clicked.connect(self._on_later_clicked)
        button_layout.addWidget(later_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
    def _on_configure_clicked(self):
        """User clicked configure button"""
        self.dont_remind = self.dont_remind_checkbox.isChecked()
        self.open_settings = True
        self.accept()
        
    def _on_later_clicked(self):
        """User clicked later button"""
        self.dont_remind = self.dont_remind_checkbox.isChecked()
        self.open_settings = False
        self.accept()


class QtSettingsWindow(QMainWindow):
    """Settings window with hotkey and API configuration"""
    
    # Signals
    settings_applied = pyqtSignal()
    language_changed = pyqtSignal()
    
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.wiki_urls_modified = False  # Track if wiki URLs have been modified
        self.games_config = {}  # Initialize games config
        
        # Initialize translation manager based on current settings
        settings = self.settings_manager.get()
        current_language = settings.get('language', 'en')
        init_translations(current_language)
        
        self._init_ui()
        self._load_settings()
        
    def _init_ui(self):
        """Initialize UI"""
        self.setWindowTitle(t("settings_title"))
        # Use minimum size instead of fixed size to avoid layout issues
        self.setMinimumSize(600, 500)
        self.resize(600, 500)  # Set initial size
        
        # Set window icon
        try:
            icon_path = package_file("app.ico")
            self.setWindowIcon(QIcon(str(icon_path)))
        except:
            pass
            
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create tabs - hotkey first (now includes language and audio settings)
        self._create_hotkey_tab()  # General Settings tab
        self._create_shortcuts_tab()  # Add shortcuts tab as second
        self._create_wiki_tab()  # Add wiki tab as third
        self._create_api_tab()
        
        # Set default tab to hotkey (first tab)
        self.tab_widget.setCurrentIndex(0)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Apply button
        self.apply_button = QPushButton(t("apply_button"))
        self.apply_button.setFixedHeight(35)
        self.apply_button.setStyleSheet("""
            QPushButton {
                background-color: #1668dc;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #4096ff;
            }
        """)
        self.apply_button.clicked.connect(self._on_apply)
        button_layout.addWidget(self.apply_button)
        
        # Cancel button
        self.cancel_button = QPushButton(t("cancel_button"))
        self.cancel_button.setFixedHeight(35)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                color: #333;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 14px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # Force layout update to prevent window size issues
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        self.updateGeometry()
        
    
    def _create_chinese_model_section(self):
        """Create Chinese voice model download section"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 10, 0, 0)
        
        # Model status label
        self.chinese_model_status = QLabel(t("label_chinese_model_not_installed"))
        self.chinese_model_status.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        layout.addWidget(self.chinese_model_status)
        
        # Download button and progress
        download_layout = QHBoxLayout()
        
        self.download_chinese_btn = QPushButton(t("btn_download_chinese_model_140mb"))
        self.download_chinese_btn.clicked.connect(self._download_chinese_model)
        download_layout.addWidget(self.download_chinese_btn)
        
        self.download_progress = QProgressBar()
        self.download_progress.setVisible(False)
        self.download_progress.setMaximum(100)
        download_layout.addWidget(self.download_progress)
        
        layout.addLayout(download_layout)
        
        # Info label
        info_label = QLabel(t("label_chinese_model_info"))
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        return widget
    
    def _download_chinese_model(self):
        """Download Chinese voice model"""
        try:
            from src.game_wiki_tooltip.window_component.vosk_model_manager import VoskModelManager
            
            manager = VoskModelManager()
            if not manager:
                QMessageBox.warning(self, t("error"), t("label_voice_not_available"))
                return
            
            # Disable button and show progress
            self.download_chinese_btn.setEnabled(False)
            self.download_progress.setVisible(True)
            self.chinese_model_status.setText(t("label_downloading_chinese_model"))
            self.chinese_model_status.setStyleSheet("color: #1971c2;")
            
            # Create download thread
            from PyQt6.QtCore import QThread, pyqtSignal
            
            class DownloadThread(QThread):
                progress = pyqtSignal(int, str)
                finished = pyqtSignal(bool, str)
                
                def run(self):
                    manager = VoskModelManager()
                    def progress_callback(progress, status):
                        self.progress.emit(int(progress), status)
                    
                    success = manager.download_model('chinese', progress_callback)
                    if success:
                        self.finished.emit(True, t("label_chinese_model_download_success"))
                    else:
                        self.finished.emit(False, t("label_chinese_model_download_failed"))
            
            self.download_thread = DownloadThread()
            self.download_thread.progress.connect(self._update_download_progress)
            self.download_thread.finished.connect(self._download_finished)
            self.download_thread.start()
            
        except Exception as e:
            logger.error(f"Failed to start Chinese model download: {e}")
            QMessageBox.critical(self, t("error"), f"Failed to download: {str(e)}")
            self.download_chinese_btn.setEnabled(True)
            self.download_progress.setVisible(False)
    
    def _update_download_progress(self, progress, status):
        """Update download progress"""
        self.download_progress.setValue(progress)
        self.chinese_model_status.setText(status)
    
    def _download_finished(self, success, message):
        """Handle download completion"""
        self.download_progress.setVisible(False)
        self.download_chinese_btn.setEnabled(True)
        
        if success:
            self.chinese_model_status.setText(t("label_chinese_model_installed"))
            self.chinese_model_status.setStyleSheet("color: #2f9e44; font-weight: bold;")
            self.download_chinese_btn.setText(t("btn_redownload_chinese_model"))
            QMessageBox.information(self, t("success"), message)
        else:
            self.chinese_model_status.setText(t("label_chinese_model_not_installed"))
            self.chinese_model_status.setStyleSheet("color: #ff6b6b; font-weight: bold;")
            QMessageBox.warning(self, t("error"), message)
    
    def _check_chinese_model_status(self):
        """Check if Chinese model is installed"""
        try:
            from src.game_wiki_tooltip.window_component.vosk_model_manager import VoskModelManager
            
            manager = VoskModelManager()
            if manager.is_model_available('chinese'):
                self.chinese_model_status.setText(t("label_chinese_model_installed"))
                self.chinese_model_status.setStyleSheet("color: #2f9e44; font-weight: bold;")
                self.download_chinese_btn.setText(t("btn_redownload_chinese_model"))
            else:
                self.chinese_model_status.setText(t("label_chinese_model_not_installed"))
                self.chinese_model_status.setStyleSheet("color: #ff6b6b; font-weight: bold;")
                self.download_chinese_btn.setText(t("btn_download_chinese_model_42mb"))
        except Exception as e:
            logger.error(f"Failed to check Chinese model status: {e}")
    
    def _populate_audio_devices(self, force_refresh=False):
        """Populate audio device combo box
        
        Args:
            force_refresh: Force re-enumeration of devices, bypassing cache
        """
        logger.debug(f"_populate_audio_devices called with force_refresh={force_refresh}")
        
        try:
            self.audio_device_combo.clear()
            
            # Add default option
            self.audio_device_combo.addItem(t("label_system_default"), None)
            
            # Check if audio devices function is available
            if not AUDIO_DEVICES_AVAILABLE or get_audio_input_devices is None:
                logger.warning("Audio device enumeration not available - module import failed")
                self.audio_device_combo.addItem(t("label_audio_unavailable"), None)
                return
            
            logger.debug("Calling get_audio_input_devices...")
            # Pass settings manager to enable cache saving
            devices = get_audio_input_devices(force_refresh=force_refresh, settings_manager=self.settings_manager)
            logger.debug(f"get_audio_input_devices returned {len(devices) if devices else 0} devices")
            
            if devices:
                for device in devices:
                    device_name = device['name']
                    device_index = device['index']
                    # Use clean device name without index for better readability
                    self.audio_device_combo.addItem(device_name, device_index)
                logger.info(f"Populated combo box with {len(devices)} audio devices")
            else:
                logger.warning("No audio devices returned")
                self.audio_device_combo.addItem("No audio devices found", None)
                
        except Exception as e:
            logger.error(f"Failed to populate audio devices: {e}", exc_info=True)
            # Add error indicator
            try:
                self.audio_device_combo.addItem(f"Error: {str(e)[:50]}", None)
            except:
                pass
    
    def _safe_refresh_audio_devices(self):
        """Safe wrapper for refresh button click to prevent application crashes"""
        try:
            logger.debug("Safe refresh wrapper called")
            self._refresh_audio_devices()
        except Exception as e:
            logger.critical(f"Unhandled exception in refresh button click: {e}", exc_info=True)
            try:
                # Try to show error dialog
                QMessageBox.critical(
                    self,
                    "Critical Error",
                    f"An unexpected error occurred:\n{str(e)}\n\nThe application may be unstable."
                )
            except:
                # Even dialog failed, just log it
                logger.critical("Failed to show error dialog")
    
    def _refresh_audio_devices(self):
        """Refresh audio device list with anti-bounce and status feedback"""
        logger.info("Refresh devices button clicked")
        
        try:
            from PyQt6.QtCore import QTimer
            
            # Disable refresh button to prevent rapid clicking
            self.refresh_button.setEnabled(False)
            self.refresh_button.setText(t("refreshing_devices"))
            logger.debug("Button disabled, text changed to 'Refreshing...'")
            
            # Save current selection
            current_selection = self.audio_device_combo.currentData()
            logger.debug(f"Current device selection saved: {current_selection}")
            
            try:
                # Check if audio devices are available
                if not AUDIO_DEVICES_AVAILABLE:
                    logger.error("Cannot refresh - audio devices module not available")
                    QMessageBox.warning(
                        self, 
                        "Audio Unavailable",
                        "Audio device enumeration is not available.\nPlease check that sounddevice is installed."
                    )
                    self.refresh_button.setText(t("btn_unavailable"))
                    QTimer.singleShot(1500, lambda: self.refresh_button.setText(t("refresh_devices_button")))
                    return
                
                logger.debug("Starting device refresh...")
                # Force refresh (internal anti-bounce will be applied)
                self._populate_audio_devices(force_refresh=True)
                logger.debug("Device refresh completed successfully")
                
                # Show success message
                self.refresh_button.setText(t("refresh_complete"))
                QTimer.singleShot(1000, lambda: self.refresh_button.setText(t("refresh_devices_button")))
                
                # Try to restore previous selection
                if current_selection is not None:
                    for i in range(self.audio_device_combo.count()):
                        if self.audio_device_combo.itemData(i) == current_selection:
                            self.audio_device_combo.setCurrentIndex(i)
                            logger.debug(f"Restored device selection to index {i}")
                            break
                
            except Exception as e:
                # Handle any errors during refresh
                logger.error(f"Error during device refresh: {e}", exc_info=True)
                self.refresh_button.setText(t("btn_refresh_failed"))
                QTimer.singleShot(1500, lambda: self.refresh_button.setText(t("refresh_devices_button")))
                
                # Show error dialog to user
                QMessageBox.critical(
                    self,
                    "Refresh Error",
                    f"Failed to refresh audio devices:\n{str(e)}\n\nCheck the log for details."
                )
            
        except Exception as outer_e:
            # Handle any errors in the outer try block (like QTimer import)
            logger.error(f"Critical error in _refresh_audio_devices: {outer_e}", exc_info=True)
            try:
                QMessageBox.critical(
                    self,
                    "Critical Error", 
                    f"A critical error occurred:\n{str(outer_e)}"
                )
            except:
                pass
        
        finally:
            # Re-enable button after 2 seconds
            try:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(2000, lambda: self.refresh_button.setEnabled(True))
                logger.debug("Button re-enable timer set for 2 seconds")
            except Exception as e:
                logger.error(f"Failed to set re-enable timer: {e}")
                # Try to re-enable immediately as fallback
                try:
                    self.refresh_button.setEnabled(True)
                except:
                    pass
        
    def switch_to_api_tab(self):
        """Switch to API configuration tab"""
        # API configuration tab is the fourth one, index 3 (because Wiki tab is inserted at position 3)
        self.tab_widget.setCurrentIndex(3)
        
    def _create_shortcuts_tab(self):
        """Create shortcuts management tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        
        # Title
        title_label = QLabel(t("shortcuts_title"))
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)

        # Explanation
        info_label = QLabel(t("shortcuts_info"))
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666;")
        layout.addWidget(info_label)
        
        # List widget for shortcuts
        self.shortcuts_list = QListWidget()
        self.shortcuts_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
                background-color: white;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #eee;
                color: #333;
                background-color: transparent;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
            QListWidget::item:last-child {
                border-bottom: none;
            }
        """)
        
        # Load existing shortcuts
        self._load_shortcuts_list()
        
        layout.addWidget(self.shortcuts_list)
        
        # Buttons for add/remove
        button_layout = QHBoxLayout()
        
        self.add_shortcut_btn = QPushButton(t("btn_add_website"))
        self.add_shortcut_btn.clicked.connect(self._add_shortcut)
        button_layout.addWidget(self.add_shortcut_btn)
        
        self.edit_shortcut_btn = QPushButton(t("btn_edit_selected"))
        self.edit_shortcut_btn.clicked.connect(self._edit_shortcut)
        button_layout.addWidget(self.edit_shortcut_btn)
        
        self.toggle_visibility_btn = QPushButton(t("btn_hide_show_selected"))
        self.toggle_visibility_btn.clicked.connect(self._toggle_visibility)
        button_layout.addWidget(self.toggle_visibility_btn)
        
        self.remove_shortcut_btn = QPushButton(t("btn_remove_selected"))
        self.remove_shortcut_btn.clicked.connect(self._remove_shortcut)
        button_layout.addWidget(self.remove_shortcut_btn)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
        self.tab_widget.addTab(tab, t("tab_quick_access"))
    
    def _load_shortcuts_list(self):
        """Load shortcuts into the list widget"""
        self.shortcuts_list.clear()
        
        # Get shortcuts from settings
        shortcuts = self.settings_manager.get('shortcuts', [])
        
        # Add items to list
        for shortcut in shortcuts:
            # Show visibility status in the text
            visibility_status = " (hidden)" if not shortcut.get('visible', True) else ""
            item_text = f"{shortcut['name']} - {shortcut['url']}{visibility_status}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, shortcut)
            # Set different color for hidden items
            if not shortcut.get('visible', True):
                item.setForeground(Qt.GlobalColor.gray)
            self.shortcuts_list.addItem(item)
    
    def _add_shortcut(self):
        """Add a new shortcut"""
        # Get name
        name, ok = QInputDialog.getText(self, "Add Website", "Website name:")
        if not ok or not name:
            return
            
        # Get URL
        url, ok = QInputDialog.getText(self, "Add Website", "Website URL:")
        if not ok or not url:
            return
            
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        # Get icon path (for now, use a default)
        icon_path = ""  # Use existing icon file, keep full path
        
        # Create shortcut
        shortcut = {
            "name": name,
            "url": url,
            "icon": icon_path,
            "visible": True
        }
        
        # Add to list
        item_text = f"{name} - {url}"
        item = QListWidgetItem(item_text)
        item.setData(Qt.ItemDataRole.UserRole, shortcut)
        self.shortcuts_list.addItem(item)
    
    def _edit_shortcut(self):
        """Edit selected shortcut"""
        current_item = self.shortcuts_list.currentItem()
        if not current_item:
            return
            
        shortcut = current_item.data(Qt.ItemDataRole.UserRole)
        if not shortcut:
            return
            
        # Get new name
        name, ok = QInputDialog.getText(
            self, "Edit Website", "Website name:", 
            text=shortcut.get('name', '')
        )
        if not ok or not name:
            return
            
        # Get new URL
        url, ok = QInputDialog.getText(
            self, "Edit Website", "Website URL:", 
            text=shortcut.get('url', '')
        )
        if not ok or not url:
            return
            
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        # Update shortcut
        shortcut['name'] = name
        shortcut['url'] = url
        
        # Update list item display
        current_item.setText(f"{name} - {url}")
        current_item.setData(Qt.ItemDataRole.UserRole, shortcut)
    
    def _toggle_visibility(self):
        """Toggle visibility of selected shortcut"""
        current_item = self.shortcuts_list.currentItem()
        if not current_item:
            return
            
        shortcut = current_item.data(Qt.ItemDataRole.UserRole)
        if not shortcut:
            return
            
        # Toggle visibility
        current_visibility = shortcut.get('visible', True)
        shortcut['visible'] = not current_visibility
        
        # Update the item display
        visibility_status = " (hidden)" if not shortcut['visible'] else ""
        current_item.setText(f"{shortcut['name']} - {shortcut['url']}{visibility_status}")
        current_item.setData(Qt.ItemDataRole.UserRole, shortcut)
        
        # Update color
        if not shortcut['visible']:
            current_item.setForeground(Qt.GlobalColor.gray)
        else:
            current_item.setForeground(Qt.GlobalColor.black)
    
    def _remove_shortcut(self):
        """Remove selected shortcut"""
        current_item = self.shortcuts_list.currentItem()
        if current_item:
            row = self.shortcuts_list.row(current_item)
            self.shortcuts_list.takeItem(row)
    
    def _get_shortcuts_from_list(self):
        """Get all shortcuts from the list widget"""
        shortcuts = []
        for i in range(self.shortcuts_list.count()):
            item = self.shortcuts_list.item(i)
            shortcut = item.data(Qt.ItemDataRole.UserRole)
            if shortcut:
                shortcuts.append(shortcut)
        return shortcuts
    
    def _create_hotkey_tab(self):
        """Create general settings configuration tab"""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Create content widget
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # === Hotkey Settings ===
        hotkey_title = QLabel(t("hotkey_title"))
        hotkey_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(hotkey_title)
        
        # Hotkey group
        hotkey_group = QGroupBox()
        hotkey_group_layout = QVBoxLayout(hotkey_group)
        
        # Modifiers
        mod_label = QLabel(t("modifiers_label"))
        hotkey_group_layout.addWidget(mod_label)
        
        mod_layout = QHBoxLayout()
        self.ctrl_check = QCheckBox("Ctrl")
        self.shift_check = QCheckBox("Shift")
        self.alt_check = QCheckBox("Alt")
        self.win_check = QCheckBox("Win")
        
        mod_layout.addWidget(self.ctrl_check)
        mod_layout.addWidget(self.shift_check)
        mod_layout.addWidget(self.alt_check)
        mod_layout.addWidget(self.win_check)
        mod_layout.addStretch()
        hotkey_group_layout.addLayout(mod_layout)
        
        # Main key
        key_layout = QHBoxLayout()
        key_label = QLabel(t("main_key_label"))
        key_layout.addWidget(key_label)
        
        self.key_combo = NoScrollComboBox()
        self.key_combo.setFixedWidth(100)
        # Add A-Z
        for i in range(26):
            self.key_combo.addItem(chr(ord('A') + i))
        key_layout.addWidget(self.key_combo)
        key_layout.addStretch()
        hotkey_group_layout.addLayout(key_layout)
        
        layout.addWidget(hotkey_group)
        
        # Hotkey tips
        hotkey_tips_label = QLabel(t("hotkey_tips"))
        hotkey_tips_label.setWordWrap(True)
        hotkey_tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(hotkey_tips_label)
        
        # === Language Settings ===
        lang_title = QLabel(t("language_title"))
        lang_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        lang_title.setStyleSheet("margin-top: 20px;")
        layout.addWidget(lang_title)
        
        # Language group
        lang_group = QGroupBox()
        lang_group_layout = QVBoxLayout(lang_group)
        
        # Language selection
        lang_layout = QHBoxLayout()
        lang_label = QLabel(t("language_label"))
        lang_layout.addWidget(lang_label)
        
        self.language_combo = NoScrollComboBox()
        self.language_combo.setFixedWidth(200)
        
        # Populate language options
        from src.game_wiki_tooltip.core.i18n import get_supported_languages
        supported_languages = get_supported_languages()
        for lang_code, lang_name in supported_languages.items():
            self.language_combo.addItem(lang_name, lang_code)
        
        # Connect language change signal
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        
        lang_layout.addWidget(self.language_combo)
        lang_layout.addStretch()
        lang_group_layout.addLayout(lang_layout)
        
        # Language tips
        lang_tips_label = QLabel(t("language_tips"))
        lang_tips_label.setWordWrap(True)
        lang_tips_label.setStyleSheet("color: #666; margin-top: 5px;")
        lang_group_layout.addWidget(lang_tips_label)
        
        layout.addWidget(lang_group)
        
        # === Audio Settings ===
        audio_title = QLabel(t("audio_title"))
        audio_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        audio_title.setStyleSheet("margin-top: 20px;")
        layout.addWidget(audio_title)
        
        self.audio_group = QGroupBox()
        audio_group_layout = QVBoxLayout(self.audio_group)
        
        # Audio device selection
        audio_layout = QHBoxLayout()
        self.audio_label = QLabel(t("audio_input_device_label"))
        audio_layout.addWidget(self.audio_label)
        
        self.audio_device_combo = NoScrollComboBox()
        self.audio_device_combo.setFixedWidth(300)
        
        # Populate audio device options
        self._populate_audio_devices()
        
        audio_layout.addWidget(self.audio_device_combo)
        audio_layout.addStretch()
        audio_group_layout.addLayout(audio_layout)
        
        # Refresh devices button
        refresh_layout = QHBoxLayout()
        self.refresh_button = QPushButton(t("refresh_devices_button"))
        # Use a safe wrapper for the button click to prevent crashes
        self.refresh_button.clicked.connect(self._safe_refresh_audio_devices)
        self.refresh_button.setFixedWidth(120)
        refresh_layout.addWidget(self.refresh_button)
        refresh_layout.addStretch()
        audio_group_layout.addLayout(refresh_layout)
        
        # Auto voice on hotkey checkbox
        auto_voice_layout = QHBoxLayout()
        self.auto_voice_checkbox = QCheckBox(t("checkbox_auto_voice_hotkey"))
        self.auto_voice_checkbox.setToolTip(t("tooltip_auto_voice_hotkey"))
        auto_voice_layout.addWidget(self.auto_voice_checkbox)
        auto_voice_layout.addStretch()
        audio_group_layout.addLayout(auto_voice_layout)
        
        # Auto-send voice input checkbox
        auto_send_layout = QHBoxLayout()
        self.auto_send_checkbox = QCheckBox(t("checkbox_auto_send_voice"))
        self.auto_send_checkbox.setToolTip(t("tooltip_auto_send_voice"))
        auto_send_layout.addWidget(self.auto_send_checkbox)
        auto_send_layout.addStretch()
        audio_group_layout.addLayout(auto_send_layout)
        
        # Chinese voice model download section (only shown when language is Chinese)
        self.chinese_model_widget = self._create_chinese_model_section()
        audio_group_layout.addWidget(self.chinese_model_widget)
        self.chinese_model_widget.hide()  # Initially hidden
        
        layout.addWidget(self.audio_group)
        
        layout.addStretch()
        
        # Set content widget to scroll area
        scroll_area.setWidget(content_widget)
        
        # Add scroll area to tab
        self.tab_widget.addTab(scroll_area, t("tab_general_settings"))
        
    def _create_wiki_tab(self):
        """Create wiki URL configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 10)  # Reduced bottom margin
        layout.setSpacing(15)  # Reduced spacing between sections
        
        # Title
        title = QLabel(t("wiki_title"))
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Description with search box - compact layout
        desc_search_layout = QHBoxLayout()
        desc_search_layout.setSpacing(10)  # Reduced spacing
        
        # Description
        desc_label = QLabel(t("wiki_description"))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; font-size: 12px;")  # Slightly smaller font
        desc_search_layout.addWidget(desc_label, 1)
        
        # Search box
        search_label = QLabel(t("wiki_search_label"))
        search_label.setStyleSheet("font-size: 12px;")  # Consistent font size
        desc_search_layout.addWidget(search_label)
        
        self.wiki_search_input = QLineEdit()
        self.wiki_search_input.setPlaceholderText(t("wiki_search_placeholder"))
        self.wiki_search_input.setFixedWidth(200)
        self.wiki_search_input.textChanged.connect(self._filter_wiki_list)
        desc_search_layout.addWidget(self.wiki_search_input)
        
        layout.addLayout(desc_search_layout)
        
        # List + buttons in a horizontal layout
        list_buttons_layout = QHBoxLayout()
        list_buttons_layout.setSpacing(8)

        # Wiki URL list widget
        self.wiki_list = QListWidget()
        self.wiki_list.setMinimumHeight(120)
        self.wiki_list.setSizePolicy(self.wiki_list.sizePolicy().horizontalPolicy(),
                                   self.wiki_list.sizePolicy().Policy.Expanding)
        self.wiki_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)
        list_buttons_layout.addWidget(self.wiki_list, 1)

        # Buttons column on the right
        button_layout = QVBoxLayout()
        button_layout.setSpacing(6)

        self.add_wiki_button = QPushButton(t("btn_add"))
        self.add_wiki_button.clicked.connect(self._add_wiki_entry)
        button_layout.addWidget(self.add_wiki_button)

        self.edit_wiki_button = QPushButton(t("btn_edit"))
        self.edit_wiki_button.clicked.connect(self._edit_wiki_url)
        button_layout.addWidget(self.edit_wiki_button)

        self.remove_wiki_button = QPushButton(t("btn_remove"))
        self.remove_wiki_button.clicked.connect(self._remove_wiki_entry)
        button_layout.addWidget(self.remove_wiki_button)

        button_layout.addStretch()

        self.reset_wiki_button = QPushButton(t("wiki_reset_button"))
        self.reset_wiki_button.clicked.connect(self._reset_wiki_urls)
        button_layout.addWidget(self.reset_wiki_button)

        list_buttons_layout.addLayout(button_layout)
        layout.addLayout(list_buttons_layout, 1)
        
        # Tips with bold warning - reduced spacing
        tips_html = t("wiki_tips_with_warning")
        tips_label = QLabel(tips_html)
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 5px;")
        tips_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(tips_label)
        
        # Initialize search filter state
        self.wiki_search_filter = ""
        
        # Load wiki URLs for current language
        self._load_wiki_urls()
        
        self.tab_widget.addTab(tab, t("wiki_tab"))
        
    def _create_api_tab(self):
        """Create API configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel(t("api_title"))
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # API keys group
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(15)
        
        # Google API key
        google_layout = QVBoxLayout()
        google_label = QLabel(t("google_api_label"))
        google_layout.addWidget(google_label)
        
        self.google_api_input = QLineEdit()
        self.google_api_input.setPlaceholderText(t("google_api_placeholder"))
        self.google_api_input.setEchoMode(QLineEdit.EchoMode.Password)
        google_layout.addWidget(self.google_api_input)
        
        google_help = QLabel(f'<a href="https://makersuite.google.com/app/apikey">{t("google_api_help")}</a>')
        google_help.setOpenExternalLinks(True)
        google_help.setStyleSheet("color: #1668dc;")
        google_layout.addWidget(google_help)
        
        group_layout.addLayout(google_layout)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        group_layout.addWidget(separator)

        layout.addWidget(group)
        
        # Tips
        tips_label = QLabel(t("api_tips"))
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, t("api_tab"))
        
    def _on_language_changed(self):
        """Handle language selection change"""
        current_index = self.language_combo.currentIndex()
        if current_index >= 0:
            selected_language = self.language_combo.itemData(current_index)
            
            # Update translation manager
            from src.game_wiki_tooltip.core.i18n import set_language
            set_language(selected_language)
            
            # Update settings manager's language to track current language
            self.settings_manager.settings.language = selected_language
            
            # Update all UI text
            self._update_ui_text()
            
            # Reload wiki URLs for the new language
            self._load_wiki_urls()
            
            # Notify other windows about language change
            self.language_changed.emit()

            # Show/hide Chinese model download section
            if selected_language == 'zh':
                self.chinese_model_widget.show()
                self._check_chinese_model_status()
            else:
                self.chinese_model_widget.hide()
    
    def _update_ui_text(self):
        """Update all UI text with current language"""
        # Window title
        self.setWindowTitle(t("settings_title"))
        
        # Tab titles
        self.tab_widget.setTabText(0, t("tab_general_settings"))  # General Settings tab
        self.tab_widget.setTabText(1, t("tab_quick_access"))  # Shortcuts tab
        self.tab_widget.setTabText(2, t("wiki_tab"))
        self.tab_widget.setTabText(3, t("api_tab"))
        
        # Buttons
        self.apply_button.setText(t("apply_button"))
        self.cancel_button.setText(t("cancel_button"))
        
        # Hotkey tab (index 0)
        hotkey_tab = self.tab_widget.widget(0)
        hotkey_widgets = hotkey_tab.findChildren(QLabel)
        if len(hotkey_widgets) >= 3:
            hotkey_widgets[0].setText(t("hotkey_title"))      # Title
            hotkey_widgets[1].setText(t("modifiers_label"))   # Modifiers
            hotkey_widgets[2].setText(t("main_key_label"))    # Main key
            hotkey_widgets[3].setText(t("hotkey_tips"))       # Tips
        
        # API tab (index 3)
        api_tab = self.tab_widget.widget(3)
        api_widgets = api_tab.findChildren(QLabel)
        if len(api_widgets) >= 5:
            api_widgets[0].setText(t("api_title"))            # Title
            api_widgets[1].setText(t("google_api_label"))     # Google API
            api_widgets[2].setText(f'<a href="https://makersuite.google.com/app/apikey">{t("google_api_help")}</a>')
            api_widgets[5].setText(t("api_tips"))             # Tips
        
        # Audio Settings - Update all audio-related UI elements
        if hasattr(self, 'audio_group'):
            self.audio_group.setTitle(t("audio_title"))
        if hasattr(self, 'audio_label'):
            self.audio_label.setText(t("audio_input_device_label"))
        if hasattr(self, 'refresh_button'):
            self.refresh_button.setText(t("refresh_devices_button"))
        
        # Wiki tab - Update wiki-related UI elements
        if hasattr(self, 'wiki_search_input'):
            self.wiki_search_input.setPlaceholderText(t("wiki_search_placeholder"))
        if hasattr(self, 'add_wiki_button'):
            self.add_wiki_button.setText(t("btn_add"))
        if hasattr(self, 'edit_wiki_button'):
            self.edit_wiki_button.setText(t("btn_edit"))
        if hasattr(self, 'remove_wiki_button'):
            self.remove_wiki_button.setText(t("btn_remove"))
        if hasattr(self, 'reset_wiki_button'):
            self.reset_wiki_button.setText(t("wiki_reset_button"))
        
        # Update wiki tips label to show the restart reminder
        wiki_tab = self.tab_widget.widget(2)  # Wiki tab is at index 2
        if wiki_tab:
            wiki_labels = wiki_tab.findChildren(QLabel)
            for label in wiki_labels:
                # Find the tips label (it has RichText format)
                if label.textFormat() == Qt.TextFormat.RichText:
                    label.setText(t("wiki_tips_with_warning"))
                    break
        
        # Update placeholders
        self.google_api_input.setPlaceholderText(t("google_api_placeholder"))
        
    def _load_settings(self):
        """Load current settings"""
        settings = self.settings_manager.get()
        
        # Load language settings
        current_language = settings.get('language', 'en')
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == current_language:
                self.language_combo.setCurrentIndex(i)
                break
        
        # Check Chinese model status if language is Chinese
        if current_language == 'zh':
            self.chinese_model_widget.show()
            self._check_chinese_model_status()
        else:
            self.chinese_model_widget.hide()
        
        # Load audio device settings
        audio_device_index = settings.get('audio_device_index')
        if hasattr(self, 'audio_device_combo'):
            # Find and set the current audio device
            for i in range(self.audio_device_combo.count()):
                if self.audio_device_combo.itemData(i) == audio_device_index:
                    self.audio_device_combo.setCurrentIndex(i)
                    break
        
        # Load auto voice on hotkey setting
        auto_voice_on_hotkey = settings.get('auto_voice_on_hotkey', False)
        if hasattr(self, 'auto_voice_checkbox'):
            self.auto_voice_checkbox.setChecked(auto_voice_on_hotkey)
        
        # Load auto send voice input setting
        auto_send_voice_input = settings.get('auto_send_voice_input', False)
        if hasattr(self, 'auto_send_checkbox'):
            self.auto_send_checkbox.setChecked(auto_send_voice_input)
        
        # Load hotkey settings
        hotkey = settings.get('hotkey', {})
        modifiers = hotkey.get('modifiers', [])
        self.ctrl_check.setChecked('Ctrl' in modifiers)
        self.shift_check.setChecked('Shift' in modifiers)
        self.alt_check.setChecked('Alt' in modifiers)
        self.win_check.setChecked('Win' in modifiers)
        
        key = hotkey.get('key', 'X')
        index = self.key_combo.findText(key)
        if index >= 0:
            self.key_combo.setCurrentIndex(index)
            
        # Load API settings (check both settings.json and environment variables)
        api = settings.get('api', {})
        
        # Gemini API key: settings.json -> environment variables
        gemini_api_key = (
            api.get('gemini_api_key') or
            os.getenv('GEMINI_API_KEY') or
            os.getenv('GOOGLE_API_KEY') or 
            ''
        )
        self.google_api_input.setText(gemini_api_key)
        
        
    def _on_apply(self):
        """Apply settings"""
        # Get selected language
        selected_language = self.language_combo.itemData(self.language_combo.currentIndex())
        
        # Get selected audio device
        selected_audio_device = None
        if hasattr(self, 'audio_device_combo'):
            selected_audio_device = self.audio_device_combo.itemData(self.audio_device_combo.currentIndex())
        
        # Validate hotkey
        modifiers = []
        if self.ctrl_check.isChecked():
            modifiers.append('Ctrl')
        if self.shift_check.isChecked():
            modifiers.append('Shift')
        if self.alt_check.isChecked():
            modifiers.append('Alt')
        if self.win_check.isChecked():
            modifiers.append('Win')
            
        if not modifiers:
            QMessageBox.warning(self, t("warning"), t("validation_modifier_required"))
            return
            
        # Validate API keys (check both input and environment variables)
        gemini_api_key_input = self.google_api_input.text().strip()
        gemini_api_key_env = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        gemini_api_key = gemini_api_key_input or gemini_api_key_env
        
        # Check if both API keys are available
        missing_keys = []
        if not gemini_api_key:
            missing_keys.append("Gemini API Key")
        # Only need Gemini API key now
        
        if missing_keys:
            # Check if user previously chose "don't remind me again"
            current_settings = self.settings_manager.get()
            dont_remind = current_settings.get('dont_remind_api_missing', False)
            
            if not dont_remind:
                # Show friendly dialog
                dialog = ApiKeyMissingDialog(missing_keys, parent=self)
                dialog.exec()
                
                # Handle user's choice
                if dialog.dont_remind:
                    logger.info("User selected 'Don't remind me again' in settings")
                    self.settings_manager.update({'dont_remind_api_missing': True})
                
                if dialog.open_settings:
                    # User chose to configure API keys, directly switch to API configuration tab
                    logger.info("User chose to configure API keys, switching to API tab")
                    self.switch_to_api_tab()
                    return
                else:
                    # User chose to configure later, continue saving settings but show limited mode info
                    logger.info("User chose to continue without API keys")
                    # Continue with settings save logic
            else:
                # User previously chose "don't remind me again", silently continue
                logger.info("User previously chose 'Don't remind me again', proceeding without API key validation")
                # Continue with settings save logic
            
        # Update settings (only save what user explicitly entered)
        settings_update = {
            'language': selected_language,
            'hotkey': {
                'modifiers': modifiers,
                'key': self.key_combo.currentText()
            },
            'api': {
                'gemini_api_key': gemini_api_key_input,  # Only save user input
            },
            'shortcuts': self._get_shortcuts_from_list()  # Save shortcuts
        }
        
        # Add audio device setting if available
        if selected_audio_device is not None or hasattr(self, 'audio_device_combo'):
            settings_update['audio_device_index'] = selected_audio_device
        
        # Add auto voice on hotkey setting
        if hasattr(self, 'auto_voice_checkbox'):
            settings_update['auto_voice_on_hotkey'] = self.auto_voice_checkbox.isChecked()
        
        # Add auto send voice input setting
        if hasattr(self, 'auto_send_checkbox'):
            settings_update['auto_send_voice_input'] = self.auto_send_checkbox.isChecked()
        
        self.settings_manager.update(settings_update)
        
        # Save wiki URLs if modified
        if hasattr(self, 'wiki_urls_modified') and self.wiki_urls_modified:
            try:
                # Get current language
                current_language = self.settings_manager.settings.language
                
                # Save to language-specific file
                games_file = APPDATA_DIR / f"games_{current_language}.json"
                with open(games_file, 'w', encoding='utf-8') as f:
                    json.dump(self.games_config, f, indent=4, ensure_ascii=False)
                
                logger.info(f"Saved wiki URLs to {games_file}")
                self.wiki_urls_modified = False
            except Exception as e:
                logger.error(f"Failed to save wiki URLs: {e}")
                QMessageBox.warning(self, t("warning"), t("wiki_save_failed"))
        
        # Emit signal
        self.settings_applied.emit()
        
        # Show success message (different based on API key status)
        if missing_keys:
            success_msg = (
                f"Settings saved successfully!\n\n"
                f"⚠️ Running in limited mode (Wiki search only)\n"
                f"Missing API keys: {', '.join(missing_keys)}\n\n"
                f"Configure complete API keys to enable AI guide features."
            )
        else:
            success_msg = t("validation_settings_saved")
        
        QMessageBox.information(self, t("success"), success_msg)
        
        # Close window
        self.close()
        
    def _on_cancel(self):
        """Handle cancel button click with API key validation"""
        # Check current API key configuration
        gemini_api_key_input = self.google_api_input.text().strip()
        gemini_api_key_env = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        gemini_api_key = gemini_api_key_input or gemini_api_key_env

        # Check if both API keys are available
        missing_keys = []
        if not gemini_api_key:
            missing_keys.append("Gemini API Key")
        # Only need Gemini API key now
        
        if missing_keys:
            # Check if user previously chose "don't remind me again"
            current_settings = self.settings_manager.get()
            dont_remind = current_settings.get('dont_remind_api_missing', False)
            
            if not dont_remind:
                # Show the dialog
                dialog = ApiKeyMissingDialog(missing_keys, parent=self)
                dialog.exec()
                
                # Handle user's choice
                if dialog.dont_remind:
                    logger.info("User selected 'Don't remind me again' when canceling settings")
                    self.settings_manager.update({'dont_remind_api_missing': True})
                
                if dialog.open_settings:
                    # User chose to configure API keys, switch to API tab and don't close
                    logger.info("User chose to configure API keys from cancel dialog, switching to API tab")
                    self.switch_to_api_tab()
                    return  # Don't close the window
                else:
                    # User chose "Maybe Later", close the window
                    logger.info("User chose to close settings without configuring API keys")
                    self.close()
            else:
                # User previously chose "don't remind me again", close directly
                logger.info("User previously chose 'Don't remind me again', closing settings directly")
                self.close()
        else:
            # API keys are configured, close normally
            logger.info("API keys are configured, closing settings normally")
            self.close()
    
    # Wiki URL management methods
    def _load_wiki_urls(self):
        """Load wiki URLs for the current language"""
        try:
            # Get current language
            current_language = self.settings_manager.settings.language
            
            # Get the games config file path for current language
            games_file = APPDATA_DIR / f"games_{current_language}.json"
            if not games_file.exists():
                games_file = APPDATA_DIR / "games.json"
            
            # Load the games config
            if games_file.exists():
                with open(games_file, 'r', encoding='utf-8') as f:
                    self.games_config = json.load(f)
                
                # Clear and populate the list
                self.wiki_list.clear()
                self._populate_wiki_list()
            else:
                logger.warning(f"Games config file not found: {games_file}")
                self.games_config = {}
        except Exception as e:
            logger.error(f"Failed to load wiki URLs: {e}")
            self.games_config = {}
    
    def _populate_wiki_list(self):
        """Populate the wiki list with filtered items"""
        self.wiki_list.clear()
        filter_text = self.wiki_search_filter.lower() if hasattr(self, 'wiki_search_filter') else ""
        
        for game_name, config in sorted(self.games_config.items()):
            # Apply search filter
            if filter_text and filter_text not in game_name.lower():
                continue
                
            if isinstance(config, dict) and 'BaseUrl' in config:
                # Format: "Game Name - baseurl"
                item = QListWidgetItem(f"{game_name} - {config['BaseUrl']}")
                item.setData(Qt.ItemDataRole.UserRole, game_name)
                self.wiki_list.addItem(item)
    
    def _edit_wiki_url(self):
        """Edit the selected wiki URL"""
        current_item = self.wiki_list.currentItem()
        if not current_item:
            QMessageBox.information(self, t("info"), t("wiki_select_game"))
            return
        
        game_name = current_item.data(Qt.ItemDataRole.UserRole)
        current_config = self.games_config.get(game_name, {})
        current_url = current_config.get('BaseUrl', '')
        
        # Show input dialog
        new_url, ok = QInputDialog.getText(
            self, 
            t("wiki_edit_title"),
            t("wiki_edit_prompt").format(game=game_name),
            text=current_url
        )
        
        if ok and new_url and new_url != current_url:
            # Update the config
            if game_name not in self.games_config:
                self.games_config[game_name] = {}
            self.games_config[game_name]['BaseUrl'] = new_url
            
            # Update the list item display
            current_item.setText(f"{game_name} - {new_url}")
            
            # Mark as modified (will be saved when Apply is clicked)
            self.wiki_urls_modified = True
    
    def _reset_wiki_urls(self):
        """Reset wiki URLs to default values"""
        reply = QMessageBox.question(
            self,
            t("wiki_reset_confirm_title"),
            t("wiki_reset_confirm_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Get current language
                current_language = self.settings_manager.settings.language
                
                # Get the source file from assets
                source_file = package_file(f"games_{current_language}.json")
                if not source_file.exists():
                    source_file = package_file("games.json")
                
                # Copy the default file to appdata
                target_file = APPDATA_DIR / f"games_{current_language}.json"
                shutil.copyfile(source_file, target_file)
                
                # Reload the list
                self._load_wiki_urls()
                
                # Mark as modified
                self.wiki_urls_modified = True
                
                QMessageBox.information(self, t("success"), t("wiki_reset_success"))
            except Exception as e:
                logger.error(f"Failed to reset wiki URLs: {e}")
                QMessageBox.critical(self, t("error"), t("wiki_reset_failed"))
    
    def _add_wiki_entry(self):
        """Add a new wiki entry"""
        # Get game name
        game_name, ok = QInputDialog.getText(
            self,
            t("wiki_add_title"),
            t("wiki_add_game_prompt")
        )
        
        if not ok or not game_name:
            return
        
        # Check if game already exists
        if game_name in self.games_config:
            QMessageBox.warning(self, t("warning"), t("wiki_game_exists"))
            return
        
        # Get wiki URL
        wiki_url, ok = QInputDialog.getText(
            self,
            t("wiki_add_title"),
            t("wiki_add_url_prompt").format(game=game_name)
        )
        
        if ok and wiki_url:
            # Add to config
            self.games_config[game_name] = {
                "BaseUrl": wiki_url,
                "NeedsSearch": True
            }
            
            # Refresh the list
            self._populate_wiki_list()
            
            # Mark as modified
            self.wiki_urls_modified = True
    
    def _remove_wiki_entry(self):
        """Remove selected wiki entry"""
        current_item = self.wiki_list.currentItem()
        if not current_item:
            QMessageBox.information(self, t("info"), t("wiki_select_game_remove"))
            return
        
        game_name = current_item.data(Qt.ItemDataRole.UserRole)
        
        # Confirm removal
        reply = QMessageBox.question(
            self,
            t("wiki_remove_confirm_title"),
            t("wiki_remove_confirm_message").format(game=game_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from config
            if game_name in self.games_config:
                del self.games_config[game_name]
                
                # Refresh the list
                self._populate_wiki_list()
                
                # Mark as modified
                self.wiki_urls_modified = True
    
    def _filter_wiki_list(self, text):
        """Filter the wiki list based on search text"""
        self.wiki_search_filter = text
        self._populate_wiki_list() 