/**
 * DBExplore - Browse any non-ref table with symbol/date filters
 * Default: shows data for current snapshot date. Clear date to see all data.
 */

const state = {
    tables: [],
    currentTable: null,
    dashboardDate: null,
    latestDate: null,
    columns: [],
    rows: [],
    total: 0,
    currentPage: 0,
    pageSize: 200,
    sortColumn: null,
    sortDirection: 'asc',
    filterSymbol: '',
    filterDate: '',
    filterDateFrom: '',
    filterDateTo: '',
    checkedRows: new Set(),
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
    filterSymbol:   document.getElementById('filterSymbol'),
    filterDate:     document.getElementById('filterDate'),
    filterDateFrom: document.getElementById('filterDateFrom'),
    filterDateTo:   document.getElementById('filterDateTo'),
    filterApplyBtn: document.getElementById('filterApplyBtn'),
    filterClearBtn: document.getElementById('filterClearBtn'),
    insertRowBtn: document.getElementById('insertRowBtn'),
    copyRowBtn: document.getElementById('copyRowBtn'),
    deleteRowBtn: document.getElementById('deleteRowBtn'),
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Start with blank filters
    state.filterSymbol   = '';
    state.filterDate     = '';
    state.filterDateFrom = '';
    state.filterDateTo   = '';
    if (DOM.filterSymbol)   DOM.filterSymbol.value   = '';
    if (DOM.filterDate)     DOM.filterDate.value     = '';
    if (DOM.filterDateFrom) DOM.filterDateFrom.value = '';
    if (DOM.filterDateTo)   DOM.filterDateTo.value   = '';

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

function clearDate(inputId) {
    const el = document.getElementById(inputId);
    if (el) el.value = '';
    if (inputId === 'filterDate')     state.filterDate     = '';
    if (inputId === 'filterDateFrom') state.filterDateFrom = '';
    if (inputId === 'filterDateTo')   state.filterDateTo   = '';
}

function setupFilterListeners() {
    if (DOM.filterApplyBtn) {
        DOM.filterApplyBtn.addEventListener('click', async () => {
            state.filterSymbol   = DOM.filterSymbol?.value.trim().toUpperCase() || '';
            state.filterDate     = DOM.filterDate?.value || '';
            state.filterDateFrom = DOM.filterDateFrom?.value || '';
            state.filterDateTo   = DOM.filterDateTo?.value || '';
            state.currentPage = 0;
            if (state.currentTable) {
                await loadTable(state.currentTable);
            }
        });
    }

    if (DOM.filterClearBtn) {
        DOM.filterClearBtn.addEventListener('click', async () => {
            // Clear all filters completely (show all data across all dates)
            state.filterSymbol   = '';
            state.filterDate     = '';
            state.filterDateFrom = '';
            state.filterDateTo   = '';
            if (DOM.filterSymbol)   DOM.filterSymbol.value   = '';
            if (DOM.filterDate)     DOM.filterDate.value     = '';
            if (DOM.filterDateFrom) DOM.filterDateFrom.value = '';
            if (DOM.filterDateTo)   DOM.filterDateTo.value   = '';
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

    const tableName = e.target.value;

    // Find the latest date available in this specific table
    let latestDateForTable = state.latestDate;
    try {
        // First request without sort to find what date columns exist
        const dateResp = await fetch(`/api/data/${tableName}?limit=1&offset=0&date=all`);
        if (dateResp.ok) {
            const dateData = await dateResp.json();
            if (dateData.rows && dateData.rows.length > 0) {
                // Find the date column name for this table
                const dateCol = dateData.columns.find(c =>
                    c.name === 'snapshot_date' || c.name === 'as_of_date' || c.name === 'event_date'
                );
                if (dateCol) {
                    // Re-fetch sorted by the actual date column
                    const sortedResp = await fetch(`/api/data/${tableName}?limit=1&offset=0&date=all&sort_by=${dateCol.name}&sort_dir=desc`);
                    if (sortedResp.ok) {
                        const sortedData = await sortedResp.json();
                        if (sortedData.rows && sortedData.rows.length > 0 && sortedData.rows[0][dateCol.name]) {
                            latestDateForTable = sortedData.rows[0][dateCol.name].substring(0, 10);
                        }
                    }
                }
            }
        }
    } catch (e) {
        console.warn('Could not determine latest date for table', e);
    }

    state.filterDate = latestDateForTable;
    DOM.filterSymbol.value = '';
    DOM.filterDate.value = latestDateForTable;
    await loadTable(tableName);
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

if (DOM.insertRowBtn) {
    DOM.insertRowBtn.addEventListener('click', () => {
        if (!state.currentTable) return;
        insertBlankRow();
    });
}
if (DOM.copyRowBtn) {
    DOM.copyRowBtn.addEventListener('click', () => {
        if (state.checkedRows.size === 0) return;
        const firstIdx = Math.min(...state.checkedRows);
        copyAndInsertRow(firstIdx);
    });
}
if (DOM.deleteRowBtn) {
    DOM.deleteRowBtn.addEventListener('click', () => {
        if (state.checkedRows.size === 0) return;
        deleteSelectedRows();
    });
}

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

        // Default to latest snapshot date available
        if (DOM.datePicker.options.length > 0) {
            const latestDate = dates[0].split(' ')[0];  // First date is latest (descending order)
            state.latestDate = latestDate;
            DOM.datePicker.value = latestDate;
            DOM.filterDate.value = latestDate;
            state.filterDate = latestDate;
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
    // Clear date range when single date is chosen
    if (DOM.filterDateFrom) DOM.filterDateFrom.value = '';
    if (DOM.filterDateTo)   DOM.filterDateTo.value   = '';
    state.filterDateFrom = '';
    state.filterDateTo   = '';
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
        state.checkedRows.clear();
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

        // If a symbol is set with no explicit date range → show all dates for that symbol.
        // Date range takes priority over single date when both symbol and range are set.
        if (state.filterDateFrom || state.filterDateTo) {
            url += `&date=all`;
            if (state.filterDateFrom) url += `&date_from=${state.filterDateFrom}`;
            if (state.filterDateTo)   url += `&date_to=${state.filterDateTo}`;
        } else if (state.filterSymbol && !state.filterDate) {
            url += `&date=all`;   // symbol only — search across all dates
        } else if (state.filterDate) {
            url += `&date=${state.filterDate}`;
        } else {
            url += `&date=all`;
        }

        // Symbol filter
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
        state.checkedRows.clear();

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
    // Headers: checkbox column + data columns
    const checkboxHeader = '<th style="width: 32px; padding: 12px 6px;"><input type="checkbox" id="selectAll" title="Select all rows on this page"></th>';
    const headers = state.columns.map(col => {
        const classList = col.is_pk ? ' class="pk-col"' : '';
        const isSorted = state.sortColumn === col.name;
        const indicator = isSorted
            ? `<span class="sort-indicator">${state.sortDirection === 'asc' ? '↑' : '↓'}</span>`
            : '';
        return `<th${classList} data-column="${col.name}">${col.name}${indicator}</th>`;
    }).join('');
    DOM.headerRow.innerHTML = checkboxHeader + headers;

    // Sort handlers on data column headers only
    DOM.headerRow.querySelectorAll('th[data-column]').forEach(th => {
        th.addEventListener('click', async (e) => {
            if (e.target.tagName === 'INPUT') return;
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

    // selectAll checkbox listener (created fresh each render)
    const selectAllEl = document.getElementById('selectAll');
    if (selectAllEl) {
        selectAllEl.addEventListener('change', (e) => {
            state.checkedRows.clear();
            if (e.target.checked) {
                for (let i = 0; i < state.rows.length; i++) state.checkedRows.add(i);
            }
            updateCheckboxesUI();
            updateButtonStates();
        });
    }

    // Rows: checkbox + editable non-PK cells
    const rows = state.rows.map((row, idx) => {
        const checkbox = `<td style="padding: 10px 6px;"><input type="checkbox" data-row-idx="${idx}"></td>`;
        const cells = state.columns.map(col => {
            const value = row[col.name];
            const displayValue = value === null ? '(null)' : String(value);
            if (col.is_pk) {
                return `<td class="pk-col">${escapeHtml(displayValue)}</td>`;
            }
            const fileCls = isFilePathColumn(col.name) ? ' file-link' : '';
            return `<td class="edit-cell${fileCls}" data-col="${col.name}" data-original="${escapeHtml(displayValue)}">${highlightKeywords(displayValue)}</td>`;
        }).join('');
        return `<tr>${checkbox}${cells}</tr>`;
    }).join('');
    DOM.tableBody.innerHTML = rows;

    // Per-row checkbox listeners
    DOM.tableBody.querySelectorAll('input[data-row-idx]').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.rowIdx);
            if (e.target.checked) state.checkedRows.add(idx);
            else state.checkedRows.delete(idx);
            updateSelectAllCheckbox();
            updateButtonStates();
        });
    });

    // Inline editing on non-PK cells (same pattern as Ref Data screen)
    DOM.tableBody.querySelectorAll('.edit-cell').forEach(cell => {
        cell.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT') return;
            const col = cell.dataset.col;
            const original = cell.dataset.original;
            const input = document.createElement('input');
            input.type = 'text';
            input.value = original === '(null)' ? '' : original;
            input.style.width = '100%';
            cell.innerHTML = '';
            cell.appendChild(input);
            input.focus();
            input.select();
            const save = async () => { await updateCell(col, input.value, cell); };
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') save();
                else if (e.key === 'Escape') { cell.textContent = original; }
            });
            input.addEventListener('blur', save);
        });
    });

    updateButtonStates();
    updateSelectAllCheckbox();

    // Pagination (top inline, top full, and bottom)
    const maxPage = Math.ceil(state.total / state.pageSize);
    const startRow = state.currentPage * state.pageSize + 1;
    const endRow = Math.min((state.currentPage + 1) * state.pageSize, state.total);
    const pageText = `Showing ${startRow}–${endRow} of ${state.total}`;
    const currentPageNum = state.currentPage + 1;

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


// ─────────────────────────────────────────────────────────────────────────────
// Row selection + mutation (Copy / Delete / Insert / inline edit).
// Same patterns as web/ref.js, calls /api/data/{table} (Explore-eligible).
// ─────────────────────────────────────────────────────────────────────────────

function updateCheckboxesUI() {
    DOM.tableBody.querySelectorAll('input[data-row-idx]').forEach(cb => {
        const idx = parseInt(cb.dataset.rowIdx);
        cb.checked = state.checkedRows.has(idx);
    });
    updateSelectAllCheckbox();
}

function updateSelectAllCheckbox() {
    const sa = document.getElementById('selectAll');
    if (!sa) return;
    const allSelected = state.rows.length > 0 && state.checkedRows.size === state.rows.length;
    const someSelected = state.checkedRows.size > 0 && state.checkedRows.size < state.rows.length;
    sa.checked = allSelected;
    sa.indeterminate = someSelected;
}

function updateButtonStates() {
    if (DOM.copyRowBtn) DOM.copyRowBtn.disabled = state.checkedRows.size === 0;
    if (DOM.deleteRowBtn) DOM.deleteRowBtn.disabled = state.checkedRows.size === 0;
    if (DOM.insertRowBtn) DOM.insertRowBtn.disabled = !state.currentTable;
}

async function updateCell(colName, newValue, cellEl) {
    if (!state.currentTable || !state.columns.length) return;
    const tr = cellEl.parentNode;
    const rowIdx = Array.from(DOM.tableBody.children).indexOf(tr);
    if (rowIdx < 0 || rowIdx >= state.rows.length) return;
    const row = state.rows[rowIdx];
    const pk = {};
    state.columns.forEach(col => { if (col.is_pk) pk[col.name] = row[col.name]; });
    try {
        const result = await fetchJSON(`/api/data/${state.currentTable}/row`, {
            method: 'PATCH',
            body: JSON.stringify({ pk, updates: { [colName]: newValue === '' ? null : newValue } }),
        });
        if (result.updated > 0) {
            const shown = newValue === '' ? '(null)' : newValue;
            cellEl.textContent = shown;
            cellEl.dataset.original = shown;
            row[colName] = newValue === '' ? null : newValue;
            showStatus(`Updated ${colName}`, 'success');
        } else {
            cellEl.textContent = cellEl.dataset.original;
            showStatus(`Update failed: no rows affected`, 'error');
        }
    } catch (e) {
        cellEl.textContent = cellEl.dataset.original;
        showStatus(`Update failed: ${e.message}`, 'error');
    }
}

function insertBlankRow() {
    if (!state.currentTable) return;
    const blank = {};
    state.columns.forEach(col => { blank[col.name] = ''; });
    showInlineEditor(blank, true);
}

function copyAndInsertRow(rowIdx) {
    if (rowIdx < 0 || rowIdx >= state.rows.length) return;
    showInlineEditor({ ...state.rows[rowIdx] }, false, rowIdx);
}

function showInlineEditor(newRowData, atTop, sourceIdx) {
    // Only one editor at a time
    const existing = DOM.tableBody.querySelector('tr.new-row-editor');
    if (existing) existing.remove();

    const newTr = document.createElement('tr');
    newTr.className = 'new-row-editor';
    newTr.style.backgroundColor = '#fffacd';

    // Save / Cancel buttons in the checkbox column
    const btnCell = document.createElement('td');
    btnCell.style.padding = '6px';
    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'margin-right: 4px; background: #dcfce7; color: #16a34a; padding: 4px 8px; border: 1px solid #86efac; border-radius: 3px; cursor: pointer; font-size: 11px;';
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'background: #fee2e2; color: #dc2626; padding: 4px 8px; border: 1px solid #fca5a5; border-radius: 3px; cursor: pointer; font-size: 11px;';
    btnCell.appendChild(saveBtn);
    btnCell.appendChild(cancelBtn);
    newTr.appendChild(btnCell);

    // Editable cells (PK fields included so user can set them for insert)
    state.columns.forEach(col => {
        const cell = document.createElement('td');
        cell.style.padding = '6px';
        const input = document.createElement('input');
        input.type = 'text';
        input.value = newRowData[col.name] ?? '';
        input.placeholder = col.is_pk ? `${col.name} (PK)` : col.name;
        input.style.cssText = 'width: 100%; padding: 4px; border: 1px solid var(--accent); border-radius: 3px; font-size: 12px;';
        cell.appendChild(input);
        newTr.appendChild(cell);
        input.addEventListener('change', () => {
            newRowData[col.name] = input.value === '' ? null : input.value;
        });
    });

    if (atTop || sourceIdx === undefined) {
        DOM.tableBody.insertBefore(newTr, DOM.tableBody.firstChild);
    } else {
        const tableRows = DOM.tableBody.querySelectorAll('tr');
        const targetRow = tableRows[sourceIdx];
        if (targetRow) targetRow.parentNode.insertBefore(newTr, targetRow.nextSibling);
        else DOM.tableBody.insertBefore(newTr, DOM.tableBody.firstChild);
    }

    const firstInput = newTr.querySelector('input');
    if (firstInput) { firstInput.focus(); firstInput.select(); }

    cancelBtn.addEventListener('click', () => newTr.remove());

    saveBtn.addEventListener('click', async () => {
        // Pull latest values from the inputs (handles users who didn't blur)
        const payload = {};
        const inputs = newTr.querySelectorAll('td input[type="text"]');
        state.columns.forEach((col, i) => {
            const v = inputs[i] ? inputs[i].value : '';
            payload[col.name] = v === '' ? null : v;
        });
        let valid = true;
        state.columns.forEach(col => {
            if (col.is_pk && (payload[col.name] === null || payload[col.name] === undefined)) {
                showStatus(`Primary key field "${col.name}" cannot be empty`, 'error');
                valid = false;
            }
        });
        if (!valid) return;
        saveBtn.disabled = true;
        cancelBtn.disabled = true;
        try {
            await fetchJSON(`/api/data/${state.currentTable}`, {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            newTr.remove();
            showStatus('Row inserted successfully', 'success');
            await loadTable(state.currentTable);
        } catch (e) {
            showStatus(`Insert failed: ${e.message}`, 'error');
            saveBtn.disabled = false;
            cancelBtn.disabled = false;
        }
    });
}

async function deleteSelectedRows() {
    if (state.checkedRows.size === 0 || !state.currentTable) return;
    const rowsToDelete = Array.from(state.checkedRows).map(idx => state.rows[idx]);
    const count = rowsToDelete.length;
    if (!confirm(`Delete ${count} row(s) from ${state.currentTable}? This cannot be undone.`)) return;
    let successCount = 0, failureCount = 0;
    for (const row of rowsToDelete) {
        try {
            const pk = {};
            state.columns.forEach(col => { if (col.is_pk) pk[col.name] = row[col.name]; });
            const resp = await fetch(`/api/data/${state.currentTable}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pk),
            });
            if (resp.ok) successCount++; else failureCount++;
        } catch (e) {
            console.error('Delete failed:', e);
            failureCount++;
        }
    }
    state.checkedRows.clear();
    await loadTable(state.currentTable);
    if (failureCount === 0) showStatus(`Deleted ${successCount} row(s)`, 'success');
    else showStatus(`Deleted ${successCount}, failed ${failureCount}`, 'error');
}

