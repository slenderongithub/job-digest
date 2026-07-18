# job-digest

A personal, **read-only** job aggregator. It scrapes open roles from India-relevant
sources, keeps only the ones you're plausibly eligible for, ranks the survivors
against your resume with a free LLM, and writes a local HTML digest of just the
**new** matches each day. No auto-apply. Nothing leaves your machine except the
scraper's own requests and (optionally) the Gemini scoring calls.

## What it does

```
scrape sources → dedup vs. what you've already seen → stage-1 rules
→ stage-2 Gemini fit-scoring (survivors only) → digest/latest.html
```

### Sources

| Source | How | Reliability |
|---|---|---|
| **Greenhouse** | public JSON API (`boards-api.greenhouse.io`) | ⭐ solid |
| **Lever** | public JSON API (`api.lever.co/v0`) | ⭐ solid |
| **Unstop** | public JSON API (`/api/public/...`) | good |
| **Internshala** | server-rendered HTML (path-based pages only) | ok |
| **LinkedIn** | unauthenticated `jobs-guest` HTML fragment | fragile |
| **Naukri** | headless browser (Playwright), best-effort | flaky |

Greenhouse/Lever run off a curated slug list in `config/companies.yaml`. Naukri is
the weakest link (its data is behind a signed token + JS rendering, and automated
access is against its ToS) — if it misbehaves, drop it from `enabled_sources` and
use Naukri's own **RSS/email job alerts** instead.

> **LinkedIn note:** this uses only the *public, logged-out* endpoint — no account,
> no dummy account (a dummy would risk getting IP-linked to your real profile).
> It's kept personal, local, low-volume, and never redistributes data. LinkedIn's
> ToS still technically disallows automated access; use at your discretion.

## Setup

```bash
cd job-digest
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # only needed for the Naukri source

cp config/profile.example.yaml config/profile.yaml   # then edit it
cp config/resume.example.txt config/resume.txt        # then edit it — see note below
# Gemini key (free from https://aistudio.google.com/apikey):
echo "GEMINI_API_KEY=your_key_here" > .env
```

Edit `config/profile.yaml` — CGPA, target keywords/locations, and which
`enabled_sources` to run.

**`config/resume.txt` is a skills summary, not your actual resume.** It's sent to
Gemini with every fit-scoring call, so keep it to skills/projects/interests — no
name, phone, email, address, or college name. Fit-scoring works just as well
without any of that; see `config/resume.example.txt` for the shape. If you'd rather
send nothing at all, set `gemini.enabled: false` in `profile.yaml` and you'll still
get the full stage-1-filtered list, just unranked.

## Run

```bash
python run.py              # daily run (idempotent — skips if already ran today)
python run.py --force      # run again anyway
python run.py --no-gemini  # rules only, no LLM
python run.py --source greenhouse --source lever   # just these
```

Open `digest/latest.html` in a browser. Dated archives pile up in `digest/`.

## Scam warnings

Every eligible listing is run through a local pattern check (`jobdigest/filters/scam_check.py`)
for known job-scam red flags — fee/deposit requests, "no interview / instant offer"
framing, WhatsApp/Telegram-only contact, personal-email-only contact, and classic
WFH/data-entry scam phrasing ("earn ₹X/day", "copy paste work"). Flagged listings
get a visible ⚠️ warning banner in the digest listing exactly what tripped it —
**they're never silently hidden**, since a false positive would be worse than a
missed one. Greenhouse/Lever listings (pulled directly from a company's own ATS)
are effectively unfakeable; Unstop/Internshala are open platforms where anyone can
post, so treat those with the most scrutiny regardless of what the checker says.
This is a heuristic, not a guarantee — always verify a company independently and
never pay anything to apply or get hired.

## Schedule it (macOS, runs when your laptop is on)

```bash
# edit the two absolute paths in the plist first, then:
cp scripts/com.user.jobdigest.plist ~/Library/LaunchAgents/
plutil -lint ~/Library/LaunchAgents/com.user.jobdigest.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.jobdigest.plist
launchctl kickstart -k gui/$(id -u)/com.user.jobdigest   # test-fire now
```

Fires daily at 09:00. Catches up a run missed while asleep (on wake); `RunAtLoad`
reruns it at login to cover an overnight shutdown. `run.py`'s date-guard ensures at
most one digest per day. Manage with `launchctl print|kickstart|bootout gui/$(id -u)/com.user.jobdigest`.

## Verify

```bash
pytest                                             # unit tests
python tests/manual/check_greenhouse.py --company stripe
python tests/manual/check_lever.py --company Sprinto
python tests/manual/check_unstop.py
python tests/manual/check_gemini.py                # needs GEMINI_API_KEY
```

## Adding companies

Find a company's board URL, copy the slug, validate, then add it to
`config/companies.yaml`:

```bash
python tests/manual/check_greenhouse.py --company <slug>   # 404 = wrong/stale slug
python tests/manual/check_lever.py --company <Slug>        # Lever slugs are case-sensitive
```

## How filtering works

1. **Dedup** — jobs seen on a prior run are dropped (state in `data/seen_jobs.json`).
2. **Stage 1 (rules, free):** title blocklist (drop Sales/Accountant/Recruiter/…) →
   seniority (an explicit "Senior/Staff/Lead" *title* is rejected outright) → CGPA
   cutoff → location → relevance gate (must show a tech/role keyword). On a real run
   this cut **4,261 raw → 61** eligible roles.
3. **Stage 2 (Gemini, free):** scores each survivor 0–100 vs. your `resume.txt`.

Tune the keyword lists in `config/profile.yaml` to taste — they're all data, no code.

## Notes / limitations

- **Add your resume.** With an empty `config/resume.txt`, Gemini has nothing to match
  and scores everything low. With a real resume it discriminates well (an ML-fresher
  role scored 95, a senior-SAP role scored 0 in testing).
- **Gemini free tier is small and moving.** New keys currently get only ~30–50
  requests/day, and Google retires pinned models for new users (both `gemini-1.5-*`
  and `gemini-2.5-*` now 404) — so the config uses the floating `gemini-flash-lite-latest`
  alias. If a day's survivors exceed the quota, the extras appear **unscored** at the
  bottom of the digest (the run degrades gracefully, never crashes). Check live limits
  at <https://aistudio.google.com/rate-limit>. On the free tier your prompts may be
  used to improve Google's products — keep `resume.txt` to skills/experience, not PII.
- Undocumented endpoints (Unstop/Greenhouse/Lever guest APIs, LinkedIn guest) can
  change shape or disappear without notice. Parsing is defensive and degrades to an
  empty section rather than crashing.
- This is a **discovery** tool, not an auto-applier. You still review and apply.
