import pytest
from llm.prompts import build_user_prompt, SYSTEM_PROMPT


def test_prompt_contains_file_path(fake_risk_score):
    prompt = build_user_prompt(fake_risk_score)
    assert "src/payments/processor.py" in prompt


def test_prompt_contains_risk_score(fake_risk_score):
    prompt = build_user_prompt(fake_risk_score)
    assert "87.4" in prompt


def test_prompt_contains_top_authors(fake_risk_score):
    prompt = build_user_prompt(fake_risk_score)
    assert "alice" in prompt
    assert "bob" in prompt


def test_prompt_ownership_label_high(fake_risk_score):
    fake_risk_score.hhi = 0.9
    prompt = build_user_prompt(fake_risk_score)
    assert "highly concentrated" in prompt


def test_prompt_ownership_label_mid(fake_risk_score):
    fake_risk_score.hhi = 0.5
    prompt = build_user_prompt(fake_risk_score)
    assert "moderate" in prompt


def test_prompt_ownership_label_low(fake_risk_score):
    fake_risk_score.hhi = 0.2
    prompt = build_user_prompt(fake_risk_score)
    assert "distributed" in prompt


def test_prompt_handles_no_authors(fake_risk_score):
    fake_risk_score.top_authors = []
    prompt = build_user_prompt(fake_risk_score)
    assert "unknown" in prompt


def test_prompt_handles_none_last_commit(fake_risk_score):
    fake_risk_score.last_meaningful_commit = None
    prompt = build_user_prompt(fake_risk_score)
    assert "unknown" in prompt


def test_system_prompt_contains_json_instruction():
    assert "JSON" in SYSTEM_PROMPT


def test_system_prompt_contains_required_keys():
    for key in ["what_it_does", "domain_knowledge",
                "onboarding_notes", "recommended_action"]:
        assert key in SYSTEM_PROMPT