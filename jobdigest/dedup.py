"""Cross-run dedup / state tracking. Persists which jobs have already been shown so
the daily digest only surfaces genuinely new listings."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import JobListing

PRUNE_AFTER_DAYS = 90


@dataclass
class SeenStore:
    path: Path
    seen: dict  # dedup_key -> {first_seen, last_seen, title, company}

    @classmethod
    def load(cls, path: Path) -> "SeenStore":
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(path=path, seen=data.get("seen", {}))
            except (json.JSONDecodeError, OSError):
                # Corrupt/unreadable state: start fresh rather than crash the run.
                return cls(path=path, seen={})
        return cls(path=path, seen={})

    def is_new(self, job: JobListing) -> bool:
        return job.dedup_key() not in self.seen

    def record(self, job: JobListing, today: str) -> None:
        """Mark a job as seen. Updates last_seen for repeats, sets first_seen for new."""
        key = job.dedup_key()
        if key in self.seen:
            self.seen[key]["last_seen"] = today
        else:
            self.seen[key] = {
                "first_seen": today,
                "last_seen": today,
                "title": job.title,
                "company": job.company,
            }

    def prune(self, today: str, days: int = PRUNE_AFTER_DAYS) -> int:
        cutoff = date.fromisoformat(today) - timedelta(days=days)
        stale = [
            k
            for k, v in self.seen.items()
            if _parse_date(v.get("last_seen")) and _parse_date(v["last_seen"]) < cutoff
        ]
        for k in stale:
            del self.seen[k]
        return len(stale)

    def save(self) -> None:
        """Atomic write: temp file in the same dir + os.replace, so an interrupted
        run can never leave a half-written (corrupt) state file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"seen": self.seen}, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


def _parse_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def filter_new(jobs: list[JobListing], store: SeenStore) -> list[JobListing]:
    """Return only jobs not previously seen, deduped within this batch too."""
    out: list[JobListing] = []
    batch_keys: set[str] = set()
    for job in jobs:
        key = job.dedup_key()
        if key in batch_keys:
            continue
        batch_keys.add(key)
        if store.is_new(job):
            out.append(job)
    return out
