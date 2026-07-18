import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobdigest.config import Profile
from jobdigest.filters.stage1_rules import evaluate
from jobdigest.models import JobListing


def _profile():
    return Profile(
        cgpa=7.65,
        branch_keywords=["computer science", "cse", "machine learning", "ai"],
        role_keywords=["software engineer", "developer", "data scientist", "backend"],
        exclude_title_keywords=["sales", "accountant", "audit", "recruiter", "legal"],
        require_relevance=True,
        seniority_include=["fresher", "entry level", "graduate", "junior", "new grad", "associate"],
        seniority_exclude=["senior", "staff", "principal", "8+ years", "manager"],
        locations_allow=["india", "remote", "bangalore", "hyderabad", "pune"],
    )


def _job(title="", location="", desc=""):
    return JobListing("test", "Acme", title, location, "https://x", description_text=desc)


def test_clear_fresher_cse_bangalore_passes():
    p = _profile()
    job = _job("Software Engineer (Fresher)", "Bangalore",
               "Entry level role for CSE graduates. Python.")
    passed, reasons = evaluate(job, p)
    assert passed is True, reasons


def test_senior_role_rejected():
    p = _profile()
    job = _job("Senior Backend Engineer", "Bangalore", "8+ years experience required.")
    passed, reasons = evaluate(job, p)
    assert passed is False
    assert any("seniority" in r for r in reasons)


def test_cgpa_cutoff_above_user_rejected():
    p = _profile()
    job = _job("Graduate Engineer Trainee", "Hyderabad",
               "Fresher role. Minimum 8.0 CGPA required.")
    passed, reasons = evaluate(job, p)
    assert passed is False
    assert any("cgpa" in r for r in reasons)


def test_cgpa_cutoff_below_user_passes():
    p = _profile()
    job = _job("Graduate Trainee", "Pune", "Fresher role. Minimum 7.0 CGPA. CSE.")
    passed, _ = evaluate(job, p)
    assert passed is True


def test_no_signal_passes_through():
    p = _profile()
    # No seniority word, no cgpa, but mentions an allowed location.
    job = _job("Software Developer", "Remote", "Build web apps. India.")
    passed, _ = evaluate(job, p)
    assert passed is True


def test_title_blocklist_rejects_finance_role_mentioning_python():
    # Non-tech title + a Python mention in the body must still be dropped by the blocklist.
    p = _profile()
    job = _job("Internal Audit Analyst", "Bangalore",
               "Analyze controls. Experience with Python and SQL a plus.")
    passed, reasons = evaluate(job, p)
    assert passed is False
    assert any("blocklist" in r for r in reasons), reasons


def test_sales_engineer_blocked_by_title():
    p = _profile()
    job = _job("Sales Engineer", "Remote", "Backend python developer skills useful.")
    passed, reasons = evaluate(job, p)
    assert passed is False
    assert any("blocklist" in r for r in reasons), reasons


def test_non_technical_role_rejected_by_relevance_gate():
    # A non-senior, India-based, but clearly non-technical role should be dropped.
    p = _profile()
    job = _job("Customer Support Specialist", "Bangalore",
               "Handle customer escalations. Fresher welcome.")
    passed, reasons = evaluate(job, p)
    assert passed is False
    assert any("relevance" in r for r in reasons)


def test_finance_role_rejected_despite_associate_keyword():
    # "Associate" (a seniority_include word) rescues it from the seniority gate, so the
    # RELEVANCE gate is what must reject this non-technical finance role.
    p = _profile()
    job = _job("Associate, Strategic Finance", "India",
               "Financial planning and reporting for the finance team.")
    passed, reasons = evaluate(job, p)
    assert passed is False
    assert any("relevance" in r for r in reasons), reasons


def test_relevance_gate_can_be_disabled():
    p = _profile()
    p.require_relevance = False
    job = _job("Customer Support Specialist", "Bangalore", "Fresher welcome.")
    passed, _ = evaluate(job, p)
    assert passed is True


def test_non_india_location_rejected():
    p = _profile()
    job = _job("Software Engineer (Fresher)", "Berlin, Germany",
               "Entry level role in Berlin.")
    passed, reasons = evaluate(job, p)
    assert passed is False
    assert any("location" in r for r in reasons)


def test_senior_title_rejected_even_with_junior_in_description():
    # Title seniority is authoritative — a "mentor junior engineers" description must
    # NOT rescue an explicitly-senior title.
    p = _profile()
    job = _job("Senior Software Engineer", "Bangalore",
               "You will mentor junior engineers and new grads. Python backend.")
    passed, reasons = evaluate(job, p)
    assert passed is False
    assert any("title says" in r for r in reasons), reasons


def test_senior_but_also_fresher_keyword_not_rejected_on_seniority():
    # "not for senior" style text shouldn't auto-kill if a fresher keyword is present.
    # (Job is clearly technical so the relevance gate passes and we isolate seniority.)
    p = _profile()
    job = _job("Graduate Software Engineer", "India",
               "New grad program. Not a senior position.")
    passed, _ = evaluate(job, p)
    assert passed is True
