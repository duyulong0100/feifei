"""
飞飞转录 · 单机版
模型内置，无需服务端；录音 / 转录全在本地完成。
"""
import sys
import os
import json
import wave
import queue
import tempfile
import multiprocessing
import logging
import traceback
import pyaudio
import numpy as np

# ── 配置目录 ──────────────────────────────────────────────
_CFG_DIR  = os.path.expanduser("~/Library/Application Support/飞飞转录单机版")
_CFG_FILE = os.path.join(_CFG_DIR, "ui.json")

# ── 文件日志 ──────────────────────────────────────────────
_LOG_DIR = os.path.expanduser("~/Library/Logs/飞飞转录单机版")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(_LOG_DIR, "app.log"),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("飞飞转录单机版")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QFileDialog, QMessageBox, QLineEdit,
    QFrame, QSizePolicy, QMenuBar, QMenu, QComboBox,
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import (
    QTextCursor, QTextCharFormat, QTextBlockFormat,
    QColor, QAction, QFont, QPixmap, QIcon,
)

from config import load_config, save_config, get_quality_preset, QUALITY_KEYS, QUALITY_HINTS


# ── 资源路径 ──────────────────────────────────────────────
def _resource(name: str) -> str:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = _HERE
    return os.path.join(base, name)


# ── 录音参数 ──────────────────────────────────────────────
CHUNK, FORMAT, CHANNELS, RATE = 1024, pyaudio.paInt16, 1, 16000
SILENCE_RMS_THRESH = 300
SILENCE_MIN_FRAMES = int(1.5 * RATE / CHUNK)
CHUNK_MIN_FRAMES   = int(8  * RATE / CHUNK)
CHUNK_MAX_FRAMES   = int(30 * RATE / CHUNK)


