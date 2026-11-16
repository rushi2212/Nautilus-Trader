from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


class PreviewRequest(BaseModel):
    entry_call: float = Field(gt=0)
    entry_put: float = Field(gt=0)
    current_call_ask: float = Field(gt=0)
    current_put_ask: float = Field(gt=0)
    quantity: float = Field(default=1, gt=0)
    risk_management: bool = False

