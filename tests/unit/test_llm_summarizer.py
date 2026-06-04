import pytest
from unittest.mock import MagicMock, patch
from llm.summarizer import RiskSummarizer
from llm.models import LLMSummary


def test_parse_clean_json(mock_ollama_client, fake_llm_response):
    summarizer = RiskSummarizer(client=mock_ollama_client)
    parsed = summarizer._parse_response(fake_llm_response)
    assert parsed["what_it_does"] == \
        "Handles payment transaction processing."
    assert parsed["recommended_action"] == \
        "Schedule knowledge transfer with alice."


def test_parse_strips_markdown_fences(mock_ollama_client):
    summarizer = RiskSummarizer(client=mock_ollama_client)
    fenced = '```json\n{"what_it_does": "foo", ' \
             '"domain_knowledge": "bar", ' \
             '"onboarding_notes": "baz", ' \
             '"recommended_action": "qux"}\n```'
    parsed = summarizer._parse_response(fenced)
    assert parsed["what_it_does"] == "foo"


def test_parse_handles_invalid_json(mock_ollama_client):
    summarizer = RiskSummarizer(client=mock_ollama_client)
    result = summarizer._parse_response("not json at all {{")
    # Falls back gracefully
    assert "what_it_does" in result


def test_parse_handles_missing_keys(mock_ollama_client):
    summarizer = RiskSummarizer(client=mock_ollama_client)
    partial = '{"what_it_does": "foo"}'
    result = summarizer._parse_response(partial)
    assert result["what_it_does"] == "foo"
    # Missing keys become empty strings
    assert result.get("domain_knowledge", "") == ""


def test_summarize_one_returns_correct_summary(
        mock_ollama_client, fake_risk_score):
    summarizer = RiskSummarizer(client=mock_ollama_client)
    result = summarizer._summarize_one(fake_risk_score)
    assert not result.failed
    assert result.file_path == "src/payments/processor.py"
    assert result.risk_score == 87.4
    assert result.what_it_does != ""


def test_summarize_one_returns_failed_on_error(
        mock_ollama_client, fake_risk_score):
    mock_ollama_client.chat.side_effect = RuntimeError("timeout")
    summarizer = RiskSummarizer(client=mock_ollama_client)
    result = summarizer._summarize_one(fake_risk_score)
    assert result.failed
    assert result.error_message == "timeout"


def test_summarize_batch_calls_validate_once(
        mock_ollama_client, fake_risk_score):
    summarizer = RiskSummarizer(client=mock_ollama_client)
    summarizer.summarize_batch(
        [fake_risk_score, fake_risk_score],
        owner="testowner", repo="testrepo"
    )
    mock_ollama_client.validate.assert_called_once()


def test_summarize_batch_continues_on_failure(
        mock_ollama_client, fake_risk_score):
    # First call fails, second succeeds
    mock_ollama_client.chat.side_effect = [
        RuntimeError("fail"),
        ("{\"what_it_does\": \"ok\", "
         "\"domain_knowledge\": \"ok\", "
         "\"onboarding_notes\": \"ok\", "
         "\"recommended_action\": \"ok\"}", 500)
    ]
    summarizer = RiskSummarizer(client=mock_ollama_client)
    batch = summarizer.summarize_batch(
        [fake_risk_score, fake_risk_score],
        owner="testowner", repo="testrepo"
    )
    assert batch.total_files == 2
    assert batch.failed_count == 1
    assert len(batch.successful) == 1