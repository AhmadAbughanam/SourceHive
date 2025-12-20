import os
import sys
import json
import re
import mysql.connector
import subprocess
import time
from functools import lru_cache
import traceback
import csv
from io import StringIO
from datetime import datetime, date, timedelta
from decimal import Decimal
from collections import Counter
from difflib import SequenceMatcher
from uuid import uuid4

try:
    from App.document_processing import analyze_and_extract
except ModuleNotFoundError:
    from document_processing import analyze_and_extract

try:
    from App.ats_pipeline import compute_weighted_jd_match
except ModuleNotFoundError:
    from ats_pipeline import compute_weighted_jd_match

# --- FIX PATH ISSUES (works both from App/ and project root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# --- Dual import handling ---
try:
    from App.config import DB_CONFIG
    from App.resume_parser.parser import ResumeParser
    from App.resume_parser import utils as parser_utils
except ModuleNotFoundError:
    from config import DB_CONFIG
    from resume_parser.parser import ResumeParser
    from resume_parser import utils as parser_utils

# ------------------------------------------------------
# MySQL CONNECTION
# ------------------------------------------------------
def connect_mysql():
    """Establish MySQL connection using DB_CONFIG."""
    try:
        db = mysql.connector.connect(**DB_CONFIG)
        return db
    except Exception as e:
        print("[DB ERROR] Unable to connect to MySQL:", e)
        return None


# ------------------------------------------------------
# DATABASE INSERTION
# ------------------------------------------------------
def insert_resume_to_db(parsed_data):
    """Insert parsed résumé details into MySQL."""
    db = connect_mysql()
    if not db:
        return False

    try:
        cur = db.cursor()
        sql = """
            INSERT INTO candidates
            (name, email, mobile, skills, degree, city, country, experience_years)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """
        cur.execute(sql, (
            parsed_data.get("name"),
            parsed_data.get("email"),
            parsed_data.get("mobile_number"),
            json.dumps(parsed_data.get("skills", [])),
            json.dumps(parsed_data.get("degree", [])),
            parsed_data.get("city"),
            parsed_data.get("country"),
            parsed_data.get("experience_years")
        ))
        db.commit()
        cur.close()
        db.close()
        print("[DB] Resume inserted successfully.")
        return True

    except Exception as e:
        print("[DB ERROR] Failed to insert resume:", e)
        traceback.print_exc()
        return False


def _skills_data_dir():
    return os.path.join(BASE_DIR, "resume_parser", "data")


def _skills_file(kind: str):
    filename = "hard_skills.txt" if (kind or "").lower() == "hard" else "soft_skills.txt"
    return os.path.join(_skills_data_dir(), filename)


def _load_skill_set(kind: str):
    path = _skills_file(kind)
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return {parser_utils.normalize_skill_token(line) for line in fh.read().splitlines() if line.strip()}


# ------------------------------------------------------
# FULL PIPELINE: PARSE DB PIPELINE
# ------------------------------------------------------

# synonym cache to reduce DB hits
_SYN_CACHE = {"ts": 0, "variant_map": {}, "variant_keys": [], "category_map": {}}
# role cache for fuzzy matching
_ROLE_CACHE = {"ts": 0, "names": []}
_ROLE_KEYWORD_CACHE = {"ts": 0, "roles": {}}

STOPWORDS_SKILL_DISCOVERY = {
    "and", "or", "the", "a", "an", "to", "of", "in", "for", "on", "with", "as", "by", "at", "from",
    "this", "that", "these", "those", "are", "is", "was", "were", "be", "been", "being",
    "i", "we", "you", "they", "he", "she", "it", "my", "our", "your", "their",
    "responsible", "responsibilities", "duties", "summary", "profile", "experience", "skills",
    "knowledge", "ability", "strong", "good", "excellent", "working", "years", "year", "months", "month",
}


def _ensure_role_visibility_column(cursor):
    """Ensure jd_roles has is_open column, add if missing."""
    try:
        cursor.execute("SHOW COLUMNS FROM jd_roles LIKE 'is_open'")
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(
                "ALTER TABLE jd_roles ADD COLUMN is_open TINYINT(1) NOT NULL DEFAULT 1 AFTER jd_text"
            )
    except Exception:
        traceback.print_exc()


