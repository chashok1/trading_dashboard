/* Market Situation charts, 2026-10-18 (user-directed): every chart from the latest Market Situation Report email, stacked at the bottom of the dashboard's right column.
 * The panel stays hidden when there are no images; the list is read on page load and refreshed every 15 minutes (as new emails arrive).
 * Data: GET /api/mktsit/images -> {date, images: [file names]}; each image is served by GET /api/mktsit/image?name=... */
(function () {
  'use strict';
  var KEY = 'mktSitImgCollapsed';
  var last = '';
  var urls = [], cur = 0;

  // Click-to-enlarge popup (2026-10-19, user-directed: the charts used to open in a separate browser tab). Centered over the page;
  // arrows / the left and right keys step through the charts, Esc or a click outside the picture closes it.
  function popup() {
    var m = document.getElementById('mktSitPop');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'mktSitPop';
    m.style.cssText = 'display:none; position:fixed; inset:0; z-index:2000; background:rgba(15,15,20,0.82); align-items:center; justify-content:center;';
    m.innerHTML = '<img id="mktSitPopImg" style="max-width:92vw; max-height:90vh; border-radius:6px; box-shadow:0 8px 40px rgba(0,0,0,0.5); background:#fff;">' +
      '<button type="button" id="mktSitPopPrev" title="Previous chart" style="position:absolute; left:14px; top:50%; transform:translateY(-50%); font-size:26px; padding:6px 12px; border:none; border-radius:6px; cursor:pointer;">&#8249;</button>' +
      '<button type="button" id="mktSitPopNext" title="Next chart" style="position:absolute; right:14px; top:50%; transform:translateY(-50%); font-size:26px; padding:6px 12px; border:none; border-radius:6px; cursor:pointer;">&#8250;</button>' +
      '<button type="button" id="mktSitPopX" title="Close (Esc)" style="position:absolute; right:14px; top:12px; font-size:18px; padding:4px 10px; border:none; border-radius:6px; cursor:pointer;">&#10005;</button>' +
      '<span id="mktSitPopN" style="position:absolute; bottom:12px; left:50%; transform:translateX(-50%); color:#fff; font-size:12px;"></span>';
    document.body.appendChild(m);
    m.addEventListener('click', function (e) { if (e.target === m) close(); });
    m.querySelector('#mktSitPopX').addEventListener('click', close);
    m.querySelector('#mktSitPopPrev').addEventListener('click', function (e) { e.stopPropagation(); step(-1); });
    m.querySelector('#mktSitPopNext').addEventListener('click', function (e) { e.stopPropagation(); step(1); });
    document.addEventListener('keydown', function (e) {
      if (m.style.display === 'none') return;
      if (e.key === 'Escape') close(); else if (e.key === 'ArrowLeft') step(-1); else if (e.key === 'ArrowRight') step(1);
    });
    return m;
  }
  function show(i) {
    if (!urls.length) return;
    cur = (i + urls.length) % urls.length;
    var m = popup();
    m.querySelector('#mktSitPopImg').src = urls[cur];
    m.querySelector('#mktSitPopN').textContent = (cur + 1) + ' / ' + urls.length;
    var multi = urls.length > 1 ? '' : 'none';
    m.querySelector('#mktSitPopPrev').style.display = multi; m.querySelector('#mktSitPopNext').style.display = multi;
    m.style.display = 'flex';
  }
  function step(d) { show(cur + d); }
  function close() { var m = document.getElementById('mktSitPop'); if (m) m.style.display = 'none'; }

  function setCollapsed(on) {
    var body = document.getElementById('mktSitImgBody');
    if (body) body.style.display = on ? 'none' : '';
    try { localStorage.setItem(KEY, on ? '1' : '0'); } catch (e) {}
  }

  function load() {
    fetch('/api/mktsit/images').then(function (r) { return r.json(); }).then(function (d) {
      var band = document.getElementById('mktSitImgBand'), body = document.getElementById('mktSitImgBody');
      if (!band || !body) return;
      var imgs = (d && d.images) || [];
      if (!imgs.length) { band.style.display = 'none'; return; }
      var sig = d.date + '|' + imgs.join('|');
      band.style.display = '';
      if (sig === last) return;
      last = sig;
      document.getElementById('mktSitImgTitle').textContent = 'Market Situation charts · ' + d.date;
      urls = imgs.map(function (n) { return '/api/mktsit/image?name=' + encodeURIComponent(n); });
      body.innerHTML = urls.map(function (u, i) {
        return '<img src="' + u + '" data-i="' + i + '" alt="Market Situation chart" title="Click to enlarge" loading="lazy" style="display:block;width:100%;height:auto;margin:0 0 8px;cursor:zoom-in;">';
      }).join('');
    }).catch(function () {});
  }

  function init() {
    var bodyEl = document.getElementById('mktSitImgBody');
    if (bodyEl) bodyEl.addEventListener('click', function (e) {
      var im = e.target.closest ? e.target.closest('img[data-i]') : null;
      if (im) show(Number(im.getAttribute('data-i')));
    });
    var btn = document.getElementById('mktSitImgToggle');
    if (btn) btn.addEventListener('click', function () {
      var body = document.getElementById('mktSitImgBody');
      setCollapsed(!!body && body.style.display !== 'none');
    });
    try { if (localStorage.getItem(KEY) === '1') setCollapsed(true); } catch (e) {}
    load();
    setInterval(load, 15 * 60 * 1000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
