/* Portfolio page logic */

const state = {
  date: null,
  rows: [],
  filtered: [],
  accountMap: {},
  accountList: [],
  accountExpanded: false,
  summary: null,  // Cache summary response so filters can re-render tiles without re-fetching
  filters: {
    source: '',
    account: '',
    consolidated: false,
    latestPrices: false,
    search: '',
    limitStatus: '',
  },
  sort: {
    column: 'symbol',
    direction: 'asc',
  },
  chart: null,
};
const $ = (id) => document.getElementById(id);

// Chart.js instances for the Trends panel (destroyed before re-render)
const _trendCharts = { value: null, daily: null, cum: null };
const _sparkCharts = {};   // keyed by account name

let _lastTrendData = null;

async function loadTrends() {
    const periodEl = $('trendsPeriod');
    const period = (periodEl && periodEl.value) || 'mtd';
    const params = new URLSearchParams({ period });
    if (state.filters.account) params.set('account', state.filters.account);
    if (state.filters.source)  params.set('source',  state.filters.source);
    let data;
    try {
        data = await fetchJson('/api/portfolio/trends?' + params.toString());
    } catch (e) {
        console.warn('loadTrends failed:', e);
        return;
    }
    _lastTrendData = data;
    renderTrendCharts(data);
    renderSparklines(data);
    const rngEl = $('trendsRange');
    if (rngEl && data && data.dates && data.dates.length) {
        rngEl.textContent = data.dates[0] + ' → ' + data.dates[data.dates.length - 1];
    } else if (rngEl) {
        rngEl.textContent = '(no data in period)';
    }
}

