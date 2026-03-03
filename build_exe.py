#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GameWiki Assistant Packaging Script

This script is used to package GameWiki Assistant into a standalone exe file.
Supports both onefile and onedir modes, with optional Inno Setup integration.
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

def print_status(message):
    """Print status information"""
    print(f"🔧 {message}")

def print_error(message):
    """Print error information"""
    print(f"❌ Error: {message}")

def print_success(message):
    """Print success information"""
    print(f"✅ {message}")

def run_command(command, cwd=None):
    """Execute command and return result"""
    import locale
    
    # Get system default encoding
    system_encoding = locale.getpreferredencoding()
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding=system_encoding,
            errors='replace'  # Handle encoding errors with replacement characters
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        # Ensure error information can also be decoded correctly
        error_msg = e.stderr if e.stderr else str(e)
        return False, error_msg
    except UnicodeDecodeError as e:
        print_error(f"Encoding error, trying UTF-8: {e}")
        # If system encoding fails, try UTF-8
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                check=True, 
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e2:
            error_msg = e2.stderr if e2.stderr else str(e2)
            return False, error_msg

def install_dependencies():
    """Install/update dependencies"""
    print_status("Installing/updating dependencies...")
    # 使用当前 Python 解释器执行 pip，避免 PATH 中无 pip 时失败
    pip_cmd = f'"{sys.executable}" -m pip'
    
    success, output = run_command(f"{pip_cmd} install --upgrade pip")
    if not success:
        print_error(f"Updating pip failed: {output}")
        return False
    
    success, output = run_command(f"{pip_cmd} install -r requirements.txt")
    if not success:
        print_error(f"Installing dependencies failed: {output}")
        return False
    
    print_success("Dependencies installed")
    return True

def clean_build():
    """Clean build directory"""
    print_status("Cleaning previous build files...")
    
    # 清理 PyInstaller 生成的目录
    dirs_to_clean = ['build', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"  Deleted: {dir_name}")
            except Exception as e:
                print(f"  Cannot delete {dir_name}: {e}")
                # Continue, do not stop the entire process
    
    # 清理便携版目录（如果存在）
    portable_dirs = [
        'GameWikiAssistant_Portable_onedir',
        'GameWikiAssistant_Portable_onefile'
    ]
    for dir_name in portable_dirs:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"  Deleted: {dir_name}")
            except Exception as e:
                print(f"  Cannot delete {dir_name}: {e}")
    
    # Delete spec generated cache files
    try:
        for file in Path('.').glob('*.spec~'):
            file.unlink()
            print(f"  Deleted: {file}")
    except Exception as e:
        print(f"  Error cleaning spec cache files: {e}")
    
    print_success("Build directory cleaned")
    return True  # Ensure return True

