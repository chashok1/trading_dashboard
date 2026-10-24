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
const _pmSig = {};   // last-drawn signature per pie, see _pmDrawPie

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

// 2026-08-14 -- per-pie CARD width sized to that pie's own longest
// "label + pct%" combination (canvas.measureText, matching the legend
// row's actual 10px font) instead of every pie getting an equal fixed
// width regardless of content. User: "on cumulative p/l panel -> graphs
// -> use the space for sector graph. reduce space between categories and
// percentages in asset allocation, beta, and concentration graphs and use
// it for sector graph. check max size of cat lenghts and use the same
// space as between graph and catgories/legends. Once that is done for all
// graphs, use the remaining space between the graphs." Short-label pies
// (Asset Allocation/Beta/Concentration) now claim only what their own
// content needs; Sector (longer category names) gets exactly what IT
// needs -- freed space isn't hand-tuned per pie, it falls out of each
// pie's own measured content width. Dashboard-only: index.html gives each
// pie's outer wrapper an id ("...Card"); Actionable's narrow sidebar
// stack has no such ids, so _pmFitCardWidth no-ops there (getElementById
// returns null), leaving that layout's own CSS untouched.
let _pmMeasureCtx = null;
const PM_LEGEND_FONT = '10px ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const PM_SWATCH_W = 8, PM_ROW_GAP = 4; // matches _pmDrawPie's legend-row markup below (swatch width, gap between swatch/label/pct)
const PM_CANVAS_W = 90, PM_CANVAS_LEGEND_GAP = 8; // canvas width + canvas-to-legend gap in the outer row markup
const PM_CARD_MIN_W = 130; // floor so an empty/near-empty pie doesn't collapse to nothing
function _pmMeasureTextWidth(text) {
  if (!_pmMeasureCtx) _pmMeasureCtx = document.createElement('canvas').getContext('2d');
  _pmMeasureCtx.font = PM_LEGEND_FONT;
  return _pmMeasureCtx.measureText(text).width;
}
function _pmFitCardWidth(cardId, labels, values) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const total = values.reduce((a, b) => a + b, 0);
  let maxLegendW = 0;
  labels.forEach((lab, i) => {
    const pct = total ? Math.round(values[i] / total * 100) : 0;
    const w = _pmMeasureTextWidth(String(lab)) + PM_ROW_GAP + _pmMeasureTextWidth(`${pct}%`);
    if (w > maxLegendW) maxLegendW = w;
  });
  const cardW = Math.max(PM_CARD_MIN_W,
    PM_CANVAS_W + PM_CANVAS_LEGEND_GAP + PM_SWATCH_W + PM_ROW_GAP + Math.ceil(maxLegendW));
  card.style.flex = `0 0 ${cardW}px`;
}

// onSliceClick(label): optional -- called with the clicked slice/legend
// row's label when provided. Callers pass one when this pie's categories
// map onto something openable (a real axis category -> the same exposure-
// detail popup the Sector/Asset class/Style factor-scorecard cards use, or
// a single symbol -> the price-chart popup) -- see pmRenderCoreMix below
// for which pies wire one and which don't. User: "add same click actions
// on the top graphs also" (top graphs = the Portfolio Mix pies, previously
// display-only -- no click handler existed on them at all before this).
// Very light version of a hex colour (the doughnut drawn behind the legend on the Dashboard cards, 2026-10-20).
function _pmLight(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex));
  return m ? `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, 0.1)` : hex;
}

