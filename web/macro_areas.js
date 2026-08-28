/* macro_areas.js — Macro read card for /actionable (TASK_78/TASK_85/TASK_116).
 *
 * Self-contained; reads GET /api/macro-areas?date=<D>.
 *
 * Renders:
 *   - Compact side-rail rows into #macroRailAreas (TASK_85 primary display)
 *   - Full-width collapsible card into #macroReadCard if present (legacy)
 *
 * Per-row compact layout (side rail, TASK_116 consolidation, refined by
 * several user requests through 2026-07-04 — see
 * docs/market_panel_consolidation_design.md):
 *
 *   Regular area row:
 *     [quad glyph][SYM] ... [Td][Tn][range bar+tick][candle][%chg chip]
 *   Td/Tn/range-bar/candle/%chg are grouped into one `.msr-data-cluster`
 *   flex unit (tight 2px internal gap) with `margin-left:auto` on the
 *   WHOLE cluster, not the chip alone — so the group stays packed together
 *   and is pushed flush to the row's right edge as a unit; the free space
 *   lands between SYM and the cluster, not inside it.
 *
 *   Volatility (gauge) row:
 *     [quad glyph][SYM zone-colored] ... [gauge badge, centered]
 *       ... [volBar][candle][%chg chip] (flush right)
 *   `.msr-gauge-wrap` (flex:1, justify-content:center) sits between SYM and
 *   the trailing `.msr-vol-cluster` (volBar+candle+%chg, no auto-margin of
 *   its own) — the wrap absorbs all the row's free space and centers the
 *   badge inside it, which also has the side effect of pushing the
 *   vol-cluster flush right (matching the other panels), since nothing
 *   else in the row competes for that leftover space.
 *
 *   Sectors row (own rail section) — different anatomy, only change here is
 *   railRangeBar(..., showPct=false): the trailing "NN%" range-bar label is
 *   suppressed and the symbol/sector name column grows to fill that freed
 *   space instead (`.msr-name` is already flex:1; `.msr-etf-row .msr-name-
 *   tick` gets a scoped override for the same effect in the ETF sub-row,
 *   which otherwise uses the fixed-width `.msr-name-tick`).
 */
