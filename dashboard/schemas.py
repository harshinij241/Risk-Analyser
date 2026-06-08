# dashboard/schemas.py

from pydantic import BaseModel
from typing import Optional


class AuthorShare(BaseModel):          # ← must come first
    author: str
    share:  float


class FileRiskResponse(BaseModel):     # ← uses AuthorShare
    file_path:              str
    score:                  float
    confidence:             str
    hhi:                    float
    decayed_recency:        float
    complexity:             float
    churn:                  float
    fragility:              float
    amplifier:              float
    living_knowledge:       float
    top_authors:            list[AuthorShare]
    last_meaningful_commit: Optional[str]
    confidence_flags:       list[str]

    # Structured LLM fields
    business_criticality:   Optional[str]       = None
    business_impact:        Optional[str]       = None
    knowledge_areas:        Optional[list[str]] = None
    risk_drivers:           Optional[list[str]] = None
    recommended_actions:    Optional[list[str]] = None
    onboarding_notes:       Optional[str]       = None
    llm_model:              Optional[str]       = None


class RepoSummaryResponse(BaseModel):
    owner:          str
    repo:           str
    total_files:    int
    high_risk:      int
    medium_risk:    int
    low_risk:       int
    avg_score:      float
    files:          list[FileRiskResponse]


class AnalyzeRequest(BaseModel):
    owner:       str
    repo:        str
    token:       str
    max_files:   int = 1000
    max_commits: int = 300
    model:       str = "gemma4:e4b"
    top_n:       int = 20


class ChartResponse(BaseModel):
    treemap_json: str
    network_json: str