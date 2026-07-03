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
    QComboBox,
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QTextBlockFormat, QColor, QAction, QFont
from faster_whisper import WhisperModel

# ── 路径 ─────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
BUNDLED_MODEL_ROOT = os.path.join(_BASE, "whisper_models")

USER_MODEL_ROOT = os.path.expanduser(
    "~/Library/Application Support/飞飞转录/whisper_models"
)
CHUNK, FORMAT, CHANNELS, RATE = 1024, pyaudio.paInt16, 1, 16000

SILENCE_RMS_THRESH = 300
SILENCE_MIN_FRAMES = int(1.5 * RATE / CHUNK)
CHUNK_MIN_FRAMES   = int(8  * RATE / CHUNK)
CHUNK_MAX_FRAMES   = int(30 * RATE / CHUNK)

MODEL_SIZES  = ["tiny", "base", "small", "medium", "large-v3"]
# 侧边栏 pill 显示标签（large-v3 缩短为 large）
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
QUALITY_KEYS  = list(QUALITY_PRESETS.keys())
QUALITY_HINTS = {
    QUALITY_KEYS[0]: "int8 · beam 3 · 快",
    QUALITY_KEYS[1]: "int8_float32 · beam 5 · 均衡",
    QUALITY_KEYS[2]: "float32 · beam 10 · 准（较慢）",
}

# ── WorkBuddy 色彩 Token ──────────────────────────────────
COLORS = {
    "bg_primary":       "#000000",
    "bg_secondary":     "#1c1c1e",
    "bg_card":          "#1a1a1a",
    "bg_hover":         "#2a2a2a",
    "border_default":   "#2e2e33",
    "text_primary":     "#e5e5e5",
    "text_secondary":   "#a3a3a3",
    "text_tertiary":    "#7c7c82",
    "accent_blue":      "#60a5fa",
    "accent_green":     "#4ade80",
    "accent_red":       "#f87171",
    "accent_yellow":    "#fbbf24",
    "accent_purple":    "#8b7dff",
}

