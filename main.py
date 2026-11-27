import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import database as db
from .gemini_service import TUTOR_MODES, ask_daksh_tutor
from .repository import StudyRepository

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

db.init_db()
repo = StudyRepository()

ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "dakshbugalia1@gmail.com").split(",")
    if e.strip()
}
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or os.getenv("OWNER_PASSWORD") or "daksh2026"
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyB4ZcYnp4ZerJe3u-YqVSM2Uza5FOZ1Cos")
def _load_or_create_cookie_secret() -> str:
    env_secret = os.getenv("EDUPREP_COOKIE_SECRET")
    if env_secret:
        return env_secret
    secret_file = BASE_DIR / "data" / ".cookie_secret"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    if secret_file.exists():
        val = secret_file.read_text(encoding="utf-8").strip()
        if val:
            return val
    val = secrets.token_hex(32)
    secret_file.write_text(val, encoding="utf-8")
    return val

COOKIE_SECRET = _load_or_create_cookie_secret()
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(
    title="EduPrep With Daksh",
    description="Public Python web app for Class 10, 11 & 12 study material, quizzes, practice papers, Admin Studio, and AI tutoring.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

_chat_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
CHAT_RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT_PER_MIN", "20"))


def _sign_admin_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": email.lower(), "exp": int(time.time()) + 60 * 60 * 24 * 7}).encode()
    ).decode()
    sig = hmac.new(COOKIE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_admin_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    try:
        payload, sig = token.rsplit(".", 1)
        expected = hmac.new(COOKIE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        if data.get("exp", 0) < time.time():
            return None
        email = (data.get("email") or "").strip().lower()
        return email if email in ADMIN_EMAILS else None
    except Exception:
        return None


def _get_admin_email(request: Request) -> str | None:
    token = request.cookies.get("eduprep_admin")
    return _verify_admin_token(token)


def _require_admin(request: Request) -> str:
    email = _get_admin_email(request)
    if not email:
        raise HTTPException(status_code=403, detail="Admin access required (dakshbugalia1@gmail.com).")
    return email


def _set_admin_cookie(response: Response, email: str) -> None:
    response.set_cookie(
        key="eduprep_admin",
        value=_sign_admin_token(email),
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        samesite="lax",
    )


def _get_session_id(request: Request, response: Response | None = None) -> str:
    sid = request.headers.get("X-Session-ID") or request.cookies.get("eduprep_session")
    if not sid or len(sid) > 64:
        sid = str(uuid.uuid4())
        if response is not None:
            response.set_cookie(
                key="eduprep_session",
                value=sid,
                max_age=60 * 60 * 24 * 365,
                httponly=False,
                samesite="lax",
            )
    return sid


# --- Request Schemas ---
class BookmarkIn(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=120)
    class_level: str = Field(..., min_length=1, max_length=32)
    subject_id: str = Field(..., min_length=1, max_length=64)
    item_type: Literal["NOTE", "FORMULA", "QUESTION", "CHAPTER"]
    title: str = Field(..., min_length=1, max_length=200)
    snippet: str = Field("", max_length=600)


class QuizAttemptIn(BaseModel):
    chapter_id: str = Field(..., min_length=1, max_length=64)
    chapter_title: str = Field(..., min_length=1, max_length=200)
    subject_name: str = Field(..., min_length=1, max_length=120)
    class_level: str = Field(..., min_length=1, max_length=32)
    score: int = Field(..., ge=0, le=500)
    total_questions: int = Field(..., ge=1, le=500)
    time_taken_seconds: int = Field(0, ge=0, le=86400)


class PaperAttemptIn(BaseModel):
    paper_id: str = Field(..., min_length=1, max_length=64)
    paper_title: str = Field(..., min_length=1, max_length=200)
    subject_name: str = Field(..., min_length=1, max_length=120)
    class_level: str = Field(..., min_length=1, max_length=32)
    marks_obtained: int = Field(..., ge=0, le=500)
    total_marks: int = Field(..., ge=1, le=500)


class ChapterReadIn(BaseModel):
    is_read: bool = True


class UserNoteIn(BaseModel):
    chapter_id: str = Field(..., min_length=1, max_length=64)
    chapter_title: str = Field(..., min_length=1, max_length=200)
    note_text: str = Field(..., min_length=1, max_length=4000)


class ChatTurn(BaseModel):
    sender: Literal["user", "ai"]
    text: str = Field(..., max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    class_id: Literal["class_10", "class_11", "class_12"] = "class_10"
    tutor_mode: Literal["general", "fast", "complex"] = "general"
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class AdminLoginIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=120)
    password: str = Field(..., min_length=1, max_length=120)


class SSORequest(BaseModel):
    id_token: str = Field(..., min_length=10)


class CustomFormulaIn(BaseModel):
    class_level: Literal["class_10", "class_11", "class_12"]
    subject_id: str = Field(..., min_length=1, max_length=64)
    chapter_id: str = Field(..., min_length=1, max_length=64)
    chapter_title: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=160)
    formula_text: str = Field(..., min_length=1, max_length=500)
    where_terms: str = Field("", max_length=400)
    application_note: str = Field("", max_length=400)


class CustomQuizIn(BaseModel):
    chapter_id: str = Field(..., min_length=1, max_length=64)
    question_text: str = Field(..., min_length=1, max_length=1200)
    options: list[str] = Field(..., min_length=2, max_length=6)
    correct_option_index: int = Field(..., ge=0, le=5)
    explanation: str = Field("", max_length=1200)
    hint: str = Field("", max_length=400)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    question_type: Literal["conceptual", "numerical", "assertion_reason"] = "conceptual"


# --- Frontend & Health ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    response = templates.TemplateResponse(request, "index.html", {"request": request})
    _get_session_id(request, response)
    return response


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "EduPrep With Daksh",
        "gemini_configured": bool(
            os.getenv("GEMINI_API_KEY", "").strip()
            and os.getenv("GEMINI_API_KEY", "").strip() != "MY_GEMINI_API_KEY"
        ),
    }


