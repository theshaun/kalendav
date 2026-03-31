# KalenDAV

A lightweight, async CalDAV server built with FastAPI and SQLAlchemy.

## Features

- **CalDAV Protocol Support**: Core CalDAV operations (PROPFIND, GET, PUT, DELETE, REPORT, MKCALENDAR)
- **Multiple Users**: Support for multiple user accounts
- **Multiple Calendars**: Each user can have multiple calendars
- **Calendar Sharing**: Share calendars between users with read-only or read-write permissions
- **ICS Feed Support**: Access calendars via ICS feeds using API keys or Basic Auth
- **Admin UI**: Web-based administration panel for managing users, calendars, and shares
- **Async**: Fully async using SQLAlchemy 2.0 async support
- **SQLite & PostgreSQL**: SQLite for development, PostgreSQL for production

## Quick Start

### Using Docker (Recommended)

```bash
# Build and run
docker-compose up -d

# Access the server
# CalDAV: http://localhost:8000/dav/
# Admin UI: http://localhost:8000/admin/
# ICS Feed: http://localhost:8000/ics/{calendar_id}?api_key=xxx
```

### Manual Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your settings

# Initialize database
alembic upgrade head

# Create admin user
python init_admin.py

# Run the server
uvicorn app.main:app --reload
```

## Configuration

Configuration is done via environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection URL | `sqlite+aiosqlite:///./caldav.db` |
| `SECRET_KEY` | Secret key for sessions | *required* |
| `ADMIN_USER` | Default admin username | `admin` |
| `ADMIN_PASSWORD` | Default admin password | `admin` |
| `DEBUG` | Enable debug mode | `false` |

### Database URLs

**SQLite** (default):
```
DATABASE_URL=sqlite+aiosqlite:///./caldav.db
```

**PostgreSQL**:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/caldav
```

## Usage

### Connecting Calendar Clients

Configure your calendar client (Thunderbird, macOS Calendar, etc.) with:

- **Server URL**: `http://localhost:8000/dav/`
- **Username**: Your username
- **Password**: Your password

### Admin Interface

Access the admin UI at `http://localhost:8000/admin/` with admin credentials.

From here you can:
- Create and manage users
- Create and manage calendars
- Set up calendar sharing
- Generate API keys for ICS feeds

### ICS Feeds

Access calendars via ICS feed:

```
http://localhost:8000/ics/{calendar_id}?api_key=YOUR_API_KEY
```

Or using Basic Auth:

```
http://localhost:8000/ics/{calendar_id}
# with username/password
```

## API Endpoints

### CalDAV Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `PROPFIND` | `/dav/` | Principal discovery |
| `PROPFIND` | `/dav/{user}/calendars/` | List calendars |
| `PROPFIND` | `/dav/{user}/calendars/{id}/` | Calendar properties |
| `MKCALENDAR` | `/dav/{user}/calendars/{id}/` | Create calendar |
| `GET` | `/dav/{user}/calendars/{id}/` | Get calendar (ICS) |
| `PUT` | `/dav/{user}/calendars/{id}/{event}.ics` | Create/update event |
| `DELETE` | `/dav/{user}/calendars/{id}/{event}.ics` | Delete event |
| `REPORT` | `/dav/{user}/calendars/{id}/` | Query events |

### ICS Feed Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ics/{calendar_id}` | Get ICS feed |

### Admin Endpoints

| Path | Description |
|------|-------------|
| `/admin/` | Dashboard |
| `/admin/users` | User management |
| `/admin/calendars` | Calendar management |
| `/admin/api-keys` | API key management |

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Development

```bash
# Install development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run with auto-reload
uvicorn app.main:app --reload

# Run tests
pytest tests/
```

## Project Structure

```
kalendav/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry
│   ├── config.py            # Settings (env vars)
│   ├── database.py          # Async engine, sessions
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic models
│   ├── caldav/              # CalDAV protocol
│   ├── ics_feed/            # ICS feed endpoints
│   ├── admin/               # Admin UI
│   ├── auth/                # Authentication
│   └── services/            # Business logic
├── alembic/                 # Database migrations
├── tests/                   # Test files
├── requirements.txt         # Dependencies
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## License

MIT
