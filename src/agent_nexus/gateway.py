import asyncio
import json
import math
import os
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .schemas import ChatRequest, ChatResponse, EmbeddingRequest, EmbeddingResponse, Usage
from .store import ModelStore


class GatewayError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class Gateway:
    def __init__(self, store: ModelStore, client: httpx.AsyncClient, allowed_hosts: set[str]):
        self.store, self.client, self.allowed_hosts = store, client, allowed_hosts

    def check_host(self, config):
        if urlsplit(config.base_url).hostname.lower() not in self.allowed_hosts:
            raise GatewayError(
                403, "endpoint_not_allowed", "Endpoint is not in the deployment allowlist"
            )

    def resolve(self, alias, capability):
        config = self.store.get(alias)
        if not config or not config.enabled:
            raise GatewayError(404, "model_not_found", "Model is missing or disabled")
        if capability not in config.capabilities:
            raise GatewayError(
                422, "unsupported_capability", "Model does not support this operation"
            )
        self.check_host(config)
        return config

    async def post(self, config, path, body):
        headers = {}
        if config.api_key_env:
            secret = os.environ.get(config.api_key_env)
            if not secret:
                raise GatewayError(
                    503, "credential_missing", "Provider credential is not configured"
                )
            headers["Authorization"] = f"Bearer {secret}"
        try:
            async with asyncio.timeout(config.timeout_seconds):
                async with self.client.stream(
                    "POST",
                    config.base_url + path,
                    json=body,
                    headers=headers,
                    timeout=config.timeout_seconds,
                ) as response:
                    if response.status_code == 429:
                        raise GatewayError(
                            429, "provider_rate_limited", "Provider rate limit reached"
                        )
                    if response.status_code >= 300:
                        raise GatewayError(502, "provider_error", "Provider rejected the request")
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(payload) + len(chunk) > 8 * 1024 * 1024:
                            raise GatewayError(
                                502,
                                "provider_response_too_large",
                                "Provider response exceeds 8 MiB",
                            )
                        payload.extend(chunk)
        except (httpx.TimeoutException, TimeoutError):
            raise GatewayError(504, "provider_timeout", "Provider timed out") from None
        except httpx.RequestError:
            raise GatewayError(502, "provider_unreachable", "Cannot reach provider") from None
        try:
            result = json.loads(payload)
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError()
            return result
        except ValueError:
            raise GatewayError(
                502, "invalid_provider_response", "Provider returned an invalid response"
            ) from None

    async def chat(self, request: ChatRequest, request_id: str):
        config = self.resolve(request.model, "chat")
        if request.temperature is not None and not config.supports_temperature:
            raise GatewayError(422, "unsupported_parameter", "Model does not support temperature")
        limit = request.max_tokens or config.max_output_tokens
        if limit > config.max_output_tokens:
            raise GatewayError(
                422, "output_limit_exceeded", "Requested output exceeds model configuration"
            )
        body = {
            "model": config.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": False,
        }
        if config.provider == "ollama":
            body["options"] = {"num_predict": limit}
            if request.temperature is not None:
                body["options"]["temperature"] = request.temperature
            path = "/api/chat"
        else:
            body[config.token_parameter] = limit
            if request.temperature is not None:
                body["temperature"] = request.temperature
            path = "/chat/completions"
        data = await self.post(config, path, body)
        try:
            if config.provider == "ollama":
                if data.get("done") is not True or data["message"].get("tool_calls"):
                    raise ValueError()
                content = data["message"]["content"]
                reason = data.get("done_reason")
                usage = Usage(
                    input_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count")
                )
            else:
                choice = data["choices"][0]
                if choice["message"].get("tool_calls"):
                    raise ValueError()
                content, reason = choice["message"]["content"], choice.get("finish_reason")
                counts = data.get("usage") or {}
                usage = Usage(
                    input_tokens=counts.get("prompt_tokens"),
                    output_tokens=counts.get("completion_tokens"),
                )
            return ChatResponse(
                request_id=request_id,
                model=request.model,
                content=content,
                finish_reason=reason,
                usage=usage,
            )
        except (AttributeError, KeyError, IndexError, TypeError, ValueError, ValidationError):
            raise GatewayError(
                502, "invalid_provider_response", "Provider returned an invalid chat response"
            ) from None

    async def embed(self, request: EmbeddingRequest, request_id: str):
        config = self.resolve(request.model, "embeddings")
        body = {"model": config.model, "input": request.input}
        if config.provider == "ollama":
            body["truncate"] = False
        data = await self.post(
            config, "/api/embed" if config.provider == "ollama" else "/embeddings", body
        )
        try:
            if config.provider == "ollama":
                vectors = data["embeddings"]
                tokens = data.get("prompt_eval_count")
            else:
                rows = sorted(data["data"], key=lambda item: item["index"])
                if [row["index"] for row in rows] != list(range(len(request.input))):
                    raise ValueError()
                vectors = [row["embedding"] for row in rows]
                tokens = (data.get("usage") or {}).get("prompt_tokens")
            if len(vectors) != len(request.input) or not vectors or not vectors[0]:
                raise ValueError()
            dimensions = len(vectors[0])
            if any(
                len(v) != dimensions
                or any(
                    isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n)
                    for n in v
                )
                for v in vectors
            ):
                raise ValueError()
            return EmbeddingResponse(
                request_id=request_id,
                model=request.model,
                vectors=vectors,
                dimensions=dimensions,
                usage=Usage(input_tokens=tokens),
            )
        except (AttributeError, KeyError, TypeError, ValueError, ValidationError):
            raise GatewayError(
                502, "invalid_provider_response", "Provider returned invalid embeddings"
            ) from None