// ---- Bigger-graph popup (2026-10-20, user-directed) ----
// Clicking any of the four Dashboard graphs (Asset Allocation / Sector / Concentration / Macro Stance) opens ONE window (same
// .modal-overlay look as the Jobless / MKT SIT popups): a large version of the doughnut plus a table with every slice's $ value, share,
// holding count and the holdings themselves. A table row opens the old per-category detail popup where one exists (onRowClick).
let _pmPopupChart = null;
// Black or white text, whichever reads better on the given hex slice colour.
function _pmTextOn(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex));
  if (!m) return '#111827';
  const lum = (0.299 * parseInt(m[1], 16) + 0.587 * parseInt(m[2], 16) + 0.114 * parseInt(m[3], 16)) / 255;
  return lum > 0.6 ? '#111827' : '#ffffff';
}
function _pmClosePopup() {
  if (_pmPopupChart) { _pmPopupChart.destroy(); _pmPopupChart = null; }
  const m = document.getElementById('pmGraphModal');
  if (m) m.remove();
}
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') _pmClosePopup(); });
function _pmOpenGraphModal(d) {
  _pmClosePopup();
  const total = d.values.reduce((a, b) => a + b, 0);
  if (!total) return;
  const usd = (v) => '$' + Math.round(Number(v) || 0).toLocaleString();
  const rows = d.labels.map((lab, i) => {
    const pct = total ? (d.values[i] / total * 100) : 0;
    const tickers = (d.tickerLists && d.tickerLists[i]) || [];
    const shownName = (d.shown[i] && d.shown[i] !== lab) ? `${escapeHtml(d.shown[i])} <span class="pm-pop-dim">&middot; ${escapeHtml(lab)}</span>` : escapeHtml(lab);
    const cap = 40;
    const tk = tickers.slice(0, cap).map(escapeHtml).join(', ') + (tickers.length > cap ? ` <span class="pm-pop-dim">+${tickers.length - cap} more</span>` : '');
    const clickable = !!d.onRowClick && lab !== 'Other';
    return `<tr data-pm-row="${i}"${clickable ? ' class="pm-pop-click" title="Open the detailed positions"' : ''}>`
      + `<td><span class="pm-pop-sw" style="background:${d.colors[i]};"></span>${shownName}</td>`
      + `<td class="num">${usd(d.values[i])}</td><td class="num">${pct.toFixed(1)}%</td>`
      + `<td class="num">${tickers.length}</td><td class="pm-pop-tk">${tk}</td></tr>`;
  }).join('');
  const m = document.createElement('div');
  m.id = 'pmGraphModal';
  m.className = 'modal-overlay active';
  m.innerHTML = `<div class="modal-content" style="max-width:1600px;width:96vw;"><div class="modal-header"><div>`
    + `<h2 style="margin:0;">${escapeHtml(d.title)}</h2>`
    + `<p style="margin:0;">Your holdings &middot; ${d.labels.length} slices &middot; total ${usd(total)}${d.onRowClick ? ' &middot; click a row for the detailed positions' : ''}</p></div>`
    + `<button class="close-btn" type="button" aria-label="Close">&times;</button></div>`
    + `<div class="modal-body"><div class="pm-pop-wrap"><div class="pm-pop-chart"><canvas id="pmGraphModalCanvas" width="920" height="470"></canvas></div>`
    + `<div class="pm-pop-tbl"><table class="pm-pop-table"><thead><tr><th>Slice</th><th class="num">$ value</th><th class="num">Share</th><th class="num">Holdings</th><th>Symbols</th></tr></thead>`
    + `<tbody>${rows}</tbody></table></div></div></div></div>`;
  document.body.appendChild(m);
  m.addEventListener('click', (ev) => {
    if (ev.target === m || ev.target.closest('.close-btn')) { _pmClosePopup(); return; }
    const tr = ev.target.closest('tr[data-pm-row]');
    if (tr && d.onRowClick) {
      const lab = d.labels[Number(tr.getAttribute('data-pm-row'))];
      if (lab !== 'Other') { _pmClosePopup(); d.onRowClick(lab); }
    }
  });
  const names = d.labels.map((l, i) => (d.shown[i] && d.shown[i] !== l) ? `${d.shown[i]} - ${l}` : l);
  // 2026-10-20, user-directed: every slice gets an arrow (leader line) to a label with its NAME and SHARE (%) in two columns beside the
  // ring, so the graph reads without the table (the % is the same number as the table's Share column). Labels on each side are spread
  // out vertically so they never overlap; slices under 0.4% are left to the table.
  const calloutPlugin = {
    id: 'pmCallouts',
    afterDatasetsDraw(chart) {
      const ctx = chart.ctx;
      const arcs = chart.getDatasetMeta(0).data;
      if (!arcs.length) return;
      const cx = arcs[0].x, cy = arcs[0].y, R = arcs[0].outerRadius;
      const GAP = 17, top = 14, bottom = chart.height - 14;
      const items = [];
      arcs.forEach((arc, i) => {
        const frac = d.values[i] / total;
        if (frac < 0.004) return;
        const ang = (arc.startAngle + arc.endAngle) / 2;
        const cos = Math.cos(ang), sin = Math.sin(ang);
        const name = (d.shown[i] && d.shown[i] !== d.labels[i]) ? `${d.shown[i]} \u00b7 ${d.labels[i]}` : d.labels[i];
        items.push({ i, side: cos >= 0 ? 1 : -1, cos, sin, y: cy + sin * (R + 16), name, pct: (frac * 100).toFixed(1) + '%' });
      });
      [1, -1].forEach((side) => {
        const col = items.filter(it => it.side === side).sort((p, q) => p.y - q.y);
        for (let k = 0; k < col.length; k++) col[k].y = Math.max(col[k].y, k ? col[k - 1].y + GAP : top);
        for (let k = col.length - 1; k >= 0; k--) col[k].y = Math.min(col[k].y, k === col.length - 1 ? bottom : col[k + 1].y - GAP);
      });
      ctx.save();
      ctx.textBaseline = 'middle';
      items.forEach((it) => {
        const color = d.colors[it.i];
        const p0 = { x: cx + it.cos * (R + 1), y: cy + it.sin * (R + 1) };
        const p1 = { x: cx + it.cos * (R + 16), y: cy + it.sin * (R + 16) };
        const q = { x: cx + it.side * (R + 40), y: it.y };
        ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p1.x, p1.y); ctx.lineTo(q.x, q.y); ctx.lineTo(q.x + it.side * 8, q.y); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(p0.x, p0.y); ctx.lineTo(p1.x, p1.y); ctx.stroke();
        const dx = p0.x - p1.x, dy = p0.y - p1.y, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
        ctx.beginPath();   // arrowhead on the slice
        ctx.moveTo(p0.x, p0.y);
        ctx.lineTo(p0.x - ux * 8 + uy * 4, p0.y - uy * 8 - ux * 4);
        ctx.lineTo(p0.x - ux * 8 - uy * 4, p0.y - uy * 8 + ux * 4);
        ctx.closePath(); ctx.fill();
        ctx.textAlign = it.side === 1 ? 'left' : 'right';
        const tx = q.x + it.side * 12;
        ctx.font = '600 12px ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
        const nameW = ctx.measureText(it.name).width;
        ctx.fillStyle = '#111827';
        // name then share, always read left to right: right column = name + pct, left column = pct + name
        ctx.font = '700 12px ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
        const pctW = ctx.measureText(it.pct).width;
        if (it.side === 1) {
          ctx.font = '600 12px ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
          ctx.fillText(it.name, tx, q.y);
          ctx.font = '700 12px ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
          ctx.fillStyle = color === '#eda100' || color === '#fab219' ? '#92400e' : color;
          ctx.fillText(it.pct, tx + nameW + 7, q.y);
        } else {
          ctx.fillText(it.pct, tx, q.y);
          ctx.fillStyle = '#111827';
          ctx.font = '600 12px ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
          ctx.fillText(it.name, tx - pctW - 7, q.y);
        }
      });
      ctx.restore();
    },
  };
  _pmPopupChart = new Chart(document.getElementById('pmGraphModalCanvas'), {
    type: 'doughnut',
    plugins: [calloutPlugin],
    data: { labels: names, datasets: [{ data: d.values, backgroundColor: d.colors, borderColor: '#fff', borderWidth: 2 }] },
    options: {
      responsive: false, maintainAspectRatio: false, cutout: '50%', animation: false, layout: { padding: { left: 250, right: 250, top: 34, bottom: 34 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => ` ${c.label}: ${usd(c.parsed)} (${(c.parsed / total * 100).toFixed(1)}%)` } },
      },
    },
  });
}

