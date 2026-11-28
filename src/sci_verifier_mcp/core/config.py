"""Configuration management using environment variables."""

import os
from pathlib import Path

# Paths
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sci_verifier_mcp"
CACHE_DB_PATH = Path(os.getenv("CACHE_DB_PATH", str(DEFAULT_CACHE_DIR / "cache.db")))
AUDIT_DB_PATH = Path(os.getenv("AUDIT_DB_PATH", str(DEFAULT_CACHE_DIR / "audit_log.sqlite")))

# API Credentials & Contacts
MP_API_KEY = os.getenv("MP_API_KEY", "")
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "sci-verifier@example.com")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")

# Timeouts & Limits
DEFAULT_HTTP_TIMEOUT = float(os.getenv("DEFAULT_HTTP_TIMEOUT", "15.0"))
DEFAULT_LEAN_TIMEOUT = int(os.getenv("DEFAULT_LEAN_TIMEOUT", "30"))
DEFAULT_SMT_TIMEOUT_MS = int(os.getenv("DEFAULT_SMT_TIMEOUT_MS", "5000"))
DEFAULT_SYMBOLIC_TIMEOUT = float(os.getenv("DEFAULT_SYMBOLIC_TIMEOUT", "10.0"))
DEFAULT_CONCURRENCY = int(os.getenv("DEFAULT_CONCURRENCY", "5"))
DEFAULT_RATE_LIMIT_INTERVAL = float(os.getenv("DEFAULT_RATE_LIMIT_INTERVAL", "0.2"))
DEFAULT_MAX_RETRIES = int(os.getenv("DEFAULT_MAX_RETRIES", "3"))
