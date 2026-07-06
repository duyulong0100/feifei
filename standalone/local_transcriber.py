"""
单机版本地转录模块
模型常驻内存；打包后优先使用内置 bundled_model，
开发环境回退到 whisper_models 缓存目录。
"""
import gc
import os
import sys
import logging
import threading
from typing import Generator, Optional

log = logging.getLogger("飞飞转录单机版.transcriber")

# ── 模型路径解析 ───────────────────────────────────────────

def _bundled_model_path() -> Optional[str]:
    """
    返回内置模型目录的绝对路径。
    - 打包后：位于 _MEIPASS/bundled_model/
    - 开发环境：standalone/ 同级的 bundled_model/ 目录（由 build 脚本生成）
    如果目录不存在或不完整则返回 None。
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "bundled_model")
    # 基本完整性检查
    if os.path.exists(os.path.join(path, "model.bin")):
        return path
    return None


def _dev_cache_root() -> str:
    """开发环境：项目根目录下的 whisper_models（本地缓存）"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "whisper_models")


def _dev_cache_complete(size: str = "small") -> bool:
    root = _dev_cache_root()
    d    = os.path.join(root, f"models--Systran--faster-whisper-{size}")
    if not os.path.exists(os.path.join(d, "refs", "main")):
        return False
    blobs = os.path.join(d, "blobs")
    return (
        not any(".incomplete" in f for f in os.listdir(blobs))
        if os.path.exists(blobs)
        else True
    )


def get_model_path() -> tuple[str, bool]:
    """
    返回 (model_path_or_id, use_direct_path)。
    - use_direct_path=True  → model_path_or_id 是绝对目录路径，直接传给 WhisperModel
    - use_direct_path=False → model_path_or_id 是 size 字符串，走缓存路由
    """
    bundled = _bundled_model_path()
    if bundled:
        return bundled, True
    # 开发环境回退
    if _dev_cache_complete("small"):
        return "small", False
    raise RuntimeError(
        "找不到 Whisper small 模型。\n"
        "请先运行 build_mac.sh 或手动将模型文件放置到 standalone/bundled_model/ 目录。"
    )


# ── compute type ──────────────────────────────────────────

def _ct2_device() -> str:
    """frozen .app 内强制 cpu，避免 ctranslate2 尝试不可用后端"""
    return "cpu" if getattr(sys, "frozen", False) else "auto"


# ── Transcriber 单例 ──────────────────────────────────────

class Transcriber:
    """
    WhisperModel 单例封装。
    线程安全：_model_lock 保护加载 / 卸载；转录操作可并发（同一模型实例）。
    """
    _instance: Optional["Transcriber"] = None
    _class_lock = threading.Lock()

    def __init__(self):
        self._model          = None
        self._loaded_ct      = None   # compute_type 已加载
        self._model_lock     = threading.Lock()

    @classmethod
    def get(cls) -> "Transcriber":
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 加载 / 卸载 ──────────────────────────────────────

    def ensure_loaded(self, compute_type: str) -> None:
        """确保指定 compute_type 的模型已加载，已匹配则跳过。"""
        with self._model_lock:
            if self._model is not None and self._loaded_ct == compute_type:
                return
            self._unload_locked()
            self._load_locked(compute_type)

    def _load_locked(self, compute_type: str) -> None:
        from faster_whisper import WhisperModel
        model_path, is_direct = get_model_path()
        device = _ct2_device()
        n_cpu  = os.cpu_count() or 4
        log.info("Loading model: path=%s direct=%s device=%s compute=%s",
                 model_path, is_direct, device, compute_type)
        if is_direct:
            # 直接路径（bundled_model/），不走 huggingface hub 下载
            self._model = WhisperModel(
                model_path,
                device=device,
                compute_type=compute_type,
                cpu_threads=max(2, n_cpu * 3 // 4),
                num_workers=min(4, max(1, n_cpu // 4)),
            )
        else:
            # 开发环境，走缓存 download_root
            self._model = WhisperModel(
                model_path,       # e.g. "small"
                device=device,
                compute_type=compute_type,
                download_root=_dev_cache_root(),
                cpu_threads=max(2, n_cpu * 3 // 4),
                num_workers=min(4, max(1, n_cpu // 4)),
            )
        self._loaded_ct = compute_type
        log.info("Model loaded (compute=%s)", compute_type)

    def _unload_locked(self) -> None:
        if self._model is not None:
            log.info("Unloading model")
            del self._model
            gc.collect()
            self._model     = None
            self._loaded_ct = None

    def unload(self) -> None:
        with self._model_lock:
            self._unload_locked()

    def is_loaded(self) -> bool:
        return self._model is not None

    # ── 转录 ─────────────────────────────────────────────

    def transcribe(
        self,
        wav_path: str,
        preset: dict,
        language: str = "zh",
        ctx_prompt: Optional[str] = None,
    ) -> Generator[dict, None, None]:
        """
        逐段 yield 转录结果：
          {"type": "segment", "text": "...", "start": 0.0, "end": 1.5}
        完成后 yield {"type": "done"}
        出错时 yield {"type": "error", "message": "..."}
        """
        with self._model_lock:
            if self._model is None:
                yield {"type": "error", "message": "模型未加载"}
                return
            model = self._model
            prompt = ctx_prompt if ctx_prompt is not None else preset.get("initial_prompt")
            try:
                segs, _info = model.transcribe(
                    wav_path,
                    language=language,
                    beam_size=preset["beam_size"],
                    initial_prompt=prompt,
                    condition_on_previous_text=preset["condition_on_previous_text"],
                    vad_filter=preset["vad_filter"],
                    vad_parameters=preset["vad_parameters"],
                )
                count = 0
                for seg in segs:
                    text = seg.text.strip()
                    if text:
                        count += 1
                        yield {
                            "type":  "segment",
                            "text":  text,
                            "start": round(seg.start, 2),
                            "end":   round(seg.end,   2),
                        }
                if count == 0:
                    yield {
                        "type":    "error",
                        "message": "VAD 过滤后无语音段（录音可能太短或全是静音）",
                    }
                    return
            except Exception as e:
                log.exception("Transcription error")
                yield {"type": "error", "message": str(e)}
                return

        yield {"type": "done"}
