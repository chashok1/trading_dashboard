/* rr_strip.js -- Hedgeye RR symbol strips on `/` (two rows under the area verdict bar).
 *
 * Row 1: markets (indexes, FX, rates/credit, VIX, commodities, Bitcoin). Row 2: sector ETFs and
 * stocks that have a Hedgeye range, then outlook-only ETFs (no price range) as tiny chips.
 * Symbols already on the Macro Week strip (DXY, 2Y, 10Y, VIX, Gold, WTI) are skipped here.
 *
 * Same meaning as the Macro Week strip: surrounding colour = Hedgeye outlook (green bullish,
 * red bearish, grey neutral); the arrow is the 5-session move; the % is the position inside the
 * Hedgeye risk range (0% = LRR, 100% = TRR). Reads GET /api/cockpit/rr-strip. Display only.
 */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(v, dp) { return v == null ? '--' : Number(v).toFixed(dp); }
  function olCls(o) { return o === 'bull' ? 'mw-bull' : o === 'bear' ? 'mw-bear' : ''; }
  function olName(o) { return o === 'bull' ? 'Bullish' : o === 'bear' ? 'Bearish' : 'Neutral'; }
  function arrow(v) {
    if (v == null || v === 0) return '';
    return '<span class="' + (v > 0 ? 'mw-bull' : 'mw-bear') + '">' + (v > 0 ? '▲' : '▼') + '</span>';
  }
  function posText(x) {
    if (x.pos_state === 'in') return Math.round(x.pos * 100) + '%';
    if (x.pos_state === 'above') return '⇑';
    if (x.pos_state === 'below') return '⇓';
    if (x.pos_state === 'na') return 'n/a';
    return '';
  }
  function extremeness(x) { return x.pos == null ? -1 : Math.abs(x.pos - 0.5); }

  function tipFor(x) {
    var l = [x.label + (x.name && x.name !== x.label ? ' - ' + x.name : ''),
             '• Hedgeye outlook: ' + olName(x.outlook)];
    if (x.has_range) {
      if (x.pos_state === 'na') {
        l.push('• Range position: not shown (price and range do not line up)');
      } else {
        l.push('• Position in risk range: ' + (x.pos_state === 'above' ? '⇑ price is above the top of the range (TRR)' :
          x.pos_state === 'below' ? '⇓ price is below the bottom of the range (LRR)' : Math.round(x.pos * 100) + '%'));
      }
      l.push('• Range: ' + num(x.lrr, 2) + ' (LRR) to ' + num(x.trr, 2) + ' (TRR)');
      l.push('• Last: ' + num(x.last, 2));
      l.push('• 5-session change: ' + (x.chg5 == null ? '--' : (x.chg5 > 0 ? '+' : '') + num(x.chg5, 2)));
    } else {
      l.push('• No Hedgeye price range for this symbol (outlook only)');
    }
    l.push('Source: hist_rr / drv_rr, drv_quote');
    return l.join('\n');
  }

  function chipHtml(x) {
    if (!x.has_range) {
      return '<span class="mw-chip rrs-chip rrs-tiny ' + olCls(x.outlook) + '" title="' + esc(tipFor(x)) + '">' + esc(x.label) + '</span>';
    }
    var glyph = x.extreme === 'high' ? ' <span class="mw-amber">⚠</span>'
      : x.extreme === 'low' ? ' <span class="mw-amber">◇</span>' : '';
    return '<span class="mw-chip rrs-chip ' + olCls(x.outlook) + '" title="' + esc(tipFor(x)) + '">' + esc(x.label) +
      ' <span class="' + (x.pos_state === 'above' || x.pos_state === 'below' ? 'mw-amber' : 'mw-dim') + '">' + posText(x) + '</span>' + arrow(x.chg5) + glyph + '</span>';
  }

  function byOrder(a, b) {
    if (a.sub !== b.sub) return a.sub - b.sub;
    if (extremeness(a) !== extremeness(b)) return extremeness(b) - extremeness(a);
    return a.label < b.label ? -1 : 1;
  }

  function render(data) {
    var card = document.getElementById('rrStripCard');
    var r1 = document.getElementById('rrRow1');
    var r2 = document.getElementById('rrRow2');
    if (!card || !r1 || !r2) return;
    var items = data.items;
    var markets = items.filter(function (x) { return x.group === 'markets' && !x.on_top_bar; }).sort(byOrder);
    var ranged = items.filter(function (x) { return x.group === 'etf_stock' && x.has_range; }).sort(byOrder);
    var tiny = items.filter(function (x) { return x.group === 'etf_stock' && !x.has_range; })
      .sort(function (a, b) {
        var o = { bull: 0, neutral: 1, bear: 2 };
        return o[a.outlook] - o[b.outlook] || (a.label < b.label ? -1 : 1);
      });
    var prevSub = null;
    r1.innerHTML = markets.map(function (x) {
      var sep = (prevSub != null && x.sub !== prevSub) ? '<span class="av-sepline"></span>' : '';
      prevSub = x.sub;
      return sep + chipHtml(x);
    }).join('');
    r2.innerHTML = ranged.map(chipHtml).join('') +
      (ranged.length && tiny.length ? '<span class="av-sepline"></span>' : '') + tiny.map(chipHtml).join('');
    card.style.display = (markets.length || ranged.length || tiny.length) ? '' : 'none';
  }

  function currentDate() {
    var d = document.getElementById('datePicker');
    return (d && d.value) ? d.value : '';
  }
  async function load() {
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/rr-strip' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      render(await res.json());
    } catch (e) {
      var card = document.getElementById('rrStripCard');
      if (card) card.style.display = 'none';
    }
  }
  function init() {
    var dpk = document.getElementById('datePicker');
    if (dpk) dpk.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 400); });
    setTimeout(load, 800);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
