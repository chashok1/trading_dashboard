/* Hedgeye action panel — renders intraday Hedgeye signals on the Actionable screen.
 * Reads: GET /api/actionable/hedgeye?date=<#datePicker value>
 * Renders into #hedgeyePanel. Re-renders on date change and Refresh.
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

  // mm/dd from YYYY-MM-DD
  function fmtMD(iso) {
    if (!iso) return '';
    var p = String(iso).split('-');
    return p.length >= 3 ? p[1] + '/' + p[2] : iso;
  }

  // White card box for each panel section
  function sectionHtml(title, bodyHtml, empty) {
    var inner = bodyHtml ||
      '<span style="color:#bbb; font-size:10px;">' + esc(empty || 'none') + '</span>';
    return '<div style="background:#fff; border:1px solid #e0daf5; border-radius:5px; ' +
      'padding:7px 10px; flex:1; min-width:145px; ' +
      'box-shadow:0 1px 4px rgba(83,74,183,0.07);">' +
      '<div style="font-weight:700; font-size:8.5px; text-transform:uppercase; ' +
      'letter-spacing:0.55px; color:#534ab7; padding-bottom:4px; margin-bottom:5px; ' +
      'border-bottom:1px solid #edeafb;">' + title + '</div>' +
      inner + '</div>';
  }

  function top5Html(rows) {
    if (!rows || !rows.length) return '';
    return rows.map(function (r) {
      return '<div title="' + esc(r.rationale || '') + '" style="font-size:11px; line-height:1.55;">' +
        '<span style="color:#bbb; font-size:9px;">#' + esc(r.rank) + '</span> ' +
        '<strong>' + symLink(r.symbol) + '</strong>' +
        '<span style="color:' + sideColor(r.side) + '; font-size:10px;"> ' + esc(r.side || '') + '</span>' +
        '</div>';
    }).join('');
  }

  function fmtTime(iso) {
    // "2026-06-29T10:27:02-04:00" → "10:27" (slices the ET time directly from ISO string)
    if (!iso) return '';
    var t = String(iso).split('T')[1];
    return t ? t.slice(0, 5) : '';
  }

  function alertsHtml(rows) {
    if (!rows || !rows.length) return '';
    return rows.map(function (a) {
      var sc = sideColor(a.side);
      var durs = (a.durations || []).map(function (d) { return chip(d, sc); }).join('');
      var corr = a.is_correction ? chip('CORR', '#993c1d') : '';
      var px = (a.price != null) ? ' <span style="color:#888; font-size:10px;">@ ' + esc(a.price) + '</span>' : '';
      var tm = fmtTime(a.ts);
      var tmHtml = tm ? ' <span style="color:#bbb; font-size:9px;">' + esc(tm) + '</span>' : '';
      return '<div title="' + esc(a.notes || '') + '" style="font-size:11px; line-height:1.6;">' +
        '<strong style="color:' + sc + ';">' + esc(a.action || a.side || '') + '</strong> ' +
        '<strong>' + symLink(a.symbol) + '</strong>' + px + tmHtml + durs + corr +
        '</div>';
    }).join('');
  }

  function flipsHtml(rows) {
    if (!rows || !rows.length) return '';
    return rows.map(function (f) {
      return '<div style="font-size:11px; line-height:1.55;">' +
        '<strong>' + symLink(f.symbol) + '</strong> ' +
        '<span style="color:' + sideColor(f.from) + '; font-size:10px;">' + esc(f.from) + '</span>' +
        ' <span style="color:#ccc;">&rarr;</span> ' +
        '<span style="color:' + sideColor(f.to) + '; font-size:10px;">' + esc(f.to) + '</span>' +
        '</div>';
    }).join('');
  }

  function earlyLookHtml(el) {
    if (!el || !el.takeaways) return '';
    var bullets = el.takeaways.split(/[•••�]+/).map(function (s) {
      return s.replace(/\s+/g, ' ').trim();
    }).filter(function (s) { return s.length > 10; });
    if (!bullets.length) bullets = [el.takeaways.slice(0, 600)];
    return bullets.map(function (b) {
      return '<div style="font-size:10px; line-height:1.5; margin-bottom:3px; ' +
        'padding-left:9px; text-indent:-9px;">' +
        '<span style="color:#534ab7; font-weight:700;">&#8226;</span> ' +
        esc(b.slice(0, 200)) + (b.length > 200 ? '…' : '') + '</div>';
    }).slice(0, 5).join('');
  }

  function msrHtml(msr) {
    if (!msr) return '';
    var parts = [];
    if (msr.gamma_throttle != null)
      parts.push('<span style="color:#888;">GT:</span> <strong>' +
        esc(msr.gamma_throttle.toFixed(2)) + '</strong>');
    if (msr.rvol_10day != null)
      parts.push('<span style="color:#888;">rVol:</span> <strong>' +
        esc(msr.rvol_10day.toFixed(2)) + '</strong>');
    var metrics = parts.length
      ? '<div style="font-size:11px; line-height:1.8;">' + parts.join('&nbsp; ') + '</div>'
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

  function etfChangesHtml(etf) {
    if (!etf || !etf.changes || !etf.changes.length) return '';
    var adds = etf.changes.filter(function (c) { return c.action === 'add'; });
    var removes = etf.changes.filter(function (c) { return c.action === 'remove'; });
    var line = function (label, arr, color) {
      if (!arr.length) return '';
      return '<div style="font-size:10px; line-height:1.7;">' +
        '<span style="font-weight:700; color:' + color + '; font-size:9px;">' + label + '</span> ' +
        arr.map(function (c) {
          var sc = c.side === 'long' ? '#1d9e75' : '#d4537e';
          return '<span style="color:' + sc + ';">' + symLink(c.sym) + '</span>';
        }).join(' ') + '</div>';
    };
    return line('ADD', adds, '#1d9e75') + line('REM', removes, '#c0392b');
  }

  function positionsHtml(pos) {
    if (!pos || (!pos.longs.length && !pos.shorts.length)) return '';
    var symHtml = function (p, color) {
      var s = symLink(p.sym);
      return p.best
        ? '<strong style="color:' + color + ';">' + s + '*</strong>'
        : '<span style="color:' + color + ';">' + s + '</span>';
    };
    var line = function (label, arr, color) {
      if (!arr.length) return '';
      return '<div style="font-size:10px; line-height:1.7;">' +
        '<span style="font-weight:700; color:' + color + '; font-size:9px;">' +
        label + '(' + arr.length + ')</span> ' +
        arr.map(function (p) { return symHtml(p, color); }).join(' ') + '</div>';
    };
    var n = (pos.neutral || []);
    var neutralLine = n.length
      ? '<div style="font-size:10px; line-height:1.5; color:#999; margin-top:1px;">N ' +
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
      return '<div style="font-size:10px; line-height:1.7;">' +
        '<span style="font-weight:700; color:' + color + '; font-size:9px;">' +
        label + '(' + arr.length + ')</span> ' +
        esc(arr.slice(0, 12).join(' ')) + (arr.length > 12 ? ' …' : '') + '</div>';
    };
    return line('L', bull, '#1d9e75') + line('S', bear, '#d4537e');
  }

  function render(data) {
    var el = document.getElementById('hedgeyePanel');
    if (!el) return;

    var hasAny = (data.top5 && data.top5.length) ||
      (data.alerts && data.alerts.length) ||
      (data.trend_flips && data.trend_flips.length) ||
      (data.stance && ((data.stance.bullish || []).length || (data.stance.bearish || []).length)) ||
      (data.msr && (data.msr.gamma_throttle != null || data.msr.rvol_10day != null)) ||
      (data.early_look && data.early_look.takeaways) ||
      (data.positions && (data.positions.longs.length || data.positions.shorts.length)) ||
      (data.etf_changes && data.etf_changes.changes && data.etf_changes.changes.length);
    if (!hasAny) { el.style.display = 'none'; return; }

    var collapsed = localStorage.getItem('hePanel_collapsed') === '1';
    var etfTitle = 'ETFCHG' + (data.etf_changes && data.etf_changes.date
      ? ' ' + fmtMD(data.etf_changes.date) : '');
    var elDateLabel = data.early_look
      ? ' <span style="color:#aaa; font-weight:400; font-size:8px;">(' + esc(fmtMD(data.early_look.date)) + ')</span>'
      : '';

    var flexRow =
      '<div style="display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start;">' +
      sectionHtml('Top-5', top5Html(data.top5)) +
      sectionHtml('Call', positionsHtml(data.positions)) +
      sectionHtml('Alerts', alertsHtml(data.alerts)) +
      sectionHtml(etfTitle, etfChangesHtml(data.etf_changes)) +
      sectionHtml('Trend Change', flipsHtml(data.trend_flips)) +
      sectionHtml('Macro TL;DR', stanceHtml(data.stance)) +
      sectionHtml('Mkt Situation', msrHtml(data.msr), 'no data') +
      '</div>';

    var earlyBox = data.early_look
      ? '<div style="background:#fff; border:1px solid #e0daf5; border-radius:5px; ' +
        'padding:7px 10px; margin-top:8px; box-shadow:0 1px 4px rgba(83,74,183,0.07);">' +
        '<div style="font-weight:700; font-size:8.5px; text-transform:uppercase; ' +
        'letter-spacing:0.55px; color:#534ab7; padding-bottom:4px; margin-bottom:5px; ' +
        'border-bottom:1px solid #edeafb;">Early Look' + elDateLabel + '</div>' +
        earlyLookHtml(data.early_look) + '</div>'
      : '';

    var bodyHtml =
      '<div id="hePanelBody" style="display:' + (collapsed ? 'none' : 'block') + '; margin-top:6px;">' +
      flexRow + earlyBox + '</div>';

    var toggleIcon = collapsed ? '&#9660;' : '&#9650;';
    var header =
      '<div style="display:flex; justify-content:space-between; align-items:center;">' +
      '<div style="font-weight:700; font-size:9px; text-transform:uppercase; ' +
      'letter-spacing:0.6px; color:#534ab7;">' +
      'Hedgeye' + ((data.as_of || data.date) ? ' <span style="color:#aaa; font-weight:400;">· ' +
      esc(data.as_of || data.date) + '</span>' : '') + '</div>' +
      '<button id="hePanelToggle" onclick="window._hePanelToggle()" ' +
      'style="background:none; border:none; cursor:pointer; font-size:11px; ' +
      'color:#534ab7; padding:0 3px; line-height:1; opacity:0.7;">' +
      toggleIcon + '</button></div>';

    el.innerHTML =
      '<div style="padding:7px 10px; background:#f0eefb; border:1px solid #d5d0f0; ' +
      'border-radius:6px;">' + header + bodyHtml + '</div>';
    el.style.display = 'block';

    window._hePanelToggle = function () {
      var body = document.getElementById('hePanelBody');
      var btn = document.getElementById('hePanelToggle');
      if (!body) return;
      var nowHidden = body.style.display === 'none';
      body.style.display = nowHidden ? 'block' : 'none';
      if (btn) btn.innerHTML = nowHidden ? '&#9650;' : '&#9660;';
      localStorage.setItem('hePanel_collapsed', nowHidden ? '0' : '1');
    };
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
    setTimeout(load, 600);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
