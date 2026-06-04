# llm/summarizer.py

import json
import logging
from datetime import datetime
from knowledge_risk.models import RiskScore
from .client import OllamaClient
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .models import LLMSummary, SummaryBatch

logger = logging.getLogger(__name__)


class RiskSummarizer:
    """
    Orchestrates LLM summarization for a batch of high-risk files.
    Takes list[RiskScore] → returns SummaryBatch.
    """

    def __init__(self, client: OllamaClient):
        self.client = client

    def summarize_batch(self,
                        scores: list[RiskScore],
                        owner:  str,
                        repo:   str) -> SummaryBatch:
        """
        Summarizes all scores in the list.
        Processes sequentially — Ollama is single-threaded locally.
        Continues on individual failures rather than aborting.
        """
        self.client.validate()

        summaries = []
        total = len(scores)

        for i, score in enumerate(scores, 1):
            logger.info(
                f"[{i}/{total}] Summarizing: {score.file_path} "
                f"(risk: {score.score:.1f})"
            )
            summary = self._summarize_one(score)
            summaries.append(summary)

        failed_count = sum(1 for s in summaries if s.failed)
        if failed_count:
            logger.warning(
                f"{failed_count}/{total} summaries failed."
            )

        return SummaryBatch(
            repo         = repo,
            owner        = owner,
            summaries    = summaries,
            model_used   = self.client.model,
            total_files  = total,
            failed_count = failed_count
        )


    def _summarize_one(self, score: RiskScore) -> LLMSummary:
        """
        Summarizes a single file. Returns a failed LLMSummary
        on error rather than raising — keeps batch processing alive.
        """
        try:
            user_prompt = build_user_prompt(score)

            text, latency_ms = self.client.chat(
                system_prompt = SYSTEM_PROMPT,
                user_prompt   = user_prompt,
                metadata      = {                   # ← only change
                    "file_path":  score.file_path,
                    "risk_score": score.score,
                    "confidence": score.confidence,
                    "hhi":        score.hhi,
                }
            )

            parsed = self._parse_response(text)

            return LLMSummary(
                file_path          = score.file_path,
                risk_score         = score.score,
                what_it_does       = parsed.get("what_it_does", ""),
                domain_knowledge   = parsed.get("domain_knowledge", ""),
                onboarding_notes   = parsed.get("onboarding_notes", ""),
                recommended_action = parsed.get("recommended_action", ""),
                model_used         = self.client.model,
                generation_ms      = latency_ms,
                confidence         = score.confidence,
            )

        except Exception as e:
            logger.error(
                f"Failed to summarize {score.file_path}: {e}"
            )
            return LLMSummary(
                file_path          = score.file_path,
                risk_score         = score.score,
                what_it_does       = "",
                domain_knowledge   = "",
                onboarding_notes   = "",
                recommended_action = "",
                model_used         = self.client.model,
                confidence         = score.confidence,
                failed             = True,
                error_message      = str(e)
            )


    def _parse_response(self, text: str) -> dict:
        """
        Parses JSON from LLM response.
        Handles common model quirks like markdown fences.
        """
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]).strip()

        try:
            parsed = json.loads(clean)
            required = {
                "what_it_does", "domain_knowledge",
                "onboarding_notes", "recommended_action"
            }
            missing = required - set(parsed.keys())
            if missing:
                logger.warning(
                    f"LLM response missing keys: {missing}. "
                    "Using empty strings."
                )
            return parsed

        except json.JSONDecodeError as e:
            logger.warning(
                f"Could not parse LLM JSON response: {e}\n"
                f"Raw response: {text[:200]}"
            )
            return {
                "what_it_does":       text[:500],
                "domain_knowledge":   "",
                "onboarding_notes":   "",
                "recommended_action": ""
            }