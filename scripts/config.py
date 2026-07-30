"""
Shared configuration for the age assurance regulation pipeline.
All secrets come from environment variables (GitHub Secrets).
"""

import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# --- Paths ---
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SCHEMA_DIR = DATA_DIR / "schema"
SEED_DIR = DATA_DIR / "seed"
PUBLIC_DATA_DIR = ROOT_DIR / "public" / "data"

REGULATIONS_FILE = DATA_DIR / "regulations.json"
REGULATION_METADATA_FILE = DATA_DIR / "regulation_metadata.json"
OVERRIDES_FILE = DATA_DIR / "overrides.json"
SEEN_URLS_FILE = DATA_DIR / "seen_urls.json"
# Internal monitoring log for review / audit; no frontend tab consumes this directly.
NEWS_ITEMS_FILE = DATA_DIR / "news_items.json"
JURISDICTIONS_FILE = SEED_DIR / "jurisdictions.json"
MONITORING_SOURCES_FILE = SEED_DIR / "monitoring_sources.json"
MARKETS_FILE = DATA_DIR / "markets.json"
SERVICE_TYPES_FILE = SEED_DIR / "service_types.json"
MERGED_FILE = PUBLIC_DATA_DIR / "merged.json"

REGULATIONS_SCHEMA = SCHEMA_DIR / "regulations.schema.json"
OVERRIDES_SCHEMA = SCHEMA_DIR / "overrides.schema.json"
SEEN_URLS_SCHEMA = SCHEMA_DIR / "seen_urls.schema.json"
NEWS_ITEMS_SCHEMA = SCHEMA_DIR / "news_items.schema.json"

# --- Environment Variables (GitHub Secrets) ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
WECOM_WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_URL", "").strip()

# --- LLM Config ---
LLM_MODEL = "gpt-4o-mini"
CONFIDENCE_AUTO_THRESHOLD = 0.7    # >= auto-commit
CONFIDENCE_REVIEW_THRESHOLD = 0.5  # >= create PR; < discard
URGENT_CONFIDENCE_THRESHOLD = 0.85 # >= send urgent notification

# --- News API Config ---
NEWS_API_BASE = "https://newsapi.org/v2"
NEWS_LOOKBACK_HOURS = 24
NEWS_LANGUAGE = "en"
NEWS_SORT_BY = "publishedAt"
NEWS_PAGE_SIZE = 100
OFFICIAL_SOURCE_LIMIT = 20
OFFICIAL_SOURCE_LINK_LIMIT = 4
OFFICIAL_SOURCE_MIN_CANDIDATE_SCORE = 3

TRUSTED_NEWS_SOURCES = [
    "Reuters",
    "Associated Press",
    "AP News",
    "BBC News",
    "Bloomberg",
    "Financial Times",
    "The Guardian",
    "The New York Times",
    "The Wall Street Journal",
    "Politico",
    "Agence France-Presse",
    "AFP",
    "Nikkei Asia",
    "The Globe and Mail",
]

# Keyword sets for targeted search — each set is a separate API call
NEWS_KEYWORD_SETS = [
    "age assurance",
    "age verification social media",
    "underage social media ban",
    "online safety children regulation",
    "child online protection law",
    "age estimation platform",
    "minor online safety act",
    "kids online safety act",
]

# --- WeCom Config ---
WECOM_MAX_MARKDOWN_BYTES = 4000

# --- Status Weights (must match frontend) ---
STATUS_WEIGHTS = {
    "proposed": 10,
    "under_review": 20,
    "challenged": 15,
    "enjoined": 5,
    "passed": 40,
    "implementation_period": 60,
    "effective": 70,
    "enforced": 100,
    "repealed": 0,
}

ALLOWED_REGULATION_STATUSES = [
    "proposed",
    "inactive",
    "under_review",
    "passed",
    "implementation_period",
    "effective",
    "enforced",
    "challenged",
    "enjoined",
    "repealed",
]

STATUS_NORMALIZATION_MAP = {
    "breach identified": "under_review",
    "breach found": "under_review",
    "preliminary findings": "under_review",
    "investigation opened": "under_review",
    "investigation launched": "under_review",
    "consultation launched": "under_review",
    "consultation opened": "under_review",
    "entered into force": "effective",
    "comes into force": "effective",
    "in force": "effective",
}

# --- Helper Functions ---

def now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()

def load_json(filepath: Path) -> dict:
    """Load a JSON file."""
    import json
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filepath: Path, data: dict) -> None:
    """Save data as JSON with pretty formatting."""
    import json
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def normalize_regulation_status(value: Optional[str]) -> Optional[str]:
    """Map LLM/free-text lifecycle labels onto schema-allowed regulation statuses."""
    if value is None:
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in ALLOWED_REGULATION_STATUSES:
        return normalized

    alias = value.strip().lower()
    mapped = STATUS_NORMALIZATION_MAP.get(alias)
    if mapped:
        return mapped

    return None
