const state = {
    tables: [],
    currentTable: null,
    columns: [],
    allRows: [],
    rows: [],
    total: 0,
    currentPage: 0,
    pageSize: 200,
    checkedRows: new Set(),
    filterText: '',
    sortKey: null,
    sortDir: 'asc',
    pageRows: [],
};

const DOM = {
    tableSelect: document.getElementById('tableSelect'),
    reloadBtn: document.getElementById('reloadBtn'),
    copyRowBtn: document.getElementById('copyRowBtn'),
    deleteRowBtn: document.getElementById('deleteRowBtn'),
    statusBar: document.getElementById('statusBar'),
    tableInfo: document.getElementById('tableInfo'),
    headerRow: document.getElementById('headerRow'),
    tableBody: document.getElementById('tableBody'),
    pagination: document.getElementById('pagination'),
    pageInfo: document.getElementById('pageInfo'),
    prevBtn: document.getElementById('prevBtn'),
    nextBtn: document.getElementById('nextBtn'),
    selectAll: document.getElementById('selectAll'),
    excelFileInput: document.getElementById('excelFileInput'),
    filterSearch: document.getElementById('filterSearch'),
    filterApplyBtn: document.getElementById('filterApplyBtn'),
    filterClearBtn: document.getElementById('filterClearBtn'),
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadTableList();
    setupFilterListeners();
    setupEventListeners();

    // Honor ?table=<name> from the URL — used by deep-links from File Monitor.
    const params = new URLSearchParams(window.location.search);
    const requested = params.get('table');
    if (requested) {
        const exists = state.tables.some(t => t.name === requested);
        if (exists) {
            DOM.tableSelect.value = requested;
            await loadTable(requested);
        } else {
            showStatus(`Table "${requested}" is not a ref_* table — open it in the DB Data page instead.`, 'error');
        }
    }
});

function setupFilterListeners() {
    DOM.filterApplyBtn?.addEventListener('click', () => {
        state.filterText = DOM.filterSearch.value.trim().toLowerCase();
        state.currentPage = 0;
        applyFilter();
    });

    DOM.filterClearBtn?.addEventListener('click', () => {
        state.filterText = '';
        DOM.filterSearch.value = '';
        state.currentPage = 0;
        applyFilter();
    });

    DOM.filterSearch?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            DOM.filterApplyBtn.click();
        }
    });
}

function setupEventListeners() {
    DOM.tableSelect.addEventListener('change', async (e) => {
        state.currentPage = 0;
        state.filterText = '';
        DOM.filterSearch.value = '';
        await loadTable(e.target.value);
    });

    DOM.reloadBtn.addEventListener('click', () => {
        DOM.excelFileInput.click();
    });

    DOM.excelFileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        await reloadTableFromFile(file);
        e.target.value = '';
    });

    DOM.copyRowBtn.addEventListener('click', () => {
        if (state.checkedRows.size === 0) return;
        const firstIdx = Math.min(...state.checkedRows);
        copyAndInsertRow(firstIdx);
    });

    DOM.deleteRowBtn.addEventListener('click', () => {
        if (state.checkedRows.size === 0) return;
        deleteSelectedRows();
    });

    DOM.prevBtn.addEventListener('click', () => {
        if (state.currentPage > 0) {
            state.currentPage--;
            renderTable();
        }
    });

    DOM.nextBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(state.total / state.pageSize) - 1;
        if (state.currentPage < maxPage) {
            state.currentPage++;
            renderTable();
        }
    });
}

function applyFilter() {
    if (!state.filterText) {
        state.rows = [...state.allRows];
    } else {
        state.rows = state.allRows.filter(row => {
            // Search across all columns
            return Object.values(row).some(val => {
                const str = (val === null ? '(null)' : String(val)).toLowerCase();
                return str.includes(state.filterText);
            });
        });
    }
    state.total = state.rows.length;
    state.currentPage = 0;
    renderTable();
}

// fetchJSON is provided by _common.js (window.fetchJSON).

