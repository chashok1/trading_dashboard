/* Composite editor — supports three member kinds:
     'atomic'    — pick from ref_trig_atomic_rule
     'data'      — inline rule against a drv_cat column
     'composite' — nest another composite by code
   Persists via PUT /api/rules/composite/{id}/members
   Previews via POST /api/rules/composite/{id}/dryrun                 */

const $ = id => document.getElementById(id);

const STATE = {
  ruleId: "",
  category: null,
  intent: null,
  precondition: null,
  active: true,
  members: [],     // [{kind, ...kind-specific fields, weight_override}]
  catalog: { atomics: [], composites: [], dataCols: [] },
};

window.addEventListener("DOMContentLoaded", async () => {
  // Read query: composite-edit?id=899-SA-Trend-Breaks
  const qp = new URLSearchParams(window.location.search);
  STATE.ruleId = qp.get("id") || "";
  if (STATE.ruleId) $("codeInput").value = STATE.ruleId;

  // Wire buttons
  $("loadBtn").addEventListener("click", () => {
    STATE.ruleId = ($("codeInput").value || "").trim();
    if (!STATE.ruleId) return;
    history.replaceState(null, "", "?id=" + encodeURIComponent(STATE.ruleId));
    loadComposite();
  });
  $("codeInput").addEventListener("keydown", e => { if (e.key === "Enter") $("loadBtn").click(); });

  $("saveBtn").addEventListener("click", saveComposite);
  $("deprecateBtn").addEventListener("click", deprecateComposite);
  $("cloneBtn").addEventListener("click", cloneComposite);
  $("cancelBtn").addEventListener("click", () => location.href = "/rules");
  $("dryrunBtn").addEventListener("click", runDryrun);

  // Add-tab switching
  document.querySelectorAll(".ce-add-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".ce-add-tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".ce-add-pane").forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      document.querySelector(`.ce-add-pane[data-kind="${tab.dataset.kind}"]`).classList.add("active");
    });
  });

  // Add buttons per kind
  $("addAtomicBtn").addEventListener("click", addAtomicMember);
  $("addDataBtn").addEventListener("click", addDataMember);
  $("addCompBtn").addEventListener("click", addCompositeMember);

  // Wire typeaheads
  setupTypeahead("atomicPicker", "atomicSuggest",
    () => STATE.catalog.atomics,
    a => `${a.rule_name} <span class="sub">drv_cat_atomic_input.${snakeName(a.rule_name)}</span>`,
    a => a.rule_name
  );
  setupTypeahead("dataPicker", "dataSuggest",
    () => STATE.catalog.dataCols,
    c => `${c.column_name} <span class="sub">${c.drv_cat_table} · ${c.excel_header}</span>`,
    c => `${c.drv_cat_table}.${c.column_name}`
  );
  setupTypeahead("compPicker", "compSuggest",
    () => STATE.catalog.composites.filter(c => c.composite_rule_code !== STATE.ruleId),
    c => `${c.composite_rule_code} <span class="sub">${c.category || "—"}</span>`,
    c => c.composite_rule_code
  );

  // Wire metadata inputs to STATE
  ["catInput", "intentInput", "preInput", "actSel"].forEach(id => {
    $(id).addEventListener("change", () => {
      STATE.category     = $("catInput").value || null;
      STATE.intent       = $("intentInput").value || null;
      STATE.precondition = $("preInput").value || null;
    });
  });

  // Bootstrap catalogs (atomics, composites, data cols)
  await loadCatalogs();
  await loadBases();
  if (STATE.ruleId) await loadComposite();
});

/* ---------- base-rule picker (Phase 2) ---------- */

