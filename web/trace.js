/* Symbol Trace — per-rule evaluation viewer
   Calls GET /api/trace/{symbol}?date=YYYY-MM-DD and renders the page.
   Default symbol: AAPL.  Default date: latest available (server picks).        */

const $ = (id) => document.getElementById(id);

const STATE = {
  symbol: "AAPL",
  date:   "",
  data:   null,
  filter: { kind: "all", value: null },   // {kind: 'all'|'fired'|'category', value}
};

/* ---------- bootstrapping ---------- */

window.addEventListener("DOMContentLoaded", () => {
  // Read query params
  const qp = new URLSearchParams(window.location.search);
  const sym = (qp.get("symbol") || "AAPL").toUpperCase();
  const dt  = qp.get("date") || "";

  STATE.symbol = sym;
  STATE.date   = dt;

  $("symInput").value = sym;
  if (dt) $("datePicker").value = dt;

  $("goBtn").addEventListener("click", onGoClicked);
  $("symInput").addEventListener("keydown", e => { if (e.key === "Enter") onGoClicked(); });
  $("datePicker").addEventListener("change", onGoClicked);

  loadTrace();
});

function onGoClicked() {
  STATE.symbol = ($("symInput").value || "AAPL").trim().toUpperCase();
  STATE.date   = $("datePicker").value || "";
  // Update URL without reload
  const qp = new URLSearchParams();
  qp.set("symbol", STATE.symbol);
  if (STATE.date) qp.set("date", STATE.date);
  history.replaceState(null, "", "?" + qp.toString());
  loadTrace();
}

/* ---------- data fetch ---------- */

async function loadTrace() {
  $("errBanner").style.display = "none";
  $("rulesBody").innerHTML =
    `<tr><td colspan="7" class="empty">Loading ${STATE.symbol}…</td></tr>`;
  $("compGrid").innerHTML = "";

  const url = `/api/trace/${encodeURIComponent(STATE.symbol)}` +
              (STATE.date ? `?date=${encodeURIComponent(STATE.date)}` : "");
  let resp;
  try {
    resp = await fetch(url, { headers: { Accept: "application/json" } });
  } catch (e) {
    showErr(`Network error: ${e.message}`);
    return;
  }
  if (!resp.ok) {
    let detail = await resp.text();
    try { detail = JSON.parse(detail).detail || detail; } catch { /* */ }
    showErr(`API ${resp.status}: ${detail}`);
    return;
  }
  STATE.data = await resp.json();
  const asOf = STATE.data.as_of || STATE.data.as_of_date;
  if (!STATE.date) $("datePicker").value = asOf;

  // Update Cockpit deep-link
  const ck = new URLSearchParams();
  ck.set("symbol", STATE.data.tos_symbol);
  ck.set("date",   asOf);
  $("cockpitLink").href = `/actionable?${ck.toString()}`;

  render();
  loadRRChart(STATE.data.tos_symbol, STATE.data.as_of || STATE.data.as_of_date);
}

async function loadRRChart(symbol, date) {
  const sec = $('rrSection');
  const el  = $('rrChart');
  sec.style.display = 'none';
  try {
    const data = await fetch(
      `/api/actionable/rr-analysis?symbol=${encodeURIComponent(symbol)}&date=${encodeURIComponent(date)}`,
      { headers: { Accept: 'application/json' } }
    ).then(r => r.ok ? r.json() : null);
    if (data && (data.levels.lrr != null || data.levels.trr != null ||
                 data.levels.trend != null || data.levels.trade != null)) {
      sec.style.display = '';
      if (window.td_common && window.td_common.renderRRAnalysis) {
        window.td_common.renderRRAnalysis(data, el, symbol, date);
      }
    }
  } catch(_) {}
}

function showErr(msg) {
  const el = $("errBanner");
  el.textContent = msg;
  el.style.display = "block";
  $("rulesBody").innerHTML = `<tr><td colspan="7" class="empty">No trace available.</td></tr>`;
}

/* ---------- render ---------- */

function render() {
  const d = STATE.data;
  const s = d.summary || {};

  $("symBadge").textContent = d.tos_symbol;
  $("symName").textContent  = s.description || d.tos_symbol;
  $("symSub").textContent   =
    [s.sector, s.asset_class, s.last_price != null ? `last $${fmtNum(s.last_price, 2)}` : null]
      .filter(Boolean).join(" · ") || "—";

  // KPIs
  setKpi("kpiOutlook", s.rr_outlook || "—", classByLabel(s.rr_outlook));
  setKpi("kpiLabel",   s.rr_outlook || "—", classByLabel(s.rr_outlook));
  setKpi("kpiCompFired", `${s.n_composite_fired || 0} / ${s.n_composite_total || 0}`, "");
  setKpi("kpiAtomFired", `${s.n_atomic_fired   || 0} / ${s.n_atomic_total   || 0}`, "");

  // Composites grid
  renderComposites(d.composites || []);

  // Outlook attribution (per-source change vs prev snapshot)
  renderOutlook(d.outlook, d.actionable);

  // Filter chips + table
  renderChips(d.atomics || []);
  renderRules();
}

