// Runs Python (Pyodide) off the main thread so the page stays responsive,
// and so a runaway strategy can be stopped by terminating the worker.
const PYODIDE_URL = "https://cdn.jsdelivr.net/npm/pyodide@0.29.5/";
importScripts(PYODIDE_URL + "pyodide.js");

async function boot() {
  postMessage({ type: "status", text: "Downloading Python…" });
  // Fetch the simulator package (zipped by scripts/build_web.py) while
  // Pyodide downloads and compiles, instead of after it.
  const zip = fetch("blackjack_sim.zip").then((res) => {
    if (!res.ok) throw new Error(`Couldn't load blackjack_sim.zip (HTTP ${res.status}). Build the site with scripts/build_web.py.`);
    return res.arrayBuffer();
  });
  zip.catch(() => {}); // reported below, once Pyodide is up
  const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  postMessage({ type: "status", text: "Loading the simulator…" });
  pyodide.unpackArchive(await zip, "zip");
  pyodide.runPython(`
import json
from blackjack_sim import playground

def _run(code, settings_json, progress):
    try:
        result = playground.run(code, json.loads(settings_json), progress)
        return json.dumps({"ok": True, "result": result}, default=str)
    except playground.StrategyError as e:
        return json.dumps({"ok": False, "error": str(e)})
    except ValueError as e:
        return json.dumps({"ok": False, "error": f"Settings problem: {e}"})
`);
  return pyodide;
}

const ready = boot();
ready.then(
  () => postMessage({ type: "ready" }),
  (err) => postMessage({ type: "boot-error", error: String(err && err.message || err) }),
);

onmessage = async (event) => {
  const { code, settings } = event.data;
  const pyodide = await ready;
  const run = pyodide.globals.get("_run");
  const progress = (done, total) => postMessage({ type: "progress", done, total });
  try {
    const out = JSON.parse(run(code, JSON.stringify(settings), progress));
    postMessage({ type: "done", ...out });
  } catch (err) {
    postMessage({ type: "done", ok: false, error: String(err && err.message || err) });
  } finally {
    run.destroy();
  }
};
