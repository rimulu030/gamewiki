"""Voice recognition module for speech-to-text input."""

import json
import os
import sys
import logging
import threading
import time
from pathlib import Path
from typing import Optional
from threading import Lock

try:
    import sounddevice as sd
    import numpy as np
    import queue
    from vosk import Model, KaldiRecognizer, SetLogLevel
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logging.warning("Vosk or sounddevice not available. Voice input will be disabled.")

from PyQt6.QtCore import QThread, pyqtSignal, QObject

from src.game_wiki_tooltip.core.utils import package_file
from src.game_wiki_tooltip.core.i18n import get_current_language

logger = logging.getLogger(__name__)

# Suppress Vosk logging
if VOSK_AVAILABLE:
    SetLogLevel(-1)

# Global cache variables for audio devices
_audio_devices_cache = None
_cache_timestamp = 0
_last_refresh_time = 0
_refresh_lock = Lock()
CACHE_DURATION = 3600  # Cache for 1 hour
REFRESH_COOLDOWN = 2  # Refresh cooldown time in seconds


class VoiceRecognitionThread(QThread):
    """Thread for handling voice recognition without blocking UI."""
    
    # Signals
    partial_result = pyqtSignal(str)  # Real-time partial text
    final_result = pyqtSignal(str)    # Complete sentence
    error_occurred = pyqtSignal(str)  # Error messages
    silence_detected = pyqtSignal()   # Emitted when silence is detected
    
    def __init__(self, device_index: Optional[int] = None, silence_threshold: float = 2.0):
        super().__init__()
        self.is_recording = False
        self.model = None
        self.recognizer = None
        self.audio_stream = None
        self.audio_queue = None
        self.device_index = device_index  # Allow specifying audio device
        self.silence_threshold = silence_threshold  # Seconds of silence before auto-stop
        self.last_activity_time = time.time()
        self._last_text = ""  # Track text changes for activity detection
        
        # Model paths - use package_file for consistency
        try:
            # Try to use package_file first (works in both dev and packaged)
            self.models_dir = package_file("vosk_models")
        except Exception:
            # Fallback for edge cases
            base_path = Path(__file__).parent.parent.parent
            self.models_dir = base_path / "assets" / "vosk_models"
        
    def initialize_model(self):
        """Initialize Vosk model based on current language."""
        if not VOSK_AVAILABLE:
            self.error_occurred.emit("Voice recognition not available. Please install vosk and sounddevice.")
            return False
            
        current_lang = get_current_language()
        
        # Model mapping
        model_names = {
            'zh': 'vosk-model-small-cn-0.22',
            'en': 'vosk-model-small-en-us-0.15',
            'ru': 'vosk-model-small-ru-0.22',
        }
        
        model_name = model_names.get(current_lang, model_names['en'])
        model_path = self.models_dir / model_name
        
        try:
            if not model_path.exists():
                error_msg = (
                    f"Voice model not found: {model_name}\n"
                    f"Please run 'python download_vosk_models.py' from project root\n"
                    f"or download from https://alphacephei.com/vosk/models\n"
                    f"and extract to: {self.models_dir}"
                )
                self.error_occurred.emit(error_msg)
                return False
                
            logger.info(f"Loading voice model: {model_name}")
            self.model = Model(str(model_path))
            # Note: recognizer sample rate will be set when opening audio stream
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Failed to load model: {str(e)}")
            logger.error(f"Model loading error: {e}")
            return False
    
    def run(self):
        """Main voice recognition loop using sounddevice."""
        if not self.initialize_model():
            return
            
        try:
            # Get device information
            device_index = self.device_index
            
            # Validate or find input device
            if device_index is not None:
                try:
                    device_info = sd.query_devices(device_index, 'input')
                    logger.info(f"Using specified audio input device: {device_info['name']}")
                except Exception as e:
                    self.error_occurred.emit(f"Invalid device index {device_index}: {str(e)}")
                    return
            else:
                # Find default input device
                try:
                    device_index = sd.default.device[0] if isinstance(sd.default.device, tuple) else sd.default.device
                    if device_index is None:
                        # Get default input device
                        device_info = sd.query_devices(kind='input')
                        device_index = device_info['index'] if isinstance(device_info, dict) else None
                    
                    if device_index is not None:
                        device_info = sd.query_devices(device_index, 'input')
                        logger.info(f"Using default audio input device: {device_info['name']}")
                except Exception:
                    self.error_occurred.emit("No microphone found. Please check your audio input devices.")
                    return
            
            # Get device info and determine sample rate
            try:
                device_info = sd.query_devices(device_index, 'input')
                # Try to use device's default sample rate first
                default_sr = int(device_info['default_samplerate'])
                SAMPLE_RATES = [16000, default_sr, 44100, 48000, 22050, 8000]
                # Remove duplicates while preserving order
                SAMPLE_RATES = list(dict.fromkeys(SAMPLE_RATES))
            except Exception as e:
                logger.warning(f"Could not get device info: {e}")
                SAMPLE_RATES = [16000, 44100, 48000, 22050, 8000]
            
            # Create audio queue for thread-safe audio data transfer
            self.audio_queue = queue.Queue()
            
            # Try different sample rates
            audio_opened = False
            used_sample_rate = None
            
            for sample_rate in SAMPLE_RATES:
                try:
                    # Test if this sample rate works
                    sd.check_input_settings(device=device_index, channels=1, samplerate=sample_rate)
                    
                    # Create recognizer with this sample rate
                    self.recognizer = KaldiRecognizer(self.model, sample_rate)
                    self.recognizer.SetWords(True)
                    used_sample_rate = sample_rate
                    audio_opened = True
                    logger.info(f"Audio configuration successful with sample rate: {sample_rate} Hz")
                    break
                except Exception as e:
                    logger.debug(f"Sample rate {sample_rate} Hz not supported: {e}")
                    continue
            
            if not audio_opened:
                self.error_occurred.emit(f"Could not configure audio. Tried sample rates: {SAMPLE_RATES}")
                return
            
            # Define audio callback
            def audio_callback(indata, frames, time_info, status):
                """Callback for audio stream."""
                if status:
                    logger.warning(f"Audio stream status: {status}")
                if self.is_recording:
                    # Convert float32 to int16 for Vosk
                    audio_data = (indata[:, 0] * 32767).astype(np.int16).tobytes()
                    self.audio_queue.put(audio_data)
            
            # Start audio stream
            self.audio_stream = sd.InputStream(
                samplerate=used_sample_rate,
                channels=1,
                dtype='float32',
                device=device_index,
                blocksize=4000,
                callback=audio_callback
            )
            
            with self.audio_stream:
                self.is_recording = True
                logger.info("Voice recording started")
                self.last_activity_time = time.time()
                
                while self.is_recording:
                    try:
                        # Get audio data from queue with timeout
                        data = self.audio_queue.get(timeout=0.1)
                        
                        if self.recognizer.AcceptWaveform(data):
                            # Complete result
                            result = json.loads(self.recognizer.Result())
                            text = result.get('text', '').strip()
                            if text:
                                self.final_result.emit(text)
                                self.last_activity_time = time.time()
                                self._last_text = text
                        else:
                            # Partial result
                            partial = json.loads(self.recognizer.PartialResult())
                            text = partial.get('partial', '').strip()
                            if text:
                                self.partial_result.emit(text)
                                if text != self._last_text:
                                    self.last_activity_time = time.time()
                                    self._last_text = text
                        
                        # Check for silence timeout
                        current_time = time.time()
                        if current_time - self.last_activity_time > self.silence_threshold:
                            logger.info(f"Silence detected for {self.silence_threshold} seconds, auto-stopping")
                            self.silence_detected.emit()
                            self.is_recording = False
                            break
                            
                    except queue.Empty:
                        # No audio data available, check if we should stop
                        if not self.is_recording:
                            break
                    except Exception as e:
                        if self.is_recording:
                            logger.error(f"Audio processing error: {e}")
                            
        except Exception as e:
            self.error_occurred.emit(f"Recording error: {str(e)}")
            logger.error(f"Voice recording error: {e}")
        finally:
            self.cleanup()
    
    def stop_recording(self):
        """Stop the recording."""
        if not self.is_recording:
            logger.debug("Recording already stopped")
            return
            
        self.is_recording = False
        logger.info("Voice recording stopped")
        
    def cleanup(self):
        """Clean up audio resources."""
        if self.audio_stream:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
        
        # Clear the queue
        if self.audio_queue:
            try:
                while not self.audio_queue.empty():
                    self.audio_queue.get_nowait()
            except:
                pass