async function loadBases() {
  const box = $("basePicker");
  try {
    const r = await fetch("/api/rules/base-composites");
    STATE.bases = r.ok ? await r.json() : [];
  } catch (e) {
    STATE.bases = [];
  }
  if (!box) return;
  if (!STATE.bases.length) {
    box.innerHTML = `<div style="color:var(--text-3);font-size:12px">No BASE-* rules found. `
      + `Apply <code>db/seeds_base_rules.sql</code> to create them.</div>`;
    return;
  }
  box.innerHTML = STATE.bases.map(b => {
    const mem = (b.members || []).map(m => {
      const opSym = { ">=": "≥", "<=": "≤", ">": ">", "<": "<", "=": "=" }[m.operator] || "";
      const thr = m.threshold != null ? ` ${opSym}${m.threshold}` : "";
      const role = m.role === "watch" ? " ·watch" : "";
      return `${escapeHtml(m.rule_name)}${thr}${role}`;
    }).join(" · ");
    const code = escapeAttr(b.code);
    return `<div class="ce-base-card" style="border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <div>
          <div style="font-weight:700;font-size:13px">${escapeHtml(b.code)}</div>
          <div style="font-size:11px;color:var(--text-2)">${escapeHtml(b.intent_text || "")}</div>
        </div>
        <div style="flex-shrink:0">
          <button class="ce-btn add-btn base-add" data-code="${code}" data-role="gate">Add as gate</button>
          <button class="ce-btn base-add" data-code="${code}" data-role="watch" style="margin-left:4px">Add as WATCH</button>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text-3);margin-top:5px">${mem}</div>
    </div>`;
  }).join("");
  box.querySelectorAll("button.base-add").forEach(btn => {
    btn.addEventListener("click", () => addBaseMember(btn.dataset.code, btn.dataset.role));
  });
}

function addBaseMember(code, role) {
  if (!code) return;
  if (code === STATE.ruleId) { showErr("A composite can't reference itself"); return; }
  if (STATE.members.some(m => m.kind === "composite" && m.nested_composite_code === code)) {
    showErr(`${code} is already nested`); return;
  }
  STATE.members.push({
    kind: "composite",
    nested_composite_code: code,
    member_role: role === "watch" ? "watch" : "gate",
    weight_override: null,
  });
  renderMembers(); showErr(null);
  showInfo(`Added ${code} as ${role === "watch" ? "WATCH" : "gate"}`);
}

/* ---------- catalogs ---------- */

async function loadCatalogs() {
  try {
    const [atomicsRes, compsRes, regRes] = await Promise.all([
      fetch("/api/rules/atomic?limit=500"),
      fetch("/api/rules/composite?limit=500"),
      fetch("/api/data/ref_ma_columns?limit=2000").catch(() => null),
    ]);
    if (atomicsRes.ok) {
      const data = await atomicsRes.json();
      STATE.catalog.atomics = Array.isArray(data) ? data : (data.rows || []);
    }
    if (compsRes.ok) {
      const data = await compsRes.json();
      STATE.catalog.composites = Array.isArray(data) ? data : (data.rows || []);
    }
    if (regRes && regRes.ok) {
      const data = await regRes.json();
      const rows = data.rows || [];
      STATE.catalog.dataCols = rows
        .filter(r => r.drv_cat_table && r.column_name && r.drv_cat_table !== "drv_cat_separator")
        .map(r => ({
          column_name:    r.column_name,
          drv_cat_table:  r.drv_cat_table,
          excel_header:   r.excel_header,
        }));
    }
  } catch (e) {
    showInfo(`Catalog load partial: ${e.message}`);
  }
}

/* ---------- load existing composite ---------- */

