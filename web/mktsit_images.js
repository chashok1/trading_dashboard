/* Market Situation charts, 2026-10-18 (user-directed): every chart from the latest Market Situation Report email, stacked at the bottom of the dashboard's right column.
 * The panel stays hidden when there are no images; the list is read on page load and refreshed every 15 minutes (as new emails arrive).
 * Data: GET /api/mktsit/images -> {date, images: [file names]}; each image is served by GET /api/mktsit/image?name=... */
(function () {
  'use strict';
  var KEY = 'mktSitImgCollapsed';
  var last = '';

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
      body.innerHTML = imgs.map(function (n) {
        var u = '/api/mktsit/image?name=' + encodeURIComponent(n);
        return '<a href="' + u + '" target="_blank" rel="noopener"><img src="' + u + '" alt="Market Situation chart" loading="lazy" style="display:block;width:100%;height:auto;margin:0 0 8px;"></a>';
      }).join('');
    }).catch(function () {});
  }

  function init() {
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
