"""
Preloader for GameWiki Assistant
Preloads heavy modules during application startup to avoid delays on first use
"""

import logging
import threading
import warnings
import os

logger = logging.getLogger(__name__)


def suppress_warnings():
    """Suppress known warnings that clutter the console"""
    # Suppress pkg_resources deprecation warning from jieba
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="jieba._compat")
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
    
    # Suppress numpy warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")
    
    # Set environment variable to suppress TensorFlow warnings if using it
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'


def preload_jieba():
    """Preload jieba to avoid delay on first use"""
    try:
        logger.info("Preloading jieba module...")
        import jieba
        # Initialize jieba with a simple test to ensure dictionary is loaded
        jieba.lcut("测试", cut_all=False)
        logger.info("✅ Jieba preloaded successfully")
    except Exception as e:
        logger.warning(f"Failed to preload jieba: {e}")


def preload_vector_mappings():
    """Preload vector mappings to avoid delay on first hotkey"""
    try:
        logger.info("Preloading vector mappings...")
        from .ai.rag_query import load_vector_mappings
        mappings = load_vector_mappings()
        logger.info(f"✅ Vector mappings preloaded: {len(mappings)} mappings")
    except Exception as e:
        logger.warning(f"Failed to preload vector mappings: {e}")


def preload_ai_modules():
    """Preload AI modules - now called from splash screen instead of background thread"""
    try:
        logger.info("Preloading AI modules...")
        
        # Import commonly used AI modules
        from . import ai
        from .ai import rag_query
        from .ai import enhanced_bm25_indexer
        
        # These heavy imports are now done in splash_screen.py
        # Just ensure basic modules are available
        
        logger.info("✅ Basic AI modules imported")
    except Exception as e:
        logger.warning(f"Failed to import basic AI modules: {e}")


class BackgroundPreloader:
    """Background preloader that runs in a separate thread"""
    
    def __init__(self):
        self._thread = None
        self._started = False
        
    def start(self):
        """Start preloading in background"""
        if self._started:
            return
            
        self._started = True
        suppress_warnings()  # Suppress warnings early
        
        # Start preloading in background thread
        self._thread = threading.Thread(target=self._preload_all, daemon=True)
        self._thread.start()
        logger.info("🚀 Background preloading started")
        
    def _preload_all(self):
        """Preload all heavy modules"""
        try:
            # Set thread to lowest priority
            try:
                import sys
                if sys.platform == 'win32':
                    import ctypes
                    thread_handle = ctypes.windll.kernel32.GetCurrentThread()
                    ctypes.windll.kernel32.SetThreadPriority(thread_handle, -2)  # THREAD_PRIORITY_LOWEST
            except:
                pass
                
            # Preload modules
            preload_ai_modules()
            
        except Exception as e:
            logger.error(f"Background preloading failed: {e}")
            
    def wait_completion(self, timeout=5.0):
        """Wait for preloading to complete (with timeout)"""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


# Global preloader instance
_preloader = BackgroundPreloader()


def start_preloading():
    """Start background preloading"""
    _preloader.start()


def ensure_preloaded(timeout=0.1):
    """Ensure preloading is complete (with short timeout)"""
    _preloader.wait_completion(timeout=timeout)