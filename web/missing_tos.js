/* 2026-10-20, user-directed: "Missing from TOS" -- one click lists every symbol that is on a Hedgeye list with a BULLISH read (SSS / PS on the
 * list; CALL / ETF / RR outlook Bullish; II Long) but is not in the newest TOS export, so it can be added to a TOS watchlist.
 * Data: GET /api/dashboard/missing-from-tos?date=D  ->  {as_of, count, symbols:[{symbol, lists:[...], us_ticker}]}.
 * Button #missingTosBtn lives in the "Hedgeye signals" panel header (index.html). Dashboard only. */
(function () {
  'use strict';
  var data = null;
  var SOURCES = ['SSS', 'PS', 'CALL', 'ETF', 'II', 'RR'];
  var picked = {};     // source -> true: only symbols on at least one picked list are shown (all picked by default)
  SOURCES.forEach(function (x) { picked[x] = true; });
  var usOnly = true;   // hide foreign / crypto / FRED symbols (ADS.DE, ETHUSD, DGS2:FRED ...) that cannot be added to a TOS watchlist

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function dateParam() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? '?date=' + encodeURIComponent(dp.value) : '';
  }
  function pool() {
    return ((data && data.symbols) || []).filter(function (x) { return !usOnly || x.us_ticker; });
  }
  function visible() {
    return pool().filter(function (x) { return x.lists.some(function (l) { return picked[l]; }); });
  }
  function badge() {
    var b = document.getElementById('missingTosCount');
    if (b) b.textContent = data ? '(' + visible().length + ')' : '';
  }
  async function load() {
    try {
      var r = await fetch('/api/dashboard/missing-from-tos' + dateParam());
      if (!r.ok) throw new Error('HTTP ' + r.status);
      data = await r.json();
    } catch (e) { data = null; }
    badge();
  }

  function closeModal() { var m = document.getElementById('missingTosModal'); if (m) m.remove(); }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

  function copyText(text, btn) {
    function done() { if (btn) { var t = btn.textContent; btn.textContent = 'Copied ✓'; setTimeout(function () { btn.textContent = t; }, 1500); } }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
    } else { fallbackCopy(text); done(); }
  }
  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) { /* nothing more to do */ }
    ta.remove();
  }
  function downloadCsv() {
    var rows = visible();
    var csv = 'tos_symbol,lists\n' + rows.map(function (x) { return x.symbol + ',' + x.lists.join('|'); }).join('\n') + '\n';
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = 'missing_from_tos_' + ((data && data.as_of) || 'today') + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function render() {
    var m = document.getElementById('missingTosModal');
    if (!m) return;
    var rows = visible();
    var base = pool();
    var chips = SOURCES.map(function (src) {
      var n = base.filter(function (x) { return x.lists.indexOf(src) >= 0; }).length;
      return '<label style="font-size:12px;margin-right:10px;white-space:nowrap;"><input type="checkbox" class="mtSrc" data-src="' + src + '"' + (picked[src] ? ' checked' : '') + '> ' + src + ' <span style="color:#6b7280;">(' + n + ')</span></label>';
    }).join('');
    m.querySelector('.mt-src').innerHTML = '<span style="font-size:12px;font-weight:600;margin-right:8px;">Source</span>' + chips;
    m.querySelectorAll('.mtSrc').forEach(function (cb) {
      cb.addEventListener('change', function () { picked[cb.getAttribute('data-src')] = cb.checked; render(); });
    });
    var body = rows.length
      ? '<table class="pm-pop-table"><thead><tr><th>Symbol</th><th>On these Hedgeye lists</th></tr></thead><tbody>' +
        rows.map(function (x) {
          return '<tr><td><b>' + esc(x.symbol) + '</b></td><td>' + esc(x.lists.join(', ')) + '</td></tr>';
        }).join('') + '</tbody></table>'
      : '<div class="empty-note">Nothing missing for the picked sources.</div>';
    m.querySelector('.mt-body').innerHTML = body;
    m.querySelector('.mt-sub').innerHTML = rows.length + ' symbol' + (rows.length === 1 ? '' : 's') + ' &middot; Bullish on a Hedgeye list, not in TOS &middot; as of ' + esc((data && data.as_of) || '');
    badge();
  }

  async function open() {
    await load();
    closeModal();
    var m = document.createElement('div');
    m.id = 'missingTosModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:640px;"><div class="modal-header"><div><h2 style="margin:0;">Missing from TOS</h2>' +
      '<p class="mt-sub" style="margin:0;"></p></div><button class="close-btn" type="button" aria-label="Close">&times;</button></div>' +
      '<div class="modal-body"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">' +
      '<button type="button" id="mtCopy" class="rd-detail-link" style="cursor:pointer;">Copy symbols</button>' +
      '<button type="button" id="mtCsv" class="rd-detail-link" style="cursor:pointer;">Download CSV</button>' +
      '<label style="font-size:12px;margin-left:auto;"><input type="checkbox" id="mtUs"' + (usOnly ? ' checked' : '') + '> US tickers only</label></div>' +
      '<div class="mt-src" style="margin-bottom:8px;"></div><div class="mt-body" style="max-height:55vh;overflow-y:auto;"></div></div></div>';
    document.body.appendChild(m);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
    m.querySelector('#mtCopy').addEventListener('click', function () {
      copyText(visible().map(function (x) { return x.symbol; }).join(', '), this);   // comma separated: pastes straight into a TOS watchlist
    });
    m.querySelector('#mtCsv').addEventListener('click', downloadCsv);
    m.querySelector('#mtUs').addEventListener('change', function () { usOnly = this.checked; render(); });
    render();
  }

  function init() {
    var btn = document.getElementById('missingTosBtn');
    if (!btn) return;
    btn.addEventListener('click', open);
    setTimeout(load, 1500);
    setInterval(load, 300000);
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 800); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
