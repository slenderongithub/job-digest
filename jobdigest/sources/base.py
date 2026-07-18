"""Base class for all scrapers: a shared retrying HTTP session, a polite jittered
delay helper, and a common HTML-to-text utility."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("jobdigest")

# A realistic desktop UA. Not evasion — just avoids the default python-requests UA
# that some sites reject outright.
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Deterministic jitter sequence (no Math.random needed) so delays vary but stay
# reproducible; index into it per request.
_JITTER = [0.0, 0.7, 1.3, 0.4, 1.1, 0.9, 0.2, 1.5, 0.6, 1.0]


def build_session(timeout: int = 20) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "en-US,en;q=0.9"})
    return session


def html_to_text(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)


class SourceScraper(ABC):
    name: str = "base"

    def __init__(self, profile, session: requests.Session | None = None):
        self.profile = profile
        self.session = session or build_session()
        self._req_count = 0

    def polite_pause(self, base: float = 2.0) -> None:
        """Sleep base + a rotating jitter between requests to stay low-volume."""
        jitter = _JITTER[self._req_count % len(_JITTER)]
        self._req_count += 1
        time.sleep(base + jitter)

    @abstractmethod
    def fetch(self) -> list:
        """Return a list[JobListing]. Implementations must never raise on a single
        bad response — log and continue so one dead source can't kill the run."""
        ...