async function loadComposite() {
  showErr(null);
  try {
    const detailRes = await fetch(`/api/rules/composite/${encodeURIComponent(STATE.ruleId)}`);
    const atomicsRes = await fetch(`/api/rules/composite/${encodeURIComponent(STATE.ruleId)}/atomics`);
    if (!detailRes.ok) {
      showErr(`Composite ${STATE.ruleId} not found (HTTP ${detailRes.status})`);
      return;
    }
    const detail = await detailRes.json();
    STATE.category     = detail.category     || null;
    STATE.intent       = detail.intent_text  || null;
    STATE.precondition = detail.precondition_expr || null;
    STATE.active       = detail.active !== false;
    STATE.evidenceCutoff = detail.evidence_cutoff ?? null;

    const atomics = atomicsRes.ok ? await atomicsRes.json() : [];
    // Translate to member objects (atomic only — kind metadata isn't on the legacy GET)
    STATE.members = atomics.map(a => ({
      kind: "atomic",
      atomic_rule_id: a.atomic_rule_id,
      rule_name: a.rule_name,
      weight_override: a.weight_override,
      data_brkeout_from: a.data_brkeout_from ?? null,
      condition_operator: a.condition_operator ?? null,
      member_role: a.member_role || "gate",
      _base: { wt_below: a.wt_below, wt_between: a.wt_between, wt_above: a.wt_above },
    }));

    // Update header
    $("codeText").textContent = STATE.ruleId;
    const act = (STATE.ruleId.match(/(SA|STM|SS|BM|SW)/i) || ["—"])[0].toUpperCase();
    $("actBadge").textContent = act;
    $("actBadge").className = "ce-act " + act;
    const statusTag = STATE.active
      ? `<span style="color:#15803d;font-weight:600;font-size:12px">● Active</span>`
      : `<span style="color:#9ca3af;font-weight:600;font-size:12px">○ Disabled</span>`;
    $("metaText").innerHTML = `${STATE.members.length} members · ${statusTag} · <button class="btn-sm" onclick="toggleActive()" style="font-size:11px">${STATE.active ? 'Disable' : 'Enable'}</button>`;
    $("actSel").value     = act;
    $("catInput").value   = STATE.category || "";
    $("intentInput").value = STATE.intent  || "";
    $("preInput").value   = STATE.precondition || "";
    if ($("evidenceCutoffInput"))
      $("evidenceCutoffInput").value = STATE.evidenceCutoff == null ? "" : STATE.evidenceCutoff;
    document.title = `Composite ${STATE.ruleId} — Trading Dashboard`;

    renderMembers();
    runDryrun();
  } catch (e) {
    showErr(`Load failed: ${e.message}`);
  }
}

/* ---------- render member list ---------- */

function renderMembers() {
  const list = $("memberList");
  if (!STATE.members.length) {
    list.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-3); font-size: 12px;">No members yet — add one from the picker below.</div>`;
    updateRunningTotal();
    return;
  }
  list.innerHTML = STATE.members.map((m, idx) => memberRow(m, idx)).join("");
  // Wire X buttons
  list.querySelectorAll(".x").forEach(x => {
    x.addEventListener("click", () => {
      const idx = parseInt(x.dataset.idx, 10);
      STATE.members.splice(idx, 1);
      renderMembers();
    });
  });
  // Wire override inputs
  list.querySelectorAll("input.ovr-input").forEach(inp => {
    inp.addEventListener("input", () => {
      const idx = parseInt(inp.dataset.idx, 10);
      const v = inp.value.trim();
      STATE.members[idx].weight_override = v === "" ? null : parseFloat(v);
      updateRunningTotal();
    });
  });
  // Wire condition threshold inputs
  list.querySelectorAll("input.cond-thresh").forEach(inp => {
    inp.addEventListener("input", () => {
      const idx = parseInt(inp.dataset.idx, 10);
      const v = inp.value.trim();
      STATE.members[idx].data_brkeout_from = v === "" ? null : parseFloat(v);
    });
  });
  // Wire operator selects
  list.querySelectorAll("select.cond-op").forEach(sel => {
    sel.addEventListener("change", () => {
      const idx = parseInt(sel.dataset.idx, 10);
      STATE.members[idx].condition_operator = sel.value || null;
    });
  });
  // Wire gate/WATCH role selects
  list.querySelectorAll("select.mem-role").forEach(sel => {
    sel.addEventListener("change", () => {
      const idx = parseInt(sel.dataset.idx, 10);
      STATE.members[idx].member_role = sel.value || "gate";
      renderMembers();  // re-render to update the WATCH highlight
    });
  });
  // Wire data-member inline threshold inputs
  list.querySelectorAll("input.data-field").forEach(inp => {
    inp.addEventListener("input", () => {
      const idx = parseInt(inp.dataset.idx, 10);
      const field = inp.dataset.field;
      STATE.members[idx][field] = inp.value === "" ? null : parseFloat(inp.value);
      updateRunningTotal();
    });
  });
  $("memberMeta").textContent = `${STATE.members.length} members  ·  ${countByKind()}`;
  updateRunningTotal();
}

