/* Actionable Stocks page logic */

const state = {
  date: null,
  allRows: [],   // full unfiltered dataset for the date
  baseRows: [],  // passes every filter except the action chip (drives chip counts)
  rows: [],      // filtered subset shown in grid
  sort: { key: '_priority', dir: -1, type: 'num' },  // default: priority DESC
  filters: {
    action: '',          // '' | REMOVE | REDUCE | INCREASE | ADD | HOLD
    source: '',
    account: '',
    held_only: false,
    show_hidden: false,  // when true, reveals suppressed/$0/no-action/acted/unheld-remove rows
    symbol_search: '',   // symbol search text filter
    conviction: 'any',   // 'any' | 'multi' | 'proven'
    actionable_only: true, // hides HOLD and NONE rows by default
    bull_prob_min: 0,    // TASK_66: minimum bull_prob (0 = no filter)
    agreement_class: '', // TASK_69: '' = all; else exact match on agreement_class
  },
  current: null,
  sourceMethods: {},   // source_code -> base_weight_method (Metric-column sort)
  buysellSeq: {},      // buysell code -> seq from ref_param_lookup (priority sort)
  agreementScorecard: null, // TASK_69: {agreement_class -> avg_fwd_20d} cache
  quadFactors: null,        // cached from /api/quad/band-factors for MACRO tooltip
  quadData: null,           // cached from /api/dashboard/quads (period dates for dtb)
  allAccounts: [],          // [{account_number, display_name, short_name, custom_name}] from /api/actionable/accounts
  // Pass 2: top-N collapse
  showAll: false,
  TOP_N: 15,
  // Pass 3: bulk select
  selected: new Set(),
  // Pass 3: focus mode
  focusIdx: 0,
};

const $ = (id) => document.getElementById(id);

// fetchJson is provided by _common.js (window.fetchJson).

function fmtUsd(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!isFinite(n)) return '';
  if (Math.abs(n) >= 1000) return '$' + (Math.round(n)).toLocaleString();
  return '$' + n.toFixed(0);
}
// Compact currency: $38k, $1.2m, $500 — for Pos $ column
function fmtCompact(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!isFinite(n) || n === 0) return '';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e6) return sign + '$' + (abs / 1e6).toFixed(1).replace(/\.0$/, '') + 'm';
  if (abs >= 1e3) return sign + '$' + Math.round(abs / 1e3) + 'k';
  return sign + '$' + Math.round(abs);
}
function fmtDate(d) {
  if (!d) return '—';
  return d.toString().slice(0, 10);
}
function fmtDateMD(d) {
  if (!d) return '—';
  const s = d.toString().slice(0, 10); // YYYY-MM-DD
  return s.slice(5, 7) + '/' + s.slice(8, 10);
}

// ---------- Side panel helpers + MACRO band (TASK_74) ----------

function _normSignal(v) {
  if (!v) return { cls: '', label: '' };
  const u = String(v).trim().toUpperCase();
  if (u === '0' || u === 'N' || u === 'NEUTRAL' || u === 'NEU') return { cls: 'NEUTRAL', label: 'NEUTRAL' };
  if (u.startsWith('BULL') || u === '+' || u === 'POS' || u === 'POSITIVE' || u === 'UP') return { cls: 'BULLISH', label: 'BULLISH' };
  if (u.startsWith('BEAR') || u === '-' || u === 'NEG' || u === 'NEGATIVE' || u === 'DN' || u === 'DOWN') return { cls: 'BEARISH', label: 'BEARISH' };
  return { cls: u.replace(/[^A-Z0-9]/g, ''), label: String(v).trim() };
}

// ── MACRO column cell renderer (TASK_74) ────────────────────────────────────
// Renders a single cell for the MACRO column using the existing actionDisplay()
// colors/vocabulary. The turn arrow (↗/↘ + next quad/%) is appended when present.
// Confidence cue: faded badge at < 60% confidence.
// On hover, a tooltip shows the full MacroNet breakdown from macro_detail.
function macroCellHtml(r) {
  const mv = r.macro_value;
  const turn = r.macro_turn || '';
  const conf = r.macro_conf != null ? r.macro_conf : null;
  const opacity = conf != null && conf < 0.6 ? Math.max(0.45, conf / 0.6) : 1.0;
  const sym = r.tos_symbol || '';
  // Three-period alignment: cur-month / next-month / cur-quarter
  const _dot = (net, title) => {
    if (net == null) return `<span style="color:#d1d5db;font-size:7px;" title="${title}">—</span>`;
    const n = Number(net);
    const col = n > 0 ? '#16a34a' : n < 0 ? '#dc2626' : '#9ca3af';
    const g   = n > 0 ? '▲' : n < 0 ? '▼' : '—';
    return `<span style="color:${col};font-size:7px;" title="${title}: ${n > 0 ? '+' : ''}${n.toFixed(2)}">${g}</span>`;
  };
  const _dotQ = (net, title) => {
    if (net == null) return `<span style="color:#d1d5db;font-size:7px;" title="${title}">—</span>`;
    const n = Number(net);
    const col = n > 0 ? '#16a34a' : n < 0 ? '#dc2626' : '#9ca3af';
    const g   = n > 0 ? '↑' : n < 0 ? '↓' : '—';
    return `<span style="color:${col};font-size:7px;" title="${title}: ${n > 0 ? '+' : ''}${n.toFixed(2)}">${g}</span>`;
  };
  const hasDots = r.month_now_net != null || r.month_next_net != null || r.qtr_now_net != null;
  const dotsLine = hasDots
    ? `<div style="display:flex;justify-content:center;gap:4px;line-height:1;margin-top:2px;">`
      + _dot(r.month_now_net,  'Cur month')
      + _dot(r.month_next_net, 'Nxt month')
      + _dotQ(r.qtr_now_net,   'Cur quarter')
      + `</div>`
    : '';
  // Sparkline: one bar per available month, height ∝ |score|, color = direction
  const _sparksRaw = r.monthly_scores_json;
  const _sparks = Array.isArray(_sparksRaw) ? _sparksRaw
    : (typeof _sparksRaw === 'string'
        ? (() => { try { return JSON.parse(_sparksRaw); } catch(_e) { return null; } })()
        : null);
  let sparkLine = '';
  const _curIdx = _sparks ? _sparks.findIndex(s => s.is_current) : -1;
  const _sparksVis = _sparks && _curIdx >= 0 ? _sparks.slice(_curIdx) : _sparks;
  if (_sparksVis && _sparksVis.length >= 2) {
    const maxAbs = Math.max(..._sparksVis.map(s => Math.abs(s.score || 0)), 0.001);
    const bars = _sparksVis.map(s => {
      const sc  = s.score || 0;
      const bh  = Math.max(2, Math.round(Math.abs(sc) / maxAbs * 8));
      const col = sc > 0 ? '#16a34a' : sc < 0 ? '#dc2626' : '#9ca3af';
      const bw  = s.is_current ? '3' : '2';
      const bdr = s.is_current ? 'border:1px solid #475569;box-sizing:border-box;' : '';
      const ti  = `${s.label || ''} (${s.quad || ''}) ${sc >= 0 ? '+' : ''}${sc.toFixed(2)}`;
      return `<span title="${escapeHtml(ti)}" style="display:inline-block;width:${bw}px;height:${bh}px;background:${col};vertical-align:bottom;${bdr}"></span>`;
    }).join('<span style="display:inline-block;width:1px;"></span>');
    sparkLine = `<div data-scorespop="${escapeHtml(sym)}" style="display:flex;justify-content:center;align-items:flex-end;gap:1px;height:9px;margin-top:1px;cursor:help;">${bars}</div>`;
  }
  if (!mv || mv === 'HOLD') {
    const holdCls = mv ? 'color:#9ca3af' : 'color:#cbd5e1';
    const lbl = mv ? 'HOLD' : '—';
    return `<div style="${holdCls};font-size:10px;opacity:${opacity.toFixed(2)};cursor:help;text-align:center;" data-macropop="${escapeHtml(sym)}">${escapeHtml(lbl)}${dotsLine}${sparkLine}</div>`;
  }
  const d = actionDisplay(mv);
  const cls = d.colorCls || 'act-neutral';
  return `<div style="text-align:center;cursor:help;opacity:${opacity.toFixed(2)};" data-macropop="${escapeHtml(sym)}">`
       + `<span class="act-badge ${cls}-tint" style="font-size:10px;padding:1px 5px;">${escapeHtml(d.code || mv)}</span>`
       + dotsLine
       + sparkLine
       + `</div>`;
}

// Build tooltip text for a MACRO cell from macro_detail + macro_howto.
// Layout: How to act → Month distribution + Category/Subcategory drivers
//         → Quarter → MacroNet
function _macroTooltip(r) {
  let det = r.macro_detail;
  if (typeof det === 'string') { try { det = JSON.parse(det); } catch (_) { det = null; } }
  if (!det) return r.macro_value ? `MacroNet → ${r.macro_value}` : '';
  const lines = [];

  // ── How to act ────────────────────────────────────────────────────────────
  if (r.macro_howto) {
    lines.push('HOW TO ACT');
    lines.push(r.macro_howto);
    lines.push('');
  }

  // ── Month distribution ────────────────────────────────────────────────────
  const mo = det.month || {};
  const moNow = mo.now || {};
  const moNxt = mo.next;
  const distNow = moNow.dist || [];
  lines.push('MONTH');
  if (moNow.quad) {
    const distStr = distNow.length
      ? distNow.map(x => `${x.quad} ${x.pct}%`).join(' · ')
      : `${moNow.quad} (no dist)`;
    lines.push(`  Now (${moNow.quad}): ${distStr}  [dtb ${moNow.dtb}d, net=${moNow.net}]`);
  }
  if (moNxt && moNxt.quad) {
    const distNxtArr = moNxt.dist || [];
    const distNxtStr = distNxtArr.length
      ? distNxtArr.map(x => `${x.quad} ${x.pct}%`).join(' · ')
      : `${moNxt.quad}`;
    lines.push(`  Next (${moNxt.quad}): ${distNxtStr}  [net=${moNxt.net}]`);
    lines.push(`  Blend: now ${mo.blend_now_pct}% / next ${mo.blend_nxt_pct}%  →  M=${mo.M}`);
  } else {
    lines.push(`  M=${mo.M}`);
  }

  // ── Category / Subcategory / Outlook drivers ──────────────────────────────
  const mems = det.memberships || [];
  if (mems.length) {
    lines.push('');
    lines.push('CATEGORY DRIVERS');
    mems.forEach(m => {
      const st = m.stance > 0 ? '+1' : m.stance < 0 ? '-1' : ' 0';
      const cat = m.category ? `${m.category} / ${m.sub_cat || m.label}` : m.label;
      lines.push(`  ${cat}  (×${m.weight})  →  ${m.outlook || '—'} [${st}]`);
    });
  }

  // ── Quarter ────────────────────────────────────────────────────────────────
  const qtr = det.quarter || {};
  if (qtr.now) {
    lines.push('');
    lines.push('QUARTER (fixed top-level anchor, no blend)');
    const qtrLine = `  ${qtr.now}  →  Qtr=${qtr.Qtr}`;
    const dtbStr = qtr.dtb != null ? `  (${qtr.dtb}d left)` : '';
    lines.push(qtrLine + dtbStr);
    if (qtr.next && qtr.turn_alert) {
      lines.push(`  → ${qtr.next} next quarter (near-end alert)`);
    }
  }

  // ── MacroNet ──────────────────────────────────────────────────────────────
  lines.push('');
  lines.push(`MacroNet = ${det.a}×Qtr(${det.quarter?.Qtr ?? '?'}) + ${det.b}×M(${det.month?.M ?? '?'}) = ${det.macro_net}  →  ${det.vocab}`);
  if (det.conf != null) {
    lines.push(`Confidence: ${Math.round(det.conf * 100)}%`);
  }

  // ── Turn ──────────────────────────────────────────────────────────────────
  if (r.macro_turn) {
    lines.push(`Turn signal: ${r.macro_turn}`);
  }

  return lines.join('\n');
}

// Rich HTML popover for a MACRO cell — reuses #sourcePop / _showDataPop.
function _buildMacroPopHtml(r) {
  let det = r.macro_detail;
  if (typeof det === 'string') { try { det = JSON.parse(det); } catch (_) { det = null; } }
  const mv   = r.macro_value || '—';
  const conf = r.macro_conf != null ? Math.round(r.macro_conf * 100) : null;
  const turn = r.macro_turn || null;
  const sym  = r.tos_symbol || '—';

  const _quadDistBar = dist => {
    if (!dist || !dist.length) return '';
    const segs = dist.map(x =>
      `<div style="width:${x.pct}%;background:${_quadColor(x.quad)};height:100%;" title="${escapeHtml(x.quad)} ${x.pct}%"></div>`
    ).join('');
    return `<div style="display:inline-flex;width:110px;height:7px;border-radius:3px;overflow:hidden;border:1px solid #e2e8f0;vertical-align:middle;margin-right:6px;">${segs}</div>`;
  };
  const _quadDistBreakdown = dist =>
    (dist || []).map(x =>
      `<span style="color:${_quadColor(x.quad)};font-weight:600;">${escapeHtml(x.quad)}</span> ${x.pct}%`
    ).join(' &nbsp;·&nbsp; ');

  const _vocabColor = v => {
    if (!v) return '#9ca3af';
    const u = v.toUpperCase();
    if (u === 'SA')  return '#991b1b';
    if (u === 'STM') return '#ef4444';
    if (u === 'BS')  return '#22c55e';
    if (u === 'BM')  return '#14532d';
    return '#9ca3af';
  };
  const _sigColor     = v => v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#9ca3af';
  const _coloredQuad  = q => q ? `<span style="color:${_quadColor(q)};font-weight:600;">${escapeHtml(q)}</span>` : '—';
  const _coloredVocab = v => v ? `<span style="color:${_vocabColor(v)};font-weight:700;">${escapeHtml(v)}</span>` : '—';

  const mvColor = _vocabColor(mv !== '—' ? mv : null);
  let h = `<div class="sp-title">${escapeHtml(sym)} &mdash; <span style="color:${mvColor};font-weight:700;">${escapeHtml(mv)}</span>${turn ? ' <span style="color:#f97316;">' + escapeHtml(turn) + '</span>' : ''}</div>`;

  if (!det) {
    h += `<div style="color:#94a3b8;font-size:10px;">No detail available.</div>`;
    return h;
  }

  const mems  = det.memberships || [];
  const mo    = det.month || {};
  const moNow = mo.now || {};
  const moNxt = mo.next;
  const qtr   = det.quarter || {};

  const _qfMap = {};
  if (state.quadFactors && state.quadFactors.factors) {
    for (const f of state.quadFactors.factors)
      _qfMap[`${f.category}|${(f.factor || '').toLowerCase()}`] = f;
  }
  const _qds  = (state.quadFactors || {}).quads || {};
  const cmQuad = _qds.cur_month  || moNow.quad;
  const nmQuad = _qds.next_month || (moNxt && moNxt.quad);
  const qQuad  = qtr.quad_label || _qds.cur_qtr || qtr.now;
  const cmDtb  = moNow.dtb;
  const qDtb   = qtr.dtb;

  const hasDeriveTime = r.macronet != null && r.monthly_score != null;
  let mBlendHtml = null, qBlendHtml = null, macroFormulaHtml;
  if (hasDeriveTime) {
    const Mv    = Number(r.monthly_score);
    const Qv    = Number(r.quarterly_score ?? 0);
    const net   = Number(r.macronet);
    const wMo   = det.b ?? 0.65, wQtr = det.a ?? 0.35;
    const mo_w  = r.month_weight != null ? Number(r.month_weight) : 0;
    const qtr_w = r.qtr_weight   != null ? Number(r.qtr_weight)   : 0;
    const moNow = r.month_now_net  != null ? Number(r.month_now_net)  : null;
    const moNxt = r.month_next_net != null ? Number(r.month_next_net) : null;
    const qNow  = r.qtr_now_net   != null ? Number(r.qtr_now_net)   : null;
    const qNxt  = r.qtr_next_net  != null ? Number(r.qtr_next_net)  : null;
    const _sv = v => v != null
      ? `<span style="color:${_sigColor(v)};font-weight:600;">${v >= 0 ? '+' : ''}${v.toFixed(2)}</span>`
      : '?';
    const _wLabel = (w, rB, lD) => {
      const den = rB - lD;
      if (w > 0.005 && w < 0.995) {
        const days = Math.round(rB - w * den);
        return `clamp((${rB}&#8722;${days})/${den},0,1)=${w.toFixed(2)}`;
      }
      return w.toFixed(2);
    };
    if (moNow != null) {
      const w1m = mo_w.toFixed(2);
      const bM = moNxt != null
        ? `(1&#8722;${w1m})&#xB7;cur(${_sv(moNow)}) + ${w1m}&#xB7;nxt(${_sv(moNxt)})`
        : `1.00&#xB7;cur(${_sv(moNow)})`;
      mBlendHtml = `w=${_wLabel(mo_w, 12, 5)} &nbsp;&#8594;&nbsp; ${bM}`
                 + ` = <span style="color:${_sigColor(Mv)};font-weight:700;">${Mv >= 0 ? '+' : ''}${Mv.toFixed(2)}</span>`;
    }
    if (qNow != null) {
      const w1q = qtr_w.toFixed(2);
      const bQ = qNxt != null
        ? `(1&#8722;${w1q})&#xB7;cur(${_sv(qNow)}) + ${w1q}&#xB7;nxt(${_sv(qNxt)})`
        : `1.00&#xB7;cur(${_sv(qNow)})`;
      qBlendHtml = `w=${_wLabel(qtr_w, 20, 10)} &nbsp;&#8594;&nbsp; ${bQ}`
                 + ` = <span style="color:${_sigColor(Qv)};font-weight:700;">${Qv >= 0 ? '+' : ''}${Qv.toFixed(2)}</span>`;
    }
    macroFormulaHtml =
      `${wMo}×M(<span style="color:${_sigColor(Mv)};font-weight:600;">${Mv >= 0 ? '+' : ''}${Mv.toFixed(3)}</span>) `
      + `+ ${wQtr}×Q(<span style="color:${_sigColor(Qv)};font-weight:600;">${Qv >= 0 ? '+' : ''}${Qv.toFixed(3)}</span>) `
      + `= <span style="color:${_sigColor(net)};font-weight:700;">${net.toFixed(4)}</span>`;
  } else {
    const netVal = det.macro_net != null ? Number(det.macro_net) : null;
    const qV = det.quarter?.Qtr ?? '?', mV = det.month?.M ?? '?';
    macroFormulaHtml =
      `${det.a}×Qtr(<span style="color:${_sigColor(Number(qV))}">${qV}</span>) `
      + `+ ${det.b}×M(<span style="color:${_sigColor(Number(mV))}">${mV}</span>) `
      + `= <span style="color:${netVal != null ? _sigColor(netVal) : '#475569'};font-weight:700;">${netVal ?? '?'}</span>`;
  }

  h += '<table>';
  const _card = (label, quad, net, dtbLabel) => {
    const hasNet = net != null;
    const n = hasNet ? Number(net) : null;
    const gCol  = !hasNet ? '#d1d5db' : n > 0 ? '#16a34a' : n < 0 ? '#dc2626' : '#9ca3af';
    const glyph = !hasNet ? '—' : n > 0 ? '▲' : n < 0 ? '▼' : '—';
    const netLbl = hasNet ? `<div style="font-size:8px;color:${gCol};font-weight:600;">${n > 0 ? '+' : ''}${n.toFixed(2)}</div>` : '';
    const qLbl  = quad ? `<div style="color:${_quadColor(quad)};font-weight:700;font-size:9px;white-space:nowrap;">${escapeHtml(quad)}</div>` : '';
    return `<td style="text-align:center;padding:4px 6px;border-right:1px solid #e2e8f0;vertical-align:top;">`
         + `<div style="font-size:8px;color:#94a3b8;margin-bottom:2px;">${escapeHtml(label)}</div>`
         + qLbl
         + `<div style="font-size:13px;color:${gCol};line-height:1.2;">${glyph}</div>`
         + netLbl
         + (dtbLabel ? `<div style="font-size:8px;color:#94a3b8;">${escapeHtml(dtbLabel)}</div>` : '')
         + `</td>`;
  };
  h += `<tr><td colspan="2" style="padding:4px 0 6px;">`
     + `<table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:4px;"><tr>`
     + _card('Cur Month', cmQuad, r.month_now_net,  cmDtb != null ? `${cmDtb}d left` : null)
     + _card('Nxt Month', nmQuad, r.month_next_net, cmDtb != null ? `in ${cmDtb}d`   : null)
     + `<td style="text-align:center;padding:4px 6px;vertical-align:top;">`
     + `<div style="font-size:8px;color:#94a3b8;margin-bottom:2px;">Quarter</div>`
     + (qQuad ? `<div style="color:${_quadColor(qQuad)};font-weight:700;font-size:9px;">${escapeHtml(qQuad)}</div>` : '')
     + (() => { const n = r.qtr_now_net != null ? Number(r.qtr_now_net) : null;
                const gc = n == null ? '#d1d5db' : n > 0 ? '#16a34a' : n < 0 ? '#dc2626' : '#9ca3af';
                const g  = n == null ? '—' : n > 0 ? '▲' : n < 0 ? '▼' : '—';
                const nl = n != null ? `<div style="font-size:8px;color:${gc};font-weight:600;">${n > 0 ? '+' : ''}${n.toFixed(2)}</div>` : '';
                return `<div style="font-size:13px;color:${gc};line-height:1.2;">${g}</div>${nl}`; })()
     + (qDtb != null ? `<div style="font-size:8px;color:#94a3b8;">${qDtb}d left</div>` : '')
     + `</td>`
     + `</tr></table></td></tr>`;

  if (mBlendHtml) h += `<tr><td class="k" style="font-size:9px;color:#64748b;">M (monthly)</td><td class="v" style="font-size:9px;">${mBlendHtml}</td></tr>`;
  if (qBlendHtml) h += `<tr><td class="k" style="font-size:9px;color:#64748b;">Q (quarter)</td><td class="v" style="font-size:9px;">${qBlendHtml}</td></tr>`;
  h += `<tr><td class="k">MacroNet</td><td class="v" style="font-size:9px;">${macroFormulaHtml} → ${_coloredVocab(mv)}</td></tr>`;
  if (conf != null) {
    const confNum = r.macro_conf != null ? Number(r.macro_conf) : 0;
    const confColor = confNum >= 0.7 ? '#16a34a' : confNum >= 0.4 ? '#d97706' : '#dc2626';
    h += `<tr><td class="k">Confidence</td><td class="v" style="color:${confColor};font-weight:700;">${conf}%</td></tr>`;
  }
  if (turn) h += `<tr><td class="k">Turn signal</td><td class="v" style="color:#f97316;font-weight:700;">${escapeHtml(turn)}</td></tr>`;

  if (r.macro_howto) {
    const howtoTrimmed = r.macro_howto.replace(/\s*Technical\/Sources.*$/i, '').trim();
    if (howtoTrimmed) {
      h += `<tr><td class="sp-sec" colspan="2">How to Act</td></tr>`;
      h += `<tr><td colspan="2" style="font-size:10px;color:#374151;padding:2px 0 5px;">${escapeHtml(howtoTrimmed)}</td></tr>`;
    }
  }

  if (mems.length) {
    const _stOf  = v => { const u = (v || '').toUpperCase(); return u === 'BULLISH' ? 1 : u === 'BEARISH' ? -1 : 0; };
    const _ocOf  = v => { const u = (v || '').toUpperCase(); return u === 'BULLISH' ? '#1c6c30' : u === 'BEARISH' ? '#8c1d1d' : u ? '#5b4900' : '#9ca3af'; };
    const _olLbl = v => { if (!v) return '—'; const u = v.toUpperCase(); return u === 'BULLISH' ? 'Bullish' : u === 'BEARISH' ? 'Bearish' : v; };

    const _memberBlock = qfKey => {
      let score = 0, rows = '';
      for (const m of mems) {
        const qf = _qfMap[`${m.category}|${(m.sub_cat || m.label || '').toLowerCase()}`];
        let ol;
        if (qfKey === 'cur_qtr')     ol = m.qtr_outlook ?? (qf ? qf[qfKey] : null);
        else if (qfKey === 'next_month') ol = m.nxt_outlook ?? (qf ? qf[qfKey] : null);
        else ol = qf ? qf[qfKey] : (qfKey === 'cur_month' ? m.outlook : null);
        const st = _stOf(ol);
        score += st * (m.weight || 1);
        const stSym   = st > 0 ? '▲' : st < 0 ? '▼' : '→';
        const stColor = st > 0 ? '#16a34a' : st < 0 ? '#dc2626' : '#9ca3af';
        const cat = m.category
          ? `${escapeHtml(m.category)} / ${escapeHtml(m.sub_cat || m.label || '')}`
          : escapeHtml(m.label || '');
        rows += `<tr><td class="k" style="font-size:9px;max-width:140px;white-space:normal;word-break:break-word;">${cat}</td>`
              + `<td class="v" style="font-size:9px;white-space:nowrap;">`
              + `<span style="color:${stColor}">${stSym}</span> `
              + `<span style="color:${_ocOf(ol)};font-weight:600;">${escapeHtml(_olLbl(ol))}</span>`
              + ` <span style="color:#94a3b8;">(×${m.weight})</span></td></tr>`;
      }
      const scColor = score > 0 ? '#16a34a' : score < 0 ? '#dc2626' : '#9ca3af';
      rows += `<tr><td class="k" style="font-size:9px;color:#475569;">Score</td>`
            + `<td class="v" style="color:${scColor};font-weight:700;font-size:11px;">${score > 0 ? '+' : ''}${score.toFixed(1)}</td></tr>`;
      return rows;
    };

    const _secHdr = (title, quad, dtbLabel) => {
      const qLbl = quad ? ` <span style="color:${_quadColor(quad)};font-size:9px;font-weight:400;">${escapeHtml(quad)}</span>` : '';
      const dLbl = dtbLabel ? ` <span style="color:#94a3b8;font-size:9px;">${escapeHtml(dtbLabel)}</span>` : '';
      return `<tr><td class="sp-sec" colspan="2">${escapeHtml(title)}${qLbl}${dLbl}</td></tr>`;
    };

    h += _secHdr('Current Month', cmQuad, cmDtb != null ? `(${cmDtb}d left)` : null);
    if (moNow.dist && moNow.dist.length)
      h += `<tr><td colspan="2" style="padding:2px 0 4px;">${_quadDistBar(moNow.dist)}<span style="font-size:9px;color:#475569;">${_quadDistBreakdown(moNow.dist)}</span></td></tr>`;
    h += _memberBlock('cur_month');

    h += _secHdr('Next Month', nmQuad, cmDtb != null ? `(in ${cmDtb}d)` : null);
    if (moNxt && moNxt.dist && moNxt.dist.length)
      h += `<tr><td colspan="2" style="padding:2px 0 4px;">${_quadDistBar(moNxt.dist)}<span style="font-size:9px;color:#475569;">${_quadDistBreakdown(moNxt.dist)}</span></td></tr>`;
    h += _memberBlock('next_month');

    h += _secHdr('Quarter', qQuad, qDtb != null ? `(${qDtb}d left)` : null);
    if (qQuad) {
      const qDist = [{ quad: qQuad, pct: 100 }];
      h += `<tr><td colspan="2" style="padding:2px 0 4px;">${_quadDistBar(qDist)}<span style="font-size:9px;color:#475569;">${_quadDistBreakdown(qDist)}</span></td></tr>`;
    }
    h += _memberBlock('cur_qtr');
    if (qtr.next) {
      const nc = qtr.turn_alert ? '#f97316' : '#94a3b8';
      const ns = qtr.turn_alert ? ' <span style="color:#f97316;">(near-end!)</span>' : '';
      h += `<tr><td class="k" style="font-size:9px;color:#475569;">Next quarter</td>`
         + `<td class="v" style="color:${nc};">${_coloredQuad(qtr.next)}${ns}</td></tr>`;
    }
  }

  h += '</table>';
  return h;
}

