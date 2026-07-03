# 🐦 飞飞转录

本地离线语音转文字桌面工具，基于 [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) 驱动，支持麦克风录音实时转录与音视频文件字幕生成。语音数据**全程本地处理，不上传，不联网**。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| 🎙 麦克风录音转录 | 边录边转（实时分段）或录完整转（准确率更高） |
| 🎬 音视频文件字幕 | 导入 mp3/wav/m4a/mp4/mov 等，自动生成 `.srt` 字幕文件 |
| 📋 一键复制 | 转录结果直接复制到剪贴板 |
| 🔒 完全离线 | 模型本地运行，无需联网，语音数据不离开本机 |
| ⚙️ 多模型 / 多质量 | 可在设置里切换 tiny → large-v3，以及速度 / 均衡 / 质量三档 |

---

## 系统要求

- macOS 13（Ventura）及以上
- 芯片：Apple Silicon（M1/M2/M3/M4）或 Intel（需开启 Rosetta）
- 内存：4 GB 以上（small 模型约占 500 MB）
- 磁盘：安装包约 550 MB

---

## 安装

### 方式一：DMG 安装包（推荐）

1. 双击打开 `飞飞转录.dmg`
2. 将 `飞飞转录.app` 拖入右侧 **Applications** 文件夹

   ![安装示意](https://i.imgur.com/placeholder.png)

3. 首次打开时 macOS 会提示 **"无法验证开发者"**（因为没有 Apple 付费签名证书），按以下步骤绕过：
   - **右键**点击 `飞飞转录.app` → 选 **「打开」**
   - 弹窗中点 **「打开」**
   - 之后正常双击即可，只需操作一次

4. 首次录音时 macOS 会弹出**麦克风权限授权**，点「允许」

> 如果没有弹出授权框，或转录结果为空，手动前往：
> **系统设置 → 隐私与安全性 → 麦克风** → 找到「飞飞转录」并开启

---

## 使用说明

### 麦克风录音转录

1. 打开软件，点击 **「🎙 开始录音识别」**（按钮变红）
2. 对着麦克风说话
3. 点击 **「⏹ 停止录音」**，稍等片刻后转录文字出现在文本区
4. 点击 **「📋 复制」** 一键复制全部内容

### 导入音视频文件转字幕

1. 点击 **「🎬 导入音视频」**，选择文件（支持 mp3 / wav / m4a / mp4 / mov / flv / aac / ogg）
2. 等待识别完成（时长越长等待越久）
3. 字幕文件（`.srt`）自动保存在与原文件相同的目录下，文本区也会显示保存路径

---

## 设置说明

点击右上角 **「⚙ 设置」** 打开偏好设置：

### 模型

| 模型 | 大小 | 适用场景 |
|------|------|----------|
| tiny | 75 MB | 极低配设备，准确率较低 |
| base | 145 MB | 低配设备，日常速记 |
| **small（默认内置）** | **483 MB** | **推荐：平衡速度与准确率** |
| medium | 1.5 GB | 高准确率，需另行下载 |
| large-v3 | 3.1 GB | 最高准确率，速度较慢 |

- 内置 `small` 模型，无需联网可直接使用
- 其他模型点击 **「☁ 下载」** 后写入 `~/Library/Application Support/飞飞转录/whisper_models/`
- 也可点击 **「📂 本地导入」** 使用已有的模型文件夹

### 识别质量

| 档位 | 参数 | 说明 |
|------|------|------|
| ⚡ 速度 | int8 · beam 3 | 最快，适合实时录音 |
| ⚖ 均衡（默认） | int8_float32 · beam 5 | 速度与准确率均衡 |
| 🎯 质量 | float32 · beam 10 | 最准，较慢，适合文件转录 |

### 录音模式

| 模式 | 说明 |
|------|------|
| 📼 录完整转（默认） | 录完所有音频后统一识别，准确率更高 |
| ⚡ 边录边转 | 每段静音后自动切段识别，实时输出，速度稍慢 |

---

## 常见问题

**Q：转录结果为空，什么都没有**
> 通常是麦克风权限被拒绝，录到的是静音。前往 **系统设置 → 隐私与安全性 → 麦克风** 开启权限后重试。

**Q：提示"无法验证开发者"打不开**
> **右键** 点击 app → **「打开」** → 弹窗里点 **「打开」**，仅需操作一次。

**Q：Intel Mac 打不开或闪退**
> 右键点击 app → **「显示简介」** → 勾选 **「使用 Rosetta 打开」**，关闭后重新打开。

**Q：下载模型很慢或失败**
> 软件默认使用 `hf-mirror.com` 镜像下载，如仍失败可手动从镜像站下载对应 `models--Systran--faster-whisper-<size>` 文件夹，放到 `~/Library/Application Support/飞飞转录/whisper_models/` 后在设置里点「本地导入」。

**Q：出现错误弹窗**
> 详细日志保存在 `~/Library/Logs/飞飞转录/app.log`，可将内容发给开发者排查。

---

## 开发者说明

### 环境安装

```zsh
brew install portaudio ffmpeg
pip3 install faster-whisper pyaudio numpy pyqt6 av pyinstaller
```

### 下载模型（用于打包内置）

```python
from faster_whisper import WhisperModel
WhisperModel("small", device="cpu", compute_type="int8",
             download_root="./whisper_models")
```

### 打包 .app

```zsh
bash build_mac.sh
```

### 制作发行版 DMG

```zsh
bash make_dmg.sh
```

产物：`dist/飞飞转录.dmg`

### 项目结构

```
speech-to-text/
├── main_gui.py          # 主程序（PyQt6 界面 + 转录逻辑）
├── 飞飞转录.spec         # PyInstaller 打包配置（含 info_plist）
├── build_mac.sh         # 打包 .app 脚本
├── make_dmg.sh          # 制作 DMG 脚本
├── install_mac.sh       # 开发环境依赖安装
└── whisper_models/      # 模型存放目录（打包时内置 small）
```

---

## 隐私声明

- 所有音频在本机处理，**不上传到任何服务器**
- 不收集任何用户数据
- 模型下载默认走 `hf-mirror.com`（国内镜像），可在代码中修改 `HF_ENDPOINT` 环境变量切换
