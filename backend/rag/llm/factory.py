"""
Factory for creating LLM provider instances.

The factory centralizes provider selection so the rest of the RAG
pipeline depends only on the BaseLLM interface.

Supported providers (via RAG_LLM_PROVIDER):
  groq   -- Groq (groq.com) with optional dual-key load balancing.
             Uses RAG_GROQ_API_KEY (primary) and RAG_GROQ_API_KEY_2
             (secondary, optional). Both fall back to GROQ_API_KEY.
             When two keys are provided a MultiKeyGroqClient is returned,
             giving 2x effective rate limit with automatic failover.
  ollama -- Local Ollama server (RAG_OLLAMA_BASE_URL required).
  grok   -- xAI Grok (grok.com) API.
"""

from __future__ import annotations

from rag.config import settings
from rag.llm.base import BaseLLM
from rag.llm.grok_client import GrokClient
from rag.llm.groq_client import GroqClient
from rag.llm.multi_key_client import MultiKeyGroqClient
from rag.llm.ollama_client import OllamaClient


class LLMFactory:
    """
    Factory class for creating LLM providers.
    """

    @staticmethod
    def create() -> BaseLLM:
        """
        Create and return the configured LLM provider.

        Returns
        -------
        BaseLLM
            Configured LLM implementation.

        Raises
        ------
        ValueError
            If the configured provider is unsupported or keys are missing.
        """
        provider = settings.llm_provider.lower()

        match provider:

            case "groq":
                return LLMFactory._create_groq()

            case "ollama":
                return OllamaClient()

            case "grok":
                api_key = getattr(settings, "grok_api_key", None)
                if not api_key:
                    raise ValueError("Grok API key is not configured.")
                return GrokClient(api_key=api_key)

            case _:
                raise ValueError(
                    f"Unsupported LLM provider: '{provider}'. "
                    f"Supported: groq, ollama, grok."
                )

    @staticmethod
    def _create_groq() -> BaseLLM:
        """
        Create a Groq client, using dual-key load balancing when two
        API keys are configured.

        Key resolution order:
          1. RAG_GROQ_API_KEY   (RAG-specific primary key)
          2. GROQ_API_KEY       (main app key — reused if no RAG key set)

        Secondary key (enables round-robin + failover):
          RAG_GROQ_API_KEY_2

        Returns
        -------
        GroqClient | MultiKeyGroqClient
            Single-key client or multi-key load balancer.

        Raises
        ------
        ValueError
            If no primary Groq API key is configured.
        """
        primary_key = settings.groq_api_key
        secondary_key = settings.groq_api_key_2
        model = settings.groq_model

        if not primary_key:
            raise ValueError(
                "Groq API key is not configured for the RAG module. "
                "Set GROQ_API_KEY (shared with main app) or "
                "RAG_GROQ_API_KEY (RAG-specific) in your .env file."
            )

        # Collect all valid keys (non-empty strings)
        keys = [k for k in [primary_key, secondary_key] if k]

        if len(keys) == 1:
            from rag.utils import get_logger
            get_logger(__name__).info(
                "LLMFactory: Groq single-key mode (model='%s'). "
                "Set RAG_GROQ_API_KEY_2 to enable dual-key load balancing.",
                model,
            )
            return GroqClient(api_key=keys[0], model_name=model)

        # Two keys — use round-robin multi-key client
        from rag.utils import get_logger
        get_logger(__name__).info(
            "LLMFactory: Groq dual-key mode (model='%s'). "
            "Requests will be distributed 50/50 across both keys with "
            "automatic failover on rate limit.",
            model,
        )
        return MultiKeyGroqClient(api_keys=keys, model_name=model)