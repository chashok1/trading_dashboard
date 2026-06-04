const state = {
    date: null,
    defaultDate: null,
    tables: [],
    symbols: null,
};

const DOM = {
    datePicker: document.getElementById('datePicker'),
    refreshBtn: document.getElementById('refreshBtn'),
    health: document.getElementById('health'),
    statusBar: document.getElementById('statusBar'),
    statsBody: document.getElementById('statsBody'),
    totalTables: document.getElementById('totalTables'),
    totalRows: document.getElementById('totalRows'),
    tablesWithData: document.getElementById('tablesWithData'),
    tlCount: document.getElementById('tlCount'),
    tlDate: document.getElementById('tlDate'),
    missingSymbolsList: document.getElementById('missingSymbolsList'),
    copyMissingBtn: document.getElementById('copyMissingBtn'),
};

async function fetchJSON(url, options = {}) {
    try {
        const resp = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        return await resp.json();
    } catch (e) {
        console.error(`Fetch error: ${e.message}`);
        throw e;
    }
}

async function loadDates() {
    try {
        const dates = await fetchJSON('/api/dates');
        if (dates.length === 0) {
            showStatus('No dates available', 'error');
            return;
        }
        state.defaultDate = dates[0];
        state.date = state.defaultDate;

        DOM.datePicker.innerHTML = dates.map(d =>
            `<option value="${d}" ${d === state.defaultDate ? 'selected' : ''}>${d}</option>`
        ).join('');
    } catch (e) {
        showStatus(`Failed to load dates: ${e.message}`, 'error');
    }
}

async function loadStats() {
    try {
        const url = `/api/stats/tables?date=${state.date}`;
        const stats = await fetchJSON(url);
        state.tables = stats;
        renderStats();
        updateKPIs();
    } catch (e) {
        showStatus(`Failed to load stats: ${e.message}`, 'error');
    }
}

async function loadSymbols() {
    try {
        const exclude = document.getElementById('excludeNonEquityComparison')?.checked !== false;
        const url = `/api/symbols/comparison?exclude_non_equity=${exclude}`;
        const symbols = await fetchJSON(url);
        state.symbols = symbols;
        renderSymbols();
    } catch (e) {
        showStatus(`Failed to load symbols: ${e.message}`, 'error');
    }
}

function updateKPIs() {
    const totalTables = state.tables.length;
    const totalRows = state.tables.reduce((sum, t) => sum + (t.total_rows || 0), 0);
    const tablesWithData = state.tables.filter(t => t.rows_on_date > 0).length;

    DOM.totalTables.textContent = totalTables.toLocaleString();
    DOM.totalRows.textContent = totalRows.toLocaleString();
    DOM.tablesWithData.textContent = tablesWithData.toLocaleString();
}

function renderStats() {
    const groupedByCategory = {};
    state.tables.forEach(table => {
        if (!groupedByCategory[table.category]) {
            groupedByCategory[table.category] = [];
        }
        groupedByCategory[table.category].push(table);
    });

    const categoryOrder = ['hist', 'drv', 'drv_cat', 'ref', 'meta'];
    let html = '';

    categoryOrder.forEach(cat => {
        const tables = groupedByCategory[cat] || [];
        if (tables.length === 0) return;

        tables.sort((a, b) => a.name.localeCompare(b.name));

        tables.forEach(table => {
            const hasData = table.rows_on_date > 0;
            const hasDateCol = table.date_col !== null;
            const indicator = hasDateCol ?
                (hasData ? 'has-data' : 'no-data') :
                'no-date';
            const indicatorTitle = hasDateCol ?
                (hasData ? 'Has data' : 'No data for this date') :
                'No date column';

            html += `<tr>
                <td class="table-name">${escapeHtml(table.name)}</td>
                <td><span class="category-badge ${table.category}">${table.category}</span></td>
                <td class="num">
                    <span class="data-indicator ${indicator}" title="${indicatorTitle}"></span>
                    ${table.rows_on_date !== null ? table.rows_on_date.toLocaleString() : '—'}
                </td>
                <td class="num">${table.total_rows.toLocaleString()}</td>
                <td class="num">${table.distinct_dates !== null ? table.distinct_dates.toLocaleString() : '—'}</td>
                <td class="date">${table.min_date || '—'}</td>
                <td class="date">${table.max_date || '—'}</td>
            </tr>`;
        });
    });

    DOM.statsBody.innerHTML = html;
}

function renderSymbols() {
    if (!state.symbols) return;

    const s = state.symbols;

    // Update KPI counts and dates
    DOM.tlCount.textContent = s.tl_count.toLocaleString();
    DOM.tlDate.textContent = s.tl_date || '—';

    // Render missing symbols by source
    if (s.missing_by_source.length > 0) {
        let html = '';
        s.missing_by_source.forEach(item => {
            html += `<div style="margin-bottom: 16px;">
                <strong style="color: var(--text-1);">${escapeHtml(item.source)}</strong>
                <div style="color: var(--text-2); font-size: 11px; margin-bottom: 4px;">${escapeHtml(item.date)} (${item.count} symbols)</div>
                <div style="background: white; border: 1px solid var(--border); border-radius: 3px; padding: 8px; font-family: monospace; font-size: 12px; overflow-x: auto;">
                    ${item.symbols.join(', ')}
                </div>
            </div>`;
        });
        DOM.missingSymbolsList.innerHTML = html;
        DOM.copyMissingBtn.style.display = 'block';
    } else {
        DOM.missingSymbolsList.innerHTML = '<em style="color: var(--text-3);">All symbols in other sources are already in TL. No missing symbols.</em>';
        DOM.copyMissingBtn.style.display = 'none';
    }
}

