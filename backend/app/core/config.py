from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WORKSHOP_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )

    data_dir: Path = BACKEND_DIR / "data"
    database_url: str | None = None
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_transcription_model: str = "whisper-large-v3-turbo"
    allowed_hosts: list[str] = Field(default_factory=list)
    trusted_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "[::1]"])
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    max_upload_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    max_request_bytes: int = Field(default=12 * 1024 * 1024, ge=1024, le=32 * 1024 * 1024)
    max_html_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=8 * 1024 * 1024)
    network_timeout: float = Field(default=20, ge=1, le=60)
    max_document_pages: int = Field(default=200, ge=1, le=1000)
    max_document_chunks: int = Field(default=2048, ge=1, le=10000)

    @field_validator("data_dir")
    @classmethod
    def resolve_data_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def empty_key(cls, value):
        return value or None

    @field_validator("allowed_hosts")
    @classmethod
    def exact_hosts(cls, values: list[str]) -> list[str]:
        result = []
        for value in values:
            host = value.strip().lower().rstrip(".").encode("idna").decode("ascii")
            if not host or any(c in host for c in "/:@*\\%") or any(c.isspace() for c in host):
                raise ValueError("Scrape allowlist requires exact DNS hostnames")
            result.append(host)
        return sorted(set(result))

    @field_validator("trusted_hosts")
    @classmethod
    def restrictive_hosts(cls, values: list[str]) -> list[str]:
        if not values or any("*" in host or "/" in host for host in values):
            raise ValueError("Explicit trusted hosts are required; wildcards are forbidden")
        return values

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
        return values

    @model_validator(mode="after")
    def limits(self):
        if self.max_request_bytes <= self.max_upload_bytes:
            raise ValueError("Request limit must exceed upload limit for multipart overhead")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
