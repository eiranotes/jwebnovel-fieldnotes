from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(slots=True)
class HttpResponse:
    url: str
    status: int
    text: str

    def json(self):
        return json.loads(self.text)


class PoliteHttpClient:
    def __init__(self, *, user_agent: str, delay_seconds: float, timeout_seconds: float):
        self.user_agent = user_agent
        self.delay_seconds = max(0.0, delay_seconds)
        self.timeout_seconds = timeout_seconds
        self._last_request_at = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def get(self, url: str, params: dict | None = None) -> HttpResponse:
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        self._wait()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "ja,en;q=0.7",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as res:
            payload = res.read()
            charset = res.headers.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            status = int(getattr(res, "status", 200))
            final_url = res.geturl()
        self._last_request_at = time.monotonic()
        return HttpResponse(url=final_url, status=status, text=text)
