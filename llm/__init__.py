from .client import OllamaClient
from .summarizer import RiskSummarizer
from .models import LLMSummary, SummaryBatch
from .prompts import SYSTEM_PROMPT, build_user_prompt

__version__ = "0.1.0"


__all__ = [
    # Main entry points
    "OllamaClient",
    "RiskSummarizer",

    # Data structures
    "LLMSummary",
    "SummaryBatch",

    # Prompts (exposed for customization)
    "SYSTEM_PROMPT",
    "build_user_prompt",
]