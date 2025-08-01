"""
Unified window system for GameWikiTooltip.
Provides mini assistant and expandable chat window functionality.
"""

import sys
import asyncio
import json
import ctypes
import logging
import re
import time
import os
import pathlib
from datetime import datetime
import threading
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass, field

from src.game_wiki_tooltip.core.i18n import t
from src.game_wiki_tooltip.core.config import WindowGeometryConfig, ChatOnlyGeometry, FullContentGeometry, WebViewGeometry

# Import from ui components module
from .components import (
    convert_markdown_to_html,
    AssistantController,
    WikiView,
    load_svg_icon
)

class WindowState(Enum):
    """Window state enumeration"""
    CHAT_ONLY = "chat_only"      # Only show input box
    FULL_CONTENT = "full_content" # Show all content
    WEBVIEW = "webview"          # WebView2 form

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
    print("Error: PyQt6 is required. PyQt5 is no longer supported.")
    sys.exit(1)

# Try to import BlurWindow
try:
    from BlurWindow.blurWindow import GlobalBlur
    BLUR_WINDOW_AVAILABLE = True
    print("✅ BlurWindow module loaded successfully")
except ImportError:
    print("Warning: BlurWindow module not found, will use default transparency effect")
    BLUR_WINDOW_AVAILABLE = False

# Import graphics compatibility for Windows version detection
from src.game_wiki_tooltip.integration.graphics_compatibility import WindowsGraphicsCompatibility

class QuickAccessPopup(QWidget):
    """Horizontal popup widget for quick access shortcuts"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus |
            Qt.WindowType.Popup  # Add popup flag for auto-close behavior
        )

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("QuickAccessPopup")  # Set object name for the main widget
        self.setStyleSheet("""
                #QuickAccessPopup {
                    background-color: rgb( 0);
                    border-radius: 50px !important;
                    border: 1px ;
                    padding: 0;
                    margin: 0;
                }
            """)

        # Main container
        self.container = QFrame()
        self.container.setObjectName("quickAccessPopup")
        # Container should be transparent since parent has the background
        self.container.setStyleSheet("""
            #quickAccessPopup {
                background-color: rgb(255, 255, 255);
                border-radius: 10px;
                padding: 5px;
                border: none;
                margin: 0;
            }
        """)
        
        # Layout
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.container)
        
        # Shortcuts layout
        self.shortcuts_layout = QHBoxLayout(self.container)
        self.shortcuts_layout.setContentsMargins(10, 5, 10, 5)
        self.shortcuts_layout.setSpacing(0)
        
        # Hide timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)
        
        # Track if mouse is over popup
        self.mouse_over = False
        self.setMouseTracking(True)
        self.container.setMouseTracking(True)
        
    def add_shortcut(self, button: 'ExpandableIconButton'):
        """Add a shortcut button to the popup"""
        self.shortcuts_layout.addWidget(button)
        
    def clear_shortcuts(self):
        """Clear all shortcuts"""
        while self.shortcuts_layout.count() > 0:
            item = self.shortcuts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
    def show_at(self, parent_widget: QWidget):
        """Show popup above the parent widget"""
        # Calculate position
        parent_pos = parent_widget.mapToGlobal(QPoint(0, 0))
        
        # Show first to get correct size
        self.show()
        self.adjustSize()
        
        # Position above parent with left alignment
        x = parent_pos.x()  # Align left edge with parent button
        y = parent_pos.y() - self.height() - 5
        
        # Ensure popup stays within screen bounds
        screen = QApplication.primaryScreen().geometry()
        if x < 0:
            x = 0
        elif x + self.width() > screen.width():
            x = screen.width() - self.width()
            
        if y < 0:
            # Show below if no space above
            y = parent_pos.y() + parent_widget.height() + 5
            
        self.move(x, y)
        
        # Don't auto-hide on hover show
        self.hide_timer.stop()
        
    def enterEvent(self, event):
        """Mouse entered popup"""
        self.mouse_over = True
        self.hide_timer.stop()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """Mouse left popup"""
        self.mouse_over = False
        self.hide_timer.start(500)  # Hide after 500ms
        super().leaveEvent(event)
    
    def eventFilter(self, obj, event):
        """Filter events to detect clicks outside popup"""
        from PyQt6.QtCore import QEvent
        
        # Handle mouse press events
        if event.type() == QEvent.Type.MouseButtonPress:
            # Check if click is outside the popup
            if self.isVisible() and not self.geometry().contains(event.globalPosition().toPoint()):
                # Get the widget at the click position
                click_pos = event.globalPosition().toPoint()
                widget_at_pos = QApplication.widgetAt(click_pos)
                
                # If clicking on a button (history, mode, etc), hide popup but don't consume event
                # This allows the button's click handler to execute
                if widget_at_pos and isinstance(widget_at_pos, QPushButton):
                    self.hide()
                    return False  # Don't consume event, let button handle it
                else:
                    self.hide()
                    return True  # Consume event for other clicks
        
        return super().eventFilter(obj, event)
    
    def showEvent(self, event):
        """Install event filter when showing"""
        super().showEvent(event)
        # Install event filter on application to detect clicks
        QApplication.instance().installEventFilter(self)
    
    def hideEvent(self, event):
        """Remove event filter when hiding"""
        super().hideEvent(event)
        # Remove event filter
        QApplication.instance().removeEventFilter(self)


class ExpandableIconButton(QPushButton):
    """Icon button that expands to show text on hover"""
    
    def __init__(self, icon_path: str, text: str, url: str, name: str = "", parent=None):
        super().__init__(parent)
        self.icon_path = icon_path
        self.full_text = text
        self.url = url
        self.name = name  # Store the website name
        self.expanded = False
        self._animation_callback = None
        self.has_icon = False
        
        # Try to set icon
        try:
            print(f"[ExpandableIconButton] Attempting to load icon from: {icon_path}")
            if icon_path and os.path.exists(icon_path):
                print(f"[ExpandableIconButton] File exists at {icon_path}")
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    print(f"[ExpandableIconButton] Pixmap loaded successfully, size: {pixmap.size()}")
                    self.setIcon(QIcon(pixmap))
                    self.has_icon = True
                    self.setText("")  # Initially show icon only
                else:
                    print(f"[ExpandableIconButton] Failed to load pixmap from {icon_path} - pixmap is null")
            else:
                print(f"[ExpandableIconButton] File does not exist at {icon_path}")
        except Exception as e:
            print(f"[ExpandableIconButton] Exception loading icon {icon_path}: {e}")
        
        # If no icon, show full name
        if not self.has_icon and self.name:
            # Show full name
            self.setText(self.name)
        
        self.setIconSize(QSize(20, 20))
        self.setFixedHeight(28)
        # Adjust minimum width based on content
        if self.has_icon:
            self.setMinimumWidth(28)
        else:
            # Calculate width based on text
            fm = self.fontMetrics()
            text_width = fm.horizontalAdvance(self.name) if hasattr(fm, 'horizontalAdvance') else fm.width(self.name)
            self.setMinimumWidth(text_width + 20)  # Add padding
        
        # Animation for width
        self.animation = QPropertyAnimation(self, b"minimumWidth")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Styling
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 14px;
                padding: 0 8px;
                font-size: 13px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """)
        
    def enterEvent(self, event):
        """Expand to show text on hover"""
        if not self.expanded:
            self.expanded = True
            # Stop any ongoing animation
            self.animation.stop()
            # Disconnect any existing connections
            try:
                self.animation.finished.disconnect()
            except:
                pass
            
            # Show full text with or without icon
            if self.has_icon:
                self.setText(f"  {self.full_text}")
            else:
                self.setText(self.full_text)
            
            self.animation.setStartValue(self.minimumWidth())
            self.animation.setEndValue(140)
            self.animation.start()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """Collapse to show icon only"""
        if self.expanded:
            self.expanded = False
            # Stop any ongoing animation
            self.animation.stop()
            # Disconnect any existing connections
            try:
                self.animation.finished.disconnect()
            except:
                pass
            
            # Create callback function
            def clear_text():
                if not self.expanded:  # Double check we're still collapsed
                    if self.has_icon:
                        self.setText("")
                    else:
                        # Show full name for non-icon buttons
                        self.setText(self.name)
            
            # Connect new callback
            self.animation.finished.connect(clear_text)
            self.animation.setStartValue(self.minimumWidth())
            self.animation.setEndValue(28)
            self.animation.start()
        super().leaveEvent(event)


class WindowMode(Enum):
    """Window display modes"""
    CHAT = "chat"
    WIKI = "wiki"


class MessageType(Enum):
    """Chat message types"""
    USER_QUERY = "user_query"
    AI_RESPONSE = "ai_response"
    AI_STREAMING = "ai_streaming"
    WIKI_LINK = "wiki_link"
    TRANSITION = "transition"


@dataclass
class ChatMessage:
    """Single chat message"""
    type: MessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# To allow class attributes to dynamically return translations, we use a metaclass
class TransitionMessagesMeta(type):
    """Metaclass for dynamically handling TransitionMessages attribute access"""
    
    def __getattribute__(cls, name):
        # Map old attribute names to new translation keys
        attribute_mapping = {
            'WIKI_SEARCHING': 'status_wiki_searching',
            'WIKI_FOUND': 'status_wiki_found', 
            'GUIDE_SEARCHING': 'status_guide_searching',
            'GUIDE_GENERATING': 'status_guide_generating',
            'ERROR_NOT_FOUND': 'status_error_not_found',
            'ERROR_TIMEOUT': 'status_error_timeout',
            'QUERY_RECEIVED': 'status_query_received',
            'DB_SEARCHING': 'status_db_searching',
            'AI_SUMMARIZING': 'status_ai_summarizing',
            'COMPLETED': 'status_completed'
        }
        
        if name in attribute_mapping:
            return t(attribute_mapping[name])
        
        # For other attributes, use default behavior
        return super().__getattribute__(name)

