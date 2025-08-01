"""
Smart Interaction Manager - Handles UI interaction logic in gaming scenarios
Solves mouse click conflicts and hotkey repeat issues when mouse is hidden
"""

import ctypes
import logging
import time
from ctypes import wintypes
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# Windows API constants
CURSOR_SHOWING = 0x00000001
CURSOR_SUPPRESSED = 0x00000002

# Windows API function definitions
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD), 
        ("hCursor", wintypes.HANDLE),  # Use HANDLE instead of HCURSOR
        ("ptScreenPos", POINT)
    ]

# Windows API functions
GetCursorInfo = user32.GetCursorInfo
GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
GetCursorInfo.restype = wintypes.BOOL

GetForegroundWindow = user32.GetForegroundWindow
GetForegroundWindow.restype = wintypes.HWND

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int

class InteractionMode(Enum):
    """Interaction mode enumeration"""
    NORMAL = "normal"           # Normal mode: mouse visible, normal interaction
    GAME_HIDDEN = "game_hidden" # Game mode: mouse hidden, requires passthrough
    GAME_VISIBLE = "game_visible" # Game mode: mouse visible, normal interaction

@dataclass
class MouseState:
    """Mouse state information"""
    is_visible: bool
    is_suppressed: bool
    position: Tuple[int, int]
    cursor_handle: int

@dataclass
class WindowState:
    """Window state information"""
    foreground_window: int
    window_title: str
    is_game_window: bool

