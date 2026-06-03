/* Parameter-set management screen.
   Lists ref_trig_param_set rows, shows values, and activates / deactivates /
   deletes via /api/rules/param-sets. See docs/rule_engine_redesign.md. */

const $ = (id) => document.getElementById(id);
let _sets = [];
let _openId = null;

function msg(t, ok = true) {
  const el = $("psMsg");
  el.textContent = t || "";
  el.style.color = ok ? "#059669" : "#b91c1c";
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function fmtNum(v) {
  if (v == null) return "";
  const n = Number(v);
  return Number.isFinite(n) ? (Math.round(n * 1e6) / 1e6).toString() : esc(v);
}

function fmtDate(s) {
  if (!s) return "";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? esc(s) : d.toLocaleString();
}

async function load() {
  msg("");
  let rows;
  try {
    const r = await fetch("/api/rules/param-sets");
    if (!r.ok) throw new Error("HTTP " + r.status);
    rows = await r.json();
  } catch (e) {
    $("psBody").innerHTML = `<tr><td colspan="8" class="muted">Could not load (${esc(e.message)})</td></tr>`;
    return;
  }
  _sets = rows || [];
  renderBanner();
  renderTable();
  if (_openId != null && _sets.some(s => s.param_set_id === _openId)) openDetail(_openId);
}

function renderBanner() {
  const active = _sets.find(s => s.is_active);
  const b = $("banner");
  if (active) {
    b.className = "ps-banner active";
    b.innerHTML = `<b>Active set:</b> #${active.param_set_id} — ${esc(active.label)} `
      + `<span class="muted">(${active.n_targets} rules, ${active.n_values} values)</span>. `
      + `Run <code>rebuild_rules</code> after any change.`;
  } else {
    b.className = "ps-banner none";
    b.innerHTML = `<b>No active parameter set.</b> The engine is using the base values stored on each atomic rule.`;
  }
}

function renderTable() {
  if (!_sets.length) {
    $("psBody").innerHTML = `<tr><td colspan="8" class="muted">No parameter sets yet. `
      + `Create one with <code>python -m etl.ml_tune_thresholds</code>.</td></tr>`;
    return;
  }
  $("psBody").innerHTML = _sets.map(s => {
    const status = s.is_active
      ? `<span class="pill on">ACTIVE</span>`
      : `<span class="pill off">inactive</span>`;
    const actToggle = s.is_active
      ? `<button class="ps-btn" data-act="deactivate" data-id="${s.param_set_id}">Deactivate</button>`
      : `<button class="ps-btn primary" data-act="activate" data-id="${s.param_set_id}">Activate</button>`;
    return `<tr class="${s.is_active ? "is-active" : ""}">
      <td>${s.param_set_id}</td>
      <td><b>${esc(s.label)}</b>${s.notes ? `<div class="muted" style="font-size:11px">${esc(s.notes)}</div>` : ""}</td>
      <td>${esc(s.provenance || "")}</td>
      <td>${status}</td>
      <td>${s.n_targets}</td>
      <td>${s.n_values}</td>
      <td class="muted">${fmtDate(s.created_at)}</td>
      <td>
        <button class="ps-btn" data-act="view" data-id="${s.param_set_id}">View</button>
        ${actToggle}
        <button class="ps-btn danger" data-act="delete" data-id="${s.param_set_id}">Delete</button>
      </td>
    </tr>`;
  }).join("");

  $("psBody").querySelectorAll("button[data-act]").forEach(btn => {
    btn.addEventListener("click", () => handleAction(btn.dataset.act, Number(btn.dataset.id)));
  });
}

async function handleAction(act, id) {
  if (act === "view") { return openDetail(id); }
  if (act === "delete") {
    if (!confirm(`Delete parameter set #${id} and all its values?`)) return;
    await call(`/api/rules/param-sets/${id}`, "DELETE", `Deleted set #${id}`);
    if (_openId === id) { _openId = null; $("psDetail").innerHTML = ""; }
    return;
  }
  if (act === "activate") {
    await call(`/api/rules/param-sets/${id}/activate`, "POST",
      `Activated set #${id}. Run rebuild_rules to apply.`);
    return;
  }
  if (act === "deactivate") {
    await call(`/api/rules/param-sets/${id}/deactivate`, "POST",
      `Deactivated set #${id}. Engine now uses base values.`);
    return;
  }
}

async function call(url, method, okMsg) {
  try {
    const r = await fetch(url, { method });
    if (!r.ok) throw new Error("HTTP " + r.status + ": " + (await r.text()));
    msg(okMsg, true);
    await load();
  } catch (e) {
    msg("Failed: " + e.message, false);
  }
}

async function openDetail(id) {
  _openId = id;
  const box = $("psDetail");
  box.innerHTML = `<div class="muted">Loading values for set #${id}…</div>`;
  let data;
  try {
    const r = await fetch(`/api/rules/param-sets/${id}`);
    if (!r.ok) throw new Error("HTTP " + r.status);
    data = await r.json();
  } catch (e) {
    box.innerHTML = `<div class="muted">Could not load set #${id} (${esc(e.message)})</div>`;
    return;
  }
  const vals = data.values || [];
  // group by target so each rule shows its params on one row
  const byTarget = {};
  for (const v of vals) {
    const key = v.target_id;
    (byTarget[key] = byTarget[key] || { name: v.rule_name || v.target_id, kind: v.target_kind, params: {} })
      .params[v.param_name] = v.param_value;
  }
  const targets = Object.entries(byTarget);
  const rowsHtml = targets.map(([tid, t]) => {
    const ps = Object.entries(t.params)
      .map(([k, val]) => `<span class="pill off" style="margin-right:4px">${esc(k)}=${fmtNum(val)}</span>`)
      .join(" ");
    return `<tr><td>${esc(t.name)}</td><td class="muted">${esc(t.kind)}</td><td>${ps}</td></tr>`;
  }).join("");
  box.innerHTML = `
    <h3 style="font-size:13px;margin:0 0 8px">Set #${id} — ${esc(data.set.label)}
      <span class="muted" style="font-weight:400">(${targets.length} targets, ${vals.length} values)</span></h3>
    <table>
      <thead><tr><th>Target</th><th>Kind</th><th>Parameters</th></tr></thead>
      <tbody>${rowsHtml || `<tr><td colspan="3" class="muted">No values</td></tr>`}</tbody>
    </table>`;
}

document.addEventListener("DOMContentLoaded", () => {
  $("reloadBtn").addEventListener("click", load);
  load();
});
