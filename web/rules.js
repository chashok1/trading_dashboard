const state = {
    atomicRules: [],
    compositeRules: [],
    currentTab: 'atomic',
    editingRule: null,
    editingType: null,
    allSymbols: [],
    selectedSymbol: null,
    selectedStockData: null,
    selectedDate: null,
};

const DOM = {
    atomicTableBody: document.getElementById('atomicTableBody'),
    compositeTableBody: document.getElementById('compositeTableBody'),
    editModal: document.getElementById('editModal'),
    modalTitle: document.getElementById('modalTitle'),
    atomicSection: document.getElementById('atomicSection'),
    compositeSection: document.getElementById('compositeSection'),
    searchInput: document.getElementById('searchInput'),
    categoryFilter: document.getElementById('categoryFilter'),
    symbolPicker: document.getElementById('symbolPicker'),
    symbolSuggestions: document.getElementById('symbolSuggestions'),
    datePicker: document.getElementById('datePicker'),
    atomicSymbolHeader: document.getElementById('atomicSymbolHeader'),
    atomicMaDataHeader: document.getElementById('atomicMaDataHeader'),
    compositeSymbolHeader: document.getElementById('compositeSymbolHeader'),
};

document.addEventListener('DOMContentLoaded', async () => {
    await loadDates();
    await loadAtomicRules();
    await loadCompositeRules();
    await loadSymbols();

    // Restore last entered symbol from localStorage, default to AAPL
    const savedSymbol = localStorage.getItem('rulesPage_lastSymbol') || 'AAPL';
    DOM.symbolPicker.value = savedSymbol;
    state.selectedSymbol = savedSymbol;

    // Auto-execute View for default symbol
    setTimeout(async () => {
        await viewSymbolData();
    }, 500);

    DOM.searchInput.addEventListener('input', filterRules);
    DOM.categoryFilter.addEventListener('change', filterRules);
    DOM.symbolPicker.addEventListener('input', handleSymbolPickerInput);
    DOM.symbolPicker.addEventListener('blur', () => setTimeout(() => DOM.symbolSuggestions.style.display = 'none', 200));
    DOM.datePicker.addEventListener('change', async (e) => {
        state.selectedDate = e.target.value;
        if (state.selectedSymbol) {
            await loadSelectedStock();
            renderTables();
        }
    });
});

async function loadDates() {
    try {
        const dates = await fetch('/api/dates').then(r => r.json());
        if (dates.length > 0) {
            DOM.datePicker.innerHTML = '';
            dates.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d;
                opt.textContent = d;
                DOM.datePicker.appendChild(opt);
            });
            DOM.datePicker.value = dates[0];
            state.selectedDate = dates[0];
        }
    } catch (e) {
        console.error('Failed to load dates:', e);
    }
}

async function loadSymbols() {
    try {
        const data = await fetch(`/api/stks?date=${state.selectedDate}&limit=10000`).then(r => r.json());
        state.allSymbols = data.map(d => d.tos_symbol).sort();
    } catch (e) {
        console.error('Failed to load symbols:', e);
    }
}

function handleSymbolPickerInput(e) {
    const input = e.target.value.toUpperCase();
    if (!input) {
        DOM.symbolSuggestions.style.display = 'none';
        return;
    }

    const matches = state.allSymbols.filter(s => s.includes(input)).slice(0, 10);
    if (matches.length === 0) {
        DOM.symbolSuggestions.style.display = 'none';
        return;
    }

    DOM.symbolSuggestions.innerHTML = matches.map(sym => `
        <div style="padding: 8px 12px; border-bottom: 1px solid var(--border); cursor: pointer; hover: background: #f5f5f5;" onclick="selectSymbol('${sym}')">${sym}</div>
    `).join('');
    DOM.symbolSuggestions.style.display = 'block';
}

function selectSymbol(symbol) {
    state.selectedSymbol = symbol;
    DOM.symbolPicker.value = symbol;
    DOM.symbolSuggestions.style.display = 'none';
    localStorage.setItem('rulesPage_lastSymbol', symbol);
}