function renderOutlook(outlook, actionable) {
  let container = $("outlookSection");
  if (!container) {
    container = document.createElement("section");
    container.id = "outlookSection";
    container.style.cssText = "margin: 12px 0; padding: 12px; background: var(--card-bg, #fff); " +
                              "border: 1px solid var(--border, #e0e0e0); border-radius: 6px;";
    const compGrid = $("compGrid");
    if (compGrid && compGrid.parentNode) {
      compGrid.parentNode.insertBefore(container, compGrid);
    } else {
      document.body.appendChild(container);
    }
  }
  if (!outlook && !actionable) { container.innerHTML = ""; container.style.display = "none"; return; }
  container.style.display = "";

  const sources = (outlook && outlook.actions) || [];
  const actMap = { REMOVE:"#7f1d1d", REDUCE:"#7c2d12", ADD:"#1e3a8a", INCREASE:"#14532d", HOLD:"#374151" };
  const bgMap  = { REMOVE:"#fee2e2", REDUCE:"#ffedd5", ADD:"#dbeafe", INCREASE:"#dcfce7", HOLD:"#f3f4f6" };

  const banner = (outlook && outlook.changed)
    ? `<span style="background:#fff8e1;border:1px solid #f3d27a;padding:2px 8px;border-radius:10px;color:#5b4400;">
         ${outlook.n_sources_changed} source(s) flipped outlook today
       </span>`
    : `<span style="color:#666;">No outlook changes today</span>`;

  let aDesc = "";
  if (actionable && actionable.consolidated_action) {
    const ca = actionable.consolidated_action;
    aDesc = `<span style="background:${bgMap[ca]||"#eee"};color:${actMap[ca]||"#222"};
                          padding:3px 10px;border-radius:4px;font-weight:600;">${ca}</span>
             <span style="color:#666;font-size:12px;margin-left:8px;">
               via ${actionable.winning_source||"—"}
               ${actionable.suppressed_reason ? `(suppressed: ${actionable.suppressed_reason})` : ""}
             </span>`;
  }

  const rows = sources.map(r => {
    const act = r.action || "—";
    const bg = bgMap[act] || "#f9fafb";
    const fg = actMap[act] || "#222";
    const delta = (r.weight_delta != null) ? fmtSigned(r.weight_delta) : "—";
    const prevW = (r.prev_weight != null) ? fmtSigned(r.prev_weight) : "—";
    const baseW = (r.base_weight != null) ? fmtSigned(r.base_weight) : "—";
    return `<tr>
      <td style="font-family:ui-monospace,Consolas,monospace;font-size:12px;">${r.source_code}</td>
      <td><span style="background:${bg};color:${fg};padding:1px 6px;border-radius:3px;font-weight:600;font-size:11px;">${act}</span></td>
      <td style="font-variant-numeric:tabular-nums;font-size:12px;">${prevW}</td>
      <td style="font-variant-numeric:tabular-nums;font-size:12px;">${baseW}</td>
      <td style="font-variant-numeric:tabular-nums;font-size:12px;color:${(r.weight_delta||0)<0?"#7f1d1d":"#14532d"};">${delta}</td>
      <td style="font-size:11px;color:#666;">${r.action_reason || ""}</td>
    </tr>`;
  }).join("");

  container.innerHTML = `
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap;">
      <strong style="font-size:13px;color:#374151;">Outlook attribution</strong>
      ${banner}
      ${aDesc ? ` &nbsp;→&nbsp; ${aDesc}` : ""}
    </div>
    ${sources.length ? `
      <table style="width:100%;border-collapse:collapse;font-size:12px;">
        <thead><tr style="background:#f9fafb;text-align:left;">
          <th style="padding:4px;">Source</th>
          <th style="padding:4px;">Action</th>
          <th style="padding:4px;">Prev wt</th>
          <th style="padding:4px;">Curr wt</th>
          <th style="padding:4px;">Δ</th>
          <th style="padding:4px;">Reason</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    ` : `<div style="color:#666;font-size:12px;">No outlook sources covered this symbol today.</div>`}
  `;
}

