import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobdigest.dedup import SeenStore, filter_new
from jobdigest.models import JobListing


def _job(company="Acme", title="ML Engineer", location="Bangalore"):
    return JobListing("greenhouse", company, title, location, "https://x")


def test_same_job_seen_only_once(tmp_path):
    store = SeenStore.load(tmp_path / "seen.json")
    today = date.today().isoformat()
    job = _job()

    first = filter_new([job], store)
    assert len(first) == 1  # new the first time
    for j in first:
        store.record(j, today)

    second = filter_new([job], store)
    assert len(second) == 0  # suppressed the second time


def test_within_batch_dedup(tmp_path):
    store = SeenStore.load(tmp_path / "seen.json")
    # same role scraped from two sources in one run collapses to one
    a = JobListing("greenhouse", "Acme", "ML Engineer", "Bangalore", "https://a")
    b = JobListing("linkedin", "Acme", "ML Engineer", "Bangalore", "https://b")
    assert len(filter_new([a, b], store)) == 1


def test_prune_old_entries(tmp_path):
    store = SeenStore.load(tmp_path / "seen.json")
    today = date.today()
    old = (today - timedelta(days=91)).isoformat()
    store.seen["deadkey"] = {"first_seen": old, "last_seen": old,
                             "title": "x", "company": "y"}
    removed = store.prune(today.isoformat())
    assert removed == 1
    assert "deadkey" not in store.seen


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "seen.json"
    store = SeenStore.load(path)
    store.record(_job(), date.today().isoformat())
    store.save()

    reloaded = SeenStore.load(path)
    assert reloaded.is_new(_job()) is False
