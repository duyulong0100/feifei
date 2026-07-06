# -*- mode: python ; coding: utf-8 -*-
"""
飞飞转录 · 单机版 PyInstaller 打包配置
- 内置 faster-whisper small 模型
- 无需服务端，录音 / 转录全部在本地完成
"""
import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

_here = os.path.dirname(os.path.abspath(SPEC))

# ── 内置模型目录（由 build_mac.sh 在打包前准备好）────────
_bundled_model = os.path.join(_here, "bundled_model")
if not os.path.exists(os.path.join(_bundled_model, "model.bin")):
    raise SystemExit(
        "\n❌ 找不到 bundled_model/model.bin\n"
        "   请先运行 build_mac.sh 中的「准备模型」步骤，或手动执行：\n"
        "   python3 prepare_model.py\n"
    )

# ── 收集依赖 ────────────────────────────────────────────
datas     = []
binaries  = []
hiddenimports = [
    "pyaudio", "numpy", "config", "local_transcriber",
    "faster_whisper", "faster_whisper.audio", "faster_whisper.feature_extractor",
    "faster_whisper.tokenizer", "faster_whisper.transcribe", "faster_whisper.vad",
    "faster_whisper.utils",
    "ctranslate2",
    "tokenizers",
    "huggingface_hub",
    "huggingface_hub.file_download",
    "huggingface_hub._commit_api",
    "av",
]

# Logo
if os.path.exists(os.path.join(_here, "logo-app.png")):
    datas.append((os.path.join(_here, "logo-app.png"), "."))

# 内置 Whisper small 模型
datas.append((_bundled_model, "bundled_model"))

# PyQt6
for pkg in ("PyQt6", "PyQt6.Qt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets"):
    try:
        tmp = collect_all(pkg)
        datas    += tmp[0]
        binaries += tmp[1]
        hiddenimports += tmp[2]
    except Exception:
        pass

# faster_whisper 数据文件
try:
    datas += collect_data_files("faster_whisper")
except Exception:
    pass

# ctranslate2 本机库（.dylib / .so / .dll）
try:
    tmp = collect_all("ctranslate2")
    datas    += tmp[0]
    binaries += tmp[1]
    hiddenimports += tmp[2]
except Exception:
    pass

# tokenizers 本机库
try:
    tmp = collect_all("tokenizers")
    datas    += tmp[0]
    binaries += tmp[1]
    hiddenimports += tmp[2]
except Exception:
    pass

# av（faster_whisper 无条件 import av，必须打包）
try:
    tmp = collect_all("av")
    datas    += tmp[0]
    binaries += tmp[1]
    hiddenimports += tmp[2]
except Exception:
    pass

# ── Analysis ────────────────────────────────────────────
a = Analysis(
    [os.path.join(_here, "main_gui.py")],
    pathex=[_here],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch", "torchaudio", "torchvision",
        "matplotlib", "scipy", "PIL",
        "tensorflow", "keras",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

_icon_file = (
    os.path.join(_here, "logo-app.icns") if sys.platform == "darwin"
    else os.path.join(_here, "logo-app.ico")
)
_icon = _icon_file if os.path.exists(_icon_file) else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="飞飞转录",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["*.dylib", "*.so"],   # 避免 UPX 压缩原生库
    name="飞飞转录",
)

# ── macOS .app bundle ───────────────────────────────────
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="飞飞转录.app",
        icon=_icon,
        bundle_identifier="com.feifei.transcription.standalone",
        info_plist={
            "CFBundleDisplayName":           "飞飞转录",
            "CFBundleShortVersionString":    "1.0.0",
            "LSMultipleInstancesProhibited": True,
            "NSMicrophoneUsageDescription":  "需要麦克风权限以进行实时语音转录",
            "NSHighResolutionCapable":       True,
            "LSBackgroundOnly":              False,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
