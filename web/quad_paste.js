// Paste-import of monthly quad values on the /ref screen (table ref_quad_periods),
// with import history, per-import change view, and undo.
(function () {
  const TABLE = 'ref_quad_periods';
  const API = '/api/ref/quad-months';
  const btn = document.createElement('button');
  btn.id = 'quadPasteBtn';
  btn.textContent = 'Paste quad months';
  btn.style.display = 'none';
  const host = document.getElementById('reloadBtn');
  host.parentNode.insertBefore(btn, host);

  const dlg = document.createElement('dialog');
  dlg.style.cssText = 'width:min(820px,95vw);border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--card-bg);color:var(--text-1)';
  dlg.innerHTML =
    '<h3 style="margin:0 0 6px">Monthly quad values</h3>' +
    '<div style="color:var(--text-2);font-size:13px;margin-bottom:8px">Paste columns Month, Qud, Q1, Q2, Q3, Q4 (e.g. <code>26-Oct 2 52% 0% 0% 48%</code>). Existing months are overwritten; other months stay.</div>' +
    '<textarea id="qpText" rows="9" style="width:100%;font-family:monospace;box-sizing:border-box"></textarea>' +
    '<div id="qpOut" style="margin:8px 0;font-size:13px;max-height:260px;overflow:auto"></div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
    '<button id="qpPreview">Preview</button><button id="qpApply" disabled>Apply</button><button id="qpClose">Close</button></div>' +
    '<hr style="margin:12px 0"><div style="font-weight:bold;margin-bottom:4px">Import history</div>' +
    '<div id="qpHist" style="font-size:13px"></div>' +
    '<div id="qpRe" style="margin-top:8px;font-size:13px"></div>' +
    '<div id="qpDetail" style="margin-top:8px;font-size:13px;max-height:260px;overflow:auto"></div>';
  document.body.appendChild(dlg);
  const $ = id => dlg.querySelector('#' + id);
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;');

  async function post(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    return r.json();
  }
  const get = url => fetch(url).then(r => r.json());

  function table(rows, withStatus) {
    return '<table style="border-collapse:collapse;width:100%"><tr><th align="left">Month</th><th>Quad</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th>' +
      (withStatus ? '<th>Status</th>' : '') + '</tr>' +
      rows.map(r => '<tr style="' + (r.status === 'same' ? 'color:var(--text-3)' : '') + '"><td>' + esc(r.label) + '</td><td align="center">' +
        esc(r.quad.replace('Quad ', '')) +
        (r.old_quad && r.old_quad !== r.quad ? ' <small>(was ' + esc(r.old_quad.replace('Quad ', '')) + ')</small>' : '') + '</td>' +
        r.pcts.map((p, i) => {
          const ch = r.old && r.old[i] !== p;
          return '<td align="center"' + (ch ? ' style="font-weight:bold;background:rgba(245,158,11,.18)"' : '') + '>' + p + '%' +
            (ch ? ' <small>(was ' + r.old[i] + ')</small>' : '') + '</td>';
        }).join('') +
        '<td align="center">' + r.status + '</td></tr>').join('') + '</table>';
  }


  let poll = null;
  async function rederive() {
    const re = $('qpRe');
    const st = await post(API + '/rederive');
    re.innerHTML = '<i>Recalculating dashboard for the current date (MACRO, Risk Dial, Action)...</i>';
    clearInterval(poll);
    poll = setInterval(async () => {
      const s = await get(API + '/rederive');
      if (s.state === 'running') return;
      clearInterval(poll);
      re.innerHTML = s.state === 'done'
        ? '<b style="color:#16a34a">Dashboard recalculated for ' + esc(s.date) + '. Reload other screens to see it.</b>'
        : '<b style="color:#dc2626">Recalculation failed: ' + esc(s.error || '') + '</b> <button id="qpRetry">Retry</button>';
      const rb = re.querySelector('#qpRetry'); if (rb) rb.onclick = rederive;
    }, 3000);
  }

  function show(res) {
    const out = $('qpOut');
    if (!res.ok) {
      out.innerHTML = '<div style="color:#dc2626">' + res.errors.map(e => '<div>' + esc(e) + '</div>').join('') + '</div>';
      $('qpApply').disabled = true; return;
    }
    const n = { new: 0, changed: 0, same: 0 };
    res.rows.forEach(r => n[r.status]++);
    out.innerHTML = '<div style="margin-bottom:4px"><b>' + (res.applied ? 'Saved: ' : 'Will save: ') +
      n.changed + ' changed, ' + n.new + ' new, ' + n.same + ' unchanged</b></div>' + table(res.rows, true);
    $('qpApply').disabled = !!res.applied || (n.changed + n.new) === 0;
  }

  async function loadHistory() {
    const h = await get(API + '/history');
    $('qpHist').innerHTML = h.length ? '<table style="border-collapse:collapse;width:100%">' +
      h.map(r => '<tr><td>#' + r.id + '</td><td>' + new Date(r.imported_at).toLocaleString() + '</td><td>' +
        r.n_changed + ' changed, ' + r.n_new + ' new</td><td>' +
        (r.undone_at ? '<i>undone</i>' : '<button data-undo="' + r.id + '">Undo</button>') +
        '</td><td><button data-view="' + r.id + '">View changes</button></td></tr>').join('') + '</table>'
      : '<span style="color:var(--text-3)">No imports yet.</span>';
  }

  $('qpHist').addEventListener('click', async e => {
    const v = e.target.dataset.view, u = e.target.dataset.undo;
    if (v) {
      const d = await get(API + '/history/' + v);
      $('qpDetail').innerHTML = '<b>Import #' + d.id + '</b> (showing what it changed; bold = value it changed, was = before)' + table(d.rows, true);
    } else if (u) {
      if (!confirm('Undo import #' + u + '? The months it changed go back to their earlier values.')) return;
      const r = await post(API + '/history/' + u + '/undo');
      $('qpDetail').innerHTML = '<b style="color:' + (r.ok ? '#16a34a' : '#dc2626') + '">' + esc(r.message) + '</b>';
      await loadHistory();
      if (r.ok) rederive();
      if (r.ok && typeof loadTable === 'function' && state.currentTable === TABLE) loadTable(TABLE);
    }
  });

  btn.onclick = () => { dlg.showModal(); loadHistory(); };
  $('qpClose').onclick = () => dlg.close();
  $('qpPreview').onclick = async () => show(await post(API + '/import', { text: $('qpText').value, apply: false }));
  $('qpText').oninput = () => { $('qpApply').disabled = true; };
  $('qpApply').onclick = async () => {
    const res = await post(API + '/import', { text: $('qpText').value, apply: true });
    show(res); await loadHistory();
    if (res.ok && res.log_id) rederive();
    if (res.ok && typeof loadTable === 'function' && state.currentTable === TABLE) loadTable(TABLE);
  };
  window.quadPasteSync = name => { btn.style.display = name === TABLE ? '' : 'none'; };
})();
