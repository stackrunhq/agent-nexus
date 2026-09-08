from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelConfig(StrictModel):
    alias: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
    provider: Literal["openai_compatible", "ollama"]
    model: str = Field(min_length=1, max_length=200)
    base_url: str = Field(max_length=2048)
    deployment: Literal["cloud", "local"]
    api_key_env: str | None = Field(default=None, pattern=r"^NEXUS_PROVIDER_[A-Z0-9_]+$")
    enabled: bool = True
    capabilities: list[Literal["chat", "embeddings"]] = Field(min_length=1)
    timeout_seconds: float = Field(default=60, ge=1, le=300)
    max_output_tokens: int = Field(default=2048, ge=1, le=32768)
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    supports_temperature: bool = True

    @model_validator(mode="after")
    def validate_url(self):
        try:
            url = urlsplit(self.base_url)
            port = url.port
        except ValueError as exc:
            raise ValueError("Invalid base URL") from exc
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("Use an HTTP(S) base URL without credentials, query or fragment")
        if self.deployment == "cloud" and url.scheme != "https":
            raise ValueError("Cloud endpoints require HTTPS")
        if port == 0:
            raise ValueError("Invalid port")
        if self.provider == "ollama" and self.token_parameter != "max_tokens":
            raise ValueError("Ollama uses num_predict; keep token_parameter at its default")
        self.base_url = self.base_url.rstrip("/")
        return self


class ModelView(ModelConfig):
    etag: str


class Message(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32000)


class ChatRequest(StrictModel):
    model: str = Field(min_length=1, max_length=64)
    messages: list[Message] = Field(min_length=1, max_length=100)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
    temperature: float | None = Field(default=None, ge=0, le=2)

    @model_validator(mode="after")
    def limit_total(self):
        if sum(len(message.content) for message in self.messages) > 128000:
            raise ValueError("Message content exceeds request limit")
        return self


class EmbeddingRequest(StrictModel):
    model: str = Field(min_length=1, max_length=64)
    input: list[str] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def limit_input(self):
        if any(not item.strip() or len(item) > 32000 for item in self.input):
            raise ValueError("Each input must contain 1..32000 characters")
        if sum(map(len, self.input)) > 128000:
            raise ValueError("Embedding input exceeds request limit")
        return self


class Usage(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ChatResponse(StrictModel):
    request_id: str
    model: str
    content: str
    finish_reason: str | None = None
    usage: Usage


class EmbeddingResponse(StrictModel):
    request_id: str
    model: str
    vectors: list[list[float]]
    dimensions: int
    usage: Usage


class ModelTestRequest(StrictModel):
    capability: Literal["chat", "embeddings"] = "chat"
    input: str = Field(default="Reply with OK.", min_length=1, max_length=4000)

    @model_validator(mode="after")
    def nonblank(self):
        if not self.input.strip():
            raise ValueError("Test input cannot be blank")
        return self


class ModelTestResponse(StrictModel):
    request_id: str
    model: str
    capability: Literal["chat", "embeddings"]
    elapsed_ms: float
    result: ChatResponse | EmbeddingResponse
