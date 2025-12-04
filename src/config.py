"""
Configuration helpers for database and data directory settings.

Loads environment variables from a .env file in the project root.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/insider_data",
)
# Default to the extracted data root from the prompt guidance.
DATA_DIR = Path(os.getenv("DATA_DIR", "data/extracted"))


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create a singleton SQLAlchemy engine using the configured DATABASE_URL."""
    return create_engine(DATABASE_URL)
