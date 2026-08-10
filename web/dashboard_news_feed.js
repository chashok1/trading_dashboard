/* Dashboard-only market news feed, anchored to the bottom of the screen.
 * TradingView "Timeline" widget (feedMode: all_symbols -- general market
 * news, not tied to one symbol), same free embed pattern (script src +
 * JSON config, no API key) as dashboard_tv_chart_tape.js's Ticker Tape.
 * Self-mounting, Dashboard (/) only. Collapsible (chevron), state
 * persisted in localStorage -- a permanent ~250px fixed footer would
 * otherwise always cover some page content.
 * User: "add trending view news feed anchored to the bottom of the
 * screen" (following up on "Is there a free service available to see
 * market news like scrolling bar?").
 */
(function () {
  function _ensureMount() {
    if (window.location.pathname.replace(/\/+$/, '') !== '' && window.location.pathname !== '/') return null;
    var bar = document.getElementById('dashNewsFeed');
    if (bar) return bar;
    bar = document.createElement('div');
    bar.id = 'dashNewsFeed';
    bar.className = 'dash-news-feed';
    document.body.appendChild(bar);
    return bar;
  }

  function _buildTimelineWidget() {
    var container = document.createElement('div');
    container.className = 'tradingview-widget-container';
    var wd = document.createElement('div');
    wd.className = 'tradingview-widget-container__widget';
    container.appendChild(wd);
    var sc = document.createElement('script');
    sc.type = 'text/javascript';
    sc.src = 'https://s3.tradingview.com/external-embedding/embed-widget-timeline.js';
    sc.async = true;
    sc.textContent = JSON.stringify({
      feedMode: 'all_symbols',
      isTransparent: false,
      displayMode: 'compact',
      colorTheme: 'light',
      locale: 'en',
      width: '100%',
      height: '100%',
    });
    container.appendChild(sc);
    return container;
  }

  function _init() {
    var bar = _ensureMount();
    if (!bar) return;
    var collapsed = localStorage.getItem('dashNewsFeed_collapsed') === '1';
    bar.innerHTML =
      '<div class="dash-news-hdr" id="dashNewsHdr">' +
        '<span>Market News</span>' +
        '<span class="dash-news-chevron" id="dashNewsChevron">' + (collapsed ? '&#9652;' : '&#9662;') + '</span>' +
      '</div>' +
      '<div class="dash-news-body" id="dashNewsBody" style="display:' + (collapsed ? 'none' : 'block') + ';"></div>';
    bar.querySelector('#dashNewsBody').appendChild(_buildTimelineWidget());

    document.getElementById('dashNewsHdr').addEventListener('click', function () {
      var body = document.getElementById('dashNewsBody');
      var chev = document.getElementById('dashNewsChevron');
      var nowCollapsed = body.style.display !== 'none';
      body.style.display = nowCollapsed ? 'none' : 'block';
      chev.innerHTML = nowCollapsed ? '&#9652;' : '&#9662;';
      localStorage.setItem('dashNewsFeed_collapsed', nowCollapsed ? '1' : '0');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})();
