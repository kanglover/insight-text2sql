"""FastAPI 依赖注入。

服务对象本身无状态（只持有 session_factory），因此可以在应用级别复用单例，
由 FastAPI 的 Depends 提供，路由里不再出现任何 `new`。
"""

from functools import lru_cache

from app.db.session import Database, db
from app.services.config_service import ConfigService
from app.services.feedback_service import FeedbackService
from app.services.log_service import LogService
from app.services.model_service import ModelService
from app.services.query_service import QueryService
from app.services.session_service import SessionService


def get_database() -> Database:
    return db


@lru_cache
def get_session_service() -> SessionService:
    return SessionService(db.session_factory)


@lru_cache
def get_log_service() -> LogService:
    return LogService(db.session_factory)


@lru_cache
def get_feedback_service() -> FeedbackService:
    return FeedbackService(db.session_factory)


@lru_cache
def get_config_service() -> ConfigService:
    return ConfigService(db.session_factory)


@lru_cache
def get_model_service() -> ModelService:
    return ModelService(db.session_factory)


@lru_cache
def get_query_service() -> QueryService:
    return QueryService(
        db,
        session_service=get_session_service(),
        log_service=get_log_service(),
    )
