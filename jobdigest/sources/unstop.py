"""Unstop scraper via its public JSON API.

The HTML surface is a Next.js SPA shell with no listing data, but there's an
undocumented public JSON endpoint (robots-ALLOWED under /api/public/*):

  GET https://unstop.com/api/public/opportunity/search-result
      ?opportunity=jobs&page=1&per_page=15&oppstatus=open

Response: {"data": {"data": [ ...opportunities... ], "total": N, ...}}. Being
undocumented, field names vary — we parse defensively across likely keys."""

from __future__ import annotations

import logging

from ..models import JobListing
from .base import SourceScraper

logger = logging.getLogger("jobdigest")

BASE = "https://unstop.com/api/public/opportunity/search-result"


class UnstopScraper(SourceScraper):
    name = "unstop"

    def fetch(self) -> list[JobListing]:
        out: list[JobListing] = []
        per_page = 15
        for page in range(1, self.profile.max_pages_per_query + 1):
            params = {
                "opportunity": "jobs",
                "page": page,
                "per_page": per_page,
                "oppstatus": "open",
            }
            items = self._fetch_page(params)
            if not items:
                break
            out.extend(self._parse(it) for it in items)
            if len(items) < per_page:
                break
            self.polite_pause(base=2.0)
        # drop any that failed to parse into a usable listing
        out = [j for j in out if j and j.title]
        logger.info("unstop: %d jobs", len(out))
        return out

    def _fetch_page(self, params: dict) -> list:
        try:
            resp = self.session.get(BASE, params=params, timeout=20,
                                    headers={"Accept": "application/json"})
        except Exception as e:
            logger.warning("unstop: request failed: %s", e)
            return []
        if resp.status_code != 200:
            logger.warning("unstop: HTTP %s", resp.status_code)
            return []
        try:
            payload = resp.json()
        except ValueError:
            logger.warning("unstop: non-JSON response")
            return []
        data = payload.get("data", payload)
        # endpoint nests the list one more level: data.data[]
        if isinstance(data, dict):
            return data.get("data", []) or []
        return data if isinstance(data, list) else []

    def _parse(self, it: dict) -> JobListing | None:
        if not isinstance(it, dict):
            return None
        title = it.get("title") or it.get("name") or ""
        # organisation name lives under a few possible keys
        org = it.get("organisation") or it.get("organization") or {}
        company = ""
        if isinstance(org, dict):
            company = org.get("name") or org.get("legal_name") or ""
        company = company or it.get("company_name") or "Unstop"
        # public url
        seo = it.get("seo_url") or it.get("public_url") or it.get("url") or ""
        if seo and not seo.startswith("http"):
            seo = "https://unstop.com/" + seo.lstrip("/")
        # location: jobs may be remote or list regions
        loc = ""
        regions = it.get("region") or it.get("regions") or it.get("job_detail") or ""
        if isinstance(regions, list):
            loc = ", ".join(str(r.get("name", r) if isinstance(r, dict) else r) for r in regions)
        elif isinstance(regions, str):
            loc = regions
        if not loc and it.get("remote"):
            loc = "Remote"

        # description bits vary; stitch what we can for keyword matching
        desc = " ".join(
            str(it.get(k, ""))
            for k in ("subtitle", "details", "description", "eligibility")
            if it.get(k)
        )
        return JobListing(
            source=self.name,
            company=str(company).strip(),
            title=str(title).strip(),
            location=str(loc).strip(),
            url=seo,
            description_text=desc.strip(),
            job_id=str(it.get("id")) if it.get("id") else None,
        )
