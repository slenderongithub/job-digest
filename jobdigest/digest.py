"""Renders a self-contained HTML digest (inline CSS, no external assets) of the
new, ranked job matches. Writes both a dated archive file and an overwritten
digest/latest.html."""

from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from .models import JobListing

_SOURCE_COLORS = {
    "greenhouse": "#2b8a3e",
    "lever": "#5f3dc4",
    "naukri": "#1971c2",
    "internshala": "#0b7285",
    "unstop": "#c2255c",
    "linkedin": "#0a66c2",
}


def _score_class(score) -> str:
    if score is None:
        return "unscored"
    if score >= 75:
        return "high"
    if score >= 50:
        return "mid"
    return "low"


def _scam_level(scam_score) -> str | None:
    """None = no warning shown. 'high' >= 40, 'medium' >= 20."""
    if scam_score is None or scam_score < 20:
        return None
    return "high" if scam_score >= 40 else "medium"


def _scam_warning(job: JobListing) -> str:
    level = _scam_level(job.scam_score)
    if level is None:
        return ""
    label = "⚠️ POSSIBLE SCAM" if level == "high" else "⚠️ Use caution"
    flags = job.scam_flags or []
    flags_html = "".join(f"<li>{html.escape(f)}</li>" for f in flags)
    return f"""
        <div class="scam-warn scam-{level}">
          <strong>{label}</strong> — automated pattern check flagged this listing:
          <ul>{flags_html}</ul>
          Never pay a fee/deposit to apply or get hired. Verify the company
          independently before sharing any personal or financial details.
        </div>"""


def _row(job: JobListing) -> str:
    score = job.fit_score
    score_txt = "—" if score is None else str(score)
    badge_color = _SOURCE_COLORS.get(job.source, "#495057")
    posted = f" · {html.escape(job.posted_date)}" if job.posted_date else ""
    rationale = html.escape(job.rationale or "")
    scam_level = _scam_level(job.scam_score)
    row_class = f" scam-row-{scam_level}" if scam_level else ""
    return f"""
    <tr class="job {_score_class(score)}{row_class}">
      <td class="score-cell"><span class="score {_score_class(score)}">{score_txt}</span></td>
      <td class="main">
        <a class="title" href="{html.escape(job.url)}" target="_blank" rel="noopener">{html.escape(job.title)}</a>
        <div class="meta">
          <span class="company">{html.escape(job.company)}</span>
          <span class="loc">{html.escape(job.location or "—")}{posted}</span>
          <span class="badge" style="background:{badge_color}">{html.escape(job.source)}</span>
        </div>
        {f'<div class="rationale">{rationale}</div>' if rationale else ''}
        {_scam_warning(job)}
      </td>
    </tr>"""


def render_html(jobs: list[JobListing], stats: dict) -> str:
    today = date.today().isoformat()
    # scored first (desc), then unscored, then by company for stability
    ordered = sorted(
        jobs,
        key=lambda j: (j.fit_score is None, -(j.fit_score or 0), j.company.lower()),
    )
    rows = "\n".join(_row(j) for j in ordered) or (
        '<tr><td colspan="2" class="empty">No new eligible jobs today. 🎉 '
        "Check back tomorrow.</td></tr>"
    )
    summary = " · ".join(f"{k}: {v}" for k, v in stats.items())

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Digest — {today}</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; background: #f6f7f9; color: #1a1d21; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #14161a; color: #e6e8eb; }}
    header {{ background: #1b1e24 !important; border-color: #2a2e35 !important; }}
    tr.job {{ background: #1b1e24 !important; }}
    .rationale {{ color: #9aa0a8 !important; }}
    a.title {{ color: #6ea8fe !important; }}
    .scam-high {{ background: #3a1618 !important; border-color: #8b2c2c !important; color: #ffb3b3 !important; }}
    .scam-medium {{ background: #3a2f14 !important; border-color: #8a6d1f !important; color: #ffd98a !important; }}
  }}
  .wrap {{ max-width: 900px; margin: 0 auto; padding: 24px 16px 64px; }}
  header {{ background: #fff; border: 1px solid #e6e8eb; border-radius: 12px;
           padding: 20px 22px; margin-bottom: 20px; }}
  h1 {{ margin: 0 0 4px; font-size: 22px; }}
  .subtitle {{ color: #6b7280; font-size: 13px; }}
  table {{ width: 100%; border-collapse: separate; border-spacing: 0 10px; }}
  tr.job {{ background: #fff; }}
  tr.job td {{ padding: 14px 16px; vertical-align: top; }}
  tr.job td:first-child {{ border-radius: 10px 0 0 10px; }}
  tr.job td:last-child {{ border-radius: 0 10px 10px 0; }}
  .score-cell {{ width: 62px; text-align: center; }}
  .score {{ display: inline-block; min-width: 40px; padding: 6px 0; border-radius: 8px;
           font-weight: 700; font-size: 15px; color: #fff; }}
  .score.high {{ background: #2f9e44; }}
  .score.mid {{ background: #f08c00; }}
  .score.low {{ background: #868e96; }}
  .score.unscored {{ background: #ced4da; color: #495057; }}
  a.title {{ font-size: 16px; font-weight: 600; color: #1c4b8a; text-decoration: none; }}
  a.title:hover {{ text-decoration: underline; }}
  .meta {{ margin-top: 5px; font-size: 13px; color: #6b7280; display: flex;
          flex-wrap: wrap; gap: 10px; align-items: center; }}
  .company {{ font-weight: 600; color: inherit; }}
  .badge {{ color: #fff; padding: 2px 8px; border-radius: 20px; font-size: 11px;
           text-transform: uppercase; letter-spacing: .3px; }}
  .rationale {{ margin-top: 8px; font-size: 13px; color: #495057; line-height: 1.45; }}
  .empty {{ text-align: center; padding: 40px; color: #6b7280; }}
  tr.job.scam-row-high td {{ box-shadow: inset 4px 0 0 #e03131; }}
  tr.job.scam-row-medium td {{ box-shadow: inset 4px 0 0 #f08c00; }}
  .scam-warn {{ margin-top: 10px; padding: 10px 12px; border-radius: 8px; font-size: 12.5px;
               line-height: 1.5; border: 1px solid; }}
  .scam-warn.scam-high {{ background: #fff5f5; border-color: #ffc9c9; color: #a61e1e; }}
  .scam-warn.scam-medium {{ background: #fff9db; border-color: #ffe066; color: #7a5c00; }}
  .scam-warn ul {{ margin: 4px 0 4px 18px; padding: 0; }}
  .scam-warn li {{ margin: 2px 0; }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>📬 Job Digest — {today}</h1>
      <div class="subtitle">{html.escape(summary)}</div>
    </header>
    <table>
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>
</body>
</html>"""


def write_digest(jobs: list[JobListing], stats: dict, digest_dir: Path) -> Path:
    digest_dir.mkdir(parents=True, exist_ok=True)
    doc = render_html(jobs, stats)
    dated = digest_dir / f"{date.today().isoformat()}.html"
    latest = digest_dir / "latest.html"
    dated.write_text(doc, encoding="utf-8")
    latest.write_text(doc, encoding="utf-8")
    return latest