async function viewSymbolData() {
    const symbol = DOM.symbolPicker.value.toUpperCase().trim();
    if (!symbol) {
        alert('Please enter a stock symbol');
        return;
    }

    state.selectedSymbol = symbol;
    const date = state.selectedDate || DOM.datePicker.value;

    if (!date) {
        alert('No date selected. Please refresh the page.');
        return;
    }

    state.selectedDate = date;

    try {
        const data = await fetch(`/api/stks?date=${date}&limit=5000`).then(r => r.json());
        const stockData = data.find(d => d.tos_symbol === symbol);

        if (!stockData) {
            alert(`Stock ${symbol} not found for date ${date}`);
            return;
        }

        state.selectedStockData = stockData;
        DOM.atomicMaDataHeader.style.display = '';
        DOM.atomicSymbolHeader.style.display = '';
        DOM.compositeSymbolHeader.style.display = '';
        renderTables();
    } catch (e) {
        console.error('Failed to load stock data:', e);
        alert('Error loading stock data');
    }
}

async function loadSelectedStock() {
    try {
        const data = await fetch(`/api/stks?date=${state.selectedDate}&limit=10000`).then(r => r.json());
        state.selectedStockData = data.find(d => d.tos_symbol === state.selectedSymbol);
    } catch (e) {
        console.error('Failed to load stock data:', e);
    }
}

function renderTables() {
    renderAtomicTable();
    renderCompositeTable();
    renderMaColumns();
}

async function loadAtomicRules() {
    try {
        const rules = await fetch('/api/rules/atomic?limit=1000').then(r => r.json());
        state.atomicRules = rules;
        renderAtomicTable();
    } catch (e) {
        console.error('Failed to load atomic rules:', e);
        DOM.atomicTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-3);">Error loading rules</td></tr>';
    }
}

async function loadCompositeRules() {
    try {
        const rules = await fetch('/api/rules/composite?limit=1000').then(r => r.json());
        state.compositeRules = rules;
        renderCompositeTable();
    } catch (e) {
        console.error('Failed to load composite rules:', e);
        DOM.compositeTableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-3);">Error loading rules</td></tr>';
    }
}

function getMaDataValue(rule, stockData) {
    if (!rule || !stockData) return '—';

    // Extract column name from ma_column_name (e.g., "drv_ma.a_bb_streak" -> "a_bb_streak")
    let columnName = rule.ma_column_name;
    if (columnName && columnName.includes('.')) {
        columnName = columnName.split('.')[1];
    }

    if (!columnName) return '—';

    // Get the value from stock data
    const value = stockData[columnName];
    if (value === null || value === undefined) return '—';

    // Format the value
    const numValue = parseFloat(value);
    if (isNaN(numValue)) {
        return value.toString();
    }

    // Return with 2 decimal places
    return numValue.toFixed(2);
}

function getRuleWeight(rule, stockData) {
    if (!rule || !stockData) return '—';

    // Look for this rule in triggered_atomic_ids
    if (stockData.triggered_atomic_ids && Array.isArray(stockData.triggered_atomic_ids)) {
        const triggered = stockData.triggered_atomic_ids.find(t => t.rule_id === rule.atomic_rule_id);
        if (triggered && triggered.weight !== null && triggered.weight !== undefined) {
            return Math.round(triggered.weight);
        }
    }

    // If not triggered, return dash
    return '—';
}

