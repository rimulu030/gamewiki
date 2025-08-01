"""
WebView2 setup helper - Downloads necessary WebView2 assemblies
"""

import os
import sys
import zipfile
import tempfile
import urllib.request
from pathlib import Path


def download_webview2_sdk():
    """Download WebView2 SDK assemblies from NuGet"""
    
    # WebView2 NuGet package URL - using latest stable version
    # Using version 1.0.3351.48 which is the latest stable release
    nuget_url = "https://www.nuget.org/api/v2/package/Microsoft.Web.WebView2/1.0.3351.48"
    
    # Target directory for assemblies
    target_dir = Path(__file__).parent / "webview2" / "lib"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if already downloaded
    core_dll = target_dir / "Microsoft.Web.WebView2.Core.dll"
    winforms_dll = target_dir / "Microsoft.Web.WebView2.WinForms.dll"
    loader_dll = target_dir / "WebView2Loader.dll"
    
    if core_dll.exists() and winforms_dll.exists() and loader_dll.exists():
        print("✅ WebView2 assemblies already downloaded")
        return True
    
    print("📥 Downloading WebView2 SDK from NuGet...")
    
    try:
        # Download NuGet package
        with tempfile.NamedTemporaryFile(suffix=".nupkg", delete=False) as tmp:
            urllib.request.urlretrieve(nuget_url, tmp.name)
            temp_file = tmp.name
        
        print("📦 Extracting assemblies...")
        
        # Extract the package (it's a zip file)
        with zipfile.ZipFile(temp_file, 'r') as zip_ref:
            # List all files in the package for debugging
            print("Available files in NuGet package:")
            for name in zip_ref.namelist()[:10]:  # Show first 10 files
                print(f"  - {name}")
            
            # Extract .NET assemblies (try different target frameworks)
            managed_files = [
                ("lib/net45/Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.Core.dll"),
                ("lib/net45/Microsoft.Web.WebView2.WinForms.dll", "Microsoft.Web.WebView2.WinForms.dll"),
                ("lib/net462/Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.Core.dll"),
                ("lib/net462/Microsoft.Web.WebView2.WinForms.dll", "Microsoft.Web.WebView2.WinForms.dll"),
                ("lib/netcoreapp3.0/Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.Core.dll"),
                ("lib/netcoreapp3.0/Microsoft.Web.WebView2.WinForms.dll", "Microsoft.Web.WebView2.WinForms.dll"),
            ]
            
            extracted_managed = set()
            for source_path, target_name in managed_files:
                if source_path in zip_ref.namelist() and target_name not in extracted_managed:
                    file_data = zip_ref.read(source_path)
                    target_file = target_dir / target_name
                    target_file.write_bytes(file_data)
                    print(f"  ✓ Extracted {target_name}")
                    extracted_managed.add(target_name)
            
            # Extract native DLLs (WebView2Loader.dll)
            native_files = [
                "runtimes/win-x64/native/WebView2Loader.dll",
                "runtimes/win-x86/native/WebView2Loader.dll",
                "runtimes/win/native/WebView2Loader.dll",
                "native/x64/WebView2Loader.dll",
                "native/x86/WebView2Loader.dll",
                "build/native/x64/WebView2Loader.dll",
                "build/native/x86/WebView2Loader.dll",
            ]
            
            loader_extracted = False
            for file_path in native_files:
                if file_path in zip_ref.namelist():
                    file_data = zip_ref.read(file_path)
                    # Prefer x64 version, but accept any
                    if "x64" in file_path or not loader_extracted:
                        target_file = target_dir / "WebView2Loader.dll"
                        target_file.write_bytes(file_data)
                        print(f"  ✓ Extracted WebView2Loader.dll from {file_path}")
                        loader_extracted = True
                        if "x64" in file_path:
                            break  # Prefer x64 version
        
        # Clean up
        os.unlink(temp_file)
        
        # Verify all required files are present
        if not loader_extracted:
            print("⚠️  WebView2Loader.dll not found in NuGet package")
            print("   Attempting alternative download method...")
            return download_webview2_loader_alternative(target_dir)
        
        print("✅ WebView2 SDK downloaded successfully")
        print(f"📁 Assemblies saved to: {target_dir}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to download WebView2 SDK: {e}")
        return False


