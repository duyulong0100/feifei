"""
音频预处理模块
使用 ffmpeg 滤镜链 + 可选 noisereduce 谱减法，去除回声、杂音、低频噪声。

预设强度：
  light      高通滤波 + 音量归一化（速度快，影响小）
  balanced   高通 + FFT 降噪 + 归一化（推荐）
  aggressive 高通 + 非局部均值降噪 + FFT 降噪 + 响度标准化（最干净，速度慢）

Python 谱减法（noisereduce）可在 ffmpeg 之后追加运行，对非平稳噪声效果更好。
"""
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

log = logging.getLogger("飞飞转录.preprocess")

# ── ffmpeg 滤镜链预设 ─────────────────────────────────────────

_PRESETS: dict[str, list[str]] = {
    "light": [
        "highpass=f=80",              # 去除 <80Hz 低频噪声（空调、震动）
        "dynaudnorm=f=150:g=15",      # 动态音量归一化
    ],
    "balanced": [
        "highpass=f=80",
        "afftdn=nf=-25:nr=33:nt=w",  # FFT 降噪：-25dB 噪底，33% 降噪强度
        "dynaudnorm=f=150:g=15",
    ],
    "aggressive": [
        "highpass=f=80",
        "anlmdn=s=7:p=0.002:r=0.002:m=15",  # 非局部均值降噪（宽带噪声）
        "afftdn=nf=-35:nr=50:nt=w",          # 更强的 FFT 降噪
        "loudnorm=I=-16:LRA=11:TP=-1.5",     # EBU R128 响度标准化
    ],
}

PRESET_HINTS = {
    "light":      "高通滤波 + 归一化，速度快，不改变音色",
    "balanced":   "高通 + FFT 降噪 + 归一化（推荐）",
    "aggressive": "高通 + 宽带降噪 + FFT + 响度标准化，效果最强，速度较慢",
}


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def noisereduce_available() -> bool:
    try:
        import noisereduce  # noqa: F401
        import soundfile    # noqa: F401
        return True
    except ImportError:
        return False


def preprocess(input_path: str, cfg: dict) -> str:
    """
    对音频做预处理，返回处理后的临时 WAV 文件路径。
    调用方负责在使用完后删除该文件。

    若预处理未启用或失败，返回 input_path（原路径）。

    Parameters
    ----------
    input_path : 输入音频路径（任意格式，由 ffmpeg 解码）
    cfg        : preprocess 配置子树
    """
    if not cfg.get("enabled", False):
        return input_path

    if not ffmpeg_available():
        log.warning("ffmpeg not found — skipping audio preprocessing")
        return input_path

    preset   = cfg.get("preset", "balanced")
    filters  = list(_PRESETS.get(preset, _PRESETS["balanced"]))

    # 回声抑制：speechnorm 进一步压制峰值，减少混响拖尾影响
    if cfg.get("echo_reduction", False):
        filters.insert(-1, "speechnorm=e=25:r=0.0005:l=1")

    filter_chain = ",".join(filters)

    # 输出为 16kHz 单声道 WAV（Whisper 最佳输入）
    fd, out_path = tempfile.mkstemp(suffix="_clean.wav")
    os.close(fd)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-af", filter_chain,
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        out_path,
        "-loglevel", "error",
    ]

    log.info("Preprocessing | preset=%s echo=%s | %s",
             preset, cfg.get("echo_reduction", False), filter_chain)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error("ffmpeg preprocessing failed:\n%s", result.stderr[:800])
            _safe_remove(out_path)
            return input_path

        out_size = os.path.getsize(out_path)
        log.info("ffmpeg preprocessing done → %s (%d bytes)", out_path, out_size)

        # 可选：Python 谱减法（noisereduce）追加处理
        if cfg.get("spectral_gating", False) and noisereduce_available():
            out_path = _spectral_gate(out_path, cfg)

        return out_path

    except subprocess.TimeoutExpired:
        log.error("ffmpeg preprocessing timeout")
        _safe_remove(out_path)
        return input_path
    except Exception:
        log.exception("Unexpected preprocessing error")
        _safe_remove(out_path)
        return input_path


def _spectral_gate(wav_path: str, cfg: dict) -> str:
    """
    用 noisereduce 对 WAV 做谱减法（非平稳噪声效果好）。
    在原文件基础上生成新的临时文件，并删除旧文件。
    """
    import soundfile as sf
    import noisereduce as nr
    import numpy as np

    fd, out_path = tempfile.mkstemp(suffix="_nr.wav")
    os.close(fd)

    try:
        data, rate = sf.read(wav_path)
        if data.ndim > 1:
            data = data.mean(axis=1)   # 强制单声道

        prop_decrease = float(cfg.get("nr_prop_decrease", 0.75))
        reduced = nr.reduce_noise(
            y=data, sr=rate,
            stationary=False,
            prop_decrease=prop_decrease,
        )
        sf.write(out_path, reduced.astype(np.float32), rate, subtype="PCM_16")
        log.info("Spectral gating done → %s", out_path)
        _safe_remove(wav_path)   # 删除 ffmpeg 输出，用 nr 输出代替
        return out_path
    except Exception:
        log.exception("noisereduce failed, using ffmpeg output")
        _safe_remove(out_path)
        return wav_path


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
