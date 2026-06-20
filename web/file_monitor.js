const $ = (id) => document.getElementById(id);

const state = {
    summary: null,
    schedule: null,
    etlRuns: null,
    deriveRuns: null,
    currentLimit: 50,
    currentFileTypeFilter: '',
    currentSchedulerLevelFilter: '',
    currentSchedulerFileFilter: '',
    refreshInterval: null,
    countdownInterval: null,
    countdownSeconds: 60,
};


// ─── Run-Missing-Derives button ──────────────────────────────────────
async function runMissingDerives(force = false) {
    const btn = document.getElementById(force ? 'forceRederiveBtn' : 'runMissingDerivesBtn');
    const stat = document.getElementById('missingDerivesStatus');
    const daysSel = document.getElementById('missingDerivesDays');
    if (!btn || !stat) return;
    const lastN = daysSel ? parseInt(daysSel.value, 10) : 7;
    let qs = (lastN && lastN > 0) ? `?last_n_days=${lastN}` : '';
    if (force) qs += (qs ? '&' : '?') + 'force=true';
    const what = force ? 'already-derived' : 'missing';
    // 1) Preview which dates need derives.
    stat.textContent = ' loading…';
    let preview;
    try {
        const r = await fetch('/api/monitor/derive-missing' + qs);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        preview = await r.json();
    } catch (e) {
        stat.textContent = ' preview failed: ' + e.message;
        return;
    }
    const dates = preview.dates || [];
    if (!dates.length) {
        stat.textContent = ` no ${what} dates in last ${lastN} day(s) 👍`;
        setTimeout(() => { stat.textContent = ''; }, 3000);
        return;
    }
    // 2) Confirm before running.
    const msg = `Run derive_all for ${dates.length} ${what} date(s) in last ${lastN} day(s)?\n\n` +
                `Oldest→newest: ${dates[0]} → ${dates[dates.length - 1]}` +
                (dates.length > 8 ? `\n(showing range; ${dates.length} total)` : '');
    if (!confirm(msg)) {
        stat.textContent = ' cancelled';
        setTimeout(() => { stat.textContent = ''; }, 3000);
        return;
    }
    // 3) Run.
    btn.disabled = true;
    stat.textContent = ` running ${dates.length} date(s)…`;
    try {
        const r = await fetch('/api/monitor/derive-missing/run' + qs, { method: 'POST' });
        const data = await r.json();
        if (!r.ok || !data.success) {
            stat.textContent = ' failed: ' + (data.msg || `HTTP ${r.status}`);
            return;
        }
        const errs = (data.results || []).filter(x => x.status === 'failed').length;
        const ok   = (data.results || []).filter(x => x.status === 'success').length;
        stat.textContent = ` done: ${ok} ok` + (errs ? `, ${errs} err` : '');
        // Refresh derive-runs panel so the user sees the new rows.
        if (typeof loadDeriveRuns === 'function') loadDeriveRuns();
        if (typeof loadSummary === 'function') loadSummary();
    } catch (e) {
        stat.textContent = ' error: ' + e.message;
    } finally {
        btn.disabled = false;
        setTimeout(() => { stat.textContent = ''; }, 8000);
    }
}

// ─── Run-Stale-Derives button ────────────────────────────────────────
async function runStaleDerives() {
    const btn = document.getElementById('runStaleDerivesBtn');
    const stat = document.getElementById('staleDerivesStatus');
    if (!btn || !stat) return;
    stat.textContent = ' loading…';
    let preview;
    try {
        const r = await fetch('/api/monitor/derive-stale');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        preview = await r.json();
    } catch (e) {
        stat.textContent = ' preview failed: ' + e.message;
        return;
    }
    const dates = preview.dates || [];
    if (!dates.length) {
        stat.textContent = ' no stale dates 👍';
        setTimeout(() => { stat.textContent = ''; }, 3000);
        return;
    }
    const msg = `Re-derive ${dates.length} stale date(s)?\n\n` +
                `${dates[0]} → ${dates[dates.length - 1]}`;
    if (!confirm(msg)) {
        stat.textContent = ' cancelled';
        setTimeout(() => { stat.textContent = ''; }, 3000);
        return;
    }
    btn.disabled = true;
    stat.textContent = ` re-deriving ${dates.length} date(s)…`;
    try {
        const r = await fetch('/api/monitor/derive-stale/run', { method: 'POST' });
        const data = await r.json();
        if (!r.ok || !data.success) {
            stat.textContent = ' failed: ' + (data.msg || `HTTP ${r.status}`);
            return;
        }
        const ok = (data.healed || []).length;
        const errs = (data.failed || []).length;
        stat.textContent = ` done: ${ok} healed` + (errs ? `, ${errs} err` : '');
        if (typeof loadDeriveRuns === 'function') loadDeriveRuns();
        if (typeof loadSummary === 'function') loadSummary();
    } catch (e) {
        stat.textContent = ' error: ' + e.message;
    } finally {
        btn.disabled = false;
        setTimeout(() => { stat.textContent = ''; }, 8000);
    }
}