# ── 样式表 ────────────────────────────────────────────────
STYLE = """
/* ── 全局 ─────────────────────────────────── */
* {
    font-family: -apple-system, "PingFang SC", "Hiragino Sans GB",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #e5e5e5;
    outline: none;
}
QMainWindow, QDialog { background: #000000; }

/* ── 菜单栏 ──────────────────────────────── */
QMenuBar {
    background: #1c1c1e;
    border-bottom: 1px solid #2e2e33;
    padding: 2px 4px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 6px; color: #a3a3a3; }
QMenuBar::item:selected { background: #2a2a2a; color: #e5e5e5; }
QMenu {
    background: #1a1a1a;
    border: 1px solid #2e2e33;
    border-radius: 10px;
    padding: 4px;
}
QMenu::item { padding: 7px 20px; border-radius: 6px; color: #e5e5e5; }
QMenu::item:selected { background: #2a2a2a; }
QMenu::separator { height: 1px; background: #2e2e33; margin: 4px 8px; }

/* ── 侧边栏 ──────────────────────────────── */
#sidebar {
    background: #1c1c1e;
    border-right: 1px solid #2e2e33;
}
#sidebarBrand {
    font-family: "Poppins", -apple-system, sans-serif;
    font-size: 16px; font-weight: 600;
    color: #e5e5e5;
}
#sectionTitle {
    font-size: 11px; font-weight: 600;
    color: #7c7c82;
    letter-spacing: 0.06em;
    padding: 12px 12px 4px;
}
#sidebarFooterLabel {
    font-size: 12px;
    color: #7c7c82;
}
#btnAdvanced {
    background: transparent;
    border: none;
    color: #7c7c82;
    font-size: 11px;
    text-align: left;
    padding: 0;
}
#btnAdvanced:hover { color: #a3a3a3; }

/* ── Pill 按钮 ───────────────────────────── */
#pillBtn {
    background: transparent;
    border: 1px solid #2e2e33;
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 12px;
    color: #7c7c82;
}
#pillBtn:checked {
    background: rgba(96,165,250,0.15);
    border-color: #60a5fa;
    color: #60a5fa;
    font-weight: 600;
}
#pillBtn:hover:!checked { border-color: #3f3f46; color: #a3a3a3; }
#pillBtn:disabled { color: #555558; border-color: #252525; }

/* ── 主 CTA：录音按钮 ─────────────────────── */
#btnRecord {
    background: #60a5fa;
    color: #000000;
    border: none;
    border-radius: 10px;
    padding: 10px 0;
    font-size: 14px; font-weight: 600;
}
#btnRecord:hover { background: #93c5fd; }
#btnRecord:disabled { background: #1e1e20; color: #555558; }
#btnRecording {
    background: rgba(248,113,113,0.15);
    color: #f87171;
    border: 1px solid #f87171;
    border-radius: 10px;
    padding: 10px 0;
    font-size: 14px; font-weight: 600;
}
#btnRecording:hover { background: rgba(248,113,113,0.25); }

/* ── 主内容区 ─────────────────────────────── */
#mainArea { background: #000000; }
#topBar {
    background: #000000;
    border-bottom: 1px solid #2e2e33;
}
#topBarTitle { font-size: 14px; font-weight: 600; color: #e5e5e5; }

/* ── 转录卡片 ─────────────────────────────── */
#transcriptCard {
    background: #1a1a1a;
    border: 1px solid #2e2e33;
    border-radius: 12px;
}
#transcript {
    background: transparent;
    border: none;
    color: #e5e5e5;
    selection-background-color: rgba(96,165,250,0.25);
}

/* ── 底部工具栏 ──────────────────────────── */
#bottomToolbar { background: #000000; }
#tbLabel {
    font-size: 10px; font-weight: 600;
    color: #7c7c82; letter-spacing: 0.08em;
    padding: 0;
}

/* ── 工具栏下拉选择器 ────────────────────── */
QComboBox#tbCombo {
    background: #1a1a1a;
    border: 1px solid #2e2e33;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    color: #e5e5e5;
    min-width: 90px;
}
QComboBox#tbCombo:hover { border-color: #3f3f46; }
QComboBox#tbCombo:focus { border-color: #60a5fa; }
QComboBox#tbCombo:disabled { color: #555558; border-color: #252525; }
QComboBox#tbCombo::drop-down { border: none; width: 20px; }
QComboBox#tbCombo::down-arrow {
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #7c7c82;
    margin-right: 6px;
}
QComboBox#tbCombo QAbstractItemView {
    background: #1c1c1e;
    border: 1px solid #2e2e33;
    border-radius: 8px;
    padding: 4px;
    color: #e5e5e5;
    selection-background-color: rgba(96,165,250,0.2);
    selection-color: #60a5fa;
    outline: none;
}
QComboBox#tbCombo QAbstractItemView::item {
    padding: 5px 10px;
    border-radius: 4px;
    min-height: 22px;
}

/* ── 侧边栏宽度缩小 ──────────────────────── */
#sidebar { min-width: 160px; max-width: 160px; }

/* ── 操作按钮（次要）─────────────────────── */
#btnAction {
    background: #1a1a1a;
    color: #a3a3a3;
    border: 1px solid #2e2e33;
    border-radius: 8px;
    padding: 5px 14px;
    font-size: 12px;
}
#btnAction:hover { background: #2a2a2a; color: #e5e5e5; border-color: #3f3f46; }
#btnAction:disabled { color: #555558; border-color: #1e1e20; background: #111111; }

/* 危险操作按钮 */
#btnActionDanger {
    background: transparent;
    color: #f87171;
    border: 1px solid rgba(248,113,113,0.3);
    border-radius: 8px;
    padding: 5px 14px;
    font-size: 12px;
}
#btnActionDanger:hover { background: rgba(248,113,113,0.1); border-color: #f87171; }

/* ── 状态栏 ──────────────────────────────── */
QStatusBar {
    background: #1c1c1e;
    border-top: 1px solid #2e2e33;
    font-size: 12px;
    color: #7c7c82;
}
QStatusBar::item { border: none; }

/* ── 滚动条 ──────────────────────────────── */
QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 2px; }
QScrollBar::handle:vertical {
    background: rgba(255,255,255,0.12);
    border-radius: 3px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.2); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

/* ── 对话框 ──────────────────────────────── */
QDialog { background: #000000; }
#dialogCard {
    background: #1a1a1a;
    border: 1px solid #2e2e33;
    border-radius: 12px;
}
#pathLabel  { color: #7c7c82; font-size: 12px; }
#statusOk   { color: #4ade80; font-size: 12px; }
#statusError { color: #f87171; font-size: 12px; }
#statusWarn  { color: #fbbf24; font-size: 12px; }

/* ── 分割线 ──────────────────────────────── */
#divider { background: #2e2e33; max-height: 1px; min-height: 1px; }
"""

