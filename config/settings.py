"""
Cerebro configuration — loads from environment variables with sensible defaults.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Database
DB_PATH = os.getenv("CEREBRO_DB_PATH", str(PROJECT_ROOT / "data" / "cerebro.db"))

# Claude API
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# API Server
API_HOST = os.getenv("CEREBRO_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("CEREBRO_API_PORT", "8000"))

# Frontend URL (for CORS)
FRONTEND_URL = os.getenv("CEREBRO_FRONTEND_URL", "http://localhost:3000")

# Ingestion intervals (seconds)
GDELT_INTERVAL = int(os.getenv("CEREBRO_GDELT_INTERVAL", "900"))  # 15 min