// SPDR sector ETF per GICS sector (same map as api/routers/macro_areas.py::_SECTOR_ETF).
const _PM_SECTOR_SYMBOL = {
  'Communication Services': 'XLC', 'Consumer Discretionary': 'XLY', 'Consumer Staples': 'XLP', 'Energy': 'XLE',
  'Financials': 'XLF', 'Health Care': 'XLV', 'Industrials': 'XLI', 'Information Technology': 'XLK',
  'Materials': 'XLB', 'Real Estate': 'XLRE', 'Utilities': 'XLU',
};
// displayLabels (optional, 2026-10-20): what the legend shows instead of `labels` (e.g. the ETF symbol XLK for 'Information Technology');
// `labels` stay the real category names used for clicks, and the tooltip / legend hover show both.
function _pmDrawPie(key, canvasId, legendId, labels, values, colors, tickerLists, emptyMsg, onSliceClick, displayLabels, popupTitle) {
  // Dashboard cards (popupTitle set) show the 3-letter short name 'Unm' for Unmapped (2026-10-20, user-directed); hover / popup keep the full name.
  const shown = (displayLabels || labels).map(l => (popupTitle && l === 'Unmapped') ? 'Unm' : l);
  // 2026-10-20, user-directed: "why is the graph getting redrawn now and then? stop it." The Dashboard reloads everything whenever any
  // data file finishes processing (app.js::checkForNewData -> refreshAll) and each reload used to destroy + redraw (with animation) every
  // graph. Now a graph whose slices are unchanged is left exactly as it is, and a changed one is redrawn without the animation.
  const sig = JSON.stringify([labels, values.map(v => Math.round(v)), colors, shown]);
  if (_pmCharts[key] && _pmSig[key] === sig && popupTitle) return;
  _pmSig[key] = sig;
  // popupTitle (2026-10-20): the whole card opens the bigger-graph popup (_pmOpenGraphModal); the old per-slice / per-row click is then
  // available from that popup's table instead (its onRowClick), so slices and legend rows don't also fire it directly.
  const card = popupTitle ? (canvasEl => canvasEl && canvasEl.closest('[id$="Card"]'))($(canvasId)) : null;
  if (card) card._pmOpen = null;
  const fullNames = labels.map((l, i) => (shown[i] && shown[i] !== l) ? `${shown[i]} \u00b7 ${l}` : l);
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
  // 'ppm' = the Portfolio screen's pies: solid, full-colour pies (the Dashboard's are faint doughnuts).
  const solid = String(key).indexOf('ppm') === 0;
  _pmCharts[key] = new Chart(canvas, {
    type: 'doughnut',
    data: { labels: fullNames, datasets: [{ data: values, backgroundColor: (popupTitle && !solid) ? colors.map(_pmLight) : colors, borderColor: '#fff', borderWidth: 1 }] },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      animation: false,   // no draw-in animation on (re)draw
      cutout: solid ? '0%' : '55%',
      // Slice click -> onSliceClick(label), same drill-down the Sector/
      // Asset class/Style factor-scorecard pies already had before this pie
      // ever existed -- see pmRenderCoreMix's own callers for which axis
      // each pie opens (or none, for pies with no natural backend
      // counterpart -- e.g. Beta's Low/Mid/High buckets aren't a real
      // category anywhere server-side).
      onClick: solid ? (evt, elements) => {
        // Portfolio screen: a slice filters the positions grid (portfolio.js::onPieSelect); a click elsewhere on the card opens the popup.
        if (!elements.length || typeof window.onPieSelect !== 'function') return;
        if (evt.native && evt.native.stopPropagation) evt.native.stopPropagation();
        const i = elements[0].index;
        window.onPieSelect(key, labels[i], (tickerLists && tickerLists[i]) || []);
      } : (onSliceClick && !popupTitle) ? (evt, elements) => {
        if (!elements.length) return;
        onSliceClick(labels[elements[0].index]);
      } : undefined,
      onHover: (solid || (onSliceClick && !popupTitle)) ? (evt, elements) => {
        evt.native.target.style.cursor = elements.length ? 'pointer' : 'default';
      } : undefined,
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
      const nameLine = (shown[i] !== lab) ? [lab] : [];
      const titleLines = nameLine.concat(tickers.length ? _pmTickerLines(tickers) : []);
      const title = titleLines.length ? escapeHtml(titleLines.join('\n')) : '';
      const clickable = !!onSliceClick || !!popupTitle;
      const cursor = clickable ? 'pointer' : ((tickers.length || nameLine.length) ? 'help' : 'default');
      return `<div title="${title}" data-pm-idx="${i}" data-pm-label="${escapeHtml(lab)}" style="display:flex;align-items:center;gap:4px;font-size:10px;padding:1px 0;cursor:${cursor};">`
        + `<span style="width:8px;height:8px;border-radius:2px;background:${colors[i]};flex-shrink:0;"></span>`
        + `<span style="flex:1;min-width:0;color:#374151;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(shown[i])}</span>`
        + `<span style="color:#6b7280;flex-shrink:0;">${pct}%${solid ? ' ($' + Math.round(values[i] / 1000).toLocaleString() + 'k)' : ''}</span>`
        + `</div>`;
    }).join('');
    if (solid && typeof window.onPieSelect === 'function') {
      // Portfolio screen: a legend row filters the positions grid (does not bubble up to the card's open-popup click).
      legendEl.querySelectorAll('[data-pm-idx]').forEach((el) => {
        el.addEventListener('click', (ev) => {
          ev.stopPropagation();
          const i = Number(el.getAttribute('data-pm-idx'));
          window.onPieSelect(key, labels[i], (tickerLists && tickerLists[i]) || []);
        });
      });
    } else if (onSliceClick && !popupTitle) {
      legendEl.querySelectorAll('[data-pm-idx]').forEach((el) => {
        el.addEventListener('click', () => onSliceClick(labels[Number(el.getAttribute('data-pm-idx'))]));
      });
    }
  }
  if (card) {
    card.style.cursor = 'pointer';
    card._pmOpen = () => _pmOpenGraphModal({ title: popupTitle, labels, shown, values, colors, tickerLists, onRowClick: onSliceClick });
    if (!card._pmWired) { card._pmWired = true; card.addEventListener('click', () => { if (card._pmOpen) card._pmOpen(); }); }
  }
}

