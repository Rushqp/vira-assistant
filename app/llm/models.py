"""Known free models per provider, with friendly names for the 🤖 AI model menu.

Free catalogs change often: these are defaults (checked October 2026) and every provider's model
can be overridden in .env (`GEMINI_MODEL`, `GROQ_MODEL`, …). The local provider lists whatever
models are pulled in Ollama at runtime.
"""

PROVIDER_NAMES = {
    "gemini": "Gemini",
    "groq": "Groq",
    "mistral": "Mistral",
    "github": "GitHub Models",
    "openrouter": "OpenRouter",
    "local": "Local",
}
KEY_NAMES = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "github": "GITHUB_TOKEN",
    "openrouter": "OPENROUTER_API_KEY",
}

# provider → [(model id, friendly name)], the first one is the default.
CATALOG: dict[str, list[tuple[str, str]]] = {
    # Google AI Studio free tier; the "-latest" aliases follow Google's newest Flash models.
    "gemini": [
        ("gemini-flash-latest", "Gemini Flash"),
        ("gemini-flash-lite-latest", "Gemini Flash-Lite"),
    ],
    # Groq free tier (production models with tool use, plus one preview model).
    "groq": [
        ("openai/gpt-oss-120b", "GPT-OSS 120B"),
        ("openai/gpt-oss-20b", "GPT-OSS 20B"),
        ("llama-3.3-70b-versatile", "Llama 3.3 70B"),
        ("qwen/qwen3.8-27b", "Qwen 3.8 27B"),
    ],
    # Mistral La Plateforme free "Experiment" plan (all models, rate limited).
    "mistral": [
        ("mistral-small-latest", "Mistral Small"),
        ("mistral-medium-latest", "Mistral Medium"),
        ("mistral-large-latest", "Mistral Large"),
    ],
    # GitHub Models (free with a GitHub token; bigger models have smaller daily quotas).
    "github": [
        ("openai/gpt-4.1-mini", "GPT-4.1 mini"),
        ("openai/gpt-4.1", "GPT-4.1"),
        ("openai/gpt-4o-mini", "GPT-4o mini"),
        ("openai/gpt-5-mini", "GPT-5 mini"),
    ],
    # OpenRouter: the free router picks a free model that supports tools for each request.
    "openrouter": [("openrouter/free", "OpenRouter Free")],
}

DEFAULT_MODELS = {provider: models[0][0] for provider, models in CATALOG.items()}


def model_name(provider: str, model: str) -> str:
    """Friendly name of a model ("GPT-OSS 120B"), or its id when it isn't in the catalog."""
    for known, name in CATALOG.get(provider, []):
        if known == model:
            return name
    return model


def model_label(provider: str, model: str) -> str:
    """ "GPT-OSS 120B · Groq", "qwen3:4b · Local"."""
    return f"{model_name(provider, model)} · {PROVIDER_NAMES.get(provider, provider)}"