async function loadTableList() {
    try {
        console.log('[REF] Loading table list from /api/ref/tables...');
        state.tables = await fetchJSON('/api/ref/tables');
        console.log('[REF] Got tables:', state.tables);

        if (!Array.isArray(state.tables)) {
            throw new Error(`Expected array, got ${typeof state.tables}`);
        }

        const options = state.tables.map(t => {
            const label = `${t.name} (${t.row_count} rows)${t.tunable ? '' : ' [read-only]'}`;
            return `<option value="${t.name}">${label}</option>`;
        });

        DOM.tableSelect.innerHTML = '<option value="">Choose a table...</option>' + options.join('');
        console.log('[REF] Combo box populated with', options.length, 'options');
    } catch (e) {
        const errorMsg = e?.message || String(e) || 'Unknown error';
        console.error('[REF] Failed to load tables:', e);
        showStatus(`Failed to load tables: ${errorMsg}`, 'error');
    }
}

async function loadTable(tableName) {
    if (!tableName) {
        state.currentTable = null;
        state.columns = [];
        state.rows = [];
        state.allRows = [];
        state.sortKey = null;
        state.sortDir = 'asc';
        DOM.tableBody.innerHTML = '';
        DOM.headerRow.innerHTML = '';
        updateCopyButtonState();
        updateDeleteButtonState();
        return;
    }

    try {
        console.log('[REF] Loading table:', tableName);
        const url = `/api/ref/${tableName}?limit=5000`;
        console.log('[REF] Fetching URL:', url);
        const data = await fetchJSON(url);
        console.log('[REF] Got data for', tableName, 'with', data.rows.length, 'rows');

        state.currentTable = tableName;
        state.columns = data.columns;
        state.allRows = data.rows;
        state.total = data.total;

        // Apply filter if any
        applyFilter();

        // Update reload button state
        const tableMeta = state.tables.find(t => t.name === tableName);
        DOM.reloadBtn.disabled = !tableMeta || !tableMeta.tunable;

        // Update table info
        const maxPage = Math.ceil(state.rows.length / state.pageSize);
        DOM.tableInfo.textContent = `${state.rows.length} of ${state.total} rows ${state.filterText ? '(filtered)' : ''}(page ${state.currentPage + 1}/${maxPage})`;

        renderTable();
        showStatus(`Loaded ${tableName}: ${state.total} rows`, 'success');
    } catch (e) {
        console.error('[REF] Catch block - full error:', e);
        console.error('[REF] Error message:', e?.message);
        console.error('[REF] Error detail:', e?.detail);
        console.error('[REF] Error toString:', String(e));
        if (e instanceof Error) {
            console.error('[REF] Error stack:', e.stack);
        }

        let errorMsg = 'Unknown error';
        if (e?.message) {
            errorMsg = e.message;
        } else if (typeof e === 'string') {
            errorMsg = e;
        } else if (e?.detail) {
            errorMsg = e.detail;
        } else {
            errorMsg = String(e) || 'Unknown error occurred';
        }

        showStatus(`Failed to load table: ${errorMsg}`, 'error');
    }
}

