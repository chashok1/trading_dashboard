/**
 * DBExplore - Browse any non-ref table with symbol/date filters
 * Default: shows data for current snapshot date. Clear date to see all data.
 */

const state = {
    tables: [],
    currentTable: null,
    dashboardDate: null,
    columns: [],
    rows: [],
    total: 0,
    currentPage: 0,
    pageSize: 200,
    sortColumn: null,
    sortDirection: 'asc',
    filterSymbol: '',
    filterDate: '',
};

const DOM = {
    datePicker: document.getElementById('datePicker'),
    tableSelect: document.getElementById('tableSelect'),
    statusBar: document.getElementById('statusBar'),
    rowsDisplay: document.getElementById('rowsDisplay'),
    headerRow: document.getElementById('headerRow'),
    tableBody: document.getElementById('tableBody'),
    pagination: document.getElementById('pagination'),
    pageInfo: document.getElementById('pageInfo'),
    prevBtn: document.getElementById('prevBtn'),
    nextBtn: document.getElementById('nextBtn'),
    inlinePrevBtn: document.getElementById('inlinePrevBtn'),
    inlineNextBtn: document.getElementById('inlineNextBtn'),
    inlinePageInfo: document.getElementById('inlinePageInfo'),
    filterSymbol: document.getElementById('filterSymbol'),
    filterDate: document.getElementById('filterDate'),
    filterApplyBtn: document.getElementById('filterApplyBtn'),
    filterClearBtn: document.getElementById('filterClearBtn'),
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Start with blank filters
    state.filterSymbol = '';
    state.filterDate = '';
    if (DOM.filterSymbol) DOM.filterSymbol.value = '';
    if (DOM.filterDate) DOM.filterDate.value = '';

    await loadAvailableDates();
    await loadTableList();
    setupFilterListeners();

    // Honor ?table=<name>&date=<yyyy-mm-dd> deep-links from File Monitor.
    const params = new URLSearchParams(window.location.search);
    const requestedTable = params.get('table');
    const requestedDate = params.get('date');
    if (requestedTable && state.tables.some(t => t.name === requestedTable)) {
        DOM.tableSelect.value = requestedTable;
        if (requestedDate && DOM.filterDate) {
            DOM.filterDate.value = requestedDate;
            state.filterDate = requestedDate;
        }
        await loadTable(requestedTable);
    }
});

function setupFilterListeners() {
    if (DOM.filterApplyBtn) {
        DOM.filterApplyBtn.addEventListener('click', async () => {
            state.filterSymbol = DOM.filterSymbol?.value.trim().toUpperCase() || '';
            state.filterDate = DOM.filterDate?.value || '';
            state.currentPage = 0;
            if (state.currentTable) {
                await loadTable(state.currentTable);
            }
        });
    }

    if (DOM.filterClearBtn) {
        DOM.filterClearBtn.addEventListener('click', async () => {
            // Clear all filters completely (show all data across all dates)
            state.filterSymbol = '';
            state.filterDate = '';
            if (DOM.filterSymbol) DOM.filterSymbol.value = '';
            if (DOM.filterDate) DOM.filterDate.value = '';
            state.currentPage = 0;
            if (state.currentTable) {
                await loadTable(state.currentTable);
            }
        });
    }

    // Allow Enter key to apply filters
    if (DOM.filterSymbol) {
        DOM.filterSymbol.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter' && DOM.filterApplyBtn) {
                await DOM.filterApplyBtn.click();
            }
        });
    }
    if (DOM.filterDate) {
        DOM.filterDate.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter' && DOM.filterApplyBtn) {
                await DOM.filterApplyBtn.click();
            }
        });
    }
}

DOM.tableSelect.addEventListener('change', async (e) => {
    state.currentPage = 0;
    state.sortColumn = null;
    state.sortDirection = 'asc';
    state.filterSymbol = '';
    state.filterDate = '';
    DOM.filterSymbol.value = '';
    DOM.filterDate.value = '';
    await loadTable(e.target.value);
});

DOM.prevBtn.addEventListener('click', async () => {
    if (state.currentPage > 0) {
        state.currentPage--;
        await loadTable(state.currentTable);
    }
});

DOM.nextBtn.addEventListener('click', async () => {
    const maxPage = Math.ceil(state.total / state.pageSize) - 1;
    if (state.currentPage < maxPage) {
        state.currentPage++;
        await loadTable(state.currentTable);
    }
});

DOM.inlinePrevBtn.addEventListener('click', async () => {
    if (state.currentPage > 0) {
        state.currentPage--;
        await loadTable(state.currentTable);
    }
});