class TransitionMessages(metaclass=TransitionMessagesMeta):
    """Predefined transition messages with i18n support"""
    
    def __new__(cls):
        # Prevent instantiation, this class should only be used for static access
        raise TypeError(f"{cls.__name__} should not be instantiated")
    
    # Static method versions for use when needed
    @staticmethod
    def get_wiki_searching():
        return t("status_wiki_searching")
    
    @staticmethod 
    def get_wiki_found():
        return t("status_wiki_found")
    
    @staticmethod
    def get_guide_searching():
        return t("status_guide_searching")
    
    @staticmethod
    def get_guide_generating():
        return t("status_guide_generating")
    
    @staticmethod
    def get_error_not_found():
        return t("status_error_not_found")
    
    @staticmethod
    def get_error_timeout():
        return t("status_error_timeout")
    
    @staticmethod
    def get_query_received():
        return t("status_query_received")
    
    @staticmethod
    def get_db_searching():
        return t("status_db_searching")
    
    @staticmethod
    def get_ai_summarizing():
        return t("status_ai_summarizing")
    
    @staticmethod
    def get_completed():
        return t("status_completed")


def detect_markdown_content(text: str) -> bool:
    """
    Detect if text contains markdown format or HTML format
    
    Args:
        text: Text to detect
        
    Returns:
        True if text contains markdown or HTML format, False otherwise
    """
    if not text:
        return False
        
    # Detect common markdown patterns
    markdown_patterns = [
        r'\*\*.*?\*\*',  # Bold **text**
        r'\*.*?\*',      # Italic *text*
        r'#{1,6}\s',     # Headers # ## ### etc.
        r'^\s*[-\*\+]\s', # Unordered lists
        r'^\s*\d+\.\s',  # Ordered lists
        r'`.*?`',        # Inline code
        r'```.*?```',    # Code blocks
        r'\[.*?\]\(.*?\)', # Links [text](url)
    ]
    
    # Detect HTML tags (especially those used in video sources)
    html_patterns = [
        r'<small.*?>.*?</small>',  # <small> tags
        r'<a\s+.*?href.*?>.*?</a>', # <a> link tags
        r'<[^>]+>',  # Other HTML tags
        r'📺\s*\*\*info source：\*\*',  # Video source title
        r'---\s*\n\s*<small>',  # Markdown separator + HTML
        r'\n\n<small>.*?来源.*?</small>',  # Generic source pattern
        r'<br\s*/?>',  # <br> tags
        r'<strong>.*?</strong>',  # <strong> tags
        r'<em>.*?</em>',  # <em> tags
        r'<code>.*?</code>',  # <code> tags
        r'<pre>.*?</pre>',  # <pre> tags
    ]
    
    # Check markdown patterns
    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE | re.DOTALL):
            return True
    
    # Check HTML patterns        
    for pattern in html_patterns:
        if re.search(pattern, text, re.MULTILINE | re.DOTALL):
            return True
            
    return False