function renderTable() {
    // Headers - keep existing checkboxes th
    const checkboxHeader = '<th style="width: 32px; padding: 12px 6px;"><input type="checkbox" id="selectAll" title="Select all rows on this page"></th>';
    const headers = state.columns.map(col => {
        const isSort = state.sortKey === col.name;
        const ind = isSort ? (state.sortDir === 'asc' ? ' ▲' : ' ▼') : '';
        const cls = col.is_pk ? 'pk-col sortable' : 'sortable';
        return `<th class="${cls}" data-col="${col.name}" style="cursor:pointer;user-select:none;">${col.name}${ind}</th>`;
    }).join('');
    DOM.headerRow.innerHTML = checkboxHeader + headers;
    DOM.headerRow.querySelectorAll('th[data-col]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.col;
            if (state.sortKey === col) {
                state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                state.sortKey = col;
                state.sortDir = 'asc';
            }
            renderTable();
        });
    });
    DOM.selectAll = document.getElementById('selectAll');
    DOM.selectAll.addEventListener('change', (e) => {
        state.checkedRows.clear();
        if (e.target.checked) {
            for (let i = 0; i < state.rows.length; i++) {
                state.checkedRows.add(i);
            }
        }
        updateCheckboxesUI();
        updateCopyButtonState();
        updateDeleteButtonState();
    });

    // Sort
    let displayRows = [...state.rows];
    if (state.sortKey) {
        const key = state.sortKey, asc = state.sortDir === 'asc';
        displayRows.sort((a, b) => {
            const va = a[key], vb = b[key];
            if (va == null && vb == null) return 0;
            if (va == null) return asc ? 1 : -1;
            if (vb == null) return asc ? -1 : 1;
            const na = Number(va), nb = Number(vb);
            if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
            return asc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
        });
    }
    const pageStart = state.currentPage * state.pageSize;
    const pageRows = displayRows.slice(pageStart, pageStart + state.pageSize);
    state.pageRows = pageRows;

    // Rows with checkbox column
    const rows = pageRows.map((row, idx) => {
        const isChecked = state.checkedRows.has(idx) ? 'checked' : '';
        const checkbox = `<td style="padding: 10px 6px;"><input type="checkbox" data-row-idx="${idx}" ${isChecked}></td>`;
        const cells = state.columns.map(col => {
            const value = row[col.name];
            const displayValue = value === null ? '(null)' : String(value);
            if (col.is_pk) {
                return `<td class="pk-col">${escapeHtml(displayValue)}</td>`;
            }
            return `<td class="edit-cell" data-col="${col.name}" data-original="${displayValue}">${highlightKeywords(displayValue)}</td>`;
        }).join('');
        return `<tr>${checkbox}${cells}</tr>`;
    }).join('');
    DOM.tableBody.innerHTML = rows;

    // Add checkbox change listeners
    document.querySelectorAll('input[data-row-idx]').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.rowIdx);
            if (e.target.checked) {
                state.checkedRows.add(idx);
            } else {
                state.checkedRows.delete(idx);
            }
            updateSelectAllCheckbox();
            updateCopyButtonState();
            updateDeleteButtonState();
        });
    });

    // Attach edit listeners
    document.querySelectorAll('.edit-cell').forEach(cell => {
        cell.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT') return;
            const col = cell.dataset.col;
            const original = cell.dataset.original;
            const input = document.createElement('input');
            input.type = 'text';
            input.value = original === '(null)' ? '' : original;
            cell.innerHTML = '';
            cell.appendChild(input);
            input.focus();
            input.select();

            const save = async () => {
                const newVal = input.value;
                await updateCell(col, newVal, cell);
            };

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') save();
                else if (e.key === 'Escape') {
                    cell.textContent = original;
                }
            });

            input.addEventListener('blur', save);
        });
    });

    // Pagination
    const maxPage = Math.ceil(state.total / state.pageSize);
    if (state.total > state.pageSize) {
        DOM.pagination.style.display = 'flex';
        const startRow = state.currentPage * state.pageSize + 1;
        const endRow = Math.min((state.currentPage + 1) * state.pageSize, state.total);
        DOM.pageInfo.textContent = `Showing ${startRow}–${endRow} of ${state.total}`;
        DOM.prevBtn.disabled = state.currentPage === 0;
        DOM.nextBtn.disabled = state.currentPage >= maxPage - 1;
    } else {
        DOM.pagination.style.display = 'none';
    }
}

async function updateCell(colName, newValue, cellEl) {
    if (!state.currentTable || !state.columns.length) return;

    // Build PK object
    const pk = {};
    const row = state.pageRows[Array.from(cellEl.parentNode.parentNode.children).findIndex(r => r === cellEl.parentNode)];
    state.columns.forEach(col => {
        if (col.is_pk) pk[col.name] = row[col.name];
    });

    try {
        const result = await fetchJSON(`/api/ref/${state.currentTable}/row`, {
            method: 'PATCH',
            body: JSON.stringify({
                pk,
                updates: { [colName]: newValue },
            }),
        });

        if (result.updated > 0) {
            cellEl.classList.add('flash-success');
            cellEl.textContent = newValue === '' ? '(empty)' : newValue;
            cellEl.dataset.original = newValue === '' ? '(empty)' : newValue;
            showStatus(`Updated ${colName}`, 'success');
        } else {
            cellEl.classList.add('flash-error');
            cellEl.textContent = cellEl.dataset.original;
            showStatus(`Update failed: no rows affected`, 'error');
        }
    } catch (e) {
        cellEl.classList.add('flash-error');
        cellEl.textContent = cellEl.dataset.original;
        showStatus(`Update failed: ${e.message}`, 'error');
    }
}

function updateCheckboxesUI() {
    document.querySelectorAll('input[data-row-idx]').forEach(cb => {
        const idx = parseInt(cb.dataset.rowIdx);
        cb.checked = state.checkedRows.has(idx);
    });
    updateSelectAllCheckbox();
}

