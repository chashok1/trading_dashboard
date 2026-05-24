/**
 * Trigger Rules Analyzer - View which rules fire for each stock
 */

const state = {
    allRules: [],
    symbols: [],
    currentSymbol: null,
    currentPage: 0,
    pageSize: 50,
    triggeredFilter: '',
    compositeFilter: '',
    compositeRules: new Set(),
};

const DOM = {
    statusBar: document.getElementById('statusBar'),
    trigList: document.getElementById('trigList'),
    trigDetail: document.getElementById('trigDetail'),
    trigFilter: document.getElementById('trigFilter'),
    compositeFilter: document.getElementById('compositeFilter'),
    trigStats: document.getElementById('trigStats'),
    pagination: document.getElementById('pagination'),
    pageInfo: document.getElementById('pageInfo'),
    prevBtn: document.getElementById('prevBtn'),
    nextBtn: document.getElementById('nextBtn'),
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadDashboardDate();
    await loadTrigRules();
    renderStats();
    renderSymbolList();
});

DOM.trigFilter.addEventListener('change', (e) => {
    state.triggeredFilter = e.target.value;
    state.currentPage = 0;
    renderSymbolList();
});

DOM.compositeFilter.addEventListener('change', (e) => {
    state.compositeFilter = e.target.value;
    state.currentPage = 0;
    renderSymbolList();
});

DOM.prevBtn.addEventListener('click', () => {
    if (state.currentPage > 0) {
        state.currentPage--;
        renderSymbolList();
    }
});

DOM.nextBtn.addEventListener('click', () => {
    const maxPage = Math.ceil(state.symbols.length / state.pageSize) - 1;
    if (state.currentPage < maxPage) {
        state.currentPage++;
        renderSymbolList();
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
            // FastAPI 422 returns detail as a LIST of {loc, msg, type}; pluck
            // the human-readable msg out so the screen doesn't show
            // "[object Object]". Other errors usually have detail as string.
            let msg;
            if (Array.isArray(err.detail)) {
                msg = err.detail.map(e => {
                    const loc = Array.isArray(e.loc) ? e.loc.join('.') : (e.loc || '');
                    return loc ? `${loc}: ${e.msg}` : e.msg;
                }).join('; ');
            } else if (typeof err.detail === 'object' && err.detail !== null) {
                msg = JSON.stringify(err.detail);
            } else {
                msg = err.detail || resp.statusText;
            }
            throw new Error(`HTTP ${resp.status}: ${msg}`);
        }
        return await resp.json();
    } catch (e) {
        console.error(`Fetch error: ${e.message}`);
        throw e;
    }
}

async function loadDashboardDate() {
    try {
        const dates = await fetchJSON('/api/dates');
        if (dates.length > 0) {
            window.dashboardDate = dates[0];
        }
    } catch (e) {
        showStatus(`Failed to load date: ${e.message}`, 'error');
    }
}

async function loadTrigRules() {
    try {
        const data = await fetchJSON(`/api/data/drv_trig?limit=10000&offset=0&date=${window.dashboardDate}`);
        state.allRules = data.rows;

        // Extract unique symbols
        const symbolSet = new Set();
        const compositeSet = new Set();
        state.allRules.forEach(rule => {
            symbolSet.add(rule.symbol);
            compositeSet.add(rule.composite_rule_code);
        });

        state.symbols = Array.from(symbolSet).sort();
        state.compositeRules = compositeSet;

        // Populate composite rule filter
        populateCompositeFilter();

        showStatus(`Loaded ${state.allRules.length} trigger rules for ${state.symbols.length} symbols`, 'success');
    } catch (e) {
        showStatus(`Failed to load trigger rules: ${e.message}`, 'error');
    }
}

function populateCompositeFilter() {
    const select = DOM.compositeFilter;
    const sorted = Array.from(state.compositeRules).sort();

    select.innerHTML = '<option value="">All Rules</option>' +
        sorted.map(code => `<option value="${code}">${code}</option>`).join('');
}

function getFilteredRules(symbol) {
    let filtered = state.allRules.filter(r => r.symbol === symbol);

    if (state.triggeredFilter === 'true') {
        filtered = filtered.filter(r => r.triggered);
    } else if (state.triggeredFilter === 'false') {
        filtered = filtered.filter(r => !r.triggered);
    }

    if (state.compositeFilter) {
        filtered = filtered.filter(r => r.composite_rule_code === state.compositeFilter);
    }

    return filtered;
}

