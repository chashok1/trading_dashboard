/* Dashboard Notes panel — sticky notes with an optional effective/
 * expiration date window. Reads/writes /api/dashboard-notes.
 * Renders into #dashNotesBody (inside the #dashNotesBand .cockpit-band,
 * left column, just below the Mkt Situation panel). Not deferred — self-
 * initializes on DOMContentLoaded like app.js's other loaders.
 * User: "i need to be able to add notes with effective date and expiration
 * dates. a panel to display and edit the entries."
 */
(function () {
  'use strict';

  var fetchJson = window.fetchJson || async function (url, opts) {
    var r = await fetch(url, opts);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  var esc = window.escapeHtml || function (s) { return String(s == null ? '' : s); };

  var _notes = [];
  var _editingId = null;   // note id being edited, or null when adding/form closed
  var _formOpen = false;
  var _showAll = false;    // reveal upcoming/expired notes too (default view = active only)

  // "Today" is the dashboard's selected as_of date (#datePicker), NOT the
  // system clock -- this is a historical snapshot viewer, same convention
  // every other "today"-dependent computation on this dashboard follows
  // (see api/routers/dash.py::list_dashboard_notes). Same pattern
  // hedgeye_panel.js's currentDate() already uses to read the shared
  // picker without any cross-script state dependency.
  function currentDate() {
    var dp = document.getElementById('datePicker');
    return (dp && dp.value) ? dp.value : '';
  }

  function fmtMD(iso) {
    if (!iso) return '';
    var p = String(iso).split('-');
    return p.length >= 3 ? p[1] + '/' + p[2] : iso;
  }

  function asOfLocalDate() {
    var d = currentDate();
    return d ? new Date(d + 'T00:00:00') : new Date();
  }

  function toLocalDate(iso) {
    return iso ? new Date(iso + 'T00:00:00') : null;
  }

  // Mirrors the API's active_only=true window: both bounds open-ended,
  // inclusive on both ends, evaluated against the selected as_of date (not
  // the system clock). Not-yet-effective and past-expiration both count as
  // inactive.
  function isActive(n) {
    var t = asOfLocalDate();
    var eff = toLocalDate(n.effective_date);
    var exp = toLocalDate(n.expiration_date);
    if (eff && eff > t) return false;
    if (exp && exp < t) return false;
    return true;
  }

  function statusTag(n) {
    var t = asOfLocalDate();
    var eff = toLocalDate(n.effective_date);
    var exp = toLocalDate(n.expiration_date);
    if (eff && eff > t) return 'upcoming';
    if (exp && exp < t) return 'expired';
    return null;
  }

  function dateRangeLabel(n) {
    if (n.effective_date && n.expiration_date) return 'from ' + fmtMD(n.effective_date) + ' – until ' + fmtMD(n.expiration_date);
    if (n.expiration_date) return 'until ' + fmtMD(n.expiration_date);
    if (n.effective_date) return 'from ' + fmtMD(n.effective_date);
    return 'no expiration';
  }

  function noteRowHtml(n) {
    var tag = statusTag(n);
    var tagHtml = tag ? ' &middot; <span style="text-transform:uppercase;">' + tag + '</span>' : '';
    return '<div class="dash-note-row" style="display:flex; gap:6px; align-items:flex-start; ' +
      'padding:6px 0; border-bottom:1px solid var(--border);' + (tag ? ' opacity:0.55;' : '') + '">' +
      '<div style="flex:1; min-width:0;">' +
        '<div style="font-size:11.5px; line-height:1.45; color:var(--text-1); white-space:pre-wrap;">' + esc(n.note_text) + '</div>' +
        '<div style="font-size:9.5px; color:var(--text-3); margin-top:2px;">' + esc(dateRangeLabel(n)) + tagHtml + '</div>' +
      '</div>' +
      '<div style="display:flex; gap:2px; flex-shrink:0;">' +
        '<button class="btn btn-sm dash-note-edit" data-id="' + n.id + '" type="button" title="Edit" style="padding:1px 6px;">&#9998;</button>' +
        '<button class="btn btn-sm dash-note-del" data-id="' + n.id + '" type="button" title="Delete" style="padding:1px 6px;">&#10005;</button>' +
      '</div>' +
    '</div>';
  }

  function formHtml(n) {
    n = n || {};
    return '<div id="dashNoteForm" style="margin-top:6px; padding:8px; background:var(--bg); border:1px solid var(--border); border-radius:5px;">' +
      '<div style="display:flex; gap:8px; margin-bottom:6px;">' +
        '<label style="font-size:10px; color:var(--text-3); flex:1;">From<br>' +
          '<input type="date" id="dashNoteFrom" value="' + esc(n.effective_date || '') + '" style="width:100%; font-size:11px; box-sizing:border-box;"></label>' +
        '<label style="font-size:10px; color:var(--text-3); flex:1;">To<br>' +
          '<input type="date" id="dashNoteTo" value="' + esc(n.expiration_date || '') + '" style="width:100%; font-size:11px; box-sizing:border-box;"></label>' +
      '</div>' +
      '<textarea id="dashNoteText" rows="3" placeholder="Note..." ' +
        'style="width:100%; font-size:11.5px; box-sizing:border-box; resize:vertical; font-family:inherit;">' + esc(n.note_text || '') + '</textarea>' +
      '<div id="dashNoteFormErr" style="color:#c0392b; font-size:10px; margin-top:2px; display:none;"></div>' +
      '<div style="display:flex; gap:6px; margin-top:6px;">' +
        '<button class="btn btn-sm btn-primary" id="dashNoteSave" type="button">Save</button>' +
        '<button class="btn btn-sm" id="dashNoteCancel" type="button">Cancel</button>' +
      '</div>' +
    '</div>';
  }

  function render() {
    var el = document.getElementById('dashNotesBody');
    if (!el) return;
    var visible = _showAll ? _notes : _notes.filter(isActive);
    var list = visible.length
      ? visible.map(noteRowHtml).join('')
      : '<div style="color:var(--text-3); font-size:11px; padding:6px 0;">No notes.</div>';
    var editingNote = _editingId != null ? _notes.find(function (n) { return n.id === _editingId; }) : null;

    el.innerHTML =
      '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">' +
        '<span style="font-size:12px; letter-spacing:0.08em; text-transform:uppercase; color:var(--text-3); font-weight:600;">Notes</span>' +
        '<div style="display:flex; gap:8px; align-items:center;">' +
          '<label style="font-size:9.5px; color:var(--text-3); display:flex; gap:3px; align-items:center; cursor:pointer;">' +
            '<input type="checkbox" id="dashNoteShowAll"' + (_showAll ? ' checked' : '') + '> show all</label>' +
          '<button class="btn btn-sm btn-primary" id="dashNoteAddBtn" type="button">+ Add</button>' +
        '</div>' +
      '</div>' +
      '<div id="dashNotesList">' + list + '</div>' +
      (_formOpen ? formHtml(editingNote) : '');

    wire();
  }

  function openAddForm() {
    _editingId = null;
    _formOpen = true;
    render();
    var t = document.getElementById('dashNoteText');
    if (t) t.focus();
  }

  function openEditForm(id) {
    _editingId = id;
    _formOpen = true;
    render();
    var t = document.getElementById('dashNoteText');
    if (t) t.focus();
  }

  function closeForm() {
    _editingId = null;
    _formOpen = false;
    render();
  }

  async function saveForm() {
    var textEl = document.getElementById('dashNoteText');
    var fromEl = document.getElementById('dashNoteFrom');
    var toEl = document.getElementById('dashNoteTo');
    var errEl = document.getElementById('dashNoteFormErr');
    var noteText = (textEl.value || '').trim();
    var from = fromEl.value || null;
    var to = toEl.value || null;
    if (!noteText) {
      errEl.textContent = 'Note text is required.';
      errEl.style.display = 'block';
      return;
    }
    if (from && to && from > to) {
      errEl.textContent = 'From date must be on or before To date.';
      errEl.style.display = 'block';
      return;
    }
    var body = JSON.stringify({ note_text: noteText, effective_date: from, expiration_date: to });
    try {
      if (_editingId != null) {
        await fetchJson('/api/dashboard-notes/' + _editingId, { method: 'PUT', body: body });
      } else {
        await fetchJson('/api/dashboard-notes', { method: 'POST', body: body });
      }
      _formOpen = false;
      _editingId = null;
      await load();
    } catch (e) {
      errEl.textContent = 'Save failed: ' + e.message;
      errEl.style.display = 'block';
    }
  }

  async function deleteNote(id) {
    if (!window.confirm('Delete this note?')) return;
    try {
      await fetchJson('/api/dashboard-notes/' + id, { method: 'DELETE' });
      await load();
    } catch (e) { /* non-critical */ }
  }

  function wire() {
    var addBtn = document.getElementById('dashNoteAddBtn');
    if (addBtn) addBtn.addEventListener('click', openAddForm);
    var showAllCb = document.getElementById('dashNoteShowAll');
    if (showAllCb) showAllCb.addEventListener('change', function () { _showAll = this.checked; render(); });
    var saveBtn = document.getElementById('dashNoteSave');
    if (saveBtn) saveBtn.addEventListener('click', saveForm);
    var cancelBtn = document.getElementById('dashNoteCancel');
    if (cancelBtn) cancelBtn.addEventListener('click', closeForm);
    document.querySelectorAll('.dash-note-edit').forEach(function (btn) {
      btn.addEventListener('click', function () { openEditForm(+btn.getAttribute('data-id')); });
    });
    document.querySelectorAll('.dash-note-del').forEach(function (btn) {
      btn.addEventListener('click', function () { deleteNote(+btn.getAttribute('data-id')); });
    });
  }

  async function load() {
    try {
      var data = await fetchJson('/api/dashboard-notes?active_only=false');
      _notes = data.notes || [];
    } catch (e) {
      _notes = [];
    }
    render();
  }

  function init() {
    load();
    // Re-check active/upcoming/expired status on date change, same trigger
    // every other dashboard panel refreshes on (no need to re-fetch notes
    // themselves, just re-evaluate which are active for a new "as of" date).
    var dp = document.getElementById('datePicker');
    if (dp) dp.addEventListener('change', render);
    var rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', function () { setTimeout(load, 300); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
