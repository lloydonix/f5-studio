/* F5 Studio front end. Talks to the local backend in app/studio/server.py. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const I = {
    play: '<svg viewBox="0 0 20 20"><path d="M6 4l10 6-10 6z"/></svg>',
    pause: '<svg viewBox="0 0 20 20"><path d="M7 4v12M13 4v12"/></svg>',
    redo: '<svg viewBox="0 0 20 20"><path d="M16 10a6 6 0 1 1-2-4.5M16 3v4h-4"/></svg>',
    chev: '<svg viewBox="0 0 20 20" class="chev"><path d="M8 5l5 5-5 5"/></svg>',
    upload: '<svg viewBox="0 0 20 20"><path d="M10 13V3M6 7l4-4 4 4M4 13v3h12v-3"/></svg>',
    check: '<svg viewBox="0 0 20 20"><path d="M4 10l4 4 8-8"/></svg>',
    warn: '<svg viewBox="0 0 20 20"><path d="M10 3l8 14H2zM10 8v4M10 14.5v.5"/></svg>',
    file: '<svg viewBox="0 0 20 20"><path d="M6 2h6l4 4v12H6zM12 2v4h4"/></svg>',
    trash: '<svg viewBox="0 0 20 20"><path d="M4 6h12M8 6V4h4v2M6 6l1 11h6l1-11"/></svg>',
    plus: '<svg viewBox="0 0 20 20"><path d="M10 4v12M4 10h12"/></svg>',
    mic: '<svg viewBox="0 0 20 20"><path d="M10 2a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3zM5 10a5 5 0 0 0 10 0M10 15v3"/></svg>',
    spark: '<svg viewBox="0 0 20 20"><path d="M10 2l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/></svg>',
    save: '<svg viewBox="0 0 20 20"><path d="M4 4h9l3 3v9H4zM7 4v4h6V4M7 16v-5h6v5"/></svg>',
  };

  const S = {
    overview: null, project: null, prons: null, models: null,
    pid: null, step: "generate",
    filter: "all", playing: null, scriptDirty: false, sourceDirty: false,
    exportOpts: { format: "mp3", quality: "high", name: "" },
  };
  try { S.pid = localStorage.getItem("pid"); S.step = localStorage.getItem("step") || "generate"; } catch { }

  /* ---------- helpers ---------- */
  async function api(method, path, body) {
    const opt = { method, headers: {} };
    if (body instanceof FormData) opt.body = body;
    else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["content-type"] = "application/json"; }
    const r = await fetch(path, opt);
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { }
      throw new Error(msg);
    }
    const ct = r.headers.get("content-type") || "";
    return ct.includes("json") ? r.json() : r;
  }
  const attempt = fn => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message); } };
  function toast(msg, ms = 3200) {
    const t = $("#toast");
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("show"), ms);
  }
  const save = (k, v) => { try { localStorage.setItem(k, v); } catch { } };
  const fmtDur = s => {
    if (s == null) return "–";
    s = Math.round(s);
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
    return h ? `${h}h ${m}m` : m ? `${m}m ${String(sec).padStart(2, "0")}s` : `${sec}s`;
  };
  const shortPath = f => String(f || "").replace(/^\/Users\/[^/]+/, "~");
  const words = t => t.trim() ? t.trim().split(/\s+/).length : 0;
  const allParas = p => p.sections.flatMap(s => s.paras);
  const wpm = x => words(x.text) / x.dur * 60;
  const isFlagged = x => x.dur && words(x.text) > 4 && (wpm(x) < 100 || wpm(x) > 220);
  const voiceById = id => (S.overview?.voices || []).find(v => v.id === id);
  const worker = () => S.overview?.worker || {};
  const debounce = (fn, ms) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; };

  function modal(title, bodyHTML, okLabel = "OK") {
    return new Promise(resolve => {
      $("#modalTitle").textContent = title;
      $("#modalBody").innerHTML = bodyHTML;
      $("#modalOk").textContent = okLabel;
      $("#modal").hidden = false;
      const first = $("#modalBody input, #modalBody select, #modalBody textarea");
      if (first) setTimeout(() => first.focus(), 30);
      const done = v => { $("#modal").hidden = true; $("#modalForm").onsubmit = null; resolve(v); };
      $("#modalForm").onsubmit = e => {
        e.preventDefault();
        done(Object.fromEntries($$("#modalBody [name]").map(i => [i.name, i.type === "checkbox" ? i.checked : i.value])));
      };
      $("#modalCancel").onclick = () => done(null);
    });
  }

  /* ---------- audio ---------- */
  const player = $("#player");
  function play(src, key, onTick) {
    if (S.playing === key) { player.pause(); S.playing = null; refreshPlay(); return; }
    player.src = src; player.currentTime = 0;
    player.play().catch(() => toast("Couldn't play that clip."));
    S.playing = key; player.ontimeupdate = onTick || null; refreshPlay();
  }
  player.onended = () => { S.playing = null; refreshPlay(); };
  function refreshPlay() {
    $$("[data-play]").forEach(b => { const on = b.dataset.play === S.playing; b.classList.toggle("playing", on); b.innerHTML = on ? I.pause : I.play; });
  }

  /* ---------- data ---------- */
  async function loadOverview() {
    S.overview = await api("GET", "/api/state");
    if (!S.overview.projects.find(p => p.id === S.pid)) S.pid = S.overview.projects[0]?.id || null;
  }
  async function loadProject() {
    S.project = S.pid ? await api("GET", `/api/projects/${S.pid}`) : null;
    S.scriptDirty = S.sourceDirty = false;
  }

  /* ---------- sidebar & header ---------- */
  function ring(p) {
    const r = 11, c = 2 * Math.PI * r, f = p.total ? p.done / p.total : 0;
    return `<svg class="ring ${p.total && f >= 1 ? "complete" : ""}" viewBox="0 0 28 28"><circle class="bg" cx="14" cy="14" r="${r}"/>
      <circle class="fg" cx="14" cy="14" r="${r}" stroke-dasharray="${c * f} ${c}"/></svg>`;
  }
  function renderSidebar() {
    const o = S.overview, w = worker();
    $("#projectList").innerHTML = o.projects.map(p => `
      <button class="proj-item ${p.id === S.pid ? "active" : ""}" data-pid="${p.id}">${ring(p)}
        <div><div class="name">${esc(p.title)}</div>
        <div class="sub">${!p.total ? "No script yet" : p.done >= p.total ? fmtDur(p.audio) + " · done"
          : (w.running && w.current?.project === p.id ? "Generating · " : "") + `${p.done}/${p.total} paragraphs`}</div></div>
      </button>`).join("") || '<div class="small muted" style="padding:8px">No projects yet.</div>';
    if (S.cog) renderCog();
    $("#voiceCount").textContent = o.voices.length;
    $("#pronCount").textContent = o.pronunciations;
    const busy = w.running;
    $(".engine .dot").className = "dot " + (w.error ? "dot-warn" : busy ? "dot-busy" : "dot-ok");
    $(".engine-sub").textContent = w.error ? "Stopped with an error"
      : w.running ? (w.engine === "loading" ? "Loading the voice model…" : `Generating ${titleOf(w.current?.project)}`)
      : "Offline · idle";
  }
  const titleOf = pid => (S.overview.projects.find(p => p.id === pid)?.title || "").split(" · ").pop();

  function renderHeader() {
    const p = S.project;
    if (!p) {
      $("#projTitle").textContent = "Welcome";
      $("#projState").className = "chip"; $("#projState").textContent = "";
      $("#projMeta").innerHTML = '<span>Create a project to get started.</span>';
      return;
    }
    const w = worker(), mine = w.running && w.current?.project === p.id, done = p.total && p.done >= p.total;
    $("#projTitle").textContent = p.title;
    const chip = $("#projState");
    chip.className = "chip " + (mine ? "chip-busy" : done ? "chip-ok" : p.total ? "chip-warn" : "");
    chip.innerHTML = mine ? '<span class="dot dot-busy"></span>Generating' : done ? "Complete" : p.done ? "Paused" : p.total ? "Not started" : "Empty";
    const v = voiceById(p.voice);
    $("#projMeta").innerHTML = `
      <span>Voice <b>${esc(v?.name || "none")}</b></span>
      ${p.persona ? `<span>Persona <b>${esc(p.persona)}</b></span>` : ""}
      <span><b>${p.words.toLocaleString()}</b> words</span>
      <span><b>${fmtDur(done ? p.audio : p.words / 150 * 60)}</b> ${done ? "of audio" : "estimated audio"}</span>`;
    $$(".step").forEach(b => b.classList.toggle("active", b.dataset.step === S.step));
  }

  /* ---------- 1. script ---------- */
  function checkHTML(c) {
    if (!c) return '<p class="small muted" style="margin:0">Paste your original notes under <b>Source notes</b> and this checks that no numbers or citations got lost.</p>';
    const row = (ok, txt) => `<li><span class="${ok ? "ok" : "warn"}">${ok ? I.check : I.warn}</span><span>${txt}</span></li>`;
    return `<ul class="check-list">
      ${row(!c.numbers_missing.length, c.numbers_missing.length ? `<b>${c.numbers_missing.length}</b> numbers missing: ${esc(c.numbers_missing.slice(0, 12).join(", "))}` : `All <b>${c.numbers}</b> numbers kept`)}
      ${row(!c.citations_missing.length, c.citations_missing.length ? `Missing citations: ${esc(c.citations_missing.slice(0, 6).join("; "))}` : `All <b>${c.citations}</b> citations kept`)}
      ${row(c.headings_script >= c.headings_source, `${c.headings_script} of ${c.headings_source} headings`)}
    </ul>`;
  }
  function cogPickerHTML(p) {
    const c = S.cog;
    if (!c) return '<p class="small muted" style="margin:14px 0 0">Looking for the Cogitator…</p>';
    if (!c.available) return `<p class="small muted" style="margin:14px 0 0">The Cogitator's scripts folder (~/study/scripts) isn't there yet.</p>`;
    const linked = p.origin?.cogitator, li = c.items.find(i => i.name === linked);
    const ready = c.items.filter(i => i.state !== "writing");
    const protect = !linked && (p.done > 0 || p.script.trim());   // don't swap scripts in a project that has its own
    return `
      ${linked ? `<div class="row" style="margin-top:14px;padding:10px 12px;border-radius:10px;background:var(--panel-2)">
        <span class="small"><b>Linked to</b> ${esc(linked.replace(/\.txt$/, ""))}${li ? ` · ${li.changed ? '<span class="tag tag-updated">updated in the Cogitator</span>' : '<span class="tag tag-imported">up to date</span>'}` : ' · <span class="tag tag-incomplete">no longer in the folder</span>'}</span>
        <span class="spacer"></span>${li?.changed ? `<button class="btn btn-primary" data-cogpull="${esc(linked)}">${I.redo}Update</button>` : ""}</div>` : ""}
      <div class="row" style="margin-top:14px;flex-wrap:nowrap">
        <select id="cogSel" style="flex:1" ${ready.length ? "" : "disabled"}>${ready.length ? ready.map(i => `<option value="${esc(i.name)}" ${i.name === linked ? "selected" : ""}>
          ${esc(i.subject)} · ${esc(i.label)} (${esc(i.voice)}, ${i.words.toLocaleString()} words${i.state === "incomplete" ? ", unfinished" : ""})</option>`).join("")
          : "<option>No finished scripts yet</option>"}</select>
        ${protect
          ? `<button class="btn btn-primary" id="cogNew" ${ready.length ? "" : "disabled"}>Import as a new project</button>`
          : `<button class="btn btn-primary" id="cogUse" ${ready.length ? "" : "disabled"}>Use this script</button>`}
      </div>
      ${protect && ready.length ? `<div class="row" style="margin-top:8px"><span class="small muted">This project already has ${p.done ? `audio for ${p.done} paragraphs` : "its own script"}, so a Cogitator script becomes a new project.</span>
        <span class="spacer"></span><button class="btn btn-ghost" id="cogUse">Replace this project's script instead</button></div>` : ""}
      ${c.items.some(i => i.state === "writing") ? `<p class="small muted" style="margin:8px 0 0">${c.items.filter(i => i.state === "writing").map(i => esc(i.subject + " · " + i.label)).join(", ")} is still being written${c.job?.total ? ` (${c.job.done}/${c.job.total})` : ""}.</p>` : ""}
      <div class="row" style="margin-top:12px"><button class="btn" id="cogOpen">Open the Cogitator</button>
        <span class="small muted">Write it in the Scriptorium (Workspace → Scriptorium), then pick it above.</span></div>`;
  }
  function renderScript() {
    const p = S.project, mode = p.writer?.mode === "cogitator" ? "cogitator" : "paste", est = p.words / 150 * 60;
    $("#view-script").innerHTML = `
      <div class="grid-side">
        <div class="stack">
          <div class="card">
            <div class="card-head"><div><div class="card-title">Who writes the script</div>
              <div class="card-sub">Both are free. You can switch any time; the rest of the app works the same.</div></div></div>
            <div class="card-pad">
              <div class="seg" id="writerSeg">
                <button data-mode="paste" class="${mode === "paste" ? "on" : ""}">Paste from Claude</button>
                <button data-mode="cogitator" class="${mode === "cogitator" ? "on" : ""}">The Cogitator</button>
              </div>
              <p class="small muted" style="margin:12px 0 0">${mode === "paste"
                ? "Ask Claude for the script in chat, then paste it below. Best quality, and free with your Claude plan."
                : "The Cogitator's Scriptorium writes it from your reviewer and the notes it links to, in the character you choose. Pick a finished script to put it in this project. If it's rewritten later, this project shows it as updated."}</p>
              ${mode === "cogitator" ? `<div id="cogPicker">${cogPickerHTML(p)}</div>` : ""}
            </div>
          </div>

          <div class="card">
            <div class="card-head">
              <div><div class="card-title">Script</div><div class="card-sub">Headings go between ===== or ----- lines. Each line becomes one paragraph.</div></div>
              <div class="row"><span class="saved-note" id="scriptNote">Saved</span>
                <button class="btn" id="openTxt">${I.upload}Open .txt</button>
                <button class="btn btn-primary" id="saveScript">${I.save}Save</button></div>
            </div>
            <div class="card-pad"><textarea class="editor" id="scriptBox" spellcheck="false" placeholder="Paste the script here.">${esc(p.script)}</textarea></div>
          </div>

          <div class="card">
            <div class="card-head">
              <div><div class="card-title">Source notes</div><div class="card-sub">Your original reviewer, for the fact check.</div></div>
              <div class="row"><span class="saved-note" id="sourceNote">Saved</span><button class="btn" id="saveSource">${I.save}Save</button></div>
            </div>
            <div class="card-pad"><textarea id="sourceBox" rows="8" spellcheck="false" placeholder="Paste the original notes here.">${esc(p.source)}</textarea></div>
          </div>
        </div>

        <div class="stack">
          <div class="card card-pad">
            <div class="card-title" style="margin-bottom:12px">Persona</div>
            <label class="label">Name shown on the project</label>
            <input type="text" id="personaName" value="${esc(p.persona)}" placeholder="e.g. Shadowheart (dom)">
          </div>
          <div class="card card-pad"><div class="card-title" style="margin-bottom:10px">Fact check against source</div><div id="checkBox">${checkHTML(p.check)}</div></div>
          <div class="card card-pad">
            <div class="card-title" style="margin-bottom:10px">Estimate</div>
            <div class="voice-stats" style="grid-template-columns:1fr 1fr">
              <div class="stat"><div class="k">Audio</div><div class="v">${fmtDur(est)}</div></div>
              <div class="stat"><div class="k">Generation</div><div class="v">${fmtDur(est * (worker().ratio || 6.5))}</div></div>
            </div>
          </div>
        </div>
      </div>`;

    const sBox = $("#scriptBox"), srcBox = $("#sourceBox");
    sBox.oninput = () => { S.scriptDirty = true; $("#scriptNote").textContent = "Unsaved"; $("#scriptNote").classList.add("dirty"); };
    srcBox.oninput = () => { S.sourceDirty = true; $("#sourceNote").textContent = "Unsaved"; $("#sourceNote").classList.add("dirty"); };
    $("#saveScript").onclick = attempt(saveScript);
    $("#saveSource").onclick = attempt(saveSource);
    $("#openTxt").onclick = () => $("#pickScript").click();
    $$("#writerSeg button").forEach(b => b.onclick = attempt(async () => {
      if (S.scriptDirty || S.sourceDirty) return toast("Save your text first.");
      p.writer = { ...p.writer, mode: b.dataset.mode };
      await api("PUT", `/api/projects/${p.id}/settings`, { writer: p.writer });
      if (b.dataset.mode === "cogitator") await loadCog();
      renderScript();
    }));
    $("#personaName").onchange = attempt(async e => { await api("PUT", `/api/projects/${p.id}/settings`, { persona: e.target.value }); p.persona = e.target.value; renderHeader(); });
    bindCogPicker();
  }
  function bindCogPicker() {
    const use = $("#cogUse");
    if (use) use.onclick = attempt(() => useCogScript($("#cogSel").value));
    const nw = $("#cogNew");
    if (nw) nw.onclick = attempt(() => importCogAsNew($("#cogSel").value));
    $$("[data-cogpull]").forEach(b => b.onclick = attempt(() => useCogScript(b.dataset.cogpull)));
    const op = $("#cogOpen");
    if (op) op.onclick = attempt(() => api("POST", "/api/cogitator/open"));
  }
  async function importCogAsNew(name) {
    const it = S.cog.items.find(i => i.name === name);
    if (it?.project) { await selectProject(it.project); return toast("That script already has its own project. Here it is."); }
    const pr = await api("POST", "/api/cogitator/import", { name });
    await loadCog(); await loadOverview(); await selectProject(pr.id); go("script");
    toast(`Imported as a new project: ${pr.title}.`);
  }
  async function useCogScript(name) {
    if (S.scriptDirty || S.sourceDirty) return toast("Save your text first.");
    const p = S.project, it = S.cog.items.find(i => i.name === name), label = it ? it.subject + " · " + it.label : name;
    const replacing = p.script.trim() && p.origin?.cogitator !== name;
    if (replacing && !confirm(p.done
        ? `Replace "${p.title}" with "${label}"?\n\nIts current script has audio for ${p.done} paragraphs. That audio stays on disk, but none of it will match the new script.`
        : `Replace this project's script with "${label}"?`)) return;
    await api("POST", "/api/cogitator/import", { name, project: p.id, replace: !!replacing });
    await loadProject(); await refreshOverview(); await loadCog(); renderScript();
    toast(`Script loaded: ${S.project.total} paragraphs, ${S.project.done} already have audio.`);
  }
  async function saveScript() {
    S.project = await api("PUT", `/api/projects/${S.pid}/script`, { script: $("#scriptBox").value });
    S.scriptDirty = false;
    await refreshOverview();
    renderScript();
    toast(`Saved. ${S.project.total} paragraphs, ${S.project.done} already have audio.`);
  }
  async function saveSource() {
    const r = await api("PUT", `/api/projects/${S.pid}/source`, { source: $("#sourceBox").value });
    S.project.source = $("#sourceBox").value; S.project.check = r.check; S.sourceDirty = false;
    $("#sourceNote").textContent = "Saved"; $("#sourceNote").classList.remove("dirty");
    $("#checkBox").innerHTML = checkHTML(r.check);
  }
  $("#pickScript").onchange = e => {
    const f = e.target.files[0]; if (!f) return;
    f.text().then(t => { $("#scriptBox").value = t; $("#scriptBox").oninput(); toast(`Loaded ${f.name}. Press Save to keep it.`); });
    e.target.value = "";
  };

  /* ---------- 2. pronunciation ---------- */
  const shown = r => r.say.match(/\w/) ? r : { ...r, term: r.term.replace(/[^\w' -]/g, "").trim(), say: "(removed)" };
  const AUTO = "JDR ADR SPA MR MRS SC PNB IRAS LED FEC RTC MTC TRO".split(" ");
  function suggestions() {
    if (!S.project) return [];
    const known = new Set(S.prons.map(r => r.term.trim().toLowerCase()));
    AUTO.forEach(a => known.add(a.toLowerCase()));
    const skip = new Set("RULE PART AND THE OF VS II III IV PURE FAME CAP DEW JDN CIVIL TO ON BY OR IN NO AN AT IS IT".split(" "));
    const prose = S.project.script.split("\n").filter(l => /[a-z]/.test(l)).join("\n");
    const found = new Set();
    (prose.match(/\b[A-Z]{2,5}\b/g) || []).forEach(a => { if (!known.has(a.toLowerCase()) && !skip.has(a)) found.add(a); });
    return [...found].slice(0, 8).map(a => ({ term: a, say: a.split("").join("-") }));
  }
  async function renderPron(q = "") {
    if (!S.prons) S.prons = await api("GET", "/api/pronunciations");
    const rows = S.prons.map((r, i) => ({ ...shown(r), i })).filter(r => !q || (r.term + r.say).toLowerCase().includes(q.toLowerCase()));
    const sug = suggestions(), v = voiceById(S.project?.voice);
    $("#view-pron").innerHTML = `
      <div class="grid-side">
        <div class="card">
          <div class="card-head">
            <div><div class="card-title">Pronunciation list</div><div class="card-sub">Shared by every project. Changes apply to paragraphs not generated yet.</div></div>
            <div class="row" style="flex-wrap:nowrap">
              <input type="search" id="pronSearch" placeholder="Search ${S.prons.length} terms" value="${esc(q)}" style="width:210px">
              <button class="btn" id="addTerm">${I.plus}Add</button></div>
          </div>
          <div class="pron-scroll"><table class="pron-table">
            <thead><tr><th style="width:40%">Written</th><th>Spoken as</th><th style="width:76px"></th></tr></thead>
            <tbody>${rows.map(r => `<tr><td class="term">${esc(r.term)}</td>
              <td>${r.say === "(removed)" ? '<span class="muted small" style="padding-left:8px">(removed)</span>' : `<input type="text" data-say="${r.i}" value="${esc(r.say)}">`}</td>
              <td><div class="row" style="gap:0;flex-wrap:nowrap">
                <button class="icon-btn" title="Hear it" data-hear="${r.i}" ${v ? "" : "disabled"}>${I.play}</button>
                <button class="icon-btn" title="Remove" data-del="${r.i}">${I.trash}</button></div></td></tr>`).join("")}</tbody>
          </table></div>
        </div>
        <div class="stack">
          <div class="card card-pad">
            <div class="card-title">New terms in this script</div>
            <div class="card-sub" style="margin-bottom:6px">Acronyms the list doesn't cover yet.</div>
            ${sug.length ? sug.map(s => `<div class="suggest"><b style="min-width:52px">${esc(s.term)}</b><span class="muted small">→ ${esc(s.say)}</span>
              <span class="spacer"></span><button class="btn" data-addsug="${esc(s.term)}|${esc(s.say)}">Add</button></div>`).join("")
              : '<p class="small muted">Nothing new. Every acronym is covered.</p>'}
          </div>
          <div class="card card-pad">
            <div class="card-title" style="margin-bottom:10px">Test a line</div>
            <textarea rows="3" id="testLine">Under Rule 39, the writ must follow the fallo, and a supersedeas bond stays discretionary execution.</textarea>
            <div class="small muted" id="testSpoken" style="margin-top:8px"></div>
            <div class="row" style="margin-top:10px"><span class="small muted">${v ? `In ${esc(v.name)}'s voice` : "Pick a voice first"}</span><span class="spacer"></span>
              <button class="btn btn-primary" id="speakBtn" ${v ? "" : "disabled"}>${I.play}Speak it</button></div>
          </div>
        </div>
      </div>`;
    const s = $("#pronSearch");
    s.oninput = () => { const pos = s.selectionStart; renderPron(s.value).then(() => { const n = $("#pronSearch"); n.focus(); n.setSelectionRange(pos, pos); }); };
    $("#addTerm").onclick = attempt(async () => {
      const r = await modal("Add a pronunciation", `
        <div><label class="label">Written as</label><input type="text" name="term" required placeholder="e.g. habeas data"></div>
        <div><label class="label">Spoken as</label><input type="text" name="say" required placeholder="e.g. hay-bee-as day-ta"></div>`, "Add");
      if (r && r.term.trim() && r.say.trim()) await savePron([...S.prons, { term: r.term.trim(), say: r.say.trim() }], `Added ${r.term.trim()}.`);
    });
    $$("[data-say]").forEach(inp => inp.onchange = attempt(() => {
      const next = S.prons.slice(); next[+inp.dataset.say] = { ...next[+inp.dataset.say], say: inp.value }; return savePron(next, "Saved.");
    }));
    $$("[data-del]").forEach(b => b.onclick = attempt(() => savePron(S.prons.filter((_, i) => i !== +b.dataset.del), "Removed.")));
    $$("[data-addsug]").forEach(b => b.onclick = attempt(() => { const [term, say] = b.dataset.addsug.split("|"); return savePron([...S.prons, { term, say }], `Added ${term}.`); }));
    $$("[data-hear]").forEach(b => b.onclick = attempt(() => speak(S.prons[+b.dataset.hear].term, b)));
    const sb = $("#speakBtn"); if (sb) sb.onclick = attempt(() => speak($("#testLine").value, sb, true));
  }
  async function savePron(list, msg) {
    S.prons = await api("PUT", "/api/pronunciations", list);
    S.overview.pronunciations = S.prons.length;
    renderSidebar(); await renderPron($("#pronSearch")?.value || ""); toast(msg);
  }
  async function speak(text, btn, showSpoken) {
    const old = btn.innerHTML; btn.disabled = true;
    btn.innerHTML = worker().running ? "Waiting for the current paragraph…" : "Speaking…";
    try {
      const r = await api("POST", "/api/preview", { text, voice: S.project.voice, quality: "fast" });
      if (showSpoken) $("#testSpoken").textContent = "Read as: " + (r.headers.get("X-Spoken") || "");
      const url = URL.createObjectURL(await r.blob());
      play(url, "preview");
    } finally { btn.disabled = false; btn.innerHTML = old; }
  }

  /* ---------- 3. voice ---------- */
  const waveCache = {};
  async function drawWave(v) {
    const cv = $("#wave"); if (!cv) return;
    const dpr = devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    const g = cv.getContext("2d"); g.scale(dpr, dpr);
    try {
      if (!waveCache[v.id]) {
        const buf = await (await fetch(`/media/voices/${v.id}/original`)).arrayBuffer();
        waveCache[v.id] = (await new AudioContext().decodeAudioData(buf)).getChannelData(0);
      }
      const data = waveCache[v.id], bars = Math.floor(w / 3), step = Math.max(1, Math.floor(data.length / bars));
      g.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--accent");
      for (let i = 0; i < bars; i++) {
        let m = 0; for (let j = 0; j < step; j += 4) m = Math.max(m, Math.abs(data[i * step + j] || 0));
        const bh = Math.max(2, m * h * .9); g.fillRect(i * 3, (h - bh) / 2, 2, bh);
      }
    } catch { g.fillStyle = "gray"; g.fillText("Couldn't load audio", 12, 20); }
  }
  function renderVoice() {
    const vs = S.overview.voices, v = voiceById(S.project?.voice) || vs[0];
    if (!v) {
      $("#view-voice").innerHTML = `<div class="card"><div class="empty"><b>No voices yet</b>Add a 5–10 second clip of the voice you want.
        <div style="margin-top:14px"><button class="btn btn-primary" id="addVoice2">${I.mic}Add a voice</button></div></div></div>`;
      $("#addVoice2").onclick = () => $("#pickVoice").click();
      return;
    }
    const src = v.source_dur || v.dur, [t0, t1] = v.trim || [0, v.dur];
    $("#view-voice").innerHTML = `
      <div class="grid-side">
        <div class="card">
          <div class="card-head"><div><div class="card-title">${esc(v.name)}</div><div class="card-sub">${esc(v.note)}</div></div>
            <button class="icon-btn" data-play="voice" id="playVoice" title="Play the trimmed clip">${I.play}</button></div>
          <div class="card-pad stack">
            <div class="wave-wrap"><canvas id="wave"></canvas>
              <div class="trim" style="left:${t0 / src * 100}%;right:${100 - t1 / src * 100}%"></div><div class="playhead" id="playhead"></div></div>
            <div class="trim-inputs">
              <div><label class="label">Start (s)</label><input type="text" id="trimStart" value="${t0.toFixed(1)}" inputmode="decimal"></div>
              <div><label class="label">End (s)</label><input type="text" id="trimEnd" value="${t1.toFixed(1)}" inputmode="decimal"></div>
              <button class="btn" id="applyTrim">Apply trim</button>
            </div>
            <div class="small muted">Full recording is ${src}s. F5 uses up to 12 seconds; 5–10 is best.</div>
            <div><label class="label">What's said in the clip</label>
              <textarea rows="2" id="transcript">${esc(v.transcript)}</textarea>
              <div class="row" style="margin-top:8px"><span class="small muted">Transcribed with Whisper. Fix any wrong words, since F5 relies on this.</span><span class="spacer"></span>
                <button class="btn" id="retrans">${I.redo}Re-transcribe</button></div></div>
            <div class="voice-stats">
              <div class="stat"><div class="k">Clip length</div><div class="v">${v.dur}s</div></div>
              <div class="stat"><div class="k">Sample rate</div><div class="v">24 kHz</div></div>
              <div class="stat"><div class="k">Clip quality</div><div class="v" style="color:var(${v.dur >= 4 && v.dur <= 12 ? "--ok" : "--warn"})">${v.dur < 4 ? "Too short" : v.dur > 12 ? "Too long" : "Good"}</div></div>
            </div>
          </div>
        </div>
        <div class="stack">
          <div class="card card-pad">
            <div class="card-title" style="margin-bottom:4px">Voices</div>
            <div class="card-sub" style="margin-bottom:10px">Pick the one this project uses.</div>
            <div class="stack" style="gap:8px">
              ${vs.map(x => `<div class="voice-card ${x.id === v.id ? "on" : ""}" data-vid="${x.id}"><div class="avatar">${esc(x.name[0])}</div>
                <div><div style="font-weight:600">${esc(x.name)}</div><div class="small muted">${x.dur}s${x.note ? " · " + esc(x.note) : ""}</div></div></div>`).join("")}
              <div class="drop" id="voiceDrop">${I.mic}<b>Add a voice</b><span class="small">Drop a clip here or click to choose</span></div>
            </div>
          </div>
          <div class="card card-pad">
            <div class="card-title" style="margin-bottom:10px">What makes a good clip</div>
            <ul class="check-list">
              <li><span class="ok">${I.check}</span>5 to 10 seconds of clear speech</li>
              <li><span class="ok">${I.check}</span>No music or background noise</li>
              <li><span class="ok">${I.check}</span>The tone you want copied, calm or stern</li>
              <li><span class="warn">${I.warn}</span>Only voices that people have agreed to lend you</li>
            </ul>
          </div>
        </div>
      </div>`;
    $("#playVoice").onclick = () => play(`/media/voices/${v.id}.wav?${v.dur}`, "voice", () => {
      const ph = $("#playhead"); if (!ph) return;
      ph.style.display = "block"; ph.style.left = ((t0 + player.currentTime) / src * 100) + "%";
    });
    $("#applyTrim").onclick = attempt(async () => {
      const a = parseFloat($("#trimStart").value), b = parseFloat($("#trimEnd").value);
      if (!(b > a)) return toast("End has to be after start.");
      toast("Trimming and re-transcribing…", 8000);
      await api("POST", `/api/voices/${v.id}/trim`, { start: a, end: b });
      await refreshOverview(); renderVoice(); toast("Trimmed. Lines generated from now on use the new clip.");
    });
    $("#transcript").onchange = attempt(async e => { await api("PUT", `/api/voices/${v.id}`, { transcript: e.target.value }); await refreshOverview(); toast("Transcript saved."); });
    $("#retrans").onclick = attempt(async () => { toast("Transcribing…", 8000); await api("POST", `/api/voices/${v.id}/transcribe`); await refreshOverview(); renderVoice(); toast("Done."); });
    $$("[data-vid]").forEach(c => c.onclick = attempt(async () => {
      if (c.dataset.vid === S.project.voice) return;
      if (S.project.done && !confirm("Switching voices means every paragraph is generated again in the new voice. Continue?")) return;
      await api("PUT", `/api/projects/${S.pid}/settings`, { voice: c.dataset.vid });
      await reloadAll(); toast("Voice changed.");
    }));
    const drop = $("#voiceDrop");
    drop.onclick = () => $("#pickVoice").click();
    drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) addVoice(e.dataTransfer.files[0]); };
    requestAnimationFrame(() => drawWave(v));
  }
  const addVoice = attempt(async file => {
    const r = await modal("Add a voice", `
      <div class="small muted">${esc(file.name)}</div>
      <div><label class="label">Name</label><input type="text" name="name" required placeholder="e.g. Narrator (calm)"></div>
      <div><label class="label">Note (optional)</label><input type="text" name="note" placeholder="e.g. warm, slow"></div>`, "Add voice");
    if (!r || !r.name.trim()) return;
    const fd = new FormData(); fd.append("file", file); fd.append("name", r.name); fd.append("note", r.note || "");
    toast("Adding the voice and transcribing it. This can take a minute.", 60000);
    const v = await api("POST", "/api/voices", fd);
    await refreshOverview();
    if (S.project && !voiceById(S.project.voice)) await api("PUT", `/api/projects/${S.pid}/settings`, { voice: v.id });
    renderVoice(); toast(`Added ${v.name}. Check the transcript, then pick it for a project.`);
  });
  $("#pickVoice").onchange = e => { if (e.target.files[0]) addVoice(e.target.files[0]); e.target.value = ""; };

  /* ---------- splitting long projects into parts (optional) ---------- */
  function splitOfferHTML(sp) {
    if (!sp.suggest) return "";
    return `<div class="card card-pad offer">
      <div><div class="card-title">This will take about ${fmtDur(sp.total_gen)} to generate</div>
        <div class="small muted" style="margin-top:4px">Split it into ${sp.suggested} parts of up to ${sp.hours} hours each? Parts are whole sections, and each one is
        saved to this project's exports folder as soon as it's done, so you can start listening to Part 1 while the rest generates.</div></div>
      <div class="row" style="flex-wrap:nowrap"><button class="btn" data-split="dismiss">Keep as one</button>
        <button class="btn btn-primary" data-split="on">Split into ${sp.suggested} parts</button></div></div>`;
  }
  function partsStripHTML(sp) {
    if (!sp.enabled || !sp.parts.length) return "";
    return `<div class="parts-strip">${sp.parts.map(x => `
      <div class="part-chip ${x.complete ? "done" : x.done ? "going" : ""}" title="${esc(x.first_title)} → ${esc(x.last_title)}">
        <b>Part ${x.n}</b><span>${x.complete ? (x.exported ? "saved ✓" : "done") : `${Math.round(x.done / x.total * 100)}%`}</span>
        <div class="mini"><div style="width:${x.done / x.total * 100}%"></div></div></div>`).join("")}</div>
      <div class="small muted" style="margin-top:8px">Split into parts of up to ${sp.hours} hours${sp.auto_export ? ". Each part is saved to the exports folder when it finishes." : ". Export each part from the Export step."}
        <a href="#" data-goto="export">Part settings</a></div>`;
  }
  function bindSplit() {
    $$("[data-split]").forEach(b => b.onclick = attempt(async e => {
      e.preventDefault();
      const v = b.dataset.split;
      if (v === "on") await setSplit({ enabled: true }, "Split into parts. Each one saves to the exports folder when it's done.");
      else if (v === "dismiss") await setSplit({ dismissed: true }, "Keeping it as one file. You can still split it from the Export step.");
      else if (v === "off") await setSplit({ enabled: false }, "Back to one file.");
      else if (v === "redo") await setSplit({ enabled: true }, "Parts re-planned.");
    }));
    const auto = $("#splitAuto"); if (auto) auto.onchange = attempt(() => setSplit({ auto_export: auto.checked }, auto.checked ? "Each part will save itself when it's done." : "Export parts yourself from here."));
    const hrs = $("#splitHours"); if (hrs) hrs.onchange = attempt(() => setSplit({ hours: +hrs.value }, S.project.split.enabled ? "Parts re-planned for the new limit." : "Limit changed."));
  }
  async function setSplit(change, msg) {
    S.project.split = await api("PUT", `/api/projects/${S.pid}/split`, change);
    if (S.step === "generate") renderGenerate(openSet(), true); else if (S.step === "export") renderExport();
    toast(msg);
  }

  /* ---------- 4. generate ---------- */
  function renderGenerate(keepOpen, keepScroll) {
    const p = S.project, paras = allParas(p), w = worker();
    if (!paras.length) {
      $("#view-generate").innerHTML = `<div class="card"><div class="empty"><b>No script yet</b>Add a script in step 1, then come back here.</div></div>`;
      return;
    }
    const mine = w.current?.project === p.id, running = w.running && w.queue?.[0] === p.id;
    const done = paras.filter(x => x.dur).length, left = paras.filter(x => !x.dur);
    const doneWords = paras.filter(x => x.dur).reduce((a, x) => a + words(x.text), 0);
    const pace = p.audio ? doneWords / p.audio : 2.5;                   // words per second in this voice
    const leftSecs = left.reduce((a, x) => a + words(x.text), 0) / pace;
    const flagged = paras.filter(isFlagged).length;
    const firstOpen = p.sections.findIndex(s => s.paras.some(x => !x.dur));
    const open = keepOpen || new Set(firstOpen >= 0 ? [firstOpen] : []);
    if (mine) open.add(w.current.si);
    const counts = { all: paras.length, done, queued: left.length, flagged };
    const show = x => S.filter === "all" || (S.filter === "done" && x.dur && !isFlagged(x)) || (S.filter === "queued" && !x.dur) || (S.filter === "flagged" && isFlagged(x));
    const isCur = x => mine && w.current.si === x.si && w.current.pi === x.pi;
    const listTop = keepScroll ? $(".gen-list")?.scrollTop || 0 : 0;

    const sp = p.split || {}, partStart = new Map((sp.enabled ? sp.parts : []).map(x => [x.first, x]));
    $("#view-generate").innerHTML = `
      <div class="stack">
        ${splitOfferHTML(sp)}
        <div class="card card-pad">
          <div class="gen-bar">
            <div>
              <div class="row" style="margin-bottom:8px"><b style="font-size:15px">${done} of ${paras.length} paragraphs</b>
                <span class="muted small">${Math.round(done / paras.length * 100)}%</span>
                ${running && w.engine === "loading" ? '<span class="chip chip-busy">Loading the voice model…</span>' : ""}</div>
              <div class="progress"><div style="width:${done / paras.length * 100}%"></div></div>
              <div class="gen-stats">
                <span>Audio so far <b>${fmtDur(p.audio)}</b></span>
                <span>Time left <b>${left.length ? "~" + fmtDur(leftSecs * w.ratio) : "none"}</b></span>
                <span>Speed <b>${w.ratio}× slower than real time</b></span>
                <span>${running ? "Keeping the Mac awake" : "Pauses after the current paragraph"}</span>
              </div>
              <div class="small muted" style="margin-top:6px">Exports are saved in <b>${esc(shortPath(p.export_dir))}</b></div>
              ${w.error && !running ? `<div class="err" style="margin-top:12px">Stopped: ${esc(w.error)}</div>` : ""}
            </div>
            <div class="row" style="flex-wrap:nowrap">
              <div class="seg" id="qualitySeg" title="Fast is about 1.5× quicker, slightly rougher">
                <button data-q="best" class="${p.quality === "best" ? "on" : ""}">Best</button>
                <button data-q="fast" class="${p.quality === "fast" ? "on" : ""}">Fast</button></div>
              <button class="btn" data-showexports title="Open this project's exports folder">${I.file}Show in Finder</button>
              ${left.length ? `<button class="btn btn-primary" id="runBtn">${running ? I.pause + "Pause" : I.play + (done ? "Resume" : "Start")}</button>`
                : `<button class="btn" disabled>${I.check}Done</button>`}
            </div>
          </div>
          ${partsStripHTML(sp)}
          ${w.running && !mine && w.current ? `<p class="small muted" style="margin:12px 0 0">Busy with ${esc(titleOf(w.current.project))}. Starting this one puts it first.</p>` : ""}
        </div>
        <div class="card">
          <div class="card-head">
            <div class="filters" id="filters">${[["all", "All"], ["done", "Done"], ["queued", "To do"], ["flagged", "Check these"]].map(([k, l]) =>
              `<button data-f="${k}" class="${S.filter === k ? "on" : ""}">${l} · ${counts[k]}</button>`).join("")}</div>
            <span class="small muted">Click a line to read it in full. "Check these" are lines whose pace looks off.</span>
          </div>
          <div class="gen-list">${p.sections.map((s, si) => {
            const vis = s.paras.filter(show); if (!vis.length) return "";
            const sd = s.paras.filter(x => x.dur).length, pt = partStart.get(si);
            return `${pt ? `<div class="part-head"><b>Part ${pt.n} of ${sp.parts.length}</b><span>${pt.complete ? (pt.exported ? "done · saved" : "done") : `${pt.done}/${pt.total} · ~${fmtDur(pt.gen_left)} left`}</span></div>` : ""}<div class="sec ${open.has(si) || S.filter !== "all" ? "open" : ""}" data-si="${si}">
              <div class="sec-head">${I.chev}<span class="sec-title">${esc(s.title.toLowerCase())}</span>
                <span class="sec-count">${sd}/${s.paras.length}</span><div class="mini"><div style="width:${sd / s.paras.length * 100}%"></div></div></div>
              <div class="paras">${vis.map(x => {
                const st = isCur(x) ? "busy" : !x.dur ? "queued" : isFlagged(x) ? "warn" : "done";
                return `<div class="para ${st === "queued" ? "queued" : ""}"><span class="dot dot-${st}"></span>
                  <div class="para-text">${esc(x.text)}</div>
                  <div class="para-side">
                    ${st === "warn" ? '<span class="flag">pace</span>' : ""}${st === "busy" ? '<span class="flag" style="color:var(--busy);background:var(--busy-soft)">now</span>' : ""}
                    <span class="para-dur">${x.dur ? x.dur.toFixed(1) + "s" : ""}</span>
                    <button class="icon-btn" ${x.clip ? `data-play="${x.key}" data-src="${x.clip}"` : "disabled"} title="Play">${I.play}</button>
                    <button class="icon-btn" title="Redo this line" data-regen="${x.key}" ${x.dur ? "" : "disabled"}>${I.redo}</button>
                  </div></div>`;
              }).join("")}</div></div>`;
          }).join("")}</div>
        </div>
      </div>`;

    $$("#filters button").forEach(b => b.onclick = () => { S.filter = b.dataset.f; renderGenerate(); });
    bindSplit();
    $$("#qualitySeg button").forEach(b => b.onclick = attempt(async () => {
      await api("PUT", `/api/projects/${p.id}/settings`, { quality: b.dataset.q }); p.quality = b.dataset.q; renderGenerate(openSet(), true);
    }));
    $$(".sec-head").forEach(h => h.onclick = () => h.parentElement.classList.toggle("open"));
    $$(".para-text").forEach(t => t.onclick = () => t.parentElement.classList.toggle("expanded"));
    $$("[data-regen]").forEach(b => b.onclick = attempt(async () => {
      await api("POST", `/api/projects/${p.id}/regen`, { key: b.dataset.regen });
      await reloadProject(true); toast(running ? "Queued. It'll be redone soon." : "Marked to redo. Press Resume to generate it.");
    }));
    $$("[data-play]").forEach(b => b.onclick = () => play(b.dataset.src, b.dataset.play));
    const run = $("#runBtn");
    if (run) run.onclick = attempt(async () => {
      if (running) { await api("POST", "/api/generate/pause"); toast("Pausing after the current paragraph."); }
      else { await api("POST", `/api/generate/${p.id}/start`); toast(done ? "Resuming." : "Starting. The first line takes longer while the model loads."); }
      await refreshOverview(); renderGenerate(openSet(), true); poll();
    });
    const list = $(".gen-list");
    if (list) {
      list.scrollTop = listTop;
      const el = $(".dot-busy", list)?.closest(".para");
      if (el && keepScroll && (el.offsetTop < list.scrollTop || el.offsetTop + el.offsetHeight > list.scrollTop + list.clientHeight))
        list.scrollTop = el.offsetTop - list.clientHeight / 2;
    }
    refreshPlay();
  }
  const openSet = () => new Set($$(".sec.open").map(e => +e.dataset.si));

  /* ---------- 5. export ---------- */
  function renderExport() {
    const p = S.project, paras = allParas(p), complete = paras.length && paras.every(x => x.dur), o = S.exportOpts;
    if (!paras.length) { $("#view-export").innerHTML = `<div class="card"><div class="empty"><b>Nothing to export yet</b>Generate some audio first.</div></div>`; return; }
    const secDur = p.sections.map(s => s.paras.reduce((a, x) => a + (x.dur || words(x.text) / 2.5), 0)), total = secDur.reduce((a, b) => a + b, 0) || 1;
    const lastFull = p.sections.findIndex(s => s.paras.some(x => !x.dur));
    const partialSecs = (lastFull < 0 ? p.sections : p.sections.slice(0, lastFull)).reduce((a, s) => a + s.paras.reduce((b, x) => b + (x.dur || 0), 0), 0);
    const name = o.name || p.title.replace(" · ", " - ");
    const sp = p.split || {}, starts = new Set((sp.enabled ? sp.parts : []).slice(1).map(x => x.first));
    $("#view-export").innerHTML = `
      <div class="grid-side">
        <div class="stack">
          <div class="card card-pad">
            <div class="row" style="margin-bottom:10px"><div class="card-title">Timeline</div><span class="spacer"></span>
              <span class="small muted">${p.sections.length} sections · grey isn't generated yet</span></div>
            <div class="timeline">${p.sections.map((s, i) => `<div class="${s.paras.some(x => !x.dur) ? "missing" : ""} ${starts.has(i) ? "part-start" : ""}" style="flex:${secDur[i] / total}" title="${esc(s.title)}"></div>`).join("")}</div>
            ${sp.enabled ? `<div class="small muted" style="margin-top:8px">Marks show where each of the ${sp.parts.length} parts begins.</div>` : ""}
          </div>
          <div class="card card-pad">
            <div class="card-title" style="margin-bottom:4px">Export</div>
            <div class="export-row"><div class="file-ic">${I.file}</div>
              <div style="flex:1"><div style="font-weight:600">Full audio</div><div class="small muted">${complete ? fmtDur(p.audio) + " plus pauses · every paragraph" : "Available once every paragraph is generated"}</div></div>
              <button class="btn btn-primary" id="expFull" ${complete ? "" : "disabled"}>Export ${o.format.toUpperCase()}</button></div>
            <div class="export-row"><div class="file-ic">${I.file}</div>
              <div style="flex:1"><div style="font-weight:600">Finished sections only</div><div class="small muted">${fmtDur(partialSecs)} · stops at the end of the last complete section</div></div>
              <button class="btn" id="expPart" ${partialSecs ? "" : "disabled"}>Export partial</button></div>
          </div>
          ${partsCardHTML(sp)}
          <div class="card card-pad">
            <div class="row" style="margin-bottom:4px"><div class="card-title">Exported from F5 Studio</div><span class="spacer"></span>
              <button class="btn" data-showexports>${I.file}Show in Finder</button></div>
            ${p.exports.length ? p.exports.map((e, i) => `<div class="export-row"><div class="file-ic">${I.file}</div>
              <div style="flex:1;min-width:0"><div style="font-weight:600;overflow-wrap:anywhere">${esc(e.name)}</div>
              <div class="small muted">${fmtDur(e.secs)} · ${e.part ? `part ${e.part}` : e.partial ? `first ${e.sections} sections` : "complete"} · ${new Date(e.when * 1000).toLocaleString()}</div></div>
              <button class="btn btn-ghost" data-reveal="${i}">Show in Finder</button></div>`).join("")
              : `<p class="small muted" style="margin:8px 0 0">Nothing yet. Files go to ${esc(shortPath(p.export_dir))}.</p>`}
          </div>
        </div>
        <div class="card card-pad">
          <div class="card-title" style="margin-bottom:14px">Pacing and format</div>
          ${[["para", "Between paragraphs"], ["heading", "After a heading"], ["section", "Between sections"]].map(([k, l]) => `
            <div class="range-row"><span class="small">${l}</span><span class="val" id="gv-${k}">${(+p.pacing[k]).toFixed(2)}s</span>
            <input type="range" min="0" max="3" step="0.05" value="${p.pacing[k]}" data-gap="${k}" style="grid-column:1/-1"></div>`).join("")}
          <label class="label" style="margin-top:6px">Format</label>
          <div class="seg" id="fmtSeg"><button data-fmt="mp3" class="${o.format === "mp3" ? "on" : ""}">MP3</button><button data-fmt="wav" class="${o.format === "wav" ? "on" : ""}">WAV</button></div>
          ${o.format === "mp3" ? `<label class="label" style="margin-top:14px">MP3 quality</label>
          <select id="qSel">${[["high", "High (about 190 kbps)"], ["standard", "Standard (about 130 kbps)"], ["small", "Small (about 96 kbps)"]].map(([k, l]) => `<option value="${k}" ${o.quality === k ? "selected" : ""}>${l}</option>`).join("")}</select>` : ""}
          <label class="label" style="margin-top:14px">File name</label>
          <input type="text" id="expName" value="${esc(name)}">
          <p class="small muted" style="margin:10px 0 0">Saved in ${esc(shortPath(p.export_dir))}. A file with the same name is replaced.</p>
        </div>
      </div>`;
    const savePacing = debounce(attempt(() => api("PUT", `/api/projects/${p.id}/settings`, { pacing: p.pacing })), 400);
    $$("[data-gap]").forEach(r => r.oninput = () => { p.pacing[r.dataset.gap] = +r.value; $("#gv-" + r.dataset.gap).textContent = (+r.value).toFixed(2) + "s"; savePacing(); });
    $$("#fmtSeg button").forEach(b => b.onclick = () => { o.format = b.dataset.fmt; renderExport(); });
    const q = $("#qSel"); if (q) q.onchange = () => o.quality = q.value;
    $("#expName").oninput = e => o.name = e.target.value;
    const ex = partial => attempt(async () => {
      toast("Exporting…", 20000);
      const r = await api("POST", `/api/projects/${p.id}/export`, { partial, format: o.format, quality: o.quality, name: $("#expName").value });
      await reloadProject(); toast(`Saved ${r.name} (${fmtDur(r.secs)}) in the exports folder.`, 5000);
    });
    $("#expFull").onclick = ex(false);
    $("#expPart").onclick = ex(true);
    $$("[data-reveal]").forEach(b => b.onclick = attempt(() => api("POST", "/api/reveal", { path: p.exports[+b.dataset.reveal].path })));
    $$("[data-exppart]").forEach(b => b.onclick = attempt(async () => {
      toast("Exporting…", 20000);
      const r = await api("POST", `/api/projects/${p.id}/export`, { part: +b.dataset.exppart, format: o.format, quality: o.quality });
      await reloadProject(); toast(`Saved ${r.name} (${fmtDur(r.secs)}) in the exports folder.`, 5000);
    }));
    bindSplit();
  }
  function partsCardHTML(sp) {
    const hours = `<select id="splitHours" style="width:auto">${[3, 4, 5, 6, 8, 12].map(h => `<option value="${h}" ${+sp.hours === h ? "selected" : ""}>${h} hours</option>`).join("")}</select>`;
    if (!sp.enabled) return `<div class="card card-pad">
      <div class="row"><div class="card-title">Parts</div><span class="spacer"></span><span class="small muted">Optional</span></div>
      <p class="small muted" style="margin:6px 0 12px">Generating everything takes about <b>${fmtDur(sp.total_gen)}</b>.
        ${sp.over ? `That's over the limit, so it would split into <b>${sp.suggested} parts</b>.` : "That's within the limit, so it stays one file unless you split it."}
        Each part is whole sections, saved to the exports folder as soon as it's done.</p>
      <div class="row"><span class="small">Up to</span>${hours}<span class="small">of generation per part</span><span class="spacer"></span>
        <button class="btn ${sp.over ? "btn-primary" : ""}" data-split="on">Split into parts</button></div></div>`;
    return `<div class="card card-pad">
      <div class="row"><div class="card-title">Parts</div><span class="spacer"></span>
        <button class="btn btn-ghost" data-split="redo" title="Plan the parts again from the current script and speed">Re-plan</button>
        <button class="btn btn-ghost" data-split="off">Don't split</button></div>
      ${sp.parts.map(x => `<div class="export-row"><div class="file-ic">${I.file}</div>
        <div style="flex:1;min-width:0"><div style="font-weight:600">Part ${x.n} of ${sp.parts.length}</div>
          <div class="small muted" style="overflow-wrap:anywhere">${esc(x.first_title.toLowerCase())} → ${esc(x.last_title.toLowerCase())}</div>
          <div class="small muted">${x.complete ? `${fmtDur(x.audio)} of audio${x.exported ? ` · saved as ${esc(x.file || "")}` : ""}` : `${x.done}/${x.total} paragraphs · about ${fmtDur(x.gen_left)} left`}</div></div>
        <button class="btn ${x.complete && !x.exported ? "btn-primary" : ""}" data-exppart="${x.n}" ${x.complete ? "" : "disabled"}>${x.exported ? "Export again" : "Export"}</button></div>`).join("")}
      <div class="row" style="margin-top:12px"><span class="small">Up to</span>${hours}<span class="small">per part</span></div>
      <label class="toggle"><input type="checkbox" id="splitAuto" ${sp.auto_export ? "checked" : ""}><span class="sw"></span><span><span class="t">Save each part to the exports folder when it finishes</span><br>
        <span class="d">Uses the format and quality set on the right.</span></span></label></div>`;
  }

  /* ---------- the Cogitator (Scriptorium scripts from ~/study) ---------- */
  const COG_TAG = { writing: "writing…", ready: "new", incomplete: "incomplete" };
  function cogStatus(it) {
    if (it.state === "writing") {
      const j = S.cog.job;
      return `<span class="tag tag-writing">writing${j?.total ? ` ${j.done}/${j.total}` : "…"}</span>`;
    }
    if (it.project) return it.changed ? '<span class="tag tag-updated">updated · re-import</span>' : '<span class="tag tag-imported">imported</span>';
    return `<span class="tag tag-${it.state === "ready" ? "new" : "incomplete"}">${COG_TAG[it.state]}</span>`;
  }
  function renderCog() {
    const c = S.cog, show = c?.available && c.items.length;
    $("#cogLabel").hidden = $("#cogList").hidden = !show;
    if (!show) return;
    $("#cogList").innerHTML = c.items.map((it, i) => `
      <button class="proj-item cog-item ${it.project && it.project === S.pid ? "active" : ""}" data-cog="${i}" title="${esc(it.name)}">
        <span class="cog-ic">${esc((it.voice || "?")[0])}</span>
        <div><div class="name">${esc(it.subject)} · ${esc(it.label)}</div>
        <div class="sub">${esc(it.voice)} · ${cogStatus(it)}</div></div>
      </button>`).join("");
    $$("[data-cog]").forEach(b => b.onclick = () => cogClick(c.items[+b.dataset.cog]));
  }
  async function loadCog() {
    const before = S.cog?.items.filter(i => i.project).length;
    S.cog = await api("GET", "/api/cogitator").catch(() => null);
    renderCog();
    const pk = $("#cogPicker");
    if (pk && S.step === "script" && S.project && !S.scriptDirty && !S.sourceDirty) { pk.innerHTML = cogPickerHTML(S.project); bindCogPicker(); }
    if (S.cog && before !== undefined && S.cog.items.filter(i => i.project).length !== before) await refreshOverview();
  }
  const cogClick = attempt(async it => {
    if (it.project && !it.changed) return selectProject(it.project);
    if (it.state === "writing") return toast("The Cogitator is still writing this one. It'll be ready to import when it's done.");
    const vs = S.overview.voices;
    if (!vs.length) { toast("Add a voice first."); return go("voice"); }
    const proj = it.project && S.overview.projects.find(p => p.id === it.project);
    const pick = proj?.voice || S.cog.settings.voice_map[it.voice] || vs[0].id;
    const r = await modal(it.project ? "Update from the Cogitator" : "Import from the Cogitator", `
      <div><b>${esc(it.subject)} · ${esc(it.label)}</b><div class="small muted">${esc(it.voice)} · ${it.words.toLocaleString()} words · about ${fmtDur(it.words / 150 * 60)} of audio</div></div>
      ${it.state === "incomplete" ? '<div class="err">This script looks unfinished (it has no sign-off). The Scriptorium may have stopped partway.</div>' : ""}
      ${it.project ? '<div class="small muted">The script changed since you imported it. Updating keeps the audio of every paragraph that stayed the same.</div>' : ""}
      <div><label class="label">Voice</label><select name="voice">${vs.map(v => `<option value="${v.id}" ${v.id === pick ? "selected" : ""}>${esc(v.name)}</option>`).join("")}</select></div>
      <label class="toggle"><input type="checkbox" name="generate"><span class="sw"></span><span><span class="t">Start generating right away</span><br>
        <span class="d">About ${fmtDur(it.words / 150 * 60 * (worker().ratio || 6.5))} on this Mac.</span></span></label>`, it.project ? "Update" : "Import");
    if (!r) return;
    const p = await api("POST", "/api/cogitator/import", { name: it.name, voice: r.voice, generate: r.generate });
    await loadCog(); await loadOverview(); await selectProject(p.id); go(r.generate ? "generate" : "script");
    if (r.generate) poll();
    toast(r.generate ? "Imported. Generating now." : "Imported. Check the script and pronunciations, then generate.");
  });
  $("#cogSettings").onclick = attempt(async () => {
    const s = S.cog.settings, vs = S.overview.voices;
    const personas = [...new Set([...S.cog.items.map(i => i.voice).filter(Boolean), ...Object.keys(s.voice_map)])];
    const r = await modal("The Cogitator", `
      <div class="small muted">Scripts come from <b>${esc(S.cog.folder.replace(/^\/Users\/[^/]+/, "~"))}</b>, written by the Scriptorium. F5 Studio only reads that folder.</div>
      <label class="toggle"><input type="checkbox" name="auto_import" ${s.auto_import ? "checked" : ""}><span class="sw"></span><span><span class="t">Import finished scripts automatically</span><br>
        <span class="d">New scripts become projects, and updated ones refresh their project.</span></span></label>
      <label class="toggle"><input type="checkbox" name="auto_generate" ${s.auto_generate ? "checked" : ""}><span class="sw"></span><span><span class="t">Then start generating</span><br>
        <span class="d">Queued behind whatever is already generating.</span></span></label>
      ${personas.length ? `<div><label class="label">Which F5 voice reads each character</label><div class="stack" style="gap:8px">
        ${personas.map(n => `<div class="map-row"><span>${esc(n)}</span><select name="map:${esc(n)}">
          <option value="">First voice (${esc(vs[0]?.name || "none")})</option>
          ${vs.map(v => `<option value="${v.id}" ${s.voice_map[n] === v.id ? "selected" : ""}>${esc(v.name)}</option>`).join("")}</select></div>`).join("")}
      </div></div>` : ""}`, "Save");
    if (!r) return;
    const voice_map = {};
    Object.entries(r).forEach(([k, v]) => { if (k.startsWith("map:") && v) voice_map[k.slice(4)] = v; });
    S.cog.settings = await api("PUT", "/api/cogitator/settings", { auto_import: r.auto_import, auto_generate: r.auto_generate, voice_map });
    toast(r.auto_import ? "Saved. Finished scripts will import on their own." : "Saved.");
  });

  /* ---------- routing, polling ---------- */
  const views = { script: renderScript, pron: () => renderPron(), voice: renderVoice, generate: () => renderGenerate(), export: renderExport };
  function go(step) {
    if (S.step === "script" && step !== "script" && (S.scriptDirty || S.sourceDirty) && !confirm("You have unsaved text. Leave without saving?")) return;
    if (S.step === "script") S.scriptDirty = S.sourceDirty = false;
    S.step = step; save("step", step);
    $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + step));
    if (!S.project && step !== "pron" && step !== "voice") {
      $("#view-" + step).innerHTML = `<div class="card"><div class="empty"><b>No project selected</b>Press <b>New project</b> to start one.</div></div>`;
    } else views[step]();
    renderHeader();
  }
  async function refreshOverview() { await loadOverview(); renderSidebar(); renderHeader(); }
  async function reloadProject(keep) {
    await loadProject(); renderSidebar(); renderHeader();
    if (S.step === "generate") renderGenerate(keep ? openSet() : undefined, keep);
    else if (S.step === "export") renderExport();
  }
  async function reloadAll() { await loadOverview(); await loadProject(); renderSidebar(); go(S.step); }
  async function selectProject(pid) {
    if (S.step === "script" && (S.scriptDirty || S.sourceDirty) && !confirm("You have unsaved text. Leave without saving?")) return;
    player.pause(); S.playing = null; S.pid = pid; save("pid", pid);
    await loadProject(); renderSidebar(); go(S.step);
  }

  let pollTimer = null, lastDone = null, lastCur = null;
  function poll() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      try {
        const st = await api("GET", "/api/status");
        const was = S.overview.worker.running;
        S.overview.worker = st.worker;
        const le = st.worker.last_export;
        if (le && le.when !== S.lastExportWhen) {
          if (S.lastExportWhen !== undefined) toast(`Part ${le.part} is done and saved: ${le.name}`, 7000);
          S.lastExportWhen = le.when;
        }
        if (st.project) { const i = S.overview.projects.findIndex(p => p.id === st.project.id); if (i >= 0) S.overview.projects[i] = st.project; }
        renderSidebar(); renderHeader();
        const cur = st.worker.current ? `${st.worker.current.project}:${st.worker.current.si}:${st.worker.current.pi}` : null;
        const busy = st.worker.running;
        if (S.project && (cur !== lastCur || (st.project && st.project.id === S.pid && st.project.done !== lastDone) || (was && !busy))) {
          lastCur = cur; lastDone = st.project?.done;
          if (S.step === "generate" || S.step === "export") await reloadProject(true);
          if (was && !busy) await refreshOverview();
        }
        if (busy) poll();
      } catch { poll(); }
    }, 1500);
  }

  document.addEventListener("click", e => {
    if (e.target.closest("[data-showexports]")) { attempt(() => api("POST", `/api/projects/${S.pid}/exports/reveal`))(); return; }
    const pi = e.target.closest("[data-pid]"); if (pi) { selectProject(pi.dataset.pid); return; }
    const st = e.target.closest("[data-step]"); if (st) { go(st.dataset.step); return; }
    const g = e.target.closest("[data-goto]"); if (g) { go(g.dataset.goto); return; }
  });
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key === "s" && S.step === "script") { e.preventDefault(); if (S.scriptDirty) attempt(saveScript)(); else if (S.sourceDirty) attempt(saveSource)(); }
  });
  $("#newProject").onclick = attempt(async () => {
    const vs = S.overview.voices;
    if (!vs.length) { toast("Add a voice first."); go("voice"); return; }
    const r = await modal("New project", `
      <div><label class="label">Name</label><input type="text" name="title" required placeholder="e.g. Evidence · Part 1"></div>
      <div><label class="label">Voice</label><select name="voice">${vs.map(v => `<option value="${v.id}">${esc(v.name)}</option>`).join("")}</select></div>
      <div><label class="label">Persona (optional)</label><input type="text" name="persona" placeholder="e.g. Shadowheart (dom)"></div>`, "Create");
    if (!r || !r.title.trim()) return;
    const p = await api("POST", "/api/projects", r);
    await loadOverview(); await selectProject(p.id); go("script");
    toast("Project created. Paste the script, then press Save.");
  });
  addEventListener("resize", () => { if (S.step === "voice") { const v = voiceById(S.project?.voice) || S.overview.voices[0]; v && drawWave(v); } });
  addEventListener("beforeunload", e => { if (S.scriptDirty || S.sourceDirty) { e.preventDefault(); e.returnValue = ""; } });

  (async () => {
    try { await loadOverview(); await loadProject(); }
    catch (e) { document.body.innerHTML = `<div class="empty"><b>Can't reach the F5 Studio server</b>${esc(e.message)}</div>`; return; }
    renderSidebar(); go(S.step);
    S.lastExportWhen = worker().last_export?.when ?? null;
    if (worker().running) poll();
    loadCog(); setInterval(loadCog, 10000);
  })();
})();
