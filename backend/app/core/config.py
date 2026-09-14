"""应用配置。

所有可变项统一走环境变量（本地开发读 backend/.env），代码里不出现硬编码密钥。
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "var"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "经管问数 · Insight Text2SQL"
    debug: bool = False

    # ---- 数据库 ----
    # 默认 SQLite，零依赖即可跑起来；生产可通过环境变量切 MySQL / PostgreSQL
    #   MySQL:      mysql+aiomysql://user:pass@host:3306/insight?charset=utf8mb4
    #   PostgreSQL: postgresql+asyncpg://user:pass@host:5432/insight
    # 完整 DSN（SQLite 默认 / PostgreSQL 等不走组件式的特殊库用这个）
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'insight.db'}"
    # 组件式配置：设置 db_host 后自动拼成 MySQL 连接串，便于不同环境只换 host：
    #   本地裸跑    db_host=127.0.0.1
    #   docker 开发 db_host=mysql（compose 服务名）
    #   生产云库    db_host=<rds-endpoint>
    db_host: str = ""
    db_port: int = 3306
    db_user: str = "insight"
    db_password: str = "Insight_2026"
    db_name: str = "insight"
    db_echo: bool = False

    @property
    def effective_database_url(self) -> str:
        """db_host 优先：设置后自动拼 MySQL 连接串，否则回退到 database_url（SQLite / PG 等）。"""
        if self.db_host:
            return (
                f"mysql+aiomysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
            )
        return self.database_url
    # 长连接池的回收周期（秒）。MySQL 默认 wait_timeout=28800，但中间件 / 云数据库
    # 往往更短，池里留下已被对端掐断的连接就会报 2006。配合 pool_pre_ping 双保险。
    db_pool_recycle: int = 1800
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ---- 大模型（OpenAI 兼容协议）----
    # auto: 有 key 就走大模型，失败自动降级到规则引擎；openai: 只用大模型；rule: 只用规则引擎
    llm_provider: str = "auto"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_timeout: float = 60.0
    llm_max_retries: int = 1

    # ---- 问数安全与执行 ----
    sql_row_limit: int = 500
    sql_timeout_seconds: float = 15.0
    sql_max_correction_retry: int = 1

    # ---- 检索 ----
    recall_top_k: int = 12
    recall_max_tables: int = 6

    # NoDecode 关掉 pydantic-settings 对复杂类型的 JSON 预解析，
    # 把原始字符串直接交给下面的校验器，这样 `CORS_ORIGINS=*` 才不会被拒。
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        """兼容三种写法，避免用户踩 pydantic 的 JSON 解析坑。

        pydantic-settings 对 `list[str]` 字段默认只认 JSON 数组，于是最常见的
        `CORS_ORIGINS=*` 会直接抛 SettingsError 让服务起不来。这里统一按
        逗号分隔解析，`*`、`a.com,b.com`、`["a.com"]` 都能用。
        """
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                import json

                try:
                    return json.loads(text)
                except ValueError:
                    return [text]
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    @property
    def use_llm(self) -> bool:
        return self.llm_provider in {"auto", "openai"} and bool(self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
