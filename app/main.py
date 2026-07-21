from app import __version__
from app.config import settings
from app.database import init_db
from app.init_data import create_admin_user
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from app.caldav.xml_responses import build_well_known_caldav
from fastapi.staticfiles import StaticFiles
from app.caldav.router import router as caldav_router
from app.ics_feed.router import router as ics_router
from app.admin.router import router as admin_router
from app.auth.session_deps import LoginRequiredException
from contextlib import asynccontextmanager
from pathlib import Path


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await create_admin_user()
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    lifespan=lifespan,
)

# Static asset mount. In prod the Vite build populates app/static/dist/.
# In dev (VITE_DEV=true) the directory may not exist yet — the dev server
# at :5173 serves assets directly and templates use the vite_asset filter
# to point at it. We mount a tmpdir fallback so import-time never crashes.
_static_dist = Path("app/static/dist")
if _static_dist.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dist)), name="static")
else:
    import tempfile

    _fallback = Path(tempfile.mkdtemp(prefix="kalendav-static-"))
    app.mount("/static", StaticFiles(directory=str(_fallback)), name="static")


@app.exception_handler(LoginRequiredException)
async def login_required_handler(request: Request, exc: LoginRequiredException):
    return RedirectResponse(url="/admin/login", status_code=302)


app.include_router(caldav_router, prefix="/dav", tags=["CalDAV"])
app.include_router(ics_router, prefix="/ics", tags=["ICS Feeds"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__}


@app.api_route("/.well-known/caldav", methods=["GET", "HEAD", "PROPFIND", "OPTIONS"])
async def well_known_caldav(request: Request):
    """RFC 6764 §3.3 CalDAV discovery endpoint."""
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "DAV": "1, 2, 3, calendar-access, calendar-schedule",
                "Allow": "OPTIONS, PROPFIND, GET, HEAD",
                "Content-Length": "0",
            },
        )
    base = settings.base_uri.rstrip("/")
    if not base or base.endswith("localhost:8000"):
        fwd_proto = request.headers.get("x-forwarded-proto", "http")
        fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        if fwd_host:
            base = f"{fwd_proto}://{fwd_host}"
    return Response(
        content=build_well_known_caldav(base),
        media_type="application/xml; charset=utf-8",
        status_code=207,
        headers={"DAV": "1, 2, 3, calendar-access, calendar-schedule"},
    )


@app.api_route("/.well-known/carddav", methods=["GET", "HEAD", "PROPFIND", "OPTIONS"])
async def well_known_carddav(request: Request):
    return Response(status_code=404, content="CardDAV not supported")
