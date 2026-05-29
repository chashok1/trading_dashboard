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
  // renderRRAnalysis(data, el) — render the Risk Range chart + stats into `el`.
  // `data` is the JSON from /api/actionable/rr-analysis.
  function renderRRAnalysis(data, el) {
    if (!data) { el.innerHTML = '<p style="color:#888;font-size:12px;">No Risk Range data available.</p>'; return; }
    const p = data.price   || {};
    const lv = data.levels || {};
    const sd = data.sd     || {};
    const ix = data.idx    || {};
    const ru = data.rules  || {};

    const cur       = p.current;
    const prev      = p.prev_close;
    const hi        = p.high;
    const lo        = p.low;
    const trend     = lv.trend;
    const trade     = lv.trade;
    const lrr       = lv.lrr;
    const mrr       = lv.mrr;
    const trr       = lv.trr;
    const sdVal     = sd.value;

    const fmt = v => v == null ? '—' : Number(v).toFixed(2);
    const fmtSd = v => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2);

    // ── Score colour helpers ──────────────────────────────────────────────────
    const scoreColor = v => v == null ? '#999' : v > 0 ? '#16a34a' : v < 0 ? '#dc2626' : '#94a3b8';
    const scoreClass = v => v == null ? 'rr-neutral' : v > 0 ? 'rr-bull' : v < 0 ? 'rr-bear' : 'rr-neutral';
    const dotHtml = v => `<span class="rr-dot ${scoreClass(v)}"></span>`;

    // ── SVG chart ─────────────────────────────────────────────────────────────
    // Y range: clip to RR bands ± 1 SD, show Trend/Trade as out-of-range labels
    const W = 180, H = 200, PAD_L = 52, PAD_R = 8, PAD_T = 14, PAD_B = 14;
    const chartW = W - PAD_L - PAD_R;
    const chartH = H - PAD_T - PAD_B;

    const vals = [cur, prev, hi, lo, lrr, trr].filter(v => v != null);
    const rawMin = Math.min(...vals);
    const rawMax = Math.max(...vals);
    const padding = sdVal ? sdVal * 0.4 : (rawMax - rawMin) * 0.08;
    const yMin = rawMin - padding;
    const yMax = rawMax + padding;
    const yRange = yMax - yMin || 1;

    const yPx = v => PAD_T + chartH * (1 - (v - yMin) / yRange);
    const x0  = PAD_L;
    const x1  = PAD_L + chartW;
    const xMid = PAD_L + chartW * 0.42;

    // out-of-range labels (Trend / Trade below chart)
    const outLabels = [];
    if (trend != null && trend < yMin) outLabels.push({ name: 'Trend', val: trend });
    if (trade != null && trade < yMin) outLabels.push({ name: 'Trade', val: trade });

    function hline(y, color, dash, label, align = 'right') {
      const labelX = align === 'right' ? x1 + 3 : x0 - 3;
      const anchor = align === 'right' ? 'start' : 'end';
      return `<line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}" stroke="${color}" stroke-width="1" stroke-dasharray="${dash}"/>
              <text x="${labelX}" y="${y + 4}" fill="${color}" font-size="9" text-anchor="${anchor}" font-weight="600">${label}</text>`;
    }

    function priceBar() {
      if (cur == null && prev == null) return '';
      const y1 = yPx(Math.max(cur ?? prev, prev ?? cur));
      const y2 = yPx(Math.min(cur ?? prev, prev ?? cur));
      const barH = Math.max(y2 - y1, 2);
      const isUp = (cur ?? prev) >= (prev ?? cur);
      const fill = isUp ? '#16a34a' : '#dc2626';
      const stroke = isUp ? '#15803d' : '#b91c1c';
      const barX = xMid - 10;
      const barW = 20;
      // Wick lines (high/low from drv_quote)
      const wickTop    = hi   != null ? `<line x1="${xMid}" y1="${yPx(hi)}"  x2="${xMid}" y2="${y1}" stroke="${fill}" stroke-width="1.5"/>` : '';
      const wickBottom = lo   != null ? `<line x1="${xMid}" y1="${y2}"       x2="${xMid}" y2="${yPx(lo)}" stroke="${fill}" stroke-width="1.5"/>` : '';
      return `${wickTop}${wickBottom}
              <rect x="${barX}" y="${y1}" width="${barW}" height="${barH}" fill="${fill}" stroke="${stroke}" stroke-width="1" rx="1"/>`;
    }

    // RR zone fill (between LRR and TRR)
    const rrZone = (lrr != null && trr != null)
      ? `<rect x="${x0}" y="${yPx(trr)}" width="${chartW}" height="${yPx(lrr)-yPx(trr)}" fill="#f0fdf4" stroke="none"/>`
      : '';

    // Dashed reference lines for in-range levels
    const lines = [];
    if (trr  != null && trr  >= yMin && trr  <= yMax) lines.push(hline(yPx(trr),  '#16a34a', '4 2', `TRR ${fmt(trr)}`));
    if (mrr  != null && mrr  >= yMin && mrr  <= yMax) lines.push(hline(yPx(mrr),  '#4ade80', '2 3', `MRR ${fmt(mrr)}`));
    if (lrr  != null && lrr  >= yMin && lrr  <= yMax) lines.push(hline(yPx(lrr),  '#16a34a', '4 2', `LRR ${fmt(lrr)}`));
    if (trade != null && trade >= yMin) lines.push(hline(yPx(trade), '#f97316', '3 2', `Trade ${fmt(trade)}`));
    if (trend != null && trend >= yMin) lines.push(hline(yPx(trend), '#6366f1', '3 2', `Trend ${fmt(trend)}`));

    // Y-axis labels (prev close + current price)
    const yLabels = [];
    if (prev != null) yLabels.push(`<text x="${x0-4}" y="${yPx(prev)+4}" fill="#64748b" font-size="9" text-anchor="end">${fmt(prev)}</text>`);
    if (cur  != null) yLabels.push(`<text x="${x0-4}" y="${yPx(cur)+4}"  fill="#1e293b" font-size="9" text-anchor="end" font-weight="700">${fmt(cur)}</text>`);

    const svg = `<svg width="${W}" height="${H}" style="overflow:visible;">
      ${rrZone}
      ${lines.join('\n')}
      ${priceBar()}
      ${yLabels.join('\n')}
      <text x="${xMid}" y="${H - 2}" fill="#94a3b8" font-size="8" text-anchor="middle">▲ today ▼ prev</text>
    </svg>`;

    // ── KI/KJ/KK right panel ─────────────────────────────────────────────────
    const idxRows = [
      { name: 'TRR Idx', sd: sd.trr_sd, score: ix.trr, level: fmt(trr) },
      { name: 'MRR Idx', sd: sd.mrr_sd, score: ix.mrr, level: fmt(mrr) },
      { name: 'LRR Idx', sd: sd.lrr_sd, score: ix.lrr, level: fmt(lrr) },
    ].map(r => `
      <tr>
        <td style="padding:3px 6px 3px 0; font-size:11px; font-weight:600; color:#374151;">${r.name}</td>
        <td style="padding:3px 4px; font-size:11px; font-family:monospace; color:#64748b;">${fmtSd(r.sd)} SD</td>
        <td style="padding:3px 4px; text-align:center;">${dotHtml(r.score)}</td>
        <td style="padding:3px 0 3px 4px; font-size:11px; font-weight:700; color:${scoreColor(r.score)};">${r.score ?? '—'}</td>
        <td style="padding:3px 0 3px 6px; font-size:10px; color:#94a3b8;">${r.level}</td>
      </tr>`).join('');

    // ── Rule score pills ──────────────────────────────────────────────────────
    const pill = (label, val, desc) => {
      const c = scoreColor(val);
      return `<span style="display:inline-flex;flex-direction:column;align-items:center;
        background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;
        padding:4px 8px;min-width:48px;gap:1px;">
        <span style="font-size:9px;color:#94a3b8;font-weight:600;">${label}</span>
        <span style="font-size:16px;font-weight:700;color:${c};line-height:1;">${val ?? '—'}</span>
        ${desc ? `<span style="font-size:8px;color:#64748b;white-space:nowrap;">${desc}</span>` : ''}
      </span>`;
    };

    const actionCode = ru.action || '—';
    const priority   = ru.priority != null ? ru.priority : '—';
    const actionBull = ['B','BM','BS','BN','BMN','BRW','BW','BSW','BR','BC'].includes(actionCode);
    const actionBear = ['SA','S','STM','SS','SO','SW','SWW','SN'].includes(actionCode);
    const actionColor = actionBull ? '#16a34a' : actionBear ? '#dc2626' : '#64748b';

    // ── Assemble layout ───────────────────────────────────────────────────────
    el.innerHTML = `
    <style>
      .rr-dot { display:inline-block; width:8px; height:8px; border-radius:50%; }
      .rr-bull { background:#16a34a; }
      .rr-bear { background:#dc2626; }
      .rr-neutral { background:#94a3b8; }
    </style>
    <div style="display:flex; gap:16px; align-items:flex-start; flex-wrap:wrap;">

      <!-- Chart -->
      <div style="flex-shrink:0;">${svg}</div>

      <!-- Right: KI/KJ/KK + SD stats -->
      <div style="flex:1; min-width:200px;">
        <table style="border-collapse:collapse; margin-bottom:10px;">
          <thead><tr>
            <th style="font-size:10px;color:#94a3b8;font-weight:600;text-align:left;padding:0 6px 4px 0;">Index</th>
            <th style="font-size:10px;color:#94a3b8;font-weight:600;padding:0 4px 4px;">Distance</th>
            <th colspan="2" style="font-size:10px;color:#94a3b8;font-weight:600;padding:0 4px 4px;">Score</th>
            <th style="font-size:10px;color:#94a3b8;font-weight:600;padding:0 0 4px 6px;">Level</th>
          </tr></thead>
          <tbody>${idxRows}</tbody>
        </table>

        <div style="font-size:11px; color:#475569; margin-bottom:10px; display:flex; gap:14px; flex-wrap:wrap;">
          <span><span style="color:#94a3b8;">SD</span> <strong>${fmt(sdVal)}</strong></span>
          <span><span style="color:#94a3b8;">Trend SD</span> <strong style="color:${scoreColor(sd.trend_sd)}">${fmtSd(sd.trend_sd)}</strong></span>
          <span><span style="color:#94a3b8;">Trade SD</span> <strong style="color:${scoreColor(sd.trade_sd)}">${fmtSd(sd.trade_sd)}</strong></span>
        </div>

        <!-- QE/QJ/QM/QN rule pills -->
        <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px;">
          ${pill('Trend/Trade', ru.trend_trade, ru.tn_td_desc ? ru.tn_td_desc.slice(0,18) : null)}
          ${pill('BB Streak',   ru.bb_streak,   ru.bb_desc || null)}
          ${pill('Bull RR',     ru.bull_rr,     null)}
          ${pill('Not-Bull RR', ru.not_bull_rr, null)}
        </div>

        <!-- Final action box -->
        <div style="display:flex; align-items:center; gap:10px;
          background:#f0fdf4; border:2px solid ${actionColor};
          border-radius:8px; padding:8px 14px;">
          <div style="text-align:center;">
            <div style="font-size:9px;color:#94a3b8;font-weight:600;">SCORE</div>
            <div style="font-size:20px;font-weight:700;color:#374151;line-height:1;">${ru.final_score ?? '—'}</div>
          </div>
          <div style="font-size:20px;color:#94a3b8;">→</div>
          <div style="text-align:center;">
            <div style="font-size:9px;color:#94a3b8;font-weight:600;">ACTION</div>
            <div style="font-size:22px;font-weight:800;color:${actionColor};line-height:1;">${actionCode}</div>
          </div>
          <div style="flex:1; font-size:11px; color:#475569; line-height:1.4;">
            ${ru.tn_td_desc ? `<div style="color:#64748b;">${ru.tn_td_desc}</div>` : ''}
            <div style="color:#94a3b8; font-size:10px;">priority ${priority}</div>
          </div>
        </div>

        ${outLabels.length ? `<div style="font-size:10px;color:#94a3b8;margin-top:6px;">${outLabels.map(l=>`${l.name}: ${fmt(l.val)}`).join(' &nbsp;·&nbsp; ')} (below chart range)</div>` : ''}
      </div>
    </div>`;
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
