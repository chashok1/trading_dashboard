/* Portfolio Builder page (DESIGN_SPEC_9/10/11, docs/portfolio_builder_logic.md).
 * Account first, then how long, mix by asset class, split each bucket by area (Macro and Quad) or by recipe, warnings,
 * accept and freeze. Colours reuse the Portfolio pie (_PM_ASSET_COLORS from portfolio_mix.js) and Universe's Quad pills.
 * The Builder never trades and never changes the Actionable Final Call. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const tipAttr = lines => esc(lines.filter(Boolean).map(l => '• ' + l).join('\n')).replace(/\n/g, '&#10;');
  // 2026-10-28, user: amounts shown in K ($442.8K); under $1,000 stays in dollars, $1M and over in M
  const kfmt = a => a >= 1e6 ? (a / 1e6).toFixed(2) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(1) + 'K' : Math.round(a).toLocaleString();
  const usd = n => (n == null || isNaN(n)) ? '-' : (n < 0 ? '-$' : '$') + kfmt(Math.abs(n));
  const sgnUsd = n => (n == null || isNaN(n)) ? '-' : (n > 0 ? '+' : n < 0 ? '−' : '') + '$' + kfmt(Math.abs(n));
  const pct = (x, d = 1) => (x == null || isNaN(x)) ? '-' : (x * 100).toFixed(d) + '%';
  const sgnPct = (x, d = 1) => (x == null || isNaN(x)) ? '-' : (x >= 0 ? '+' : '−') + Math.abs(x * 100).toFixed(d) + '%';
  const cls = x => x == null ? '' : (x > 0 ? 'bld-up' : x < 0 ? 'bld-dn' : '');
  const BUCKETS = ['Equities', 'Fixed Income', 'Gold', 'Commodities', 'Crypto', 'Currency'];
  const bcol = b => b === 'Currency' ? (_PM_ASSET_COLORS.FX) : (_PM_ASSET_COLORS[b] || '#c3c2b7');
  const ACT_LABEL = { BM: 'Buy More', BS: 'Buy Some', BMN: 'Buy To Min', INCREASE: 'Increase', ADD: 'Add', BW: 'Buy Watch', BSW: 'Buy Some Watch',
    SA: 'Sell All', SS: 'Sell Some', STM: 'Sell/Trim', REDUCE: 'Reduce', SO: 'Sell (Over Max)', SW: 'Sell Watch', SWW: 'Sell Watch', REMOVE: 'Remove', HOLD: 'Hold' };
  // factor filters on the names list; style tags as the Builder already uses them (Defensives, Low Beta ...)
  const FACTORS = [['', 'All factors'], ['defensive', 'Defensive'], ['offensive', 'Offensive'], ['value', 'Value'], ['growth', 'Growth'], ['mid', 'Mid'],
    ['lowbeta', 'Low beta'], ['highbeta', 'High beta'], ['uptrend', 'Above trend'], ['mom', 'Positive momentum']];
  const FACTOR_TIP = 'Defensive = Defensives, Low Beta or Dividend tag. Offensive = Cyclical, High Beta or Small Caps. Value = Value. Growth = Secular. Mid = Mid Caps. Low beta = measured beta 0.8 or under. High beta = over 1.2.';
  const STYLE_TAGS = { defensive: ['defensives', 'low beta', 'dividend'], offensive: ['cyclical', 'high beta', 'small caps'], value: ['value'], growth: ['secular'], mid: ['mid caps'] };
  const hasStyle = (n, k) => (n.styles || []).some(t => STYLE_TAGS[k].includes(String(t).toLowerCase()));
  function factorOk(n, k) {
    if (!k) return true;
    if (STYLE_TAGS[k]) return hasStyle(n, k);
    if (k === 'lowbeta') return n.beta != null && n.beta <= 0.8;
    if (k === 'highbeta') return n.beta != null && n.beta > 1.2;
    if (k === 'uptrend') return n.above_trend === true;
    if (k === 'mom') return n.mom != null && n.mom > 0;
    return true;
  }

  const S = {
    date: null, accounts: [], acct: '', horizon: '3M', preset: 'current', seeded: null, mix: null, amount: null, useDial: false,
    srcNames: [], outlooks: {}, nameCache: {}, picks: [], assign: {}, targets: {}, gapIdx: null, namesSeq: 0, sources: [], srcList: [], warn: {}, presets: {}, preview: null,
    reqSeq: 0, timer: null, detail: null, chart: null,
  };

  async function api(url, opts) {
    const r = await fetch(url, opts);
    let j = null;
    try { j = await r.json(); } catch (e) { /* not json */ }
    if (!r.ok) throw new Error((j && j.detail) || ('HTTP ' + r.status));
    return j;
  }
  const dq = () => S.date ? 'date=' + encodeURIComponent(S.date) : '';
  const withDate = u => u + (dq() ? (u.includes('?') ? '&' : '?') + dq() : '');
  const post = (u, body, method) => api(withDate(u), { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

  function buildReq() {
    // hand-picked build: the server uses exactly these names, each in its asset class, with the % typed (null = share equally)
    const req = { account: S.acct || 'ALL', horizon: S.horizon, preset: S.preset, use_risk_dial: S.useDial, warnings: S.warn,
      manual: true, picks: S.picks.map(p => ({ sym: p.sym, bucket: p.bucket, pct: p.pct })) };
    if (S.preset === 'custom') req.mix = S.mix;
    if (S.amount) req.amount = S.amount;
    return req;
  }

  // ---------------------------------------------------------------- init
  async function init() {
    document.querySelectorAll('.bld-tab').forEach(t => t.onclick = () => showView(t.dataset.v));
    try {
      const dates = await api('/api/dates');
      const sel = $('datePicker');
      sel.innerHTML = dates.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
      S.date = dates[0] || null;
      if (S.date) sel.value = S.date;
      sel.onchange = () => { S.date = sel.value; reloadAll(); };
    } catch (e) { problems(['Could not load dates: ' + e.message]); }
    $('refreshBtn').onclick = reloadAll;
    $('backToList').onclick = e => { e.preventDefault(); showView('list'); };
    $('preset').onchange = () => { S.preset = $('preset').value; if (S.preset !== 'custom') S.mix = null; schedule(); };
    document.querySelectorAll('[data-warn]').forEach(c => c.onchange = () => { S.warn[c.dataset.warn] = c.checked; });
    $('acctSel').onchange = () => { S.acct = $('acctSel').value; S.amount = null; S.targets = {}; S.seeded = null; S.preset = 'current'; S.mix = null; loadSourceNames(); schedule(0); };
    try {
      const so = await api('/api/builder/sources');
      S.srcList = so.sources || [];
      if (S.srcList.some(x => x.code === 'HELD')) S.sources = ['HELD'];
      renderSources();
    } catch (e) { problems(['Could not load source lists: ' + e.message]); }
    $('setOpen').onclick = openSet; $('setSave').onclick = saveSet; $('setDel').onclick = deleteSet;
    loadSets();
    $('listAcct').onchange = loadList;
    $('listStatus').onchange = loadList;
    // editable amount (defaults to the account value)
    const lab = document.createElement('label');
    lab.className = 'bld-muted';
    lab.innerHTML = 'Amount <input type="number" id="amount" min="0" step="1000" style="width:110px" title="Defaults to the account value. Lower it to model part of the account.">';
    $('acctSnap').before(lab);
    $('amount').onchange = () => { const v = parseFloat($('amount').value); S.amount = v > 0 ? v : null; schedule(); };
    await reloadAll(true);
  }

  async function reloadAll(first) {
    try {
      const pr = await api('/api/builder/presets');
      S.presets = pr.presets || {};
      if (pr.problems && pr.problems.length) problems(pr.problems);
      const ac = await api(withDate('/api/builder/accounts'));
      S.accounts = ac.accounts || [];
      if (ac.problems && ac.problems.length) problems(ac.problems);
      const opts = S.accounts.map(a => `<option value="${esc(a.short)}">${esc(a.short)}${a.type && a.type !== 'OTHER' ? ' · ' + esc(a.type) : ''}</option>`);   // 2026-10-28: the Amount box below already shows the value
      opts.push(`<option value="ALL">Whole book (preview only)</option>`);
      $('acctSel').innerHTML = opts.join('');
      if (!S.acct || ![...$('acctSel').options].some(o => o.value === S.acct)) S.acct = S.accounts.length ? S.accounts.slice().sort((x, y) => y.value - x.value)[0].short : 'ALL';
      $('acctSel').value = S.acct;
      const po = [['current', 'My current mix']].concat(Object.keys(S.presets).map(k => [k, S.presets[k].label])).concat([['custom', 'Custom']]);
      $('preset').innerHTML = po.map(p => `<option value="${esc(p[0])}">${esc(p[1])}</option>`).join('');
      if (!po.some(p => p[0] === S.preset)) S.preset = po.length > 2 ? po[1][0] : 'current';
      $('preset').value = S.preset;
    } catch (e) { problems(['Could not load accounts: ' + e.message]); }
    await loadList();
    loadSourceNames();
    if (first !== true || true) schedule(0);
  }

  function problems(list) {
    const el = $('bldProblems');
    const msgs = (list || []).filter(Boolean);
    el.hidden = !msgs.length;
    el.innerHTML = msgs.map(esc).join('<br>');
  }

  function showView(v) {
    ['build', 'list', 'detail'].forEach(x => { $('view-' + x).hidden = x !== v; });
    document.querySelectorAll('.bld-tab').forEach(t => t.classList.toggle('on', t.dataset.v === v || (v === 'detail' && t.dataset.v === 'list')));
    if (v === 'list') loadList();
  }

  // ---------------------------------------------------------------- Hedgeye source pool + checks
  function renderSources() {
    $('srcBox').innerHTML = S.srcList.map(x => `<label><input type="checkbox" data-src="${esc(x.code)}" ${S.sources.includes(x.code) ? 'checked' : ''}> ${esc(x.code)} <span class="bld-muted">${esc(x.label)}</span></label>`).join('');
    $('srcBox').querySelectorAll('[data-src]').forEach(c => c.onchange = () => {
      S.sources = [...$('srcBox').querySelectorAll('[data-src]')].filter(i => i.checked).map(i => i.dataset.src);
      loadSourceNames();
    });
    ['srcfSource', 'srcfClass', 'srcfFactor', 'srcfIndustry'].forEach(id => $(id).onchange = renderSourceNames);
    $('srcfSector').onchange = () => { fillIndustries(''); renderSourceNames(); };
    $('fillGaps').onclick = fillGaps;
    $('clearFilters').onclick = () => {
      ['srcfSource', 'srcfClass', 'srcfSector', 'srcfFactor'].forEach(id => { $(id).value = ''; });
      fillIndustries('');
      $('srcfText').value = ''; S.gapIdx = null; $('srcNamesHint').textContent = '';
      setFilters({});
    };
    $('srcfQuad').querySelectorAll('input').forEach(c => c.onchange = renderSourceNames);
    $('srcfFactor').innerHTML = FACTORS.map(f => `<option value="${f[0]}">${esc(f[1])}</option>`).join('');
    $('srcfFactor').title = FACTOR_TIP;
    $('srcfText').oninput = renderSourceNames;
    $('selShown').onclick = selectShown;
    // fill each held pick's % of its class from the account's holdings (the class totals follow the 'current' mix)
    $('matchHold').onclick = matchHoldings;
    function matchHoldings() {
      const hold = {};
      ((S.preview && S.preview.account && S.preview.account.holdings) || []).forEach(h => { hold[h.sym] = h.value || 0; });
      const tot = {};
      S.picks.forEach(p => { if (hold[p.sym] > 0) tot[p.bucket] = (tot[p.bucket] || 0) + hold[p.sym]; });
      S.picks.forEach(p => { p.pct = hold[p.sym] > 0 ? Math.round(hold[p.sym] / tot[p.bucket] * 10000) / 100 : null; });
      if (S.preset !== 'current') S.preset = 'current';
      renderSourceNames(); schedule(0);
    }
    $('clearPicks').onclick = () => { S.picks = []; renderSourceNames(); schedule(0); };
    renderSourceNames();
  }

  // every name on the ticked lists, even when its asset class etc. is missing (information only)
  async function loadSourceNames() {
    if (!S.sources.length) { S.srcNames = []; renderSourceNames(); return; }
    const seq = ++S.namesSeq;
    $('srcNamesRows').innerHTML = '<tr><td colspan="9" class="bld-muted">Loading...</td></tr>';
    try {
      const r = await api(withDate('/api/builder/source-names?sources=' + encodeURIComponent(S.sources.join(',')) + '&account=' + encodeURIComponent(S.acct || '')));
      if (seq !== S.namesSeq) return;
      S.srcNames = r.names || [];
      S.srcNames.forEach(n => { S.nameCache[n.sym] = n; });
    } catch (e) {
      if (seq !== S.namesSeq) return;
      S.srcNames = [];
      $('srcNamesRows').innerHTML = `<tr><td colspan="9" class="bld-warn">${esc(e.message)}</td></tr>`;
      return;
    }
    const keep = [$('srcfSource').value, $('srcfClass').value, $('srcfSector').value, $('srcfIndustry').value];
    const sectors = [...new Set(S.srcNames.filter(n => n.bucket === 'Equities' && n.sector && !['Unmapped', 'Other'].includes(n.sector)).map(n => n.sector))].sort();
    $('srcfSector').innerHTML = '<option value="">All sectors</option>' + sectors.map(s => `<option>${esc(s)}</option>`).join('');
    if (sectors.includes(keep[2])) $('srcfSector').value = keep[2];
    fillIndustries(keep[3]);
    $('srcfSource').innerHTML = '<option value="">All lists</option>' + S.sources.map(c => `<option>${esc(c)}</option>`).join('');
    $('srcfClass').innerHTML = '<option value="">All asset classes</option>' + BUCKETS.map(c => `<option>${esc(c)}</option>`).join('') + '<option value="__missing">No class yet</option>';
    if ([...$('srcfSource').options].some(o => o.value === keep[0])) $('srcfSource').value = keep[0];
    if ([...$('srcfClass').options].some(o => o.value === keep[1])) $('srcfClass').value = keep[1];
    // 2026-10-29, user: the default list is HELD, so tick every held name that qualifies unless picks already exist
    const autoPick = S.sources.length === 1 && S.sources[0] === 'HELD' && !S.picks.length;
    if (autoPick) S.srcNames.forEach(n => setPick(n.sym, true));
    renderSourceNames();
    if (autoPick && S.picks.length) { S.matchNext = true; schedule(0); }
  }

  // industries of the names in the chosen sector (all equity industries when no sector is chosen)
  function fillIndustries(want) {
    const sc = $('srcfSector').value;
    const inds = [...new Set((S.srcNames || []).filter(n => n.industry && (!sc || (n.bucket === 'Equities' && n.sector === sc))).map(n => n.industry))].sort();
    $('srcfIndustry').innerHTML = '<option value="">All industries</option>' + inds.map(s => `<option>${esc(s)}</option>`).join('');
    if (want && inds.includes(want)) $('srcfIndustry').value = want;
  }

  const bucketOf = n => (n && (n.bucket || S.assign[n.sym])) || null;
  // symbol text coloured by its Hedgeye outlook (same colours as the other screens); plain when unknown
  const symHtml = sym => { const o = (S.outlooks[sym] || (S.nameCache[sym] || {}).outlook); const c = o && window.outlookColor ? window.outlookColor(o) : ''; return `<span${c && c !== 'inherit' ? ` style="color:${c}"` : ''}${o ? ` title="Outlook: ${esc(o)}"` : ''}>${esc(sym)}</span>`; };
  const picked = sym => S.picks.find(p => p.sym === sym);

  function shownNames() {
    const all = S.srcNames || [];
    const sc = $('srcfSector').value, ind = $('srcfIndustry').value;
    const fs =$('srcfSource').value, fc = $('srcfClass').value, ff = $('srcfFactor').value, tx = $('srcfText').value.trim().toUpperCase();
    const qsel = [...$('srcfQuad').querySelectorAll('input:checked')].map(i => parseInt(i.value, 10));
    return all.filter(n => (!fs || n.sources.includes(fs)) &&
      (!qsel.length || qsel.some(i => (n.quad || [])[i] === 'bull')) &&
      (!sc || (bucketOf(n) === 'Equities' && n.sector === sc)) && (!ind || n.industry === ind) &&
      (!fc || (fc === '__missing' ? !bucketOf(n) : bucketOf(n) === fc)) && factorOk(n, ff) &&
      (!tx || n.sym.toUpperCase().includes(tx)));
  }

  function setPick(sym, on) {
    const n = S.nameCache[sym];
    const b = bucketOf(n);
    if (on && n && b && n.usable && !picked(sym)) S.picks.push({ sym, bucket: b, pct: null });
    if (!on) S.picks = S.picks.filter(p => p.sym !== sym);
  }

  function selectShown() {
    shownNames().forEach(n => setPick(n.sym, true));
    renderSourceNames(); schedule(0);
  }

  function renderSourceNames() {
    const all = S.srcNames || [];
    const rows = shownNames();
    $('srcNamesCount').textContent = all.length ? `${all.length} names` + (rows.length !== all.length ? ` · showing ${rows.length}` : '') : '';
    $('srcNamesHint').textContent = S.picks.length ? `${S.picks.length} picked` : '';
    if (!all.length) { $('srcNamesRows').innerHTML = `<tr><td colspan="9" class="bld-muted">${S.sources.length ? 'No names on those lists today.' : 'Tick a list on the left to see its names here.'}</td></tr>`; return; }
    $('srcNamesRows').innerHTML = rows.map(n => {
      const b = bucketOf(n), on = !!picked(n.sym);
      const cls = b ? esc(b) : `<select data-assign="${esc(n.sym)}"><option value="">Choose...</option>${BUCKETS.map(x => `<option>${esc(x)}</option>`).join('')}</select>`;
      const st = (n.styles || []).map(esc).join(', ') || '<span class="bld-muted">-</span>';
      return `<tr><td><input type="checkbox" data-pick="${esc(n.sym)}" ${on ? 'checked' : ''} ${!b ? 'disabled' : ''} title="${!b ? 'Choose an asset class first' : 'Add to picks'}"></td>` +
        `<td>${symHtml(n.sym)}</td><td>${esc(n.sources.join(', '))}</td><td>${cls}</td><td>${(bucketOf(n) === 'Equities' && n.sector && !['Unmapped', 'Other'].includes(n.sector)) ? esc(n.sector) : '<span class="bld-muted">-</span>'}</td>` +
        `<td>${(n.quad || []).map((w, i) => `<span class="bld-qp ${w || 'none'}" title="Q${i + 1}: ${w || 'no view'}">${w ? 'Q' + (i + 1) : '-'}</span>`).join('')}</td><td class="n">${n.beta == null ? '<span class="bld-muted">-</span>' : n.beta.toFixed(2)}</td><td>${st}</td></tr>`;
    }).join('') || '<tr><td colspan="9" class="bld-muted">No names match.</td></tr>';
    $('srcNamesRows').querySelectorAll('[data-pick]').forEach(c => c.onchange = () => { setPick(c.dataset.pick, c.checked); renderSourceNames(); schedule(0); });
    $('srcNamesRows').querySelectorAll('[data-assign]').forEach(sel => sel.onchange = () => {
      if (!sel.value) return;
      S.assign[sel.dataset.assign] = sel.value;
      api('/api/builder/asset-class', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sym: sel.dataset.assign, bucket: sel.value }) }).catch(() => {});   // remembered for every screen
      setPick(sel.dataset.assign, true);
      renderSourceNames(); schedule(0);
    });
  }

  // the asset classes shown in the comparison: any with a target, picked money or held money
  function mixBuckets(res) {
    const fin = res.mix_final || {}, cur = res.mix_current || {}, amt = res.amount || 1;
    return BUCKETS.filter(b => (fin[b] || 0) > 0.04 || (cur[b] || 0) > 0.04 ||
      (res.positions || []).some(p => p.bucket === b && p.value / amt > 0.0004));
  }

  // bars above each grid: one row per line of the grid. Bar = picks (green within 5 pts of the target, amber short, red over),
  // thin grey bar = portfolio, black line = target. Shown from the start, before anything is picked.
  function barBlock(rows) {
    rows = (rows || []).filter(r => r.pv != null || r.hv != null || r.tv != null);
    if (!rows.length) return '';
    const scale = Math.max(10, ...rows.map(r => Math.max(r.pv || 0, r.hv || 0, r.tv || 0))) * 1.15;
    const w = v => Math.min(Math.max(v, 0) / scale * 100, 100);
    return '<div class="bld-viz">' + rows.map(r => {
      const pv = r.pv, tv = r.tv;
      const col = pv == null ? '#c3c2b7' : (tv != null && tv > 0 ? (pv > tv + 5 ? '#dc2626' : (pv < tv - 5 ? '#d97706' : '#16a34a')) : (r.col || '#6b7fd7'));
      return `<div class="vrow"><span class="vlab" title="${esc(r.label)}">${r.col ? `<span class="bld-sw" style="background:${r.col}"></span>` : ''}${esc(r.label)}</span>` +
        `<div class="vtrack2">${pv != null ? `<div class="vfill" style="width:${w(pv)}%;background:${col}"></div>` : ''}${r.hv != null ? `<div class="vhold" style="width:${w(r.hv)}%"></div>` : ''}` +
        `${tv != null && tv > 0 ? `<div class="vtick" style="left:${w(tv)}%" title="Target ${tv.toFixed(0)}%"></div>` : ''}</div></div>`;
    }).join('') + '</div>';
  }

  // One comparison table: factor names down the left, "Your picks" and "My portfolio" side by side, then the gap.
  function compareTable(res) {
    const ex = res.exposure || {}, P = ex.picked || {}, H = ex.held || {};
    const cur = res.mix_current || {}, fin = res.mix_final || {}, amt = res.amount || 1;
    const hasPick = (P.total || 0) > 0, hasHeld = (H.total || 0) > 0;
    if (!hasPick && !hasHeld && !S.picks.length) return '';
    const dash = '<span class="bld-muted">-</span>';
    const f0 = v => v.toFixed(0) + '%';
    const bd = (q, w) => ((q || {})[w] || 0);
    const gapTd = (g, dec) => (g == null || !hasPick || !hasHeld) ? '<td></td>'
      : `<td class="n ${Math.abs(g) < (dec ? 0.005 : 0.5) ? '' : (g > 0 ? 'bld-up' : 'bld-dn')}">${(g >= 0 ? '+' : '−') + Math.abs(g).toFixed(dec || 0)}${dec ? '' : ' pts'}</td>`;
    // a section break: the rows after it become their own small table (laid out in three columns, see the end of this function)
    let curKey = '';
    const vizRows = {};
    const sec = t => { curKey = t.split(' ·')[0]; vizRows[curKey] = []; return `\u0001${t}\u0002`; };
    const chosen = res.mix_target || {};
    const judge = (pv, tv, dec) => { const tol = dec ? 0.05 : 5; return pv > tv + tol ? 'bld-over' : (pv < tv - tol ? 'bld-warn' : 'bld-up'); };
    // gap = picks minus its reference (the target if one is set, else the portfolio); coloured against a target
    const gapCell = (pv, ref, haveRef, dec, judged) => {
      if (pv == null || ref == null || !hasPick || !haveRef) return '<td></td>';
      const g = pv - ref;
      const c = judged ? judge(pv, ref, dec) : (Math.abs(g) < (dec ? 0.005 : 0.5) ? '' : (g > 0 ? 'bld-up' : 'bld-dn'));
      return `<td class="n ${c}">${(g >= 0 ? '+' : '−') + Math.abs(g).toFixed(dec || 0)}${dec ? '' : ' pts'}</td>`;
    };
    const tgtCell = (attr, tv, dec) => `<td class="n"><input type="number" min="0" step="${dec ? 0.05 : 1}" ${attr} value="${tv == null ? '' : tv}" class="${tv != null && !dec && tv > 100 ? 'tgt-over' : ''}"></td>`;
    // One row. pv / hv = percent picked / held (null = nothing there). key = target key (null: no target cell);
    // asset = asset class name (its target is the mix you chose; judged against the mix after the Risk Dial).
    const R = (label, pv, hv, tip, key, asset) => {
      const tv = asset ? (chosen[asset] > 0 ? Math.round(chosen[asset] * 100) / 100 : null) : (key ? tgtOf(key) : null);
      const eff = asset ? (fin[asset] > 0 ? fin[asset] : null) : tv;
      const cell = asset ? tgtCell(`data-tgt-asset="${esc(asset)}"`, tv) : (key ? tgtCell(`data-tgt="${esc(key)}"`, tv) : '<td></td>');
      if (vizRows[curKey]) vizRows[curKey].push({ label: asset || String(label).replace(/<[^>]*>/g, ''), pv: hasPick ? pv : null, hv: hasHeld ? hv : null, tv: eff, col: asset ? bcol(asset) : null });
      const pCell = hasPick && pv != null ? `<b class="${eff != null ? judge(pv, eff) : ''}">${f0(pv)}</b>` : dash;
      return `<tr><td${tip ? ` class="bld-tip" data-tip="${esc(tip)}"` : ''}>${label}</td>${cell}<td class="n">${pCell}</td><td class="n">${hasHeld && hv != null ? f0(hv) : dash}</td>` +
        `${eff != null ? gapCell(pv, eff, true, 0, true) : gapCell(pv, hv, hasHeld, 0, false)}</tr>`;
    };
    const generalTip = 'Asset class rows are % of the account. Everything below is % of the invested money on that side. Quad and style rows overlap (one fund can carry several), so they do not add to 100%. A stock takes its sector\'s Quad view. Red = over target.';
    let t = '';
    t += sec('Asset class · % of the account');
    let placedTotal = 0, heldInvested = 0;
    for (const b of mixBuckets(res)) {
      const placed = (res.positions || []).filter(p => p.bucket === b).reduce((a, p) => a + p.value, 0) / amt * 100;
      placedTotal += placed;
      heldInvested += cur[b] || 0;
      t += R(`<span class="bld-sw" style="background:${bcol(b)}"></span>${esc(b)}`, placed, cur[b] || 0, null, null, b);
    }
    t += `<tr><td class="bld-tip" data-tip="All the money your picks place. Over 100% (red) means the picks add up to more than the account.">Total invested</td><td></td><td class="n">${S.picks.length ? `<b class="${placedTotal > 100.5 ? 'bld-over' : ''}">${f0(placedTotal)}</b>` : dash}</td><td class="n">${hasHeld ? f0(heldInvested) : dash}</td><td></td></tr>`;
    t += R(`<span class="bld-sw" style="background:${_PM_ASSET_COLORS.Cash}"></span>Cash`, (res.cash && res.cash.dollars || 0) / amt * 100, cur.Cash || 0, 'Cash and money not yet placed');
    if (cur.Unmapped > 0.04) t += R('Unmapped', null, cur.Unmapped, 'Held with no asset class: cannot be picked');
    t += sec('Risk · % of the invested money');
    const fb = v => (v == null ? dash : v.toFixed(2));
    const bt = tgtOf('beta');
    t += `<tr><td class="bld-tip" data-tip="Weighted average beta against SPY (SPY = 1.00). Names with no beta are left out.">Portfolio beta</td>${tgtCell('data-tgt="beta"', bt, true)}` +
      `<td class="n">${hasPick && P.beta != null ? `<b class="${bt != null ? judge(P.beta, bt, true) : ''}">${P.beta.toFixed(2)}</b>` : dash}</td><td class="n">${hasHeld ? fb(H.beta) : dash}</td>` +
      `${bt != null ? gapCell(P.beta, bt, true, 2, true) : gapCell(P.beta, H.beta, hasHeld, 2, false)}</tr>`;
    t += R('Low beta (0.8 or under)', hasPick ? P.lowbeta : null, hasHeld ? H.lowbeta : null, null, 'lowbeta') + R('High beta (over 1.2)', hasPick ? P.highbeta : null, hasHeld ? H.highbeta : null, null, 'highbeta');
    t += sec('Quad favored (Bull)');
    for (const q of ['Q1', 'Q2', 'Q3', 'Q4']) {
      const pq = (P.quad || {})[q], hq = (H.quad || {})[q];
      const tip = `${q} outlook. Picks: Bull ${bd(pq, 'bull').toFixed(0)}%, Neutral ${bd(pq, 'neutral').toFixed(0)}%, Bear ${bd(pq, 'bear').toFixed(0)}%, no view ${bd(pq, 'none').toFixed(0)}%. Portfolio: Bull ${bd(hq, 'bull').toFixed(0)}%, Neutral ${bd(hq, 'neutral').toFixed(0)}%, Bear ${bd(hq, 'bear').toFixed(0)}%, no view ${bd(hq, 'none').toFixed(0)}%`;
      t += R(q, hasPick ? bd(pq, 'bull') : null, hasHeld ? bd(hq, 'bull') : null, tip, 'quad:' + q);
    }
    t += sec('Sectors · equities');
    const sv = k => Math.max((P.sector || {})[k] || 0, (H.sector || {})[k] || 0, tgtOf('sector:' + k) || 0);
    const allSec = new Set(Object.keys(P.sector || {}).concat(Object.keys(H.sector || {})));
    Object.keys(S.targets).filter(k => k.startsWith('sector:')).forEach(k => allSec.add(k.slice(7)));
    Object.values(S.nameCache).forEach(n => { if (n.bucket === 'Equities' && n.sector && !['Unmapped', 'Other'].includes(n.sector)) allSec.add(n.sector); });
    [...allSec].sort((a, b) => sv(b) - sv(a) || a.localeCompare(b))
      .forEach(s => { t += R(esc(s), hasPick ? ((P.sector || {})[s] || 0) : null, hasHeld ? ((H.sector || {})[s] || 0) : null, null, 'sector:' + s); });
    t += sec('Style');
    [['defensive', 'Defensive'], ['offensive', 'Offensive'], ['value', 'Value'], ['growth', 'Growth'], ['mid', 'Mid']]
      .forEach(f => { t += R(f[1], hasPick ? ((P.style || {})[f[0]] || 0) : null, hasHeld ? ((H.style || {})[f[0]] || 0) : null, null, 'style:' + f[0]); });
    // 2026-10-28, user: show the sections in three columns. Cut the rows at each section break, one small table per section.
    const parts = t.split(/\u0001([^\u0002]*)\u0002/);          // ['', title1, rows1, title2, rows2, ...]
    const tables = {};
    for (let i = 1; i < parts.length; i += 2) {
      const title = parts[i], first = i === 1;
      tables[title.split(' ·')[0]] = barBlock(vizRows[title.split(' ·')[0]]) + `<table class="bld-t bld-exp"><thead><tr><th${first ? ` class="bld-tip" data-tip="${esc(generalTip)}"` : ''}>${title}</th>` +
        `<th class="n bld-tip" data-tip="Type your target % on any row. Blank = no target. Targets guide you; they never pick stocks.">Target</th><th class="n">Picks${first && S.picks.length ? ' (' + S.picks.length + ')' : ''}</th><th class="n">Port&shy;folio</th><th class="n">Gap</th></tr></thead><tbody>${parts[i + 1]}</tbody></table>`;
    }
    const T = k => tables[k] || '';
    // 2026-10-28, user: the five grids stay in three columns
    return `<div class="bld-cmp3"><div>${T('Asset class')}${T('Risk')}</div><div>${T('Style')}${T('Quad favored (Bull)')}</div><div>${T('Sectors')}</div></div>`;   // keys are the title up to " ·"
  }

  const tgtOf = key => (S.targets[key] == null ? null : S.targets[key]);

  // an asset class target typed in the table: it becomes the custom mix (the rest stays Cash; the classes cannot add to more than 100)
  function setAssetTarget(b, raw) {
    const res = S.preview || {};
    const base = Object.assign({}, S.mix || res.mix_target || {});
    delete base.Cash;
    const others = Object.keys(base).reduce((t, k) => t + (k === b ? 0 : (base[k] || 0)), 0);
    base[b] = raw === '' ? 0 : Math.max(0, Math.min(parseFloat(raw) || 0, 100 - others));
    S.mix = base; S.preset = 'custom'; $('preset').value = 'custom'; schedule(0);
  }

  // targets typed on the other rows are guides only: redraw the table, no server call
  function bindCmp() {
    const host = $('cmpTable');
    host.querySelectorAll('[data-tgt]').forEach(i => i.onchange = () => {
      const k = i.dataset.tgt;
      if (i.value === '') delete S.targets[k]; else S.targets[k] = Math.max(0, parseFloat(i.value) || 0);
      host.innerHTML = compareTable(S.preview);
      bindCmp();
    });
    host.querySelectorAll('[data-tgt-asset]').forEach(i => i.onchange = () => setAssetTarget(i.dataset.tgtAsset, i.value));
  }

  // "Show what's missing": the target rows still short of their target, biggest shortfall first; each click filters the names list to the next one
  function gapList() {
    const res = S.preview;
    if (!res) return [];
    const P = (res.exposure || {}).picked || {}, fin = res.mix_final || {}, amt = res.amount || 1, out = [];
    const add = (label, short, apply) => { if (short > 5) out.push({ label: `${label}: ${short.toFixed(0)} pts short`, short, apply }); };
    BUCKETS.forEach(b => {
      const placed = (res.positions || []).filter(p => p.bucket === b).reduce((a, p) => a + p.value, 0) / amt * 100;
      add(b, (fin[b] || 0) - placed, f => { f.cls = b; });
    });
    ['Q1', 'Q2', 'Q3', 'Q4'].forEach((q, i) => { const tv = tgtOf('quad:' + q); if (tv != null) add(q + ' Bull', tv - (((P.quad || {})[q] || {}).bull || 0), f => { f.quad = [i]; }); });
    ['defensive', 'offensive', 'value', 'growth', 'mid'].forEach(k => { const tv = tgtOf('style:' + k); if (tv != null) add(k[0].toUpperCase() + k.slice(1), tv - ((P.style || {})[k] || 0), f => { f.factor = k; }); });
    [['lowbeta', 'Low beta'], ['highbeta', 'High beta']].forEach(([k, lab]) => { const tv = tgtOf(k); if (tv != null) add(lab, tv - (P[k] || 0), f => { f.factor = k; }); });
    Object.keys(S.targets).filter(k => k.startsWith('sector:')).forEach(k => add(k.slice(7), S.targets[k] - ((P.sector || {})[k.slice(7)] || 0), f => { f.sector = k.slice(7); }));
    return out.sort((a, b) => b.short - a.short);
  }

  function setFilters(f) {
    $('srcfClass').value = f.cls || '';
    $('srcfSector').value = f.sector || '';
    fillIndustries('');
    $('srcfFactor').value = f.factor || '';
    $('srcfQuad').querySelectorAll('input').forEach(c => { c.checked = (f.quad || []).includes(parseInt(c.value, 10)); });
    renderSourceNames();
  }

  function fillGaps() {
    const gaps = gapList();
    if (!gaps.length) { $('srcNamesHint').textContent = 'No target is short by more than 5 pts.'; return; }
    S.gapIdx = ((S.gapIdx == null ? -1 : S.gapIdx) + 1) % gaps.length;
    const g = gaps[S.gapIdx], f = {};
    g.apply(f);
    setFilters(f);
    $('srcNamesHint').textContent = `Showing: ${g.label}${gaps.length > 1 ? ` (${S.gapIdx + 1} of ${gaps.length}, click for next)` : ''}`;
  }

  // One symbol table: a row for every symbol you picked OR the account holds, grouped by asset class, with
  // Your picks and My portfolio side by side. The % box on a picked row is where you set its share of the class.
  function symbolTable(res) {
    const holdBy = {};
    ((res.account && res.account.holdings) || []).forEach(h => { holdBy[h.sym] = h; });
    const posBy = {};
    (res.positions || []).forEach(p => { posBy[p.sym] = p; });
    const vsBy = {};
    ((res.vs_account && res.vs_account.rows) || []).forEach(r => { vsBy[r.sym] = r; });
    const acctVal = (res.account && res.account.value) || 0, amt = res.amount || 1, fin = res.mix_final || {};
    const syms = [...new Set(S.picks.map(p => p.sym).concat(Object.keys(holdBy)))];
    if (!syms.length) return '<div class="bld-muted" style="margin-top:8px">Nothing picked yet. Tick names in the middle column.</div>';
    const rows = syms.map(sym => {
      const pk = picked(sym), pos = posBy[sym], h = holdBy[sym];
      const bucket = (pk && pk.bucket) || (pos && pos.bucket) || (h && h.bucket) || 'Unmapped';
      return { sym, pk, pos, h, bucket, hold: h ? h.value : 0, model: pos ? pos.value : 0, kept: !!(h && h.kept), trade: (vsBy[sym] || {}).trade || '' };
    });
    const dash = '<span class="bld-muted">-</span>';
    // 2026-10-28, user: two columns -- Equities on the right, every other asset class on the left
    const head = `<table class="bld-t bld-exp"><thead><tr><th>Symbol</th><th class="n">Picks</th><th class="n">Portfolio</th><th class="n">Gap $</th><th>To match</th></tr></thead><tbody>`;
    const side = { left: '', right: '' };
    for (const b of BUCKETS.concat(['Unmapped'])) {
      const mine = rows.filter(r => r.bucket === b).sort((x, y) => Math.max(y.hold, y.model) - Math.max(x.hold, x.model));
      if (!mine.length) continue;
      let t = '';
      const mTot = mine.reduce((a, r) => a + r.model, 0), hTot = mine.reduce((a, r) => a + r.hold, 0);
      const sumPct = mine.reduce((a, r) => a + (r.pk && r.pk.pct != null ? r.pk.pct : 0), 0);
      t += `<tr class="sec"><td><span class="bld-sw" style="background:${bcol(b)}"></span>${esc(b)}${(fin[b] || 0) > 0 ? `<br><span class="bld-muted bld-tsum">target ${(fin[b]).toFixed(0)}%</span>` : ''}</td><td class="n ${(sumPct > 100.5 || (fin[b] || 0) > 0 && mTot / amt * 100 > fin[b] + 0.5) ? 'bld-over' : ''}" title="${sumPct > 0 ? 'Your % boxes in this class add to ' + sumPct.toFixed(0) + '%' : ''}">${usd(mTot)} · ${pct(mTot / amt, 0)}${sumPct > 100.5 ? ' (' + sumPct.toFixed(0) + '% of class)' : ''}</td><td class="n">${usd(hTot)} · ${acctVal ? pct(hTot / acctVal, 0) : ''}</td><td class="n">${sgnUsd(mTot - hTot)}</td><td></td></tr>`;
      mine.forEach(r => {
        const ph = r.pos && (fin[b] || 0) > 0 ? (r.pos.value / amt * 100 / fin[b] * 100).toFixed(0) : 'equal';
        const pCell = r.pk
          ? `<input type="number" min="0" max="100" step="1" data-pct="${esc(r.sym)}" value="${r.pk.pct == null ? '' : r.pk.pct}" placeholder="${ph}" style="width:80px" title="% of ${esc(b)}"> % ` +
            `${r.pos ? '<b>' + usd(r.pos.value) + '</b>' : '<span class="bld-muted">not buyable</span>'} <button class="bld-btn sm alt" data-drop="${esc(r.sym)}" title="Remove from picks">×</button>`
          : dash;
        const hCell = r.h ? `${usd(r.hold)} <span class="bld-muted">${acctVal ? pct(r.hold / acctVal, 1) : ''}</span>${r.kept ? ' <span class="bld-badge sell">Kept</span>' : ''}` : dash;
        const gap = (r.pk || r.h) ? sgnUsd(r.model - r.hold) : '';
        t += `<tr${(!r.pk && !r.kept) ? ' class="zero"' : ''}><td>${symHtml(r.sym)}</td><td class="n">${pCell}</td><td class="n">${hCell}</td><td class="n">${gap}</td>` +
          `<td>${esc(r.kept ? 'Kept' : (r.pk ? r.trade : (r.h ? 'Held, not in picks' : '')))}</td></tr>`;
      });
      side[b === 'Equities' ? 'right' : 'left'] += t;
    }
    const tbl = rowsHtml => rowsHtml ? head + rowsHtml + '</tbody></table>' : '';
    return `<div class="bld-sym2"><div>${tbl(side.left)}</div><div>${tbl(side.right)}</div></div>`;
  }

  // ---------------------------------------------------------------- step 2: your picks, actual mix, factor mix
  function renderPicks(res) {
    Object.assign(S.outlooks, res.outlooks || {});
    $('picksCount').textContent = S.picks.length ? `${S.picks.length} picked` : '';
    $('cmpTable').innerHTML = compareTable(res);
    bindCmp();
    $('symTable').innerHTML = symbolTable(res);
    $('symTable').querySelectorAll('[data-pct]').forEach(i => i.onchange = () => {
      const p = picked(i.dataset.pct);
      if (p) { p.pct = i.value === '' ? null : Math.max(0, parseFloat(i.value)); schedule(0); }
    });
    $('symTable').querySelectorAll('[data-drop]').forEach(btn => btn.onclick = () => { setPick(btn.dataset.drop, false); renderSourceNames(); schedule(0); });
  }

  // ---------------------------------------------------------------- preview
  function schedule(ms) {
    clearTimeout(S.timer);
    S.timer = setTimeout(runPreview, ms == null ? 400 : ms);
  }

  async function runPreview() {
    const seq = ++S.reqSeq;
    try {
      const res = await post('/api/builder/preview', buildReq());
      if (seq !== S.reqSeq) return;
      S.preview = res;
      render(res);
      if (S.matchNext) { S.matchNext = false; $('matchHold').click(); }   // auto-picked held names take the account's own weights
    } catch (e) {
      if (seq !== S.reqSeq) return;
      $('cmpTable').innerHTML = `<span class="bld-warn">Could not build: ${esc(e.message)}</span>`;
    }
  }

  // ---------------------------------------------------------------- saved sets (picks + targets, by name)
  async function loadSets(selectId) {
    try {
      const r = await api('/api/builder/sets');
      S.sets = r.sets || [];
      $('setSel').innerHTML = S.sets.length ? S.sets.map(x => `<option value="${x.id}">${esc(x.name)}${x.account ? ' · ' + esc(x.account) : ''}</option>`).join('') : '<option value="">(none saved)</option>';
      if (selectId) $('setSel').value = String(selectId);
    } catch (e) { $('setMsg').textContent = 'Could not load saved sets: ' + e.message; }
  }

  async function saveSet() {
    const cur = (S.sets || []).find(x => String(x.id) === $('setSel').value);
    const name = window.prompt('Save as (an existing name is replaced)', cur ? cur.name : '');
    if (!name || !name.trim()) return;
    const state = { acct: S.acct, picks: S.picks, assign: S.assign, targets: S.targets, preset: S.preset, mix: S.mix,
      sources: S.sources, useDial: S.useDial, amount: S.amount };
    try {
      const r = await api('/api/builder/sets', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim(), account: S.acct, state }) });
      await loadSets(r.id);
      $('setMsg').textContent = 'Saved "' + r.name + '"';
    } catch (e) { $('setMsg').textContent = e.message; }
  }

  async function openSet() {
    const id = $('setSel').value;
    if (!id) return;
    try {
      const r = await api('/api/builder/sets/' + id), st = r.state || {};
      S.acct = st.acct || r.account || S.acct;
      if ([...$('acctSel').options].some(o => o.value === S.acct)) $('acctSel').value = S.acct;
      S.picks = st.picks || []; S.assign = st.assign || {}; S.targets = st.targets || {};
      S.preset = st.preset || 'current'; S.mix = st.mix || null; S.useDial = false; S.amount = st.amount || null;
      S.sources = st.sources || []; S.seeded = S.acct;
      renderSources();
      $('preset').value = S.preset;
      $('setMsg').textContent = 'Opened "' + r.name + '"';
      await loadSourceNames();
      schedule(0);
    } catch (e) { $('setMsg').textContent = e.message; }
  }

  async function deleteSet() {
    const id = $('setSel').value;
    if (!id || !window.confirm('Delete this saved set?')) return;
    try { await api('/api/builder/sets/' + id, { method: 'DELETE' }); await loadSets(); $('setMsg').textContent = 'Deleted'; }
    catch (e) { $('setMsg').textContent = e.message; }
  }

  // first view of an account: every Target starts at what the account holds now, to edit as you work
  function seedTargets(res) {
    const H = (res.exposure || {}).held || {};
    if (S.seeded === S.acct || !(H.total > 0)) return;
    S.seeded = S.acct;
    const t = {}, r0 = v => Math.round(v);
    const put = (k, v) => { if (v != null && v >= 0.5) t[k] = r0(v); };
    if (H.beta != null) t.beta = Math.round(H.beta * 100) / 100;
    put('lowbeta', H.lowbeta); put('highbeta', H.highbeta);
    ['Q1', 'Q2', 'Q3', 'Q4'].forEach(q => put('quad:' + q, ((H.quad || {})[q] || {}).bull));
    Object.keys(H.sector || {}).forEach(s => put('sector:' + s, H.sector[s]));
    Object.keys(H.style || {}).forEach(s => put('style:' + s, H.style[s]));
    S.targets = t;
  }

  function render(res) {
    problems(res.problems);
    seedTargets(res);
    renderAcct(res);
    renderMix(res);
    renderPicks(res);
    document.querySelectorAll('[data-warn]').forEach(c => { c.checked = !!S.warn[c.dataset.warn]; });
  }

  // ---------------------------------------------------------------- account bar
  function renderAcct(res) {
    const a = res.account || {};
    const atype = S.acct === 'ALL' ? 'all accounts' : (a.type && a.type !== 'OTHER' ? a.type : '');
    $('acctType').textContent = atype ? 'Type: ' + atype : '';
    $('acctType').hidden = !atype;
    const run = a.running;
    $('acctRun').textContent = S.acct === 'ALL' ? 'Preview only, cannot be frozen' : (run ? `Running model: ${run.name} (ends ${run.end_date})` : 'Running model: none');
    $('acctRun').className = 'bld-pill' + (run ? ' warn' : '');
    $('acctSnap').textContent = a.snap_date ? 'Positions file: ' + a.snap_date + (a.positions_stale ? ' (older than 3 trading days)' : '') : '';
    if ($('amount') && document.activeElement !== $('amount')) $('amount').value = S.amount || Math.round(a.value || 0);
    const rb = $('runBanner');
    rb.hidden = !(run && S.acct !== 'ALL');
    rb.textContent = run ? `${S.acct} already has a running model: ${run.name} (ends ${run.end_date}). Accepting a new one will close it and start this one.` : '';
  }

  // ---------------------------------------------------------------- step 2: mix
  function stackBar(vals, extra) {
    const segs = BUCKETS.concat(['Cash']).map(b => [b, vals[b] || 0, b === 'Cash' ? _PM_ASSET_COLORS.Cash : bcol(b)]);
    if (extra && extra.Unmapped) segs.push(['Unmapped', extra.Unmapped, _PM_ASSET_COLORS.Unclassified]);
    return segs.filter(s => s[1] > 0.04).map(s => `<span style="width:${s[1]}%;background:${s[2]}" title="${esc(s[0])} ${s[1].toFixed(1)}%">${s[1] >= 6 ? esc(s[0]) + ' ' + Math.round(s[1]) + '%' : ''}</span>`).join('');
  }

  function renderMix(res) {
    const cur = res.mix_current || {}, tgt = res.mix_target || {}, fin = res.mix_final || {};
    if (S.preset === 'custom' && !S.mix) S.mix = Object.assign({}, tgt);
    $('preset').value = S.preset;
  }

  // ---------------------------------------------------------------- proposal
  function fcBadge(p) {
    if (!p.final_code) return '<span class="bld-muted">-</span>';
    const side = p.final_side || 'neutral';
    return `<span class="bld-badge ${side}">${esc(ACT_LABEL[p.final_code] || p.final_code)}</span>` + (p.conflict ? ' <span class="bld-badge sell">Conflict</span>' : '');
  }

  // ---------------------------------------------------------------- list view
  async function loadList() {
    const acct = $('listAcct').value, status = $('listStatus').value;
    try {
      const r = await api(withDate('/api/builder/portfolios?' + (acct ? 'account=' + encodeURIComponent(acct) + '&' : '') + 'status=' + status));
      if (r.problems && r.problems.length) problems(r.problems);
      const have = new Set([...$('listAcct').options].map(o => o.value));
      S.accounts.forEach(a => { if (!have.has(a.short)) { $('listAcct').insertAdjacentHTML('beforeend', `<option value="${esc(a.short)}">${esc(a.short)}</option>`); } });
      $('listCount').textContent = '(' + r.portfolios.filter(p => p.status !== 'CLOSED').length + ')';
      const totals = {};
      (r.totals || []).forEach(t => { totals[t.account] = t; });
      let h = '', prev = null;
      const flush = a => {
        const t = totals[a];
        if (!t) return;
        h += `<tr class="tot"><td>${esc(a)} total</td><td colspan="5" class="bld-muted">running model only · all periods paper gain ${sgnUsd(t.all_gain)}</td><td class="n">${t.running_amount ? usd(t.running_value) : '—'}</td><td class="n ${cls(t.running_ret)}">${t.running_ret == null ? '' : sgnPct(t.running_ret)}</td><td colspan="3"></td></tr>`;
      };
      for (const p of r.portfolios) {
        if (prev !== null && prev !== p.account) flush(prev);
        prev = p.account;
        const alert = p.alerts.length ? ` <span class="bld-tip bld-warn" data-tip="${tipAttr(p.alerts)}">&#9679;</span>` : '';
        const stt = p.status === 'REVIEW_DUE' ? '<span class="bld-warn">Review due</span>' : p.status === 'CLOSED' ? `<span class="bld-muted">Closed${p.close_reason ? ' (' + esc(p.close_reason) + ')' : ''}</span>` : esc(p.status === 'RUNNING' ? 'Running' : p.status);
        h += `<tr class="click" data-id="${p.portfolio_id}"><td>${esc(p.account)}</td><td>${esc(p.name)}${alert}</td><td>${esc(p.mix)}</td><td>${esc(p.split)}</td><td>${esc(p.start)} → ${esc(p.end)}</td>` +
          `<td>${p.days} / ${p.total_days || '?'}</td><td class="n">${usd(p.value)}</td><td class="n ${cls(p.ret)}">${sgnPct(p.ret)}</td><td class="n ${cls(p.vs_spy)}">${sgnPct(p.vs_spy)}</td><td class="n ${cls(p.vs_account)}">${sgnPct(p.vs_account)}</td><td>${stt}</td></tr>`;
      }
      if (prev !== null) flush(prev);
      const sf = r.shared_funds || { funds: [], over_note: [] };
      const tip = sf.funds.length ? tipAttr(sf.funds.map(f => `${f.sym}: ${f.models} models, ${usd(f.value)}${f.share != null ? ' = ' + pct(f.share, 0) + ' of all running models' : ''}`).concat(sf.over_note.length ? ['Over 20% of all running models: ' + sf.over_note.join(', ')] : [])) : tipAttr(['No fund is in 2 or more running models']);
      if (r.portfolios.length) h += `<tr class="gtot"><td>All accounts</td><td colspan="5"><span class="bld-tip" data-tip="${tip}">Same fund in several accounts: ${sf.funds.length} fund${sf.funds.length === 1 ? '' : 's'}</span></td><td class="n">${usd(r.grand.value)}</td><td class="n ${cls(r.grand.ret)}">${sgnPct(r.grand.ret)}</td><td colspan="3" class="bld-muted">value-weighted, running models</td></tr>`;
      $('listRows').innerHTML = h || '<tr><td colspan="11" class="bld-muted">No model portfolios yet. Build one and accept it.</td></tr>';
      $('listRows').querySelectorAll('tr.click').forEach(tr => tr.onclick = () => openDetail(parseInt(tr.dataset.id, 10)));
    } catch (e) { problems(['Could not load model portfolios: ' + e.message]); }
  }

  // ---------------------------------------------------------------- detail view
  async function openDetail(id) {
    try {
      const d = await api(withDate('/api/builder/portfolios/' + id));
      S.detail = d;
      showView('detail');
      renderDetail(d);
    } catch (e) { problems([e.message]); }
  }

  function driftStack(vals) {
    return stackBar(vals);
  }

  function renderDetail(d) {
    Object.assign(S.outlooks, d.outlooks || {});
    const k = d.kpis, ai = d.account_info || {};
    const stat = d.status === 'REVIEW_DUE' ? 'review due' : d.status.toLowerCase();
    let h = `<h3 style="margin:0 0 8px">${esc(d.name)} · account ${esc(d.account)} (${esc(d.account_type || 'OTHER')}) · day ${d.day} of ${d.total_days || '?'} · frozen since ${esc(d.start)} · ends ${esc(d.end)} · ${esc(stat)}${d.close_reason ? ' (' + esc(d.close_reason) + ')' : ''}</h3>`;
    h += `<div class="bld-kpis"><div class="bld-kpi"><small>Return</small><b class="${cls(k.ret)}">${sgnPct(k.ret)}</b></div><div class="bld-kpi"><small>vs SPY</small><b class="${cls(k.vs_spy)}">${sgnPct(k.vs_spy)}</b></div>` +
      `<div class="bld-kpi"><small>vs account ${esc(d.account)}</small><b class="${cls(k.vs_account)}">${sgnPct(k.vs_account)}</b></div><div class="bld-kpi"><small>Worst drop</small><b class="bld-dn">${k.worst_drop == null ? '-' : sgnPct(k.worst_drop)}</b></div>` +
      `<div class="bld-kpi"><small>Swings (model vs SPY)</small><b>${k.swings == null ? 'n/a yet' : pct(k.swings, 0) + ' vs ' + pct(k.spy_swings, 0)}</b></div><div class="bld-kpi"><small>Alerts</small><b>${k.alerts}</b></div></div>`;
    h += `<div class="bld-muted" style="margin-bottom:6px">${esc(d.note)} "vs account" compares with what the account held at the start, left untouched (not a flow-adjusted return).</div>`;
    // alerts + opt-in warnings
    const oi = d.opt_in || {};
    h += `<div class="bld-card"><h3>Alerts <span class="bld-muted">(alert only: they never change the portfolio)</span></h3>` +
      (d.alerts.length ? d.alerts.map(a => `<div><span class="bld-warn">&#9679;</span> ${esc(a.message)} <span class="bld-muted">(${esc(a.date)})</span> <button class="bld-btn sm alt" data-dismiss="${esc(a.code)}">Dismiss</button></div>`).join('') : '<div class="bld-muted">No alerts.</div>') +
      `<div class="bld-line" style="margin-top:6px">` + [['drop', 'down 10% from start'], ['quad_turn', 'Quad check says "transition"'], ['no_new_risk', 'Risk Dial says "No new risk"'], ['final_call_sell', 'a Final Call turns Sell']].map(w => `<label><input type="checkbox" data-optin="${w[0]}" ${oi[w[0]] ? 'checked' : ''}> Tell me if ${w[1]}</label>`).join(' ') + `</div></div>`;
    h += `<div class="bld-card"><h3>Model, same money in SPY, and your account's untouched holdings</h3><div style="height:260px"><canvas id="detChart"></canvas></div></div>`;
    // drift
    if (d.drift) {
      const cur = {}, tgt = {}, mod = {};
      d.drift.forEach(r => { tgt[r.bucket] = r.target; mod[r.bucket] = r.model; cur[r.bucket] = r.account; });
      h += `<div class="bld-card"><h3>Allocation drift <span class="bld-muted">(${esc(d.account)}, today; click Equities for areas)</span></h3><table class="bld-t"><thead><tr><th>Bucket</th><th class="n">Target</th><th class="n">Model now</th><th class="n">Account now</th><th class="n">Account vs target</th></tr></thead><tbody>` +
        d.drift.map(r => `<tr${r.bucket === 'Equities' ? ' class="click" id="eqDrift"' : ''}><td><span class="bld-sw" style="background:${r.bucket === 'Cash' ? _PM_ASSET_COLORS.Cash : bcol(r.bucket)}"></span>${esc(r.bucket)}${r.bucket === 'Equities' && d.area_drift ? ' ▸' : ''}</td><td class="n">${r.target.toFixed(0)}%</td><td class="n">${r.model.toFixed(0)}%</td><td class="n">${r.account.toFixed(0)}%</td><td class="n ${r.amber ? 'bld-amb' : ''}">${r.gap > 0 ? '+' : ''}${r.gap.toFixed(0)} pts</td></tr>`).join('') + '</tbody></table>' +
        `<div style="margin-top:8px"><div class="bld-stackrow"><span>Target</span><div class="bld-stack">${driftStack(tgt)}</div></div><div class="bld-stackrow"><span>Model now</span><div class="bld-stack">${driftStack(mod)}</div></div><div class="bld-stackrow"><span>Account now</span><div class="bld-stack">${driftStack(cur)}</div></div></div>`;
      if (d.area_drift && d.area_drift.length) h += `<div id="driftAreas" hidden style="margin-top:10px"><table class="bld-t"><thead><tr><th>Equities area</th><th>Macro at build</th><th class="n">Target</th><th class="n">Model now</th><th class="n">Account now</th><th class="n">Gap</th></tr></thead><tbody>` +
        d.area_drift.map(r => `<tr><td>${esc(r.area)}</td><td><span class="bld-chip ${r.chip_at_build === '-' ? 'dash' : r.chip_at_build}">${esc(r.chip_at_build)}</span></td><td class="n">${r.target.toFixed(1)}%</td><td class="n">${r.model.toFixed(1)}%</td><td class="n">${r.account.toFixed(1)}%</td><td class="n ${r.amber ? 'bld-amb' : ''}">${r.gap > 0 ? '+' : ''}${r.gap.toFixed(1)} pts</td></tr>`).join('') + '</tbody></table></div>';
      h += '<div class="bld-muted">Amber = 5 points or more away from target. Drift is not good or bad, so no green or red. "Model now" drifts with prices because we hold shares, not weights.</div></div>';
    } else if (ai.active === false) h += '<div class="bld-card bld-muted">Account inactive: the model keeps marking on its frozen shares.</div>';
    // holdings
    h += `<div class="bld-card"><h3>Holdings</h3><div style="overflow-x:auto"><table class="bld-t"><thead><tr><th>Fund</th><th>Area</th><th class="n">Shares</th><th class="n">Entry</th><th class="n">Now</th><th class="n">Return</th><th class="n">Weight now</th><th>Final Call now</th><th>Why here</th></tr></thead><tbody>` +
      d.positions.map(p => `<tr><td>${symHtml(p.sym)}${p.is_kept ? ' &#128274;' : ''}${p.stale_days ? ` <span class="bld-warn" title="No new price for ${p.stale_days} day(s)">&#9679;</span>` : ''}</td><td>${esc(p.area || '')}</td><td class="n">${p.shares == null ? '' : Math.round(p.shares)}</td><td class="n">${p.entry == null ? '' : p.entry.toFixed(2)}</td><td class="n">${p.close == null ? '' : p.close.toFixed(2)}</td><td class="n ${cls(p.ret)}">${sgnPct(p.ret)}</td><td class="n">${pct(p.weight_now, 1)}</td>` +
        `<td>${p.final_now ? `<span class="bld-badge ${/^(SA|SS|STM|SO|SW|SWW|REMOVE|REDUCE)$/.test(p.final_now) ? 'sell' : /^(BM|BS|BMN|BW|BSW|INCREASE|ADD)$/.test(p.final_now) ? 'buy' : 'neutral'}">${esc(ACT_LABEL[p.final_now] || p.final_now)}</span>` : '-'}</td><td><span class="bld-tip" data-tip="${tipAttr(p.why_detail)}">${esc(p.why || '')}</span></td></tr>`).join('') + '</tbody></table></div></div>';
    // vs account
    const va = d.vs_account;
    if (va) {
      h += `<div class="bld-card"><h3>vs your account <span class="bld-muted">(${esc(d.account)} holdings only, no scaling)</span></h3><div style="overflow-x:auto"><table class="bld-t"><thead><tr><th>Fund</th><th>Area</th><th class="n">Model $</th><th class="n">You hold $</th><th class="n">Gap $</th><th>Trade to match</th><th class="n">Tax if sold</th></tr></thead><tbody>` +
        va.rows.map(r => `<tr><td>${symHtml(r.sym)}${r.kept ? ' &#128274;' : ''}</td><td>${esc(r.area || '')}</td><td class="n">${r.model == null ? '—' : usd(r.model)}</td><td class="n">${usd(r.hold)}</td><td class="n">${r.gap == null ? '—' : sgnUsd(r.gap)}</td><td>${esc(r.trade)}${r.trade.startsWith('Buy') || r.trade.startsWith('Sell') ? ' <span class="bld-muted">(only if you want to match, not advice)</span>' : ''}</td><td class="n">${r.tax == null ? '' : sgnUsd(r.tax) + (r.tax >= 0 ? ' gain' : ' loss')}</td></tr>`).join('') +
        `</tbody></table></div><div style="margin-top:6px"><b>Matches model: ${va.match_pct == null ? '-' : va.match_pct.toFixed(0) + '%'}</b>${va.tax ? ` · selling to match would realise about <b>${sgnUsd(va.tax.gain)}</b> gain / <b>${sgnUsd(va.tax.loss)}</b> loss (estimate, not tax advice)` : ''}${va.paper_only ? ' · 401k: paper-only, plan funds only' : ''}</div></div>`;
    }
    // promise
    const pc = d.promise || { items: [], hit_rate: {} };
    h += `<div class="bld-card"><h3>Promise check <span class="bld-muted">(fills in as days pass; final at the end)</span></h3>` +
      pc.items.map(i => `<div>${i.result === 'pass' ? '<span class="bld-up">✓</span>' : i.result === 'fail' ? '<span class="bld-dn">✗</span>' : '•'} ${esc(i.label)} <b>${esc(i.detail)}</b></div>`).join('') +
      `<div>• Funds beating SPY: <b>${pc.hit_rate.beat == null ? 'n/a yet' : pc.hit_rate.beat + ' of ' + pc.hit_rate.of}</b></div></div>`;
    h += `<button class="bld-btn alt" id="reviewBtn" ${d.review_available ? '' : 'disabled'} title="Opens on the end date; it never runs by itself">End-of-period review</button> <span class="bld-muted">Roll over · Change recipe · Close (available from ${esc(d.end)})</span>`;
    $('detailBody').innerHTML = h;
    if ($('eqDrift')) $('eqDrift').onclick = () => { const el = $('driftAreas'); if (el) el.hidden = !el.hidden; };
    document.querySelectorAll('[data-dismiss]').forEach(b => b.onclick = async () => { await api('/api/builder/portfolios/' + d.portfolio_id + '/warnings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dismiss: [b.dataset.dismiss] }) }); openDetail(d.portfolio_id); });
    document.querySelectorAll('[data-optin]').forEach(c => c.onchange = async () => { await api('/api/builder/portfolios/' + d.portfolio_id + '/warnings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ opt_in: { [c.dataset.optin]: c.checked } }) }); });
    if ($('reviewBtn')) $('reviewBtn').onclick = () => openReview(d);
    drawChart(d);
  }

  function drawChart(d) {
    if (S.chart) { S.chart.destroy(); S.chart = null; }
    const cv = $('detChart');
    if (!cv || typeof Chart === 'undefined' || !d.series.dates.length) return;
    const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || undefined;
    S.chart = new Chart(cv, {
      type: 'line',
      data: { labels: d.series.dates, datasets: [
        { label: 'Model', data: d.series.model, borderColor: css('--cat1') || '#1d4ed8', pointRadius: 2, tension: 0.1 },
        { label: 'Same money in SPY', data: d.series.spy, borderColor: css('--neutral') || '#6b7280', pointRadius: 0, borderDash: [4, 3], tension: 0.1 },
        { label: 'Your account, untouched', data: d.series.account, borderColor: css('--cat2') || '#0f9488', pointRadius: 0, tension: 0.1 },
      ] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, scales: { y: { ticks: { callback: v => '$' + Math.round(v).toLocaleString() } } } },
    });
  }

  // ---------------------------------------------------------------- end-of-period review
  async function openReview(d) {
    const host = $('modalHost');
    host.innerHTML = '<div class="bld-modal"><div><span class="bld-muted">Building a fresh proposal with the same settings...</span></div></div>';
    try {
      const r = await api(withDate('/api/builder/portfolios/' + d.portfolio_id + '/review-preview'));
      const k = d.kpis, c = r.change;
      const list = (a, f) => a.length ? a.map(f).join(', ') : 'none';
      host.innerHTML = `<div class="bld-modal"><div><h3 style="margin-top:0">End-of-period review · ${esc(d.name)}</h3>` +
        `<div class="bld-kpis"><div class="bld-kpi"><small>Return</small><b class="${cls(k.ret)}">${sgnPct(k.ret)}</b></div><div class="bld-kpi"><small>vs SPY</small><b class="${cls(k.vs_spy)}">${sgnPct(k.vs_spy)}</b></div><div class="bld-kpi"><small>vs account</small><b class="${cls(k.vs_account)}">${sgnPct(k.vs_account)}</b></div><div class="bld-kpi"><small>Worst drop</small><b>${k.worst_drop == null ? '-' : sgnPct(k.worst_drop)}</b></div></div>` +
        d.promise.items.map(i => `<div>${i.result === 'pass' ? '✓' : i.result === 'fail' ? '✗' : '•'} ${esc(i.label)} <b>${esc(i.detail)}</b></div>`).join('') +
        `<div><b>Hit rate:</b> ${d.promise.hit_rate.beat == null ? 'n/a' : d.promise.hit_rate.beat + ' of ' + d.promise.hit_rate.of} funds beat SPY</div>` +
        `<h4>What changes if you roll over (same settings, today's data)</h4>` +
        `<div><b>Keep (${c.keep.length}):</b> ${esc(list(c.keep, x => x.sym + ' ' + Math.round(x.old_shares) + '→' + Math.round(x.new_shares) + ' sh'))}</div>` +
        `<div><b>Add (${c.add.length}):</b> ${esc(list(c.add, x => x.sym + ' ' + Math.round(x.new_shares) + ' sh'))}</div>` +
        `<div><b>Drop (${c.drop.length}):</b> ${esc(list(c.drop, x => x.sym + ' ' + Math.round(x.old_shares) + ' sh'))}</div>` +
        `<div class="bld-disc">This applies your chosen recipe mechanically. Past results only, not a forecast.</div>` +
        `<div style="margin-top:10px"><button class="bld-btn" id="rvRoll">Roll over</button><button class="bld-btn alt" id="rvChange">Change recipe</button><button class="bld-btn alt" id="rvClose">Close</button><button class="bld-btn alt" id="rvCancel">Cancel</button></div></div></div>`;
      $('rvCancel').onclick = () => { host.innerHTML = ''; };
      $('rvClose').onclick = async () => { if (!confirm('Stop tracking this model and keep its history?')) return; await review(d, 'close'); };
      $('rvRoll').onclick = async () => { if (!confirm('Freeze the fresh build as a new portfolio linked to this one?')) return; await review(d, 'roll'); };
      $('rvChange').onclick = () => { host.innerHTML = ''; prefill(d); };
    } catch (e) { host.innerHTML = ''; window.alert(e.message); }
  }

  async function review(d, action) {
    try {
      await post('/api/builder/portfolios/' + d.portfolio_id + '/review', { action });
      $('modalHost').innerHTML = '';
      await reloadAll();
      showView('list');
    } catch (e) { window.alert(e.message); }
  }

  function prefill(d) {
    const req = (d.settings && d.settings.req) || {};
    S.acct = d.account; S.horizon = req.horizon || d.horizon; S.preset = req.preset || 'balanced'; S.mix = req.mix || null;
    S.useDial = false; S.amount = null;
    S.picks = req.manual ? (req.picks || []).map(p => ({ sym: p.sym, bucket: p.bucket, pct: p.pct == null ? null : p.pct })) : [];
    renderSourceNames();
    $('acctSel').value = S.acct;
    showView('build');
    schedule(0);
  }


  document.addEventListener('DOMContentLoaded', init);
})();