// Monthly scores popover — triggered by hovering the sparkline bars.
// Shows current month + future only (no past months).
function _buildScoresPopHtml(r) {
  const sym = r.tos_symbol || '—';
  const _sparksRaw = r.monthly_scores_json;
  const all = Array.isArray(_sparksRaw) ? _sparksRaw
    : (typeof _sparksRaw === 'string'
        ? (() => { try { return JSON.parse(_sparksRaw); } catch (_) { return null; } })()
        : null);
  if (!all || !all.length) return `<div class="sp-title">${escapeHtml(sym)} — Monthly Scores</div><div style="color:#94a3b8;font-size:10px;">No data.</div>`;

  const curIdx = all.findIndex(s => s.is_current);
  const rows = curIdx >= 0 ? all.slice(curIdx) : all;

  const _sigColor = v => v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#9ca3af';
  let h = `<div class="sp-title">${escapeHtml(sym)} — Monthly Scores</div><table>`;
  h += `<tr><td class="sp-sec" colspan="2">Current &amp; Forward Months</td></tr>`;
  for (const s of rows) {
    const sc  = s.score != null ? Number(s.score) : null;
    const col = sc == null ? '#9ca3af' : _sigColor(sc);
    const gl  = sc == null ? '—' : sc > 0 ? '▲' : sc < 0 ? '▼' : '→';
    const scHtml = sc != null
      ? `<span style="color:${col};font-weight:700;">${sc >= 0 ? '+' : ''}${sc.toFixed(2)}</span>`
      : '<span style="color:#9ca3af;">—</span>';
    const isCur = !!s.is_current;
    const qcol  = s.quad ? _quadColor(s.quad) : '#9ca3af';
    const distSegs = [
      {q:'Quad 1',pct:s.q1||0},{q:'Quad 2',pct:s.q2||0},
      {q:'Quad 3',pct:s.q3||0},{q:'Quad 4',pct:s.q4||0},
    ].filter(x => x.pct > 0);
    const distBar = distSegs.length
      ? `<span style="display:inline-flex;width:50px;height:4px;border-radius:2px;overflow:hidden;vertical-align:middle;margin-left:4px;border:1px solid #e2e8f0;">`
        + distSegs.map(x => `<div style="width:${x.pct}%;background:${_quadColor(x.q)};height:100%;" title="${escapeHtml(x.q)} ${x.pct}%"></div>`).join('')
        + `</span>`
      : '';
    h += `<tr${isCur ? ' style="background:#f1f5f9;"' : ''}>`
       + `<td class="k" style="font-size:9px;${isCur ? 'font-weight:700;' : ''}padding:1px 4px;">${escapeHtml(s.label || '')}</td>`
       + `<td class="v" style="font-size:9px;padding:1px 4px;white-space:nowrap;">`
       + `<span style="color:${qcol};font-weight:600;font-size:8px;">${escapeHtml(s.quad || '')}</span>`
       + distBar
       + `&nbsp;<span style="color:${col};">${gl}</span>&nbsp;${scHtml}`
       + `</td></tr>`;
  }
  h += '</table>';
  return h;
}

// Rich popover for regime-band quad labels (data-quadbandpop="all_periods|cur_month|next_month|cur_qtr|next_qtr")
function _buildQuadBandPopHtml(key) {
  const facs  = (state.quadFactors || {}).factors || [];
  const quads = (state.quadFactors || {}).quads   || {};

  // ── "Month" label: comparison table across all 3 periods ──────────────────
  if (key === 'all_periods') {
    const _oc = v => { const u=(v||'').toUpperCase(); return u==='BULLISH'?'#1c6c30':u==='BEARISH'?'#8c1d1d':'#9ca3af'; };
    const _ol = v => { if (!v) return '—'; const u=v.toUpperCase(); return u==='BULLISH'?'Bullish':u==='BEARISH'?'Bearish':v; };
    const bull = facs.filter(f => (f.cur_month||'').toUpperCase()==='BULLISH');
    const bear = facs.filter(f => (f.cur_month||'').toUpperCase()==='BEARISH');
    const neut = facs.filter(f => { const u=(f.cur_month||'').toUpperCase(); return u!=='BULLISH'&&u!=='BEARISH'; });
    const _vcol = 'padding-left:12px;min-width:58px;';
    const _row = f =>
      `<tr><td class="k">${escapeHtml(f.factor)}</td>`
      + `<td class="v" style="${_vcol}color:${_oc(f.cur_month)};font-size:10px;font-weight:600;">${_ol(f.cur_month)}</td>`
      + `<td class="v" style="${_vcol}color:${_oc(f.next_month)};font-size:10px;font-weight:600;">${_ol(f.next_month)}</td>`
      + `<td class="v" style="${_vcol}color:${_oc(f.cur_qtr)};font-size:10px;font-weight:600;">${_ol(f.cur_qtr)}</td>`
      + `</tr>`;
    const _hdr = `<tr style="border-bottom:1px solid #e2e8f0;">`
      + `<td class="k" style="color:#94a3b8;font-size:9px;padding-bottom:3px;">Factor</td>`
      + `<td class="v" style="${_vcol}color:#94a3b8;font-size:9px;white-space:nowrap;padding-bottom:3px;">Cur Month</td>`
      + `<td class="v" style="${_vcol}color:#94a3b8;font-size:9px;white-space:nowrap;padding-bottom:3px;">Next Month</td>`
      + `<td class="v" style="${_vcol}color:#94a3b8;font-size:9px;white-space:nowrap;padding-bottom:3px;">Quarter</td>`
      + `</tr>`;
    let h = `<div class="sp-title">Monthly Outlook</div><table>${_hdr}`;
    const sections = [
      [bull, `<tr><td class="sp-sec" colspan="4" style="color:#1c6c30;">↑ Bull — Current Month</td></tr>`],
      [bear, `<tr><td class="sp-sec" colspan="4" style="color:#8c1d1d;">↓ Bear — Current Month</td></tr>`],
      [neut, neut.length ? `<tr><td class="sp-sec" colspan="4" style="color:#9ca3af;">Neutral</td></tr>` : ''],
    ];
    for (const [items, hdr] of sections) { if (items.length) { h += hdr; items.forEach(f => { h += _row(f); }); } }
    return h + '</table>';
  }

  const quad  = quads[key] || '—';
  const periodLabel = { cur_month: 'Current Month', next_month: 'Next Month', cur_qtr: 'Current Quarter', next_qtr: 'Next Quarter' }[key] || key;
  const bull = facs.filter(f => (f[key] || '').toUpperCase() === 'BULLISH');
  const bear = facs.filter(f => (f[key] || '').toUpperCase() === 'BEARISH');
  let h = `<div class="sp-title" style="color:${_quadColor(quad)}">${escapeHtml(quad)}</div>`;
  h += `<div style="color:#94a3b8;font-size:9px;margin-bottom:4px;padding:0 6px;">${periodLabel}</div>`;
  h += '<table>';
  if (bull.length) {
    h += `<tr><td class="sp-sec" colspan="2" style="color:#1c6c30;">↑ Bull Factors</td></tr>`;
    for (const f of bull)
      h += `<tr><td class="k">${escapeHtml(f.factor)}</td><td class="v" style="color:#1c6c30;font-weight:600;font-size:10px;">Bullish</td></tr>`;
  }
  if (bear.length) {
    h += `<tr><td class="sp-sec" colspan="2" style="color:#8c1d1d;">↓ Bear Factors</td></tr>`;
    for (const f of bear)
      h += `<tr><td class="k">${escapeHtml(f.factor)}</td><td class="v" style="color:#8c1d1d;font-weight:600;font-size:10px;">Bearish</td></tr>`;
  }
  if (!bull.length && !bear.length)
    h += `<tr><td class="k" colspan="2" style="color:#9ca3af;">No factor data</td></tr>`;
  h += '</table>';
  return h;
}

// ── MACRO Regime Band (TASK_74) ─────────────────────────────────────────────
// Loads /api/dashboard/quads and renders the regime band above the grid.
const _MONTH_3C = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
function _shortMonthLbl(p) {
  if (p.start_date) { const d = new Date(p.start_date); if (!isNaN(d)) return _MONTH_3C[d.getMonth()]; }
  if (p.label) { const m = String(p.label).match(/^\d{4}-(\d{2})/); if (m) { const i = +m[1]-1; return (i>=0&&i<12)?_MONTH_3C[i]:String(p.label).toUpperCase(); } return String(p.label).toUpperCase(); }
  return '—';
}
function _shortQtrLbl(p) {
  if (p.start_date) { const d = new Date(p.start_date); if (!isNaN(d)) return `Q${Math.floor(d.getMonth()/3)+1} '${String(d.getFullYear()).slice(-2)}`; }
  return p.label ? String(p.label) : '—';
}
function _quadShort(q) { return q ? String(q).replace(/^Quad\s*/i, 'Q') : '—'; }
// Return the displayed quad name from a period object, using distribution argmax
// when available, falling back to the declared `.quad` field.
function _effectiveQuad(p) {
  if (!p) return null;
  const pcts = { 'Quad 1': p.quad1_pct || 0, 'Quad 2': p.quad2_pct || 0,
                 'Quad 3': p.quad3_pct || 0, 'Quad 4': p.quad4_pct || 0 };
  const total = Object.values(pcts).reduce((a, b) => a + b, 0);
  if (total > 0) return Object.entries(pcts).sort((a, b) => b[1] - a[1])[0][0];
  return p.quad || null;
}
function _quadColor(q) {
  if (!q) return '#9ca3af';
  if (/1/.test(q)) return '#2f9e2f'; // Q1 = bullish/growth
  if (/2/.test(q)) return '#1f7af2'; // Q2 = neutral/up
  if (/3/.test(q)) return '#e07c1a'; // Q3 = slowing
  if (/4/.test(q)) return '#d83a3a'; // Q4 = risk-off
  return '#9ca3af';
}


