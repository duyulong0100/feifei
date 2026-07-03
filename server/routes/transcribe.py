"""
转录 API 路由 — 双阶段实时流式

阶段一：Whisper 转录
  - 后台线程运行，segment 事件通过 queue 实时推送给客户端
  - LLM 关闭时：客户端收到第一段文字的延迟 ≈ 首段转录时间（通常 <1s）
  - LLM 开启时：静默收集全文（不推送 raw），等 Whisper 结束后进入阶段二

阶段二：LLM 润色（仅 LLM 开启时）
  - 后台线程调用 LLM，token 通过 queue 实时推送
  - 客户端收到首个润色 token 的延迟 ≈ Whisper 完成后 + LLM 首 token 时间

全程以 SSE 格式推送，客户端零感知差异。
"""
import asyncio
import json
import logging
import os
import queue as sync_queue
import tempfile
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..config import load_config, get_quality_preset
from ..transcriber import Transcriber
from ..llm import stream_polish
from ..audio_preprocess import preprocess as audio_preprocess, _safe_remove

log    = logging.getLogger("飞飞转录.transcribe")
router = APIRouter(tags=["transcribe"])

# ── 各客户端最近一次转录记录 ─────────────────────────────────
_record_lock = threading.Lock()
_records: dict[str, dict] = {}    # client_id → 该客户端最近一次记录

_MAX_CLIENTS = 50   # 最多保留 N 个客户端，防止内存无限增长


def _save_record(client_id: str, **kw) -> None:
    with _record_lock:
        _records[client_id] = {"client_id": client_id, **kw}
        # 超出上限时淘汰最早的记录
        if len(_records) > _MAX_CLIENTS:
            oldest = next(iter(_records))
            del _records[oldest]


# ── 通用：在后台线程运行同步生成器，结果放入 queue ────────────

def _run_gen_in_thread(gen_fn, q: sync_queue.Queue) -> threading.Thread:
    """
    把同步生成器 gen_fn() 放到后台线程运行，
    每个 yield 值放入 q，结束后放入哨兵 None。
    """
    def _worker():
        try:
            for item in gen_fn():
                q.put(item)
        except Exception as e:
            log.exception("gen worker error")
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(None)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


