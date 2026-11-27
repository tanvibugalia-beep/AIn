const state = {
  classId: localStorage.getItem("eduprep_class") || "class_10",
  view: "home",
  historyStack: [],
  classes: [],
  subjects: [],
  progress: { bookmarks: [], quiz_attempts: [], paper_attempts: [], chapter_progress: [], user_notes: [] },
  chatHistory: [],
  tutorMode: "general",
  isAdmin: false,
  adminEmail: null,
};

const $ = (id) => document.getElementById(id);

function showToast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 2800);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function api(url, options = {}) {
  const headers = options.body instanceof FormData ? { ...(options.headers || {}) } : { "Content-Type": "application/json", ...(options.headers || {}) };
  const res = await fetch(url, { headers, ...options });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const err = await res.json();
      if (err.detail) msg = err.detail;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("eduprep_theme", theme);
  const isDark = theme === "dark";
  $("themeIcon").textContent = isDark ? "☀️" : "🌙";
  $("themeLabel").textContent = isDark ? "Light Mode" : "Dark Mode";
  $("mobileThemeBtn").textContent = isDark ? "☀️" : "🌙";
}

function syncAdminUI() {
  $("adminNavBtn").classList.toggle("hidden", !state.isAdmin);
  $("mobileAdminBtn").classList.toggle("hidden", !state.isAdmin);
  $("adminBadgeTop").classList.toggle("hidden", !state.isAdmin);
  if ($("sidebarAdminLogoutBtn")) $("sidebarAdminLogoutBtn").classList.toggle("hidden", !state.isAdmin);
  if ($("topAdminLogoutBtn")) $("topAdminLogoutBtn").classList.toggle("hidden", !state.isAdmin);
  $("adminTriggerLabel").textContent = state.isAdmin ? `Admin (${state.adminEmail})` : "Admin Access";
}

async function logoutAdmin() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (e) {}
  state.isAdmin = false;
  state.adminEmail = null;
  syncAdminUI();
  showToast("Signed out of Admin Studio");
  if (state.view === "admin") navigate("home", {}, false);
}

async function handleDakshSSOIfPresent() {
  const hash = window.location.hash || "";
  const search = window.location.search || "";
  let ssoToken = null;

  if (hash.includes("sso_token=")) {
    const params = new URLSearchParams(hash.slice(1));
    ssoToken = params.get("sso_token");
  } else if (search.includes("sso_token=")) {
    const params = new URLSearchParams(search);
    ssoToken = params.get("sso_token");
  }

  if (ssoToken) {
    try {
      const res = await api("/api/auth/sso", {
        method: "POST",
        body: JSON.stringify({ id_token: ssoToken }),
      });
      if (res.is_admin) {
        state.isAdmin = true;
        state.adminEmail = res.email;
        showToast("Admin Studio unlocked via Daksh Intelligence!");
      }
    } catch (e) {
      console.warn("SSO check failed:", e.message);
    }
    history.replaceState(null, "", window.location.pathname);
  } else {
    const me = await api("/api/auth/me");
    state.isAdmin = Boolean(me.is_admin);
    state.adminEmail = me.email || null;
  }
  syncAdminUI();
}

function updateNavActive(view) {
  document.querySelectorAll("[data-view]").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === view);
  });
}

function navigate(view, params = {}, pushHistory = true) {
  if (view === "admin" && !state.isAdmin) {
    $("adminModal").classList.remove("hidden");
    return;
  }
  if (pushHistory && state.view) {
    state.historyStack.push({ view: state.view, params: state.params || {} });
  }
  state.view = view;
  state.params = params;
  $("backBtn").classList.toggle("hidden", state.historyStack.length === 0);
  updateNavActive(view);
  renderCurrentView();
}

function goBack() {
  const prev = state.historyStack.pop();
  if (!prev) return;
  state.view = prev.view;
  state.params = prev.params;
  $("backBtn").classList.toggle("hidden", state.historyStack.length === 0);
  updateNavActive(prev.view);
  renderCurrentView();
}

async function refreshProgress() {
  state.progress = await api("/api/progress");
}

function isBookmarked(itemId) {
  return state.progress.bookmarks.some((b) => b.item_id === itemId);
}

async function toggleBookmark(item) {
  if (isBookmarked(item.item_id)) {
    await api(`/api/bookmarks/${encodeURIComponent(item.item_id)}`, { method: "DELETE" });
    showToast("Removed bookmark");
  } else {
    await api("/api/bookmarks", { method: "POST", body: JSON.stringify(item) });
    showToast("Saved to bookmarks");
  }
  await refreshProgress();
  renderCurrentView();
}

function isChapterRead(chapterId) {
  const row = state.progress.chapter_progress.find((p) => p.chapter_id === chapterId);
  return Boolean(row && row.is_read);
}

async function renderCurrentView() {
  const main = $("mainContent");
  try {
    if (state.view === "home") await renderHome(main);
    else if (state.view === "subject") await renderSubject(main, state.params.subjectId);
    else if (state.view === "chapter") await renderChapter(main, state.params.chapterId);
    else if (state.view === "quiz") await renderQuiz(main, state.params.chapterId);
    else if (state.view === "formulas") await renderFormulas(main);
    else if (state.view === "files") await renderFiles(main);
    else if (state.view === "papers") await renderPapers(main);
    else if (state.view === "paper_detail") await renderPaperDetail(main, state.params.paperId);
    else if (state.view === "search") await renderSearch(main);
    else if (state.view === "progress") await renderProgress(main);
    else if (state.view === "tutor") await renderTutor(main);
    else if (state.view === "admin") await renderAdmin(main);
  } catch (err) {
    main.innerHTML = `<div class="card"><h3>Error</h3><p class="muted">${escapeHtml(err.message)}</p></div>`;
  }
}