def check_assets():
    """Check if necessary resource files exist"""
    print_status("Checking resource files...")
    
    required_files = [
        "src/game_wiki_tooltip/assets/app.ico",
        "src/game_wiki_tooltip/assets/games.json",
        "src/game_wiki_tooltip/assets/settings.json",
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print_error("Missing necessary resource files:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    print_success("Resource files checked")
    return True

def check_ai_modules():
    """Check if AI modules can be imported correctly"""
    print_status("Checking AI module dependencies...")
    
    # AI module import tests
    ai_modules_to_test = [
        "src.game_wiki_tooltip.ai.hybrid_retriever",
        "src.game_wiki_tooltip.ai.enhanced_bm25_indexer", 
        "src.game_wiki_tooltip.ai.batch_embedding",
        "src.game_wiki_tooltip.ai.rag_query",
        "src.game_wiki_tooltip.ai.unified_query_processor",
        "src.game_wiki_tooltip.core.config",
    ]
    
    # Temporarily add src to path for testing
    original_sys_path = sys.path.copy()
    src_path = Path("src")
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    failed_imports = []
    
    try:
        for module_name in ai_modules_to_test:
            try:
                __import__(module_name)
                print(f"  ✓ {module_name}")
            except ImportError as e:
                failed_imports.append(f"{module_name}: {e}")
                print(f"  ❌ {module_name}: {e}")
            except Exception as e:
                print(f"  ⚠️  {module_name}: {e} (non-import error)")
    finally:
        # Restore original sys.path
        sys.path[:] = original_sys_path
    
    if failed_imports:
        print_error("Some AI modules failed to import:")
        for failure in failed_imports:
            print(f"  - {failure}")
        print("\n💡 This may cause 'hybrid retriever module is not available' errors in the packaged exe")
        print("   Please ensure all dependencies are properly installed")
        return False
    
    print_success("All AI modules can be imported correctly")
    return True

def check_webview2_requirements():
    """Check WebView2 WinRT requirements"""
    print_status("Checking WebView2 WinRT requirements...")
    
    # Check WinRT packages
    required_packages = [
        ('winrt', 'winrt-runtime'),
        ('webview2.microsoft.web.webview2.core', 'webview2-Microsoft.Web.WebView2.Core'),
        ('winrt.windows.foundation', 'winrt-Windows.Foundation'),
        ('qasync', 'qasync')
    ]
    
    missing_packages = []
    for module_name, package_name in required_packages:
        try:
            # Try to import the module
            if '.' in module_name:
                # For nested modules, use __import__ with fromlist
                parts = module_name.split('.')
                __import__(module_name, fromlist=[parts[-1]])
            else:
                __import__(module_name)
            print(f"  ✓ {package_name} installed")
        except ImportError:
            missing_packages.append(package_name)
            print(f"  ✗ {package_name} not installed")
    
    if missing_packages:
        print_error(f"Missing WinRT packages: {', '.join(missing_packages)}")
        print("Please run: pip install -r requirements.txt")
        return False
    
    print("  ✓ All WinRT packages installed")
    
    # Check WebView2 Runtime (optional check, because it may be installed on the target machine)
    try:
        import winreg
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        version = winreg.QueryValueEx(key, "pv")[0]
        winreg.CloseKey(key)
        print(f"  ✓ WebView2 Runtime installed: {version}")
    except:
        print("  ⚠️  WebView2 Runtime not detected, but user may need to install it on the target machine")
    
    print_success("WebView2 WinRT requirements checked")
    return True

def verify_spec_for_webview2():
    """Verify spec file has correct WinRT WebView2 configuration"""
    print_status("Verifying PyInstaller configuration for WinRT WebView2...")
    
    spec_file = "game_wiki_tooltip.spec"
    if not os.path.exists(spec_file):
        print_error(f"Spec file not found: {spec_file}")
        return False
    
    # Read current spec file
    with open(spec_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if WinRT WebView2 configuration is included
    required_imports = ['winrt', 'webview2', 'qasync']
    missing_imports = []
    
    for import_name in required_imports:
        if f"'{import_name}" not in content and f'"{import_name}' not in content:
            missing_imports.append(import_name)
    
    if missing_imports:
        print_error(f"Spec file missing WinRT imports: {', '.join(missing_imports)}")
        print("Please update your spec file to include WinRT WebView2 imports")
        return False
    
    print("  ✓ Spec file includes WinRT WebView2 configuration")
    
    # Verify old pythonnet references are removed
    if "pythonnet" in content or "clr" in content:
        print("  ⚠️  Warning: Spec file still contains old pythonnet references")
        print("     Consider removing pythonnet/clr imports from hiddenimports")
    
    print_success("Spec file verified for WinRT WebView2")
    return True

def build_uninstaller(output_dir):
    """Build uninstaller exe using PyInstaller
    
    Args:
        output_dir: Directory to place the uninstaller exe
    """
    print_status("Building uninstaller...")
    
    # Check if uninstaller.py exists
    if not Path("uninstaller.py").exists():
        print_error("uninstaller.py not found")
        return False
    
    # Check if uninstaller.spec exists, if not create it
    if not Path("uninstaller.spec").exists():
        print_status("Creating uninstaller.spec...")
        spec_content = '''# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for GameWikiTooltip Uninstaller
"""

a = Analysis(
    ['uninstaller.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include the app icon for the uninstaller
        ('src/game_wiki_tooltip/assets/app.ico', '.')
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Uninstall',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI application, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src\\\\game_wiki_tooltip\\\\assets\\\\app.ico',
    uac_admin=False,  # Don't force admin, let user choose
    uac_uiaccess=False,
)'''
        try:
            with open("uninstaller.spec", "w", encoding="utf-8") as f:
                f.write(spec_content)
        except Exception as e:
            print_error(f"Failed to create uninstaller.spec: {e}")
            return False
    
    # Build the uninstaller to a temporary directory first
    temp_dist = "dist_uninstaller"
    success, output = run_command(f'"{sys.executable}" -m PyInstaller uninstaller.spec --clean --noconfirm --distpath {temp_dist}')
    
    if not success:
        print_error(f"Uninstaller build failed: {output}")
        return False
    
    # Check if uninstaller was built successfully
    uninstaller_exe = Path(temp_dist) / "GameWikiUninstaller.exe"
    if not uninstaller_exe.exists():
        print_error("Uninstaller exe not found after build")
        return False
    
    # Copy uninstaller to the output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target_exe = output_path / "Uninstall.exe"
    
    try:
        shutil.copy2(uninstaller_exe, target_exe)
        print_success(f"Uninstaller created: {target_exe}")
        
        # Clean up temporary build directory
        if Path(temp_dist).exists():
            shutil.rmtree(temp_dist, ignore_errors=True)
        
        return True
    except Exception as e:
        print_error(f"Failed to copy uninstaller: {e}")
        return False

def build_exe(mode='onedir'):
    """Build exe file using PyInstaller
    
    Args:
        mode: 'onedir' or 'onefile' - specifies packaging mode
    """
    print_status(f"Building exe file in {mode} mode...")
    print("This may take a few minutes, please wait...")
    
    # 定义最终输出目录
    final_output_dir = f"GameWikiAssistant_Portable_{mode}"
    
    # 使用 --distpath 参数直接指定输出到最终目录
    spec_file = "game_wiki_tooltip.spec"
    
    # 修改 PyInstaller 命令，直接输出到最终目录
    success, output = run_command(f'"{sys.executable}" -m PyInstaller {spec_file} --clean --noconfirm --distpath {final_output_dir}')
    
    if not success:
        print_error(f"Build failed: {output}")
        return False
    
    # 检查生成的文件
    if mode == 'onedir':
        exe_dir = Path(final_output_dir) / "GameWikiAssistant"
        exe_path = exe_dir / "GameWikiAssistant.exe"
        if exe_dir.exists() and exe_path.exists():
            print_success(f"Build successful! Output directory: {exe_dir.absolute()}")
            # 计算总目录大小
            total_size = sum(f.stat().st_size for f in exe_dir.rglob('*') if f.is_file())
            print(f"Total size: {total_size / 1024 / 1024:.1f} MB")
            return True
    else:
        exe_path = Path(final_output_dir) / "GameWikiAssistant.exe"
        if exe_path.exists():
            print_success(f"Build successful! exe file location: {exe_path.absolute()}")
            print(f"File size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
            return True
    
    print_error("Build completed but output not found")
    return False

def create_portable_package(mode='onedir'):
    """Create portable package
    
    Args:
        mode: 'onedir' or 'onefile' - specifies which build to package
    """
    print_status(f"Adding portable package files for {mode} build...")
    
    # 最终目录已经由 PyInstaller 直接创建
    portable_dir = Path(f"GameWikiAssistant_Portable_{mode}")
    
    if not portable_dir.exists():
        print_error(f"Target directory not found: {portable_dir}")
        return False
    
    # 验证构建文件是否存在
    if mode == 'onedir':
        exe_path = portable_dir / "GameWikiAssistant" / "GameWikiAssistant.exe"
        if not exe_path.exists():
            print_error(f"OneDir build not found: {exe_path}")
            return False
    else:
        exe_path = portable_dir / "GameWikiAssistant.exe"
        if not exe_path.exists():
            print_error(f"Onefile build not found: {exe_path}")
            return False
    
    # 根据模式生成各语言 README 的通用片段
    _run_hint_onedir = 'Run GameWikiAssistant/GameWikiAssistant.exe' if mode == 'onedir' else 'Double-click GameWikiAssistant.exe'
    _run_hint_onedir_ru = 'Запустите GameWikiAssistant/GameWikiAssistant.exe' if mode == 'onedir' else 'Дважды щёлкните GameWikiAssistant.exe'
    _run_hint_cn = '运行 GameWikiAssistant/GameWikiAssistant.exe' if mode == 'onedir' else '双击 GameWikiAssistant.exe'
    _temp_note_onedir = 'OneDir mode runs from the install folder and does not extract temp files.' if mode == 'onedir' else 'When the app exits abnormally, temp files may be left in the system temp folder:'
    _temp_note_onedir_ru = 'Режим OneDir запускается из папки установки и не создаёт временные файлы.' if mode == 'onedir' else 'При аварийном завершении программы во временной папке системы могут остаться файлы:'
    _temp_note_cn = '这主要是 onefile 模式的问题。OneDir 模式不会产生临时文件。' if mode == 'onedir' else '当程序异常退出或崩溃时，可能在系统临时目录留下临时文件：'
    _temp_list_onedir = '- OneDir mode runs from the install folder, no temp extraction.' if mode == 'onedir' else '''- Location: %TEMP%\\_MEI****** (e.g. AppData\\Local\\Temp\\_MEI260882\\)
- These folders can be safely deleted
- PyInstaller cleans them on normal exit
- You may delete them periodically to free space'''
    _temp_list_onedir_ru = '- Режим OneDir запускается из папки установки, без распаковки во временные каталоги.' if mode == 'onedir' else '''- Папка: %TEMP%\\_MEI****** (напр. AppData\\Local\\Temp\\_MEI260882\\)
- Эти папки можно безопасно удалить
- PyInstaller удаляет их при нормальном завершении
- Можно периодически удалять их для освобождения места'''
    _temp_list_cn = '- OneDir 模式直接从安装目录运行，不会解压临时文件' if mode == 'onedir' else '''- 位置：%TEMP%\\_MEI****** （如：AppData\\Local\\Temp\\_MEI260882\\）
- 这些文件夹可以安全删除，不会影响系统运行
- PyInstaller 在程序正常退出时会自动清理这些文件夹
- 您可以定期手动删除这些文件夹来释放磁盘空间'''

    readme_zh = f"""# GameWiki Assistant Portable ({mode.capitalize()} Mode)

## 使用说明

1. **首次使用必读**：本应用程序使用 WebView2 技术，需要 Microsoft Edge WebView2 Runtime 支持。
2. {_run_hint_cn} 启动程序。
3. 如果程序无法启动或显示白屏，请安装 WebView2 Runtime。
4. 首次运行需要配置 API 密钥（可选）。
5. 使用快捷键 Ctrl+Q 或设置新的快捷键来激活游戏助手功能。

## 卸载说明

**便携版卸载**：
1. 运行 Uninstall.exe 卸载程序
2. 程序会自动清理：
   - 用户数据文件夹 (%APPDATA%\\GameWikiTooltip)
   - 桌面和开始菜单快捷方式
   - 临时文件
   - 程序文件夹（可选）
3. 或者您可以直接删除整个便携版文件夹

## 系统要求

- Windows 10 或更高版本（推荐 Windows 11）
- 64位系统（推荐64位系统）
- Microsoft Edge WebView2 Runtime

## WebView2 Runtime 安装

### Windows 11 用户
✅ 您的系统已预装 WebView2 Runtime，可直接使用。

### Windows 10 用户  
⚠️ 需要安装 WebView2 Runtime：

**方法一（推荐）**：运行自动安装脚本
1. 进入 runtime 文件夹
2. 双击运行 install_webview2.bat
3. 按提示完成安装

**方法二**：手动下载安装
1. 访问：https://go.microsoft.com/fwlink/p/?LinkId=2124703
2. 下载并安装 WebView2 Runtime
3. 重启应用程序

## 注意事项

- 本程序为独立便携版，无需安装（WebView2 Runtime 除外）
- 配置文件将保存在系统 AppData 目录
- 完整 AI 功能需要配置 Gemini 和 Jina API 密钥
- WebView2 Runtime 首次安装需要下载约100MB，但只需安装一次

## 故障排除

### 问题：程序无法启动或显示白屏
**解决方案**：安装 WebView2 Runtime（参见上述安装说明）

### 问题：视频播放失败
**解决方案**：确认 WebView2 Runtime 已正确安装，重启程序

### 问题：临时文件堆积
**说明**：{_temp_note_cn}
{_temp_list_cn}

## 技术支持

如遇问题，请访问项目页面获取帮助。
"""

    readme_en = f"""# GameWiki Assistant Portable ({mode.capitalize()} Mode)

## Instructions

1. **First run**: This app uses WebView2 and requires Microsoft Edge WebView2 Runtime.
2. {_run_hint_onedir} to start the application.
3. If the app does not start or shows a white screen, install WebView2 Runtime.
4. On first run you may configure API keys (optional).
5. Use hotkey Ctrl+Q or set a custom hotkey to activate the game assistant.

## Uninstall

**Portable uninstall**:
1. Run Uninstall.exe
2. The uninstaller will remove:
   - User data folder (%APPDATA%\\GameWikiTooltip)
   - Desktop and Start menu shortcuts
   - Temporary files
   - Program folder (optional)
3. Or simply delete the entire portable folder.

## System requirements

- Windows 10 or later (Windows 11 recommended)
- 64-bit system
- Microsoft Edge WebView2 Runtime

## WebView2 Runtime installation

### Windows 11
✅ WebView2 Runtime is preinstalled; no action needed.

### Windows 10
⚠️ You need to install WebView2 Runtime:

**Option 1 (recommended)** – Run the installer script:
1. Open the runtime folder
2. Double-click install_webview2.bat
3. Follow the prompts

**Option 2** – Manual download:
1. Visit: https://go.microsoft.com/fwlink/p/?LinkId=2124703
2. Download and install WebView2 Runtime
3. Restart the application

## Notes

- This is a portable app; no installation required (except WebView2 Runtime).
- Config is stored in the system AppData folder.
- Full AI features require Gemini and Jina API keys.
- First-time WebView2 install is about 100 MB; one-time only.

## Troubleshooting

### App does not start or shows white screen
**Fix**: Install WebView2 Runtime (see above).

### Video playback fails
**Fix**: Ensure WebView2 Runtime is installed and restart the app.

### Temporary files left on disk
**Note**: {_temp_note_onedir}
{_temp_list_onedir}

## Support

For help, visit the project page.
"""

    readme_ru = f"""# GameWiki Assistant Portable (режим {mode.capitalize()})

## Инструкция

1. **Первый запуск**: приложение использует WebView2 и требует Microsoft Edge WebView2 Runtime.
2. {_run_hint_onedir_ru} для запуска.
3. Если приложение не запускается или показывает белый экран — установите WebView2 Runtime.
4. При первом запуске можно настроить API-ключи (по желанию).
5. Используйте горячую клавишу Ctrl+Q или задайте свою для вызова игрового ассистента.

## Удаление

**Портативное удаление**:
1. Запустите Uninstall.exe
2. Удалятся:
   - Папка данных (%APPDATA%\\GameWikiTooltip)
   - Ярлыки на рабочем столе и в меню «Пуск»
   - Временные файлы
   - Папка программы (по желанию)
3. Либо просто удалите всю портативную папку.

## Системные требования

- Windows 10 или новее (рекомендуется Windows 11)
- 64-разрядная система
- Microsoft Edge WebView2 Runtime

## Установка WebView2 Runtime

### Windows 11
✅ WebView2 Runtime уже установлен; ничего делать не нужно.

### Windows 10
⚠️ Нужно установить WebView2 Runtime:

**Вариант 1 (рекомендуется)** — запустите скрипт:
1. Откройте папку runtime
2. Дважды щёлкните install_webview2.bat
3. Следуйте подсказкам

**Вариант 2** — ручная загрузка:
1. Откройте: https://go.microsoft.com/fwlink/p/?LinkId=2124703
2. Скачайте и установите WebView2 Runtime
3. Перезапустите приложение

## Важно

- Портативное приложение; установка не требуется (кроме WebView2 Runtime).
- Настройки хранятся в папке AppData.
- Полные функции ИИ требуют API-ключей Gemini и Jina.
- Первая установка WebView2 — около 100 МБ; один раз.

## Решение проблем

### Приложение не запускается или белый экран
**Решение**: Установите WebView2 Runtime (см. выше).

### Не воспроизводится видео
**Решение**: Убедитесь, что WebView2 Runtime установлен, и перезапустите приложение.

### Остались временные файлы
**Примечание**: {_temp_note_onedir_ru}
{_temp_list_onedir_ru}

## Поддержка

Поддержка: страница проекта.
"""

    readme_files = [
        (portable_dir / "README.txt", readme_zh),
        (portable_dir / "README_en.txt", readme_en),
        (portable_dir / "README_ru.txt", readme_ru),
    ]
    try:
        for readme_path, content in readme_files:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✓ Created: {readme_path.name}")
    except Exception as e:
        print_error(f"Failed to create README: {e}")
        return False
    
    print_success(f"Portable package files added to: {portable_dir.absolute()}")
    return True

def create_webview2_runtime_installer(portable_dir):
    """Create WebView2 Runtime installer
    
    Args:
        portable_dir: Path to the portable directory (can be string or Path object)
    """
    print_status("Creating WebView2 Runtime installer...")
    
    # 确保 portable_dir 是 Path 对象
    portable_dir = Path(portable_dir)
    if not portable_dir.exists():
        print_error(f"Portable directory not found: {portable_dir}")
        return False
    
    # 创建 runtime 目录
    runtime_dir = portable_dir / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    
    # Download WebView2 Runtime Bootstrapper
    try:
        import urllib.request
        bootstrapper_url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
        bootstrapper_path = runtime_dir / "MicrosoftEdgeWebView2Setup.exe"
        
        print("  Downloading WebView2 Runtime Bootstrapper...")
        urllib.request.urlretrieve(bootstrapper_url, bootstrapper_path)
        print(f"  ✓ Downloaded to: {bootstrapper_path}")
        
        # Create installation script
        install_script = runtime_dir / "install_webview2.bat"
        script_content = """@echo off
echo Checking WebView2 Runtime...
reg query "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" >nul 2>&1
if %errorlevel% equ 0 (
    echo WebView2 Runtime is already installed, no need to install.
    pause
    exit /b 0
)

echo WebView2 Runtime is not installed, installing...
echo This may take a few minutes, please wait...
MicrosoftEdgeWebView2Setup.exe /silent /install
if %errorlevel% equ 0 (
    echo WebView2 Runtime installation completed!
) else (
    echo Installation failed, please manually run MicrosoftEdgeWebView2Setup.exe
)
pause
"""
        with open(install_script, 'w', encoding='gbk') as f:
            f.write(script_content)
        
        print_success("WebView2 Runtime installer created")
        return True
        
    except Exception as e:
        print_error(f"Failed to create WebView2 Runtime installer: {e}")
        return False

def create_inno_setup_script(mode='onedir'):
    """Create Inno Setup script for creating installer
    
    Args:
        mode: 'onedir' or 'onefile' - specifies which build to create installer for
    """
    print_status("Creating Inno Setup script...")
    
    # Determine source directory based on mode
    if mode == 'onedir':
        source_dir = f"GameWikiAssistant_Portable_{mode}\\GameWikiAssistant"
        files_section = f"""Source: "{source_dir}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs"""
    else:
        source_dir = f"GameWikiAssistant_Portable_{mode}"
        files_section = f"""Source: "{source_dir}\\GameWikiAssistant.exe"; DestDir: "{{app}}"; Flags: ignoreversion"""
    
    script_content = f"""#define MyAppName "GameWiki Assistant"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "GameWiki Team"
#define MyAppURL "https://github.com/yourusername/gamewiki"
#define MyAppExeName "GameWikiAssistant.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
AppId={{{{8F7A9E2C-4B3D-4E6A-9C1F-2A3B4C5D6E7F}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
; Remove the following line to run in administrative install mode
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=GameWikiAssistant_Setup_{mode}
SetupIconFile=src\\game_wiki_tooltip\\assets\\app.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Enable disk spanning for better performance with signed installers
DiskSpanning=yes
DiskSliceSize=max
; Uncomment the following lines if you have a code signing certificate
; SignTool=signtool
; SignedUninstaller=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{{cm:CreateQuickLaunchIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
{files_section}
; WebView2 Runtime installer
Source: "GameWikiAssistant_Portable_{mode}\\runtime\\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{{tmp}}"; Flags: deleteafterinstall

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{'GameWikiAssistant\\' if mode == 'onedir' else ''}}{{#MyAppExeName}}"
Name: "{{group}}\\{{cm:UninstallProgram,{{#MyAppName}}}}"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{'GameWikiAssistant\\' if mode == 'onedir' else ''}}{{#MyAppExeName}}"; Tasks: desktopicon
Name: "{{userappdata}}\\Microsoft\\Internet Explorer\\Quick Launch\\{{#MyAppName}}"; Filename: "{{app}}\\{{'GameWikiAssistant\\' if mode == 'onedir' else ''}}{{#MyAppExeName}}"; Tasks: quicklaunchicon

[Run]
; Check and install WebView2 Runtime if not present
Filename: "{{tmp}}\\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing WebView2 Runtime..."; Check: not IsWebView2RuntimeInstalled
Filename: "{{app}}\\{{'GameWikiAssistant\\' if mode == 'onedir' else ''}}{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: nowait postinstall skipifsilent

[Code]
function IsWebView2RuntimeInstalled: Boolean;
var
  ResultCode: Integer;
begin
  // Check if WebView2 Runtime is installed by looking for the registry key
  Result := RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}}');
  if not Result then
    Result := RegKeyExists(HKEY_CURRENT_USER, 'SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    // Delete old temporary files if they exist
    DelTree(ExpandConstant('{{localappdata}}\\Temp\\_MEI*'), False, True, False);
  end;
end;

[UninstallDelete]
; Clean up any remaining temporary files during uninstall
Type: filesandordirs; Name: "{{localappdata}}\\Temp\\_MEI*"
Type: filesandordirs; Name: "{{userappdata}}\\game_wiki_tooltip"
"""
    
    # Write the script file
    script_path = Path(f"GameWikiAssistant_{mode}.iss")
    try:
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        print_success(f"Inno Setup script created: {script_path}")
        print("\n💡 To create the installer:")
        print(f"   1. Install Inno Setup from https://jrsoftware.org/isdl.php")
        print(f"   2. Open {script_path} in Inno Setup Compiler")
        print(f"   3. Click 'Build' -> 'Compile' (or press F9)")
        print(f"   4. The installer will be created in the 'installer' directory")
        return True
    except Exception as e:
        print_error(f"Failed to create Inno Setup script: {e}")
        return False

def main():
    """Main function"""
    # Set console encoding to ensure Chinese characters are displayed correctly
    if sys.platform == "win32":
        import locale
        try:
            # Try to set console encoding to UTF-8
            os.system("chcp 65001 >nul 2>&1")
        except:
            pass
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GameWiki Assistant Packaging Tool')
    parser.add_argument('--mode', choices=['onedir', 'onefile'], default='onedir',
                        help='Packaging mode: onedir (folder, recommended, avoids missing DLL) or onefile (single exe)')
    parser.add_argument('--skip-deps', action='store_true',
                        help='Skip dependency installation')
    parser.add_argument('--create-installer', action='store_true',
                        help='Create Inno Setup script for installer')
    args = parser.parse_args()
    
    print("🚀 GameWiki Assistant Packaging Tool")
    print(f"📦 Mode: {args.mode}")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print_error("Python 3.8 or higher is required")
        return 1
    
    # Check if in project root directory
    if not os.path.exists("src/game_wiki_tooltip/qt_app.py"):
        print_error("Please run this script in the project root directory")
        return 1
    
    try:
        # Define build steps based on options
        steps = [
            ("Clean build", clean_build),
            ("Check resources", check_assets),
            ("Check AI modules", check_ai_modules),
            ("Check WebView2 WinRT requirements", check_webview2_requirements),
            ("Verify spec file", verify_spec_for_webview2),
        ]
        
        # Skip dependency installation if requested
        if not args.skip_deps:
            steps.insert(0, ("Install dependencies", install_dependencies))
        
        # Add build and packaging steps
        steps.extend([
            ("Build exe", lambda: build_exe(args.mode)),
            ("Build uninstaller", lambda: build_uninstaller(f"GameWikiAssistant_Portable_{args.mode}")),
            ("Add portable package files", lambda: create_portable_package(args.mode)),
            ("Create WebView2 Runtime installer", lambda: create_webview2_runtime_installer(f"GameWikiAssistant_Portable_{args.mode}")),
        ])
        
        # Add Inno Setup script creation if requested
        if args.create_installer:
            steps.append(("Create Inno Setup script", lambda: create_inno_setup_script(args.mode)))
        
        for step_name, step_func in steps:
            print(f"\n📋 Step: {step_name}")
            if not step_func():
                print_error(f"Step '{step_name}' failed")
                return 1
        
        print("\n" + "=" * 50)
        print_success("🎉 Packaging completed!")
        print("\n📦 Generated files:")
        portable_dir = f"GameWikiAssistant_Portable_{args.mode}"
        if args.mode == 'onedir':
            print(f"  - {portable_dir}/GameWikiAssistant/ (application directory)")
        else:
            print(f"  - {portable_dir}/GameWikiAssistant.exe (standalone exe file)")
        print(f"  - {portable_dir}/Uninstall.exe (uninstaller)")
        print(f"  - {portable_dir}/README.txt, README_en.txt, README_ru.txt (user guide)")
        print(f"  - {portable_dir}/runtime/ (WebView2 installer)")
        
        if args.create_installer:
            print(f"  - GameWikiAssistant_{args.mode}.iss (Inno Setup script)")
        
        print("\n💡 Tips:")
        print(f"  - {args.mode.capitalize()} mode: {'Fast startup, no temp files' if args.mode == 'onedir' else 'Slower startup, creates temp files'}")
        print(f"  - You can compress the {portable_dir} directory and distribute it to other users")
        if args.mode == 'onefile':
            print("  - If program crashes, temporary files may remain in %TEMP%\\\\_MEI****** folders")
            print("  - These temporary folders can be safely deleted to free up disk space")
        if args.create_installer:
            print("\n🔧 Next step: Use Inno Setup to compile the installer script")
        
        return 0
        
    except KeyboardInterrupt:
        print_error("User interrupted the build process")
        return 1
    except Exception as e:
        print_error(f"Unexpected error occurred during build: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code) 