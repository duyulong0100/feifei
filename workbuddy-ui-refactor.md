# 飞飞转录 · WorkBuddy 风格 UI 重构方案

> 基于对 `/Applications/WorkBuddy.app` 的 CSS 设计系统完整提取，指导 `main_gui.py` 的界面重构。

---

## 一、WorkBuddy 设计系统

### 1.1 色彩 Token（完整提取自 `index-9X2LkU-w.css`）

#### 深色主题 `[data-theme=dark]`（默认）

| Token | 值 | 用途 |
|-------|----|------|
| `--color-bg-primary` | `#000000` | 最外层主背景 |
| `--color-bg-secondary` | `#1c1c1e` | 侧边栏、次级面板 |
| `--color-bg-tertiary` | `#242424` | 三级背景 |
| `--color-bg-card` | `#1a1a1a` | 卡片背景 |
| `--color-bg-hover` | `#2a2a2a` | 悬停态 |
| `--color-bg-input` | `#1a1a1a` | 输入框背景 |
| `--color-bg-code` | `#161616` | 代码块 |
| `--color-border-default` | `#2e2e33` | 通用边框 |
| `--color-border-muted` | `#232328` | 次级边框 |
| `--color-border-input` | `#252525` | 输入框边框 |
| `--color-text-primary` | `#e5e5e5` | 主文字 |
| `--color-text-secondary` | `#a3a3a3` | 次要文字 |
| `--color-text-tertiary` | `#7c7c82` | 提示/占位文字 |
| `--color-accent-blue` | `#60a5fa` | 蓝色强调（主 CTA） |
| `--color-accent-green` | `#4ade80` | 成功/录音中 |
| `--color-accent-red` | `#f87171` | 危险/停止 |
| `--color-accent-yellow` | `#fbbf24` | 警告 |
| `--color-accent-purple` | `#8b7dff` | AI/识别中 |
| `--color-accent-brand` | `#e5e5e5` | 品牌强调色（深色下即主文字色） |
| `--color-focus-ring` | `#60a5fa` | 焦点环 |
| `--color-disabled-text` | `#555558` | 禁用文字 |
| `--color-disabled-bg` | `#1e1e20` | 禁用背景 |
| `--color-success-bg` | `rgba(74,222,128,.1)` | 成功态背景 |
| `--color-error-bg` | `rgba(248,113,113,.1)` | 错误态背景 |
| `--color-info-bg` | `rgba(96,165,250,.1)` | 信息态背景 |

#### 浅色主题 `[data-theme=light]`（备用）

| Token | 值 |
|-------|----|
| `--color-bg-primary` | `#fefefe` |
| `--color-bg-secondary` | `#f5f5f7` |
| `--color-bg-card` | `#ffffff` |
| `--color-bg-hover` | `#f5f5f5` |
| `--color-border-default` | `#dcdee3` |
| `--color-text-primary` | `#1a1a1a` |
| `--color-text-secondary` | `#5c5c5c` |
| `--color-text-tertiary` | `#8e8e93` |
| `--color-accent-blue` | `#1677ff` |
| `--color-accent-green` | `#22c55e` |
| `--color-accent-red` | `#ff4d4f` |
| `--color-accent-purple` | `#6c4dff` |

---

### 1.2 字体规范

| 场景 | 字体 | 大小 | 字重 |
|------|------|------|------|
| 品牌名 / 侧边栏标题 | `Poppins, sans-serif` | 16px | 600 |
| 区段标题（section title） | 系统字体 | 11px | 600，全大写，letter-spacing 0.06em |
| 正文 / 导航项 | `-apple-system, PingFang SC, ...` | 13px | 400 / 500 |
| 转录文本 | 同上 | 15px | 400 |
| 副标题 / 提示 | 同上 | 12px | 400，色 text-tertiary |

**完整系统字体栈：**
```
-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
"Helvetica Neue", Arial, sans-serif
```

---

### 1.3 圆角规范

| 级别 | 值 | 适用 |
|------|----|------|
| 卡片 | `12px` | 设置卡片、转录区 |
| 按钮 | `8px` | 普通按钮 |
| 导航项 | `8px` | sidebar nav-item |
| 头像 / 图标 | `50%` / `6px` | 圆形头像、图标容器 |
| 输入框 | `8px` | 文本输入 |

