"""Stage 2: LLM fit-scoring of stage-1 survivors against the user's skills profile,
via the Google Gemini free tier. Uses the current unified `google-genai` SDK (the
old `google-generativeai` package is deprecated and Gemini 1.5 models 404).

Design for the free tier:
- BATCHED: one call scores up to BATCH_SIZE jobs (JSON array back), so a ~50-call
  daily quota scores ~50*BATCH_SIZE jobs instead of 50. The quota, not the scrape,
  is the real ceiling — batching is what lifts it.
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

# Jobs scored per Gemini call. Bigger = fewer calls = more jobs per daily quota, but
# a larger prompt and more chance the model drops/miscounts an entry. 10 is a safe
# middle for flash-lite. ponytail: fixed batch size, tune if the model starts truncating.
BATCH_SIZE = 10

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)

_PROMPT = """You are screening jobs for a candidate. Score how well each job below fits \
THIS candidate's skills/background for an early-career (fresher/entry) application.

CANDIDATE SKILLS SUMMARY:
{resume}

JOBS (each starts with its index number):
{jobs_block}

Return ONLY a strict JSON array, no prose, no markdown fences. One object per job, \
using the SAME index number given above:
[{{"n": <index>, "fit_score": <integer 0-100>, "rationale": "<one or two sentences, plain>"}}]
fit_score reflects skills/role/seniority match for a fresher/entry candidate. \
Include an object for EVERY index; if unsure, still give your best estimate."""

_JOB_TMPL = """[{n}]
Title: {title}
Company: {company}
Location: {location}
Description (truncated):
{description}
"""


def _extract_array(text: str) -> list | None:
    if not text:
        return None
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return None
    try:
        val = json.loads(m.group(0))
        return val if isinstance(val, list) else None
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

    # Chunk into batches; the call cap now bounds BATCHES, so it covers
    # max_calls_per_run * BATCH_SIZE jobs on the same quota.
    batches = [jobs[i:i + BATCH_SIZE] for i in range(0, len(jobs), BATCH_SIZE)]
    call_budget = profile.gemini_max_calls_per_run
    if len(batches) > call_budget:
        covered = call_budget * BATCH_SIZE
        logger.info("gemini: capping at %d calls (%d of %d jobs) this run",
                    call_budget, covered, len(jobs))

    scored_so_far = 0
    for bi, batch in enumerate(batches):
        if bi >= call_budget:
            break
        jobs_block = "\n".join(
            _JOB_TMPL.format(
                n=n,
                title=job.title,
                company=job.company,
                location=job.location or "unspecified",
                description=job.description_text[:1500],
            )
            for n, job in enumerate(batch)
        )
        prompt = _PROMPT.format(
            resume=profile.resume_text[:6000] or "(no resume provided)",
            jobs_block=jobs_block,
        )
        parsed = _call_once(client, profile.gemini_model, prompt)
        if parsed is _QUOTA:
            left = len(jobs) - scored_so_far
            logger.warning("gemini: daily quota exhausted — stopping; ~%d jobs left unscored", left)
            break
        _apply_batch(batch, parsed)
        scored_so_far += len(batch)
        time.sleep(profile.gemini_delay_seconds)

    scored = sum(1 for j in jobs if j.fit_score is not None)
    logger.info("gemini: scored %d/%d jobs", scored, len(jobs))
    return jobs


def _apply_batch(batch: list[JobListing], parsed: list | None) -> None:
    """Map a JSON array of {n, fit_score, rationale} back onto the batch by index."""
    if not parsed:
        for job in batch:
            job.rationale = "scoring failed"
        return
    by_n = {}
    for obj in parsed:
        if isinstance(obj, dict) and "n" in obj:
            try:
                by_n[int(obj["n"])] = obj
            except (TypeError, ValueError):
                continue
    for n, job in enumerate(batch):
        obj = by_n.get(n)
        if not obj:
            job.rationale = "scoring failed"  # model dropped this index
            continue
        try:
            job.fit_score = max(0, min(100, int(obj.get("fit_score"))))
        except (TypeError, ValueError):
            job.fit_score = None
        job.rationale = str(obj.get("rationale", "")).strip() or None


# Sentinel so _call_once can signal "stop entirely, quota gone" vs "this one failed".
_QUOTA = object()


def _call_once(client, model: str, prompt: str, retries: int = 1):
    for attempt in range(retries + 1):
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            parsed = _extract_array(getattr(resp, "text", "") or "")
            if parsed:
                return parsed
            # Unparseable but not an error → one retry, then give up on this batch.
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