function copyMissingSymbols() {
    if (!state.symbols) return;

    const missing = state.symbols.missing_by_source;
    let allSymbols = [];
    missing.forEach(item => {
        allSymbols = allSymbols.concat(item.symbols);
    });

    const text = allSymbols.join(', ');
    navigator.clipboard.writeText(text).then(() => {
        showStatus(`Copied ${allSymbols.length} missing symbols to clipboard`, 'success');
    }).catch(() => {
        showStatus('Failed to copy to clipboard', 'error');
    });
}

function showStatus(message, type) {
    DOM.statusBar.textContent = message;
    DOM.statusBar.className = `status-bar ${type}`;
    if (type === 'success') {
        setTimeout(() => { DOM.statusBar.style.display = 'none'; }, 3000);
    }
}

function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

async function checkHealth() {
    try {
        await fetch('/health');
        DOM.health.className = 'badge badge-ok';
        DOM.health.title = 'API is healthy';
    } catch {
        DOM.health.className = 'badge badge-err';
        DOM.health.title = 'API is down';
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadDates();
    await loadStats();
    await loadSymbols();
    checkHealth();

    DOM.datePicker.addEventListener('change', async (e) => {
        state.date = e.target.value;
        await loadStats();
        await loadSymbols();
    });

    DOM.refreshBtn.addEventListener('click', async () => {
        await loadStats();
        await loadSymbols();
        showStatus('Refreshed', 'success');
    });

    DOM.copyMissingBtn.addEventListener('click', copyMissingSymbols);

    // uppercase-on-type for rename inputs
    ['renameFrom','renameTo'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', () => { el.value = el.value.toUpperCase(); });
    });

    setInterval(checkHealth, 10000);
});

async function doRename() {
    const from = (document.getElementById('renameFrom').value || '').trim().toUpperCase();
    const to   = (document.getElementById('renameTo').value   || '').trim().toUpperCase();
    const res  = document.getElementById('renameResult');
    if (!from || !to) { res.innerHTML = '<span style="color:#b91c1c">Enter both symbols.</span>'; return; }
    if (from === to)  { res.innerHTML = '<span style="color:#b91c1c">From and To are the same.</span>'; return; }
    if (!confirm(`Rename ${from} → ${to} across ALL tables? This cannot be undone.`)) return;
    res.innerHTML = '<span style="color:var(--text-3)">Renaming…</span>';
    try {
        const data = await fetchJSON('/api/admin/rename-symbol', {
            method: 'POST',
            body: JSON.stringify({ from, to }),
        });
        const tables = Object.entries(data.by_table || {})
            .map(([t, n]) => `${t} (${n})`).join(', ') || 'none';
        res.innerHTML = `<span style="color:#15803d">✓ Renamed ${from} → ${to}. ${data.total_rows} rows updated.<br>
            <span style="font-size:11px;color:var(--text-3)">${tables}</span></span>`;
        document.getElementById('renameFrom').value = '';
        document.getElementById('renameTo').value   = '';
    } catch(e) {
        res.innerHTML = `<span style="color:#b91c1c">Error: ${e.message}</span>`;
    }
}

async function loadMissingSourceData() {
    const el = document.getElementById('missingSourceList');
    el.innerHTML = '<span style="color:var(--text-3)">Loading…</span>';
    try {
        const exclude = document.getElementById('excludeNonEquity')?.checked !== false;
        const rows = await fetchJSON(`/api/admin/missing-symbols?exclude_non_equity=${exclude}`);
        if (!rows.length) {
            el.innerHTML = '<span style="color:#15803d">All symbols have hist_tw and hist_td data.</span>';
            return;
        }
        const html = `<table style="width:100%;border-collapse:collapse;font-size:12px">
            <thead><tr>
                <th style="text-align:left;padding:4px 8px;border-bottom:1px solid var(--border)">Symbol</th>
                <th style="text-align:center;padding:4px 8px;border-bottom:1px solid var(--border)">hist_tw</th>
                <th style="text-align:center;padding:4px 8px;border-bottom:1px solid var(--border)">hist_td</th>
            </tr></thead>
            <tbody>${rows.map(r => `<tr>
                <td style="padding:3px 8px;font-family:monospace">${r.tos_symbol}</td>
                <td style="text-align:center;padding:3px 8px;color:${r.missing_tw?'#b91c1c':'#15803d'}">${r.missing_tw?'MISSING':'ok'}</td>
                <td style="text-align:center;padding:3px 8px;color:${r.missing_td?'#b91c1c':'#15803d'}">${r.missing_td?'MISSING':'ok'}</td>
            </tr>`).join('')}</tbody>
        </table>
        <div style="margin-top:6px;font-size:11px;color:var(--text-3)">${rows.length} symbol(s) with missing source data</div>`;
        el.innerHTML = html;
    } catch(e) {
        el.innerHTML = `<span style="color:#b91c1c">Error: ${e.message}</span>`;
    }
}
