"""Shared data model. Every scraper normalizes its results into JobListing so the
downstream filter/dedup/rank/digest code is completely source-agnostic."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class JobListing:
    # --- identity / provenance ---
    source: str  # "greenhouse" | "lever" | "naukri" | "internshala" | "unstop" | "linkedin"
    company: str
    title: str
    location: str
    url: str

    # --- content ---
    description_text: str = ""  # HTML-stripped plain text, used for keyword matching
    description_raw: str = ""  # original html/text as fetched (optional, for debugging)
    posted_date: Optional[str] = None  # ISO-8601 date string if the source exposes one
    job_id: Optional[str] = None  # source-native id, if any
    fetched_at: Optional[str] = None  # ISO timestamp, stamped by the orchestrator

    # --- annotations populated by the filter/rank pipeline ---
    passed_stage1: Optional[bool] = None
    stage1_reasons: Optional[list[str]] = None
    fit_score: Optional[int] = None  # 0-100 from Gemini; None = unscored
    rationale: Optional[str] = None
    scam_score: Optional[int] = None  # 0-100, higher = more suspicious; None = unchecked
    scam_flags: Optional[list[str]] = None  # human-readable reasons for the score

    def _normalized_parts(self) -> tuple[str, str, str]:
        return (
            (self.company or "").strip().lower(),
            (self.title or "").strip().lower(),
            (self.location or "").strip().lower(),
        )

    def dedup_key(self) -> str:
        """Stable 16-hex-char key from company+title+location so the same role
        mirrored across sources (e.g. a company's own Greenhouse post and an
        Internshala repost) collapses to a single entry. URL is deliberately
        excluded because it differs per source for the same job."""
        company, title, location = self._normalized_parts()
        raw = f"{company}|{title}|{location}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "JobListing":
        # Tolerate extra/missing keys so state files written by older versions load.
        fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in fields})
