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
from datetime import datetime, date
from decimal import Decimal
from collections import Counter
from difflib import SequenceMatcher

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


# ------------------------------------------------------
# FULL PIPELINE: PARSE DB PIPELINE
# ------------------------------------------------------

# synonym cache to reduce DB hits
_SYN_CACHE = {"ts": 0, "map": {}}
# role cache for fuzzy matching
_ROLE_CACHE = {"ts": 0, "names": []}


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


def _find_existing_candidate(
    cursor, available_cols, first_name, last_name, email, phone, selected_role
):
    """Return existing user_data id if we already have the same person for the same role."""
    required_cols = {"id", "first_name", "last_name", "email", "phone", "selected_role"}
    if not required_cols.issubset(available_cols):
        return None

    first = (first_name or "").strip()
    last = (last_name or "").strip()
    mail = (email or "").strip()
    phone_norm = (phone or "").strip()
    role = (selected_role or "").strip()

    if not (first and last and mail and phone_norm and role):
        return None

    lookup_sql = """
        SELECT id
        FROM user_data
        WHERE first_name = %s
          AND last_name = %s
          AND email = %s
          AND phone = %s
          AND selected_role = %s
        ORDER BY updated_at DESC
        LIMIT 1
    """
    cursor.execute(lookup_sql, (first, last, mail, phone_norm, role))
    row = cursor.fetchone()
    return row[0] if row else None


