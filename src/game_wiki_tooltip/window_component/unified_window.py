"""
Unified window system for GameWikiTooltip.
Provides mini assistant and expandable chat window functionality.
"""

import sys
import logging
import time
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)

from src.game_wiki_tooltip.core.i18n import t
from src.game_wiki_tooltip.core.config import WindowGeometryConfig

from src.game_wiki_tooltip.window_component import (
    WikiView,
    load_svg_icon,
    MessageType,
    WindowState,
    QuickAccessPopup,
    ExpandableIconButton,
    ChatView,
    VoiceRecognitionThread,
    is_voice_recognition_available,
)

try:
    from PyQt6.QtCore import (
        Qt, QTimer, QPropertyAnimation, QRect, QSize, QPoint,
        QEasingCurve, QParallelAnimationGroup, pyqtSignal, QUrl,
        QThread, pyqtSlot
    )
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QFrame, QStackedWidget,
        QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QLineEdit,
        QToolButton, QMenu
    )
    from PyQt6.QtGui import (
        QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
        QPalette, QIcon, QPixmap, QPainterPath, QTextDocument, QCursor
    )
    # Only WebView2 is supported
except ImportError:
    print("Error: PyQt6 is required.")
    sys.exit(1)

# Try to import BlurWindow
try:
    from BlurWindow.blurWindow import GlobalBlur
    BLUR_WINDOW_AVAILABLE = True
    logger.debug("BlurWindow module loaded successfully")
except ImportError:
    print("Warning: BlurWindow module not found, will use default transparency effect")
    BLUR_WINDOW_AVAILABLE = False

# Import graphics compatibility for Windows version detection
from src.game_wiki_tooltip.core.graphics_compatibility import WindowsGraphicsCompatibility

