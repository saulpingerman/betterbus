"""Repository paths and API keys.

Keys are read from the git-ignored `.env` file at the repository root (see `.env.example`).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
RAW = DATA / "raw"

load_dotenv(REPO / ".env")


def key(name):
    """Return the API key `name` from the environment or `.env`, or raise naming the missing key."""
    value = os.environ.get(name)
    if not value:
        raise KeyError(f"{name} is not set; add it to {REPO / '.env'} (see .env.example)")
    return value
