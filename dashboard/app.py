# dashboard/app.py

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

from .schemas import AnalyzeRequest, ChartResponse
from .chart_builder import build_treemap, build_network_graph

from github_pipeline.pipeline import (
    build_file_commit_map, PipelineConfig
)
from github_pipeline.client import RepoVisibility
from knowledge_risk import run_pipeline
from llm import OllamaClient, RiskSummarizer

logger = logging.getLogger(__name__)

# ── App setup ──────────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).parent
app       = FastAPI(title="TacitAI", version="0.1.0")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

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
    import uuid
    job_id = str(uuid.uuid4())[:8]

    _current_results[job_id] = {
        "status":   "running",
        "progress": 0,
        "message":  "Starting analysis..."
    }

    background_tasks.add_task(_run_analysis, job_id, req)
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    result = _current_results.get(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@app.get("/api/results/{job_id}")
async def results(job_id: str):
    result = _current_results.get(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    if result["status"] != "complete":
        raise HTTPException(status_code=202,
                            detail="Analysis still running")
    return result["data"]


@app.get("/api/charts/{job_id}")
async def charts(job_id: str):
    result = _current_results.get(job_id)
    if not result or result["status"] != "complete":
        raise HTTPException(status_code=404,
                            detail="Results not ready")
    treemap = build_treemap(result["scores"], result["summaries"])
    network = build_network_graph(result["scores"])
    return ChartResponse(
        treemap_json=treemap,
        network_json=network
    )


@app.get("/api/file/{job_id}")
async def file_detail(job_id: str, path: str):
    result = _current_results.get(job_id)
    if not result or result["status"] != "complete":
        raise HTTPException(status_code=404)
    match = next(
        (f for f in result["data"]["files"]
         if f["file_path"] == path),
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
        scores = run_pipeline(file_commit_map, top_n=req.top_n)

        if not scores:
            _current_results[job_id] = {
                "status":   "failed",
                "progress": 0,
                "message":  "No analyzable source files found in "
                            "this repository. Check that it contains "
                            "supported source code files (.py, .js, "
                            ".php, .java, etc.)"
            }
            return

        # Step 3 — LLM summarization
        update(70, f"Generating AI summaries for "
                   f"{len(scores)} files...")
        llm_client = OllamaClient(model=req.model)
        summarizer = RiskSummarizer(client=llm_client)
        batch      = summarizer.summarize_batch(
            scores, owner=req.owner, repo=req.repo
        )

        summary_map = {s.file_path: s for s in batch.summaries}

        # Step 4 — Assemble dashboard data
        update(90, "Assembling results...")

        files = []
        for s in scores:
            summ = summary_map.get(s.file_path)

            # Primary author info
            primary_owner = (
                s.top_authors[0][0] if s.top_authors else "unknown"
            )
            primary_share = (
                s.top_authors[0][1] if s.top_authors else 0
            )
            backup_count = max(len(s.top_authors) - 1, 0)

            files.append({
                # Core risk fields
                "file_path":        s.file_path,
                "score":            s.score,
                "hhi":              s.hhi,
                "decayed_recency":  s.decayed_recency,
                "complexity":       s.complexity,
                "churn":            s.churn,
                "fragility":        s.fragility,
                "amplifier":        s.amplifier,
                "confidence":       s.confidence,
                "confidence_flags": s.confidence_flags,
                "living_knowledge": s.living_knowledge,
                "last_meaningful_commit": (
                    s.last_meaningful_commit.date().isoformat()
                    if s.last_meaningful_commit else None
                ),

                # Ownership
                "top_authors":    [
                    {"author": a, "share": sh}
                    for a, sh in s.top_authors
                ],
                "primary_owner":  primary_owner,
                "primary_share":  primary_share,
                "backup_count":   backup_count,
                "bus_factor":     len(s.top_authors),

                # ── NEW structured LLM fields ──────────────────────
                "business_criticality": (
                    summ.business_criticality
                    if summ and not summ.failed else None
                ),
                "business_impact": (
                    summ.business_impact
                    if summ and not summ.failed else None
                ),
                "knowledge_areas": (
                    summ.knowledge_areas
                    if summ and not summ.failed else []
                ),
                "risk_drivers": (
                    summ.risk_drivers
                    if summ and not summ.failed else []
                ),
                "recommended_actions": (
                    summ.recommended_actions
                    if summ and not summ.failed else []
                ),
                "onboarding_notes": (
                    summ.onboarding_notes
                    if summ and not summ.failed else None
                ),
                "llm_model":      req.model,
                "llm_failed":     (
                    summ.failed if summ else True
                ),
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
            "avg_score":   round(
                sum(s.score for s in scores) / len(scores), 2
            ),
            "files": files
        }

        _current_results[job_id] = {
            "status":    "complete",
            "progress":  100,
            "message":   f"Done. {len(scores)} files analyzed. "
                         f"{batch.failed_count} summaries failed.",
            "data":      dashboard_data,
            "scores":    scores,
            "summaries": summary_map
        }

    except Exception as e:
        import traceback
        logger.error(f"Analysis failed:\n{traceback.format_exc()}")
        _current_results[job_id] = {
            "status":   "failed",
            "progress": 0,
            "message":  str(e)
        }