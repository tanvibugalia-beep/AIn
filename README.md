# EduPrep With Daksh — Python Public Web App

A public-ready Python (FastAPI + SQLite + Responsive Web UI) version of **EduPrep With Daksh** for Class 10, 11, and 12 exam preparation.

## Features
- **Class 10, 11 & 12 Curriculum**: 13 subjects and 36 chapters with high-yield ratings, estimated reading times, concept cards, mind maps, derivations, and board exam tips.
- **Formula Deck**: Filterable formula reference per class with bookmarking.
- **Interactive Quizzes**: Chapter quizzes with hints, difficulty/type tags, instant explanations, and score tracking.
- **Board Practice Papers**: CBSE-style model papers with interactive MCQs, model answers, and marking schemes.
- **Global Search**: Instant search across chapters, concepts, and formulas.
- **Per-Visitor Progress & Personal Notes**: Session-scoped SQLite storage (`eduprep_session` cookie) so public visitors keep their own bookmarks, quiz scores, read status, and study notes.
- **Daksh AI Tutor**: Server-side Gemini integration with rate limiting and 3 tutor modes (`Daksh AI Mentor`, `Quick Doubts`, `Deep Analysis`).

## Run Locally
```powershell
cd eduprep_app
copy .env.example .env
# Optional: set GEMINI_API_KEY in .env for live AI tutoring
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Or on Windows if uvicorn is not in PATH:
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open `http://localhost:8000` in your browser.

## Deploy Publicly
- **Docker**: `docker build -t eduprep-web . && docker run -p 8000:8000 -e GEMINI_API_KEY=your_key eduprep-web`
- **Render**: Use the included `render.yaml` and set `GEMINI_API_KEY` in the Render dashboard.
- **Railway / Fly.io / Cloud Run**: Start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