async function loadAll() {
    // All fetches restored. The scheduler's heartbeat is now written
    // atomically (os.replace → temp → final), so the API's read can no
    // longer collide with the scheduler's write. Diagnostic comments
    // kept above the function for reference if we ever need to bisect again.
    await loadSummary();
    await loadSchedule();
    await loadEtlRuns();
    await loadDeriveRuns();
    await loadSchedulerOutput();
    await loadSchedulerStatus();
    await loadSchedulerLevels();
    resetCountdown();
}

async function loadSchedulerStatus() {
    try {
        const resp = await fetch('/api/monitor/scheduler');
        const s = await resp.json();
        renderSchedulerStatus(s);
    } catch (e) {
        renderSchedulerStatus(null);
    }
}

async function loadStartupStatus() {
    try {
        const resp = await fetch('/api/monitor/startup');
        const s = await resp.json();
        renderStartupStatus(s);
    } catch (e) {
        renderStartupStatus(null);
    }
}

function renderStartupStatus(s) {
    const schedDot  = $('startupSchedDot');
    const schedText = $('startupSchedText');
    const appDot    = $('startupAppDot');
    const appText   = $('startupAppText');
    const regSchedBtn = $('registerSchedBtn');
    const regAppBtn   = $('registerAppBtn');
    const unregBtn    = $('unregisterBtn');

    const unknown = !s;
    const schedOn = s && s.scheduler_registered;
    const appOn   = s && s.app_registered;

    // ETL Scheduler dot + button
    schedDot.style.background = unknown ? 'var(--text-3)' : schedOn ? 'var(--bull)' : 'var(--bear)';
    schedText.textContent = unknown ? 'Scheduler auto-start: ?' : schedOn ? 'Scheduler auto-start: ON' : 'Scheduler auto-start: OFF';
    schedText.style.color = unknown ? 'var(--text-2)' : schedOn ? 'var(--bull)' : 'var(--bear)';
    regSchedBtn.style.display = (!unknown && !schedOn) ? '' : 'none';

    // Trading App dot + button
    appDot.style.background = unknown ? 'var(--text-3)' : appOn ? 'var(--bull)' : 'var(--bear)';
    appText.textContent = unknown ? 'App auto-start: ?' : appOn ? 'App auto-start: ON' : 'App auto-start: OFF';
    appText.style.color = unknown ? 'var(--text-2)' : appOn ? 'var(--bull)' : 'var(--bear)';
    regAppBtn.style.display = (!unknown && !appOn) ? '' : 'none';

    // Unregister shown when either is ON
    unregBtn.style.display = (!unknown && (schedOn || appOn)) ? '' : 'none';
}

function renderSchedulerStatus(s) {
    const dot      = $('schedulerDot');
    const text     = $('schedulerText');
    const startBtn = $('startSchedulerBtn');
    const stopBtn  = $('stopSchedulerBtn');

    // Show or hide the duplicate-warning banner. Created on-demand so we don't
    // need to edit the HTML.
    let warn = $('schedulerWarn');
    if (!warn) {
        warn = document.createElement('div');
        warn.id = 'schedulerWarn';
        warn.style.cssText = 'margin: 6px 0; padding: 6px 10px; ' +
            'background:#fee2e2; border:1px solid #fca5a5; border-radius:4px; ' +
            'color:#7f1d1d; font-size:11px; line-height:1.5; display:none;';
        if (text && text.parentNode) {
            text.parentNode.insertBefore(warn, text.nextSibling);
        }
    }

    // Simple state: running or stopped (from OS file-lock probe).
    const hint = $('schedulerHint');
    if (!s || !s.running) {
        dot.style.background = 'var(--bear)';
        text.textContent = 'ETL Scheduler — Stopped';
        text.style.color = 'var(--bear)';
        if (hint) hint.textContent = '— start with `python -m etl.scheduler` in a terminal';
    } else {
        dot.style.background = 'var(--bull)';
        text.textContent = 'ETL Scheduler — Running';
        text.style.color = 'var(--bull)';
        if (hint) hint.textContent = '';
    }
    // Buttons stay hidden regardless of state.
    if (startBtn) startBtn.style.display = 'none';
    if (stopBtn)  stopBtn.style.display = 'none';
    // Warning banner stays hidden — duplicate detection retired with the
    // PID-based heartbeat. OS lock guarantees at most one running instance.
    if (warn) warn.style.display = 'none';
}

async function loadSummary() {
    try {
        const resp = await fetch('/api/monitor/summary');
        state.summary = await resp.json();
        renderSummary();
    } catch (e) {
        console.error('Failed to load summary:', e);
    }
}

async function loadSchedule() {
    try {
        const resp = await fetch('/api/monitor/schedule');
        state.schedule = await resp.json();
        renderSchedule();
        updateFileTypeFilterOptions();
    } catch (e) {
        console.error('Failed to load schedule:', e);
    }
}

async function loadEtlRuns() {
    try {
        const limit = state.currentLimit;
        const ft = state.currentFileTypeFilter ? `&file_type=${state.currentFileTypeFilter}` : '';
        const resp = await fetch(`/api/monitor/etl-runs?limit=${limit}${ft}`);
        state.etlRuns = await resp.json();
        renderEtlRuns();
    } catch (e) {
        console.error('Failed to load ETL runs:', e);
    }
}

