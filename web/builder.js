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
  // Every panel gets a small button (top right) that collapses it to its title. Remembered in this browser only.
  function makePanelsCollapsible() {
    const panels = [['.bld-acct', 'Account and plan', 'acct'], ['#srcBox', 'Lists to choose from', 'lists', '.bld-card'], ['#srcNames', 'Names', 'names'],
      ['.bld-picks', 'Stock picks', 'picks'], ['#todoCard', 'To do', 'todo']];
    let st = {};
    try { st = JSON.parse(localStorage.getItem('bld_cx') || '{}') || {}; } catch (e) { st = {}; }
    panels.forEach(([sel, title, key, up]) => {
      let el = document.querySelector(sel);
      if (el && up) el = el.closest(up);
      if (!el || el.querySelector(':scope > .bld-cx')) return;
      el.dataset.ctitle = title;
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'bld-cx';
      const paint = () => { const shut = el.classList.contains('cx-collapsed'); b.innerHTML = shut ? '&#9656;' : '&#9662;'; b.title = (shut ? 'Show ' : 'Hide ') + title; };
      b.onclick = () => {
        el.classList.toggle('cx-collapsed');
        st[key] = el.classList.contains('cx-collapsed');
        try { localStorage.setItem('bld_cx', JSON.stringify(st)); } catch (e) { /* private window */ }
        paint();
      };
      if (st[key]) el.classList.add('cx-collapsed');
      el.prepend(b);
      paint();
    });
  }

  async function init() {
    makePanelsCollapsible();
    try {
      const dates = await api('/api/dates');
      const sel = $('datePicker');
      sel.innerHTML = dates.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
      S.date = dates[0] || null;
      if (S.date) sel.value = S.date;
      sel.onchange = () => { S.date = sel.value; reloadAll(); };
    } catch (e) { problems(['Could not load dates: ' + e.message]); }
    $('refreshBtn').onclick = reloadAll;
    document.querySelectorAll('[data-warn]').forEach(c => c.onchange = () => { S.warn[c.dataset.warn] = c.checked; });
    // 2026-11-14 save-safety: ask before dropping unsaved edits; the old account's picks never follow you to the next account;
    // the saved plan (if any) loads first and marks the targets as seeded so holdings never overwrite them.
    $('acctSel').onchange = () => {
      if (PL.dirty && !window.confirm('You have unsaved changes for ' + S.acct + '. Switch account and lose them?')) { $('acctSel').value = S.acct; return; }
      S.acct = $('acctSel').value; S.amount = null; S.targets = {}; S.seeded = null; S.guideFor = null; S.preset = 'current'; S.mix = null;
      S.picks = []; S.fillGapNext = false; S.matchNext = false; PL.dirty = false;
      loadSourceNames(); planLoad(); schedule(0);
    };
    try {
      const so = await api('/api/builder/sources');
      S.srcList = so.sources || [];
      if (S.srcList.some(x => x.code === 'HELD')) S.sources = ['HELD'];
      renderSources();
    } catch (e) { problems(['Could not load source lists: ' + e.message]); }

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
      S.presetOpts = po;
      if (!po.some(p => p[0] === S.preset)) S.preset = po.length > 2 ? po[1][0] : 'current';
      planInit();
    } catch (e) { problems(['Could not load accounts: ' + e.message]); }
    loadSourceNames();
    if (first !== true || true) schedule(0);
  }

  function problems(list) {
    const el = $('bldProblems');
    const msgs = (list || []).filter(Boolean);
    el.hidden = !msgs.length;
    el.innerHTML = msgs.map(esc).join('<br>');
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
    $('srcNamesRows').addEventListener('click', e => { const t = e.target.closest('[data-ftype]'); if (t) toggleFilter(t.dataset.ftype, t.dataset.fval); });
    // Start from my holdings (one direct function, no hidden flags). A click ticks every stock the account holds (your other
    // picks stay), sets each one's share of its class, sets the asset class % to the current mix, fills the sector / style /
    // beta limits and the Buy $ gaps, and says what it did. The automatic pass on opening an account (auto = true) only ticks
    // and matches the held stocks: it never fills the limits or any Buy $.
    $('matchHold').onclick = () => startFromHoldings(false);
    startFromHoldings = function (auto) {
      const held = ((S.preview && S.preview.account && S.preview.account.holdings) || []);
      const hold = {};
      held.forEach(h => { hold[h.sym] = h.value || 0; });
      if (!auto) {
        const have = new Set(S.picks.map(p => p.sym));
        held.forEach(h => { if (h.value > 0 && h.bucket && h.bucket !== 'Cash' && BUCKETS.includes(h.bucket) && !have.has(h.sym)) S.picks.push({ sym: h.sym, bucket: h.bucket, pct: null }); });
      }
      const tot = {};
      S.picks.forEach(p => { if (hold[p.sym] > 0) tot[p.bucket] = (tot[p.bucket] || 0) + hold[p.sym]; });
      S.picks.forEach(p => { p.pct = hold[p.sym] > 0 ? Math.round(hold[p.sym] / tot[p.bucket] * 10000) / 100 : null; });
      S.fillGapNext = !auto;
      // opening an account with no saved plan starts the same way (limits = holdings, so the bars are green); it never
      // overwrites limits you already typed and does not count as an unsaved change
      if (auto && S.preview && !Object.keys(S.targets).length) seedTargets(S.preview);
      if (!auto) {
        S.preset = 'current'; S.mix = null;
        if (S.preview) seedTargets(S.preview);
        planDirty();
        $('srcNamesHint').textContent = 'Started from your holdings: ' + S.picks.filter(p => hold[p.sym] > 0).length + ' stocks, ' + Object.keys(S.targets).length + ' limits.';
      }
      renderSourceNames(); schedule(0);
    };
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
  const symHtml = sym => { const o = (S.outlooks[sym] || (S.nameCache[sym] || {}).outlook); const c = o && window.outlookColor ? window.outlookColor(o) : ''; return `<span${c && c !== 'inherit' ? ` style="color:${c}"` : ''}${o ? ` title="Outlook: ${esc(o)}"` : ''}>${window.symbolLink ? window.symbolLink(esc(sym), sym) : esc(sym)}</span>`; };
  const picked = sym => S.picks.find(p => p.sym === sym);
  const isEquitySector = n => !!n && !BUCKETS.includes(n) && !['Equities', 'Unmapped', 'Other', 'Cash'].includes(n);
  // which comparison sections are collapsed (Asset class, Risk, Style, ...): remembered in this browser only
  try { S.collapsed = JSON.parse(localStorage.getItem('bld_collapsed') || '{}') || {}; } catch (e) { S.collapsed = {}; }
  let startFromHoldings = () => {};   // set in renderSources()

  // 2026-10-29: copy-symbols icon (two overlapping squares, same as the Actionable screen) -> comma-separated, pastes into a TOS watchlist
  const COPY_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  const copyBtn = (kind, syms, tip) => `<button type="button" class="bld-copy" data-copy="${kind}"${syms ? ` data-syms="${esc(syms.join(','))}"` : ''} title="${esc(tip)}">${COPY_SVG}</button>`;
  async function copyText(text) {
    try { if (navigator.clipboard && navigator.clipboard.writeText) { await navigator.clipboard.writeText(text); return true; } } catch (e) { /* fall back below */ }
    try {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch (e) { return false; }
  }
  document.addEventListener('click', async e => {
    const b = e.target.closest('.bld-copy');
    if (!b) return;
    e.preventDefault();   // the copy icon sits in the panel header: do not also open / close the panel
    const k = b.dataset.copy;
    const syms = k === 'shown' ? shownNames().map(n => n.sym) : k === 'picks' ? S.picks.map(p => p.sym) : (b.dataset.syms || '').split(',').filter(Boolean);
    if (!syms.length) { b.title = 'Nothing to copy'; return; }
    const ok = await copyText(syms.join(','));
    const old = b.title;
    b.classList.toggle('ok', ok);
    b.title = ok ? 'Copied ' + syms.length + ' symbols' : 'Copy failed: the browser blocked clipboard access';
    setTimeout(() => { b.classList.remove('ok'); b.title = old; }, 1800);
  });

  // 2026-10-29: tags on each Names row are click-to-filter (same filters as the bar above the list; click again to clear)
  const STYLE_TO_FACTOR = { 'defensives': 'defensive', 'dividend': 'defensive', 'low beta': 'lowbeta', 'cyclical': 'offensive', 'small caps': 'offensive',
    'high beta': 'highbeta', 'mid caps': 'mid', 'secular': 'growth', 'value': 'value', 'momentum': 'mom' };
  const filterSel = { src: 'srcfSource', cls: 'srcfClass', sector: 'srcfSector', factor: 'srcfFactor' };
  const ftag = (type, val, html, tip) => {
    const el = type === 'quad' ? null : $(filterSel[type]);
    const on = type === 'quad' ? !!$('srcfQuad').querySelector(`input[value="${val}"]:checked`) : (el && el.value === val);
    return `<span class="bld-ftag${on ? ' on' : ''}" data-ftype="${type}" data-fval="${esc(val)}" title="${esc(tip)}">${html}</span>`;
  };
  function toggleFilter(type, val) {
    if (type === 'quad') {
      const c = $('srcfQuad').querySelector(`input[value="${val}"]`);
      if (c) c.checked = !c.checked;
    } else {
      const el = $(filterSel[type]);
      if (!el) return;
      if (el.value === val) el.value = '';
      else if ([...el.options].some(o => o.value === val)) el.value = val;
      else return;
      if (type === 'sector') fillIndustries('');
    }
    renderSourceNames();
  }

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
    if (on && n && b && n.usable && !picked(sym)) S.picks.push({ sym, bucket: b, pct: null, amt: null, grp: '' });
    if (!on) S.picks = S.picks.filter(p => p.sym !== sym);
  }

  function selectShown() {
    shownNames().forEach(n => setPick(n.sym, true));
    renderSourceNames(); schedule(0);
  }

  function renderSourceNames() {
    markActiveFilters();
    const all = S.srcNames || [];
    const rows = shownNames();
    $('srcNamesCount').textContent = all.length ? `${all.length} names` + (rows.length !== all.length ? ` · showing ${rows.length}` : '') : '';
    $('srcNamesHint').textContent = S.picks.length ? `${S.picks.length} picked` : '';
    if (!all.length) { $('srcNamesRows').innerHTML = `<tr><td colspan="9" class="bld-muted">${S.sources.length ? 'No names on those lists today.' : 'Tick a list on the left to see its names here.'}</td></tr>`; return; }
    $('srcNamesRows').innerHTML = rows.map(n => {
      const b = bucketOf(n), on = !!picked(n.sym);
      const cls = b ? esc(b) : `<select data-assign="${esc(n.sym)}"><option value="">Choose...</option>${BUCKETS.map(x => `<option>${esc(x)}</option>`).join('')}</select>`;
      const st = (n.styles || []).map(t => { const f = STYLE_TO_FACTOR[String(t).toLowerCase()]; return f ? ftag('factor', f, esc(t), 'Filter: ' + ((FACTORS.find(x => x[0] === f) || [])[1] || f) + ' (a group of related tags)') : esc(t); }).join(', ') || '<span class="bld-muted">-</span>';
      return `<tr><td><input type="checkbox" data-pick="${esc(n.sym)}" ${on ? 'checked' : ''} ${!b ? 'disabled' : ''} title="${!b ? 'Choose an asset class first' : 'Add to picks'}"></td>` +
        `<td>${symHtml(n.sym)}</td><td>${n.sources.map(c => ftag('src', c, esc(c), 'Show only the ' + c + ' list')).join(', ')}</td><td>${b ? ftag('cls', b, esc(b), 'Show only ' + b) : cls}</td><td>${(bucketOf(n) === 'Equities' && n.sector && !['Unmapped', 'Other'].includes(n.sector)) ? ftag('sector', n.sector, esc(n.sector), 'Show only ' + n.sector) : '<span class="bld-muted">-</span>'}</td>` +
        `<td>${(n.quad || []).map((w, i) => `<span class="bld-qp ${w || 'none'}${w ? ' bld-ftag' : ''}${w && $('srcfQuad').querySelector('input[value="' + i + '"]:checked') ? ' on' : ''}"${w ? ` data-ftype="quad" data-fval="${i}"` : ''} title="Q${i + 1}: ${w || 'no view'}${w ? ' (click: filter to Quad ' + (i + 1) + ' favored)' : ''}">${w ? 'Q' + (i + 1) : '-'}</span>`).join('')}</td><td class="n">${n.beta == null ? '<span class="bld-muted">-</span>' : n.beta.toFixed(2)}</td><td>${st}</td></tr>`;
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
  // 2026-11-15, user: chart and grid side by side, each bar on its own row. The bar is a cell inside the grid row, so it can never drift.
  // Rows are written with a placeholder cell (\u0005section\u0006index\u0007); this swaps in the real bar once the section's scale is known.
  function barCells(html, key, rows) {
    rows = rows || [];
    const any = rows.filter(r => r.pv != null || r.hv != null || r.tv != null);
    const scale = Math.max(10, ...any.map(r => Math.max(r.pv || 0, r.hv || 0, r.tv || 0))) * 1.15;
    const w = v => Math.min(Math.max(v, 0) / scale * 100, 100);
    return html.replace(/\u0005[^\u0006]*\u0006(\d+)\u0007/g, (m, i) => {
      const r = rows[+i];
      if (!r || (r.pv == null && r.hv == null && r.tv == null)) return '<td class="bld-bar"></td>';
      const pv = r.pv, tv = r.tv;
      const col = pv == null ? '#c3c2b7' : (tv != null && tv > 0 ? (pv > tv + 5 ? '#dc2626' : (pv < tv - 5 ? '#d97706' : '#16a34a')) : (r.col || '#b8bcc8'));
      return '<td class="bld-bar"><div class="bld-viz"><div class="vrow">' +
        `<div class="vtrack2">${pv != null ? `<div class="vfill" style="width:${w(pv)}%;background:${col}"></div>` : ''}${r.hv != null ? `<div class="vhold" style="width:${w(r.hv)}%"></div>` : ''}` +
        `${tv != null && tv > 0 ? `<div class="vtick" style="left:${w(tv)}%" title="Target ${tv.toFixed(0)}%"></div>` : ''}</div></div></div></td>`;
    });
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
    // 2026-11-14, user: in the Asset class grid, say in dollars what the account must do to reach the target (the account's own value).
    // Target vs what it holds now: Sell all / Sell $X / Room to buy $X / On plan. Information only; nothing trades.
    const planTd = (asset, tv, hv) => {
      if (curKey !== 'Asset class') return '<td></td>';
      if (!asset || tv == null || !hasHeld) return '<td></td>';
      const gap = (tv - (hv || 0)) / 100 * amt;
      if (tv === 0 && (hv || 0) * amt / 100 > 500) return `<td class="n bld-dn"><b>Sell all ${usd((hv || 0) * amt / 100)}</b></td>`;
      if (gap < -500) return `<td class="n bld-dn">Sell ${usd(-gap)}</td>`;
      if (gap > 500) return `<td class="n bld-up">Room ${usd(gap)}</td>`;
      return '<td class="n bld-muted">On plan</td>';
    };
    // One row. pv / hv = percent picked / held (null = nothing there). key = target key (null: no target cell);
    // asset = asset class name (its target is the mix you chose; judged against the mix after the Risk Dial).
    const R = (label, pv, hv, tip, key, asset, flt, tvx) => {   // tvx = a reference value with no box (Cash: what is left after the asset classes)
      const tv = asset ? (chosen[asset] > 0 ? Math.round(chosen[asset] * 100) / 100 : null) : (key ? tgtOf(key) : null);
      const eff = asset ? (fin[asset] > 0 ? fin[asset] : null) : (key ? tv : (tvx > 0 ? tvx : null));
      const cell = asset ? tgtCell(`data-tgt-asset="${esc(asset)}"`, tv) : (key ? tgtCell(`data-tgt="${esc(key)}"`, tv) : (tvx > 0 ? `<td class="n" title="Calculated: 100% minus the asset class targets above"><b>${Math.round(tvx * 100) / 100}</b></td>` : '<td></td>'));
      if (vizRows[curKey]) vizRows[curKey].push({ label: asset || String(label).replace(/<[^>]*>/g, ''), pv: hasPick ? pv : null, hv: hasHeld ? hv : null, tv: eff, col: asset ? bcol(asset) : null, flt });
      const barTd = `\u0005${curKey}\u0006${(vizRows[curKey] || []).length - 1}\u0007`;
      const pCell = hasPick && pv != null ? `<b class="${eff != null ? judge(pv, eff) : ''}">${f0(pv)}</b>` : dash;
      return `<tr${flt ? ` class="bld-frow" data-ftype="${flt[0]}" data-fval="${esc(flt[1])}" title="Click: show only this in the names list (Ctrl+click: add to the current filters)"` : ''}><td${tip ? ` class="bld-tip" data-tip="${esc(tip)}"` : ''}>${label}</td>${barTd}${cell}<td class="n">${pCell}</td><td class="n">${hasHeld && hv != null ? f0(hv) : dash}</td>` +
        `${eff != null ? gapCell(pv, eff, true, 0, true) : gapCell(pv, hv, hasHeld, 0, false)}${planTd(asset, asset && Object.keys(chosen).length ? (chosen[asset] || 0) : null, hv)}</tr>`;
    };
    const generalTip = 'Asset class rows are % of the account. Everything below is also % of the account (the same basis the plan check uses). Quad and style rows overlap (one fund can carry several), so they do not add to 100%. A stock takes its sector\'s Quad view. Red = over target.';
    let t = '';
    t += sec('Asset class');
    let placedTotal = 0, heldInvested = 0;
    for (const b of mixBuckets(res)) {
      const placed = (res.positions || []).filter(p => p.bucket === b).reduce((a, p) => a + p.value, 0) / amt * 100;
      placedTotal += placed;
      heldInvested += cur[b] || 0;
      t += R(`<span class="bld-sw" style="background:${bcol(b)}"></span>${esc(b)}`, placed, cur[b] || 0, null, null, b, ['cls', b]);
    }
    t += `<tr><td class="bld-tip" data-tip="All the money your picks place. Over 100% (red) means the picks add up to more than the account.">Total invested</td><td class="bld-bar"></td><td></td><td class="n">${S.picks.length ? `<b class="${placedTotal > 100.5 ? 'bld-over' : ''}">${f0(placedTotal)}</b>` : dash}</td><td class="n">${hasHeld ? f0(heldInvested) : dash}</td><td></td><td></td></tr>`;
    t += R(`<span class="bld-sw" style="background:${_PM_ASSET_COLORS.Cash}"></span>Cash`, (res.cash && res.cash.dollars || 0) / amt * 100, cur.Cash || 0, 'Cash and money not yet placed', null, undefined, undefined, Object.keys(chosen).length ? Math.max(0, 100 - BUCKETS.reduce((a, b) => a + (chosen[b] || 0), 0)) : fin.Cash);
    if (cur.Unmapped > 0.04) t += R('Unmapped', null, cur.Unmapped, 'Held with no asset class: cannot be picked');
    t += sec('Risk');
    const fb = v => (v == null ? dash : v.toFixed(2));
    t += R('Low beta (0.8 or under)', hasPick ? P.lowbeta : null, hasHeld ? H.lowbeta : null, null, 'lowbeta', undefined, ['factor', 'lowbeta']) + R('High beta (over 1.2)', hasPick ? P.highbeta : null, hasHeld ? H.highbeta : null, null, 'highbeta', undefined, ['factor', 'highbeta']);
    t += R('Middle beta (0.8 to 1.2)', hasPick ? P.midbeta : null, hasHeld ? H.midbeta : null, 'Names with a beta between 0.8 and 1.2: not low, not high.', 'midbeta')
      + R('No beta known', hasPick ? P.nobeta : null, hasHeld ? H.nobeta : null, 'Names with no beta yet (cash, new listings, some funds). Not covered by the beta rows above.', 'nobeta');
    t += sec('Quad');
    for (const q of ['Q1', 'Q2', 'Q3', 'Q4']) {
      const pq = (P.quad || {})[q], hq = (H.quad || {})[q];
      const tip = `${q} outlook. Picks: Bull ${bd(pq, 'bull').toFixed(0)}%, Neutral ${bd(pq, 'neutral').toFixed(0)}%, Bear ${bd(pq, 'bear').toFixed(0)}%, no view ${bd(pq, 'none').toFixed(0)}%. Portfolio: Bull ${bd(hq, 'bull').toFixed(0)}%, Neutral ${bd(hq, 'neutral').toFixed(0)}%, Bear ${bd(hq, 'bear').toFixed(0)}%, no view ${bd(hq, 'none').toFixed(0)}%`;
      t += R(q, hasPick ? bd(pq, 'bull') : null, hasHeld ? bd(hq, 'bull') : null, tip, 'quad:' + q, undefined, ['quad', String(['Q1', 'Q2', 'Q3', 'Q4'].indexOf(q))]);
    }
    t += sec('Sectors · equities');
    const sv = k => Math.max((P.sector || {})[k] || 0, (H.sector || {})[k] || 0, tgtOf('sector:' + k) || 0);
    const allSec = new Set(Object.keys(P.sector || {}).concat(Object.keys(H.sector || {})));
    Object.keys(S.targets).filter(k => k.startsWith('sector:')).forEach(k => allSec.add(k.slice(7)));
    Object.values(S.nameCache).forEach(n => { if (n.bucket === 'Equities' && n.sector && !['Unmapped', 'Other'].includes(n.sector)) allSec.add(n.sector); });
    [...allSec].filter(s => s === 'Equities' || !BUCKETS.includes(s)).sort((a, b) => sv(b) - sv(a) || a.localeCompare(b))   // Fixed Income / Gold / Currency are in the Asset class grid; 'Equities' here = equities with no sector
      .forEach(s => { t += R(s === 'Equities' ? 'No sector' : esc(s), hasPick ? ((P.sector || {})[s] || 0) : null, hasHeld ? ((H.sector || {})[s] || 0) : null, s === 'Equities' ? 'Equities with no sector assigned (not a filter: Equities is in the Asset class grid)' : null, 'sector:' + s, undefined, s === 'Equities' ? undefined : ['sector', s]); });
    t += sec('Style');
    [['defensive', 'Defensive'], ['offensive', 'Offensive'], ['value', 'Value'], ['growth', 'Growth'], ['mid', 'Mid']]
      .forEach(f => { t += R(f[1], hasPick ? ((P.style || {})[f[0]] || 0) : null, hasHeld ? ((H.style || {})[f[0]] || 0) : null, null, 'style:' + f[0], undefined, ['factor', f[0]]); });
    t += R('No style tag', hasPick ? P.nostyle : null, hasHeld ? H.nostyle : null, 'Names that carry none of the style groups above.', 'style:none');
    // 2026-10-28, user: show the sections in three columns. Cut the rows at each section break, one small table per section.
    const parts = t.split(/\u0001([^\u0002]*)\u0002/);          // ['', title1, rows1, title2, rows2, ...]
    const tables = {};
    for (let i = 1; i < parts.length; i += 2) {
      const title = parts[i], first = i === 1;
      const skey = title.split(' ·')[0], shut = !!S.collapsed[skey];
      tables[skey] = `<div class="bld-sec${shut ? ' collapsed' : ''}" data-sec="${esc(skey)}">` + (first ? presetHtml() : '') + `<table class="bld-t bld-exp"><thead><tr><th${first ? ` class="bld-tip" data-tip="${esc(generalTip)}"` : ''}><span class="bld-chev" data-sec-toggle="${esc(skey)}" title="${shut ? 'Show' : 'Hide'} this section">${shut ? '&#9656;' : '&#9662;'}</span> ${title}</th><th class="bld-bar-h" title="Bar = picks (green on target, amber short, red over), thin grey = portfolio, black line = target">Chart</th>` +
        `<th class="n bld-tip" data-tip="Type your target % on any row. Blank = no target. Targets guide you; they never pick stocks.">Target</th><th class="n">Picks</th><th class="n">Held</th><th class="n">Gap</th>${first ? '<th class="n bld-tip" data-tip="What the account must do to reach the Target, in dollars: Sell all, Sell, or Room to buy. Information only; nothing trades.">To plan</th>' : '<th></th>'}</tr></thead><tbody>${barCells(parts[i + 1], skey, vizRows[skey])}</tbody></table></div>`;
    }
    const T = k => tables[k] || '';
    // 2026-10-28, user: the five grids stay in three columns
    return `<div class="bld-cmp3"><div>${T('Asset class')}${T('Sectors')}</div><div>${T('Style')}${T('Quad')}${T('Risk')}</div></div>`;   // keys are the title up to " ·"
  }

  // The Preset sits between the Asset class bar chart and its grid: it only fills the asset class % boxes below it.
  function presetHtml() {
    const opts = (S.presetOpts || [['current', 'My current mix'], ['custom', 'Custom']]).map(p => `<option value="${esc(p[0])}"${p[0] === S.preset ? ' selected' : ''}>${esc(p[1])}</option>`).join('');
    return `<div class="bld-line" style="gap:6px;margin:4px 0"><b style="min-width:0" class="bld-tip" data-tip="A ready-made mix that fills the asset class % boxes below. Type a % in any box and this switches to Custom.">Fill classes from</b><select id="preset">${opts}</select></div>`;
  }
  const tgtOf = key => (S.targets[key] == null ? null : S.targets[key]);

  // an asset class target typed in the table: it becomes the custom mix (the rest stays Cash; the classes cannot add to more than 100)
  function setAssetTarget(b, raw) {
    const res = S.preview || {};
    const base = Object.assign({}, S.mix || res.mix_target || {});
    delete base.Cash;
    const others = Object.keys(base).reduce((t, k) => t + (k === b ? 0 : (base[k] || 0)), 0);
    base[b] = raw === '' ? 0 : Math.max(0, Math.min(parseFloat(raw) || 0, 100 - others));
    S.mix = base; S.preset = 'custom'; planDirty(); schedule(0);
  }

  // targets typed on the other rows are guides only: redraw the table, no server call
  function bindCmp() {
    const host = $('cmpTable');
    if (!host.dataset.fbound) { host.dataset.fbound = '1'; host.addEventListener('click', e => { if (e.target.closest('input,select,button')) return; const t = e.target.closest('[data-ftype]'); if (t) focusFilter(t.dataset.ftype, t.dataset.fval, e.ctrlKey || e.metaKey); }); }
    host.querySelectorAll('[data-tgt]').forEach(i => i.onchange = () => {
      const k = i.dataset.tgt;
      if (i.value === '') delete S.targets[k]; else S.targets[k] = Math.max(0, parseFloat(i.value) || 0);
      planDirty();
      host.innerHTML = compareTable(S.preview);
      bindCmp();
    });
    // the whole charts-and-grids panel: shown only when there is something to show; open/closed is remembered in this browser
    const panel = $('cmpPanel');
    if (panel) {
      panel.hidden = !host.innerHTML.trim();
      if (!panel.dataset.bound) {
        panel.dataset.bound = '1';
        try { if (localStorage.getItem('bld_panel') === 'closed') panel.open = false; } catch (x) { /* private window */ }
        panel.addEventListener('toggle', () => { try { localStorage.setItem('bld_panel', panel.open ? 'open' : 'closed'); } catch (x) { /* private window */ } });
      }
    }
    host.querySelectorAll('[data-sec-toggle]').forEach(c => c.onclick = e => {
      e.stopPropagation();
      const k = c.dataset.secToggle;
      S.collapsed[k] = !S.collapsed[k];
      try { localStorage.setItem('bld_collapsed', JSON.stringify(S.collapsed)); } catch (x) { /* private window */ }
      const box = c.closest('.bld-sec'); box.classList.toggle('collapsed', !!S.collapsed[k]);
      c.innerHTML = S.collapsed[k] ? '&#9656;' : '&#9662;'; c.title = (S.collapsed[k] ? 'Show' : 'Hide') + ' this section';
    });
    const pe = host.querySelector('#preset');
    if (pe) pe.onchange = () => { S.preset = pe.value; if (S.preset !== 'custom') S.mix = null; planDirty(); schedule(); };
    host.querySelectorAll('[data-tgt-asset]').forEach(i => i.onchange = () => setAssetTarget(i.dataset.tgtAsset, i.value));
    markActiveFilters();
  }

  // plain click on a comparison row/bar = only that filter; Ctrl+click = add it to the others; clicking the sole active one clears it
  function focusFilter(type, val, add) {
    if (add) return toggleFilter(type, val);
    const was = filterIsOn(type, val);
    const others = ['srcfSource', 'srcfClass', 'srcfSector', 'srcfIndustry', 'srcfFactor', 'srcfText'].some(id => $(id).value && !(filterSel[type] === id && was))
      || [...$('srcfQuad').querySelectorAll('input:checked')].some(c => !(type === 'quad' && was && c.value === val));
    ['srcfSource', 'srcfClass', 'srcfSector', 'srcfFactor', 'srcfText'].forEach(id => { $(id).value = ''; });
    fillIndustries('');
    $('srcfQuad').querySelectorAll('input').forEach(c => { c.checked = false; });
    if (was && !others) renderSourceNames(); else toggleFilter(type, val);
  }

  // 2026-10-29: rows and bars in the comparison are click-to-filter for the Names list; the active ones are highlighted
  function filterIsOn(type, val) {
    if (type === 'quad') return !!$('srcfQuad').querySelector(`input[value="${val}"]:checked`);
    const el = $(filterSel[type]);
    return !!el && el.value === val;
  }
  function markActiveFilters() {
    document.querySelectorAll('#cmpTable [data-ftype]').forEach(e => e.classList.toggle('on', filterIsOn(e.dataset.ftype, e.dataset.fval)));
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

  // One symbol table: a row for every symbol you picked OR the account holds, grouped by asset class, with
  // Your picks and My portfolio side by side. The % box on a picked row is where you set its share of the class.
  const GRP_COL = ['#1d4ed8', '#0d9488', '#b45309', '#9333ea', '#be185d', '#4d7c0f'];
  function symbolTable(res) {
    const holdBy = {};
    ((res.account && res.account.holdings) || []).forEach(h => { holdBy[h.sym] = h; });
    const posBy = {};
    (res.positions || []).forEach(p => { posBy[p.sym] = p; });
    const vsBy = {};
    ((res.vs_account && res.vs_account.rows) || []).forEach(r => { vsBy[r.sym] = r; });
    const acctVal = (res.account && res.account.value) || 0, amt = res.amount || 1, fin = res.mix_final || {};
    const syms = [...new Set(S.picks.map(p => p.sym).concat(Object.keys(holdBy)))];
    if (!syms.length) return '<div class="bld-muted" style="margin-top:8px">Nothing picked yet. Tick names in the list on the left.</div>';
    const rows = syms.map(sym => {
      const pk = picked(sym), pos = posBy[sym], h = holdBy[sym];
      const bucket = (pk && pk.bucket) || (pos && pos.bucket) || (h && h.bucket) || 'Unmapped';
      return { sym, pk, pos, h, bucket, hold: h ? h.value : 0, model: pos ? pos.value : 0, kept: !!(h && h.kept), trade: (vsBy[sym] || {}).trade || '' };
    });
    const dash = '<span class="bld-muted">-</span>';
    // 2026-10-28, user: two columns -- Equities on the right, every other asset class on the left
    const head = `<table class="bld-t bld-exp"><thead><tr><th>Symbol</th><th class="n">Picks</th><th class="n bld-tip" data-tip="Dollars you want to buy of this pick. Blank = not planned yet.">Buy $</th><th class="bld-tip" data-tip="Give two or more picks the same letter to buy any one of them (whichever is better when Actionable says Buy). One amount is shared by the group.">One of</th><th class="n">Portfolio</th><th class="n">Gap $</th><th>To match</th></tr></thead><tbody>`;
    const side = { left: '', right: '' };
    for (const b of BUCKETS.concat(['Unmapped'])) {
      const mine = rows.filter(r => r.bucket === b).sort((x, y) => Math.max(y.hold, y.model) - Math.max(x.hold, x.model));
      if (!mine.length) continue;
      let t = '';
      const mTot = mine.reduce((a, r) => a + r.model, 0), hTot = mine.reduce((a, r) => a + r.hold, 0);
      const sumPct = mine.reduce((a, r) => a + (r.pk && r.pk.pct != null ? r.pk.pct : 0), 0);
      t += `<tr class="sec"><td><span class="bld-sw" style="background:${bcol(b)}"></span>${esc(b)} ${copyBtn('list', mine.map(r => r.sym), 'Copy the ' + mine.length + ' ' + b + ' symbols')}</td><td class="n ${(sumPct > 100.5 || (fin[b] || 0) > 0 && mTot / amt * 100 > fin[b] + 0.5) ? 'bld-over' : ''}" title="${sumPct > 0 ? 'Your % boxes in this class add to ' + sumPct.toFixed(0) + '%' : ''}">${usd(mTot)} · ${pct(mTot / amt, 0)}${sumPct > 100.5 ? ' (' + sumPct.toFixed(0) + '% of class)' : ''}</td><td></td><td></td><td class="n">${usd(hTot)} · ${acctVal ? pct(hTot / acctVal, 0) : ''}</td><td class="n">${sgnUsd(mTot - hTot)}</td><td>${(fin[b] || 0) > 0 ? `<span class="bld-muted bld-tsum">target ${(fin[b]).toFixed(0)}%</span>` : ''}</td></tr>`;
      mine.forEach(r => {
        const ph = r.pos && (fin[b] || 0) > 0 ? (r.pos.value / amt * 100 / fin[b] * 100).toFixed(0) : 'equal';
        const pCell = r.pk
          ? `<input type="number" min="0" max="100" step="1" data-pct="${esc(r.sym)}" value="${r.pk.pct == null ? '' : r.pk.pct}" placeholder="${ph}" style="width:80px" title="% of ${esc(b)}"> % ` +
            `${r.pos ? '<b>' + usd(r.pos.value) + '</b>' : '<span class="bld-muted">not buyable</span>'} <button class="bld-btn sm alt" data-drop="${esc(r.sym)}" title="Remove from picks">×</button>`
          : dash;
        const hCell = r.h ? `${usd(r.hold)} <span class="bld-muted">${acctVal ? pct(r.hold / acctVal, 1) : ''}</span>${r.kept ? ' <span class="bld-badge sell">Kept</span>' : ''}` : dash;
        const gap = (r.pk || r.h) ? sgnUsd(r.model - r.hold) : '';
        const gl = r.pk && r.pk.grp ? r.pk.grp : '', gcol = gl ? GRP_COL[gl.charCodeAt(0) - 65] : '';
        const amtCells = r.pk
          ? `<td class="n"><input type="number" min="0" step="500" data-amt="${esc(r.sym)}" value="${r.pk.amt ? r.pk.amt : ''}" placeholder="$" style="width:74px" title="Dollars to buy"></td>` +
            `<td><select data-grp="${esc(r.sym)}" title="Give two or more picks the same letter to buy any one of them">${['', 'A', 'B', 'C', 'D', 'E', 'F'].map(g => `<option value="${g}"${(r.pk.grp || '') === g ? ' selected' : ''}>${g || '-'}</option>`).join('')}</select></td>`
          : '<td></td><td></td>';
        t += `<tr${(!r.pk && !r.kept) ? ' class="zero"' : ''}${gcol ? ` style="box-shadow:inset 3px 0 0 ${gcol}"` : ''}><td>${symHtml(r.sym)}${gl ? ` <span class="bld-badge" style="background:${gcol};color:#fff" title="Buy one of group ${gl}: you buy only one of these">${gl}</span>` : ''}</td><td class="n">${pCell}</td>${amtCells}<td class="n">${hCell}</td><td class="n">${gap}</td>` +
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
    if ($('picksCount')) $('picksCount').textContent = S.picks.length ? `${S.picks.length} picked` : '';
    const pcb = document.querySelector('#cmpPanel .bld-copy'); if (pcb) pcb.hidden = !S.picks.length;
    $('cmpTable').innerHTML = compareTable(res);
    bindCmp();
    $('symTable').innerHTML = symbolTable(res);
    $('symTable').querySelectorAll('[data-pct]').forEach(i => i.onchange = () => {
      const p = picked(i.dataset.pct);
      if (p) { p.pct = i.value === '' ? null : Math.max(0, parseFloat(i.value)); schedule(0); }
    });
    $('symTable').querySelectorAll('[data-drop]').forEach(btn => btn.onclick = () => { setPick(btn.dataset.drop, false); renderSourceNames(); planDirty(); schedule(0); });
    // 2026-11-14: a pick's dollars, and 'buy one of' groups (same letter = buy any one; the group shares one amount)
    $('symTable').querySelectorAll('[data-amt]').forEach(i => i.onchange = () => {
      const p = picked(i.dataset.amt); if (!p) return;
      p.amt = i.value === '' ? null : Math.max(0, parseFloat(i.value) || 0);
      if (p.grp) S.picks.forEach(q => { if (q.grp === p.grp) q.amt = p.amt; });
      planDirty(); renderPicks(res);
    });
    $('symTable').querySelectorAll('[data-grp]').forEach(sel => sel.onchange = () => {
      const p = picked(sel.dataset.grp); if (!p) return;
      p.grp = sel.value;
      if (p.grp) { const o = S.picks.find(q => q !== p && q.grp === p.grp && q.amt); if (o) p.amt = o.amt; else if (p.amt) S.picks.forEach(q => { if (q.grp === p.grp) q.amt = p.amt; }); }
      planDirty(); renderPicks(res);
    });
  }

  // Buy $ = what the pick still needs to reach the plan: the dollars the plan gives it minus what the account holds
  // (rounded to $100; nothing when it is already at or over the plan; a 'buy one of' group shares the biggest gap).
  function fillBuyGaps(res) {
    const posBy = {}, holdBy = {};
    (res.positions || []).forEach(p => { posBy[p.sym] = p.value || 0; });
    ((res.account && res.account.holdings) || []).forEach(h => { holdBy[h.sym] = h.value || 0; });
    S.picks.forEach(p => { if (p.amt) return; const gap = (posBy[p.sym] || 0) - (holdBy[p.sym] || 0); p.amt = gap >= 500 ? Math.round(gap / 100) * 100 : null; });   // never overwrite an amount you typed
    S.picks.forEach(p => { if (p.grp) { const m = Math.max(...S.picks.filter(q => q.grp === p.grp).map(q => q.amt || 0)); S.picks.filter(q => q.grp === p.grp).forEach(q => { q.amt = m || null; }); } });
    planDirty(); renderPicks(res);
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
      if (S.fillGapNext) { S.fillGapNext = false; fillBuyGaps(res); }
      if (S.matchNext) { S.matchNext = false; startFromHoldings(true); }   // auto-picked held names take the account's own weights
    } catch (e) {
      if (seq !== S.reqSeq) return;
      $('cmpTable').innerHTML = `<span class="bld-warn">Could not build: ${esc(e.message)}</span>`;
    }
  }

  // 'Start from my holdings' (and the first view of an account with no saved plan): the sector / style / beta limits become what the account holds now.
  // Opening an account with no saved plan does this too (limits = holdings, bars green); clear a box to leave that line without a limit.
  function seedTargets(res) {
    const H = (res.exposure || {}).held || {};
    if (!(H.total > 0)) return;
    const t = {}, r0 = v => Math.round(v * 100) / 100;   // 2 decimals: a fill from holdings must land on a gap of 0, not a rounded one
    const put = (k, v) => { if (v != null && v >= 0.005) t[k] = r0(v); };
    put('lowbeta', H.lowbeta); put('highbeta', H.highbeta); put('midbeta', H.midbeta); put('nobeta', H.nobeta);
    ['Q1', 'Q2', 'Q3', 'Q4'].forEach(q => put('quad:' + q, ((H.quad || {})[q] || {}).bull));
    Object.keys(H.sector || {}).filter(isEquitySector).forEach(s => put('sector:' + s, H.sector[s]));   // equity sectors only: Fixed Income, Gold, Currency, 'Equities' (no sector) are not sector limits
    Object.keys(H.style || {}).forEach(s => put('style:' + s, H.style[s]));
    put('style:none', H.nostyle);
    put('sector:Equities', (H.sector || {}).Equities);   // 'No sector' guide row (not a saved limit)
    S.targets = t;
  }
  // 'No sector' is a guide only: a saved plan does not hold it, so after a plan loads it is filled from what the
  // account holds (once per account), without touching the limits the plan did save.
  function fillGuides(res) {
    const H = (res.exposure || {}).held || {};
    if (!(H.total > 0) || !(Object.keys(S.targets).length || (S.legacyKeys || []).length)) return;   // nothing typed or loaded yet: the first fill from holdings covers these rows
    S.guideFor = S.acct;
    const put = (k, v) => { if (S.targets[k] == null && v != null && v >= 0.005) S.targets[k] = Math.round(v * 100) / 100; };
    // limit rows added after this plan was saved (the plan has no such key at all, so it never said "no limit"): fill them from holdings once
    const lg = S.legacyKeys || [];
    if (lg.includes('midbeta')) put('midbeta', H.midbeta);
    if (lg.includes('nobeta')) put('nobeta', H.nobeta);
    if (lg.includes('style:none')) put('style:none', H.nostyle);
    ['Q1', 'Q2', 'Q3', 'Q4'].forEach(q => { if (lg.includes('quad:' + q)) put('quad:' + q, ((H.quad || {})[q] || {}).bull); });
    S.legacyKeys = [];
    put('sector:Equities', (H.sector || {}).Equities);   // only 'No sector' is still a guide; Quad boxes are saved limits now (a blank one stays blank)
  }

  function render(res) {
    problems(res.problems);
    if (S.guideFor !== S.acct) fillGuides(res);
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
    $('acctSnap').textContent = a.snap_date ? 'Positions file: ' + a.snap_date + (a.positions_stale ? ' (older than 3 trading days)' : '') : '';
    if ($('amount') && document.activeElement !== $('amount')) $('amount').value = S.amount || Math.round(a.value || 0);
  }

  // ---------------------------------------------------------------- step 2: mix
  function renderMix(res) {
    const cur = res.mix_current || {}, tgt = res.mix_target || {}, fin = res.mix_final || {};
    if (S.preset === 'custom' && !S.mix) S.mix = Object.assign({}, tgt);
  }

  // ---------------------------------------------------------------- plan per account (2026-11-14, DESIGN_SPEC_16)
  // The Target % typed in the grids are this account's plan. Save plan keeps them as the plan the To do
  // list and warnings use (class % must add to 100, Cash is the rest). Nothing here trades or changes the Final Call.
  const PLAN_CLASSES = ['Equities', 'Fixed Income', 'Gold', 'Commodities', 'Crypto', 'Currency', 'Cash'];
  const PL = { name: null, checked: null, versions: [], dirty: false, activeAt: null };
  const planSend = (u, b, m) => api(u, { method: m || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) });
  function planNote(html, warn) {
    const el = $('planMsg'); if (!el) return;
    el.hidden = !html; el.innerHTML = html || ''; el.style.color = warn ? '#b45309' : '';
  }
  function planPill() {
    const el = $('planPill'); if (!el) return;
    const act = PL.checked ? 'Active plan: ' + PL.checked + (PL.activeAt ? ' (since ' + PL.activeAt.slice(5, 10) + ')' : '') : 'No active plan';
    const view = PL.name && PL.name !== PL.checked ? ' · viewing "' + PL.name + '"' : '';
    el.textContent = act + view + (PL.dirty ? ' · unsaved' : '');
  }
  function planDirty() { PL.dirty = true; planPill(); }
  function planFromState() {
    const res = S.preview || {}, base = Object.assign({}, S.mix || res.mix_target || {});
    const cls = {}; let sum = 0;
    PLAN_CLASSES.filter(c => c !== 'Cash').forEach(c => { cls[c] = +(base[c] || 0); sum += cls[c]; });
    cls.Cash = +Math.max(0, 100 - sum).toFixed(2);
    const plan = { cls, beta: { low: tgtOf('lowbeta'), high: tgtOf('highbeta'), mid: tgtOf('midbeta'), none: tgtOf('nobeta') }, sector: {}, style: {}, quad: { Q1: tgtOf('quad:Q1'), Q2: tgtOf('quad:Q2'), Q3: tgtOf('quad:Q3'), Q4: tgtOf('quad:Q4') }, cash_keep: 1000,
      picks: S.picks.map(p => ({ sym: p.sym, bucket: p.bucket, pct: p.pct, amt: p.amt || 0, grp: p.grp || '' })), sources: S.sources.slice() };
    Object.keys(S.targets).forEach(k => {
      if (k.startsWith('sector:')) { if (isEquitySector(k.slice(7))) plan.sector[k.slice(7)] = S.targets[k]; }
      else if (k.startsWith('style:')) plan.style[k.slice(6)] = S.targets[k];
    });
    if (!('none' in plan.style)) plan.style.none = null;   // always present, so a blank 'No style tag' box is remembered as 'no limit'
    return plan;
  }
  function planApply(p) {
    const mix = {};
    PLAN_CLASSES.filter(c => c !== 'Cash').forEach(c => { if ((p.cls || {})[c] > 0) mix[c] = p.cls[c]; });
    S.mix = mix; S.preset = 'custom';
    S.targets = {}; S.seeded = S.acct;   // saved limits win: holdings must never re-seed (overwrite) them
    S.legacyKeys = []; if (!p.beta || !('mid' in p.beta)) S.legacyKeys.push('midbeta', 'nobeta'); if (!p.style || !('none' in p.style)) S.legacyKeys.push('style:none');
    if (!p.quad) ['Q1', 'Q2', 'Q3', 'Q4'].forEach(q => S.legacyKeys.push('quad:' + q)); S.guideFor = null;
    if (p.beta && p.beta.low != null) S.targets.lowbeta = p.beta.low;
    if (p.beta && p.beta.high != null) S.targets.highbeta = p.beta.high;
    if (p.beta && p.beta.mid != null) S.targets.midbeta = p.beta.mid;
    if (p.beta && p.beta.none != null) S.targets.nobeta = p.beta.none;
    Object.keys(p.quad || {}).forEach(k => { if (p.quad[k] != null) S.targets['quad:' + k] = p.quad[k]; });
    Object.keys(p.sector || {}).forEach(k => { if (p.sector[k] != null) S.targets['sector:' + k] = p.sector[k]; });
    Object.keys(p.style || {}).forEach(k => { if (p.style[k] != null) S.targets['style:' + k] = p.style[k]; });
    if (Array.isArray(p.sources) && p.sources.length) { S.sources = p.sources.slice(); renderSources(); loadSourceNames(); }
    if (Array.isArray(p.picks)) { S.picks = p.picks.map(x => ({ sym: x.sym, bucket: x.bucket, pct: x.pct == null ? null : x.pct, amt: x.amt || null, grp: x.grp || '' })); renderSourceNames(); }
    schedule(0);
  }
  // The account's saved versions go in the Plan box; the checked one (tick) opens first, else the newest.
  function planVersionsFill(r) {
    PL.versions = r.versions || []; PL.checked = r.checked || null;
    if ($('planVer')) $('planVer').innerHTML = PL.versions.length ? PL.versions.map(v => `<option value="${esc(v.name)}">${v.name === PL.checked ? '&#10003; ' : ''}${esc(v.name)}</option>`).join('') : '<option value="">(none saved)</option>';
  }
  async function planLoad(keepName) {
    if (!S.acct || S.acct === 'ALL' || !$('planPill')) { PL.name = null; PL.checked = null; PL.dirty = false; planPill(); return; }
    planNote('');
    try {
      const r = await api('/api/builder/plan/versions?account=' + encodeURIComponent(S.acct));
      PL.name = keepName || r.checked || (r.versions[0] && r.versions[0].name) || null;
      planVersionsFill(r);
      PL.dirty = false;
      if (PL.name) {
        const v = await api('/api/builder/plan/version?account=' + encodeURIComponent(S.acct) + '&name=' + encodeURIComponent(PL.name));
        planApply(v.plan);
        const st = await api('/api/builder/plan/saved?account=' + encodeURIComponent(S.acct));
        PL.activeAt = st.active_at;
      }
    } catch (e) { PL.name = null; PL.checked = null; }
    planPill();
    todoLoad();
  }
  async function planAfterSave(name, activated) {
    PL.name = name; PL.dirty = false;
    planVersionsFill(await api('/api/builder/plan/versions?account=' + encodeURIComponent(S.acct)));
    if (activated) PL.activeAt = new Date().toISOString();
    planPill(); todoLoad();
  }
  // Names look like "Plan 11-14-2026" (the screen's date)
  function defaultPlanName() {
    const d = (S.date || new Date().toISOString().slice(0, 10)).split('-');
    return 'Plan ' + d[1] + '-' + d[2] + '-' + d[0];
  }
  const planNeedAcct = () => { if (!S.acct || S.acct === 'ALL') { planNote('Choose one account first. A plan belongs to one account.', true); return true; } return false; };
  // Keep the screen as plan `name`. Saving the ACTIVE plan also refreshes what the To do list reads; any other plan is only kept.
  async function planStore(name) {
    if (name === PL.checked || !PL.checked) {   // the active plan, or the account's first plan (nothing active yet): saving also makes it active
      const r = await planSend('/api/builder/plan/save-check', { account: S.acct, name, plan: planFromState(), date: S.date });
      await planAfterSave(r.name, r.checking);
      return r;
    }
    const r = await planSend('/api/builder/plan/save-as', { account: S.acct, name, plan: planFromState() });
    await planAfterSave(r.name, false);
    return r;
  }
  async function planSave() {
    if (planNeedAcct()) return;
    const name = PL.name || defaultPlanName();
    const r = await planStore(name);
    if (r && r.checking === false && (r.problems || []).length) { planNote('<b>Saved "' + esc(name) + '", but it cannot be used by the To do list yet.</b> ' + r.problems.map(esc).join(' '), true); return; }
    planNote('<b>Saved "' + esc(name) + '".</b>' + (name === PL.checked ? ' It is the active plan, so the To do list uses it.' : ''));
  }
  async function planSaveAs() {
    if (planNeedAcct()) return;
    const name = (window.prompt('Save this plan as', defaultPlanName()) || '').trim();
    if (!name) return;
    if ((PL.versions || []).some(v => v.name === name) && !window.confirm('A saved plan named "' + name + '" already exists. Replace it?')) return;
    await planStore(name);
    planNote('<b>Saved as "' + esc(name) + '".</b> Press Activate to make it the active plan.');
  }
  async function planActivate() {
    if (planNeedAcct()) return;
    const name = PL.name || defaultPlanName();
    if (PL.dirty && !window.confirm('Save your changes to "' + name + '" and make it the active plan?')) return;
    const r = await planSend('/api/builder/plan/save-check', { account: S.acct, name, plan: planFromState(), date: S.date });
    await planAfterSave(r.name, r.checking);
    if (!r.checking) { planNote('<b>Saved, but it cannot be activated yet.</b> ' + (r.problems || []).map(esc).join(' '), true); return; }
    planNote('<b>"' + esc(r.name) + '" is now the active plan.</b> The To do list uses it.');
  }
  async function planDelete() {
    if (!S.acct || S.acct === 'ALL') return;
    if (!PL.name) { S.picks = []; S.targets = {}; S.mix = null; S.preset = 'current'; PL.dirty = false; planPill(); renderSourceNames(); schedule(0); return; }
    if (!window.confirm('Delete the saved plan "' + PL.name + '" for ' + S.acct + '?' + (PL.name === PL.checked ? ' It is the active plan, so the To do list and its planned buys stop. ' : ' ') + 'Your My stocks list is kept.')) return;
    try {
      await planSend('/api/builder/plan?account=' + encodeURIComponent(S.acct) + '&name=' + encodeURIComponent(PL.name), {}, 'DELETE');
      S.picks = []; S.targets = {}; S.seeded = null; S.mix = null; S.preset = 'current'; PL.name = null;
      await planLoad(); renderSourceNames(); schedule(0);
      planNote('Plan deleted for ' + esc(S.acct) + '.');
      } catch (e) { planNote(esc(e.message), true); }
  }
  // ---------------------------------------------------------------- To do (2026-11-14): from the ACTIVE plan
  // Sells = holdings in classes above their plan % (plan 0% = sell all); a ticked sell adds EXPECTED cash to this account only.
  // Buys = the picks with an amount (Save plan writes them), counted when Actionable says Buy and the pick is ticked.
  // Money blocks or cuts a buy (account cash, cash floor, the plan's Cash %); the % lines only warn. Nothing trades.
  const TD = { data: null, seq: 0 };
  const tdPill = (cls, t) => `<span class="td-p ${cls}">${esc(t)}</span>`;
  const tdCall = c => c ? (ACT_LABEL[c] || c) : 'No call';
  function tdMsg(t, warn) { $('tdMsg').textContent = t; $('tdMsg').className = 'td-msg' + (warn ? ' w' : ''); }
  async function todoLoad() {
    if (!$('todoCard')) return;
    const seq = ++TD.seq;
    if (!S.acct || S.acct === 'ALL') { $('tdEmpty').hidden = false; $('tdBody').hidden = true; $('tdSub').textContent = ''; return; }
    $('tdBody').classList.add('td-dim');
    try {
      const t = await api(withDate('/api/builder/todo?account=' + encodeURIComponent(S.acct)));
      if (seq !== TD.seq) return;
      TD.data = t; todoRender();
    } catch (e) { if (seq === TD.seq) tdMsg('Could not load the to-do list: ' + e.message, true); }
    $('tdBody').classList.remove('td-dim');
  }
  function todoRender() {
    const t = TD.data;
    $('tdEmpty').hidden = t.state !== 'none'; $('tdBody').hidden = t.state === 'none';
    $('tdSub').textContent = t.state === 'none' ? '' : ' · ' + S.acct + ' · active plan since ' + String(t.active_at || '').slice(5, 10) + (PL.dirty ? ' · your unsaved changes are not in this list' : '');
    if (t.state === 'none') return;

    // sells
    $('tdSells').innerHTML = (t.sells || []).length ? t.sells.map(s => `<div style="margin-bottom:8px"><div class="bld-line"><b>${esc(s.cls)}</b>` +
      tdPill('sell', s.all ? 'Plan 0%: sell all ' + usd(s.held) : 'Over plan by about ' + usd(s.need)) +
      `<span class="bld-muted" style="margin-left:auto">Ticked ${usd(s.ticked_total)} of ${usd(s.need)}</span></div>` +
      '<table class="bld-t"><thead><tr><th></th><th>Holding</th><th class="n">Value</th><th>Actionable</th></tr></thead><tbody>' +
      s.holdings.map(h => `<tr><td><input type="checkbox" data-tdsell="${esc(h.sym)}" data-pid="${h.pick_id || ''}" data-val="${h.value}"${h.ticked ? ' checked' : ''} aria-label="Sell ${esc(h.sym)}"></td><td><b>${esc(h.sym)}</b></td><td class="n">${usd(h.value)}</td><td>${tdPill(h.side === 'sell' ? 'sell' : h.side === 'buy' ? 'buy' : '', tdCall(h.call))}</td></tr>`).join('') +
      '</tbody></table></div>').join('') : '<div class="bld-muted">Nothing is over its plan. No sells needed.</div>';
    $('tdSells').querySelectorAll('[data-tdsell]').forEach(e => e.onchange = async () => {
      try {
        if (e.checked) await planSend('/api/builder/pick', { account: S.acct, side: 'SELL', members: [e.dataset.tdsell], amount: Number(e.dataset.val), ticked: true });
        else if (e.dataset.pid) await planSend('/api/builder/pick/' + e.dataset.pid, {}, 'DELETE');
        await todoLoad();
      } catch (x) { tdMsg(x.message, true); }
    });

    // buys
    const RES = { OK: ['ok', 'OK'], OVER_PLAN: ['warn', 'Over plan'], SHRUNK: ['warn', 'Cut'], BLOCKED: ['bad', 'Blocked'], WAITING: ['', 'Waiting'], READY: ['buy', 'Has a Buy'] };
    let b = '<thead><tr><th></th><th>Pick</th><th>Actionable today</th><th class="n">Amount</th><th class="n">Allowed</th><th>Result</th></tr></thead><tbody>';
    (t.buys || []).forEach(x => {
      const names = x.members.map(m => `<b>${esc(m)}</b>`).join(x.members.length > 1 ? ' <span class="bld-muted">or</span> ' : '');
      const calls = x.members.map(m => esc(m) + ': ' + esc(tdCall(x.calls[m]))).join(' · ');
      const r = RES[x.result] || ['', x.result];
      b += `<tr><td><input type="checkbox" data-tdbuy="${x.id}"${x.ticked ? ' checked' : ''}${x.result === 'WAITING' ? ' disabled' : ''} aria-label="Count this pick"></td><td>${names}<div class="bld-muted">${calls}</div></td><td>` +
        (x.buy_member ? tdPill('buy', 'Buy: ' + x.buy_member) : tdPill('', 'None yet')) + `</td><td class="n"><input type="number" min="0" step="500" data-tdamt="${x.id}" value="${x.amount || ''}" placeholder="$0" style="width:78px"></td><td class="n">${x.allowed ? usd(x.allowed) : '-'}</td><td>${tdPill(r[0], r[1])} <span class="bld-muted">${esc(x.why)}</span></td></tr>`;
    });
    if (!(t.buys || []).length) b += '<tr><td colspan="6" class="bld-muted">No planned buys yet. Type a Buy $ on a pick, then press Save plan.</td></tr>';
    $('tdBuys').innerHTML = b + '</tbody>';
    const patch = async (id, body) => { try { await planSend('/api/builder/pick/' + id, body, 'PATCH'); await todoLoad(); } catch (x) { tdMsg(x.message, true); } };
    $('tdBuys').querySelectorAll('[data-tdbuy]').forEach(e => e.onchange = () => patch(e.dataset.tdbuy, { ticked: e.checked }));
    $('tdBuys').querySelectorAll('[data-tdamt]').forEach(e => e.onchange = () => patch(e.dataset.tdamt, { amount: Math.max(0, Number(e.value) || 0) }));

    // what is left
    const bar = (now, used, plan, hard) => {
      const after = now + used, w = plan > 0 ? Math.min(after / plan * 100, 100) : (after > 0 ? 100 : 0), nw = plan > 0 ? Math.min(now / plan * 100, 100) : (now > 0 ? 100 : 0);
      return `<div class="td-bar"><i class="${hard ? 'h' : after > plan + 1 ? 'o' : ''}" style="width:${w}%"></i><b style="width:${nw}%"></b></div>`;
    };
    let L = '';
    // a line within the on-plan band (the smaller of $500 and 0.5% of the account) counts as matched: "$0 left"
    // (holdings-based targets are kept to 2 decimals, so a few dollars of rounding must not read as "over")
    const tol = Math.min(500, 0.005 * (t.value || 0)) || 500;
    const lf = v => (Math.abs(v) <= tol ? 0 : v);
    (t.lines || []).filter(r => r.kind === 'cls' && r.key !== 'Cash' && (r.plan > 0 || r.now > 500)).forEach(r => {
      const left = lf(r.left), over = left < -1;
      L += `<div><div class="bld-line"><b>${esc(r.key)}</b><span style="margin-left:auto;color:${over ? '#b45309' : '#16a34a'}">${over ? 'over by ' + usd(-left) + ' (warning)' : usd(left) + ' left'}</span></div>${bar(r.now, r.used, r.plan, false)}<div class="bld-muted">Plan ${r.plan_pct}% = ${usd(r.plan)}</div></div>`;
    });
    const hard = t.cash_left <= 0;
    L += `<div><div class="bld-line"><b>Cash you can spend</b><span style="margin-left:auto;color:${hard ? '#9e3636' : '#16a34a'}">${usd(t.cash_left)} left</span></div>` +
      `<div class="td-bar"><i class="${hard ? 'h' : ''}" style="width:${t.cash_to_spend > 0 ? Math.min((t.cash_to_spend - t.cash_left) / t.cash_to_spend * 100, 100) : 100}%"></i></div>` +
      `<div class="bld-muted">Cash ${usd(t.cash)}${t.sell_cash ? ' + ' + usd(t.sell_cash) + ' expected from sells (not in your broker file yet)' : ''}. Keeps the plan's Cash % and ${usd(t.cash_keep)}. A money limit: it blocks.</div></div>`;
    // two columns: Asset class (with Cash) on the left, Sectors on the right; the other optional lines (style, beta, Quad) stay below as before
    const optRow = r => { const left = lf(r.left), over = left < -1; return `<div><div class="bld-line"><span>${esc(r.label)}</span><span style="margin-left:auto;color:${over ? '#b45309' : '#16a34a'}">${over ? 'over by ' + usd(-left) : usd(left) + ' left'}</span></div>${bar(r.now, r.used, r.plan, false)}</div>`; };
    const sectors = (t.lines || []).filter(r => r.kind === 'sector');
    const opt = (t.lines || []).filter(r => r.kind !== 'cls' && r.kind !== 'sector');
    const col = h => h ? `<div style="display:flex;flex-direction:column;gap:8px">${h}</div>` : '<div></div>';
    // optional lines: each group (Style, Quad, Beta) stays together and the groups are split into two columns as evenly as possible
    const grp = []; opt.forEach(r => { const g = grp.length && grp[grp.length - 1].kind === r.kind ? grp[grp.length - 1] : (grp.push({ kind: r.kind, rows: [] }), grp[grp.length - 1]); g.rows.push(r); });
    let cut1 = 0, best = 1e9;
    for (let k = 0; k <= grp.length; k++) { const a = grp.slice(0, k).reduce((n, g) => n + g.rows.length, 0), b = opt.length - a; if (Math.abs(a - b) < best) { best = Math.abs(a - b); cut1 = k; } }
    const colOf = gs => `<div style="display:flex;flex-direction:column;gap:8px;min-width:0">${gs.map(g => g.rows.map(optRow).join('')).join('')}</div>`;
    $('tdLeft').innerHTML = col(L) + col(sectors.map(optRow).join('')) +
      (opt.length ? '<div style="grid-column:1/-1"><div class="bld-muted" style="margin-bottom:8px"><b>Optional lines (warn only)</b></div><div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px;align-items:start">' + colOf(grp.slice(0, cut1)) + colOf(grp.slice(cut1)) + '</div></div>' : '');
    const cut = (t.buys || []).some(x => x.result === 'SHRUNK' || x.result === 'BLOCKED');
    const overNote = (t.notes || []).some(n => /over its plan/.test(n));
    const parts = ['Buys counted: ' + usd(t.bought) + '.'];
    if (t.sell_cash) parts.push('Sells ticked: ' + usd(t.sell_cash) + ' (expected).');
    parts.push(cut ? 'A cash limit cut a buy. Tick more sells or lower an amount.' : overNote ? 'Some lines are over plan. You can still place these.' : t.bought ? 'Everything is inside the plan.' : 'Nothing counted yet.');
    tdMsg(parts.join(' '), cut || overNote);
    $('tdNotes').innerHTML = (t.notes || []).map(n => `<li>${esc(n)}</li>`).join('');
  }

  async function myAdd() {
    const sym = ($('myAddSym').value || '').trim().toUpperCase();
    if (!sym) return;
    try {
      await planSend(withDate('/api/builder/my-stocks/' + encodeURIComponent(sym)), {}, 'PUT');
      $('myAddSym').value = ''; $('myMsg').textContent = sym + ' added to My stocks.';
      if (!S.sources.includes('MINE')) S.sources.push('MINE');
      renderSources(); loadSourceNames();
    } catch (e) { $('myMsg').textContent = e.message; }
  }
  function planInit() {
    if ($('myAdd')) $('myAdd').onclick = myAdd;
    if ($('tdRefresh')) $('tdRefresh').onclick = todoLoad;
    if (!$('planPill')) return;
    $('planSave').onclick = () => planSave().catch(e => planNote(esc(e.message), true));
    $('planDelete').onclick = planDelete;
    $('planSaveAs').onclick = () => planSaveAs().catch(e => planNote(esc(e.message), true));
    $('planActivate').onclick = () => planActivate().catch(e => planNote(esc(e.message), true));
    $('planVer').onchange = () => {
      if (PL.dirty && !window.confirm('You have unsaved changes. Open another saved plan and lose them?')) { $('planVer').value = PL.name || ''; return; }
      if ($('planVer').value) planLoad($('planVer').value);
    };
    if (!PL.dirty) planLoad();   // date change / Refresh must not replace unsaved edits with the saved plan
  }

  document.addEventListener('DOMContentLoaded', init);
})();