async function renderHome(main) {
  const cls = state.classes.find((c) => c.id === state.classId) || { displayName: "Class 10", description: "" };
  $("pageTitle").textContent = `EduPrep With Daksh • ${cls.displayName}`;
  const data = await api(`/api/subjects?class_id=${encodeURIComponent(state.classId)}`);
  state.subjects = data.subjects;

  const readCount = state.progress.chapter_progress.filter((p) => p.is_read).length;
  const quizCount = state.progress.quiz_attempts.length;
  const bmCount = state.progress.bookmarks.length;

  main.innerHTML = `
    <div class="hero-banner">
      <h2>${escapeHtml(cls.displayName)} Board & Exam Prep</h2>
      <p>${escapeHtml(cls.description)}</p>
      <div class="hero-actions">
        <button class="btn btn-light" onclick="navigate('papers')">📝 Practice Papers</button>
        <button class="btn btn-light" onclick="navigate('formulas')">📐 Formula Deck</button>
        <button class="btn btn-light" onclick="navigate('files')">📁 Study Files</button>
        <button class="btn btn-light" onclick="navigate('tutor')">🤖 Ask Daksh AI</button>
        <button class="btn btn-light" onclick="navigate('search')">🔍 Search Syllabus</button>
        ${state.isAdmin ? `<button class="btn btn-amber" onclick="navigate('admin')">🛡️ Open Admin Studio</button>` : ""}
      </div>
    </div>

    <div class="grid-3" style="margin-bottom:20px;">
      <div class="card"><div class="muted">Chapters Read</div><div style="font-size:26px;font-weight:800;margin-top:4px;">${readCount}</div></div>
      <div class="card"><div class="muted">Quizzes Taken</div><div style="font-size:26px;font-weight:800;margin-top:4px;">${quizCount}</div></div>
      <div class="card"><div class="muted">Saved Bookmarks</div><div style="font-size:26px;font-weight:800;margin-top:4px;">${bmCount}</div></div>
    </div>

    <div class="section-header"><h3>Subjects (${state.subjects.length})</h3></div>
    <div class="grid-2">
      ${state.subjects
        .map(
          (s) => `
        <div class="card card-clickable" onclick="navigate('subject', { subjectId: '${escapeHtml(s.id)}' })">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span class="badge">${escapeHtml(s.code)}</span>
            <span class="muted">${s.chapterCount} Chapters</span>
          </div>
          <h3 style="margin:0 0 6px;">${escapeHtml(s.name)}</h3>
          <p class="muted" style="margin:0;">${escapeHtml(s.description)}</p>
        </div>`
        )
        .join("")}
    </div>
  `;
}

async function renderSubject(main, subjectId) {
  const data = await api(`/api/subjects/${encodeURIComponent(subjectId)}/chapters`);
  const { subject, chapters } = data;
  $("pageTitle").textContent = subject.name;

  main.innerHTML = `
    <div class="card" style="margin-bottom:18px;">
      <span class="badge">${escapeHtml(subject.code)}</span>
      <h2 style="margin:8px 0 4px;">${escapeHtml(subject.name)}</h2>
      <p class="muted" style="margin:0;">${escapeHtml(subject.description)}</p>
    </div>

    <div class="section-header"><h3>Chapters (${chapters.length})</h3></div>
    <div style="display:flex;flex-direction:column;gap:12px;">
      ${chapters
        .map((ch) => {
          const read = isChapterRead(ch.id);
          return `
          <div class="card card-clickable" onclick="navigate('chapter', { chapterId: '${escapeHtml(ch.id)}' })">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
              <div>
                <span class="badge">Ch ${ch.chapterNumber}</span>
                ${read ? '<span class="badge badge-emerald">✓ Read</span>' : ""}
                <span class="badge badge-amber">★ ${ch.highYieldRating}/5 Yield</span>
              </div>
              <span class="muted">${ch.estimatedReadMinutes} min read • ${ch.totalQuestions} Qs</span>
            </div>
            <h3 style="margin:10px 0 4px;">${escapeHtml(ch.title)}</h3>
            <div class="muted" style="font-weight:600;margin-bottom:4px;">${escapeHtml(ch.subtitle)}</div>
            <p class="muted" style="margin:0;">${escapeHtml(ch.summary)}</p>
          </div>`;
        })
        .join("")}
    </div>
  `;
}

