from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import StrictModel


class ChatMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class ChatRequest(StrictModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    temperature: float = Field(default=0.3, ge=0, le=2, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded_context(self):
        if sum(len(message.content) for message in self.messages) > 48000:
            raise ValueError("Conversation exceeds the context size limit")
        if self.messages[-1].role != "user":
            raise ValueError("Conversation must end with a user message")
        return self


class SpeechRequest(StrictModel):
    text: str = Field(min_length=1, max_length=8000)
    language: str = Field(default="en-US", pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,8})?$")
    rate: float = Field(default=1, ge=0.5, le=2, allow_inf_nan=False)
    pitch: float = Field(default=1, ge=0, le=2, allow_inf_nan=False)
