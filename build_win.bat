@echo off
chcp 65001
echo ===== 打包Windows桌面程序 =====
pip install pyinstaller
pyinstaller -F -w -n "Whisper离线语音工具" main_gui.py
echo 打包完成！exe文件在 dist 文件夹内
pause

