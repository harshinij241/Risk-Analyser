import json
import csv
import io
from datetime import datetime
from typing import Optional
from .models import RiskScore


# ── JSON ───────────────────────────────────────────────────────────────────

def to_json(scores: list[RiskScore],
            indent: int = 2) -> str:
    """
    Full fidelity export. Suitable for dashboard ingestion,
    GitHub Action artifacts, and LLM context building.
    """
    def serialize(s: RiskScore) -> dict:
        return {
            "file": s.file_path,
            "score": s.score,
            "confidence": s.confidence,
            "confidence_flags": s.confidence_flags,
            "breakdown": {
                "hhi": s.hhi,
                "decayed_recency": s.decayed_recency,
                "complexity": s.complexity,
                "churn": s.churn,
                "fragility": s.fragility,
                "amplifier": s.amplifier,
            },
            "authorship": {
                "living_knowledge": s.living_knowledge,
                "top_authors": [
                    {"author": a, "share": round(sh, 3)}
                    for a, sh in s.top_authors
                ],
                "last_meaningful_commit": (
                    s.last_meaningful_commit.isoformat()
                    if s.last_meaningful_commit else None
                ),
            }
        }

    payload = {
        "generated_at": datetime.now().isoformat(),
        "total_files_scored": len(scores),
        "results": [serialize(s) for s in scores]
    }
    return json.dumps(payload, indent=indent)


# ── CSV ────────────────────────────────────────────────────────────────────

