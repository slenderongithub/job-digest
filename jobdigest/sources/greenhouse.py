"""Greenhouse public job board API.

Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Returns every open job for a company in a single response (no pagination). The
`content` field is HTML-entity-encoded HTML, so it needs unescaping before parsing."""

from __future__ import annotations

import html
import logging

from ..models import JobListing
from .base import SourceScraper, html_to_text

logger = logging.getLogger("jobdigest")

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


class GreenhouseScraper(SourceScraper):
    name = "greenhouse"

    def __init__(self, profile, slugs: list[str], session=None):
        super().__init__(profile, session)
        self.slugs = slugs

    def fetch(self) -> list[JobListing]:
        out: list[JobListing] = []
        for slug in self.slugs:
            out.extend(self._fetch_one(slug))
            self.polite_pause(base=1.0)
        return out

    def _fetch_one(self, slug: str) -> list[JobListing]:
        url = API.format(slug=slug)
        try:
            resp = self.session.get(url, timeout=20)
        except Exception as e:  # network error — skip this company, keep going
            logger.warning("greenhouse %s: request failed: %s", slug, e)
            return []
        if resp.status_code == 404:
            logger.warning("greenhouse %s: 404 (bad/stale slug?)", slug)
            return []
        if resp.status_code != 200:
            logger.warning("greenhouse %s: HTTP %s", slug, resp.status_code)
            return []
        try:
            jobs = resp.json().get("jobs", [])
        except ValueError:
            logger.warning("greenhouse %s: non-JSON response", slug)
            return []

        results: list[JobListing] = []
        for j in jobs:
            content_html = html.unescape(j.get("content", "") or "")
            results.append(
                JobListing(
                    source=self.name,
                    company=slug,
                    title=j.get("title", "").strip(),
                    location=(j.get("location") or {}).get("name", "").strip(),
                    url=j.get("absolute_url", ""),
                    description_raw=content_html,
                    description_text=html_to_text(content_html),
                    posted_date=(j.get("updated_at") or "")[:10] or None,
                    job_id=str(j.get("id")) if j.get("id") is not None else None,
                )
            )
        logger.info("greenhouse %s: %d jobs", slug, len(results))
        return results