function countByKind() {
  const c = { atomic: 0, data: 0, composite: 0 };
  STATE.members.forEach(m => c[m.kind]++);
  return Object.entries(c).filter(([_, n]) => n).map(([k, n]) => `${n} ${k}`).join(" · ");
}

function memberRow(m, idx) {
  const kindBadge = `<span class="kind-badge ${m.kind}">${m.kind}</span>`;
  const x         = `<span class="x" data-idx="${idx}" title="Remove">×</span>`;
  const ovrField  = `<div class="ovr"><label>override</label>
    <input class="ovr-input" type="number" step="0.5" data-idx="${idx}"
      placeholder="—" value="${m.weight_override == null ? "" : m.weight_override}"></div>`;
  const role      = (m.member_role || "gate");
  const roleField = `<div class="ovr" style="min-width:78px"
      title="Gate = mandatory (strict AND). WATCH = corroborating evidence; does not block the fire.">
    <label>role</label>
    <select class="mem-role" data-idx="${idx}"
        style="font-size:12px;padding:2px 4px;${role==='watch'?'color:#92400e;font-weight:600':''}">
      <option value="gate"  ${role==='gate' ?'selected':''}>gate</option>
      <option value="watch" ${role==='watch'?'selected':''}>WATCH</option>
    </select></div>`;

  if (m.kind === "atomic") {
    const thresh  = m.data_brkeout_from;
    const selOp   = m.condition_operator || '';
    const noThreshWarn = thresh == null
      ? `<span title="No condition threshold set — any nonzero value qualifies"
              style="background:#fef3c7;color:#92400e;border:1px solid #fbbf24;border-radius:3px;
                     font-size:10px;font-weight:700;padding:1px 5px;margin-left:6px">⚠ no threshold</span>`
      : '';
    const opField = `<div class="ovr" style="min-width:72px">
      <label>operator</label>
      <select class="cond-op" data-idx="${idx}" style="font-family:monospace;font-size:13px;padding:2px 4px">
        <option value=""  ${selOp===''   ?'selected':''}>auto</option>
        <option value=">=" ${selOp==='>='?'selected':''}>&gt;=</option>
        <option value="<=" ${selOp==='<='?'selected':''}>&lt;=</option>
        <option value=">"  ${selOp==='>' ?'selected':''}>&gt;</option>
        <option value="<"  ${selOp==='<' ?'selected':''}>&lt;</option>
        <option value="="  ${selOp==='=' ?'selected':''}>=</option>
      </select>
    </div>`;
    const condField = `<div class="ovr" style="min-width:100px">
      <label>threshold</label>
      <input class="cond-thresh" type="number" step="1" data-idx="${idx}"
        placeholder="any≠0"
        value="${thresh == null ? '' : thresh}">
    </div>`;
    return `<div class="ce-mem" style="${thresh == null ? 'border-left:3px solid #fbbf24' : ''}">
      <span class="grip" title="Drag to reorder">⋮⋮</span>
      ${kindBadge}
      <div class="body">
        <div class="name">${escapeHtml(m.rule_name || "atomic#" + m.atomic_rule_id)}${noThreshWarn}</div>
      </div>
      ${opField}
      ${condField}
      ${roleField}
      ${ovrField}
      ${x}
    </div>`;
  }

  if (m.kind === "data") {
    return `<div class="ce-mem">
      <span class="grip">⋮⋮</span>
      ${kindBadge}
      <div class="body">
        <div class="name">${escapeHtml(m.data_column || "—")}</div>
        <div class="col">inline rule · mode=${escapeHtml(m.scoring_mode || "jump")}</div>
        <div class="inline-thresh">
          <span>lo</span><input class="data-field" data-idx="${idx}" data-field="brkeout_from" type="number" step="0.01" value="${m.brkeout_from ?? ""}">
          <span>hi</span><input class="data-field" data-idx="${idx}" data-field="brkeout_to"   type="number" step="0.01" value="${m.brkeout_to ?? ""}">
          <span>w&lt;</span><input class="data-field" data-idx="${idx}" data-field="wt_below"     type="number" step="0.5"  value="${m.wt_below ?? 0}">
          <span>w=</span><input class="data-field" data-idx="${idx}" data-field="wt_between"   type="number" step="0.5"  value="${m.wt_between ?? 0}">
          <span>w&gt;</span><input class="data-field" data-idx="${idx}" data-field="wt_above"     type="number" step="0.5"  value="${m.wt_above ?? 0}">
        </div>
      </div>
      ${roleField}
      ${ovrField}
      ${x}
    </div>`;
  }

  if (m.kind === "composite") {
    return `<div class="ce-mem">
      <span class="grip">⋮⋮</span>
      ${kindBadge}
      <div class="body">
        <div class="name">${escapeHtml(m.nested_composite_code)}</div>
        <div class="col">nested composite — score added to parent (× multiplier)</div>
      </div>
      ${roleField}
      ${ovrField}
      ${x}
    </div>`;
  }
  return "";
}

