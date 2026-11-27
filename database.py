import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("EDUPREP_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "eduprep.db"))


def init_db() -> None:
    """Initialize SQLite tables for student progress and admin-managed resources."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bookmarks (
                session_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                class_level TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                title TEXT NOT NULL,
                snippet TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                PRIMARY KEY (session_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                chapter_title TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                class_level TEXT NOT NULL,
                score INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                time_taken_seconds INTEGER NOT NULL DEFAULT 0,
                timestamp INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                paper_title TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                class_level TEXT NOT NULL,
                marks_obtained INTEGER NOT NULL,
                total_marks INTEGER NOT NULL,
                timestamp INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chapter_progress (
                session_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                quiz_high_score INTEGER NOT NULL DEFAULT 0,
                quiz_attempts_count INTEGER NOT NULL DEFAULT 0,
                last_accessed INTEGER NOT NULL,
                PRIMARY KEY (session_id, chapter_id)
            );

            CREATE TABLE IF NOT EXISTS user_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                chapter_title TEXT NOT NULL,
                note_text TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_level TEXT NOT NULL,
                subject_id TEXT NOT NULL DEFAULT '',
                chapter_id TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Formula Sheet',
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                filename TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                uploaded_by TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS custom_formulas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_level TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                chapter_title TEXT NOT NULL,
                name TEXT NOT NULL,
                formula_text TEXT NOT NULL,
                where_terms TEXT NOT NULL DEFAULT '',
                application_note TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS custom_quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id TEXT NOT NULL,
                question_text TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_option_index INTEGER NOT NULL,
                explanation TEXT NOT NULL DEFAULT '',
                hint TEXT NOT NULL DEFAULT '',
                difficulty TEXT NOT NULL DEFAULT 'medium',
                question_type TEXT NOT NULL DEFAULT 'conceptual',
                created_at INTEGER NOT NULL
            );
            """
        )


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now_ms() -> int:
    return int(time.time() * 1000)


# --- Bookmarks ---
def list_bookmarks(session_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bookmarks WHERE session_id = ? ORDER BY timestamp DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_bookmark(
    session_id: str,
    item_id: str,
    class_level: str,
    subject_id: str,
    item_type: str,
    title: str,
    snippet: str,
) -> dict[str, Any]:
    ts = _now_ms()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO bookmarks
            (session_id, item_id, class_level, subject_id, item_type, title, snippet, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, item_id, class_level, subject_id, item_type, title, snippet, ts),
        )
    return {
        "session_id": session_id,
        "item_id": item_id,
        "class_level": class_level,
        "subject_id": subject_id,
        "item_type": item_type,
        "title": title,
        "snippet": snippet,
        "timestamp": ts,
    }


def remove_bookmark(session_id: str, item_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM bookmarks WHERE session_id = ? AND item_id = ?",
            (session_id, item_id),
        )


# --- Quiz Attempts & Chapter Progress ---
def record_quiz_attempt(
    session_id: str,
    chapter_id: str,
    chapter_title: str,
    subject_name: str,
    class_level: str,
    score: int,
    total_questions: int,
    time_taken_seconds: int = 0,
) -> dict[str, Any]:
    ts = _now_ms()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO quiz_attempts
            (session_id, chapter_id, chapter_title, subject_name, class_level, score, total_questions, time_taken_seconds, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, chapter_id, chapter_title, subject_name, class_level, score, total_questions, time_taken_seconds, ts),
        )
        attempt_id = cur.lastrowid

        existing = conn.execute(
            "SELECT * FROM chapter_progress WHERE session_id = ? AND chapter_id = ?",
            (session_id, chapter_id),
        ).fetchone()
        if existing:
            new_high = max(existing["quiz_high_score"], score)
            new_count = existing["quiz_attempts_count"] + 1
            conn.execute(
                """
                UPDATE chapter_progress
                SET quiz_high_score = ?, quiz_attempts_count = ?, last_accessed = ?
                WHERE session_id = ? AND chapter_id = ?
                """,
                (new_high, new_count, ts, session_id, chapter_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO chapter_progress
                (session_id, chapter_id, is_read, quiz_high_score, quiz_attempts_count, last_accessed)
                VALUES (?, ?, 0, ?, 1, ?)
                """,
                (session_id, chapter_id, score, ts),
            )
    return {"id": attempt_id, "timestamp": ts}


def list_quiz_attempts(session_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM quiz_attempts WHERE session_id = ? ORDER BY timestamp DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_chapter_read(session_id: str, chapter_id: str, is_read: bool = True) -> dict[str, Any]:
    ts = _now_ms()
    read_val = 1 if is_read else 0
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM chapter_progress WHERE session_id = ? AND chapter_id = ?",
            (session_id, chapter_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE chapter_progress SET is_read = ?, last_accessed = ? WHERE session_id = ? AND chapter_id = ?",
                (read_val, ts, session_id, chapter_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO chapter_progress (session_id, chapter_id, is_read, quiz_high_score, quiz_attempts_count, last_accessed)
                VALUES (?, ?, ?, 0, 0, ?)
                """,
                (session_id, chapter_id, read_val, ts),
            )
    return {"chapter_id": chapter_id, "is_read": is_read, "last_accessed": ts}


def list_chapter_progress(session_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM chapter_progress WHERE session_id = ? ORDER BY last_accessed DESC",
            (session_id,),
        ).fetchall()
        return [{**dict(r), "is_read": bool(r["is_read"])} for r in rows]


# --- Practice Paper Attempts ---
def record_paper_attempt(
    session_id: str,
    paper_id: str,
    paper_title: str,
    subject_name: str,
    class_level: str,
    marks_obtained: int,
    total_marks: int,
) -> dict[str, Any]:
    ts = _now_ms()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO paper_attempts
            (session_id, paper_id, paper_title, subject_name, class_level, marks_obtained, total_marks, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, paper_id, paper_title, subject_name, class_level, marks_obtained, total_marks, ts),
        )
        return {"id": cur.lastrowid, "timestamp": ts}


