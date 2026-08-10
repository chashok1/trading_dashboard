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

  // Rich tooltips (reuses actionable.js's #sourcePop / _showDataPop / hideSourcePop,
  // globals since actionable.js loads un-deferred before this deferred script runs).
  // Each hoverable element gets data-hetip="<index>" instead of a plain title=;
  // _tipHtml is rebuilt every render() so indices always match the current DOM.
  var _tipHtml = [];
  function _richTip(html) {
    _tipHtml.push(html);
    return _tipHtml.length - 1;
  }
  function _popBox(titleHtml, body) {
    return '<div class="sp-title">' + titleHtml + '</div>' +
      '<div style="max-width:320px; white-space:pre-wrap;">' + esc(body || '') + '</div>';
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
      var idx = _richTip(_popBox(
        '#' + esc(r.rank) + ' &middot; ' + esc(r.symbol) + ' &middot; ' + esc(r.side || ''),
        r.rationale));
      return '<div data-hetip="' + idx + '" style="font-size:11px; line-height:1.55;">' +
        '<span style="color:#bbb; font-size:9px;">#' + esc(r.rank) + '</span> ' +
        '<strong style="font-size:9px;">' + symLink(r.symbol) + '</strong>' +
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
      var idx = _richTip(_popBox(
        esc(a.symbol) + ' &middot; RTA' + (tm ? ' &middot; ' + esc(tm) : ''),
        a.notes));
      return '<div data-hetip="' + idx + '" style="font-size:9px; line-height:1.6;">' +
        '<strong style="color:' + sc + ';">' + esc(a.action || a.side || '') + '</strong> ' +
        '<strong>' + symLink(a.symbol) + '</strong>' + px + tmHtml + durs + corr +
        '</div>';
    }).join('');
  }

  // "BULLISH" -> "Bullish" for display only; sideColor()/comparisons upstream
  // still see the raw uppercase value.
  function titleCase(s) {
    s = String(s || '');
    return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
  }

  function flipsHtml(rows) {
    if (!rows || !rows.length) return '';
    return rows.map(function (f) {
      return '<div style="display:flex; align-items:center; gap:3px; font-size:9px; line-height:1.55; margin-bottom:3px;">' +
        '<strong style="display:inline-block; width:38px; flex:0 0 auto; overflow:hidden;">' + symLink(f.symbol) + '</strong>' +
        '<span style="display:inline-block; width:46px; flex:0 0 auto; text-align:right; font-size:8px; font-weight:700; color:' + sideColor(f.from) + ';">' + esc(titleCase(f.from)) + '</span>' +
        '<span style="flex:0 0 auto; color:#ccc;">&rarr;</span>' +
        '<span style="display:inline-block; width:46px; flex:0 0 auto; font-size:8px; font-weight:700; color:' + sideColor(f.to) + ';">' + esc(titleCase(f.to)) + '</span>' +
        '</div>';
    }).join('');
  }

  function earlyLookHtml(el) {
    if (!el || !el.takeaways) return '';
    // Current parser joins takeaway paragraphs with "\n• "; older stored
    // notes instead used a bare bullet/replacement-char between items with no
    // newline. Split on either convention.
    var bullets = el.takeaways.split(/\n+\s*[•�]+\s*|[•�]+/).map(function (s) {
      return s.replace(/\s+/g, ' ').trim();
    }).filter(function (s) { return s.length > 10; });
    // A handful of older notes carry no bullet/replacement-char markers at
    // all — the "Key Takeaways" section arrives as one continuous paragraph.
    // Split that into one bullet per sentence so it still reads as a list.
    if (bullets.length <= 1) {
      var whole = (bullets[0] || el.takeaways).replace(/\s+/g, ' ').trim();
      var sentences = (whole.match(/[^.!?]+[.!?]+(?=\s|$)/g) || [whole])
        .map(function (s) { return s.trim(); })
        .filter(function (s) { return s.length > 10; });
      bullets = sentences.length ? sentences : [whole];
    }
    // No per-bullet truncation and no cap on bullet count — CARD_BODY scrolls
    // (overflow-y:auto), so showing everything relies on scroll, not cutoff.
    // Numbered "1) 2) 3) ..." instead of bullet points, all flowing in one
    // continuous inline span (2026-07-04) -- rendered via _inlineHdrCard, so
    // this text itself starts right where the card's title span ends (no
    // separate header row/indent needed here).
    return '<span style="font-size:11px; line-height:1.5;">' +
      bullets.map(function (b, i) {
        return '<span style="color:#534ab7; font-weight:700;">' + (i + 1) + ')</span> ' + esc(b);
      }).join(' ') +
      '</span>';
  }

  // "Hedgeye's Top 3 Things" from THE MACRO SHOW — note_text is 1-3 lines,
  // each pre-formatted by parse_macro_show_top3 as "N) LABEL – takeaway".
  function top3Html(t3) {
    if (!t3 || !t3.note_text) return '';
    var lines = t3.note_text.split(/\n+/).map(function (s) { return s.trim(); }).filter(Boolean);
    // All items flowing in one continuous inline span (2026-07-04, same
    // treatment as earlyLookHtml) -- "N)" numbering is already in the
    // source text (parse_macro_show_top3), kept as-is. Rendered via
    // _inlineHdrCard, so this text starts right where the card's title
    // span ends.
    return '<span style="font-size:11px; line-height:1.5;">' +
      lines.map(function (line) {
        var m = line.match(/^(\d\)\s*[^–—-]+?)\s*([–—-])\s*(.+)$/);
        var head = m ? m[1] : '';
        var body = m ? m[3] : line;
        return (head ? '<strong style="color:#534ab7;">' + esc(head) + '</strong> – ' : '') +
          boldTickers(body);
      }).join(' ') +
      '</span>';
  }

  // Click-to-enlarge overlay, shared by any panel image (built lazily, reused
  // across calls). Exposed on window since inline onclick="" runs outside
  // this IIFE's closure.
  function _showImagePopup(url) {
    var modal = document.getElementById('heImgModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'heImgModal';
      modal.style.cssText = 'display:none; position:fixed; inset:0; z-index:2000; ' +
        'background:rgba(15,15,20,0.82); cursor:zoom-out; align-items:center; justify-content:center;';
      modal.innerHTML = '<img id="heImgModalImg" style="max-width:92vw; max-height:92vh; ' +
        'border-radius:6px; box-shadow:0 8px 40px rgba(0,0,0,0.5);">';
      modal.addEventListener('click', function () { modal.style.display = 'none'; });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') modal.style.display = 'none';
      });
      document.body.appendChild(modal);
    }
    document.getElementById('heImgModalImg').src = url;
    modal.style.display = 'flex';
  }
  window._heShowImagePopup = _showImagePopup;

  // 2026-08-10 -- moved out of the purple Hedgeye card grid into its own
  // standalone .cockpit-band section (#heMktSituationPanel, just below Risk
  // Dial in index.html's left column) -- no nested white/shadow box of its
  // own anymore, the parent section already supplies that chrome, so this
  // only fills it. Image now stretches to the section's full content width
  // (width:100%, height:auto) instead of capping at a small fixed pixel
  // height, so it matches Risk Dial's column width above it instead of
  // sitting at some arbitrary smaller size. User: "adjust the width and
  // height of Mkt situation graph so it matches with risk dial width.
  // don't make it odd."
  function msrCardHtml(msr, loadedAt) {
    var msrMetricsHtml = '';
    if (msr) {
      var metricParts = [];
      var _metricLabel = function (label, val) {
        var color = val >= 0 ? '#1d9e75' : '#d4537e';
        return '<span style="text-transform:none;">' + label + '</span> ' +
          '<strong style="color:' + color + '; font-size:11px;">' + esc(val.toFixed(2)) + '</strong>';
      };
      if (msr.gamma_throttle != null)
        metricParts.push(_metricLabel('Gamma Throttle', msr.gamma_throttle));
      if (msr.rvol_10day != null)
        metricParts.push(_metricLabel('Realized Vol', msr.rvol_10day));
      if (metricParts.length) {
        msrMetricsHtml = ' <span style="font-size:8px; color:#888; font-weight:400;">&middot; ' +
          metricParts.join(' &middot; ') + '</span>';
      }
    }
    var img = (msr && msr.image_url)
      ? (function () {
          var titleHtml = 'Market Situation Report' + (msr.date ? ' &middot; ' + esc(msr.date) : '');
          var bodyParts = [];
          if (msr.received_at) bodyParts.push('Received: ' + fmtRecv(msr.received_at));
          if (msr.gamma_throttle != null) bodyParts.push('Gamma Throttle: ' + msr.gamma_throttle.toFixed(2));
          if (msr.rvol_10day != null) bodyParts.push('Realized Vol: ' + msr.rvol_10day.toFixed(2));
          var idx = _richTip(_popBox(titleHtml, bodyParts.join('\n')));
          // width:100% (not max-width/auto) -- deliberately stretches to
          // fill the section's full content width, matching its
          // .cockpit-band siblings (Risk Dial etc.) in the same column.
          // height:auto preserves the image's own aspect ratio, so it just
          // scales proportionally rather than being cropped or distorted.
          return '<img src="' + esc(msr.image_url) + '" ' +
            'style="width:100%; height:auto; border-radius:4px; display:block; cursor:zoom-in;" ' +
            'data-hetip="' + idx + '" ' +
            'onclick="window._heShowImagePopup(\'' + esc(msr.image_url) + '\')" ' +
            'onerror="this.style.display=\'none\'">';
        })()
      : '<span style="color:#bbb; font-size:10px;">none</span>';
    var msrLabel = (msr && msr.received_at) ? fmtRecv(msr.received_at)
                 : (msr && msr.date)        ? fmtMD(msr.date) : '';
    var msrTileTs = msrLabel
      ? ' <span style="font-size:8px; color:#bbb; font-weight:400;">· ' + esc(msrLabel) + '</span>'
      : '';
    var panelTitle = '<div style="font-weight:700; font-size:9px; text-transform:uppercase; ' +
      'letter-spacing:0.6px; color:#534ab7; margin-bottom:6px; display:flex; ' +
      'align-items:baseline; justify-content:space-between; gap:8px;">' +
      '<span>' + linked('Mkt Situation', 'mkt_situation') + msrTileTs +
      (loadedAt ? ' <span style="color:#bbb; font-weight:400; font-size:8px;">· ' + esc(loadedAt) + '</span>' : '') +
      '</span>' +
      '<span>' + msrMetricsHtml + '</span>' +
      '</div>';
    return panelTitle + img;
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
          var titleHtml = etf.date
            ? esc(etf.date) + ' &middot; etf_changes &middot; ' + esc(c.sym)
            : esc(c.sym);
          var t = c.desc ? ' data-hetip="' + _richTip(_popBox(titleHtml, c.desc)) + '"' : '';
          return '<span' + t + ' style="color:' + sc + ';">' + symLink(c.sym) + '</span>';
        }).join(' ') + '</div>';
    };
    return line('ADD', adds, '#1d9e75') + line('REM', removes, '#c0392b');
  }

  function iiChangesHtml(ii) {
    if (!ii || !ii.changes || !ii.changes.length) return '';
    var adds = ii.changes.filter(function (c) { return c.action === 'add'; });
    var removes = ii.changes.filter(function (c) { return c.action === 'remove'; });
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

  // 2026-08-10 -- width:100%/height:auto (was max-height:96px/width:auto)
  // so the image fills the right-rail column's full width, same fix
  // msrCardHtml() got for Mkt Situation's column -- height follows
  // proportionally at the image's own aspect ratio, no separate height
  // logic needed. User: "adjust the graph size to width of the whole
  // column and thus height of the graph (with current ratio)." Sole
  // caller is #heInflPanel (see render()); the old Actionable INFL slot
  // was replaced by Risk Range.
  function inflationNowcastHtml(infl) {
    if (!infl || !infl.image_url) return '';
    return '<img src="' + esc(infl.image_url) + '" ' +
      'style="width:100%; height:auto; border-radius:3px; display:block; cursor:zoom-in;" ' +
      'onclick="window._heShowImagePopup(\'' + esc(infl.image_url) + '\')" ' +
      'onerror="this.style.display=\'none\'">';
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
      var body = p.commentary || p.modifier || '';
      var titleHtml = pos.date
        ? esc(pos.date) + ' &middot; the_call_commentary &middot; ' + esc(p.sym)
        : esc(p.sym);
      var t = body ? ' data-hetip="' + _richTip(_popBox(titleHtml, body)) + '"' : '';
      return p.best
        ? '<strong' + t + ' style="color:' + color + ';">' + s + '*</strong>'
        : '<span' + t + ' style="color:' + color + ';">' + s + '</span>';
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
        n.map(function (p) { return symHtml(p, '#999'); }).join(' ') + '</div>'
      : '';
    return line('L', pos.longs, '#1d9e75') +
           line('S', pos.shorts, '#d4537e') +
           neutralLine;
  }

  function stanceHtml(stance, stanceDate) {
    stance = stance || {};
    var bull = (stance.bullish || []);
    var bear = (stance.bearish || []);
    if (!bull.length && !bear.length) return '';
    var line = function (label, arr, color) {
      if (!arr.length) return '';
      var shown = arr.slice(0, 12);
      return '<div style="font-size:10px; line-height:1.7;">' +
        '<span style="font-weight:700; color:' + color + '; font-size:9px;">' +
        label + '(' + arr.length + ')</span> ' +
        shown.map(function (p) {
          var titleHtml = stanceDate
            ? esc(stanceDate) + ' &middot; macro_show &middot; ' + esc(p.sym || '')
            : esc(p.sym || '');
          var t = p.label ? ' data-hetip="' + _richTip(_popBox(titleHtml, p.label)) + '"' : '';
          return '<span' + t + '>' + esc(p.sym || '') + '</span>';
        }).join(' ') + (arr.length > 12 ? ' …' : '') + '</div>';
    };
    return line('L', bull, '#1d9e75') + line('S', bear, '#d4537e');
  }

  function render(data, loadedAt) {
    // 2026-08-10 -- four independent targets from one shared fetch:
    // #hedgeyePanel (Actionable, unchanged element), #heMktSituationPanel
    // (Dashboard left column, below Risk Dial), #heInflPanel (Dashboard
    // right rail, above the Indicator grid), #hedgeyeDashPanel (Dashboard
    // center column -- Early Look/Macro Commentary/Top 3 Things only, Mkt
    // Situation and INFL split out of it). Any subset may be present in the
    // DOM depending on which page loaded this script. User: "move the mkt
    // situation panel to just below risk dial panel and INFL to 3rd column
    // above Indicator grid."
    var actEl = document.getElementById('hedgeyePanel');
    var dashEl = document.getElementById('hedgeyeDashPanel');
    // 2026-08-10 -- innerHTML now targets this inner wrapper, not dashEl
    // itself -- dashEl's own display:block/none (data-presence) and the
    // Hedgeye collapse toggle's display on this inner div (user-collapse)
    // would otherwise fight over the same style.display. See
    // web/hedgeye_collapse.js.
    var dashBodyEl = document.getElementById('hedgeyeDashPanelBody');
    var mktPanelEl = document.getElementById('heMktSituationPanel');
    var mktBodyEl = document.getElementById('heMktSituationBody');
    var inflPanelEl = document.getElementById('heInflPanel');
    var inflBodyEl = document.getElementById('heInflBody');
    if (!actEl && !dashEl && !mktPanelEl && !inflPanelEl) return;
    _tipHtml = [];  // reset so data-hetip indices match this render's DOM

    var hasMktAny = !!data.msr;
    var hasInflAny = !!(data.inflation_nowcast && data.inflation_nowcast.image_url);
    var hasDashAny = !!(
      (data.early_look && data.early_look.takeaways) ||
      (data.call_macro && data.call_macro.note_text) ||
      (data.top3_things && data.top3_things.note_text));
    var hasActAny = !!((data.top5 && data.top5.length) ||
      (data.alerts && data.alerts.length) ||
      (data.trend_flips && data.trend_flips.length) ||
      (data.stance && ((data.stance.bullish || []).length || (data.stance.bearish || []).length)) ||
      (data.positions && (data.positions.longs.length || data.positions.shorts.length)) ||
      (data.etf_changes && data.etf_changes.changes && data.etf_changes.changes.length) ||
      (data.ii_changes && data.ii_changes.changes && data.ii_changes.changes.length) ||
      (data.sss_changes && data.sss_changes.changes && data.sss_changes.changes.length));

    if (dashEl && !hasDashAny) dashEl.style.display = 'none';
    if (actEl && !hasActAny) actEl.style.display = 'none';
    if (mktPanelEl && !hasMktAny) mktPanelEl.style.display = 'none';
    if (inflPanelEl && !hasInflAny) inflPanelEl.style.display = 'none';
    if (!hasDashAny && !hasActAny && !hasMktAny && !hasInflAny) return;

    var collapsed = localStorage.getItem('hePanel_collapsed') === '1';
    var etfTitle = 'ETF CHG';
    var iiTitle = 'II CHG';
    var sssTitle = 'SSS CHG';

    // Show email received time (mm/dd H:MM AM/PM) when available, else date only (mm/dd).
    var td = function (receivedAt, dateIso) {
      var label = receivedAt ? fmtRecv(receivedAt) : (dateIso ? fmtMD(dateIso) : '');
      return label ? ' <span style="font-size:8px; color:#bbb; font-weight:400;">' + esc(label) + '</span>' : '';
    };

    // Card chrome shared by every row via _card(). Sizing (width) now comes
    // entirely from each row's CSS-grid grid-template-columns — cards never
    // set their own width/flex-basis, so a narrower window or an added card
    // just changes the grid track math, nothing hand-tuned per card.
    var CARD_BASE = 'background:#fff; border:1px solid #e0daf5; border-radius:5px; ' +
      'padding:7px 10px; min-width:0; box-shadow:0 1px 4px rgba(83,74,183,0.07); ' +
      'display:flex; flex-direction:column;';
    var CARD_HDR = 'font-weight:700; font-size:8.5px; text-transform:uppercase; ' +
      'letter-spacing:0.55px; color:#534ab7; padding-bottom:4px; margin-bottom:4px; ' +
      'border-bottom:1px solid #edeafb; flex-shrink:0;';
    var CARD_BODY = 'overflow-y:auto; flex:1; min-height:0;';

    // Cards size to content, capped at maxH (default 125, rowMacroTop3 uses
    // 105) with internal scroll past that — never a fixed row height, so a
    // row with only short content doesn't force every sibling to stretch to
    // an arbitrary pixel number.
    var _card = function (title, body, dateHtml, opts) {
      opts = opts || {};
      var maxH = opts.maxH || 126;
      var extra = opts.extra || '';
      return '<div style="' + CARD_BASE + 'max-height:' + maxH + 'px;' + extra + '">' +
        '<div style="' + CARD_HDR + '">' + title + (dateHtml || '') + '</div>' +
        '<div style="' + CARD_BODY + '">' +
        (body || '<span style="color:#bbb; font-size:10px;">none</span>') +
        '</div></div>';
    };

    // Variant of _card (2026-07-04, Early Look / Top 3 Things): no separate
    // header bar -- title, date, and body all share one flowing block
    // instead of the header's row going mostly empty above a body that
    // starts fresh below it. Date sits right after the title (its original
    // position in the old header bar), then a fixed gap, then the body text
    // begins on the same line, reclaiming the space that would otherwise
    // sit empty next to a short title+date.
    var _inlineHdrCard = function (title, body, dateHtml, opts) {
      opts = opts || {};
      var maxH = opts.maxH || 125;
      var extra = opts.extra || '';
      var titleStyle = 'font-weight:700; font-size:8.5px; text-transform:uppercase; ' +
        'letter-spacing:0.55px; color:#534ab7;';
      // Same CARD_BASE as every other card, but padding trimmed to match --
      // no separate header row/divider here means less vertical space is
      // needed before content starts than the other cards use. Top padding
      // cut further than bottom/sides since there's no header row above the
      // text to justify the same top gap the other cards have.
      return '<div style="' + CARD_BASE + 'max-height:' + maxH + 'px; padding:2px 8px 5px 8px;' + extra + '">' +
        '<div style="' + CARD_BODY + '">' +
        '<span style="' + titleStyle + '">' + title + '</span>' +
        (dateHtml || '') +
        '<span style="display:inline-block; width:6px;"></span>' +
        (body || '<span style="color:#bbb; font-size:10px;">none</span>') +
        '</div></div>';
    };

    var _inflValueHtml = '';
    var _inflMonth = '';
    if (data.inflation_nowcast) {
      var _infl = data.inflation_nowcast;
      if (_infl.date) {
        var _monAbbr = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        var _inflD = new Date(_infl.date + 'T00:00:00');
        if (!isNaN(_inflD.getTime())) _inflMonth = _monAbbr[_inflD.getMonth()];
      }
      if (_infl.value != null) {
        var _valParts = esc(_infl.value.toFixed(2)) + '%' +
          '<span style="font-size:8px; font-weight:400;"> y/y</span>';
        if (_infl.seq_bp != null) {
          _valParts += ' <span style="font-size:8px; font-weight:400;">' +
            esc(_infl.seq_bp.toFixed(1)) + ' bp</span>';
        }
        _inflValueHtml = ' <strong style="color:#534ab7;">' + _valParts + '</strong>';
      }
    }
    var _inflDateHtml = data.inflation_nowcast
      ? td(data.inflation_nowcast.received_at, data.inflation_nowcast.date) : '';
    var _inflRight = (_inflMonth ? '<span style="text-transform:none; color:#888;">' + esc(_inflMonth) + '</span>' : '') +
      _inflValueHtml;
    var _inflTitle = '<span style="display:flex; justify-content:space-between; align-items:baseline; width:100%;">' +
      '<span>' + linked('INFL', 'inflation_nowcast') + _inflDateHtml + '</span>' +
      '<span>' + _inflRight + '</span>' +
      '</span>';

    // ---- Mkt Situation panel (index.html #heMktSituationPanel, left column
    // just below Risk Dial) -- 2026-08-10, per user: "move the mkt situation
    // panel to just below risk dial panel." Plain .cockpit-band section (see
    // index.html) supplies the card chrome; msrCardHtml() just fills it --
    // see its own comment for the width/height fix.
    if (mktPanelEl) {
      if (hasMktAny) {
        if (mktBodyEl) mktBodyEl.innerHTML = msrCardHtml(data.msr, loadedAt);
        mktPanelEl.style.display = 'block';
      } else {
        mktPanelEl.style.display = 'none';
      }
    }

    // ---- INFL panel (index.html #heInflPanel, right rail above the
    // Indicator grid) -- 2026-08-10, per user: "INFL to 3rd column above
    // Indicator grid." Same plain-section treatment as Mkt Situation above.
    if (inflPanelEl) {
      if (hasInflAny) {
        if (inflBodyEl) {
          inflBodyEl.innerHTML =
            '<div style="font-weight:700; font-size:9px; text-transform:uppercase; ' +
            'letter-spacing:0.6px; color:#534ab7; margin-bottom:6px;">' + _inflTitle + '</div>' +
            inflationNowcastHtml(data.inflation_nowcast);
        }
        inflPanelEl.style.display = 'block';
      } else {
        inflPanelEl.style.display = 'none';
      }
    }

    // ---- Dashboard center panel (index.html #hedgeyeDashPanel) -- Early
    // Look / Macro Commentary / Hedgeye's Top 3 Things stacked full-width.
    // Mkt Situation and INFL split out into their own panels above
    // (2026-08-10) -- this container now holds only the three prose/list
    // cards that don't have a more specific home elsewhere on the
    // dashboard. User: "move HE earylook, macro commentory, hedgeye top 3
    // things ... from actionable screen to Dashboard screen."
    if (dashEl) {
      if (hasDashAny) {
        var dashRowEarly =
          _inlineHdrCard(linked('Early Look', 'early_look'),
                data.early_look ? earlyLookHtml(data.early_look) : '',
                td(data.early_look && data.early_look.received_at, data.early_look && data.early_look.date),
                { maxH: 150 });
        var dashRowMacro = '<div style="margin-top:3px;">' +
          _inlineHdrCard(linked('Macro Commentary', 'call_macro'),
                data.call_macro ? '<span style="font-size:11px; line-height:1.5;">' + boldTickers(data.call_macro.note_text) + '</span>' : '',
                td(data.call_macro && data.call_macro.received_at, data.call_macro && data.call_macro.date),
                { maxH: 150 }) +
          '</div>';
        var dashRowTop3 = '<div style="margin-top:3px;">' +
          _inlineHdrCard(linked("Hedgeye's Top 3 Things", 'macro_show'), top3Html(data.top3_things),
                td(data.top3_things && data.top3_things.received_at, data.top3_things && data.top3_things.date),
                { maxH: 150 }) +
          '</div>';

        if (dashBodyEl) dashBodyEl.innerHTML =
          '<div style="padding:2px 4px; background:#f0eefb; border:1px solid #d5d0f0; ' +
          'border-radius:6px;">' + dashRowEarly + dashRowMacro + dashRowTop3 + '</div>';
        dashEl.style.display = 'block';
      } else {
        dashEl.style.display = 'none';
      }
    }

    // ---- Actionable panel (#hedgeyePanel): Top-5 | Macro Show | RTA | ETF
    // | II | SSS | Call | Risk Range. Risk Range moved into INFL's old last
    // column 2026-08-10 (INFL itself moved to the Dashboard panel above) --
    // same track width (minmax(150px,210px)) INFL used to occupy, per user:
    // "move the risk range in actionable screen to where INFL panel was
    // there currently."
    if (actEl) {
      if (hasActAny) {
        var GRID_ROW2 = 'display:grid; grid-template-columns: ' +
          'minmax(120px, calc(15ch + 20px)) minmax(200px, 1fr) minmax(220px, calc(35ch + 20px)) ' +
          'minmax(120px, calc(15ch + 20px)) minmax(120px, calc(15ch + 20px)) minmax(120px, calc(15ch + 20px)) ' +
          'minmax(200px, 1fr) minmax(150px, 210px); gap:3px; align-items:stretch;';
        var row2 =
          '<div style="' + GRID_ROW2 + '">' +
          _card(linked('Top-5', 'top5'),                 top5Html(data.top5),              td(data.top5_received_at, data.top5_date)) +
          _card(linked('Macro Show', 'macro_show'),      stanceHtml(data.stance, data.stance_date), td(data.stance_received_at, data.stance_date)) +
          _card(linked('RTA', 'alerts'),                 alertsHtml(data.alerts),          td(data.rta_received_at, data.rta_date)) +
          _card(linked(etfTitle, 'etf_pro'),             etfChangesHtml(data.etf_changes), td(data.etf_changes && data.etf_changes.received_at, data.etf_changes && data.etf_changes.date)) +
          _card(linked(iiTitle, 'investing_ideas'),      iiChangesHtml(data.ii_changes),   td(data.ii_changes && data.ii_changes.received_at, data.ii_changes && data.ii_changes.date)) +
          _card(linked(sssTitle, 'sss'),                 sssChangesHtml(data.sss_changes), td(data.sss_changes && data.sss_changes.received_at, data.sss_changes && data.sss_changes.date)) +
          _card(linked('Call', 'call'),                  positionsHtml(data.positions),    td(data.positions && data.positions.received_at, data.positions && data.positions.date)) +
          _card(linked('Risk Range', 'trend_change'),    flipsHtml(data.trend_flips),      td(data.trend_flips_received_at, data.trend_flips_date)) +
          '</div>';

        var bodyHtml =
          '<div id="hePanelBody" style="display:' + (collapsed ? 'none' : 'block') + '; margin-top:2px;">' +
          row2 + '</div>';

        actEl.innerHTML =
          '<div style="padding:2px 4px; background:#f0eefb; border:1px solid #d5d0f0; ' +
          'border-radius:6px;">' + bodyHtml + '</div>';
        actEl.style.display = 'block';

        // U15: sync the toggle button's chevron to the persisted collapsed
        // state on every render (covers page reload — clicking already syncs
        // this via _hePanelToggle below, but that only runs on click).
        var toggleBtn = document.getElementById('hePanelToggle');
        if (toggleBtn) {
          toggleBtn.classList.toggle('icon-on', !collapsed);
          toggleBtn.classList.toggle('icon-off', collapsed);
        }
      } else {
        actEl.style.display = 'none';
      }
    }

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
      ['hedgeyePanel', 'hedgeyeDashPanel', 'heMktSituationPanel', 'heInflPanel'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
      });
    }
  }

  // Poll /api/hedgeye/fetch-status for new emails and auto-refresh the panel
  // when one lands, instead of waiting for a manual Refresh click.
  var _lastEmailSignal = null;

  function _emailSignal(status) {
    var latest = '';
    (status.today_by_type || []).forEach(function (t) {
      if (t.latest && t.latest > latest) latest = t.latest;
    });
    return status.today_total + '|' + latest;
  }

  async function checkForNewEmail() {
    try {
      var status = await fetchJson('/api/hedgeye/fetch-status');
      var sig = _emailSignal(status);
      if (_lastEmailSignal !== null && sig !== _lastEmailSignal) load();
      _lastEmailSignal = sig;
    } catch (e) { /* non-critical, ignore */ }
  }

  // Rich tooltips: delegated hover on the panel, reusing actionable.js's
  // #sourcePop/_showDataPop/hideSourcePop globals (see _richTip/_popBox
  // above). Only actionable.html loads actionable.js, so on the Dashboard
  // (#hedgeyeDashPanel only, no _showDataPop global) this is a no-op --
  // guarded per-panel rather than bailing out entirely if only one target
  // exists.
  function _wireRichTips() {
    if (typeof _showDataPop !== 'function') return;
    ['hedgeyePanel', 'hedgeyeDashPanel', 'heMktSituationPanel', 'heInflPanel'].forEach(function (id) {
      var panel = document.getElementById(id);
      if (!panel) return;
      panel.addEventListener('mouseover', function (e) {
        var el = e.target.closest('[data-hetip]');
        if (el) _showDataPop(el, _tipHtml[+el.getAttribute('data-hetip')] || '');
      });
      panel.addEventListener('mouseout', function (e) {
        if (e.relatedTarget && e.relatedTarget.closest('[data-hetip]')) return;
        if (typeof hideSourcePop === 'function') hideSourcePop();
      });
    });
  }

  function init() {
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 600);
    setTimeout(checkForNewEmail, 1000);
    setInterval(checkForNewEmail, 30000);
    _wireRichTips();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
