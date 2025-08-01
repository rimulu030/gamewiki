"""
Assistant controller for managing chat window and game context.
"""

import logging
from enum import Enum
from typing import Optional


from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import QApplication


class WindowMode(Enum):
    """Window display modes"""
    CHAT = "chat"
    WIKI = "wiki"


class MessageType(Enum):
    """Chat message types"""
    USER_QUERY = "user_query"
    AI_RESPONSE = "ai_response"
    SYSTEM_MESSAGE = "system_message"
    STATUS = "status"
    ERROR = "error"


class TransitionMessages:
    """Transition state messages"""
    QUERY_RECEIVED = "Processing your query..."


class WindowState(Enum):
    """Window state enumeration"""
    CHAT_ONLY = "chat_only"      # Only show input box
    FULL_CONTENT = "full_content" # Show all content
    WEBVIEW = "webview"          # WebView2 form


class AssistantController:
    """Controller for the assistant system"""
    
    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager
        self.main_window = None
        self.current_mode = WindowMode.CHAT
        self.current_game_window = None  # Record current game window title
        self._precreated = False  # Track if window has been pre-created
        self.previous_window_state = None  # Track previous window state for restoration
        
    def set_current_game_window(self, game_window_title: str):
        """Set current game window title"""
        self.current_game_window = game_window_title
        
        # Pass game window information to main window
        if self.main_window:
            self.main_window.set_current_game_window(game_window_title)
        
        logger = logging.getLogger(__name__)
        logger.info(f"🎮 Recording game window: '{game_window_title}'")

    def precreate_chat_window(self):
        """Pre-create chat window for faster first-time response"""
        logger = logging.getLogger(__name__)
        
        if self._precreated or self.main_window:
            logger.info("Chat window already created or pre-created")
            return
            
        try:
            logger.info("Pre-creating chat window...")
            
            # Import here to avoid circular import
            from ..unified_window import UnifiedAssistantWindow
            
            # Create window but keep it hidden
            self.main_window = UnifiedAssistantWindow(self.settings_manager)
            
            # Set precreating mode to prevent geometry saving during initialization
            self.main_window.set_precreating_mode(True)
            
            self.main_window.query_submitted.connect(self.handle_query)
            self.main_window.wiki_page_found.connect(self.handle_wiki_page_found)
            
            # Connect stop generation signal if handler exists
            if hasattr(self, 'handle_stop_generation'):
                self.main_window.stop_generation_requested.connect(self.handle_stop_generation)
                logger.info("✅ Connected stop_generation_requested signal")
            
            # CRITICAL FIX: Ensure task buttons are created during pre-creation
            logger.info(f"🔍 [DEBUG] Force loading shortcuts for pre-created window...")
            try:
                # Call _load_deferred_content directly since showEvent won't be triggered
                self.main_window._load_deferred_content()
                self.main_window.shortcuts_loaded = True  # Mark as loaded
                button_count = len(getattr(self.main_window, 'game_task_buttons', {}))
                logger.info(f"✅ [DEBUG] Shortcuts loaded for pre-created window, task buttons: {button_count}")
            except Exception as e:
                logger.error(f"❌ [DEBUG] Failed to load shortcuts for pre-created window: {e}")
                import traceback
                traceback.print_exc()
            
            # If we already have a game context, set it AFTER shortcuts are loaded
            try:
                if self.current_game_window:
                    self.main_window.set_current_game_window(self.current_game_window)
                    logger.info(f"✅ [DEBUG] Set game context for pre-created window: {self.current_game_window}")
            except Exception as e:
                logger.error(f"❌ [DEBUG] Failed to set game context for pre-created window: {e}")
            
            # Important: Keep window hidden
            self.main_window.hide()
            
            # Mark as pre-created
            self._precreated = True
            logger.info("✅ Chat window pre-created and hidden")
            
        except Exception as e:
            logger.error(f"Failed to pre-create chat window: {e}")
            import traceback
            traceback.print_exc()
            self.main_window = None
            self._precreated = False
        
    def handle_wiki_page_found(self, url: str, title: str):
        """Handle signal when real wiki page is found (basic implementation, subclasses can override)"""
        logger = logging.getLogger(__name__)
        logger.info(f"🔗 AssistantController received wiki page signal: {title} -> {url}")
        # Basic implementation: do nothing, subclasses (IntegratedAssistantController) will override this method
    
    def refresh_shortcuts(self):
        """Refresh shortcut buttons"""
        if self.main_window:
            self.main_window.load_shortcuts()
        
    def handle_query(self, query: str, mode: str = "auto"):
        """Handle user query"""
        # Check if the last message in chat view is already this user query
        # to avoid duplication (since it may have been added in the UI already)
        should_add_message = True
        if self.main_window and self.main_window.chat_view.messages:
            last_message = self.main_window.chat_view.messages[-1]
            if (hasattr(last_message, 'message') and 
                last_message.message.type == MessageType.USER_QUERY and 
                last_message.message.content == query):
                should_add_message = False
        
        # Add user message to chat only if not already added
        if should_add_message:
            self.main_window.chat_view.add_message(
                MessageType.USER_QUERY,
                query
            )
        
        
        # Show initial processing status
        self.main_window.chat_view.show_status(TransitionMessages.QUERY_RECEIVED)
        
    def is_visible(self):
        """Check if any window is visible"""
        return self.main_window and self.main_window.isVisible()
