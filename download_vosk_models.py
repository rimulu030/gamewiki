#!/usr/bin/env python
"""Download Vosk models for voice recognition."""

import os
import sys
import argparse
import requests
import zipfile
from pathlib import Path

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("Warning: tqdm not installed. Progress bars will not be shown.")
    print("Install with: pip install tqdm")

def download_file(url, dest_path):
    """Download file with progress bar."""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(dest_path, 'wb') as f:
        if TQDM_AVAILABLE:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=dest_path.name) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))
        else:
            # Simple progress without tqdm
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    print(f"\rDownloading {dest_path.name}: {percent:.1f}%", end='', flush=True)
            print()  # New line after download

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download Vosk voice recognition models')
    parser.add_argument('--chinese', '-c', action='store_true', 
                        help='Download Chinese model (42 MB)')
    parser.add_argument('--russian', '-r', action='store_true', 
                        help='Download Russian model (45 MB)')
    parser.add_argument('--all', action='store_true',
                        help='Download all models (English + Chinese + Russian, ~127 MB)')
    parser.add_argument('--list', action='store_true',
                        help='List available models and their status')
    args = parser.parse_args()
    
    models = {
        'vosk-model-small-cn-0.22': {
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip',
            'desc': 'Chinese voice model (42 MB)',
            'lang': 'zh'
        },
        'vosk-model-small-en-us-0.15': {
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
            'desc': 'English voice model (40 MB)',
            'lang': 'en'
        },
        'vosk-model-small-ru-0.22': {
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip',
            'desc': 'Russian voice model (45 MB)',
            'lang': 'ru'
        },
    }
    
    # Target directory
    models_dir = Path("src/game_wiki_tooltip/assets/vosk_models")
    models_dir.mkdir(parents=True, exist_ok=True)
    
    # Handle --list argument
    if args.list:
        print("=== Available Vosk Models ===")
        for model_name, info in models.items():
            model_path = models_dir / model_name
            status = "✓ Installed" if model_path.exists() else "✗ Not installed"
            print(f"{info['desc']} [{info['lang']}]: {status}")
        print(f"\nModels location: {models_dir.absolute()}")
        return
    
    # Determine which models to download
    models_to_download = {}
    if args.all:
        models_to_download = models
        print("=== Vosk Voice Recognition Model Downloader ===")
        print("Downloading ALL models (English + Chinese + Russian)")
        print("Total download size: ~127 MB\n")
    elif args.chinese:
        # Only Chinese model
        models_to_download = {k: v for k, v in models.items() if v['lang'] == 'zh'}
        print("=== Vosk Voice Recognition Model Downloader ===")
        print("Downloading Chinese model only")
        print("Total download size: ~42 MB\n")
    elif args.russian:
        # Only Russian model
        models_to_download = {k: v for k, v in models.items() if v['lang'] == 'ru'}
        print("=== Vosk Voice Recognition Model Downloader ===")
        print("Downloading Russian model only")
        print("Total download size: ~45 MB\n")
    else:
        # Default: only English model
        models_to_download = {k: v for k, v in models.items() if v['lang'] == 'en'}
        print("=== Vosk Voice Recognition Model Downloader ===")
        print("Downloading English model only (default)")
        print("Total download size: ~40 MB")
        print("To download Chinese model, use: python download_vosk_models.py --chinese")
        print("To download all models, use: python download_vosk_models.py --all\n")
    
    success_count = 0
    
    for model_name, info in models_to_download.items():
        model_path = models_dir / model_name
        
        if model_path.exists():
            print(f"✓ {model_name} already exists, skipping...")
            success_count += 1
            continue
            
        print(f"\nDownloading {info['desc']}...")
        print(f"URL: {info['url']}")
        
        zip_path = models_dir / f"{model_name}.zip"
        
        try:
            # Download
            download_file(info['url'], zip_path)
            
            # Extract
            print(f"Extracting {model_name}...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Extract to models_dir, the zip should contain the model folder
                zip_ref.extractall(models_dir)
            
            # Clean up zip file
            zip_path.unlink()
            
            print(f"✓ {model_name} installed successfully!")
            success_count += 1
            
        except KeyboardInterrupt:
            print("\n\nDownload cancelled by user.")
            if zip_path.exists():
                zip_path.unlink()
            sys.exit(1)
            
        except Exception as e:
            print(f"✗ Error installing {model_name}: {e}")
            if zip_path.exists():
                zip_path.unlink()
    
    print("\n" + "="*50)
    total_requested = len(models_to_download)
    if total_requested == 0:
        print("No models were selected for download.")
        return
        
    if success_count == total_requested:
        print(f"✅ All requested models ({success_count}/{total_requested}) downloaded successfully!")
        print("Voice recognition is ready for the installed languages.")
    else:
        print(f"⚠️  {success_count}/{total_requested} models installed.")
        print("Some models failed to download. Voice recognition may not work for those languages.")
    
    print("\nModels location:", models_dir.absolute())
    
    # Check if Chinese model is missing and user is using Chinese
    chinese_model = 'vosk-model-small-cn-0.22'
    if chinese_model not in models_to_download and not (models_dir / chinese_model).exists():
        print("\nNote: Chinese model not installed. To download it, run:")
        print("  python download_vosk_models.py --chinese")
        
    # Check if Russian model is missing and user is using Russian
    russian_model = 'vosk-model-small-ru-0.22'
    if russian_model not in models_to_download and not (models_dir / russian_model).exists():
        print("\nNote: Russian model not installed. To download it, run:")
        print("  python download_vosk_models.py --russian")

if __name__ == "__main__":
    main()