---

### 1.4 间距规范

```
侧边栏宽度:     220px（固定）
侧边栏内边距:   12px（左右）
头部内边距:     16px 20px
卡片内边距:     4px 0（外）→ 16px 20px（内行）
导航项高度:     36px，内边距 8px 12px
区段标题间距:   12px 12px 4px（top right bottom）
内容区内边距:   16px 20px
```

---

### 1.5 关键组件样式

#### 侧边栏品牌头部
```css
.sidebar-header { padding: 16px 20px; gap: 10px; }
.sidebar-logo   { width: 28px; height: 28px; border-radius: 6px; }
.sidebar-brand  { font-family: Poppins; font-weight: 600; font-size: 16px; }
```

#### 侧边栏导航项
```css
.sidebar-nav-item {
  height: 36px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  color: text-secondary;
  transition: background 0.15s;
}
.sidebar-nav-item:hover  { background: bg-hover; color: text-primary; }
.sidebar-nav-item.active { background: bg-primary; color: text-primary; font-weight: 500; }
```

#### 区段标题
```css
.sidebar-section-title {
  font-size: 11px; font-weight: 600;
  color: text-tertiary;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 12px 12px 4px;
}
```

#### 设置卡片
```css
.settings-card {
  background: bg-card;
  border: 1px solid border-default;
  border-radius: 12px;
  padding: 4px 0;
  overflow: hidden;
}
```

---

## 二、重构布局方案

### 2.1 整体结构

```
QMainWindow  (bg: #000000)
├── QMenuBar  (bg: #1c1c1e, border-bottom: #2e2e33)
└── central widget  (QHBoxLayout, spacing: 0)
    ├── Sidebar  (fixed 220px, bg: #1c1c1e)
    │   ├── Header (logo + 品牌名)
    │   ├── Nav Section "录音"
    │   │   └── [● 开始录音]  ←  主 CTA，宽按钮
    │   ├── Section Divider
    │   ├── Section Title "模型"
    │   │   └── 5 个 pill 按钮（tiny/base/small/medium/large）
    │   ├── Section Title "质量"
    │   │   └── 3 个 pill（速度/均衡/质量）
    │   ├── Section Title "录音模式"
    │   │   └── 2 个 pill（录完整转/边录边转）
    │   └── Footer (状态指示)
    └── MainArea  (flex: 1, bg: #000000)
        ├── TopBar  (height: 48px, border-bottom: #2e2e33)
        │   ├── Title "转录结果"
        │   └── Action buttons [清空] [📋 复制] [🎬 文件]
        ├── Transcript Card  (bg: #1a1a1a, border-radius: 12px, flex: 1)
        │   └── QTextEdit (bg: transparent)
        └── StatusBar  (bg: #1c1c1e, border-top: #2e2e33)
```

### 2.2 侧边栏细节

```
┌────────────────────┐
│  🐦  飞飞转录       │  ← Poppins 600 16px
├────────────────────┤
│  ● 开始录音识别    │  ← 主 CTA，accent-blue 背景，高度 40px
├────────────────────┤
│  MODELS            │  ← 区段标题 11px uppercase
│  [tiny][base][✓small][medium][large]
├────────────────────┤
│  QUALITY           │
│  [⚡速度][⚖均衡✓][🎯质量]
├────────────────────┤
│  MODE              │
│  [📼录完整转✓][⚡边录边转]
├────────────────────┤  ← 底部分割线
│  ✅ 模型已就绪      │  ← text-tertiary 12px
└────────────────────┘
```

### 2.3 主内容区细节

```
┌──────────────────────────────────────────┐
│  转录结果          [清空] [📋 复制] [🎬] │  ← 48px top bar
├──────────────────────────────────────────┤
│                                          │
│   ░░░░░░░░░░░ 转录文本 ░░░░░░░░░░░       │
│   （深色卡片，border-radius: 12px）       │
│   文字颜色 #e5e5e5，15px，160% 行高      │
│                                          │
│   段落标签用 text-tertiary 11px          │
│                                          │
└──────────────────────────────────────────┘
│  模型：small ✓  ·  质量：⚖ 均衡  ·  就绪 │  ← 状态栏 12px
└──────────────────────────────────────────┘
```

