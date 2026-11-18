/* Builder notes popover (2026-11-18): the 🔭 long-term note and the 🔔 watch on one stock, from the Builder's first column.
 * Same stored rows as the Actionable screen (/api/actionable/conviction-holds, /api/actionable/watch): one note per stock on both screens.
 * Self-contained (Actionable's own popovers live in actionable.js and depend on its grid). A stock with neither entry can keep a plain
 * note on My stocks (PUT /api/builder/my-stocks/{sym}).  window.BldNotes.open(sym, anchorEl, flags, onChange) */
(function () {
  'use strict';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let pop = null, curSym = null;

  const css = document.createElement('style');
  css.textContent = `
    #bldNotePop { position: fixed; z-index: 9000; width: 300px; max-height: 80vh; overflow: auto; background: var(--card-bg, #fff); color: var(--text-1, #111);
      border: 1px solid var(--border, #d1d5db); border-radius: 8px; box-shadow: 0 6px 24px rgba(0,0,0,.18); padding: 10px 12px; font-size: 12px; display: none; }
    #bldNotePop .np-title { font-weight: 700; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
    #bldNotePop .np-x { border: 0; background: none; cursor: pointer; font-size: 16px; line-height: 1; color: var(--text-3, #6b7280); }
    #bldNotePop details { border-top: 1px solid var(--border, #e5e7eb); padding: 6px 0; }
    #bldNotePop summary { cursor: pointer; font-weight: 600; }
    #bldNotePop textarea, #bldNotePop input[type=text], #bldNotePop input[type=number], #bldNotePop input[type=date], #bldNotePop select {
      width: 100%; box-sizing: border-box; font: inherit; padding: 4px 6px; border: 1px solid var(--border, #d1d5db); border-radius: 5px; margin: 4px 0; background: var(--card-bg, #fff); color: inherit; }
    #bldNotePop textarea { min-height: 54px; resize: vertical; }
    #bldNotePop .np-row { display: flex; gap: 6px; align-items: center; }
    #bldNotePop .np-row input, #bldNotePop .np-row select { width: auto; flex: 1 1 0; }
    #bldNotePop .np-chk { display: flex; gap: 6px; align-items: center; margin: 2px 0; }
    #bldNotePop .np-actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 4px; }
    #bldNotePop .np-actions button { font: inherit; padding: 3px 10px; border: 1px solid var(--border, #d1d5db); border-radius: 5px; background: var(--card-bg, #fff); color: inherit; cursor: pointer; }
    #bldNotePop .np-actions button.danger { color: #dc2626; border-color: #dc2626; }
    #bldNotePop .np-msg { min-height: 14px; margin-top: 4px; color: #dc2626; }
    #bldNotePop .np-sub { color: var(--text-3, #6b7280); margin: 2px 0; }`;
  document.head.appendChild(css);

  async function call(url, method, body) {
    const r = await fetch(url, { method: method || 'GET', headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
    let j = null;
    try { j = await r.json(); } catch (e) { /* not json */ }
    if (!r.ok) throw new Error((j && j.detail) || ('HTTP ' + r.status));
    return j;
  }

  function close() { curSym = null; if (pop) pop.style.display = 'none'; }

  function watchSummary(w) {
    const bits = [];
    if (w.pct != null) bits.push((w.dir === 'DOWN' ? 'down ' : 'up ') + w.pct + '% move');
    if (w.lrr) bits.push('LRR'); if (w.trr) bits.push('TRR'); if (w.trade) bits.push('Trade line'); if (w.trend) bits.push('Trend line');
    if (w.price != null) bits.push('$' + w.price);
    return bits.length ? bits.join(', ') : 'plain end-of-close reminder';
  }

  function html(sym, f) {
    const lt = f.lt, w = f.w;
    const ltOpen = lt ? ' open' : '', wOpen = w && !lt ? ' open' : '', mOpen = !lt && !w ? ' open' : '';
    let h = `<div class="np-title"><span>${esc(sym)} &mdash; notes</span><button class="np-x" data-np="x" title="Close">&times;</button></div>`;
    // ---- long-term
    h += `<details${ltOpen}><summary>${lt && lt.dir === 'AVOID' ? '🚫 Avoid' : '🔭 Long-term'}${lt ? '' : ' <span class="np-sub">(none)</span>'}</summary>`;
    if (lt) {
      h += `<textarea id="npLtNote">${esc(lt.note)}</textarea>${lt.target ? `<div class="np-sub">Target date ${esc(lt.target)}</div>` : ''}
        <select id="npLtClose"><option value="CLOSED_WIN">Close as: Won, thesis played out</option><option value="CLOSED_LOSS">Close as: Lost, thesis broke</option><option value="EXPIRED">Close as: Expired / no longer tracking</option></select>
        <div class="np-actions"><button class="danger" data-np="lt-del" title="Delete this entry for good (Close keeps it as history)">Delete</button><button data-np="lt-close">Close it</button><button data-np="lt-save">Save note</button></div>`;
    } else {
      h += `<select id="npLtDir" title="Hold: don't sell on short-term noise. Avoid: don't chase a buy."><option value="HOLD">🔭 Hold: don't sell</option><option value="AVOID">🚫 Avoid: don't buy</option></select>
        <textarea id="npLtNote" placeholder="Why you hold it for the long term..."></textarea>
        <label class="np-sub">Target date <input type="date" id="npLtDate"></label>
        <div class="np-actions"><button data-np="lt-add">Add long-term note</button></div>`;
    }
    h += '</details>';
    // ---- watch
    h += `<details${wOpen}><summary>🔔 Watch${w ? '' : ' <span class="np-sub">(none)</span>'}</summary>`;
    if (w) {
      h += `<div class="np-sub">${esc(watchSummary(w))}${w.triggered ? ' &middot; triggered' : ''}</div>
        <textarea id="npWNote" placeholder="note (optional)...">${esc(w.note || '')}</textarea>
        <div class="np-actions"><button class="danger" data-np="w-stop">Stop watching</button><button data-np="w-save">Save note</button></div>`;
    } else {
      h += `<div class="np-row"><select id="npWDir"><option value="UP">&uarr; Up</option><option value="DOWN">&darr; Down</option></select><input type="number" id="npWPct" step="0.5" min="0" placeholder="% move"></div>
        <label class="np-chk"><input type="checkbox" id="npWLrr"> LRR</label><label class="np-chk"><input type="checkbox" id="npWTrr"> TRR</label>
        <label class="np-chk"><input type="checkbox" id="npWTrade"> Trade line</label><label class="np-chk"><input type="checkbox" id="npWTrend"> Trend line</label>
        <input type="number" id="npWPrice" step="0.01" min="0" placeholder="target price $">
        <textarea id="npWNote" placeholder="note (optional)..."></textarea>
        <div class="np-sub">Leave every trigger blank for a plain end-of-close reminder.</div>
        <div class="np-actions"><button data-np="w-add">Watch</button></div>`;
    }
    h += '</details>';
    // ---- My stocks note (only for a stock with no long-term or watch entry)
    if (!lt && !w) {
      h += `<details${mOpen}><summary>📝 My stocks note${f.mine ? '' : ' <span class="np-sub">(none)</span>'}</summary>
        <textarea id="npMine" placeholder="A plain note (the stock joins your My stocks list)...">${esc(f.mine || '')}</textarea>
        <div class="np-actions"><button data-np="m-save">Save note</button></div></details>`;
    }
    return h + '<div class="np-msg" id="npMsg"></div>';
  }

  function place(anchor) {
    const r = anchor.getBoundingClientRect();
    let top = r.bottom + 4;
    if (top + pop.offsetHeight > window.innerHeight - 8) top = Math.max(8, r.top - pop.offsetHeight - 4);
    let left = r.left;
    if (left + pop.offsetWidth > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pop.offsetWidth - 8);
    pop.style.top = top + 'px'; pop.style.left = left + 'px';
  }

  function open(sym, anchor, flags, onChange) {
    if (!pop) {
      pop = document.createElement('div'); pop.id = 'bldNotePop'; document.body.appendChild(pop);
      document.addEventListener('click', e => { if (curSym && !pop.contains(e.target) && !e.target.closest('[data-ic]')) close(); });
      document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
    }
    if (curSym === sym && pop.style.display === 'block') { close(); return; }
    curSym = sym;
    const f = flags || {};
    pop.innerHTML = html(sym, f);
    pop.style.display = 'block';
    place(anchor);
    const $ = id => pop.querySelector('#' + id);
    const msg = t => { $('npMsg').textContent = t || ''; };
    const done = async () => { close(); if (onChange) await onChange(); };
    const act = {
      'x': async () => close(),
      'lt-add': async () => {
        const note = $('npLtNote').value.trim();
        if (!note) return msg('Type the note first.');
        await call('/api/actionable/conviction-holds', 'POST', { tos_symbol: sym, thesis_note: note, target_date: $('npLtDate').value || null, direction: $('npLtDir').value });
      },
      'lt-save': async () => {
        const note = $('npLtNote').value.trim();
        if (!note) return msg('The note cannot be empty.');
        await call('/api/actionable/conviction-holds/' + f.lt.id, 'PATCH', { thesis_note: note });
      },
      'lt-close': async () => { await call('/api/actionable/conviction-holds/' + f.lt.id, 'PATCH', { status: $('npLtClose').value }); },
      'lt-del': async () => { if (!window.confirm('Delete this long-term note for ' + sym + '? This cannot be undone (Close it keeps it as history).')) throw new Error(''); await call('/api/actionable/conviction-holds/' + f.lt.id, 'DELETE'); },
      'w-add': async () => {
        const pct = $('npWPct').value, price = $('npWPrice').value;
        await call('/api/actionable/watch', 'POST', { tos_symbol: sym, note: $('npWNote').value || null, trigger_pct: pct ? Number(pct) : null, trigger_pct_dir: pct ? $('npWDir').value : null,
          trigger_lrr: $('npWLrr').checked, trigger_trr: $('npWTrr').checked, trigger_trade: $('npWTrade').checked, trigger_trend: $('npWTrend').checked, trigger_price: price ? Number(price) : null });
      },
      'w-save': async () => { await call('/api/actionable/watch/' + f.w.id, 'PATCH', { note: $('npWNote').value }); },
      'w-stop': async () => { if (!window.confirm('Stop watching ' + sym + '? This cannot be undone.')) throw new Error(''); await call('/api/actionable/watch/' + f.w.id, 'DELETE'); },
      'm-save': async () => { await call('/api/builder/my-stocks/' + encodeURIComponent(sym), 'PUT', { note: $('npMine').value.trim() || null }); },
    };
    pop.querySelectorAll('[data-np]').forEach(b => b.onclick = async () => {
      const k = b.dataset.np;
      if (k === 'x') return close();
      msg('');
      try { await act[k](); await done(); } catch (e) { if (e.message) msg(e.message); }
    });
  }

  window.BldNotes = { open, close };
})();
