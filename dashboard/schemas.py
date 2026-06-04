# dashboard/schemas.py

from pydantic import BaseModel
from typing import Optional


class FileRiskSchema(BaseModel):
    file_path:              str
    score:                  float
    hhi:                    float
    decayed_recency:        float
    complexity:             float
    churn:                  float
    confidence:             str
    living_knowledge:       float
    top_author:             str
    last_meaningful_commit: Optional[str]
    what_it_does:           str
    domain_knowledge:       str
    onboarding_notes:       str
    recommended_action:     str
    confidence_flags:       list[str]


class DashboardData(BaseModel):
    owner:         str
    repo:          str
    total_files:   int
    high_risk:     int       # score >= 75
    medium_risk:   int       # score 40-74
    low_risk:      int       # score < 40
    avg_score:     float
    files:         list[FileRiskSchema]


class ChartResponse(BaseModel):
    treemap_json:  str       # Plotly JSON
    network_json:  str       # Plotly JSON


class AnalyzeRequest(BaseModel):
    owner:       str
    repo:        str
    token:       str
    max_files:   int = 1000
    max_commits: int = 300
    model:       str = "gemma4:e4b"