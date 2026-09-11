from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from .schemas import ChatRequest, ChatResponse, EmbeddingRequest, EmbeddingResponse


def client_model_router(client_auth, allowed_models, authorize_model):
    router = APIRouter(tags=["Model invocation"])

    @router.get("/api/v1/models", dependencies=[Depends(client_auth)])
    def models(request: Request):
        allowed = allowed_models(request)
        return {
            "data": [
                {"id": m.alias, "deployment": m.deployment, "capabilities": m.capabilities}
                for m in request.app.state.gateway.store.list()
                if m.enabled and (allowed is None or m.alias in allowed)
            ]
        }

    @router.post(
        "/api/v1/chat/completions", dependencies=[Depends(client_auth)], response_model=ChatResponse
    )
    async def chat(body: ChatRequest, request: Request):
        await run_in_threadpool(authorize_model, request, body.model)
        return await request.app.state.gateway.chat(
            body, request.state.request_id, tenant_id=request.state.tenant_id
        )

    @router.post(
        "/api/v1/embeddings", dependencies=[Depends(client_auth)], response_model=EmbeddingResponse
    )
    async def embed(body: EmbeddingRequest, request: Request):
        await run_in_threadpool(authorize_model, request, body.model)
        return await request.app.state.gateway.embed(
            body, request.state.request_id, tenant_id=request.state.tenant_id
        )

    return router
