"""应用配置服务：应用配置开关、开场白、快捷提问（常问 / 收藏）。"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.biz import AppSetting
from app.services.log_service import LogService

APP_CONFIG_KEY = "app_config"

DEFAULT_APP_CONFIG: dict[str, Any] = {
    "greeting": True,
    "suggestions": True,
    # 语音能力默认开启：入口可见，用户可在「应用配置」里关掉。
    # 前端会再探测一次浏览器能力，不支持时按钮置灰而不是隐藏。
    "tts": True,
    "stt": True,
    "hotRecommend": True,
    "modelConfig": True,
    "greetingText": "欢迎使用智能AI问数，您可以向我咨询经营数据、报表分析相关问题。",
    "greetingQuestions": [
        "2026年各经营单元的收入和完成率分别是多少",
        "各产品线的收入占比",
        "高风险项目有哪些",
        "2026年各行业的收入是多少",
    ],
    "hotThreshold": 3,
    "favorites": [],
    "maxGreetingQuestions": 10,
}

# 没有任何问数历史时，「常问」用这组推荐问题兜底
FALLBACK_HOT = [
    "2026年各经营单元的收入排名",
    "各产品线的收入占比",
    "高风险项目有哪些",
    "2026年每月合同金额趋势",
]


class ConfigService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory
        self.logs = LogService(session_factory)

    async def get_app_config(self) -> dict[str, Any]:
        async with self.session_factory() as session:
            row = await session.get(AppSetting, APP_CONFIG_KEY)
            stored = _loads(row.value) if row else {}
        return {**DEFAULT_APP_CONFIG, **stored}

    async def save_app_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = await self.get_app_config()
        merged = {**current, **{k: v for k, v in patch.items() if v is not None}}
        # 白名单裁剪，避免前端塞入任意键
        allowed = set(DEFAULT_APP_CONFIG)
        merged = {k: v for k, v in merged.items() if k in allowed}
        if isinstance(merged.get("greetingQuestions"), list):
            merged["greetingQuestions"] = [
                str(q)[:100] for q in merged["greetingQuestions"] if str(q).strip()
            ][: DEFAULT_APP_CONFIG["maxGreetingQuestions"]]
        if isinstance(merged.get("favorites"), list):
            merged["favorites"] = [str(q)[:200] for q in merged["favorites"] if str(q).strip()][:200]

        async with self.session_factory() as session:
            row = await session.get(AppSetting, APP_CONFIG_KEY)
            payload = json.dumps(merged, ensure_ascii=False)
            if row is None:
                session.add(AppSetting(key=APP_CONFIG_KEY, value=payload))
            else:
                row.value = payload
            await session.commit()
        return merged

    async def toggle_favorite(self, question: str) -> list[str]:
        config = await self.get_app_config()
        favorites: list[str] = list(config.get("favorites") or [])
        if question in favorites:
            favorites.remove(question)
        else:
            favorites.insert(0, question)
        saved = await self.save_app_config({"favorites": favorites})
        return saved.get("favorites", [])

    async def quick_questions(self) -> dict[str, Any]:
        """快捷提问面板：常问（按频次）+ 收藏 + 推荐。"""
        config = await self.get_app_config()
        threshold = int(config.get("hotThreshold") or 3)
        hot = dedupe(await self.logs.hot_questions(days=90, threshold=threshold))
        if not hot:
            # 没有达到阈值的历史问题时，用推荐问题兜底，保证面板不空
            hot = list(FALLBACK_HOT)
        favorites = dedupe(config.get("favorites") or [])
        recommend = dedupe(q for q in [*hot, *FALLBACK_HOT] if q not in favorites)[:6]
        return {"recent": hot, "favorite": favorites, "recommend": recommend}


def dedupe(items: Any) -> list[str]:
    """按首次出现顺序去重（Python 的 dict 保序，set 会打乱顺序）。"""
    seen: dict[str, None] = {}
    for item in items:
        text = str(item).strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
