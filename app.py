"""
Daksh Intelligence - Personal PC AI Assistant & Workstation Copilot
Created by Daksh Bugalia. Ported to Pure Python (Streamlit).

Features:
- Real-time AI Chat with multi-model fallback (Gemini 2.5 Flash, 1.5 Flash, 2.0 Flash)
- Multi-persona system (Daksh Core, Nexus Code Architect, Terminal Guru, Echo Executive)
- System Toolkit (PowerShell generator, Bash generator, Code Debugger, Regex Builder, Summarizer)
- Ingested Knowledge Base with live Web URL scraper & document grounding
- Active Task Manager with AI copilot integration
- Interactive Python Code Studio Sandbox with live execution
- Hardware profile detection & session persistence
"""

import os
import sys

# Auto-launch with Streamlit if run via `python app.py` directly
try:
    import streamlit.runtime
    if not streamlit.runtime.exists():
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", os.path.abspath(__file__)]
        sys.exit(stcli.main())
except Exception:
    pass

import io
import time
import json
import base64
import platform
import streamlit as st
from datetime import datetime, timezone
from typing import List, Dict, Any


from defaults import (
    ASSISTANT_PERSONAS,
    PC_QUICK_ACTIONS,
    DEFAULT_KNOWLEDGE_DOCUMENTS,
    DEFAULT_TASKS,
    DEFAULT_ACCOUNT,
)
from scraper import fetch_url_content
from gemini_client import GeminiClient