async function loadMacroBand() {
  const band = $('macroBand');
  if (!band) return;
  try {
    const dateParam = state.date ? `?date=${encodeURIComponent(state.date)}` : '';
    const [data, factors] = await Promise.all([
      fetchJson(`/api/dashboard/quads${dateParam}`),
      fetchJson(`/api/quad/band-factors${dateParam}`).catch(() => ({ bull: [], bear: [] })),
    ]);
    const cq = data.current_quarter, nq = data.next_quarter;
    const months = data.months || [];
    const cm = months[0], nm = months[1];
    const elM = $('macroBandMonth'), elQ = $('macroBandQtr'), elF = $('macroBandFavoring');
    if (!elM) return;

    const _qdLbl = q => q ? q.replace('Quad ', 'Qd ') : '—';
    // Segmented distribution bar with Q1 50% labels inside each segment (monthly)
    const _distBarMonth = p => {
      if (!p) return '';
      const segs = [
        {q:'Quad 1',pct:p.quad1_pct||0},{q:'Quad 2',pct:p.quad2_pct||0},
        {q:'Quad 3',pct:p.quad3_pct||0},{q:'Quad 4',pct:p.quad4_pct||0},
      ].filter(s=>s.pct>0);
      if (!segs.length) return '';
      const bars = segs.map(s => {
        const lbl = s.pct >= 15
          ? `<span style="font-size:7px;color:#fff;font-weight:600;line-height:1;pointer-events:none;">Q${s.q.slice(-1)} ${Math.round(s.pct)}%</span>`
          : '';
        return `<div style="width:${s.pct}%;background:${_quadColor(s.q)};height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;" title="${escapeHtml(s.q)} ${s.pct}%">${lbl}</div>`;
      }).join('');
      return `<span style="display:inline-flex;width:120px;height:14px;border-radius:3px;overflow:hidden;border:1px solid #e2e8f0;vertical-align:middle;margin-left:5px;">${bars}</span>`;
    };
    // Thin solid bar for quarterly
    const _distBarQtr = p => {
      if (!p) return '';
      const segs = [
        {q:'Quad 1',pct:p.quad1_pct||0},{q:'Quad 2',pct:p.quad2_pct||0},
        {q:'Quad 3',pct:p.quad3_pct||0},{q:'Quad 4',pct:p.quad4_pct||0},
      ].filter(s=>s.pct>0);
      if (!segs.length) return '';
      const bars = segs.map(s=>`<div style="width:${s.pct}%;background:${_quadColor(s.q)};height:100%;" title="${escapeHtml(s.q)} ${s.pct}%"></div>`).join('');
      return `<span style="display:inline-flex;width:40px;height:5px;border-radius:2px;overflow:hidden;border:1px solid #e2e8f0;vertical-align:middle;margin-left:3px;">${bars}</span>`;
    };

    // Month span — data-quadbandpop triggers rich popover
    const mCur = _effectiveQuad(cm) || '—';
    const mNxt = _effectiveQuad(nm);
    const mDtb = cm?.end_date ? Math.max(0, Math.round((new Date(cm.end_date) - new Date(data.as_of_date)) / 864e5)) : null;
    elM.innerHTML = `<span style="color:#64748b;font-size:10px;cursor:help;text-decoration:underline dotted;" data-quadbandpop="all_periods">Month</span> `
      + `<strong style="color:${_quadColor(mCur)};cursor:help;" data-quadbandpop="cur_month">${escapeHtml(_qdLbl(mCur))}</strong>`
      + _distBarMonth(cm)
      + (mDtb != null ? ` <span style="color:#94a3b8;font-size:10px;">(${mDtb}d left)</span>` : '')
      + (mNxt ? ` → <strong style="color:${_quadColor(mNxt)};opacity:0.7;cursor:help;" data-quadbandpop="next_month">${escapeHtml(_qdLbl(mNxt))}</strong>${_distBarMonth(nm)}` : '');

    // Quarter span
    const qCur = _effectiveQuad(cq) || '—';
    const qNxt = _effectiveQuad(nq);
    const qDtb = cq?.end_date ? Math.max(0, Math.round((new Date(cq.end_date) - new Date(data.as_of_date)) / 864e5)) : null;
    elQ.innerHTML = `<span style="color:#64748b;font-size:10px;">Qtr</span> `
      + `<strong style="color:${_quadColor(qCur)};cursor:help;" data-quadbandpop="cur_qtr">${escapeHtml(_qdLbl(qCur))}</strong>`
      + _distBarQtr(cq)
      + (qDtb != null ? ` <span style="color:#94a3b8;font-size:10px;">(${qDtb}d left)</span>` : '')
      + (qNxt ? ` → <strong style="color:${_quadColor(qNxt)};opacity:0.7;cursor:help;" data-quadbandpop="next_qtr">${escapeHtml(_qdLbl(qNxt))}</strong>${_distBarQtr(nq)}` : '');

    // Macro distribution — same universe as action split below
    if (elF) elF.innerHTML = '';
    // universe is computed below; defer macro dist render until then

    // Universe: same rules as matchesBaseFilters(show_hidden=off) —
    // excludes null-action, zero-AMT, and unheld-REMOVE rows.
    // Ignores active user filters (held_only, source, etc.) so stats
    // always reflect the full real signal universe, not just visible rows.
    const universe = (state.allRows || []).filter(r => {
      if (!r.consolidated_action) return false;
      if (!r._amt) return false;
      if ((r.consolidated_action || '').toUpperCase() === 'REMOVE' && !r.held_today) return false;
      return true;
    });

    // Breadth: ↑/↓ count from pct_change
    const elBreadth = $('macroBandBreadth');
    if (elBreadth) {
      if (universe.length) {
        let up = 0, dn = 0;
        for (const r of universe) {
          const p = r.pct_change != null ? Number(r.pct_change) : null;
          if (p != null) { if (p > 0) up++; else if (p < 0) dn++; }
        }
        elBreadth.innerHTML = `<span style="color:#166534;">↑${up}</span> <span style="color:#991b1b;">↓${dn}</span>`;
      } else { elBreadth.textContent = ''; }
    }

    // Macro distribution — counts macro_value within the same universe as action split
    if (elF && universe.length) {
      const mcnts = {};
      for (const r of universe) { const mv = r.macro_value; if (mv) mcnts[mv] = (mcnts[mv]||0)+1; }
      const SIDE_ORDER = { buy: 0, neutral: 1, sell: 2 };
      const mparts = Object.entries(mcnts)
        .sort((a, b) => {
          const sa = SIDE_ORDER[actionDisplay(a[0]).side] ?? 1;
          const sb = SIDE_ORDER[actionDisplay(b[0]).side] ?? 1;
          return sa !== sb ? sa - sb : b[1] - a[1];
        })
        .map(([code, cnt]) => {
          const d = actionDisplay(code);
          const col = d.side === 'buy' ? '#166534' : d.side === 'sell' ? '#991b1b' : '#6b7280';
          return `<span style="color:${col};">${escapeHtml(d.code || code)}:${cnt}</span>`;
        });
      elF.innerHTML = mparts.length
        ? `<span style="color:#64748b;font-size:10px;">Macro </span>${mparts.join(' ')}`
        : '';
    }

    // Action split: distribution grouped buy→neutral→sell
    const elSplit = $('macroBandSplit');
    if (elSplit) {
      if (universe.length) {
        const cnts2 = {};
        for (const r of universe) {
          const a = r.consolidated_action;
          if (a) cnts2[a] = (cnts2[a]||0) + 1;
        }
        const SIDE_ORDER = { buy: 0, neutral: 1, sell: 2 };
        const parts = Object.entries(cnts2)
          .sort((a, b) => {
            const sa = SIDE_ORDER[actionDisplay(a[0]).side] ?? 1;
            const sb = SIDE_ORDER[actionDisplay(b[0]).side] ?? 1;
            return sa !== sb ? sa - sb : b[1] - a[1];
          })
          .map(([code, cnt]) => {
            const d = actionDisplay(code);
            const col = d.side === 'buy' ? '#166534' : d.side === 'sell' ? '#991b1b' : '#6b7280';
            return `<span style="color:${col};">${escapeHtml(actionText(d))}:${cnt}</span>`;
          });
        elSplit.innerHTML = parts.join(' ');
      } else { elSplit.textContent = ''; }
    }

    state.quadData = data;
    state.quadFactors = factors;
    band.style.display = 'flex';

    // Wire rich popover on band quad labels (done once; re-attaching is safe via delegation)
    if (!band._qbpInit) {
      band._qbpInit = true;
      band.addEventListener('mouseover', e => {
        const el = e.target.closest('[data-quadbandpop]');
        if (el) _showDataPop(el, _buildQuadBandPopHtml(el.dataset.quadbandpop));
      });
      band.addEventListener('mouseout', e => {
        if (e.relatedTarget && e.relatedTarget.closest('[data-quadbandpop]')) return;
        hideSourcePop();
      });
    }
  } catch(e) { console.error('MACRO band:', e); if (band) band.style.display = 'none'; }
}
async function loadSideEcon() {
  const tbody = $('econBody'), empty = $('econEmpty'); if (!tbody) return;
  tbody.innerHTML = '';
  try {
    const rows = await fetchJson(state.date ? `/api/dashboard/econ-indicators?date=${encodeURIComponent(state.date)}&limit=20` : '/api/dashboard/econ-indicators?limit=20');
    if (!rows?.length) { empty.hidden = false; return; }
    empty.hidden = true;
    for (const r of rows) {
      const tr = document.createElement('tr'), sig = _normSignal(r.signal);
      tr.innerHTML = `<td class="text">${r.indicator||''}</td><td>${fmtDate(r.indicator_date)}</td><td class="num">${r.days??''}</td><td class="text">${sig.label?`<span class="signal-${sig.cls}">${sig.label}</span>`:''}</td>`;
      tbody.appendChild(tr);
    }
  } catch(e) { console.error('Side econ:', e); empty.hidden = false; }
}
async function loadSideEarnings() {
  const tbody = $('earningsBody'), empty = $('earningsEmpty'); if (!tbody) return;
  tbody.innerHTML = '';
  try {
    const rows = await fetchJson(state.date ? `/api/dashboard/earnings?date=${encodeURIComponent(state.date)}&days_ahead=60&limit=50` : '/api/dashboard/earnings?days_ahead=60&limit=50');
    if (!rows?.length) { empty.hidden = false; return; }
    empty.hidden = true;
    for (const r of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td class="text">${r.category||''}</td><td>${fmtDateMD(r.event_date)}</td><td class="num">${r.days_until!=null?r.days_until+'d':''}</td>`;
      tbody.appendChild(tr);
    }
  } catch(e) { console.error('Side earnings:', e); empty.hidden = false; }
}
function loadSidePanels() {
  if (!$('actSidePanel')?.classList.contains('pinned')) return;
  Promise.all([loadSideEcon(), loadSideEarnings()]);
}
// Short MM/DD date for snapshot columns (no year). '' for empty.
function fmtMD(d) {
  if (!d) return '';
  const m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? (m[2] + '/' + m[3]) : String(d);
}
// Format derived_at timestamp: show M/DD if yesterday, HH:MM AM/PM if today.
function fmtAsOf(ts) {
  if (!ts) return '';
  const dt = new Date(ts);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const tsDate = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const yestDate = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate());
  if (tsDate.getTime() === yestDate.getTime()) {
    return (yesterday.getMonth() + 1) + '/' + String(yesterday.getDate()).padStart(2, '0');
  } else if (tsDate.getTime() === todayDate.getTime()) {
    return dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  }
  return fmtMD(ts);
}

function fmtAsOfExport(exportDate, exportTime, loadedAt) {
  // Use export_date/time if available, otherwise fall back to loaded_at timestamp
  if (exportDate) {
    // Parse export_date as YYYY-MM-DD string
    const parts = String(exportDate).split('-');
    if (parts.length === 3) {
      const expYear = parseInt(parts[0]);
      const expMonth = parseInt(parts[1]);
      const expDay = parseInt(parts[2]);

      const today = new Date();
      const todayYear = today.getFullYear();
      const todayMonth = today.getMonth() + 1;
      const todayDay = today.getDate();

      const yesterday = new Date(today);
      yesterday.setDate(yesterday.getDate() - 1);
      const yestYear = yesterday.getFullYear();
      const yestMonth = yesterday.getMonth() + 1;
      const yestDay = yesterday.getDate();

      // Compare dates
      if (expYear === yestYear && expMonth === yestMonth && expDay === yestDay) {
        return yestMonth + '/' + String(yestDay).padStart(2, '0');
      } else if (expYear === todayYear && expMonth === todayMonth && expDay === todayDay) {
        // Format time: convert HHMM to HH:MM AM/PM
        if (exportTime) {
          const timeStr = String(exportTime).replace(':', '').trim();
          let hours = parseInt(timeStr.substring(0, timeStr.length - 2)) || 0;
          let minutes = parseInt(timeStr.substring(timeStr.length - 2)) || 0;
          const ampm = hours >= 12 ? 'PM' : 'AM';
          if (hours > 12) hours -= 12;
          if (hours === 0) hours = 12;
          return hours + ':' + String(minutes).padStart(2, '0') + ' ' + ampm;
        }
        return '';
      }
      return fmtMD(exportDate);
    }
  }
  // Fallback to loaded_at if export_date is missing
  if (loadedAt) {
    return fmtAsOf(loadedAt);
  }
  return '';
}
function showStatus(msg, kind = 'info', timeout = 4000) {
  const el = $('statusBar');
  el.className = 'status-bar ' + kind;
  el.textContent = msg;
  if (timeout) setTimeout(() => { el.style.display = 'none'; }, timeout);
}

// ---- date picker ----
async function loadDates() {
  const dates = await fetchJson('/api/actionable/dates');
  if (dates.length === 0) {
    showStatus('No actionable data computed yet. Run Admin > Rebuild to generate actionable recommendations.', 'warning', 0);
    return;
  }
  const sel = $('datePicker');
  sel.innerHTML = '';
  for (const d of dates) {
    const o = document.createElement('option');
    o.value = d; o.textContent = d;
    sel.appendChild(o);
  }
  state.date = dates[0] || null;
  if (state.date) sel.value = state.date;
  await loadActionable();
  checkEodFeed();
}

// ---- source metadata (base_weight_method per source, for Metric sort) ----
async function loadSources() {
  try {
    const rows = await fetchJson('/api/actionable/sources');
    state.sourceMethods = {};
    for (const r of rows) state.sourceMethods[r.source_code] = r.base_weight_method;
  } catch (_) { state.sourceMethods = {}; }
  // Rule track-record (v_rule_scorecard) keyed by composite code, for the
  // edge badges on fired-rule pills. Diagnostic only while history is shallow.
  try {
    const sc = await fetchJson('/api/rules/scorecard?min_fires=0&limit=2000');
    state.scorecard = {};
    for (const r of sc) state.scorecard[r.rule_id] = r;
  } catch (_) { state.scorecard = {}; }
  // Buysell code→seq map from ref_param_lookup for the default priority sort.
  // SA has seq=21 (highest); sorting by seq DESC puts SA at the top.
  try {
    state.buysellSeq = await fetchJson('/api/ref/buysell');
  } catch (_) { state.buysellSeq = {}; }
  // TASK_69: agreement scorecard — keyed by agreement_class -> avg_fwd_20d.
  try {
    const asc = await fetchJson('/api/rules/agreement-scorecard');
    state.agreementScorecard = {};
    for (const r of (asc || [])) {
      if (r.agreement_class != null) {
        state.agreementScorecard[r.agreement_class] = r.avg_fwd_20d;
      }
    }
  } catch (_) { state.agreementScorecard = {}; }
}

// Resolve the buy/sell side for a fired rule ID via actions.js (single source
// of truth). Uses the scorecard's direction field ('BUY'/'SELL') and maps it
// through actionDisplay() to get the canonical side string ('buy'/'sell'/'neutral').
function _ruleSide(id) {
  const sc = (state.scorecard || {})[id];
  if (!sc || !sc.direction) return 'neutral';
  // Map scorecard direction → representative BuySell code → actionDisplay side.
  const code = sc.direction === 'BUY' ? 'BM' : sc.direction === 'SELL' ? 'SA' : '';
  return actionDisplay(code).side; // 'buy' | 'sell' | 'neutral'
}

// Build the inline edge badge HTML for a fired composite code (or '' if unknown).
// Color = direction (buy=green, sell=red, neutral=grey); fill = edge strength.
// Confidence buckets: 'proven' = solid badge; 'promising' = normal; 'unproven' = muted grey.
function ruleEdgeBadge(code) {
  const sc = (state.scorecard || {})[code];
  if (!sc || sc.edge_20d == null) return '';
  const e = Number(sc.edge_20d);
  const conf = sc.confidence || 'unproven';
  const n = sc.n_fires != null ? sc.n_fires : (sc.fires != null ? sc.fires : '?');
  const ciLow  = sc.edge_20d_ci_low  != null ? Number(sc.edge_20d_ci_low).toFixed(1)  : null;
  const ciHigh = sc.edge_20d_ci_high != null ? Number(sc.edge_20d_ci_high).toFixed(1) : null;
  const ciStr  = ciLow != null ? ` CI [${ciLow}%,${ciHigh}%]` : '';
  if (conf === 'unproven') {
    // Muted grey badge — no color signal until sample is adequate
    return ` <span class="rule-edge-badge rule-neutral rule-weak" style="opacity:0.55;" `
         + `title="Unproven (n=${n}, too few fires or CI straddles 0${ciStr}) — diagnostic only">`
         + `n=${n}</span>`;
  }
  const side = _ruleSide(code);
  const sideCls = side === 'buy' ? 'rule-buy' : side === 'sell' ? 'rule-sell' : 'rule-neutral';
  const emphCls = conf === 'proven' ? 'rule-strong' : (e > 0 ? 'rule-strong' : 'rule-weak');
  const wr = (sc.win_rate != null) ? ` · ${(Number(sc.win_rate) * 100).toFixed(0)}%` : '';
  const sign = e >= 0 ? '+' : '';
  const provenMark = conf === 'proven' ? ' ✓' : '';
  return ` <span class="rule-edge-badge ${sideCls} ${emphCls}" `
       + `title="${conf}: 20d edge (n=${n}${ciStr}) — diagnostic, shallow history">`
       + `${sign}${e.toFixed(1)}%${wr}${provenMark}</span>`;
}

// Grid cell: fired rules ordered winning-first (highest score), each with its
// historical edge. Hue = Final Call action side (all pills match row's action);
// fill = edge emphasis (bold border=positive edge, light border=non-positive).
// Unproven rules (n<30 or CI straddles 0) render muted regardless of edge sign.
function firesCellHtml(r) {
  let fires = r.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (!Array.isArray(fires) || !fires.length) return '<span style="color:#cbd5e1">—</span>';
  const sc = state.scorecard || {};
  const items = fires.map(f => {
    const id = String(f.rule_id || f.id || f);
    const s   = sc[id] || {};
    const e   = s.edge_20d  != null ? Number(s.edge_20d)  : null;
    const conf = s.confidence || 'unproven';
    const n    = s.n_fires   != null ? s.n_fires : (s.fires != null ? s.fires : null);
    const score = (f.score != null) ? Number(f.score) : 0;
    return { id, e, conf, n, score };
  });
  // winning first: highest fired score, then strongest edge
  items.sort((a, b) => (b.score - a.score) || ((b.e ?? -99) - (a.e ?? -99)));
  const _RULE_CLR = {
    'act-sell-strong': '#991b1b', 'act-sell': '#ef4444', 'act-sell-weak': '#f97316',
    'act-buy-strong':  '#14532d', 'act-buy':  '#22c55e', 'act-buy-weak':  '#86efac',
  };
  // D5: _RULE_EXTRA (BR/B overrides) removed — BR and B now in actions.js _MAP.
  const _ruleColor = (id) => {
    for (const part of String(id).toUpperCase().split('-')) {
      const d = actionDisplay(part);
      const cls = (d.colorCls && d.colorCls !== 'act-neutral') ? d.colorCls : null;
      if (cls && _RULE_CLR[cls]) return _RULE_CLR[cls];
    }
    return '#94a3b8';
  };
  return items.map(it => {
    const color = _ruleColor(it.id);
    if (it.conf === 'unproven') {
      const nLabel = it.n != null ? `n=${it.n}` : '';
      const tip = `Unproven rule${it.n != null ? ' ('+nLabel+')' : ''} — too few fires or CI straddles 0`;
      return `<span style="white-space:nowrap;opacity:0.45;font-size:11px;color:${color};" title="${tip}">`
           + `${escapeHtml(it.id)}${nLabel ? ' <b>'+nLabel+'</b>' : ''}</span>`;
    }
    const weight = (it.e != null && it.e > 0) ? '700' : '400';
    const edge = it.e == null ? '' : ` <b>${it.e >= 0 ? '+' : ''}${it.e.toFixed(1)}</b>`;
    return `<span style="white-space:nowrap;font-size:11px;font-weight:${weight};color:${color};">${escapeHtml(it.id)}${edge}</span>`;
  }).join(' ');
}

// Best-first Metric direction: rank ascending (rank 1 best), else descending.
function _metricAscending(src) {
  return (state.sourceMethods || {})[src] === 'rank';
}

// The selected source's driver metric for a row (rank for PS, weight for
// outlook sources) - read from that source's source_actions entry.
function _rowMetric(row, src) {
  if (!src) return null;
  const e = _sourcesOf(row).find(s => (s.source || s.source_code || '') === src);
  if (!e || e.weight == null) return null;
  const n = Number(e.weight);
  return isFinite(n) ? n : null;
}

// SSS-style metrics (base_weight_method = rank_pct_delta) are percentages.
function _isPctSource(src) {
  return (state.sourceMethods || {})[src] === 'rank_pct_delta';
}

// Format a fraction as a percentage for display. pct_delta is stored as a
// fraction (e.g. 0.053) - scaled x100 here for display only; the stored
// value is never changed.
function fmtPct(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  return isFinite(n) ? (formatNum(n * 100) + '%') : '';
}

// ---- core load ----
async function loadActionable() {
  if (!state.date) return;
  // Reset to default actionability sort on every fresh data load (date change / refresh).
  // Column-header clicks override this until the next load or Clear.
  state.sort = { key: '_priority', dir: -1, type: 'num' };
  // Always fetch all rows -- action/category filters applied client-side so chip counts stay accurate
  // When show_hidden is on, also fetch acted/suppressed rows from the API.
  const params = new URLSearchParams({ date: state.date });
  if (state.filters.show_hidden) {
    params.append('show_acted', 'true');
    params.append('show_suppressed', 'true');
  }
  try {
    const dateParam = state.date ? `?date=${encodeURIComponent(state.date)}` : '';
    const [rows, accts] = await Promise.all([
      fetchJson('/api/actionable?' + params.toString()),
      fetchJson(`/api/actionable/accounts${dateParam}`).catch(() => []),
    ]);
    state.allAccounts = Array.isArray(accts) ? accts : [];
    state.allRows = Array.isArray(rows) ? rows : [];
    state.allRows.forEach(r => {
      const act = (r.consolidated_action || '').toUpperCase();
      if (_isOverMaxOverlay(r)) {
        // Over-allocation overlay — AMT$ = trim back to the category Max.
        r._amt = Number(r.current_position_dollar) - Number(r.target_max_dollar);
      } else if (act === 'REMOVE') {
        r._amt = r.current_position_dollar;
      } else if (act === 'ADD' && r.target_min_dollar != null) {
        // ADD: AMT$ is the top-up needed to reach Min. Already at/above Min → 0.
        const pos = Number(r.current_position_dollar) || 0;
        const min = Number(r.target_min_dollar);
        r._amt = pos < min ? min - pos : 0;
      } else if (act === 'INCREASE') {
        // INCREASE: AMT$ = target - position (amount to buy). Suppressed -> 0.
        const pos = Number(r.current_position_dollar) || 0;
        const tgt = Number(r.suggested_target_dollar) || 0;
        r._amt = tgt > pos ? tgt - pos : 0;
      } else if (act === 'REDUCE') {
        // REDUCE: AMT$ = position - target (amount to sell). Suppressed -> 0.
        const pos = Number(r.current_position_dollar) || 0;
        const tgt = Number(r.suggested_target_dollar) || 0;
        r._amt = pos > tgt ? pos - tgt : 0;
      } else {
        r._amt = r.suggested_target_dollar;
      }
    });
    // Priority and Final Call must be computed after _amt (uses _agreeingSources +
    // _hasPositiveEdge which need source_actions and scorecard, both already loaded).
    state.allRows.forEach(r => {
      var fc = finalCall(r);
      r._fc_strength = fc.strength;
      r._fc_code     = fc.code;
      r._fc_side     = fc.side;
      r._priority = _computePriority(r);
    });
    applyClientFilter();
    loadSidePanels();
    loadMacroBand();
  } catch (e) {
    showStatus('Failed to load actionable: ' + e.message, 'error', 0);
  }
}

// Client filters EXCEPT the action chip. Kept separate so the action-chip
// counts can reflect every other active filter.
// All active filters combine with AND.
function matchesBaseFilters(r) {
  // When show_hidden is OFF, hide suppressed/$0 AMT/no-action/acted/unheld-remove rows.
  if (!state.filters.show_hidden) {
    if (!r.consolidated_action) return false;
    if (!r._amt) return false;
    const ca = (r.consolidated_action || '').toUpperCase();
    if (ca === 'REMOVE' && !r.held_today) return false;
  }
  if (state.filters.source) {
    if (!_rowHasSource(r, state.filters.source)) return false;
  }
  if (state.filters.account) {
    if (!r.held_accounts) return false;
    const accts = r.held_accounts.split(',').map(a => a.trim());
    if (!accts.includes(state.filters.account)) return false;
  }
  if (state.filters.held_only) {
    if (!r.held_today) return false;
  }
  if (state.filters.conviction === 'multi') {
    if (_agreeingSources(r) < 2) return false;
  } else if (state.filters.conviction === 'proven') {
    if (!_hasPositiveEdge(r)) return false;
  }
  const symSearch = state.filters.symbol_search || '';
  if (symSearch) {
    const search = symSearch.toUpperCase();
    if (!r.tos_symbol || !r.tos_symbol.toUpperCase().includes(search)) return false;
  }
  // TASK_66: bull_prob minimum filter
  const bpMin = Number(state.filters.bull_prob_min) || 0;
  if (bpMin > 0) {
    if (r.bull_prob == null || Number(r.bull_prob) < bpMin) return false;
  }
  // TASK_69: agreement_class filter
  const agCls = state.filters.agreement_class || '';
  if (agCls && r.agreement_class !== agCls) return false;
  return true;
}

function applyClientFilter() {
  if (state.filters.source && !_availableSources().has(state.filters.source)) {
    state.filters.source = '';
  }
  // baseRows: all filters except the action chip (drives chip counts that reflect
  // every other active filter, via matchesBaseFilters).
  state.baseRows = state.allRows.filter(matchesBaseFilters);
  // rows: baseRows + action chip filter + actionable_only (AND combined)
  state.rows = state.baseRows.filter(r => {
    if (state.filters.action) return _chipAction(r) === state.filters.action;
    if (state.filters.actionable_only) {
      const a = _chipAction(r);
      return a !== 'HOLD' && a !== 'NONE';
    }
    return true;
  });
  // Reset collapse and selection on filter change.
  state.showAll = false;
  state.selected.clear();
  renderBulkBar();
  renderSummary();
  renderSourceFilter();
  renderAccountFilter();
  saveFiltersToStorage();
  renderGrid();
  _symTapeStart = 0;
  renderSymTape();
}

// ---- symbol tape (filterable chip bar) ------------------------------------
const _SYM_BATCH = 20;
let _symTapeStart = 0;

function _symTapeBg(row) {
  if (row.rr_outlook && window.outlookColor) {
    const c = window.outlookColor(row.rr_outlook);
    if (c && c !== 'inherit') return c;
  }
  // No outlook — fall back to pct_change direction
  const pct = row.pct_change != null ? Number(row.pct_change) : null;
  if (pct != null && pct > 0.001)  return '#2f9e2f';
  if (pct != null && pct < -0.001) return '#d83a3a';
  return '#888';
}

function renderSymTape() {
  const track = document.getElementById('symTapeTrack');
  const prevBtn = document.getElementById('symTapePrev');
  const nextBtn = document.getElementById('symTapeNext');
  const badge   = document.getElementById('symTapeBadge');
  if (!track) return;

  const rows  = state.rows;
  const total = rows.length;
  const start = Math.max(0, Math.min(_symTapeStart, total - 1));
  _symTapeStart = start;
  const end   = Math.min(start + _SYM_BATCH, total);
  const batch = rows.slice(start, end);

  track.innerHTML = batch.map(r => {
    const pct    = r.pct_change != null ? Number(r.pct_change) : null;
    const pctStr = pct != null ? Math.abs(pct).toFixed(2) + '%' : '—';
    const pctBg  = pct == null ? null : pct > 0.001 ? '#2f9e2f' : pct < -0.001 ? '#d83a3a' : '#888';
    const pctBoxStyle = pctBg ? `background:${pctBg};color:#fff;` : 'color:#94a3b8;';
    const bg     = _symTapeBg(r);
    const action = r.consolidated_action || '';
    const fmt2   = v => v != null ? Number(v).toFixed(2) : '—';
    const lrrStr = r.lrr != null ? `LRR ${fmt2(r.lrr)}` : '';
    const mrrStr = r.mrr != null ? `MRR ${fmt2(r.mrr)}` : '';
    const trrStr = r.trr != null ? `TRR ${fmt2(r.trr)}` : '';

    // Range bar fill — pct_brr is 0–100 (position within buy–sell range)
    const pctBrr = r.quote_pct_brr != null ? Number(r.quote_pct_brr)
                 : r.ma_pct_brr   != null ? Number(r.ma_pct_brr) : null;
    const rbW    = pctBrr != null ? Math.round(Math.max(0, Math.min(100, pctBrr))) : null;
    const rbHtml = rbW != null
      ? `<div class="rr-rb"><div class="rr-rb-tick" style="left:${rbW}%;"></div></div>`
      : `<div class="rr-rb"></div>`;

    // Action icon (glyph via actions.js) and IV bar glyph (TASK 62)
    const disp     = actionDisplay(r.consolidated_action);
    const actIc    = actionIcon(r.consolidated_action);
    const actGlyph = actIc.glyph !== '·' ? actIc.glyph : '';
    const actColor = actIc.color;
    // iv/hv stored as fractions (0.35 = 35%) → multiply by 100 for glyph percent units
    const _ivPct = r.imp_volatility != null ? Number(r.imp_volatility) * 100 : null;
    const _hvPct = r.hv            != null ? Number(r.hv)            * 100 : null;
    const ivGlyphHtml = window.ivGlyph
      ? window.ivGlyph(r.iv_percentile, _ivPct, _hvPct, r.iv_to_hv_discount, { size: 16, width: 24 })
      : '';
    const rvolHtml = typeof rvolDot === 'function'
      ? rvolDot(r.rvol, r.rvol_prior, { size: 16 }) : '';
    const candle = window.mtTip?.candleSvg(r.open_price, r.high_price, r.low_price, r.last_price) || '';
    const metaHtml = (actGlyph || rvolHtml || ivGlyphHtml || candle)
      ? `<div class="sym-tile-meta">` +
        (actGlyph    ? `<span class="sym-act-lbl" style="color:${actColor};font-family:ui-monospace,monospace;">${actGlyph}</span>` : '') +
        (rvolHtml    ? `<span class="sym-rvol" data-volpop data-sym="${escapeHtml(r.tos_symbol)}" style="cursor:default;">${rvolHtml}</span>` : '') +
        (ivGlyphHtml ? `<span class="sym-iv" data-ivpop data-sym="${escapeHtml(r.tos_symbol)}" style="cursor:default;">${ivGlyphHtml}</span>` : '') +
        candle +
        `</div>`
      : '';

    return `<div class="rr-chip" data-sym="${escapeHtml(r.tos_symbol)}">` +
      `<div class="rr-chip-body">` +
      `<div class="rr-chip-sym-col">` +
      `<span class="rr-sym" style="color:${bg};">${escapeHtml(r.tos_symbol)}</span>` +
      rbHtml +
      `</div>` +
      `<span class="mt-chg" style="${pctBoxStyle}">${pctStr}</span>` +
      `</div>` +
      metaHtml +
      `</div>`;
  }).join('');

  if (prevBtn) prevBtn.disabled = start === 0;
  if (nextBtn) nextBtn.disabled = end >= total;
  if (badge)   badge.textContent = total === 0 ? 'No symbols' : `${start + 1}–${end} of ${total}`;
}

function _initSymTape() {
  const prev = document.getElementById('symTapePrev');
  const next = document.getElementById('symTapeNext');
  if (prev) prev.addEventListener('click', () => {
    _symTapeStart = Math.max(0, _symTapeStart - _SYM_BATCH);
    renderSymTape();
  });
  if (next) next.addEventListener('click', () => {
    _symTapeStart = Math.min(state.rows.length - 1, _symTapeStart + _SYM_BATCH);
    renderSymTape();
  });
}

// ---- staleness banner ----
async function checkFreshness() {
  const banner = $('staleBanner');
  if (!banner || !state.date) return;
  try {
    const f = await fetchJson('/api/actionable/freshness?date=' +
      encodeURIComponent(state.date));
    if (f && f.stale) {
      $('staleBannerMsg').textContent =
        "This date's data is stale - newer source data was loaded after it " +
        "was last derived. Re-derive to refresh.";
      banner.style.display = 'flex';
    } else {
      banner.style.display = 'none';
    }
  } catch (_) {
    banner.style.display = 'none';
  }
}

// ---- Task 2: EOD feed missing banner ----
async function checkEodFeed() {
  const banner = $('eodMissingBanner');
  if (!banner || !state.date) return;
  try {
    const f = await fetchJson('/api/eod-feed-status?date=' +
      encodeURIComponent(state.date));
    if (f && f.missing) {
      $('eodMissingMsg').textContent = f.message ||
        'EOD price feed (TOSL) missing for this date — recommendations may be unreliable.';
      banner.style.display = 'block';
      // Apply warning style to every data row
      document.querySelectorAll('#actGrid tbody tr').forEach(tr => {
        tr.style.opacity = '0.7';
      });
    } else {
      banner.style.display = 'none';
      document.querySelectorAll('#actGrid tbody tr').forEach(tr => {
        tr.style.opacity = '';
      });
    }
  } catch (_) {
    banner.style.display = 'none';
  }
}

async function rederiveStale() {
  const btn = $('staleRederiveBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Re-deriving...'; }
  try {
    await fetchJson('/api/monitor/derive-stale/run', { method: 'POST' });
  } catch (_) { /* ignore - banner re-check below reflects the result */ }
  if (btn) { btn.disabled = false; btn.textContent = 'Re-derive now'; }
  await loadActionable();
  await checkFreshness();
}

// ---- summary chips (act as quick action filters) ----
function renderSummary() {
  const counts = { REMOVE: 0, OVER_MAX: 0, REDUCE: 0, INCREASE: 0, ADD: 0, HOLD: 0, NONE: 0 };
  for (const r of state.baseRows) {
    const a = _chipAction(r);
    if (counts[a] !== undefined) counts[a] += 1;
  }
  const wrap = $('summaryChips');
  wrap.innerHTML = '';
  const order = ['REMOVE', 'OVER_MAX', 'REDUCE', 'INCREASE', 'ADD', 'HOLD', 'NONE'];
  const all = document.createElement('div');
  all.className = 'act-chip' + (state.filters.action === '' ? ' active' : '');
  all.innerHTML = `<span>ALL</span><span class="count">${state.baseRows.length}</span>`;
  all.onclick = () => {
    state.filters.action = '';
    applyClientFilter();
  };
  wrap.appendChild(all);
  for (const a of order) {
    const chip = document.createElement('div');
    const disp = actionDisplay(a);
    chip.className = 'act-chip act-chip-' + a.toLowerCase()
                   + (state.filters.action === a ? ' active' : '');
    chip.title = disp.label || a;
    chip.innerHTML = `<span>${actionText(disp)}</span><span class="count">${counts[a] || 0}</span>`;
    chip.onclick = () => {
      state.filters.action = (state.filters.action === a) ? '' : a;
      applyClientFilter();
    };
    wrap.appendChild(chip);
  }
}

// Set of every source code present in the current dataset (winning + other).
function _availableSources() {
  const have = new Set();
  for (const r of state.allRows) {
    if (r.winning_source) have.add(r.winning_source);
    for (const s of _sourcesOf(r)) {
      const c = s.source || s.source_code || '';
      if (c) have.add(c);
    }
  }
  return have;
}

function renderSourceFilter() {
  const sel = $('sourceFilter');
  const have = _availableSources();
  // preserve current selection if still present
  const cur = state.filters.source;
  sel.innerHTML = '<option value="">All</option>';
  for (const c of Array.from(have).sort()) {
    const o = document.createElement('option');
    o.value = c; o.textContent = c;
    if (c === cur) o.selected = true;
    sel.appendChild(o);
  }
}

// Returns the display name for an account_number using state.allAccounts lookup.
function _acctDisplayName(acctNum) {
  const a = state.allAccounts.find(x => x.account_number === acctNum);
  return a ? (a.display_name || a.account_number) : acctNum;
}

// Returns comma-separated display names for a held_accounts string (account_numbers).
function _heldAccountsDisplay(held) {
  if (!held) return '';
  return held.split(',').map(n => _acctDisplayName(n.trim())).join(', ');
}

function _availableAccounts() {
  const have = new Set();
  for (const r of state.allRows) {
    if (!r.held_accounts) continue;
    for (const a of r.held_accounts.split(',')) {
      const t = a.trim();
      if (t) have.add(t);
    }
  }
  return have;
}

function renderAccountFilter() {
  const sel = $('accountFilter');
  if (!sel) return;
  // Use dedicated accounts list (objects with account_number + display_name).
  // Fall back to scraping raw account_numbers from state.allRows.
  const fallbackNums = state.allAccounts.length ? null : _availableAccounts();
  const accounts = state.allAccounts.length
    ? state.allAccounts
    : Array.from(fallbackNums).map(n => ({ account_number: n, display_name: n }));

  if (state.filters.account && !accounts.some(a => a.account_number === state.filters.account)) {
    state.filters.account = '';
  }
  const cur = state.filters.account;
  sel.innerHTML = '<option value="">All</option>';
  const sorted = [...accounts].sort((a, b) =>
    (a.display_name || a.account_number).localeCompare(b.display_name || b.account_number));
  for (const a of sorted) {
    const o = document.createElement('option');
    o.value = a.account_number;
    o.textContent = a.display_name || a.account_number;
    if (a.account_number === cur) o.selected = true;
    sel.appendChild(o);
  }
}


// localStorage persistence
const LS_KEY = 'act_filters_v3';
function saveFiltersToStorage() {
  try {
    const f = state.filters;
    const toSave = {
      source: f.source, account: f.account, held_only: f.held_only, show_hidden: f.show_hidden,
      symbol_search: f.symbol_search, conviction: f.conviction,
      actionable_only: f.actionable_only,
    };
    localStorage.setItem(LS_KEY, JSON.stringify(toSave));
  } catch (_) {}
}

function loadFiltersFromStorage() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    const f = state.filters;
    // Only load keys that exist in the current schema; ignore stale keys gracefully.
    if (saved.source !== undefined)       f.source = saved.source;
    if (saved.account !== undefined)      f.account = saved.account;
    if (saved.held_only !== undefined)    f.held_only = !!saved.held_only;
    if (saved.show_hidden !== undefined)  f.show_hidden = !!saved.show_hidden;
    if (saved.symbol_search !== undefined) f.symbol_search = saved.symbol_search;
    if (saved.conviction !== undefined)   f.conviction = saved.conviction;
    if (saved.actionable_only !== undefined) f.actionable_only = !!saved.actionable_only;
  } catch (_) {}
}

function syncFilterUi() {
  // Sync all UI elements to current state.filters
  const f = state.filters;
  const heldOnly = $('heldOnly');       if (heldOnly) heldOnly.classList.toggle('active', !!f.held_only);
  const acctFilter = $('accountFilter'); if (acctFilter) acctFilter.value = f.account || '';
  const showHidden = $('showHidden');   if (showHidden) showHidden.classList.toggle('active', !!f.show_hidden);
  const sym = $('symbolSearch');        if (sym) sym.value = f.symbol_search || '';
  const bp = $('bullProbFilter');       if (bp) bp.value = f.bull_prob_min || 0;
  const ag = $('agreementFilter');      if (ag) ag.value = f.agreement_class || '';
  // conviction segmented
  document.querySelectorAll('#convictionCtrl button').forEach(b => {
    b.classList.toggle('seg-active', b.dataset.conv === f.conviction);
  });
  // actionable_only toggle
  const aoBtn = $('actionableOnlyBtn');
  if (aoBtn) {
    aoBtn.classList.toggle('active', !!f.actionable_only);
  }
}

