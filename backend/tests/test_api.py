"""REST 接口测试（httpx ASGITransport，不启动真实端口）。"""

import json

import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_query_returns_full_result(client, monkeypatch):
    # 接口测试不依赖真实大模型
    monkeypatch.setenv("LLM_PROVIDER", "rule")
    from app.core import config as config_module

    config_module.get_settings.cache_clear()
    config_module.settings.llm_provider = "rule"

    response = await client.post(
        "/api/chat/query", json={"question": "2026年各行业的收入排名"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "rule"
    assert data["row_count"] == 14
    assert data["columns"] == ["行业", "收入额"]
    assert data["chart"]["type"] == "bar"
    assert data["answer"]
    assert data["steps"]


@pytest.mark.asyncio
async def test_chat_stream_emits_sse_and_persists_session(client):
    from app.core import config as config_module

    config_module.settings.llm_provider = "rule"

    async with client.stream(
        "POST", "/api/chat/stream", json={"question": "目前有多少个高风险项目"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    kinds = [e["type"] for e in events]
    assert "session" in kinds
    assert "result" in kinds
    assert "done" in kinds

    session_event = next(e for e in events if e["type"] == "session")
    session_id = session_event["session"]["id"]

    detail = (await client.get(f"/api/sessions/{session_id}")).json()["data"]
    assert detail["msg_count"] == 2
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["payload"]["sql"]


@pytest.mark.asyncio
async def test_session_crud(client):
    created = (await client.post("/api/sessions", json={"title": "测试会话"})).json()["data"]
    session_id = created["id"]

    listed = (await client.get("/api/sessions")).json()["data"]
    assert any(s["id"] == session_id for s in listed)

    renamed = (
        await client.put(f"/api/sessions/{session_id}/title", json={"title": "改名了"})
    ).json()["data"]
    assert renamed["title"] == "改名了"

    pinned = (await client.post(f"/api/sessions/{session_id}/pin")).json()["data"]
    assert pinned["pinned"] is True

    assert (await client.delete(f"/api/sessions/{session_id}")).json()["data"]["deleted"]
    assert (await client.get(f"/api/sessions/{session_id}")).status_code == 404


@pytest.mark.asyncio
async def test_quick_questions_and_favorites(client):
    data = (await client.get("/api/sessions/quick-questions")).json()["data"]
    assert set(data) == {"recent", "favorite", "recommend"}
    assert data["recent"]

    await client.post("/api/sessions/favorites", params={"question": "各产品线的收入占比"})
    data = (await client.get("/api/sessions/quick-questions")).json()["data"]
    assert "各产品线的收入占比" in data["favorite"]

    await client.post("/api/sessions/favorites", params={"question": "各产品线的收入占比"})
    data = (await client.get("/api/sessions/quick-questions")).json()["data"]
    assert "各产品线的收入占比" not in data["favorite"]


@pytest.mark.asyncio
async def test_feedback_flow(client):
    created = (
        await client.post(
            "/api/feedback",
            json={
                "session_id": 0,
                "question": "上季度销售目标达成率",
                "user_name": "张经理",
                "message": "数据有误，实际达成率应为 85%",
            },
        )
    ).json()["data"]
    assert created["status"] == "待处理"

    listed = (await client.get("/api/feedback", params={"status": "待处理"})).json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["user_name"] == "张经理"

    updated = (
        await client.put(f"/api/feedback/{created['id']}", json={"status": "已处理", "remark": "已核查"})
    ).json()["data"]
    assert updated["status"] == "已处理"
    assert updated["remark"] == "已核查"

    stats = (await client.get("/api/feedback/stats")).json()["data"]
    assert stats["total"] == 1
    assert stats["pending"] == 0


@pytest.mark.asyncio
async def test_feedback_search_and_filter(client):
    for i in range(3):
        await client.post(
            "/api/feedback",
            json={"session_id": 0, "question": f"问题{i}", "user_name": "李主管"},
        )
    await client.post(
        "/api/feedback", json={"session_id": 0, "question": "收入口径", "user_name": "王主任"}
    )

    by_keyword = (await client.get("/api/feedback", params={"keyword": "收入"})).json()["data"]
    assert by_keyword["total"] == 1

    by_user = (await client.get("/api/feedback", params={"user_keyword": "李"})).json()["data"]
    assert by_user["total"] == 3

    paged = (await client.get("/api/feedback", params={"page": 2, "page_size": 2})).json()["data"]
    assert len(paged["items"]) == 2


@pytest.mark.asyncio
async def test_app_config_get_and_patch(client):
    config = (await client.get("/api/config/app")).json()["data"]
    assert config["greeting"] is True
    assert config["greetingText"]
    assert isinstance(config["greetingQuestions"], list)

    patched = (
        await client.patch(
            "/api/config/app",
            json={"greeting": False, "hotThreshold": 5, "greetingText": "新的开场白"},
        )
    ).json()["data"]
    assert patched["greeting"] is False
    assert patched["hotThreshold"] == 5
    assert patched["greetingText"] == "新的开场白"

    # 未提交的字段应保持原值
    assert patched["suggestions"] is True

    reloaded = (await client.get("/api/config/app")).json()["data"]
    assert reloaded["greeting"] is False


@pytest.mark.asyncio
async def test_app_config_truncates_greeting_questions(client):
    too_many = [f"问题{i}" for i in range(20)]
    data = (
        await client.patch("/api/config/app", json={"greetingQuestions": too_many})
    ).json()["data"]
    assert len(data["greetingQuestions"]) == 10


@pytest.mark.asyncio
async def test_app_config_voice_switches_round_trip(client):
    """语音开关（tts 播报 / stt 语音输入）默认开启，且改动能持久化。

    前端据此决定是否渲染「语音播放」与麦克风按钮，所以这里的默认值
    与持久化行为都属于对外契约，改动需同步前端。
    """
    config = (await client.get("/api/config/app")).json()["data"]
    assert config["tts"] is True
    assert config["stt"] is True

    off = (await client.patch("/api/config/app", json={"tts": False, "stt": False})).json()["data"]
    assert off["tts"] is False
    assert off["stt"] is False

    # 重新读取，确认真的落库而不是只改了返回值
    reloaded = (await client.get("/api/config/app")).json()["data"]
    assert reloaded["tts"] is False
    assert reloaded["stt"] is False

    # 局部更新：只回开 tts，stt 必须保持关闭
    partial = (await client.patch("/api/config/app", json={"tts": True})).json()["data"]
    assert partial["tts"] is True
    assert partial["stt"] is False


@pytest.mark.asyncio
async def test_models_endpoints(client):
    # 后端不预置模型：初始列表为空，由用户自行新增
    models = (await client.get("/api/models")).json()["data"]
    assert isinstance(models, list)

    added = (
        await client.post(
            "/api/models",
            json={
                "base_url": "https://example.com/v1",
                "model_name": "my-model",
                "api_key": "sk-test-123456",
                "name": "自建模型",
            },
        )
    ).json()["data"]
    assert added["api_key_hint"] == "****3456"  # 只留后四位
    assert added["name"] == "自建模型"

    # 选中刚新增的模型
    selected = (await client.post("/api/models/select", params={"model_id": added["id"]})).json()["data"]
    assert selected["selected"] is True

    # 列表里恰好有一个被选中
    models_after = (await client.get("/api/models")).json()["data"]
    assert sum(1 for m in models_after if m["selected"]) == 1

    assert (await client.delete(f"/api/models/{added['id']}")).json()["data"]["deleted"]


@pytest.mark.asyncio
async def test_selected_model_drives_effective_model(client, monkeypatch):
    """选中带 Key 的模型后，runtime 接口应反映 db_selected 来源与对应模型名。"""
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "llm_api_key", "")

    before = (await client.get("/api/config/runtime")).json()["data"]["model"]
    assert before["source"] == "env"

    added = (
        await client.post(
            "/api/models",
            json={
                "base_url": "https://api.deepseek.com/v1",
                "model_name": "deepseek-chat",
                "api_key": "sk-selected-9999",
                "name": "选中模型",
            },
        )
    ).json()["data"]
    await client.post("/api/models/select", params={"model_id": added["id"]})

    after = (await client.get("/api/config/runtime")).json()["data"]["model"]
    assert after["source"] == "db_selected"
    assert after["selected_id"] == added["id"]
    assert after["model_name"] == "deepseek-chat"
    assert after["base_url"] == "https://api.deepseek.com/v1"
    assert after["configured"] is True


def test_build_llm_overrides(monkeypatch):
    """build_llm 的 base_url/api_key/model 覆盖应生效；rule 模式强制走规则引擎。"""
    from app.core import config as config_module
    from app.text2sql.llm import NullLLM, OpenAICompatLLM, build_llm

    # 清空环境变量 Key，确保「无 Key」分支可控
    monkeypatch.setattr(config_module.settings, "llm_api_key", "")

    rule = build_llm("rule")
    assert isinstance(rule, NullLLM)

    llm = build_llm("auto", base_url="https://x/v1", api_key="sk-abc", model="my-model")
    assert isinstance(llm, OpenAICompatLLM)
    assert llm.base_url == "https://x/v1"
    assert llm.api_key == "sk-abc"
    assert llm.model == "my-model"
    assert llm.available is True

    # 没有任何可用 Key 时（覆盖为空且环境变量也为空）回退到 NullLLM，不发起真实请求
    no_key = build_llm("auto", base_url="https://x/v1", api_key=None, model="my-model")
    assert isinstance(no_key, NullLLM)


@pytest.mark.asyncio
async def test_model_test_connection_without_key(client, monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "llm_api_key", "")
    result = (
        await client.post(
            "/api/models/test",
            json={"base_url": "https://example.com/v1", "model_name": "x", "api_key": ""},
        )
    ).json()["data"]
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_logs_and_pipeline_and_metadata(client):
    summary = (await client.get("/api/logs/summary")).json()["data"]
    assert set(summary) >= {"total", "failed", "success_rate"}

    logs = (await client.get("/api/logs")).json()["data"]
    assert isinstance(logs, list)

    pipeline = (await client.get("/api/pipeline")).json()["data"]
    assert len(pipeline["nodes"]) >= 12
    assert "graph TD" in pipeline["mermaid"]

    metadata = (await client.get("/api/metadata")).json()["data"]
    assert len(metadata["tables"]) == 8
    assert len(metadata["metrics"]) == 10
    assert len(metadata["examples"]) == 20


@pytest.mark.asyncio
async def test_chat_query_validates_input(client):
    assert (await client.post("/api/chat/query", json={"question": ""})).status_code == 422
    too_long = await client.post("/api/chat/query", json={"question": "问" * 600})
    assert too_long.status_code == 422
