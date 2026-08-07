/* Exposure drill-down modal -- shared by two triggers:
     - a fired gauge row on the Risk Dial card (openGaugeExposureModal)
     - a Factor Scorecard row, band 3 of the cockpit grid (openFactorExposureModal)
   Both card/table only ever show a 1-line $/% total; this shows the full
   position list behind it. Self-contained: injects its own DOM on first
   open, same pattern as chart_modal.js (Escape / overlay-click / X to
   close). The two backend responses differ slightly (gauge exposure-detail
   has label/categories/tag; factor exposure-detail has axis/category, no
   tag) -- _renderData() normalizes both into the same table + bar chart. */
(function () {
  var MODAL_ID = 'gaugeExpModal';

  function _ensure() {
    if (document.getElementById(MODAL_ID)) return;
    var el = document.createElement('div');
    el.id = MODAL_ID;
    el.className = 'gauge-modal-backdrop';
    el.setAttribute('aria-modal', 'true');
    el.setAttribute('role', 'dialog');
    el.innerHTML = [
      '<div class="gm-overlay" id="gmOverlay"></div>',
      '<div class="gauge-modal">',
      '  <div class="gm-head">',
      '    <div>',
      '      <div class="gm-title" id="gmTitle">&nbsp;</div>',
      '      <div class="gm-sub" id="gmSub"></div>',
      '    </div>',
      '    <div class="gm-total" id="gmTotal"></div>',
      '    <button class="gm-close" id="gmClose" aria-label="Close">&#10005;</button>',
      '  </div>',
      '  <div class="gm-body" id="gmBody">',
      '    <div class="gm-table-wrap">',
      '      <table class="gm-table">',
      '        <thead><tr><th>Symbol</th><th>Account</th><th style="text-align:right">$</th><th id="gmTagHead">Tag</th></tr></thead>',
      '        <tbody id="gmTableBody"></tbody>',
      '      </table>',
      '    </div>',
      '    <div class="gm-chart-pane">',
      '      <h4>Largest holdings</h4>',
      '      <svg class="chart" id="gmBarChart" viewBox="0 0 380 300"></svg>',
      '    </div>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(el);
    document.getElementById('gmClose').addEventListener('click', window.closeGaugeExposureModal);
    document.getElementById('gmOverlay').addEventListener('click', window.closeGaugeExposureModal);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') window.closeGaugeExposureModal();
    });
  }

  function _dateQS(sep) {
    return (window.state && window.state.date) ? (sep + 'date=' + encodeURIComponent(window.state.date)) : '';
  }

  function fmt(n) { return '$' + Math.round(n).toLocaleString('en-US'); }
  function svgns(tag) { return document.createElementNS('http://www.w3.org/2000/svg', tag); }

  function _renderBars(rows) {
    // Aggregate per symbol across accounts, take top 6 + an "Other" bucket --
    // a 20-row donut/bar is unreadable; this mirrors the design mockup.
    var bySym = {};
    rows.forEach(function (r) { bySym[r.symbol] = (bySym[r.symbol] || 0) + r.dollar; });
    var pairs = Object.keys(bySym).map(function (s) { return [s, bySym[s]]; })
      .sort(function (a, b) { return b[1] - a[1]; });
    var top = pairs.slice(0, 6);
    var restTotal = pairs.slice(6).reduce(function (s, p) { return s + p[1]; }, 0);
    var restCount = pairs.length - top.length;
    if (restCount > 0) top.push(['Other (' + restCount + ' pos.)', restTotal]);

    var svg = document.getElementById('gmBarChart');
    svg.innerHTML = '';
    var W = 380, H = Math.max(top.length * 32, 120);
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    var max = Math.max.apply(null, top.map(function (d) { return d[1]; })) || 1;
    var rowH = H / top.length, barH = 20, labelW = 108, plotW = W - labelW - 66;

    top.forEach(function (d, i) {
      var y = i * rowH + (rowH - barH) / 2;
      var isOther = /^Other/.test(d[0]);
      var color = isOther ? 'var(--text-3)' : 'var(--act-sell)';

      var name = svgns('text');
      name.setAttribute('x', labelW - 8); name.setAttribute('y', y + barH * 0.72);
      name.setAttribute('text-anchor', 'end'); name.setAttribute('class', 'bar-name');
      name.textContent = d[0];
      svg.appendChild(name);

      var w = (d[1] / max) * plotW;
      var rect = svgns('rect');
      rect.setAttribute('x', labelW); rect.setAttribute('y', y);
      rect.setAttribute('width', Math.max(w, 2)); rect.setAttribute('height', barH);
      rect.setAttribute('rx', 4); rect.setAttribute('fill', color);
      svg.appendChild(rect);

      var val = svgns('text');
      val.setAttribute('x', labelW + w + 8); val.setAttribute('y', y + barH * 0.72);
      val.setAttribute('class', 'bar-value'); val.textContent = fmt(d[1]);
      svg.appendChild(val);
    });
  }

  // opts: {title, subtitlePrefix} -- title shown if the response has no
  // better one (factor response has no `label`); subtitlePrefix prepends
  // e.g. "Sector match" before the position/account count.
  function _open(fetchUrl, fallbackTitle, subtitlePrefix) {
    _ensure();
    var modal = document.getElementById(MODAL_ID);
    modal.classList.add('open');
    document.getElementById('gmTitle').textContent = fallbackTitle;
    document.getElementById('gmSub').textContent = 'Loading…';
    document.getElementById('gmTotal').innerHTML = '';
    document.getElementById('gmTableBody').innerHTML = '';
    document.getElementById('gmBarChart').innerHTML = '';

    fetch(fetchUrl)
      .then(function (r) { return r.json(); })
      .then(function (data) { _renderData(data, fallbackTitle, subtitlePrefix); })
      .catch(function (e) {
        console.error('exposure detail failed:', e);
        document.getElementById('gmSub').textContent = 'Failed to load exposure detail.';
      });
  }

  function _renderData(data, fallbackTitle, subtitlePrefix) {
    var hasTag = (data.positions || []).some(function (p) { return p.tag; });
    document.getElementById('gmTagHead').style.display = hasTag ? '' : 'none';

    document.getElementById('gmTitle').textContent = data.label || fallbackTitle;
    var cats = (data.categories || []).join(' · ');
    var n = (data.positions || []).length;
    var acctCount = new Set((data.positions || []).map(function (p) { return p.account; })).size;
    var prefix = cats ? ('Match: ' + cats + '  ·  ') : (subtitlePrefix ? subtitlePrefix + '  ·  ' : '');
    document.getElementById('gmSub').textContent =
      prefix + n + ' position' + (n === 1 ? '' : 's') +
      (acctCount ? ' across ' + acctCount + ' account' + (acctCount === 1 ? '' : 's') : '');
    document.getElementById('gmTotal').innerHTML = (data.dollar != null)
      ? '<div class="d">' + fmt(data.dollar) + '</div><div class="p">' + (data.pct != null ? data.pct.toFixed(1) + '% of portfolio' : '') + '</div>'
      : '<div class="d">&mdash;</div>';

    var tbody = document.getElementById('gmTableBody');
    (data.positions || []).forEach(function (p) {
      var tr = document.createElement('tr');
      var symTd = document.createElement('td'); symTd.className = 'sym'; symTd.textContent = p.symbol;
      var acctTd = document.createElement('td'); acctTd.className = 'acct'; acctTd.textContent = p.account;
      var dTd = document.createElement('td'); dTd.className = 'dollar'; dTd.textContent = fmt(p.dollar);
      tr.appendChild(symTd); tr.appendChild(acctTd); tr.appendChild(dTd);
      if (hasTag) {
        var tagTd = document.createElement('td'); tagTd.className = 'tag'; tagTd.textContent = p.tag || '';
        tr.appendChild(tagTd);
      }
      tbody.appendChild(tr);
    });
    if (!(data.positions || []).length) {
      var tr = document.createElement('tr');
      var td = document.createElement('td'); td.colSpan = hasTag ? 4 : 3; td.className = 'gm-empty';
      td.textContent = 'No positions match.';
      tr.appendChild(td); tbody.appendChild(tr);
    } else {
      _renderBars(data.positions);
    }
  }

  window.openGaugeExposureModal = function (gaugeKey) {
    _open('/api/cockpit/risk-dial/' + encodeURIComponent(gaugeKey) + '/exposure-detail' + _dateQS('?'),
          gaugeKey, null);
  };

  window.openFactorExposureModal = function (axis, category) {
    var axisLabel = axis === 'asset_class' ? 'Asset class' : (axis === 'style' ? 'Style' : 'Sector');
    _open('/api/cockpit/factor-scorecard/' + encodeURIComponent(axis) + '/' + encodeURIComponent(category) +
          '/exposure-detail' + _dateQS('?'), category, axisLabel + ' match');
  };

  window.closeGaugeExposureModal = function () {
    var modal = document.getElementById(MODAL_ID);
    if (modal) modal.classList.remove('open');
  };
})();
