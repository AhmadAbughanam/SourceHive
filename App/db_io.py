import os
import sys
import json
import mysql.connector
from elasticsearch import Elasticsearch
import subprocess
import time
from functools import lru_cache

# --- FIX PATH ISSUES (works both from App/ and project root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# --- Dual import handling ---
try:
    from App.config import DB_CONFIG, ES_CONFIG
    from App.resume_parser.parser import ResumeParser
    from App.resume_parser import utils as parser_utils
except ModuleNotFoundError:
    from config import DB_CONFIG, ES_CONFIG
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
# ELASTICSEARCH CONNECTION
# ------------------------------------------------------
def connect_es(auto_start=True, wait_seconds=6):
    """Connect to Elasticsearch; optionally try to start it if down."""
    host = ES_CONFIG.get("host", "http://127.0.0.1:9200")
    def _client():
        return Elasticsearch(
            hosts=[host],
            verify_certs=False,
            request_timeout=ES_CONFIG.get("timeout", 30),
            max_retries=ES_CONFIG.get("max_retries", 3),
            retry_on_timeout=ES_CONFIG.get("retry_on_timeout", True),
        )

    try:
        es = _client()
        if es.ping():
            return es
    except Exception:
        pass

    if not auto_start:
        print("[ES] Elasticsearch not reachable; skipping.")
        return None

    # Try to start ES via start_es.sh if present
    start_script = os.path.join(PARENT_DIR, "start_es.sh")
    if os.path.exists(start_script):
        try:
            subprocess.Popen(["bash", start_script], cwd=os.path.dirname(start_script))
            time.sleep(wait_seconds)
            es = _client()
            if es.ping():
                print("[ES] Elasticsearch started and reachable.")
                return es
            print("[ES] Elasticsearch still not reachable after start attempt.")
        except Exception as e:
            print("[ES] Failed to auto-start Elasticsearch:", e)
    else:
        print(f"[ES] start_es.sh not found at {start_script}; cannot auto-start.")

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
# ELASTICSEARCH INDEXING
# ------------------------------------------------------
def index_resume_to_es(parsed_data):
    """Index parsed résumé into Elasticsearch for fast search."""
    es = connect_es(auto_start=True)
    if not es:
        return False

    try:
        es.index(index="candidates", document=parsed_data)
        print("[ES] Resume indexed successfully.")
        return True
    except Exception as e:
        print("[ES ERROR] Failed to index resume:", e)
        traceback.print_exc()
        return False


# ------------------------------------------------------
# FULL PIPELINE: PARSE → DB → SEARCH SYNC
# ------------------------------------------------------
import os
import json
import mysql.connector
from elasticsearch import Elasticsearch
from App.config import DB_CONFIG, ES_CONFIG
from App.resume_parser.parser import ResumeParser
from App.resume_parser import utils as parser_utils

# synonym cache to reduce DB hits
_SYN_CACHE = {"ts": 0, "map": {}}


def process_and_sync_resume(
    path,
    first_name="",
    last_name="",
    email="",
    phone="",
    selected_role=""
):
    """Parse resume → insert into MySQL → sync to Elasticsearch."""

    import os, json, mysql.connector
    from urllib.parse import urlparse
    from elasticsearch import Elasticsearch
    from App.resume_parser.parser import ResumeParser
    from App.config import DB_CONFIG, ES_CONFIG

    # 1️⃣ Parse the resume
    skills_path = os.path.join(os.path.dirname(__file__), "resume_parser", "data", "skills.txt")
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
        "selected_role": selected_role,
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
        "selected_role": selected_role,
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
    }

    # 3️⃣ Sync to Elasticsearch
    es = connect_es(auto_start=True)
    if es:
        try:
            es.index(index=ES_CONFIG["index"], id=candidate_id, document=doc)
        except Exception as exc:
            print(f"[WARN] Elasticsearch sync skipped: {exc}")
    else:
        print("[WARN] Elasticsearch unavailable; skipping index.")

    # 4️⃣ Cleanup
    cursor.close()
    conn.close()

    return {"db_id": candidate_id, **doc}
# ------------------------------------------------------
# OPTIONAL SEARCH WRAPPER (for sidebar search)
# ------------------------------------------------------
def search_candidates_es(keyword):
    """Search candidates in Elasticsearch by keyword."""
    es = connect_es()
    if not es:
        return []

    try:
        query = {"query": {"multi_match": {"query": keyword, "fields": ["name", "skills", "degree", "city", "country"]}}}
        results = es.search(index="candidates", body=query)
        hits = [hit["_source"] for hit in results["hits"]["hits"]]
        print(f"[ES SEARCH] Found {len(hits)} matches for '{keyword}'.")
        return hits
    except Exception as e:
        print("[ES SEARCH ERROR]", e)
        traceback.print_exc()
        return []


# ------------------------------------------------------
# DEBUG / MANUAL RUN
# ------------------------------------------------------
if __name__ == "__main__":
    # Example usage: Parse + Insert + Sync
    test_file = "App/Uploaded_Resumes/MY_CV.pdf"
    process_and_sync_resume(test_file)

    # Example search
    results = search_candidates_es("python")
    for r in results:
        print(r)