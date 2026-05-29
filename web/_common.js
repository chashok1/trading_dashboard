/* Trading Dashboard — shared helpers (opt-in)
 *
 * Per-page scripts each redefine fetchJson(), escapeHtml(), fmtUsd(), and the
 * date-picker loader. This module exposes them on window.td_common so pages
 * can adopt them gradually:
 *
 *     <script src="/static/_common.js"></script>
 *     <script src="/static/portfolio.js"></script>
 *
 *     // in portfolio.js:
 *     const { fetchJson, escapeHtml, fmtUsd, loadDates } = window.td_common;
 *
 * The module is self-contained and side-effect-free at load time (it does
 * NOT mount any DOM, populate any dropdown, or auto-fetch). Existing pages
 * keep their own copies of these helpers and are unaffected until they opt in.
 *
 * Available:
 *   - fetchJson(url, opts)           — fetch wrapper that throws on non-OK
 *   - escapeHtml(s)                  — HTML-escape a string
 *   - fmtUsd(v)                      — format a number as USD string
 *   - fmtPct(v, decimals=2)          — format a number as percentage
 *   - fmtDate(d)                     — format a date (YYYY-MM-DD)
 *   - fmtNum(v)                      — generic number formatter
 *   - loadDates({selectId, cache})   — populate a <select> with /api/dates
 *   - clearDateCache()               — invalidate the localStorage cache
 *
 * The loadDates helper caches /api/dates in localStorage for 10 minutes by
 * default so opening multiple pages in succession doesn't repeat the call.
 */
