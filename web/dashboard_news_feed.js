/* Dashboard-only one-line scrolling market news ticker, anchored to the
 * bottom of the screen. Sourced from GET /api/market-news (Yahoo Finance
 * RSS, server-side fetch+cache -- see api/routers/health.py). Pure CSS
 * marquee (translateX keyframe animation, content duplicated once for a
 * seamless loop) -- TradingView's own free news widgets (Top Stories/
 * Timeline) turned out to be vertical-list format only, no one-line
 * scrolling option, so this replaces that first attempt entirely.
 * Self-mounting, Dashboard (/) only. Collapsible (small toggle at the
 * right end), state persisted in localStorage.
 * User: "Is there a free service available to see market news like
 * scrolling bar?" -> "add trending view news feed anchored to the bottom
 * of the screen." -> "i need one line scrolling news."
 */
(function () {
  var fetchJson = window.fetchJson || async function (url) {
    var r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  var esc = window.escapeHtml || function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

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

  function _itemsHtml(items) {
    return items.map(function (it) {
      var src = it.source ? '<span class="dash-news-src">' + esc(it.source) + '</span> ' : '';
      return it.link
        ? '<a class="dash-news-item" href="' + esc(it.link) + '" target="_blank" rel="noopener">' + src + esc(it.title) + '</a>'
        : '<span class="dash-news-item">' + src + esc(it.title) + '</span>';
    }).join('<span class="dash-news-sep">&#8226;</span>');
  }

  async function _load() {
    var track = document.getElementById('dashNewsTrack');
    if (!track) return;
    try {
      var data = await fetchJson('/api/market-news?limit=20');
      var items = data.items || [];
      if (!items.length) {
        track.innerHTML = '<span class="dash-news-item">No news available.</span>';
        return;
      }
      // Content duplicated once (with a separator bridging the two copies)
      // so the translateX(-50%) loop has no visible seam -- the second
      // copy scrolls into view exactly as the first scrolls out.
      var html = _itemsHtml(items);
      track.innerHTML = html + '<span class="dash-news-sep">&#8226;</span>' + html;
      // Animation duration scales with content length so a longer headline
      // set doesn't feel rushed and a shorter one doesn't crawl -- rough
      // reading-speed estimate (~8 chars/sec), floored at 30s.
      var dur = Math.max(30, Math.round(track.textContent.length / 8));
      track.style.animationDuration = dur + 's';
    } catch (e) {
      track.innerHTML = '<span class="dash-news-item">News unavailable.</span>';
    }
  }

  function _init() {
    var bar = _ensureMount();
    if (!bar) return;
    var collapsed = localStorage.getItem('dashNewsFeed_collapsed') === '1';
    bar.innerHTML =
      '<span class="dash-news-label">News</span>' +
      '<div class="dash-news-viewport" id="dashNewsViewport" style="display:' + (collapsed ? 'none' : 'flex') + ';">' +
        '<div class="dash-news-track" id="dashNewsTrack"><span class="dash-news-item">Loading&hellip;</span></div>' +
      '</div>' +
      '<button class="dash-news-toggle" id="dashNewsToggle" type="button" title="' + (collapsed ? 'Show' : 'Hide') + ' news">' +
        (collapsed ? '&#9652;' : '&#9662;') +
      '</button>';

    document.getElementById('dashNewsToggle').addEventListener('click', function () {
      var vp = document.getElementById('dashNewsViewport');
      var btn = document.getElementById('dashNewsToggle');
      var nowCollapsed = vp.style.display !== 'none';
      vp.style.display = nowCollapsed ? 'none' : 'flex';
      btn.innerHTML = nowCollapsed ? '&#9652;' : '&#9662;';
      btn.title = (nowCollapsed ? 'Show' : 'Hide') + ' news';
      localStorage.setItem('dashNewsFeed_collapsed', nowCollapsed ? '1' : '0');
    });

    _load();
    // Refresh alongside the server's own 5-minute cache TTL (api/routers/
    // health.py::_MARKET_NEWS_TTL) -- no point polling faster than that.
    setInterval(_load, 5 * 60 * 1000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})();
