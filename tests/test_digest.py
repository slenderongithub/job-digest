import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobdigest.digest import render_html, write_digest
from jobdigest.models import JobListing


def _jobs():
    a = JobListing("greenhouse", "Acme", "ML Engineer (Fresher)", "Bangalore",
                   "https://acme.example/job1")
    a.fit_score = 88
    a.rationale = "Strong ML fit for a fresher."
    b = JobListing("linkedin", "OldCorp", "Data Analyst", "Remote",
                   "https://linkedin.example/job2")
    b.fit_score = 40
    c = JobListing("unstop", "StartupX", "Backend Intern", "Hyderabad",
                   "https://unstop.example/job3")  # unscored
    return [a, b, c]


def test_render_contains_jobs_and_orders_by_score():
    html = render_html(_jobs(), {"new": 3, "eligible": 3})
    assert "ML Engineer (Fresher)" in html
    assert "https://acme.example/job1" in html
    assert "Strong ML fit" in html
    # highest score should appear before the lower one
    assert html.index("ML Engineer (Fresher)") < html.index("Data Analyst")
    # unscored still present
    assert "Backend Intern" in html


def test_scam_warning_rendered_for_flagged_job():
    job = JobListing("internshala", "SketchyCo", "Work From Home Data Entry",
                     "Remote", "https://x")
    job.scam_score = 65
    job.scam_flags = ["asks for a registration fee", "claims instant offer/joining"]
    html = render_html([job], {"new": 1})
    assert "POSSIBLE SCAM" in html
    assert "asks for a registration fee" in html
    assert "scam-row-high" in html


def test_medium_scam_score_shows_caution_not_scam():
    job = JobListing("internshala", "MaybeCo", "Sales Associate", "Remote", "https://x")
    job.scam_score = 25
    job.scam_flags = ["directs contact via WhatsApp"]
    html = render_html([job], {"new": 1})
    assert "Use caution" in html
    assert "POSSIBLE SCAM" not in html


def test_clean_job_has_no_scam_warning():
    job = JobListing("greenhouse", "Acme", "Software Engineer", "Bangalore", "https://x")
    job.scam_score = 0
    job.scam_flags = []
    html = render_html([job], {"new": 1})
    # the CSS block always defines .scam-warn rules; what matters is that no
    # actual warning <div> was rendered into the job row.
    assert '<div class="scam-warn' not in html
    assert "POSSIBLE SCAM" not in html
    assert "Use caution" not in html


def test_empty_digest_has_friendly_message():
    html = render_html([], {"new": 0, "eligible": 0})
    assert "No new eligible jobs" in html


def test_write_digest_creates_files(tmp_path):
    latest = write_digest(_jobs(), {"new": 3}, tmp_path)
    assert latest.exists()
    assert latest.name == "latest.html"
    dated = list(tmp_path.glob("*.html"))
    assert len(dated) == 2  # latest.html + dated archive
