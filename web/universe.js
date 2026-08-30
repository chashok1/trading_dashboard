// Universe by Sector — real screen (was prototyped as a Claude Artifact
// mockup first; this is the DB-backed version). Fetches /api/universe once
// (symbol-level universe rows + per-account position rows + account
// labels) and does all filtering/aggregation/drilldown client-side, same
// model the prototype used.
//
// Three independent controls: View (size/category/capital — what sizes and
// colors each tile), Filter (all/held/actionable — which symbols count),
// Account (Held only — narrow to one account, or split every tile by
// account). Click any tile to drill into its individual symbols; click a
// symbol to jump to Actionable.
(function () {
  "use strict";

  const $ = id => document.getElementById(id);
  const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmtInt = d3.format(',');
  const fmtUsd = v => (v >= 1000 || v <= -1000) ? (v < 0 ? '-$' : '$') + d3.format(',.0f')(Math.abs(v)) : '$' + Math.round(v);

  function normSector(raw) {
    const s = (raw || '').trim();
    if (!s || s === 'N/A' || s === 'USD') return 'Unclassified';
    if (s.toLowerCase() === 'health care') return 'Health Care';
    return s;
  }

  // ---------------------------------------------------------------------
  // Data load + client-side aggregation
  // ---------------------------------------------------------------------
  let SYMS = [];              // raw symbol rows from the API, sector normalized
  let POS = [];                // raw position rows, sector attached via symbol lookup
  let ACCOUNTS = [];           // [{key, label, total}] sorted by total desc -- total = securities + cash
  let acctLabelMap = new Map();
  let cashByAccount = new Map(); // account_id -> cash $ (no sector -- can't feed a by-sector breakdown)

  let AGG = {};                // AGG[filterKey] = [{sector,count,held,held_value,sample}]
  let SYMS_BY_SECTOR = {};     // SYMS_BY_SECTOR[filterKey][sector] = [symbol rows]
  let HELD_BY_ACCOUNT = {};    // HELD_BY_ACCOUNT[account_id] = [{sector,count,held,held_value,sample}]
  let SECTOR_ACCOUNT = {};     // SECTOR_ACCOUNT[sector] = [{account,count,held_value,sample}]
  let POS_BY_SECTOR_ACCOUNT = {}; // POS_BY_SECTOR_ACCOUNT[sector][account] = [{tos_symbol,market_value}]
  let catAssign = new Map();
  const CAT_SLOTS = ['--cat1', '--cat2', '--cat3', '--cat4', '--cat5', '--cat6', '--cat7', '--cat8', '--cat9'];
  const ACCOUNT_COLOR_SLOTS = ['--cat1', '--cat2', '--cat3', '--cat4', '--cat5'];
  let acctColor = new Map();

  function aggregate(rows) {
    const by = new Map();
    rows.forEach(r => {
      const sector = r.sector;
      if (!by.has(sector)) by.set(sector, { sector, count: 0, held: 0, held_value: 0, sample: [] });
      const a = by.get(sector);
      a.count++;
      if (r.held_today) { a.held++; a.held_value += r.current_position_dollar || 0; }
      if (a.sample.length < 6) a.sample.push(r.tos_symbol);
    });
    return [...by.values()].sort((a, b) => b.count - a.count);
  }

  function build(payload) {
    SYMS = (payload.symbols || []).map(r => ({ ...r, sector: normSector(r.sector) }));
    const sectorOf = new Map(SYMS.map(r => [r.tos_symbol, r.sector]));
    POS = (payload.positions || [])
      .filter(r => r.tos_symbol && sectorOf.has(r.tos_symbol))
      .map(r => ({ ...r, sector: sectorOf.get(r.tos_symbol) }));

    const accts = payload.accounts || [];
    acctLabelMap = new Map(accts.map(a => [a.account_number, a.display_name || a.short_name || a.account_number]));

    AGG.all = aggregate(SYMS);
    AGG.held = aggregate(SYMS.filter(r => r.held_today));
    AGG.actionable = aggregate(SYMS.filter(r => r.final_code && r.final_code !== 'HOLD'));

    SYMS_BY_SECTOR.all = groupBy(SYMS, r => r.sector);
    SYMS_BY_SECTOR.held = groupBy(SYMS.filter(r => r.held_today), r => r.sector);
    SYMS_BY_SECTOR.actionable = groupBy(SYMS.filter(r => r.final_code && r.final_code !== 'HOLD'), r => r.sector);

    // per-account, per-sector aggregation + raw position lists (for
    // account-level drilldown)
    const acctTotals = new Map();
    POS.forEach(r => {
      if (!POS_BY_SECTOR_ACCOUNT[r.sector]) POS_BY_SECTOR_ACCOUNT[r.sector] = {};
      if (!POS_BY_SECTOR_ACCOUNT[r.sector][r.account_id]) POS_BY_SECTOR_ACCOUNT[r.sector][r.account_id] = [];
      POS_BY_SECTOR_ACCOUNT[r.sector][r.account_id].push({ tos_symbol: r.tos_symbol, market_value: r.market_value });
      acctTotals.set(r.account_id, (acctTotals.get(r.account_id) || 0) + r.market_value);

      if (!HELD_BY_ACCOUNT[r.account_id]) HELD_BY_ACCOUNT[r.account_id] = new Map();
      const bySec = HELD_BY_ACCOUNT[r.account_id];
      if (!bySec.has(r.sector)) bySec.set(r.sector, { sector: r.sector, count: 0, held: 0, held_value: 0, sample: [] });
      const a = bySec.get(r.sector);
      a.count++; a.held++; a.held_value += r.market_value || 0;
      if (a.sample.length < 6 && !a.sample.includes(r.tos_symbol)) a.sample.push(r.tos_symbol);

      if (!SECTOR_ACCOUNT[r.sector]) SECTOR_ACCOUNT[r.sector] = new Map();
      const bySA = SECTOR_ACCOUNT[r.sector];
      if (!bySA.has(r.account_id)) bySA.set(r.account_id, { account: r.account_id, count: 0, held: 0, held_value: 0, sample: [] });
      const b = bySA.get(r.account_id);
      b.count++; b.held++; b.held_value += r.market_value || 0;
      if (b.sample.length < 6 && !b.sample.includes(r.tos_symbol)) b.sample.push(r.tos_symbol);
    });
    Object.keys(HELD_BY_ACCOUNT).forEach(k => { HELD_BY_ACCOUNT[k] = [...HELD_BY_ACCOUNT[k].values()].sort((a, b) => b.held_value - a.held_value); });
    Object.keys(SECTOR_ACCOUNT).forEach(k => { SECTOR_ACCOUNT[k] = [...SECTOR_ACCOUNT[k].values()]; });

    // Cash folded into every account's total (not just cash-only ones) --
    // an account's real size is securities + cash, and a 100%-cash account
    // (e.g. Designated_Bene_Individual ...100, "A") would otherwise have
    // zero POS rows and never even appear in ACCOUNTS at all, rather than
    // showing up with $0 securities.
    cashByAccount = new Map((payload.cash_by_account || []).map(r => [r.account_id, r.cash_value || 0]));
    cashByAccount.forEach((cashVal, acctId) => {
      acctTotals.set(acctId, (acctTotals.get(acctId) || 0) + cashVal);
    });

    ACCOUNTS = [...acctTotals.entries()]
      .map(([key, total]) => ({ key, label: acctLabelMap.get(key) || key, total }))
      .sort((a, b) => b.total - a.total);
    acctColor = new Map(ACCOUNTS.map((a, i) => [a.key, ACCOUNT_COLOR_SLOTS[i % ACCOUNT_COLOR_SLOTS.length]]));

    // categorical assignment — ranked on the FULL ("all") universe so a
    // sector's color stays the same across filters
    const ranked = AGG.all.filter(d => d.sector !== 'Unclassified').sort((a, b) => b.count - a.count);
    catAssign = new Map();
    ranked.forEach((d, i) => catAssign.set(d.sector, i < CAT_SLOTS.length ? CAT_SLOTS[i] : '--cat-unmapped'));
    catAssign.set('Unclassified', '--cat-unmapped');

    return { ranked };
  }

  function groupBy(rows, keyFn) {
    const m = {};
    rows.forEach(r => { const k = keyFn(r); (m[k] = m[k] || []).push(r); });
    return m;
  }

  // ---------------------------------------------------------------------
  // Views / filters
  // ---------------------------------------------------------------------
  // 2026-08-30: color is 'cat' (sector identity, catAssign) everywhere now
  // -- user: "keep sector colors consistent everywhere". Follow-up: "By
  // size" and "By category" had become identical once color stopped
  // distinguishing them (both sized AND colored by count) -- merged into
  // one "By Count" view (key kept as `count`, was `size`; `category`
  // dropped). "By Account" is NOT in this object -- it's account-primary,
  // not sector-primary, and gets its own render path (renderAccountView)
  // since it doesn't share VIEWS' {value,color,data} shape (sector rows).
  const VIEWS = {
    count:   { value: d => d.count, color: 'cat', data: base => base },
    capital: { value: d => d.held_value, color: 'cat', data: base => base.filter(d => d.held_value > 0) },
  };
  let FILTERS = {};

  function luminance(hex) {
    const c = d3.rgb(hex);
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  const labelColorFor = hex => luminance(hex) > 0.42 ? '#1c1917' : '#ffffff';

  const svg = d3.select('#uvTm');
  const tt = $('uvTt');

  // ---------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------
  let currentView = 'count', currentFilter = 'all', currentAccount = 'all', splitByAccount = false;
  // drill = null (root) or { sector?, account? } (at least one set) — set
  // on tile click, cleared whenever view/filter/account/split changes
  // underneath it.
  let drill = null;

  function resetDrill() { drill = null; }

  function render() {
    document.querySelectorAll('.uv-tab[data-view]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.view === currentView)));
    document.querySelectorAll('.uv-tab[data-filter]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.filter === currentFilter)));

    // "By Account" is account-primary, not sector-primary -- doesn't share
    // VIEWS' {value,color,data} shape, so it gets its own render path
    // entirely (renderAccountView) rather than being squeezed into the
    // logic below.
    if (currentView === 'account') { renderAccountView(); return; }

    const view = VIEWS[currentView];
    const filter = FILTERS[currentFilter];

    const acctRow = $('uvAcctRow');
    acctRow.hidden = currentFilter !== 'held';
    if (currentFilter !== 'held') currentAccount = 'all';
    document.querySelectorAll('.uv-tab[data-acct]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.acct === currentAccount)));

    const base = (currentFilter === 'held' && currentAccount !== 'all')
      ? HELD_BY_ACCOUNT[currentAccount] || []
      : filter.data;
    const data = view.data(base);

    $('uvTotalCount').textContent = fmtInt(d3.sum(base, d => d.count));
    $('uvTotalSectors').textContent = base.length;
    $('uvSectorsUnit').textContent = 'sectors';
    $('uvSHeld').textContent = d3.sum(base, d => d.held) + ' symbols';
    $('uvSCapital').textContent = fmtUsd(d3.sum(base, d => d.held_value));
    const acctNote = (currentFilter === 'held' && currentAccount !== 'all') ? `in ${acctLabelMap.get(currentAccount) || currentAccount} only` : filter.note;
    $('uvFilterCount').textContent = (currentFilter === 'all' && currentAccount === 'all') ? '' : `— ${acctNote}`;

    const canSplit = currentFilter === 'held' && currentAccount === 'all';
    $('uvSplitToggleWrap').hidden = !canSplit;
    if (!canSplit) splitByAccount = false;
    $('uvSplitToggle').checked = splitByAccount;

    renderCrumbs();
    $('uvSideHeading').textContent = 'Top sectors';

    const wrap = document.querySelector('.uv-svg-wrap');
    const W = wrap.clientWidth, H = wrap.clientHeight;
    svg.attr('viewBox', `0 0 ${W} ${H}`);

    if (data.length === 0 && !drill) {
      svg.selectAll('*').remove();
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text('No symbols match this filter + view combination.');
      hideAllLegends();
      $('uvRankList').innerHTML = ''; $('uvSLargest').textContent = '—';
      return;
    }

    if (drill) {
      renderDrill(drill, W, H);
    } else if (splitByAccount && canSplit) {
      renderNested(view, data, W, H);
    } else {
      renderFlat(view, data, W, H);
    }

    // side panel — top sectors (unaffected by drill/split)
    const ranklist = $('uvRankList');
    const top = [...data].sort((a, b) => view.value(b) - view.value(a)).slice(0, 8);
    ranklist.innerHTML = top.map(d => {
      const dot = cssVar(catAssign.get(d.sector) || '--cat-unmapped');
      const val = currentView === 'capital' ? fmtUsd(d.held_value) : fmtInt(d.count);
      return `<li class="uv-rank-row"><span class="uv-rank-dot" style="background:${dot};"></span>` +
        `<span class="uv-rank-name">${esc(d.sector)}</span><span class="uv-rank-val">${val}</span></li>`;
    }).join('');
    $('uvSLargest').textContent = top[0] ? top[0].sector : '—';
  }

  // ---- "By Account" — account-primary treemap (tiles = accounts, not
  // sectors), only meaningful for held positions so this view forces
  // Filter=Held (see wireStaticControls). Its own drilldown is symbols
  // held in that account across ALL sectors (drill = {account} only, no
  // sector) -- see renderDrill's third branch. ------------------------
  function renderAccountView() {
    document.querySelectorAll('.uv-tab[data-filter]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.filter === 'held')));
    $('uvAcctRow').hidden = true; // the account SELECTOR doesn't add anything once this whole view is account-primary

    const totalHeldSymbols = d3.sum(Object.values(HELD_BY_ACCOUNT), rows => d3.sum(rows, r => r.held));
    $('uvTotalCount').textContent = fmtInt(totalHeldSymbols);
    $('uvTotalSectors').textContent = ACCOUNTS.length;
    $('uvSectorsUnit').textContent = 'accounts';
    $('uvSHeld').textContent = totalHeldSymbols + ' symbols';
    $('uvSCapital').textContent = fmtUsd(d3.sum(ACCOUNTS, a => a.total));
    $('uvFilterCount').textContent = '— by account';

    renderCrumbs();
    $('uvSideHeading').textContent = 'Top accounts';

    const wrap = document.querySelector('.uv-svg-wrap');
    const W = wrap.clientWidth, H = wrap.clientHeight;
    svg.attr('viewBox', `0 0 ${W} ${H}`);

    if (ACCOUNTS.length === 0 && !drill) {
      svg.selectAll('*').remove();
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text('No held positions to break out by account.');
      hideAllLegends();
      $('uvRankList').innerHTML = ''; $('uvSLargest').textContent = '—';
      return;
    }

    if (drill) {
      renderDrill(drill, W, H);
    } else {
      renderAccountFlat(W, H);
    }

    const ranklist = $('uvRankList');
    ranklist.innerHTML = ACCOUNTS.slice(0, 8).map(a => {
      const dot = cssVar(acctColor.get(a.key));
      return `<li class="uv-rank-row"><span class="uv-rank-dot" style="background:${dot};"></span>` +
        `<span class="uv-rank-name">${esc(a.label)}</span><span class="uv-rank-val">${fmtUsd(a.total)}</span></li>`;
    }).join('');
    $('uvSLargest').textContent = ACCOUNTS[0] ? ACCOUNTS[0].label : '—';
  }

  function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  // Greedy word-wrap for the small sample-ticker line(s) on a tile -- SVG
  // <text> doesn't wrap on its own, so this pre-splits the token list into
  // up to maxLines strings that each fit charsPerLine (a rough px-width ->
  // char-count estimate, not exact font metrics; good enough at this size).
  // Excess tokens beyond what fits are simply dropped -- the tooltip
  // already shows the full sample list on hover.
  function wrapTokens(tokens, charsPerLine, maxLines) {
    const lines = []; let cur = '';
    for (const t of tokens) {
      const candidate = cur ? cur + ' ' + t : t;
      if (candidate.length <= charsPerLine) { cur = candidate; continue; }
      if (cur) lines.push(cur);
      if (lines.length >= maxLines) return lines.slice(0, maxLines);
      cur = t;
    }
    if (cur) lines.push(cur);
    return lines.slice(0, maxLines);
  }
  function hideAllLegends() { $('uvLegendCat').hidden = true; $('uvLegendAcct').hidden = true; }

  function renderCrumbs() {
    const el = $('uvCrumbs');
    if (!drill) { el.innerHTML = ''; return; }
    const parts = [`<span class="uv-crumb" data-crumb="root">Universe</span>`, `<span class="uv-crumb-sep">/</span>`];
    const label = (drill.sector && drill.account) ? `${esc(drill.sector)} · ${esc(acctLabelMap.get(drill.account) || drill.account)}`
      : drill.account ? esc(acctLabelMap.get(drill.account) || drill.account)
      : esc(drill.sector);
    parts.push(`<span class="uv-crumb current">${label}</span>`);
    el.innerHTML = parts.join('');
    el.querySelectorAll('[data-crumb="root"]').forEach(e => e.addEventListener('click', () => { drill = null; render(); }));
  }

  // ---- flat, single-level treemap ---------------------------------------
  function renderFlat(view, data, W, H) {
    const root = d3.hierarchy({ children: data }).sum(view.value).sort((a, b) => b.value - a.value);
    d3.treemap().size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    // Color is always sector identity now (catAssign) -- see VIEWS' own
    // comment on why the sequential magnitude ramp was dropped.
    hideAllLegends();
    $('uvLegendCat').hidden = false;
    const colorFn = d => cssVar(catAssign.get(d.sector) || '--cat-unmapped');
    const ranked = AGG.all.filter(d => d.sector !== 'Unclassified').sort((a, b) => b.count - a.count);
    $('uvLegendCat').innerHTML = ranked.slice(0, CAT_SLOTS.length).map((d, i) =>
      `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar(CAT_SLOTS[i])};"></span>${esc(d.sector)}</span>`
    ).join('') + `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar('--cat-unmapped')};"></span>Other / unclassified</span>`;

    const leaves = root.leaves();
    svg.selectAll('*').remove();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => colorFn(d.data));

    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      if (w < 46 || h < 26) return;
      const fill = colorFn(d.data); const ink = labelColorFor(fill);
      const g = d3.select(this); const name = d.data.sector;
      g.append('text').attr('class', 'uv-c-name').attr('x', 7).attr('y', 16)
        .attr('font-size', w < 90 ? 9.5 : 11).attr('fill', ink)
        .text(name.length > (w / 6) ? name.slice(0, Math.max(3, Math.floor(w / 6.2))) + '…' : name);
      // count + capital together (was one or the other depending on view) --
      // user wants both on the tile, not just whichever matches this view's
      // color job.
      if (h > 40) {
        g.append('text').attr('class', 'uv-c-sub').attr('x', 7).attr('y', 30)
          .attr('font-size', 9.5).attr('fill', ink).attr('opacity', 0.85)
          .text(`${fmtInt(d.data.count)} sym · ${fmtUsd(d.data.held_value)}`);
      }
      // sample tickers, smaller + more muted, wrapped onto up to 2 lines
      // when the tile has room -- see wrapTokens.
      if (h > 56 && w > 70 && d.data.sample && d.data.sample.length) {
        const maxLines = h > 74 ? 2 : 1;
        const charsPerLine = Math.max(6, Math.floor((w - 10) / 4.3));
        wrapTokens(d.data.sample, charsPerLine, maxLines).forEach((line, i) => {
          g.append('text').attr('x', 7).attr('y', 43 + i * 10)
            .attr('font-size', 7.5).attr('fill', ink).attr('opacity', 0.62).text(line);
        });
      }
    });

    cell.on('mousemove', (evt, d) => {
      const heldPct = d.data.count ? Math.round((d.data.held / d.data.count) * 100) : 0;
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.sector)}</div>` +
        `<div class="uv-tt-row"><span>Symbols</span><span>${fmtInt(d.data.count)}</span></div>` +
        `<div class="uv-tt-row"><span>Held</span><span>${d.data.held} (${heldPct}%)</span></div>` +
        `<div class="uv-tt-row"><span>Capital</span><span>${fmtUsd(d.data.held_value)}</span></div>` +
        `<div class="uv-tt-syms">${d.data.sample.map(esc).join(' · ')}${d.data.count > d.data.sample.length ? ' …' : ''}</div>` +
        `<div class="uv-tt-hint">Click to see symbols</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => { drill = { sector: d.data.sector }; render(); });
  }

  // ---- nested (split-by-account) treemap ---------------------------------
  function renderNested(view, data, W, H) {
    hideAllLegends();
    const legendAcct = $('uvLegendAcct');
    legendAcct.hidden = false;
    legendAcct.innerHTML = ACCOUNTS.map(a =>
      `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar(acctColor.get(a.key))};"></span>${esc(a.label)}</span>`
    ).join('');

    const sectorsInView = new Set(data.map(d => d.sector));
    const groups = Object.keys(SECTOR_ACCOUNT)
      .filter(s => sectorsInView.has(s))
      .map(sector => ({ sector, children: SECTOR_ACCOUNT[sector].filter(a => view.value(a) > 0) }))
      .filter(g => g.children.length > 0);

    const root = d3.hierarchy({ children: groups }).sum(view.value).sort((a, b) => b.value - a.value);
    d3.treemap().size([W, H]).paddingOuter(2).paddingTop(d => d.depth === 1 ? 17 : 0).paddingInner(2).round(true)(root);

    svg.selectAll('*').remove();

    const groupNode = svg.selectAll('g.uv-grp').data(root.children || []).join('g')
      .attr('class', 'uv-grp').attr('transform', d => `translate(${d.x0},${d.y0})`).style('cursor', 'pointer');
    groupNode.append('rect').attr('class', 'uv-grp-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0)).attr('rx', 4);
    groupNode.append('text').attr('class', 'uv-grp-label').attr('x', 6).attr('y', 12).attr('font-size', 10)
      .text(d => { const w = d.x1 - d.x0, name = d.data.sector; return name.length > w / 5.6 ? name.slice(0, Math.max(3, Math.floor(w / 6))) + '…' : name; });
    groupNode.on('click', (evt, d) => { evt.stopPropagation(); drill = { sector: d.data.sector }; render(); });

    const leaves = root.leaves();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 2).attr('fill', d => cssVar(acctColor.get(d.data.account)));

    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      if (w < 40 || h < 20) return;
      const fill = cssVar(acctColor.get(d.data.account)); const ink = labelColorFor(fill);
      const label = acctLabelMap.get(d.data.account) || d.data.account;
      d3.select(this).append('text').attr('x', 5).attr('y', 13).attr('font-size', 9).attr('font-weight', 700)
        .attr('fill', ink).text(w < 60 ? String(label).slice(0, 4) : label);
    });

    cell.on('mousemove', (evt, d) => {
      const label = acctLabelMap.get(d.data.account) || d.data.account;
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.sector)} · ${esc(label)}</div>` +
        `<div class="uv-tt-row"><span>Capital</span><span>${fmtUsd(d.data.held_value)}</span></div>` +
        `<div class="uv-tt-syms">${d.data.sample.map(esc).join(' · ')}${d.data.count > d.data.sample.length ? ' …' : ''}</div>` +
        `<div class="uv-tt-hint">Click to see symbols</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => { evt.stopPropagation(); drill = { sector: d.data.sector, account: d.data.account }; render(); });
  }

  // ---- "By Account" top level: tiles = accounts (not sectors), sized +
  // colored by acctColor. Click drills into that account's symbols across
  // every sector (drill = {account} only) -- see renderDrill's 2nd branch.
  function renderAccountFlat(W, H) {
    hideAllLegends();
    const legendAcct = $('uvLegendAcct');
    legendAcct.hidden = false;
    legendAcct.innerHTML = ACCOUNTS.map(a =>
      `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar(acctColor.get(a.key))};"></span>${esc(a.label)}</span>`
    ).join('');

    const root = d3.hierarchy({ children: ACCOUNTS }).sum(d => d.total).sort((a, b) => b.value - a.value);
    d3.treemap().size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    svg.selectAll('*').remove();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => cssVar(acctColor.get(d.data.key)));

    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      if (w < 46 || h < 26) return;
      const fill = cssVar(acctColor.get(d.data.key)); const ink = labelColorFor(fill);
      const g = d3.select(this); const name = d.data.label;
      g.append('text').attr('class', 'uv-c-name').attr('x', 7).attr('y', 16)
        .attr('font-size', w < 90 ? 9.5 : 11).attr('fill', ink)
        .text(name.length > (w / 6) ? name.slice(0, Math.max(3, Math.floor(w / 6.2))) + '…' : name);
      if (h > 40) {
        const sectorCount = (HELD_BY_ACCOUNT[d.data.key] || []).length;
        const sub = sectorCount > 0
          ? `${fmtUsd(d.data.total)} · ${sectorCount} sector${sectorCount === 1 ? '' : 's'}`
          : `${fmtUsd(d.data.total)} · all cash`;
        g.append('text').attr('class', 'uv-c-sub').attr('x', 7).attr('y', 30)
          .attr('font-size', 9.5).attr('fill', ink).attr('opacity', 0.85).text(sub);
      }
    });

    cell.on('mousemove', (evt, d) => {
      const sectorCount = (HELD_BY_ACCOUNT[d.data.key] || []).length;
      const cashVal = cashByAccount.get(d.data.key) || 0;
      const securitiesVal = d.data.total - cashVal;
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.label)}</div>` +
        `<div class="uv-tt-row"><span>Total</span><span>${fmtUsd(d.data.total)}</span></div>` +
        `<div class="uv-tt-row"><span>Securities</span><span>${fmtUsd(securitiesVal)}</span></div>` +
        `<div class="uv-tt-row"><span>Cash</span><span>${fmtUsd(cashVal)}</span></div>` +
        `<div class="uv-tt-row"><span>Sectors</span><span>${sectorCount}</span></div>` +
        `<div class="uv-tt-hint">${sectorCount > 0 ? 'Click to see symbols' : 'No securities held'}</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => { if ((HELD_BY_ACCOUNT[d.data.key] || []).length > 0) { drill = { account: d.data.key }; render(); } });
  }

  // ---- drilldown: individual symbols within a sector (± account) --------
  function renderDrill(drillState, W, H) {
    hideAllLegends();
    let rows, color, unit;
    if (drillState.sector && drillState.account) {
      // sector + account (from the split-by-account nested treemap)
      const posList = (POS_BY_SECTOR_ACCOUNT[drillState.sector] || {})[drillState.account] || [];
      rows = posList.map(r => ({ tos_symbol: r.tos_symbol, value: r.market_value }));
      color = cssVar(acctColor.get(drillState.account));
      unit = 'capital';
    } else if (drillState.account) {
      // account only (from "By Account") -- flatten that account's
      // positions across every sector, not just one.
      let flat = [];
      Object.keys(POS_BY_SECTOR_ACCOUNT).forEach(sector => {
        const list = POS_BY_SECTOR_ACCOUNT[sector][drillState.account];
        if (list) flat = flat.concat(list);
      });
      rows = flat.map(r => ({ tos_symbol: r.tos_symbol, value: r.market_value }));
      color = cssVar(acctColor.get(drillState.account));
      unit = 'capital';
    } else {
      const symRows = (SYMS_BY_SECTOR[currentFilter] || {})[drillState.sector] || [];
      const useCapital = currentFilter === 'held';
      rows = symRows.map(r => ({ tos_symbol: r.tos_symbol, value: useCapital ? (r.current_position_dollar || 0) : 1 }));
      unit = useCapital ? 'capital' : 'count';
      color = cssVar(catAssign.get(drillState.sector) || '--cat-unmapped');
    }
    if (unit === 'count') rows = rows.map(r => ({ ...r, value: 1 }));

    const root = d3.hierarchy({ children: rows }).sum(d => Math.max(d.value, 0.0001)).sort((a, b) => b.value - a.value);
    d3.treemap().size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    svg.selectAll('*').remove();
    const leaves = root.leaves();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', color);

    const ink = labelColorFor(color);
    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      if (w < 30 || h < 18) return;
      const g = d3.select(this);
      g.append('text').attr('class', 'uv-c-name').attr('x', 5).attr('y', 13)
        .attr('font-size', w < 60 ? 9 : 10.5).attr('fill', ink).text(d.data.tos_symbol);
      if (h > 32 && unit === 'capital') {
        g.append('text').attr('class', 'uv-c-sub').attr('x', 5).attr('y', 26)
          .attr('font-size', 9).attr('fill', ink).attr('opacity', 0.85).text(fmtUsd(d.data.value));
      }
    });

    cell.on('mousemove', (evt, d) => {
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.tos_symbol)}</div>` +
        (unit === 'capital' ? `<div class="uv-tt-row"><span>Value</span><span>${fmtUsd(d.data.value)}</span></div>` : '') +
        `<div class="uv-tt-hint">Click to open in Actionable</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => { window.location.href = '/actionable?symbol=' + encodeURIComponent(d.data.tos_symbol); });
  }

  // ---------------------------------------------------------------------
  // Wiring
  // ---------------------------------------------------------------------
  function wireStaticControls() {
    document.querySelectorAll('.uv-tab[data-view]').forEach(t =>
      t.addEventListener('click', () => {
        currentView = t.dataset.view;
        // "By Account" only means anything for held positions.
        if (currentView === 'account') currentFilter = 'held';
        resetDrill(); render();
      }));
    document.querySelectorAll('.uv-tab[data-filter]').forEach(t =>
      t.addEventListener('click', () => {
        currentFilter = t.dataset.filter; currentAccount = 'all';
        // leaving Held with "By Account" active means there's nothing left
        // to show it against -- fall back to the default view.
        if (currentFilter !== 'held' && currentView === 'account') currentView = 'count';
        resetDrill(); render();
      }));
    $('uvSplitToggle').addEventListener('change', e => { splitByAccount = e.target.checked; resetDrill(); render(); });
    window.addEventListener('resize', () => render());
  }

  function wireAccountTabs() {
    const acctTabs = $('uvAcctTabs');
    acctTabs.innerHTML = '<button class="uv-tab" role="tab" data-acct="all" aria-selected="true">All accounts</button>' +
      ACCOUNTS.map(a => `<button class="uv-tab" role="tab" data-acct="${esc(a.key)}" aria-selected="false" title="$${Math.round(a.total).toLocaleString()}">${esc(a.label)}</button>`).join('');
    document.querySelectorAll('.uv-tab[data-acct]').forEach(t =>
      t.addEventListener('click', () => { currentAccount = t.dataset.acct; resetDrill(); render(); }));
  }

  async function init() {
    let payload;
    try {
      const resp = await fetch('/api/universe');
      payload = await resp.json();
    } catch (e) {
      console.error('Failed to load /api/universe:', e);
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', '#b91c1c').attr('font-size', 12)
        .text('Failed to load universe data — see console.');
      return;
    }
    build(payload);
    FILTERS = {
      all:        { note: 'every tracked symbol', data: AGG.all },
      held:       { note: 'symbols with an open position', data: AGG.held },
      actionable: { note: 'symbols with a live signal today', data: AGG.actionable },
    };
    $('uvAsOf').textContent = new Date().toLocaleDateString();
    wireAccountTabs();
    wireStaticControls();
    render();
  }

  init();
})();
