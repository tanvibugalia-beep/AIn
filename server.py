"""
Daksh Intelligence - FastAPI Backend Server
Direct 1-to-1 Python conversion of server.ts.

Provides REST and SSE streaming endpoints:
- GET  /api/health
- POST /api/knowledge/fetch-url
- POST /api/chat (SSE streaming with short-term memory, knowledge base, tasks, and attachments)
- POST /api/quick-tool (PowerShell, Bash, Code Debugger, Regex, Summarizer)
- POST /api/voice/tts
- POST /api/voice/transcribe
- Static file serving (dist/ fallback)
"""

import os
import sys
import json
import base64
from typing import List, Optional, Any, Dict
from datetime import datetime

# Ensure current directory is on sys.path for robust module loading anywhere
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from scraper import fetch_url_content
from gemini_client import GeminiClient

app = FastAPI(
    title="Daksh Intelligence API",
    description="PC Desktop AI Assistant & Copilot API created by Daksh Bugalia",
    version="1.0.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client = GeminiClient(api_key=API_KEY)

# ----------------- DATA MODELS -----------------

class FetchUrlRequest(BaseModel):
    url: str

class ChatMessageModel(BaseModel):
    role: str
    content: Optional[str] = ""

class FileAttachmentModel(BaseModel):
    name: Optional[str] = "file"
    mimeType: Optional[str] = ""
    data: Optional[str] = None  # Base64
    text: Optional[str] = None

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    systemInstruction: Optional[str] = None
    temperature: Optional[float] = 0.7
    fileAttachment: Optional[Dict[str, Any]] = None
    knowledgeContext: Optional[str] = None
    taskContext: Optional[str] = None

class QuickToolRequest(BaseModel):
    toolType: str
    input: str
    context: Optional[str] = None

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "Kore"

class TranscribeRequest(BaseModel):
    audioData: str
    mimeType: Optional[str] = "audio/webm"

class LoginRequest(BaseModel):
    email: str
    password: Optional[str] = ""
    authProvider: Optional[str] = "password"

class RunCodeRequest(BaseModel):
    code: str

# ----------------- ROUTES -----------------

@app.post("/api/auth/login")
def api_login(req: LoginRequest):
    email_clean = req.email.lower().strip()
    is_owner = email_clean in ["dakshbugalia1@gmail.com", "dakshbugalia1@gamil.com"]
    owner_pwd = os.environ.get("OWNER_PASSWORD", "daksh2026")

    if is_owner:
        if req.password != owner_pwd:
            raise HTTPException(status_code=401, detail="Invalid Owner Security Password. Access to dakshbugalia1@gmail.com denied.")
        return {
            "success": True,
            "user": {
                "id": "usr-daksh-owner",
                "name": "Daksh Bugalia",
                "email": "dakshbugalia1@gmail.com",
                "role": "Owner & System Administrator",
                "isOwner": True,
                "isGuest": False,
                "authProvider": req.authProvider or "password",
            }
        }

    # Public Member Login
    user_name = req.email.split("@")[0].capitalize()
    return {
        "success": True,
        "user": {
            "id": f"usr-{int(datetime.utcnow().timestamp())}",
            "name": user_name,
            "email": req.email,
            "role": "Verified Member",
            "isOwner": False,
            "isGuest": False,
            "authProvider": req.authProvider or "google",
        }
    }


@app.get("/api/health")
def health_check():
    key = os.environ.get("GEMINI_API_KEY", gemini_client.api_key)
    return {
        "status": "ok",
        "version": "2.5.0",
        "hasApiKey": bool(key and len(key) > 5),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model": "gemini-2.5-flash",
        "app": "Daksh Intelligence",
        "owner": "Daksh Bugalia",
    }

@app.post("/api/knowledge/fetch-url")
def api_fetch_url(req: FetchUrlRequest):
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="Valid URL is required")
    res = fetch_url_content(req.url)
    if not res["success"]:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@app.post("/api/chat")
