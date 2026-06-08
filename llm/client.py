# llm/client.py

import os
import time
import logging
from typing import Optional
import ollama
from langsmith import traceable

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Thin wrapper around the Ollama Python client.
    Handles model validation, timeouts, and error recovery.
    All LLM calls go through here — nothing else touches ollama directly.
    """

    def __init__(self,
                 model:       str = "gemma4:e4b",
                 host:        str = "http://localhost:11434",
                 timeout_s:   int = 120,
                 max_retries: int = 2):

        self.model       = model
        self.host        = host
        self.timeout_s   = timeout_s
        self.max_retries = max_retries
        self._client     = ollama.Client(host=host)

        # LangSmith is enabled only if env vars are set
        # If not configured, @traceable is a no-op
        self._tracing = (
            os.getenv("LANGCHAIN_TRACING_V2", "false").lower()
            == "true"
        )
        if self._tracing:
            logger.info("LangSmith tracing enabled.")


    # ── Startup check ──────────────────────────────────────────────────────

    def validate(self) -> None:
        """
        Checks Ollama is running and the model is pulled.
        Call once at startup — fail fast before processing any files.
        """
        try:
            models    = self._client.list()
            available = [m.model for m in models.models]
        except Exception:
            raise RuntimeError(
                "Ollama is not running. Start it with: ollama serve\n"
                f"Then pull the model: ollama pull {self.model}"
            )

        matched = any(
            self.model.split(":")[0] in m
            for m in available
        )
        if not matched:
            raise RuntimeError(
                f"Model '{self.model}' is not pulled.\n"
                f"Run: ollama pull {self.model}\n"
                f"Available models: {available}"
            )

        logger.info(f"Ollama validated. Model '{self.model}' is ready.")


    # ── Core chat interface ────────────────────────────────────────────────

    @traceable(
        name     = "summarize_file",
        run_type = "llm",
        tags     = ["ollama", "risk-summary"]
    )
    def chat(self,
             system_prompt: str,
             user_prompt:   str,
             metadata:      Optional[dict] = None) -> tuple[str, int]:
        """
        Sends a chat request to Ollama.
        Returns (response_text, latency_ms).
        Retries on transient failures.

        metadata dict is passed from summarizer per file:
          {file_path, risk_score, confidence, hhi}
        LangSmith picks it up automatically via @traceable.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        for attempt in range(self.max_retries + 1):
            try:
                start = time.time()

                response = self._client.chat(
                    model    = self.model,
                    messages = messages,
                    options  = {
                        "temperature": 0.2,
                        "num_predict": 2048,
                        "top_p":       0.9,
                    }
                )

                latency_ms = int((time.time() - start) * 1000)
                text       = response.message.content.strip()

                logger.debug(
                    f"LLM response in {latency_ms}ms "
                    f"({len(text)} chars)"
                )
                return text, latency_ms

            except ollama.ResponseError as e:
                logger.warning(
                    f"Ollama response error (attempt {attempt+1}): {e}"
                )
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                else:
                    raise

            except Exception as e:
                logger.error(f"Unexpected LLM error: {e}")
                raise

        raise RuntimeError("LLM chat failed after retries")