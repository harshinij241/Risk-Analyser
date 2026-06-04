from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LLMSummary:
    """
    Structured output from the LLM for one high-risk file.
    """
    file_path:        str
    risk_score:       float

    # Core LLM output
    what_it_does:     str        # what the file does
    domain_knowledge: str        # what expertise is needed
    onboarding_notes: str        # what a new dev must understand
    recommended_action: str      # one concrete action for the team

    # Metadata
    model_used:       str
    generated_at:     datetime   = field(
                                    default_factory=datetime.now
                                   )
    generation_ms:    int        = 0     # latency tracking
    confidence:       str        = ""    # passed through from RiskScore
    failed:           bool       = False # True if LLM call errored
    error_message:    Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "file_path":          self.file_path,
            "risk_score":         self.risk_score,
            "what_it_does":       self.what_it_does,
            "domain_knowledge":   self.domain_knowledge,
            "onboarding_notes":   self.onboarding_notes,
            "recommended_action": self.recommended_action,
            "model_used":         self.model_used,
            "generated_at":       self.generated_at.isoformat(),
            "generation_ms":      self.generation_ms,
            "confidence":         self.confidence,
            "failed":             self.failed,
            "error_message":      self.error_message,
        }


@dataclass
class SummaryBatch:
    """
    Collection of summaries for an entire repo analysis run.
    """
    repo:         str
    owner:        str
    summaries:    list[LLMSummary]
    generated_at: datetime = field(default_factory=datetime.now)
    model_used:   str      = ""
    total_files:  int      = 0
    failed_count: int      = 0

    @property
    def successful(self) -> list[LLMSummary]:
        return [s for s in self.summaries if not s.failed]

    @property
    def failed(self) -> list[LLMSummary]:
        return [s for s in self.summaries if s.failed]

    def to_dict(self) -> dict:
        return {
            "repo":         f"{self.owner}/{self.repo}",
            "generated_at": self.generated_at.isoformat(),
            "model_used":   self.model_used,
            "total_files":  self.total_files,
            "failed_count": self.failed_count,
            "summaries":    [s.to_dict() for s in self.summaries]
        }