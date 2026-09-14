"""SQL 生成器门面：在「大模型」与「规则引擎」之间做选择与降级。

选择逻辑（`LLM_PROVIDER`）：
- ``openai``：只走大模型，失败即报错（线上严格模式）；
- ``rule``：只走规则引擎（离线、单测、对照实验）；
- ``auto``：优先大模型，调用异常时自动降级到规则引擎，并在事件里如实标注。

无论哪条路径，产出的 SQL 都还要过 ``sql_guard``，生成器不负责安全。
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.log import get_logger
from app.entities import MetaSnapshot
from app.text2sql.generators.llm_generator import llm_generate_sql
from app.text2sql.generators.rule_generator import generate_with_rules
from app.text2sql.llm import LLMClient, LLMUnavailable
from app.text2sql.prompts import SQL_SYSTEM_PROMPT, build_feedback_prompt, build_sql_prompt

logger = get_logger(__name__)


@dataclass
class GeneratedSql:
    sql: str
    provider: str  # llm / rule
    prompt: str = ""
    intent: str = ""
    confidence: float = 0.0
    reason: str = ""
    tokens: int = 0
    fallback_reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


async def generate_sql(
    *,
    query: str,
    snapshot: MetaSnapshot,
    llm: LLMClient,
    provider: str,
    tables: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    values: list[dict[str, Any]],
    date_info: dict[str, str],
    db_info: dict[str, str],
    examples: list[dict[str, Any]],
    join_paths: list[str] | None = None,
) -> GeneratedSql:
    mode = (provider or settings.llm_provider).lower()
    want_llm = mode in {"auto", "openai"}
    prompt = build_sql_prompt(query, tables, metrics, values, date_info, db_info, examples, join_paths)

    if want_llm and llm.available:
        try:
            sql, tokens = await llm_generate_sql(llm, prompt)
            if sql:
                return GeneratedSql(sql=sql, provider="llm", prompt=prompt, tokens=tokens)
            raise LLMUnavailable("大模型返回了空 SQL")
        except LLMUnavailable as exc:
            if mode == "openai":
                raise
            logger.warning("大模型生成失败，降级到规则引擎：%s", exc)
            rule = generate_with_rules(query, snapshot)
            return GeneratedSql(
                sql=rule.sql,
                provider="rule",
                prompt=prompt,
                intent=rule.intent,
                confidence=rule.confidence,
                reason=rule.reason,
                fallback_reason=str(exc),
            )

    rule = generate_with_rules(query, snapshot)
    return GeneratedSql(
        sql=rule.sql,
        provider="rule",
        prompt=prompt,
        intent=rule.intent,
        confidence=rule.confidence,
        reason=rule.reason,
        fallback_reason="" if mode == "rule" or not llm.available else "未配置大模型 API Key",
    )


async def correct_sql(
    *,
    llm: LLMClient,
    first_prompt: str,
    failed_sql: str,
    error: str,
    fallback_sql: str,
    dialect: str = "sqlite",
) -> GeneratedSql:
    """修正失败 SQL：优先让 LLM 带着报错重写；不可用时回退到规则引擎的 SQL。"""
    if llm.available and first_prompt:
        try:
            response = await llm.complete(
                SQL_SYSTEM_PROMPT,
                build_feedback_prompt(first_prompt, failed_sql, error, dialect),
            )
            from app.text2sql.llm import strip_code_fence

            sql = strip_code_fence(response.text)
            if sql:
                return GeneratedSql(sql=sql, provider="llm", tokens=response.total_tokens)
        except LLMUnavailable as exc:
            logger.warning("SQL 修正失败，使用规则引擎结果：%s", exc)
    return GeneratedSql(
        sql=fallback_sql,
        provider="rule",
        reason="规则引擎兜底 SQL",
        fallback_reason=error,
    )
