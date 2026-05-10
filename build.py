"""
Build Script - Đóng gói AIVideoCreator thành file .exe
Sử dụng PyInstaller để tạo thư mục chứa .exe hoạt động được.
"""

import os
import sys
import subprocess
import shutil


def build():
    """Chạy PyInstaller để đóng gói ứng dụng."""

    print("=" * 60)
    print("  🔨 AIVideoCreator - Build Script")
    print("=" * 60)

    # Kiểm tra PyInstaller
    try:
        import PyInstaller
        print(f"✅ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("📦 Đang cài đặt PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Đường dẫn gốc
    base_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(base_dir, "main_ui.py")

    if not os.path.exists(main_script):
        print(f"❌ Không tìm thấy {main_script}")
        return

    # Tìm đường dẫn Playwright browsers
    playwright_path = _find_playwright_browsers()

    # Chuẩn bị tham số PyInstaller
    pyinstaller_args = [
        main_script,
        "--name=AIVideoCreator",
        "--windowed",                    # Không hiện console
        "--noconfirm",                   # Tự động ghi đè
        f"--distpath={os.path.join(base_dir, 'dist')}",
        f"--workpath={os.path.join(base_dir, 'build_temp')}",
        f"--specpath={base_dir}",

        # Thêm các module cần thiết
        "--hidden-import=module_video_agent",
        "--hidden-import=module_audio_agent",
        "--hidden-import=video_assembler",
        "--hidden-import=ollama",
        "--hidden-import=pydantic",
        "--hidden-import=moviepy",
        "--hidden-import=PIL",
        "--hidden-import=requests",
        "--hidden-import=playwright",
        "--hidden-import=playwright.sync_api",

        # PyQt5
        "--hidden-import=PyQt5",
        "--hidden-import=PyQt5.QtWidgets",
        "--hidden-import=PyQt5.QtCore",
        "--hidden-import=PyQt5.QtGui",

        # Thêm data files
        "--add-data", f"{os.path.join(base_dir, 'module_video_agent.py')};.",
        "--add-data", f"{os.path.join(base_dir, 'module_audio_agent.py')};.",
        "--add-data", f"{os.path.join(base_dir, 'video_assembler.py')};.",
    ]

    # Thêm Playwright browsers nếu tìm thấy
    if playwright_path and os.path.exists(playwright_path):
        pyinstaller_args.extend([
            "--add-data", f"{playwright_path};playwright/driver/package/.local-browsers"
        ])
        print(f"📁 Playwright browsers: {playwright_path}")
    else:
        print("⚠️ Không tìm thấy Playwright browsers. User sẽ cần chạy 'playwright install' riêng.")

    # Thêm tts_engine nếu tồn tại
    tts_engine_dir = os.path.join(base_dir, "tts_engine")
    if os.path.exists(tts_engine_dir):
        pyinstaller_args.extend([
            "--add-data", f"{tts_engine_dir};tts_engine"
        ])
        print(f"📁 TTS Engine: {tts_engine_dir}")

    # Chạy PyInstaller
    print("\n🔨 Đang build...")
    print(f"   Command: pyinstaller {' '.join(pyinstaller_args[:5])}...")

    try:
        subprocess.check_call([sys.executable, "-m", "PyInstaller"] + pyinstaller_args)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build thất bại: {e}")
        print("\n💡 Thử lại với --onedir (thay vì --onefile):")
        # Retry không có --onefile
        subprocess.check_call([sys.executable, "-m", "PyInstaller"] + pyinstaller_args)
        return

    # Dọn dẹp build temp
    build_temp = os.path.join(base_dir, "build_temp")
    if os.path.exists(build_temp):
        shutil.rmtree(build_temp, ignore_errors=True)

    # Kết quả
    dist_dir = os.path.join(base_dir, "dist", "AIVideoCreator")
    exe_path = os.path.join(dist_dir, "AIVideoCreator.exe")

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print("\n" + "=" * 60)
        print("  ✅ BUILD THÀNH CÔNG!")
        print("=" * 60)
        print(f"  📁 Thư mục: {dist_dir}")
        print(f"  📦 File:    {exe_path}")
        print(f"  💾 Kích thước EXE: {size_mb:.1f} MB")
        print()
        print("  📋 Hướng dẫn sử dụng:")
        print("  1. Copy toàn bộ thư mục 'AIVideoCreator' trong dist/")
        print("  2. Đảm bảo Ollama đang chạy trên máy đích")
        print("  3. Chạy AIVideoCreator.exe")
        print()
        print("  ⚠️ Lưu ý:")
        print("  - Cần Ollama cài sẵn và đang chạy (ollama serve)")
        print("  - Lần đầu chạy sẽ tự động tải model VieNeu-TTS")
        print("  - Playwright browsers sẽ cần cài nếu chưa có")
    else:
        print(f"\n❌ Không tìm thấy file exe tại {exe_path}")
        print("   Kiểm tra thư mục dist/ để xem kết quả build.")


def _find_playwright_browsers() -> str:
    """Tìm thư mục browsers của Playwright."""
    possible_paths = [
        os.path.expanduser("~/.cache/ms-playwright"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright"),
        os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "ms-playwright"),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return ""


# ──────────────────────────────────────
# Tạo file .bat tiện lợi để chạy
# ──────────────────────────────────────
def create_run_script():
    """Tạo file run.bat để chạy nhanh từ source code."""
    bat_content = """@echo off
echo ============================================
echo   AI Video Creator - Launcher
echo ============================================
echo.

REM Kiểm tra .venv
if exist ".venv\\Scripts\\python.exe" (
    echo [OK] Virtual environment found
    .venv\\Scripts\\python.exe main_ui.py
) else (
    echo [!] Virtual environment not found, using system Python
    python main_ui.py
)

pause
"""
    with open("run.bat", "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("✅ Đã tạo run.bat")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AIVideoCreator Build Script")
    parser.add_argument("--run-script", action="store_true", help="Tạo file run.bat")
    args = parser.parse_args()

    if args.run_script:
        create_run_script()
    else:
        build()