(function () {
  'use strict';

  /* ── utilities ──────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
                 '"': '&quot;', "'": '&#39;' }[c];
      });
  }

  // Wraps _common.js's symbolLink() defensively (same guard style this file
  // already uses for window.mtTip below) -- Yahoo Finance quote-page link on
  // the member symbol text, no separate icon. `desc` (the friendly name
  // already shown as the row's display text, e.g. "Gold" for /GC) prints
  // ahead of "Open ... on Yahoo Finance" in the hover title when it differs
  // from the raw symbol -- user: "for symbols -> popover -> add company
  // names before saying open in finance."
  function symLink(html, sym, desc) {
    return (typeof window.symbolLink === 'function') ? window.symbolLink(html, sym, desc) : html;
  }

  function fmtPct(v, digits) {
    if (v === null || v === undefined) return '—';
    return (v * 100).toFixed(digits === undefined ? 0 : digits) + '%';
  }

  /* ── Td / Tn diagonal arrows ──────────────────────────────────────── */
  /* val: >0 up (↗), <0 down (↘), 0 flat (–), null/undefined = no data at
     all for this symbol (e.g. Dollar/DXY has no Trade/Trend value) -- that
     case renders BLANK, not a "Td–" placeholder. Still keeps the fixed
     22px .msr-dur box (styles.css) so columns line up; just nothing in it.
     User: "Just replace with blanks when there is no values for TD and TN
     ex: Dollar." (Labels print normally whenever there IS a value.) */
  function durArrow(val, label) {
    if (val === null || val === undefined) {
      return '<span class="msr-dur" title="' + esc(label) + ': no data"></span>';
    }
    if (val > 0) {
      return '<span class="msr-dur msr-dur-up" title="' + esc(label) + ' up">' +
        esc(label) + '&#8599;</span>';
    }
    if (val < 0) {
      return '<span class="msr-dur msr-dur-down" title="' + esc(label) + ' down">' +
        esc(label) + '&#8600;</span>';
    }
    return '<span class="msr-dur msr-dur-flat" title="' + esc(label) + '">' + esc(label) + '&ndash;</span>';
  }

  /* ── ETF proxy sub-row (single sector ETF: price/%chg/Td/Tn/Risk Range) ── */
  // Symbol-name color, same convention as rrTape's chips (market_bar.js
  // outlookBg): color by RR outlook, falling back to muted gray when there
  // isn't one.
  function _nameColor(outlook) {
    if (!outlook) return '#888';
    var c = window.outlookColor ? window.outlookColor(outlook) : 'inherit';
    return (c && c !== 'inherit') ? c : '#888';
  }

  // Zone color for Volatility members (TASK_116) — same palette as rrTape's
  // chipHtml zoneColor: investable=green, chop=amber, elevated=red. Used to
  // color the volatility SYMBOL name (not outlook) so an investable VIX
  // reads green on the rail the same way it does on the mini-tape.
  function _zoneColor(zone) {
    if (zone === 'investable') return '#1d9e75';
    if (zone === 'chop')       return '#eab308';
    if (zone === 'elevated')   return '#d4537e';
    return '#888';
  }

  // 7×14 mini candle, reusing market_bar.js's SVG builder via the shared
  // mtTip API (window.mtTip.candleSvg) — no duplicate candle-drawing code.
  function _candleHtml(m) {
    if (!window.mtTip || !window.mtTip.candleSvg) return '';
    return window.mtTip.candleSvg(m.open, m.high, m.low, m.last) || '';
  }

  // Solid %chg chip (tape convention, TASK_116) — replaces the plain colored
  // % text. Honors the member `inverted` flag (HY/HYSPRD: rising = risk-off
  // = red), same convention as market_bar.js's dirClass/INVERTED.
  function _chgChipHtml(pct, inverted) {
    if (pct === null || pct === undefined) return '<span class="msr-chg"></span>';
    var n = Number(pct);
    var flat = Math.abs(n) < 0.001;
    var up = !flat && (inverted ? n < 0 : n > 0);
    var down = !flat && (inverted ? n > 0 : n < 0);
    var bg = up ? '#1d9e75' : down ? '#d4537e' : '#888';
    var txt = flat ? '0.0%' : (n > 0 ? '+' : '') + n.toFixed(1) + '%';
    return '<span class="msr-chg" style="background:' + bg + ';">' + esc(txt) + '</span>';
  }

  // Friendly display name for a non-gauge member (2026-07-04) — ref_macro_
  // area.label is a per-row column that's the AREA's own label repeated for
  // most members (stocks/ETFs: already-readable tickers, left alone) but a
  // genuine override for cryptic ones (futures /XX, $-index tickers, FRED/
  // CGI-suffixed yields, foreign indices — e.g. '/GC' -> 'Gold'). Detect a
  // real override by checking it differs from the area's own label; only
  // then prefer it over the raw symbol.
  function _memberDisplayName(m, area) {
    return (m.label && m.label !== area.label) ? m.label : m.symbol;
  }

  // Native title-attribute tooltip for the compact row (symbol/price/%chg/
  // outlook) — the anatomy no longer shows a separate price column (tape
  // convention: price lives in the hover, only %chg is a visible chip).
  // Includes both the friendly name (if the row is showing one) and the raw
  // symbol, so a renamed row like "Gold" doesn't lose its "/GC" identity.
  function _rowTitle(m, displayName) {
    var parts = [];
    if (displayName && m.symbol && displayName !== m.symbol) {
      parts.push(displayName + ' (' + m.symbol + ')');
    } else if (m.symbol) {
      parts.push(m.symbol);
    }
    var priceTxt = _fmtPrice(m.last);
    if (priceTxt !== null) parts.push(priceTxt);
    if (m.pct_change !== null && m.pct_change !== undefined) {
      parts.push((m.pct_change > 0 ? '+' : '') + Number(m.pct_change).toFixed(2) + '%');
    }
    if (m.outlook) parts.push(m.outlook);
    return parts.join(' — ');
  }

  // 6-caret MacroNet breakdown shown before the symbol (replaces the old
  // single monthly-score glyph, 2026-08-27) — 60D window, this/next/
  // following month, Qtr, Next Qtr: the same 6 legs, same glyph set
  // (▲/▼/→, green/red/grey) as the Actionable grid's Category Drivers
  // caret rows (web/actionable.js ~line 690: `st > 0 ? '▲' : st < 0 ? '▼'
  // : '→'`), sourced from api/routers/macro_areas.py::_macro6_from_detail
  // (per-member `macro6`). All 6 on ONE line (user: "same way ... same
  // sizes all on the same line with same ratio, but smaller") — same
  // glyph/color proportions as that reference, just shrunk to font-size
  // 5px so 6 fit ahead of the symbol name instead of Category Drivers'
  // one-per-row layout. Hover -> bulleted popover with the full breakdown
  // (label/quad/weight/value per leg), same Rich Tooltips convention as
  // the rest of the app (structured list, not a flat string — a native
  // title= attribute can't render that, hence the custom popover below
  // instead of just a longer title=).
  // 3rd element: true = the "headline" legs (60D window = the blended
  // summary of the 3 months; Qtr = the live current-quarter leg, as
  // opposed to Next Qtr's often-~0%-weight preview) render bigger than
  // the 4 supporting-detail legs. User: "60D and Qtr should be bigger
  // than the others."
  var _MACRO6_ORDER = [
    ['window',   '60D window', true],
    ['month1',   'This month', false],
    ['month2',   'Next month', false],
    ['month3',   'Following month', false],
    ['qtr',      'Qtr', true],
    ['next_qtr', 'Next Qtr', false],
  ];
  var _macro6BySymbol = {};   // symbol -> macro6 obj, for the hover popover

  function _macro6Dir(stance) {
    if (stance === null || stance === undefined) return { g: '→', c: '#9ca3af' };
    var n = Number(stance);
    if (n > 0) return { g: '▲', c: '#16a34a' };
    if (n < 0) return { g: '▼', c: '#dc2626' };
    return { g: '→', c: '#9ca3af' };
  }

  function _macro6CaretsHtml(macro6, sym) {
    // Fixed-width empty slot when there's no data, so rows still line up
    // the same way the old single-caret slot did. A separate flex-item
    // sibling of .msr-name-tick (NOT nested inside it) -- text-overflow:
    // ellipsis on a container with mixed inline content (this caret strip
    // + the symbol text) measures unreliably, which is what was cutting
    // "S&P" down to just "S" while leaving visible slack before Td. Extra
    // margin-right beyond .msr-row's own gap:2px -- user: "add a space
    // after Carets and Symbol."
    if (!macro6 || !sym) {
      return '<span style="display:inline-block; width:20px; vertical-align:middle;"></span>';
    }
    _macro6BySymbol[sym] = macro6;
    var cells = _MACRO6_ORDER.map(function (pair) {
      var leg = macro6[pair[0]];
      var dir = _macro6Dir(leg ? leg.stance : null);
      var big = pair[2];
      return '<span style="color:' + dir.c + '; font-size:' + (big ? '7px' : '5px') +
        '; line-height:1;">' + dir.g + '</span>';
    }).join('');
    return '<span class="mra-macro6" data-mra-sym="' + esc(sym) + '" ' +
      'style="display:inline-flex; align-items:center; gap:0.5px; margin-right:4px; ' +
      'vertical-align:middle; cursor:help;">' + cells + '</span>';
  }

  /* ── 6-caret popover (bulleted, per Rich Tooltips convention) ─────────── */
  var _macro6PopEl = null;
  function _macro6Pop() {
    if (_macro6PopEl) return _macro6PopEl;
    var el = document.createElement('div');
    el.id = 'mra-macro6-pop';
    el.style.cssText = 'display:none; position:fixed; z-index:3000; background:#fff; ' +
      'border:1px solid #d1d5db; border-radius:6px; box-shadow:0 4px 16px rgba(0,0,0,0.18); ' +
      'padding:8px 10px; font-size:10px; color:#1f2937; max-width:230px; pointer-events:none;';
    document.body.appendChild(el);
    _macro6PopEl = el;
    return el;
  }
  function _macro6PopHtml(macro6, sym) {
    var lis = _MACRO6_ORDER.map(function (pair) {
      var leg = macro6[pair[0]];
      var dir = _macro6Dir(leg ? leg.stance : null);
      var label = (leg && leg.label) ? leg.label : pair[1];
      var quadTxt = (leg && leg.quad != null) ? ' (Q' + leg.quad + ')' : '';
      var wTxt = (leg && leg.w != null) ? ' ×' + Math.round(leg.w * 100) + '%' : '';
      var valTxt = (leg && leg.stance != null)
        ? (leg.stance >= 0 ? '+' : '') + leg.stance.toFixed(3) : '—';
      return '<li style="margin:2px 0;">' +
        '<span style="color:' + dir.c + ';font-weight:700;">' + dir.g + '</span> ' +
        '<strong>' + pair[1] + '</strong>' + esc(quadTxt) +
        '<span style="color:#94a3b8;">' + esc(wTxt) + '</span>: ' +
        '<span style="color:' + dir.c + ';font-weight:600;">' + esc(valTxt) + '</span>' +
        (label && label !== pair[1] ? ' <span style="color:#94a3b8;">(' + esc(label) + ')</span>' : '') +
        '</li>';
    }).join('');
    return '<div style="font-weight:700;margin-bottom:4px;">' + esc(sym) + ' — MacroNet legs</div>' +
      '<ul style="margin:0;padding-left:15px;list-style:disc;">' + lis + '</ul>';
  }
  function _macro6Show(target, macro6, sym) {
    if (!macro6) return;
    var pop = _macro6Pop();
    pop.innerHTML = _macro6PopHtml(macro6, sym);
    pop.style.display = 'block';
    var rect = target.getBoundingClientRect();
    pop.style.top = (rect.bottom + 4) + 'px';
    pop.style.left = rect.left + 'px';
    requestAnimationFrame(function () {
      var vw = window.innerWidth, vh = window.innerHeight;
      var pr = pop.getBoundingClientRect();
      if (pr.right > vw - 8) pop.style.left = Math.max(8, vw - pr.width - 8) + 'px';
      if (pr.bottom > vh - 8) pop.style.top = Math.max(8, rect.top - pr.height - 4) + 'px';
    });
  }
  function _macro6Hide() {
    if (_macro6PopEl) _macro6PopEl.style.display = 'none';
  }
  // Delegated (rows are rebuilt via innerHTML on every refresh, so a
  // per-element listener would need re-attaching every render).
  document.addEventListener('mouseover', function (ev) {
    var el = ev.target.closest && ev.target.closest('.mra-macro6');
    if (!el) return;
    var sym = el.getAttribute('data-mra-sym');
    var macro6 = _macro6BySymbol[sym];
    if (macro6) _macro6Show(el, macro6, sym);
  });
  document.addEventListener('mouseout', function (ev) {
    var el = ev.target.closest && ev.target.closest('.mra-macro6');
    if (!el) return;
    if (ev.relatedTarget && el.contains(ev.relatedTarget)) return;
    _macro6Hide();
  });

  /* ── range bar (compact rail version) ──────────────────────────────── */
  // showPct (default true): the trailing "42%"-style label. railAreaRow's
  // regular rows (2026-07-04) pass false since the row is already dense with
  // the candle + Td/Tn + %chg chip; the tick + hover title (still present)
  // carry the same info. renderSectorsPanel's own row doesn't pass it, so
  // it keeps the label unchanged.
  function railRangeBar(rr_pos, hot_pct, cold_pct, showPct) {
    if (rr_pos === null || rr_pos === undefined) {
      return '<span class="mra-muted" style="font-size:9px;">n/a</span>';
    }
    if (showPct === undefined) showPct = true;
    var actualPct = Math.round(rr_pos * 100);   // unclamped, for the label
    var pct    = Math.max(0, Math.min(1, rr_pos));
    var tickPx = Math.round(pct * 100);          // clamped, for bar positioning
    var isHot  = (hot_pct  !== null && hot_pct  !== undefined) ? (rr_pos >= hot_pct)  : (rr_pos >= 0.80);
    var isCold = (cold_pct !== null && cold_pct !== undefined) ? (rr_pos <= cold_pct) : (rr_pos <= 0.20);
    var extreme = isHot || isCold;
    return (
      '<div class="msr-rb-wrap">' +
        '<div class="msr-rb" title="' + actualPct + '% of range">' +
          '<div class="msr-rb-fill" style="width:' + tickPx + '%"></div>' +
          '<div class="msr-rb-tick' + (extreme ? ' extreme' : '') +
               '" style="left:' + tickPx + '%"></div>' +
        '</div>' +
        (showPct ? '<span class="msr-pct">' + actualPct + '%</span>' : '') +
      '</div>'
    );
  }


  /* ── compact area row for side rail ────────────────────────────────── */
  // One row per member symbol, for every area (Volatility already worked this
  // way; every other area used to collapse to a single aggregate row — now
  // all of them break out individually, using the same per-member fields the
  // API already computes (member.trade/trend are already signed ints
  // matching durArrow; member.rr_pos is already a 0-1 fraction matching
  // railRangeBar), so no backend change was needed for this.
  function _fmtPrice(v) {
    if (v === null || v === undefined) return null;
    return v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }

  // Standalone, fixed-width price and %chg columns — siblings of
  // .msr-name-tick (not nested inside it, and not nested inside each other),
  // so both line up at the same x-position on every row regardless of
  // symbol length or how many digits the price/chg happen to have.
  function _priceChgSpan(m) {
    var priceTxt = _fmtPrice(m.last);
    if (priceTxt === null) return '<span class="msr-price"></span><span class="msr-price-chg"></span>';
    var chg = m.pct_change;
    var chgCls = chg > 0 ? 'msr-price-chg-up' : chg < 0 ? 'msr-price-chg-down' : 'msr-price-chg-flat';
    var chgTxt = (chg !== null && chg !== undefined)
      ? (chg > 0 ? '+' : '') + chg.toFixed(2) + '%'
      : '';
    return '<span class="msr-price">' + esc(priceTxt) + '</span>' +
           '<span class="msr-price-chg ' + chgCls + '">' + esc(chgTxt) + '</span>';
  }

  // Row anatomy (TASK_116): [quad glyph][SYM][candle][Td/Tn][range bar+tick]
  // [%chg chip]. Volatility (gauge) swaps Td/Tn+range-bar for the 3-zone
  // volRangeBar and colors SYM by zone instead of outlook; the trailing zone
  // badge stays.
  // Areas that skip the 6-caret MacroNet strip entirely -- user: "for
  // country ETFs & USD&Currency no carets" (Volatility already skips it
  // via its own gauge-role branch below).
  var _MACRO6_EXCLUDED_AREAS = { usd_currency: true, country_etfs: true };

  function railAreaRow(area) {
    var members = area.members || [];
    var noCarets = !!_MACRO6_EXCLUDED_AREAS[area.area_key];
    return members.map(function (m) {
      if (m.role === 'gauge') {
        var zone = m.zone || '—';
        var gaugeClass = zone === 'investable' ? 'msr-gauge-g'
                       : zone === 'elevated'   ? 'msr-gauge-r'
                       : 'msr-gauge-a';
        return (
          // Volatility (gauge) rows: no 6-caret MacroNet strip -- user:
          // "For Volatility -> don't display carets." (the zone badge
          // already carries this row's own signal). volRangeBar (the
          // low/high threshold bar between the zone text and the candle/
          // %chg) dropped too -- user: "what is bar between investable
          // text and Value? Can we remove that."
          '<div class="msr-row" title="' + esc(_rowTitle(m)) + '">' +
            '<span class="msr-name msr-name-tick" style="color:' + _zoneColor(zone) + ';">' +
              // Prefer a real per-symbol label override; when there isn't
              // one (label just repeats the area's own name, e.g. VIX's
              // is "Volatility"), fall back to ref_sector.description
              // (m.desc) instead of nothing.
              symLink(esc(m.label || area.label), m.symbol,
                      (m.label && m.label !== area.label) ? m.label : m.desc) +
            '</span>' +
            '<div class="msr-gauge-wrap">' +
              '<span class="msr-gauge ' + gaugeClass + '">' + esc(zone) + '</span>' +
            '</div>' +
            '<div class="msr-vol-cluster">' +
              _candleHtml(m) +
              _chgChipHtml(m.pct_change, m.inverted) +
            '</div>' +
          '</div>'
        );
      }
      var dispName = _memberDisplayName(m, area);
      return (
        '<div class="msr-row" title="' + esc(_rowTitle(m, dispName)) + '">' +
          (noCarets ? '' : _macro6CaretsHtml(m.macro6, m.symbol)) +
          '<span class="msr-name msr-name-tick" style="color:' + _nameColor(m.outlook) + ';">' +
            // Same fallback as the gauge row above: dispName only differs
            // from the raw symbol when there's a real label override
            // (_memberDisplayName); otherwise use ref_sector.description
            // (m.desc) -- user: "Why HYG is not saying High yield credit?"
            // (HYG's own ref_macro_area.label is just "Credit", its area's
            // name, so dispName fell back to the bare symbol with nothing
            // to show).
            symLink(esc(dispName), m.symbol, dispName !== m.symbol ? dispName : m.desc) +
          '</span>' +
          '<div class="msr-data-cluster">' +
            durArrow(m.trade, 'Td') +
            durArrow(m.trend, 'Tn') +
            railRangeBar(m.rr_pos, area.hot_pct, area.cold_pct, false) +
            _candleHtml(m) +
            _chgChipHtml(m.pct_change, m.inverted) +
          '</div>' +
        '</div>'
      );
    }).join('');
  }

  /* ── sectors panel (own side-rail section) ────────────────────────── */
  // 2026-08-27 -- trimmed from a full per-sector list (stance arrow + Td/Tn
  // + range bar + breadth-stats sub-row, one row per GICS sector) down to
  // just the Leaders/Laggards/Rotate-in summary, each name tagged with your
  // own $ exposure. The dropped per-sector rows visually duplicated the new
  // Sectors ETF rail panel (col 4) -- same arrow/bar widgets, unrelated math
  // underneath (breadth % vs. one ETF's price-vs-line/RR-position) -- which
  // read as "the same info again" rather than a distinct signal, per
  // analysis: "if breadth-vs-price divergence isn't a signal you
  // specifically watch for, this panel is largely redundant with the new
  // Sectors ETF panel ... keep just Leaders/Laggards/Rotate-in + your $
  // exposure." User: "do right-rail recommendation."
  // 2026-08-27 follow-up -- a numbers table under "Rotate in" for each
  // flagged sector: the raw breadth % (behind the rotate_in threshold rule
  // itself -- pct_above_trend>=50% AND pct_above_trade<50%) plus that
  // sector's own SPDR ETF read (outlook/Td/Tn/RR%), same fields as the
  // Signal|Read table shown in chat. User: "I don't need thesis, i need
  // numbers. The table you have shown, can we display that below 'Rotate
  // in'".
  function rotateDetailHtml(sectorObj, showName) {
    if (!sectorObj) return '';
    var etf = sectorObj.etf || {};
    var rows = [];
    if (sectorObj.pct_above_trade != null || sectorObj.pct_above_trend != null) {
      // User: "rename Sector Td/Tn to Sec Bredth [sic] in the details,
      // number of stocks" -- label now includes n (the breadth universe
      // size behind the two %s) instead of a bare "Td / Tn" tag.
      rows.push(['Sec Breadth' + (sectorObj.n != null ? ' (' + sectorObj.n + ')' : ''),
        (sectorObj.pct_above_trade != null ? Math.round(sectorObj.pct_above_trade * 100) + '% Td' : '—')
        + ' / ' + (sectorObj.pct_above_trend != null ? Math.round(sectorObj.pct_above_trend * 100) + '% Tn' : '—')]);
    }
    if (etf.symbol) {
      if (etf.outlook) rows.push([esc(etf.symbol) + ' RR Outlook', esc(etf.outlook)]);
      // Td/Tn arrows + RR bar combined into one row, same
      // [durArrow(Td)][durArrow(Tn)][railRangeBar] cluster every other
      // rail-panel row uses (railAreaRow's .msr-data-cluster) -- was two
      // separate rows. Same hot/cold thresholds (0.8/0.2) too. User:
      // "Combine Td/TN and RR% like others".
      if (etf.td || etf.tn || etf.rr_pos != null) {
        // 2026-08-27 -- was durArrow() (the shared rail-panel helper),
        // which wraps each arrow in .msr-dur: fixed 22px width + right-
        // justified, so a SERIES of rows' arrows all line up in a column.
        // That's correct for a repeating column of many rows (every other
        // use of durArrow in this file) but wrong for this ONE-OFF row --
        // right-justifying "Td" inside its own empty 22px box reads as a
        // phantom leading space before it. Local arrowHtml() reuses just
        // the color classes (.msr-dur-up/-down/-flat), no fixed width/
        // justify. &nbsp; (not a bare space) separates the pieces -- a
        // literal " " between flex-item siblings can collapse to nothing.
        // User: "Align Td with top rows" -> "there is one space before Td
        // and no space between arrow[Tn] and [bar]".
        var arrowHtml = function (dir, label) {
          var cls = dir === 'up' ? 'msr-dur-up' : dir === 'down' ? 'msr-dur-down' : 'msr-dur-flat';
          var glyph = dir === 'up' ? '&#8599;' : dir === 'down' ? '&#8600;' : '&ndash;';
          return '<span class="' + cls + '">' + esc(label) + glyph + '</span>';
        };
        rows.push([esc(etf.symbol),
          '<span class="msr-data-cluster" style="margin-left:0;">'
          + arrowHtml(etf.td, 'Td') + '&nbsp;'
          + arrowHtml(etf.tn, 'Tn') + '&nbsp;'
          + railRangeBar(etf.rr_pos, 0.8, 0.2, true)
          + '</span>']);
      }
    }
    if (!rows.length) return '';
    var trs = rows.map(function (r) {
      return '<tr><td style="color:var(--text-3);padding:1px 6px 1px 0;">' + r[0] + '</td>'
        + '<td style="font-weight:600;">' + r[1] + '</td></tr>';
    }).join('');
    // Per-sector name header only when there's more than one rotate-in
    // sector to tell apart -- with just one, the "Rotate in:" chip line
    // right above already names it (redundant, per "you don't need header
    // Consumer Discretionary as you already have it above Rotate in");
    // with several, each table needs its own label or they run together
    // indistinguishably. User: "you need to display details under the
    // sector name if you have multiple."
    var nameHtml = showName
      ? '<div style="font-size:9px;font-weight:600;color:var(--text-3);margin:4px 0 1px 14px;">' + esc(sectorObj.sector) + '</div>'
      : '';
    return nameHtml + '<table style="font-size:10px;margin:2px 0 2px 14px;border-collapse:collapse;">' + trs + '</table>';
  }

  function renderSectorsPanel(sectors, exposureMap) {
    var container = document.getElementById('macroRailSectors');
    if (!container) return;
    if (!sectors) { container.innerHTML = '<div class="msr-loading">No sector data.</div>'; return; }

    var all = sectors.all || [];
    function findSector(name) {
      for (var i = 0; i < all.length; i++) { if (all[i].sector === name) return all[i]; }
      return null;
    }
    function chip(name) {
      var exp = exposureMap && exposureMap[name];
      var expTxt = (exp && exp.market_value)
        ? ' (' + (typeof fmtUsd === 'function' ? fmtUsd(exp.market_value, { compact: true }) : '$' + Math.round(exp.market_value)) + ')'
        : '';
      return esc(name) + expTxt;
    }
    function chipList(names) { return (names || []).map(chip).join(' &middot; '); }

    var leaders  = chipList(sectors.leaders);
    var laggards = chipList(sectors.laggards);
    var rotateIn = chipList(sectors.rotate_in);
    var subrows = '';
    if (leaders)  subrows += '<div class="msr-sec-subrow"><span class="msr-sec-up">&#9650;</span> <span class="msr-sec-lbl">Leaders:</span> ' + leaders + '</div>';
    if (laggards) subrows += '<div class="msr-sec-subrow"><span class="msr-sec-down">&#9660;</span> <span class="msr-sec-lbl">Laggards:</span> ' + laggards + '</div>';
    if (rotateIn) {
      subrows += '<div class="msr-sec-subrow"><span class="msr-sec-rotate">&#8635;</span> <span class="msr-sec-lbl">Rotate in:</span> ' + rotateIn + '</div>';
      var rotateNames = sectors.rotate_in || [];
      var showRotateNames = rotateNames.length > 1;
      subrows += rotateNames.map(function (name) { return rotateDetailHtml(findSector(name), showRotateNames); }).join('');
    }

    if (!subrows) subrows = '<span class="mra-muted">—</span>';

    container.innerHTML = '<div class="msr-sec-block">' + subrows + '</div>';
  }

  /* ── render into side rail ──────────────────────────────────────────── */
  // Each area_key now has its own side-panel section/container (was one
  // blob container for every area concatenated together).
  var _AREA_CONTAINER_ID = {
    volatility:          'macroRailVolatility',
    top9:                'macroRailTop9',
    rates_duration:      'macroRailRates',
    credit:              'macroRailCredit',
    commodities_credit:  'macroRailCommodities',
    usd_currency:        'macroRailUsd',
    country_etfs:        'macroRailCountry',
    crypto:               'macroRailCrypto',
    sector_etfs:         'macroRailSectorEtfs',
    remaining:           'macroRailRemaining',
  };

  // Section-header breadth summary (↑n ↓n), TASK_116 — one id per area_key
  // that has a rail container (Sectors excluded; it keeps its own
  // leaders/laggards summary instead).
  var _AREA_BREADTH_ID = {
    volatility:          'macroBreadthVolatility',
    top9:                'macroBreadthTop9',
    rates_duration:      'macroBreadthRates',
    credit:              'macroBreadthCredit',
    commodities_credit:  'macroBreadthCommodities',
    usd_currency:        'macroBreadthUsd',
    country_etfs:        'macroBreadthCountry',
    crypto:               'macroBreadthCrypto',
    sector_etfs:         'macroBreadthSectorEtfs',
    remaining:           'macroBreadthRemaining',
  };

  function _breadthHtml(area) {
    var members = area.members || [];
    var up = 0, down = 0;
    members.forEach(function (m) {
      if (m.pct_change === null || m.pct_change === undefined) return;
      var n = Number(m.pct_change);
      if (n > 0) up++;
      else if (n < 0) down++;
    });
    if (!up && !down) return '';
    return '<span class="msr-breadth-up">&#8593;' + up + '</span> ' +
           '<span class="msr-breadth-down">&#8595;' + down + '</span>';
  }

  function renderRail(data) {
    var areas = (data && data.areas) || [];
    var byContainer = {};
    areas.forEach(function (area) {
      var containerId = _AREA_CONTAINER_ID[area.area_key];
      if (!containerId) return;
      byContainer[containerId] = (byContainer[containerId] || '') + railAreaRow(area);

      var breadthId = _AREA_BREADTH_ID[area.area_key];
      var breadthEl = breadthId && document.getElementById(breadthId);
      if (breadthEl) breadthEl.innerHTML = _breadthHtml(area);
    });

    Object.keys(_AREA_CONTAINER_ID).forEach(function (key) {
      var containerId = _AREA_CONTAINER_ID[key];
      var container = document.getElementById(containerId);
      if (!container) return;
      container.innerHTML = byContainer[containerId] || '<div class="msr-loading">No data.</div>';
    });
  }

  /* ── legacy full-width card (kept for backward-compat) ─────────────── */
  function stancePillHtml(stance, conviction) {
    if (!stance) return '<span class="mra-stance mra-neutral">—</span>';
    var cls = stance === 'Long' ? 'mra-long'
            : stance === 'Short' ? 'mra-short'
            : 'mra-neutral';
    var convTxt = (conviction !== null && conviction !== undefined)
      ? ' <span class="mra-conv">' + Math.round(conviction * 100) + '%</span>'
      : '';
    return '<span class="mra-stance ' + cls + '">' + esc(stance) + convTxt + '</span>';
  }

  function durationChip(val, label) {
    if (val === null || val === undefined) return '<span class="mra-chip mra-chip-na">' + label + ':—</span>';
    var cls = val > 0 ? 'mra-chip-bull' : val < 0 ? 'mra-chip-bear' : 'mra-chip-flat';
    var arrow = val > 0 ? '▲' : val < 0 ? '▼' : '—';
    return '<span class="mra-chip ' + cls + '">' + label + ':' + arrow + '</span>';
  }

  function rrBarHtml(rr_pos, is_hot, is_cold) {
    if (rr_pos === null || rr_pos === undefined) return '<span class="mra-no-rr">n/a</span>';
    var pct = Math.max(0, Math.min(1, rr_pos));
    var tickPct = Math.round(pct * 100);
    var fillCls = is_hot ? ' mra-rb-hot' : is_cold ? ' mra-rb-cold' : '';
    return (
      '<div class="rr-rb mra-rb" title="' + (tickPct) + '% of range">' +
        '<div class="rr-rb-fill' + fillCls + '" style="width:' + tickPct + '%"></div>' +
        '<div class="rr-rb-tick" style="left:' + tickPct + '%"></div>' +
      '</div>' +
      '<span class="mra-rb-label">' + tickPct + '%</span>'
    );
  }

  function extremesHtml(hot, cold) {
    var out = '';
    (hot || []).forEach(function (sym) {
      out += '<span class="mra-ext-hot" title="Overbought — trim">' + esc(sym) + ' ▲</span> ';
    });
    (cold || []).forEach(function (sym) {
      out += '<span class="mra-ext-cold" title="Oversold — add">' + esc(sym) + ' ▼</span> ';
    });
    return out || '<span class="mra-muted">—</span>';
  }

  function areaRowHtml(area) {
    var isVol   = area.area_key === 'volatility';
    var isRates = area.area_key === 'rates';

    if (isVol) {
      var vix_m = (area.members || []).find(function (m) { return m.role === 'gauge'; });
      var zone = vix_m ? (vix_m.zone || '—') : '—';
      var zoneClass = zone === 'investable' ? 'mra-zone-g'
                    : zone === 'elevated'   ? 'mra-zone-r'
                    : 'mra-zone-a';
      return (
        '<tr class="mra-row">' +
          '<td class="mra-area-name">' + esc(area.label) + '</td>' +
          '<td><span class="mra-zone ' + zoneClass + '">' + esc(zone) + '</span></td>' +
          '<td colspan="3" class="mra-muted">gauge only</td>' +
        '</tr>'
      );
    }
    if (isRates) {
      return (
        '<tr class="mra-row">' +
          '<td class="mra-area-name">' + esc(area.label) + '</td>' +
          '<td>' + stancePillHtml(area.stance, area.conviction) + '</td>' +
          '<td>' + durationChip(area.trade, 'Trade') + durationChip(area.trend, 'Trend') + '</td>' +
          '<td class="mra-muted mra-small">rate read</td>' +
          '<td>' + extremesHtml(area.extremes_hot, area.extremes_cold) + '</td>' +
        '</tr>'
      );
    }
    return (
      '<tr class="mra-row">' +
        '<td class="mra-area-name">' + esc(area.label) + '</td>' +
        '<td>' + stancePillHtml(area.stance, area.conviction) + '</td>' +
        '<td>' + durationChip(area.trade, 'Trade') + durationChip(area.trend, 'Trend') + '</td>' +
        '<td class="mra-rb-wrap">' +
          rrBarHtml(area.rr_pos, (area.extremes_hot || []).length > 0,
                                  (area.extremes_cold || []).length > 0) +
        '</td>' +
        '<td>' + extremesHtml(area.extremes_hot, area.extremes_cold) + '</td>' +
      '</tr>'
    );
  }

  function sectorsHtml(sectors) {
    if (!sectors) return '';
    function chips(arr, cls) {
      return (arr || []).map(function (s) {
        return '<span class="mra-sec-chip ' + cls + '">' + esc(s) + '</span>';
      }).join(' ');
    }
    return (
      '<tr class="mra-row mra-sectors-row">' +
        '<td class="mra-area-name">Sectors</td>' +
        '<td colspan="4">' +
          '<span class="mra-sec-label">Leaders:</span> ' +
          chips(sectors.leaders, 'mra-sec-bull') + '  ' +
          '<span class="mra-sec-label">Laggard:</span> ' +
          chips(sectors.laggards, 'mra-sec-bear') + '  ' +
          '<span class="mra-sec-label">Rotate in:</span> ' +
          chips(sectors.rotate_in, 'mra-sec-rotate') +
        '</td>' +
      '</tr>'
    );
  }

  function corrPlaceholderHtml() {
    return (
      '<tr class="mra-row mra-corr-row" id="macroCorrRow">' +
        '<td class="mra-area-name">USD Corr</td>' +
        '<td colspan="4" id="macroCorrSummary">' +
          '<span class="mra-muted">Loading…</span>' +
        '</td>' +
      '</tr>'
    );
  }

  function renderLegacyCard(data) {
    var card = document.getElementById('macroReadCard');
    if (!card) return;

    var areas   = (data && data.areas) || [];
    var sectors = data && data.sectors;
    var top_down = (data && data.top_down) || '';

    var rows = areas.map(areaRowHtml).join('');
    rows += sectorsHtml(sectors);
    rows += corrPlaceholderHtml();

    card.innerHTML =
      '<div class="mra-posture">' + esc(top_down) + '</div>' +
      '<div class="mra-body">' +
        '<table class="mra-table">' +
          '<thead><tr>' +
            '<th>Area</th><th>Stance</th><th>Duration</th><th>Range</th><th>Extremes</th>' +
          '</tr></thead>' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</div>';

    var asOf = document.getElementById('macroReadAsOf');
    if (asOf && data && data.as_of) asOf.textContent = 'as of ' + data.as_of;
  }

  function renderError(msg) {
    var rail = document.getElementById('macroRailAreas');
    if (rail) rail.innerHTML = '<div class="msr-err">Unavailable: ' + esc(msg) + '</div>';
    var card = document.getElementById('macroReadCard');
    if (card) card.innerHTML = '<div class="mra-err">Macro read unavailable: ' + esc(msg) + '</div>';
  }

  /* ── collapsible toggle (legacy card) ──────────────────────────────── */
  function initCollapse(headerEl, bodyEl) {
    if (!headerEl || !bodyEl) return;
    headerEl.style.cursor = 'pointer';
    var collapsed = false;
    headerEl.addEventListener('click', function () {
      collapsed = !collapsed;
      bodyEl.style.display = collapsed ? 'none' : '';
      var icon = headerEl.querySelector('.mra-toggle');
      if (icon) icon.textContent = collapsed ? '▶' : '▼';
    });
  }

  /* ── inject legacy card (only if the old macroReadCard anchor exists) ─ */
  function injectLegacyCard() {
    if (document.getElementById('macroReadCard')) return;
    var wrapper = document.createElement('div');
    wrapper.id = 'macroReadWrapper';
    wrapper.className = 'mra-wrapper';
    wrapper.innerHTML =
      '<div class="mra-header" id="macroReadHeader">' +
        '<span class="mra-title">Macro read</span> ' +
        '<span class="mra-toggle">▼</span>' +
        '<span class="mra-asof" id="macroReadAsOf"></span>' +
      '</div>' +
      '<div id="macroReadCard" class="mra-card"><span class="mra-muted">Loading…</span></div>';

    var anchor =
      document.getElementById('macroBand') ||
      document.getElementById('econPanel') ||
      document.querySelector('main .card');
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(wrapper, anchor.nextSibling);
    }
    initCollapse(
      document.getElementById('macroReadHeader'),
      document.getElementById('macroReadCard')
    );
  }

  // 2026-08-27 -- your own $ exposure per sector, tagged onto each name in
  // renderSectorsPanel's Leaders/Laggards/Rotate-in chip lists -- same
  // drv_category_perf table (via /api/cockpit/factor-scorecard?axis=
  // sector) the Sector factor-scorecard grid and Portfolio Mix's Sector
  // pie both read, so this agrees with those rather than recomputing its
  // own $ totals from raw held rows. Whole-portfolio (no accounts= filter)
  // -- this rail panel has no Accounts-filter UI of its own to scope it
  // further. Best-effort: a failure here still lets the chip lists render,
  // just without the $ exposure tag.
  async function _fetchSectorExposure(dateParam) {
    try {
      var qs = dateParam ? dateParam + '&axis=sector' : '?axis=sector';
      var resp = await fetch('/api/cockpit/factor-scorecard' + qs);
      if (!resp.ok) return {};
      var data = await resp.json();
      var map = {};
      (data.rows || []).forEach(function (r) { map[r.category] = r; });
      return map;
    } catch (e) { return {}; }
  }

  /* ── main load ──────────────────────────────────────────────────────── */
  async function load() {
    var dateEl    = document.getElementById('datePicker');
    var dateParam = dateEl && dateEl.value ? '?date=' + dateEl.value : '';
    try {
      var resp = await fetch('/api/macro-areas' + dateParam);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();
      var exposureMap = await _fetchSectorExposure(dateParam);

      /* Primary: render side rail */
      renderRail(data);
      renderSectorsPanel(data && data.sectors, exposureMap);

      /* Legacy full-width card (only if the old wrapper was injected by another path) */
      if (document.getElementById('macroReadCard')) {
        renderLegacyCard(data);
      }

      /* Notify USD-corr listener that areas card is ready */
      document.dispatchEvent(new CustomEvent('macroReadReady', { detail: data }));
    } catch (e) {
      renderError(e && e.message ? e.message : String(e));
    }
  }

  // 2026-08-10 -- Dashboard (/) has no `main .card` element (Actionable's
  // own layout marker) but does have #macroRailVolatility once this script
  // loads there too -- widened rather than replaced so Actionable's
  // original check still stands unchanged. User: "add Volatility & Major
  // Market panels that you see on actionable screen to dashboard screen on
  // the right side."
  function init() {
    if (!document.querySelector('main .card') && !document.getElementById('macroRailVolatility')) return;
    load();
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Exposed so actionable.js's Refresh button (loadActionable) can re-pull
  // the Macro rail too -- previously only the #datePicker "change" event
  // reloaded it, so the volatility gauges (and the rest of the rail) went
  // stale after the initial page load until the date was changed.
  window.reloadMacroAreas = load;

})();