// Segmented bar (2026-09-01, user request: "change the Beta chart into bar
// like Quad % mixes from pie chart and don't use legend. instead use the %
// in the bar itself just like Quad %s") -- same visual convention as the
// Quads panel's Quarterly/Monthly bars (web/app.js::_renderQuadOutlookPanel's
// _segBar): one horizontal bar, width-proportional segments, % printed
// INSIDE a segment only once it's wide enough (>=15%) to hold the text
// legibly. No separate legend list -- the bar IS the legend. Only caller
// so far is Beta (pmRenderCoreMix above); written generically (same
// labels/values/colors/tickerLists/onClick shape as _pmDrawPie) in case a
// future pie gets the same treatment.
function _pmDrawSegBar(barId, labels, values, colors, tickerLists, emptyMsg, onSliceClick) {
  const el = $(barId);
  if (!el) return;
  const total = values.reduce((a, b) => a + b, 0);
  if (!total || !labels.length) {
    el.innerHTML = `<div class="empty-note" style="font-size:10px;">${emptyMsg}</div>`;
    return;
  }
  const segs = labels.map((lab, i) => ({ lab, val: values[i], pct: values[i] / total * 100,
    color: colors[i], tickers: (tickerLists && tickerLists[i]) || [] }))
    .filter(s => s.pct > 0);
  const bars = segs.map((s, i) => {
    const pctRound = Math.round(s.pct);
    const inner = s.pct >= 15
      ? `<span style="font-size:9px;color:#fff;font-weight:700;pointer-events:none;white-space:nowrap;">${escapeHtml(s.lab)} ${pctRound}%</span>`
      : '';
    const titleTickers = s.tickers.length ? ` — ${_pmTickerLines(s.tickers).join(', ')}` : '';
    const title = `${s.lab}: ${_pmFmtUsd(s.val)} (${pctRound}%)${titleTickers}`;
    const cursor = onSliceClick && s.lab !== 'Other' ? 'pointer' : 'default';
    return `<div data-pm-seg="${i}" style="width:${s.pct}%;background:${s.color};height:100%;` +
      `display:flex;align-items:center;justify-content:center;overflow:hidden;cursor:${cursor};" ` +
      `title="${escapeHtml(title)}">${inner}</div>`;
  }).join('');
  el.innerHTML = `<div style="display:flex;width:100%;height:16px;border-radius:3px;overflow:hidden;border:1px solid #e2e8f0;">${bars}</div>`;
  if (onSliceClick) {
    el.querySelectorAll('[data-pm-seg]').forEach((seg) => {
      const s = segs[Number(seg.getAttribute('data-pm-seg'))];
      if (s.lab === 'Other') return;
      seg.addEventListener('click', (ev) => { ev.stopPropagation(); onSliceClick(s.lab); });
    });
  }
}

