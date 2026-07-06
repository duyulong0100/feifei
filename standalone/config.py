"""
单机版配置：质量预设 + 本地持久化
不依赖服务端，所有配置存储在用户 Application Support 目录。
"""
import json
import os

_CONFIG_DIR  = os.path.expanduser("~/Library/Application Support/飞飞转录单机版")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "config.json")

# ── 质量预设 ────────────────────────────────────────────────
QUALITY_PRESETS = {
    "⚡ 速度": {
        "compute_type": "int8", "beam_size": 3,
        "initial_prompt": None, "condition_on_previous_text": False,
        "vad_filter": True,
        "vad_parameters": {"threshold": 0.5, "min_silence_duration_ms": 500},
    },
    "⚖ 均衡": {
        "compute_type": "int8_float32", "beam_size": 5,
        "initial_prompt": "以下是普通话的语音识别结果。",
        "condition_on_previous_text": True, "vad_filter": True,
        "vad_parameters": {"threshold": 0.4, "min_silence_duration_ms": 300},
    },
    "🎯 质量": {
        "compute_type": "float32", "beam_size": 10,
        "initial_prompt": "以下是普通话的语音识别结果，请准确识别每个字词。",
        "condition_on_previous_text": True, "vad_filter": True,
        "vad_parameters": {"threshold": 0.3, "min_silence_duration_ms": 200},
    },
}
QUALITY_KEYS = list(QUALITY_PRESETS.keys())

QUALITY_HINTS = {
    QUALITY_KEYS[0]: "int8 · beam 3 · 快",
    QUALITY_KEYS[1]: "int8_float32 · beam 5 · 均衡",
    QUALITY_KEYS[2]: "float32 · beam 10 · 准（较慢）",
}

DEFAULT_CONFIG = {
    "quality_key": "⚖ 均衡",
    "theme":       "dark",
    "mode":        "batch",
}


def load_config() -> dict:
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = {**DEFAULT_CONFIG, **data}
            if cfg["quality_key"] not in QUALITY_PRESETS:
                cfg["quality_key"] = DEFAULT_CONFIG["quality_key"]
            return cfg
        except Exception:
            pass
    import copy
    return copy.deepcopy(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_quality_preset(quality_key: str) -> dict:
    return QUALITY_PRESETS.get(quality_key, QUALITY_PRESETS[DEFAULT_CONFIG["quality_key"]])