class StatusMessageWidget(QFrame):
    """Message component specifically for displaying status information"""
    
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.current_message = message
        
        # Initialize animation properties (must be before init_ui as update_display is called in init_ui)
        self.animation_dots = 0
        
        self.init_ui()
        
        # Animation timer
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_timer.start(500)  # Update animation every 500ms
        
    def init_ui(self):
        """Initialize status message UI"""
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create status bubble
        bubble = QFrame()
        bubble.setObjectName("statusBubble")
        bubble.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        
        # Status text label
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum
        )
        
        # Set status style
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                line-height: 1.5;
                font-family: "Segoe UI", "Microsoft YaHei", Arial;
                background-color: transparent;
                border: none;
                padding: 0;
                color: #666;
                font-style: italic;
            }
        """)
        
        # Set bubble style
        bubble.setStyleSheet("""
            QFrame#statusBubble {
                background-color: rgba(240, 248, 255, 200);
                border: 1px solid rgba(224, 232, 240, 150);
                border-radius: 18px;
                padding: 4px;
            }
        """)
        
        bubble_layout.addWidget(self.status_label)
        layout.addWidget(bubble)
        layout.addStretch()
        
        # Override context menu for proper styling
        self.status_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_label.customContextMenuRequested.connect(self._show_context_menu)
        
        self.update_display()
        
    def update_status(self, new_message: str):
        """Update status information"""
        self.current_message = new_message
        self.animation_dots = 0  # Reset animation
        self.update_display()
        # Ensure animation continues running
        if not self.animation_timer.isActive():
            self.animation_timer.start(500)
        
    def update_animation(self):
        """Update animation effect"""
        self.animation_dots = (self.animation_dots + 1) % 4
        self.update_display()
        
    def update_display(self):
        """Update display content"""
        dots = "." * self.animation_dots
        display_text = f"{self.current_message}{dots}"
        self.status_label.setText(display_text)
        self.status_label.adjustSize()
        self.adjustSize()
        
        # Ensure parent container also updates layout
        if self.parent():
            self.parent().adjustSize()
        
    def stop_animation(self):
        """Stop animation"""
        if self.animation_timer.isActive():
            self.animation_timer.stop()
            
    def hide_with_fadeout(self):
        """Hide with fade out"""
        self.stop_animation()
        # Simple hide, can add fade out animation later
        self.hide()
    
    def _show_context_menu(self, pos):
        """Show custom context menu for the label"""
        # Create a new menu instead of using createStandardContextMenu
        menu = QMenu(self)
        
        # Add standard actions manually
        if self.status_label.selectedText():
            copy_action = menu.addAction("Copy")
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(self.status_label.selectedText())
            )
        
        # Show the menu
        global_pos = self.status_label.mapToGlobal(pos)
        menu.exec(global_pos)


class MessageWidget(QFrame):
    """Individual chat message widget"""
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(parent)
        self.message = message
        self.init_ui()
        
    def init_ui(self):
        """Initialize the message UI"""
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,  # 改为Expanding以占满可用width
            QSizePolicy.Policy.Minimum
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create message bubble
        bubble = QFrame()
        bubble.setObjectName("messageBubble")
        bubble.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        # Set the maximum width to 80% of the parent container to leave margins
        bubble.setMaximumWidth(9999)  # Set a large value initially, will be dynamically adjusted later
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        
        # Use QLabel for better auto-sizing
        self.content_label = QLabel()
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.content_label.setOpenExternalLinks(False)
        self.content_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum
        )
        
        # Set content based on message type
        if self.message.type == MessageType.WIKI_LINK:
            url = self.message.metadata.get('url', '')
            html_content = (
                f'[LINK] <a href="{url}" style="color: #4096ff;">{url}</a><br/>'
                f'<span style="color: #666; margin-left: 20px;">{self.message.content}</span>'
            )
            self.content_label.setText(html_content)
            self.content_label.setTextFormat(Qt.TextFormat.RichText)
        elif self.message.type == MessageType.AI_RESPONSE:
            # AI response may contain markdown format, need to detect and convert
            if detect_markdown_content(self.message.content):
                # Convert markdown to HTML
                html_content = convert_markdown_to_html(self.message.content)
                self.content_label.setText(html_content)
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
                # AI response may contain links, need to connect linkActivated signal
                self.content_label.setOpenExternalLinks(False)  # Ensure using signal processing
                self.content_label.linkActivated.connect(self.on_link_clicked)
            else:
                # Plain text
                self.content_label.setText(self.message.content)
                self.content_label.setTextFormat(Qt.TextFormat.PlainText)
        else:
            self.content_label.setText(self.message.content)
            self.content_label.setTextFormat(Qt.TextFormat.PlainText)
            
        # Style the label based on message type
        if self.message.type == MessageType.USER_QUERY:
            self.content_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    line-height: 1.5;
                    font-family: "Segoe UI", "Microsoft YaHei", Arial;
                    background-color: transparent;
                    border: none;
                    padding: 0;
                    color: white;
                }
            """)
        else:
            self.content_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    line-height: 1.5;
                    font-family: "Segoe UI", "Microsoft YaHei", Arial;
                    background-color: transparent;
                    border: none;
                    padding: 0;
                    color: #333;
                }
            """)
        
        # Style based on message type
        if self.message.type == MessageType.USER_QUERY:
            # Right-aligned user message
            layout.addStretch()
            bubble.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: rgba(64, 150, 255, 220);
                    border-radius: 18px;
                    color: white;
                    padding: 4px;
                    border: 1px solid rgba(64, 150, 255, 100);
                }
            """)
            # Style is already set above for QTextEdit
        else:
            # Left-aligned AI/system message
            # Wiki link handling is done above in content setting
            
            bubble.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: rgba(255, 255, 255, 200);
                    border-radius: 18px;
                    padding: 4px;
                    border: 1px solid rgba(224, 224, 224, 150);
                }
            """)
            layout.addWidget(bubble)
            layout.addStretch()
            
        bubble_layout.addWidget(self.content_label)
        
        # Override context menu for proper styling
        self.content_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.content_label.customContextMenuRequested.connect(self._show_context_menu)
        
        if self.message.type == MessageType.USER_QUERY:
            layout.addWidget(bubble)
            
        # Handle link clicks for wiki messages
        if self.message.type == MessageType.WIKI_LINK:
            self.content_label.linkActivated.connect(self.on_link_clicked)
            
        # Set initial width
        self._set_initial_width()
            
    def _set_initial_width(self):
        """Set initial width of message, based on parent container"""
        # This method will be overridden by _update_message_width method after adding to chat view
        # But can provide a reasonable initial value
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            bubble.setMaximumWidth(500)  # Set a reasonable initial maximum width
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            
    def on_link_clicked(self, url):
        """Handle wiki link clicks"""
        logger = logging.getLogger(__name__)
        print(f"🔗 [LINK-DEBUG] Link clicked: {url}")
        print(f"🔗 [LINK-DEBUG] Message type: {self.message.type}")
        print(f"🔗 [LINK-DEBUG] Is streaming message: {isinstance(self, StreamingMessageWidget)}")
        print(f"🔗 [LINK-DEBUG] content_label format: {self.content_label.textFormat()}")
        print(f"🔗 [LINK-DEBUG] openExternalLinks: {self.content_label.openExternalLinks()}")
        
        logger.info(f"🔗 WikiLink clicked: {url}")
        logger.info(f"Message content: {self.message.content}")
        logger.info(f"Message metadata: {self.message.metadata}")
        
        # Optimize title passing: use message content first, if empty then extract from URL
        title = self.message.content
        if not title or title.strip() == "":
            # If no title, extract from URL
            try:
                from urllib.parse import unquote
                title = unquote(url.split('/')[-1]).replace('_', ' ')
            except:
                title = "Wiki页面"
        
        logger.info(f"Using title: {title}")
        print(f"🔗 [LINK-DEBUG] Using title: {title}")
        
        # Find ChatView instance upwards
        chat_view = self._find_chat_view()
        if chat_view:
            logger.info(f"Found ChatView instance, calling show Wiki page")
            print(f"🔗 [LINK-DEBUG] Found ChatView instance, calling show Wiki page")
            chat_view.show_wiki(url, title)
        else:
            logger.warning(f"ChatView instance not found")
            print(f"🔗 [LINK-DEBUG] ❌ ChatView instance not found")
            
    def _find_chat_view(self):
        """Find ChatView instance upwards"""
        parent = self.parent()
        while parent:
            if isinstance(parent, ChatView):
                return parent
            parent = parent.parent()
        return None
        
    def update_content(self, new_content: str):
        """Update message content"""
        self.message.content = new_content
        
        # If AI response, detect and convert markdown
        if self.message.type == MessageType.AI_RESPONSE:
            if detect_markdown_content(new_content):
                html_content = convert_markdown_to_html(new_content)
                self.content_label.setText(html_content)
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
            else:
                self.content_label.setText(new_content)
                self.content_label.setTextFormat(Qt.TextFormat.PlainText)
        else:
            self.content_label.setText(new_content)
            
        self.content_label.adjustSize()
        self.adjustSize()
    
    def _show_context_menu(self, pos):
        """Show custom context menu for the label"""
        # Create a new menu instead of using createStandardContextMenu
        menu = QMenu(self)
        
        # Add standard actions manually
        if self.content_label.selectedText():
            copy_action = menu.addAction("Copy")
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(self.content_label.selectedText())
            )
        
        # Show the menu
        global_pos = self.content_label.mapToGlobal(pos)
        menu.exec(global_pos)

class StreamingMessageWidget(MessageWidget):
    """Message widget with streaming/typing animation support"""
    
    # Add signal
    streaming_finished = pyqtSignal()  # Signal for streaming completion
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(message, parent)
        self.full_text = ""
        self.display_index = 0
        self.is_stopped = False  # Flag indicating if stopped by user
        
        # Markdown rendering control - ensure re-initialization each time
        self.last_render_index = 0  # Last render character position
        self.render_interval = 50   # Render markdown every 50 characters (reduce frequency to avoid flickering)
        self.last_render_time = 0   # Last render time
        self.render_time_interval = 1.0  # Maximum 1.0 second between renders
        self.is_markdown_detected = False  # Cache markdown detection result - force reset
        self.current_format = Qt.TextFormat.PlainText  # Current text format - force reset
        self.link_signal_connected = False  # Track if linkActivated signal is connected - force reset
        self.has_video_source = False  # Track if video source has been detected - force reset
        self.force_render_count = 0  # Force render counter
        
        # Optimize streaming message layout to prevent flickering
        self._optimize_for_streaming()
        
        # Set default render parameters (more sensitive detection)
        self.set_render_params(char_interval=50, time_interval=1.0)
        
        # Typing animation timer
        self.typing_timer = QTimer()
        self.typing_timer.timeout.connect(self.show_next_char)
        # Ensure timer is stopped during initialization
        self.typing_timer.stop()
        
        # Loading dots animation
        self.dots_timer = QTimer()
        self.dots_count = 0
        self.dots_timer.timeout.connect(self.update_dots)
        self.dots_timer.start(500)
        
        # Add debug logs
        print(f"🔧 [STREAMING] New StreamingMessageWidget initialization completed, timer status: {'Active' if self.typing_timer.isActive() else 'Inactive'}")
        
        # Configure link handling during initialization
        if hasattr(self, 'content_label'):
            self.content_label.setOpenExternalLinks(False)  # Ensure signal handling instead of direct opening
            # Pre-connect linkActivated signal to avoid connection issues during streaming
            try:
                self.content_label.linkActivated.connect(self.on_link_clicked)
                self.link_signal_connected = True
                print(f"🔗 [STREAMING] linkActivated signal already connected during initialization")
            except Exception as e:
                print(f"⚠️ [STREAMING] Failed to connect linkActivated signal during initialization: {e}")
                self.link_signal_connected = False
    
    def _optimize_for_streaming(self):
        """Optimize streaming message layout to prevent flickering"""
        # Find message bubble
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            # Use Minimum policy to only take required height
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        
        # Optimize content_label settings
        if hasattr(self, 'content_label'):
            # Use Minimum policy to only take required height
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            # Set text wrapping
            self.content_label.setWordWrap(True)
            self.content_label.setScaledContents(False)
            
        # Initial width setup (based on parent container)
        self._update_bubble_width()
        
        # Fix initial width for streaming messages to avoid layout jumping
        self._fix_width_for_streaming()
    
    def _update_bubble_width(self):
        """Dynamically set dialog width based on chat window width"""
        # Get chat view width, considering scrollbar width
        parent_widget = self.parent()
        
        # Try to use get_chat_view, but may not be available during initialization
        if hasattr(self, 'get_chat_view'):
            chat_view = self.get_chat_view()
        else:
            chat_view = parent_widget if parent_widget and hasattr(parent_widget, 'viewport') else None
            
        if chat_view and hasattr(chat_view, 'viewport'):
            viewport_width = chat_view.viewport().width()
            # Subtract scrollbar width (usually about 20px)
            if hasattr(chat_view, 'verticalScrollBar'):
                scrollbar = chat_view.verticalScrollBar()
                if scrollbar and scrollbar.isVisible():
                    viewport_width -= scrollbar.width()
        else:
            # If unable to get chat view width, try to get from parent container
            viewport_width = parent_widget.width() if parent_widget else 500
        
        # Ensure valid width
        viewport_width = max(300, viewport_width)
        
        # Calculate dialog width (75% of chat view width, reduce ratio to avoid too wide, but not exceed 600px, not less than 300px)
        bubble_width = max(300, min(600, int(viewport_width * 0.75)))
        content_width = bubble_width - 24  # Subtract margins
        
        # Save calculated width for later use
        self._calculated_bubble_width = bubble_width
        self._calculated_content_width = content_width
        
        # Update bubble and content width - use maximum width instead of fixed width
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            bubble.setMaximumWidth(bubble_width)
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            
        if hasattr(self, 'content_label'):
            self.content_label.setMaximumWidth(content_width)
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            
        # Only output debug information in abnormal cases
        if chat_view and hasattr(chat_view, 'viewport'):
            original_viewport_width = chat_view.viewport().width()
            # Only output warning when width is abnormally small
            if original_viewport_width < 400:
                print(f"⚠️ Streaming message view width abnormal: viewport={original_viewport_width}px")
    
    def _fix_width_for_streaming(self):
        """Fix width for streaming messages to avoid layout jumping"""
        if not hasattr(self, '_calculated_bubble_width'):
            return
            
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            # Use fixed width instead of maximum width
            bubble.setFixedWidth(self._calculated_bubble_width)
            print(f"🔒 [STREAMING] Fixed bubble width: {self._calculated_bubble_width}px")
            
        if hasattr(self, 'content_label'):
            # Content label also uses fixed width
            self.content_label.setFixedWidth(self._calculated_content_width)
            # Set minimum height to avoid vertical jumping
            self.content_label.setMinimumHeight(30)
            print(f"🔒 [STREAMING] Fixed content width: {self._calculated_content_width}px")
            
        # Mark width as fixed
        self._width_fixed = True
    
    def _restore_flexible_width(self):
        """Restore flexible width settings (called after streaming ends)"""
        if not hasattr(self, '_width_fixed') or not self._width_fixed:
            return
            
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble and hasattr(self, '_calculated_bubble_width'):
            # Remove fixed width, restore maximum width limit
            bubble.setMinimumWidth(0)
            bubble.setMaximumWidth(self._calculated_bubble_width)
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            print(f"🔓 [STREAMING] Restored bubble flexible width, max: {self._calculated_bubble_width}px")
            
        if hasattr(self, 'content_label') and hasattr(self, '_calculated_content_width'):
            # Remove fixed width, restore maximum width limit
            self.content_label.setMinimumWidth(0)
            self.content_label.setMaximumWidth(self._calculated_content_width)
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            print(f"🔓 [STREAMING] Restored content flexible width, max: {self._calculated_content_width}px")
            
        # Mark flexible width as restored
        self._width_fixed = False
        
    def get_chat_view(self):
        """Get parent ChatView (if exists)"""
        try:
            parent = self.parent()
            # Check if parent is ChatView (by checking specific methods)
            if parent and hasattr(parent, 'verticalScrollBar'):
                return parent
        except:
            pass
        return None
    
    def set_render_params(self, char_interval: int = 50, time_interval: float = 1.0):
        """
        Set markdown rendering parameters
        
        Args:
            char_interval: Character interval, how many characters between renders
            time_interval: Time interval, maximum seconds between renders
        """
        self.render_interval = max(20, char_interval)  # Minimum 20 characters
        self.render_time_interval = max(0.5, time_interval)  # Minimum 0.5 seconds
        
    def append_chunk(self, chunk: str):
        """Append text chunk for streaming display"""
        # Stricter stop check, return without processing
        if self.is_stopped:
            print(f"🛑 Streaming message stopped, rejecting new content chunk: '{chunk[:50]}...'")
            return
        
        # Record timer status for debugging
        timer_was_active = self.typing_timer.isActive()
        
        self.full_text += chunk
        print(f"✅ [STREAMING-WIDGET] Full text updated, new length: {len(self.full_text)}")
        
        # Improved initial detection logic:
        # 1. Remove timer check restriction, ensure each new message can perform initial detection
        # 2. Lower length limit, detect markdown early
        if not timer_was_active:
            self.dots_timer.stop()
            # Initialize render timestamp
            self.last_render_time = time.time()
            
        # Perform markdown detection for each new chunk (not just the first one)
        # Use cache to avoid repeated detection of same content
        if not self.is_markdown_detected and len(self.full_text) > 5:  # Lower length limit
            self.is_markdown_detected = detect_markdown_content(self.full_text)
            # If markdown is detected, perform initial render immediately
            if self.is_markdown_detected:
                print(f"🔍 [STREAMING] Initially detected markdown format, length: {len(self.full_text)}")
                print(f"📋 [STREAMING] Timer status: {'Active' if timer_was_active else 'Inactive'}")
                print(f"📝 [STREAMING] First 50 characters: {self.full_text[:50]}...")
                # Set correct format immediately
                self.current_format = Qt.TextFormat.RichText
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
                
        # Ensure timer starts
        if not self.typing_timer.isActive():
            print(f"⏰ [STREAMING-WIDGET] Started typewriter timer")
            # Faster typewriter effect: 2ms per character (previously 5ms)
            self.typing_timer.start(2)
        else:
            print(f"⏰ [STREAMING-WIDGET] Typewriter timer already running")
    
    def _adjust_typing_speed(self):
        """Dynamically adjust typewriter speed"""
        remaining_chars = len(self.full_text) - self.display_index
        
        # If many remaining characters, speed up display
        if remaining_chars > 500:
            # Large amount of remaining content, very fast speed
            new_interval = 1
        elif remaining_chars > 200:
            # Medium remaining content, fast speed
            new_interval = 1
        elif remaining_chars > 50:
            # Small amount of remaining content, normal speed
            new_interval = 2
        else:
            # Very little remaining content, normal speed to maintain typewriter effect
            new_interval = 2
            
        # Check if timer interval needs adjustment
        if self.typing_timer.isActive():
            current_interval = self.typing_timer.interval()
            if current_interval != new_interval:
                print(f"🚀 [TYPING] Adjusted typing speed: {current_interval}ms -> {new_interval}ms, Remaining: {remaining_chars}characters")
                self.typing_timer.setInterval(new_interval)
    
    def mark_as_stopped(self):
        """Mark as stopped"""
        self.is_stopped = True
        self.typing_timer.stop()
        self.dots_timer.stop()
        
        # Add stop marker at current position
        if self.display_index < len(self.full_text):
            stopped_text = self.full_text[:self.display_index] + "\n\n*[Generation stopped by user]*"
        else:
            stopped_text = self.full_text + "\n\n*[Generation stopped by user]*"
            
        # Immediately display all generated text plus stop marker
        self.content_label.setText(stopped_text)
        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
        
        # Convert Message type to AI_RESPONSE
        self.message.type = MessageType.AI_RESPONSE
        
        print(f"🛑 Streaming message stopped, display position: {self.display_index}/{len(self.full_text)}")
            
    def show_next_char(self):
        """Show next character in typing animation"""
        
        # First check if it has been stopped
        if self.is_stopped:
            self.typing_timer.stop()
            print(f"🛑 Typewriter effect detected stop state, immediately terminating")
            return
            
        # Dynamically adjusted typing speed (based on remaining characters)
        self._adjust_typing_speed()
            
        if self.display_index < len(self.full_text):
            # Show multiple characters at once for faster display
            batch_size = 3  # Show 3 characters at a time
            self.display_index = min(self.display_index + batch_size, len(self.full_text))
            display_text = self.full_text[:self.display_index]
            current_time = time.time()
            
            # Early markdown detection (start detecting at the first 20 characters)
            if self.display_index <= 20 and not self.is_markdown_detected and len(self.full_text) > 5:
                if detect_markdown_content(self.full_text):
                    self.is_markdown_detected = True
                    self.current_format = Qt.TextFormat.RichText
                    self.content_label.setTextFormat(Qt.TextFormat.RichText)
                    print(f"🚀 [STREAMING] Early detected markdown format（{self.display_index}characters），Full text length: {len(self.full_text)}")
            
            # Check if it needs to perform staged markdown rendering
            should_render = False
            
            # Add update buffer check - reduce frequent DOM operations
            should_update_display = False
            
            # Buffer condition 1: Update display every 5 characters (reduce update frequency)
            # But the first 10 characters are immediately displayed, ensuring the user sees the content start
            if self.display_index <= 10 or self.display_index % 5 == 0:
                should_update_display = True
            
            # Buffer condition 2: Encounter line breaks or paragraph ends
            elif display_text and display_text[-1] in ['\n', '.', '。', '!', '！', '?', '？']:
                should_update_display = True
            
            # Buffer condition 3: Must update when characters interval is reached
            if self.display_index - self.last_render_index >= self.render_interval:
                should_render = True
                should_update_display = True
            
            # Condition 2: Time interval reached
            elif current_time - self.last_render_time >= self.render_time_interval:
                should_render = True
                should_update_display = True
            
            # Condition 3: Detect key content boundaries (e.g., video sources start)
            elif not self.has_video_source and ('📺' in display_text[-10:] or 
                  '---\n<small>' in display_text[-20:] or
                  '<small>' in display_text[-10:]):
                should_render = True
                should_update_display = True
                self.has_video_source = True  # Mark as detected video source, avoid duplicate printing
                print(f"🎬 [STREAMING] Detected video source content, triggering render")
            
            # Condition 4: Detect markdown format content (new condition, ensure format content can be rendered)
            elif not self.is_markdown_detected and len(display_text) > 5 and detect_markdown_content(display_text):
                should_render = True
                should_update_display = True
                self.is_markdown_detected = True
                print(f"🔄 [STREAMING] Detected format content, triggering render, current length: {len(display_text)}")
                print(f"📝 [STREAMING] First 50 characters: {display_text[:50]}...")
                # Immediately set the correct format
                self.current_format = Qt.TextFormat.RichText
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
            
            # Condition 5: If markdown is detected, but the current text has no format, re-detect (handle format changes)
            elif self.is_markdown_detected and not detect_markdown_content(display_text):
                # Re-detect the entire text to avoid misjudgment
                if detect_markdown_content(self.full_text):
                    should_render = True
                    print(f"🔄 [STREAMING] Re-detected format content, triggering render")
                else:
                    # If there is no format, reset the state
                    self.is_markdown_detected = False
                    self.current_format = Qt.TextFormat.PlainText
                    print(f"🔄 [STREAMING] Reset to plain text format")
            
            # Condition 6: Force detect format every 100 characters (new, ensure no format content is missed)
            elif self.display_index % 100 == 0 and self.display_index > 0:
                if detect_markdown_content(display_text) and not self.is_markdown_detected:
                    should_render = True
                    self.is_markdown_detected = True
                    print(f"🔄 [STREAMING] Force detected format content, triggering render, position: {self.display_index}")
            
            # Condition 7: If markdown is detected but not yet rendered, force render (new)
            elif self.is_markdown_detected and self.current_format == Qt.TextFormat.PlainText:
                should_render = True
                print(f"🔄 [STREAMING] Force render detected markdown content, position: {self.display_index}")
            
            # Perform rendering processing
            if should_render and self.message.type == MessageType.AI_STREAMING:
                # Re-detect content format (supports dynamic changes, such as adding HTML video sources)
                current_has_format = detect_markdown_content(display_text)
                
                # Perform staged rendering
                if self.is_markdown_detected or current_has_format:
                    html_content = convert_markdown_to_html(display_text)
                    # Only set format when the format actually changes to avoid flickering
                    if self.current_format != Qt.TextFormat.RichText:
                        self.content_label.setTextFormat(Qt.TextFormat.RichText)
                        self.current_format = Qt.TextFormat.RichText
                        print(f"📝 [STREAMING] Switched to RichText format, content length: {len(display_text)}")
                    self.content_label.setText(html_content)
                    
                    # If the linkActivated signal is not yet connected, connect it now
                    if not self.link_signal_connected:
                        self.content_label.linkActivated.connect(self.on_link_clicked)
                        self.link_signal_connected = True
                        print(f"🔗 [STREAMING] linkActivated signal connected")
                        print(f"🔗 [STREAMING] Current content contains links: {'<a href' in html_content}")
                        
                    # Ensure the content label enables link opening
                    self.content_label.setOpenExternalLinks(False)  # Ensure signal processing instead of direct opening
                    print(f"🔗 [STREAMING] Content label config - OpenExternalLinks: {self.content_label.openExternalLinks()}")
                    print(f"🔗 [STREAMING] Content label format: {self.content_label.textFormat()}")
                    
                    # Ensure state consistency
                    self.is_markdown_detected = True
                else:
                    # Only set format when the format actually changes to avoid flickering
                    if self.current_format != Qt.TextFormat.PlainText:
                        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                        self.current_format = Qt.TextFormat.PlainText
                        print(f"📝 [STREAMING] Switched to PlainText format, content length: {len(display_text)}")
                    self.content_label.setText(display_text)
                    
                    # Ensure state consistency
                    self.is_markdown_detected = False
                
                # Update rendering state
                self.last_render_index = self.display_index
                self.last_render_time = current_time
            elif should_update_display:
                # Only update display, not perform full render
                # Use setUpdatesEnabled to reduce flickering
                self.content_label.setUpdatesEnabled(False)
                
                if self.is_markdown_detected:
                    # If markdown/HTML is detected, continue using HTML format
                    html_content = convert_markdown_to_html(display_text)
                    self.content_label.setText(html_content)
                    # Ensure format is set correctly
                    if self.current_format != Qt.TextFormat.RichText:
                        self.content_label.setTextFormat(Qt.TextFormat.RichText)
                        self.current_format = Qt.TextFormat.RichText
                else:
                    # Otherwise use plain text
                    self.content_label.setText(display_text)
                    # Ensure format is set correctly
                    if self.current_format != Qt.TextFormat.PlainText:
                        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                        self.current_format = Qt.TextFormat.PlainText
                
                # Restore updates
                self.content_label.setUpdatesEnabled(True)
            # If neither rendering nor display update is needed, but this is the first 5 characters, force at least one display
            elif self.display_index <= 5:
                print(f"🚀 [DISPLAY] 强制显示前5个characters: display_index={self.display_index}")
                should_update_display = True
                if self.is_markdown_detected:
                    html_content = convert_markdown_to_html(display_text)
                    self.content_label.setText(html_content)
                else:
                    self.content_label.setText(display_text)
                
            # Only scroll when needed (reduce scrolling calls)
            if should_update_display:
                chat_view = self.get_chat_view()
        else:
            self.typing_timer.stop()
            
            # When finally completed, convert Message type and perform final render
            if self.message.type == MessageType.AI_STREAMING and self.full_text and not self.is_stopped:
                # Convert Message type to AI_RESPONSE, indicating streaming output is complete
                self.message.type = MessageType.AI_RESPONSE
                
                # Output completion information
                has_video_sources = any(pattern in self.full_text for pattern in [
                    '📺 **info source：**', 
                    '---\n<small>', 
                    '<small>.*?来源.*?</small>'
                ])
                print(f"🎬 [STREAMING] Streaming message completed, length: {len(self.full_text)} characters，Contains video sources: {has_video_sources}")
                
                # Emit completion signal
                self.streaming_finished.emit()
                
                # Perform final format detection and conversion - force re-detection, ignore Cache status
                final_has_format = detect_markdown_content(self.full_text)
                final_has_video_sources = has_video_sources
                
                # If markdown was not detected before, but detected finally, update immediately
                if not self.is_markdown_detected and final_has_format:
                    self.is_markdown_detected = True
                    self.current_format = Qt.TextFormat.RichText
                    print(f"⚡ [STREAMING] Finally detected markdown format, force update render")
                
                print(f"🔄 [STREAMING] Final format detection: markdown={final_has_format}, video={final_has_video_sources}, Cache status={self.is_markdown_detected}")
                
                # Ensure final render uses correct format - based on actual detection results, not Cache status
                if final_has_format or final_has_video_sources:
                    html_content = convert_markdown_to_html(self.full_text)
                    self.content_label.setText(html_content)
                    self.content_label.setTextFormat(Qt.TextFormat.RichText)
                    self.current_format = Qt.TextFormat.RichText
                    self.is_markdown_detected = True  # Update state to match detection result
                    
                    # After streaming output is complete, ensure linkActivated signal is connected (avoid duplicate connections)
                    if not self.link_signal_connected:
                        self.content_label.linkActivated.connect(self.on_link_clicked)
                        self.link_signal_connected = True
                        print(f"🔗 [STREAMING] Connect linkActivated signal during final render")
                        
                    # Ensure content label configuration is correct
                    self.content_label.setOpenExternalLinks(False)  # Ensure signal processing instead of direct opening
                    print(f"🔗 [STREAMING] Final render - content contains links: {'<a href' in html_content}")
                    print(f"🔗 [STREAMING] Final render - OpenExternalLinks: {self.content_label.openExternalLinks()}")
                    print(f"🔗 [STREAMING] Final render - text format: {self.content_label.textFormat()}")
                    
                    print(f"✅ [STREAMING] Final render completed, using RichText format")
                else:
                    self.content_label.setText(self.full_text)
                    self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                    self.current_format = Qt.TextFormat.PlainText
                    self.is_markdown_detected = False  # Update state to match detection result
                    print(f"✅ [STREAMING] Final render completed, using PlainText format")
                
                # After streaming ends, restore flexible width
                self._restore_flexible_width()
                
                # Only perform one full layout update after streaming ends
                self.content_label.updateGeometry()
                self.updateGeometry()
                
                # Ensure parent container also updates layout (delayed execution, avoid blocking)
                chat_view = self.get_chat_view()
                if chat_view and hasattr(chat_view, 'container'):
                    QTimer.singleShot(50, chat_view.container.updateGeometry)
                
                # Request scrolling to the bottom, using unified scroll management
            
    def update_dots(self):
        """Update loading dots animation"""
        self.dots_count = (self.dots_count + 1) % 4
        dots = "." * self.dots_count
        self.content_label.setText(f"{self.message.content}{dots}")
    
    def mark_as_completed(self):
        """Mark streaming output as completed, quickly display Remaining content"""
        print(f"🏁 [STREAMING] Streaming output completed, quickly display Remaining content")
        print(f"🏁 [STREAMING] Currently displaying: {self.display_index}/{len(self.full_text)} characters")
        
        # If there is still a lot of content that has not been displayed, display it directly
        remaining_chars = len(self.full_text) - self.display_index
        if remaining_chars > 50:
            print(f"⚡ [STREAMING] Remaining {remaining_chars} characters, switch to extremely fast display mode")
            # Stop current timer
            self.typing_timer.stop()
            # Use extremely fast timer to quickly display Remaining content
            self.typing_timer.start(1)  # 1ms per character, extremely fast speed
        else:
            print(f"✅ [STREAMING] Remaining {remaining_chars} characters, keep current speed")


class ChatView(QScrollArea):
    """Chat message list view"""
    
    wiki_requested = pyqtSignal(str, str)  # url, title
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages: List[MessageWidget] = []
        self.current_status_widget: Optional[StatusMessageWidget] = None
        
        # Resize anti-shake mechanism
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._performDelayedResize)
        
        # Content stability detection
        self._last_content_height = 0
        self._content_stable_timer = QTimer()
        self._content_stable_timer.setSingleShot(True)
        self._content_stable_timer.timeout.connect(self._check_content_stability)
        
        # Animation status flag
        self._is_animating = False
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the chat view UI"""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Container widget
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.addStretch()  # Keep bottom alignment
        
        # Ensure container fills ScrollArea
        self.container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        self.setWidget(self.container)
        
        # Styling - transparent background to blend with main window
        self.setStyleSheet("""
            QScrollArea {
                background: rgba(248, 249, 250, 120);
                border: none;
                border-radius: 0px;
            }
            QScrollArea::corner {
                background: transparent;
            }
        """)
        
        # Connect scrollbar signals
        scrollbar = self.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll_changed)
        
        # Don't add welcome message anymore
        
    def _check_and_fix_width(self):
        """Check and fix ChatView width exception"""
        if not self.parent():
            return
            
        parent_width = self.parent().width()
        current_width = self.width()
        viewport_width = self.viewport().width()
        
        # If Parent container width is normal but ChatView width is abnormal
        if parent_width > 600 and current_width < 600:
            print(f"🔧 Detected ChatView width abnormal, starting fix:")
            print(f"  Parent container width: {parent_width}px")
            print(f"  ChatView width: {current_width}px") 
            print(f"  viewport width: {viewport_width}px")
            
            # Display the complete parent container chain
            print(f"  Complete parent container chain:")
            parent = self.parent()
            level = 0
            while parent and level < 5:
                parent_width_info = parent.width() if hasattr(parent, 'width') else "N/A"
                parent_type = type(parent).__name__
                parent_geometry = parent.geometry() if hasattr(parent, 'geometry') else "N/A"
                print(f"    └─ [{level}] {parent_type}: width={parent_width_info}px, geometry={parent_geometry}")
                parent = parent.parent() if hasattr(parent, 'parent') else None
                level += 1
            
            # Force set to Parent container width
            self.setFixedWidth(parent_width)
            QTimer.singleShot(50, lambda: self.setMaximumWidth(16777215))  # Delay removal of fixed width limit
            QTimer.singleShot(100, lambda: self.setMinimumWidth(0))
            
            print(f"🔧 ChatView width fixed: {parent_width}px")
            
        # If viewport width is abnormal, force refresh
        elif viewport_width < 600 and parent_width > 600:
            print(f"🔧 Detected viewport width abnormal, force refresh layout")
            print(f"  Current size policy: {self.sizePolicy().horizontalPolicy()}")
            print(f"  Minimum size: {self.minimumSize()}")
            print(f"  Maximum size: {self.maximumSize()}")
            
            self.updateGeometry()
            self.container.updateGeometry()
            if self.parent():
                self.parent().updateGeometry()
        
    def _add_welcome_message(self):
        """Add welcome message and recommended queries"""
        # Build multi-language welcome message
        welcome_parts = [
            t('welcome_title'),
            "",
            t('welcome_features'),
            t('welcome_wiki_search'),
            t('welcome_ai_guide'),
            "",
            t('welcome_examples'),
            t('welcome_helldivers'),
            t('welcome_eldenring'),
            t('welcome_dst')
        ]
        
        welcome_content = "\n".join(welcome_parts)
        
        # Create welcome message
        welcome_message = ChatMessage(
            type=MessageType.AI_RESPONSE,
            content=welcome_content,
            metadata={"is_welcome": True}
        )
        
        widget = MessageWidget(welcome_message, self)
        self.layout.insertWidget(self.layout.count() - 1, widget)
        self.messages.append(widget)
        
    def add_message(self, msg_type: MessageType, content: str, 
                   metadata: Dict[str, Any] = None) -> MessageWidget:
        """Add a new message to the chat"""
        # Check and fix ChatView width exception
        self._check_and_fix_width()
        
        message = ChatMessage(
            type=msg_type,
            content=content,
            metadata=metadata or {}
        )
        
        if msg_type == MessageType.AI_STREAMING:
            widget = StreamingMessageWidget(message, self)
        else:
            widget = MessageWidget(message, self)
            
        self.layout.insertWidget(self.layout.count() - 1, widget)
        self.messages.append(widget)
        
        # Dynamically set message maximum width to 75% of ChatView width
        self._update_message_width(widget)
        
        # Gentle layout update, avoid forced resizing
        widget.updateGeometry()
        self.container.updateGeometry()
        
        return widget
        
    def add_streaming_message(self) -> StreamingMessageWidget:
        """Add a new streaming message"""
        print(f"🎬 [UI-DEBUG] Started creating streaming message component")
        try:
            # Create streaming message, which will be converted to AI_RESPONSE type after completion
            streaming_widget = self.add_message(MessageType.AI_STREAMING, "")
            print(f"✅ [UI-DEBUG] Streaming message component created successfully: {streaming_widget}")
            print(f"✅ [UI-DEBUG] Streaming message component type: {type(streaming_widget)}")
            return streaming_widget
        except Exception as e:
            print(f"❌ [UI-DEBUG] Failed to create streaming message component: {e}")
            raise

    def show_status(self, message: str) -> StatusMessageWidget:
        """Display status information"""
        # Check and fix ChatView width exception
        self._check_and_fix_width()
        
        # If there is already a status message, hide it first
        if self.current_status_widget:
            self.hide_status()
            
        # Create new status message
        self.current_status_widget = StatusMessageWidget(message, self)
        self.layout.insertWidget(self.layout.count() - 1, self.current_status_widget)
        
        # Dynamically set message maximum width
        self._update_status_width(self.current_status_widget)
        
        # Gentle layout update
        self.current_status_widget.updateGeometry()
        self.container.updateGeometry()
        
        return self.current_status_widget
        
    def update_status(self, message: str):
        """Update current status information"""
        if self.current_status_widget:
            self.current_status_widget.update_status(message)
        else:
            self.show_status(message)
            
    def hide_status(self):
        """Hide current status information"""
        if self.current_status_widget:
            self.current_status_widget.hide_with_fadeout()
            self.layout.removeWidget(self.current_status_widget)
            self.current_status_widget.deleteLater()
            self.current_status_widget = None
            
    def _update_status_width(self, widget: StatusMessageWidget):
        """Update status message widget maximum width"""
        # Get the actual width of the chat view, considering the width of the scrollbar
        chat_width = self.viewport().width()
        
        # Subtract the width that the scrollbar may occupy
        scrollbar = self.verticalScrollBar()
        if scrollbar and scrollbar.isVisible():
            chat_width -= scrollbar.width()
            
        if chat_width > 0:
            # Ensure valid width
            chat_width = max(300, chat_width)
            
            # Set the maximum width of the status message to 85% of the width of the chat view, minimum 300px, maximum 800px
            max_width = min(max(int(chat_width * 0.85), 300), 800)
            # Find the status bubble and set its maximum width
            bubble = widget.findChild(QFrame, "statusBubble")
            if bubble:
                bubble.setMaximumWidth(max_width)
                # Use preferred size policy, avoid fixed width causing layout problems
                bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        
    def scroll_to_bottom(self):
        """Scroll to the bottom of the chat"""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
            
        
        
    def _check_content_stability(self):
        """Check if the content is stable"""
        current_height = self.container.sizeHint().height()
        if current_height != self._last_content_height:
            # Content is still changing, continue waiting
            self._last_content_height = current_height
            self._content_stable_timer.start(50)
            
    def _on_scroll_changed(self, value):
        """Callback when scroll position changes"""
        # Currently no action needed on scroll change
        pass
            
            
    def wheelEvent(self, event):
        """Mouse wheel event"""
        # Call the original wheel event processing
        super().wheelEvent(event)
            
    def mouseDoubleClickEvent(self, event):
        """Double-click event"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Scroll to bottom on double-click
            self.scroll_to_bottom()
        super().mouseDoubleClickEvent(event)
        
        
    def keyPressEvent(self, event):
        """Keyboard event"""
        if event.key() == Qt.Key.Key_End:
            # End key: scroll to the bottom
            self.scroll_to_bottom()
        elif event.key() == Qt.Key.Key_Home:
            # Home key: scroll to the top
            scrollbar = self.verticalScrollBar()
            scrollbar.setValue(0)
        else:
            super().keyPressEvent(event)
    
    def contextMenuEvent(self, event):
        """Override context menu event to ensure proper styling"""
        # Create a custom context menu
        menu = QMenu(self)
        
        # The menu will inherit the global QMenu styling
        # No need to add any actions for scrollbar - just show empty menu
        # This prevents the default transparent context menu
        
        menu.exec(event.globalPos())
        
    def show_wiki(self, url: str, title: str):
        """Emit signal to show wiki page"""
        logger = logging.getLogger(__name__)
        logger.info(f"📄 ChatView.show_wiki called: URL={url}, Title={title}")
        self.wiki_requested.emit(url, title)
        logger.info(f"📤 wiki_requested signal emitted")
        
    def _update_message_width(self, widget: MessageWidget):
        """Update message widget maximum width"""
        # If it is animating, skip update
        if self._is_animating:
            return
            
        # Get multi-layer container width information for debugging
        viewport_width = self.viewport().width()
        scroll_area_width = self.width()
        parent_window_width = self.parent().width() if self.parent() else "N/A"
        
        # Get the actual width of the chat view, considering the width of the scrollbar
        chat_width = viewport_width
        
        # Subtract the width that the scrollbar may occupy
        scrollbar = self.verticalScrollBar()
        scrollbar_width = 0
        if scrollbar and scrollbar.isVisible():
            scrollbar_width = scrollbar.width()
            chat_width -= scrollbar_width
            
        if chat_width > 0:
            # Ensure valid width
            chat_width = max(300, chat_width)
            
            # Set the maximum width of the message to 75% of the width of the chat view, minimum 300px, maximum 600px
            max_width = min(max(int(chat_width * 0.75), 300), 600)
            
            # If it is StreamingMessageWidget, call its specialized update method
            if isinstance(widget, StreamingMessageWidget):
                widget._update_bubble_width()
            else:
                # For normal messages, use maximum width instead of fixed width
                bubble = widget.findChild(QFrame, "messageBubble")
                if bubble:
                    # Use maximum width, let the layout system decide the actual width
                    bubble.setMaximumWidth(max_width)
                    bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                
                # Update the width of content_label at the same time
                if hasattr(widget, 'content_label'):
                    content_width = max_width - 24  # Subtract margin
                    widget.content_label.setMaximumWidth(content_width)
                    widget.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                
                # Output debug information only in abnormal cases
                if viewport_width < 400:  # Output warning when the view width is abnormal
                    print(f"⚠️ View width abnormal: viewport={viewport_width}px")
                
    def resizeEvent(self, event):
        """Trigger anti-shake update when window size changes"""
        super().resizeEvent(event)
        
        # If it is animating, skip update to avoid stuttering
        if self._is_animating:
            return
        
        # Force ChatView to maintain the correct width (immediately executed to avoid display exceptions)
        parent_width = self.parent().width() if self.parent() else 0
        current_width = self.width()
        if parent_width > 0 and abs(current_width - parent_width) > 5:  # More than 5px difference
            self.resize(parent_width, self.height())
        
        # Use anti-shake mechanism to delay updating message width (restore original logic)
        self.resize_timer.stop()  # Stop the previous timer
        self.resize_timer.start(200)  # Update after 0.2 seconds
        
    def _performDelayedResize(self):
        """Delayed resize update operation"""
        print(f"📏 ChatView layout updated: {self.size()}")
        
        # Update the width of all existing messages
        for widget in self.messages:
            self._update_message_width(widget)
        # Update the width of the status message
        if self.current_status_widget:
            self._update_status_width(self.current_status_widget)
            
        # Force update the height of all messages to ensure complete display
        self._ensureContentComplete()
        
        # Delay a little bit to check again, ensure all content has been rendered
        QTimer.singleShot(50, self._finalizeContentDisplay)
        
        
    def _ensureContentComplete(self):
        """Ensure all message content is displayed completely"""
        try:
            # Update the display of all messages
            for widget in self.messages:
                if hasattr(widget, 'content_label'):
                    try:
                        # 1. Update message width
                        self._update_message_width(widget)
                        
                        # 2. Force content label to recalculate size
                        content_label = widget.content_label
                        
                        # Ensure content is not truncated
                        content_label.setWordWrap(True)
                        content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                        
                        # For StreamingMessageWidget, ensure the format is correct
                        if isinstance(widget, StreamingMessageWidget):
                            # If there is complete text, re-detect and render
                            if hasattr(widget, 'full_text') and widget.full_text:
                                if detect_markdown_content(widget.full_text):
                                    html_content = convert_markdown_to_html(widget.full_text)
                                    content_label.setText(html_content)
                                    content_label.setTextFormat(Qt.TextFormat.RichText)
                                else:
                                    content_label.setText(widget.full_text)
                                    content_label.setTextFormat(Qt.TextFormat.PlainText)
                        
                        # 3. Force update content size
                        content_label.adjustSize()
                        
                        # 4. Ensure bubble container is correctly expanded
                        bubble = widget.findChild(QFrame, "messageBubble")
                        if bubble:
                            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
                            
                            # Improved: use a more reliable way to calculate the required height
                            # Wait a little bit to let the content render
                            QTimer.singleShot(10, lambda w=widget, b=bubble, cl=content_label: self._updateBubbleHeight(w, b, cl))
                        
                        # 5. Special handling for streaming messages
                        if isinstance(widget, StreamingMessageWidget):
                            if hasattr(widget, 'full_text') and widget.full_text:
                                widget._update_bubble_width()
                                widget.updateGeometry()
                        
                    except Exception as e:
                        # Record errors instead of silent processing
                        print(f"Error updating message display: {e}")
            
            # Update status message
            if self.current_status_widget:
                try:
                    self._update_status_width(self.current_status_widget)
                except Exception:
                    pass
            
            # Force the entire container to re-layout
            self.container.updateGeometry()
            self.updateGeometry()
            self.verticalScrollBar().update()
            
        except Exception as e:
            # Record global error
            print(f"_ensureContentComplete error: {e}")
    
    def _updateBubbleHeight(self, widget, bubble, content_label):
        """Delay updating bubble height, ensure content rendering is complete"""
        try:
            # Get the actual height of the content
            # Use multiple methods to get the most accurate height
            height1 = content_label.sizeHint().height()
            height2 = content_label.heightForWidth(content_label.width())
            
            # For rich text content, additional height calculation is required
            if content_label.textFormat() == Qt.TextFormat.RichText:
                # Create a temporary document to accurately calculate the height of HTML content
                doc = QTextDocument()
                doc.setDefaultFont(content_label.font())
                doc.setHtml(content_label.text())
                doc.setTextWidth(content_label.width())
                height3 = int(doc.size().height())
            else:
                height3 = height1
            
            # Take the maximum value to ensure complete display
            actual_height = max(height1, height2, height3)
            
            # Add padding
            min_height = actual_height + 20  # Increase margin
            
            # Set minimum height
            bubble.setMinimumHeight(min_height)
            
            # Force update the entire message widget
            widget.updateGeometry()
            widget.update()
            
        except Exception as e:
            print(f"Error updating bubble height: {e}")
    
    def _finalizeContentDisplay(self):
        """Finalize content display"""
        # Check the height of all messages again
        for widget in self.messages:
            if hasattr(widget, 'content_label'):
                bubble = widget.findChild(QFrame, "messageBubble")
                if bubble and widget.content_label:
                    self._updateBubbleHeight(widget, bubble, widget.content_label)
    
    def _force_content_refresh(self):
        """Force refresh all content display (simplified version)"""
        try:
            # Simple content refresh, ensure the scroll position is correct
            if hasattr(self, 'near_bottom_before_resize') and self.near_bottom_before_resize:
                self.scroll_to_bottom()
        except Exception:
            pass
            
    def update_all_message_widths(self):
        """Update the width of all messages (for initialization after window display)"""
        for widget in self.messages:
            self._update_message_width(widget)
        if self.current_status_widget:
            self._update_status_width(self.current_status_widget)
        
    def showEvent(self, event):
        """Update message width when window is displayed"""
        super().showEvent(event)
        # Delay update, ensure the window is fully displayed
        QTimer.singleShot(100, self.update_all_message_widths)






class UnifiedAssistantWindow(QMainWindow):
    """Main unified window with all modes"""
    
    query_submitted = pyqtSignal(str, str)  # query, mode
    window_closing = pyqtSignal()  # Signal when window is closing
    wiki_page_found = pyqtSignal(str, str)  # New signal: pass real wiki page information to controller
    visibility_changed = pyqtSignal(bool)  # Signal for visibility state changes
    stop_generation_requested = pyqtSignal()  # New signal: stop generation request

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
        self._cached_chat_only_size = None  # Cache for chat_only size to avoid recalculation
        
        # Default WebView size (landscape orientation) - defer calculation to avoid GUI initialization issues
        self._default_webview_size = None  # Will be calculated when needed
        
        # Geometry save timer for delayed saving on move/resize
        self._geometry_save_timer = QTimer()
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.timeout.connect(self.save_geometry)
        
        # History manager will be initialized lazily
        self.history_manager = None
        
        # Track current navigation to avoid duplicate history entries
        self._pending_navigation = None  # URL being navigated to
        self._last_recorded_url = None  # Last URL added to history
        
        self.init_ui()
        
        # Apply BlurWindow effect
        self.apply_blur_effect()
        
        self.restore_geometry()
        
        # Debug: print size after initialization
        print(f"🏠 UnifiedAssistantWindow initialized, size: {self.size()}")

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
                print("✅ Win10 Aero effect applied")
                    
            except Exception as e:
                print(f"❌ BlurWindow application failed: {e}")
                print("Will use default transparency effect")
        else:
            print("⚠️ BlurWindow not available, using default transparency effect")
            
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
                print("✅ Window rounded corners set successfully")
            else:
                print(f"⚠️ Window rounded corners setting failed: {result}")
                
        except Exception as e:
            print(f"❌ Failed to set window rounded corners: {e}")
        
    def _ensure_history_manager(self):
        """Ensure history manager is initialized"""
        if self.history_manager is None:
            from src.game_wiki_tooltip.core.history_manager import WebHistoryManager
            self.history_manager = WebHistoryManager()
            print("📚 History manager initialized")
        
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
        self.wiki_view.close_requested.connect(self.hide)  # Connect close button to hide window
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
            "search for information...",
        ]
        self.input_field.setPlaceholderText(" | ".join(placeholder_texts[:3]))  # Show first 3 examples
        self.input_field.returnPressed.connect(self.on_input_return_pressed)
        
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
        self.history_button.setToolTip("History")
        self.history_button.clicked.connect(self.show_history_menu)
        
        # Load history icon
        from src.game_wiki_tooltip.core.utils import package_file
        history_icon_path = str(package_file("icons/refresh-ccw-clock-svgrepo-com.svg"))
        history_icon = load_svg_icon(history_icon_path, color="#111111", size=20)
        self.history_button.setIcon(history_icon)
        self.history_button.setIconSize(QSize(20, 20))
        
        # Quick Access button (replaces external website button)
        self.quick_access_button = QPushButton()
        self.quick_access_button.setObjectName("externalBtn")
        self.quick_access_button.setFixedSize(32, 32)
        self.quick_access_button.setToolTip("Go to external website")
        # Connect click handler
        self.quick_access_button.clicked.connect(self.on_quick_access_clicked)
        
        # Load quick access icon
        external_icon_path = str(package_file("icons/globe-alt-1-svgrepo-com.svg"))
        external_icon = load_svg_icon(external_icon_path, color="#111111", size=20)
        self.quick_access_button.setIcon(external_icon)
        self.quick_access_button.setIconSize(QSize(20, 20))
        
        # Search mode button
        self.mode_button = QPushButton()
        self.mode_button.setObjectName("searchBtn")
        self.mode_button.setFixedSize(32, 32)
        self.mode_button.setToolTip("Search Mode")
        self.mode_button.clicked.connect(self.show_mode_menu)
        
        # Load search icon
        search_icon_path = str(package_file("icons/search-alt-1-svgrepo-com.svg"))
        search_icon = load_svg_icon(search_icon_path, color="#111111", size=20)
        self.mode_button.setIcon(search_icon)
        self.mode_button.setIconSize(QSize(20, 20))
        
        # Send button
        self.send_button = QPushButton()
        self.send_button.setObjectName("sendBtn")
        self.send_button.setFixedSize(32, 32)
        self.send_button.clicked.connect(self.on_send_clicked)
        
        # Load send icon
        send_icon_path = str(package_file("icons/arrow-circle-up-svgrepo-com.svg"))
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
        
        # Load task flow icon
        task_icon_path = str(package_file("icons/layers-svgrepo-com.svg"))
        task_icon = load_svg_icon(task_icon_path, color="#111111", size=20)
        self.task_flow_button.setIcon(task_icon)
        self.task_flow_button.setIconSize(QSize(20, 20))
        
        access_layout.addWidget(self.task_flow_button)
        
        # Initialize current task flow game
        self.current_task_flow_game = None
        
        access_layout.addStretch()  # Space in middle
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
        
        #minBtn, #closeBtn {
            background: rgba(255, 255, 255, 150);
            border: none;
            border-radius: 5px;
            color: #111111;
            font-weight: bold;
            font-family: "Segoe UI", "Microsoft YaHei", Arial;
        }
        
        #minBtn:hover, #closeBtn:hover {
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
        #historyBtn, #externalBtn, #searchBtn, #sendBtn {
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
            background-color: rgba(255, 77, 79, 200);
            border-radius: 4px;
        }
        
        #sendBtn[stop_mode="true"]:hover {
            background-color: rgba(255, 120, 117, 200);
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
    
    def _final_geometry_check(self, x, y, width, height, screen):
        """
        Final geometry check, ensure the window is fully visible and operable
        
        Args:
            x, y, width, height: Window geometry parameters
            screen: Screen available area
            
        Returns:
            tuple: Adjusted (x, y, width, height)
        """
        # Ensure Minimum size
        min_width, min_height = 300, 200
        width = max(min_width, width)
        height = max(min_height, height)
        
        # Ensure Maximum size does not exceed screen
        max_width = screen.width() - 20
        max_height = screen.height() - 40
        width = min(width, max_width)
        height = min(height, max_height)
        
        # Ensure position is within visible range
        margin = 10
        max_x = screen.x() + screen.width() - width - margin
        max_y = screen.y() + screen.height() - height - margin
        min_x = screen.x() + margin
        min_y = screen.y() + margin
        
        x = max(min_x, min(x, max_x))
        y = max(min_y, min(y, max_y))
        
        return x, y, width, height
    
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
    
    def _save_initial_geometry_config(self, popup_config):
        """
        Save initial geometry configuration to settings file
        
        Args:
            popup_config: PopupConfig instance
        """
        try:
            from dataclasses import asdict
            popup_dict = asdict(popup_config)
            self.settings_manager.update({'popup': popup_dict})
            logging.info("Saved smart default window configuration to settings file")
        except Exception as e:
            logging.warning(f"Failed to save initial geometry configuration: {e}")
    
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
        
    def switch_to_webview(self):
        """Switch to webview state"""
        # Save current state's geometry before switching
        if self.current_state == WindowState.FULL_CONTENT:
            self.save_geometry()
            
        self.current_state = WindowState.WEBVIEW
        self.has_switched_state = True  # User has manually switched states
        self.update_window_layout()
        
    def position_chat_window(self):
        """Position the search box at bottom right of screen"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        window_geometry = self.geometry()
        
        # Position at right side leaving about 1/5 space
        x = screen_geometry.width() - window_geometry.width() - int(screen_geometry.width() * 0.2)
        # Near bottom but not touching, leave about 50px gap
        y = screen_geometry.height() - window_geometry.height() - 50
        
        self.move(x, y)
        
    def center_window(self):
        """Center window on screen"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        window_geometry = self.geometry()
        
        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2
        
        self.move(x, y)
        
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
    
    def show_chat_view(self):
        """Switch to chat view"""
        # First stop media playback in WikiView (only pause when currently displaying WikiView)
        if hasattr(self, 'wiki_view') and self.wiki_view:
            current_widget = self.content_stack.currentWidget()
            if current_widget == self.wiki_view:
                self.wiki_view.pause_page()
        
        # If coming from WEBVIEW state, switch back to FULL_CONTENT
        if self.current_state == WindowState.WEBVIEW:
            self.switch_to_full_content()
            
        self.content_stack.setCurrentWidget(self.chat_view)
        # Show input area and shortcuts in chat mode
        if hasattr(self, 'input_container'):
            self.input_container.show()
        # Shortcut container is now hidden - shortcuts are in popup
        # Reset size constraints when switching to chat view
        self.reset_size_constraints()
        # Ensure message width is correct and trigger full layout update
        QTimer.singleShot(50, self.chat_view.update_all_message_widths)
        # Delay executing full layout update, ensure content is fully displayed
        QTimer.singleShot(100, self.chat_view._performDelayedResize)
        # Set focus to input field when returning to chat view
        QTimer.singleShot(150, self._set_chat_input_focus)
        
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

    def show_wiki_page(self, url: str, title: str):
        """Switch to wiki view and load page"""
        logger = logging.getLogger(__name__)
        logger.info(f"🌐 UnifiedAssistantWindow.show_wiki_page called: URL={url}, Title={title}")
        
        # Switch to WEBVIEW state
        self.switch_to_webview()
        
        # Only add to history if:
        # 1. Not a local file
        # 2. Not the same as last recorded URL
        # 3. Has a meaningful title (not just domain)
        if (hasattr(self, 'history_manager') and 
            not url.startswith('file://') and 
            url != self._last_recorded_url and
            title and title.strip() != ""):
            
            # Check if title is just a domain (indicates quick access)
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                is_just_domain = (title == parsed.netloc)
            except:
                is_just_domain = False
            
            # Only record if we have a real title, not just domain
            if not is_just_domain:
                # Determine source type
                if "wiki" in url.lower() or "wiki" in title.lower():
                    source = "wiki"
                else:
                    source = "web"
                self._ensure_history_manager()
                self.history_manager.add_entry(url, title, source=source)
                self._last_recorded_url = url
            else:
                # Mark as pending for when real title arrives
                self._pending_navigation = url
        
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
        from src.game_wiki_tooltip.core.i18n import t
        
        self.current_mode = mode
        if mode == "url":
            self.input_field.setPlaceholderText("Enter URL...")
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_open_url_clicked)
        elif mode == "wiki":
            self.input_field.setPlaceholderText("Enter search query...")
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_send_clicked)
        elif mode == "ai":
            self.input_field.setPlaceholderText("Enter question...")
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_send_clicked)
        else:  # auto mode
            self.input_field.setPlaceholderText("Enter message...")
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
        # Mark as pending navigation (don't record history yet)
        self._pending_navigation = url
        
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
                    from src.game_wiki_tooltip.core.utils import package_file
                    icon_path = ""
                    if shortcut.get('icon'):
                        try:
                            relative_path = shortcut.get('icon', '')
                            print(f"[load_shortcuts] Trying to load icon: {relative_path}")
                            
                            # Get the actual file path
                            import pathlib
                            # Try direct path first (for development)
                            base_path = pathlib.Path(__file__).parent
                            # relative_path already contains "assets/icons/..."
                            direct_path = base_path / relative_path
                            
                            if direct_path.exists():
                                icon_path = str(direct_path)
                                print(f"[load_shortcuts] Using direct path: {icon_path}")
                            else:
                                # Try package_file for packaged app
                                try:
                                    # Remove 'assets/' prefix for package_file call
                                    package_path = relative_path
                                    if relative_path.startswith('assets/'):
                                        package_path = relative_path[7:]  # Remove 'assets/'
                                    path_obj = package_file(package_path)
                                    # For resources, we might need to extract
                                    if hasattr(path_obj, 'read_bytes'):
                                        # It's a resource, we need to save it temporarily
                                        import tempfile
                                        data = path_obj.read_bytes()
                                        suffix = pathlib.Path(relative_path).suffix
                                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                                            tmp.write(data)
                                            icon_path = tmp.name
                                        print(f"[load_shortcuts] Extracted resource to: {icon_path}")
                                    else:
                                        icon_path = str(path_obj)
                                        print(f"[load_shortcuts] package_file path: {icon_path}")
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
            html_path = package_file(f"html/{html_filename}")
            
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
                more_action = history_menu.addAction(f"... and {len(history_items) - 10} more")
                more_action.setEnabled(False)
            
            # Add clear history option
            history_menu.addSeparator()
            clear_action = history_menu.addAction("Clear History")
            clear_action.triggered.connect(self.clear_history)
        
        # Show menu with intelligent positioning
        self._show_menu_with_intelligent_position(history_menu, self.history_button)
    
    def clear_history(self):
        """Clear browsing history"""
        self._ensure_history_manager()
        self.history_manager.clear_history()
        # Show notification
        QTimer.singleShot(100, lambda: self.history_button.setToolTip("History cleared"))
        QTimer.singleShot(2000, lambda: self.history_button.setToolTip("View browsing history"))

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

    def set_current_game_window(self, game_window_title: str):
        """Set current game window title and update task flow button visibility"""
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        
        # Debug: Log method call with stack trace to identify caller
        logger.info(f"🎮 [DEBUG] set_current_game_window called with: '{game_window_title}'")
        logger.debug(f"🔍 [DEBUG] Call stack (last 3 frames):")
        stack = traceback.extract_stack()
        for i, frame in enumerate(stack[-4:-1]):  # Skip current frame, show last 3
            logger.debug(f"    Frame {i+1}: {frame.filename}:{frame.lineno} in {frame.name}")
        
        # Debug: Log current state before change
        old_game_window = getattr(self, 'current_game_window', None)
        logger.info(f"🔄 [DEBUG] Game window change: '{old_game_window}' -> '{game_window_title}'")
        
        # Debug: Check if task buttons are initialized
        button_count = len(getattr(self, 'game_task_buttons', {}))
        logger.info(f"📋 [DEBUG] Current task buttons count: {button_count}")
        
        # Critical fix: Ensure task buttons are created before trying to update visibility
        if button_count == 0:
            logger.warning(f"⚠️ [DEBUG] Task buttons not created yet, creating them first")
            logger.warning(f"⚠️ [DEBUG] Game task layout not available, buttons will be created later")
        
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
    
    def set_generating_state(self, is_generating: bool, streaming_msg=None):
        """Set generation state"""
        self.is_generating = is_generating
        self.streaming_widget = streaming_msg
        
        # Get icon paths
        import pathlib
        pause_icon_path = str(package_file("icons/pause-circle-svgrepo-com.svg"))
        send_icon_path = str(package_file("icons/arrow-circle-up-svgrepo-com.svg"))
        
        if is_generating:
            # Switch to stop mode with pause icon
            pause_icon = load_svg_icon(pause_icon_path, color="#ffffff", size=20)
            self.send_button.setIcon(pause_icon)
            self.send_button.setProperty("stop_mode", "true")
            self.input_field.setPlaceholderText("Click Stop to cancel generation...")
            self.input_field.setEnabled(False)  # Disable input field
        else:
            # Switch back to send mode with arrow icon
            send_icon = load_svg_icon(send_icon_path, color="#111111", size=20)
            self.send_button.setIcon(send_icon)
            if self.current_mode == "url":
                self.send_button.setText("Open")
            else:
                self.send_button.setText("")  # No text, icon only
            self.send_button.setProperty("stop_mode", "false")
            self.input_field.setPlaceholderText("Enter message..." if self.current_mode != "url" else "Enter URL...")
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
            print("✅ UI state restored")
            
            # Hide status information
            try:
                self.chat_view.hide_status()
                print("✅ Status information hidden")
            except Exception as e:
                print(f"⚠️ Error hiding status information: {e}")
            
            # If there is current streaming message, mark as stopped
            if self.streaming_widget:
                try:
                    self.streaming_widget.mark_as_stopped()
                    print("✅ Streaming message marked as stopped")
                except Exception as e:
                    print(f"⚠️ Error marking streaming message as stopped: {e}")
            
            # Finally emit stop signal, use QTimer.singleShot to avoid possible deadlock
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._emit_stop_signal_safe())
            print("✅ Stop signal scheduled to be sent")
            
        except Exception as e:
            print(f"❌ Error during stop generation: {e}")
            # Even if error occurs, try to restore UI state
            try:
                self.set_generating_state(False)
            except:
                pass
                
    def _emit_stop_signal_safe(self):
        """Safely emit stop signal"""
        try:
            self.stop_generation_requested.emit()
            print("✅ Stop signal sent")
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
        
        # Load shortcuts and history after window is shown
        if not self.shortcuts_loaded:
            self.shortcuts_loaded = True
            # Use QTimer to defer loading to next event loop iteration
            QTimer.singleShot(0, self._load_deferred_content)
            
    def _load_deferred_content(self):
        """Load non-critical content after window is shown"""
        try:
            # Load shortcuts
            print("📌 Loading shortcuts...")
            start_time = time.time()
            self.load_shortcuts()
            print(f"✅ Shortcuts loaded in {time.time() - start_time:.2f}s")
            
            # Initialize history manager
            print("📌 Initializing history manager...")
            start_time = time.time()
            self._ensure_history_manager()
            print(f"✅ History manager initialized in {time.time() - start_time:.2f}s")
            
            # Load other deferred content
            # Add more deferred loading here if needed
            
        except Exception as e:
            print(f"❌ Error loading deferred content: {e}")
            import traceback
            traceback.print_exc()
        
    def closeEvent(self, event):
        """Handle close event - just hide the window"""
        event.ignore()  # Don't actually close the window
        
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


