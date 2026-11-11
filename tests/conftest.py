import pytest


@pytest.fixture(autouse=True)
def clear_llm_keys(monkeypatch):
    """Keep unit tests offline and deterministic."""
    names = (
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "GROQ_MODEL",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
        for index in range(16):
            monkeypatch.delenv(f"{name}_P{index}", raising=False)
