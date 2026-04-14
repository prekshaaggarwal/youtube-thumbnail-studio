"""
Windows helper: resolve conflicts on 127.0.0.1:8080 before starting Flask.

- If nothing listens: exit 0 (use 8080).
- If our app already responds correctly: exit 4 (tell batch: do not start another server).
- If something else (or old app) listens: try to terminate that PID, exit 0.
- On failure: exit 2 (batch should pick another port).
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

HOST = "127.0.0.1"
PORT = 8080
BUILD_INFO = f"http://{HOST}:{PORT}/api/build-info"


def _listening_pids() -> list[str]:
    try:
        r = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except OSError:
        return []
    pids: list[str] = []
    needle = f"{HOST}:{PORT}"
    for line in r.stdout.splitlines():
        if "LISTENING" not in line:
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        pid = parts[-1]
        if pid.isdigit():
            pids.append(pid)
    return list(dict.fromkeys(pids))


def _is_our_app() -> bool:
    try:
        with urllib.request.urlopen(BUILD_INFO, timeout=2) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return False
    return (
        data.get("app") == "thumbnail-studio"
        and data.get("has_route_studio") is True
    )


def _kill_pid(pid: str) -> bool:
    r = subprocess.run(
        ["taskkill", "/F", "/PID", pid],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return r.returncode == 0


def main() -> int:
    pids = _listening_pids()
    if not pids:
        return 0

    if _is_our_app():
        print("")
        print("Thumbnail Studio is already running on http://127.0.0.1:8080/")
        print("Open: http://127.0.0.1:8080/studio")
        print("")
        return 4

    print("")
    print("Port 8080 is in use by another process (PID %s)." % ", ".join(pids))
    print("Stopping it so this project can bind to 8080...")
    for pid in pids:
        if _kill_pid(pid):
            print("  Stopped PID", pid)
        else:
            print("  Could not stop PID", pid, file=sys.stderr)
    # Re-check
    if _listening_pids():
        print("Port 8080 still busy — launcher will try another port.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