function renderAtomicTable() {
    const filtered = filterBySearch(state.atomicRules);
    // Only show rules with From/To thresholds in this tab
    const thresholdRules = filtered.filter(r => r.brkeout_from !== null && r.brkeout_from !== undefined);

    if (thresholdRules.length === 0) {
        DOM.atomicTableBody.innerHTML = '<tr><td colspan="13" style="text-align: center; padding: 20px; color: var(--text-3);">No threshold-based atomic rules (rules with From/To values)</td></tr>';
        return;
    }

    DOM.atomicTableBody.innerHTML = thresholdRules.map(r => {
        const formatNum = (val) => {
            const num = parseFloat(val);
            return !isNaN(num) ? num.toFixed(2) : '—';
        };
        const formatInt = (val) => {
            const num = parseInt(val);
            return !isNaN(num) ? num : '—';
        };

        let maDataValue = '—';
        let symbolWeight = '—';
        if (state.selectedStockData) {
            maDataValue = getMaDataValue(r, state.selectedStockData);
            symbolWeight = getRuleWeight(r, state.selectedStockData);
        }

        return `
        <tr>
            <td><strong>${r.atomic_rule_id || r.rule_id || '—'}</strong></td>
            <td>${r.rule_name || '—'}</td>
            <td>${r.category || '—'}</td>
            <td style="font-size: 12px; color: var(--text-2); font-family: monospace;">${r.ma_column_name || '—'}</td>
            <td style="text-align: center;">${formatNum(r.brkeout_from)}</td>
            <td style="text-align: center;">${formatNum(r.brkeout_to)}</td>
            <td style="text-align: center;">${formatInt(r.wt_below)}</td>
            <td style="text-align: center;">${formatInt(r.wt_between)}</td>
            <td style="text-align: center;">${formatInt(r.wt_above)}</td>
            <td><span class="badge badge-${r.scoring_mode || 'jump'}">${r.scoring_mode || 'jump'}</span></td>
            <td>
                <div class="actions-cell">
                    <button class="btn-sm btn-edit" onclick="viewRule('atomic', '${r.atomic_rule_id || r.rule_id}')">View</button>
                    <button class="btn-sm btn-edit" onclick="editRule('atomic', '${r.atomic_rule_id || r.rule_id}')">Edit</button>
                    <button class="btn-sm btn-deprecate" onclick="deprecateRule('${r.atomic_rule_id || r.rule_id}', 'atomic')">Deprecate</button>
                </div>
            </td>
            <td style="text-align: center;">${maDataValue}</td>
            <td style="text-align: center; font-weight: bold;">${symbolWeight}</td>
        </tr>
    `;
    }).join('');
}

function renderCompositeTable() {
    const filtered = filterBySearch(state.compositeRules);
    if (filtered.length === 0) {
        DOM.compositeTableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px; color: var(--text-3);">No composite rules</td></tr>';
        return;
    }

    const formatNum = (val) => {
        const num = parseFloat(val);
        return !isNaN(num) ? num.toFixed(2) : '—';
    };

    DOM.compositeTableBody.innerHTML = filtered.map(r => {
        let symbolScore = '—';
        if (state.selectedStockData && state.selectedStockData.triggered_composite_ids) {
            const triggered = state.selectedStockData.triggered_composite_ids.find(t => t.rule_id === r.composite_rule_code || t.rule_id === r.rule_id);
            if (triggered) {
                symbolScore = formatNum(triggered.score);
            }
        }

        return `
        <tr>
            <td><strong>${r.composite_rule_code || r.rule_id || '—'}</strong></td>
            <td>${r.category || '—'}</td>
            <td>${r.intent_text ? r.intent_text.substring(0, 40) + '...' : '—'}</td>
            <td>${r.precondition_expr ? r.precondition_expr.substring(0, 30) + '...' : '—'}</td>
            <td>
                <div class="actions-cell">
                    <button class="btn-sm btn-edit" onclick="viewRule('composite', '${r.composite_rule_code || r.rule_id}')">View</button>
                    <button class="btn-sm btn-edit" onclick="editRule('composite', '${r.composite_rule_code || r.rule_id}')">Edit</button>
                    <button class="btn-sm btn-deprecate" onclick="deprecateRule('${r.composite_rule_code || r.rule_id}', 'composite')">Deprecate</button>
                </div>
            </td>
            <td style="text-align: center; font-weight: bold;">${symbolScore}</td>
        </tr>
    `;
    }).join('');
}

