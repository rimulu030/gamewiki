"""
Integration module for game wiki tooltip application.
Contains integration between different components and system compatibility.
"""

from .assistant_integration import IntegratedAssistantController
from .smart_interaction_manager import SmartInteractionManager
from .graphics_compatibility import (
    apply_windows_10_fixes,
    set_application_attributes,
    get_graphics_debug_info,
    set_qt_attributes_before_app_creation
)

__all__ = [
    'IntegratedAssistantController',
    'SmartInteractionManager',
    'apply_windows_10_fixes',
    'set_application_attributes',
    'get_graphics_debug_info',
    'set_qt_attributes_before_app_creation'
]