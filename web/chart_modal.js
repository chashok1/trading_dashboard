// Shared TradingView chart popup modal
// Usage: openChartModal(sym, {description, price, pctChange, badgeHtml})
// Closes on overlay click, X button, or Escape key.

(function () {
  var TV_MAP = {
    'SPX':   'SP:SPX',       '$SPX':  'SP:SPX',
    '$COMP': 'NASDAQ:NDX',   'COMP':  'NASDAQ:NDX', 'COMPQ': 'NASDAQ:NDX',
    '$DJI':  'DJ:DJI',       'DJI':   'DJ:DJI',     'INDU':  'DJ:DJI',
    'RUT':   'TVC:RUT',      'VIX':   'TVC:VIX',    'VXN':   'TVC:VXN',
    'VXD':   'TVC:VXD',      'RVX':   'TVC:RVX',    'OVX':   'TVC:OVX',
    'GVZ':   'TVC:GVZ',      'MOVE':  'TVC:MOVE',
    'DXY':   'TVC:DXY',      '$DXY':  'TVC:DXY',
    '/CL':   'TVC:USOIL',    '/GC':   'TVC:GOLD',
    '/ES':   'SP:SPX',       '/NQ':   'NASDAQ:NDX',  '/RTY':  'TVC:RUT',
  };

  function toTvSym(sym) {
    if (!sym) return '';
    if (TV_MAP[sym]) return TV_MAP[sym];
    if (sym.startsWith('$')) return sym.slice(1);
    if (sym.startsWith('/')) return sym.slice(1) + '1!';
    return sym;
  }

  var MODAL_ID = 'symChartModal';

  function _ensure() {
    if (document.getElementById(MODAL_ID)) return;
    var el = document.createElement('div');
    el.id        = MODAL_ID;
    el.className = 'sym-chart-modal';
    el.setAttribute('aria-modal', 'true');
    el.setAttribute('role', 'dialog');
    el.style.display = 'none';
    el.innerHTML = [
      '<div class="scm-overlay" id="scmOverlay"></div>',
      '<div class="scm-dialog">',
      '  <div class="scm-header">',
      '    <span class="scm-sym"   id="scmSym"></span>',
      '    <span id="scmYahoo"></span>',
      '    <span class="scm-desc"  id="scmDesc"></span>',
      '    <span id="scmBadge"></span>',
      '    <span class="scm-price" id="scmPrice"></span>',
      '    <span class="scm-chg"   id="scmChg"></span>',
      '    <button class="scm-close" id="scmClose" aria-label="Close">&#x2715;</button>',
      '  </div>',
      '  <div class="scm-body" id="scmBody"></div>',
      '</div>',
    ].join('');
    document.body.appendChild(el);
    document.getElementById('scmClose').addEventListener('click', window.closeChartModal);
    document.getElementById('scmOverlay').addEventListener('click', window.closeChartModal);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') window.closeChartModal();
    });
  }

  // Own candle chart above the TradingView one (2026-10-22, user: match the ThinkOrSwim look): dark candles, TRR (cyan) /
  // LRR (blue) bands day by day, dotted Trade / Trend lines at today's level, price tags on the right edge.
  var C_UP = '#22c55e', C_DN = '#f87171', C_TRR = '#22d3ee', C_LRR = '#2f3cff', C_TRADE = '#fbbf24', C_TREND = '#e879f9', C_GRID = '#3a3a3a';

  // Smooth path (Catmull-Rom -> cubic Bezier, light tension) per unbroken run of values; a missing day breaks the line.
  function _bandPath(pts, at, xOf, yOf) {
    var runs = [], cur = [];
    pts.forEach(function (p, i) {
      var v = at(p, i);
      if (v == null) { if (cur.length) runs.push(cur); cur = []; return; }
      cur.push([xOf(i), yOf(v)]);
    });
    if (cur.length) runs.push(cur);
    var T = 0.5 / 3, d = '';
    runs.forEach(function (r) {
      d += 'M' + r[0][0].toFixed(1) + ' ' + r[0][1].toFixed(1);
      for (var k = 0; k < r.length - 1; k++) {
        var p0 = r[k - 1] || r[k], p1 = r[k], p2 = r[k + 1], p3 = r[k + 2] || r[k + 1];
        d += 'C' + (p1[0] + (p2[0] - p0[0]) * T).toFixed(1) + ' ' + (p1[1] + (p2[1] - p0[1]) * T).toFixed(1) + ','
          + (p2[0] - (p3[0] - p1[0]) * T).toFixed(1) + ' ' + (p2[1] - (p3[1] - p1[1]) * T).toFixed(1) + ','
          + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
      }
    });
    return d;
  }

  function _ownLine(pts, key, xOf, yOf, color, w) {
    var d = _bandPath(pts, function (p) { return p[key]; }, xOf, yOf);
    return d ? '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="' + w + '"/>' : '';
  }

  function _evKind(a) { return /^(ADD|INCREASE)$/.test(a) ? 'up' : /^(REMOVE|REDUCE)$/.test(a) ? 'dn' : 'hold'; }
  function _esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  function _drawOwn(el, pts, events) {
    var W = Math.max(el.clientWidth, 400), H = el.clientHeight || Math.round(W * 366 / 2004);
    var PL = 6, PR = 62, PT = 22, PB = (events && events.length) ? 54 : 16, n = pts.length;
    var last = function (k) { for (var i = n - 1; i >= 0; i--) if (pts[i][k] != null) return pts[i][k]; return null; };
    var trade = last('trade'), trend = last('trend'), lrr = last('lrr'), trr = last('trr'), px = last('price');
    var vals = [];
    pts.forEach(function (p) { ['high', 'low', 'price', 'lrr', 'trr'].forEach(function (k) { if (p[k] != null) vals.push(p[k]); }); });
    [trade, trend].forEach(function (v) { if (v != null) vals.push(v); });
    var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals), pad = ((mx - mn) || 1) * 0.05;
    mn -= pad; mx += pad;
    var pw = W - PL - PR, ph = H - PT - PB, slot = pw / (n + 12), /* 12 empty bar slots after the last day */ bw = Math.max(1.5, Math.min(9, slot * 0.6));
    var xOf = function (i) { return PL + slot * (i + 0.5); };
    var yOf = function (v) { return PT + (mx - v) / (mx - mn) * ph; };
    var f = function (v) { return Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2); };
    var g = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" style="display:block;background:#1b1b1b;font-family:Arial,sans-serif;">';
    for (var t = 0; t <= 5; t++) {
      var v = mn + (mx - mn) * t / 5, y = yOf(v);
      g += '<line x1="' + PL + '" x2="' + (W - PR) + '" y1="' + y + '" y2="' + y + '" stroke="' + C_GRID + '" stroke-dasharray="1 3"/>'
        + '<text x="' + (W - PR + 5) + '" y="' + (y + 3) + '" font-size="10" fill="#cbd5e1">' + f(v) + '</text>';
    }
    var step = Math.max(1, Math.ceil(46 / slot));
    for (var i = 0; i < n; i += step) {
      var dt = pts[i].date, x = xOf(i);
      g += '<line x1="' + x + '" x2="' + x + '" y1="' + PT + '" y2="' + (H - PB) + '" stroke="' + C_GRID + '" stroke-dasharray="1 3"/>'
        + '<text x="' + x + '" y="' + (H - 4) + '" font-size="9" fill="#9ca3af" text-anchor="middle">' + dt.slice(5, 7) + '/' + dt.slice(8, 10) + '</text>';
    }
    // Source-action lane: one small triangle per date where a source's action changed (up = ADD/INCREASE, down = REMOVE/REDUCE, dot = HOLD).
    // Details show on hover so the chart itself stays clean.
    var evAt = {}, laneY = H - 30;
    if (events && events.length) {
      var idxOf = {}; pts.forEach(function (p, i) { idxOf[p.date] = i; });
      events.forEach(function (e) {
        var i = idxOf[e.date];
        if (i == null) { for (var j = 0; j < n; j++) if (pts[j].date >= e.date) { i = j; break; } }
        if (i == null) return;
        (evAt[i] = evAt[i] || []).push(e);
      });
      g += '<line x1="' + PL + '" x2="' + (W - PR) + '" y1="' + (laneY - 15) + '" y2="' + (laneY - 15) + '" stroke="' + C_GRID + '"/>';
      Object.keys(evAt).forEach(function (k) {
        var x = xOf(+k), kinds = {};
        evAt[k].forEach(function (e) { kinds[_evKind(e.action)] = 1; });
        var ks = Object.keys(kinds), off = (ks.length - 1) * -6;
        ks.forEach(function (kd, m) {
          var cx = x + off + m * 12, c = kd === 'up' ? C_UP : kd === 'dn' ? C_DN : '#9ca3af';
          g += kd === 'up' ? '<path d="M' + cx + ' ' + (laneY - 5) + 'l-5 10h10z" fill="' + c + '"/>'
            : kd === 'dn' ? '<path d="M' + cx + ' ' + (laneY + 5) + 'l-5 -10h10z" fill="' + c + '"/>'
            : '<circle cx="' + cx + '" cy="' + laneY + '" r="3.5" fill="' + c + '"/>';
        });
      });
    }
    [[trade, C_TRADE], [trend, C_TREND]].forEach(function (l) {
      if (l[0] == null) return;
      g += '<line x1="' + PL + '" x2="' + (W - PR) + '" y1="' + yOf(l[0]) + '" y2="' + yOf(l[0]) + '" stroke="' + l[1] + '" stroke-width="1.5" stroke-dasharray="1.5 4" stroke-linecap="round"/>';
    });
    g += _ownLine(pts, 'trr', xOf, yOf, C_TRR, 1.8) + _ownLine(pts, 'lrr', xOf, yOf, C_LRR, 1.8);
    pts.forEach(function (p, i) {
      if (p.price == null) return;
      var o = p.open != null ? p.open : p.price, h = p.high != null ? p.high : Math.max(o, p.price), lo = p.low != null ? p.low : Math.min(o, p.price);
      var up = p.price >= o, c = up ? C_UP : C_DN, x = xOf(i), yt = yOf(Math.max(o, p.price)), yb = yOf(Math.min(o, p.price));
      g += '<line x1="' + x + '" x2="' + x + '" y1="' + yOf(h) + '" y2="' + yOf(lo) + '" stroke="' + c + '"/>'
        + '<rect x="' + (x - bw / 2) + '" y="' + yt + '" width="' + bw + '" height="' + Math.max(1, yb - yt) + '" fill="' + (up ? '#1b1b1b' : c) + '" stroke="' + c + '"/>';
    });
    // Only the price tag is always on; TRR / LRR / Trade / Trend numbers appear on hover (see below).
    if (px != null) {
      var pc = pts[n - 1].open != null && px < pts[n - 1].open ? C_DN : C_UP, py = yOf(px);
      g += '<rect x="' + (W - PR + 1) + '" y="' + (py - 7) + '" width="' + (PR - 2) + '" height="14" fill="' + pc + '"/>'
        + '<text x="' + (W - PR + 4) + '" y="' + (py + 3.5) + '" font-size="10" font-weight="700" fill="#000">' + f(px) + '</text>';
    }
    // Hover (like TOS): the line nearest the cursor is highlighted and its number shows in a coloured box at the cursor.
    var hov = [
      { n: 'TRR', c: C_TRR, fg: '#000', now: trr, at: function (i) { return pts[i].trr; } },
      { n: 'LRR', c: C_LRR, fg: '#fff', now: lrr, at: function (i) { return pts[i].lrr; } },
      { n: 'Trade', c: C_TRADE, fg: '#000', now: trade, at: function () { return trade; } },
      { n: 'Trend', c: C_TREND, fg: '#000', now: trend, at: function () { return trend; } }
    ];
    var host = el.querySelector('.scm-own-svg') || el;
    host.innerHTML = g + '<g class="scm-hov" pointer-events="none"></g></svg>';
    var hg = host.querySelector('.scm-hov');
    host.onmousemove = function (e) {
      var r = host.getBoundingClientRect(), mx_ = e.clientX - r.left, my_ = e.clientY - r.top;
      var i = Math.max(0, Math.min(n - 1, Math.round((mx_ - PL) / slot - 0.5)));
      var best = null, bd = 7;
      hov.forEach(function (h) {
        var v = h.at(i);
        if (v == null || mx_ < PL || mx_ > W - PR) return;
        var d = Math.abs(yOf(v) - my_);
        if (d < bd) { bd = d; best = { h: h, v: v }; }
      });
      if (events && events.length && my_ > laneY - 14 && my_ < laneY + 14 && mx_ >= PL && mx_ <= W - PR) {   // source-action lane: details for the nearest marked date
        var near = null, nd = 12;
        Object.keys(evAt).forEach(function (k) { var d_ = Math.abs(xOf(+k) - mx_); if (d_ < nd) { nd = d_; near = +k; } });
        if (near == null) { hg.innerHTML = ''; host.style.cursor = ''; return; }
        host.style.cursor = 'default';
        var L = ['Source actions · ' + pts[near].date.slice(5, 7) + '/' + pts[near].date.slice(8, 10)].concat(evAt[near].map(function (e) {
          var why = e.reason ? ' — ' + (e.reason.length > 46 ? e.reason.slice(0, 45) + '…' : e.reason) : '';
          return '• ' + e.source + ' ' + e.action + why;
        }));
        var tw = Math.min(W - PL - 4, Math.max.apply(null, L.map(function (s) { return s.length; })) * 5.6 + 12), th = L.length * 13 + 6;
        var tx = Math.max(PL, Math.min(xOf(near) - tw / 2, W - PR - tw)), ty = laneY - 18 - th;
        hg.innerHTML = '<rect x="' + tx + '" y="' + ty + '" width="' + tw + '" height="' + th + '" rx="3" fill="#0f172a" stroke="#475569"/>'
          + L.map(function (s, q) { return '<text x="' + (tx + 6) + '" y="' + (ty + 13 + q * 13) + '" font-size="10" font-weight="' + (q ? 400 : 700) + '" fill="#e5e7eb">' + _esc(s) + '</text>'; }).join('');
        return;
      }
      if (!best) { hg.innerHTML = ''; host.style.cursor = ''; return; }
      host.style.cursor = 'pointer';
      best.v = best.h.now != null ? best.h.now : best.v;
      var y = yOf(best.v), isFlat = best.h.n === 'Trade' || best.h.n === 'Trend';
      var txt = best.h.n + ' ' + f(best.v), bx = W - PR - 84, by = Math.max(PT, y - 20);
      var s = '<line x1="' + PL + '" x2="' + (W - PR) + '" y1="' + y + '" y2="' + y + '" stroke="' + best.h.c + '" stroke-width="3" opacity="0.9"'
        + (isFlat ? ' stroke-dasharray="1.5 4" stroke-linecap="round"' : '') + '/>';
      if (!isFlat) {
        var pp = _bandPath(pts, function (p, j) { return best.h.at(j); }, xOf, yOf);
        s = '<path d="' + pp + '" fill="none" stroke="' + best.h.c + '" stroke-width="3.5"/>';
      }
      s += '<rect x="' + bx + '" y="' + by + '" width="78" height="16" rx="2" fill="' + best.h.c + '"/>'
        + '<text x="' + (bx + 5) + '" y="' + (by + 11.5) + '" font-size="11" font-weight="700" fill="' + best.h.fg + '">' + txt + '</text>'
        + '<rect x="' + (W - PR + 1) + '" y="' + (y - 7) + '" width="' + (PR - 2) + '" height="14" fill="' + best.h.c + '"/>'
        + '<text x="' + (W - PR + 4) + '" y="' + (y + 3.5) + '" font-size="10" font-weight="700" fill="' + best.h.fg + '">' + f(best.v) + '</text>';
      hg.innerHTML = s;
    };
    host.onmouseleave = function () { hg.innerHTML = ''; };
  }

  var _ownDays = 180;
  function _ownButtons(el, sym) {
    var b = el.querySelector('.scm-own-btns');
    if (!b) {
      b = document.createElement('div');
      b.className = 'scm-own-btns';
      b.style.cssText = 'position:absolute;top:2px;right:70px;display:flex;gap:4px;z-index:1;';
      b.innerHTML = [[90, '3M'], [180, '6M']].map(function (w) {
        return '<button type="button" data-days="' + w[0] + '" style="font-size:10px;padding:1px 7px;border-radius:3px;cursor:pointer;border:1px solid #4b5563;background:#1b1b1b;color:#cbd5e1;">' + w[1] + '</button>';
      }).join('');
      b.addEventListener('click', function (e) {
        var t = e.target.closest('button[data-days]');
        if (t) { _ownDays = Number(t.getAttribute('data-days')); _loadOwn(el, sym); }
      });
      el.appendChild(b);
    }
    Array.prototype.forEach.call(b.querySelectorAll('button'), function (x) {
      var on = Number(x.getAttribute('data-days')) === _ownDays;
      x.style.background = on ? '#22d3ee' : '#1b1b1b';
      x.style.color = on ? '#000' : '#cbd5e1';
    });
  }

  // el._tok: per-chart token, so the click popup and the Action popup can each have a chart without cancelling each other.
  // el.dataset.reserve: the host (Action popup) keeps the chart's height and shows a note when there is no history,
  // so the popup doesn't change size after it opens.
  async function _loadOwn(el, sym) {
    var tok = el._tok = (el._tok || 0) + 1;
    var note = function (t) {
      if (!el.dataset.reserve) return;
      var h = el.querySelector('.scm-own-svg') || el;
      h.innerHTML = '<div style="color:#94a3b8;font:11px Arial,sans-serif;padding:8px;">' + t + '</div>';
    };
    if (el.dataset.reserve) note('Loading chart...');
    try {
      var res = await fetch('/api/cockpit/rr-history?symbol=' + encodeURIComponent(sym) + '&days=' + _ownDays);
      if (!res.ok) { if (tok === el._tok) note('Chart not available.'); return; }
      var js = await res.json();
      var pts = (js.points || []).filter(function (p) { return p.price != null || p.lrr != null; });
      if (tok !== el._tok) return;
      if (pts.length < 5) { note('No range history stored for this symbol.'); return; }
      el.style.display = 'block';
      _ownButtons(el, sym);
      _drawOwn(el, pts, js.events || []);
    } catch (e) { if (tok === el._tok) note('Chart not available.'); /* click popup: the TradingView chart below still shows */ }
  }
  window.mountRrChart = function (el, sym) { if (el && sym) _loadOwn(el, sym); };

  // ── Studies panels (Action popup, right side): Volume / RSI / MACD / Volume ROC / IV, one shared date axis ──
  // Data: GET /api/actionable/studies (daily rows; MACD and Volume ROC calculated server-side). Plain SVG, TOS-like dark look.
  var SW = 800, SPL = 6, SPR = 54;
  function _sFmt(v, d) { return v == null ? '' : Number(v).toFixed(d == null ? 2 : d); }
  function _sVol(v) { return v == null ? '' : v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(0) + 'k' : String(Math.round(v)); }
  function _sPanel(pts, o) {
    var H = o.h, PT = 8, PB = o.axis ? 16 : 3, n = pts.length, iw = SW - SPL - SPR, slot = iw / n;
    var xOf = function (i) { return SPL + (i + 0.5) * slot; };
    var all = [];
    o.series.forEach(function (s) { if (s.nodraw) return; pts.forEach(function (p) { if (p[s.k] != null) all.push(p[s.k]); }); });
    (o.refs || []).forEach(function (r) { all.push(r); });
    if (o.zero) all.push(0);
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    if (o.floor0) lo = 0;
    if (!isFinite(lo) || hi === lo) { lo = (isFinite(lo) ? lo : 0) - 1; hi = lo + 2; }
    var pad = (hi - lo) * 0.06; if (!o.floor0) lo -= pad; hi += pad;
    var yOf = function (v) { return PT + (hi - v) / (hi - lo) * (H - PT - PB); };
    var g = '<rect width="' + SW + '" height="' + H + '" fill="#1b1b1b"/>';
    for (var q = 0; q < 5; q++) { var gy = PT + q * (H - PT - PB) / 4; g += '<line x1="' + SPL + '" x2="' + (SW - SPR) + '" y1="' + gy + '" y2="' + gy + '" stroke="#2a2a2a" stroke-dasharray="1 3"/>'; }
    (o.refs || []).forEach(function (r) { g += '<line x1="' + SPL + '" x2="' + (SW - SPR) + '" y1="' + yOf(r) + '" y2="' + yOf(r) + '" stroke="#d6c58a" stroke-width="1"/>'; });
    if (o.zero) g += '<line x1="' + SPL + '" x2="' + (SW - SPR) + '" y1="' + yOf(0) + '" y2="' + yOf(0) + '" stroke="' + (o.zeroColor || '#8b5a2b') + '"/>';
    o.series.forEach(function (s) {
      if (s.nodraw) return;
      if (s.bars) {
        var base = yOf(Math.max(lo, 0)), bw = Math.max(1, slot * 0.7);
        pts.forEach(function (p, i) {
          var v = p[s.k]; if (v == null) return;
          var col = s.signed ? (v >= 0 ? '#22c55e' : '#ef4444') : '#1f6f9f', y = yOf(v);
          g += '<rect x="' + (xOf(i) - bw / 2) + '" y="' + Math.min(y, base) + '" width="' + bw + '" height="' + Math.max(1, Math.abs(base - y)) + '" fill="' + col + '"/>';
        });
      } else {
        var d = '', on = false;
        pts.forEach(function (p, i) { var v = p[s.k]; if (v == null) { on = false; return; } d += (on ? 'L' : 'M') + xOf(i).toFixed(1) + ' ' + yOf(v).toFixed(1); on = true; });
        g += '<path d="' + d + '" fill="none" stroke="' + s.color + '" stroke-width="' + (s.w || 1.3) + '"/>';
      }
    });
    // Right-axis tag with the latest value of each line (the name + pointer values are in the strip above the panel).
    o.series.forEach(function (s) {
      var last = null; for (var i = n - 1; i >= 0; i--) { if (pts[i][s.k] != null) { last = pts[i][s.k]; break; } }
      if (s.nodraw || last == null || (s.bars && !s.tag)) return;
      g += '<rect x="' + (SW - SPR + 2) + '" y="' + (yOf(last) - 7) + '" width="' + (SPR - 4) + '" height="14" fill="' + (s.color || '#475569') + '"/>'
        + '<text x="' + (SW - SPR + 5) + '" y="' + (yOf(last) + 3.5) + '" font-size="10" font-weight="700" fill="#000">' + (s.fmt ? s.fmt(last) : _sFmt(last)) + '</text>';
    });
    if (o.axis) {
      var step = Math.max(1, Math.round(n / 9));
      for (var j = 0; j < n; j += step) g += '<text x="' + xOf(j) + '" y="' + (H - 3) + '" font-size="9" fill="#9ca3af" text-anchor="middle" font-family="Arial,sans-serif">' + Number(pts[j].date.slice(5, 7)) + '/' + Number(pts[j].date.slice(8, 10)) + '</text>';
    }
    g += '<line class="st-x" x1="-10" x2="-10" y1="0" y2="' + H + '" stroke="#9ca3af" stroke-dasharray="2 2"/>';
    return '<svg width="' + SW + '" height="' + H + '" viewBox="0 0 ' + SW + ' ' + H + '" style="display:block;" font-family="Arial,sans-serif">' + g + '</svg>';
  }
  // Values strip above each panel (like TOS): study name + the values at the pointer's date (latest day when the pointer is away).
  function _sHead(pts, o, i) {
    var p = pts[i], h = '<b style="color:#e5e7eb;">' + o.title + '</b>';
    o.series.forEach(function (s) {
      var v = p[s.k]; if (v == null) return;
      var col = s.signed ? (v >= 0 ? '#22c55e' : '#ef4444') : (s.hc || s.color || '#cbd5e1');
      h += ' <span style="color:' + col + ';">' + (s.fmt ? s.fmt(v) : _sFmt(v)) + '</span>';
    });
    (o.refs || []).forEach(function (r) { h += ' <span style="color:#d6c58a;">' + r + '</span>'; });
    return h + '<span style="float:right;color:#9ca3af;">' + p.date.slice(5, 7) + '/' + p.date.slice(8, 10) + '</span>';
  }
  var _SH = 'font:11px Arial,sans-serif;color:#9ca3af;background:#262626;padding:2px 6px;border-top:1px solid #3a3a3a;white-space:nowrap;overflow:hidden;';
  function _drawStudies(el, pts) {
    var f1 = function (v) { return _sFmt(v, 1); }, f3 = function (v) { return _sFmt(v, 3); };
    var P = [
      { h: 100, title: 'Volume', series: [{ k: 'volume', bars: true, fmt: _sVol, tag: true, color: '#1f6f9f', hc: '#7fb8dd' }], floor0: true },
      { h: 115, title: 'RSI (14, 70, 30)', series: [{ k: 'rsi', color: '#9ca3af', fmt: f1 }], refs: [30, 70] },
      { h: 140, title: 'MACD (12, 26, 9)', series: [{ k: 'hist', bars: true, signed: true, fmt: f3 }, { k: 'macd', color: '#22d3ee', fmt: f3 }, { k: 'signal', color: '#e7d9a8', fmt: f3 }], zero: true, zeroColor: '#8b5cf6' },
      { h: 100, title: 'Volume Rate Of Change (14)', series: [{ k: 'vroc', color: '#f59e0b', fmt: f1 }], zero: true, zeroColor: '#ef4444' },
      { h: 130, title: 'Implied Volatility', series: [{ k: 'iv', color: '#22d3ee', fmt: function (v) { return _sFmt(v, 4); } }, { k: 'iv_ratio', nodraw: true, fmt: function (v) { return 'IV Ratio ' + _sFmt(v, 2); }, hc: '#f87171' }], axis: true }
    ];
    var n = pts.length;
    el.innerHTML = P.map(function (o, pi) { return '<div class="st-h" style="' + _SH + '">' + _sHead(pts, o, n - 1) + '</div>' + _sPanel(pts, o); }).join('');
    var heads = el.querySelectorAll('.st-h'), svgs = el.querySelectorAll('svg'), slot = (SW - SPL - SPR) / n;
    var put = function (i, x) {
      Array.prototype.forEach.call(heads, function (hd, pi) { hd.innerHTML = _sHead(pts, P[pi], i); });
      Array.prototype.forEach.call(svgs, function (sv) { var l = sv.querySelector('.st-x'); l.setAttribute('x1', x); l.setAttribute('x2', x); });
    };
    el.onmousemove = function (e) {
      var r = svgs[0].getBoundingClientRect(), x = e.clientX - r.left;
      if (x < SPL || x > SW - SPR) return put(n - 1, -10);
      var i = Math.max(0, Math.min(n - 1, Math.floor((x - SPL) / slot)));
      put(i, SPL + (i + 0.5) * slot);
    };
    el.onmouseleave = function () { put(n - 1, -10); };
  }
  window.mountActpopStudies = async function (el, sym) {
    if (!el || !sym) return;
    var tok = el._tok = (el._tok || 0) + 1;
    var note = function (t) { el.innerHTML = '<div style="color:#94a3b8;font:11px Arial,sans-serif;padding:8px;">' + t + '</div>'; };
    note('Loading studies...');
    try {
      var res = await fetch('/api/actionable/studies?symbol=' + encodeURIComponent(sym) + '&days=130');
      if (!res.ok) { if (tok === el._tok) note('Studies not available.'); return; }
      var js = await res.json();
      var pts = (js.points || []).filter(function (x) { return x.close != null; });
      if (tok !== el._tok) return;
      if (pts.length < 20) { note('Not enough daily history for studies.'); return; }
      _drawStudies(el, pts);
    } catch (e) { if (tok === el._tok) note('Studies not available.'); }
  };

  function _loadChart(containerEl, tvSym) {
    containerEl.innerHTML = '';
    var wrapper = document.createElement('div');
    wrapper.className    = 'tradingview-widget-container';
    wrapper.style.cssText = 'height:100%;width:100%;';
    var wd = document.createElement('div');
    wd.className    = 'tradingview-widget-container__widget';
    wd.style.cssText = 'height:calc(100% - 32px);width:100%;';
    wrapper.appendChild(wd);
    var sc = document.createElement('script');
    sc.type  = 'text/javascript';
    sc.src   = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    sc.async = true;
    sc.textContent = JSON.stringify({
      autosize: true, symbol: tvSym,
      interval: 'D', timezone: 'America/New_York',
      theme: 'light', style: '1', locale: 'en',
      withdateranges: true, hide_side_toolbar: false,
      allow_symbol_change: true, calendar: false,
      studies: ['BB@tv-basicstudies','RSI@tv-basicstudies'],
      support_host: 'https://www.tradingview.com',
    });
    wrapper.appendChild(sc);
    containerEl.appendChild(wrapper);
  }

  // opts: { description, price, pctChange, badgeHtml, displaySym }
  window.openChartModal = function (sym, opts) {
    opts = opts || {};
    _ensure();

    var displaySym = opts.displaySym || sym || '';
    var tvSym      = toTvSym(sym);

    document.getElementById('scmSym').textContent   = displaySym;
    document.getElementById('scmYahoo').innerHTML   = (typeof yahooLink === 'function') ? yahooLink(sym) : '';
    document.getElementById('scmDesc').textContent  = opts.description || '';
    document.getElementById('scmBadge').innerHTML   = opts.badgeHtml   || '';

    var price = opts.price != null ? '$' + Number(opts.price).toFixed(2) : '';
    document.getElementById('scmPrice').textContent = price;

    var pct    = opts.pctChange != null ? Number(opts.pctChange) : null;
    var pctStr = pct != null ? (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%' : '';
    var pctCls = pct == null ? '' : pct > 0.001 ? 'mt-up' : pct < -0.001 ? 'mt-down' : 'mt-flat';
    var chgEl  = document.getElementById('scmChg');
    chgEl.textContent = pctStr;
    chgEl.className   = 'scm-chg ' + pctCls;

    var body = document.getElementById('scmBody');
    if (!sym || sym === '$') {
      body.innerHTML = '<div style="padding:40px;text-align:center;color:#94a3b8;font-size:14px;">No chart available for ' + displaySym + '</div>';
    } else {
      body.innerHTML = '<div id="scmOwn" style="display:none;height:370px;flex:0 0 370px;position:relative;"><div class="scm-own-svg"></div></div>'
        + '<div id="scmTv" style="flex:1 1 auto;min-height:0;"></div>';
      _loadChart(document.getElementById('scmTv'), tvSym);
    }

    document.getElementById(MODAL_ID).style.display = 'flex';
    if (sym && sym !== '$') _loadOwn(document.getElementById('scmOwn'), sym);
    document.body.style.overflow = 'hidden';
  };

  window.closeChartModal = function () {
    var modal = document.getElementById(MODAL_ID);
    if (!modal || modal.style.display === 'none') return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
    var body = document.getElementById('scmBody');
    if (body) body.innerHTML = '';
  };
})();
