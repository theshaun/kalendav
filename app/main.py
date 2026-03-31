from app.config import settings
from app.database import init_db
from fastapi import FastAPI
from app.caldav.router import router as caldav_router
from app.ics_feed.router import router as ics_router
from app.admin.router import router as admin_router
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.include_router(caldav_router, prefix="/dav", tags=["CalDAV"])
app.include_router(ics_router, prefix="/ics", tags=["ICS Feeds"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])


@app.get("/health")
async def health():
    return {"status": "ok"}
