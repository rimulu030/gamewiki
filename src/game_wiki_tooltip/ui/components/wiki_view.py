"""
Wiki view widget for displaying web content.
"""

import os
import logging
import time
from typing import Optional

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
        # Try the simple implementation first
        from src.game_wiki_tooltip.webview2_simple import SimpleWebView2Widget as WebView2Widget
        from src.game_wiki_tooltip.webview_widget import check_webview2_runtime
        WEBVIEW2_AVAILABLE = True
        print("Using simplified WebView2 implementation")
        # Check if WebView2 Runtime is installed
        if not check_webview2_runtime():
            print("Warning: WebView2 Runtime not installed. Video playback may be limited.")
            print("Visit https://go.microsoft.com/fwlink/p/?LinkId=2124703 to install WebView2 Runtime.")
    except ImportError as e:
        print(f"Warning: WebView2Widget not available: {e}")
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
        self.back_button = QPushButton("< Back to Chat")
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
        self.nav_back_button.setToolTip("Back to the previous page")
        self.nav_back_button.setEnabled(False)

        self.nav_forward_button = QPushButton("▶")
        self.nav_forward_button.setStyleSheet(nav_button_style)
        self.nav_forward_button.setToolTip("Forward to the next page")
        self.nav_forward_button.setEnabled(False)

        self.refresh_button = QPushButton("🔄")
        self.refresh_button.setStyleSheet(nav_button_style)
        self.refresh_button.setToolTip("Refresh page")

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
        self.url_bar.setPlaceholderText("Enter URL and press Enter to navigate...")

        # Open in browser button
        self.open_browser_button = QPushButton("Open in Browser")
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
        self.close_button.setToolTip("Close window")
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
        placeholder_label = QLabel("Loading...")
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_label.setStyleSheet("color: #666; font-size: 14px;")
        placeholder_layout.addWidget(placeholder_label)

        self.content_widget = self.placeholder_widget

        layout.addWidget(toolbar)
        layout.addWidget(self.content_widget)

        # Store current URL and title
        self.current_url = ""
        self.current_title = ""

        # Start WebView2 initialization immediately in background
        QTimer.singleShot(0, self._initialize_webview_async)

    def load_url(self, url: str):
        """Load a URL in the web view"""
        if self.web_view and self._webview_initialized:
            self.web_view.setUrl(QUrl(url))
            self.current_url = url
        else:
            # Store pending URL, will be loaded when WebView is ready
            self._pending_url = url
            # WebView should already be initializing, just wait

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
        if not title or not self._pending_navigation:
            return

        # Get current URL from web view
        current_url = self.web_view.url().toString()

        # Check if this title change is for our pending navigation
        if current_url == self._pending_navigation:
            # Now we have the real title, record to history
            if hasattr(self, 'history_manager') and title.strip() != "":
                # Determine source type
                if "wiki" in current_url.lower() or "wiki" in title.lower():
                    source = "wiki"
                else:
                    source = "web"

                self._ensure_history_manager()
                self.history_manager.add_entry(current_url, title, source=source)
                self._last_recorded_url = current_url
                self._pending_navigation = None  # Clear pending state

                logger = logging.getLogger(__name__)
                logger.info(f"📝 Added to history with real title: {title}")

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

    def _on_page_load_finished(self, ok):
        """Callback when page loading is complete"""
        if not ok or not self.web_view:
            return

        # Update navigation state
        self._update_navigation_state()

        try:
            # Get the URL and title of the current page
            current_url = self.web_view.url().toString()

            # Check if it is a real wiki page (not a search page)
            if self._is_real_wiki_page(current_url):
                # Delay to ensure page is fully rendered
                QTimer.singleShot(500, self._extract_page_info)
            else:
                # If it is still a search page, check again after a while
                QTimer.singleShot(2000, self._check_for_redirect)

        except Exception as e:
            print(f"Page load completion handling failed: {e}")

    def _check_for_redirect(self):
        """检查页面是否已重定向到真实wiki页面"""
        if not self.web_view:
            return

        try:
            current_url = self.web_view.url().toString()
            if self._is_real_wiki_page(current_url):
                # Delay to ensure page is fully rendered
                QTimer.singleShot(500, self._extract_page_info)
            else:
                # Still on search page, check one more time
                QTimer.singleShot(2000, self._final_check_for_redirect)
        except Exception as e:
            print(f"Redirect check failed: {e}")

    def _final_check_for_redirect(self):
        """Final check for redirect after additional delay"""
        if not self.web_view:
            return

        try:
            current_url = self.web_view.url().toString()
            if self._is_real_wiki_page(current_url):
                self._extract_page_info()
        except Exception as e:
            print(f"Final redirect check failed: {e}")

    def _extract_page_info(self):
        """Extract page title and URL"""
        if not self.web_view:
            return

        try:
            current_url = self.web_view.url().toString()
            self._try_get_page_title(current_url)
        except Exception as e:
            print(f"Failed to extract page info: {e}")

    def _process_page_info(self, url, title):
        """Process extracted page information"""
        if not title or not url:
            return

        # Clean up the title
        title = title.strip()

        # Skip if title looks like a search or redirect page
        if any(x in title.lower() for x in ['search', 'redirect', 'loading', '...', 'duckduckgo']):
            return

        # Save current info
        self.current_url = url
        self.current_title = title

        # Emit signal with real wiki page info
        self._emit_wiki_found(url, title)

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
        """Try to get page title using multiple methods"""
        print(f"🔍 Attempting to extract title for: {url}")

        # Method 1: Try JavaScript
        if hasattr(self.web_view, 'page') and callable(self.web_view.page):
            try:
                # More comprehensive title extraction script
                script = """
                    (function() {
                        // First try document.title
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
                        // Fallback to first heading
                        var heading = document.querySelector('h1, h2, h3');
                        if (heading && heading.innerText) {
                            return heading.innerText.trim();
                        }
                        return '';
                    })();
                    """
                self.web_view.page().runJavaScript(
                    script,
                    lambda title: self._on_title_extracted(url, title)
                )
                return
            except Exception as e:
                print(f"❌ JavaScript title extraction failed: {e}")

        # Method 2: For WebView2Widget
        elif hasattr(self.web_view, 'runJavaScript'):
            try:
                script = """
                    (function() {
                        var title = document.title;
                        if (title && title !== '' && title !== 'undefined') {
                            // Return title as-is without modification
                            return title;
                        }
                        var h1 = document.querySelector('h1');
                        if (h1 && h1.innerText) {
                            return h1.innerText.trim();
                        }
                        return '';
                    })();
                    """
                self.web_view.runJavaScript(script, lambda title: self._on_title_extracted(url, title))
                return
            except Exception as e:
                print(f"❌ WebView2 JavaScript title extraction failed: {e}")

    def _on_title_extracted(self, url, title):
        """Handle extracted title"""
        if title and title.strip() and title != "null" and title != "undefined":
            print(f"✅ Successfully extracted title: {title}")
            self._emit_wiki_found(url, title)
        else:
            print(f"⚠️ Empty or invalid title extracted, trying fallback")
            # Fallback: use the last part of the URL as title
            try:
                from urllib.parse import urlparse, unquote
                parsed = urlparse(url)
                path_parts = parsed.path.strip('/').split('/')
                if path_parts and path_parts[-1]:
                    fallback_title = unquote(path_parts[-1]).replace('_', ' ')
                    print(f"📝 Using URL-based fallback title: {fallback_title}")
                    self._emit_wiki_found(url, fallback_title)
                else:
                    # Last resort: emit with a generic title
                    self._emit_wiki_found(url, "Wiki Page")
            except Exception as e:
                print(f"❌ Fallback title extraction failed: {e}")
                # Still emit with a generic title
                self._emit_wiki_found(url, "Wiki Page")

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

        self._webview_initializing = True

        # WebView2 must be created in main thread due to COM requirements
        # Use QTimer to defer creation to avoid blocking current event
        def create_webview():
            try:
                if USE_WEBVIEW2 and WEBVIEW2_AVAILABLE:
                    print("🔧 Creating WebView2...")
                    start_time = time.time()
                    web_view = WebView2Widget()
                    elapsed = time.time() - start_time
                    print(f"✅ WebView2 created in {elapsed:.2f}s")
                    self._apply_webview(web_view)
                else:
                    print("⚠️ WebView2 not available")
            except Exception as e:
                print(f"❌ WebView2 creation failed: {e}")

        # Defer to next event loop iteration to avoid blocking
        QTimer.singleShot(10, create_webview)

    def _apply_webview(self, web_view):
        """Apply WebView2 widget (must be called in main thread)"""
        if self._webview_initialized:
            return

        try:
            # Remove placeholder
            layout = self.layout()
            layout.removeWidget(self.placeholder_widget)
            self.placeholder_widget.deleteLater()

            # Apply WebView2
            self.web_view = web_view
            self.content_widget = self.web_view
            layout.addWidget(self.content_widget)

            # Connect signals
            self._connect_navigation_signals()

            self._webview_ready = True
            self._webview_initialized = True
            self._webview_initializing = False

            print("✅ WebView2 applied successfully")

            # If there's a pending URL to load
            if hasattr(self, '_pending_url'):
                self.load_url(self._pending_url)
                delattr(self, '_pending_url')

        except Exception as e:
            print(f"❌ Failed to apply WebView2: {e}")

    def _delayed_webview_creation(self):
        """Delayed WebView creation, executed after Qt application is fully initialized"""
        try:
            print("🔧 Starting delayed WebView creation...")

            # WebView2 is the only supported option - skip creation
            new_web_view = None

            if new_web_view is not None:
                print("✅ WebView delayed creation successful")

                # Configure WebView properties
                try:
                    new_web_view.setMinimumSize(100, 100)
                    new_web_view.setMaximumSize(16777215, 16777215)
                    new_web_view.setSizePolicy(
                        QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Expanding
                    )

                    # Connect signals
                    new_web_view.loadFinished.connect(self._on_page_load_finished)
                    print("✅ WebView configuration completed")
                except Exception as config_error:
                    print(f"⚠️ WebView configuration failed: {config_error}")

                # Replace content component
                try:
                    old_widget = self.content_widget
                    self.content_widget = new_web_view
                    self.web_view = new_web_view
                    self._webview_ready = True  # Mark WebView as ready

                    # Update layout
                    layout = self.layout()
                    if layout:
                        # Find old content_widget and replace it
                        for i in range(layout.count()):
                            item = layout.itemAt(i)
                            if item and item.widget() == old_widget:
                                layout.removeWidget(old_widget)
                                layout.addWidget(new_web_view)
                                # Delay deletion of old component to avoid issues from immediate deletion
                                QTimer.singleShot(100, old_widget.deleteLater)
                                break

                    print("✅ WebView successfully replaced text view")
                except Exception as replace_error:
                    print(f"⚠️ WebView replacement failed: {replace_error}")
                    # If replacement fails, clean up newly created WebView
                    new_web_view.deleteLater()
            else:
                print("⚠️ WebView creation failed, continuing to use text view")

        except Exception as e:
            print(f"❌ Delayed WebView creation process failed: {e}")

    def load_wiki(self, url: str, title: str):
        """Load a wiki page"""
        self.current_search_url = url  # Save search URL
        self.current_search_title = title  # Save search title
        self.current_url = url
        self.current_title = title
        self.url_bar.setText(url)  # Update URL bar instead of title label

        # Start monitoring for wiki page navigation if loading from search engine
        if any(engine in url.lower() for engine in ['duckduckgo.com', 'google.com', 'bing.com']):
            self._start_wiki_monitoring(url)

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
            except Exception as e:
                print(f"❌ Failed to load wiki page: {e}")
                import traceback
                traceback.print_exc()
                # Display error message
                self.web_view.setHtml(f"<h2>Error</h2><p>Failed to load page: {str(e)}</p>")
        else:
            # Show fallback message
            fallback_text = f"""
                <h2>{title}</h2>
                <p><strong>URL:</strong> <a href="{url}">{url}</a></p>
                <hr>
                <p>WebView2 is not available. Please click "Open in Browser" to view this page in your default browser.</p>
                <p>Alternatively, you can copy and paste the URL above into your browser.</p>
                """
            self.content_widget.setHtml(fallback_text)

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
                            video.currentTime = 0;
                            video.muted = true;
                            video.volume = 0;
                            // Remove all event listeners
                            video.onplay = null;
                            video.onloadeddata = null;
                            video.oncanplay = null;
                        });

                        audios.forEach(function(audio) {
                            audio.pause();
                            audio.currentTime = 0;
                            audio.muted = true;
                            audio.volume = 0;
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
                                    video.currentTime = 0;
                                    video.muted = true;
                                    video.volume = 0;
                                    video.onplay = null;
                                    video.onloadeddata = null;
                                    video.oncanplay = null;
                                });

                                iframeAudios.forEach(function(audio) {
                                    audio.pause();
                                    audio.currentTime = 0;
                                    audio.muted = true;
                                    audio.volume = 0;
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

                self.web_view.page().runJavaScript(javascript_code)
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
                    self.web_view.page().runJavaScript("""
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

    def safe_cleanup(self):
        """Safe cleanup of WikiView resources, used when window is closing"""
        try:
            print("🔄 Starting simplified WikiView cleanup...")

            if self.web_view:
                # Only perform the most basic cleanup, avoiding complex JavaScript or signal operations
                try:
                    # Stop network activity
                    self.web_view.stop()
                    print("✅ WebView stopped")
                except Exception:
                    # If stopping fails, continue processing
                    pass

                # Do not perform complex media stop, JavaScript execution, or signal disconnection operations
                # These may cause crashes

            print("✅ Simplified WikiView cleanup completed")

        except Exception as e:
            print(f"❌ WikiView cleanup failed: {e}")

    def resume_page(self):
        """Resume page activity"""
        if self.web_view and self._is_paused:
            try:
                # Restore page visibility and interactivity
                self.web_view.page().runJavaScript("""
                    (function() {
                        // Restore page visibility state
                        Object.defineProperty(document, 'hidden', {value: false, writable: false});
                        Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: false});

                        // Trigger visibility change event
                        var event = new Event('visibilitychange');
                        document.dispatchEvent(event);

                        // Restore page interactivity
                        document.body.style.pointerEvents = '';

                        // Restore media playback functionality
                        if (window._originalPlay) {
                            HTMLMediaElement.prototype.play = window._originalPlay;
                            delete window._originalPlay;
                        }

                        console.log('▶️ The page has been restored to visible and interactive state');
                    })();
                    """)

                self._is_paused = False
                print("▶️ WikiView: The page has been restored")

            except Exception as e:
                print(f"⚠️ WikiView: Failed to restore page: {e}")
        else:
            print("▶️ WikiView: The page is not in a paused state, skipping restore operation")

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

        # Ensure WebView2 is initialized when showing
        if not self._webview_initialized and not self._webview_initializing:
            self._initialize_webview_async()

        # Delay restore, ensure the page is fully displayed
        QTimer.singleShot(100, self.resume_page)