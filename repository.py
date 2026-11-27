import json
from pathlib import Path
from typing import Any

from . import database as db

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "study_data.json"


class StudyRepository:
    """Repository for Class 10, 11, and 12 study material + admin-added resources."""

    def __init__(self, data_path: Path = DATA_PATH):
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        self.classes: list[dict[str, Any]] = raw.get("classes", [])
        self.subjects: list[dict[str, Any]] = raw.get("subjects", [])
        self.chapters: list[dict[str, Any]] = raw.get("chapters", [])
        self.notes: dict[str, dict[str, Any]] = raw.get("notes", {})
        self.fallback_notes: dict[str, dict[str, Any]] = raw.get("fallback_notes", {})
        self.quizzes: dict[str, list[dict[str, Any]]] = raw.get("quizzes", {})
        self.practice_papers: list[dict[str, Any]] = raw.get("practice_papers", [])

    def get_classes(self) -> list[dict[str, Any]]:
        return self.classes

    def get_class_by_id(self, class_id: str) -> dict[str, Any] | None:
        return next((c for c in self.classes if c["id"] == class_id), None)

    def get_subjects_for_class(self, class_id: str) -> list[dict[str, Any]]:
        return [s for s in self.subjects if s["classLevel"] == class_id]

    def get_subject_by_id(self, subject_id: str) -> dict[str, Any] | None:
        return next((s for s in self.subjects if s["id"] == subject_id), None)

    def get_chapters_for_subject(self, subject_id: str) -> list[dict[str, Any]]:
        return [c for c in self.chapters if c["subjectId"] == subject_id]

    def get_chapters_for_class(self, class_id: str) -> list[dict[str, Any]]:
        return [c for c in self.chapters if c["classLevel"] == class_id]

    def get_chapter_by_id(self, chapter_id: str) -> dict[str, Any] | None:
        return next((c for c in self.chapters if c["id"] == chapter_id), None)

    def get_notes_for_chapter(self, chapter_id: str) -> dict[str, Any]:
        if chapter_id in self.notes:
            cloned = json.loads(json.dumps(self.notes[chapter_id]))
        else:
            chapter = self.get_chapter_by_id(chapter_id)
            class_id = chapter["classLevel"] if chapter else "class_10"
            title = chapter["title"] if chapter else "Chapter Study"
            fb = self.fallback_notes.get(class_id) or next(iter(self.fallback_notes.values()), {})
            cloned = json.loads(json.dumps(fb))
            cloned["chapterId"] = chapter_id
            if not cloned.get("overview"):
                cloned["overview"] = f"High-yield study notes for {title}."

        # Merge admin-added custom formulas for this chapter
        custom_f = db.list_custom_formulas(chapter_id=chapter_id)
        if custom_f:
            existing_formulas = cloned.get("formulas", [])
            cloned["formulas"] = custom_f + existing_formulas
        return cloned

    def get_quiz_for_chapter(self, chapter_id: str) -> list[dict[str, Any]]:
        base_questions: list[dict[str, Any]] = []
        if chapter_id in self.quizzes and self.quizzes[chapter_id]:
            base_questions = list(self.quizzes[chapter_id])
        else:
            chapter = self.get_chapter_by_id(chapter_id)
            title = chapter["title"] if chapter else "Chapter Study"
            subtitle = chapter["subtitle"] if chapter else "Core Concepts"
            base_questions = [
                {
                    "id": f"{chapter_id}_gen_1",
                    "chapterId": chapter_id,
                    "questionText": f"Which core principle best summarizes the foundation of {title} ({subtitle})?",
                    "options": [
                        "Conservation laws and governing quantitative relationships",
                        "Arbitrary assumptions independent of boundary conditions",
                        "Non-reproducible empirical observations only",
                        "Static equilibrium under infinite external force",
                    ],
                    "correctOptionIndex": 0,
                    "explanation": f"Board syllabi emphasize conservation laws and quantitative relationships in {title}.",
                    "hint": "Focus on fundamental laws and standard definitions.",
                    "difficulty": "easy",
                    "questionType": "conceptual",
                },
                {
                    "id": f"{chapter_id}_gen_2",
                    "chapterId": chapter_id,
                    "questionText": f"When solving board exam numericals or case-based questions in {title}, which step ensures full marking scheme credit?",
                    "options": [
                        "Writing given data, applicable formula, step-by-step substitution, and proper SI units",
                        "Writing only the final numerical value without units",
                        "Skipping intermediate steps to save space",
                        "Using non-standard units without conversion",
                    ],
                    "correctOptionIndex": 0,
                    "explanation": "CBSE/Board marking schemes award step marks for given data, formula, substitution, and final answer with SI units.",
                    "hint": "Think about how board examiners allocate step marking.",
                    "difficulty": "easy",
                    "questionType": "conceptual",
                },
                {
                    "id": f"{chapter_id}_gen_3",
                    "chapterId": chapter_id,
                    "questionText": f"Assertion (A): Dimensional consistency is a necessary condition for any physical/mathematical relation in {title}.\nReason (R): Dimensionally correct formulas are always physically accurate in every scenario.",
                    "options": [
                        "Both A and R are true and R is the correct explanation of A",
                        "Both A and R are true but R is NOT the correct explanation of A",
                        "A is true but R is false",
                        "A is false but R is true",
                    ],
                    "correctOptionIndex": 2,
                    "explanation": "A formula must be dimensionally consistent (A is true), but dimensionless constants like 1/2 cannot be checked by dimensions alone (R is false).",
                    "hint": "Think about dimensionless constants in formulas.",
                    "difficulty": "medium",
                    "questionType": "assertion_reason",
                },
                {
                    "id": f"{chapter_id}_gen_4",
                    "chapterId": chapter_id,
                    "questionText": f"In {title}, why are standard conditions (temperature, reference frame, or domain restrictions) explicitly specified in definitions?",
                    "options": [
                        "Because the governing law or formula holds strictly within those validity limits",
                        "They are optional decorative details with no physical meaning",
                        "They only apply to multiple-choice questions",
                        "They change the SI unit of the final result",
                    ],
                    "correctOptionIndex": 0,
                    "explanation": "Every scientific law and mathematical theorem has well-defined validity conditions (e.g. constant temperature for Ohm's Law, non-zero leading coefficient for quadratics).",
                    "hint": "Recall conditions like 'at constant temperature' or 'a ≠ 0'.",
                    "difficulty": "medium",
                    "questionType": "conceptual",
                },
            ]

        custom_q = db.list_custom_quizzes(chapter_id=chapter_id)
        return custom_q + base_questions

    def get_formulas_for_class(self, class_id: str) -> list[dict[str, Any]]:
        formulas: list[dict[str, Any]] = []
        seen = set()

        for f in db.list_custom_formulas(class_level=class_id):
            if f["id"] not in seen:
                seen.add(f["id"])
                formulas.append(f)

        for ch in self.get_chapters_for_class(class_id):
            notes = self.get_notes_for_chapter(ch["id"])
            for f in notes.get("formulas", []):
                if f["id"] not in seen:
                    seen.add(f["id"])
                    formulas.append(f)
        return formulas

    def get_practice_papers_for_class(self, class_id: str) -> list[dict[str, Any]]:
        return [p for p in self.practice_papers if p["classLevel"] == class_id]

    def get_practice_paper_by_id(self, paper_id: str) -> dict[str, Any] | None:
        return next((p for p in self.practice_papers if p["id"] == paper_id), None)

    def search_material(self, query: str, class_id: str | None = None) -> list[dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return []

        chapters = self.get_chapters_for_class(class_id) if class_id else self.chapters
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for ch in chapters:
            if q in ch["title"].lower() or q in ch["subtitle"].lower() or q in ch["summary"].lower():
                if ch["id"] not in seen_ids:
                    seen_ids.add(ch["id"])
                    results.append(
                        {
                            "type": "CHAPTER",
                            "id": ch["id"],
                            "title": ch["title"],
                            "subtitle": ch["subtitle"],
                            "extraInfo": f"Chapter {ch['chapterNumber']} • {ch['estimatedReadMinutes']} min read",
                            "chapterId": ch["id"],
                            "classLevel": ch["classLevel"],
                        }
                    )

            notes = self.get_notes_for_chapter(ch["id"])
            for concept in notes.get("keyConcepts", []):
                if q in concept["title"].lower() or q in concept["explanation"].lower():
                    cid = f"{ch['id']}_{concept['title']}"
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        results.append(
                            {
                                "type": "CONCEPT",
                                "id": cid,
                                "title": concept["title"],
                                "subtitle": f"Concept in {ch['title']}",
                                "extraInfo": concept.get("keyFormula") or concept.get("examImportance", ""),
                                "chapterId": ch["id"],
                                "classLevel": ch["classLevel"],
                            }
                        )

            for f in notes.get("formulas", []):
                if q in f["name"].lower() or q in f["formulaText"].lower() or q in f["applicationNote"].lower():
                    if f["id"] not in seen_ids:
                        seen_ids.add(f["id"])
                        results.append(
                            {
                                "type": "FORMULA",
                                "id": f["id"],
                                "title": f["name"],
                                "subtitle": f["formulaText"],
                                "extraInfo": f"{ch['title']} • {f['whereTerms']}",
                                "chapterId": ch["id"],
                                "classLevel": ch["classLevel"],
                            }
                        )

        return results[:25]