def is_voice_recognition_available():
    """Check if voice recognition is available."""
    return VOSK_AVAILABLE


def test_device_availability(device_index, sample_rate=None):
    """Test if an audio input device is actually available and working.
    
    Args:
        device_index: Device index to test
        sample_rate: Sample rate to test with (uses device default if None)
        
    Returns:
        bool: True if device is available and working, False otherwise
    """
    if not VOSK_AVAILABLE:
        return False
    
    try:
        # Get device info to determine appropriate sample rate
        device_info = sd.query_devices(device_index, 'input')
        if sample_rate is None:
            sample_rate = int(device_info.get('default_samplerate', 16000))
        
        # Try to open a short audio stream to test if device is really available
        stream = sd.InputStream(
            device=device_index,
            channels=1,
            samplerate=sample_rate,
            blocksize=512,
            dtype='float32'
        )
        stream.start()
        # Brief test - just check if we can start the stream
        time.sleep(0.02)  # 20ms test
        stream.stop()
        stream.close()
        return True
    except Exception as e:
        logger.debug(f"Device {device_index} availability test failed: {e}")
        return False


def get_audio_input_devices(force_refresh=False, settings_manager=None, test_availability=True):
    """Get list of available audio input devices using sounddevice.
    
    Args:
        force_refresh: Force re-enumeration of devices, bypassing cache
        settings_manager: Optional SettingsManager instance to save cache to settings
        test_availability: Test if devices are actually available (default True)
        
    Returns:
        List of audio device dictionaries (only includes actually available devices if test_availability=True)
    """
    global _audio_devices_cache, _cache_timestamp, _last_refresh_time
    
    if not VOSK_AVAILABLE:
        return []
    
    current_time = time.time()
    
    # Try to load from settings cache first (if not forcing refresh)
    if not force_refresh and settings_manager:
        settings = settings_manager.get()
        cache_time = settings.get('audio_devices_cache_time', 0)
        cache_data = settings.get('audio_devices_cache', [])
        
        # Use settings cache if it's less than 7 days old
        if cache_data and cache_time and (current_time - cache_time < 7 * 24 * 3600):
            logger.info(f"Using audio devices from settings cache (age: {(current_time - cache_time) / 3600:.1f} hours)")
            _audio_devices_cache = cache_data
            _cache_timestamp = cache_time
            return cache_data
    
    # Check for refresh cooldown if force_refresh is requested
    if force_refresh:
        with _refresh_lock:
            if current_time - _last_refresh_time < REFRESH_COOLDOWN:
                logger.info(f"Refresh cooldown active ({REFRESH_COOLDOWN}s), using cached devices")
                if _audio_devices_cache is not None:
                    return _audio_devices_cache
                force_refresh = False  # Downgrade to normal request
            else:
                _last_refresh_time = current_time
    
    # Return memory cache if available and not forcing refresh
    if not force_refresh and _audio_devices_cache is not None:
        if current_time - _cache_timestamp < CACHE_DURATION:
            logger.info("Using memory cached audio devices")
            return _audio_devices_cache
    
    logger.info("Enumerating audio devices using sounddevice...")
    
    import re
    devices = []
    seen_base_names = {}  # Track unique device base names
    
    # System/virtual devices to filter out
    SYSTEM_DEVICES = [
        "Microsoft Sound Mapper",
        "Microsoft 声音映射器", 
        "主声音捕获驱动程序",
        "Primary Sound Capture Driver",
        "Microphone Array (Intel® Smart Sound Technology",  # Often problematic
    ]
    
    # API type indicators in device names
    API_PATTERNS = r'\s*\((MME|DirectSound|WASAPI|WDM-KS|Windows DirectSound|Windows WASAPI|Windows WDM-KS)\)'
    
    try:
        # Get all devices from sounddevice with timeout protection
        logger.debug("Calling sd.query_devices()...")
        try:
            all_devices = sd.query_devices()
            logger.debug(f"sd.query_devices() returned {len(all_devices) if all_devices else 0} devices")
        except Exception as sd_error:
            logger.error(f"sounddevice.query_devices() failed: {sd_error}")
            raise RuntimeError(f"Audio system query failed: {str(sd_error)}")
        
        for i, device_info in enumerate(all_devices):
            try:
                # Only process input devices
                if device_info['max_input_channels'] <= 0:
                    continue
                
                name = device_info['name']
                
                # Skip system/mapper devices
                if any(sys_dev in name for sys_dev in SYSTEM_DEVICES):
                    continue
                
                # Extract base name (remove API type suffix)
                clean_name = re.sub(API_PATTERNS, '', name).strip()
                
                # Remove index numbers that Windows sometimes adds
                clean_name = re.sub(r'\s*\(\d+\)$', '', clean_name)
                clean_name = re.sub(r'\s*\[\d+\]$', '', clean_name)
                
                # Check if we've seen this base device name
                if clean_name in seen_base_names:
                    # Keep the one with better properties (higher sample rate or more channels)
                    existing = seen_base_names[clean_name]
                    if (device_info['default_samplerate'] > existing['default_sample_rate'] or
                        device_info['max_input_channels'] > existing['channels']):
                        # This version is better, replace
                        seen_base_names[clean_name] = {
                            'index': i,
                            'name': clean_name,
                            'channels': device_info['max_input_channels'],
                            'default_sample_rate': device_info['default_samplerate'],
                            'original_name': name  # Keep original for debugging
                        }
                else:
                    # First time seeing this device
                    seen_base_names[clean_name] = {
                        'index': i,
                        'name': clean_name,
                        'channels': device_info['max_input_channels'],
                        'default_sample_rate': device_info['default_samplerate'],
                        'original_name': name
                    }
                    
            except Exception as e:
                logger.debug(f"Error processing device {i}: {e}")
                continue
        
        # Convert to list, removing debug info and optionally testing availability
        if test_availability:
            logger.info("Testing device availability...")
            tested_devices = []
            
            for device_data in seen_base_names.values():
                device_index = device_data['index']
                device_name = device_data['name']
                
                # Test if device is actually available
                logger.debug(f"Testing device '{device_name}' (index {device_index})...")
                is_available = test_device_availability(
                    device_index, 
                    device_data['default_sample_rate']
                )
                
                if is_available:
                    logger.debug(f"Device '{device_name}' is available")
                    tested_devices.append({
                        'index': device_index,
                        'name': device_name,
                        'channels': device_data['channels'],
                        'default_sample_rate': device_data['default_sample_rate']
                    })
                else:
                    logger.info(f"Device '{device_name}' is not available, filtering out")
            
            devices = tested_devices
        else:
            # Skip availability testing
            devices = []
            for device_data in seen_base_names.values():
                devices.append({
                    'index': device_data['index'],
                    'name': device_data['name'],
                    'channels': device_data['channels'],
                    'default_sample_rate': device_data['default_sample_rate']
                })
        
        # Sort by name for consistent display
        devices.sort(key=lambda d: d['name'])
        
        if test_availability:
            logger.info(f"Found {len(devices)} available audio input devices (filtered from {len(seen_base_names)} total)")
        else:
            logger.info(f"Found {len(devices)} audio input devices (availability not tested)")
        
        # Update memory cache
        _audio_devices_cache = devices
        _cache_timestamp = current_time
        
        # Save to settings if manager provided
        if settings_manager:
            try:
                settings_manager.update({
                    'audio_devices_cache': devices,
                    'audio_devices_cache_time': current_time
                })
                logger.info("Audio devices cache saved to settings")
            except Exception as e:
                logger.warning(f"Failed to save audio devices cache to settings: {e}")
        
    except Exception as e:
        logger.error(f"Error getting audio devices: {e}")
        # Return cached devices if available on error
        if _audio_devices_cache is not None:
            logger.info("Returning cached devices due to enumeration error")
            return _audio_devices_cache
    
    return devices


