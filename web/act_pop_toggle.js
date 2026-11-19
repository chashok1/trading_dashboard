/* Action-popup hover on/off switch for the Builder (2026-11-18, user: like the 💬 switch on Actionable / Dashboard, but for the Action popup
 * that shows when you hover a Final Call code such as SA). On by default; the choice is remembered in this browser (own key, so it does not
 * touch the symbol-notes switch). Gate reader: targetOf() in actionable_pops_dash.js ([data-actpop] cells). */
(function () {
  'use strict';
  var KEY = 'bldActPopHover';
  function read() { try { return localStorage.getItem(KEY) !== '0'; } catch (e) { return true; } }
  var on = read();
  window.actPopHoverOn = function () { return on; };
  function paint(btn) {
    btn.classList.toggle('active', on);
    btn.style.opacity = on ? '1' : '0.45';
    btn.title = on ? 'Action popup on hover: ON (click to turn off)' : 'Action popup on hover: OFF (click to turn on)';
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  function mount() {
    var host = document.querySelector('header .controls');
    if (!host || document.getElementById('actPopToggle')) return;
    var btn = document.createElement('button');
    btn.type = 'button'; btn.id = 'actPopToggle'; btn.className = 'btn';
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