function clearAllFilters() {
  const f = state.filters;
  f.action = ''; f.source = ''; f.account = ''; f.held_only = false;
  f.show_hidden = false; f.actionable_only = true;
  f.symbol_search = ''; f.conviction = 'any';
  f.bull_prob_min = 0;
  f.agreement_class = '';
  const bpEl = $('bullProbFilter'); if (bpEl) bpEl.value = '0';
  const agEl = $('agreementFilter'); if (agEl) agEl.value = '';
  // Reset sort to default actionability order (updateSortIndicators called in renderGrid)
  state.sort = { key: '_priority', dir: -1, type: 'num' };
  // Reset show_hidden -> requires refetch (show_hidden=false excludes acted/suppressed from API)
  syncFilterUi();
  loadActionable();
}

// ---- grid ----
// Helper: render other (non-winning) source actions as inline pills
function _renderOtherSources(r) {
  let sources = r.source_actions;
  if (typeof sources === 'string') {
    try { sources = JSON.parse(sources); } catch (_) { sources = []; }
  }
  if (!Array.isArray(sources) || sources.length === 0) return '';
  
  const winning = (r.winning_source || '').toString();
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  
  if (others.length === 0) return '';

  // Strongest action first — same severity order as the consolidation sort.
  others.sort((a, b) =>
    (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
    (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  
  // colorCls from actions.js (single source of truth)
  return others.map(s => {
    const srcCode = (s.source || s.source_code || '?');
    const src = srcCode.toLowerCase();
    const action = (s.action || '').toUpperCase() || '?';
    const actDisp = actionDisplay(action);
    const colorCls = (actDisp.colorCls || 'act-neutral') + '-tint';
    const actLabel = actionText(actDisp) || action;
    return `<span data-srcpop data-sym="${escapeHtml(r.tos_symbol)}" data-src="${escapeHtml(srcCode)}" class="act-badge act-badge-sm ${colorCls}" style="margin-right:4px; cursor:help;" title="${escapeHtml(srcCode)}">${escapeHtml(actLabel)} <span style="font-size:8px; opacity:0.8;">(${src})</span></span>`;
  }).join('');
}

// ---- source-data hover popover ----
const _srcDataCache = new Map();   // symbol -> { RR:{...}, ETF:{...}, ... }
let _srcPopEl = null;
const _FEED_SRC = ['RR', 'ETF', 'PS', 'SSS'];

function _saFor(row, src) {
  let sa = row && row.source_actions;
  if (typeof sa === 'string') { try { sa = JSON.parse(sa); } catch (_) { sa = []; } }
  if (!Array.isArray(sa)) return null;
  return sa.find(s => (s.source || s.source_code || '') === src) || null;
}

// Action severity rank — REMOVE strongest. Mirrors the consolidation sort.
const ACTION_RANK = { REMOVE: 4, REDUCE: 3, INCREASE: 2, ADD: 1, HOLD: 0 };

// Per-code colors shared by Sources and Technical columns — matches Final Call / Portfolio palette.
const ACTION_CODE_COLOR = {
  SA:'#d83a3a',
  SS:'#e07c1a', STM:'#e07c1a', SO:'#e07c1a', SW:'#e07c1a', SWW:'#e07c1a',
  BM:'#2f9e2f', BS:'#2f9e2f',
  BMN:'#1f7af2', BW:'#1f7af2', BSW:'#1f7af2',
};
function _actionCodeColor(disp) {
  return ACTION_CODE_COLOR[disp.code] || (disp.side === 'sell' ? '#d83a3a' : disp.side === 'buy' ? '#2f9e2f' : '#888');
}

// Action color lookup: returns a CSS class from the token palette (actions.js).
// Used to color the "was X" overlay annotation via the act-* CSS utility classes.
function _actionColorCls(act) {
  return actionDisplay(act).colorCls || 'act-neutral';
}
// actionDisplay() is provided by actions.js (loaded before this script).
// actionLabel: plain-English label for a row's consolidated_action.
// OVER_MAX synthetic overlay gets its own display entry.
function actionLabel(row) {
  if (_isOverMaxOverlay(row)) return actionText(actionDisplay('OVER_MAX'));
  const a = ((row && row.consolidated_action) || 'NONE').toUpperCase();
  return actionText(actionDisplay(a));
}
// Chip bucket for a row — derived from finalCall() so filter pills match
// what the Final Call column actually shows.
// Returns one of: REMOVE | REDUCE | INCREASE | ADD | HOLD | OVER_MAX | NONE
function _chipAction(row) {
  if (_isOverMaxOverlay(row)) return 'OVER_MAX';
  const fc = finalCall(row);
  if (!fc.feasible) return 'NONE';
  const code = (fc.code || '').toUpperCase();
  if (code === 'SA') return 'REMOVE';
  if (code === 'SS' || code === 'STM' || code === 'SO') return 'REDUCE';
  if (code === 'BM' || code === 'BS') return 'INCREASE';
  if (code === 'BMN') return 'ADD';
  if (fc.side === 'neutral' || code === 'HOLD') return 'HOLD';
  return 'NONE';
}

// Badge color class — REDUCE (orange) when the over-Max overlay fires so
// the sell intent reads at a glance; otherwise mirrors consolidated_action.
function _badgeAction(row) {
  if (_isOverMaxOverlay(row)) return 'REDUCE';
  return ((row && row.consolidated_action) || 'NONE').toUpperCase();
}
// True when the row's held position exceeds the category Max and the
// SELL→MAX overlay applies (badge label + AMT$ + "was X" annotation).
// REMOVE rows are excluded — sell-all is stronger than sell-to-max.
function _isOverMaxOverlay(row) {
  if (!row) return false;
  if ((row.consolidated_action || '').toUpperCase() === 'REMOVE') return false;
  const pos = Number(row.current_position_dollar);
  const max = Number(row.target_max_dollar);
  return isFinite(pos) && isFinite(max) && max > 0 && pos > max;
}

// Parsed source_actions array for a row (winning + every "other" source).
function _sourcesOf(row) {
  let sa = row && row.source_actions;
  if (typeof sa === 'string') { try { sa = JSON.parse(sa); } catch (_) { sa = []; } }
  return Array.isArray(sa) ? sa : [];
}

// ── Source sub-line (Action cell second line) ──────────────────────────────
// Returns compact HTML like: RR·<colored>BS</colored>  II·<colored>BM</colored>
// Winning source first, then others sorted by severity.  Empty → ''.
function _srcSubLineHtml(r) {
  const sources = _sourcesOf(r);
  if (!sources.length) return '';
  const winning = (r.winning_source || '').toString();
  // Put winning source first, then sort remainder by severity.
  const winner = sources.filter(s => (s.source || s.source_code || '') === winning);
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  others.sort((a, b) =>
    (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
    (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  const ordered = winner.concat(others);
  const tokens = ordered.map(s => {
    const srcCode = escapeHtml(s.source || s.source_code || '?');
    const act = (s.action || '').toUpperCase();
    const disp = actionDisplay(act);
    const code = escapeHtml(disp.code || act || '?');
    const colorCls = disp.colorCls || 'act-neutral';
    return `<span class="act-src-token"><span class="${colorCls}" style="font-size:9px;">${srcCode}-${code}</span></span>`;
  });
  return `<div class="act-src-sub">${tokens.join(' ')}</div>`;
}

// Per-source reason lines for the Sources column: "SRC <icon> reason".
function _srcReasonsHtml(r) {
  const sources = _sourcesOf(r);
  if (!sources.length) return '';
  const winning = (r.winning_source || '').toString();
  const winner = sources.filter(s => (s.source || s.source_code || '') === winning);
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  others.sort((a, b) =>
    (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
    (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  const rows = winner.concat(others).map(s => {
    const src    = escapeHtml((s.source || s.source_code || '?').slice(0, 2));
    const ic     = actionIcon(s.action);
    const reason = s.reason ? escapeHtml(s.reason) : '';
    const dtRaw  = fmtMD(s.snapshot_date);
    const dt     = dtRaw ? `<span style="font-size:9px;font-weight:400;opacity:0.7;"> (${dtRaw.replace(/^0/, '')})</span>` : '';
    return `<div class="src-reason-line">
      <span class="src-ic" style="color:${ic.color};">${ic.glyph}</span>
      <span class="src-tag">${src}${dt}</span>
      <span class="src-rsn">${reason}</span>
    </div>`;
  });
  return `<div class="src-reasons">${rows.join('')}</div>`;
}

function _srcTooltip(r) {
  const sources = _sourcesOf(r);
  if (!sources.length) return '';
  const winning = (r.winning_source || '').toString();
  const winner = sources.filter(s => (s.source || s.source_code || '') === winning);
  const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
  others.sort((a, b) =>
    (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
    (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
  const lines = winner.concat(others).map(s => {
    const isWin = (s.source || s.source_code || '') === winning;
    const src   = s.source || s.source_code || '?';
    const ic    = actionIcon(s.action);
    const act   = (s.action || '').toUpperCase();
    const dt    = fmtMD(s.snapshot_date) || '?';
    const rsn   = s.reason || '';
    return (isWin ? '✓ ' : '  ') + src + '  ' + ic.glyph + '  ' + act + '  ' + dt + '  ' + rsn;
  });
  return 'ALL SOURCES\n' + lines.join('\n');
}

// ── Pass 1: Conviction ─────────────────────────────────────────────────────
// Count source_actions entries whose action aligns with consolidated_action direction.
// "align" = same sell/buy side (REMOVE/REDUCE/OVER_MAX → sell; INCREASE/ADD → buy).
function _agreeingSources(row) {
  const ca = (row.consolidated_action || '').toUpperCase();
  const isSell = ca === 'REMOVE' || ca === 'REDUCE' || ca === 'OVER_MAX';
  const isBuy  = ca === 'INCREASE' || ca === 'ADD';
  const sources = _sourcesOf(row);
  if (!sources.length) return 0;
  let count = 0;
  for (const s of sources) {
    const sa = (s.action || '').toUpperCase();
    if (isSell && (sa === 'REMOVE' || sa === 'REDUCE')) count++;
    else if (isBuy && (sa === 'INCREASE' || sa === 'ADD')) count++;
  }
  return count;
}

// True if any fired rule has positive 20d edge.
function _hasPositiveEdge(row) {
  let fires = row.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (!Array.isArray(fires) || !fires.length) return false;
  const sc = state.scorecard || {};
  for (const f of fires) {
    const id = String(f.rule_id || f.id || f);
    if (sc[id] && sc[id].edge_20d != null && Number(sc[id].edge_20d) > 0.5) return true;
  }
  return false;
}

// Returns the hidden reason string for a row, or null if not hidden.
function _hiddenReason(r) {
  if (r.suppressed_reason) return 'Snoozed: ' + r.suppressed_reason;
  const ua = (r.last_user_action || '').toUpperCase();
  if (ua === 'DONE' || ua === 'SKIPPED' || ua === 'OVERRIDDEN') return 'Acted: ' + ua;
  if (!r.consolidated_action) return 'No action';
  if (!r._amt) return 'AMT$ = 0';
  const ca = (r.consolidated_action || '').toUpperCase();
  if (ca === 'REMOVE' && !r.held_today) return 'REMOVE – not held';
  return null;
}

// Conviction badge HTML for grid cell.
function _convictionHtml(row) {
  const n = _agreeingSources(row);
  const edge = _hasPositiveEdge(row);
  const cls = edge ? 'conviction-badge edge-positive' : 'conviction-badge edge-none';
  const sources = _sourcesOf(row);
  const labels = sources
    .filter(s => {
      const ca = (row.consolidated_action || '').toUpperCase();
      const sa = (s.action || '').toUpperCase();
      const isSell = ca === 'REMOVE' || ca === 'REDUCE';
      const isBuy  = ca === 'INCREASE' || ca === 'ADD';
      return (isSell && (sa === 'REMOVE' || sa === 'REDUCE')) || (isBuy && (sa === 'INCREASE' || sa === 'ADD'));
    })
    .map(s => s.source || s.source_code || '?')
    .join(', ');
  const tip = labels || 'no agreeing sources';
  return `<span class="${cls}" title="${escapeHtml(tip)}">${n}&#10003;${edge ? ' &#9650;' : ''}</span>`;
}

// ── Final Call — reconcile three action lenses into one decision ────────────
//
// Scale: sell-all=-3, sell-some=-2, sell-overage=-1, hold=0,
//        buy-some/min/more=+2
// (OVER_MAX synthetic uses -1 so it sorts below genuine sells.)
var _FC_SCALE = {
  SA: -3, REMOVE: -3,
  SS: -2, STM: -2, REDUCE: -2,
  OVER_MAX: -1,
  HOLD: 0, NONE: 0,
  BS: 2, INCREASE: 2, BMN: 2, ADD: 2, BM: 2,
};

function _fcStrength(code) {
  if (!code) return 0;
  var v = _FC_SCALE[('' + code).toUpperCase()];
  return (v !== undefined) ? v : 0;
}

// Best-matching action display for a numeric strength (pick the canonical code
// that sits nearest to the target strength, honouring sign).
function _fcStrengthToAction(strength, consolidated) {
  // Round to nearest integer for lookup
  var s = Math.round(strength);
  if (s <= -3) return actionDisplay('SA');
  if (s === -2) return actionDisplay('SS');
  if (s === -1) return actionDisplay('OVER_MAX');
  if (s === 0)  return actionDisplay('HOLD');
  // positive: prefer what consolidated_action says if same side
  var ca = (consolidated || '').toUpperCase();
  if (s >= 2) {
    if (ca === 'ADD' || ca === 'BMN') return actionDisplay('ADD');
    if (ca === 'BM')  return actionDisplay('BM');
    return actionDisplay('INCREASE');
  }
  return actionDisplay('HOLD');
}

/**
 * finalCall(row) -> {label, code, side, strength, confidence, feasible}
 *
 * D6: server (derive_actionable.py::_compute_final_call) is the single source
 * of truth. This function reads final_code/final_side/fc_* when present.
 * The client-side computation below is a fallback ONLY for:
 *   (a) historical dates pre-TASK_53 migration (no final_code column yet), or
 *   (b) rows returned by a non-derived path (e.g. direct DB query without derive).
 * Do NOT add decision logic here — keep it in _compute_final_call on the server.
 *
 * Two-driver hierarchical decision (mirrored server-side):
 *   Sources (consolidated_action) = strategic: gates ownership (own it or exit).
 *   Technical (rr_action)         = tactical: trim/add while owning.
 *   Rules/edge are NOT consulted here — kept in the Rules column for manual
 *   cross-reference only.
 */
function finalCall(row) {
  // D6: prefer server-computed final call (derived at ETL time via _compute_final_call).
  // Client-side code below is a thin read-only fallback for pre-migration rows.
  if (row.final_code !== undefined && row.final_code !== null) {
    var _feasible = (row.fc_feasible === true || row.fc_feasible === 'true');
    var _strength = Number(row.fc_strength) || 0;
    var _confidence = row.fc_confidence || 'none';
    var _code = row.final_code || '';
    var _label = row.final_action || '';
    var _side = row.final_side || 'neutral';
    return {
      label: _label, code: _code, side: _side,
      strength: _strength, confidence: _confidence, feasible: _feasible,
    };
  }

  var ca  = (row.consolidated_action || '').toUpperCase();
  var rra = (row.rr_action           || '').toUpperCase();

  // ── 0. No recommendation at all ──────────────────────────────────────────
  if (!ca || ca === 'NONE') {
    var dispNone = actionDisplay('HOLD');
    return {
      label: dispNone.label, code: dispNone.code,
      side: 'neutral', strength: 0,
      confidence: 'none', feasible: false,
    };
  }

  // ── Helper classifiers ────────────────────────────────────────────────────
  var caOverMax  = _isOverMaxOverlay(row);
  var isHeld     = !!row.held_today;
  var atMax      = caOverMax;  // position already exceeds category Max

  // Sources side categorisation
  var srcIsExit    = (ca === 'REMOVE' || ca === 'SA');
  var srcIsReduce  = (ca === 'REDUCE' || ca === 'SS' || ca === 'STM');
  var srcIsBuy     = (ca === 'INCREASE' || ca === 'BS' || ca === 'BM' || ca === 'ADD' || ca === 'BMN');
  var srcIsAdd     = (ca === 'ADD' || ca === 'BMN');  // specifically "ADD to position / BUY TO MIN"
  var srcIsHold    = (!srcIsExit && !srcIsReduce && !srcIsBuy);  // HOLD or neutral

  // Technical side categorisation
  var techIsSell   = (rra === 'SS' || rra === 'STM' || rra === 'SO' ||
                      rra === 'REDUCE' || rra === 'SA' || rra === 'REMOVE');
  var techIsBuy    = (rra === 'BS' || rra === 'BM' ||
                      rra === 'INCREASE');
  var techIsBuyMin = (rra === 'BMN' || rra === 'ADD');
  var techIsNeutral = (!techIsSell && !techIsBuy && !techIsBuyMin);

  // ── 1. Feasibility (pre-check): never sell unheld, never buy past Max ─────
  // Selling an unheld position is infeasible; we'll guard this below per-path.
  // Buying past Max is infeasible; over-max rows are flagged via caOverMax.

  // ── 2. Strategic gate: SELL ALL / REMOVE → exit regardless of Technical ──
  if (srcIsExit || caOverMax) {
    // Over-max uses the OVER_MAX strength so it sorts below genuine SELL ALL.
    var exitStrength = caOverMax ? _FC_SCALE['OVER_MAX'] : _FC_SCALE['SA'];
    var exitCode     = caOverMax ? 'OVER_MAX' : 'SA';
    var exitDisp     = actionDisplay(exitCode);
    // Feasibility: can only sell if held (or over-max which implies held via overlay).
    if (!isHeld && !caOverMax) {
      var holdDisp = actionDisplay('HOLD');
      return {
        label: holdDisp.label, code: holdDisp.code,
        side: 'neutral', strength: 0,
        confidence: 'gate',
        gateReason: 'Exit signal but not held — no action feasible',
        feasible: false,
      };
    }
    return {
      label:      exitDisp.label,
      code:       exitDisp.code,
      side:       exitDisp.side,
      cls:        exitDisp.cls,
      strength:   exitStrength,
      confidence: 'gate',
      gateReason: caOverMax
        ? 'Over category Max — trim back to cap'
        : 'Sources: exit signal — Technical not evaluated',
      feasible:   true,
    };
  }

  // ── 3. Sources endorses owning → Technical drives tactical action ─────────
  // At this point ca is REDUCE, HOLD, INCREASE, ADD, or equivalent.

  // Don't-initiate guard: NOT held AND Sources doesn't endorse buying → HOLD
  if (!isHeld && !srcIsBuy) {
    var holdD = actionDisplay('HOLD');
    return {
      label: holdD.label, code: holdD.code,
      side: 'neutral', strength: 0,
      confidence: 'gate',
      gateReason: 'Not held + Sources don’t endorse buying — hold',
      feasible: true,
    };
  }

  var fcDisp, fcStrength, confidence, gateReason;

  if (techIsSell) {
    // Technical says trim — but only if held (can't sell what you don't have).
    if (!isHeld) {
      // Technical wants to sell, but not held → HOLD (infeasible sell).
      // At this point srcIsBuy must be true (the !isHeld && !srcIsBuy guard above
      // already returned). So Sources says buy but Technical says sell — genuine
      // conflict, even though the sell is infeasible.  Use 'mixed', not 'high'.
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'mixed';
    } else if (srcIsReduce) {
      // Sources AND Technical both say sell → High confidence SELL SOME
      fcDisp     = actionDisplay('SS');
      fcStrength = _FC_SCALE['SS'];
      confidence = 'high';
    } else {
      // Sources owns/buys, Technical says sell → Mixed (conflict)
      fcDisp     = actionDisplay('SS');
      fcStrength = _FC_SCALE['SS'];
      confidence = 'mixed';
    }
  } else if (techIsBuy || techIsBuyMin) {
    // Technical says add.
    // Note: at this point srcIsBuy is true OR isHeld is true (the don't-initiate
    // guard above already filtered out !isHeld && !srcIsBuy).
    if (srcIsReduce) {
      // Sources is souring (REDUCE), Technical says buy — conflict: downgrade to HOLD
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'mixed';
    } else if (atMax) {
      // Already at/past Max — cap: can't add more
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'gate';
      gateReason = 'At/over category Max — cannot add more';
    } else if (!isHeld && srcIsAdd) {
      // Not yet held, Sources says ADD (buy-to-min intent) → BUY TO MIN (establish)
      fcDisp     = actionDisplay('BMN');
      fcStrength = _FC_SCALE['BMN'];
      confidence = 'high';
    } else {
      // Sources owns/buys (or held), Technical says buy — add.
      // Prefer BM (buy-more) if either lens calls for it strongly.
      var buyCode = (rra === 'BM' || ca === 'BM' || ca === 'INCREASE' || ca === 'BS') ? 'BM' : 'BS';
      fcDisp     = actionDisplay(buyCode);
      fcStrength = _FC_SCALE[buyCode] || _FC_SCALE['BS'];
      confidence = (srcIsBuy) ? 'high' : 'mixed';
    }
  } else {
    // Technical is neutral/BMN/HOLD
    if (!isHeld && srcIsAdd) {
      // Not held, Sources says ADD → BUY TO MIN (establish position)
      fcDisp     = actionDisplay('BMN');
      fcStrength = _FC_SCALE['BMN'];
      confidence = 'gate';
      gateReason = 'Sources says ADD, Technical neutral — establishing position';
    } else if (srcIsReduce) {
      // Sources souring, Technical neutral → HOLD (no action but watch)
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      // Mild conflict: Sources wants down, Technical neutral
      confidence = 'mixed';
    } else {
      // Sources neutral/hold, Technical neutral — no active signal from either lens
      fcDisp     = actionDisplay('HOLD');
      fcStrength = 0;
      confidence = 'gate';
      gateReason = 'No active signal — Sources and Technical both neutral';
    }
  }

  return {
    label:      fcDisp.label,
    code:       fcDisp.code,
    side:       fcDisp.side,
    cls:        fcDisp.cls,
    strength:   fcStrength,
    confidence: confidence,
    gateReason: gateReason || null,
    feasible:   true,
  };
}

// HTML for the Final Call cell (label + confidence badge).
function _finalCallHtml(row) {
  var fc = finalCall(row);
  if (!fc.feasible || fc.confidence === 'none') {
    return '<span style="color:#cbd5e1;">—</span>';
  }
  var text = fc.label || actionText(fc);  // plain-English label (e.g. "SELL ALL")
  // Badge
  var badgeHtml;
  if (fc.confidence === 'high') {
    badgeHtml = '<span style="font-size:9px;color:#16a34a;" title="Sources and Technical align">High</span>';
  } else if (fc.confidence === 'gate') {
    var gateTitle = fc.gateReason || 'Deterministic gate — Technical not evaluated';
    badgeHtml = '<span style="font-size:9px;color:#64748b;" title="' + escapeHtml(gateTitle) + '">Gate</span>';
  } else {
    badgeHtml = '<span style="font-size:9px;color:#f97316;" title="Sources and Technical conflict — cross-check the Rules column">Mixed</span>';
  }
  // Color via actions.js token (act-*-fill gives solid fill + white text, matching Portfolio Action column)
  var fcDisp = actionDisplay(fc.code || (fc.side === 'sell' ? 'SA' : fc.side === 'buy' ? 'BS' : 'HOLD'));
  var colorCls = (fcDisp.colorCls || 'act-neutral') + '-fill';
  var subIcon = '<div style="font-size:9px;line-height:1.4;">' + badgeHtml + '</div>';
  return '<span class="act-badge act-badge-sm ' + colorCls + '" title="' +
         escapeHtml(fc.label || text) + '">' +
         escapeHtml(text) + '</span>' + subIcon;
}

// ── Pass 2: Priority score ──────────────────────────────────────────────────
// Priority = buysell SEQ of the Final Call action code (from ref_param_lookup).
// Sort direction is DESCENDING so the highest seq (SA=21) appears at the top.
//
// Feasibility gate: infeasible Final Call (e.g. unheld SELL ALL → HOLD)
// receives seq = -1 so it sinks below all real codes (lowest seqs start at 3).
//
// Codes not present in the buysell map (HOLD, OVER_MAX, none) also receive
// seq = -1 and sort to the bottom. Dollars at stake break ties within the
// same seq tier (×1e12 keeps tiers from crossing).
function _computePriority(row) {
  // TASK_53: use server-computed priority_rank when available (uses same formula).
  // Server uses seq * 1e6 + |amt|; client uses seq * 1e12 + |amt|.
  // We still add |_amt| at the client scale so ties break on dollars at stake.
  var amt = Math.abs(Number(row._amt) || 0);
  if (row.priority_rank !== undefined && row.priority_rank !== null) {
    var pr = Number(row.priority_rank);
    if (isFinite(pr)) return pr * 1e6 + amt;
  }
  var fc = finalCall(row);
  if (!fc.feasible) {
    // Infeasible: sink to bottom (seq = -1 < all real codes).
    return -1 * 1e12 + amt;
  }
  var code = (fc.code || '').toUpperCase();
  var seqMap = state.buysellSeq || {};
  // OVER_MAX is a synthetic code; map it to SO (SellOverage, seq=12) for sorting.
  if (code === 'OVER_MAX') code = 'SO';
  var seq = (seqMap[code] !== undefined) ? seqMap[code] : -1;
  return seq * 1e12 + amt;
}

// True if `src` drove this row OR appears among its other sources.
function _rowHasSource(row, src) {
  if (!src) return true;
  if ((row.winning_source || '') === src) return true;
  return _sourcesOf(row).some(s => (s.source || s.source_code || '') === src);
}

// Normalized weight delta for `src` on this row — per-source default sort key.
function _sourceWeightDelta(row, src) {
  const e = _sourcesOf(row).find(s => (s.source || s.source_code || '') === src);
  if (!e || e.weight_delta == null) return NaN;
  const n = Number(e.weight_delta);
  return isFinite(n) ? n : NaN;
}

function _renderSourcePop(el, sym, src, feed, loading) {
  if (_srcPopEl !== el) return;
  const pop = $('sourcePop');
  if (!pop) return;
  const row = state.rows.find(r => r.tos_symbol === sym);
  const sa = _saFor(row, src);
  const kv = [];
  let saActionHtml = '';
  if (sa) {
    if (sa.action) {
      const saAct = (sa.action || '').toUpperCase();
      const saDisp = actionDisplay(saAct);
      const saText = actionText(saDisp) || saAct;
      const saCls = (saDisp.colorCls || 'act-neutral') + '-tint';
      saActionHtml = `<span class="act-badge act-badge-sm ${saCls}" style="font-size:10px;">${escapeHtml(saText)}</span>`;
    }
    if (sa.weight != null)       kv.push(['Weight', formatNum(sa.weight)]);
    if (sa.prev_weight != null)  kv.push(['Prev wt', formatNum(sa.prev_weight)]);
    if (sa.weight_delta != null) kv.push(['&#916;', formatNum(sa.weight_delta)]);
  }
  const f = feed && feed[src];
  if (f && f.snapshot_date) kv.push(['Snapshot', f.snapshot_date]);
  const feedKv = [];
  if (src === 'RR' && f) {
    feedKv.push(['Buy Trade', formatNum(f.buy_trade)], ['Sell Trade', formatNum(f.sell_trade)]);
  } else if (src === 'ETF' && f) {
    feedKv.push(['BRR', formatNum(f.brr)], ['TRR', formatNum(f.trr)]);
  } else if (src === 'PS' && f) {
    feedKv.push(['Rank', formatNum(f.rank)]);
  } else if (src === 'SSS' && f) {
    feedKv.push(['Pct Delta', fmtPct(f.pct_delta)],
                ['Analyst Rank', (f.anlst_best_idea_rank == null ? '' : f.anlst_best_idea_rank)]);
  }
  let html = '<div class="sp-title">' + escapeHtml(src) + '</div><table>';
  if (saActionHtml) {
    html += '<tr><td class="k">Action</td><td class="v">' + saActionHtml + '</td></tr>';
  }
  for (const [k, v] of kv) {
    html += '<tr><td class="k">' + k + '</td><td class="v">' + escapeHtml(v) + '</td></tr>';
  }
  const showFeed = feedKv.length || (loading && _FEED_SRC.indexOf(src) >= 0);
  if (showFeed) {
    html += '<tr><td class="sp-sec" colspan="2">Feed</td></tr>';
    if (loading && !feedKv.length) {
      html += '<tr><td class="k" colspan="2">loading...</td></tr>';
    }
    for (const [k, v] of feedKv) {
      html += '<tr><td class="k">' + k + '</td><td class="v">' + escapeHtml(v) + '</td></tr>';
    }
  }
  if (sa && sa.reason) {
    html += '<tr><td class="sp-sec" colspan="2">Reason</td></tr>' +
            '<tr><td colspan="2" style="white-space:normal;">' + escapeHtml(sa.reason) + '</td></tr>';
  }
  html += '</table>';
  pop.innerHTML = html;
  pop.style.display = 'block';
  const rect = el.getBoundingClientRect();
  let top = rect.bottom + 4;
  if (top + pop.offsetHeight > window.innerHeight - 8) {
    top = Math.max(8, rect.top - pop.offsetHeight - 4);
  }
  let left = rect.left;
  if (left + pop.offsetWidth > window.innerWidth - 8) {
    left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
  }
  pop.style.top = top + 'px';
  pop.style.left = left + 'px';
}

async function showSourcePop(el) {
  const sym = el.dataset.sym;
  const src = el.dataset.src;
  if (!sym || !src) return;
  _srcPopEl = el;
  _renderSourcePop(el, sym, src, _srcDataCache.get(sym), !_srcDataCache.has(sym));
  if (!_srcDataCache.has(sym)) {
    let data = {};
    try {
      data = await fetchJson('/api/actionable/source-data?symbol=' +
        encodeURIComponent(sym) + '&date=' + encodeURIComponent(state.date || ''));
    } catch (_) { data = {}; }
    _srcDataCache.set(sym, data);
    _renderSourcePop(el, sym, src, data, false);
  }
}

function hideSourcePop() {
  _srcPopEl = null;
  const pop = $('sourcePop');
  if (pop) pop.style.display = 'none';
}

// ---- sym tape rich hover popover ----------------------------------------
function _buildSymTilePopHtml(r) {
  if (!r) return '';
  const fmt2 = v => v != null ? Number(v).toFixed(2) : '—';

  // Header
  const disp    = actionDisplay(r.consolidated_action);
  const actCode = actionText(disp);
  const actCls  = (disp.colorCls || 'act-neutral') + '-tint';
  const pct     = r.pct_change != null ? Number(r.pct_change) : null;
  const pctStr  = pct != null ? (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%' : '—';
  const pctCls  = pct == null ? '' : pct > 0.001 ? 'mt-up' : pct < -0.001 ? 'mt-down' : 'mt-flat';
  let html = `<div class="stp-header">` +
    `<span class="stp-sym">${escapeHtml(r.tos_symbol)}</span>` +
    (actCode && actCode !== '--' ? `<span class="act-badge act-badge-sm ${actCls}">${escapeHtml(actCode)}</span>` : '') +
    `<span class="stp-price">${r.last_price != null ? '$' + Number(r.last_price).toFixed(2) : ''}` +
    (pctStr ? ` <span class="${pctCls}">${pctStr}</span>` : '') +
    `</span></div>`;

  // Outlook — driven by drv_rr rr_outlook (same field that colors the symbol text)
  const _olColor = lbl => {
    if (window.outlookColor) {
      const c = window.outlookColor(lbl);
      if (c && c !== 'inherit') return c;
    }
    const u = (lbl || '').toUpperCase();
    return u.includes('BULL') ? '#16a34a' : u.includes('BEAR') ? '#dc2626' : '#64748b';
  };
  const rrOutlook = r.rr_outlook ? String(r.rr_outlook).charAt(0).toUpperCase() + String(r.rr_outlook).slice(1).toLowerCase() : null;
  if (rrOutlook) {
    html += `<div class="stp-section"><div class="stp-label">Outlook</div>` +
      `<div class="stp-row"><span class="stp-key">RR</span><span class="stp-val" style="font-weight:700;color:${_olColor(rrOutlook)};">${escapeHtml(rrOutlook)}</span></div>` +
      `</div>`;
  }

  // Sources
  const sources = _sourcesOf(r);
  if (sources.length) {
    html += `<div class="stp-section"><div class="stp-label">Sources</div>`;
    sources.forEach(s => {
      const sc   = s.source_code || s.source || '';
      const sa   = (s.action || '').toUpperCase();
      const sd   = actionDisplay(sa);
      const sCls = (sd.colorCls || 'act-neutral') + '-tint';
      const sTxt = actionText(sd) || sa || '—';
      const wt   = s.weight != null ? Number(s.weight).toFixed(2) : null;
      html += `<div class="stp-row">` +
        `<span class="stp-key">${escapeHtml(sc)}</span>` +
        `<span class="act-badge act-badge-sm ${sCls}">${escapeHtml(sTxt)}</span>` +
        (wt ? `<span class="stp-val">${wt}</span>` : '') +
        `</div>`;
    });
    html += `</div>`;
  }

  // Technical
  const pctBrr   = r.quote_pct_brr != null ? r.quote_pct_brr : r.ma_pct_brr;
  const hasTech  = r.lrr != null || r.mrr != null || r.trr != null ||
                   pctBrr != null || r.quote_zone || r.rr_desc ||
                   r.tn_td_desc || r.bb_desc;
  if (hasTech) {
    html += `<div class="stp-section"><div class="stp-label">Technical</div>`;
    if (r.tn_td_desc) html += `<div class="stp-row"><span class="stp-key">TnTd</span><span class="stp-val">${escapeHtml(r.tn_td_desc)}</span></div>`;
    if (r.bb_desc)    html += `<div class="stp-row"><span class="stp-key">BB</span><span class="stp-val">${escapeHtml(r.bb_desc)}</span></div>`;
    if (r.lrr  != null) html += `<div class="stp-row"><span class="stp-key">LRR</span><span class="stp-val">${fmt2(r.lrr)}</span></div>`;
    if (r.mrr  != null) html += `<div class="stp-row"><span class="stp-key">MRR</span><span class="stp-val">${fmt2(r.mrr)}</span></div>`;
    if (r.trr  != null) html += `<div class="stp-row"><span class="stp-key">TRR</span><span class="stp-val">${fmt2(r.trr)}</span></div>`;
    if (pctBrr != null) html += `<div class="stp-row"><span class="stp-key">BRR%</span><span class="stp-val">${Math.round(Number(pctBrr))}%</span></div>`;
    if (r.quote_zone) html += `<div class="stp-row"><span class="stp-key">Zone</span><span class="stp-val">${escapeHtml(r.quote_zone)}</span></div>`;
    if (r.rr_desc)    html += `<div class="stp-desc">${escapeHtml(r.rr_desc)}</div>`;
    html += `</div>`;
  }

  // Rules
  let fires = r.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (Array.isArray(fires) && fires.length) {
    html += `<div class="stp-section"><div class="stp-label">Rules</div>` +
      `<div class="stp-rules">${firesCellHtml(r)}</div></div>`;
  }

  return html;
}

function _showSymTilePop(chipEl) {
  const sym = chipEl.dataset.sym;
  if (!sym) return;
  const r   = state.rows.find(row => row.tos_symbol === sym);
  const pop = $('symTilePop');
  if (!pop || !r) return;
  pop.innerHTML    = _buildSymTilePopHtml(r);
  pop.style.display = 'block';
  const rect = chipEl.getBoundingClientRect();
  const popH = pop.offsetHeight;
  let top  = rect.top - popH - 8;
  if (top < 4) top = rect.bottom + 8;
  const left = Math.max(4, Math.min(window.innerWidth - 260, rect.left));
  pop.style.top  = top  + 'px';
  pop.style.left = left + 'px';
}

function _hideSymTilePop() {
  const pop = $('symTilePop');
  if (pop) pop.style.display = 'none';
}

function _showSymRichTip(e, chipEl) {
  if (!window.mtTip) return;
  const sym = chipEl.dataset.sym;
  const r   = state.rows.find(row => row.tos_symbol === sym);
  if (!r) return;
  const pct    = r.pct_change != null ? Number(r.pct_change) : null;
  const pctStr = pct != null ? (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%' : '—';
  const pctCls = pct == null ? 'mt-flat' : pct > 0.001 ? 'mt-up' : pct < -0.001 ? 'mt-down' : 'mt-flat';
  const arrow  = pct == null ? '' : pct > 0.001 ? '▲' : pct < -0.001 ? '▼' : '';
  const fmtN   = v => v != null ? Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : null;
  window.mtTip.showObj(e, {
    dname:        r.tos_symbol,
    sym:          r.tos_symbol,
    price:        fmtN(r.last_price),
    pct:          pctStr,
    arrow:        arrow,
    pctCls:       pctCls,
    outlook:      r.rr_outlook || '',
    price_source: r.last_price != null ? 'drv_quote' : '',
    rr_source:    (r.lrr != null && r.trr != null) ? 'hist_rr' : '',
    asof:         r.export_date ? String(r.export_date).slice(0, 10) : '',
    quote_time:   r.export_time ? String(r.export_time).slice(0, 5) : '',
    buy:          r.lrr != null ? Number(r.lrr).toFixed(2) : null,
    sell:         r.trr != null ? Number(r.trr).toFixed(2) : null,
    open:         fmtN(r.open_price),
    high:         fmtN(r.high_price),
    low:          fmtN(r.low_price),
    iv_pct:       r.imp_volatility    != null ? Math.round(Number(r.imp_volatility) * 100) : null,
    iv_pctile:    r.iv_percentile     != null ? Math.round(Number(r.iv_percentile))        : null,
    iv_to_hv:     r.iv_to_hv_discount != null ? Number(r.iv_to_hv_discount)               : null,
    stale:        false,
  });
}

function initSymTilePop() {
  const track = $('symTapeTrack');
  if (!track) return;

  track.addEventListener('mouseover', (e) => {
    const chip = e.target.closest('.rr-chip[data-sym]');
    if (!chip) { _hideSymTilePop(); window.mtTip?.hide(); return; }
    if (e.target.closest('[data-volpop],[data-ivpop]')) {
      // Vol/IV icons → handled by initSourcePopover; suppress symTilePop
      _hideSymTilePop();
      window.mtTip?.hide();
    } else if (e.target.closest('.sym-tile-meta')) {
      // Action label area → existing symTilePop
      window.mtTip?.hide();
      _showSymTilePop(chip);
    } else {
      // Symbol / price / range bar area → rich market tooltip
      _hideSymTilePop();
      _showSymRichTip(e, chip);
    }
  });
  track.addEventListener('mousemove', (e) => {
    if (e.target.closest('.rr-chip[data-sym]') && !e.target.closest('.sym-tile-meta')) {
      window.mtTip?.move(e);
    }
  });
  track.addEventListener('mouseout', (e) => {
    if (!e.relatedTarget || !e.relatedTarget.closest('.rr-chip[data-sym]')) {
      _hideSymTilePop();
      window.mtTip?.hide();
    }
  });
  track.addEventListener('click', (e) => {
    const chip = e.target.closest('.rr-chip[data-sym]');
    if (!chip) return;
    _hideSymTilePop();
    window.mtTip?.hide();
    const sym = chip.dataset.sym;
    const r   = state.rows.find(row => row.tos_symbol === sym);
    if (r) openDrilldown(r);
  });
}

function initGridSymClick() {
  const body = $('actBody');
  if (!body) return;
  body.addEventListener('click', (e) => {
    const cell = e.target.closest('[data-sym-cell]');
    if (!cell) return;
    const sym = cell.dataset.symCell;
    const r   = state.rows.find(row => row.tos_symbol === sym);
    const disp = actionDisplay(r?.consolidated_action || '');
    const code = actionText(disp);
    const cls  = (disp.colorCls || 'act-neutral') + '-tint';
    openChartModal(sym, {
      description: r?.description,
      price:       r?.last_price,
      pctChange:   r?.pct_change,
      badgeHtml:   code ? `<span class="act-badge ${cls}">${escapeHtml(code)}</span>` : '',
    });
  });
}

function _initSidePanels() {
  document.querySelectorAll('#actSidePanel .sp-hdr').forEach(hdr => {
    const panel = hdr.closest('.sp-panel');
    if (!panel) return;
    const key = 'sp_' + (hdr.dataset.panel || panel.id || '');
    if (localStorage.getItem(key) === 'collapsed') panel.classList.add('sp-collapsed');
    hdr.addEventListener('click', () => {
      panel.classList.toggle('sp-collapsed');
      localStorage.setItem(key, panel.classList.contains('sp-collapsed') ? 'collapsed' : 'open');
    });
  });
}

function initEcoBarClick() {
  ['marketTape','rrTape','rrTape3'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('click', (e) => {
      const chip = e.target.closest('.rr-chip[data-sym]');
      if (!chip) return;
      const sym = chip.dataset.sym;
      const r   = state.rows.find(row => row.tos_symbol === sym)
               || { tos_symbol: sym, as_of_date: state.date };
      openDrilldown(r);
    });
  });
}

// ---- rich Vol popover -------------------------------------------------------
function _decodeVolumeSpike(FF) {
  // Reproduces Excel: FH = RIGHT("0000000000" & FG & REPT("0",9-LEN(FG)), 10)
  // Source of truth: etl/derive_cat_atomic_input.py::_decode_vs (Python).
  // Step 1: right-pad fgStr to >=9 chars; Step 2: prepend 10 zeros; Step 3: last 10.
  if (FF == null || FF === 0) return null;
  const FG = Math.abs(Number(FF));
  const fgStr = FG.toFixed(2);
  const reptPad = Math.max(0, 9 - fgStr.length);
  const FH = ('0000000000' + fgStr + '0'.repeat(reptPad)).slice(-10);
  const nv = s => { const n = parseInt(s, 10); return isNaN(n) ? 0 : n; };
  return { FI: nv(FH.slice(0,2)), FJ: nv(FH.slice(2,5)),
           FL: nv(FH.slice(5,7)), FM: nv(FH.slice(8,10)) };
}

function _macdColor(v) {
  if (v == null) return '';
  const n = Number(v);
  if (n >  0.5) return '#15803d';   // strong bull  — green-700
  if (n >  0)   return '#4ade80';   // mild bull    — green-400
  if (n < -0.5) return '#b91c1c';   // strong bear  — red-700
  if (n <  0)   return '#f87171';   // mild bear    — red-400
  return '#6b7280';                  // flat         — gray-500
}
function _rsiColor(v) {
  if (v == null) return '';
  const n = Number(v);
  if (n >= 70) return '#b91c1c';    // overbought   — red-700
  if (n >= 60) return '#f97316';    // elevated     — orange-500
  if (n <= 30) return '#15803d';    // oversold     — green-700
  if (n <= 40) return '#4ade80';    // low          — green-400
  return '#6b7280';                  // neutral      — gray-500
}

function _buildVolPopHtml(r) {
  const fmtV = v => v != null ? Number(v).toLocaleString() : '—';
  const fmtR = v => v != null ? Number(v).toFixed(2) + '×' : '—';
  const fmtN = v => v != null ? Number(v).toFixed(2) : '—';
  const fmtP = v => v != null ? Number(v).toFixed(1) + '%' : '—';
  const dir = r.rvol != null && r.rvol_prior != null && r.rvol_prior > 0
    ? (r.rvol / r.rvol_prior > 1.05 ? '▲' : r.rvol / r.rvol_prior < 0.95 ? '▼' : '→') : '';
  const dirCls = dir === '▲' ? 'color:#16a34a' : dir === '▼' ? 'color:#dc2626' : 'color:#888';
  const vs = _decodeVolumeSpike(r.a_volume_spike);
  const rows = [
    ['Rel Vlm (RVOL)',    fmtR(r.rvol)],
    ['Prior Day RVOL',   fmtR(r.rvol_prior)],
    ['vs Prior',         dir ? `<span style="${dirCls}">${dir}</span>` : '—'],
    ['Volume',           fmtV(r.w_volume || r.volume)],
    ['Proj Volume',      fmtV(r.vlm_projected)],
    ['Avg Vlm 10d',      fmtV(r.volume_avg_10d)],
    ['Avg Vlm 3m',       fmtV(r.volume_avg_3m)],
    ['Vlm vs 3m Avg',    fmtP(r.vlm_3m_pct)],
    ['Vlm Rate Chg',     fmtN(r.volume_rate_change)],
    ['Vlm Signal',       r.vlm_desc || '—'],
    ['Vlm Action',       r.vlm_action ? (r.vlm_action === 'Accumulate' ? 'Accum' : r.vlm_action) : '—'],
  ];
  let html = '<div class="sp-title">Volume</div><table>';
  for (const [k, v] of rows)
    html += `<tr><td class="k">${k}</td><td class="v">${v}</td></tr>`;
  if (vs && vs.FI > 60) {
    const dir = (r.a_volume_spike || 0) >= 0 ? '↑' : '↓';
    const spikeStr = vs.FI === 0 ? '—' : vs.FI <= 15 ? 'Minor' : vs.FI <= 35 ? 'Mild' : vs.FI <= 60 ? 'Moderate' : vs.FI <= 80 ? 'Strong' : 'Extreme';
    const priceStr = vs.FJ === 0 ? '—' : `${dir} ${vs.FJ <= 100 ? 'Small' : vs.FJ <= 300 ? 'Moderate' : vs.FJ <= 600 ? 'Large' : 'Sharp'}`;
    const volStr   = vs.FL === 0 ? '—' : vs.FL <= 25 ? 'Low' : vs.FL <= 50 ? 'Moderate' : vs.FL <= 75 ? 'Elevated' : 'High';
    const daysStr  = vs.FM === 0 ? '—' : vs.FM === 1 ? '1 day' : `${vs.FM} days`;
    html += '<tr><td class="sp-sec" colspan="2">Vlm Spike (decoded)</td></tr>';
    html += '<tr><td colspan="2" style="font-size:9px;color:#94a3b8;padding:1px 4px 4px;">TOS unusual volume event: how big, price direction, volatility, when it occurred</td></tr>';
    html += `<tr><td class="k">Spike Strength</td><td class="v">${spikeStr}</td></tr>`;
    html += `<tr><td class="k">Price Move</td><td class="v">${priceStr}</td></tr>`;
    html += `<tr><td class="k">Volatility</td><td class="v">${volStr}</td></tr>`;
    html += `<tr><td class="k">Days Ago</td><td class="v">${daysStr}</td></tr>`;
  }
  return html + '</table>';
}

// ---- rich IV popover --------------------------------------------------------
function _buildIvPopHtml(r) {
  const fmtP = v => v != null ? Number(v).toFixed(1) + '%' : '—';
  const fmtN = v => v != null ? Number(v).toFixed(1) : '—';
  const iv  = r.imp_volatility != null ? r.imp_volatility * 100 : null;
  const hv  = r.hv             != null ? r.hv             * 100 : null;
  const dc  = r.iv_to_hv_discount;
  const dcStr = dc != null
    ? (dc > 0 ? '<span style="color:#16a34a">cheap ' : '<span style="color:#dc2626">rich ') +
      Math.abs(dc).toFixed(1) + '%</span>'
    : '—';
  const ivpVal = r.iv_percentile != null ? Math.round(Number(r.iv_percentile)) : null;
  const ivpColor = window._ivpBarColor ? window._ivpBarColor(ivpVal) : '#333';
  const ivpHtml = ivpVal != null
    ? `<span style="color:${ivpColor};font-weight:700;">${ivpVal}</span>`
    : '—';
  const rows = [
    ['IVP (IV Rank)',    ivpHtml],
    ['IV (Impl Vol)',    fmtP(iv)],
    ['HV (Hist Vol)',    fmtP(hv)],
    ['IV/HV Status',    dcStr],
    ['HV Percentile',   fmtN(r.hv_percentile)],
    ['Range Compress',  fmtN(r.range_compression)],
    ['IV/HV Ratio',     r.d_iv_to_hv != null ? Number(r.d_iv_to_hv).toFixed(3) : '—'],
  ];
  let html = '<div class="sp-title">Volatility</div><table>';
  for (const [k, v] of rows)
    html += `<tr><td class="k">${k}</td><td class="v">${v}</td></tr>`;
  return html + '</table>';
}

function _showDataPop(el, html) {
  const pop = $('sourcePop');
  if (!pop) return;
  pop.innerHTML = html;
  pop.style.display = 'block';
  const rect = el.getBoundingClientRect();
  let top = rect.bottom + 4;
  if (top + pop.offsetHeight > window.innerHeight - 8)
    top = Math.max(8, rect.top - pop.offsetHeight - 4);
  let left = rect.left;
  if (left + pop.offsetWidth > window.innerWidth - 8)
    left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
  pop.style.top  = top  + 'px';
  pop.style.left = left + 'px';
}

function initSourcePopover() {
  const body = $('actBody');
  if (!body) return;
  const _onOver = (e) => {
    const el = e.target.closest('[data-srcpop]');
    if (el && el.dataset.src) { showSourcePop(el); return; }
    const volEl = e.target.closest('[data-volpop]');
    if (volEl) {
      const r = state.rows.find(x => x.tos_symbol === volEl.dataset.sym);
      if (r) _showDataPop(volEl, _buildVolPopHtml(r));
      return;
    }
    const ivEl = e.target.closest('[data-ivpop]');
    if (ivEl) {
      const r = state.rows.find(x => x.tos_symbol === ivEl.dataset.sym);
      if (r) _showDataPop(ivEl, _buildIvPopHtml(r));
      return;
    }
    const scoresEl = e.target.closest('[data-scorespop]');
    if (scoresEl) {
      const r = state.rows.find(x => x.tos_symbol === scoresEl.dataset.scorespop);
      if (r) _showDataPop(scoresEl, _buildScoresPopHtml(r));
      return;
    }
    const macroEl = e.target.closest('[data-macropop]');
    if (macroEl) {
      const r = state.rows.find(x => x.tos_symbol === macroEl.dataset.macropop);
      if (r) _showDataPop(macroEl, _buildMacroPopHtml(r));
    }
  };
  const _onOut = (e) => {
    if (e.relatedTarget && e.relatedTarget.closest('[data-srcpop],[data-volpop],[data-ivpop],[data-macropop],[data-scorespop]')) return;
    hideSourcePop();
  };
  body.addEventListener('mouseover', _onOver);
  body.addEventListener('mouseout', _onOut);
  const tape = $('symTapeTrack');
  if (tape) {
    tape.addEventListener('mouseover', _onOver);
    tape.addEventListener('mouseout', _onOut);
  }
}

// ---- TASK_66: bull_prob cell renderer ----
// Shows probability as a percent with color coding.
// Agreement badge: green dot = high agreement (≥0.7), amber = mixed (0.4–0.7), red = split (<0.4).
function _bullProbCellHtml(r) {
  const prob = r.bull_prob;
  if (prob == null) return '<span style="color:#cbd5e1;font-size:10px;">—</span>';
  const pct = Math.round(Number(prob) * 100);
  const probColor = pct >= 65 ? '#16a34a' : pct >= 50 ? '#d97706' : '#dc2626';
  const agr = r.bull_agreement;
  let agrBadge = '';
  if (agr != null) {
    const agrVal = Number(agr);
    const agrColor = agrVal >= 0.7 ? '#16a34a' : agrVal >= 0.4 ? '#d97706' : '#dc2626';
    const agrTitle = `Signal agreement: ${Math.round(agrVal * 100)}% of signals bullish`;
    agrBadge = `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${agrColor};margin-left:3px;vertical-align:middle;" title="${agrTitle}"></span>`;
  }
  return `<span style="font-weight:700;font-size:11px;color:${probColor};">${pct}%</span>${agrBadge}`;
}

// ---- TASK_69: agreement_class cell renderer ----
// Colors: agree_bull=green, agree_bear=red, split_tech_bull=amber, split_tech_bear=orange, neutral=slate.
// Edge badge loaded from v_agreement_scorecard (stored in state.agreementScorecard).
const _AGR_LABEL = {
  agree_bull:      'Bull',
  agree_bear:      'Bear',
  split_tech_bull: 'SplTB',
  split_tech_bear: 'SplTSB',
  neutral:         'Neutral',
};
const _AGR_COLOR = {
  agree_bull:      '#16a34a',
  agree_bear:      '#dc2626',
  split_tech_bull: '#d97706',
  split_tech_bear: '#ea580c',
  neutral:         '#94a3b8',
};
function _agreementCellHtml(r) {
  const cls = r.agreement_class;
  if (!cls) return '<span style="color:#cbd5e1;font-size:10px;">—</span>';
  const lbl = _AGR_LABEL[cls] || cls;
  const color = _AGR_COLOR[cls] || '#64748b';
  // Edge badge from scorecard (populated after /api/rules/agreement-scorecard loads)
  let edgeBadge = '';
  if (state.agreementScorecard && state.agreementScorecard[cls] != null) {
    const e = Number(state.agreementScorecard[cls]);
    const eColor = e > 0.5 ? '#16a34a' : e < -0.5 ? '#dc2626' : '#d97706';
    const eSign = e >= 0 ? '+' : '';
    edgeBadge = `<span style="font-size:9px;color:${eColor};margin-left:3px;" title="Avg fwd 20d for ${cls}: ${eSign}${e.toFixed(2)}%">${eSign}${e.toFixed(1)}</span>`;
  }
  return `<span style="font-size:10px;font-weight:700;color:${color};" title="${cls}">${lbl}</span>${edgeBadge}`;
}

// ---- TASK_70: Final Call (cal) cell renderer ----
// Shows the calibrated final call (derived from bull_prob) beside the existing
// Final Call column so the user can compare them side-by-side.
// Uses the same badge style as _finalCallHtml but reads *_cal fields.
// A "vs" highlight (amber border) is added when the two disagree on side.
function _finalCallCalHtml(r) {
  const code = r.final_code_cal;
  if (code == null || code === '') {
    return '<span style="color:#cbd5e1;font-size:10px;">—</span>';
  }
  const label    = r.final_action_cal || code;
  const side     = r.final_side_cal   || 'neutral';
  const strength = Number(r.fc_strength_cal) || 0;
  // Treat as feasible when code is non-null.
  var fcDisp = actionDisplay(code);
  var colorCls = (fcDisp.colorCls || 'act-neutral') + '-fill';
  // "vs" highlight: amber left-border when cal side differs from existing FC side.
  var vsBorder = '';
  var vsTitle   = '';
  const existSide = r.final_side || 'neutral';
  if (existSide && side !== existSide) {
    vsBorder = 'border-left:3px solid #f59e0b;padding-left:3px;';
    vsTitle  = ' — disagrees with Final Call (' + existSide + ' vs ' + side + ')';
  }
  var tipText = 'Cal: ' + label + ' (strength ' + strength + ', p=' +
    (r.bull_prob != null ? Math.round(Number(r.bull_prob)*100) + '%' : '?') +
    ')' + vsTitle;
  return '<span class="act-badge act-badge-sm ' + colorCls + '" ' +
    'style="' + vsBorder + '" title="' + escapeHtml(tipText) + '">' +
    escapeHtml(label) + '</span>';
}

// ---- column sorting ----
function sortRows() {
  const { key, dir, type } = state.sort;
  const num = type === 'num';
  state.rows.sort((a, b) => {
    let va = a[key], vb = b[key];
    const aE = va === null || va === undefined || va === '';
    const bE = vb === null || vb === undefined || vb === '';
    if (aE && bE) return 0;
    if (aE) return 1;
    if (bE) return -1;
    if (num) {
      va = Number(va); vb = Number(vb);
      if (isNaN(va) && isNaN(vb)) return 0;
      if (isNaN(va)) return 1;
      if (isNaN(vb)) return -1;
      return (va - vb) * dir;
    }
    va = String(va).toLowerCase();
    vb = String(vb).toLowerCase();
    return va < vb ? -dir : va > vb ? dir : 0;
  });
}

function updateSortIndicators() {
  document.querySelectorAll('#actGrid th.sortable').forEach(th => {
    const base = th.dataset.label || th.textContent.trim();
    if (th.dataset.key === state.sort.key) {
      th.innerHTML = escapeHtml(base) + ' <span class="sort-ind">' +
        (state.sort.dir === 1 ? '&#9650;' : '&#9660;') + '</span>';
    } else {
      th.innerHTML = escapeHtml(base);
    }
  });
}

function initSorting() {
  document.querySelectorAll('#actGrid th.sortable').forEach(th => {
    // Preserve data-label if already set in HTML (e.g. for multi-line headers)
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (state.sort.key === key) {
        state.sort.dir = -state.sort.dir;
      } else {
        state.sort.key = key;
        state.sort.dir = (key === '_metric' && !_metricAscending(state.filters.source)) ? -1 : 1;
        state.sort.type = th.dataset.type || 'str';
      }
      updateSortIndicators();
      renderGrid();
      _symTapeStart = 0;
      renderSymTape();
    });
  });
}

function renderGrid() {
  for (const r of state.rows) {
    r._snapshot = _winningSnapshot(r);
    // Re-compute priority and final call here in case scorecard loaded after allRows.
    var fc = finalCall(r);
    r._fc_strength = fc.strength;
    r._fc_code     = fc.code;
    r._fc_side     = fc.side;
    r._priority = _computePriority(r);
  }
  hideSourcePop();
  sortRows();
  updateSortIndicators();
  const tb = $('actBody');
  tb.innerHTML = '';
  const total = state.rows.length;
  $('rowCount').textContent = `${total} row${total === 1 ? '' : 's'}`;
  $('emptyState').style.display = total === 0 ? 'block' : 'none';

  const visibleRows = state.rows;

  for (const r of visibleRows) {
    const tr = document.createElement('tr');
    const action = (r.consolidated_action || 'NONE').toUpperCase();
    const _ua = (r.last_user_action || '').toUpperCase();
    const isActed = r._rowActed || _ua === 'DONE' || _ua === 'SKIPPED' || _ua === 'OVERRIDDEN';
    if (isActed) tr.classList.add('row-acted');
    tr.dataset.sym = r.tos_symbol;

    const pctCls = r.pct_change != null ? (Number(r.pct_change) >= 0 ? 'pct-positive' : 'pct-negative') : '';
    const pctStr = r.pct_change != null ? (Number(r.pct_change).toFixed(2) + '%') : '';
    const priceStr = r.last_price != null ? fmtUsd(r.last_price) : '';
    // Task 4: intraday marker — shown only when quote is fresher than EOD anchor
    //         AND export_time falls within regular market hours (0930–1559 ET).
    const _idyRaw = String(r.export_time || '').replace(/:/g, '');
    const _idyTime = _idyRaw.length >= 4 ? ' @ ' + _idyRaw.slice(0,2) + ':' + _idyRaw.slice(2,4) : '';
    const _idyHHMM = _idyRaw.length >= 4 ? parseInt(_idyRaw.slice(0,4)) : null;
    const _inMktHours = _idyHHMM != null && _idyHHMM >= 930 && _idyHHMM < 1600;
    const intradayTag = r.quote_is_intraday && _inMktHours
      ? `<span title="Intraday price${escapeHtml(_idyTime)} — pct_brr/zone computed against live quote" style="font-size:8px;color:#0a84ff;font-weight:700;margin-left:2px;">IDY</span>`
      : '';
    const isChecked = state.selected.has(r.tos_symbol);

    // TrTnBBRskRng cell: run action through actionDisplay; attach rr-action-cell for hover tooltip
    const rrRaw = r.rr_action || '';
    const rrDisp = actionDisplay(rrRaw);
    const _rrIcData = actionIcon(rrRaw);
    const rrHtml = rrRaw
      ? `<span class="rr-main-ic" style="font-family:ui-monospace,monospace;font-size:24px;font-weight:700;color:${_rrIcData.color};cursor:help;flex-shrink:0;display:inline-block;width:36px;text-align:center;">${_rrIcData.glyph}</span>`
      : `<span class="rr-main-ic" style="font-size:12px;color:#cbd5e1;cursor:default;flex-shrink:0;display:inline-block;width:36px;text-align:center;">—</span>`;
    const _rrSubLineHtml = (() => {
      const td = r.tn_td_desc || '', bb = r.bb_desc || '';
      const rr = r.rr_desc || (rrRaw && r.rr_bull_bear ? (r.rr_bull_bear === 'B' ? 'Bull' : 'Not-Bull') : '');
      if (!td && !bb && !rr) return '';
      const line = t => `<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">${escapeHtml(t)}</div>`;
      return `<div class="rr-sub-line" style="font-size:9px;color:#94a3b8;line-height:1.4;" data-filled="1">${td ? line('TnTd: ' + td) : ''}${bb ? line('BB: ' + bb) : ''}${rr ? line('RR: ' + rr) : ''}</div>`;
    })();

    // Final Call cell — reconciled action + confidence badge
    const fcHtml = _finalCallHtml(r);
    // Default Act action: use final call code when available, else 'DONE'
    const fcActCode = r._fc_code || 'DONE';

    const posStr = fmtCompact(r.current_position_dollar);
    const _hReason = _hiddenReason(r);
    tr.innerHTML = `
      <td style="padding:4px 6px; text-align:center;">
        <input type="checkbox" class="row-check" data-sym="${escapeHtml(r.tos_symbol)}"${isChecked ? ' checked' : ''}>
      </td>
      <td class="num" style="font-size:10px;color:#f59e0b;font-weight:700;text-align:center;">${_hReason ? `<span title="${escapeHtml(_hReason)}">Y</span>` : ''}</td>
      <td class="num" style="font-size:11px; color:#475569;" ${r.held_accounts ? `title="Held in: ${escapeHtml(_heldAccountsDisplay(r.held_accounts))}"` : ''}>${posStr || '<span style="color:#cbd5e1;">—</span>'}</td>
      <td class="num">
        <span class="amt-primary">${fmtUsd(r._amt)}</span>
        ${r.stop_level != null ? `<div style="font-size:9px;color:#94a3b8;white-space:nowrap;" title="Stop / exit-below level (task 8)">stop ${fmtUsd(r.stop_level)}</div>` : ''}
      </td>
      <td class="num">
        <span class="${pctCls}" style="font-weight:700;">${pctStr}${intradayTag}</span>
        ${priceStr ? `<div style="font-size:10px;color:#94a3b8;">${priceStr}</div>` : ''}
      </td>
      <td data-sym-cell="${escapeHtml(r.tos_symbol)}" style="padding:6px 4px; cursor:pointer;" title="Click for chart">
        <strong class="tv-sym-link" style="font-size:11px;">${escapeHtml(r.tos_symbol || '')}</strong>
      </td>
      <td style="padding:6px 4px;">${fcHtml}</td>
      <td style="padding:4px 6px; text-align:center;">${macroCellHtml(r)}</td>
      <td style="padding:6px 4px;">${_finalCallCalHtml(r)}</td>
      <td class="act-action-cell" data-sym="${escapeHtml(r.tos_symbol)}" style="padding:6px 4px; cursor:help;">
        <div style="display:flex;align-items:flex-start;gap:8px;">
          <div style="width:38px;flex-shrink:0;align-self:center;text-align:center;">
            ${(()=>{ const _ic=actionIcon(_badgeAction(r)); return `<span class="act-main-ic" style="font-family:ui-monospace,monospace;font-size:24px;font-weight:700;color:${_ic.color};cursor:help;">${_ic.glyph}</span>`; })()}
            ${_isOverMaxOverlay(r) ? `<div style="font-size:8px;line-height:1;font-weight:600;margin-top:1px;" class="${_actionColorCls(action)}">was ${actionText(actionDisplay(action))}</div>` : ''}
          </div>
          ${_srcReasonsHtml(r)}
        </div>
      </td>
      <td class="rr-action-cell" data-sym="${escapeHtml(r.tos_symbol)}" data-date="${escapeHtml(r.as_of_date || state.date || '')}" style="padding:6px 4px;">
        <div style="display:flex;align-items:flex-start;gap:6px;">
          ${rrHtml}
          ${_rrSubLineHtml}
        </div>
      </td>
      <td class="num rvol-cell" data-sym="${escapeHtml(r.tos_symbol)}" data-volpop style="cursor:default;">${typeof rvolDot === 'function' ? rvolDot(r.rvol, r.rvol_prior) : ''}${r.vlm_action ? `<span style="display:inline-block;margin-left:3px;font-size:9px;padding:1px 3px;border-radius:3px;background:${r.vlm_action==='Accumulate'?'#bbf7d0':r.vlm_action==='Avoid'?'#fecaca':'#e5e7eb'};color:#374151;font-weight:600;text-decoration:none;vertical-align:middle;">${escapeHtml(r.vlm_action === 'Accumulate' ? 'Accum' : r.vlm_action)}</span>` : ''}</td>
      <td class="num" data-sym="${escapeHtml(r.tos_symbol)}" data-ivpop style="padding:3px 4px;cursor:default;">${window.ivGlyph ? window.ivGlyph(r.iv_percentile, r.imp_volatility != null ? r.imp_volatility * 100 : null, r.hv != null ? r.hv * 100 : null, r.iv_to_hv_discount) : ''}</td>
      <td class="num" style="font-size:11px;font-weight:600;color:${_macdColor(r.a_macd_brr)}">${r.a_macd_brr != null ? Number(r.a_macd_brr).toFixed(2) : ''}</td>
      <td class="num" style="font-size:11px;font-weight:600;color:${_macdColor(r.a_macdh_d_brr)}">${r.a_macdh_d_brr != null ? Number(r.a_macdh_d_brr).toFixed(2) : ''}</td>
      <td class="num" style="font-size:11px;font-weight:600;color:${_rsiColor(r.rsi)}">${r.rsi != null ? Number(r.rsi).toFixed(1) : ''}</td>
      <td class="rules-link-cell" data-sym="${escapeHtml(r.tos_symbol)}" style="padding:4px 6px; max-width:720px; overflow:hidden; cursor:pointer;" title="Open Rule Flow for ${escapeHtml(r.tos_symbol)}">${firesCellHtml(r)}</td>
      <td class="num" style="padding:4px 6px; white-space:nowrap;">${_bullProbCellHtml(r)}</td>
      <td style="padding:4px 6px; white-space:nowrap;">${_agreementCellHtml(r)}</td>
      <td style="padding:4px 6px;">
        <div class="act-inline-btns">
          <button type="button" class="btn-done btn-inline-done" data-sym="${escapeHtml(r.tos_symbol)}" data-fc="${escapeHtml(fcActCode)}" title="Act: log final call action">&#10003; ${escapeHtml(fcActCode)}</button>
          <button type="button" class="btn-skip btn-inline-skip" data-sym="${escapeHtml(r.tos_symbol)}" title="Skip">&#10007;</button>
          <button type="button" class="btn-snz btn-inline-snz"  data-sym="${escapeHtml(r.tos_symbol)}" title="Snooze">&#128164;</button>
        </div>
      </td>
    `;
    tr.onclick = (e) => {
      if (e.target.closest('.btn-inline-done') || e.target.closest('.btn-inline-skip') ||
          e.target.closest('.btn-inline-snz')  || e.target.closest('.row-check')) return;
      const rulesCell = e.target.closest('.rules-link-cell');
      if (rulesCell) {
        window.location.href = '/rule-flow?symbol=' + encodeURIComponent(rulesCell.dataset.sym);
        return;
      }
      openDrilldown(r);
    };
    tb.appendChild(tr);
  }

  // Sync select-all checkbox
  const allChk = $('bulkSelectAll');
  if (allChk) {
    allChk.checked = state.selected.size > 0 && state.selected.size >= visibleRows.length;
    allChk.indeterminate = state.selected.size > 0 && state.selected.size < visibleRows.length;
  }
}

// escapeHtml is provided by _common.js (window.escapeHtml).

// ── Pass 3: Bulk bar ───────────────────────────────────────────────────────
function renderBulkBar() {
  const bar = $('bulkBar');
  if (!bar) return;
  const n = state.selected.size;
  if (n > 0) {
    bar.classList.add('visible');
    $('bulkCount').textContent = `${n} selected`;
  } else {
    bar.classList.remove('visible');
  }
}

// Inline action: call the same endpoint as the modal Save/Dismiss.
async function inlineAction(sym, action) {
  if (!sym || !state.date) return;
  const row = state.allRows.find(r => r.tos_symbol === sym);
  const asOf = row ? row.as_of_date : state.date;
  // user_action must be the legacy enum (DONE/SKIPPED/SNOOZED/OVERRIDDEN).
  // The Final Call BuySell code (SA/SS/BM/etc.) goes into action_code.
  const isLegacyAction = ['DONE','SKIPPED','SNOOZED','OVERRIDDEN'].includes((action||'').toUpperCase());
  const userAction = isLegacyAction ? action.toUpperCase() : 'DONE';
  const actionCode = isLegacyAction ? null : action;
  const payload = { as_of_date: asOf, user_action: userAction,
                    action_code: actionCode, user_notes: 'inline' };
  try {
    await fetchJson('/api/actionable/' + encodeURIComponent(sym) + '/action', {
      method: 'POST', body: JSON.stringify(payload),
    });
    // Mark row visually acted; keep in grid until next reload.
    if (row) row._rowActed = true;
    const tr = document.querySelector(`#actBody tr[data-sym="${CSS.escape(sym)}"]`);
    if (tr) tr.classList.add('row-acted');
    showStatus(`${action}: ${sym}`, 'success', 2500);
  } catch (e) {
    showStatus(`${action} failed: ${e.message}`, 'error');
  }
}

async function bulkAction(action) {
  const syms = Array.from(state.selected);
  if (!syms.length) return;
  for (const sym of syms) await inlineAction(sym, action);
  state.selected.clear();
  renderBulkBar();
  renderGrid();
}

// ── Pass 3: Focus mode ─────────────────────────────────────────────────────
function _focusRows() {
  return state.rows.filter(r => !r._rowActed);
}

function openFocusMode() {
  state.focusIdx = 0;
  _renderFocusCard();
  $('focusBackdrop').classList.add('open');
}

function _renderFocusCard() {
  const rows = _focusRows();
  if (!rows.length) {
    $('focusBackdrop').classList.remove('open');
    showStatus('All done! No more rows.', 'success', 3000);
    return;
  }
  if (state.focusIdx >= rows.length) state.focusIdx = rows.length - 1;
  const r = rows[state.focusIdx];
  $('fcProg').textContent = `${state.focusIdx + 1} of ${rows.length}`;
  $('fcSym').textContent = r.tos_symbol || '';
  $('fcAction').innerHTML = `<span class="act-badge ${(actionDisplay(_badgeAction(r)).colorCls || 'act-neutral') + '-tint'}" style="font-size:16px;padding:4px 14px;">${actionLabel(r)}</span>`;
  $('fcAmt').textContent = fmtUsd(r._amt) || '—';
  // "Why": top fired rule or winning source + reason snippet.
  let why = '';
  let fires = r.rules_engine_fires;
  if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
  if (Array.isArray(fires) && fires.length) {
    const topRule = String(fires[0].rule_id || fires[0].id || fires[0]);
    why = 'Rule: ' + topRule;
  } else if (r.winning_source) {
    why = r.winning_source;
    const reason = _winningReason(r);
    if (reason) why += ': ' + reason.slice(0, 80);
  }
  $('fcWhy').textContent = why;
}

function focusAdvance(action) {
  const rows = _focusRows();
  if (!rows.length) return;
  const r = rows[state.focusIdx];
  if (action) {
    inlineAction(r.tos_symbol, action).then(() => {
      state.focusIdx = Math.min(state.focusIdx, _focusRows().length - 1);
      _renderFocusCard();
    });
  } else {
    state.focusIdx = Math.min(state.focusIdx + 1, _focusRows().length - 1);
    _renderFocusCard();
  }
}

// ---- CSV export (current filtered + sorted view) ----
function otherSourcesText(r) {
  let sources = r.source_actions;
  if (typeof sources === 'string') {
    try { sources = JSON.parse(sources); } catch (_) { sources = []; }
  }
  if (!Array.isArray(sources)) return '';
  const winning = (r.winning_source || '').toString();
  return sources
    .filter(s => (s.source || s.source_code || '') !== winning)
    .map(s => `${(s.action || '').toUpperCase()} (${s.source || s.source_code || '?'})`)
    .join('; ');
}

function exportCsv() {
  const cols = [
    ['Symbol',        r => r.tos_symbol],
    ['Change %',      r => r.pct_change != null ? (Number(r.pct_change).toFixed(2) + '%') : ''],
    ['AMT$',          r => r._amt],
    ['Action',        r => r.consolidated_action ? actionText(actionDisplay(r.consolidated_action)) : ''],
    ['TrTnBBRskRng',  r => r.rr_action || ''],
    ['Trig',          r => r.trig_action ? actionText(actionDisplay(r.trig_action)) : ''],
    ['Source',        r => r.winning_source || ''],
    ['Metric',        r => r._metric],
    ['Reason',        r => _winningReason(r)],
    ['Other Sources', r => otherSourcesText(r)],
    ['Sector',        r => r.sector || ''],
    ['Real Asset Class', r => r.real_asset_class || ''],
    ['MACRO',          r => r.macro_value ? (r.macro_value + (r.macro_turn ? ' ' + r.macro_turn : '')) : ''],
    // kept in CSV even though removed from table
    ['POS$',          r => r.current_position_dollar],
    ['Price',         r => r.last_price],
    ['Change $',      r => r.net_chng],
    ['As Of',         r => fmtAsOfExport(r.export_date, r.export_time, r.loaded_at)],
    ['Held',          r => r.held_today ? 'Y' : 'N'],
    ['In My List',    r => r.in_my_list ? 'Y' : 'N'],
    ['Suppressed',    r => r.suppressed_reason || ''],
  ];
  const esc = (v) => {
    if (v === null || v === undefined) return '';
    const s = String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const lines = [cols.map(c => esc(c[0])).join(',')];
  for (const r of state.rows) {
    lines.push(cols.map(c => esc(c[1](r))).join(','));
  }
  const csv = '\ufeff' + lines.join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `actionable_${state.date || 'export'}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Map a numeric weight back to an {outlook, modifier} label pair.
// Standard convention: BULLISH=3, BEARISH=-3, NEUTRAL=0; "Bench" modifier
// divides the magnitude by 3 → fractional. We infer from magnitude.
function _weightToOutlook(w) {
  if (w === null || w === undefined || w === '' || Number.isNaN(Number(w))) {
    return { label: 'none', cls: 'ol-none', modifier: '' };
  }
  const n = Number(w);
  if (n > 2)       return { label: 'BULLISH', cls: 'ol-bullish', modifier: '' };
  if (n >= 0.5)    return { label: 'BULLISH', cls: 'ol-bullish', modifier: 'Bench' };
  if (n > -0.5 && n < 0.5) return { label: 'NEUTRAL', cls: 'ol-neutral', modifier: '' };
  if (n >= -2)     return { label: 'BEARISH', cls: 'ol-bearish', modifier: 'Bench' };
  return { label: 'BEARISH', cls: 'ol-bearish', modifier: '' };
}

// Render a two-line chip cell. `base` = today's weight, `prev` = yesterday's.
function _outlookChip(base, prev) {
  const a = _weightToOutlook(base);
  const b = _weightToOutlook(prev);
  const aMod = a.modifier ? `<span class="ol-mod">${a.modifier}</span>` : '';
  const bMod = b.modifier ? `<span class="ol-mod">${b.modifier}</span>` : '';
  return `<div class="outlook-cell">
    <div class="ol-today ${a.cls}">${a.label}${aMod}</div>
    <div class="ol-was">was <span class="${b.cls}">${b.label}</span>${bMod}</div>
  </div>`;
}

// Find the winning source's entry inside the source_actions JSONB.
// `sourceActions` may be the parsed array or a JSON string.
function _winningSourceEntry(row) {
  let sa = row.source_actions;
  if (typeof sa === 'string') {
    try { sa = JSON.parse(sa); } catch (_) { sa = []; }
  }
  if (!Array.isArray(sa) || !sa.length) return null;
  const want = (row.winning_source || '').toString();
  return sa.find(s => (s.source || s.source_code || '') === want) || sa[0];
}

// Snapshot date of the winning source's underlying record (ISO string).
function _winningSnapshot(row) {
  const e = _winningSourceEntry(row);
  return (e && e.snapshot_date) ? e.snapshot_date : null;
}

// Reason text for the winning/consolidated action only. Returns '' when the
// winner is a rule group (no per-source entry) so the grid never shows a
// misleading reason borrowed from a non-winning source.
function _winningReason(row) {
  let sa = row.source_actions;
  if (typeof sa === 'string') {
    try { sa = JSON.parse(sa); } catch (_) { sa = []; }
  }
  if (!Array.isArray(sa) || !sa.length) return '';
  const want = (row.winning_source || '').toString();
  const hit = sa.find(s => (s.source || s.source_code || '') === want);
  return hit ? (hit.reason || hit.action_reason || '') : '';
}

// Asset class for the grid/CSV. drv_stks.asset_class is only populated for
// TL-master stocks; ETF-feed / PS symbols (e.g. EQRR) carry the same value in
// position_category. Fall back to it only for those sources.
function _assetClass(r) {
  if (r.asset_class) return r.asset_class;
  const ws = (r.winning_source || '').toUpperCase();
  if (ws === 'ETF' || ws === 'ETFCHG' || ws === 'PS') return r.position_category || '';
  return '';
}

// ---- drilldown TV chart ----
const _DD_TV_MAP = {
  '$SPX':'SP:SPX','SPX':'SP:SPX','$COMP':'NASDAQ:NDX','COMP':'NASDAQ:NDX','COMPQ':'NASDAQ:NDX',
  '$DJI':'DJ:DJI','DJI':'DJ:DJI','INDU':'DJ:DJI','RUT':'TVC:RUT',
  'VIX':'TVC:VIX','VXN':'TVC:VXN','VXD':'TVC:VXD','RVX':'TVC:RVX',
  'OVX':'TVC:OVX','GVZ':'TVC:GVZ','MOVE':'TVC:MOVE',
  'DXY':'TVC:DXY','$DXY':'TVC:DXY',
  '/CL':'TVC:USOIL','/GC':'TVC:GOLD','/ES':'SP:SPX','/NQ':'NASDAQ:NDX','/RTY':'TVC:RUT',
};
let _ddTvSeq = 0;
function _loadDrilldownChart(sym) {
  const el = $('modalTvChart');
  if (!el) return;
  el.innerHTML = '';
  if (!sym || sym.startsWith('$_CASH')) {
    el.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:12px;">No chart</div>';
    return;
  }
  let tvSym = _DD_TV_MAP[sym] || (sym.startsWith('$') ? sym.slice(1) : sym.startsWith('/') ? sym.slice(1)+'1!' : sym);
  const id = 'dd_tv_' + (++_ddTvSeq);
  const wrap = document.createElement('div');
  wrap.id = id;
  wrap.style.cssText = 'width:100%;height:100%;';
  el.appendChild(wrap);
  const s = document.createElement('script');
  s.src = 'https://s3.tradingview.com/tv.js';
  s.onload = () => {
    new TradingView.widget({
      autosize:true, symbol:tvSym, interval:'D',
      timezone:'America/New_York', theme:'light', style:'1', locale:'en',
      enable_publishing:false, allow_symbol_change:true, save_image:false,
      studies:['BB@tv-basicstudies','RSI@tv-basicstudies'],
      container_id:id,
    });
  };
  if (window.TradingView) {
    // already loaded
    new TradingView.widget({
      autosize:true, symbol:tvSym, interval:'D',
      timezone:'America/New_York', theme:'light', style:'1', locale:'en',
      enable_publishing:false, allow_symbol_change:true, save_image:false,
      studies:['BB@tv-basicstudies','RSI@tv-basicstudies'],
      container_id:id,
    });
  } else {
    document.head.appendChild(s);
  }
}

// ---- drilldown ----
async function openDrilldown(row) {
  hideSourcePop();
  state.current = row;
  $('modalTitle').textContent = row.tos_symbol;
  $('modalPrice').textContent = row.last_price != null ? '$' + Number(row.last_price).toFixed(2) : '';
  $('modalSector').textContent = row.sector || '';
  const _ac = row.real_asset_class || '';
  $('modalAssetClass').textContent = _ac;
  $('modalAssetClass').style.display = _ac ? '' : 'none';
  const _posDollar = row.current_position_dollar != null ? 'Pos: ' + fmtUsd(row.current_position_dollar) : '';
  $('modalPositionDollar').textContent = _posDollar;
  $('modalPositionDollar').style.display = _posDollar ? '' : 'none';
  const _cname = row.company_name || '';
  $('modalCompanyName').textContent = _cname;
  $('modalCompanyName').style.display = _cname ? '' : 'none';

  const chgEl = $('modalPriceChange');
  if (row.net_chng != null && row.pct_change != null) {
    const nc = Number(row.net_chng), pc = Number(row.pct_change);
    const chgCls = nc >= 0 ? 'act-buy-strong' : 'act-sell-strong';
    const fmtAmt = v => { const a = Math.abs(v); return (v < 0 ? '-' : '+') + '$' + (a >= 1000 ? Math.round(a).toLocaleString() : a.toFixed(2)); };
    chgEl.innerHTML = `<span class="${chgCls}" style="font-weight:700;font-size:15px;">${fmtAmt(nc)} (${pc.toFixed(2)}%)</span>`;
  } else {
    chgEl.innerHTML = '';
  }

  const action = (row.consolidated_action || 'NONE').toUpperCase();
  const kv = $('modalKv');
  kv.innerHTML = `
    <dt>Action</dt><dd><span class="act-badge ${(actionDisplay(_badgeAction(row)).colorCls || 'act-neutral') + '-tint'}">${actionLabel(row)}</span>${_isOverMaxOverlay(row) ? ` <small class="${_actionColorCls(action)}" style="font-weight:600;font-size:9px;">was ${actionText(actionDisplay(action))}</small>` : ''}</dd>
    <dt>Winning source</dt><dd>${row.winning_source || '—'}</dd>
    <dt>AMT$</dt><dd><strong>${fmtUsd(row._amt) || '—'}</strong></dd>
    <dt>Suppressed</dt><dd>${row.suppressed_reason || '—'}</dd>
  `;

  // Per-source actions table
  const srcTbody = $('modalSources').querySelector('tbody');
  srcTbody.innerHTML = '';
  let sourceList = row.source_actions;
  if (typeof sourceList === 'string') {
    try { sourceList = JSON.parse(sourceList); } catch (_) { sourceList = []; }
  }
  if (Array.isArray(sourceList) && sourceList.length) {
    for (const s of sourceList) {
      const srcCode = s.source || s.source_code || '';
      const tr = document.createElement('tr');
      tr.dataset.cmpsrc = srcCode;
      tr.className = 'cmp-src-row';
      const sa = (s.action || '').toUpperCase();
      const _wfmt = (v) => (v == null || v === '') ? ''
                    : (_isPctSource(srcCode) ? fmtPct(v) : v);
      const todayOl = _weightToOutlook(s.weight ?? s.base_weight);
      const prevOl  = _weightToOutlook(s.prev_weight);
      const todayMod = todayOl.modifier ? ` <span class="ol-mod">${todayOl.modifier}</span>` : '';
      const prevMod  = prevOl.modifier  ? ` <span class="ol-mod">${prevOl.modifier}</span>`  : '';
      tr.innerHTML = `
        <td><span class="cmp-caret">&#9656;</span><strong>${escapeHtml(srcCode)}</strong></td>
        <td>${escapeHtml(s.base_weight_method || s.method || '')}</td>
        <td>${fmtMD(s.snapshot_date)}</td>
        <td class="num">${_wfmt(s.base_weight ?? s.weight)}</td>
        <td class="num">${_wfmt(s.prev_weight)}</td>
        <td class="num">${_wfmt(s.weight_delta)}</td>
        <td>${fmtMD(s.prev_date)}</td>
        <td>${escapeHtml(s.analyst_rank ?? '')}</td>
        <td><span class="${todayOl.cls}" style="font-weight:600;">${todayOl.label}</span>${todayMod}</td>
        <td><span class="${prevOl.cls}">${prevOl.label}</span>${prevMod}</td>
        <td>${s.held_today ? 'Y' : 'N'}</td>
        <td>${sa ? `<span class="act-badge ${(actionDisplay(sa).colorCls || 'act-neutral') + '-tint'}">${actionText(actionDisplay(sa)) || sa}</span>` : ''}</td>
        <td style="font-size:10px;">${escapeHtml(s.reason || s.action_reason || '')}</td>
      `;
      tr.addEventListener('click', () => toggleCmpRow(tr, srcCode));
      srcTbody.appendChild(tr);
    }
  } else {
    srcTbody.innerHTML = '<tr><td colspan="13" style="color:var(--text-2,#666); padding:8px;">No per-source actions recorded.</td></tr>';
  }

  // Rules fires — pills are clickable; clicking one opens the atomic-rule popover
  let fires = row.rules_engine_fires;
  if (typeof fires === 'string') {
    try { fires = JSON.parse(fires); } catch (_) { fires = []; }
  }
  const firesEl = $('modalFires');
  closeAtomicPopover();
  if (Array.isArray(fires) && fires.length) {
    firesEl.innerHTML = '';
    for (const f of fires) {
      const id    = String(f.rule_id || f.id || f);
      const score = (f.score != null) ? ` <span style="opacity:.65;font-size:10px;">${f.score}</span>` : '';
      const span = document.createElement('span');
      span.className = 'act-badge act-badge-sm pill-rule';
      span.innerHTML = `${escapeHtml(id)}${score}${ruleEdgeBadge(id)}`;
      span.dataset.compositeCode = id;
      span.addEventListener('click', (e) => {
        e.stopPropagation();
        openAtomicPopover(row.tos_symbol, row.as_of_date, id, span);
      });
      firesEl.appendChild(span);
      firesEl.appendChild(document.createTextNode(' '));
    }
  } else {
    firesEl.textContent = '—';
  }

  // Pre-fill snooze date
  $('userAction').value = 'DONE';
  $('userTarget').value = '';
  $('snoozeUntil').value = '';
  $('userNotes').value = '';
  $('actionStatus').textContent = '';

  await loadComparison(row.tos_symbol, row.as_of_date);
  await loadHistory(row.tos_symbol);
  loadRRAnalysis(row.tos_symbol, row.as_of_date);
  _loadDrilldownChart(row.tos_symbol);

  $('modalBackdrop').classList.add('open');
}

// ---- inline current-vs-previous record comparison ----
// loadComparison fetches the two source records each rule compared (current
// snapshot vs the prior one) and caches them by source code. Clicking a row in
// the Per-source actions table expands an inline panel showing every column of
// both records side by side. Source-agnostic: whatever columns the API returns
// are rendered, so a new source needs no client change.
const _cmpData = new Map();   // source code -> comparison row from the API

async function loadComparison(symbol, asOf) {
  _cmpData.clear();
  let rows = [];
  try {
    rows = await fetchJson('/api/actionable/comparison?symbol=' +
      encodeURIComponent(symbol) + '&date=' + encodeURIComponent(asOf || ''));
  } catch (_) { rows = []; }
  if (Array.isArray(rows)) {
    for (const r of rows) _cmpData.set(r.source || '', r);
  }
}

// Toggle the inline comparison panel under a per-source row. One open at a time.
function toggleCmpRow(tr, srcCode) {
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('cmp-expand-row')) {
    next.remove();
    tr.classList.remove('expanded');
    return;
  }
  document.querySelectorAll('#modalSources tr.cmp-expand-row')
          .forEach(el => el.remove());
  document.querySelectorAll('#modalSources tr.cmp-src-row.expanded')
          .forEach(el => el.classList.remove('expanded'));
  const exp = document.createElement('tr');
  exp.className = 'cmp-expand-row';
  const td = document.createElement('td');
  td.colSpan = 13;
  td.innerHTML = _comparisonPanelHtml(srcCode);
  exp.appendChild(td);
  tr.after(exp);
  tr.classList.add('expanded');
}

// Build the Field / Current / Previous / Delta table for one source.
function _comparisonPanelHtml(srcCode) {
  const c = _cmpData.get(srcCode);
  if (!c) {
    return '<div class="cmp-panel"><div class="cmp-empty">No comparison record available for ' +
           escapeHtml(srcCode) + '.</div></div>';
  }
  const cur = c.current || {}, prv = c.previous || {};
  const cf = cur.fields || {}, pf = prv.fields || {};
  // Only the classifier's decision-driving field(s) get highlighted.
  const drivers = new Set(c.driver_fields || []);
  const keys = [];
  for (const k of Object.keys(cf)) keys.push(k);
  for (const k of Object.keys(pf)) if (!keys.includes(k)) keys.push(k);

  const fmtV = (k, v) => (v === null || v === undefined || v === '')
    ? '' : (k === 'pct_delta' ? fmtPct(v) : escapeHtml(String(v)));
  let body =
    '<tr><td class="cmp-field">snapshot_date</td>' +
    '<td class="cmp-val">' + (cur.dropped ? '' : fmtMD(cur.snapshot_date)) + '</td>' +
    '<td class="cmp-val">' + (prv.dropped ? '' : fmtMD(prv.snapshot_date)) + '</td>' +
    '<td class="cmp-val"><span class="cmp-delta-none">&mdash;</span></td></tr>';
  if (!keys.length) {
    body += '<tr><td colspan="4" class="cmp-empty">No record columns returned.</td></tr>';
  }
  for (const k of keys) {
    const cv = cf[k], pv = pf[k];
    const isPct = (k === 'pct_delta');
    const changed = String(cv ?? '') !== String(pv ?? '');
    let delta = '<span class="cmp-delta-none">&mdash;</span>';
    if (changed) {
      const cn = Number(cv), pn = Number(pv);
      if (cv != null && pv != null && cv !== '' && pv !== '' &&
          isFinite(cn) && isFinite(pn)) {
        const d = cn - pn;
        const cls = d > 0 ? 'cmp-delta-up' : 'cmp-delta-down';
        const arrow = d > 0 ? '&#9650;' : '&#9660;';
        const mag = isPct ? fmtPct(Math.abs(d)) : formatNum(Math.abs(d));
        delta = '<span class="' + cls + '">' + arrow + ' ' + mag + '</span>';
      } else {
        delta = '<span class="cmp-delta-changed">changed</span>';
      }
    }
    body += '<tr class="' + (drivers.has(k) ? 'cmp-changed' : '') + '">' +
            '<td class="cmp-field">' + escapeHtml(k) + '</td>' +
            '<td class="cmp-val">' + fmtV(k, cv) + '</td>' +
            '<td class="cmp-val">' + fmtV(k, pv) + '</td>' +
            '<td class="cmp-val">' + delta + '</td></tr>';
  }
  const sideLabel = (rec, kind) => (rec && rec.dropped)
    ? ('not in ' + kind + ' bundle')
    : ((fmtMD(rec && rec.snapshot_date) || '?') +
       ((rec && rec.weight != null) ? (' &middot; wt ' + formatNum(rec.weight)) : ''));
  const _actCode = (c.action || '').toUpperCase();
  const act = _actCode ? '<span class="act-badge ' +
              escapeHtml((actionDisplay(_actCode).colorCls || 'act-neutral') + '-tint') + '">' +
              escapeHtml(actionText(actionDisplay(_actCode)) || _actCode) + '</span> ' : '';
  return '<div class="cmp-panel">' +
    '<div class="cmp-panel-head">' +
      '<span class="cmp-src">' + act + escapeHtml(srcCode) + ' &middot; record comparison</span>' +
      '<span class="cmp-meta">current ' + sideLabel(cur, 'current') +
      '  vs  previous ' + sideLabel(prv, 'previous') + '</span>' +
    '</div>' +
    '<table class="cmp-table">' +
      '<thead><tr><th>Field</th><th>Current</th><th>Previous</th><th>&Delta;</th></tr></thead>' +
      '<tbody>' + body + '</tbody>' +
    '</table>' +
    '<div class="cmp-empty">Highlighted = the field(s) that drive ' + escapeHtml(srcCode) + '&#39;s action. Other rows may differ but are informational.</div>' +
  '</div>';
}

// ---- atomic-rule popover (composite drill-down) ----
const traceCache = new Map();   // key = symbol + '@' + date  ->  trace payload

async function fetchTrace(symbol, asOf) {
  const key = symbol + '@' + asOf;
  if (traceCache.has(key)) return traceCache.get(key);
  const url = '/api/trace/' + encodeURIComponent(symbol) + '?date=' + encodeURIComponent(asOf);
  const payload = await fetchJson(url);
  traceCache.set(key, payload);
  return payload;
}

function closeAtomicPopover() {
  const pop = $('atomicPopover');
  if (pop) pop.classList.remove('open');
  // Clear any "active" pill highlight
  document.querySelectorAll('#modalFires .pill-rule.active')
          .forEach(el => el.classList.remove('active'));
}

async function openAtomicPopover(symbol, asOf, compositeCode, pillEl) {
  const pop = $('atomicPopover');
  const codeEl = $('popComposite');
  const loadingEl = $('popLoading');
  const contentEl = $('popContent');

  // Toggle off if the same pill is clicked again
  if (pillEl && pillEl.classList.contains('active')) {
    closeAtomicPopover();
    return;
  }
  closeAtomicPopover();
  if (pillEl) pillEl.classList.add('active');

  codeEl.textContent = compositeCode;
  contentEl.innerHTML = '';
  loadingEl.style.display = 'block';
  pop.classList.add('open');

  let trace;
  try {
    trace = await fetchTrace(symbol, asOf);
  } catch (e) {
    loadingEl.style.display = 'none';
    contentEl.innerHTML = `<div style="color:#8c1d1d;">Failed to load trace: ${escapeHtml(e.message)}</div>`;
    return;
  }
  loadingEl.style.display = 'none';

  // Filter atomic rules whose rolls_into contains this composite_code
  const atomics = (trace.atomics || []).filter(a =>
    Array.isArray(a.rolls_into) && a.rolls_into.includes(compositeCode)
  );

  if (!atomics.length) {
    contentEl.innerHTML = `<div style="color:var(--text-2,#666); padding:4px;">No atomic rules map to this composite, or the composite has only data/composite members.</div>`;
    return;
  }

  // Sort: fired first (by absolute weight desc), then unfired
  atomics.sort((x, y) => {
    if ((x.fired ? 1 : 0) !== (y.fired ? 1 : 0)) return (y.fired ? 1 : 0) - (x.fired ? 1 : 0);
    return Math.abs(y.weight || 0) - Math.abs(x.weight || 0);
  });

  const rows = atomics.map(a => {
    const fired = !!a.fired;
    const wt = Number(a.weight) || 0;
    const wtClass = wt > 0 ? 'wt-pos' : (wt < 0 ? 'wt-neg' : '');
    return `
      <tr class="${fired ? 'fired' : ''}">
        <td>${a.id ?? ''}</td>
        <td><strong>${escapeHtml(a.rule_name || '')}</strong></td>
        <td style="font-family:ui-monospace,Menlo,monospace; opacity:.75;">${escapeHtml(a.ma_column || '')}</td>
        <td class="num">${formatNum(a.value)}</td>
        <td class="num">${formatNum(a.brkeout_from)}</td>
        <td class="num">${formatNum(a.brkeout_to)}</td>
        <td class="num ${wtClass}">${formatNum(a.weight)}</td>
        <td>${fired ? '✓' : ''}</td>
      </tr>`;
  }).join('');

  contentEl.innerHTML = `
    <table class="atomic-table">
      <thead>
        <tr>
          <th style="width:30px;">#</th>
          <th>Rule</th>
          <th>MA column</th>
          <th class="num">Value</th>
          <th class="num">Brk From</th>
          <th class="num">Brk To</th>
          <th class="num">Weight</th>
          <th style="width:30px;">Fired</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="font-size:10px; color:var(--text-2,#666); padding-top:4px;">
      ${atomics.filter(a => a.fired).length} of ${atomics.length} atomic rules fired for this composite.
    </div>`;
}

function formatNum(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (!isFinite(n)) return '';
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(3).replace(/\.?0+$/, '');
}

async function loadRRAnalysis(symbol, date) {
  const sec = $('rrSection');
  const el  = $('rrChart');
  sec.style.display = 'none';
  el.innerHTML = '<span style="color:#94a3b8;font-size:12px;">Loading…</span>';
  try {
    const data = await fetchJson(`/api/actionable/rr-analysis?symbol=${encodeURIComponent(symbol)}&date=${encodeURIComponent(date)}`);
    if (data && (data.levels.lrr != null || data.levels.trr != null ||
                 data.levels.trend != null || data.levels.trade != null)) {
      sec.style.display = '';
      if (window.td_common && window.td_common.renderRRAnalysis) {
        window.td_common.renderRRAnalysis(data, el, symbol, date);
      }
    }
  } catch(_) {}
}


async function loadHistory(symbol) {
  const tb = $('modalHistory').querySelector('tbody');
  tb.innerHTML = '';
  $('modalHistoryEmpty').style.display = 'none';
  try {
    const rows = await fetchJson('/api/actionable/history?symbol=' + encodeURIComponent(symbol) + '&limit=50');
    if (!rows.length) {
      $('modalHistoryEmpty').style.display = 'block';
      return;
    }
    for (const h of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${(h.acted_at || '').toString().slice(0, 19).replace('T', ' ')}</td>
        <td>${h.user_id || ''}</td>
        <td>${h.user_action || ''}</td>
        <td>${h.user_action_target || ''}</td>
        <td>${(h.winning_source || '')} / ${h.winning_priority ?? ''}</td>
        <td style="font-size:10px;">${escapeHtml(h.user_notes || '')}</td>
      `;
      tb.appendChild(tr);
    }
  } catch (e) {
    $('modalHistoryEmpty').textContent = 'Failed to load history: ' + e.message;
    $('modalHistoryEmpty').style.display = 'block';
  }
}

async function saveUserAction() {
  if (!state.current) return;
  const payload = {
    as_of_date: state.current.as_of_date,
    user_action: $('userAction').value,
    user_action_target: $('userTarget').value || null,
    snooze_until: $('snoozeUntil').value || null,
    user_notes: $('userNotes').value || null,
  };
  try {
    const r = await fetchJson('/api/actionable/' + encodeURIComponent(state.current.tos_symbol) + '/action', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    $('actionStatus').textContent = 'Saved (log id ' + (r.log_id || '?') + ')';
    await loadHistory(state.current.tos_symbol);
    // Reload grid so the chip updates
    loadActionable();
  } catch (e) {
    $('actionStatus').textContent = 'Save failed: ' + e.message;
  }
}

async function dismissUserAction() {
  // Quick "dismiss this from the actionable list" — log a SKIPPED with no snooze.
  // Notes are preserved if the user typed any; target is forced null because
  // SKIPPED is a no-op-with-rationale, not an override.
  if (!state.current) return;
  const payload = {
    as_of_date: state.current.as_of_date,
    user_action: 'SKIPPED',
    user_action_target: null,
    snooze_until: null,
    user_notes: $('userNotes').value || 'dismissed',
  };
  try {
    const r = await fetchJson('/api/actionable/' + encodeURIComponent(state.current.tos_symbol) + '/action', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    $('actionStatus').textContent = 'Dismissed (log id ' + (r.log_id || '?') + ')';
    await loadHistory(state.current.tos_symbol);
    loadActionable();
  } catch (e) {
    $('actionStatus').textContent = 'Dismiss failed: ' + e.message;
  }
}

// ---- per-row snooze toggle ----
// The row "Snooze" button logs a SKIPPED user action for (snapshot date,
// symbol); "Un-snooze" clears it. Snoozed rows are hidden unless "Show
// acted/snoozed" is on. The action is keyed to the snapshot date, so the next
// data load (a new snapshot date) surfaces the row again.
async function toggleSuppress(symbol, isSuppressed) {
  if (!symbol || !state.date) return;
  try {
    if (isSuppressed) {
      await fetchJson('/api/actionable/' + encodeURIComponent(symbol) +
        '/action?date=' + encodeURIComponent(state.date), { method: 'DELETE' });
    } else {
      await fetchJson('/api/actionable/' + encodeURIComponent(symbol) + '/action', {
        method: 'POST',
        body: JSON.stringify({ as_of_date: state.date,
                               user_action: 'SKIPPED',
                               user_notes: 'suppressed' }),
      });
    }
    await loadActionable();
  } catch (e) {
    showStatus('Snooze toggle failed: ' + e.message, 'error');
  }
}

// ---- TradingView tape toggle --------------------------------------------------
const _TV_LS_KEY = 'act_tv_tape';

// Regular session (Mon–Fri 9:30–16:00 ET): cash index symbols
const _TV_SYMS_REGULAR = [
  {proName:'FOREXCOM:SPXUSD',  title:'S&P 500'},
  {proName:'FOREXCOM:NSXUSD',  title:'Nasdaq 100'},
  {proName:'FOREXCOM:DJI',     title:'Dow Jones'},
  {proName:'FOREXCOM:US2000',  title:'Russell 2K'},
  {proName:'CAPITALCOM:VIX',   title:'VIX'},
  {proName:'CAPITALCOM:DXY',   title:'Dollar'},
  {proName:'TVC:GOLD',         title:'Gold'},
  {proName:'TVC:SILVER',       title:'Silver'},
  {proName:'TVC:USOIL',        title:'WTI Crude'},
  {proName:'TVC:UKOIL',        title:'Brent'},
  {proName:'CAPITALCOM:NATURALGAS', title:'Nat Gas'},
  {proName:'BITSTAMP:BTCUSD',  title:'Bitcoin'},
  {proName:'FX:EURUSD',        title:'EUR/USD'},
  {proName:'FX:USDJPY',        title:'USD/JPY'},
  {proName:'FX:GBPUSD',        title:'GBP/USD'},
];

// Futures session: FOREXCOM/OANDA CFD equivalents — these track the futures
// overnight and work in the free TradingView embed (CME contracts require a
// paid CME data subscription and show "No Data" in free embeds).
const _TV_SYMS_FUTURES = [
  {proName:'FOREXCOM:SPXUSD',  title:'S&P Fut'},
  {proName:'FOREXCOM:NSXUSD',  title:'Nasdaq Fut'},
  {proName:'FOREXCOM:DJI',     title:'Dow Fut'},
  {proName:'FOREXCOM:US2000',  title:'Russell Fut'},
  {proName:'CAPITALCOM:VIX',   title:'VIX'},
  {proName:'CAPITALCOM:DXY',   title:'Dollar'},
  {proName:'TVC:GOLD',         title:'Gold'},
  {proName:'TVC:SILVER',       title:'Silver'},
  {proName:'TVC:USOIL',        title:'WTI Crude'},
  {proName:'TVC:UKOIL',        title:'Brent'},
  {proName:'CAPITALCOM:NATURALGAS', title:'Nat Gas'},
  {proName:'BITSTAMP:BTCUSD',  title:'Bitcoin'},
  {proName:'FX:EURUSD',        title:'EUR/USD'},
  {proName:'FX:USDJPY',        title:'USD/JPY'},
  {proName:'FX:GBPUSD',        title:'GBP/USD'},
];

// Returns 'regular' | 'futures' | 'none'
// Regular:  Mon–Fri 09:30–16:00 ET
// Futures:  Sun 18:00 ET through Fri 17:00 ET, outside regular hours
//           (US equity futures run Sun 18:00 – Fri 17:00 ET with daily ~5–5:15 PM break)
// None:     Fri 17:00 ET – Sun 18:00 ET (weekend, futures closed)
function _tvMode() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short', hour: 'numeric', minute: 'numeric', hour12: false,
  }).formatToParts(new Date());
  const get = t => (parts.find(p => p.type === t) || {}).value || '';
  const day  = get('weekday');
  const mins = parseInt(get('hour'), 10) * 60 + parseInt(get('minute'), 10);

  if (day === 'Sat') return 'none';
  if (day === 'Sun' && mins < 1080) return 'none';   // before 18:00 ET Sunday
  if (day === 'Fri' && mins >= 1020) return 'none';  // Fri 17:00 ET and later
  // Regular trading window
  if (['Mon','Tue','Wed','Thu','Fri'].includes(day) && mins >= 570 && mins < 960) return 'regular';
  return 'futures';
}

function _buildTvWidget(symbols) {
  const wrapper = $('tv-tape-wrapper');
  if (!wrapper) return;
  wrapper.innerHTML = '';
  const container = document.createElement('div');
  container.className = 'tradingview-widget-container';
  const wd = document.createElement('div');
  wd.className = 'tradingview-widget-container__widget';
  container.appendChild(wd);
  const sc = document.createElement('script');
  sc.type = 'text/javascript';
  sc.src = 'https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js';
  sc.async = true;
  sc.textContent = JSON.stringify({
    symbols, showSymbolLogo: false, isTransparent: false,
    displayMode: 'adaptive', colorTheme: 'light', locale: 'en',
  });
  container.appendChild(sc);
  wrapper.appendChild(container);
}

function _setTvTape(visible) {
  const wrapper = $('tv-tape-wrapper');
  if (wrapper) wrapper.style.display = visible ? '' : 'none';
  const btn = $('tvToggleBtn');
  if (btn) {
    btn.title = visible ? 'Hide TradingView tape' : 'Show TradingView tape';
    btn.classList.toggle('active', visible);
    btn.disabled = false;
  }
  try { localStorage.setItem(_TV_LS_KEY, visible ? '1' : '0'); } catch (_) {}
}

function _initTvToggle() {
  const mode = _tvMode();
  const btn = $('tvToggleBtn');

  if (mode === 'none') {
    // Futures closed — hide tape, disable button
    const wrapper = $('tv-tape-wrapper');
    if (wrapper) wrapper.style.display = 'none';
    if (btn) {
      btn.innerHTML = 'TV &#9660;';
      btn.title = 'TradingView tape (market closed)';
      btn.disabled = true;
      btn.classList.remove('active');
    }
    return;
  }

  // Load the correct symbol set for the current session
  _buildTvWidget(mode === 'regular' ? _TV_SYMS_REGULAR : _TV_SYMS_FUTURES);

  // Visibility: respect user's localStorage preference, default to visible
  let show = true;
  try {
    const stored = localStorage.getItem(_TV_LS_KEY);
    if (stored !== null) show = stored === '1';
  } catch (_) {}
  _setTvTape(show);

  if (btn) btn.addEventListener('click', () => {
    const wrapper = $('tv-tape-wrapper');
    _setTvTape(!wrapper || wrapper.style.display === 'none');
  });
}

// ---- wire up ----
document.addEventListener('DOMContentLoaded', async () => {
  // Restore filters before loading data
  loadFiltersFromStorage();
  // initSorting must run before loadDates/renderGrid so th.dataset.label is
  // captured from the clean header text (before sort indicators are injected).
  initSorting();
  _initSymTape();
  initSymTilePop();
  initGridSymClick();
  initEcoBarClick();
  _initSidePanels();

  await loadSources();
  await loadDates();
  checkFreshness();

  // Sync UI to restored state
  syncFilterUi();

  $('datePicker').addEventListener('change', (e) => {
    state.date = e.target.value;
    loadActionable();
    checkFreshness();
    checkEodFeed();
  });
  $('refreshBtn').addEventListener('click', () => {
    loadActionable();
    checkFreshness();
    checkEodFeed();
  });
  $('staleRederiveBtn').addEventListener('click', rederiveStale);
  $('exportCsvBtn').addEventListener('click', exportCsv);
  initSourcePopover();
  // Inline action buttons (Pass 3)
  $('actBody').addEventListener('click', (e) => {
    const doneBtn = e.target.closest('.btn-inline-done');
    if (doneBtn) {
      e.stopPropagation();
      // Use final call code as the action if available, else 'DONE'
      const actCode = doneBtn.dataset.fc || 'DONE';
      inlineAction(doneBtn.dataset.sym, actCode);
      return;
    }
    const skipBtn = e.target.closest('.btn-inline-skip');
    if (skipBtn) { e.stopPropagation(); inlineAction(skipBtn.dataset.sym, 'SKIPPED'); return; }
    const snzBtn = e.target.closest('.btn-inline-snz');
    if (snzBtn) { e.stopPropagation(); inlineAction(snzBtn.dataset.sym, 'SNOOZED'); return; }
    const chk = e.target.closest('.row-check');
    if (chk) {
      e.stopPropagation();
      const sym = chk.dataset.sym;
      if (chk.checked) state.selected.add(sym); else state.selected.delete(sym);
      renderBulkBar();
      const allChk = $('bulkSelectAll');
      if (allChk) {
        const vis = Array.from(document.querySelectorAll('.row-check'));
        allChk.checked = vis.length > 0 && vis.every(c => c.checked);
        allChk.indeterminate = state.selected.size > 0 && !allChk.checked;
      }
      return;
    }
    const btn = e.target.closest('.btn-suppress');
    if (!btn) return;
    e.stopPropagation();
    toggleSuppress(btn.dataset.sym, btn.dataset.suppressed === '1');
  });

  // Bulk select-all
  $('bulkSelectAll').addEventListener('change', (e) => {
    const vis = Array.from(document.querySelectorAll('.row-check'));
    if (e.target.checked) vis.forEach(c => { state.selected.add(c.dataset.sym); c.checked = true; });
    else { state.selected.clear(); vis.forEach(c => { c.checked = false; }); }
    renderBulkBar();
  });

  // Bulk action buttons
  $('bulkDoneBtn').addEventListener('click', () => bulkAction('DONE'));
  $('bulkSkipBtn').addEventListener('click', () => bulkAction('SKIPPED'));
  $('bulkSnzBtn').addEventListener('click',  () => bulkAction('SNOOZED'));
  $('bulkClearBtn').addEventListener('click', () => { state.selected.clear(); renderBulkBar(); renderGrid(); });

  // Focus mode
  $('focusModeBtn').addEventListener('click', openFocusMode);
  $('fcDoneBtn').addEventListener('click', () => focusAdvance('DONE'));
  $('fcSkipBtn').addEventListener('click', () => focusAdvance('SKIPPED'));
  $('fcSnzBtn').addEventListener('click',  () => focusAdvance('SNOOZED'));
  $('fcNextBtn').addEventListener('click', () => focusAdvance(null));
  $('fcCloseBtn').addEventListener('click', () => $('focusBackdrop').classList.remove('open'));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && $('focusBackdrop').classList.contains('open')) {
      $('focusBackdrop').classList.remove('open');
    }
  });

  // ── Filter zone wire-ups ────────────────────────────────────────────────────
  $('sourceFilter').addEventListener('change', (e) => {
    state.filters.source = e.target.value;
    applyClientFilter();
  });
  $('accountFilter').addEventListener('change', (e) => {
    state.filters.account = e.target.value;
    applyClientFilter();
  });
  $('heldOnly').addEventListener('click', () => {
    state.filters.held_only = !state.filters.held_only;
    $('heldOnly').classList.toggle('active', state.filters.held_only);
    applyClientFilter();
  });
  $('showHidden').addEventListener('click', () => {
    state.filters.show_hidden = !state.filters.show_hidden;
    $('showHidden').classList.toggle('active', state.filters.show_hidden);
    // show_hidden also controls whether acted/suppressed rows are fetched from the API
    loadActionable();
  });
  $('symbolSearch').addEventListener('input', (e) => {
    state.filters.symbol_search = e.target.value;
    applyClientFilter();
  });

  // TASK_66: Bull Prob minimum filter
  const bullProbFilterEl = $('bullProbFilter');
  if (bullProbFilterEl) {
    bullProbFilterEl.addEventListener('input', (e) => {
      state.filters.bull_prob_min = parseFloat(e.target.value) || 0;
      applyClientFilter();
    });
  }

  // TASK_69: Agreement class filter
  const agreementFilterEl = $('agreementFilter');
  if (agreementFilterEl) {
    agreementFilterEl.addEventListener('change', (e) => {
      state.filters.agreement_class = e.target.value || '';
      applyClientFilter();
    });
  }

  // Conviction segmented control
  $('convictionCtrl').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-conv]');
    if (!btn) return;
    state.filters.conviction = btn.dataset.conv;
    document.querySelectorAll('#convictionCtrl button').forEach(b =>
      b.classList.toggle('seg-active', b === btn));
    applyClientFilter();
  });

  // Actionable-only toggle
  $('actionableOnlyBtn').addEventListener('click', () => {
    state.filters.actionable_only = !state.filters.actionable_only;
    syncFilterUi();
    applyClientFilter();
  });

  // TradingView tape toggle
  _initTvToggle();

  // Clear all filters
  $('clearFiltersBtn').addEventListener('click', clearAllFilters);

const _closeModal = () => {
    $('modalBackdrop').classList.remove('open');
    const tc = $('modalTvChart'); if (tc) tc.innerHTML = '';
  };
  $('modalClose').addEventListener('click', _closeModal);
  $('modalBackdrop').addEventListener('click', (e) => {
    if (e.target === $('modalBackdrop')) _closeModal();
  });
  $('saveActionBtn').addEventListener('click', saveUserAction);
  $('dismissActionBtn').addEventListener('click', dismissUserAction);
  $('closePop').addEventListener('click', () => $('detailPop')?.classList.remove('open'));

  // ── Side panel toggle ─────────────────────────────────────────────────────
  const _sideEl  = $('actSidePanel');
  const _sideBtn = $('sidePanelBtn');
  if (_sideEl && _sideBtn) {
    if (localStorage.getItem('actSidePinned') === '1') {
      _sideEl.classList.add('pinned');
      _sideBtn.classList.add('sp-active');
      loadSidePanels();
    }
    _sideBtn.addEventListener('click', () => {
      const pinned = _sideEl.classList.toggle('pinned');
      _sideBtn.classList.toggle('sp-active', pinned);
      localStorage.setItem('actSidePinned', pinned ? '1' : '0');
      if (pinned) loadSidePanels();
    });
  }

  // ── Action column hover popup ──────────────────────────────────────────────
  setupActionCol();
  // ── TrTnBBRskRng column: lazy-load action + hover tooltip ─────────────────
  document.addEventListener('DOMContentLoaded', setupRRActionCol);
  setupRRActionCol();
});

// ── Action-cell hover popup ────────────────────────────────────────────────
// Builds a glance-level "why" popup from fields already on the row.
// Reuses the same fixed-position tooltip pattern as the TrTnBBRskRng popup.

function _actionPopHtml(sym) {
  const r = state.rows.find(row => row.tos_symbol === sym);
  if (!r) return '';

  // Winning source entry
  const winEntry = _winningSourceEntry(r);
  const winSrc   = r.winning_source || (winEntry && (winEntry.source || winEntry.source_code)) || '';
  const winMethod = (winEntry && (winEntry.base_weight_method || winEntry.method)) || '';
  const winReason = _winningReason(r);

  // Section helpers
  const sec = label =>
    `<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:6px 0 2px;">${label}</div>`;
  const kv = (k, v) =>
    `<div style="display:flex;justify-content:space-between;gap:10px;margin-bottom:2px;">
       <span style="color:#475569;white-space:nowrap;">${k}</span>
       <span style="font-weight:600;color:#0f172a;text-align:right;">${v}</span>
     </div>`;

  // ── Header ────────────────────────────────────────────────────────────────
  const _hIc = actionIcon(_badgeAction(r));
  const _hPrice = r.last_price != null ? fmtUsd(r.last_price) : '';
  let html = `<div style="font-weight:700;color:#0f172a;margin-bottom:6px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;display:flex;align-items:baseline;gap:6px;">` +
    `<span>${escapeHtml(sym)}</span>` +
    `<span class="act-badge ${(actionDisplay(_badgeAction(r)).colorCls || 'act-neutral') + '-tint'}">${escapeHtml(actionLabel(r))}</span>` +
    `<span style="font-size:10px;font-weight:400;color:#475569;">${escapeHtml(_hIc.label)}</span>` +
    (_hPrice ? `<span style="margin-left:auto;font-size:12px;font-weight:700;color:#0f172a;">${escapeHtml(_hPrice)}</span>` : '') +
    `</div>`;

  // ── Suppression ────────────────────────────────────────────────────────────
  if (r.suppressed_reason) {
    html += `<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:4px;padding:4px 8px;margin-bottom:6px;font-size:10px;color:#991b1b;font-weight:600;">` +
      `Suppressed: ${escapeHtml(r.suppressed_reason)}</div>`;
  }

  // ── Winning source ─────────────────────────────────────────────────────────
  if (winSrc) {
    html += sec('Winning Source');
    html += kv('Source', escapeHtml(winSrc));
    if (winMethod) html += kv('Method/Metric', escapeHtml(winMethod));
    if (winReason) {
      html += `<div style="font-size:10px;color:#475569;margin-top:3px;white-space:normal;line-height:1.4;">` +
        `${escapeHtml(winReason)}</div>`;
    }
  }

  // ── Other sources ──────────────────────────────────────────────────────────
  let sources = r.source_actions;
  if (typeof sources === 'string') { try { sources = JSON.parse(sources); } catch (_) { sources = []; } }
  if (Array.isArray(sources) && sources.length) {
    // Winning first, then others sorted by action severity
    const winFirst = sources.filter(s => (s.source || s.source_code || '') === winSrc);
    const others = sources.filter(s => (s.source || s.source_code || '') !== winSrc);
    others.sort((a, b) =>
      (ACTION_RANK[(b.action || '').toUpperCase()] || 0) -
      (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
    const ordered = [...winFirst, ...others];

    html += sec('All Sources');
    for (const s of ordered) {
      const srcCode = s.source || s.source_code || '?';
      const srcAct  = (s.action || '').toUpperCase() || '?';
      const isWin   = srcCode === winSrc;
      const ic      = actionIcon(srcAct);
      const actText = actionText(actionDisplay(srcAct)) || srcAct;
      const dt      = fmtMD(s.snapshot_date) || '—';
      const rsn     = s.reason || '';
      html += `<div style="display:flex;align-items:baseline;gap:5px;margin-bottom:3px;font-size:10px;">` +
        `<span style="min-width:10px;color:#16a34a;font-weight:700;">${isWin ? '✓' : ''}</span>` +
        `<span style="min-width:32px;color:#475569;font-weight:600;">${escapeHtml(srcCode)}</span>` +
        `<span style="font-family:ui-monospace,monospace;font-size:12px;font-weight:700;color:${ic.color};min-width:14px;text-align:center;" title="${escapeHtml(ic.title)}">${ic.glyph}</span>` +
        `<span style="min-width:46px;color:#0f172a;font-weight:600;">${escapeHtml(actText)}</span>` +
        `<span style="min-width:30px;color:#94a3b8;">${escapeHtml(dt)}</span>` +
        `<span style="color:#475569;white-space:normal;line-height:1.3;">${escapeHtml(rsn)}</span>` +
        `</div>`;
    }
  }

  // ── Sizing ─────────────────────────────────────────────────────────────────
  const hasSize = r.current_position_dollar != null || r.suggested_target_dollar != null ||
                  r.target_min_dollar != null || r.target_max_dollar != null || r._amt != null;
  if (hasSize) {
    html += sec('Sizing');
    if (r.current_position_dollar != null)  html += kv('Current Pos $', fmtUsd(r.current_position_dollar));
    if (r.suggested_target_dollar != null)  html += kv('Target $',      fmtUsd(r.suggested_target_dollar));
    if (r.target_min_dollar != null)        html += kv('Min $',         fmtUsd(r.target_min_dollar));
    if (r.target_max_dollar != null)        html += kv('Max $',         fmtUsd(r.target_max_dollar));
    if (r._amt != null)                     html += kv('AMT$',          fmtUsd(r._amt));
  }

  return html;
}

function setupActionCol() {
  let tip = document.getElementById('actDetailTip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'actDetailTip';
    tip.style.cssText = 'position:fixed;z-index:9999;display:none;background:#fff;color:#1e293b;' +
      'border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;font-size:11px;line-height:1.6;max-width:300px;' +
      'box-shadow:0 4px 16px rgba(0,0,0,0.12);pointer-events:none;';
    document.body.appendChild(tip);
  }

  const body = $('actBody');
  if (!body) return;

  body.addEventListener('mouseover', (e) => {
    const ic = e.target.closest('.act-main-ic');
    if (!ic) return;
    const cell = ic.closest('.act-action-cell');
    if (!cell) return;
    const sym = cell.dataset.sym;
    if (!sym) return;
    tip.innerHTML = _actionPopHtml(sym);
    const rect = ic.getBoundingClientRect();
    tip.style.display = 'block';
    const tipW = tip.offsetWidth;
    let left = rect.right + 8;
    if (left + tipW > window.innerWidth - 4) left = rect.left - tipW - 8;
    tip.style.left = Math.max(4, left) + 'px';
    tip.style.top  = Math.min(rect.top, window.innerHeight - tip.offsetHeight - 8) + 'px';
  });

  body.addEventListener('mouseout', (e) => {
    if (e.relatedTarget && e.relatedTarget.closest('.act-main-ic')) return;
    tip.style.display = 'none';
  });
}

// Cache keyed by "sym@date"
const _rrDetailCache = new Map();

async function _fetchRRDetail(sym, date) {
  const key = sym + '@' + date;
  if (_rrDetailCache.has(key)) return _rrDetailCache.get(key);
  try {
    const d = await fetchJson(`/api/actionable/rr-detail?symbol=${encodeURIComponent(sym)}&date=${encodeURIComponent(date)}`);
    _rrDetailCache.set(key, d);
    return d;
  } catch(_) { return null; }
}

function setupRRActionCol() {
  let tip = document.getElementById('rrDetailTip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'rrDetailTip';
    tip.style.cssText = 'position:fixed;z-index:9999;display:none;background:#fff;color:#1e293b;' +
      'border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;font-size:11px;line-height:1.6;max-width:320px;' +
      'box-shadow:0 4px 16px rgba(0,0,0,0.12);pointer-events:none;';
    document.body.appendChild(tip);
  }

  const fmt2 = v => v == null ? '—' : Number(v).toFixed(2);
  const scoreCol = v => v == null ? '#94a3b8' : v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#94a3b8';

  const body = $('actBody');
  if (!body) return;

  body.addEventListener('mouseover', async (e) => {
    const ic = e.target.closest('.rr-main-ic');
    if (!ic) return;
    const cell = ic.closest('.rr-action-cell');
    if (!cell) return;
    const sym = cell.dataset.sym, date = cell.dataset.date;
    if (!sym || !date) return;

    const d = await _fetchRRDetail(sym, date);
    if (!d) return;

    // Update sub-line in the cell with the Trend/Trade · BB · RR component triplet.
    const subLine = cell.querySelector('.rr-sub-line');
    if (subLine && !subLine.dataset.filled) {
      const _sc = v => v == null ? '—' : String(v);
      const _scColor = v => v == null ? '#94a3b8' : v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#64748b';
      subLine.innerHTML =
        `<span style="color:${_scColor(d.tn_td_action)}">${_sc(d.tn_td_action)}</span>` +
        `<span style="color:#cbd5e1;margin:0 1px;">·</span>` +
        `<span style="color:${_scColor(d.bb_action)}">${_sc(d.bb_action)}</span>` +
        `<span style="color:#cbd5e1;margin:0 1px;">·</span>` +
        `<span style="color:${_scColor(d.rr_action)}">${_sc(d.rr_action)}</span>`;
      subLine.dataset.filled = '1';
    }

    // Look up row price for the tooltip header.
    const rowData = state.rows.find(r => r.tos_symbol === sym);
    const lastPrice = rowData && rowData.last_price != null ? rowData.last_price : null;
    const priceHtml = lastPrice != null
      ? `<span style="margin-left:auto;font-size:12px;font-weight:700;color:#0f172a;">${fmtUsd(lastPrice)}</span>`
      : '';
    const _rrHDisp = actionDisplay(d.action || rowData?.rr_action || '');
    const _rrHCode = actionText(_rrHDisp);
    const _rrHDesc = _rrHDisp.label || '';

    const row = (label, val, color) =>
      `<div style="display:flex;justify-content:space-between;gap:12px;">
         <span style="color:#475569;white-space:nowrap;">${label}</span>
         <span style="font-weight:600;color:${color || '#0f172a'};text-align:right;">${val}</span>
       </div>`;
    const rowScore = (label, score, desc) => {
      const sc = score != null ? score : null;
      const scCol = sc == null ? '#94a3b8' : sc > 0 ? '#16a34a' : sc < 0 ? '#dc2626' : '#64748b';
      const scBg  = sc == null ? '#f8fafc' : sc > 0 ? '#f0fdf4' : sc < 0 ? '#fef2f2' : '#f8fafc';
      const scBdr = sc == null ? '#e2e8f0' : sc > 0 ? '#bbf7d0' : sc < 0 ? '#fecaca' : '#e2e8f0';
      return `<div style="display:flex;align-items:baseline;gap:6px;margin-bottom:5px;">
        <span style="font-size:9px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.04em;white-space:nowrap;">${label}</span>
        <span style="font-size:11px;color:${scCol};line-height:1.3;text-align:right;margin-left:auto;">${desc || '—'}</span>
      </div>`;
    };
    const sec = label =>
      `<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin:5px 0 2px;">${label}</div>`;
    const shortDesc = (short, desc) => {
      const sHtml = short ? `<span style="font-weight:700;">${escapeHtml(short)}</span>` : '';
      const dPart = (desc && desc !== short) ? escapeHtml(desc) : '';
      return [sHtml, dPart].filter(Boolean).join(': ') || escapeHtml(desc) || '—';
    };

    // ── QR decision path ─────────────────────────────────────────────────────
    // qf/qk/qo are the stored seq values (QF/QK/QO from PARM_LOOKUP_SQL).
    // qr is the ground-truth stored score (QR from Pass 2, which uses the
    // atomic-input QE — potentially a different source than PARM_LOOKUP_SQL QF).
    // Drive the path display from qr (ground truth) with qf/qk/qo as context.
    const qf = d.tn_td_action, qk = d.bb_action, qo = d.rr_action, qr = d.final_score;
    const step = (indent, label, val, note, active) => {
      const pad = '&nbsp;'.repeat(indent * 3);
      const col = active ? '#0f172a' : '#94a3b8';
      const valCol = val < 0 ? '#dc2626' : val > 0 ? '#16a34a' : '#64748b';
      const arrow = active ? '<span style="color:#4338ca;font-weight:700;">→</span>' : '<span style="color:#cbd5e1;">→</span>';
      return `<div style="font-family:monospace;font-size:10px;color:${col};line-height:1.7;">
        ${pad}${label} <span style="font-weight:700;color:${valCol};">${val != null ? val : '—'}</span>
        ${arrow} <span style="color:${active?'#475569':'#cbd5e1'};font-style:italic;">${note}</span>
      </div>`;
    };

    let decisionHtml = '';
    if (qr != null) {
      // Determine which driver caused qr, using qr as ground truth.
      // qf < 0 means Trend/Trade was bearish and should have driven qr = qf.
      // qk < 0 (with qf > 0) means BB was bearish and should have driven qr = qk.
      // Otherwise qr should equal qo (RR signal).
      if (qf != null && qf < 0 && qr < 0) {
        // Trend/Trade bearish wins — consistent with qr.
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bearish → wins', true);
      } else if (qf != null && qf > 0 && qk != null && qk < 0 && qr < 0) {
        // BB bearish wins over bullish Trend/Trade — consistent with qr.
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bullish → check BB', true);
        decisionHtml += step(1, 'BB Range Streak (QK)', qk, 'bearish → wins', true);
      } else if (qf != null && qf > 0 && (qk == null || qk >= 0)) {
        // Should be RR path.  Show it, but flag if qr diverges from qo
        // (can happen when the Pass-2 QE source differs from PARM_LOOKUP_SQL QF).
        const rrNote = (qo != null && qr != null && qo !== qr)
          ? 'QO=' + qo + ' but score overridden (see Score)'
          : '→ Score';
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bullish → check BB', true);
        decisionHtml += step(1, 'BB Range Streak (QK)', qk != null ? qk : 0, 'not bearish → use RR', true);
        decisionHtml += step(2, 'RR (QO)', qo, rrNote, true);
      } else if (qr < 0) {
        // qr is negative but QF path doesn't clearly explain it — show QF as context.
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, qf != null && qf < 0 ? 'bearish → wins' : 'see score', true);
      } else {
        // Neutral / no path
        if (qf != null) decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'neutral → null', true);
      }
    } else if (qf != null) {
      // No stored score yet — reconstruct from qf/qk/qo as before.
      if (qf < 0) {
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bearish → wins', true);
      } else if (qf > 0) {
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'bullish → check BB', true);
        if (qk != null) {
          if (qk < 0) {
            decisionHtml += step(1, 'BB Range Streak (QK)', qk, 'bearish → wins', true);
          } else {
            decisionHtml += step(1, 'BB Range Streak (QK)', qk, 'not bearish → use RR', true);
            decisionHtml += step(2, 'RR (QO)', qo, '→ Score', true);
          }
        }
      } else {
        decisionHtml = step(0, 'Trend/Trade (QF)', qf, 'neutral → null', true);
      }
    }

    tip.innerHTML = `
      <div style="font-weight:700;color:#0f172a;margin-bottom:6px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;display:flex;align-items:baseline;gap:6px;">
        <span>${escapeHtml(sym)}</span>
        ${_rrHCode && _rrHCode !== '--' ? `<span class="act-badge ${(_rrHDisp.colorCls || 'act-neutral') + '-tint'}">${escapeHtml(_rrHCode)}</span>` : ''}
        ${_rrHDesc ? `<span style="font-size:10px;font-weight:400;color:#475569;">${escapeHtml(_rrHDesc)}</span>` : ''}
        ${priceHtml}
      </div>
      ${rowScore('Trend/Trade',    d.trend_trade, shortDesc(null, rowData?.tn_td_desc || d.tn_td_desc))}
      ${rowScore('BB Range Streak', d.bb_streak,  shortDesc(null, rowData?.bb_desc   || d.bb_desc))}
      ${(()=>{ const _z=rowData?.rr_bull_bear?(rowData.rr_bull_bear==='B'?'Bull Up':'Bull Side Ways'):''; const _zc=rowData?.rr_bull_bear==='B'?'#16a34a':'#f59e0b'; return rowScore(`RR${_z?` <span style="font-size:8px;font-weight:400;text-transform:none;color:${_zc};">${_z}</span>`:''}`,d.rr_action,shortDesc(null,d.rr_desc)); })()}
      ${sec('Decision Path')}
      ${decisionHtml}
      <div style="margin-top:3px;font-size:11px;font-weight:700;color:${scoreCol(qr)};">Score = ${qr != null ? qr : '—'} → ${d.action || '—'}</div>
      ${sec('Levels' + (lastPrice != null ? ' · Price ' + fmtUsd(lastPrice) : ''))}
      ${row('Trade',   fmt2(d.trade), '#ea580c')}
      ${row('Trend',   fmt2(d.trend), '#6366f1')}
      ${row('TRR',     fmt2(d.trr),   '#16a34a')}
      ${row('LRR',     fmt2(d.lrr),   '#16a34a')}
      ${sec('Indices')}
      ${row('TRR Idx', d.trr_idx != null ? String(d.trr_idx) : '—', scoreCol(d.trr_idx))}
      ${row('MRR Idx', d.mrr_idx != null ? String(d.mrr_idx) : '—', scoreCol(d.mrr_idx))}
      ${row('LRR Idx', d.lrr_idx != null ? String(d.lrr_idx) : '—', scoreCol(d.lrr_idx))}`;

    const rect = ic.getBoundingClientRect();
    tip.style.display = 'block';
    const tipW = tip.offsetWidth;
    let left = rect.left - tipW - 8;
    if (left < 4) left = rect.right + 8;
    tip.style.left = left + 'px';
    tip.style.top  = Math.min(rect.top, window.innerHeight - tip.offsetHeight - 8) + 'px';
  });

  body.addEventListener('mouseout', (e) => {
    if (e.relatedTarget && e.relatedTarget.closest('.rr-main-ic')) return;
    tip.style.display = 'none';
  });
}
