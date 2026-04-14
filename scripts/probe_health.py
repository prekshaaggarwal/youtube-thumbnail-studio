"""Print /health for 8080 and 8765 — used by check-server.bat."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request

_TIMEOUT = 1.0


def _label_exc(e: BaseException) -> str:
    if isinstance(e, urllib.error.URLError) and e.reason is not None:
        r = e.reason
        if isinstance(r, ConnectionRefusedError):
            return "connection refused (server not running on this port)"
        if isinstance(r, socket.timeout):
            return "timeout (nothing responded — server likely down)"
        return f"{type(r).__name__}: {r}"
    if isinstance(e, TimeoutError):
        return "timeout (server likely down)"
    return f"{type(e).__name__}: {e}"


for port in (8080, 8765):
    url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            body = r.read().decode("utf-8", errors="replace")[:200]
        print(f"{port}  OK  {body}")
    except Exception as e:
        print(f"{port}  --  {_label_exc(e)}")
