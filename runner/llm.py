# -*- coding: utf-8 -*-
"""LLM 调用层：OpenAI 兼容的 /chat/completions，**只用标准库 urllib**。

为什么不用 `openai` 包：官方评测环境是别人的机器，少一个依赖就少一类装不上的可能。
我们只需要一个 POST，stdlib 足够；顺带让 `requirements.txt` 保持"几乎为空"。

支持：
- `BIRD_API_KEY` / `BIRD_BASE_URL` / `BIRD_MODEL` 环境变量
- 429/5xx/网络错误 → 指数退避重试（默认 4 次）
- token 统计（`usage`）—— 官方要求提前报 prompt token 数
- `mock`：离线自测用的假响应，不联网（`--mock` 走这条路）
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"   # DeepSeek 现行正式名（`deepseek-chat` 是遗留名，官方已宣布下线）
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """调用失败（重试耗尽 / 非重试类错误）。调用方应把它记进日志并跳过该题。"""


class LLMClient:
    def __init__(self, model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, temperature: float = 0.0,
                 timeout: float = 180.0, http_retries: int = 4,
                 thinking: str = "disabled",
                 mock=None, verbose: bool = False):
        self.model = model or os.environ.get("BIRD_MODEL") or DEFAULT_MODEL
        self.api_key = api_key or os.environ.get("BIRD_API_KEY") or ""
        self.base_url = (base_url or os.environ.get("BIRD_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.http_retries = http_retries
        self.thinking = thinking          # disabled / enabled / default
        self.mock = mock                  # Callable[[list[dict]], str] | None
        self.verbose = verbose
        if not self.mock and not self.api_key:
            raise LLMError("没有 API key：设置 BIRD_API_KEY，或用 --mock 跑离线自测")

    # ------------------------------------------------------------------ 公开接口

    def chat(self, messages: list[dict], max_tokens: int = 2048) -> tuple[str, dict]:
        """返回 (文本, usage)。usage 至少含 prompt_tokens / completion_tokens。"""
        if self.mock is not None:
            text = self.mock(messages)
            return text, {"prompt_tokens": 0, "completion_tokens": 0, "mock": True}

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        # DeepSeek 的 `deepseek-flash` **默认开思考模式**（响应带 reasoning_content）：
        # 难题会思考十几分钟（实测单题 1107s），且 reasoning tokens 按输出计费。
        # 默认显式关掉 —— 与本项目 dev 成绩产生的口径一致（agent 当时 reasoning=off）。
        if self.thinking in ("disabled", "enabled"):
            payload["thinking"] = {"type": self.thinking}
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        last_err = ""
        for attempt in range(self.http_retries + 1):
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8", "replace"))
                text = data["choices"][0]["message"]["content"] or ""
                usage = data.get("usage") or {}
                return text, {
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                }
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:400]
                last_err = f"HTTP {e.code}: {detail}"
                if e.code not in RETRY_STATUS:
                    raise LLMError(last_err) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = f"{type(e).__name__}: {e}"
            except (KeyError, IndexError, ValueError) as e:
                raise LLMError(f"响应解析失败（{type(e).__name__}: {e}）") from None

            if attempt < self.http_retries:
                wait = min(2 ** attempt, 20)
                if self.verbose:
                    print(f"    [llm] {last_err} → {wait}s 后重试（{attempt + 1}/{self.http_retries}）")
                time.sleep(wait)
        raise LLMError(f"重试 {self.http_retries} 次仍失败：{last_err}")
