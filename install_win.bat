@echo off
chcp 65001
echo ===== Faster-Whisper桌面版依赖一键安装 =====
python -m pip install --upgrade pip
pip install faster-whisper pyaudio numpy pyqt6 ffmpeg-downloader
ffdl install --add-path
echo.
echo 依赖安装完成！运行 main_gui.py 启动软件，或执行 build_win.bat 打包成桌面程序
pause

