import sys
import os
import gc
import wave
import queue
import tempfile
import multiprocessing
import logging
import traceback
import pyaudio
import numpy as np

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# frozen .app 内强制单进程：禁止 OpenMP/ctranslate2 再 spawn 子进程
if getattr(sys, "frozen", False):
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")

# ── 文件日志（frozen .app 里 stdout/stderr 会被丢弃，日志是唯一调试手段） ──
_LOG_DIR = os.path.expanduser("~/Library/Logs/飞飞转录")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(_LOG_DIR, "app.log"),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("飞飞转录")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QFileDialog, QMessageBox, QButtonGroup,
    QFrame, QSizePolicy, QMenuBar, QMenu, QStatusBar,
    QCheckBox
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QTextBlockFormat, QColor, QAction, QFont
from faster_whisper import WhisperModel

# ── 路径 ─────────────────────────────────────────────────
# 内置模型目录：打包后在 sys._MEIPASS 里（只读），开发时和脚本同目录
if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
BUNDLED_MODEL_ROOT = os.path.join(_BASE, "whisper_models")

# 用户模型目录：可写，用于下载新模型
USER_MODEL_ROOT = os.path.expanduser(
    "~/Library/Application Support/飞飞转录/whisper_models"
)
CHUNK, FORMAT, CHANNELS, RATE = 1024, pyaudio.paInt16, 1, 16000

SILENCE_RMS_THRESH = 300
SILENCE_MIN_FRAMES = int(1.5 * RATE / CHUNK)
CHUNK_MIN_FRAMES   = int(8  * RATE / CHUNK)
CHUNK_MAX_FRAMES   = int(30 * RATE / CHUNK)

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]
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
QUALITY_KEYS  = list(QUALITY_PRESETS.keys())
QUALITY_HINTS = {
    QUALITY_KEYS[0]: "int8 · beam 3 · 快",
    QUALITY_KEYS[1]: "int8_float32 · beam 5 · 均衡",
    QUALITY_KEYS[2]: "float32 · beam 10 · 准（较慢）",
}

# ── 样式表 ────────────────────────────────────────────────
STYLE = """
* { font-family: "PingFang SC", "Helvetica Neue"; font-size: 13px;
    color: #1C1C1E; outline: none; }
QMainWindow, QDialog, #central { background: #F2F2F7; }

QMenuBar { background: #F2F2F7; border-bottom: 1px solid #E5E5EA; padding: 2px 4px; }
QMenuBar::item { padding: 4px 10px; border-radius: 6px; }
QMenuBar::item:selected { background: #E5E5EA; }
QMenu { background: white; border: 1px solid #E5E5EA; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 4px; }
QMenu::item:selected { background: #007AFF; color: white; }
QMenu::separator { height: 1px; background: #E5E5EA; margin: 4px 8px; }

#card { background: white; border-radius: 14px; border: 1px solid #E5E5EA; }
#section { background: white; border-radius: 10px; border: 1px solid #E5E5EA; }
#titleLabel { font-size: 17px; font-weight: 700; letter-spacing: -0.3px; }
#subtitleLabel { font-size: 12px; color: #8E8E93; }
#sectionTitle { font-size: 12px; font-weight: 600; color: #8E8E93; letter-spacing: 0.3px; }

#pillBtn {
    background: #F2F2F7; border: 1.5px solid #D1D1D6;
    border-radius: 8px; padding: 5px 14px; font-size: 13px;
    color: #3C3C43; min-width: 60px;
}
#pillBtn:checked { background: #007AFF; border-color: #007AFF; color: white; font-weight: 600; }
#pillBtn:hover:!checked { border-color: #007AFF; color: #007AFF; }

#pillBtnSpeed, #pillBtnBalance, #pillBtnQuality {
    background: #F2F2F7; border: 1.5px solid #D1D1D6;
    border-radius: 8px; padding: 5px 16px; font-size: 13px;
    color: #3C3C43; min-width: 80px;
}
#pillBtnSpeed:checked   { background: #34C759; border-color: #34C759; color: white; font-weight: 600; }
#pillBtnBalance:checked { background: #007AFF; border-color: #007AFF; color: white; font-weight: 600; }
#pillBtnQuality:checked { background: #FF9500; border-color: #FF9500; color: white; font-weight: 600; }
#pillBtnSpeed:hover:!checked, #pillBtnBalance:hover:!checked,
#pillBtnQuality:hover:!checked { border-color: #007AFF; color: #007AFF; }

/* 设置页复选框 */
QCheckBox { font-size: 13px; color: #1C1C1E; spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 5px;
    border: 1.5px solid #D1D1D6; background: white;
}
QCheckBox::indicator:checked {
    background: #007AFF; border-color: #007AFF;
    image: url("data:image/svg+xml,<svg/>");  /* Qt 会忽略无效 url，用颜色填充即可 */
}
QCheckBox::indicator:hover { border-color: #007AFF; }

#btnPrimary {
    background: #007AFF; color: white; border: none;
    border-radius: 10px; padding: 10px 0; font-size: 14px; font-weight: 500;
}
#btnPrimary:hover { background: #0062CC; }
#btnPrimary:pressed { background: #004FA3; }
#btnRecord {
    background: #FF3B30; color: white; border: none;
    border-radius: 10px; padding: 10px 0; font-size: 14px; font-weight: 500;
}
#btnRecord:hover { background: #D63028; }
#btnSecondary {
    background: white; color: #007AFF; border: 1.5px solid #C7D8F5;
    border-radius: 10px; padding: 10px 0; font-size: 14px;
}
#btnSecondary:hover { background: #F0F7FF; }
#btnSecondary:pressed { background: #E0EEFF; }
#btnAction {
    background: white; color: #007AFF; border: 1px solid #C7D8F5;
    border-radius: 7px; padding: 5px 14px; font-size: 12px;
}
#btnAction:hover { background: #F0F7FF; }
#btnAction:disabled { color: #C7C7CC; border-color: #E5E5EA; }
#btnDanger {
    background: white; color: #FF3B30; border: 1px solid #FFD0CE;
    border-radius: 7px; padding: 5px 14px; font-size: 12px;
}
#btnDanger:hover { background: #FFF3F2; }
#btnClose {
    background: #007AFF; color: white; border: none;
    border-radius: 8px; padding: 8px 28px; font-size: 13px; font-weight: 500;
}
#btnClose:hover { background: #0062CC; }

#statusOk    { color: #34C759; font-size: 12px; }
#statusError { color: #FF3B30; font-size: 12px; }
#statusWarn  { color: #FF9500; font-size: 12px; }
#pathLabel   { color: #8E8E93; font-size: 12px; }

/* 转录文本区 */
#transcript {
    background: white; border: 1.5px solid #E5E5EA; border-radius: 12px;
    padding: 20px; selection-background-color: #CCE4FF;
}
#transcript:focus { border-color: #007AFF; }

QStatusBar { background: #F2F2F7; border-top: 1px solid #E5E5EA; font-size: 12px; color: #8E8E93; }
QStatusBar::item { border: none; }

QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #C7C7CC; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
#sep { background: #F2F2F7; max-height: 1px; min-height: 1px; }
"""

