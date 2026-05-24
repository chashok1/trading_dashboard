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
  };
  window.yahooLink = yahooLink;
})();