function renderMaColumns() {
    const content = document.getElementById('maColumnsContent');

    const formatNum = (val) => {
        if (val === null || val === undefined) return '—';
        const num = parseFloat(val);
        return !isNaN(num) ? num.toFixed(4) : '—';
    };

    // Direct column references (atomic rules without From/To thresholds)
    const directRules = state.atomicRules.filter(r => !r.brkeout_from && r.brkeout_from === null);

    // Show MA column reference rules (no From/To thresholds)
    if (directRules.length === 0) {
        content.innerHTML = '<p style="color: var(--text-3);">No atomic rules with direct column references</p>';
        return;
    }

    let html = `<div class="scrollable-table-container">
        <table class="rules-table">
            <thead><tr><th>Rule ID</th><th>Rule Name</th><th>MA Column</th><th>Category</th>`;

    // Add Value column only if stock data is selected
    if (state.selectedStockData) {
        html += `<th>Value</th>`;
    }

    html += `</tr></thead><tbody>`;

    directRules.forEach(r => {
        html += `<tr>
            <td><strong>${r.atomic_rule_id || r.rule_id || '—'}</strong></td>
            <td>${r.rule_name || '—'}</td>
            <td style="font-size: 12px; color: var(--text-2); font-family: monospace;">${r.ma_column_name || '—'}</td>
            <td>${r.category || '—'}</td>`;

        if (state.selectedStockData) {
            const columnKey = getMaColumnKey(r.ma_column_name);
            const val = columnKey ? state.selectedStockData[columnKey] : null;
            html += `<td style="text-align: center; font-weight: bold;">${formatNum(val)}</td>`;
        }

        html += `</tr>`;
    });

    html += `</tbody></table></div>`;

    content.innerHTML = html;
}

function getMaColumnKey(maColumnName) {
    // Map MA column names to state keys
    const mapping = {
        'last_price': 'last_price',
        'a_trend_value': 'a_trend_value',
        'a_trade_value': 'a_trade_value',
        'rr_outlook': 'rr_outlook',
        'rr_brr': 'rr_brr',
        'call_outlook': 'call_outlook',
        'etf_outlook': 'etf_outlook',
        'ii_outlook': 'ii_outlook',
        'ssh_signal_sign': 'ssh_signal_sign',
        'iv_percentile': 'iv_percentile',
        'rsi': 'rsi',
        'pct_brr': 'pct_brr',
        // 41 derived indicator columns
        'macdh_direction': 'macdh_direction',
        'macd_direction': 'macd_direction',
        'bb_direction': 'bb_direction',
        'bbthresh_crossover': 'bbthresh_crossover',
        'trade_cross_over': 'trade_cross_over',
        'not_trade_rule': 'not_trade_rule',
        'trend_cross_over': 'trend_cross_over',
        'not_trend_rule': 'not_trend_rule',
        'trend_trade_dep_rule': 'trend_trade_dep_rule',
        'trade_trend_relation': 'trade_trend_relation',
        'not_trade_trend_relation': 'not_trade_trend_relation',
        'brr_pct_dir': 'brr_pct_dir',
        'trend_below_trr': 'trend_below_trr',
        'lrr_above_trade': 'lrr_above_trade',
        'ivrule': 'ivrule',
        'three_m_long': 'three_m_long',
        'not_perf1d_sd_rule': 'not_perf1d_sd_rule',
        'perf_sd_rule': 'perf_sd_rule',
        'not_perf_sd_rule': 'not_perf_sd_rule',
        'not_perf3d_rule': 'not_perf3d_rule',
        'bb_bull_rule': 'bb_bull_rule',
        'bb_bull_puts': 'bb_bull_puts',
        'macd_and_h_rule': 'macd_and_h_rule',
        'macd_and_h_rule_puts': 'macd_and_h_rule_puts',
        'not_overbought': 'not_overbought',
        'not_outlook_3wk': 'not_outlook_3wk',
        'not_outlook_3wk_days': 'not_outlook_3wk_days',
        'bull_rule': 'bull_rule',
        'not_bull_rule': 'not_bull_rule',
        'perfourbull_rule': 'perfourbull_rule',
        'not_perfourbull_rule': 'not_perfourbull_rule',
        'dma_50_crossover': 'dma_50_crossover',
        'dma_200_crossover': 'dma_200_crossover',
        'trade_close_to_brr': 'trade_close_to_brr',
        'trade_close_to_trr': 'trade_close_to_trr',
        'up_resistance': 'up_resistance',
        'down_resistance': 'down_resistance',
        'vs_lt_outlook_rule': 'vs_lt_outlook_rule',
        'short_term_outlook_bullish': 'short_term_outlook_bullish',
        'short_term_outlook_bearish': 'short_term_outlook_bearish',
        'overbought': 'overbought',
    };

    if (!maColumnName) return null;

    // Handle both "column_name" and "drv_ma.column_name" formats
    const colName = maColumnName.includes('.') ? maColumnName.split('.')[1] : maColumnName;
    return mapping[colName.toLowerCase()] || null;
}

