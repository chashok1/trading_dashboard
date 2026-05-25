/* Trading Dashboard — rebuild-modal provider (formerly the health banner)
 *
 * Self-mounting on every page. The visible health banner was retired: the
 * topbar warning badge (warning_badge.js) is now the single warnings UI.
 * This file now provides ONLY the "Rebuild derived tables" modal, which the
 * badge's "Fix..." button opens via window.hbRebuildModal.open().
 *
 * Add via:  <script src="/static/rebuild_modal.js"></script>
 */
(function () {
  'use strict';

  // ---- styles (injected once) ----------------------------------------------
  function injectStyles() {
    if (document.getElementById('hbStyles')) return;
    const css = `
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
    if (!document.getElementById('hbModalBackdrop')) mountModal();
    document.getElementById('hbResult').classList.remove('show');
    document.getElementById('hbResult').textContent = '';
    document.getElementById('hbRebuildBtn').disabled = false;
    document.getElementById('hbRebuildBtn').textContent = 'Rebuild now';
    document.getElementById('hbCopyBtn').style.display = 'none';
    document.getElementById('hbModalBackdrop').classList.add('open');
  }

  function closeFixModal() {
    document.getElementById('hbModalBackdrop').classList.remove('open');
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

  async function runRebuild() {
    const days = Number(document.getElementById('hbDays').value);
    const btn = document.getElementById('hbRebuildBtn');
    const result = document.getElementById('hbResult');
    btn.disabled = true;
    btn.textContent = 'Rebuilding...';
    result.classList.add('show');
    result.textContent = 'POST /api/admin/rebuild { days: ' + days + ' } ...\n';
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
    } catch (e) {
      result.textContent += 'ERROR: ' + e.message;
      document.getElementById('hbCopyBtn').style.display = 'inline-block';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Run again';
    }
  }

  // ---- public API ----------------------------------------------------------
  // The topbar warning badge's "Fix..." button calls this.
  window.hbRebuildModal = { open: openFixModal };

  // ---- entry ---------------------------------------------------------------
  function init() {
    injectStyles();
    mountModal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
