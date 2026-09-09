from importlib.resources import files
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_admin(app):
    static_dir = files("agent_nexus_web").joinpath("static")
    app.mount("/admin/assets", StaticFiles(directory=static_dir), name="admin-assets")

    @app.get("/admin", include_in_schema=False)
    def admin_page():
        # Public shell; all business data requires authenticated API access.
        return FileResponse(static_dir / "index.html")