// Click actions for the pies whose categories map onto something openable.
// 'Other' (the top-7-cutoff synthetic aggregate, several categories/symbols
// folded together) has no single matching backend category/symbol -- not
// clickable, in either pie/bar. Guarded with typeof-checks, not a hard
// dependency -- the two popup scripts (risk_gauge_modal.js/chart_modal.js)
// are expected to be loaded on every page that includes this module
// (index.html only now -- actionable.html's Portfolio Mix panel, and its
// copy of both those scripts, was removed 2026-09-01), but a future page
// reusing pmRenderCoreMix without them should degrade to "click does
// nothing" rather than throwing.
function _pmOpenCategoryModal(axis, label) {
  if (label === 'Other') return;
  if (typeof window.openFactorExposureModal === 'function') window.openFactorExposureModal(axis, label);
}
function _pmOpenSymbolChart(label) {
  if (label === 'Other') return;
  if (typeof window.openChartModal === 'function') window.openChartModal(label);
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
    assetLabels.map(k => assetTickerMap[k]), 'No asset class data for held positions.',
    (label) => _pmOpenCategoryModal('asset_class', label), undefined, (idPrefix === 'dpm' || idPrefix === 'ppm') ? 'Asset Allocation' : null);
  _pmFitCardWidth(idPrefix + 'AssetCard', assetLabels, assetLabels.map(k => assetTotals[k]));

  if (!held.length) {
    _pmDrawSegBar(idPrefix + 'BetaBar', [], [], [], [], 'No held positions match the current filters.');
    if (idPrefix === 'ppm') _pmDrawPie('ppmBeta', 'ppmBetaCanvas', 'ppmBetaLegend', [], [], [], [], 'No held positions match the current filters.');
    ['Sector', 'Conc'].forEach(suf => {
      _pmDrawPie(idPrefix + suf, idPrefix + suf + 'Canvas', idPrefix + suf + 'Legend',
        [], [], [], [], 'No held positions match the current filters.');
      _pmFitCardWidth(idPrefix + suf + 'Card', [], []);
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
  // 2026-09-01, user request: "change the Beta chart into bar like Quad %
  // mixes from pie chart and don't use legend. instead use the % in the
  // bar itself just like Quad %s" -- segmented bar (_pmDrawSegBar below),
  // same look/convention as the Quads panel's Quarterly/Monthly bars
  // (web/app.js::_renderQuadOutlookPanel's _segBar) -- one bar, no
  // separate legend list, % printed INSIDE each wide-enough segment.
  // Click-to-open popup unchanged (same 'beta' axis/thresholds as before).
  if (idPrefix === 'ppm') {
    // Portfolio screen: Beta is a pie of its own (2026-10-24, user-directed); the Dashboard keeps the segmented bar.
    _pmDrawPie('ppmBeta', 'ppmBetaCanvas', 'ppmBetaLegend', betaLabels, betaLabels.map(k => betaBuckets[k]),
      betaLabels.map(k => _PM_BETA_COLORS[k]), betaLabels.map(k => betaTickers[k]),
      'No beta data for held positions.', (label) => _pmOpenCategoryModal('beta', label), undefined, 'Beta');
  } else {
    _pmDrawSegBar(idPrefix + 'BetaBar', betaLabels, betaLabels.map(k => betaBuckets[k]),
      betaLabels.map(k => _PM_BETA_COLORS[k]), betaLabels.map(k => betaTickers[k]),
      'No beta data for held positions.',
      (label) => _pmOpenCategoryModal('beta', label));
  }

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
  // 2026-10-20, user-directed: the legend shows the sector's ETF symbol (XLK for Information Technology, ...) instead of the long name;
  // hover and clicks still use the full sector name. Unmapped / Other / Country ETF have no SPDR symbol and keep their name.
  const secShown = secEntries.map(e => _PM_SECTOR_SYMBOL[e[0]] || e[0]);
  _pmDrawPie(idPrefix + 'Sector', idPrefix + 'SectorCanvas', idPrefix + 'SectorLegend',
    secEntries.map(e => e[0]), secEntries.map(e => e[1]), secEntries.map(e => secColorOf(e[0])),
    secTickerLists, 'No sector data for held positions.',
    (label) => _pmOpenCategoryModal('sector', label), secShown, (idPrefix === 'dpm' || idPrefix === 'ppm') ? 'Sector' : null);
  _pmFitCardWidth(idPrefix + 'SectorCard', secShown, secEntries.map(e => e[1]));

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
    concTickerLists, 'No held positions.',
    _pmOpenSymbolChart, undefined, (idPrefix === 'dpm' || idPrefix === 'ppm') ? 'Concentration' : null);
  _pmFitCardWidth(idPrefix + 'ConcCard', concEntries.map(e => e[0]), concEntries.map(e => e[1]));
}