function updateSelectAllCheckbox() {
    const allSelected = state.rows.length > 0 && state.checkedRows.size === state.rows.length;
    const someSelected = state.checkedRows.size > 0 && state.checkedRows.size < state.rows.length;
    DOM.selectAll.checked = allSelected;
    DOM.selectAll.indeterminate = someSelected;
}

function updateCopyButtonState() {
    DOM.copyRowBtn.disabled = state.checkedRows.size === 0;
}

function updateDeleteButtonState() {
    DOM.deleteRowBtn.disabled = state.checkedRows.size === 0;
}

async function copyAndInsertRow(rowIdx) {
    if (rowIdx < 0 || rowIdx >= state.rows.length) return;

    const sourceRow = state.rows[rowIdx];
    const newRowData = { ...sourceRow };

    // Find the table row in DOM and insert a new editable row below
    const tableRows = DOM.tableBody.querySelectorAll('tr');
    const targetRow = tableRows[rowIdx];
    if (!targetRow) return;

    const newTr = document.createElement('tr');
    newTr.className = 'new-row-editor';
    newTr.style.backgroundColor = '#fffacd';

    // Checkbox cell (empty for new row)
    const checkboxCell = document.createElement('td');
    checkboxCell.style.padding = '10px 6px';
    newTr.appendChild(checkboxCell);

    // Data cells (all editable)
    state.columns.forEach(col => {
        const cell = document.createElement('td');
        cell.style.padding = '10px 12px';
        const currentValue = newRowData[col.name] ?? '';
        const input = document.createElement('input');
        input.type = 'text';
        input.value = currentValue;
        input.style.width = '100%';
        input.style.padding = '6px';
        input.style.border = '1px solid var(--accent)';
        input.style.borderRadius = '3px';
        cell.appendChild(input);
        newTr.appendChild(cell);

        input.addEventListener('change', () => {
            newRowData[col.name] = input.value || null;
        });
    });

    // Insert the new row
    targetRow.parentNode.insertBefore(newTr, targetRow.nextSibling);
    const firstInput = newTr.querySelector('input');
    if (firstInput) firstInput.focus();

    // Add save/cancel buttons
    const btnCell = document.createElement('td');
    btnCell.style.padding = '10px 6px';
    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.marginRight = '6px';
    saveBtn.style.background = '#dcfce7';
    saveBtn.style.color = '#16a34a';
    saveBtn.style.padding = '4px 8px';
    saveBtn.style.border = '1px solid #86efac';
    saveBtn.style.borderRadius = '3px';
    saveBtn.style.cursor = 'pointer';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.background = '#fee2e2';
    cancelBtn.style.color = '#dc2626';
    cancelBtn.style.padding = '4px 8px';
    cancelBtn.style.border = '1px solid #fca5a5';
    cancelBtn.style.borderRadius = '3px';
    cancelBtn.style.cursor = 'pointer';

    btnCell.appendChild(saveBtn);
    btnCell.appendChild(cancelBtn);

    // Re-insert the new row with buttons
    newTr.removeChild(newTr.lastChild); // Remove last data cell
    newTr.appendChild(btnCell); // Add buttons cell
    for (let i = state.columns.length - 1; i >= 0; i--) {
        newTr.insertBefore(newTr.children[i + 1], newTr.children[i + 1]);
    }

    cancelBtn.addEventListener('click', () => {
        newTr.remove();
    });

    saveBtn.addEventListener('click', async () => {
        // Validate PK fields are present
        const pk = {};
        let valid = true;
        state.columns.forEach(col => {
            if (col.is_pk) {
                const val = newRowData[col.name];
                if (!val) {
                    showStatus(`Primary key field "${col.name}" cannot be empty`, 'error');
                    valid = false;
                }
                pk[col.name] = val;
            }
        });
        if (!valid) return;

        // Disable both buttons during the async call to prevent double-submit.
        // On failure they get re-enabled so the user can edit + retry.
        saveBtn.disabled = true;
        cancelBtn.disabled = true;

        try {
            await fetchJSON(`/api/ref/${state.currentTable}`, {
                method: 'POST',
                body: JSON.stringify(newRowData),
            });
            // Success: remove the new-row editor directly so the Save/Cancel
            // buttons go away immediately (don't depend on loadTable's
            // tbody.innerHTML wipe — guard against any future re-render
            // change that might leave the editor row in place).
            newTr.remove();
            showStatus('Row inserted successfully', 'success');
            state.currentPage = 0;
            await loadTable(state.currentTable);
            state.checkedRows.clear();
            updateCopyButtonState();
            updateDeleteButtonState();
        } catch (e) {
            showStatus(`Insert failed: ${e.message}`, 'error');
            // Failure path: keep the row visible with editable fields so
            // the user can fix the input and click Save again.
            saveBtn.disabled = false;
            cancelBtn.disabled = false;
        }
    });
}

