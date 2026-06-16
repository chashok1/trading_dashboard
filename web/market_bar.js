/* Trading Dashboard — global market tape
 *
 * Self-mounting widget. Injects three sticky ribbons below the topbar:
 *   Bar 1 (#marketTape)  — index/vol pairs + rates + commodities + bonds
 *   Bar 2 (#rrTape)      — ETFs + Commodities  (curated, with group labels)
 *   Bar 3 (#rrTape3)     — Tech + FX + Indexes (curated, with group labels)
 *
 * The Econ panel (#econPanel) is a static div in the page HTML (actionable.html).
 * It is toggled by #econBtn and lazily loaded from GET /api/macro.
 *
 * Color convention: green = "good", red = "bad".
 *   Normal:   up → green, down → red  (indexes, DXY, WTI, rates)
 *   Inverted: up → red,  down → green (VIX, HY — risk/stress metrics)
 */
(function () {
  'use strict';

  const REFRESH_MS = 60 * 1000;

  const INVERTED = new Set(['VIX', 'VXN', 'VXD', 'RVX', 'OVX', 'GVZ', 'MOVE', 'HY', 'HYSPRD']);

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
    if (item.rr_outlook) parts.push(`Outlook: ${item.rr_outlook}`);
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
    return ol === 'bullish' ? '#2f9e2f'
         : ol === 'bearish' ? '#d83a3a'
         : '#888';
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
    const pctBg = pctCls === 'mt-up' ? '#2f9e2f' : pctCls === 'mt-down' ? '#d83a3a' : null;
    const pctBoxStyle = pctBg ? `background:${pctBg};color:#fff;padding:1px 5px;border-radius:3px;` : 'color:#94a3b8;';
    return `<div class="rr-chip${staleCls}" data-sym="${escHtml(name)}" title="${tip}" style="cursor:pointer;">` +
      `<div class="rr-chip-top">` +
      `<span class="rr-sym" style="color:${outlookBg(ol)};">${escHtml(name)}</span>` +
      `<span class="mt-chg" style="${pctBoxStyle}">${pctStr}</span>` +
      `</div>` +
      rangeBar(buy, sell, cur) +
      `</div>`;
  }

  // ---- build tape row (bar 1) — explicit labeled groups -----------------
  const BAR1_GROUPS = [
    { label: 'Eq',    keys: ['SPX', 'VIX', 'COMP', 'VXN', 'DJI', 'VXD', 'RUT', 'RVX'] },
    { label: 'Cmdty', keys: ['WTI', 'BZ', 'OVX', 'GC', 'GVZ'] },
    { label: 'FX',    keys: ['DXY', 'MOVE'] },
  ];

  function buildTapeHtml(data) {
    const items = data.items || [];
    const byKey = Object.fromEntries(items.map(it => [it.metric_key, it]));
    const cells = [];

    for (const grp of BAR1_GROUPS) {
      const grpCells = [];
      for (const key of grp.keys) {
        const item = byKey[key];
        if (!item) continue;
        const cls    = dirClass(item.chg_pct, item.metric_key);
        const chgStr = fmtChgPct(item.chg_pct);
        const arrow  = dirArrow(item.chg_pct);
        const valStr = fmtValue(item.value, item.value_format);
        const pctStr = chgStr ? arrow + chgStr : valStr;
        const tip    = itemTip(item, valStr, chgStr, arrow);
        grpCells.push(chipHtml(item.label || item.metric_key, item.rr_outlook, pctStr, cls,
                               item.rr_buy, item.rr_sell, item.value, tip, item.stale));
      }
      if (!grpCells.length) continue;
      cells.push(`<span class="rr-cat">${escHtml(grp.label)}</span>`);
      cells.push(...grpCells);
    }

    return cells.join('');
  }

  // ---- build RR bar (bar 2 or 3) — chips with inline group headings ----
  const BAR2_CATS = ['ETFs', 'Commodities', 'Credit'];
  const BAR3_CATS = ['Rates', 'Tech', 'FX', 'Crypto'];
  const CAT_SHORT  = {
    'ETFs': 'ETF', 'Commodities': 'Cmdty', 'Credit': 'Crd',
    'Rates': 'Rates', 'Tech': 'Tech', 'FX': 'FX', 'Indexes': 'Idx', 'Crypto': 'Crypt',
  };

  function buildRrBarHtml(data, cats) {
    const groups = data.groups || {};
    const cells = [];
    for (const cat of cats) {
      const items = groups[cat];
      if (!items || !items.length) continue;
      cells.push(`<span class="rr-cat">${escHtml(CAT_SHORT[cat] || cat)}</span>`);
      for (const item of items) {
        const pct    = item.pct != null ? Number(item.pct) : null;
        const cls    = dirClass(pct, null);
        const chgStr = pct != null ? (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%' : '—';
        const name   = item.label || (item.symbol || '').replace(/^\//, '') || '?';
        const buyStr = item.buy != null ? Number(item.buy).toFixed(2) : '—';
        const sellStr = item.sell != null ? Number(item.sell).toFixed(2) : '—';
        const tip    = escHtml(
          `${item.label || item.symbol}  ${chgStr}` +
          (item.buy != null ? `  range: ${buyStr}–${sellStr}` : '') +
          (item.outlook ? `  Outlook: ${item.outlook}` : '') +
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

        const pctPart = (item.chg_pct !== null && item.chg_pct !== undefined)
          ? ` (${Number(item.chg_pct).toFixed(2)}%)`
          : '';
        const tip = escHtml(`${item.label} — as of: ${item.latest_date || '?'}${pctPart}`);

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
  let tapeEl    = null;
  let rrTapeEl  = null;
  let rrTape3El = null;

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

    // Bar 2 — ETFs + Commodities
    rrTapeEl = document.createElement('div');
    rrTapeEl.id = 'rrTape';
    rrTapeEl.className = 'rr-tape';
    rrTapeEl.innerHTML = '<span style="color:var(--text-3);padding:0 8px;font-size:11px;">Loading…</span>';
    tapeEl.insertAdjacentElement('afterend', rrTapeEl);

    // Bar 3 — Tech + FX + Indexes
    rrTape3El = document.createElement('div');
    rrTape3El.id = 'rrTape3';
    rrTape3El.className = 'rr-tape';
    rrTape3El.innerHTML = '<span style="color:var(--text-3);padding:0 8px;font-size:11px;">Loading…</span>';
    rrTapeEl.insertAdjacentElement('afterend', rrTape3El);

    // Wire #econBtn → #econPanel (only present on pages that include it, e.g. actionable)
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('#econBtn');
      if (!btn) return;
      const panel = document.getElementById('econPanel');
      if (!panel) return;
      const open = panel.classList.toggle('open');
      btn.innerHTML = open ? 'Econ &#9652;' : 'Econ &#9662;';
      btn.classList.toggle('active', open);
      if (open && !panel.dataset.loaded) loadEcon();
    });
  }

  // ---- fetch & render ---------------------------------------------------
  async function loadTape() {
    ensureMount();
    if (!tapeEl) return;

    try {
      const [mktRes, rrRes] = await Promise.all([
        fetch('/api/marketbar'),
        fetch('/api/rr-bar'),
      ]);
      if (!mktRes.ok) throw new Error('HTTP ' + mktRes.status);
      if (!rrRes.ok)  throw new Error('HTTP ' + rrRes.status);
      const [mktData, rrData] = await Promise.all([mktRes.json(), rrRes.json()]);
      tapeEl.innerHTML = buildTapeHtml(mktData) + buildRrBarHtml(rrData, ['Indexes']);
    } catch (err) {
      if (tapeEl) {
        tapeEl.innerHTML =
          '<span style="color:var(--bear,#b91c1c);padding:0 8px;font-size:11px;">Market data unavailable</span>';
      }
    }
  }

  async function loadRrBar() {
    ensureMount();
    if (!rrTapeEl || !rrTape3El) return;
    try {
      const r = await fetch('/api/rr-bar');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      rrTapeEl.innerHTML  = buildRrBarHtml(data, BAR2_CATS);
      const econOpen = (document.getElementById('econPanel') || {}).classList
                       && document.getElementById('econPanel').classList.contains('open');
      rrTape3El.innerHTML = buildRrBarHtml(data, BAR3_CATS) +
        `<button id="econBtn" class="mt-expander${econOpen ? ' active' : ''}" type="button" title="Toggle FRED macro panel">Econ ${econOpen ? '&#9652;' : '&#9662;'}</button>`;
    } catch (err) {
      const msg = '<span style="color:var(--bear,#b91c1c);padding:0 8px;font-size:11px;">RR data unavailable</span>';
      if (rrTapeEl)  rrTapeEl.innerHTML  = msg;
      if (rrTape3El) rrTape3El.innerHTML = msg;
    }
  }

  async function loadEcon() {
    const panel = document.getElementById('econPanel');
    if (!panel) return;
    try {
      const r = await fetch('/api/macro');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      panel.innerHTML = buildEconHtml(data);
      panel.dataset.loaded = '1';
    } catch (err) {
      if (panel) {
        panel.innerHTML =
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
