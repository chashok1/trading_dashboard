// web/portfolio_mix.js -- shared "Portfolio Mix" pie-chart engine, used by
// both the Actionable screen's sidebar panel (web/actionable.js,
// #portfolioMixSection) and the Dashboard screen's card below Cumulative
// P&L (web/app.js, #todaySnapshot). Extracted from actionable.js so the
// Dashboard could reuse the exact same charts instead of re-implementing
// them. User: "display graphs from actionable screen, side bar -> portfolio
// mix -> asset allocation, Beta, sector, concentration ... on dashboard
// screen -> line below cumulative P&L."
//
// Loaded on both pages BEFORE actionable.js / app.js. Depends only on
// globals from _common.js ($, escapeHtml, fetchJson) and the Chart.js CDN
// script, both already loaded ahead of this file on both pages.

// Fixed vocabulary (from _ASSET_CLASS_ALIAS) -> fixed color, same category
// always gets the same slice color regardless of what else is held.
const _ASSET_CLASS_ALIAS = {
  'domestic equities': 'Equities', 'global equities': 'Equities',
  'international equities': 'Equities', 'emerging markets equities': 'Equities',
  'equities': 'Equities',
  'us fixed income': 'Fixed Income', 'domestic fixed income': 'Fixed Income',
  'fixed income': 'Fixed Income',
  'foreign currencies': 'FX', 'foreign currency': 'FX', 'fx': 'FX',
  'commodities': 'Commodities',
  'crypto': 'Crypto',
  'gold': 'Gold',
  'cash': 'Cash',
};
function _normAssetClass(raw) {
  if (!raw) return 'Unclassified';
  const key = String(raw).trim().toLowerCase();
  return _ASSET_CLASS_ALIAS[key] || raw;
}

const _PM_BETA_COLORS = { Low: '#0ca30c', Mid: '#fab219', High: '#d03b3b', Unknown: '#898781' };
const _PM_CAT_PALETTE = ['#2a78d6', '#008300', '#e87ba4', '#eda100', '#1baf7a', '#eb6834', '#4a3aa7', '#e34948'];
const _PM_SIDE_COLORS = { buy: '#166534', sell: '#991b1b', neutral: '#6b7280' };
const _PM_ASSET_COLORS = {
  Equities: '#2a78d6', 'Fixed Income': '#008300', Cash: '#898781',
  Commodities: '#eb6834', Gold: '#eda100', Crypto: '#4a3aa7',
  FX: '#e87ba4', Unclassified: '#c3c2b7',
};
const _pmCharts = {};

function _pmFmtUsd(v) {
  const n = Number(v) || 0;
  return Math.abs(n) >= 1000 ? '$' + (n / 1000).toFixed(1) + 'k' : '$' + Math.round(n);
}

// Formats the ticker list shown on hover (chart tooltip + legend title),
// wrapped ~8/line, capped at 24 with a "+N more" tail so a big HOLD/Financials
// bucket doesn't produce an unreadable wall of text.
function _pmTickerLines(tickers) {
  const cap = 24, perLine = 8;
  const shown = tickers.slice(0, cap);
  const lines = [];
  for (let i = 0; i < shown.length; i += perLine) lines.push(shown.slice(i, i + perLine).join(', '));
  if (tickers.length > cap) lines.push(`+${tickers.length - cap} more`);
  return lines;
}

