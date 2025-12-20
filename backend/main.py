from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from typing import Optional
import os
import sys
import re
from pathlib import Path
import traceback
import json  # for pretty printing
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urlencode
import os as _os



# Ensure the backend directory itself is on sys.path so `App` stays importable
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Load environment variables from backend/App/.env so DB/ES configs pick them up
load_dotenv(BASE_DIR / "App" / ".env")

from App.db_io import (
    process_and_sync_resume,
    get_dashboard_insights,
    fetch_applications,
    export_applications_csv,
    fetch_candidate_detail,
    update_candidate_status,
    update_candidate_resume_score,
    add_candidate_note,
    delete_candidate,
    delete_candidate_note,
    delete_all_candidate_notes,
    fetch_roles,
    fetch_role_detail,
    update_role_jd,
    upsert_role_keyword,
    delete_role_keyword,
    analytics_overview,
    create_role,
    set_role_visibility,
    discover_skill_candidates,
    append_skills_to_dictionary,
    get_skill_dictionary,
    list_synonyms,
    create_synonym,
    update_synonym,
    delete_synonym,
    reprocess_candidate,
    ensure_interview_schema_mod,
    fetch_interview_sessions,
    create_interview_invite,
    bulk_invite_best_fits,
)
from App.document_processing import run_cv_understanding
from App.resume_parser.parser import ResumeParser
from App.interview_portal_ui import build_portal_view
from App.interviews import (
    mark_session_started,
    mark_session_completed,
    create_invite_with_token,
    mark_invite_sent,
    mark_invite_failed,
    get_session_by_token,
    mark_session_started_by_token,
    mark_session_completed_by_token,
)
from App.emailer import SmtpConfig, send_email, is_valid_email
from App.interview_engine import build_system_prompt, start_interview, continue_interview
from App.interview_state import get_session_state, update_session_state, update_interview_score

# Initialize FastAPI app
app = FastAPI(title="SourceHive API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Upload directory
UPLOAD_DIR = BASE_DIR / "App" / "Uploaded_Resumes"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Skills file path (must exist!)
SKILLS_FILE = BASE_DIR / "App" / "resume_parser" / "data" / "hard_skills.txt"
if not SKILLS_FILE.exists():
    raise FileNotFoundError(f"Skills file not found: {SKILLS_FILE}")

ALLOWED_UPLOAD_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".rtf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)

ALLOWED_STATUSES = {"new", "shortlisted", "interviewed", "hired", "rejected"}


class StatusUpdatePayload(BaseModel):
    status: str = Field(..., description="New status value")


class ResumeScoreUpdatePayload(BaseModel):
    resume_score: float = Field(..., ge=0, le=100)


class NotePayload(BaseModel):
    comment: str = Field(..., min_length=1, max_length=2000)


class RoleJDPayload(BaseModel):
    jd_text: str = Field("", description="Job description text")


class RoleCreatePayload(BaseModel):
    role_name: str = Field(..., min_length=2, max_length=255)
    jd_text: str = Field("", description="Job description text")


class RoleVisibilityPayload(BaseModel):
    is_open: bool = Field(default=True)


class KeywordPayload(BaseModel):
    keyword: str
    importance: str = Field(default="preferred")
    weight: float = Field(default=1.0)
    keyword_id: Optional[int] = None


class SkillDictionaryPayload(BaseModel):
    kind: str = Field(default="hard")
    skills: list[str] = Field(default=[])


class SynonymCreatePayload(BaseModel):
    token: str
    expands_to: str
    category: str = Field(default="skill")


class SynonymUpdatePayload(BaseModel):
    token: Optional[str] = None
    expands_to: Optional[str] = None
    category: Optional[str] = None


class InterviewInvitePayload(BaseModel):
    user_id: int
    candidate_name: str = Field(default="")
    role_name: str
    email: str = Field(default="")
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class BulkInterviewInvitePayload(BaseModel):
    role_name: str
    top_n: int = Field(default=10, ge=1, le=200)
    min_jd: int = Field(default=70, ge=0, le=100)
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class InterviewCompletePayload(BaseModel):
    score: Optional[float] = Field(default=None, ge=0, le=100)


class InterviewEmailInvitePayload(BaseModel):
    candidate_email: str
    candidate_name: str = Field(default="")
    role_name: str
    expires_hours: int = Field(default=72, ge=1, le=720)


class TestSmtpPayload(BaseModel):
    to_email: Optional[str] = None


class HrEmailPayload(BaseModel):
    to_email: str
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=8000)


class InterviewMessagePayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


def _build_resume_label(first_name: str, last_name: str, email: str, phone: str) -> str:
    parts = [first_name.strip(), last_name.strip(), email.strip(), phone.strip()]
    base = "_".join(filter(None, parts))
    if not base:
        base = "resume"
    normalized = re.sub(r"[^\w]+", "_", base).strip("_")
    return normalized or "resume"

# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "SourceHive API is running"}