# ══════════════════════════════════════════════════════════
#  样式表
# ══════════════════════════════════════════════════════════
STYLE_DARK = """
* {
    font-family: -apple-system, "PingFang SC", "Hiragino Sans GB",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px; color: #e8e8e8; outline: none;
}
QMainWindow, QDialog { background: #0d0d0d; }
QMenuBar {
    background: #1a1a1a; border-bottom: 1px solid #303033; padding: 2px 4px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 6px; color: #888890; }
QMenuBar::item:selected { background: #222225; color: #e8e8e8; }
QMenu {
    background: #1a1a1a; border: 1px solid #303033; border-radius: 10px; padding: 4px;
}
QMenu::item { padding: 7px 20px; border-radius: 6px; color: #e8e8e8; }
QMenu::item:selected { background: #222225; }
QMenu::separator { height: 1px; background: #303033; margin: 4px 8px; }
#topBar  { background: #1a1a1a; border-bottom: 1px solid #303033; }
#brand   { font-size: 15px; font-weight: 600; color: #e8e8e8; }
#iconBtn {
    background: transparent; border: none; border-radius: 7px;
    font-size: 16px; color: #888890;
    min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
}
#iconBtn:hover { background: #222225; color: #e8e8e8; }
#dividerV { background: #303033; min-width:1px; max-width:1px; min-height:24px; max-height:24px; }
#transcriptArea { background: #0d0d0d; border: none; }
#transcript {
    background: transparent; border: none; color: #e8e8e8;
    selection-background-color: rgba(96,165,250,0.25); selection-color: #e8e8e8;
}
#bottomBar { background: #1a1a1a; border-top: 1px solid #303033; }
/* mode tabs */
#modeTabLeftOff {
    background:#1a1a1a; color:#888890; border:1px solid #303033; border-right:none;
    border-top-left-radius:8px; border-bottom-left-radius:8px;
    border-top-right-radius:0; border-bottom-right-radius:0;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px;
}
#modeTabLeftOff:hover { background:#222225; color:#e8e8e8; }
#modeTabLeftOn {
    background:#60a5fa; color:#000000; border:1px solid #60a5fa; border-right:none;
    border-top-left-radius:8px; border-bottom-left-radius:8px;
    border-top-right-radius:0; border-bottom-right-radius:0;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px; font-weight:600;
}
#modeTabRightOff {
    background:#1a1a1a; color:#888890; border:1px solid #303033;
    border-top-left-radius:0; border-bottom-left-radius:0;
    border-top-right-radius:8px; border-bottom-right-radius:8px;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px;
}
#modeTabRightOff:hover { background:#222225; color:#e8e8e8; }
#modeTabRightOn {
    background:#60a5fa; color:#000000; border:1px solid #60a5fa;
    border-top-left-radius:0; border-bottom-left-radius:0;
    border-top-right-radius:8px; border-bottom-right-radius:8px;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px; font-weight:600;
}
/* theme tabs in settings */
#themeTabLeftOff {
    background:#1a1a1a; color:#888890; border:1px solid #303033; border-right:none;
    border-top-left-radius:8px; border-bottom-left-radius:8px;
    border-top-right-radius:0; border-bottom-right-radius:0;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px;
}
#themeTabLeftOff:hover { background:#222225; color:#e8e8e8; }
#themeTabLeftOn {
    background:#60a5fa; color:#000000; border:1px solid #60a5fa; border-right:none;
    border-top-left-radius:8px; border-bottom-left-radius:8px;
    border-top-right-radius:0; border-bottom-right-radius:0;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px; font-weight:600;
}
#themeTabRightOff {
    background:#1a1a1a; color:#888890; border:1px solid #303033;
    border-top-left-radius:0; border-bottom-left-radius:0;
    border-top-right-radius:8px; border-bottom-right-radius:8px;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px;
}
#themeTabRightOff:hover { background:#222225; color:#e8e8e8; }
#themeTabRightOn {
    background:#60a5fa; color:#000000; border:1px solid #60a5fa;
    border-top-left-radius:0; border-bottom-left-radius:0;
    border-top-right-radius:8px; border-bottom-right-radius:8px;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px; font-weight:600;
}
#btnRecord {
    background:#60a5fa; color:#000000; border:none; border-radius:12px;
    font-size:14px; font-weight:600; min-height:44px; max-height:44px;
}
#btnRecord:hover { background:#93c5fd; }
#btnRecord:disabled { background:#1e1e20; color:#555558; }
#btnRecording {
    background:rgba(248,113,113,0.15); color:#f87171; border:1px solid #f87171;
    border-radius:12px; font-size:14px; font-weight:600; min-height:44px; max-height:44px;
}
#btnRecording:hover { background:rgba(248,113,113,0.25); }
#btnAction {
    background:#1a1a1a; color:#888890; border:1px solid #303033;
    border-radius:8px; padding:5px 14px; font-size:12px;
}
#btnAction:hover { background:#222225; color:#e8e8e8; }
#btnAction:disabled { color:#555558; border-color:#222225; background:#111113; }
QScrollBar:vertical { background:transparent; width:5px; margin:2px 1px; }
QScrollBar::handle:vertical {
    background:rgba(255,255,255,0.14); border-radius:2px; min-height:30px;
}
QScrollBar::handle:vertical:hover { background:rgba(255,255,255,0.22); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
#dialogCard { background:#1a1a1a; border:1px solid #303033; border-radius:14px; }
QLineEdit {
    background:#1a1a1a; border:1px solid #303033; border-radius:8px;
    padding:8px 12px; color:#e8e8e8; font-size:13px;
}
QLineEdit:focus { border-color:#60a5fa; }
QLineEdit:disabled { color:#555558; }
QComboBox {
    background:#1a1a1a; border:1px solid #303033; border-radius:8px;
    padding:6px 12px; color:#e8e8e8; font-size:13px;
}
QComboBox::drop-down { border:none; width:24px; }
QComboBox QAbstractItemView {
    background:#1a1a1a; border:1px solid #303033; selection-background-color:#222225;
}
#sectionTitle { font-size:11px; font-weight:600; color:#888890; letter-spacing:0.06em; }
#statusOk     { color:#34d399; font-size:12px; }
#statusError  { color:#f87171; font-size:12px; }
#statusWarn   { color:#fbbf24; font-size:12px; }
#divider      { background:#303033; max-height:1px; min-height:1px; }
#insertIndicator {
    font-size:11px; color:#60a5fa;
    background:rgba(96,165,250,0.12); border:1px solid rgba(96,165,250,0.35);
    border-radius:6px; padding:3px 10px;
}
#modelStatus { font-size:11px; color:#888890; }
#modelStatusOk   { font-size:11px; color:#34d399; }
#modelStatusWarn { font-size:11px; color:#fbbf24; }
"""

