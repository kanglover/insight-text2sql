"""测试替身：可控的假大模型。

单元测试不应该依赖外部网络与模型随机性，因此这里用「脚本化的响应队列」
模拟大模型：想让它先返回坏 SQL 再返回好 SQL，只需要按顺序塞两条响应。
"""

from typing import Any

from app.text2sql.llm import LLMResponse, LLMUnavailable
from app.text2sql.prompts import SQL_SYSTEM_PROMPT


class ScriptedLLM:
    def __init__(self, responses: list[str] | None = None, *, available: bool = True) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    async def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        if not self._available:
            raise LLMUnavailable("测试环境未启用大模型")
        if not self.responses:
            raise LLMUnavailable("脚本化响应已用尽")
        text = self.responses.pop(0)
        return LLMResponse(text=text, total_tokens=42, model="scripted")

    @property
    def sql_prompts(self) -> list[str]:
        """只看发往「SQL 生成」的 Prompt。"""
        return [c["user"] for c in self.calls if c["system"] == SQL_SYSTEM_PROMPT]