async function loadDeriveRuns() {
    try {
        const resp = await fetch('/api/monitor/derive-runs');
        state.deriveRuns = await resp.json();
        renderDeriveRuns();
        updateLastRefreshed();
    } catch (e) {
        console.error('Failed to load derive runs:', e);
    }
}

async function loadSchedulerOutput() {
    try {
        const level = state.currentSchedulerLevelFilter ? `&level=${state.currentSchedulerLevelFilter}` : '';
        const ft = state.currentSchedulerFileFilter ? `&file_type=${encodeURIComponent(state.currentSchedulerFileFilter)}` : '';
        const resp = await fetch(`/api/monitor/scheduler/output?last_n=500${level}${ft}`);
        const data = await resp.json();
        renderSchedulerOutput(data.rows);
    } catch (e) {
        console.error('Failed to load scheduler output:', e);
    }
}

async function loadSchedulerLevels() {
    try {
        const resp = await fetch('/api/monitor/scheduler/levels');
        const data = await resp.json();
        updateSchedulerLevelFilterOptions(data.levels || []);
    } catch (e) {
        console.error('Failed to load scheduler levels:', e);
    }
}

async function doReprocess(btn, filePath, fileType) {
    try {
        btn.classList.add('spinning');
        btn.disabled = true;
        btn.title = 'Processing...';

        const resp = await fetch(`/api/monitor/reprocess?file_path=${encodeURIComponent(filePath)}&file_type=${encodeURIComponent(fileType)}`, {
            method: 'POST'
        });

        if (!resp.ok) {
            const error = await resp.text();
            const msg = `[ERROR] Reprocess failed (HTTP ${resp.status}): ${error}`;
            console.error(msg);
            addSchedulerOutputLog('ERROR', msg, fileType);
            await loadSchedulerOutput();
            btn.classList.remove('spinning');
            btn.disabled = false;
            btn.title = 'Reprocess file';
            return;
        }

        const result = await resp.json();
        if (result.status === 'error') {
            const msg = `[ERROR] Reprocess error: ${result.msg || 'Unknown error'}`;
            console.error(msg);
            addSchedulerOutputLog('ERROR', msg, fileType);
            await loadSchedulerOutput();
            btn.classList.remove('spinning');
            btn.disabled = false;
            btn.title = 'Reprocess file';
            return;
        }

        // Success — refresh the schedule grid
        btn.classList.remove('spinning');
        btn.disabled = false;
        btn.title = 'Reprocess file';
        await loadSchedule();
        await loadSummary();
        await loadSchedulerOutput();
    } catch (e) {
        const msg = `[EXCEPTION] Reprocess failed: ${e.message}`;
        console.error(msg, e);
        addSchedulerOutputLog('ERROR', msg, fileType);
        await loadSchedulerOutput();
        btn.classList.remove('spinning');
        btn.disabled = false;
        btn.title = 'Reprocess file';
    }
}

function updateSchedulerLevelFilterOptions(levels) {
    const select = $('schedulerLevelFilter');
    const currentValue = select.value;

    // Keep only the default options (All levels, Errors, Warnings, Info)
    const defaultOptions = Array.from(select.options).filter(o => o.value === '' || ['ERROR', 'WARNING', 'INFO'].includes(o.value));
    select.innerHTML = '';
    defaultOptions.forEach(opt => {
        const newOpt = document.createElement('option');
        newOpt.value = opt.value;
        newOpt.textContent = opt.textContent;
        select.appendChild(newOpt);
    });

    // If there are other levels in the DB not in the default options, add them
    levels.forEach(level => {
        if (!['ERROR', 'WARNING', 'INFO'].includes(level)) {
            const opt = document.createElement('option');
            opt.value = level;
            opt.textContent = level;
            select.appendChild(opt);
        }
    });

    select.value = currentValue;
}

function addSchedulerOutputLog(level, message, fileName) {
    const grid = $('schedulerOutputGrid');
    const colors = { ERROR: 'var(--bear)', WARNING: '#f59e0b', INFO: 'var(--text-2)' };
    const color = colors[level] || 'var(--text-2)';
    const time = new Date().toLocaleTimeString();
    const fn = fileName ? `<span style="color:var(--text-3);margin-right:6px;">[${escapeHtml(fileName)}]</span>` : '';
    const row = `<div style="padding:3px 8px;border-bottom:1px solid var(--border-subtle,#e5e5e0);">
        <span style="color:var(--text-3);">${time}</span>
        <span style="color:${color};margin:0 6px;font-weight:600;">${level}</span>
        ${fn}<span style="color:${color};">${escapeHtml(message)}</span>
    </div>`;
    if (grid.innerHTML.includes('No scheduler output yet')) {
        grid.innerHTML = row;
    } else {
        grid.insertAdjacentHTML('afterbegin', row);
    }
}