function classByLabel(lbl) {
  if (!lbl) return "";
  const u = String(lbl).toUpperCase();
  if (u.includes("BULL")) return "bull";
  if (u.includes("BEAR")) return "bear";
  return "";
}

function setKpi(id, value, cls) {
  const el = $(id);
  el.textContent = value;
  el.className = "v" + (cls ? " " + cls : "");
}

function renderComposites(comps) {
  const fired = comps.filter(c => c.fired).sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  const dim   = comps.filter(c => !c.fired).slice(0, 4);   // show first 4 dim ones for context
  $("compMeta").textContent = `${fired.length} of ${comps.length} composites fired`;

  if (!comps.length) {
    $("compGrid").innerHTML = `<div class="empty" style="grid-column:1/-1">No composite rules defined.</div>`;
    return;
  }

  const html = [...fired, ...dim].map(c => {
    const cls = c.fired ? "comp fired" + (c.score < 0 ? " bear" : "") : "comp dim";
    const sc  = c.score === 0 ? "zero" : (c.score > 0 ? "pos" : "neg");
    return `<div class="${cls}">
      <span class="code">${escapeHtml(c.code)}</span>
      <span class="score ${sc}">${fmtSigned(c.score)}</span>
    </div>`;
  }).join("");
  $("compGrid").innerHTML = html;
}

function renderChips(atomics) {
  const fired = atomics.filter(a => a.fired).length;
  const cats = {};
  atomics.forEach(a => {
    const c = a.category || "uncategorized";
    cats[c] = (cats[c] || 0) + 1;
  });

  const chips = [
    chipHtml("All", atomics.length, STATE.filter.kind === "all", "all", null),
    chipHtml("Fired only", fired, STATE.filter.kind === "fired", "fired", null),
  ];
  Object.entries(cats)
    .sort((a, b) => b[1] - a[1])
    .forEach(([cat, n]) => {
      const isActive = STATE.filter.kind === "category" && STATE.filter.value === cat;
      chips.push(chipHtml(cat, n, isActive, "category", cat));
    });

  $("chips").innerHTML = chips.join("");
  // Wire clicks
  $("chips").querySelectorAll(".chip").forEach(el => {
    el.addEventListener("click", () => {
      STATE.filter.kind  = el.dataset.kind;
      STATE.filter.value = el.dataset.value || null;
      renderChips(atomics);
      renderRules();
    });
  });
}

function chipHtml(label, n, active, kind, value) {
  const v = value == null ? "" : ` data-value="${escapeAttr(value)}"`;
  return `<span class="chip${active ? " active" : ""}" data-kind="${kind}"${v}>${escapeHtml(label)} <span class="n">${n}</span></span>`;
}

function renderRules() {
  const all = STATE.data.atomics || [];

  // Apply filter
  let rows = all;
  if (STATE.filter.kind === "fired") rows = all.filter(a => a.fired);
  else if (STATE.filter.kind === "category") rows = all.filter(a => (a.category || "uncategorized") === STATE.filter.value);

  // Sort: fired first, then by abs(weight) desc, then by id
  rows = [...rows].sort((a, b) => {
    if (a.fired !== b.fired) return a.fired ? -1 : 1;
    const dw = Math.abs(b.weight) - Math.abs(a.weight);
    if (dw !== 0) return dw;
    return a.id - b.id;
  });

  if (!rows.length) {
    $("rulesBody").innerHTML = `<tr><td colspan="7" class="empty">No rules match the current filter.</td></tr>`;
    $("ruleFootCount").textContent = "0 of " + all.length;
    return;
  }

  $("rulesBody").innerHTML = rows.map(rowHtml).join("");
  const firedCount = all.filter(a => a.fired).length;
  $("ruleFootCount").textContent =
    `Showing ${rows.length} of ${all.length} atomic rules · ${firedCount} fired`;
}

