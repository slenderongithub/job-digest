"""Scam-pattern detection on stage-1 survivors.

Runs cheap, local regex pattern-matching against well-known job-scam red flags —
fee/deposit requests, "no interview / instant offer" framing, WhatsApp/Telegram-only
contact, personal-email-only contact, and classic WFH/data-entry scam phrasing
("earn ₹X per day", "copy paste work").

Deliberately does NOT filter jobs out — false positives would silently hide real
jobs (e.g. a legit gig-platform listing mentioning "WhatsApp" once in passing).
Instead it annotates JobListing.scam_score/scam_flags so the digest can render a
visible warning and let the user make the final call. This is a heuristic, not a
guarantee — always independently verify a company before paying it anything."""

from __future__ import annotations

import re

from ..models import JobListing

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com",
    "rediffmail.com", "icloud.com", "protonmail.com", "aol.com",
}

_EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)", re.IGNORECASE)

# (pattern, severity, human-readable label). Score is capped at 100.
# HIGH (30-40): direct financial red flags — the strongest, most reliable signal.
# MEDIUM (15-25): informal contact channels / classic scam framing — suspicious but
#   can occasionally appear in legit gig-economy or small-startup postings.
_PATTERNS: list[tuple[str, int, str]] = [
    # --- HIGH: any request for money from the candidate ---
    (r"\bregistration\s+fee\b", 40, "asks for a registration fee"),
    (r"\bsecurity\s+deposit\b", 40, "asks for a security deposit"),
    (r"\brefundable\s+deposit\b", 40, "asks for a 'refundable' deposit"),
    (r"\bprocessing\s+fee\b", 40, "asks for a processing fee"),
    (r"\btraining\s+fee\b", 40, "asks for a training fee"),
    (r"\bjoining\s+fee\b", 40, "asks for a joining fee"),
    (r"\bactivation\s+fee\b", 40, "asks for an activation fee"),
    (r"\bcaution\s+money\b", 40, "asks for 'caution money'"),
    (r"\bpay(?:ment)?\s+(?:before|prior to)\s+(?:joining|onboarding)\b", 40,
     "asks for payment before joining"),
    (r"\badvance\s+payment\b", 35, "asks for an advance payment"),
    (r"\bpurchase\s+(?:a |the )?(?:kit|starter kit|study material)\b", 35,
     "requires buying a kit/materials first"),
    # --- HIGH: too-good-to-be-true instant hiring ---
    (r"\bno\s+interview\s+required\b", 30, "claims no interview required"),
    (r"\binstant\s+(?:offer|joining)\b", 30, "claims instant offer/joining"),
    (r"\bwithout\s+any\s+interview\b", 30, "claims hiring without any interview"),
    (r"\bselection\s+is\s+100%\s*guaranteed\b", 30, "claims guaranteed selection"),
    # --- MEDIUM: informal-only contact channels ---
    # One combined pattern (not two) so "contact us on WhatsApp only" isn't
    # double-counted by two separately-firing rules.
    (r"\bwhatsapp\b[^.]{0,25}\b(?:only|number|group)\b|\bcontact\b[^.]{0,25}\bwhatsapp\b",
     20, "directs contact via WhatsApp"),
    (r"\btelegram\b[^.]{0,20}\b(?:contact|join|group)\b", 20,
     "directs contact via Telegram"),
    (r"\bdm\s+(?:for|to)\s+(?:details|apply)\b", 15,
     "asks to DM for details instead of a formal process"),
    # --- MEDIUM: classic WFH/data-entry scam framing ---
    (r"\bearn\s*(?:up to\s*)?(?:rs\.?|inr|₹)\s*[\d,]+[^.]{0,15}\b(?:per day|daily|/day)\b",
     25, "'earn ₹X per day' framing typical of WFH scams"),
    (r"\bno\s+experience\b[^.]{0,25}\bhigh\s+(?:salary|pay|stipend)\b", 20,
     "no-experience-needed + high-pay framing"),
    (r"\bcopy\s+paste\s+(?:job|work)\b", 25, "'copy paste work' (classic scam phrasing)"),
    (r"\bhome\s+based\s+typing\s+(?:job|work)\b", 25, "'home based typing job' scam phrasing"),
]


def _find_personal_email_flag(text: str) -> str | None:
    for m in _EMAIL_RE.finditer(text or ""):
        domain = m.group(1).lower()
        if domain in PERSONAL_EMAIL_DOMAINS:
            return f"contact email uses a personal domain ({domain}), not a company one"
    return None


def evaluate(job: JobListing) -> tuple[int, list[str]]:
    """Return (scam_score 0-100, flags). Pure function, does not mutate job."""
    text = f"{job.title}\n{job.description_text}"
    score = 0
    flags: list[str] = []
    for pattern, severity, label in _PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            score += severity
            flags.append(label)

    email_flag = _find_personal_email_flag(job.description_text)
    if email_flag:
        score += 15
        flags.append(email_flag)

    return min(score, 100), flags


def run_scam_check(jobs: list[JobListing]) -> list[JobListing]:
    """Annotate every job in place with scam_score/scam_flags. Returns the same list."""
    for job in jobs:
        score, flags = evaluate(job)
        job.scam_score = score
        job.scam_flags = flags
    return jobs
