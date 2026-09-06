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
// 2026-09-02: added a 3rd entry point, "By Source" (Source -> Asset Class ->
// Sector -> Symbol), rooted at the outlook source(s) that flagged a symbol
// (drv_actionable.source_actions -- RR/CALL/ETF/II/SSS/PS/...). Unlike
// Account/Asset Class (each symbol has exactly one), a symbol can carry
// several sources at once, so it can land under more than one source root
// tile -- same multi-tag shape Style already has, not a strict partition.
// Filter (All/Held/Actionable) stays live under it (a source can flag a
// not-held symbol too), unlike "By Account" which forces Held.
//
// Independent controls: View (Asset Class / Account / Source — which
// hierarchy), Size (Count/Capital — what sizes every tile), Filter (all/
// held/actionable — which symbols count), Color (buy/sell/hold — narrows
// drilldown tiles), Style (one style tag — narrows drilldown tiles). Click
// any group tile to drill in; click a symbol tile to jump to Actionable.
(function () {
  "use strict";

  const $ = id => document.getElementById(id);
  const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmtInt = d3.format(',');
  // Sign always goes before the $ ("-$188", never "$-188") -- the old
  // small-magnitude branch below 1000 tacked Math.round(v)'s own leading
  // "-" straight onto "$" instead of moving it in front. User: "fix the
  // fmtUsd negative formatting" -- 2026-09-05, noticed via the new Account
  // tile P&L lines but pre-existing everywhere fmtUsd/fmtSignedUsd render
  // a small negative $ amount (e.g. the KPI strip's "Today" card).
  const fmtUsd = v => (v < 0 ? '-$' : '$') + (Math.abs(v) >= 1000 ? d3.format(',.0f')(Math.abs(v)) : Math.round(Math.abs(v)));
  // Compact $ value ("1000s -> Ks") for the Account tile's P&L lines and
  // its Asset Class / Sector legend rows -- a full "$322,411" would either
  // crowd out the legend's own name column, or (in the P&L block) run
  // wider than the fixed-width value column can hold once a caret column
  // sits in front of it. Same K/M convention web/_common.js's own
  // fmtUsd(..., {compact:true}) uses elsewhere in the app (1 decimal for
  // K, 2 for M) -- kept as its own local helper rather than importing that
  // one, since universe.js's own `fmtUsd` above (full digits, no
  // compacting) is still what the tile's header line and hover tooltip
  // use. User: "along with % i need the numbers in 1000s -> Ks" --
  // 2026-09-05, then "all in Ks" for the P&L block too -- 2026-09-06.
  function fmtK(v) {
    const sign = v < 0 ? '-' : '';
    const abs = Math.abs(v);
    if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
    return `${sign}$${Math.round(abs)}`;
  }
  // Signed compact $ value ("+$3.4K" / "-$0.3K") -- fmtK already prepends
  // its own "-" for a negative, so this only ever needs to add the "+".
  const fmtSignedK = v => (v >= 0 ? '+' : '') + fmtK(v);

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
  // 2026-09-03 (held-perspective proposal): account_id -> {costBasis,
  // totalGainDollar, todayGainDollar} -- summed from POS rows (each already
  // carries its own account's unrealized P&L straight off get_portfolio(),
  // see api/routers/universe.py). Feeds the Account root tile tooltip.
  let acctGain = new Map();
  // account_id -> {total_realized, ytd_realized} -- FIFO-matched realized
  // gain (drv_realized_gain), same rollup /portfolio's Realized tab uses.
  let realizedByAccount = new Map();
  // account_id -> {total_dividends, ytd_dividends} -- gross dividend income
  // (drv_dividend_income), same rollup /portfolio's Dividends tab uses.
  // Feeds the Account root tile tooltip, same spot realizedByAccount does.
  // User: "add the dividends line to universe" -- 2026-09-05.
  let dividendsByAccount = new Map();
  // account_id -> {buy, sell} -- count of that account's held positions
  // whose current final_code (drv_actionable's trading signal) is a buy-
  // or sell-tier action, same tiering ACTION_COLOR already encodes. Feeds
  // the Account root tile's "N BUY · N SELL" line. User: "so I know
  // exactly what is happening to my accounts" -- 2026-09-05.
  let acctActionCounts = new Map();
  // account_id -> [{asset_class, value, count}] sorted desc by value --
  // that account's own held positions broken out by asset class (securities
  // only, cash isn't an asset class in this taxonomy). Feeds the Account
  // tile's Asset Class legend rows, shown when there's still room below
  // the P&L/signal lines. User: "We still have more space in the tiles on
  // top level. Display Asset Classes breakdown in the tile for 'By
  // Account'" -- 2026-09-05.
  let acctAssetBreakdown = new Map();
  // account_id -> [{sector, value, count, costBasis, gainDollar}] sorted
  // desc by value -- that account's Equities positions ONE level further
  // broken out by GICS sector (Equities is the only asset class with a
  // real sub-grouping; every other class mostly lands in one
  // 'Unclassified' sector, same reason buildAssetHierarchy only bothers
  // sub-splitting Equities for the drilldown hierarchy). Feeds a compact
  // "Equities by Sector" legend below the Asset Class legend, shown only
  // when there's still room. User: "all the tile that have enough space
  // do the details about equities (next level grouping like sectors)
  // below the asset style legend" -- 2026-09-05.
  let acctSectorBreakdown = new Map();
  // account_id -> Map(sector -> [{tos_symbol, value, count, costBasis,
  // gainDollar}]) sorted desc by value -- the individual stocks behind
  // one sector, one level deeper than acctSectorBreakdown above. Feeds a
  // "Stocks" legend on the Sector tile (within an account's Equities).
  // User: "Now one level deep, dsiplay stocks, % and amount, caret,% up
  // or down" -- 2026-09-06.
  let acctSectorSymbolBreakdown = new Map();
  // Portfolio-wide KPI strip totals, computed once in build() -- NOT
  // re-filtered by View/Filter/Color (those only narrow the treemap).
  let KPI = null;
  // tos_symbol -> full SYMS row (final_code, last_price, trade/trend line
  // values, lrr/trr, style_tags) -- position rows (account drilldowns)
  // don't carry any of this themselves, only {tos_symbol, market_value},
  // so drilldown tiles look it up here regardless of which drill path
  // produced them.
  let symbolDetail = new Map();
  // tos_symbol -> [account label, ...] -- every account currently holding
  // that symbol, friendly-labeled (acctLabelMap). Built from POS (which
  // already carries account_id per symbol/position) rather than a new
  // backend `held_accounts` field, so it stays in the same account-label
  // key space renderAccountFlat's own ACCOUNTS list already uses. Feeds
  // the Symbol tile's "Held" line. User: "Remove the RSI from stock tile
  // and display where it is held instead" -- 2026-09-06.
  let symbolAccounts = new Map();

  let catAssign = new Map();          // sector -> --catN, ranked once on the whole universe (stable across filters/drills)
  let assetColorAssign = new Map();   // asset_class -> --catN, same pattern
  let SECTOR_RANK = [];                // ranked sector aggregate, whole universe, excl. Unclassified -- feeds catAssign + every sector legend
  let ASSET_RANK = [];                 // same for asset classes
  const CAT_SLOTS = ['--cat1', '--cat2', '--cat3', '--cat4', '--cat5', '--cat6', '--cat7', '--cat8', '--cat9'];
  // GICS sector -> its SPDR Select Sector ETF -- a clean, single-symbol,
  // already-computed technical read for "the sector," used by the Sector
  // legend's outlook caret instead of a noisy majority-vote across every
  // (mostly unheld/watchlist) symbol classified under that sector. User
  // checked XLY (Consumer Discretionary) specifically: its own rr_outlook
  // read Neutral, but the old vote-across-134-symbols tally read Bullish
  // -- "should have been neutral ... i see up green arrow" -> confirmed
  // they wanted XLY's own individual outlook, not the crowd's -- 2026-09-06.
  const SECTOR_ETF = {
    'Communication Services': 'XLC', 'Consumer Discretionary': 'XLY', 'Consumer Staples': 'XLP',
    'Energy': 'XLE', 'Financials': 'XLF', 'Health Care': 'XLV', 'Industrials': 'XLI',
    'Materials': 'XLB', 'Real Estate': 'XLRE', 'Information Technology': 'XLK', 'Utilities': 'XLU',
  };
  // Same idea as SECTOR_ETF, for the two Asset Class rows that actually
  // have an honest single-ticker benchmark and a small enough crowd for
  // one instrument to fairly represent it -- Equities (already broken out
  // further into 11 GICS sectors elsewhere on this screen), Fixed Income
  // (the loaded instruments span very different durations/credit and
  // genuinely disagree -- TLT/IEF/LQD/HYG), and Commodities (this app's
  // own data already splits Gold into its own separate asset_class) don't
  // get one -- no ticker would be an honest stand-in for any of those
  // three, so those rows stay on the crowd tally. User: "Do we have the
  // same or similar for 'asset class'?" -> confirmed UUP/BTC only --
  // 2026-09-06.
  const ASSET_ETF = { 'FX / Currency': 'UUP', 'Crypto': 'BTC' };
  // Tiling for every treemap in this file (Account/Source/AssetClass/
  // Sector/Symbol tiles all share this one d3.treemap() config). Default
  // squarify targets phi (~1.618, a general-purpose aesthetic ratio) as
  // its "good enough" aspect ratio -- still produces genuine slivers on
  // real data (the "Ra" account tile measured an 18:1 ratio under the
  // default, at some viewport sizes/size-modes). ratio(1) asks the same
  // built-in algorithm to target an actual square instead, cutting that
  // same tile's worst case to ~4.2:1 with no downside on tiles that were
  // already reasonable (verified against live account data across several
  // viewport sizes and both Count/Capital size modes). User: "arrange
  // tiles... close to square boxes instead of long horizontal or
  // vertical" -- 2026-09-05.
  const SQUARE_TILE = d3.treemapSquarify.ratio(1);
  const ACCOUNT_COLOR_SLOTS = ['--cat1', '--cat2', '--cat3', '--cat4', '--cat5'];
  let acctColor = new Map();
  let sourceColorAssign = new Map();  // source code -> --catN, same ranked-on-whole-universe pattern as catAssign/assetColorAssign
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

  // Same shape as aggregateBy(), but for a MULTI-valued field (r.sources
  // can list more than one code) -- a row with 2 sources counts under
  // both, same multi-membership Style tags already allow, so this can't
  // reuse aggregateBy's one-key-per-row loop as-is.
  function aggregateByMulti(rows, keyField, keysFn) {
    const by = new Map();
    rows.forEach(r => {
      (keysFn(r) || []).forEach(key => {
        if (!by.has(key)) by.set(key, { [keyField]: key, count: 0, held: 0, held_value: 0, sample: [] });
        const a = by.get(key);
        a.count++;
        if (r.held_today) { a.held++; a.held_value += r.current_position_dollar || 0; }
        if (a.sample.length < 6) a.sample.push(r.tos_symbol);
      });
    });
    return [...by.values()].sort((a, b) => b.count - a.count);
  }
  const aggregateSources = rows => aggregateByMulti(rows, 'source', r => r.sources);

  // A raw value-based treemap can degenerate a near-zero-share item to a
  // literal 0-height sliver -- genuinely invisible, not just unlabeled
  // (e.g. a sector holding one tiny odd-lot position next to sectors
  // worth 1000x more, under Capital sizing). User: "Still doesn't show"
  // -- traced to exactly this. Floors every item's share at a small
  // percentage of the group's total so it still gets a visible, clickable
  // tile; the distortion is tiny for anything with a real share and only
  // matters for the near-zero outliers this exists to rescue.
  function floorValueFn(items, rawValueFn, floorRatio) {
    const total = d3.sum(items, rawValueFn) || 0;
    const n = items.length || 1;
    // Auto-scale by count when the caller doesn't pin a ratio: a handful
    // of sector/asset-class/account tiles vs. a couple hundred individual
    // symbol tiles need very different floors for the same "still
    // visible" guarantee -- cap all items' floors together at ~40% of the
    // total, however many items there are.
    const ratio = floorRatio != null ? floorRatio : Math.min(0.02, 0.4 / n);
    const floor = total * ratio;
    return d => Math.max(rawValueFn(d), floor);
  }

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

  // Generic per-scope P&L/breakdown aggregation -- takes ANY subset of POS
  // rows (one account's positions, one source's positions across every
  // account, or the entire portfolio unfiltered) and returns the same
  // {gain, counts, assetBreakdown, sectorBreakdown, sectorSymbolBreakdown}
  // shape build() used to compute ONLY per-account. build() itself now
  // calls this once per account (below) so the Account path can't drift
  // from what By-Asset-Class-root/By-Source use; renderAssetClassFlat/
  // renderSectorWithinAsset call it directly, on the fly, with a source-
  // filtered or whole-portfolio POS subset when there's no single account
  // to look a precomputed map up by. User: "Now, do the same when you
  // choose all other options starting with By Asset Class, By Source etc.
  // all applicable data" -- 2026-09-06.
  function computeScopedBreakdown(posRows) {
    const gain = { costBasis: 0, totalGainDollar: 0, todayGainDollar: 0 };
    const counts = { buy: 0, sell: 0, buySymbols: [], sellSymbols: [] };
    const assetTmp = new Map();
    const sectorTmp = new Map();
    const sectorSymbolsTmp = new Map();
    posRows.forEach(r => {
      if (r.cost_basis != null) gain.costBasis += r.cost_basis;
      if (r.total_gain_dollar != null) gain.totalGainDollar += r.total_gain_dollar;
      if (r.today_gain_dollar != null) gain.todayGainDollar += r.today_gain_dollar;
      const det = symbolDetail.get(r.tos_symbol);
      const side = actionSide(det?.final_code);
      if (side === 'buy' || side === 'sell') { counts[side] += 1; counts[`${side}Symbols`].push(r.tos_symbol); }
      // Simple per-symbol Bullish/Bearish read (rr_outlook -- "Bullish"/
      // "Mild Bullish"/.../"Bearish", same field/prefix-match convention
      // drv_dash_summary's own n_bullish/n_bearish counts already use
      // whole-portfolio) -- tallied per asset-class/sector row below.
      // Drives the Asset Class legend's outlook caret directly; for the
      // Sector legend it's only a fallback for a sector with no SPDR ETF
      // reading available (see SECTOR_ETF/appendOutlookCaret -- the normal
      // path there uses the sector ETF's own single rr_outlook instead of
      // this crowd tally, since 100+ mostly-unheld symbols voting can
      // disagree with the sector's own tracking ETF). User: "Don't i have
      // a simple Bullish or Bearish signal?" -> "Just display one, rr
      // outlook" -- 2026-09-06.
      const dir = _outlookDir(det && det.rr_outlook);
      const ae = assetTmp.get(r.asset_class) || { value: 0, count: 0, costBasis: 0, gainDollar: 0, todayGainDollar: 0, buy: 0, sell: 0, buySymbols: [], sellSymbols: [], rrBullish: 0, rrBearish: 0 };
      ae.value += (r.market_value || 0); ae.count += 1;
      if (r.cost_basis != null) ae.costBasis += r.cost_basis;
      if (r.total_gain_dollar != null) ae.gainDollar += r.total_gain_dollar;
      if (r.today_gain_dollar != null) ae.todayGainDollar += r.today_gain_dollar;
      if (side === 'buy' || side === 'sell') { ae[side] += 1; ae[`${side}Symbols`].push(r.tos_symbol); }
      if (dir === 'up') ae.rrBullish += 1; else if (dir === 'down') ae.rrBearish += 1;
      assetTmp.set(r.asset_class, ae);
      if (r.asset_class === 'Equities') {
        const se = sectorTmp.get(r.sector) || { value: 0, count: 0, costBasis: 0, gainDollar: 0, todayGainDollar: 0, buy: 0, sell: 0, buySymbols: [], sellSymbols: [], rrBullish: 0, rrBearish: 0 };
        se.value += (r.market_value || 0); se.count += 1;
        if (r.cost_basis != null) se.costBasis += r.cost_basis;
        if (r.total_gain_dollar != null) se.gainDollar += r.total_gain_dollar;
        if (r.today_gain_dollar != null) se.todayGainDollar += r.today_gain_dollar;
        if (side === 'buy' || side === 'sell') { se[side] += 1; se[`${side}Symbols`].push(r.tos_symbol); }
        if (dir === 'up') se.rrBullish += 1; else if (dir === 'down') se.rrBearish += 1;
        sectorTmp.set(r.sector, se);

        const symList = sectorSymbolsTmp.get(r.sector) || [];
        symList.push({
          tos_symbol: r.tos_symbol, value: r.market_value || 0, count: 1,
          costBasis: r.cost_basis || 0, gainDollar: r.total_gain_dollar || 0,
        });
        sectorSymbolsTmp.set(r.sector, symList);
      }
    });
    const assetBreakdown = [...assetTmp.entries()]
      .map(([asset_class, v]) => ({ asset_class, ...v }))
      .sort((a, b) => b.value - a.value);
    const sectorBreakdown = [...sectorTmp.entries()]
      .map(([sector, v]) => ({ sector, ...v }))
      .sort((a, b) => b.value - a.value);
    const sectorSymbolBreakdown = new Map();
    sectorSymbolsTmp.forEach((rows, sector) => sectorSymbolBreakdown.set(sector, [...rows].sort((a, b) => b.value - a.value)));
    return { gain, counts, assetBreakdown, sectorBreakdown, sectorSymbolBreakdown };
  }

  // Resolves the P&L/breakdown data for whatever scope `drill` currently
  // represents -- an account's precomputed maps (fast path, unchanged
  // since build() time), a source's positions (filtered on the fly, since
  // a symbol's `sources` membership isn't a POS-row field), or the whole
  // portfolio (no filter at all -- the "By Asset Class"/"By Source" ROOT
  // level, before any account/source is chosen). Same reason as
  // computeScopedBreakdown's own comment above.
  function scopedBreakdownFor(drill) {
    if (drill && drill.account) {
      return {
        gain: acctGain.get(drill.account),
        counts: acctActionCounts.get(drill.account),
        assetBreakdown: acctAssetBreakdown.get(drill.account) || [],
        sectorBreakdown: acctSectorBreakdown.get(drill.account) || [],
        sectorSymbolBreakdown: acctSectorSymbolBreakdown.get(drill.account) || new Map(),
      };
    }
    if (drill && drill.source) {
      const src = drill.source;
      return computeScopedBreakdown(POS.filter(r => (symbolDetail.get(r.tos_symbol)?.sources || []).includes(src)));
    }
    return computeScopedBreakdown(POS);
  }

  function build(payload) {
    SYMS = (payload.symbols || []).map(r => ({
      ...r,
      sector: normSector(r.sector, r.is_macro_instrument),
      asset_class: normAssetClass(r.asset_class),
      style_tags: r.style_tags || [],
      sources: r.sources || [],
    }));
    const sectorOf = new Map(SYMS.map(r => [r.tos_symbol, r.sector]));
    const assetClassOf = new Map(SYMS.map(r => [r.tos_symbol, r.asset_class]));
    symbolDetail = new Map(SYMS.map(r => [r.tos_symbol, r]));
    POS = (payload.positions || [])
      .filter(r => r.tos_symbol && sectorOf.has(r.tos_symbol))
      .map(r => ({ ...r, sector: sectorOf.get(r.tos_symbol), asset_class: assetClassOf.get(r.tos_symbol) || 'Unclassified' }));

    const accts = payload.accounts || [];
    acctLabelMap = new Map(accts.map(a => [a.account_number, a.display_name || a.short_name || a.account_number]));

    symbolAccounts = new Map();
    POS.forEach(r => {
      const label = acctLabelMap.get(r.account_id) || r.account_id;
      const arr = symbolAccounts.get(r.tos_symbol) || [];
      if (!arr.includes(label)) arr.push(label);
      symbolAccounts.set(r.tos_symbol, arr);
    });

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
    // account_id -> that account's own POS rows, grouped once so
    // computeScopedBreakdown (the single shared aggregator every scope --
    // account, source, whole-portfolio -- now goes through) can run once
    // per account instead of a second, parallel hand-rolled loop that
    // could quietly drift from what the other scopes compute. User: "Now,
    // do the same when you choose all other options starting with By
    // Asset Class, By Source etc. all applicable data" -- 2026-09-06.
    const posByAccount = new Map();
    POS.forEach(r => {
      acctTotals.set(r.account_id, (acctTotals.get(r.account_id) || 0) + (r.market_value || 0));
      posCounts.set(r.account_id, (posCounts.get(r.account_id) || 0) + 1);
      let arr = posByAccount.get(r.account_id);
      if (!arr) { arr = []; posByAccount.set(r.account_id, arr); }
      arr.push(r);
    });
    acctGain = new Map();
    acctActionCounts = new Map();
    acctAssetBreakdown = new Map();
    acctSectorBreakdown = new Map();
    acctSectorSymbolBreakdown = new Map();
    posByAccount.forEach((rows, acctId) => {
      const b = computeScopedBreakdown(rows);
      acctGain.set(acctId, b.gain);
      acctActionCounts.set(acctId, b.counts);
      acctAssetBreakdown.set(acctId, b.assetBreakdown);
      acctSectorBreakdown.set(acctId, b.sectorBreakdown);
      acctSectorSymbolBreakdown.set(acctId, b.sectorSymbolBreakdown);
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
    realizedByAccount = new Map((payload.realized_by_account || []).map(r => [r.account_id, r]));
    dividendsByAccount = new Map((payload.dividends_by_account || []).map(r => [r.account_id, r]));
    ACCOUNTS = [...acctTotals.entries()]
      .map(([key, total]) => ({ key, label: acctLabelMap.get(key) || key, total, posCount: posCounts.get(key) || 0 }))
      .sort((a, b) => b.total - a.total);
    acctColor = new Map(ACCOUNTS.map((a, i) => [a.key, ACCOUNT_COLOR_SLOTS[i % ACCOUNT_COLOR_SLOTS.length]]));

    // 2026-09-03 (held-perspective proposal): portfolio-wide KPI totals.
    // Total securities/cash come from ACCOUNTS (already the securities+cash
    // total per account); unrealized P&L is summed from SYMS (held) rather
    // than POS so it covers the full drv_actionable-known universe, not
    // just the subset POS kept (POS drops a symbol with no sector match --
    // see its own filter in build() above). Realized is summed from the
    // per-account rollup since that's all the API returns (no single
    // portfolio-wide total row).
    const totalCash = d3.sum([...cashByAccount.values()]);
    const totalPortfolio = d3.sum(ACCOUNTS, a => a.total);
    const heldSyms = SYMS.filter(r => r.held_today);
    const totalCostBasis = d3.sum(heldSyms, r => r.cost_basis || 0);
    const totalUnrealizedDollar = d3.sum(heldSyms, r => r.total_gain_dollar || 0);
    const totalTodayDollar = d3.sum(heldSyms, r => r.today_gain_dollar || 0);
    const realizedRows = payload.realized_by_account || [];
    KPI = {
      totalPortfolio, totalCash,
      totalSecurities: totalPortfolio - totalCash,
      totalUnrealizedDollar,
      totalUnrealizedPct: totalCostBasis ? (totalUnrealizedDollar / totalCostBasis * 100) : null,
      totalTodayDollar,
      totalRealizedYtd: d3.sum(realizedRows, r => r.ytd_realized || 0),
      totalRealizedAll: d3.sum(realizedRows, r => r.total_realized || 0),
      accountCount: ACCOUNTS.length,
    };

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

    // Source ranked on the FULL universe too, same reason -- a source's
    // color stays the same whichever Filter tab (All/Held/Actionable) is
    // active, since (unlike Account) the Source root's own tile SET does
    // change with that filter.
    const SOURCE_RANK = aggregateSources(SYMS);
    sourceColorAssign = new Map();
    SOURCE_RANK.forEach((d, i) => sourceColorAssign.set(d.source, i < CAT_SLOTS.length ? CAT_SLOTS[i] : '--cat-unmapped'));
  }

  // ---------------------------------------------------------------------
  // Colors / formulas shared by every tile level
  // ---------------------------------------------------------------------
  function luminanceRgb(r, g, b) {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }
  function luminance(hex) { const c = d3.rgb(hex); return luminanceRgb(c.r, c.g, c.b); }
  const labelColorFor = hex => luminance(hex) > 0.42 ? '#1c1917' : '#ffffff';
  // WCAG contrast ratio between two hex colors.
  function contrastRatio(hex1, hex2) {
    const a = luminance(hex1), b = luminance(hex2);
    const hi = Math.max(a, b), lo = Math.min(a, b);
    return (hi + 0.05) / (lo + 0.05);
  }
  // Blends `base` (a semantic red/green) toward `toward` (the tile's own
  // `ink` -- white on a dark tile, black on a light one) just far enough to
  // clear `target` contrast against `bg`, so the result stays as close to
  // "red"/"green" as legibility allows instead of one fixed hex that reads
  // fine on some account colors and is nearly invisible on others (checked:
  // a flat #dc2626/#16a34a bottoms out around 1.0-2.0 contrast on --cat2/
  // --cat3/--cat5). Falls back to `toward` itself (ink) if even a full
  // blend can't clear the target -- still guaranteed legible, just no
  // longer tinted. User: "is there a way to represent -ves in some kind of
  // red version" -- 2026-09-05.
  function legibleTint(bg, base, toward, target) {
    const from = d3.rgb(base), to = d3.rgb(toward);
    for (let t = 0; t <= 1.0001; t += 0.05) {
      const r = Math.round(from.r + (to.r - from.r) * t);
      const g = Math.round(from.g + (to.g - from.g) * t);
      const bl = Math.round(from.b + (to.b - from.b) * t);
      if (contrastRatio(bg, `rgb(${r},${g},${bl})`) >= target) return `rgb(${r},${g},${bl})`;
    }
    return toward;
  }

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

  // Tile fill -- always the trading-signal action color. Used to also
  // switch to a Gain/Loss-interpolated fill via a Color-by toggle
  // (2026-09-03, "held-perspective proposal"); removed per "Remove signal
  // gain/loss toggle and display both signal and gain/loss information in
  // the tile" -- 2026-09-06 -- gain/loss is no longer a fill-color choice,
  // it's unconditionally shown as its own Unrealized/Today text lines
  // (appendSymbolBreakdown-adjacent code below) alongside the signal
  // fill/badge, so both are visible on every tile at once instead of
  // either/or.
  function tileColor(det) {
    return actionColor(det.final_code);
  }
  const fmtSignedUsd = v => (v >= 0 ? '+' : '') + fmtUsd(v);
  const fmtSignedPct1 = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
  // Small colored "+$X (+Y%)" span for tooltips -- green/red, same convention
  // as the tile's own Td/Tn line coloring (above/below = green/red).
  function gainSpanHtml(dollar, pct) {
    if (dollar == null) return '';
    const color = dollar >= 0 ? '#16a34a' : '#dc2626';
    const pctTxt = pct != null ? ` (${fmtSignedPct1(pct)})` : '';
    return `<span style="color:${color};font-weight:700;">${fmtSignedUsd(dollar)}${pctTxt}</span>`;
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
  let currentView = 'account'; // 'assetclass' | 'account' | 'source' -- which hierarchy's root is showing; defaults to Account
  // "All My Stocks" button -- orthogonal to currentView/drill: when true,
  // every grouping level (account, source, asset class, sector) is
  // skipped and every held symbol across every account renders as flat
  // symbol tiles on one screen (renderAllStocksFlat). User: "no drill
  // down at the account level, all accounts combined." Cleared by
  // clicking any View tab (see wireStaticControls).
  let flatStocksMode = false;
  let sizeMode = 'count';         // 'count' | 'capital' -- what sizes every tile at every level
  // Held to match the 'account' default above -- "By Account" only ever
  // means anything for held positions, same rule wireStaticControls
  // enforces on every subsequent view click (see its own comment).
  let currentFilter = 'held';
  // 'all' | 'buy' | 'sell' | 'hold' -- narrows the drilldown (stock) tiles
  // by trading signal; has no effect above the drilldown level.
  let currentColorFilter = 'all';
  // 'all' or one tag from ALL_STYLE_TAGS -- same scope as Color.
  let currentStyleFilter = 'all';
  // Risk Range position band (0-100, clamped -- same scale the mini RR
  // bar itself uses), same scope as Color/Style -- narrows symbol tiles
  // to a rawRrPos() range, via the #uvRrMin/#uvRrMax dual-thumb slider.
  let rrMin = 0, rrMax = 100;
  // Unified drill path, shared by all three hierarchies: null (root) or
  // { account?, source?, assetClass?, sector? } -- built progressively.
  // "By Asset Class" never sets `account`/`source`; "By Account" sets
  // `account` first and "By Source" sets `source` first, then the same
  // assetClass/sector legs follow underneath either one.
  let drill = null;
  function resetDrill() { drill = null; }
  // Sentinel for drill.sector meaning "every sector, flattened" -- set by
  // the Equities tile's small "All stocks" link (renderAssetClassFlat),
  // which skips the Sector grouping step and goes straight to a flat list
  // of every equity symbol in scope. Not a real sector name, so it's
  // rendered as "All stocks" in the breadcrumb rather than shown raw.
  const ALL_SECTORS = '__ALL_SECTORS__';
  // Sentinel for drill.assetClass meaning "every asset class, flattened" --
  // only reachable via the Equities tile's "All stocks" link while inside
  // an account (By Account path). User: "only going through the By
  // account i need to see all stocks for the account when i click on all
  // stocks" -- there, "all stocks" means every position in that account
  // (bonds/FX/etc included), not just the equity subset the same link
  // gives you from the whole-universe root (where there's no single
  // account to unify around, so it stays Equities-only there).
  const ALL_ASSET_CLASSES = '__ALL_ASSET_CLASSES__';

  let FILTERS = {}; // {all|held|actionable: {note, rows: [SYMS...]}}

  // The symbol-shaped rows the CURRENT drill level's hierarchy is built
  // from. Once an account is chosen (drill.account set), scope narrows to
  // just that account's positions; once a source is chosen (drill.source),
  // scope narrows to the current Filter's rows that carry that source tag
  // (a row can carry several, so this is a filter, not a partition -- same
  // membership rule aggregateSources() itself uses). Otherwise it's the
  // whole filtered universe. Same {tos_symbol,...} shape either way
  // (posAsSymRow adapts POS to match), so buildAssetHierarchy doesn't care
  // which source it got.
  function currentScopeRows() {
    if (drill && drill.account) return POS.filter(r => r.account_id === drill.account).map(posAsSymRow);
    if (drill && drill.source) return FILTERS[currentFilter].rows.filter(r => (r.sources || []).includes(drill.source));
    return FILTERS[currentFilter].rows;
  }

  // True when the current state's render would show individual symbol
  // tiles (renderSymbolTiles) rather than a group-level rollup (Account /
  // Asset Class / Sector tiles) -- Color and Style only affect symbol
  // tiles, so those controls are hidden everywhere else. Mirrors
  // renderHierarchy's own dispatch exactly, without running it.
  function atSymbolLevel() {
    if (flatStocksMode) return true; // "All My Stocks" -- always flat symbol tiles
    if (currentView === 'account' && !(drill && drill.account)) return false; // Account root
    if (currentView === 'source' && !(drill && drill.source)) return false; // Source root
    if (!drill || !drill.assetClass) return false; // Asset Class tiles
    if (drill.assetClass === ALL_ASSET_CLASSES) return true; // "All stocks" (whole account)
    if (!drill.sector) return drill.assetClass !== 'Equities'; // Equities -> Sector tiles; others -> symbols directly
    return true; // a sector (or ALL_SECTORS) is chosen -> symbol tiles
  }

  // 2026-09-03 (held-perspective proposal), condensed 2026-09-06: portfolio-
  // wide KPI summary, right-justified on the filter bar itself
  // (.uv-hdr's own justify-content:space-between). Rendered once from
  // build()'s KPI totals -- NOT re-rendered inside render(), since it
  // deliberately does not follow the current View/Filter/drill (it's
  // "what does my whole book look like", not "what's in the current
  // treemap"). One dot-separated line -- Total/YTD/Cash/Today -- replacing
  // the old 6-card strip; Unrealized P&L and Accounts dropped from this
  // condensed line (still computed on KPI for anything that wants them
  // later) since 4 figures is what was asked for. User: "is there a way
  // to display Total portfolio/YTD/Cash/Today in concise manner on the
  // top filter bar right justified" -- 2026-09-06.
  function renderKpiStrip() {
    if (!KPI) return;
    const gainCls = v => v >= 0 ? 'uv-gain-pos' : 'uv-gain-neg';
    const gainSpan = v => `<span class="${gainCls(v)}">${fmtSignedUsd(v)}</span>`;
    $('uvHdrKpis').innerHTML =
      `Total <b>${fmtUsd(KPI.totalPortfolio)}</b>` +
      `<span class="uv-kpi-sep">·</span>YTD <b>${gainSpan(KPI.totalRealizedYtd)}</b>` +
      `<span class="uv-kpi-sep">·</span>Cash <b>${fmtUsd(KPI.totalCash)}</b>` +
      `<span class="uv-kpi-sep">·</span>Today <b>${gainSpan(KPI.totalTodayDollar)}</b>`;
  }

  function render() {
    // sizeMode only means anything under Source -- All/Account/Asset don't
    // have a meaningful "count vs $" distinction (their own tile sizing/
    // legend %s are always dollar-based already, see the "% and $K must
    // match" fix earlier this session), so it's forced to Capital there.
    // Resolved BEFORE the aria-selected sync below, not after -- doing it
    // after left the tab UI showing a stale selection on the very first
    // render even though sizeMode itself had already flipped. User:
    // "Filter Count|Capital -> doesn't appply for first three radio
    // button options... Always use Capital option" -- 2026-09-06.
    if (flatStocksMode || currentView !== 'source') sizeMode = 'capital';
    // One combined data-view radio group -- All|Account|Asset|Src#|Src$.
    // "All" is its own value (selected whenever flatStocksMode is on,
    // ignoring currentView, same as before it was a separate toggle
    // button). Src#/Src$ carry BOTH data-view="source" AND their own
    // data-size, so a tab only reads as selected when currentView AND (if
    // it has one) sizeMode both match -- otherwise Src$ would show
    // selected while looking at Account just because sizeMode happened to
    // still be 'capital' from a previous Source visit. There's no longer
    // any element with ONLY data-size (no standalone Size row exists any
    // more), so this one loop replaces what used to be two separate
    // syncs. User: "Combine first two radio buttons... into one as
    // All|Account|Asset and separate By source into its own as Source"
    // -- 2026-09-06, then "Why do you need Source still? Can we combine
    // Src#|Src$ with All|Account|Asset" -- 2026-09-06.
    document.querySelectorAll('.uv-tab[data-view]').forEach(t => {
      let selected;
      if (t.dataset.view === 'all') selected = flatStocksMode;
      else if (t.dataset.size) selected = !flatStocksMode && t.dataset.view === currentView && t.dataset.size === sizeMode;
      else selected = !flatStocksMode && t.dataset.view === currentView;
      t.setAttribute('aria-selected', String(selected));
    });
    document.querySelectorAll('.uv-tab[data-filter]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.filter === currentFilter)));
    document.querySelectorAll('.uv-tab[data-color]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.color === currentColorFilter)));
    document.querySelectorAll('.uv-tab[data-style]').forEach(t => t.setAttribute('aria-selected', String(t.dataset.style === currentStyleFilter)));
    // Filter (All/Held/Actionable) isn't a real choice under "By Account"
    // -- it's forced to Held there (see wireStaticControls) -- so hide it
    // instead of showing a 3-way selector that silently reverts you to
    // "By Asset Class" if you touch anything but Held. Same reason under
    // "All My Stocks" -- it's held positions by definition.
    $('uvFilterRow').hidden = currentView === 'account' || flatStocksMode;
    // Color/Style/Risk Range only affect individual symbol tiles -- hide
    // them at every group level (Account root, Asset Class, Sector) where
    // they'd have no visible effect.
    const showSymbolFilters = atSymbolLevel();
    $('uvColorRow').hidden = !showSymbolFilters;
    $('uvStyleRow').hidden = !showSymbolFilters;
    $('uvRrRow').hidden = !showSymbolFilters;

    if (flatStocksMode) { renderAllStocksFlat(); return; }
    if (currentView === 'account' && !(drill && drill.account)) { renderAccountRoot(); return; }
    if (currentView === 'source' && !(drill && drill.source)) { renderSourceRoot(); return; }
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
    $('uvFilterCount').textContent = '';

    renderCrumbs();
    $('uvSideHeading').textContent = 'Top accounts';

    const wrap = document.querySelector('.uv-svg-wrap');
    const W = wrap.clientWidth, H = wrap.clientHeight;
    svg.attr('viewBox', `0 0 ${W} ${H}`);

    if (ACCOUNTS.length === 0) {
      svg.selectAll('*').remove();
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text('No held positions to break out by account.');
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

  // ---- "All My Stocks": every held symbol, every account combined, as
  // flat individual tiles -- no Account/Source/Asset Class/Sector grouping
  // at all. `current_position_dollar` on a SYMS row is already the
  // symbol's TOTAL held $ across every account (drv_actionable is one row
  // per symbol, not per account -- POS, the per-account breakdown, isn't
  // needed here), so this is just SYMS filtered to held, no aggregation.
  function renderAllStocksFlat() {
    const rows = SYMS.filter(r => r.held_today);
    const sectorCount = new Set(rows.map(r => r.sector)).size;

    $('uvTotalCount').textContent = fmtInt(rows.length);
    $('uvTotalSectors').textContent = sectorCount;
    $('uvSectorsUnit').textContent = 'sectors';
    $('uvSHeld').textContent = rows.length + ' symbols';
    $('uvSCapital').textContent = fmtUsd(d3.sum(rows, r => r.current_position_dollar || 0));
    $('uvFilterCount').textContent = '';

    const crumbEl = $('uvCrumbs');
    crumbEl.innerHTML = `<span class="uv-crumb" data-crumb="root">Universe</span>` +
      `<span class="uv-crumb-sep">/</span><span class="uv-crumb current">All My Stocks</span>`;
    crumbEl.querySelectorAll('[data-crumb="root"]').forEach(e => e.addEventListener('click', () => { flatStocksMode = false; render(); }));
    $('uvSideHeading').textContent = 'Top holdings';

    const wrap = document.querySelector('.uv-svg-wrap');
    const W = wrap.clientWidth, H = wrap.clientHeight;
    svg.attr('viewBox', `0 0 ${W} ${H}`);

    if (rows.length === 0) {
      svg.selectAll('*').remove();
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text('No held positions.');
      $('uvRankList').innerHTML = ''; $('uvSLargest').textContent = '—';
      return;
    }

    const tileRows = rows.map(r => ({ tos_symbol: r.tos_symbol, value: r.current_position_dollar || 0, detail: r }));
    renderSymbolTiles(tileRows, W, H);

    // side panel -- top holdings by $ regardless of Size mode (Count
    // sizing makes every tile here weigh the same, so it has no natural
    // per-symbol ranking of its own; Capital is the meaningful one).
    const ranklist = $('uvRankList');
    const top = [...rows].sort((a, b) => (b.current_position_dollar || 0) - (a.current_position_dollar || 0)).slice(0, 8);
    ranklist.innerHTML = top.map(d => {
      const dot = actionColor(d.final_code);
      return `<li class="uv-rank-row"><span class="uv-rank-dot" style="background:${dot};"></span>` +
        `<span class="uv-rank-name">${esc(d.tos_symbol)}</span><span class="uv-rank-val">${fmtUsd(d.current_position_dollar || 0)}</span></li>`;
    }).join('');
    $('uvSLargest').textContent = top[0] ? top[0].tos_symbol : '—';
  }

  // ---- Shared hierarchy renderer: Asset Class -> Sector (Equities only)
  // -> Symbol, for whichever `scope` currentScopeRows() resolves (whole
  // universe for "By Asset Class", one account's positions for "By
  // Account" past its root level). ------------------------------------
  function renderHierarchy() {
    const scope = currentScopeRows();
    const hier = buildAssetHierarchy(scope);
    const inAccount = !!(drill && drill.account);
    // "in {scope}" label for either an account or a source drill leg --
    // same treatment, just a different lookup for the display label
    // (accounts have a friendly display_name; sources are shown as-is).
    const scopeLabel = inAccount ? (acctLabelMap.get(drill.account) || drill.account)
      : (drill && drill.source) ? drill.source : null;

    $('uvTotalCount').textContent = fmtInt(scope.length);
    $('uvTotalSectors').textContent = hier.agg.length;
    $('uvSectorsUnit').textContent = 'asset classes';
    $('uvSHeld').textContent = d3.sum(hier.agg, d => d.held) + ' symbols';
    $('uvSCapital').textContent = fmtUsd(d3.sum(hier.agg, d => d.held_value));
    $('uvFilterCount').textContent = scopeLabel ? `— in ${scopeLabel}` : '';

    renderCrumbs();
    $('uvSideHeading').textContent = scopeLabel ? `Top asset classes in ${scopeLabel}` : 'Top asset classes';

    const wrap = document.querySelector('.uv-svg-wrap');
    const W = wrap.clientWidth, H = wrap.clientHeight;
    svg.attr('viewBox', `0 0 ${W} ${H}`);

    if (scope.length === 0) {
      svg.selectAll('*').remove();
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text('No symbols match this filter.');
      $('uvRankList').innerHTML = ''; $('uvSLargest').textContent = '—';
      return;
    }

    if (!drill || !drill.assetClass) {
      // Preserve whichever root leg (account or source) got us here --
      // same `parent` pattern renderCrumbs() uses.
      const parent = inAccount ? { account: drill.account } : (drill && drill.source) ? { source: drill.source } : {};
      renderAssetClassFlat(hier.agg, W, H,
        ac => { drill = { ...parent, assetClass: ac }; render(); },
        ac => {
          drill = inAccount
            ? { account: drill.account, assetClass: ALL_ASSET_CLASSES } // whole account, every asset class
            : { ...parent, assetClass: ac, sector: ALL_SECTORS };       // whole universe / one source: Equities only, flat
          render();
        });
    } else if (drill.assetClass === ALL_ASSET_CLASSES) {
      // "All stocks" link, taken from inside an account -- every position
      // in that account, regardless of asset class. `scope` is already
      // exactly that (currentScopeRows() narrows to the account once
      // drill.account is set), so no further filtering needed.
      const rows = scope.map(r => ({ tos_symbol: r.tos_symbol, value: r.current_position_dollar || 0, detail: symbolDetail.get(r.tos_symbol) || {} }));
      renderSymbolTiles(rows, W, H);
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

  // Guard for the group-level tiles' (Account/Source/Asset Class/Sector)
  // hover tooltip -- true only when the pointer is actually over that
  // tile's own `.uv-c-name` header text, not anywhere else on the tile.
  // Used as an early-return check inside each `cell.on('mousemove', ...)`
  // handler below (still bound to the whole tile group -- mousemove keeps
  // firing continuously as the pointer moves inside it, so this just makes
  // the tooltip itself only actually show/stay up while the target is the
  // header) rather than rebinding each handler onto the child text
  // selection, which stock tiles' own new hover popover does instead
  // (mouseenter/mouseleave bound directly to `.uv-c-name`, a cleaner fit
  // there since that's a per-tile popover, not a shared single `tt` div
  // reused across every open/close cycle the way this tooltip is). User:
  // "On all universe screen -> make the popover pops up only when i hover
  // over the header, for ex, hover on account name, source name, stock
  // name etc" -- 2026-09-06.
  function _uvOverHeader(evt) {
    return !!(evt.target && evt.target.closest && evt.target.closest('.uv-c-name'));
  }

  // Breadcrumb for the unified drill path (account?/source? -> assetClass?
  // -> sector?) -- works for all three hierarchies since it just walks
  // whichever legs `drill` has set.
  function renderCrumbs() {
    const el = $('uvCrumbs');
    if (!drill) { el.innerHTML = ''; return; }
    const segs = [];
    if (drill.account) segs.push({ key: 'account', label: acctLabelMap.get(drill.account) || drill.account });
    if (drill.source) segs.push({ key: 'source', label: drill.source });
    if (drill.assetClass && drill.assetClass !== ALL_ASSET_CLASSES) segs.push({ key: 'assetClass', label: drill.assetClass });
    if (drill.assetClass === ALL_ASSET_CLASSES) segs.push({ key: 'assetClass', label: 'All stocks' });
    if (drill.sector) segs.push({ key: 'sector', label: drill.sector === ALL_SECTORS ? 'All stocks' : drill.sector });
    if (segs.length === 0) { el.innerHTML = ''; return; }

    const parts = [`<span class="uv-crumb" data-crumb="root">Universe</span>`];
    segs.forEach((s, i) => {
      parts.push(`<span class="uv-crumb-sep">/</span>`);
      const isLast = i === segs.length - 1;
      parts.push(isLast ? `<span class="uv-crumb current">${esc(s.label)}</span>` : `<span class="uv-crumb" data-crumb="${s.key}">${esc(s.label)}</span>`);
    });
    el.innerHTML = parts.join('');
    // `parent` carries whichever root leg (account or source) the current
    // drill has, so re-clicking the assetClass crumb keeps it instead of
    // dropping back to the whole-universe root.
    const parent = drill.account ? { account: drill.account } : drill.source ? { source: drill.source } : {};
    el.querySelectorAll('[data-crumb="root"]').forEach(e => e.addEventListener('click', () => { drill = null; render(); }));
    el.querySelectorAll('[data-crumb="account"]').forEach(e => e.addEventListener('click', () => { drill = { account: drill.account }; render(); }));
    el.querySelectorAll('[data-crumb="source"]').forEach(e => e.addEventListener('click', () => { drill = { source: drill.source }; render(); }));
    el.querySelectorAll('[data-crumb="assetClass"]').forEach(e => e.addEventListener('click', () => { drill = { ...parent, assetClass: drill.assetClass }; render(); }));
  }

  // Draws a group tile's name (+ optional sub-line, if there's room) --
  // shared by every group-level tile renderer (Account / Asset Class /
  // Sector) so the "how small can a tile be before it goes label-less"
  // rule is the same everywhere. User: "Some tiles are blank. By asset
  // class -> equities" -- the old cutoff (46x26) left plenty of
  // legitimately smaller-but-not-tiny sector tiles with no name at all
  // (just a colored box); lowered so a tile only goes unlabeled once it's
  // genuinely too small to hold even an abbreviated name.
  // Shared "N sym · $value (X%)" subtitle text -- ONE %, on whichever
  // figure actually sizes the tile (the treemap's own rawValueFn, always
  // $ value now that Count/Capital is forced to Capital for these views --
  // see render()'s own comment). Not a % for the symbol count too --
  // that's not what determines the tile's area, so a % next to it would
  // just be a second, unrelated number, not "how big is this tile".
  // Computed against `totalValue` (the SAME set of tiles actually
  // rendered, so percentages sum to ~100% among what's on screen). Used
  // by every group-level tile renderer (Source/Asset Class/Sector; Account
  // has its own slightly different "all cash" variant, see
  // renderAccountFlat). User: "Display % of tile occupation between
  // number of symbols and $$ (which is below the header, ex, equities)"
  // -- 2026-09-06, then "No. Only one not two. The measurement you are
  // using for tile. i belive it is amount." -- 2026-09-06.
  function groupTileSubText(count, value, totalValue) {
    const valuePct = totalValue ? Math.round(value / totalValue * 100) : 0;
    return `${fmtInt(count)} sym · ${fmtUsd(value)} (${valuePct}%)`;
  }

  function drawGroupTileLabel(g, w, h, ink, name, subText) {
    if (w < 22 || h < 12) return; // truly too small for even 1-2 characters
    const fontSize = w < 50 ? 8 : (w < 90 ? 9.5 : 11);
    const nameY = h < 18 ? Math.max(9, Math.round(h / 2) + 3) : 16;
    const maxChars = Math.max(1, Math.floor((w - 6) / (fontSize * 0.62)));
    g.append('text').attr('class', 'uv-c-name').attr('x', 5).attr('y', nameY)
      .attr('font-size', fontSize).attr('fill', ink)
      .text(name.length > maxChars ? name.slice(0, Math.max(1, maxChars - 1)) + '…' : name);
    if (subText && h > 40) {
      g.append('text').attr('class', 'uv-c-sub').attr('x', 7).attr('y', 30)
        .attr('font-size', 9.5).attr('fill', ink).attr('opacity', 0.85).text(subText);
    }
  }

  // Draws the "Stocks →" corner-link shared by every top-level tile that
  // has sublevels underneath it (Account, Source, Equities-within-Asset-
  // Class). User: "make sure last account tile has it visible" -- squarify
  // hands the smallest item whichever thin shape the data produces: a WIDE
  // short strip in some layouts, a TALL narrow column in others (confirmed
  // via the live page's own DOM -- the real "last" tile came back w=53
  // h=337, the opposite orientation from the wide-strip case this was
  // first fixed for). One fixed w/h gate can't cover both, so this now
  // picks between two layouts: "row" -- link right-aligned beside the name
  // on the same line (needs width) -- when there's room, else "stacked" --
  // link on its own line below the name/subtitle (needs height instead).
  // `stackY` -- where the stacked (narrow-tile) layout starts, default 44
  // (right after name+subtitle, the old fixed spot) for Source/Equities
  // callers that draw nothing else below the subtitle. The Account tile
  // caller passes the real y-cursor appendAccountPnlAndSignals returns
  // instead, so this link stacks below whatever P&L/signal lines actually
  // rendered rather than overwriting them at a stale fixed y.
  function canShowCornerLink(w, h, stackY = 44) { return (w > 78 && h > 13) || (w > 40 && h > stackY + 4); }
  function cornerLinkY(h) { return h < 22 ? Math.max(9, Math.round(h / 2) + 3) : 16; }
  function appendCornerLink(g, w, h, ink, onClick, stackY = 44) {
    const t = g.append('text').attr('class', 'uv-c-link').attr('font-size', 8.5).attr('font-weight', 700)
      .attr('fill', ink).style('text-decoration', 'underline').style('cursor', 'pointer')
      .text('Stocks →')
      .on('click', evt => { evt.stopPropagation(); onClick(); });
    if (w > 78 && h > 13) {
      t.attr('x', w - 6).attr('y', cornerLinkY(h)).attr('text-anchor', 'end');
    } else {
      t.attr('x', 5).attr('y', stackY).attr('text-anchor', 'start');
    }
  }

  // Account tile "what's happening" extras -- unrealized P&L, today's $
  // move, and a BUY/SELL signal count. User: "top level -> tile has space
  // -> what can you show me so i know exactly what is happening to my
  // accounts" -- 2026-09-05, chose "Combine P&L + signals".
  //
  // Each line WRAPS (via the existing wrapTokens greedy wrapper, same one
  // the sample-ticker line uses) onto up to 2 rows instead of just not
  // showing at all once the text is wider than the tile -- user: "last
  // tile doesn't show all the info, wrap the information so it displays
  // the info" -- 2026-09-05, after the original w > 100 hard cutoff (fine
  // on roomy tiles, but hid this whole block on any narrow-but-tall tile,
  // including the exact "last tile" shape the "Stocks →" link itself had
  // to be fixed for earlier). Returns the y-cursor after the last line
  // actually drawn, so the caller's "Stocks →" link -- which shares this
  // same left column when the tile's too narrow for its own row layout --
  // can stack below whatever did fit instead of at a fixed y that might
  // already be occupied.
  //
  // Text color: a real red/green, not `ink` flat -- but tinted toward
  // `ink` (legibleTint) rather than a fixed hex, since a flat #dc2626/
  // #16a34a bottoms out around a 1.0-2.0 WCAG contrast ratio on several
  // account colors (teal/brown/pink especially), well under the ~3:1 floor
  // this text size needs, and no single green/red pair clears that floor
  // on all five. The ▲/▼ glyph still backs up the color for direction,
  // same trick this file's own Td/Tn arrow already uses. User: "is there a
  // way to represent -ves in some kind of red version" -- 2026-09-05,
  // after "check colors for fonts and background... choose contrast
  // colors" (the flat-ink fallback that immediately preceded this).
  // Negative/red target lowered 3.2 -> 2.6 ("little bit more reddish for
  // -ve numbers not too much" -- 2026-09-05): legibleTint needs LESS ink
  // blended in to clear a lower target, so the result sits closer to the
  // real #dc2626 red instead of the paler tint 3.2 required -- e.g. on
  // --cat1 blue, #f0a0a0 (3.2) -> #eb8585 (2.6). Positive/green kept at
  // 3.2 -- only "-ve numbers" were asked for.
  const PNL_RED = '#dc2626', PNL_GREEN = '#16a34a';
  const PNL_CONTRAST_TARGET = 3.2, PNL_NEG_CONTRAST_TARGET = 2.6;
  const PNL_START_Y = 44, PNL_LINE_H = 12;
  // Same width floor the Asset Class legend's own label+%-gain row already
  // uses (GAINLOSS_MIN_W below) -- one consistent "wide enough for a
  // label + right-aligned value" threshold across the tile instead of a
  // second, differently-tuned number.
  const PNL_ALIGNED_MIN_W = 130;
  // Value column sits at most this far from the left edge -- NOT the
  // tile's own right edge. Anchoring the value to the full tile width
  // read fine on a narrow tile but stretched label and value apart with a
  // large empty gap on a wide one (e.g. IRA at 719px: "Cash" at x=7,
  // value all the way out at x=712). 180 comfortably fits the longest
  // label ("Realized YTD") beside the longest value ("11 BUY · 12 SELL")
  // without the two colliding, while keeping the whole label/value pair
  // visually grouped near the left regardless of how wide the tile is.
  // User: "Too far from header labels. need values to be close to label
  // headers" -- 2026-09-05.
  const PNL_VALUE_COL_W = 180;
  // Legend rows (Asset Class + Equities-by-Sector) below the P&L block get
  // a 5-column layout once there's room, left to right -- name (truncated,
  // fit-to-content width) | alloc-% (own right-aligned column) | $K (own
  // right-aligned column) | caret (own right-aligned column) | gain/loss %
  // (own right-aligned column, the RIGHTMOST -- reads as the row's
  // headline direction indicator). Both legends now show gain/loss the
  // same way, so "up/down" isn't present in one and silently missing from
  // the other. Below LEGEND_ALIGNED_MIN_W there's no room for this without
  // squeezing the name to nothing, so both legends fall back to the
  // original inline "label %" with no value shown at all.
  // LEGEND_PCT_COL_W fits up to "100%". History: "align % also" (name
  // truncation accepted over dropping gain/loss) -- 2026-09-06; "align %
  // Ks carets and up/down in the tile everywhere" (extended gain/loss +
  // caret to the Sector legend) -- 2026-09-06; "carets below the bar are
  // not aligned" (caret needed its own fixed column, not embedded in a
  // shared right-anchored run) -- 2026-09-06; "%s right justified please"
  // (caret and % split into two separate right-anchored columns so both
  // align, not just the run's own end) -- 2026-09-06; "have more space...
  // display 'equities' in full" ($K's column decoupled from
  // PNL_VALUE_COL_W and made fit-to-content instead, so it no longer
  // necessarily shares an x with the P&L block above it) -- 2026-09-06;
  // "carets %up or down should be the right most column" (reordered so
  // caret+gain-% sits after $K, not before it) -- 2026-09-06.
  const LEGEND_ALIGNED_MIN_W = 175;
  const LEGEND_PCT_COL_W = 28;
  // Count column (number of stock positions behind that row) sits right
  // after the name, before alloc-%, e.g. "Financials 10 27%" -- own fixed
  // right-anchored column, same technique as everything else here. Only
  // on the Asset Class / Sector legends (each row there IS a group of
  // stocks); the Stocks legend's own rows are already individual stocks,
  // so a "how many stocks" column wouldn't mean anything there. User:
  // "Tiles -> grids -> add number of stocks as a column after desc (for
  // example: Financials 10 27% etc)" -- 2026-09-06.
  const LEGEND_COUNT_GAP = 4;
  const LEGEND_COUNT_COL_W = 20; // up to 3-digit counts
  // Caret and gain/loss-% are TWO separate right-anchored columns (not one
  // combined run, and not the left-anchored caret+% blob from the previous
  // pass) -- a shared run right-anchored as a whole put the caret (its
  // leading character) at a position that drifted with the %'s own width;
  // making the caret+% pair left-anchored instead fixed the caret but left
  // the % itself NOT right-justified (its trailing digits landed wherever
  // that row's own text happened to end). Two independent right-anchored
  // elements gets both: the caret (one glyph, so anchor style barely
  // matters) sits at a fixed x, and the % lands flush-right at its own
  // fixed x regardless of how many digits it has. User: "carets below the
  // bar are not aligned" -- 2026-09-06, then "%s right justified please" --
  // 2026-09-06.
  const LEGEND_PCT_GAP = 4;           // gap between the alloc-% column and the caret column
  const LEGEND_CARET_RESERVE = 12;    // "▲"/"▼" alone
  const LEGEND_CARET_GAP = 2;         // gap between the caret column and the gain-% column
  const LEGEND_GAINPCT_RESERVE = 42;  // "+999.9%"
  const LEGEND_K_GAP = 5;             // gap between the gain-% column and $K
  const LEGEND_K_RESERVE = 45;        // "$999.9K" alone
  const LEGEND_VALUE_RESERVE = LEGEND_PCT_GAP + LEGEND_CARET_RESERVE + LEGEND_CARET_GAP + LEGEND_GAINPCT_RESERVE + LEGEND_K_GAP + LEGEND_K_RESERVE;
  // Upper bound on the name column's width -- enough for the longest real
  // name in this data ("Communication Services"/"Information Technology"/
  // "Consumer Discretionary", 23 chars) so a genuinely long name still
  // gets SOME cap rather than pushing every numeric column arbitrarily far
  // right on an unusually wide tile.
  const LEGEND_NAME_MAX_W = 150;
  // Caret gets its own fixed column only once the tile is wide enough that
  // the longest label ("Realized YTD", ~67px at this block's 9px font)
  // can't possibly collide with it -- CARET_RESERVE is the worst-realistic
  // width of the amount (+ optional %) that follows the caret at the
  // Unrealized row's own compact-K format, e.g. "+$99.9K (+99.9%)". Below
  // PNL_CARET_MIN_W the caret stays embedded in the value string like
  // before (still right-anchored as one block, just not its own column) --
  // there simply isn't room for a 3rd column at that width. User: "all in
  // Ks and align carets and Ks" -- 2026-09-06 (Ks: "along with % i need
  // the numbers in 1000s -> Ks" was legend-only until now).
  const PNL_CARET_MIN_W = 200;
  const CARET_RESERVE = 90;
  function appendAccountPnlAndSignals(g, w, h, bg, ink, gain, counts, cashVal, securitiesVal, realized, dividends) {
    if (w <= 34) return PNL_START_Y; // truly too narrow for even a wrapped word or two
    const posColor = legibleTint(bg, PNL_GREEN, ink, PNL_CONTRAST_TARGET);
    const negColor = legibleTint(bg, PNL_RED, ink, PNL_NEG_CONTRAST_TARGET);
    const wide = w > PNL_ALIGNED_MIN_W;
    const valueX = Math.min(w - 7, PNL_VALUE_COL_W);
    const showCaretCol = w >= PNL_CARET_MIN_W;
    const caretX = valueX - CARET_RESERVE;
    let y = PNL_START_Y;

    // Wide layout: a short label left, the caret (own fixed column, wide
    // tiles only) and the $ amount right-aligned within a compact fixed
    // column close to the label -- same label/value row shape the tile's
    // hover tooltip already uses, so every line's $ amount lands in one
    // consistent column regardless of label length, and every caret sits
    // in the same column instead of drifting with the amount's own width.
    // User: "Format it properly. its hard to read. align the numbers.
    // align the carets etc" -- 2026-09-05, after "The tooltip information,
    // can that also be displayed in the tile" added several more
    // differently-shaped lines that made the misalignment worse; carets
    // weren't actually in their own column until "align carets and Ks" --
    // 2026-09-06.
    const drawRow = (label, valueText, color, weight, opacity, caret) => {
      if (h <= y + PNL_LINE_H - 5) return;
      g.append('text').attr('x', 7).attr('y', y).attr('font-size', 9)
        .attr('fill', ink).attr('opacity', 0.7).text(label);
      if (caret) {
        g.append('text').attr('x', caretX).attr('y', y).attr('text-anchor', 'end')
          .attr('font-size', 9).attr('font-weight', 700).attr('fill', color)
          .text(caret);
      }
      g.append('text').attr('x', valueX).attr('y', y).attr('text-anchor', 'end')
        .attr('font-size', 9).attr('font-weight', weight).attr('opacity', opacity).attr('fill', color)
        .text(valueText);
      y += PNL_LINE_H;
    };
    // Narrow fallback: the original wrapped single-string format (caret
    // baked into the text, left-aligned, wraps onto up to 2 lines) --
    // still the only way to fit anything at all on the narrowest real
    // tiles (an all-cash account's tile can be under 110px wide).
    const maxChars = Math.max(3, Math.floor((w - 12) / (9 * 0.62)));
    const drawWrapped = (text, color, opacity, weight) => {
      for (const line of wrapTokens(text.split(' '), maxChars, 2)) {
        if (h <= y + PNL_LINE_H - 5) return;
        g.append('text').attr('x', 7).attr('y', y).attr('font-size', 9)
          .attr('font-weight', weight).attr('opacity', opacity).attr('fill', color).text(line);
        y += PNL_LINE_H;
      }
    };
    // `caret` is the bare glyph or null/undefined (no direction, e.g.
    // Securities/Cash/Signals). `amt` never includes it -- drawRow decides
    // whether the caret gets its own column (wide tiles) based on
    // showCaretCol; the wrapped narrow fallback always keeps it embedded
    // in `wrappedText`, which the caller builds with the caret already
    // prefixed since there's no column concept at that width.
    const drawLine = (label, wrappedText, caret, amt, color, weight, opacity) => {
      if (wide) drawRow(label, showCaretCol ? amt : (caret ? `${caret} ${amt}` : amt), color, weight, opacity, showCaretCol ? caret : null);
      else drawWrapped(wrappedText, color, opacity, weight);
    };

    if (gain && gain.costBasis) {
      const pct = gain.totalGainDollar / gain.costBasis * 100;
      const up = gain.totalGainDollar >= 0;
      const caret = up ? '▲' : '▼';
      const amt = `${fmtSignedK(gain.totalGainDollar)} (${fmtSignedPct1(pct)})`;
      drawLine('Unrealized', `${caret} ${amt}`, caret, amt, up ? posColor : negColor, 700, 1);
    }
    if (gain && gain.todayGainDollar != null) {
      const up = gain.todayGainDollar >= 0;
      const caret = up ? '▲' : '▼';
      const amt = fmtSignedK(gain.todayGainDollar);
      drawLine('Today', `${caret} ${amt} today`, caret, amt, up ? posColor : negColor, 700, 0.9);
    }
    // Everything below this point duplicates a row the tile's own hover
    // tooltip already shows (Securities/Cash/Realized YTD/Dividends YTD) --
    // same "more room -> more detail" progressive reveal as the lines
    // above, just further down the priority order since those tooltip
    // facts are less time-sensitive than P&L/today. User: "The tooltip
    // information, can that also be displayed in the tile (if we have
    // space, if not only show it in the tooltip)?" -- 2026-09-05.
    if (securitiesVal != null) {
      const amt = fmtK(securitiesVal);
      drawLine('Securities', `${amt} securities`, null, amt, ink, 400, 0.85);
    }
    if (cashVal != null) {
      const amt = fmtK(cashVal);
      drawLine('Cash', `${amt} cash`, null, amt, ink, 400, 0.85);
    }
    if (realized && realized.ytd_realized) {
      const up = realized.ytd_realized >= 0;
      const caret = up ? '▲' : '▼';
      const amt = fmtSignedK(realized.ytd_realized);
      drawLine('Realized YTD', `${caret} ${amt} realized YTD`, caret, amt, up ? posColor : negColor, 700, 0.9);
    }
    if (dividends && dividends.ytd_dividends) {
      const caret = '▲';
      const amt = fmtSignedK(dividends.ytd_dividends);
      drawLine('Div YTD', `${caret} ${amt} div YTD`, caret, amt, posColor, 700, 0.9);
    }
    if (counts && (counts.buy || counts.sell)) {
      const val = `${counts.buy} BUY · ${counts.sell} SELL`;
      drawLine('Signals', val, null, val, ink, 400, 0.85);
    }
    return y;
  }

  // Buy/Sell symbol list -- the actual tickers behind a tile's "N BUY ·
  // N SELL" Signals line, appended at the very END of a tile's content
  // (after the P&L block AND the Asset Class / Sector breakdowns below
  // it), not right under Signals itself -- a long list there would eat
  // into the room the breakdown bars need, and the breakdown is the more
  // important content to protect. Same progressive height-reveal every
  // other block in this file uses; trimmed to a "+N more" suffix rather
  // than relying on wrapTokens' own silent line-cap (which would cut the
  // tail off mid-list with no indication more symbols exist). Colored by
  // the tile's own posColor/negColor (not the full 6-tier action palette)
  // -- this is a compact "what's flagged" list, not the Actionable grid.
  // User: "Display Buy and Sell stocks list since we have space in that
  // tile" -- 2026-09-06, then "display Buy and Sell at the end" --
  // 2026-09-06.
  function appendBuySellList(g, w, h, bg, ink, startY, counts) {
    if (!counts || (!counts.buy && !counts.sell)) return startY;
    const posColor = legibleTint(bg, PNL_GREEN, ink, PNL_CONTRAST_TARGET);
    const negColor = legibleTint(bg, PNL_RED, ink, PNL_NEG_CONTRAST_TARGET);
    const listCharsPerLine = Math.max(10, Math.floor((w - 12) / (8.5 * 0.62)));
    const listMaxLines = 2;
    let y = startY;
    const drawSymbolList = (label, symbols, color) => {
      if (!symbols || !symbols.length) return;
      let shown = symbols, extra = 0;
      while (shown.length > 1 && `${label}: ${shown.join(', ')}${extra ? ` +${extra} more` : ''}`.length > listCharsPerLine * listMaxLines) {
        extra++;
        shown = shown.slice(0, -1);
      }
      const text = `${label}: ${shown.join(', ')}${extra ? ` +${extra} more` : ''}`;
      for (const line of wrapTokens(text.split(' '), listCharsPerLine, listMaxLines)) {
        if (h <= y + PNL_LINE_H - 5) return;
        g.append('text').attr('x', 7).attr('y', y).attr('font-size', 8.5)
          .attr('fill', color).attr('opacity', 0.9).text(line);
        y += PNL_LINE_H;
      }
    };
    drawSymbolList('Buy', counts.buySymbols, posColor);
    drawSymbolList('Sell', counts.sellSymbols, negColor);
    return y;
  }

  // Account tile Asset Class breakdown -- a thin stacked composition bar +
  // a companion legend (dot + name + %), segments/rows proportional to
  // whichever basis (value $ / count) the current Size toggle uses
  // elsewhere on this screen. Segment/dot color is assetColorAssign -- the
  // SAME palette the Asset Class root tiles use, so "Equities" reads as
  // the same color here as anywhere else it appears.
  //
  // Surface ring + gaps (dataviz skill's own fix for "a mark overlapping a
  // colored surface"): acctColor and assetColorAssign are BOTH ranked
  // "biggest gets slot 1" over their own populations, so the #1 account by
  // $ and the #1 asset class by count (almost always Equities) collide on
  // --cat1 more often than not -- confirmed live: F-M's tile fill and its
  // own dominant Equities segment were BOTH #1d4ed8, the segment
  // invisible against its own tile. A track drawn behind the segments
  // (showing through as ~1.5px gaps between them) plus a ring around the
  // whole bar keeps every segment demarcated regardless of which account/
  // asset-class colors happen to coincide, without touching the shared
  // color-ranking scheme those two legends still rely on elsewhere in the
  // app.
  //
  // Track/ring/dot-outline colors are COMPUTED (legibleTint, the same
  // blend-until-contrast-clears helper the P&L red/green already uses),
  // not a guessed opacity -- an alpha-blended `ink` at a picked-by-eye
  // opacity is itself just another unverified color, the exact thing this
  // whole feature's color pass has been fixing. Track targets a mild 1.6
  // contrast (just enough to read as "a different surface," not a bold
  // stripe); ring/dot-outline target 2.4 (assertively visible, since their
  // whole job is demarcation). User: "Try to use proper contrast colors
  // and add some space between legend and bar" -- 2026-09-05, after "bar
  // chart need proper colors with % names in it and a legend".
  const ASSETBAR_TRACK_TARGET = 1.6, ASSETBAR_RING_TARGET = 2.4;
  // Neutral gray anchor for the track/ring blend (legibleTint's `base`) --
  // NOT the tile's own bg. Blending from the tile's own color (as this
  // first did) still comes out visibly tinted with that color once mixed
  // toward `ink` -- e.g. on a blue (--cat1) tile the "neutral" track/ring
  // computed out to #567ae2/#839eea, still plainly blue. Zero-saturation
  // gray as the start point keeps the result a genuine neutral (light or
  // dark gray) on every tile color instead of just a paler shade of
  // whatever hue the tile already is. User: "you are using blue for the
  // bar. change that to something else" -- 2026-09-05.
  const ASSETBAR_NEUTRAL = '#808080';
  // Segment/dot color override for the bar ONLY -- assetColorAssign still
  // ranks asset classes into the shared --cat1..5 slots exactly as it
  // always has (Asset Class root tiles, Sector tiles, and Account tile
  // backgrounds via acctColor all keep reading those slots' real CSS
  // values unaffected), this just substitutes a different rendered hex
  // for --cat1 specifically WITHIN this bar's own segments/dots. First
  // tried changing --cat1 itself in styles.css, but that's shared with
  // Account tile backgrounds too -- reverted per "Change the color only
  // in the bar not tile. Bar is good now." -- 2026-09-05. Amber (#c8800d)
  // clears the blue-vs-cat4-purple normal-vision-floor failure (ΔE 13.0)
  // the validator's --pairs all check found; see styles.css's own comment
  // on --cat1 for the full history.
  const ASSETBAR_SLOT_OVERRIDE = { '--cat1': '#c8800d' };
  function assetBarColor(assetClass) {
    const slot = assetColorAssign.get(assetClass) || '--cat-unmapped';
    return ASSETBAR_SLOT_OVERRIDE[slot] || cssVar(slot);
  }
  // Pairs in the app's own --cat1..5 categorical palette (shared with
  // Account/Sector/Source tiles elsewhere -- NOT something to silently
  // recolor here beyond the one swap made in styles.css, see its own
  // comment) that fail the dataviz skill's own checks when placed
  // directly adjacent, found via the full --pairs all sweep (the default
  // adjacent-only check misses these): --cat2<->--cat5 (teal/pink) fails
  // the deuteranopia CVD floor (ΔE 3.8, below 6) -- pre-existing.
  // --cat1<->--cat3 (amber/brown, since 2026-09-05's blue->amber swap)
  // sits at ΔE 11.6, below the 15 normal-vision floor -- amber was picked
  // specifically to clear the WORSE pair blue used to fail (blue<->purple
  // was 13.0; amber<->purple is 35), at the cost of this milder one with
  // brown, its nearest neighbor on the hue wheel. Since the palette itself
  // is out of scope to change further here, this bar instead never PLACES
  // either pair adjacent -- reorderAvoidingUnsafeAdjacency swaps a
  // colliding neighbor forward when a safe one is available, a bounded,
  // local mitigation matching the skill's own prescribed fix ("re-step it
  // on the adjacent pair list"). User: "Color contrast please..." then
  // "you are using blue for the bar. change that to something else" --
  // 2026-09-05.
  const UNSAFE_ADJACENT_SLOTS = new Set(['--cat1|--cat3', '--cat3|--cat1', '--cat2|--cat5', '--cat5|--cat2']);
  // `slotOf` defaults to the asset-class lookup (this function's original
  // caller); the Equities sector legend passes a sector-keyed one instead
  // (catAssign) so the same mitigation applies to whichever categorical
  // slot assignment the caller's rows are colored by -- the unsafe PAIRS
  // are a property of the shared --cat1..5 palette itself, not of asset
  // classes specifically.
  function reorderAvoidingUnsafeAdjacency(rows, slotOf = r => assetColorAssign.get(r.asset_class) || '--cat-unmapped') {
    const arr = rows.slice();
    for (let i = 0; i < arr.length - 1; i++) {
      if (!UNSAFE_ADJACENT_SLOTS.has(`${slotOf(arr[i])}|${slotOf(arr[i + 1])}`)) continue;
      // Look ahead for a later row that's safe on both sides of the swap
      // (won't re-create the same collision at i, won't create a new one
      // where it lands) and bring it forward one slot.
      for (let j = i + 2; j < arr.length; j++) {
        const safeAtI = !UNSAFE_ADJACENT_SLOTS.has(`${slotOf(arr[i])}|${slotOf(arr[j])}`);
        const safeAfter = !UNSAFE_ADJACENT_SLOTS.has(`${slotOf(arr[j])}|${slotOf(arr[i + 1])}`);
        if (safeAtI && safeAfter) {
          const [moved] = arr.splice(j, 1);
          arr.splice(i + 1, 0, moved);
          break;
        }
      }
    }
    return arr;
  }
  let _assetBarClipSeq = 0;
  // Stacked composition bar (track + colored segments, each with a direct
  // %-label when there's room, + a crisp ring on top) -- shared by the
  // Asset Class bar (original) and the Equities-by-Sector bar (added per
  // "neee a bar for equities also like other bar" -- 2026-09-06). `rows`
  // should already be in whatever left-to-right order the caller wants
  // drawn (color-safe reordered -- NOT necessarily the legend's own sort
  // order below it, see the split explained where this is called).
  // `colorFn(row)` returns that row's segment fill. `rightX` is where the
  // bar's own right edge lands -- matched to the legend grid's own
  // rightmost column below it (not the tile's right edge), so the bar's
  // width tracks whatever the legend actually uses rather than always
  // spanning the full tile. User: "just make bar's width as same as grid
  // (data below)" -- 2026-09-06. Returns the bar's bottom y, or null if
  // there was no room to draw anything at all.
  function appendCompositionBar(g, w, h, bg, ink, startY, rows, basis, total, colorFn, rightX) {
    // barH raised 9 -> 14 to fit a direct %-label on each wide-enough
    // segment (font-size 8, vertically centered) -- user: "put the % in
    // the bar" -- 2026-09-05.
    const barH = 14, gapAbove = 8, segGap = rows.length > 1 ? 1.5 : 0;
    const y = startY + gapAbove;
    if (h <= y + barH - 4) return null; // no room -- don't spend the gap either
    const barX = 7, barW = Math.max(0, rightX - barX);
    const drawableW = Math.max(0, barW - segGap * (rows.length - 1));
    const trackColor = legibleTint(bg, ASSETBAR_NEUTRAL, ink, ASSETBAR_TRACK_TARGET);
    const ringColor = legibleTint(bg, ASSETBAR_NEUTRAL, ink, ASSETBAR_RING_TARGET);

    // Track: the pill shape itself -- what shows through as the gap
    // between segments, and what frames a segment whose fill happens to
    // match the tile's own bg.
    g.append('rect').attr('x', barX).attr('y', y).attr('width', barW).attr('height', barH)
      .attr('rx', barH / 2).attr('fill', trackColor);

    const clipId = `uv-assetbar-clip-${_assetBarClipSeq++}`;
    g.append('clipPath').attr('id', clipId).append('rect')
      .attr('x', barX).attr('y', y).attr('width', barW).attr('height', barH).attr('rx', barH / 2);
    const segG = g.append('g').attr('clip-path', `url(#${clipId})`);
    const pctFontSize = 8;
    let x = barX;
    for (const row of rows) {
      const segW = row[basis] / total * drawableW;
      const fill = colorFn(row);
      segG.append('rect').attr('x', x).attr('y', y).attr('width', segW).attr('height', barH).attr('fill', fill);
      // Direct %-label ON the segment, only when it's wide enough to hold
      // its own text without spilling into a neighbor -- selective direct
      // labeling (never crammed onto every sliver), same principle as
      // drawGroupTileLabel's own "too small -> skip" cutoffs elsewhere in
      // this file. Color is computed against THIS segment's own fill
      // (labelColorFor), not the tile's `ink` -- ink is only guaranteed
      // legible against the tile's background, not against an arbitrary
      // asset-class color sitting on top of it.
      const pct = Math.round(row[basis] / total * 100);
      const pctStr = `${pct}%`;
      const pctW = pctStr.length * pctFontSize * 0.62;
      if (segW >= pctW + 6) {
        segG.append('text').attr('x', x + segW / 2).attr('y', y + barH / 2 + pctFontSize * 0.35)
          .attr('text-anchor', 'middle').attr('font-size', pctFontSize).attr('font-weight', 700)
          .attr('fill', labelColorFor(fill)).text(pctStr);
      }
      x += segW + segGap;
    }
    // Ring: crisp outline on top of the segments so the bar's own boundary
    // against the tile is always visible, independent of any segment/tile
    // color coincidence.
    g.append('rect').attr('x', barX).attr('y', y).attr('width', barW).attr('height', barH)
      .attr('rx', barH / 2).attr('fill', 'none').attr('stroke', ringColor).attr('stroke-width', 1);

    return y + barH;
  }

  // Bullish/Bearish direction from a raw rr_outlook string ('Bullish',
  // 'Mild Bullish', 'Light Bullish', 'Mild Bearish', 'Bearish',
  // 'NEUTRAL', etc, any case -- the data mixes both) -- 'up'/'down'/null
  // (Neutral, or no reading at all). `.includes`, not `.startsWith` --
  // "Mild Bullish"/"Light Bullish" don't START with "BULL" (they start
  // with "MILD"/"LIGHT"), so a prefix match (the drv_dash_summary SQL
  // convention this was first copied from, `LIKE 'BULL%'`) silently
  // read them as neither bullish nor bearish. Any bullish- or bearish-
  // leaning tier now counts as a direction; only a literal "Neutral" (or
  // no data) stays flat. Shared by the tally fallback in
  // computeScopedBreakdown and the sector/asset-class ETF lookups below.
  // User: "Yes, broaden it to include Mild/Light tiers" -- 2026-09-06.
  function _outlookDir(text) {
    const ol = (text || '').toUpperCase();
    if (ol.includes('BULL')) return 'up';
    if (ol.includes('BEAR')) return 'down';
    return null;
  }

  // One small caret glyph, replacing the legend row's old flat category-
  // color dot. `dir` is precomputed by the caller ('up'/'down'/null) --
  // for the Sector legend that's the row's SPDR sector ETF's own
  // rr_outlook (see SECTOR_ETF), for the Asset Class legend it's still a
  // Bullish-vs-Bearish majority tally across the row's symbols
  // (`rrBullish`/`rrBearish`, computeScopedBreakdown). A tie (or no
  // reading at all) draws a flat muted dash instead of guessing a
  // direction, same "don't fabricate a signal" rule the rest of this file
  // follows. User: first proposed a two-caret current+macro design, then
  // "Don't worry about the current. Just display one, rr outlook" / "One
  // indicator not two" -- then, checking XLY (Consumer Discretionary)
  // specifically: its own rr_outlook read Neutral but the old vote-
  // across-134-symbols tally read Bullish -- "should have been neutral...
  // i see up green arrow" -> confirmed they wanted XLY's own individual
  // outlook, not the crowd's -- 2026-09-06.
  function appendOutlookCaret(g, x, y, dir, ink, posColor, negColor) {
    g.append('text').attr('x', x).attr('y', y).attr('text-anchor', 'middle')
      .attr('font-size', 8).attr('font-weight', 700)
      .attr('fill', dir === 'up' ? posColor : dir === 'down' ? negColor : ink)
      .attr('opacity', dir ? 1 : 0.35)
      .text(dir === 'up' ? '▲' : dir === 'down' ? '▼' : '–');
  }

  function appendAccountAssetBreakdown(g, w, h, bg, ink, startY, rowsIn) {
    if (!rowsIn || !rowsIn.length || w <= 30) return startY;
    // `rows` (color-safe reordered) drives the BAR segments only -- their
    // left-to-right order is what an adjacent-color collision actually
    // depends on. The legend below is a separate, independently-sorted
    // list (`legendRows`, strict desc by whichever basis $/count is
    // active) so its rows read top-to-bottom by size regardless of
    // whatever swap the color-safety pass made to the bar's own order.
    // These used to share one array (deliberately, so the two visually
    // matched) -- User: "Sort them by % desc order" -- 2026-09-06, ended
    // that: the color-safety swap could put a smaller % above a larger
    // one in the legend (e.g. bar order also reordered "Fixed Income 7%"
    // ahead of "Commodities 7%" and behind "FX / Currency 4%" -- not a
    // desc sort by design, since reorderAvoidingUnsafeAdjacency's whole
    // job is trading sort order for color safety).
    const rows = reorderAvoidingUnsafeAdjacency(rowsIn);
    // Always dollar-value, NOT sizeMode's Count/Capital toggle -- this
    // legend now shows an actual $K figure beside the %, and the two need
    // to agree. Before $K existed, tying the bar's own % to whichever
    // basis the outer Size toggle used was harmless (nothing else on the
    // row to compare it against); once $K sat right next to it, a %
    // computed from POSITION COUNT (Count mode, the default) routinely
    // disagreed with the dollar figure beside it -- e.g. a sector holding
    // few, large positions showed a small % next to a large $K, or the
    // reverse for many tiny ones. User: "Why the % and Ks don't match?" --
    // 2026-09-06.
    const basis = 'value';
    const legendRows = [...rowsIn].sort((a, b) => b[basis] - a[basis]);
    const total = rows.reduce((s, r) => s + r[basis], 0) || 1;

    // Legend: outlook caret (see appendOutlookCaret) +
    // name + allocation % + (if room) a right-aligned gain/loss indicator
    // per asset class -- still
    // shown even though wide segments now carry their own %-label too,
    // since narrow segments (and their names) only ever appear here.
    // Largest share first, only as many rows as actually fit. legendGap
    // widened to 12 (was 5) so the legend clearly reads as its own section
    // below the bar, not a cramped continuation of it.
    //
    // Gain/loss color reuses the same legibleTint-computed green/red the
    // P&L block uses (not a fixed hex -- same reasoning: a flat green/red
    // can fail contrast on some account colors). GAINLOSS_MIN_W gates the
    // whole indicator off on tiles too narrow to fit "name + alloc% +
    // ▼-99.9%" without the name getting squeezed to nothing. User: "is it
    // possible to display loss/gain by asset class as separate bar in the
    // tile" -- chose "inline with legend rows" -- 2026-09-05.
    //
    // Value column sized to fit the LONGEST name actually in this row
    // list (capped at LEGEND_NAME_MAX_W), not blindly pinned at
    // PNL_VALUE_COL_W -- pinning it there squeezed every name down to ~2-3
    // characters ("Equities" -> "Eq…") even on a 700px-wide tile with
    // plenty of room to spare, since the numeric columns' own reserved
    // widths ate almost everything between the label and x=180. User:
    // "have more space. you can use it to display 'equities' in full for
    // example" -- 2026-09-06. This does mean the $ column here can land at
    // a different x than the P&L block's own (fixed, short-label-sized)
    // value column above it -- that tension is inherent: P&L's labels are
    // fixed and short so its column stays tight; this legend's names are
    // long and variable so its column has to flex with them.
    const legendFontSize = 9.5, legendRowH = 13, legendGap = 12;
    const showAligned = w >= LEGEND_ALIGNED_MIN_W;
    const showGainLoss = showAligned; // gain/loss only ever shows alongside the aligned 3-column layout
    const posColor = legibleTint(bg, PNL_GREEN, ink, PNL_CONTRAST_TARGET);
    const negColor = legibleTint(bg, PNL_RED, ink, PNL_NEG_CONTRAST_TARGET);
    // nameAreaW is the SMALLER of (a) what the longest name in this list
    // actually needs, capped at LEGEND_NAME_MAX_W, and (b) what the tile's
    // own width can supply once every numeric column's reserve is
    // subtracted -- (b) alone is what an unusually long name at a
    // width just above LEGEND_ALIGNED_MIN_W would need capped to,
    // otherwise the numeric columns computed FROM an oversized name width
    // would land past the tile's own right edge.
    const availableForName = (w - 7) - LEGEND_VALUE_RESERVE - LEGEND_COUNT_GAP - LEGEND_COUNT_COL_W - LEGEND_PCT_COL_W - 4 - 19;
    const longestName = legendRows.reduce((m, r) => Math.max(m, r.asset_class.length), 0);
    const nameAreaW = showAligned
      ? Math.max(0, Math.min(LEGEND_NAME_MAX_W, longestName * legendFontSize * 0.62, availableForName))
      : (w - 24);
    // Order left to right: name | count | alloc-% | $K | caret | gain/
    // loss-% (rightmost) -- caret+gain/loss pushed to the far right so it
    // reads as the tile's own "headline" direction indicator, same visual
    // priority the P&L block's caret column already gets by sitting right
    // before ITS rightmost (value) column. User: "carets %up or down
    // should be the right most column" -- 2026-09-06, then "add number of
    // stocks as a column after desc" -- 2026-09-06.
    const countColX = 19 + nameAreaW + LEGEND_COUNT_COL_W;
    const pctColX = countColX + LEGEND_COUNT_GAP + LEGEND_PCT_COL_W;
    const kColX = pctColX + LEGEND_PCT_GAP + LEGEND_K_RESERVE;
    const caretColX = kColX + LEGEND_K_GAP + LEGEND_CARET_RESERVE;
    const gainPctColX = caretColX + LEGEND_CARET_GAP + LEGEND_GAINPCT_RESERVE;
    const legendValueX = gainPctColX;
    const maxChars = Math.max(3, Math.floor(nameAreaW / (legendFontSize * 0.62)));
    // Bar's own right edge matched to the legend grid's rightmost column
    // (legendValueX) computed just above, not the tile's right edge --
    // user: "just make bar's width as same as grid (data below)" --
    // 2026-09-06. Falls back to the tile's own edge when the legend isn't
    // in aligned/columned mode at all (narrow tiles -- no "grid" to match).
    const barBottom = appendCompositionBar(g, w, h, bg, ink, startY, rows, basis, total,
      r => assetBarColor(r.asset_class), showAligned ? legendValueX : (w - 7));
    if (barBottom == null) return startY;
    let ly = barBottom + legendGap;
    for (const row of legendRows) {
      if (h <= ly + legendRowH - 4) break;
      const pct = Math.round(row[basis] / total * 100);
      const label = row.asset_class.length > maxChars ? row.asset_class.slice(0, Math.max(1, maxChars - 1)) + '…' : row.asset_class;
      // FX/Currency (UUP) and Crypto (BTC) get the same representative-
      // ticker treatment as the Sector legend's SECTOR_ETF -- see
      // ASSET_ETF's own comment for why Equities/Fixed Income/Commodities
      // don't. Falls back to the crowd tally if that ticker isn't in the
      // loaded universe/has no outlook.
      const acEtfDet = symbolDetail.get(ASSET_ETF[row.asset_class]);
      const acEtfDir = acEtfDet ? _outlookDir(acEtfDet.rr_outlook) : null;
      const acDir = acEtfDet ? acEtfDir : (row.rrBullish > row.rrBearish ? 'up' : row.rrBearish > row.rrBullish ? 'down' : null);
      appendOutlookCaret(g, 11, ly, acDir, ink, posColor, negColor);
      g.append('text').attr('x', 19).attr('y', ly).attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.9)
        .text(showAligned ? label : `${label} ${row.count} ${pct}%`);
      if (showAligned) {
        g.append('text').attr('x', countColX).attr('y', ly).attr('text-anchor', 'end')
          .attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.75)
          .text(String(row.count));
        g.append('text').attr('x', pctColX).attr('y', ly).attr('text-anchor', 'end')
          .attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.9)
          .text(`${pct}%`);
        g.append('text').attr('x', kColX).attr('y', ly).attr('text-anchor', 'end')
          .attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.85)
          .text(fmtK(row.value));
        // Caret and gain-% are TWO separate right-anchored columns, pushed
        // out to the far right (past $K) -- the caret (one glyph) at
        // caretColX, the % (right-justified, flush at its own fixed x
        // regardless of digit count) at gainPctColX/legendValueX.
        if (showGainLoss && row.costBasis) {
          const glPct = row.gainDollar / row.costBasis * 100;
          const up = glPct >= 0;
          const color = up ? posColor : negColor;
          g.append('text').attr('x', caretColX).attr('y', ly).attr('text-anchor', 'end')
            .attr('font-size', legendFontSize).attr('font-weight', 700).attr('fill', color)
            .text(up ? '▲' : '▼');
          g.append('text').attr('x', gainPctColX).attr('y', ly).attr('text-anchor', 'end')
            .attr('font-size', legendFontSize).attr('font-weight', 700).attr('fill', color)
            .text(fmtSignedPct1(glPct));
        }
      }
      ly += legendRowH;
    }
    return ly > barBottom + legendGap ? ly : barBottom;
  }

  // Equities -> Sector mini-legend + its own composition bar, appended
  // below the Asset Class bar+legend on tiles with enough remaining room.
  // Reuses the same sector color slots (catAssign, ranked once on the
  // whole universe in build()) every other sector surface in this file
  // already uses, so a sector's color here matches its own Sector-
  // drilldown tile. Originally legend-only (no bar, to save space) --
  // "neee a bar for equities also like other bar" added one. Gated off
  // entirely for accounts with no Equities exposure (rowsIn empty -- e.g.
  // an all-cash or all-fixed-income account) and for tiles too narrow to
  // hold even a short sector name. User: "all the tile that have enough
  // space do the details about equities (next level grouping like
  // sectors) below the asset style legend" -- 2026-09-05.
  const SECTOR_LEGEND_MIN_W = 110;
  function appendAccountSectorBreakdown(g, w, h, bg, ink, startY, rowsIn) {
    if (!rowsIn || !rowsIn.length || w < SECTOR_LEGEND_MIN_W) return startY;
    // Always dollar-value, not sizeMode's Count/Capital toggle -- same fix
    // as the Asset Class legend above, same reason (a % from a different
    // basis than the $K beside it looked wrong). User: "Why the % and Ks
    // don't match?" -- 2026-09-06.
    const basis = 'value';
    const total = rowsIn.reduce((s, r) => s + r[basis], 0) || 1;
    // `barRows` (color-safe reordered, same adjacent-pair mitigation the
    // Asset Class bar uses -- catAssign's slots carry the same unsafe
    // pairs) drives the BAR segments; `legendRows` is the independently,
    // strictly-sorted list the legend text below actually renders -- same
    // split as the Asset Class legend, same reason (the color-safety swap
    // trades sort order for adjacency safety, which a bar needs but a
    // vertically-stacked list doesn't). User: "neee a bar for equities
    // also like other bar" -- 2026-09-06 (added the bar); "Sort them by %
    // desc order" -- 2026-09-06 (the legend/bar split).
    const barRows = reorderAvoidingUnsafeAdjacency(rowsIn, r => catAssign.get(r.sector) || '--cat-unmapped');
    const legendRows = [...rowsIn].sort((a, b) => b[basis] - a[basis]);
    const headFontSize = 8.5, legendFontSize = 9.5, legendRowH = 13, headGap = 14, barGapAbove = 8, barH = 14, legendGap = 12;
    // Bail before drawing anything (heading, bar, or legend) unless the
    // heading + bar + at least one legend row will ALL actually fit --
    // same all-or-nothing philosophy the Asset Class legend/bar pair uses
    // (never leave a heading or a bar dangling with nothing useful under
    // it).
    const headingY = startY + headGap - 4;
    const barBottomEstimate = headingY + barGapAbove + barH;
    const firstLegendY = barBottomEstimate + legendGap;
    if (h <= firstLegendY + legendRowH - 4) return startY;
    g.append('text').attr('x', 7).attr('y', headingY).attr('font-size', headFontSize)
      .attr('fill', ink).attr('opacity', 0.6).attr('font-weight', 700)
      .text('EQUITIES BY SECTOR');
    const posColor = legibleTint(bg, PNL_GREEN, ink, PNL_CONTRAST_TARGET);
    const negColor = legibleTint(bg, PNL_RED, ink, PNL_NEG_CONTRAST_TARGET);
    // Same layout as the Asset Class legend above -- name | alloc-% | $K |
    // caret | gain/loss-% (rightmost), each its own column -- gain/loss
    // data (acctSectorTmp, aggregated in build()) so a sector's own up/
    // down shows the same way its asset class's does, not silently
    // missing from just this one section. Names get squeezed accordingly,
    // same trade-off the user already accepted for the Asset Class
    // legend. User: "alignment please" / "align % also" -- 2026-09-05/06
    // -- then "align % Ks carets and up/down in the tile everywhere" --
    // 2026-09-06, which is what actually added gain/loss to this legend
    // at all -- then "carets %up or down should be the right most
    // column" -- 2026-09-06.
    const showAligned = w >= LEGEND_ALIGNED_MIN_W;
    const showGainLoss = showAligned;
    // Same fit-to-content name width as the Asset Class legend above --
    // sized to the longest sector name actually in this list (GICS sector
    // names run long, e.g. "Communication Services"), capped by
    // LEGEND_NAME_MAX_W and by what the tile can physically supply. User:
    // "have more space. you can use it to display 'equities' in full for
    // example" -- 2026-09-06.
    const availableForName = (w - 7) - LEGEND_VALUE_RESERVE - LEGEND_COUNT_GAP - LEGEND_COUNT_COL_W - LEGEND_PCT_COL_W - 4 - 19;
    const longestName = legendRows.reduce((m, r) => Math.max(m, r.sector.length), 0);
    const nameAreaW = showAligned
      ? Math.max(0, Math.min(LEGEND_NAME_MAX_W, longestName * legendFontSize * 0.62, availableForName))
      : (w - 24);
    // Order left to right: name | count | alloc-% | $K | caret | gain/
    // loss-% (rightmost) -- same reorder as the Asset Class legend, so a
    // sector's own up/down reads as the rightmost, "headline" figure the
    // same way there too. User: "carets %up or down should be the right
    // most column" -- 2026-09-06, then "add number of stocks as a column
    // after desc" -- 2026-09-06.
    const countColX = 19 + nameAreaW + LEGEND_COUNT_COL_W;
    const pctColX = countColX + LEGEND_COUNT_GAP + LEGEND_PCT_COL_W;
    const sectorKColX = pctColX + LEGEND_PCT_GAP + LEGEND_K_RESERVE;
    const caretColX = sectorKColX + LEGEND_K_GAP + LEGEND_CARET_RESERVE;
    const gainPctColX = caretColX + LEGEND_CARET_GAP + LEGEND_GAINPCT_RESERVE;
    const sectorValueX = gainPctColX;
    const maxChars = Math.max(3, Math.floor(nameAreaW / (legendFontSize * 0.62)));
    // Bar's own right edge matched to the legend grid's rightmost column
    // (sectorValueX) computed just above -- user: "just make bar's width
    // as same as grid (data below)" -- 2026-09-06.
    const barBottom = appendCompositionBar(g, w, h, bg, ink, headingY, barRows, basis, total,
      r => cssVar(catAssign.get(r.sector) || '--cat-unmapped'), showAligned ? sectorValueX : (w - 7));
    let ly = barBottom + legendGap;
    for (const row of legendRows) {
      if (h <= ly + legendRowH - 4) break;
      const pct = Math.round(row[basis] / total * 100);
      const label = row.sector.length > maxChars ? row.sector.slice(0, Math.max(1, maxChars - 1)) + '…' : row.sector;
      // Prefer the sector's own SPDR ETF's rr_outlook (a single, clean
      // read) over the row's crowd tally -- falls back to the tally only
      // if that ETF isn't in the loaded universe/has no outlook. See
      // SECTOR_ETF/appendOutlookCaret's own comment for why.
      const etfDet = symbolDetail.get(SECTOR_ETF[row.sector]);
      const etfDir = etfDet ? _outlookDir(etfDet.rr_outlook) : null;
      const secDir = etfDet ? etfDir : (row.rrBullish > row.rrBearish ? 'up' : row.rrBearish > row.rrBullish ? 'down' : null);
      appendOutlookCaret(g, 11, ly, secDir, ink, posColor, negColor);
      g.append('text').attr('x', 19).attr('y', ly).attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.9)
        .text(showAligned ? label : `${label} ${row.count} ${pct}%`);
      if (showAligned) {
        g.append('text').attr('x', countColX).attr('y', ly).attr('text-anchor', 'end')
          .attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.75)
          .text(String(row.count));
        g.append('text').attr('x', pctColX).attr('y', ly).attr('text-anchor', 'end')
          .attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.9)
          .text(`${pct}%`);
        g.append('text').attr('x', sectorKColX).attr('y', ly).attr('text-anchor', 'end')
          .attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.85)
          .text(fmtK(row.value));
        // Caret and gain-% are TWO separate right-anchored columns, pushed
        // out to the far right (past $K) -- same reasoning as the Asset
        // Class legend above.
        if (showGainLoss && row.costBasis) {
          const glPct = row.gainDollar / row.costBasis * 100;
          const up = glPct >= 0;
          const color = up ? posColor : negColor;
          g.append('text').attr('x', caretColX).attr('y', ly).attr('text-anchor', 'end')
            .attr('font-size', legendFontSize).attr('font-weight', 700).attr('fill', color)
            .text(up ? '▲' : '▼');
          g.append('text').attr('x', gainPctColX).attr('y', ly).attr('text-anchor', 'end')
            .attr('font-size', legendFontSize).attr('font-weight', 700).attr('fill', color)
            .text(fmtSignedPct1(glPct));
        }
      }
      ly += legendRowH;
    }
    return ly;
  }

  // Individual-stock legend -- one level deeper than the Sector
  // breakdown above (that groups by sector; this lists the actual
  // symbols behind ONE sector). Same name|%|$K|caret|gain-% column
  // layout as both breakdowns above, PLUS a rightmost BUY/SELL column --
  // the per-stock trading-signal side, replacing the separate "Buy: ...
  // / Sell: ..." list that used to sit below this legend (redundant once
  // every row already carries its own side). Legend-only, no bar -- a
  // sector can hold many more stocks than there are sectors, and a
  // segment per stock would rarely be legible at that count. Leading dot
  // was originally the symbol's own trading-signal action color
  // (actionColor/final_code) -- replaced with the same single outlook
  // caret (rr_outlook, appendOutlookCaret) the Sector/Asset Class legends
  // use, for consistency across all three levels; the trading-signal side
  // still shows separately via the BUY/SELL column at the far right.
  // User: "Now one level deep, dsiplay stocks, % and amount, caret,% up
  // or down" -- 2026-09-06, then "add Buy or Sell as a last column
  // instead of listing at the bottom for this" -- 2026-09-06, then "What
  // do the dots before stock symbols represent?" -> "do the same for
  // stocks" -- 2026-09-06.
  const SYMBOL_LEGEND_MIN_W = 110;
  const SYMBOL_SIDE_GAP = 6, SYMBOL_SIDE_RESERVE = 30; // "SELL" alone
  function appendSymbolBreakdown(g, w, h, bg, ink, startY, rowsIn) {
    if (!rowsIn || !rowsIn.length || w < SYMBOL_LEGEND_MIN_W) return startY;
    const basis = 'value'; // always dollar -- same "% must match $K" fix as the two breakdowns above
    const legendRows = [...rowsIn].sort((a, b) => b[basis] - a[basis]);
    const total = legendRows.reduce((s, r) => s + r[basis], 0) || 1;
    const headFontSize = 8.5, legendFontSize = 9.5, legendRowH = 13, headGap = 14;
    const firstRowY = startY + headGap + legendRowH - 3;
    // Bail before drawing anything (including the heading) unless at
    // least one stock row will actually fit.
    if (h <= firstRowY + legendRowH - 4) return startY;
    g.append('text').attr('x', 7).attr('y', startY + headGap - 4).attr('font-size', headFontSize)
      .attr('fill', ink).attr('opacity', 0.6).attr('font-weight', 700)
      .text('STOCKS');
    const posColor = legibleTint(bg, PNL_GREEN, ink, PNL_CONTRAST_TARGET);
    const negColor = legibleTint(bg, PNL_RED, ink, PNL_NEG_CONTRAST_TARGET);
    const showAligned = w >= LEGEND_ALIGNED_MIN_W;
    const showGainLoss = showAligned;
    // Symbols are short (2-5 chars) and don't need LEGEND_NAME_MAX_W's
    // full budget the way a GICS sector name does -- still fit-to-content
    // (capped smaller) so a short ticker doesn't reserve more name room
    // than it needs, leaving a bit more to the tile's own physical limit.
    const availableForName = (w - 7) - LEGEND_VALUE_RESERVE - SYMBOL_SIDE_GAP - SYMBOL_SIDE_RESERVE - LEGEND_PCT_COL_W - 4 - 19;
    const longestName = legendRows.reduce((m, r) => Math.max(m, r.tos_symbol.length), 0);
    const nameAreaW = showAligned
      ? Math.max(0, Math.min(60, longestName * legendFontSize * 0.62, availableForName))
      : (w - 24);
    const pctColX = 19 + nameAreaW + 4 + LEGEND_PCT_COL_W;
    const symKColX = pctColX + LEGEND_PCT_GAP + LEGEND_K_RESERVE;
    const caretColX = symKColX + LEGEND_K_GAP + LEGEND_CARET_RESERVE;
    const gainPctColX = caretColX + LEGEND_CARET_GAP + LEGEND_GAINPCT_RESERVE;
    const sideColX = gainPctColX + SYMBOL_SIDE_GAP + SYMBOL_SIDE_RESERVE;
    const maxChars = Math.max(3, Math.floor(nameAreaW / (legendFontSize * 0.62)));
    let ly = firstRowY;
    for (const row of legendRows) {
      if (h <= ly + legendRowH - 4) break;
      const pct = Math.round(row[basis] / total * 100);
      const label = row.tos_symbol.length > maxChars ? row.tos_symbol.slice(0, Math.max(1, maxChars - 1)) + '…' : row.tos_symbol;
      // Same single outlook caret as the Sector/Asset Class legends above
      // it -- here there's no crowd to tally or ETF to stand in for, it's
      // just the stock's own rr_outlook directly. Was a colored dot keyed
      // to final_code (the trading signal, still shown separately via the
      // BUY/SELL column at the far right of this same row) -- replaced so
      // all three legend levels read the same way. User: "What do the
      // dots before stock symbols represent?" -> "do the same for stocks"
      // -- 2026-09-06.
      appendOutlookCaret(g, 11, ly, _outlookDir(symbolDetail.get(row.tos_symbol)?.rr_outlook), ink, posColor, negColor);
      g.append('text').attr('x', 19).attr('y', ly).attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.9)
        .text(showAligned ? label : `${label} ${pct}%`);
      if (showAligned) {
        g.append('text').attr('x', pctColX).attr('y', ly).attr('text-anchor', 'end')
          .attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.9)
          .text(`${pct}%`);
        g.append('text').attr('x', symKColX).attr('y', ly).attr('text-anchor', 'end')
          .attr('font-size', legendFontSize).attr('fill', ink).attr('opacity', 0.85)
          .text(fmtK(row.value));
        if (showGainLoss && row.costBasis) {
          const glPct = row.gainDollar / row.costBasis * 100;
          const up = glPct >= 0;
          const color = up ? posColor : negColor;
          g.append('text').attr('x', caretColX).attr('y', ly).attr('text-anchor', 'end')
            .attr('font-size', legendFontSize).attr('font-weight', 700).attr('fill', color)
            .text(up ? '▲' : '▼');
          g.append('text').attr('x', gainPctColX).attr('y', ly).attr('text-anchor', 'end')
            .attr('font-size', legendFontSize).attr('font-weight', 700).attr('fill', color)
            .text(fmtSignedPct1(glPct));
        }
        const side = actionSide(symbolDetail.get(row.tos_symbol)?.final_code);
        if (side === 'buy' || side === 'sell') {
          g.append('text').attr('x', sideColX).attr('y', ly).attr('text-anchor', 'end')
            .attr('font-size', legendFontSize).attr('font-weight', 700)
            .attr('fill', side === 'buy' ? posColor : negColor)
            .text(side === 'buy' ? 'BUY' : 'SELL');
        }
      }
      ly += legendRowH;
    }
    return ly;
  }

  // ---- "By Account" root tiles: accounts, colored by acctColor. Click
  // drills into that account's Asset Class breakdown (renderHierarchy).
  // Small "Stocks →" corner link skips straight past that Asset Class /
  // Sector breakdown to the account's flat symbol tiles -- same shortcut
  // mechanism (ALL_ASSET_CLASSES) the Equities "All stocks" link already
  // uses, just reachable one level earlier. User: "top level filters -- if
  // they have sublevels then the tile should have a 'Stocks' link so I can
  // go to stocks directly."
  function renderAccountFlat(W, H) {
    // Count mode sizes tiles by posCount -- an all-cash account (real $,
    // zero stock positions, e.g. an HSA or a beneficiary account sitting
    // in cash) has posCount=0, so `rawValueFn(a) > 0` was silently
    // excluding it from `sized` below and it never got a tile at all in
    // the DEFAULT (Count) mode -- confirmed live: 2 of 6 real accounts
    // ("A"/HSA ...311, both cash-only) were completely missing from the
    // treemap. The `cashByAccount` build()-time fold-in (this file's own
    // earlier comment) only guaranteed these accounts exist in `ACCOUNTS`
    // with a real `total`, not that Count mode's sizing basis would ever
    // be positive for them. Nominal size 1 (a real cash account still
    // "counts" as one thing to show) fixes it without disturbing relative
    // sizing among accounts that DO hold positions. User: "Cash is missing
    // from Universe. Check and fix it" -- 2026-09-05.
    const rawValueFn = a => sizeMode === 'capital' ? a.total : (a.posCount > 0 ? a.posCount : (a.total > 0 ? 1 : 0));
    const sized = ACCOUNTS.filter(a => rawValueFn(a) > 0);
    const root = d3.hierarchy({ children: sized }).sum(floorValueFn(sized, rawValueFn)).sort((a, b) => b.value - a.value);
    d3.treemap().tile(SQUARE_TILE).size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    svg.selectAll('*').remove();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => cssVar(acctColor.get(d.data.key)));

    // Every tile's own % share of the whole screen -- ONE %, on $ value
    // (rawValueFn above, always 'capital'/$ now that the Count/Capital
    // toggle is forced to Capital for this view), not a second % for
    // symbol count too -- that's not what actually sizes the tile.
    // Percentages are of `sized` (the same set actually getting a tile),
    // so they sum to ~100% among what's on screen. User: "Display % of
    // tile occupation... (which is below the header, ex, equities)" --
    // 2026-09-06, then "No. Only one not two. The measurement you are
    // using for tile. i belive it is amount." -- 2026-09-06.
    const totalValue = d3.sum(sized, a => a.total);
    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      const fill = cssVar(acctColor.get(d.data.key)); const ink = labelColorFor(fill);
      const valuePct = totalValue ? Math.round(d.data.total / totalValue * 100) : 0;
      const sub = d.data.posCount > 0
        ? `${fmtUsd(d.data.total)} (${valuePct}%) · ${d.data.posCount} symbol${d.data.posCount === 1 ? '' : 's'}`
        : `${fmtUsd(d.data.total)} (${valuePct}%) · all cash`;
      drawGroupTileLabel(d3.select(this), w, h, ink, d.data.label, sub);
      const cashVal = cashByAccount.get(d.data.key) || 0;
      const securitiesVal = d.data.total - cashVal;
      let contentY = appendAccountPnlAndSignals(d3.select(this), w, h, fill, ink, acctGain.get(d.data.key), acctActionCounts.get(d.data.key), cashVal, securitiesVal, realizedByAccount.get(d.data.key), dividendsByAccount.get(d.data.key));
      contentY = appendAccountAssetBreakdown(d3.select(this), w, h, fill, ink, contentY, acctAssetBreakdown.get(d.data.key));
      contentY = appendAccountSectorBreakdown(d3.select(this), w, h, fill, ink, contentY, acctSectorBreakdown.get(d.data.key));
      contentY = appendBuySellList(d3.select(this), w, h, fill, ink, contentY, acctActionCounts.get(d.data.key));
      // Small "Stocks →" corner link -- skips the Asset Class / Sector
      // breakdown and goes straight to every held symbol in this account,
      // flat. Own click handler stops propagation so the rest of the tile
      // keeps its normal "go to Asset Classes" click. Stacks below
      // whatever P&L/signal/asset-breakdown content actually rendered
      // (contentY) rather than a fixed y, so nothing ever overwrites
      // anything else on a narrow tile that has room for all of it.
      if (d.data.posCount > 0 && canShowCornerLink(w, h, contentY)) {
        appendCornerLink(d3.select(this), w, h, ink, () => { drill = { account: d.data.key, assetClass: ALL_ASSET_CLASSES }; render(); }, contentY);
      }
    });

    cell.on('mousemove', (evt, d) => {
      if (!_uvOverHeader(evt)) { tt.classList.remove('show'); return; }
      const cashVal = cashByAccount.get(d.data.key) || 0;
      const securitiesVal = d.data.total - cashVal;
      // 2026-09-03 (held-perspective proposal): per-account unrealized P&L
      // (acctGain, summed from POS in build()) + realized YTD
      // (realizedByAccount, drv_realized_gain rollup) -- both optional,
      // rendered only when present so an account with no gain data (e.g.
      // all-cash) doesn't show a misleading "$0".
      const g = acctGain.get(d.data.key);
      const rg = realizedByAccount.get(d.data.key);
      const dv = dividendsByAccount.get(d.data.key);
      const gainPct = g && g.costBasis ? (g.totalGainDollar / g.costBasis * 100) : null;
      const hint = d.data.posCount > 0 ? 'Click to see asset classes · or "Stocks" to skip straight to symbols' : 'No securities held';
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.label)}</div>` +
        `<div class="uv-tt-row"><span>Total</span><span>${fmtUsd(d.data.total)}</span></div>` +
        `<div class="uv-tt-row"><span>Securities</span><span>${fmtUsd(securitiesVal)}</span></div>` +
        `<div class="uv-tt-row"><span>Cash</span><span>${fmtUsd(cashVal)}</span></div>` +
        (g ? `<div class="uv-tt-row"><span>Unrealized</span>${gainSpanHtml(g.totalGainDollar, gainPct)}</div>` : '') +
        (rg ? `<div class="uv-tt-row"><span>Realized (YTD)</span>${gainSpanHtml(rg.ytd_realized, null)}</div>` : '') +
        (dv && dv.ytd_dividends ? `<div class="uv-tt-row"><span>Dividends (YTD)</span>${gainSpanHtml(dv.ytd_dividends, null)}</div>` : '') +
        `<div class="uv-tt-row"><span>Symbols</span><span>${d.data.posCount}</span></div>` +
        `<div class="uv-tt-hint">${hint}</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => { if (d.data.posCount > 0) { drill = { account: d.data.key }; render(); } });
  }

  // ---- "By Source" root: tiles = outlook sources (RR/CALL/ETF/II/SSS/
  // PS/...). Unlike ACCOUNTS (fixed once in build(), always Held), this is
  // recomputed from the CURRENT Filter's rows on every render -- a source
  // can flag a not-held symbol too, so All/Held/Actionable stays a live
  // choice here (see currentScopeRows()'s own comment). Click drills into
  // that source's own Asset Class -> Sector -> Symbol hierarchy
  // (renderHierarchy, via drill = {source}).
  function renderSourceRoot() {
    const rows = FILTERS[currentFilter].rows;
    const srcAgg = aggregateSources(rows);

    $('uvTotalCount').textContent = fmtInt(rows.length);
    $('uvTotalSectors').textContent = srcAgg.length;
    $('uvSectorsUnit').textContent = 'sources';
    $('uvSHeld').textContent = d3.sum(srcAgg, d => d.held) + ' symbols';
    $('uvSCapital').textContent = fmtUsd(d3.sum(srcAgg, d => d.held_value));
    $('uvFilterCount').textContent = '';

    renderCrumbs();
    $('uvSideHeading').textContent = 'Top sources';

    const wrap = document.querySelector('.uv-svg-wrap');
    const W = wrap.clientWidth, H = wrap.clientHeight;
    svg.attr('viewBox', `0 0 ${W} ${H}`);

    if (srcAgg.length === 0) {
      svg.selectAll('*').remove();
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text('No symbols match this filter.');
      $('uvRankList').innerHTML = ''; $('uvSLargest').textContent = '—';
      return;
    }

    renderSourceFlat(srcAgg, W, H, src => { drill = { source: src }; render(); },
      src => { drill = { source: src, assetClass: ALL_ASSET_CLASSES }; render(); });

    const ranklist = $('uvRankList');
    const top = [...srcAgg].sort((a, b) => (sizeMode === 'capital' ? b.held_value - a.held_value : b.count - a.count)).slice(0, 8);
    ranklist.innerHTML = top.map(d => {
      const dot = cssVar(sourceColorAssign.get(d.source) || '--cat-unmapped');
      const val = sizeMode === 'capital' ? fmtUsd(d.held_value) : fmtInt(d.count);
      return `<li class="uv-rank-row"><span class="uv-rank-dot" style="background:${dot};"></span>` +
        `<span class="uv-rank-name">${esc(d.source)}</span><span class="uv-rank-val">${val}</span></li>`;
    }).join('');
    $('uvSLargest').textContent = top[0] ? top[0].source : '—';
  }

  // ---- Source tiles, colored by sourceColorAssign -- same generic
  // {count,held,held_value,sample}-keyed tile renderer as
  // renderSectorWithinAsset, just at root level and keyed by source code
  // instead of sector name. `onAllStocks(source)` fires only from the small
  // "Stocks →" corner link -- same shortcut as the Account root tiles, skips
  // the Asset Class / Sector breakdown and goes straight to this source's
  // flat symbol tiles.
  function renderSourceFlat(data, W, H, onClick, onAllStocks) {
    const rawValueFn = d => sizeMode === 'capital' ? d.held_value : d.count;
    const sized = data.filter(d => rawValueFn(d) > 0);
    const root = d3.hierarchy({ children: sized }).sum(floorValueFn(sized, rawValueFn)).sort((a, b) => b.value - a.value);
    d3.treemap().tile(SQUARE_TILE).size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    svg.selectAll('*').remove();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    const colorFn = d => cssVar(sourceColorAssign.get(d.source) || '--cat-unmapped');
    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => colorFn(d.data));

    // Each Source root tile gets the SAME full recipe the Account root
    // tile has -- P&L block, Asset Class bar+legend, Sector bar+legend,
    // Buy/Sell list -- scoped to that one source's positions (a symbol's
    // `sources` membership, not a POS-row field, so this filters POS by
    // source per tile via computeScopedBreakdown rather than a precomputed
    // per-account map). Precomputed once per source here (there are only
    // a handful), not recomputed per treemap leaf. User: "do the same when
    // you choose all other options starting with By Asset Class, By
    // Source etc." -- 2026-09-06.
    const sourceBreakdown = new Map(data.map(d => [
      d.source,
      computeScopedBreakdown(POS.filter(r => (symbolDetail.get(r.tos_symbol)?.sources || []).includes(d.source))),
    ]));
    const totalValue = d3.sum(data, d => d.held_value);

    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      const fill = colorFn(d.data); const ink = labelColorFor(fill);
      const g = d3.select(this);
      drawGroupTileLabel(g, w, h, ink, d.data.source, groupTileSubText(d.data.count, d.data.held_value, totalValue));
      const scoped = sourceBreakdown.get(d.data.source);
      let contentY = PNL_START_Y;
      if (scoped) {
        contentY = appendAccountPnlAndSignals(g, w, h, fill, ink, scoped.gain, scoped.counts, null, null, null, null);
        contentY = appendAccountAssetBreakdown(g, w, h, fill, ink, contentY, scoped.assetBreakdown);
        contentY = appendAccountSectorBreakdown(g, w, h, fill, ink, contentY, scoped.sectorBreakdown);
        contentY = appendBuySellList(g, w, h, fill, ink, contentY, scoped.counts);
      }
      if (canShowCornerLink(w, h, contentY) && onAllStocks) {
        appendCornerLink(g, w, h, ink, () => onAllStocks(d.data.source), contentY);
      }
    });

    cell.on('mousemove', (evt, d) => {
      if (!_uvOverHeader(evt)) { tt.classList.remove('show'); return; }
      const heldPct = d.data.count ? Math.round((d.data.held / d.data.count) * 100) : 0;
      tt.innerHTML = `<div class="uv-tt-title">${esc(d.data.source)}</div>` +
        `<div class="uv-tt-row"><span>Symbols</span><span>${fmtInt(d.data.count)}</span></div>` +
        `<div class="uv-tt-row"><span>Held</span><span>${d.data.held} (${heldPct}%)</span></div>` +
        `<div class="uv-tt-row"><span>Capital</span><span>${fmtUsd(d.data.held_value)}</span></div>` +
        `<div class="uv-tt-syms">${d.data.sample.map(esc).join(' · ')}${d.data.count > d.data.sample.length ? ' …' : ''}</div>` +
        `<div class="uv-tt-hint">Click to see asset classes · or "Stocks" to skip straight to symbols</div>`;
      tt.style.left = (evt.clientX + 14) + 'px'; tt.style.top = (evt.clientY + 14) + 'px'; tt.classList.add('show');
    }).on('mouseleave', () => tt.classList.remove('show'))
      .on('click', (evt, d) => onClick(d.data.source));
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
    const rawValueFn = d => sizeMode === 'capital' ? d.held_value : d.count;
    const sized = data.filter(d => rawValueFn(d) > 0);
    const root = d3.hierarchy({ children: sized }).sum(floorValueFn(sized, rawValueFn)).sort((a, b) => b.value - a.value);
    d3.treemap().tile(SQUARE_TILE).size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    svg.selectAll('*').remove();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    const colorFn = d => cssVar(assetColorAssign.get(d.asset_class) || '--cat-unmapped');
    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => colorFn(d.data));

    // Every Asset Class tile gets the SAME P&L block (Unrealized/Today/
    // Signals -- Cash/Realized/Dividends don't exist per asset class, so
    // those lines just don't render, same "only if the data exists"
    // gating appendAccountPnlAndSignals already has) plus, on the
    // Equities tile specifically, the SAME Sector composition bar+legend
    // the Account tile shows -- regardless of which View got here
    // (Account, Source, or the whole-portfolio "By Asset Class" root).
    // scopedBreakdownFor resolves account/source/whole-portfolio data
    // uniformly (precomputed maps for the account fast-path, computed on
    // the fly otherwise). User: "Once i click on the account -> next
    // screen -> do the same as this screen" -- 2026-09-06, then "do the
    // same when you choose all other options starting with By Asset
    // Class, By Source etc." -- 2026-09-06.
    const scoped = scopedBreakdownFor(drill);
    const gainByAssetClass = new Map(scoped.assetBreakdown.map(r => [r.asset_class, r]));
    const totalValue = d3.sum(data, d => d.held_value);

    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      const fill = colorFn(d.data); const ink = labelColorFor(fill);
      const g = d3.select(this);
      drawGroupTileLabel(g, w, h, ink, d.data.asset_class, groupTileSubText(d.data.count, d.data.held_value, totalValue));
      let contentY = PNL_START_Y;
      const gainRow = gainByAssetClass.get(d.data.asset_class);
      if (gainRow) {
        const gain = { costBasis: gainRow.costBasis, totalGainDollar: gainRow.gainDollar, todayGainDollar: gainRow.todayGainDollar };
        const counts = { buy: gainRow.buy, sell: gainRow.sell, buySymbols: gainRow.buySymbols, sellSymbols: gainRow.sellSymbols };
        contentY = appendAccountPnlAndSignals(g, w, h, fill, ink, gain, counts, null, null, null, null);
        if (d.data.asset_class === 'Equities') {
          contentY = appendAccountSectorBreakdown(g, w, h, fill, ink, contentY, scoped.sectorBreakdown);
        }
        contentY = appendBuySellList(g, w, h, fill, ink, contentY, counts);
      }
      // Small "Stocks →" corner link, Equities tile only -- skips the
      // Sector step and goes straight to every equity symbol, flat. Its
      // own click handler stops propagation so the rest of the tile keeps
      // its normal "go to Sectors" click. Stacks below whatever P&L/sector
      // content actually rendered (contentY), same as the Account root
      // tile's own "Stocks →" link does.
      if (d.data.asset_class === 'Equities' && canShowCornerLink(w, h, contentY) && onAllStocks) {
        appendCornerLink(g, w, h, ink, () => onAllStocks(d.data.asset_class), contentY);
      }
    });

    cell.on('mousemove', (evt, d) => {
      if (!_uvOverHeader(evt)) { tt.classList.remove('show'); return; }
      const heldPct = d.data.count ? Math.round((d.data.held / d.data.count) * 100) : 0;
      const hint = d.data.asset_class === 'Equities' ? 'Click to see sectors · or "Stocks" to skip sectors' : 'Click to see symbols';
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
  // as the same color here as anywhere else it appears. Every scope
  // (Account, Source, or the whole-portfolio root -- same
  // scopedBreakdownFor as renderAssetClassFlat), each tile also gets the
  // P&L block, a "Stocks" legend (the individual symbols behind that
  // sector), and the Buy/Sell list -- the same recipe applied one level
  // deeper each time. User: "Once i click on the account -> next screen
  // -> do the same as this screen" -- 2026-09-06, then "Now one level
  // deep, dsiplay stocks, % and amount, caret,% up or down" -- 2026-09-06,
  // then "do the same when you choose all other options starting with By
  // Asset Class, By Source etc." -- 2026-09-06.
  function renderSectorWithinAsset(sectors, W, H, onClick) {

    const rawValueFn = d => sizeMode === 'capital' ? d.held_value : d.count;
    const sized = sectors.filter(d => rawValueFn(d) > 0);
    const root = d3.hierarchy({ children: sized }).sum(floorValueFn(sized, rawValueFn)).sort((a, b) => b.value - a.value);
    d3.treemap().tile(SQUARE_TILE).size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    svg.selectAll('*').remove();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    const colorFn = d => cssVar(catAssign.get(d.sector) || '--cat-unmapped');
    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => colorFn(d.data));

    const scoped = scopedBreakdownFor(drill);
    const gainBySector = new Map(scoped.sectorBreakdown.map(r => [r.sector, r]));
    const symbolsBySector = scoped.sectorSymbolBreakdown;
    const totalValue = d3.sum(sectors, d => d.held_value);

    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      const fill = colorFn(d.data); const ink = labelColorFor(fill);
      const g = d3.select(this);
      drawGroupTileLabel(g, w, h, ink, d.data.sector, groupTileSubText(d.data.count, d.data.held_value, totalValue));
      const gainRow = gainBySector && gainBySector.get(d.data.sector);
      if (gainRow) {
        const gain = { costBasis: gainRow.costBasis, totalGainDollar: gainRow.gainDollar, todayGainDollar: gainRow.todayGainDollar };
        const counts = { buy: gainRow.buy, sell: gainRow.sell, buySymbols: gainRow.buySymbols, sellSymbols: gainRow.sellSymbols };
        // No appendBuySellList here -- the Stocks legend below already
        // carries a per-row BUY/SELL column, so a separate "Buy: ... /
        // Sell: ..." list would just repeat the same tickers. User: "add
        // Buy or Sell as a last column instead of listing at the bottom
        // for this" -- 2026-09-06.
        const contentY = appendAccountPnlAndSignals(g, w, h, fill, ink, gain, counts, null, null, null, null);
        appendSymbolBreakdown(g, w, h, fill, ink, contentY, symbolsBySector && symbolsBySector.get(d.data.sector));
      }
    });

    cell.on('mousemove', (evt, d) => {
      if (!_uvOverHeader(evt)) { tt.classList.remove('show'); return; }
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
    const unit = sizeMode;
    // realValue preserves the actual $ value through the Count-mode
    // override below (which blanks `value` to 1 for treemap AREA only) --
    // the tile's own display wants the real $ regardless of what's
    // currently sizing it. User: "display as much information as you can
    // in the tile as we have space" -- 2026-09-06.
    if (unit === 'count') rows = rows.map(r => ({ ...r, value: 1, realValue: r.value }));
    else rows = rows.filter(r => r.value > 0); // capital sizing: a $0 position/symbol gets no tile

    // Color/Style/Risk Range filters -- narrow to one trading-signal
    // side, one style tag, and/or a Risk Range position band, applied
    // here (drilldown level) only; rollups above are unaffected.
    if (currentColorFilter !== 'all') {
      rows = rows.filter(r => actionSide(r.detail.final_code) === currentColorFilter);
    }
    if (currentStyleFilter !== 'all') {
      rows = rows.filter(r => (r.detail.style_tags || []).includes(currentStyleFilter));
    }
    if (rrMin > 0 || rrMax < 100) {
      rows = rows.filter(r => {
        const pos = rawRrPos(r.detail.lrr, r.detail.trr, r.detail.last_price);
        if (pos == null) return false;
        const clamped = Math.max(0, Math.min(100, pos));
        return clamped >= rrMin && clamped <= rrMax;
      });
    }

    svg.selectAll('*').remove();
    if (rows.length === 0) {
      const msg = currentStyleFilter !== 'all' ? `No ${currentStyleFilter} symbols here.`
        : currentColorFilter !== 'all' ? `No ${currentColorFilter} symbols here.`
        : (rrMin > 0 || rrMax < 100) ? `No symbols in the ${rrMin}–${rrMax}% Risk Range band here.`
        : 'No symbols here.';
      svg.append('text').attr('x', 16).attr('y', 24).attr('fill', cssVar('--text-3')).attr('font-size', 12)
        .text(msg);
      return;
    }

    const root = d3.hierarchy({ children: rows }).sum(floorValueFn(rows, r => r.value)).sort((a, b) => b.value - a.value);
    d3.treemap().tile(SQUARE_TILE).size([W, H]).paddingInner(2).paddingOuter(2).round(true)(root);

    const leaves = root.leaves();
    const cell = svg.selectAll('g.uv-cell').data(leaves).join('g')
      .attr('class', 'uv-cell-group uv-cell').attr('tabindex', 0)
      .attr('transform', d => `translate(${d.x0},${d.y0})`);

    // per-symbol color = trading signal (final_code) by default, or
    // unrealized P&L % in Gain/Loss mode -- see tileColor()'s own comment.
    cell.append('rect').attr('class', 'uv-cell-rect')
      .attr('width', d => Math.max(0, d.x1 - d.x0)).attr('height', d => Math.max(0, d.y1 - d.y0))
      .attr('rx', 3).attr('fill', d => tileColor(d.data.detail));

    // Progressive detail as the tile has room -- name always, then action
    // code, then value, then Trade/Trend above/below coloring, then a mini
    // Risk Range bar. Same fields/formula the Action popup's own Td/Tn
    // boxes and RR bar use (trade_line_value/trend_line_value, rawRrPos),
    // just miniaturized onto the tile.
    cell.each(function (d) {
      const w = d.x1 - d.x0, h = d.y1 - d.y0;
      const det = d.data.detail;
      const fill = tileColor(det);
      const ink = labelColorFor(fill);
      const g = d3.select(this);

      // contentBottom tracks the lowest y drawn so far, so the RR bar
      // (added below) can place itself under whatever actually rendered
      // above it instead of a fixed offset that risked overlapping Td/Tn
      // once its own threshold was lowered independently.
      let contentBottom = 0;

      // Symbol name -- draw down to a much smaller minimum than the
      // richer progressive detail below, so a short treemap row (a whole
      // band of short-but-not-narrow tiles, common with hundreds of
      // symbols) still shows ticker names instead of going fully blank.
      // User: "Name doesn't show in the tile that whole row."
      if (w >= 16 && h >= 10) {
        const nameFontSize = w < 30 ? 7.5 : (w < 60 ? 9 : 10.5);
        const nameY = h < 16 ? Math.max(8, Math.round(h / 2) + 3) : 13;
        // Action code (BM/SA/etc) -- same line as the name, right-
        // justified, instead of its own line below. User: "display BM/BTM
        // same level as symbol right justified." Only when there's room
        // for a short code beside the name (w>=40); reserved out of the
        // name's own width budget below so the two never collide. Used to
        // switch to showing unrealized % here instead, in Gain/Loss color
        // mode (2026-09-03) -- that toggle is gone (see tileColor's own
        // comment); the action code always shows here now, and gain/loss
        // is always visible too, via the Unrealized/Today lines below.
        const codeText = det.final_code;
        const showCode = !!codeText && w >= 40;
        const codeReserve = showCode ? 24 : 0;
        const maxChars = Math.max(1, Math.floor((w - 4 - codeReserve) / (nameFontSize * 0.62)));
        const symName = d.data.tos_symbol;
        // Action popover (2026-09-06) -- hovering the header/name text
        // specifically (not the whole tile -- see .uv-c-name's own
        // pointer-events override in universe.html) opens the same rich
        // popover Actionable's Action-badge hover shows (_uvShowActionPopover
        // -> _buildActionPopHtmlV2, both above). `det` (this tile's full
        // merged row) is already in scope here. The tile's own click
        // handler (below, cell.on('click', ...)) is untouched -- it still
        // navigates to /actionable, so hover gives a quick in-place
        // preview and click still drills into the full screen. User: "make
        // the popover pops up only when i hover over the header, for ex,
        // hover on account name, source name, stock name etc" -- 2026-09-06.
        g.append('text').attr('class', 'uv-c-name').attr('x', 4).attr('y', nameY)
          .attr('font-size', nameFontSize).attr('fill', ink)
          .text(symName.length > maxChars ? symName.slice(0, maxChars) : symName)
          .on('mouseenter', function () { _uvShowActionPopover(this, det); })
          .on('mouseleave', function () { _uvHideActionPopover(); });
        contentBottom = nameY;

        if (showCode) {
          g.append('text').attr('x', w - 4).attr('y', nameY).attr('text-anchor', 'end')
            .attr('font-size', 6.5).attr('font-weight', 400).attr('fill', ink).attr('opacity', 0.85)
            .text(codeText);
        }
      }
      if (w < 30 || h < 18) return; // too small for the richer detail below

      // Every detail line below (Value, Unrealized, Today, Td, Tn, Risk
      // Range) uses the SAME label|value two-column format the Account/
      // Asset Class/Sector tiles' own P&L block uses (drawRow there) --
      // label left (small, dim), value right-anchored (bold/colored) --
      // instead of the old mix of inline "text + suffix" strings each
      // line invented its own way. Colors are legibleTint-computed
      // against THIS tile's own fill (not a fixed hex) -- the same fix as
      // everywhere else in this session; a flat #16a34a/#dc2626 goes
      // weak-to-illegible on some of the darker/mid-tone action-color and
      // Gain/Loss-mode fills. User: "make sure fonts are in contrast
      // colors, display as much information as you can in the tile as we
      // have space" -- 2026-09-06, then "add risk range numbers / format
      // labels and numbers like others" -- 2026-09-06.
      const posColor = legibleTint(fill, PNL_GREEN, ink, PNL_CONTRAST_TARGET);
      const negColor = legibleTint(fill, PNL_RED, ink, PNL_NEG_CONTRAST_TARGET);
      const lineH = 11;
      let y = 35;
      const drawSubline = (label, valueText, color, weight, opacity) => {
        if (h <= y + lineH - 3) return;
        g.append('text').attr('x', 5).attr('y', y).attr('font-size', 9)
          .attr('fill', ink).attr('opacity', 0.7).text(label);
        g.append('text').attr('x', w - 5).attr('y', y).attr('text-anchor', 'end')
          .attr('font-size', 9).attr('font-weight', weight).attr('fill', color).attr('opacity', opacity)
          .text(valueText);
        contentBottom = Math.max(contentBottom, y);
        y += lineH;
      };
      if (h > 40) {
        const realValue = d.data.realValue != null ? d.data.realValue : d.data.value;
        if (realValue > 0) drawSubline('Value', fmtUsd(realValue), ink, 400, 0.85);
        if (det.total_gain_dollar != null) {
          const up = det.total_gain_dollar >= 0;
          const pctTxt = det.total_gain_pct != null ? ` (${fmtSignedPct1(det.total_gain_pct)})` : '';
          drawSubline('Unrealized', `${up ? '▲' : '▼'} ${fmtSignedUsd(det.total_gain_dollar)}${pctTxt}`, up ? posColor : negColor, 700, 1);
        }
        if (det.today_gain_dollar != null) {
          const up = det.today_gain_dollar >= 0;
          const pctTxt = det.today_gain_pct != null ? ` (${fmtSignedPct1(det.today_gain_pct)})` : '';
          drawSubline('Today', `${up ? '▲' : '▼'} ${fmtSignedUsd(det.today_gain_dollar)}${pctTxt}`, up ? posColor : negColor, 700, 0.9);
        }
      }

      // Trade/Trend: caret (direction) + Td/Tn value colored by above/
      // below (green above, red below, same convention as the Action
      // popup's Td/Tn boxes) + signed stop-proximity SD in parentheses
      // (lineProximitySd -- same formula/sign as the popup's own SD badge).
      const lastPx = det.last_price;
      if (w > 60) {
        const lineRow = (label, lineVal) => {
          if (lineVal == null || lastPx == null) return;
          const above = lastPx >= lineVal;
          const color = above ? posColor : negColor;
          const sd = lineProximitySd(det.hv, lastPx, lineVal);
          const valueText = `${above ? '▲' : '▼'} ${lineVal.toFixed(1)}${sd != null ? ` (${sd.toFixed(1)}σ)` : ''}`;
          drawSubline(label, valueText, color, 700, 1);
        };
        lineRow('Td', det.trade_line_value);
        lineRow('Tn', det.trend_line_value);
      }

      // Risk Range number -- position % (plus the actual LRR/TRR levels
      // once there's extra width), same label|value line as everything
      // above it instead of leaving the bar below as the only numeric
      // representation. User: "add risk range numbers" -- 2026-09-06.
      const pos = rawRrPos(det.lrr, det.trr, lastPx);
      if (pos != null && w > 60) {
        const rrText = w > 140 && det.lrr != null && det.trr != null
          ? `${Math.round(pos)}% (${det.lrr.toFixed(1)}/${det.trr.toFixed(1)})`
          : `${Math.round(pos)}%`;
        drawSubline('Risk Range', rrText, ink, 700, 0.95);
      }

      // Macro / Sources / Held / PVV -- compact, one representative line
      // per category, straight off the same get_actionable() row the
      // Actionable screen's own grid columns already read (surfaced here
      // by api/routers/universe.py), except Held (which account(s) hold
      // this symbol -- symbolAccounts, built client-side from POS, not a
      // grid column at all). One line each rather than the full grid -- a
      // treemap tile has nowhere near a grid row's width. PVV is colored
      // buy/sell like the rest of this block (legibleTint posColor/
      // negColor); Macro/Sources/Held stay in plain `ink` -- there's no
      // existing tinted-color pair for the quad-regime scale the way
      // there is for gain/loss, and guessing one would reintroduce the
      // exact uncomputed-contrast risk this whole pass fixed. User:
      // "display/add macro, sources, technical, PVV, & other columns
      // that you see on actionable screen" -- 2026-09-06, then "Remove
      // the RSI from stock tile and display where it is held instead" --
      // 2026-09-06.
      if (det.macro_value) {
        const conflictMark = det.macro_conflict ? ' ⚡' : '';
        drawSubline('Macro', `${det.macro_value}${conflictMark}`, ink, 700, 0.9);
      }
      if (det.sources && det.sources.length) {
        drawSubline('Sources', det.sources.join(', '), ink, 400, 0.85);
      }
      const heldIn = symbolAccounts.get(d.data.tos_symbol);
      if (heldIn && heldIn.length) {
        drawSubline('Held', heldIn.join(', '), ink, 400, 0.85);
      }
      if (det.pvv_decision) {
        const pvvSide = /^BUY/.test(det.pvv_decision) ? 'buy' : /^(SELL|REDUCE|TRIM|AVOID)/.test(det.pvv_decision) ? 'sell' : null;
        const pvvColor = pvvSide === 'buy' ? posColor : pvvSide === 'sell' ? negColor : ink;
        drawSubline('PVV', det.pvv_decision.replace(/_/g, ' '), pvvColor, 700, pvvSide ? 1 : 0.85);
      }

      // mini Risk Range bar -- clamped track + a tick at the raw
      // (possibly <0 or >100) position, ink-colored so it stays legible
      // against whichever action color the tile itself is filled with.
      // Placed under whatever content actually rendered above it
      // (contentBottom) instead of the old fixed h>62 threshold, so it
      // shows on plenty of tiles too small for Td/Tn but with a little
      // room to spare below the name/action code. User: "you could show
      // the riskrange bar on tiles. right?"
      if (pos != null && w > 34 && h > contentBottom + 14) {
        const barW = w - 10, barY = h - 10, clamped = Math.max(0, Math.min(100, pos));
        g.append('rect').attr('x', 5).attr('y', barY).attr('width', barW).attr('height', 3)
          .attr('rx', 1.5).attr('fill', ink).attr('opacity', 0.25);
        g.append('rect').attr('x', 5).attr('y', barY).attr('width', barW * clamped / 100).attr('height', 3)
          .attr('rx', 1.5).attr('fill', ink).attr('opacity', 0.75);
        g.append('rect').attr('x', 5 + barW * clamped / 100 - 1).attr('y', barY - 2).attr('width', 2).attr('height', 7)
          .attr('fill', ink);
      }
    });

    // No plain `tt` tooltip on Symbol tiles any more -- the header-hover
    // Action popover (wired inside cell.each above, on .uv-c-name) already
    // covers everything this used to show (Signal/Value/Unrealized/Today/
    // Realized/Trade-Trend/Risk Range) and far more; keeping both would
    // stack two floating boxes over the same hover gesture. Click still
    // navigates to the full Actionable screen.
    cell.on('click', (evt, d) => { window.location.href = '/actionable?symbol=' + encodeURIComponent(d.data.tos_symbol); });
  }

  // =========================================================================
  // Action popover port (2026-09-06). User: "Also display the same popover
  // that is being displayed in Actionable screen -> Action column -> Action
  // popover." A PARALLEL REIMPLEMENTATION of web/actionable.js's
  // _buildActionPopHtmlV2 stack -- same "copy, don't share" precedent
  // web/app.js's #quadPop already established for this exact popover shell
  // (see that file's own comment, ~line 1191-1197), NOT a shared module;
  // web/actionable.js/.html stay untouched. Every function below mirrors
  // its actionable.js namesake's logic verbatim except: escapeHtml(...) ->
  // this file's own esc(...); state.* -> this file's own uvPopState.*;
  // window.mtTip.candleSvg -> _uvCandleSvg (replicated below, market_bar.js
  // itself isn't loaded on this page -- see universe.html's own comment);
  // fmtUsd is untouched -- both files define a same-named function and this
  // one intentionally keeps using ITS OWN (no cents, "-$" sign placement).
  //
  // Trigger/dismiss are intentionally NOT the same as the Actionable
  // source (which is hover-anywhere-on-a-cell + pointer-events:none): user
  // course-correction, "make the popover pops up only when i hover over
  // the header, for ex, hover on account name, source name, stock name
  // etc" -- 2026-09-06. So here it's mouseenter/mouseleave bound to the
  // Symbol tile's OWN .uv-c-name text element specifically (wired at the
  // bottom of renderSymbolTiles' cell.each loop, above), not the whole
  // tile -- the tile's own click-to-navigate-to-Actionable (renderSymbolTiles'
  // own `cell.on('click', ...)`) is left exactly as it was: hover now gives
  // a quick in-place preview, click still drills into the full screen.
  // Escape is kept as a keyboard-only safety net alongside hover-out.
  // =========================================================================

  // Page-scoped popover state -- the datasets Actionable's own init() fetches
  // once at load and reads throughout _buildActionPopHtmlV2's helper chain
  // (state.scorecard/sourceScorecard/factorScorecard/rsiOverbought/
  // rsiOversold/vlmRvolAvoidThreshold/convictionProvenEdgeMin/sectorEtfMap
  // in web/actionable.js -- factorScorecard wasn't called out in the task
  // spec's own "state dependencies" list but _signalReasons/
  // _buyTradabilityScore/_tradabilityBreakdown all read it, so it's fetched
  // here too). Named uvPopState, not `state` -- this file has no existing
  // module-scope `state` of its own, but nearly every OTHER screen in this
  // app uses that exact name for its own unrelated blob; a distinct name
  // avoids ever colliding if this file grows one later.
  let uvPopState = {
    scorecard: {}, sourceScorecard: {}, factorScorecard: {},
    rsiOverbought: 70, rsiOversold: 30, vlmRvolAvoidThreshold: 1.5,
    convictionProvenEdgeMin: 0.5, sectorEtfMap: {},
  };

  // Fired once from init() (fire-and-forget -- doesn't block the main
  // /api/universe render). Same 4 fetches actionable.js's own init() makes
  // (scorecard/sourceScorecard/settings/factorScorecard) plus the
  // sectorEtfMap build from /api/macro-areas (actionable.js ~1788-1791,
  // copied verbatim). Best-effort per slot: a failed fetch just leaves that
  // slot at its documented default instead of blocking the popover.
  async function _uvLoadPopState() {
    await Promise.all([
      (async () => {
        try {
          const sc = await (await fetch('/api/rules/scorecard?min_fires=0&limit=2000')).json();
          const m = {};
          for (const r of sc) m[r.rule_id] = r;
          uvPopState.scorecard = m;
        } catch (_) { /* keep default {} */ }
      })(),
      (async () => {
        try {
          uvPopState.sourceScorecard = await (await fetch('/api/actionable/source-scorecard')).json();
        } catch (_) { /* keep default {} */ }
      })(),
      (async () => {
        try {
          const settings = await (await fetch('/api/actionable/settings')).json();
          uvPopState.convictionProvenEdgeMin = Number(settings.conviction_proven_edge_min);
          if (!isFinite(uvPopState.convictionProvenEdgeMin)) uvPopState.convictionProvenEdgeMin = 0.5;
          uvPopState.rsiOverbought = Number(settings.rsi_overbought);
          if (!isFinite(uvPopState.rsiOverbought)) uvPopState.rsiOverbought = 70;
          uvPopState.rsiOversold = Number(settings.rsi_oversold);
          if (!isFinite(uvPopState.rsiOversold)) uvPopState.rsiOversold = 30;
          uvPopState.vlmRvolAvoidThreshold = Number(settings.vlm_rvol_avoid_threshold);
          if (!isFinite(uvPopState.vlmRvolAvoidThreshold)) uvPopState.vlmRvolAvoidThreshold = 1.5;
        } catch (_) { /* keep defaults */ }
      })(),
      (async () => {
        try {
          const fsc = await (await fetch('/api/rules/factor-scorecard?min_n=30')).json();
          const m = {};
          for (const r of (fsc || [])) m[r.factor + '|' + r.bucket] = r;
          uvPopState.factorScorecard = m;
        } catch (_) { /* keep default {} */ }
      })(),
      (async () => {
        try {
          const ma = await (await fetch('/api/macro-areas')).json();
          const m = {};
          for (const s of ((ma && ma.sectors && ma.sectors.all) || [])) {
            if (s.sector && s.etf) m[s.sector.trim().toLowerCase()] = s.etf;
          }
          uvPopState.sectorEtfMap = m;
        } catch (_) { /* keep default {} */ }
      })(),
    ]);
  }

  // Mini candlestick SVG -- replicated from web/market_bar.js::_candleSvg
  // (that file isn't loaded here, see universe.html's own comment) so
  // _chgCandleControlsHtml below has something to call. Verbatim copy of
  // that function's own logic/geometry.
  function _uvCandleSvg(o, h, l, c, vh) {
    if (o == null || h == null || l == null || c == null) return '';
    const range = h - l;
    if (range <= 0) return '';
    const VW = 7, VH = vh || 14, PAD = 1;
    const usable = VH - 2 * PAD;
    const toY = p => Math.round(PAD + usable * (1 - (p - l) / range));
    const color = c >= o ? '#1d9e75' : '#d4537e';
    const wickTop = toY(h);
    const wickBot = toY(l);
    const bodyTop = toY(Math.max(o, c));
    const bodyH = Math.max(1, toY(Math.min(o, c)) - bodyTop);
    return `<svg class="rr-candle" width="${VW}" height="${VH}" viewBox="0 0 ${VW} ${VH}" shape-rendering="crispEdges">` +
      `<line x1="3.5" y1="${wickTop}" x2="3.5" y2="${wickBot}" stroke="${color}" stroke-width="1"/>` +
      `<rect x="2" y="${bodyTop}" width="3" height="${bodyH}" fill="${color}"/>` +
      `</svg>`;
  }

  function _pctChgChipHtml(pct) {
    if (pct === null || pct === undefined) return '';
    const n = Number(pct);
    const flat = Math.abs(n) < 0.001;
    const bg = flat ? '#888' : (n > 0 ? '#1d9e75' : '#d4537e');
    const txt = (n > 0 ? '+' : '') + n.toFixed(2) + '%';
    return `<span class="msr-chg" style="background:${bg};flex:0 0 auto;">${esc(txt)}</span>`;
  }
  const _CHG_TINY_STYLE = 'font-size:8px;color:#334155;line-height:1.2;white-space:nowrap;'
    + '-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;';
  function _hiLoParts(high, low, last) {
    if (last == null || !last) return { hi: '', lo: '' };
    const line = val => {
      if (val == null) return '';
      const pct = Math.round((val - last) / last * 100);
      return `<div style="${_CHG_TINY_STYLE}">${pct}%</div>`;
    };
    return { hi: line(high), lo: line(low) };
  }
  function _hiLoRangeHtml(high, low) {
    if (high == null || low == null) return '';
    return `<div style="${_CHG_TINY_STYLE}margin-top:4.01px;">${fmtUsd(low)} - ${fmtUsd(high)}</div>`;
  }
  // Full %CHG widget (candle + hi/lo% + chip + price + range) -- verbatim
  // port of web/actionable.js::_chgCandleControlsHtml, reused here in the
  // popover header's control row.
  function _chgCandleControlsHtml(row, gap) {
    const pctChipHtml = _pctChgChipHtml(row.pct_change);
    const priceStr = row.last_price != null ? fmtUsd(row.last_price) : '';
    const hiLo = _hiLoParts(row.high_price, row.low_price, row.last_price);
    const candleHtml = _uvCandleSvg(row.open_price, row.high_price, row.low_price, row.last_price, 28) || '';
    return `<div class="chg-candle-row" style="display:flex;align-items:center;justify-content:center;gap:${gap != null ? gap : 9}px;">
      <div style="display:flex;flex-direction:column;align-items:center;gap:1px;width:22px;flex:0 0 auto;">
        ${hiLo.hi}
        ${candleHtml}
        ${hiLo.lo}
      </div>
      <div style="display:flex;flex-direction:column;align-items:center;width:60px;flex:0 0 auto;margin-top:0.68px;">
        ${pctChipHtml}
        ${priceStr ? `<div style="font-size:10px;color:#94a3b8;margin-top:2.29px;">${priceStr}</div>` : ''}
        ${_hiLoRangeHtml(row.high_price, row.low_price)}
      </div>
    </div>`;
  }

  // Shared magenta "conflict" bolt icon -- see web/actionable.js's own
  // header comment on _conflictBoltHtml for why this glyph (not the ⚡
  // CHARACTER, a color emoji that ignores CSS `color`).
  function _conflictBoltHtml(title) {
    return `<span style="display:inline-block;vertical-align:middle;margin-left:2px;color:#ec4899;" `
      + `title="${esc(title)}">`
      + `<svg width="11" height="15" viewBox="0 0 24 24" preserveAspectRatio="none" style="display:inline-block;vertical-align:middle;">`
      + `<path fill="currentColor" d="M13 2 3 14h7v8l10-12h-7z"/></svg></span>`;
  }
  // Premature-drop pill -- a flagged REMOVE source entry whose price has
  // since rallied.
  function _dropPctPillHtml(s) {
    if (s.action !== 'REMOVE' || s.pct_since_drop == null) return '';
    const pct = Number(s.pct_since_drop);
    const sign = pct >= 0 ? '+' : '';
    const flagged = s.drop_conflict === true;
    const cls = pct >= 0 ? 'hit-rate-pill-high' : 'hit-rate-pill-neg';
    const title = `${sign}${pct.toFixed(1)}% since dropped` + (flagged ? (s.up_streak_3d ? ' — up 3 days running' : ' — up >5% since') : '');
    const bolt = flagged
      ? _conflictBoltHtml(`Dropped but up ${sign}${pct.toFixed(1)}% since — may have been premature`)
      : '';
    return ` <span class="hit-rate-pill ${cls}" title="${esc(title)}">${sign}${pct.toFixed(1)}%</span>${bolt}`;
  }

  // Short MM/DD date for a source snapshot_date, no year.
  function fmtMD(d) {
    if (!d) return '';
    const m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? (m[2] + '/' + m[3]) : String(d);
  }

  // Action severity rank -- REMOVE strongest, same as the grid's Sources
  // column sort.
  const ACTION_RANK = { REMOVE: 4, REDUCE: 3, INCREASE: 2, ADD: 1, HOLD: 0 };
  // Parsed source_actions array for a row.
  function _sourcesOf(row) {
    let sa = row && row.source_actions;
    if (typeof sa === 'string') { try { sa = JSON.parse(sa); } catch (_) { sa = []; } }
    return Array.isArray(sa) ? sa : [];
  }

  // True when a held position exceeds its category Max (informational
  // overlay, not a gate on the badge -- see actionable.js's own comment).
  function _isOverMaxOverlay(row) {
    if (!row) return false;
    if ((row.consolidated_action || '').toUpperCase() === 'REMOVE') return false;
    const pos = Number(row.current_position_dollar);
    const max = Number(row.target_max_dollar);
    return isFinite(pos) && isFinite(max) && max > 0 && pos > max;
  }
  var _FC_SCALE = {
    SA: -3, REMOVE: -3,
    SS: -2, STM: -2, REDUCE: -2,
    OVER_MAX: -1,
    HOLD: 0, NONE: 0,
    BS: 2, INCREASE: 2, BMN: 2, ADD: 2, BM: 2,
  };
  // Deterministic-gate reason classifier -- walks the same branch order as
  // etl/derive_actionable.py::_compute_final_call, purely to NAME why a
  // 'gate' confidence tier fired (the server doesn't persist the reason
  // text).
  function _gateReasonFor(row) {
    var ca  = (row.consolidated_action || '').toUpperCase();
    var rra = (row.rr_action           || '').toUpperCase();
    if (!ca || ca === 'NONE') return null;
    var atMax       = _isOverMaxOverlay(row);
    var isHeld      = !!row.held_today;
    var srcIsExit   = (ca === 'REMOVE' || ca === 'SA');
    var srcIsReduce = (ca === 'REDUCE' || ca === 'SS' || ca === 'STM');
    var srcIsBuy    = (ca === 'INCREASE' || ca === 'BS' || ca === 'BM' || ca === 'ADD' || ca === 'BMN');
    var srcIsAdd    = (ca === 'ADD' || ca === 'BMN');
    var techIsSell    = (rra === 'SS' || rra === 'STM' || rra === 'SO' || rra === 'REDUCE' || rra === 'SA' || rra === 'REMOVE');
    var techIsBuy     = (rra === 'BS' || rra === 'BM' || rra === 'INCREASE');
    var techIsBuyMin  = (rra === 'BMN' || rra === 'ADD');
    var techIsNeutral = (!techIsSell && !techIsBuy && !techIsBuyMin);
    if (row.stop_breached && (ca === 'ADD' || ca === 'INCREASE')) {
      return 'Held position crossed its stop (' + (row.stop_signal || 'stop') + ') — ADD/INCREASE downgraded to HOLD';
    }
    if (srcIsExit) {
      if (!isHeld) return 'Exit signal but not held — no action feasible';
      return 'Sources: exit signal — Technical not evaluated';
    }
    if (!isHeld && !srcIsBuy) {
      return 'Not held + Sources don’t endorse buying — hold';
    }
    if ((techIsBuy || techIsBuyMin) && atMax) {
      return 'At/over category Max — cannot add more';
    }
    if (techIsNeutral) {
      if (!isHeld && srcIsAdd) return 'Sources says ADD, Technical neutral — establishing position';
      if (!srcIsReduce) return 'No active signal — Sources and Technical both neutral';
    }
    return null;
  }
  // finalCall(row) -> {label, code, side, strength, confidence, feasible,
  // gateReason}. D6: prefers the server-computed final call (final_code
  // etc, always present on a get_actionable() row -- api/routers/
  // universe.py now surfaces it); the branch below is a read-only fallback
  // for a row without it, kept for parity with the source function.
  function finalCall(row) {
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
        gateReason: _confidence === 'gate' ? _gateReasonFor(row) : null,
      };
    }
    var ca  = (row.consolidated_action || '').toUpperCase();
    var rra = (row.rr_action           || '').toUpperCase();
    if (!ca || ca === 'NONE') {
      var dispNone = actionDisplay('HOLD');
      return { label: dispNone.label, code: dispNone.code, side: 'neutral', strength: 0, confidence: 'none', feasible: false };
    }
    var isHeld     = !!row.held_today;
    var atMax      = _isOverMaxOverlay(row);
    var srcIsExit    = (ca === 'REMOVE' || ca === 'SA');
    var srcIsReduce  = (ca === 'REDUCE' || ca === 'SS' || ca === 'STM');
    var srcIsBuy     = (ca === 'INCREASE' || ca === 'BS' || ca === 'BM' || ca === 'ADD' || ca === 'BMN');
    var srcIsAdd     = (ca === 'ADD' || ca === 'BMN');
    var techIsSell   = (rra === 'SS' || rra === 'STM' || rra === 'SO' || rra === 'REDUCE' || rra === 'SA' || rra === 'REMOVE');
    var techIsBuy    = (rra === 'BS' || rra === 'BM' || rra === 'INCREASE');
    var techIsBuyMin = (rra === 'BMN' || rra === 'ADD');
    if (srcIsExit) {
      var exitDisp = actionDisplay('SA');
      if (!isHeld) {
        var holdDisp = actionDisplay('HOLD');
        return { label: holdDisp.label, code: holdDisp.code, side: 'neutral', strength: 0, confidence: 'gate', gateReason: 'Exit signal but not held — no action feasible', feasible: false };
      }
      return { label: exitDisp.label, code: exitDisp.code, side: exitDisp.side, cls: exitDisp.cls, strength: _FC_SCALE['SA'], confidence: 'gate', gateReason: 'Sources: exit signal — Technical not evaluated', feasible: true };
    }
    if (!isHeld && !srcIsBuy) {
      var holdD = actionDisplay('HOLD');
      return { label: holdD.label, code: holdD.code, side: 'neutral', strength: 0, confidence: 'gate', gateReason: 'Not held + Sources don’t endorse buying — hold', feasible: true };
    }
    var fcDisp, fcStrength, confidence, gateReason;
    if (techIsSell) {
      if (!isHeld) { fcDisp = actionDisplay('HOLD'); fcStrength = 0; confidence = 'mixed'; }
      else if (srcIsReduce) { fcDisp = actionDisplay('SS'); fcStrength = _FC_SCALE['SS']; confidence = 'high'; }
      else { fcDisp = actionDisplay('SS'); fcStrength = _FC_SCALE['SS']; confidence = 'mixed'; }
    } else if (techIsBuy || techIsBuyMin) {
      if (srcIsReduce) { fcDisp = actionDisplay('HOLD'); fcStrength = 0; confidence = 'mixed'; }
      else if (atMax) { fcDisp = actionDisplay('HOLD'); fcStrength = 0; confidence = 'gate'; gateReason = 'At/over category Max — cannot add more'; }
      else if (!isHeld && srcIsAdd) { fcDisp = actionDisplay('BMN'); fcStrength = _FC_SCALE['BMN']; confidence = 'high'; }
      else {
        var buyCode = (rra === 'BM' || ca === 'BM' || ca === 'INCREASE' || ca === 'BS') ? 'BM' : 'BS';
        fcDisp = actionDisplay(buyCode); fcStrength = _FC_SCALE[buyCode] || _FC_SCALE['BS']; confidence = (srcIsBuy) ? 'high' : 'mixed';
      }
    } else {
      if (!isHeld && srcIsAdd) { fcDisp = actionDisplay('BMN'); fcStrength = _FC_SCALE['BMN']; confidence = 'gate'; gateReason = 'Sources says ADD, Technical neutral — establishing position'; }
      else if (srcIsReduce) { fcDisp = actionDisplay('HOLD'); fcStrength = 0; confidence = 'mixed'; }
      else { fcDisp = actionDisplay('HOLD'); fcStrength = 0; confidence = 'gate'; gateReason = 'No active signal — Sources and Technical both neutral'; }
    }
    return { label: fcDisp.label, code: fcDisp.code, side: fcDisp.side, cls: fcDisp.cls, strength: fcStrength, confidence: confidence, gateReason: gateReason || null, feasible: true };
  }

  function _rsiBucket(rsi) {
    if (rsi == null) return null;
    const rv = Number(rsi);
    const hi = uvPopState.rsiOverbought != null ? uvPopState.rsiOverbought : 70;
    const lo = uvPopState.rsiOversold   != null ? uvPopState.rsiOversold   : 30;
    if (rv <= lo) return 'Oversold (<=' + lo + ')';
    if (rv >= hi) return 'Overbought (>=' + hi + ')';
    return 'Neutral';
  }
  function _ivBucket(ivPct) {
    if (ivPct == null) return null;
    const v = Number(ivPct);
    if (v >= 90) return 'Extreme (>=90)';
    if (v >= 70) return 'Elevated (70-90)';
    if (v <= 30) return 'Low (<=30)';
    return 'Mid (30-70)';
  }
  function _rvolBucket(rvol, pctChange) {
    if (rvol == null) return null;
    const hi = uvPopState.vlmRvolAvoidThreshold != null ? uvPopState.vlmRvolAvoidThreshold : 1.5;
    const rv = Number(rvol);
    if (rv >= hi && pctChange != null && Number(pctChange) > 0) return 'High RVOL + up day';
    if (rv >= hi && pctChange != null && Number(pctChange) < 0) return 'High RVOL + down day';
    return 'Normal/low RVOL';
  }
  // Resolve a fired rule's buy/sell side via actions.js's canonical map.
  function _ruleSide(id) {
    const sc = (uvPopState.scorecard || {})[id];
    if (!sc || !sc.direction) return 'neutral';
    const code = sc.direction === 'BUY' ? 'BM' : sc.direction === 'SELL' ? 'SA' : '';
    return actionDisplay(code).side;
  }

  function _factorWinRateDelta(factor, bucket) {
    if (!bucket) return null;
    const r = (uvPopState.factorScorecard || {})[factor + '|' + bucket];
    const base = (uvPopState.factorScorecard || {})['Baseline|All stocks'];
    if (!r || r.win_rate == null || !base || base.win_rate == null) return null;
    return (Number(r.win_rate) - Number(base.win_rate)) * 100;
  }
  function _factorWinRateDeltaGated(factor, bucket, minSymbols) {
    if (!bucket) return null;
    const r = (uvPopState.factorScorecard || {})[factor + '|' + bucket];
    const base = (uvPopState.factorScorecard || {})['Baseline|All stocks'];
    if (!r || r.win_rate == null || !base || base.win_rate == null) return null;
    const nSymbols = r.n_symbols != null ? Number(r.n_symbols) : 0;
    if (nSymbols < (minSymbols != null ? minSymbols : 5)) return null;
    return { delta: (Number(r.win_rate) - Number(base.win_rate)) * 100, n: r.n, nSymbols };
  }

  // Raw (unclamped) LRR-relative Risk Range position, % -- distinct from
  // this file's own rawRrPos(lrr,trr,last) helper (used by the tile/
  // tooltip rendering above): same formula, row-object signature to match
  // the ported tradability/signal-reasons code that calls it this way.
  function _rawRrPos(row) {
    if (row.lrr == null || row.trr == null || row.last_price == null) return null;
    const lrr = Number(row.lrr), trr = Number(row.trr), last = Number(row.last_price);
    if (trr === lrr) return null;
    return (last - lrr) / (trr - lrr) * 100;
  }

  // Two-way signal reasons for the Final Call side: {warn:[...], buy:[...]}.
  function _signalReasons(row, side) {
    const isSell = side === 'sell';
    const warn = [];
    const buy = [];
    const _rrPosForWarn = !isSell ? _rawRrPos(row) : null;
    if (_rrPosForWarn != null && _rrPosForWarn >= 85) {
      warn.push('Caution: price at TRR');
    }
    if (!isSell && row.warn_added_this_leg) {
      warn.push('Already bought this symbol since price last closed at/above TRR — repeat buy signal this leg');
    }
    if (row.rvol != null && row.pct_change != null) {
      const rvolHi = uvPopState.vlmRvolAvoidThreshold != null ? uvPopState.vlmRvolAvoidThreshold : 1.5;
      if (Number(row.rvol) >= rvolHi && Number(row.pct_change) > 0) {
        warn.push('VLM: high RVOL (' + Number(row.rvol).toFixed(1) + 'x) on an up day — possible buying climax');
      }
    }
    if (row.rsi != null) {
      const rv = Number(row.rsi);
      const hi = uvPopState.rsiOverbought != null ? uvPopState.rsiOverbought : 70;
      const lo = uvPopState.rsiOversold   != null ? uvPopState.rsiOversold   : 30;
      if (rv >= hi) warn.push('RSI overbought (' + rv + ')');
      else if (rv <= lo) buy.push('RSI oversold (' + rv + ')');
    }
    if (row.winning_source) {
      const srcCode = row.winning_source.toString().toUpperCase();
      const g = _factorWinRateDeltaGated('Winning source', srcCode);
      if (g && g.delta < -3) {
        warn.push('Winning source ' + srcCode + ' historically underperforms (' + g.delta.toFixed(1) + 'pp vs baseline, ' + g.nSymbols + ' symbols)');
      }
    }
    if (row.sector && row.sector !== 'N/A') {
      const g = _factorWinRateDeltaGated('Sector', row.sector);
      if (g && g.delta < -3) {
        warn.push('Sector ' + row.sector + ' historically underperforms (' + g.delta.toFixed(1) + 'pp vs baseline, ' + g.nSymbols + ' symbols)');
      }
    }
    let fires = row.rules_engine_fires;
    if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
    if (Array.isArray(fires)) {
      const sc = uvPopState.scorecard || {};
      for (const f of fires) {
        const id = String(f.rule_id || f.id || f);
        const s = sc[id];
        if (!s || s.edge_20d == null) continue;
        const e = Number(s.edge_20d);
        const conf = s.confidence || 'unproven';
        const ruleSide = _ruleSide(id);
        if (ruleSide === 'buy') {
          if (e <= 0 || conf === 'unproven') {
            warn.push('Rule ' + id + ' fired buy with ' + (conf === 'unproven' ? 'unproven' : 'negative') + ' edge');
          } else if (conf === 'proven') {
            buy.push('Rule ' + id + ' fired buy with proven positive edge (+' + e.toFixed(1) + '%)');
          }
        } else if (ruleSide === 'sell' && e > 0) {
          warn.push('Sell rule ' + id + ' historically correct (+' + e.toFixed(1) + '%)');
        }
      }
    }
    return isSell ? { warn: buy, buy: warn } : { warn, buy };
  }

  const _PVV_BUY_SIDE = ['BUY_LRR', 'BUY_DIP', 'BUY_WATCH'];
  const _PVV_SELL_SIDE = ['SELL', 'SELL_WATCH', 'REDUCE', 'TRIM', 'AVOID'];
  const _PVV_CAUTION = ['BUY_WATCH', 'SELL_WATCH'];
  const _PVV_LABEL = {
    BUY_LRR: 'BUY@LRR', BUY_WATCH: 'BUYWATCH', SELL_WATCH: 'SELLWATCH',
  };
  const _PVV_DECISION_INFO = {
    BUY_LRR:    { condition: 'outlook=Bullish, today=STRONG_BULL/WEAK_BULL, price at LRR',
                  meaning: 'Price up today, confirmed by volume/volatility, and sitting right at the LRR support line — a genuine buy setup.' },
    BUY_DIP:    { condition: 'outlook=Bullish, today=DRIFT/BEAR_LEAN',
                  meaning: "Bullish outlook intact; today's soft pullback is a dip to buy, not a reversal. Your most reliable signal." },
    BUY_WATCH:  { condition: 'outlook=Bullish, today=MILD_BEAR',
                  meaning: "Bullish outlook, but today's down move came with rising volume — a softer, less-confirmed dip. Worth watching for an entry, not a confirmed buy yet." },
    TRIM:       { condition: 'outlook=Bullish & today=OVEREXT_BULL, or outlook=Bearish & today=STRONG_BULL/WEAK_BULL/OVEREXT_BULL/BEAR_DIV',
                  meaning: 'Either an overbought pop in a bullish name, or a rip in a bearish one ("sell the rip") — take some off either way.' },
    REDUCE:     { condition: 'outlook=Bearish, today=MILD_BEAR/BEAR_LEAN',
                  meaning: 'Bearish outlook with the tape confirming the down move — lighten up.' },
    SELL:       { condition: 'outlook=Bearish, today=STRONG_BEAR',
                  meaning: "Bearish outlook and today's heavy-volume selloff both confirm — exit." },
    SELL_WATCH: { condition: 'outlook=Bullish, today=STRONG_BEAR',
                  meaning: "Bullish outlook, but today is a heavy-volume selloff — a serious warning sign. Watch closely; you may need to get rid of the stock despite the bullish thesis." },
    AVOID:      { condition: 'outlook=Bearish, today=NEUTRAL/NA/DRIFT',
                  meaning: "Bearish outlook, no confirming setup yet — don't initiate." },
    NO_ACTION:  { condition: 'outlook=Bullish & today=BEAR_DIV/NEUTRAL/NA, or today=STRONG_BULL/WEAK_BULL but not at LRR',
                  meaning: 'No confirmed setup today — sit tight.' },
    WATCH:      { condition: 'outlook=Neutral/none (any today)',
                  meaning: 'No outlook conviction either way — nothing to act on.' },
  };

  const _ENTRY_RIPE_TECH = ['BS', 'BM', 'BMN'];
  const _MACRO_BUY = new Set(['BM', 'BS']), _MACRO_SELL = new Set(['STM', 'SA']);
  const _SRC_BUY   = new Set(['ADD', 'INCREASE']), _SRC_SELL = new Set(['REDUCE', 'REMOVE']);
  const _TECH_BUY  = new Set(['BM', 'BS', 'BMN', 'BR']), _TECH_SELL = new Set(['SA', 'STM', 'SS', 'SO']);
  // TASK_122 sub-tier: 2 = full 3-way buy agreement, 1 = partial (2/3, none
  // opposing), 0 = weak/solo.
  function _buyAgreementSubTier(row) {
    const m = (row.macro_value || '').toUpperCase();
    const s = (row.consolidated_action || '').toUpperCase();
    const t = (row.rr_action || '').toUpperCase();
    const techBuy   = _ENTRY_RIPE_TECH.indexOf(t) !== -1;
    const srcBuy    = _SRC_BUY.has(s);
    const macroBuy  = _MACRO_BUY.has(m);
    const anySell   = _TECH_SELL.has(t) || _SRC_SELL.has(s) || _MACRO_SELL.has(m);
    const buyVotes  = (techBuy ? 1 : 0) + (srcBuy ? 1 : 0) + (macroBuy ? 1 : 0);
    if (buyVotes === 3) return 2;
    if (buyVotes === 2 && !anySell) return 1;
    return 0;
  }
  // Score thresholds mirror the user's own IV-spike/normalize ThinkOrSwim
  // study exactly -- see actionable.js's own header comment on this
  // function for the full backtest rationale.
  function _ivRatioScore(ratio) {
    if (ratio == null) return 0;
    const r = Number(ratio);
    if (r > 1.15) return -3;
    if (r < 1) return 3;
    return 0;
  }
  function _lrrProximityScore(row) {
    const rawPos = _rawRrPos(row);
    if (rawPos == null) return 0;
    const turningUp = row.pct_change != null && Number(row.pct_change) >= 0;
    if (rawPos < 0) {
      if (!turningUp) return -1;
      return Math.max(0, 0.3 - Math.abs(rawPos) / 100);
    }
    const base = Math.max(0, 1 - rawPos / 40);
    return base * (turningUp ? 1 : 0.7);
  }
  function _sourceTrackRecordScore(row) {
    const src = (row.winning_source || '').toString().toUpperCase();
    const sc = ((uvPopState.sourceScorecard || {})[src] || {}).buy;
    const base = (uvPopState.factorScorecard || {})['Baseline|All stocks'];
    if (!sc || sc.win_rate_20d == null || sc.n < 5 || !base || base.win_rate == null) return 0;
    const delta = (Number(sc.win_rate_20d) - Number(base.win_rate)) * 100;
    return Math.max(-3, Math.min(6, delta));
  }
  // Buy Tradability Score -- see actionable.js's own extensive header
  // comment on _buyTradabilityScore for the full backtest rationale behind
  // every weight below (LRR proximity dominant, RSI/IV/RVOL/source
  // capped-sum secondary terms, agreement its own dedicated weight). Stays
  // buy-calibrated under the hood regardless of the row's own side, same as
  // the source.
  function _buyTradabilityScore(row) {
    const tech = (row.rr_action || '').toUpperCase();
    const techPts = _ENTRY_RIPE_TECH.indexOf(tech) !== -1 ? 1 : 0;
    const lrrPts = _lrrProximityScore(row);
    const rsiDelta  = _factorWinRateDelta('RSI', _rsiBucket(row.rsi));
    const rvolDelta = _factorWinRateDelta('RVOL + direction', _rvolBucket(row.rvol, row.pct_change));
    const clamp = v => v == null ? 0 : Math.max(-3, Math.min(6, v));
    const factorPts = clamp(rsiDelta) + _ivRatioScore(row.iv_ratio) + clamp(rvolDelta)
      + _sourceTrackRecordScore(row);
    const secondaryRaw = techPts * 2 + factorPts;
    const secondaryPts = Math.max(-6, Math.min(8, secondaryRaw));
    const agreementPts = _buyAgreementSubTier(row) * 3;
    return lrrPts * 10 + secondaryPts + agreementPts;
  }
  function _tradabilityDeltaColor(d) {
    if (d == null) return '#94a3b8';
    if (d > 1.5) return '#16a34a';
    if (d < -1.5) return '#dc2626';
    return '#94a3b8';
  }
  // Structured breakdown feeding the Tradability box (_actpopTradabilityHtml).
  function _tradabilityBreakdown(row) {
    const items = [];
    const fmtDelta = d => (d >= 0 ? '+' : '') + d.toFixed(1) + 'pp win rate vs baseline';
    const rawPos = _rawRrPos(row);
    const turningUpForLrr = row.pct_change != null && Number(row.pct_change) >= 0;
    items.push({
      label: 'Risk Range',
      detail: rawPos == null ? 'no LRR/TRR data'
        : rawPos < 0
          ? Math.abs(Math.round(rawPos)) + '% BELOW LRR' + (turningUpForLrr ? ' — bouncing, but still under the line' : ' — falling below LRR, be cautious')
          : Math.round(rawPos) + '% up from LRR' + (rawPos <= 15 ? ' — near LRR, the strongest proven buy signal (52-BS-BRR)' : rawPos <= 40 ? ' — reasonably close to LRR' : ' — well above LRR'),
      color: rawPos == null ? '#94a3b8'
        : rawPos < 0 ? (turningUpForLrr ? '#d97706' : '#dc2626')
        : rawPos <= 15 ? '#16a34a' : rawPos <= 40 ? '#d97706' : '#94a3b8',
    });
    const tech = (row.rr_action || '').toUpperCase();
    const techRipe = _ENTRY_RIPE_TECH.indexOf(tech) !== -1;
    items.push({
      label: 'Technical',
      detail: tech ? (tech + (techRipe ? ' — entry-ripe' : '')) : 'no Technical (QS) code',
      color: techRipe ? '#16a34a' : '#94a3b8',
    });
    const rsiB = _rsiBucket(row.rsi);
    const rsiD = _factorWinRateDelta('RSI', rsiB);
    items.push({
      label: 'RSI',
      detail: (row.rsi != null ? Number(row.rsi).toFixed(1) + ' — ' : '') + (rsiB || 'no data') + (rsiD != null ? ' (' + fmtDelta(rsiD) + ')' : ''),
      color: _tradabilityDeltaColor(rsiD),
    });
    const ivRatio = row.iv_ratio != null ? Number(row.iv_ratio) : null;
    items.push({
      label: 'IV',
      detail: ivRatio == null ? 'no data'
        : ivRatio.toFixed(2) + 'x its own 63-day average'
          + (ivRatio > 1.15 ? ' — spiked, above the 1.15x red line, be careful'
             : ivRatio < 1 ? ' — below its own normal range'
             : ' — elevated but not yet spiked'),
      color: ivRatio == null ? '#94a3b8' : ivRatio > 1.15 ? '#dc2626' : ivRatio < 1 ? '#16a34a' : '#d97706',
    });
    const rvolB = _rvolBucket(row.rvol, row.pct_change);
    const rvolD = _factorWinRateDelta('RVOL + direction', rvolB);
    items.push({
      label: 'Volume',
      detail: (rvolB || 'no data') + (rvolD != null ? ' (' + fmtDelta(rvolD) + ')' : ''),
      color: _tradabilityDeltaColor(rvolD),
    });
    const src = (row.winning_source || '').toString().toUpperCase();
    const srcSide = finalCall(row).side;
    const srcSc = ((uvPopState.sourceScorecard || {})[src] || {})[srcSide];
    const srcHasData = !!src && !!srcSc && srcSc.win_rate_20d != null && srcSc.n >= 5;
    const srcD = _sourceTrackRecordScore(row);
    items.push({
      label: 'Source',
      detail: !src ? 'no winning source'
        : !srcHasData ? src + (srcSide === 'buy' || srcSide === 'sell' ? ' — not enough ' + srcSide + ' history yet' : ' — no directional read')
        : src + ': ' + Math.round(srcSc.win_rate_20d * 100) + '% ' + srcSide + ' win rate (n=' + srcSc.n + ') (' + fmtDelta(srcD) + ')',
      color: _tradabilityDeltaColor(srcHasData ? srcD : null),
    });
    const subtier = _buyAgreementSubTier(row);
    items.push({
      label: 'Agreement',
      detail: subtier === 2 ? '3-way — Technical + Sources + MACRO all agree'
            : subtier === 1 ? 'Partial — 2 of 3 agree, none opposing'
            : 'Weak/solo — not independently corroborated',
      color: subtier === 2 ? '#16a34a' : subtier === 1 ? '#d97706' : '#94a3b8',
    });
    return items;
  }
  // Shared target/bullseye icon -- inline SVG (fill/stroke=currentColor),
  // not the 🎯 CHARACTER (a color emoji that ignores CSS `color`).
  function _tradabilityIconSvg(size) {
    const s = size || 12;
    return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="display:inline-block;vertical-align:middle;">`
      + `<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2.5"/>`
      + `<circle cx="12" cy="12" r="5.5" fill="none" stroke="currentColor" stroke-width="2.5"/>`
      + `<circle cx="12" cy="12" r="1.8" fill="currentColor"/></svg>`;
  }
  const _TRADABILITY_BADGE_MIN = 12;

  // "$7,356" -> "$7k" (>=1000); untouched below 1000.
  function _actpopFmtAmt(v) {
    const n = Number(v);
    if (!isFinite(n)) return '';
    const abs = Math.abs(n);
    if (abs >= 1000) return (n < 0 ? '-' : '') + '$' + Math.round(abs / 1000) + 'k';
    return fmtUsd(n);
  }

  function _monthlyScoresVisible(r) {
    const raw = r.monthly_scores_json;
    const arr = Array.isArray(raw) ? raw
      : (typeof raw === 'string' ? (() => { try { return JSON.parse(raw); } catch (_e) { return null; } })() : null);
    if (!arr) return null;
    const curIdx = arr.findIndex(s => s.is_current);
    return curIdx >= 0 ? arr.slice(curIdx) : arr;
  }
  // Two bar rows: forward monthly quad-regime sparkline, and the
  // Sector/Asset class/Style stance bars.
  function _actpopMacroBarsHtml(r) {
    const sparks = _monthlyScoresVisible(r);
    let sparkRow = '';
    if (sparks && sparks.length >= 2) {
      const maxAbs = Math.max(...sparks.map(s => Math.abs(s.score || 0)), 0.001);
      const bars = sparks.map(s => {
        const sc = s.score || 0;
        const bh = Math.max(3, Math.round(Math.abs(sc) / maxAbs * 16));
        const cls = sc > 0 ? 'buy' : sc < 0 ? 'sell' : 'neutral';
        const ti = `${s.label || ''} (${s.quad || ''}) ${sc >= 0 ? '+' : ''}${sc.toFixed(2)}${s.is_current ? ' — current month' : ''}`;
        return `<span class="actpop-mbar ${cls}" style="height:${bh}px;" title="${esc(ti)}"></span>`;
      }).join('');
      sparkRow = `<div class="actpop-mrow spark" title="Forward monthly quad-regime score (live sparkline)">${bars}</div>`;
    }
    const memberItems = [];
    if (r.sector_stance != null) memberItems.push({ label: `Sector: ${r.sector || '?'}`, v: Number(r.sector_stance) });
    if (r.asset_class_stance != null) memberItems.push({ label: `Asset class: ${r.real_asset_class || '?'}`, v: Number(r.asset_class_stance) });
    let styles = r.style_stances;
    if (typeof styles === 'string') { try { styles = JSON.parse(styles); } catch (_) { styles = []; } }
    if (Array.isArray(styles)) {
      for (const s of styles) if (s && s.stance != null) memberItems.push({ label: `Style: ${s.label}`, v: Number(s.stance) });
    }
    let memberRow = '';
    if (memberItems.length) {
      const maxAbs = Math.max(...memberItems.map(b => Math.abs(b.v)), 0.001);
      const bars = memberItems.map(b => {
        const bh = Math.max(3, Math.round(Math.abs(b.v) / maxAbs * 14));
        const cls = b.v > 0 ? 'buy' : b.v < 0 ? 'sell' : 'neutral';
        const ti = `${b.label}: ${b.v >= 0 ? '+' : ''}${b.v.toFixed(2)} (live quad regime)`;
        return `<span class="actpop-mbar ${cls}" style="height:${bh}px;" title="${esc(ti)}"></span>`;
      }).join('');
      memberRow = `<div class="actpop-mrow member" title="Sector / Asset class / Style — live quad-regime stance">${bars}</div>`;
    }
    if (!sparkRow && !memberRow) return '';
    return `<div class="actpop-mgroup-wrap"><div class="actpop-mgroup">${sparkRow}${memberRow}</div></div>`;
  }

  const _VLM_ACTION_LABEL = { Accumulate: 'Heavy', Watch: 'Mixed', Avoid: 'Thin' };
  function _vlmActionLabel(va) {
    return _VLM_ACTION_LABEL[va] || va;
  }
  function _actpopVlmPillHtml(row) {
    const va = row.vlm_action;
    const cls = !va ? 'disabled' : va === 'Accumulate' ? 'buy' : va === 'Avoid' ? 'sell' : '';
    const txt = va ? _vlmActionLabel(va) : '—';
    const detail = row.vlm_desc ? `<span style="font-size:8px;color:#94a3b8;margin-left:3px;">${esc(row.vlm_desc)}</span>` : '';
    return `<span class="actpop-lv"><span class="actpop-lbl">VLM</span><span class="actpop-val ${cls}">${esc(txt)}</span>${detail}</span>`;
  }
  function _actpopVlmLineHtml(row) {
    const rvolTxt = row.rvol != null ? `<span style="font-size:9px;color:#94a3b8;">RVOL ${Number(row.rvol).toFixed(2)}&times; (d/10d)</span>` : '';
    return `<div class="actpop-vlm-line">${_actpopVlmPillHtml(row)}${rvolTxt}</div>`;
  }

  function _actpopMacroStackHtml(row) {
    const mv = row.macro_value;
    const mcls = (mv === 'BM' || mv === 'BS') ? 'buy' : (mv === 'SA' || mv === 'STM') ? 'sell' : '';
    const conflictMark = row.macro_conflict === true
      ? _conflictBoltHtml('MacroNet disagrees with technical direction (price vs 50-day average)') : '';
    return `<span class="actpop-macro-stack">
      <span class="actpop-lv"><span class="actpop-lbl">Macro</span><span class="actpop-val ${mcls}">${esc(mv || 'HOLD')}</span>${conflictMark}</span>
      ${_actpopMacroBarsHtml(row)}
    </span>`;
  }

  function _actpopPvvActionHtml(row) {
    const d = row.pvv_decision;
    const hasReal = !!d && d !== 'NO_ACTION' && d !== 'WATCH';
    const pvvSide = hasReal ? (_PVV_BUY_SIDE.includes(d) ? 'buy' : _PVV_SELL_SIDE.includes(d) ? 'sell' : null) : null;
    const caution = hasReal && _PVV_CAUTION.includes(d);
    const cls = !hasReal ? 'disabled' : caution ? '' : (pvvSide === 'buy' ? 'buy' : pvvSide === 'sell' ? 'sell' : '');
    const txt = hasReal ? (_PVV_LABEL[d] || d) : '—';
    return `<span class="actpop-lv"><span class="actpop-lbl">PVV</span><span class="actpop-val ${cls}">${esc(txt)}</span></span>`;
  }

  function _actpopTradIconHtml(row) {
    const score = _buyTradabilityScore(row);
    const meetsMin = score >= _TRADABILITY_BADGE_MIN;
    const scoreColor = score >= 16 ? 'var(--act-buy-strong)' : meetsMin ? '#d97706' : '#94a3b8';
    const icon = `<span class="actpop-trad-icon${meetsMin ? '' : ' disabled'}" title="Tradability read below">`
      + _tradabilityIconSvg(12) + `</span>`;
    const scoreLine = `<div class="actpop-trad-score" style="color:${scoreColor};" title="Tradability score">${score.toFixed(1)}</div>`;
    return `<span class="actpop-trad-col">${icon}${scoreLine}</span>`;
  }

  function _actpopRrBarHtml(row) {
    const rawPos = _rawRrPos(row);
    if (rawPos == null) return '';
    const lrr = row.lrr != null ? Number(row.lrr) : null;
    const trr = row.trr != null ? Number(row.trr) : null;
    const clamped = Math.max(0, Math.min(100, rawPos));
    const tagBg = rawPos > 100 ? 'var(--act-sell-strong-bg)' : rawPos < 0 ? 'var(--act-buy-bg)' : '#f1f5f9';
    const tagColor = rawPos > 100 ? 'var(--act-sell-strong)' : rawPos < 0 ? 'var(--act-buy-strong)' : '#475569';
    return `<div class="actpop-rr">
      <div class="actpop-rr-track">
        <div class="actpop-rr-tag" style="left:${clamped}%;background:${tagBg};color:${tagColor};">${Math.round(rawPos)}%</div>
        <div class="actpop-rr-fill" style="width:${clamped}%;"></div>
        <div class="actpop-rr-tick" style="left:${clamped}%;"></div>
      </div>
      <div class="actpop-rr-labels"><span>LRR ${lrr != null ? lrr.toFixed(2) : '&mdash;'}</span>`
      + `<span class="num">${row.last_price != null ? fmtUsd(row.last_price) : ''}</span>`
      + `<span>TRR ${trr != null ? trr.toFixed(2) : '&mdash;'}</span></div>
    </div>`;
  }

  function _actpopCalcPillHtml(row) {
    const p = row.bull_prob;
    const has = p != null;
    const pct = has ? Math.round(Number(p) * 100) : null;
    const color = !has ? '' : pct >= 65 ? 'var(--act-buy-strong)' : pct >= 50 ? '#d97706' : 'var(--act-sell-strong)';
    const txt = has ? pct + '%' : '—';
    return `<span class="actpop-lv"><span class="actpop-lbl">CAL</span><span class="actpop-val${has ? '' : ' disabled'}"${has ? ` style="color:${color};"` : ''}>${esc(txt)}</span></span>`;
  }

  function _sectorEtfFor(row) {
    const raw = (row.sector || '').trim().toLowerCase();
    if (!raw) return null;
    const key = raw === 'healthcare' ? 'health care' : raw;
    return (uvPopState.sectorEtfMap || {})[key] || null;
  }
  function _actpopSectorEtfHtml(row) {
    const etf = _sectorEtfFor(row);
    if (!etf) return '';
    const pos = etf.rr_pos != null ? Math.max(0, Math.min(100, Number(etf.rr_pos) * 100)) : null;
    const pct = etf.pct_change != null ? Number(etf.pct_change) : null;
    const pctTxt = pct != null ? `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` : '&mdash;';
    const pctColor = pct == null ? '#94a3b8' : pct >= 0 ? 'var(--act-buy-strong)' : 'var(--act-sell-strong)';
    const outlookTxt = etf.outlook || '&mdash;';
    const outlookCss = etf.outlook && window.outlookColor ? window.outlookColor(etf.outlook) : '#94a3b8';
    const bar = pos != null
      ? `<div class="actpop-rr-track" style="width:45px;display:inline-block;vertical-align:middle;flex-shrink:0;">
           <div class="actpop-rr-fill" style="width:${pos}%;"></div>
           <div class="actpop-rr-tick" style="left:${pos}%;"></div>
         </div><span style="font-size:9px;color:#94a3b8;margin-left:3px;">${Math.round(pos)}%</span>`
      : '';
    return `<div class="actpop-sector-etf" style="font-size:9px;color:#64748b;`
      + `display:flex;align-items:center;width:100%;">`
      + `<span style="display:flex;align-items:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;">`
      + `<span class="actpop-lbl" style="margin-right:4px;flex-shrink:0;">Sector ETF</span>`
      + `<b style="flex-shrink:0;">${esc(etf.symbol || '')}</b>`
      + `<span style="margin-left:6px;flex-shrink:0;">Outlook <b style="color:${outlookCss};">${esc(outlookTxt)}</b></span>`
      + `<span style="margin-left:6px;flex-shrink:0;color:${pctColor};">${pctTxt}</span>`
      + `</span>`
      + `<span style="margin-left:auto;flex-shrink:0;display:flex;align-items:center;padding-left:4px;">${bar}</span>`
      + `</div>`;
  }

  // Signed stop-proximity SD -- HV-daily-move-normalized distance from a
  // Trade/Trend line, negative when price is below it.
  function _lineProximitySd(row, lineVal) {
    const px = row.last_price != null ? Number(row.last_price) : null;
    const hv = row.hv != null ? Number(row.hv) : null;
    if (px == null || hv == null || hv <= 0 || lineVal == null) return null;
    const dailyMove = px * hv / Math.sqrt(252);
    return dailyMove > 0 ? (px - lineVal) / dailyMove : null;
  }
  function _tdtnSdBadge(sd) {
    if (sd == null) return '';
    const below = sd < 0;
    const color = below ? '#b91c1c' : sd < 0.5 ? '#b91c1c' : sd < 1.5 ? '#d97706' : 'var(--act-buy-strong)';
    const note = below ? ' — below this line' : sd < 0.5 ? ' — close' : sd < 1.5 ? ' — getting close' : ' — clear';
    return `<span class="actpop-tdtn-sd" style="color:${color};border-color:${color};" `
      + `title="${sd.toFixed(1)}σ from this line${note}">${sd.toFixed(1)}&sigma;</span>`;
  }
  // Trade/Trend header boxes -- whichever line is currently higher sits on
  // top; order decided here (data-dependent per row), not CSS.
  function _actpopTdTnHtml(row) {
    const td = row.trade_line_value != null ? Number(row.trade_line_value) : null;
    const tn = row.trend_line_value != null ? Number(row.trend_line_value) : null;
    if (td == null && tn == null) return '';
    const lp = row.last_price != null ? Number(row.last_price) : null;
    const lineCls = v => (lp == null || v == null) ? '' : lp >= v ? ' buy' : ' sell';
    const tdRow = td != null
      ? `<span class="actpop-tdtn-row"><span class="actpop-tdtn-box${lineCls(td)}">Td ${td.toFixed(1)}</span>`
        + `${_tdtnSdBadge(_lineProximitySd(row, td))}</span>`
      : '';
    const tnRow = tn != null
      ? `<span class="actpop-tdtn-row"><span class="actpop-tdtn-box${lineCls(tn)}">Tn ${tn.toFixed(1)}</span>`
        + `${_tdtnSdBadge(_lineProximitySd(row, tn))}</span>`
      : '';
    const top = (tn != null && (td == null || tn > td)) ? tnRow : tdRow;
    const bottom = top === tdRow ? tnRow : tdRow;
    return `<div class="actpop-tdtn">${top}${bottom}</div>`;
  }

  // Fired composite rules, partitioned by whether their proven direction
  // agrees with the row's own side.
  function _actpopRulePillsHtml(row, side) {
    let fires = row.rules_engine_fires;
    if (typeof fires === 'string') { try { fires = JSON.parse(fires); } catch (_) { fires = []; } }
    if (!Array.isArray(fires) || !fires.length) return { support: '', oppose: '', supportCount: 0, opposeCount: 0 };
    const sc = uvPopState.scorecard || {};
    const supportPills = [], opposePills = [];
    for (const f of fires) {
      const id = String(f.rule_id || f.id || f);
      const s = sc[id];
      const ruleSide = _ruleSide(id);
      if (ruleSide !== 'buy' && ruleSide !== 'sell') continue;
      const bucket = ruleSide === side ? supportPills : opposePills;
      const cls = ruleSide === 'buy' ? 'buy' : 'sell';
      const conf = (s && s.confidence) || 'unproven';
      const e = (s && s.edge_20d != null) ? Number(s.edge_20d) : null;
      if (conf === 'unproven' || e == null) {
        const n = s && (s.n_fires != null ? s.n_fires : s.fires);
        bucket.push(`<span class="rule-edge-badge act-badge-sm rule-${cls} rule-weak" style="opacity:.55;" `
          + `title="Unproven${n != null ? ' (n=' + n + ')' : ''} — too few fires or CI straddles 0">${esc(id)}</span>`);
      } else {
        const strong = conf === 'proven' ? 'rule-strong' : 'rule-weak';
        bucket.push(`<span class="rule-edge-badge act-badge-sm rule-${cls} ${strong}" title="${conf}: 20d edge, diagnostic">`
          + `${esc(id)} ${e >= 0 ? '+' : ''}${e.toFixed(1)}%</span>`);
      }
    }
    return {
      support: supportPills.length ? `<div class="actpop-rule-pills">${supportPills.join('')}</div>` : '',
      oppose: opposePills.length ? `<div class="actpop-rule-pills">${opposePills.join('')}</div>` : '',
      supportCount: supportPills.length,
      opposeCount: opposePills.length,
    };
  }

  // Opposing/Supporting tug-of-war + conviction tally.
  function _actpopTugHtml(row, side) {
    if (side !== 'buy' && side !== 'sell') return { conviction: '', html: '' };
    const sig = _signalReasons(row, side);
    const isRuleText = s => /^Rule \S+ fired|^Sell rule \S+/.test(s);
    const supportSignals = sig.buy.filter(s => !isRuleText(s));
    let opposeSignals = sig.warn.filter(s => !isRuleText(s));
    if (side === 'sell') {
      const dropOpp = _sourcesOf(row)
        .filter(s => s.action === 'REMOVE' && s.drop_conflict === true)
        .map(s => {
          const src = s.source || s.source_code || '?';
          const pct = Number(s.pct_since_drop);
          const sign = pct >= 0 ? '+' : '';
          return `${src} dropped it but up ${sign}${pct.toFixed(1)}% since — may have been premature`;
        });
      opposeSignals = opposeSignals.concat(dropOpp);
    }
    const rulePills = _actpopRulePillsHtml(row, side);
    const oppItems = opposeSignals.map(s => `<div class="actpop-tug-item">${esc(s)}</div>`).join('');
    const supItems = supportSignals.map(s => `<div class="actpop-tug-item">${esc(s)}</div>`).join('');
    if (!oppItems && !supItems && !rulePills.oppose && !rulePills.support) return { conviction: '', html: '' };
    const oppBody = (oppItems || rulePills.oppose)
      ? `${oppItems}${rulePills.oppose}`
      : `<div class="actpop-tug-item" style="color:#94a3b8;">none</div>`;
    const supBody = (supItems || rulePills.support)
      ? `${supItems}${rulePills.support}`
      : `<div class="actpop-tug-item" style="color:#94a3b8;">none</div>`;
    const supportN = supportSignals.length + rulePills.supportCount;
    const opposeN = opposeSignals.length + rulePills.opposeCount;
    const net = supportN - opposeN;
    const netColor = net > 0 ? 'var(--act-buy-strong)' : net < 0 ? 'var(--act-sell-strong)' : '#94a3b8';
    const conviction = (supportN + opposeN) > 0
      ? `<span class="actpop-tug-conviction">`
        + `<b style="font-size:13px;color:${netColor};">${net > 0 ? '+' : ''}${net}</b>`
        + `<span class="actpop-tug-conviction-nn">`
        + `<span class="actpop-tug-conviction-n" style="color:var(--act-buy-strong);">${supportN} Supp</span>`
        + `<span class="actpop-tug-conviction-n" style="color:var(--act-sell-strong);">${opposeN} Opp</span>`
        + `</span></span>`
      : '';
    const html = `<div class="actpop-tug">
      <div class="actpop-tug-col oppose"><div class="actpop-tug-h">Opposing</div>${oppBody}</div>
      <div class="actpop-tug-col support"><div class="actpop-tug-h">Supporting</div>${supBody}</div>
    </div>`;
    return { conviction, html };
  }

  // Bottom "no read" line -- factors that don't clear a real lean threshold.
  function _actpopNeutralLine(row) {
    const bits = [];
    const mv = row.macro_value;
    if (!mv || mv === 'HOLD') {
      const confPct = row.macro_conf != null ? Math.round(row.macro_conf * 100) + '%' : null;
      bits.push('MACRO' + (confPct ? ` (Hold, ${confPct})` : ''));
    }
    if (row.rsi != null) {
      const rv = Number(row.rsi);
      const hi = uvPopState.rsiOverbought != null ? uvPopState.rsiOverbought : 70;
      const lo = uvPopState.rsiOversold != null ? uvPopState.rsiOversold : 30;
      if (rv > lo && rv < hi) bits.push('RSI ' + Math.round(rv));
    }
    if (row.iv_percentile != null) {
      const bucket = _ivBucket(row.iv_percentile);
      if (bucket === 'Mid (30-70)' || bucket === 'Low (<=30)') bits.push('IV ' + Math.round(row.iv_percentile) + 'pt');
    }
    const pvvD = row.pvv_decision;
    if (!pvvD || pvvD === 'NO_ACTION' || pvvD === 'WATCH') bits.push('PVV');
    if (row.final_side_cal == null) bits.push('CALC model');
    if (!bits.length) return '';
    return `<div class="actpop-neutral">no read: ${bits.join(' &middot; ')} &mdash; none extreme enough to lean either way</div>`;
  }

  // Tradability box -- always shown, score always computed regardless of side.
  function _actpopTradabilityHtml(row) {
    const score = _buyTradabilityScore(row);
    const scoreColor = score >= 16 ? 'var(--act-buy-strong)' : score >= _TRADABILITY_BADGE_MIN ? '#d97706' : '#94a3b8';
    const items = _tradabilityBreakdown(row).map(it =>
      `<div class="actpop-trad-item"><b style="color:${it.color};">${esc(it.label)}</b>: `
      + `<span style="color:#374151;">${esc(it.detail)}</span></div>`).join('');
    return `<div class="actpop-trad">
      <div class="actpop-trad-h"><span>Tradability</span><span style="color:${scoreColor};font-size:12px;">${score.toFixed(1)}</span></div>
      ${items}
    </div>`;
  }

  // Tier 1 -- "Driven by": one bullet per source_actions entry + Technical,
  // winning source first, each with a real historical hit-rate pill.
  function _actpopDriverBullets(row, side) {
    const sc = uvPopState.sourceScorecard || {};
    const bulletFor = (label, actUpper, reason, dt, tag, pctSinceDrop, dropConflict, upStreak3d) => {
      const d = actionDisplay(actUpper);
      const cls = d.side === 'buy' ? 'buy' : d.side === 'sell' ? 'sell' : '';
      const srcSc = (sc[(label || '').toUpperCase()] || {})[d.side];
      let hit = '';
      if (srcSc && srcSc.win_rate_20d != null && srcSc.n >= 5) {
        const wr = Math.round(srcSc.win_rate_20d * 100);
        const hcls = wr < 45 ? 'hit-rate-pill-low' : wr > 55 ? 'hit-rate-pill-high' : 'hit-rate-pill-mid';
        hit = `<span class="actpop-hit hit-rate-pill ${hcls}" title="${esc(label)} hit rate: ${wr}% (n=${srcSc.n})">${wr}%</span>`;
      }
      const actionLbl = d.label || actUpper || '—';
      let noteHtml = esc(reason || '') + (dt ? ` &middot; snapshot ${esc(dt)}` : '');
      noteHtml += _dropPctPillHtml({ action: actUpper, pct_since_drop: pctSinceDrop, drop_conflict: dropConflict, up_streak_3d: upStreak3d });
      return `<div class="actpop-driver ${cls}">
        <span class="dv-name">${esc(label)}</span>${hit}
        <span class="dv-action ${cls}">${esc(actionLbl)}</span>
        <span class="dv-note">${noteHtml}</span>
        ${tag ? `<span class="dv-tag">${esc(tag)}</span>` : ''}
      </div>`;
    };
    const rows = [];
    const sources = _sourcesOf(row);
    const winning = (row.winning_source || '').toString();
    const winEntry = sources.find(s => (s.source || s.source_code || '') === winning);
    if (winEntry) {
      const code = winEntry.source || winEntry.source_code || winning;
      rows.push(bulletFor(code, winEntry.action, winEntry.reason, fmtMD(winEntry.snapshot_date), 'drove it',
        winEntry.pct_since_drop, winEntry.drop_conflict, winEntry.up_streak_3d));
    }
    const rraUpper = (row.rr_action || '').toUpperCase();
    if (rraUpper) {
      const techSide = actionDisplay(rraUpper).side;
      const tag = winEntry ? (techSide === side ? 'agrees' : (techSide && side ? 'conflicts' : ''))
                            : 'drove it';
      const desc = row.rr_desc || row.tn_td_desc || row.bb_desc || '';
      rows.push(bulletFor('Technical', rraUpper, desc, null, tag));
    }
    const others = sources.filter(s => (s.source || s.source_code || '') !== winning);
    others.sort((a, b) => (ACTION_RANK[(b.action || '').toUpperCase()] || 0) - (ACTION_RANK[(a.action || '').toUpperCase()] || 0));
    for (const s of others) {
      const code = s.source || s.source_code || '?';
      rows.push(bulletFor(code, s.action, s.reason, fmtMD(s.snapshot_date), null, s.pct_since_drop, s.drop_conflict, s.up_streak_3d));
    }
    const pvvD = row.pvv_decision;
    if (pvvD && pvvD !== 'NO_ACTION' && pvvD !== 'WATCH') {
      const pvvSide = _PVV_BUY_SIDE.includes(pvvD) ? 'buy' : (_PVV_SELL_SIDE.includes(pvvD) ? 'sell' : null);
      if (pvvSide) {
        const caution = _PVV_CAUTION.includes(pvvD);
        const cls = caution ? '' : pvvSide;
        const conflicts = (side === 'buy' || side === 'sell') && pvvSide !== side;
        const tag = conflicts ? 'conflicts' : (pvvSide === side ? 'agrees' : '');
        const info = _PVV_DECISION_INFO[pvvD];
        rows.push(`<div class="actpop-driver ${cls}">
          <span class="dv-name">PVV</span>
          <span class="dv-action ${cls}">${esc(_PVV_LABEL[pvvD] || pvvD)}</span>
          <span class="dv-note">${esc(info ? info.meaning : '')}</span>
          ${tag ? `<span class="dv-tag">${esc(tag)}</span>` : ''}
        </div>`);
      }
    }
    return rows.length ? `<div class="actpop-drivers">${rows.join('')}</div>` : '';
  }

  // Main builder -- ported verbatim from web/actionable.js::_buildActionPopHtmlV2,
  // minus the localStorage V1/V2 rollback toggle (V2 is the only version
  // here, there's no V1 on this screen to roll back to).
  function _buildActionPopHtmlV2(row) {
    const fc = finalCall(row);
    const sym = row.tos_symbol || '—';
    const side = fc.side;
    const callCls = side === 'buy' ? 'buy' : side === 'sell' ? 'sell' : 'neutral';
    const amtTxt = row.held_today && row.current_position_dollar != null
      ? _actpopFmtAmt(row.current_position_dollar) : 'not held (yet)';
    const ed = row.earnings_days;
    const hasEd = ed != null && Number(ed) >= 0 && Number(ed) < 900;
    const edDays = hasEd ? Math.round(Number(ed)) : null;
    const edTxt = hasEd
      ? ` &middot; ${edDays <= 3 ? `<span class="opex-soon">${edDays}d</span>` : `${edDays}d`}`
      : '';
    const tug = _actpopTugHtml(row, side);

    let h = `<div class="actpop">`;
    h += `<div class="actpop-head">
      <div class="actpop-sym">${esc(sym)}`
      + `<span class="actpop-call ${callCls}" style="margin-left:8px;">${esc(fc.label || actionText(fc) || '—')}</span>`
      + `<div class="actpop-co">${esc(amtTxt)}${edTxt}</div>`
      + `</div>`
      + `<div class="actpop-ctrl-row">`
      + tug.conviction
      + `<div class="actpop-ctrl-anchor-rr">${_chgCandleControlsHtml(row, 0)}</div>`
      + _actpopTdTnHtml(row)
      + _actpopRrBarHtml(row)
      + `</div>`
      + `</div>`;

    h += `<div class="actpop-rr-row">`
      + `<div class="actpop-rr-icons">${_actpopMacroStackHtml(row)}`
      + `<span class="actpop-rr-trad">${_actpopTradIconHtml(row)}</span>`
      + `<span class="actpop-pvv-calc-col">${_actpopPvvActionHtml(row)}${_actpopCalcPillHtml(row)}</span>`
      + `</div>`
      + `<div class="actpop-rr-info">${_actpopSectorEtfHtml(row)}${_actpopVlmLineHtml(row)}</div>`
      + `</div>`;

    if (row.stop_breached) {
      const lineVal = row.stop_signal === 'TN SA' ? row.trend_line_value : row.trade_line_value;
      const lineLabel = row.stop_signal === 'TN SA' ? 'Trend' : 'Trade';
      const priceTxt = lineVal != null ? ` (${lineLabel} line ${fmtUsd(Number(lineVal))})` : '';
      h += `<div class="actpop-neutral" style="color:#b91c1c;font-weight:700;">&#9888; Stop breached &mdash; `
         + `${esc(row.stop_signal || 'trade line broke down')}${priceTxt}</div>`;
    }

    const ltAvoid = row.conviction_direction === 'AVOID';
    const ltConflict = !!row.conviction_hold && side === (ltAvoid ? 'buy' : 'sell');
    if (ltConflict) {
      h += `<div class="actpop-neutral" style="color:#7c3aed;font-weight:700;">`
         + `${ltAvoid ? '&#128683;' : '&#128301;'} Conflicts with long-term conviction ${ltAvoid ? 'AVOID' : 'HOLD'} `
         + `&mdash; ${esc(row.conviction_note || '')}</div>`;
    }

    // "Fresh signal" note deliberately NOT ported -- gated in the source on
    // row._watchlisted/row._isNew, both computed client-side by
    // actionable.js's own watchlist-gating pipeline (_buyNoiseGated/
    // _isNewSnapshot), which is out of scope here (a get_actionable() row
    // doesn't carry either flag). Harmless omission -- purely informational.

    h += _actpopDriverBullets(row, side);
    h += tug.html;
    h += _actpopNeutralLine(row);

    const details = [];
    if (!row.held_today && row.suggested_target_dollar != null) details.push(`target ${_actpopFmtAmt(row.suggested_target_dollar)}`);
    if (details.length) h += `<div class="actpop-details">${details.join(' &middot; ')}</div>`;

    h += _actpopTradabilityHtml(row);

    h += `</div>`;
    return h;
  }

  // ---- Shell mechanics (adapted, not copied verbatim) --------------------
  // #uvActionPop -- own dedicated element (not a reuse of the generic
  // #uvTt tile tooltip, and NOT web/actionable.html's #sourcePop/
  // .source-pop -- that shell is pointer-events:none, hover-only; this one
  // is pointer-events:auto, see web/styles.css's .uv-actpop-shell). Created
  // once, appended to document.body, positioned near whatever element
  // triggered it -- same fits-in-viewport flip logic as actionable.js's own
  // _showDataPop.
  function _uvActionPopEl() {
    let el = $('uvActionPop');
    if (!el) {
      el = document.createElement('div');
      el.id = 'uvActionPop';
      el.className = 'uv-actpop-shell';
      document.body.appendChild(el);
    }
    return el;
  }
  function _uvShowActionPopover(el, det) {
    const pop = _uvActionPopEl();
    pop.innerHTML = _buildActionPopHtmlV2(det);
    pop.style.display = 'block';
    const rect = el.getBoundingClientRect();
    let top = rect.bottom + 4;
    if (top + pop.offsetHeight > window.innerHeight - 8) top = Math.max(8, rect.top - pop.offsetHeight - 4);
    let left = rect.left;
    if (left + pop.offsetWidth > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
    pop.style.top = top + 'px';
    pop.style.left = left + 'px';
  }
  function _uvHideActionPopover() {
    const pop = $('uvActionPop');
    if (pop) pop.style.display = 'none';
  }
  // Escape stays wired as a keyboard-only safety net -- the PRIMARY dismiss
  // is hover-out (mouseleave on the .uv-c-name element that opened it, see
  // renderSymbolTiles), per the user's course-correction: "make the
  // popover pops up only when i hover over the header ... hover on account
  // name, source name, stock name etc" -- 2026-09-06. (An earlier version
  // of this port used click-to-open + click-outside-to-dismiss; that
  // mechanism was replaced, not layered on top of, the hover one below.)
  let _uvActionPopEscapeWired = false;
  function _uvWireActionPopoverEscape() {
    if (_uvActionPopEscapeWired) return;
    _uvActionPopEscapeWired = true;
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') _uvHideActionPopover();
    });
  }

  // ---------------------------------------------------------------------
  // Wiring
  // ---------------------------------------------------------------------
  function wireStaticControls() {
    document.querySelectorAll('.uv-tab[data-view]').forEach(t =>
      t.addEventListener('click', () => {
        // "All" is a real radio option now (data-view="all"), not the old
        // separate uvAllStocksBtn toggle -- selecting it turns
        // flatStocksMode on and leaves `currentView` alone (unused while
        // flatStocksMode is on, so whatever it already was stays put for
        // whenever you switch to Account/Asset/Source next). User:
        // "Combine first two radio buttons (By account etc & All stocks)
        // into one as All|Account|Asset" -- 2026-09-06.
        if (t.dataset.view === 'all') {
          flatStocksMode = true;
        } else {
          flatStocksMode = false;
          currentView = t.dataset.view;
          // "By Account" only means anything for held positions.
          if (currentView === 'account') currentFilter = 'held';
          // Src#/Src$ are two separate buttons now, each declaring its own
          // data-size ('count'/'capital') -- a click just sets sizeMode to
          // whichever one was clicked, same as the old standalone Size-
          // toggle row used to, no more "always reset to Src# on entry"
          // special case needed (there's no longer a single "Source"
          // button that could be clicked without also picking a size).
          // User: "Why do you need Source still? Can we combine Src#|Src$
          // with All|Account|Asset" -- 2026-09-06.
          if (t.dataset.size) sizeMode = t.dataset.size;
        }
        resetDrill(); render();
      }));
    document.querySelectorAll('.uv-tab[data-filter]').forEach(t =>
      t.addEventListener('click', () => {
        currentFilter = t.dataset.filter;
        // leaving Held with "By Account" active means there's nothing left
        // to show it against -- fall back to the default view. Only THIS
        // edge case resets the drill (an Account drill leg wouldn't make
        // sense once we're no longer in Account view).
        if (currentFilter !== 'held' && currentView === 'account') { currentView = 'assetclass'; resetDrill(); }
        // Otherwise keep the current drill path -- switching the filter
        // re-slices whatever screen you're already looking at (e.g. a
        // sector's stock tiles get re-filtered in place) instead of
        // kicking you back out to the root; currentScopeRows()/
        // renderHierarchy() already rebuild the hierarchy from
        // FILTERS[currentFilter] on every render, so the drill legs
        // (assetClass/sector/account/source) stay valid as-is. User:
        // "All|held|actionable -> instead of taking to main screen, can
        // it filter the current screen (drill down screen)" -- 2026-09-06.
        render();
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

  // Short button labels for the Style filter row -- the full tag names
  // (drv_macro_score.style_stances: Cyclical/Defensives/Dividend/High
  // Beta/Low Beta/Mid Caps/Momentum/Secular/Small Caps/Value) ran the row
  // wide enough to wrap. `data-style` (used for filtering/aria-selected)
  // always stays the real, unabbreviated tag -- only the visible text is
  // shortened, with the full name kept as a `title` tooltip. Falls back to
  // the tag itself for anything not in this map (e.g. a future tag added
  // to the data before this map is updated). User: "Shorten Style names"
  // -- 2026-09-06.
  const STYLE_TAG_ABBR = {
    'Cyclical': 'Cyc', 'Defensives': 'Def', 'Dividend': 'Div',
    'High Beta': 'Hi-B', 'Low Beta': 'Lo-B', 'Mid Caps': 'Mid',
    'Momentum': 'Mom', 'Secular': 'Sec', 'Small Caps': 'Small', 'Value': 'Val',
  };
  function wireStyleTabs() {
    const styleTabs = $('uvStyleTabs');
    styleTabs.innerHTML = '<button class="uv-tab" role="tab" data-style="all" aria-selected="true">All</button>' +
      ALL_STYLE_TAGS.map(t => `<button class="uv-tab" role="tab" data-style="${esc(t)}" title="${esc(t)}" aria-selected="false">${esc(STYLE_TAG_ABBR[t] || t)}</button>`).join('');
    document.querySelectorAll('.uv-tab[data-style]').forEach(t =>
      t.addEventListener('click', () => { currentStyleFilter = t.dataset.style; render(); }));
  }

  // Dual-thumb Risk Range slider -- two overlapping native <input
  // type=range> elements (min/max), a shared visual track drawn between
  // them. Deliberately does NOT reset the drill on change, same as
  // Color/Style (see wireStaticControls' own comment on why).
  function wireRrSlider() {
    const minEl = $('uvRrMin'), maxEl = $('uvRrMax'), rangeEl = $('uvRrRange');
    const update = () => {
      let lo = parseInt(minEl.value, 10), hi = parseInt(maxEl.value, 10);
      // keep the two thumbs from crossing -- clamp whichever one just
      // moved to the other's position instead of letting lo > hi.
      if (lo > hi) {
        if (document.activeElement === maxEl) { lo = hi; minEl.value = String(lo); }
        else { hi = lo; maxEl.value = String(hi); }
      }
      rrMin = lo; rrMax = hi;
      rangeEl.style.left = lo + '%';
      rangeEl.style.right = (100 - hi) + '%';
      render();
    };
    minEl.addEventListener('input', update);
    maxEl.addEventListener('input', update);
    // initial visual state only (0-100%, the default) -- not a full
    // update(), which would also trigger a redundant render() before
    // init()'s own first render() call right after this wiring.
    rangeEl.style.left = '0%'; rangeEl.style.right = '0%';
  }

  async function init() {
    // Action popover port -- fired alongside the main /api/universe fetch
    // below, not awaited (fire-and-forget): populates uvPopState in the
    // background so it's ready by the time a user actually hovers a
    // Symbol tile's name; doesn't block the treemap's own first render.
    _uvLoadPopState();
    _uvWireActionPopoverEscape();
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
    renderKpiStrip();
    FILTERS = {
      all:        { rows: SYMS },
      held:       { rows: SYMS.filter(r => r.held_today) },
      actionable: { rows: SYMS.filter(r => r.final_code && r.final_code !== 'HOLD') },
    };
    $('uvAsOf').textContent = new Date().toLocaleDateString();
    wireStyleTabs();
    wireRrSlider();
    wireStaticControls();
    render();
  }

  init();
})();