def list_paper_attempts(session_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_attempts WHERE session_id = ? ORDER BY timestamp DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- User Notes ---
def list_user_notes(session_id: str, chapter_id: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if chapter_id:
            rows = conn.execute(
                "SELECT * FROM user_notes WHERE session_id = ? AND chapter_id = ? ORDER BY timestamp DESC",
                (session_id, chapter_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM user_notes WHERE session_id = ? ORDER BY timestamp DESC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def add_user_note(session_id: str, chapter_id: str, chapter_title: str, note_text: str) -> dict[str, Any]:
    ts = _now_ms()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO user_notes (session_id, chapter_id, chapter_title, note_text, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, chapter_id, chapter_title, note_text, ts),
        )
        return {
            "id": cur.lastrowid,
            "session_id": session_id,
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "note_text": note_text,
            "timestamp": ts,
        }


def delete_user_note(session_id: str, note_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM user_notes WHERE session_id = ? AND id = ?",
            (session_id, note_id),
        )


# --- Admin: Files, Custom Formulas, Custom Quizzes ---
def add_admin_file(
    class_level: str,
    subject_id: str,
    chapter_id: str,
    category: str,
    title: str,
    description: str,
    filename: str,
    stored_name: str,
    file_size: int,
    mime_type: str,
    uploaded_by: str,
) -> dict[str, Any]:
    ts = _now_ms()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO admin_files
            (class_level, subject_id, chapter_id, category, title, description, filename, stored_name, file_size, mime_type, uploaded_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (class_level, subject_id, chapter_id, category, title, description, filename, stored_name, file_size, mime_type, uploaded_by, ts),
        )
        row = conn.execute("SELECT * FROM admin_files WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_admin_files(class_level: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if class_level:
            rows = conn.execute(
                "SELECT * FROM admin_files WHERE class_level = ? ORDER BY created_at DESC",
                (class_level,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM admin_files ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_admin_file(file_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM admin_files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None


def delete_admin_file(file_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM admin_files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM admin_files WHERE id = ?", (file_id,))
        return dict(row)


def add_custom_formula(
    class_level: str,
    subject_id: str,
    chapter_id: str,
    chapter_title: str,
    name: str,
    formula_text: str,
    where_terms: str,
    application_note: str,
) -> dict[str, Any]:
    ts = _now_ms()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO custom_formulas
            (class_level, subject_id, chapter_id, chapter_title, name, formula_text, where_terms, application_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (class_level, subject_id, chapter_id, chapter_title, name, formula_text, where_terms, application_note, ts),
        )
        return {
            "id": f"custom_f_{cur.lastrowid}",
            "db_id": cur.lastrowid,
            "subjectId": subject_id,
            "chapterId": chapter_id,
            "chapterTitle": chapter_title,
            "name": name,
            "formulaText": formula_text,
            "whereTerms": where_terms,
            "applicationNote": application_note,
            "classLevel": class_level,
            "isCustom": True,
        }


def list_custom_formulas(class_level: str | None = None, chapter_id: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        query = "SELECT * FROM custom_formulas"
        clauses = []
        params: list[Any] = []
        if class_level:
            clauses.append("class_level = ?")
            params.append(class_level)
        if chapter_id:
            clauses.append("chapter_id = ?")
            params.append(chapter_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, tuple(params)).fetchall()
        return [
            {
                "id": f"custom_f_{r['id']}",
                "db_id": r["id"],
                "subjectId": r["subject_id"],
                "chapterId": r["chapter_id"],
                "chapterTitle": r["chapter_title"],
                "name": r["name"],
                "formulaText": r["formula_text"],
                "whereTerms": r["where_terms"],
                "applicationNote": r["application_note"],
                "classLevel": r["class_level"],
                "isCustom": True,
            }
            for r in rows
        ]


def delete_custom_formula(db_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM custom_formulas WHERE id = ?", (db_id,))


def add_custom_quiz(
    chapter_id: str,
    question_text: str,
    options: list[str],
    correct_option_index: int,
    explanation: str,
    hint: str,
    difficulty: str,
    question_type: str,
) -> dict[str, Any]:
    ts = _now_ms()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO custom_quizzes
            (chapter_id, question_text, options_json, correct_option_index, explanation, hint, difficulty, question_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chapter_id, question_text, json.dumps(options), correct_option_index, explanation, hint, difficulty, question_type, ts),
        )
        return {
            "id": f"custom_q_{cur.lastrowid}",
            "db_id": cur.lastrowid,
            "chapterId": chapter_id,
            "questionText": question_text,
            "options": options,
            "correctOptionIndex": correct_option_index,
            "explanation": explanation,
            "hint": hint,
            "difficulty": difficulty,
            "questionType": question_type,
            "isCustom": True,
        }


def list_custom_quizzes(chapter_id: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if chapter_id:
            rows = conn.execute(
                "SELECT * FROM custom_quizzes WHERE chapter_id = ? ORDER BY created_at DESC",
                (chapter_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM custom_quizzes ORDER BY created_at DESC").fetchall()
        return [
            {
                "id": f"custom_q_{r['id']}",
                "db_id": r["id"],
                "chapterId": r["chapter_id"],
                "questionText": r["question_text"],
                "options": json.loads(r["options_json"]),
                "correctOptionIndex": r["correct_option_index"],
                "explanation": r["explanation"],
                "hint": r["hint"],
                "difficulty": r["difficulty"],
                "questionType": r["question_type"],
                "isCustom": True,
            }
            for r in rows
        ]


def delete_custom_quiz(db_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM custom_quizzes WHERE id = ?", (db_id,))


def list_all_students_summary() -> list[dict[str, Any]]:
    """Aggregate activity across all student sessions for Admin Studio."""
    with get_conn() as conn:
        session_rows = conn.execute(
            """
            SELECT session_id FROM quiz_attempts
            UNION
            SELECT session_id FROM paper_attempts
            UNION
            SELECT session_id FROM chapter_progress
            UNION
            SELECT session_id FROM bookmarks
            UNION
            SELECT session_id FROM user_notes
            """
        ).fetchall()

        students: list[dict[str, Any]] = []
        for row in session_rows:
            sid = row["session_id"]
            quiz_stats = conn.execute(
                """
                SELECT COUNT(*) AS cnt,
                       COALESCE(AVG(CASE WHEN total_questions > 0 THEN (score * 100.0 / total_questions) END), 0) AS avg_pct,
                       MAX(timestamp) AS last_ts
                FROM quiz_attempts WHERE session_id = ?
                """,
                (sid,),
            ).fetchone()
            paper_stats = conn.execute(
                "SELECT COUNT(*) AS cnt, MAX(timestamp) AS last_ts FROM paper_attempts WHERE session_id = ?",
                (sid,),
            ).fetchone()
            chap_stats = conn.execute(
                """
                SELECT SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) AS read_cnt,
                       COUNT(*) AS touched_cnt,
                       MAX(last_accessed) AS last_ts
                FROM chapter_progress WHERE session_id = ?
                """,
                (sid,),
            ).fetchone()
            bm_cnt = conn.execute(
                "SELECT COUNT(*) AS cnt, MAX(timestamp) AS last_ts FROM bookmarks WHERE session_id = ?",
                (sid,),
            ).fetchone()
            note_cnt = conn.execute(
                "SELECT COUNT(*) AS cnt, MAX(timestamp) AS last_ts FROM user_notes WHERE session_id = ?",
                (sid,),
            ).fetchone()
            cls_rows = conn.execute(
                """
                SELECT DISTINCT class_level FROM quiz_attempts WHERE session_id = ?
                UNION
                SELECT DISTINCT class_level FROM paper_attempts WHERE session_id = ?
                UNION
                SELECT DISTINCT class_level FROM bookmarks WHERE session_id = ?
                """,
                (sid, sid, sid),
            ).fetchall()

            last_active = max(
                int(quiz_stats["last_ts"] or 0),
                int(paper_stats["last_ts"] or 0),
                int(chap_stats["last_ts"] or 0),
                int(bm_cnt["last_ts"] or 0),
                int(note_cnt["last_ts"] or 0),
            )
            students.append(
                {
                    "session_id": sid,
                    "classes": [c["class_level"] for c in cls_rows if c["class_level"]],
                    "quiz_count": int(quiz_stats["cnt"] or 0),
                    "avg_quiz_pct": round(float(quiz_stats["avg_pct"] or 0), 1),
                    "paper_count": int(paper_stats["cnt"] or 0),
                    "chapters_read": int(chap_stats["read_cnt"] or 0),
                    "chapters_touched": int(chap_stats["touched_cnt"] or 0),
                    "bookmarks_count": int(bm_cnt["cnt"] or 0),
                    "notes_count": int(note_cnt["cnt"] or 0),
                    "last_active": last_active,
                }
            )

        students.sort(key=lambda s: s["last_active"], reverse=True)
        return students


def get_student_detail(session_id: str) -> dict[str, Any]:
    """Return full study records for a single student session."""
    return {
        "session_id": session_id,
        "quiz_attempts": list_quiz_attempts(session_id),
        "paper_attempts": list_paper_attempts(session_id),
        "chapter_progress": list_chapter_progress(session_id),
        "bookmarks": list_bookmarks(session_id),
        "user_notes": list_user_notes(session_id),
    }
