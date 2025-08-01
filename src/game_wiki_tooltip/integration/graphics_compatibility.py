"""
Graphics compatibility module for PyQt6 on Windows 10.
Provides different rendering strategies to resolve graphics context issues.
"""

import os
import sys
import logging
import platform
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class GraphicsMode(Enum):
    """Different graphics rendering modes for compatibility"""
    AUTO = "auto"           # Auto-detect best mode
    SOFTWARE = "software"   # Pure software rendering (safest)
    OPENGL = "opengl"      # Hardware OpenGL (if available)
    ANGLE = "angle"        # ANGLE translation layer
    D3D11 = "d3d11"        # Direct3D 11 (Windows 10+ default)


class WindowsGraphicsCompatibility:
    """Manages graphics compatibility for PyQt6 on Windows"""
    
    def __init__(self):
        self.windows_version = self._get_windows_version()
        self.is_windows_10 = self._is_windows_10(self.windows_version)
        self.graphics_mode = GraphicsMode.AUTO
        
    def _get_windows_version(self) -> str:
        """Get Windows version string"""
        try:
            return platform.version()
        except:
            return "unknown"
    
    def _is_windows_10(self, version: str) -> bool:
        """
        Check if the current Windows version is Windows 10.
        Windows 11 still has version numbers starting with "10." but with build numbers >= 22000.
        
        Args:
            version: Version string like "10.0.22621" or "10.0.19044"
            
        Returns:
            True if Windows 10, False if Windows 11 or unknown
        """
        try:
            # Split version string to get build number
            # Format: "major.minor.build" e.g., "10.0.22621"
            parts = version.split('.')
            if len(parts) >= 3 and parts[0] == "10" and parts[1] == "0":
                build_number = int(parts[2])
                # Windows 11 starts from build 22000
                return build_number < 22000
            # If not in expected format, assume Windows 10 for safety
            return True
        except (ValueError, IndexError):
            # If we can't parse the version, assume Windows 10 for compatibility
            return True
    
    def apply_compatibility_fixes(self, mode: GraphicsMode = GraphicsMode.AUTO) -> None:
        """Apply graphics compatibility fixes based on the specified mode"""
        self.graphics_mode = mode
        
        if mode == GraphicsMode.AUTO:
            # Auto-detect best mode based on Windows version
            if self.is_windows_10:
                mode = GraphicsMode.SOFTWARE
                logger.info("Windows 10 detected, using SOFTWARE rendering mode")
            else:
                mode = GraphicsMode.D3D11
                logger.info("Windows 11 detected, using D3D11 rendering mode")
        
        logger.info(f"Applying graphics compatibility fixes for mode: {mode.value}")
        
        if mode == GraphicsMode.SOFTWARE:
            self._apply_software_mode()
        elif mode == GraphicsMode.OPENGL:
            self._apply_opengl_mode()
        elif mode == GraphicsMode.ANGLE:
            self._apply_angle_mode()
        elif mode == GraphicsMode.D3D11:
            self._apply_d3d11_mode()
        
        logger.info("Graphics compatibility fixes applied")
    
    def _apply_software_mode(self) -> None:
        """Apply pure software rendering mode - safest for Windows 10"""
        env_vars = {
            # Qt Core Graphics
            'QT_OPENGL': 'software',
            'QSG_RHI_PREFER_SOFTWARE_RENDERER': '1',
            'QSG_RHI_BACKEND': 'software',
            
            # Qt Quick
            'QT_QUICK_BACKEND': 'software',
            'QML_DISABLE_DISK_CACHE': '1',
            
            # ANGLE and WebEngine
            'QT_ANGLE_PLATFORM': 'software',
            'QTWEBENGINE_DISABLE_GPU_THREAD': '1',
            
            # Additional compatibility
            'QT_ENABLE_GLYPH_CACHE_WORKAROUND': '1',
            'QT_SCALE_FACTOR_ROUNDING_POLICY': 'PassThrough',
            'QT_AUTO_SCREEN_SCALE_FACTOR': '0',
            
            # Disable hardware acceleration entirely
            'QT_OPENGL_DLL': 'opengl32sw.dll',
            'QT_QPA_PLATFORM_PLUGIN_PATH': '',
        }
        
        for key, value in env_vars.items():
            os.environ.setdefault(key, value)
            
        # WebEngine flags for software mode
        webengine_flags = (
            '--disable-gpu '
            '--disable-gpu-compositing '
            '--disable-gpu-rasterization '
            '--disable-gpu-sandbox '
            '--disable-software-rasterizer '
            '--disable-background-timer-throttling '
            '--disable-features=VizDisplayCompositor,UseSkiaRenderer,UseChromeOSDirectVideoDecoder '
            '--no-sandbox '
            '--use-angle=swiftshader '
            '--disable-d3d11 '
            '--disable-d3d9 '
            '--force-cpu-draw '
            '--disable-accelerated-2d-canvas '
            '--disable-accelerated-video-decode '
            '--disable-accelerated-video-encode '
            '--disable-background-networking '
            '--disable-sync '
        )
        
        os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', webengine_flags)
        
    def _apply_opengl_mode(self) -> None:
        """Apply OpenGL hardware rendering mode"""
        env_vars = {
            'QT_OPENGL': 'desktop',
            'QSG_RHI_BACKEND': 'opengl',
            'QT_QUICK_BACKEND': 'opengl',
        }
        
        for key, value in env_vars.items():
            os.environ.setdefault(key, value)
            
        webengine_flags = (
            '--enable-gpu-rasterization '
            '--enable-zero-copy '
            '--use-gl=desktop '
        )
        
        os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', webengine_flags)
        
    def _apply_angle_mode(self) -> None:
        """Apply ANGLE translation layer mode"""
        env_vars = {
            'QT_OPENGL': 'angle',
            'QT_ANGLE_PLATFORM': 'gl',
            'QSG_RHI_BACKEND': 'opengl',
        }
        
        for key, value in env_vars.items():
            os.environ.setdefault(key, value)
            
        webengine_flags = (
            '--use-angle=gl '
            '--use-gl=angle '
        )
        
        os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', webengine_flags)
        
    def _apply_d3d11_mode(self) -> None:
        """Apply Direct3D 11 mode (default for Windows 11)"""
        env_vars = {
            'QSG_RHI_BACKEND': 'd3d11',
            'QT_QUICK_BACKEND': 'd3d11',
        }
        
        for key, value in env_vars.items():
            os.environ.setdefault(key, value)
            
        # Minimal WebEngine flags for D3D11
        webengine_flags = (
            '--enable-gpu-rasterization '
            '--enable-zero-copy '
        )
        
        os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', webengine_flags)
    
    def set_qt_application_attributes(self, app) -> None:
        """Set Qt application attributes based on current graphics mode"""
        from PyQt6.QtCore import Qt
        
        # Note: Most attributes must be set before QApplication creation
        # This function is kept for compatibility but may have limited effect
        logger.warning("set_qt_application_attributes called after QApplication creation - some attributes may not take effect")
        
        if self.graphics_mode in [GraphicsMode.SOFTWARE, GraphicsMode.AUTO]:
            # Try to set attributes that can be set after creation
            try:
                # These should already be set before QApplication creation
                pass
            except Exception as e:
                logger.warning(f"Failed to set post-creation attributes: {e}")
                
        logger.info(f"Post-creation Qt application attributes processed for mode: {self.graphics_mode.value}")
    
    def get_debug_info(self) -> dict:
        """Get debug information about graphics configuration"""
        return {
            'windows_version': self.windows_version,
            'is_windows_10': self.is_windows_10,
            'graphics_mode': self.graphics_mode.value,
            'qt_opengl': os.environ.get('QT_OPENGL', 'not set'),
            'qsg_rhi_backend': os.environ.get('QSG_RHI_BACKEND', 'not set'),
            'qsg_rhi_prefer_software': os.environ.get('QSG_RHI_PREFER_SOFTWARE_RENDERER', 'not set'),
        }


