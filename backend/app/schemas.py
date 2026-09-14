"""接口请求 / 响应模型。"""

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500, description="用户的自然语言问题")
    session_id: int | None = Field(default=None, description="续聊的会话 ID，为空则新建会话")
    user_name: str = Field(default="管理员", max_length=64)


class SessionRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)


class SessionCreateRequest(BaseModel):
    title: str = Field(default="新对话", max_length=128)
    user_name: str = Field(default="管理员", max_length=64)


class FeedbackCreateRequest(BaseModel):
    session_id: int = 0
    question: str = Field(min_length=1, max_length=500)
    user_name: str = Field(default="管理员", max_length=64)
    message: str = Field(default="数据有误，实际数据与 AI 回复不一致", max_length=1000)
    ai_reply: str = Field(default="", max_length=5000)


class FeedbackUpdateRequest(BaseModel):
    status: str = Field(default="", pattern="^(|待处理|已处理)$")
    remark: str = Field(default="", max_length=1000)


class AppConfigPatch(BaseModel):
    greeting: bool | None = None
    suggestions: bool | None = None
    tts: bool | None = None
    stt: bool | None = None
    hotRecommend: bool | None = None
    modelConfig: bool | None = None
    greetingText: str | None = Field(default=None, max_length=500)
    greetingQuestions: list[str] | None = None
    hotThreshold: int | None = Field(default=None, ge=1, le=100)
    favorites: list[str] | None = None


class ModelAddRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=255)
    model_name: str = Field(min_length=1, max_length=128)
    api_key: str = Field(default="", max_length=255)
    name: str = Field(default="", max_length=128)


class ModelTestRequest(BaseModel):
    base_url: str = Field(default="", max_length=255)
    model_name: str = Field(default="", max_length=128)
    api_key: str = Field(default="", max_length=255)


class ApiResponse(BaseModel):
    """统一返回体，方便前端用同一套错误处理逻辑。"""

    code: int = 0
    message: str = "ok"
    data: Any = None

    @classmethod
    def ok(cls, data: Any = None) -> "ApiResponse":
        return cls(code=0, message="ok", data=data)

    @classmethod
    def fail(cls, message: str, code: int = 1) -> "ApiResponse":
        return cls(code=code, message=message, data=None)
