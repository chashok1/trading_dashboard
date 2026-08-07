/* Risk Detail screen (/risk-detail) -- structural all-gauge exposure +
   risk-budget trailing history. See docs/dashboard_cockpit_design.md and
   the Risk Dial's exposure-detail modal (risk_gauge_modal.js) for the
   sibling "today only" drill-down; this screen is the "not just today"
   complement, reached via the Risk Dial card's "-> Risk detail" link. */
(function () {
  const tip = document.getElementById('tip');
  function showTip(evt, rows) {
    tip.innerHTML = rows.map(r =>
      `<div class="row"><span class="${r.k2 ? 'k k2' : 'k'}">${r.k}</span><b>${r.v}</b></div>`
    ).join('');
    tip.classList.add('show');
    moveTip(evt);
  }
  function moveTip(evt) { tip.style.left = evt.clientX + 'px'; tip.style.top = (evt.clientY - 10) + 'px'; }
  function hideTip() { tip.classList.remove('show'); }
  document.addEventListener('mousemove', e => { if (tip.classList.contains('show')) moveTip(e); });

  function svgns(tag) { return document.createElementNS('http://www.w3.org/2000/svg', tag); }
  function fmtD(n) { return '$' + Math.round(n).toLocaleString('en-US'); }

  async function init() {
    let allExp, history;
    try {
      [allExp, history] = await Promise.all([
        fetch('/api/cockpit/risk-dial/all-exposure').then(r => r.json()),
        fetch('/api/cockpit/risk-dial/history?days=90').then(r => r.json()),
      ]);
    } catch (e) {
      console.error('risk-detail load failed:', e);
      return;
    }
    document.getElementById('rdAsOf').textContent = 'as of ' + (allExp.as_of || '—');
    renderGaugeBars('allGaugeChart', allExp.gauges || []);
    renderLegend(allExp.gauges || []);
    renderBudgetTrend('budgetTrendChart', history.history || []);
  }

  function renderLegend(gauges) {
    const fired = gauges.filter(g => g.fired).length;
    const quiet = gauges.filter(g => !g.fired && g.has_mapping).length;
    const unmapped = gauges.filter(g => !g.has_mapping).length;
    document.getElementById('allGaugeLegend').innerHTML = `
      <span class="lk"><span class="sw" style="background:var(--act-sell-strong)"></span>Fired today (${fired})</span>
      <span class="lk"><span class="sw" style="background:var(--border)"></span>Quiet (${quiet})</span>
      <span class="lk"><span class="sw" style="background:var(--card-bg);border:1px dashed var(--text-3)"></span>No position mapping yet (${unmapped})</span>
    `;
  }

  function renderGaugeBars(id, gauges) {
    const svg = document.getElementById(id);
    svg.innerHTML = '';
    const mapped = gauges.filter(g => g.has_mapping).sort((a, b) => (b.dollar || 0) - (a.dollar || 0));
    const unmapped = gauges.filter(g => !g.has_mapping);
    const ordered = mapped.concat(unmapped);
    if (!ordered.length) return;
    const W = 900, H = Math.max(ordered.length * 33, 200);
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const max = Math.max(1, ...mapped.map(g => g.dollar || 0));
    const rowH = H / ordered.length, barH = 22, labelW = 210, plotW = W - labelW - 100;

    // gridlines, rounded to a clean step
    const step = Math.pow(10, Math.floor(Math.log10(max / 3)));
    const niceStep = step * (max / step > 6 ? 2 : 1);
    for (let g = 0; g <= max; g += niceStep) {
      const x = labelW + (g / max) * plotW;
      const line = svgns('line');
      line.setAttribute('x1', x); line.setAttribute('x2', x);
      line.setAttribute('y1', 0); line.setAttribute('y2', H - 18);
      line.setAttribute('class', 'gridline');
      svg.appendChild(line);
      const lbl = svgns('text');
      lbl.setAttribute('x', x); lbl.setAttribute('y', H - 4);
      lbl.setAttribute('class', 'axis-label'); lbl.setAttribute('text-anchor', 'middle');
      lbl.textContent = '$' + Math.round(g / 1000) + 'k';
      svg.appendChild(lbl);
    }

    ordered.forEach((g, i) => {
      const y = i * rowH + (rowH - barH) / 2;
      const name = svgns('text');
      name.setAttribute('x', labelW - 10); name.setAttribute('y', y + barH * 0.68);
      name.setAttribute('text-anchor', 'end');
      name.setAttribute('style', g.has_mapping ? '' : 'fill:var(--text-3)');
      name.setAttribute('class', g.has_mapping ? 'bar-name' : 'axis-label');
      name.textContent = g.label;
      svg.appendChild(name);

      if (g.fired) {
        const textW = String(g.label).length * 5.6;
        const dot = svgns('circle');
        dot.setAttribute('cx', labelW - 10 - textW - 10);
        dot.setAttribute('cy', y + barH * 0.5 - 3);
        dot.setAttribute('r', 3); dot.setAttribute('class', 'fired-dot');
        svg.appendChild(dot);
      }

      if (!g.has_mapping) {
        const rect = svgns('rect');
        rect.setAttribute('x', labelW); rect.setAttribute('y', y);
        rect.setAttribute('width', 60); rect.setAttribute('height', barH);
        rect.setAttribute('rx', 4); rect.setAttribute('fill', 'none');
        rect.setAttribute('stroke', 'var(--text-3)'); rect.setAttribute('stroke-dasharray', '3,3');
        svg.appendChild(rect);
        const na = svgns('text');
        na.setAttribute('x', labelW + 70); na.setAttribute('y', y + barH * 0.68);
        na.setAttribute('class', 'axis-label'); na.textContent = 'no mapping yet';
        svg.appendChild(na);
        return;
      }

      const dollar = g.dollar || 0;
      const w = (dollar / max) * plotW;
      const rect = svgns('rect');
      rect.setAttribute('x', labelW); rect.setAttribute('y', y);
      rect.setAttribute('width', Math.max(w, 2)); rect.setAttribute('height', barH);
      rect.setAttribute('rx', 4); rect.setAttribute('fill', g.fired ? 'var(--act-sell-strong)' : 'var(--border)');
      svg.appendChild(rect);

      const val = svgns('text');
      val.setAttribute('x', labelW + w + 8); val.setAttribute('y', y + barH * 0.68);
      val.setAttribute('class', 'bar-value');
      val.textContent = `${fmtD(dollar)}  (${(g.pct || 0).toFixed(1)}%)`;
      svg.appendChild(val);

      const hit = svgns('rect');
      hit.setAttribute('x', labelW); hit.setAttribute('y', y - 3);
      hit.setAttribute('width', plotW + 120); hit.setAttribute('height', barH + 6);
      hit.setAttribute('class', 'chart-hit');
      hit.addEventListener('mousemove', e => showTip(e, [
        { k: g.label, v: '' },
        { k: 'Exposure', v: fmtD(dollar) },
        { k: '% of portfolio', v: (g.pct || 0).toFixed(1) + '%' },
        { k: 'Status', v: g.fired ? 'fired today' : 'quiet', k2: true },
      ]));
      hit.addEventListener('mouseleave', hideTip);
      hit.style.cursor = 'pointer';
      hit.addEventListener('click', () => { if (window.openGaugeExposureModal) openGaugeExposureModal(g.gauge_key); });
      svg.appendChild(hit);
    });
  }

  function renderBudgetTrend(id, hist) {
    const svg = document.getElementById(id);
    svg.innerHTML = '';
    if (!hist.length) return;
    const W = 900, H = 340, padL = 34, padR = 118, padT = 10, padB = 28;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const xAt = i => padL + (hist.length === 1 ? 0 : (i / (hist.length - 1)) * plotW);
    const yAt = v => padT + (1 - v / 100) * plotH;

    const bands = [
      [80, 100, 'var(--ok)', 'CLEAR'],
      [55, 80, 'var(--warn)', 'CAUTION'],
      [30, 55, 'var(--act-sell)', 'DEFENSIVE'],
      [0, 30, 'var(--bear)', 'NOT INVESTABLE'],
    ];
    bands.forEach(b => {
      const rect = svgns('rect');
      rect.setAttribute('x', padL); rect.setAttribute('y', yAt(b[1]));
      rect.setAttribute('width', plotW); rect.setAttribute('height', yAt(b[0]) - yAt(b[1]));
      rect.setAttribute('fill', b[2]); rect.setAttribute('opacity', '0.07');
      svg.appendChild(rect);
      const lbl = svgns('text');
      lbl.setAttribute('x', padL + plotW + 10); lbl.setAttribute('y', (yAt(b[0]) + yAt(b[1])) / 2 + 3);
      lbl.setAttribute('class', 'axis-label'); lbl.setAttribute('style', 'fill:' + b[2]);
      lbl.textContent = b[3];
      svg.appendChild(lbl);
    });

    [0, 25, 50, 75, 100].forEach(v => {
      const y = yAt(v);
      const line = svgns('line');
      line.setAttribute('x1', padL); line.setAttribute('x2', padL + plotW);
      line.setAttribute('y1', y); line.setAttribute('y2', y);
      line.setAttribute('class', 'gridline'); line.setAttribute('opacity', '0.5');
      svg.appendChild(line);
      const lbl = svgns('text');
      lbl.setAttribute('x', padL - 8); lbl.setAttribute('y', y + 3);
      lbl.setAttribute('text-anchor', 'end'); lbl.setAttribute('class', 'axis-label');
      lbl.textContent = v;
      svg.appendChild(lbl);
    });

    const pts = hist.map((d, i) => `${xAt(i)},${yAt(d.risk_budget ?? 0)}`).join(' ');
    const poly = svgns('polyline');
    poly.setAttribute('points', pts);
    poly.setAttribute('fill', 'none'); poly.setAttribute('stroke', 'var(--accent)');
    poly.setAttribute('stroke-width', '2'); poly.setAttribute('stroke-linejoin', 'round');
    poly.setAttribute('stroke-linecap', 'round');
    svg.appendChild(poly);

    const todayFired = new Set((hist[hist.length - 1] || {}).fired || []);

    hist.forEach((d, i) => {
      const x = xAt(i), y = yAt(d.risk_budget ?? 0);
      const overlap = (d.fired || []).some(k => todayFired.has(k));
      if (overlap) {
        const ring = svgns('circle');
        ring.setAttribute('cx', x); ring.setAttribute('cy', y); ring.setAttribute('r', 5);
        ring.setAttribute('fill', 'var(--card-bg)');
        svg.appendChild(ring);
        const dot = svgns('circle');
        dot.setAttribute('cx', x); dot.setAttribute('cy', y); dot.setAttribute('r', 3.5);
        dot.setAttribute('class', 'fired-dot');
        svg.appendChild(dot);
      }
      const hit = svgns('circle');
      hit.setAttribute('cx', x); hit.setAttribute('cy', y); hit.setAttribute('r', 10);
      hit.setAttribute('class', 'chart-hit');
      hit.addEventListener('mousemove', e => {
        const rows = [{ k: d.as_of, v: d.risk_budget }];
        rows.push({ k: 'Fired', v: (d.fired || []).length ? d.fired.join(', ') : 'none', k2: true });
        showTip(e, rows);
      });
      hit.addEventListener('mouseleave', hideTip);
      svg.appendChild(hit);
    });

    const lastI = hist.length - 1, lx = xAt(lastI), ly = yAt(hist[lastI].risk_budget ?? 0);
    const endDot = svgns('circle');
    endDot.setAttribute('cx', lx); endDot.setAttribute('cy', ly); endDot.setAttribute('r', 4.5);
    endDot.setAttribute('fill', 'var(--accent)');
    svg.appendChild(endDot);
    const endLbl = svgns('text');
    endLbl.setAttribute('x', lx + 9); endLbl.setAttribute('y', ly - 8);
    endLbl.setAttribute('class', 'bar-value'); endLbl.setAttribute('font-weight', '700');
    endLbl.textContent = `${hist[lastI].risk_budget} today`;
    svg.appendChild(endLbl);

    const tickCount = Math.min(6, hist.length);
    for (let t = 0; t < tickCount; t++) {
      const i = Math.round((t / (tickCount - 1 || 1)) * lastI);
      const lbl = svgns('text');
      lbl.setAttribute('x', xAt(i)); lbl.setAttribute('y', H - 8);
      lbl.setAttribute('text-anchor', 'middle'); lbl.setAttribute('class', 'axis-label');
      lbl.textContent = hist[i].as_of.slice(5);
      svg.appendChild(lbl);
    }
  }

  init();
})();
