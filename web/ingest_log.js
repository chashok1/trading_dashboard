/* Ingest Log screen — vanilla JS, no dependencies. */

(function () {
  'use strict';

  // ── DOM refs ──────────────────────────────────────────────────────────────
  const channelSel = document.getElementById('channelSelect');
  const feedInput  = document.getElementById('feedInput');
  const dateInput  = document.getElementById('dateInput');
  const refreshBtn = document.getElementById('refreshBtn');
  const clearBtn   = document.getElementById('clearBtn');
  const rowCount   = document.getElementById('rowCount');
  const tbody      = document.getElementById('ingestBody');

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmtDatetime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString([], {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    });
  }

  function truncate(str, max) {
    if (!str) return '—';
    if (str.length <= max) return str;
    return str.slice(0, max) + '…';
  }

  function statusClass(s) {
    if (!s) return '';
    s = s.toLowerCase();
    if (s === 'loaded' || s === 'success' || s === 'ok') return 'status-loaded';
    if (s === 'error' || s === 'failed') return 'status-error';
    if (s === 'skipped') return 'status-skipped';
    return '';
  }

  // ── Build query string ────────────────────────────────────────────────────

  function buildQs() {
    const parts = ['limit=200'];
    const ch = channelSel.value.trim();
    const fd = feedInput.value.trim();
    const dt = dateInput.value.trim();
    if (ch) parts.push('channel=' + encodeURIComponent(ch));
    if (fd) parts.push('feed=' + encodeURIComponent(fd));
    if (dt) parts.push('date=' + encodeURIComponent(dt));
    return parts.join('&');
  }

  // ── Render ────────────────────────────────────────────────────────────────

  function renderRows(rows) {
    if (!rows || rows.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="8" style="color:var(--text-3);text-align:center;padding:20px;">' +
        'No records found.</td></tr>';
      rowCount.textContent = '0 rows';
      return;
    }

    rowCount.textContent = rows.length + ' row' + (rows.length === 1 ? '' : 's');

    const html = rows.map(function (r) {
      const isEmail = (r.source_kind === 'email');
      const emailBadge = isEmail
        ? '<span class="badge-email">email</span>'
        : '';

      const statusTxt = r.status || '—';
      const cls = statusClass(statusTxt);

      const refTrunc = truncate(r.source_ref, 60);
      const refTitle = r.source_ref ? ' title="' + escapeAttr(r.source_ref) + '"' : '';

      return '<tr>' +
        '<td style="white-space:nowrap;font-size:11px;color:var(--text-2);">' +
          fmtDatetime(r.processed_at) + '</td>' +
        '<td>' + esc(r.channel) + '</td>' +
        '<td>' + esc(r.source_kind) + emailBadge + '</td>' +
        '<td style="font-weight:600;">' + esc(r.feed) + '</td>' +
        '<td style="color:var(--text-2);">' + esc(r.target_tab) + '</td>' +
        '<td style="font-variant-numeric:tabular-nums;">' + esc(r.data_date) + '</td>' +
        '<td class="' + cls + '">' + esc(statusTxt) + '</td>' +
        '<td><span class="source-ref"' + refTitle + '>' + esc(refTrunc) + '</span></td>' +
      '</tr>';
    }).join('');

    tbody.innerHTML = html;
  }

  function esc(v) {
    if (v == null) return '—';
    return String(v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escapeAttr(v) {
    if (!v) return '';
    return String(v)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;');
  }

  // ── Fetch ─────────────────────────────────────────────────────────────────

  function load() {
    rowCount.textContent = 'Loading…';
    tbody.innerHTML =
      '<tr><td colspan="8" style="color:var(--text-3);text-align:center;padding:20px;">' +
      'Loading…</td></tr>';

    fetch('/api/ingest-log?' + buildQs())
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(renderRows)
      .catch(function (e) {
        tbody.innerHTML =
          '<tr><td colspan="8" style="color:#b91c1c;text-align:center;padding:20px;">' +
          'Error: ' + esc(e.message) + '</td></tr>';
        rowCount.textContent = 'error';
      });
  }

  // ── Wire up events ────────────────────────────────────────────────────────

  channelSel.addEventListener('change', load);
  feedInput.addEventListener('change', load);
  feedInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') load();
  });
  dateInput.addEventListener('change', load);
  refreshBtn.addEventListener('click', load);

  clearBtn.addEventListener('click', function () {
    channelSel.value = '';
    feedInput.value  = '';
    dateInput.value  = '';
    load();
  });

  // ── Initial load ──────────────────────────────────────────────────────────
  load();

}());