class SmartInteractionManager(QObject):
    """
    Smart Interaction Manager
    
    Main features:
    1. Detect mouse show/hide status
    2. Detect current focus window and game state
    3. Manage window mouse passthrough state
    4. Optimize hotkey response logic
    """
    
    # Signal definitions
    interaction_mode_changed = pyqtSignal(object)  # InteractionMode
    mouse_state_changed = pyqtSignal(object)       # MouseState
    # 移除 window_state_changed 信号，改为按需检测
    
    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        
        # Store reference to the assistant controller (not necessarily a QObject)
        self.controller = controller
        
        # State variables
        self.current_mode = InteractionMode.NORMAL
        self.last_mouse_state: Optional[MouseState] = None
        # 移除 last_window_state，改为按需检测
        self.last_hotkey_time = 0
        self.hotkey_double_press_threshold = 0.5  # Double-click hotkey time threshold (seconds)
        
        # Monitor timer
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._monitor_system_state)
        self.monitor_timer.start(100)  # Check every 100ms
        
        # Game window title keywords (can be loaded from config)
        self.game_keywords = [
            'unity', 'unreal', 'steam', 'epic', 'origin',
            'helldivers', 'elden ring', 'civilization', 'dst', 'don\'t starve',
            '游戏', '全屏', 'fullscreen', 'gamemode', 'gaming'
        ]
        
        logger.info("SmartInteractionManager initialized successfully")
    
    def get_mouse_state(self) -> Optional[MouseState]:
        """Get current mouse state"""
        try:
            cursor_info = CURSORINFO()
            cursor_info.cbSize = ctypes.sizeof(CURSORINFO)
            
            if GetCursorInfo(ctypes.byref(cursor_info)):
                is_visible = bool(cursor_info.flags & CURSOR_SHOWING)
                is_suppressed = bool(cursor_info.flags & CURSOR_SUPPRESSED)
                position = (cursor_info.ptScreenPos.x, cursor_info.ptScreenPos.y)
                
                # Safely handle cursor handle - it may be None when mouse is hidden
                cursor_handle = 0  # Default value
                if cursor_info.hCursor is not None:
                    try:
                        cursor_handle = int(cursor_info.hCursor)
                    except (ValueError, TypeError):
                        cursor_handle = 0  # Fallback to 0 if conversion fails
                
                return MouseState(
                    is_visible=is_visible,
                    is_suppressed=is_suppressed,
                    position=position,
                    cursor_handle=cursor_handle
                )
            else:
                logger.warning("GetCursorInfo call failed")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get mouse state: {e}")
            return None
    
    def get_window_state(self) -> Optional[WindowState]:
        """Get current window state"""
        try:
            hwnd = GetForegroundWindow()
            if not hwnd:
                return None
                
            # Get window title
            buffer = ctypes.create_unicode_buffer(512)
            GetWindowTextW(hwnd, buffer, 512)
            window_title = buffer.value or ""
            
            # Check if it's a game window
            is_game_window = self._is_game_window(window_title)
            
            return WindowState(
                foreground_window=hwnd,
                window_title=window_title,
                is_game_window=is_game_window
            )
            
        except Exception as e:
            logger.error(f"Failed to get window state: {e}")
            return None
    
    def _is_game_window(self, window_title: str) -> bool:
        """Check if it's a game window"""
        if not window_title:
            return False
            
        title_lower = window_title.lower()
        
        # 排除应用程序自身的窗口
        app_window_keywords = [
            'gamewiki assistant',
            'gamewiki',
            'game wiki assistant',
            'game wiki'
        ]
        
        # 如果是应用程序自身的窗口，不视为游戏窗口（不记录日志）
        if any(app_keyword in title_lower for app_keyword in app_window_keywords):
            return False
        
        return any(keyword in title_lower for keyword in self.game_keywords)
    
    def _monitor_system_state(self):
        """Monitor system state changes - 只监控鼠标状态，不监控窗口变化"""
        try:
            # Get current mouse state
            mouse_state = self.get_mouse_state()
            
            # Check mouse state changes
            if mouse_state and (not self.last_mouse_state or 
                              mouse_state.is_visible != self.last_mouse_state.is_visible or
                              mouse_state.is_suppressed != self.last_mouse_state.is_suppressed):
                self.last_mouse_state = mouse_state
                self.mouse_state_changed.emit(mouse_state)
                logger.debug(f"Mouse state changed: visible={mouse_state.is_visible}, suppressed={mouse_state.is_suppressed}")
                
                # 只在鼠标状态变化时才重新计算交互模式
                window_state = self.get_window_state()
                new_mode = self._calculate_interaction_mode(mouse_state, window_state)
                if new_mode != self.current_mode:
                    old_mode = self.current_mode
                    self.current_mode = new_mode
                    self.interaction_mode_changed.emit(new_mode)
                    logger.info(f"Interaction mode changed: {old_mode.value} -> {new_mode.value}")
                
        except Exception as e:
            logger.error(f"Error monitoring system state: {e}")
    
    def _calculate_interaction_mode(self, mouse_state: Optional[MouseState], 
                                  window_state: Optional[WindowState]) -> InteractionMode:
        """Calculate current interaction mode"""
        if not mouse_state or not window_state:
            return InteractionMode.NORMAL
        
        # If current focus is a game window
        if window_state.is_game_window:
            # Mouse is hidden or suppressed
            if not mouse_state.is_visible or mouse_state.is_suppressed:
                return InteractionMode.GAME_HIDDEN
            else:
                return InteractionMode.GAME_VISIBLE
        
        return InteractionMode.NORMAL
    
    def should_enable_mouse_passthrough(self) -> bool:
        """Check if mouse passthrough should be enabled"""
        return self.current_mode == InteractionMode.GAME_HIDDEN
    
    def handle_hotkey_press(self, current_chat_visible: bool) -> str:
        """
        Handle hotkey press event
        
        Args:
            current_chat_visible: Whether the chat window (main_window) is currently visible
            
        Returns:
            Suggested action: 'show_chat', 'hide_chat', 'ignore', 'show_mouse'
        """
        current_time = time.time()
        time_since_last = current_time - self.last_hotkey_time
        self.last_hotkey_time = current_time
        
        # 获取当前状态用于调试
        mouse_state = self.get_mouse_state()
        window_state = self.get_window_state()
        
        logger.info(f"Hotkey triggered - mode: {self.current_mode.value}, chat visible: {current_chat_visible}, interval: {time_since_last:.2f}s")
        logger.debug(f"🖱️ Mouse state: visible={mouse_state.is_visible if mouse_state else 'None'}, suppressed={mouse_state.is_suppressed if mouse_state else 'None'}")
        logger.debug(f"🪟 Window state: title='{window_state.window_title if window_state else 'None'}', is_game={window_state.is_game_window if window_state else 'None'}")
        
        # 场景1：聊天窗口不可见 -> 显示聊天窗口
        if not current_chat_visible:
            logger.info("💬 Chat window not visible: Showing chat window")
            return 'show_chat'
        
        # 场景2&3：聊天窗口可见的情况
        if self.current_mode == InteractionMode.GAME_HIDDEN:
            # 游戏模式 + 鼠标隐藏 -> 显示鼠标，让用户与聊天窗口互动
            logger.info("🎮 Game mode (mouse hidden): Showing mouse for interaction")
            return 'show_mouse'
            
        elif time_since_last < self.hotkey_double_press_threshold:
            # 双击热键 -> 隐藏聊天窗口
            logger.info(f"⚡ Double-press detected ({time_since_last:.2f}s < {self.hotkey_double_press_threshold}s): Hiding chat window")
            return 'hide_chat'
            
        else:
            # 单击热键 + 聊天窗口可见 + 鼠标可见 -> 隐藏聊天窗口，根据设置处理悬浮窗
            if self.current_mode == InteractionMode.GAME_VISIBLE:
                logger.info("🎮 Game mode (mouse visible): Single press, hiding chat window")
            else:
                logger.info("🖥️ Normal mode: Single press, hiding chat window")
            return 'hide_chat'
    
    def apply_mouse_passthrough(self, widget: QWidget, enable: bool):
        """
        Apply or cancel mouse passthrough for the specified window
        
        Args:
            widget: Target window widget
            enable: Whether to enable mouse passthrough
        """
        try:
            if enable:
                # Enable mouse passthrough
                widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                # Keep window on top but don't respond to mouse events
                current_flags = widget.windowFlags()
                new_flags = current_flags | Qt.WindowType.WindowTransparentForInput
                widget.setWindowFlags(new_flags)
                logger.debug(f"Enabled mouse passthrough for window {widget}")
            else:
                # Disable mouse passthrough
                widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
                # Restore normal mouse event response
                current_flags = widget.windowFlags()
                new_flags = current_flags & ~Qt.WindowType.WindowTransparentForInput
                widget.setWindowFlags(new_flags)
                logger.debug(f"Disabled mouse passthrough for window {widget}")
                
            # Re-show window to apply settings
            if widget.isVisible():
                widget.show()
                
        except Exception as e:
            logger.error(f"Error applying mouse passthrough settings: {e}")
    
    def set_hotkey_double_press_threshold(self, threshold: float):
        """Set hotkey double-click time threshold"""
        self.hotkey_double_press_threshold = max(0.1, min(2.0, threshold))
        logger.info(f"Set hotkey double-click threshold: {self.hotkey_double_press_threshold} seconds") 

    def get_current_game_window(self) -> Optional[str]:
        """获取当前前台窗口的游戏名称（用于热键触发时检测）"""
        try:
            window_state = self.get_window_state()
            if window_state and window_state.is_game_window:
                logger.info(f"🎮 Current game window detected: '{window_state.window_title}'")
                return window_state.window_title
            else:
                # 检查是否是应用自身窗口，如果是则不记录日志
                if window_state and window_state.window_title:
                    title_lower = window_state.window_title.lower()
                    app_window_keywords = [
                        'gamewiki assistant', 'gamewiki', 'game wiki assistant', 'game wiki'
                    ]
                    if not any(app_keyword in title_lower for app_keyword in app_window_keywords):
                        logger.debug(f"🪟 Current window is not a game: '{window_state.window_title}'")
                return None
        except Exception as e:
            logger.error(f"Failed to get current game window: {e}")
            return None 