// Chart.js's built-in tooltip draws INSIDE the canvas's own pixel bounds --
// with a 90x90 canvas, our multi-line ticker text simply gets clipped. This
// renders an external floating tooltip (fixed-position div on <body>) instead,
// so it isn't clipped by the tiny canvas or the panel's overflow:hidden, and
// flips to the left of the cursor when it would overflow the viewport edge.
function _pmTooltipHandler(context) {
  const { chart, tooltip } = context;
  let el = document.getElementById('pmTooltipFloat');
  if (!el) {
    el = document.createElement('div');
    el.id = 'pmTooltipFloat';
    el.style.cssText = 'position:fixed;pointer-events:none;z-index:9999;background:#1f2937;color:#f3f4f6;'
      + 'font-size:10px;line-height:1.5;padding:5px 7px;border-radius:4px;max-width:220px;'
      + 'white-space:pre-line;box-shadow:0 2px 8px rgba(0,0,0,0.3);opacity:0;';
    document.body.appendChild(el);
  }
  if (!tooltip || tooltip.opacity === 0) { el.style.opacity = '0'; return; }
  const lines = [];
  (tooltip.body || []).forEach(b => (b.lines || []).forEach(l => lines.push(l)));
  el.innerHTML = lines.map(escapeHtml).join('<br>');
  const rect = chart.canvas.getBoundingClientRect();
  const cx = rect.left + tooltip.caretX;
  const cy = rect.top + tooltip.caretY;
  el.style.left = '0px'; el.style.top = '0px'; el.style.opacity = '1';
  const w = el.offsetWidth, h = el.offsetHeight;
  let x = (cx + w + 12 > window.innerWidth) ? cx - w - 12 : cx + 12;
  let y = (cy + h > window.innerHeight) ? window.innerHeight - h - 8 : cy;
  el.style.left = Math.max(4, x) + 'px';
  el.style.top = Math.max(4, y) + 'px';
}

function _pmDrawPie(key, canvasId, legendId, labels, values, colors, tickerLists, emptyMsg) {
  const canvas = $(canvasId);
  const legendEl = $(legendId);
  if (!canvas) return;
  if (_pmCharts[key]) { _pmCharts[key].destroy(); _pmCharts[key] = null; }
  const total = values.reduce((a, b) => a + b, 0);
  if (!total || !labels.length) {
    canvas.style.display = 'none';
    if (legendEl) legendEl.innerHTML = `<div class="empty-note" style="font-size:10px;">${emptyMsg}</div>`;
    return;
  }
  canvas.style.display = '';
  _pmCharts[key] = new Chart(canvas, {
    type: 'doughnut',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: '#fff', borderWidth: 1 }] },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      cutout: '55%',
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: false,
          external: _pmTooltipHandler,
          callbacks: {
            label: (ctx) => {
              const pct = total ? Math.round(ctx.parsed / total * 100) : 0;
              return ` ${ctx.label}: ${_pmFmtUsd(ctx.parsed)} (${pct}%)`;
            },
            afterLabel: (ctx) => _pmTickerLines((tickerLists && tickerLists[ctx.dataIndex]) || []),
          },
        },
      },
    },
  });
  if (legendEl) {
    legendEl.innerHTML = labels.map((lab, i) => {
      const pct = total ? Math.round(values[i] / total * 100) : 0;
      const tickers = (tickerLists && tickerLists[i]) || [];
      const title = tickers.length ? escapeHtml(_pmTickerLines(tickers).join('\n')) : '';
      return `<div title="${title}" style="display:flex;align-items:center;gap:4px;font-size:10px;padding:1px 0;cursor:${tickers.length ? 'help' : 'default'};">`
        + `<span style="width:8px;height:8px;border-radius:2px;background:${colors[i]};flex-shrink:0;"></span>`
        + `<span style="flex:1;min-width:0;color:#374151;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(lab)}</span>`
        + `<span style="color:#6b7280;flex-shrink:0;">${pct}%</span>`
        + `</div>`;
    }).join('');
  }
}

