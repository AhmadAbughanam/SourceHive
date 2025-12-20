from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Optional
from uuid import uuid4

from App.db_io import connect_mysql, ensure_interview_schema_mod, _serialize_row, _serialize_rows


@dataclass
class InviteResult:
    session_id: str
    created: bool
    token: Optional[str] = None
    token_hash: Optional[str] = None
    invite_sent: bool = False
    invite_last_error: Optional[str] = None


def list_sessions():
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
        return []


def get_session(session_id: str):
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return None
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
            WHERE session_id = %s
            LIMIT 1
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        return _serialize_row(row) if row else None
    except Exception:
        return None


def create_invite(user_id: int, role_name: str, candidate_name: str = "", email: str = "", expires_in_hours: int = 72):
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
            return InviteResult(session_id=existing["session_id"], created=False)

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
        return InviteResult(session_id=session_id, created=True)
    except Exception:
        return None


def _hash_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


def create_invite_with_token(
    *,
    user_id: int,
    role_name: str,
    candidate_name: str = "",
    email: str = "",
    expires_in_hours: int = 72,
    rate_limit_minutes: int = 10,
):
    """
    Create (or reuse) an interview invite with a one-time token.

    - Stores only sha256(token) in DB (token_hash).
    - Rate limits re-sends by (user_id, role_name) + invite_sent_at.
    """
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
            SELECT session_id, interview_status, invite_sent_at
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

        # Don't rotate tokens for in-progress sessions; create a new one instead.
        if existing and existing.get("interview_status") == "in_progress":
            existing = None

        # Rate-limit resends for the same (user_id, role) if we already sent recently.
        if existing and existing.get("invite_sent_at") and rate_limit_minutes:
            try:
                sent_at = existing["invite_sent_at"]
                if isinstance(sent_at, str):
                    sent_dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                else:
                    sent_dt = sent_at
                if sent_dt and (now - sent_dt.replace(tzinfo=None)).total_seconds() < rate_limit_minutes * 60:
                    cursor.close()
                    db.close()
                    return InviteResult(session_id=existing["session_id"], created=False, token=None)
            except Exception:
                pass

        raw_token = token_urlsafe(32)
        token_hash = _hash_token(raw_token)

        if existing and existing.get("session_id"):
            session_id = existing["session_id"]
            cursor.execute(
                """
                UPDATE interview_sessions
                SET token_hash = %s,
                    invite_last_error = NULL,
                    current_question = NULL,
                    llm_messages_json = NULL,
                    invite_sent_at = NULL,
                    expires_at = %s
                WHERE session_id = %s
                """,
                (token_hash, expires, session_id),
            )
            db.commit()
            cursor.close()
            db.close()
            return InviteResult(session_id=session_id, created=False, token=raw_token, token_hash=token_hash)

        session_id = uuid4().hex
        cursor.execute(
            """
            INSERT INTO interview_sessions
            (session_id, user_id, candidate_name, email, invite_email, interview_role,
             interview_status, interview_score, token_hash, invite_last_error, current_question, llm_messages_json,
             invite_sent_at, expires_at, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,'invited',0.0,%s,NULL,NULL,NULL,NULL,%s,%s)
            """,
            (
                session_id,
                int(user_id),
                (candidate_name or "").strip() or None,
                (email or "").strip() or None,
                (email or "").strip() or None,
                (role_name or "").strip(),
                token_hash,
                expires,
                now,
            ),
        )
        db.commit()
        cursor.close()
        db.close()
        return InviteResult(session_id=session_id, created=True, token=raw_token, token_hash=token_hash)
    except Exception:
        return None


def mark_invite_sent(session_id: str):
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE interview_sessions
            SET invite_sent_at = UTC_TIMESTAMP(),
                invite_last_error = NULL
            WHERE session_id = %s
            """,
            (session_id,),
        )
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        return False


def mark_invite_failed(session_id: str, error_message: str):
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE interview_sessions
            SET invite_last_error = %s
            WHERE session_id = %s
            """,
            ((error_message or "")[:2000], session_id),
        )
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        return False


def get_session_by_token(raw_token: str):
    ensure_interview_schema_mod()
    token_hash = _hash_token((raw_token or "").strip())
    if not token_hash:
        return None
    db = connect_mysql()
    if not db:
        return None
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
            WHERE token_hash = %s
            LIMIT 1
            """,
            (token_hash,),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if not row:
            return None
        return _serialize_row(row)
    except Exception:
        return None


def bulk_invite(role_name: str, top_n: int = 10, min_jd: int = 70, expires_in_hours: int = 72):
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

        candidate_name = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or ""
        email = row.get("email") or ""
        result = create_invite(
            user_id=int(row.get("id")),
            role_name=role_name,
            candidate_name=candidate_name,
            email=email,
            expires_in_hours=expires_in_hours,
        )
        if not result:
            errors += 1
            continue
        if result.created:
            created += 1
        else:
            skipped += 1
        session_ids.append(result.session_id)
        if created >= int(top_n):
            break

    return {"created": created, "skipped": skipped, "errors": errors, "session_ids": session_ids}


def mark_session_started(session_id: str):
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE interview_sessions
            SET interview_status = 'in_progress',
                started_at = COALESCE(started_at, UTC_TIMESTAMP())
            WHERE session_id = %s
            """,
            (session_id,),
        )
        updated = cursor.rowcount
        db.commit()
        if updated == 0:
            cursor.execute(
                "SELECT 1 FROM interview_sessions WHERE session_id = %s LIMIT 1",
                (session_id,),
            )
            exists = cursor.fetchone() is not None
            cursor.close()
            db.close()
            return exists
        cursor.close()
        db.close()
        return updated > 0
    except Exception:
        return False


def mark_session_completed(session_id: str, score: Optional[float] = None):
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE interview_sessions
            SET interview_status = 'completed',
                completed_at = COALESCE(completed_at, UTC_TIMESTAMP()),
                interview_score = COALESCE(%s, interview_score)
            WHERE session_id = %s
            """,
            (score, session_id),
        )
        updated = cursor.rowcount
        db.commit()
        if updated == 0:
            cursor.execute(
                "SELECT 1 FROM interview_sessions WHERE session_id = %s LIMIT 1",
                (session_id,),
            )
            exists = cursor.fetchone() is not None
            cursor.close()
            db.close()
            return exists
        cursor.close()
        db.close()
        return updated > 0
    except Exception:
        return False


def mark_session_started_by_token(raw_token: str):
    session = get_session_by_token(raw_token)
    if not session or not session.get("session_id"):
        return False
    return mark_session_started(session["session_id"])


def mark_session_completed_by_token(raw_token: str, score: Optional[float] = None):
    session = get_session_by_token(raw_token)
    if not session or not session.get("session_id"):
        return False
    return mark_session_completed(session["session_id"], score)
