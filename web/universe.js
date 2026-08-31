// Universe by Sector — real screen (was prototyped as a Claude Artifact
// mockup first; this is the DB-backed version). Fetches /api/universe once
// (symbol-level universe rows + per-account position rows + account
// labels) and does all filtering/aggregation/drilldown client-side, same
// model the prototype used.
//
// 2026-08-30 consolidation: was 4 top-level views (By Count / By Capital /
// By Account / By Asset Class) — By Count and By Capital were the SAME
// sector-primary tree, just sized by a different number, and By Account's
// drilldown was flat (account -> symbols, no grouping underneath). User:
// "Do i need 'By Count' any more? and can't 'By Capital', 'By account'
// drill down to asset class and the rest follows" — collapsed to 2 entry
// points that share one hierarchy and one size control:
//   By Asset Class:  Asset Class -> Sector (Equities only) -> Symbol
//   By Account:      Account -> Asset Class -> Sector (Equities only) -> Symbol
// "Size" (Count/Capital) is now an independent toggle applied at every
// level of either hierarchy, instead of being baked into separate tabs.
// The old "split each sector tile by account" nested view is dropped —
// By Account now covers that angle on its own, more completely (it groups
// by asset class + sector under the account too, not just a flat symbol
// list), so a diagonal sector-split-by-account cut isn't needed alongside it.
//
// Independent controls: View (Asset Class / Account — which hierarchy),
// Size (Count/Capital — what sizes every tile), Filter (all/held/
// actionable — which symbols count), Color (buy/sell/hold — narrows
// drilldown tiles), Style (one style tag — narrows drilldown tiles). Click
// any group tile to drill in; click a symbol tile to jump to Actionable.
(function () {
  "use strict";

  const $ = id => document.getElementById(id);
  const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmtInt = d3.format(',');
  const fmtUsd = v => (v >= 1000 || v <= -1000) ? (v < 0 ? '-$' : '$') + d3.format(',.0f')(Math.abs(v)) : '$' + Math.round(v);

  // isMacro (is_macro_instrument from drv_actionable) peels real futures/
  // FX/index instruments (/GC, SPX, /6E, foreign indices, etc.) into their
  // own bucket instead of "Unclassified" -- they have no GICS sector by
  // nature, unlike the much larger set of ordinary stocks that land in
  // Unclassified only because `sector` happens to be unpopulated for them
  // in the reference data (a real data gap, not this screen's doing --
  // still fully visible via Unclassified's own drilldown, just not split
  // further).
  function normSector(raw, isMacro) {
    const s = (raw || '').trim();
    if (!s || s === 'N/A' || s === 'USD') return isMacro ? 'Futures / FX / Macro' : 'Unclassified';
    if (s.toLowerCase() === 'health care') return 'Health Care';
    return s;
  }
  // asset_class arrives already merged/normalized by the backend
  // (_norm_asset_class) -- this just supplies the "Unclassified" fallback
  // for the ~43% of the universe with no asset-class data (same
  // reference-data gap "Unclassified" sectors come from).
  function normAssetClass(raw) {
    const s = (raw || '').trim();
    return s || 'Unclassified';
  }

  // ---------------------------------------------------------------------
  // Data load + client-side aggregation
  // ---------------------------------------------------------------------
  let SYMS = [];              // raw symbol rows from the API, sector/asset_class normalized
  let POS = [];                // raw position rows, sector + asset_class attached via symbol lookup
  let ACCOUNTS = [];           // [{key,label,total,posCount}] sorted by total desc -- total = securities + cash
  let acctLabelMap = new Map();
  let cashByAccount = new Map(); // account_id -> cash $ (no sector -- can't feed a by-sector breakdown)
  // tos_symbol -> full SYMS row (final_code, last_price, trade/trend line
  // values, lrr/trr, style_tags) -- position rows (account drilldowns)
  // don't carry any of this themselves, only {tos_symbol, market_value},
  // so drilldown tiles look it up here regardless of which drill path
  // produced them.
  let symbolDetail = new Map();

  let catAssign = new Map();          // sector -> --catN, ranked once on the whole universe (stable across filters/drills)
  let assetColorAssign = new Map();   // asset_class -> --catN, same pattern
  let SECTOR_RANK = [];                // ranked sector aggregate, whole universe, excl. Unclassified -- feeds catAssign + every sector legend
  let ASSET_RANK = [];                 // same for asset classes
  const CAT_SLOTS = ['--cat1', '--cat2', '--cat3', '--cat4', '--cat5', '--cat6', '--cat7', '--cat8', '--cat9'];
  const ACCOUNT_COLOR_SLOTS = ['--cat1', '--cat2', '--cat3', '--cat4', '--cat5'];
  let acctColor = new Map();
  let ALL_STYLE_TAGS = [];      // sorted unique style labels across the whole universe

  // keyField names the output property (e.g. 'sector' or 'asset_class') so
  // callers get the same {sector,count,...} / {asset_class,count,...}
  // shape aggregate() always returned, just keyed by whichever dimension.
  function aggregateBy(rows, keyField, keyFn) {
    const by = new Map();
    rows.forEach(r => {
      const key = keyFn(r);
      if (!by.has(key)) by.set(key, { [keyField]: key, count: 0, held: 0, held_value: 0, sample: [] });
      const a = by.get(key);
      a.count++;
      if (r.held_today) { a.held++; a.held_value += r.current_position_dollar || 0; }
      if (a.sample.length < 6) a.sample.push(r.tos_symbol);
    });
    return [...by.values()].sort((a, b) => b.count - a.count);
  }
  const aggregate = rows => aggregateBy(rows, 'sector', r => r.sector);

  // Adapts a POS row (per-account position: tos_symbol/account_id/sector/
  // asset_class/market_value -- sector+asset_class attached in build()) to
  // the shape SYMS rows already have, so the exact same aggregation/
  // hierarchy code below serves both the whole-universe ("By Asset Class")
  // and the per-account ("By Account", once an account is picked)
  // hierarchies without a second code path.
  function posAsSymRow(r) {
    return { tos_symbol: r.tos_symbol, sector: r.sector, asset_class: r.asset_class, held_today: true, current_position_dollar: r.market_value };
  }

  // Builds the Asset Class -> Sector (Equities only) -> Symbol grouping for
  // an arbitrary list of symbol-shaped rows. `sectorByAsset`/
  // `symsByAssetSector` only really matter for 'Equities' -- other asset
  // classes don't have a GICS sector to sub-split by (their rows mostly
  // land in one 'Unclassified' sector bucket, which the client just skips
  // past, going straight asset class -> symbols).
  function buildAssetHierarchy(rows) {
    const agg = aggregateBy(rows, 'asset_class', r => r.asset_class);
    const byAsset = groupBy(rows, r => r.asset_class);
    const sectorByAsset = {};
    const symsByAssetSector = {};
    Object.keys(byAsset).forEach(ac => {
      const acRows = byAsset[ac];
      sectorByAsset[ac] = aggregate(acRows);
      symsByAssetSector[ac] = groupBy(acRows, r => r.sector);
    });
    return { agg, byAsset, sectorByAsset, symsByAssetSector };
  }

  function groupBy(rows, keyFn) {
    const m = {};
    rows.forEach(r => { const k = keyFn(r); (m[k] = m[k] || []).push(r); });
    return m;
  }

  function build(payload) {
    SYMS = (payload.symbols || []).map(r => ({
      ...r,
      sector: normSector(r.sector, r.is_macro_instrument),
      asset_class: normAssetClass(r.asset_class),
      style_tags: r.style_tags || [],
    }));
    const sectorOf = new Map(SYMS.map(r => [r.tos_symbol, r.sector]));
    const assetClassOf = new Map(SYMS.map(r => [r.tos_symbol, r.asset_class]));
    symbolDetail = new Map(SYMS.map(r => [r.tos_symbol, r]));
    POS = (payload.positions || [])
      .filter(r => r.tos_symbol && sectorOf.has(r.tos_symbol))
      .map(r => ({ ...r, sector: sectorOf.get(r.tos_symbol), asset_class: assetClassOf.get(r.tos_symbol) || 'Unclassified' }));

    const accts = payload.accounts || [];
    acctLabelMap = new Map(accts.map(a => [a.account_number, a.display_name || a.short_name || a.account_number]));

    // Style filter's own tab list -- every distinct tag seen anywhere in
    // the universe (not narrowed by the current Filter tab, so the list of
    // available styles doesn't shuffle as you switch All/Held/Actionable).
    const styleSet = new Set();
    SYMS.forEach(r => r.style_tags.forEach(t => styleSet.add(t)));
    ALL_STYLE_TAGS = [...styleSet].sort();

    // Per-account totals (securities from POS + cash, folded together) and
    // position counts, for the "By Account" root level.
    const acctTotals = new Map();
    const posCounts = new Map();
    POS.forEach(r => {
      acctTotals.set(r.account_id, (acctTotals.get(r.account_id) || 0) + (r.market_value || 0));
      posCounts.set(r.account_id, (posCounts.get(r.account_id) || 0) + 1);
    });
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
      .map(([key, total]) => ({ key, label: acctLabelMap.get(key) || key, total, posCount: posCounts.get(key) || 0 }))
      .sort((a, b) => b.total - a.total);
    acctColor = new Map(ACCOUNTS.map((a, i) => [a.key, ACCOUNT_COLOR_SLOTS[i % ACCOUNT_COLOR_SLOTS.length]]));

    // categorical color assignment — ranked on the FULL universe so a
    // sector's / asset class's color stays the same across filters, drills
    // and accounts. 'Unclassified' forced to the neutral unmapped slot.
    SECTOR_RANK = aggregate(SYMS).filter(d => d.sector !== 'Unclassified').sort((a, b) => b.count - a.count);
    catAssign = new Map();
    SECTOR_RANK.forEach((d, i) => catAssign.set(d.sector, i < CAT_SLOTS.length ? CAT_SLOTS[i] : '--cat-unmapped'));
    catAssign.set('Unclassified', '--cat-unmapped');

    ASSET_RANK = aggregateBy(SYMS, 'asset_class', r => r.asset_class).filter(d => d.asset_class !== 'Unclassified').sort((a, b) => b.count - a.count);
    assetColorAssign = new Map();
    ASSET_RANK.forEach((d, i) => assetColorAssign.set(d.asset_class, i < CAT_SLOTS.length ? CAT_SLOTS[i] : '--cat-unmapped'));
    assetColorAssign.set('Unclassified', '--cat-unmapped');
  }

  // ---------------------------------------------------------------------
  // Colors / formulas shared by every tile level
  // ---------------------------------------------------------------------
  function luminance(hex) {
    const c = d3.rgb(hex);
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  const labelColorFor = hex => luminance(hex) > 0.42 ? '#1c1917' : '#ffffff';

  // Per-symbol color for the drilldown level (individual tickers) -- the
  // trading signal (final_code), not a decorative hash. The app's own
  // documented action palette (web/styles.css's "single source of truth"
  // comment), same 6-tier buy/sell strength + neutral every action badge
  // elsewhere in the app already uses.
  const ACTION_COLOR = {
    BM: '--act-buy-strong',
    BS: '--act-buy', INCREASE: '--act-buy',
    BMN: '--act-buy-weak', ADD: '--act-buy-weak', BW: '--act-buy-weak', BSW: '--act-buy-weak',
    SA: '--act-sell-strong', REMOVE: '--act-sell-strong',
    SS: '--act-sell', STM: '--act-sell', REDUCE: '--act-sell', SO: '--act-sell',
    SW: '--act-sell-weak', SWW: '--act-sell-weak',
  };
  const ACTION_LABEL = {
    BM: 'Buy More', BS: 'Buy Some', BMN: 'Buy To Min', INCREASE: 'Increase', ADD: 'Add',
    BW: 'Buy Watch', BSW: 'Buy Some Watch',
    SA: 'Sell All', SS: 'Sell Some', STM: 'Sell/Trim', REDUCE: 'Reduce', SO: 'Sell (Over Max)',
    SW: 'Sell Watch', SWW: 'Sell Watch', REMOVE: 'Remove',
    HOLD: 'Hold',
  };
  function actionColor(code) { return cssVar(ACTION_COLOR[code] || '--act-neutral'); }
  function actionLabel(code) { return ACTION_LABEL[code] || 'Hold'; }
  // 'buy' | 'sell' | 'hold' -- same grouping as ACTION_COLOR, coarsened to
  // 3 buckets for the Color filter (all 3 buy tiers count as "Buy", etc.).
  function actionSide(code) {
    const slot = ACTION_COLOR[code];
    if (slot === '--act-buy-strong' || slot === '--act-buy' || slot === '--act-buy-weak') return 'buy';
    if (slot === '--act-sell-strong' || slot === '--act-sell' || slot === '--act-sell-weak') return 'sell';
    return 'hold';
  }

  // Raw Risk Range position (%, can go <0 or >100) -- identical formula to
  // web/actionable.js's own _rawRrPos, so a symbol's mini RR bar here reads
  // the same as its Action popup's RR bar there.
  function rawRrPos(lrr, trr, last) {
    if (lrr == null || trr == null || last == null || trr === lrr) return null;
    return (last - lrr) / (trr - lrr) * 100;
  }

  // Signed stop-proximity SD -- identical formula to web/actionable.js's
  // own _lineProximitySd (HV daily-move-normalized distance from a Trade/
  // Trend line): negative when price is BELOW the line. Shown in
  // parentheses next to the Td/Tn value.
  function lineProximitySd(hv, px, lineVal) {
    if (hv == null || px == null || lineVal == null || hv <= 0) return null;
    const dailyMove = px * hv / Math.sqrt(252);
    return dailyMove > 0 ? (px - lineVal) / dailyMove : null;
  }

  const svg = d3.select('#uvTm');
  const tt = $('uvTt');

  // ---------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------
  let currentView = 'assetclass'; // 'assetclass' | 'account' -- which hierarchy's root is showing
  let sizeMode = 'count';         // 'count' | 'capital' -- what sizes every tile at every level
  let currentFilter = 'all';
  // 'all' | 'buy' | 'sell' | 'hold' -- narrows the drilldown (stock) tiles
  // by trading signal; has no effect above the drilldown level.
  let currentColorFilter = 'all';
  // 'all' or one tag from ALL_STYLE_TAGS -- same scope as Color.
  let currentStyleFilter = 'all';
  // Unified drill path, shared by both hierarchies: null (root) or
  // { account?, assetClass?, sector? } -- built progressively. The "By
  // Asset Class" entry never sets `account`; the "By Account" entry sets
  // it first, then the same assetClass/sector legs follow underneath.
  let drill = null;
  function resetDrill() { drill = null; }
  // Sentinel for drill.sector meaning "every sector, flattened" -- set by
  // the Equities tile's small "All stocks" link (renderAssetClassFlat),
  // which skips the Sector grouping step and goes straight to a flat list
  // of every equity symbol in scope. Not a real sector name, so it's
  // rendered as "All stocks" in the breadcrumb rather than shown raw.
  const ALL_SECTORS = '__ALL_SECTORS__';

  let FILTERS = {}; // {all|held|actionable: {note, rows: [SYMS...]}}

  // The symbol-shaped rows the CURRENT drill level's hierarchy is built
  // from. Once an account is chosen (drill.account set), scope narrows to
  // just that account's positions; otherwise it's the whole filtered
  // universe. Same shape either way (posAsSymRow adapts POS to match), so
  // buildAssetHierarchy doesn't care which source it got.
  function currentScopeRows() {
    if (drill && drill.account) return POS.filter(r => r.account_id === drill.account).map(posAsSymRow);
    return FILTERS[currentFilter].rows;
  }

  function render() {
    document.querySelectorAll('.uv-tab[data-view]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.view === currentView)));
    document.querySelectorAll('.uv-tab[data-size]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.size === sizeMode)));
    document.querySelectorAll('.uv-tab[data-filter]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.filter === currentFilter)));
    document.querySelectorAll('.uv-tab[data-color]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.color === currentColorFilter)));
    document.querySelectorAll('.uv-tab[data-style]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.style === currentStyleFilter)));

    if (currentView === 'account' && !(drill && drill.account)) { renderAccountRoot(); return; }
    renderHierarchy();
  }

  // ---- "By Account" root: tiles = accounts. Click drills into that
  // account's own Asset Class -> Sector -> Symbol hierarchy (renderHierarchy,
  // via drill = {account}). ------------------------------------------------
  function renderAccountRoot() {
    const totalHeldSymbols = d3.sum(ACCOUNTS, a => a.posCount);
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

    if (ACCOUNTS.length === 0) {
      svg.selectAll('*').remove();
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text('No held positions to break out by account.');
      hideAllLegends();
      $('uvRankList').innerHTML = ''; $('uvSLargest').textContent = '—';
      return;
    }

    renderAccountFlat(W, H);

    const ranklist = $('uvRankList');
    ranklist.innerHTML = ACCOUNTS.slice(0, 8).map(a => {
      const dot = cssVar(acctColor.get(a.key));
      const val = sizeMode === 'capital' ? fmtUsd(a.total) : fmtInt(a.posCount);
      return `<li class="uv-rank-row"><span class="uv-rank-dot" style="background:${dot};"></span>` +
        `<span class="uv-rank-name">${esc(a.label)}</span><span class="uv-rank-val">${val}</span></li>`;
    }).join('');
    $('uvSLargest').textContent = ACCOUNTS[0] ? ACCOUNTS[0].label : '—';
  }

  // ---- Shared hierarchy renderer: Asset Class -> Sector (Equities only)
  // -> Symbol, for whichever `scope` currentScopeRows() resolves (whole
  // universe for "By Asset Class", one account's positions for "By
  // Account" past its root level). ------------------------------------
  function renderHierarchy() {
    const scope = currentScopeRows();
    const hier = buildAssetHierarchy(scope);
    const inAccount = !!(drill && drill.account);

    $('uvTotalCount').textContent = fmtInt(scope.length);
    $('uvTotalSectors').textContent = hier.agg.length;
    $('uvSectorsUnit').textContent = 'asset classes';
    $('uvSHeld').textContent = d3.sum(hier.agg, d => d.held) + ' symbols';
    $('uvSCapital').textContent = fmtUsd(d3.sum(hier.agg, d => d.held_value));
    const note = inAccount ? `in ${acctLabelMap.get(drill.account) || drill.account}`
      : (currentFilter !== 'all' ? FILTERS[currentFilter].note : '');
    $('uvFilterCount').textContent = note ? `— ${note}` : '';

    renderCrumbs();
    $('uvSideHeading').textContent = inAccount ? `Top asset classes in ${acctLabelMap.get(drill.account) || drill.account}` : 'Top asset classes';

    const wrap = document.querySelector('.uv-svg-wrap');
    const W = wrap.clientWidth, H = wrap.clientHeight;
    svg.attr('viewBox', `0 0 ${W} ${H}`);

    if (scope.length === 0) {
      svg.selectAll('*').remove();
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text('No symbols match this filter.');
      hideAllLegends(); $('uvRankList').innerHTML = ''; $('uvSLargest').textContent = '—';
      return;
    }

    if (!drill || !drill.assetClass) {
      renderAssetClassFlat(hier.agg, W, H,
        ac => { drill = inAccount ? { account: drill.account, assetClass: ac } : { assetClass: ac }; render(); },
        ac => { drill = inAccount ? { account: drill.account, assetClass: ac, sector: ALL_SECTORS } : { assetClass: ac, sector: ALL_SECTORS }; render(); });
    } else if (!drill.sector) {
      if (drill.assetClass === 'Equities') {
        renderSectorWithinAsset(hier.sectorByAsset['Equities'] || [], W, H, sec => { drill = { ...drill, sector: sec }; render(); });
      } else {
        const rows = (hier.byAsset[drill.assetClass] || []).map(r => ({ tos_symbol: r.tos_symbol, value: r.current_position_dollar || 0, detail: symbolDetail.get(r.tos_symbol) || {} }));
        renderSymbolTiles(rows, W, H);
      }
    } else if (drill.sector === ALL_SECTORS) {
      // "All stocks" link on the Equities tile -- every equity symbol in
      // this scope, flat, skipping the Sector grouping step entirely.
      const rows = (hier.byAsset[drill.assetClass] || []).map(r => ({ tos_symbol: r.tos_symbol, value: r.current_position_dollar || 0, detail: symbolDetail.get(r.tos_symbol) || {} }));
      renderSymbolTiles(rows, W, H);
    } else {
      const symRows = ((hier.symsByAssetSector[drill.assetClass] || {})[drill.sector] || []);
      const rows = symRows.map(r => ({ tos_symbol: r.tos_symbol, value: r.current_position_dollar || 0, detail: symbolDetail.get(r.tos_symbol) || {} }));
      renderSymbolTiles(rows, W, H);
    }

    // side panel -- top asset classes for the current scope, regardless of
    // drill depth (the breadcrumb already says where you are).
    const ranklist = $('uvRankList');
    const top = [...hier.agg].sort((a, b) => (sizeMode === 'capital' ? b.held_value - a.held_value : b.count - a.count)).slice(0, 8);
    ranklist.innerHTML = top.map(d => {
      const dot = cssVar(assetColorAssign.get(d.asset_class) || '--cat-unmapped');
      const val = sizeMode === 'capital' ? fmtUsd(d.held_value) : fmtInt(d.count);
      return `<li class="uv-rank-row"><span class="uv-rank-dot" style="background:${dot};"></span>` +
        `<span class="uv-rank-name">${esc(d.asset_class)}</span><span class="uv-rank-val">${val}</span></li>`;
    }).join('');
    $('uvSLargest').textContent = top[0] ? top[0].asset_class : '—';
  }

  function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function hideAllLegends() { $('uvLegendCat').hidden = true; $('uvLegendAcct').hidden = true; }

  // Breadcrumb for the unified drill path (account? -> assetClass? ->
  // sector?) -- works for both hierarchies since it just walks whichever
  // legs `drill` has set.
  function renderCrumbs() {
    const el = $('uvCrumbs');
    if (!drill) { el.innerHTML = ''; return; }
    const segs = [];
    if (drill.account) segs.push({ key: 'account', label: acctLabelMap.get(drill.account) || drill.account });
    if (drill.assetClass) segs.push({ key: 'assetClass', label: drill.assetClass });
    if (drill.sector) segs.push({ key: 'sector', label: drill.sector === ALL_SECTORS ? 'All stocks' : drill.sector });
    if (segs.length === 0) { el.innerHTML = ''; return; }

    const parts = [`<span class="uv-crumb" data-crumb="root">Universe</span>`];
    segs.forEach((s, i) => {
      parts.push(`<span class="uv-crumb-sep">/</span>`);
      const isLast = i === segs.length - 1;
      parts.push(isLast ? `<span class="uv-crumb current">${esc(s.label)}</span>` : `<span class="uv-crumb" data-crumb="${s.key}">${esc(s.label)}</span>`);
    });
    el.innerHTML = parts.join('');
    el.querySelectorAll('[data-crumb="root"]').forEach(e => e.addEventListener('click', () => { drill = null; render(); }));
    el.querySelectorAll('[data-crumb="account"]').forEach(e => e.addEventListener('click', () => { drill = { account: drill.account }; render(); }));
    el.querySelectorAll('[data-crumb="assetClass"]').forEach(e => e.addEventListener('click', () => { drill = drill.account ? { account: drill.account, assetClass: drill.assetClass } : { assetClass: drill.assetClass }; render(); }));
  }

  // ---- "By Account" root tiles: accounts, colored by acctColor. Click
  // drills into that account's Asset Class breakdown (renderHierarchy).
  function renderAccountFlat(W, H) {
    hideAllLegends();
    const legendAcct = $('uvLegendAcct');
    legendAcct.hidden = false;
    legendAcct.innerHTML = ACCOUNTS.map(a =>
      `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar(acctColor.get(a.key))};"></span>${esc(a.label)}</span>`
    ).join('');

    const valueFn = a => sizeMode === 'capital' ? a.total : a.posCount;
    const sized = ACCOUNTS.filter(a => valueFn(a) > 0);
    const root = d3.hierarchy({ children: sized }).sum(valueFn).sort((a, b) => b.value - a.value);
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
        const sub = d.data.posCount > 0
          ? `${fmtUsd(d.data.total)} · ${d.data.posCount} symbol${d.data.posCount === 1 ? '' : 's'}`
          : `${fmtUsd(d.data.total)} · all cash`;
        g.append('text').attr('class', 'uv-c-sub').attr('x', 7).attr('y', 30)
          .attr('font-size', 9.5).attr('fill', ink).attr('opacity', 0.85).text(sub);
      }
    });

    cell.on('mousemove', (evt, d) => {
      const cashVal = cashByAccount.get(d.data.key) || 0;
      const securitiesVal = d.data.total - cashVal;
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.label)}</div>` +
        `<div class="uv-tt-row"><span>Total</span><span>${fmtUsd(d.data.total)}</span></div>` +
        `<div class="uv-tt-row"><span>Securities</span><span>${fmtUsd(securitiesVal)}</span></div>` +
        `<div class="uv-tt-row"><span>Cash</span><span>${fmtUsd(cashVal)}</span></div>` +
        `<div class="uv-tt-row"><span>Symbols</span><span>${d.data.posCount}</span></div>` +
        `<div class="uv-tt-hint">${d.data.posCount > 0 ? 'Click to see asset classes' : 'No securities held'}</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => { if (d.data.posCount > 0) { drill = { account: d.data.key }; render(); } });
  }

  // ---- Asset Class tiles (top level of renderHierarchy), colored by
  // assetColorAssign. `onClick(assetClass)` lets the caller decide what the
  // resulting drill state looks like (whole-universe vs within an account).
  // `onAllStocks(assetClass)` fires only from the Equities tile's small
  // "All stocks" corner link -- user: "small link on the account tile ->
  // equities to take me to all stocks directly and anywhere else on the
  // equities tile takes me to sectors" -- the link stops the click event
  // from bubbling, so the rest of the tile keeps its normal onClick
  // (-> Sector tiles) behavior.
  function renderAssetClassFlat(data, W, H, onClick, onAllStocks) {
    hideAllLegends();
    const legendCat = $('uvLegendCat');
    legendCat.hidden = false;
    legendCat.innerHTML = ASSET_RANK.slice(0, CAT_SLOTS.length).map((d, i) =>
      `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar(CAT_SLOTS[i])};"></span>${esc(d.asset_class)}</span>`
    ).join('') + `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar('--cat-unmapped')};"></span>Other / unclassified</span>`;

    const valueFn = d => sizeMode === 'capital' ? d.held_value : d.count;
    const sized = data.filter(d => valueFn(d) > 0);
    const root = d3.hierarchy({ children: sized }).sum(valueFn).sort((a, b) => b.value - a.value);
    d3.treemap().size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    svg.selectAll('*').remove();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    const colorFn = d => cssVar(assetColorAssign.get(d.asset_class) || '--cat-unmapped');
    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => colorFn(d.data));

    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      if (w < 46 || h < 26) return;
      const fill = colorFn(d.data); const ink = labelColorFor(fill);
      const g = d3.select(this); const name = d.data.asset_class;
      g.append('text').attr('class', 'uv-c-name').attr('x', 7).attr('y', 16)
        .attr('font-size', w < 90 ? 9.5 : 11).attr('fill', ink)
        .text(name.length > (w / 6) ? name.slice(0, Math.max(3, Math.floor(w / 6.2))) + '…' : name);
      if (h > 40) {
        g.append('text').attr('class', 'uv-c-sub').attr('x', 7).attr('y', 30)
          .attr('font-size', 9.5).attr('fill', ink).attr('opacity', 0.85)
          .text(`${fmtInt(d.data.count)} sym · ${fmtUsd(d.data.held_value)}`);
      }
      // Small "All stocks" corner link, Equities tile only -- skips the
      // Sector step and goes straight to every equity symbol, flat. Its
      // own click handler stops propagation so the rest of the tile keeps
      // its normal "go to Sectors" click.
      if (d.data.asset_class === 'Equities' && w > 78 && h > 26 && onAllStocks) {
        g.append('text').attr('class', 'uv-c-link').attr('x', w - 6).attr('y', 16)
          .attr('text-anchor', 'end').attr('font-size', 8.5).attr('font-weight', 700)
          .attr('fill', ink).style('text-decoration', 'underline').style('cursor', 'pointer')
          .text('All stocks →')
          .on('click', evt => { evt.stopPropagation(); onAllStocks(d.data.asset_class); });
      }
    });

    cell.on('mousemove', (evt, d) => {
      const heldPct = d.data.count ? Math.round((d.data.held / d.data.count) * 100) : 0;
      const hint = d.data.asset_class === 'Equities' ? 'Click to see sectors · or "All stocks" for every symbol' : 'Click to see symbols';
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.asset_class)}</div>` +
        `<div class="uv-tt-row"><span>Symbols</span><span>${fmtInt(d.data.count)}</span></div>` +
        `<div class="uv-tt-row"><span>Held</span><span>${d.data.held} (${heldPct}%)</span></div>` +
        `<div class="uv-tt-row"><span>Capital</span><span>${fmtUsd(d.data.held_value)}</span></div>` +
        `<div class="uv-tt-syms">${d.data.sample.map(esc).join(' · ')}${d.data.count > d.data.sample.length ? ' …' : ''}</div>` +
        `<div class="uv-tt-hint">${hint}</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => onClick(d.data.asset_class));
  }

  // ---- Sector tiles WITHIN one asset class (Equities only), colored by
  // the SAME catAssign the sector legend uses everywhere -- a sector reads
  // as the same color here as anywhere else it appears.
  function renderSectorWithinAsset(sectors, W, H, onClick) {
    hideAllLegends();
    const legendCat = $('uvLegendCat');
    legendCat.hidden = false;
    legendCat.innerHTML = SECTOR_RANK.slice(0, CAT_SLOTS.length).map((d, i) =>
      `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar(CAT_SLOTS[i])};"></span>${esc(d.sector)}</span>`
    ).join('') + `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar('--cat-unmapped')};"></span>Other / unclassified</span>`;

    const valueFn = d => sizeMode === 'capital' ? d.held_value : d.count;
    const sized = sectors.filter(d => valueFn(d) > 0);
    const root = d3.hierarchy({ children: sized }).sum(valueFn).sort((a, b) => b.value - a.value);
    d3.treemap().size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    svg.selectAll('*').remove();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    const colorFn = d => cssVar(catAssign.get(d.sector) || '--cat-unmapped');
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
      if (h > 40) {
        g.append('text').attr('class', 'uv-c-sub').attr('x', 7).attr('y', 30)
          .attr('font-size', 9.5).attr('fill', ink).attr('opacity', 0.85)
          .text(`${fmtInt(d.data.count)} sym · ${fmtUsd(d.data.held_value)}`);
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
      .on('click', (evt, d) => onClick(d.data.sector));
  }

  // Greedy word-wrap for the small sample-ticker line(s) on a tile -- kept
  // for potential reuse (not currently called by any active render path,
  // symbol tiles show a single ticker per tile), SVG <text> doesn't wrap on
  // its own.
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

  // ---- Symbol tiles: the actual "individual stock" drawing (action
  // color, Td/Tn, RR bar, click-to-Actionable) used by every drilldown
  // path. Caller resolves `rows` (each needing {tos_symbol, value, detail}
  // -- value is always the $ figure; this function itself decides whether
  // to size by it or by count, per the module-level `sizeMode`).
  function renderSymbolTiles(rows, W, H) {
    hideAllLegends();
    const unit = sizeMode;
    if (unit === 'count') rows = rows.map(r => ({ ...r, value: 1 }));
    else rows = rows.filter(r => r.value > 0); // capital sizing: a $0 position/symbol gets no tile

    // Color/Style filters -- narrow to one trading-signal side and/or one
    // style tag, applied here (drilldown level) only; rollups above are
    // unaffected.
    if (currentColorFilter !== 'all') {
      rows = rows.filter(r => actionSide(r.detail.final_code) === currentColorFilter);
    }
    if (currentStyleFilter !== 'all') {
      rows = rows.filter(r => (r.detail.style_tags || []).includes(currentStyleFilter));
    }

    svg.selectAll('*').remove();
    if (rows.length === 0) {
      const why = currentStyleFilter !== 'all' ? currentStyleFilter
        : currentColorFilter !== 'all' ? currentColorFilter : '';
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text(why ? `No ${why} symbols here.` : 'No symbols here.');
      return;
    }

    const root = d3.hierarchy({ children: rows }).sum(d => Math.max(d.value, 0.0001)).sort((a, b) => b.value - a.value);
    d3.treemap().size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    // per-symbol color = trading signal (final_code), not identity -- see
    // ACTION_COLOR's own comment.
    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => actionColor(d.data.detail.final_code));

    // Progressive detail as the tile has room -- name always, then action
    // code, then value, then Trade/Trend above/below coloring, then a mini
    // Risk Range bar. Same fields/formula the Action popup's own Td/Tn
    // boxes and RR bar use (trade_line_value/trend_line_value, rawRrPos),
    // just miniaturized onto the tile.
    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      if (w < 30 || h < 18) return;
      const fill = actionColor(d.data.detail.final_code);
      const ink = labelColorFor(fill);
      const det = d.data.detail;
      const g = d3.select(this);

      g.append('text').attr('class', 'uv-c-name').attr('x', 5).attr('y', 13)
        .attr('font-size', w < 60 ? 9 : 10.5).attr('fill', ink).text(d.data.tos_symbol);

      if (h > 28 && det.final_code) {
        g.append('text').attr('x', 5).attr('y', 24)
          .attr('font-size', 8.5).attr('font-weight', 700).attr('fill', ink).attr('opacity', 0.85)
          .text(det.final_code);
      }
      if (h > 40 && unit === 'capital') {
        g.append('text').attr('class', 'uv-c-sub').attr('x', 5).attr('y', 35)
          .attr('font-size', 9).attr('fill', ink).attr('opacity', 0.85).text(fmtUsd(d.data.value));
      }

      // Trade/Trend: white up/down arrow (direction, always legible
      // against any action-color fill) + Td/Tn value colored by above/
      // below (green above, red below, same convention as the Action
      // popup's Td/Tn boxes) + signed stop-proximity SD in parentheses
      // (lineProximitySd -- same formula/sign as the popup's own SD badge).
      // 2026-08-30: briefly added a white background chip behind this
      // text to fix red-on-green contrast -- reverted, user: "too much
      // white now". Red-on-dark-green is a known weaker case; live with it
      // for now rather than re-introduce the chip.
      const lastPx = det.last_price;
      const tdY = (h > 40 && unit === 'capital') ? 46 : 35;
      if (h > tdY + 8 && w > 60) {
        const lineRow = (label, lineVal, y) => {
          if (lineVal == null || lastPx == null) return;
          const above = lastPx >= lineVal;
          const color = above ? '#16a34a' : '#dc2626';
          const sd = lineProximitySd(det.hv, lastPx, lineVal);
          const t = g.append('text').attr('x', 5).attr('y', y).attr('font-size', 7.5).attr('font-weight', 700);
          t.append('tspan').attr('fill', '#ffffff').text(above ? '▲ ' : '▼ ');
          t.append('tspan').attr('fill', color).text(`${label} ${lineVal.toFixed(1)}`);
          if (sd != null) t.append('tspan').attr('fill', color).attr('opacity', 0.8).text(` (${sd.toFixed(1)}σ)`);
        };
        lineRow('Td', det.trade_line_value, tdY);
        if (h > tdY + 18) lineRow('Tn', det.trend_line_value, tdY + 9);
      }

      // mini Risk Range bar -- clamped track + a tick at the raw (possibly
      // <0 or >100) position, ink-colored so it stays legible against
      // whichever action color the tile itself is filled with.
      const pos = rawRrPos(det.lrr, det.trr, lastPx);
      if (pos != null && h > 62 && w > 46) {
        const barW = w - 10, barY = h - 10, clamped = Math.max(0, Math.min(100, pos));
        g.append('rect').attr('x', 5).attr('y', barY).attr('width', barW).attr('height', 3)
          .attr('rx', 1.5).attr('fill', ink).attr('opacity', 0.25);
        g.append('rect').attr('x', 5).attr('y', barY).attr('width', barW * clamped / 100).attr('height', 3)
          .attr('rx', 1.5).attr('fill', ink).attr('opacity', 0.75);
        g.append('rect').attr('x', 5 + barW * clamped / 100 - 1).attr('y', barY - 2).attr('width', 2).attr('height', 7)
          .attr('fill', ink);
      }
    });

    cell.on('mousemove', (evt, d) => {
      const det = d.data.detail;
      const pos = rawRrPos(det.lrr, det.trr, det.last_price);
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.tos_symbol)}</div>` +
        `<div class="uv-tt-row"><span>Signal</span><span>${esc(actionLabel(det.final_code))} (${esc(det.final_code || 'HOLD')})</span></div>` +
        (unit === 'capital' ? `<div class="uv-tt-row"><span>Value</span><span>${fmtUsd(d.data.value)}</span></div>` : '') +
        (det.trade_line_value != null ? `<div class="uv-tt-row"><span>Trade line</span><span>${fmtUsd(det.trade_line_value)}</span></div>` : '') +
        (det.trend_line_value != null ? `<div class="uv-tt-row"><span>Trend line</span><span>${fmtUsd(det.trend_line_value)}</span></div>` : '') +
        (pos != null ? `<div class="uv-tt-row"><span>Risk Range</span><span>${Math.round(pos)}%</span></div>` : '') +
        `<div class="uv-tt-hint">Click to open in Actionable</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => { window.location.href = '/actionable?symbol=' + encodeURIComponent(d.data.tos_symbol); });

    // small Buy/Sell/Hold legend -- reuses .uv-legend-cats' styling via
    // uvLegendCat (hidden by everything else at the top of this function).
    const legendCat = $('uvLegendCat');
    legendCat.hidden = false;
    legendCat.innerHTML = [
      { c: '--act-buy-strong', l: 'Buy' },
      { c: '--act-sell-strong', l: 'Sell' },
      { c: '--act-neutral', l: 'Hold' },
    ].map(x => `<span class="uv-lg-item"><span class="uv-lg-dot" style="background:${cssVar(x.c)};"></span>${x.l}</span>`).join('');
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
    document.querySelectorAll('.uv-tab[data-size]').forEach(t =>
      t.addEventListener('click', () => { sizeMode = t.dataset.size; render(); }));
    document.querySelectorAll('.uv-tab[data-filter]').forEach(t =>
      t.addEventListener('click', () => {
        currentFilter = t.dataset.filter;
        // leaving Held with "By Account" active means there's nothing left
        // to show it against -- fall back to the default view.
        if (currentFilter !== 'held' && currentView === 'account') currentView = 'assetclass';
        resetDrill(); render();
      }));
    // Color filter deliberately does NOT reset the drill -- if you're
    // already looking at a sector's (or asset class's) stock tiles,
    // narrowing to Buy/Sell/Hold should re-filter that same view, not kick
    // you back out to the level above. (Style filter is the same -- wired
    // in wireStyleTabs() below, once its data-driven tab list exists.)
    document.querySelectorAll('.uv-tab[data-color]').forEach(t =>
      t.addEventListener('click', () => { currentColorFilter = t.dataset.color; render(); }));
    window.addEventListener('resize', () => render());
  }

  function wireStyleTabs() {
    const styleTabs = $('uvStyleTabs');
    styleTabs.innerHTML = '<button class="uv-tab" role="tab" data-style="all" aria-selected="true">All</button>' +
      ALL_STYLE_TAGS.map(t => `<button class="uv-tab" role="tab" data-style="${esc(t)}" aria-selected="false">${esc(t)}</button>`).join('');
    document.querySelectorAll('.uv-tab[data-style]').forEach(t =>
      t.addEventListener('click', () => { currentStyleFilter = t.dataset.style; render(); }));
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
      all:        { note: 'every tracked symbol', rows: SYMS },
      held:       { note: 'symbols with an open position', rows: SYMS.filter(r => r.held_today) },
      actionable: { note: 'symbols with a live signal today', rows: SYMS.filter(r => r.final_code && r.final_code !== 'HOLD') },
    };
    $('uvAsOf').textContent = new Date().toLocaleDateString();
    wireStyleTabs();
    wireStaticControls();
    render();
  }

  init();
})();