# ============================================================
# RESUME UPLOAD & PROCESSING
# ============================================================
@app.post("/api/resume/upload")
async def upload_resume(
    file: UploadFile = File(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    selected_role: str = Form("")
):
    try:
        # Validate file type
        if not file.filename.lower().endswith(ALLOWED_UPLOAD_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Use PDF, DOC/DOCX, TXT/RTF, or common image formats (PNG/JPG/WEBP).",
            )

        # Save file with human-readable label + extension; ensure uniqueness if same person uploads multiple times
        resume_label = _build_resume_label(first_name, last_name, email, phone)
        ext = Path(file.filename).suffix.lower() or ".pdf"
        safe_name = f"{resume_label}{ext}"
        file_path = UPLOAD_DIR / safe_name
        suffix = 1
        while file_path.exists():
            file_path = UPLOAD_DIR / f"{resume_label}_{suffix}{ext}"
            suffix += 1
        with open(file_path, "wb") as f:
            f.write(await file.read())
        print(f"\nSaved file to: {file_path}\n")

        # ==========================
        # Parse resume
        # ==========================
        doc_payload = {}
        try:
            doc_payload = run_cv_understanding(
                str(file_path),
                original_name=file.filename,
            )
        except Exception:
            print('[Doc] Unable to analyze document; falling back to legacy extraction.')
            traceback.print_exc()
            doc_payload = {}

        try:
            parser = ResumeParser(
                resume=str(file_path),
                skills_file=str(SKILLS_FILE),
                extracted_text=doc_payload.get('text'),
                document_meta=doc_payload,
                original_filename=file.filename,
            )
            parsed_resume = parser.get_extracted_data()
            print('[Parse] Parsed resume successfully.')
            print(json.dumps(parsed_resume, indent=4, ensure_ascii=False))
        except Exception:
            print('[Parse] Error parsing resume:')
            traceback.print_exc()
            parsed_resume = {}
        # ==========================
        # Process and sync to DB/ES
        # ==========================
        try:
            db_result = process_and_sync_resume(
                path=str(file_path),
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                selected_role=selected_role,
                resume_text=doc_payload.get('text'),
                doc_kind=doc_payload.get('doc_kind'),
                extraction_method=doc_payload.get('extraction_method'),
                ocr_used=doc_payload.get('ocr_used'),
                extraction_error=doc_payload.get('extraction_error'),
                file_mime=doc_payload.get('file_mime'),
                original_filename=file.filename,
            )
            print("[DB] Stored resume metadata:")
            print(json.dumps(db_result, indent=4, ensure_ascii=False))
            if isinstance(db_result, dict):
                db_result.setdefault('resume_display_name', resume_label)
        except Exception:
            print("[DB] Error syncing to database:")
            traceback.print_exc()
            db_result = {}


        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Resume processed successfully",
                "parsed_resume": parsed_resume,
                "document_meta": doc_payload,
                "db_result": db_result
            }
        )

    except HTTPException as e:
        raise e
    except Exception:
        print("❌ Unexpected error in /api/resume/upload:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")

# ============================================================
# SEARCH CANDIDATES
# ============================================================
@app.get("/api/dashboard/overview")
async def dashboard_overview():
    try:
        overview = get_dashboard_insights()
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "overview": overview
            }
        )
    except Exception:
        print("??O Error in /api/dashboard/overview:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ============================================================
# HR APPLICATIONS MANAGEMENT
# ============================================================
@app.get("/api/hr/applications")
async def list_applications(
    status: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    try:
        results = fetch_applications(
            status=status,
            role=role,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "applications": results["rows"],
                "total": results["total"],
                "stats": results["stats"],
                "page": page,
                "page_size": page_size,
            },
        )
    except Exception:
        print("??O Error in /api/hr/applications:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/hr/skills/dictionary")
async def get_skill_dictionary_endpoint(kind: str = Query("hard")):
    try:
        data = get_skill_dictionary(kind)
        return JSONResponse(
            status_code=200,
            content={"success": True, "dictionary": data},
        )
    except Exception:
        print("??O Error in /api/hr/skills/dictionary GET:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post("/api/hr/skills/dictionary")
async def add_skill_dictionary_entries(payload: SkillDictionaryPayload):
    if not payload.skills:
        raise HTTPException(status_code=400, detail="Provide at least one skill to append.")
    try:
        result = append_skills_to_dictionary(payload.kind, payload.skills)
        return JSONResponse(
            status_code=200,
            content={"success": True, "result": result},
        )
    except Exception:
        print("??O Error in /api/hr/skills/dictionary POST:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/hr/skills/enrichment")
async def skill_enrichment_endpoint(
    role: Optional[str] = Query(None),
    limit: int = Query(400, ge=50, le=1000),
    max_phrases: int = Query(100, ge=10, le=300),
):
    try:
        suggestions = discover_skill_candidates(role=role, limit=limit, max_phrases=max_phrases)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "role": role,
                "limit": limit,
                "max_phrases": max_phrases,
                "suggestions": suggestions,
            },
        )
    except Exception:
        print("??O Error in /api/hr/skills/enrichment:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/hr/synonyms")
