/* 2026-10-17 -- SPX realized volatility panel (1 month vs 3 month + SPX daily % change bars), 6 months.
 * Left column of the Dashboard (#spxRvBand), directly below the MKT SIT graph (moved from the right column 2026-10-20).
 * Data: GET /api/cockpit/spx-realized-vol -> rows [date, rv21, rv63, pct]. */
(function () {
  'use strict';
  var L = 28, R = 30, T = 8, B = 18;
  var lastRows = [];
  var ST = 'rv', KEYS = ['m1', 'm3', 'bars'];

  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  // Hover: vertical guide line + floating tooltip with date, 1M, 3M and SPX daily %.
  function attachHover(svg, D, W) {
    if (!svg) return;
    var n = D.length, tip = null, guide = null;
    var NS = 'http://www.w3.org/2000/svg';
    var f = function (v) { return v == null ? '--' : v.toFixed(1) + '%'; };
    function hide() {
      if (tip) { tip.remove(); tip = null; }
      if (guide) { guide.remove(); guide = null; }
    }
    svg.addEventListener('mouseleave', hide);
    svg.addEventListener('mousemove', function (ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width * W;
      var i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
      var row = D[i], gx = L + (W - L - R) * i / (n - 1);
      var vb = svg.viewBox.baseVal;
      if (!guide) {
        guide = document.createElementNS(NS, 'line');
        guide.setAttribute('stroke', '#888'); guide.setAttribute('stroke-dasharray', '3 3');
        guide.setAttribute('pointer-events', 'none');
        svg.appendChild(guide);
      }
      guide.setAttribute('x1', gx); guide.setAttribute('x2', gx);
      guide.setAttribute('y1', T); guide.setAttribute('y2', vb.height - B);
      if (!tip) {
        tip = document.createElement('div');
        tip.className = 'spxrv-tip';
        document.body.appendChild(tip);
      }
      var hid = SeriesToggle.hidden(ST);
      tip.innerHTML = '<b>' + row[0] + '</b>' +
        (hid.m1 ? '' : '<br><span style="color:#2b2bf0">&#9632;</span> 1-month: ' + f(row[1])) +
        (hid.m3 ? '' : '<br><span style="color:#ff5a14">&#9632;</span> 3-month: ' + f(row[2])) +
        (hid.bars ? '' : '<br><span style="color:#9a9a9a">&#9632;</span> SPX day: ' + (row[3] == null ? '--' : (row[3] > 0 ? '+' : '') + row[3].toFixed(2) + '%'));
      var tw = tip.offsetWidth, left = ev.clientX + 14;
      if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - 14;
      tip.style.left = Math.max(4, left) + 'px';
      tip.style.top = Math.max(4, ev.clientY - 20) + 'px';
    });
  }

  // Vol-funds signal: SELLING when 1M is above 3M AND 1M is higher than 5 sessions ago (null if not enough data).
  function signal(rows) {
    var D = rows.filter(function (r) { return r[1] != null && r[2] != null; });
    if (D.length < 6) return null;
    var now = D[D.length - 1], chg = now[1] - D[D.length - 6][1];
    return { now: now, chg: chg, sell: now[1] > now[2] && chg > 0 };
  }

  function draw(D, W, H, fs) {
    var n = D.length;
    var x = function (i) { return L + (W - L - R) * i / (n - 1); };
    var hid = SeriesToggle.hidden(ST), on = function (k) { return !hid[k]; };
    var showL = on('m1') || on('m3'), showR = on('bars');
    var vals = [], all = [];
    D.forEach(function (r) {
      if (r[1] != null) all.push(r[1]);
      if (r[2] != null) all.push(r[2]);
      if (on('m1') && r[1] != null) vals.push(r[1]);
      if (on('m3') && r[2] != null) vals.push(r[2]);
    });
    if (!vals.length) vals = all;   // both lines hidden: scale from the full range so the bars axis still lines up
    if (n < 2 || !vals.length) return '<div class="msr-loading">No SPX volatility history yet.</div>';
    var lo = Math.floor(Math.min.apply(null, vals) / 5) * 5 - 5, hi = Math.ceil(Math.max.apply(null, vals) / 5) * 5 + 5;
    var y = function (v) { return T + (H - T - B) * (1 - (v - lo) / (hi - lo)); };
    var pc = D.map(function (r) { return r[3]; }).filter(function (v) { return v != null; });
    var ma = Math.max.apply(null, pc.map(Math.abs).concat([0.5]));
    var rlo = -Math.ceil(ma * 1.8), rhi = Math.ceil(ma * 2.6);
    var ry = function (v) { return T + (H - T - B) * (1 - (v - rlo) / (rhi - rlo)); };
    var s = '';
    if (showL) {
      for (var v = Math.ceil(lo / 10) * 10; v <= hi; v += 10) {
        s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--border,#e5e5e2)"/>' +
          '<text x="' + (L - 4) + '" y="' + (y(v) + 4) + '" text-anchor="end" font-size="' + fs + '" fill="currentColor">' + v + '</text>';
      }
    }
    if (showR) {
      for (var rv = Math.ceil(rlo / 2) * 2; rv <= rhi; rv += 2) {
        if (!showL) s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + ry(rv) + '" y2="' + ry(rv) + '" stroke="var(--border,#e5e5e2)"/>';
        s += '<text x="' + (W - R + 4) + '" y="' + (ry(rv) + 4) + '" font-size="' + fs + '" fill="#7a1fa2">' + rv + '</text>';
      }
    }
    var bw = Math.max(1, (W - L - R) / n * 0.7);
    D.forEach(function (r, i) {
      if (!showR || r[3] == null) return;
      var y0 = ry(0), y1 = ry(r[3]);
      s += '<rect x="' + (x(i) - bw / 2).toFixed(1) + '" y="' + Math.min(y0, y1).toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + Math.max(0.5, Math.abs(y1 - y0)).toFixed(1) + '" fill="#9a9a9a" opacity="0.7"/>';
    });
    var line = function (k, color, w) {
      var p = '', on = false;
      D.forEach(function (r, i) {
        if (r[k] == null) return;
        p += (on ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[k]).toFixed(1); on = true;
      });
      return '<path d="' + p + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
    };
    if (on('m1')) s += line(1, '#2b2bf0', 1.5);
    if (on('m3')) s += line(2, '#ff5a14', 2.5);
    for (var t = 0; t < 4; t++) {
      var i = Math.round((n - 1) * t / 3), pp = D[i][0].split('-');
      s += '<text x="' + x(i) + '" y="' + (H - 4) + '" text-anchor="' + (t === 0 ? 'start' : t === 3 ? 'end' : 'middle') +
        '" font-size="' + fs + '" fill="currentColor">' + pp[1] + '/' + pp[2] + '/' + pp[0].slice(2) + '</text>';
    }
    var last = D[n - 1];
    var f = function (v) { return v == null ? '--' : v.toFixed(1) + '%'; };
    var head = '<div class="spxrv-head"><span class="spxrv-ttl">SPX Realized Vol</span>' +
      '<span class="spxrv-k">' + SeriesToggle.item(ST, 'm1', '<i style="background:#2b2bf0"></i>1M ' + f(last[1])) + '</span>' +
      '<span class="spxrv-k">' + SeriesToggle.item(ST, 'm3', '<i style="background:#ff5a14"></i>3M ' + f(last[2])) + '</span>' +
      '<span class="spxrv-k">' + SeriesToggle.item(ST, 'bars', '<i style="background:#9a9a9a"></i>SPX daily %') + '</span>' +
      (fs <= 11 && signal(D) && signal(D).sell ? '<span class="spxrv-warn" title="1M realized vol is above 3M and rising: volatility-control, CTA and risk-parity funds are selling stocks. Risk Dial gauge is ON.">&#9888; vol funds selling</span>' : '') + '</div>';
    return head + '<svg viewBox="0 0 ' + W + ' ' + H + '" class="spxrv-svg' + (fs > 11 ? '' : ' spxrv-click') + '" role="img" aria-label="SPX 1-month vs 3-month realized volatility">' + s + '</svg>';
  }

  function renderPanel() {
    var body = document.getElementById('spxRvBody');
    if (!body) return;
    body.innerHTML = draw(lastRows, 600, 250, 11);
    attachHover(body.querySelector('svg'), lastRows, 600);
  }

  async function load() {
    var body = document.getElementById('spxRvBody');
    if (!body) return;
    try {
      var d = currentDate();
      var res = await fetch('/api/cockpit/spx-realized-vol' + (d ? '?date=' + encodeURIComponent(d) : ''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      lastRows = (await res.json()).rows || [];
      renderPanel();
    } catch (e) {
      body.innerHTML = '<div class="msr-loading">SPX volatility unavailable.</div>';
    }
  }

  // Plain-English guide under the popup chart (generic background from the Hedgeye Market Situation Report, MSR 2.0).
  function descHtml() {
    return '<div class="cr-desc cr-desc-lg">' +
      '<p><b>What the lines show.</b> <b style="color:#2b2bf0">1M (blue)</b> and <b style="color:#ff5a14">3M (orange)</b> are realized volatility: how much the S&amp;P 500 has actually moved over the last month and the last 3 months, shown as a yearly percentage. The gray bars are the index&#39;s daily % change, so a big bar is a big up or down day.</p>' +
      '<p><b>Realized vs implied.</b> Realized volatility looks backward: what the market really did. Implied volatility (the VIX is the best known) looks forward: what option prices say the market expects. <span class="cr-key">A high realized number means the market has been moving a lot, whatever options were expecting.</span></p>' +
      '<p><b>Why this chart matters: systematic funds.</b> A large group of funds does not pick stocks by looking at the business or the economy. They follow rules based on volatility: <b>volatility-control funds</b> (they size their stock holdings to hold the fund&#39;s risk steady), <b>CTAs</b> (trend-following funds that trade futures) and <b>risk parity funds</b> (they spread money so each asset carries equal risk, often with borrowed money). <span class="cr-key">When volatility rises they mechanically sell stocks, and when it falls they mechanically buy.</span> The rules ignore price, news and sentiment.</p>' +
      '<p><b>Which line they use.</b> Volatility-control funds typically use the <b>higher</b> of the 1-month and 3-month readings to decide how much to hold. <span class="cr-key">So the higher of the two lines is the one that counts.</span></p>' +
      '<ul>' +
      '<li><b>Both lines low and flat:</b> a calm market. These funds are holding a lot of stocks and have little reason to change.</li>' +
      '<li><b>1M climbs above 3M:</b> a recent burst of big moves. The 1M line reacts first, and once it is the higher line it sets the funds&#39; risk, so they sell as it keeps rising. <i>The selling follows the higher line going up, not the crossing itself: if 1M is above 3M but falling, the funds are buying, not selling.</i></li>' +
      '<li><b>Both lines high:</b> the funds stay light on stocks. They cannot buy back much until the readings come down.</li>' +
      '<li><b>Lines falling:</b> the funds can add stocks again, which can support the market. It happens gradually, as the big days age out of the window.</li>' +
      '</ul>' +
      '<p><b>Why a calm spell can lift the market.</b> Each day the oldest day drops out of the 1-month and 3-month windows. When that day was a big move, the reading falls even if today is quiet. <span class="cr-key">A run of quiet days lets realized volatility fall, and that frees these funds to buy.</span></p>' +
      '<p>These are rules of thumb from the Hedgeye Market Situation Report, not results we tested. The size and timing of the fund flows depend on each fund&#39;s own rules.</p>' +
      '</div>';
  }
  // The signal (2026-10-19, user-directed; same rule as the Risk Dial gauge vol_funds_selling in etl/derive_risk_dial.py):
  // vol funds SELL when 1M is above 3M AND 1M is higher than 5 sessions ago.
  function signalHtml() {
    var sg = signal(lastRows);
    if (!sg) return '';
    var now = sg.now, chg = sg.chg, sell = sg.sell;
    var why = '1M ' + now[1].toFixed(1) + '% vs 3M ' + now[2].toFixed(1) + '%, 1M ' + (chg > 0 ? 'up ' : 'down ') + Math.abs(chg).toFixed(1) + ' pts over 5 sessions';
    return '<div class="spxrv-sig ' + (sell ? 'spxrv-sig-sell' : 'spxrv-sig-ok') + '"><b>Vol funds: ' + (sell ? 'SELLING' : 'not selling') + '</b> &mdash; ' + why +
      (sell ? '. 1M is above 3M and still rising: risk-dial warning is ON.' : '. Needs 1M above 3M and rising; the risk-dial warning is off.') + '</div>';
  }
  function modalBodyHtml() { return signalHtml() + draw(lastRows, 1100, 440, 13) + descHtml(); }

  // Click the small chart -> large popup (same overlay/dialog classes as the Cumulative P&L expand modal).
  function closeModal() { var m = document.getElementById('spxRvModal'); if (m) m.remove(); }
  function openModal() {
    if (!lastRows.length) return;
    closeModal();
    var m = document.createElement('div');
    m.id = 'spxRvModal';
    m.className = 'modal-overlay active';
    m.innerHTML = '<div class="modal-content" style="max-width:1100px;"><div class="modal-header"><div><h2 style="margin:0;">SPX Realized Volatility</h2>' +
      '<p style="margin:0;">1 month vs 3 month, ' + lastRows[0][0] + ' to ' + lastRows[lastRows.length - 1][0] + '</p></div>' +
      '<button class="close-btn" type="button" aria-label="Close">&times;</button></div>' +
      '<div class="modal-body">' + modalBodyHtml() + '</div></div>';
    document.body.appendChild(m);
    attachHover(m.querySelector('svg'), lastRows, 1100);
    m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.closest('.close-btn')) closeModal(); });
    SeriesToggle.bind(m, ST, KEYS, refresh);
  }
  // A toggle redraws the panel and, if the popup is open, its body too.
  function refresh() {
    renderPanel();
    var m = document.getElementById('spxRvModal');
    if (m) { m.querySelector('.modal-body').innerHTML = modalBodyHtml(); attachHover(m.querySelector('svg'), lastRows, 1100); }
  }

  function init() {
    var host = document.getElementById('spxRvBody');
    if (host) host.addEventListener('click', function (ev) { if (ev.target.closest('.spxrv-svg')) openModal(); });
    SeriesToggle.bind(host, ST, KEYS, refresh);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', load);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
    setTimeout(load, 700);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
