/* Per-symbol Hedgeye dossier. Reads GET /api/symbol/{sym}/hedgeye.
 * Accepts ?sym=XXX in the URL (so the actionable panel can deep-link).
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

  function rows(arr, cols) {
    if (!arr || !arr.length) return '<div style="color:#999; font-size:11px;">none</div>';
    var head = '<tr>' + cols.map(function (c) { return '<th>' + esc(c.label) + '</th>'; }).join('') + '</tr>';
    var body = arr.map(function (r) {
      return '<tr>' + cols.map(function (c) {
        var v = r[c.key];
        if (typeof v === 'string' && v.length > 16 && /T\d\d:/.test(v)) v = v.slice(0, 16).replace('T', ' ');
        return '<td>' + esc(v == null ? '' : v) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<table class="ds-tbl"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
  }
  function sec(label, html) { return '<div class="ds-sec"><h3>' + esc(label) + '</h3>' + html + '</div>'; }

  async function load(sym) {
    if (!sym) return;
    $('body').innerHTML = '<div style="color:#777;">Loading…</div>';
    try {
      var d = await getJson('/api/symbol/' + encodeURIComponent(sym) + '/hedgeye');
      var html = '<h2 style="margin:0 0 10px;">' + esc(d.symbol) + ' <span style="font-size:12px; color:#999;">as of ' + esc(d.date) + '</span></h2>';
      if (d.risk_range) {
        var rr = d.risk_range;
        html += sec('Risk Range', '<div class="rr-box"><strong>' + esc(rr.outlook || '') + '</strong> · buy ' +
          esc(rr.buy_trade) + ' / sell ' + esc(rr.sell_trade) +
          (rr.last_price != null ? ' · last ' + esc(rr.last_price) : '') +
          ' <span style="color:#999; font-size:11px;">(' + esc(rr.snapshot_date) + ')</span></div>');
      }
      html += sec('Trend flips', rows(d.trend_flips, [{ key: 'as_of_date', label: 'Date' }, { key: 'from_trend', label: 'From' }, { key: 'to_trend', label: 'To' }]));
      html += sec('Real-Time Alerts', rows(d.alerts, [{ key: 'alert_ts', label: 'When' }, { key: 'action', label: 'Action' }, { key: 'side', label: 'Side' }, { key: 'price', label: 'Price' }, { key: 'is_correction', label: 'Corr' }]));
      html += sec('Investing Ideas changes', rows(d.ii_changes, [{ key: 'event_date', label: 'Date' }, { key: 'outlook', label: 'Outlook' }, { key: 'change_str', label: 'Change' }]));
      html += sec('ETF changes', rows(d.etf_changes, [{ key: 'event_date', label: 'Date' }, { key: 'outlook', label: 'Outlook' }, { key: 'change_str', label: 'Change' }]));
      html += sec('Top-5 appearances', rows(d.top5, [{ key: 'snapshot_date', label: 'Date' }, { key: 'rank', label: 'Rank' }, { key: 'side', label: 'Side' }, { key: 'rationale_snippet', label: 'Why' }]));
      html += sec('Notes', rows(d.notes, [{ key: 'note_date', label: 'Date' }, { key: 'source_type', label: 'Source' }, { key: 'subject', label: 'Subject' }]));
      $('body').innerHTML = html;
    } catch (e) { $('body').innerHTML = '<div style="color:#c33;">Load failed.</div>'; }
  }

  function init() {
    var m = (location.search.match(/[?&]sym=([^&]+)/));
    var sym = m ? decodeURIComponent(m[1]) : '';
    if (sym) $('sym').value = sym;
    $('go').addEventListener('click', function () { load($('sym').value); });
    $('sym').addEventListener('keydown', function (e) { if (e.key === 'Enter') load($('sym').value); });
    if (sym) load(sym);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
