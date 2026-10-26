// TASK_155 (2026-10-25): small static pictures of the Technical rules -- an illustration of each rule, NOT stock data.
// Shared by the Action popup (web/actionable_pops.js) and anything else that wants a rule thumbnail (grid, rules map page).
//   techRuleGraph(stepId, label, size) -> inline SVG string (size in px, default 64), theme aware (CSS variables only).
// Step 1 rules (S1-a ... 1e): price path against the Trade line (dashed), Trend line and the dotted lowest-of-5 Trade line.
// Step 2 (2a ... 2f): the two Bollinger bands rising / flat / falling.
// Step 3 rules (3a ... tr): the LRR to TRR ladder with the LRR and TRR zones shaded and a bracket for the rule's range.
// The wording of each rule lives in etl/technical_why.py::RULE_HELP; keep these pictures in step with web/technical_rules_map.html.
(function (w) {
  'use strict';
  var C = { fg: 'var(--text-1,#1c1917)', mu: 'var(--text-3,#a8a29e)', ac: 'var(--accent,#1d4ed8)',
            bu: 'var(--bull,#15803d)', be: 'var(--bear,#b91c1c)', zn: 'var(--border,#e5e5e2)' };
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }
  function pl(pts, attrs) { return '<polyline points="' + pts.map(function (p) { return p[0] + ',' + p[1]; }).join(' ') + '" fill="none" ' + attrs + '/>'; }
  function dot(x, y, fill, stroke, r) { return '<circle cx="' + x + '" cy="' + y + '" r="' + (r || 3.4) + '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="1.6"/>'; }
  function arrow(x, y, dir, col) {   // small triangle pointing up / down
    var d = dir === 'up' ? -1 : 1;
    return '<path d="M' + (x - 4) + ' ' + y + ' L' + x + ' ' + (y + 6 * d) + ' L' + (x + 4) + ' ' + y + ' Z" fill="' + col + '"/>';
  }
  function wrap(label, size, inner) {
    return '<svg class="tg-svg" viewBox="0 0 64 64" width="' + size + '" height="' + size + '" role="img" aria-label="' + esc(label) +
           '" xmlns="http://www.w3.org/2000/svg">' + inner + '</svg>';
  }

  // ---- Step 3: LRR (0%) to TRR (100%) ladder -------------------------------------------------
  function Y(p) { return +(54 - p * 0.46).toFixed(1); }
  function ladder(o) {
    var s = '<rect x="8" y="' + Y(25) + '" width="32" height="' + (Y(0) - Y(25)).toFixed(1) + '" fill="' + C.zn + '"/>' +
            '<rect x="8" y="' + Y(100) + '" width="32" height="' + (Y(90) - Y(100)).toFixed(1) + '" fill="' + C.zn + '"/>';
    [0, 50, 100].forEach(function (p) {
      s += '<line x1="8" x2="40" y1="' + Y(p) + '" y2="' + Y(p) + '" stroke="' + C.mu + '" stroke-width="1" stroke-dasharray="3 2"/>';
    });
    if (o.bracket) {
      var a = Y(o.bracket[0]), b = Y(o.bracket[1]);
      s += '<path d="M45 ' + a + ' L48 ' + a + ' L48 ' + b + ' L45 ' + b + '" fill="none" stroke="' + C.fg + '" stroke-width="1.6"/>';
    }
    s += pl(o.path.map(function (p) { return [p[0], Y(p[1])]; }), 'stroke="' + C.fg + '" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"');
    if (o.mark) s += dot(o.mark[0], Y(o.mark[1]), o.mark[2], o.mark[2], 3.2);
    if (o.arrow) s += arrow(o.arrow[0], Y(o.arrow[1]), o.arrow[2], o.arrow[3]);
    return s;
  }
  var LADDER = {
    '3a': { path: [[12, 30], [19, 14], [27, -6], [35, -20]], mark: [27, -6, C.be], arrow: [54, 40, 'down', C.be] },
    '3x': { bracket: [25, 60], path: [[12, 46], [18, 20], [24, 4], [30, 26], [38, 48]], mark: [24, 4, C.bu] },
    '3f': { bracket: [0, 25], path: [[12, 36], [18, 18], [24, 6], [30, 14], [38, 20]], mark: [24, 6, C.bu] },
    '3h': { bracket: [25, 60], path: [[12, 28], [20, 34], [28, 40], [38, 54]], arrow: [54, 40, 'up', C.bu] },
    '3k': { bracket: [90, 100], path: [[12, 58], [20, 72], [28, 88], [34, 96], [38, 86]], mark: [34, 96, C.be] },
    '3p': { bracket: [90, 100], path: [[12, 58], [20, 72], [28, 88], [34, 96], [38, 86]], mark: [34, 96, C.be] }
  };

  // ---- Step 1: price against the Trade / Trend / lowest-of-5 lines ---------------------------
  function lines(path, mark, o) {
    o = o || {};
    var s = pl([[5, 22], [59, 20]], 'stroke="' + C.ac + '" stroke-width="1.8" stroke-dasharray="5 3"') +     // Trade
            pl([[5, 44], [59, 40]], 'stroke="' + C.mu + '" stroke-width="1.8"') +                            // Trend
            (o.lowest === false ? '' : pl([[5, 31], [59, 29]], 'stroke="' + C.ac + '" stroke-width="1.4" stroke-dasharray="1.5 2.5"')) +  // lowest of last 5 Trade lines
            pl(path, 'stroke="' + C.fg + '" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"');
    if (mark) s += dot(mark[0], mark[1], mark[2], mark[3] || mark[2]);
    return s;
  }
  var SOFT = 'var(--act-sell-strong-bg,#fee2e2)';
  var LINES = {
    'S1-a': [[[5, 12], [16, 8], [26, 15], [34, 23], [44, 31.5], [57, 37]], [44, 31.5, C.be]],
    'S1-b': [[[5, 24], [18, 32], [32, 42], [46, 50], [58, 55]], [46, 50, 'none', C.be]],
    'S1-c': [[[5, 12], [16, 8], [26, 15], [34, 24], [44, 27], [57, 33]], [30, 20.5, SOFT, C.be]],
    'S1-d': [[[5, 27], [18, 26], [32, 27], [46, 26], [57, 27]], null],
    '1a': [[[5, 14], [18, 10], [32, 13], [46, 8], [58, 5]], null, { lowest: false }],
    '1b': [[[5, 12], [20, 10], [32, 25], [42, 24], [58, 15]], [32, 25, C.bu], { lowest: false }],
    '1d': [[[5, 12], [18, 24], [30, 33], [40, 30], [50, 21], [58, 12]], [40, 30, C.bu]],
    '1e': [[[5, 32], [20, 34], [34, 31], [46, 33], [58, 32]], null, { lowest: false }]
  };
  // tr (falling bands + under a line): two falling lines with price under them
  function trPic() {
    return pl([[5, 14], [59, 30]], 'stroke="' + C.ac + '" stroke-width="1.8" stroke-dasharray="5 3"') +
           pl([[5, 26], [59, 42]], 'stroke="' + C.mu + '" stroke-width="1.8"') +
           pl([[5, 30], [20, 38], [34, 46], [46, 52], [58, 56]], 'stroke="' + C.fg + '" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"') +
           dot(46, 52, C.be, C.be) ;
  }
  // ---- Step 2: the two Bollinger bands -------------------------------------------------------
  function bands(kind) {
    var up = { rise: [[5, 40], [59, 22]], flat: [[5, 30], [59, 30]], fall: [[5, 20], [59, 38]] }[kind];
    var lo = { rise: [[5, 52], [59, 36]], flat: [[5, 46], [59, 46]], fall: [[5, 32], [59, 52]] }[kind];
    return pl(up, 'stroke="' + C.mu + '" stroke-width="2"') + pl(lo, 'stroke="' + C.mu + '" stroke-width="2"') +
           (kind === 'rise' ? arrow(32, 12, 'up', C.bu) : kind === 'fall' ? arrow(32, 8, 'down', C.be) : '');
  }
  var BAND_KIND = { '2a': 'rise', '2b': 'rise', '2c': 'flat', '2d': 'flat', '2e': 'fall', '2f': 'fall' };

  w.techRuleGraph = function (id, label, size) {
    size = size || 64;
    var inner;
    if (LADDER[id]) inner = ladder(LADDER[id]);
    else if (LINES[id]) inner = lines(LINES[id][0], LINES[id][1], LINES[id][2]);
    else if (id === 'tr') inner = trPic();
    else if (BAND_KIND[id]) inner = bands(BAND_KIND[id]);
    else return '';
    return wrap(label || ('Illustration of rule ' + id), size, inner);
  };
})(window);
