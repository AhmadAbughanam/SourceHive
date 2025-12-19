import os

# ------------------------------------------------------
# MYSQL CONFIGURATION
# ------------------------------------------------------
def _read_env(*keys, default=None):
    """Return the first found environment variable from provided keys."""
    for key in keys:
        if key and key in os.environ:
            return os.environ[key]
    return default


DB_CONFIG = {
    "host": _read_env("DB_HOST", "MYSQL_HOST", default="127.0.0.1"),
    "user": _read_env("DB_USER", "MYSQL_USER", default="cv"),
    "password": _read_env("DB_PASSWORD", "MYSQL_PASSWORD", default="cv@MySQL4admin"),
    "database": _read_env("DB_NAME", "MYSQL_DB", default="cv"),
    "port": int(_read_env("DB_PORT", "MYSQL_PORT", default=3306)),
    "autocommit": True,
}


# ------------------------------------------------------
# ELASTICSEARCH CONFIGURATION
# ------------------------------------------------------
ES_CONFIG = {
    # For single-node, no-auth mode
    "host": os.getenv("ES_HOST", "http://127.0.0.1:9200"),
    "index": os.getenv("ES_INDEX", "candidates"),

    # Optional settings (for future scaling)
    "timeout": int(os.getenv("ES_TIMEOUT", 30)),
    "max_retries": int(os.getenv("ES_MAX_RETRIES", 3)),
    "retry_on_timeout": True,
}


# ------------------------------------------------------
# RESUME SCORING RULES (used in scoring.py)
# ------------------------------------------------------
SCORING_RULES = {
    "critical_weight": 0.25,
    "preferred_weight": 0.3,
    "semantic_weight": 0.35
}