async def list_synonyms_endpoint():
    try:
        rows = list_synonyms()
        return JSONResponse(
            status_code=200,
            content={"success": True, "synonyms": rows},
        )
    except Exception:
        print("??O Error in /api/hr/synonyms GET:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post("/api/hr/synonyms")
async def create_synonym_endpoint(payload: SynonymCreatePayload):
    try:
        ok = create_synonym(payload.token, payload.expands_to, payload.category)
        if not ok:
            raise HTTPException(status_code=400, detail="Unable to create synonym mapping.")
        return JSONResponse(
            status_code=200,
            content={"success": True},
        )
    except HTTPException:
        raise
    except Exception:
        print("??O Error in /api/hr/synonyms POST:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.patch("/api/hr/synonyms/{synonym_id}")
async def update_synonym_endpoint(synonym_id: int, payload: SynonymUpdatePayload):
    if not any([payload.token, payload.expands_to, payload.category]):
        raise HTTPException(status_code=400, detail="Provide at least one field to update.")
    try:
        ok = update_synonym(
            synonym_id,
            token=payload.token,
            expands_to=payload.expands_to,
            category=payload.category,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Synonym entry not found or not updated.")
        return JSONResponse(status_code=200, content={"success": True})
    except HTTPException:
        raise
    except Exception:
        print("??O Error in /api/hr/synonyms PATCH:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.delete("/api/hr/synonyms/{synonym_id}")
async def delete_synonym_endpoint(synonym_id: int):
    try:
        ok = delete_synonym(synonym_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Synonym entry not found.")
        return JSONResponse(status_code=200, content={"success": True})
    except HTTPException:
        raise
    except Exception:
        print("??O Error in /api/hr/synonyms DELETE:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post("/api/hr/candidates/{candidate_id}/reprocess")
async def reprocess_candidate_endpoint(candidate_id: int):
    try:
        result = reprocess_candidate(candidate_id)
        return JSONResponse(
            status_code=200,
            content={"success": True, "result": result},
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Resume file not found for candidate.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        print("??O Error in /api/hr/candidates/{candidate_id}/reprocess:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/hr/applications/export")
async def export_applications(
    status: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
):
    try:
        csv_payload = export_applications_csv(
            {
                "status": status,
                "role": role,
                "start_date": start_date,
                "end_date": end_date,
                "keyword": keyword,
            }
        )
        filename = f"applications_{datetime.utcnow().date()}.csv"
        return Response(
            content=csv_payload,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception:
        print("??O Error in /api/hr/applications/export:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/hr/applications/{application_id}")
async def get_application(application_id: int):
    data = fetch_candidate_detail(application_id)
    if not data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "candidate": data["user"],
            "notes": data["notes"],
            "jd_keywords": data["jd_keywords"],
            "jd_match": data["jd_match"],
        },
    )


@app.patch("/api/hr/applications/{application_id}/status")
async def update_application_status(application_id: int, payload: StatusUpdatePayload):
    status_value = payload.status.lower()
    if status_value not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status value")
    success = update_candidate_status(application_id, status_value)
    if not success:
        raise HTTPException(status_code=500, detail="Unable to update status")
    return {"success": True, "status": status_value}


@app.patch("/api/hr/applications/{application_id}/resume_score")
async def update_application_resume_score(application_id: int, payload: ResumeScoreUpdatePayload):
    try:
        ok = update_candidate_resume_score(application_id, payload.resume_score)
        if not ok:
            raise HTTPException(status_code=400, detail="Unable to update resume score")
        return {"success": True, "resume_score": payload.resume_score}
    except HTTPException:
        raise
    except Exception:
        print("??O Error in /api/hr/applications/{id}/resume_score:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")



# ============================================================
# ROLES MANAGEMENT
# ============================================================
@app.get("/api/hr/applications/{application_id}/notes")
async def list_application_notes(application_id: int):
    data = fetch_candidate_detail(application_id)
    if not data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"success": True, "notes": data["notes"]}


@app.post("/api/hr/applications/{application_id}/notes")
async def create_application_note(application_id: int, payload: NotePayload):
    success = add_candidate_note(application_id, payload.comment.strip())
    if not success:
        raise HTTPException(status_code=500, detail="Unable to add note")
    return {"success": True}


@app.delete("/api/hr/applications/{application_id}")
async def remove_application(application_id: int):
    success = delete_candidate(application_id)
    if not success:
        raise HTTPException(status_code=500, detail="Unable to delete candidate")
    return {"success": True}


@app.delete("/api/hr/applications/{application_id}/notes/{note_id}")
async def remove_note(application_id: int, note_id: int):
    success = delete_candidate_note(note_id)
    if not success:
        raise HTTPException(status_code=500, detail="Unable to delete note")
    return {"success": True}


@app.delete("/api/hr/applications/{application_id}/notes")
async def remove_all_notes(application_id: int):
    success = delete_all_candidate_notes(application_id)
    if not success:
        raise HTTPException(status_code=500, detail="Unable to delete notes")
    return {"success": True}


@app.get("/api/hr/roles")
async def list_roles():
    return {"success": True, "roles": fetch_roles()}


@app.post("/api/hr/roles", status_code=201)
async def create_hr_role(payload: RoleCreatePayload):
    role_name = payload.role_name.strip()
    if not role_name:
        raise HTTPException(status_code=400, detail="Role name required")
    role_id = create_role(role_name, payload.jd_text)
    if not role_id:
        raise HTTPException(status_code=500, detail="Unable to create role")
    detail = fetch_role_detail(role_id)
    return {"success": True, "role": detail["role"] if detail else {"id": role_id, "role_name": role_name, "jd_text": payload.jd_text}}


@app.get("/api/hr/roles/{role_id}")
async def get_role(role_id: int):
    detail = fetch_role_detail(role_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"success": True, **detail}


@app.patch("/api/hr/roles/{role_id}/jd")
async def patch_role_jd(role_id: int, payload: RoleJDPayload):
    success = update_role_jd(role_id, payload.jd_text)
    if not success:
        raise HTTPException(status_code=500, detail="Unable to update JD")
    return {"success": True}


@app.patch("/api/hr/roles/{role_id}/visibility")
async def patch_role_visibility(role_id: int, payload: RoleVisibilityPayload):
    success = set_role_visibility(role_id, payload.is_open)
    if not success:
        raise HTTPException(status_code=500, detail="Unable to update role visibility")
    return {"success": True, "is_open": payload.is_open}


@app.post("/api/hr/roles/{role_id}/keywords")
async def create_or_update_keyword(role_id: int, payload: KeywordPayload):
    success = upsert_role_keyword(
        role_id=role_id,
        keyword=payload.keyword,
        importance=payload.importance,
        weight=payload.weight,
        keyword_id=payload.keyword_id,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Unable to save keyword")
    return {"success": True}


@app.delete("/api/hr/roles/keywords/{keyword_id}")
async def remove_keyword(keyword_id: int):
    success = delete_role_keyword(keyword_id)
    if not success:
        raise HTTPException(status_code=500, detail="Unable to delete keyword")
    return {"success": True}


# ============================================================
# ANALYTICS
# ============================================================
@app.get("/api/hr/analytics")
async def analytics_summary(start_date: str = "", end_date: str = "", role: str = ""):
    try:
        data = analytics_overview(
            start_date=start_date or None,
            end_date=end_date or None,
            role=role or None,
        )
        return {"success": True, "analytics": data}
    except Exception:
        print("??O Error in /api/hr/analytics:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ============================================================
# AI INTERVIEWS
# ============================================================
@app.get("/api/hr/interviews/sessions")
async def list_interview_sessions():
    try:
        try:
            ensure_interview_schema_mod()
        except Exception:
            pass

        sessions = fetch_interview_sessions() or []
        invited = sum(1 for s in sessions if (s.get("interview_status") or "") == "invited")
        in_prog = sum(1 for s in sessions if (s.get("interview_status") or "") == "in_progress")
        completed = sum(1 for s in sessions if (s.get("interview_status") or "") == "completed")

        scores = []
        for s in sessions:
            val = s.get("interview_score")
            try:
                num = float(val)
            except Exception:
                num = None
            if num is not None:
                scores.append(num)
        avg_score = round((sum(scores) / len(scores)) if scores else 0.0, 1)

        return {
            "success": True,
            "sessions": sessions,
            "stats": {
                "invited": invited,
                "in_progress": in_prog,
                "completed": completed,
                "avg_score": avg_score,
            },
        }
    except Exception:
        print("??O Error in /api/hr/interviews/sessions:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post("/api/hr/interviews/invite", status_code=201)
async def invite_ai_interview(payload: InterviewInvitePayload):
    try:
        result = create_interview_invite(
            user_id=payload.user_id,
            candidate_name=payload.candidate_name,
            role_name=payload.role_name,
            email=payload.email,
            expires_in_hours=payload.expires_in_hours,
        )
        if not result:
            raise HTTPException(status_code=500, detail="Unable to create invite")
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception:
        print("??O Error in /api/hr/interviews/invite:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post("/api/hr/interviews/bulk-invite", status_code=201)
async def bulk_invite_ai_interviews(payload: BulkInterviewInvitePayload):
    try:
        result = bulk_invite_best_fits(
            role_name=payload.role_name,
            top_n=payload.top_n,
            min_jd=payload.min_jd,
            expires_in_hours=payload.expires_in_hours,
        )
        return {"success": True, **result}
    except Exception:
        print("??O Error in /api/hr/interviews/bulk-invite:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ============================================================
# EMAIL INVITES (token-based)
# ============================================================
def _get_interview_base_url() -> str:
    value = _os.environ.get("INTERVIEW_BASE_URL", "").strip()
    return value or "http://localhost:5173/interview"

def _max_interview_questions() -> int:
    try:
        return max(1, int(_os.environ.get("INTERVIEW_MAX_QUESTIONS", "6")))
    except Exception:
        return 6


def _fallback_questions(role_name: str):
    role = (role_name or "").strip().lower()
    common = [
        "Can you introduce yourself and describe your recent experience?",
        "Tell me about a challenging project you worked on and what you learned.",
        "How do you prioritize tasks when you have multiple deadlines?",
        "Describe a time you had a conflict with a teammate. How did you handle it?",
        "What are you looking for in your next role?",
    ]
    if "python" in role or "backend" in role:
        return [
            "Can you introduce yourself and describe your recent Python experience?",
            "Explain the difference between a list and a tuple, and when you’d use each.",
            "How do you handle errors and logging in a production API?",
            "Describe an optimization you made (performance or memory) and how you measured it.",
            "How do you design an API endpoint with validation, pagination, and filtering?",
        ]
    if "frontend" in role or "react" in role:
        return [
            "Can you introduce yourself and describe your recent frontend experience?",
            "How do you structure React components for maintainability?",
            "What’s your approach to state management and data fetching?",
            "How do you improve performance for a slow page?",
            "How do you ensure accessibility in your UI?",
        ]
    return common


def _parse_json_list(value):
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
    return parsed if isinstance(parsed, list) else []


def _fetch_candidate_profile_snapshot(user_id: int):
    """Fetch minimal candidate data for interview context (no email/phone)."""
    import mysql.connector
    from App.config import DB_CONFIG

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
          id,
          first_name,
          last_name,
          selected_role,
          parsed_role,
          experience_years,
          skills_hard,
          skills_soft,
          job_titles_json,
          seniority_level,
          education_json,
          certifications_json
        FROM user_data
        WHERE id = %s
        LIMIT 1
        """,
        (int(user_id),),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        return None

    first = (row.get("first_name") or "").strip()
    last = (row.get("last_name") or "").strip()
    skills_hard = _parse_json_list(row.get("skills_hard"))
    skills_soft = _parse_json_list(row.get("skills_soft"))
    titles = _parse_json_list(row.get("job_titles_json"))
    certs = _parse_json_list(row.get("certifications_json"))
    education = row.get("education_json")

    return {
        "name": (f"{first} {last}".strip() or "Candidate"),
        "selected_role": (row.get("selected_role") or "").strip(),
        "parsed_role": (row.get("parsed_role") or "").strip(),
        "experience_years": float(row.get("experience_years") or 0),
        "seniority_level": (row.get("seniority_level") or "").strip(),
        "skills_hard": [str(s).strip() for s in skills_hard if str(s).strip()][:25],
        "skills_soft": [str(s).strip() for s in skills_soft if str(s).strip()][:25],
        "job_titles": [str(s).strip() for s in titles if str(s).strip()][:10],
        "certifications": [str(s).strip() for s in certs if str(s).strip()][:10],
        "education": education,
    }


def _fetch_role_context(role_name: str):
    import mysql.connector
    from App.config import DB_CONFIG

    role = (role_name or "").strip()
    if not role:
        return {"role_name": "", "jd_text": "", "keywords": []}

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT jd_text FROM jd_roles WHERE role_name = %s LIMIT 1", (role,))
    jd_row = cursor.fetchone() or {}
    jd_text = jd_row.get("jd_text") or ""
    if isinstance(jd_text, bytes):
        jd_text = jd_text.decode("utf-8", errors="ignore")

    cursor.execute(
        """
        SELECT keyword, importance, weight
        FROM jd_keywords
        WHERE role_id = (SELECT id FROM jd_roles WHERE role_name = %s LIMIT 1)
        ORDER BY importance DESC, weight DESC, keyword ASC
        LIMIT 40
        """,
        (role,),
    )
    keywords = cursor.fetchall() or []
    cursor.close()
    conn.close()

    kw_tokens = []
    for row in keywords:
        token = (row.get("keyword") or "").strip()
        if token:
            kw_tokens.append(token)

    return {"role_name": role, "jd_text": jd_text or "", "keywords": kw_tokens}


def _build_interview_context_text(*, user_id: int, role_name: str):
    candidate = _fetch_candidate_profile_snapshot(user_id) or {}
    role_ctx = _fetch_role_context(role_name or candidate.get("selected_role") or "") or {}

    name = candidate.get("name") or "Candidate"
    applied_role = role_ctx.get("role_name") or (role_name or candidate.get("selected_role") or "the role")
    exp = candidate.get("experience_years") or 0
    seniority = candidate.get("seniority_level") or ""
    hard_skills = candidate.get("skills_hard") or []
    soft_skills = candidate.get("skills_soft") or []
    titles = candidate.get("job_titles") or []
    certs = candidate.get("certifications") or []
    keywords = role_ctx.get("keywords") or []
    jd_text = role_ctx.get("jd_text") or ""

    # Keep JD short to reduce prompt size.
    jd_excerpt = jd_text.strip().replace("\r", "").replace("\n\n", "\n")
    if len(jd_excerpt) > 1200:
        jd_excerpt = jd_excerpt[:1200] + "…"

    def _join(items):
        return ", ".join(items) if items else "N/A"

    return "\n".join(
        [
            "CANDIDATE_CONTEXT (for interviewer only):",
            f"- Candidate name: {name}",
            f"- Role applied for: {applied_role}",
            f"- Experience years (estimated): {exp}",
            f"- Seniority: {seniority or 'N/A'}",
            f"- Recent titles: {_join(titles)}",
            f"- Hard skills (parsed): {_join(hard_skills)}",
            f"- Soft skills (parsed): {_join(soft_skills)}",
            f"- Certifications (parsed): {_join(certs)}",
            "",
            "ROLE_CONTEXT:",
            f"- Key JD keywords: {_join(keywords[:25])}",
            f"- JD excerpt: {jd_excerpt or 'N/A'}",
            "",
            "INSTRUCTIONS:",
            "- Ask questions tailored to the candidate + this role.",
            "- Validate claims: ask for examples and details.",
            "- If a key keyword is missing, ask about it politely (don’t assume lack of skill).",
            "- Do NOT reveal or mention private data like email/phone.",
            "- Keep one question at a time.",
        ]
    )


def _build_system_prompt_for_session(user_id: int, role_name: str) -> str:
    base = build_system_prompt()
    ctx = _build_interview_context_text(user_id=user_id, role_name=role_name)
    return base + "\n\n" + ctx


def _fallback_next_question(role_name: str, current_question: str):
    questions = _fallback_questions(role_name)
    if not current_question:
        return questions[0]
    try:
        idx = questions.index(current_question)
        return questions[min(idx + 1, len(questions) - 1)]
    except Exception:
        return questions[0]


def _normalize_question(text: str) -> str:
    import re

    value = (text or "").strip().lower()
    value = re.sub(r"[\s\r\n\t]+", " ", value)
    value = re.sub(r"[^\w\s]", "", value)
    return value.strip()


def _is_same_question(a: str, b: str) -> bool:
    na = _normalize_question(a)
    nb = _normalize_question(b)
    return bool(na and nb and na == nb)


def _find_user_id_by_email(candidate_email: str) -> Optional[int]:
    import mysql.connector
    from App.config import DB_CONFIG

    email_value = (candidate_email or "").strip()
    if not email_value:
        return None
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id
        FROM user_data
        WHERE email = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (email_value,),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return int(row[0]) if row else None


@app.post("/api/interviews/invite", status_code=201)
async def invite_interview_email(payload: InterviewEmailInvitePayload):
    candidate_email = (payload.candidate_email or "").strip()
    if not is_valid_email(candidate_email):
        raise HTTPException(status_code=400, detail="Invalid candidate_email")

    user_id = _find_user_id_by_email(candidate_email)
    if not user_id:
        raise HTTPException(status_code=404, detail="Candidate not found for this email")

    role_name = (payload.role_name or "").strip()
    if not role_name:
        raise HTTPException(status_code=400, detail="role_name is required")

    invite = create_invite_with_token(
        user_id=user_id,
        role_name=role_name,
        candidate_name=payload.candidate_name,
        email=candidate_email,
        expires_in_hours=payload.expires_hours,
        rate_limit_minutes=10,
    )
    if not invite:
        raise HTTPException(status_code=500, detail="Unable to create interview session")

    # If rate-limited we don't have a token; return 429.
    if not invite.token:
        raise HTTPException(status_code=429, detail="Invite recently sent. Please wait before resending.")

    token = invite.token
    token_hash = invite.token_hash

    base_url = _get_interview_base_url()
    invite_url = f"{base_url}?{urlencode({'token': token})}"

    subject = f"Interview Invitation — {role_name}"
    name = (payload.candidate_name or "").strip() or "Candidate"
    body = "\n".join(
        [
            f"Hello {name},",
            "",
            "You have been invited to an AI interview.",
            "",
            f"Role: {role_name}",
            "",
            "Start Interview:",
            invite_url,
            "",
            "Instructions:",
            "- Use Google Chrome",
            "- Allow microphone access when prompted",
            "",
            f"This link expires in {payload.expires_hours} hours.",
            "",
            "If you need help, reply to this email.",
        ]
    )

    try:
        smtp = SmtpConfig.from_env()
        send_email(to_email=candidate_email, subject=subject, body=body, config=smtp)
        mark_invite_sent(invite.session_id)
        return {"success": True, "session_id": invite.session_id, "invite_sent": True}
    except Exception as exc:
        # Do not log token; store only error + token hash.
        mark_invite_failed(invite.session_id, str(exc))
        return {
            "success": True,
            "session_id": invite.session_id,
            "invite_sent": False,
            "token_hash": token_hash,
            "fallback_url": invite_url,
        }

@app.get("/api/interviews/by-token")
async def get_interview_portal_by_token(token: str = ""):
    session = get_session_by_token(token)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    view = build_portal_view(session.get("session_id"))
    if not view:
        raise HTTPException(status_code=404, detail="Interview session not found")
    state = get_session_state(session.get("session_id")) or {}
    return {
        "success": True,
        "session": {
            **view,
            "current_question": state.get("current_question"),
            "question_count": state.get("question_count") or 0,
            "max_questions": _max_interview_questions(),
        },
    }


@app.post("/api/interviews/by-token/start")
async def start_interview_session_by_token(token: str = ""):
    session = get_session_by_token(token)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")

    session_id = session.get("session_id")
    state = get_session_state(session_id) or {}
    llm_messages = state.get("llm_messages") or []
    current_question = state.get("current_question") or ""
    question_count = int(state.get("question_count") or 0)
    max_q = _max_interview_questions()

    ok = mark_session_started(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Interview session not found")

    if current_question and llm_messages:
        return {
            "success": True,
            "started": True,
            "current_question": current_question,
            "question_count": question_count,
            "max_questions": max_q,
        }

    # Initialize conversation + get first question.
    if not llm_messages:
        llm_messages = [{"role": "system", "content": _build_system_prompt_for_session(session.get("user_id"), session.get("interview_role") or role_name)}]

    try:
        turn = start_interview(llm_messages)
        llm_messages.append({"role": "user", "content": "Start the interview. Ask the first question."})
        llm_messages.append({"role": "assistant", "content": turn.raw})
        role_name = session.get("interview_role") or ""
        question = (turn.question or "").strip() or _fallback_next_question(role_name, "")
        next_count = question_count if question_count > 0 else 1
        update_session_state(session_id, current_question=question, llm_messages=llm_messages, question_count=next_count)
        return {
            "success": True,
            "started": True,
            "ack": turn.ack,
            "feedback": turn.feedback,
            "question": question,
            "question_count": next_count,
            "max_questions": max_q,
        }
    except Exception as exc:
        # LLM is optional; fall back to a deterministic question set.
        role_name = session.get("interview_role") or ""
        question = _fallback_next_question(role_name, "")
        next_count = question_count if question_count > 0 else 1
        update_session_state(
            session_id,
            current_question=question,
            llm_messages=[{"role": "system", "content": "FALLBACK_MODE"}],
            question_count=next_count,
        )
        return {
            "success": True,
            "started": True,
            "mode": "fallback",
            "warning": f"AI engine unavailable ({type(exc).__name__}). Using basic interview questions.",
            "ack": "Hi! I'll be your interviewer today.",
            "feedback": [],
            "question": question,
            "question_count": next_count,
            "max_questions": max_q,
        }


@app.post("/api/interviews/by-token/complete")
async def complete_interview_session_by_token(payload: InterviewCompletePayload, token: str = ""):
    ok = mark_session_completed_by_token(token, payload.score)
    if not ok:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return {"success": True}


@app.post("/api/interviews/by-token/message")
async def interview_portal_message(payload: InterviewMessagePayload, token: str = ""):
    session = get_session_by_token(token)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    session_id = session.get("session_id")
    state = get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Interview session not found")

    current_question = (state.get("current_question") or "").strip()
    llm_messages = state.get("llm_messages") or []
    question_count = int(state.get("question_count") or 0)
    max_q = _max_interview_questions()
    if not llm_messages:
        llm_messages = [{"role": "system", "content": _build_system_prompt_for_session(session.get("user_id"), session.get("interview_role") or "")}]
    if not current_question:
        # If interview wasn't started, start now.
        try:
            first = start_interview(llm_messages)
            llm_messages.append({"role": "user", "content": "Start the interview. Ask the first question."})
            llm_messages.append({"role": "assistant", "content": first.raw})
            current_question = first.question
        except Exception as exc:
            role_name = session.get("interview_role") or ""
            current_question = _fallback_next_question(role_name, "")
            llm_messages = [{"role": "system", "content": "FALLBACK_MODE"}]
            next_count = question_count if question_count > 0 else 1
            update_session_state(session_id, current_question=current_question, llm_messages=llm_messages, question_count=next_count)
            return {
                "success": True,
                "mode": "fallback",
                "warning": f"AI engine unavailable ({type(exc).__name__}). Using basic interview questions.",
                "ack": "Hi! I'll be your interviewer today.",
                "feedback": [],
                "question": current_question,
                "question_count": next_count,
                "max_questions": max_q,
            }

    user_answer = payload.message.strip()
    try:
        turn = continue_interview(llm_messages, current_question=current_question, user_answer=user_answer)
        user_payload = f"CURRENT_QUESTION: {current_question}\nUSER_ANSWER: {user_answer}\n\nRespond using the JSON schema."
        llm_messages.append({"role": "user", "content": user_payload})
        llm_messages.append({"role": "assistant", "content": turn.raw})
    except Exception as exc:
        role_name = session.get("interview_role") or ""
        next_question = _fallback_next_question(role_name, current_question)
        # If candidate just answered the last question, finish instead of asking more.
        if question_count >= max_q:
            mark_session_completed(session_id, None)
            update_session_state(session_id, current_question="", llm_messages=[{"role": "system", "content": "FALLBACK_MODE"}], question_count=question_count)
            return {
                "success": True,
                "mode": "fallback",
                "completed": True,
                "ack": "Thanks — your interview is complete.",
                "feedback": [],
                "question": "",
                "question_count": question_count,
                "max_questions": max_q,
            }

        next_count = question_count + 1 if question_count > 0 else 2
        update_session_state(
            session_id,
            current_question=next_question,
            llm_messages=[{"role": "system", "content": "FALLBACK_MODE"}],
            question_count=next_count,
        )
        # Simple heuristic scoring in fallback mode.
        try:
            score = 60.0
            if len(user_answer) >= 200:
                score = 85.0
            elif len(user_answer) >= 80:
                score = 75.0
            update_interview_score(session_id, score)
        except Exception:
            pass
        return {
            "success": True,
            "mode": "fallback",
            "warning": f"AI engine unavailable ({type(exc).__name__}). Using basic interview questions.",
            "ack": "Thanks — noted.",
            "feedback": [],
            "question": next_question,
            "question_count": next_count,
            "max_questions": max_q,
        }

    # If candidate just answered the last question, finish instead of asking more.
    if question_count >= max_q:
        mark_session_completed(session_id, None)
        update_session_state(session_id, current_question="", llm_messages=llm_messages, question_count=question_count)
        return {
            "success": True,
            "completed": True,
            "ack": turn.ack or "Thanks — your interview is complete.",
            "feedback": turn.feedback,
            "question": "",
            "question_count": question_count,
            "max_questions": max_q,
            "evaluation": turn.evaluation,
        }

    role_name = session.get("interview_role") or ""
    proposed = (turn.question or "").strip()
    is_follow_up = bool((turn.follow_up or "").strip()) and not bool((turn.next_question or "").strip())

    # Enforce forward progress: never repeat the same question verbatim and never store empty questions.
    if not proposed:
        proposed = _fallback_next_question(role_name, current_question)
        is_follow_up = False
    elif _is_same_question(proposed, current_question):
        proposed = _fallback_next_question(role_name, current_question)
        is_follow_up = False

    next_question = proposed
    next_count = question_count if is_follow_up else (question_count + 1 if question_count > 0 else 2)
    update_session_state(session_id, current_question=next_question, llm_messages=llm_messages, question_count=next_count)

    # Update interview_score as percent from overall_score 1-10.
    try:
        overall = turn.evaluation.get("overall_score")
        overall_int = int(overall) if overall is not None else None
        if overall_int is not None:
            update_interview_score(session_id, float(max(0, min(10, overall_int)) * 10))
    except Exception:
        pass

    return {
        "success": True,
        "ack": turn.ack,
        "feedback": turn.feedback,
        "question": next_question,
        "question_count": next_count,
        "max_questions": max_q,
    }


@app.get("/api/interviews/{session_id}")
async def get_interview_portal(session_id: str):
    view = build_portal_view(session_id)
    if not view:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return {"success": True, "session": view}


@app.post("/api/interviews/{session_id}/start")
async def start_interview_session(session_id: str):
    ok = mark_session_started(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return {"success": True}


@app.post("/api/interviews/{session_id}/complete")
async def complete_interview_session(session_id: str, payload: InterviewCompletePayload):
    ok = mark_session_completed(session_id, payload.score)
    if not ok:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return {"success": True}


@app.post("/api/hr/admin/test-smtp")
async def test_smtp(payload: TestSmtpPayload):
    to_email = (payload.to_email or "").strip() or _os.environ.get("SMTP_USER", "")
    if not to_email:
        raise HTTPException(status_code=400, detail="to_email is required")
    if not is_valid_email(to_email):
        raise HTTPException(status_code=400, detail="Invalid to_email")
    smtp = SmtpConfig.from_env()
    send_email(
        to_email=to_email,
        subject="SourceHive SMTP test",
        body="This is a test email from SourceHive.",
        config=smtp,
    )
    return {"success": True}


@app.post("/api/hr/email/send")
async def send_hr_email(payload: HrEmailPayload):
    to_email = (payload.to_email or "").strip()
    if not is_valid_email(to_email):
        raise HTTPException(status_code=400, detail="Invalid to_email")
    smtp = SmtpConfig.from_env()
    send_email(to_email=to_email, subject=payload.subject.strip(), body=payload.body, config=smtp)
    return {"success": True}


# ============================================================
# ROOT ENDPOINT
# ============================================================
@app.get("/")
async def root():
    return {
        "message": "Welcome to SourceHive API",
        "docs": "/docs",
        "version": "1.0.0"
    }

# ============================================================
# RUN LOCAL
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
