// Page logic: editor, settings, the Python worker, and rendering results.
(() => {
  const $ = (id) => document.getElementById(id);
  const STORAGE_KEY = "bj-lab-code";

  // ------------------------------------------------------------ editor
  const examples = window.EXAMPLES;
  const exampleSelect = $("example");
  examples.forEach((ex, i) => exampleSelect.add(new Option(ex.name, String(i))));

  let saved = null;
  try { saved = localStorage.getItem(STORAGE_KEY); } catch (_) { /* storage blocked */ }

  const editor = CodeMirror($("editor"), {
    value: saved || examples[0].code,
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
  editor.on("change", () => {
    try { localStorage.setItem(STORAGE_KEY, editor.getValue()); } catch (_) { /* storage blocked */ }
  });
  if (saved) exampleSelect.value = "";

  exampleSelect.addEventListener("change", () => {
    const ex = examples[Number(exampleSelect.value)];
    if (!ex) return;
    const current = editor.getValue();
    const untouched = examples.some((e) => e.code === current);
    if (!untouched && !confirm("Replace your code with this example?")) {
      exampleSelect.value = "";
      return;
    }
    editor.setValue(ex.code);
  });

  // ---------------------------------------------------------- settings
  const outputs = {
    players: (v) => (v === "1" ? "just you" : `you + ${v - 1}`),
    num_decks: (v) => v,
    penetration: (v) => `${Math.round(v * 100)}%`,
  };
  for (const [id, fmt] of Object.entries(outputs)) {
    const input = $(id);
    const show = () => { $(`${id}-out`).textContent = fmt(input.value); };
    input.addEventListener("input", show);
    show();
  }

  const num = (id) => Number($(id).value);
  const checked = (id) => $(id).checked;

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
    if (msg.type === "ready") {
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
    worker.postMessage({ code: editor.getValue(), settings: readSettings() });
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

  function showError(text) {
    $("results").hidden = false;
    $("error").hidden = false;
    $("error").textContent = text;
    $("result-body").hidden = true;
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
