"""日志与请求上下文。"""

import logging
import sys
from contextvars import ContextVar

# 每次请求注入 request_id，便于在海量日志里串起同一条链路
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_CONFIGURED = False


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-5s | %(request_id)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # 降低第三方库噪声
    for noisy in ("httpx", "httpcore", "jieba"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
