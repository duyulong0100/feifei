"""
管理 API 路由
GET  /api/config              → 返回当前配置
PUT  /api/config              → 更新配置并重新加载模型
GET  /api/models              → 列出所有模型及下载状态
POST /api/models/{size}/download → 触发模型下载（SSE 进度流）
"""
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from ..config import (
    load_config, save_config, get_quality_preset,
    MODEL_SIZES, MODEL_LABELS, MODEL_HINTS, QUALITY_KEYS, QUALITY_HINTS,
    _DEFAULT_PREPROCESS,
)
from ..transcriber import Transcriber, check_downloaded
from ..audio_preprocess import ffmpeg_available, noisereduce_available, PRESET_HINTS

log = logging.getLogger("飞飞转录.admin")
router = APIRouter(tags=["admin"])


# ── 请求/响应 Schema ─────────────────────────────────────

class ConfigIn(BaseModel):
    model_size:  Optional[str] = None
    quality_key: Optional[str] = None
    custom_path: Optional[str] = None


class ConfigOut(BaseModel):
    model_size:  str
    quality_key: str
    custom_path: Optional[str]
    model_loaded: bool
    current_model_id: Optional[str]


# ── 路由 ─────────────────────────────────────────────────

@router.get("/config", response_model=ConfigOut)
async def get_config():
    """返回当前服务端配置"""
    cfg = load_config()
    t = Transcriber.get()
    return ConfigOut(
        model_size=cfg["model_size"],
        quality_key=cfg["quality_key"],
        custom_path=cfg.get("custom_path"),
        model_loaded=t.is_loaded(),
        current_model_id=t.current_model_id(),
    )


@router.put("/config")
async def update_config(body: ConfigIn):
    """
    更新配置，若 model_size/quality_key 变化则重新加载模型。
    """
    cfg = load_config()
    changed = False

    if body.model_size is not None:
        if body.model_size not in MODEL_SIZES:
            raise HTTPException(400, f"无效 model_size：{body.model_size}")
        if cfg["model_size"] != body.model_size:
            cfg["model_size"] = body.model_size; changed = True

    if body.quality_key is not None:
        if body.quality_key not in QUALITY_KEYS:
            raise HTTPException(400, f"无效 quality_key：{body.quality_key}")
        if cfg["quality_key"] != body.quality_key:
            cfg["quality_key"] = body.quality_key; changed = True

    # custom_path 可以显式置 None
    if body.custom_path != cfg.get("custom_path"):
        cfg["custom_path"] = body.custom_path; changed = True

    save_config(cfg)
    log.info("Config updated: %s (changed=%s)", cfg, changed)

    if changed:
        model_id     = cfg.get("custom_path") or cfg["model_size"]
        compute_type = get_quality_preset(cfg["quality_key"])["compute_type"]
        try:
            Transcriber.get().ensure_loaded(model_id, compute_type)
            log.info("Model reloaded: %s (%s)", model_id, compute_type)
        except Exception as e:
            log.error("Model reload failed: %s", e)
            raise HTTPException(500, f"模型加载失败：{e}")

    return {"ok": True, "config": cfg}


@router.get("/models")
async def list_models():
    """返回所有模型及其下载状态"""
    t = Transcriber.get()
    result = []
    for size in MODEL_SIZES:
        result.append({
            "size":        size,
            "label":       MODEL_LABELS[size],
            "hint":        MODEL_HINTS[size],
            "downloaded":  check_downloaded(size),
            "active":      t.current_model_id() == size,
        })
    return {"models": result}


@router.post("/models/{size}/download")
async def download_model(size: str):
    """
    触发指定模型下载，以 SSE 流式返回进度。
    客户端用 EventSource 监听。
    """
    if size not in MODEL_SIZES:
        raise HTTPException(400, f"无效 model_size：{size}")

    if check_downloaded(size):
        async def _already():
            yield f"data: {json.dumps({'type': 'done', 'message': f'「{size}」已下载，无需重复下载'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(_already(), media_type="text/event-stream")

    def _gen():
        for event in Transcriber.get().download_model(size):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/quality-presets")
async def list_quality_presets():
    """返回所有质量预设信息（供管理 UI 渲染）"""
    return {
        "presets": [
            {"key": k, "hint": QUALITY_HINTS[k]}
            for k in QUALITY_KEYS
        ]
    }


# ── 音频预处理配置 ────────────────────────────────────────────

class PreprocessConfigIn(BaseModel):
    enabled:         Optional[bool]  = None
    preset:          Optional[str]   = None
    echo_reduction:  Optional[bool]  = None
    spectral_gating: Optional[bool]  = None
    nr_prop_decrease: Optional[float] = None


@router.get("/preprocess/config")
async def get_preprocess_config():
    """返回当前音频预处理配置及环境依赖状态"""
    cfg = load_config()
    return {
        "preprocess": cfg.get("preprocess", _DEFAULT_PREPROCESS),
        "env": {
            "ffmpeg":       ffmpeg_available(),
            "noisereduce":  noisereduce_available(),
        },
        "presets": [
            {"key": k, "hint": v} for k, v in PRESET_HINTS.items()
        ],
    }


@router.put("/preprocess/config")
async def update_preprocess_config(body: PreprocessConfigIn):
    """更新音频预处理配置"""
    cfg = load_config()
    pre = cfg.get("preprocess", dict(_DEFAULT_PREPROCESS))

    if body.enabled         is not None: pre["enabled"]         = body.enabled
    if body.preset          is not None: pre["preset"]          = body.preset
    if body.echo_reduction  is not None: pre["echo_reduction"]  = body.echo_reduction
    if body.spectral_gating is not None: pre["spectral_gating"] = body.spectral_gating
    if body.nr_prop_decrease is not None:
        pre["nr_prop_decrease"] = max(0.0, min(1.0, body.nr_prop_decrease))

    cfg["preprocess"] = pre
    save_config(cfg)
    log.info("Preprocess config updated: %s", pre)
    return {"ok": True, "preprocess": pre}