function renderStats() {
    const triggered = state.allRules.filter(r => r.triggered).length;
    const notTriggered = state.allRules.filter(r => !r.triggered).length;
    const uniqueComposites = state.compositeRules.size;
    const avgScore = (state.allRules.reduce((sum, r) => sum + r.score, 0) / state.allRules.length).toFixed(2);

    const html = `
        <div class="trig-stat-card">
            <div class="trig-stat-value" style="color: var(--bull);">${triggered}</div>
            <div class="trig-stat-label">Rules Triggered</div>
        </div>
        <div class="trig-stat-card">
            <div class="trig-stat-value" style="color: var(--bear);">${notTriggered}</div>
            <div class="trig-stat-label">Not Triggered</div>
        </div>
        <div class="trig-stat-card">
            <div class="trig-stat-value">${uniqueComposites}</div>
            <div class="trig-stat-label">Composite Rules</div>
        </div>
        <div class="trig-stat-card">
            <div class="trig-stat-value">${avgScore}</div>
            <div class="trig-stat-label">Avg Score</div>
        </div>
    `;

    DOM.trigStats.innerHTML = html;
}

function renderSymbolList() {
    const start = state.currentPage * state.pageSize;
    const end = start + state.pageSize;
    const pageSymbols = state.symbols.slice(start, end);

    const html = pageSymbols.map((sym, idx) => {
        const symbolRules = getFilteredRules(sym);
        const triggered = symbolRules.filter(r => r.triggered).length;
        const total = symbolRules.length;
        const isActive = sym === state.currentSymbol ? 'active' : '';

        return `
            <div class="trig-list-item ${isActive}" data-symbol="${sym}">
                <div class="trig-list-item-symbol">${sym}</div>
                <div class="trig-list-item-info">
                    ${triggered}/${total} rules triggered
                </div>
            </div>
        `;
    }).join('');

    DOM.trigList.innerHTML = html;

    // Add click handlers
    document.querySelectorAll('.trig-list-item').forEach(item => {
        item.addEventListener('click', () => {
            const symbol = item.dataset.symbol;
            state.currentSymbol = symbol;
            renderSymbolList();
            renderDetail(symbol);
        });
    });

    // Update pagination
    const maxPage = Math.ceil(state.symbols.length / state.pageSize);
    if (state.symbols.length > state.pageSize) {
        DOM.pagination.style.display = 'flex';
        const startNum = start + 1;
        const endNum = Math.min(end, state.symbols.length);
        DOM.pageInfo.textContent = `${startNum}–${endNum} of ${state.symbols.length}`;
        DOM.prevBtn.disabled = state.currentPage === 0;
        DOM.nextBtn.disabled = state.currentPage >= maxPage - 1;
    } else {
        DOM.pagination.style.display = 'none';
    }
}

function renderDetail(symbol) {
    const rules = getFilteredRules(symbol);

    if (rules.length === 0) {
        DOM.trigDetail.innerHTML = `
            <div class="trig-detail-empty">
                No rules match the current filters for ${symbol}
            </div>
        `;
        return;
    }

    // Sort triggered first, then by score descending
    rules.sort((a, b) => {
        if (a.triggered !== b.triggered) {
            return b.triggered ? 1 : -1;
        }
        return b.score - a.score;
    });

    const triggeredCount = rules.filter(r => r.triggered).length;
    const totalScore = rules.reduce((sum, r) => sum + r.score, 0);

    const html = `
        <div class="trig-symbol-header">${symbol}</div>
        <div style="font-size: 12px; color: var(--text-2); margin-bottom: 16px;">
            ${triggeredCount} of ${rules.length} rules triggered | Total Score: <strong>${totalScore}</strong>
        </div>
        <div class="trig-rules-list">
            ${rules.map(rule => {
                const status = rule.triggered ? 'triggered' : 'not-triggered';
                const badge = rule.triggered ? '✓ TRIGGERED' : '✗ NO';
                return `
                    <div class="trig-rule-row ${status}">
                        <div class="trig-rule-code">
                            ${rule.composite_rule_code}
                            <span style="float: right; font-weight: normal; font-size: 12px;">${badge}</span>
                        </div>
                        <div class="trig-rule-score">
                            <span>Atomic Rules Hit: ${rule.n_atomic_hit}</span>
                            <span class="trig-score-value">Score: ${rule.score}</span>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;

    DOM.trigDetail.innerHTML = html;
}

function showStatus(message, type) {
    DOM.statusBar.textContent = message;
    DOM.statusBar.className = `status-bar ${type}`;

    if (type === 'success') {
        setTimeout(() => {
            DOM.statusBar.className = 'status-bar';
        }, 3000);
    }
}
