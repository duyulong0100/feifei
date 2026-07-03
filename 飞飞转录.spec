# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('whisper_models/CACHEDIR.TAG', 'whisper_models'), ('whisper_models/models--Systran--faster-whisper-small', 'whisper_models/models--Systran--faster-whisper-small')]
binaries = []
hiddenimports = ['pyaudio', 'numpy', 'av']
tmp_ret = collect_all('ctranslate2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tokenizers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('faster_whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('huggingface_hub')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='飞飞转录',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='飞飞转录',
)
app = BUNDLE(
    coll,
    name='飞飞转录.app',
    icon='AppIcon.icns',
    bundle_identifier='com.feifei.transcription',
    info_plist={
        'LSMultipleInstancesProhibited': True,
        'NSMicrophoneUsageDescription': '需要麦克风权限以进行语音转录',
        'NSHighResolutionCapable': True,
        'LSBackgroundOnly': False,
    },
)
