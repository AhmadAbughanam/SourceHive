	# 1.	Add summary metric cards (step 1)
	# 2.	Replace filters with the new dynamic filter bar (step 2)
	# 3.	Add a toggle for Card/Table view (step 3)
	# 4.	Add Plotly charts at the bottom (step 5)
import streamlit as st
import mysql.connector
import pandas as pd
import json
import time
import os
from config import DB_CONFIG, SCORING_RULES
from db_io import process_and_sync_resume

# --------------------------------------------------------------------
# 🎨 Custom Styles & Page Setup
# --------------------------------------------------------------------
st.set_page_config(
    page_title="HR Resume Analyzer",
    layout="wide",
    page_icon=""
)

st.markdown("""
    <style>
    /* Sidebar + body */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        padding-top: 1rem;
    }
    [data-testid="stAppViewContainer"] {
        background-color: #f9fafb;
    }
    /* Headers */
    h1, h2, h3, h4 {color: #1e293b; font-family: 'Inter', sans-serif;}
    /* Buttons */
    .stButton>button {
        background-color:#2563eb;
        color:white;
        border-radius:8px;
        font-weight:500;
        transition:0.2s;
    }
    .stButton>button:hover {
        background-color:#1d4ed8;
        transform: scale(1.02);
    }
    /* Cards */
    .metric-card {
        background-color:white;
        border-radius:12px;
        padding:1rem;
        box-shadow:0 1px 3px rgba(0,0,0,0.1);
        text-align:center;
    }
    .metric-value {
        font-size:1.5rem;
        font-weight:700;
        color:#2563eb;
    }
    .metric-label {
        font-size:0.9rem;
        color:#475569;
    }
    </style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------
# 🧠 DB UTILITIES
# --------------------------------------------------------------------
def get_conn():
    return mysql.connector.connect(**DB_CONFIG)

def fetch_df(query, params=None):
    conn = get_conn()
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def execute(query, params=None):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(query, params or ())
    conn.commit()
    cursor.close()
    conn.close()


# --------------------------------------------------------------------
# MAIN DASHBOARD UI (Header + Overview)
# --------------------------------------------------------------------
import base64

logo_path = os.path.join("Logo", "Globitel.png")

# Safely encode image to Base64
if os.path.exists(logo_path):
    with open(logo_path, "rb") as f:
        logo_base64 = base64.b64encode(f.read()).decode("utf-8")
else:
    logo_base64 = ""

st.markdown(f"""
<div style="
    background:linear-gradient(90deg, #2563eb 0%, #1e40af 100%);
    color:white;
    padding:1.2rem 1.5rem;
    border-radius:10px;
    margin-bottom:1rem;
    display:flex;
    justify-content:space-between;
    align-items:center;">
    <div style="display:flex; align-items:center; gap:1rem;">
        {'<img src="data:image/png;base64,' + logo_base64 + '" width="55" height="55" style="border-radius:8px; background:white; padding:4px;">' if logo_base64 else ''}
        <div style="font-size:1.5rem; font-weight:600;">HR Admin Dashboard</div>
    </div>
    <div style="font-size:0.95rem;">Logged in as <b>admin@resume-analyzer</b></div>
</div>
""", unsafe_allow_html=True)
# Fetch core stats
try:
    df_stats = fetch_df("""
        SELECT
            COUNT(*) AS total,
            SUM(status='shortlisted') AS shortlisted,
            SUM(status='hired') AS hired,
            AVG(resume_score) AS avg_score
        FROM user_data;
    """)
    total = int(df_stats["total"].iloc[0] or 0)
    shortlisted = int(df_stats["shortlisted"].iloc[0] or 0)
    hired = int(df_stats["hired"].iloc[0] or 0)
    avg_score = round(df_stats["avg_score"].iloc[0] or 0, 1)
except Exception:
    total, shortlisted, hired, avg_score = 0, 0, 0, 0

# Summary Metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f"<div class='metric-card'><div class='metric-value'>{total}</div><div class='metric-label'>Total Applicants</div></div>", unsafe_allow_html=True)
with col2:
    st.markdown(f"<div class='metric-card'><div class='metric-value'>{shortlisted}</div><div class='metric-label'>Shortlisted</div></div>", unsafe_allow_html=True)
with col3:
    st.markdown(f"<div class='metric-card'><div class='metric-value'>{hired}</div><div class='metric-label'>Hired</div></div>", unsafe_allow_html=True)
with col4:
    st.markdown(f"<div class='metric-card'><div class='metric-value'>{avg_score}%</div><div class='metric-label'>Avg Evaluation Score</div></div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Tab Navigation
tabs = st.tabs([
    "Applicants",
    "Roles & JD Keywords",
    "Skill Synonyms",
    "Scoring Rules",
    "Audit Log"
])
# ====================================================================
# TAB 1 — APPLICANTS DASHBOARD (v6 — Clickable Grid + JD Insights)
# ====================================================================
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import plotly.express as px

with tabs[0]:
    st.markdown("<h2 style='margin-bottom:0;'>Applicant Management</h2>", unsafe_allow_html=True)
    df = fetch_df("SELECT * FROM user_data ORDER BY created_at DESC;")

    if df.empty:
        st.info("No applicants yet — start by uploading one below.")
        st.stop()

    # -------------------------------------------------------
    #  KPI CARDS
    # -------------------------------------------------------
    c1, c2, c3, c4, c5 = st.columns(5)
    total = len(df)
    shortlisted = (df["status"] == "shortlisted").sum()
    hired = (df["status"] == "hired").sum()
    rejected = (df["status"] == "rejected").sum()
    avg_score = round(df["resume_score"].mean(), 1)
    avg_jd = round(df["jd_match_score"].mean(), 1)

    c1.metric("Total", total)
    c2.metric("Shortlisted", shortlisted)
    c3.metric("Hired", hired)
    c4.metric("Avg JD Match", f"{avg_jd}%")
    c5.metric("Avg Eval Score", f"{avg_score}%")

    st.markdown("---")

# -------------------------------------------------------
#  ADVANCED FILTERS
# -------------------------------------------------------
    import datetime
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

    c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1, 1, 1, 1, 1.5])
    with c1:
        role_filter = st.selectbox(
            "Role",
            ["All"] + sorted(df["selected_role"].dropna().unique().tolist()),
            key="role_filter_v6",
        )
    with c2:
        status_filter = st.multiselect(
            "Status",
            sorted(df["status"].dropna().unique().tolist()),
            default=[],
            key="status_filter_v6",
        )
    with c3:
        eval_range = st.slider("Eval Score %", 0, 100, (0, 100), 5, key="eval_range_v6")
    with c4:
        jd_range = st.slider("JD Match %", 0, 100, (0, 100), 5, key="jd_range_v6")
    with c5:
        # --- Date range filter restored ---
        try:
            date_min = pd.to_datetime(df["created_at"].min()).date()
            date_max = pd.to_datetime(df["created_at"].max()).date()
        except Exception:
            date_min, date_max = datetime.date(2024, 1, 1), datetime.date.today()

        date_filter = st.date_input(
            "🗓 Date Range",
            (date_min, date_max),
            key="date_filter_v6"
        )
    with c6:
        keyword = st.text_input(
            "🔍 Search by Name / Skill / Note",
            key="kw_v6"
        ).lower().strip()

    # -------------------------------------------------------
    # Apply filters
    # -------------------------------------------------------
    filtered = df.copy()

    if role_filter != "All":
        filtered = filtered[filtered["selected_role"] == role_filter]

    if status_filter:
        filtered = filtered[filtered["status"].isin(status_filter)]

    filtered = filtered[
        (filtered["resume_score"].between(eval_range[0], eval_range[1]))
        & (filtered["jd_match_score"].between(jd_range[0], jd_range[1]))
    ]

    # --- Date range filter logic ---
    if isinstance(date_filter, (list, tuple)) and len(date_filter) == 2:
        start, end = date_filter
        filtered = filtered[
            (pd.to_datetime(filtered["created_at"]).dt.date >= start)
            & (pd.to_datetime(filtered["created_at"]).dt.date <= end)
        ]

    # --- Keyword filter (includes skills) ---
    if keyword:
        def match_any(text):
            return isinstance(text, str) and keyword in text.lower()

        def match_skills(skills_json):
            try:
                skills = json.loads(skills_json) if isinstance(skills_json, str) else []
                return any(keyword in s.lower() for s in skills)
            except Exception:
                return False

        mask = (
            filtered["first_name"].apply(match_any)
            | filtered["last_name"].apply(match_any)
            | filtered["email"].apply(match_any)
            | filtered["notes"].apply(match_any)
            | filtered["selected_role"].apply(match_any)
            | filtered["skills_hard"].apply(match_skills)
            | filtered["skills_soft"].apply(match_skills)
        )
        filtered = filtered[mask]

    # -------------------------------------------------------
    # 🧾 CLICKABLE TABLE (AgGrid)
    # -------------------------------------------------------
    st.markdown("### Applicants Overview")

    if filtered.empty:
        st.warning("No matching applicants found.")
    else:
        filtered_display = filtered[
            ["id", "first_name", "last_name", "selected_role", "status",
            "resume_score", "jd_match_score", "experience_years", "created_at"]
        ].rename(columns={
            "id": "ID",
            "first_name": "First Name",
            "last_name": "Last Name",
            "selected_role": "Role",
            "status": "Status",
            "resume_score": "Eval Score",
            "jd_match_score": "JD Match",
            "experience_years": "Exp (yrs)",
            "created_at": "Created At"
        })

        gb = GridOptionsBuilder.from_dataframe(filtered_display)
        gb.configure_selection("single", use_checkbox=True)
        gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=10)
        gb.configure_grid_options(domLayout="normal")
        gridOptions = gb.build()

        grid_response = AgGrid(
            filtered_display,
            gridOptions=gridOptions,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            fit_columns_on_grid_load=True,
            theme="balham",
            height=350,
        )

        selected_rows = grid_response.get("selected_rows", [])

        # -------------------------------------------------------
        # DETAIL PANEL — Clean Split Layout
        # -------------------------------------------------------
        selected_rows = grid_response.get("selected_rows", [])

        # Defensive handling (AgGrid sometimes returns DataFrame)
        if isinstance(selected_rows, pd.DataFrame):
            selected_rows = selected_rows.to_dict("records")

        if isinstance(selected_rows, list) and len(selected_rows) > 0:
            candidate = selected_rows[0]
            selected_id = int(candidate["ID"])

            # Safely extract full record (for non-displayed fields like email/skills)
            candidate_full = filtered[filtered["id"] == selected_id].iloc[0].to_dict()

            st.markdown("---")
            st.markdown(
                f"<h3 style='color:#1e293b;'>Candidate Profile — {candidate_full['first_name']} {candidate_full['last_name']}</h3>",
                unsafe_allow_html=True,
            )

            # ---------------------------------------------------
            # LEFT COLUMN — Candidate info + actions
            # ---------------------------------------------------
            col1, col2 = st.columns([1.3, 2.2])

            with col1:
                st.markdown(f"**Email:** {candidate_full['email']}")
                st.markdown(f"**Phone:** {candidate_full['phone']}")
                st.markdown(f"**Role:** {candidate_full['selected_role']}")
                st.markdown(f"**Location:** {candidate_full.get('address', '-')}")
                st.markdown(f"**Experience:** {candidate_full.get('experience_years', 0)} yrs")

                st.divider()

                # --- Editable Fields ---
                new_status = st.selectbox(
                    "Change Status",
                    ["new", "shortlisted", "interviewed", "hired", "rejected"],
                    index=["new", "shortlisted", "interviewed", "hired", "rejected"].index(candidate_full["status"]),
                    key=f"status_{selected_id}"
                )
                new_score = st.slider(
                    "Update Evaluation Score",
                    0, 100,
                    int(candidate_full.get("resume_score", 0)),
                    1,
                    key=f"score_{selected_id}"
                )
                new_notes = st.text_area(
                    "Notes / Feedback",
                    value=candidate_full.get("notes") or "",
                    key=f"notes_{selected_id}"
                )

                c1, c2, c3 = st.columns([1, 1, 1])
                with c1:
                    if st.button("Save Changes", key=f"save_{selected_id}"):
                        execute(
                            "UPDATE user_data SET status=%s, resume_score=%s, notes=%s WHERE id=%s",
                            (new_status, new_score, new_notes, selected_id)
                        )
                        st.success("✅ Candidate updated successfully!")
                        st.rerun()
                with c2:
                    if st.button("Delete", key=f"del_{selected_id}"):
                        execute("DELETE FROM user_data WHERE id=%s", (selected_id,))
                        st.warning("Applicant deleted.")
                        st.rerun()
                with c3:
                    cv_file = candidate_full["cv_filename"]
                    st.download_button(
                        label="Download CV",
                        data=open(os.path.join("App", "Uploaded_Resumes", cv_file), "rb").read(),
                        file_name=cv_file,
                        mime="application/pdf"
                    )

            # ---------------------------------------------------
            # RIGHT COLUMN — Evaluation, Skills, JD Match
            # ---------------------------------------------------
            with col2:
                st.markdown("### Evaluation Overview")
                eval_score = float(candidate_full.get("resume_score", 0))
                st.progress(int(eval_score), text=f"Evaluation Score: {eval_score:.1f}%")

                hard_skills = (
                    json.loads(candidate_full["skills_hard"])
                    if isinstance(candidate_full.get("skills_hard"), str) and candidate_full["skills_hard"]
                    else []
                )
                soft_skills = (
                    json.loads(candidate_full["skills_soft"])
                    if isinstance(candidate_full.get("skills_soft"), str) and candidate_full["skills_soft"]
                    else []
                )

                st.markdown("### Skills Summary")
                if hard_skills or soft_skills:
                    colh, cols = st.columns(2)
                    with colh:
                        st.markdown("**Hard Skills:**")
                        st.markdown(
                            ", ".join([f"<span style='color:#22c55e;'> {s}</span>" for s in hard_skills]),
                            unsafe_allow_html=True
                        )
                    with cols:
                        st.markdown("**Soft Skills:**")
                        st.markdown(
                            ", ".join([f"<span style='color:#2563eb;'> {s}</span>" for s in soft_skills]),
                            unsafe_allow_html=True
                        )
                else:
                    st.info("No skills detected.")

                # ---------------------------------------------------
                # JD Keyword Match (Weighted + Accurate)
                # ---------------------------------------------------
                st.divider()
                st.markdown("### JD Keyword Match")

                try:
                    conn = get_conn()
                    cur = conn.cursor(dictionary=True)
                    cur.execute("""
                        SELECT keyword, importance, weight
                        FROM jd_keywords
                        WHERE role_id = (SELECT id FROM jd_roles WHERE role_name = %s LIMIT 1)
                    """, (candidate_full.get("selected_role"),))
                    jd_keywords = cur.fetchall()
                    cur.close()
                    conn.close()

                    if jd_keywords:
                        all_skills = [s.lower() for s in (hard_skills + soft_skills)]
                        total_weight = matched_weight = 0
                        matched_keywords, missing_keywords = [], []

                        for kw in jd_keywords:
                            keyword = kw["keyword"].lower()
                            weight = float(kw.get("weight", 1.0))
                            importance = kw.get("importance", "preferred")
                            imp_factor = 1.5 if importance == "critical" else 1.0
                            total_weight += weight * imp_factor

                            if any(keyword in s for s in all_skills):
                                matched_weight += weight * imp_factor
                                matched_keywords.append(keyword)
                            else:
                                missing_keywords.append(keyword)

                        jd_match_score = (matched_weight / total_weight * 100) if total_weight > 0 else 0
                        jd_match_score = round(jd_match_score, 1)

                        execute("UPDATE user_data SET jd_match_score=%s WHERE id=%s", (jd_match_score, selected_id))
                        st.progress(int(jd_match_score), text=f"JD Match: {jd_match_score:.1f}%")

                        st.markdown(f"**Matched ({len(matched_keywords)}/{len(jd_keywords)}):**")
                        st.markdown(
                            ", ".join([f"<span style='color:#22c55e;'>✅ {m}</span>" for m in matched_keywords]),
                            unsafe_allow_html=True
                        )
                        st.markdown(f"**Missing ({len(missing_keywords)}):**")
                        if missing_keywords:
                            st.markdown(
                                ", ".join([f"<span style='color:#ef4444;'>❌ {m}</span>" for m in missing_keywords]),
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown("<span style='color:#22c55e;'>All JD keywords covered!</span>", unsafe_allow_html=True)
                    else:
                        st.info("No JD keywords defined for this role.")
                except Exception as e:
                    st.warning(f"JD match check failed: {e}")

        else:
            st.info("* Click a row in the table to view candidate details.")
                    
            # -------------------------------------------------------
            # ANALYTICS SECTION
            # -------------------------------------------------------
            st.markdown("---")
            st.markdown("## Analytics Overview")
            if not filtered.empty:
                col1, col2 = st.columns(2)
                role_chart = px.pie(filtered, names="selected_role", title="Applicants by Role", hole=0.4)
                st.plotly_chart(role_chart, use_container_width=True)
                status_chart = px.bar(filtered, x="status", y="resume_score", color="status", title="Avg Score by Status")
                st.plotly_chart(status_chart, use_container_width=True)
            else:
                st.info("Not enough data for analytics.")
            
    # -------------------------------------------------------
    # Manual Upload Section (always visible)
    # -------------------------------------------------------
    st.divider()
    st.subheader("Add Applicant (Manual Upload)")

    with st.form("add_applicant_form_v3"):
        first_name = st.text_input("First Name")
        last_name = st.text_input("Last Name")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        role = st.selectbox(
            "Select Role",
            ["AI Engineer", "Software Developer", "Data Analyst", "Cybersecurity Engineer"],
            key="role_select_app_v3",
        )
        uploaded_cv = st.file_uploader("Upload CV (PDF only)", type=["pdf"])
        submit = st.form_submit_button("Submit")

    if submit:
        if not all([first_name, last_name, email, phone, uploaded_cv]):
            st.warning("⚠️ Please complete all fields.")
        else:
            upload_dir = os.path.join("App", "Uploaded_Resumes")
            os.makedirs(upload_dir, exist_ok=True)
            path = os.path.join(upload_dir, f"{first_name}_{last_name}_{int(time.time())}.pdf")
            with open(path, "wb") as f:
                f.write(uploaded_cv.getbuffer())

            st.info("📄 Resume uploaded. Processing...")
            try:
                result = process_and_sync_resume(path, first_name, last_name, email, phone, role)
                st.success("✅ Application processed and stored!")
                st.json(result)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to process resume: {e}")
# ====================================================================
# TAB 2 — ROLES & JD KEYWORDS (v3 – Smart Manager)
# ====================================================================
import plotly.express as px

with tabs[1]:
    st.markdown("<h2 style='margin-bottom:0;'>Roles & JD Keywords Manager</h2>", unsafe_allow_html=True)
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)

    # ----------------------------------------------------------------
    # 🎓 Role Creation
    # ----------------------------------------------------------------
    with st.expander("➕ Add a New Role", expanded=False):
        with st.form("add_role_form"):
            st.write("Define a new role in the system")
            new_role = st.text_input("Role Name", key="role_name_input")
            new_text = st.text_area("JD Description (optional)", height=180, key="role_text_input")
            submit_role = st.form_submit_button("Add Role")
            if submit_role and new_role:
                cursor.execute("INSERT INTO jd_roles (role_name, jd_text) VALUES (%s, %s)", (new_role, new_text))
                conn.commit()
                st.success(f"Added role: {new_role}")
                st.rerun()

    st.markdown("---")

    # ----------------------------------------------------------------
    # 📋 Role List
    # ----------------------------------------------------------------
    cursor.execute("SELECT id, role_name, created_at, updated_at FROM jd_roles ORDER BY created_at DESC;")
    roles = cursor.fetchall()

    if not roles:
        st.info("No roles found. Create one above to begin.")
        cursor.close()
        conn.close()
        st.stop()

    left, right = st.columns([1.3, 2.7])
    with left:
        st.markdown("### Available Roles")
        df_roles = pd.DataFrame(roles)
        df_roles_display = df_roles.rename(columns={
            "role_name": "Role Name", "created_at": "Created", "updated_at": "Updated"
        })
        st.dataframe(df_roles_display, use_container_width=True, hide_index=True)

        selected_role_name = st.selectbox(
            "Select Role to Manage",
            df_roles["role_name"].tolist(),
            key="selected_role_manage"
        )
        selected_role = next(r for r in roles if r["role_name"] == selected_role_name)
        role_id = selected_role["id"]

        if st.button(f"Delete '{selected_role_name}'", key=f"del_role_{role_id}"):
            cursor.execute("DELETE FROM jd_roles WHERE id=%s", (role_id,))
            cursor.execute("DELETE FROM jd_keywords WHERE role_id=%s", (role_id,))
            conn.commit()
            st.warning(f"Deleted role and all its keywords: {selected_role_name}")
            st.rerun()

    # ----------------------------------------------------------------
    # Role Editor + Keyword Manager
    # ----------------------------------------------------------------
    with right:
        st.markdown(f"### Role: **{selected_role_name}**")

        # Fetch JD text
        cursor.execute("SELECT jd_text FROM jd_roles WHERE id=%s", (role_id,))
        jd_text = cursor.fetchone()["jd_text"] or ""

        # Editable JD text
        jd_text_updated = st.text_area("Job Description", jd_text, height=300, key=f"jd_text_{role_id}")
        if st.button("Save JD Description", key=f"save_jd_{role_id}"):
            cursor.execute("UPDATE jd_roles SET jd_text=%s WHERE id=%s", (jd_text_updated, role_id))
            conn.commit()
            st.success("JD text updated successfully!")

        st.divider()
        st.markdown("### Keywords for This Role")

        cursor.execute("SELECT * FROM jd_keywords WHERE role_id=%s ORDER BY importance DESC, keyword ASC;", (role_id,))
        keywords = cursor.fetchall()

        if keywords:
            
            df_kw = pd.DataFrame(keywords).rename(columns={
                "keyword": "Keyword",
                "importance": "Importance",
                "weight": "Weight"
            })
            # Visualize critical vs preferred
            fig = px.pie(
                df_kw,
                names="Importance",
                title="Keyword Importance Distribution",
                hole=0.4,
                color_discrete_sequence=["#2563eb", "#22c55e"]
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_kw[["Keyword", "Importance", "Weight"]], use_container_width=True, hide_index=True)

            
        else:
            st.info("No keywords defined yet for this role.")

        st.divider()

        # ------------------------------------------------------------
        # ➕ Add Keyword
        # ------------------------------------------------------------
        with st.form(f"add_keyword_form_{role_id}"):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                kw = st.text_input("Keyword", key=f"kw_input_{role_id}")
            with col2:
                imp = st.selectbox("Importance", ["critical", "preferred"], key=f"kw_imp_{role_id}")
            with col3:
                wt = st.number_input("Weight", 0.1, 5.0, 1.0, step=0.1, key=f"kw_wt_{role_id}")
            add_kw_btn = st.form_submit_button("Add Keyword")
            if add_kw_btn and kw:
                cursor.execute(
                    "INSERT INTO jd_keywords (role_id, keyword, importance, weight) VALUES (%s, %s, %s, %s)",
                    (role_id, kw.lower(), imp, wt)
                )
                conn.commit()
                st.success(f"Added keyword: {kw}")
                st.rerun()

        # ------------------------------------------------------------
        # Delete Keyword
        # ------------------------------------------------------------
        cursor.execute("SELECT keyword FROM jd_keywords WHERE role_id=%s;", (role_id,))
        kw_list = [r["keyword"] for r in cursor.fetchall()]
        if kw_list:
            del_kw = st.selectbox("Select Keyword to Delete", kw_list, key=f"kw_del_{role_id}")
            if st.button("Delete Keyword", key=f"kw_del_btn_{role_id}"):
                cursor.execute("DELETE FROM jd_keywords WHERE role_id=%s AND keyword=%s", (role_id, del_kw))
                conn.commit()
                st.warning(f"Deleted keyword: {del_kw}")
                st.rerun()

       
        # ------------------------------------------------------------
        # Smart Tools — Auto Extract Keywords
        # ------------------------------------------------------------
        st.divider()
        with st.expander("Smart Tools"):
            st.markdown("Automatically extract potential keywords from the JD text using NLP.")
            if st.button("Auto Extract Keywords from JD", key=f"auto_extract_{role_id}"):
                try:
                    import spacy, re
                    nlp = spacy.load("en_core_web_sm")

                    # --- Process JD text ---
                    doc = nlp(jd_text_updated)
                    candidates = set()

                    # Extract meaningful noun tokens
                    for token in doc:
                        if (
                            token.pos_ in ["NOUN", "PROPN"]
                            and len(token.text) > 2
                            and not token.is_stop
                            and re.match(r"^[A-Za-z][A-Za-z0-9\+\-\.]*$", token.text)
                        ):
                            candidates.add(token.text.lower())

                    # Filter out duplicates and existing keywords
                    cursor.execute("SELECT keyword FROM jd_keywords WHERE role_id=%s", (role_id,))
                    existing = {r["keyword"].lower() for r in cursor.fetchall()}

                    new_keywords = sorted(list(candidates - existing))
                    if not new_keywords:
                        st.info("No new keywords found in JD text.")
                    else:
                        # Insert new keywords
                        inserted = 0
                        for kw in new_keywords:
                            cursor.execute(
                                "INSERT INTO jd_keywords (role_id, keyword, importance, weight) VALUES (%s, %s, %s, %s)",
                                (role_id, kw, "preferred", 1.0)
                            )
                            inserted += 1

                        conn.commit()
                        st.success(f"✅ Extracted and added {inserted} new keywords automatically!")
                        st.rerun()

                except Exception as e:
                    st.error(f"❌ Extraction failed: {e}")

    cursor.close()
    conn.close()
# ====================================================================
# TAB 3 — SKILL SYNONYMS MANAGER
# ====================================================================
with tabs[2]:
    st.subheader("Skill Synonyms Manager")

    # ---------------------------------------------------------------
    # Load existing synonyms
    # ---------------------------------------------------------------
    df_syn = fetch_df("SELECT id, token, expands_to, category FROM synonyms ORDER BY token;")

    total_synonyms = len(df_syn)
    st.markdown(f"**Total Synonyms:** {total_synonyms}")

    if total_synonyms > 0:
        st.dataframe(df_syn, use_container_width=True, hide_index=True)
    else:
        st.info("No synonyms found. Add some below to improve semantic matching accuracy.")

    st.divider()

    # ---------------------------------------------------------------
    # Add new synonym
    # ---------------------------------------------------------------
    st.markdown("**Add New Synonym**")

    with st.form("add_syn_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([1.5, 1.5, 1])
        with c1:
            token = st.text_input("Base Skill or Abbreviation", placeholder="e.g. ml", key="syn_token")
        with c2:
            expands = st.text_input("Expanded Term", placeholder="e.g. machine learning", key="syn_exp")
        with c3:
            cat = st.selectbox("Category", ["skill", "tool", "certification", "other"], key="syn_cat")

        add_btn = st.form_submit_button("Add Synonym")

        if add_btn:
            if not token or not expands:
                st.warning("Please fill in both the base and expanded term fields.")
            else:
                # Normalize inputs
                token, expands, cat = token.strip().lower(), expands.strip().lower(), cat.strip().lower()

                # Check for duplicates
                existing = fetch_df("SELECT * FROM synonyms WHERE token = %s AND expands_to = %s", (token, expands))
                if not existing.empty:
                    st.warning("This synonym mapping already exists.")
                else:
                    execute(
                        "INSERT INTO synonyms (token, expands_to, category) VALUES (%s, %s, %s)",
                        (token, expands, cat)
                    )
                    st.success(f"Added synonym: '{token}' → '{expands}'  [{cat}]")
                    st.rerun()

    st.divider()

    # ---------------------------------------------------------------
    # Delete existing synonym
    # ---------------------------------------------------------------
    if not df_syn.empty:
        st.markdown("**Delete Synonym**")

        c1, c2 = st.columns([2, 1])
        with c1:
            del_token = st.selectbox(
                "Select a synonym to delete",
                options=df_syn.apply(lambda r: f"{r['token']} → {r['expands_to']} ({r['category']})", axis=1),
                key="syn_delete_sel"
            )
        with c2:
            delete_btn = st.button("Delete Selected", key="syn_delete_btn", use_container_width=True)

        if delete_btn:
            # Extract original token from selection text
            token_to_delete = del_token.split("→")[0].strip()
            execute("DELETE FROM synonyms WHERE token = %s", (token_to_delete,))
            st.warning(f"Deleted synonym: {del_token}")
            st.rerun()

# ====================================================================
# TAB 4 — SCORING RULES
# ====================================================================
with tabs[3]:
    st.subheader("Resume Scoring Weights")
    critical = st.slider("Critical Weight", 0.0, 1.0, SCORING_RULES["critical_weight"], 0.05, key="crit_w")
    preferred = st.slider("Preferred Weight", 0.0, 1.0, SCORING_RULES["preferred_weight"], 0.05, key="pref_w")
    semantic = st.slider("Semantic Weight", 0.0, 1.0, SCORING_RULES["semantic_weight"], 0.05, key="sem_w")
    if st.button("💾 Save Settings", key="save_scoring"):
        new_rules = {
            "critical_weight": critical,
            "preferred_weight": preferred,
            "semantic_weight": semantic
        }

        config_path = os.path.join( "config.py")

        # Read the existing file
        with open(config_path, "r") as f:
            content = f.read()

        import re
        # Replace the entire SCORING_RULES = { ... } block safely using regex
        updated_content = re.sub(
            r"SCORING_RULES\s*=\s*\{[^}]+\}",
            f"SCORING_RULES = {json.dumps(new_rules, indent=4)}",
            content,
            flags=re.DOTALL
        )

        # Write back the clean version
        with open(config_path, "w") as f:
            f.write(updated_content)

        st.success("✅ Updated scoring weights in config.py!")
        st.rerun()


# ====================================================================
# TAB 5 — AUDIT LOG
# ====================================================================
with tabs[4]:
    st.subheader("System Audit Log")
    try:
        logs = fetch_df("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 200;")
        if logs.empty:
            st.info("No logs yet.")
        else:
            st.dataframe(logs, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not fetch logs: {e}")