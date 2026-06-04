from .models import NormalizedFeatures, RawFeatures, RiskScore
from .confidence import compute_confidence
from .extractor import compute_recency_raw, compute_hhi_raw

def compute_risk(norm: NormalizedFeatures,
                raw: RawFeatures,
                commits) -> RiskScore:

    fragility = (0.45 * norm.hhi) + (0.25 * norm.decayed_recency)
    amplifier = 1 + (0.20 * norm.complexity) + (0.10 * norm.churn)
    raw_score = 100 * fragility * amplifier
    score = round(max(0.0, min(100.0, raw_score)), 2)

    _, top_authors = compute_hhi_raw(commits)
    _, living_knowledge, last_commit = compute_recency_raw(commits)
    confidence_result = compute_confidence(raw)

    return RiskScore(
        file_path=norm.file_path,
        score=score,
        hhi=norm.hhi,
        decayed_recency=norm.decayed_recency,
        complexity=norm.complexity,
        churn=norm.churn,
        fragility=round(fragility, 4),
        amplifier= round(amplifier, 4),
        confidence= confidence_result.level,
        confidence_flags=confidence_result.to_strings(),
        top_authors=top_authors,
        living_knowledge=living_knowledge,
        last_meaningful_commit=last_commit
    )