function filterBySearch(rules) {
    const search = DOM.searchInput.value.toLowerCase();
    const category = DOM.categoryFilter.value;

    return rules.filter(r => {
        const matchSearch = !search ||
            (r.atomic_rule_id && r.atomic_rule_id.toString().toLowerCase().includes(search)) ||
            (r.composite_rule_code && r.composite_rule_code.toLowerCase().includes(search)) ||
            (r.rule_id && r.rule_id.toLowerCase().includes(search)) ||
            (r.rule_name && r.rule_name.toLowerCase().includes(search)) ||
            (r.intent_text && r.intent_text.toLowerCase().includes(search));

        const matchCategory = !category || r.category === category;

        return matchSearch && matchCategory;
    });
}

function filterRules() {
    if (state.currentTab === 'atomic') {
        renderAtomicTable();
    } else {
        renderCompositeTable();
    }
}

function switchTab(tab) {
    state.currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById(tab).classList.add('active');

    // Render MA columns when switching to that tab
    if (tab === 'macolumns') {
        renderMaColumns();
    }
}

function openNewModal(type) {
    state.editingRule = null;
    state.editingType = type;
    DOM.modalTitle.textContent = `Create ${type === 'atomic' ? 'Atomic' : 'Composite'} Rule`;

    document.getElementById('ruleId').value = '';
    document.getElementById('ruleCategory').value = 'Mixed';
    document.getElementById('ruleIntent').value = '';

    if (type === 'atomic') {
        DOM.atomicSection.style.display = 'block';
        DOM.compositeSection.style.display = 'none';
        document.getElementById('scoringMode').value = 'jump';
        document.getElementById('breakoutFrom').value = '';
        document.getElementById('breakoutTo').value = '';
        document.getElementById('wtBelow').value = '';
        document.getElementById('wtBetween').value = '';
        document.getElementById('wtAbove').value = '';
    } else {
        DOM.atomicSection.style.display = 'none';
        DOM.compositeSection.style.display = 'block';
        document.getElementById('precondition').value = '';
    }

    DOM.editModal.classList.add('active');
}

async function viewRule(type, ruleId) {
    try {
        const endpoint = type === 'atomic' ? `/api/rules/atomic/${ruleId}` : `/api/rules/composite/${ruleId}`;
        const rule = await fetch(endpoint).then(r => r.json());

        DOM.modalTitle.textContent = `View ${type === 'atomic' ? 'Atomic' : 'Composite'} Rule`;
        populateRuleForm(type, rule, true);
        DOM.editModal.classList.add('active');
    } catch (e) {
        alert(`Failed to load rule: ${e.message}`);
    }
}

async function editRule(type, ruleId) {
    try {
        const endpoint = type === 'atomic' ? `/api/rules/atomic/${ruleId}` : `/api/rules/composite/${ruleId}`;
        const rule = await fetch(endpoint).then(r => r.json());

        state.editingRule = rule;
        state.editingType = type;
        DOM.modalTitle.textContent = `Edit ${type === 'atomic' ? 'Atomic' : 'Composite'} Rule`;
        populateRuleForm(type, rule, false);
        DOM.editModal.classList.add('active');
    } catch (e) {
        alert(`Failed to load rule: ${e.message}`);
    }
}

