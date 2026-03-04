"""Vosk model manager for downloading and managing voice recognition models."""

import os
import sys
import logging
import requests
import zipfile
import threading
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class VoskModelManager:
    """Manager for Vosk voice recognition models."""
    
    MODELS = {
        'chinese': {
            'name': 'vosk-model-small-cn-0.22',
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip',
            'size': '42 MB',
            'lang': 'zh'
        },
        'english': {
            'name': 'vosk-model-small-en-us-0.15',
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
            'size': '40 MB',
            'lang': 'en'
        },
        'russian': {
            'name': 'vosk-model-small-ru-0.22',
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip',
            'size': '45 MB',
            'lang': 'ru'
        }
    }
    
    def __init__(self):
        """Initialize the Vosk model manager."""
        # Try to find the models directory
        try:
            from src.game_wiki_tooltip.core.utils import package_file
            self.models_dir = package_file("vosk_models")
        except Exception:
            # Fallback to relative path
            base_path = Path(__file__).parent.parent
            self.models_dir = base_path / "assets" / "vosk_models"
        
        # Ensure directory exists
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
    def is_model_available(self, model_type: str) -> bool:
        """Check if a model is available locally.
        
        Args:
            model_type: 'chinese' or 'english' or 'russian'
            
        Returns:
            True if model is installed, False otherwise
        """
        if model_type not in self.MODELS:
            return False
            
        model_info = self.MODELS[model_type]
        model_path = self.models_dir / model_info['name']
        return model_path.exists()
    
    def get_model_path(self, model_type: str) -> Optional[Path]:
        """Get the path to a model if it exists.
        
        Args:
            model_type: 'chinese' or 'english' or 'russian'
            
        Returns:
            Path to model directory or None if not found
        """
        if not self.is_model_available(model_type):
            return None
            
        model_info = self.MODELS[model_type]
        return self.models_dir / model_info['name']
    
    def download_model(self, model_type: str, progress_callback: Optional[Callable] = None) -> bool:
        """Download a specific model.
        
        Args:
            model_type: 'chinese' or 'english' or 'russian'
            progress_callback: Optional callback function(progress: int, status: str)
            
        Returns:
            True if successful, False otherwise
        """
        if model_type not in self.MODELS:
            logger.error(f"Unknown model type: {model_type}")
            return False
            
        model_info = self.MODELS[model_type]
        model_name = model_info['name']
        model_url = model_info['url']
        model_path = self.models_dir / model_name
        
        # Check if already exists
        if model_path.exists():
            logger.info(f"Model {model_name} already exists")
            if progress_callback:
                progress_callback(100, f"{model_name} already installed")
            return True
        
        zip_path = self.models_dir / f"{model_name}.zip"
        
        try:
            # Download the model
            logger.info(f"Downloading {model_name} from {model_url}")
            if progress_callback:
                progress_callback(0, f"Downloading {model_name}...")
            
            response = requests.get(model_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0 and progress_callback:
                            progress = int((downloaded / total_size) * 90)  # 90% for download
                            status = f"Downloading: {downloaded / (1024*1024):.1f}/{total_size / (1024*1024):.1f} MB"
                            progress_callback(progress, status)
            
            # Extract the model
            logger.info(f"Extracting {model_name}")
            if progress_callback:
                progress_callback(90, f"Extracting {model_name}...")
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.models_dir)
            
            # Clean up zip file
            zip_path.unlink()
            
            logger.info(f"Successfully installed {model_name}")
            if progress_callback:
                progress_callback(100, f"{model_name} installed successfully")
            
            return True
            
        except requests.RequestException as e:
            logger.error(f"Failed to download {model_name}: {e}")
            if progress_callback:
                progress_callback(0, f"Download failed: {str(e)}")
            return False
            
        except zipfile.BadZipFile as e:
            logger.error(f"Failed to extract {model_name}: {e}")
            if progress_callback:
                progress_callback(0, f"Extraction failed: {str(e)}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error installing {model_name}: {e}")
            if progress_callback:
                progress_callback(0, f"Installation failed: {str(e)}")
            return False
            
        finally:
            # Clean up zip file if it exists
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except:
                    pass
    
    def download_model_async(self, model_type: str, progress_callback: Optional[Callable] = None,
                           completion_callback: Optional[Callable] = None):
        """Download a model asynchronously in a separate thread.
        
        Args:
            model_type: 'chinese' or 'english' or 'russian'
            progress_callback: Optional callback function(progress: int, status: str)
            completion_callback: Optional callback function(success: bool, message: str)
        """
        def download_thread():
            success = self.download_model(model_type, progress_callback)
            if completion_callback:
                if success:
                    completion_callback(True, f"{self.MODELS[model_type]['name']} installed successfully")
                else:
                    completion_callback(False, f"Failed to install {self.MODELS[model_type]['name']}")
        
        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()
        
    def get_model_info(self, model_type: str) -> Optional[dict]:
        """Get information about a model.
        
        Args:
            model_type: 'chinese' or 'english' or 'russian'
            
        Returns:
            Dictionary with model information or None if not found
        """
        return self.MODELS.get(model_type)
    
    def list_models(self) -> dict:
        """List all available models and their status.
        
        Returns:
            Dictionary mapping model types to their status
        """
        status = {}
        for model_type in self.MODELS:
            status[model_type] = {
                'installed': self.is_model_available(model_type),
                'info': self.MODELS[model_type]
            }
        return status