def process_and_sync_resume(
    path,
    first_name="",
    last_name="",
    email="",
    phone="",
    selected_role=""
):
    """Parse resume ? insert into MySQL."""
    global _SYN_CACHE

    resume_label = _build_resume_label(first_name, last_name, email, phone)

    # 1️⃣ Parse the resume
    skills_path = os.path.join(BASE_DIR, "resume_parser", "data", "hard_skills.txt")
    # Build synonym variant map from DB (canonicalization) with cache (5 min TTL)
    now_ts = time.time()
    if now_ts - _SYN_CACHE["ts"] > 300 or not _SYN_CACHE["map"]:
        try:
            db_tmp = mysql.connector.connect(**DB_CONFIG)
            cur_tmp = db_tmp.cursor(dictionary=True)
            cur_tmp.execute("SELECT token, expands_to FROM synonyms;")
            syn_rows = cur_tmp.fetchall()
            cur_tmp.close()
            db_tmp.close()
        except Exception:
            syn_rows = []

        variant_map = {}
        for row in syn_rows:
            token = parser_utils.normalize_skill_token(row.get("token"))
            canonical = parser_utils.normalize_skill_token(row.get("expands_to") or token)
            if token:
                variant_map[token] = canonical or token
            if canonical:
                variant_map.setdefault(canonical, canonical)

        _SYN_CACHE = {"ts": now_ts, "map": variant_map}
    else:
        variant_map = _SYN_CACHE["map"]

    parser = ResumeParser(path, skills_file=skills_path, synonym_map=variant_map)  # ✅ FIXED: use `path`, not `file_path`
    data = parser.get_extracted_data()

    derived_role = selected_role or data.get("parsed_role")
    canonical_role = _match_role_name(derived_role) if derived_role else None
    if not canonical_role and data.get("parsed_role"):
        canonical_role = _match_role_name(data.get("parsed_role"))

    normalized_role = canonical_role or derived_role

    # 2️⃣ Build DB connection
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Prepare JSON fields safely (raw + canonical)
    skills_hard_raw = json.dumps(data.get("skills_hard_raw") or data.get("skills_hard") or data.get("skills") or [])
    skills_soft_raw = json.dumps(data.get("skills_soft_raw") or data.get("skills_soft") or [])
    skills_hard_canon = json.dumps(data.get("skills_hard_canonical") or data.get("skills_hard") or data.get("skills") or [])
    skills_soft_canon = json.dumps(data.get("skills_soft_canonical") or data.get("skills_soft") or [])
    education_json = json.dumps({"degree": data.get("degree")}) if data.get("degree") else None
    certifications_json = json.dumps(data.get("certifications") or [])
    titles_json = json.dumps(data.get("titles") or [])
    sentences_json = json.dumps(data.get("sentences") or [])
    embedding_json = json.dumps(data.get("resume_embedding")) if data.get("resume_embedding") is not None else None

    # Build dynamic column list to stay backward-compatible
    cursor.execute("SHOW COLUMNS FROM user_data;")
    available_cols = {row[0] for row in cursor.fetchall()}

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
        "skills_hard": skills_hard_canon,  # store canonical as primary
        "skills_soft": skills_soft_canon,
        "resume_score": data.get("resume_score", 0),
        "jd_match_score": data.get("jd_match_score", 0),
        "status": "new",
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

    existing_candidate_id = _find_existing_candidate(
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

    # Prepare ES document once (used for return even if ES is down)
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
        "jd_match_score": data.get("jd_match_score", 0),
        "status": "new",
        "cv_filename": os.path.basename(path),
        "resume_display_name": resume_label,
    }

    # Cleanup
    cursor.close()
    conn.close()

    return {"db_id": candidate_id, **doc}
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
        rows = _serialize_rows(cursor.fetchall())

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

    role_keywords_query = """
        SELECT jk.keyword, jk.importance, jk.weight
        FROM jd_keywords jk
        JOIN jd_roles jr ON jk.role_id = jr.id
        WHERE jr.role_name = %s
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

        cursor.execute(role_keywords_query, (user.get("selected_role"),))
        keywords = _serialize_rows(cursor.fetchall())

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

        # compute JD keyword match
        candidate_tokens = {
            token.lower()
            for token in user["skills_hard"]
            + user["skills_soft"]
            + user["skills_hard_canonical"]
            + user["skills_soft_canonical"]
        }
        matched = []
        missing = []
        for kw in keywords:
            key = (kw["keyword"] or "").lower()
            if not key:
                continue
            if any(key in token for token in candidate_tokens):
                matched.append(kw["keyword"])
            else:
                missing.append(kw["keyword"])

        return {
            "user": user,
            "notes": notes,
            "jd_keywords": keywords,
            "jd_match": {"matched": matched, "missing": missing},
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
        cursor.execute(
            "SELECT id, role_name, jd_text, updated_at FROM jd_roles ORDER BY role_name ASC"
        )
        rows = _serialize_rows(cursor.fetchall())
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
        cursor.execute(
            "INSERT INTO jd_roles (role_name, jd_text) VALUES (%s, %s)",
            (role_name.strip(), jd_text),
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
        cursor.execute(
            "SELECT id, role_name, jd_text, updated_at FROM jd_roles WHERE id = %s",
            (role_id,),
        )
        role = cursor.fetchone()
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


def analytics_overview():
    db = connect_mysql()
    if not db:
        return {
            "status_breakdown": [],
            "applications_over_time": [],
            "top_roles": [],
            "match_distribution": [],
        }

    try:
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT status, COUNT(*) AS count FROM user_data GROUP BY status ORDER BY count DESC"
        )
        status_breakdown = _serialize_rows(cursor.fetchall())

        cursor.execute(
            """
            SELECT DATE(created_at) AS date, COUNT(*) AS count
            FROM user_data
            WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
            """
        )
        over_time = _serialize_rows(cursor.fetchall())

        cursor.execute(
            """
            SELECT selected_role AS role, COUNT(*) AS count
            FROM user_data
            GROUP BY selected_role
            ORDER BY count DESC
            LIMIT 5
            """
        )
        top_roles = _serialize_rows(cursor.fetchall())

        cursor.execute(
            """
            SELECT
                CASE
                    WHEN jd_match_score >= 80 THEN '80-100'
                    WHEN jd_match_score >= 60 THEN '60-79'
                    WHEN jd_match_score >= 40 THEN '40-59'
                    WHEN jd_match_score >= 20 THEN '20-39'
                    ELSE '0-19'
                END AS bucket,
                COUNT(*) AS count
            FROM user_data
            GROUP BY bucket
            ORDER BY bucket DESC
            """
        )
        match_distribution = _serialize_rows(cursor.fetchall())

        cursor.close()
        db.close()

        return {
            "status_breakdown": status_breakdown,
            "applications_over_time": over_time,
            "top_roles": top_roles,
            "match_distribution": match_distribution,
        }
    except Exception:
        traceback.print_exc()
        return {
            "status_breakdown": [],
            "applications_over_time": [],
            "top_roles": [],
            "match_distribution": [],
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
        total_candidates = metrics.get("total", 0) or 0
        avg_resume_score = metrics.get("avg_score") or 0

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
        formatted_top_roles = [
            {"role": row.get("role"), "count": row.get("count", 0)}
            for row in top_roles_rows
            if row.get("role")
        ]

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
                    "resume_score": row.get("resume_score"),
                    "jd_match_score": row.get("jd_match_score"),
                    "skills_hard": parsed_skills,
                    "seniority_level": row.get("seniority_level"),
                    "experience_years": row.get("experience_years"),
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
