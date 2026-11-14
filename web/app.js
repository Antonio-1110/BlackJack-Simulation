// Page logic: editor, settings, saving and sharing, the Python worker, and
// rendering results.
(() => {
  const $ = (id) => document.getElementById(id);
  const CODE_KEY = "bj-lab-code";
  const SETTINGS_KEY = "bj-lab-settings";
  const SAVED_KEY = "bj-lab-saved";
  const SHARE_PREFIX = "#lab=";

  // Browser storage can be blocked (private windows, strict settings), so
  // every access is wrapped and the page still works without it.
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); return true; } catch (_) { return false; } },
  };
  const readJSON = (key, fallback) => {
    try { return JSON.parse(store.get(key)) ?? fallback; } catch (_) { return fallback; }
  };

  let toastTimer = 0;
  function toast(text) {
    $("toast").textContent = text;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $("toast").textContent = ""; }, 5000);
  }

  // ------------------------------------------------------------ editor
  const examples = window.EXAMPLES;
  const picker = $("example");
  let savedList = readJSON(SAVED_KEY, []).filter((s) => s && typeof s.name === "string" && typeof s.code === "string");

  const storedCode = store.get(CODE_KEY);
  const editor = CodeMirror($("editor"), {
    value: storedCode || examples[0].code,
    mode: "python",
    lineNumbers: true,
    indentUnit: 4,
    tabSize: 4,
    viewportMargin: Infinity,
    extraKeys: {
      Tab: (cm) => cm.somethingSelected() ? cm.indentSelection("add") : cm.replaceSelection("    "),
      "Shift-Tab": (cm) => cm.indentSelection("subtract"),
      "Ctrl-Enter": () => startRun(),
      "Cmd-Enter": () => startRun(),
    },
  });
  // The code as it was last loaded from an example, a saved strategy, a file
  // or a link. Replacing code that still matches it needs no confirmation.
  let loadedCode = storedCode ? null : examples[0].code;
  let loadedName = storedCode ? null : examples[0].name;

  editor.on("change", () => {
    store.set(CODE_KEY, editor.getValue());
    clearErrorLine();
  });

  function fillPicker(selected) {
    picker.innerHTML = "";
    const placeholder = new Option("Your current code", "");
    placeholder.hidden = true;
    picker.add(placeholder);
    const exGroup = document.createElement("optgroup");
    exGroup.label = "Examples";
    examples.forEach((ex, i) => exGroup.appendChild(new Option(ex.name, `ex:${i}`)));
    picker.appendChild(exGroup);
    if (savedList.length) {
      const savedGroup = document.createElement("optgroup");
      savedGroup.label = "Saved in this browser";
      savedList.forEach((s, i) => savedGroup.appendChild(new Option(s.name, `saved:${i}`)));
      picker.appendChild(savedGroup);
    }
    picker.value = selected || "";
    $("delete-saved").hidden = !picker.value.startsWith("saved:");
  }

  function isDirty() {
    const current = editor.getValue();
    return current.trim() !== "" && current !== loadedCode && !examples.some((e) => e.code === current);
  }

  function loadCode(code, name, pickerValue) {
    editor.setValue(code);
    loadedCode = code;
    loadedName = name;
    fillPicker(pickerValue);
  }

  fillPicker(storedCode ? (examples.findIndex((e) => e.code === storedCode) >= 0
    ? `ex:${examples.findIndex((e) => e.code === storedCode)}` : "") : "ex:0");

  picker.addEventListener("change", () => {
    const [kind, idx] = picker.value.split(":");
    const item = kind === "ex" ? examples[Number(idx)] : savedList[Number(idx)];
    if (!item) return;
    if (isDirty() && !confirm(`Replace your code with "${item.name}"? Use "Save as…" first to keep it.`)) {
      fillPicker("");
      return;
    }
    loadCode(item.code, item.name, picker.value);
    if (kind === "saved" && item.settings) applySettings(item.settings);
    if (kind === "saved") toast(`Loaded "${item.name}" with its table and simulation settings.`);
  });

  function persistSaved() {
    if (!store.set(SAVED_KEY, JSON.stringify(savedList))) {
      toast("Your browser is blocking storage, so this can't be kept. Try Download .py instead.");
      return false;
    }
    return true;
  }

  $("save-as").addEventListener("click", () => {
    const suggestion = loadedName && savedList.some((s) => s.name === loadedName) ? loadedName : "";
    const name = (prompt("Name this strategy (saved with your current settings, in this browser only):", suggestion) || "").trim();
    if (!name) return;
    const entry = { name, code: editor.getValue(), settings: readSettings(), savedAt: new Date().toISOString() };
    let idx = savedList.findIndex((s) => s.name === name);
    if (idx >= 0) {
      if (!confirm(`Replace the saved strategy "${name}"?`)) return;
      savedList[idx] = entry;
    } else {
      savedList.push(entry);
      idx = savedList.length - 1;
    }
    if (!persistSaved()) return;
    loadedCode = entry.code;
    loadedName = name;
    fillPicker(`saved:${idx}`);
    toast(`Saved "${name}".`);
  });

  $("delete-saved").addEventListener("click", () => {
    const idx = Number(picker.value.split(":")[1]);
    const item = savedList[idx];
    if (!item || !confirm(`Delete the saved strategy "${item.name}"? Your code in the editor stays.`)) return;
    savedList.splice(idx, 1);
    persistSaved();
    fillPicker("");
    toast(`Deleted "${item.name}".`);
  });

  // A file name from the strategy's name, e.g. "Hi-Lo spread" -> hi-lo-spread.py
  const fileName = (ext) => `${(loadedName || "my-strategy").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "strategy"}.${ext}`;

  function download(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  $("download-py").addEventListener("click", () => download(fileName("py"), editor.getValue(), "text/x-python"));

  $("open-py").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 500_000) { toast("That file is too big for a strategy (over 500 KB)."); return; }
    const text = await file.text();
    if (isDirty() && !confirm(`Replace your code with ${file.name}?`)) return;
    loadCode(text, file.name.replace(/\.py$/i, ""), "");
    toast(`Opened ${file.name}.`);
  });

  // ------------------------------------------------------- share links
  // The code and settings, deflated and base64url-encoded into the URL hash.
  // Nothing is uploaded: the link itself carries the strategy.
  const b64url = (bytes) => {
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };
  const unb64url = (text) => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  const pipe = async (bytes, stream) => new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(stream)).arrayBuffer());

  async function encodeShare(payload) {
    const json = new TextEncoder().encode(JSON.stringify(payload));
    return b64url(await pipe(json, new CompressionStream("deflate-raw")));
  }
  async function decodeShare(text) {
    const json = await pipe(unb64url(text), new DecompressionStream("deflate-raw"));
    return JSON.parse(new TextDecoder().decode(json));
  }

  $("share").addEventListener("click", async () => {
    let url;
    try {
      const token = await encodeShare({ v: 1, name: loadedName || undefined, code: editor.getValue(), settings: readSettings() });
      url = `${location.origin}${location.pathname}${SHARE_PREFIX}${token}`;
    } catch (err) {
      toast("This browser can't make share links (it's missing CompressionStream).");
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      toast("Link copied. It holds your code and settings, so anyone with it can open the same setup.");
    } catch (_) {
      history.replaceState(null, "", url);
      toast("Couldn't reach the clipboard, so the link is in the address bar. Copy it from there.");
    }
  });

  async function openSharedLink() {
    if (!location.hash.startsWith(SHARE_PREFIX)) return;
    const token = location.hash.slice(SHARE_PREFIX.length);
    history.replaceState(null, "", location.pathname + location.search);
    let shared;
    try {
      shared = await decodeShare(token);
      if (typeof shared.code !== "string") throw new Error("no code");
    } catch (_) {
      toast("That share link looks broken or cut off, so your own code is still here.");
      return;
    }
    // Keep the visitor's own work: back it up before the link replaces it.
    const backup = isDirty() && editor.getValue() !== shared.code;
    if (backup) {
      const name = `My code before opening a link (${new Date().toLocaleString()})`;
      savedList.push({ name, code: editor.getValue(), settings: readSettings(), savedAt: new Date().toISOString() });
      persistSaved();
    }
    const name = typeof shared.name === "string" ? shared.name : "Shared strategy";
    loadCode(shared.code, name, "");
    if (shared.settings) applySettings(shared.settings);
    toast(`Opened "${name}" from a shared link.` + (backup ? " Your own code is under Saved in this browser." : ""));
  }

  // ---------------------------------------------------------- settings
  const outputs = {
    players: (v) => (v === "1" ? "just you" : `you + ${v - 1}`),
    num_decks: (v) => v,
    penetration: (v) => `${Math.round(v * 100)}%`,
  };
  function refreshOutputs() {
    for (const [id, fmt] of Object.entries(outputs)) $(`${id}-out`).textContent = fmt($(id).value);
  }
  for (const id of Object.keys(outputs)) $(id).addEventListener("input", refreshOutputs);
  refreshOutputs();

  const num = (id) => Number($(id).value);
  const checked = (id) => $(id).checked;

  // Form fields by settings key. "players" is stored as other_players.
  const RULE_FIELDS = ["num_decks", "penetration", "insurance", "blackjack_payout", "double_on", "surrender",
    "double_after_split", "resplit_aces", "dealer_peeks", "table_min", "table_max"];
  const SESSION_FIELDS = ["rounds", "sessions", "bankroll", "seed", "stop_loss", "win_target"];

  function readSettings() {
    return {
      rules: {
        num_decks: num("num_decks"),
        penetration: num("penetration"),
        dealer_hits_soft_17: document.querySelector("input[name=dealer_hits_soft_17]:checked").value === "true",
        insurance: checked("insurance"),
        blackjack_payout: num("blackjack_payout"),
        double_on: $("double_on").value,
        surrender: $("surrender").value,
        double_after_split: checked("double_after_split"),
        resplit_aces: checked("resplit_aces"),
        dealer_peeks: checked("dealer_peeks"),
        table_min: num("table_min"),
        table_max: num("table_max"),
      },
      session: {
        rounds: num("rounds"),
        sessions: num("sessions"),
        bankroll: num("bankroll"),
        seed: num("seed"),
        stop_loss: num("stop_loss") || 0,
        win_target: num("win_target") || 0,
        other_players: num("players") - 1,
      },
      compare: checked("compare"),
    };
  }

  // Puts settings (from storage, a saved strategy or a link) back in the
  // form. Unknown keys and values the form can't show are skipped.
  function applySettings(s) {
    if (!s || typeof s !== "object") return;
    const setField = (id, value) => {
      const el = $(id);
      if (!el || value == null) return;
      if (el.type === "checkbox") el.checked = Boolean(value);
      else if (el.tagName === "SELECT") {
        if ([...el.options].some((o) => o.value === String(value))) el.value = String(value);
      } else if (Number.isFinite(Number(value))) el.value = String(value);
    };
    const rules = s.rules || {};
    const session = s.session || {};
    RULE_FIELDS.forEach((k) => setField(k, rules[k]));
    SESSION_FIELDS.forEach((k) => setField(k, session[k]));
    if (typeof rules.dealer_hits_soft_17 === "boolean") {
      document.querySelector(`input[name=dealer_hits_soft_17][value="${rules.dealer_hits_soft_17}"]`).checked = true;
    }
    if (Number.isFinite(session.other_players)) setField("players", session.other_players + 1);
    if (typeof s.compare === "boolean") $("compare").checked = s.compare;
    refreshOutputs();
    saveSettings();
  }

  const DEFAULT_SETTINGS = readSettings();
  const saveSettings = () => store.set(SETTINGS_KEY, JSON.stringify(readSettings()));
  applySettings(readJSON(SETTINGS_KEY, null));
  $("settings").addEventListener("input", saveSettings);
  $("settings").addEventListener("change", saveSettings);
  $("reset-settings").addEventListener("click", () => {
    applySettings(DEFAULT_SETTINGS);
    $("progress-text").textContent = "Settings are back to the defaults.";
  });

  openSharedLink();
  // Pasting a link into a tab that already has the Lab open only changes the hash.
  addEventListener("hashchange", openSharedLink);

  // ------------------------------------------------------------ worker
  let worker = null;
  let running = false;

  function setEngine(text, state) {
    const el = $("engine-status");
    el.textContent = text;
    el.dataset.state = state;
  }

  function startWorker() {
    setEngine("Loading Python…", "loading");
    $("run").disabled = true;
    worker = new Worker("worker.js");
    worker.onmessage = (e) => handle(e.data);
    worker.onerror = (e) => {
      setEngine("Python failed to load", "error");
      showError(`The Python engine failed to start: ${e.message || "unknown error"}`);
    };
  }

  function handle(msg) {
    if (msg.type === "status") {
      setEngine(msg.text, "loading");
    } else if (msg.type === "ready") {
      setEngine("Python ready", "ready");
      $("run").disabled = running;
    } else if (msg.type === "boot-error") {
      setEngine("Python failed to load", "error");
      showError(`The Python engine failed to start:\n${msg.error}`);
    } else if (msg.type === "progress") {
      const pct = (100 * msg.done) / msg.total;
      $("progress-bar").style.width = `${pct}%`;
      $("progress-text").textContent = `Played ${msg.done} of ${msg.total} sessions…`;
    } else if (msg.type === "done") {
      finishRun();
      if (msg.ok) render(msg.result);
      else showError(msg.error);
    }
  }

  function startRun() {
    if (running || $("run").disabled) return;
    running = true;
    $("run").disabled = true;
    $("stop").hidden = false;
    $("progress").hidden = false;
    $("progress-bar").style.width = "0%";
    $("progress-text").textContent = "Starting…";
    runStarted = performance.now();
    clearErrorLine();
    lastRun = { code: editor.getValue(), settings: readSettings() };
    worker.postMessage(lastRun);
  }

  let runStarted = 0;
  function finishRun() {
    running = false;
    $("run").disabled = false;
    $("stop").hidden = true;
    $("progress").hidden = true;
    const secs = ((performance.now() - runStarted) / 1000).toFixed(1);
    $("progress-text").textContent = `Finished in ${secs}s.`;
  }

  $("settings").addEventListener("submit", (e) => { e.preventDefault(); startRun(); });
  $("stop").addEventListener("click", () => {
    // Python can't be interrupted from outside, so restart the worker.
    worker.terminate();
    finishRun();
    $("progress-text").textContent = "Stopped.";
    startWorker();
  });

  startWorker();

  // ----------------------------------------------------------- results
  const charts = {};
  let lastResult = null;
  let lastRun = null;
  let errorLine = null;

  function showError(text) {
    $("results").hidden = false;
    $("error").hidden = false;
    $("result-body").hidden = true;
    // Tracebacks and syntax errors name the line as: File "<your code>", line 12
    const lines = [...text.matchAll(/"<your code>", line (\d+)/g)];
    const line = lines.length ? Number(lines[lines.length - 1][1]) : null;
    $("error").textContent = line && line <= editor.lineCount()
      ? `${text}\n\nLine ${line} is highlighted in the editor.` : text;
    if (line && line <= editor.lineCount()) {
      errorLine = editor.addLineClass(line - 1, "wrap", "cm-error-line");
      editor.setCursor(line - 1, 0);
    }
    $("error").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function clearErrorLine() {
    if (errorLine) editor.removeLineClass(errorLine, "wrap", "cm-error-line");
    errorLine = null;
  }

  const money = (v, sign = false) => {
    if (v == null || Number.isNaN(v)) return "–";
    const s = Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) < 100 ? 2 : 0 });
    if (v < 0) return `−$${s}`;
    return `${sign && v > 0 ? "+" : ""}$${s}`;
  };
  const pct = (v, digits = 1) => (v == null ? "–" : `${(v * 100).toFixed(digits)}%`);
  const signedPct = (v, digits = 2) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}%`);
  const round1 = (v) => (Math.round(v * 10) / 10).toLocaleString();

  function render(result) {
    lastResult = result;
    $("results").hidden = false;
    $("error").hidden = true;
    $("result-body").hidden = false;

    const [yours, base] = result.candidates;
    const used = [
      result.play ? `play strategy ${result.play}` : "basic strategy (no play strategy in your code)",
      result.bet ? `bet strategy ${result.bet}` : "a flat table-minimum bet (no bet strategy in your code)",
    ];
    $("used").textContent = `Ran ${yours.summary.sessions} sessions with ${used.join(" and ")}.`;

    renderTiles(yours.summary, base && base.summary);
    renderEdge(yours.summary, base && base.summary);
    renderBankroll(result);
    renderProfit(result);
    renderStats(result);
    renderLog(result.log);
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderTiles(s, b) {
    const ci = s.edge_se_pct == null ? "" : ` ± ${(1.96 * s.edge_se_pct).toFixed(2)}%`;
    const tiles = [
      { label: "Average profit per session", value: money(s.mean_net, true), base: b && money(b.mean_net, true),
        tone: s.mean_net > 0 ? "pos" : s.mean_net < 0 ? "neg" : "" },
      { label: "Return per $1 bet", value: signedPct(s.edge_pct), note: ci ? `95% range${ci}` : "", base: b && signedPct(b.edge_pct) },
      { label: "Sessions that ended ahead", value: pct(s.prob_profit, 0), base: b && pct(b.prob_profit, 0) },
      { label: "Sessions that went broke", value: pct(s.prob_ruin, 0), base: b && pct(b.prob_ruin, 0) },
      { label: "Average ending bankroll", value: money(s.mean_final), note: `started with ${money(s.start)}`, base: b && money(b.mean_final) },
      { label: "Hands per session", value: round1(s.avg_hands), note: `average bet ${money(s.avg_bet)}`, base: b && round1(b.avg_hands) },
    ];
    $("tiles").innerHTML = "";
    for (const t of tiles) {
      const el = document.createElement("div");
      el.className = "tile";
      el.innerHTML = `<div class="tile-label"></div><div class="tile-value"></div><div class="tile-note"></div>`;
      el.querySelector(".tile-label").textContent = t.label;
      const v = el.querySelector(".tile-value");
      v.textContent = t.value;
      if (t.tone) v.dataset.tone = t.tone;
      const notes = [t.note, t.base ? `baseline ${t.base}` : ""].filter(Boolean);
      el.querySelector(".tile-note").textContent = notes.join(" · ");
      $("tiles").appendChild(el);
    }
  }

  // ------------------------------------------------- edge vs baseline
  // Return per $1 bet with a 95% range for each strategy, and a plain verdict
  // on whether the run can tell them apart. The ranges treat the two runs as
  // independent; both use the same shuffles, so this errs on the cautious side.
  function renderEdge(s, b) {
    const card = $("edge-card");
    if (!b || s.edge_se_pct == null || b.edge_se_pct == null) { card.hidden = true; return; }
    card.hidden = false;
    const rows = [
      { name: "Your strategy", edge: s.edge_pct, half: 1.96 * s.edge_se_pct, cls: "" },
      { name: "Basic strategy, flat bet", edge: b.edge_pct, half: 1.96 * b.edge_se_pct, cls: "is-base" },
    ];
    const diff = s.edge_pct - b.edge_pct;
    const seDiff = Math.hypot(s.edge_se_pct, b.edge_se_pct);
    const verdict = $("verdict");
    verdict.innerHTML = "";
    const strong = document.createElement("strong");
    const amount = `${Math.abs(diff).toFixed(2)}%`;
    if (Math.abs(diff) > 1.96 * seDiff) {
      strong.textContent = diff > 0 ? `Your strategy is ahead by ${amount} per $1 bet.` : `Your strategy is behind by ${amount} per $1 bet.`;
      strong.dataset.tone = diff > 0 ? "pos" : "neg";
      verdict.append(strong, " That gap is bigger than the run's noise, so it's very likely real for these rules.");
    } else {
      strong.textContent = "Too close to call.";
      const need = s.sessions * (1.96 * seDiff / Math.max(Math.abs(diff), 1e-9)) ** 2;
      const more = need > 10000
        ? " The gap is so small it would take more than 10,000 sessions to measure, so the two are about the same."
        : ` To tell a ${amount} gap from luck, try about ${(Math.ceil(need / 10) * 10).toLocaleString()} sessions.`;
      verdict.append(strong, ` Your strategy's return differs from basic strategy by ${amount} per $1 bet, which is within the run's noise.${more}`);
    }

    let lo = Math.min(0, ...rows.map((r) => r.edge - r.half));
    let hi = Math.max(0, ...rows.map((r) => r.edge + r.half));
    const pad = (hi - lo) * 0.08 || 0.5;
    lo -= pad; hi += pad;
    const x = (v) => `${(100 * (v - lo)) / (hi - lo)}%`;
    const forest = $("forest");
    forest.innerHTML = "";
    for (const r of rows) {
      const row = document.createElement("div");
      row.className = `f-row ${r.cls}`;
      row.innerHTML = `<span class="f-name"></span><div class="f-track"><div class="f-zero"></div><div class="f-range"></div><div class="f-dot"></div></div><span class="f-val"></span>`;
      row.querySelector(".f-name").textContent = r.name;
      row.querySelector(".f-zero").style.left = x(0);
      const range = row.querySelector(".f-range");
      range.style.left = x(r.edge - r.half);
      range.style.width = `${(100 * 2 * r.half) / (hi - lo)}%`;
      row.querySelector(".f-dot").style.left = x(r.edge);
      row.querySelector(".f-val").textContent = `${signedPct(r.edge)} ± ${r.half.toFixed(2)}%`;
      forest.appendChild(row);
    }
    const axis = document.createElement("div");
    axis.className = "f-axis";
    const step = niceStep((hi - lo) / 4);
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
      const tick = document.createElement("span");
      tick.style.left = x(v);
      tick.textContent = signedPct(Math.abs(v) < step / 1e6 ? 0 : v, step < 0.1 ? 2 : step < 1 ? 1 : 0);
      axis.appendChild(tick);
    }
    forest.appendChild(axis);
  }

  // ---------------------------------------------------------- downloads
  $("download-csv").addEventListener("click", () => {
    if (!lastResult) return;
    const cands = lastResult.candidates;
    const quote = (v) => `"${String(v).replace(/"/g, '""')}"`;
    const lines = [["session", ...cands.map((c) => `${c.name} profit`)].map(quote).join(",")];
    cands[0].nets.forEach((_, i) => lines.push([i + 1, ...cands.map((c) => c.nets[i])].join(",")));
    download(fileName("csv"), lines.join("\n") + "\n", "text/csv");
  });
  $("download-json").addEventListener("click", () => {
    if (!lastResult) return;
    const out = { code: lastRun && lastRun.code, settings: lastRun && lastRun.settings, ...lastResult };
    download(fileName("json"), JSON.stringify(out, null, 2), "application/json");
  });

  // Colors come from CSS tokens so charts follow light and dark mode.
  function tokens() {
    const css = getComputedStyle(document.documentElement);
    const get = (n) => css.getPropertyValue(n).trim();
    return {
      series: get("--series-1"), band50: get("--band-50"), band90: get("--band-90"),
      baseline: get("--baseline"), sample: get("--sample"), grid: get("--grid"),
      text: get("--text-secondary"), surface: get("--surface-2"), zero: get("--text-muted"),
    };
  }

  function baseOptions(t) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top", align: "start", labels: { color: t.text, boxWidth: 14, boxHeight: 8, usePointStyle: false } },
        tooltip: { backgroundColor: t.surface, titleColor: t.text, bodyColor: t.text, borderColor: t.grid, borderWidth: 1 },
      },
    };
  }

  function renderBankroll(result) {
    const t = tokens();
    const [yours, base] = result.candidates;
    const rounds = yours.bands.round;
    const pts = (arr) => arr.map((y, i) => ({ x: rounds[i], y }));
    const line = { pointRadius: 0, pointHoverRadius: 0, borderWidth: 0 };
    const datasets = [
      { label: "Middle 90% of sessions", data: pts(yours.bands.p95), fill: "+1", backgroundColor: t.band90, ...line, role: "p95" },
      { label: "p05", data: pts(yours.bands.p05), fill: false, ...line, role: "p05" },
      { label: "Middle 50% of sessions", data: pts(yours.bands.p75), fill: "+1", backgroundColor: t.band50, ...line, role: "p75" },
      { label: "p25", data: pts(yours.bands.p25), fill: false, ...line, role: "p25" },
      { label: "Your median session", data: pts(yours.bands.p50), borderColor: t.series, backgroundColor: t.series, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, role: "median" },
    ];
    if (base) {
      datasets.push({ label: "Baseline median (basic, flat bet)", data: pts(base.bands.p50), borderColor: t.baseline, backgroundColor: t.baseline,
        borderWidth: 2, borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 4, role: "baseline" });
    }
    if ($("show-samples").checked) {
      yours.samples.forEach((s, i) => datasets.push({ label: `Session ${i + 1}`, data: pts(s), borderColor: t.sample, borderWidth: 1,
        pointRadius: 0, pointHoverRadius: 0, role: "sample" }));
    }
    const byRole = (role) => datasets.findIndex((d) => d.role === role);
    const opts = baseOptions(t);
    opts.plugins.legend.labels.filter = (item) => !["p05", "p25", "sample"].includes(datasets[item.datasetIndex].role);
    opts.plugins.tooltip.filter = (item) => ["p95", "p75", "median", "baseline"].includes(datasets[item.datasetIndex].role);
    opts.plugins.tooltip.callbacks = {
      title: (items) => `Round ${items[0].parsed.x}`,
      label: (item) => {
        const role = datasets[item.datasetIndex].role;
        const i = item.dataIndex;
        if (role === "p95") return `Middle 90%: ${money(datasets[byRole("p05")].data[i].y)} to ${money(item.parsed.y)}`;
        if (role === "p75") return `Middle 50%: ${money(datasets[byRole("p25")].data[i].y)} to ${money(item.parsed.y)}`;
        return `${role === "median" ? "Your median" : "Baseline median"}: ${money(item.parsed.y)}`;
      },
    };
    opts.scales = {
      x: { type: "linear", min: 0, max: rounds[rounds.length - 1], title: { display: true, text: "Round", color: t.text },
        grid: { display: false }, ticks: { color: t.text, maxTicksLimit: 8 } },
      y: { title: { display: true, text: "Bankroll", color: t.text }, grid: { color: t.grid }, ticks: { color: t.text, callback: (v) => money(v) } },
    };
    draw("bankroll-chart", { type: "line", data: { datasets }, options: opts });
  }

  function renderProfit(result) {
    const t = tokens();
    const cands = result.candidates;
    const all = cands.flatMap((c) => c.nets);
    let lo = Math.min(...all), hi = Math.max(...all);
    if (lo === hi) { lo -= 1; hi += 1; }
    const bins = Math.min(30, Math.max(8, Math.round(Math.sqrt(cands[0].nets.length) * 2)));
    const width = niceStep((hi - lo) / bins);
    const start = Math.floor(lo / width) * width;
    const n = Math.max(1, Math.ceil((hi - start) / width + 1e-9));
    const labels = Array.from({ length: n }, (_, i) => start + i * width);
    const count = (nets) => {
      const c = new Array(n).fill(0);
      for (const v of nets) c[Math.min(n - 1, Math.floor((v - start) / width))] += 1;
      return c.map((k) => (100 * k) / nets.length);
    };
    const datasets = [{ label: "Your strategy", data: count(cands[0].nets), backgroundColor: t.series, borderRadius: 3, borderSkipped: "bottom" }];
    if (cands[1]) datasets.push({ label: "Baseline (basic, flat bet)", data: count(cands[1].nets), backgroundColor: t.baseline, borderRadius: 3, borderSkipped: "bottom" });
    const opts = baseOptions(t);
    opts.plugins.legend.display = datasets.length > 1;
    opts.plugins.tooltip.callbacks = {
      title: (items) => `Profit ${money(labels[items[0].dataIndex], true)} to ${money(labels[items[0].dataIndex] + width, true)}`,
      label: (item) => `${item.dataset.label}: ${item.parsed.y.toFixed(1)}% of sessions`,
    };
    opts.scales = {
      x: { grid: { display: false }, ticks: { color: t.text, maxTicksLimit: 8, callback: (_, i) => money(labels[i], true) },
        title: { display: true, text: "Profit at end of session", color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text, callback: (v) => `${v}%` }, title: { display: true, text: "Share of sessions", color: t.text } },
    };
    opts.datasets = { bar: { categoryPercentage: 0.9, barPercentage: 0.95 } };
    draw("profit-chart", { type: "bar", data: { labels, datasets }, options: opts });
  }

  function niceStep(raw) {
    const mag = 10 ** Math.floor(Math.log10(raw));
    for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * mag) return m * mag;
    return 10 * mag;
  }

  function draw(id, config) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart($(id), config);
  }

  const STATS = [
    ["Average profit per session", "mean_net", (v) => money(v, true)],
    ["Median profit per session", "median_net", (v) => money(v, true)],
    ["Worst 5% of sessions end below", "p05_net", (v) => money(v, true)],
    ["Best 5% of sessions end above", "p95_net", (v) => money(v, true)],
    ["Return per $1 bet (player edge)", "edge_pct", (v) => signedPct(v)],
    ["Standard error of the edge", "edge_se_pct", (v) => (v == null ? "–" : `${v.toFixed(2)}%`)],
    ["Profit per hand", "ev_per_hand", (v) => money(v, true)],
    ["Sessions that ended ahead", "prob_profit", (v) => pct(v)],
    ["Sessions that went broke", "prob_ruin", (v) => pct(v)],
    ["Sessions that hit the win target", "prob_target", (v) => pct(v)],
    ["Sessions that hit the stop loss", "prob_stop_loss", (v) => pct(v)],
    ["Hands per session", "avg_hands", round1],
    ["Average bet", "avg_bet", (v) => money(v)],
    ["Average worst drop from a peak", "avg_max_drawdown", (v) => money(v)],
  ];

  function renderStats(result) {
    const rows = [["", ...result.candidates.map((c) => c.name)]];
    for (const [label, key, fmt] of STATS) rows.push([label, ...result.candidates.map((c) => fmt(c.summary[key]))]);
    fillTable($("stats-table"), rows);
  }

  function renderLog(log) {
    const cols = [["round", "Round"], ["true_count", "True count"], ["bet", "Bet"], ["player", "Your cards"], ["dealer", "Dealer"],
      ["dealer_total", "Dealer total"], ["outcome", "Outcome"], ["net", "Net"], ["bankroll", "Bankroll"]];
    const rows = [cols.map((c) => c[1])];
    for (const r of log) {
      rows.push(cols.map(([k]) => {
        const v = r[k];
        if (k === "bet" || k === "bankroll") return money(v);
        if (k === "net") return money(v, true);
        if (k === "round" && r.shuffled) return `${v} (shuffle)`;
        return v == null ? "" : String(v);
      }));
    }
    fillTable($("log-table"), rows);
  }

  function fillTable(table, rows) {
    table.innerHTML = "";
    const thead = table.createTHead().insertRow();
    for (const h of rows[0]) { const th = document.createElement("th"); th.textContent = h; thead.appendChild(th); }
    const body = table.createTBody();
    for (const r of rows.slice(1)) {
      const tr = body.insertRow();
      r.forEach((v, i) => { const cell = i === 0 ? document.createElement("th") : document.createElement("td"); cell.textContent = v; tr.appendChild(cell); });
    }
  }

  $("show-samples").addEventListener("change", () => lastResult && renderBankroll(lastResult));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (lastResult) { renderBankroll(lastResult); renderProfit(lastResult); }
  });
})();