DOM.inlineNextBtn.addEventListener('click', async () => {
    const maxPage = Math.ceil(state.total / state.pageSize) - 1;
    if (state.currentPage < maxPage) {
        state.currentPage++;
        await loadTable(state.currentTable);
    }
});

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

async function loadAvailableDates() {
    try {
        const dates = await fetchJSON('/api/dates');
        if (dates.length === 0) {
            return;
        }

        // Populate date picker dropdown at the top
        let html = '';
        dates.forEach(d => {
            const dateStr = d.split(' ')[0];
            html += `<option value="${dateStr}">${dateStr}</option>`;
        });
        DOM.datePicker.innerHTML = html;

        // Don't auto-select a date — let user choose when to filter
        if (DOM.datePicker.options.length > 0) {
            DOM.datePicker.value = '';
        }
    } catch (e) {
        console.error(`Failed to load available dates: ${e.message}`);
    }
}

// Listen for changes to the top date picker — just populate the filter input
// User must click Apply to actually apply the filter
DOM.datePicker?.addEventListener('change', async (e) => {
    const selectedDate = e.target.value;
    DOM.filterDate.value = selectedDate;
});

async function loadTableList() {
    try {
        const tables = await fetchJSON('/api/data/tables');
        state.tables = tables;

        // Group by category
        const categories = {
            'hist': tables.filter(t => t.category === 'hist'),
            'drv': tables.filter(t => t.category === 'drv'),
            'drv2': tables.filter(t => t.category === 'drv2'),
            'drv_cat': tables.filter(t => t.category === 'drv_cat'),
            'ref': tables.filter(t => t.category === 'ref'),
            'meta': tables.filter(t => t.category === 'meta'),
            'other': tables.filter(t => t.category === 'other'),
        };

        let html = '<option value="">Choose a table...</option>';

        const categoryLabels = {
            'hist': 'hist_* (raw history)',
            'drv': 'drv_* (derived)',
            'drv_cat': 'drv_cat_* (concept tables)',
            'ref': 'ref_* (reference)',
            'meta': 'meta_* (operational)',
            'other': 'other',
        };

        for (const [cat, label] of Object.entries(categoryLabels)) {
            const catTables = categories[cat];
            if (catTables && catTables.length > 0) {
                html += `<optgroup label="${label}">`;
                catTables.forEach(t => {
                    html += `<option value="${t.name}">${t.name} (${t.row_count} rows)</option>`;
                });
                html += '</optgroup>';
            }
        }

        DOM.tableSelect.innerHTML = html;
    } catch (e) {
        showStatus(`Failed to load tables: ${e.message}`, 'error');
    }
}

async function loadTable(tableName) {
    if (!tableName) {
        state.currentTable = null;
        state.columns = [];
        state.rows = [];
        state.total = 0;
        DOM.rowsDisplay.textContent = '';
        DOM.inlinePageInfo.textContent = '';
        DOM.headerRow.innerHTML = '';
        DOM.tableBody.innerHTML = '<tr><td colspan="20" style="text-align: center; color: var(--text-3); padding: 20px;">Select a table to view</td></tr>';
        DOM.pagination.style.display = 'none';
        const inlinePagination = document.querySelector('.inline-pagination');
        if (inlinePagination) inlinePagination.classList.remove('visible');
        return;
    }

    try {
        const offset = state.currentPage * state.pageSize;
        let url = `/api/data/${tableName}?limit=${state.pageSize}&offset=${offset}`;

        // Add date filter if provided, otherwise use "all" to search all dates
        if (state.filterDate) {
            url += `&date=${state.filterDate}`;
        } else {
            // Empty date means search all dates in database
            url += `&date=all`;
        }

        // Add symbol filter if provided
        if (state.filterSymbol) {
            url += `&symbol=${encodeURIComponent(state.filterSymbol)}`;
        }

        // Add sort if specified
        if (state.sortColumn) {
            url += `&sort_by=${state.sortColumn}&sort_dir=${state.sortDirection}`;
        }

        const data = await fetchJSON(url);
        state.currentTable = tableName;
        state.columns = data.columns;
        state.rows = data.rows;
        state.total = data.total;

        // Show what filter the API applied to produce this set of records
        const fBar = document.getElementById('filterInfoBar');
        const fText = document.getElementById('filterInfoText');
        if (fBar && fText) {
            if (data.filter_description) {
                fText.textContent = data.filter_description;
                fBar.style.display = 'block';
            } else {
                fBar.style.display = 'none';
            }
        }

        renderTable();
        showStatus(`Loaded ${tableName}: ${state.total} rows`, 'success');
    } catch (e) {
        showStatus(`Failed to load table: ${e.message}`, 'error');
    }
}

