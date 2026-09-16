"""大模型客户端（OpenAI 兼容协议）。

直接基于 httpx 实现 `/chat/completions` 调用，不额外引入 SDK：
依赖更少、可控性更强，测试里也能轻松指向一个本地桩服务。

`LLMClient` 是一个 Protocol，`NullLLM` 表示「不可用」，
流水线据此决定是否回退到规则引擎。
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import settings


class LLMUnavailable(RuntimeError):
    """没有配置大模型，或调用失败到无法继续。"""


@dataclass
class LLMResponse:
    text: str
    total_tokens: int = 0
    model: str = ""
    provider: str = "llm"


_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", re.MULTILINE)


def strip_code_fence(text: str) -> str:
    """模型很爱把 SQL 包在 ```sql 里，统一剥掉。"""
    if not text:
        return ""
    cleaned = _FENCE_RE.sub("", text).strip()
    return cleaned


@runtime_checkable
class LLMClient(Protocol):
    @property
    def available(self) -> bool: ...

    async def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...


class NullLLM:
    """未配置大模型时的占位实现。"""

    @property
    def available(self) -> bool:
        return False

    async def complete(self, system: str, user: str, **_: Any) -> LLMResponse:
        raise LLMUnavailable("未配置大模型 API Key")


class OpenAICompatLLM:
    """任何兼容 OpenAI /chat/completions 的服务都能用（OpenAI、DeepSeek、通义、GLM…）。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout
        self.max_retries = max_retries if max_retries is not None else settings.llm_max_retries

    @property
    def available(self) -> bool:
        return bool(self.api_key.strip())

    async def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if not self.available:
            raise LLMUnavailable("未配置大模型 API Key")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": settings.llm_temperature if temperature is None else temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                text = message.get("content") or ""
                usage = data.get("usage") or {}
                return LLMResponse(
                    text=text.strip(),
                    total_tokens=int(usage.get("total_tokens") or 0),
                    model=data.get("model") or self.model,
                )
            except Exception as exc:  # noqa: BLE001 - 统一转成 LLMUnavailable 让上层降级
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.6 * (attempt + 1))
        raise LLMUnavailable(f"大模型调用失败：{last_error}")


def build_llm(
    provider: str | None = None,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """按配置构造 LLM 客户端；未配置 Key 时返回 NullLLM。

    `provider="rule"` 时强制走规则引擎（不调用大模型）。
    传入 base_url / api_key / model 可覆盖环境变量默认值（用于「模型配置」选中的模型）；
    任一参数为 None 时回退到对应的环境变量。
    """
    mode = (provider or settings.llm_provider).lower()
    if mode == "rule":
        return NullLLM()
    client = OpenAICompatLLM(base_url=base_url, api_key=api_key, model=model)
    return client if client.available else NullLLM()
