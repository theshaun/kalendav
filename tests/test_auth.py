"""Characterization tests for app/auth/basic.py and app/auth/dependencies.py.

password/api-key hashing is unit-tested directly; get_current_user (HTTP Basic)
is exercised end-to-end via a real protected CalDAV endpoint (PROPFIND /dav/,
which depends on get_current_user — unlike OPTIONS /dav/ which is unauthenticated).
"""
import pytest

from app.auth.basic import (
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


# ---------- password hashing ----------

def test_hash_password_verify_round_trip():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert verify_password("s3cret", h) is True


def test_verify_password_wrong_password():
    h = hash_password("s3cret")
    assert verify_password("wrong", h) is False


def test_verify_password_corrupted_hash_returns_false():
    # non-bcrypt hash triggers UnknownHashError, which is caught -> False
    assert verify_password("anything", "not-a-real-hash") is False


def test_verify_password_empty_hash_returns_false():
    assert verify_password("anything", "") is False


# ---------- api key generation / hashing ----------

def test_generate_api_key_distinct_across_calls():
    a = generate_api_key()
    b = generate_api_key()
    assert a != b
    assert len(a) > 0


def test_hash_api_key_deterministic():
    assert hash_api_key("key-one") == hash_api_key("key-one")


def test_hash_api_key_distinct_inputs():
    assert hash_api_key("key-one") != hash_api_key("key-two")


def test_hash_api_key_is_sha256_hex():
    # sha256 hex digest is 64 chars
    assert len(hash_api_key("x")) == 64


# ---------- get_current_user via HTTP Basic on a protected endpoint ----------

@pytest.mark.asyncio
async def test_get_current_user_valid_credentials(client, db_session):
    from tests.conftest import basic_auth_header, make_user

    await make_user(db_session, username="alice", password="pw")
    resp = await client.request(
        "PROPFIND", "/dav/", headers=basic_auth_header("alice", "pw")
    )
    # PROPFIND root returns 207 multistatus when authenticated
    assert resp.status_code == 207


@pytest.mark.asyncio
async def test_get_current_user_wrong_password_returns_401(client, db_session):
    from tests.conftest import basic_auth_header, make_user

    await make_user(db_session, username="alice", password="pw")
    resp = await client.request(
        "PROPFIND", "/dav/", headers=basic_auth_header("alice", "wrong")
    )
    assert resp.status_code == 401
    assert "Basic" in resp.headers.get("WWW-Authenticate", "")


@pytest.mark.asyncio
async def test_get_current_user_unknown_user_returns_401(client, db_session):
    from tests.conftest import basic_auth_header

    resp = await client.request(
        "PROPFIND", "/dav/", headers=basic_auth_header("ghost", "pw")
    )
    assert resp.status_code == 401
    assert "Basic" in resp.headers.get("WWW-Authenticate", "")


@pytest.mark.asyncio
async def test_get_current_user_missing_auth_returns_401(client):
    resp = await client.request("PROPFIND", "/dav/")
    assert resp.status_code == 401
    assert "Basic" in resp.headers.get("WWW-Authenticate", "")


# ---------- get_current_user_optional (the optional HTTP Basic variant) ----------

@pytest.mark.asyncio
async def test_optional_no_credentials_returns_none(db_session):
    from app.auth.dependencies import get_current_user_optional

    assert await get_current_user_optional(None, db_session) is None


@pytest.mark.asyncio
async def test_optional_valid_credentials_returns_user(db_session):
    from fastapi.security import HTTPBasicCredentials

    from app.auth.dependencies import get_current_user_optional
    from tests.conftest import make_user

    await make_user(db_session, username="bob", password="pw")
    creds = HTTPBasicCredentials(username="bob", password="pw")
    user = await get_current_user_optional(creds, db_session)
    assert user is not None
    assert user.username == "bob"


@pytest.mark.asyncio
async def test_optional_invalid_credentials_returns_none(db_session):
    from fastapi.security import HTTPBasicCredentials

    from app.auth.dependencies import get_current_user_optional
    from tests.conftest import make_user

    await make_user(db_session, username="bob", password="pw")
    creds = HTTPBasicCredentials(username="bob", password="wrong")
    assert await get_current_user_optional(creds, db_session) is None


@pytest.mark.asyncio
async def test_optional_unknown_user_returns_none(db_session):
    from fastapi.security import HTTPBasicCredentials

    from app.auth.dependencies import get_current_user_optional

    creds = HTTPBasicCredentials(username="ghost", password="pw")
    assert await get_current_user_optional(creds, db_session) is None