function renderSchedulerOutput(rows) {
    const grid = $('schedulerOutputGrid');
    if (!rows || rows.length === 0) {
        grid.innerHTML = '<div style="color:var(--text-3);padding:8px;">No scheduler output yet</div>';
        return;
    }
    renderSchedulerOutputRows(rows, grid);
}

function renderSchedulerOutputRows(rows, container) {
    const colors = { ERROR: 'var(--bear)', WARNING: '#f59e0b', INFO: 'var(--text-2)' };
    container.innerHTML = rows.map(r => {
        const color = colors[r.log_level] || 'var(--text-2)';
        const fn = r.file_name ? `<span style="color:var(--text-3);margin-right:6px;">[${escapeHtml(r.file_name)}]</span>` : '';
        return `<div style="padding:3px 8px;border-bottom:1px solid var(--border-subtle,#e5e5e0);">
            <span style="color:var(--text-3);">${r.time}</span>
            <span style="color:${color};margin:0 6px;font-weight:600;">${r.log_level}</span>
            ${fn}<span style="color:${color};">${escapeHtml(r.message)}</span>
        </div>`;
    }).join('');
}

async function showFileLogsPopup(fileType) {
    $('fileLogsTitle').textContent = `Logs — ${fileType}`;
    $('fileLogsBody').innerHTML = '<div style="padding:8px;color:var(--text-3);">Loading...</div>';
    $('fileLogsModal').style.display = 'flex';
    try {
        const resp = await fetch(`/api/monitor/scheduler/output?last_n=200&file_type=${encodeURIComponent(fileType)}`);
        const data = await resp.json();
        if (data.rows && data.rows.length > 0) {
            renderSchedulerOutputRows(data.rows, $('fileLogsBody'));
        } else {
            $('fileLogsBody').innerHTML = '<div style="padding:8px;color:var(--text-3);">No logs for this file type</div>';
        }
    } catch (e) {
        $('fileLogsBody').innerHTML = '<div style="padding:8px;color:var(--bear);">Error loading logs: ' + escapeHtml(e.toString()) + '</div>';
    }
}

// escapeHtml is provided by _common.js (window.escapeHtml).

function renderSummary() {
    const s = state.summary;
    if (!s) return;

    const bull = 'var(--bull)';
    const bear = 'var(--bear)';
    const warn = '#f59e0b';
    const dim  = 'var(--text-2)';

    // Scheduled
    $('ki-scheduled').textContent = s.scheduled_today || '0';
    $('ki-scheduled').style.color = dim;

    // Processed
    if (s.scheduled_today > 0) {
        $('ki-processed').textContent = `${s.processed_today || 0}/${s.scheduled_today}`;
        $('ki-processed').style.color =
            s.processed_today === s.scheduled_today ? bull :
            s.processed_today > 0                  ? warn : bear;
    } else {
        $('ki-processed').textContent = '—';
        $('ki-processed').style.color = dim;
    }

    // Running
    $('ki-running').textContent = s.running_now || '0';
    $('ki-running').style.color = s.running_now > 0 ? warn : dim;

    // Errors
    $('ki-errors').textContent = s.errors_today || '0';
    $('ki-errors').style.color = s.errors_today > 0 ? bear : bull;

    // Derives
    if (s.derives_total > 0) {
        $('ki-derives').textContent = `${s.derives_ok || 0}/${s.derives_total}`;
        $('ki-derives').style.color = s.derives_ok === s.derives_total ? bull : warn;
    } else {
        $('ki-derives').textContent = '—';
        $('ki-derives').style.color = dim;
    }

    // Last file
    if (s.last_file_at) {
        const diffMins = Math.floor((new Date() - new Date(s.last_file_at)) / 60000);
        $('ki-last').textContent = `${new Date(s.last_file_at).toLocaleTimeString()} (${diffMins}m ago)`;
        $('ki-last').style.color = diffMins > 120 ? bear : diffMins > 60 ? warn : dim;
    } else {
        $('ki-last').textContent = '—';
        $('ki-last').style.color = dim;
    }
}

// Build a deep-link URL for opening a DB table in the appropriate maintenance
// page. ref_* tables open in the Ref Data page; hist_*/drv_*/meta_* go to the
// DB Data page. Returns null when there's no sensible target.
function tableLinkUrl(tableName, fileDate) {
    if (!tableName) return null;
    if (tableName.startsWith('ref_')) {
        return `/ref?table=${encodeURIComponent(tableName)}`;
    }
    let url = `/explore?table=${encodeURIComponent(tableName)}`;
    if (fileDate) url += `&date=${encodeURIComponent(fileDate)}`;
    return url;
}

