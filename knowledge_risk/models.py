from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class FileCommit:
    file_path: str
    author: str
    timestamp: datetime
    lines_added: int
    lines_deleted: int
    commit_hash: str
    message: str

    @property
    def lines_changed(self) -> int:
        return self.lines_added + self.lines_deleted

    @property
    def age_days(self) -> float:
        return (datetime.now() - self.timestamp).total_seconds() / 86400


@dataclass
class RawFeatures:
    file_path: str
    hhi: float                    # 0–1, concentration
    decayed_recency: float        # 0–1, staleness
    complexity: dict              # raw dict, not yet normalized
    churn: dict                   # raw dict, not yet normalized
    total_commits: int
    unique_authors: int
    file_age_days: float
    has_sparse_history: bool      # < 3 commits total


@dataclass
class NormalizedFeatures:
    file_path: str
    hhi: float              # 0–1
    decayed_recency: float  # 0–1
    complexity: float       # 0–1, normalized across repo
    churn: float            # 0–1, normalized across repo


@dataclass
class RiskScore:
    file_path: str
    score: float                        # 0–100
    hhi: float
    decayed_recency: float
    complexity: float
    churn: float
    fragility: float                    # intermediate: ownership+recency
    amplifier: float                    # intermediate: complexity+churn
    confidence: str                     # 'high' | 'medium' | 'low'
    confidence_flags: list[str]         # human-readable reasons
    top_authors: list[tuple[str, float]]  # (author, share) top 3
    living_knowledge: float             # 0–1
    last_meaningful_commit: Optional[datetime]