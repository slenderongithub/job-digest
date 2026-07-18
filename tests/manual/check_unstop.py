#!/usr/bin/env python3
"""Manual smoke test: hit Unstop's public JSON API and print jobs.

  python tests/manual/check_unstop.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jobdigest.config import Profile
from jobdigest.sources.unstop import UnstopScraper


def main():
    profile = Profile(cgpa=7.65, max_pages_per_query=2)
    jobs = UnstopScraper(profile).fetch()
    print(f"\n{len(jobs)} jobs from unstop\n" + "-" * 50)
    for j in jobs[:15]:
        print(f"- {j.title}  |  {j.company}  |  {j.location}\n  {j.url}")
    if not jobs:
        print("No jobs — the public API shape may have changed; inspect the JSON.")


if __name__ == "__main__":
    main()
