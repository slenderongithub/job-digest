#!/usr/bin/env python3
"""Manual smoke test: hit a real Greenhouse board and print what comes back.

  python tests/manual/check_greenhouse.py --company stripe
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jobdigest.config import Profile
from jobdigest.sources.greenhouse import GreenhouseScraper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="stripe", help="Greenhouse board slug")
    args = ap.parse_args()

    profile = Profile(cgpa=7.65)
    jobs = GreenhouseScraper(profile, [args.company]).fetch()
    print(f"\n{len(jobs)} jobs from greenhouse/{args.company}\n" + "-" * 50)
    for j in jobs[:15]:
        print(f"- {j.title}  |  {j.location}\n  {j.url}")
    if not jobs:
        print("No jobs — slug may be wrong/stale, or the company left Greenhouse.")


if __name__ == "__main__":
    main()