def ensure_interview_schema_mod():
    """Ensure interview_sessions table exists (idempotent)."""
    db = connect_mysql()
    if not db:
        return False

    try:
        cursor = db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS interview_sessions (
              session_id        VARCHAR(64) PRIMARY KEY,
              user_id           BIGINT NOT NULL,
              candidate_name    VARCHAR(255),
              email             VARCHAR(190),
              invite_email      VARCHAR(190),
              interview_role    VARCHAR(120),
              interview_status  ENUM('invited','in_progress','completed','expired','canceled') DEFAULT 'invited',
              interview_score   DECIMAL(5,2) DEFAULT 0.0,
              token_hash        CHAR(64),
              invite_last_error TEXT,
              current_question  TEXT,
              llm_messages_json MEDIUMTEXT,
              question_count    INT NOT NULL DEFAULT 0,
              invite_sent_at    TIMESTAMP NULL,
              expires_at        TIMESTAMP NULL,
              started_at        TIMESTAMP NULL,
              completed_at      TIMESTAMP NULL,
              created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES user_data(id) ON DELETE CASCADE,
              INDEX idx_is_user (user_id),
              INDEX idx_is_status (interview_status),
              INDEX idx_is_role (interview_role),
              INDEX idx_is_created (created_at),
              UNIQUE KEY uk_is_token_hash (token_hash)
            ) ENGINE=InnoDB
            """,
        )

        # Idempotent upgrades for existing DBs (columns + indexes).
        cursor.execute("SHOW COLUMNS FROM interview_sessions LIKE 'token_hash'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE interview_sessions ADD COLUMN token_hash CHAR(64) NULL AFTER interview_score")
        cursor.execute("SHOW COLUMNS FROM interview_sessions LIKE 'invite_last_error'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE interview_sessions ADD COLUMN invite_last_error TEXT NULL AFTER token_hash")
        cursor.execute("SHOW COLUMNS FROM interview_sessions LIKE 'current_question'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE interview_sessions ADD COLUMN current_question TEXT NULL AFTER invite_last_error")
        cursor.execute("SHOW COLUMNS FROM interview_sessions LIKE 'llm_messages_json'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE interview_sessions ADD COLUMN llm_messages_json MEDIUMTEXT NULL AFTER current_question")
        cursor.execute("SHOW COLUMNS FROM interview_sessions LIKE 'question_count'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE interview_sessions ADD COLUMN question_count INT NOT NULL DEFAULT 0 AFTER llm_messages_json")
        cursor.execute("SHOW INDEX FROM interview_sessions WHERE Key_name = 'uk_is_token_hash'")
        if not cursor.fetchone():
            cursor.execute("CREATE UNIQUE INDEX uk_is_token_hash ON interview_sessions (token_hash)")

        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        traceback.print_exc()
        return False


def fetch_interview_sessions():
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return []

    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
              session_id,
              user_id,
              candidate_name,
              email,
              invite_email,
              interview_role,
              interview_status,
              interview_score,
              invite_sent_at,
              expires_at,
              started_at,
              completed_at,
              created_at
            FROM interview_sessions
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return _serialize_rows(rows)
    except Exception:
        traceback.print_exc()
        return []


def create_interview_invite(user_id, candidate_name, role_name, email="", expires_in_hours=72):
    ensure_interview_schema_mod()
    if not user_id or not role_name:
        return None

    db = connect_mysql()
    if not db:
        return None

    now = datetime.utcnow()
    try:
        expires = now + timedelta(hours=int(expires_in_hours or 72))
    except Exception:
        expires = now + timedelta(hours=72)

    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT session_id
            FROM interview_sessions
            WHERE user_id = %s
              AND interview_role = %s
              AND interview_status IN ('invited','in_progress')
              AND (expires_at IS NULL OR expires_at > UTC_TIMESTAMP())
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (int(user_id), role_name),
        )
        existing = cursor.fetchone()
        if existing and existing.get("session_id"):
            cursor.close()
            db.close()
            return {"session_id": existing["session_id"], "created": False}

        session_id = uuid4().hex
        cursor.execute(
            """
            INSERT INTO interview_sessions
            (session_id, user_id, candidate_name, email, invite_email, interview_role,
             interview_status, interview_score, invite_sent_at, expires_at, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,'invited',0.0,%s,%s,%s)
            """,
            (
                session_id,
                int(user_id),
                (candidate_name or "").strip() or None,
                (email or "").strip() or None,
                (email or "").strip() or None,
                (role_name or "").strip(),
                now,
                expires,
                now,
            ),
        )
        db.commit()
        cursor.close()
        db.close()
        return {"session_id": session_id, "created": True}
    except Exception:
        traceback.print_exc()
        return None


def bulk_invite_best_fits(role_name, top_n=10, min_jd=70, expires_in_hours=72):
    ensure_interview_schema_mod()
    if not role_name:
        return {"created": 0, "skipped": 0, "errors": 0, "session_ids": []}

    db = connect_mysql()
    if not db:
        return {"created": 0, "skipped": 0, "errors": 0, "session_ids": []}

    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
              id,
              first_name,
              last_name,
              email,
              jd_match_score,
              resume_score
            FROM user_data
            WHERE selected_role = %s
            ORDER BY jd_match_score DESC, resume_score DESC, created_at DESC
            LIMIT %s
            """,
            (role_name, int(top_n) * 3),
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
    except Exception:
        traceback.print_exc()
        return {"created": 0, "skipped": 0, "errors": 0, "session_ids": []}

    created = 0
    skipped = 0
    errors = 0
    session_ids = []

    for row in rows or []:
        try:
            jd_score = float(row.get("jd_match_score") or 0)
        except Exception:
            jd_score = 0.0
        if jd_score < float(min_jd or 0):
            continue

        candidate_name = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or None
        email = row.get("email") or ""
        result = create_interview_invite(
            user_id=row.get("id"),
            candidate_name=candidate_name,
            role_name=role_name,
            email=email,
            expires_in_hours=expires_in_hours,
        )
        if not result:
            errors += 1
            continue
        if result.get("created"):
            created += 1
        else:
            skipped += 1
        if result.get("session_id"):
            session_ids.append(result["session_id"])
        if created >= int(top_n):
            break

    return {"created": created, "skipped": skipped, "errors": errors, "session_ids": session_ids}

def _serialize_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        try:
            return float(value)
        except Exception:
            return str(value)
    return value


def _serialize_row(row):
    if not row:
        return row
    return {key: _serialize_value(val) for key, val in row.items()}


def _serialize_rows(rows):
    return [_serialize_row(row) for row in rows or []]


def _build_resume_label(first_name, last_name, email, phone):
    parts = [
        (first_name or "").strip(),
        (last_name or "").strip(),
        (email or "").strip(),
        (phone or "").strip(),
    ]
    base = "_".join(filter(None, parts)) or "resume"
    normalized = re.sub(r"[^\w]+", "_", base).strip("_")
    return normalized or "resume"


def _append_skills_to_file(kind: str, skills):
    kind = (kind or "hard").lower()
    path = _skills_file(kind)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = _load_skill_set(kind)
    normalized = []
    for skill in skills or []:
        norm = parser_utils.normalize_skill_token(skill)
        if norm and norm not in existing:
            existing.add(norm)
            normalized.append(norm)
    if not normalized:
        return 0
    with open(path, "a", encoding="utf-8") as fh:
        for token in normalized:
            fh.write(token + "\n")
    return len(normalized)


def _get_known_role_names():
    """Return cached role names from jd_roles (cache ttl ~5 minutes)."""
    now_ts = time.time()
    if now_ts - _ROLE_CACHE["ts"] < 300 and _ROLE_CACHE["names"]:
        return _ROLE_CACHE["names"]

    db = connect_mysql()
    if not db:
        return _ROLE_CACHE["names"]

    try:
        cursor = db.cursor()
        cursor.execute("SELECT role_name FROM jd_roles")
        names = []
        for (role_name,) in cursor.fetchall():
            if role_name:
                names.append(role_name.strip())
        cursor.close()
        db.close()
        if names:
            _ROLE_CACHE["ts"] = now_ts
            _ROLE_CACHE["names"] = names
        return names
    except Exception:
        traceback.print_exc()
        return _ROLE_CACHE["names"]


def _match_role_name(role_text):
    """Fuzzy-match a role name to existing jd_roles entries."""
    if not role_text:
        return None
    cleaned = role_text.strip()
    if not cleaned:
        return None

    options = _get_known_role_names()
    if not options:
        return cleaned

    best = None
    best_score = 0.0
    for candidate in options:
        score = SequenceMatcher(
            None, cleaned.lower(), (candidate or "").lower()
        ).ratio()
        if score > best_score:
            best = candidate
            best_score = score

    if best_score >= 0.72:
        return best
    return cleaned