def to_csv(scores: list[RiskScore]) -> str:
    """
    Flat export for spreadsheet review or BI tools.
    One row per file, key metrics as columns.
    """
    output = io.StringIO()
    fieldnames = [
        'file', 'score', 'confidence',
        'hhi', 'decayed_recency', 'complexity', 'churn',
        'living_knowledge', 'top_author', 'top_author_share',
        'last_meaningful_commit', 'confidence_flags'
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for s in scores:
        top_author, top_share = s.top_authors[0] if s.top_authors else ('', 0)
        writer.writerow({
            'file': s.file_path,
            'score': s.score,
            'confidence': s.confidence,
            'hhi': s.hhi,
            'decayed_recency': s.decayed_recency,
            'complexity': s.complexity,
            'churn': s.churn,
            'living_knowledge': s.living_knowledge,
            'top_author': top_author,
            'top_author_share': round(top_share, 3),
            'last_meaningful_commit': (
                s.last_meaningful_commit.date().isoformat()
                if s.last_meaningful_commit else ''
            ),
            'confidence_flags': ' | '.join(s.confidence_flags)
        })

    return output.getvalue()


# ── Markdown ───────────────────────────────────────────────────────────────

def to_markdown(scores: list[RiskScore],
                repo_name: str = "Repository",
                top_n: int = 10) -> str:
    """
    Human-readable report for GitHub PR comments,
    Slack messages, or internal wikis.
    """
    lines = [
        f"## Knowledge Risk Report — {repo_name}",
        f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        f"### Top {min(top_n, len(scores))} highest-risk files",
        "",
        "| # | File | Score | Confidence | Top Author | Living Knowledge |",
        "|---|------|-------|------------|------------|-----------------|",
    ]

    for i, s in enumerate(scores[:top_n], 1):
        top_author = s.top_authors[0][0] if s.top_authors else "—"
        living = f"{s.living_knowledge:.0%}"
        conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(
            s.confidence, "⚪"
        )
        lines.append(
            f"| {i} | `{s.file_path}` | **{s.score:.1f}** | "
            f"{conf_emoji} {s.confidence} | {top_author} | {living} |"
        )

    # Summary stats
    high_risk   = [s for s in scores if s.score >= 75]
    medium_risk = [s for s in scores if 40 <= s.score < 75]
    low_conf    = [s for s in scores if s.confidence == 'low']

    lines += [
        "",
        "### Summary",
        "",
        f"- **High risk** (≥75): {len(high_risk)} files",
        f"- **Medium risk** (40–74): {len(medium_risk)} files",
        f"- **Low confidence scores**: {len(low_conf)} files "
         "(treat with caution)",
        "",
    ]

    if high_risk:
        lines += [
            "### High-risk files — action recommended",
            "",
        ]
        for s in high_risk:
            flags = (
                "\n  - " + "\n  - ".join(s.confidence_flags)
                if s.confidence_flags else ""
            )
            lines += [
                f"**`{s.file_path}`** — score {s.score:.1f}",
                f"- Fragility: {s.fragility:.2f} × Amplifier: "
                f"{s.amplifier:.2f}",
                f"- Living knowledge: {s.living_knowledge:.0%}",
                f"- Last meaningful commit: "
                f"{s.last_meaningful_commit.date().isoformat() if s.last_meaningful_commit else 'unknown'}",
                flags,
                "",
            ]

    return "\n".join(lines)


# ── LLM prompt builder ─────────────────────────────────────────────────────

def to_llm_prompt(score: RiskScore,
                system_context: Optional[str] = None) -> str:
    """
    Builds a structured prompt for local LLM summarization.
    Includes all signal data so the model can reason about
    *why* the file is risky, not just that it is.
    """
    top_authors_text = ", ".join(
        f"{a} ({sh:.0%})" for a, sh in score.top_authors
    ) or "unknown"

    flags_text = (
        "\n".join(f"  - {f}" for f in score.confidence_flags)
        if score.confidence_flags
        else "  None"
    )

    last_commit = (
        score.last_meaningful_commit.date().isoformat()
        if score.last_meaningful_commit else "unknown"
    )

    prompt = f"""You are a senior engineering analyst reviewing codebase knowledge risk.

FILE UNDER REVIEW: {score.file_path}

RISK SIGNALS:
  Overall risk score : {score.score:.1f} / 100
  Confidence level   : {score.confidence}

  Ownership (HHI)    : {score.hhi:.2f}
    → 1.0 = one person wrote everything
    → 0.25 = four equal contributors

  Knowledge staleness: {score.decayed_recency:.2f}
    → 0 = knowledge is fresh, 1 = fully stale

  Living knowledge   : {score.living_knowledge:.0%}
    → proportion of original understanding still active

  Complexity         : {score.complexity:.2f} (normalized 0–1)
  Churn              : {score.churn:.2f} (normalized 0–1)

  Top authors        : {top_authors_text}
  Last meaningful commit: {last_commit}

CONFIDENCE FLAGS:
{flags_text}

Based on the file path and these risk signals, write a concise report (3–5 sentences) covering:
1. What this file likely does and what domain it belongs to
2. Why it is flagged as high risk (cite the specific signals above)
3. What a new developer would need to understand before modifying it
4. One concrete action the engineering team should take

Be specific. Do not restate the numbers — interpret them.
"""

    if system_context:
        prompt = f"{system_context}\n\n{prompt}"

    return prompt


# ── GitHub Action summary ──────────────────────────────────────────────────

def to_github_action_summary(scores: list[RiskScore],
                            threshold: float = 75.0) -> str:
    """
    Writes to GITHUB_STEP_SUMMARY format.
    Called when risk score exceeds threshold on a PR.
    """
    triggered = [s for s in scores if s.score >= threshold]
    if not triggered:
        return f"✅ No files exceeded risk threshold of {threshold:.0f}."

    lines = [
        f"## ⚠️ Knowledge Risk Alert",
        f"{len(triggered)} file(s) exceed risk threshold of {threshold:.0f}",
        "",
        "| File | Score | Top Author | Living Knowledge |",
        "|------|-------|------------|-----------------|",
    ]
    for s in triggered:
        top = s.top_authors[0][0] if s.top_authors else "—"
        lines.append(
            f"| `{s.file_path}` | {s.score:.1f} | {top} | "
            f"{s.living_knowledge:.0%} |"
        )

    return "\n".join(lines)