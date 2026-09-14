"""模型配置服务：可选模型清单、当前选中模型、新增模型与连接测试。

安全说明：演示项目**不在数据库里保存 API Key 明文**，只保留后四位提示；
真正生效的密钥始终来自后端环境变量（`LLM_API_KEY`）。
这样「模型配置」页既完成了交互闭环，又不会把一个可用的凭据写进数据库。
"""

import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.biz import ModelSetting

# 首次启动时写入的预置模型（与 demo 的 mcDefaultModels 对应）
DEFAULT_MODELS: list[dict[str, str]] = [
    {
        "name": "GLM-4-Plus（智谱）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model_name": "glm-4-plus",
    },
    {
        "name": "DeepSeek-V3",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat",
    },
    {
        "name": "Qwen2.5-72B（通义）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen2.5-72b-instruct",
    },
    {
        "name": "GPT-4o mini",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o-mini",
    },
]


class ModelService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def ensure_seeded(self) -> None:
        async with self.session_factory() as session:
            existing = (await session.execute(select(ModelSetting.id))).first()
            if existing:
                return
            for index, item in enumerate(DEFAULT_MODELS):
                session.add(
                    ModelSetting(
                        name=item["name"],
                        base_url=item["base_url"],
                        model_name=item["model_name"],
                        selected=1 if index == 0 else 0,
                    )
                )
            await session.commit()

    async def list_models(self) -> list[dict[str, Any]]:
        await self.ensure_seeded()
        async with self.session_factory() as session:
            rows = (
                (await session.execute(select(ModelSetting).order_by(ModelSetting.id.asc())))
                .scalars()
                .all()
            )
        return [self._to_dict(row) for row in rows]

    async def select(self, model_id: int) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            rows = (await session.execute(select(ModelSetting))).scalars().all()
            target = None
            for row in rows:
                row.selected = 1 if row.id == model_id else 0
                if row.id == model_id:
                    target = row
            await session.commit()
            return self._to_dict(target) if target else None

    async def add_model(
        self, *, base_url: str, model_name: str, api_key: str = "", name: str = ""
    ) -> dict[str, Any]:
        display = name or model_name
        async with self.session_factory() as session:
            row = ModelSetting(
                name=display,
                base_url=base_url,
                model_name=model_name,
                api_key_hint=_hint(api_key),
                note="用户新增",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def delete_model(self, model_id: int) -> bool:
        async with self.session_factory() as session:
            row = await session.get(ModelSetting, model_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    @staticmethod
    async def test_connection(*, base_url: str, model_name: str, api_key: str) -> dict[str, Any]:
        """真实发起一次极小的请求，而不是「假装成功」。

        没填 Key 时退化为「检查当前后端是否已配置可用模型」，
        避免把未验证的配置标成连接成功。
        """
        key = api_key.strip() or settings.llm_api_key
        target_url = base_url.strip() or settings.llm_base_url
        model = model_name.strip() or settings.llm_model
        if not key:
            return {
                "ok": False,
                "message": "未提供 API Key，且后端环境变量中也没有配置可用密钥",
                "latency_ms": 0,
                "checked": "local",
            }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{target_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                        "temperature": 0,
                    },
                )
            latency = int((time.perf_counter() - started) * 1000)
            if response.status_code < 400:
                return {"ok": True, "message": "连接成功", "latency_ms": latency, "checked": "remote"}
            return {
                "ok": False,
                "message": f"HTTP {response.status_code}: {response.text[:200]}",
                "latency_ms": latency,
                "checked": "remote",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "message": f"请求失败：{exc}",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "checked": "remote",
            }

    @staticmethod
    def runtime_model() -> dict[str, Any]:
        """当前后端真实生效的模型（来自环境变量）。"""
        return {
            "provider": settings.llm_provider,
            "model_name": settings.llm_model,
            "base_url": settings.llm_base_url,
            "configured": bool(settings.llm_api_key.strip()),
            "temperature": settings.llm_temperature,
            "use_llm": settings.use_llm,
        }

    @staticmethod
    def _to_dict(row: ModelSetting) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "base_url": row.base_url,
            "model_name": row.model_name,
            "api_key_hint": row.api_key_hint,
            "selected": bool(row.selected),
            "reachable": bool(row.reachable),
            "latency_ms": row.latency_ms,
            "note": row.note,
        }


def _hint(api_key: str) -> str:
    key = (api_key or "").strip()
    if not key:
        return ""
    return f"****{key[-4:]}" if len(key) > 4 else "****"
