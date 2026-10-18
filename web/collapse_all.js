/* Collapse / expand controls for the Dashboard (/), 2026-10-17, user-directed.
 * A small button group in the header: All | Left | Mid L | Mid R | Right. Each button collapses its columns' panels, or
 * expands them when they are all already collapsed.
 *  - Panels that already have their own arrow (the .msr-sort-btn with a down/up triangle) are driven by clicking that arrow,
 *    so their own saved state and redraw keep working.
 *  - Left and Right column panels without an arrow get a small chevron in their top-right corner (collapsed = a thin strip
 *    with the panel name). That state is remembered for the rest of the day.
 * Self-mounting; Dashboard only. */
(function () {
  'use strict';
  if (window.location.pathname.replace(/\/+$/, '') !== '') return;

  var KEY = 'dashPanelCollapsed';
  var NAMES = {
    riskDialBand: 'Risk Dial', heMktSituationPanel: 'MKT SIT', quadCardsPanel: 'Quads', quadSmallPanel: 'Quad windows',
    yieldCurveBand: 'Yield curve', moveVixBand: 'Volatility', creditBand: 'Credit', momentumBand: 'Momentum', crossAssetPanel: 'Cross-Asset', dashNotesBand: 'Notes', housekeepingBand: 'Housekeeping',
    macroCorrBand: '$ Corln', macroSectorsBand: 'Sectors', headwindBand: 'Headwind areas', spxRvBand: 'SPX realized vol',
    heInflPanel: 'INFL', quadOutlookSection: 'Quad Outlook', indicatorBand: 'E.IND', nearEarningsBand: 'Symbol'
  };
  var GROUPS = [
    { key: 'left', label: 'Left', sel: '.dial-changed-col', chevrons: true, tip: 'Left column' },
    { key: 'midl', label: 'Mid L', sel: '.rail-split-main', chevrons: false, tip: 'Middle column, left part (Hedgeye, Macro Rail, Themes, scorecards)' },
    { key: 'midr', label: 'Mid R', sel: '.rail-split-side', chevrons: false, tip: 'Middle column, right part (graphs, Accounts)' },
    { key: 'right', label: 'Right', sel: '.right-rail', chevrons: true, tip: 'Right column' }
  ];
  var UP = '▴', DOWN = '▾';

  function today() {
    var d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function loadSaved() {
    try {
      var o = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (o && o.d === today() && Array.isArray(o.ids)) return o.ids;
    } catch (e) {}
    return [];
  }
  function save() {
    var ids = [];
    document.querySelectorAll('.pc-collapsed').forEach(function (p) { if (p.id) ids.push(p.id); });
    try { localStorage.setItem(KEY, JSON.stringify({ d: today(), ids: ids })); } catch (e) {}
  }

  function arrowToggles(root) {
    return Array.prototype.filter.call(root.querySelectorAll('.msr-sort-btn'), function (b) {
      var t = (b.textContent || '').trim();
      return t === UP || t === DOWN;
    });
  }
  function chevronPanels(root) {
    return Array.prototype.filter.call(root.querySelectorAll('section.cockpit-band'), function (p) {
      if (p.parentElement && p.parentElement.closest('.cockpit-band')) return false;   // nested inside another panel
      if (p.querySelector('details')) return false;                                     // already compact, has its own toggle
      if (arrowToggles(p).length) return false;                                         // has its own arrow
      return true;
    });
  }

  function setPanel(p, c) {
    p.classList.toggle('pc-collapsed', c);
    var b = p.querySelector(':scope > .pc-chev');
    if (b) b.textContent = c ? UP : DOWN;
  }
  function ensureChevron(p) {
    p.classList.add('pc-panel');
    if (!p.getAttribute('data-pc-name')) p.setAttribute('data-pc-name', NAMES[p.id] || p.id || 'Panel');
    if (p.querySelector(':scope > .pc-chev')) return;
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'pc-chev';
    b.title = 'Collapse / expand this panel';
    b.textContent = p.classList.contains('pc-collapsed') ? UP : DOWN;
    b.addEventListener('click', function (e) { e.stopPropagation(); setPanel(p, !p.classList.contains('pc-collapsed')); save(); refresh(); });
    p.appendChild(b);
  }

  var observed = typeof WeakSet === 'function' ? new WeakSet() : null;
  function setupChevrons(g) {
    var root = document.querySelector(g.sel);
    if (!root) return;
    var saved = loadSaved();
    chevronPanels(root).forEach(function (p) {
      if (observed && !observed.has(p)) {
        observed.add(p);
        if (saved.indexOf(p.id) >= 0) p.classList.add('pc-collapsed');
        // Some panels are redrawn with innerHTML on the section itself, which removes the chevron: put it back.
        new MutationObserver(function () { ensureChevron(p); }).observe(p, { childList: true });
      }
      ensureChevron(p);
    });
  }

  function items(g) {
    var root = document.querySelector(g.sel);
    var out = [];
    if (!root) return out;
    arrowToggles(root).forEach(function (b) {
      out.push({
        collapsed: function () { return (b.textContent || '').trim() === UP; },
        set: function (c) { if (((b.textContent || '').trim() === UP) !== c) b.click(); }
      });
    });
    if (g.chevrons) chevronPanels(root).forEach(function (p) {
      out.push({ collapsed: function () { return p.classList.contains('pc-collapsed'); }, set: function (c) { setPanel(p, c); } });
    });
    return out;
  }
  function allCollapsed(list) { return list.length > 0 && list.every(function (i) { return i.collapsed(); }); }
  function apply(list, c) { list.forEach(function (i) { i.set(c); }); save(); setTimeout(refresh, 80); }

  var btns = {};
  function refresh() {
    var every = [];
    GROUPS.forEach(function (g) {
      var list = items(g); every = every.concat(list);
      var b = btns[g.key];
      if (b) b.textContent = (allCollapsed(list) ? UP : DOWN) + ' ' + g.label;
    });
    if (btns.all) btns.all.textContent = (allCollapsed(every) ? UP : DOWN) + ' All';
  }

  function mount() {
    var controls = document.querySelector('header .controls');
    if (!controls || document.getElementById('collapseCtl')) return;
    var wrap = document.createElement('span');
    wrap.id = 'collapseCtl'; wrap.className = 'cc-ctl';
    function add(key, label, tip, getList) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'cc-btn'; b.title = tip; b.textContent = DOWN + ' ' + label;
      b.addEventListener('click', function () { var l = getList(); apply(l, !allCollapsed(l)); });
      btns[key] = b; wrap.appendChild(b);
    }
    add('all', 'All', 'Collapse all panels on the Dashboard (or expand them when all are collapsed)', function () {
      return GROUPS.reduce(function (a, g) { return a.concat(items(g)); }, []);
    });
    GROUPS.forEach(function (g) { add(g.key, g.label, g.tip + ': collapse all (or expand when all are collapsed)', function () { return items(g); }); });
    controls.insertBefore(wrap, controls.firstChild);
  }

  function init() {
    mount();
    GROUPS.forEach(function (g) { if (g.chevrons) setupChevrons(g); });
    refresh();
    // Panels render late and some arrows are drawn by scripts after load: re-check for a while, then every few seconds.
    var n = 0;
    var t = setInterval(function () {
      GROUPS.forEach(function (g) { if (g.chevrons) setupChevrons(g); });
      refresh();
      if (++n > 20) { clearInterval(t); setInterval(refresh, 4000); }
    }, 1000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
