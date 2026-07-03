#!/bin/zsh
set -e
echo "===== 飞飞转录 · Mac 打包 ====="

# 安装打包工具
pip3 install pyinstaller -q

# 清理上次产物
rm -rf build dist

echo "→ 开始打包（内含 small 模型，不含 medium，约需 2-5 分钟）…"

# 使用 spec 文件打包（保留 info_plist / bundle_identifier 等设置）
pyinstaller --noconfirm --clean 飞飞转录.spec

echo ""
echo "✅ 打包完成！"
echo "   产物：$(pwd)/dist/飞飞转录.app"
echo "   注：.app 内已内置 small 模型（不含 medium），其他模型可在设置里下载"
echo "   其他模型会下载到：~/Library/Application Support/飞飞转录/whisper_models/"
echo "   日志文件：~/Library/Logs/飞飞转录/app.log"