def _get_role_keywords(role_name):
    """Fetch JD keywords for a role with basic caching."""
    if not role_name:
        return []
    role_key = role_name.strip().lower()
    cache_entry = _ROLE_KEYWORD_CACHE["roles"].get(role_key)
    now_ts = time.time()
    if cache_entry and now_ts - cache_entry["ts"] < 300:
        return cache_entry["keywords"]

    db = connect_mysql()
    if not db:
        return []
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT jk.keyword, jk.importance, jk.weight
            FROM jd_keywords jk
            JOIN jd_roles jr ON jk.role_id = jr.id
            WHERE jr.role_name = %s
            ORDER BY jk.importance DESC, jk.keyword ASC
            """,
            (role_name,),
        )
        keywords = cursor.fetchall()
        cursor.close()
        db.close()
    except Exception:
        traceback.print_exc()
        keywords = []

    # Fallback: if HR didn't define keywords yet, derive them from jd_text using
    # known skills + synonyms so JD match can still work for prototypes.
    if not keywords:
        try:
            jd_text = _get_role_jd_text(role_name)
            variant_map, _, _ = _get_synonym_maps()
            keywords = _derive_keywords_from_jd_text(jd_text, variant_map=variant_map, max_keywords=40)
        except Exception:
            keywords = []

    _ROLE_KEYWORD_CACHE["roles"][role_key] = {"ts": now_ts, "keywords": keywords}
    return keywords


def _derive_keywords_from_jd_text(jd_text: str, *, variant_map=None, max_keywords: int = 40):
    variant_map = variant_map or {}
    jd_norm = parser_utils.normalize_skill_token(jd_text or "")
    if not jd_norm:
        return []

    known = set()
    try:
        known |= _load_skill_set("hard")
        known |= _load_skill_set("soft")
    except Exception:
        pass
    try:
        known |= set(variant_map.keys())
        known |= set(variant_map.values())
    except Exception:
        pass

    padded = f" {jd_norm} "
    keywords = []
    # Prefer multi-word phrases first for better signal.
    for token in sorted(known, key=lambda s: (s.count(" "), len(s)), reverse=True):
        token = (token or "").strip()
        if len(token) < 3:
            continue
        if len(keywords) >= max_keywords:
            break
        # Whitespace-bounded match to reduce accidental substrings.
        if re.search(rf"(^|\\s){re.escape(token)}(\\s|$)", padded):
            keywords.append({"keyword": token, "importance": "preferred", "weight": 1.0})
    return keywords


def _fetch_recent_resume_texts(role=None, limit=400):
    db = connect_mysql()
    if not db:
        return []
    try:
        cursor = db.cursor()
        if role:
            cursor.execute(
                """
                SELECT full_text_clean
                FROM user_data
                WHERE selected_role = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (role, int(limit)),
            )
        else:
            cursor.execute(
                """
                SELECT full_text_clean
                FROM user_data
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (int(limit),),
            )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        texts = []
        for (text,) in rows:
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="ignore")
            texts.append(text or "")
        return texts
    except Exception:
        traceback.print_exc()
        return []


def _get_role_jd_text(role_name):
    if not role_name:
        return ""
    db = connect_mysql()
    if not db:
        return ""
    try:
        cursor = db.cursor()
        cursor.execute("SELECT jd_text FROM jd_roles WHERE role_name = %s LIMIT 1", (role_name,))
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if row and row[0]:
            text = row[0]
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="ignore")
            return text or ""
        return ""
    except Exception:
        return ""


def discover_skill_candidates(role=None, limit=400, max_phrases=200):
    texts = _fetch_recent_resume_texts(role, limit)
    if not texts:
        return []

    known_hard = _load_skill_set("hard")
    known_soft = _load_skill_set("soft")
    known_skills = known_hard.union(known_soft)
    jd_text = _get_role_jd_text(role)
    jd_norm = parser_utils.normalize_skill_token(jd_text) if jd_text else ""

    doc_freq = {}
    examples = {}
    jd_hits = set()

    for raw in texts:
        text_norm = parser_utils.normalize_skill_token(raw or "")
        if not text_norm:
            continue

        tokens = re.findall(r"[A-Za-z0-9\\+#\\.\\-/]+", text_norm)
        tokens = [t for t in tokens if len(t) > 1 and t not in STOPWORDS_SKILL_DISCOVERY]

        candidates = set()
        for token in tokens:
            if any(ch in token for ch in "+#./-") or any(ch.isdigit() for ch in token) or len(token) <= 6:
                candidates.add(token)

        for n in (2, 3, 4):
            for idx in range(0, max(0, len(tokens) - n + 1)):
                gram = " ".join(tokens[idx:idx + n]).strip()
                if len(gram) < 6:
                    continue
                candidates.add(gram)

        for cand in candidates:
            if cand in known_skills:
                continue
            if len(cand) < 2:
                continue
            doc_freq[cand] = doc_freq.get(cand, 0) + 1
            if cand not in examples:
                snippet = (raw or "")[:160].replace("\n", " ").strip()
                examples[cand] = snippet
            if jd_norm and f" {cand} " in f" {jd_norm} ":
                jd_hits.add(cand)

    rows = []
    for cand, freq in doc_freq.items():
        has_digits = any(ch.isdigit() for ch in cand)
        has_symbols = any(ch in cand for ch in "+#./-")
        score = freq * 10 + (15 if cand in jd_hits else 0) + (5 if has_digits else 0) + (5 if has_symbols else 0)
        rows.append(
            {
                "skill": cand,
                "docs": freq,
                "in_jd": cand in jd_hits,
                "score": score,
                "example": examples.get(cand, ""),
            }
        )

    rows.sort(key=lambda item: (item["score"], item["docs"], item["skill"]), reverse=True)
    return rows[: int(max_phrases)]


def append_skills_to_dictionary(kind, skills):
    added = _append_skills_to_file(kind, skills)
    return {"added": added, "kind": (kind or "hard").lower()}


def get_skill_dictionary(kind):
    kind = (kind or "hard").lower()
    entries = sorted(_load_skill_set(kind))
    return {"kind": kind, "skills": entries}


def list_synonyms():
    db = connect_mysql()
    if not db:
        return []
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, token, expands_to, category FROM synonyms ORDER BY token ASC")
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return _serialize_rows(rows)
    except Exception:
        traceback.print_exc()
        return []


def create_synonym(token, expands_to, category="skill"):
    if not token or not expands_to:
        raise ValueError("token and expands_to are required")
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO synonyms (token, expands_to, category)
            VALUES (%s, %s, %s)
            """,
            (token.strip(), expands_to.strip(), (category or "skill").strip().lower()),
        )
        db.commit()
        cursor.close()
        db.close()
        _clear_synonym_cache()
        return True
    except Exception:
        traceback.print_exc()
        return False


def update_synonym(synonym_id, token=None, expands_to=None, category=None):
    if not synonym_id:
        raise ValueError("synonym_id is required")
    fields = []
    values = []
    if token is not None:
        fields.append("token = %s")
        values.append(token.strip())
    if expands_to is not None:
        fields.append("expands_to = %s")
        values.append(expands_to.strip())
    if category is not None:
        fields.append("category = %s")
        values.append((category or "skill").strip().lower())
    if not fields:
        return False

    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        sql = f"UPDATE synonyms SET {', '.join(fields)} WHERE id = %s"
        cursor.execute(sql, values + [int(synonym_id)])
        db.commit()
        cursor.close()
        db.close()
        _clear_synonym_cache()
        return cursor.rowcount > 0
    except Exception:
        traceback.print_exc()
        return False


def delete_synonym(synonym_id):
    if not synonym_id:
        return False
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM synonyms WHERE id = %s", (int(synonym_id),))
        db.commit()
        deleted = cursor.rowcount > 0
        cursor.close()
        db.close()
        if deleted:
            _clear_synonym_cache()
        return deleted
    except Exception:
        traceback.print_exc()
        return False