async function reloadTableFromFile(file) {
    if (!state.currentTable) {
        showStatus('No table selected', 'error');
        return;
    }

    try {
        const formData = new FormData();
        formData.append('file', file);

        const resp = await fetch(`/api/ref/${state.currentTable}/load-excel`, {
            method: 'POST',
            body: formData,
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }

        const result = await resp.json();
        showStatus(`Reloaded: ${result.inserted} rows inserted, ${result.skipped || 0} skipped`, 'success');
        await loadTable(state.currentTable);
    } catch (e) {
        showStatus(`Reload failed: ${e.message}`, 'error');
    }
}

function showStatus(message, type) {
    const msg = String(message || 'Unknown error');
    DOM.statusBar.textContent = msg;
    DOM.statusBar.className = `status-bar ${type}`;
    DOM.statusBar.style.display = 'block';
    if (type === 'success') {
        setTimeout(() => { DOM.statusBar.style.display = 'none'; }, 3000);
    }
}

function highlightKeywords(text) {
    // Semantic keyword highlighting
    const bullishRegex = /\bbullish\b/gi;
    const bearishRegex = /\bbearish\b/gi;
    const longPrimaryRegex = /\bbest idea long\b/gi;
    const longSecondaryRegex = /\blong\b/gi;
    const longTertiaryRegex = /\blong bench\b/gi;
    const shortPrimaryRegex = /\bbest idea short\b/gi;
    const shortSecondaryRegex = /\bshort\b/gi;
    const shortTertiaryRegex = /\bshort bench\b/gi;

    let result = text;
    result = result.replace(bullishRegex, '<span class="hl-bullish">$&</span>');
    result = result.replace(bearishRegex, '<span class="hl-bearish">$&</span>');
    result = result.replace(longPrimaryRegex, '<span class="hl-long-primary">$&</span>');
    result = result.replace(longSecondaryRegex, '<span class="hl-long-secondary">$&</span>');
    result = result.replace(longTertiaryRegex, '<span class="hl-long-tertiary">$&</span>');
    result = result.replace(shortPrimaryRegex, '<span class="hl-short-primary">$&</span>');
    result = result.replace(shortSecondaryRegex, '<span class="hl-short-secondary">$&</span>');
    result = result.replace(shortTertiaryRegex, '<span class="hl-short-tertiary">$&</span>');

    return result;
}

// escapeHtml is provided by _common.js (window.escapeHtml).

async function deleteSelectedRows() {
    if (state.checkedRows.size === 0 || !state.currentTable) return;

    const rowsToDelete = Array.from(state.checkedRows).map(idx => state.rows[idx]);
    const count = rowsToDelete.length;
    const confirmed = confirm(`Delete ${count} row(s)? This cannot be undone.`);
    if (!confirmed) return;

    let successCount = 0;
    let failureCount = 0;

    for (const row of rowsToDelete) {
        try {
            // Build pk object from row data
            const pk = {};
            state.columns.forEach(col => {
                if (col.is_pk) pk[col.name] = row[col.name];
            });
            const params = new URLSearchParams();
            for (const [k, v] of Object.entries(pk)) {
                params.append(k, v);
            }
            const resp = await fetch(`/api/ref/${state.currentTable}?${params.toString()}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pk),
            });
            if (resp.ok) {
                successCount++;
            } else {
                failureCount++;
            }
        } catch (e) {
            console.error('Delete row failed:', e);
            failureCount++;
        }
    }

    state.checkedRows.clear();
    await loadTable(state.currentTable);
    updateCopyButtonState();
    updateDeleteButtonState();
    if (failureCount === 0) {
        showStatus(`Deleted ${successCount} row(s)`, 'success');
    } else {
        showStatus(`Deleted ${successCount}, failed ${failureCount}`, 'error');
    }
}
