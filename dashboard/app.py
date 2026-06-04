import os
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse

from .schemas import AnalyzeRequest, DashboardData, ChartResponse
from .chart_builder import build_treemap, build_network_graph

from github_pipeline.pipeline import (
    build_file_commit_map, PipelineConfig
)
from github_pipeline.client import RepoVisibility
from knowledge_risk import run_pipeline
from llm import OllamaClient, RiskSummarizer

logger = logging.getLogger(__name__)

# ── App setup ──────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
app        = FastAPI(title="Knowledge Risk Mapper", version="0.1.0")
templates  = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

# In-memory store for current analysis results
# In production replace with Redis or a simple SQLite store
_current_results: dict = {}


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request}
    )


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest,
                  background_tasks: BackgroundTasks):
    """
    Triggers full analysis pipeline.
    Returns immediately with a job ID.
    Frontend polls /api/status/{job_id} for progress.
    """
    import uuid
    job_id = str(uuid.uuid4())[:8]

    _current_results[job_id] = {
        "status": "running",
        "progress": 0,
        "message": "Starting analysis..."
    }

    background_tasks.add_task(
        _run_analysis, job_id, req
    )

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    """Poll this endpoint for analysis progress."""
    result = _current_results.get(job_id)
    if not result:
        raise HTTPException(status_code=404,
                            detail="Job not found")
    return result


@app.get("/api/results/{job_id}")
async def results(job_id: str):
    """Returns full DashboardData when analysis is complete."""
    result = _current_results.get(job_id)
    if not result:
        raise HTTPException(status_code=404,
                            detail="Job not found")
    if result["status"] != "complete":
        raise HTTPException(status_code=202,
                            detail="Analysis still running")
    return result["data"]


@app.get("/api/charts/{job_id}")
async def charts(job_id: str):
    """Returns Plotly chart JSON for treemap and network graph."""
    result = _current_results.get(job_id)
    if not result or result["status"] != "complete":
        raise HTTPException(status_code=404,
                            detail="Results not ready")

    scores    = result["scores"]
    summaries = result["summaries"]

    treemap  = build_treemap(scores, summaries)
    network  = build_network_graph(scores)

    return ChartResponse(
        treemap_json = treemap,
        network_json = network
    )


@app.get("/api/file/{job_id}")
async def file_detail(job_id: str, path: str):
    """Returns full detail for one file."""
    result = _current_results.get(job_id)
    if not result or result["status"] != "complete":
        raise HTTPException(status_code=404)

    data  = result["data"]
    match = next(
        (f for f in data["files"] if f["file_path"] == path),
        None
    )
    if not match:
        raise HTTPException(status_code=404,
                            detail="File not found")
    return match


# ── Background analysis task ───────────────────────────────────────────────

async def _run_analysis(job_id: str, req: AnalyzeRequest):
    try:
        def update(progress: int, message: str):
            _current_results[job_id]["progress"] = progress
            _current_results[job_id]["message"]  = message

        # Step 1 — GitHub fetch
        update(10, "Fetching commit history from GitHub...")
        config = PipelineConfig(
            owner       = req.owner,
            repo        = req.repo,
            token       = req.token,
            visibility  = RepoVisibility.PUBLIC,
            max_commits = req.max_commits,
            max_files   = req.max_files,
        )
        file_commit_map = build_file_commit_map(config)

        # Step 2 — Risk scoring
        update(50, "Scoring knowledge risk...")
        scores = run_pipeline(file_commit_map, top_n=20)

        # Step 3 — LLM summarization
        update(70, "Generating AI summaries...")
        llm_client = OllamaClient(model=req.model)
        summarizer = RiskSummarizer(client=llm_client)
        batch      = summarizer.summarize_batch(
            scores, owner=req.owner, repo=req.repo
        )

        # Step 4 — Build summary lookup
        summary_map = {
            s.file_path: s for s in batch.summaries
        }

        # Step 5 — Assemble dashboard data
        update(90, "Assembling results...")

        files = []
        for s in scores:
            summ = summary_map.get(s.file_path)
            files.append({
                "file_path":   s.file_path,
                "score":       s.score,
                "hhi":         s.hhi,
                "decayed_recency": s.decayed_recency,
                "complexity":  s.complexity,
                "churn":       s.churn,
                "confidence":  s.confidence,
                "living_knowledge": s.living_knowledge,
                "top_author":  (
                    s.top_authors[0][0]
                    if s.top_authors else "unknown"
                ),
                "last_meaningful_commit": (
                    s.last_meaningful_commit.date().isoformat()
                    if s.last_meaningful_commit else None
                ),
                "what_it_does":       (
                    summ.what_it_does if summ else ""
                ),
                "domain_knowledge":   (
                    summ.domain_knowledge if summ else ""
                ),
                "onboarding_notes":   (
                    summ.onboarding_notes if summ else ""
                ),
                "recommended_action": (
                    summ.recommended_action if summ else ""
                ),
                "confidence_flags":   s.confidence_flags
            })

        dashboard_data = {
            "owner":       req.owner,
            "repo":        req.repo,
            "total_files": len(scores),
            "high_risk":   sum(
                1 for s in scores if s.score >= 75
            ),
            "medium_risk": sum(
                1 for s in scores if 40 <= s.score < 75
            ),
            "low_risk":    sum(
                1 for s in scores if s.score < 40
            ),
            "avg_score":   (
                sum(s.score for s in scores) / len(scores)
                if scores else 0
            ),
            "files": files
        }

        _current_results[job_id] = {
            "status":    "complete",
            "progress":  100,
            "message":   "Analysis complete.",
            "data":      dashboard_data,
            "scores":    scores,
            "summaries": summary_map
        }

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        _current_results[job_id] = {
            "status":  "failed",
            "progress": 0,
            "message": str(e)
        }