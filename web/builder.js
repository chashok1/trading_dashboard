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
    ['lowbeta', 'Low beta'], ['highbeta', 'High beta'], ['nobeta', 'No beta known'], ['nostyle', 'No style tag'], ['uptrend', 'Above trend'], ['mom', 'Positive momentum']];
  const FACTOR_TIP = 'Defensive = Defensives, Low Beta or Dividend tag. Offensive = Cyclical, High Beta or Small Caps. Value = Value. Growth = Secular. Mid = Mid Caps. Low beta = measured beta 0.8 or under. High beta = over 1.2.';
  const STYLE_TAGS = { defensive: ['defensives', 'low beta', 'dividend'], offensive: ['cyclical', 'high beta', 'small caps'], value: ['value'], growth: ['secular'], mid: ['mid caps'] };
  const hasStyle = (n, k) => (n.styles || []).some(t => STYLE_TAGS[k].includes(String(t).toLowerCase()));
  function factorOk(n, k) {
    if (!k) return true;
    if (STYLE_TAGS[k]) return hasStyle(n, k);
    if (k === 'nobeta') return n.beta == null;
    if (k === 'nostyle') return !(n.styles || []).some(t => Object.values(STYLE_TAGS).some(g => g.includes(String(t).toLowerCase())));
    if (k === 'lowbeta') return n.beta != null && n.beta <= 0.8;
    if (k === 'highbeta') return n.beta != null && n.beta > 1.2;
    if (k === 'uptrend') return n.above_trend === true;
    if (k === 'mom') return n.mom != null && n.mom > 0;
    return true;
  }

  const S = {
    date: null, accounts: [], acct: '', horizon: '3M', preset: 'current', seeded: null, mix: null, amount: null, useDial: false,
    srcNames: [], outlooks: {}, nameCache: {}, picks: [], assign: {}, targets: {}, gapIdx: null, namesSeq: 0, sources: [], srcList: [], warn: {}, presets: {}, preview: null,
    reqSeq: 0, timer: null, detail: null, chart: null, sell: {}, sellHold: {}, myMax: {}, pickBase: {}, flags: {},
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

  // 2026-11-17: a pick's Buy $ is filled for you (its Stk Room $ share, first come first served, Buy-call stocks first; a Buy call is not needed, this is planning) until you type your own
  const autoAmt = p => !p.amtUser && !p.grp && (!p.amt || p.autoAmt);
  function buildReq() {
    // hand-picked build: the server uses exactly these names, each in its asset class, with the % typed (null = share equally)
    const req = { account: S.acct || 'ALL', horizon: S.horizon, preset: S.preset, use_risk_dial: S.useDial, warnings: S.warn,
      manual: true, picks: S.picks.map(p => ({ sym: p.sym, bucket: p.bucket, pct: p.pct, amt: p.amt || 0, grp: p.grp || '' })) };
    if (S.preset === 'custom') req.mix = S.mix;
    if (S.amount) req.amount = S.amount;
    if (S.acct && S.acct !== 'ALL') {            // the plan as typed on screen: the server works out Stk Room $ per stock from it (warn only)
      const pl = planFromState();
      pl.picks = S.picks.map(p => ({ sym: p.sym, bucket: p.bucket, pct: p.pct, amt: autoAmt(p) ? 0 : (p.amt || 0), grp: p.grp || '' }));
      req.plan = pl;
      // every name in the names list, so each can show whether there is room to pick it (Can pick column)
      req.names = S.srcNames.slice(0, 800).map(n => ({ sym: n.sym, bucket: bucketOf(n), sector: n.sector, beta: n.beta, styles: n.styles, quad: n.quad }));
    }
    return req;
  }

  // ---------------------------------------------------------------- init
  // Every panel gets a small button (top right) that collapses it to its title. Remembered in this browser only.
  function makePanelsCollapsible() {
    const panels = [['.bld-acct', 'Account and plan', 'acct'], ['#srcNames', 'Names', 'names'],
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
      // 2026-11-17, user: every panel's collapse button sits at the right edge   // 2026-11-17, user: these two panels carry the button before their label (Account / Symbol)
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
      S.acct = $('acctSel').value; S.amount = null; S.sell = {}; S.sellHold = {}; S.myMax = {}; S.pickBase = {}; S.targets = {}; S.seeded = null; S.guideFor = null; S.preset = 'current'; S.mix = null;
      S.picks = []; S.fillGapNext = false; S.matchNext = false; PL.dirty = false;
      loadSourceNames(); planLoad(); schedule(0);
    };
    try {
      const so = await api('/api/builder/sources');
      S.srcList = so.sources || [];
      S.srcImported = so.imported || {};
      if (S.srcList.some(x => x.code === 'HELD')) S.sources = ['HELD'];
      renderSources();
    } catch (e) { problems(['Could not load source lists: ' + e.message]); }

    // editable amount (defaults to the account value)
    const lab = document.createElement('label');
    lab.className = 'bld-muted';
    lab.style.cssText = 'justify-content:flex-start;gap:4px';   // 2026-11-17, user: the value sits right after the colon, one space, not pushed to the right edge
    lab.innerHTML = 'Acct Value: <b id="amount" style="color:var(--text-1)" title="The account value the plan is worked out on."></b>';
    $('acctType').after(lab);
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
    watchAmounts();
    await loadFlags();
    try { S.bands = (await api('/api/builder/class-bands')).bands || {}; } catch (e) { S.bands = S.bands || {}; }
    if (!S.icWired) {
      S.icWired = true;      // reloadAll runs again on Refresh: wire the click once
      document.addEventListener('click', e => {
        const b = e.target.closest('[data-ic]');
        if (!b || !window.BldNotes) return;
        e.preventDefault();
        window.BldNotes.open(b.dataset.ic, b, S.flags[b.dataset.ic], refreshFlags, b.dataset.k);
      });
    }
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
    $('srcBox').innerHTML = S.srcList.map(x => `<label><input type="checkbox" data-src="${esc(x.code)}" ${S.sources.includes(x.code) ? 'checked' : ''}> ${esc(x.code)} <span class="bld-muted">${esc(x.label)}</span>${S.srcImported && S.srcImported[x.code] ? ` <span class="bld-muted" title="Last imported ${esc(S.srcImported[x.code])}">${esc(S.srcImported[x.code].slice(5, 7) + '/' + S.srcImported[x.code].slice(8, 10))}</span>` : ''}</label>`).join('');
    $('srcBox').querySelectorAll('[data-src]').forEach(c => c.onchange = () => {
      S.sources = [...$('srcBox').querySelectorAll('[data-src]')].filter(i => i.checked).map(i => i.dataset.src);
      loadSourceNames();
    });
    ['srcfSource', 'srcfClass', 'srcfFactor', 'srcfIndustry', 'srcfAction'].forEach(id => $(id).onchange = renderSourceNames);
    $('srcfSector').onchange = () => { fillIndustries(''); renderSourceNames(); };
    $('clearFilters').onclick = () => {
      ['srcfSource', 'srcfClass', 'srcfSector', 'srcfFactor', 'srcfAction'].forEach(id => { $(id).value = ''; });
      fillIndustries('');
      $('srcfText').value = ''; S.gapIdx = null; $('srcNamesHint').textContent = '';
      setFilters({});
    };
    $('srcfQuad').querySelectorAll('input').forEach(c => c.onchange = renderSourceNames);
    $('srcfFactor').innerHTML = FACTORS.map(f => `<option value="${f[0]}">${esc(f[1])}</option>`).join('');
    $('srcfFactor').title = FACTOR_TIP;
    $('srcfText').oninput = renderSourceNames;
    $('srcfHidePicked').onchange = renderSourceNames;
    $('srcfScope').onchange = renderSourceNames;
    $('selShown').onclick = selectShown;
    $('clearTargets').onclick = e => {          // 2026-11-17, user: Clear targets is a button on the charts-and-grids panel (left)
      e.preventDefault(); e.stopPropagation();   // it sits in the panel's heading, which opens and closes the panel
      clearTargetsIn('all');
    };
    $('srcNamesRows').addEventListener('click', e => { const t = e.target.closest('[data-ftype]'); if (t) toggleFilter(t.dataset.ftype, t.dataset.fval); });
    // Start from my holdings (one direct function, no hidden flags). A click ticks every stock the account holds (your other
    // picks stay), sets each one's share of its class, sets the asset class % to the current mix, fills the sector / style /
    // beta limits and the Buy $ gaps, and says what it did. The automatic pass on opening an account (auto = true) only ticks
    // and matches the held stocks: it never fills the limits or any Buy $.
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
      S.picks.forEach(p => { if (hold[p.sym] > 0) p.pct = null; });      // held stocks keep what they hold: no % share
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
    $('srcNamesRows').innerHTML = '<tr><td colspan="10" class="bld-muted">Loading...</td></tr>';
    try {
      const r = await api(withDate('/api/builder/source-names?sources=' + encodeURIComponent(S.sources.join(',')) + '&account=' + encodeURIComponent(S.acct || '')));
      if (seq !== S.namesSeq) return;
      S.srcNames = r.names || [];
      S.srcNames.forEach(n => { S.nameCache[n.sym] = n; });
      if (S.acct && S.acct !== 'ALL') schedule(0);        // Can pick column needs room for these names
    } catch (e) {
      if (seq !== S.namesSeq) return;
      S.srcNames = [];
      $('srcNamesRows').innerHTML = `<tr><td colspan="10" class="bld-warn">${esc(e.message)}</td></tr>`;
      return;
    }
    const keep = [$('srcfSource').value, $('srcfClass').value, $('srcfSector').value, $('srcfIndustry').value];
    const sectors = [...new Set(S.srcNames.filter(n => n.bucket === 'Equities' && n.sector && !['Unmapped', 'Other'].includes(n.sector)).map(n => n.sector))].sort();
    $('srcfSector').innerHTML = '<option value="">All sectors</option><option value="__none">No sector</option>' + sectors.map(s => `<option>${esc(s)}</option>`).join('');
    if (sectors.includes(keep[2]) || keep[2] === '__none') $('srcfSector').value = keep[2];
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
    const inds = [...new Set((S.srcNames || []).filter(n => n.industry && (!sc || (n.bucket === 'Equities' && (sc === '__none' ? noSector(n) : n.sector === sc)))).map(n => n.industry))].sort();
    $('srcfIndustry').innerHTML = '<option value="">All industries</option>' + inds.map(s => `<option>${esc(s)}</option>`).join('');
    if (want && inds.includes(want)) $('srcfIndustry').value = want;
  }

  const bucketOf = n => (n && (n.bucket || S.assign[n.sym])) || null;
  // symbol text coloured by its Hedgeye outlook (same colours as the other screens); plain when unknown
  const symHtml = sym => { const o = (S.outlooks[sym] || (S.nameCache[sym] || {}).outlook); const c = o && window.outlookColor ? window.outlookColor(o) : ''; return `<span${c && c !== 'inherit' ? ` style="color:${c}"` : ''}${o ? ` title="Outlook: ${esc(o)}"` : ''}>${window.symbolLink ? window.symbolLink(esc(sym), sym) : esc(sym)}</span>`; };
  // 2026-11-18, user: 🔭 long-term and 🔔 watch badges (+ notes) in the first column, same notes as the Actionable screen.
  // Fixed-width slots (ticker | group letter | 🔭 | 🔔) so the icons line up on every row; an empty slot shows a faint icon on row hover.
  const bullets = lines => lines.filter(Boolean).map(l => '• ' + l).join('\n');
  const noteIcon = (sym, kind) => noteIconRaw(sym, kind).replace('data-ic=', `data-k="${kind}" data-ic=`);   // data-k = which popover the icon opens (lt | w)
  function noteIconRaw(sym, kind) {
    const f = S.flags[sym] || {};
    if (kind === 'lt') {
      const lt = f.lt, avoid = lt && lt.dir === 'AVOID';
      if (lt) return `<button type="button" class="bld-ic on${avoid ? ' avoid' : ''}" data-ic="${esc(sym)}" title="${esc(bullets([avoid ? 'Long-term AVOID: do not buy' : 'Long-term hold: do not sell on short-term noise', lt.note, lt.target ? 'Target date ' + lt.target : '', 'Click to edit']))}">${avoid ? '🚫' : '🔭'}</button>`;
      if (f.mine) return `<button type="button" class="bld-ic on" data-ic="${esc(sym)}" title="${esc(bullets(['My stocks note', f.mine, 'Click to edit']))}">📝</button>`;
      return `<button type="button" class="bld-ic off" data-ic="${esc(sym)}" title="Add a long-term note, a watch or a note">🔭</button>`;
    }
    const w = f.w;
    if (w) return `<button type="button" class="bld-ic on" data-ic="${esc(sym)}" title="${esc(bullets(['Watching' + (w.triggered ? ' (triggered)' : ''), w.note, 'Alert: ' + [w.pct != null ? (w.dir === 'DOWN' ? 'down ' : 'up ') + w.pct + '% move' : '', w.lrr ? 'LRR' : '', w.trr ? 'TRR' : '', w.trade ? 'Trade line' : '', w.trend ? 'Trend line' : '', w.price != null ? '$' + w.price : '', w.call ? 'Final Call turns ' + (w.call === 'SELL' ? 'Sell' : 'Buy') : ''].filter(Boolean).join(', ').replace(/^Alert: $/, 'Alert: end-of-close reminder'), 'Click to edit']))}">🔔</button>`;
    return `<button type="button" class="bld-ic off" data-ic="${esc(sym)}" title="Add a watch or a note">🔔</button>`;
  }
  const symCell = (sym, grpHtml) => `<span class="bld-sc"><span class="bld-sct">${symHtml(sym)}</span>${grpHtml == null ? '' : `<span class="bld-scg">${grpHtml}</span>`}${noteIcon(sym, 'lt')}${noteIcon(sym, 'w')}</span>`;
  // 2026-11-18, user: amounts in the grids are bold and dark. Any cell / span whose whole text is a dollar amount gets .bld-amt (CSS in builder.html).
  const AMT_RE = /^[+−-]?\$[\d.,]+[KM]?$/;
  function markAmounts(root) {
    if (!root) return;
    root.querySelectorAll('td, td span, td b').forEach(el => {
      if (!el.children.length && !el.classList.contains('bld-amt') && AMT_RE.test(el.textContent.trim())) el.classList.add('bld-amt');
    });
  }
  let amtT = null;
  function watchAmounts() {
    ['cmpTable', 'symTable'].forEach(id => {
      const el = $(id);
      if (!el || el._amtObs) return;
      el._amtObs = new MutationObserver(() => { clearTimeout(amtT); amtT = setTimeout(() => { markAmounts($('cmpTable')); markAmounts($('symTable')); }, 30); });
      el._amtObs.observe(el, { childList: true, subtree: true });
    });
    markAmounts($('cmpTable')); markAmounts($('symTable'));
  }
  async function loadFlags() {
    try { S.flags = (await api('/api/builder/sym-flags')).flags || {}; } catch (e) { S.flags = S.flags || {}; }
  }
  async function refreshFlags() {
    await loadFlags();
    if (S.sources.includes('LT') || S.sources.includes('WATCH')) await loadSourceNames(); else renderSourceNames();
    if (S.preview) renderPicks(S.preview);
  }
  const picked = sym => S.picks.find(p => p.sym === sym);
  const isEquitySector = n => !!n && !BUCKETS.includes(n) && !['Equities', 'Unmapped', 'Other', 'Cash'].includes(n);
  // which comparison sections are collapsed (Asset class, Risk, Style, ...): remembered in this browser only
  try { S.collapsed = JSON.parse(localStorage.getItem('bld_collapsed') || '{}') || {}; } catch (e) { S.collapsed = {}; }
  let startFromHoldings = () => {};   // set in renderSources()

  // 2026-10-29: copy-symbols icon (two overlapping squares, same as the Actionable screen) -> comma-separated, pastes into a TOS watchlist
  const COPY_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  const EQUITY_SECTORS = ['Communication Services', 'Consumer Discretionary', 'Consumer Staples', 'Energy', 'Financials', 'Health Care', 'Industrials', 'Information Technology', 'Materials', 'Real Estate', 'Utilities'];   // the 11 sectors the data uses
  // 2026-11-18, user: when Stk Room $ is $0, say WHY in the cell (the tightest limit), so nobody has to hover
  const whyShort = b => b === 'Cash to spend' ? 'no cash' : (b === "The stock's own Max" ? 'own max' : (CLS_ABBR[b] ? CLS_ABBR[b] + ' full' : String(b || '').replace(/ favored \(Bull\)/, '') + ' full'));
  // 2026-11-18, user: say why a pick got no shares. Two causes: the class has no target money, or one share costs more than the pick's slice.
  function noBuyWhy(sym, b, fin, amt) {
    const n = S.nameCache[sym] || {}, pk = picked(sym) || {};
    if (n.price == null) return 'no price today';
    if (pk.amt > 0) return 'The room is less than one share ($' + Math.round(n.price).toLocaleString() + ')';
    return 'nothing to add';
  }
  // 2026-11-18, user: short names in the names list (hover shows the full name). Display only.
  const SEC_ABBR = { 'Communication Services': 'Comm', 'Consumer Discretionary': 'Disc', 'Consumer Staples': 'Stap', 'Energy': 'Energy', 'Financials': 'Fin',
    'Health Care': 'Health', 'Industrials': 'Indus', 'Information Technology': 'Tech', 'Materials': 'Matl', 'Real Estate': 'RE', 'Utilities': 'Util' };
  const STY_ABBR = { 'defensives': 'Def', 'low beta': 'LoB', 'dividend': 'Div', 'cyclical': 'Cyc', 'high beta': 'HiB', 'small caps': 'SmC', 'value': 'Val', 'secular': 'Sec', 'mid caps': 'MidC', 'momentum': 'Mtum' };
  const CLS_ABBR = { 'Equities': 'Eqts', 'Fixed Income': 'F.Inc', 'Currency': 'Curr', 'Gold': 'Gold', 'Commodities': 'Cmdty', 'Crypto': 'Crypto', 'Unmapped': 'Unmpd' };   // display only
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

  const noSector = n => !n.sector || ['Unmapped', 'Other'].includes(n.sector);   // an equity with no real sector: the 'No sector' row
  // 2026-11-17, user: the same filters also apply to the picked list on the right (a row there = a pick or a holding).
  // The name's sector / quad / style / source come from the names list when it has it, else from the cache of looked-up names.
  // 2026-11-17, user: the Actionable Final Call as a column and a filter (any action = buy side or sell side)
  const actOk = (a, f) => !f || (f === 'any' ? !!(a && (a.side === 'buy' || a.side === 'sell')) : !!(a && a.side === f));
  const actHtml = (a, sym) => !a || !a.label ? `<span class="bld-muted" data-actpop="${esc(sym || '')}">-</span>` : `<span style="color:${a.side === 'buy' ? '#0f9d58' : a.side === 'sell' ? '#e5484d' : '#8a93a6'};font-weight:600;font-size:10px" data-actpop="${esc(sym || '')}">${esc(a.code || a.label)}</span>`;   // hover = the Actionable screen's Action popup (web/actionable_pops_dash.js)
  function rowPassesFilters(sym, bucket) {
    const sc = $('srcfSector').value, ind = $('srcfIndustry').value;
    const fs = $('srcfSource').value, fc = $('srcfClass').value, ff = $('srcfFactor').value, tx = $('srcfText').value.trim().toUpperCase();
    const qsel = [...$('srcfQuad').querySelectorAll('input:checked')].map(i => parseInt(i.value, 10));
    const fa = $('srcfAction').value;
    if ($('srcfScope').value === 'names') return true;   // 2026-11-17, user: "names list only" leaves the picked grid unfiltered
    if (!sc && !ind && !fs && !fc && !ff && !tx && !qsel.length && !fa) return true;
    const n = (S.srcNames || []).find(x => x.sym === sym) || S.nameCache[sym] || {};
    return (!fs || (n.sources || []).includes(fs)) &&
      (!qsel.length || qsel.some(i => (n.quad || [])[i] === 'bull')) &&
      (!sc || (bucket === 'Equities' && (sc === '__none' ? noSector(n) : n.sector === sc))) && (!ind || n.industry === ind) &&
      (!fc || (fc === '__missing' ? bucket === 'Unmapped' : bucket === fc)) && factorOk(n, ff) &&
      (!tx || sym.toUpperCase().includes(tx)) && actOk(((S.preview || {}).final_calls || {})[sym], fa);
  }
  function shownNames() {
    const all = S.srcNames || [];
    const sc = $('srcfSector').value, ind = $('srcfIndustry').value;
    const fs =$('srcfSource').value, fc = $('srcfClass').value, ff = $('srcfFactor').value, tx = $('srcfText').value.trim().toUpperCase();
    const qsel = [...$('srcfQuad').querySelectorAll('input:checked')].map(i => parseInt(i.value, 10));
    const hidePicked = !!($('srcfHidePicked') && $('srcfHidePicked').checked);
    // 2026-11-17, user: "Picked grid only" leaves the names list unfiltered (Hide picked still applies)
    if ($('srcfScope').value === 'picks') return all.filter(n => !hidePicked || !picked(n.sym));
    return all.filter(n => (!fs || n.sources.includes(fs)) &&
      (!qsel.length || qsel.some(i => (n.quad || [])[i] === 'bull')) &&
      (!sc || (bucketOf(n) === 'Equities' && (sc === '__none' ? noSector(n) : n.sector === sc))) && (!ind || n.industry === ind) &&
      (!fc || (fc === '__missing' ? !bucketOf(n) : bucketOf(n) === fc)) && factorOk(n, ff) &&
      (!tx || n.sym.toUpperCase().includes(tx)) &&
      actOk(n.act, $('srcfAction').value) && (!hidePicked || !picked(n.sym)));
  }

  // 2026-11-17, user: "Allocate my holdings". Ticks the stocks the account holds (only in asset classes that have a target, or all of
  // them when no target is set) and gives each its share of its class, in proportion to what is held now. Targets are not touched,
  // and picks you chose by hand that are not held keep their own %. Runs from the button and after a preset is chosen.
  function allocateHoldings() {
    const res = S.preview || {};
    const held = (res.account && res.account.holdings) || [];
    const chosen = res.mix_target || {}, anyTarget = Object.keys(chosen).some(k => chosen[k] > 0);
    const hold = {};
    let added = 0;
    held.forEach(h => {
      if (!(h.value > 0) || !h.bucket || h.bucket === 'Cash' || !BUCKETS.includes(h.bucket)) return;
      if (anyTarget && !(chosen[h.bucket] > 0)) return;
      hold[h.sym] = h.value;
      if (!picked(h.sym)) { S.picks.push({ sym: h.sym, bucket: h.bucket, pct: null, amt: null, grp: '' }); added++; }
    });
    const tot = {};
    S.picks.forEach(p => { if (hold[p.sym] > 0) tot[p.bucket] = (tot[p.bucket] || 0) + hold[p.sym]; });
    const n = Object.keys(hold).length;         // 2026-11-19: no % shares are written any more: a held stock simply keeps what it holds
    const hint = $('srcNamesHint');
    if (hint) hint.textContent = n ? 'Allocated ' + n + ' held stocks across ' + Object.keys(tot).length + ' asset classes (' + added + ' added to picks).' : 'No held stocks fall in an asset class with a target.';
    if (n) planDirty();
    renderSourceNames(); schedule(0);
  }

  // 2026-11-19, user: every plan starts with what you hold. After a delete the held stocks are ticked again (they sit on the right, so the left boxes are locked)
  // 2026-11-20, user: shares bought since the plan was saved come off the planned Buy $; once it is all bought the stock leaves the plan (it stays on the right as a holding)
  function applyBought(res) {
    const hold = {}; (((res || {}).account || {}).holdings || []).forEach(h => { hold[h.sym] = h; });
    const done = [];
    S.picks.forEach(p => {
      if (!(p.amtSaved > 0) || S.pickBase[p.sym] == null) return;
      const h = hold[p.sym] || {}, price = h.price || 0, bought = Math.max(0, (h.qty || 0) - S.pickBase[p.sym]) * price;
      const rem = p.amtSaved - bought;
      if (bought > 0 && price && rem < price) done.push(p.sym);
      else p.amt = bought > 0 ? Math.round(rem) : p.amtSaved;
    });
    if (done.length) {
      S.picks = S.picks.filter(p => !done.includes(p.sym));
      done.forEach(k => { delete S.pickBase[k]; });
      const hint = $('srcNamesHint'); if (hint) hint.textContent = done.join(', ') + (done.length === 1 ? ' is' : ' are') + ' bought: removed from the plan\'s buys (still held on the right).';
      renderSourceNames();
    }
  }
  function tickHeldPicks() {
    const held = (S.preview && S.preview.account && S.preview.account.holdings) || [];
    held.forEach(h => {
      if (h.value > 0 && h.bucket && h.bucket !== 'Cash' && BUCKETS.includes(h.bucket) && !picked(h.sym)) S.picks.push({ sym: h.sym, bucket: h.bucket, pct: null, amt: null, grp: '' });
    });
  }
  function setPick(sym, on) {
    const n = S.nameCache[sym];
    const b = bucketOf(n);
    if (on && n && b && n.usable && !picked(sym)) {   // existing picks are never touched: a new stock is added on top
      // if the class adds up to less than 100%, the new stock starts with what is left, but never more than its own room allows
      let pc = null;
      const bk = S.preview && S.preview.buckets && S.preview.buckets[b], tgt = bk && bk.pct > 0 ? bk.dollars : 0;
      const holdNow = ((S.preview && S.preview.account && S.preview.account.holdings) || []).some(h => h.sym === sym && h.value > 0);
      const rm = (S.room || {})[sym];
      S.clsTotal = S.clsTotal || {};
      const tot = S.clsTotal[b] || 0;
      if (tgt > 0 && !holdNow && tot < 99.95) {
        let v = 100 - tot;
        if (rm && rm.max != null) v = Math.min(v, rm.max / tgt * 100);
        v = Math.floor(v * 10) / 10;
        if (v >= 0.1) { pc = v; S.clsTotal[b] = tot + v; }
      }
      S.picks.push({ sym, bucket: b, pct: pc, amt: null, grp: '' });
    }   // existing picks are never touched: a new stock is added on top
    if (!on) S.picks = S.picks.filter(p => p.sym !== sym);
  }

  function selectShown() {
    shownNames().forEach(n => setPick(n.sym, true));
    renderSourceNames(); schedule(0);
  }

  // 2026-11-18, user: can this name be picked, and is there room to buy it? (same Stk Room $ as the picks grid; warn-only, you can still pick it)
  function canPickTd(n, b) {
    if (!b) return '<td class="bld-muted" title="Choose an asset class first (use the Asset class filter or the name\'s class)">No class</td>';
    if (n.price == null) return '<td class="bld-muted" title="No price today, so it cannot be turned into shares">No price</td>';
    const rm = (S.room || {})[n.sym];
    if (!rm) return '<td class="bld-muted">-</td>';
    const tip = esc('Most you can still add: ' + usd(rm.max) + '. Tightest limit: ' + rm.binding + '.');
    return rm.max > 0 ? `<td class="n bld-up bld-tip" data-tip="${tip}">${usd(rm.max)}</td>` : `<td class="n bld-warn bld-tip" data-tip="${tip}">Full <span class="bld-muted" style="font-size:9px">${esc(whyShort(rm.binding))}</span></td>`;
  }

  function renderSourceNames() {
    const heldSyms = new Set(((S.preview && S.preview.account && S.preview.account.holdings) || []).filter(h => h.value > 0).map(h => h.sym));
    markActiveFilters();
    if (S.preview) renderPicks(S.preview);   // 2026-11-17, user: the filters also cut the picked list on the right
    const all = S.srcNames || [];
    const rows = shownNames();
    $('srcNamesCount').textContent = all.length ? `${all.length} names` + (rows.length !== all.length ? ` · showing ${rows.length}` : '') : '';
    $('srcNamesHint').textContent = S.picks.length ? `${S.picks.length} picked` : '';
    if (!all.length) { $('srcNamesRows').innerHTML = `<tr><td colspan="10" class="bld-muted">${S.sources.length ? 'No names on those lists today.' : 'Tick a list on the left to see its names here.'}</td></tr>`; return; }
    $('srcNamesRows').innerHTML = rows.map(n => {
      const b = bucketOf(n), on = !!picked(n.sym);
      const cls = b ? esc(b) : `<select data-assign="${esc(n.sym)}"><option value="">Class...</option>${BUCKETS.map(x => `<option>${esc(x)}</option>`).join('')}</select>`;
      const st = (n.styles || []).map(t => { const f = STYLE_TO_FACTOR[String(t).toLowerCase()]; const sh = STY_ABBR[String(t).toLowerCase()] || t; return f ? ftag('factor', f, esc(sh), t + '. Filter: ' + ((FACTORS.find(x => x[0] === f) || [])[1] || f) + ' (a group of related tags)') : `<span title="${esc(t)}">${esc(sh)}</span>`; }).join(', ') || '<span class="bld-muted">-</span>';
      const heldNow = on;      // on = already in the picks on the right (held or not)      // 2026-11-19, user: a stock you already hold is already on the right: its box is ticked and locked
      return `<tr><td><input type="checkbox" data-pick="${esc(n.sym)}" ${on ? 'checked' : ''} ${(!b || heldNow) ? 'disabled' : ''} title="${!b ? 'Choose an asset class first' : (heldNow ? (heldSyms.has(n.sym) ? 'You hold this stock: it is already in the picks on the right (use the x there to remove it)' : 'Already in the picks on the right (use the x there to remove it)') : 'Add to picks')}"></td>` +
        `<td>${symCell(n.sym)}</td>${canPickTd(n, b)}<td>${n.sources.map(c => ftag('src', c, esc(c), 'Show only the ' + c + ' list')).join(', ')}</td><td>${b ? ftag('cls', b, esc(CLS_ABBR[b] || b), 'Show only ' + b) : cls}</td><td>${(bucketOf(n) === 'Equities' && n.sector && !['Unmapped', 'Other'].includes(n.sector)) ? ftag('sector', n.sector, esc(SEC_ABBR[n.sector] || n.sector), 'Show only ' + n.sector) : '<span class="bld-muted">-</span>'}</td>` +
        `<td>${(n.quad || []).map((w, i) => `<span class="bld-qp ${w || 'none'}${w ? ' bld-ftag' : ''}${w && $('srcfQuad').querySelector('input[value="' + i + '"]:checked') ? ' on' : ''}"${w ? ` data-ftype="quad" data-fval="${i}"` : ''} title="Q${i + 1}: ${w || 'no view'}${w ? ' (click: filter to Quad ' + (i + 1) + ' favored)' : ''}">${w ? 'Q' + (i + 1) : '-'}</span>`).join('')}</td><td class="n">${n.beta == null ? '<span class="bld-muted">-</span>' : n.beta.toFixed(2)}</td><td>${st}</td><td>${actHtml(n.act, n.sym)}</td></tr>`;
    }).join('') || '<tr><td colspan="10" class="bld-muted">No names match.</td></tr>';
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
    return BUCKETS.slice();      // 2026-11-17, user: every asset class always has a row, so a target can be typed for any of them (Gold, Crypto...)
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
      // 2026-11-17, user: the bar shows what you HOLD: green = held (up to the target), amber = still to add, red = held beyond the target;
      // grey when there is no target. Picks are the thin blue line underneath; the black tick is the target.
      const hv = r.hv, seg = (a, b, c, thin) => b > a ? `<div class="vfill" style="left:${w(a)}%;width:${w(b) - w(a)}%;background:${c}${thin ? ';top:1.5px;height:4px' : ''}"></div>` : '';
      let main = '';
      if (hv != null) {
        if (tv == null) main = seg(0, hv, '#9ca3af');
        else main = seg(0, Math.min(hv, tv), '#16a34a') + seg(hv, tv, '#d97706', true) + seg(tv, hv, '#dc2626', true);
      }
      return '<td class="bld-bar"><div class="bld-viz"><div class="vrow">' +
        `<div class="vtrack2">${main}${pv != null && pv > 0 ? `<div class="vhold" style="width:${w(pv)}%;background:#2563eb" title="Picks ${pv.toFixed(1)}%"></div>` : ''}` +
        `${tv != null && tv > 0 ? `<div class="vtick" style="left:${w(tv)}%" title="Target ${tv.toFixed(1)}%"></div>` : ''}</div></div></div></td>`;
    });
  }

  // One comparison table: factor names down the left, "Your picks" and "My portfolio" side by side, then the gap.
  function compareTable(res) {
    S.limitOvers = [];      // 2026-11-18: limit rows (Quad / Sector / Style / Beta) the picks go over, for the line above the picks grids
    const ex = res.exposure || {}, P = ex.picked || {}, H = ex.held || {};
    const cur = res.mix_current || {}, fin = res.mix_final || {}, amt = res.amount || 1;
    const hasPick = (P.total || 0) > 0, hasHeld = (H.total || 0) > 0;
    if (!hasPick && !hasHeld && !S.picks.length) return '';
    const dash = '<span class="bld-muted">-</span>';
    const f0 = v => v.toFixed(1) + '%';
    const bd = (q, w) => ((q || {})[w] || 0);
    const gapTd = (g, dec) => (g == null || !hasPick || !hasHeld) ? '<td></td>'
      : `<td class="n ${Math.abs(g) < (dec ? 0.005 : 0.5) ? '' : (g > 0 ? 'bld-up' : 'bld-dn')}">${(g >= 0 ? '+' : '−') + Math.abs(g).toFixed(dec || 1)}${dec ? '' : ' pts'}</td>`;
    // a section break: the rows after it become their own small table (laid out in three columns, see the end of this function)
    let curKey = '';
    const vizRows = {}, heldMap = {}, pickMap = {};
    const sec = t => { curKey = t.split(' ·')[0]; vizRows[curKey] = []; return `\u0001${t}\u0002`; };
    const chosen = (S.preset === 'custom' && S.mix) ? S.mix : (res.mix_target || {});   // what you typed, not the rescaled copy
    // 2026-11-17: against a target of 0, any pick is Over (no 5-point leeway)
    // 2026-11-17, user: amber until the target is reached (no "close enough"), green on target, red over
    const judge = (pv, tv) => { const tol = 0.05; return pv > tv + tol ? 'bld-over' : (pv < tv - tol ? 'bld-warn' : 'bld-up'); };
    // gap = picks minus its reference (the target if one is set, else the portfolio); coloured against a target
    // 2026-11-17, user: Gap in points and dollars, each right-aligned in a fixed-width box so they line up row to row
    const gapPd = g => `<span style="display:inline-block;width:62px;text-align:right">${(g >= 0 ? '+' : '−') + '$' + Math.round(Math.abs(g) / 100 * amt / 1000)}K</span>`;   // 2026-11-17, user: amount only, no points
    const gapCell = (pv, ref, haveRef, dec, judged) => {
      if (pv == null || ref == null || !hasPick || !haveRef) return '<td></td>';
      const g = pv - ref;
      const c = judged ? judge(pv, ref, dec) : '';   // 2026-11-17, user: no target = no verdict, so no green / red
      if (judged && !dec) {   // against a target: say it in words ("Short 20.0 pts" = 20 points of the account below the target)
        const a = Math.abs(g);
        return `<td class="n ${c}" style="white-space:nowrap" title="${a < 0.05 ? 'On target' : (g < 0 ? 'Short ' : 'Over ') + a.toFixed(1) + ' points of the account = ' + esc(usd(a / 100 * amt)) + '. Picks ' + pv.toFixed(1) + '% vs Target ' + ref.toFixed(1) + '%'}">${a < 0.05 ? 'On target' : gapPd(g)}</td>`;
      }
      if (!dec) return `<td class="n ${c}" style="white-space:nowrap" title="Picks minus Held: ${Math.abs(g).toFixed(1)} points = ${esc(usd(Math.abs(g) / 100 * amt))}">${gapPd(g)}</td>`;
      return `<td class="n ${c}">${(g >= 0 ? '+' : '−') + Math.abs(g).toFixed(dec)}</td>`;
    };
    const tgtCell = (attr, tv, dec, eq, sw) => `<td class="n" style="white-space:nowrap"><input type="number" min="0" step="${dec ? 0.05 : 0.1}" ${attr}${sw ? ` data-eq="${eq}"` : ''} value="${tv == null ? '' : Number(sw ? tv / eq * 100 : tv).toFixed(1)}" class="${tv != null && !dec && tv > 100 ? 'tgt-over' : ''}">${tv != null && tv > 0 && !(eq > 0) ? '<span style="display:inline-block;width:22px;margin:0 3px 0 6px"></span>' : ''}${tv != null && tv > 0 && eq > 0 ? `<span class="bld-muted" style="display:inline-block;width:22px;font-size:9px;margin:0 3px 0 6px" title="${esc(sw ? (tv / eq * 100).toFixed(1) + '% of the Equities target (' + eq.toFixed(1) + '% of the account) = ' + tv.toFixed(1) + '% of the account' : tv.toFixed(1) + '% of the account = ' + (tv / eq * 100).toFixed(0) + '% of the Equities target (' + eq.toFixed(1) + '%)')}">${sw ? Number(tv.toFixed(1)) : (tv / eq * 100).toFixed(0)}%</span>` : ''}${tv != null && tv > 0 && amt ? `<span style="color:var(--text-1);font-size:9px;margin-left:3px;white-space:nowrap;display:inline-block;width:34px;text-align:left" title="The target in dollars: ${esc(usd(tv / 100 * amt))} of the account">$${Math.round(tv / 100 * amt / 1000)}K</span>` : ''}</td>`;
    // 2026-11-14, user: in the Asset class grid, say in dollars what the account must do to reach the target (the account's own value).
    // Target vs what it holds now: Sell all / Sell $X / Room to buy $X / On plan. Information only; nothing trades.
    const planTd = (asset, tv, hv) => {
      if (!asset) {                                    // 2026-11-17: the other grids say it too -- room left under the limit, or over it, in dollars
        if (tv == null || !hasHeld || hv == null) return '<td></td>';   // a typed 0 is a real limit: held money there shows Over
        const g = (tv - hv) / 100 * amt;
        if (g < -500) return `<td class="n bld-dn" title="Held is over this limit">Over ${usd(-g)}</td>`;
        if (g > 500) return `<td class="n bld-up" title="Room left under this limit">Stk Room ${usd(g)}</td>`;
        return '<td class="n bld-muted">On plan</td>';
      }
      if (curKey !== 'Asset class') return '<td></td>';
      if (tv == null || !hasHeld) return '<td></td>';
      const gap = (tv - (hv || 0)) / 100 * amt;
      if (tv === 0 && (hv || 0) * amt / 100 > 500) return `<td class="n bld-dn"><b>Sell all ${usd((hv || 0) * amt / 100)}</b></td>`;
      if (gap < -500) return `<td class="n bld-dn">Sell ${usd(-gap)}</td>`;
      if (gap > 500) return `<td class="n bld-up">Stk Room ${usd(gap)}</td>`;
      return '<td class="n bld-muted">On plan</td>';
    };
    // 2026-11-17, user: "Covered" = how much of the target the stocks you already hold fill (held up to the target, as % of the target),
    // and how many held stocks that is. The count needs each stock's sector / style / quad, so it comes from the names list when known.
    const heldList = ((res.account && res.account.holdings) || []).filter(h => h.value > 0 && h.bucket && h.bucket !== 'Cash');
    const heldIn = flt => heldList.filter(h => {
      if (!flt) return false;
      const n = S.nameCache[h.sym];
      if (flt[0] === 'cls') return h.bucket === flt[1];
      if (!n) return false;
      if (flt[0] === 'sector') return n.sector === flt[1];
      if (flt[0] === 'factor') return factorOk(n, flt[1]);
      if (flt[0] === 'quad') return (n.quad || [])[+flt[1]] === 'bull';
      return false;
    }).length;
    const coverTd = (hv, eff, flt) => {
      if (eff == null || !(eff > 0) || !hasHeld || hv == null) return '<td></td>';
      const c = Math.min(hv, eff) / eff * 100, n = flt ? heldIn(flt) : null;
      return `<td class="n bld-tip" data-tip="Your held stocks fill ${c.toFixed(1)}% of this target${n != null ? ' (' + n + ' stock' + (n === 1 ? '' : 's') + ')' : ''}. Held ${hv.toFixed(1)}% of the account, target ${eff.toFixed(1)}%."><b class="${c >= 95 ? 'bld-up' : 'bld-warn'}">${c.toFixed(1)}%</b>${n != null && n > 0 ? ' <span class="bld-muted">' + n + '</span>' : ''}</td>`;
    };
    // One row. pv / hv = percent picked / held (null = nothing there). key = target key (null: no target cell);
    // asset = asset class name (its target is the mix you chose; judged against the mix after the Risk Dial).
    // 2026-11-17, user: dollars next to the % -- the % of the account times the account amount
    const kOf = p => { const d = p / 100 * amt; return (d < 0 ? '-$' : '$') + Math.round(Math.abs(d) / 1000) + 'K'; };
    const dolTd = (p, cls) => `<td class="n ${cls == null ? '' : cls}" style="font-size:9px${cls == null ? ';color:var(--text-1)' : ''}" title="${p == null ? '' : esc(usd(p / 100 * amt))}">${p == null ? '-' : kOf(p)}</td>`;
    // 2026-11-17, user: colour of the name = the outlook (Hedgeye risk range, else your Bollinger-band signal) of the sector's ETF or the
    // asset class's proxy.  (Style / Quad / Risk rows have no proxy).
    const GO = res.group_outlooks || {};
    // same rule and colours as the dashboard chips (today_strip.js): 'bull...' = green, 'bear...' (incl. Mild Bearish) = red, anything else = grey, none = no colour
    const olColor = o => { o = String(o || '').toLowerCase(); return !o ? '' : o.indexOf('bull') >= 0 ? '#0f9d58' : o.indexOf('bear') >= 0 ? '#e5484d' : '#8a93a6'; };
    const R = (label, pv, hv, tip, key, asset, flt, tvx) => {
      const olv = asset ? (GO.asset || {})[asset] : (flt && flt[0] === 'sector' && flt[1] !== '__none' ? (GO.sector || {})[flt[1]] : null);
      const olCol = olColor(olv), olTip = olv ? `\nOutlook: ${olv} (${(GO.proxy || {})[asset || flt[1]] || ''}: Hedgeye risk range, else your Bollinger signal)` : '';   // tvx = a reference value with no box (Cash: what is left after the asset classes)
      const tv = asset ? (chosen[asset] > 0 ? Math.round(chosen[asset] * 100) / 100 : null) : (key ? tgtOf(key) : null);
      // 2026-11-17, user: once a mix is set, a class at 0 is a real target of 0 (picks there are Over), not "no target"
      const eff = asset ? (fin[asset] > 0 ? fin[asset] : (Object.keys(chosen).length ? 0 : null)) : (key ? tv : (tvx > 0 ? tvx : null));
      const cell = asset ? tgtCell(`data-tgt-asset="${esc(asset)}"`, tv) : (key ? tgtCell(`data-tgt="${esc(key)}"`, tv, false, /^sector:/.test(key) ? (fin.Equities > 0 ? fin.Equities : 0) : 0, key.startsWith('sector:') && fin.Equities > 0) : (tvx > 0 ? `<td class="n" style="white-space:nowrap" title="Calculated: 100% minus the asset class targets above"><b style="display:inline-block;width:37px;padding-right:3px;box-sizing:border-box;text-align:right">${tvx.toFixed(1)}</b>${amt ? `<span style="display:inline-block;width:22px;margin:0 3px 0 6px"></span><span style="color:var(--text-1);font-size:9px;margin-left:3px;white-space:nowrap;display:inline-block;width:34px;text-align:left" title="The target in dollars: ${esc(usd(tvx / 100 * amt))} of the account">$${Math.round(tvx / 100 * amt / 1000)}K</span>` : ''}</td>` : '<td></td>'));
      if (!asset && key && tv != null && hasPick && pv != null && (pv - tv) / 100 * amt > Math.min(500, 0.005 * amt)) S.limitOvers.push({ label: String(label).replace(/<[^>]*>/g, ''), by: (pv - tv) / 100 * amt });
      if (hasHeld && hv != null && (asset || key)) (heldMap[curKey] = heldMap[curKey] || {})[asset ? 'asset:' + asset : key] = hv;
      if (hasPick && pv != null && key) (pickMap[curKey] = pickMap[curKey] || {})[key] = pv;   // 2026-11-20: for the Sectors 'from picks' button (No sector included, so the Targets add to the whole Equities target)
      if (vizRows[curKey]) vizRows[curKey].push({ label: asset || String(label).replace(/<[^>]*>/g, ''), pv: hasPick ? pv : null, hv: hasHeld ? hv : null, tv: eff, col: asset ? bcol(asset) : null, flt });
      const barTd = `\u0005${curKey}\u0006${(vizRows[curKey] || []).length - 1}\u0007`;
      const eqB = key && key.startsWith('sector:') && fin.Equities > 0 ? fin.Equities : 0, kq = eqB ? 100 / eqB : 1;   // 2026-11-18, user: the SCTR grid shows Held % and Picks % as a share of the Equities target
      const pCell = hasPick && pv != null ? `<span class="bld-muted" style="font-size:9px"${eqB ? ` title="${esc(f0(pv) + ' of the account')}"` : ''}>${f0(pv * kq)}</span>` : dash;   // 2026-11-17, user: % grey, amounts dark (the status colour is on the Picks $ and Gap amounts)
      const bd = asset && (S.bands || {})[asset];      // 2026-11-18, user: min-max % of one position, next to the asset class name
      const bandTxt = bd ? ` <span class="bld-muted bld-tip" style="font-size:9px;font-weight:400" data-tip="${esc('Each ' + asset + ' position may be ' + bd.min + '% to ' + bd.max + '% of the account (Ref Data: asset allocation, ' + bd.category + ').')}">${bd.min}%-${bd.max}%</span>` : '';
      return `<tr${flt ? ` class="bld-frow" data-ftype="${flt[0]}" data-fval="${esc(flt[1])}"` : ''}><td${olCol ? ` style="color:${olCol};font-weight:600"` : ''}${tip ? ` class="bld-tip" data-tip="${esc(tip + olTip)}"` : (flt ? ` title="${esc('Click: show only this in the names list (Ctrl+click: add to the current filters)' + olTip)}"` : (olTip ? ` title="${esc(olTip.trim())}"` : ''))}>${label}${bandTxt}</td>${barTd}${cell}<td class="n bld-muted" style="font-size:9px"${eqB && hasHeld && hv != null ? ` title="${esc(f0(hv) + ' of the account')}"` : ''}>${hasHeld && hv != null ? f0(hv * kq) : dash}</td>${dolTd(hasHeld ? hv : null)}` +
        // 2026-11-17, user: order = Target, Held, Held $, To plan (none use picks), then Picks, Picks $, Gap (use picks)
        `${planTd(asset, asset ? (Object.keys(chosen).length ? (chosen[asset] || 0) : null) : (key ? tv : null), hv)}<td class="n">${pCell}</td>${dolTd(hasPick ? pv : null, hasPick && pv != null && eff != null ? judge(pv, eff) : null)}${eff != null ? gapCell(pv, eff, true, 0, true) : gapCell(pv, hv, hasHeld, 0, false)}</tr>`;
    };
    const generalTip = 'Asset class rows are % of the account. Everything below is also % of the account (the same basis the plan check uses). Quad and style rows overlap (one fund can carry several), so they do not add to 100%. A stock takes its sector\'s Quad view. Red = over target.';
    let t = '';
    t += sec('Asset class');
    let placedTotal = 0, heldInvested = 0;
    for (const b of mixBuckets(res)) {
      const placed = (res.positions || []).filter(p => p.bucket === b).reduce((a, p) => a + p.value, 0) / amt * 100;
      placedTotal += placed;
      heldInvested += cur[b] || 0;
      t += R(esc(b), placed, cur[b] || 0, null, null, b, ['cls', b]);
    }
    t += `<tr><td class="bld-tip" data-tip="All the money your picks place. Over 100% (red) means the picks add up to more than the account.">Total invested</td><td class="bld-bar"></td><td></td><td class="n bld-muted" style="font-size:9px">${hasHeld ? f0(heldInvested) : dash}</td>${dolTd(hasHeld ? heldInvested : null)}<td></td><td class="n">${S.picks.length ? `<b class="${placedTotal > 100.5 ? 'bld-over' : ''}">${f0(placedTotal)}</b>` : dash}</td>${dolTd(S.picks.length ? placedTotal : null)}<td></td></tr>`;
    const clsSum = BUCKETS.reduce((a, b) => a + (chosen[b] || 0), 0);
    const overBy = Object.keys(chosen).length && clsSum > 100.05 ? clsSum - 100 : 0;
    t += R(`Cash${overBy ? ` <span class="bld-over" title="The asset class targets add to ${clsSum.toFixed(1)}%. They need to add to 100% before the plan can be activated.">classes add to ${clsSum.toFixed(1)}%, over by ${overBy.toFixed(1)}</span>` : ''}`, (res.cash && res.cash.dollars || 0) / amt * 100, cur.Cash || 0, 'Cash and money not yet placed', null, undefined, undefined, Object.keys(chosen).length ? Math.max(0, 100 - BUCKETS.reduce((a, b) => a + (chosen[b] || 0), 0)) : fin.Cash);
    if (cur.Unmapped > 0.04) t += R('Unmapped', null, cur.Unmapped, 'Held with no asset class: cannot be picked');
    t += sec('Risk');
    const fb = v => (v == null ? dash : v.toFixed(2));
    t += R('Low beta (0.8 or under)', hasPick ? P.lowbeta : null, hasHeld ? H.lowbeta : null, null, 'lowbeta', undefined, ['factor', 'lowbeta']) + R('High beta (over 1.2)', hasPick ? P.highbeta : null, hasHeld ? H.highbeta : null, null, 'highbeta', undefined, ['factor', 'highbeta']);
    t += R('Middle beta (0.8 to 1.2)', hasPick ? P.midbeta : null, hasHeld ? H.midbeta : null, 'Names with a beta between 0.8 and 1.2: not low, not high.', 'midbeta')
      + R('No beta known', hasPick ? P.nobeta : null, hasHeld ? H.nobeta : null, 'Names with no beta yet (cash, new listings, some funds). Not covered by the beta rows above. Click the row to list them.', 'nobeta', undefined, ['factor', 'nobeta']);
    t += sec('Quad');
    for (const q of ['Q1', 'Q2', 'Q3', 'Q4']) {
      const pq = (P.quad || {})[q], hq = (H.quad || {})[q];
      const tip = `${q} outlook. Picks: Bull ${bd(pq, 'bull').toFixed(1)}%, Neutral ${bd(pq, 'neutral').toFixed(1)}%, Bear ${bd(pq, 'bear').toFixed(1)}%, no view ${bd(pq, 'none').toFixed(1)}%. Portfolio: Bull ${bd(hq, 'bull').toFixed(1)}%, Neutral ${bd(hq, 'neutral').toFixed(1)}%, Bear ${bd(hq, 'bear').toFixed(1)}%, no view ${bd(hq, 'none').toFixed(1)}%`;
      t += R(q, hasPick ? bd(pq, 'bull') : null, hasHeld ? bd(hq, 'bull') : null, tip, 'quad:' + q, undefined, ['quad', String(['Q1', 'Q2', 'Q3', 'Q4'].indexOf(q))]);
    }
    t += sec('Sectors');
    const sv = k => Math.max((P.sector || {})[k] || 0, (H.sector || {})[k] || 0, tgtOf('sector:' + k) || 0);
    const SEC_SHORT = { 'Information Technology': 'Info Tech', 'Consumer Discretionary': 'Cons Disc', 'Communication Services': 'Comm Svcs' };
    const allSec = new Set(Object.keys(P.sector || {}).concat(Object.keys(H.sector || {})));
    Object.keys(S.targets).filter(k => k.startsWith('sector:')).forEach(k => allSec.add(k.slice(7)));
    EQUITY_SECTORS.forEach(k => allSec.add(k));      // 2026-11-17, user: all 11 sectors always have a row, so a limit can be typed for any of them
    Object.values(S.nameCache).forEach(n => { if (n.bucket === 'Equities' && n.sector && !['Unmapped', 'Other'].includes(n.sector)) allSec.add(n.sector); });
    [...allSec].filter(s => s === 'Equities' || !BUCKETS.includes(s)).sort((a, b) => sv(b) - sv(a) || a.localeCompare(b))   // Fixed Income / Gold / Currency are in the Asset class grid; 'Equities' here = equities with no sector
      .forEach(s => { t += R(s === 'Equities' ? 'No sector' : (SEC_SHORT[s] ? `<span title="${esc(s)}">${SEC_SHORT[s]}</span>` : esc(s)), hasPick ? ((P.sector || {})[s] || 0) : null, hasHeld ? ((H.sector || {})[s] || 0) : null, s === 'Equities' ? 'Equities with no sector assigned. Click the row to list them.' : null, 'sector:' + s, undefined, s === 'Equities' ? ['sector', '__none'] : ['sector', s]); });
    t += sec('Style');
    // 2026-11-18, user: say what each style row means. A name can carry several tags, so it can sit in more than one row (rows can add to over 100%).
    const STYLE_HELP = {
      defensive: 'Defensive: stocks tagged Defensives, Low Beta or Dividend. They tend to fall less when the market drops: steady businesses and dividend payers.',
      offensive: 'Offensive: stocks tagged Cyclical, High Beta or Small Caps. They tend to move more than the market: they gain more in rallies and lose more in selloffs.',
      value: 'Value: stocks tagged Value. Priced cheaply compared with what the business earns or owns.',
      growth: 'Growth: stocks tagged Secular. Businesses growing steadily whatever the economy does (long-term themes).',
      mid: 'Mid: stocks tagged Mid Caps. Medium-sized companies, between large and small.' };
    [['defensive', 'Defensive'], ['offensive', 'Offensive'], ['value', 'Value'], ['growth', 'Growth'], ['mid', 'Mid']]
      .forEach(f => { t += R(f[1], hasPick ? ((P.style || {})[f[0]] || 0) : null, hasHeld ? ((H.style || {})[f[0]] || 0) : null, STYLE_HELP[f[0]] + '\nA stock can carry several tags, so it can count in more than one row and the rows can add to over 100%.', 'style:' + f[0], undefined, ['factor', f[0]]); });
    t += R('No style tag', hasPick ? P.nostyle : null, hasHeld ? H.nostyle : null, 'Names that carry none of the style groups above. Click the row to list them.', 'style:none', undefined, ['factor', 'nostyle']);
    // 2026-11-18, user: a Total line at the bottom of every grid (targets, held, picks added up)
    const totRow = k => {
      const v = vizRows[k] || [], sm = f => v.reduce((a, x) => a + (x[f] == null ? 0 : x[f]), 0);
      const tT = sm('tv'), hT = sm('hv'), pT = sm('pv'), hasT = v.some(x => x.tv != null);
      const tq = k === 'Sectors' && fin.Equities > 0 ? 100 / fin.Equities : 1;   // SCTR: a share of the Equities target
      const ov = k === 'Quad' || k === 'Style' ? 'A stock can sit in more than one row here, so the total can be over 100%.' : (k === 'Asset class' ? 'Asset classes plus Cash: the target should add to 100%.' : 'Added up from the rows above.');
      return `<tr class="bld-tot" style="border-top:1px solid #aeb6c8;font-weight:600"><td class="bld-tip" data-tip="${esc('Total of the rows above. ' + ov)}">Total</td><td class="bld-bar"></td><td class="n" style="font-size:9px">${hasT ? '<span style="display:inline-block;width:37px;box-sizing:border-box;padding-right:3px;text-align:right">' + (tT * (k === 'Sectors' ? tq : 1)).toFixed(1) + '</span>' + ((k === 'Sectors' || k === 'Style') && fin.Equities > 0 ? `<span class="bld-muted" style="display:inline-block;width:22px;font-size:9px;font-weight:400;margin:0 3px 0 6px" title="${esc(k === 'Sectors' ? (tT * tq).toFixed(1) + '% of the Equities target = ' + tT.toFixed(1) + '% of the account' : tT.toFixed(1) + '% of the account = ' + (tT / fin.Equities * 100).toFixed(0) + '% of the Equities target (' + fin.Equities.toFixed(1) + '%)')}">${k === 'Sectors' ? Number(tT.toFixed(1)) : (tT / fin.Equities * 100).toFixed(0)}%</span>` : '') : dash}</td><td class="n bld-muted" style="font-size:9px">${hasHeld ? f0(hT * tq) : dash}</td>${dolTd(hasHeld ? hT : null)}<td></td><td class="n bld-muted" style="font-size:9px">${hasPick ? f0(pT * tq) : dash}</td>${dolTd(hasPick ? pT : null)}<td></td></tr>`;
    };
    // 2026-10-28, user: show the sections in three columns. Cut the rows at each section break, one small table per section.
    const parts = t.split(/\u0001([^\u0002]*)\u0002/);          // ['', title1, rows1, title2, rows2, ...]
    const tables = {};
    for (let i = 1; i < parts.length; i += 2) {
      const title = parts[i], first = i === 1;
      const skey = title.split(' ·')[0], shut = false;
      tables[skey] = `<div class="bld-sec${shut ? ' collapsed' : ''}" data-sec="${esc(skey)}">` + `<table class="bld-t bld-exp"><thead><tr><th${first ? ` class="bld-tip" data-tip="${esc(generalTip)}"` : ''}>${title.replace(/^Asset class/, 'Asset').replace(/^Sectors/, 'SCTR')}<span style="white-space:nowrap;margin-left:2px">${heldMap[skey] && Object.keys(heldMap[skey]).length ? `<button type="button" class="bld-clr" data-byholdgrid="${esc(skey)}" style="margin-right:4px" title="Set every Target in this grid to what you hold now (rounded to 0.1%). Nothing is saved until you press Save.">Hlds</button>` : ''}<button type="button" class="bld-clr" style="float:none" data-clear="${esc(skey)}" title="Clear the Target boxes in this grid only">Clear</button></span></th><th class="bld-bar-h" title="Bar = what you hold: green = held (up to the target), amber = still to add, red = held beyond the target, grey = no target. Thin blue line = picks. Black line = target.">${skey === 'Sectors' ? `<button type="button" class="bld-clr" style="float:none" data-bypickgrid="Sectors" title="Set every sector Target to the share your picks have in it (kept to 0.01%, shown to 0.1%); sectors with no picks are cleared. Nothing is saved until you press Save.">From picks</button>` : 'Chart'}</th>` +
        `<th class="n bld-tip" style="white-space:nowrap !important" data-tip="Type your target % on any row. Blank = no target. Targets guide you; they never pick stocks."><span style="display:inline-block;width:68px;white-space:nowrap">Target</span><span style="margin-left:3px;font-weight:600;color:var(--text-1);font-size:9px;text-transform:none;letter-spacing:0;white-space:nowrap" title="${esc(skey === 'Sectors' && fin.Equities > 0 ? 'The Equities target in dollars: 100% of this grid' : 'The account amount: 100% of this grid')}">${amt && (skey === 'Asset class' || skey === 'Sectors') ? '$' + Math.round((skey === 'Sectors' && fin.Equities > 0 ? amt * fin.Equities / 100 : amt) / 1000) + 'K' : ""}</span></th><th class="n">Held</th><th class="n" title="Held in dollars (K = thousands)">Held $</th>${first ? '<th class="n bld-tip" data-tip="What the account must do to reach the Target, in dollars: Sell all, Sell, or Room to buy. Information only; nothing trades.">To plan</th>' : '<th class="n bld-tip" data-tip="Room left under the limit, in dollars (or how far held is over it).">Room</th>'}<th class="n">Picks</th><th class="n" title="Picks in dollars (K = thousands)">Picks $</th><th class="n bld-tip" data-tip="Picks against the Target, in points of the account. A minus = your picks are below the target; a plus = above it. Without a target it is Picks minus Held. The dollars are the points times the account amount.">Gap <span class="bld-muted" style="font-weight:400;font-size:9px;text-transform:none;letter-spacing:0">$K</span></th></tr></thead><tbody>${barCells(parts[i + 1], skey, vizRows[skey])}${skey === 'Asset class' || skey === 'Sectors' ? totRow(skey) : ''}</tbody></table></div>`;
    }
    S.heldMap = heldMap; S.pickMap = pickMap;
    const T = k => tables[k] || '';
    // 2026-10-28, user: the five grids stay in three columns
    return `<div class="bld-cmp3"><div>${T('Asset class')}${T('Sectors')}</div><div>${T('Style')}${T('Quad')}${T('Risk')}</div></div>`;   // keys are the title up to " ·"
  }

  // The Preset sits between the Asset class bar chart and its grid: it only fills the asset class % boxes below it.
  function presetHtml() {
    // 2026-11-17, user: ONE control. "My holdings" = everything from the account; a preset = class % only; Clear = every target. It resets to "Start from..." after it runs.
    const pre = (S.presetOpts || []).filter(p => p[0] !== 'current' && p[0] !== 'custom').map(p => `<option value="p:${esc(p[0])}">${esc(p[1])}</option>`).join('');
    return `<select id="startFrom" title="Create a new plan from: your holdings (class %, picked stocks, sector / style / beta limits, Buy $ gaps), a ready-made mix (asset class % only). Nothing is saved until you press Save."><option value="">Create new plan from...</option><option value="hold">My holdings</option>${pre ? '<option disabled>------------</option>' + pre : ''}</select>`;
  }
  const tgtOf = key => (S.targets[key] == null ? null : S.targets[key]);

  // an asset class target typed in the table: it becomes the custom mix (the rest stays Cash; the classes cannot add to more than 100)
  function setAssetTarget(b, raw) {
    const res = S.preview || {};
    const base = Object.assign({}, S.mix || res.mix_target || {});
    delete base.Cash;
    // 2026-11-18, user: keep the number typed (0 to 100). If the classes then add to more than 100 the Cash row turns red and says so; Save still asks for 100.
    base[b] = raw === '' ? 0 : Math.max(0, Math.min(parseFloat(raw) || 0, 100));
    S.mix = base; S.preset = 'custom'; planDirty(); schedule(0);
  }

  // targets typed on the other rows are guides only: redraw the table, no server call
  // 2026-11-18, user: a Clear button on every grid (and one for all, on the heading line). Targets only: picks stay, nothing is saved until Save.
  function clearTargetsIn(scope) {
    const all = scope === 'all';
    if (all || scope === 'Asset class') { S.mix = {}; S.preset = 'custom'; S.allocNext = false; }
    Object.keys(S.targets).forEach(k => {
      const hit = all || (scope === 'Risk' && ['lowbeta', 'highbeta', 'midbeta', 'nobeta'].includes(k)) || (scope === 'Quad' && k.startsWith('quad:'))
        || (scope === 'Sectors' && k.startsWith('sector:')) || (scope === 'Style' && k.startsWith('style:'));
      if (hit) delete S.targets[k];
    });
    if (all) S.targets = {};
    planDirty(); drawCmpSoon(); schedule(0);
  }
  // 2026-11-19, user: typing in a Target box and clicking the next one lost the click, because the grids were redrawn in the middle of it.
  // Redraw after the click has finished, and put the cursor back in whichever Target box has it.
  function drawCmp(res) {
    const host = $('cmpTable'), ae = document.activeElement;
    let sel = null;
    if (ae && ae.tagName === 'INPUT' && host.contains(ae)) {
      const at = [...ae.attributes].find(x => /^data-(tgt|tgt-asset)$/.test(x.name));
      if (at) sel = 'input[' + at.name + '="' + at.value.replace(/"/g, '\\"') + '"]';
    }
    host.innerHTML = compareTable(res);
    bindCmp();
    if (sel) { const el = host.querySelector(sel); if (el) el.focus(); }
  }
  const drawCmpSoon = () => setTimeout(() => drawCmp(S.preview), 0);
  function bindCmp() {
    const host = $('cmpTable');
    if (!host.dataset.fbound) { host.dataset.fbound = '1'; host.addEventListener('click', e => { if (e.target.closest('input,select,button')) return; const t = e.target.closest('[data-ftype]'); if (t && t.tagName === 'TR' && e.target.closest('td') !== t.cells[0]) return; /* 2026-11-17, user: only the first column filters */ if (t) focusFilter(t.dataset.ftype, t.dataset.fval, e.ctrlKey || e.metaKey); }); }
    host.querySelectorAll('[data-tgt]').forEach(i => i.onchange = () => {
      const k = i.dataset.tgt;
      if (i.value === '') delete S.targets[k]; else S.targets[k] = Math.max(0, parseFloat(i.value) || 0) * (parseFloat(i.dataset.eq) > 0 ? parseFloat(i.dataset.eq) / 100 : 1);   // SCTR boxes are a % of the Equities target; stored as a % of the account
      planDirty();
      drawCmpSoon();
      schedule();                         // Stk Room $ depends on the limits
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
    host.querySelectorAll('[data-byholdgrid]').forEach(b => b.onclick = e => {
      e.stopPropagation();
      const hm = (S.heldMap || {})[b.dataset.byholdgrid] || {}, tot = Object.values(hm).reduce((a, v) => a + v, 0);
      if (b.dataset.byholdgrid === 'Asset class') {
        const mix = {}; Object.keys(hm).forEach(k => { if (k.startsWith('asset:')) mix[k.slice(6)] = Math.round(hm[k] * 10) / 10; });
        S.mix = mix; S.preset = 'custom';
      } else Object.keys(hm).forEach(k => { S.targets[k] = Math.round(hm[k] * 10) / 10; });
      planDirty(); drawCmpSoon(); schedule(0);
    });
    host.querySelectorAll('[data-bypickgrid]').forEach(b => b.onclick = e => {   // 2026-11-20, user: fill the sector Targets from the picks
      e.stopPropagation();
      const pm = (S.pickMap || {})[b.dataset.bypickgrid] || {};
      Object.keys(S.targets).filter(k => k.startsWith('sector:')).forEach(k => delete S.targets[k]);
      // the SCTR boxes show a % of the Equities target (stored as a % of the account): round what is SHOWN to 0.1 so the Target equals the Picks % beside it
      const eqEl = host.querySelector('[data-tgt^="sector:"][data-eq]'), eq = eqEl ? parseFloat(eqEl.dataset.eq) : 0;
      Object.keys(pm).forEach(k => {
        const shown = Math.round((eq > 0 ? pm[k] / eq * 100 : pm[k]) * 100) / 100;   // 2 decimals kept so the total adds up; the box still shows 1
        if (shown > 0) S.targets[k] = shown * (eq > 0 ? eq / 100 : 1);
      });
      planDirty(); drawCmpSoon(); schedule(0);
    });
    host.querySelectorAll('[data-clear]').forEach(b => b.onclick = e => {
      e.stopPropagation();
      clearTargetsIn(b.dataset.clear);
    });
    host.querySelectorAll('[data-sec-toggle]').forEach(c => c.onclick = e => {
      e.stopPropagation();
      const k = c.dataset.secToggle;
      S.collapsed[k] = !S.collapsed[k];
      try { localStorage.setItem('bld_collapsed', JSON.stringify(S.collapsed)); } catch (x) { /* private window */ }
      const box = c.closest('.bld-sec'); box.classList.toggle('collapsed', !!S.collapsed[k]);
      c.innerHTML = S.collapsed[k] ? '&#9656;' : '&#9662;'; c.title = (S.collapsed[k] ? 'Show' : 'Hide') + ' this section';
    });
    // the preset + Allocate controls live on the Charts and grids heading line
    const slot = $('presetSlot'); if (slot) slot.innerHTML = presetHtml();
    const sf = slot && slot.querySelector('#startFrom');
    if (sf) sf.onchange = () => {
      const v = sf.value; sf.value = '';
      if (!v) return;
      if (PL.dirty && !window.confirm('This replaces your current numbers (you have unsaved changes). Continue?')) return;
      if (v === 'hold') { startFromHoldings(false); return; }
      S.preset = v.slice(2); S.mix = null; planDirty(); schedule();     // a ready-made mix: the asset class % boxes only
    };
    host.querySelectorAll('[data-tgt-asset]').forEach(i => i.onchange = () => setAssetTarget(i.dataset.tgtAsset, i.value));
    markActiveFilters();
  }

  // plain click on a comparison row/bar = only that filter; Ctrl+click = add it to the others; clicking the sole active one clears it
  function focusFilter(type, val, add) {
    if ($('srcfHidePicked')) $('srcfHidePicked').checked = false;   // 2026-11-17, user: clicking a grid row to filter shows the picked stocks too
    if (add) return toggleFilter(type, val);
    const was = filterIsOn(type, val);
    const others = ['srcfSource', 'srcfClass', 'srcfSector', 'srcfIndustry', 'srcfFactor', 'srcfAction', 'srcfText'].some(id => $(id).value && !(filterSel[type] === id && was))
      || [...$('srcfQuad').querySelectorAll('input:checked')].some(c => !(type === 'quad' && was && c.value === val));
    ['srcfSource', 'srcfClass', 'srcfSector', 'srcfFactor', 'srcfAction', 'srcfText'].forEach(id => { $(id).value = ''; });
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
    const add = (label, short, apply) => { if (short > 5) out.push({ label: `${label}: ${short.toFixed(1)} pts short`, short, apply }); };
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
    }).filter(r => rowPassesFilters(r.sym, r.bucket));
    // 2026-11-17, user: "Matched" must not hide a class that is over its target. A pick equal to its holding in a class whose picks
    // exceed the class target says "Sell $X to reach target", the class excess split in proportion to each pick's amount.
    const clsPick = {};
    rows.forEach(r => { if (r.pk) clsPick[r.bucket] = (clsPick[r.bucket] || 0) + r.model; });
    // 2026-11-19, user: typing a % on one stock must only change the class's last line (Left to set / Over target), never the other rows,
    // so the old "this name's share of the excess" Sell amount is off.
    const sellToTarget = r => {
      return 0;
      if (!r.pk || r.kept || r.trade !== 'Matched' || !BUCKETS.includes(r.bucket) || !Object.keys(fin).length) return 0;
      const cp = clsPick[r.bucket] || 0, ex = cp - (fin[r.bucket] || 0) / 100 * amt;
      return (cp > 0 && ex > Math.min(500, 0.005 * amt)) ? ex * r.model / cp : 0;
    };
    const dash = '<span class="bld-muted">-</span>';
    // 2026-11-17, user: the Actionable screen's Final Call, as a last column (green = buy side, red = sell side, grey = hold / other)
    const actTd = sym => {
      const fc = (res.final_calls || {})[sym];
      if (!fc || !fc.label) return `<td><span class="bld-muted" data-actpop="${esc(sym)}">-</span></td>`;
      const col = fc.side === 'buy' ? '#0f9d58' : fc.side === 'sell' ? '#e5484d' : '#8a93a6';
      return `<td><span style="color:${col};font-weight:600;font-size:10px" data-actpop="${esc(sym)}">${esc(fc.code || fc.label)}</span></td>`;
    };
    // 2026-10-28, user: two columns -- Equities on the right, every other asset class on the left
    const head = `<table class="bld-t bld-exp bld-symt"><thead><tr><th>Symbol ${copyBtn('list', rows.map(r => r.sym), 'Copy all ' + rows.length + ' symbols (every asset class)')}</th><th class="n">Picks</th><th class="n bld-tip" data-tip="Stk Room $ = the most you can still buy of this ONE stock (its cap less what you hold): its Max rule less what you hold. An ETF counts as an equity, so with no rule of its own it uses your usual stock limit. A dash = no per-stock limit for this class.">Stk Room $</th><th class="n bld-tip" data-tip="Ceiling $ = your own lower cap on the TOTAL you hold of this stock. The gray number is the Max rule; you can never go above it. Blank = use the rule. Stk Room $ is the cap less what you hold.">Ceiling $ <button type="button" class="bld-btn sm alt" data-ceilall style="padding:0 5px;margin-left:3px;font-size:9px" title="Set the Picks % of every stock that has a ceiling, to its ceiling %">&rarr;</button></th><th class="n bld-tip" data-tip="Room Left $ = the room left in the buckets this stock sits in: cash, its asset class, sector, style and beta, after the other buys you planned. The word beside a $0 says which bucket is full. The amount planned is the smaller of Stk Room $ and Room Left $. Information only: nothing stops you going over.">Room Left $</th><th class="bld-tip" data-tip="Give two or more picks the same letter to buy any one of them (whichever is better when Actionable says Buy). The $ box beside the letter is the most to buy across the whole group; blank = the biggest room any member has.">One of</th><th class="n bld-tip" data-tip="Held % = this stock's held dollars as a share of its asset class (the class target when one is set, otherwise what you hold in the class). Same basis as the Picks % box. The class row shows the share of the whole account.">Held %</th><th class="n">Held $</th><th class="n">Gap $</th><th>To match</th><th title="Action: the Actionable screen's Final Call for this stock">Actn</th></tr></thead><tbody>`;
    const side = { left: '', right: '' };
    S.clsTotal = {};
    S.unal = {}; S.byHold = {};          // 2026-11-18: per class, what the Unallocated / Over target buttons work on
    const overs = [];   // classes where the picks add up to more than the class allows
    const mixSet = Object.keys((S.preset === 'custom' && S.mix) ? S.mix : (res.mix_target || {})).length > 0;
    for (const b of BUCKETS.concat(['Unmapped'])) {
      const mine = rows.filter(r => r.bucket === b).sort((x, y) => {
        // 2026-11-19, user: stocks you hold come first (biggest first); a stock you just ticked stays at the bottom, in the order ticked
        const xh = x.hold > 0, yh = y.hold > 0;
        if (xh !== yh) return xh ? -1 : 1;
        if (xh) return y.hold - x.hold;
        return S.picks.findIndex(q => q.sym === x.sym) - S.picks.findIndex(q => q.sym === y.sym);
      });
      if (!mine.length) continue;      // 2026-11-18, user: a class shows in the picks grids only once something is held or picked in it (the Asset class grid lists them all)
      let t = '';
      const mTot = mine.reduce((a, r) => a + r.model, 0), hTot = mine.reduce((a, r) => a + r.hold, 0);
      const sumPct = mine.reduce((a, r) => a + (r.pk && r.pk.pct != null ? r.pk.pct : 0), 0);
      const clsShare = (fin[b] || 0) > 0 && amt ? mTot / (amt * fin[b] / 100) * 100 : (sumPct > 0 ? sumPct : null);
      // the header adds up what each row shows: the % you typed, or the gray one where you typed nothing
      const sumShown = mine.reduce((a, r) => a + (!r.pk ? 0 : (r.pk.pct != null ? r.pk.pct : ((fin[b] || 0) > 0 && amt && r.pos ? r.pos.value / (amt * fin[b] / 100) * 100 : 0))), 0);
      S.clsTotal[b] = sumShown;   // the class total on screen: a stock picked next may take what is left of 100
      const hdrShare = sumShown > 0 ? sumShown : clsShare;
      const hdrCls = sumShown > 0 ? (Math.abs(sumShown - 100) < 0.05 ? 'bld-up' : (sumShown > 100 ? 'bld-over' : 'bld-warn')) : '';   // green = exactly 100, amber = short, red = over
      // 2026-11-17, user: a blank / 0 class target (once a mix is set) is a target of 0, so any picks there are over the limit
      const zeroTgt = mixSet && BUCKETS.includes(b) && !((fin[b] || 0) > 0);
      const overCls = sumPct > 100.5 || ((fin[b] || 0) > 0 && mTot / amt * 100 > fin[b] + 0.5) || (zeroTgt && mTot > Math.min(500, 0.005 * amt));
      if (overCls) overs.push(`${CLS_ABBR[b] || b}: picks ${usd(mTot)}${clsShare != null ? ' = ' + clsShare.toFixed(1) + '% of the class' : ''}${(fin[b] || 0) > 0 ? ' (class target ' + usd(amt * fin[b] / 100) + ')' : (zeroTgt ? ' (class target $0)' : '')}${sumPct > 100.5 ? ', your % boxes add to ' + sumPct.toFixed(1) + '%' : ''}`);
      t += `<tr class="sec"><td title="${esc(b)}">${esc(CLS_ABBR[b] || b)} ${mine.length ? copyBtn('list', mine.map(r => r.sym), 'Copy the ' + mine.length + ' ' + b + ' symbols') : ''}</td><td class="n ${hdrCls || (overCls ? 'bld-over' : '')}" title="${(sumShown > 0 ? 'The Picks % shown in this class (typed, or gray where blank) add to ' + sumShown.toFixed(1) + '% (green = 100, amber = short, red = over). ' : '') + 'Picks in this class: ' + (clsShare != null ? clsShare.toFixed(1) + '% of the class, ' : '') + pct(mTot / amt, 1) + ' of the whole account'}"><span style="display:inline-block;width:36px;text-align:right;box-sizing:border-box;padding-right:3px" title="Class share: the picks' % boxes (blank ones as shown) add to this">${hdrShare != null ? hdrShare.toFixed(1) : ''}</span><span style="display:inline-block;width:92px;padding-left:6px;box-sizing:border-box;font-size:9px"><span style="display:inline-block;width:36px;text-align:right;margin-right:6px" title="Picks in this class as a % of the whole account">${amt ? (mTot / amt * 100).toFixed(1) + '%' : ''}</span><b>${usd(mTot)}</b></span></td><td></td><td>${mine.some(x => x.pk) ? `<button type="button" class="bld-btn sm alt" data-ceilcls="${esc(mine.map(x => x.sym).join(','))}" style="padding:0 5px;margin-left:10px;font-size:9px" title="Set the Picks % of every ${esc(b)} stock that has a ceiling, to its ceiling %">&rarr;</button>` : ''}</td><td></td><td></td><td class="n">${hTot > 0 && (fin[b] || 0) > 0 && amt ? pct(hTot / (amt * fin[b] / 100), 1) : (acctVal ? pct(hTot / acctVal, 1) : '')}</td><td class="n">${usd(hTot)}</td><td class="n">${sgnUsd(mTot - hTot)}</td><td>${(fin[b] || 0) > 0 ? `<span class="bld-muted bld-tsum" title="Class target: ${(fin[b]).toFixed(1)}% of the account = ${usd(amt * fin[b] / 100)}">Tgt ${(fin[b]).toFixed(1)}%${amt ? ' ' + usd(amt * fin[b] / 100) : ''}</span>` : ''}</td><td></td></tr>`;
      mine.forEach(r => {
        // 2026-11-18, user: the Picks box is typed as a % of the WHOLE account; to its right: the class % and the dollars (same total width as before)
        const fb = fin[b] || 0, cb0 = fb > 0 && amt ? amt * fb / 100 : hTot;
        const ph = r.pos && amt ? (r.pos.value / amt * 100).toFixed(1) : '';
        const accLbl = r.pk && r.pk.pct != null && fb > 0 ? Number((r.pk.pct * fb / 100).toFixed(1)) + '%' : (ph ? ph + '%' : '');   // 2026-11-19, user: the box is the % of the CLASS; the grey label is the % of the account
        const clsVal = r.pk && r.pk.pct != null ? String(Number(r.pk.pct.toFixed(1))) : '';
        const clsPh = cb0 > 0 ? ((r.pos ? r.pos.value : r.model) / cb0 * 100).toFixed(1) : '';
        const pCell = r.pk
          ? `<input type="number" min="0" max="100" step="0.1" data-pct="${esc(r.sym)}" data-fin="${fb}" value="${clsVal}" placeholder="${clsPh}"${fb > 0 ? '' : ' disabled'} style="width:36px;padding-left:3px;padding-right:3px" title="${fb > 0 ? '% of the ' + esc(b) + ' class (the % of the whole account and the dollars are shown to the right)' : 'Set the ' + esc(b) + ' class target first'}"><span style="font-size:9px;display:inline-block;width:92px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;vertical-align:middle;padding-left:6px;box-sizing:border-box"><span class="bld-muted" style="display:inline-block;width:36px;text-align:right;margin-right:6px;font-size:9px" title="% of the whole account">${accLbl}</span>` +
            `${r.pos ? '<b>' + usd(r.pos.value) + '</b>' : (r.pk.amt > 0 ? '<span class="bld-warn" title="' + esc(noBuyWhy(r.sym, b, fin, amt)) + '">' + esc(noBuyWhy(r.sym, b, fin, amt)) + '</span>' : '<span class="bld-muted" title="Nothing to add: no room left under its Stk Room $">nothing to add</span>')}</span> <button class="bld-btn sm alt" data-drop="${esc(r.sym)}" title="Remove from picks">×</button>`
          : dash;
        const clsBase = (fin[b] || 0) > 0 && amt ? amt * fin[b] / 100 : hTot;   // same base as the Picks % box: a share of the class
        const hPct = r.h ? (clsBase > 0 ? pct(r.hold / clsBase, 1) : '') : dash;
        const hCell = r.h ? `${usd(r.hold)}${r.kept ? ' <span class="bld-badge sell">Kept</span>' : ''}` : dash;
        const gap = (r.pk || r.h) ? sgnUsd(r.model - r.hold) : '';
        const gl = r.pk && r.pk.grp ? r.pk.grp : '', gcol = gl ? GRP_COL[gl.charCodeAt(0) - 65] : '';
        const rm = (S.room || {})[r.sym];
        const callTxt = '';
        const maxTd = !rm ? '<td></td>' : (rm.stock == null ? '<td class="n bld-muted" title="No per-stock limit for this class">-</td>'
          : `<td class="n bld-tip" data-tip="${esc('Most you can still buy of this one stock: ' + usd(rm.stock) + '. (Its Max rule less what you hold; an ETF with no rule uses your usual stock limit.)')}">${rm.stock > 0 ? usd(rm.stock) : (() => {
            const mm0 = S.myMax[r.sym], cap0 = mm0 != null ? (rm.rule_max != null ? Math.min(mm0, rm.rule_max) : mm0) : rm.rule_max, over0 = cap0 != null ? (r.hold || 0) - cap0 : 0;   // 2026-11-20: show HOW MUCH over the limit
            return over0 > 0.5 ? `<span class="bld-over" title="You hold ${usd(r.hold)}; the limit is ${usd(cap0)} (${mm0 != null && mm0 <= (rm.rule_max ?? mm0) ? 'your ceiling' : 'the Max rule'}). Over by ${usd(over0)}.">Over ${usd(over0)}</span>` : '<span class="bld-warn">$0</span> <span class="bld-muted" style="font-size:9px">at max</span>';
          })()}</td>`);
        const mmv = S.myMax[r.sym];
        const mmTd = `<td class="n"><input type="number" min="0" step="500" data-mymax="${esc(r.sym)}"${rm && rm.rule_max != null ? ' max="' + Math.round(rm.rule_max) + '"' : ''} value="${mmv == null ? '' : mmv}" placeholder="${rm && rm.rule_max != null ? Math.round(rm.rule_max) : ''}" style="width:42px"${mmv != null && rm && rm.stock != null && rm.binding === 'Your ceiling' ? ' class="tgt-over"' : ''} title="Ceiling $: your own cap on the total you hold of ${esc(r.sym)}. Never above the Max rule (gray). Blank = use the rule.">${mmv != null && (fin[b] || 0) > 0 && amt ? `<span class="bld-muted" style="font-size:9px;margin-left:4px;white-space:nowrap;display:inline-block;width:38px;text-align:right;vertical-align:middle" title="Your ceiling as a % of the whole account, the same basis as the Picks % box.">${(mmv / amt * 100).toFixed(1)}%</span>` : ''}${(() => { const cv = mmv != null ? mmv : (rm && rm.rule_max != null ? rm.rule_max : null);   // arrow uses your ceiling, else the Max rule
        return r.pk && cv > 0 && (fin[b] || 0) > 0 && amt ? `<button type="button" class="bld-btn sm alt" data-ceilpct="${esc(r.sym)}" data-v="${(cv / (amt * fin[b] / 100) * 100).toFixed(1)}" style="padding:0 5px;margin-left:3px;font-size:9px" title="Set the Picks % to the ceiling (${mmv != null ? 'yours' : 'the Max rule'})">&rarr;</button>` : ''; })()}</td>`;
        const planBuy = (r.pk && (r.pk.pct != null || !r.pk.grp)) ? Math.max(0, r.model - r.hold) : 0;     // 2026-11-18, user: say when the buy goes over a limit
        // 2026-11-20, user: when the picks in this class add up to no more than the class target, the grid's own sells pay for its buys (the class ends on target),
        // so a class-full limit is not an overrun. Only a real overrun (picks above the class target, or another limit) says Over.
        const clsFundedBySells = (fin[b] || 0) > 0 && amt > 0 && mTot / amt * 100 <= fin[b] + 0.5;   // same 0.5%-of-account slack the class header uses (whole shares round the dollars)
        const overBy = rm && rm.max != null && planBuy > rm.max + 50 && !(clsFundedBySells && rm.binding === b) ? planBuy - rm.max : 0;
        const bindLbl = b0 => b0 === 'Cash to spend' ? 'cash' : (b0 === "The stock's own Max" ? 'own max' : (CLS_ABBR[b0] || String(b0 || '').replace(/ favored \(Bull\)/, '')));
        const bktTd = overBy > 0 ? `<td class="n bld-tip" data-tip="${esc('This buy (' + usd(planBuy) + ') is ' + usd(overBy) + ' more than the room left (' + usd(rm.max) + '). Tightest limit: ' + rm.binding + '. Warning only: nothing is cut.')}"><span class="bld-over" style="white-space:nowrap">Over ${esc(bindLbl(rm.binding))} +${usd(overBy)}</span></td>`
          : !rm ? '<td></td>' : `<td class="n bld-tip" data-tip="${esc('Room left in its buckets: ' + usd(rm.bucket) + '. Tightest: ' + rm.bucket_binding + '. Other planned buys already counted.' + callTxt)}">${rm.bucket > 0 ? '<span class="bld-amt">' + usd(rm.bucket) + '</span>' : (rm.bucket_raw < -0.5 && !(clsFundedBySells && rm.bucket_binding === b) ? '<span class="bld-over" title="' + esc('Already over this limit by ' + usd(-rm.bucket_raw) + ' (held plus planned buys).') + '">Over ' + usd(-rm.bucket_raw) + '</span>' : '<span class="bld-warn">$0</span>')}${(rm.bucket <= 0 || (rm.stock != null && rm.bucket < rm.stock) || (rm.stock == null && rm.bucket < 5000)) ? ' <span class="bld-muted" style="font-size:9px">' + esc(whyShort(rm.bucket_binding)) + '</span>' : ''}</td>`;
        const amtCells = r.pk
          ? `<td><select data-grp="${esc(r.sym)}" title="Give two or more picks the same letter to buy any one of them">${['', 'A', 'B', 'C', 'D', 'E', 'F'].map(g => `<option value="${g}"${(r.pk.grp || '') === g ? ' selected' : ''}>${g || '-'}</option>`).join('')}</select>` +
            (r.pk.grp ? ` <input type="number" min="0" step="500" data-amt="${esc(r.sym)}" value="${r.pk.amt ? r.pk.amt : ''}" placeholder="group $" style="width:70px" title="The most to buy across the whole group (all members share it). Blank = the biggest room any member has.">` : '') + '</td>'
          : '<td></td>';
        t += `<tr${(!r.pk && !r.kept) ? ' class="zero"' : ''}${gcol ? ` style="box-shadow:inset 3px 0 0 ${gcol}"` : ''}><td>${symCell(r.sym, gl ? `<span class="bld-badge" style="background:${gcol};color:#fff;padding:1px 5px" title="Buy one of group ${gl}: you buy only one of these">${gl}</span>` : '')}</td><td class="n">${pCell}</td>${maxTd}${mmTd}${bktTd}${amtCells}<td class="n bld-muted" style="font-size:9px">${hPct}</td><td class="n">${hCell}</td><td class="n">${gap}</td>` +
          (sellToTarget(r) > 0 ? `<td class="bld-dn" title="Same as held, but the ${esc(b)} picks are over the class target. This name's share of the excess, split in proportion to its amount.">Sell ${usd(sellToTarget(r))}</td>${actTd(r.sym)}</tr>`
            : `<td${!r.kept && r.pk && /^Buy /.test(r.trade) ? ' class="bld-up"' : (!r.kept && ((r.pk && /^Sell /.test(r.trade)) || (!r.pk && r.h && r.hold > 0)) ? (!r.pk ? ' class="bld-over"' : ' class="bld-dn"') : '')}${!r.pk && !r.kept && r.h && r.hold > 0 ? ' title="Held but not in your picks: selling all of it moves you to your plan."' : ''}>${esc(r.kept ? 'Kept' : (r.pk ? r.trade : (r.h ? (r.hold > 0 ? 'Sell ' + usd(r.hold) : 'Held, not in picks') : '')))}</td>${actTd(r.sym)}</tr>`);
      });
      // 2026-11-18, user: one line per class showing the difference between the class target and what the picks add up to.
      // Under target = "Unallocated" (money the class has room for that no stock was given); over = "Over target" (picks add up to more than allowed).
      // Nothing is bought or sold for you: you type a % on a stock, or press the button (it only changes blank stocks, evenly).
      {
        const tgtD = (fin[b] || 0) > 0 && amt ? amt * fin[b] / 100 : (zeroTgt ? 0 : null);
        const un = tgtD != null && Math.abs(tgtD - mTot) > (tgtD > 0 ? tgtD * 0.0005 : Math.min(500, 0.005 * amt)) ? tgtD - mTot : 0;   // 2026-11-19, user: the line goes away only when the class adds to 100.0%; any shown difference (0.1% or more) keeps it
        if (un) {
          const over = un < 0, col = over ? '#dc2626' : '#2563eb', bk = (res.buckets || {})[b];
          const base = bk ? Math.max(0, (bk.dollars || 0) - (bk.kept_dollars || 0)) : (tgtD || hTot);
          const blank = mine.filter(r => r.pk && r.pk.pct == null && !r.pk.grp && (!over || r.hold > 0)).map(r => ({ sym: r.sym, v: r.model }));
          S.unal[b] = { diff: un, base, blank };
          const can = blank.length > 0 && base > 0, nb = blank.length;
          // 2026-11-19, user: no buttons and no boxes here: it only says how much of the class is left to set (or over), so you set each stock yourself
          const clsLeft = tgtD > 0 ? un / tgtD * 100 : null, sg = over ? '−' : '+';
          t += `<tr class="bld-unal"><td style="color:${col};font-weight:600;white-space:nowrap" title="${over ? 'The picks add up to ' + usd(mTot) + ', more than the ' + esc(b) + ' target of ' + usd(tgtD) + '.' : 'The ' + esc(b) + ' target is ' + usd(tgtD) + ' and the picks add up to ' + usd(mTot) + '.'} Nothing is bought or sold for you.">${over ? 'Over target' : 'Left to set'}</td>` +
            `<td class="n" style="white-space:nowrap;color:${col};font-weight:600"><span style="display:inline-block;width:36px;text-align:right;box-sizing:border-box;padding-right:3px" title="% of the ${esc(b)} class ${over ? 'over' : 'left'}">${clsLeft != null ? sg + Math.abs(clsLeft).toFixed(1) : ''}</span><span style="font-size:9px;display:inline-block;width:92px;padding-left:6px;box-sizing:border-box"><span style="display:inline-block;width:36px;text-align:right;margin-right:6px;font-weight:400;opacity:.8" title="% of the whole account">${amt ? sg + (Math.abs(un) / amt * 100).toFixed(1) + '%' : ''}</span><b>${sg}${usd(Math.abs(un))}</b></span></td>` +
            `<td colspan="9" class="bld-muted" style="font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"><button type="button" class="bld-btn sm alt" data-unal="${esc(b)}" data-mode="${over ? 'trim' : 'spread'}"${can ? '' : ' disabled'} style="margin-right:6px;padding:0 6px;font-size:9px" title="${can ? (over ? 'Take the excess off the stocks you hold in this class that have no % typed, in proportion to what you hold: ' + nb + ' stock' + (nb === 1 ? '' : 's') + ', about ' + usd(Math.abs(un) / nb) + ' each' : 'Share it equally between the stocks in this class that have no % typed: ' + nb + ' stock' + (nb === 1 ? '' : 's') + ', about ' + usd(un / nb) + ' each') : (over ? 'No held stock without a typed % to trim: lower a % yourself' : 'No stock without a typed % to give it to: type a % on one')}">${over ? 'Trim evenly' : 'Spread equally'}</button>${tgtD > 0 ? 'picks are ' + (mTot / tgtD * 100).toFixed(1) + '% of the ' + esc(CLS_ABBR[b] || b) + ' target (' + usd(mTot) + ' vs ' + usd(tgtD) + ')' : 'picks ' + usd(mTot) + ' with a target of $0'}</td></tr>`;
        }
      }
      side[b === 'Equities' ? 'right' : 'left'] += t;
    }
    // 2026-11-17, user: the column names show once, on the left block; the Equities block drops its own header row (it keeps one when it is the only block)
    const tbl = (rowsHtml, noHead) => rowsHtml ? (noHead ? head.replace(/<thead>.*<\/thead>/, '') : head) + rowsHtml + '</tbody></table>' : '';
    // 2026-11-17, user: one line saying where the Stk Room $ money comes from (real cash vs money from selling over-target classes)
    const rmeta = res.room_meta;
    const money = rmeta ? `<div class="bld-muted bld-money" title="Stk Room $ spends from this. Spendable keeps your cash reserve (${usd(rmeta.keep)}) and the plan's Cash %. Sale money assumes you sell whatever sits above its asset class target. Information only.">Cash <b>${usd(rmeta.cash)}</b> · From selling over-target classes <b>${usd(rmeta.sells)}</b> · Spendable <b>${usd(rmeta.spendable)}</b></div>` : '';
    const lim = (S.limitOvers || []);
    const limMsg = lim.length ? `<div class="bld-over" style="font-size:10px;margin:4px 0" title="Picks above the limit you set on those rows. Warning only: nothing is cut.">Your picks go over ${lim.length} limit${lim.length === 1 ? '' : 's'}: ${lim.map(l => esc(l.label) + ' +' + usd(l.by)).join(', ')}</div>`
      : (S.picks.length && !overs.length ? '<div class="bld-up" style="font-size:10px;margin:4px 0">All limits OK</div>' : '');
    const overMsg = limMsg + (overs.length ? `<div class="bld-over" style="font-size:10px;margin:4px 0">Over the limit - ${overs.map(esc).join(' | ')}. Lower a pick or raise the class target.</div>` : '');
    return money + overMsg + `<div class="bld-sym2"><div>${tbl(side.left)}</div><div>${tbl(side.right, !!side.left)}</div></div>`;
  }

  // ---------------------------------------------------------------- step 2: your picks, actual mix, factor mix
  function renderPicks(res) {
    Object.assign(S.outlooks, res.outlooks || {});
    if ($('picksCount')) $('picksCount').textContent = S.picks.length ? `${S.picks.length} picked` : '';
    const pcb = document.querySelector('.bld-copy[data-copy="picks"]'); if (pcb) pcb.hidden = !S.picks.length;
    drawCmp(res);
    // keep the cursor where it is: typing in one box and clicking another must not lose the click when the table redraws
    let keep = null;
    const ae = document.activeElement;
    if (ae && ae.tagName === 'INPUT' && $('symTable').contains(ae)) {
      const at = [...ae.attributes].find(x => /^data-(pct|mymax|amt)$/.test(x.name));
      if (at) keep = { name: at.name, val: at.value, s: ae.selectionStart, e: ae.selectionEnd };
    }
    $('symTable').innerHTML = symbolTable(res);
    if (keep) {
      const el = [...$('symTable').querySelectorAll('input[' + keep.name + ']')].find(x => x.getAttribute(keep.name) === keep.val);
      if (el) { el.focus(); try { el.setSelectionRange(keep.s, keep.e); } catch (e) { /* number boxes have no selection */ } }
    }
    $('symTable').querySelectorAll('[data-pct]').forEach(i => i.onchange = () => {
      const p = picked(i.dataset.pct);
      const fb = parseFloat(i.dataset.fin) || 0;     // 2026-11-19: the box is a % of the class, stored as typed (fb = the class target % of the account)
      if (p && fb > 0) { p.pct = i.value === '' ? null : Math.min(100, Math.max(0, parseFloat(i.value))); planDirty(); schedule(0); }
    });
    $('symTable').querySelectorAll('[data-mymax]').forEach(i => i.onchange = () => {
      const sym = i.dataset.mymax;
      const rmx = (S.room || {})[sym], ruleMax = rmx && rmx.rule_max != null ? rmx.rule_max : null;
      if (i.value === '') delete S.myMax[sym];
      else {
        let v = Math.max(0, parseFloat(i.value) || 0);
        if (ruleMax != null && v > ruleMax) {   // a ceiling can only lower the rule Max, never raise it
          v = Math.round(ruleMax);
          i.value = v; i.style.outline = '2px solid #dc2626';
          i.title = 'Capped: your ceiling can not be above the Max rule (' + usd(ruleMax) + ').';
          const note = document.createElement('div');
          note.className = 'bld-over'; note.style.cssText = 'font-size:10px;font-weight:400';
          note.textContent = 'Max is ' + usd(ruleMax);
          if (i.parentNode) i.parentNode.appendChild(note);
        }
        S.myMax[sym] = v;
      }
      planDirty(); schedule(0);
    });
    $('symTable').querySelectorAll('[data-ceilpct]').forEach(btn => btn.onclick = () => {
      const p = picked(btn.dataset.ceilpct);
      if (p) { p.pct = Math.min(100, parseFloat(btn.dataset.v) || 0); planDirty(); schedule(0); }
    });
    $('symTable').querySelectorAll('[data-unal]').forEach(btn => btn.onclick = () => {
      const c = (S.unal || {})[btn.dataset.unal];
      if (!c || !(c.base > 0) || !c.blank.length) return;
      if (btn.dataset.mode === 'spread') {
        const add = c.diff / c.blank.length;
        c.blank.forEach(x => { const p = picked(x.sym); if (p) p.pct = Math.min(100, (x.v + add) / c.base * 100); });
      } else {
        const tot = c.blank.reduce((a, x) => a + x.v, 0), cut = Math.min(-c.diff, tot);
        c.blank.forEach(x => { const p = picked(x.sym); if (p && tot > 0) p.pct = Math.max(0, x.v - cut * x.v / tot) / c.base * 100; });
      }
      planDirty(); schedule(0);
    });
    $('symTable').querySelectorAll('[data-ceilall]').forEach(btn => btn.onclick = e => {
      e.stopPropagation();
      let n = 0;
      $('symTable').querySelectorAll('[data-ceilpct]').forEach(b => { const p = picked(b.dataset.ceilpct); if (p) { p.pct = Math.min(100, parseFloat(b.dataset.v) || 0); n++; } });
      if (n) { planDirty(); schedule(0); }
    });
    $('symTable').querySelectorAll('[data-ceilcls]').forEach(btn => btn.onclick = e => {   // one asset class only
      e.stopPropagation();
      let n = 0;
      btn.dataset.ceilcls.split(',').forEach(sym => {
        const b = [...$('symTable').querySelectorAll('[data-ceilpct]')].find(x => x.dataset.ceilpct === sym), p = picked(sym);
        if (b && p) { p.pct = Math.min(100, parseFloat(b.dataset.v) || 0); n++; }
      });
      if (n) { planDirty(); schedule(0); }
    });
    $('symTable').querySelectorAll('[data-drop]').forEach(btn => btn.onclick = () => { setPick(btn.dataset.drop, false); renderSourceNames(); planDirty(); schedule(0); });
    // 2026-11-14: a pick's dollars, and 'buy one of' groups (same letter = buy any one; the group shares one amount)
    $('symTable').querySelectorAll('[data-amt]').forEach(i => i.onchange = () => {
      const p = picked(i.dataset.amt); if (!p) return;
      p.amt = i.value === '' ? null : Math.max(0, parseFloat(i.value) || 0);
      p.amtUser = true; p.autoAmt = false; p.amtSaved = null; delete S.pickBase[p.sym];
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
      applyBought(res);
      S.room = res.room || {};
      let refill = false;
      // the last stock added gets only what is left of its class: if its default would take the class over 100%, it is reduced so the total is exactly 100%
      const posVal = {}, bSum = {}, lastAuto = {};
      (res.positions || []).forEach(x => { posVal[x.sym] = x.value || 0; bSum[x.bucket] = (bSum[x.bucket] || 0) + (x.value || 0); });
      S.picks.forEach(p => { if (autoAmt(p) && p.pct == null) lastAuto[p.bucket] = p.sym; });
      const heldNow = {}; ((res.account && res.account.holdings) || []).forEach(h => { heldNow[h.sym] = h.value || 0; });
      S.picks.forEach(p => {                          // fill the starting Buy $ of picks you have not typed an amount for
        if (!autoAmt(p)) return;
        let st = (S.room[p.sym] || {}).start;
        // 2026-11-18, user: a blank % behaves like a typed one -- the planned buy is what the build gives it (its equal share of what is unfilled in the class)
        // 2026-11-20, user: a typed % too. The To do list was missing the buys of picks with a typed % (BNDD, UUP, XLRE): the server's start amount is 0 when a limit is
        // already full, but limits only warn, so the planned buy is the gap the To match column shows.
        st = Math.max(0, Math.round((posVal[p.sym] || 0) - (heldNow[p.sym] || 0)));
        if (st > 0 && p.amt !== st) { p.amt = st; p.autoAmt = true; refill = true; } else if (!(st > 0) && p.autoAmt) { p.amt = null; p.autoAmt = false; refill = true; }
      });
      if (refill) schedule(0);        // the amounts changed: the grids must be worked out again with them
      render(res);
      if (TD.data && $('tdBuys')) todoRender();   // the To do list follows the picks on screen
      if (S.srcNames.length) {                         // the room for the names list just arrived: redraw it (keeping its scroll place)
        const sc = document.querySelector('.bld-side-scroll'), top = sc ? sc.scrollTop : 0;
        renderSourceNames();
        if (sc) sc.scrollTop = top;
      }
      if (S.fillGapNext) { S.fillGapNext = false; fillBuyGaps(res); }
      if (S.allocNext) { S.allocNext = false; allocateHoldings(); }   // a preset was just chosen: its targets are now in, so lay the held stocks over them
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
    $('acctSnap').textContent = a.snap_date ? 'Acct File: ' + a.snap_date + (a.positions_stale ? ' (older than 3 trading days)' : '') : '';
    if ($('amount')) $('amount').textContent = usd(S.amount || Math.round(a.value || 0));   // 2026-11-19, user: a label, not a box
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
    // 2026-11-17, user: say Unsaved loudly, in red
    const dc = $('planDiscard'); if (dc) dc.hidden = !(PL.dirty && PL.name);   // 2026-11-17, user: Discard shows only while there are unsaved changes
    el.innerHTML = esc(act + view) + (PL.dirty ? ' · <b style="color:#dc2626;background:#fee2e2;padding:0 6px;border-radius:8px">UNSAVED</b>' : '');
  }
  let tdTimer = null;
  function planDirty() { PL.dirty = true; planPill(); clearTimeout(tdTimer); tdTimer = setTimeout(todoLoad, 700); }   // the To do preview follows the edits
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
    plan.sell = Object.assign({}, S.sell); plan.sell_hold = Object.assign({}, S.sellHold); plan.my_max = Object.assign({}, S.myMax);
    plan.pick_base = {};                                   // shares held now of every planned buy: later purchases come off its amount
    const hq = {}; (((S.preview || {}).account || {}).holdings || []).forEach(h => { hq[h.sym] = h.qty || 0; });
    S.picks.forEach(p => { if (p.amt > 0) plan.pick_base[p.sym] = hq[p.sym] || 0; });   // the sale amounts typed in the To do list
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
    S.sell = Object.assign({}, p.sell || {}); S.sellHold = Object.assign({}, p.sell_hold || {}); S.myMax = Object.assign({}, p.my_max || {}); S.pickBase = Object.assign({}, p.pick_base || {});
    if (Array.isArray(p.picks)) { S.picks = p.picks.map(x => ({ sym: x.sym, bucket: x.bucket, pct: x.pct == null ? null : x.pct, amt: x.amt || null, grp: x.grp || '', amtUser: !!x.amt, amtSaved: x.amt || null })); renderSourceNames(); }
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
    const pl = planFromState();
    const rebase = () => { S.pickBase = Object.assign({}, pl.pick_base); S.picks.forEach(p => { p.amtSaved = p.amt > 0 ? p.amt : null; }); };   // what is saved now is the new starting point
    if (name === PL.checked || !PL.checked) {   // the active plan, or the account's first plan (nothing active yet): saving also makes it active
      const r = await planSend('/api/builder/plan/save-check', { account: S.acct, name, plan: pl, date: S.date });
      rebase();
      await planAfterSave(r.name, r.checking);
      return r;
    }
    const r = await planSend('/api/builder/plan/save-as', { account: S.acct, name, plan: pl });
    rebase();
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
    if (!PL.name) { S.picks = []; S.sell = {}; S.sellHold = {}; S.myMax = {}; S.pickBase = {}; S.targets = {}; S.mix = null; S.preset = 'current'; PL.dirty = false; tickHeldPicks(); planPill(); renderSourceNames(); schedule(0); return; }
    if (!window.confirm('Delete the saved plan "' + PL.name + '" for ' + S.acct + '?' + (PL.name === PL.checked ? ' It is the active plan, so the To do list and its planned buys stop. ' : ' ') + 'Your My stocks list is kept.')) return;
    try {
      await planSend('/api/builder/plan?account=' + encodeURIComponent(S.acct) + '&name=' + encodeURIComponent(PL.name), {}, 'DELETE');
      S.picks = []; S.sell = {}; S.sellHold = {}; S.myMax = {}; S.pickBase = {}; S.targets = {}; S.seeded = null; S.mix = null; S.preset = 'current'; PL.name = null;
      await planLoad(); tickHeldPicks(); renderSourceNames(); schedule(0);
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
      // 2026-11-17, user: with unsaved changes the To do list is a preview of the plan on the screen (nothing is saved)
      const t = !(PL.name && PL.name === PL.checked && !PL.dirty)   // 2026-11-20, user: always calculate it -- a preview of the plan on the screen whenever it is not exactly the saved active plan.  // 2026-11-19, user: a loaded plan gets its To do list at once (a preview when it is not the active plan)
        ? await api(withDate('/api/builder/todo-preview'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account: S.acct, plan: planFromState() }) })
        : await api(withDate('/api/builder/todo?account=' + encodeURIComponent(S.acct)));
      if (seq !== TD.seq) return;
      TD.data = t; todoRender();
    } catch (e) { if (seq === TD.seq) tdMsg('Could not load the to-do list: ' + e.message, true); }
    $('tdBody').classList.remove('td-dim');
  }
  // 2026-11-19, user: a summary at the top of the To do list: what is in it, what is left to do, and which chosen stocks are not in it yet
  function tdSummaryHtml(t) {
    const buys = (t.buys || []).filter(x => (x.amount || 0) > 0);
    const buyTot = buys.reduce((a, x) => a + (x.amount || 0), 0);
    const sells = (t.sells || []).filter(x => (x.left || 0) > 0 || x.all);
    const inList = new Set((t.buys || []).flatMap(x => x.members || []));
    const held = new Set(((S.preview && S.preview.account && S.preview.account.holdings) || []).filter(h => h.value > 0).map(h => h.sym));
    const noAmt = S.picks.filter(p => !(p.amt > 0) && !held.has(p.sym)).map(p => p.sym);            // chosen, not held, no Buy $: cannot be a buy
    const unsaved = S.picks.filter(p => p.amt > 0 && !inList.has(p.sym)).map(p => p.sym);          // has a Buy $ but is not in the saved plan yet
    const li = [];
    li.push(buys.length ? `<li><b>Buys:</b> ${buys.length} planned, ${usd(buyTot)} in all (${buys.slice(0, 3).map(x => esc(x.members.join(' or ')) + ' ' + usd(x.amount)).join(', ')}${buys.length > 3 ? ', ...' : ''}). Carry them out on the Actionable screen.</li>` : '<li><b>Buys:</b> none planned yet.</li>');
    li.push(sells.length ? `<li><b>Sells:</b> ${sells.map(x => esc(x.cls) + (x.all ? ' (plan 0%: sell all ' + usd(x.held) + ')' : ' is ' + usd(x.need) + ' over its target')).join('; ')}. They are counted as sold for the cash below.</li>` : '<li><b>Sells:</b> nothing is over its plan.</li>');
    if (unsaved.length) li.push(`<li class="bld-warn"><b>Not saved yet:</b> ${unsaved.slice(0, 8).map(esc).join(', ')}${unsaved.length > 8 ? ' ...' : ''} ${unsaved.length === 1 ? 'has' : 'have'} a Buy $ but ${unsaved.length === 1 ? 'is' : 'are'} not in this list. Press Save to add ${unsaved.length === 1 ? 'it' : 'them'}.</li>`);
    if (noAmt.length) li.push(`<li class="bld-muted"><b>Chosen but not in the list:</b> ${noAmt.slice(0, 8).map(esc).join(', ')}${noAmt.length > 8 ? ' ...' : ''} ${noAmt.length === 1 ? 'has' : 'have'} no room to add under the limits.</li>`);
    return '<b>What to do</b><ul>' + li.join('') + '</ul>';
  }
  function todoRender() {
    const t = TD.data;
    $('tdEmpty').hidden = t.state !== 'none'; $('tdBody').hidden = t.state === 'none';
    $('tdSub').textContent = t.state === 'none' ? '' : ' · ' + S.acct + (t.active_at ? ' · active plan since ' + String(t.active_at).slice(5, 10) : (PL.name ? '' : ' · no plan saved yet')) + (t.preview ? (PL.dirty ? ' · PREVIEW with your unsaved changes (not saved)' : ' · PREVIEW of the loaded plan (it is not the active plan)') : '');
    if (t.state === 'none') return;
    $('tdSummary').innerHTML = tdSummaryHtml(t);

    // sells
    // 2026-11-20, user: type the amount to sell per class; it is split over the holdings in proportion to their value (type over any holding and the
    // others share the rest). Saved with the plan (Save), shown here at once.
    const allocSell = (vals, amount, ov) => {
      const keys = Object.keys(vals), total = keys.reduce((a, k) => a + vals[k], 0);
      amount = Math.min(Math.max(0, amount || 0), total);
      const fixed = {}; let fx = 0;
      keys.forEach(k => { if (ov && ov[k] != null) { fixed[k] = Math.min(Math.max(0, ov[k]), vals[k]); fx += fixed[k]; } });
      const free = keys.filter(k => fixed[k] == null), base = free.reduce((a, k) => a + vals[k], 0), rest = Math.max(0, amount - fx);
      const out = {}; keys.forEach(k => { out[k] = fixed[k] != null ? Math.round(fixed[k]) : 0; });
      if (base > 0 && rest > 0) {
        free.forEach(k => { out[k] = Math.round(rest * vals[k] / base); });
        const diff = Math.round(rest) - free.reduce((a, k) => a + out[k], 0), big = free.slice().sort((a, b) => vals[b] - vals[a])[0];
        out[big] = Math.min(vals[big], Math.max(0, out[big] + diff));
      }
      return out;
    };
    $('tdSells').innerHTML = (t.sells || []).length ? t.sells.map(sl => {
      const vals = {}; sl.holdings.forEach(h => { vals[h.sym] = h.value; });
      const held = Object.values(vals).reduce((a, v) => a + v, 0);
      const def = sl.default != null ? sl.default : sl.need;
      const amt = S.sell[sl.cls] != null ? Math.min(S.sell[sl.cls], held) : def;
      const split = allocSell(vals, amt, S.sellHold);
      const tot = Object.values(split).reduce((a, v) => a + v, 0);
      return `<div style="margin-bottom:10px"><div class="bld-line"><b>${esc(sl.cls)}</b>` +
        tdPill('sell', sl.all ? 'Plan 0%: sell all ' + usd(sl.held) : 'Over plan by about ' + usd(sl.need)) +
        `<span style="margin-left:auto">Amount to sell <input type="number" min="0" step="1000" data-tdcls="${esc(sl.cls)}" value="${Math.round(amt)}" style="width:92px" title="Defaults to how far the class is over its plan plus the buys you planned in the same class (the sells pay for them). Split over the holdings below in proportion to their value."></span></div>` +
        '<table class="bld-t"><thead><tr><th>Holding</th><th class="n">Value</th><th class="n">Sell $</th><th class="n" title="What you still hold after selling: Value minus Sell $">Remaining</th></tr></thead><tbody>' +
        sl.holdings.map(h => {
          const sv = split[h.sym] || 0;
          return `<tr><td><b>${esc(h.sym)}</b></td><td class="n">${usd(h.value)}</td><td class="n"><input type="number" min="0" step="500" data-tdhold="${esc(h.sym)}" value="${Math.round(sv)}" style="width:80px"${S.sellHold[h.sym] != null ? ' class="tgt-over" title="You typed this amount: the other holdings share the rest"' : ''}></td><td class="n">${usd(Math.max(0, h.value - sv))}</td></tr>`;
        }).join('') +
        `<tr><td><b>Total</b></td><td class="n">${usd(held)}</td><td class="n"><b>${usd(tot)}</b></td><td class="n"><b>${usd(Math.max(0, held - tot))}</b></td></tr></tbody></table></div>`;
    }).join('') : '<div class="bld-muted">Nothing is over its plan. No sells needed.</div>';
    $('tdSells').querySelectorAll('[data-tdcls]').forEach(e => e.onchange = () => {
      S.sell[e.dataset.tdcls] = Math.max(0, Number(e.value) || 0);
      Object.keys(S.sellHold).forEach(k => { delete S.sellHold[k]; });       // a new class amount re-splits everything
      planDirty(); todoRender();
    });
    $('tdSells').querySelectorAll('[data-tdhold]').forEach(e => e.onchange = () => {
      S.sellHold[e.dataset.tdhold] = Math.max(0, Number(e.value) || 0);
      planDirty(); todoRender();
    });

    // buys
    const RES = { OK: ['ok', 'OK'], OVER_PLAN: ['warn', 'Over plan'], SHRUNK: ['warn', 'Cut'], BLOCKED: ['bad', 'Blocked'], WAITING: ['', 'Waiting'], READY: ['buy', 'Has a Buy'] };
    // 2026-11-20, user: just Pick, Amount and a small flag. The flag is empty when all is well; it says "Not saved yet" or warns.
    let b = '<thead><tr><th>Pick</th><th class="n">Amount</th><th>Flag</th></tr></thead><tbody>';
    const saved = {};
    (t.buys || []).forEach(x => x.members.forEach(m => { saved[m] = x; }));
    const onScreen = S.picks.filter(p => p.amt > 0);
    const seen = new Set();
    let rows = 0;
    const flagOf = x => (x && x.result && x.result !== 'OK' && x.result !== 'WAITING' && x.result !== 'READY') ? tdPill('warn', (RES[x.result] || ['', x.result])[1]) + (x.why ? ' <span class="bld-muted">' + esc(x.why) + '</span>' : '') : '';
    onScreen.forEach(p => {
      const x = saved[p.sym];
      seen.add(p.sym);
      rows++;
      const stale = !x || Math.abs((x.amount || 0) - p.amt) > 0.5;
      const flag = stale ? tdPill('warn', 'Not saved yet') + (x ? ' <span class="bld-muted">the saved amount is ' + usd(x.amount || 0) + '</span>' : ' <span class="bld-muted">press Save to put it in the plan</span>') : flagOf(x);
      b += `<tr><td><b>${esc(p.sym)}</b></td><td class="n">${usd(p.amt)}</td><td>${flag}</td></tr>`;
    });
    (t.buys || []).forEach(x => {                      // saved buys that are no longer picked on the screen
      if (x.members.some(m => seen.has(m))) return;
      rows++;
      const names = x.members.map(m => `<b>${esc(m)}</b>`).join(x.members.length > 1 ? ' <span class="bld-muted">or</span> ' : '');
      b += `<tr><td>${names}</td><td class="n">${x.amount ? usd(x.amount) : '-'}</td><td>${tdPill('', 'Saved only')} <span class="bld-muted">in the saved plan, not picked on the screen</span>${flagOf(x) ? ' ' + flagOf(x) : ''}</td></tr>`;
    });
    if (!rows) b += '<tr><td colspan="3" class="bld-muted">No planned buys yet. Picks with room under their Stk Room $ appear here at once and are saved when you press Save.</td></tr>';
    $('tdBuys').innerHTML = b + '</tbody>';
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
      `<div class="bld-muted">Cash ${usd(t.cash)}${t.sell_cash ? ' + ' + usd(t.sell_cash) + ' counted from selling over-target classes' : ''}. Keeps the plan's Cash % and ${usd(t.cash_keep)}. A warning only: nothing is cut.</div></div>`;
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
    $('planDiscard').onclick = async () => {
      if (!window.confirm('Discard your unsaved changes and go back to the saved plan "' + PL.name + '"?')) return;
      await planLoad(PL.name); tickHeldPicks(); renderSourceNames(); schedule(0);
    };
    $('planSaveAs').onclick = () => planSaveAs().catch(e => planNote(esc(e.message), true));
    $('planActivate').onclick = () => planActivate().catch(e => planNote(esc(e.message), true));
    $('planVer').onchange = () => {
      if (PL.dirty && !window.confirm('You have unsaved changes. Open another saved plan and lose them?')) { $('planVer').value = PL.name || ''; return; }
      if ($('planVer').value) planLoad($('planVer').value);
    };
    if (!PL.dirty) planLoad();   // date change / Refresh must not replace unsaved edits with the saved plan
  }

  // Hover help uses the browser's normal tooltip (title), not a drawn popup that
  // changes the page size and makes the screen jump.
  document.addEventListener('mouseover', function (e) {
    const el = e.target.closest && e.target.closest('[data-tip]');
    if (el && !el.title) el.title = el.getAttribute('data-tip');
  });

  // Clicking into a number box selects what is in it, so typing replaces it.
  document.addEventListener('focusin', function (e) {
    const t = e.target;
    if (t && t.tagName === 'INPUT' && t.type === 'number') setTimeout(function () { try { t.select(); } catch (err) { /* ignore */ } }, 0);
  });

  document.addEventListener('DOMContentLoaded', init);
})();
