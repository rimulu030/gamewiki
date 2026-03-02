"""
Splash screen for GameWiki Assistant
Shows a loading screen while the main application initializes
"""

import sys
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QFont
from pathlib import Path

from src.game_wiki_tooltip.core.i18n import t


class InitializationThread(QThread):
    """Thread for application initialization"""
    progress_update = pyqtSignal(int, str)
    initialization_complete = pyqtSignal()
    
    def run(self):
        """Run initialization tasks"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Step 1: Import core modules
            self.progress_update.emit(10, t("splash_loading_core"))
            from src.game_wiki_tooltip.core import config
            from src.game_wiki_tooltip.core import utils

            # Step 2: Import Qt modules
            self.progress_update.emit(25, t("splash_loading_ui"))
            from . import qt_app
            from src.game_wiki_tooltip.window_component import unified_window

            # Step 3: Initialize settings
            self.progress_update.emit(40, t("splash_loading_settings"))
            from src.game_wiki_tooltip.core.config import SettingsManager
            settings_manager = SettingsManager()
            
            # Step 4: Load AI modules directly (not just start background loading)
            self.progress_update.emit(55, t("splash_loading_ai"))
            try:
                # Import and initialize AI modules during splash screen
                from .ai.unified_query_processor import process_query_unified
                from .ai.rag_config import get_default_config
                from .ai.rag_query import EnhancedRagQuery
                
                # Mark AI modules as loaded in assistant_integration
                from . import assistant_integration as ai_integration
                ai_integration.process_query_unified = process_query_unified
                ai_integration.get_default_config = get_default_config
                ai_integration.EnhancedRagQuery = EnhancedRagQuery
                ai_integration._ai_modules_loaded = True
                ai_integration._ai_modules_loading = False
                
                logger.info("✅ AI modules loaded during splash screen")
            except Exception as e:
                logger.warning(f"Failed to load AI modules during splash: {e}")
                # Still start background preloading as fallback
                try:
                    from .preloader import start_preloading
                    start_preloading()
                except:
                    pass
            
            # Step 5: Initialize jieba and load vector mappings
            self.progress_update.emit(70, t("splash_loading_text"))
            try:
                # Initialize jieba to avoid delay on first use
                import jieba
                jieba.lcut("初始化", cut_all=False)  # Force initialization
                logger.info("✅ Jieba initialized during splash screen")
            except Exception as e:
                logger.warning(f"Failed to initialize jieba: {e}")
            
            # Step 6: Load game mappings
            self.progress_update.emit(80, t("splash_loading_games"))
            try:
                # Force load vector mappings early
                from .ai.rag_query import load_vector_mappings
                load_vector_mappings()
            except:
                pass
            
            # Step 7: Final initialization
            self.progress_update.emit(90, t("splash_almost_ready"))

            import time
            time.sleep(0.2)  # Brief pause for visual effect
            
            self.progress_update.emit(100, t("splash_starting_app"))
            self.initialization_complete.emit()
            
        except Exception as e:
            print(f"Initialization error: {e}")
            self.initialization_complete.emit()


class SplashScreen(QWidget):
    """Splash screen window"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_thread = None
        
    def init_ui(self):
        """Initialize UI"""
        # Window settings
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # Set size
        self.setFixedSize(400, 300)
        
        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Background widget
        background = QWidget()
        background.setObjectName("background")
        background.setStyleSheet("""
            #background {
                background-color: #2b2b2b;
                border-radius: 10px;
                border: 1px solid #444;
            }
        """)
        
        bg_layout = QVBoxLayout(background)
        bg_layout.setSpacing(20)
        
        # Logo/Icon (if available)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Try to load app icon
        icon_path = Path(__file__).parent / "assets" / "app.ico"
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, 
                                             Qt.TransformationMode.SmoothTransformation)
                icon_label.setPixmap(scaled_pixmap)
        
        # If no icon, use text
        if icon_label.pixmap() is None or icon_label.pixmap().isNull():
            icon_label.setText("🎮")
            icon_label.setStyleSheet("font-size: 48px;")
        
        bg_layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel("GameWiki Assistant")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont("Arial", 18, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #ffffff;")
        bg_layout.addWidget(title_label)
        
        # Version
        version_label = QLabel("Version 1.0.0")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #888888; font-size: 12px;")
        bg_layout.addWidget(version_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 5px;
                background-color: #333;
                height: 10px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
        """)
        bg_layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel(t("splash_starting"))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        bg_layout.addWidget(self.status_label)
        
        # Add stretch
        bg_layout.addStretch()
        
        # Copyright
        copyright_label = QLabel("© 2024 GameWiki Team")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_label.setStyleSheet("color: #666666; font-size: 10px;")
        bg_layout.addWidget(copyright_label)
        
        layout.addWidget(background)
        self.setLayout(layout)
        
    def start_initialization(self):
        """Start initialization process"""
        self.init_thread = InitializationThread()
        self.init_thread.progress_update.connect(self.update_progress)
        self.init_thread.initialization_complete.connect(self.on_initialization_complete)
        self.init_thread.start()
        
    def update_progress(self, value, status):
        """Update progress bar and status"""
        self.progress_bar.setValue(value)
        self.status_label.setText(status)
        
    def on_initialization_complete(self):
        """Called when initialization is complete"""
        # Close splash screen after a brief delay
        QTimer.singleShot(500, self.close)
        
    def close_and_cleanup(self):
        """Close splash screen and cleanup"""
        if self.init_thread and self.init_thread.isRunning():
            self.init_thread.quit()
            self.init_thread.wait()
        self.close()


def show_splash():
    """Show splash screen and return the instance"""
    splash = SplashScreen()
    splash.show()
    splash.start_initialization()
    return splash


if __name__ == "__main__":
    # Test splash screen
    app = QApplication(sys.argv)
    splash = show_splash()
    
    # Simulate main window appearing after splash
    def show_main():
        splash.close()
        print("Main application would start here")
        app.quit()
    
    QTimer.singleShot(3000, show_main)
    sys.exit(app.exec())