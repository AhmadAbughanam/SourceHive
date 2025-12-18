import os

# ------------------------------------------------------
# MYSQL CONFIGURATION
# ------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "user": os.getenv("DB_USER", "cv"),
    "password": os.getenv("DB_PASSWORD", "cv@MySQL4admin"),
    "database": os.getenv("DB_NAME", "cv"),
    "port": int(os.getenv("DB_PORT", 3306)),
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