"""
WebView2 widget for PyQt6 - A lightweight alternative to QWebEngineView
Uses Microsoft Edge WebView2 for better performance and smaller file size
"""

import sys
import os
import logging
import ctypes
from ctypes import wintypes
from typing import Optional, Callable
from pathlib import Path

try:
    import clr
    PYTHONNET_AVAILABLE = True
except ImportError:
    PYTHONNET_AVAILABLE = False
    print("Warning: pythonnet not available. WebView2 functionality will be limited.")

from PyQt6.QtCore import (
    QUrl, QTimer, pyqtSignal, QRect, QPoint, QSize,
    QObject, QThread, pyqtSlot
)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtGui import QWindow

import win32gui
import win32con
import win32api

logger = logging.getLogger(__name__)


class WebView2Widget(QWidget):
    """
    WebView2 wrapper that mimics QWebEngineView API
    Provides a lightweight alternative using Microsoft Edge WebView2
    """
    
    # Signals to match QWebEngineView API
    urlChanged = pyqtSignal(QUrl)
    loadFinished = pyqtSignal(bool)
    loadStarted = pyqtSignal()
    titleChanged = pyqtSignal(str)
    loadProgress = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.webview2 = None
        self.webview2_hwnd = None
        self.current_url = ""
        self.current_title = ""
        self._is_loading = False
        self._message_processor = None
        
        # Initialize UI
        self._init_ui()
        
        # Try to initialize WebView2
        if PYTHONNET_AVAILABLE:
            QTimer.singleShot(100, self._init_webview2)
        else:
            self._show_error("pythonnet not installed. Please install it with: pip install pythonnet")
    
    def _init_ui(self):
        """Initialize the UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Placeholder for when WebView2 is not available
        self.placeholder = QLabel("Initializing WebView2...")
        self.placeholder.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #666;
                font-size: 14px;
                padding: 20px;
            }
        """)
        layout.addWidget(self.placeholder)
        self.placeholder.hide()
    
    def _init_webview2(self):
        """Initialize WebView2 control"""
        try:
            # Add references to WebView2 assemblies
            webview2_path = self._find_webview2_assemblies()
            if not webview2_path:
                self._show_error("WebView2 assemblies not found. Please ensure WebView2 SDK is installed.")
                return
            
            clr.AddReference(str(webview2_path / "Microsoft.Web.WebView2.Core.dll"))
            clr.AddReference(str(webview2_path / "Microsoft.Web.WebView2.WinForms.dll"))
            clr.AddReference("System.Windows.Forms")
            
            # Import .NET types
            from Microsoft.Web.WebView2.WinForms import WebView2
            from System.Windows.Forms import Application, Control
            
            # Debug: List available types in the assembly
            try:
                import Microsoft.Web.WebView2.Core as core_module
                logger.info("Available types in WebView2.Core:")
                for attr in dir(core_module):
                    if not attr.startswith('_'):
                        logger.info(f"  - {attr}")
            except Exception as e:
                logger.warning(f"Could not list WebView2.Core types: {e}")
            
            # Create WebView2 control
            self.webview2 = WebView2()
            
            # Set user data folder directly (without CoreWebView2CreationProperties)
            user_data_folder = str(Path.home() / ".gamewiki" / "webview2_data")
            Path(user_data_folder).mkdir(parents=True, exist_ok=True)
            
            # Try to set CreationProperties if available
            try:
                from Microsoft.Web.WebView2.Core import CoreWebView2CreationProperties
                props = CoreWebView2CreationProperties()
                props.UserDataFolder = user_data_folder
                self.webview2.CreationProperties = props
            except ImportError:
                # If CoreWebView2CreationProperties is not available, try alternative approach
                logger.info("CoreWebView2CreationProperties not available, using default settings")
            
            # Get the window handle
            self.webview2_hwnd = int(self.webview2.Handle.ToString())
            
            # Embed into Qt window
            self._embed_webview2()
            
            # Connect events
            self._connect_webview2_events()
            
            # Start message processor
            self._message_processor = MessageProcessor(self)
            
            # Hide placeholder
            self.placeholder.hide()
            
            logger.info("WebView2 initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize WebView2: {e}")
            self._show_error(f"Failed to initialize WebView2: {str(e)}")
    
    def _find_webview2_assemblies(self) -> Optional[Path]:
        """Find WebView2 assemblies in common locations"""
        # Common locations for WebView2 SDK
        possible_paths = [
            Path(__file__).parent / "webview2" / "lib",
            Path.home() / ".nuget" / "packages" / "Microsoft.Web.WebView2" / "1.0.1245.22" / "lib" / "net45",
            Path.home() / ".nuget" / "packages" / "Microsoft.Web.WebView2" / "1.0.2210.55" / "lib" / "net45",
            Path("C:/Program Files/Microsoft/EdgeWebView/x64"),
            Path(os.environ.get("WEBVIEW2_SDK_PATH", ""))
        ]
        
        logger.info("Searching for WebView2 assemblies...")
        for path in possible_paths:
            if path.exists():
                logger.info(f"Checking path: {path}")
                core_dll = path / "Microsoft.Web.WebView2.Core.dll"
                winforms_dll = path / "Microsoft.Web.WebView2.WinForms.dll"
                if core_dll.exists() and winforms_dll.exists():
                    logger.info(f"Found WebView2 assemblies at: {path}")
                    return path
        
        logger.error("WebView2 assemblies not found in any location")
        return None
    
    def _embed_webview2(self):
        """Embed WebView2 window into Qt widget"""
        if not self.webview2_hwnd:
            return
        
        # Get Qt window handle
        qt_hwnd = int(self.winId())
        
        # Set WebView2 as child window
        win32gui.SetParent(self.webview2_hwnd, qt_hwnd)
        
        # Remove window decorations
        style = win32gui.GetWindowLong(self.webview2_hwnd, win32con.GWL_STYLE)
        style = style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME & ~win32con.WS_SYSMENU
        style = style | win32con.WS_CHILD | win32con.WS_VISIBLE
        win32gui.SetWindowLong(self.webview2_hwnd, win32con.GWL_STYLE, style)
        
        # Initial resize
        self._resize_webview2()
    
    def _connect_webview2_events(self):
        """Connect WebView2 events to Qt signals"""
        if not self.webview2:
            return
        
        try:
            # Ensure WebView2 is ready first
            self.webview2.EnsureCoreWebView2Async(None)
            
            # Wait a bit for initialization
            QTimer.singleShot(500, self._connect_events_delayed)
            
        except Exception as e:
            logger.error(f"Failed to initialize WebView2 core: {e}")
            self._connect_events_delayed()
    
    def _connect_events_delayed(self):
        """Connect events after a delay to ensure WebView2 is ready"""
        try:
            # Navigation events
            self.webview2.NavigationStarting += self._on_navigation_starting
            self.webview2.NavigationCompleted += self._on_navigation_completed
            self.webview2.SourceChanged += self._on_source_changed
            
            # Try to connect DocumentTitleChanged if available
            if hasattr(self.webview2, 'DocumentTitleChanged'):
                self.webview2.DocumentTitleChanged += self._on_title_changed
            elif hasattr(self.webview2, 'CoreWebView2') and self.webview2.CoreWebView2:
                # Alternative: connect to CoreWebView2's DocumentTitleChanged
                self.webview2.CoreWebView2.DocumentTitleChanged += self._on_title_changed
                
            logger.info("WebView2 events connected successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect WebView2 events: {e}")
    
    def _on_navigation_starting(self, sender, args):
        """Handle navigation starting event"""
        self._is_loading = True
        self.loadStarted.emit()
    
    def _on_navigation_completed(self, sender, args):
        """Handle navigation completed event"""
        self._is_loading = False
        success = args.IsSuccess if hasattr(args, 'IsSuccess') else True
        self.loadFinished.emit(success)
    
    def _on_source_changed(self, sender, args):
        """Handle source (URL) changed event"""
        try:
            if self.webview2 and self.webview2.Source:
                new_url = str(self.webview2.Source)
                self.current_url = new_url
                self.urlChanged.emit(QUrl(new_url))
        except Exception as e:
            logger.error(f"Error in source changed handler: {e}")
    
    def _on_title_changed(self, sender, args):
        """Handle document title changed event"""
        try:
            new_title = None
            
            # Try different ways to get the title
            if hasattr(self.webview2, 'CoreWebView2') and self.webview2.CoreWebView2:
                if hasattr(self.webview2.CoreWebView2, 'DocumentTitle'):
                    new_title = str(self.webview2.CoreWebView2.DocumentTitle)
            elif hasattr(self.webview2, 'DocumentTitle'):
                new_title = str(self.webview2.DocumentTitle)
            elif hasattr(sender, 'DocumentTitle'):
                new_title = str(sender.DocumentTitle)
                
            if new_title:
                self.current_title = new_title
                self.titleChanged.emit(new_title)
        except Exception as e:
            logger.error(f"Error in title changed handler: {e}")
    
    def _resize_webview2(self):
        """Resize WebView2 to fit the widget"""
        if not self.webview2_hwnd:
            return
        
        rect = self.rect()
        win32gui.MoveWindow(
            self.webview2_hwnd,
            0, 0,
            rect.width(), rect.height(),
            True
        )
    
    def _show_error(self, message: str):
        """Show error message in placeholder"""
        self.placeholder.setText(f"WebView2 Error: {message}")
        self.placeholder.show()
    
    # Public API matching QWebEngineView
    
    def setUrl(self, url: QUrl):
        """Load the specified URL"""
        if self.webview2:
            try:
                url_string = url.toString()
                self.webview2.Source = url_string
                self.current_url = url_string
            except Exception as e:
                logger.error(f"Failed to set URL: {e}")
    
    def load(self, url: QUrl):
        """Load the specified URL (alias for setUrl)"""
        self.setUrl(url)
    
    def url(self) -> QUrl:
        """Get the current URL"""
        return QUrl(self.current_url)
    
    def title(self) -> str:
        """Get the current page title"""
        return self.current_title
    
    def reload(self):
        """Reload the current page"""
        if self.webview2:
            try:
                self.webview2.Reload()
            except Exception as e:
                logger.error(f"Failed to reload: {e}")
    
    def back(self):
        """Navigate back in history"""
        if self.webview2 and self.webview2.CanGoBack:
            try:
                self.webview2.GoBack()
            except Exception as e:
                logger.error(f"Failed to go back: {e}")
    
    def forward(self):
        """Navigate forward in history"""
        if self.webview2 and self.webview2.CanGoForward:
            try:
                self.webview2.GoForward()
            except Exception as e:
                logger.error(f"Failed to go forward: {e}")
    
    def stop(self):
        """Stop loading the current page"""
        if self.webview2:
            try:
                self.webview2.Stop()
            except Exception as e:
                logger.error(f"Failed to stop loading: {e}")
    
    def history(self):
        """Get navigation history (simplified)"""
        # Return a mock history object with basic functionality
        class MockHistory:
            def canGoBack(self):
                return self.webview2.CanGoBack if self.webview2 else False
            
            def canGoForward(self):
                return self.webview2.CanGoForward if self.webview2 else False
        
        return MockHistory()
    
    def page(self):
        """Return self as a simplified page object"""
        return self
    
    def settings(self):
        """Return a mock settings object"""
        # Return a mock settings object that does nothing
        class MockSettings:
            def setAttribute(self, attr, value):
                pass
        
        return MockSettings()
    
    def runJavaScript(self, script: str, callback: Optional[Callable] = None):
        """
        Execute JavaScript code and optionally call a callback with the result
        This method mimics QWebEngineView's page().runJavaScript() API
        """
        if not self.webview2 or not self.webview2.CoreWebView2:
            logger.warning("WebView2 not initialized, cannot execute JavaScript")
            if callback:
                callback(None)
            return
        
        try:
            # Use async wrapper to handle the ExecuteScriptAsync call
            QTimer.singleShot(0, lambda: self._execute_javascript_async(script, callback))
        except Exception as e:
            logger.error(f"Failed to execute JavaScript: {e}")
            if callback:
                callback(None)
    
    def _execute_javascript_async(self, script: str, callback: Optional[Callable] = None):
        """Execute JavaScript asynchronously using WebView2's ExecuteScriptAsync"""
        try:
            # Import .NET types if available
            from System.Threading.Tasks import Task
            
            def on_complete(task):
                """Handle the completion of the JavaScript execution"""
                try:
                    if task.IsCompletedSuccessfully:
                        result = task.Result
                        # WebView2 returns JSON-encoded strings, try to decode if possible
                        try:
                            import json
                            # Try to decode JSON result
                            if result and result.startswith('"') and result.endswith('"'):
                                # It's a JSON string, decode it
                                result = json.loads(result)
                            elif result and result in ['true', 'false']:
                                result = result == 'true'
                            elif result and result.isdigit():
                                result = int(result)
                        except:
                            # If JSON decoding fails, keep the original result
                            pass
                        
                        if callback:
                            callback(result)
                    else:
                        logger.error(f"JavaScript execution failed: {task.Exception}")
                        if callback:
                            callback(None)
                except Exception as e:
                    logger.error(f"Error in JavaScript callback: {e}")
                    if callback:
                        callback(None)
            
            # Execute the script asynchronously
            task = self.webview2.CoreWebView2.ExecuteScriptAsync(script)
            
            # Handle the task completion
            task.ContinueWith(on_complete)
            
        except Exception as e:
            logger.error(f"Failed to execute JavaScript asynchronously: {e}")
            if callback:
                callback(None)
    
    # Qt event handlers
    
    def resizeEvent(self, event):
        """Handle widget resize"""
        super().resizeEvent(event)
        self._resize_webview2()
    
    def showEvent(self, event):
        """Handle widget show"""
        super().showEvent(event)
        self._resize_webview2()
    
    def focusInEvent(self, event):
        """Handle focus in event"""
        super().focusInEvent(event)
        if self.webview2_hwnd:
            try:
                win32gui.SetFocus(self.webview2_hwnd)
            except Exception as e:
                logger.error(f"Failed to set focus: {e}")