function updateRunningTotal() {
  // Each member's max contribution = max(|wt_below|, |wt_between|, |wt_above|)
  // (or override if set).
  let total = 0;
  STATE.members.forEach(m => {
    let maxAbs = 0;
    if (m.weight_override != null) {
      maxAbs = Math.abs(m.weight_override);
    } else if (m.kind === "atomic" && m._base) {
      maxAbs = Math.max(
        Math.abs(m._base.wt_below  || 0),
        Math.abs(m._base.wt_between|| 0),
        Math.abs(m._base.wt_above  || 0));
    } else if (m.kind === "data") {
      maxAbs = Math.max(
        Math.abs(m.wt_below  || 0),
        Math.abs(m.wt_between|| 0),
        Math.abs(m.wt_above  || 0));
    } else if (m.kind === "composite") {
      maxAbs = 1;   // unknown — leave conservative
    }
    total += maxAbs;
  });
  $("runningTotal").textContent = (total >= 0 ? "+" : "") + total;
}

/* ---------- add member handlers ---------- */

function addAtomicMember() {
  const name = $("atomicPicker").value.trim();
  const ovr  = $("atomicOverride").value.trim();
  const a = STATE.catalog.atomics.find(x => x.rule_name === name);
  if (!a) { showErr(`Atomic rule "${name}" not found`); return; }
  if (STATE.members.some(m => m.kind === "atomic" && m.atomic_rule_id === a.atomic_rule_id)) {
    showErr(`Atomic rule already in this composite`); return;
  }
  STATE.members.push({
    kind: "atomic",
    atomic_rule_id: a.atomic_rule_id,
    rule_name: a.rule_name,
    weight_override: ovr === "" ? null : parseFloat(ovr),
    // Pre-fill the condition threshold from the atomic rule's own definition so
    // the member doesn't degrade to "value ≠ 0". The user can still edit it.
    data_brkeout_from: a.brkeout_from ?? null,
    member_role: "gate",
    _base: { wt_below: a.wt_below, wt_between: a.wt_between, wt_above: a.wt_above },
  });
  $("atomicPicker").value = ""; $("atomicOverride").value = "";
  renderMembers(); showErr(null);
}

function addDataMember() {
  const colKey = $("dataPicker").value.trim();
  if (!colKey) { showErr("Pick a data column"); return; }
  // colKey shape: "drv_cat_atomic_input.bb_top" or just "bb_top"
  const dataColumn = colKey.includes(".") ? colKey : "drv_cat_atomic_input." + colKey;
  if (STATE.members.some(m => m.kind === "data" && m.data_column === dataColumn)) {
    showErr(`Data column already added`); return;
  }
  STATE.members.push({
    kind: "data",
    data_column: dataColumn,
    brkeout_from: parseFloat($("dataLo").value || 0),
    brkeout_to:   parseFloat($("dataHi").value || 0),
    wt_below:     parseFloat($("dataWb").value || 0),
    wt_between:   parseFloat($("dataWbt").value || 0),
    wt_above:     parseFloat($("dataWa").value || 0),
    scoring_mode: $("dataMode").value || "jump",
    weight_override: null,
  });
  $("dataPicker").value = "";
  renderMembers(); showErr(null);
}

