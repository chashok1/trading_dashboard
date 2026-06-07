/* Market-context band — renders the FRED macro feed on the Cockpit screen.
 *
 * Self-contained and side-effect-free except for the DOMContentLoaded hook.
 * Reads:
 *   GET  /api/macro            -> { as_of, groups:{grp:[tiles]}, last_fetch }
 *   POST /api/macro/refresh    -> throttled fetch (may return {skipped:true,...})
 *
 * Renders into #macroBand; wires #macroRefreshBtn; stamps #macroAsOf /
 * #macroLastFetch. Reads never call FRED; the Refresh button respects the
 * server-side throttle, so repeated clicks cannot stack up FRED requests.
 */
(function () {
  'use strict';

  var fetchJson = (window.td_common && window.td_common.fetchJson) || async function (url, opts) {
    var r = await fetch(url, opts);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };

  var GROUP_LABELS = {
    index: 'Indexes',
    rates: 'Rates & curve',
    inflation: 'Inflation',
    jobs: 'Jobs',
    risk: 'Risk',
    fx_cmdty: 'Dollar & commodities',
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtValue(v, unit) {
    if (v === null || v === undefined) return '—';
    var n = Number(v);
    if (!isFinite(n)) return '—';
    if (unit === '%') return n.toFixed(2) + '%';
    if (unit === '$') return '$' + n.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  // For % series (yields, unemployment, spreads) the meaningful move is the
  // absolute change in points; for everything else it's the percent move.
  function changeHtml(item) {
    var isPct = item.unit === '%';
    var d = isPct ? item.chg_abs : item.chg_pct;
    if (d === null || d === undefined || !isFinite(Number(d))) return '';
    d = Number(d);
    var cls = d > 0 ? 'mt-up' : d < 0 ? 'mt-down' : 'mt-flat';
    var arrow = d > 0 ? '▲' : d < 0 ? '▼' : '•';
    var sign = d > 0 ? '+' : '';
    var body = isPct ? (sign + d.toFixed(2) + ' pts') : (sign + d.toFixed(2) + '%');
    return '<div class="mt-chg ' + cls + '">' + arrow + ' ' + body + '</div>';
  }

  function tileHtml(item) {
    var date = item.latest_date ? String(item.latest_date).slice(0, 10) : '';
    return '' +
      '<div class="macro-tile" title="' + esc(item.series_id) + '">' +
        '<div class="mt-label">' + esc(item.label) + '</div>' +
        '<div class="mt-value">' + fmtValue(item.latest_value, item.unit) + '</div>' +
        changeHtml(item) +
        (date ? '<div class="mt-date">' + esc(date) + '</div>' : '') +
      '</div>';
  }

  function render(data) {
    var band = document.getElementById('macroBand');
    if (!band) return;
    var groups = (data && data.groups) || {};
    var keys = Object.keys(groups);
    if (!keys.length) {
      band.innerHTML = '<div class="macro-empty">No macro data yet. Click “Refresh data”, ' +
        'or run <code>python -m etl.fetch_macro --full</code>.</div>';
    } else {
      var html = '';
      keys.forEach(function (g) {
        var tiles = groups[g] || [];
        if (!tiles.length) return;
        html += '<div class="macro-group">' +
          '<div class="macro-group-label">' + esc(GROUP_LABELS[g] || g) + '</div>' +
          '<div class="macro-tiles">' + tiles.map(tileHtml).join('') + '</div>' +
          '</div>';
      });
      band.innerHTML = html;
    }

    var asOf = document.getElementById('macroAsOf');
    if (asOf) asOf.textContent = data && data.as_of ? ('as of ' + data.as_of) : '';

    stampLastFetch(data && data.last_fetch);
  }

  function ago(iso) {
    if (!iso) return 'never';
    var ms = Date.now() - Date.parse(iso);
    if (!isFinite(ms)) return '';
    var m = Math.round(ms / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return m + 'm ago';
    var h = Math.round(m / 60);
    if (h < 24) return h + 'h ago';
    return Math.round(h / 24) + 'd ago';
  }

  function stampLastFetch(lf, note) {
    var el = document.getElementById('macroLastFetch');
    if (!el) return;
    el.classList.remove('is-throttled');
    if (note) {
      el.textContent = note;
      el.classList.add('is-throttled');
      return;
    }
    el.textContent = lf && lf.started_at ? ('updated ' + ago(lf.started_at)) : 'not fetched yet';
  }

  async function load() {
    var band = document.getElementById('macroBand');
    try {
      var data = await fetchJson('/api/macro');
      render(data);
    } catch (e) {
      if (band) band.innerHTML = '<div class="macro-error">Could not load market data: ' +
        esc(e && e.message ? e.message : e) + '</div>';
    }
  }

  async function refresh() {
    var btn = document.getElementById('macroRefreshBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Refreshing…'; }
    try {
      var res = await fetchJson('/api/macro/refresh', { method: 'POST' });
      if (res && res.skipped) {
        stampLastFetch(null, 'Up to date (fetched ' + (res.age_min || 0) + 'm ago)');
      } else {
        await load();  // re-render with the freshly fetched values
      }
    } catch (e) {
      stampLastFetch(null, 'Refresh failed: ' + esc(e && e.message ? e.message : e));
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Refresh data'; }
    }
  }

  function init() {
    if (!document.getElementById('macroBand')) return;  // not on this page
    var btn = document.getElementById('macroRefreshBtn');
    if (btn) btn.addEventListener('click', refresh);
    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
