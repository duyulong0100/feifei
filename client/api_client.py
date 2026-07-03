"""
HTTP + SSE 客户端封装
与服务端 /api/* 接口对接。
"""
import json
import logging
from typing import Iterator, Optional

import requests

log = logging.getLogger("飞飞转录.client.api")

DEFAULT_TIMEOUT_CONNECT = 5    # 秒：连接超时
DEFAULT_TIMEOUT_READ    = 120  # 秒：读取超时（转录长音频可能需要较长时间）


class ApiError(Exception):
    """API 调用失败"""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """
    飞飞转录服务端 HTTP 客户端。

    用法：
        client = ApiClient("http://localhost:8000")
        for event in client.transcribe_stream("path/to/audio.wav"):
            if event["type"] == "segment":
                print(event["text"])
    """

    def __init__(self, base_url: str = "http://localhost:8000", client_id: str = ""):
        self.base_url  = base_url.rstrip("/")
        self.client_id = client_id
        self._session  = requests.Session()
        self._session.headers.update({
            "Accept":       "application/json",
            "X-Client-ID":  client_id,   # 所有请求携带客户端身份
        })

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    # ── 连通性检测 ────────────────────────────────────────

    def ping(self) -> bool:
        """检测服务端是否可达，返回 True/False"""
        try:
            r = self._session.get(
                self._url("/api/config"),
                timeout=DEFAULT_TIMEOUT_CONNECT,
            )
            return r.ok
        except Exception:
            return False

    # ── 配置 ─────────────────────────────────────────────

    def get_config(self) -> dict:
        """
        获取当前服务端配置。
        返回：{model_size, quality_key, custom_path, model_loaded, current_model_id}
        """
        try:
            r = self._session.get(
                self._url("/api/config"),
                timeout=DEFAULT_TIMEOUT_CONNECT,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError:
            raise ApiError("无法连接服务端，请检查服务器是否运行")
        except requests.exceptions.Timeout:
            raise ApiError("连接超时")
        except requests.exceptions.HTTPError as e:
            raise ApiError(f"API 错误：{e}", e.response.status_code if e.response else 0)

    # ── 转录（SSE 流式）──────────────────────────────────

    def transcribe_stream(
        self,
        wav_path: str,
        ctx_prompt: Optional[str] = None,
        language: str = "zh",
    ) -> Iterator[dict]:
        """
        上传 WAV 文件到服务端进行转录，以迭代器方式逐事件返回 dict。

        每个 dict 形如：
          {"type": "segment", "text": "识别文字", "start": 0.0, "end": 1.5}
          {"type": "done"}
          {"type": "error", "message": "..."}

        调用方应检查 type 字段。
        """
        data: dict = {"language": language}
        if ctx_prompt:
            data["ctx_prompt"] = ctx_prompt

        try:
            with open(wav_path, "rb") as f:
                files = {"audio_file": ("audio.wav", f, "audio/wav")}
                resp = self._session.post(
                    self._url("/api/transcribe"),
                    files=files,
                    data=data,
                    stream=True,
                    timeout=(DEFAULT_TIMEOUT_CONNECT, DEFAULT_TIMEOUT_READ),
                )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            yield {"type": "error", "message": "无法连接服务端，请检查服务器是否运行"}
            return
        except requests.exceptions.Timeout:
            yield {"type": "error", "message": "连接超时"}
            return
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else 0
            body = ""
            try:
                body = e.response.json().get("detail", "") if e.response else ""
            except Exception:
                pass
            yield {"type": "error", "message": f"HTTP {code}：{body or str(e)}"}
            return

        yield from self._iter_sse(resp)

    # ── 内部：通用 SSE 流解析 ─────────────────────────────────

    def _iter_sse(self, resp) -> Iterator[dict]:
        buf = ""
        try:
            for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                buf += chunk
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    for line in block.splitlines():
                        if line.startswith("data: "):
                            try:
                                yield json.loads(line[6:])
                            except json.JSONDecodeError as e:
                                log.warning("SSE parse error: %s | line=%r", e, line)
        except Exception as e:
            log.exception("SSE stream error")
            yield {"type": "error", "message": f"流读取失败：{e}"}
