import os
from typing import Any
import httpx

TUTOR_MODES = {
    "general": {
        "id": "general",
        "displayName": "Daksh AI Mentor",
        "modelName": os.getenv("GEMINI_MODEL_GENERAL", "gemini-2.5-flash"),
        "tag": "Balanced",
        "description": "Comprehensive step-by-step explanations & board exam guidance",
        "temperature": 0.7,
    },
    "fast": {
        "id": "fast",
        "displayName": "Quick Doubts",
        "modelName": os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash-lite"),
        "tag": "Fast",
        "description": "Instant definitions, quick facts & speedy doubt resolutions",
        "temperature": 0.6,
    },
    "complex": {
        "id": "complex",
        "displayName": "Deep Analysis",
        "modelName": os.getenv("GEMINI_MODEL_COMPLEX", "gemini-2.5-pro"),
        "tag": "Deep Reasoning",
        "description": "Complex derivations, tough numericals & advanced conceptual synthesis",
        "temperature": 0.4,
    },
}

CLASS_LABELS = {
    "class_10": ("Class 10", "Secondary Board"),
    "class_11": ("Class 11", "Senior Secondary"),
    "class_12": ("Class 12", "Senior Board & Entrances"),
}


async def ask_daksh_tutor(
    user_message: str,
    history: list[dict[str, str]],
    class_id: str = "class_10",
    tutor_mode: str = "general",
) -> dict[str, Any]:
    """Send a multi-turn tutoring request to Gemini REST API."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "MY_GEMINI_API_KEY":
        return {
            "configured": False,
            "modelUsed": "none",
            "reply": (
                "Daksh AI Tutor is not configured yet on this server. "
                "Set the `GEMINI_API_KEY` environment variable (in `.env` or your hosting dashboard) "
                "to enable live AI tutoring. All chapters, notes, quizzes, formulas, and practice papers "
                "work offline without an API key!"
            ),
        }

    mode_cfg = TUTOR_MODES.get(tutor_mode, TUTOR_MODES["general"])
    model_name = mode_cfg["modelName"]
    class_name, level_tag = CLASS_LABELS.get(class_id, ("Class 10", "Secondary Board"))

    system_instruction = (
        f"You are Daksh, an expert, enthusiastic and patient academic tutor and exam preparation mentor "
        f"for students in {class_name} ({level_tag}).\n"
        "The student is actively preparing for school and board examinations in core subjects including "
        "Physics, Chemistry, Mathematics, Biology, Social Science, English, and Computer Science.\n\n"
        "Your guidelines:\n"
        f"1. Always tailor your explanations to the {class_name} syllabus level (e.g. NCERT / CBSE curriculum).\n"
        "2. Structure your responses with clear headings, bullet points, and numbered steps.\n"
        "3. When explaining numerical problems or derivations, clearly show:\n"
        "   - Given variables and values\n"
        "   - Applicable formulas and physical laws\n"
        "   - Step-by-step algebraic substitution\n"
        "   - Final answer with proper SI units\n"
        "4. For subjective questions, highlight key keywords that examiners award marks for.\n"
        "5. Highlight common student pitfalls and board exam tips where relevant.\n"
        "6. Maintain an encouraging, motivating tone. Be concise, mathematically accurate, and avoid unnecessary fluff."
    )

    contents = []
    for msg in history[-10:]:
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        role = "user" if msg.get("sender") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": text}]})

    contents.append({"role": "user", "parts": [{"text": user_message}]})

    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": {
            "temperature": mode_cfg["temperature"],
            "topP": 0.95,
        },
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload)

    if resp.status_code != 200:
        try:
            err_msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
        except Exception:
            err_msg = f"HTTP {resp.status_code}"
        raise RuntimeError(f"Gemini API Error ({model_name}): {err_msg}")

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("No response received from Gemini.")

    parts = candidates[0].get("content", {}).get("parts") or []
    reply_text = parts[0].get("text", "") if parts else ""
    if not reply_text.strip():
        raise RuntimeError("Empty answer returned by model.")

    return {
        "configured": True,
        "modelUsed": model_name,
        "reply": reply_text,
    }