function populateRuleForm(type, rule, isReadOnly) {
    const ruleId = rule.atomic_rule_id || rule.composite_rule_code || rule.rule_id;
    const idField = document.getElementById('ruleId');
    const categoryField = document.getElementById('ruleCategory');
    const intentField = document.getElementById('ruleIntent');

    idField.value = ruleId;
    categoryField.value = rule.category || 'Mixed';
    intentField.value = rule.intent_text || '';

    idField.readOnly = true;
    categoryField.readOnly = isReadOnly;
    intentField.readOnly = isReadOnly;

    if (type === 'atomic') {
        DOM.atomicSection.style.display = 'block';
        DOM.compositeSection.style.display = 'none';
        const ruleNameField = document.getElementById('ruleName');
        const maColumnNameField = document.getElementById('maColumnName');
        const scoringModeField = document.getElementById('scoringMode');
        const breakoutFromField = document.getElementById('breakoutFrom');
        const breakoutToField = document.getElementById('breakoutTo');
        const wtBelowField = document.getElementById('wtBelow');
        const wtBetweenField = document.getElementById('wtBetween');
        const wtAboveField = document.getElementById('wtAbove');

        ruleNameField.value = rule.rule_name || '';
        maColumnNameField.value = rule.ma_column_name || '';
        scoringModeField.value = rule.scoring_mode || 'jump';
        breakoutFromField.value = rule.brkeout_from || '';
        breakoutToField.value = rule.brkeout_to || '';
        wtBelowField.value = rule.wt_below || '';
        wtBetweenField.value = rule.wt_between || '';
        wtAboveField.value = rule.wt_above || '';
        document.getElementById('negMultiplier').value = rule.neg_multiplier ?? 1.0;

        ruleNameField.readOnly = isReadOnly;
        maColumnNameField.readOnly = true; // Always read-only
        scoringModeField.readOnly = isReadOnly;
        breakoutFromField.readOnly = isReadOnly;
        breakoutToField.readOnly = isReadOnly;
        wtBelowField.readOnly = isReadOnly;
        wtBetweenField.readOnly = isReadOnly;
        wtAboveField.readOnly = isReadOnly;
        document.getElementById('negMultiplier').readOnly = isReadOnly;
    } else {
        DOM.atomicSection.style.display = 'none';
        DOM.compositeSection.style.display = 'block';
        const preconditionField = document.getElementById('precondition');
        preconditionField.value = rule.precondition_expr || '';
        preconditionField.readOnly = isReadOnly;

        // Load atomic rules for this composite rule
        loadCompositeAtomicRules(rule.rule_id || rule.composite_rule_code);
    }

    const saveBtn = document.querySelector('.btn-save');
    saveBtn.style.display = isReadOnly ? 'none' : 'block';
}

