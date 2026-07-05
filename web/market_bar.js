/* Trading Dashboard — global mini market tape (TASK_116 consolidation)
 *
 * Self-mounting widget. Injects a single sticky ribbon (#rrTape1) below the
 * topbar with a curated pulse: SPX · VIX · [Nasdaq/Dow/Russell/Gold/Oil/Bond
 * Vol] · DXY · GC · WTI · 10Y · HY · BTC (2026-07-04: the 6 bracketed vol
 * gauges were added after VIX, mirroring every entry in the side rail's
 * Volatility area one-for-one). The full market breadth (ETFs, sectors,
 * tech, FX, indexes, credit, crypto, ...) still lives in the Actionable side
 * rail (web/macro_areas.js, /api/macro-areas) — bars 2/3 (#rrTape2/#rrTape3)
 * were retired in favor of that rail. See
 * docs/market_panel_consolidation_design.md.
 *
 * The Econ panel (#econPanel) is a static div in the page HTML (actionable.html).
 * It is toggled by #econBtn and lazily loaded from GET /api/macro.
 *
 * Color convention: green = up, red = down for all metrics.
 *   Inverted: up → red, down → green (HY credit spread only)
 */
(function () {
  'use strict';

  const REFRESH_MS = 60 * 1000;

  const INVERTED = new Set(['HY', 'HYSPRD']);

  // ---- formatting helpers -----------------------------------------------
  function fmtValue(v, fmt) {
    if (v === null || v === undefined) return '—';
    switch (fmt) {
      case 'index':
      case 'price':
        return Number(v).toLocaleString('en-US', {
          minimumFractionDigits: 2, maximumFractionDigits: 2
        });
      case 'pct':
        return Number(v).toFixed(2) + '%';
      case 'level':
        return Number(v).toFixed(1);
      default:
        return String(v);
    }
  }

  function fmtChgPct(chg_pct) {
    if (chg_pct === null || chg_pct === undefined) return '';
    return Math.abs(Number(chg_pct)).toFixed(1) + '%';
  }

  function dirClass(chg_pct, metric_key) {
    if (chg_pct === null || chg_pct === undefined) return 'mt-flat';
    const n = Number(chg_pct);
    if (Math.abs(n) < 0.001) return 'mt-flat';
    const inverted = INVERTED.has((metric_key || '').toUpperCase());
    if (inverted) {
      return n > 0 ? 'mt-down' : 'mt-up';
    }
    return n > 0 ? 'mt-up' : 'mt-down';
  }

  function dirArrow(chg_pct) {
    if (chg_pct === null || chg_pct === undefined) return '';
    const n = Number(chg_pct);
    if (Math.abs(n) < 0.001) return '';
    return n > 0 ? '▲' : '▼';
  }

  function volZoneCls(value, low, high) {
    if (value == null) return 'mt-flat';
    if (value < low)   return 'mt-up';    // green = investable
    if (value <= high) return 'mt-chop';  // amber = chop
    return 'mt-down';                     // red = elevated vol
  }

  // Zone label shown in place of the symbol name on a volatility-gauge mini-
  // tape chip (2026-07-04, user-specified strings, not abbreviations of the
  // zone name) — mirrors volZoneCls's classes.
  function _volZoneLabel(zoneCls) {
    if (zoneCls === 'mt-up')   return 'invst';
    if (zoneCls === 'mt-chop') return 'chop';
    if (zoneCls === 'mt-down') return 'fck';
    return 'none';
  }

  // Solid background+text pill for the zone label (2026-07-04) — same
  // colors as the side panel's .msr-gauge-g/-a/-r badge (macro_areas.js /
  // styles.css), not just colored text.
  function _volZoneBadgeStyle(zoneCls) {
    if (zoneCls === 'mt-up')   return { bg: '#dcfce7', fg: '#166534' };
    if (zoneCls === 'mt-chop') return { bg: '#fef9c3', fg: '#854d0e' };
    if (zoneCls === 'mt-down') return { bg: '#fee2e2', fg: '#991b1b' };
    return { bg: '#f3f4f6', fg: '#6b7280' };
  }

  function escHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  // ---- cell helpers -------------------------------------------------------

  function itemTipObj(item, chipLabel, valStr, chgStr, arrow, cls) {
    const sym  = item.symbol || item.metric_key || '';
    const fmtN = (v) => v != null ? fmtValue(v, item.value_format || 'price') : null;
    return {
      dname:        item.label || chipLabel,
      sym:          sym,
      price:        valStr,
      pct:          chgStr,
      arrow:        arrow,
      pctCls:       cls,
      outlook:      item.rr_outlook || '',
      price_source: item.source || '',
      rr_source:    (item.rr_buy != null && item.rr_sell != null) ? 'hist_rr' : '',
      asof:         (item.as_of || '').slice(0, 10),
      quote_time:   item.quote_time || '',
      buy:          fmtN(item.rr_buy),
      sell:         fmtN(item.rr_sell),
      open:         fmtN(item.open),
      high:         fmtN(item.high),
      low:          fmtN(item.low),
      stale:        !!item.stale,
    };
  }

  function rrItemTipObj(name, item, chgStr, cls, pct) {
    const sym   = item.symbol || '';
    const fmtN2 = (v) => v != null ? Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : null;
    const price = fmtN2(item.bar_price);
    const arrow = pct != null ? (pct > 0 ? '▲' : pct < 0 ? '▼' : '') : '';
    return {
      dname:        item.label || name,
      sym:          sym,
      price:        price,
      pct:          chgStr,
      arrow:        arrow,
      pctCls:       cls,
      outlook:      item.outlook || '',
      price_source: item.price_source || '',
      rr_source:    (item.buy != null && item.sell != null) ? 'hist_rr' : '',
      asof:         (item.as_of || '').slice(0, 10),
      quote_time:   item.quote_time || '',
      buy:          item.buy  != null ? Number(item.buy).toFixed(2)  : null,
      sell:         item.sell != null ? Number(item.sell).toFixed(2) : null,
      open:         fmtN2(item.open),
      high:         fmtN2(item.high),
      low:          fmtN2(item.low),
      stale:        false,
    };
  }

  // ---- rich tooltip -------------------------------------------------------

  let _tipEl = null;

  function _ensureTip() {
    if (_tipEl) return _tipEl;
    _tipEl = document.createElement('div');
    _tipEl.id = 'mtChipTip';
    Object.assign(_tipEl.style, {
      position: 'fixed', zIndex: '9999', pointerEvents: 'none',
      background: '#fff', border: '1px solid #dde', borderRadius: '8px',
      boxShadow: '0 4px 16px rgba(0,0,0,0.13)', padding: '10px 13px',
      fontSize: '12px', lineHeight: '1.5', minWidth: '140px', maxWidth: '240px',
      display: 'none', color: '#1e293b', whiteSpace: 'nowrap',
    });
    document.body.appendChild(_tipEl);
    return _tipEl;
  }

  function _buildTipHtml(d) {
    const showSym  = d.sym && d.sym !== d.dname;
    const pctColor = d.pctCls === 'mt-up' ? '#1d9e75' : d.pctCls === 'mt-down' ? '#d4537e' : '#888';
    const olColor  = (window.outlookColor && d.outlook)
      ? (window.outlookColor(d.outlook) || '#666') : '#666';

    // as-of: prefer time (HH:MM) + date, else just date
    const timeStr    = d.quote_time ? String(d.quote_time).slice(0, 5) : '';
    const dateStr    = d.asof || '';
    const dateTimeStr = timeStr ? `${dateStr} ${timeStr}` : dateStr;

    let h = `<div style="font-weight:700;font-size:13px;margin-bottom:${showSym?'1px':'4px'};">${escHtml(d.dname)}</div>`;
    if (showSym) {
      h += `<div style="color:#888;font-size:10px;margin-bottom:4px;letter-spacing:0.02em;">${escHtml(d.sym)}</div>`;
    }

    // Price + pct change
    if (d.price && d.price !== '—') {
      h += `<div style="display:flex;align-items:baseline;gap:7px;">` +
           `<span style="font-size:13px;font-weight:600;">${escHtml(d.price)}</span>`;
      if (d.pct) h += `<span style="color:${pctColor};font-size:12px;">${escHtml(d.arrow)}${escHtml(d.pct)}</span>`;
      h += `</div>`;
    } else if (d.pct) {
      h += `<div style="color:${pctColor};font-size:13px;font-weight:600;">${escHtml(d.arrow)}${escHtml(d.pct)}</div>`;
    }

    // As-of date + time + price source
    if (dateTimeStr || d.price_source) {
      const srcTxt = d.price_source ? ` · ${escHtml(d.price_source)}` : '';
      h += `<div style="font-size:10px;color:#aaa;margin-top:2px;margin-bottom:5px;">${dateTimeStr ? 'as of ' + escHtml(dateTimeStr) : ''}${srcTxt}</div>`;
    }

    // Open / High / Low
    const ohlParts = [];
    if (d.open) ohlParts.push(`O: ${escHtml(d.open)}`);
    if (d.high) ohlParts.push(`H: ${escHtml(d.high)}`);
    if (d.low)  ohlParts.push(`L: ${escHtml(d.low)}`);
    if (ohlParts.length) {
      h += `<div style="font-size:11px;color:#555;display:flex;gap:14px;margin-bottom:4px;">${ohlParts.map(p => `<span>${p}</span>`).join('')}</div>`;
    }

    if (d.iv_pct != null || d.iv_pctile != null || d.iv_to_hv != null) {
      const hvColor = (d.iv_to_hv != null && d.iv_to_hv < 0) ? '#dc2626' : '#16a34a';
      const ivTxt   = d.iv_pct    != null ? `<span style="color:#374151;">IV <b>${d.iv_pct}%</b></span>`           : '';
      const ivpTxt  = d.iv_pctile != null ? `<span style="color:#374151;">IVP <b>${d.iv_pctile}%</b></span>`       : '';
      const hvTxt   = d.iv_to_hv  != null ? `<span style="color:${hvColor};">IV/HV <b>${d.iv_to_hv}%</b></span>` : '';
      h += `<div style="display:flex;gap:10px;align-items:center;font-size:11px;margin-bottom:3px;">${ivTxt}${ivpTxt}${hvTxt}</div>`;
    }
    if (d.outlook) {
      h += `<div style="font-size:11px;color:${olColor};">Outlook: ${escHtml(d.outlook)}</div>`;
    }
    if (d.buy && d.sell) {
      const rrSrc = d.rr_source ? ` <span style="color:#aaa;font-size:10px;">· ${escHtml(d.rr_source)}</span>` : '';
      h += `<div style="margin-top:3px;font-size:11px;color:#666;">Range: ${escHtml(d.buy)} – ${escHtml(d.sell)}${rrSrc}</div>`;
    }
    if (d.stale) h += `<div style="margin-top:3px;font-size:10px;color:#f97316;">⚠ stale</div>`;
    return h;
  }

  function _posTip(e) {
    if (!_tipEl || _tipEl.style.display === 'none') return;
    const tw = _tipEl.offsetWidth, th = _tipEl.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + tw > window.innerWidth  - 8) x = e.clientX - tw - 8;
    if (y + th > window.innerHeight - 8) y = e.clientY - th - 8;
    _tipEl.style.left = x + 'px';
    _tipEl.style.top  = y + 'px';
  }

  function _showTip(e, chip) {
    const raw = chip.dataset.tip;
    if (!raw) return;
    let d;
    try { d = JSON.parse(raw); } catch { return; }
    const el = _ensureTip();
    el.innerHTML = _buildTipHtml(d);
    el.style.display = 'block';
    _posTip(e);
  }

  function _hideTip() { if (_tipEl) _tipEl.style.display = 'none'; }

  function _attachTooltip(container) {
    container.addEventListener('mouseover',  (e) => { const c = e.target.closest('.rr-chip'); if (c) _showTip(e, c); else _hideTip(); });
    container.addEventListener('mousemove',  _posTip);
    container.addEventListener('mouseleave', _hideTip);
  }

  // ---- mini candlestick SVG -----------------------------------------------

  function _candleSvg(o, h, l, c) {
    if (o == null || h == null || l == null || c == null) return '';
    const range = h - l;
    if (range <= 0) return '';

    // Fixed 7×14 px canvas — VH chosen to match the mt-chg button height (~14px).
    // shape-rendering="crispEdges" disables anti-aliasing on lines/rects for pixel-sharp output.
    const VW = 7, VH = 14, PAD = 1;
    const usable = VH - 2 * PAD;
    const toY = p => Math.round(PAD + usable * (1 - (p - l) / range));

    const color   = c >= o ? '#1d9e75' : '#d4537e';
    const wickTop = toY(h);
    const wickBot = toY(l);
    const bodyTop = toY(Math.max(o, c));
    const bodyH   = Math.max(1, toY(Math.min(o, c)) - bodyTop);

    return `<svg class="rr-candle" width="${VW}" height="${VH}" viewBox="0 0 ${VW} ${VH}" shape-rendering="crispEdges">` +
      `<line x1="3.5" y1="${wickTop}" x2="3.5" y2="${wickBot}" stroke="${color}" stroke-width="1"/>` +
      `<rect x="2" y="${bodyTop}" width="3" height="${bodyH}" fill="${color}"/>` +
      `</svg>`;
  }

  // ---- shared chip helpers -----------------------------------------------

  // D3: delegate entirely to canonical outlookColor (defined in _common.js,
  // always loaded before market_bar.js). No duplicate palette.
  function outlookBg(outlook) {
    if (!outlook) return '#888';
    const c = window.outlookColor ? window.outlookColor(outlook) : 'inherit';
    return (c && c !== 'inherit') ? c : '#888';
  }

  function rangeBar(buy, sell, cur) {
    if (buy == null || sell == null || sell <= buy || cur == null) {
      return '<div class="rr-rb"></div>';
    }
    const pct = Math.max(0, Math.min(1, (Number(cur) - Number(buy)) / (Number(sell) - Number(buy))));
    const w = Math.round(pct * 100);
    return `<div class="rr-rb"><div class="rr-rb-tick" style="left:${w}%;"></div></div>`;
  }

  function volRangeBar(value, low, high) {
    if (value == null || low == null || high == null) return '<div class="rr-rb"></div>';
    // Zones are equal thirds. Tick uses piecewise scale so it lands inside the right zone:
    //   0 → low  maps to 0–33%,  low → high maps to 33–67%,  high → high×1.5 maps to 67–100%
    let valPct;
    if (value <= 0) {
      valPct = 0;
    } else if (value <= low) {
      valPct = Math.round(value / low * 33);
    } else if (value <= high) {
      valPct = Math.round(33 + (value - low) / (high - low) * 34);
    } else {
      valPct = Math.min(100, Math.round(67 + (value - high) / (high * 0.5) * 33));
    }
    // Colors + tick mark only (2026-07-04) -- the two zone-boundary dot
    // markers are intentionally gone; the colored zones already show the
    // boundaries without them.
    return `<div class="rr-rb vol-rb">` +
      `<div class="vol-z vol-z-g"></div>` +
      `<div class="vol-z vol-z-a"></div>` +
      `<div class="vol-z vol-z-r"></div>` +
      `<div class="rr-rb-tick" style="left:${valPct}%;"></div>` +
      `</div>`;
  }

  function _msGlyphTape(score) {
    if (score == null) return '';
    const s = Number(score);
    if (s > 0) return '<span style="font-size:6px;color:#16a34a;line-height:1;vertical-align:middle;">▲</span>';
    if (s < 0) return '<span style="font-size:6px;color:#dc2626;line-height:1;vertical-align:middle;">▼</span>';
    return '';
  }

  function chipHtml(name, ol, pctStr, pctCls, buy, sell, cur, tipObj, stale, ohlc, volThresh, scoreSym, pairLead) {
    const staleCls = stale ? ' mt-stale' : '';
    // pairLead (2026-07-04): this tile is the "value" half of a value/vol-
    // gauge pair (e.g. SPX before VIX) -- suppress the separator before its
    // paired gauge so the pair reads as one visual unit.
    const pairCls = pairLead ? ' rr-chip-pair-lead' : '';
    const pctBg = pctCls === 'mt-up' ? '#1d9e75' : pctCls === 'mt-down' ? '#d4537e' : '#888';
    const pctBoxStyle = `background:${pctBg};color:#fff;`;
    const symColor = outlookBg(ol);
    const dataTip = tipObj ? ` data-tip="${escHtml(JSON.stringify(tipObj))}"` : '';
    // Inline now (2026-07-04), not the absolutely-positioned corner overlay
    // it used to be -- sits between sym-col and the trailing chip, same as
    // the layout below. #rrTape1 svg.rr-candle in styles.css cancels the
    // base absolute positioning for this context.
    const candle = ohlc ? _candleSvg(ohlc.o, ohlc.h, ohlc.l, ohlc.c) : '';
    const rb = volThresh
      ? volRangeBar(volThresh.value, volThresh.low, volThresh.high)
      : rangeBar(buy, sell, cur);
    const _pg = _msGlyphTape(scoreSym);
    // Volatility-gauge tile (VIX, currently the only BAR_MINI item carrying
    // a volThresh): badge and range bar stay stacked together in rr-chip-
    // sym-col (badge on top, bar below it, 2026-07-04) -- the candle sits
    // BEFORE that whole stack instead of before a trailing chip, since there
    // is no price chip for this tile anymore. Styled as a solid background+
    // text pill matching the side panel's .msr-gauge badge convention, not
    // just colored text. Regular tiles keep their existing order: sym-col
    // (name/bar), then candle, then the trailing %chg chip. data-sym stays
    // the real instrument name for tooltip/click purposes throughout.
    const symHtml = volThresh
      ? (function () {
          const b = _volZoneBadgeStyle(volThresh.zone);
          const badgeStyle = `background:${b.bg}; color:${b.fg}; padding:0 2px; border-radius:3px; display:inline-block; line-height:1.1;`;
          return `<span class="rr-sym" style="${badgeStyle}">${_pg}${escHtml(_volZoneLabel(volThresh.zone))}</span>`;
        })()
      : `<span class="rr-sym" style="color:${symColor};">${_pg}${escHtml(name)}</span>`;
    const symCol = `<div class="rr-chip-sym-col">${symHtml}${rb}</div>`;
    const trailChip = volThresh ? '' : `<span class="mt-chg" style="${pctBoxStyle}">${pctStr}</span>`;
    // mt-candle-trail/mt-candle-lead mark the candle depending on which side
    // of sym-col it's on (2026-07-04) -- trail for regular tiles (candle
    // after sym-col), lead for volatility-gauge tiles (candle before the
    // badge+bar stack, whose chip has padding-left:0 for tight pairing with
    // its value tile) -- so CSS can tune the space on each side separately.
    const body = volThresh
      ? `<span class="mt-candle-lead">${candle}</span>` + symCol
      : symCol + `<span class="mt-candle-trail">${candle}</span>` + trailChip;
    return `<div class="rr-chip${staleCls}${pairCls}" data-sym="${escHtml(name)}"${dataTip} style="cursor:pointer;">` +
      `<div class="rr-chip-body">` +
      body +
      `</div>` +
      `</div>`;
  }

  // ---- build mini-tape row (#rrTape1) -------------------------------------
  // Grouped PAIRS (2026-07-04, user requests) -- pairLead:true on the first
  // tile of a group suppresses the separator before the next tile, so
  // buildMiniTapeHtml renders the group as one visual unit:
  //   S&P(SPX)+VIX, Nasdaq(COMP)+VXN, Dow(DJI)+VXD, Russell(RUT)+RVX,
  //   Gold(GC)+GVZ, Oil(WTI)+OVX  -- one pair per Volatility-area entry in
  //     db/seeds_macro_area.sql (area_key='volatility')
  //   2Y+10Y+MOVE  -- 3-tile group (2Y in front of 10Y, both paired via
  //     chained pairLead flags)
  //   HY+LQD  -- Credit group
  //   BTC, QQQ  -- unpaired, QQQ added after BTC
  //   Dolr(DXY)+Yen(USD/JPY)  -- moved to the very end, now paired
  // GC/WTI/10Y/DXY/HY/BTC identifiers are verbatim from TASK_115's original
  // preflight (DEV_HANDOFF AGENT_WORK_24); COMP/DJI/RUT/VXN/VXD/RVX/GVZ/
  // OVX/MOVE/2Y/LQD/QQQ/Yen(/6J) were confirmed later directly against
  // ref_market_metric/live /api/marketbar/rr-bar. All 'mkt' entries resolve
  // from /api/marketbar (metric_key); 'rr' entries resolve from
  // /api/rr-bar groups.
  const BAR_MINI = [
    // Display labels renamed 2026-07-04 (S&P/Nas/Rus/Gold/Dolr) -- `key` is
    // still the real metric_key used for the /api/marketbar lookup, only
    // the on-tile text changed.
    { label: 'S&P',  source: 'mkt', key: 'SPX',  pairLead: true },   // S&P 500
    { label: 'VIX',  source: 'mkt', key: 'VIX' },   // S&P Vol
    { label: 'Nas',  source: 'mkt', key: 'COMP', pairLead: true },  // Nasdaq Composite
    { label: 'VXN',  source: 'mkt', key: 'VXN' },   // Nasdaq Vol
    { label: 'DJI',  source: 'mkt', key: 'DJI',  pairLead: true },   // Dow
    { label: 'VXD',  source: 'mkt', key: 'VXD' },   // Dow Vol
    { label: 'Rus',  source: 'mkt', key: 'RUT',  pairLead: true },   // Russell 2000
    { label: 'RVX',  source: 'mkt', key: 'RVX' },   // Russell Vol
    { label: 'Gold', source: 'mkt', key: 'GC',   pairLead: true },    // Gold
    { label: 'GVZ',  source: 'mkt', key: 'GVZ' },   // Gold Vol
    { label: 'WTI',  source: 'mkt', key: 'WTI',  pairLead: true },   // Oil
    { label: 'OVX',  source: 'mkt', key: 'OVX' },   // Oil Vol
    // Rates group (2026-07-04): 2Y in front of 10Y, both grouped with MOVE
    // as one 3-tile unit (2Y pairLead removes its border to 10Y; 10Y's
    // existing pairLead removes its border to MOVE).
    { label: '2Y',   source: 'rr',  group: 'Rates',  symbol: 'DGS2:FRED', pairLead: true }, // 2Y Treasury
    { label: '10Y',  source: 'rr',  group: 'Rates',  symbol: 'TNX:CGI', pairLead: true }, // Bond/Treasury
    // MOVE: /api/marketbar currently returns vol_low/vol_high = null for
    // this metric_key even though ref_vol_threshold has a row for the
    // underlying MOVE:GIF symbol (the side rail's Bond Vol gauge works) —
    // a lookup-key mismatch in the marketbar endpoint, not a missing
    // threshold. Until that's fixed this tile will show the "None" zone
    // badge; not blocking, flagged for a follow-up.
    { label: 'MOVE', source: 'mkt', key: 'MOVE' },  // Bond Vol
    // Credit group (2026-07-04): LQD grouped with HY (HY pairLead removes
    // the border to LQD).
    { label: 'HY',   source: 'rr',  group: 'Credit', symbol: 'HYG', pairLead: true },
    { label: 'LQD',  source: 'rr',  group: 'Credit', symbol: 'LQD' },
    { label: 'BTC',  source: 'rr',  group: 'Crypto', symbol: '/BTC' },
    // QQQ (2026-07-04): added after BTC. Needed a new ref_market_metric seed
    // row (db/seeds_market_metric.sql) + _METRIC_TO_RR_SYMBOL entry
    // (api/routers/marketbar.py) since it wasn't exposed by either endpoint
    // before, despite drv_quote already having real data for it.
    { label: 'QQQ',  source: 'mkt', key: 'QQQ' },
    // Dollar group (2026-07-04): moved to the very end, now grouped with
    // USD/JPY (Dolr pairLead removes the border to it). /6J is the FX
    // group's dollar-yen futures entry (label "$JPY" in /api/rr-bar).
    { label: 'Dolr', source: 'mkt', key: 'DXY', pairLead: true },
    { label: 'Yen',  source: 'rr',  group: 'FX', symbol: '/6J' },
  ];

  function _miniChipFromMkt(spec, item) {
    const volThresh = item.vol_low != null
      ? { low: item.vol_low, high: item.vol_high, value: item.value,
          zone: volZoneCls(item.value, item.vol_low, item.vol_high) } : null;
    const cls    = dirClass(item.chg_pct, item.metric_key);
    const chgStr = fmtChgPct(item.chg_pct);
    const arrow  = dirArrow(item.chg_pct);
    const valStr = fmtValue(item.value, item.value_format);
    const pctStr = volThresh ? valStr : (chgStr || valStr);
    const tipObj = itemTipObj(item, spec.label, valStr, chgStr, arrow, cls);
    const ohlc   = (item.open != null && item.high != null && item.low != null)
      ? { o: item.open, h: item.high, l: item.low, c: item.value } : null;
    return chipHtml(spec.label, item.rr_outlook, pctStr, cls,
                     item.rr_buy, item.rr_sell, item.value, tipObj, item.stale, ohlc, volThresh,
                     item.monthly_score ?? null, spec.pairLead);
  }

  function _miniChipFromRr(spec, item) {
    const volThresh = item.vol_low != null
      ? { low: item.vol_low, high: item.vol_high, value: item.bar_price,
          zone: volZoneCls(item.bar_price, item.vol_low, item.vol_high) } : null;
    const pct    = item.pct != null ? Number(item.pct) : null;
    // Pass the mini-tape label (not null) so INVERTED (HY) actually applies —
    // pre-existing bug in the retired bar2/3 path always passed null here.
    const cls    = dirClass(pct, spec.label);
    const chgStr = volThresh
      ? (item.bar_price != null ? Number(item.bar_price).toFixed(2) : '—')
      : (pct != null ? Math.abs(pct).toFixed(1) + '%' : '—');
    const tipObj = rrItemTipObj(spec.label, item, chgStr, cls, pct);
    const ohlc   = (item.open != null && item.high != null && item.low != null && item.bar_price != null)
      ? { o: item.open, h: item.high, l: item.low, c: item.bar_price } : null;
    return chipHtml(spec.label, item.outlook, chgStr, cls,
                     item.buy, item.sell, item.bar_price, tipObj, false, ohlc, volThresh,
                     item.monthly_score, spec.pairLead);
  }

  // Cluster consecutive pairLead-chained tiles into one <div
  // class="mt-group"> so CSS can give each group a shared background box
  // (2026-07-04, kept after an A/B compare against a font-only tweak) --
  // makes grouping an explicit visual cue instead of relying on the mere
  // absence of a border to imply it. A tile with pairLead:true continues
  // the current group; a tile without it closes the group.
  function buildMiniTapeHtml(mktData, rrData) {
    const mktItems = (mktData && mktData.items) || [];
    const byKey    = Object.fromEntries(mktItems.map(it => [it.metric_key, it]));
    const rrGroups = (rrData && rrData.groups) || {};
    const groups = [];
    let current = [];
    for (const spec of BAR_MINI) {
      let cellHtml = null;
      if (spec.source === 'mkt') {
        const item = byKey[spec.key];
        if (item) cellHtml = _miniChipFromMkt(spec, item);
      } else {
        const items = rrGroups[spec.group] || [];
        const item  = items.find(it => it.symbol === spec.symbol);
        if (item) cellHtml = _miniChipFromRr(spec, item);
      }
      if (cellHtml == null) continue;
      current.push(cellHtml);
      if (!spec.pairLead) {
        groups.push(current);
        current = [];
      }
    }
    if (current.length) groups.push(current);
    return groups.map(g => `<div class="mt-group">${g.join('')}</div>`).join('');
  }

  // ---- right-aligned as-of timestamp --------------------------------------
  function _tapeAsOfHtml(mktData) {
    const asOfDate = mktData && mktData.as_of;
    if (!asOfDate) return '';
    const items    = (mktData && mktData.items) || [];
    const withTime = items.find(it => it.quote_time);
    const timeStr  = withTime ? String(withTime.quote_time).slice(0, 5) : '';
    // mm/dd (2026-07-04) instead of the raw YYYY-MM-DD -- same date-shortening
    // convention already used for the econ-panel rows below.
    const dateStr  = /^\d{4}-\d{2}-\d{2}$/.test(asOfDate)
      ? asOfDate.slice(5, 7) + '/' + asOfDate.slice(8, 10)
      : asOfDate;
    const label    = timeStr ? `${dateStr} ${timeStr}` : dateStr;
    return `<span class="mt-asof">as of ${escHtml(label)}</span>`;
  }

  // ---- build econ expander panel ----------------------------------------
  function buildEconHtml(macro) {
    const groups = macro.groups || {};
    const entries = Object.entries(groups);
    if (!entries.length) return '<span style="color:var(--text-3);font-size:11px;">No econ data available.</span>';

    return entries.map(([groupName, items]) => {
      const rows = (items || []).map(item => {
        let val;
        if (item.latest_value !== null && item.latest_value !== undefined) {
          const n = Number(item.latest_value);
          val = (item.unit === '%')
            ? n.toFixed(2) + '%'
            : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        } else {
          val = '—';
        }

        const chgRaw = (item.chg_abs !== null && item.chg_abs !== undefined) ? Number(item.chg_abs) : null;
        const chgStr = chgRaw !== null
          ? (chgRaw >= 0 ? '+' : '') + chgRaw.toFixed(2)
          : '';
        const chgCls = chgRaw === null ? '' : chgRaw > 0 ? 'mt-up' : chgRaw < 0 ? 'mt-down' : 'mt-flat';

        const pctPart = (item.chg_pct !== null && item.chg_pct !== undefined)
          ? ` (${Number(item.chg_pct).toFixed(2)}%)`
          : '';
        const tip = escHtml(`${item.label} — as of: ${item.latest_date || '?'}${pctPart}`);

        let dateLbl = '--';
        if (item.latest_date && /^\d{4}-\d{2}-\d{2}$/.test(item.latest_date)) {
          const parts = item.latest_date.split('-');
          dateLbl = parts[1] + '/' + parts[2];
        }

        return `<div class="mt-econ-row" title="${tip}">` +
          `<span class="mt-econ-name">${escHtml(item.label)}</span>` +
          `<span class="mt-econ-val">${val}</span>` +
          (chgStr ? `<span class="mt-econ-chg ${chgCls}">${chgStr}</span>` : '') +
          `<span class="mt-econ-date">${dateLbl}</span>` +
          `</div>`;
      }).join('');

      return `<div class="mt-econ-group">` +
        `<div class="mt-econ-group-label">${escHtml(groupName)}</div>` +
        rows +
        `</div>`;
    }).join('');
  }

  // ---- DOM mount --------------------------------------------------------
  let tapeEl = null;

  const TAPE_PAGES = new Set(['/', '/actionable', '/portfolio']);

  function ensureMount() {
    if (tapeEl) return;

    const path = window.location.pathname.replace(/\/+$/, '') || '/';
    if (!TAPE_PAGES.has(path)) return;

    const topbar = document.querySelector('header.topbar');
    if (!topbar) return;

    // Single mini-tape row — curated 8-instrument pulse
    tapeEl = document.createElement('div');
    tapeEl.id = 'rrTape1';
    tapeEl.className = 'market-tape';
    tapeEl.innerHTML = '<span style="color:var(--text-3);padding:0 8px;font-size:11px;">Loading market data…</span>';
    topbar.insertAdjacentElement('afterend', tapeEl);

    // Attach rich tooltip (event delegation — once only)
    _attachTooltip(tapeEl);

    // Wire [data-econ-toggle] buttons → #econPanel (any button with the attribute)
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-econ-toggle]');
      if (!btn) return;
      const panel = document.getElementById('econPanel');
      if (!panel) return;
      const open = panel.classList.toggle('open');
      document.querySelectorAll('[data-econ-toggle]').forEach(b => {
        b.classList.toggle('active', open);
      });
      if (open && !panel.dataset.loaded) loadEcon();
    });
  }

  // ---- fetch & render ---------------------------------------------------
  let _lastMktData = null;
  let _lastRrData  = null;

  function _renderAll() {
    if (_lastMktData && tapeEl)
      tapeEl.innerHTML = buildMiniTapeHtml(_lastMktData, _lastRrData || {}) + _tapeAsOfHtml(_lastMktData);
  }
  window._refreshTapeGlyphs = _renderAll;

  async function loadTape() {
    ensureMount();
    if (!tapeEl) return;

    try {
      const [mktRes, rrRes] = await Promise.all([
        fetch('/api/marketbar'),
        fetch('/api/rr-bar'),
      ]);
      if (!mktRes.ok) throw new Error('HTTP ' + mktRes.status);
      if (!rrRes.ok)  throw new Error('HTTP ' + rrRes.status);
      [_lastMktData, _lastRrData] = await Promise.all([mktRes.json(), rrRes.json()]);
      _renderAll();
    } catch (err) {
      if (tapeEl) {
        tapeEl.innerHTML =
          '<span style="color:var(--bear,#b91c1c);padding:0 8px;font-size:11px;">Market data unavailable</span>';
      }
    }
  }

  async function loadEcon() {
    const panel = document.getElementById('econPanel');
    if (!panel) return;
    try {
      const r = await fetch('/api/macro');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      panel.innerHTML = buildEconHtml(data);
      panel.dataset.loaded = '1';
    } catch (err) {
      if (panel) {
        panel.innerHTML =
          '<span style="color:var(--bear,#b91c1c);font-size:11px;">Econ data unavailable</span>';
      }
    }
  }

  // ---- entry ------------------------------------------------------------
  function init() {
    loadTape();
    setInterval(loadTape, REFRESH_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public tooltip API — lets other scripts (actionable.js, macro_areas.js) reuse
  // the same tooltip + candle + volatility 3-zone range bar (TASK_116: macro_areas.js
  // rail rows port volRangeBar from here instead of duplicating it).
  window.mtTip = {
    showObj: function(e, obj) {
      const el = _ensureTip();
      el.innerHTML = _buildTipHtml(obj);
      el.style.display = 'block';
      _posTip(e);
    },
    move: _posTip,
    hide: _hideTip,
    candleSvg: _candleSvg,
    volRangeBar: volRangeBar,
  };
})();
