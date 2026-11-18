/* Builder notes popovers (2026-11-18): the 🔭 long-term note and the 🔔 watch on one stock, from the Builder's first column.
 * Same look and same fields as the Actionable screen's popovers (styles copied from actionable.html), same stored rows
 * (/api/actionable/conviction-holds, /api/actionable/watch): one note per stock on both screens.
 * 🔭 opens the long-term popover, 🔔 opens the watch popover. A stock with no long-term entry can also keep a plain note on
 * My stocks (PUT /api/builder/my-stocks/{sym}).   window.BldNotes.open(sym, anchorEl, flags, onChange, kind)  kind = 'lt' | 'w' */
(function () {
  'use strict';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pops = {};          // kind -> element
  let cur = null;           // { kind, sym }

  const css = document.createElement('style');
  css.textContent = `
    .bn-pop { pointer-events: auto !important; z-index: 9000 !important; }
    .conviction-pop .cp-title { font-weight: 700; color: #6d28d9; margin-bottom: 6px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
    .conviction-pop textarea, .conviction-pop input[type="text"] { width: 100%; box-sizing: border-box; font: inherit; padding: 5px; border: 1px solid #e2e8f0; border-radius: 5px; margin-bottom: 6px; resize: vertical; }
    .conviction-pop textarea { min-height: 48px; }
    .conviction-pop input[type="date"] { font: inherit; padding: 3px 5px; border: 1px solid #e2e8f0; border-radius: 5px; }
    .conviction-pop select { width: 100%; font: inherit; padding: 4px; border: 1px solid #e2e8f0; border-radius: 5px; margin-bottom: 6px; }
    .conviction-pop .cp-actions { display: flex; justify-content: flex-end; gap: 6px; }
    .conviction-pop .cp-status { font-size: 10px; color: #64748b; margin-top: 5px; min-height: 12px; }
    .watch-pop .wp-title { font-weight: 700; color: #0369a1; margin-bottom: 6px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
    .watch-pop textarea, .watch-pop input[type="text"], .watch-pop input[type="number"] { width: 100%; box-sizing: border-box; font: inherit; padding: 5px; border: 1px solid #e2e8f0; border-radius: 5px; margin-bottom: 6px; resize: vertical; }
    .watch-pop textarea { min-height: 36px; }
    .watch-pop select { font: inherit; padding: 3px 4px; border: 1px solid #e2e8f0; border-radius: 5px; }
    .watch-pop label.wp-trig { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #334155; margin-bottom: 4px; }
    .watch-pop label.wp-trig input[type="checkbox"] { margin: 0; }
    .watch-pop .wp-pctrow { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; font-size: 11px; color: #334155; }
    .watch-pop .wp-pctrow input { width: 56px; flex: 0 0 auto; margin-bottom: 0; }
    .watch-pop .wp-actions { display: flex; justify-content: flex-end; gap: 6px; }
    .watch-pop .wp-status { font-size: 10px; color: #64748b; margin-top: 5px; min-height: 12px; }
    .bn-pop .btn { font: inherit; padding: 3px 10px; border: 1px solid #e2e8f0; border-radius: 5px; background: #fff; color: #1e293b; cursor: pointer; height: auto; line-height: 1.4; }
    .bn-pop .btn.danger { color: #dc2626; border-color: #dc2626; }
    .bn-pop .bn-sub { color: #64748b; margin: 0 0 6px; }
    .bn-pop .bn-sep { border-top: 1px solid #e2e8f0; margin: 8px 0 6px; padding-top: 6px; color: #64748b; }
    .bn-pop .bn-err { color: #dc2626; }`;
  document.head.appendChild(css);

  async function call(url, method, body) {
    const r = await fetch(url, { method: method || 'GET', headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
    let j = null;
    try { j = await r.json(); } catch (e) { /* not json */ }
    if (!r.ok) throw new Error((j && j.detail) || ('HTTP ' + r.status));
    return j;
  }

  function closeAll() { cur = null; Object.values(pops).forEach(p => { p.style.display = 'none'; }); }

  function watchSummary(w) {
    const bits = [];
    if (w.pct != null) bits.push((w.dir === 'DOWN' ? '↓' : '↑') + w.pct + '%');
    if (w.lrr) bits.push('LRR'); if (w.trr) bits.push('TRR'); if (w.trade) bits.push('Trade line'); if (w.trend) bits.push('Trend line');
    if (w.price != null) bits.push('$' + Number(w.price).toFixed(2));
    if (w.call) bits.push('Final Call turns ' + (w.call === 'SELL' ? 'Sell' : 'Buy') + (bits.length ? ' (with the rest)' : ''));
    return bits.length ? bits.join(' · ') : 'plain reminder (no condition)';
  }

  function ltHtml(sym, f) {
    const lt = f.lt;
    if (lt) {
      const avoid = lt.dir === 'AVOID';
      return `<div class="cp-title">${avoid ? '🚫' : '🔭'} ${esc(sym)} &mdash; ${avoid ? 'Avoid (don\'t buy)' : 'Hold (don\'t sell)'}</div>
        <div class="bn-sub">${lt.target ? 'Target ' + esc(lt.target) : 'Long-term note'}</div>
        <textarea id="bnNote">${esc(lt.note)}</textarea>
        <div class="cp-actions"><button class="btn" data-bn="lt-save">Save note</button></div>
        <div class="bn-sep">
          <select id="bnClose"><option value="CLOSED_WIN">Close as: Won &mdash; thesis played out</option><option value="CLOSED_LOSS">Close as: Lost &mdash; thesis broke</option><option value="EXPIRED">Close as: Expired / no longer tracking</option></select>
          <div class="cp-actions"><button class="btn danger" data-bn="lt-del" title="Hard-delete this entry (not reversible) — use Close instead to keep it as history">Delete</button><button class="btn" data-bn="lt-close">Close</button></div>
        </div>
        <div class="cp-status" id="bnMsg"></div>`;
    }
    return `<div class="cp-title">&#128301; ${esc(sym)} &mdash; Add Long-Term Note</div>
      <select id="bnDir" title="Hold: don't sell on short-term noise. Avoid: don't chase a BUY signal."><option value="HOLD">🔭 Hold — don't sell</option><option value="AVOID">🚫 Avoid — don't buy</option></select>
      <textarea id="bnNote" placeholder="e.g. HE Call: strong Q3 setup, accumulate on weakness…"></textarea>
      <label style="display:flex;align-items:center;gap:6px;color:#64748b;margin-bottom:6px;">Target date <input type="date" id="bnDate"></label>
      <div class="cp-actions"><button class="btn" data-bn="lt-add">Add note</button></div>
      <div class="bn-sep">or just a plain note (kept on My stocks)
        <textarea id="bnMine" placeholder="plain note…" style="margin-top:4px">${esc(f.mine || '')}</textarea>
        <div class="cp-actions"><button class="btn" data-bn="m-save">Save note</button></div></div>
      <div class="cp-status" id="bnMsg"></div>`;
  }

  function wHtml(sym, f) {
    const w = f.w;
    if (w) {
      if (w.triggered) {
        return `<div class="wp-title">🔔 ${esc(sym)} — Triggered</div>
          <div style="margin-bottom:7px;">${esc(w.note || '')}</div>
          <div class="bn-sub">${esc(watchSummary(w))}</div>
          <textarea id="bnNote" placeholder="note (optional)…">${esc(w.note || '')}</textarea>
          <div class="wp-actions"><button class="btn danger" data-bn="w-stop" title="Hard-delete (not reversible)">Stop</button><button class="btn" data-bn="w-save">Save note</button></div>
          <div class="wp-status" id="bnMsg"></div>`;
      }
      return `<div class="wp-title">🔔 ${esc(sym)} — Watching</div>
        <div class="bn-sub">${esc(watchSummary(w))}</div>
        <textarea id="bnNote" placeholder="note (optional)…">${esc(w.note || '')}</textarea>
        <div class="wp-actions"><button class="btn danger" data-bn="w-stop" title="Stop watching (not reversible)">Stop watching</button><button class="btn" data-bn="w-save">Save note</button></div>
        <div class="wp-status" id="bnMsg"></div>`;
    }
    return `<div class="wp-title">🔔 ${esc(sym)} — Watch</div>
      <div class="wp-pctrow"><select id="bnPctDir"><option value="UP">↑ Up</option><option value="DOWN">↓ Down</option></select><input type="number" id="bnPct" step="0.5" min="0" placeholder="4"> % move</div>
      <label class="wp-trig"><input type="checkbox" id="bnLrr"> LRR</label>
      <label class="wp-trig"><input type="checkbox" id="bnTrr"> TRR</label>
      <label class="wp-trig"><input type="checkbox" id="bnTrade"> Trade line</label>
      <label class="wp-trig"><input type="checkbox" id="bnTrend"> Trend line</label>
      <div class="wp-pctrow">$ <input type="number" id="bnPrice" step="0.01" min="0" placeholder="target price"></div>
      <div class="wp-pctrow" title="Alert when the Actionable Final Call turns Buy or Sell (any buy-side / sell-side call). With other triggers above, both must hold.">Final Call turns <select id="bnCall"><option value="">(off)</option><option value="BUY">Buy</option><option value="SELL">Sell</option></select></div>
      <textarea id="bnNote" placeholder="note (optional)…"></textarea>
      <div class="wp-actions"><button class="btn" data-bn="w-add">Watch</button></div>
      <div class="wp-status" id="bnMsg">Leave every field blank for a plain end-of-close reminder.</div>`;
  }

  function place(pop, anchor) {
    const r = anchor.getBoundingClientRect();
    let top = r.bottom + 4;
    if (top + pop.offsetHeight > window.innerHeight - 8) top = Math.max(8, r.top - pop.offsetHeight - 4);
    let left = r.left;
    if (left + pop.offsetWidth > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
    pop.style.top = top + 'px'; pop.style.left = left + 'px';
  }

  function popFor(kind) {
    if (pops[kind]) return pops[kind];
    const el = document.createElement('div');
    el.id = kind === 'w' ? 'bldWatchPop' : 'bldLtPop';
    el.className = 'source-pop bn-pop ' + (kind === 'w' ? 'watch-pop' : 'conviction-pop');
    el.style.width = kind === 'w' ? '250px' : '260px';
    document.body.appendChild(el);
    pops[kind] = el;
    return el;
  }

  function open(sym, anchor, flags, onChange, kind) {
    kind = kind === 'w' ? 'w' : 'lt';
    if (!document.body.dataset.bnWired) {
      document.body.dataset.bnWired = '1';
      document.addEventListener('click', e => { if (cur && !e.target.closest('.bn-pop') && !e.target.closest('[data-ic]')) closeAll(); });
      document.addEventListener('keydown', e => { if (e.key === 'Escape') closeAll(); });
    }
    const wasSame = cur && cur.kind === kind && cur.sym === sym;
    closeAll();
    if (wasSame) return;                 // clicking the same icon again toggles it off
    cur = { kind, sym };
    const f = flags || {};
    const pop = popFor(kind);
    pop.innerHTML = kind === 'w' ? wHtml(sym, f) : ltHtml(sym, f);
    pop.style.display = 'block';
    place(pop, anchor);
    const $ = id => pop.querySelector('#' + id);
    const msg = t => { const m = $("bnMsg"); if (m) { m.textContent = t || ""; m.style.color = t ? "#dc2626" : ""; } };
    const done = async () => { closeAll(); if (onChange) await onChange(); };
    const act = {
      'lt-add': async () => {
        const note = $('bnNote').value.trim();
        if (!note) return msg('Thesis note is required.');
        await call('/api/actionable/conviction-holds', 'POST', { tos_symbol: sym, thesis_note: note, target_date: $('bnDate').value || null, direction: $('bnDir').value });
      },
      'lt-save': async () => {
        const note = $('bnNote').value.trim();
        if (!note) return msg('The note cannot be empty.');
        await call('/api/actionable/conviction-holds/' + f.lt.id, 'PATCH', { thesis_note: note });
      },
      'lt-close': async () => { await call('/api/actionable/conviction-holds/' + f.lt.id, 'PATCH', { status: $('bnClose').value }); },
      'lt-del': async () => { if (!window.confirm('Delete this conviction hold? This cannot be undone (use Close instead to keep it as history).')) throw new Error(''); await call('/api/actionable/conviction-holds/' + f.lt.id, 'DELETE'); },
      'm-save': async () => { await call('/api/builder/my-stocks/' + encodeURIComponent(sym), 'PUT', { note: $('bnMine').value.trim() || null }); },
      'w-add': async () => {
        const pct = $('bnPct').value, price = $('bnPrice').value;
        await call('/api/actionable/watch', 'POST', { tos_symbol: sym, note: $('bnNote').value || null, trigger_pct: pct ? Number(pct) : null, trigger_pct_dir: pct ? $('bnPctDir').value : null,
          trigger_lrr: $('bnLrr').checked, trigger_trr: $('bnTrr').checked, trigger_trade: $('bnTrade').checked, trigger_trend: $('bnTrend').checked,
          trigger_price: price ? Number(price) : null, trigger_call: $('bnCall').value || null });
      },
      'w-save': async () => { await call('/api/actionable/watch/' + f.w.id, 'PATCH', { note: $('bnNote').value }); },
      'w-stop': async () => { if (!window.confirm('Stop watching ' + sym + '? This cannot be undone.')) throw new Error(''); await call('/api/actionable/watch/' + f.w.id, 'DELETE'); },
    };
    pop.querySelectorAll('[data-bn]').forEach(b => b.onclick = async () => {
      msg('');
      try { await act[b.dataset.bn](); await done(); } catch (e) { if (e.message) msg(e.message); }
    });
  }

  window.BldNotes = { open, close: closeAll };
})();
