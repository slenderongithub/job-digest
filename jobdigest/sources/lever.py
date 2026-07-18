"""Lever postings API.

Endpoint: GET https://api.lever.co/v0/postings/{slug}?mode=json
Returns a flat JSON array of all live postings (no pagination). `descriptionPlain`
is already plain text; `createdAt` is epoch milliseconds.

Gotchas verified July 2026:
- Slugs are CASE-SENSITIVE (e.g. "Sprinto", "Onehouse" resolve; lowercase 404s) —
  store exact casing in companies.yaml.
- EU-hosted accounts serve from api.eu.lever.co, not api.lever.co. If the global
  host 404s, we retry the EU host before giving up.
- A slug that resolves but returns [] is a DEAD board (company left Lever), not
  "no matches" — logged distinctly."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..models import JobListing
from .base import SourceScraper

logger = logging.getLogger("jobdigest")

HOSTS = ("https://api.lever.co", "https://api.eu.lever.co")
API = "{host}/v0/postings/{slug}?mode=json"


def _epoch_ms_to_date(ms) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


class LeverScraper(SourceScraper):
    name = "lever"

    def __init__(self, profile, slugs: list[str], session=None):
        super().__init__(profile, session)
        self.slugs = slugs

    def fetch(self) -> list[JobListing]:
        out: list[JobListing] = []
        for slug in self.slugs:
            out.extend(self._fetch_one(slug))
            self.polite_pause(base=1.0)
        return out

    def _get_postings(self, slug: str):
        """Try the global host, then the EU host on 404. Returns the parsed list or None."""
        for host in HOSTS:
            url = API.format(host=host, slug=slug)
            try:
                resp = self.session.get(url, timeout=20)
            except Exception as e:
                logger.warning("lever %s (%s): request failed: %s", slug, host, e)
                continue
            if resp.status_code == 404:
                continue  # try next host (EU) before concluding not-on-Lever
            if resp.status_code != 200:
                logger.warning("lever %s (%s): HTTP %s", slug, host, resp.status_code)
                continue
            try:
                data = resp.json()
            except ValueError:
                logger.warning("lever %s (%s): non-JSON response", slug, host)
                continue
            if isinstance(data, list):
                return data
            logger.warning("lever %s (%s): unexpected shape", slug, host)
        return None

    def _fetch_one(self, slug: str) -> list[JobListing]:
        postings = self._get_postings(slug)
        if postings is None:
            logger.warning("lever %s: 404 on both hosts (bad/stale/case-wrong slug?)", slug)
            return []
        if len(postings) == 0:
            logger.info("lever %s: resolved but empty (dead board — left Lever?)", slug)
            return []

        results: list[JobListing] = []
        for p in postings:
            cats = p.get("categories") or {}
            results.append(
                JobListing(
                    source=self.name,
                    company=slug,
                    title=p.get("text", "").strip(),
                    location=(cats.get("location") or "").strip(),
                    url=p.get("hostedUrl", ""),
                    description_raw=p.get("description", "") or "",
                    description_text=p.get("descriptionPlain", "") or "",
                    posted_date=_epoch_ms_to_date(p.get("createdAt")),
                    job_id=str(p.get("id")) if p.get("id") else None,
                )
            )
        logger.info("lever %s: %d jobs", slug, len(results))
        return results
