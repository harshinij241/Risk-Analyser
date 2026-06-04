# tests/conftest.py  (add to existing file)

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from knowledge_risk.models import RiskScore
from github_pipeline.client import GitHubClient
from llm.models import LLMSummary


# ── GitHub fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def fake_token():
    return "ghp_testtoken123"


@pytest.fixture
def github_client(fake_token):
    return GitHubClient(token=fake_token, max_concurrency=2)


@pytest.fixture
def fake_repo_response():
    return {
        "default_branch": "main",
        "full_name": "testowner/testrepo",
        "private": False
    }


@pytest.fixture
def fake_commit_response():
    return [
        {
            "sha": "abc123",
            "author": {"login": "alice"},
            "commit": {
                "author": {
                    "name": "Alice",
                    "email": "alice@company.com",
                    "date": "2024-06-01T10:00:00Z"
                },
                "message": "fix payment logic"
            },
            "files": [
                {
                    "filename": "src/payments/processor.py",
                    "additions": 45,
                    "deletions": 10
                }
            ]
        }
    ]


@pytest.fixture
def fake_tree_response():
    return {
        "repository": {
            "defaultBranchRef": {"name": "main"},
            "object": {
                "entries": [
                    {
                        "path": "src/payments/processor.py",
                        "type": "blob",
                        "object": {"byteSize": 4200}
                    },
                    {
                        "path": "src/auth/middleware.py",
                        "type": "blob",
                        "object": {"byteSize": 1800}
                    },
                    {
                        "path": "package-lock.json",
                        "type": "blob",
                        "object": {"byteSize": 95000}
                    },
                    {
                        "path": "src/",
                        "type": "tree",   # should be excluded
                        "object": None
                    }
                ]
            }
        }
    }


# ── LLM fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def fake_risk_score():
    return RiskScore(
        file_path             = "src/payments/processor.py",
        score                 = 87.4,
        hhi                   = 0.89,
        decayed_recency       = 0.71,
        complexity            = 0.68,
        churn                 = 0.44,
        fragility             = 0.58,
        amplifier             = 1.32,
        confidence            = "high",
        confidence_flags      = [],
        top_authors           = [("alice", 0.82), ("bob", 0.18)],
        living_knowledge      = 0.29,
        last_meaningful_commit= datetime(2024, 7, 3)
    )


@pytest.fixture
def fake_llm_response():
    return """{
  "what_it_does": "Handles payment transaction processing.",
  "domain_knowledge": "Requires knowledge of Stripe API.",
  "onboarding_notes": "Understand the webhook retry logic.",
  "recommended_action": "Schedule knowledge transfer with alice."
}"""


@pytest.fixture
def mock_ollama_client(fake_llm_response):
    client = MagicMock()
    client.model = "gemma4:e4b"
    client.chat.return_value = (fake_llm_response, 1200)
    client.validate.return_value = None
    return client