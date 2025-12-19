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
)
from App.resume_parser.parser import ResumeParser

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

# Ensure _SYN_CACHE exists globally
if "_SYN_CACHE" not in globals():
    _SYN_CACHE = {"ts": 0, "map": {}}

ALLOWED_STATUSES = {"new", "shortlisted", "interviewed", "hired", "rejected"}


class StatusUpdatePayload(BaseModel):
    status: str = Field(..., description="New status value")


class NotePayload(BaseModel):
    comment: str = Field(..., min_length=1, max_length=2000)


class RoleJDPayload(BaseModel):
    jd_text: str = Field("", description="Job description text")


class RoleCreatePayload(BaseModel):
    role_name: str = Field(..., min_length=2, max_length=255)
    jd_text: str = Field("", description="Job description text")


class KeywordPayload(BaseModel):
    keyword: str
    importance: str = Field(default="preferred")
    weight: float = Field(default=1.0)
    keyword_id: Optional[int] = None


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
        if not file.filename.lower().endswith((".pdf", ".docx")):
            raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF or DOCX.")

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
        try:
            parser = ResumeParser(resume=str(file_path), skills_file=str(SKILLS_FILE))
            parsed_resume = parser.get_extracted_data()
            print("📝 Parsed Resume:")
            print(json.dumps(parsed_resume, indent=4, ensure_ascii=False))
        except Exception:
            print("❌ Error parsing resume:")
            traceback.print_exc()
            parsed_resume = {}

        # ==========================
        # Process and sync to DB/ES
        # ==========================
        try:
            global _SYN_CACHE
            db_result = process_and_sync_resume(
                path=str(file_path),
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                selected_role=selected_role
            )
            print("💾 DB/ES Result:")
            print(json.dumps(db_result, indent=4, ensure_ascii=False))
            if isinstance(db_result, dict):
                db_result.setdefault("resume_display_name", resume_label)
        except Exception:
            print("❌ Error syncing to DB/ES:")
            traceback.print_exc()
            db_result = {}

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Resume processed successfully",
                "parsed_resume": parsed_resume,
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
async def analytics_summary():
    try:
        data = analytics_overview()
        return {"success": True, "analytics": data}
    except Exception:
        print("??O Error in /api/hr/analytics:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


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
