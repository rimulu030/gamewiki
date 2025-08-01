"""
PyQt6-based settings window with hotkey and API configuration.
"""

import logging
import os
import json
import shutil
from typing import Dict, Optional, Callable, List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QCheckBox, QComboBox, QLineEdit,
    QGridLayout, QFrame, QMessageBox, QGroupBox, QDialog,
    QListWidget, QListWidgetItem, QInputDialog, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from src.game_wiki_tooltip.core.config import SettingsManager
from src.game_wiki_tooltip.core.utils import package_file, APPDATA_DIR
from src.game_wiki_tooltip.core.i18n import init_translations, get_translation_manager, t

logger = logging.getLogger(__name__)


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
        title_label = QLabel("AI Features Unavailable")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #d32f2f;")
        layout.addWidget(title_label)
        
        # Message content
        message = (
            "AI guide features require both API keys to function properly:\n\n"
            f"Missing: {', '.join(self.missing_keys)}\n\n"
            "⚠️ Note: Gemini API alone cannot provide high-quality RAG functionality.\n"
            "Jina vector search is essential for complete AI guide features.\n\n"
            "You can still use Wiki search without API keys."
        )
        
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("font-size: 11px; line-height: 1.4;")
        layout.addWidget(message_label)
        
        # "Don't remind me again" checkbox
        self.dont_remind_checkbox = QCheckBox("Don't remind me again (Wiki search only)")
        self.dont_remind_checkbox.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.dont_remind_checkbox)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Configure button
        config_button = QPushButton("Configure API Keys")
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
        later_button = QPushButton("Maybe Later")
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
        self.setFixedSize(600, 500)
        
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
        
        # Create tabs - hotkey first, language last
        self._create_hotkey_tab()
        self._create_shortcuts_tab()  # Add shortcuts tab as second
        self._create_wiki_tab()  # Add wiki tab as third
        self._create_api_tab()
        self._create_language_tab()
        
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
        
    def _create_language_tab(self):
        """Create language configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel(t("language_title"))
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Language group
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        
        # Language selection
        lang_layout = QHBoxLayout()
        lang_label = QLabel(t("language_label"))
        lang_layout.addWidget(lang_label)
        
        self.language_combo = QComboBox()
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
        group_layout.addLayout(lang_layout)
        
        layout.addWidget(group)
        
        # Tips
        tips_label = QLabel(t("language_tips"))
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, t("language_tab"))
        
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
        title_label = QLabel("Manage Quick Access Websites")
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)
        
        # Explanation
        info_label = QLabel("Add or remove quick access buttons for your favorite websites.\n"
                           "These buttons will appear above the input field for easy access.")
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
        
        self.add_shortcut_btn = QPushButton("Add Website")
        self.add_shortcut_btn.clicked.connect(self._add_shortcut)
        button_layout.addWidget(self.add_shortcut_btn)
        
        self.edit_shortcut_btn = QPushButton("Edit Selected")
        self.edit_shortcut_btn.clicked.connect(self._edit_shortcut)
        button_layout.addWidget(self.edit_shortcut_btn)
        
        self.toggle_visibility_btn = QPushButton("Hide/Show Selected")
        self.toggle_visibility_btn.clicked.connect(self._toggle_visibility)
        button_layout.addWidget(self.toggle_visibility_btn)
        
        self.remove_shortcut_btn = QPushButton("Remove Selected")
        self.remove_shortcut_btn.clicked.connect(self._remove_shortcut)
        button_layout.addWidget(self.remove_shortcut_btn)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "Quick Access")
    
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
        """Create hotkey configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel(t("hotkey_title"))
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Hotkey group
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        
        # Modifiers
        mod_label = QLabel(t("modifiers_label"))
        group_layout.addWidget(mod_label)
        
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
        group_layout.addLayout(mod_layout)
        
        # Main key
        key_layout = QHBoxLayout()
        key_label = QLabel(t("main_key_label"))
        key_layout.addWidget(key_label)
        
        self.key_combo = QComboBox()
        self.key_combo.setFixedWidth(100)
        # Add A-Z
        for i in range(26):
            self.key_combo.addItem(chr(ord('A') + i))
        # Add F1-F12
        for i in range(1, 13):
            self.key_combo.addItem(f"F{i}")
        key_layout.addWidget(self.key_combo)
        key_layout.addStretch()
        group_layout.addLayout(key_layout)
        
        layout.addWidget(group)
        
        # Tips
        tips_label = QLabel(t("hotkey_tips"))
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, t("hotkey_tab"))
        
    def _create_wiki_tab(self):
        """Create wiki URL configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Title
        title = QLabel(t("wiki_title"))
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Description with search box
        desc_search_layout = QHBoxLayout()
        
        # Description
        desc_label = QLabel(t("wiki_description"))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666;")
        desc_search_layout.addWidget(desc_label, 1)
        
        # Search box
        search_label = QLabel(t("wiki_search_label"))
        desc_search_layout.addWidget(search_label)
        
        self.wiki_search_input = QLineEdit()
        self.wiki_search_input.setPlaceholderText(t("wiki_search_placeholder"))
        self.wiki_search_input.setFixedWidth(200)
        self.wiki_search_input.textChanged.connect(self._filter_wiki_list)
        desc_search_layout.addWidget(self.wiki_search_input)
        
        layout.addLayout(desc_search_layout)
        
        # Wiki URL list widget
        self.wiki_list = QListWidget()
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
        layout.addWidget(self.wiki_list)
        
        # Buttons layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Add button
        self.add_wiki_button = QPushButton("Add")
        self.add_wiki_button.clicked.connect(self._add_wiki_entry)
        button_layout.addWidget(self.add_wiki_button)
        
        # Edit button
        self.edit_wiki_button = QPushButton("Edit")
        self.edit_wiki_button.clicked.connect(self._edit_wiki_url)
        button_layout.addWidget(self.edit_wiki_button)
        
        # Remove button
        self.remove_wiki_button = QPushButton("Remove")
        self.remove_wiki_button.clicked.connect(self._remove_wiki_entry)
        button_layout.addWidget(self.remove_wiki_button)
        
        # Reset button
        self.reset_wiki_button = QPushButton(t("wiki_reset_button"))
        self.reset_wiki_button.clicked.connect(self._reset_wiki_urls)
        button_layout.addWidget(self.reset_wiki_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Tips with bold warning
        tips_html = t("wiki_tips_with_warning")
        tips_label = QLabel(tips_html)
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; font-size: 11px;")
        tips_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
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
        
        # Jina API no longer needed - using Gemini for embeddings
        
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
            
            # Update all UI text
            self._update_ui_text()
    
    def _update_ui_text(self):
        """Update all UI text with current language"""
        # Window title
        self.setWindowTitle(t("settings_title"))
        
        # Tab titles
        self.tab_widget.setTabText(0, t("hotkey_tab"))
        self.tab_widget.setTabText(1, "Quick Access")  # Shortcuts tab
        self.tab_widget.setTabText(2, t("wiki_tab"))
        self.tab_widget.setTabText(3, t("api_tab"))
        self.tab_widget.setTabText(4, t("language_tab"))
        
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
            api_widgets[3].setText(t("jina_api_label"))       # Jina API
            api_widgets[4].setText(f'<a href="https://jina.ai/">{t("jina_api_help")}</a>')
            api_widgets[5].setText(t("api_tips"))             # Tips
        
        # Language tab (index 4)
        language_tab = self.tab_widget.widget(4)
        language_widgets = language_tab.findChildren(QLabel)
        if len(language_widgets) >= 2:
            language_widgets[0].setText(t("language_title"))  # Title
            language_widgets[1].setText(t("language_label"))  # Language label
            language_widgets[2].setText(t("language_tips"))   # Tips
        
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
        
        # Jina API key no longer needed
        
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
        self.settings_manager.update({
            'language': selected_language,
            'hotkey': {
                'modifiers': modifiers,
                'key': self.key_combo.currentText()
            },
            'api': {
                'gemini_api_key': gemini_api_key_input,  # Only save user input
                # jina_api_key removed
            },
            'shortcuts': self._get_shortcuts_from_list()  # Save shortcuts
        })
        
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
        
        # Jina API key no longer needed
        
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