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
      _loadChart(body, tvSym);
    }

    document.getElementById(MODAL_ID).style.display = 'flex';
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
