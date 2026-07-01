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

  // Bold "(TICKER)" and "#QuadN" mentions within a paragraph of prose (e.g. Macro Commentary).
  function boldTickers(s) {
    return esc(s)
      .replace(/\(([A-Z][A-Z0-9.\-]{0,9})\)/g, '<strong>($1)</strong>')
      .replace(/#Quad[1-4]/gi, '<strong>$&</strong>');
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

  // mm/dd H:MM AM/PM from ISO timestamp (email received time)
  function fmtRecv(ts) {
    if (!ts) return '';
    var dt = new Date(ts);
    var mo = dt.getMonth() + 1;
    var dd = String(dt.getDate()).padStart(2, '0');
    var hh = dt.getHours(), mn = String(dt.getMinutes()).padStart(2, '0');
    var ap = hh >= 12 ? 'PM' : 'AM';
    if (hh > 12) hh -= 12; else if (hh === 0) hh = 12;
    return mo + '/' + dd + ' ' + hh + ':' + mn + ' ' + ap;
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
      return '<div title="' + esc(a.notes || '') + '" style="font-size:9px; line-height:1.6;">' +
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
      return '<div style="font-size:11px; line-height:1.5; margin-bottom:3px;' +
        'padding-left:9px; text-indent:-9px;">' +
        '<span style="color:#534ab7; font-weight:700;">&#8226;</span> ' +
        esc(b.slice(0, 200)) + (b.length > 200 ? '…' : '') + '</div>';
    }).slice(0, 5).join('');
  }

  function msrCardHtml(msr, asOf, loadedAt) {
    var metrics = '';
    if (msr) {
      if (msr.gamma_throttle != null)
        metrics += '<div style="font-size:10px; line-height:1.8;">' +
          '<span style="color:#888;">Gamma Throttle</span> ' +
          '<strong>' + esc(msr.gamma_throttle.toFixed(2)) + '</strong></div>';
      if (msr.rvol_10day != null)
        metrics += '<div style="font-size:10px; line-height:1.8;">' +
          '<span style="color:#888;">Relative Volume</span> ' +
          '<strong>' + esc(msr.rvol_10day.toFixed(2)) + '</strong></div>';
    }
    var img = (msr && msr.image_url)
      ? '<img src="' + esc(msr.image_url) + '" ' +
        'style="height:90px; width:auto; border-radius:3px; display:block; cursor:pointer;" ' +
        'title="MSR ' + esc((msr && msr.date) || '') + '" ' +
        'onerror="this.style.display=\'none\'">'
      : '';
    var msrLabel = (msr && msr.received_at) ? fmtRecv(msr.received_at)
                 : (msr && msr.date)        ? fmtMD(msr.date) : '';
    var msrTileTs = msrLabel
      ? ' <span style="font-size:8px; color:#bbb; font-weight:400;">· ' + esc(msrLabel) + '</span>'
      : '';
    var panelTitle = '<div style="font-weight:700; font-size:9px; text-transform:uppercase; ' +
      'letter-spacing:0.6px; color:#534ab7; margin-bottom:4px; display:flex; ' +
      'align-items:baseline; justify-content:space-between; gap:8px;">' +
      '<span>Hedgeye' +
      (loadedAt ? ' <span style="color:#bbb; font-weight:400; font-size:8px;">· ' + esc(loadedAt) + '</span>' : '') +
      '</span>' +
      '<span>' + linked('Mkt Situation', 'mkt_situation') + msrTileTs + '</span>' +
      '</div>';
    return '<div style="background:#fff; border:1px solid #e0daf5; border-radius:5px; ' +
      'padding:7px 10px; flex:0 0 340px; ' +
      'box-shadow:0 1px 4px rgba(83,74,183,0.07); display:flex; flex-direction:column;">' +
      panelTitle +
      '<div style="display:flex; gap:0; align-items:flex-start; flex-wrap:nowrap; flex:1; min-height:0; overflow-y:auto;">' +
      '<div style="flex:0 0 130px; min-width:0;">' + metrics + '</div>' +
      (img ? '<div style="flex-shrink:0;">' + img + '</div>' : '') +
      '</div></div>';
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

  function sssChangesHtml(sss) {
    if (!sss || !sss.changes || !sss.changes.length) return '';
    var adds = sss.changes.filter(function (c) { return c.action === 'add'; });
    var removes = sss.changes.filter(function (c) { return c.action === 'remove'; });
    var line = function (label, arr, color) {
      if (!arr.length) return '';
      return '<div style="font-size:10px; line-height:1.7;">' +
        '<span style="font-weight:700; color:' + color + '; font-size:9px;">' + label + '</span> ' +
        arr.map(function (c) { return symLink(c.sym); }).join(' ') + '</div>';
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

  function render(data, loadedAt) {
    var el = document.getElementById('hedgeyePanel');
    if (!el) return;

    var hasAny = (data.top5 && data.top5.length) ||
      (data.alerts && data.alerts.length) ||
      (data.trend_flips && data.trend_flips.length) ||
      (data.stance && ((data.stance.bullish || []).length || (data.stance.bearish || []).length)) ||
      (data.msr && (data.msr.gamma_throttle != null || data.msr.rvol_10day != null)) ||
      (data.early_look && data.early_look.takeaways) ||
      (data.positions && (data.positions.longs.length || data.positions.shorts.length)) ||
      (data.etf_changes && data.etf_changes.changes && data.etf_changes.changes.length) ||
      (data.sss_changes && data.sss_changes.changes && data.sss_changes.changes.length) ||
      (data.call_macro && data.call_macro.note_text);
    if (!hasAny) { el.style.display = 'none'; return; }

    var collapsed = localStorage.getItem('hePanel_collapsed') === '1';
    var etfTitle = 'ETFCHG';
    var sssTitle = 'SSS';

    // Show email received time (mm/dd H:MM AM/PM) when available, else date only (mm/dd).
    var td = function (receivedAt, dateIso) {
      var label = receivedAt ? fmtRecv(receivedAt) : (dateIso ? fmtMD(dateIso) : '');
      return label ? ' <span style="font-size:8px; color:#bbb; font-weight:400;">' + esc(label) + '</span>' : '';
    };

    var CARD_BASE = 'background:#fff; border:1px solid #e0daf5; border-radius:5px; ' +
      'padding:7px 10px; min-width:0; box-shadow:0 1px 4px rgba(83,74,183,0.07); ' +
      'display:flex; flex-direction:column;';
    var CARD_HDR = 'font-weight:700; font-size:8.5px; text-transform:uppercase; ' +
      'letter-spacing:0.55px; color:#534ab7; padding-bottom:4px; margin-bottom:4px; ' +
      'border-bottom:1px solid #edeafb; flex-shrink:0;';
    var CARD_BODY = 'overflow-y:auto; flex:1; min-height:0;';

    var row1 = (data.early_look || data.msr || (data.top5 && data.top5.length))
      ? '<div style="display:flex; gap:3px; flex-wrap:nowrap; align-items:stretch; height:125px;">' +
        msrCardHtml(data.msr, data.as_of || data.date, loadedAt) +
        '<div style="' + CARD_BASE + 'flex:0 0 calc(15ch + 20px);">' +
        '<div style="' + CARD_HDR + '">' + linked('Top-5', 'top5') + td(data.top5_received_at, data.top5_date) + '</div>' +
        '<div style="' + CARD_BODY + '">' +
        (top5Html(data.top5) || '<span style="color:#bbb; font-size:10px;">none</span>') +
        '</div></div>' +
        (data.early_look
          ? '<div style="' + CARD_BASE + 'flex:1 1 0;">' +
            '<div style="' + CARD_HDR + '">' + linked('Early Look', 'early_look') + td(data.early_look.received_at, data.early_look.date) + '</div>' +
            '<div style="' + CARD_BODY + '">' + earlyLookHtml(data.early_look) + '</div></div>'
          : '') +
        '</div>'
      : '';

    var _card = function (title, body, flex, dateHtml) {
      return '<div style="' + CARD_BASE + flex + ';">' +
        '<div style="' + CARD_HDR + '">' + title + (dateHtml || '') + '</div>' +
        '<div style="' + CARD_BODY + '">' +
        (body || '<span style="color:#bbb; font-size:10px;">none</span>') +
        '</div></div>';
    };
    var rowMacro = data.call_macro
      ? '<div style="display:flex; gap:3px; flex-wrap:nowrap; align-items:stretch; margin-top:3px;">' +
        '<div style="' + CARD_BASE + 'flex:1;">' +
        '<div style="font-size:11px; line-height:1.6;">' +
        '<span style="font-weight:700; font-size:8.5px; text-transform:uppercase; ' +
        'letter-spacing:0.55px; color:#534ab7;">' + linked('Macro Commentary', 'call_macro') + '</span>' +
        td(data.call_macro.received_at, data.call_macro.date) + ' ' +
        boldTickers(data.call_macro.note_text) +
        '</div></div></div>'
      : '';
    var row2 =
      '<div style="display:flex; gap:3px; flex-wrap:nowrap; align-items:stretch; height:110px; margin-top:3px;">' +
      _card(linked('Call', 'call'),                  positionsHtml(data.positions),    'flex:2',                       td(data.positions && data.positions.received_at, data.positions && data.positions.date)) +
      _card(linked('Alerts', 'alerts'),              alertsHtml(data.alerts),          'flex:0 0 calc(35ch + 20px)',   td(data.rta_received_at, data.rta_date)) +
      _card(linked(etfTitle, 'etf_pro'),             etfChangesHtml(data.etf_changes), 'flex:1',                       td(data.etf_changes && data.etf_changes.received_at, data.etf_changes && data.etf_changes.date)) +
      _card(linked(sssTitle, 'sss'),                 sssChangesHtml(data.sss_changes), 'flex:1',                       td(data.sss_changes && data.sss_changes.received_at, data.sss_changes && data.sss_changes.date)) +
      _card(linked('Trend Change', 'trend_change'),  flipsHtml(data.trend_flips),      'flex:0 0 calc(22.5ch + 18px)', td(data.trend_flips_received_at, data.trend_flips_date)) +
      _card(linked('Macro TL;DR', 'macro_show'),     stanceHtml(data.stance),          'flex:2',                       td(data.stance_received_at, data.stance_date)) +
      '</div>';

    var bodyHtml =
      '<div id="hePanelBody" style="display:' + (collapsed ? 'none' : 'block') + '; margin-top:2px;">' +
      row1 + rowMacro + row2 + '</div>';

    el.innerHTML =
      '<div style="padding:2px 4px; background:#f0eefb; border:1px solid #d5d0f0; ' +
      'border-radius:6px;">' + bodyHtml + '</div>';
    el.style.display = 'block';

    window._hePanelToggle = function () {
      var body = document.getElementById('hePanelBody');
      var btn = document.getElementById('hePanelToggle');
      if (!body) return;
      var nowHidden = body.style.display === 'none';
      body.style.display = nowHidden ? 'block' : 'none';
      if (btn) btn.classList.toggle('icon-on', nowHidden);
      if (btn) btn.classList.toggle('icon-off', !nowHidden);
      localStorage.setItem('hePanel_collapsed', nowHidden ? '0' : '1');
    };
  }

  var _links = {};

  function linked(text, key) {
    var l = _links[key];
    if (!l || !l.url) return text;
    return '<a href="' + esc(l.url) + '" target="_blank" rel="noopener" ' +
      'style="color:inherit; text-decoration:none;" title="' + esc(l.label) + '">' +
      text + ' <span style="font-size:7px; opacity:0.55; font-weight:400;">&#8599;</span></a>';
  }

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  function fmtLoadedAt() {
    var now = new Date();
    var mo = now.getMonth() + 1;
    var dd = String(now.getDate()).padStart(2, '0');
    var hh = now.getHours(), mn = String(now.getMinutes()).padStart(2, '0');
    var ap = hh >= 12 ? 'PM' : 'AM';
    if (hh > 12) hh -= 12; else if (hh === 0) hh = 12;
    return mo + '/' + dd + ' ' + hh + ':' + mn + ' ' + ap;
  }

  async function load() {
    try {
      var d = currentDate();
      var [data, links] = await Promise.all([
        fetchJson('/api/actionable/hedgeye' + (d ? '?date=' + encodeURIComponent(d) : '')),
        fetchJson('/api/ext-links').catch(function () { return {}; }),
      ]);
      _links = links || {};
      render(data, fmtLoadedAt());
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
