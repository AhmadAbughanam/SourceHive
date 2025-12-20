import os
import sys

import streamlit as st

# Ensure repo root is importable when running `streamlit run hackathon/interview_portal.py`
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from App.interview_portal_ui import render_interview_portal  # noqa: E402

token = (st.query_params.get("token") or "").strip()
if not token:
    st.set_page_config(page_title="AI Interview", layout="centered")
    st.title("AI Interview")
    token = st.text_input("Interview token").strip()
if token:
    render_interview_portal(token)