async function renderChapter(main, chapterId) {
  const data = await api(`/api/chapters/${encodeURIComponent(chapterId)}`);
  const { chapter, subject, notes } = data;
  const userNotesData = await api(`/api/notes?chapter_id=${encodeURIComponent(chapterId)}`);
  const userNotes = userNotesData.notes || [];
  const read = isChapterRead(chapterId);
  const bm = isBookmarked(chapterId);

  $("pageTitle").textContent = chapter.title;

  main.innerHTML = `
    <div class="card" style="margin-bottom:16px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;">
        <div>
          <span class="badge">${escapeHtml(subject?.name || "")} • Ch ${chapter.chapterNumber}</span>
          <h2 style="margin:8px 0 4px;">${escapeHtml(chapter.title)}</h2>
          <p class="muted" style="margin:0;">${escapeHtml(chapter.subtitle)}</p>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-sm ${read ? "btn-emerald" : "btn-outline"}" id="markReadBtn">
            ${read ? "✓ Completed" : "Mark as Read"}
          </button>
          <button class="btn btn-sm btn-outline" id="bmChapterBtn">
            ${bm ? "★ Bookmarked" : "☆ Bookmark"}
          </button>
          <button class="btn btn-sm btn-primary" onclick="navigate('quiz', { chapterId: '${escapeHtml(chapterId)}' })">
            Take Quiz →
          </button>
        </div>
      </div>
      <p style="margin:14px 0 0;">${escapeHtml(notes.overview || chapter.summary)}</p>
    </div>

    <div class="section-header"><h3>Key Concepts (${(notes.keyConcepts || []).length})</h3></div>
    <div style="display:flex;flex-direction:column;gap:12px;">
      ${(notes.keyConcepts || [])
        .map(
          (c) => `
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
            <h4 style="margin:0;">${escapeHtml(c.title)}</h4>
            <span class="badge badge-amber">${escapeHtml(c.examImportance || "High")}</span>
          </div>
          <p style="margin:8px 0;">${escapeHtml(c.explanation)}</p>
          ${c.keyFormula ? `<div class="formula-box">${escapeHtml(c.keyFormula)}</div>` : ""}
          ${
            c.keyPoints && c.keyPoints.length
              ? `<ul style="margin:8px 0 0;padding-left:18px;">${c.keyPoints.map((kp) => `<li>${escapeHtml(kp)}</li>`).join("")}</ul>`
              : ""
          }
        </div>`
        )
        .join("")}
    </div>

    ${
      notes.mindMapSummary && notes.mindMapSummary.length
        ? `<div class="section-header"><h3>Quick Revision Mind Map</h3></div>
           <div class="card"><ul style="margin:0;padding-left:18px;">${notes.mindMapSummary
             .map((m) => `<li style="margin-bottom:6px;">${escapeHtml(m)}</li>`)
             .join("")}</ul></div>`
        : ""
    }

    ${
      notes.formulas && notes.formulas.length
        ? `<div class="section-header"><h3>Chapter Formulas</h3></div>
           <div class="grid-2">${notes.formulas
             .map(
               (f) => `
             <div class="card">
               <h4 style="margin:0 0 6px;">${escapeHtml(f.name)}</h4>
               <div class="formula-box">${escapeHtml(f.formulaText)}</div>
               <div class="muted"><strong>Terms:</strong> ${escapeHtml(f.whereTerms)}</div>
               <div class="muted" style="margin-top:4px;"><strong>Use:</strong> ${escapeHtml(f.applicationNote)}</div>
             </div>`
             )
             .join("")}</div>`
        : ""
    }

    ${
      notes.derivationsAndDiagrams && notes.derivationsAndDiagrams.length
        ? `<div class="section-header"><h3>Derivations & Diagrams</h3></div>
           <div style="display:flex;flex-direction:column;gap:12px;">${notes.derivationsAndDiagrams
             .map(
               (d) => `
             <div class="card">
               <h4 style="margin:0 0 8px;">${escapeHtml(d.title)}</h4>
               <ol style="margin:0;padding-left:20px;">${(d.steps || [])
                 .map((st) => `<li style="margin-bottom:4px;">${escapeHtml(st)}</li>`)
                 .join("")}</ol>
               <div class="formula-box" style="margin-top:10px;"><strong>Takeaway:</strong> ${escapeHtml(d.keyTakeaway)}</div>
             </div>`
             )
             .join("")}</div>`
        : ""
    }

    ${
      notes.examTips && notes.examTips.length
        ? `<div class="section-header"><h3>Board Exam Tips & Pitfalls</h3></div>
           <div class="grid-2">${notes.examTips
             .map(
               (tip) => `
             <div class="card">
               <span class="badge ${tip.isCommonPitfall ? "badge-rose" : "badge-emerald"}">
                 ${tip.isCommonPitfall ? "⚠ Common Pitfall" : "💡 Exam Tip"}
               </span>
               <h4 style="margin:8px 0 4px;">${escapeHtml(tip.title)}</h4>
               <p class="muted" style="margin:0;">${escapeHtml(tip.description)}</p>
             </div>`
             )
             .join("")}</div>`
        : ""
    }

    <div class="section-header"><h3>My Personal Study Notes</h3></div>
    <div class="card">
      <textarea id="personalNoteInput" class="textarea" placeholder="Write your own revision summary, mnemonics, or doubts for this chapter..."></textarea>
      <div style="margin-top:10px;display:flex;justify-content:flex-end;">
        <button class="btn btn-primary btn-sm" id="saveNoteBtn">Save Note</button>
      </div>
      <div id="userNotesList" style="margin-top:14px;display:flex;flex-direction:column;gap:8px;">
        ${
          userNotes.length
            ? userNotes
                .map(
                  (n) => `
            <div style="padding:10px 12px;border-radius:10px;background:var(--surface-variant);display:flex;justify-content:space-between;gap:10px;align-items:flex-start;">
              <div style="white-space:pre-wrap;font-size:13px;">${escapeHtml(n.note_text)}</div>
              <button class="btn btn-sm btn-outline" onclick="deleteUserNote(${n.id}, '${escapeHtml(chapterId)}')">Delete</button>
            </div>`
                )
                .join("")
            : '<div class="muted">No personal notes yet for this chapter.</div>'
        }
      </div>
    </div>
  `;

  $("markReadBtn").onclick = async () => {
    await api(`/api/chapters/${encodeURIComponent(chapterId)}/read`, {
      method: "POST",
      body: JSON.stringify({ is_read: !read }),
    });
    await refreshProgress();
    showToast(!read ? "Marked chapter as completed!" : "Marked as unread");
    renderChapter(main, chapterId);
  };

  $("bmChapterBtn").onclick = () =>
    toggleBookmark({
      item_id: chapter.id,
      class_level: chapter.classLevel,
      subject_id: chapter.subjectId,
      item_type: "CHAPTER",
      title: chapter.title,
      snippet: chapter.subtitle,
    });

  $("saveNoteBtn").onclick = async () => {
    const text = $("personalNoteInput").value.trim();
    if (!text) return;
    await api("/api/notes", {
      method: "POST",
      body: JSON.stringify({ chapter_id: chapter.id, chapter_title: chapter.title, note_text: text }),
    });
    await refreshProgress();
    showToast("Personal note saved");
    renderChapter(main, chapterId);
  };
}

window.deleteUserNote = async (noteId) => {
  await api(`/api/notes/${noteId}`, { method: "DELETE" });
  await refreshProgress();
  showToast("Note deleted");
  renderCurrentView();
};

async function renderQuiz(main, chapterId) {
  const data = await api(`/api/chapters/${encodeURIComponent(chapterId)}/quiz`);
  const { chapter, questions } = data;
  $("pageTitle").textContent = `Quiz • ${chapter.title}`;

  let idx = 0;
  let score = 0;
  let answered = false;
  let showHint = false;
  const startTime = Date.now();

  function draw() {
    if (idx >= questions.length) {
      const elapsed = Math.max(1, Math.round((Date.now() - startTime) / 1000));
      const pct = Math.round((score / questions.length) * 100);
      main.innerHTML = `
        <div class="card" style="text-align:center;padding:32px 20px;">
          <span class="badge ${pct >= 70 ? "badge-emerald" : "badge-amber"}">Quiz Complete</span>
          <h2 style="margin:12px 0 6px;">Score: ${score} / ${questions.length} (${pct}%)</h2>
          <p class="muted">Time taken: ${elapsed}s • ${escapeHtml(chapter.title)}</p>
          <div style="display:flex;justify-content:center;gap:10px;margin-top:20px;flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="navigate('quiz', { chapterId: '${escapeHtml(chapterId)}' }, false)">Retry Quiz</button>
            <button class="btn btn-outline" onclick="goBack()">Back to Chapter</button>
          </div>
        </div>
      `;
      return;
    }

    const q = questions[idx];
    main.innerHTML = `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px;">
          <span class="badge">Question ${idx + 1} of ${questions.length}</span>
          <div>
            <span class="badge badge-amber">${escapeHtml(q.difficulty || "medium").toUpperCase()}</span>
            <span class="badge">${escapeHtml(q.questionType || "conceptual").toUpperCase()}</span>
          </div>
        </div>

        <h3 style="margin:0 0 14px;white-space:pre-wrap;">${escapeHtml(q.questionText)}</h3>

        <div id="optionsWrap">
          ${q.options
            .map(
              (opt, i) => `
            <button class="quiz-option" data-opt="${i}">${String.fromCharCode(65 + i)}. ${escapeHtml(opt)}</button>
          `
            )
            .join("")}
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;flex-wrap:wrap;gap:8px;">
          <button class="btn btn-sm btn-outline" id="hintBtn">${showHint ? "Hide Hint" : "💡 Show Hint"}</button>
          <span class="muted">Score: ${score}</span>
        </div>

        ${showHint ? `<div class="formula-box" style="margin-top:10px;"><strong>Hint:</strong> ${escapeHtml(q.hint)}</div>` : ""}
        <div id="feedbackBox" class="hidden" style="margin-top:14px;"></div>
      </div>
    `;

    $("hintBtn").onclick = () => {
      showHint = !showHint;
      draw();
    };

    document.querySelectorAll(".quiz-option").forEach((btn) => {
      btn.onclick = async () => {
        if (answered) return;
        answered = true;
        const chosen = Number(btn.dataset.opt);
        const correct = q.correctOptionIndex;
        if (chosen === correct) score++;

        document.querySelectorAll(".quiz-option").forEach((b) => {
          b.disabled = true;
          const o = Number(b.dataset.opt);
          if (o === correct) b.classList.add("correct");
          else if (o === chosen) b.classList.add("wrong");
        });

        const fb = $("feedbackBox");
        fb.classList.remove("hidden");
        fb.innerHTML = `
          <div class="formula-box">
            <strong>${chosen === correct ? "✅ Correct!" : "❌ Incorrect"}</strong><br/>
            ${escapeHtml(q.explanation)}
          </div>
          <div style="margin-top:12px;display:flex;justify-content:flex-end;">
            <button class="btn btn-primary" id="nextQBtn">${idx + 1 === questions.length ? "Finish Quiz" : "Next Question →"}</button>
          </div>
        `;

        if (idx + 1 === questions.length) {
          const elapsed = Math.max(1, Math.round((Date.now() - startTime) / 1000));
          await api("/api/quiz-attempts", {
            method: "POST",
            body: JSON.stringify({
              chapter_id: chapter.id,
              chapter_title: chapter.title,
              subject_name: chapter.subjectId,
              class_level: chapter.classLevel,
              score,
              total_questions: questions.length,
              time_taken_seconds: elapsed,
            }),
          });
          await refreshProgress();
        }

        $("nextQBtn").onclick = () => {
          idx++;
          answered = false;
          showHint = false;
          draw();
        };
      };
    });
  }

  draw();
}

