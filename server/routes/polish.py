"""
文字润色 API
POST /api/polish   → 接收转录文字，调用 LLM 润色/分段，SSE 流式返回
GET  /api/polish/config  → 返回 LLM 配置（api_key 脱敏）
PUT  /api/polish/config  → 更新 LLM 配置
POST /api/polish/test    → 测试 LLM 连接
"""
import asyncio
import json
import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import load_config, save_config
from ..llm import stream_polish, test_connection, TASKS

log    = logging.getLogger("飞飞转录.polish")
router = APIRouter(tags=["polish"])


# ── Schema ────────────────────────────────────────────────

class PolishRequest(BaseModel):
    text: str
    task: str = "polish"   # "polish" | "segment" | "both"

class LlmConfigIn(BaseModel):
    enabled:  Optional[bool] = None
    base_url: Optional[str] = None
    api_key:  Optional[str] = None
    model:    Optional[str] = None
    task:     Optional[str] = None    # "polish" | "segment" | "both"（自动执行的任务）
    prompts:  Optional[dict] = None   # {"polish": str, "segment": str, "both": str}


# ── 润色 ──────────────────────────────────────────────────

@router.post("/polish")
async def polish_text(body: PolishRequest):
    """
    调用 LLM 对转录文字润色/分段，以 SSE 流式返回。
    转录在线程池执行，不阻塞事件循环。
    """
    if not body.text.strip():
        raise HTTPException(400, "text 不能为空")
    if body.task not in TASKS:
        raise HTTPException(400, f"task 必须为 {list(TASKS.keys())} 之一")

    cfg     = load_config()
    llm_cfg = cfg.get("llm", {})

    def _run() -> list[dict]:
        return list(stream_polish(body.text, body.task, llm_cfg))

    try:
        events = await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception as e:
        log.exception("Polish executor error")
        events = [{"type": "error", "message": str(e)}]

    async def _sse():
        for ev in events:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── LLM 配置 CRUD ─────────────────────────────────────────

@router.get("/polish/config")
async def get_llm_config():
    """返回 LLM 配置，api_key 脱敏显示"""
    cfg     = load_config()
    llm_cfg = dict(cfg.get("llm", {}))
    # 脱敏：只返回前4位 + 星号
    key = llm_cfg.get("api_key", "")
    llm_cfg["api_key_masked"] = (key[:4] + "****") if len(key) > 4 else ("****" if key else "")
    llm_cfg.pop("api_key", None)
    return {"llm": llm_cfg, "tasks": [{"key": k, "label": v} for k, v in TASKS.items()]}


@router.put("/polish/config")
async def update_llm_config(body: LlmConfigIn):
    """更新 LLM 配置，仅更新提供的字段"""
    cfg     = load_config()
    llm_cfg = cfg.get("llm", {})

    if body.enabled  is not None: llm_cfg["enabled"]  = body.enabled
    if body.base_url is not None: llm_cfg["base_url"] = body.base_url.strip()
    if body.api_key  is not None: llm_cfg["api_key"]  = body.api_key.strip()
    if body.model    is not None: llm_cfg["model"]    = body.model.strip()
    if body.task     is not None: llm_cfg["task"]     = body.task.strip()
    if body.prompts  is not None:
        llm_cfg["prompts"] = {**llm_cfg.get("prompts", {}), **body.prompts}

    cfg["llm"] = llm_cfg
    save_config(cfg)
    log.info("LLM config updated: enabled=%s model=%s", llm_cfg.get("enabled"), llm_cfg.get("model"))
    return {"ok": True}


@router.post("/polish/test")
async def test_llm():
    """测试当前 LLM 配置的连通性（同步，在 executor 里跑）"""
    cfg     = load_config()
    llm_cfg = cfg.get("llm", {})
    result  = await asyncio.get_event_loop().run_in_executor(
        None, test_connection, llm_cfg
    )
    return result
