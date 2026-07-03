#!/bin/zsh
echo "===== Mac Faster-Whisper桌面版依赖安装 ====="
brew install portaudio ffmpeg
python3 -m pip install --upgrade pip
pip3 install faster-whisper pyaudio numpy pyqt6
echo "安装完毕，运行 python3 main_gui.py 启动软件"