function addCompositeMember() {
  const code = $("compPicker").value.trim();
  const mult = $("compMult").value.trim();
  if (!code) { showErr("Pick a composite"); return; }
  if (code === STATE.ruleId) { showErr("Composite can't reference itself"); return; }
  if (STATE.members.some(m => m.kind === "composite" && m.nested_composite_code === code)) {
    showErr(`Composite already nested`); return;
  }
  STATE.members.push({
    kind: "composite",
    nested_composite_code: code,
    weight_override: mult === "" ? null : parseFloat(mult),
  });
  $("compPicker").value = ""; $("compMult").value = "";
  renderMembers(); showErr(null);
}

/* ---------- typeahead helper ---------- */

function setupTypeahead(inputId, suggestId, getCorpus, render, value) {
  const input = $(inputId);
  const drop  = $(suggestId);
  let blurTimer = null;

  function refresh() {
    const q = input.value.toLowerCase().trim();
    if (q.length < 1) { drop.classList.remove("open"); return; }
    const corpus = getCorpus();
    const matches = corpus.filter(item => {
      const v = value(item).toLowerCase();
      return v.includes(q);
    }).slice(0, 30);
    if (!matches.length) { drop.classList.remove("open"); return; }
    drop.innerHTML = matches.map(item => {
      const v = value(item);
      return `<div class="item" data-value="${escapeAttr(v)}">${render(item)}</div>`;
    }).join("");
    drop.classList.add("open");
    drop.querySelectorAll(".item").forEach(el => {
      el.addEventListener("mousedown", e => {
        e.preventDefault();
        input.value = el.dataset.value;
        drop.classList.remove("open");
      });
    });
  }
  input.addEventListener("input", refresh);
  input.addEventListener("focus", refresh);
  input.addEventListener("blur", () => {
    blurTimer = setTimeout(() => drop.classList.remove("open"), 150);
  });
}

/* ---------- save ---------- */

async function cloneComposite() {
  if (!STATE.ruleId) { showErr("Load a composite first"); return; }
  const newCode = (prompt(`Clone "${STATE.ruleId}" to a new composite code:`, STATE.ruleId + "-copy") || "").trim();
  if (!newCode) return;
  try {
    const r = await fetch(`/api/rules/composite/${encodeURIComponent(STATE.ruleId)}/clone`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_code: newCode }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const out = await r.json();
    showInfo(`Cloned to ${out.new_code} (${out.members} members). Opening…`);
    setTimeout(() => { location.href = `/composite-edit?id=${encodeURIComponent(out.new_code)}`; }, 600);
  } catch (e) {
    showErr(`Clone failed: ${e.message}`);
  }
}

