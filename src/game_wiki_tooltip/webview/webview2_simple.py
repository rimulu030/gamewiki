"""
Simplified WebView2 widget for PyQt6 - Alternative implementation
Uses minimal WebView2 features to avoid compatibility issues
"""

import sys
import os
import logging
import ctypes
from ctypes import wintypes
from typing import Optional
from pathlib import Path
import ctypes.wintypes

try:
    import clr
    PYTHONNET_AVAILABLE = True
except ImportError:
    PYTHONNET_AVAILABLE = False

from PyQt6.QtCore import QUrl, QTimer, pyqtSignal, QSize
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy

import win32gui
import win32con

logger = logging.getLogger(__name__)


class SimpleWebView2Widget(QWidget):
    """
    Simplified WebView2 wrapper with minimal dependencies
    """
    
    # Basic signals
    urlChanged = pyqtSignal(QUrl)
    loadFinished = pyqtSignal(bool)
    loadStarted = pyqtSignal()
    titleChanged = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.webview2 = None
        self.webview2_hwnd = None
        self.current_url = ""
        self.current_title = ""
        
        # Resize debouncing
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._do_resize_webview2)
        self._resize_debounce_ms = 200  # Wait 200ms after last resize event
        
        # Set size policy to expand
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Initialize UI
        self._init_ui()
        
        # Try to initialize WebView2
        if PYTHONNET_AVAILABLE:
            QTimer.singleShot(100, self._init_webview2)
    
    def _init_ui(self):
        """Initialize the UI layout"""
        # Use a proper layout to ensure correct size management
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Placeholder label
        self.placeholder = QLabel("Initializing WebView2...")
        self.placeholder.setStyleSheet("background-color: white; padding: 20px;")
        self.placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.placeholder)
    
    def _init_webview2(self):
        """Initialize WebView2 with minimal setup"""
        try:
            # Find assemblies
            dll_path = Path(__file__).parent / "webview2" / "lib"
            if not dll_path.exists():
                self._show_error("WebView2 DLLs not found. Run webview2_setup.py first.")
                return
            
            # Load assemblies
            clr.AddReference(str(dll_path / "Microsoft.Web.WebView2.WinForms.dll"))
            clr.AddReference("System.Windows.Forms")
            clr.AddReference("System")  # Add System reference for Uri
            
            # Import only what we need
            from Microsoft.Web.WebView2.WinForms import WebView2
            
            # Create WebView2
            self.webview2 = WebView2()
            
            # Get window handle as integer
            handle_str = str(self.webview2.Handle)
            self.webview2_hwnd = int(handle_str)
            
            # Ensure the window handle is valid
            if not win32gui.IsWindow(self.webview2_hwnd):
                raise Exception("Invalid window handle")
            
            # Embed into Qt window
            qt_hwnd = int(self.winId())
            win32gui.SetParent(self.webview2_hwnd, qt_hwnd)
            
            # Remove window decorations and set child style
            style = win32gui.GetWindowLong(self.webview2_hwnd, win32con.GWL_STYLE)
            style = (style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME & 
                    ~win32con.WS_SYSMENU & ~win32con.WS_BORDER & ~win32con.WS_POPUP) | win32con.WS_CHILD | win32con.WS_VISIBLE
            win32gui.SetWindowLong(self.webview2_hwnd, win32con.GWL_STYLE, style)
            
            # Also remove extended window styles that might affect sizing
            ex_style = win32gui.GetWindowLong(self.webview2_hwnd, win32con.GWL_EXSTYLE)
            ex_style = (ex_style & ~win32con.WS_EX_CLIENTEDGE & ~win32con.WS_EX_WINDOWEDGE & 
                       ~win32con.WS_EX_DLGMODALFRAME & ~win32con.WS_EX_STATICEDGE)
            win32gui.SetWindowLong(self.webview2_hwnd, win32con.GWL_EXSTYLE, ex_style)
            
            # Force window to update its non-client area
            win32gui.SetWindowPos(self.webview2_hwnd, 0, 0, 0, 0, 0,
                                win32con.SWP_FRAMECHANGED | win32con.SWP_NOMOVE | 
                                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            
            # Hide placeholder
            self.placeholder.hide()
            
            # Make WebView2 visible
            win32gui.ShowWindow(self.webview2_hwnd, win32con.SW_SHOW)
            
            # Try to initialize core first
            try:
                self.webview2.EnsureCoreWebView2Async(None)
            except:
                pass  # Ignore if method doesn't exist
            
            # Initial resize after WebView2 is ready
            QTimer.singleShot(100, self._do_resize_webview2)
            
            # Simple event connections
            QTimer.singleShot(500, self._connect_basic_events)
            
            logger.info("Simple WebView2 initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize WebView2: {e}")
            self._show_error(f"WebView2 Error: {str(e)}")
    
    def _connect_basic_events(self):
        """Connect basic events that should work"""
        try:
            # Try to connect navigation events
            if hasattr(self.webview2, 'NavigationCompleted'):
                self.webview2.NavigationCompleted += self._on_nav_completed
            if hasattr(self.webview2, 'SourceChanged'):
                self.webview2.SourceChanged += self._on_source_changed
            
            # Add new window request handling
            if hasattr(self.webview2, 'CoreWebView2'):
                # Delay a bit to wait for CoreWebView2 initialization
                QTimer.singleShot(1000, self._connect_new_window_handler)
                
        except Exception as e:
            logger.warning(f"Could not connect events: {e}")
    
    def _on_nav_completed(self, sender, args):
        """Navigation completed"""
        self.loadFinished.emit(True)
        # Inject JavaScript after page load completion
        QTimer.singleShot(100, self._inject_link_interceptor)
        # Extract title after navigation with longer delay for dynamic pages
        QTimer.singleShot(1500, self._extract_and_emit_title)
    
    def _on_source_changed(self, sender, args):
        """URL changed"""
        try:
            if hasattr(self.webview2, 'Source') and self.webview2.Source:
                url = str(self.webview2.Source)
                self.current_url = url
                self.urlChanged.emit(QUrl(url))
                # Extract title when URL changes
                QTimer.singleShot(1000, self._extract_title)
        except:
            pass
            
    def _extract_title(self):
        """Extract page title using JavaScript"""
        try:
            if self.webview2 and hasattr(self.webview2, 'CoreWebView2') and self.webview2.CoreWebView2:
                # More comprehensive title extraction
                script = """
                (function() {
                    var title = document.title;
                    if (title && title !== '' && title !== 'undefined') {
                        return title;
                    }
                    // Fallback to h1 if title is empty
                    var h1 = document.querySelector('h1');
                    if (h1 && h1.innerText) {
                        return h1.innerText.trim();
                    }
                    return '';
                })();
                """
                # Use ExecuteScriptAsync if available
                if hasattr(self.webview2.CoreWebView2, 'ExecuteScriptAsync'):
                    self.webview2.CoreWebView2.ExecuteScriptAsync(script)
                    # Check for title change after a delay
                    QTimer.singleShot(500, self._check_and_emit_title)
                elif hasattr(self.webview2, 'ExecuteScriptAsync'):
                    self.webview2.ExecuteScriptAsync(script)
                    QTimer.singleShot(500, self._check_and_emit_title)
        except Exception as e:
            logger.warning(f"Failed to extract title: {e}")
            
    def _check_and_emit_title(self):
        """Check if we have a title and emit it"""
        try:
            # Try to get the title from the document
            if hasattr(self.webview2, 'CoreWebView2') and self.webview2.CoreWebView2:
                # Extract title from DOM
                script = """
                (function() {
                    var title = document.title;
                    if (title && title !== '' && title !== 'undefined' && !title.includes('duckduckgo.com')) {
                        // Clean up title - remove site suffix if present
                        title = title.replace(/ - .* Wiki.*$/i, '');
                        title = title.replace(/ \\| .* Wiki.*$/i, '');
                        return title.trim();
                    }
                    return '';
                })();
                """
                # We can't get the result directly, but the title should be in document.title
                # Emit title changed signal with current URL
                if self.current_url and self.current_title != self.current_url:
                    # Only emit if we have a proper title
                    self.titleChanged.emit(self.current_title)
        except Exception as e:
            logger.warning(f"Failed to check and emit title: {e}")
            
    def _extract_and_emit_title(self):
        """Extract title and emit titleChanged signal"""
        try:
            if self.webview2 and hasattr(self.webview2, 'CoreWebView2') and self.webview2.CoreWebView2:
                # JavaScript to extract and return title
                script = """
                (function() {
                    var title = document.title;
                    if (title && title !== '' && title !== 'undefined') {
                        // Return title as-is without modification
                        return title;
                    }
                    // Fallback to h1
                    var h1 = document.querySelector('h1');
                    if (h1 && h1.innerText) {
                        return h1.innerText.trim();
                    }
                    return '';
                })();
                """
                
                # Since we can't get the async result directly, we'll monitor document.title
                # Execute the script to ensure title is properly set
                self.webview2.CoreWebView2.ExecuteScriptAsync(script)
                
                # Check document.title after a short delay
                QTimer.singleShot(200, self._emit_title_from_document)
        except Exception as e:
            logger.warning(f"Failed to extract and emit title: {e}")
            
    def _emit_title_from_document(self):
        """Emit title from document.title"""
        try:
            # Skip title extraction for WebView2 - it causes crashes
            # The titleChanged signal from WebView2 itself should handle this
            logger.info("Skipping manual title extraction for WebView2 to avoid crashes")
            pass
        except Exception as e:
            logger.warning(f"Failed to emit title from document: {e}")
    
            
    def _check_title_via_script(self):
        """Check title by injecting and reading JavaScript"""
        try:
            # Inject script to set title in a known location
            script = """
            (function() {
                var title = document.title;
                if (window.__webview2_title !== title) {
                    window.__webview2_title = title;
                    // Try to trigger a detectable event
                    if (title && title !== '') {
                        console.log('TITLE:' + title);
                    }
                }
                return title;
            })();
            """
            self.runJavaScript(script)
            
            # For now, we'll rely on the page's title tag being updated
            # and detected through other means
        except Exception as e:
            logger.warning(f"Failed to check title via script: {e}")
    
    def _connect_new_window_handler(self):
        """Connect new window request handler"""
        try:
            if self.webview2 and hasattr(self.webview2, 'CoreWebView2') and self.webview2.CoreWebView2:
                self.webview2.CoreWebView2.NewWindowRequested += self._on_new_window_requested
                logger.info("Successfully connected NewWindowRequested handler")
                
                # Also inject JavaScript to intercept all link clicks
                self._inject_link_interceptor()
        except Exception as e:
            logger.warning(f"Could not connect new window handler: {e}")
    
    def _on_new_window_requested(self, sender, args):
        """Handle new window request, open in current window"""
        try:
            # Get the requested URL
            uri = args.Uri
            
            # Navigate to the URL in the current window
            from System import Uri
            self.webview2.Source = Uri(uri)
            
            # Mark event as handled, prevent opening new window
            args.Handled = True
            
            logger.info(f"Intercepted new window request, navigating to: {uri}")
        except Exception as e:
            logger.error(f"Error handling new window request: {e}")
    
    def _inject_link_interceptor(self):
        """Inject JavaScript to intercept all link clicks"""
        script = """
        (function() {
            // Intercept all link clicks
            document.addEventListener('click', function(e) {
                var target = e.target;
                while (target && target.tagName !== 'A') {
                    target = target.parentElement;
                }
                if (target && target.tagName === 'A' && target.href) {
                    e.preventDefault();
                    window.location.href = target.href;
                }
            }, true);
            
            // Handle dynamically added content
            var observer = new MutationObserver(function() {
                // Re-bind events (if needed)
            });
            observer.observe(document.body, { childList: true, subtree: true });
        })();
        """
        self.runJavaScript(script)
    
    def _resize_webview2(self):
        """Start the resize debounce timer"""
        # Cancel any existing timer and start a new one
        self._resize_timer.stop()
        self._resize_timer.start(self._resize_debounce_ms)
        
    def _do_resize_webview2(self):
        """Resize WebView2 to match parent widget size - using PHYSICAL PIXELS"""
        if not self.webview2_hwnd:
            return
            
        try:
            # Get the Qt widget's size in logical pixels
            rect = self.rect()
            logical_width = rect.width()
            logical_height = rect.height()
            
            # Make sure we have valid dimensions
            if logical_width <= 0 or logical_height <= 0:
                logger.warning(f"Invalid dimensions: {logical_width}x{logical_height}")
                return
            
            # Get DPI scale and convert to physical pixels
            scale = self._get_dpi_scale()
            physical_width = int(logical_width * scale)
            physical_height = int(logical_height * scale)
            
            logger.info(f"Resizing WebView2: {logical_width}x{logical_height} logical -> {physical_width}x{physical_height} physical pixels (DPI scale: {scale})")
            
            # Ensure the window is valid
            if not win32gui.IsWindow(self.webview2_hwnd):
                logger.error("WebView2 window handle is invalid")
                return
            
            # Set both .NET control and Windows HWND to physical pixels
            success = False
            
            # Method 1: Set .NET Control Size using physical pixels
            try:
                if self.webview2:
                    # Import System.Drawing types
                    from System.Drawing import Size, Rectangle
                    
                    # Set the .NET control size using PHYSICAL pixels
                    new_size = Size(physical_width, physical_height)
                    if hasattr(self.webview2, 'Size'):
                        self.webview2.Size = new_size
                        logger.info(f"Set .NET WebView2.Size to {physical_width}x{physical_height} physical pixels")
                    
                    if hasattr(self.webview2, 'ClientSize'):
                        self.webview2.ClientSize = new_size
                        logger.info(f"Set .NET WebView2.ClientSize to {physical_width}x{physical_height} physical pixels")
                    
                    if hasattr(self.webview2, 'Bounds'):
                        bounds = Rectangle(0, 0, physical_width, physical_height)
                        self.webview2.Bounds = bounds
                        logger.info(f"Set .NET WebView2.Bounds to {physical_width}x{physical_height} physical pixels")
                    
                    success = True
                    
            except Exception as e:
                logger.warning(f"Could not set .NET control size: {e}")
            
            # Method 2: Use Windows API with physical pixels
            try:
                result = win32gui.SetWindowPos(
                    self.webview2_hwnd,
                    0,  # HWND_TOP
                    0, 0,  # x, y position
                    physical_width, physical_height,  # physical dimensions
                    win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
                )
                
                if result != 0:
                    logger.info(f"SetWindowPos succeeded with {physical_width}x{physical_height} physical pixels")
                    success = True
                else:
                    import ctypes
                    error = ctypes.windll.kernel32.GetLastError()
                    logger.warning(f"SetWindowPos failed with error: {error}")
                    
            except Exception as e:
                logger.error(f"SetWindowPos exception: {e}")
            
            # Force refresh
            if success:
                try:
                    win32gui.InvalidateRect(self.webview2_hwnd, None, True)
                    win32gui.UpdateWindow(self.webview2_hwnd)
                    self.update()
                except:
                    pass
            
        except Exception as e:
            logger.error(f"Error resizing WebView2: {e}")
    
    
    def _get_dpi_scale(self):
        """Get DPI scale factor"""
        try:
            # Try to get DPI scale from Windows
            import ctypes
            user32 = ctypes.windll.user32
            dc = user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
            user32.ReleaseDC(0, dc)
            return dpi / 96.0
        except:
            return 1.0
    
    
    def _show_error(self, message: str):
        """Show error message"""
        self.placeholder.setText(message)
        self.placeholder.show()
    
    # Public API (minimal)
    
    def setUrl(self, url: QUrl):
        """Load URL"""
        if self.webview2:
            try:
                # Convert to System.Uri for .NET
                from System import Uri
                url_string = url.toString()
                self.webview2.Source = Uri(url_string)
                self.current_url = url_string
            except Exception as e:
                logger.error(f"Failed to set URL: {e}")
    
    def load(self, url: QUrl):
        """Load URL (alias)"""
        self.setUrl(url)
    
    def url(self) -> QUrl:
        """Get current URL"""
        return QUrl(self.current_url)
    
    def reload(self):
        """Reload page"""
        if self.webview2:
            try:
                self.webview2.Reload()
            except:
                pass
    
    def back(self):
        """Go back"""
        if self.webview2:
            try:
                if hasattr(self.webview2, 'GoBack'):
                    self.webview2.GoBack()
            except:
                pass
    
    def forward(self):
        """Go forward"""
        if self.webview2:
            try:
                if hasattr(self.webview2, 'GoForward'):
                    self.webview2.GoForward()
            except:
                pass
    
    def stop(self):
        """Stop loading"""
        if self.webview2:
            try:
                if hasattr(self.webview2, 'Stop'):
                    self.webview2.Stop()
            except:
                pass
    
    def page(self):
        """Return self for compatibility"""
        return self
    
    def history(self):
        """Return history object"""
        widget = self
        class History:
            def canGoBack(self):
                if widget.webview2:
                    try:
                        return widget.webview2.CanGoBack
                    except:
                        return False
                return False
            
            def canGoForward(self):
                if widget.webview2:
                    try:
                        return widget.webview2.CanGoForward
                    except:
                        return False
                return False
        return History()
    
    def settings(self):
        """Return mock settings"""
        class MockSettings:
            def setAttribute(self, attr, value): pass
        return MockSettings()
    
    def runJavaScript(self, script: str, callback=None):
        """Execute JavaScript code"""
        if self.webview2:
            try:
                # Check if CoreWebView2 is available
                if hasattr(self.webview2, 'CoreWebView2') and self.webview2.CoreWebView2:
                    # Execute script asynchronously
                    self.webview2.CoreWebView2.ExecuteScriptAsync(script)
                elif hasattr(self.webview2, 'ExecuteScriptAsync'):
                    # Try direct method
                    self.webview2.ExecuteScriptAsync(script)
                else:
                    logger.warning("JavaScript execution not available")
                
                # For simplicity, call callback with None
                if callback:
                    QTimer.singleShot(100, lambda: callback(None))
            except Exception as e:
                logger.error(f"Failed to execute JavaScript: {e}")
                if callback:
                    callback(None)
        else:
            logger.warning("WebView2 not initialized, cannot execute JavaScript")
            if callback:
                callback(None)
    
    # Qt events
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_webview2()
    
    def showEvent(self, event):
        super().showEvent(event)
        # Delay resize to ensure widget is fully shown (no debouncing for show event)
        QTimer.singleShot(0, self._do_resize_webview2)
        QTimer.singleShot(100, self._do_resize_webview2)
    
    def sizeHint(self) -> QSize:
        """Provide a size hint for the layout system"""
        # Return a reasonable default size hint
        return QSize(800, 600)
    
    def minimumSizeHint(self) -> QSize:
        """Provide a minimum size hint"""
        return QSize(400, 300)
    
    def paintEvent(self, event):
        """Handle paint events"""
        super().paintEvent(event)
        # Simplified - no complex checking in paint event