function renderSchedule() {
    const tbody = $('scheduleBody');
    tbody.innerHTML = '';

    $('scheduleDate').textContent = new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });

    if (!state.schedule || state.schedule.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" class="empty">No schedule data.</td></tr>';
        return;
    }

    state.schedule.forEach(row => {
        const tr = document.createElement('tr');
        const notToday = row.status === 'not today';
        const overdue  = row.status === 'overdue';
        if (row.status === 'running') tr.style.background = '#fffbeb';
        if (overdue)  tr.style.background = '#fef2f2';
        if (notToday) tr.style.opacity = '0.5';

        const statusPill = statusToPill(row.status);

        const fileName = row.file_path ? row.file_path.split(/[\\/]/).pop() : '—';

        const blankProcessed = (row.status === 'overdue' || row.status === 'optional' || row.status === 'not today' || row.status === 'running') && !row.file_date;

        const historyDots = (row.history || []).map(h => {
            const label = new Date(h.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
            const color = h.received ? '#16a34a' : '#dc2626';
            return `<span title="${label}" style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${color};margin:0 1px;"></span>`;
        }).join('');

        const rowCountChanged = row.prev_rows_inserted !== null && row.prev_rows_inserted !== undefined &&
                                 row.rows_inserted !== null && row.rows_inserted !== row.prev_rows_inserted;
        const shouldCheckMatch = row.rows_should_match !== false;
        const rowsIsZero = row.rows_inserted === 0;
        const isProcessed = ['success', 'done', 'error'].includes(row.status);
        const rowCountHighlight = isProcessed && ((rowCountChanged && shouldCheckMatch) || rowsIsZero) ? 'background:#fee2e2;' : '';

        const rowsInsertedDisp = blankProcessed
            ? '—'
            : (row.rows_inserted != null ? row.rows_inserted.toLocaleString() : '—');
        const prevSuffix = row.prev_rows_inserted != null
            ? ` <span style="color:var(--text-3);">(P ${row.prev_rows_inserted.toLocaleString()})</span>`
            : '';
        const linkUrl = tableLinkUrl(row.target_table, row.file_date);
        const rowsInsertedCell = linkUrl
            ? `<a href="${linkUrl}" title="Open ${escapeHtml(row.target_table)}" style="color:var(--accent);text-decoration:none;">${rowsInsertedDisp}</a>${prevSuffix}`
            : `${rowsInsertedDisp}${prevSuffix}`;

        tr.innerHTML = `
            <td>${notToday ? row.file_type : `<strong>${row.file_type}</strong>`}</td>
            <td><span class="category-badge hist">${row.target_tab}</span></td>
            <td style="color:var(--text-3);font-size:11px;">${row.week_day || '—'}</td>
            <td>${row.file_time}</td>
            <td>${statusPill}</td>
            <td style="white-space:nowrap;">${historyDots}</td>
            <td>${blankProcessed ? '—' : row.file_date || '—'}</td>
            <td>${blankProcessed ? '—' : row.processed_at ? new Date(row.processed_at).toLocaleTimeString() : '—'}</td>
            <td class="file-cell" style="color:var(--text-2);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;" title="${escapeHtml(row.source_dir || '')} (click for logs)">${blankProcessed ? '—' : escapeHtml(fileName)}</td>
            <td class="num" style="${rowCountHighlight}">${rowsInsertedCell}</td>
            <td style="text-align:center;">
                <button class="btn btn-sm reprocess-btn"
                        data-file-path="${escapeHtml(row.file_path || '')}"
                        data-file-type="${escapeHtml(row.file_type)}"
                        title="Reprocess file"
                        ${!row.file_path ? 'disabled' : ''}>
                    ↻
                </button>
            </td>
        `;

        // Logs popup now opens only when the File cell is clicked.
        const fileCell = tr.querySelector('.file-cell');
        if (fileCell) {
            fileCell.addEventListener('click', (e) => {
                e.stopPropagation();
                showFileLogsPopup(row.file_type);
            });
        }

        const btn = tr.querySelector('.reprocess-btn');
        if (btn && row.file_path) {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                doReprocess(e.target, row.file_path, row.file_type);
            });
        }

        tbody.appendChild(tr);
    });
}

