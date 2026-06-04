from .extractor import extract_raw_features
from .normalizer import normalize_repo
from .scorer import compute_risk
from .filters import is_excluded_file
from .models import FileCommit, RiskScore

def run_pipeline(file_commit_map: dict[str, list[FileCommit]],
                top_n: int = 20) -> list[RiskScore]:
    """
    file_commit_map: { file_path -> [FileCommit, ...] }
    Returns risk scores sorted highest first.
    """

    # 1. Filter excluded files
    filtered = {
        path: commits
        for path, commits in file_commit_map.items()
        if not is_excluded_file(path)
    }

    # 2. Extract raw features per file
    raw_features = {
        path: extract_raw_features(path, commits)
        for path, commits in filtered.items()
    }

    # 3. Normalize across repo
    normalized = normalize_repo(list(raw_features.values()))
    norm_map = {n.file_path: n for n in normalized}

    # 4. Score each file
    scores = [
        compute_risk(
            norm_map[path],
            raw_features[path],
            filtered[path]
        )
        for path in filtered
    ]

    # 5. Sort and return top N for LLM summarization
    scores.sort(key=lambda s: s.score, reverse=True)
    return scores[:top_n]