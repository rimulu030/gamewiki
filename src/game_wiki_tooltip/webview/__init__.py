"""
WebView module for game wiki tooltip application.
Contains WebView2 integration and web-based UI components.
"""

from .webview_widget import WebViewWidget
from .webview2_setup import setup_webview2
from .webview2_simple import SimpleWebView

__all__ = [
    'WebViewWidget',
    'setup_webview2',
    'SimpleWebView'
]