function rowHtml(a) {
  const fired = a.fired;
  const cls = fired ? "fired" : "dim";
  const dot = `<span class="firedot${fired ? "" : " off"}"></span>`;
  const valDisplay = a.value === null || a.value === undefined ? "—" : formatValue(a.value);
  const wClass = fired ? (a.weight > 0 ? "pos" : "neg") : "zero";
  const wText  = fmtSigned(a.weight);
  const modeClass = (a.scoring_mode || "jump").toLowerCase();
  const rolls = (a.rolls_into || []).slice(0, 3).join(" · ") +
                ((a.rolls_into || []).length > 3 ? ` +${a.rolls_into.length - 3}` : "") || "—";

  // "Why didn't it fire?" — show a compact tag for dim rows so users can spot
  // no_data / no_column / no_thresholds at a glance without clicking through.
  const reasonTag = !fired && a.reason
    ? `<div class="rule-reason" title="${escapeAttr(a.reason)}">${escapeHtml(reasonTagText(a.reason))}</div>`
    : "";
  const rowTitle = a.reason ? `title="${escapeAttr(a.reason)}"` : "";

  return `<tr class="${cls}" ${rowTitle}>
    <td>${dot}${escapeHtml(a.rule_name || "rule#" + a.id)}${reasonTag}</td>
    <td class="mono">${escapeHtml(shortColName(a.ma_column))}</td>
    <td class="val">${escapeHtml(valDisplay)}</td>
    <td>${bandHtml(a)}<div class="thresh">${escapeHtml(thresholdText(a))}</div></td>
    <td><span class="mode ${escapeAttr(modeClass)}">${escapeHtml(modeClass)}</span></td>
    <td><span class="w ${wClass}">${escapeHtml(wText)}</span></td>
    <td class="rolls" title="${escapeAttr((a.rolls_into||[]).join(', '))}">${escapeHtml(rolls)}</td>
  </tr>`;
}

function reasonTagText(reason) {
  // Take just the first token before "—" so tags stay compact.
  const head = String(reason).split("—")[0].trim();
  return head;
}

/* ---------- threshold band ---------- */

function bandHtml(a) {
  const lo = numOrNull(a.brkeout_from);
  const hi = numOrNull(a.brkeout_to);
  const v  = numOrNull(a.value);

  if (lo === null && hi === null) {
    return `<div class="band"><span class="v" style="left:50%"></span></div>`;
  }

  // Build a comfortable display window around [lo, hi]
  const lo2 = lo === null ? hi - 1 : lo;
  const hi2 = hi === null ? lo + 1 : hi;
  const span = Math.max(hi2 - lo2, 0.0001);
  const padLeft = Math.max(span * 0.35, 0.5);
  const padRight = Math.max(span * 0.35, 0.5);
  const winLo = lo2 - padLeft;
  const winHi = hi2 + padRight;
  const winSpan = winHi - winLo;
  const pct = (x) => {
    let p = ((x - winLo) / winSpan) * 100;
    if (p < 0) p = 0; if (p > 100) p = 100;
    return p;
  };

  let cls = "v";
  if (v === null) {
    cls = "v";   // unknown — gray
  } else if (v < lo2) {
    cls = "v under";
  } else if (v > hi2) {
    cls = "v over";
  } else {
    cls = "v in";
  }

  const loPct = pct(lo2).toFixed(1);
  const hiPct = pct(hi2).toFixed(1);
  const vPct  = v === null ? 50 : pct(v).toFixed(1);

  return `<div class="band">
    <span class="lo" style="left:${loPct}%"></span>
    <span class="hi" style="left:${hiPct}%"></span>
    <span class="${cls}" style="left:${vPct}%"></span>
  </div>`;
}

function thresholdText(a) {
  const lo = a.brkeout_from === null ? "—" : fmtNum(a.brkeout_from, 2);
  const hi = a.brkeout_to   === null ? "—" : fmtNum(a.brkeout_to,   2);
  const v  = a.value === null || a.value === undefined ? "—" : formatValue(a.value);
  return `${lo} / ${hi}  ·  v=${v}`;
}

/* ---------- formatting helpers ---------- */

function numOrNull(x) {
  if (x === null || x === undefined) return null;
  if (typeof x === "number") return isFinite(x) ? x : null;
  if (typeof x === "string") {
    if (x === "+" || x === "-") return x === "+" ? 1 : -1;
    const n = parseFloat(x);
    return isFinite(n) ? n : null;
  }
  return null;
}

function formatValue(v) {
  if (typeof v === "number") return fmtNum(v, 2);
  return String(v);
}

function fmtNum(n, decimals = 2) {
  if (n === null || n === undefined || !isFinite(n)) return "—";
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return n.toFixed(decimals).replace(/\.?0+$/, "") || "0";
}

function fmtSigned(n) {
  if (n === null || n === undefined || !isFinite(n)) return "—";
  if (n === 0) return "0";
  return (n > 0 ? "+" : "") + fmtNum(n, 2);
}

function shortColName(s) {
  if (!s) return "—";
  const i = String(s).lastIndexOf(".");
  return i === -1 ? String(s) : String(s).slice(i + 1);
}

// escapeHtml is provided by _common.js (window.escapeHtml).

function escapeAttr(s) {
  return escapeHtml(s);
}