# ── 文本格式 ──────────────────────────────────────────────
def _fmt_label():
    """分段标签：小号灰字"""
    f = QTextCharFormat()
    f.setForeground(QColor("#B0B0B8"))
    f.setFontPointSize(11)
    return f

def _fmt_body():
    """正文：标准黑字，稍大"""
    f = QTextCharFormat()
    f.setForeground(QColor("#1C1C1E"))
    f.setFontPointSize(15)
    return f

def _blk_label():
    b = QTextBlockFormat()
    b.setTopMargin(20); b.setBottomMargin(4)
    return b

def _blk_body():
    b = QTextBlockFormat()
    b.setTopMargin(0); b.setBottomMargin(2)
    b.setLineHeight(160, 1)   # 160% 行高
    return b

# ── 工具 ──────────────────────────────────────────────────
def _model_complete(root, size):
    """判断 root 目录下 size 模型是否完整"""
    d = os.path.join(root, f"models--Systran--faster-whisper-{size}")
    if not os.path.exists(os.path.join(d, "refs", "main")):
        return False
    blobs = os.path.join(d, "blobs")
    return not any(".incomplete" in f for f in os.listdir(blobs)) if os.path.exists(blobs) else True

def check_downloaded(size):
    """用户目录或内置目录任一完整即算已下载"""
    return _model_complete(USER_MODEL_ROOT, size) or _model_complete(BUNDLED_MODEL_ROOT, size)

def get_model_root(size):
    """返回模型实际所在 download_root（用户目录优先，再找内置，兜底用可写目录）"""
    if _model_complete(USER_MODEL_ROOT, size):
        return USER_MODEL_ROOT
    if _model_complete(BUNDLED_MODEL_ROOT, size):
        return BUNDLED_MODEL_ROOT
    return USER_MODEL_ROOT   # 模型不存在时返回可写目录，让 WhisperModel 去下载

def dl_root(model_id):
    """线程内通用：model_id 是已知尺寸名则查找对应目录，否则（自定义路径）用用户目录"""
    return get_model_root(model_id) if model_id in MODEL_SIZES else USER_MODEL_ROOT

def _ct2_device():
    """frozen .app 内强制 cpu，避免 ctranslate2 尝试不可用的 Metal/CoreML 后端"""
    return "cpu" if getattr(sys, "frozen", False) else "auto"

def polish(w):
    w.style().unpolish(w); w.style().polish(w)

def save_wav(frames, path):
    pa = pyaudio.PyAudio()
    wf = wave.open(path, "wb")
    wf.setnchannels(CHANNELS); wf.setsampwidth(pa.get_sample_size(FORMAT))
    wf.setframerate(RATE); wf.writeframes(b"".join(frames))
    wf.close(); pa.terminate()


