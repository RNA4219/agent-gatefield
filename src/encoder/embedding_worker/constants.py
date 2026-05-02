"""
Embedding Worker Constants

Default models and runtime configurations.
"""

# Default model per RUNBOOK Local Retrieval Stack
DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_DIMENSIONS = 1024
DEFAULT_RUNTIME = "llama.cpp"
FALLBACK_MODEL = "local-hash-embedding-v1"
FALLBACK_DIMENSIONS = 1536


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_DIMENSIONS",
    "DEFAULT_RUNTIME",
    "FALLBACK_MODEL",
    "FALLBACK_DIMENSIONS",
]