STYLE_LIGHT = """
* {
    font-family: -apple-system, "PingFang SC", "Hiragino Sans GB",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px; color: #111118; outline: none;
}
QMainWindow, QDialog { background: #f0f0f5; }
QMenuBar {
    background: #ffffff; border-bottom: 1px solid #e0e0e5; padding: 2px 4px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 6px; color: #6e6e76; }
QMenuBar::item:selected { background: #f5f5fa; color: #111118; }
QMenu {
    background: #ffffff; border: 1px solid #e0e0e5; border-radius: 10px; padding: 4px;
}
QMenu::item { padding: 7px 20px; border-radius: 6px; color: #111118; }
QMenu::item:selected { background: #f5f5fa; }
QMenu::separator { height: 1px; background: #e0e0e5; margin: 4px 8px; }
#topBar  { background: #ffffff; border-bottom: 1px solid #e0e0e5; }
#brand   { font-size: 15px; font-weight: 600; color: #111118; }
#iconBtn {
    background: transparent; border: none; border-radius: 7px;
    font-size: 16px; color: #6e6e76;
    min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
}
#iconBtn:hover { background: #f5f5fa; color: #111118; }
#dividerV { background:#e0e0e5; min-width:1px; max-width:1px; min-height:24px; max-height:24px; }
#transcriptArea { background: #f0f0f5; border: none; }
#transcript {
    background: transparent; border: none; color: #111118;
    selection-background-color: rgba(37,99,235,0.15); selection-color: #111118;
}
#bottomBar { background: #ffffff; border-top: 1px solid #e0e0e5; }
#modeTabLeftOff {
    background:#ffffff; color:#6e6e76; border:1px solid #e0e0e5; border-right:none;
    border-top-left-radius:8px; border-bottom-left-radius:8px;
    border-top-right-radius:0; border-bottom-right-radius:0;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px;
}
#modeTabLeftOff:hover { background:#f5f5fa; color:#111118; }
#modeTabLeftOn {
    background:#2563eb; color:#ffffff; border:1px solid #2563eb; border-right:none;
    border-top-left-radius:8px; border-bottom-left-radius:8px;
    border-top-right-radius:0; border-bottom-right-radius:0;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px; font-weight:600;
}
#modeTabRightOff {
    background:#ffffff; color:#6e6e76; border:1px solid #e0e0e5;
    border-top-left-radius:0; border-bottom-left-radius:0;
    border-top-right-radius:8px; border-bottom-right-radius:8px;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px;
}
#modeTabRightOff:hover { background:#f5f5fa; color:#111118; }
#modeTabRightOn {
    background:#2563eb; color:#ffffff; border:1px solid #2563eb;
    border-top-left-radius:0; border-bottom-left-radius:0;
    border-top-right-radius:8px; border-bottom-right-radius:8px;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px; font-weight:600;
}
#themeTabLeftOff {
    background:#ffffff; color:#6e6e76; border:1px solid #e0e0e5; border-right:none;
    border-top-left-radius:8px; border-bottom-left-radius:8px;
    border-top-right-radius:0; border-bottom-right-radius:0;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px;
}
#themeTabLeftOff:hover { background:#f5f5fa; color:#111118; }
#themeTabLeftOn {
    background:#2563eb; color:#ffffff; border:1px solid #2563eb; border-right:none;
    border-top-left-radius:8px; border-bottom-left-radius:8px;
    border-top-right-radius:0; border-bottom-right-radius:0;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px; font-weight:600;
}
#themeTabRightOff {
    background:#ffffff; color:#6e6e76; border:1px solid #e0e0e5;
    border-top-left-radius:0; border-bottom-left-radius:0;
    border-top-right-radius:8px; border-bottom-right-radius:8px;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px;
}
#themeTabRightOff:hover { background:#f5f5fa; color:#111118; }
#themeTabRightOn {
    background:#2563eb; color:#ffffff; border:1px solid #2563eb;
    border-top-left-radius:0; border-bottom-left-radius:0;
    border-top-right-radius:8px; border-bottom-right-radius:8px;
    min-height:34px; max-height:34px; padding:0 16px; font-size:12px; font-weight:600;
}
#btnRecord {
    background:#2563eb; color:#ffffff; border:none; border-radius:12px;
    font-size:14px; font-weight:600; min-height:44px; max-height:44px;
}
#btnRecord:hover { background:#1d4ed8; }
#btnRecord:disabled { background:#e0e0e5; color:#9e9ea8; }
#btnRecording {
    background:rgba(220,38,38,0.1); color:#dc2626; border:1px solid #dc2626;
    border-radius:12px; font-size:14px; font-weight:600; min-height:44px; max-height:44px;
}
#btnRecording:hover { background:rgba(220,38,38,0.18); }
#btnAction {
    background:#ffffff; color:#6e6e76; border:1px solid #e0e0e5;
    border-radius:8px; padding:5px 14px; font-size:12px;
}
#btnAction:hover { background:#f5f5fa; color:#111118; }
#btnAction:disabled { color:#9e9ea8; border-color:#e8e8ed; background:#f5f5fa; }
QScrollBar:vertical { background:transparent; width:5px; margin:2px 1px; }
QScrollBar::handle:vertical {
    background:rgba(0,0,0,0.15); border-radius:2px; min-height:30px;
}
QScrollBar::handle:vertical:hover { background:rgba(0,0,0,0.25); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
#dialogCard { background:#ffffff; border:1px solid #e0e0e5; border-radius:14px; }
QLineEdit {
    background:#ffffff; border:1px solid #e0e0e5; border-radius:8px;
    padding:8px 12px; color:#111118; font-size:13px;
}
QLineEdit:focus { border-color:#2563eb; }
QLineEdit:disabled { color:#9e9ea8; }
QComboBox {
    background:#ffffff; border:1px solid #e0e0e5; border-radius:8px;
    padding:6px 12px; color:#111118; font-size:13px;
}
QComboBox::drop-down { border:none; width:24px; }
QComboBox QAbstractItemView {
    background:#ffffff; border:1px solid #e0e0e5; selection-background-color:#f5f5fa;
}
#sectionTitle { font-size:11px; font-weight:600; color:#6e6e76; letter-spacing:0.06em; }
#statusOk     { color:#059669; font-size:12px; }
#statusError  { color:#dc2626; font-size:12px; }
#statusWarn   { color:#d97706; font-size:12px; }
#divider      { background:#e0e0e5; max-height:1px; min-height:1px; }
#insertIndicator {
    font-size:11px; color:#2563eb;
    background:rgba(37,99,235,0.08); border:1px solid rgba(37,99,235,0.3);
    border-radius:6px; padding:3px 10px;
}
#modelStatus     { font-size:11px; color:#6e6e76; }
#modelStatusOk   { font-size:11px; color:#059669; }
#modelStatusWarn { font-size:11px; color:#d97706; }
"""