async function renderFormulas(main) {
  $("pageTitle").textContent = "Formula Deck";
  const data = await api(`/api/formulas?class_id=${encodeURIComponent(state.classId)}`);
  const formulas = data.formulas || [];

  main.innerHTML = `
    <div class="card" style="margin-bottom:16px;">
      <input id="formulaFilter" class="input" placeholder="Filter formulas by name, symbol, or topic..." />
    </div>
    <div id="formulaGrid" class="grid-2"></div>
  `;

  function drawList(filter = "") {
    const q = filter.trim().toLowerCase();
    const list = formulas.filter(
      (f) => !q || f.name.toLowerCase().includes(q) || f.formulaText.toLowerCase().includes(q) || f.chapterTitle.toLowerCase().includes(q)
    );
    $("formulaGrid").innerHTML = list.length
      ? list
          .map((f) => {
            const bm = isBookmarked(f.id);
            return `
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                <span class="badge">${escapeHtml(f.chapterTitle)}</span>
                <button class="btn btn-sm btn-outline" onclick='toggleFormulaBm(${JSON.stringify(f).replace(/'/g, "&apos;")})'>
                  ${bm ? "★" : "☆"}
                </button>
              </div>
              <h4 style="margin:10px 0 4px;">${escapeHtml(f.name)}</h4>
              <div class="formula-box">${escapeHtml(f.formulaText)}</div>
              <div class="muted"><strong>Where:</strong> ${escapeHtml(f.whereTerms)}</div>
              <div class="muted" style="margin-top:4px;"><strong>Tip:</strong> ${escapeHtml(f.applicationNote)}</div>
            </div>`;
          })
          .join("")
      : `<div class="card"><p class="muted">No formulas matched your filter.</p></div>`;
  }

  window.toggleFormulaBm = (f) =>
    toggleBookmark({
      item_id: f.id,
      class_level: state.classId,
      subject_id: f.subjectId,
      item_type: "FORMULA",
      title: f.name,
      snippet: f.formulaText,
    });

  $("formulaFilter").oninput = (e) => drawList(e.target.value);
  drawList();
}

async function renderFiles(main) {
  $("pageTitle").textContent = "Study Files & Formula Sheets";
  const data = await api(`/api/files?class_id=${encodeURIComponent(state.classId)}`);
  const files = data.files || [];

  main.innerHTML = files.length
    ? `<div class="grid-2">${files
        .map(
          (f) => `
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="badge badge-amber">${escapeHtml(f.category)}</span>
            <span class="muted">${(f.file_size / 1024).toFixed(1)} KB</span>
          </div>
          <h3 style="margin:10px 0 4px;">${escapeHtml(f.title)}</h3>
          <p class="muted" style="margin:0 0 12px;">${escapeHtml(f.description || f.filename)}</p>
          <a class="btn btn-primary btn-sm" href="/api/files/${f.id}/download" download="${escapeHtml(f.filename)}">⬇ Download File</a>
        </div>`
        )
        .join("")}</div>`
    : `<div class="card"><h3>No Study Files Uploaded Yet</h3><p class="muted">Formula sheets and PDFs uploaded by Daksh Admin for ${escapeHtml(state.classId.replace("_", " "))} will appear here.</p></div>`;
}

async function renderPapers(main) {
  $("pageTitle").textContent = "Practice Papers";
  const data = await api(`/api/papers?class_id=${encodeURIComponent(state.classId)}`);
  const papers = data.papers || [];

  main.innerHTML = papers.length
    ? `<div class="grid-2">${papers
        .map(
          (p) => `
        <div class="card card-clickable" onclick="navigate('paper_detail', { paperId: '${escapeHtml(p.id)}' })">
          <span class="badge badge-amber">${escapeHtml(p.yearOrPattern)}</span>
          <h3 style="margin:10px 0 6px;">${escapeHtml(p.title)}</h3>
          <div class="muted">${escapeHtml(p.subjectName)} • ${p.totalMarks} Marks • ${p.durationMinutes} Mins</div>
          <div class="muted" style="margin-top:6px;">${p.questions.length} Sample Questions with Marking Scheme</div>
        </div>`
        )
        .join("")}</div>`
    : `<div class="card"><h3>No Practice Papers Yet</h3><p class="muted">Switch to Class 10 or Class 12 to view available CBSE Model Papers.</p></div>`;
}