---

## 三、PyQt6 样式表（STYLE 常量）

```python
STYLE = """
/* ── 全局 ─────────────────────────────────── */
* {
    font-family: -apple-system, "PingFang SC", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #e5e5e5;
    outline: none;
}
QMainWindow, QDialog { background: #000000; }

/* ── 菜单栏 ──────────────────────────────── */
QMenuBar {
    background: #1c1c1e;
    border-bottom: 1px solid #2e2e33;
    padding: 2px 4px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 6px; color: #a3a3a3; }
QMenuBar::item:selected { background: #2a2a2a; color: #e5e5e5; }
QMenu {
    background: #1a1a1a;
    border: 1px solid #2e2e33;
    border-radius: 10px;
    padding: 4px;
}
QMenu::item { padding: 7px 20px; border-radius: 6px; color: #e5e5e5; }
QMenu::item:selected { background: #2a2a2a; }
QMenu::separator { height: 1px; background: #2e2e33; margin: 4px 8px; }

/* ── 侧边栏 ──────────────────────────────── */
#sidebar {
    background: #1c1c1e;
    border-right: 1px solid #2e2e33;
    min-width: 220px; max-width: 220px;
}
#sidebarBrand {
    font-family: "Poppins", -apple-system, sans-serif;
    font-size: 16px; font-weight: 600;
    color: #e5e5e5;
}
#sectionTitle {
    font-size: 11px; font-weight: 600;
    color: #7c7c82;
    letter-spacing: 0.06em;
}

/* ── 侧边栏 Pill 按钮 ────────────────────── */
#pillBtn {
    background: transparent;
    border: 1px solid #2e2e33;
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 12px;
    color: #7c7c82;
}
#pillBtn:checked {
    background: rgba(96,165,250,0.15);
    border-color: #60a5fa;
    color: #60a5fa;
    font-weight: 600;
}
#pillBtn:hover:!checked { border-color: #3f3f46; color: #a3a3a3; }

/* ── 主 CTA：录音按钮 ─────────────────────── */
#btnRecord {
    background: #60a5fa;
    color: #000000;
    border: none;
    border-radius: 10px;
    padding: 10px 0;
    font-size: 14px; font-weight: 600;
}
#btnRecord:hover { background: #93c5fd; }
#btnRecording {
    background: rgba(248,113,113,0.15);
    color: #f87171;
    border: 1px solid #f87171;
    border-radius: 10px;
    padding: 10px 0;
    font-size: 14px; font-weight: 600;
}

/* ── 主内容区 ─────────────────────────────── */
#mainArea { background: #000000; }
#topBar {
    background: #000000;
    border-bottom: 1px solid #2e2e33;
}
#topBarTitle { font-size: 14px; font-weight: 600; color: #e5e5e5; }

/* ── 转录卡片 ─────────────────────────────── */
#transcriptCard {
    background: #1a1a1a;
    border: 1px solid #2e2e33;
    border-radius: 12px;
}
#transcript {
    background: transparent;
    border: none;
    color: #e5e5e5;
    selection-background-color: rgba(96,165,250,0.25);
}

/* ── 操作按钮（次要）─────────────────────── */
#btnAction {
    background: #1a1a1a;
    color: #a3a3a3;
    border: 1px solid #2e2e33;
    border-radius: 8px;
    padding: 5px 14px;
    font-size: 12px;
}
#btnAction:hover { background: #2a2a2a; color: #e5e5e5; border-color: #3f3f46; }
#btnAction:disabled { color: #555558; border-color: #1e1e20; }

/* ── 状态栏 ──────────────────────────────── */
QStatusBar {
    background: #1c1c1e;
    border-top: 1px solid #2e2e33;
    font-size: 12px;
    color: #7c7c82;
}

/* ── 滚动条 ──────────────────────────────── */
QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 2px; }
QScrollBar::handle:vertical {
    background: rgba(255,255,255,0.12);
    border-radius: 3px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.2); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── 对话框 ──────────────────────────────── */
QDialog { background: #000000; }
#dialogCard {
    background: #1a1a1a;
    border: 1px solid #2e2e33;
    border-radius: 12px;
}
#statusOk    { color: #4ade80; font-size: 12px; }
#statusError { color: #f87171; font-size: 12px; }
#statusWarn  { color: #fbbf24; font-size: 12px; }

/* ── 分割线 ──────────────────────────────── */
#divider { background: #2e2e33; max-height: 1px; min-height: 1px; }
"""
```

