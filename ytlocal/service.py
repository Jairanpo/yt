"""Background singleton for `yt serve`: at most one server per user, per machine.

Two layers, doing different jobs. A flock'd file under $XDG_RUNTIME_DIR is the
source of truth for "is it up?" -- the kernel releases the lock however the
process dies, so there is never a stale pidfile to second-guess. A systemd user
unit is what starts the thing at login and puts it back if it falls over.
"""
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UNIT = "ytlocal.service"


class ServiceError(RuntimeError):
    """Something went wrong starting or stopping the background server."""


# --- where state lives -----------------------------------------------------

def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    d = Path(base) / "ytlocal" if base else Path(tempfile.gettempdir()) / f"ytlocal-{os.getuid()}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lock_path() -> Path:
    return runtime_dir() / "serve.lock"


def log_path() -> Path:
    return runtime_dir() / "serve.log"


def unit_path() -> Path:
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return cfg / "systemd" / "user" / UNIT


# --- the lock itself -------------------------------------------------------

# Held open for the lifetime of the serving process. Closing it drops the lock,
# so this must outlive every local scope: a module global is the whole point.
_held_fd = None


def claim(port: int):
    """Take the singleton lock for this process, or return False if taken."""
    global _held_fd
    fd = os.open(str(lock_path()), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    os.ftruncate(fd, 0)
    os.write(fd, json.dumps({"pid": os.getpid(), "port": port}).encode())
    os.fsync(fd)
    _held_fd = fd
    return True


def running():
    """{"pid": …, "port": …} for the live server, or None if there isn't one.

    An empty dict means one is up but we caught it mid-write; treat that as
    running-with-unknown-details rather than not running.
    """
    path = lock_path()
    if not path.exists():
        return None
    fd = os.open(str(path), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            return json.loads(os.read(fd, 4096) or "{}")
        except json.JSONDecodeError:
            return {}
        finally:
            os.close(fd)
    # We got the lock, so nobody is serving. Give it straight back.
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
    return None


# --- systemd ---------------------------------------------------------------

def _systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args],
                          capture_output=True, text=True)


def systemd_available() -> bool:
    """Is there a user bus we can actually talk to? (Not true over plain su.)"""
    if not shutil.which("systemctl"):
        return False
    return _systemctl("show-environment").returncode == 0


def installed() -> bool:
    return unit_path().exists()


def enabled() -> bool:
    return systemd_available() and _systemctl("is-enabled", UNIT).stdout.strip() == "enabled"


def unit_active() -> bool:
    return systemd_available() and _systemctl("is-active", UNIT).stdout.strip() == "active"


UNIT_TEMPLATE = """\
[Unit]
Description=ytlocal web library
After=default.target

[Service]
Type=simple
ExecStart={exec_start}
# yt-dlp lives on the user's PATH, which a user manager started at boot may not
# have yet. Pin the PATH that was in effect when this unit was installed.
Environment=PATH={path}
Environment=PYTHONPATH={root}
WorkingDirectory={root}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""


def _exec_start() -> str:
    """Absolute command line for the unit. Nothing here may rely on a PATH."""
    return f"{sys.executable} -m ytlocal serve --foreground --no-open"


def _clean_path() -> str:
    """The current PATH, deduplicated -- shells stack it up over a session."""
    seen, keep = set(), []
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if part and part not in seen:
            seen.add(part)
            keep.append(part)
    return os.pathsep.join(keep)


def install(port=None) -> Path:
    """Write and enable the user unit so the library is up after every login."""
    if not systemd_available():
        raise ServiceError("no systemd user session here; "
                           "start it by hand with  yt serve")
    root = Path(__file__).resolve().parent.parent
    exec_start = _exec_start()
    if port:
        exec_start += f" --port {int(port)}"
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(UNIT_TEMPLATE.format(
        exec_start=exec_start, path=_clean_path(), root=root))
    _systemctl("daemon-reload")
    r = _systemctl("enable", UNIT)
    if r.returncode:
        raise ServiceError(r.stderr.strip() or f"could not enable {UNIT}")
    return path


def uninstall() -> bool:
    """Undo install(). Leaves a running server alone; stop() is stop()'s job."""
    if not installed():
        return False
    if systemd_available():
        _systemctl("disable", UNIT)
    unit_path().unlink()
    if systemd_available():
        _systemctl("daemon-reload")
    return True


# --- start / stop ----------------------------------------------------------

def start(port=None, verbose=False, timeout=15.0):
    """Bring the singleton up and wait until it is listening. Returns its state."""
    if running():
        raise ServiceError("already running")
    if installed() and systemd_available():
        r = _systemctl("start", UNIT)
        if r.returncode:
            raise ServiceError(r.stderr.strip() or f"could not start {UNIT}")
        where = f"journalctl --user -u {UNIT}"
    else:
        _spawn(port, verbose)
        where = str(log_path())
    st = _wait(lambda: running(), timeout)
    if st is None:
        raise ServiceError(f"server did not come up within {timeout:g}s; see {where}")
    return st


def _spawn(port, verbose):
    """Detached child, outliving the shell that typed the command."""
    cmd = [sys.executable, "-m", "ytlocal", "serve", "--foreground", "--no-open"]
    if port:
        cmd += ["--port", str(port)]
    if verbose:
        cmd.append("--verbose")
    with open(log_path(), "ab") as fh:
        subprocess.Popen(cmd, stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
                         start_new_session=True)


def stop(timeout=15.0) -> bool:
    """Take it down however it was started. False if nothing was running."""
    st = running()
    if st is None:
        return False
    if unit_active():
        r = _systemctl("stop", UNIT)
        if r.returncode:
            raise ServiceError(r.stderr.strip() or f"could not stop {UNIT}")
    elif st.get("pid"):
        try:
            os.kill(st["pid"], signal.SIGTERM)
        except ProcessLookupError:
            return True
    else:
        raise ServiceError("a server holds the lock but left no pid to signal")
    if _wait(lambda: None if running() else True, timeout) is None:
        raise ServiceError(f"server ignored the stop request for {timeout:g}s")
    return True


def _wait(check, timeout, interval=0.05):
    deadline = time.monotonic() + timeout
    while True:
        got = check()
        if got:
            return got
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval)
