"""Wait until Flask answers GET /health (used by run-local.bat)."""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    url = f"http://127.0.0.1:{port}/health"
    for i in range(90):
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.getcode() == 200:
                    print(f"OK — server is listening on port {port}.")
                    return 0
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(1)
        if i in (4, 9, 19, 29):
            print(f"  Still waiting for {url!r} ... ({i + 1}s)")
    print(f"Timeout: no response from {url}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
