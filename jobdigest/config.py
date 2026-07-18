"""Loads all configuration: .env secrets, config/profile.yaml (eligibility rules +
resume), and config/companies.yaml (Greenhouse/Lever seed slugs)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

# Resolve project directories relative to this file so paths work no matter the CWD
# (important: launchd may invoke run.py from an arbitrary working directory).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
DIGEST_DIR = PROJECT_ROOT / "digest"


@dataclass
class Profile:
    cgpa: float
    branch_keywords: list[str] = field(default_factory=list)
    role_keywords: list[str] = field(default_factory=list)
    exclude_title_keywords: list[str] = field(default_factory=list)
    require_relevance: bool = True
    seniority_include: list[str] = field(default_factory=list)
    seniority_exclude: list[str] = field(default_factory=list)
    locations_allow: list[str] = field(default_factory=list)

    # search terms fed to the keyword-driven scrapers (naukri/internshala/unstop/linkedin)
    search_keywords: list[str] = field(default_factory=list)
    search_locations: list[str] = field(default_factory=list)

    # source toggles
    enabled_sources: list[str] = field(default_factory=list)

    # gemini ranking controls
    gemini_enabled: bool = True
    gemini_model: str = "gemini-flash-lite-latest"  # floating alias → current cheap lite model
    gemini_max_calls_per_run: int = 50
    gemini_delay_seconds: float = 1.5

    # per-source polite scraping caps
    max_pages_per_query: int = 3

    resume_text: str = ""


def load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def get_gemini_api_key() -> Optional[str]:
    return os.environ.get("GEMINI_API_KEY")


def _read_resume() -> str:
    txt = CONFIG_DIR / "resume.txt"
    if txt.exists():
        return txt.read_text(encoding="utf-8", errors="ignore").strip()
    return ""


def load_profile(path: Optional[Path] = None) -> Profile:
    path = path or (CONFIG_DIR / "profile.yaml")
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy config/profile.example.yaml to config/profile.yaml "
            "and fill in your details."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    gem = raw.get("gemini", {}) or {}
    search = raw.get("search", {}) or {}

    return Profile(
        cgpa=float(raw.get("cgpa", 0.0)),
        branch_keywords=list(raw.get("branch_keywords", [])),
        role_keywords=list(raw.get("role_keywords", [])),
        exclude_title_keywords=[s.lower() for s in raw.get("exclude_title_keywords", [])],
        require_relevance=bool(raw.get("require_relevance", True)),
        seniority_include=list(raw.get("seniority_include", [])),
        seniority_exclude=list(raw.get("seniority_exclude", [])),
        locations_allow=[s.lower() for s in raw.get("locations_allow", [])],
        search_keywords=list(search.get("keywords", [])),
        search_locations=list(search.get("locations", [])),
        enabled_sources=list(raw.get("enabled_sources", [])),
        gemini_enabled=bool(gem.get("enabled", True)),
        gemini_model=str(gem.get("model", "gemini-flash-lite-latest")),
        gemini_max_calls_per_run=int(gem.get("max_calls_per_run", 50)),
        gemini_delay_seconds=float(gem.get("delay_seconds", 1.5)),
        max_pages_per_query=int(raw.get("max_pages_per_query", 3)),
        resume_text=_read_resume(),
    )


def load_companies(path: Optional[Path] = None) -> dict:
    path = path or (CONFIG_DIR / "companies.yaml")
    if not path.exists():
        return {"greenhouse": [], "lever": []}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "greenhouse": list(raw.get("greenhouse", [])),
        "lever": list(raw.get("lever", [])),
    }
