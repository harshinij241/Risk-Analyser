from knowledge_risk.models import RiskScore


SYSTEM_PROMPT = """You are a senior engineering analyst specializing \
in codebase knowledge risk.

Your job is to analyze high-risk source files and explain them clearly \
to engineering managers and new developers.

Always respond in this exact JSON format with no extra text:
{
  "what_it_does": "2-3 sentences describing what this file does and \
what system it belongs to",
  "domain_knowledge": "2-3 sentences describing the expertise needed \
to maintain this file",
  "onboarding_notes": "2-3 sentences describing what a new developer \
must understand before modifying this file",
  "recommended_action": "one specific, concrete action the engineering \
team should take to reduce risk"
}

Rules:
- Be specific. Do not use vague language like 'this file handles logic'.
- Infer meaning from the file path, not just the risk numbers.
- Cite the risk signals when explaining why the file is dangerous.
- The recommended action must be actionable within 2 weeks.
- Never return anything outside the JSON block."""


def build_user_prompt(score: RiskScore) -> str:
    """
    Builds the per-file user prompt from a RiskScore object.
    Structured to give the model maximum context for inference.
    """
    top_authors = ", ".join(
        f"{a} ({s:.0%})"
        for a, s in score.top_authors
    ) or "unknown"

    last_commit = (
        score.last_meaningful_commit.date().isoformat()
        if score.last_meaningful_commit else "unknown"
    )

    flags = (
        "\n".join(f"  - {f}" for f in score.confidence_flags)
        if score.confidence_flags else "  none"
    )

    # Risk interpretation helpers
    ownership_label = _label(score.hhi,
                              low="distributed", mid="moderate",
                              high="highly concentrated")
    recency_label   = _label(score.decayed_recency,
                              low="fresh", mid="aging",
                              high="stale")
    complexity_label = _label(score.complexity,
                              low="simple", mid="moderate",
                              high="complex")
    churn_label      = _label(score.churn,
                              low="stable", mid="active",
                              high="volatile")
    return f"""FILE: {score.file_path}
RISK SCORE: {score.score:.1f} / 100
CONFIDENCE: {score.confidence}

RISK BREAKDOWN:
  Ownership  : {score.hhi:.2f}  → {ownership_label}
                (1.0 = one person wrote everything,
                0.25 = four equal contributors)

  Staleness  : {score.decayed_recency:.2f}  → {recency_label}
                (0 = knowledge is fresh, 1 = fully forgotten)

  Complexity : {score.complexity:.2f}  → {complexity_label}
                (relative to this repo, normalized 0–1)

  Churn      : {score.churn:.2f}  → {churn_label}
                (recent change volume, normalized 0–1)

  Living knowledge retained : {score.living_knowledge:.0%}
  Top contributors          : {top_authors}
  Last meaningful commit    : {last_commit}

CONFIDENCE FLAGS:
{flags}

Based on the file path and risk signals above, generate your analysis."""


def _label(value: float,
            low: str, mid: str, high: str) -> str:
    """Converts a 0–1 score to a human-readable label."""
    if value < 0.35:
        return low
    if value < 0.70:
        return mid
    return high
