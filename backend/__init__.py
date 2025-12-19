"""
Backend initialization and configuration.
"""
from pathlib import Path

# Backend directory
BACKEND_DIR = Path(__file__).parent

# API configuration
API_PREFIX = "/api"
API_TITLE = "SourceHive API"
API_VERSION = "1.0.0"

# CORS settings for React frontend
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
