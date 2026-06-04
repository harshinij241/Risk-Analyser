
from dataclasses import dataclass
from typing import Optional
from .models import RawFeatures


# ── Thresholds (tune these after calibration) ─────────────────────────────

MIN_COMMITS_HIGH_CONFIDENCE   = 10
MIN_COMMITS_MEDIUM_CONFIDENCE = 3
MIN_FILE_AGE_DAYS             = 30
MIN_AUTHORS_FOR_HHI_TRUST     = 2   # HHI is trivially 1.0 with one author
RECENCY_STALE_THRESHOLD_DAYS  = 365 # if ALL authors > 1yr ago, flag it
HIGH_CHURN_COMMIT_THRESHOLD   = 30  # commits in 90 days = volatile
BOT_DOMINATED_SHARE_THRESHOLD = 0.6 # if >60% commits were bots, data is thin


# ── Confidence flag definitions ────────────────────────────────────────────

@dataclass
class ConfidenceFlag:
    code: str           # machine-readable, for filtering/grouping
    message: str        # human-readable, for reports and LLM context
    severity: str       # 'warning' | 'info'


def _check_sparse_history(raw: RawFeatures) -> Optional[ConfidenceFlag]:
    if raw.total_commits < MIN_COMMITS_MEDIUM_CONFIDENCE:
        return ConfidenceFlag(
            code="SPARSE_HISTORY",
            message=f"Only {raw.total_commits} total commits — "
                    "score is based on very limited history.",
            severity="warning"
        )
    if raw.total_commits < MIN_COMMITS_HIGH_CONFIDENCE:
        return ConfidenceFlag(
            code="THIN_HISTORY",
            message=f"{raw.total_commits} commits is enough to score "
                    "but not enough for high confidence.",
            severity="info"
        )
    return None


def _check_file_age(raw: RawFeatures) -> Optional[ConfidenceFlag]:
    if raw.file_age_days < MIN_FILE_AGE_DAYS:
        return ConfidenceFlag(
            code="NEW_FILE",
            message=f"File is only {int(raw.file_age_days)} days old. "
                    "Risk may resolve naturally as more authors contribute.",
            severity="info"
        )
    return None


def _check_single_author(raw: RawFeatures) -> Optional[ConfidenceFlag]:
    """
    One author is not automatically low confidence —
    it might genuinely be a solo-owned file.
    But HHI of 1.0 from a single author is trivially true,
    so we flag it to distinguish 'concentrated by design'
    from 'concentrated by neglect'.
    """
    if raw.unique_authors < MIN_AUTHORS_FOR_HHI_TRUST:
        return ConfidenceFlag(
            code="SINGLE_AUTHOR",
            message="Only one author has made meaningful commits. "
                    "HHI is trivially 1.0 — verify if this is intentional ownership.",
            severity="info"
        )
    return None


def _check_fully_stale(raw: RawFeatures) -> Optional[ConfidenceFlag]:
    """
    If decayed recency is near 1.0, living knowledge is near zero.
    Score is technically valid but means 'nobody remembers this' —
    worth calling out explicitly.
    """
    if raw.decayed_recency >= 0.95:
        return ConfidenceFlag(
            code="FULLY_STALE",
            message="Living knowledge is near zero — no active contributor "
                    "has meaningful recent context on this file.",
            severity="warning"
        )
    return None


def _check_high_churn(raw: RawFeatures) -> Optional[ConfidenceFlag]:
    """
    Very high churn can mean the file is actively evolving,
    which makes historical ownership signals less reliable.
    """
    recent_commits = raw.churn.get('commit_count', 0)
    if recent_commits >= HIGH_CHURN_COMMIT_THRESHOLD:
        return ConfidenceFlag(
            code="HIGH_CHURN",
            message=f"{recent_commits} commits in the last 90 days. "
                    "File is highly volatile — ownership signals may lag reality.",
            severity="warning"
        )
    return None


def _check_rename_risk(raw: RawFeatures) -> Optional[ConfidenceFlag]:
    """
    If file_age_days is large but commit count is small,
    it likely has a rename in its history that broke git tracking.
    """
    if raw.file_age_days > 365 and raw.total_commits < 5:
        return ConfidenceFlag(
            code="POSSIBLE_RENAME",
            message="File appears old but has very few tracked commits. "
                    "It may have been renamed — use --follow to verify history.",
            severity="warning"
        )
    return None


def _check_complexity_unavailable(raw: RawFeatures) -> Optional[ConfidenceFlag]:
    if raw.complexity.get('method') == 'unavailable':
        return ConfidenceFlag(
            code="COMPLEXITY_UNAVAILABLE",
            message="File could not be read for complexity analysis. "
                    "Complexity factor defaulted to 0 — score may be understated.",
            severity="warning"
        )
    if raw.complexity.get('method') == 'keyword_proxy':
        return ConfidenceFlag(
            code="COMPLEXITY_ESTIMATED",
            message="Complexity computed via keyword proxy, not AST. "
                    "Python files use exact AST analysis; others are estimated.",
            severity="info"
        )
    return None


# ── Confidence level resolution ────────────────────────────────────────────

def _resolve_confidence_level(flags: list[ConfidenceFlag]) -> str:
    """
    Derive overall confidence from flag severity and count.

    high   → no warnings, any number of info flags
    medium → 1 warning, or 3+ info flags
    low    → 2+ warnings, or SPARSE_HISTORY present
    """
    warning_count = sum(1 for f in flags if f.severity == 'warning')
    info_count    = sum(1 for f in flags if f.severity == 'info')
    codes         = {f.code for f in flags}

    if 'SPARSE_HISTORY' in codes or warning_count >= 2:
        return 'low'
    if warning_count == 1 or info_count >= 3:
        return 'medium'
    return 'high'


# ── Public interface ───────────────────────────────────────────────────────

@dataclass
class ConfidenceResult:
    level: str                    # 'high' | 'medium' | 'low'
    flags: list[ConfidenceFlag]
    warning_count: int
    info_count: int

    def to_strings(self) -> list[str]:
        """Convenience — flat list of messages for reports and LLM prompts."""
        return [f.message for f in self.flags]

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "flags": [
                {"code": f.code, "message": f.message, "severity": f.severity}
                for f in self.flags
            ]
        }


def compute_confidence(raw: RawFeatures) -> ConfidenceResult:
    """
    Run all checks and return a structured confidence result.
    Order matters — checks are listed most-impactful first.
    """
    checks = [
        _check_sparse_history(raw),
        _check_file_age(raw),
        _check_fully_stale(raw),
        _check_rename_risk(raw),
        _check_high_churn(raw),
        _check_single_author(raw),
        _check_complexity_unavailable(raw),
    ]

    flags = [c for c in checks if c is not None]
    level = _resolve_confidence_level(flags)

    return ConfidenceResult(
        level=level,
        flags=flags,
        warning_count=sum(1 for f in flags if f.severity == 'warning'),
        info_count=sum(1 for f in flags if f.severity == 'info')
    )