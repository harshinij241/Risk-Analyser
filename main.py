from github_pipeline.pipeline import build_file_commit_map, PipelineConfig
from github_pipeline.client import RepoVisibility
from knowledge_risk import run_pipeline, to_markdown, to_json
from dotenv import load_dotenv
import os 

load_dotenv()

config = PipelineConfig(
    owner       = os.getenv("GITHUB_OWNER"),
    repo        = os.getenv("GITHUB_REPO"),
    token       = os.getenv("GITHUB_TOKEN"),
    visibility  = RepoVisibility.PUBLIC,
    max_commits = 300,
    max_files   = 1000,
)

# Fetch from GitHub
file_commit_map = build_file_commit_map(config)

# Score with risk engine
scores = run_pipeline(file_commit_map, top_n=20)

# Export
print(to_markdown(scores, repo_name="react"))