async function renderPaperDetail(main, paperId) {
  const data = await api(`/api/papers/${encodeURIComponent(paperId)}`);
  const paper = data.paper;
  $("pageTitle").textContent = paper.subjectName + " Model Paper";

  main.innerHTML = `
    <div class="card" style="margin-bottom:16px;">
      <span class="badge badge-amber">${escapeHtml(paper.yearOrPattern)}</span>
      <h2 style="margin:8px 0 4px;">${escapeHtml(paper.title)}</h2>
      <div class="muted">Max Marks: ${paper.totalMarks} • Duration: ${paper.durationMinutes} minutes</div>
      <ul style="margin:12px 0 0;padding-left:18px;font-size:13px;">
        ${paper.instructions.map((ins) => `<li>${escapeHtml(ins)}</li>`).join("")}
      </ul>
    </div>

    <div style="display:flex;flex-direction:column;gap:14px;">
      ${paper.questions
        .map(
          (q) => `
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span class="badge">Q${q.questionNumber} • ${escapeHtml(q.sectionType.replace(/_/g, " "))}</span>
            <span class="badge badge-emerald">${q.marks} Mark${q.marks > 1 ? "s" : ""}</span>
          </div>
          <p style="font-weight:600;white-space:pre-wrap;">${escapeHtml(q.questionText)}</p>
          ${
            q.mcqOptions
              ? `<div style="margin:10px 0;">${q.mcqOptions
                  .map(
                    (opt, idx) => `
                <button class="quiz-option" onclick="checkPaperMcq(this, ${idx}, ${q.correctMcqOptionIndex})">
                  ${String.fromCharCode(65 + idx)}. ${escapeHtml(opt)}
                </button>`
                  )
                  .join("")}</div>`
              : ""
          }
          <button class="btn btn-sm btn-outline" onclick="this.nextElementSibling.classList.toggle('hidden')">
            Show Model Answer & Marking Scheme
          </button>
          <div class="hidden" style="margin-top:12px;">
            <div class="formula-box" style="white-space:pre-wrap;">${escapeHtml(q.modelAnswer)}</div>
            <div class="muted"><strong>Marking Scheme:</strong></div>
            <ul style="margin:4px 0 0;padding-left:18px;font-size:13px;">
              ${q.markingScheme.map((m) => `<li>${escapeHtml(m)}</li>`).join("")}
            </ul>
          </div>
        </div>`
        )
        .join("")}
    </div>
  `;
}

window.checkPaperMcq = (btn, chosen, correct) => {
  const parent = btn.parentElement;
  parent.querySelectorAll(".quiz-option").forEach((b, idx) => {
    b.disabled = true;
    if (idx === correct) b.classList.add("correct");
    else if (idx === chosen) b.classList.add("wrong");
  });
};

async function renderSearch(main) {
  $("pageTitle").textContent = "Search Syllabus";
  main.innerHTML = `
    <div class="card" style="margin-bottom:16px;">
      <div style="display:flex;gap:10px;">
        <input id="searchInput" class="input" placeholder="Search chapters, concepts, or formulas (e.g. Ohm, quadratic, lens)..." />
        <button id="searchBtn" class="btn btn-primary">Search</button>
      </div>
    </div>
    <div id="searchResults"></div>
  `;

  async function runSearch() {
    const q = $("searchInput").value.trim();
    if (!q) {
      $("searchResults").innerHTML = `<div class="card"><p class="muted">Type a keyword to search across ${escapeHtml(state.classId.replace("_", " "))}.</p></div>`;
      return;
    }
    const data = await api(`/api/search?q=${encodeURIComponent(q)}&class_id=${encodeURIComponent(state.classId)}`);
    const results = data.results || [];
    $("searchResults").innerHTML = results.length
      ? `<div style="display:flex;flex-direction:column;gap:10px;">${results
          .map(
            (r) => `
          <div class="card card-clickable" onclick="navigate('chapter', { chapterId: '${escapeHtml(r.chapterId)}' })">
            <span class="badge">${escapeHtml(r.type)}</span>
            <h4 style="margin:8px 0 4px;">${escapeHtml(r.title)}</h4>
            <div class="muted">${escapeHtml(r.subtitle)}</div>
            ${r.extraInfo ? `<div class="muted" style="margin-top:4px;font-size:12px;">${escapeHtml(r.extraInfo)}</div>` : ""}
          </div>`
          )
          .join("")}</div>`
      : `<div class="card"><p class="muted">No results found for "${escapeHtml(q)}".</p></div>`;
  }

  $("searchBtn").onclick = runSearch;
  $("searchInput").onkeydown = (e) => {
    if (e.key === "Enter") runSearch();
  };
}

async function renderProgress(main) {
  $("pageTitle").textContent = "Progress & Bookmarks";
  await refreshProgress();
  const { bookmarks, quiz_attempts, chapter_progress, user_notes } = state.progress;
  const readCount = chapter_progress.filter((c) => c.is_read).length;

  main.innerHTML = `
    <div class="grid-3" style="margin-bottom:20px;">
      <div class="card"><div class="muted">Chapters Read</div><div style="font-size:26px;font-weight:800;">${readCount}</div></div>
      <div class="card"><div class="muted">Quizzes Completed</div><div style="font-size:26px;font-weight:800;">${quiz_attempts.length}</div></div>
      <div class="card"><div class="muted">Personal Notes</div><div style="font-size:26px;font-weight:800;">${user_notes.length}</div></div>
    </div>

    <div class="section-header"><h3>Bookmarks (${bookmarks.length})</h3></div>
    <div class="grid-2" style="margin-bottom:20px;">
      ${
        bookmarks.length
          ? bookmarks
              .map(
                (b) => `
          <div class="card">
            <span class="badge">${escapeHtml(b.item_type)}</span>
            <h4 style="margin:8px 0 4px;">${escapeHtml(b.title)}</h4>
            <p class="muted" style="margin:0 0 10px;">${escapeHtml(b.snippet)}</p>
            <button class="btn btn-sm btn-outline" onclick="removeBm('${escapeHtml(b.item_id)}')">Remove</button>
          </div>`
              )
              .join("")
          : `<div class="card"><p class="muted">No bookmarks saved yet.</p></div>`
      }
    </div>

    <div class="section-header"><h3>Recent Quiz Attempts</h3></div>
    <div style="display:flex;flex-direction:column;gap:10px;">
      ${
        quiz_attempts.length
          ? quiz_attempts
              .map(
                (q) => `
          <div class="card" style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <strong>${escapeHtml(q.chapter_title)}</strong>
              <div class="muted">${q.time_taken_seconds}s</div>
            </div>
            <span class="badge badge-emerald">${q.score} / ${q.total_questions}</span>
          </div>`
              )
              .join("")
          : `<div class="card"><p class="muted">Take a chapter quiz to track your scores here.</p></div>`
      }
    </div>
  `;
}

