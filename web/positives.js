/* positives.js -- Positives panel under the Risk Dial (#positivesBody). Reads GET /api/cockpit/positives.
 * Display only: never changes the Risk Dial score or any action. */
(function () {
  'use strict';
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  window.loadPositives = async function (date) {
    var body = document.getElementById('positivesBody');
    if (!body) return;
    try {
      var r = await fetch('/api/cockpit/positives' + (date ? '?date=' + encodeURIComponent(date) : ''));
      var j = await r.json();
      var items = j.items || [];
      if (!items.length) { body.innerHTML = '<div class="ev-quiet">' + esc(j.note || 'No data.') + '</div>'; return; }
      body.innerHTML = '<div class="pos-head">Positives</div>' + items.map(function (it) {
        var tip = [it.history, it.ratio != null ? '1-month VIX / 3-month VIX = ' + it.ratio : ''].filter(Boolean).join('\n');
        return '<div class="pos-row ' + (it.on ? 'on' : 'off') + '" title="' + esc(tip) + '">' +
          '<span class="pos-mark">' + (it.on ? '✔' : '○') + '</span>' +
          '<span class="pos-text"><strong>' + esc(it.title) + '</strong> — ' + esc(it.text) + '</span></div>' +
          (it.history ? '<div class="pos-hist">' + esc(it.history) + '</div>' : '');
      }).join('');
    } catch (e) {
      console.error('positives failed:', e);
      body.innerHTML = '<div class="ev-quiet">Positives unavailable.</div>';
    }
  };
})();
