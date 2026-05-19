from .models import RawFeatures, NormalizedFeatures

def minmax(values: list[float], v: float) -> float:
    mn, mx = min(values), max(values)
    if mx == mn:
        return 0.0
    return (v - mn) / (mx - mn)

def normalize_repo(raw_features: list[RawFeatures]) -> list[NormalizedFeatures]:
    """
    Normalizes complexity and churn against repo distribution.
    HHI and decayed_recency are already 0–1, passed through directly.
    """
    locs       = [f.complexity.get('loc', 0)       for f in raw_features]
    decisions  = [f.complexity.get('decisions', 0) for f in raw_features]
    imports    = [f.complexity.get('imports', 0)   for f in raw_features]

    commits    = [f.churn.get('commit_count', 0)   for f in raw_features]
    lines      = [f.churn.get('lines_changed', 0)  for f in raw_features]

    normalized = []
    for f in raw_features:
        complexity_score = (
            0.5 * minmax(locs,      f.complexity.get('loc', 0)) +
            0.3 * minmax(decisions, f.complexity.get('decisions', 0)) +
            0.2 * minmax(imports,   f.complexity.get('imports', 0))
        )
        churn_score = (
            0.6 * minmax(commits, f.churn.get('commit_count', 0)) +
            0.4 * minmax(lines,   f.churn.get('lines_changed', 0))
        )
        normalized.append(NormalizedFeatures(
            file_path=f.file_path,
            hhi=f.hhi,
            decayed_recency=f.decayed_recency,
            complexity=round(complexity_score, 4),
            churn=round(churn_score, 4)
        ))
    return normalized