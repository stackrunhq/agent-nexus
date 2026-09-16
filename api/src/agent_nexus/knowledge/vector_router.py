from fastapi import APIRouter, Depends, Request, Query
from starlette.concurrency import run_in_threadpool
from agent_nexus.core.errors import GatewayError
from .vectors import IndexRequest, VectorSearchRequest, VectorService
from .answers import AnswerRequest, AnswerService
from .index_jobs import IndexJobs, validate_submission
from contextlib import suppress
from typing import Literal


def vector_router(get_store, admin_auth, client_auth):
    router = APIRouter(tags=["Knowledge vectors"])
    admin = "/api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}"

    def service(request):
        return VectorService(get_store().database, request.app.state.gateway)

    @router.get("/api/v1/admin/tenants/{tenant_id}/index-usage", dependencies=[Depends(admin_auth)])
    def index_usage(tenant_id: str):
        return IndexJobs(get_store().database).usage(tenant_id)

    @router.post(admin + "/index-jobs", dependencies=[Depends(admin_auth)], status_code=202)
    async def enqueue_index(
        tenant_id: str, app_id: str, version_id: str, body: IndexRequest, request: Request
    ):
        await run_in_threadpool(
            validate_submission, service(request), tenant_id, app_id, version_id, body.model
        )
        return await run_in_threadpool(
            IndexJobs(get_store().database).enqueue,
            tenant_id,
            app_id,
            version_id,
            body.model,
            request.state.actor,
            request.state.request_id,
        )

    @router.get(admin + "/index-jobs", dependencies=[Depends(admin_auth)])
    def list_index_jobs(
        tenant_id: str,
        app_id: str,
        version_id: str,
        offset: int = Query(0, ge=0, le=1000000),
        limit: int = Query(20, ge=1, le=100),
        model: str | None = Query(None, min_length=1, max_length=200),
        status: Literal["queued", "processing", "succeeded", "failed"] | None = None,
        error: str | None = Query(None, max_length=200),
        cursor: str | None = Query(None, min_length=1, max_length=1024),
    ):
        return IndexJobs(get_store().database).list(
            tenant_id,
            app_id,
            version_id,
            offset=offset,
            limit=limit,
            model=model,
            status=status,
            error=error,
            cursor=cursor,
        )

    @router.post(admin + "/hybrid-search", dependencies=[Depends(admin_auth)])
    async def hybrid_preview(
        tenant_id: str, app_id: str, version_id: str, body: VectorSearchRequest, request: Request
    ):
        return await AnswerService(get_store().database, request.app.state.gateway).hybrid(
            tenant_id, app_id, version_id, body, request.state.request_id
        )

    @router.get(admin + "/index-jobs/{job_id}", dependencies=[Depends(admin_auth)])
    def index_job_detail(
        tenant_id: str,
        app_id: str,
        version_id: str,
        job_id: str,
        offset: int = Query(0, ge=0, le=100000),
        limit: int = Query(20, ge=1, le=100),
        attempt: Literal["1", "2", "3", "unknown"] | None = None,
        call_status: Literal["pending", "succeeded", "failed"] | None = None,
        call_error: str | None = Query(None, max_length=200),
    ):
        from .index_details import detail

        return detail(
            get_store().database,
            tenant_id,
            app_id,
            version_id,
            job_id,
            offset,
            limit,
            attempt,
            call_status,
            call_error,
        )

    @router.get(admin + "/index-jobs/{job_id}/export", dependencies=[Depends(admin_auth)])
    def export_index_calls(
        tenant_id: str,
        app_id: str,
        version_id: str,
        job_id: str,
        attempt: Literal["1", "2", "3", "unknown"] | None = None,
        call_status: Literal["pending", "succeeded", "failed"] | None = None,
        call_error: str | None = Query(None, max_length=200),
    ):
        from .index_export import export

        return export(
            get_store().database,
            tenant_id,
            app_id,
            version_id,
            job_id,
            attempt,
            call_status,
            call_error,
        )

    @router.post(admin + "/answers", dependencies=[Depends(admin_auth)])
    async def answer_preview(
        tenant_id: str, app_id: str, version_id: str, body: AnswerRequest, request: Request
    ):
        return await AnswerService(get_store().database, request.app.state.gateway).answer(
            tenant_id, app_id, version_id, body, request.state.request_id
        )

    @router.post(
        "/api/v1/applications/{app_id}/versions/{version_id}/hybrid-search",
        dependencies=[Depends(client_auth)],
    )
    async def hybrid_public(
        app_id: str, version_id: str, body: VectorSearchRequest, request: Request
    ):
        if request.state.tenant_id is None:
            raise GatewayError(403, "tenant_required", "A tenant-scoped identity is required")
        return await hybrid_preview(request.state.tenant_id, app_id, version_id, body, request)

    @router.post(
        "/api/v1/applications/{app_id}/versions/{version_id}/answers",
        dependencies=[Depends(client_auth)],
    )
    async def answer_public(app_id: str, version_id: str, body: AnswerRequest, request: Request):
        if request.state.tenant_id is None:
            raise GatewayError(403, "tenant_required", "A tenant-scoped identity is required")
        return await answer_preview(request.state.tenant_id, app_id, version_id, body, request)

    @router.get(admin + "/vector-index", dependencies=[Depends(admin_auth)])
    async def status(
        tenant_id: str,
        app_id: str,
        version_id: str,
        request: Request,
        model: str = Query(min_length=1, max_length=64),
    ):
        return await run_in_threadpool(
            service(request).describe, tenant_id, app_id, version_id, model
        )

    @router.post(admin + "/vector-index", dependencies=[Depends(admin_auth)])
    async def build(
        tenant_id: str, app_id: str, version_id: str, body: IndexRequest, request: Request
    ):
        builder = service(request)
        await run_in_threadpool(
            validate_submission, builder, tenant_id, app_id, version_id, body.model
        )
        store = IndexJobs(get_store().database)
        task = await run_in_threadpool(
            store.enqueue,
            tenant_id,
            app_id,
            version_id,
            body.model,
            request.state.actor,
            request.state.request_id,
            immediate=True,
        )
        try:
            return await builder.build(
                tenant_id,
                app_id,
                version_id,
                body.model,
                request.state.actor,
                request.state.request_id,
                on_save=lambda db: store.finish(db, task),
                index_job_id=task["id"],
                index_attempt=task["attempts"],
            )
        except Exception as exc:
            with suppress(GatewayError):
                await run_in_threadpool(
                    store.fail,
                    task,
                    exc.code if isinstance(exc, GatewayError) else "index_build_failed",
                )
            raise

    @router.post(admin + "/vector-search", dependencies=[Depends(admin_auth)])
    async def preview(
        tenant_id: str, app_id: str, version_id: str, body: VectorSearchRequest, request: Request
    ):
        return await service(request).search(
            tenant_id, app_id, version_id, body, request.state.request_id
        )

    @router.post(
        "/api/v1/applications/{app_id}/versions/{version_id}/vector-search",
        dependencies=[Depends(client_auth)],
    )
    async def search(app_id: str, version_id: str, body: VectorSearchRequest, request: Request):
        if request.state.tenant_id is None:
            raise GatewayError(403, "tenant_required", "A tenant-scoped identity is required")
        return await service(request).search(
            request.state.tenant_id, app_id, version_id, body, request.state.request_id
        )

    return router
