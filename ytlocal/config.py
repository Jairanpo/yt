"""Config resolution: XDG paths, JSON overrides, env overrides."""
import json
import os
from pathlib import Path

APP = "ytlocal"


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


DATA_DIR = Path(os.environ.get("YTLOCAL_DATA") or _xdg("XDG_DATA_HOME", ".local/share") / APP)
CONFIG_PATH = Path(
    os.environ.get("YTLOCAL_CONFIG") or _xdg("XDG_CONFIG_HOME", ".config") / APP / "config.json"
)
DB_PATH = DATA_DIR / "catalog.db"
THUMB_DIR = DATA_DIR / "thumbs"

DEFAULTS = {
    # Where downloaded media lives. One subdirectory per channel.
    "media_dir": str(Path.home() / "Videos" / "yt"),
    # Max video height to fetch. 1080 keeps files sane and browser-friendly.
    "max_height": 1080,
    # Subtitle languages, yt-dlp --sub-langs syntax. Keep these exact rather
    # than wildcards: "en.*" also matches every auto-translated track, which
    # means dozens of requests per video and a fast 429 from YouTube.
    "sub_langs": "en,es",
    # Port for `yt serve`.
    "port": 8420,
    # External player for `yt watch --external`. None -> autodetect mpv/vlc/xdg-open.
    "player": None,
    # yt-dlp executable.
    "ytdlp": "yt-dlp",
    # Extra args appended to every yt-dlp invocation (e.g. cookies, rate limit).
    "ytdlp_args": [],
}

_ENV_OVERRIDES = {
    "media_dir": "YTLOCAL_MEDIA",
    "port": "YTLOCAL_PORT",
    "ytdlp": "YTLOCAL_YTDLP",
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"config at {CONFIG_PATH} is not valid JSON: {exc}")
    for key, env in _ENV_OVERRIDES.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    cfg["port"] = int(cfg["port"])
    cfg["max_height"] = int(cfg["max_height"])
    cfg["media_dir"] = str(Path(cfg["media_dir"]).expanduser())
    return cfg


def write_default_config() -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(DEFAULTS, indent=2) + "\n")
    return CONFIG_PATH


def media_dir(cfg: dict) -> Path:
    path = Path(cfg["media_dir"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
