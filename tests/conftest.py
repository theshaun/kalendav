"""Async test infrastructure for KalenDAV.

Provides an isolated in-memory SQLite database per test via a StaticPool
engine (single shared connection so the in-memory DB persists across sessions
within one test), a FastAPI `get_db` dependency override, an httpx ASGITransport
client (app lifespan is NOT run), and seeded helper functions.
"""
import base64
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.basic import generate_api_key, hash_api_key, hash_password
from app.caldav.ics_parser import generate_ics
from app.database import Base, get_db
from app.main import app
from app.models import APIKey, Calendar, CalendarShare, Event, User
from app.models.share import SharePermission


@pytest_asyncio.fixture
async def db_engine():
    """Function-scoped in-memory SQLite engine. Schema created/dropped per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _session_factory(db_engine):
    return async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest_asyncio.fixture
async def db_session(db_engine):
    """An AsyncSession on the test engine, for direct DB seeding/assertions."""
    Session = _session_factory(db_engine)
    async with Session() as session:
        yield session
        await session.close()


@pytest_asyncio.fixture
async def db_override(db_engine):
    """Register a get_db override pointing at the test engine.

    KEYSTONE: without this, every endpoint hits the real configured DB
    (Postgres in .env, unreachable in tests). Tests obtain `client` only
    through this fixture, so the override is always active for HTTP tests.
    """
    Session = _session_factory(db_engine)

    async def override_get_db():
        async with Session() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def client(db_override):
    """httpx client over ASGI. Lifespan is NOT run (no init_db/create_admin_user
    against the real engine). Transitive dep on db_override guarantees a ready DB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Seeded helpers (plain async functions; caller passes a `db` session) ---

async def make_user(db, username="testuser", password="testpass", is_admin=False, email=None):
    user = User(
        username=username,
        email=email or f"{username}@example.com",
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def make_calendar(db, user_id, name="Calendar", description=None,
                        color="#3B82F6", is_default=False):
    cal = Calendar(
        user_id=user_id,
        name=name,
        description=description,
        color=color,
        is_default=is_default,
    )
    db.add(cal)
    await db.commit()
    await db.refresh(cal)
    return cal


async def make_event(db, calendar_id, **kw):
    """Seed an Event. Populates the non-nullable raw_ics via generate_ics
    when not explicitly provided."""
    uid = kw.get("uid") or str(uuid.uuid4())
    summary = kw.get("summary")
    dtstart = kw.get("dtstart", datetime.utcnow())
    dtend = kw.get("dtend")
    description = kw.get("description")
    location = kw.get("location")
    rrule = kw.get("rrule")
    is_all_day = kw.get("is_all_day", False)
    color = kw.get("color")
    timezone = kw.get("timezone")
    raw_ics = kw.get("raw_ics")
    if raw_ics is None:
        raw_ics = generate_ics(
            uid=uid,
            summary=summary or "",
            dtstart=dtstart,
            dtend=dtend,
            description=description,
            location=location,
            rrule=rrule,
            is_all_day=is_all_day,
            color=color,
            timezone=timezone,
        )
    event = Event(
        calendar_id=calendar_id,
        uid=uid,
        summary=summary,
        description=description,
        dtstart=dtstart,
        dtend=dtend,
        location=location,
        color=color,
        rrule=rrule,
        timezone=timezone,
        is_all_day=is_all_day,
        raw_ics=raw_ics,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def make_api_key(db, user_id, name="key"):
    """Return (APIKey, plain_key). Stores hash_api_key(plain)."""
    plain = generate_api_key()
    api_key = APIKey(
        user_id=user_id,
        key_hash=hash_api_key(plain),
        name=name,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key, plain


async def make_share(db, calendar_id, user_id, permission):
    share = CalendarShare(
        calendar_id=calendar_id,
        user_id=user_id,
        permission=permission,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


def basic_auth_header(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}