(function () {
  'use strict';

  const DATE_CACHE_KEY = 'td_dates_cache_v1';
  const DATE_CACHE_TTL_MS = 10 * 60 * 1000;   // 10 minutes

  async function fetchJson(url, opts = {}) {
    const r = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    });
    if (!r.ok) {
      let detail;
      try {
        const body = await r.json();
        detail = body && body.detail ? body.detail : r.statusText;
      } catch (_) {
        detail = r.statusText;
      }
      throw new Error(detail || ('HTTP ' + r.status));
    }
    return r.json();
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }

  function fmtUsd(v) {
    if (v === null || v === undefined || v === '') return '';
    const n = Number(v);
    if (!isFinite(n)) return '';
    if (Math.abs(n) >= 1000) return '$' + Math.round(n).toLocaleString();
    return '$' + n.toFixed(0);
  }

  function fmtPct(v, decimals = 2) {
    if (v === null || v === undefined || v === '') return '';
    const n = Number(v);
    if (!isFinite(n)) return '';
    return n.toFixed(decimals) + '%';
  }

  function fmtDate(d) {
    if (!d) return '—';
    return String(d).slice(0, 10);
  }

  function fmtNum(v) {
    if (v === null || v === undefined || v === '') return '';
    const n = Number(v);
    if (!isFinite(n)) return '';
    if (Number.isInteger(n)) return String(n);
    return n.toFixed(3).replace(/\.?0+$/, '');
  }

  function _readDateCache() {
    try {
      const raw = localStorage.getItem(DATE_CACHE_KEY);
      if (!raw) return null;
      const obj = JSON.parse(raw);
      if (!obj || !Array.isArray(obj.dates) || !obj.expires_at) return null;
      if (Date.now() > obj.expires_at) return null;
      return obj.dates;
    } catch (_) {
      return null;
    }
  }

  function _writeDateCache(dates) {
    try {
      localStorage.setItem(DATE_CACHE_KEY, JSON.stringify({
        dates,
        expires_at: Date.now() + DATE_CACHE_TTL_MS,
      }));
    } catch (_) { /* quota / private mode — ignore */ }
  }

  function clearDateCache() {
    try { localStorage.removeItem(DATE_CACHE_KEY); } catch (_) { /* */ }
  }

  /**
   * Populate a <select> with the list of snapshot dates from /api/dates.
   * @param {object} opts
   * @param {string} opts.selectId   ID of the <select> element.
   * @param {boolean} [opts.cache]   Use localStorage cache (default true).
   * @returns {Promise<string[]>}    The dates, newest first.
   */
  async function loadDates({ selectId, cache = true } = {}) {
    let dates = cache ? _readDateCache() : null;
    if (!dates) {
      dates = await fetchJson('/api/dates');
      if (cache && Array.isArray(dates)) _writeDateCache(dates);
    }
    if (selectId) {
      const sel = document.getElementById(selectId);
      if (sel) {
        sel.innerHTML = '';
        for (const d of dates) {
          const o = document.createElement('option');
          o.value = d;
          o.textContent = d;
          sel.appendChild(o);
        }
      }
    }
    return dates;
  }

  // ── Yahoo Finance lookup link ─────────────────────────────────────
  // Returns an inline HTML snippet (small "Y!" badge) that opens the
  // symbol's Yahoo Finance quote page in a new tab. Empty string when
  // the symbol is a pseudo / cash marker that Yahoo doesn't index.
  function yahooLink(symbol) {
    if (!symbol) return '';
    const sym = String(symbol).trim();
    if (!sym) return '';
    if (sym.includes('**') || /^cash/i.test(sym) ||
        sym === 'Cash & Cash Investments') return '';
    const url = 'https://finance.yahoo.com/quote/' + encodeURIComponent(sym) + '/';
    const safe = escapeHtml(sym);
    return '<a href="' + url + '" target="_blank" rel="noopener noreferrer" '
         + 'onclick="event.stopPropagation()" '
         + 'title="Open ' + safe + ' on Yahoo Finance" '
         + 'style="margin-right:6px; font-size:9px; font-weight:700; '
         + 'color:#5f259f; background:#f3eafe; padding:1px 4px; '
         + 'border:1px solid #c3a4ed; border-radius:3px; '
         + 'text-decoration:none; vertical-align:middle; '
         + 'line-height:1.2; display:inline-block;">Y!</a>';
  }

  // ─── Risk Range Chart ────────────────────────────────────────────────────────
  // renderRRAnalysis(data, el, symbol, date) — render the Risk Range chart + stats.
  function renderRRAnalysis(data, el, symbol, date) {
    if (!data) { el.innerHTML = '<p style="color:#888;font-size:12px;">No Risk Range data.</p>'; return; }
    const p  = data.price   || {};
    const lv = data.levels  || {};
    const sd = data.sd      || {};
    const ix = data.idx     || {};
    const ru = data.rules   || {};

    const cur = p.current, prev = p.prev_close, hi = p.high, lo = p.low;
    const trend = lv.trend, trade = lv.trade, lrr = lv.lrr, mrr = lv.mrr, trr = lv.trr;
    const sdVal = sd.value;

    const fmt   = v => v == null ? '—' : Number(v).toFixed(2);
    const fmtSd = v => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2);
    const scoreColor = v => v == null ? '#94a3b8' : v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#94a3b8';
    const dot = (v, label, sdv) => {
      const c = scoreColor(v);
      const sdStr = sdv != null ? ` ${fmtSd(sdv)}SD` : '';
      return `<span style="display:inline-flex;align-items:center;gap:3px;font-size:10px;color:#475569;">
        <span style="width:9px;height:9px;border-radius:50%;background:${c};display:inline-block;flex-shrink:0;"></span>
        <span style="font-weight:600;">${label}</span><span style="color:#94a3b8;font-size:9px;">${sdStr}</span>
      </span>`;
    };

    // ── Today's price bar (current snapshot) ─────────────────────────────────
    // Left Y-axis = hist_td labels, Right Y-axis = drv_quote labels
    const W = 160, H = 210, PAD_L = 44, PAD_R = 52, PAD_T = 12, PAD_B = 18;
    const chartW = W - PAD_L - PAD_R;
    const chartH = H - PAD_T - PAD_B;

    const vals = [cur, prev, hi, lo, lrr, trr].filter(v => v != null);
    const rawMin = Math.min(...vals);
    const rawMax = Math.max(...vals);
    const pad = sdVal ? sdVal * 0.35 : (rawMax - rawMin) * 0.08;
    const yMin = rawMin - pad, yMax = rawMax + pad, yRange = yMax - yMin || 1;
    const yPx = v => PAD_T + chartH * (1 - (v - yMin) / yRange);
    const x0 = PAD_L, x1 = PAD_L + chartW, xMid = PAD_L + chartW * 0.5;

    const outLabels = [];
    if (trend != null && trend < yMin) outLabels.push(`Trend ${fmt(trend)}`);
    if (trade != null && trade < yMin) outLabels.push(`Trade ${fmt(trade)}`);

    const hline = (y, color, dash, label) =>
      `<line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}" stroke="${color}" stroke-width="1.2" stroke-dasharray="${dash}"/>
       <text x="${x1+4}" y="${y+4}" fill="${color}" font-size="9" font-weight="600">${label}</text>`;

    const rrZone = (lrr != null && trr != null)
      ? `<rect x="${x0}" y="${yPx(trr)}" width="${chartW}" height="${Math.max(yPx(lrr)-yPx(trr),1)}" fill="#f0fdf4"/>`
      : '';

    const lines = [];
    if (trr  != null && trr  >= yMin && trr  <= yMax) lines.push(hline(yPx(trr),  '#15803d', '5 2', `TRR ${fmt(trr)}`));
    if (mrr  != null && mrr  >= yMin && mrr  <= yMax) lines.push(hline(yPx(mrr),  '#4ade80', '2 3', `MRR ${fmt(mrr)}`));
    if (lrr  != null && lrr  >= yMin && lrr  <= yMax) lines.push(hline(yPx(lrr),  '#15803d', '5 2', `LRR ${fmt(lrr)}`));
    if (trade != null && trade >= yMin)               lines.push(hline(yPx(trade), '#f97316', '3 2', `Trade ${fmt(trade)}`));
    if (trend != null && trend >= yMin)               lines.push(hline(yPx(trend), '#818cf8', '3 2', `Trend ${fmt(trend)}`));

    const priceBar = () => {
      if (cur == null) return '';
      const top = yPx(Math.max(cur, prev ?? cur));
      const bot = yPx(Math.min(cur, prev ?? cur));
      const bH  = Math.max(bot - top, 2);
      const up  = cur >= (prev ?? cur);
      const fill = up ? '#16a34a' : '#dc2626';
      const wickT = hi != null ? `<line x1="${xMid}" y1="${yPx(hi)}" x2="${xMid}" y2="${top}" stroke="${fill}" stroke-width="1.5"/>` : '';
      const wickB = lo != null ? `<line x1="${xMid}" y1="${bot}" x2="${xMid}" y2="${yPx(lo)}" stroke="${fill}" stroke-width="1.5"/>` : '';
      return `${wickT}${wickB}
        <rect x="${xMid-8}" y="${top}" width="16" height="${bH}" fill="${fill}" stroke="${up?'#15803d':'#b91c1c'}" stroke-width="1" rx="1"/>`;
    };

    // Dashed horizontal reference lines for prev close and current price
    const refLines = [];
    if (prev != null && prev >= yMin && prev <= yMax)
      refLines.push(`<line x1="${x0}" y1="${yPx(prev)}" x2="${x1}" y2="${yPx(prev)}" stroke="#94a3b8" stroke-width="0.8" stroke-dasharray="3 3"/>`);
    if (cur  != null && cur  >= yMin && cur  <= yMax)
      refLines.push(`<line x1="${x0}" y1="${yPx(cur)}"  x2="${x1}" y2="${yPx(cur)}"  stroke="#374151" stroke-width="0.8" stroke-dasharray="3 3"/>`);

    // Left labels: hist_td (prev close) — offset up/down if too close to cur
    // Right labels: drv_quote (current)
    const MIN_LABEL_GAP = 11;
    let prevY = prev != null ? yPx(prev) : null;
    let curY  = cur  != null ? yPx(cur)  : null;
    if (prevY != null && curY != null && Math.abs(prevY - curY) < MIN_LABEL_GAP) {
      if (prev > cur) { prevY -= MIN_LABEL_GAP / 2; curY += MIN_LABEL_GAP / 2; }
      else            { prevY += MIN_LABEL_GAP / 2; curY -= MIN_LABEL_GAP / 2; }
    }
    const leftLbls = prev != null
      ? `<text x="${x0-3}" y="${prevY+4}" fill="#64748b" font-size="9" text-anchor="end">${fmt(prev)}</text>
         <text x="${x0-3}" y="${prevY+13}" fill="#94a3b8" font-size="7" text-anchor="end">prev</text>` : '';
    const rightLbls = cur != null
      ? `<text x="${x1+PAD_R-2}" y="${curY+4}" fill="#111" font-size="9" text-anchor="end" font-weight="700">${fmt(cur)}</text>
         <text x="${x1+PAD_R-2}" y="${curY+13}" fill="#94a3b8" font-size="7" text-anchor="end">today</text>` : '';

    const svgToday = `<svg width="${W}" height="${H}" style="overflow:visible;display:block;">
      ${rrZone}${lines.join('')}${refLines.join('')}${priceBar()}${leftLbls}${rightLbls}
      <text x="${xMid}" y="${H}" fill="#64748b" font-size="8" text-anchor="middle" font-weight="600">Today</text>
    </svg>`;

    // ── Historical chart ──────────────────────────────────────────────────────
    const histId = 'rrHist_' + Math.random().toString(36).slice(2);
    const histSvg = `<svg id="${histId}" width="280" height="${H}" style="overflow:visible;display:block;">
      <text x="140" y="${H/2}" fill="#94a3b8" font-size="10" text-anchor="middle">Loading history…</text>
    </svg>`;

    // ── Action colour ─────────────────────────────────────────────────────────
    const actionCode = ru.action || '—';
    const priority   = ru.priority != null ? ru.priority : '—';
    const isBull = ['B','BM','BS','BN','BMN','BRW','BW','BSW','BR','BC'].includes(actionCode);
    const isBear = ['SA','S','STM','SS','SO','SW','SWW','SN'].includes(actionCode);
    const actionColor = isBull ? '#16a34a' : isBear ? '#dc2626' : '#64748b';
    const actionBg    = isBull ? '#f0fdf4' : isBear ? '#fef2f2' : '#f8fafc';

    const descRow = (label, text) => text
      ? `<div style="margin-bottom:6px;">
           <div style="font-size:9px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:1px;">${label}</div>
           <div style="font-size:11px;color:#1e293b;line-height:1.35;">${text}</div>
         </div>` : '';

    // ── Assemble ──────────────────────────────────────────────────────────────
    el.innerHTML = `
    <div style="display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap;">

      <!-- Today's bar chart -->
      <div style="flex-shrink:0;">
        ${svgToday}
        ${outLabels.length ? `<div style="font-size:9px;color:#94a3b8;margin-top:1px;">${outLabels.join(' · ')} (below)</div>` : ''}
      </div>

      <!-- Historical chart -->
      <div style="flex-shrink:0;">${histSvg}
        <div style="font-size:8px;color:#94a3b8;text-align:center;margin-top:1px;">
          <span style="color:#2563eb;">— price</span> &nbsp;
          <span style="color:#15803d;">— TRR/LRR</span> &nbsp;
          <span style="color:#4ade80;">— MRR</span> &nbsp;
          <span style="color:#f97316;">— Trade</span> &nbsp;
          <span style="color:#818cf8;">— Trend</span>
        </div>
      </div>

      <!-- Right panel -->
      <div style="flex:1;min-width:200px;display:flex;flex-direction:column;gap:8px;">

        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;
          padding:5px 8px;background:#f8fafc;border-radius:6px;border:1px solid #e2e8f0;">
          ${dot(ix.trr, 'TRR', sd.trr_sd)}
          ${dot(ix.mrr, 'MRR', sd.mrr_sd)}
          ${dot(ix.lrr, 'LRR', sd.lrr_sd)}
          <span style="margin-left:auto;font-size:10px;color:#64748b;">
            <span style="color:#94a3b8;">SD</span> <strong>${fmt(sdVal)}</strong>
            &nbsp;
            <span style="color:#94a3b8;">Trend</span> <strong style="color:${scoreColor(sd.trend_sd)}">${fmtSd(sd.trend_sd)}</strong>
            &nbsp;
            <span style="color:#94a3b8;">Trade</span> <strong style="color:${scoreColor(sd.trade_sd)}">${fmtSd(sd.trade_sd)}</strong>
          </span>
        </div>

        <div style="padding:6px 8px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;">
          ${descRow('Trend Trade Rule', ru.tn_td_desc)}
          ${descRow('BB Range Streak', ru.bb_desc)}
          ${descRow('RR Desc', ru.rr_desc)}
        </div>

        <div style="display:flex;align-items:center;gap:10px;
          background:${actionBg};border:2px solid ${actionColor};border-radius:8px;padding:8px 12px;">
          <div style="font-size:26px;font-weight:900;color:${actionColor};line-height:1;min-width:36px;">${actionCode}</div>
          <div style="flex:1;">
            <div style="font-size:9px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;">Final Action · priority ${priority}</div>
            <div style="font-size:11px;color:#1e293b;line-height:1.3;margin-top:2px;">Trend Trade BB Risk Range Rule Action</div>
          </div>
        </div>

      </div>
    </div>`;

    // ── Async: fetch and render historical chart ──────────────────────────────
    if (symbol && date) {
      fetch(`/api/actionable/rr-history?symbol=${encodeURIComponent(symbol)}&date=${encodeURIComponent(date)}&days=60`)
        .then(r => r.ok ? r.json() : null)
        .then(h => {
          const svgEl = document.getElementById(histId);
          if (!svgEl || !h || !h.dates || !h.dates.length) return;
          _renderHistChart(svgEl, h, H);
        })
        .catch(() => {});
    }
  }

  // ── Historical RR line chart ──────────────────────────────────────────────
  function _renderHistChart(svgEl, h, H) {
    const dates = h.dates, prices = h.price, lrrs = h.lrr, trrs = h.trr, mrrs = h.mrr;
    const trends = h.trend || [], trades = h.trade || [];
    const n = dates.length;
    if (!n) return;

    const W = 280, PAD_L = 36, PAD_R = 8, PAD_T = 10, PAD_B = 22;
    const cW = W - PAD_L - PAD_R, cH = H - PAD_T - PAD_B;

    const allVals = [...prices, ...lrrs, ...trrs, ...trends, ...trades].filter(v => v != null);
    if (!allVals.length) return;
    const yMin = Math.min(...allVals), yMax = Math.max(...allVals);
    const yRange = yMax - yMin || 1;
    const pad = yRange * 0.05;
    const yMinP = yMin - pad, yMaxP = yMax + pad, yRangeP = yMaxP - yMinP;

    const xPx = i => PAD_L + (i / (n - 1)) * cW;
    const yPx = v => PAD_T + cH * (1 - (v - yMinP) / yRangeP);

    const polyline = (arr, color, width, dash = '') => {
      const pts = arr.map((v, i) => v != null ? `${xPx(i).toFixed(1)},${yPx(v).toFixed(1)}` : null);
      // Split into segments at nulls
      let segs = [], seg = [];
      pts.forEach(p => {
        if (p) seg.push(p);
        else if (seg.length) { segs.push(seg); seg = []; }
      });
      if (seg.length) segs.push(seg);
      return segs.map(s =>
        `<polyline points="${s.join(' ')}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linejoin="round" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`
      ).join('');
    };

    // RR zone fill (between LRR and TRR where both exist)
    let rrFill = '';
    const rrPts = lrrs.map((lv, i) => ({ i, lv, tv: trrs[i] })).filter(d => d.lv != null && d.tv != null);
    if (rrPts.length > 1) {
      const topPts = rrPts.map(d => `${xPx(d.i).toFixed(1)},${yPx(d.tv).toFixed(1)}`).join(' ');
      const botPts = [...rrPts].reverse().map(d => `${xPx(d.i).toFixed(1)},${yPx(d.lv).toFixed(1)}`).join(' ');
      rrFill = `<polygon points="${topPts} ${botPts}" fill="#f0fdf4" stroke="none"/>`;
    }

    // X-axis date labels (first, middle, last)
    const dateLabel = i => {
      const d = dates[i]; if (!d) return '';
      const parts = d.split('-');
      return parts.length >= 3 ? `${parts[1]}/${parts[2]}` : d;
    };
    const xLabels = [0, Math.floor(n/2), n-1].map(i =>
      `<text x="${xPx(i).toFixed(1)}" y="${H-4}" fill="#94a3b8" font-size="8" text-anchor="middle">${dateLabel(i)}</text>`
    ).join('');

    // Y-axis labels (min, max)
    const yLabels = [yMin, yMax].map(v =>
      `<text x="${PAD_L-3}" y="${yPx(v)+4}" fill="#94a3b8" font-size="8" text-anchor="end">${v.toFixed(0)}</text>`
    ).join('');

    // Today marker (last point)
    const todayX = xPx(n - 1);
    const todayMark = `<line x1="${todayX}" y1="${PAD_T}" x2="${todayX}" y2="${PAD_T+cH}" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="2 2"/>`;

    // Prev close + current dashed reference lines
    const prevPrice = prices[n-2] != null ? prices[n-2] : null;
    const curPrice  = prices[n-1] != null ? prices[n-1] : null;
    const hrefLines = [];
    if (prevPrice != null)
      hrefLines.push(`<line x1="${PAD_L}" y1="${yPx(prevPrice).toFixed(1)}" x2="${PAD_L+cW}" y2="${yPx(prevPrice).toFixed(1)}" stroke="#94a3b8" stroke-width="0.7" stroke-dasharray="3 3"/>`);
    if (curPrice != null)
      hrefLines.push(`<line x1="${PAD_L}" y1="${yPx(curPrice).toFixed(1)}" x2="${PAD_L+cW}" y2="${yPx(curPrice).toFixed(1)}" stroke="#374151" stroke-width="0.7" stroke-dasharray="3 3"/>`);

    svgEl.innerHTML = `
      ${rrFill}
      ${todayMark}
      ${hrefLines.join('')}
      ${polyline(trends, '#818cf8', 1,   '3 2')}
      ${polyline(trades, '#f97316', 1,   '3 2')}
      ${polyline(trrs,   '#15803d', 1.2, '4 2')}
      ${polyline(mrrs,   '#4ade80', 1,   '2 2')}
      ${polyline(lrrs,   '#15803d', 1.2, '4 2')}
      ${polyline(prices, '#2563eb', 1.8)}
      ${xLabels}${yLabels}
      <text x="${W/2}" y="${H-12}" fill="#64748b" font-size="8" text-anchor="middle" font-weight="600">60-day history</text>
    `;
  }

  window.td_common = {
    fetchJson,
    escapeHtml,
    fmtUsd,
    fmtPct,
    fmtDate,
    fmtNum,
    loadDates,
    clearDateCache,
    yahooLink,
    renderRRAnalysis,
  };
  window.yahooLink = yahooLink;
})();