window.removeBm = async (itemId) => {
  await api(`/api/bookmarks/${encodeURIComponent(itemId)}`, { method: "DELETE" });
  await refreshProgress();
  renderCurrentView();
};

async function renderTutor(main) {
  $("pageTitle").textContent = "Daksh AI Tutor";
  main.innerHTML = `
    <div class="chat-box">
      <div class="chat-header">
        <div>
          <strong>Daksh AI Mentor</strong>
          <span class="muted" style="margin-left:8px;">Syllabus-aligned doubt solver</span>
        </div>
        <select id="tutorModeSelect" class="class-select" style="width:auto;">
          <option value="general" ${state.tutorMode === "general" ? "selected" : ""}>Daksh AI Mentor (Balanced)</option>
          <option value="fast" ${state.tutorMode === "fast" ? "selected" : ""}>Quick Doubts (Fast)</option>
          <option value="complex" ${state.tutorMode === "complex" ? "selected" : ""}>Deep Analysis (Reasoning)</option>
        </select>
      </div>
      <div id="chatMessages" class="chat-messages">
        ${
          state.chatHistory.length === 0
            ? `<div class="msg msg-ai">Hi! I'm Daksh, your AI exam mentor. Ask me any doubt from Class 10, 11, or 12 — derivations, numericals, formulas, or board exam tips!</div>`
            : state.chatHistory
                .map((m) => `<div class="msg ${m.sender === "user" ? "msg-user" : "msg-ai"}">${escapeHtml(m.text)}</div>`)
                .join("")
        }
      </div>
      <div class="chat-input-row">
        <input id="chatInput" class="input" placeholder="Ask a question (e.g. Derive mirror formula or explain Ohm's law)..." />
        <button id="sendChatBtn" class="btn btn-primary">Send</button>
      </div>
    </div>
  `;

  $("tutorModeSelect").onchange = (e) => {
    state.tutorMode = e.target.value;
  };

  async function sendMsg() {
    const input = $("chatInput");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";

    const historySnapshot = [...state.chatHistory];
    state.chatHistory.push({ sender: "user", text });
    const msgBox = $("chatMessages");
    msgBox.innerHTML += `<div class="msg msg-user">${escapeHtml(text)}</div>`;
    const loadingEl = document.createElement("div");
    loadingEl.className = "msg msg-ai";
    loadingEl.textContent = "Daksh is thinking...";
    msgBox.appendChild(loadingEl);
    msgBox.scrollTop = msgBox.scrollHeight;

    try {
      const res = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          class_id: state.classId,
          tutor_mode: state.tutorMode,
          history: historySnapshot,
        }),
      });
      loadingEl.textContent = res.reply;
      state.chatHistory.push({ sender: "ai", text: res.reply });
    } catch (err) {
      loadingEl.textContent = `Error: ${err.message}`;
    }
    msgBox.scrollTop = msgBox.scrollHeight;
  }

  $("sendChatBtn").onclick = sendMsg;
  $("chatInput").onkeydown = (e) => {
    if (e.key === "Enter") sendMsg();
  };
}

// --- ADMIN STUDIO (Visible ONLY to dakshbugalia1@gmail.com) ---
async function renderAdmin(main) {
  if (!state.isAdmin) {
    navigate("home", {}, false);
    return;
  }
  $("pageTitle").textContent = "🛡️ Admin Studio (Daksh Owner)";

  let subData, filesData, formulasData, quizzesData, studentsData;
  try {
    [subData, filesData, formulasData, quizzesData, studentsData] = await Promise.all([
      api(`/api/subjects?class_id=${encodeURIComponent(state.classId)}`),
      api("/api/files"),
      api(`/api/formulas?class_id=${encodeURIComponent(state.classId)}`),
      api("/api/admin/quizzes"),
      api("/api/admin/students").catch(() => ({ students: [], total_students: 0, total_quizzes: 0, total_papers: 0, total_notes: 0 })),
    ]);
  } catch (err) {
    if (String(err.message || "").toLowerCase().includes("admin access required")) {
      state.isAdmin = false;
      state.adminEmail = null;
      syncAdminUI();
      $("adminModal").classList.remove("hidden");
      showToast("Admin session expired — please sign in again");
      navigate("home", {}, false);
      return;
    }
    throw err;
  }

  const subjects = subData.subjects || [];
  let chapters = [];
  for (const s of subjects) {
    const cData = await api(`/api/subjects/${encodeURIComponent(s.id)}/chapters`);
    chapters = chapters.concat(cData.chapters || []);
  }

  const files = filesData.files || [];
  const customFormulas = (formulasData.formulas || []).filter((f) => f.isCustom);
  const customQuizzes = quizzesData.quizzes || [];
  const students = studentsData.students || [];

  const studentsHtml = students.length
    ? students
        .map((s) => {
          const shortId = s.session_id.length > 14 ? `${s.session_id.slice(0, 12)}…` : s.session_id;
          const lastStr = s.last_active ? new Date(s.last_active).toLocaleString() : "N/A";
          const clsStr = (s.classes || []).map((c) => c.replace("_", " ")).join(", ") || "All";
          return `
            <div class="card" style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
              <div>
                <strong>Student #${escapeHtml(shortId)}</strong>
                <span class="badge badge-indigo" style="margin-left:6px;">${escapeHtml(clsStr)}</span>
                <div class="muted" style="margin-top:4px;">
                  Quizzes: <strong>${s.quiz_count}</strong> (Avg ${s.avg_quiz_pct}%) • Papers: <strong>${s.paper_count}</strong> • Chapters Read: <strong>${s.chapters_read}</strong> • Notes: <strong>${s.notes_count}</strong> • Bookmarks: <strong>${s.bookmarks_count}</strong>
                </div>
                <div class="muted" style="font-size:12px;">Last active: ${escapeHtml(lastStr)}</div>
              </div>
              <button class="btn btn-sm btn-primary" onclick="viewStudentDetail('${escapeHtml(s.session_id)}')">View Activity</button>
            </div>`;
        })
        .join("")
    : '<div class="card"><p class="muted">No student activity recorded yet. Once students read chapters, take quizzes, or save notes, they will appear here.</p></div>';

  main.innerHTML = `
    <div class="card" style="margin-bottom:18px;border-color:var(--amber);">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
        <div>
          <span class="badge badge-amber">OWNER ADMIN DASHBOARD</span>
          <h2 style="margin:6px 0 2px;">Signed in as ${escapeHtml(state.adminEmail)}</h2>
          <p class="muted" style="margin:0;">Upload student files, formula sheets, and add new formulas or quiz questions for ${escapeHtml(state.classId.replace("_", " "))}.</p>
        </div>
        <button id="adminLogoutBtn" class="btn btn-sm btn-rose">Sign Out Admin</button>
      </div>
    </div>

    <div class="grid-2">
      <!-- Upload File -->
      <div class="card">
        <h3 style="margin-top:0;">📁 Upload Student File / Formula Sheet</h3>
        <div style="display:flex;flex-direction:column;gap:10px;">
          <input id="admFileTitle" class="input" placeholder="Title (e.g. Class 10 Physics Formula Sheet)" />
          <select id="admFileCat" class="class-select">
            <option value="Formula Sheet">Formula Sheet</option>
            <option value="Chapter Notes">Chapter Notes</option>
            <option value="Practice Paper">Practice Paper</option>
            <option value="Assignment">Assignment</option>
          </select>
          <input id="admFileDesc" class="input" placeholder="Short description (optional)" />
          <input id="admFileInput" class="input" type="file" />
          <button id="admUploadBtn" class="btn btn-primary">Upload File</button>
        </div>
      </div>

      <!-- Add Formula -->
      <div class="card">
        <h3 style="margin-top:0;">📐 Add New Formula</h3>
        <div style="display:flex;flex-direction:column;gap:10px;">
          <select id="admFormulaChap" class="class-select">
            ${chapters.map((c) => `<option value="${escapeHtml(c.id)}" data-sub="${escapeHtml(c.subjectId)}" data-title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</option>`).join("")}
          </select>
          <input id="admFormulaName" class="input" placeholder="Formula Name (e.g. Lens Maker's Formula)" />
          <input id="admFormulaText" class="input" placeholder="Formula (e.g. 1/f = (n - 1)(1/R1 - 1/R2))" />
          <input id="admFormulaTerms" class="input" placeholder="Terms (e.g. f = focal length, n = refractive index)" />
          <input id="admFormulaTip" class="input" placeholder="Application tip" />
          <button id="admAddFormulaBtn" class="btn btn-emerald">Add Formula</button>
        </div>
      </div>
    </div>

    <!-- Add Quiz Question -->
    <div class="card" style="margin-top:16px;">
      <h3 style="margin-top:0;">❓ Add Quiz Question</h3>
      <div style="display:flex;flex-direction:column;gap:10px;">
        <select id="admQuizChap" class="class-select">
          ${chapters.map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.title)}</option>`).join("")}
        </select>
        <textarea id="admQuizQ" class="textarea" placeholder="Enter question text..."></textarea>
        <div class="grid-2">
          <input id="admOpt0" class="input" placeholder="Option A" />
          <input id="admOpt1" class="input" placeholder="Option B" />
          <input id="admOpt2" class="input" placeholder="Option C" />
          <input id="admOpt3" class="input" placeholder="Option D" />
        </div>
        <div class="grid-3">
          <select id="admCorrect" class="class-select">
            <option value="0">Correct: Option A</option>
            <option value="1">Correct: Option B</option>
            <option value="2">Correct: Option C</option>
            <option value="3">Correct: Option D</option>
          </select>
          <select id="admDiff" class="class-select">
            <option value="easy">Easy</option>
            <option value="medium" selected>Medium</option>
            <option value="hard">Hard</option>
          </select>
          <select id="admType" class="class-select">
            <option value="conceptual">Conceptual</option>
            <option value="numerical">Numerical</option>
            <option value="assertion_reason">Assertion/Reason</option>
          </select>
        </div>
        <input id="admHint" class="input" placeholder="Hint (optional)" />
        <input id="admExp" class="input" placeholder="Explanation for answer" />
        <button id="admAddQuizBtn" class="btn btn-amber">Add Quiz Question</button>
      </div>
    </div>

    <div class="section-header" style="margin-top:20px;">
      <h3>👨‍🎓 All Students Access &amp; Progress (${students.length})</h3>
      <button class="btn btn-sm btn-outline" onclick="renderCurrentView()">↻ Refresh</button>
    </div>
    <div class="grid-3" style="margin-bottom:12px;">
      <div class="card"><div class="muted">Active Students</div><h2 style="margin:4px 0 0;">${studentsData.total_students || 0}</h2></div>
      <div class="card"><div class="muted">Total Quizzes Taken</div><h2 style="margin:4px 0 0;">${studentsData.total_quizzes || 0}</h2></div>
      <div class="card"><div class="muted">Papers / Notes</div><h2 style="margin:4px 0 0;">${studentsData.total_papers || 0} / ${studentsData.total_notes || 0}</h2></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:18px;">
      ${studentsHtml}
    </div>

    <div class="section-header"><h3>Uploaded Files (${files.length})</h3></div>
    <div class="grid-2">
      ${files
        .map(
          (f) => `
        <div class="card" style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <div>
            <strong>${escapeHtml(f.title)}</strong>
            <div class="muted">${escapeHtml(f.class_level)} • ${escapeHtml(f.category)} • ${escapeHtml(f.filename)}</div>
          </div>
          <button class="btn btn-sm btn-rose" onclick="admDeleteFile(${f.id})">Delete</button>
        </div>`
        )
        .join("") || '<div class="card"><p class="muted">No uploaded files yet.</p></div>'}
    </div>

    <div class="section-header"><h3>Custom Formulas (${customFormulas.length}) & Quizzes (${customQuizzes.length})</h3></div>
    <div class="grid-2">
      ${customFormulas
        .map(
          (f) => `
        <div class="card" style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <div><strong>${escapeHtml(f.name)}</strong><div class="muted">${escapeHtml(f.formulaText)}</div></div>
          <button class="btn btn-sm btn-rose" onclick="admDeleteFormula(${f.db_id})">Delete</button>
        </div>`
        )
        .join("")}
      ${customQuizzes
        .map(
          (q) => `
        <div class="card" style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <div><strong>${escapeHtml(q.questionText.slice(0, 70))}...</strong><div class="muted">${escapeHtml(q.chapterId)}</div></div>
          <button class="btn btn-sm btn-rose" onclick="admDeleteQuiz(${q.db_id})">Delete</button>
        </div>`
        )
        .join("")}
    </div>
  `;

  $("adminLogoutBtn").onclick = logoutAdmin;

  $("admUploadBtn").onclick = async () => {
    const fileEl = $("admFileInput");
    const title = $("admFileTitle").value.trim();
    if (!fileEl.files.length || !title) {
      showToast("Please select a file and enter a title");
      return;
    }
    const fd = new FormData();
    fd.append("file", fileEl.files[0]);
    fd.append("title", title);
    fd.append("class_level", state.classId);
    fd.append("category", $("admFileCat").value);
    fd.append("description", $("admFileDesc").value.trim());
    await api("/api/admin/files", { method: "POST", body: fd });
    showToast("File uploaded for students!");
    renderAdmin(main);
  };

  $("admAddFormulaBtn").onclick = async () => {
    const sel = $("admFormulaChap");
    const opt = sel.options[sel.selectedIndex];
    const name = $("admFormulaName").value.trim();
    const text = $("admFormulaText").value.trim();
    if (!name || !text) {
      showToast("Enter formula name and equation");
      return;
    }
    await api("/api/admin/formulas", {
      method: "POST",
      body: JSON.stringify({
        class_level: state.classId,
        subject_id: opt.dataset.sub,
        chapter_id: sel.value,
        chapter_title: opt.dataset.title,
        name,
        formula_text: text,
        where_terms: $("admFormulaTerms").value.trim(),
        application_note: $("admFormulaTip").value.trim(),
      }),
    });
    showToast("Formula added!");
    renderAdmin(main);
  };

  $("admAddQuizBtn").onclick = async () => {
    const qText = $("admQuizQ").value.trim();
    const opts = [$("admOpt0").value.trim(), $("admOpt1").value.trim(), $("admOpt2").value.trim(), $("admOpt3").value.trim()];
    if (!qText || opts.some((o) => !o)) {
      showToast("Fill question and all 4 options");
      return;
    }
    await api("/api/admin/quizzes", {
      method: "POST",
      body: JSON.stringify({
        chapter_id: $("admQuizChap").value,
        question_text: qText,
        options: opts,
        correct_option_index: Number($("admCorrect").value),
        difficulty: $("admDiff").value,
        question_type: $("admType").value,
        hint: $("admHint").value.trim(),
        explanation: $("admExp").value.trim(),
      }),
    });
    showToast("Quiz question added!");
    renderAdmin(main);
  };
}

