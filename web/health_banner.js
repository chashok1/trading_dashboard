/* Trading Dashboard — shared health banner
 *
 * Self-mounting widget loaded on every page. Polls /api/health/derive-status
 * every 60s and inserts a banner under the topbar when any check fails. Click
 * the banner to expand details; "Fix" opens a modal that POSTs to
 * /api/admin/rebuild for the last N days. Stays out of the way when healthy.
 *
 * Add via:  <script src="/static/health_banner.js"></script>
 * (No CSS file needed — styles are injected inline.)
 */
(function () {
  'use strict';

  const POLL_MS = 60 * 1000;
  const STATE = { lastPayload: null, expanded: false };

  // ---- styles (injected once) ----------------------------------------------
  function injectStyles() {
    if (document.getElementById('hbStyles')) return;
    const css = `
      #hbBanner {
        display: none;
        background: #fff8e1;
        border-bottom: 1px solid #f0d97a;
        color: #5b4900;
        font-size: 12px;
        padding: 6px 14px;
        line-height: 1.6;
      }
      #hbBanner.warning { background: #fff8e1; border-color: #f0d97a; color: #5b4900; }
      #hbBanner.error   { background: #fbeaea; border-color: #e6a4a4; color: #8c1d1d; }
      #hbBanner.show    { display: block; }
      #hbBanner .hb-icon { font-weight: 700; margin-right: 6px; }
      #hbBanner .hb-summary { font-weight: 600; }
      #hbBanner .hb-toggle  { font-size: 10px; opacity: 0.7; margin-left: 8px; }
      #hbBanner .hb-fix-btn {
        float: right;
        background: #fff;
        border: 1px solid currentColor;
        border-radius: 4px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        color: inherit;
        margin-left: 8px;
      }
      #hbBanner .hb-fix-btn:hover { background: rgba(0,0,0,0.05); }
      #hbDetails {
        display: none;
        margin-top: 6px;
        padding: 8px 10px;
        background: rgba(255,255,255,0.5);
        border-radius: 4px;
        font-size: 11px;
        user-select: text;
        cursor: text;
      }
      #hbDetails.show { display: block; }
      #hbDetails .check { padding: 3px 0; border-bottom: 1px dashed rgba(0,0,0,0.1); }
      #hbDetails .check:last-child { border-bottom: none; }
      #hbDetails .check.ok    { color: #1c6c30; }
      #hbDetails .check.warn  { color: #5b4900; }
      #hbDetails .check.error { color: #8c1d1d; }
      #hbDetails .check .title { font-weight: 600; }
      #hbDetails .check .detail { opacity: 0.85; }
      #hbDetails .check .items {
        margin: 3px 0 0 14px;
        font-family: ui-monospace, "SF Mono", Menlo, monospace;
        font-size: 10px;
        opacity: 0.85;
        user-select: text;
        cursor: text;
      }
      #hbCopyWarningsBtn {
        margin-top: 6px;
        padding: 4px 8px;
        font-size: 11px;
        background: #fff;
        border: 1px solid #f0d97a;
        border-radius: 3px;
        cursor: pointer;
        color: #5b4900;
        font-weight: 600;
        display: none;
      }
      #hbCopyWarningsBtn:hover { background: #fffef0; }
      #hbCopyWarningsBtn:active { background: #fff5e0; }

      /* Fix modal */
      #hbModalBackdrop {
        position: fixed; inset: 0;
        background: rgba(0,0,0,0.4);
        display: none;
        z-index: 1000;
        align-items: center; justify-content: center;
      }
      #hbModalBackdrop.open { display: flex; }
      #hbModal {
        background: #fff;
        border-radius: 8px;
        width: 440px;
        max-width: 92vw;
        box-shadow: 0 12px 40px rgba(0,0,0,0.25);
        padding: 18px 22px;
        font-size: 13px;
      }
      #hbModal h3 { margin: 0 0 8px; font-size: 16px; }
      #hbModal p  { color: #555; margin: 0 0 12px; }
      #hbModal .row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
      #hbModal label { font-size: 12px; color: #555; }
      #hbModal select {
        padding: 4px 8px; font-size: 12px;
        border: 1px solid #ddd; border-radius: 4px;
      }
      #hbModal .btn {
        padding: 5px 14px; font-size: 12px;
        border-radius: 4px; cursor: pointer; border: 1px solid #ccc;
        background: #f5f5f7;
      }
      #hbModal .btn-primary { background: #0a84ff; color: #fff; border-color: #0a84ff; }
      #hbModal .btn-primary:hover { filter: brightness(0.95); }
      #hbModal .btn-primary[disabled] { opacity: 0.55; cursor: progress; }
      #hbModal .result {
        margin-top: 10px;
        padding: 8px;
        background: #f5f5f7;
        border-radius: 4px;
        font-size: 11px;
        max-height: 200px;
        overflow-y: auto;
        font-family: ui-monospace, Menlo, monospace;
        white-space: pre-wrap;
        display: none;
        user-select: text;
        cursor: text;
        word-wrap: break-word;
        line-height: 1.4;
      }
      #hbModal .result.show { display: block; }
      #hbModal .copy-btn {
        margin-top: 8px;
        padding: 5px 14px;
        font-size: 11px;
        border-radius: 4px;
        cursor: pointer;
        border: 1px solid #ccc;
        background: #f5f5f7;
      }
      #hbModal .copy-btn:hover { background: #e8e8ea; }
      #hbModal .copy-btn:active { background: #d8d8da; }
    `;
    const tag = document.createElement('style');
    tag.id = 'hbStyles';
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  // ---- DOM construction ----------------------------------------------------
  function mountBanner() {
    if (document.getElementById('hbBanner')) return;
    const banner = document.createElement('div');
    banner.id = 'hbBanner';
    banner.innerHTML = `
      <button class="hb-fix-btn" id="hbFixBtn">Fix…</button>
      <span class="hb-icon">[!]</span>
      <span class="hb-summary" id="hbSummary">Checking…</span>
      <span class="hb-toggle" id="hbToggle">(click for details)</span>
      <div id="hbDetails"></div>
      <button id="hbCopyWarningsBtn">Copy warnings</button>
    `;
    // Insert after the topbar if present, else as first child of <body>
    const top = document.querySelector('header.topbar');
    if (top && top.parentNode) {
      top.parentNode.insertBefore(banner, top.nextSibling);
    } else {
      document.body.insertBefore(banner, document.body.firstChild);
    }

    banner.addEventListener('click', (e) => {
      // Don't toggle when the Fix button or Copy button is clicked
      if (e.target.closest('#hbFixBtn') || e.target.closest('#hbCopyWarningsBtn')) return;
      STATE.expanded = !STATE.expanded;
      document.getElementById('hbDetails').classList.toggle('show', STATE.expanded);
    });
    document.getElementById('hbFixBtn').addEventListener('click', (e) => {
      e.stopPropagation();
      openFixModal();
    });
    document.getElementById('hbCopyWarningsBtn').addEventListener('click', (e) => {
      e.stopPropagation();
      copyWarnings();
    });
  }

  function mountModal() {
    if (document.getElementById('hbModalBackdrop')) return;
    const wrap = document.createElement('div');
    wrap.id = 'hbModalBackdrop';
    wrap.innerHTML = `
      <div id="hbModal" role="dialog" aria-modal="true">
        <h3>Rebuild derived tables</h3>
        <p>
          Re-runs <code>derive_outlook_action</code> + <code>derive_actionable</code> for
          the last N dashboard dates. Use after editing reference data (outlook
          weights, source priorities, asset allocation) or to backfill missing
          dates.
        </p>
        <div class="row">
          <label for="hbDays">Rebuild last</label>
          <select id="hbDays">
            <option value="1">1 day</option>
            <option value="3" selected>3 days</option>
            <option value="7">7 days</option>
            <option value="14">14 days</option>
            <option value="30">30 days</option>
          </select>
        </div>
        <div class="row" style="justify-content:flex-end; gap:6px;">
          <button class="btn" id="hbCancelBtn">Cancel</button>
          <button class="btn btn-primary" id="hbRebuildBtn">Rebuild now</button>
        </div>
        <div class="result" id="hbResult"></div>
        <button class="copy-btn" id="hbCopyBtn" style="display:none;">Copy result</button>
      </div>
    `;
    document.body.appendChild(wrap);

    document.getElementById('hbCancelBtn').addEventListener('click', closeFixModal);
    document.getElementById('hbRebuildBtn').addEventListener('click', runRebuild);
    document.getElementById('hbCopyBtn').addEventListener('click', copyResult);
    document.getElementById('hbResult').addEventListener('click', (e) => { e.stopPropagation(); });
    wrap.addEventListener('click', (e) => { if (e.target === wrap) closeFixModal(); });
  }

  function openFixModal() {
    document.getElementById('hbResult').classList.remove('show');
    document.getElementById('hbResult').textContent = '';
    document.getElementById('hbRebuildBtn').disabled = false;
    document.getElementById('hbRebuildBtn').textContent = 'Rebuild now';
    document.getElementById('hbCopyBtn').style.display = 'none';
    document.getElementById('hbModalBackdrop').classList.add('open');
  }

  function copyResult() {
    const text = document.getElementById('hbResult').textContent;
    navigator.clipboard.writeText(text).then(() => {
      const btn = document.getElementById('hbCopyBtn');
      const original = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = original; }, 2000);
    }).catch(() => {
      alert('Failed to copy to clipboard');
    });
  }
  function closeFixModal() {
    document.getElementById('hbModalBackdrop').classList.remove('open');
  }

  async function runRebuild() {
    const days = Number(document.getElementById('hbDays').value);
    const btn = document.getElementById('hbRebuildBtn');
    const result = document.getElementById('hbResult');
    btn.disabled = true;
    btn.textContent = 'Rebuilding…';
    result.classList.add('show');
    result.textContent = 'POST /api/admin/rebuild { days: ' + days + ' } …\n';
    try {
      const r = await fetch('/api/admin/rebuild', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days }),
      });
      const data = await r.json();
      if (!r.ok) {
        result.textContent += 'ERROR: ' + (data.detail || r.statusText);
        return;
      }
      let lines = [data.summary, ''];
      for (const e of (data.rebuilt || [])) {
        const tag = e.ok ? 'OK  ' : 'FAIL';
        lines.push(`${tag} ${e.date}  outlook=${e.drv_outlook_action_rows}  actionable=${e.drv_actionable_rows}` +
                   (e.error ? '   ' + e.error : ''));
      }
      result.textContent += lines.join('\n');
      document.getElementById('hbCopyBtn').style.display = 'inline-block';
      // Refresh the health status immediately
      poll();
    } catch (e) {
      result.textContent += 'ERROR: ' + e.message;
      document.getElementById('hbCopyBtn').style.display = 'inline-block';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Run again';
    }
  }

  // ---- rendering -----------------------------------------------------------
  function render(payload) {
    STATE.lastPayload = payload;
    const banner = document.getElementById('hbBanner');
    if (!banner) return;
    if (!payload || payload.ok) {
      banner.classList.remove('show', 'warning', 'error');
      document.getElementById('hbCopyWarningsBtn').style.display = 'none';
      return;
    }
    // Severity = error if any check has severity:'error', else warning
    const hasError = (payload.checks || []).some(c => c.severity === 'error');
    banner.classList.remove('warning', 'error');
    banner.classList.add('show', hasError ? 'error' : 'warning');

    document.getElementById('hbSummary').textContent = payload.summary || '';

    // Details
    const det = document.getElementById('hbDetails');
    det.innerHTML = (payload.checks || []).map(c => {
      const cls = c.ok ? 'ok' : (c.severity === 'error' ? 'error' : 'warn');
      const items = (c.items || []).slice(0, 5).map(it => {
        try { return JSON.stringify(it); } catch (_) { return String(it); }
      });
      const itemsHtml = items.length
        ? `<div class="items">${items.map(escapeHtml).join('<br>')}</div>`
        : '';
      return `
        <div class="check ${cls}">
          <span class="title">${escapeHtml(c.title || c.id)}</span>
          — <span class="detail">${escapeHtml(c.detail || '')}</span>
          ${itemsHtml}
        </div>`;
    }).join('');
    det.classList.toggle('show', STATE.expanded);
    // Show the Copy-warnings button whenever there's at least one non-OK check.
    document.getElementById('hbCopyWarningsBtn').style.display =
      payload.checks && payload.checks.some(c => !c.ok) ? 'inline-block' : 'none';
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
    })[c]);
  }

  // ---- copy-warnings (clipboard) -------------------------------------------
  async function copyWarnings() {
    if (!STATE.lastPayload) return;
    const lines = [`Trading Dashboard health — ${STATE.lastPayload.checked_at || ''}`,
                   `Summary: ${STATE.lastPayload.summary || ''}`,
                   ''];
    for (const c of (STATE.lastPayload.checks || [])) {
      if (c.ok) continue;
      lines.push(`[${c.severity || 'warn'}] ${c.title || c.id}: ${c.detail || ''}`);
      for (const it of (c.items || [])) {
        try { lines.push('   ' + JSON.stringify(it)); }
        catch (_) { lines.push('   ' + String(it)); }
      }
    }
    const text = lines.join('\n');
    try {
      await navigator.clipboard.writeText(text);
      const btn = document.getElementById('hbCopyWarningsBtn');
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = orig; }, 1200);
    } catch (_) {
      // Fallback: select-all in a hidden textarea
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed'; ta.style.left = '-9999px';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (__) { /* */ }
      document.body.removeChild(ta);
    }
  }

  // ---- polling -------------------------------------------------------------
  async function poll() {
    try {
      const r = await fetch('/api/health/derive-status');
      if (!r.ok) return;
      const payload = await r.json();
      render(payload);
    } catch (_) { /* silent on network blips */ }
  }

  // ---- entry ---------------------------------------------------------------
  function init() {
    injectStyles();
    // Skip banner if warning badge is active (it shows the same info)
    // But always mount modal so warning badge Fix button can use it
    if (!window.warnBadge) {
      mountBanner();
      poll();
      setInterval(poll, POLL_MS);
    }
    mountModal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
