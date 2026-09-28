"""Toggl Track API v9, enough of it to run one timer.

The browser extension used to be the way in: you pasted a small script into it
and it drove the timer from the page. Manifest V3 took user scripts away, so
custom integrations and development mode are gone from the shipped extension
with no date for their return. This talks to the API instead.

The call is made from here, not from the page. The library's own page still
reaches nothing but this server -- it asks localhost to start a timer, and
localhost is what knows the token and where to send it.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.track.toggl.com/api/v9"
TIMEOUT = 15
# Projects change rarely and a name has to be resolved to an id on every start;
# a short memory keeps a click from costing two round trips.
_PROJECT_TTL = 300
_cache = {"workspace": None, "projects": None, "projects_at": 0}


class TogglError(RuntimeError):
    """Something the user needs to read, not a stack trace."""


def token(cfg) -> str:
    return (os.environ.get("YTLOCAL_TOGGL_TOKEN") or cfg.get("toggl_token") or "").strip()


def configured(cfg) -> bool:
    return bool(token(cfg))


def _call(cfg, method, path, body=None):
    tok = token(cfg)
    if not tok:
        raise TogglError(
            "no Toggl API token — put one in toggl_token in your config "
            "(Toggl → Profile settings → API token)")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    # The token goes in as the username with the literal word api_token as the
    # password; that is Toggl's scheme, not a placeholder.
    auth = base64.b64encode(f"{tok}:api_token".encode()).decode()
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = (exc.read() or b"").decode(errors="replace").strip()[:300]
        if exc.code in (401, 403):
            raise TogglError("Toggl rejected the token — check toggl_token") from exc
        raise TogglError(f"Toggl said {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise TogglError(f"could not reach Toggl: {exc.reason}") from exc


def workspace(cfg) -> int:
    """The workspace to file entries under, from config or your default."""
    if cfg.get("toggl_workspace"):
        return int(cfg["toggl_workspace"])
    if _cache["workspace"] is None:
        me = _call(cfg, "GET", "/me")
        wid = me.get("default_workspace_id")
        if not wid:
            raise TogglError("your Toggl account reports no default workspace; "
                             "set toggl_workspace in the config")
        _cache["workspace"] = int(wid)
    return _cache["workspace"]


def _project_id(cfg, wid, name):
    """Resolve a project name to its id. Unknown names are not fatal."""
    if not name:
        return None
    fresh = time.time() - _cache["projects_at"] < _PROJECT_TTL
    if not fresh or _cache["projects"] is None:
        rows = _call(cfg, "GET", f"/workspaces/{wid}/projects") or []
        _cache["projects"] = {(p.get("name") or "").casefold(): p.get("id")
                              for p in rows}
        _cache["projects_at"] = time.time()
    return _cache["projects"].get(name.casefold())


def forget_projects() -> None:
    """Drop the project cache, for when a name was just created in Toggl."""
    _cache["projects"] = None
    _cache["projects_at"] = 0


def current(cfg):
    """The running entry, or None. Cheap enough to ask on every page load."""
    return _call(cfg, "GET", "/me/time_entries/current")


def start(cfg, description, project=None, tags=()):
    """Start a timer now. A project name Toggl does not know is left off."""
    wid = workspace(cfg)
    pid = _project_id(cfg, wid, project)
    missing = bool(project) and pid is None
    entry = _call(cfg, "POST", f"/workspaces/{wid}/time_entries", {
        "created_with": "ytlocal",
        "workspace_id": wid,
        "description": description or "",
        "project_id": pid,
        "tags": [t for t in tags if t],
        # A negative duration is how v9 says "still running".
        "duration": -1,
        "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stop": None,
    })
    return entry, missing


def stop(cfg, entry_id, wid=None):
    wid = wid or workspace(cfg)
    return _call(cfg, "PATCH", f"/workspaces/{wid}/time_entries/{entry_id}/stop")


def as_json(entry) -> dict:
    """The parts of an entry the page has any use for."""
    if not entry:
        return {}
    return {"id": entry.get("id"),
            "description": entry.get("description") or "",
            "project_id": entry.get("project_id"),
            "workspace_id": entry.get("workspace_id"),
            "tags": entry.get("tags") or [],
            "start": entry.get("start")}
