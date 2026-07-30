import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobdigest.filters.stage2_gemini import _apply_batch, _extract_array
from jobdigest.models import JobListing


def _batch(n):
    return [JobListing("test", "Acme", f"Job {i}", "India", f"https://x/{i}") for i in range(n)]


def test_apply_batch_maps_by_index_not_order():
    batch = _batch(3)
    # deliberately out of order + clamps out-of-range score
    parsed = [
        {"n": 2, "fit_score": 150, "rationale": "great"},
        {"n": 0, "fit_score": 40, "rationale": "ok"},
        {"n": 1, "fit_score": -5, "rationale": "meh"},
    ]
    _apply_batch(batch, parsed)
    assert batch[0].fit_score == 40
    assert batch[1].fit_score == 0    # clamped
    assert batch[2].fit_score == 100  # clamped


def test_dropped_index_is_marked_failed_not_crash():
    batch = _batch(2)
    _apply_batch(batch, [{"n": 0, "fit_score": 55, "rationale": "x"}])  # index 1 missing
    assert batch[0].fit_score == 55
    assert batch[1].fit_score is None
    assert batch[1].rationale == "scoring failed"


def test_none_marks_whole_batch_failed():
    batch = _batch(2)
    _apply_batch(batch, None)
    assert all(j.fit_score is None and j.rationale == "scoring failed" for j in batch)


def test_extract_array_ignores_surrounding_prose_and_fences():
    txt = 'Sure! ```json\n[{"n":0,"fit_score":70,"rationale":"good"}]\n``` done'
    assert _extract_array(txt) == [{"n": 0, "fit_score": 70, "rationale": "good"}]
    assert _extract_array("no json here") is None