# ── 文本格式 ──────────────────────────────────────────────
def _fmt_label():
    """分段标签：WorkBuddy text-tertiary"""
    f = QTextCharFormat()
    f.setForeground(QColor("#7c7c82"))
    f.setFontPointSize(11)
    return f

def _fmt_body():
    """正文：WorkBuddy text-primary"""
    f = QTextCharFormat()
    f.setForeground(QColor("#e5e5e5"))
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
    return USER_MODEL_ROOT

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
    result = pyqtSignal(str)
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
    done    = pyqtSignal(str)
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


# ── 设置对话框（简化版：只保留模型管理）────────────────────
class SettingsDialog(QDialog):
    changed = pyqtSignal()

    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("模型管理")
        self.setModal(True); self.setFixedWidth(440)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui(); self._refresh_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20); layout.setSpacing(16)

        # 对话框标题
        title = QLabel("模型管理"); title.setObjectName("topBarTitle")
        layout.addWidget(title)

        # 模型卡片
        card = QFrame(); card.setObjectName("dialogCard")
        cl = QVBoxLayout(card); cl.setContentsMargins(16, 14, 16, 14); cl.setSpacing(10)

        # 区段标题
        lbl_sel = QLabel("选择模型"); lbl_sel.setObjectName("sectionTitle")
        lbl_sel.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(lbl_sel)

        # 模型 pill 按钮组（两行）
        self._model_group = QButtonGroup(self); self._model_group.setExclusive(True)
        self._model_btns  = {}
        for sizes_row in [["tiny", "base", "small"], ["medium", "large-v3"]]:
            row = QHBoxLayout(); row.setSpacing(4)
            for size in sizes_row:
                b = QPushButton(MODEL_LABELS[size]); b.setObjectName("pillBtn")
                b.setCheckable(True); b.clicked.connect(self._on_model_changed)
                self._model_group.addButton(b)
                self._model_btns[size] = b; row.addWidget(b)
            row.addStretch(); cl.addLayout(row)
        self._model_btns[self.cfg["model_size"]].setChecked(True)

        # 状态行
        row_status = QHBoxLayout(); row_status.setSpacing(8)
        self._lbl_model_status = QLabel()
        row_status.addWidget(self._lbl_model_status); row_status.addStretch()
        cl.addLayout(row_status)

        # 操作按钮行
        row_dl = QHBoxLayout(); row_dl.setSpacing(6)
        self._btn_download = QPushButton("☁  下载模型"); self._btn_download.setObjectName("btnAction")
        self._btn_download.setFixedHeight(30); self._btn_download.clicked.connect(self._download_model)
        self._btn_import = QPushButton("📂  本地导入"); self._btn_import.setObjectName("btnAction")
        self._btn_import.setFixedHeight(30); self._btn_import.clicked.connect(self._import_model)
        self._btn_clear = QPushButton("清除路径"); self._btn_clear.setObjectName("btnActionDanger")
        self._btn_clear.setFixedHeight(30); self._btn_clear.clicked.connect(self._clear_path)
        row_dl.addWidget(self._btn_download); row_dl.addWidget(self._btn_import)
        row_dl.addWidget(self._btn_clear); row_dl.addStretch()
        cl.addLayout(row_dl)

        # 路径标签
        self._lbl_path = QLabel(); self._lbl_path.setObjectName("pathLabel")
        self._lbl_path.setWordWrap(True); cl.addWidget(self._lbl_path)

        layout.addWidget(card)

        # 完成按钮
        row_done = QHBoxLayout(); row_done.addStretch()
        btn_done = QPushButton("完成"); btn_done.setObjectName("btnRecord")
        btn_done.setFixedSize(100, 34); btn_done.clicked.connect(self.accept)
        row_done.addWidget(btn_done); layout.addLayout(row_done)

        self._update_path_ui()

    def _refresh_status(self):
        self._update_model_pills()
        size = self.cfg["model_size"]
        if self.cfg.get("custom_path"):
            self._set_model_status("📂 本地模型", "statusWarn")
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
            base = MODEL_LABELS[size]
            btn.setText(f"{base} ✓" if check_downloaded(size) else base)

    def _update_path_ui(self):
        p = self.cfg.get("custom_path")
        if p:
            self._lbl_path.setText(f"路径：{p if len(p) <= 55 else '…' + p[-52:]}")
            self._btn_clear.show()
        else:
            self._lbl_path.clear(); self._btn_clear.hide()

    def _on_model_changed(self):
        self.cfg["model_size"] = next(s for s, b in self._model_btns.items() if b.isChecked())
        self.cfg["custom_path"] = None
        self._update_path_ui(); self._refresh_status()

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
        self._btn_download.setEnabled(True); self._btn_download.setText("☁  下载模型")
        p = self.parent()
        if p:
            if ok:  p.statusBar().showMessage(f"✅ 「{msg}」下载完成！", 4000)
            else:   p.statusBar().showMessage(f"❌ 下载失败：{msg}", 0)
        self._refresh_status()

    def _import_model(self):
        path = QFileDialog.getExistingDirectory(self, "选择本地模型文件夹")
        if not path: return
        if not any(f in os.listdir(path) for f in ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]):
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
        self.resize(900, 640); self.setMinimumSize(720, 520)

        self._cfg = {
            "model_size":  "small",
            "quality_key": QUALITY_KEYS[1],
            "custom_path": None,
            "mode":        "batch",
        }
        self._recording  = False
        self._rec_stream = None
        self._rec_pa     = None
        self._rec_frames = []
        self._chunk_no   = 0
        self._worker     = None
        self._full_th    = None
        self._last_text  = ""

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._update_record_btn)

        self._build_ui()
        self._update_sidebar_pills()
        self._update_status_bar()

    # ─── 界面构建 ─────────────────────────────────────────

    def _build_ui(self):
        # 菜单栏（只保留文件菜单）
        mb = QMenuBar(self); self.setMenuBar(mb)
        file_menu = QMenu("文件", self)
        act_import = QAction("导入音视频…", self); act_import.setShortcut("Ctrl+O")
        act_import.triggered.connect(self._select_file)
        act_quit = QAction("退出", self); act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_import); file_menu.addSeparator(); file_menu.addAction(act_quit)
        mb.addMenu(file_menu)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main_area())

        # 状态栏
        sb = QStatusBar(); self.setStatusBar(sb)
        self._lbl_sb_model   = QLabel(); sb.addWidget(self._lbl_sb_model)
        self._lbl_sb_sep1    = QLabel("·"); sb.addWidget(self._lbl_sb_sep1)
        self._lbl_sb_quality = QLabel(); sb.addWidget(self._lbl_sb_quality)
        self._lbl_sb_sep2    = QLabel("·"); sb.addWidget(self._lbl_sb_sep2)
        self._lbl_sb_status  = QLabel(); sb.addWidget(self._lbl_sb_status)

    def _build_sidebar(self):
        sidebar = QWidget(); sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        # 1. 品牌头部
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 16, 14, 16); hl.setSpacing(8)
        logo = QLabel("🐦"); logo.setFixedSize(26, 26)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand = QLabel("飞飞转录"); brand.setObjectName("sidebarBrand")
        hl.addWidget(logo); hl.addWidget(brand); hl.addStretch()
        layout.addWidget(header)
        layout.addWidget(self._make_divider())

        # 弹性空间
        layout.addStretch()
        layout.addWidget(self._make_divider())

        # 2. 底部状态 + 高级设置入口
        footer = QWidget()
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(12, 8, 12, 12); fl.setSpacing(4)
        self._lbl_sidebar_status = QLabel()
        self._lbl_sidebar_status.setObjectName("sidebarFooterLabel")
        fl.addWidget(self._lbl_sidebar_status)
        btn_adv = QPushButton("⚙  高级 · 下载模型")
        btn_adv.setObjectName("btnAdvanced")
        btn_adv.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_adv.clicked.connect(self._open_settings)
        fl.addWidget(btn_adv)
        layout.addWidget(footer)

        return sidebar

    def _build_main_area(self):
        main = QWidget(); main.setObjectName("mainArea")
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        # Top bar（固定 48px）
        topbar = QWidget(); topbar.setObjectName("topBar")
        topbar.setFixedHeight(48)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(20, 0, 16, 0); tbl.setSpacing(8)
        title = QLabel("转录结果"); title.setObjectName("topBarTitle")
        tbl.addWidget(title); tbl.addStretch()

        self._btn_clear = QPushButton("清空"); self._btn_clear.setObjectName("btnAction")
        self._btn_clear.setFixedHeight(30); self._btn_clear.clicked.connect(self._clear_transcript)
        self._btn_copy = QPushButton("📋  复制"); self._btn_copy.setObjectName("btnAction")
        self._btn_copy.setFixedHeight(30); self._btn_copy.clicked.connect(self._copy_text)
        self._btn_file = QPushButton("🎬  文件"); self._btn_file.setObjectName("btnAction")
        self._btn_file.setFixedHeight(30); self._btn_file.clicked.connect(self._select_file)
        tbl.addWidget(self._btn_clear); tbl.addWidget(self._btn_copy); tbl.addWidget(self._btn_file)
        layout.addWidget(topbar)
        layout.addWidget(self._make_divider())

        # 转录卡片（带外边距）
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 16, 16, 16)
        card = QFrame(); card.setObjectName("transcriptCard")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(16, 16, 16, 16)
        self._transcript = QTextEdit()
        self._transcript.setObjectName("transcript")
        self._transcript.setReadOnly(False)
        self._transcript.setPlaceholderText(
            "转录内容将在这里显示\n\n"
            "点击下方「🎙 开始录音识别」开始录音；\n"
            "或点击右上角「🎬 文件」导入音视频。"
        )
        card_l.addWidget(self._transcript)
        cl.addWidget(card)
        layout.addWidget(content)

        # ── 底部工具栏（下拉选择器 + 录音按钮）──────────────────
        layout.addWidget(self._make_divider())
        toolbar = QWidget(); toolbar.setObjectName("bottomToolbar")
        tbl = QHBoxLayout(toolbar)
        tbl.setContentsMargins(20, 10, 16, 12); tbl.setSpacing(0)

        def _tb_label(text):
            l = QLabel(text); l.setObjectName("tbLabel"); return l

        def _tb_combo():
            c = QComboBox(); c.setObjectName("tbCombo"); return c

        # MODEL 下拉
        model_grp = QWidget()
        mgl = QVBoxLayout(model_grp)
        mgl.setContentsMargins(0, 0, 0, 0); mgl.setSpacing(5)
        mgl.addWidget(_tb_label("模型"))
        self._combo_model = _tb_combo()
        for size in MODEL_SIZES:
            base = MODEL_LABELS[size]
            label = f"{base} ✓" if check_downloaded(size) else base
            self._combo_model.addItem(label)
        self._combo_model.setCurrentIndex(MODEL_SIZES.index(self._cfg["model_size"]))
        self._combo_model.currentIndexChanged.connect(self._on_combo_model_changed)
        mgl.addWidget(self._combo_model)
        tbl.addWidget(model_grp)

        tbl.addSpacing(12)

        # QUALITY 下拉
        qual_grp = QWidget()
        qgl = QVBoxLayout(qual_grp)
        qgl.setContentsMargins(0, 0, 0, 0); qgl.setSpacing(5)
        qgl.addWidget(_tb_label("质量"))
        self._combo_quality = _tb_combo()
        for key in QUALITY_KEYS:
            self._combo_quality.addItem(key)
        self._combo_quality.setCurrentIndex(QUALITY_KEYS.index(self._cfg["quality_key"]))
        self._combo_quality.currentIndexChanged.connect(self._on_combo_quality_changed)
        qgl.addWidget(self._combo_quality)
        tbl.addWidget(qual_grp)

        tbl.addSpacing(12)

        # MODE 下拉
        self._mode_keys = ["batch", "realtime"]
        mode_grp = QWidget()
        mogl = QVBoxLayout(mode_grp)
        mogl.setContentsMargins(0, 0, 0, 0); mogl.setSpacing(5)
        mogl.addWidget(_tb_label("模式"))
        self._combo_mode = _tb_combo()
        for label in ["📼 整段", "⚡ 实时"]:
            self._combo_mode.addItem(label)
        cur_mode = self._cfg.get("mode", "batch")
        self._combo_mode.setCurrentIndex(self._mode_keys.index(cur_mode))
        self._combo_mode.currentIndexChanged.connect(self._on_combo_mode_changed)
        mogl.addWidget(self._combo_mode)
        tbl.addWidget(mode_grp)

        # ── 弹性 + 录音按钮 ───────────────────────────────────
        tbl.addStretch()
        self._btn_record = QPushButton("🎙  开始录音识别")
        self._btn_record.setObjectName("btnRecord")
        self._btn_record.setFixedHeight(42)
        self._btn_record.setFixedWidth(200)
        self._btn_record.clicked.connect(self._toggle_record)
        tbl.addWidget(self._btn_record)

        layout.addWidget(toolbar)
        return main

    # ─── 侧边栏辅助 ───────────────────────────────────────

    def _section_title(self, text):
        l = QLabel(text); l.setObjectName("sectionTitle"); return l

    def _make_divider(self):
        d = QWidget(); d.setObjectName("divider")
        d.setFixedHeight(1)
        d.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return d

    # ─── 工具栏下拉事件 ────────────────────────────────────

    def _on_combo_model_changed(self, index):
        self._cfg["model_size"] = MODEL_SIZES[index]
        self._cfg["custom_path"] = None
        self._update_status_bar()

    def _on_combo_quality_changed(self, index):
        self._cfg["quality_key"] = QUALITY_KEYS[index]
        self._update_status_bar()

    def _on_combo_mode_changed(self, index):
        self._cfg["mode"] = self._mode_keys[index]
        self._update_status_bar()

    def _update_sidebar_pills(self):
        """更新模型下拉的 ✓ 标记（下载状态变化后调用）"""
        for i, size in enumerate(MODEL_SIZES):
            base = MODEL_LABELS[size]
            self._combo_model.setItemText(i, f"{base} ✓" if check_downloaded(size) else base)

    def _set_controls_enabled(self, enabled):
        """录音期间禁用选择器"""
        self._combo_model.setEnabled(enabled)
        self._combo_quality.setEnabled(enabled)
        self._combo_mode.setEnabled(enabled)
        self._btn_file.setEnabled(enabled)

    # ─── 设置 / 状态 ──────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self, self._cfg)
        dlg.changed.connect(self._update_status_bar)
        dlg.exec()
        # 下载完成后刷新 pill 标记 + 状态
        self._update_sidebar_pills()
        self._update_status_bar()

    def _update_status_bar(self):
        size = self._cfg["model_size"]
        ok   = bool(self._cfg.get("custom_path")) or check_downloaded(size)
        mode_label = "⚡ 实时" if self._cfg.get("mode") == "realtime" else "📼 整段"
        self._lbl_sb_model.setText(f"模型：{size}{'  ✓' if check_downloaded(size) else ''}")
        self._lbl_sb_quality.setText(f"质量：{self._cfg['quality_key']}")
        if self._cfg.get("custom_path"):
            self._lbl_sb_status.setText(f"本地模型  ·  {mode_label}")
        elif ok:
            self._lbl_sb_status.setText(f"✅ 就绪  ·  {mode_label}")
        else:
            self._lbl_sb_status.setText(f"❌ 未下载  ·  {mode_label}")
        # 同步侧边栏底部状态
        self._update_sidebar_footer()

    def _update_sidebar_footer(self):
        size = self._cfg["model_size"]
        if self._cfg.get("custom_path"):
            self._lbl_sidebar_status.setText("📂 使用本地模型")
            self._lbl_sidebar_status.setObjectName("statusWarn")
        elif check_downloaded(size):
            self._lbl_sidebar_status.setText(f"✅ {size} 模型已就绪")
            self._lbl_sidebar_status.setObjectName("statusOk")
        else:
            self._lbl_sidebar_status.setText(f"❌ 模型未下载")
            self._lbl_sidebar_status.setObjectName("statusError")
        polish(self._lbl_sidebar_status)

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
        self._set_controls_enabled(False)

        self._rec_pa = pyaudio.PyAudio()
        self._rec_stream = self._rec_pa.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK
        )
        self._blink_timer.start(500)
        self._btn_record.setObjectName("btnRecording"); polish(self._btn_record)

        if self._cfg["mode"] == "realtime":
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
            self._btn_record.setText("⏹  ● 录音中  0s")
            self.statusBar().showMessage("录音中，停止后开始转录…")

        self._record_loop()

    def _stop_recording(self):
        self._recording = False; self._blink_timer.stop()
        self._rec_stream.stop_stream(); self._rec_stream.close()
        if self._rec_pa:
            self._rec_pa.terminate(); self._rec_pa = None

        self._btn_record.setObjectName("btnRecord"); polish(self._btn_record)
        self._btn_record.setText("🎙  开始录音识别")
        self._set_controls_enabled(True)

        if self._cfg["mode"] == "realtime":
            if self._rec_frames: self._flush_chunk(final=True)
            self._worker.stop()
            self.statusBar().showMessage("录音结束，等待最后识别完成…")
        else:
            if not self._rec_frames:
                self.statusBar().showMessage("没有录到音频", 3000); return
            frames = self._rec_frames[:]; self._rec_frames = []
            duration = len(frames) * CHUNK / RATE
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
        self._insert_chunk_label(n, duration, trigger)
        self.statusBar().showMessage(f"识别第 {n} 段（{duration:.1f}s）…")
        ctx = self._last_text[-80:] if self._last_text else None
        self._worker.submit(tmp.name, n, ctx_prompt=ctx)

    def _insert_chunk_label(self, chunk_no, duration, trigger):
        cur = self._transcript.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        if chunk_no > 1:
            spacer_blk = QTextBlockFormat()
            spacer_blk.setTopMargin(18)
            cur.insertBlock(spacer_blk)
            cur.insertText("")
        cur.insertBlock(_blk_label())
        cur.insertText(f"第 {chunk_no} 段  ·  {duration:.0f}s  ·  {trigger}", _fmt_label())
        cur.insertBlock(_blk_body())
        self._transcript.setTextCursor(cur)

    def _on_segment(self, _no, text):
        self._last_text = text
        cur = self._transcript.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.setCharFormat(_fmt_body())
        cur.insertText(text + "\n")
        self._transcript.setTextCursor(cur)
        self._transcript.ensureCursorVisible()

    def _on_segment_batch(self, text):
        self._last_text = text
        cur = self._transcript.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.setCharFormat(_fmt_body())
        cur.insertText(text + "\n")
        self._transcript.setTextCursor(cur)
        self._transcript.ensureCursorVisible()

    def _on_transcribe_error(self, msg):
        log.error("Transcribe error: %s", msg)
        self.statusBar().showMessage(f"❌ 转录失败：{msg}", 0)
        QMessageBox.critical(self, "转录失败", f"{msg}\n\n详细日志：~/Library/Logs/飞飞转录/app.log")

    def _on_full_done(self, wav_path):
        try: os.remove(wav_path)
        except OSError: pass
        self.statusBar().showMessage("✅ 转录完成，模型已释放", 4000)

    def _cleanup_full_th(self):
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

    # ─── 导入音视频 ───────────────────────────────────────
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
            cur = self._transcript.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            tip_fmt = QTextCharFormat()
            tip_fmt.setForeground(QColor("#4ade80")); tip_fmt.setFontPointSize(12)
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
    multiprocessing.freeze_support()
    os.makedirs(USER_MODEL_ROOT, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWin()
    win.show()
    sys.exit(app.exec())
