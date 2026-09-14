"""基于大模型的 SQL 生成与结果解读。

这里只负责「拼好 Prompt 之后的模型调用」，Prompt 的拼装由 `prompts.py` 负责，
这样调用方（`generators/__init__.py`）手里始终持有原文 Prompt，
在 SQL 报错时可以直接把它交给修正节点，不必重新构造上下文。
"""

import json
import re
from typing import Any

from app.text2sql.llm import LLMClient, LLMUnavailable, strip_code_fence
from app.text2sql.prompts import ANSWER_SYSTEM_PROMPT, SQL_SYSTEM_PROMPT


async def llm_generate_sql(llm: LLMClient, prompt: str) -> tuple[str, int]:
    """调用大模型生成 SQL，返回 (sql, tokens)。"""
    response = await llm.complete(SQL_SYSTEM_PROMPT, prompt)
    return strip_code_fence(response.text), response.total_tokens


async def llm_summarize(
    llm: LLMClient,
    *,
    query: str,
    sql: str,
    columns: list[str],
    rows: list[list[Any]],
    max_tokens: int | None = None,
) -> tuple[str, int]:
    """让模型基于真实结果写结论；失败时由调用方回退到模板摘要。

    默认不限制 max_tokens —— 对 GLM / o 系列这类推理模型，
    输出额度会先被 reasoning 消耗，设太小会导致 content 为空。
    """
    from app.text2sql.prompts import build_answer_prompt

    response = await llm.complete(
        ANSWER_SYSTEM_PROMPT,
        build_answer_prompt(query, sql, columns, rows),
        max_tokens=max_tokens,
    )
    return response.text, response.total_tokens


async def llm_followups(llm: LLMClient, *, query: str, columns: list[str]) -> list[str]:
    """生成 3 条延伸问题；失败直接返回空列表，不影响主流程。"""
    try:
        response = await llm.complete(
            "你是一名企业经营分析助手。",
            f"用户刚刚问了：{query}\n查询结果字段：{json.dumps(columns, ensure_ascii=False)}\n"
            "请给出 3 条与该问题相关、且能进一步下钻的追问，每行一条，不要编号，不要解释。",
            max_tokens=1500,
        )
    except LLMUnavailable:
        return []
    lines = [_strip_list_marker(line) for line in response.text.splitlines()]
    return [line for line in lines if line][:3]


_MARKER_RE = re.compile(r"^\s*(?:\d+\s*[.、)）]|[（(]\s*\d+\s*[)）]|[-•*·]\s*)+")


def _strip_list_marker(line: str) -> str:
    """模型常带着「1. 」「- 」这类前缀返回，统一剥掉，避免污染延伸问题。"""
    return _MARKER_RE.sub("", line).strip()


__all__ = ["llm_generate_sql", "llm_summarize", "llm_followups", "LLMUnavailable"]
