/* Notes browser + rule-candidate builder (P3).
 * Reads  GET /api/notes, /api/notes/source-types, /api/rule-candidates
 * Writes POST /api/rule-candidates
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var linked = {}; // note_id -> true

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  async function getJson(u) { var r = await fetch(u); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }

  function qs() {
    var p = [];
    if ($('q').value) p.push('q=' + encodeURIComponent($('q').value));
    if ($('ticker').value) p.push('ticker=' + encodeURIComponent($('ticker').value));
    if ($('sourceType').value) p.push('source_type=' + encodeURIComponent($('sourceType').value));
    if ($('date').value) p.push('date=' + encodeURIComponent($('date').value));
    return p.length ? '?' + p.join('&') : '';
  }

  function noteCard(n) {
    var sel = linked[n.note_id] ? ' sel' : '';
    var tickers = (n.tickers || []).join(', ');
    var snippet = (n.note_text || '').slice(0, 280);
    return '<div class="note-card' + sel + '" data-id="' + n.note_id + '">' +
      '<div class="note-meta">' + esc(n.note_date || '') + ' · ' + esc(n.source_type || '') +
      (n.analyst ? ' · ' + esc(n.analyst) : '') + (tickers ? ' · ' + esc(tickers) : '') +
      (n.quad ? ' · Quad' + esc(n.quad) : '') + '</div>' +
      '<div style="font-weight:600;">' + esc(n.subject || '(no subject)') + '</div>' +
      '<div style="color:#444;">' + esc(snippet) + (snippet.length >= 280 ? '…' : '') + '</div>' +
      (n.gmail_link ? '<a href="' + esc(n.gmail_link) + '" target="_blank" rel="noopener" style="font-size:10px;">open in Gmail</a>' : '') +
      '</div>';
  }

  async function loadNotes() {
    try {
      var rows = await getJson('/api/notes' + qs());
      $('count').textContent = rows.length + ' notes';
      $('notes').innerHTML = rows.length ? rows.map(noteCard).join('') : '<div style="color:#999;">No notes.</div>';
      Array.prototype.forEach.call(document.querySelectorAll('.note-card'), function (el) {
        el.addEventListener('click', function () {
          var id = el.getAttribute('data-id');
          if (linked[id]) { delete linked[id]; el.classList.remove('sel'); }
          else { linked[id] = true; el.classList.add('sel'); }
          $('linkedCount').textContent = Object.keys(linked).length;
        });
      });
    } catch (e) { $('notes').innerHTML = '<div style="color:#c33;">Load failed.</div>'; }
  }

  function candCard(c) {
    return '<div class="cand-card"><div style="font-weight:600;">' + esc(c.title || '(untitled)') +
      '<span class="pill">' + esc(c.status || '') + '</span></div>' +
      '<div style="color:#555;">' + esc(c.hypothesis || '') + '</div>' +
      '<div style="font-size:10px; color:#888;">notes: ' + ((c.linked_note_ids || []).join(', ') || '—') + '</div>' +
      '</div>';
  }
  async function loadCandidates() {
    try {
      var rows = await getJson('/api/rule-candidates');
      $('candidates').innerHTML = rows.length ? rows.map(candCard).join('') : '<div style="color:#999;">None yet.</div>';
    } catch (e) { $('candidates').innerHTML = '<div style="color:#c33;">Load failed.</div>'; }
  }

  async function createCandidate() {
    var body = {
      title: $('candTitle').value,
      hypothesis: $('candHyp').value,
      linked_note_ids: Object.keys(linked).map(Number),
    };
    if (!body.title) { $('createMsg').textContent = 'title required'; return; }
    try {
      var r = await fetch('/api/rule-candidates', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      $('createMsg').textContent = 'created ✓';
      $('candTitle').value = ''; $('candHyp').value = '';
      linked = {}; $('linkedCount').textContent = '0';
      Array.prototype.forEach.call(document.querySelectorAll('.note-card.sel'), function (el) { el.classList.remove('sel'); });
      loadCandidates();
      setTimeout(function () { $('createMsg').textContent = ''; }, 2500);
    } catch (e) { $('createMsg').textContent = 'failed'; }
  }

  async function init() {
    try {
      var types = await getJson('/api/notes/source-types');
      $('sourceType').innerHTML = '<option value="">All sources</option>' +
        types.map(function (t) { return '<option value="' + esc(t.source_type) + '">' + esc(t.source_type) + ' (' + t.count + ')</option>'; }).join('');
    } catch (e) { /* ignore */ }
    $('reload').addEventListener('click', loadNotes);
    $('clear').addEventListener('click', function () {
      $('q').value = ''; $('ticker').value = ''; $('sourceType').value = ''; $('date').value = ''; loadNotes();
    });
    $('createCand').addEventListener('click', createCandidate);
    loadNotes(); loadCandidates();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
