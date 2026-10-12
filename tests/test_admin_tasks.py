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


@pytest.mark.asyncio
async def test_task_page_filters_by_calendar_param(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal_a = await make_calendar(db_session, user.id, name="A")
    cal_b = await make_calendar(db_session, user.id, name="B")
    await make_task(db_session, cal_a.id, summary="TaskA")
    await make_task(db_session, cal_b.id, summary="TaskB")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.get("/admin/tasks", params={"calendar": cal_a.id})
    assert resp.status_code == 200
    assert "TaskA" in resp.text
    assert "TaskB" not in resp.text

    unfiltered = await client.get("/admin/tasks")
    assert "TaskA" in unfiltered.text and "TaskB" in unfiltered.text


@pytest.mark.asyncio
async def test_task_page_groups_by_calendar(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal_a = await make_calendar(db_session, user.id, name="Work Cal", color="#ff0000")
    cal_b = await make_calendar(db_session, user.id, name="Home Cal", color="#00ff00")
    await make_task(db_session, cal_a.id, summary="TaskA")
    await make_task(db_session, cal_b.id, summary="TaskB")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.get("/admin/tasks")
    assert resp.status_code == 200
    assert "Work Cal" in resp.text and "Home Cal" in resp.text
    assert f'data-calendar-id="{cal_a.id}"' in resp.text
    assert f'data-calendar-id="{cal_b.id}"' in resp.text


@pytest.mark.asyncio
async def test_task_filter_accepts_read_shared_calendar(client, db_session):
    # Viewing a read-only shared calendar's tasks via the deep link must
    # filter to that calendar, not silently fall back to every task.
    alice = await make_user(db_session, username="alice", password="pw")
    bob = await make_user(db_session, username="bob", password="pw")
    cal_shared = await make_calendar(db_session, alice.id, name="SharedRO")
    cal_own = await make_calendar(db_session, bob.id, name="BobsOwn")
    await make_share(db_session, cal_shared.id, bob.id, SharePermission.READ)
    await make_task(db_session, cal_shared.id, summary="AlicesTask")
    await make_task(db_session, cal_own.id, summary="BobsTask")
    login = await client.post("/admin/login", data={"username": "bob", "password": "pw"})
    assert login.status_code == 302

    resp = await client.get("/admin/tasks", params={"calendar": cal_shared.id})
    assert resp.status_code == 200
    assert "AlicesTask" in resp.text
    assert "BobsTask" not in resp.text


@pytest.mark.asyncio
async def test_readonly_shared_tasks_render_non_interactive(client, db_session):
    alice = await make_user(db_session, username="alice", password="pw")
    bob = await make_user(db_session, username="bob", password="pw")
    cal_ro = await make_calendar(db_session, alice.id, name="RO")
    await make_share(db_session, cal_ro.id, bob.id, SharePermission.READ)
    task = await make_task(db_session, cal_ro.id, summary="ReadOnlyTask")
    login = await client.post("/admin/login", data={"username": "bob", "password": "pw"})
    assert login.status_code == 302

    resp = await client.get("/admin/tasks")
    assert resp.status_code == 200
    assert f'hx-post="/admin/tasks/{task.id}/toggle"' not in resp.text
    assert f'hx-delete="/admin/tasks/{task.id}"' not in resp.text
    assert "ReadOnlyTask" in resp.text


@pytest.mark.asyncio
async def test_my_calendars_shared_rows_have_deep_links(client, db_session):
    alice = await make_user(db_session, username="alice", password="pw")
    bob = await make_user(db_session, username="bob", password="pw")
    cal = await make_calendar(db_session, alice.id, name="SharedCal")
    await make_share(db_session, cal.id, bob.id, SharePermission.WRITE)
    login = await client.post("/admin/login", data={"username": "bob", "password": "pw"})
    assert login.status_code == 302

    resp = await client.get("/admin/my-calendars")
    assert resp.status_code == 200
    assert f'href="/admin/calendar?calendar={cal.id}"' in resp.text
    assert f'href="/admin/tasks?calendar={cal.id}"' in resp.text


@pytest.mark.asyncio
async def test_task_page_renders_subtask_hierarchy(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    parent = await make_task(db_session, cal.id, summary="ParentTask", uid="p-uid")
    await make_task(db_session, cal.id, summary="ChildTask", uid="c-uid", related_to="p-uid")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.get("/admin/tasks")
    assert resp.status_code == 200
    assert 'data-child="1"' in resp.text
    assert resp.text.index("ParentTask") < resp.text.index("ChildTask")


@pytest.mark.asyncio
async def test_create_task_with_parent_from_form(client, db_session):
    from sqlalchemy import select as sa_select
    from app.models import Task

    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_task(db_session, cal.id, summary="ParentTask", uid="p-uid")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.post("/admin/tasks", data={
        "calendar_id": cal.id,
        "summary": "WebChild",
        "related_to": "p-uid",
    })
    assert resp.status_code == 200

    row = (await db_session.execute(
        sa_select(Task).where(Task.summary == "WebChild")
    )).scalar_one()
    assert row.related_to == "p-uid"
    assert 'data-child="1"' in resp.text


@pytest.mark.asyncio
async def test_reorder_nests_task_under_parent(client, db_session):
    from sqlalchemy import select as sa_select
    from app.models import Task

    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    parent = await make_task(db_session, cal.id, summary="P", uid="p-1")
    child = await make_task(db_session, cal.id, summary="K", uid="k-1")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.post("/admin/tasks/reorder", json={
        "ids": [parent.id, child.id],
        "parents": {str(child.id): parent.id},
    })
    assert resp.status_code == 200
    await db_session.refresh(child)
    assert child.related_to == "p-1"

    page = await client.get("/admin/tasks")
    assert 'data-child="1"' in page.text


@pytest.mark.asyncio
async def test_reorder_parents_zero_clears_relation(client, db_session):
    from sqlalchemy import select as sa_select
    from app.models import Task

    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    parent = await make_task(db_session, cal.id, summary="P", uid="p-1")
    child = await make_task(db_session, cal.id, summary="K", uid="k-1", related_to="p-1")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.post("/admin/tasks/reorder", json={
        "ids": [child.id, parent.id],
        "parents": {str(child.id): 0},
    })
    assert resp.status_code == 200
    await db_session.refresh(child)
    assert child.related_to is None


@pytest.mark.asyncio
async def test_reorder_rejects_mutual_cycle(client, db_session):
    from sqlalchemy import select as sa_select
    from app.models import Task

    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    a = await make_task(db_session, cal.id, summary="A", uid="a-1")
    b = await make_task(db_session, cal.id, summary="B", uid="b-1")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.post("/admin/tasks/reorder", json={
        "ids": [a.id, b.id],
        "parents": {str(a.id): b.id, str(b.id): a.id},
    })
    assert resp.status_code == 200
    await db_session.refresh(a)
    await db_session.refresh(b)
    # A mutual pair cannot both survive: the first link wins, the cycle
    # breaker detaches the second — the result must be a renderable tree.
    assert not (a.related_to == "b-1" and b.related_to == "a-1")
    assert (a.related_to, b.related_to) in {(None, "a-1"), ("b-1", None)}


@pytest.mark.asyncio
async def test_reorder_parents_rejects_foreign_parent(client, db_session):
    from sqlalchemy import select as sa_select
    from app.models import Task

    alice = await make_user(db_session, username="alice", password="pw")
    mallory = await make_user(db_session, username="mallory", password="pw")
    cal_a = await make_calendar(db_session, alice.id, name="A")
    cal_m = await make_calendar(db_session, mallory.id, name="M")
    child = await make_task(db_session, cal_a.id, summary="K")
    foreign = await make_task(db_session, cal_m.id, summary="X")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.post("/admin/tasks/reorder", json={
        "ids": [child.id],
        "parents": {str(child.id): foreign.id},
    })
    assert resp.status_code == 200
    await db_session.refresh(child)
    assert child.related_to is None


@pytest.mark.asyncio
async def test_move_task_endpoint(client, db_session):
    from sqlalchemy import select as sa_select
    from app.models import Task

    user = await make_user(db_session, username="alice", password="pw")
    cal_a = await make_calendar(db_session, user.id, name="A")
    cal_b = await make_calendar(db_session, user.id, name="B")
    task = await make_task(db_session, cal_a.id, summary="Mover")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.post(f"/admin/tasks/{task.id}/move", json={"calendar_id": cal_b.id})
    assert resp.status_code == 200
    await db_session.refresh(task)
    assert task.calendar_id == cal_b.id

    # Moving to a calendar the user cannot write is rejected.
    mallory = await make_user(db_session, username="mallory", password="pw")
    cal_m = await make_calendar(db_session, mallory.id, name="M")
    resp = await client.post(f"/admin/tasks/{task.id}/move", json={"calendar_id": cal_m.id})
    assert resp.status_code == 403
    await db_session.refresh(task)
    assert task.calendar_id == cal_b.id


@pytest.mark.asyncio
async def test_move_task_readonly_source_403(client, db_session):
    alice = await make_user(db_session, username="alice", password="pw")
    bob = await make_user(db_session, username="bob", password="pw")
    cal_ro = await make_calendar(db_session, alice.id, name="RO")
    cal_b = await make_calendar(db_session, bob.id, name="B")
    await make_share(db_session, cal_ro.id, bob.id, SharePermission.READ)
    task = await make_task(db_session, cal_ro.id, summary="Locked")
    login = await client.post("/admin/login", data={"username": "bob", "password": "pw"})
    assert login.status_code == 302

    resp = await client.post(f"/admin/tasks/{task.id}/move", json={"calendar_id": cal_b.id})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_task_page_shows_empty_writable_calendar_headers(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal_a = await make_calendar(db_session, user.id, name="HasTasks")
    cal_b = await make_calendar(db_session, user.id, name="EmptyCal")
    await make_task(db_session, cal_a.id, summary="T1")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.get("/admin/tasks")
    assert resp.status_code == 200
    assert f'data-cal-header="{cal_b.id}"' in resp.text
    assert f'data-cal-header="{cal_a.id}"' in resp.text
