import pytest
from datetime import datetime
from llm.models import LLMSummary, SummaryBatch


def make_summary(failed=False):
    return LLMSummary(
        file_path         = "src/foo.py",
        risk_score        = 80.0,
        what_it_does      = "handles payments",
        domain_knowledge  = "stripe knowledge",
        onboarding_notes  = "read the docs",
        recommended_action= "pair program",
        model_used        = "gemma4:e4b",
        failed            = failed,
        error_message     = "timeout" if failed else None
    )


def test_summary_to_dict_has_all_keys():
    s = make_summary()
    d = s.to_dict()
    for key in ["file_path", "risk_score", "what_it_does",
                "domain_knowledge", "onboarding_notes",
                "recommended_action", "model_used",
                "generated_at", "failed"]:
        assert key in d


def test_failed_summary_has_error_message():
    s = make_summary(failed=True)
    assert s.error_message == "timeout"


def test_batch_successful_excludes_failed():
    batch = SummaryBatch(
        repo="repo", owner="owner",
        summaries=[make_summary(False), make_summary(True)]
    )
    assert len(batch.successful) == 1
    assert len(batch.failed) == 1


def test_batch_to_dict_serializes_correctly():
    batch = SummaryBatch(
        repo="repo", owner="owner",
        summaries=[make_summary()],
        model_used="gemma4:e4b",
        total_files=1
    )
    d = batch.to_dict()
    assert d["repo"] == "owner/repo"
    assert len(d["summaries"]) == 1
