/* Dashboard-only replacement for market_bar.js's mini-tape: a single
   TradingView "Ticker Tape" widget -- one auto-scrolling (marquee) row of
   symbol/price/%change, no per-symbol chart. History: started as per-symbol
   "Mini Chart" cards (160x140px, real sparkline) -> switched to Ticker Tape
   for a smaller footprint -> switched to static "Single Ticker" cards
   because Ticker Tape's marquee scroll has no off switch -> reverted back
   to Ticker Tape per user request (the scrolling was wanted after all).
   Self-mounting, Dashboard (/) only -- Actionable and Portfolio keep the
   original market_bar.js tape unchanged.

   Symbol set and session logic (regular cash-index hours vs. overnight
   futures-equivalent CFDs vs. weekend-closed) are duplicated from
   web/actionable.js's _TV_SYMS_REGULAR/_TV_SYMS_FUTURES/_tvMode rather than
   shared, since actionable.js is off-limits to touch (unrelated in-progress
   work) and there is no existing shared module between the two pages. */

const _DTV_SYMS_REGULAR = [
  { symbol: 'FOREXCOM:SPXUSD',      title: 'S&P 500' },
  { symbol: 'FOREXCOM:NSXUSD',      title: 'Nasdaq 100' },
  { symbol: 'FOREXCOM:DJI',         title: 'Dow Jones' },
  { symbol: 'FOREXCOM:US2000',      title: 'Russell 2K' },
  { symbol: 'CAPITALCOM:VIX',       title: 'VIX' },
  { symbol: 'CAPITALCOM:DXY',       title: 'Dollar' },
  { symbol: 'TVC:GOLD',             title: 'Gold' },
  { symbol: 'TVC:USOIL',            title: 'WTI Crude' },
  { symbol: 'BITSTAMP:BTCUSD',      title: 'Bitcoin' },
  { symbol: 'FX:EURUSD',            title: 'EUR/USD' },
  { symbol: 'FX:USDJPY',            title: 'USD/JPY' },
];

const _DTV_SYMS_FUTURES = [
  { symbol: 'FOREXCOM:SPXUSD',      title: 'S&P Fut' },
  { symbol: 'FOREXCOM:NSXUSD',      title: 'Nasdaq Fut' },
  { symbol: 'FOREXCOM:DJI',         title: 'Dow Fut' },
  { symbol: 'FOREXCOM:US2000',      title: 'Russell Fut' },
  { symbol: 'CAPITALCOM:VIX',       title: 'VIX' },
  { symbol: 'CAPITALCOM:DXY',       title: 'Dollar' },
  { symbol: 'TVC:GOLD',             title: 'Gold' },
  { symbol: 'TVC:USOIL',            title: 'WTI Crude' },
  { symbol: 'BITSTAMP:BTCUSD',      title: 'Bitcoin' },
  { symbol: 'FX:EURUSD',            title: 'EUR/USD' },
  { symbol: 'FX:USDJPY',            title: 'USD/JPY' },
];

// Same session-window definition as actionable.js::_tvMode -- kept
// byte-for-byte equivalent so behavior matches across both pages.
function _dtvMode() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short', hour: 'numeric', minute: 'numeric', hour12: false,
  }).formatToParts(new Date());
  const get = t => (parts.find(p => p.type === t) || {}).value || '';
  const day = get('weekday');
  const mins = parseInt(get('hour'), 10) * 60 + parseInt(get('minute'), 10);

  if (day === 'Sat') return 'none';
  if (day === 'Sun' && mins < 1080) return 'none';
  if (day === 'Fri' && mins >= 1020) return 'none';
  if (['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].includes(day) && mins >= 570 && mins < 960) return 'regular';
  return 'futures';
}

function _dtvBuildTickerTape(syms) {
  const container = document.createElement('div');
  container.className = 'tradingview-widget-container';
  const wd = document.createElement('div');
  wd.className = 'tradingview-widget-container__widget';
  container.appendChild(wd);
  const sc = document.createElement('script');
  sc.type = 'text/javascript';
  sc.src = 'https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js';
  sc.async = true;
  sc.textContent = JSON.stringify({
    symbols: syms.map(s => ({ proName: s.symbol, title: s.title })),
    colorTheme: 'light', isTransparent: false, showSymbolLogo: false,
    displayMode: 'compact', locale: 'en',
  });
  container.appendChild(sc);
  return container;
}

function _dtvEnsureMount() {
  if (window.location.pathname.replace(/\/+$/, '') !== '' && window.location.pathname !== '/') return null;
  const topbar = document.querySelector('header.topbar');
  if (!topbar) return null;
  let tape = document.getElementById('dtvChartTape');
  if (tape) return tape;
  tape = document.createElement('div');
  tape.id = 'dtvChartTape';
  tape.className = 'tv-chart-tape';
  topbar.insertAdjacentElement('afterend', tape);
  return tape;
}

function _dtvInit() {
  const tape = _dtvEnsureMount();
  if (!tape) return;

  const mode = _dtvMode();
  if (mode === 'none') {
    tape.style.display = 'none';
    return;
  }
  tape.style.display = '';
  tape.innerHTML = '';
  const syms = mode === 'regular' ? _DTV_SYMS_REGULAR : _DTV_SYMS_FUTURES;
  tape.appendChild(_dtvBuildTickerTape(syms));
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _dtvInit);
} else {
  _dtvInit();
}