window.admDeleteFile = async (id) => {
  await api(`/api/admin/files/${id}`, { method: "DELETE" });
  showToast("File deleted");
  renderCurrentView();
};
window.admDeleteFormula = async (id) => {
  await api(`/api/admin/formulas/${id}`, { method: "DELETE" });
  showToast("Formula deleted");
  renderCurrentView();
};
window.admDeleteQuiz = async (id) => {
  await api(`/api/admin/quizzes/${id}`, { method: "DELETE" });
  showToast("Quiz deleted");
  renderCurrentView();
};
window.viewStudentDetail = async (sessionId) => {
  const modal = $("studentDetailModal");
  const body = $("studentDetailBody");
  modal.classList.remove("hidden");
  body.innerHTML = "<p class='muted'>Loading student records...</p>";
  try {
    const d = await api(`/api/admin/students/${encodeURIComponent(sessionId)}`);
    const quizzes = (d.quiz_attempts || []).map((q) => `<li><strong>${escapeHtml(q.chapter_title)}</strong> (${escapeHtml(q.class_level)}) — ${q.score}/${q.total_questions}</li>`).join("") || "<li class='muted'>None</li>";
    const papers = (d.paper_attempts || []).map((p) => `<li><strong>${escapeHtml(p.paper_title)}</strong> — ${p.marks_obtained}/${p.total_marks}</li>`).join("") || "<li class='muted'>None</li>";
    const notes = (d.user_notes || []).map((n) => `<li><strong>${escapeHtml(n.chapter_title)}:</strong> ${escapeHtml(n.note_text)}</li>`).join("") || "<li class='muted'>None</li>";
    const readChaps = (d.chapter_progress || []).filter((c) => c.is_read).length;
    body.innerHTML = `
      <p><strong>Session ID:</strong> <code>${escapeHtml(d.session_id)}</code></p>
      <p><strong>Chapters Marked Read:</strong> ${readChaps} • <strong>Bookmarks:</strong> ${(d.bookmarks || []).length}</p>
      <h4>Quiz Attempts (${(d.quiz_attempts || []).length})</h4><ul>${quizzes}</ul>
      <h4>Paper Attempts (${(d.paper_attempts || []).length})</h4><ul>${papers}</ul>
      <h4>Student Notes (${(d.user_notes || []).length})</h4><ul>${notes}</ul>
    `;
  } catch (err) {
    body.innerHTML = `<p style="color:var(--rose);">Error: ${escapeHtml(err.message)}</p>`;
  }
};

