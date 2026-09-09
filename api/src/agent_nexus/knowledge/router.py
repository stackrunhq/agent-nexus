"""Raw-byte upload and scoped metadata/chunk APIs; parsing runs only in workers."""

from pathlib import PurePath

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from agent_nexus.core.errors import GatewayError
from .parsing import MAX_FILE_BYTES


class Publication(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    published: bool


def knowledge_router(get_store, admin_auth, client_auth):
    router = APIRouter(tags=["Knowledge documents"])
    root = "/api/v1/admin/tenants/{tenant_id}/applications/{app_id}/versions/{version_id}/documents"

    @router.post(
        root, status_code=202, dependencies=[Depends(admin_auth)],
        openapi_extra={"requestBody": {"required": True, "content": {
            "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
        }}},
    )
    async def upload(
        tenant_id: str,
        app_id: str,
        version_id: str,
        request: Request,
        filename: str = Query(min_length=1, max_length=240),
    ):
        if any(ord(c) < 32 or c in "/\\:" for c in filename):
            raise GatewayError(422, "invalid_filename", "Use a plain filename")
        if PurePath(filename).suffix.lower() not in {".pdf", ".docx", ".txt", ".md"}:
            raise GatewayError(415, "unsupported_format", "Use PDF, DOCX, Markdown or TXT")
        if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
            raise GatewayError(
                415, "unsupported_media_type", "Send raw bytes as application/octet-stream"
            )
        # Check ownership before receiving file data; upload() rechecks inside its transaction.
        await run_in_threadpool(get_store().list, tenant_id, app_id, version_id, limit=1)
        content = bytearray()
        async for block in request.stream():
            if len(content) + len(block) > MAX_FILE_BYTES:
                raise GatewayError(413, "file_too_large", "Maximum file size is 10 MiB")
            content.extend(block)
        if not content:
            raise GatewayError(422, "empty_file", "File must not be empty")
        return await run_in_threadpool(
            get_store().upload,
            tenant_id,
            app_id,
            version_id,
            filename,
            bytes(content),
            request.state.actor,
            request.state.request_id,
        )

    @router.get(root, dependencies=[Depends(admin_auth)])
    def list_documents(
        tenant_id: str,
        app_id: str,
        version_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ):
        return {"data": get_store().list(tenant_id, app_id, version_id, offset=offset, limit=limit)}

    @router.get(root + "/{document_id}", dependencies=[Depends(admin_auth)])
    def get_document(tenant_id: str, app_id: str, version_id: str, document_id: str):
        return get_store().get(tenant_id, app_id, version_id, document_id)

    @router.get(root + "/{document_id}/chunks", dependencies=[Depends(admin_auth)])
    def get_chunks(
        tenant_id: str,
        app_id: str,
        version_id: str,
        document_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ):
        return {
            "data": get_store().get(
                tenant_id,
                app_id,
                version_id,
                document_id,
                with_chunks=True,
                offset=offset,
                limit=limit,
            )
        }

    @router.patch(root + "/{document_id}", dependencies=[Depends(admin_auth)])
    def publication(
        tenant_id: str,
        app_id: str,
        version_id: str,
        document_id: str,
        body: Publication,
        request: Request,
    ):
        return get_store().publish(
            tenant_id,
            app_id,
            version_id,
            document_id,
            body.published,
            request.state.actor,
            request.state.request_id,
        )

    @router.post(root + "/{document_id}/retry", dependencies=[Depends(admin_auth)], status_code=202)
    def retry(tenant_id: str, app_id: str, version_id: str, document_id: str, request: Request):
        return get_store().retry(
            tenant_id,
            app_id,
            version_id,
            document_id,
            request.state.actor,
            request.state.request_id,
        )

    public = "/api/v1/applications/{app_id}/versions/{version_id}/documents"

    def tenant(request):
        if request.state.tenant_id is None:
            raise GatewayError(403, "tenant_required", "A tenant-scoped identity is required")
        return request.state.tenant_id

    @router.get(public, dependencies=[Depends(client_auth)])
    def public_list(
        app_id: str,
        version_id: str,
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ):
        rows = get_store().list(
            tenant(request), app_id, version_id, public=True, offset=offset, limit=limit
        )
        return {
            "data": [
                {k: row[k] for k in ("id", "filename", "version_id", "sha256")} for row in rows
            ]
        }

    @router.get(public + "/{document_id}/chunks", dependencies=[Depends(client_auth)])
    def public_chunks(
        app_id: str,
        version_id: str,
        document_id: str,
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ):
        return {
            "data": get_store().get(
                tenant(request),
                app_id,
                version_id,
                document_id,
                public=True,
                with_chunks=True,
                offset=offset,
                limit=limit,
            )
        }

    return router
