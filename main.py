# main.py

import sys
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt= "%H:%M:%S"
)
logger = logging.getLogger(__name__)


# ── LangSmith setup ────────────────────────────────────────────────────────
def _setup_langsmith():
    """
    Validates LangSmith env vars at startup.
    Warns if tracing is enabled but API key is missing.
    Silent if tracing is disabled.
    """
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"

    if not tracing:
        return

    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    project = os.getenv("LANGCHAIN_PROJECT", "knowledge-risk-mapper")

    if not api_key:
        logger.warning(
            "LangSmith tracing is enabled but LANGCHAIN_API_KEY "
            "is not set. Traces will not be sent. "
            "Get your key at https://smith.langchain.com"
        )
        return

    logger.info(
        f"LangSmith tracing enabled. "
        f"Project: '{project}'. "
        f"View traces at https://smith.langchain.com"
    )


# ── CLI mode ───────────────────────────────────────────────────────────────
def run_cli():
    from github_pipeline.pipeline import (
        build_file_commit_map, PipelineConfig
    )
    from github_pipeline.client import RepoVisibility
    from knowledge_risk import run_pipeline, to_markdown
    from llm import OllamaClient, RiskSummarizer

    # Validate required env vars
    owner = os.getenv("GITHUB_OWNER")
    repo  = os.getenv("GITHUB_REPO")
    token = os.getenv("GITHUB_TOKEN")
    model = os.getenv("LLM_MODEL", "gemma4:e4b")

    if not all([owner, repo, token]):
        logger.error(
            "Missing required env vars. "
            "Ensure GITHUB_OWNER, GITHUB_REPO, and "
            "GITHUB_TOKEN are set in your .env file."
        )
        sys.exit(1)

    logger.info(f"Analyzing {owner}/{repo}...")

    # Step 1 — GitHub fetch
    config = PipelineConfig(
        owner       = owner,
        repo        = repo,
        token       = token,
        visibility  = RepoVisibility.PUBLIC,
        max_commits = int(os.getenv("MAX_COMMITS", 300)),
        max_files   = int(os.getenv("MAX_FILES",   1000)),
    )
    file_commit_map = build_file_commit_map(config)

    # Step 2 — Risk scoring
    top_n  = int(os.getenv("TOP_N", 20))
    scores = run_pipeline(file_commit_map, top_n=top_n)
    logger.info(f"Scored {len(scores)} files.")

    # Step 3 — LLM summarization
    llm_client = OllamaClient(model=model)
    summarizer = RiskSummarizer(client=llm_client)
    batch      = summarizer.summarize_batch(
        scores = scores,
        owner  = owner,
        repo   = repo
    )

    logger.info(
        f"Summaries: {len(batch.successful)} succeeded, "
        f"{batch.failed_count} failed."
    )

    # Step 4 — Output
    print(to_markdown(scores, repo_name=f"{owner}/{repo}"))


# ── Dashboard mode ─────────────────────────────────────────────────────────
def run_dashboard():
    import uvicorn
    logger.info("Starting dashboard at http://localhost:8000")
    uvicorn.run(
        "dashboard.app:app",
        host    = "0.0.0.0",
        port    = int(os.getenv("PORT", 8000)),
        reload  = os.getenv("DEBUG", "false").lower() == "true"
    )


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _setup_langsmith()

    if "--dashboard" in sys.argv:
        run_dashboard()
    else:
        run_cli()