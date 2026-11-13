/* Symbol-hover Notes popup on/off switch (Dashboard + Actionable). 2026-11-13, user: a small toggle; popup shows only when it is on.
 * Off by default; the choice is remembered in this browser. Gate readers: showNotesPop (actionable_pops.js) and the Dashboard hover (actionable_pops_dash.js). */
(function () {
  'use strict';
  var KEY = 'symNotesPop';
  function read() { try { return localStorage.getItem(KEY) === '1'; } catch (e) { return false; } }
  var on = read();
  window.symNotesPopOn = function () { return on; };
  function paint(btn) {
    btn.classList.toggle('active', on);
    btn.style.opacity = on ? '1' : '0.45';
    btn.title = on ? 'Symbol hover notes: ON (click to turn off)' : 'Symbol hover notes: OFF (click to turn on)';
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  function mount() {
    var host = document.querySelector('header .controls');
    if (!host || document.getElementById('symNotesToggle')) return;
    var btn = document.createElement('button');
    btn.type = 'button'; btn.id = 'symNotesToggle'; btn.className = 'btn';
    btn.textContent = '💬';
    btn.style.cssText = 'padding:1px 6px;font-size:12px;line-height:1.2;';
    paint(btn);
    btn.addEventListener('click', function () {
      on = !on;
      try { localStorage.setItem(KEY, on ? '1' : '0'); } catch (e) { /* ignore */ }
      paint(btn);
      if (!on && window.hideSourcePop) { try { window.hideSourcePop(); } catch (e) { /* ignore */ } }
    });
    host.insertBefore(btn, host.firstChild);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
