"""Stage 1: fast, deterministic, no-network eligibility rules. Cheap enough to run
on every scraped listing before spending any LLM calls. Philosophy: only reject on
a POSITIVE disqualifying signal (explicit senior role, an explicit CGPA cutoff above
the user's, a clearly non-India location). When a signal is simply absent, pass the
job through and let stage 2 (the LLM) judge it — being strict here risks discarding
legitimate fresher roles that just don't use the exact keyword."""

from __future__ import annotations

import re

from ..config import Profile
from ..models import JobListing

# Matches "7.5 CGPA", "CGPA of 8.0", "minimum 8 GPA", "6.5 cgpa" etc.
_CGPA_RE = re.compile(
    r"(?:(?:min(?:imum)?|above|at least)\s*)?(\d(?:\.\d{1,2})?)\s*(?:\+\s*)?(?:cgpa|gpa)"
    r"|(?:cgpa|gpa)\s*(?:of|:|>=|>|above|at least)?\s*(\d(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


def _text_of(job: JobListing) -> str:
    return f"{job.title}\n{job.location}\n{job.description_text}".lower()


def _any_in(terms: list[str], text: str) -> bool:
    return any(t.lower() in text for t in terms)


def _max_cgpa_cutoff(text: str) -> float | None:
    """Return the highest CGPA cutoff mentioned in the JD, or None if none stated."""
    values: list[float] = []
    for m in _CGPA_RE.finditer(text):
        num = m.group(1) or m.group(2)
        try:
            v = float(num)
        except (TypeError, ValueError):
            continue
        # Guard against matching things like years ("2.0 years") — CGPA is 4-10 scale.
        if 4.0 <= v <= 10.0:
            values.append(v)
    return max(values) if values else None


def evaluate(job: JobListing, profile: Profile) -> tuple[bool, list[str]]:
    """Return (passed, reasons). reasons explains the decision either way."""
    text = _text_of(job)
    title_l = job.title.lower()
    reasons: list[str] = []

    # 0) Anti-relevance title blocklist: some non-technical roles (Accountant, Sales,
    # Audit, Concierge, Recruiter...) mention "Python/SQL/data" in their descriptions and
    # would sneak past the relevance gate. If the TITLE names a clearly non-technical
    # function, drop it outright — the title is decisive here.
    blocked = [t for t in profile.exclude_title_keywords if t in title_l]
    if blocked:
        return False, [f"title blocklist: {blocked}"]

    # 1) Seniority. The TITLE is authoritative: an explicit "Senior/Staff/Lead" title is
    # rejected outright — a description that happens to say "mentor junior devs" must not
    # rescue it. Only a description-LEVEL exclude is softened by an include keyword.
    excl_in_title = [t for t in profile.seniority_exclude if t.lower() in title_l]
    if excl_in_title:
        return False, [f"seniority: title says {excl_in_title}"]
    has_exclude = _any_in(profile.seniority_exclude, text)
    has_include = _any_in(profile.seniority_include, text)
    if has_exclude and not has_include:
        matched = [t for t in profile.seniority_exclude if t.lower() in text]
        return False, [f"seniority: excluded by {matched} (in description)"]
    if has_include:
        reasons.append("seniority: matched fresher/entry keyword")
    else:
        reasons.append("seniority: no signal, passed through")

    # 2) CGPA cutoff stated in the JD above the user's → reject.
    cutoff = _max_cgpa_cutoff(text)
    if cutoff is not None and cutoff > profile.cgpa:
        return False, [f"cgpa: JD requires {cutoff} > your {profile.cgpa}"]
    if cutoff is not None:
        reasons.append(f"cgpa: JD cutoff {cutoff} <= your {profile.cgpa}")

    # 3) Location: must mention an allowed location, or say nothing specific.
    if profile.locations_allow:
        if _any_in(profile.locations_allow, text):
            reasons.append("location: allowed location matched")
        else:
            # No allowed location string anywhere — treat as out of scope.
            return False, ["location: no India/remote/allowed location matched"]

    # 4) Relevance gate: the job must show a tech/role signal. Big ATS boards (Stripe,
    # Datadog, ...) post every role — sales, legal, finance, support — and steps 1-3
    # alone would let a non-senior India-based "Senior Counsel" or "Field Ops Manager"
    # through. Require at least one branch OR role keyword in the title/description.
    # The TITLE match is the strong signal; a description-only match is weaker but kept
    # (stage 2 can still down-rank it).
    if profile.require_relevance:
        relevance_terms = profile.branch_keywords + profile.role_keywords
        if relevance_terms:
            if _any_in(relevance_terms, title_l):
                reasons.append("relevance: tech/role keyword in title")
            elif _any_in(relevance_terms, text):
                reasons.append("relevance: tech/role keyword in description only")
            else:
                return False, ["relevance: no tech/role keyword — likely non-technical role"]

    return True, reasons


def run_stage1(jobs: list[JobListing], profile: Profile) -> list[JobListing]:
    """Annotate every job and return only those that pass."""
    survivors: list[JobListing] = []
    for job in jobs:
        passed, reasons = evaluate(job, profile)
        job.passed_stage1 = passed
        job.stage1_reasons = reasons
        if passed:
            survivors.append(job)
    return survivors