class MessageProcessor(QObject):
    """Process Windows messages for WebView2 to avoid blocking Qt"""
    
    def __init__(self, webview_widget: WebView2Widget):
        super().__init__()
        self.widget = webview_widget
        self.timer = QTimer()
        self.timer.timeout.connect(self._process_messages)
        self.timer.start(10)  # Process messages every 10ms
        
        # Windows message constants
        self.WM_QUIT = 0x0012
        self.PM_NOREMOVE = 0x0000
        self.PM_REMOVE = 0x0001
    
    def _process_messages(self):
        """Process Windows messages for WebView2"""
        if not self.widget.webview2_hwnd:
            return
        
        try:
            user32 = ctypes.windll.user32
            msg = wintypes.MSG()
            
            # Process up to 10 messages per cycle to avoid blocking
            count = 0
            while count < 10 and user32.PeekMessageW(
                ctypes.byref(msg),
                None,  # Process all messages
                0, 0,
                self.PM_REMOVE
            ):
                if msg.message == self.WM_QUIT:
                    break
                
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
                count += 1
                
        except Exception as e:
            logger.error(f"Error processing messages: {e}")
    
    def stop(self):
        """Stop processing messages"""
        self.timer.stop()


def check_webview2_runtime() -> bool:
    """Check if WebView2 Runtime is installed"""
    import winreg
    
    try:
        # Check for WebView2 Runtime in registry
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        winreg.CloseKey(key)
        return True
    except:
        pass
    
    # Also check for Edge installation
    try:
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\Edge\BLBeacon"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        version = winreg.QueryValueEx(key, "version")[0]
        winreg.CloseKey(key)
        # Edge version 83+ includes WebView2
        return int(version.split('.')[0]) >= 83
    except:
        return False


def install_webview2_runtime(silent: bool = True) -> bool:
    """Download and install WebView2 Runtime"""
    import urllib.request
    import subprocess
    import tempfile
    
    if check_webview2_runtime():
        return True
    
    try:
        # Download WebView2 Runtime installer
        url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
            urllib.request.urlretrieve(url, tmp.name)
            
            # Run installer
            args = [tmp.name]
            if silent:
                args.extend(["/silent", "/install"])
            
            result = subprocess.run(args, capture_output=True)
            
            # Clean up
            os.unlink(tmp.name)
            
            return result.returncode == 0
            
    except Exception as e:
        logger.error(f"Failed to install WebView2 Runtime: {e}")
        return False