async function init() {
  const savedTheme = localStorage.getItem("eduprep_theme") || "light";
  setTheme(savedTheme);

  $("themeToggleBtn").onclick = () => setTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
  $("mobileThemeBtn").onclick = () => setTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
  $("backBtn").onclick = goBack;

  $("adminLoginTrigger").onclick = () => {
    if (state.isAdmin) navigate("admin", {}, false);
    else $("adminModal").classList.remove("hidden");
  };
  $("closeAdminModal").onclick = () => $("adminModal").classList.add("hidden");
  if ($("sidebarAdminLogoutBtn")) $("sidebarAdminLogoutBtn").onclick = logoutAdmin;
  if ($("topAdminLogoutBtn")) $("topAdminLogoutBtn").onclick = logoutAdmin;
  if ($("closeStudentDetailModal")) $("closeStudentDetailModal").onclick = () => $("studentDetailModal").classList.add("hidden");
  $("adminLoginSubmit").onclick = async () => {
    const email = $("adminEmailInput").value.trim();
    const password = $("adminPassInput").value;
    const errEl = $("adminLoginError");
    errEl.style.display = "none";
    try {
      const res = await api("/api/auth/admin-login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      state.isAdmin = res.is_admin;
      state.adminEmail = res.email;
      syncAdminUI();
      $("adminModal").classList.add("hidden");
      showToast("Admin Studio unlocked!");
      navigate("admin", {}, false);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = "block";
    }
  };

  const syncClass = (val) => {
    state.classId = val;
    localStorage.setItem("eduprep_class", val);
    $("globalClassSelect").value = val;
    $("mobileClassSelect").value = val;
    state.historyStack = [];
    navigate("home", {}, false);
  };

  $("globalClassSelect").value = state.classId;
  $("mobileClassSelect").value = state.classId;
  $("globalClassSelect").onchange = (e) => syncClass(e.target.value);
  $("mobileClassSelect").onchange = (e) => syncClass(e.target.value);

  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.onclick = () => {
      state.historyStack = [];
      navigate(btn.dataset.view, {}, false);
    };
  });

  await handleDakshSSOIfPresent();
  const [clsData] = await Promise.all([api("/api/classes"), refreshProgress()]);
  state.classes = clsData.classes;
  renderCurrentView();
}

init();
