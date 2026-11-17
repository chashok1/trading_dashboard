/* Builder "Plan" and "To do" tabs (DESIGN_SPEC_16, per-account plans). Reuses the Builder page and its look.
 * Plan: asset class % (required, total 100) + optional beta / sector / style (blank = Open) + the stocks you pick
 * ("buy one of these" when several). Activate makes it the account's active plan. To do: sells for classes above
 * their %, your picks with Actionable's call, and what is left. Money limits block; % lines only warn.
 * The Builder never trades and never changes the Actionable Final Call. Every account stands alone. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const kfmt = a => a >= 1e6 ? (a / 1e6).toFixed(2) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(1) + 'K' : Math.round(a).toLocaleString();
  const usd = n => (n == null || isNaN(n)) ? '-' : (n < 0 ? '-$' : '$') + kfmt(Math.abs(n));
  const CLASSES = ['Equities', 'Fixed Income', 'Gold', 'Commodities', 'Crypto', 'Currency', 'Cash'];
  const CALL_LABEL = { BM: 'Buy More', BS: 'Buy Some', BMN: 'Buy To Min', INCREASE: 'Increase', ADD: 'Add', BW: 'Buy Watch', BSW: 'Buy Some Watch',
    SA: 'Sell All', SS: 'Sell Some', STM: 'Sell/Trim', REDUCE: 'Reduce', SO: 'Sell (Over Max)', SW: 'Sell Watch', SWW: 'Sell Watch', REMOVE: 'Remove', HOLD: 'Hold' };
  const callLabel = c => c ? (CALL_LABEL[c] || c) : 'No call';

  const S = { acct: null, accts: [], states: {}, page: null, plan: null, dirty: false, sources: [], srcOn: new Set(), names: [], mine: [],
    ticks: new Set(), todo: null, ready: false };

  async function api(url, opt) {
    const r = await fetch(url, opt);
    let j = null;
    try { j = await r.json(); } catch (e) { /* no body */ }
    if (!r.ok) throw new Error((j && j.detail) || ('HTTP ' + r.status));
    return j;
  }
  const send = (url, body, method) => api(url, { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  const dq = () => { const el = $('datePicker'); return el && el.value ? 'date=' + encodeURIComponent(el.value) : ''; };
  const withDate = u => { const q = dq(); return q ? u + (u.includes('?') ? '&' : '?') + q : u; };
  function note(msg, warn, html) {
    const el = $('plMsg');
    if (!msg) { el.hidden = true; return; }
    el.hidden = false; el.className = 'bld-note'; el.style.borderColor = warn ? '#b45309' : '';
    if (html) el.innerHTML = msg; else el.textContent = msg;
  }

  // ------------------------------------------------------------------ plan object
  function blankPlan() {
    return { cls: Object.fromEntries(CLASSES.map(c => [c, 0])), beta: { low: null, high: null }, sector: {}, style: {}, cash_keep: 1000 };
  }
  function fromHeld(page) {
    const p = blankPlan(), v = page.value || 0;
    let sum = 0;
    CLASSES.filter(c => c !== 'Cash').forEach(c => { const x = v ? Math.round((page.now.cls[c] || 0) / v * 100) : 0; p.cls[c] = x; sum += x; });
    p.cls.Cash = Math.max(0, 100 - sum);
    return p;
  }
  const clone = o => JSON.parse(JSON.stringify(o));
  const num = el => { const t = String(el.value).trim(); return t === '' ? null : Math.max(0, Number(t)); };

  // ------------------------------------------------------------------ Plan tab
  async function loadPlan() {
    if (!S.acct) return;
    $('plState').textContent = 'Loading...';
    try {
      const [page, mine, st] = await Promise.all([
        api(withDate('/api/builder/plan?account=' + encodeURIComponent(S.acct))),
        api(withDate('/api/builder/my-stocks')), api('/api/builder/plan/states')]);
      S.page = page; S.mine = mine.stocks || []; S.states = st.states || {};
      S.plan = clone(page.draft || page.active || fromHeld(page));
      S.dirty = !(page.draft || page.active);
      S.ticks = new Set();
      await loadNames();
      renderPlan();
    } catch (e) { note('Could not load the plan: ' + e.message, true); $('plState').textContent = ''; }
  }

  async function loadNames() {
    const codes = [...S.srcOn].filter(c => c !== 'MINE');
    let rows = [];
    if (codes.length) {
      const j = await api(withDate('/api/builder/source-names?sources=' + encodeURIComponent(codes.join(',')) + '&account=' + encodeURIComponent(S.acct)));
      rows = (j.names || []).map(n => Object.assign({}, n, { lists: (n.sources || []).filter(c => c !== 'HELD' || true) }));
    }
    if (S.srcOn.has('MINE')) {
      const have = new Set(rows.map(r => r.sym));
      S.mine.filter(m => !m.moved_on && m.info).forEach(m => {
        if (have.has(m.sym)) return;
        rows.push(Object.assign({}, m.info, { sym: m.sym, lists: ['MINE'] }));
      });
    }
    S.names = rows;
  }

  function renderPlan() {
    const pg = S.page, v = pg.value || 0;
    $('plAcct').value = S.acct; $('tdAcct').value = S.acct;
    const st = pg.state;
    $('plState').textContent = (st === 'active' ? 'Active plan' : st === 'draft' ? 'Draft only' : 'No plan yet') + (S.dirty ? ' · unsaved changes' : '');
    $('plState').className = 'bld-pill';
    $('plSnap').textContent = 'Value ' + usd(v) + ' · Cash ' + usd(pg.cash) + ' · Positions ' + (pg.snap_date || '-') + (pg.stale ? ' · old file' : '');
    renderStart(); renderLists(); renderMine(); renderNames(); renderCls(); renderOpt(); renderPicks();
  }

  function renderStart() {
    const others = S.accts.filter(a => a !== S.acct && S.states[a] && S.states[a] !== 'none');
    $('plStart').innerHTML = '<option value="">Start from...</option><option value="held">What this account holds now</option>' +
      others.map(a => '<option value="copy:' + esc(a) + '">Copy ' + esc(a) + "'s plan</option>").join('');
  }

  function renderLists() {
    $('plLists').innerHTML = S.sources.map(s => '<label><input type="checkbox" data-src="' + esc(s.code) + '"' + (S.srcOn.has(s.code) ? ' checked' : '') + '> ' + esc(s.label) + '</label>').join('') +
      '<label><input type="checkbox" data-src="MINE"' + (S.srcOn.has('MINE') ? ' checked' : '') + '> My stocks (' + S.mine.filter(m => !m.moved_on).length + ')</label>';
    $('plLists').querySelectorAll('[data-src]').forEach(e => e.onchange = async () => {
      if (e.checked) S.srcOn.add(e.dataset.src); else S.srcOn.delete(e.dataset.src);
      try { await loadNames(); renderNames(); } catch (x) { note(x.message, true); }
    });
  }

  function renderMine() {
    $('plMine').innerHTML = S.mine.length ? S.mine.map(m => m.moved_on
      ? '<span class="pl-chip" title="Hedgeye listed it on ' + esc(m.moved_on) + '. It now counts as a Hedgeye name.">' + esc(m.sym) + ' <span class="bld-muted">moved to Hedgeye</span> <a href="#" data-mrm="' + esc(m.sym) + '" aria-label="Remove ' + esc(m.sym) + '">&times;</a></span>'
      : '<span class="pl-chip">' + esc(m.sym) + ' <a href="#" data-mrm="' + esc(m.sym) + '" aria-label="Remove ' + esc(m.sym) + '">&times;</a></span>').join('')
      : '<span class="bld-muted">None yet.</span>';
    $('plMine').querySelectorAll('[data-mrm]').forEach(a => a.onclick = async ev => {
      ev.preventDefault();
      try { await send('/api/builder/my-stocks/' + encodeURIComponent(a.dataset.mrm), {}, 'DELETE'); await refreshMine(); } catch (x) { note(x.message, true); }
    });
  }
  async function refreshMine() {
    const mine = await api(withDate('/api/builder/my-stocks'));
    S.mine = mine.stocks || [];
    await loadNames(); renderLists(); renderMine(); renderNames();
  }

  function renderNames() {
    const cls = $('plFClass').value, q = $('plFText').value.trim().toUpperCase();
    const inPick = new Set((S.page.picks || []).filter(p => p.side === 'BUY').flatMap(p => p.members));
    let rows = S.names.filter(n => (!cls || n.bucket === cls) && (!q || n.sym.includes(q)));
    $('plNamesCount').textContent = rows.length + ' names';
    rows = rows.slice(0, 400);
    $('plNames').innerHTML = rows.map(n => {
      const mine = (n.lists || []).includes('MINE');
      const lists = mine ? '<span class="pl-p grp">My stocks</span>' : esc((n.lists || n.sources || []).filter(c => c !== 'HELD').slice(0, 3).join(' ') || ((n.lists || []).includes('HELD') ? 'Held' : ''));
      return '<tr><td><input type="checkbox" data-t="' + esc(n.sym) + '"' + (S.ticks.has(n.sym) ? ' checked' : '') + (inPick.has(n.sym) ? ' disabled title="Already in a pick"' : '') + ' aria-label="Pick ' + esc(n.sym) + '"></td><td><b>' + esc(n.sym) + '</b></td><td>' + lists +
        '</td><td>' + esc(n.bucket || 'No class') + '</td><td>' + esc(n.sector || '') + '</td><td class="n">' + (n.beta == null ? '' : Number(n.beta).toFixed(2)) + '</td><td>' + esc((n.styles || []).slice(0, 2).join(', ')) + '</td></tr>';
    }).join('');
    $('plNames').querySelectorAll('[data-t]').forEach(e => e.onchange = () => { if (e.checked) S.ticks.add(e.dataset.t); else S.ticks.delete(e.dataset.t); syncMake(); });
    syncMake();
  }
  function syncMake() {
    const n = S.ticks.size, b = $('plMake');
    b.disabled = n < 1; b.textContent = n > 1 ? 'Make a buy-one-of group' : 'Add as pick';
  }

  function renderCls() {
    const pg = S.page, v = pg.value || 1, p = S.plan;
    let tot = 0;
    let h = '<thead><tr><th>Class</th><th class="n">Held</th><th class="n">Plan %</th><th class="n">Gap</th><th></th></tr></thead><tbody>';
    CLASSES.forEach(c => {
      const held = pg.now.cls[c] || 0, plan = p.cls[c] || 0, gap = plan / 100 * v - held;
      tot += plan;
      let n;
      if (plan === 0 && held > 500 && c !== 'Cash') n = '<span class="pl-p sell">Sell all ' + usd(held) + '</span>';
      else if (gap < -500 && c !== 'Cash') n = '<span class="pl-p sell">Sell ' + usd(-gap) + '</span>';
      else if (gap > 500) n = '<span class="pl-p buy">Room ' + usd(gap) + '</span>';
      else n = '<span class="bld-muted">On plan</span>';
      h += '<tr><td>' + esc(c) + '</td><td class="n">' + (held / v * 100).toFixed(1) + '%</td><td class="n"><input class="pl-in" type="number" min="0" max="100" step="1" data-c="' + esc(c) + '" value="' + plan + '" aria-label="' + esc(c) + ' plan percent"></td><td class="n">' + (gap >= 0 ? '+' : '-') + usd(Math.abs(gap)) + '</td><td>' + n + '</td></tr>';
    });
    const un = pg.now.cls.Unmapped || 0;
    if (un > 500) h += '<tr><td>No class</td><td class="n">' + (un / v * 100).toFixed(1) + '%</td><td class="n bld-muted">-</td><td></td><td class="bld-muted">Not covered by the plan</td></tr>';
    $('plCls').innerHTML = h + '</tbody>';
    const ok = Math.abs(tot - 100) <= 0.1;
    $('plClsTot').innerHTML = '<span style="color:' + (ok ? '#16a34a' : '#9e3636') + '">' + (+tot.toFixed(2)) + '% ' + (ok ? '&#10003;' : '(must be 100)') + '</span>';
    $('plCls').querySelectorAll('[data-c]').forEach(e => e.onchange = () => { S.plan.cls[e.dataset.c] = Math.max(0, Number(e.value) || 0); dirty(); renderCls(); renderOpt(); });
  }

  function renderOpt() {
    const pg = S.page, v = pg.value || 1, p = S.plan;
    const hp = x => (x / v * 100).toFixed(1) + '%';
    const low = p.beta.low, high = p.beta.high;
    const open = 100 - (low || 0) - (high || 0);
    let h = '<tr class="pl-sec"><td colspan="3">Beta</td></tr>' +
      '<tr><td>Low beta (0.8 or less)</td><td class="n bld-muted">Held ' + hp(pg.now.beta.low || 0) + '</td><td class="n"><input class="pl-in" type="number" min="0" max="100" data-b="low" placeholder="Open" value="' + (low == null ? '' : low) + '"> %</td></tr>' +
      '<tr><td>High beta (over 1.2)</td><td class="n bld-muted">Held ' + hp(pg.now.beta.high || 0) + '</td><td class="n"><input class="pl-in" type="number" min="0" max="100" data-b="high" placeholder="Open" value="' + (high == null ? '' : high) + '"> %</td></tr>' +
      '<tr class="pl-open"><td><b>Open</b> <span class="bld-muted">(no rule)</span></td><td></td><td class="n"><b>' + (+open.toFixed(2)) + '</b> %</td></tr>';
    const secs = [...new Set([...(pg.sectors || []), ...Object.keys(p.sector || {})])].sort();
    h += '<tr class="pl-sec"><td colspan="3">Sector <span class="bld-muted" style="font-weight:400">(blank = Open)</span></td></tr>' + secs.map(s =>
      '<tr><td>' + esc(s) + '</td><td class="n bld-muted">Held ' + hp(pg.now.sector[s] || 0) + '</td><td class="n"><input class="pl-in" type="number" min="0" max="100" data-s="' + esc(s) + '" placeholder="Open" value="' + (p.sector[s] == null ? '' : p.sector[s]) + '"> %</td></tr>').join('');
    h += '<tr class="pl-sec"><td colspan="3">Style <span class="bld-muted" style="font-weight:400">(blank = Open)</span></td></tr>' + (pg.styles || []).map(s =>
      '<tr><td>' + esc(s) + '</td><td class="n bld-muted">Held ' + hp(pg.now.style[s] || 0) + '</td><td class="n"><input class="pl-in" type="number" min="0" max="100" data-y="' + esc(s) + '" placeholder="Open" value="' + (p.style[s] == null ? '' : p.style[s]) + '"> %</td></tr>').join('');
    $('plOpt').innerHTML = h;
    $('plOpt').querySelectorAll('[data-b]').forEach(e => e.onchange = () => { S.plan.beta[e.dataset.b] = num(e); dirty(); renderOpt(); });
    $('plOpt').querySelectorAll('[data-s]').forEach(e => e.onchange = () => { S.plan.sector[e.dataset.s] = num(e); dirty(); });
    $('plOpt').querySelectorAll('[data-y]').forEach(e => e.onchange = () => { S.plan.style[e.dataset.y] = num(e); dirty(); });
  }

  function renderPicks() {
    const picks = (S.page.picks || []).filter(p => p.side === 'BUY');
    $('plPicks').innerHTML = picks.length ? picks.map(p => '<div class="pl-pick"><div class="bld-line"><b>' + (p.members.length > 1 ? 'Buy one of' : 'Buy') + '</b> ' +
      p.members.map(m => '<span class="pl-chip">' + esc(m) + '</span>').join(p.members.length > 1 ? '<span class="bld-muted">or</span>' : '') +
      '<span style="margin-left:auto"><button class="bld-btn sm alt" data-prm="' + p.id + '">Remove</button></span></div>' +
      '<div class="bld-line"><span class="bld-muted">Amount</span><input class="pl-in pl-amt" type="number" min="0" step="500" data-pa="' + p.id + '" value="' + (p.amount || '') + '" placeholder="$0"></div></div>').join('')
      : '<div class="bld-muted" style="margin:6px 0">No stocks picked. Tick names in the middle column.</div>';
    $('plPicks').querySelectorAll('[data-prm]').forEach(b => b.onclick = async () => {
      try { await send('/api/builder/pick/' + b.dataset.prm, {}, 'DELETE'); S.page.picks = S.page.picks.filter(p => String(p.id) !== b.dataset.prm); renderPicks(); renderNames(); } catch (x) { note(x.message, true); }
    });
    $('plPicks').querySelectorAll('[data-pa]').forEach(e => e.onchange = async () => {
      const amt = Math.max(0, Number(e.value) || 0);
      try { await send('/api/builder/pick/' + e.dataset.pa, { amount: amt }, 'PATCH'); const pk = S.page.picks.find(p => String(p.id) === e.dataset.pa); if (pk) pk.amount = amt; } catch (x) { note(x.message, true); }
    });
  }

  function dirty() { S.dirty = true; $('plState').textContent = $('plState').textContent.replace(/ · unsaved changes$/, '') + ' · unsaved changes'; }

  async function savePlan(quiet) {
    await send('/api/builder/plan', { account: S.acct, plan: S.plan }, 'PUT');
    S.dirty = false;
    if (!S.page.draft) S.page.draft = clone(S.plan);
    if (S.page.state === 'none') S.page.state = 'draft';
    S.states[S.acct] = S.page.state;
    if (!quiet) note('Draft saved. The active plan has not changed.');
    renderPlan();
  }

  async function onActivate() {
    try {
      await savePlan(true);
      const dry = await send('/api/builder/plan/activate', { account: S.acct, plan: S.plan, dry_run: true });
      const ch = (dry.changes || []).map(c => '<li>' + esc(c) + '</li>').join('') || '<li>No change from the active plan.</li>';
      note('<b>Activate this plan for ' + esc(S.acct) + '?</b> It will change:<ul style="margin:4px 0 6px 18px">' + ch + '</ul>' +
        '<button class="bld-btn" id="plGo">Activate</button> <button class="bld-btn alt" id="plNo">Cancel</button>', false, true);
      $('plGo').onclick = async () => {
        try {
          await send('/api/builder/plan/activate', { account: S.acct, plan: S.plan });
          S.page.state = 'active'; S.states[S.acct] = 'active'; note('');
          document.querySelector('.bld-tab[data-v="todo"]').click();
        } catch (e) { note(e.message, true); }
      };
      $('plNo').onclick = () => note('');
    } catch (e) { note(e.message, true); }
  }

  async function onStart() {
    const v = $('plStart').value;
    if (!v) return;
    try {
      if (v === 'held') S.plan = fromHeld(S.page);
      else if (v.startsWith('copy:')) {
        const src = await api(withDate('/api/builder/plan?account=' + encodeURIComponent(v.slice(5))));
        const sp = src.active || src.draft;
        if (sp) { S.plan = clone(sp); S.plan.cash_keep = S.plan.cash_keep || 1000; }
      }
      dirty(); renderCls(); renderOpt(); note('Boxes filled. Nothing is saved until you press Save draft.');
    } catch (e) { note(e.message, true); }
    $('plStart').value = '';
  }

  async function onMake() {
    const members = [...S.ticks];
    if (!members.length) return;
    try {
      const r = await send('/api/builder/pick', { account: S.acct, side: 'BUY', members, amount: 0, ticked: false });
      S.page.picks = (S.page.picks || []).concat([{ id: r.id, side: 'BUY', members, amount: 0, ticked: false }]);
      S.ticks = new Set(); renderPicks(); renderNames(); note('');
    } catch (e) { note(e.message, true); }
  }

  // ------------------------------------------------------------------ To do tab
  async function loadTodo() {
    if (!S.acct) return;
    $('tdAcct').value = S.acct;
    $('tdBody').classList.add('pl-dim');
    try {
      S.todo = await api(withDate('/api/builder/todo?account=' + encodeURIComponent(S.acct)));
      renderTodo();
    } catch (e) { $('tdMsg').textContent = 'Could not load: ' + e.message; $('tdMsg').className = 'pl-msg w'; }
    $('tdBody').classList.remove('pl-dim');
  }

  const pill = (cls, t, tip) => '<span class="pl-p ' + cls + '"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' + esc(t) + '</span>';

  function renderTodo() {
    const t = S.todo;
    $('tdEmpty').hidden = t.state !== 'none'; $('tdBody').hidden = t.state === 'none';
    $('tdState').textContent = t.state === 'none' ? 'No active plan' : 'Active since ' + String(t.active_at || '').slice(0, 10);
    $('tdSnap').textContent = t.state === 'none' ? '' : 'Value ' + usd(t.value) + ' · Cash ' + usd(t.cash) + ' · Positions ' + (t.snap_date || '-');
    if (t.state === 'none') return;

    // sells
    $('tdSells').innerHTML = (t.sells || []).length ? t.sells.map(s => '<div style="margin-bottom:10px"><div class="bld-line"><b>' + esc(s.cls) + '</b>' +
      pill('sell', s.all ? 'Plan 0%: sell all ' + usd(s.held) : 'Over plan by about ' + usd(s.need)) +
      '<span class="bld-muted" style="margin-left:auto">Ticked ' + usd(s.ticked_total) + ' of ' + usd(s.need) + '</span></div>' +
      '<table class="bld-t"><thead><tr><th></th><th>Holding</th><th class="n">Value</th><th>Actionable</th></tr></thead><tbody>' +
      s.holdings.map(h => '<tr><td><input type="checkbox" data-sell="' + esc(h.sym) + '" data-pid="' + (h.pick_id || '') + '" data-val="' + h.value + '"' + (h.ticked ? ' checked' : '') + ' aria-label="Sell ' + esc(h.sym) + '"></td><td><b>' + esc(h.sym) + '</b></td><td class="n">' + usd(h.value) +
        '</td><td>' + pill(h.side === 'sell' ? 'sell' : h.side === 'buy' ? 'buy' : '', callLabel(h.call)) + '</td></tr>').join('') + '</tbody></table></div>').join('')
      : '<div class="bld-muted">Nothing is over its plan. No sells needed.</div>';
    $('tdSells').querySelectorAll('[data-sell]').forEach(e => e.onchange = async () => {
      try {
        if (e.checked) await send('/api/builder/pick', { account: S.acct, side: 'SELL', members: [e.dataset.sell], amount: Number(e.dataset.val), ticked: true });
        else if (e.dataset.pid) await send('/api/builder/pick/' + e.dataset.pid, {}, 'DELETE');
        await loadTodo();
      } catch (x) { $('tdMsg').textContent = x.message; $('tdMsg').className = 'pl-msg w'; }
    });

    // buys
    const RES = { OK: ['ok', 'OK'], OVER_PLAN: ['warn', 'Over plan'], SHRUNK: ['warn', 'Cut'], BLOCKED: ['bad', 'Blocked'], WAITING: ['', 'Waiting'], READY: ['buy', 'Has a Buy'] };
    let b = '<thead><tr><th></th><th>Pick</th><th>Actionable today</th><th class="n">Amount</th><th class="n">Allowed</th><th>Result</th></tr></thead><tbody>';
    (t.buys || []).forEach(x => {
      const names = x.members.map(m => '<span class="pl-chip">' + esc(m) + '</span>').join(x.members.length > 1 ? '<span class="bld-muted">or</span>' : '');
      const calls = x.members.map(m => esc(m) + ': ' + esc(callLabel(x.calls[m]))).join(' · ');
      const r = RES[x.result] || ['', x.result];
      const canTick = x.result !== 'WAITING';
      b += '<tr><td><input type="checkbox" data-buy="' + x.id + '"' + (x.ticked ? ' checked' : '') + (canTick ? '' : ' disabled') + ' aria-label="Count this pick"></td><td>' + names + '<div class="bld-muted">' + calls + '</div></td><td>' +
        (x.buy_member ? pill('buy', 'Buy: ' + x.buy_member) : pill('', 'None yet')) + '</td><td class="n"><input class="pl-in pl-amt" type="number" min="0" step="500" data-ba="' + x.id + '" value="' + (x.amount || '') + '" placeholder="$0"></td><td class="n">' +
        (x.allowed ? usd(x.allowed) : '-') + '</td><td>' + pill(r[0], r[1]) + ' <span class="bld-muted">' + esc(x.why) + '</span></td></tr>';
    });
    if (!(t.buys || []).length) b += '<tr><td colspan="6" class="bld-muted">No picks yet. Add them on the Plan tab.</td></tr>';
    $('tdBuys').innerHTML = b + '</tbody>';
    $('tdBuys').querySelectorAll('[data-buy]').forEach(e => e.onchange = async () => { await patchBuy(e.dataset.buy, { ticked: e.checked }); });
    $('tdBuys').querySelectorAll('[data-ba]').forEach(e => e.onchange = async () => { await patchBuy(e.dataset.ba, { amount: Math.max(0, Number(e.value) || 0) }); });

    // what is left
    const bar = (now, used, plan, hard) => {
      const after = now + used, w = plan > 0 ? Math.min(after / plan * 100, 100) : (after > 0 ? 100 : 0), nw = plan > 0 ? Math.min(now / plan * 100, 100) : (now > 0 ? 100 : 0);
      const over = after > plan + 1;
      return '<div class="pl-bar2"><i class="' + (hard ? 'h' : over ? 'o' : '') + '" style="width:' + w + '%"></i><b style="width:' + nw + '%"></b></div>';
    };
    let L = '';
    (t.lines || []).filter(r => r.kind === 'cls' && r.key !== 'Cash' && (r.plan > 0 || r.now > 500)).forEach(r => {
      const over = r.left < -1;
      L += '<div><div class="bld-line"><b>' + esc(r.key) + '</b><span style="margin-left:auto;color:' + (over ? '#b45309' : '#16a34a') + '">' + (over ? 'over by ' + usd(-r.left) + ' (warning)' : usd(r.left) + ' left') + '</span></div>' +
        bar(r.now, r.used, r.plan, false) + '<div class="bld-muted">Plan ' + r.plan_pct + '% = ' + usd(r.plan) + '</div></div>';
    });
    const cashHard = t.cash_left <= 0;
    L += '<div><div class="bld-line"><b>Cash you can spend</b><span style="margin-left:auto;color:' + (cashHard ? '#9e3636' : '#16a34a') + '">' + usd(t.cash_left) + ' left</span></div>' +
      '<div class="pl-bar2"><i class="' + (cashHard ? 'h' : '') + '" style="width:' + (t.cash_to_spend > 0 ? Math.min((t.cash_to_spend - t.cash_left) / t.cash_to_spend * 100, 100) : 100) + '%"></i></div>' +
      '<div class="bld-muted">Cash ' + usd(t.cash) + (t.sell_cash ? ' + ' + usd(t.sell_cash) + ' expected from sells (not in your broker file yet)' : '') + '. Keeps the plan\'s Cash % and ' + usd(t.cash_keep) + '. This is a money limit: it blocks.</div></div>';
    const opt = (t.lines || []).filter(r => r.kind !== 'cls');
    if (opt.length) {
      L += '<div class="bld-muted" style="margin-top:4px"><b>Optional lines (warn only)</b></div>' + opt.map(r => {
        const over = r.left < -1;
        return '<div><div class="bld-line"><span>' + esc(r.label) + '</span><span style="margin-left:auto;color:' + (over ? '#b45309' : '#16a34a') + '">' + (over ? 'over by ' + usd(-r.left) : usd(r.left) + ' left') + '</span></div>' + bar(r.now, r.used, r.plan, false) + '</div>';
      }).join('');
    }
    $('tdLeft').innerHTML = L;
    const cut = (t.buys || []).some(x => x.result === 'SHRUNK' || x.result === 'BLOCKED');
    const parts = ['Buys counted: ' + usd(t.bought) + '.'];
    if (t.sell_cash) parts.push('Sells ticked: ' + usd(t.sell_cash) + ' (expected).');
    if (cut) parts.push('A cash limit cut a buy. Tick more sells or lower an amount.');
    else if ((t.notes || []).some(n => /over its plan/.test(n))) parts.push('Some lines are over plan. You can still place these.');
    else if (t.bought) parts.push('Everything is inside the plan.');
    else parts.push('Nothing counted yet.');
    $('tdMsg').textContent = parts.join(' ');
    $('tdMsg').className = 'pl-msg' + ((cut || (t.notes || []).some(n => /over its plan/.test(n))) ? ' w' : '');
    $('tdNotes').innerHTML = (t.notes || []).map(n => '<li>' + esc(n) + '</li>').join('');
  }

  async function patchBuy(id, body) {
    try { await send('/api/builder/pick/' + id, body, 'PATCH'); await loadTodo(); }
    catch (e) { $('tdMsg').textContent = e.message; $('tdMsg').className = 'pl-msg w'; }
  }

  // ------------------------------------------------------------------ wiring
  function setAcct(a) { S.acct = a; $('plAcct').value = a; $('tdAcct').value = a; }
  async function show(v) {
    if (!S.ready) return;
    if (v === 'plan') await loadPlan();
    else if (v === 'todo') await loadTodo();
  }
  function current() { return (document.querySelector('.bld-tab.on') || {}).dataset ? document.querySelector('.bld-tab.on').dataset.v : 'plan'; }

  async function init() {
    if (!$('view-plan')) return;
    try {
      const [accts, srcs, st] = await Promise.all([api('/api/builder/accounts'), api('/api/builder/sources'), api('/api/builder/plan/states')]);
      S.accts = (accts.accounts || []).map(a => a.short);
      S.states = st.states || {};
      S.sources = (srcs.sources || []).filter(s => s.code !== 'FUND');
      S.srcOn = new Set(S.sources.map(s => s.code)); S.srcOn.add('MINE');
      const opts = S.accts.map(a => '<option value="' + esc(a) + '">' + esc(a) + '</option>').join('');
      $('plAcct').innerHTML = opts; $('tdAcct').innerHTML = opts;
      $('plFClass').innerHTML = '<option value="">All classes</option>' + CLASSES.filter(c => c !== 'Cash').map(c => '<option>' + c + '</option>').join('');
      setAcct(S.accts.includes('IRA') ? 'IRA' : S.accts[0]);
    } catch (e) { note('Could not load accounts: ' + e.message, true); return; }
    S.ready = true;
    const onAcct = ev => { setAcct(ev.target.value); show(current()); };
    $('plAcct').onchange = onAcct; $('tdAcct').onchange = onAcct;
    $('plSave').onclick = () => savePlan(false).catch(e => note(e.message, true));
    $('plActivate').onclick = onActivate;
    $('plOff').onclick = async () => { try { await send('/api/builder/plan/off?account=' + encodeURIComponent(S.acct), {}); S.page.state = S.page.draft ? 'draft' : 'none'; S.states[S.acct] = S.page.state; note('Plan turned off. ' + S.acct + ' is not checked.'); renderPlan(); } catch (e) { note(e.message, true); } };
    $('plStart').onchange = onStart;
    $('plMake').onclick = onMake;
    $('plClearTicks').onclick = () => { S.ticks = new Set(); renderNames(); };
    $('plFClass').onchange = renderNames; $('plFText').oninput = renderNames;
    $('plAddMine').onclick = async () => {
      const sym = $('plAddSym').value.trim();
      if (!sym) return;
      try { await send(withDate('/api/builder/my-stocks/' + encodeURIComponent(sym.toUpperCase())), {}, 'PUT'); $('plAddSym').value = ''; await refreshMine(); note(''); } catch (e) { note(e.message, true); }
    };
    const dp = $('datePicker'); if (dp) dp.addEventListener('change', () => show(current()));
    await show(current());
  }
  window.PlanTab = { show };
  document.addEventListener('DOMContentLoaded', init);
})();