function renderEtlRuns() {
    const tbody = $('etlBody');
    tbody.innerHTML = '';

    if (!state.etlRuns || state.etlRuns.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty">No ETL runs found.</td></tr>';
        return;
    }

    state.etlRuns.forEach((row, idx) => {
        const tr = document.createElement('tr');
        tr.id = `etl-row-${row.run_id}`;
        if (row.status === 'running') tr.style.background = '#fffbeb';

        const startTime = new Date(row.started_at);
        const startDisplay = startTime.toLocaleTimeString();
        const duration = formatDuration(row.duration_sec, row.status === 'running');

        const statusPill = statusToPill(row.status);

        const fileName = row.file_path ? row.file_path.split(/[\\/]/).pop() : '—';

        const rowCountChanged = row.prev_rows_inserted !== null && row.prev_rows_inserted !== undefined &&
                                 row.rows_inserted !== null && row.rows_inserted !== row.prev_rows_inserted;
        const shouldCheckMatch = row.rows_should_match !== false;
        const rowsIsZero = row.rows_inserted === 0;
        const isProcessed = ['success', 'done', 'error'].includes(row.status);
        const rowCountHighlight = isProcessed && ((rowCountChanged && shouldCheckMatch) || rowsIsZero) ? 'background:#fee2e2;' : '';

        const fileDateForLink = row.started_at ? row.started_at.split('T')[0] : '';
        const linkUrl = tableLinkUrl(row.target_table, fileDateForLink);
        const rowsInsertedDisp = row.rows_inserted != null ? row.rows_inserted.toLocaleString() : '—';
        const prevSuffix = row.prev_rows_inserted != null
            ? ` <span style="color:var(--text-3);">(P ${row.prev_rows_inserted.toLocaleString()})</span>`
            : '';
        const rowsInsertedCell = linkUrl
            ? `<a href="${linkUrl}" title="Open ${escapeHtml(row.target_table)}" style="color:var(--accent);text-decoration:none;">${rowsInsertedDisp}</a>${prevSuffix}`
            : `${rowsInsertedDisp}${prevSuffix}`;

        tr.innerHTML = `
            <td><code style="color: var(--text-3);">${row.run_id}</code></td>
            <td>${startDisplay}</td>
            <td><strong>${row.file_type}</strong></td>
            <td><span class="category-badge hist">${row.target_tab}</span></td>
            <td style="color: var(--text-2); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(row.file_path || '')}">${escapeHtml(fileName)}</td>
            <td>${statusPill}</td>
            <td class="num" style="${rowCountHighlight}">${rowsInsertedCell}</td>
            <td class="num" style="color: var(--text-3);">${row.rows_skipped != null ? row.rows_skipped.toLocaleString() : '—'}</td>
            <td>${duration}</td>
        `;

        if (row.status === 'error') {
            tr.style.cursor = 'pointer';
            tr.addEventListener('click', () => toggleErrorDetail(row.run_id));
        }

        tbody.appendChild(tr);

        if (row.status === 'error' && row.error_msg) {
            const detailTr = document.createElement('tr');
            detailTr.id = `error-detail-${row.run_id}`;
            detailTr.className = 'error-detail';
            detailTr.style.display = 'none';
            detailTr.innerHTML = `
                <td colspan="9" style="background: #fee2e2; padding: 12px; border-top: none;">
                    <pre style="color: var(--bear); margin: 0; font-size: 12px; white-space: pre-wrap; word-wrap: break-word;">
${escapeHtml(row.error_msg)}
                    </pre>
                </td>
            `;
            tbody.appendChild(detailTr);
        }
    });
}

function toggleErrorDetail(runId) {
    const detailEl = $(`error-detail-${runId}`);
    if (detailEl) {
        detailEl.style.display = detailEl.style.display === 'none' ? 'table-row' : 'none';
    }
}

function renderDeriveRuns() {
    const tbody = $('deriveBody');
    tbody.innerHTML = '';

    if (!state.deriveRuns || state.deriveRuns.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">No derive runs found.</td></tr>';
        return;
    }

    state.deriveRuns.forEach(row => {
        const tr = document.createElement('tr');
        if (row.status === 'running') tr.style.background = '#fffbeb';

        const startTime = new Date(row.started_at);
        const startDisplay = startTime.toLocaleTimeString();
        const duration = formatDuration(row.duration_sec, row.status === 'running');
        const statusPill = statusToPill(row.status);

        let parentLink = row.parent_run_id ? `<a href="#etl-row-${row.parent_run_id}" style="color: var(--accent);">${row.parent_run_id}</a>` : '—';

        tr.innerHTML = `
            <td><code style="color: var(--text-3);">${row.run_id}</code></td>
            <td>${startDisplay}</td>
            <td>${row.as_of_date}</td>
            <td><span class="category-badge drv">${row.target_table}</span></td>
            <td>${statusPill}</td>
            <td class="num">${row.rows_built != null ? row.rows_built.toLocaleString() : '—'}</td>
            <td>${duration}</td>
        `;

        tbody.appendChild(tr);
    });
}

function statusToPill(status) {
    const map = {
        'success':   { cls: 'pill-bull', txt: 'success' },
        'done':      { cls: 'pill-bull', txt: 'done' },
        'running':   { cls: 'pill-warn', txt: '⟳ running' },
        'pending':   { cls: 'pill-neut', txt: 'pending' },
        'overdue':   { cls: 'pill-bear', txt: '⚠ overdue' },
        'error':     { cls: 'pill-bear', txt: 'error' },
        'not today': { cls: 'pill-neut', txt: 'not today' },
        'optional':  { cls: 'pill-opt',  txt: 'optional' },
    };
    const def = map[status] || { cls: 'pill-neut', txt: status };
    return `<span class="pill ${def.cls}">${def.txt}</span>`;
}

function formatDuration(seconds, isRunning) {
    if (seconds == null) return '—';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    const result = `${mins}:${secs.toString().padStart(2, '0')}`;
    return isRunning ? result + '…' : result;
}

