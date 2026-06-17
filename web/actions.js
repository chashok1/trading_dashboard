/**
 * actions.js — canonical action vocabulary map.
 * Single source of truth for display labels, BuySell codes, side, and CSS class.
 * Loaded before per-screen scripts (like _common.js).
 *
 * Usage:
 *   const d = actionDisplay('REMOVE');  // { label, code, side, cls }
 *   actionText(d)   // code only: "SA", "HOLD", "SO", or "—"
 *   d.label         // plain-English name for title= tooltip: "SELL ALL"
 */

/* jshint esversion: 6 */
/* global window */

(function () {
  'use strict';

  // Canonical table: any action code (consolidated OR trig) -> display object.
  // Keys are upper-cased for lookup.
  // colorCls: CSS utility class from styles.css token block (act-sell-strong etc.)
  // Use colorCls for color, cls for chip border indicator.
  var _MAP = {
    // -- Sell / Remove ---------------------------------------------------------
    'REMOVE':   { label: 'SELL ALL',     code: 'SA',  side: 'sell',    cls: 'act-chip-remove',   colorCls: 'act-sell-strong' },
    'SA':       { label: 'SELL ALL',     code: 'SA',  side: 'sell',    cls: 'act-chip-remove',   colorCls: 'act-sell-strong' },
    // -- Sell / Reduce ---------------------------------------------------------
    'REDUCE':   { label: 'SELL SOME',    code: 'SS',  side: 'sell',    cls: 'act-chip-reduce',   colorCls: 'act-sell' },
    'SS':       { label: 'SELL SOME',    code: 'SS',  side: 'sell',    cls: 'act-chip-reduce',   colorCls: 'act-sell' },
    'STM':      { label: 'SELL TRIM',    code: 'STM', side: 'sell',    cls: 'act-chip-reduce',   colorCls: 'act-sell' },
    // -- Sell / Overage (synthetic) --------------------------------------------
    // OVER_MAX displays as "SO" per actionText(); label used in tooltips only.
    'OVER_MAX': { label: 'SELL OVERAGE', code: 'SO',  side: 'sell',    cls: 'act-chip-over_max', colorCls: 'act-sell-weak' },
    // -- Sell / Watch ----------------------------------------------------------
    'SO':       { label: 'SELL OVER',    code: 'SO',  side: 'sell',    cls: 'act-chip-reduce',   colorCls: 'act-sell' },
    'SW':       { label: 'SELL WATCH',   code: 'SW',  side: 'sell',    cls: 'act-chip-reduce',   colorCls: 'act-sell-weak' },
    'SWW':      { label: 'SELL WATCH W', code: 'SWW', side: 'sell',    cls: 'act-chip-reduce',   colorCls: 'act-sell-weak' },
    // -- Buy / Increase --------------------------------------------------------
    'INCREASE': { label: 'BUY SOME',     code: 'BS',  side: 'buy',     cls: 'act-chip-increase', colorCls: 'act-buy' },
    'BS':       { label: 'BUY SOME',     code: 'BS',  side: 'buy',     cls: 'act-chip-increase', colorCls: 'act-buy' },
    'BM':       { label: 'BUY MORE',     code: 'BM',  side: 'buy',     cls: 'act-chip-increase', colorCls: 'act-buy-strong' },
    // -- Buy / Add to min ------------------------------------------------------
    'ADD':      { label: 'BUY TO MIN',   code: 'BMN', side: 'buy',     cls: 'act-chip-add',      colorCls: 'act-buy-weak' },
    'BMN':      { label: 'BUY TO MIN',   code: 'BMN', side: 'buy',     cls: 'act-chip-add',      colorCls: 'act-buy-weak' },
    'BW':       { label: 'BUY WATCH',    code: 'BW',  side: 'buy',     cls: 'act-chip-add',      colorCls: 'act-buy-weak' },
    'BSW':      { label: 'BUY SOME W',   code: 'BSW', side: 'buy',     cls: 'act-chip-add',      colorCls: 'act-buy-weak' },
    // -- Hold ------------------------------------------------------------------
    'HOLD':     { label: 'HOLD',         code: 'HOLD', side: 'neutral', cls: 'act-chip-hold',    colorCls: 'act-neutral' },
    'N':        { label: 'NEUTRAL',      code: 'N',    side: 'neutral', cls: 'act-chip-hold',    colorCls: 'act-neutral' },
    'BN':       { label: 'HOLD',         code: 'HOLD', side: 'neutral', cls: 'act-chip-hold',    colorCls: 'act-neutral' },
    'SN':       { label: 'HOLD',         code: 'HOLD', side: 'neutral', cls: 'act-chip-hold',    colorCls: 'act-neutral' },
    // -- None / null -----------------------------------------------------------
    'NONE':     { label: 'None',         code: '',     side: 'neutral', cls: 'act-chip-none',    colorCls: 'act-neutral' },
  };

  var _DEFAULT = { label: 'None', code: '', side: 'neutral', cls: 'act-chip-none', colorCls: 'act-neutral' };

  /**
   * actionDisplay(code) -> { label, code, side, cls }
   * Pass any consolidated_action or trig_action value (case-insensitive).
   * null/undefined/''/NONE all resolve to the dash entry.
   */
  function actionDisplay(code) {
    if (!code) return _DEFAULT;
    return _MAP[('' + code).toUpperCase()] || { label: '' + code, code: '', side: 'neutral', cls: 'act-chip-none', colorCls: 'act-neutral' };
  }

  /**
   * actionText(displayObj) -> cryptic code only (plain-English label in d.label for tooltips).
   *   SA/STM/SS/BMN/BS/BM/SO/SW/etc. -> the code string
   *   HOLD/neutral with no code       -> "HOLD"
   *   none/null/empty                 -> "--"
   *
   * Full plain-English name is d.label — use it in title= attributes.
   */
  function actionText(d) {
    if (!d) return '--';
    if (d.code) return d.code;
    // neutral side with a real label (HOLD) -> "HOLD"
    if (d.side === 'neutral' && d.label && d.label !== 'None') return 'HOLD';
    return '--';
  }

  // Icon map: action code -> { glyph, color }
  var _ICON = {
    // buys (up)
    BM:  { g: '⇈', c: '#14532d' },
    BS:  { g: '↑', c: '#22c55e' },
    BMN: { g: '↥', c: '#16a34a' },
    BW:  { g: '◇', c: '#22c55e' },
    BSW: { g: '◇', c: '#22c55e' },
    HOLD:{ g: '=', c: '#9ca3af' },
    N:   { g: '=', c: '#9ca3af' },
    BN:  { g: '=', c: '#9ca3af' },
    // sells (down)
    SA:  { g: '⇊', c: '#991b1b' },
    SS:  { g: '↓', c: '#ef4444' },
    STM: { g: '↓', c: '#ef4444' },
    SO:  { g: '↧', c: '#ea580c' },
    SW:  { g: '◇', c: '#f97316' },
    SWW: { g: '◇', c: '#f97316' },
    SN:  { g: '=', c: '#9ca3af' },
  };
  var _ICON_NONE = { g: '·', c: '#d1d5db' };

  /**
   * actionIcon(code) -> { glyph, color, code, label, title }
   * Resolves any raw action or alias (ADD->BMN, REMOVE->SA, …) then returns
   * the matching glyph and color for rendering in the Sources column.
   */
  function actionIcon(code) {
    var d = actionDisplay(code);                 // resolves ADD->BMN, REMOVE->SA, ...
    var ic = _ICON[d.code] || (d.side === 'neutral' ? _ICON.HOLD : _ICON_NONE);
    var title = (d.code && d.code !== d.label) ? (d.code + ' - ' + d.label)
                                               : (d.label || 'None');
    return { glyph: ic.g, color: ic.c, code: d.code, label: d.label, title: title };
  }

  // Expose on window for use by per-screen scripts.
  window.actionDisplay = actionDisplay;
  window.actionText    = actionText;
  window.actionIcon    = actionIcon;
  window._ACTION_MAP   = _MAP;  // for debugging / direct key iteration
}());
