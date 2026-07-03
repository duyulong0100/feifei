"""
WhisperModel 单例管理 + 转录逻辑
模型常驻内存，配置变更时才重新加载。
"""
import gc
import os
import sys
import logging
import threading
from typing import Generator, Optional

log = logging.getLogger("飞飞转录.transcriber")

# ── 路径 ─────────────────────────────────────────────────
USER_MODEL_ROOT = os.path.expanduser(
    "~/Library/Application Support/飞飞转录/whisper_models"
)

# 如果是打包后的 .app，内置模型根目录
if getattr(sys, "frozen", False):
    BUNDLED_MODEL_ROOT = os.path.join(sys._MEIPASS, "whisper_models")
else:
    BUNDLED_MODEL_ROOT = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "whisper_models"
    )


# ── 工具函数 ──────────────────────────────────────────────

def _model_complete(root: str, size: str) -> bool:
    """判断 root 目录下 size 模型是否完整"""
    d = os.path.join(root, f"models--Systran--faster-whisper-{size}")
    if not os.path.exists(os.path.join(d, "refs", "main")):
        return False
    blobs = os.path.join(d, "blobs")
    return (
        not any(".incomplete" in f for f in os.listdir(blobs))
        if os.path.exists(blobs)
        else True
    )


def check_downloaded(size: str) -> bool:
    """用户目录或内置目录任一完整即算已下载"""
    return _model_complete(USER_MODEL_ROOT, size) or _model_complete(BUNDLED_MODEL_ROOT, size)


def get_model_root(size: str) -> str:
    """返回模型实际所在目录（用户目录优先，再找内置，兜底用可写目录）"""
    if _model_complete(USER_MODEL_ROOT, size):
        return USER_MODEL_ROOT
    if _model_complete(BUNDLED_MODEL_ROOT, size):
        return BUNDLED_MODEL_ROOT
    return USER_MODEL_ROOT


def dl_root(model_id: str) -> str:
    """model_id 是已知尺寸名则查找对应目录，否则（自定义路径）用用户目录"""
    from .config import MODEL_SIZES
    return get_model_root(model_id) if model_id in MODEL_SIZES else USER_MODEL_ROOT


def _ct2_device() -> str:
    """frozen .app 内强制 cpu，避免 ctranslate2 尝试不可用后端"""
    return "cpu" if getattr(sys, "frozen", False) else "auto"


# ── Transcriber 单例 ──────────────────────────────────────

class Transcriber:
    """
    WhisperModel 单例封装。
    线程安全：使用 _lock 保护模型加载/卸载，转录操作可并发。
    """
    _instance: Optional["Transcriber"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._model = None
        self._model_id: Optional[str] = None
        self._compute_type: Optional[str] = None
        self._model_lock = threading.Lock()

    @classmethod
    def get(cls) -> "Transcriber":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 模型管理 ─────────────────────────────────────────

    def ensure_loaded(self, model_id: str, compute_type: str) -> None:
        """
        确保指定模型已加载。若 model_id/compute_type 与当前一致则跳过。
        若不一致则先卸载再加载。
        """
        with self._model_lock:
            if self._model is not None and \
               self._model_id == model_id and \
               self._compute_type == compute_type:
                log.debug("Model already loaded: %s (%s)", model_id, compute_type)
                return
            self._unload_locked()
            self._load_locked(model_id, compute_type)

    def _load_locked(self, model_id: str, compute_type: str) -> None:
        """（调用时需持有 _model_lock）加载模型"""
        from faster_whisper import WhisperModel
        root = dl_root(model_id)
        log.info("Loading model: %s | device=%s | compute=%s | root=%s",
                 model_id, _ct2_device(), compute_type, root)
        n_cpu = os.cpu_count() or 4
        self._model = WhisperModel(
            model_id,
            device=_ct2_device(),
            compute_type=compute_type,
            download_root=root,
            cpu_threads=max(2, n_cpu * 3 // 4),   # 75% of cores
            num_workers=min(4, max(1, n_cpu // 4)), # parallel segment workers
        )
        self._model_id = model_id
        self._compute_type = compute_type
        log.info("Model loaded: %s", model_id)

    def _unload_locked(self) -> None:
        """（调用时需持有 _model_lock）卸载当前模型"""
        if self._model is not None:
            log.info("Unloading model: %s", self._model_id)
            del self._model
            gc.collect()
            self._model = None
            self._model_id = None
            self._compute_type = None

    def unload(self) -> None:
        """公开接口：卸载模型"""
        with self._model_lock:
            self._unload_locked()

    def is_loaded(self) -> bool:
        return self._model is not None

    def current_model_id(self) -> Optional[str]:
        return self._model_id

    # ── 转录 ─────────────────────────────────────────────

    def transcribe(
        self,
        wav_path: str,
        preset: dict,
        language: str = "zh",
        ctx_prompt: Optional[str] = None,
    ) -> Generator[dict, None, None]:
        """
        对 wav_path 进行转录，逐段 yield 结果 dict：
          {"type": "segment", "text": "...", "start": 0.0, "end": 1.5}
        完成后 yield {"type": "done"}
        出错时 yield {"type": "error", "message": "..."}
        """
        with self._model_lock:
            if self._model is None:
                yield {"type": "error", "message": "模型未加载，请先在管理后台配置模型"}
                return
            model = self._model
            # preset 参数
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
                        yield {"type": "segment", "text": text,
                               "start": round(seg.start, 2), "end": round(seg.end, 2)}
                if count == 0:
                    yield {"type": "error", "message": "VAD 过滤后无语音段（录音可能太短或全是静音）"}
                    return
            except Exception as e:
                log.exception("Transcription error")
                yield {"type": "error", "message": str(e)}
                return

        yield {"type": "done"}

    def download_model(self, size: str) -> Generator[dict, None, None]:
        """
        下载指定模型，逐步 yield 进度 dict：
          {"type": "progress", "message": "..."} or {"type": "done"} or {"type": "error", ...}
        此函数在独立线程中调用（FastAPI BackgroundTask 或 generator streaming）。
        """
        from .config import MODEL_HINTS
        yield {"type": "progress", "message": f"正在下载「{size}」（约 {MODEL_HINTS.get(size, '?')}）…"}
        try:
            from faster_whisper import WhisperModel
            os.makedirs(USER_MODEL_ROOT, exist_ok=True)
            # 仅用于下载，不常驻
            m = WhisperModel(size, device="cpu", compute_type="int8",
                             download_root=USER_MODEL_ROOT)
            del m; gc.collect()
            yield {"type": "done", "message": f"「{size}」下载完成"}
        except Exception as e:
            log.exception("Download error: %s", size)
            yield {"type": "error", "message": str(e)}
