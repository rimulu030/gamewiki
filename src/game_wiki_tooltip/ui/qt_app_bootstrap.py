"""
Bootstrap entry point for GameWiki Assistant.
This minimal script shows the splash screen immediately before loading heavy modules.
"""

import sys
import os
import logging

def main():
    """Bootstrap main function that shows splash screen first"""
    # Step 0: Absolute minimal setup for logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Step 1: Set Qt attributes before creating QApplication (minimal imports)
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except:
        pass
    
    # Step 2: Create QApplication immediately
    logger.info("Creating QApplication...")
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("GameWiki Assistant")
    
    # Step 3: Show splash screen IMMEDIATELY (before any other imports)
    logger.info("Showing splash screen...")
    from src.game_wiki_tooltip.splash_screen import SplashScreen, FirstRunSplashScreen
    
    # Check if this is first run
    is_first_run = False
    if hasattr(sys, '_MEIPASS'):
        # Running from PyInstaller bundle
        marker_file = os.path.join(sys._MEIPASS, '.first_run_complete')
        if not os.path.exists(marker_file):
            is_first_run = True
            # Create marker file
            try:
                with open(marker_file, 'w') as f:
                    f.write('1')
            except:
                pass
    
    # Show appropriate splash screen
    if is_first_run:
        splash = FirstRunSplashScreen()
    else:
        splash = SplashScreen()
    
    splash.show()
    qapp.processEvents()  # Force immediate display
    
    # Step 4: Now import and run the main app (while splash is visible)
    logger.info("Loading main application...")
    try:
        from src.game_wiki_tooltip.qt_app import run_main_app
        run_main_app(qapp, splash)
    except Exception as e:
        logger.error(f"Failed to load main application: {e}")
        splash.close()
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Error", f"Failed to start GameWiki Assistant:\n{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()