def _get_synonym_maps():
    """Return variant map, variant keys, and category map with caching."""
    global _SYN_CACHE
    now_ts = time.time()
    cached = _SYN_CACHE
    if cached["variant_map"] and now_ts - cached["ts"] < 300:
        return cached["variant_map"], cached["variant_keys"], cached["category_map"]

    variant_map = {}
    category_map = {}
    try:
        db_tmp = mysql.connector.connect(**DB_CONFIG)
        cur_tmp = db_tmp.cursor(dictionary=True)
        cur_tmp.execute("SELECT token, expands_to, category FROM synonyms;")
        syn_rows = cur_tmp.fetchall()
        cur_tmp.close()
        db_tmp.close()
    except Exception:
        syn_rows = []

    for row in syn_rows:
        token = parser_utils.normalize_skill_token(row.get("token"))
        expands_to = parser_utils.normalize_skill_token(row.get("expands_to") or token)
        if not token:
            continue
        canonical = expands_to or token
        category = (row.get("category") or "skill").strip().lower()
        variant_map[token] = canonical
        category_map[token] = category
        category_map.setdefault(canonical, category)
        variant_map.setdefault(canonical, canonical)
    variant_keys = list(variant_map.keys())
    _SYN_CACHE = {
        "ts": now_ts,
        "variant_map": variant_map,
        "variant_keys": variant_keys,
        "category_map": category_map,
    }
    return variant_map, variant_keys, category_map


def _clear_synonym_cache():
    _SYN_CACHE["ts"] = 0
    _SYN_CACHE["variant_map"] = {}
    _SYN_CACHE["variant_keys"] = []
    _SYN_CACHE["category_map"] = {}


def _normalize_phone_digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _find_existing_candidate(
    cursor, available_cols, first_name, last_name, email, phone, selected_role
):
    """Return existing user_data id if we already have the same person for the same role."""
    if "selected_role" not in available_cols:
        return None

    role = (selected_role or "").strip()
    if not role:
        return None

    email_norm = (email or "").strip().lower() if "email" in available_cols else ""
    phone_norm = _normalize_phone_digits(phone) if "phone" in available_cols else ""

    if not email_norm and not phone_norm:
        return None

    if email_norm:
        cursor.execute(
            """
            SELECT id
            FROM user_data
            WHERE selected_role = %s
              AND LOWER(email) = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (role, email_norm),
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    if phone_norm:
        phone_sql = (
            "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(phone,'-',''),' ',''),'(',''),')',''),'+',''),'.','')"
        )
        cursor.execute(
            f"""
            SELECT id
            FROM user_data
            WHERE selected_role = %s
              AND {phone_sql} = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (role, phone_norm),
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    return None


def process_and_sync_resume(
    path,
    first_name="",
    last_name="",
    email="",
    phone="",
    selected_role="",
    *,
    existing_id=None,
    preserve_status=None,
    resume_text=None,
    notes=None,
    doc_kind=None,
    extraction_method=None,
    ocr_used=None,
    extraction_error=None,
    file_mime=None,
    original_filename=None,
    force_status=None,
):
    """Parse resume & insert into MySQL."""
    resume_label = _build_resume_label(first_name, last_name, email, phone)
    skills_path = os.path.join(BASE_DIR, "resume_parser", "data", "hard_skills.txt")
    variant_map, variant_keys, category_map = _get_synonym_maps()

    extraction_payload = None
    text_override = (resume_text or "").strip()
    if not text_override:
        try:
            extraction_payload = analyze_and_extract(
                path,
                original_name=original_filename,
            )
            text_override = extraction_payload.get("text") or ""
        except Exception:
            extraction_payload = None
    if not text_override:
        text_override = parser_utils.extract_text(path)

    document_meta = extraction_payload or {
        "doc_kind": doc_kind,
        "extraction_method": extraction_method,
        "ocr_used": ocr_used,
        "extraction_error": extraction_error,
        "file_mime": file_mime,
        "details": {},
    }

    parser = ResumeParser(
        path,
        skills_file=skills_path,
        synonym_map=variant_map,
        extracted_text=text_override,
        document_meta=document_meta,
        original_filename=original_filename,
    )
    data = parser.get_extracted_data()

    derived_role = selected_role or data.get("parsed_role")
    canonical_role = _match_role_name(derived_role) if derived_role else None
    if not canonical_role and data.get("parsed_role"):
        canonical_role = _match_role_name(data.get("parsed_role"))
    normalized_role = canonical_role or derived_role

    role_keywords = _get_role_keywords(normalized_role)
    match_info = None
    if role_keywords:
        resume_tokens = (data.get("skills_hard_canonical") or []) + (data.get("skills_soft_canonical") or [])
        match_info = compute_weighted_jd_match(
            resume_tokens,
            role_keywords,
            variant_map=variant_map,
            variant_keys=variant_keys,
            category_map=category_map,
            resume_text=data.get("full_text_clean") or "",
        )

    status_value = force_status or preserve_status or "new"

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SHOW COLUMNS FROM user_data;")
    available_cols = {row[0] for row in cursor.fetchall()}

    skills_hard_raw = json.dumps(data.get("skills_hard_raw") or data.get("skills_hard") or data.get("skills") or [])
    skills_soft_raw = json.dumps(data.get("skills_soft_raw") or data.get("skills_soft") or [])
    skills_hard_canon = json.dumps(data.get("skills_hard_canonical") or data.get("skills_hard") or data.get("skills") or [])
    skills_soft_canon = json.dumps(data.get("skills_soft_canonical") or data.get("skills_soft") or [])
    education_json = json.dumps({"degree": data.get("degree")}) if data.get("degree") else None
    certifications_json = json.dumps(data.get("certifications") or [])
    titles_json = json.dumps(data.get("titles") or [])
    sentences_json = json.dumps(data.get("sentences") or [])
    embedding_json = json.dumps(data.get("resume_embedding")) if data.get("resume_embedding") is not None else None

    base_fields = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "address": data.get("address"),
        "selected_role": normalized_role,
        "parsed_role": data.get("parsed_role"),
        "education_json": education_json,
        "experience_years": data.get("experience_years", 0),
        "skills_hard": skills_hard_canon,
        "skills_soft": skills_soft_canon,
        "resume_score": data.get("resume_score", 0),
        "jd_match_score": (match_info or {}).get("score", data.get("jd_match_score", 0)),
        "status": status_value,
        "cv_filename": os.path.basename(path),
    }

    optional_fields = {
        "skills_hard_raw": skills_hard_raw,
        "skills_soft_raw": skills_soft_raw,
        "skills_hard_canonical": skills_hard_canon,
        "skills_soft_canonical": skills_soft_canon,
        "full_text_clean": data.get("full_text_clean"),
        "resume_sentences": sentences_json,
        "resume_embedding": embedding_json,
        "certifications_json": certifications_json,
        "job_titles_json": titles_json,
        "seniority_level": data.get("seniority_level"),
        "notes": notes,
    }

    insert_fields = []
    insert_values = []
    for col, val in base_fields.items():
        if col in available_cols:
            insert_fields.append(col)
            insert_values.append(val)
    for col, val in optional_fields.items():
        if col in available_cols:
            insert_fields.append(col)
            insert_values.append(val)

    assignment_parts = [f"{field} = %s" for field in insert_fields]
    if "updated_at" in available_cols:
        assignment_parts.append("updated_at = NOW()")

    existing_candidate_id = existing_id or _find_existing_candidate(
        cursor, available_cols, first_name, last_name, email, phone, normalized_role
    )

    if existing_candidate_id:
        sql = f"UPDATE user_data SET {', '.join(assignment_parts)} WHERE id = %s"
        cursor.execute(sql, tuple(insert_values + [existing_candidate_id]))
        conn.commit()
        candidate_id = existing_candidate_id
    else:
        placeholders = ", ".join(["%s"] * len(insert_fields))
        sql = f"INSERT INTO user_data ({', '.join(insert_fields)}) VALUES ({placeholders})"
        cursor.execute(sql, tuple(insert_values))
        conn.commit()
        candidate_id = cursor.lastrowid

    doc = {
        "user_id": candidate_id,
        "name": f"{first_name} {last_name}".strip(),
        "email": email,
        "phone": phone,
        "address": data.get("address"),
        "city": data.get("city"),
        "country": data.get("country"),
        "selected_role": normalized_role,
        "parsed_role": data.get("parsed_role"),
        "skills_hard": json.loads(skills_hard_canon),
        "skills_soft": json.loads(skills_soft_canon),
        "skills_hard_raw": json.loads(skills_hard_raw),
        "skills_soft_raw": json.loads(skills_soft_raw),
        "education_json": json.loads(education_json) if education_json else None,
        "certifications": data.get("certifications") or [],
        "job_titles": data.get("titles") or [],
        "seniority_level": data.get("seniority_level"),
        "experience_years": data.get("experience_years", 0),
        "full_text_clean": data.get("full_text_clean"),
        "sentences": data.get("sentences"),
        "resume_embedding": data.get("resume_embedding"),
        "resume_score": data.get("resume_score", 0),
        "jd_match_score": (match_info or {}).get("score", data.get("jd_match_score", 0)),
        "status": status_value,
        "cv_filename": os.path.basename(path),
        "resume_display_name": resume_label,
        "doc_metadata": document_meta,
        "jd_match_details": match_info,
    }

    cursor.close()
    conn.close()
    return {"db_id": candidate_id, **doc}


