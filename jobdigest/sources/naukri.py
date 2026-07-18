"""Naukri scraper — BEST-EFFORT, the fragile one.

Reality (verified July 2026): Naukri's internal /jobapi search requires a rotating
signed 'nkparam' header generated inside obfuscated JS (a plain request gets 403),
and the search results page is JS-rendered (requests+BS4 returns an empty shell).
So the only workable path is a headless browser that renders the page. This also
sits in tension with Naukri's Terms of Use, so keep volume minimal.

Because of all that, this module:
- uses Playwright (headless Chromium) and degrades gracefully (logs + returns [])
  if Playwright or its browser isn't installed — the rest of the tool is unaffected;
- renders one search page per keyword and reads a couple of cards to confirm the
  selectors still work, otherwise logs a 'selectors may have changed' warning.

If this proves too flaky, the ToS-friendlier alternative is Naukri's own RSS/email
job alerts (set them up in your Naukri account) — noted in the README."""

from __future__ import annotations

import logging
import re

from ..models import JobListing
from .base import SourceScraper

logger = logging.getLogger("jobdigest")


def _slug(keyword: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")


class NaukriScraper(SourceScraper):
    name = "naukri"

    def fetch(self) -> list[JobListing]:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            logger.warning(
                "naukri: playwright not installed — skipping. "
                "`pip install playwright && playwright install chromium` to enable."
            )
            return []

        out: list[JobListing] = []
        keywords = self.profile.search_keywords or ["software engineer"]
        try:
            out = self._scrape(keywords)
        except Exception as e:
            logger.warning("naukri: scrape failed (%s) — skipping", e)
            return []
        # dedup within naukri by url
        seen: set[str] = set()
        uniq = []
        for j in out:
            if j.url and j.url not in seen:
                seen.add(j.url)
                uniq.append(j)
        logger.info("naukri: %d jobs", len(uniq))
        return uniq

    def _scrape(self, keywords: list[str]) -> list[JobListing]:
        from playwright.sync_api import sync_playwright

        results: list[JobListing] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=self.session.headers.get("User-Agent"),
                locale="en-US",
                viewport={"width": 1366, "height": 900},
            )
            page = ctx.new_page()
            for kw in keywords:
                url = f"https://www.naukri.com/{_slug(kw)}-jobs"
                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_selector(
                        ".srp-jobtuple-wrapper, article.jobTuple", timeout=15000
                    )
                except Exception as e:
                    logger.warning("naukri '%s': cards didn't render (%s) — "
                                   "selectors may have changed", kw, e)
                    continue
                cards = page.query_selector_all(".srp-jobtuple-wrapper, article.jobTuple")
                for card in cards[: self.profile.max_pages_per_query * 20]:
                    job = self._parse_card(card, kw)
                    if job:
                        results.append(job)
            browser.close()
        return results

    def _parse_card(self, card, keyword: str) -> JobListing | None:
        try:
            title_el = card.query_selector("a.title") or card.query_selector(".title")
            comp_el = card.query_selector("a.comp-name") or card.query_selector(".comp-name")
            loc_el = card.query_selector(".locWdth") or card.query_selector(".loc")
            desc_el = card.query_selector(".job-desc") or card.query_selector(".job-description")

            if not title_el:
                return None
            title = title_el.inner_text().strip()
            url = title_el.get_attribute("href") or ""
            company = comp_el.inner_text().strip() if comp_el else "—"
            location = loc_el.inner_text().strip() if loc_el else ""
            desc = desc_el.inner_text().strip() if desc_el else ""
            if not title:
                return None
            return JobListing(
                source=self.name,
                company=company,
                title=title,
                location=location,
                url=url,
                description_text=f"{title} {desc} {location}",
            )
        except Exception as e:
            logger.debug("naukri: skipped a card: %s", e)
            return None