_current_theme = "dark"

def get_style(theme: str) -> str:
    return STYLE_LIGHT if theme == "light" else STYLE_DARK

def apply_theme(theme: str) -> None:
    global _current_theme
    _current_theme = theme
    QApplication.instance().setStyleSheet(get_style(theme))


# ── 文本格式 ──────────────────────────────────────────────
def _fmt_label():
    f = QTextCharFormat()
    f.setForeground(QColor("#6c6c70" if _current_theme == "light" else "#7c7c82"))
    f.setFontPointSize(11); return f

def _fmt_body():
    f = QTextCharFormat()
    f.setForeground(QColor("#1c1c1e" if _current_theme == "light" else "#e5e5e5"))
    f.setFontPointSize(15); return f

def _blk_label():
    b = QTextBlockFormat(); b.setTopMargin(20); b.setBottomMargin(4); return b

def _blk_body():
    b = QTextBlockFormat(); b.setTopMargin(0); b.setBottomMargin(0); return b


# ── 工具 ──────────────────────────────────────────────────
def polish(w):
    w.style().unpolish(w); w.style().polish(w)

def save_wav(frames, path):
    pa = pyaudio.PyAudio()
    wf = wave.open(path, "wb")
    wf.setnchannels(CHANNELS); wf.setsampwidth(pa.get_sample_size(FORMAT))
    wf.setframerate(RATE); wf.writeframes(b"".join(frames))
    wf.close(); pa.terminate()


# ══════════════════════════════════════════════════════════
#  后台线程：预加载模型
# ══════════════════════════════════════════════════════════
class ModelLoadThread(QThread):
    finished = pyqtSignal(bool, str)   # (success, message)

    def __init__(self, compute_type: str):
        super().__init__()
        self._compute_type = compute_type

    def run(self):
        try:
            from local_transcriber import Transcriber
            Transcriber.get().ensure_loaded(self._compute_type)
            self.finished.emit(True, "模型已就绪")
        except Exception as e:
            log.exception("Model load error")
            self.finished.emit(False, str(e))


# ══════════════════════════════════════════════════════════
#  后台线程：本地转录
# ══════════════════════════════════════════════════════════
class LocalTranscribeThread(QThread):
    segment = pyqtSignal(str)    # 整段文字
    done    = pyqtSignal(str)    # 转录完成（携带 wav_path 以便清理）
    error   = pyqtSignal(str)    # 错误消息

    def __init__(self, wav_path: str, preset: dict,
                 ctx_prompt: str = None, delete_after: bool = True):
        super().__init__()
        self._wav_path     = wav_path
        self._preset       = preset
        self._ctx_prompt   = ctx_prompt
        self._delete_after = delete_after

    def run(self):
        try:
            from local_transcriber import Transcriber
            for event in Transcriber.get().transcribe(
                self._wav_path,
                self._preset,
                ctx_prompt=self._ctx_prompt,
            ):
                t = event.get("type", "")
                if t == "segment":
                    self.segment.emit(event.get("text", ""))
                elif t == "done":
                    self.done.emit(self._wav_path)
                    return
                elif t == "error":
                    self.error.emit(event.get("message", "未知错误"))
                    return
            self.done.emit(self._wav_path)
        except Exception as e:
            log.exception("LocalTranscribeThread error")
            self.error.emit(str(e))
        finally:
            if self._delete_after:
                try:
                    os.remove(self._wav_path)
                except OSError:
                    pass