# --- Admin Auth & Daksh Intelligence SSO ---
@app.get("/api/auth/me")
async def auth_me(request: Request):
    email = _get_admin_email(request)
    return {"is_admin": bool(email), "email": email}


@app.post("/api/auth/admin-login")
async def admin_login(payload: AdminLoginIn, response: Response):
    email = payload.email.strip().lower()
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Only authorized admin accounts can sign in.")
    if not hmac.compare_digest(payload.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid admin password.")
    _set_admin_cookie(response, email)
    return {"is_admin": True, "email": email}


@app.post("/api/auth/sso")
async def firebase_sso(payload: SSORequest, response: Response):
    """Verify Firebase ID token from Daksh Intelligence and auto-grant admin access."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_API_KEY}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"idToken": payload.id_token})

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired Daksh Intelligence session token.")

    users = resp.json().get("users") or []
    if not users:
        raise HTTPException(status_code=401, detail="No user found for token.")

    email = (users[0].get("email") or "").strip().lower()
    if email not in ADMIN_EMAILS:
        return {"is_admin": False, "email": email, "message": "Signed in as student."}

    _set_admin_cookie(response, email)
    return {"is_admin": True, "email": email, "message": "Admin access granted automatically."}


@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie("eduprep_admin")
    return {"ok": True}


# --- Study Content Endpoints ---
@app.get("/api/classes")
async def get_classes():
    return {"classes": repo.get_classes()}


@app.get("/api/subjects")
async def get_subjects(class_id: str = "class_10"):
    return {"subjects": repo.get_subjects_for_class(class_id)}


@app.get("/api/subjects/{subject_id}/chapters")
async def get_subject_chapters(subject_id: str):
    subject = repo.get_subject_by_id(subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"subject": subject, "chapters": repo.get_chapters_for_subject(subject_id)}


@app.get("/api/chapters/{chapter_id}")
async def get_chapter_detail(chapter_id: str):
    chapter = repo.get_chapter_by_id(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    subject = repo.get_subject_by_id(chapter["subjectId"])
    notes = repo.get_notes_for_chapter(chapter_id)
    return {"chapter": chapter, "subject": subject, "notes": notes}


@app.get("/api/chapters/{chapter_id}/quiz")
async def get_chapter_quiz(chapter_id: str):
    chapter = repo.get_chapter_by_id(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return {"chapter": chapter, "questions": repo.get_quiz_for_chapter(chapter_id)}


@app.get("/api/formulas")
async def get_formulas(class_id: str = "class_10"):
    return {"formulas": repo.get_formulas_for_class(class_id)}


@app.get("/api/papers")
async def get_practice_papers(class_id: str = "class_10"):
    return {"papers": repo.get_practice_papers_for_class(class_id)}


@app.get("/api/papers/{paper_id}")
async def get_practice_paper(paper_id: str):
    paper = repo.get_practice_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Practice paper not found")
    return {"paper": paper}


@app.get("/api/search")
async def search(q: str = "", class_id: str | None = None):
    return {"results": repo.search_material(q, class_id)}


# --- Public Student Study Files (Uploaded by Admin) ---
@app.get("/api/files")
async def list_files(class_id: str | None = None):
    return {"files": db.list_admin_files(class_id)}


@app.get("/api/files/{file_id}/download")
async def download_file(file_id: int):
    rec = db.get_admin_file(file_id)
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = UPLOAD_DIR / rec["stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File missing from storage")
    return FileResponse(path=file_path, filename=rec["filename"], media_type=rec["mime_type"])


# --- Admin-Only Endpoints ---
@app.post("/api/admin/files")
async def upload_admin_file(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    class_level: str = Form("class_10"),
    category: str = Form("Formula Sheet"),
    subject_id: str = Form(""),
    chapter_id: str = Form(""),
    description: str = Form(""),
):
    admin_email = _require_admin(request)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit.")

    original_name = Path(file.filename or "document.pdf").name
    ext = Path(original_name).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / stored_name).write_bytes(content)

    rec = db.add_admin_file(
        class_level=class_level,
        subject_id=subject_id,
        chapter_id=chapter_id,
        category=category,
        title=title.strip(),
        description=description.strip(),
        filename=original_name,
        stored_name=stored_name,
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        uploaded_by=admin_email,
    )
    return {"file": rec}


@app.delete("/api/admin/files/{file_id}")
async def remove_admin_file(file_id: int, request: Request):
    _require_admin(request)
    rec = db.delete_admin_file(file_id)
    if rec:
        (UPLOAD_DIR / rec["stored_name"]).unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/admin/formulas")
async def create_custom_formula(payload: CustomFormulaIn, request: Request):
    _require_admin(request)
    f = db.add_custom_formula(
        class_level=payload.class_level,
        subject_id=payload.subject_id,
        chapter_id=payload.chapter_id,
        chapter_title=payload.chapter_title,
        name=payload.name,
        formula_text=payload.formula_text,
        where_terms=payload.where_terms,
        application_note=payload.application_note,
    )
    return {"formula": f}


@app.delete("/api/admin/formulas/{db_id}")
async def remove_custom_formula(db_id: int, request: Request):
    _require_admin(request)
    db.delete_custom_formula(db_id)
    return {"ok": True}


@app.get("/api/admin/quizzes")
async def get_all_custom_quizzes(request: Request):
    _require_admin(request)
    return {"quizzes": db.list_custom_quizzes()}


@app.post("/api/admin/quizzes")
async def create_custom_quiz(payload: CustomQuizIn, request: Request):
    _require_admin(request)
    if payload.correct_option_index >= len(payload.options):
        raise HTTPException(status_code=400, detail="correct_option_index out of range")
    q = db.add_custom_quiz(
        chapter_id=payload.chapter_id,
        question_text=payload.question_text,
        options=payload.options,
        correct_option_index=payload.correct_option_index,
        explanation=payload.explanation,
        hint=payload.hint,
        difficulty=payload.difficulty,
        question_type=payload.question_type,
    )
    return {"quiz": q}


@app.delete("/api/admin/quizzes/{db_id}")
async def remove_custom_quiz(db_id: int, request: Request):
    _require_admin(request)
    db.delete_custom_quiz(db_id)
    return {"ok": True}


@app.get("/api/admin/students")
async def get_all_students(request: Request):
    _require_admin(request)
    students = db.list_all_students_summary()
    return {
        "students": students,
        "total_students": len(students),
        "total_quizzes": sum(s["quiz_count"] for s in students),
        "total_papers": sum(s["paper_count"] for s in students),
        "total_notes": sum(s["notes_count"] for s in students),
    }


@app.get("/api/admin/students/{session_id}")
async def get_student_activity(session_id: str, request: Request):
    _require_admin(request)
    return db.get_student_detail(session_id)


# --- User Progress, Bookmarks, Notes (Session-scoped SQLite) ---
@app.get("/api/progress")
async def get_progress(request: Request, response: Response):
    sid = _get_session_id(request, response)
    return {
        "session_id": sid,
        "bookmarks": db.list_bookmarks(sid),
        "quiz_attempts": db.list_quiz_attempts(sid),
        "paper_attempts": db.list_paper_attempts(sid),
        "chapter_progress": db.list_chapter_progress(sid),
        "user_notes": db.list_user_notes(sid),
    }


@app.post("/api/bookmarks")
async def create_bookmark(payload: BookmarkIn, request: Request, response: Response):
    sid = _get_session_id(request, response)
    bm = db.add_bookmark(
        sid,
        payload.item_id,
        payload.class_level,
        payload.subject_id,
        payload.item_type,
        payload.title,
        payload.snippet,
    )
    return {"bookmark": bm}


@app.delete("/api/bookmarks/{item_id}")
async def delete_bookmark(item_id: str, request: Request, response: Response):
    sid = _get_session_id(request, response)
    db.remove_bookmark(sid, item_id)
    return {"ok": True}


@app.post("/api/quiz-attempts")
async def create_quiz_attempt(payload: QuizAttemptIn, request: Request, response: Response):
    sid = _get_session_id(request, response)
    res = db.record_quiz_attempt(
        sid,
        payload.chapter_id,
        payload.chapter_title,
        payload.subject_name,
        payload.class_level,
        payload.score,
        payload.total_questions,
        payload.time_taken_seconds,
    )
    return {"attempt": res}


@app.post("/api/paper-attempts")
async def create_paper_attempt(payload: PaperAttemptIn, request: Request, response: Response):
    sid = _get_session_id(request, response)
    res = db.record_paper_attempt(
        sid,
        payload.paper_id,
        payload.paper_title,
        payload.subject_name,
        payload.class_level,
        payload.marks_obtained,
        payload.total_marks,
    )
    return {"attempt": res}


@app.post("/api/chapters/{chapter_id}/read")
async def set_chapter_read(chapter_id: str, payload: ChapterReadIn, request: Request, response: Response):
    sid = _get_session_id(request, response)
    res = db.mark_chapter_read(sid, chapter_id, payload.is_read)
    return {"progress": res}


@app.get("/api/notes")
async def get_user_notes(request: Request, response: Response, chapter_id: str | None = None):
    sid = _get_session_id(request, response)
    return {"notes": db.list_user_notes(sid, chapter_id)}


@app.post("/api/notes")
async def create_user_note(payload: UserNoteIn, request: Request, response: Response):
    sid = _get_session_id(request, response)
    note = db.add_user_note(sid, payload.chapter_id, payload.chapter_title, payload.note_text)
    return {"note": note}


@app.delete("/api/notes/{note_id}")
async def remove_user_note(note_id: int, request: Request, response: Response):
    sid = _get_session_id(request, response)
    db.delete_user_note(sid, note_id)
    return {"ok": True}


# --- Daksh AI Tutor ---
@app.get("/api/tutor-modes")
async def get_tutor_modes():
    return {"modes": list(TUTOR_MODES.values())}


@app.post("/api/chat")
async def chat_with_daksh(payload: ChatRequest, request: Request, response: Response):
    sid = _get_session_id(request, response)
    client_key = f"{request.client.host if request.client else 'unknown'}:{sid}"
    now = time.time()
    bucket = _chat_rate_buckets[client_key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= CHAT_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a minute before asking more questions.")
    bucket.append(now)

    try:
        result = await ask_daksh_tutor(
            user_message=payload.message,
            history=[t.model_dump() for t in payload.history],
            class_id=payload.class_id,
            tutor_mode=payload.tutor_mode,
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
