from __future__ import annotations

"""
Minimal interview portal helpers.

The original Desktop files were empty; this module provides the project-side
equivalent so the React portal can fetch session details and display a
candidate-facing entry screen.
"""

from typing import Optional

from App.interviews import get_session


def build_portal_view(session_id: str):
    """Return safe, candidate-facing session data."""
    session = get_session(session_id)
    if not session:
        return None

    return {
        "session_id": session.get("session_id"),
        "candidate_name": session.get("candidate_name"),
        "interview_role": session.get("interview_role"),
        "interview_status": session.get("interview_status"),
        "expires_at": session.get("expires_at"),
        "started_at": session.get("started_at"),
        "completed_at": session.get("completed_at"),
    }

