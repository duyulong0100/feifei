#!/bin/zsh
set -e
echo "===== 飞飞转录 · 制作 DMG ====="

APP="dist/飞飞转录.app"
DMG_OUT="dist/飞飞转录.dmg"
STAGING="dist/dmg_staging"

if [[ ! -d "$APP" ]]; then
  echo "❌ 找不到 $APP，请先运行 build_mac.sh"; exit 1
fi

# ── 1. 移除本机 quarantine 标记 ────────────────────────────
echo "→ 清理 quarantine 标记…"
xattr -cr "$APP"

# ── 2. 准备 staging 目录 ───────────────────────────────────
rm -rf "$STAGING" "$DMG_OUT"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

cat > "$STAGING/安装说明.txt" << 'TXT'
安装：把「飞飞转录.app」拖入「Applications」文件夹。

首次打开提示"无法验证开发者"时：
  右键点击 .app → 选「打开」→ 弹窗里点「打开」
TXT

# ── 3. 从 staging 目录创建压缩只读 DMG ────────────────────
echo "→ 打包为 DMG…"
hdiutil create \
  -srcfolder "$STAGING" \
  -volname "飞飞转录" \
  -fs HFS+ \
  -format UDZO \
  -imagekey zlib-level=6 \
  -ov \
  "$DMG_OUT"

rm -rf "$STAGING"

SIZE=$(du -sh "$DMG_OUT" | awk '{print $1}')
echo ""
echo "✅ DMG 制作完成！"
echo "   文件：$(pwd)/$DMG_OUT"
echo "   大小：$SIZE"
echo ""
echo "   对方首次打开方法："
echo "   右键点击「飞飞转录.app」→ 打开 → 弹窗里点「打开」"