def download_webview2_loader_alternative(target_dir: Path):
    """Alternative method to download WebView2Loader.dll"""
    
    print("🔄 Trying alternative WebView2Loader.dll download...")
    
    # Try downloading from Microsoft Edge WebView2 package directly
    alternative_urls = [
        "https://www.nuget.org/api/v2/package/Microsoft.Web.WebView2/1.0.2903.40",  # Another stable version
        "https://www.nuget.org/api/v2/package/Microsoft.Web.WebView2/1.0.2792.45",  # Fallback version
    ]
    
    for url in alternative_urls:
        try:
            print(f"📥 Trying {url}...")
            
            with tempfile.NamedTemporaryFile(suffix=".nupkg", delete=False) as tmp:
                urllib.request.urlretrieve(url, tmp.name)
                temp_file = tmp.name
            
            with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                # Look for WebView2Loader.dll in all possible locations
                for file_path in zip_ref.namelist():
                    if "WebView2Loader.dll" in file_path:
                        print(f"  Found WebView2Loader.dll at: {file_path}")
                        file_data = zip_ref.read(file_path)
                        target_file = target_dir / "WebView2Loader.dll"
                        target_file.write_bytes(file_data)
                        print(f"  ✓ Extracted WebView2Loader.dll")
                        os.unlink(temp_file)
                        return True
            
            os.unlink(temp_file)
            
        except Exception as e:
            print(f"   Failed: {e}")
            continue
    
    # If all else fails, suggest manual download
    print("⚠️  Could not automatically download WebView2Loader.dll")
    print("📋 Manual download option:")
    print("   1. Download WebView2 SDK from: https://developer.microsoft.com/microsoft-edge/webview2/")
    print("   2. Extract WebView2Loader.dll to:", target_dir)
    print("   3. Or install WebView2 Runtime which may provide system-wide access")
    
    return False


def check_webview2_runtime():
    """Check if WebView2 Runtime is installed"""
    import winreg
    
    try:
        # Check for WebView2 Runtime in registry
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        version = winreg.QueryValueEx(key, "pv")[0]
        winreg.CloseKey(key)
        print(f"✅ WebView2 Runtime installed: version {version}")
        return True
    except:
        # Also check for Edge installation
        try:
            key_path = r"SOFTWARE\WOW6432Node\Microsoft\Edge\BLBeacon"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            version = winreg.QueryValueEx(key, "version")[0]
            winreg.CloseKey(key)
            # Edge version 83+ includes WebView2
            if int(version.split('.')[0]) >= 83:
                print(f"✅ Microsoft Edge installed: version {version} (includes WebView2)")
                return True
        except:
            pass
        
        print("❌ WebView2 Runtime not installed")
        print("📥 Download from: https://go.microsoft.com/fwlink/p/?LinkId=2124703")
        return False


def verify_installation(target_dir: Path):
    """Verify that all required files are present"""
    required_files = [
        "Microsoft.Web.WebView2.Core.dll",
        "Microsoft.Web.WebView2.WinForms.dll",
        "WebView2Loader.dll"
    ]
    
    missing_files = []
    for file_name in required_files:
        file_path = target_dir / file_name
        if not file_path.exists():
            missing_files.append(file_name)
        else:
            # Check file size to ensure it's not empty
            if file_path.stat().st_size == 0:
                missing_files.append(f"{file_name} (empty)")
    
    if missing_files:
        print(f"⚠️  Missing or invalid files: {', '.join(missing_files)}")
        return False
    
    print("✅ All required WebView2 files are present")
    return True


def main():
    """Main setup function"""
    print("🔧 WebView2 Setup for GameWiki")
    print("=" * 50)
    
    # Check runtime
    runtime_ok = check_webview2_runtime()
    
    # Download SDK
    sdk_ok = download_webview2_sdk()
    
    # Verify installation
    target_dir = Path(__file__).parent / "webview2" / "lib"
    verification_ok = verify_installation(target_dir)
    
    # Check pythonnet
    try:
        import clr
        print("✅ pythonnet is installed")
        pythonnet_ok = True
    except ImportError:
        print("❌ pythonnet not installed")
        print("📥 Install with: pip install pythonnet")
        pythonnet_ok = False
    
    print("\n" + "=" * 50)
    
    if runtime_ok and sdk_ok and verification_ok and pythonnet_ok:
        print("✅ WebView2 setup complete! You can now use WebView2 in the application.")
    else:
        print("⚠️  Some components are missing. Please resolve the issues above.")
        
        if not runtime_ok:
            print("\n🔧 To fix Runtime issue:")
            print("   Download and install WebView2 Runtime:")
            print("   https://go.microsoft.com/fwlink/p/?LinkId=2124703")
            
        if not pythonnet_ok:
            print("\n🔧 To fix pythonnet issue:")
            print("   Run: pip install pythonnet")
        
        if not verification_ok:
            print("\n🔧 To fix missing files:")
            print("   1. Delete the webview2/lib folder and re-run this script")
            print("   2. Or manually download WebView2 SDK and extract files")


if __name__ == "__main__":
    main()