def api_chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="Messages array is required.")

    # Generator for Server-Sent Events (SSE)
    def sse_event_stream():
        try:
            stream = gemini_client.stream_chat(
                messages=req.messages,
                system_instruction=req.systemInstruction,
                temperature=req.temperature or 0.7,
                file_attachment=req.fileAttachment,
                knowledge_context=req.knowledgeContext,
                task_context=req.taskContext,
            )
            for chunk in stream:
                if chunk:
                    data_payload = json.dumps({"text": chunk})
                    yield f"data: {data_payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            err_payload = json.dumps({"error": str(e)})
            yield f"data: {err_payload}\n\n"

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/api/quick-tool")
def api_quick_tool(req: QuickToolRequest):
    if not req.input:
        raise HTTPException(status_code=400, detail="Input text is required")
    try:
        result = gemini_client.run_quick_tool(
            tool_type=req.toolType,
            user_input=req.input,
            context=req.context,
        )
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/tts")
def api_tts(req: TTSRequest):
    if not req.text:
        raise HTTPException(status_code=400, detail="Text is required for TTS")
    audio_b64 = gemini_client.generate_speech_audio(req.text, voice=req.voice or "Kore")
    if audio_b64:
        return {"audio": audio_b64, "mimeType": "audio/wav"}
    raise HTTPException(status_code=500, detail="TTS generation failed or model not available")

@app.post("/api/voice/transcribe")
def api_transcribe(req: TranscribeRequest):
    if not req.audioData:
        raise HTTPException(status_code=400, detail="Audio data is required")
    # Clean base64 header if present
    clean_b64 = req.audioData.split(",")[1] if "," in req.audioData else req.audioData
    # Transcribe via client
    try:
        if gemini_client._sdk_client:
            from google.genai import types
            audio_bytes = base64.b64decode(clean_b64)
            response = gemini_client._sdk_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=req.mimeType or "audio/webm"),
                    "Transcribe this spoken speech accurately. Return ONLY the transcribed text in the language spoken.",
                ],
            )
            return {"transcript": response.text.strip() if response.text else ""}
    except Exception as e:
        pass
    return {"transcript": ""}

@app.post("/api/code/run")
def api_run_code(req: RunCodeRequest):
    if not req.code or not req.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")
    
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "-c", req.code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out (10-second limit reached).",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }

@app.get("/logo.jpg")
def get_logo():
    for candidate in [
        os.path.join(BASE_DIR, "logo.jpg"),
        os.path.join(BASE_DIR, "dist", "logo.jpg"),
        os.path.join(BASE_DIR, "public", "logo.jpg"),
        os.path.join(BASE_DIR, "src", "assets", "logo.jpg"),
    ]:
        if os.path.exists(candidate):
            return FileResponse(candidate, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Logo not found")

@app.get("/")
@app.get("/index.html")
def get_index():
    for candidate in [
        os.path.join(BASE_DIR, "index.html"),
        os.path.join(BASE_DIR, "dist", "index.html"),
    ]:
        if os.path.exists(candidate):
            return FileResponse(candidate, media_type="text/html")
    raise HTTPException(status_code=404, detail="index.html not found")

# Catch-all for assets or Single Page Application routes
@app.get("/{full_path:path}")
def serve_spa_or_static(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    for folder in [BASE_DIR, os.path.join(BASE_DIR, "dist"), os.path.join(BASE_DIR, "public")]:
        candidate = os.path.join(folder, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)

    for candidate in [
        os.path.join(BASE_DIR, "index.html"),
        os.path.join(BASE_DIR, "dist", "index.html"),
    ]:
        if os.path.exists(candidate):
            return FileResponse(candidate, media_type="text/html")

    raise HTTPException(status_code=404, detail="Not Found")

if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading

    port = int(os.environ.get("PORT", 3000))
    url = f"http://localhost:{port}"
    is_cloud = bool(os.environ.get("SPACE_ID") or port == 7860)

    print(f"================================================================")
    print(f"  DAKSH INTELLIGENCE - PERSONAL PC AI WORKSTATION (PYTHON)")
    print(f"  Server active on port: {port}")
    print(f"================================================================")

    if not is_cloud:
        try:
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        except Exception:
            pass

    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=not is_cloud)


