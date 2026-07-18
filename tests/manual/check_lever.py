#!/usr/bin/env python3
"""Manual smoke test: hit a real Lever board and print what comes back.

  python tests/manual/check_lever.py --company Sprinto
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jobdigest.config import Profile
from jobdigest.sources.lever import LeverScraper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="leverdemo", help="Lever slug (CASE-SENSITIVE)")
    args = ap.parse_args()

    profile = Profile(cgpa=7.65)
    jobs = LeverScraper(profile, [args.company]).fetch()
    print(f"\n{len(jobs)} jobs from lever/{args.company}\n" + "-" * 50)
    for j in jobs[:15]:
        print(f"- {j.title}  |  {j.location}\n  {j.url}")
    if not jobs:
        print("No jobs — check casing, try EU host, or the board may be empty/dead.")


if __name__ == "__main__":
    main()
