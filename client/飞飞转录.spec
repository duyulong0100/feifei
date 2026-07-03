# -*- mode: python ; coding: utf-8 -*-
"""
飞飞转录客户端 · PyInstaller 打包配置（macOS + Windows 通用）
"""
import sys
from PyInstaller.utils.hooks import collect_all

import os as _os
_here = _os.path.dirname(_os.path.abspath(SPEC))

datas = [
    (_os.path.join(_here, "logo-app.png"),        "."),
    (_os.path.join(_here, "logo-background.png"), "."),
]
binaries     = []
hiddenimports = [
    "pyaudio",
    "numpy",
    "requests",
    "urllib3",
    "charset_normalizer",
    "certifi",
    "idna",
    "api_client",
]

for pkg in ("PyQt6", "PyQt6.Qt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets"):
    try:
        tmp = collect_all(pkg)
        datas    += tmp[0]
        binaries += tmp[1]
        hiddenimports += tmp[2]
    except Exception:
        pass

a = Analysis(
    ["main_gui.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "faster_whisper", "ctranslate2", "tokenizers",
        "huggingface_hub", "torch", "torchaudio",
        "matplotlib", "scipy", "PIL",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

_icon_file = (
    _os.path.join(_here, "logo-app.icns") if sys.platform == "darwin"
    else _os.path.join(_here, "logo-app.ico")
)
_icon = _icon_file if _os.path.exists(_icon_file) else None

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
    upx_exclude=[],
    name="飞飞转录",
)

# ── macOS：额外打成 .app bundle ───────────────────────────
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="飞飞转录.app",
        icon=_icon,
        bundle_identifier="com.feifei.transcription.client",
        info_plist={
            "CFBundleDisplayName":           "飞飞转录",
            "CFBundleShortVersionString":    "2.0.0",
            "LSMultipleInstancesProhibited": True,
            "NSMicrophoneUsageDescription":  "需要麦克风权限以进行实时语音转录",
            "NSHighResolutionCapable":       True,
            "LSBackgroundOnly":              False,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