# Global instance for easy access
graphics_compatibility = WindowsGraphicsCompatibility()


def apply_windows_10_fixes(mode: GraphicsMode = GraphicsMode.AUTO) -> None:
    """Convenience function to apply Windows 10 graphics fixes"""
    graphics_compatibility.apply_compatibility_fixes(mode)


def set_application_attributes(app) -> None:
    """Convenience function to set Qt application attributes"""
    graphics_compatibility.set_qt_application_attributes(app)


def set_qt_attributes_before_app_creation(mode: GraphicsMode = GraphicsMode.AUTO) -> None:
    """Set Qt application attributes BEFORE QApplication creation"""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        
        # Auto-detect Windows version if needed
        if mode == GraphicsMode.AUTO:
            windows_version = platform.version()
            is_windows_10 = graphics_compatibility._is_windows_10(windows_version)
            if is_windows_10:
                mode = GraphicsMode.SOFTWARE
            else:
                mode = GraphicsMode.D3D11
        
        # Set DPI scale factor rounding policy first
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        logger.info("DPI scale factor rounding policy set successfully")
        
        # Define only the most essential and widely supported attributes
        # These are the core OpenGL-related attributes that should exist in all PyQt6 versions
        essential_attributes = [
            ('AA_UseSoftwareOpenGL', True if mode in [GraphicsMode.SOFTWARE, GraphicsMode.AUTO] else False),
            ('AA_UseOpenGLES', False if mode in [GraphicsMode.SOFTWARE, GraphicsMode.OPENGL, GraphicsMode.AUTO] else True),
            ('AA_UseDesktopOpenGL', True if mode in [GraphicsMode.SOFTWARE, GraphicsMode.OPENGL, GraphicsMode.AUTO] else False),
        ]
        
        # Apply only essential attributes with comprehensive error handling
        success_count = 0
        for attr_name, value in essential_attributes:
            try:
                if hasattr(Qt.ApplicationAttribute, attr_name):
                    attr = getattr(Qt.ApplicationAttribute, attr_name)
                    QApplication.setAttribute(attr, value)
                    logger.debug(f"Successfully set {attr_name} = {value}")
                    success_count += 1
                else:
                    logger.warning(f"Essential attribute {attr_name} not available in this PyQt6 version")
            except Exception as e:
                logger.warning(f"Failed to set essential attribute {attr_name}: {e}")
        
        if success_count > 0:
            logger.info(f"Successfully applied {success_count}/{len(essential_attributes)} Qt application attributes for graphics mode: {mode.value}")
        else:
            logger.warning("No Qt application attributes could be set - using default behavior")
        
    except Exception as e:
        logger.error(f"Failed to set Qt application attributes: {e}")
        # Don't raise the exception - allow the app to continue with default settings
        logger.warning("Continuing with default Qt application settings")


def get_graphics_debug_info() -> dict:
    """Convenience function to get graphics debug information"""
    return graphics_compatibility.get_debug_info() 