"""
Wiki view widget for displaying web content.
"""

import time
import logging

from src.game_wiki_tooltip.core.i18n import t

logger = logging.getLogger(__name__)

from PyQt6.QtCore import (
    Qt, QTimer, QUrl, pyqtSignal
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QPushButton, QLineEdit, QLabel, QSizePolicy
)

# Always use WebView2 for web content
USE_WEBVIEW2 = True

# Import WebView2Widget if enabled
if USE_WEBVIEW2:
    try:
        # Try the new WinRT implementation first
        from src.game_wiki_tooltip.webview2_winrt import WebView2WinRTWidget as WebView2Widget
        from src.game_wiki_tooltip.webview2_winrt import check_webview2_runtime
        WEBVIEW2_AVAILABLE = True
        print("Using PyWinRT WebView2 implementation")
        # Check if WebView2 Runtime is installed
        if not check_webview2_runtime():
            print("Warning: WebView2 Runtime not installed. Video playback may be limited.")
            print("Visit https://go.microsoft.com/fwlink/p/?LinkId=2124703 to install WebView2 Runtime.")
    except ImportError as e:
        print(f"Warning: WebView2WinRTWidget not available: {e}")
        # Fallback to simple implementation if available
        print(f"Warning: No WebView2 implementation available")
        WEBVIEW2_AVAILABLE = False
        USE_WEBVIEW2 = False  # WebView2 failed to initialize
else:
    WEBVIEW2_AVAILABLE = False