def reprocess_candidate(candidate_id):
    """Reload candidate resume from disk, re-run parsing + scoring, and update DB."""
    db = connect_mysql()
    if not db:
        raise ValueError("Database unavailable")

    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, first_name, last_name, email, phone, selected_role, cv_filename
        FROM user_data
        WHERE id = %s
        LIMIT 1
        """,
        (candidate_id,),
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        db.close()
        raise ValueError("Candidate not found")

    resume_name = row.get("cv_filename")
    file_path = os.path.join(BASE_DIR, "Uploaded_Resumes", resume_name) if resume_name else None
    if not file_path or not os.path.exists(file_path):
        cursor.close()
        db.close()
        raise FileNotFoundError("Original resume file not found on disk.")

    payload = analyze_and_extract(file_path, original_name=resume_name)
    result = process_and_sync_resume(
        path=file_path,
        first_name=row.get("first_name", ""),
        last_name=row.get("last_name", ""),
        email=row.get("email", ""),
        phone=row.get("phone", ""),
        selected_role=row.get("selected_role") or "",
        existing_id=row.get("id"),
        resume_text=payload.get("text"),
        doc_kind=payload.get("doc_kind"),
        extraction_method=payload.get("extraction_method"),
        ocr_used=payload.get("ocr_used"),
        extraction_error=payload.get("extraction_error"),
        file_mime=payload.get("file_mime"),
        original_filename=resume_name,
    )
    cursor.close()
    db.close()
    return result

def _build_applications_filters(
    status=None,
    role=None,
    start_date=None,
    end_date=None,
    keyword=None,
):
    clauses = ["1=1"]
    params = []

    if status:
        clauses.append("status = %s")
        params.append(status)

    if role:
        clauses.append("selected_role = %s")
        params.append(role)

    if start_date:
        clauses.append("DATE(created_at) >= %s")
        params.append(start_date)

    if end_date:
        clauses.append("DATE(created_at) <= %s")
        params.append(end_date)

    if keyword:
        like_keyword = f"%{keyword}%"
        clauses.append(
            "("
            "CONCAT(IFNULL(first_name,''),' ',IFNULL(last_name,'')) LIKE %s "
            "OR email LIKE %s OR selected_role LIKE %s)"
        )
        params.extend([like_keyword, like_keyword, like_keyword])

    return " AND ".join(clauses), params


def fetch_applications(
    status=None,
    role=None,
    start_date=None,
    end_date=None,
    keyword=None,
    sort_by="created_at",
    sort_dir="desc",
    page=1,
    page_size=20,
):
    db = connect_mysql()
    if not db:
        return {"rows": [], "total": 0, "stats": {}}

    allowed_sort = {
        "created_at": "created_at",
        "updated_at": "updated_at",
        "resume_score": "resume_score",
        "jd_match_score": "jd_match_score",
    }
    sort_column = allowed_sort.get(sort_by, "created_at")
    sort_direction = "ASC" if sort_dir and sort_dir.lower() == "asc" else "DESC"

    filters_sql, filter_params = _build_applications_filters(
        status=status,
        role=role,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
    )

    offset = max(page - 1, 0) * page_size

    query = f"""
        SELECT
            id,
            CONCAT(IFNULL(first_name,''), ' ', IFNULL(last_name,'')) AS name,
            email,
            phone,
            selected_role,
            status,
            created_at,
            updated_at,
            resume_score,
            jd_match_score,
            skills_hard,
            skills_soft,
            skills_hard_canonical,
            skills_soft_canonical,
            full_text_clean,
            (SELECT COUNT(*) FROM user_feedback uf WHERE uf.user_id = user_data.id) AS notes_count
        FROM user_data
        WHERE {filters_sql}
        ORDER BY {sort_column} {sort_direction}
        LIMIT %s OFFSET %s
    """

    count_query = f"SELECT COUNT(*) FROM user_data WHERE {filters_sql}"

    status_summary_query = """
        SELECT status, COUNT(*) AS count
        FROM user_data
        GROUP BY status
    """

    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(count_query, filter_params)
        total = cursor.fetchone()["COUNT(*)"]

        cursor.execute(
            query,
            [*filter_params, page_size, offset],
        )
        raw_rows = cursor.fetchall() or []

        def _decode_json_list(value):
            if not value:
                return []
            if isinstance(value, list):
                return value
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
            except Exception:
                return []
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, str):
                return [parsed]
            return []

        variant_map, variant_keys, category_map = _get_synonym_maps()
        for row in raw_rows:
            role_name = row.get("selected_role") or ""
            jd_keywords = _get_role_keywords(role_name) if role_name else []
            jd_keyword_count = len(jd_keywords or [])
            resume_tokens = _decode_json_list(row.get("skills_hard_canonical")) + _decode_json_list(
                row.get("skills_soft_canonical")
            )
            if not resume_tokens:
                resume_tokens = _decode_json_list(row.get("skills_hard")) + _decode_json_list(row.get("skills_soft"))

            resume_text = row.get("full_text_clean") or ""
            match_details = compute_weighted_jd_match(
                resume_tokens,
                _serialize_rows(jd_keywords),
                variant_map=variant_map,
                variant_keys=variant_keys,
                category_map=category_map,
                resume_text=resume_text,
            )
            jd_match = {
                "score": row.get("jd_match_score") or 0,
                "matched_count": 0,
                "missing_count": 0,
                "matched_preview": [],
                "missing_preview": [],
                "jd_keyword_count": jd_keyword_count,
                "reason": "",
            }
            if match_details:
                jd_match.update(
                    {
                        "score": match_details.get("score", 0),
                        "matched_count": len(match_details.get("matched") or []),
                        "missing_count": len(match_details.get("missing") or []),
                        "matched_preview": (match_details.get("matched") or [])[:6],
                        "missing_preview": (match_details.get("missing") or [])[:6],
                    }
                )
            else:
                if not role_name:
                    jd_match["reason"] = "No role selected"
                elif jd_keyword_count == 0:
                    jd_match["reason"] = "No JD keywords saved for this role"
                elif not resume_tokens and not (resume_text or "").strip():
                    jd_match["reason"] = "No extracted text yet (OCR needed?)"
                else:
                    jd_match["reason"] = "Not enough data to score"
            row["jd_match"] = jd_match

            # drop heavy fields from list response
            row.pop("full_text_clean", None)
            row.pop("skills_hard", None)
            row.pop("skills_soft", None)
            row.pop("skills_hard_canonical", None)
            row.pop("skills_soft_canonical", None)

        rows = _serialize_rows(raw_rows)

        cursor.execute(status_summary_query)
        status_summary = cursor.fetchall()
        stats = {row["status"]: row["count"] for row in status_summary}

        cursor.close()
        db.close()
        return {"rows": rows, "total": total, "stats": stats}
    except Exception:
        traceback.print_exc()
        return {"rows": [], "total": 0, "stats": {}}


def export_applications_csv(filters):
    db = connect_mysql()
    if not db:
        return ""

    filters_sql, filter_params = _build_applications_filters(**filters)
    query = f"""
        SELECT
            id,
            CONCAT(IFNULL(first_name,''), ' ', IFNULL(last_name,'')) AS name,
            email,
            phone,
            selected_role,
            status,
            DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_at,
            DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%s') AS updated_at,
            resume_score,
            jd_match_score
        FROM user_data
        WHERE {filters_sql}
        ORDER BY created_at DESC
    """
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(query, filter_params)
        rows = cursor.fetchall()
        cursor.close()
        db.close()
    except Exception:
        traceback.print_exc()
        return ""

    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "name",
            "email",
            "phone",
            "selected_role",
            "status",
            "created_at",
            "updated_at",
            "resume_score",
            "jd_match_score",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def fetch_candidate_detail(user_id):
    db = connect_mysql()
    if not db:
        return None

    query = """
        SELECT *
        FROM user_data
        WHERE id = %s
        LIMIT 1
    """
    notes_query = """
        SELECT id, comment, updated_at
        FROM user_feedback
        WHERE user_id = %s AND comment IS NOT NULL AND comment <> ''
        ORDER BY updated_at DESC
    """

    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(query, (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.close()
            db.close()
            return None

        # decode JSON fields safely
        def _decode_json(value):
            if not value:
                return []
            if isinstance(value, list):
                return value
            try:
                return json.loads(value)
            except Exception:
                return []

        user["skills_hard"] = _decode_json(user.get("skills_hard"))
        user["skills_soft"] = _decode_json(user.get("skills_soft"))
        user["skills_hard_canonical"] = _decode_json(user.get("skills_hard_canonical"))
        user["skills_soft_canonical"] = _decode_json(user.get("skills_soft_canonical"))

        cursor.execute(notes_query, (user_id,))
        notes = [_serialize_row(row) for row in cursor.fetchall()]

        cursor.close()
        db.close()

        user = _serialize_row(user)
        resume_label = _build_resume_label(
            user.get("first_name", ""),
            user.get("last_name", ""),
            user.get("email", ""),
            user.get("phone", "")
        )
        user["resume_display_name"] = resume_label

        keywords = _serialize_rows(_get_role_keywords(user.get("selected_role")))
        variant_map, variant_keys, category_map = _get_synonym_maps()
        resume_tokens = (
            (user["skills_hard_canonical"] or user["skills_hard"])
            + (user["skills_soft_canonical"] or user["skills_soft"])
        )
        match_details = compute_weighted_jd_match(
            resume_tokens,
            keywords,
            variant_map=variant_map,
            variant_keys=variant_keys,
            category_map=category_map,
            resume_text=user.get("full_text_clean") or "",
        )

        return {
            "user": user,
            "notes": notes,
            "jd_keywords": keywords,
            "jd_match": match_details or {"matched": [], "missing": [], "score": 0, "total": 0},
        }
    except Exception:
        traceback.print_exc()
        return None


def update_candidate_status(user_id, status):
    db = connect_mysql()
    if not db:
        return False

    query = "UPDATE user_data SET status = %s WHERE id = %s"
    try:
        cursor = db.cursor()
        cursor.execute(query, (status, user_id))
        db.commit()
        cursor.close()
        db.close()
        return cursor.rowcount > 0
    except Exception:
        traceback.print_exc()
        return False


def add_candidate_note(user_id, comment):
    if not comment:
        return False
    db = connect_mysql()
    if not db:
        return False

    query = "INSERT INTO user_feedback (user_id, comment) VALUES (%s, %s)"
    try:
        cursor = db.cursor()
        cursor.execute(query, (user_id, comment))
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        traceback.print_exc()
        return False


def update_candidate_resume_score(user_id: int, resume_score):
    db = connect_mysql()
    if not db:
        return False
    try:
        score = float(resume_score)
    except Exception:
        return False
    if score < 0:
        score = 0.0
    if score > 100:
        score = 100.0

    try:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE user_data SET resume_score=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (score, int(user_id)),
        )
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        traceback.print_exc()
        return False


def delete_candidate(user_id):
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM user_data WHERE id = %s", (user_id,))
        db.commit()
        deleted = cursor.rowcount > 0
        cursor.close()
        db.close()
        return deleted
    except Exception:
        traceback.print_exc()
        return False


def delete_candidate_note(note_id):
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM user_feedback WHERE id = %s", (note_id,))
        db.commit()
        deleted = cursor.rowcount > 0
        cursor.close()
        db.close()
        return deleted
    except Exception:
        traceback.print_exc()
        return False


def delete_all_candidate_notes(user_id):
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM user_feedback WHERE user_id = %s", (user_id,))
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        traceback.print_exc()
        return False


def fetch_roles():
    db = connect_mysql()
    if not db:
        return []
    try:
        cursor = db.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, role_name, jd_text, is_open, updated_at FROM jd_roles ORDER BY role_name ASC"
            )
            rows = _serialize_rows(cursor.fetchall())
        except mysql.connector.Error:
            cursor.execute(
                "SELECT id, role_name, jd_text, updated_at FROM jd_roles ORDER BY role_name ASC"
            )
            rows = _serialize_rows(cursor.fetchall())
            for row in rows:
                row["is_open"] = 1
        cursor.close()
        db.close()
        return rows
    except Exception:
        traceback.print_exc()
        return []


def create_role(role_name, jd_text=""):
    db = connect_mysql()
    if not db:
        return None
    try:
        cursor = db.cursor()
        trimmed_name = (role_name or "").strip()
        if not trimmed_name:
            return None
        try:
            cursor.execute(
                "INSERT INTO jd_roles (role_name, jd_text, is_open) VALUES (%s, %s, %s)",
                (trimmed_name, jd_text, 1),
            )
        except mysql.connector.Error:
            cursor.execute(
                "INSERT INTO jd_roles (role_name, jd_text) VALUES (%s, %s)",
                (trimmed_name, jd_text),
            )
        role_id = cursor.lastrowid
        db.commit()
        cursor.close()
        db.close()
        # refresh role cache so new role is available immediately
        _ROLE_CACHE["ts"] = 0
        return role_id
    except Exception:
        traceback.print_exc()
        return None


def fetch_role_detail(role_id):
    db = connect_mysql()
    if not db:
        return None
    try:
        cursor = db.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, role_name, jd_text, is_open, updated_at FROM jd_roles WHERE id = %s",
                (role_id,),
            )
        except mysql.connector.Error:
            cursor.execute(
                "SELECT id, role_name, jd_text, updated_at FROM jd_roles WHERE id = %s",
                (role_id,),
            )
        row = cursor.fetchone()
        if row and "is_open" not in row:
            row["is_open"] = 1
        role = row
        if not role:
            cursor.close()
            db.close()
            return None
        role = _serialize_row(role)

        cursor.execute(
            """
            SELECT id, keyword, importance, weight
            FROM jd_keywords
            WHERE role_id = %s
            ORDER BY importance DESC, weight DESC
            """,
            (role_id,),
        )
        keywords = _serialize_rows(cursor.fetchall())
        cursor.close()
        db.close()
        return {"role": role, "keywords": keywords}
    except Exception:
        traceback.print_exc()
        return None


def update_role_jd(role_id, jd_text):
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE jd_roles SET jd_text = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (jd_text, role_id),
        )
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        traceback.print_exc()
        return False


def upsert_role_keyword(role_id, keyword, importance="preferred", weight=1.0, keyword_id=None):
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        if keyword_id:
            cursor.execute(
                """
                UPDATE jd_keywords
                SET keyword=%s, importance=%s, weight=%s
                WHERE id=%s AND role_id=%s
                """,
                (keyword, importance, weight, keyword_id, role_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO jd_keywords (role_id, keyword, importance, weight)
                VALUES (%s, %s, %s, %s)
                """,
                (role_id, keyword, importance, weight),
            )
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        traceback.print_exc()
        return False


