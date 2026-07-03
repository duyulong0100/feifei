"""
LLM 客户端封装
支持所有 OpenAI 兼容接口：官方 GPT、Ollama 本地模型、其他兼容服务。
"""
import logging
from typing import Generator

log = logging.getLogger("飞飞转录.llm")

# 任务 → 提示词键名
TASKS = {
    "polish":  "润色",
    "segment": "分段",
    "both":    "润色+分段",
}


def stream_polish(text: str, task: str, llm_cfg: dict) -> Generator[dict, None, None]:
    """
    调用 LLM 对转录文字做润色/分段，逐 token 流式返回。

    每次 yield：
      {"type": "chunk", "text": "部分文字"}
      {"type": "done",  "text": "完整结果"}   ← 最后一条
      {"type": "error", "message": "..."}     ← 出错时

    Parameters
    ----------
    text     : 待处理的转录文字
    task     : "polish" | "segment" | "both"
    llm_cfg  : llm 配置子树（来自 config.load_config()["llm"]）
    """
    if not llm_cfg.get("enabled"):
        yield {"type": "error", "message": "LLM 功能未启用，请在管理后台开启并配置"}
        return

    base_url = llm_cfg.get("base_url", "").strip()
    api_key  = llm_cfg.get("api_key",  "").strip()
    model    = llm_cfg.get("model",    "gpt-4o-mini").strip()
    prompts  = llm_cfg.get("prompts",  {})

    if not base_url:
        yield {"type": "error", "message": "LLM base_url 未配置"}
        return
    if not model:
        yield {"type": "error", "message": "LLM 模型名称未配置"}
        return

    system_prompt = prompts.get(task, prompts.get("polish", ""))
    if not system_prompt:
        yield {"type": "error", "message": f"未找到任务「{task}」的系统提示词"}
        return

    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=base_url,
            api_key=api_key or "no-key",   # Ollama 等本地服务不需要真实 key
        )
        log.info("LLM polish start | model=%s task=%s chars=%d", model, task, len(text))
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": text},
            ],
            stream=True,
            timeout=120,
        )
        full = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                full.append(delta)
                yield {"type": "chunk", "text": delta}
        log.info("LLM polish done | chars_in=%d chars_out=%d", len(text), sum(len(s) for s in full))
        yield {"type": "done", "text": "".join(full)}

    except ImportError:
        yield {"type": "error", "message": "缺少 openai 依赖，请在服务端执行：pip install openai"}
    except Exception as e:
        log.exception("LLM polish error")
        yield {"type": "error", "message": str(e)}


def test_connection(llm_cfg: dict) -> dict:
    """
    测试 LLM 连接，返回 {"ok": bool, "message": str}
    同步调用，用于管理界面「测试连接」按钮。
    """
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=llm_cfg.get("base_url", "").strip(),
            api_key=llm_cfg.get("api_key",  "").strip() or "no-key",
        )
        # 用最小请求验证连通性
        resp = client.chat.completions.create(
            model=llm_cfg.get("model", "gpt-4o-mini"),
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
            timeout=10,
        )
        return {"ok": True, "message": f"连接成功（model: {resp.model}）"}
    except ImportError:
        return {"ok": False, "message": "缺少 openai 依赖：pip install openai"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