async function saveComposite() {
  if (!STATE.ruleId) { showErr("Load a composite first"); return; }
  const _ecut = $("evidenceCutoffInput") ? $("evidenceCutoffInput").value.trim() : "";
  const body = {
    members: STATE.members.map(m => stripInternal(m)),
    category:          $("catInput").value || null,
    intent_text:       $("intentInput").value || null,
    precondition_expr: $("preInput").value || null,
    evidence_cutoff:   _ecut === "" ? null : parseFloat(_ecut),
  };
  $("saveBtn").disabled = true;
  try {
    const r = await fetch(`/api/rules/composite/${encodeURIComponent(STATE.ruleId)}/members`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const out = await r.json();
    showInfo(`Saved · ${out.members_written} members written` +
             (out.warnings && out.warnings.length ? ` · ${out.warnings.length} warning(s)` : "") +
             (out.schema_extended ? "" : " (legacy schema — apply db/19_composite_member_kinds.sql for full kinds)"));
    await loadComposite();
  } catch (e) {
    showErr(`Save failed: ${e.message}`);
  } finally {
    $("saveBtn").disabled = false;
  }
}

function stripInternal(m) {
  const out = {};
  for (const k of Object.keys(m)) {
    if (k.startsWith("_")) continue;
    out[k] = m[k];
  }
  return out;
}

/* ---------- active toggle ---------- */

async function toggleActive() {
  if (!STATE.ruleId) return;
  const newActive = !STATE.active;
  try {
    const r = await fetch(`/api/rules/composite/${encodeURIComponent(STATE.ruleId)}/active`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: newActive }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    STATE.active = newActive;
    // Refresh the header status badge
    const statusTag = STATE.active
      ? `<span style="color:#15803d;font-weight:600;font-size:12px">● Active</span>`
      : `<span style="color:#9ca3af;font-weight:600;font-size:12px">○ Disabled</span>`;
    $("metaText").innerHTML = `${STATE.members.length} members · ${statusTag} · <button class="btn-sm" onclick="toggleActive()" style="font-size:11px">${STATE.active ? 'Disable' : 'Enable'}</button>`;
  } catch (e) {
    alert(`Toggle failed: ${e.message}`);
  }
}

/* ---------- deprecate ---------- */

async function deprecateComposite() {
  if (!STATE.ruleId) return;
  if (!confirm(`Deprecate composite "${STATE.ruleId}"? Sets deprecated_at = now() (soft delete).`)) return;
  try {
    const r = await fetch(`/api/rules/composite/${encodeURIComponent(STATE.ruleId)}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    showInfo("Deprecated. Returning to /rules in 2s…");
    setTimeout(() => location.href = "/rules", 2000);
  } catch (e) {
    showErr(`Deprecate failed: ${e.message}`);
  }
}

/* ---------- dry-run ---------- */

async function runDryrun() {
  if (!STATE.ruleId) return;
  $("dryrunSpinner").style.display = "inline";
  $("dryrunResult").innerHTML = "";
  try {
    const sym = ($("sampleSym").value || "AAPL").trim().toUpperCase();
    const body = {
      members: STATE.members.map(m => stripInternal(m)),
      precondition_expr: $("preInput").value || null,
      sample_symbol: sym,
    };
    const r = await fetch(`/api/rules/composite/${encodeURIComponent(STATE.ruleId)}/dryrun`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const out = await r.json();
    renderDryrun(out);
  } catch (e) {
    $("dryrunResult").innerHTML = `<div style="color:#791F1F; margin-top:6px">Dry-run failed: ${escapeHtml(e.message)}</div>`;
  } finally {
    $("dryrunSpinner").style.display = "none";
  }
}

function renderDryrun(out) {
  const before = out.before || {};
  const after  = out.after  || {};
  const bk     = after.by_kind || { atomic: 0, data: 0, composite: 0 };
  const beforeStr = before.score == null ? "—" : signed(before.score);
  const afterStr  = after.score  == null ? "skipped (precondition false)" : signed(after.score);
  const kindHtml = `
    <span><code>atomic</code> ${signed(bk.atomic)}</span>
    <span><code>data</code> ${signed(bk.data)}</span>
    <span><code>composite</code> ${signed(bk.composite)}</span>
  `;
  $("dryrunResult").innerHTML = `
    <div class="row" style="margin-top: 10px">
      <div class="stat"><span class="v">${escapeHtml(out.sample_symbol)}</span><span class="lbl">symbol · ${out.as_of_date}</span></div>
      <div class="stat"><span class="v">${escapeHtml(beforeStr)}</span><span class="lbl">score before</span></div>
      <div class="stat"><span class="v">${escapeHtml(afterStr)}</span><span class="lbl">score after edit</span></div>
      <div class="stat"><span class="v">${out.affected_symbols_estimate ?? "—"}</span><span class="lbl">symbols fired this composite (today)</span></div>
    </div>
    <div class="by-kind">${kindHtml}</div>
    <div class="note">${escapeHtml(out.note || "")}</div>
  `;
}

function signed(n) {
  if (n == null || !isFinite(n)) return "—";
  if (n === 0) return "0";
  const r = Math.abs(n) < 100 ? n.toFixed(2).replace(/\.?0+$/, "") : Math.round(n);
  return (n > 0 ? "+" : "") + r;
}

/* ---------- helpers ---------- */

function showErr(msg) {
  const el = $("errBanner");
  if (msg == null) { el.style.display = "none"; el.textContent = ""; return; }
  el.textContent = msg; el.style.display = "block";
}
function showInfo(msg) {
  const el = $("infoBanner");
  el.textContent = msg; el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 5000);
}
// escapeHtml is provided by _common.js (window.escapeHtml).
function escapeAttr(s) { return escapeHtml(s); }
function snakeName(s) {
  return String(s || "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}