def initialize_audio_devices(settings_manager=None):
    """Initialize audio device cache on program startup.
    
    This function checks if audio devices are cached in settings.
    If cache exists and is recent (< 7 days), skip enumeration.
    Otherwise, enumerate devices and save to cache.
    
    Args:
        settings_manager: Optional SettingsManager instance to load/save cache
    """
    if not VOSK_AVAILABLE:
        logger.info("Voice recognition not available, skipping audio device initialization")
        return
    
    # Check if we have a recent cache in settings
    if settings_manager:
        settings = settings_manager.get()
        cache_time = settings.get('audio_devices_cache_time', 0)
        cache_data = settings.get('audio_devices_cache', [])
        
        if cache_data and cache_time:
            age_days = (time.time() - cache_time) / (24 * 3600)
            if age_days < 7:
                logger.info(f"Audio devices cache found in settings (age: {age_days:.1f} days), skipping enumeration")
                # Load cache into memory
                global _audio_devices_cache, _cache_timestamp
                _audio_devices_cache = cache_data
                _cache_timestamp = cache_time
                return
            else:
                logger.info(f"Audio devices cache is stale (age: {age_days:.1f} days), will enumerate")
    
    # Add a small delay to ensure Qt/system is ready
    time.sleep(0.5)
    
    logger.info("Initializing audio devices (first run or stale cache)...")
    try:
        # Enumerate devices and save to cache
        devices = get_audio_input_devices(force_refresh=True, settings_manager=settings_manager)
        logger.info(f"Audio device initialization complete. Found {len(devices)} devices.")
    except Exception as e:
        logger.error(f"Failed to initialize audio devices: {e}")
        # Don't let audio initialization failure crash the app
        import traceback
        logger.debug(f"Audio initialization traceback: {traceback.format_exc()}")