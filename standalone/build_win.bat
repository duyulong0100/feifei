@echo off
chcp 65001 > nul
echo ╔═══════════════════════════════════════════════╗
echo ║  飞飞转录 · 单机版 · Windows 打包             ║
echo ║  内置 Whisper small 模型                      ║
echo ╚═══════════════════════════════════════════════╝

cd /d "%~dp0"

echo.
echo [1/5] 检查依赖...
python -c "import PyInstaller" 2>nul || pip install pyinstaller -q
python -c "import PyQt6, pyaudio, numpy, faster_whisper, ctranslate2" || (
    echo ❌ 缺少依赖，请先运行：pip install -r requirements.txt
    pause & exit /b 1
)
echo      ✓ 依赖就绪

echo.
echo [2/5] 准备内置 Whisper small 模型...
python prepare_model.py --size small --download
if not exist "bundled_model\model.bin" (
    echo ❌ bundled_model\model.bin 不存在
    pause & exit /b 1
)
echo      ✓ 模型就绪

echo.
echo [3/5] 清理旧产物...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo.
echo [4/5] 开始打包（含模型约 500 MB，需 5-15 分钟）...
pyinstaller --noconfirm --clean 飞飞转录.spec
if not exist "dist\飞飞转录" (
    echo ❌ 打包失败
    pause & exit /b 1
)
echo      ✓ exe 打包完成

echo.
echo [5/5] 制作安装包...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
    echo      使用 Inno Setup 制作安装程序...
    %ISCC% installer.iss
    if errorlevel 1 (
        echo ❌ Inno Setup 失败，改用 ZIP...
        goto :zip
    )
    echo      ✓ 安装包制作完成
    goto :done
)

:zip
echo      Inno Setup 未安装，改用 ZIP 打包...
powershell -Command ^
    "@'飞飞转录单机版 v1.0.0\n\n使用方法：\n  1. 解压本 ZIP 到任意目录\n  2. 运行飞飞转录.exe\n  3. 首次启动约需 5-15 秒加载模型\n'@ | Out-File -FilePath 'dist\飞飞转录\使用说明.txt' -Encoding UTF8; ^
    Compress-Archive -Path 'dist\飞飞转录\*' -DestinationPath 'dist\飞飞转录单机版.zip' -Force"
echo      ✓ ZIP 打包完成

:done
echo.
echo ╔═══════════════════════════════════════════════╗
echo ║   ✅  单机版打包完成！                        ║
echo ╚═══════════════════════════════════════════════╝
echo.
echo 输出目录：dist\
echo.
dir /b dist\
echo.
echo 安装：运行 dist\ 中的 Setup.exe 或解压 ZIP
echo.
pause
