from scipy import stats
import numpy as np

from .models import RawFeatures, NormalizedFeatures

def percentile_normalize(values: list[float]) -> list[float]:
    if len(values) <= 1:
        return [0.0] * len(values)
    ranks = stats.rankdata(values, method='average')
    return [round(float((r - 1) / (len(ranks) - 1)), 4) 
            for r in ranks]

def normalize_repo(raw_features: list[RawFeatures]) -> list[NormalizedFeatures]:
    locs      = [f.complexity.get('loc', 0)       for f in raw_features]
    decisions = [f.complexity.get('decisions', 0) for f in raw_features]
    imports   = [f.complexity.get('imports', 0)   for f in raw_features]
    commits   = [f.churn.get('commit_count', 0)   for f in raw_features]
    lines     = [f.churn.get('lines_changed', 0)  for f in raw_features]

    # Percentile normalize each raw signal
    locs_n      = percentile_normalize(locs)
    decisions_n = percentile_normalize(decisions)
    imports_n   = percentile_normalize(imports)
    commits_n   = percentile_normalize(commits)
    lines_n     = percentile_normalize(lines)

    normalized = []
    for i, f in enumerate(raw_features):
        complexity_score = (
            0.5 * locs_n[i] +
            0.3 * decisions_n[i] +
            0.2 * imports_n[i]
        )
        churn_score = (
            0.6 * commits_n[i] +
            0.4 * lines_n[i]
        )
        normalized.append(NormalizedFeatures(
            file_path=f.file_path,
            hhi=f.hhi,                    # already 0-1, no normalization needed
            decayed_recency=f.decayed_recency,  # same
            complexity=round(complexity_score, 4),
            churn=round(churn_score, 4)
        ))
    return normalized