function renderTable() {
    // Headers
    const headers = state.columns.map(col => {
        const classList = col.is_pk ? ' class="pk-col"' : '';
        const isSorted = state.sortColumn === col.name;
        const indicator = isSorted
            ? `<span class="sort-indicator">${state.sortDirection === 'asc' ? '↑' : '↓'}</span>`
            : '';
        return `<th${classList} data-column="${col.name}">${col.name}${indicator}</th>`;
    }).join('');
    DOM.headerRow.innerHTML = headers;

    // Add click handlers to headers
    DOM.headerRow.querySelectorAll('th').forEach(th => {
        th.addEventListener('click', async () => {
            const column = th.getAttribute('data-column');
            if (state.sortColumn === column) {
                state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                state.sortColumn = column;
                state.sortDirection = 'asc';
            }
            state.currentPage = 0;
            await loadTable(state.currentTable);
        });
    });

    // Rows
    const rows = state.rows.map(row => {
        const cells = state.columns.map(col => {
            const value = row[col.name];
            const displayValue = value === null ? '(null)' : String(value);
            if (col.is_pk) {
                return `<td class="pk-col">${escapeHtml(displayValue)}</td>`;
            }
            // Style file paths/names in blue
            if (isFilePathColumn(col.name)) {
                return `<td class="file-link">${escapeHtml(displayValue)}</td>`;
            }
            return `<td>${highlightKeywords(displayValue)}</td>`;
        }).join('');
        return `<tr>${cells}</tr>`;
    }).join('');
    DOM.tableBody.innerHTML = rows;

    // Pagination (top inline, top full, and bottom)
    const maxPage = Math.ceil(state.total / state.pageSize);
    const startRow = state.currentPage * state.pageSize + 1;
    const endRow = Math.min((state.currentPage + 1) * state.pageSize, state.total);
    const pageText = `Showing ${startRow}–${endRow} of ${state.total}`;
    const currentPageNum = state.currentPage + 1;

    // Update inline controls (always visible if data loaded)
    const inlinePagination = document.querySelector('.inline-pagination');
    if (state.total > 0) {
        DOM.rowsDisplay.textContent = pageText;
        DOM.inlinePageInfo.textContent = `${currentPageNum}/${maxPage}`;
        DOM.inlinePrevBtn.disabled = state.currentPage === 0;
        DOM.inlineNextBtn.disabled = state.currentPage >= maxPage - 1;
        if (inlinePagination) inlinePagination.classList.add('visible');
    } else {
        if (inlinePagination) inlinePagination.classList.remove('visible');
    }

    // Bottom pagination (only if more than one page)
    if (state.total > state.pageSize) {
        DOM.pagination.style.display = 'flex';
        DOM.pageInfo.textContent = pageText;
        DOM.prevBtn.disabled = state.currentPage === 0;
        DOM.nextBtn.disabled = state.currentPage >= maxPage - 1;
    } else {
        DOM.pagination.style.display = 'none';
    }
}

function getFilterDescription() {
    const parts = [];
    if (state.filterSymbol) {
        parts.push(`Symbol: ${state.filterSymbol}`);
    }
    if (state.filterDate) {
        parts.push(`Date: ${state.filterDate}`);
    } else {
        parts.push('Date: All');
    }
    return parts.length > 0 ? parts.join(' • ') : 'No filters';
}

function showStatus(message, type) {
    const filterDesc = getFilterDescription();
    const fullMessage = `${message} (${filterDesc})`;
    DOM.statusBar.textContent = fullMessage;
    DOM.statusBar.className = `status-bar ${type}`;
    DOM.statusBar.style.display = 'block';
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

function isFilePathColumn(colName) {
    const lowerName = colName.toLowerCase();
    return lowerName.includes('file') || lowerName.includes('path') || lowerName.includes('dir');
}

function highlightKeywords(text) {
    if (!text || typeof text !== 'string') return text;

    const escaped = escapeHtml(text);
    const regex = /Best idea long|Best idea short|long bench|short bench|\bBullish\b|\bBearish\b|\blong\b|\bshort\b/gi;

    return escaped.replace(regex, match => {
        const lower = match.toLowerCase();
        if (lower === 'best idea long') return `<span class="hl-long-primary">${match}</span>`;
        if (lower === 'best idea short') return `<span class="hl-short-primary">${match}</span>`;
        if (lower === 'long bench') return `<span class="hl-long-tertiary">${match}</span>`;
        if (lower === 'short bench') return `<span class="hl-short-tertiary">${match}</span>`;
        if (lower === 'bullish') return `<span class="hl-bullish">${match}</span>`;
        if (lower === 'bearish') return `<span class="hl-bearish">${match}</span>`;
        if (lower === 'long') return `<span class="hl-long-secondary">${match}</span>`;
        if (lower === 'short') return `<span class="hl-short-secondary">${match}</span>`;
        return match;
    });
}