async def _drain_queue(q: sync_queue.Queue, timeout: float = 180.0):
    """
    异步逐个从 queue 取出事件（不阻塞事件循环），
    直到遇到哨兵 None 或超时。
    CancelledError（客户端断开）向上传播，由调用方 finally 做清理。
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        if asyncio.get_event_loop().time() > deadline:
            log.error("_drain_queue timeout")
            return
        try:
            ev = q.get_nowait()
        except sync_queue.Empty:
            try:
                await asyncio.sleep(0.03)
            except asyncio.CancelledError:
                raise   # 让上层 finally 做清理
            continue
        if ev is None:
            return
        yield ev


# ── 主接口 ───────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe_audio(
    audio_file:   UploadFile    = File(..., description="音频 / 视频文件"),
    ctx_prompt:   Optional[str] = Form(None, description="上下文提示"),
    language:     str           = Form("zh",  description="语言代码，默认中文"),
    x_client_id: str            = Header(default="", alias="X-Client-ID"),
):
    client_id = x_client_id.strip() or "anonymous"
    # ── 保存上传文件 ─────────────────────────────────────────
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(400, "audio_file 为空")

    orig_name = audio_file.filename or "audio.wav"
    suffix    = os.path.splitext(orig_name)[1] or ".wav"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, audio_bytes); os.close(fd)
    log.debug("Saved upload → %s (%d bytes)", tmp_path, len(audio_bytes))

    # ── 读取配置 ─────────────────────────────────────────────
    cfg          = load_config()
    preset       = get_quality_preset(cfg["quality_key"])
    model_id     = cfg.get("custom_path") or cfg["model_size"]
    compute_type = preset["compute_type"]
    pre_cfg      = cfg.get("preprocess", {})
    llm_cfg      = cfg.get("llm", {})
    llm_enabled  = bool(llm_cfg.get("enabled"))

    # ── 确保模型已加载（executor，不阻塞事件循环）────────────
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None, Transcriber.get().ensure_loaded, model_id, compute_type
        )
    except Exception as e:
        _safe_remove(tmp_path)
        raise HTTPException(503, f"模型加载失败：{e}")

    # ── 构建 SSE 异步生成器 ──────────────────────────────────

    async def _event_stream():
        # Step 0: 音频预处理（executor）
        audio_path = await loop.run_in_executor(None, audio_preprocess, tmp_path, pre_cfg)

        raw_segments:  list[str]    = []    # 收集原始文字（LLM 时用）
        polished_text: Optional[str] = None # LLM 润色结果
        llm_error:     Optional[str] = None

        try:
            # ── 阶段一：Whisper 实时流式 ─────────────────────
            whisper_q: sync_queue.Queue = sync_queue.Queue()
            _run_gen_in_thread(
                lambda: Transcriber.get().transcribe(
                    audio_path, preset, language=language, ctx_prompt=ctx_prompt
                ),
                whisper_q,
            )

            async for ev in _drain_queue(whisper_q):
                if ev.get("type") == "segment":
                    raw_segments.append(ev.get("text", ""))
                    if not llm_enabled:
                        # LLM 关闭：实时推送原始段落
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                elif ev.get("type") == "error":
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    return

            if not raw_segments:
                yield f"data: {json.dumps({'type':'error','message':'VAD 过滤后无语音段（录音可能太短或全是静音）'}, ensure_ascii=False)}\n\n"
                return

            # ── 阶段二：LLM 实时流式（若启用）───────────────
            if llm_enabled:
                full_text = "\n".join(raw_segments)
                task      = llm_cfg.get("task", "polish")
                log.info("LLM polish | task=%s chars=%d", task, len(full_text))

                llm_q: sync_queue.Queue = sync_queue.Queue()
                _run_gen_in_thread(
                    lambda: stream_polish(full_text, task, llm_cfg),
                    llm_q,
                )

                llm_chunks: list[str] = []
                async for ev in _drain_queue(llm_q):
                    t = ev.get("type", "")
                    if t == "chunk":
                        text = ev.get("text", "")
                        llm_chunks.append(text)
                        # 直接推送 token，客户端追加显示
                        yield f"data: {json.dumps({'type':'chunk','text':text}, ensure_ascii=False)}\n\n"
                    elif t == "done":
                        break
                    elif t == "error":
                        llm_error = ev.get("message", "")
                        log.warning("LLM polish failed (%s) → fallback", llm_error)
                        # 润色失败：回退推送原始段落
                        for seg in raw_segments:
                            yield f"data: {json.dumps({'type':'segment','text':seg}, ensure_ascii=False)}\n\n"
                        break

                polished_text = "".join(llm_chunks) if llm_chunks and not llm_error else None
            else:
                polished_text = None

            yield f"data: {json.dumps({'type':'done'}, ensure_ascii=False)}\n\n"

        finally:
            if audio_path != tmp_path:
                _safe_remove(audio_path)
            _safe_remove(tmp_path)

            # 保存完整记录供管理后台对比（按 client_id 分桶）
            _save_record(
                client_id,
                timestamp        = datetime.now().isoformat(timespec="seconds"),
                audio_bytes      = len(audio_bytes),
                model_id         = model_id,
                preprocess_on    = bool(pre_cfg.get("enabled")),
                preprocess_preset= pre_cfg.get("preset", "balanced"),
                llm_enabled      = llm_enabled,
                llm_model        = llm_cfg.get("model", "") if llm_enabled else "",
                llm_task         = llm_cfg.get("task", "polish") if llm_enabled else "",
                raw_text         = "\n".join(raw_segments),
                polished_text    = polished_text,
                polished_ok      = polished_text is not None,
                llm_error        = llm_error,
            )

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 记录查询接口 ─────────────────────────────────────────────

@router.get("/transcribe/latest")
async def get_latest(client_id: str = ""):
    """
    带 client_id：返回该客户端最近一次记录（客户端自查）。
    不带 client_id：返回所有客户端记录列表（管理端全览）。
    """
    with _record_lock:
        if client_id:
            rec = _records.get(client_id)
            return rec if rec else {"empty": True, "client_id": client_id}
        if not _records:
            return {"empty": True}
        return {"records": sorted(
            _records.values(),
            key=lambda r: r.get("timestamp", ""),
            reverse=True,
        )}
