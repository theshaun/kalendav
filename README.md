# KalenDAV

A lightweight, async CalDAV server built with FastAPI and SQLAlchemy.

## Features

- **CalDAV Protocol Support**: Full CalDAV operations (OPTIONS, PROPFIND, PROPPATCH, GET, PUT, DELETE, REPORT, MKCALENDAR)
- **Multiple Users**: Support for multiple user accounts
- **Multiple Calendars**: Each user can have multiple calendars with custom colors
- **Calendar Sharing**: Share calendars between users with read, write, or admin permissions
- **Web Calendar**: Beautiful web interface for viewing and managing events
- **Recurring Events**: Full support for recurring events (daily, weekly, monthly, yearly)
- **Calendar Management**: Rename calendars and change colors via CalDAV clients
- **ICS Feed Support**: Access calendars via ICS feeds using API keys or Basic Auth
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
- **Calendar Colors**: Events display in their calendar's color
- **Shared Calendars**: View events from calendars shared with you
- **Permissions**: Edit rights are enforced - read-only calendars cannot be modified

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

KalenDAV should works with most CalDAV-compatible clients:

**Desktop:**
- Thunderbird (with Lightning)
- macOS Calendar
- Microsoft Outlook (with CalDAV Synchronizer)
- Evolution

**Mobile:**
- iOS Calendar
- Android (via DAVx⁵)

**Web:**
- Built-in web calendar at `/admin/calendar/`

**Recommended Settings:**
- Server URL: `http://your-server:8000/dav/`
- Use SSL/TLS in production
- Enable periodic sync (recommended: 15-30 minutes)

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

## License

MIT
