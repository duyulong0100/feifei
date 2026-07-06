#!/bin/zsh
set -e
cd "$(dirname "$0")"   # 始终在 standalone/ 目录执行

echo "╔══════════════════════════════════════════════╗"
echo "║   飞飞转录 · 单机版 · macOS 打包             ║"
echo "║   内置 Whisper small 模型                    ║"
echo "╚══════════════════════════════════════════════╝"

# ── 1. 依赖检查 ──────────────────────────────────────────
echo "\n[1/5] 检查依赖…"
python3 -c "import PyInstaller" 2>/dev/null || pip3 install pyinstaller -q
python3 -c "import PyQt6, pyaudio, numpy, faster_whisper, ctranslate2" || {
    echo "❌ 缺少依赖，请先运行：pip3 install -r requirements.txt"
    exit 1
}
echo "     ✓ 依赖就绪"

# ── 2. 准备内置模型 ───────────────────────────────────────
echo "\n[2/5] 准备内置 Whisper small 模型…"
python3 prepare_model.py --size small
# 验证
[[ -f "bundled_model/model.bin" ]] || {
    echo "❌ bundled_model/model.bin 不存在，准备步骤失败"
    exit 1
}
echo "     ✓ 模型就绪"

# ── 3. 拷贝图标（从项目根目录共用）──────────────────────
echo "\n[3/5] 准备图标资源…"
ROOT_DIR="$(dirname "$(pwd)")"
for f in logo-app.png AppIcon.icns; do
    [[ -f "$ROOT_DIR/$f" ]] && cp "$ROOT_DIR/$f" . && echo "     拷贝 $f" || true
done
# logo-app.icns -> 如果有 AppIcon.icns 就复制为 logo-app.icns 供 spec 使用
[[ -f "AppIcon.icns" ]] && cp AppIcon.icns logo-app.icns && true

# ── 4. PyInstaller 打包 ───────────────────────────────────
echo "\n[4/5] 开始打包（含模型约 500 MB，需 5-15 分钟）…\n"
rm -rf build dist __pycache__
pyinstaller --noconfirm --clean 飞飞转录.spec

APP="dist/飞飞转录.app"
[[ -d "$APP" ]] || { echo "❌ 打包失败，找不到 $APP"; exit 1 }
echo "\n     ✓ .app 打包完成：$APP"

# ── 5. 制作 DMG ──────────────────────────────────────────
echo "\n[5/5] 制作 DMG…"
DMG_OUT="dist/飞飞转录单机版.dmg"
STAGING="dist/_dmg_staging"

xattr -cr "$APP"              # 清除 quarantine 属性
rm -rf "$STAGING" "$DMG_OUT"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

cat > "$STAGING/安装说明.txt" << 'TXT'
飞飞转录 · 单机版

安装：把「飞飞转录.app」拖入「Applications」文件夹。

✅ 单机版无需安装服务端，模型已内置。
   首次启动时会花约 5-15 秒加载模型，请耐心等待。

首次打开提示"无法验证开发者"时：
   右键点击 .app → 选「打开」→ 弹窗里点「打开」

如遇问题，日志位于：
   ~/Library/Logs/飞飞转录单机版/app.log
TXT

hdiutil create \
    -srcfolder "$STAGING" \
    -volname   "飞飞转录单机版" \
    -fs        HFS+ \
    -format    UDZO \
    -imagekey  zlib-level=6 \
    -ov        "$DMG_OUT"

rm -rf "$STAGING"

SIZE=$(du -sh "$DMG_OUT" | awk '{print $1}')
echo "\n╔══════════════════════════════════════════════╗"
echo "║   ✅  单机版打包完成！                       ║"
echo "╚══════════════════════════════════════════════╝"
echo "DMG：$(pwd)/$DMG_OUT  ($SIZE)"
echo ""
echo "安装方式："
echo "  1. 打开 DMG，把「飞飞转录.app」拖入「Applications」"
echo "  2. 直接打开，无需启动任何服务端"
echo ""
echo "注意：首次启动会加载 Whisper small 模型（约数秒）"
