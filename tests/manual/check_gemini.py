#!/usr/bin/env python3
"""Manual smoke test: confirm the Gemini key + SDK + model work end to end by
scoring one obviously-matching and one obviously-mismatched job.

  export GEMINI_API_KEY=...   (or put it in .env)
  python tests/manual/check_gemini.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jobdigest import config as cfg
from jobdigest.config import Profile
from jobdigest.filters import stage2_gemini
from jobdigest.models import JobListing

RESUME = (
    "Final-year CSE (AI/ML) student. Python, PyTorch, scikit-learn, SQL. "
    "Built ML projects: image classification, an NLP sentiment app. Seeking "
    "entry-level ML/data/software roles."
)


def main():
    cfg.load_env()
    key = cfg.get_gemini_api_key()
    if not key:
        print("No GEMINI_API_KEY found (env or .env). Aborting.")
        return

    profile = Profile(cgpa=7.65, resume_text=RESUME, gemini_model="gemini-flash-lite-latest")
    jobs = [
        JobListing("test", "AcmeAI", "Machine Learning Engineer (Fresher)", "Bangalore",
                   "https://x", description_text="Entry-level ML role. Python, PyTorch. New grads welcome."),
        JobListing("test", "OldCorp", "Senior SAP ABAP Consultant", "Pune",
                   "https://y", description_text="8+ years SAP ABAP. Senior enterprise consultant."),
    ]
    stage2_gemini.rank(jobs, profile, key)
    print("-" * 50)
    for j in jobs:
        print(f"{j.title}\n  score={j.fit_score}  rationale={j.rationale}\n")
    print("Expect: the ML fresher role scores clearly higher than the senior SAP role.")


if __name__ == "__main__":
    main()
