"""
飞飞转录 · 服务端入口
FastAPI 应用：挂载路由 + 静态文件 + CORS + 启动时加载模型
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

# ── 日志 ─────────────────────────────────────────────────
_LOG_DIR = os.path.expanduser("~/Library/Logs/飞飞转录")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(_LOG_DIR, "server.log"),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s  %(message)s",
    encoding="utf-8",
)
# 同时输出到控制台
logging.getLogger().addHandler(logging.StreamHandler())
log = logging.getLogger("飞飞转录.server")

# 压制第三方库的 DEBUG 日志（openai / httpx 请求细节不需要显示）
for _noisy in ("httpx", "httpcore", "openai"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ── 路径 ─────────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
_STATIC_DIR  = os.path.join(_HERE, "static")


# ── 启动 / 关闭 ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预加载模型，关闭时释放"""
    from .config import load_config, get_quality_preset
    from .transcriber import Transcriber
    cfg = load_config()
    model_id    = cfg.get("custom_path") or cfg["model_size"]
    compute_type = get_quality_preset(cfg["quality_key"])["compute_type"]
    log.info("Startup: preloading model %s (%s)", model_id, compute_type)
    try:
        Transcriber.get().ensure_loaded(model_id, compute_type)
        log.info("Model ready: %s", model_id)
    except Exception as e:
        log.warning("Model preload failed (will retry on first request): %s", e)
    yield
    log.info("Shutdown: releasing model")
    Transcriber.get().unload()


# ── FastAPI App ────────────────────────────────────────────
app = FastAPI(
    title="飞飞转录 API",
    description="Whisper 语音转录服务 + 管理后台",
    version="2.0.0",
    lifespan=lifespan,
)

# 允许跨域（客户端 GUI 通过 http://localhost:8000 访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由 ─────────────────────────────────────────────────
from .routes.admin      import router as admin_router
from .routes.transcribe import router as transcribe_router
from .routes.polish     import router as polish_router

app.include_router(admin_router,      prefix="/api")
app.include_router(transcribe_router, prefix="/api")
app.include_router(polish_router,     prefix="/api")

# ── 静态文件（管理 Web UI）──────────────────────────────────
if os.path.exists(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_admin():
        """根路径：返回管理后台 HTML"""
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
