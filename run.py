#!/usr/bin/env python3
"""Entrypoint / orchestrator for the job digest.

Pipeline: load config -> run enabled scrapers -> collect -> dedup vs seen_jobs.json
-> stage-1 rules -> scam-pattern check -> stage-2 Gemini ranking (survivors only)
-> record seen -> write HTML digest. Idempotent per day (date-stamp guard) so
launchd firing more than once — or a manual run — produces at most one digest per
day unless --force is given.

Usage:
  python run.py                 # normal daily run (skips if already ran today)
  python run.py --force         # run even if already ran today
  python run.py --no-gemini     # skip LLM ranking (rules only)
  python run.py --source greenhouse --source lever   # limit to specific sources
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timezone

from jobdigest import config as cfg
from jobdigest.dedup import SeenStore, filter_new
from jobdigest.digest import write_digest
from jobdigest.filters import scam_check, stage1_rules, stage2_gemini
from jobdigest.logging_conf import setup_logging

LAST_RUN_FILE = cfg.DATA_DIR / "last_run.txt"


def build_scrapers(profile, companies, only: list[str] | None):
    """Instantiate the enabled scrapers. Imports are local so a missing optional
    dependency (e.g. playwright for naukri) can't break unrelated sources."""
    enabled = [s for s in profile.enabled_sources if not only or s in only]
    scrapers = []
    for name in enabled:
        if name == "greenhouse":
            from jobdigest.sources.greenhouse import GreenhouseScraper
            scrapers.append(GreenhouseScraper(profile, companies.get("greenhouse", [])))
        elif name == "lever":
            from jobdigest.sources.lever import LeverScraper
            scrapers.append(LeverScraper(profile, companies.get("lever", [])))
        elif name == "unstop":
            from jobdigest.sources.unstop import UnstopScraper
            scrapers.append(UnstopScraper(profile))
        elif name == "internshala":
            from jobdigest.sources.internshala import InternshalaScraper
            scrapers.append(InternshalaScraper(profile))
        elif name == "linkedin":
            from jobdigest.sources.linkedin import LinkedInScraper
            scrapers.append(LinkedInScraper(profile))
        elif name == "naukri":
            from jobdigest.sources.naukri import NaukriScraper
            scrapers.append(NaukriScraper(profile))
        else:
            logging.getLogger("jobdigest").warning("unknown source in config: %s", name)
    return scrapers


def already_ran_today() -> bool:
    if LAST_RUN_FILE.exists():
        return LAST_RUN_FILE.read_text(encoding="utf-8").strip() == date.today().isoformat()
    return False


def stamp_run() -> None:
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.write_text(date.today().isoformat(), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Personal job-digest aggregator")
    ap.add_argument("--force", action="store_true", help="run even if already ran today")
    ap.add_argument("--no-gemini", action="store_true", help="skip LLM ranking")
    ap.add_argument("--source", action="append", help="limit to these sources (repeatable)")
    args = ap.parse_args()

    log = setup_logging(cfg.DATA_DIR)

    if already_ran_today() and not args.force:
        log.info("already ran today (%s) — use --force to re-run. Exiting.", date.today())
        return 0

    cfg.load_env()
    profile = cfg.load_profile()
    companies = cfg.load_companies()
    if args.no_gemini:
        profile.gemini_enabled = False

    scrapers = build_scrapers(profile, companies, args.source)
    log.info("running %d sources: %s", len(scrapers), [s.name for s in scrapers])

    # --- scrape (one dead source must never kill the run) ---
    all_jobs = []
    per_source: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()
    for sc in scrapers:
        try:
            jobs = sc.fetch()
        except Exception as e:
            log.warning("source %s crashed: %s", sc.name, e)
            jobs = []
        for j in jobs:
            j.fetched_at = now
        per_source[sc.name] = len(jobs)
        all_jobs.extend(jobs)
    log.info("scraped %d total (%s)", len(all_jobs), per_source)

    # --- dedup vs prior runs ---
    today = date.today().isoformat()
    store = SeenStore.load(cfg.DATA_DIR / "seen_jobs.json")
    pruned = store.prune(today)
    new_jobs = filter_new(all_jobs, store)
    log.info("new since last run: %d (pruned %d stale seen-entries)", len(new_jobs), pruned)

    # --- stage 1 rules ---
    survivors = stage1_rules.run_stage1(new_jobs, profile)
    log.info("stage 1 survivors: %d / %d", len(survivors), len(new_jobs))

    # --- scam-pattern check (annotates, never filters out) ---
    scam_check.run_scam_check(survivors)
    scam_flagged = sum(1 for j in survivors if (j.scam_score or 0) >= 20)
    log.info("scam check: %d/%d flagged as suspicious", scam_flagged, len(survivors))

    # --- stage 2 gemini ranking (survivors only) ---
    stage2_gemini.rank(survivors, profile, cfg.get_gemini_api_key())

    # --- record scraped jobs as seen, then persist. New ones so we don't
    # resurface them tomorrow; repeats so their last_seen stays fresh and a
    # still-open listing isn't pruned (and later re-surfaced) while it's active.
    # Exception: stage-1 survivors that never got a Gemini score (quota ran out
    # before reaching them) must NOT be marked seen — otherwise they vanish
    # forever instead of getting a chance to be scored on a future run. ---
    unscored_survivor_keys = {
        j.dedup_key() for j in survivors if j.fit_score is None
    }
    for j in all_jobs:
        if j.dedup_key() in unscored_survivor_keys:
            continue
        store.record(j, today)
    store.save()

    # --- digest ---
    stats = {
        "new": len(new_jobs),
        "eligible": len(survivors),
        "scored": sum(1 for j in survivors if j.fit_score is not None),
        "flagged": scam_flagged,
        **{f"src:{k}": v for k, v in per_source.items()},
    }
    dated_path = cfg.DIGEST_DIR / f"{today}.html"
    if not survivors and dated_path.exists() and dated_path.stat().st_size > 0:
        log.warning(
            "0 survivors this run but a digest for today already exists — "
            "leaving it in place instead of overwriting with an empty one"
        )
        path = dated_path
    else:
        path = write_digest(survivors, stats, cfg.DIGEST_DIR)
    stamp_run()
    log.info("digest written: %s", path)
    print(f"Done. Open {path} in your browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