class WikiView(QWidget):
    """Wiki page viewer - simplified version to avoid crashes"""

    back_requested = pyqtSignal()
    wiki_page_loaded = pyqtSignal(str, str)
    close_requested = pyqtSignal()  # Signal to close the window

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_search_url = ""  # Store search URL
        self.current_search_title = ""  # Store search title
        self.web_view = None
        self.content_widget = None
        self._webview_ready = False
        self._is_paused = False  # Add pause state flag
        self._pause_lock = False  # Add pause lock to prevent duplicate calls

        # URL monitoring for wiki detection
        self._url_monitor_timer = QTimer()
        self._url_monitor_timer.timeout.connect(self._monitor_wiki_navigation)
        self._monitoring_start_url = None
        
        # Enable mouse tracking for better edge detection
        self.setMouseTracking(True)

        self.init_ui()

    def init_ui(self):
        """Initialize the wiki view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet("""
                QFrame {
                    background-color: #f8f9fa;
                    border-bottom: 1px solid #e0e0e0;
                }
            """)

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 0, 10, 0)

        # Back to chat button
        self.back_button = QPushButton(t("btn_back_to_chat"))
        self.back_button.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    color: #4096ff;
                    font-size: 14px;
                    padding: 8px 12px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #e8f0fe;
                    border-radius: 4px;
                }
            """)
        self.back_button.clicked.connect(self.back_requested.emit)

        # Navigation button style
        nav_button_style = """
                QPushButton {
                    background-color: transparent;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    color: #5f6368;
                    font-size: 16px;
                    padding: 4px 4px;
                    min-width: 28px;
                    max-width: 28px;
                }
                QPushButton:hover {
                    background-color: #f0f0f0;
                    border-color: #d0d0d0;
                }
                QPushButton:pressed {
                    background-color: #e0e0e0;
                }
                QPushButton:disabled {
                    color: #c0c0c0;
                    border-color: #f0f0f0;
                }
            """

        # Browser navigation buttons
        self.nav_back_button = QPushButton("◀")
        self.nav_back_button.setStyleSheet(nav_button_style)
        self.nav_back_button.setToolTip(t("tooltip_nav_back"))
        self.nav_back_button.setEnabled(False)

        self.nav_forward_button = QPushButton("▶")
        self.nav_forward_button.setStyleSheet(nav_button_style)
        self.nav_forward_button.setToolTip(t("tooltip_nav_forward"))
        self.nav_forward_button.setEnabled(False)

        self.refresh_button = QPushButton("🔄")
        self.refresh_button.setStyleSheet(nav_button_style)
        self.refresh_button.setToolTip(t("tooltip_refresh"))

        # URL bar
        self.url_bar = QLineEdit()
        self.url_bar.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    padding: 6px 10px;
                    font-size: 13px;
                    background: white;
                    color: #202124;
                }
                QLineEdit:focus {
                    border-color: #4096ff;
                    outline: none;
                }
            """)
        self.url_bar.setPlaceholderText(t("placeholder_url_bar"))

        # Open in browser button
        self.open_browser_button = QPushButton(t("btn_open_browser"))
        self.open_browser_button.setStyleSheet("""
                QPushButton {
                    background-color: #4096ff;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #2d7ff9;
                }
            """)
        self.open_browser_button.clicked.connect(self.open_in_browser)

        # Close button
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.close_button.setToolTip(t("tooltip_close_window"))
        self.close_button.clicked.connect(self.close_requested.emit)

        # Add all widgets to toolbar
        toolbar_layout.addWidget(self.back_button)
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(self.nav_back_button)
        toolbar_layout.addWidget(self.nav_forward_button)
        toolbar_layout.addWidget(self.refresh_button)
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(self.url_bar, 1)  # URL bar takes remaining space
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(self.open_browser_button)
        toolbar_layout.addSpacing(5)
        toolbar_layout.addWidget(self.close_button)

        # Content area - delayed WebView creation
        self.web_view = None
        self.content_widget = None
        self._webview_initialized = False
        self._webview_initializing = False

        # Create placeholder widget first
        self.placeholder_widget = QFrame()
        self.placeholder_widget.setStyleSheet("""
                QFrame {
                    background-color: #f8f9fa;
                    border: 1px solid #e0e0e0;
                }
            """)
        placeholder_layout = QVBoxLayout(self.placeholder_widget)
        self.placeholder_label = QLabel(t("label_loading"))
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setStyleSheet("color: #666; font-size: 14px;")
        placeholder_layout.addWidget(self.placeholder_label)

        self.content_widget = self.placeholder_widget

        layout.addWidget(toolbar)
        layout.addWidget(self.content_widget)

        # Store current URL and title
        self.current_url = ""
        self.current_title = ""

        # WebView2 initialization will be started when needed or when event loop is running
        self._webview_init_requested = False  # Track if initialization was requested

    def ensure_webview_ready(self):
        """Ensure WebView2 is initialized and ready - safe to call anytime"""
        if self._webview_initialized:
            logger.info("WebView2 already initialized and ready")
            return
        if self._webview_initializing or self._webview_init_requested:
            logger.info("WebView2 initialization already requested/in progress")
            return
        logger.info("Ensuring WebView2 is ready, triggering initialization")
        self._webview_init_requested = True
        QTimer.singleShot(200, self._initialize_webview_async)

    def load_url(self, url: str):
        """Load a URL in the web view"""
        if self.web_view:  # Don't wait for _webview_initialized - let inner widget handle queuing
            try:
                # Use the load method which is compatible with WebView2WinRTWidget
                if hasattr(self.web_view, 'load'):
                    self.web_view.load(QUrl(url))
                elif hasattr(self.web_view, 'setUrl'):
                    self.web_view.setUrl(QUrl(url))
                else:
                    print(f"WebView has no load or setUrl method")
                self.current_url = url
            except Exception as e:
                print(f"Failed to load URL: {e}")
        else:
            # Store pending URL, will be loaded when WebView is ready
            self._pending_url = url
            print(f"WebView2 not ready, storing URL for later: {url}")
            # Ensure WebView initialization is triggered
            self.ensure_webview_ready()

    def _connect_navigation_signals(self):
        """Connect navigation-related signals"""
        if not self.web_view:
            return

        # Connect navigation buttons
        self.nav_back_button.clicked.connect(self.web_view.back)
        self.nav_forward_button.clicked.connect(self.web_view.forward)
        self.refresh_button.clicked.connect(self.web_view.reload)

        # Connect URL bar
        self.url_bar.returnPressed.connect(self.navigate_to_url)

        # Connect web view signals
        self.web_view.urlChanged.connect(self._on_url_changed)
        self.web_view.loadFinished.connect(self._update_navigation_state)
        self.web_view.titleChanged.connect(self._on_web_title_changed)

        # Connect page signals if available
        if hasattr(self.web_view, 'page') and callable(self.web_view.page):
            page = self.web_view.page()
            if page:
                page.loadStarted.connect(self._on_load_started)
        else:
            # For WebView2Widget, connect loadStarted directly
            if hasattr(self.web_view, 'loadStarted'):
                self.web_view.loadStarted.connect(self._on_load_started)

    def navigate_to_url(self):
        """Navigate to the URL entered in the URL bar"""
        url = self.url_bar.text().strip()
        if not url:
            return

        # Add protocol if missing
        if not url.startswith(('http://', 'https://', 'file://')):
            url = 'https://' + url

        # Mark as pending navigation
        self._pending_navigation = url
        self.load_url(url)

    def _on_url_changed(self, url):
        """Update URL bar when URL changes"""
        url_str = url.toString()
        self.url_bar.setText(url_str)
        self.current_url = url_str

        # If URL changed to a new page (not just hash change), mark as pending
        if hasattr(self, '_last_recorded_url') and url_str != self._last_recorded_url:
            # Check if it's a significant navigation (not just anchor/hash change)
            try:
                from urllib.parse import urlparse
                current_parsed = urlparse(url_str)
                last_parsed = urlparse(self._last_recorded_url) if self._last_recorded_url else None

                # Different domain or path = new navigation
                if not last_parsed or (current_parsed.netloc != last_parsed.netloc or
                                       current_parsed.path != last_parsed.path):
                    self._pending_navigation = url_str
            except:
                self._pending_navigation = url_str

    def _on_load_started(self):
        """Called when page loading starts"""
        # You could add a loading indicator here if desired
        pass

    def _on_web_title_changed(self, title):
        """Handle title change from web view"""
        # History recording moved to show_chat_view() in UnifiedAssistantWindow
        # But we still need to update the current title for later use
        if title and title.strip():
            old_title = self.current_title
            self.current_title = title
            import logging
            logger = logging.getLogger(__name__)
            
            # Enhanced logging to track title changes, especially during redirects
            if old_title != title:
                logger.info(f"📄 Title changed in WikiView: '{old_title}' -> '{title}'")
            else:
                logger.debug(f"📄 Title confirmed in WikiView: {title}")
            
            # Emit signal for external components that may need to track title changes
            # This is especially useful for tracking delayed title updates after redirects
            if hasattr(self, 'wiki_page_loaded') and hasattr(self, 'current_url'):
                if self.current_url and title != self.current_url:  # Avoid duplicate events
                    self.wiki_page_loaded.emit(self.current_url, title)
    
    def _sync_webview_state(self):
        """Sync current URL and title state from WebView after initialization"""
        if not self.web_view or not self._webview_initialized:
            return
        
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Get current URL from WebView
            current_url = None
            if hasattr(self.web_view, 'url') and callable(self.web_view.url):
                qurl = self.web_view.url()
                if qurl and not qurl.isEmpty():
                    current_url = qurl.toString()
            
            # Get current title from WebView's internal state
            current_title = None
            if hasattr(self.web_view, 'current_title'):
                current_title = getattr(self.web_view, 'current_title', None)
            
            # Update WikiView state if we got valid data
            if current_url and current_url != self.current_url:
                old_url = self.current_url
                self.current_url = current_url
                # Also update URL bar
                if hasattr(self, 'url_bar'):
                    self.url_bar.setText(current_url)
                logger.info(f"🔄 Syncing URL in WikiView: '{old_url}' -> '{current_url}'")
            
            if current_title and current_title != self.current_title:
                old_title = self.current_title  
                self.current_title = current_title
                logger.info(f"📝 Syncing title in WikiView: '{old_title}' -> '{current_title}'")
                
                # Emit signal for components that track title changes
                if hasattr(self, 'wiki_page_loaded') and current_url:
                    self.wiki_page_loaded.emit(current_url, current_title)
            
        except Exception as e:
            logger.error(f"Failed to sync WebView state: {e}")

    def _update_navigation_state(self, ok=True):
        """Update navigation button states based on history"""
        if not self.web_view:
            return

        # Update back/forward button states
        try:
            history = self.web_view.history()
            self.nav_back_button.setEnabled(history.canGoBack())
            self.nav_forward_button.setEnabled(history.canGoForward())
        except:
            pass

    def _emit_wiki_found(self, url, title):
        """Emit wiki page found signal"""
        print(f"📄 WikiView found real wiki page: {title} -> {url}")
        self.wiki_page_loaded.emit(url, title)

    def _extract_page_info_for_url(self, expected_url):
        """Extract page info and verify it's for the expected URL"""
        if not self.web_view:
            return

        try:
            current_url = self.web_view.url().toString()

            # Verify we're still on the same page
            if current_url == expected_url:
                # Try multiple methods to get title
                self._try_get_page_title(current_url)
        except Exception as e:
            print(f"Failed to extract page info for URL: {e}")

    def _try_get_page_title(self, url):
        """Get page title - now relies on WebView2's titleChanged signal"""
        print(f"🔍 Attempting to extract title for: {url}")
        
        # JavaScript title extraction removed - WebView2 titleChanged signal handles this automatically
        # Use current title if available
        if hasattr(self, 'current_title') and self.current_title:
            self._emit_wiki_found(url, self.current_title)
        else:
            # Use URL-based fallback if no title available yet
            print("⚠️ Empty or invalid title extracted, trying fallback")
            fallback_title = url.split('/')[-1].replace('-', ' ').replace('_', ' ')
            if not fallback_title:
                fallback_title = url.split('/')[-2] if len(url.split('/')) > 1 else "Wiki Page"
            print(f"📝 Using URL-based fallback title: {fallback_title}")
            self._emit_wiki_found(url, fallback_title)

    def _is_real_wiki_page(self, url: str) -> bool:
        """Determine if it is a real wiki page (not a search page)"""
        if not url:
            return False

        # Check if the URL contains common search engine domains
        search_engines = [
            'duckduckgo.com',
            'bing.com',
            'google.com',
            'search.yahoo.com'
        ]

        for engine in search_engines:
            if engine in url.lower():
                return False

        # Check if it contains wiki-related domains or paths
        wiki_indicators = [
            'wiki',
            'fandom.com',
            'wikia.com',
            'gamepedia.com',
            'huijiwiki.com',  # Add support for HuijiWiki
            'mcmod.cn',  # MC Encyclopedia
            'terraria.wiki.gg',
            'helldiversgamepedia.com'
        ]

        url_lower = url.lower()
        for indicator in wiki_indicators:
            if indicator in url_lower:
                return True

        # If the URL is different from the initial search URL and is not a search engine, it is considered a real page
        return url != self.current_search_url

    def _start_wiki_monitoring(self, search_url: str):
        """Start monitoring for wiki page navigation"""
        self._monitoring_start_url = search_url
        self._url_monitor_timer.start(1000)  # Check every second
        print(f"🔍 Started monitoring for wiki navigation from: {search_url}")

    def _stop_wiki_monitoring(self):
        """Stop monitoring for wiki page navigation"""
        self._url_monitor_timer.stop()
        self._monitoring_start_url = None
        print("🚫 Stopped wiki navigation monitoring")

    def _monitor_wiki_navigation(self):
        """Monitor WebView for navigation to actual wiki page"""
        if not self.web_view:
            return

        try:
            current_url = self.web_view.url().toString()

            # Check if we've navigated away from search engine
            if current_url != self._monitoring_start_url and self._is_real_wiki_page(current_url):
                print(f"🎆 Detected navigation to wiki page: {current_url}")
                self._stop_wiki_monitoring()

                # Extract title first, don't emit with URL as title
                # Wait a bit for page to load then extract proper title
                QTimer.singleShot(1000, lambda: self._extract_page_info_for_url(current_url))
        except Exception as e:
            print(f"Error in wiki navigation monitoring: {e}")

    def _initialize_webview_async(self):
        """Initialize WebView2 asynchronously"""
        if self._webview_initialized or self._webview_initializing:
            return

        self._webview_initializing = True  # 开始创建就置True（不要立刻清掉）

        # WebView2 must be created in main thread due to COM requirements
        # Use QTimer to defer creation to avoid blocking current event
        def create_and_init_webview():
            try:
                if USE_WEBVIEW2 and WEBVIEW2_AVAILABLE:
                    print("🔧 Creating WebView2 widget...")
                    start_time = time.time()
                    web_view = WebView2Widget()
                    elapsed = time.time() - start_time
                    print(f"✅ WebView2 widget created in {elapsed:.2f}s")
                    
                    # Apply the widget first
                    self._apply_webview(web_view)
                    
                    # Mark that we should auto-init on show
                    web_view._auto_init_on_show = True
                    
                    # If already visible, initialize now
                    if self.isVisible():
                        logger.info("WikiView is visible, initializing WebView2 now")
                        QTimer.singleShot(100, web_view.initialize)
                    else:
                        print("✅ WebView2 widget ready, will initialize when shown")
                else:
                    print("⚠️ WebView2 not available")
            except Exception as e:
                print(f"❌ WebView2 creation failed: {e}")
                self._webview_initializing = False

        # Defer to next event loop iteration to avoid blocking
        QTimer.singleShot(10, create_and_init_webview)

    def _apply_webview(self, web_view):
        """Apply WebView2 widget (must be called in main thread)"""
        if self._webview_initialized:
            return

        try:
            # Get layout first
            layout = self.layout()
            
            # Remove placeholder safely
            if self.placeholder_widget is not None:
                layout.removeWidget(self.placeholder_widget)
                self.placeholder_widget.deleteLater()
                self.placeholder_widget = None  # Prevent further access

            # Apply WebView2
            self.web_view = web_view
            self.content_widget = self.web_view
            layout.addWidget(self.content_widget)

            # Don't connect signals yet - wait for WebView2 to be initialized
            # self._connect_navigation_signals()  # Will be called after init

            # Don't mark as initialized yet - wait for actual WebView2 init
            # 重要：不要重置_webview_initializing，保持它为True直到首次loadFinished
            self._webview_ready = False
            self._webview_initialized = False
            # self._webview_initializing = False  # 删除这行！

            print("✅ WebView2 widget applied, waiting for initialization...")
            
            # Connect to the WebView2's initialization signals
            if hasattr(web_view, 'loadFinished'):
                def on_first_load():
                    if not self._webview_initialized:
                        self._webview_initialized = True
                        self._webview_initializing = False  # 在"首次加载完成"才清掉
                        self._webview_init_requested = False  # 释放闸门
                        self._webview_ready = True
                        self._connect_navigation_signals()
                        print("✅ WebView2 fully initialized and ready")
                        
                        # Schedule state synchronization after initialization
                        # This helps catch any redirects that happened during initialization
                        QTimer.singleShot(200, self._sync_webview_state)
                        
                        # Disconnect this handler
                        try:
                            web_view.loadFinished.disconnect(on_first_load)
                        except:
                            pass
                web_view.loadFinished.connect(on_first_load)

            # If there's a pending URL to load (from load_wiki or load_url)
            if hasattr(self, '_pending_url') and self._pending_url:
                url = self._pending_url
                title = getattr(self, '_pending_title', '')
                
                # Clear pending attributes
                self._pending_url = None
                self._pending_title = None
                
                # Load the pending wiki page
                if title:
                    print(f"Loading pending wiki page: {url}")
                    # Use QTimer to ensure we're in the right context
                    QTimer.singleShot(100, lambda: self.load_wiki(url, title))
                else:
                    print(f"Loading pending URL: {url}")
                    QTimer.singleShot(100, lambda: self.load_url(url))

        except Exception as e:
            print(f"❌ Failed to apply WebView2: {e}")

    def load_wiki(self, url: str, title: str):
        """Load a wiki page"""
        self.current_search_url = url  # Save search URL
        self.current_search_title = title  # Save search title
        self.current_url = url
        self.current_title = title
        self.url_bar.setText(url)  # Update URL bar instead of title label
        
        # Always load if we have a web_view instance - let inner widget handle queuing
        if not self.web_view:
            print(f"WebView2 not created yet, saving URL for later: {url}")
            self._pending_url = url
            self._pending_title = title
            # Ensure WebView2 initialization is triggered
            self.ensure_webview_ready()
            return
        
        # Always ensure page is in interactive state when loading
        if self._is_paused:
            print("📝 Page was paused, resuming before load")
            self.resume_page()

        # Start monitoring for wiki page navigation if loading from search engine
        if any(engine in url.lower() for engine in ['duckduckgo.com', 'google.com', 'bing.com']):
            self._start_wiki_monitoring(url)

        # Always load if we have web_view - don't wait for _webview_initialized
        if self.web_view:
            try:
                # For local files, use load method directly to preserve external resource loading capability
                if url.startswith('file:///'):
                    # Create QUrl object
                    qurl = QUrl(url)
                    print(f"📄 Loading local file: {url}")

                    # Load file URL
                    self.web_view.load(qurl)
                    print(f"✅ Using load method to load local HTML, preserving external resource loading")
                else:
                    # Non-local files, normal loading
                    self.web_view.load(QUrl(url))
                    print(f"🌐 Loading URL: {url}")
            except Exception as e:
                print(f"❌ Failed to load wiki page: {e}")
                import traceback
                traceback.print_exc()
                # Display error message - only if web_view is a real webview
                if hasattr(self.web_view, 'setHtml'):
                    self.web_view.setHtml(f"<h2>Error</h2><p>Failed to load page: {str(e)}</p>")
                else:
                    print(f"Cannot display error in web view - WebView2 not ready")
        else:
            # Show fallback message - check if we have a label to display it
            if hasattr(self, 'placeholder_widget') and self.placeholder_widget:
                # Update placeholder label text
                placeholder_layout = self.placeholder_widget.layout()
                if placeholder_layout and placeholder_layout.count() > 0:
                    label = placeholder_layout.itemAt(0).widget()
                    if isinstance(label, QLabel):
                        label.setText(f"WebView2 not ready.\nURL: {url}\n\nClick 'Open in Browser' to view in external browser.")
            else:
                print(f"WebView2 not available to load: {url}")
                print(f"Title: {title}")
            
            # Trigger WebView2 initialization if not already started
            self.ensure_webview_ready()

    def open_in_browser(self):
        """Open the current URL in default browser"""
        if self.current_url:
            import webbrowser
            try:
                webbrowser.open(self.current_url)
            except Exception as e:
                print(f"Failed to open browser: {e}")

    def stop_media_playback(self):
        """Stop all media playback in the page"""
        if self.web_view:
            try:
                # Execute more comprehensive JavaScript to stop all media playback
                javascript_code = """
                    (function() {
                        // Stop all video and audio
                        var videos = document.querySelectorAll('video');
                        var audios = document.querySelectorAll('audio');

                        videos.forEach(function(video) {
                            video.pause();
                            // Don't change muted state or volume
                            // Remove all event listeners
                            video.onplay = null;
                            video.onloadeddata = null;
                            video.oncanplay = null;
                        });

                        audios.forEach(function(audio) {
                            audio.pause();
                            // Don't change muted state or volume
                            // Remove all event listeners
                            audio.onplay = null;
                            audio.onloadeddata = null;
                            audio.oncanplay = null;
                        });

                        // Stop all media in iframes
                        var iframes = document.querySelectorAll('iframe');
                        iframes.forEach(function(iframe) {
                            try {
                                var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                var iframeVideos = iframeDoc.querySelectorAll('video');
                                var iframeAudios = iframeDoc.querySelectorAll('audio');

                                iframeVideos.forEach(function(video) {
                                    video.pause();
                                    // Don't change muted state or volume
                                    video.onplay = null;
                                    video.onloadeddata = null;
                                    video.oncanplay = null;
                                });

                                iframeAudios.forEach(function(audio) {
                                    audio.pause();
                                    // Don't change muted state or volume
                                    audio.onplay = null;
                                    audio.onloadeddata = null;
                                    audio.oncanplay = null;
                                });
                            } catch(e) {
                                // Cross-domain iframe cannot be accessed, ignore error
                            }
                        });

                        // Prevent new media playback
                        if (!window._originalPlay) {
                            window._originalPlay = HTMLMediaElement.prototype.play;
                        }
                        HTMLMediaElement.prototype.play = function() {
                            console.log('🚫 Prevent media playback:', this);
                            return Promise.reject(new Error('Media playback blocked'));
                        };

                        console.log('🔇 Media playback has been stopped and new playback has been prevented');
                    })();
                    """

                self.web_view.runJavaScript(javascript_code)
                print("🔇 WikiView: Enhanced media stop script executed")

            except Exception as e:
                print(f"⚠️ WikiView: Failed to stop media playback: {e}")

    def pause_page(self):
        """Pause page activity (including media playback)"""
        # Prevent repeated calls
        if self._pause_lock:
            print("🔄 WikiView: Pause operation is in progress, skipping repeated call")
            return

        if self.web_view and not self._is_paused:
            try:
                self._pause_lock = True
                print("🔄 Pausing WikiView page...")

                # 1. Stop current network request
                try:
                    self.web_view.stop()
                    print("✅ WebView network request stopped")
                except Exception as stop_error:
                    print(f"⚠️ WebView stop failed: {stop_error}")

                # 2. Stop media playback
                try:
                    self.stop_media_playback()
                    print("✅ Media playback stopped")
                except Exception as media_error:
                    print(f"⚠️ Media stop failed: {media_error}")

                # 3. Set the page to an invisible state, some websites will automatically pause media
                try:
                    self.web_view.runJavaScript("""
                        (function() {
                            // Set the page to an invisible state
                            Object.defineProperty(document, 'hidden', {value: true, writable: false});
                            Object.defineProperty(document, 'visibilityState', {value: 'hidden', writable: false});

                            // Trigger visibility change event
                            var event = new Event('visibilitychange');
                            document.dispatchEvent(event);

                            // Prevent page focus
                            if (document.hasFocus) {
                                document.hasFocus = function() { return false; };
                            }

                            // Set the page to an uninteractive state
                            document.body.style.pointerEvents = 'none';

                            console.log('🔇 The page has been set to an invisible state');
                        })();
                        """)
                    print("✅ The page visibility state has been set")
                except Exception as js_error:
                    print(f"⚠️ JavaScript execution failed: {js_error}")

                self._is_paused = True
                print("✅ WikiView page pause completed")

            except Exception as e:
                print(f"⚠️ WikiView: Failed to pause page: {e}")
            finally:
                self._pause_lock = False
        else:
            print("🔄 WikiView: The page is already paused or WebView is not available, skipping pause operation")

    def resume_page(self):
        """Resume page activity"""
        if self.web_view and self._is_paused:
            def restore_interactivity():
                try:
                    # Restore page visibility and interactivity
                    script = """
                    (function() {
                        // Restore page visibility state
                        Object.defineProperty(document, 'hidden', {value: false, writable: false});
                        Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: false});

                        // Trigger visibility change event
                        var event = new Event('visibilitychange');
                        document.dispatchEvent(event);

                        // Force restore page interactivity - multiple attempts
                        document.body.style.pointerEvents = '';
                        document.body.style.pointerEvents = 'auto';
                        
                        // Also check all parent elements
                        var element = document.body;
                        while (element) {
                            if (element.style && element.style.pointerEvents === 'none') {
                                element.style.pointerEvents = '';
                            }
                            element = element.parentElement;
                        }

                        // Force restore media playback functionality
                        if (window._originalPlay) {
                            HTMLMediaElement.prototype.play = window._originalPlay;
                            delete window._originalPlay;
                            console.log('✅ Media play function restored from backup');
                        } else {
                            // If original method is lost, check if play is still blocked
                            if (HTMLMediaElement.prototype.play.toString().includes('blocked')) {
                                // Create a new native play method
                                HTMLMediaElement.prototype.play = function() {
                                    // Use native browser's play implementation
                                    var video = document.createElement('video');
                                    var nativePlay = video.play;
                                    return nativePlay.apply(this, arguments);
                                };
                                console.log('⚠️ Media play function recreated');
                            }
                        }
                        
                        // Restore all existing media elements
                        var allMedia = document.querySelectorAll('video, audio');
                        allMedia.forEach(function(media) {
                            // Don't change muted state or volume - let user control remain
                            // Clear any event handlers that might block playback
                            media.onplay = null;
                            console.log('✅ Media element restored:', media.tagName);
                        });

                        console.log('▶️ Page restored - pointer events: ' + document.body.style.pointerEvents);
                        
                        // Return true to indicate success
                        return true;
                    })();
                    """
                    
                    self.web_view.runJavaScript(script)
                    self._is_paused = False
                    print("▶️ WikiView: Page restore attempted")
                    
                    # Schedule a verification check
                    QTimer.singleShot(200, self._verify_page_restored)
                    
                except Exception as e:
                    print(f"⚠️ WikiView: Failed to restore page: {e}")
                    # Retry after a delay
                    QTimer.singleShot(100, restore_interactivity)
            
            # Execute restoration
            restore_interactivity()
        else:
            print("▶️ WikiView: The page is not in a paused state, skipping restore operation")
    
    def _verify_page_restored(self):
        """Page restoration verification - function removed to prevent thread errors"""
        # Verification removed: page restoration works correctly without JavaScript verification
        pass

    def hideEvent(self, event):
        """When WikiView is hidden, automatically pause media playback"""
        # Only pause when currently displaying WikiView
        if hasattr(self, 'parent') and self.parent():
            parent = self.parent()
            if hasattr(parent, 'content_stack'):
                current_widget = parent.content_stack.currentWidget()
                if current_widget == self:
                    self.pause_page()
        super().hideEvent(event)

    def showEvent(self, event):
        """When WikiView is displayed, restore page activity"""
        super().showEvent(event)

        # Ensure WebView2 is initialized when showing (with proper timing)
        if not self._webview_initialized and not self._webview_initializing:
            # 延迟初始化以确保事件循环已经运行
            QTimer.singleShot(100, self._initialize_webview_async)

        # Delay restore, ensure the page is fully displayed
        QTimer.singleShot(100, self.resume_page)

    def retranslate_ui(self):
        """Update all UI text after language change"""
        self.back_button.setText(t("btn_back_to_chat"))
        self.nav_back_button.setToolTip(t("tooltip_nav_back"))
        self.nav_forward_button.setToolTip(t("tooltip_nav_forward"))
        self.refresh_button.setToolTip(t("tooltip_refresh"))
        self.url_bar.setPlaceholderText(t("placeholder_url_bar"))
        self.open_browser_button.setText(t("btn_open_browser"))
        self.close_button.setToolTip(t("tooltip_close_window"))
        self.placeholder_label.setText(t("label_loading"))