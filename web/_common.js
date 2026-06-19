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

  /**
   * Format a number as USD.
   * @param {*}       v     — the value
   * @param {object} [opts]
   * @param {boolean} [opts.compact]  — use K/M suffixes (portfolio.js style)
   * @param {boolean} [opts.sign]     — prepend + for positive values
   */
  function fmtUsd(v, opts = {}) {
    if (v === null || v === undefined || v === '') return '';
    const n = Number(v);
    if (!isFinite(n)) return '';
    const abs = Math.abs(n);
    let s;
    if (opts.compact && abs >= 1e6) {
      s = (abs / 1e6).toLocaleString(undefined,
          { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'M';
    } else if (opts.compact && abs >= 1e3) {
      s = (abs / 1e3).toLocaleString(undefined,
          { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'K';
    } else if (abs >= 1000) {
      s = Math.round(abs).toLocaleString();
    } else {
      s = abs.toFixed(0);
    }
    const prefix = (n < 0 ? '-$' : (opts.sign && n > 0 ? '+$' : '$'));
    return prefix + s;
  }

  /**
   * Format a number as a percentage.
   * @param {*}      v        — the value (treated as already-a-percent, e.g. 5.3 → "5.30%")
   * @param {number} [decimals=2]
   * @param {boolean} [opts.sign]  — prepend + for positive
   */
  function fmtPct(v, decimals = 2, opts = {}) {
    if (v === null || v === undefined || v === '') return '';
    const n = Number(v);
    if (!isFinite(n)) return '';
    const sign = (opts && opts.sign) ? (n >= 0 ? '+' : '') : '';
    return sign + n.toFixed(decimals) + '%';
  }

  function fmtDate(d) {
    if (!d) return '—';
    return String(d).slice(0, 10);
  }

  /**
   * Generic number formatter.
   * @param {*}      v
   * @param {number} [digits=2]  — max decimal places
   */
  function fmtNum(v, digits = 2) {
    if (v === null || v === undefined || v === '') return '';
    const n = Number(v);
    if (!isFinite(n)) return '';
    if (Number.isInteger(n)) return String(n);
    return n.toFixed(digits).replace(/\.?0+$/, '');
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
    const rrOutlookRaw = data.rr_outlook || null;

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
    const W1 = 210, H = 220, PAD_L = 44, PAD_R = 102, PAD_T = 12, PAD_B = 18;
    const chartW1 = W1 - PAD_L - PAD_R, chartH = H - PAD_T - PAD_B;
    const pad1 = sdVal ? sdVal * 0.35 : (rawMax1 - rawMin1) * 0.08;
    const yMin1 = rawMin1 - pad1, yMax1 = rawMax1 + pad1, yRng1 = yMax1 - yMin1 || 1;
    const yPx1 = v => PAD_T + chartH * (1 - (v - yMin1) / yRng1);
    const x0 = PAD_L, x1 = PAD_L + chartW1, xMid1 = PAD_L + chartW1 * 0.5;

    const hline1 = (y, color, dash, label) =>
      `<line x1="${x0}" y1="${y}" x2="${x1+40}" y2="${y}" stroke="${color}" stroke-width="1.2" stroke-dasharray="${dash}"/>
       ${label ? `<text x="${x1+44}" y="${y+4}" fill="${color}" font-size="8" text-anchor="start" font-weight="600">${label}</text>` : ''}`;

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
      curYe  != null ? `<line x1="${x0}" y1="${curYe}"  x2="${x1+2}"  y2="${curYe}"  stroke="#374151" stroke-width="0.8" stroke-dasharray="3 3"/>` : '',
      prevLY != null ? `<text x="${x0-3}" y="${prevLY+4}" fill="#64748b" font-size="9" text-anchor="end">${fmt(prev)}</text>
                        <text x="${x0-3}" y="${prevLY+12}" fill="#94a3b8" font-size="7" text-anchor="end">prev</text>` : '',
      curLY  != null ? `<text x="${x1+4}" y="${curLY+4}" fill="#111" font-size="9" text-anchor="start" font-weight="700">${fmt(cur)}</text>
                        <text x="${x1+4}" y="${curLY+12}" fill="#94a3b8" font-size="7" text-anchor="start">today</text>` : '',
    ].join('');

    const rrZone = (lrr != null && trr != null)
      ? `<rect x="${x0}" y="${yPx1(trr)}" width="${chartW1}" height="${Math.max(yPx1(lrr)-yPx1(trr),1)}" fill="#f0fdf4"/>` : '';

    // TRR/LRR lines extend to x1+40 (almost touching labels at x1+44)
    const rrLabel = (y, label) =>
      `<line x1="${x0}" y1="${y}" x2="${x1+40}" y2="${y}" stroke="#15803d" stroke-width="1.2" stroke-dasharray="5 2"/>
       <text x="${x1+44}" y="${y+4}" fill="#15803d" font-size="8" text-anchor="start" font-weight="600">${label}</text>`;
    const lines1 = [];
    if (trr != null && trr >= yMin1 && trr <= yMax1) lines1.push(rrLabel(yPx1(trr), `TRR ${fmt(trr)}`));
    if (mrr != null && mrr >= yMin1 && mrr <= yMax1) lines1.push(hline1(yPx1(mrr), '#4ade80', '2 3', null));
    if (lrr != null && lrr >= yMin1 && lrr <= yMax1) lines1.push(rrLabel(yPx1(lrr), `LRR ${fmt(lrr)}`));

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
    </svg>`;

    // ── Chart 2: Trend/Trade — fixed positions, price indicator ──────────────
    const svgTT = (() => {
      if (trend == null && trade == null) return '';
      const W2 = 120, H2 = 120, PAD_L2 = 42, PAD_R2 = 50, PAD_T2 = 14, PAD_B2 = 14;
      const cW2 = W2 - PAD_L2 - PAD_R2, cH2 = H2 - PAD_T2 - PAD_B2;
      const xa = PAD_L2, xb = PAD_L2 + cW2, xm2 = PAD_L2 + cW2 * 0.5;

      const yTrade = PAD_T2 + cH2 * 0.25;
      const yTrend = PAD_T2 + cH2 * 0.75;

      const hline2 = (y, color, dash, label) =>
        `<line x1="${xa}" y1="${y}" x2="${xb}" y2="${y}" stroke="${color}" stroke-width="1.2" stroke-dasharray="${dash}"/>
         ${label ? `<text x="${xb+3}" y="${y+4}" fill="${color}" font-size="8" text-anchor="start" font-weight="600">${label}</text>` : ''}`;

      const tradeLine = trade != null ? hline2(yTrade, '#f97316', '3 2', `Trade ${fmt(trade)}`) : '';
      const trendLine = trend != null ? hline2(yTrend, '#818cf8', '3 2', `Trend ${fmt(trend)}`) : '';

      // Price indicator relative to Trade and Trend
      let priceIndicator = '';
      if (cur != null) {
        const aboveTrade = trade != null && cur > trade;
        const belowTrend = trend != null && cur < trend;
        if (aboveTrade) {
          priceIndicator = `<text x="${xm2}" y="${PAD_T2-2}" fill="#374151" font-size="9" text-anchor="middle" font-weight="700">↑ ${fmt(cur)}</text>`;
        } else if (belowTrend) {
          priceIndicator = `<text x="${xm2}" y="${H2-PAD_B2+10}" fill="#374151" font-size="9" text-anchor="middle" font-weight="700">↓ ${fmt(cur)}</text>`;
        } else {
          const ttSpan = (trade ?? trend) - (trend ?? trade);
          const ttFrac = ttSpan > 0 ? (cur - (trend ?? cur)) / ttSpan : 0.5;
          const py2 = yTrend - ttFrac * (yTrend - yTrade);
          priceIndicator = `
            <line x1="${xa}" y1="${py2}" x2="${xb}" y2="${py2}" stroke="#374151" stroke-width="0.8" stroke-dasharray="3 3"/>
            <text x="${xa-3}" y="${py2+4}" fill="#374151" font-size="9" text-anchor="end" font-weight="700">${fmt(cur)}</text>`;
        }
      }

      return `<svg width="${W2}" height="${H2}" style="overflow:visible;display:block;">
        ${tradeLine}${trendLine}${priceIndicator}
      </svg>`;
    })();

    // ── Historical chart ──────────────────────────────────────────────────────
    const histId = 'rrHist_' + Math.random().toString(36).slice(2);
    const histSvg = `<svg id="${histId}" width="100%" height="${H}" style="overflow:visible;display:block;">
      <text x="50%" y="${H/2}" fill="#94a3b8" font-size="10" text-anchor="middle">Loading history…</text>
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

    // ── tagged descRow — label + "short_name: description" ──────────────────
    const taggedRow = (shortName, label, text, score) => (shortName || text || score != null)
      ? `<div style="margin-bottom:8px;">
           <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">
             <span style="font-size:9px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.04em;">${label}</span>
             ${score != null ? `<span style="font-size:10px;font-weight:700;color:${scoreColor(score)};background:${score>0?'#f0fdf4':score<0?'#fef2f2':'#f8fafc'};border:1px solid ${score>0?'#bbf7d0':score<0?'#fecaca':'#e2e8f0'};padding:0 5px;border-radius:4px;">${score}</span>` : ''}
           </div>
           <div style="font-size:11px;color:${scoreColor(score)};line-height:1.35;">
             ${shortName ? `<span style="font-weight:700;">${escapeHtml(shortName)}</span>${text ? ': ' : ''}` : ''}${escapeHtml(text)}
           </div>
         </div>` : '';

    // ── Assemble ──────────────────────────────────────────────────────────────
    // ── Shared box style ──────────────────────────────────────────────────────
    const infoBox = (content, extraStyle = '') =>
      `<div style="padding:5px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-size:9px;${extraStyle}">${content}</div>`;

    // ── Box above Graph1: TRR MRR LRR centered close together ───────────────
    const rrIdxBox = infoBox(`
      <div style="display:flex;align-items:center;justify-content:center;gap:12px;">
        ${dot(ix.trr, 'TRR', sd.trr_sd)}
        ${dot(ix.mrr, 'MRR', sd.mrr_sd)}
        ${dot(ix.lrr, 'LRR', sd.lrr_sd)}
      </div>`);

    // ── Box above Graph2: SD Trend Trade centered close together ─────────────
    const sdBox = infoBox(`
      <div style="display:flex;align-items:center;justify-content:center;gap:12px;color:#64748b;">
        <span><span style="color:#94a3b8;">SD</span> <strong>${fmt(sdVal)}</strong></span>
        <span><span style="color:#94a3b8;">Trend</span> <strong style="color:${scoreColor(sd.trend_sd)}">${fmtSd(sd.trend_sd)}</strong></span>
        <span><span style="color:#94a3b8;">Trade</span> <strong style="color:${scoreColor(sd.trade_sd)}">${fmtSd(sd.trade_sd)}</strong></span>
      </div>`);

    // ── Box below Graph1: TRR MRR LRR centered (always shown) ───────────────
    const graph1Box = infoBox(`
      <div style="display:flex;justify-content:center;gap:12px;">
        <span><span style="color:#94a3b8;">TRR</span> <strong style="color:#be185d;">${fmt(trr)}</strong></span>
        <span><span style="color:#94a3b8;">MRR</span> <strong style="color:#4ade80;">${fmt(mrr)}</strong></span>
        <span><span style="color:#94a3b8;">LRR</span> <strong style="color:#be185d;">${fmt(lrr)}</strong></span>
      </div>`);

    // ── Box below Graph2: Trade Trend centered, same width as top box ────────
    const graph2Box = infoBox(`
      <div style="display:flex;justify-content:center;gap:12px;width:100%;">
        <span><span style="color:#94a3b8;">Trade</span> <strong style="color:#f97316;">${fmt(trade)}</strong></span>
        <span><span style="color:#94a3b8;">Trend</span> <strong style="color:#818cf8;">${fmt(trend)}</strong></span>
      </div>`, 'width:100%;box-sizing:border-box;');

    // ── Graph4 top bar: TRR/MRR/LRR + SD/Trend/Trade left; OHLC right ────────
    const graph3TopBox = infoBox(
      `<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">` +
      `<div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">` +
        `${dot(ix.trr,'TRR',sd.trr_sd)}${dot(ix.mrr,'MRR',sd.mrr_sd)}${dot(ix.lrr,'LRR',sd.lrr_sd)}` +
        `<span style="color:#94a3b8;font-size:9px;">SD</span><strong style="font-size:9px;">${fmt(sdVal)}</strong>` +
        `<span style="color:#94a3b8;font-size:9px;">Trend</span><strong style="font-size:9px;color:${scoreColor(sd.trend_sd)};">${fmtSd(sd.trend_sd)}</strong>` +
        `<span style="color:#94a3b8;font-size:9px;">Trade</span><strong style="font-size:9px;color:${scoreColor(sd.trade_sd)};">${fmtSd(sd.trade_sd)}</strong>` +
      `</div>` +
      `<div id="${histId}_ohlc" style="font-size:9px;color:#64748b;white-space:nowrap;min-height:13px;text-align:right;flex-shrink:0;"></div>` +
      `</div>`);

    el.innerHTML = `
    <div style="display:grid;grid-template-columns:minmax(220px,1fr) auto auto minmax(320px,3fr);gap:14px;align-items:stretch;width:100%;overflow-x:auto;">

      <!-- Left panel: header (top, aligns with graph) + action line + descriptions + decision -->
      <div style="display:flex;flex-direction:column;gap:6px;min-width:0;">

        <div style="font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.05em;padding:5px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;white-space:nowrap;">
          Risk Range Analysis
        </div>

        <div style="font-size:12px;color:#64748b;display:flex;align-items:center;gap:8px;padding:2px 0;">
          <span>Trend Trade BB Risk Range Rule Action</span>
          ${(() => {
            const _d = window.actionDisplay && ru.action ? window.actionDisplay(ru.action) : null;
            const _cls = _d ? `act-badge ${_d.colorCls}-tint` : 'act-badge act-neutral-tint';
            const _code = _d ? (_d.code || ru.action || '—') : '—';
            return `<span class="${_cls}">${_code}</span>`;
          })()}
        </div>

        <div style="padding:7px 11px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;flex:1;min-height:0;">
          ${taggedRow(null, 'Trend/Trade',     ru.tn_td_desc, ru.tn_td_action)}
          ${taggedRow(null, 'BB Range Streak', ru.bb_desc,   ru.bb_action)}
          ${taggedRow(null, 'RR',              ru.rr_desc,   ru.rr_action)}
          ${rrOutlookRaw ? (() => {
            const olColor = (window.outlookColor ? window.outlookColor(rrOutlookRaw) : null) || '#64748b';
            const olLabel = rrOutlookRaw.charAt(0).toUpperCase() + rrOutlookRaw.slice(1).toLowerCase();
            return `<div style="margin-top:4px;display:flex;align-items:center;gap:6px;font-size:10px;">` +
              `<span style="color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:.04em;font-size:9px;">Outlook</span>` +
              `<span style="font-weight:700;color:${olColor};">${escapeHtml(olLabel)}</span>` +
              `</div>`;
          })() : ''}
        </div>

        <!-- Decision Path -->
        <div style="padding:6px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-family:monospace;font-size:10px;line-height:1.8;">
          ${(() => {
            const qf = ru.tn_td_action, qk = ru.bb_action, qo = ru.rr_action, qr = ru.final_score;
            const vc = v => v == null ? '#94a3b8' : v < 0 ? '#dc2626' : v > 0 ? '#16a34a' : '#64748b';
            const vspan = v => `<span style="font-weight:700;color:${vc(v)};">${v != null ? v : '—'}</span>`;
            const arr = '<span style="color:#4338ca;">→</span>';
            let html = '';
            if (qf == null) return '<span style="color:#94a3b8;">No data</span>';
            if (qf < 0) {
              html = `Trend/Trade ${vspan(qf)} ${arr} <span style="color:#dc2626;">bearish wins</span>`;
            } else if (qf > 0) {
              html = `Trend/Trade ${vspan(qf)} ${arr} <span style="color:#475569;">bullish → check BB</span><br>`;
              if (qk != null && qk < 0) {
                html += `&nbsp;&nbsp;BB Range Streak ${vspan(qk)} ${arr} <span style="color:#dc2626;">bearish wins</span>`;
              } else {
                html += `&nbsp;&nbsp;BB Range Streak ${vspan(qk)} ${arr} <span style="color:#475569;">bullish → use RR</span><br>`;
                html += `&nbsp;&nbsp;&nbsp;&nbsp;RR ${vspan(qo)} ${arr} Score ${vspan(qr)}`;
              }
            } else {
              html = `Trend/Trade ${vspan(qf)} ${arr} <span style="color:#94a3b8;">neutral → null</span>`;
            }
            return html;
          })()}
        </div>

      </div>

      <!-- Column 1: graph only (no top/bottom boxes) -->
      <div style="display:flex;flex-direction:column;">
        <div style="flex:1;display:flex;align-items:center;justify-content:center;padding:6px 0;">
          ${svgToday}
        </div>
      </div>

      <!-- Column 2: graph only (no top/bottom boxes) -->
      <div style="display:flex;flex-direction:column;align-items:center;">
        <div style="flex:1;display:flex;align-items:center;justify-content:center;padding:6px 0;">
          ${svgTT || ''}
        </div>
      </div>

      <!-- Historical chart: combined top bar + graph + bottom bar -->
      <div style="overflow:hidden;display:flex;flex-direction:column;min-width:0;">
        ${graph3TopBox}
        <div style="flex:1;display:flex;align-items:center;justify-content:center;padding:6px 0;">
          <div id="${histId}_wrap" style="width:100%;">${histSvg}</div>
        </div>
        <div style="display:flex;gap:6px;margin-top:2px;">
          ${graph1Box}
          ${graph2Box}
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
          _renderHistChart(svgEl, h, H, lv, symbol);
        })
        .catch(() => {});
    }
  }

  // ── Historical RR line chart ──────────────────────────────────────────────
  function _renderHistChart(svgEl, h, H, levels, symbol) {
    const dates = h.dates;
    const n = dates.length;
    if (!n) return;

    // Client-side backward+forward fill for LRR/TRR
    const lrrs = [...(h.lrr || [])], trrs = [...(h.trr || [])];
    const firstLrr = lrrs.find(v => v != null), firstTrr = trrs.find(v => v != null);
    for (let i = 0; i < n; i++) { if (lrrs[i] == null) lrrs[i] = firstLrr ?? null; else break; }
    for (let i = 0; i < n; i++) { if (trrs[i] == null) trrs[i] = firstTrr ?? null; else break; }

    // Raw OHLC — no fill; bars only rendered where data exists
    const closes = h.price  || [];
    const opens  = h.open   || [];
    const highs  = h.high   || [];
    const lows   = h.low    || [];

    // Forward-fill close only — for the current-price reference line
    const prices = [...closes];
    let lastP = null;
    for (let i = 0; i < n; i++) { if (prices[i] != null) lastP = prices[i]; else if (lastP != null) prices[i] = lastP; }

    const W = Math.max(svgEl.parentElement ? svgEl.parentElement.offsetWidth || 700 : 700, 400);
    const PAD_L = 44, PAD_R = 90, PAD_T = 10, PAD_B = 22;
    const cW = W - PAD_L - PAD_R, cH = H - PAD_T - PAD_B;

    const tradeLevel = levels && levels.trade != null ? levels.trade : null;
    const trendLevel = levels && levels.trend != null ? levels.trend : null;
    const allVals = [...closes, ...opens, ...highs, ...lows, ...lrrs, ...trrs,
                     tradeLevel, trendLevel].filter(v => v != null);
    if (!allVals.length) return;
    const yMin = Math.min(...allVals), yMax = Math.max(...allVals);
    const pad = (yMax - yMin) * 0.05 || 1;
    const yMinP = yMin - pad, yMaxP = yMax + pad, yRangeP = yMaxP - yMinP;

    const nExt = n + 2; // 2 blank slots at the right for breathing room
    const xPx = i => PAD_L + (nExt > 1 ? (i / (nExt - 1)) * cW : cW / 2);
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
      rrFill = `<polygon points="${[...topPts,...botPts].join(' ')}" fill="#fdf2f8" stroke="none"/>`;
    }

    // Right-side labels for latest TRR and LRR
    const latestTrr = [...trrs].reverse().find(v => v != null);
    const latestLrr = [...lrrs].reverse().find(v => v != null);
    const rrLabels = [
      latestTrr != null && latestTrr >= yMinP && latestTrr <= yMaxP
        ? `<text x="${PAD_L+cW+40}" y="${yPx(latestTrr)+4}" fill="#be185d" font-size="9" font-weight="600">TRR ${latestTrr.toFixed(0)}</text>` : '',
      latestLrr != null && latestLrr >= yMinP && latestLrr <= yMaxP
        ? `<text x="${PAD_L+cW+40}" y="${yPx(latestLrr)+4}" fill="#be185d" font-size="9" font-weight="600">LRR ${latestLrr.toFixed(0)}</text>` : '',
    ].join('');

    // Date labels — fit as many as possible without overlap (~30px per label)
    const dateLabel = i => { const d = dates[i]; if (!d) return ''; const p = d.split('-'); return p.length >= 3 ? `${p[1]}/${p[2]}` : d; };
    const maxLbls = Math.max(2, Math.floor(cW / 30));
    const lblStep = Math.max(1, Math.floor((n - 1) / (maxLbls - 1)));
    const lblIdxs = [];
    for (let i = 0; i < n - 1; i += lblStep) lblIdxs.push(i);
    lblIdxs.push(n - 1);
    const xLabels = lblIdxs.map(i =>
      `<text x="${xPx(i).toFixed(1)}" y="${H-4}" fill="#94a3b8" font-size="8" text-anchor="middle">${dateLabel(i)}</text>`
    ).join('');

    // Right Y-axis: price labels at regular intervals + horizontal grid lines
    const _niceStep = r => {
      const rough = r / 5, mag = Math.pow(10, Math.floor(Math.log10(rough || 1)));
      const n = rough / mag;
      return n < 1.5 ? mag : n < 3.5 ? 2*mag : n < 7.5 ? 5*mag : 10*mag;
    };
    const step = _niceStep(yMax - yMin || 1);
    const firstTick = Math.ceil(yMinP / step) * step;
    let rightAxis = '';
    for (let v = firstTick; v <= yMaxP + 0.001; v = Math.round((v + step) * 1e6) / 1e6) {
      if (v < yMinP || v > yMaxP) continue;
      const yv = yPx(v).toFixed(1);
      rightAxis +=
        `<line x1="${PAD_L}" y1="${yv}" x2="${PAD_L+cW}" y2="${yv}" stroke="#e2e8f0" stroke-width="0.5"/>` +
        `<text x="${PAD_L+cW+4}" y="${parseFloat(yv)+3.5}" fill="#64748b" font-size="8" text-anchor="start">${v.toFixed(0)}</text>` +
        `<text x="${PAD_L-4}" y="${parseFloat(yv)+3.5}" fill="#64748b" font-size="8" text-anchor="end">${v.toFixed(0)}</text>`;
    }
    // Max-price badge: computed here, rendered as SVG element later (toggled by hover)
    const priceMax = Math.max(...highs.filter(v => v != null));
    const priceMaxIdx = isFinite(priceMax) ? highs.indexOf(priceMax) : -1;
    const priceMaxDate = priceMaxIdx >= 0 ? dateLabel(priceMaxIdx) : '';
    const priceMaxY = (isFinite(priceMax) && priceMax >= yMinP && priceMax <= yMaxP)
      ? yPx(priceMax) : null;
    const maxPriceBadge = priceMaxY != null
      ? `<rect id="${svgEl.id}_mpbg" x="${PAD_L+4}" y="${(priceMaxY-11).toFixed(1)}" width="38" height="22" rx="2" fill="#475569"/>` +
        `<text id="${svgEl.id}_mpt"  x="${PAD_L+23}" y="${(priceMaxY-4).toFixed(1)}" fill="#fff" font-size="8" font-weight="600" text-anchor="middle" dominant-baseline="middle">${priceMax.toFixed(2)}</text>` +
        `<text id="${svgEl.id}_mpdt" x="${PAD_L+23}" y="${(priceMaxY+6).toFixed(1)}" fill="#94a3b8" font-size="7" text-anchor="middle" dominant-baseline="middle">${priceMaxDate}</text>`
      : '';

    const tradeLine = (tradeLevel != null && tradeLevel >= yMinP && tradeLevel <= yMaxP)
      ? `<line x1="${PAD_L}" y1="${yPx(tradeLevel).toFixed(1)}" x2="${PAD_L+cW+35}" y2="${yPx(tradeLevel).toFixed(1)}" stroke="#f97316" stroke-width="1" stroke-dasharray="5 3"/>` +
        `<text x="${PAD_L+cW+38}" y="${(yPx(tradeLevel)+3.5).toFixed(1)}" fill="#f97316" font-size="8" font-weight="600" text-anchor="start">Trade</text>` : '';
    const trendLine = (trendLevel != null && trendLevel >= yMinP && trendLevel <= yMaxP)
      ? `<line x1="${PAD_L}" y1="${yPx(trendLevel).toFixed(1)}" x2="${PAD_L+cW+35}" y2="${yPx(trendLevel).toFixed(1)}" stroke="#818cf8" stroke-width="1" stroke-dasharray="5 3"/>` +
        `<text x="${PAD_L+cW+38}" y="${(yPx(trendLevel)+3.5).toFixed(1)}" fill="#818cf8" font-size="8" font-weight="600" text-anchor="start">Trend</text>` : '';

    const todayX = xPx(n - 1);
    const todayMark = `<line x1="${todayX}" y1="${PAD_T}" x2="${todayX}" y2="${PAD_T+cH}" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="2 2"/>`;
    const curPrice = prices[n-1];
    const curPriceY = curPrice != null ? yPx(curPrice) : null;
    const curLine = curPriceY != null
      ? `<line x1="${PAD_L}" y1="${curPriceY.toFixed(1)}" x2="${PAD_L+cW}" y2="${curPriceY.toFixed(1)}" stroke="#374151" stroke-width="0.7" stroke-dasharray="3 3"/>` : '';
    const lastPriceBadge = curPriceY != null
      ? `<rect id="${svgEl.id}_lpbg" x="${PAD_L+cW+2}" y="${(curPriceY-7).toFixed(1)}" width="32" height="14" rx="2" fill="#374151"/>` +
        `<text id="${svgEl.id}_lpt" x="${PAD_L+cW+18}" y="${curPriceY.toFixed(1)}" fill="#fff" font-size="8" font-weight="600" text-anchor="middle" dominant-baseline="middle">${curPrice.toFixed(2)}</text>`
      : '';

    // OHLC candlestick bars
    const barW = Math.max(2, (cW / n) * 0.7);
    const candlesticks = closes.map((close, i) => {
      if (close == null) return '';
      const open = opens[i] ?? close, high = highs[i] ?? close, low = lows[i] ?? close;
      const isUp = close >= open;
      const clr = isUp ? '#16a34a' : '#dc2626';
      const x = xPx(i);
      const bodyTop = yPx(Math.max(close, open)).toFixed(1);
      const bodyBot = yPx(Math.min(close, open)).toFixed(1);
      const bodyH = Math.max(parseFloat(bodyBot) - parseFloat(bodyTop), 1).toFixed(1);
      return `<line x1="${x.toFixed(1)}" y1="${yPx(high).toFixed(1)}" x2="${x.toFixed(1)}" y2="${yPx(low).toFixed(1)}" stroke="${clr}" stroke-width="1"/>` +
             `<rect x="${(x - barW/2).toFixed(1)}" y="${bodyTop}" width="${barW.toFixed(1)}" height="${bodyH}" fill="${clr}"/>`;
    }).join('');

    svgEl.setAttribute('width', W);
    svgEl.innerHTML = `
      ${rightAxis}
      ${rrFill}
      ${todayMark}${curLine}
      ${tradeLine}${trendLine}
      ${stepPolyline(trrs, '#ec4899', 1.5, '5 3')}
      ${stepPolyline(lrrs, '#ec4899', 1.5, '5 3')}
      ${candlesticks}
      ${rrLabels}${xLabels}
      ${lastPriceBadge}
      ${maxPriceBadge}
      <line id="${svgEl.id}_chv" x1="0" y1="${PAD_T}" x2="0" y2="${PAD_T+cH}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4 3" display="none" pointer-events="none"/>
      <line id="${svgEl.id}_chh" x1="${PAD_L}" y1="0" x2="${PAD_L+cW}" y2="0" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4 3" display="none" pointer-events="none"/>
      <rect id="${svgEl.id}_chxbg" width="32" height="13" rx="2" fill="#475569" display="none" pointer-events="none"/>
      <text id="${svgEl.id}_chxt"  fill="#fff" font-size="8" text-anchor="middle" dominant-baseline="middle" display="none" pointer-events="none"/>
      <rect id="${svgEl.id}_chybg" width="40" height="22" rx="2" fill="#374151" display="none" pointer-events="none"/>
      <text id="${svgEl.id}_chyt"  fill="#fff" font-size="8" font-weight="600" text-anchor="middle" dominant-baseline="middle" display="none" pointer-events="none"/>
      <text id="${svgEl.id}_chydt" fill="#94a3b8" font-size="7" text-anchor="middle" dominant-baseline="middle" display="none" pointer-events="none"/>
    `;

    // ── OHLC hover: update top box on mouse move, revert to last day on leave ─
    const ohlcEl = document.getElementById(svgEl.id + '_ohlc');
    const lastIdx = closes.reduceRight((a, v, i) => a < 0 && v != null ? i : a, -1);

    const fmtOHLC = i => {
      const d = dates[i], o = opens[i], hv = highs[i], l = lows[i], c = closes[i];
      if (c == null) return '';
      const fmt = v => v != null ? Number(v).toFixed(2) : '—';
      const clr = c >= (o ?? c) ? '#16a34a' : '#dc2626';
      const ds = d ? d.slice(5).replace('-', '/') : '';
      return `<span style="color:#94a3b8;">${ds}</span>` +
             ` <span>O <b>${fmt(o)}</b></span>` +
             ` <span style="margin-left:6px;">H <b>${fmt(hv)}</b></span>` +
             ` <span style="margin-left:6px;">L <b>${fmt(l)}</b></span>` +
             ` <span style="margin-left:6px;color:${clr};">C <b>${fmt(c)}</b></span>`;
    };

    if (ohlcEl && lastIdx >= 0) ohlcEl.innerHTML = fmtOHLC(lastIdx);

    const wrap = svgEl.parentElement;
    const chV   = document.getElementById(svgEl.id + '_chv');
    const chH   = document.getElementById(svgEl.id + '_chh');
    const chXbg = document.getElementById(svgEl.id + '_chxbg');
    const chXt  = document.getElementById(svgEl.id + '_chxt');
    const chYbg = document.getElementById(svgEl.id + '_chybg');
    const chYt  = document.getElementById(svgEl.id + '_chyt');
    const chYdt = document.getElementById(svgEl.id + '_chydt');
    const lpBg  = document.getElementById(svgEl.id + '_lpbg');
    const lpT   = document.getElementById(svgEl.id + '_lpt');
    const mpBg  = document.getElementById(svgEl.id + '_mpbg');
    const mpT   = document.getElementById(svgEl.id + '_mpt');
    const mpDt  = document.getElementById(svgEl.id + '_mpdt');

    const showCH = show => {
      [chV, chH, chXbg, chXt, chYbg, chYt, chYdt].forEach(el => {
        if (!el) return;
        if (show) el.removeAttribute('display'); else el.setAttribute('display', 'none');
      });
      // static badges (last price + max price): hide while hovering
      [lpBg, lpT, mpBg, mpT, mpDt].forEach(el => {
        if (!el) return;
        if (show) el.setAttribute('display', 'none'); else el.removeAttribute('display');
      });
    };

    if (wrap) {
      wrap.addEventListener('mousemove', e => {
        const rect = svgEl.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const ix = Math.max(0, Math.min(n - 1, Math.round((mx - PAD_L) / cW * (nExt - 1))));
        if (ohlcEl && closes[ix] != null) ohlcEl.innerHTML = fmtOHLC(ix);

        const cx = xPx(ix);
        const cy = Math.max(PAD_T, Math.min(PAD_T + cH, my));

        if (chV) { chV.setAttribute('x1', cx); chV.setAttribute('x2', cx); }
        if (chH) { chH.setAttribute('y1', cy); chH.setAttribute('y2', cy); }

        // Date label on x-axis
        const dlbl = dateLabel(ix);
        if (chXbg) { chXbg.setAttribute('x', cx - 16); chXbg.setAttribute('y', PAD_T + cH + 2); }
        if (chXt)  { chXt.setAttribute('x', cx); chXt.setAttribute('y', PAD_T + cH + 8); chXt.textContent = dlbl; }

        // Price + date badge on LEFT y-axis — snap to candle close price
        const closePrice = closes[ix];
        if (closePrice != null) {
          const pval = closePrice.toFixed(2);
          const pY = yPx(closePrice);
          if (chYbg) { chYbg.setAttribute('x', PAD_L + 4);  chYbg.setAttribute('y', (pY - 11).toFixed(1)); }
          if (chYt)  { chYt.setAttribute('x', PAD_L + 24);  chYt.setAttribute('y', (pY - 4).toFixed(1));  chYt.textContent = pval; }
          if (chYdt) { chYdt.setAttribute('x', PAD_L + 24); chYdt.setAttribute('y', (pY + 5).toFixed(1)); chYdt.textContent = dlbl; }
        }

        showCH(true);
      });
      wrap.addEventListener('mouseleave', () => {
        if (ohlcEl && lastIdx >= 0) ohlcEl.innerHTML = fmtOHLC(lastIdx);
        showCH(false);
      });

      // Click → expand chart into full-viewport modal
      wrap.style.cursor = 'crosshair';
      wrap.addEventListener('click', () => {
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9999;display:flex;align-items:center;justify-content:center;';

        const box = document.createElement('div');
        box.style.cssText = 'background:#fff;border-radius:8px;padding:16px 16px 8px;width:94vw;height:88vh;display:flex;flex-direction:column;position:relative;box-shadow:0 20px 60px rgba(0,0,0,0.4);';

        const closeBtn = document.createElement('button');
        closeBtn.textContent = '×';
        closeBtn.style.cssText = 'position:absolute;top:8px;right:12px;font-size:22px;line-height:1;border:none;background:transparent;cursor:pointer;color:#64748b;';
        closeBtn.onclick = () => document.body.removeChild(overlay);

        // Symbol + OHLC header
        const header = document.createElement('div');
        header.style.cssText = 'display:flex;align-items:center;gap:12px;margin-bottom:6px;';
        const symSpan = document.createElement('span');
        symSpan.textContent = symbol || '';
        symSpan.style.cssText = 'font-size:18px;font-weight:700;color:#1e293b;';

        const newSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        newSvg.id = 'rrHistExp_' + Math.random().toString(36).slice(2);
        newSvg.setAttribute('width', '100%');
        newSvg.style.cssText = 'overflow:visible;display:block;';

        const ohlcDiv = document.createElement('div');
        ohlcDiv.id = newSvg.id + '_ohlc';
        ohlcDiv.style.cssText = 'font-size:11px;color:#64748b;';
        header.appendChild(symSpan);
        header.appendChild(ohlcDiv);

        const svgWrap = document.createElement('div');
        svgWrap.style.cssText = 'flex:1;width:100%;overflow:hidden;';
        svgWrap.appendChild(newSvg);

        box.appendChild(closeBtn);
        box.appendChild(header);
        box.appendChild(svgWrap);
        overlay.appendChild(box);
        document.body.appendChild(overlay);

        // Render at full box height after layout
        requestAnimationFrame(() => {
          const bigH = svgWrap.clientHeight || Math.floor(window.innerHeight * 0.8);
          newSvg.setAttribute('height', bigH);
          _renderHistChart(newSvg, h, bigH, levels, symbol);
        });

        overlay.addEventListener('click', ev => { if (ev.target === overlay) document.body.removeChild(overlay); });
      });
    }
  }

  // ── Percent Ring ──────────────────────────────────────────────────────────
  // pctRing(value, opts) -> SVG string. value is in PERCENT units (42 = 42%, 300 = 300%).
  // Each 100% adds a concentric ring working inward: outermost = first loop, next = second, etc.
  // Colors: green (1st), deep-green (2nd), amber (3rd), red (4th+).
  // null/undefined/<=0 -> empty track ring. Tooltip shows exact value.
  function pctRing(value, opts) {
    opts = opts || {};
    var size  = opts.size   || 22;
    var sw    = opts.stroke || 2;
    var gap   = opts.gap    || 1;
    var track = opts.track  || '#eef0f3';
    var c = size / 2;
    var v = (value == null || isNaN(value)) ? null : Number(value);
    var label = v == null ? '—' : Math.round(v) + '%';
    // opts.color overrides all ring colors with a single hue (caller picks green/red/etc.)
    var baseColor = opts.color || null;
    var COLORS = baseColor
      ? [baseColor, baseColor, baseColor, baseColor]
      : ['#22c55e', '#16a34a', '#f59e0b', '#ef4444'];

    var svg = '<svg width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+
              '" role="img" aria-label="'+label+'"><title>'+label+'</title>';

    if (v == null || v <= 0) {
      var r0 = c - sw / 2;
      svg += '<circle cx="'+c+'" cy="'+c+'" r="'+r0+'" fill="none" stroke="'+track+'" stroke-width="'+sw+'"/>';
      return svg + '</svg>';
    }

    var laps = Math.floor(v / 100);
    var frac = (v % 100) / 100;
    var maxRings = Math.floor(c / (sw + gap));
    var totalRings = laps + (frac > 0 ? 1 : 0);
    var rings = Math.min(totalRings, maxRings);

    for (var i = 0; i < rings; i++) {
      var r = c - sw / 2 - i * (sw + gap);
      var C = 2 * Math.PI * r;
      var color = COLORS[Math.min(i, COLORS.length - 1)];
      // track
      svg += '<circle cx="'+c+'" cy="'+c+'" r="'+r+'" fill="none" stroke="'+track+'" stroke-width="'+sw+'"/>';
      if (i < laps) {
        // complete loop
        svg += '<circle cx="'+c+'" cy="'+c+'" r="'+r+'" fill="none" stroke="'+color+'" stroke-width="'+sw+'"/>';
      } else if (frac > 0) {
        // partial arc for the current incomplete loop
        svg += '<circle cx="'+c+'" cy="'+c+'" r="'+r+'" fill="none" stroke="'+color+
               '" stroke-width="'+sw+'" stroke-linecap="round" stroke-dasharray="'+
               (frac*C).toFixed(2)+' '+C.toFixed(2)+'" transform="rotate(-90 '+c+' '+c+')"/>';
      }
    }
    return svg + '</svg>';
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
    pctRing,
  };
  // TASK_58: expose helpers directly on window so pages that previously defined
  // their own local copies can remove them and use the canonical versions without
  // updating every call site.
  window.fetchJson    = fetchJson;
  window.escapeHtml   = escapeHtml;
  window.fmtUsd       = fmtUsd;
  window.fmtPct       = fmtPct;
  window.fmtDate      = fmtDate;
  window.fmtNum       = fmtNum;
  // fetchJSON is a common alias used in ref.js, dbstats.js, explore.js, trig.js
  window.fetchJSON    = fetchJson;
  window.yahooLink    = yahooLink;
  window.pctRing      = pctRing;
})();
