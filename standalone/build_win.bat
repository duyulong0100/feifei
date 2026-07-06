@echo off
chcp 65001 > nul
echo ╔═══════════════════════════════════════════════╗
echo ║  飞飞转录 · 单机版 · Windows 打包             ║
echo ║  内置 Whisper small 模型                      ║
echo ╚═══════════════════════════════════════════════╝

cd /d "%~dp0"

echo.
echo [1/4] 检查依赖...
python -c "import PyInstaller" 2>nul || pip install pyinstaller -q
python -c "import PyQt6, pyaudio, numpy, faster_whisper, ctranslate2" || (
    echo ❌ 缺少依赖，请先运行：pip install -r requirements.txt
    pause & exit /b 1
)
echo      ✓ 依赖就绪

echo.
echo [2/4] 准备内置 Whisper small 模型...
python prepare_model.py --size small
if not exist "bundled_model\model.bin" (
    echo ❌ bundled_model\model.bin 不存在
    pause & exit /b 1
)
echo      ✓ 模型就绪

echo.
echo [3/4] 清理旧产物...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo.
echo [4/4] 开始打包（含模型约 500 MB，需 5-15 分钟）...
pyinstaller --noconfirm --clean 飞飞转录.spec

if not exist "dist\飞飞转录" (
    echo ❌ 打包失败
    pause & exit /b 1
)

echo.
echo ╔═══════════════════════════════════════════════╗
echo ║   ✅  单机版打包完成！                        ║
echo ╚═══════════════════════════════════════════════╝
echo.
echo 输出目录：dist\飞飞转录\
echo 直接运行 dist\飞飞转录\飞飞转录.exe 即可使用
echo 无需安装任何服务端
echo.
pause