// Draws the 4 core Portfolio Mix pies (Asset Allocation, Beta, Sector,
// Concentration) shared between the Actionable sidebar (idPrefix 'pm') and
// the Dashboard screen (idPrefix 'dpm'; canvas/legend ids idPrefix+'AssetCanvas'
// etc.). Macro Stance is NOT included here -- it depends on actionDisplay()'s
// buy/sell/neutral mapping, an Actionable-screen-only concept -- callers that
// want it draw it themselves via _pmDrawPie(idPrefix+'Macro', ...).
function pmRenderCoreMix(idPrefix, heldRowsIn, cashTotal, betaMap) {
  const held = (heldRowsIn || []).slice()
    .sort((a, b) => (Number(b.current_position_dollar) || 0) - (Number(a.current_position_dollar) || 0));

  // Asset allocation mix -- r._pmAssetClass, the SAME drv_ma.asset_class
  // (ref_sector fallback, "Unmapped" for anything else) classification the
  // Asset class factor-scorecard table uses (via /api/portfolio/asset-
  // class-map), so this pie always agrees with that table. NOT
  // r._assetClass (real_asset_class/_normAssetClass, the broker's own
  // source asset-class tag) -- that field still drives the Actionable
  // grid's own Asset Class filter chips unrelated to this pie, and the two
  // classifications can legitimately disagree per symbol (see the
  // /api/portfolio/asset-class-map docstring). Plus uninvested cash
  // (SPAXX/pending activity, via is_cash()) which has no tos_symbol so it
  // can't come from `held`.
  const assetTotals = {}, assetTickerMap = {};
  for (const r of held) {
    const ac = r._pmAssetClass || 'Unmapped';
    assetTotals[ac] = (assetTotals[ac] || 0) + (Number(r.current_position_dollar) || 0);
    (assetTickerMap[ac] = assetTickerMap[ac] || []).push(r.tos_symbol);
  }
  if (cashTotal > 0) {
    assetTotals.Cash = (assetTotals.Cash || 0) + cashTotal;
    assetTickerMap.Cash = (assetTickerMap.Cash || []).concat(['Cash balance']);
  }
  const assetLabels = Object.keys(assetTotals).sort((a, b) => assetTotals[b] - assetTotals[a]);
  _pmDrawPie(idPrefix + 'Asset', idPrefix + 'AssetCanvas', idPrefix + 'AssetLegend',
    assetLabels, assetLabels.map(k => assetTotals[k]),
    assetLabels.map(k => _PM_ASSET_COLORS[k] || '#c3c2b7'),
    assetLabels.map(k => assetTickerMap[k]), 'No asset class data for held positions.');

  if (!held.length) {
    ['Beta', 'Sector', 'Conc'].forEach(suf => {
      _pmDrawPie(idPrefix + suf, idPrefix + suf + 'Canvas', idPrefix + suf + 'Legend',
        [], [], [], [], 'No held positions match the current filters.');
    });
    return;
  }

  // Beta mix -- Low <=0.7 / Mid / High >=1.5, matching etl/derive_macro.py::_classify_style.
  const betaBuckets = { Low: 0, Mid: 0, High: 0, Unknown: 0 };
  const betaTickers = { Low: [], Mid: [], High: [], Unknown: [] };
  for (const r of held) {
    const b = (betaMap || {})[r.tos_symbol];
    const amt = Number(r.current_position_dollar) || 0;
    const bucket = b == null ? 'Unknown' : b <= 0.7 ? 'Low' : b >= 1.5 ? 'High' : 'Mid';
    betaBuckets[bucket] += amt;
    betaTickers[bucket].push(r.tos_symbol);
  }
  const betaLabels = Object.keys(betaBuckets).filter(k => betaBuckets[k] > 0);
  _pmDrawPie(idPrefix + 'Beta', idPrefix + 'BetaCanvas', idPrefix + 'BetaLegend',
    betaLabels, betaLabels.map(k => betaBuckets[k]), betaLabels.map(k => _PM_BETA_COLORS[k]),
    betaLabels.map(k => betaTickers[k]), 'No beta data for held positions.');

  // Sector mix -- top 7 by $ value + Other. Color assigned by alpha rank so
  // the same sector keeps the same slot across re-renders (not tied to $ rank).
  // Groups by r._pmSector (from /api/portfolio/sector-map), the SAME
  // canonicalized/equity-gated/ref_sector-fallback classification the
  // Sector factor-scorecard table uses -- NOT the raw r.sector field
  // (still drives the Actionable grid's own unrelated Sector filter
  // chips).
  //
  // 2026-08-14 -- Non-equity holdings (bond/gold/commodity ETFs) EXCLUDED
  // entirely from this pie -- their dollars simply aren't part of the
  // Sector mix, same as Cash isn't. Previously shown as their own
  // "Non-Equity (excluded)" slice (matching the table's then-behavior of
  // the same name); user: "Sector should include only equities from
  // 'Asset Class', so non-equity (excluded) probably shouldn't exist at
  // all in the sector" -- reverted alongside api/routers/cockpit.py's own
  // get_factor_scorecard, which now drops that category from the table's
  // response the same way again.
  //
  // 2026-08-14 (earlier the same day) -- briefly added a Cash slice here
  // (to make this pie's % match the table's own WT% column, which divides
  // by the whole portfolio including cash) -- reverted same day. User,
  // after seeing it live: "top sector included the cash, which it should
  // not." Sector intentionally has no Cash category (cash isn't
  // sector-classified); this pie's % is deliberately "% of your
  // sector-classified equity holdings", not "% of whole portfolio" --
  // won't equal the table's WT% number, by design.
  const secTotals = {}, secTickerMap = {};
  for (const r of held) {
    if (r._pmSector === 'Non-Equity (excluded)') continue;
    const s = r._pmSector || 'Unmapped';
    secTotals[s] = (secTotals[s] || 0) + (Number(r.current_position_dollar) || 0);
    (secTickerMap[s] = secTickerMap[s] || []).push(r.tos_symbol);
  }
  let secEntries = Object.entries(secTotals).sort((a, b) => b[1] - a[1]);
  let secTickerLists = secEntries.map(e => secTickerMap[e[0]]);
  if (secEntries.length > 8) {
    const otherSum = secEntries.slice(7).reduce((s, e) => s + e[1], 0);
    const otherTickers = secEntries.slice(7).flatMap(e => secTickerMap[e[0]]);
    secEntries = secEntries.slice(0, 7).concat([['Other', otherSum]]);
    secTickerLists = secTickerLists.slice(0, 7).concat([otherTickers]);
  }
  const sortedSecNames = secEntries.map(e => e[0]).filter(n => n !== 'Other').sort();
  const secColorOf = (n) => n === 'Other' ? '#898781' : _PM_CAT_PALETTE[sortedSecNames.indexOf(n) % _PM_CAT_PALETTE.length];
  _pmDrawPie(idPrefix + 'Sector', idPrefix + 'SectorCanvas', idPrefix + 'SectorLegend',
    secEntries.map(e => e[0]), secEntries.map(e => e[1]), secEntries.map(e => secColorOf(e[0])),
    secTickerLists, 'No sector data for held positions.');

  // Concentration -- top 7 holdings by $ value + Other.
  let concEntries = held.map(r => [r.tos_symbol, Number(r.current_position_dollar) || 0]);
  let concTickerLists = concEntries.map(e => [e[0]]);
  if (concEntries.length > 8) {
    const otherSum = concEntries.slice(7).reduce((s, e) => s + e[1], 0);
    const otherTickers = concEntries.slice(7).map(e => e[0]);
    concEntries = concEntries.slice(0, 7).concat([['Other', otherSum]]);
    concTickerLists = concTickerLists.slice(0, 7).concat([otherTickers]);
  }
  _pmDrawPie(idPrefix + 'Conc', idPrefix + 'ConcCanvas', idPrefix + 'ConcLegend',
    concEntries.map(e => e[0]), concEntries.map(e => e[1]),
    concEntries.map((e, i) => e[0] === 'Other' ? '#898781' : _PM_CAT_PALETTE[i % _PM_CAT_PALETTE.length]),
    concTickerLists, 'No held positions.');
}
