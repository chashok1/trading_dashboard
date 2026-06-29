/* Hedgeye action panel (TASK_100) — renders the intraday Hedgeye money-makers on
 * the Actionable screen: Top-5 ideas, today's Real-Time Alerts, Risk-Range trend
 * flips, and the Macro Show Bullish/Bearish stance.
 *
 * Reads: GET /api/actionable/hedgeye?date=<#datePicker value>
 * Renders into #hedgeyePanel. Re-renders on date change and Refresh. Self-contained;
 * empty sections render a quiet "none today", never an error.
 */
(function () {
  'use strict';

  var fetchJson = (window.td_common && window.td_common.fetchJson) || async function (url) {
    var r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function sideColor(side) {
    var v = String(side || '').toLowerCase();
    if (v.indexOf('long') >= 0 || v.indexOf('bull') >= 0 || v.indexOf('buy') >= 0) return '#1d9e75';
    if (v.indexOf('short') >= 0 || v.indexOf('bear') >= 0 || v.indexOf('sell') >= 0) return '#d4537e';
    return '#888780';
  }

  function symLink(sym) {
    var u = '/symbol-hedgeye?sym=' + encodeURIComponent(sym);
    return '<a href="' + u + '" style="color:inherit; text-decoration:none; border-bottom:1px dotted #aaa;">' + esc(sym) + '</a>';
  }

  function chip(text, color) {
    return '<span style="display:inline-block; padding:0 5px; border-radius:3px; font-size:9px; ' +
      'font-weight:700; color:#fff; background:' + color + '; margin-left:4px;">' + esc(text) + '</span>';
  }

  function sectionHtml(title, bodyHtml, empty) {
    var inner = bodyHtml || ('<span style="color:#999; font-size:10px;">' + esc(empty || 'none today') + '</span>');
    return '<div style="flex:1; min-width:160px;">' +
      '<div style="font-weight:700; font-size:9px; text-transform:uppercase; letter-spacing:0.5px; color:#555; margin-bottom:3px;">' +
      esc(title) + '</div>' + inner + '</div>';
  }

  function top5Html(rows) {
    if (!rows || !rows.length) return '';
    return rows.map(function (r) {
      return '<div title="' + esc(r.rationale || '') + '" style="font-size:11px; line-height:1.5;">' +
        '<span style="color:#999;">#' + esc(r.rank) + '</span> ' +
        '<strong>' + symLink(r.symbol) + '</strong>' +
        '<span style="color:' + sideColor(r.side) + '; font-size:10px;"> ' + esc(r.side || '') + '</span>' +
        '</div>';
    }).join('');
  }

  function alertsHtml(rows) {
    if (!rows || !rows.length) return '';
    return rows.map(function (a) {
      var durs = (a.durations || []).map(function (d) { return chip(d, '#534ab7'); }).join('');
      var corr = a.is_correction ? chip('CORRECTION', '#993c1d') : '';
      var px = (a.price != null) ? ' @ ' + esc(a.price) : '';
      return '<div title="' + esc(a.notes || '') + '" style="font-size:11px; line-height:1.55;">' +
        '<strong style="color:' + sideColor(a.side) + ';">' + esc(a.action || a.side || '') + '</strong> ' +
        '<strong>' + symLink(a.symbol) + '</strong>' + esc(px) + durs + corr +
        '</div>';
    }).join('');
  }

  function flipsHtml(rows) {
    if (!rows || !rows.length) return '';
    return rows.map(function (f) {
      return '<div style="font-size:11px; line-height:1.5;">' +
        '<strong>' + symLink(f.symbol) + '</strong> ' +
        '<span style="color:' + sideColor(f.from) + ';">' + esc(f.from) + '</span>' +
        ' <span style="color:#999;">&rarr;</span> ' +
        '<span style="color:' + sideColor(f.to) + ';">' + esc(f.to) + '</span>' +
        '</div>';
    }).join('');
  }

  function earlyLookHtml(el) {
    if (!el || !el.takeaways) return '';
    var bullets = el.takeaways.split(/[••�]+/).map(function (s) {
      return s.replace(/\s+/g, ' ').trim();
    }).filter(function (s) { return s.length > 10; });
    if (!bullets.length) {
      bullets = [el.takeaways.slice(0, 600)];
    }
    return bullets.map(function (b) {
      return '<div style="font-size:10px; line-height:1.5; margin-bottom:3px; padding-left:8px; ' +
        'text-indent:-8px;">' +
        '<span style="color:#534ab7; font-weight:700;">&#8226;</span> ' +
        esc(b.slice(0, 200)) + (b.length > 200 ? '…' : '') + '</div>';
    }).slice(0, 5).join('');
  }

  function msrHtml(msr) {
    if (!msr) return '';
    var parts = [];
    if (msr.gamma_throttle != null)
      parts.push('<span style="color:#555;">Gamma Throttle:</span> <strong>' +
        esc(msr.gamma_throttle.toFixed(2)) + '</strong>');
    if (msr.rvol_10day != null)
      parts.push('<span style="color:#555;">10-Day rVol:</span> <strong>' +
        esc(msr.rvol_10day.toFixed(2)) + '</strong>');
    var metrics = parts.length
      ? '<div style="font-size:11px; line-height:1.7;">' + parts.join('&nbsp;&nbsp;') + '</div>'
      : '';
    var img = msr.image_url
      ? '<img src="' + esc(msr.image_url) + '" ' +
        'style="max-width:100%; height:auto; max-height:110px; margin-top:5px; ' +
        'border-radius:3px; display:block; cursor:pointer;" ' +
        'title="MSR ' + esc(msr.date || '') + '" ' +
        'onerror="this.style.display=\'none\'">'
      : '';
    return metrics + img;
  }

  function positionsHtml(pos) {
    if (!pos || (!pos.longs.length && !pos.shorts.length)) return '';
    var symHtml = function (p, color) {
      var s = symLink(p.sym);
      return p.best
        ? '<span style="color:' + color + '; font-weight:700;">' + s + '*</span>'
        : '<span style="color:' + color + ';">' + s + '</span>';
    };
    var line = function (label, arr, color) {
      if (!arr.length) return '';
      return '<div style="font-size:10px; line-height:1.6;">' +
        '<span style="font-weight:700; color:' + color + ';">' +
        label + ' (' + arr.length + ')</span> ' +
        arr.map(function (p) { return symHtml(p, color); }).join(' ') + '</div>';
    };
    var n = (pos.neutral || []);
    var neutralLine = n.length
      ? '<div style="font-size:10px; line-height:1.5; color:#888;">N ' +
        n.map(function (p) { return esc(p.sym); }).join(' ') + '</div>'
      : '';
    return line('L', pos.longs, '#1d9e75') +
           line('S', pos.shorts, '#d4537e') +
           neutralLine;
  }

  function stanceHtml(stance) {
    stance = stance || {};
    var bull = (stance.bullish || []);
    var bear = (stance.bearish || []);
    if (!bull.length && !bear.length) return '';
    var line = function (label, arr, color) {
      if (!arr.length) return '';
      return '<div style="font-size:10px; line-height:1.5;"><span style="color:' + color +
        '; font-weight:700;">' + label + ' (' + arr.length + ')</span>: ' +
        esc(arr.slice(0, 14).join(', ')) + (arr.length > 14 ? ' …' : '') + '</div>';
    };
    return line('Bullish', bull, '#1d9e75') + line('Bearish', bear, '#d4537e');
  }

  function render(data) {
    var el = document.getElementById('hedgeyePanel');
    if (!el) return;
    var hasAny = (data.top5 && data.top5.length) || (data.alerts && data.alerts.length) ||
      (data.trend_flips && data.trend_flips.length) ||
      (data.stance && ((data.stance.bullish || []).length || (data.stance.bearish || []).length)) ||
      (data.msr && (data.msr.gamma_throttle != null || data.msr.rvol_10day != null)) ||
      (data.early_look && data.early_look.takeaways) ||
      (data.positions && (data.positions.longs.length || data.positions.shorts.length));
    if (!hasAny) { el.style.display = 'none'; return; }

    var elDate = data.early_look ? ' <span style="color:#999;font-weight:400;">(' + esc(data.early_look.date || '') + ')</span>' : '';
    var posDate = data.positions ? ' <span style="color:#999;font-weight:400;">(' + esc(data.positions.date || '') + ')</span>' : '';
    var body = '<div style="display:flex; gap:14px; flex-wrap:wrap; align-items:flex-start;">' +
      sectionHtml('Top-5 Ideas', top5Html(data.top5)) +
      sectionHtml('Real-Time Alerts', alertsHtml(data.alerts)) +
      sectionHtml('Trend Change', flipsHtml(data.trend_flips)) +
      sectionHtml('Macro TL;DR', stanceHtml(data.stance)) +
      sectionHtml('Mkt Situation', msrHtml(data.msr), 'no data') +
      '</div>' +
      (data.positions
        ? '<div style="margin-top:8px; border-top:1px solid #ece9f8; padding-top:6px;">' +
          '<div style="font-weight:700; font-size:9px; text-transform:uppercase; ' +
          'letter-spacing:0.5px; color:#555; margin-bottom:4px;">Hedgeye Positions' + posDate + '</div>' +
          positionsHtml(data.positions) + '</div>'
        : '') +
      (data.early_look
        ? '<div style="margin-top:8px; border-top:1px solid #ece9f8; padding-top:6px;">' +
          '<div style="font-weight:700; font-size:9px; text-transform:uppercase; ' +
          'letter-spacing:0.5px; color:#555; margin-bottom:4px;">Early Look' + elDate + '</div>' +
          earlyLookHtml(data.early_look) + '</div>'
        : '');

    el.innerHTML =
      '<div style="padding:5px 10px; background:#fbfbfe; border:1px solid #e6e3f5; border-radius:5px;">' +
      '<div style="font-weight:700; font-size:9px; text-transform:uppercase; letter-spacing:0.6px; color:#534ab7; margin-bottom:4px;">' +
      'Hedgeye' + ((data.as_of || data.date) ? ' · ' + esc(data.as_of || data.date) : '') + '</div>' + body + '</div>';
    el.style.display = 'block';
  }

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  async function load() {
    try {
      var d = currentDate();
      var data = await fetchJson('/api/actionable/hedgeye' + (d ? '?date=' + encodeURIComponent(d) : ''));
      render(data);
    } catch (e) {
      var el = document.getElementById('hedgeyePanel');
      if (el) el.style.display = 'none';
    }
  }

  function init() {
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    // Initial paint — wait a beat for the date picker to populate.
    setTimeout(load, 600);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
