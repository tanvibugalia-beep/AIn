"""
Gemini AI Client module for Daksh Intelligence.
Ported from TypeScript (server.ts and src/services/api.ts).

Supports:
- google-genai official Python SDK
- Graceful REST API fallback using standard library urllib if SDK is not yet installed
- Streaming response generator
- Multi-tier model fallback (gemini-2.5-flash, gemini-1.5-flash, gemini-2.0-flash, gemini-3.1-flash-lite)
- Knowledge Base grounding context injection
- Active tasks context injection
- File/Image attachment handling
- Quick Tools (PowerShell generator, Bash generator, Code debugger, Regex builder, Summarizer)
- Text to Speech (TTS) and Audio Transcription
"""

import os
import json
import base64
import urllib.request
import urllib.error
from typing import List, Dict, Any, Generator, Optional

CANDIDATE_MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
]

DEFAULT_SYSTEM_INSTRUCTION = """You are Daksh Intelligence, a state-of-the-art PC Desktop AI Assistant and Workstation Copilot, engineered and owned by Daksh Bugalia.
You specialize in helping users on their personal computers with:
1. Answering questions using your built-in knowledge base, citing ingested source documents and URLs accurately.
2. Short-term conversational memory: recall earlier user statements, questions, code, and preferences within this session.
3. Managing user tasks, deadlines, and reminders.
4. Programming, script automation (PowerShell, Bash, Python, JS, C++, Rust, etc.), debugging, and software architecture.
5. System workflows, shortcuts, file organization, terminal commands, and productivity.
When asked who built or owns you, proudly state that you are Daksh Intelligence, personal PC copilot created and owned by Daksh Bugalia. Maintain a polite, razor-sharp, and resourceful PC assistant demeanor."""

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._sdk_client = None
        self._init_sdk()

    def _init_sdk(self):
        """Attempts to initialize the modern google-genai SDK if available."""
        if not self.api_key:
            return
        try:
            from google import genai
            self._sdk_client = genai.Client(api_key=self.api_key)
        except Exception:
            self._sdk_client = None

    def set_api_key(self, key: str):
        self.api_key = key.strip()
        self._init_sdk()

    def build_effective_system_instruction(
        self,
        base_instruction: Optional[str] = None,
        knowledge_context: Optional[str] = None,
        task_context: Optional[str] = None,
    ) -> str:
        effective = base_instruction or DEFAULT_SYSTEM_INSTRUCTION
        if knowledge_context and knowledge_context.strip():
            effective += f"\n\n=== INGESTED KNOWLEDGE BASE CONTEXT ===\n" \
                         f"The user has provided the following verified knowledge base documents/URLs. " \
                         f"Always reference and prioritize this information when answering user questions relevant to these topics, " \
                         f"and cite the document title or source URL:\n" \
                         f"{knowledge_context}\n" \
                         f"======================================="

        if task_context and task_context.strip():
            effective += f"\n\n=== USER'S ACTIVE TASKS & REMINDERS ===\n" \
                         f"{task_context}\n" \
                         f"If the user asks about their tasks or asks you to modify/add a task, refer to this list.\n" \
                         f"======================================="

        return effective

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        file_attachment: Optional[Dict[str, Any]] = None,
        knowledge_context: Optional[str] = None,
        task_context: Optional[str] = None,
        preferred_model: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Streams response chunks from Gemini for a conversational exchange.
        Yields text chunks as they arrive.
        """
        if not self.api_key:
            yield "⚠️ **GEMINI_API_KEY is not configured.** Please enter your Gemini API key in the sidebar."
            return

        effective_system = self.build_effective_system_instruction(
            system_instruction, knowledge_context, task_context
        )

        # Retain last 12 messages for memory
        memory_messages = messages[-12:] if len(messages) > 12 else messages

        # Build contents structure
        contents = []
        for i, msg in enumerate(memory_messages):
            role = "model" if msg.get("role") in ["assistant", "model"] else "user"
            parts = []

            # If user message is the last one and includes an attachment
            if i == len(memory_messages) - 1 and file_attachment:
                mime_type = file_attachment.get("mimeType", "")
                data_b64 = file_attachment.get("data", "")
                text_content = file_attachment.get("text", "")

                if mime_type.startswith("image/") and data_b64:
                    parts.append({
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": data_b64,
                        }
                    })
                elif text_content:
                    fname = file_attachment.get("name", "document")
                    parts.append({
                        "text": f"[Attached File: {fname}]\n```\n{text_content}\n```\n\n"
                    })

            content_text = msg.get("content", "")
            if content_text or parts:
                if content_text:
                    parts.append({"text": content_text})
                contents.append({"role": role, "parts": parts})

        models_to_try = [preferred_model] if preferred_model else CANDIDATE_MODELS
        for m in CANDIDATE_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        # Try with official SDK first
        if self._sdk_client:
            for model_name in models_to_try:
                try:
                    from google.genai import types
                    config = types.GenerateContentConfig(
                        system_instruction=effective_system,
                        temperature=max(0.0, min(1.5, float(temperature))),
                    )
                    stream = self._sdk_client.models.generate_content_stream(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    for chunk in stream:
                        if hasattr(chunk, "text") and chunk.text:
                            yield chunk.text
                    return
                except Exception as sdk_err:
                    err_str = str(sdk_err)
                    # If model not found or overloaded, continue to next candidate
                    continue

        # Fallback to direct REST API streaming
        last_error = None
        for model_name in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?key={self.api_key}&alt=sse"
                payload = {
                    "contents": contents,
                    "systemInstruction": {
                        "parts": [{"text": effective_system}]
                    },
                    "generationConfig": {
                        "temperature": max(0.0, min(1.5, float(temperature))),
                    }
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=30) as response:
                    buffer = ""
                    for line_bytes in response:
                        line = line_bytes.decode("utf-8", errors="replace")
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                parsed = json.loads(data_str)
                                candidates = parsed.get("candidates", [])
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts", [])
                                    for part in parts:
                                        if "text" in part:
                                            yield part["text"]
                            except Exception:
                                pass
                return
            except urllib.error.HTTPError as e:
                try:
                    err_body = json.loads(e.read().decode("utf-8", errors="replace"))
                    msg = err_body.get("error", {}).get("message", e.reason)
                except Exception:
                    msg = str(e)
                last_error = f"Model {model_name} error: {msg}"
                continue
            except Exception as e:
                last_error = str(e)
                continue

        yield f"\n\n⚠️ **Error communicating with Gemini:** {last_error or 'Unable to generate response. Check your API key and network connection.'}"

    def run_quick_tool(self, tool_type: str, user_input: str, context: Optional[str] = None) -> str:
        """
        Executes a specialized prompt for PC automation, debugging, or summarization.
        Replicates /api/quick-tool from server.ts.
        """
        if not self.api_key:
            return "Error: GEMINI_API_KEY is not configured."

        system_instruction = "You are a specialized PC desktop productivity utility."
        if tool_type == "powershell_generator":
            system_instruction = "You are a Windows PowerShell and Command Line automation expert. Provide safe, robust scripts with comments and error checking."
            prompt = f"Generate a safe, robust PowerShell script for the following task. Include comments and safety flags:\n\nTask: {user_input}\nContext: {context or 'Windows PC'}"
        elif tool_type == "bash_generator":
            system_instruction = "You are a Linux/macOS Bash terminal automation expert."
            prompt = f"Generate an efficient, robust shell/Bash script for the following task. Include error handling (set -euo pipefail if appropriate) and usage comments:\n\nTask: {user_input}\nContext: {context or 'Unix PC'}"
        elif tool_type == "code_debugger":
            system_instruction = "You are a senior code architect and debugger."
            prompt = f"Analyze this code snippet or error stack trace. Identify root cause, provide fixed code, and explain why:\n\n{user_input}"
        elif tool_type == "regex_builder":
            system_instruction = "You are a Regular Expression specialist."
            prompt = f"Create a regex matching the following requirements, explain each token, and provide test sample matches:\n\nRequirement: {user_input}"
        elif tool_type == "summarizer":
            system_instruction = "You are a concise executive summarizer."
            prompt = f"Provide a structured summary of the following content with key takeaways and actionable points:\n\n{user_input}"
        else:
            prompt = user_input

        # Collect response
        chunks = []
        for chunk in self.stream_chat(
            messages=[{"role": "user", "content": prompt}],
            system_instruction=system_instruction,
            temperature=0.3,
        ):
            chunks.append(chunk)

        return "".join(chunks).strip()

    def generate_speech_audio(self, text: str, voice: str = "Kore") -> Optional[str]:
        """
        Generates audio using gemini-3.8-flash-lite-tts or returns None.
        Returns base64 encoded audio string if successful.
        """
        clean_text = text[:800]
        if self._sdk_client:
            try:
                from google.genai import types
                response = self._sdk_client.models.generate_content(
                    model="gemini-3.8-flash-lite-tts",
                    contents=[clean_text],
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice
                                )
                            )
                        )
                    )
                )
                candidates = getattr(response, "candidates", [])
                if candidates:
                    parts = candidates[0].content.parts
                    for p in parts:
                        if hasattr(p, "inline_data") and p.inline_data:
                            return base64.b64encode(p.inline_data.data).decode("utf-8")
            except Exception:
                pass
        return None