# ══════════════════════════════════════════════════════════
#  设置对话框（无服务器 URL，只有质量 + 主题）
# ══════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    saved = pyqtSignal(str, str)  # (quality_key, theme)

    def __init__(self, parent, cfg: dict):
        super().__init__(parent)
        self._cfg       = cfg
        self._sel_theme = cfg.get("theme", "dark")
        self.setWindowTitle("设置")
        self.setModal(True); self.setFixedWidth(400)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(16)

        # ── 质量卡片 ─────────────────────────────────────
        quality_card = QFrame(); quality_card.setObjectName("dialogCard")
        qcl = QVBoxLayout(quality_card)
        qcl.setContentsMargins(18, 16, 18, 16); qcl.setSpacing(10)

        lbl_q = QLabel("识别质量"); lbl_q.setObjectName("sectionTitle")
        qcl.addWidget(lbl_q)

        self._combo_quality = QComboBox()
        for key in QUALITY_KEYS:
            self._combo_quality.addItem(f"{key}  —  {QUALITY_HINTS[key]}", key)
        cur_key = self._cfg.get("quality_key", QUALITY_KEYS[1])
        for i in range(self._combo_quality.count()):
            if self._combo_quality.itemData(i) == cur_key:
                self._combo_quality.setCurrentIndex(i)
                break
        qcl.addWidget(self._combo_quality)

        hint = QLabel("注：切换质量时会重新加载模型（约数秒）")
        hint.setObjectName("sectionTitle")
        qcl.addWidget(hint)

        layout.addWidget(quality_card)

        # ── 外观卡片 ─────────────────────────────────────
        appear_card = QFrame(); appear_card.setObjectName("dialogCard")
        al = QVBoxLayout(appear_card)
        al.setContentsMargins(18, 16, 18, 16); al.setSpacing(10)

        lbl_a = QLabel("外观"); lbl_a.setObjectName("sectionTitle")
        al.addWidget(lbl_a)

        seg_row = QHBoxLayout(); seg_row.setSpacing(0)
        self._btn_dark  = QPushButton("🌙  深色")
        self._btn_light = QPushButton("☀️  浅色")
        self._btn_dark.setFixedHeight(34)
        self._btn_light.setFixedHeight(34)
        self._btn_dark.clicked.connect(lambda: self._select_theme("dark"))
        self._btn_light.clicked.connect(lambda: self._select_theme("light"))
        self._btn_dark.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_light.setCursor(Qt.CursorShape.PointingHandCursor)
        seg_row.addWidget(self._btn_dark)
        seg_row.addWidget(self._btn_light)
        seg_row.addStretch()
        al.addLayout(seg_row)

        layout.addWidget(appear_card)
        self._apply_theme_btns()

        # ── 按钮行 ───────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.addStretch()
        btn_cancel = QPushButton("取消"); btn_cancel.setObjectName("btnAction")
        btn_cancel.setFixedSize(80, 34); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存"); btn_save.setObjectName("btnRecord")
        btn_save.setFixedSize(80, 34); btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _select_theme(self, theme: str):
        self._sel_theme = theme
        self._apply_theme_btns()

    def _apply_theme_btns(self):
        if self._sel_theme == "dark":
            self._btn_dark.setObjectName("themeTabLeftOn")
            self._btn_light.setObjectName("themeTabRightOff")
        else:
            self._btn_dark.setObjectName("themeTabLeftOff")
            self._btn_light.setObjectName("themeTabRightOn")
        polish(self._btn_dark); polish(self._btn_light)

    def _save(self):
        quality_key = self._combo_quality.currentData()
        self.saved.emit(quality_key, self._sel_theme)
        self.accept()