async function loadCompositeAtomicRules(compositeRuleId) {
    try {
        const atomics = await fetch(`/api/rules/composite/${compositeRuleId}/atomics`).then(r => r.json());
        const tbody = document.getElementById('compositeAtomicsBody');

        if (atomics.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 12px; color: var(--text-3);">No atomic rules in this composite rule</td></tr>';
            return;
        }

        tbody.innerHTML = atomics.map(a => `
            <tr>
                <td style="padding: 7px 10px; border-bottom: 1px solid #f4f4f2;">${a.atomic_rule_id}</td>
                <td style="padding: 7px 10px; border-bottom: 1px solid #f4f4f2;">${a.rule_name || '—'}</td>
                <td style="padding: 7px 10px; border-bottom: 1px solid #f4f4f2;">${a.category || '—'}</td>
                <td style="padding: 7px 10px; border-bottom: 1px solid #f4f4f2;"><span class="badge badge-${a.scoring_mode || 'jump'}">${a.scoring_mode || 'jump'}</span></td>
                <td style="padding: 7px 10px; border-bottom: 1px solid #f4f4f2; text-align: center;">${a.weight_override !== null ? a.weight_override : '—'}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load atomic rules:', e);
        document.getElementById('compositeAtomicsBody').innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 12px; color: var(--bear);">Error loading atomic rules</td></tr>';
    }
}

function closeModal() {
    DOM.editModal.classList.remove('active');
    state.editingRule = null;
}

async function saveRule() {
    const ruleId = document.getElementById('ruleId').value.trim();
    const category = document.getElementById('ruleCategory').value;
    const intent = document.getElementById('ruleIntent').value;

    if (!ruleId && !state.editingRule) {
        alert('Rule ID is required');
        return;
    }

    if (state.editingType === 'atomic') {
        const data = {
            rule_id: ruleId,
            category: category,
            intent_text: intent,
            rule_name: document.getElementById('ruleName').value || null,
            scoring_mode: document.getElementById('scoringMode').value,
            brkeout_from: parseFloat(document.getElementById('breakoutFrom').value) || null,
            brkeout_to: parseFloat(document.getElementById('breakoutTo').value) || null,
            wt_below: parseFloat(document.getElementById('wtBelow').value) || null,
            wt_between: parseFloat(document.getElementById('wtBetween').value) || null,
            wt_above: parseFloat(document.getElementById('wtAbove').value) || null,
            neg_multiplier: parseFloat(document.getElementById('negMultiplier').value) || 1.0,
        };

        const method = state.editingRule ? 'PUT' : 'POST';
        const endpoint = state.editingRule ? `/api/rules/atomic/${ruleId}` : '/api/rules/atomic';
        try {
            const response = await fetch(endpoint, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state.editingRule ? {
                    category: data.category,
                    intent_text: data.intent_text,
                    rule_name: data.rule_name,
                    scoring_mode: data.scoring_mode,
                    brkeout_from: data.brkeout_from,
                    brkeout_to: data.brkeout_to,
                    wt_below: data.wt_below,
                    wt_between: data.wt_between,
                    wt_above: data.wt_above,
                    neg_multiplier: data.neg_multiplier,
                } : data),
            });

            if (response.ok) {
                alert(`Atomic rule ${state.editingRule ? 'updated' : 'created'} successfully`);
                await loadAtomicRules();
                closeModal();
            } else {
                const errData = await response.json();
                alert(`Failed to save rule: ${errData.detail || response.statusText}`);
            }
        } catch (e) {
            console.error('Error:', e);
            alert('Error saving rule');
        }
    } else {
        const data = {
            rule_code: ruleId,
            category: category,
            intent_text: intent,
            precondition_expr: document.getElementById('precondition').value,
        };

        const method = state.editingRule ? 'PUT' : 'POST';
        const endpoint = state.editingRule ? `/api/rules/composite/${ruleId}` : '/api/rules/composite';
        try {
            const response = await fetch(endpoint, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state.editingRule ? {
                    category: data.category,
                    intent_text: data.intent_text,
                    precondition_expr: data.precondition_expr,
                } : data),
            });

            if (response.ok) {
                alert(`Composite rule ${state.editingRule ? 'updated' : 'created'} successfully`);
                await loadCompositeRules();
                closeModal();
            } else {
                const errData = await response.json();
                alert(`Failed to save rule: ${errData.detail || response.statusText}`);
            }
        } catch (e) {
            console.error('Error:', e);
            alert('Error saving rule');
        }
    }
}

async function deprecateRule(ruleId, type) {
    if (!confirm(`Deprecate rule ${ruleId}? This cannot be undone.`)) return;

    try {
        const endpoint = type === 'atomic' ? '/api/rules/atomic' : '/api/rules/composite';
        const response = await fetch(`${endpoint}/${ruleId}`, {
            method: 'DELETE',
        });

        if (response.ok) {
            alert(`Rule ${ruleId} deprecated successfully`);
            if (type === 'atomic') {
                await loadAtomicRules();
            } else {
                await loadCompositeRules();
            }
        } else {
            alert('Failed to deprecate rule (endpoint not implemented)');
        }
    } catch (e) {
        console.error('Error:', e);
        alert('Error deprecating rule');
    }
}

window.switchTab = switchTab;
window.openNewModal = openNewModal;
window.viewRule = viewRule;
window.editRule = editRule;
window.closeModal = closeModal;
window.saveRule = saveRule;
window.deprecateRule = deprecateRule;
window.filterRules = filterRules;
window.selectSymbol = selectSymbol;
window.viewSymbolData = viewSymbolData;
