"""
模型配置管理：持久化到 ~/.飞飞转录/server_config.json
"""
import json
import os

_CONFIG_DIR  = os.path.expanduser("~/Library/Application Support/飞飞转录")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "server_config.json")

# ── 常量（与原 main_gui.py 保持一致）────────────────────────
MODEL_SIZES  = ["tiny", "base", "small", "medium", "large-v3"]
MODEL_LABELS = {
    "tiny": "tiny", "base": "base", "small": "small",
    "medium": "medium", "large-v3": "large",
}
MODEL_HINTS = {
    "tiny": "75 MB", "base": "145 MB", "small": "483 MB",
    "medium": "1.5 GB", "large-v3": "3.1 GB",
}
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

_DEFAULT_PREPROCESS = {
    "enabled":        False,
    "preset":         "balanced",    # light | balanced | aggressive
    "echo_reduction": False,          # speechnorm 压制混响尾音
    "spectral_gating": False,         # noisereduce 谱减法（需安装 noisereduce）
    "nr_prop_decrease": 0.75,         # 谱减法降噪比例 0~1
}

_DEFAULT_LLM = {
    "enabled":  False,
    "base_url": "https://api.openai.com/v1",
    "api_key":  "",
    "model":    "gpt-4o-mini",
    "task":     "polish",   # 自动执行的任务：polish | segment | both
    "prompts": {
        "polish":  "你是文字润色专家。将以下语音识别文字润色为规范书面文字：修正错别字、语病，使表达流畅自然，保持原意。直接输出结果，不加解释。",
        "segment": "你是文章整理专家。将以下文字按话题合理分段，段落之间用空行隔开，不要添加任何标题或注释。直接输出结果。",
        "both":    "你是文字处理专家。对以下语音识别文字：①修正错别字和语病，使表达流畅自然；②按话题合理分段，段落之间用空行隔开，不要添加任何标题或注释。直接输出结果。",
    },
}

DEFAULT_CONFIG = {
    "model_size":  "small",
    "quality_key": "⚖ 均衡",
    "custom_path": None,
    "preprocess":  _DEFAULT_PREPROCESS,
    "llm":         _DEFAULT_LLM,
}


def load_config() -> dict:
    """读取配置文件，缺失字段以 DEFAULT_CONFIG 补全（llm 子树深度合并）"""
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = {**DEFAULT_CONFIG, **data}
            # 校验枚举字段
            if cfg["model_size"] not in MODEL_SIZES:
                cfg["model_size"] = DEFAULT_CONFIG["model_size"]
            if cfg["quality_key"] not in QUALITY_PRESETS:
                cfg["quality_key"] = DEFAULT_CONFIG["quality_key"]
            # 深度合并 preprocess 子树
            cfg["preprocess"] = {**_DEFAULT_PREPROCESS, **data.get("preprocess", {})}
            # 深度合并 llm 子树，避免局部更新丢失默认 prompts
            saved_llm = data.get("llm", {})
            cfg["llm"] = {**_DEFAULT_LLM, **saved_llm}
            cfg["llm"]["prompts"] = {
                **_DEFAULT_LLM["prompts"],
                **saved_llm.get("prompts", {}),
            }
            return cfg
        except Exception:
            pass
    import copy
    return copy.deepcopy(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    """保存配置到文件"""
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_quality_preset(quality_key: str) -> dict:
    """根据 quality_key 返回对应的预设参数"""
    return QUALITY_PRESETS.get(quality_key, QUALITY_PRESETS[DEFAULT_CONFIG["quality_key"]])
