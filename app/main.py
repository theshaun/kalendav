from app.config import settings
from app.database import init_db
from app.init_data import create_admin_user
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from app.caldav.router import router as caldav_router
from app.ics_feed.router import router as ics_router
from app.admin.router import router as admin_router
from app.auth.session_deps import LoginRequiredException
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await create_admin_user()
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)


@app.exception_handler(LoginRequiredException)
async def login_required_handler(request: Request, exc: LoginRequiredException):
    return RedirectResponse(url="/admin/login", status_code=302)


app.include_router(caldav_router, prefix="/dav", tags=["CalDAV"])
app.include_router(ics_router, prefix="/ics", tags=["ICS Feeds"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.api_route("/.well-known/caldav", methods=["GET", "HEAD", "PROPFIND", "OPTIONS"])
async def well_known_caldav(request: Request):
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "DAV": "1, 2, 3, calendar-access, calendar-schedule",
                "Allow": "OPTIONS, PROPFIND, GET, HEAD",
                "Content-Length": "0",
            },
        )
    return RedirectResponse(url="/dav/", status_code=301)


@app.api_route("/.well-known/carddav", methods=["GET", "HEAD", "PROPFIND", "OPTIONS"])
async def well_known_carddav(request: Request):
    return Response(status_code=404, content="CardDAV not supported")