function updateFileTypeFilterOptions() {
    const fileTypes = new Set();
    if (state.schedule) {
        state.schedule.forEach(row => fileTypes.add(row.file_type));
    }

    // Update ETL Loads filter
    const select1 = $('fileTypeFilter');
    const currentValue1 = select1.value;
    const existingOptions1 = Array.from(select1.options).map(o => o.value);
    fileTypes.forEach(ft => {
        if (!existingOptions1.includes(ft)) {
            const opt = document.createElement('option');
            opt.value = ft;
            opt.textContent = ft;
            select1.appendChild(opt);
        }
    });
    select1.value = currentValue1;

    // Update Scheduler Output filter
    const select2 = $('schedulerFileFilter');
    const currentValue2 = select2.value;
    const existingOptions2 = Array.from(select2.options).map(o => o.value);
    fileTypes.forEach(ft => {
        if (!existingOptions2.includes(ft)) {
            const opt = document.createElement('option');
            opt.value = ft;
            opt.textContent = ft;
            select2.appendChild(opt);
        }
    });
    select2.value = currentValue2;
}

// escapeHtml is provided by _common.js (window.escapeHtml).

function updateLastRefreshed() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    $('lastRefreshed').textContent = `Last refreshed ${timeStr}`;
}

function resetCountdown() {
    state.countdownSeconds = 30;
}

function startSchedulerOutputRefresh() {
    // Refresh scheduler output every 30 seconds (independent of main auto-refresh).
    // Was 5s — that's 12 DB queries per minute which contributed to psycopg
    // contention with the scheduler on Windows.
    setInterval(loadSchedulerOutput, 30000);
    // Load immediately on start
    loadSchedulerOutput();
}

function startCountdownTimer() {
    if (state.countdownInterval) clearInterval(state.countdownInterval);
    state.countdownInterval = setInterval(() => {
        state.countdownSeconds--;
        updateCountdownDisplay();
        if (state.countdownSeconds <= 0) {
            loadAll();
            resetCountdown();
            updateCountdownDisplay();
        }
    }, 1000);
    updateCountdownDisplay();
}

function updateCountdownDisplay() {
    $('refreshCountdown').textContent = `Auto-refresh in ${state.countdownSeconds}s`;
}

function startAutoRefresh() {
    if (state.refreshInterval) clearInterval(state.refreshInterval);
    state.refreshInterval = setInterval(loadAll, 60000);
    startCountdownTimer();
}

// ── Live SSE banner ───────────────────────────────────────────────────────────

let _liveSource   = null;
let _prevRunIds   = new Set();
let _wasRunning   = false;

function startLiveStream() {
    if (_liveSource) _liveSource.close();
    _liveSource = new EventSource('/api/monitor/live');

    _liveSource.onmessage = (e) => {
        const data = JSON.parse(e.data);

        if (data.type === 'running') {
            renderLiveBanner(data.jobs);

            // If job set changed, refresh ETL table + summary immediately
            const curIds = new Set(data.jobs.map(j => j.run_id));
            const changed = [...curIds].some(id => !_prevRunIds.has(id)) ||
                            [..._prevRunIds].some(id => !curIds.has(id));
            if (changed) { loadEtlRuns(); loadSummary(); }
            _prevRunIds = curIds;
            _wasRunning = true;

        } else {
            if (_wasRunning) {
                // Jobs just finished — do a full refresh once
                loadAll();
            }
            _prevRunIds = new Set();
            _wasRunning = false;
            hideLiveBanner();
        }
    };

    _liveSource.onerror = () => hideLiveBanner();
}

function renderLiveBanner(jobs) {
    const banner = $('liveBanner');
    const container = $('liveJobs');

    container.innerHTML = jobs.map(job => {
        const fname   = job.file_path ? job.file_path.split(/[\\/]/).pop() : '—';
        const mins    = Math.floor(job.elapsed_sec / 60);
        const secs    = String(job.elapsed_sec % 60).padStart(2, '0');
        const elapsed = `${mins}:${secs}`;
        return `
            <span style="display:inline-flex;align-items:center;gap:8px;">
                <strong style="color:#92400e;">${escapeHtml(job.file_type)}</strong>
                <span style="color:var(--text-3);">→</span>
                <span>${escapeHtml(job.target_tab)}</span>
                <span style="color:var(--text-2);max-width:200px;overflow:hidden;
                      text-overflow:ellipsis;white-space:nowrap;"
                      title="${escapeHtml(job.file_path)}">${escapeHtml(fname)}</span>
                <span style="color:var(--text-3);">|</span>
                <span style="font-variant-numeric:tabular-nums;">
                    ${job.rows_inserted.toLocaleString()} rows in
                </span>
                <span style="color:var(--text-3);">|</span>
                <span style="color:#92400e;font-variant-numeric:tabular-nums;">${elapsed}</span>
            </span>`;
    }).join('<span style="color:var(--border);margin:0 4px;">·</span>');

    banner.style.display = 'flex';
}

function hideLiveBanner() {
    $('liveBanner').style.display = 'none';
    $('liveJobs').innerHTML = '';
}

