"""LinkedIn scraper — UNAUTHENTICATED public 'jobs-guest' endpoint only.

No login, no account, no cookies (a dummy account was rejected because LinkedIn's
multi-account IP-linking could drag down the user's real profile). This uses the
public guest endpoint that powers the "see more jobs" scroll on logged-out job
search:

  GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
      ?keywords=<enc>&location=<enc>&start=<0,25,50,...>

IMPORTANT: the response is an HTML FRAGMENT (a <ul> of <li> job cards), NOT JSON.
Parse with CSS selectors. 'start' steps by 25 with a ~1000-result ceiling. A single
IP typically gets HTTP 429 after ~10 pages/session, so we keep volume low, add
jittered delays, and stop on 429 or an empty page. Class names get tweaked
periodically — parsing is isolated here and skips unreadable cards.

ToS note: LinkedIn's Terms prohibit automated access; this stays personal, local,
low-volume, unauthenticated, and never redistributes data. See README."""

from __future__ import annotations

import logging
import urllib.parse

from bs4 import BeautifulSoup

from ..models import JobListing
from .base import SourceScraper

logger = logging.getLogger("jobdigest")

ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
# f_TPR=r604800 → postings from the last 7 days (keeps volume + relevance sane).
TIME_FILTER = "r604800"
RESULT_CEILING = 1000


class LinkedInScraper(SourceScraper):
    name = "linkedin"

    def fetch(self) -> list[JobListing]:
        out: list[JobListing] = []
        keywords = self.profile.search_keywords or ["software engineer"]
        locations = self.profile.search_locations or ["India"]
        for kw in keywords:
            for loc in locations:
                out.extend(self._search(kw, loc))
        # dedup within linkedin by url
        seen: set[str] = set()
        uniq = []
        for j in out:
            if j.url in seen:
                continue
            seen.add(j.url)
            uniq.append(j)
        logger.info("linkedin: %d jobs", len(uniq))
        return uniq

    def _search(self, keywords: str, location: str) -> list[JobListing]:
        results: list[JobListing] = []
        pages = min(self.profile.max_pages_per_query, RESULT_CEILING // 25)
        for page in range(pages):
            start = page * 25
            cards = self._fetch_page(keywords, location, start)
            if cards is None:  # 429 / hard error → stop this query entirely
                logger.warning("linkedin: throttled at start=%d for '%s' — stopping query",
                               start, keywords)
                break
            if not cards:
                break
            results.extend(cards)
            self.polite_pause(base=3.0)
        return results

    def _fetch_page(self, keywords: str, location: str, start: int):
        params = {
            "keywords": keywords,
            "location": location,
            "f_TPR": TIME_FILTER,
            "start": start,
        }
        url = ENDPOINT + "?" + urllib.parse.urlencode(params)
        try:
            resp = self.session.get(url, timeout=20)
        except Exception as e:
            logger.warning("linkedin: request failed: %s", e)
            return None
        if resp.status_code == 429:
            return None
        if resp.status_code != 200:
            logger.warning("linkedin: HTTP %s", resp.status_code)
            return None
        return self._parse(resp.text)

    def _parse(self, html: str) -> list[JobListing]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("li")
        out: list[JobListing] = []
        for li in cards:
            job = self._parse_card(li)
            if job:
                out.append(job)
        return out

    def _parse_card(self, li) -> JobListing | None:
        try:
            title_el = li.select_one(".base-search-card__title")
            company_el = li.select_one(".base-search-card__subtitle")
            loc_el = li.select_one(".job-search-card__location")
            link_el = li.select_one("a.base-card__full-link") or li.select_one("a[href]")
            time_el = li.select_one("time")

            if not title_el or not link_el:
                return None
            url = link_el.get("href", "").split("?")[0]
            return JobListing(
                source=self.name,
                company=company_el.get_text(strip=True) if company_el else "—",
                title=title_el.get_text(strip=True),
                location=loc_el.get_text(strip=True) if loc_el else "",
                url=url,
                description_text=title_el.get_text(strip=True),
                posted_date=(time_el.get("datetime") if time_el else None),
            )
        except Exception as e:
            logger.debug("linkedin: skipped a card: %s", e)
            return None
