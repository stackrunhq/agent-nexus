from importlib.resources import files
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import HTTPException


def mount_admin(app):
    static_dir = files("agent_nexus_web").joinpath("static")
    app.mount("/admin/assets", StaticFiles(directory=static_dir), name="admin-assets")

    @app.get("/admin", include_in_schema=False)
    def admin_page():
        # Public shell; all business data requires authenticated API access.
        return FileResponse(static_dir / "index.html")

    @app.get("/admin/tenants", include_in_schema=False)
    def tenant_page():
        page = static_dir / "tenants" / "index.html"
        if not page.is_file():
            raise HTTPException(503, "Build the frontend with npm --prefix web run build")
        return FileResponse(page)
