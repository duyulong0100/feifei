#!/bin/zsh
set -e
cd "$(dirname "$0")"   # 始终在 client/ 目录执行

echo "╔══════════════════════════════════════╗"
echo "║   飞飞转录客户端 · macOS 打包         ║"
echo "╚══════════════════════════════════════╝"

# ── 依赖检查 ─────────────────────────────────────────────────
echo "\n→ 检查依赖…"
python3 -c "import PyInstaller" 2>/dev/null || pip3 install pyinstaller -q
python3 -c "import PyQt6, pyaudio, requests, numpy" || {
    echo "❌ 缺少依赖，请先运行：pip3 install -r requirements.txt"
    exit 1
}

# ── 清理旧产物 ────────────────────────────────────────────────
echo "→ 清理上次产物…"
rm -rf build dist __pycache__

# ── PyInstaller 打包 ──────────────────────────────────────────
echo "→ 开始打包（约需 2-5 分钟）…\n"
pyinstaller --noconfirm --clean 飞飞转录.spec

APP="dist/飞飞转录.app"
[[ -d "$APP" ]] || { echo "❌ 打包失败，找不到 $APP"; exit 1 }
echo "\n✅ .app 打包完成：$APP"

# ── 制作 DMG ─────────────────────────────────────────────────
echo "\n→ 制作 DMG…"
DMG_OUT="dist/飞飞转录.dmg"
STAGING="dist/_dmg_staging"

xattr -cr "$APP"                          # 清除 quarantine
rm -rf "$STAGING" "$DMG_OUT"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

cat > "$STAGING/安装说明.txt" << 'TXT'
安装：把「飞飞转录.app」拖入「Applications」文件夹。

⚙  首次打开前：先启动服务端
   cd speech-to-text
   python3 server/run.py

首次打开提示"无法验证开发者"时：
   右键点击 .app → 选「打开」→ 弹窗里点「打开」
TXT

hdiutil create \
    -srcfolder "$STAGING" \
    -volname   "飞飞转录" \
    -fs        HFS+ \
    -format    UDZO \
    -imagekey  zlib-level=6 \
    -ov        "$DMG_OUT"

rm -rf "$STAGING"

SIZE=$(du -sh "$DMG_OUT" | awk '{print $1}')
echo "\n╔══════════════════════════════════════╗"
echo "║   ✅  打包完成！                       ║"
echo "╚══════════════════════════════════════╝"
echo "DMG：$(pwd)/$DMG_OUT  ($SIZE)"
echo ""
echo "安装方式："
echo "  1. 打开 DMG，把「飞飞转录.app」拖入「Applications」"
echo "  2. 启动服务端后再打开客户端"
