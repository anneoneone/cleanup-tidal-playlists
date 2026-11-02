"""Protect the local server against other websites in the same browser.

- Host must be ``127.0.0.1:<port>`` or ``localhost:<port>`` (stops DNS rebinding).
- Requests that change something must send ``X-Cratekeeper: 1``. A browser only
  adds custom headers for same-origin requests or after a CORS preflight, and
  the server allows no CORS, so other sites cannot send it.
- If such a request carries an ``Origin``, it must be the server's own origin.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
HEADER = "x-cratekeeper"


class LocalOnlyGuard:
    """ASGI-style HTTP middleware for :func:`FastAPI.middleware`."""

    def __init__(
        self,
        port: int,
        extra_origins: Iterable[str] = (),
        extra_hosts: Iterable[str] = (),
    ) -> None:
        """Allow this ``port``; extras are for the Vite dev server and tests."""
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.allowed_hosts = hosts | set(extra_hosts)
        self.allowed_origins = {f"http://{h}" for h in hosts} | set(extra_origins)

    async def __call__(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Reject requests that do not come from Cratekeeper's own page."""
        host = request.headers.get("host", "")
        if host not in self.allowed_hosts:
            return JSONResponse({"detail": "Host not allowed"}, status_code=403)
        if request.method not in SAFE_METHODS:
            if request.headers.get(HEADER) != "1":
                return JSONResponse(
                    {"detail": "Missing X-Cratekeeper header"}, status_code=403
                )
            origin = request.headers.get("origin")
            if origin is not None and origin not in self.allowed_origins:
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        return await call_next(request)
