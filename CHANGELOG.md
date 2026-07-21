# Changelog

All notable changes to KalenDAV are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **CalDAV discovery (KashCal)**: `.well-known/caldav` now returns a proper 207
  Multi-Status response with `calendar-home-set` instead of a 301 redirect.
  XML generation moved to `xml_responses.build_well_known_caldav()`.
- **CalDAV discovery (KashCal)**: root `/dav/` PROPFIND now includes
  `current-user-principal` per RFC 5987, and no longer advertises
  `<c:calendar/>` in `resourcetype` on non-calendar resources.
- **CalDAV read-only (KashCal)**: calendar PROPFIND responses now include
  `current-user-privilege-set` (RFC 3744 §4.3). Writable calendars advertise
  `write`, `write-content`, `write-properties`, `bind`, `unbind` privileges;
  read-only shared calendars only advertise `read`. Previously absent, causing
  strict clients like KashCal to treat all calendars as read-only.
- **Web calendar (htmx)**: `htmx` is now explicitly assigned to `window.htmx`
  in `main.js`. The Vite ESM migration loaded htmx as a bare side-effect
  import which does not set the global, breaking `htmx.ajax()` calls in the
  calendar template's module scripts (both event editing and creation).

## [0.1.0] - 2026-07-20

First tagged release. Establishes the CalDAV server, admin UI, web calendar,
ICS feed, and the versioning machinery (`app.__version__`, `pyproject.toml`,
this changelog, `git tag v0.1.0`).

### Added
- **CalDAV protocol**: OPTIONS, PROPFIND, PROPPATCH, GET, PUT, DELETE, REPORT,
  MKCALENDAR. `.well-known/caldav` redirect per RFC 6764 (iOS support).
- **Multi-user & multi-calendar**: per-user calendars with custom colors;
  default calendar bootstrapped on user creation.
- **Calendar sharing**: read / write / admin permission levels via
  `calendar_shares` table.
- **Web calendar UI**: day / week / month views, event CRUD, recurring events
  (daily / weekly / monthly / yearly), calendar-color rendering, shared-calendar
  visibility with permission indicators. Accessible at `/admin/calendar/`.
- **Admin UI**: manage users, calendars, shares, and API keys. Personal
  dashboard for non-admin users at `/admin/`.
- **ICS feeds**: per-calendar ICS output via API key or Basic Auth at
  `/ics/{calendar_id}`.
- **ICS import**: upload `.ics` files from the web UI.
- **Per-event color & timezone**: `events.color` and `events.timezone` columns
  (alembic revisions `002`, `003`); both nullable with sensible fallbacks
  (calendar color, `DEFAULT_TIMEZONE`).
- **Auth**: bcrypt-hashed passwords, session-based admin/UI auth, pluggable
  CalDAV HTTP basic auth.
- **Async stack**: FastAPI + SQLAlchemy 2.0 async; SQLite (default) and
  PostgreSQL (production) backends.
- **Docker**: `Dockerfile` + `docker-compose.yml` with optional PostgreSQL
  service.
- **Versioning**: `app.__version__` as single source of truth, dynamic version
  in `pyproject.toml` via hatchling, `/health` exposes `version`, FastAPI
  OpenAPI `version` field populated.
- **Tests**: `tests/` covering auth, CalDAV router, ICS feed, and event
  service. Pytest with async mode and coverage thresholds.

### Security
- bcrypt pinned to `>=4.0.0,<4.1.0` to match `passlib[bcrypt]` expectations
  and avoid hash-format regressions.
- `SECRET_KEY` required for session signing — defaults to a development value
  and **must** be overridden in production via `.env`.

### Database Migrations
- `001` — initial schema (users, calendars, calendar_shares, events, api_keys)
- `002` — `events.color` (nullable string, used to override calendar color)
- `003` — `events.timezone` (nullable IANA tz name, falls back to
  `DEFAULT_TIMEZONE` at serialization)

[Unreleased]: https://github.com/theshaun/kalendav/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/theshaun/kalendav/releases/tag/v0.1.0
