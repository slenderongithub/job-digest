"""Stage 2: LLM fit-scoring of stage-1 survivors against the user's skills profile,
via the Google Gemini free tier. Uses the current unified `google-genai` SDK (the
old `google-generativeai` package is deprecated and Gemini 1.5 models 404).

Design for the free tier:
- One call per job (small, independent prompts → clean per-job JSON, easy retry).
- Hard cap on calls/run so we never blow the daily quota (new keys get ~30-50/day).
- Graceful degradation: on quota exhaustion or repeated errors we stop calling and
  leave the rest unscored (they still appear in the digest, sorted last).

Privacy note: config/resume.txt is sent with every call. It is meant to hold a
SKILLS/PROJECTS SUMMARY, not your actual resume — no name, contact info, address,
or college name needed for fit-scoring to work well. See config/resume.example.txt.
On the free tier, prompts may also be used by Google to improve their products."""

from __future__ import annotations

import json
import logging
import re
import time

from ..config import Profile
from ..models import JobListing

logger = logging.getLogger("jobdigest")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_PROMPT = """You are screening jobs for a candidate. Score how well THIS job fits \
THIS candidate's skills/background for an early-career application.

CANDIDATE SKILLS SUMMARY:
{resume}

JOB:
Title: {title}
Company: {company}
Location: {location}
Description (truncated):
{description}

Return ONLY strict JSON, no prose, no markdown fences:
{{"fit_score": <integer 0-100>, "rationale": "<one or two sentences, plain>"}}
Where fit_score reflects skills/role/seniority match for a fresher/entry candidate."""


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _make_client(api_key: str):
    # Imported lazily so the rest of the tool runs even without google-genai installed.
    from google import genai

    return genai.Client(api_key=api_key)


def rank(
    jobs: list[JobListing],
    profile: Profile,
    api_key: str | None,
) -> list[JobListing]:
    """Annotate jobs in place with fit_score/rationale. Returns the same list."""
    if not profile.gemini_enabled:
        logger.info("gemini: disabled in profile — skipping stage 2")
        return jobs
    if not api_key:
        logger.warning("gemini: no GEMINI_API_KEY set — skipping stage 2 (jobs stay unscored)")
        return jobs
    if not profile.resume_text:
        logger.warning("gemini: config/resume.txt is empty — scoring will be weak")

    try:
        client = _make_client(api_key)
    except ImportError:
        logger.error("gemini: google-genai not installed (`pip install google-genai`) — skipping")
        return jobs
    except Exception as e:
        logger.error("gemini: client init failed: %s — skipping", e)
        return jobs

    budget = min(len(jobs), profile.gemini_max_calls_per_run)
    if budget < len(jobs):
        logger.info("gemini: capping at %d of %d jobs this run", budget, len(jobs))

    quota_hit = False
    for i, job in enumerate(jobs):
        if i >= budget or quota_hit:
            break
        prompt = _PROMPT.format(
            resume=profile.resume_text[:6000] or "(no resume provided)",
            title=job.title,
            company=job.company,
            location=job.location or "unspecified",
            description=job.description_text[:4000],
        )
        parsed = _call_once(client, profile.gemini_model, prompt)
        if parsed is _QUOTA:
            logger.warning("gemini: daily quota exhausted — stopping; %d jobs left unscored",
                           len(jobs) - i)
            quota_hit = True
            break
        if parsed:
            try:
                job.fit_score = max(0, min(100, int(parsed.get("fit_score"))))
            except (TypeError, ValueError):
                job.fit_score = None
            job.rationale = str(parsed.get("rationale", "")).strip() or None
        else:
            job.rationale = "scoring failed"
        time.sleep(profile.gemini_delay_seconds)

    scored = sum(1 for j in jobs if j.fit_score is not None)
    logger.info("gemini: scored %d/%d jobs", scored, len(jobs))
    return jobs


# Sentinel so _call_once can signal "stop entirely, quota gone" vs "this one failed".
_QUOTA = object()


def _call_once(client, model: str, prompt: str, retries: int = 1):
    for attempt in range(retries + 1):
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            parsed = _extract_json(getattr(resp, "text", "") or "")
            if parsed:
                return parsed
            # Unparseable but not an error → one retry, then give up on this job.
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "quota" in msg or "resource_exhausted" in msg:
                # Distinguish per-minute (RPM) throttle from daily (RPD) exhaustion is
                # unreliable from the message; back off once, then treat as quota-gone.
                if attempt < retries:
                    time.sleep(5)
                    continue
                return _QUOTA
            logger.warning("gemini: call error: %s", e)
            if attempt < retries:
                time.sleep(2)
                continue
            return None
    return None
