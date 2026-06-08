# llm/prompts.py

from knowledge_risk.models import RiskScore


SYSTEM_PROMPT = """You are a senior engineering risk analyst writing \
reports for CTOs and engineering managers.

Your job is to analyze high-risk source files and produce structured \
risk reports that engineering leadership can act on immediately.

Always respond in this exact JSON format with no extra text:
{
  "business_criticality": "High | Medium | Low",
  "business_impact": "One sentence max. What breaks if this file is wrong.",
  "knowledge_areas": [
    "specific skill 1",
    "specific skill 2",
    "specific skill 3"
  ],
  "risk_drivers": [
    "+ one amplifier",
    "+ another amplifier",
    "- one mitigator"
  ],
  "recommended_actions": [
    "Action 1 with deadline",
    "Action 2 with deadline",
    "Action 3 with deadline"
  ],
  "onboarding_notes": "Two sentences max. What new dev must know."
}

STRICT RULES:
- knowledge_areas: exactly 3-5 items, each under 10 words
- risk_drivers: exactly 2-4 items, each under 12 words
- recommended_actions: exactly 3 items, each under 20 words
- business_impact: one sentence, under 25 words
- onboarding_notes: two sentences max, under 40 words total
- No trailing commas in JSON
- No markdown outside the JSON block
- No explanations, no preamble, no postamble
- Return ONLY the JSON object"""


def build_user_prompt(score: RiskScore) -> str:
    top_authors = ", ".join(
        f"{a} ({s:.0%})"
        for a, s in score.top_authors
    ) or "unknown"

    primary_owner = (
        score.top_authors[0][0]
        if score.top_authors else "unknown"
    )
    primary_share = (
        score.top_authors[0][1]
        if score.top_authors else 0
    )
    backup_count = len(score.top_authors) - 1

    last_commit = (
        score.last_meaningful_commit.date().isoformat()
        if score.last_meaningful_commit else "unknown"
    )

    flags = (
        "\n".join(f"  - {f}" for f in score.confidence_flags)
        if score.confidence_flags else "  none"
    )

    ownership_label = _label(score.hhi,
                             low="distributed",
                             mid="moderately concentrated",
                             high="highly concentrated")
    recency_label   = _label(score.decayed_recency,
                             low="fresh",
                             mid="aging",
                             high="stale")

    return f"""FILE: {score.file_path}
RISK SCORE: {score.score:.1f} / 100
CONFIDENCE: {score.confidence}

OWNERSHIP ANALYSIS:
  Primary contributor : {primary_owner}
  Ownership share     : {primary_share:.0%}
  Backup maintainers  : {backup_count}
  Bus factor          : {len(score.top_authors)}
  All contributors    : {top_authors}

RISK SIGNALS:
  Concentration (HHI) : {score.hhi:.2f}  → {ownership_label}
  Knowledge staleness : {score.decayed_recency:.2f}  → {recency_label}
  Complexity          : {score.complexity:.2f}  (repo-normalized 0–1)
  Churn               : {score.churn:.2f}  (recent change volume)
  Living knowledge    : {score.living_knowledge:.0%} retained
  Last meaningful commit: {last_commit}

RISK SCORE BREAKDOWN:
  Fragility score     : {score.fragility:.3f}
  Amplifier           : {score.amplifier:.3f}x
  Formula             : 100 × {score.fragility:.3f} × {score.amplifier:.3f} = {score.score:.1f}

CONFIDENCE FLAGS:
{flags}

Write a risk report for this file that an engineering manager
can use in a risk review meeting. Be specific. Name the primary
contributor. Cite the actual signals. Make actions measurable."""


def build_score_breakdown(score: RiskScore) -> list[dict]:
    """
    Builds a human-readable score breakdown showing
    what contributed to the final number.
    Used in dashboard and PDF report.
    """
    breakdown = []

    # Ownership contribution
    ownership_points = round(0.45 * score.hhi * 100 * score.amplifier, 1)
    breakdown.append({
        "label": f"Single/concentrated authorship (HHI={score.hhi:.2f})",
        "points": f"+{ownership_points}",
        "type": "risk"
    })

    # Recency contribution
    recency_points = round(0.25 * score.decayed_recency * 100 * score.amplifier, 1)
    breakdown.append({
        "label": f"Knowledge staleness ({score.decayed_recency:.0%} stale)",
        "points": f"+{recency_points}",
        "type": "risk"
    })

    # Complexity amplification
    if score.complexity > 0.3:
        complexity_boost = round((score.complexity * 0.20) * 100, 1)
        breakdown.append({
            "label": f"High complexity amplifier ({score.complexity:.2f})",
            "points": f"+{complexity_boost}",
            "type": "amplifier"
        })

    # Churn amplification
    if score.churn > 0.3:
        churn_boost = round((score.churn * 0.10) * 100, 1)
        breakdown.append({
            "label": f"High churn amplifier ({score.churn:.2f})",
            "points": f"+{churn_boost}",
            "type": "amplifier"
        })

    # Mitigators
    if score.living_knowledge > 0.5:
        breakdown.append({
            "label": f"Good living knowledge retention ({score.living_knowledge:.0%})",
            "points": f"-{round(score.living_knowledge * 10, 1)}",
            "type": "mitigator"
        })

    for flag in score.confidence_flags:
        if "new" in flag.lower() or "young" in flag.lower():
            breakdown.append({
                "label": "File age reduces confidence",
                "points": "-5 (confidence)",
                "type": "mitigator"
            })
            break

    return breakdown


def _label(value: float, low: str, mid: str, high: str) -> str:
    if value < 0.35:
        return low
    if value < 0.70:
        return mid
    return high