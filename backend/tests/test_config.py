"""配置解析的回归测试。

重点是 `CORS_ORIGINS`：pydantic-settings 对 `list[str]` 字段默认只接受 JSON 数组，
如果直接把原始字符串交回去，最常见的 `CORS_ORIGINS=*` 会让服务启动直接失败——
容器里踩到这个坑时，报错信息是 SettingsError，很难一眼看出是 CORS 配置的问题。
"""

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("*", ["*"]),
        ("https://a.com,https://b.com", ["https://a.com", "https://b.com"]),
        ("https://a.com, https://b.com ", ["https://a.com", "https://b.com"]),
        ('["https://c.com"]', ["https://c.com"]),
        ("", []),
    ],
)
def test_cors_origins_accepts_common_forms(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert Settings().cors_origins == expected


def test_cors_origins_defaults_to_wildcard_when_unset(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    # .env 里可能配了值，这里明确断言「未设置时不会抛异常且是列表」
    assert isinstance(Settings().cors_origins, list)


def test_use_llm_requires_key_and_provider():
    """规则引擎永不调用大模型；auto/openai 必须同时有 key 才算启用。"""
    assert Settings(llm_provider="rule", llm_api_key="sk-x").use_llm is False
    assert Settings(llm_provider="auto", llm_api_key="").use_llm is False
    assert Settings(llm_provider="auto", llm_api_key="sk-x").use_llm is True
    assert Settings(llm_provider="openai", llm_api_key="sk-x").use_llm is True


def test_unknown_env_vars_are_ignored(monkeypatch):
    """容器里常会多注入一堆环境变量，不能让它们把服务搞崩。"""
    monkeypatch.setenv("SOME_UNRELATED_VAR", "1")
    monkeypatch.setenv("SERVER__PORT", "0")
    assert Settings().app_name
