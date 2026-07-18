"""Internshala scraper.

Listing pages are server-rendered, so requests + BeautifulSoup works — no browser.
BUT Internshala's robots.txt disallows every query-string URL ('/*?*'), '/api/',
and search/details paths. So we must NOT paginate via ?page=N or hit /ajax/ calls.
A robots-respecting build hits only the first, path-based category listing page per
target and refreshes daily. Card CSS classes change periodically, so parsing is
defensive and skips (rather than crashes on) any card it can't read."""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from ..models import JobListing
from .base import SourceScraper

logger = logging.getLogger("jobdigest")

BASE = "https://internshala.com"

# Path-based category listings only (no query strings). Tweak to taste.
CATEGORY_PATHS = [
    "/jobs/fresher-jobs/",
    "/jobs/work-from-home-jobs/",
    "/jobs/computer-science-jobs/",
    "/jobs/software-development-jobs/",
    "/jobs/data-science-jobs/",
    "/jobs/machine-learning-jobs/",
]


class InternshalaScraper(SourceScraper):
    name = "internshala"

    def fetch(self) -> list[JobListing]:
        out: list[JobListing] = []
        for path in CATEGORY_PATHS:
            out.extend(self._fetch_category(path))
            self.polite_pause(base=3.0)
        # dedup within internshala by url before returning
        seen: set[str] = set()
        uniq: list[JobListing] = []
        for j in out:
            if j.url in seen:
                continue
            seen.add(j.url)
            uniq.append(j)
        logger.info("internshala: %d jobs", len(uniq))
        return uniq

    def _fetch_category(self, path: str) -> list[JobListing]:
        url = BASE + path
        try:
            resp = self.session.get(url, timeout=20)
        except Exception as e:
            logger.warning("internshala %s: request failed: %s", path, e)
            return []
        if resp.status_code != 200:
            logger.warning("internshala %s: HTTP %s", path, resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        # Cards have historically been .individual_internship (jobs reuse the class).
        cards = soup.select(".individual_internship") or soup.select("[data-job-id]")
        results: list[JobListing] = []
        for card in cards:
            job = self._parse_card(card)
            if job:
                results.append(job)
        return results

    def _parse_card(self, card) -> JobListing | None:
        try:
            title_el = (
                card.select_one(".job-internship-name")
                or card.select_one(".profile")
                or card.select_one("h3 a")
                or card.select_one("h3")
            )
            company_el = (
                card.select_one(".company-name")
                or card.select_one(".company_name")
                or card.select_one(".company")
            )
            link_el = card.select_one("a[href]")
            loc_el = card.select_one(".locations") or card.select_one(".location_link")
            # .about_job carries a real one-line summary and .job_skills the skill
            # tags — both sit on the same listing page we already fetched, so this
            # is "free" (no extra request, still robots.txt-compliant) but was being
            # left unused, leaving stage-1 filtering and scam-pattern checks blind
            # to anything beyond the bare title.
            about_el = card.select_one(".about_job")
            skills_el = card.select_one(".job_skills")

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            href = link_el["href"] if link_el else ""
            url = href if href.startswith("http") else BASE + href
            location = loc_el.get_text(" ", strip=True) if loc_el else ""
            about = about_el.get_text(" ", strip=True) if about_el else ""
            skills = skills_el.get_text(", ", strip=True) if skills_el else ""

            if not title:
                return None
            desc_parts = [title, company, location, about, skills]
            return JobListing(
                source=self.name,
                company=company or "—",
                title=title,
                location=location,
                url=url,
                description_text=" ".join(p for p in desc_parts if p),
                job_id=card.get("data-job-id") or card.get("internshipid"),
            )
        except Exception as e:
            logger.debug("internshala: skipped a card: %s", e)
            return None
