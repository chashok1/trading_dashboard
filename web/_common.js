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
    // ── Chart 1: Today's price bar vs RR bands ────────────────────────────────
    // Y scale = RR range only (lrr..trr + price); Trade/Trend in separate chart
    const vals1 = [cur, prev, hi, lo, lrr, trr].filter(v => v != null);
    const rawMin1 = Math.min(...vals1), rawMax1 = Math.max(...vals1);
    const W1 = 160, H = 220, PAD_L = 44, PAD_R = 54, PAD_T = 12, PAD_B = 18;
    const chartW1 = W1 - PAD_L - PAD_R, chartH = H - PAD_T - PAD_B;
    const pad1 = sdVal ? sdVal * 0.35 : (rawMax1 - rawMin1) * 0.08;
    const yMin1 = rawMin1 - pad1, yMax1 = rawMax1 + pad1, yRng1 = yMax1 - yMin1 || 1;
    const yPx1 = v => PAD_T + chartH * (1 - (v - yMin1) / yRng1);
    const x0 = PAD_L, x1 = PAD_L + chartW1, xMid1 = PAD_L + chartW1 * 0.5;

    const hline1 = (y, color, dash, label) =>
      `<line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}" stroke="${color}" stroke-width="1.2" stroke-dasharray="${dash}"/>
       <text x="${x1+4}" y="${y+4}" fill="${color}" font-size="9" font-weight="600">${label}</text>`;

    const prevYe = prev != null && prev >= yMin1 && prev <= yMax1 ? yPx1(prev) : null;
    const curYe  = cur  != null && cur  >= yMin1 && cur  <= yMax1 ? yPx1(cur)  : null;
    const MIN_GAP = 10;
    let prevLY = prevYe, curLY = curYe;
    if (prevLY != null && curLY != null && Math.abs(prevLY - curLY) < MIN_GAP) {
      const half = (MIN_GAP - Math.abs(prevLY - curLY)) / 2;
      if (prev > cur) { prevLY -= half; curLY += half; } else { prevLY += half; curLY -= half; }
    }

    const priceDashes1 = [
      prevYe != null ? `<line x1="${x0}" y1="${prevYe}" x2="${x1}" y2="${prevYe}" stroke="#94a3b8" stroke-width="0.8" stroke-dasharray="3 3"/>` : '',
      curYe  != null ? `<line x1="${x0}" y1="${curYe}"  x2="${x1}" y2="${curYe}"  stroke="#374151" stroke-width="0.8" stroke-dasharray="3 3"/>` : '',
      prevLY != null ? `<text x="${x0-3}" y="${prevLY+4}" fill="#64748b" font-size="9" text-anchor="end">${fmt(prev)}</text>
                        <text x="${x0-3}" y="${prevLY+12}" fill="#94a3b8" font-size="7" text-anchor="end">prev</text>` : '',
      curLY  != null ? `<text x="${x1+4}" y="${curLY+4}" fill="#111" font-size="9" font-weight="700">${fmt(cur)}</text>
                        <text x="${x1+4}" y="${curLY+12}" fill="#94a3b8" font-size="7">today</text>` : '',
    ].join('');

    const rrZone = (lrr != null && trr != null)
      ? `<rect x="${x0}" y="${yPx1(trr)}" width="${chartW1}" height="${Math.max(yPx1(lrr)-yPx1(trr),1)}" fill="#f0fdf4"/>` : '';

    const lines1 = [];
    if (trr != null && trr >= yMin1 && trr <= yMax1) lines1.push(hline1(yPx1(trr), '#15803d', '5 2', `TRR ${fmt(trr)}`));
    if (mrr != null && mrr >= yMin1 && mrr <= yMax1) lines1.push(hline1(yPx1(mrr), '#4ade80', '2 3', `MRR ${fmt(mrr)}`));
    if (lrr != null && lrr >= yMin1 && lrr <= yMax1) lines1.push(hline1(yPx1(lrr), '#15803d', '5 2', `LRR ${fmt(lrr)}`));

    const priceBar1 = () => {
      if (cur == null) return '';
      const top = yPx1(Math.max(cur, prev ?? cur)), bot = yPx1(Math.min(cur, prev ?? cur));
      const bH = Math.max(bot - top, 2), up = cur >= (prev ?? cur);
      const fill = up ? '#16a34a' : '#dc2626';
      const wT = hi != null ? `<line x1="${xMid1}" y1="${yPx1(hi)}" x2="${xMid1}" y2="${top}" stroke="${fill}" stroke-width="1.5"/>` : '';
      const wB = lo != null ? `<line x1="${xMid1}" y1="${bot}" x2="${xMid1}" y2="${yPx1(lo)}" stroke="${fill}" stroke-width="1.5"/>` : '';
      return `${wT}${wB}<rect x="${xMid1-8}" y="${top}" width="16" height="${bH}" fill="${fill}" stroke="${up?'#15803d':'#b91c1c'}" stroke-width="1" rx="1"/>`;
    };

    const svgToday = `<svg width="${W1}" height="${H}" style="overflow:visible;display:block;">
      ${rrZone}${lines1.join('')}${priceDashes1}${priceBar1()}
      <text x="${xMid1}" y="${H}" fill="#64748b" font-size="8" text-anchor="middle" font-weight="600">Today (RR)</text>
    </svg>`;

    // ── Chart 2: Trade / Trend — fixed small height, no proportional scaling ──
    const svgTT = (() => {
      if (trend == null && trade == null) return '';
      // Fixed small chart: Trend/Trade lines evenly spaced, price indicator only
      const W2 = 120, H2 = 155, PAD_L2 = 42, PAD_R2 = 50, PAD_T2 = 14, PAD_B2 = 38;
      const cW2 = W2 - PAD_L2 - PAD_R2, cH2 = H2 - PAD_T2 - PAD_B2;
      const xa = PAD_L2, xb = PAD_L2 + cW2, xm2 = PAD_L2 + cW2 * 0.5;

      // Fixed Y positions: Trade at top third, Trend at bottom third
      const yTrade = PAD_T2 + cH2 * 0.25;
      const yTrend = PAD_T2 + cH2 * 0.75;

      const hline2 = (y, color, dash, label) =>
        `<line x1="${xa}" y1="${y}" x2="${xb}" y2="${y}" stroke="${color}" stroke-width="1.2" stroke-dasharray="${dash}"/>
         <text x="${xb+3}" y="${y+4}" fill="${color}" font-size="9" font-weight="600">${label}</text>`;

      const trendLine = trend != null ? hline2(yTrend, '#818cf8', '3 2', `Trend ${fmt(trend)}`) : '';
      const tradeLine = trade != null ? hline2(yTrade, '#f97316', '3 2', `Trade ${fmt(trade)}`) : '';

      // Price indicator: arrow at top if above Trade, arrow at bottom if below Trend,
      // or a marker between the two lines if between Trend and Trade
      let priceIndicator = '';
      if (cur != null) {
        const aboveTrade = trade != null && cur > trade;
        const belowTrend = trend != null && cur < trend;
        if (aboveTrade) {
          priceIndicator = `
            <text x="${xm2}" y="${PAD_T2-2}" fill="#374151" font-size="9" text-anchor="middle" font-weight="700">↑ ${fmt(cur)}</text>`;
        } else if (belowTrend) {
          priceIndicator = `
            <text x="${xm2}" y="${H2-2}" fill="#374151" font-size="9" text-anchor="middle" font-weight="700">↓ ${fmt(cur)}</text>`;
        } else {
          // Between Trend and Trade — show as dashed line proportionally
          const ttSpan = (trade ?? trend) - (trend ?? trade);
          const ttFrac = ttSpan > 0 ? (cur - (trend ?? cur)) / ttSpan : 0.5;
          const py2 = yTrend - ttFrac * (yTrend - yTrade);
          priceIndicator = `
            <line x1="${xa}" y1="${py2}" x2="${xb}" y2="${py2}" stroke="#374151" stroke-width="0.8" stroke-dasharray="3 3"/>
            <text x="${xa-3}" y="${py2+4}" fill="#374151" font-size="9" text-anchor="end" font-weight="700">${fmt(cur)}</text>`;
        }
      }

      // SD labels sit inside the bottom padding (PAD_B2=38 gives room for 3 lines)
      const chartLbl = `<text x="${xm2}" y="${H2-24}" fill="#64748b" font-size="8" text-anchor="middle" font-weight="600">Trend/Trade</text>`;
      const trendSdTxt = sd.trend_sd != null
        ? `<text x="${xm2}" y="${H2-13}" fill="${scoreColor(sd.trend_sd)}" font-size="8" text-anchor="middle">Trend ${fmtSd(sd.trend_sd)}SD</text>` : '';
      const tradeSdTxt = sd.trade_sd != null
        ? `<text x="${xm2}" y="${H2-3}" fill="${scoreColor(sd.trade_sd)}" font-size="8" text-anchor="middle">Trade ${fmtSd(sd.trade_sd)}SD</text>` : '';

      return `<svg width="${W2}" height="${H2}" style="overflow:visible;display:block;">
        ${trendLine}${tradeLine}${priceIndicator}
        ${chartLbl}${trendSdTxt}${tradeSdTxt}
      </svg>`;
    })();

    // ── Historical chart ──────────────────────────────────────────────────────
    const histId = 'rrHist_' + Math.random().toString(36).slice(2);
    const histSvg = `<svg id="${histId}" width="380" height="${H}" style="overflow:visible;display:block;">
      <text x="190" y="${H/2}" fill="#94a3b8" font-size="10" text-anchor="middle">Loading history…</text>
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
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;">

      <!-- Today's bar chart (RR bands) -->
      <div style="flex-shrink:0;">${svgToday}</div>

      <!-- Trade / Trend separate chart -->
      ${svgTT ? `<div style="flex-shrink:0;">${svgTT}</div>` : ''}

      <!-- Historical chart -->
      <div style="flex-shrink:0;">${histSvg}
        <div style="font-size:8px;color:#94a3b8;text-align:center;margin-top:2px;display:flex;gap:8px;flex-wrap:wrap;justify-content:center;">
          <span style="color:#2563eb;">&#9644; price</span>
          <span style="color:#15803d;">&#9135;&#9135; TRR/LRR</span>
          <span style="color:#f97316;">&#9135;&#9135; Trade</span>
          <span style="color:#818cf8;">&#9135;&#9135; Trend</span>
        </div>
      </div>

      <!-- Right panel -->
      <div style="flex:1;min-width:160px;max-width:260px;display:flex;flex-direction:column;gap:8px;">

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
          _renderHistChart(svgEl, h, H, lv);
        })
        .catch(() => {});
    }
  }

  // ── Historical RR line chart ──────────────────────────────────────────────
  function _renderHistChart(svgEl, h, H, levels) {
    const dates = h.dates, prices = h.price, lrrs = h.lrr, trrs = h.trr;
    const trends = h.trend || [], trades = h.trade || [];
    const n = dates.length;
    if (!n) return;

    const W = 380, PAD_L = 44, PAD_R = 54, PAD_T = 10, PAD_B = 22;
    const cW = W - PAD_L - PAD_R, cH = H - PAD_T - PAD_B;

    const allVals = [...prices, ...lrrs, ...trrs, ...trends, ...trades].filter(v => v != null);
    if (!allVals.length) return;
    const yMin = Math.min(...allVals), yMax = Math.max(...allVals);
    const pad = (yMax - yMin) * 0.05 || 1;
    const yMinP = yMin - pad, yMaxP = yMax + pad, yRangeP = yMaxP - yMinP;

    const xPx = i => PAD_L + (n > 1 ? (i / (n - 1)) * cW : cW / 2);
    const yPx = v => PAD_T + cH * (1 - (v - yMinP) / yRangeP);

    // Step-function polyline — each value holds until the next change
    const stepPolyline = (arr, color, lw, dash = '') => {
      const pts = [];
      for (let i = 0; i < n; i++) {
        if (arr[i] == null) continue;
        pts.push(`${xPx(i).toFixed(1)},${yPx(arr[i]).toFixed(1)}`);
        // Extend horizontally to next point
        if (i + 1 < n && arr[i+1] != null && arr[i+1] !== arr[i]) {
          pts.push(`${xPx(i+1).toFixed(1)},${yPx(arr[i]).toFixed(1)}`);
        }
      }
      if (!pts.length) return '';
      return `<polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="${lw}" stroke-linejoin="round" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
    };

    const smoothPolyline = (arr, color, lw, dash = '') => {
      const pts = arr.map((v, i) => v != null ? `${xPx(i).toFixed(1)},${yPx(v).toFixed(1)}` : null);
      let segs = [], seg = [];
      pts.forEach(p => { if (p) seg.push(p); else if (seg.length) { segs.push(seg); seg = []; } });
      if (seg.length) segs.push(seg);
      return segs.map(s =>
        `<polyline points="${s.join(' ')}" fill="none" stroke="${color}" stroke-width="${lw}" stroke-linejoin="round" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`
      ).join('');
    };

    // Green zone fill between TRR and LRR (step-function polygon)
    let rrFill = '';
    const rrPts = lrrs.map((lv, i) => ({ i, lv, tv: trrs[i] })).filter(d => d.lv != null && d.tv != null);
    if (rrPts.length >= 1) {
      // Build step-function polygon top (TRR) then reverse bottom (LRR)
      const topPts = [], botPts = [];
      for (let k = 0; k < rrPts.length; k++) {
        const { i, lv, tv } = rrPts[k];
        topPts.push(`${xPx(i).toFixed(1)},${yPx(tv).toFixed(1)}`);
        if (k + 1 < rrPts.length) topPts.push(`${xPx(rrPts[k+1].i).toFixed(1)},${yPx(tv).toFixed(1)}`);
        botPts.unshift(`${xPx(i).toFixed(1)},${yPx(lv).toFixed(1)}`);
        if (k + 1 < rrPts.length) botPts.unshift(`${xPx(rrPts[k+1].i).toFixed(1)},${yPx(lv).toFixed(1)}`);
      }
      rrFill = `<polygon points="${[...topPts,...botPts].join(' ')}" fill="#f0fdf4" stroke="none"/>`;
    }

    // Right-side labels for latest TRR and LRR
    const latestTrr = [...trrs].reverse().find(v => v != null);
    const latestLrr = [...lrrs].reverse().find(v => v != null);
    const rrLabels = [
      latestTrr != null && latestTrr >= yMinP && latestTrr <= yMaxP
        ? `<text x="${PAD_L+cW+3}" y="${yPx(latestTrr)+4}" fill="#15803d" font-size="9" font-weight="600">TRR ${latestTrr.toFixed(0)}</text>` : '',
      latestLrr != null && latestLrr >= yMinP && latestLrr <= yMaxP
        ? `<text x="${PAD_L+cW+3}" y="${yPx(latestLrr)+4}" fill="#15803d" font-size="9" font-weight="600">LRR ${latestLrr.toFixed(0)}</text>` : '',
    ].join('');

    // Date labels (first, mid, last)
    const dateLabel = i => { const d = dates[i]; if (!d) return ''; const p = d.split('-'); return p.length >= 3 ? `${p[1]}/${p[2]}` : d; };
    const xLabels = [0, Math.floor(n/2), n-1].filter((v,i,a) => a.indexOf(v) === i).map(i =>
      `<text x="${xPx(i).toFixed(1)}" y="${H-4}" fill="#94a3b8" font-size="8" text-anchor="middle">${dateLabel(i)}</text>`
    ).join('');

    // Y-axis labels (top, mid, bottom)
    const yLabels = [yMin, (yMin+yMax)/2, yMax].map(v =>
      `<text x="${PAD_L-3}" y="${yPx(v)+4}" fill="#94a3b8" font-size="8" text-anchor="end">${v.toFixed(0)}</text>`
    ).join('');

    const todayX = xPx(n - 1);
    const todayMark = `<line x1="${todayX}" y1="${PAD_T}" x2="${todayX}" y2="${PAD_T+cH}" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="2 2"/>`;
    const curPrice = prices[n-1];
    const curLine = curPrice != null
      ? `<line x1="${PAD_L}" y1="${yPx(curPrice).toFixed(1)}" x2="${PAD_L+cW}" y2="${yPx(curPrice).toFixed(1)}" stroke="#374151" stroke-width="0.7" stroke-dasharray="3 3"/>` : '';

    svgEl.setAttribute('width', W);
    svgEl.innerHTML = `
      ${rrFill}
      ${todayMark}${curLine}
      ${smoothPolyline(trends, '#818cf8', 1,   '3 2')}
      ${smoothPolyline(trades, '#f97316', 1,   '3 2')}
      ${stepPolyline(trrs,   '#15803d', 1.5, '4 2')}
      ${stepPolyline(lrrs,   '#15803d', 1.5, '4 2')}
      ${smoothPolyline(prices, '#2563eb', 2)}
      ${rrLabels}${xLabels}${yLabels}
      <text x="${(PAD_L+PAD_L+cW)/2}" y="${H-12}" fill="#64748b" font-size="8" text-anchor="middle" font-weight="600">60-day history</text>
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
