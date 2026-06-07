/* Trading Dashboard — global market tape
 *
 * Self-mounting widget. Injects a slim horizontal ribbon (28px) below the
 * topbar on every page.  Fed by GET /api/marketbar (read-only, no FRED calls).
 * A ▾ toggle at the end opens an econ expander panel (GET /api/macro).
 *
 * Color convention: green = "good", red = "bad".
 *   Normal:   up → green, down → red  (indexes, DXY, WTI, rates)
 *   Inverted: up → red,  down → green (VIX, HY — risk/stress metrics)
 */
(function () {
  'use strict';

  const REFRESH_MS = 60 * 1000;  // auto-refresh every 60 s

  // Metric keys whose direction is inverted (up = bad / red)
  const INVERTED = new Set(['VIX', 'HY', 'HYSPRD']);

  // ---- formatting helpers -----------------------------------------------
  function fmtValue(v, fmt) {
    if (v === null || v === undefined) return '—';
    switch (fmt) {
      case 'index':
      case 'price':
        return Number(v).toLocaleString('en-US', {
          minimumFractionDigits: 2, maximumFractionDigits: 2
        });
      case 'pct':
        return Number(v).toFixed(2) + '%';
      case 'level':
        return Number(v).toFixed(1);
      default:
        return String(v);
    }
  }

  function fmtChgPct(chg_pct) {
    if (chg_pct === null || chg_pct === undefined) return '';
    const n = Number(chg_pct);
    const sign = n > 0 ? '+' : '';
    return sign + n.toFixed(2) + '%';
  }

  function dirClass(chg_pct, metric_key) {
    if (chg_pct === null || chg_pct === undefined) return 'mt-flat';
    const n = Number(chg_pct);
    if (Math.abs(n) < 0.001) return 'mt-flat';
    const inverted = INVERTED.has((metric_key || '').toUpperCase());
    if (inverted) {
      return n > 0 ? 'mt-down' : 'mt-up';
    }
    return n > 0 ? 'mt-up' : 'mt-down';
  }

  function dirArrow(chg_pct) {
    if (chg_pct === null || chg_pct === undefined) return '';
    const n = Number(chg_pct);
    if (Math.abs(n) < 0.001) return '';
    return n > 0 ? '▲' : '▼';
  }

  function escHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  // ---- build tape row ---------------------------------------------------
  function buildTapeHtml(data) {
    const items = data.items || [];
    const asOf = data.as_of || '';

    const cells = items.map(item => {
      const val    = fmtValue(item.value, item.value_format);
      const chg    = fmtChgPct(item.chg_pct);
      const arrow  = dirArrow(item.chg_pct);
      const cls    = dirClass(item.chg_pct, item.metric_key);
      const stale  = item.stale ? ' mt-stale' : '';
      const tip    = escHtml(
        `${item.label} — source: ${item.source || '?'}, as of: ${item.as_of || '?'}`
        + (item.stale ? ' (stale)' : '')
      );
      return `<div class="mt-cell${stale}" title="${tip}">` +
        `<span class="mt-label">${escHtml(item.label)}</span>` +
        `<span class="mt-value">${val}</span>` +
        (chg ? `<span class="mt-chg ${cls}">${arrow}${chg}</span>` : '') +
        `</div>`;
    }).join('');

    return (
      `<span class="mt-asof">as of ${escHtml(asOf)}</span>` +
      cells +
      `<button class="mt-expander" id="mtExpandBtn" type="button" aria-expanded="false" title="Show full econ panel">Econ ▾</button>`
    );
  }

  // ---- build econ expander panel ----------------------------------------
  function buildEconHtml(macro) {
    const groups = macro.groups || [];
    if (!groups.length) return '<span style="color:var(--text-3);font-size:11px;">No econ data available.</span>';

    return groups.map(grp => {
      const rows = (grp.items || []).map(item => {
        const val = item.value !== null && item.value !== undefined
          ? Number(item.value).toLocaleString('en-US', { maximumFractionDigits: 2 })
          : '—';
        const chgRaw = item.chg !== null && item.chg !== undefined ? Number(item.chg) : null;
        const chgStr = chgRaw !== null
          ? (chgRaw >= 0 ? '+' : '') + chgRaw.toFixed(2)
          : '';
        const chgCls = chgRaw === null ? '' : chgRaw > 0 ? 'mt-up' : chgRaw < 0 ? 'mt-down' : 'mt-flat';
        const stale  = item.stale ? ' mt-econ-stale' : '';
        const tip    = escHtml(`${item.label} — as of: ${item.as_of || '?'}` + (item.stale ? ' (stale)' : ''));
        return `<div class="mt-econ-row${stale}" title="${tip}">` +
          `<span class="mt-econ-name">${escHtml(item.label)}</span>` +
          `<span class="mt-econ-val">${val}</span>` +
          (chgStr ? `<span class="mt-econ-chg ${chgCls}">${chgStr}</span>` : '') +
          `</div>`;
      }).join('');

      return `<div class="mt-econ-group">` +
        `<div class="mt-econ-group-label">${escHtml(grp.group || grp.label || '')}</div>` +
        rows +
        `</div>`;
    }).join('');
  }

  // ---- DOM mount --------------------------------------------------------
  let tapeEl = null;
  let econEl = null;

  function ensureMount() {
    if (tapeEl) return;

    const topbar = document.querySelector('header.topbar');
    if (!topbar) return;

    // Tape strip
    tapeEl = document.createElement('div');
    tapeEl.id = 'marketTape';
    tapeEl.className = 'market-tape';
    tapeEl.innerHTML = '<span style="color:var(--text-3);padding:0 8px;font-size:11px;">Loading market data…</span>';
    topbar.insertAdjacentElement('afterend', tapeEl);

    // Econ panel (hidden by default)
    econEl = document.createElement('div');
    econEl.id = 'mtEconPanel';
    econEl.className = 'mt-econ-panel';
    econEl.innerHTML = '<span style="color:var(--text-3);font-size:11px;">Loading…</span>';
    tapeEl.insertAdjacentElement('afterend', econEl);

    // Expand/collapse toggle (delegated — button injected after fetch)
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('#mtExpandBtn');
      if (!btn) return;
      const open = econEl.classList.toggle('open');
      btn.setAttribute('aria-expanded', String(open));
      btn.textContent = open ? 'Econ ▴' : 'Econ ▾';
      if (open && !econEl.dataset.loaded) {
        loadEcon();
      }
    });
  }

  // ---- fetch & render ---------------------------------------------------
  async function loadTape() {
    ensureMount();
    if (!tapeEl) return;

    try {
      const r = await fetch('/api/marketbar');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      tapeEl.innerHTML = buildTapeHtml(data);
    } catch (err) {
      if (tapeEl) {
        tapeEl.innerHTML =
          '<span style="color:var(--bear,#b91c1c);padding:0 8px;font-size:11px;">Market data unavailable</span>';
      }
    }
  }

  async function loadEcon() {
    if (!econEl) return;
    try {
      const r = await fetch('/api/macro');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      econEl.innerHTML = buildEconHtml(data);
      econEl.dataset.loaded = '1';
    } catch (err) {
      if (econEl) {
        econEl.innerHTML =
          '<span style="color:var(--bear,#b91c1c);font-size:11px;">Econ data unavailable</span>';
      }
    }
  }

  // ---- entry ------------------------------------------------------------
  function init() {
    loadTape();
    setInterval(loadTape, REFRESH_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
