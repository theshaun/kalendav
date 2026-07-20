"""KalenDAV — lightweight async CalDAV server.

The version string below is the single source of truth for the project.
``pyproject.toml`` reads it dynamically via hatchling, ``app.main`` surfaces
it on the FastAPI app and ``/health`` endpoint, and release tags should
match it (``v0.1.0`` for ``__version__ == "0.1.0"``).
"""

__version__ = "0.1.0"