---

## 四、`_build_ui` 重构要点

### 4.1 侧边栏构建顺序

```python
def _build_sidebar(self):
    sidebar = QWidget(); sidebar.setObjectName("sidebar")
    layout = QVBoxLayout(sidebar)
    layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

    # 1. Header: 图标 + Poppins 品牌名
    # 2. 主录音 CTA 按钮（全宽）
    # 3. 水平分割线
    # 4. section_title("MODELS") + 模型 pill 按钮组
    # 5. section_title("QUALITY") + 质量 pill 按钮组
    # 6. section_title("MODE") + 模式 pill 按钮组
    # 7. layout.addStretch()
    # 8. Footer：状态文字
    return sidebar
```

### 4.2 主内容区构建顺序

```python
def _build_main(self):
    # 1. topBar（HBoxLayout）: title + [清空][复制][文件] 按钮
    # 2. transcriptCard（QFrame）: 内含 QTextEdit #transcript
    # 3. 状态栏由 QStatusBar 承载（已在 MainWin 级别）
```

### 4.3 设置对话框（SettingsDialog）适配

- 背景改为 `#000000`
- 模型/质量卡片用 `#dialogCard`（`#1a1a1a` + border `#2e2e33` + border-radius `12px`）
- Section label 用 `#sectionTitle` 样式
- 按钮用 `#btnAction`
- "完成"按钮用 `#btnRecord` 样式

---

## 五、文字格式函数调整

转录段落标签颜色由原来的 `#B0B0B8` 调整为 WorkBuddy 的 `#7c7c82`（text-tertiary）：

```python
def _fmt_label():
    f = QTextCharFormat()
    f.setForeground(QColor("#7c7c82"))   # WorkBuddy text-tertiary
    f.setFontPointSize(11)
    return f

def _fmt_body():
    f = QTextCharFormat()
    f.setForeground(QColor("#e5e5e5"))   # WorkBuddy text-primary
    f.setFontPointSize(15)
    return f
```

---

## 六、实施步骤

1. **替换 `STYLE` 常量** → 使用上方完整样式表
2. **重构 `_build_ui`** → 拆分为 `_build_sidebar()` + `_build_main_area()`，用 `QHBoxLayout` 拼合
3. **侧边栏内联 model/quality/mode 选择器**，移除菜单栏的设置入口（保留文件菜单）
4. **SettingsDialog 样式更新** → 只保留「下载模型 / 本地导入」等高级选项
5. **颜色 token 变量化** → 在 Python 里定义 `COLORS` 字典，方便后续切换深/浅色

```python
COLORS = {
    "bg_primary":       "#000000",
    "bg_secondary":     "#1c1c1e",
    "bg_card":          "#1a1a1a",
    "bg_hover":         "#2a2a2a",
    "border_default":   "#2e2e33",
    "text_primary":     "#e5e5e5",
    "text_secondary":   "#a3a3a3",
    "text_tertiary":    "#7c7c82",
    "accent_blue":      "#60a5fa",
    "accent_green":     "#4ade80",
    "accent_red":       "#f87171",
    "accent_yellow":    "#fbbf24",
    "accent_purple":    "#8b7dff",
}
```

6. **打包测试** → `bash build_mac.sh && bash make_dmg.sh`

---

## 七、参考来源

- 设计 Token 提取自：`/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/dist/web-ui/assets/index-9X2LkU-w.css`
- HTML 入口：`/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/dist/web-ui/index.html`
- WorkBuddy 使用 Tailwind CSS + 自定义 CSS 变量体系，深色主题通过 `[data-theme=dark]` 切换