# ══════════════════════════════════════════════════════════
#  主窗口
# ══════════════════════════════════════════════════════════
class MainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("飞飞转录")
        self.resize(900, 640); self.setMinimumSize(720, 520)

        icon_path = _resource("logo-app.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._cfg       = load_config()
        self._recording = False
        self._rec_stream= None
        self._rec_pa    = None
        self._rec_frames= []
        self._chunk_no  = 0
        self._last_text = ""
        self._threads   = []
        self._busy      = False
        self._insert_cursor = None

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._update_record_btn)

        self._build_ui()
        apply_theme(self._cfg.get("theme", "dark"))

        # 启动时后台预加载模型
        self._start_model_load()

    # ─── 模型加载 ─────────────────────────────────────────

    def _start_model_load(self):
        """异步预加载模型，期间禁用录音按钮"""
        self._btn_record.setEnabled(False)
        self._set_model_status("⏳ 正在加载模型…", "modelStatusWarn")
        preset       = get_quality_preset(self._cfg.get("quality_key", QUALITY_KEYS[1]))
        compute_type = preset["compute_type"]
        th = ModelLoadThread(compute_type)
        th.finished.connect(self._on_model_loaded)
        th.finished.connect(lambda: th.deleteLater())
        self._threads.append(th)
        th.start()

    def _on_model_loaded(self, success: bool, message: str):
        if success:
            self._set_model_status("✓ 模型已就绪（small · 内置）", "modelStatusOk")
            self._btn_record.setEnabled(True)
        else:
            self._set_model_status(f"✗ 模型加载失败: {message[:60]}", "statusError")
            QMessageBox.critical(self, "模型加载失败",
                f"无法加载 Whisper small 模型：\n\n{message}\n\n"
                "请检查应用是否完整安装，或查看日志：\n"
                f"~/Library/Logs/飞飞转录单机版/app.log")

    def _set_model_status(self, text: str, obj_name: str):
        self._lbl_model.setText(text)
        self._lbl_model.setObjectName(obj_name)
        polish(self._lbl_model)

    # ─── 界面构建 ─────────────────────────────────────────

    def _build_ui(self):
        mb = QMenuBar(self); self.setMenuBar(mb)
        file_menu = QMenu("文件", self)
        act_import = QAction("导入音视频…", self); act_import.setShortcut("Ctrl+O")
        act_import.triggered.connect(self._select_file)
        act_quit = QAction("退出", self); act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_import); file_menu.addSeparator()
        file_menu.addAction(act_quit)
        mb.addMenu(file_menu)

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_main_area())

    def _build_main_area(self):
        main   = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        # ── 顶部栏 52px ───────────────────────────────────
        topbar = QWidget(); topbar.setObjectName("topBar"); topbar.setFixedHeight(52)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(16, 0, 12, 0); tbl.setSpacing(4)

        logo_path = _resource("logo-app.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(
                28, 28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl = QLabel(); logo_lbl.setPixmap(pix)
            logo_lbl.setFixedSize(28, 28)
            tbl.addWidget(logo_lbl); tbl.addSpacing(6)

        brand = QLabel("飞飞转录"); brand.setObjectName("brand")
        tbl.addWidget(brand)
        tbl.addSpacing(8)

        # 模型状态标签（顶部栏内）
        self._lbl_model = QLabel("⏳ 加载中…")
        self._lbl_model.setObjectName("modelStatusWarn")
        tbl.addWidget(self._lbl_model)
        tbl.addStretch()

        def make_icon_btn(text, tip=None):
            b = QPushButton(text); b.setObjectName("iconBtn")
            b.setFixedSize(28, 28)
            if tip: b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            return b

        self._btn_clear = make_icon_btn("🗑", "清空")
        self._btn_clear.clicked.connect(self._clear_transcript)
        self._btn_copy = make_icon_btn("📋", "复制")
        self._btn_copy.clicked.connect(self._copy_text)
        self._btn_file = make_icon_btn("🎬", "导入音视频")
        self._btn_file.clicked.connect(self._select_file)

        tbl.addWidget(self._btn_clear)
        tbl.addWidget(self._btn_copy)
        tbl.addWidget(self._btn_file)

        tbl.addSpacing(6)
        divv = QWidget(); divv.setObjectName("dividerV")
        divv.setFixedWidth(1); divv.setFixedHeight(24)
        tbl.addWidget(divv); tbl.addSpacing(4)

        btn_settings = make_icon_btn("⚙", "设置")
        btn_settings.clicked.connect(self._open_settings)
        tbl.addWidget(btn_settings)

        layout.addWidget(topbar)

        # ── 转录区域 ──────────────────────────────────────
        transcript_wrap = QWidget(); transcript_wrap.setObjectName("transcriptArea")
        tw_layout = QVBoxLayout(transcript_wrap)
        tw_layout.setContentsMargins(20, 20, 20, 20); tw_layout.setSpacing(0)

        self._transcript = QTextEdit(); self._transcript.setObjectName("transcript")
        self._transcript.setReadOnly(False)
        self._transcript.setPlaceholderText(
            "转录内容将在这里显示\n\n"
            "点击下方「🎙 开始录音识别」开始录音；\n"
            "或点击顶栏「🎬」导入音视频文件。\n\n"
            "ℹ️  单机版无需服务端，模型已内置在应用中。"
        )
        tw_layout.addWidget(self._transcript)
        self._transcript.cursorPositionChanged.connect(self._on_cursor_changed)
        layout.addWidget(transcript_wrap, 1)

        # ── 底部操作栏 68px ──────────────────────────────
        bottombar = QWidget(); bottombar.setObjectName("bottomBar"); bottombar.setFixedHeight(68)
        bbl = QHBoxLayout(bottombar)
        bbl.setContentsMargins(20, 12, 20, 12); bbl.setSpacing(0)

        self._btn_mode_batch    = QPushButton("📼  整段")
        self._btn_mode_realtime = QPushButton("⚡  实时")
        self._btn_mode_batch.setFixedHeight(34)
        self._btn_mode_realtime.setFixedHeight(34)
        self._btn_mode_batch.clicked.connect(lambda: self._set_mode("batch"))
        self._btn_mode_realtime.clicked.connect(lambda: self._set_mode("realtime"))
        self._btn_mode_batch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mode_realtime.setCursor(Qt.CursorShape.PointingHandCursor)

        bbl.addWidget(self._btn_mode_batch)
        bbl.addWidget(self._btn_mode_realtime)
        bbl.addStretch()

        self._lbl_insert = QLabel("📍 插入点已选择，下次录音将插入此处")
        self._lbl_insert.setObjectName("insertIndicator")
        self._lbl_insert.setVisible(False)
        bbl.addWidget(self._lbl_insert); bbl.addSpacing(12)

        self._btn_record = QPushButton("🎙  开始录音识别")
        self._btn_record.setObjectName("btnRecord")
        self._btn_record.setFixedHeight(44); self._btn_record.setFixedWidth(196)
        self._btn_record.clicked.connect(self._toggle_record)
        bbl.addWidget(self._btn_record)

        layout.addWidget(bottombar)

        self._set_mode(self._cfg.get("mode", "batch"), save=False)
        return main

    # ─── 插入点追踪 ───────────────────────────────────────

    def _on_cursor_changed(self):
        if self._busy: return
        cur = self._transcript.textCursor()
        end = self._transcript.document().characterCount() - 1
        if cur.position() < end and self._transcript.toPlainText().strip():
            self._insert_cursor = QTextCursor(cur)
            self._lbl_insert.setVisible(True)
        else:
            self._insert_cursor = None
            self._lbl_insert.setVisible(False)

    def _clear_insert_point(self):
        self._insert_cursor = None
        self._lbl_insert.setVisible(False)

    def _do_insert_text(self, text: str, add_newline: bool = True):
        self._transcript.blockSignals(True)
        try:
            if self._insert_cursor is not None:
                cur = self._insert_cursor
            else:
                cur = self._transcript.textCursor()
                cur.movePosition(QTextCursor.MoveOperation.End)
            cur.setCharFormat(_fmt_body())
            cur.insertText(text + ("\n" if add_newline else ""))
            if self._insert_cursor is not None:
                self._insert_cursor = QTextCursor(cur)
            self._transcript.setTextCursor(cur)
            self._transcript.ensureCursorVisible()
        finally:
            self._transcript.blockSignals(False)

    # ─── 模式切换 ─────────────────────────────────────────

    def _set_mode(self, mode: str, save: bool = True):
        self._cfg["mode"] = mode
        if save: save_config(self._cfg)
        if mode == "batch":
            self._btn_mode_batch.setObjectName("modeTabLeftOn")
            self._btn_mode_realtime.setObjectName("modeTabRightOff")
        else:
            self._btn_mode_batch.setObjectName("modeTabLeftOff")
            self._btn_mode_realtime.setObjectName("modeTabRightOn")
        polish(self._btn_mode_batch); polish(self._btn_mode_realtime)

    def _set_controls_enabled(self, enabled: bool):
        self._btn_mode_batch.setEnabled(enabled)
        self._btn_mode_realtime.setEnabled(enabled)
        self._btn_file.setEnabled(enabled)

    # ─── 设置 ─────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self, self._cfg)
        dlg.saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self, quality_key: str, theme: str):
        old_quality = self._cfg.get("quality_key")
        self._cfg["quality_key"] = quality_key
        self._cfg["theme"] = theme
        save_config(self._cfg)
        apply_theme(theme)
        if quality_key != old_quality:
            # 切换质量需要重新加载模型
            from local_transcriber import Transcriber
            Transcriber.get().unload()
            self._start_model_load()

    # ─── 录音 ─────────────────────────────────────────────

    def _toggle_record(self):
        self._start_recording() if not self._recording else self._stop_recording()

    def _start_recording(self):
        self._recording  = True
        self._busy       = True
        self._rec_frames = []; self._chunk_no = 0; self._last_text = ""
        self._set_controls_enabled(False)

        self._rec_pa = pyaudio.PyAudio()
        self._rec_stream = self._rec_pa.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK,
        )
        self._blink_timer.start(500)
        self._btn_record.setObjectName("btnRecording"); polish(self._btn_record)
        if self._cfg["mode"] == "realtime":
            self._btn_record.setText("⏹  ● 录音中  0s / 最多 30s")
        else:
            self._btn_record.setText("⏹  ● 录音中  0s")
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
        else:
            if not self._rec_frames: return
            frames   = self._rec_frames[:]; self._rec_frames = []
            duration = len(frames) * CHUNK / RATE
            raw      = b"".join(frames)
            samples  = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            rms      = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0
            log.info("Stop: %d frames, %.1fs, RMS=%.1f", len(frames), duration, rms)
            if rms < 50:
                QMessageBox.warning(self, "麦克风静音",
                    "录音电平过低（可能是麦克风权限未授权）。\n\n"
                    "请前往：系统设置 → 隐私与安全性 → 麦克风\n"
                    "找到「飞飞转录」并开启权限，然后重新录音。")
                return
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close(); save_wav(frames, tmp.name)
            self._insert_chunk_label(1, duration, "完整录音")
            self._start_local_transcribe(tmp.name)

    def _record_loop(self):
        if not self._recording: return
        self._rec_frames.append(
            self._rec_stream.read(CHUNK, exception_on_overflow=False))
        if self._cfg["mode"] == "realtime":
            n = len(self._rec_frames)
            if n >= CHUNK_MAX_FRAMES:
                self._flush_chunk()
            elif n >= CHUNK_MIN_FRAMES and n % 5 == 0:
                if self._is_silence(self._rec_frames[-SILENCE_MIN_FRAMES:]):
                    self._flush_chunk()
        QTimer.singleShot(10, self._record_loop)

    @staticmethod
    def _is_silence(frames) -> bool:
        data = b"".join(frames)
        s    = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        rms  = float(np.sqrt(np.mean(s ** 2))) if len(s) else 0
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
        ctx = self._last_text[-80:] if self._last_text else None
        self._start_local_transcribe(tmp.name, ctx_prompt=ctx)

    def _start_local_transcribe(self, wav_path: str, ctx_prompt: str = None,
                                 delete_after: bool = True):
        preset = get_quality_preset(self._cfg.get("quality_key", QUALITY_KEYS[1]))
        th = LocalTranscribeThread(wav_path, preset,
                                   ctx_prompt=ctx_prompt,
                                   delete_after=delete_after)
        th.segment.connect(self._on_segment)
        th.done.connect(self._on_transcribe_done)
        th.error.connect(self._on_transcribe_error)
        th.finished.connect(lambda: self._cleanup_thread(th))
        self._threads.append(th)
        th.start()

    def _cleanup_thread(self, th):
        if th in self._threads:
            self._threads.remove(th)
        th.deleteLater()

    def _insert_chunk_label(self, chunk_no, duration, trigger):
        self._transcript.blockSignals(True)
        try:
            if self._insert_cursor is not None:
                cur = self._insert_cursor
            else:
                cur = self._transcript.textCursor()
                cur.movePosition(QTextCursor.MoveOperation.End)
            if chunk_no > 1 or self._insert_cursor is not None:
                spacer = QTextBlockFormat(); spacer.setTopMargin(18)
                cur.insertBlock(spacer); cur.insertText("")
            cur.insertBlock(_blk_label())
            dur_part = f"  ·  {duration:.0f}s" if duration > 0 else ""
            cur.insertText(f"第 {chunk_no} 段{dur_part}  ·  {trigger}", _fmt_label())
            cur.insertBlock(_blk_body())
            if self._insert_cursor is not None:
                self._insert_cursor = QTextCursor(cur)
            self._transcript.setTextCursor(cur)
        finally:
            self._transcript.blockSignals(False)

    def _on_segment(self, text: str):
        self._last_text = text
        self._do_insert_text(text, add_newline=True)

    def _on_transcribe_done(self, _wav_path: str):
        self._transcript.blockSignals(True)
        cur = self._transcript.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        if not self._transcript.toPlainText().endswith("\n"):
            cur.insertText("\n")
        self._transcript.blockSignals(False)
        self._busy = False
        self._clear_insert_point()

    def _on_transcribe_error(self, msg: str):
        log.error("Transcribe error: %s", msg)
        self._busy = False
        self._clear_insert_point()
        QMessageBox.critical(self, "转录失败",
            f"{msg}\n\n日志位置：\n~/Library/Logs/飞飞转录单机版/app.log")

    # ─── 导入音视频 ───────────────────────────────────────

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音视频文件", "",
            "音视频文件 (*.mp3 *.wav *.m4a *.mp4 *.mov *.flv *.aac *.ogg)"
        )
        if not path: return
        self._chunk_no += 1
        self._insert_chunk_label(self._chunk_no, 0, f"文件导入·{os.path.basename(path)}")
        self._start_local_transcribe(path, delete_after=False)

    # ─── 清空 / 复制 ──────────────────────────────────────

    def _clear_transcript(self):
        self._transcript.clear()
        self._clear_insert_point()

    def _copy_text(self):
        text = self._transcript.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "转录内容为空，没有可复制的内容。"); return
        QApplication.clipboard().setText(text)
        orig = self._btn_copy.text(); self._btn_copy.setText("✅")
        QTimer.singleShot(1500, lambda: self._btn_copy.setText(orig))

    def _update_record_btn(self):
        sec = int(len(self._rec_frames) * CHUNK / RATE)
        if self._cfg["mode"] == "realtime":
            self._btn_record.setText(f"⏹  ● 录音中  {sec}s / 最多 30s")
        else:
            self._btn_record.setText(f"⏹  ● 录音中  {sec}s")

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
        for th in list(self._threads):
            if th.isRunning(): th.wait(3000)
        event.accept()


# ══════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    multiprocessing.freeze_support()
    os.makedirs(_CFG_DIR, exist_ok=True)
    app = QApplication(sys.argv)
    cfg = load_config()
    apply_theme(cfg.get("theme", "dark"))
    win = MainWin()
    win.show()
    sys.exit(app.exec())
