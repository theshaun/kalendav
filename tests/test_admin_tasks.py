"""Tests for the /admin/tasks* routes (T6 of the caldav-task-support plan).

Auth pattern: the admin HTML routes use a session cookie (not HTTP Basic),
so each test POSTs /admin/login with seeded credentials; the httpx AsyncClient
from conftest persists the returned Set-Cookie automatically for subsequent
requests on the same client instance.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import Task
from app.models.share import SharePermission
from tests.conftest import make_calendar, make_share, make_task, make_user


# Rendering tasks.html extends base.html which calls the `vite_asset` filter.
# In prod that filter reads dist/manifest.json (built by `npm run build`).
# Setting VITE_DEV=true makes the filter return the live dev-server URL
# instead, so HTML rendering works without a built manifest.
@pytest.fixture(autouse=True)
def _vite_dev(monkeypatch):
    monkeypatch.setenv("VITE_DEV", "true")


async def _login(client, username: str, password: str):
    resp = await client.post(
        "/admin/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code == 302, f"login failed: {resp.status_code} {resp.text}"


@pytest.mark.asyncio
async def test_get_tasks_page(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Work")
    await make_task(db_session, cal.id, summary="Buy milk")

    await _login(client, "alice", "pw")
    resp = await client.get("/admin/tasks")

    assert resp.status_code == 200
    assert "task-list" in resp.text
    assert "Buy milk" in resp.text


@pytest.mark.asyncio
async def test_create_task(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Work")

    await _login(client, "alice", "pw")
    resp = await client.post(
        "/admin/tasks",
        data={
            "calendar_id": cal.id,
            "summary": "Write tests",
            "due": "2026-12-31",
            "priority": "5",
        },
    )

    assert resp.status_code == 200, resp.text
    assert "Write tests" in resp.text, "create response must show the new task"

    result = await db_session.execute(
        select(Task).where(Task.calendar_id == cal.id)
    )
    tasks = result.scalars().all()
    assert len(tasks) == 1
    assert tasks[0].summary == "Write tests"
    assert tasks[0].priority == 5
    assert tasks[0].due == datetime(2026, 12, 31, 0, 0, 0)


@pytest.mark.asyncio
async def test_create_task_rejects_empty_summary(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Work")

    await _login(client, "alice", "pw")
    resp = await client.post(
        "/admin/tasks",
        data={"calendar_id": cal.id, "summary": ""},
    )

    # FastAPI Form(..., ...) returns 422 for missing required fields —
    # never a 500. (Browser `required` attr prevents this path client-side.)
    assert resp.status_code == 422
    result = await db_session.execute(select(Task))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_toggle_task(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Work")
    task = await make_task(db_session, cal.id, summary="Toggle me", status="NEEDS-ACTION")
    assert task.status == "NEEDS-ACTION"

    await _login(client, "alice", "pw")
    resp = await client.post(f"/admin/tasks/{task.id}/toggle")

    assert resp.status_code == 200, resp.text
    assert "Toggle me" in resp.text

    await db_session.refresh(task)
    assert task.status == "COMPLETED"
    assert task.completed is not None
    assert task.percent_complete == 100


@pytest.mark.asyncio
async def test_delete_task(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Work")
    task = await make_task(db_session, cal.id, summary="Delete me")

    await _login(client, "alice", "pw")
    resp = await client.delete(f"/admin/tasks/{task.id}")

    assert resp.status_code == 200, resp.text

    result = await db_session.execute(select(Task).where(Task.id == task.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_reorder(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Work")
    t1 = await make_task(db_session, cal.id, summary="First", sort_order=0)
    t2 = await make_task(db_session, cal.id, summary="Second", sort_order=1)

    await _login(client, "alice", "pw")
    resp = await client.post(
        "/admin/tasks/reorder",
        json={"ids": [t2.id, t1.id]},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    await db_session.refresh(t1)
    await db_session.refresh(t2)
    assert t2.sort_order == 0
    assert t1.sort_order == 1


@pytest.mark.asyncio
async def test_reorder_rejects_non_list_ids(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Work")
    await make_task(db_session, cal.id, summary="First", sort_order=0)

    await _login(client, "alice", "pw")
    # Adversarial: ids is a string, not a list. Must 400, not 500.
    resp = await client.post(
        "/admin/tasks/reorder",
        json={"ids": "notalist"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_permission_readonly(client, db_session):
    owner = await make_user(db_session, username="owner", password="pw")
    reader = await make_user(db_session, username="reader", password="pw")
    cal = await make_calendar(db_session, owner.id, name="Shared")
    await make_share(db_session, cal.id, reader.id, SharePermission.READ)
    task = await make_task(db_session, cal.id, summary="Read-only task")

    await _login(client, "reader", "pw")

    # Reader can SEE the task on /admin/tasks (READ share).
    page = await client.get("/admin/tasks")
    assert page.status_code == 200
    assert "Read-only task" in page.text

    # But cannot toggle (403).
    toggle_resp = await client.post(f"/admin/tasks/{task.id}/toggle")
    assert toggle_resp.status_code == 403

    # And cannot delete (403).
    delete_resp = await client.delete(f"/admin/tasks/{task.id}")
    assert delete_resp.status_code == 403

    # Task is unchanged in DB.
    await db_session.refresh(task)
    assert task.status == "NEEDS-ACTION"


@pytest.mark.asyncio
async def test_create_task_in_unwritable_calendar_is_403(client, db_session):
    owner = await make_user(db_session, username="owner", password="pw")
    reader = await make_user(db_session, username="reader", password="pw")
    cal = await make_calendar(db_session, owner.id, name="Shared")
    await make_share(db_session, cal.id, reader.id, SharePermission.READ)

    await _login(client, "reader", "pw")
    resp = await client.post(
        "/admin/tasks",
        data={"calendar_id": cal.id, "summary": "Should fail"},
    )
    assert resp.status_code == 403

    result = await db_session.execute(select(Task))
    assert result.scalars().all() == []
