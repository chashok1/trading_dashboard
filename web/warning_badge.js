/* Trading Dashboard — warning badge in topbar
 *
 * Self-mounting widget loaded on every page. Shows a count badge in the topbar
 * .controls area (next to refresh button). Polls /api/warnings for system-level
 * warnings (ETL/derive errors, stale data). Pages can push their own warnings
 * via window.warnBadge.setPage() / .addPage().
 *
 * Click the badge to expand/collapse a dropdown panel with warning details.
 */
(function () {
  'use strict';

  const POLL_MS = 5 * 60 * 1000;  // 5 minutes
  const STATE = { apiWarnings: [], pageWarnings: [], anchorWarning: [], expanded: false };

  // ---- styles (injected once) ----------------------------------------------
  function injectStyles() {
    if (document.getElementById('wbStyles')) return;
    const css = `
      #warnBadge { position: relative; display: inline-flex; align-items: center; }
      #warnBadge[hidden] { display: none; }

      #warnBtn {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 5px 10px;
        border-radius: 4px;
        border: 1px solid #ccc;
        background: #f5f5f7;
        color: #555;
        font-size: 12px;
        cursor: pointer;
        font-weight: 500;
      }
      #warnBtn:hover { background: #e8e8ec; }
      #warnBtn.active-warning {
        background: #fef3c7;
        border-color: #f0d97a;
        color: #5b4900;
      }
      #warnBtn.active-warning:hover {
        background: #fce8a6;
      }
      #warnBtn.active-error {
        background: #fee2e2;
        border-color: #e6a4a4;
        color: #8c1d1d;
      }
      #warnBtn.active-error:hover {
        background: #fdcdcd;
      }

      #warnPanel {
        position: fixed;
        top: 68px;
        left: auto;
        right: 12px;
        background: #fff;
        border: 1px solid var(--border, #e0e0e0);
        border-radius: 6px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        width: 380px;
        max-width: calc(100vw - 24px);
        max-height: calc(100vh - 100px);
        overflow-y: auto;
        z-index: 1001;
        display: none;
      }
      #warnPanel[open] { display: block; }

      .wb-header {
        padding: 8px 12px;
        border-bottom: 1px solid var(--border, #ececec);
        font-weight: 600;
        font-size: 12px;
        color: var(--text-2, #666);
        text-transform: uppercase;
        letter-spacing: 0.4px;
      }
      .wb-items { padding: 0; }
      .wb-item {
        padding: 8px 12px;
        border-bottom: 1px solid var(--border, #ececec);
        font-size: 11px;
      }
      .wb-item:last-child { border-bottom: none; }
      .wb-item.warning { border-left: 3px solid #f0d97a; background: #fffbf0; }
      .wb-item.error   { border-left: 3px solid #e6a4a4; background: #fef7f7; }

      .wb-item-title {
        font-weight: 600;
        color: #333;
        margin-bottom: 2px;
      }
      .wb-item.warning .wb-item-title { color: #5b4900; }
      .wb-item.error .wb-item-title   { color: #8c1d1d; }

      .wb-item-detail {
        font-size: 10px;
        color: var(--text-2, #666);
        margin-bottom: 3px;
      }
      .wb-item-subs {
        margin-top: 3px;
        padding-left: 12px;
        font-size: 10px;
        color: var(--text-2, #777);
      }
      .wb-item-sub { margin-bottom: 2px; }
      .wb-item-sub::before { content: '• '; opacity: 0.6; }

      #warnPanel::-webkit-scrollbar { width: 6px; }
      #warnPanel::-webkit-scrollbar-track { background: transparent; }
      #warnPanel::-webkit-scrollbar-thumb { background: #d0d0d0; border-radius: 3px; }
      #warnPanel::-webkit-scrollbar-thumb:hover { background: #999; }

      /* Date control highlighted when the loaded data is behind the latest
         market close (see /api/anchor-status). */
      #datePicker.date-stale, select.date-stale {
        border: 2px solid #f59e0b !important;
        background: #fff7ed !important;
        color: #92400e !important;
        font-weight: 600;
        box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.30);
      }
    `;
    const tag = document.createElement('style');
    tag.id = 'wbStyles';
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  // ---- DOM construction ------------------------------------------------
  function mount() {
    if (document.getElementById('warnBadge')) return;
    const controls = document.querySelector('.controls');
    if (!controls) return;

    const badge = document.createElement('div');
    badge.id = 'warnBadge';
    badge.hidden = true;
    badge.innerHTML = `
      <button id="warnBtn" type="button">[!] <span id="warnCount">0</span></button>
      <div id="warnPanel">
        <div class="wb-header" style="display:flex; justify-content:space-between; align-items:center;">
          <span>Warnings</span>
          <button id="warnFixBtn" style="background:#0a84ff; color:#fff; border:none; border-radius:4px; padding:3px 10px; font-size:11px; cursor:pointer; font-weight:600;">Fix...</button>
        </div>
        <div class="wb-items" id="warnItems"></div>
      </div>
    `;

    const healthBadge = controls.querySelector('#health');
    if (healthBadge) {
      controls.insertBefore(badge, healthBadge);
    } else {
      controls.appendChild(badge);
    }

    // Wire up click to toggle
    document.getElementById('warnBtn').addEventListener('click', togglePanel);
    // Fix button opens health banner's rebuild modal
    const fixBtn = document.getElementById('warnFixBtn');
    if (fixBtn) {
      fixBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        // Open the rebuild modal (provided by rebuild_modal.js)
        if (window.hbRebuildModal) window.hbRebuildModal.open();
        else alert('Rebuild tool not available');
      });
    }
    // Click outside to close
    document.addEventListener('click', (e) => {
      const btn = document.getElementById('warnBtn');
      const panel = document.getElementById('warnPanel');
      if (!badge.contains(e.target) && STATE.expanded) {
        STATE.expanded = false;
        panel.removeAttribute('open');
      }
    });
  }

  // ---- rendering --------------------------------------------------
  function render() {
    const all = [...STATE.anchorWarning, ...STATE.apiWarnings, ...STATE.pageWarnings];
    const unique = {};
    for (const w of all) {
      if (!unique[w.id]) unique[w.id] = w;
    }
    const warnings = Object.values(unique);

    const badge = document.getElementById('warnBadge');
    const btn = document.getElementById('warnBtn');
    const panel = document.getElementById('warnPanel');
    const count = document.getElementById('warnCount');
    const items = document.getElementById('warnItems');

    if (warnings.length === 0) {
      badge.hidden = true;
      return;
    }

    badge.hidden = false;
    count.textContent = warnings.length;

    // Determine severity: red if any error, amber otherwise
    const hasError = warnings.some(w => w.level === 'error');
    btn.classList.remove('active-warning', 'active-error');
    btn.classList.add(hasError ? 'active-error' : 'active-warning');

    // Render items
    items.innerHTML = warnings.map(w => {
      const subs = (w.items || []).slice(0, 5).map(it => `
        <div class="wb-item-sub">${escapeHtml(it.label || it.title || '')}</div>
      `).join('');
      return `
        <div class="wb-item ${w.level || 'warning'}">
          <div class="wb-item-title">${escapeHtml(w.title || '')}</div>
          ${w.items && w.items.length ? `<div class="wb-item-subs">${subs}</div>` : ''}
        </div>
      `;
    }).join('');
  }

  function togglePanel() {
    STATE.expanded = !STATE.expanded;
    const panel = document.getElementById('warnPanel');
    if (STATE.expanded) {
      panel.setAttribute('open', '');
    } else {
      panel.removeAttribute('open');
    }
  }

  // escapeHtml is provided by _common.js (window.escapeHtml).

  // ---- polling --------------------------------------------------------
  async function poll() {
    // Single source: /api/warnings aggregates ETL/derive failures, the
    // meta_warning table, and the derive-status health checks.
    try {
      const r = await fetch('/api/warnings');
      if (r.ok) {
        const ws = await r.json();
        STATE.apiWarnings = (Array.isArray(ws) ? ws : []).map(w => ({
          id: w.id,
          level: w.level === 'error' ? 'error' : 'warning',
          title: w.title || w.id || 'Warning',
          items: w.items || [],
        }));
      }
    } catch (_) { /* silent */ }

    // Anchor staleness: is the loaded data behind the latest market close?
    // Request-time check (depends on the current clock). When stale, raise a
    // toolbar warning AND highlight the #datePicker control.
    try {
      const ar = await fetch('/api/anchor-status');
      if (ar.ok) applyAnchorStatus(await ar.json());
    } catch (_) { /* silent */ }

    render();
  }

  function applyAnchorStatus(st) {
    const sel = document.getElementById('datePicker');
    if (st && st.is_stale) {
      STATE.anchorWarning = [{
        id: 'anchor-stale',
        level: 'warning',
        title: st.message || 'Loaded data is behind the latest market close.',
        items: [],
      }];
      if (sel) {
        sel.classList.add('date-stale');
        sel.title = st.message || 'Data behind latest market close';
      }
    } else {
      STATE.anchorWarning = [];
      if (sel) {
        sel.classList.remove('date-stale');
        sel.removeAttribute('title');
      }
    }
  }

  // ---- public API -----------------------------------------------------
  window.warnBadge = {
    setPage: (warnings) => {
      STATE.pageWarnings = warnings || [];
      render();
    },
    addPage: (warnings) => {
      STATE.pageWarnings.push(...(warnings || []));
      render();
    },
    clearPage: () => {
      STATE.pageWarnings = [];
      render();
    },
  };

  // ---- entry ----------------------------------------------------------
  function init() {
    injectStyles();
    mount();
    poll();
    setInterval(poll, POLL_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
