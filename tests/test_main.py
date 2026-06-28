import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_unauthorized(client):
    response = await client.get("/admin/")
    # LoginRequiredException handler (app/main.py:24-25) returns a 302
    # redirect to /admin/login, raised before any DB query.
    assert response.status_code == 302
