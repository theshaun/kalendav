# KalenDAV

A lightweight, async CalDAV server built with FastAPI and SQLAlchemy.

## Features

- **CalDAV Protocol Support**: Full CalDAV operations (OPTIONS, PROPFIND, PROPPATCH, GET, PUT, DELETE, REPORT, MKCALENDAR) with RFC 6764 service discovery and RFC 3744 access control
- **Multiple Users**: Support for multiple user accounts
- **Multiple Calendars**: Each user can have multiple calendars with custom colors
- **Calendar Sharing**: Share calendars between users with read, write, or admin permissions
- **Web Calendar**: Beautiful web interface for viewing and managing events
- **Recurring Events**: Full support for recurring events (daily, weekly, monthly, yearly)
- **Calendar Management**: Rename calendars and change colors via CalDAV clients
- **ICS Feed Support**: Access calendars via ICS feeds using API keys or Basic Auth
- **ICS Import**: Upload `.ics` files from the web UI
- **Admin UI**: Web-based administration panel for managing users, calendars, and shares
- **User Dashboard**: Personal dashboard for non-admin users to manage their calendars
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

#### Live Frontend Development

The `docker-compose.yml` includes a `vite-dev` service that watches source
files and serves them via HMR at `:5173`. The `caldav` service sets
`VITE_DEV=true` so templates point at the dev server instead of the built
manifest:

```bash
docker-compose up -d
# Edit files in app/static/src/ — changes appear immediately in the browser.
```

For production builds, the multi-stage `Dockerfile` runs `npm run build`
and copies only the hashed bundles into the runtime image.

### Manual Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install JS deps and build frontend (Node 20+ required)
npm install
npm run build

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

For live frontend development, set `VITE_DEV=true` and run the Vite dev
server separately:

```bash
VITE_DEV=true uvicorn app.main:app --reload
npm run dev  # serves at http://localhost:5173
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
| `BASE_URI` | Override auto-detected server URL | `http://localhost:8000` |
| `DEFAULT_TIMEZONE` | IANA timezone for naive datetimes | `UTC` |

### Reverse Proxy

KalenDAV auto-detects its public URL from `X-Forwarded-Proto` and
`X-Forwarded-Host` headers — set `BASE_URI` only if the auto-detection
doesn't match your public URL.

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

**For Admins:**
- Create and manage users
- Create and manage all calendars
- Set up calendar sharing
- Generate API keys for ICS feeds
- View system statistics

**For Regular Users:**
- Manage your own calendars
- View shared calendars (with permission indicators)
- Create and manage your own API keys
- Use the web calendar interface

### Web Calendar

Access the web calendar at `http://localhost:8000/admin/calendar/`

Features:
- **Multiple Views**: Day, week, and month views
- **Event Management**: Create, edit, and delete events with a modern interface
- **Recurring Events**: Set up daily, weekly, monthly, or yearly recurring events
- **Time Slots**: Click on specific times in day/week view to create events with 30-minute default duration
- **Event Colors**: Per-event color overrides or inherit from calendar color
- **Calendar Colors**: Events display in their calendar's color
- **Shared Calendars**: View events from calendars shared with you
- **Permissions**: Edit rights are enforced — read-only calendars cannot be modified
- **ICS Import**: Upload `.ics` files directly from the calendar view

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

### Calendar Sharing

Share calendars with other users:

1. Go to **My Calendars** in the admin interface
2. Click **Shares** on the calendar you want to share
3. Select a user and permission level:
   - **Read**: Can view events only
   - **Write**: Can view, create, and edit events
   - **Admin**: Full control including sharing management

Shared calendars appear in both the CalDAV client and web calendar with clear permission indicators.

## Supported CalDAV Clients

KalenDAV works with most CalDAV-compatible clients:

**Desktop:**
- Thunderbird (with Lightning)
- macOS Calendar
- Microsoft Outlook (with CalDAV Synchronizer)
- Evolution

**Mobile:**
- iOS Calendar
- Android (via DAVx⁵)
- Android (via KashCal)

**Web:**
- Built-in web calendar at `/admin/calendar/`

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
# Install all dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
npm install

# Run frontend build
npm run build

# Run with auto-reload
uvicorn app.main:app --reload

# Run tests
pytest tests/
```

## License

MIT