function renderTrendCharts(data) {
    if (typeof Chart === 'undefined') return;
    const labels = data.dates || [];
    const colorPos = '#1c6c30', colorNeg = '#b21f1f', colorAcc = '#7F77DD';
    const yTick = (v) => Math.abs(v) >= 1000
        ? '$' + (Math.round(v / 100) / 10).toFixed(1) + 'k'
        : '$' + Math.round(v);
    // After Chart.js lays out the chart, copy the right Y-axis gutter width
    // onto a header div so the last value in the header lines up with the
    // plot-area's right edge (instead of running past it to the canvas edge).
    function syncHeaderPadding(headerId) {
        return {
            afterLayout(chart) {
                const el = document.getElementById(headerId);
                if (!el) return;
                // For right-positioned axes, chart.chartArea.right is where
                // the data plot ends. chart.width is canvas total width.
                const pad = Math.max(0, chart.width - chart.chartArea.right);
                el.style.paddingRight = pad + 'px';
            }
        };
    }
    // Account Value chart options: NO legend, x-axis ticks visible, Y on right
    const baseOpts = {
        responsive: true, maintainAspectRatio: false,
        plugins: {
            legend:  { display: false },
            tooltip: { enabled: true, mode: 'index', intersect: false },
        },
        scales: {
            x: { display: true,
                 ticks: { font: { size: 9 }, color: '#666',
                          maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
                 grid:  { display: false } },
            y: { type: 'linear', position: 'right', display: true,
                 ticks: { font: { size: 9 }, color: '#666', callback: yTick },
                 grid:  { color: 'rgba(0,0,0,0.06)' } },
        },
        elements: { point: { radius: 0 } },
    };
    if (_trendCharts.value) _trendCharts.value.destroy();
    _trendCharts.value = new Chart($('chTrendValue'), {
        type: 'line',
        data: { labels, datasets: [{
            label: 'Account Value',
            data: data.account_value || [], borderColor: colorAcc,
            backgroundColor: 'rgba(127,119,221,0.12)', fill: true,
            borderWidth: 2, tension: 0.25,
        }] },
        options: baseOpts,
        plugins: [syncHeaderPadding('ovValueHeader')],
    });
    // Combined Cumulative P&L (line) + Day Change (thin bars overlay)
    if (_trendCharts.daily) _trendCharts.daily.destroy();
    if (_trendCharts.cum)   _trendCharts.cum.destroy();
    // Copy so the override below doesn't mutate _lastTrendData. Without
    // .slice() a toggle off→on cycle would see dayArr[last] already pointing
    // at the previously-overridden value, making origDay == newDay and
    // producing a zero-delta override (= no visible change).
    const dayArr = (data.day_change || []).slice();
    const cum    = (data.cumulative_pl || []).slice();
    // ── Latest-prices override for the rightmost bar + Cum line ─────────
    // The rightmost data point represents the "current" day in this chart
    // (which equals today only when today's data is loaded; otherwise it
    // equals the most recent loaded snapshot). When "Use latest prices" is
    // on, replace that day's day_change with the client-side recomputed
    // value (sum of overridden per-row today_gain) and re-derive the
    // cumulative. Skip ONLY when the user has selected a Portfolio snapshot
    // date older than this trends series (then they're examining history,
    // and re-pricing makes no sense).
    if (state.filters && state.filters.latestPrices && state.latestSummary
        && cum.length && data.dates && data.dates.length === cum.length) {
        const lastIdx = cum.length - 1;
        const lastTrendsDate = data.dates[lastIdx];
        const userInPast = state.date && lastTrendsDate && state.date < lastTrendsDate;
        if (!userInPast) {
            const newDay = Number(state.latestSummary.today_gain_dollar || 0);
            const origDay = Number(dayArr[lastIdx] || 0);
            dayArr[lastIdx] = newDay;
            cum[lastIdx] = (cum[lastIdx] || 0) - origDay + newDay;
        }
    }
    // lastCum / cumColor computed AFTER the override so the line color and
    // overlay label both reflect the new rightmost value.
    const lastCum  = cum.length ? cum[cum.length - 1] : 0;
    const cumColor = lastCum >= 0 ? colorPos : colorNeg;
    const _lastCum = lastCum;  // kept for compatibility with _finalCum below
    const combinedOpts = {
        responsive: true, maintainAspectRatio: false,
        plugins: {
            legend:  { display: false },
            tooltip: { enabled: true, mode: 'index', intersect: false },
        },
        scales: {
            x:  { display: true,
                  ticks: { font: { size: 9 }, color: '#666',
                           maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
                  grid:  { display: false } },
            y:  { type: 'linear', position: 'right', display: true,
                  ticks: { font: { size: 9 }, color: '#666', callback: yTick },
                  grid:  { color: 'rgba(0,0,0,0.06)' } },
            y1: { type: 'linear', position: 'left', display: true,
                  ticks: { font: { size: 9 }, color: '#888', callback: yTick },
                  grid:  { drawOnChartArea: false } },
        },
        elements: { point: { radius: 0 } },
    };
    _trendCharts.cum = new Chart($('chTrendCum'), {
        type: 'bar',
        data: { labels, datasets: [
            // Thin Day Change bars on the secondary axis (left).
            // order:0 puts bars on top so they're never hidden by the line stroke.
            { type: 'bar', label: 'Day Change', data: dayArr,
              backgroundColor: dayArr.map(v => v >= 0
                  ? 'rgba(28,108,48,0.85)' : 'rgba(178,31,31,0.85)'),
              borderWidth: 0,
              barPercentage: 0.45, categoryPercentage: 0.7,
              yAxisID: 'y1', order: 0 },
            // Cumulative P&L line on the primary axis (right). fill:false so
            // the line's translucent area doesn't cover the bars underneath.
            { type: 'line', label: 'Cumulative P&L', data: cum,
              borderColor: cumColor,
              backgroundColor: lastCum >= 0 ? 'rgba(28,108,48,0.10)' : 'rgba(178,31,31,0.10)',
              fill: false, borderWidth: 2, tension: 0.25,
              yAxisID: 'y', order: 1 },
        ] },
        options: combinedOpts,
        plugins: [syncHeaderPadding('ovCumHeader')],
    });
    // Update the Cum overlay label in the chart header
    // Prefer the post-override cumulative if present (latest-prices toggle).
    const _finalCum = (typeof _lastCum === 'number') ? _lastCum : lastCum;
    const ovCumEl = $('ovCum');
    if (ovCumEl) {
        ovCumEl.textContent = (_finalCum >= 0 ? '+' : '') + fmtUsd(_finalCum);
        ovCumEl.className   = gainClass(_finalCum);
    }
}

function renderSparklines(data) {
    if (typeof Chart === 'undefined') return;
    const colorPos = '#1c6c30', colorNeg = '#b21f1f';
    // Walk every spark-canvas-{acct} created by the by-account renderer
    Object.keys(_sparkCharts).forEach(k => { try { _sparkCharts[k].destroy(); } catch (e) {} });
    document.querySelectorAll('canvas[data-spark-acct]').forEach(c => {
        const acct = c.getAttribute('data-spark-acct');
        const series = (data.per_account || {})[acct] || [];
        const last = series.length ? series[series.length - 1] : null;
        const first = series.length ? series[0] : null;
        const trendUp = (last != null && first != null) ? (last >= first) : true;
        const color = trendUp ? colorPos : colorNeg;
        _sparkCharts[acct] = new Chart(c, {
            type: 'line',
            data: { labels: series.map((_, i) => i),
                    datasets: [{ data: series, borderColor: color,
                                 backgroundColor: color + '22',
                                 fill: true, borderWidth: 1.5, tension: 0.25,
                                 pointRadius: 0 }] },
            options: { responsive: true, maintainAspectRatio: false,
                       plugins: { legend: { display: false }, tooltip: { enabled: false } },
                       scales: { x: { display: false }, y: { display: false } } },
        });
    });
}



let _trendModalChart = null;

function openTrendModal(key, title) {
    if (!_lastTrendData) return;
    const colorPos = '#1c6c30', colorNeg = '#b21f1f', colorAcc = '#7F77DD';
    const labels = _lastTrendData.dates || [];

    let dataset, type, yPos = 'right', combined = null;
    if (key === 'value') {
        dataset = { type: 'line',
                    data: _lastTrendData.account_value || [], borderColor: colorAcc,
                    backgroundColor: 'rgba(127,119,221,0.15)', fill: true,
                    borderWidth: 2, tension: 0.25, pointRadius: 0 };
        type = 'line';
    } else if (key === 'cum' || key === 'daily') {
        // Cumulative P&L (line, right axis) + Day Change (thin bars, left axis)
        const arr = _lastTrendData.day_change || [];
        const cum = _lastTrendData.cumulative_pl || [];
        const lastCum = cum.length ? cum[cum.length - 1] : 0;
        const cumColor = lastCum >= 0 ? colorPos : colorNeg;
        combined = [
            { type: 'bar', label: 'Day Change', data: arr,
              backgroundColor: arr.map(v => v >= 0
                  ? 'rgba(28,108,48,0.85)' : 'rgba(178,31,31,0.85)'),
              borderWidth: 0,
              barPercentage: 0.45, categoryPercentage: 0.7,
              yAxisID: 'y1', order: 0 },
            { type: 'line', label: 'Cumulative P&L', data: cum,
              borderColor: cumColor,
              backgroundColor: lastCum >= 0 ? 'rgba(28,108,48,0.10)' : 'rgba(178,31,31,0.10)',
              fill: false, borderWidth: 2, tension: 0.25, pointRadius: 0,
              yAxisID: 'y', order: 1 },
        ];
        type = 'bar';
    } else if (key === 'account') {
        // title is "Account Name — Market Value"; recover account from the prefix
        const acct = (title || '').split(' — ')[0];
        const series = (_lastTrendData.per_account || {})[acct] || [];
        const first = series.length ? series[0]  : null;
        const last  = series.length ? series[series.length - 1] : null;
        const up = (last != null && first != null) ? (last >= first) : true;
        const c = up ? colorPos : colorNeg;
        dataset = { type: 'line', data: series, borderColor: c,
                    backgroundColor: (up ? 'rgba(28,108,48,0.15)' : 'rgba(178,31,31,0.15)'),
                    fill: true, borderWidth: 2, tension: 0.25, pointRadius: 0 };
        type = 'line';
    } else {
        return;
    }

    const sub = _lastTrendData.start && _lastTrendData.end
        ? _lastTrendData.start + ' → ' + _lastTrendData.end
        : '';
    $('trendModalTitle').textContent = title;
    $('trendModalSub').textContent   = sub;
    $('trendModalBackdrop').style.display = 'flex';

    if (_trendModalChart) { _trendModalChart.destroy(); _trendModalChart = null; }
    const yTick = (v) => Math.abs(v) >= 1000
        ? '$' + (Math.round(v / 100) / 10).toFixed(1) + 'k'
        : '$' + Math.round(v);
    const modalScales = combined
        ? {
            x:  { display: true,
                  ticks: { font: { size: 10 }, color: '#666',
                           maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
                  grid: { display: false } },
            y:  { type: 'linear', position: 'right', display: true,
                  ticks: { font: { size: 10 }, color: '#666', callback: yTick },
                  grid: { color: 'rgba(0,0,0,0.06)' } },
            y1: { type: 'linear', position: 'left',  display: true,
                  ticks: { font: { size: 10 }, color: '#888', callback: yTick },
                  grid: { drawOnChartArea: false } },
          }
        : {
            x: { display: true,
                 ticks: { font: { size: 10 }, color: '#666',
                          maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
                 grid: { display: false } },
            y: { type: 'linear', position: yPos, display: true,
                 ticks: { font: { size: 10 }, color: '#666', callback: yTick },
                 grid: { color: 'rgba(0,0,0,0.06)' } },
          };
    _trendModalChart = new Chart($('trendModalCanvas'), {
        type,
        data: { labels, datasets: combined ? combined : [dataset] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend:  { display: false },
                tooltip: { enabled: true, mode: combined ? 'index' : 'nearest', intersect: false },
            },
            scales: modalScales,
        },
    });
}

function closeTrendModal() {
    if (_trendModalChart) { _trendModalChart.destroy(); _trendModalChart = null; }
    const bd = $('trendModalBackdrop');
    if (bd) bd.style.display = 'none';
}

// fetchJson is provided by _common.js (window.fetchJson).

function fmtUsd(v, opts = {}) {
  if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return '';
  const n = Number(v);
  const abs = Math.abs(n);
  let s;
  if (opts.compact && abs >= 1e6) {
    s = Math.abs(n / 1e6).toLocaleString(undefined,
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'M';
  } else if (opts.compact && abs >= 1e3) {
    s = Math.abs(n / 1e3).toLocaleString(undefined,
        { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'K';
  } else {
    s = abs.toLocaleString(undefined,
        { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return (n < 0 ? '-$' : '$') + s;
}
function fmtPct(v, d = 2) {
  if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return '';
  return (Number(v) >= 0 ? '+' : '') + Number(v).toFixed(d) + '%';
}
function fmtNum(v, d = 2) {
  if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return '';
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: d });
}
function gainClass(v) {
  if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return 'gain-zero';
  const n = Number(v);
  if (n > 0) return 'gain-pos';
  if (n < 0) return 'gain-neg';
  return 'gain-zero';
}
// ---- Export current Positions view to CSV --------------------------------
function exportPositionsCsv() {
  const rows = state.filtered || [];
  // Match the column order shown in the on-screen grid.
  const headers = [
    'Account','Source','Symbol','Description','Qty',
    'AvgCost','LastPrice','MarketValue','CostBasis',
    'TodayGain$','TodayGain%','TotalGain$','TotalGain%',
    'PctOfTP','Sector','Action','LimitStatus','InMyList',
    'YTDGain$','MTDGain$',
  ];
  const fields = [
    'account','source','symbol','description','qty',
    'avg_cost','last_price','market_value','cost_basis',
    'today_gain_dollar','today_gain_pct','total_gain_dollar','total_gain_pct',
    'pct_of_tp','sector','consolidated_action','limit_status','in_my_list',
    'ytd_gain_dollar','mtd_gain_dollar',
  ];
  // RFC 4180-style CSV escape: wrap every field in double quotes and
  // double any internal quotes. Handles commas, newlines, quotes safely.
  const esc = v => {
    if (v === null || v === undefined) return '""';
    return '"' + String(v).replace(/"/g, '""') + '"';
  };
  const lines = [headers.map(esc).join(',')];
  for (const r of rows) {
    lines.push(fields.map(f => esc(r[f])).join(','));
  }
  const csv = lines.join('\r\n');
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  const date = state.date || new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `portfolio_${date}.csv`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// escapeHtml is provided by _common.js (window.escapeHtml).

// ---- date picker ----
async function loadDates() {
  try {
    const dates = await fetchJson('/api/dates');
    console.log('Dates loaded:', dates);
    const sel = $('datePicker');
    sel.innerHTML = '';
    for (const d of dates) {
      const o = document.createElement('option');
      o.value = d; o.textContent = d;
      sel.appendChild(o);
    }
    state.date = dates[0] || null;
    console.log('State date set to:', state.date);
    if (state.date) {
      sel.value = state.date;
      await loadSummary();
      await loadPortfolio();
    }
  } catch (e) {
    console.error('Failed to load dates:', e);
    showStatus('Failed to load dates: ' + e.message, 'error');
  }
}

// ---- KPI tiles renderer ----

// ---- Cash-row detection -----------------------------------------------
// TASK_54: reads server-emitted is_cash flag (computed by the DB function
// is_cash() in baseline.sql). Falls back to client-side rules for rows
// that predate the migration or come from other endpoints.
function isCashRow(r) {
  if (!r) return false;
  // Prefer server-computed flag when present.
  if (r.is_cash !== undefined && r.is_cash !== null) return r.is_cash === true;
  // Fallback: reproduce the rules for older data / non-portfolio endpoints.
  const sym  = (r.symbol || '');
  const desc = (r.description || '').toUpperCase();
  const stype = (r.security_type || '');
  const src  = (r.source || '').toUpperCase();
  if (src === 'F') {
    return sym === 'SPAXX**' || desc.indexOf('HELD IN MONEY MARKET') >= 0;
  }
  if (src === 'CS') {
    return sym === 'Cash & Cash Investments' || stype === 'Cash and Money Market';
  }
  return false;
}

// ---- Latest-prices client-side aggregate override ----------------------
// When the "Use latest prices" toggle is on, /api/portfolio returns rows whose
// last_price / market_value / today_gain_dollar have been re-priced from
// drv_quote. We re-aggregate them here so the chart-header tiles (Market,
// Cost, Today's Gain, Cash, Total) reflect the same view as the per-row grid.
//
// Cash rows are split out so Market = sum(non-cash market_value) and
// Cash = sum(cash row market_value). Without that split, Market would
// double-count cash (it'd include SPAXX/Schwab cash) and the global
// cash tile would still add cash again on top — inflating Total.
function recomputeLatestSummary() {
  if (!state.filters.latestPrices) { state.latestSummary = null; return; }
  let mv = 0, tg = 0, cb = 0, cash = 0;
  // Sum from state.filtered (what the grid is actually showing) so the
  // tile and the grid always match. Fall back to state.rows for the
  // brief moment before applyClientFilter() has populated filtered.
  const src = (state.filtered && state.filtered.length) ? state.filtered : state.rows;
  for (const r of src || []) {
    if (isCashRow(r)) {
      if (r.market_value != null) cash += Number(r.market_value);
      continue;
    }
    if (r.market_value     != null) mv += Number(r.market_value);
    if (r.today_gain_dollar!= null) tg += Number(r.today_gain_dollar);
    if (r.cost_basis       != null) cb += Number(r.cost_basis);
  }
  state.latestSummary = {
    market_value:      mv,
    today_gain_dollar: tg,
    cost_basis:        cb,
    cash_value:        cash,
    total_gain_dollar: mv - cb,
    total_gain_pct:    cb !== 0 ? ((mv - cb) / cb) * 100 : null,
  };
}

// Returns the summary entry to render, layering latestSummary overrides if on.
function effectiveSummary(base) {
  if (!base) return base;
  if (!state.filters.latestPrices || !state.latestSummary) return base;
  return Object.assign({}, base, state.latestSummary);
}

function renderKpiTiles(data) {
  // Render KPI tiles from a data object that may be the global summary or a by_account entry.
  // Both have the same shape: market_value, today_gain_dollar, today_gain_pct, ytd_gain_dollar, mtd_gain_dollar, cost_basis, positions.
  const safeSet = (id, text) => {
    const el = $(id);
    if (el) el.textContent = text;
    else console.warn('Missing element:', id);
  };
  const safeClass = (id, cls) => {
    const el = $(id);
    if (el) el.className = cls;
    else console.warn('Missing element:', id);
  };

  const mv  = data.market_value      || 0;
  const tg  = data.today_gain_dollar || 0;
  const cb  = data.cost_basis        || 0;
  const ytd = data.ytd_gain_dollar != null ? Number(data.ytd_gain_dollar) : null;
  const mtd = data.mtd_gain_dollar != null ? Number(data.mtd_gain_dollar) : null;

  safeSet('kpiMV', fmtUsd(mv));
  safeSet('kpiMVsub', cb ? 'cost ' + fmtUsd(cb, { compact: true }) : '');

  safeSet('kpiToday', (tg >= 0 ? '+' : '') + fmtUsd(tg));
  safeClass('kpiToday', 'kpi-value ' + gainClass(tg));
  safeClass('kpiTodayPct', 'kpi-sub ' + gainClass(data.today_gain_pct));
  safeSet('kpiTodayPct', data.today_gain_pct != null ? fmtPct(data.today_gain_pct) : '');

  // Day Change: Schwab-style day change (currently held positions only,
  // excludes realized P&L from today's sales). Will equal Today's Gain
  // for F (Fidelity reports just day change) and differ for CS when there
  // were sales today.
  // Realized Today: FIFO realized P&L (for tax tracking). Today's Gain above
  // already matches Schwab via the API formula (day_chng + intraday-on-sold + DIV/INT),
  // so we no longer display a separate Day Change tile.
  const rt = data.realized_today_dollar != null ? Number(data.realized_today_dollar) : null;
  safeSet('kpiRealizedToday', rt != null ? (rt >= 0 ? '+' : '') + fmtUsd(rt) : '—');
  safeClass('kpiRealizedToday', 'kpi-value ' + gainClass(rt));

  safeSet('kpiCost', fmtUsd(cb));

  // ── Mirror the KPI numbers into the trend chart headers (Account Value
  //     and Daily Day Change). The old standalone tiles for these are
  //     hidden; we keep the IDs (safeSet above) for any other callers.
  const ovMarket = $('ovMarket');
  if (ovMarket) {
    ovMarket.textContent = fmtUsd(mv);
    ovMarket.className   = gainClass(mv);
  }
  const ovCost = $('ovCost');
  if (ovCost) {
    ovCost.textContent = fmtUsd(cb);
    ovCost.className   = 'gain-zero';
  }
  const ovTG = $('ovTodayGain');
  if (ovTG) {
    ovTG.textContent = (tg >= 0 ? '+' : '') + fmtUsd(tg);
    ovTG.className   = gainClass(tg);
  }
  // Realized Today reuses `rt` computed above (data.realized_today_dollar).
  const ovR = $('ovRealized');
  if (ovR) {
    ovR.textContent = rt != null ? (rt >= 0 ? '+' : '') + fmtUsd(rt) : '—';
    ovR.className   = rt != null ? gainClass(rt) : 'gain-zero';
  }
  // `cash_value` and `accounts` only exist on the global summary object, not on by_account entries
  const cash = Number(data.cash_value || 0);
  safeSet('kpiCash', fmtUsd(cash));
  // Total = Market Value (investments ex-cash) + Cash
  const total = mv + cash;
  safeSet('kpiTotal', fmtUsd(total));
  safeSet('kpiPos', data.positions || 0);
  safeSet('kpiAccts', data.accounts
    ? data.accounts + ' account' + (data.accounts === 1 ? '' : 's')
    : '');

  // Mirror Cash + Total into the Account Value chart header
  const ovCashEl = $('ovCash');
  if (ovCashEl) {
    ovCashEl.textContent = fmtUsd(cash);
    ovCashEl.className   = 'gain-zero';
  }
  const ovTotalEl = $('ovTotal');
  if (ovTotalEl) {
    ovTotalEl.textContent = fmtUsd(total);
    ovTotalEl.className   = 'gain-zero';
  }
}

function updateKpiTiles() {
  // Dispatch KPI tile rendering based on current filter state.
  // If a specific account is selected, show that account's data.
  // If a source is selected (but no account), aggregate all accounts for that source.
  // Otherwise, show global totals.
  const s = state.summary;
  if (!s) return;

  const selectedAcct = state.filters.account;
  const selectedSrc  = state.filters.source;

  // Apply latestSummary override to the global before dispatching
  const s_eff = effectiveSummary(s);

  // When Latest is on, state.latestSummary already represents the
  // currently-displayed grid (per recomputeLatestSummary using
  // state.filtered). Render that directly; don't reach into the
  // un-overridden by_account or source-aggregate values.
  if (state.filters && state.filters.latestPrices) {
    renderKpiTiles(s_eff);
    return;
  }

  if (selectedAcct) {
    // Specific account selected: find its by_account entry.
    // Same account name can exist in both F and CS (e.g. cross-broker
    // accounts), so when a source filter is also active, match on
    // (source, account) — otherwise the first matching entry could
    // be from the wrong side (CS sorts before F, so an F-only filter
    // would silently get the CS row with $0 cost_basis).
    const matchAcct = (a) => {
      if (a.account !== selectedAcct) return false;
      if (!selectedSrc) return true;
      return (a.source || '').toUpperCase() === selectedSrc.toUpperCase();
    };
    const entry = (s.by_account || []).find(matchAcct);
    renderKpiTiles(entry || s);
  } else if (selectedSrc) {
    // Source selected but no specific account: aggregate all accounts for that source
    const matching = (s.by_account || []).filter(a =>
      (a.source || '').toUpperCase() === selectedSrc.toUpperCase()
    );
    if (matching.length) {
      // Compute aggregate from by_account entries
      const agg = matching.reduce((acc, a) => {
        acc.market_value          += Number(a.market_value          || 0);
        acc.today_gain_dollar     += Number(a.today_gain_dollar     || 0);
        acc.day_change_dollar     += Number(a.day_change_dollar     || 0);
        acc.realized_today_dollar += Number(a.realized_today_dollar || 0);
        acc.ytd_gain_dollar       += Number(a.ytd_gain_dollar       || 0);
        acc.mtd_gain_dollar       += Number(a.mtd_gain_dollar       || 0);
        acc.cost_basis            += Number(a.cost_basis            || 0);
        acc.cash_value            += Number(a.cash_value            || 0);
        acc.positions             += Number(a.positions             || 0);
        return acc;
      }, {
        market_value: 0,
        today_gain_dollar: 0,
        day_change_dollar: 0,
        realized_today_dollar: 0,
        ytd_gain_dollar: 0,
        mtd_gain_dollar: 0,
        cost_basis: 0,
        cash_value: 0,
        positions: 0,
      });

      // Recompute today_gain_pct from aggregated values (avoid averaging percentages incorrectly)
      const denom = agg.market_value - agg.today_gain_dollar;
      agg.today_gain_pct = denom ? (agg.today_gain_dollar / denom * 100) : null;

      renderKpiTiles(agg);
    } else {
      renderKpiTiles(s_eff);
    }
  } else {
    // All accounts, all sources: use global summary totals
    // (s_eff layers latestSummary overrides on top of s when toggle is on)
    renderKpiTiles(s_eff);
  }
}

// ---- KPI summary ----
async function loadSummary() {
  try {
    const s = await fetchJson('/api/portfolio/summary?date=' + state.date);
    state.summary = s;  // Cache for filter updates

    // Update snapshot label
    const safeSet = (id, text) => {
      const el = $(id);
      if (el) el.textContent = text;
    };
    safeSet('snapshotLabel', 'snapshot ' + (s.as_of_date || state.date));

    // Render KPI tiles using current filter state
    updateKpiTiles();

    // Render limit chips and warnings
    renderLimitChips(s);
    window.warnBadge?.clearPage();

    // By-account breakdown table (always shows all accounts, independent of filters)
    const byAcct = Array.isArray(s.by_account) ? s.by_account : [];
    const acctWrap = $('kpiByAccount');
    const acctBody = $('kpiByAccountBody');
    const acctToggle = $('acctToggle');
    if (byAcct.length) {
      acctBody.innerHTML = byAcct.map(a => {
        const ytdA = Number(a.ytd_gain_dollar || 0);
        const mtdA = Number(a.mtd_gain_dollar || 0);
        const tdA = Number(a.today_gain_dollar || 0);
        const tdPct = Number(a.today_gain_pct || 0);
        const mv = Number(a.market_value || 0);
        const cash = Number(a.cash_value || 0);
        const tot = mv + cash;
        const acctInfo = state.accountMap[a.account] || null;
        const acctTag = acctInfo ? getAccountTag(acctInfo.num, acctInfo.source) : getAccountTag('?', '?');
        return `<tr style="border-top:1px solid #eee;">
          <td style="padding:4px 8px;"><span style="display:inline-block; padding:4px 8px; border-radius:4px; background:${acctTag.bgColor}; color:${acctTag.fgColor}; font-weight:600; font-size:11px;">${acctTag.tag}</span> ${escapeHtml(a.account || '').slice(0, 35)}</td>
          <td style="padding:4px 8px; text-align:center;"><div style="height:24px; width:80px; display:inline-block; position:relative;"><canvas data-spark-acct="${escapeHtml(a.account || '')}"></canvas></div></td>
          <td style="padding:4px 8px; text-align:right;">${fmtUsd(tot)}</td>
          <td style="padding:4px 8px; text-align:right;">${fmtUsd(cash)}</td>
          <td style="padding:4px 8px; text-align:right;">${fmtUsd(mv)}</td>
          <td style="padding:4px 8px; text-align:right;" class="${gainClass(tdA)}">${tdA >= 0 ? '+$' : '-$'}${Math.abs(tdA).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
          <td style="padding:4px 8px; text-align:right;" class="${gainClass(tdPct)}">${tdPct != null ? fmtPct(tdPct) : ''}</td>
          <td style="padding:4px 8px; text-align:right;" class="${gainClass(ytdA)}">${ytdA >= 0 ? '+' : ''}${fmtUsd(ytdA)}</td>
          <td style="padding:4px 8px; text-align:right;" class="${gainClass(mtdA)}">${mtdA >= 0 ? '+' : ''}${fmtUsd(mtdA)}</td>
          <td style="padding:4px 8px; text-align:right;">${fmtUsd(a.cost_basis)}</td>
          <td style="padding:4px 8px; text-align:right;">${a.positions || 0}</td>
        </tr>`;
      }).join('');
      acctWrap.style.display = state.accountExpanded ? 'block' : 'none';
      acctToggle.style.display = 'block';
    } else {
      acctWrap.style.display = 'none';
      acctToggle.style.display = 'none';
    }
  } catch (e) {
    showStatus('Failed to load summary: ' + e.message, 'error');
  }
}

// ---- main portfolio load ----
async function loadPortfolio() {
  if (!state.date) return;
  const params = new URLSearchParams({ date: state.date });
  if (state.filters.source) params.append('source', state.filters.source);
  if (state.filters.consolidated) params.append('consolidated', 'true');
  if (state.filters.latestPrices) params.append('latest_prices', 'true');
  try {
    const rows = await fetchJson('/api/portfolio?' + params.toString());
    state.rows = Array.isArray(rows) ? rows : [];
    buildAccountMap();
    refreshAccountFilter();
    applyClientFilter();
    // recomputeLatestSummary must run AFTER applyClientFilter so it
    // sees the freshly-filtered rows (the grid's actual contents).
    recomputeLatestSummary();
  } catch (e) {
    showStatus('Failed to load portfolio: ' + e.message, 'error');
  }
}

function refreshAccountFilter() {
  const sel = $('acctFilter');
  const cur = sel.value;
  const opts = new Set();
  for (const r of state.rows) {
    if (r.account && r.account !== 'ALL') opts.add(r.account);
  }
  sel.innerHTML = '<option value="">All</option>';
  for (const a of Array.from(opts).sort()) {
    const o = document.createElement('option');
    o.value = a; o.textContent = a;
    if (a === cur) o.selected = true;
    sel.appendChild(o);
  }
}

function renderLimitChips(summary) {
  const wrap = document.getElementById('limitChips');
  if (!wrap) return;
  const above = summary.above_max || 0;
  const below = summary.below_min || 0;
  const floor = summary.at_floor  || 0;
  const totalFlagged = above + below + floor;
  if (!totalFlagged) { wrap.innerHTML = ''; return; }
  const cur = state.filters.limitStatus;
  const chip = (kind, label, count, cls) =>
    `<span class="kpi-chip ${cls} ${cur === kind ? 'active' : ''}" data-kind="${kind}">
       <span>${label}</span><span class="ct">${count}</span>
     </span>`;
  wrap.innerHTML =
    `<span class="kpi-chip ${!cur ? 'active' : ''}" data-kind="all">
       <span>Show all</span>
     </span>` +
    chip('ABOVE_MAX', 'Above max', above, 'above-max') +
    chip('BELOW_MIN', 'Below min', below, 'below-min') +
    chip('AT_FLOOR',  'At floor',  floor, 'at-floor');
  wrap.querySelectorAll('.kpi-chip').forEach(el => {
    el.onclick = () => {
      const k = el.dataset.kind;
      if (k === 'all') {
        state.filters.limitStatus = '';
      } else {
        state.filters.limitStatus = (state.filters.limitStatus === k) ? '' : k;
      }
      renderLimitChips(summary);
      applyClientFilter();
    };
  });
}

function buildAccountMap() {
  const seen = new Set();
  const list = [];
  for (const r of state.rows) {
    if (r.account && !seen.has(r.account)) {
      seen.add(r.account);
      list.push(r.account);
    }
  }
  list.sort();
  state.accountList = list;
  state.accountMap = {};

  // Build per-source numbering (C1, C2, C3, C4 for CS; F1 for F)
  const csList = [];
  const fList = [];
  for (const acc of list) {
    // Find source by checking rows
    const row = state.rows.find(r => r.account === acc);
    if (row) {
      const src = (row.source || '').toUpperCase();
      if (src === 'CS' || src.includes('SCHWAB') || src.includes('CHARLES')) {
        csList.push(acc);
      } else if (src === 'F' || src.includes('FIDELITY')) {
        fList.push(acc);
      }
    }
  }

  // Map accounts to per-source numbers
  for (let i = 0; i < csList.length; i++) {
    state.accountMap[csList[i]] = { source: 'CS', num: i + 1 };
  }
  for (let i = 0; i < fList.length; i++) {
    state.accountMap[fList[i]] = { source: 'F', num: i + 1 };
  }
}

function applyClientFilter() {
  const q = (state.filters.search || '').toLowerCase().trim();
  state.filtered = state.rows.filter(r => {
    if (q && !(`${r.symbol || ''} ${r.description || ''}`).toLowerCase().includes(q)) return false;
    if (state.filters.account && r.account !== state.filters.account) return false;
    if (state.filters.limitStatus && r.limit_status !== state.filters.limitStatus) return false;
    return true;
  });
  applySort();              // apply current sort so the visible order matches the indicator
  renderGrid();
  updateSortIndicators();   // initial load needs this so the default ▲ appears on Symbol

  // Latest-prices override depends on what is currently shown.
  if (state.filters && state.filters.latestPrices) {
    recomputeLatestSummary();
    if (typeof updateKpiTiles === 'function') updateKpiTiles();
  }
}

function getAccountTag(accountNum, source) {
  const tagColors = {
    'C1-bg': '#d9e8f5',
    'C2-bg': '#e8d9f5',
    'C3-bg': '#f5f0d9',
    'C4-bg': '#f5d9e8',
    'F1-bg': '#d9f0f5'
  };

  const src = (source || '').trim().toUpperCase();
  let tag = '?';

  // Determine prefix based on source
  let prefix = '?';
  if (src === 'CS' || src === 'C' || src.includes('SCHWAB') || src.includes('CHARLES')) {
    prefix = 'C';
  } else if (src === 'F' || src.includes('FIDELITY')) {
    prefix = 'F';
  }

  // Create tag: e.g., "C1", "C2", "F1"
  if (prefix !== '?') {
    tag = prefix + accountNum;
  }

  const bgColor = tagColors[tag + '-bg'] || '#e8e8e8';
  const fgColor = '#333';
  return { tag, bgColor, fgColor };
}

function applySort() {
  // Sort state.filtered in place using state.sort.{column,direction}.
  // Called from both applyClientFilter (initial load + filter change)
  // and sortRows (user clicked a header).
  const col = state.sort.column;
  const dir = state.sort.direction;
  state.filtered.sort((a, b) => {
    let aVal = a[col];
    let bVal = b[col];
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return dir === 'asc' ? 1 : -1;
    if (bVal == null) return dir === 'asc' ? -1 : 1;
    if (typeof aVal === 'string' && !isNaN(aVal)) aVal = Number(aVal);
    if (typeof bVal === 'string' && !isNaN(bVal)) bVal = Number(bVal);
    let cmp = 0;
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      cmp = aVal - bVal;
    } else {
      cmp = String(aVal).localeCompare(String(bVal));
    }
    return dir === 'asc' ? cmp : -cmp;
  });
}

function sortRows(column) {
  // Toggle direction if clicking same column, otherwise set to asc
  if (state.sort.column === column) {
    state.sort.direction = state.sort.direction === 'asc' ? 'desc' : 'asc';
  } else {
    state.sort.column = column;
    state.sort.direction = 'asc';
  }
  applySort();
  renderGrid();
  updateSortIndicators();
}

function updateSortIndicators() {
  // Update all header indicators
  document.querySelectorAll('[data-sort-col]').forEach(th => {
    const col = th.getAttribute('data-sort-col');
    const indicator = th.querySelector('.sort-indicator');
    if (!indicator) return;

    if (col === state.sort.column) {
      indicator.textContent = state.sort.direction === 'asc' ? ' ▲' : ' ▼';
      indicator.style.opacity = '1';
    } else {
      indicator.textContent = '';
      indicator.style.opacity = '0.3';
    }
  });
}

function renderGrid() {
  const tb = $('pfBody');
  tb.innerHTML = '';
  $('rowCount').textContent = `${state.filtered.length} of ${state.rows.length}`;
  $('emptyState').style.display = state.filtered.length === 0 ? 'block' : 'none';

  // Find max abs pct for bar scaling
  const pctVals = state.filtered.map(r => Math.abs(Number(r.total_gain_pct) || 0));
  const maxPct = Math.max(20, Math.max.apply(null, pctVals.length ? pctVals : [20]));

  for (const r of state.filtered) {
    const tr = document.createElement('tr');
    const action = (r.consolidated_action || '').toUpperCase();
    const todayCls = gainClass(r.today_gain_dollar);
    const totalCls = gainClass(r.total_gain_dollar);
    const totalPct = Number(r.total_gain_pct) || 0;
    const barW = Math.min(100, (Math.abs(totalPct) / maxPct) * 100);

    const ytdCls  = gainClass(r.ytd_gain_dollar);
    const mtdCls  = gainClass(r.mtd_gain_dollar);
    const acctInfo = r.account ? state.accountMap[r.account] : null;
    const acctTag = acctInfo ? getAccountTag(acctInfo.num, acctInfo.source) : getAccountTag('?', '?');
    tr.innerHTML = `
      <td style="text-align:center; padding:8px 4px;"><span style="display:inline-block; padding:4px 8px; border-radius:4px; background:${acctTag.bgColor}; color:${acctTag.fgColor}; font-weight:600; font-size:12px;">${acctTag.tag}</span></td>
      <td>${typeof yahooLink === 'function' ? yahooLink(r.symbol) : ''}<strong><span class="tv-sym-link" data-sym="${escapeHtml(r.symbol)}" data-desc="${(r.description||'').replace(/"/g,'&quot;')}" onclick="event.stopPropagation(); _portSymClick(this)">${escapeHtml(r.symbol)}</span></strong> <button onclick="event.stopPropagation(); openPortfolioModal('${r.symbol}')" style="background:none; border:none; color:var(--text-3); cursor:pointer; font-size:11px; padding:0 2px;" title="Detail">☰</button></td>
      <td title="${escapeHtml(r.description || '')}">${escapeHtml((r.description || '').slice(0, 32))}</td>
      <td class="num">${fmtNum(r.qty, 2)}</td>
      <td class="num">${r.avg_cost != null ? '$' + Number(r.avg_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : ''}</td>
      <td class="num">${r.last_price != null ? '$' + Number(r.last_price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : ''}</td>
      <td class="num"><strong>${fmtUsd(r.market_value)}</strong></td>
      <td class="num">${fmtUsd(r.cost_basis)}</td>
      <td class="num ${todayCls}">${r.today_gain_dollar != null ? (Number(r.today_gain_dollar) >= 0 ? '+$' : '-$') + Math.abs(Number(r.today_gain_dollar)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : ''}</td>
      <td class="num ${todayCls}">${fmtPct(r.today_gain_pct)}</td>
      <td class="num ${totalCls}">${r.total_gain_dollar != null ? (Number(r.total_gain_dollar) >= 0 ? '+' : '') + fmtUsd(r.total_gain_dollar) : ''}</td>
      <td class="num gain-cell ${totalCls === 'gain-pos' ? 'pos' : (totalCls === 'gain-neg' ? 'neg' : '')}">
        <div class="pct-bar" style="width:${barW}%"></div>
        <span class="val ${totalCls}">${fmtPct(r.total_gain_pct)}</span>
      </td>
      <td class="num">${r.pct_of_tp != null ? Number(r.pct_of_tp).toFixed(1) + '%' : ''}</td>
      <td>${escapeHtml(r.sector || '')}</td>
      <td>${action ? `<span class="badge-action badge-action-${action}">${action}</span>` : ''}</td>
      <td class="num" style="border-left: 4px solid ${(() => {
        const ls = r.limit_status || 'NO_LIMIT';
        const colors = {
          'WITHIN': '#2f9e2f',
          'BELOW_MIN': '#e07c1a',
          'ABOVE_MAX': '#d83a3a',
          'AT_FLOOR': '#1f7af2',
          'NO_LIMIT': '#aaa'
        };
        return colors[ls] || '#aaa';
      })()};">${(r.limit_min != null || r.limit_max != null) ? fmtUsd(r.limit_min) + '–' + fmtUsd(r.limit_max) : ''}</td>
    `;
    tr.onclick = () => openDrilldown(r);
    tb.appendChild(tr);
  }

  // Update sort indicators after rendering
  updateSortIndicators();
}

function showStatus(msg, kind = 'info', timeout = 4000) {
  const el = $('statusBar');
  el.className = 'status-bar ' + kind;
  el.textContent = msg;
  if (timeout) setTimeout(() => { el.style.display = 'none'; }, timeout);
}

// ---- drilldown ----
async function openDrilldown(row) {
  $('modalTitle').textContent = row.symbol;
  $('modalName').textContent = row.description || '';
  $('modalSub').textContent = [`as of ${row.snapshot_date || state.date}`, row.account, row.sector].filter(Boolean).join(' · ');

  // Mini KPIs from current row
  const kpis = [
    ['Qty',           fmtNum(row.qty, 2)],
    ['Avg Cost',      row.avg_cost != null ? '$' + Number(row.avg_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'],
    ['Last Price',    row.last_price != null ? '$' + Number(row.last_price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'],
    ['Market Value',  fmtUsd(row.market_value)],
    ['Today',         (row.today_gain_dollar != null ? (row.today_gain_dollar >= 0 ? '+' : '') + fmtUsd(row.today_gain_dollar) : '—') + ' ' + (fmtPct(row.today_gain_pct) || '')],
    ['Total',         (row.total_gain_dollar != null ? (row.total_gain_dollar >= 0 ? '+' : '') + fmtUsd(row.total_gain_dollar) : '—') + ' ' + (fmtPct(row.total_gain_pct) || '')],
    ['Cost Basis',    fmtUsd(row.cost_basis)],
  ];
  $('modalKpis').innerHTML = kpis.map(([l, v]) =>
    `<div class="mini-kpi"><div class="lbl">${l}</div><div class="val ${gainClass(v.startsWith('+') ? 1 : v.startsWith('-') ? -1 : 0)}">${escapeHtml(v)}</div></div>`
  ).join('');
  // Append a Position Limits summary block
  if (row.applied_category || row.limit_min != null || row.limit_max != null) {
    const ls = row.limit_status || 'NO_LIMIT';
    const limitHTML = `
      <div class="mini-kpi"><div class="lbl">Category</div><div class="val">${escapeHtml(row.applied_category || '—')}</div></div>
      <div class="mini-kpi"><div class="lbl">Min</div><div class="val">${fmtUsd(row.limit_min) || '—'}</div></div>
      <div class="mini-kpi"><div class="lbl">Max</div><div class="val">${fmtUsd(row.limit_max) || '—'}</div></div>
      <div class="mini-kpi"><div class="lbl">Units</div><div class="val">${fmtUsd(row.limit_units) || '—'}</div></div>
      <div class="mini-kpi"><div class="lbl">Status</div><div class="val"><span class="badge-limit badge-limit-${ls}">${ls.replace('_',' ')}</span></div></div>
    `;
    $('modalKpis').innerHTML += limitHTML;
  }


  $('modalBackdrop').classList.add('open');

  // Fetch detail bundle
  let detail = null;
  try {
    detail = await fetchJson(`/api/portfolio/${encodeURIComponent(row.symbol)}`);
  } catch (e) {
    showStatus('Failed to load detail: ' + e.message, 'error');
    return;
  }

  renderChart(detail.timeseries || []);
  renderTimeline(detail.legs || [], detail.user_actions || [], detail.recommendation_history || []);
}

function renderChart(ts) {
  const ctx = document.getElementById('pfChart').getContext('2d');
  if (state.chart) { state.chart.destroy(); state.chart = null; }
  const labels = ts.map(p => (p.snapshot_date || '').toString().slice(0, 10));
  const mv     = ts.map(p => Number(p.market_value) || 0);
  const tg     = ts.map(p => Number(p.total_gain_dollar) || 0);
  state.chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        { label: 'Market Value', data: mv, borderColor: '#1f7af2', backgroundColor: 'rgba(31,122,242,0.10)', borderWidth: 2, tension: 0.25, fill: true, yAxisID: 'y' },
        { label: 'Total Gain $', data: tg, borderColor: '#2f9e2f', backgroundColor: 'rgba(47,158,47,0.06)', borderWidth: 2, tension: 0.25, fill: false, yAxisID: 'y1' },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      stacked: false,
      scales: {
        y:  { type: 'linear', position: 'left',  title: { display: true, text: 'Market Value ($)' } },
        y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Total Gain ($)' } },
      },
      plugins: { legend: { display: false } },
    },
  });
}


function renderTimeline(legs, actions, recs) {
  const events = [];
  for (const l of legs) {
    if (!l.qty_diff) continue;
    const closed = (l.final_status || '').toUpperCase() === 'CLOSED';
    const action = Number(l.qty_diff) > 0 ? 'Added' : 'Reduced';
    events.push({
      when: (l.snapshot_date || '').toString().slice(0,10),
      kind: 'leg' + (closed ? ' close' : ''),
      title: `${action} ${Math.abs(Number(l.qty_diff)).toFixed(2)} sh (${l.source}/${l.account})`,
      meta: `leg ${l.leg_id ?? '?'} • ${l.leg_status || ''}${l.leg_pl ? ' • leg P/L ' + fmtUsd(l.leg_pl) : ''}`,
    });
  }
  for (const a of actions) {
    events.push({
      when: (a.acted_at || a.as_of_date || '').toString().slice(0,19).replace('T',' '),
      kind: 'user',
      title: `You: ${a.user_action || ''}${a.user_action_target ? ' → ' + a.user_action_target : ''}`,
      meta:  `system said ${a.consolidated_action || '—'} (src ${a.winning_source || '—'})${a.user_notes ? ' • ' + a.user_notes : ''}`,
    });
  }
  // sort newest first
  events.sort((x, y) => (y.when || '').localeCompare(x.when || ''));
  const wrap = $('modalTimeline');
  if (!wrap) return;
  if (!events.length) {
    wrap.innerHTML = '<div class="empty-mini">No leg events or decisions yet.</div>';
    return;
  }
  wrap.innerHTML = events.slice(0, 80).map(e => `
    <div class="timeline-item ${e.kind}">
      <div><span class="timeline-when">${escapeHtml(e.when)}</span> · ${escapeHtml(e.title)}</div>
      <div class="timeline-meta">${escapeHtml(e.meta)}</div>
    </div>
  `).join('');
}

// ---- wire up ----
console.log('Portfolio.js loaded');
document.addEventListener('DOMContentLoaded', async () => {
  console.log('DOMContentLoaded fired');
  await loadDates();

  $('datePicker').addEventListener('change', async (e) => {
    state.date = e.target.value;
    await Promise.all([loadSummary(), loadPortfolio()]);
    loadTrends();
  });
  $('refreshBtn').addEventListener('click', async () => {
    await Promise.all([loadSummary(), loadPortfolio()]);
    loadTrends();
  });

  $('srcFilter').addEventListener('change', e => {
    state.filters.source = e.target.value;
    state.filters.account = '';  // Reset account selection when source changes
    updateKpiTiles();
    loadPortfolio();
    loadTrends();
  });
  $('acctFilter').addEventListener('change', e => {
    state.filters.account = e.target.value;
    updateKpiTiles();
    applyClientFilter();
    loadTrends();
  });
  $('consolidated').addEventListener('change', e => { state.filters.consolidated = e.target.checked; loadPortfolio(); });
  $('exportCsvBtn')?.addEventListener('click', exportPositionsCsv);
  $('latestPrices').addEventListener('change', e => {
    state.filters.latestPrices = e.target.checked;
    try { localStorage.setItem('pf_latest_prices', e.target.checked ? '1' : '0'); } catch (_) {}
    loadPortfolio().then(() => {
      updateKpiTiles();
      // Re-render the Trends panel so the Cum overlay + rightmost bar pick
      // up the new state.latestSummary (or revert if toggle just turned off).
      if (_lastTrendData) {
        try { renderTrendCharts(_lastTrendData); } catch (_) {}
      }
    });
  });
  $('symSearch').addEventListener('input', e => { state.filters.search = e.target.value; applyClientFilter(); });

  $('acctToggle').addEventListener('click', () => {
    state.accountExpanded = !state.accountExpanded;
    $('kpiByAccount').style.display = state.accountExpanded ? 'block' : 'none';
    $('acctToggle').textContent = (state.accountExpanded ? '▼' : '▶') + ' Account breakdown';
  });

  $('modalClose').addEventListener('click', () => $('modalBackdrop').classList.remove('open'));
  $('modalBackdrop').addEventListener('click', (e) => {
    if (e.target === $('modalBackdrop')) $('modalBackdrop').classList.remove('open');
  });

  // Add sort listeners to table headers
  document.querySelectorAll('table.pf-grid [data-sort-col]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.getAttribute('data-sort-col');
      sortRows(col);
    });
  });

  // Restore Use-latest-prices preference
  try {
    const stored = localStorage.getItem('pf_latest_prices') === '1';
    state.filters.latestPrices = stored;
    const cb = $('latestPrices'); if (cb) cb.checked = stored;
  } catch (_) {}

  await Promise.all([loadSummary(), loadPortfolio(), loadSnapshotStatus()]);
  loadTrends();
  $('trendsPeriod')?.addEventListener('change', loadTrends);

  // Trend card clicks → popup modal
  document.querySelectorAll('.trend-card').forEach(card => {
    card.addEventListener('click', () => {
      const key   = card.getAttribute('data-trend-key');
      const title = card.getAttribute('data-trend-title') || 'Chart';
      openTrendModal(key, title);
    });
  });

  // Sparkline clicks (delegated — rows render after init) → popup modal for that account
  document.addEventListener('click', (ev) => {
    const c = ev.target.closest('canvas[data-spark-acct]');
    if (!c) return;
    ev.stopPropagation();
    const acct = c.getAttribute('data-spark-acct');
    openTrendModal('account', acct + ' — Market Value');
  });

  // Modal close handlers
  $('trendModalClose')?.addEventListener('click', closeTrendModal);
  $('trendModalBackdrop')?.addEventListener('click', (ev) => {
    if (ev.target.id === 'trendModalBackdrop') closeTrendModal();
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') closeTrendModal();
  });

  // Pre-populate the Realized account dropdown on page load so it's already
  // filled before the user clicks into the tab. (Tab-activation also calls
  // this, but pre-loading covers the case where the user lands directly on
  // Realized via hash, or where the auto-load on click hits an error.)
  loadRealizedAccounts().catch(e => console.warn('preload accounts:', e));

  // -------- Tab switching (Positions / Activity / Realized) --------
  // Activity + Realized panes load lazily on first activation so the
  // Positions tab opens fast.
  const _loadedTabs = new Set(['positions']);
  document.querySelectorAll('.pf-tab-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const tab = btn.getAttribute('data-pf-tab');
      document.querySelectorAll('.pf-tab-btn').forEach(b => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.pf-tab-pane').forEach(p => p.classList.toggle('active', p.id === `pf-pane-${tab}`));
      $('pfTabHint').textContent = ({
        positions: 'Snapshot positions (hist_cs / hist_f)',
        realized:  'Realized gains + transactions feed',
      })[tab] || '';
      if (tab === 'realized' && !_loadedTabs.has('realized')) {
        _loadedTabs.add('realized');
        await loadRealizedAccounts();
        await loadRealized();
        await loadActivity();
      }
    });
  });

  // Shared (Realized + Activity) filter wiring.
  // Any change to a Realized filter refreshes both grids; Group-by only
  // affects the Realized grid; Kind only affects the Activity grid.
  const _reloadBoth = () => { loadRealized(); loadActivity(); };
  ['realSrcFilter','realAccountFilter','realDatePreset','realFromDate','realToDate']
    .forEach(id => { const el = $(id); if (el) el.addEventListener('change', _reloadBoth); });
  $('realGroupBy')?.addEventListener('change', loadRealized);
  $('realSymFilter')?.addEventListener('change', _reloadBoth);
  $('realSymFilter')?.addEventListener('input', _debounce(_reloadBoth, 300));
  $('actKindFilter')?.addEventListener('change', loadActivity);
});

// ---- helpers shared by new tabs ----
function _debounce(fn, ms) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// ---- snapshot staleness banner ----
async function loadSnapshotStatus() {
  const banner = $('snapshotStatusBanner');
  if (!banner) return;
  try {
    const resp = await fetchJson('/api/portfolio/snapshot-status');
    // API now returns { rows, last_activity_date, activity_today,
    //                   last_realized_date, realized_today }.
    // Tolerate the older array-only shape for forward-compat.
    const rows = Array.isArray(resp) ? resp : (resp && resp.rows) || [];
    const meta = Array.isArray(resp) ? {} : (resp || {});

    // ─── Per-tab default period (Activity & Realized) ─────────────────
    // Each tab checks its own data source. If today has rows there, leave
    // the dropdown at Today. Otherwise switch to Custom with from/to set
    // to the latest available date for THAT tab's data.
    try {
        // Activity tab → hist_cst (transactions)
        if (!meta.activity_today && meta.last_activity_date) {
            const aw = $('actWindow');
            if (aw) aw.value = 'custom';
            const af = $('actFromDate'); if (af) af.value = meta.last_activity_date;
            const at = $('actToDate');   if (at) at.value = meta.last_activity_date;
            const acw = $('actCustomDateWrap');
            if (acw) acw.style.display = 'inline-flex';
        }
        // Realized tab → drv_cs_realized_gain
        if (!meta.realized_today && meta.last_realized_date) {
            const rp = $('realDatePreset');
            if (rp) rp.value = 'custom';
            const rf = $('realFromDate'); if (rf) rf.value = meta.last_realized_date;
            const rt = $('realToDate');   if (rt) rt.value = meta.last_realized_date;
            const rcw = $('realCustomDateWrap');
            if (rcw) rcw.style.display = 'inline-flex';
        }
    } catch (_) { /* default-period setup is best-effort; never break stale banner */ }
    const stale = (rows || []).filter(r => Number(r.days_stale) >= 2);
    if (stale.length === 0) {
      banner.style.display = 'none';
      return;
    }
    const items = stale.map(r =>
      `<span style="margin-right:10px;">
         <strong>${escapeHtml(r.source)} ${escapeHtml(r.account)}:</strong>
         last snapshot ${escapeHtml(r.last_snapshot)} (${r.days_stale} days stale)
       </span>`).join('');
    banner.innerHTML =
      `<strong style="color:#5b4400;">Stale snapshots:</strong> ${items}` +
      `<span style="color:#666;"> &mdash; Activity / Realized tabs use transactions and are unaffected.</span>`;
    banner.style.display = 'block';
  } catch (e) {
    console.warn('snapshot-status failed', e);
    banner.style.display = 'none';
  }
}

// ---- Activity tab ----
async function loadActivity() {
  // Now sourced from the shared (Realized) filter bar — there is no
  // dedicated Activity filter bar anymore. Kind filter sits on its own
  // sub-bar between the two grids.
  const body = $('actBody');
  const empty = $('actEmpty');
  if (!body) return;
  const params = new URLSearchParams();
  // Date window: read the Realized preset + custom inputs.
  const preset = $('realDatePreset')?.value || 'today';
  const range = _realPresetRange(preset);
  if (range.from) params.set('from', range.from);
  if (range.to)   params.set('to',   range.to);
  if ($('realSrcFilter')?.value)     params.set('source',  $('realSrcFilter').value);
  if ($('realAccountFilter')?.value) params.set('account', $('realAccountFilter').value);
  if ($('realSymFilter')?.value)     params.set('symbol',  $('realSymFilter').value.trim().toUpperCase());
  if ($('actKindFilter')?.value)     params.set('kind',    $('actKindFilter').value);
  params.set('limit', '1000');

  body.innerHTML = '<tr><td colspan="10" style="padding:20px;text-align:center;color:#888;">Loading…</td></tr>';
  empty.style.display = 'none';
  let rows;
  try {
    rows = await fetchJson('/api/portfolio/activity?' + params.toString());
  } catch (e) {
    body.innerHTML = `<tr><td colspan="10" style="padding:20px;text-align:center;color:#b21f1f;">Error: ${escapeHtml(e.message)}</td></tr>`;
    return;
  }
  $('actRowCount').textContent = `${(rows||[]).length} rows`;
  if (!rows || rows.length === 0) {
    body.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  const kindColors = {
    BUY: '#dcfce7', SELL: '#fee2e2', DIV: '#dbeafe',
    INT: '#e0e7ff', CASH: '#f3f4f6', OTHER: '#fef3c7',
  };
  body.innerHTML = rows.map(r => {
    const kc = kindColors[r.action_kind] || '#fff';
    return `<tr>
      <td><span class="pill pill-${(r.source||'').toLowerCase()}">${escapeHtml(r.source||'')}</span></td>
      <td>${escapeHtml(r.trade_date||'')}</td>
      <td title="${escapeHtml(r.account||'')}">${escapeHtml((r.account||'').slice(0,30))}</td>
      <td><strong>${escapeHtml(r.symbol||'')}</strong></td>
      <td><span style="background:${kc};padding:1px 6px;border-radius:3px;font-weight:600;font-size:10px;">${escapeHtml(r.action_kind||'')}</span></td>
      <td title="${escapeHtml(r.action||'')}" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml((r.action||'').slice(0,60))}</td>
      <td class="num">${fmtNum(r.quantity, 4)}</td>
      <td class="num">${fmtUsd(r.price)}</td>
      <td class="num ${gainClass(r.amount)}">${fmtUsd(r.amount)}</td>
      <td class="num">${fmtUsd(r.fees)}</td>
    </tr>`;
  }).join('');
}

// ---- Realized tab ----
// Compute YYYY-MM-DD from a preset key.  Returns {from, to} (each may be null).
function _realPresetRange(preset) {
  const today = new Date();
  const ymd = (d) => d.toISOString().slice(0, 10);
  const tEnd = ymd(today);
  if (preset === 'today') {
    return { from: tEnd, to: tEnd };
  }
  if (preset === 'ytd') {
    return { from: `${today.getFullYear()}-01-01`, to: tEnd };
  }
  if (preset === 'mtd') {
    const m = String(today.getMonth() + 1).padStart(2, '0');
    return { from: `${today.getFullYear()}-${m}-01`, to: tEnd };
  }
  // Rolling windows: last30 / last90 / last180 / last365 / last1825.
  // Parse the number after 'last' so adding new options doesn't need code.
  if (preset.startsWith('last')) {
    const n = Number(preset.slice(4));
    if (Number.isFinite(n) && n > 0) {
      const d = new Date(today);
      d.setDate(d.getDate() - n);
      return { from: ymd(d), to: tEnd };
    }
  }
  if (preset === 'custom') {
    return { from: $('realFromDate')?.value || null, to: $('realToDate')?.value || null };
  }
  // 'all' or unrecognized
  return { from: null, to: null };
}

// Populate the Account dropdown.  Tries /api/portfolio/accounts?has_realized=true
// first; if that returns nothing (e.g. drv_realized_gain is empty for this DB),
// falls back to the union of all known accounts so the picker is never empty
// when accounts exist somewhere.
async function loadRealizedAccounts() {
  const sel = $('realAccountFilter');
  if (!sel) return;
  const prior = sel.value;
  const buildOpts = (rows) =>
    (rows || []).map(r => {
      const acct = r.account || '';
      const src  = r.source  || '';
      const label = src ? `[${src}] ${acct}` : acct;
      return `<option value="${escapeHtml(acct)}">${escapeHtml(label)}</option>`;
    }).join('');

  let rows = [];
  try {
    rows = await fetchJson('/api/portfolio/accounts?has_realized=true');
    if (!Array.isArray(rows) || rows.length === 0) {
      // Fall back to full account universe
      rows = await fetchJson('/api/portfolio/accounts?has_realized=false');
    }
  } catch (e) {
    console.error('loadRealizedAccounts failed:', e);
    try {
      rows = await fetchJson('/api/portfolio/accounts?has_realized=false');
    } catch (e2) {
      console.error('account-fallback also failed:', e2);
      rows = [];
    }
  }
  sel.innerHTML = '<option value="">All accounts</option>' + buildOpts(rows);
  if (prior) sel.value = prior;
  console.log(`[portfolio] loaded ${rows.length} accounts into Realized filter`);
}

async function loadRealized() {
  const groupBy = $('realGroupBy').value || 'symbol';
  const params = new URLSearchParams();
  params.set('group_by', groupBy);
  if ($('realSrcFilter').value) params.set('source', $('realSrcFilter').value);
  if ($('realSymFilter').value) params.set('symbol', $('realSymFilter').value.trim().toUpperCase());
  if ($('realAccountFilter')?.value) params.set('account', $('realAccountFilter').value);

  // Date preset → from/to.  Show/hide custom date inputs based on selection.
  const preset = $('realDatePreset')?.value || 'today';
  const wrap = $('realCustomDateWrap');
  if (wrap) wrap.style.display = (preset === 'custom') ? 'inline-flex' : 'none';
  const { from, to } = _realPresetRange(preset);
  if (from) params.set('from', from);
  if (to)   params.set('to',   to);

  // Build the table header based on groupBy
  const theadEl = $('realThead');
  const body    = $('realBody');
  const empty   = $('realEmpty');
  body.innerHTML = '<tr><td colspan="9" style="padding:20px;text-align:center;color:#888;">Loading…</td></tr>';
  empty.style.display = 'none';

  let rows;
  try {
    rows = await fetchJson('/api/portfolio/realized?' + params.toString());
  } catch (e) {
    body.innerHTML = `<tr><td colspan="9" style="padding:20px;text-align:center;color:#b21f1f;">Error: ${escapeHtml(e.message)}</td></tr>`;
    return;
  }

  // Roll up KPI tiles from the filtered response.  Works for both grouped
  // (symbol/account) and raw (sell-event) modes — schemas differ.
  // YTD/MTD always use the calendar boundaries vs today, regardless of the
  // date-range filter.
  const today = new Date();
  const ytdCut = `${today.getFullYear()}-01-01`;
  const mtdCut = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2,'0')}-01`;

  let totals;
  if (groupBy === 'none') {
    // Each row is a single sell event. Aggregate the realized_gain column.
    totals = (rows||[]).reduce((m, r) => {
      const g = Number(r.realized_gain || 0);
      m.all += g;
      if (r.is_long_term) m.lt += g; else m.st += g;
      const sd = r.sell_date || '';
      if (sd >= ytdCut) m.ytd += g;
      if (sd >= mtdCut) m.mtd += g;
      m.n   += 1;
      return m;
    }, {ytd:0,mtd:0,all:0,lt:0,st:0,n:0});
  } else {
    totals = (rows||[]).reduce((m, r) => {
      m.ytd += Number(r.ytd_realized||0);
      m.mtd += Number(r.mtd_realized||0);
      m.all += Number(r.total_realized||0);
      m.lt  += Number(r.long_term_gain||0);
      m.st  += Number(r.short_term_gain||0);
      m.n   += Number(r.n_sells||0);
      return m;
    }, {ytd:0,mtd:0,all:0,lt:0,st:0,n:0});
  }
  $('realKpiYtd').textContent = fmtUsd(totals.ytd);
  $('realKpiYtd').className   = 'kpi-value ' + gainClass(totals.ytd);
  $('realKpiMtd').textContent = fmtUsd(totals.mtd);
  $('realKpiMtd').className   = 'kpi-value ' + gainClass(totals.mtd);
  $('realKpiAll').textContent = fmtUsd(totals.all);
  $('realKpiAll').className   = 'kpi-value ' + gainClass(totals.all);
  $('realKpiLT').textContent  = fmtUsd(totals.lt);
  $('realKpiLT').className    = 'kpi-value ' + gainClass(totals.lt);
  $('realKpiST').textContent  = fmtUsd(totals.st);
  $('realKpiST').className    = 'kpi-value ' + gainClass(totals.st);
  $('realKpiN').textContent   = String(totals.n);

  // Sub-line under "Total Realized" describes the active filter scope so the
  // user knows what these numbers reflect.
  const sub = [];
  if ($('realSrcFilter').value)      sub.push($('realSrcFilter').value);
  if ($('realAccountFilter')?.value) sub.push($('realAccountFilter').value);
  if ($('realSymFilter').value)      sub.push($('realSymFilter').value.trim().toUpperCase());
  if (from || to) sub.push(`${from || '…'} → ${to || 'today'}`);
  const subEl = $('realKpiAllSub');
  if (subEl) subEl.textContent = sub.length ? sub.join(' • ') : 'all accounts • all time';

  $('realRowCount').textContent = `${(rows||[]).length} rows`;
  if (!rows || rows.length === 0) {
    body.innerHTML = '';
    theadEl.innerHTML = '';
    empty.style.display = 'block';
    return;
  }

  if (groupBy === 'none') {
    theadEl.innerHTML = `<tr>
      <th>Sell Date</th><th>Src</th><th>Account</th><th>Symbol</th>
      <th class="num">Shares</th><th class="num">Proceeds</th>
      <th class="num">Cost</th>
      <th class="num">Realized</th>
      <th class="num">%</th><th class="num">Hold (d)</th><th>LT?</th>
    </tr>`;
    body.innerHTML = rows.map(r => `<tr>
      <td>${escapeHtml(r.sell_date||'')}</td>
      <td><span class="pill pill-${(r.source||'').toLowerCase()}">${escapeHtml(r.source||'')}</span></td>
      <td title="${escapeHtml(r.account||'')}">${escapeHtml((r.account||'').slice(0,28))}</td>
      <td><strong>${escapeHtml(r.symbol||'')}</strong></td>
      <td class="num">${fmtNum(r.shares_sold, 4)}</td>
      <td class="num">${fmtUsd(r.sell_proceeds)}</td>
      <td class="num">${fmtUsd(r.cost_basis)}</td>
      <td class="num ${gainClass(r.realized_gain)}">${fmtUsd(r.realized_gain)}</td>
      <td class="num ${gainClass(r.realized_gain_pct)}">${fmtPct(r.realized_gain_pct)}</td>
      <td class="num">${fmtNum(r.holding_days_avg, 0)}</td>
      <td>${r.is_long_term ? '✓' : ''}</td>
    </tr>`).join('');
  } else {
    const label = groupBy === 'symbol' ? 'Symbol' : 'Account';
    theadEl.innerHTML = `<tr>
      <th>${label}</th>
      <th class="num">Sells</th>
      <th class="num">Shares</th>
      <th class="num">Proceeds</th>
      <th class="num">Cost</th>
      <th class="num">Realized</th>
      <th class="num">YTD</th>
      <th class="num">MTD</th>
      <th class="num">LT $</th>
      <th class="num">ST $</th>
      <th>First → Last</th>
    </tr>`;
    body.innerHTML = rows.map(r => `<tr>
      <td><strong>${escapeHtml(r.bucket||'')}</strong></td>
      <td class="num">${r.n_sells||0}</td>
      <td class="num">${fmtNum(r.total_shares, 4)}</td>
      <td class="num">${fmtUsd(r.total_proceeds)}</td>
      <td class="num">${fmtUsd(r.total_cost)}</td>
      <td class="num ${gainClass(r.total_realized)}">${fmtUsd(r.total_realized)}</td>
      <td class="num ${gainClass(r.ytd_realized)}">${fmtUsd(r.ytd_realized)}</td>
      <td class="num ${gainClass(r.mtd_realized)}">${fmtUsd(r.mtd_realized)}</td>
      <td class="num ${gainClass(r.long_term_gain)}">${fmtUsd(r.long_term_gain)}</td>
      <td class="num ${gainClass(r.short_term_gain)}">${fmtUsd(r.short_term_gain)}</td>
      <td>${escapeHtml(r.first_sell||'')} → ${escapeHtml(r.last_sell||'')}</td>
    </tr>`).join('');
  }
}

function _portSymClick(el) {
  openChartModal(el.dataset.sym, {
    description: el.dataset.desc,
  });
}
window._portSymClick = _portSymClick;
