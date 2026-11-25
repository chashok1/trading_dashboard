/* positives.js -- Positives panel under the Risk Dial (#positivesBody). Reads GET /api/cockpit/positives.
 * Styled with the Risk Dial's own classes (rd-gauge-row / rd-quiet-toggle / rd-quiet-list): active signs show as rows,
 * inactive ones hide behind the toggle. Display only: never changes the Risk Dial score or any action. */
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
      var on = items.filter(function (it) { return it.on; });
      var off = items.filter(function (it) { return !it.on; });
      var tip = function (it) { return [it.text, it.history].filter(Boolean).join('\n'); };
      var rows = on.map(function (it) {
        // 2026-11-25, user: "oversold" rows are a warning (stocks often fall further first), never the green tick.
        var warn = /oversold$/.test(it.key);
        return '<div class="rd-gauge-row ' + (warn ? 'sev-warn' : 'sev-pos') + '" title="' + esc(tip(it)) + '">' +
          '<span class="rd-rail"></span><span class="rd-wt">' + (warn ? '&#9888;' : '&#10004;') + '</span>' +
          '<span class="rd-gauge-text"><strong>' + esc(it.title) + '</strong> — <span class="rd-desc">' + esc(it.text) + '</span></span></div>';
      }).join('');
      var quiet = off.map(function (it) {
        return '<span class="rd-q-item" title="' + esc(tip(it)) + '">' + '<strong>' + esc(it.title) + ':</strong> ' + esc(it.text) + '</span>';
      }).join('');
      body.innerHTML =
        '<div class="rd-gauge-list">' + rows + '</div>' +
        '<div class="rd-bottom-row"><span class="rd-quiet-toggle" onclick="document.getElementById(\'posQuietList\').classList.toggle(\'open\')">' +
        'Positives not active (' + off.length + ')</span></div>' +
        '<div class="rd-quiet-list" id="posQuietList">' + quiet + '</div>';
    } catch (e) {
      console.error('positives failed:', e);
      body.innerHTML = '<div class="ev-fail">&#9888; Positives unavailable.</div>';
    }
  };
})();
