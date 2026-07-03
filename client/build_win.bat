@echo off
chcp 65001 >nul
setlocal

echo ╔══════════════════════════════════════╗
echo ║   飞飞转录客户端 · Windows 打包       ║
echo ╚══════════════════════════════════════╝

:: ── 切换到 client 目录 ────────────────────────────────────
cd /d "%~dp0"

:: ── 检查 Python ───────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请安装 Python 3.10+ 并加入 PATH
    pause & exit /b 1
)

:: ── 安装依赖 ─────────────────────────────────────────────
echo.
echo → 检查 / 安装依赖...
pip install pyinstaller pyqt6 pyaudio requests numpy -q
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause & exit /b 1
)

:: ── 清理旧产物 ────────────────────────────────────────────
echo → 清理旧产物...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__

:: ── PyInstaller 打包 ──────────────────────────────────────
echo.
echo → 开始打包（约需 3-8 分钟）...
pyinstaller --noconfirm --clean 飞飞转录.spec
if errorlevel 1 (
    echo [错误] 打包失败，请查看上方日志
    pause & exit /b 1
)

:: ── 打 ZIP 安装包 ─────────────────────────────────────────
echo.
echo → 制作 ZIP 安装包...
set "APP_DIR=dist\飞飞转录"
set "ZIP_OUT=dist\飞飞转录_Windows.zip"

if not exist "%APP_DIR%" (
    echo [错误] 找不到 %APP_DIR%
    pause & exit /b 1
)

:: 写安装说明
(
echo 飞飞转录客户端 · Windows 版
echo.
echo 使用方法：
echo   1. 解压本 ZIP 到任意目录
echo   2. 先在服务器端启动服务端：
echo         python server/run.py
echo   3. 运行「飞飞转录.exe」
echo   4. 首次打开在「⚙ 服务器设置」填入服务端地址
echo.
echo 注：客户端本身不含语音模型，模型运行在服务端。
) > "%APP_DIR%\使用说明.txt"

:: 用 PowerShell 压缩（Windows 10+ 内置）
powershell -NoProfile -Command ^
    "Compress-Archive -Path '%APP_DIR%\*' -DestinationPath '%ZIP_OUT%' -Force"

if errorlevel 1 (
    echo [警告] ZIP 制作失败，但 exe 文件夹已生成：%APP_DIR%
) else (
    echo.
    echo ╔══════════════════════════════════════╗
    echo ║   ✅  打包完成！                       ║
    echo ╚══════════════════════════════════════╝
    echo 安装包：%~dp0%ZIP_OUT%
    echo exe目录：%~dp0%APP_DIR%
)

pause
