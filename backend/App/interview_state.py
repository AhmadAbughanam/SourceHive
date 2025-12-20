from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from App.db_io import connect_mysql, ensure_interview_schema_mod, _serialize_row


def _loads(value: Optional[str]):
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return []


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def get_session_state(session_id: str):
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return None
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT session_id, interview_status, interview_score, current_question, llm_messages_json, question_count, started_at, completed_at
            FROM interview_sessions
            WHERE session_id = %s
            LIMIT 1
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if not row:
            return None
        row = _serialize_row(row)
        row["llm_messages"] = _loads(row.pop("llm_messages_json", None))
        return row
    except Exception:
        return None


def update_session_state(
    session_id: str,
    *,
    current_question: Optional[str],
    llm_messages: list[dict[str, str]],
    question_count: Optional[int] = None,
):
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        if question_count is None:
            cursor.execute(
                """
                UPDATE interview_sessions
                SET current_question = %s,
                    llm_messages_json = %s
                WHERE session_id = %s
                """,
                (current_question, _dumps(llm_messages), session_id),
            )
        else:
            cursor.execute(
                """
                UPDATE interview_sessions
                SET current_question = %s,
                    llm_messages_json = %s,
                    question_count = %s
                WHERE session_id = %s
                """,
                (current_question, _dumps(llm_messages), int(question_count), session_id),
            )
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        return False


def append_portal_message(session_id: str, kind: str, payload: dict):
    """
    Store candidate/bot portal-visible messages in a simple JSONL text column.
    For now we keep it in llm_messages only; portal reads synthesized messages.
    """
    return True


def update_interview_score(session_id: str, score_percent: float):
    ensure_interview_schema_mod()
    db = connect_mysql()
    if not db:
        return False
    try:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE interview_sessions SET interview_score = %s WHERE session_id = %s",
            (float(score_percent), session_id),
        )
        db.commit()
        cursor.close()
        db.close()
        return True
    except Exception:
        return False
