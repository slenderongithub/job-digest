import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobdigest.filters.scam_check import evaluate
from jobdigest.models import JobListing


def _job(title="Software Engineer", desc=""):
    return JobListing("test", "Acme", title, "India", "https://x", description_text=desc)


def test_clean_listing_scores_zero():
    job = _job(desc=(
        "We are hiring a backend engineer to work on our Python/Django APIs. "
        "Apply through our careers page. Interview process: phone screen, "
        "technical round, final round with the team."
    ))
    score, flags = evaluate(job)
    assert score == 0
    assert flags == []


def test_registration_fee_flagged_high():
    job = _job(desc="Selected candidates must pay a registration fee of Rs 500 to confirm the offer.")
    score, flags = evaluate(job)
    assert score >= 40
    assert any("registration fee" in f for f in flags)


def test_security_deposit_flagged_high():
    job = _job(desc="A refundable security deposit of Rs 2000 is required before training begins.")
    score, flags = evaluate(job)
    assert score >= 40


def test_no_interview_required_flagged():
    job = _job(desc="Instant joining, no interview required. Start earning today!")
    score, flags = evaluate(job)
    assert score >= 30
    assert any("no interview" in f or "instant" in f for f in flags)


def test_whatsapp_only_contact_flagged_medium():
    job = _job(desc="Interested candidates should contact us on WhatsApp only for further details.")
    score, flags = evaluate(job)
    assert 15 <= score < 40
    assert any("WhatsApp" in f for f in flags)


def test_earn_per_day_wfh_framing_flagged():
    job = _job(title="Work From Home Data Entry",
              desc="Earn up to Rs 3000 per day! No experience needed, flexible hours.")
    score, flags = evaluate(job)
    assert score >= 25


def test_copy_paste_work_flagged():
    job = _job(desc="Simple copy paste work from home, earn extra income.")
    score, flags = evaluate(job)
    assert score >= 25


def test_personal_gmail_contact_flagged():
    job = _job(desc="Send your resume and a copy of your Aadhaar to hr.recruiter123@gmail.com")
    score, flags = evaluate(job)
    assert score >= 15
    assert any("personal domain" in f for f in flags)


def test_legit_company_email_not_flagged():
    job = _job(desc="Send your resume to careers@acmecorp.com to apply.")
    score, flags = evaluate(job)
    assert score == 0


def test_multiple_red_flags_compound_score():
    job = _job(
        title="Work From Home - Urgent Hiring",
        desc=(
            "Pay a registration fee of Rs 999 to secure your spot. No interview "
            "required, instant joining. Contact us on WhatsApp only. "
            "Earn up to Rs 5000 per day!"
        ),
    )
    score, flags = evaluate(job)
    assert score >= 70  # multiple strong signals should compound
    assert len(flags) >= 4


def test_score_capped_at_100():
    job = _job(
        desc=(
            "registration fee security deposit refundable deposit processing fee "
            "training fee joining fee activation fee caution money pay before joining "
            "advance payment purchase a kit no interview required instant offer "
            "instant joining without any interview selection is 100% guaranteed"
        )
    )
    score, _ = evaluate(job)
    assert score == 100
