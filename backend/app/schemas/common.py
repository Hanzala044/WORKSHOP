from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    module: str
    title: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    input_summary: dict
    output_metadata: dict
    error: str | None
    duration_ms: int | None

    @field_validator("started_at", "completed_at")
    @classmethod
    def utc_dates(cls, value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


class Preferences(StrictModel):
    theme: Literal["system", "light", "dark"] = "system"
    speech_language: str = Field(default="en-US", pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,8})?$")
    speech_rate: float = Field(default=1, ge=0.5, le=2, allow_inf_nan=False)


class PreferencesPatch(StrictModel):
    theme: Literal["system", "light", "dark"] | None = None
    speech_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,8})?$")
    speech_rate: float | None = Field(default=None, ge=0.5, le=2, allow_inf_nan=False)