# ── 线程 ─────────────────────────────────────────────────
class DownloadThread(QThread):
    progress = pyqtSignal(str)
    done     = pyqtSignal(bool, str)
    def __init__(self, size):
        super().__init__(); self.size = size
    def run(self):
        try:
            self.progress.emit(f"正在下载「{self.size}」（约 {MODEL_HINTS[self.size]}）…")
            m = WhisperModel(self.size, device="cpu", compute_type="int8", download_root=USER_MODEL_ROOT)
            del m; gc.collect()
            self.done.emit(True, self.size)
        except Exception as e:
            self.done.emit(False, str(e))


class TranscribeWorker(QThread):
    ready     = pyqtSignal()
    segment   = pyqtSignal(int, str)
    chunk_end = pyqtSignal(int)
    all_done  = pyqtSignal()
    error     = pyqtSignal(str)
    _STOP = object()

    def __init__(self, model, preset):
        super().__init__()
        self._model_id = model; self._preset = preset
        self._queue = queue.Queue()

    def submit(self, wav_path, chunk_no, ctx_prompt=None):
        self._queue.put((chunk_no, wav_path, ctx_prompt))

    def stop(self):
        self._queue.put(self._STOP)

    def run(self):
        try:
            m = WhisperModel(
                self._model_id, device=_ct2_device(),
                compute_type=self._preset["compute_type"],
                download_root=dl_root(self._model_id),
                cpu_threads=max(1, (os.cpu_count() or 4) // 2),
            )
            self.ready.emit()
        except Exception as e:
            self.error.emit(f"模型加载失败：{e}"); return
        try:
            while True:
                item = self._queue.get()
                if item is self._STOP: break
                chunk_no, wav_path, ctx_prompt = item
                prompt = ctx_prompt if ctx_prompt is not None else self._preset["initial_prompt"]
                try:
                    segs, _ = m.transcribe(
                        wav_path, language="zh",
                        beam_size=self._preset["beam_size"],
                        initial_prompt=prompt,
                        condition_on_previous_text=self._preset["condition_on_previous_text"],
                        vad_filter=self._preset["vad_filter"],
                        vad_parameters=self._preset["vad_parameters"],
                    )
                    for seg in segs:
                        t = seg.text.strip()
                        if t: self.segment.emit(chunk_no, t)
                except Exception as e:
                    self.segment.emit(chunk_no, f"[识别失败：{e}]")
                finally:
                    self.chunk_end.emit(chunk_no)
                    try: os.remove(wav_path)
                    except OSError: pass
        finally:
            del m; gc.collect()
            self.all_done.emit()


class SrtThread(QThread):
    result = pyqtSignal(str)   # 保存路径
    end    = pyqtSignal()
    def __init__(self, path, model, preset):
        super().__init__()
        self.path = path; self.model = model; self.preset = preset
    def run(self):
        m = None
        try:
            m = WhisperModel(
                self.model, device=_ct2_device(),
                compute_type=self.preset["compute_type"],
                download_root=dl_root(self.model),
                cpu_threads=max(1, (os.cpu_count() or 4) // 2),
            )
            segs, _ = m.transcribe(
                self.path, language="zh",
                beam_size=self.preset["beam_size"],
                initial_prompt=self.preset["initial_prompt"],
                condition_on_previous_text=self.preset["condition_on_previous_text"],
                vad_filter=self.preset["vad_filter"],
                vad_parameters=self.preset["vad_parameters"],
            )
            def fmt(sec):
                h, r = divmod(int(sec), 3600); mn, s = divmod(r, 60)
                return f"{h:02d}:{mn:02d}:{s:02d},{int((sec%1)*1000):03d}"
            srt = "".join(
                f"{i}\n{fmt(s.start)} --> {fmt(s.end)}\n{s.text.strip()}\n\n"
                for i, s in enumerate(segs, 1)
            )
            out = os.path.splitext(self.path)[0] + ".srt"
            with open(out, "w", encoding="utf-8") as f: f.write(srt)
            self.result.emit(out)
        except Exception as e:
            self.result.emit(f"ERROR:{e}")
        finally:
            if m is not None: del m; gc.collect()
            self.end.emit()


class FullTranscribeThread(QThread):
    """录完整体转：对完整 WAV 做一次性识别，逐句流式 emit"""
    segment = pyqtSignal(str)
    done    = pyqtSignal(str)    # 携带 wav_path 供清理
    error   = pyqtSignal(str)

    def __init__(self, wav_path, model, preset):
        super().__init__()
        self.wav_path = wav_path; self.model = model; self.preset = preset

    def run(self):
        m = None
        try:
            root = dl_root(self.model)
            log.info("FullTranscribe start | wav=%s model=%s device=%s compute=%s root=%s",
                     self.wav_path, self.model, _ct2_device(),
                     self.preset["compute_type"], root)
            m = WhisperModel(
                self.model, device=_ct2_device(),
                compute_type=self.preset["compute_type"],
                download_root=root,
                cpu_threads=max(1, (os.cpu_count() or 4) // 2),
            )
            log.info("Model loaded OK, starting transcribe …")
            segs, info = m.transcribe(
                self.wav_path, language="zh",
                beam_size=self.preset["beam_size"],
                initial_prompt=self.preset["initial_prompt"],
                condition_on_previous_text=self.preset["condition_on_previous_text"],
                vad_filter=self.preset["vad_filter"],
                vad_parameters=self.preset["vad_parameters"],
            )
            count = 0
            for seg in segs:
                t = seg.text.strip()
                log.debug("seg[%d] text=%r", count, t)
                count += 1
                if t: self.segment.emit(t)
            log.info("Transcribe done, %d segments", count)
            if count == 0:
                self.error.emit("VAD 过滤后无语音段（录音可能太短或静音）")
        except Exception as e:
            log.error("FullTranscribe error: %s", traceback.format_exc())
            self.error.emit(str(e))
        finally:
            if m is not None: del m; gc.collect()
            self.done.emit(self.wav_path)


# ── 设置对话框 ────────────────────────────────────────────
class SettingsDialog(QDialog):
    changed = pyqtSignal()

    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("偏好设置")
        self.setModal(True); self.setFixedWidth(500)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui(); self._refresh_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20); layout.setSpacing(14)

        # 模型
        layout.addWidget(self._section_label("模型"))
        model_sec = QFrame(); model_sec.setObjectName("section")
        ml = QVBoxLayout(model_sec); ml.setContentsMargins(14,12,14,12); ml.setSpacing(10)

        row_pills = QHBoxLayout(); row_pills.setSpacing(6)
        self._model_group = QButtonGroup(self); self._model_group.setExclusive(True)
        self._model_btns  = {}
        for size in MODEL_SIZES:
            b = QPushButton(size); b.setObjectName("pillBtn")
            b.setCheckable(True); b.setFixedHeight(30)
            b.clicked.connect(self._on_model_changed)
            self._model_group.addButton(b)
            self._model_btns[size] = b; row_pills.addWidget(b)
        self._model_btns[self.cfg["model_size"]].setChecked(True)
        row_pills.addStretch(); ml.addLayout(row_pills)

        row_dl = QHBoxLayout(); row_dl.setSpacing(8)
        self._lbl_model_status = QLabel(); row_dl.addWidget(self._lbl_model_status)
        row_dl.addStretch()
        self._btn_download = QPushButton("☁ 下载"); self._btn_download.setObjectName("btnAction")
        self._btn_download.setFixedHeight(28); self._btn_download.clicked.connect(self._download_model)
        self._btn_import = QPushButton("📂 本地导入"); self._btn_import.setObjectName("btnAction")
        self._btn_import.setFixedHeight(28); self._btn_import.clicked.connect(self._import_model)
        self._btn_clear = QPushButton("清除路径"); self._btn_clear.setObjectName("btnDanger")
        self._btn_clear.setFixedHeight(28); self._btn_clear.clicked.connect(self._clear_path)
        row_dl.addWidget(self._btn_download); row_dl.addWidget(self._btn_import)
        row_dl.addWidget(self._btn_clear); ml.addLayout(row_dl)

        self._lbl_path = QLabel(); self._lbl_path.setObjectName("pathLabel")
        self._lbl_path.setWordWrap(True); ml.addWidget(self._lbl_path)
        layout.addWidget(model_sec)

        # 识别质量
        layout.addWidget(self._section_label("识别质量"))
        q_sec = QFrame(); q_sec.setObjectName("section")
        ql = QVBoxLayout(q_sec); ql.setContentsMargins(14,12,14,12); ql.setSpacing(8)
        row_q = QHBoxLayout(); row_q.setSpacing(6)
        self._quality_group = QButtonGroup(self); self._quality_group.setExclusive(True)
        self._quality_btns  = {}
        for key, obj in zip(QUALITY_KEYS, ["pillBtnSpeed","pillBtnBalance","pillBtnQuality"]):
            b = QPushButton(key); b.setObjectName(obj)
            b.setCheckable(True); b.setFixedHeight(30)
            b.clicked.connect(self._on_quality_changed)
            self._quality_group.addButton(b)
            self._quality_btns[key] = b; row_q.addWidget(b)
        self._quality_btns[self.cfg["quality_key"]].setChecked(True)
        row_q.addStretch(); ql.addLayout(row_q)
        self._lbl_quality_hint = QLabel(); self._lbl_quality_hint.setObjectName("subtitleLabel")
        ql.addWidget(self._lbl_quality_hint); layout.addWidget(q_sec)

        # 录音模式
        layout.addWidget(self._section_label("录音模式"))
        mode_sec = QFrame(); mode_sec.setObjectName("section")
        mo = QVBoxLayout(mode_sec); mo.setContentsMargins(14, 14, 14, 14); mo.setSpacing(6)
        self._chk_realtime = QCheckBox("开启边录边转（实时分段识别）")
        self._chk_realtime.setChecked(self.cfg.get("mode") == "realtime")
        self._chk_realtime.toggled.connect(self._on_mode_toggled)
        mo.addWidget(self._chk_realtime)
        self._lbl_mode_hint = QLabel(); self._lbl_mode_hint.setObjectName("subtitleLabel")
        mo.addWidget(self._lbl_mode_hint)
        layout.addWidget(mode_sec)
        self._on_mode_toggled(self._chk_realtime.isChecked())

        layout.addSpacing(4)
        row_close = QHBoxLayout(); row_close.addStretch()
        btn_close = QPushButton("完成"); btn_close.setObjectName("btnClose")
        btn_close.setFixedHeight(34); btn_close.clicked.connect(self.accept)
        row_close.addWidget(btn_close); layout.addLayout(row_close)

        self._on_quality_changed(); self._update_path_ui()

    def _section_label(self, text):
        l = QLabel(text.upper()); l.setObjectName("sectionTitle"); return l

    def _refresh_status(self):
        self._update_model_pills()
        size = self.cfg["model_size"]
        if self.cfg.get("custom_path"):
            self._set_model_status("✅ 本地模型", "statusOk")
        elif check_downloaded(size):
            self._set_model_status(f"✅ 已下载  {MODEL_HINTS[size]}", "statusOk")
        else:
            self._set_model_status(f"❌ 未下载  约 {MODEL_HINTS[size]}", "statusError")
        self.changed.emit()

    def _set_model_status(self, text, obj):
        self._lbl_model_status.setText(text)
        self._lbl_model_status.setObjectName(obj); polish(self._lbl_model_status)

    def _update_model_pills(self):
        for size, btn in self._model_btns.items():
            btn.setText(f"{size} ✓" if check_downloaded(size) else size)

    def _update_path_ui(self):
        p = self.cfg.get("custom_path")
        if p:
            self._lbl_path.setText(f"路径：{p if len(p)<=55 else '…'+p[-52:]}")
            self._btn_clear.show()
        else:
            self._lbl_path.clear(); self._btn_clear.hide()

    def _on_model_changed(self):
        self.cfg["model_size"] = next(s for s,b in self._model_btns.items() if b.isChecked())
        self.cfg["custom_path"] = None
        self._update_path_ui(); self._refresh_status()

    def _on_quality_changed(self):
        self.cfg["quality_key"] = next(k for k,b in self._quality_btns.items() if b.isChecked())
        self._lbl_quality_hint.setText(QUALITY_HINTS.get(self.cfg["quality_key"], ""))
        self.changed.emit()

    def _on_mode_toggled(self, checked):
        self.cfg["mode"] = "realtime" if checked else "batch"
        self._lbl_mode_hint.setText(
            "录音同时每段静音后自动识别，结果实时流式输出" if checked
            else "默认模式：录完全部后统一识别，准确率更高"
        )
        self.changed.emit()

    def _download_model(self):
        size = self.cfg["model_size"]
        if check_downloaded(size):
            QMessageBox.information(self, "提示", f"「{size}」已下载，无需重复下载。"); return
        self._btn_download.setEnabled(False); self._btn_download.setText("⏳ 下载中…")
        self._set_model_status("⏳ 下载中…", "statusWarn")
        self._dl = DownloadThread(size)
        p = self.parent()
        self._dl.progress.connect(lambda t: p.statusBar().showMessage(t) if p else None)
        self._dl.done.connect(self._on_download_done); self._dl.start()

    def _on_download_done(self, ok, msg):
        self._btn_download.setEnabled(True); self._btn_download.setText("☁ 下载")
        p = self.parent()
        if p:
            if ok:  p.statusBar().showMessage(f"✅ 「{msg}」下载完成！", 4000)
            else:   p.statusBar().showMessage(f"❌ 下载失败：{msg}", 0)
        self._refresh_status()

    def _import_model(self):
        path = QFileDialog.getExistingDirectory(self, "选择本地模型文件夹")
        if not path: return
        if not any(f in os.listdir(path) for f in ["config.json","model.bin","tokenizer.json","vocabulary.txt"]):
            QMessageBox.warning(self, "格式不符",
                "所选文件夹不像 Whisper 模型目录。\n请选择含有 config.json / model.bin 等文件的文件夹。")
            return
        self.cfg["custom_path"] = path
        self._update_path_ui(); self._refresh_status()

    def _clear_path(self):
        self.cfg["custom_path"] = None
        self._update_path_ui(); self._refresh_status()


# ── 主窗口 ────────────────────────────────────────────────
class MainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("飞飞转录")
        self.resize(680, 600); self.setMinimumSize(560, 480)

        self._cfg = {
            "model_size":  "small",
            "quality_key": QUALITY_KEYS[1],
            "custom_path": None,
            "mode":        "batch",      # 默认：录完整转；"realtime" = 边录边转
        }
        self._recording  = False
        self._rec_stream = None
        self._rec_pa     = None   # 与 _rec_stream 配套的 PyAudio 实例
        self._rec_frames = []
        self._chunk_no   = 0
        self._worker     = None
        self._full_th    = None
        self._last_text  = ""

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._update_record_btn)

        self._build_ui(); self._update_status_bar()

    # ─── 界面 ─────────────────────────────────────────────
    def _build_ui(self):
        mb = QMenuBar(self); self.setMenuBar(mb)
        file_menu = QMenu("文件", self)
        act_import = QAction("导入音视频…", self); act_import.setShortcut("Ctrl+O")
        act_import.triggered.connect(self._select_file)
        act_quit = QAction("退出", self); act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_import); file_menu.addSeparator(); file_menu.addAction(act_quit)
        settings_menu = QMenu("设置", self)
        act_prefs = QAction("偏好设置…", self); act_prefs.setShortcut("Ctrl+,")
        act_prefs.triggered.connect(self._open_settings)
        settings_menu.addAction(act_prefs)
        mb.addMenu(file_menu); mb.addMenu(settings_menu)

        central = QWidget(); central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16); root.setSpacing(12)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel("🐦 飞飞转录"); title.setObjectName("titleLabel")
        sub   = QLabel("本地离线语音转录"); sub.setObjectName("subtitleLabel")
        btn_settings = QPushButton("⚙ 设置"); btn_settings.setObjectName("btnAction")
        btn_settings.setFixedHeight(28); btn_settings.clicked.connect(self._open_settings)
        btn_clear = QPushButton("清空"); btn_clear.setObjectName("btnAction")
        btn_clear.setFixedHeight(28); btn_clear.clicked.connect(self._clear_transcript)
        vt = QVBoxLayout(); vt.setSpacing(2)
        vt.addWidget(title); vt.addWidget(sub)
        header.addLayout(vt); header.addStretch()
        header.addWidget(btn_settings); header.addWidget(btn_clear)
        root.addLayout(header)

        # 操作按钮行
        row = QHBoxLayout(); row.setSpacing(10)
        self._btn_record = QPushButton("🎙  开始录音识别"); self._btn_record.setObjectName("btnPrimary")
        self._btn_record.setFixedHeight(44)
        self._btn_record.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_record.clicked.connect(self._toggle_record)
        self._btn_file = QPushButton("🎬  导入音视频"); self._btn_file.setObjectName("btnSecondary")
        self._btn_file.setFixedHeight(44)
        self._btn_file.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_file.clicked.connect(self._select_file)
        self._btn_copy = QPushButton("📋  复制"); self._btn_copy.setObjectName("btnSecondary")
        self._btn_copy.setFixedSize(90, 44); self._btn_copy.clicked.connect(self._copy_text)
        row.addWidget(self._btn_record); row.addWidget(self._btn_file); row.addWidget(self._btn_copy)
        root.addLayout(row)

        # 转录文本区（纯正文，无日志混入）
        self._transcript = QTextEdit()
        self._transcript.setObjectName("transcript")
        self._transcript.setReadOnly(False)
        self._transcript.setPlaceholderText(
            "转录内容将在这里显示\n\n"
            "录音时每段语音识别完成后实时追加；\n"
            "导入音视频后逐句输出。\n\n"
            "通过「⚙ 设置」选择模型和识别质量。"
        )
        root.addWidget(self._transcript)

        # 状态栏
        sb = QStatusBar(); self.setStatusBar(sb)
        self._lbl_sb_model   = QLabel(); sb.addWidget(self._lbl_sb_model)
        self._lbl_sb_sep1    = QLabel("·"); sb.addWidget(self._lbl_sb_sep1)
        self._lbl_sb_quality = QLabel(); sb.addWidget(self._lbl_sb_quality)
        self._lbl_sb_sep2    = QLabel("·"); sb.addWidget(self._lbl_sb_sep2)
        self._lbl_sb_status  = QLabel(); sb.addWidget(self._lbl_sb_status)

    # ─── 设置 / 状态栏 ────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(self, self._cfg)
        dlg.changed.connect(self._update_status_bar)
        dlg.exec(); self._update_status_bar()

    def _update_status_bar(self):
        size = self._cfg["model_size"]
        ok   = bool(self._cfg.get("custom_path")) or check_downloaded(size)
        mode_label = "⚡ 边录边转" if self._cfg.get("mode") == "realtime" else "📼 录完整转"
        self._lbl_sb_model.setText(f"模型：{size}{'  ✓' if check_downloaded(size) else ''}")
        self._lbl_sb_quality.setText(f"质量：{self._cfg['quality_key']}")
        self._lbl_sb_sep2.setText("·")
        if self._cfg.get("custom_path"):  self._lbl_sb_status.setText(f"本地模型  ·  {mode_label}")
        elif ok:                          self._lbl_sb_status.setText(f"✅ 就绪  ·  {mode_label}")
        else:                             self._lbl_sb_status.setText(f"❌ 未下载  ·  {mode_label}")

    # ─── 当前参数 ─────────────────────────────────────────
    def _get_model(self):
        return self._cfg.get("custom_path") or self._cfg["model_size"]

    def _get_preset(self):
        return QUALITY_PRESETS[self._cfg["quality_key"]]

    # ─── 录音 ─────────────────────────────────────────────
    def _toggle_record(self):
        self._start_recording() if not self._recording else self._stop_recording()

    def _start_recording(self):
        self._recording = True
        self._rec_frames = []; self._chunk_no = 0; self._last_text = ""

        self._rec_pa = pyaudio.PyAudio()
        self._rec_stream = self._rec_pa.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK
        )
        self._blink_timer.start(500)
        self._btn_record.setObjectName("btnRecord"); polish(self._btn_record)

        if self._cfg["mode"] == "realtime":
            # 边录边转：启动持久化 worker，静音自动切段
            self._worker = TranscribeWorker(self._get_model(), self._get_preset())
            self._worker.ready.connect(lambda: self.statusBar().showMessage("模型已就绪，开始识别…", 3000))
            self._worker.segment.connect(self._on_segment)
            self._worker.chunk_end.connect(lambda _: None)
            self._worker.all_done.connect(lambda: self.statusBar().showMessage("✅ 识别完成，模型已释放", 4000))
            self._worker.error.connect(lambda e: self.statusBar().showMessage(f"❌ {e}", 0))
            self._worker.finished.connect(self._cleanup_worker)
            self._worker.start()
            self._btn_record.setText("⏹  ● 录音中  0s / 最多 30s")
            self.statusBar().showMessage("模型加载中，请稍候…")
        else:
            # 录完整转：只录音，停止后统一转录
            self._btn_record.setText("⏹  ● 录音中  0s")
            self.statusBar().showMessage("录音中，停止后开始转录…")

        self._record_loop()

    def _stop_recording(self):
        self._recording = False; self._blink_timer.stop()
        self._rec_stream.stop_stream(); self._rec_stream.close()
        if self._rec_pa:
            self._rec_pa.terminate(); self._rec_pa = None

        self._btn_record.setObjectName("btnPrimary"); polish(self._btn_record)
        self._btn_record.setText("🎙  开始录音识别")

        if self._cfg["mode"] == "realtime":
            if self._rec_frames: self._flush_chunk(final=True)
            self._worker.stop()
            self.statusBar().showMessage("录音结束，等待最后识别完成…")
        else:
            # 批量模式：把全部帧保存为一个 WAV 整体提交
            if not self._rec_frames:
                self.statusBar().showMessage("没有录到音频", 3000); return
            frames = self._rec_frames[:]; self._rec_frames = []
            duration = len(frames) * CHUNK / RATE
            # 检查录音电平，确认麦克风权限是否正常
            raw = b"".join(frames)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0
            log.info("Stop recording: %d frames, %.1fs, RMS=%.1f, model=%s",
                     len(frames), duration, rms, self._get_model())
            if rms < 50:
                self.statusBar().showMessage("⚠️ 录音电平极低，请检查麦克风权限（系统设置→隐私→麦克风）", 0)
                QMessageBox.warning(self, "麦克风静音",
                    "录音电平过低（可能是麦克风权限未授权）。\n\n"
                    "请前往：系统设置 → 隐私与安全性 → 麦克风\n"
                    "找到「飞飞转录」并开启权限，然后重新录音。")
                return
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close(); save_wav(frames, tmp.name)
            log.info("WAV saved to %s (RMS=%.1f)", tmp.name, rms)
            self._insert_chunk_label(1, duration, "完整录音")
            self.statusBar().showMessage(f"正在转录全部录音（{duration:.0f}s）…")
            self._full_th = FullTranscribeThread(tmp.name, self._get_model(), self._get_preset())
            self._full_th.segment.connect(self._on_segment_batch)
            self._full_th.error.connect(self._on_transcribe_error)
            self._full_th.done.connect(self._on_full_done)
            self._full_th.finished.connect(self._cleanup_full_th)
            self._full_th.start()

    def _record_loop(self):
        if not self._recording: return
        self._rec_frames.append(self._rec_stream.read(CHUNK, exception_on_overflow=False))
        if self._cfg["mode"] == "realtime":
            n = len(self._rec_frames)
            if n >= CHUNK_MAX_FRAMES:
                self._flush_chunk()
            elif n >= CHUNK_MIN_FRAMES and n % 5 == 0:
                if self._is_silence(self._rec_frames[-SILENCE_MIN_FRAMES:]):
                    self._flush_chunk()
        QTimer.singleShot(10, self._record_loop)

    @staticmethod
    def _is_silence(frames):
        data    = b"".join(frames)
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        rms     = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0
        return rms < SILENCE_RMS_THRESH

    def _flush_chunk(self, final=False):
        if not self._rec_frames: return
        frames = self._rec_frames[:]; self._rec_frames = []
        self._chunk_no += 1; n = self._chunk_no
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close(); save_wav(frames, tmp.name)
        duration = len(frames) * CHUNK / RATE
        trigger  = "尾段" if final else ("静音切断" if duration < 28 else "超时切断")

        # 在转录区插入分段标签
        self._insert_chunk_label(n, duration, trigger)
        self.statusBar().showMessage(f"识别第 {n} 段（{duration:.1f}s）…")

        ctx = self._last_text[-80:] if self._last_text else None
        self._worker.submit(tmp.name, n, ctx_prompt=ctx)

    def _insert_chunk_label(self, chunk_no, duration, trigger):
        """在转录区插入浅灰分段标签，与正文视觉分层"""
        cur = self._transcript.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)

        if chunk_no > 1:
            # 段落间距：插入带 topMargin 的空块
            spacer_blk = QTextBlockFormat()
            spacer_blk.setTopMargin(18)
            cur.insertBlock(spacer_blk)
            cur.insertText("")   # 确保空行存在

        # 标签行
        cur.insertBlock(_blk_label())
        cur.insertText(f"第 {chunk_no} 段  ·  {duration:.0f}s  ·  {trigger}", _fmt_label())

        # 正文起始行
        cur.insertBlock(_blk_body())
        self._transcript.setTextCursor(cur)

    def _on_segment(self, _no, text):
        """流式追加识别句子到正文段落"""
        self._last_text = text
        cur = self._transcript.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.setCharFormat(_fmt_body())
        cur.insertText(text + "\n")
        self._transcript.setTextCursor(cur)
        self._transcript.ensureCursorVisible()

    def _on_segment_batch(self, text):
        """批量模式逐句流式输出"""
        self._last_text = text
        cur = self._transcript.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.setCharFormat(_fmt_body())
        cur.insertText(text + "\n")
        self._transcript.setTextCursor(cur)
        self._transcript.ensureCursorVisible()

    def _on_transcribe_error(self, msg):
        """转录失败时弹窗 + 状态栏双重提示，确保用户能看到"""
        log.error("Transcribe error: %s", msg)
        self.statusBar().showMessage(f"❌ 转录失败：{msg}", 0)
        QMessageBox.critical(self, "转录失败", f"{msg}\n\n详细日志：~/Library/Logs/飞飞转录/app.log")

    def _on_full_done(self, wav_path):
        try: os.remove(wav_path)
        except OSError: pass
        self.statusBar().showMessage("✅ 转录完成，模型已释放", 4000)

    def _cleanup_full_th(self):
        # finished 信号触发时线程已退出 run()，直接解除引用即可；
        # 不在此处调用 wait()，避免在 finished 槽里阻塞主线程引发死锁
        if self._full_th:
            self._full_th.deleteLater(); self._full_th = None

    def _cleanup_worker(self):
        if self._worker:
            self._worker.deleteLater(); self._worker = None

    def _update_record_btn(self):
        sec = int(len(self._rec_frames) * CHUNK / RATE)
        if self._cfg["mode"] == "realtime":
            self._btn_record.setText(f"⏹  ● 录音中  {sec}s / 最多 30s")
        else:
            self._btn_record.setText(f"⏹  ● 录音中  {sec}s")

    # ─── 导入字幕 ─────────────────────────────────────────
    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音视频文件", "",
            "音视频文件 (*.mp3 *.wav *.m4a *.mp4 *.mov *.flv *.aac *.ogg)"
        )
        if not path: return
        self.statusBar().showMessage(f"正在处理：{os.path.basename(path)}…")
        self._srt_th = SrtThread(path, self._get_model(), self._get_preset())
        self._srt_th.result.connect(self._on_srt_done)
        self._srt_th.start()

    def _on_srt_done(self, result):
        if result.startswith("ERROR:"):
            self.statusBar().showMessage(f"❌ 生成失败：{result[6:]}", 0)
        else:
            self.statusBar().showMessage(f"✅ 字幕已保存：{result}", 6000)
            # 在转录区追加完成提示
            cur = self._transcript.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            tip_fmt = QTextCharFormat()
            tip_fmt.setForeground(QColor("#34C759")); tip_fmt.setFontPointSize(12)
            cur.insertBlock(_blk_label())
            cur.insertText(f"✅ 字幕已保存：{result}", tip_fmt)
            cur.insertBlock(_blk_body())
            self._transcript.setTextCursor(cur)

    # ─── 清空 / 复制 ──────────────────────────────────────
    def _clear_transcript(self):
        self._transcript.clear()

    def _copy_text(self):
        text = self._transcript.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "转录内容为空，没有可复制的内容。"); return
        QApplication.clipboard().setText(text)
        orig = self._btn_copy.text(); self._btn_copy.setText("✅ 已复制")
        QTimer.singleShot(1500, lambda: self._btn_copy.setText(orig))

    # ─── 关闭保护 ─────────────────────────────────────────
    def closeEvent(self, event):
        if self._recording:
            self._recording = False; self._blink_timer.stop()
            try: self._rec_stream.stop_stream(); self._rec_stream.close()
            except Exception: pass
            try:
                if self._rec_pa: self._rec_pa.terminate()
            except Exception: pass
            self._rec_pa = None
        if self._worker and self._worker.isRunning():
            self._worker.stop(); self._worker.wait(5000)
        if self._full_th and self._full_th.isRunning():
            self._full_th.wait(5000)
        event.accept()


# ── 入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    # macOS frozen .app：必须最先调用，防止 ctranslate2/OpenMP 内部 spawn
    # 子进程时重新执行 .app 可执行文件，导致弹出第二个窗口
    multiprocessing.freeze_support()

    os.makedirs(USER_MODEL_ROOT, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWin()
    win.show()
    sys.exit(app.exec())