def delete_role_keyword(keyword_id):
    db = connect_mysql()
    if not db:
        return False


def set_role_visibility(role_id, is_open=True):
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        _ensure_role_visibility_column(cursor)
        cursor.execute(
            "UPDATE jd_roles SET is_open=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (1 if is_open else 0, role_id),
        )
        db.commit()
        cursor.close()
        db.close()
        _ROLE_CACHE["ts"] = 0
        return True
    except Exception:
        traceback.print_exc()
        return False
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM jd_keywords WHERE id = %s", (keyword_id,))
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        traceback.print_exc()
        return False


def _parse_date_yyyy_mm_dd(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def _daterange_days(start_d: date, end_d: date):
    cur = start_d
    while cur <= end_d:
        yield cur
        cur = cur + timedelta(days=1)


def analytics_overview(start_date=None, end_date=None, role=None):
    db = connect_mysql()
    if not db:
        return {
            "scope": {"start_date": None, "end_date": None, "role": role},
            "totals": {"total_applications": 0, "avg_jd_match_score": 0, "avg_resume_score": 0},
            "status_breakdown": [],
            "applications_over_time": [],
            "top_roles": [],
            "jd_match_distribution": [],
            "experience_distribution": [],
            "doc_kind_breakdown": [],
        }

    try:
        cursor = db.cursor(dictionary=True)

        start_d = _parse_date_yyyy_mm_dd(start_date)
        end_d = _parse_date_yyyy_mm_dd(end_date)
        today = date.today()
        if not end_d:
            end_d = today
        if not start_d:
            start_d = end_d - timedelta(days=89)

        # Build scoped WHERE clause (date + role)
        where = ["created_at >= %s", "created_at < DATE_ADD(%s, INTERVAL 1 DAY)"]
        params = [start_d.isoformat(), end_d.isoformat()]
        if role:
            where.append("selected_role = %s")
            params.append(role)
        where_sql = "WHERE " + " AND ".join(where)

        cursor.execute(
            f"""
            SELECT
              COUNT(*) AS total_applications,
              AVG(jd_match_score) AS avg_jd_match_score,
              AVG(resume_score) AS avg_resume_score
            FROM user_data
            {where_sql}
            """,
            tuple(params),
        )
        totals_row = cursor.fetchone() or {}
        totals = {
            "total_applications": int(totals_row.get("total_applications") or 0),
            "avg_jd_match_score": float(totals_row.get("avg_jd_match_score") or 0),
            "avg_resume_score": float(totals_row.get("avg_resume_score") or 0),
        }

        cursor.execute(
            f"SELECT status, COUNT(*) AS count FROM user_data {where_sql} GROUP BY status ORDER BY count DESC",
            tuple(params),
        )
        status_breakdown = _serialize_rows(cursor.fetchall())

        cursor.execute(
            f"""
            SELECT DATE(created_at) AS date, COUNT(*) AS count
            FROM user_data
            {where_sql}
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
            """,
            tuple(params),
        )
        over_time_rows = _serialize_rows(cursor.fetchall())
        # Fill missing days for nicer charting
        over_time_map = {(row.get("date") or ""): int(row.get("count") or 0) for row in over_time_rows}
        over_time = []
        for day in _daterange_days(start_d, end_d):
            day_str = day.isoformat()
            over_time.append({"date": day_str, "count": over_time_map.get(day_str, 0)})

        cursor.execute(
            f"""
            SELECT selected_role AS role, COUNT(*) AS count
            FROM user_data
            {where_sql}
            GROUP BY selected_role
            ORDER BY count DESC
            LIMIT 10
            """,
            tuple(params),
        )
        top_roles = _serialize_rows(cursor.fetchall())

        cursor.execute(
            f"""
            SELECT
                CASE
                    WHEN jd_match_score >= 90 THEN '90-100'
                    WHEN jd_match_score >= 80 THEN '80-89'
                    WHEN jd_match_score >= 70 THEN '70-79'
                    WHEN jd_match_score >= 60 THEN '60-69'
                    WHEN jd_match_score >= 50 THEN '50-59'
                    WHEN jd_match_score >= 40 THEN '40-49'
                    WHEN jd_match_score >= 30 THEN '30-39'
                    WHEN jd_match_score >= 20 THEN '20-29'
                    WHEN jd_match_score >= 10 THEN '10-19'
                    ELSE '0-9'
                END AS bucket,
                COUNT(*) AS count
            FROM user_data
            {where_sql}
            GROUP BY bucket
            ORDER BY bucket DESC
            """,
            tuple(params),
        )
        jd_match_distribution = _serialize_rows(cursor.fetchall())

        cursor.execute(
            f"SELECT experience_years FROM user_data {where_sql} AND experience_years IS NOT NULL",
            tuple(params),
        )
        exp_rows = cursor.fetchall() or []
        exp_buckets = Counter()
        for row in exp_rows:
            val = row.get("experience_years")
            try:
                years = float(val or 0)
            except Exception:
                years = 0.0
            if years <= 0:
                exp_buckets["0"] += 1
            elif years < 3:
                exp_buckets["1-2"] += 1
            elif years < 6:
                exp_buckets["3-5"] += 1
            elif years < 10:
                exp_buckets["6-9"] += 1
            else:
                exp_buckets["10+"] += 1
        experience_distribution = [{"bucket": k, "count": exp_buckets.get(k, 0)} for k in ["0", "1-2", "3-5", "6-9", "10+"]]

        doc_kind_breakdown = []
        try:
            cursor.execute(
                f"""
                SELECT
                  JSON_UNQUOTE(JSON_EXTRACT(doc_metadata, '$.doc_kind')) AS doc_kind,
                  COUNT(*) AS count
                FROM user_data
                {where_sql}
                GROUP BY doc_kind
                ORDER BY count DESC
                """,
                tuple(params),
            )
            doc_kind_breakdown = _serialize_rows(cursor.fetchall())
        except Exception:
            doc_kind_breakdown = []

        cursor.close()
        db.close()

        return {
            "scope": {"start_date": start_d.isoformat(), "end_date": end_d.isoformat(), "role": role or ""},
            "totals": totals,
            "status_breakdown": status_breakdown,
            "applications_over_time": over_time,
            "top_roles": top_roles,
            "jd_match_distribution": jd_match_distribution,
            "experience_distribution": experience_distribution,
            "doc_kind_breakdown": doc_kind_breakdown,
        }
    except Exception:
        traceback.print_exc()
        return {
            "scope": {"start_date": None, "end_date": None, "role": role},
            "totals": {"total_applications": 0, "avg_jd_match_score": 0, "avg_resume_score": 0},
            "status_breakdown": [],
            "applications_over_time": [],
            "top_roles": [],
            "jd_match_distribution": [],
            "experience_distribution": [],
            "doc_kind_breakdown": [],
        }


def get_dashboard_insights(top_skills=5, top_roles=5, recent=5):
    """Return overview metrics from MySQL for the dashboard."""
    default_response = {
        "total_candidates": 0,
        "avg_resume_score": 0,
        "top_skills": [],
        "top_roles": [],
        "recent_uploads": [],
    }

    db = connect_mysql()
    if not db:
        return default_response

    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS total, AVG(resume_score) AS avg_score FROM user_data")
        metrics = cursor.fetchone() or {}
        total_candidates = int(metrics.get("total", 0) or 0)
        avg_resume_score = float(metrics.get("avg_score") or 0)

        cursor.execute(
            """
            SELECT selected_role AS role, COUNT(*) AS count
            FROM user_data
            WHERE selected_role IS NOT NULL AND selected_role <> ''
            GROUP BY selected_role
            ORDER BY count DESC
            LIMIT %s
            """,
            (top_roles,),
        )
        top_roles_rows = cursor.fetchall()
        formatted_top_roles = []
        for row in top_roles_rows or []:
            role_name = row.get("role")
            if not role_name:
                continue
            count_val = row.get("count", 0) or 0
            if isinstance(count_val, Decimal):
                count_val = float(count_val)
            if isinstance(count_val, float) and count_val.is_integer():
                count_val = int(count_val)
            formatted_top_roles.append({"role": role_name, "count": count_val})

        cursor.execute("SELECT skills_hard FROM user_data WHERE skills_hard IS NOT NULL")
        skill_counter = Counter()
        for row in cursor.fetchall():
            raw = row.get("skills_hard")
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            try:
                skills = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                continue
            if isinstance(skills, str):
                skills = [skills]
            for skill in skills or []:
                skill = (skill or "").strip()
                if skill:
                    skill_counter[skill] += 1
        formatted_top_skills = [
            {"skill": name, "count": count}
            for name, count in skill_counter.most_common(top_skills)
        ]

        cursor.execute(
            """
            SELECT
                id AS user_id,
                CONCAT(IFNULL(first_name,''), ' ', IFNULL(last_name,'')) AS name,
                email,
                phone,
                selected_role,
                parsed_role,
                resume_score,
                jd_match_score,
                skills_hard,
                seniority_level,
                experience_years
            FROM user_data
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (recent,),
        )
        recent_rows = cursor.fetchall()
        recent_uploads = []
        for row in recent_rows:
            raw_skills = row.get("skills_hard")
            if isinstance(raw_skills, bytes):
                raw_skills = raw_skills.decode("utf-8", errors="ignore")
            try:
                parsed_skills = json.loads(raw_skills) if raw_skills else []
            except Exception:
                parsed_skills = []
            recent_uploads.append(
                {
                    "user_id": row.get("user_id"),
                    "name": (row.get("name") or "").strip(),
                    "email": row.get("email"),
                    "phone": row.get("phone"),
                    "selected_role": row.get("selected_role"),
                    "parsed_role": row.get("parsed_role"),
                      "resume_score": float(row.get("resume_score") or 0),
                      "jd_match_score": float(row.get("jd_match_score") or 0),
                    "skills_hard": parsed_skills,
                    "seniority_level": row.get("seniority_level"),
                      "experience_years": float(row.get("experience_years") or 0),
                }
            )

        return {
            "total_candidates": total_candidates,
            "avg_resume_score": round(avg_resume_score or 0, 2),
            "top_skills": formatted_top_skills,
            "top_roles": formatted_top_roles,
            "recent_uploads": recent_uploads,
        }
    except Exception:
        traceback.print_exc()
        return default_response
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        db.close()


# ------------------------------------------------------
# DEBUG / MANUAL RUN
# ------------------------------------------------------
if __name__ == "__main__":
    # Example usage: Parse + Insert
    test_file = os.path.join(BASE_DIR, "Uploaded_Resumes", "MY_CV.pdf")
    process_and_sync_resume(test_file)