class UnifiedAssistantWindow(QMainWindow):
    """Main unified window with all modes"""
    
    query_submitted = pyqtSignal(str, str)  # query, mode
    window_closing = pyqtSignal()  # Signal when window is closing
    wiki_page_found = pyqtSignal(str, str)  # New signal: pass real wiki page information to controller
    visibility_changed = pyqtSignal(bool)  # Signal for visibility state changes
    stop_generation_requested = pyqtSignal()  # New signal: stop generation request
    settings_requested = pyqtSignal()  # Signal to request settings window from main app

    def __init__(self, settings_manager=None):
        super().__init__()
        
        # Set frameless window flags and transparency
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)  # Enable tooltips without focus
        
        # Create quick access popup
        self.quick_access_popup = QuickAccessPopup()
        
        # Window properties for drag and resize
        self.dragging = False
        self.resizing = False
        self.resize_edge = None
        self.drag_position = QPoint()
        self.resize_start_pos = QPoint()
        self.resize_start_geometry = QRect()
        
        # Enable mouse tracking for resize
        self.setMouseTracking(True)
        
        # Keep all existing properties
        self.settings_manager = settings_manager
        self.current_mode = "auto"
        self.is_generating = False
        self.streaming_widget = None
        self.current_game_window = None  # Record current game window title
        
        # Window state management
        self.current_state = WindowState.FULL_CONTENT  # Default state
        self.has_user_input = False  # Track if user has entered any input
        self.has_switched_state = False  # Track if user has manually switched window states
        
        # Store geometry for different states
        self._pending_geometry_save = False  # Flag to track if geometry needs saving
        self._is_precreating = False  # Flag to indicate if window is in precreation mode
        
        # Voice recognition
        self.voice_thread = None
        self.is_voice_recording = False
        self._cleanup_in_progress = False  # Flag to prevent multiple cleanup operations
        self.original_placeholder = ""
        self._voice_completed_text = ""  # Store completed sentences
        self._voice_current_sentence = ""  # Track current partial sentence
        
        # Recording cooldown timer to prevent rapid clicks
        self._recording_cooldown = QTimer()
        self._recording_cooldown.setSingleShot(True)
        self._recording_cooldown_active = False
        self._cached_chat_only_size = None  # Cache for chat_only size to avoid recalculation
        
        # Default WebView size (landscape orientation) - defer calculation to avoid GUI initialization issues
        self._default_webview_size = None  # Will be calculated when needed
        
        # Geometry save timer for delayed saving on move/resize
        self._geometry_save_timer = QTimer()
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.timeout.connect(self.save_geometry)
        
        # History manager will be initialized lazily
        self.history_manager = None
        
        self.init_ui()
        
        # Apply BlurWindow effect
        self.apply_blur_effect()
        
        self.restore_geometry()
        
        # Debug: log size after initialization
        logger.debug(f"UnifiedAssistantWindow initialized, size: {self.size()}")

    def apply_blur_effect(self):
        """Apply BlurWindow transparency effect"""
        if BLUR_WINDOW_AVAILABLE:
            try:
                # Use the proper Windows version detection from graphics_compatibility
                graphics_compat = WindowsGraphicsCompatibility()
                windows_version = graphics_compat._get_windows_version()
                print(f"Detected system version: {windows_version}")
                
                # Set window rounded corners
                self.set_window_rounded_corners()
                
                # Always use Win10 Aero effect
                GlobalBlur(
                    int(self.winId()), 
                    Acrylic=False,   # Win10 Aero effect
                    Dark=False,      # Light theme
                    QWidget=self
                )
                logger.debug("Win10 Aero effect applied")
                    
            except Exception as e:
                logger.debug(f"BlurWindow application failed: {e}")
                logger.debug("Will use default transparency effect")
        else:
            logger.debug("BlurWindow not available, using default transparency effect")
            
    def set_window_rounded_corners(self):
        """Set window rounded corners"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Windows API constants
            DWM_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            
            # Get window handle
            hwnd = int(self.winId())
            
            # Call DwmSetWindowAttribute to set rounded corners
            dwmapi = ctypes.windll.dwmapi
            corner_preference = wintypes.DWORD(DWMWCP_ROUND)
            result = dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWM_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(corner_preference),
                ctypes.sizeof(corner_preference)
            )
            
            if result == 0:
                logger.debug("Window rounded corners set successfully")
            else:
                print(f"⚠️ Window rounded corners setting failed: {result}")
                
        except Exception as e:
            logger.debug(f"Failed to set window rounded corners: {e}")
        
    def _ensure_history_manager(self):
        """Ensure history manager is initialized"""
        if self.history_manager is None:
            from src.game_wiki_tooltip.window_component.history_manager import WebHistoryManager
            self.history_manager = WebHistoryManager()
            logger.debug("History manager initialized")
        
    def init_ui(self):
        """Initialize the main window UI"""
        self.setWindowTitle("GameWiki Assistant")
        
        # Ensure the window can be freely resized, remove any size restrictions
        self.setMinimumSize(300, 200)  # Set a reasonable Minimum size
        self.setMaximumSize(16777215, 16777215)  # Remove Maximum size restrictions
        
        # Create central widget
        central_widget = QWidget()
        central_widget.setMouseTracking(True)
        self.setCentralWidget(central_widget)
        
        # Create main container frame (consistent with BlurWindow layer size)
        main_container = QFrame()
        main_container.setObjectName("mainContainer")
        main_container.setMouseTracking(True)
        
        # Save main_container reference for later adjustments
        self.main_container = main_container
        
        # Central widget layout (only contains main container)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(main_container)
        
        # Main container layout
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create custom title bar
        self.title_bar = self.create_title_bar()
        main_layout.addWidget(self.title_bar)
        
        # Content area (chat/wiki switcher)
        self.content_stack = QStackedWidget()
        # Ensure QStackedWidget does not force size changes
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Chat view
        self.chat_view = ChatView()
        self.chat_view.wiki_requested.connect(self.show_wiki_page)
        # Ensure the chat view maintains its size
        self.chat_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Wiki view
        self.wiki_view = WikiView()
        self.wiki_view.back_requested.connect(self.show_chat_view)  # This will restore input/shortcuts
        self.wiki_view.wiki_page_loaded.connect(self.handle_wiki_page_loaded)
        self.wiki_view.close_requested.connect(self._handle_wiki_close)  # Connect close button to pause and hide
        # Ensure WikiView has a reasonable Minimum size but does not force a fixed size
        self.wiki_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        self.content_stack.addWidget(self.chat_view)
        self.content_stack.addWidget(self.wiki_view)
        
        # Shortcuts container (above input area)
        self.shortcut_container = QFrame()
        self.shortcut_container.setObjectName("shortcutContainer")
        self.shortcut_container.setFixedHeight(35)
        
        self.shortcut_layout = QHBoxLayout(self.shortcut_container)
        self.shortcut_layout.setContentsMargins(10, 4, 10, 4)
        self.shortcut_layout.setSpacing(8)
        
        # Don't load shortcuts immediately - defer to after window is shown
        self.shortcuts_loaded = False
        
        # Input area - create integrated search bar following frameless_blur_window design
        self.input_container = QFrame()
        self.input_container.setObjectName("inputContainer")
        self.input_container.setFixedHeight(115)  # Adjusted height for two-row design
        
        input_layout = QVBoxLayout(self.input_container)
        input_layout.setContentsMargins(20, 10, 20, 10)
        input_layout.setSpacing(10)

        # Integrated search container (two rows)
        search_container = QFrame()
        search_container.setObjectName("searchContainer")
        search_container.setFixedHeight(90)
        
        # Search container internal layout
        container_layout = QVBoxLayout(search_container)
        container_layout.setContentsMargins(12, 8, 12, 8)
        container_layout.setSpacing(6)
        
        # Top row: Search input only
        search_input_row = QFrame()
        search_input_row.setObjectName("searchInputRow")
        
        input_row_layout = QHBoxLayout(search_input_row)
        input_row_layout.setContentsMargins(0, 0, 0, 0)
        input_row_layout.setSpacing(8)
        
        # Search input field
        self.input_field = QLineEdit()
        self.input_field.setObjectName("searchInput")
        # Set placeholder text with recommended query examples
        placeholder_texts = [
            t("placeholder_search"),
        ]
        self.input_field.setPlaceholderText(" | ".join(placeholder_texts[:3]))  # Show first 3 examples
        self.input_field.returnPressed.connect(self.on_input_return_pressed)
        
        # Add focus event to stop voice recording when clicking input field
        self.input_field.focusInEvent = self._handle_input_focus
        
        input_row_layout.addWidget(self.input_field)
        
        # Bottom row: Quick access buttons
        quick_access_row = QFrame()
        quick_access_row.setObjectName("quickAccessRow")
        
        access_layout = QHBoxLayout(quick_access_row)
        access_layout.setContentsMargins(0, 0, 0, 0)
        access_layout.setSpacing(0)
        
        # History button
        self.history_button = QPushButton()
        self.history_button.setObjectName("historyBtn")
        self.history_button.setFixedSize(32, 32)
        self.history_button.setToolTip(t("tooltip_history"))
        self.history_button.clicked.connect(self.show_history_menu)
        
        # Load history icon
        import pathlib
        base_path = pathlib.Path(__file__).parent.parent.parent.parent  # Go up to project root
        history_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "refresh-ccw-clock-svgrepo-com.svg")
        history_icon = load_svg_icon(history_icon_path, color="#111111", size=20)
        self.history_button.setIcon(history_icon)
        self.history_button.setIconSize(QSize(20, 20))
        
        # Quick Access button (replaces external website button)
        self.quick_access_button = QPushButton()
        self.quick_access_button.setObjectName("externalBtn")
        self.quick_access_button.setFixedSize(32, 32)
        self.quick_access_button.setToolTip(t("tooltip_quick_access"))
        # Connect click handler
        self.quick_access_button.clicked.connect(self.on_quick_access_clicked)
        
        # Load quick access icon
        external_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "globe-alt-1-svgrepo-com.svg")
        external_icon = load_svg_icon(external_icon_path, color="#111111", size=20)
        self.quick_access_button.setIcon(external_icon)
        self.quick_access_button.setIconSize(QSize(20, 20))
        
        # Search mode button
        self.mode_button = QPushButton()
        self.mode_button.setObjectName("searchBtn")
        self.mode_button.setFixedSize(32, 32)
        self.mode_button.setToolTip(t("tooltip_search_mode"))
        self.mode_button.clicked.connect(self.show_mode_menu)
        
        # Load search icon
        search_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "search-alt-1-svgrepo-com.svg")
        search_icon = load_svg_icon(search_icon_path, color="#111111", size=20)
        self.mode_button.setIcon(search_icon)
        self.mode_button.setIconSize(QSize(20, 20))
        
        # Voice input button
        self.voice_button = QPushButton()
        self.voice_button.setObjectName("voiceBtn")
        self.voice_button.setFixedSize(32, 32)
        self.voice_button.setToolTip(t("tooltip_voice_input"))
        self.voice_button.clicked.connect(self.toggle_voice_input)
        
        # Load microphone icon
        mic_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "microphone-alt-1-svgrepo-com.svg")
        mic_icon = load_svg_icon(mic_icon_path, color="#111111", size=18)
        self.voice_button.setIcon(mic_icon)
        self.voice_button.setIconSize(QSize(18, 18))
        
        # Disable voice button if voice recognition not available
        if not is_voice_recognition_available():
            self.voice_button.setEnabled(False)
            self.voice_button.setToolTip(t("tooltip_voice_unavailable"))
        
        # Send button
        self.send_button = QPushButton()
        self.send_button.setObjectName("sendBtn")
        self.send_button.setFixedSize(32, 32)
        self.send_button.clicked.connect(self.on_send_clicked)
        
        # Load send icon
        send_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "arrow-circle-up-svgrepo-com.svg")
        send_icon = load_svg_icon(send_icon_path, color="#111111", size=20)
        self.send_button.setIcon(send_icon)
        self.send_button.setIconSize(QSize(20, 20))
        
        # Add buttons to bottom row
        access_layout.addWidget(self.history_button)
        access_layout.addWidget(self.quick_access_button)
        access_layout.addWidget(self.mode_button)
        
        # Single task flow button (will change based on current game)
        self.task_flow_button = QPushButton()
        self.task_flow_button.setObjectName("taskFlowBtn")
        # Dynamic sizing based on content
        self.task_flow_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.task_flow_button.setMinimumHeight(32)
        self.task_flow_button.setToolTip(t("task_flow"))
        self.task_flow_button.hide()  # Initially hidden
        
        access_layout.addWidget(self.task_flow_button)
        
        # Initialize current task flow game
        self.current_task_flow_game = None
        
        access_layout.addStretch()  # Space in middle
        access_layout.addWidget(self.voice_button)
        access_layout.addWidget(self.send_button)
        
        # Add rows to search container
        container_layout.addWidget(search_input_row)
        container_layout.addWidget(quick_access_row)
        
        # Add search container to input container
        input_layout.addWidget(search_container)
        
        # Current mode
        self.current_mode = "auto"
        
        # Add to main layout with stretch factor
        main_layout.addWidget(self.content_stack, 1)  # Stretch factor 1, occupy all available space
        # Removed shortcut_container - shortcuts now in popup
        main_layout.addWidget(self.input_container, 0)     # Stretch factor 0, keep fixed height
        
        # Apply transparent styles
        self.setup_transparent_styles()
        
        # Enable mouse tracking for all children
        self.enable_mouse_tracking_for_children()
    
    def create_title_bar(self):
        """Create custom title bar"""
        title_bar = QFrame()
        title_bar.setFixedHeight(40)
        title_bar.setObjectName("titleBar")
        title_bar.setMouseTracking(True)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Title
        self.title_label = QLabel("GameWiki Assistant")
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # Settings button
        self.settings_btn = QPushButton()
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setFixedSize(30, 25)
        self.settings_btn.setToolTip(t("tooltip_settings"))
        self.settings_btn.clicked.connect(self.open_settings)
        
        # Load settings icon
        import pathlib
        base_path = pathlib.Path(__file__).parent.parent
        settings_icon_path = str(base_path / "assets" / "icons" / "setting-svgrepo-com.svg")
        settings_icon = load_svg_icon(settings_icon_path, color="#111111", size=16)
        self.settings_btn.setIcon(settings_icon)
        self.settings_btn.setIconSize(QSize(16, 16))
        
        layout.addWidget(self.settings_btn)
        
        # Close button
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(30, 25)
        close_btn.clicked.connect(self.close)
        
        layout.addWidget(close_btn)
        
        return title_bar
    
    def enable_mouse_tracking_for_children(self):
        """Enable mouse tracking for all child widgets recursively"""
        def enable_tracking(widget):
            widget.setMouseTracking(True)
            for child in widget.findChildren(QWidget):
                enable_tracking(child)
        
        enable_tracking(self)
        
    def reset_size_constraints(self):
        """Reset window size constraints, ensure free resizing"""
        self.setMinimumSize(300, 200)  # Keep reasonable Minimum size
        self.setMaximumSize(16777215, 16777215)  # Remove Maximum size restrictions
        
    def setup_transparent_styles(self):
        """Set up styles with blur effect"""
        style_sheet = """
        QMainWindow {
            background: transparent;
        }
        
        /* Global menu styling for consistent appearance */
        QMenu {
            background-color: white;
            border: 1px solid #d0d0d0;
            border-radius: 0px;
            padding: 5px;
        }
        
        QMenu::item {
            padding: 5px 20px;
            background-color: transparent;
            border-radius: 4px;
        }
        
        QMenu::item:selected {
            background-color: #f0f0f0;
        }
        
        QMenu::separator {
            height: 1px;
            background-color: #e0e0e0;
            margin: 5px 10px;
        }
        
        #mainContainer {
            background: rgba(255, 255, 255, 115);
            border-radius: 10px;  /* Remove rounded corners from main container */
            border: none;
        }
        
        #titleBar {
            background: rgba(255, 255, 255, 115);
            border-top-left-radius: 0px;  /* Remove rounded corners */
            border-top-right-radius: 0px;  /* Remove rounded corners */
        }
        
        #titleLabel {
            color: #111111;
            font-size: 14px;
            font-weight: bold;
            font-family: "Segoe UI", "Microsoft YaHei", Arial;
        }
        
        #minBtn, #closeBtn, #settingsBtn {
            background: rgba(255, 255, 255, 150);
            border: none;
            border-radius: 5px;
            color: #111111;
            font-weight: bold;
            font-family: "Segoe UI", "Microsoft YaHei", Arial;
        }
        
        #minBtn:hover, #closeBtn:hover, #settingsBtn:hover {
            background: rgba(220, 220, 220, 180);
        }
        
        #closeBtn:hover {
            background: rgba(220, 60, 60, 180);
            color: white;
        }
        
        /* Shortcut container - hidden by default */
        #shortcutContainer {
            background: rgba(255, 255, 255, 115);
        }
        
        /* Input container - updated background */
        #inputContainer {
            background: rgba(255, 255, 255, 115);
            border-bottom-left-radius: 0px;  /* Remove rounded corners */
            border-bottom-right-radius: 0px;  /* Remove rounded corners */
        }
        
        /* Search container - integrated two-row design */
        #searchContainer {
            background: rgba(0, 0, 0, 10);
            border: 1px solid rgba(200, 200, 200, 150);
            border-radius: 10px;  
        }
        
        #searchInputRow, #quickAccessRow {
            background: transparent;
            border: none;
        }
        
        /* Search input field */
        #searchInput {
            background: transparent;
            border: none;
            color: #111111;
            font-size: 14px;
            font-family: "Segoe UI", "Microsoft YaHei", Arial;
            padding: 0 5px;
        }
        
        #searchInput:focus {
            background: transparent;
            border: none;
            outline: none;
        }
        
        /* Button styles for the bottom row */
        #historyBtn, #externalBtn, #searchBtn, #voiceBtn, #sendBtn {
            background: transparent;
            border: none;
            color: #111111;
            font-size: 12px;
            font-weight: normal;
        }
        
        /* Task flow button with dynamic sizing */
        #taskFlowBtn {
            background: transparent;
            border: none;
            color: #111111;
            font-size: 12px;
            font-weight: normal;
            padding: 6px 12px;
            min-width: auto;
        }
        
        #historyBtn:hover, #externalBtn:hover, #searchBtn:hover, #taskFlowBtn:hover {
            background: rgba(220, 220, 220, 120);
            border-radius: 4px;
        }
        
        #sendBtn:hover {
            background: rgba(220, 220, 220, 120);
            border-radius: 4px;
        }
        
        /* Send button special states */
        #sendBtn[stop_mode="true"] {
            background-color: rgba(204, 102, 104, 180);
            border-radius: 4px;
        }
        
        #sendBtn[stop_mode="true"]:hover {
            background-color: rgba(220, 128, 130, 180);
        }
        
        /* Chat view styles - updated background */
        ChatView {
            background: rgba(255, 255, 255, 115);
            border: none;
            border-radius: 0px;  /* Remove rounded corners from chat content */
        }
        
        /* Chat container widget */
        ChatView QWidget {
            background: transparent;
        }
        
        /* Chat scrollbar */
        ChatView QScrollBar:vertical {
            background: rgba(240, 240, 240, 150);
            width: 12px;
            border-radius: 6px;
        }
        
        ChatView QScrollBar::handle:vertical {
            background: rgba(180, 180, 180, 200);
            border-radius: 6px;
            min-height: 20px;
        }
        
        ChatView QScrollBar::handle:vertical:hover {
            background: rgba(150, 150, 150, 220);
        }
        
        MessageWidget {
            background: transparent;
        }
        
        /* Message bubble enhanced styles */
        QFrame#messageBubble {
            border-radius: 18px;
            padding: 4px;
        }
        
        /* Welcome message styles */
        QLabel[messageType="welcome"] {
            background: rgba(255, 255, 255, 180);
            border: 1px solid rgba(224, 224, 224, 120);
            border-radius: 12px;
            padding: 15px;
            color: #666;
            font-size: 14px;
        }
        
        /* Status message styles */
        QFrame#statusBubble {
            background-color: rgba(240, 248, 255, 200);
            border: 1px solid rgba(224, 232, 240, 150);
            border-radius: 18px;
            padding: 4px;
        }
        """
        self.setStyleSheet(style_sheet)
        
    def _get_chat_only_size(self):
        """Calculate chat_only size from settings percentages (with caching)"""
        # Return cached size if available
        if self._cached_chat_only_size is not None:
            return self._cached_chat_only_size
            
        try:
            screen = QApplication.primaryScreen()
            if not screen:
                self._cached_chat_only_size = QSize(380, 115)  # Fallback size
                return self._cached_chat_only_size
                
            available_rect = screen.availableGeometry()
            screen_width = available_rect.width()
            screen_height = available_rect.height()
            
            # Get geometry config from settings
            try:
                window_geom = self.settings_manager.settings.window_geometry
                chat_only_geom = window_geom.chat_only
            except AttributeError:
                # Fallback to default percentages
                self._cached_chat_only_size = QSize(int(screen_width * 0.22), int(screen_height * 0.108))
                return self._cached_chat_only_size
            
            width = int(screen_width * chat_only_geom.width_percent)
            height = int(screen_height * chat_only_geom.height_percent)
            
            # Ensure reasonable minimum size
            width = max(300, width)
            height = max(100, height)
            
            self._cached_chat_only_size = QSize(width, height)
            logging.info(f"Calculated and cached chat_only size: {width}x{height}")
            return self._cached_chat_only_size
            
        except Exception as e:
            logging.error(f"Failed to calculate chat_only size: {e}")
            self._cached_chat_only_size = QSize(380, 115)  # Fallback size
            return self._cached_chat_only_size
        
    def restore_geometry(self):
        """Restore window geometry from settings based on current window state"""
        if not self.settings_manager:
            self._apply_safe_default_geometry()
            return
            
        try:
            # Get current screen information
            screen = QApplication.primaryScreen()
            if not screen:
                self._apply_safe_default_geometry()
                return
                
            available_rect = screen.availableGeometry()
            screen_width = available_rect.width()
            screen_height = available_rect.height()
            screen_x = available_rect.x()
            screen_y = available_rect.y()
            print('test', screen_x, screen_y, screen_width, screen_height)
            # Get geometry config based on current state
            try:
                window_geom = self.settings_manager.settings.window_geometry
            except AttributeError:
                # If window_geometry doesn't exist, create default
                window_geom = WindowGeometryConfig()
                logging.warning("window_geometry not found in settings, using defaults")
            
            if self.current_state == WindowState.CHAT_ONLY:
                # Chat only uses position only (size is fixed)
                geom = window_geom.chat_only
                x = int(screen_x + screen_width * geom.left_percent)
                y = int(screen_y + screen_height * geom.top_percent)

                # Calculate size from settings percentages
                width = int(screen_width * geom.width_percent)
                height = int(screen_height * geom.height_percent)
                
                self.setGeometry(x, y, width, height)
                logging.info(f"Restored chat_only position: {x}, {y} (fixed size: {width}x{height})")
                
            elif self.current_state == WindowState.FULL_CONTENT:
                # Full content only uses size, position determined by search box
                geom = window_geom.full_content
                width = int(screen_width * geom.width_percent)
                height = int(screen_height * geom.height_percent)
                
                # Ensure minimum size
                width = max(400, min(width, 1200))
                height = max(300, min(height, 900))
                
                self.resize(width, height)
                
            elif self.current_state == WindowState.WEBVIEW:
                # WebView only uses size, position determined by search box
                geom = window_geom.webview
                width = int(screen_width * geom.width_percent)
                height = int(screen_height * geom.height_percent)
                
                # Ensure minimum size
                width = max(600, min(width, 1600))
                height = max(400, min(height, 1200))
                
                self.resize(width, height)
                
        except Exception as e:
            logging.error(f"Failed to restore window geometry: {e}")
            self._apply_safe_default_geometry()

    def _apply_safe_default_geometry(self):
        """Apply safe default geometry configuration"""
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            # Use the safe position on the right side of the screen
            safe_width = min(600, screen.width() - 100)
            safe_height = min(500, screen.height() - 100)
            safe_x = screen.x() + (screen.width() - safe_width) // 2 + 50
            safe_y = screen.y() + (screen.height() - safe_height) // 4
            
            self.setGeometry(safe_x, safe_y, safe_width, safe_height)
            logging.info(f"Apply safe default geometry: ({safe_x},{safe_y},{safe_width},{safe_height})")
        except Exception as e:
            # Last fallback solution
            logging.error(f"Apply safe default geometry failed: {e}")
            self.setGeometry(100, 100, 600, 500)
        
        self.reset_size_constraints()

    def save_geometry(self):
        """Save current window geometry to settings based on window state"""
        if not self.settings_manager:
            return
            
        # Skip geometry saving during precreation to avoid overwriting default settings
        if getattr(self, '_is_precreating'):
            logging.debug("Skipping geometry save during precreation")
            return
            
        try:
            geo = self.geometry()
            screen = QApplication.primaryScreen().availableGeometry()
            screen_width = screen.width()
            screen_height = screen.height()
            screen_x = screen.x()
            screen_y = screen.y()
            
            # Calculate relative values
            left_percent = (geo.x() - screen_x) / screen_width if screen_width > 0 else 0.5
            top_percent = (geo.y() - screen_y) / screen_height if screen_height > 0 else 0.1
            width_percent = geo.width() / screen_width if screen_width > 0 else 0.3
            height_percent = geo.height() / screen_height if screen_height > 0 else 0.5
            
            # Ensure values are in reasonable range
            left_percent = max(0.0, min(1.0, left_percent))
            top_percent = max(0.0, min(1.0, top_percent))
            width_percent = max(0.1, min(0.9, width_percent))
            height_percent = max(0.1, min(0.9, height_percent))
            
            # Get current window_geometry from settings or create default
            try:
                current_window_geometry = self.settings_manager.settings.window_geometry
            except AttributeError:
                current_window_geometry = WindowGeometryConfig()
                logging.warning("window_geometry not found in settings during save, using defaults")
            
            # Update geometry based on current state
            update_data = {'window_geometry': {}}
            
            if self.current_state == WindowState.CHAT_ONLY:
                # Chat only saves only position, not size (size is fixed)
                update_data['window_geometry']['chat_only'] = {
                    'left_percent': left_percent,
                    'top_percent': top_percent
                    # Size is fixed, no need to save width_percent and height_percent
                }
            elif self.current_state == WindowState.FULL_CONTENT:
                # Full content only saves size
                update_data['window_geometry']['full_content'] = {
                    'width_percent': width_percent,
                    'height_percent': height_percent
                }
            elif self.current_state == WindowState.WEBVIEW:
                # WebView only saves size
                update_data['window_geometry']['webview'] = {
                    'width_percent': width_percent,
                    'height_percent': height_percent
                }
            
            # For FULL_CONTENT and WEBVIEW, also update CHAT_ONLY position based on anchor
            if self.current_state in [WindowState.FULL_CONTENT, WindowState.WEBVIEW]:
                chat_only_geom = self._calculate_chat_only_position_from_anchor(geo)
                update_data['window_geometry']['chat_only'] = chat_only_geom
                logging.info(f"Updated CHAT_ONLY position based on {self.current_state.value} anchor")
            
            # Update settings in memory
            self.settings_manager.update(update_data)
            self._pending_geometry_save = True
            
            logging.info(f"Saved {self.current_state.value} geometry: "
                        f"pos({left_percent:.2f}, {top_percent:.2f}) "
                        f"size({width_percent:.2f}x{height_percent:.2f})")
                        
        except Exception as e:
            logging.error(f"Failed to save window geometry: {e}")
    
    def _persist_geometry_if_needed(self):
        """Persist geometry to disk if there are pending changes"""
        if getattr(self, '_pending_geometry_save', False):
            try:
                # Force save to disk
                self.settings_manager.save()
                self._pending_geometry_save = False
                logging.debug("Persisted geometry changes to disk")
            except Exception as e:
                logging.error(f"Failed to persist geometry: {e}")
    
    def moveEvent(self, event):
        """Handle window move events with delayed saving"""
        super().moveEvent(event)
        # Only save if not in precreating mode and window is visible
        if not self._is_precreating and self.isVisible():
            # Restart timer to delay save (debounce)
            self._geometry_save_timer.stop()
            self._geometry_save_timer.start(500)  # 500ms delay
    
    def resizeEvent(self, event):
        """Handle window resize events with delayed saving"""
        super().resizeEvent(event)
        # Only save if not in precreating mode and window is visible
        if not self._is_precreating and self.isVisible():
            # Restart timer to delay save (debounce)
            self._geometry_save_timer.stop()
            self._geometry_save_timer.start(500)  # 500ms delay
    
    def set_precreating_mode(self, is_precreating: bool):
        """Set the precreating mode flag"""
        self._is_precreating = is_precreating
        logging.debug(f"Precreating mode set to: {is_precreating}")
    
    def _get_window_screen_quadrant(self):
        """Get which quadrant of the screen the window center is in
        Returns: tuple (quadrant, center_x_percent, center_y_percent)
        Quadrants: 1=top-right, 2=top-left, 3=bottom-left, 4=bottom-right
        """
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            window_rect = self.geometry()
            
            # Calculate window center
            window_center_x = window_rect.x() + window_rect.width() // 2
            window_center_y = window_rect.y() + window_rect.height() // 2
            
            # Calculate relative position (0.0 to 1.0)
            center_x_percent = (window_center_x - screen.x()) / screen.width()
            center_y_percent = (window_center_y - screen.y()) / screen.height()
            
            # Determine quadrant
            if center_x_percent >= 0.5 and center_y_percent < 0.5:
                quadrant = 1  # top-right
            elif center_x_percent < 0.5 and center_y_percent < 0.5:
                quadrant = 2  # top-left  
            elif center_x_percent < 0.5 and center_y_percent >= 0.5:
                quadrant = 3  # bottom-left
            else:
                quadrant = 4  # bottom-right
                
            return quadrant, center_x_percent, center_y_percent
            
        except Exception as e:
            logging.error(f"Failed to calculate window quadrant: {e}")
            return 4, 0.8, 0.8  # Default to bottom-right
    
    def _calculate_chat_only_position_from_anchor(self, current_geometry):
        """Calculate CHAT_ONLY position based on current window's anchor point"""
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            screen_width = screen.width()
            screen_height = screen.height()
            screen_x = screen.x()
            screen_y = screen.y()
            
            # Get quadrant and anchor point
            quadrant, _, _ = self._get_window_screen_quadrant()
            
            # Get CHAT_ONLY size from settings
            try:
                window_geom = self.settings_manager.settings.window_geometry
                chat_only_geom = window_geom.chat_only
                chat_only_width = int(screen_width * chat_only_geom.width_percent)
                chat_only_height = int(screen_height * chat_only_geom.height_percent)
            except AttributeError:
                # Fallback to default percentages
                chat_only_width = int(screen_width * 0.22)
                chat_only_height = int(screen_height * 0.108)
            
            # Calculate position based on quadrant
            if quadrant == 1:  # top-right - anchor at top-right
                left = current_geometry.x() + current_geometry.width() - chat_only_width
                top = current_geometry.y()
            elif quadrant == 2:  # top-left - anchor at top-left
                left = current_geometry.x()
                top = current_geometry.y()
            elif quadrant == 3:  # bottom-left - anchor at bottom-left
                left = current_geometry.x()
                top = current_geometry.y() + current_geometry.height() - chat_only_height
            else:  # quadrant == 4, bottom-right - anchor at bottom-right
                left = current_geometry.x() + current_geometry.width() - chat_only_width
                top = current_geometry.y() + current_geometry.height() - chat_only_height
            
            # Convert to percentages
            left_percent = (left - screen_x) / screen_width
            top_percent = (top - screen_y) / screen_height
            width_percent = chat_only_width / screen_width
            height_percent = chat_only_height / screen_height
            
            # Ensure values are in reasonable range
            left_percent = max(0.0, min(1.0, left_percent))
            top_percent = max(0.0, min(1.0, top_percent))
            width_percent = max(0.1, min(0.5, width_percent))
            height_percent = max(0.1, min(0.5, height_percent))
            
            return {
                'left_percent': left_percent,
                'top_percent': top_percent,
                'width_percent': width_percent,
                'height_percent': height_percent
            }
            
        except Exception as e:
            logging.error(f"Failed to calculate chat only position: {e}")
            # Return default values
            return {
                'left_percent': 0.65,
                'top_percent': 0.85,
                'width_percent': 0.22,
                'height_percent': 0.108
            }
    
    def _show_menu_with_intelligent_position(self, menu, reference_button):
        """Show menu with intelligent positioning based on window location"""
        try:
            quadrant, center_x_percent, center_y_percent = self._get_window_screen_quadrant()
            
            # Calculate menu position based on quadrant and button position  
            button_rect = reference_button.geometry()
            button_global_pos = reference_button.mapToGlobal(QPoint(0, 0))
            menu_size = menu.sizeHint()
            
            # Decide menu direction based on window position
            if center_y_percent < 0.4:  # Window in upper part of screen
                # Show menu below button
                menu_pos = QPoint(button_global_pos.x(), button_global_pos.y() + button_rect.height())
            else:  # Window in lower part of screen  
                # Show menu above button
                menu_pos = QPoint(button_global_pos.x(), button_global_pos.y() - menu_size.height())
            
            # Adjust horizontal position to avoid screen edges
            screen = QApplication.primaryScreen().availableGeometry()
            if menu_pos.x() + menu_size.width() > screen.right():
                menu_pos.setX(screen.right() - menu_size.width())
            if menu_pos.x() < screen.left():
                menu_pos.setX(screen.left())
                
            logging.debug(f"Showing menu at quadrant {quadrant}, position: {menu_pos}")
            menu.exec(menu_pos)
            
        except Exception as e:
            logging.error(f"Failed to position menu intelligently: {e}")
            # Fallback to default positioning
            button_global_pos = reference_button.mapToGlobal(QPoint(0, reference_button.height()))
            menu.exec(button_global_pos)
    
    def update_window_layout(self):
        """Update window layout based on current state"""
        # Get anchor point based on window position before any changes
        quadrant, center_x_percent, center_y_percent = self._get_window_screen_quadrant()
        
        # Determine which corner to use as anchor based on quadrant
        if quadrant == 1:  # top-right
            anchor_point = self.geometry().topRight()
        elif quadrant == 2:  # top-left
            anchor_point = self.geometry().topLeft()
        elif quadrant == 3:  # bottom-left
            anchor_point = self.geometry().bottomLeft()
        else:  # quadrant == 4, bottom-right (default)
            anchor_point = self.geometry().bottomRight()
            
        logging.debug(f"Window quadrant: {quadrant}, using anchor: {anchor_point}")
        
        if self.current_state == WindowState.CHAT_ONLY:
            # Hide title bar and content area, only show input container
            self.title_bar.hide()
            self.content_stack.hide()
            self.input_container.show()
            
            # For CHAT_ONLY mode, completely disable resizing by setting fixed size
            # Only call setFixedSize if the size has changed to avoid BlurWindow issues
            target_size = self._get_chat_only_size()
            if self.size() != target_size:
                self.setFixedSize(target_size)
                logging.info(f"Setting CHAT_ONLY fixed size to: {target_size.width()}x{target_size.height()}")

            # Update main container style for full rounded corners
            self.update_container_style(full_rounded=True)
            
        elif self.current_state == WindowState.FULL_CONTENT:
            # Show all content
            self.title_bar.show()
            self.content_stack.show()
            self.input_container.show()
            
            # Remove fixed size constraints
            self.setMinimumSize(300, 200)
            self.setMaximumSize(16777215, 16777215)
            
            # Restore geometry from settings
            self.restore_geometry()

            # Update main container style for standard rounded corners
            self.update_container_style(full_rounded=False)
            
        elif self.current_state == WindowState.WEBVIEW:
            # WebView state - hide title bar
            self.title_bar.hide()
            self.content_stack.show()
            self.input_container.hide()  # Also hide input container in webview mode
            
            # Remove fixed size constraints
            self.setMinimumSize(300, 200)
            self.setMaximumSize(16777215, 16777215)
            
            # Restore geometry from settings
            self.restore_geometry()
            
            # Update main container style
            self.update_container_style(full_rounded=False)
        
        # Reposition window based on intelligent anchor point
        new_size = self.size()
        
        # Calculate new position based on which corner is anchored
        if quadrant == 1:  # top-right - anchor top-right corner
            new_x = anchor_point.x() - new_size.width()
            new_y = anchor_point.y()
        elif quadrant == 2:  # top-left - anchor top-left corner
            new_x = anchor_point.x()
            new_y = anchor_point.y()
        elif quadrant == 3:  # bottom-left - anchor bottom-left corner
            new_x = anchor_point.x()
            new_y = anchor_point.y() - new_size.height()
        else:  # quadrant == 4, bottom-right - anchor bottom-right corner (default)
            new_x = anchor_point.x() - new_size.width()
            new_y = anchor_point.y() - new_size.height()
        
        # Ensure window stays within screen bounds
        screen = QApplication.primaryScreen().geometry()
        new_x = max(0, min(new_x, screen.width() - new_size.width()))
        new_y = max(0, min(new_y, screen.height() - new_size.height()))
        
        logging.debug(f"Repositioning window from anchor {anchor_point} to ({new_x}, {new_y})")
        self.move(new_x, new_y)
    
    def switch_to_chat_only(self):
        """Switch to chat only state (input box only)"""
        # Save current state's geometry before switching
        self.save_geometry()

        self.current_state = WindowState.CHAT_ONLY
        self.update_window_layout()
        
    def switch_to_full_content(self):
        """Switch to full content state"""
        # Save current state's geometry before switching
        if self.current_state == WindowState.WEBVIEW:
            self.save_geometry()
            
        self.current_state = WindowState.FULL_CONTENT
        self.has_user_input = True
        self.has_switched_state = True  # User has manually switched states
        self.update_window_layout()
        
        # Restore chat scroll position after switching back from webview
        if hasattr(self, '_was_at_bottom') and hasattr(self, 'chat_view') and self.chat_view:
            # Use QTimer to ensure the layout is complete before restoring scroll position
            # Schedule after other layout updates (50ms and 100ms)
            QTimer.singleShot(200, self._restore_chat_scroll_position)
        
    def switch_to_webview(self):
        """Switch to webview state"""
        # Save current state's geometry before switching
        if self.current_state == WindowState.FULL_CONTENT:
            self.save_geometry()
            # Save chat scroll position before switching
            if hasattr(self, 'chat_view') and self.chat_view:
                scrollbar = self.chat_view.verticalScrollBar()
                current_value = scrollbar.value()
                current_maximum = scrollbar.maximum()
                
                # Check if user was at or near the bottom (within 50 pixels)
                self._was_at_bottom = (current_maximum - current_value) <= 50
                
                # Save relative position as percentage if not at bottom
                if not self._was_at_bottom and current_maximum > 0:
                    self._saved_chat_scroll_percentage = current_value / current_maximum
                else:
                    self._saved_chat_scroll_percentage = None
                    
                logging.debug(f"Saved chat scroll state: was_at_bottom={self._was_at_bottom}, percentage={self._saved_chat_scroll_percentage}")
            
        self.current_state = WindowState.WEBVIEW
        self.has_switched_state = True  # User has manually switched states
        self.update_window_layout()

    def _restore_chat_scroll_position(self):
        """Restore saved chat scroll position"""
        try:
            if hasattr(self, 'chat_view') and self.chat_view:
                scrollbar = self.chat_view.verticalScrollBar()
                
                # Check if we have saved scroll state
                if hasattr(self, '_was_at_bottom'):
                    if self._was_at_bottom:
                        # User was at bottom, scroll to new bottom
                        scrollbar.setValue(scrollbar.maximum())
                        logging.debug("Restored chat scroll to bottom")
                    elif hasattr(self, '_saved_chat_scroll_percentage') and self._saved_chat_scroll_percentage is not None:
                        # Restore to relative position
                        new_value = int(scrollbar.maximum() * self._saved_chat_scroll_percentage)
                        scrollbar.setValue(new_value)
                        logging.debug(f"Restored chat scroll to {self._saved_chat_scroll_percentage*100:.1f}% position")
                    
                    # Clean up saved state
                    if hasattr(self, '_was_at_bottom'):
                        delattr(self, '_was_at_bottom')
                    if hasattr(self, '_saved_chat_scroll_percentage'):
                        delattr(self, '_saved_chat_scroll_percentage')
        except Exception as e:
            logging.error(f"Failed to restore chat scroll position: {e}")

    def update_container_style(self, full_rounded=False):
        """Update main container rounded corner style"""
        if full_rounded:
            # CHAT_ONLY mode: full rounded corners
            self.main_container.setStyleSheet("""
                #mainContainer {
                    background: rgba(255, 255, 255, 115);
                    border-radius: 10px;
                    border: none;
                }
            """)
        else:
            # Other modes: standard style
            self.main_container.setStyleSheet("""
                #mainContainer {
                    background: rgba(255, 255, 255, 115);
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 40);
                }
            """)
    
    def _handle_wiki_close(self):
        """Handle wiki view close button - pause media then hide window"""
        # Pause media playback before hiding
        if hasattr(self, 'wiki_view') and self.wiki_view:
            current_widget = self.content_stack.currentWidget()
            if current_widget == self.wiki_view:
                self.wiki_view.pause_page()
        
        # Hide the window
        self.hide()
    
    def show_chat_view(self):
        """Switch to chat view"""
        # First record history if needed, then stop media playback
        if hasattr(self, 'wiki_view') and self.wiki_view:
            current_widget = self.content_stack.currentWidget()
            if current_widget == self.wiki_view:
                # Get current URL before switching
                current_url = getattr(self.wiki_view, 'current_url', None)
                
                # Check if we should record history (not task flow HTML and not Quick Access URL)
                if current_url and not self._is_task_flow_url(current_url):
                    # Record history with actual page title
                    self._record_history_before_leaving_wiki()
                
                # Then pause media playback
                self.wiki_view.pause_page()
        
        # If coming from WEBVIEW state, switch back to FULL_CONTENT
        if self.current_state == WindowState.WEBVIEW:
            self.switch_to_full_content()
            
        self.content_stack.setCurrentWidget(self.chat_view)
        # Show input area and shortcuts in chat mode
        if hasattr(self, 'input_container'):
            self.input_container.show()
        # Reset size constraints when switching to chat view
        self.reset_size_constraints()
        # Ensure message width is correct and trigger full layout update
        QTimer.singleShot(50, self.chat_view.update_all_message_widths)
        # Delay executing full layout update, ensure content is fully displayed
        QTimer.singleShot(100, self.chat_view._performDelayedResize)
        # Set focus to input field when returning to chat view (only if auto voice is not enabled)
        if hasattr(self, 'settings_manager') and self.settings_manager:
            if not self.settings_manager.settings.auto_voice_on_hotkey:
                QTimer.singleShot(150, self._set_chat_input_focus)
        else:
            # If no settings_manager, maintain original behavior
            QTimer.singleShot(150, self._set_chat_input_focus)
        # Also try to restore scroll position again after all layout updates
        if hasattr(self, '_was_at_bottom'):
            QTimer.singleShot(250, self._restore_chat_scroll_position)
        
    def _set_chat_input_focus(self):
        """Set focus to input field in chat view with improved reliability"""
        if not hasattr(self, 'input_field') or not self.input_field:
            return
            
        logger = logging.getLogger(__name__)
        
        def try_set_focus():
            try:
                # 1. Ensure window is properly shown and active
                if not self.isVisible():
                    logger.warning("Window is not visible, cannot set focus")
                    return False
                    
                # 2. Bring window to front and activate
                self.raise_()
                self.activateWindow()
                
                # 3. Wait a bit for window manager to process
                QApplication.processEvents()
                
                # 4. Verify window is actually active
                if not self.isActiveWindow():
                    logger.warning("Window is not active after activation attempt")
                    # Try once more
                    self.activateWindow()
                    QApplication.processEvents()
                
                # 5. Set focus to input field
                self.input_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
                
                # 6. Verify focus was set
                if self.input_field.hasFocus():
                    logger.info("✅ Chat input focus set successfully")
                    return True
                else:
                    logger.warning("⚠️ Input field does not have focus after setting")
                    return False
                    
            except Exception as e:
                logger.warning(f"❌ Failed to set chat input focus: {e}")
                return False
        
        # Try immediately first
        if try_set_focus():
            return
            
        # If immediate attempt fails, try again after a longer delay
        logger.info("🔄 Retrying focus setting after delay...")
        QTimer.singleShot(300, lambda: try_set_focus())
    
    def _is_task_flow_url(self, url: str) -> bool:
        """Check if URL is a task flow local HTML file"""
        # Task flow URLs are local files with specific game names
        if not url.startswith('file://'):
            return False
        
        # Check if it contains any game-specific task flow patterns
        # Updated patterns to match actual file names
        task_flow_patterns = [
            'helldiver2_',     # Helldivers 2
            'dst_',            # Don't Starve Together
            'civilization6_',  # Civilization VI
            'eldenring_'       # Elden Ring (for future use)
        ]
        url_lower = url.lower()
        
        # Check if URL ends with .html and contains any of the patterns
        if url_lower.endswith('.html'):
            return any(pattern in url_lower for pattern in task_flow_patterns)
        
        return False

    def _record_history_before_leaving_wiki(self):
        """Record browsing history before leaving wiki view with enhanced real-time URL and title detection"""
        logger = logging.getLogger(__name__)
        
        if not hasattr(self, 'wiki_view') or not self.wiki_view:
            logger.debug("No wiki_view available, skipping history record")
            return
            
        # Get WebView2 instance
        web_view = getattr(self.wiki_view, 'web_view', None)
        if not web_view:
            logger.debug("No web_view available, skipping history record")
            return
        
        # Enhanced URL and title detection - get real-time values from WebView2
        actual_url = None
        actual_title = None
        
        # Try to get actual current URL from WebView2 first (handles redirects properly)
        if hasattr(web_view, 'url') and callable(web_view.url):
            try:
                qurl = web_view.url()
                if qurl and not qurl.isEmpty():
                    actual_url = qurl.toString()
                    logger.info(f"📍 Got actual URL from WebView2: {actual_url}")
            except Exception as e:
                logger.warning(f"Failed to get URL from WebView2: {e}")
        
        # Try to get actual current title from WebView2 (handles redirects properly) 
        if hasattr(web_view, 'current_title'):
            try:
                actual_title = getattr(web_view, 'current_title', None)
                if actual_title:
                    logger.info(f"📄 Got actual title from WebView2: {actual_title}")
            except Exception as e:
                logger.warning(f"Failed to get title from WebView2: {e}")
        
        # Fallback to WikiView's stored values if WebView2 values not available
        if not actual_url:
            actual_url = getattr(self.wiki_view, 'current_url', None)
            logger.info(f"📍 Using fallback URL from WikiView: {actual_url}")
            
        if not actual_title:
            actual_title = getattr(self.wiki_view, 'current_title', None)  
            logger.info(f"📄 Using fallback title from WikiView: {actual_title}")
            
        if not actual_url:
            logger.debug("No URL available, skipping history record")
            return
            
        logger.info(f"🔍 Recording history for URL: {actual_url}")
        
        # Use the actual title if available and valid
        if actual_title and actual_title.strip() and actual_title != actual_url:
            logger.info(f"✅ Using actual title: {actual_title}")
            self._save_to_history(actual_url, actual_title)
        # Try JavaScript-based title extraction as additional fallback
        elif hasattr(web_view, 'runJavaScript'):
            logger.info("📝 Attempting JavaScript title extraction as fallback")
            self._get_title_from_webview2(web_view, actual_url)
        else:
            logger.warning("No title available, using URL as title")
            self._save_to_history(actual_url, actual_url)
    
    def _get_title_from_webview2(self, web_view, current_url):
        """Get title from WebView2 using a workaround"""
        logger = logging.getLogger(__name__)
        
        try:
            # First, store the title in a global variable
            store_script = """
            window.__gamewiki_page_title = (function() {
                var title = document.title;
                
                if (!title || title.trim() === '' || title === window.location.hostname) {
                    var ogTitle = document.querySelector('meta[property="og:title"]');
                    if (ogTitle && ogTitle.content) {
                        title = ogTitle.content;
                    } else {
                        var twitterTitle = document.querySelector('meta[name="twitter:title"]');
                        if (twitterTitle && twitterTitle.content) {
                            title = twitterTitle.content;
                        } else {
                            var h1 = document.querySelector('h1');
                            if (h1 && h1.innerText) {
                                title = h1.innerText.trim();
                            }
                        }
                    }
                }
                
                return title || document.title || '';
            })();
            """
            
            # Execute script to store title
            web_view.runJavaScript(store_script)
            
            # Wait a bit and then retrieve the stored title
            QTimer.singleShot(100, lambda: self._retrieve_webview2_title(web_view, current_url))
            
        except Exception as e:
            logger.error(f"Failed to store title in WebView2: {e}")
            self._save_to_history(current_url, current_url)
    
    def _retrieve_webview2_title(self, web_view, current_url):
        """Retrieve the stored title from WebView2"""
        logger = logging.getLogger(__name__)

        # Try to get title from web_view's parent WikiView's current_title attribute
        # web_view is the WebView2WinRTWidget, its parent should be WikiView
        wiki_view = web_view.parent() if hasattr(web_view, 'parent') else None
        
        if wiki_view and hasattr(wiki_view, 'current_title') and wiki_view.current_title and wiki_view.current_title != current_url:
            title = wiki_view.current_title
            logger.info(f"Using cached title from WikiView: {title}")
            self._save_to_history(current_url, title)
        # Also check if self.wiki_view exists (the actual WikiView widget)
        elif hasattr(self, 'wiki_view') and hasattr(self.wiki_view, 'current_title') and self.wiki_view.current_title and self.wiki_view.current_title != current_url:
            title = self.wiki_view.current_title
            logger.info(f"Using cached title from self.wiki_view: {title}")
            self._save_to_history(current_url, title)
        else:
            logger.warning(f"Could not retrieve title, using URL as fallback")
            self._save_to_history(current_url, current_url)

    def _save_to_history(self, url: str, title: str):
        """Save URL and title to browsing history"""
        logger = logging.getLogger(__name__)
        
        # Validate title
        if not title or title.strip() == '':
            logger.warning(f"Empty title for URL: {url}, skipping history record")
            return
            
        # Clean up title
        title = title.strip()
        
        # Ensure history manager exists
        self._ensure_history_manager()
        
        # Determine source type
        source = "web"
        if "youtube.com" in url.lower():
            source = "video"
        elif any(wiki in url.lower() for wiki in ['wikipedia.org', 'fandom.com', 'wiki.']):
            source = "wiki"
            
        # Add to history
        try:
            self.history_manager.add_entry(url, title, source=source)
            logger.info(f"✅ Recorded history: {title} ({url})")
        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def show_wiki_page(self, url: str, title: str):
        """Switch to wiki view and load page"""
        logger = logging.getLogger(__name__)
        logger.info(f"🌐 UnifiedAssistantWindow.show_wiki_page called: URL={url}, Title={title}")
        
        # Switch to WEBVIEW state
        self.switch_to_webview()
        
        self.wiki_view.load_wiki(url, title)
        self.content_stack.setCurrentWidget(self.wiki_view)
        
        # Restore page activity in WikiView (if previously paused)
        self.wiki_view.resume_page()
        
        # Hide input area and shortcuts in wiki mode
        if hasattr(self, 'input_container'):
            self.input_container.hide()
        # Shortcut container is now hidden - shortcuts are in popup
        # Reset size constraints when switching to Wiki view
        self.reset_size_constraints()
        logger.info(f"✅ Switched to Wiki view and loaded page")
        
    def handle_wiki_page_loaded(self, url: str, title: str):
        """Handle Wiki page loaded signal, forward signal to controller"""
        print(f"🌐 UnifiedAssistantWindow: Wiki page loaded - {title}: {url}")
        # Emit signal to controller for processing
        self.wiki_page_found.emit(url, title)
        
    def set_mode(self, mode: str):
        """Set the input mode (auto, wiki, ai or url)"""

        self.current_mode = mode
        if mode == "url":
            self.input_field.setPlaceholderText(t("placeholder_enter_url"))
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_open_url_clicked)
        elif mode == "wiki":
            self.input_field.setPlaceholderText(t("placeholder_search_query"))
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_send_clicked)
        elif mode == "ai":
            self.input_field.setPlaceholderText(t("placeholder_enter_question"))
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_send_clicked)
        else:  # auto mode
            self.input_field.setPlaceholderText(t("placeholder_enter_message"))
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_send_clicked)
    
    def on_input_return_pressed(self):
        """Handle return key press based on current mode"""
        if self.current_mode == "url":
            self.on_open_url_clicked()
        else:
            self.on_send_clicked()
    
    def on_open_url_clicked(self):
        """Handle URL open button click"""
        url = self.input_field.text().strip()
        if url:
            # Ensure URL has protocol
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            self.open_url(url)
            self.input_field.clear()
    
    def open_url(self, url: str):
        """Open a URL in the wiki view"""
        # Switch to webview window form first
        self.switch_to_webview()

        # Extract domain as temporary title
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            title = parsed.netloc or url
        except:
            title = url
            
        # Switch to wiki view and load URL (without recording history)
        self.wiki_view.load_wiki(url, title)
        self.content_stack.setCurrentWidget(self.wiki_view)
        
    def open_url_with_webview(self, url: str):
        """Open URL in webview mode"""
        # Switch to webview mode first
        self.switch_to_webview()
        # Then open the URL
        self.open_url(url)
        self.wiki_view.resume_page()
        
        # Hide input area and shortcuts in wiki mode
        if hasattr(self, 'input_container'):
            self.input_container.hide()
        # Shortcut container is now hidden - shortcuts are in popup
        # Reset size constraints when switching to Wiki view
        self.reset_size_constraints()
        
        logger = logging.getLogger(__name__)
        logger.info("✅ Switched to Wiki view for URL navigation")
    
    def load_shortcuts(self):
        """Load shortcut buttons from settings"""
        try:
            # Clear existing buttons in popup
            self.quick_access_popup.clear_shortcuts()
            
            # Get shortcuts from settings
            shortcuts = []
            if self.settings_manager:
                try:
                    shortcuts = self.settings_manager.get('shortcuts', [])
                except Exception as e:
                    print(f"Failed to get shortcuts from settings: {e}")
                    
            
            # Filter out hidden shortcuts
            visible_shortcuts = [s for s in shortcuts if s.get('visible', True)]
            
            # Hide shortcut container - shortcuts are now in popup
            if hasattr(self, 'shortcut_container'):
                self.shortcut_container.hide()
            
            # Create buttons for visible shortcuts only
            for shortcut in visible_shortcuts:
                try:
                    # Use package_file to get correct path
                    from src.game_wiki_tooltip.core.utils import package_file, APPDATA_DIR
                    icon_path = ""
                    if shortcut.get('icon'):
                        try:
                            relative_path = shortcut.get('icon', '')
                            print(f"[load_shortcuts] Trying to load icon: {relative_path}")
                            
                            # Get the actual file path
                            import pathlib
                            import shutil
                            
                            # Create icons directory in APPDATA if it doesn't exist
                            icons_dir = APPDATA_DIR / "icons"
                            icons_dir.mkdir(exist_ok=True)
                            
                            # Get the icon filename
                            icon_filename = pathlib.Path(relative_path).name
                            cached_icon_path = icons_dir / icon_filename
                            
                            # Check if icon already exists in cache
                            if cached_icon_path.exists():
                                icon_path = str(cached_icon_path)
                                print(f"[load_shortcuts] Using cached icon: {icon_path}")
                            else:
                                # Try direct path first (for development)
                                base_path = pathlib.Path(__file__).parent
                                # relative_path already contains "assets/icons/..."
                                direct_path = base_path / relative_path
                                
                                if direct_path.exists():
                                    # Copy to cache
                                    shutil.copyfile(direct_path, cached_icon_path)
                                    icon_path = str(cached_icon_path)
                                    print(f"[load_shortcuts] Copied icon to cache: {icon_path}")
                                else:
                                    # Try package_file for packaged app
                                    try:
                                        # Remove 'assets/' prefix for package_file call
                                        package_path = relative_path
                                        if relative_path.startswith('assets/'):
                                            package_path = relative_path[7:]  # Remove 'assets/'
                                        path_obj = package_file(package_path)
                                        
                                        # Copy file to cache
                                        shutil.copyfile(path_obj, cached_icon_path)
                                        icon_path = str(cached_icon_path)
                                        print(f"[load_shortcuts] Copied package file to cache: {icon_path}")
                                    except Exception as e:
                                        print(f"[load_shortcuts] Failed with package_file: {e}")
                                        icon_path = ""
                        except Exception as e:
                            print(f"[load_shortcuts] Failed to get icon path: {e}")
                            icon_path = ""
                    
                    name = shortcut.get('name', 'Website')
                    btn = ExpandableIconButton(
                        icon_path,
                        f"Go to {name}",
                        shortcut.get('url', 'https://google.com'),
                        name  # Pass the name for text display
                    )
                    btn.clicked.connect(lambda checked, url=shortcut.get('url', ''): self.open_url_with_webview(url))
                    # Add to popup instead of shortcut_layout
                    self.quick_access_popup.add_shortcut(btn)
                except Exception as e:
                    print(f"Failed to create shortcut button: {e}")
            
            # Note: Task flow buttons are now in the main button row, not in popup
            
            # Mark shortcuts as loaded
            self.shortcuts_loaded = True
            
        except Exception as e:
            print(f"Error in load_shortcuts: {e}")

    def _open_game_task_flow(self, config):
        """Open game task flow HTML file"""
        try:
            # Prevent multiple clicks
            if hasattr(self, '_task_flow_loading') and self._task_flow_loading:
                return
            self._task_flow_loading = True
            
            # Get current language setting
            current_language = 'en'
            if self.settings_manager:
                settings = self.settings_manager.get()
                current_language = settings.get('language', 'en')
            
            # Select corresponding HTML file based on language
            html_filename = config['html_files'].get(current_language, config['html_files']['en'])
            
            # Get HTML file path
            import pathlib
            base_path = pathlib.Path(__file__).parent.parent
            html_path = base_path / "assets" / "html" / html_filename
            
            if html_path.exists():
                print(f"Loading task flow from: {html_path}")
                
                # Display directly in the application, same as wiki link logic
                try:
                    title = t("dst_task_flow_title")

                    # Use the same display logic as wiki link
                    self._load_local_html_in_wiki_view(html_path, title)
                    
                except Exception as html_error:
                    print(f"Failed to load HTML content: {html_error}")
            else:
                print(f"DST task flow file not found: {html_path}")
                
        except Exception as e:
            print(f"Failed to open DST task flow: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Reset loading flag
            self._task_flow_loading = False
    
    def _load_local_html_in_wiki_view(self, html_path: pathlib.Path, title: str):
        """Load local HTML file with the same logic as wiki link"""
        try:
            # Create file:// URL, same as normal wiki link processing
            file_url = html_path.as_uri()
            print(f"Loading local HTML with file URL: {file_url}")
            
            # Use standard show_wiki_page method, ensure consistent behavior with other wiki links
            self.show_wiki_page(file_url, title)
            
        except Exception as e:
            print(f"Failed to load local HTML in wiki view: {e}")
    
    def show_history_menu(self):
        """Show history menu"""
        self._ensure_history_manager()
            
        history_menu = QMenu(self)  # Use standard QMenu with parent
        
        # Get history
        history_items = self.history_manager.get_history(limit=20)
        
        if not history_items:
            no_history_action = history_menu.addAction("No browsing history")
            no_history_action.setEnabled(False)
        else:
            # Add header
            header_action = history_menu.addAction("Recent Pages")
            header_action.setEnabled(False)
            header_font = header_action.font()
            header_font.setBold(True)
            header_action.setFont(header_font)
            history_menu.addSeparator()
            
            # Add history items
            for item in history_items[:10]:  # Show top 10
                title = item.get('title', 'Untitled')
                url = item.get('url', '')
                visit_count = item.get('visit_count', 1)
                
                # Truncate long titles
                if len(title) > 40:
                    title = title[:37] + "..."
                
                # Create action text with visit count if > 1
                if visit_count > 1:
                    action_text = f"{title} ({visit_count}x)"
                else:
                    action_text = title
                
                action = history_menu.addAction(action_text)
                action.setToolTip(url)
                
                # Connect to open the URL
                action.triggered.connect(lambda checked, u=url, t=item.get('title', 'Untitled'): self.show_wiki_page(u, t))
            
            if len(history_items) > 10:
                history_menu.addSeparator()
                more_action = history_menu.addAction(t("history_more", count=len(history_items) - 10))
                more_action.setEnabled(False)
            
            # Add clear history option
            history_menu.addSeparator()
            clear_action = history_menu.addAction(t("clear_history"))
            clear_action.triggered.connect(self.clear_history)
        
        # Show menu with intelligent positioning
        self._show_menu_with_intelligent_position(history_menu, self.history_button)
    
    def clear_history(self):
        """Clear browsing history"""
        self._ensure_history_manager()
        self.history_manager.clear_history()
        # Show notification
        QTimer.singleShot(100, lambda: self.history_button.setToolTip(t("tooltip_history_cleared")))
        QTimer.singleShot(2000, lambda: self.history_button.setToolTip(t("tooltip_view_history")))

    def _show_task_flow_html(self, game_name):
        """Show task flow HTML for a specific game"""
        try:
            # Get current language setting
            current_language = 'en'
            if self.settings_manager:
                settings = self.settings_manager.get()
                current_language = settings.get('language', 'en')
            
            # Build config for the game
            config = {
                'game_name': game_name,
                'display_name': t(f'{game_name}_task_button'),
                'html_files': {
                    'en': f'{game_name}_en.html',
                    'zh': f'{game_name}_zh.html'
                }
            }
            
            # Call existing method
            self._open_game_task_flow(config)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to show task flow HTML for {game_name}: {e}")
            # Show error message
            self.chat_view.add_message(
                MessageType.STATUS,
                f"Unable to open {game_name} task flow"
            )

    def set_current_game_window(self, game_window_title: Optional[str]):
        """Set current game window title and update task flow button visibility"""
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        
        # Debug: Log method call with stack trace to identify caller
        logger.info(f"🎮 [DEBUG] set_current_game_window called with: '{game_window_title}'")
        
        # Handle None value - clear game context
        if game_window_title is None:
            logger.info("🧹 Clearing game window context in main window")
            self.current_game_window = None

            logger.info("✅ Game context cleared in main window, all task buttons hidden")
            return
        
        logger.debug(f"🔍 [DEBUG] Call stack (last 3 frames):")
        stack = traceback.extract_stack()
        for i, frame in enumerate(stack[-4:-1]):  # Skip current frame, show last 3
            logger.debug(f"    Frame {i+1}: {frame.filename}:{frame.lineno} in {frame.name}")
        
        # Debug: Log current state before change
        old_game_window = getattr(self, 'current_game_window', None)
        logger.info(f"🔄 [DEBUG] Game window change: '{old_game_window}' -> '{game_window_title}'")

        # Set the new game window
        self.current_game_window = game_window_title
        
        # Debug: Log before button visibility update
        logger.info(f"🎯 [DEBUG] About to update task button visibility for: '{game_window_title}'")
        
        # Update task flow button based on current game
        self._update_task_flow_button()
        
        # Debug: Log completion
        logger.info(f"✅ [DEBUG] set_current_game_window completed for: '{game_window_title}'")
    
    def _update_task_flow_button(self):
        """Update task flow button visibility and functionality based on current game"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Define games that support task flow
        game_configs = {
            'dst': {
                'display_name': t('dst_task_button'),
                'window_titles': ["don't starve together", "dst"],
                'handler': lambda: self._show_task_flow_html('dst')
            },
            'helldiver2': {
                'display_name': t('helldiver2_task_button'),
                'window_titles': ["helldivers™ 2", "helldivers 2"],
                'handler': lambda: self._show_task_flow_html('helldiver2')
            },
            'civilization6': {
                'display_name': t('civ6_task_button'),
                'window_titles': ["sid meier's civilization vi", "civilization vi", "civ6"],
                'handler': lambda: self._show_task_flow_html('civilization6')
            },
            'eldenring': {
                'display_name': t('eldenring_task_button'),
                'window_titles': ["elden ring"],
                'handler': lambda: self._show_task_flow_html('eldenring')
            }
        }
        
        if not self.current_game_window:
            # No game window set, hide task flow button
            self.task_flow_button.hide()
            self.current_task_flow_game = None
            return
            
        # Get normalized window title for comparison
        current_window_lower = self.current_game_window.lower()
        
        # Find matching game
        matched_game = None
        for game_name, config in game_configs.items():
            if any(title in current_window_lower for title in config['window_titles']):
                matched_game = game_name
                break
                
        if matched_game:
            # Show and configure task flow button
            config = game_configs[matched_game]
            self.task_flow_button.setText(config['display_name'])
            self.task_flow_button.show()
            
            # Force UI update to show button immediately
            self.task_flow_button.update()
            self.task_flow_button.repaint()
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
            # Disconnect previous handler if any
            try:
                self.task_flow_button.clicked.disconnect()
            except:
                pass
                
            # Connect new handler
            self.task_flow_button.clicked.connect(config['handler'])
            self.current_task_flow_game = matched_game
            
            logger.info(f"✅ Task flow button shown for {matched_game}")
        else:
            # No matching game, hide button
            self.task_flow_button.hide()
            self.current_task_flow_game = None
            logger.info(f"⚠️ No task flow available for current window: {self.current_game_window}")
    
    def on_quick_access_clicked(self):
        """Show quick access popup"""
        # Load shortcuts if not loaded
        if not self.shortcuts_loaded:
            self.load_shortcuts()
            
        # Show popup above the button
        self.quick_access_popup.show_at(self.quick_access_button)
        
    def eventFilter(self, obj, event):
        """Event filter to handle events"""
        # Remove hover behavior for quick access button
        return super().eventFilter(obj, event)
        
    def show_mode_menu(self):
        """Show search mode menu with intelligent positioning"""
        mode_menu = QMenu(self)  # Use standard QMenu with parent
        from src.game_wiki_tooltip.core.i18n import t
        
        auto_action = mode_menu.addAction(t("search_mode_auto"))
        auto_action.triggered.connect(lambda: self.set_mode("auto"))
        
        wiki_action = mode_menu.addAction(t("search_mode_wiki"))
        wiki_action.triggered.connect(lambda: self.set_mode("wiki"))
        
        ai_action = mode_menu.addAction(t("search_mode_ai"))
        ai_action.triggered.connect(lambda: self.set_mode("ai"))
        
        mode_menu.addSeparator()
        
        url_action = mode_menu.addAction(t("search_mode_url"))
        url_action.triggered.connect(lambda: self.set_mode("url"))
        
        # Show menu with intelligent positioning
        self._show_menu_with_intelligent_position(mode_menu, self.mode_button)

    def on_send_clicked(self):
        """Handle send button click"""
        if self.is_generating:
            # If generating, stop generation
            self.stop_generation()
        else:
            # Normal send
            text = self.input_field.text().strip()
            if text:
                # Check if need to stop current generation (if any)
                if self.is_generating:
                    self.stop_generation()
                
                # If this is the first user input and we're in CHAT_ONLY mode, switch to FULL_CONTENT
                if not self.has_user_input and self.current_state == WindowState.CHAT_ONLY:
                    self.switch_to_full_content()
                
                # Add user message to chat immediately to avoid blank screen
                self.chat_view.add_message(MessageType.USER_QUERY, text)
                    
                self.input_field.clear()
                self.query_submitted.emit(text, self.current_mode)
    
    def toggle_voice_input(self):
        """Toggle voice recording on/off with debouncing and state protection."""
        # Prevent rapid clicks with cooldown
        if self._recording_cooldown_active:
            logger.debug("Voice toggle ignored due to cooldown")
            return
            
        # Prevent operations during cleanup
        if self._cleanup_in_progress:
            logger.debug("Voice toggle ignored due to cleanup in progress")
            return
            
        # Start cooldown period
        self._recording_cooldown_active = True
        self._recording_cooldown.timeout.connect(self._reset_recording_cooldown)
        self._recording_cooldown.start(500)  # 500ms cooldown
        
        if not self.is_voice_recording:
            self.start_voice_recording()
        else:
            self.stop_voice_recording()
    
    def _reset_recording_cooldown(self):
        """Reset the recording cooldown flag."""
        self._recording_cooldown_active = False
        self._recording_cooldown.timeout.disconnect()
    
    def start_voice_recording(self):
        """Start voice recording with comprehensive state validation."""
        # Check if voice recognition is available
        if not is_voice_recognition_available():
            self.chat_view.show_status("Voice recognition not available. Please install vosk and sounddevice.")
            return
        
        # Prevent starting if already recording
        if self.is_voice_recording:
            logger.debug("Recording already in progress, ignoring start request")
            return
            
        # Prevent starting during cleanup
        if self._cleanup_in_progress:
            logger.debug("Cannot start recording: cleanup in progress")
            return
            
        # Ensure no existing thread is running
        if self.voice_thread is not None:
            logger.warning("Existing voice thread detected, stopping before starting new one")
            self._force_stop_voice_thread()
            
        self.is_voice_recording = True
        
        # Initialize voice state - keep existing text and prepare for new input
        self._voice_completed_text = self.input_field.text()  # Keep existing text
        self._voice_current_sentence = ""
        
        # Update UI state
        self.voice_button.setObjectName("voiceBtnActive")
        self.voice_button.setStyleSheet("""
            QPushButton#voiceBtnActive {
                background-color: #7a6ee6;
                border: 2px solid #5c5cb8;
                border-radius: 16px;
            }
            QPushButton#voiceBtnActive:hover {
                background-color: #8a7fee;
            }
        """)
        
        # Update icon to recording state
        import pathlib
        base_path = pathlib.Path(__file__).parent.parent
        mic_icon_path = str(base_path / "assets" / "icons" / "microphone-alt-1-svgrepo-com.svg")
        mic_icon = load_svg_icon(mic_icon_path, color="#ffffff", size=18)
        self.voice_button.setIcon(mic_icon)
        
        # Store original placeholder
        self.original_placeholder = self.input_field.placeholderText()
        self.input_field.setPlaceholderText(t("placeholder_listening"))
        
        # Create and start voice thread with configured audio device
        device_index = self.settings_manager.settings.audio_device_index
        self.voice_thread = VoiceRecognitionThread(device_index=device_index, silence_threshold=2.0)
        self.voice_thread.partial_result.connect(self.on_voice_partial_result)
        self.voice_thread.final_result.connect(self.on_voice_final_result)
        self.voice_thread.error_occurred.connect(self.on_voice_error)
        self.voice_thread.silence_detected.connect(self.on_voice_silence_detected)
        self.voice_thread.start()
    
    def stop_voice_recording(self):
        """Stop voice recording with asynchronous cleanup."""
        if not self.is_voice_recording and not self.voice_thread:
            logger.debug("No recording to stop")
            return
            
        self.is_voice_recording = False
        
        # Immediately update UI state
        self._restore_voice_ui()
        
        # Start asynchronous cleanup
        if self.voice_thread:
            self._cleanup_voice_thread_async()
        
        # Check if auto-send is enabled after stopping recording
        if hasattr(self, 'settings_manager') and self.settings_manager:
            if hasattr(self.settings_manager.settings, 'auto_send_voice_input'):
                if self.settings_manager.settings.auto_send_voice_input:
                    # Auto-send the input after a short delay
                    QTimer.singleShot(200, self._auto_send_voice_input)
    
    def _restore_voice_ui(self):
        """Restore UI to normal state immediately."""
        # Restore UI state
        self.voice_button.setObjectName("voiceBtn")
        self.voice_button.setStyleSheet("")  # Reset to default style
        self.input_field.setPlaceholderText(self.original_placeholder)
        
        # Restore icon to normal state
        import pathlib
        base_path = pathlib.Path(__file__).parent.parent
        mic_icon_path = str(base_path / "assets" / "icons" / "microphone-alt-1-svgrepo-com.svg")
        mic_icon = load_svg_icon(mic_icon_path, color="#111111", size=18)
        self.voice_button.setIcon(mic_icon)
    
    def _cleanup_voice_thread_async(self):
        """Clean up voice thread asynchronously to prevent UI blocking."""
        if self._cleanup_in_progress:
            logger.debug("Cleanup already in progress")
            return
            
        self._cleanup_in_progress = True
        
        # Use QTimer to run cleanup in next event loop iteration
        QTimer.singleShot(0, self._perform_voice_cleanup)
    
    def _perform_voice_cleanup(self):
        """Perform the actual voice thread cleanup."""
        try:
            if self.voice_thread:
                logger.debug("Stopping voice thread")
                self.voice_thread.stop_recording()
                
                # Wait for thread with timeout to prevent infinite blocking
                if not self.voice_thread.wait(3000):  # 3 second timeout
                    logger.warning("Voice thread did not stop gracefully, forcing termination")
                    if self.voice_thread.isRunning():
                        self.voice_thread.terminate()
                        self.voice_thread.wait(1000)  # Wait 1 more second
                        
                self.voice_thread = None
                logger.debug("Voice thread cleanup completed")
        except Exception as e:
            logger.error(f"Error during voice thread cleanup: {e}")
        finally:
            self._cleanup_in_progress = False
    
    def _force_stop_voice_thread(self):
        """Force stop existing voice thread (synchronous for emergency use)."""
        if self.voice_thread:
            try:
                self.voice_thread.stop_recording()
                if not self.voice_thread.wait(1000):  # 1 second timeout
                    self.voice_thread.terminate()
                    self.voice_thread.wait(500)
            except Exception as e:
                logger.error(f"Error force stopping voice thread: {e}")
            finally:
                self.voice_thread = None
    
    def on_voice_partial_result(self, text: str):
        """Handle partial voice recognition results."""
        # Update current sentence and display completed text + current partial
        self._voice_current_sentence = text
        full_text = self._voice_completed_text
        if full_text and text:
            full_text += " " + text
        elif text:
            full_text = text
        self.input_field.setText(full_text)
    
    def on_voice_final_result(self, text: str):
        """Handle final voice recognition results."""
        # Only add the final result if it's different from the current sentence
        # This prevents duplication when partial and final results are the same
        if text and text != self._voice_current_sentence:
            # This is a new sentence, append it
            if self._voice_completed_text:
                self._voice_completed_text += " " + text
            else:
                self._voice_completed_text = text
        elif text:
            # Same as current sentence, just update completed text
            if self._voice_completed_text:
                self._voice_completed_text += " " + text
            else:
                self._voice_completed_text = text
        
        # Clear current sentence and update display
        self._voice_current_sentence = ""
        self.input_field.setText(self._voice_completed_text)
        
        # Check if auto-send is enabled when voice recording stops
        if hasattr(self, 'settings_manager') and self.settings_manager:
            if hasattr(self.settings_manager.settings, 'auto_send_voice_input'):
                if self.settings_manager.settings.auto_send_voice_input and not self.is_voice_recording:
                    # Auto-send the input after a short delay to ensure recording is fully stopped
                    QTimer.singleShot(100, self._auto_send_voice_input)
    
    def _auto_send_voice_input(self):
        """Auto-send voice input if there's content"""
        if self.input_field.text().strip() and not self.is_voice_recording:
            logger.debug("Auto-sending voice input")
            self.on_send_clicked()
    
    def on_voice_silence_detected(self):
        """Handle silence detection - auto-stop recording."""
        logger.info("Silence detected, auto-stopping voice recording")
        
        # Stop recording (this will trigger auto-send if enabled)
        self.stop_voice_recording()
    
    def on_voice_error(self, error_msg: str):
        """Handle voice recognition errors with robust cleanup."""
        logger.error(f"Voice recognition error: {error_msg}")
        
        # Force immediate cleanup on error to prevent resource conflicts
        try:
            self.is_voice_recording = False
            self._restore_voice_ui()
            
            # Force synchronous cleanup on error for immediate resource release
            if self.voice_thread:
                self._force_stop_voice_thread()
        except Exception as e:
            logger.error(f"Error during voice error cleanup: {e}")
        
        # Show error to user
        self.chat_view.show_status(f"Voice error: {error_msg}")
        
        # Reset cleanup state in case it was stuck
        self._cleanup_in_progress = False
    
    def set_generating_state(self, is_generating: bool, streaming_msg=None):
        """Set generation state"""
        self.is_generating = is_generating
        self.streaming_widget = streaming_msg
        
        # Get icon paths
        import pathlib
        base_path = pathlib.Path(__file__).parent.parent.parent.parent
        pause_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "pause-circle-svgrepo-com.svg")
        send_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "arrow-circle-up-svgrepo-com.svg")
        
        if is_generating:
            # Switch to stop mode with pause icon
            pause_icon = load_svg_icon(pause_icon_path, color="#ffffff", size=20)
            self.send_button.setIcon(pause_icon)
            self.send_button.setProperty("stop_mode", "true")
            self.input_field.setPlaceholderText(t("placeholder_stop_generation"))
            self.input_field.setEnabled(False)  # Disable input field
        else:
            # Switch back to send mode with arrow icon
            send_icon = load_svg_icon(send_icon_path, color="#111111", size=20)
            self.send_button.setIcon(send_icon)
            if self.current_mode == "url":
                self.send_button.setText(t("btn_open"))
            else:
                self.send_button.setText("")  # No text, icon only
            self.send_button.setProperty("stop_mode", "false")
            self.input_field.setPlaceholderText(t("placeholder_enter_message") if self.current_mode != "url" else t("placeholder_enter_url"))
            self.input_field.setEnabled(True)  # Enable input field
            
        # Refresh style
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)
        self.send_button.update()
    
    def stop_generation(self):
        """Stop current generation"""
        print("🛑 User requested to stop generation")
        
        try:
            # First restore UI state, avoid user seeing stuck state
            self.set_generating_state(False)
            logger.debug("UI state restored")
            
            # Hide status information
            try:
                self.chat_view.hide_status()
                logger.debug("Status information hidden")
            except Exception as e:
                print(f"⚠️ Error hiding status information: {e}")
            
            # If there is current streaming message, mark as stopped
            if self.streaming_widget:
                try:
                    self.streaming_widget.mark_as_stopped()
                    logger.debug("Streaming message marked as stopped")
                except Exception as e:
                    print(f"⚠️ Error marking streaming message as stopped: {e}")
            
            # Finally emit stop signal, use QTimer.singleShot to avoid possible deadlock
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._emit_stop_signal_safe())
            logger.debug("Stop signal scheduled to be sent")
            
        except Exception as e:
            logger.error(f"Error during stop generation: {e}")
            # Even if error occurs, try to restore UI state
            try:
                self.set_generating_state(False)
            except:
                pass
                
    def _emit_stop_signal_safe(self):
        """Safely emit stop signal"""
        try:
            self.stop_generation_requested.emit()
            logger.debug("Stop signal sent")
        except Exception as e:
            print(f"⚠️ Error sending stop signal: {e}")
    
    def contextMenuEvent(self, event):
        """Handle right-click menu event"""
        menu = QMenu(self)
        
        # Hide to tray
        hide_action = menu.addAction(t("menu_hide_to_tray"))
        hide_action.triggered.connect(self._on_hide_to_tray)
        
        menu.exec(event.globalPos())
        
    def _on_hide_to_tray(self):
        """Handle hide to tray request"""
        self.hide()
        self.visibility_changed.emit(False)
        
    def showEvent(self, event):
        """Handle show event - defer loading non-critical content"""
        super().showEvent(event)
        
        # Adjust focus policy based on auto voice setting
        if hasattr(self, 'settings_manager') and self.settings_manager:
            if self.settings_manager.settings.auto_voice_on_hotkey:
                # When voice input is enabled, prevent auto-focus
                self.input_field.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            else:
                # Normal behavior - allow auto-focus
                self.input_field.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Load shortcuts and history after window is shown
        if not self.shortcuts_loaded:
            self.shortcuts_loaded = True
            # Use QTimer to defer loading to next event loop iteration
            QTimer.singleShot(0, self._load_deferred_content)
            
    def _load_deferred_content(self):
        """Load non-critical content after window is shown"""
        try:
            # Load shortcuts
            logger.debug("Loading shortcuts...")
            start_time = time.time()
            self.load_shortcuts()
            logger.debug(f"Shortcuts loaded in {time.time() - start_time:.2f}s")
            
            # Initialize history manager
            logger.debug("Initializing history manager...")
            start_time = time.time()
            self._ensure_history_manager()
            logger.debug(f"History manager initialized in {time.time() - start_time:.2f}s")
            
            # Load other deferred content
            # Add more deferred loading here if needed
            
        except Exception as e:
            logger.error(f"Error loading deferred content: {e}")
            import traceback
            traceback.print_exc()
        
    def open_settings(self):
        """Open the settings window"""
        try:
            # Emit signal to request settings window from main app
            # This ensures we use the same settings window instance as the tray icon
            logger.info("Requesting settings window from main app")
            self.settings_requested.emit()
        except Exception as e:
            logger.error(f"Failed to request settings window: {e}")
    
    
    def _handle_input_focus(self, event):
        """Handle input field focus event - stop voice recording if active"""
        # Stop voice recording if it's active when user clicks on input field
        if self.is_voice_recording:
            logger.debug("Stopping voice recording due to input field focus")
            self.stop_voice_recording()
        
        # Call the original focusInEvent
        QLineEdit.focusInEvent(self.input_field, event)
    
    def closeEvent(self, event):
        """Handle close event - just hide the window"""
        event.ignore()  # Don't actually close the window
        
        # Stop voice recording if active
        if self.is_voice_recording:
            self.stop_voice_recording()
        
        # Save geometry information and persist to disk
        try:
            self.save_geometry()
            self._persist_geometry_if_needed()
        except Exception:
            pass
            
        self.hide()  # Just hide it
            
        # Notify controller that window is closing
        self.window_closing.emit()
        
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key.Key_Escape:
            # Save geometry before hiding
            try:
                self.save_geometry()
            except Exception:
                pass
            self.hide()  # Hide instead of close
            self.window_closing.emit()  # Show mini window
        elif event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.on_send_clicked()
            
    def changeEvent(self, event):
        """Handle window state changes"""
        if event.type() == event.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                # Window is minimized, save geometry and hide it
                try:
                    self.save_geometry()
                except Exception:
                    pass
                # Hide and show mini window
                QTimer.singleShot(100, lambda: (
                    self.hide(),
                    self.setWindowState(Qt.WindowState.WindowNoState),
                    self.window_closing.emit()
                ))
        super().changeEvent(event)
    
    # Mouse event handlers for drag and resize
    def get_resize_edge(self, pos):
        """Check if mouse position is at window edge, return edge type"""
        # Disable resize detection for CHAT_ONLY mode
        if self.current_state == WindowState.CHAT_ONLY:
            return None
            
        # Use larger margin for WebView mode for better edge detection
        margin = 20 if self.current_state == WindowState.WEBVIEW else 15
        rect = self.rect()
        
        left = pos.x() <= margin
        right = pos.x() >= rect.width() - margin
        top = pos.y() <= margin
        bottom = pos.y() >= rect.height() - margin
        
        if top and left:
            return 'top-left'
        elif top and right:
            return 'top-right'
        elif bottom and left:
            return 'bottom-left'
        elif bottom and right:
            return 'bottom-right'
        elif top:
            return 'top'
        elif bottom:
            return 'bottom'
        elif left:
            return 'left'
        elif right:
            return 'right'
        else:
            return None
    
    def set_resize_cursor(self, edge):
        """Set mouse cursor based on edge type"""
        if edge == 'top' or edge == 'bottom':
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge == 'left' or edge == 'right':
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge == 'top-left' or edge == 'bottom-right':
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge == 'top-right' or edge == 'bottom-left':
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
    def mousePressEvent(self, event):
        """Mouse press event"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            
            # In CHAT_ONLY mode, disable resizing completely
            if self.current_state == WindowState.CHAT_ONLY:
                # Check if clicked on search_input_row (the input field area)
                if hasattr(self, 'input_field') and self.input_field.isVisible():
                    input_field_rect = self.input_field.geometry()
                    # Map to window coordinates
                    input_field_global = self.input_field.mapTo(self, input_field_rect.topLeft())
                    input_field_rect_in_window = QRect(input_field_global, input_field_rect.size())
                    
                    # If clicked outside the input field area, allow dragging
                    if not input_field_rect_in_window.contains(pos):
                        self.dragging = True
                        self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                else:
                    # If input field not visible, allow dragging anywhere
                    self.dragging = True
                    self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            else:
                # For other modes, keep existing behavior
                edge = self.get_resize_edge(pos)
                
                if edge:
                    # Start resizing
                    self.resizing = True
                    self.resize_edge = edge
                    self.resize_start_pos = event.globalPosition().toPoint()
                    self.resize_start_geometry = self.geometry()
                elif hasattr(self, 'title_bar') and self.title_bar.geometry().contains(pos):
                    # Start dragging only if clicked on title bar
                    self.dragging = True
                    self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        """Mouse move event"""
        pos = event.position().toPoint()
        
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.resizing and self.resize_edge:
                # Resize window
                self.resize_window(event.globalPosition().toPoint())
            elif self.dragging:
                # Move window
                self.move(event.globalPosition().toPoint() - self.drag_position)
        else:
            # Check if mouse is at edge, set cursor
            edge = self.get_resize_edge(pos)
            self.set_resize_cursor(edge)
        
        event.accept()
            
    def mouseReleaseEvent(self, event):
        """Mouse release event"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.resizing = False
            self.resize_edge = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
    
    def enterEvent(self, event):
        """Mouse entered window - reset cursor if not on edge"""
        if not self.resizing:
            # Get current mouse position relative to window
            pos = self.mapFromGlobal(QCursor.pos())
            # Only reset cursor if not on a resize edge
            if not self.get_resize_edge(pos):
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Mouse left window - reset cursor"""
        if not self.resizing:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)
    
    def resize_window(self, global_pos):
        """Resize window"""
        if not self.resize_edge:
            return
            
        delta = global_pos - self.resize_start_pos
        geometry = QRect(self.resize_start_geometry)
        
        # Set minimum window size
        min_width = 400
        min_height = 300
        
        # Handle horizontal resize
        if 'left' in self.resize_edge:
            new_width = geometry.width() - delta.x()
            if new_width >= min_width:
                geometry.setLeft(geometry.left() + delta.x())
            else:
                geometry.setLeft(geometry.right() - min_width)
        elif 'right' in self.resize_edge:
            new_width = geometry.width() + delta.x()
            if new_width >= min_width:
                geometry.setWidth(new_width)
            else:
                geometry.setWidth(min_width)
                
        # Handle vertical resize
        if 'top' in self.resize_edge:
            new_height = geometry.height() - delta.y()
            if new_height >= min_height:
                geometry.setTop(geometry.top() + delta.y())
            else:
                geometry.setTop(geometry.bottom() - min_height)
        elif 'bottom' in self.resize_edge:
            new_height = geometry.height() + delta.y()
            if new_height >= min_height:
                geometry.setHeight(new_height)
            else:
                geometry.setHeight(min_height)
        
        self.setGeometry(geometry)