from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# llm/models.py — updated LLMSummary dataclass

@dataclass
class LLMSummary:
    file_path:             str
    risk_score:            float

    # Restructured fields
    business_criticality:  str        # High | Medium | Low
    business_impact:       str        # what breaks if this file fails
    knowledge_areas:       list[str]  # specific skills required
    risk_drivers:          list[str]  # + amplifiers, - mitigators
    recommended_actions:   list[str]  # measurable actions with deadlines
    onboarding_notes:      str        # what new dev must know

    # Metadata
    model_used:            str
    generated_at:          datetime   = field(default_factory=datetime.now)
    generation_ms:         int        = 0
    confidence:            str        = ""
    failed:                bool       = False
    error_message:         Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "file_path":            self.file_path,
            "risk_score":           self.risk_score,
            "business_criticality": self.business_criticality,
            "business_impact":      self.business_impact,
            "knowledge_areas":      self.knowledge_areas,
            "risk_drivers":         self.risk_drivers,
            "recommended_actions":  self.recommended_actions,
            "onboarding_notes":     self.onboarding_notes,
            "model_used":           self.model_used,
            "generated_at":         self.generated_at.isoformat(),
            "generation_ms":        self.generation_ms,
            "confidence":           self.confidence,
            "failed":               self.failed,
            "error_message":        self.error_message,
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