# Page configuration
st.set_page_config(
    page_title="Daksh Intelligence · PC AI Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Cyber-Workstation Styling
st.markdown("""
<style>
    /* Dark Theme Accent and Typography */
    .stApp {
        background-color: #0b0f17;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    }
    
    /* Header Container */
    .header-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(56, 189, 248, 0.2);
        border-radius: 12px;
        padding: 18px 24px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    .header-title {
        font-size: 1.6rem;
        font-weight: 700;
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    
    .header-subtitle {
        color: #94a3b8;
        font-size: 0.88rem;
        margin-top: 4px;
    }
    
    /* Badge styling */
    .badge-pill {
        background-color: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 9999px;
        padding: 4px 12px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Quick Action Pills */
    .quick-pill {
        background-color: #1e293b;
        color: #cbd5e1;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 0.8rem;
        cursor: pointer;
        display: inline-block;
        margin: 4px;
        transition: all 0.2s ease;
    }
    .quick-pill:hover {
        background-color: #334155;
        color: #38bdf8;
        border-color: #38bdf8;
    }

    /* Cards */
    .kb-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    
    /* Metric boxes */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
        color: #38bdf8;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- SESSION STATE INITIALIZATION -----------------

if "api_key" not in st.session_state:
    st.session_state.api_key = os.environ.get("GEMINI_API_KEY", "")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "knowledge_docs" not in st.session_state:
    st.session_state.knowledge_docs = list(DEFAULT_KNOWLEDGE_DOCUMENTS)

if "tasks" not in st.session_state:
    st.session_state.tasks = list(DEFAULT_TASKS)

if "persona_id" not in st.session_state:
    st.session_state.persona_id = "daksh-core"

if "selected_model" not in st.session_state:
    st.session_state.selected_model = "gemini-2.5-flash"

if "temperature" not in st.session_state:
    st.session_state.temperature = 0.7

if "enable_grounding" not in st.session_state:
    st.session_state.enable_grounding = True

if "enable_task_context" not in st.session_state:
    st.session_state.enable_task_context = True

if "sandbox_code" not in st.session_state:
    st.session_state.sandbox_code = """# Daksh Intelligence - PC Code Studio Sandbox
# Test Python automation, algorithms, or API calls directly
import os
import platform

print("PC Workstation OS:", platform.system(), platform.release())
print("Architecture:", platform.machine())
print("Python Version:", platform.python_version())
"""

# Initialize Gemini Client
gemini_client = GeminiClient(api_key=st.session_state.api_key)

# ----------------- HELPER FUNCTIONS -----------------

def get_current_persona() -> Dict[str, Any]:
    for p in ASSISTANT_PERSONAS:
        if p["id"] == st.session_state.persona_id:
            return p
    return ASSISTANT_PERSONAS[0]

def get_grounding_context() -> str:
    if not st.session_state.enable_grounding or not st.session_state.knowledge_docs:
        return ""
    parts = []
    for doc in st.session_state.knowledge_docs:
        parts.append(f"--- Document: {doc['title']} (Source: {doc.get('sourceUrl') or doc.get('source')}) ---\n{doc['content']}")
    return "\n\n".join(parts)

def get_tasks_context() -> str:
    if not st.session_state.enable_task_context or not st.session_state.tasks:
        return ""
    lines = []
    for t in st.session_state.tasks:
        status = "[DONE]" if t["completed"] else "[PENDING]"
        lines.append(f"- ID {t.get('numericId', 0)}: {status} ({t['priority'].upper()}) {t['title']} (Due: {t.get('dueDate', 'N/A')})")
    return "\n".join(lines)

# ----------------- SIDEBAR CONFIGURATION -----------------

with st.sidebar:
    st.markdown("### ⚡ Daksh Intelligence")
    st.caption("Personal PC AI Assistant & Workstation Copilot")

    # Display logo if found
    logo_path = os.path.join(os.path.dirname(__file__), "public", "logo.jpg")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(os.path.dirname(__file__), "src", "assets", "logo.jpg")
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)

    st.markdown("---")

    # API Key Configuration
    st.markdown("#### 🔑 Gemini API Key")
    key_input = st.text_input(
        "Enter API Key",
        value=st.session_state.api_key,
        type="password",
        help="Get a free key from https://aistudio.google.com/app/apikey",
    )
    if key_input != st.session_state.api_key:
        st.session_state.api_key = key_input
        gemini_client.set_api_key(key_input)
        st.rerun()

    if st.session_state.api_key:
        st.success("API Key Active", icon="✅")
    else:
        st.warning("Please configure your Gemini API Key", icon="⚠️")

    st.markdown("---")

    # Persona Selection
    st.markdown("#### 👤 Assistant Persona")
    persona_options = {p["name"]: p["id"] for p in ASSISTANT_PERSONAS}
    current_persona_name = next(p["name"] for p in ASSISTANT_PERSONAS if p["id"] == st.session_state.persona_id)
    selected_name = st.selectbox(
        "Select Copilot Mode",
        options=list(persona_options.keys()),
        index=list(persona_options.keys()).index(current_persona_name),
    )
    st.session_state.persona_id = persona_options[selected_name]

    cur_p = get_current_persona()
    st.info(f"{cur_p['icon']} **{cur_p['title']}**\n\n{cur_p['description']}")

    st.markdown("---")

    # Advanced Settings Expander
    with st.expander("⚙️ Model & Grounding Controls", expanded=False):
        st.session_state.selected_model = st.selectbox(
            "Gemini Model",
            options=[
                "gemini-2.5-flash",
                "gemini-1.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-pro",
                "gemini-3.1-flash-lite",
            ],
            index=0,
        )
        st.session_state.temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.5,
            value=st.session_state.temperature,
            step=0.05,
        )
        st.session_state.enable_grounding = st.checkbox(
            "Ground responses with Knowledge Base",
            value=st.session_state.enable_grounding,
        )
        st.session_state.enable_task_context = st.checkbox(
            "Inject Active Tasks context into Chat",
            value=st.session_state.enable_task_context,
        )

    st.markdown("---")

    # Workstation Specs
    st.markdown("#### 💻 Workstation Profile")
    st.caption(f"**OS:** {platform.system()} {platform.release()} ({platform.machine()})")
    st.caption(f"**Python:** {platform.python_version()}")
    st.caption(f"**Owner:** Daksh Bugalia")

    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ----------------- MAIN WORKSPACE TABS -----------------

# Workspace Banner
st.markdown("""
<div class="header-card">
    <div>
        <h2 class="header-title">Daksh Intelligence Workstation</h2>
        <div class="header-subtitle">State-of-the-art Personal PC AI Copilot · Engineered by Daksh Bugalia</div>
    </div>
    <div class="badge-pill">Gemini Accelerated</div>
</div>
""", unsafe_allow_html=True)

tab_chat, tab_toolkit, tab_knowledge, tab_tasks, tab_code, tab_profile = st.tabs([
    "💬 AI Copilot",
    "🛠️ System Toolkit",
    "📚 Knowledge Base",
    "📋 Task Manager",
    "💻 Code Studio",
    "⚙️ Profile & System",
])

# ----------------- TAB 1: AI COPILOT (CHAT) -----------------
with tab_chat:
    persona = get_current_persona()
    
    col_p1, col_p2 = st.columns([3, 1])
    with col_p1:
        st.markdown(f"### {persona['icon']} {persona['name']} <span style='font-size:0.85rem; color:#94a3b8;'>({persona['title']})</span>", unsafe_allow_html=True)
    with col_p2:
        if st.session_state.enable_grounding and len(st.session_state.knowledge_docs) > 0:
            st.success(f"📚 {len(st.session_state.knowledge_docs)} Docs Grounded", icon="🟢")
        else:
            st.caption("Grounding: Inactive")

    # Quick action prompt shortcuts
    st.markdown("**Quick Prompts:**")
    quick_cols = st.columns(4)
    for idx, action in enumerate(PC_QUICK_ACTIONS[:4]):
        with quick_cols[idx % 4]:
            if st.button(action["title"], key=f"quick_{action['id']}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": action["prompt"]})
                st.rerun()

    st.markdown("---")

    # Render Chat History
    for msg in st.session_state.messages:
        role = msg["role"]
        with st.chat_message(role, avatar="🧑‍💻" if role == "user" else persona["icon"]):
            st.markdown(msg["content"])
            if "attachment" in msg and msg["attachment"]:
                att = msg["attachment"]
                if att.get("mimeType", "").startswith("image/"):
                    st.image(base64.b64decode(att["data"]), caption=att.get("name", "Image"))
                elif att.get("text"):
                    st.code(att["text"][:1000] + ("..." if len(att["text"]) > 1000 else ""), language="text")

    # Optional File/Image Attachment Expander
    with st.expander("📎 Attach File or Image to next prompt", expanded=False):
        uploaded_file = st.file_uploader(
            "Upload image, script, code, or document",
            type=["png", "jpg", "jpeg", "webp", "py", "ps1", "sh", "txt", "md", "json", "log"],
            key="chat_uploader",
        )

    # Chat Input
    if user_prompt := st.chat_input("Ask Daksh Intelligence anything about programming, PC automation, or tasks..."):
        attachment_data = None
        if uploaded_file is not None:
            bytes_data = uploaded_file.read()
            mime = uploaded_file.type or "application/octet-stream"
            if mime.startswith("image/"):
                attachment_data = {
                    "name": uploaded_file.name,
                    "mimeType": mime,
                    "data": base64.b64encode(bytes_data).decode("utf-8"),
                }
            else:
                try:
                    text_str = bytes_data.decode("utf-8", errors="replace")
                    attachment_data = {
                        "name": uploaded_file.name,
                        "mimeType": mime,
                        "text": text_str,
                    }
                except Exception:
                    pass

        # Append and display user message
        new_user_msg = {"role": "user", "content": user_prompt}
        if attachment_data:
            new_user_msg["attachment"] = attachment_data
        st.session_state.messages.append(new_user_msg)

        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_prompt)
            if attachment_data:
                st.caption(f"📎 Attached: {attachment_data.get('name')}")

        # Stream assistant response
        with st.chat_message("assistant", avatar=persona["icon"]):
            response_placeholder = st.empty()
            full_response = ""

            grounding_text = get_grounding_context()
            task_text = get_tasks_context()

            stream = gemini_client.stream_chat(
                messages=st.session_state.messages,
                system_instruction=persona["systemInstruction"],
                temperature=st.session_state.temperature,
                file_attachment=attachment_data,
                knowledge_context=grounding_text,
                task_context=task_text,
                preferred_model=st.session_state.selected_model,
            )

            for chunk in stream:
                full_response += chunk
                response_placeholder.markdown(full_response + "▌")
            response_placeholder.markdown(full_response)

        # Append assistant message to history
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        st.rerun()

# ----------------- TAB 2: SYSTEM TOOLKIT -----------------
with tab_toolkit:
    st.markdown("### 🛠️ Workstation Automation Toolkit")
    st.caption("Generate ready-to-run scripts, fix difficult stack traces, and summarize documents with PC-specialized models.")

    tool_choice = st.radio(
        "Choose Utility",
        [
            "⚡ PowerShell Script Generator",
            "🐧 Bash / Terminal Automation",
            "🐞 Senior Code Architect & Debugger",
            "🔍 Regular Expression Specialist",
            "📝 Executive Summarizer & Meeting Notes",
        ],
        horizontal=True,
    )

    tool_type_map = {
        "⚡ PowerShell Script Generator": "powershell_generator",
        "🐧 Bash / Terminal Automation": "bash_generator",
        "🐞 Senior Code Architect & Debugger": "code_debugger",
        "🔍 Regular Expression Specialist": "regex_builder",
        "📝 Executive Summarizer & Meeting Notes": "summarizer",
    }

    selected_tool_type = tool_type_map[tool_choice]

    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        st.markdown("#### Input Prompt / Code / Task")
        
        # Presets
        presets = {
            "powershell_generator": [
                "Clean temporary files from %TEMP% and Windows\\Temp with admin check",
                "Find the top 15 largest files on drive C: sorted by size in GB",
                "Monitor CPU and RAM usage of all Chrome and Node processes",
                "Check which process is listening on port 3000 and terminate it",
            ],
            "bash_generator": [
                "Batch rename all .jpeg files in folder to .jpg with timestamp",
                "Sync local directory to remote server via rsync with progress",
                "Find and delete all empty directories recursively",
                "Check disk usage and alert if root partition exceeds 85%",
            ],
            "code_debugger": [
                "IndexError: list index out of range in Python loop iterating over dynamic array",
                "Fix unhandled promise rejection in async Node.js fetch call with timeout",
            ],
            "regex_builder": [
                "Validate RFC-compliant Email address",
                "Extract all IPv4 addresses and port numbers from log file",
                "Match semantic version strings like 2.4.0-alpha.1",
            ],
            "summarizer": [
                "Paste meeting minutes or technical documentation here to extract key decisions and action items",
            ],
        }

        selected_preset = st.selectbox(
            "Load Preset Template:",
            ["Custom Input..."] + presets.get(selected_tool_type, []),
        )

        default_text = "" if selected_preset == "Custom Input..." else selected_preset
        tool_input = st.text_area(
            "Describe the task or paste code/logs:",
            value=default_text,
            height=200,
        )

        run_btn = st.button("🚀 Generate Solution", use_container_width=True, type="primary")

    with col_t2:
        st.markdown("#### Generated Output")
        output_placeholder = st.empty()

        if run_btn and tool_input.strip():
            with st.spinner("Generating solution via Gemini..."):
                result = gemini_client.run_quick_tool(
                    tool_type=selected_tool_type,
                    user_input=tool_input,
                    context="Windows 11 Workstation PC",
                )
                output_placeholder.markdown(result)
                
                # Option to send code to Code Studio
                if st.button("📥 Send to Code Studio", key="send_to_studio"):
                    st.session_state.sandbox_code = result
                    st.success("Sent to Code Studio! Switch to the 'Code Studio' tab to edit or run.")
        else:
            output_placeholder.info("Click 'Generate Solution' to produce output.")

# ----------------- TAB 3: KNOWLEDGE BASE -----------------
with tab_knowledge:
    st.markdown("### 📚 Grounded Knowledge Base")
    st.caption("Ingest web URLs, manual documents, and notes. The AI Copilot grounds its responses strictly using these sources.")

    col_k1, col_k2 = st.columns([1, 1])

    with col_k1:
        st.markdown("#### 🌐 Ingest Webpage URL")
        url_input = st.text_input("Enter Web URL (e.g. https://docs.python.org/3/)", placeholder="https://...")
        if st.button("📥 Scrape & Ingest URL", use_container_width=True):
            if url_input.strip():
                with st.spinner(f"Fetching {url_input}..."):
                    res = fetch_url_content(url_input)
                    if res["success"]:
                        doc_id = f"url-{int(time.time())}"
                        new_doc = {
                            "id": doc_id,
                            "title": res["title"],
                            "source": "url",
                            "sourceUrl": res["url"],
                            "fileType": "Web Article",
                            "content": res["content"],
                            "wordCount": res["wordCount"],
                            "createdAt": int(time.time() * 1000),
                            "tags": ["Web Ingested", "Grounding"],
                            "summary": res["content"][:200] + "...",
                        }
                        st.session_state.knowledge_docs.insert(0, new_doc)
                        st.success(f"Ingested '{res['title']}' ({res['wordCount']} words) successfully!")
                    else:
                        st.error(f"Failed to fetch: {res['error']}")
            else:
                st.warning("Please provide a valid URL.")

        st.markdown("---")

        st.markdown("#### ✍️ Add Manual Document")
        manual_title = st.text_input("Document Title")
        manual_tags = st.text_input("Tags (comma separated)", value="Manual, System")
        manual_content = st.text_area("Document Content (Markdown / Text)", height=150)
        if st.button("➕ Add to Knowledge Base", use_container_width=True):
            if manual_title.strip() and manual_content.strip():
                new_doc = {
                    "id": f"manual-{int(time.time())}",
                    "title": manual_title.strip(),
                    "source": "manual",
                    "fileType": "Manual Document",
                    "content": manual_content.strip(),
                    "wordCount": len(manual_content.split()),
                    "createdAt": int(time.time() * 1000),
                    "tags": [t.strip() for t in manual_tags.split(",") if t.strip()],
                    "summary": manual_content[:150] + "...",
                }
                st.session_state.knowledge_docs.insert(0, new_doc)
                st.success(f"Added '{manual_title}' to Knowledge Base!")
            else:
                st.warning("Title and Content are required.")

    with col_k2:
        st.markdown(f"#### 📖 Ingested Documents ({len(st.session_state.knowledge_docs)})")
        
        search_query = st.text_input("🔍 Search documents by title or tag", placeholder="Search...")
        filtered_docs = [
            d for d in st.session_state.knowledge_docs
            if not search_query or search_query.lower() in d["title"].lower() or any(search_query.lower() in t.lower() for t in d.get("tags", []))
        ]

        if not filtered_docs:
            st.info("No documents match your query.")
        
        for doc in filtered_docs:
            with st.expander(f"📄 {doc['title']} ({doc.get('wordCount', 0)} words)"):
                st.caption(f"**Source:** {doc.get('sourceUrl') or doc.get('source')} | **Type:** {doc.get('fileType', 'Text')}")
                if doc.get("tags"):
                    st.write(" ".join([f"`{t}`" for t in doc["tags"]]))
                st.markdown("---")
                st.markdown(doc["content"][:2000] + ("\n\n*(Truncated in preview)*" if len(doc["content"]) > 2000 else ""))
                
                if st.button("🗑️ Delete Document", key=f"del_doc_{doc['id']}"):
                    st.session_state.knowledge_docs = [d for d in st.session_state.knowledge_docs if d["id"] != doc["id"]]
                    st.rerun()

# ----------------- TAB 4: TASK MANAGER -----------------
with tab_tasks:
    st.markdown("### 📋 Workstation Task Manager & Reminders")
    st.caption("Organize PC maintenance, coding milestones, and daily tasks. Active tasks are automatically grounded into the AI Copilot!")

    # Summary Metrics
    total_t = len(st.session_state.tasks)
    completed_t = sum(1 for t in st.session_state.tasks if t.get("completed"))
    pending_t = total_t - completed_t
    high_prio_t = sum(1 for t in st.session_state.tasks if not t.get("completed") and t.get("priority") == "high")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Tasks", total_t)
    m2.metric("Pending", pending_t)
    m3.metric("Completed", completed_t)
    m4.metric("High Priority", high_prio_t)

    st.markdown("---")

    # Add Task Form
    with st.expander("➕ Add New Task", expanded=False):
        with st.form("new_task_form"):
            t_col1, t_col2 = st.columns([3, 1])
            with t_col1:
                task_title = st.text_input("Task Title", placeholder="e.g. Set up virtual environment and install packages")
                task_desc = st.text_area("Description (Optional)", placeholder="Details or terminal commands...")
            with t_col2:
                task_priority = st.selectbox("Priority", ["high", "medium", "low"], index=1)
                task_due = st.text_input("Due Date", value="Today")
            
            submitted = st.form_submit_button("Create Task", use_container_width=True)
            if submitted and task_title.strip():
                next_id = max([t.get("numericId", 0) for t in st.session_state.tasks] or [0]) + 1
                new_t = {
                    "id": f"task-{int(time.time())}",
                    "numericId": next_id,
                    "title": task_title.strip(),
                    "description": task_desc.strip(),
                    "completed": False,
                    "priority": task_priority,
                    "dueDate": task_due.strip(),
                    "createdAt": int(time.time() * 1000),
                }
                st.session_state.tasks.insert(0, new_t)
                st.success(f"Task #{next_id} created!")
                st.rerun()

    # Filter Tasks
    filter_choice = st.radio("Show:", ["All Tasks", "Pending Only", "Completed Only"], horizontal=True)
    
    tasks_to_show = st.session_state.tasks
    if filter_choice == "Pending Only":
        tasks_to_show = [t for t in tasks_to_show if not t["completed"]]
    elif filter_choice == "Completed Only":
        tasks_to_show = [t for t in tasks_to_show if t["completed"]]

    # Task List
    for t in tasks_to_show:
        col_chk, col_info, col_del = st.columns([1, 10, 1])
        with col_chk:
            chk = st.checkbox("Done", value=t["completed"], key=f"chk_{t['id']}", label_visibility="collapsed")
            if chk != t["completed"]:
                t["completed"] = chk
                st.rerun()
        
        with col_info:
            prio_badge = "🔴 High" if t["priority"] == "high" else ("🟡 Med" if t["priority"] == "medium" else "🟢 Low")
            title_styled = f"~~{t['title']}~~" if t["completed"] else f"**{t['title']}**"
            st.markdown(f"#{t.get('numericId', 0)} {title_styled} &nbsp; `{prio_badge}` &nbsp; <span style='color:#94a3b8; font-size:0.8rem;'>📅 {t.get('dueDate', 'N/A')}</span>", unsafe_allow_html=True)
            if t.get("description"):
                st.caption(t["description"])
        
        with col_del:
            if st.button("🗑️", key=f"del_task_{t['id']}"):
                st.session_state.tasks = [item for item in st.session_state.tasks if item["id"] != t["id"]]
                st.rerun()

# ----------------- TAB 5: CODE STUDIO SANDBOX -----------------
with tab_code:
    st.markdown("### 💻 PC Code Studio Sandbox")
    st.caption("Interactive code editor and live Python sandbox. Test scripts, run algorithms, or ask AI to optimize.")

    code_input = st.text_area(
        "Python Code Editor:",
        value=st.session_state.sandbox_code,
        height=320,
    )
    st.session_state.sandbox_code = code_input

    col_c1, col_c2, col_c3 = st.columns([1, 1, 2])
    with col_c1:
        run_code_btn = st.button("▶️ Run Python Script", use_container_width=True, type="primary")
    with col_c2:
        ask_ai_btn = st.button("✨ Ask AI to Optimize / Fix", use_container_width=True)

    if run_code_btn:
        st.markdown("#### Execution Output")
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        start_time = time.time()
        try:
            exec(code_input, {"__builtins__": __builtins__})
            execution_time = time.time() - start_time
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            out_text = stdout_capture.getvalue()
            err_text = stderr_capture.getvalue()

            if out_text:
                st.success(f"Executed in {execution_time:.3f}s")
                st.code(out_text, language="text")
            if err_text:
                st.error("Standard Error:")
                st.code(err_text, language="text")
            if not out_text and not err_text:
                st.info("Script executed successfully with no output.")
        except Exception as e:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            st.error(f"Execution Error: {type(e).__name__}: {str(e)}")

    if ask_ai_btn:
        with st.spinner("Analyzing code with Nexus Architect..."):
            debug_prompt = f"Analyze this Python snippet. Explain its logic, point out bugs or performance issues, and provide an optimized version:\n\n```python\n{code_input}\n```"
            res = gemini_client.run_quick_tool("code_debugger", debug_prompt)
            st.markdown("#### 💡 AI Recommendations")
            st.markdown(res)

# ----------------- TAB 6: PROFILE & SYSTEM -----------------
with tab_profile:
    st.markdown("### ⚙️ Workstation Settings & Hardware Profile")
    st.caption("Configured for Daksh Intelligence PC Copilot.")

    p_col1, p_col2 = st.columns(2)
    with p_col1:
        st.markdown("#### Detected System Information")
        st.json({
            "OS Platform": platform.system(),
            "OS Release": platform.release(),
            "Architecture": platform.machine(),
            "Processor": platform.processor() or "Multi-core PC CPU",
            "Python Version": platform.python_version(),
            "Python Executable": sys.executable,
        })

    with p_col2:
        st.markdown("#### Workspace Data Management")
        st.write("Export your active conversations, tasks, and ingested knowledge documents to a JSON backup:")
        
        backup_data = {
            "conversations": st.session_state.messages,
            "tasks": st.session_state.tasks,
            "knowledge_docs": st.session_state.knowledge_docs,
            "exportedAt": datetime.now(timezone.utc).isoformat(),
        }
        json_str = json.dumps(backup_data, indent=2)

        st.download_button(
            label="💾 Download Backup (JSON)",
            data=json_str,
            file_name=f"daksh_intelligence_backup_{int(time.time())}.json",
            mime="application/json",
            use_container_width=True,
        )

        st.markdown("---")
        st.write("Reset all data to defaults:")
        if st.button("⚠️ Factory Reset Workspace", use_container_width=True):
            st.session_state.messages = []
            st.session_state.tasks = list(DEFAULT_TASKS)
            st.session_state.knowledge_docs = list(DEFAULT_KNOWLEDGE_DOCUMENTS)
            st.rerun()

