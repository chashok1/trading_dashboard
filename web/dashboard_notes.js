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
  var _formImportance = 'medium';  // selection in the currently-open add/edit form
  var _dragId = null;      // note id currently mid-drag, or null

  // 2026-08-10 -- color-by-importance: a left-border stripe + faint tint on
  // each row (high=red/medium=amber/low=gray). Deliberately avoids green --
  // this app already uses green/red for bullish/bearish elsewhere
  // (hedgeye_panel.js::sideColor), and reusing it here for "low priority"
  // would read as a market-direction signal instead of an urgency one.
  // User: "color it by importance (high, medium, low) (choose the best
  // way)."
  var IMPORTANCE = {
    high:   { label: 'High',   color: '#dc2626', bg: 'rgba(220,38,38,0.07)' },
    medium: { label: 'Medium', color: '#d97706', bg: 'rgba(217,119,6,0.07)' },
    low:    { label: 'Low',    color: '#6b7280', bg: 'rgba(107,114,128,0.06)' },
  };
  function importanceInfo(n) {
    return IMPORTANCE[n && n.importance] || IMPORTANCE.medium;
  }

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

  // 2026-08-10 -- drag-to-reorder: the grip handle (not the whole row) is
  // the draggable element, so dragging never fights with selecting note
  // text or clicking Edit/Delete. dragstart sets the drag image to the
  // FULL row (not just the small handle) so what the user sees moving
  // under the cursor is the whole note, not a tiny icon. Drop position is
  // resolved in wire()'s dragover/drop handlers by comparing cursor Y to
  // each row's own vertical midpoint. User: "a way to move up or down by
  // dragging the notes."
  function noteRowHtml(n) {
    var tag = statusTag(n);
    var tagHtml = tag ? ' &middot; <span style="text-transform:uppercase;">' + tag + '</span>' : '';
    var imp = importanceInfo(n);
    return '<div class="dash-note-row" data-id="' + n.id + '" style="display:flex; gap:6px; align-items:flex-start; ' +
      'padding:6px 8px; margin-bottom:3px; border-radius:3px; border-left:3px solid ' + imp.color + '; ' +
      'background:' + imp.bg + ';' + (tag ? ' opacity:0.55;' : '') + '">' +
      '<span class="dash-note-handle" data-id="' + n.id + '" draggable="true" title="Drag to reorder" ' +
        'style="cursor:grab; color:var(--text-3); font-size:12px; line-height:1.6; flex-shrink:0; user-select:none;">&#8942;&#8942;</span>' +
      '<div style="flex:1; min-width:0;">' +
        '<div style="font-size:11.5px; line-height:1.45; color:var(--text-1); white-space:pre-wrap;">' + esc(n.note_text) + '</div>' +
        '<div style="font-size:9.5px; color:var(--text-3); margin-top:2px;">' +
          '<span style="font-weight:600; color:' + imp.color + ';">' + imp.label + '</span> &middot; ' +
          esc(dateRangeLabel(n)) + tagHtml +
        '</div>' +
      '</div>' +
      '<div style="display:flex; gap:2px; flex-shrink:0;">' +
        '<button class="btn btn-sm dash-note-edit" data-id="' + n.id + '" type="button" title="Edit" style="padding:1px 6px;">&#9998;</button>' +
        '<button class="btn btn-sm dash-note-del" data-id="' + n.id + '" type="button" title="Delete" style="padding:1px 6px;">&#10005;</button>' +
      '</div>' +
    '</div>';
  }

  // Importance picker: three toggle buttons colored in their own importance
  // color (filled when selected, outlined/muted otherwise) instead of a
  // plain <select> -- picking a color directly is a clearer match to what
  // the row itself will look like than reading a text label would be.
  // 2026-08-10 -- picking a button restyles the buttons IN PLACE
  // (updateImportanceButtonStyles) rather than calling render(), which
  // would rebuild the whole form from _notes' saved data and wipe out
  // whatever the user had typed/half-edited in the textarea or date
  // fields. User: "changing the priority should not clear the text
  // entered while editing the note."
  function _impBtnStyle(key, selected) {
    var imp = IMPORTANCE[key];
    return 'flex:1; padding:3px 6px; font-size:10.5px; font-weight:600; border-radius:3px; cursor:pointer; ' +
      'border:1px solid ' + imp.color + '; ' +
      (selected ? 'background:' + imp.color + '; color:#fff;' : 'background:transparent; color:' + imp.color + ';');
  }

  function importancePickerHtml() {
    return '<div style="display:flex; gap:4px; margin-bottom:6px;">' +
      Object.keys(IMPORTANCE).map(function (key) {
        return '<button type="button" class="dash-note-imp-btn" data-imp="' + key + '" style="' +
          _impBtnStyle(key, _formImportance === key) + '">' + IMPORTANCE[key].label + '</button>';
      }).join('') +
    '</div>';
  }

  function updateImportanceButtonStyles() {
    document.querySelectorAll('.dash-note-imp-btn').forEach(function (btn) {
      var key = btn.getAttribute('data-imp');
      btn.setAttribute('style', _impBtnStyle(key, _formImportance === key));
    });
  }

  function formHtml(n) {
    n = n || {};
    return '<div id="dashNoteForm" style="margin-top:6px; padding:8px; background:var(--bg); border:1px solid var(--border); border-radius:5px;">' +
      importancePickerHtml() +
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
    _formImportance = 'medium';
    _formOpen = true;
    render();
    var t = document.getElementById('dashNoteText');
    if (t) t.focus();
  }

  function openEditForm(id) {
    var n = _notes.find(function (x) { return x.id === id; });
    _editingId = id;
    _formImportance = (n && n.importance) || 'medium';
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
    var body = JSON.stringify({ note_text: noteText, effective_date: from, expiration_date: to, importance: _formImportance });
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

  // 2026-08-10 -- drag-and-drop reorder. _notes is already in sort_order
  // order (server-side ORDER BY), so "the row above/below the drop point"
  // maps directly to "the neighbor in _notes with the next/previous
  // index" -- no separate lookup needed. Only the ONE dragged note's
  // sort_order changes (midpoint of its new neighbors); everything else is
  // untouched, so a drag never renumbers notes hidden by the active-only
  // filter.
  async function reorderTo(draggedId, targetId, before) {
    if (draggedId === targetId) return;
    var visible = _showAll ? _notes : _notes.filter(isActive);
    var targetIdx = visible.findIndex(function (n) { return n.id === targetId; });
    if (targetIdx < 0) return;
    var dropIdx = before ? targetIdx : targetIdx + 1;
    var above = visible[dropIdx - 1];
    var below = visible[dropIdx];
    if (above && above.id === draggedId) return;   // dropped in its own spot
    if (below && below.id === draggedId) return;
    var newSortOrder = (above && below) ? (above.sort_order + below.sort_order) / 2
      : above ? above.sort_order + 1
      : below ? below.sort_order - 1
      : 0;
    try {
      await fetchJson('/api/dashboard-notes/' + draggedId + '/sort-order', {
        method: 'PUT', body: JSON.stringify({ sort_order: newSortOrder }),
      });
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
    document.querySelectorAll('.dash-note-imp-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        _formImportance = btn.getAttribute('data-imp');
        updateImportanceButtonStyles();
      });
    });

    // Drag source: the grip handle only (not the whole row), so drag never
    // fights with text selection or the Edit/Delete buttons. Drag image is
    // set to the full row so the whole note appears to move, not just the
    // small handle icon.
    document.querySelectorAll('.dash-note-handle').forEach(function (handle) {
      handle.addEventListener('dragstart', function (e) {
        _dragId = +handle.getAttribute('data-id');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(_dragId));
        var row = handle.closest('.dash-note-row');
        if (row) e.dataTransfer.setDragImage(row, 12, 12);
      });
      handle.addEventListener('dragend', function () { _dragId = null; });
    });
    // Drop targets: delegate dragover/drop to the list container so a
    // single listener covers every row, re-wired fresh on each render.
    var list = document.getElementById('dashNotesList');
    if (list) {
      list.addEventListener('dragover', function (e) {
        if (_dragId == null) return;
        var row = e.target.closest('.dash-note-row');
        if (!row) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
      });
      list.addEventListener('drop', function (e) {
        if (_dragId == null) return;
        var row = e.target.closest('.dash-note-row');
        if (!row) return;
        e.preventDefault();
        var targetId = +row.getAttribute('data-id');
        var rect = row.getBoundingClientRect();
        var before = (e.clientY - rect.top) < rect.height / 2;
        reorderTo(_dragId, targetId, before);
        _dragId = null;
      });
    }
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
