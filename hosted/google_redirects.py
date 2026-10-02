"""Follow Google citation redirects without notebook-owned globals."""

import threading

import requests

from audit_core.domains import is_google_goto_url


class GoogleRedirectResolver:
    def __init__(self, *, session_factory=requests.Session, max_redirects=8):
        self._session_factory = session_factory
        self._max_redirects = max_redirects
        self._cache = {}
        self._lock = threading.RLock()

    def __call__(self, url, timeout_seconds=20):
        url = str(url or "").strip()
        if not url:
            return ""
        if not is_google_goto_url(url):
            return url
        with self._lock:
            if url in self._cache:
                return self._cache[url]

        session = self._session_factory()
        session.max_redirects = self._max_redirects
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; QavisoAudit/1.0; "
                "+https://qaviso.com/)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resolved = ""
        try:
            response = session.head(
                url, headers=headers, allow_redirects=True,
                timeout=timeout_seconds,
            )
            resolved = self._destination(response.url)
        except Exception:
            pass
        if not resolved:
            try:
                response = session.get(
                    url, headers=headers, allow_redirects=True,
                    timeout=timeout_seconds, stream=True,
                )
                resolved = self._destination(response.url)
                response.close()
            except Exception:
                pass
        close = getattr(session, "close", None)
        if callable(close):
            close()
        with self._lock:
            self._cache[url] = resolved
        return resolved

    @staticmethod
    def _destination(value):
        value = str(value or "").strip()
        if value.startswith(("http://", "https://")) and not is_google_goto_url(value):
            return value
        return ""
