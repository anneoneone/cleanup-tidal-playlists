"""Tidal login: one stored session, non-blocking OAuth for the UI.

The session file is never deleted on errors. A network error must not cost the
user their login (v1 deleted the file on any exception).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from tidalapi.session import Session as TidalSession

logger = logging.getLogger(__name__)

LoginState = Literal["idle", "pending", "done", "failed"]


class TidalAuthError(RuntimeError):
    """Raised when there is no valid Tidal login."""


@dataclass(frozen=True)
class LoginStart:
    """What the user needs to finish an OAuth login in the browser."""

    url: str
    user_code: str
    expires_at: float


SessionFactory = Callable[[], Any]


class TidalAuth:
    """Owns the Tidal session for one home directory.

    Thread-safe.
    """

    def __init__(
        self, session_file: Path, session_factory: SessionFactory = TidalSession
    ) -> None:
        """Use ``session_file`` to store the login."""
        self.session_file = session_file
        self._factory = session_factory
        self._lock = threading.RLock()
        self._session: Any = None
        self._saved_tokens: Optional[tuple[str, str]] = None
        self._pending: Any = None
        self._start: Optional[LoginStart] = None
        self._state: LoginState = "idle"
        self._error: Optional[str] = None

    def has_stored_login(self) -> bool:
        """Return whether a login is stored (it may still be expired)."""
        return self.session_file.is_file()

    def session(self) -> Any:
        """Return a logged-in session or raise :class:`TidalAuthError`."""
        with self._lock:
            if self._session is not None:
                return self._session
            if not self.session_file.is_file():
                raise TidalAuthError(
                    "Not logged in to Tidal. Run 'cratekeeper login' or log in "
                    "on the Settings page."
                )
            data = self._read_file()
            session = self._factory()
            session.load_oauth_session(
                data["token_type"],
                data["access_token"],
                data.get("refresh_token"),
                _parse_expiry(data.get("expiry_time")),
            )
            if not session.check_login():
                raise TidalAuthError(
                    "The stored Tidal login is no longer valid. Log in again."
                )
            self._session = session
            self._saved_tokens = (session.access_token, session.refresh_token)
            return session

    def persist(self) -> None:
        """Save refreshed tokens (tidalapi refreshes them while requests run)."""
        with self._lock:
            session = self._session
            if session is None:
                return
            tokens = (session.access_token, session.refresh_token)
            if tokens != self._saved_tokens:
                self._write_file(session)
                self._saved_tokens = tokens

    def start_login(self) -> LoginStart:
        """Begin an OAuth login.

        The user opens the URL; poll :meth:`login_state`.
        """
        with self._lock:
            session = self._factory()
            link, future = session.login_oauth()
            url = getattr(link, "verification_uri_complete", "") or ""
            if url and not url.startswith("http"):
                url = f"https://{url}"
            start = LoginStart(
                url=url,
                user_code=str(getattr(link, "user_code", "")),
                expires_at=time.time() + float(getattr(link, "expires_in", 300)),
            )
            self._pending = (session, future)
            self._start = start
            self._state = "pending"
            self._error = None
            future.add_done_callback(lambda f: self._finish_login(session, f))
            return start

    def login_state(self) -> tuple[LoginState, Optional[str]]:
        """Return the state of the last login attempt and its error, if any."""
        with self._lock:
            return self._state, self._error

    def pending_login(self) -> Optional[LoginStart]:
        """Return the link and code of the login in progress, if any."""
        with self._lock:
            return self._start

    def wait_for_login(self, timeout: Optional[float] = None) -> LoginState:
        """Block until the pending login finishes (CLI)."""
        pending = self._pending
        if pending is not None:
            try:
                pending[1].result(timeout=timeout)
            except Exception:  # state and error are set by the callback
                logger.debug("Tidal login failed", exc_info=True)
        return self.login_state()[0]

    def _finish_login(self, session: Any, future: Any) -> None:
        with self._lock:
            try:
                future.result()
                if not session.check_login():
                    raise TidalAuthError("Tidal did not confirm the login")
                self._write_file(session)
                self._session = session
                self._saved_tokens = (session.access_token, session.refresh_token)
                self._state = "done"
                logger.info("Logged in to Tidal")
            except Exception as exc:
                self._state = "failed"
                self._error = str(exc) or exc.__class__.__name__
                logger.warning("Tidal login failed: %s", self._error)
            finally:
                self._pending = None
                self._start = None

    def _read_file(self) -> dict[str, Any]:
        try:
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TidalAuthError(f"Cannot read {self.session_file}: {exc}") from exc
        if not isinstance(data, dict) or "access_token" not in data:
            raise TidalAuthError(f"{self.session_file} has no Tidal tokens")
        data.setdefault("token_type", "Bearer")
        return data

    def _write_file(self, session: Any) -> None:
        expiry = getattr(session, "expiry_time", None)
        data = {
            "token_type": session.token_type,
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expiry_time": expiry.isoformat() if isinstance(expiry, datetime) else None,
        }
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.session_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.session_file)


def _parse_expiry(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