document.addEventListener('DOMContentLoaded', () => {
    $('refreshBtn').addEventListener('click', () => {
        loadAll();
        resetCountdown();
        updateCountdownDisplay();
    });

    $('limitSelect').addEventListener('change', (e) => {
        state.currentLimit = parseInt(e.target.value);
        loadEtlRuns();
    });

    $('fileTypeFilter').addEventListener('change', (e) => {
        state.currentFileTypeFilter = e.target.value;
        loadEtlRuns();
    });

    $('schedulerLevelFilter').addEventListener('change', (e) => {
        state.currentSchedulerLevelFilter = e.target.value;
        loadSchedulerOutput();
    });

    $('schedulerFileFilter').addEventListener('change', (e) => {
        state.currentSchedulerFileFilter = e.target.value;
        loadSchedulerOutput();
    });

    $('fileLogsClose').addEventListener('click', () => {
        $('fileLogsModal').style.display = 'none';
    });

    $('fileLogsModal').addEventListener('click', (e) => {
        if (e.target.id === 'fileLogsModal') {
            $('fileLogsModal').style.display = 'none';
        }
    });

    $('startSchedulerBtn').addEventListener('click', async () => {
        $('startSchedulerBtn').disabled = true;
        $('startSchedulerBtn').textContent = 'Starting…';
        try {
            const resp = await fetch('/api/monitor/scheduler/start', { method: 'POST' });
            const r = await resp.json();
            if (r.started) {
                // Poll up to 30 seconds for the heartbeat (scan_initial can
                // take a while on first launch). Always reset the button
                // state at the end, success or timeout.
                let attempts = 0;
                let found = false;
                while (attempts < 30) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    const status = await fetch('/api/monitor/scheduler').then(r => r.json());
                    if (status.running) {
                        renderSchedulerStatus(status);
                        found = true;
                        break;
                    }
                    attempts++;
                }
                if (!found) {
                    // Don't leave the button stuck on "Starting…" forever.
                    loadSchedulerStatus();
                }
                $('startSchedulerBtn').disabled = false;
                $('startSchedulerBtn').textContent = 'Start Scheduler';
            } else {
                alert(r.reason || 'Could not start scheduler.');
                $('startSchedulerBtn').disabled = false;
                $('startSchedulerBtn').textContent = 'Start Scheduler';
            }
        } catch (e) {
            alert('Failed to start scheduler: ' + e);
            $('startSchedulerBtn').disabled = false;
            $('startSchedulerBtn').textContent = 'Start Scheduler';
        }
    });

    $('stopSchedulerBtn').addEventListener('click', async () => {
        $('stopSchedulerBtn').disabled = true;
        $('stopSchedulerBtn').textContent = 'Stopping…';
        try {
            const resp = await fetch('/api/monitor/scheduler/stop', { method: 'POST' });
            const r = await resp.json();
            if (r.stopped) {
                // Wait a moment for heartbeat to be deleted, then refresh status
                await new Promise(resolve => setTimeout(resolve, 500));
                await loadSchedulerStatus();
                $('stopSchedulerBtn').disabled = false;
                $('stopSchedulerBtn').textContent = 'Stop Scheduler';
            } else {
                alert(r.reason || 'Could not stop scheduler.');
                $('stopSchedulerBtn').disabled = false;
                $('stopSchedulerBtn').textContent = 'Stop Scheduler';
            }
        } catch (e) {
            alert('Failed to stop scheduler: ' + e);
            $('stopSchedulerBtn').disabled = false;
            $('stopSchedulerBtn').textContent = 'Stop Scheduler';
        }
    });

    async function doRegister(task, btnId, label) {
        $(btnId).disabled = true;
        $(btnId).textContent = label + '...';
        try {
            const resp = await fetch(`/api/monitor/startup/register?task=${task}`, { method: 'POST' });
            if (resp.ok) {
                await loadStartupStatus();
            } else {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                alert(`Failed to register ${task} auto-start: ${err.detail || resp.statusText}`);
            }
        } catch (e) {
            alert(`Failed to register ${task} auto-start: ${e}`);
        } finally {
            $(btnId).disabled = false;
            $(btnId).textContent = label;
        }
    }

    $('registerSchedBtn')?.addEventListener('click', () => doRegister('scheduler', 'registerSchedBtn', 'Enable auto-start'));
    $('registerAppBtn')?.addEventListener('click', () => doRegister('app', 'registerAppBtn', 'Enable auto-start'));

    $('unregisterBtn')?.addEventListener('click', async () => {
        if (!confirm('Disable Windows auto-start for the scheduler and trading app?')) return;
        $('unregisterBtn').disabled = true;
        try {
            const resp = await fetch('/api/monitor/startup/unregister', { method: 'POST' });
            if (resp.ok) {
                await loadStartupStatus();
            } else {
                const err = await resp.json().catch(() => ({}));
                alert('Failed to unregister: ' + (err.detail || resp.statusText));
            }
        } catch (e) {
            alert('Error: ' + e.message);
        } finally {
            $('unregisterBtn').disabled = false;
        }
    });

    document.getElementById('runMissingDerivesBtn')?.addEventListener('click', () => runMissingDerives(false));
    document.getElementById('forceRederiveBtn')?.addEventListener('click', () => runMissingDerives(true));

    // Initial data load + background refresh loops.
    // These calls were lost in a prior truncation; without them the page
    // stays blank because nothing fetches data on initial DOMContentLoaded.
    loadAll();
    loadStartupStatus();
    startAutoRefresh();
    startSchedulerOutputRefresh();
    startLiveStream();
});
