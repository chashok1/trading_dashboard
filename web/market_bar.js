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
  const INVERTED = new Set(['VIX', 'VXN', 'VXD', 'RVX', 'OVX', 'GVZ', 'MOVE', 'HY', 'HYSPRD']);

  // Display pairs: [idx metric_key, vol metric_key | null for standalone]
  const PAIRS = [
    { idx: 'SPX',  vol: 'VIX'  },
    { idx: 'COMP', vol: 'VXN'  },
    { idx: 'DJI',  vol: 'VXD'  },
    { idx: 'RUT',  vol: 'RVX'  },
    { idx: 'WTI',  vol: 'OVX'  },
    { idx: 'GC',   vol: 'GVZ'  },
    { idx: 'MOVE', vol: null   },
  ];

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

  // ---- cell helpers -------------------------------------------------------

  function itemTip(item, valStr, chgStr, arrow) {
    const parts = [`${item.label}: ${valStr}`];
    if (chgStr) parts.push(`${arrow}${chgStr}`);
    parts.push(`source: ${item.source || '?'}, as of: ${item.as_of || '?'}`);
    if (item.stale) parts.push('stale');
    return escHtml(parts.join('  '));
  }

  function itemContent(item) {
    const valStr = fmtValue(item.value, item.value_format);
    const chgStr = fmtChgPct(item.chg_pct);
    const arrow  = dirArrow(item.chg_pct);
    const cls    = dirClass(item.chg_pct, item.metric_key);
    const tip    = itemTip(item, valStr, chgStr, arrow);
    // level → show value colored; pct → show value plain; else → show % change
    let inner;
    if (item.value_format === 'level') {
      inner = `<span class="mt-value ${cls}">${valStr}</span>`;
    } else if (item.value_format === 'pct') {
      inner = `<span class="mt-value">${valStr}</span>`;
    } else {
      inner = chgStr
        ? `<span class="mt-chg ${cls}">${arrow}${chgStr}</span>`
        : `<span class="mt-value">${valStr}</span>`;
    }
    return { tip, inner };
  }

  // ---- shared chip helpers -----------------------------------------------

  function outlookBg(outlook) {
    const ol = (outlook || '').toLowerCase();
    return ol === 'bullish' ? '#15803d'
         : ol === 'bearish' ? '#b91c1c'
         : '#64748b';
  }

  function rangeBar(buy, sell, cur) {
    if (buy == null || sell == null || sell <= buy || cur == null) {
      return '<div class="rr-rb"></div>';
    }
    const pct = Math.max(0, Math.min(1, (Number(cur) - Number(buy)) / (Number(sell) - Number(buy))));
    const w = Math.round(pct * 100);
    return `<div class="rr-rb">` +
      `<div class="rr-rb-fill" style="width:${w}%;"></div>` +
      `<div class="rr-rb-tick" style="left:${w}%;"></div>` +
      `</div>`;
  }

  function chipHtml(name, ol, pctStr, pctCls, buy, sell, cur, tip, stale) {
    const staleCls = stale ? ' mt-stale' : '';
    return `<div class="rr-chip${staleCls}" title="${tip}">` +
      `<div class="rr-chip-top">` +
      `<span class="rr-sym" style="background:${outlookBg(ol)};">${escHtml(name)}</span>` +
      `<span class="mt-chg ${pctCls}">${pctStr}</span>` +
      `</div>` +
      rangeBar(buy, sell, cur) +
      `</div>`;
  }

  // ---- build tape row (bar 1) -------------------------------------------
  function buildTapeHtml(data) {
    const items = data.items || [];
    const byKey = Object.fromEntries(items.map(it => [it.metric_key, it]));
    const seen  = new Set();
    const cells = [];

    for (const pair of PAIRS) {
      for (const key of [pair.idx, pair.vol].filter(Boolean)) {
        const item = byKey[key];
        if (!item) continue;
        seen.add(key);
        const cls    = dirClass(item.chg_pct, item.metric_key);
        const chgStr = fmtChgPct(item.chg_pct);
        const arrow  = dirArrow(item.chg_pct);
        const valStr = fmtValue(item.value, item.value_format);
        const pctStr = chgStr ? arrow + chgStr : valStr;
        const tip    = itemTip(item, valStr, chgStr, arrow);
        cells.push(chipHtml(item.metric_key, item.rr_outlook, pctStr, cls,
                            item.rr_buy, item.rr_sell, item.value, tip, item.stale));
      }
    }

    for (const item of items) {
      if (seen.has(item.metric_key)) continue;
      const cls    = dirClass(item.chg_pct, item.metric_key);
      const chgStr = fmtChgPct(item.chg_pct);
      const arrow  = dirArrow(item.chg_pct);
      const valStr = fmtValue(item.value, item.value_format);
      const pctStr = chgStr ? arrow + chgStr : valStr;
      const tip    = itemTip(item, valStr, chgStr, arrow);
      cells.push(chipHtml(item.metric_key, item.rr_outlook, pctStr, cls,
                          item.rr_buy, item.rr_sell, item.value, tip, item.stale));
    }

    cells.push(`<button class="mt-expander" id="mtExpandBtn" type="button" aria-expanded="false" title="Show full econ panel">Econ ▾</button>`);
    return cells.join('');
  }

  // ---- build RR tape (bar 2) — chips, no category headers ---------------
  const RR_CAT_ORDER = ['Commodities', 'ETFs', 'Tech', 'Indexes', 'FX', 'Credit', 'Other'];

  function buildRrHtml(data) {
    const groups = data.groups || {};
    const allCats = [...RR_CAT_ORDER, ...Object.keys(groups).filter(k => !RR_CAT_ORDER.includes(k))];
    const cells = [];

    for (const cat of allCats) {
      const items = groups[cat];
      if (!items || !items.length) continue;
      for (const item of items) {
        const pct    = item.pct != null ? Number(item.pct) : null;
        const cls    = dirClass(pct, null);
        const chgStr = pct != null ? (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%' : '—';
        const name   = (item.symbol || '').replace(/^\//, '') || item.label || '?';
        const buyStr = item.buy != null ? Number(item.buy).toFixed(2) : '—';
        const sellStr = item.sell != null ? Number(item.sell).toFixed(2) : '—';
        const tip    = escHtml(
          `${item.label || item.symbol}  ${chgStr}` +
          (item.buy != null ? `  range: ${buyStr}–${sellStr}` : '') +
          (item.outlook ? `  ${item.outlook}` : '') +
          (item.as_of ? `  as of: ${item.as_of}` : '')
        );
        cells.push(chipHtml(name, item.outlook, chgStr, cls,
                            item.buy, item.sell, item.bar_price, tip, false));
      }
    }
    return cells.join('');
  }

  // ---- build econ expander panel ----------------------------------------
  function buildEconHtml(macro) {
    const groups = macro.groups || {};
    const entries = Object.entries(groups);
    if (!entries.length) return '<span style="color:var(--text-3);font-size:11px;">No econ data available.</span>';

    return entries.map(([groupName, items]) => {
      const rows = (items || []).map(item => {
        // Format value using unit: '%' → fixed 2 dp + '%', else toLocaleString 2 dp
        let val;
        if (item.latest_value !== null && item.latest_value !== undefined) {
          const n = Number(item.latest_value);
          val = (item.unit === '%')
            ? n.toFixed(2) + '%'
            : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        } else {
          val = '—';
        }

        const chgRaw = (item.chg_abs !== null && item.chg_abs !== undefined) ? Number(item.chg_abs) : null;
        const chgStr = chgRaw !== null
          ? (chgRaw >= 0 ? '+' : '') + chgRaw.toFixed(2)
          : '';
        const chgCls = chgRaw === null ? '' : chgRaw > 0 ? 'mt-up' : chgRaw < 0 ? 'mt-down' : 'mt-flat';

        // Tooltip: label, date, and optional pct change
        const pctPart = (item.chg_pct !== null && item.chg_pct !== undefined)
          ? ` (${Number(item.chg_pct).toFixed(2)}%)`
          : '';
        const tip = escHtml(`${item.label} — as of: ${item.latest_date || '?'}${pctPart}`);

        // Format latest_date (YYYY-MM-DD) → mm/dd, guard against null/missing
        let dateLbl = '--';
        if (item.latest_date && /^\d{4}-\d{2}-\d{2}$/.test(item.latest_date)) {
          const parts = item.latest_date.split('-');
          dateLbl = parts[1] + '/' + parts[2];
        }

        return `<div class="mt-econ-row" title="${tip}">` +
          `<span class="mt-econ-name">${escHtml(item.label)}</span>` +
          `<span class="mt-econ-val">${val}</span>` +
          (chgStr ? `<span class="mt-econ-chg ${chgCls}">${chgStr}</span>` : '') +
          `<span class="mt-econ-date">${dateLbl}</span>` +
          `</div>`;
      }).join('');

      return `<div class="mt-econ-group">` +
        `<div class="mt-econ-group-label">${escHtml(groupName)}</div>` +
        rows +
        `</div>`;
    }).join('');
  }

  // ---- DOM mount --------------------------------------------------------
  let tapeEl = null;
  let econEl = null;
  let rrTapeEl = null;

  function ensureMount() {
    if (tapeEl) return;

    const topbar = document.querySelector('header.topbar');
    if (!topbar) return;

    // Bar 1 — market pairs tape
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

    // Bar 2 — RR symbols tape
    rrTapeEl = document.createElement('div');
    rrTapeEl.id = 'rrTape';
    rrTapeEl.className = 'rr-tape';
    rrTapeEl.innerHTML = '<span style="color:var(--text-3);padding:0 8px;font-size:11px;">Loading RR data…</span>';
    econEl.insertAdjacentElement('afterend', rrTapeEl);

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

  async function loadRrBar() {
    ensureMount();
    if (!rrTapeEl) return;
    try {
      const r = await fetch('/api/rr-bar');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      rrTapeEl.innerHTML = buildRrHtml(data);
    } catch (err) {
      if (rrTapeEl) {
        rrTapeEl.innerHTML =
          '<span style="color:var(--bear,#b91c1c);padding:0 8px;font-size:11px;">RR data unavailable</span>';
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
    loadRrBar();
    setInterval(() => { loadTape(); loadRrBar(); }, REFRESH_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
