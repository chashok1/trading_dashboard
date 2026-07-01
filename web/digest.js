/* Digest screen (P4) — pre-open + weekly roll-up.
 * Reads GET /api/digest/preopen and GET /api/digest/weekly.
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  async function getJson(u) { var r = await fetch(u); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }

  function sideColor(side) {
    var v = String(side || '').toLowerCase();
    if (v.indexOf('long') >= 0 || v.indexOf('bull') >= 0 || v.indexOf('buy') >= 0) return '#1d9e75';
    if (v.indexOf('short') >= 0 || v.indexOf('bear') >= 0 || v.indexOf('sell') >= 0) return '#d4537e';
    return null;
  }

  // Color a leading "Company Name (TICKER): " prefix red/green by signal_kind.
  var NAME_TICKER_PREFIX = /^([^\n(]*\([A-Z][A-Z0-9.\-]{0,9}\):\s*)([\s\S]*)$/;

  function noteTextHtml(n) {
    var raw = n.note_text || '';
    var m = NAME_TICKER_PREFIX.exec(raw);
    if (m) {
      var color = sideColor(n.signal_kind);
      var style = 'font-weight:700;' + (color ? ' color:' + color + ';' : '');
      return '<span style="' + style + '">' + esc(m[1]) + '</span>' + esc(m[2]);
    }
    return esc(raw);
  }

  function noteHtml(n) {
    return '<div class="dg-note"><div class="m">' + esc(n.note_date || '') + ' · ' + esc(n.source_type || '') + '</div>' +
      '<div style="font-weight:600;">' + esc(n.subject || '') + '</div>' +
      '<div style="color:#444; white-space:pre-wrap;">' + noteTextHtml(n) + '</div>' +
      '</div>';
  }
  function sectionHtml(label, notes) {
    var body = (notes && notes.length) ? notes.map(noteHtml).join('') : '<div style="color:#999; font-size:11px;">none</div>';
    return '<div class="dg-sec"><h3>' + esc(label) + '</h3>' + body + '</div>';
  }

  function renderPreopen(d) {
    var html = (d.sections || []).map(function (s) { return sectionHtml(s.label, s.notes); }).join('');
    var alerts = d.overnight_alerts || [];
    var aHtml = alerts.length ? alerts.map(function (a) {
      return '<div class="dg-alert"><strong>' + esc(a.action || a.side || '') + '</strong> ' +
        esc(a.symbol) + (a.price != null ? ' @ ' + esc(a.price) : '') +
        ' <span style="color:#999; font-size:10px;">' + esc((a.alert_ts || '').slice(0, 16).replace('T', ' ')) + '</span></div>';
    }).join('') : '<div style="color:#999; font-size:11px;">none</div>';
    html += '<div class="dg-sec"><h3>Overnight Real-Time Alerts</h3>' + aHtml + '</div>';
    $('body').innerHTML = html;
  }

  function renderWeekly(d) {
    var ps = d.portfolio_solutions || [];
    var psHtml = ps.length ? '<table class="dg-tbl"><thead><tr><th>Rank</th><th>Ticker</th><th>Asset class</th><th>Sizing</th></tr></thead><tbody>' +
      ps.map(function (r) {
        return '<tr><td>' + esc(r.rank) + '</td><td>' + esc(r.ticker) + '</td><td>' + esc(r.asset_class || '') + '</td><td>' + esc(r.position_sizing || '') + '</td></tr>';
      }).join('') + '</tbody></table>' : '<div style="color:#999; font-size:11px;">none</div>';
    var html = '<div class="dg-sec"><h3>Portfolio Solutions' + (d.ps_date ? ' · ' + esc(d.ps_date) : '') + '</h3>' + psHtml + '</div>';
    html += sectionHtml('Weekly / Monthly / Quarterly notes', d.notes);
    $('body').innerHTML = html;
  }

  async function load() {
    var mode = $('mode').value;
    var qs = $('date').value ? '?date=' + encodeURIComponent($('date').value) : '';
    $('body').innerHTML = '<div style="color:#777;">Loading…</div>';
    try {
      var d = await getJson('/api/digest/' + mode + qs);
      $('asof').textContent = 'as of ' + (d.date || '');
      if (mode === 'weekly') renderWeekly(d); else renderPreopen(d);
    } catch (e) { $('body').innerHTML = '<div style="color:#c33;">Load failed.</div>'; }
  }

  function init() {
    $('reload').addEventListener('click', load);
    $('mode').addEventListener('change', load);
    $('date').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') load();
    });
    load();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
