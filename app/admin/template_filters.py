"""Jinja2 template filters for Vite asset resolution.

Two modes:
  * Dev  (VITE_DEV=true)  — return the live Vite dev server URL.
  * Prod (default)        — look up the entry in build/manifest.json and
                            return its hashed path under /static/.

The manifest is loaded once per process and cached; the cache is invalidated
automatically when the file's mtime changes (covers re-builds while the
server is running).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jinja2 import Environment

VITE_DEV_ORIGIN = "http://localhost:5173"
MANIFEST_RELATIVE_PATH = Path("app/static/dist/manifest.json")

# Module-level cache. Keyed only by mtime so a rebuild during the process
# lifetime is picked up on the next render without a server restart.
_manifest_cache: dict[str, object] = {"mtime": -1.0, "data": {}}


def _load_manifest() -> dict[str, object]:
    """Read and cache the Vite manifest, refreshing when its mtime changes."""
    path = MANIFEST_RELATIVE_PATH
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Vite manifest not found at "
            f"{MANIFEST_RELATIVE_PATH}. Run `npm run build` first, "
            "or set VITE_DEV=true to use the Vite dev server."
        ) from exc

    if mtime == _manifest_cache["mtime"]:
        # mypy: narrowed by the cached structure; cast through object.
        return _manifest_cache["data"]  # type: ignore[return-value]

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    _manifest_cache["mtime"] = mtime
    _manifest_cache["data"] = data
    return data


def vite_asset(entry_name: str) -> str:
    """Resolve a Vite entry name to a URL the browser can load.

    ``entry_name`` is the manifest key — the source path relative to the
    project root (e.g. ``app/static/src/main.js`` or ``app/static/src/calendar.js``),
    or ``style.css`` for the CSS bundle emitted under ``cssCodeSplit: false``.

    In dev (VITE_DEV=true), the entry is served by the Vite dev server at
    its source path, e.g. ``app/static/src/main.js`` ->
    ``http://localhost:5173/app/static/src/main.js``.

    In prod, the entry is looked up in manifest.json by its key and the
    hashed file path under ``/static/`` is returned.

    Args:
        entry_name: The Vite manifest key (source path relative to project
            root), e.g. ``app/static/src/main.js`` or ``style.css``.

    Returns:
        Absolute URL path (no host) suitable for ``<script src>`` or
        ``<link href>``. In dev mode, a full ``http://localhost:5173/...``
        URL is returned.

    Raises:
        RuntimeError: if the manifest is missing in prod mode, or if the
            entry is not present in the manifest.
    """
    if os.environ.get("VITE_DEV") == "true":
        return f"{VITE_DEV_ORIGIN}/{entry_name}"

    manifest = _load_manifest()
    if entry_name not in manifest:
        raise RuntimeError(
            f"Vite entry {entry_name!r} not found in manifest.json. "
            "Run `npm run build` to regenerate it."
        )

    entry = manifest[entry_name]
    if not isinstance(entry, dict) or "file" not in entry:
        raise RuntimeError(
            f"Vite entry {entry_name!r} in manifest.json is malformed: "
            f"expected an object with a 'file' key, got {entry!r}."
        )

    file_path = entry["file"]
    return f"/static/{file_path}"


def register_template_filters(jinja_env: Environment) -> None:
    """Register the Vite-related filters on a Jinja2 environment."""
    jinja_env.filters["vite_asset"] = vite_asset
