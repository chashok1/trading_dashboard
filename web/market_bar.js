/* Trading Dashboard — global market tape
 *
 * Self-mounting widget. Injects three sticky ribbons below the topbar:
 *   Bar 1 (#rrTape1)  — index/vol pairs + rates + commodities + bonds
 *   Bar 2 (#rrTape2) — ETFs + Commodities  (curated, with group labels)
 *   Bar 3 (#rrTape3)     — Tech + FX + Indexes (curated, with group labels)
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

  const LABEL_SHORT = {
    'Shanghai': 'SSE',  'Nikkei': 'NIKK',  'HY Bond': 'HY',
    'IG Bond':  'IG',   'Dollar': 'USD',    'Bitcoin': 'BTC',
  };

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
    return Math.abs(Number(chg_pct)).toFixed(2) + '%';
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
    const pctColor = d.pctCls === 'mt-up' ? '#2f9e2f' : d.pctCls === 'mt-down' ? '#d83a3a' : '#888';
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

    const color   = c >= o ? '#2f9e2f' : '#d83a3a';
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
    return `<div class="rr-rb vol-rb">` +
      `<div class="vol-z vol-z-g"></div>` +
      `<div class="vol-z vol-z-a"></div>` +
      `<div class="vol-z vol-z-r"></div>` +
      `<div class="vol-dot" style="left:33%;"></div>` +
      `<div class="vol-dot" style="left:67%;"></div>` +
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

  function chipHtml(name, ol, pctStr, pctCls, buy, sell, cur, tipObj, stale, ohlc, volThresh, scoreSym) {
    const staleCls = stale ? ' mt-stale' : '';
    const pctBg = pctCls === 'mt-up' ? '#2f9e2f' : pctCls === 'mt-down' ? '#d83a3a' : '#888';
    const pctBoxStyle = `background:${pctBg};color:#fff;`;
    const zoneColor = volThresh
      ? (volThresh.zone === 'mt-up' ? '#2f9e2f' : volThresh.zone === 'mt-chop' ? '#eab308' : '#d83a3a')
      : null;
    const symColor = zoneColor || outlookBg(ol);
    const dataTip = tipObj ? ` data-tip="${escHtml(JSON.stringify(tipObj))}"` : '';
    const candle = ohlc ? _candleSvg(ohlc.o, ohlc.h, ohlc.l, ohlc.c) : '';
    const rb = volThresh
      ? volRangeBar(volThresh.value, volThresh.low, volThresh.high)
      : rangeBar(buy, sell, cur);
    const _pg = _msGlyphTape(scoreSym);
    return `<div class="rr-chip${staleCls}" data-sym="${escHtml(name)}"${dataTip} style="cursor:pointer;">` +
      `<div class="rr-chip-body">` +
      `<div class="rr-chip-sym-col">` +
      `<span class="rr-sym" style="color:${symColor};">${_pg}${escHtml(name)}</span>` +
      rb +
      `</div>` +
      `<span class="mt-chg" style="${pctBoxStyle}">${pctStr}</span>` +
      `</div>` +
      candle +
      `</div>`;
  }

  // ---- build tape row (bar 1) — explicit labeled groups -----------------
  const BAR1_GROUPS = [
    { label: 'Eq',    keys: ['SPX', 'VIX', 'COMP', 'VXN', 'DJI', 'VXD', 'RUT', 'RVX'] },
    { label: 'FX',    keys: ['DXY'] },
    { label: 'Gold',  keys: ['GC', 'GVZ'] },
    { label: 'Oil',   keys: ['WTI', 'BZ', 'OVX'] },
  ];

  function buildTapeHtml(data) {
    const items = data.items || [];
    const byKey = Object.fromEntries(items.map(it => [it.metric_key, it]));
    const cells = [];

    for (const grp of BAR1_GROUPS) {
      const grpCells = [];
      for (const key of grp.keys) {
        const item = byKey[key];
        if (!item) continue;
        const volThresh = item.vol_low != null
          ? { low: item.vol_low, high: item.vol_high, value: item.value,
              zone: volZoneCls(item.value, item.vol_low, item.vol_high) } : null;
        const cls       = dirClass(item.chg_pct, item.metric_key);
        const chgStr    = fmtChgPct(item.chg_pct);
        const arrow     = dirArrow(item.chg_pct);
        const valStr    = fmtValue(item.value, item.value_format);
        const pctStr    = volThresh ? valStr : (chgStr || valStr);
        const chipLabel = LABEL_SHORT[item.label] || item.label || item.metric_key;
        const tipObj    = itemTipObj(item, chipLabel, valStr, chgStr, arrow, cls);
        const ohlc1     = (item.open != null && item.high != null && item.low != null)
          ? { o: item.open, h: item.high, l: item.low, c: item.value } : null;
        grpCells.push(chipHtml(chipLabel, item.rr_outlook, pctStr, cls,
                               item.rr_buy, item.rr_sell, item.value, tipObj, item.stale, ohlc1, volThresh,
                               item.monthly_score ?? null));
      }
      if (!grpCells.length) continue;
      cells.push(`<div class="rr-group">${grpCells.join('')}</div>`);
    }

    return cells.join('');
  }

  // ---- build RR bar (bar 2 or 3) — chips with inline group headings ----
  const BAR2_CATS = ['Sectors', 'FX', 'Indexes', 'Rates'];
  const BAR3_CATS = ['Tech', 'ETFs', 'Credit'];
  const CAT_SHORT  = {
    'ETFs': 'ETF', 'Sectors': 'Sect', 'Commodities': 'Cmdty', 'Credit': 'Crd',
    'Rates': 'Rates', 'Tech': 'Tech', 'FX': 'FX', 'Indexes': 'Idx', 'Crypto': 'Crypt', 'MOVE': 'MOVE',
  };

  function buildRrBarHtml(data, cats) {
    const groups = data.groups || {};
    const cells = [];
    for (const cat of cats) {
      const items = groups[cat];
      if (!items || !items.length) continue;
      const chips = [];
      for (const item of items) {
        const volThresh = item.vol_low != null
          ? { low: item.vol_low, high: item.vol_high, value: item.bar_price,
              zone: volZoneCls(item.bar_price, item.vol_low, item.vol_high) } : null;
        const pct    = item.pct != null ? Number(item.pct) : null;
        const cls    = dirClass(pct, null);
        const chgStr = volThresh
          ? (item.bar_price != null ? Number(item.bar_price).toFixed(2) : '—')
          : (pct != null ? Math.abs(pct).toFixed(2) + '%' : '—');
        const name   = LABEL_SHORT[item.label] || item.label || (item.symbol || '').replace(/^\//, '') || '?';
        const tipObj = rrItemTipObj(name, item, chgStr, cls, pct);
        const ohlc2  = (item.open != null && item.high != null && item.low != null && item.bar_price != null)
          ? { o: item.open, h: item.high, l: item.low, c: item.bar_price } : null;
        chips.push(chipHtml(name, item.outlook, chgStr, cls,
                            item.buy, item.sell, item.bar_price, tipObj, false, ohlc2, volThresh,
                            item.monthly_score));
      }
      cells.push(`<div class="rr-group">${chips.join('')}</div>`);
    }
    return cells.join('');
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
  let tapeEl    = null;
  let rrTape2El = null;
  let rrTape3El = null;

  const TAPE_PAGES = new Set(['/', '/actionable', '/portfolio']);

  function ensureMount() {
    if (tapeEl) return;

    const path = window.location.pathname.replace(/\/+$/, '') || '/';
    if (!TAPE_PAGES.has(path)) return;

    const topbar = document.querySelector('header.topbar');
    if (!topbar) return;

    // Bar 1 — market pairs tape
    tapeEl = document.createElement('div');
    tapeEl.id = 'rrTape1';
    tapeEl.className = 'market-tape';
    tapeEl.innerHTML = '<span style="color:var(--text-3);padding:0 8px;font-size:11px;">Loading market data…</span>';
    topbar.insertAdjacentElement('afterend', tapeEl);

    // Bar 2 — ETFs + Commodities
    rrTape2El = document.createElement('div');
    rrTape2El.id = 'rrTape2';
    rrTape2El.className = 'rr-tape';
    rrTape2El.innerHTML = '<span style="color:var(--text-3);padding:0 8px;font-size:11px;">Loading…</span>';
    tapeEl.insertAdjacentElement('afterend', rrTape2El);

    // Bar 3 — Tech + FX + Indexes
    rrTape3El = document.createElement('div');
    rrTape3El.id = 'rrTape3';
    rrTape3El.className = 'rr-tape';
    rrTape3El.innerHTML = '<span style="color:var(--text-3);padding:0 8px;font-size:11px;">Loading…</span>';
    rrTape2El.insertAdjacentElement('afterend', rrTape3El);

    // Attach rich tooltip to all three tape containers (event delegation — once only)
    _attachTooltip(tapeEl);
    _attachTooltip(rrTape2El);
    _attachTooltip(rrTape3El);

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
      tapeEl.innerHTML = buildTapeHtml(_lastMktData) + buildRrBarHtml(_lastRrData || {}, ['Commodities', 'Crypto']);
    if (_lastRrData && rrTape2El) rrTape2El.innerHTML = buildRrBarHtml(_lastRrData, BAR2_CATS);
    if (_lastRrData && rrTape3El) rrTape3El.innerHTML = buildRrBarHtml(_lastRrData, BAR3_CATS);
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

  async function loadRrBar() {
    ensureMount();
    if (!rrTape2El || !rrTape3El) return;
    try {
      const r = await fetch('/api/rr-bar');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      _lastRrData = await r.json();
      rrTape2El.innerHTML = buildRrBarHtml(_lastRrData, BAR2_CATS);
      rrTape3El.innerHTML = buildRrBarHtml(_lastRrData, BAR3_CATS);
    } catch (err) {
      const msg = '<span style="color:var(--bear,#b91c1c);padding:0 8px;font-size:11px;">RR data unavailable</span>';
      if (rrTape2El)  rrTape2El.innerHTML  = msg;
      if (rrTape3El) rrTape3El.innerHTML = msg;
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
    loadRrBar();
    setInterval(() => { loadTape(); loadRrBar(); }, REFRESH_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public tooltip API — lets other scripts (actionable.js) reuse the same tooltip + candle
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
  };
})();
