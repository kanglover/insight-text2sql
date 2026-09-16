"""模型配置服务：可选模型清单、当前选中模型、新增模型与连接测试。

行为说明：
- 模型全部由用户在前端「模型配置」页自行新增，后端**不预置任何模型**；
  初始数据库里 `biz_model_setting` 为空，前端会提示「点击新增模型添加一个」。
- 用户选择的模型（selected=1）会**真正用于推理链路**：`query_service` 构造 LLM 时
  读取该模型的 base_url / model_name / api_key，缺省时回退到后端环境变量
  （LLM_BASE_URL / LLM_MODEL / LLM_API_KEY）。
- `api_key_hint` 只用于页面展示（后四位），不参与鉴权；真实 Key 保存在 `api_key` 列。
"""

import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.models.biz import ModelSetting


class ModelService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def list_models(self) -> list[dict[str, Any]]:
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
                api_key=api_key.strip(),
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

    async def get_selected(self) -> ModelSetting | None:
        """返回当前被选中的模型记录（selected=1），没有则返回 None。"""
        async with self.session_factory() as session:
            return (
                await session.execute(
                    select(ModelSetting).where(ModelSetting.selected == 1)
                )
            ).scalars().first()

    async def selected_connection(self) -> dict[str, Any] | None:
        """选中模型的连接参数（供推理链路构造 LLM 使用）。

        返回 {base_url, api_key, model_name}，缺省为 None（让调用方回退到环境变量）。
        """
        row = await self.get_selected()
        if row is None:
            return None
        return {
            "base_url": row.base_url.strip() or None,
            "api_key": row.api_key.strip() or None,
            "model_name": row.model_name.strip() or None,
        }

    async def effective_model(self) -> dict[str, Any]:
        """当前后端真实生效的模型：优先用「选中的模型」，缺 Key 时回退环境变量。"""
        row = await self.get_selected()
        has_db_key = bool(row and row.api_key.strip())
        if row and (has_db_key or settings.llm_api_key.strip()):
            base_url = row.base_url.strip() or settings.llm_base_url
            model_name = row.model_name.strip() or settings.llm_model
            api_key = row.api_key.strip() or settings.llm_api_key
            source = "db_selected"
            selected_id = row.id
        else:
            base_url = settings.llm_base_url
            model_name = settings.llm_model
            api_key = settings.llm_api_key
            source = "env"
            selected_id = None
        return {
            "source": source,
            "selected_id": selected_id,
            "provider": settings.llm_provider,
            "model_name": model_name,
            "base_url": base_url,
            "configured": bool(api_key.strip()),
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
            "has_key": bool(row.api_key.strip()),
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
