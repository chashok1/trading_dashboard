/**
 * Action Cockpit — View and log trading actions
 */

const state = {
    selectedDate: null,
    actions: [],
    selectedSymbol: null,
    sectors: [],
    allSymbols: [],
};

// TOS symbol → TradingView exchange:symbol
const TV_MAP = {
    'SPX': 'SP:SPX',   '$SPX': 'SP:SPX',
    '$COMP': 'NASDAQ:COMP', 'COMP': 'NASDAQ:COMP', 'COMPQ': 'NASDAQ:COMP',
    '$DJI': 'DJ:DJI',  'DJI': 'DJ:DJI', 'INDU': 'DJ:DJI',
    'RUT': 'TVC:RUT',
    'VIX': 'CBOE:VIX',  'VXN': 'CBOE:VXN', 'VXD': 'CBOE:VXD',
    'RVX': 'TVC:RVX',   'OVX': 'CBOE:OVX', 'GVZ': 'CBOE:GVZ',
    'MOVE': 'TVC:MOVE', 'DXY': 'TVC:DXY',  '$DXY': 'TVC:DXY',
    '/CL': 'NYMEX:CL1!', '/GC': 'COMEX:GC1!', '/ES': 'CME:ES1!',
    '/NQ': 'CME:NQ1!',   '/RTY': 'CME:RTY1!',
};

function toTvSymbol(sym) {
    if (!sym) return 'AMEX:SPY';
    if (TV_MAP[sym]) return TV_MAP[sym];
    if (sym.startsWith('/')) return sym.slice(1) + '1!';
    if (sym.startsWith('$')) return sym.slice(1);
    return sym;
}

let _tvSeq = 0;

function renderTvChart(symbol) {
    const container = document.getElementById('tv_chart_container');
    const label = document.getElementById('chartSymbolLabel');
    const ticker = document.getElementById('chartSymbolTicker');
    if (label) label.textContent = 'Chart';
    if (ticker) ticker.textContent = symbol || '';

    container.innerHTML = '';
    const id = 'tv_w' + (++_tvSeq);
    const div = document.createElement('div');
    div.id = id;
    div.style.height = '100%';
    container.appendChild(div);

    /* global TradingView */
    new TradingView.widget({
        autosize: true,
        symbol: toTvSymbol(symbol),
        interval: 'D',
        timezone: 'America/New_York',
        theme: 'light',
        style: '1',
        locale: 'en',
        enable_publishing: false,
        allow_symbol_change: true,
        save_image: false,
        container_id: id,
    });
}

const DOM = {
    datePicker: document.getElementById('datePicker'),
    actionFilter: document.getElementById('actionFilter'),
    sectorFilter: document.getElementById('sectorFilter'),
    symbolSearch: document.getElementById('symbolSearch'),
    actionsTableBody: document.getElementById('actionsTableBody'),
    detailDrawer: document.getElementById('detailDrawer'),
    drawerSymbol: document.getElementById('drawerSymbol'),
    drawerPrice: document.getElementById('drawerPrice'),
    atomicRulesList: document.getElementById('atomicRulesList'),
    compositeRulesList: document.getElementById('compositeRulesList'),
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadDates();
    await loadSectors();
});

DOM.datePicker.addEventListener('change', async (e) => {
    state.selectedDate = e.target.value;
    await loadActions(state.selectedDate);
});

DOM.actionFilter.addEventListener('change', filterActions);
DOM.sectorFilter.addEventListener('change', filterActions);
DOM.symbolSearch.addEventListener('input', filterActions);

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
            await loadActions(dates[0]);
        }
    } catch (e) {
        console.error('Failed to load dates:', e);
    }
}

async function loadSectors() {
    try {
        const sectors = await fetch('/api/sectors').then(r => r.json());
        state.sectors = sectors;
        sectors.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            DOM.sectorFilter.appendChild(opt);
        });
    } catch (e) {
        console.error('Failed to load sectors:', e);
    }
}

async function loadActions(date) {
    try {
        const data = await fetch(`/api/stks?date=${date}&limit=5000`).then(r => r.json());
        state.actions = data;
        renderTable();
    } catch (e) {
        console.error('Failed to load actions:', e);
    }
}

function filterActions() {
    renderTable();
}

function renderTable() {
    const actionFilter = DOM.actionFilter.value;
    const sectorFilter = DOM.sectorFilter.value;
    const symbolSearch = DOM.symbolSearch.value.toLowerCase();

    const filtered = state.actions.filter(a => {
        const matchAction = !actionFilter || (a.composite_label && a.composite_label.includes(actionFilter));
        const matchSector = !sectorFilter || a.sector === sectorFilter;
        const matchSymbol = !symbolSearch || a.tos_symbol.toLowerCase().includes(symbolSearch);
        return matchAction && matchSector && matchSymbol;
    });

    if (filtered.length === 0) {
        DOM.actionsTableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: var(--text-3);">No actions match filters</td></tr>';
        return;
    }

    DOM.actionsTableBody.innerHTML = filtered.map(a => `
        <tr onclick="openDrawer('${a.tos_symbol}')">
            <td>${typeof yahooLink === 'function' ? yahooLink(a.tos_symbol) : ''}${a.tos_symbol}</td>
            <td>${a.sector || a.asset_class || '—'}</td>
            <td>$${a.last_price ? a.last_price.toFixed(2) : '—'}</td>
            <td><span class="action-code ${a.composite_label || 'N/A'}">${a.composite_label || '—'}</span></td>
            <td>${a.composite_outlook ? a.composite_outlook.toFixed(2) : '—'}</td>
        </tr>
    `).join('');
}

function openDrawer(symbol) {
    state.selectedSymbol = symbol;
    const action = state.actions.find(a => a.tos_symbol === symbol);

    if (!action) return;

    renderTvChart(symbol);

    DOM.drawerSymbol.textContent = symbol;
    DOM.drawerPrice.textContent = `$${action.last_price?.toFixed(2) || '—'}`;

    // Render triggered atomic rules
    if (action.triggered_atomic_ids && action.triggered_atomic_ids.length > 0) {
        DOM.atomicRulesList.innerHTML = action.triggered_atomic_ids.map(r => `
            <li>
                <div class="rule-header">Rule ${r.rule_id}</div>
                <div class="rule-detail">Weight: ${r.weight.toFixed(2)} | Value: ${r.value?.toFixed(2) || 'N/A'}</div>
            </li>
        `).join('');
    } else {
        DOM.atomicRulesList.innerHTML = '<li><div class="rule-detail">No triggered atomic rules</div></li>';
    }

    // Render triggered composite rules
    if (action.triggered_composite_ids && action.triggered_composite_ids.length > 0) {
        DOM.compositeRulesList.innerHTML = action.triggered_composite_ids.map(r => `
            <li>
                <div class="rule-header">${r.rule_id}</div>
                <div class="rule-detail">Score: ${r.score.toFixed(2)}</div>
            </li>
        `).join('');
    } else {
        DOM.compositeRulesList.innerHTML = '<li><div class="rule-detail">No triggered composite rules</div></li>';
    }

    DOM.detailDrawer.classList.add('active');
}

function closeDrawer() {
    DOM.detailDrawer.classList.remove('active');
    state.selectedSymbol = null;
}

async function logAction(type) {
    if (!state.selectedSymbol || !state.selectedDate) return;

    const actionCode = type === 'took' ? 'ACTED' : 'SKIP';

    try {
        const response = await fetch('/api/actions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                as_of_date: state.selectedDate,
                symbol: state.selectedSymbol,
                action_code: actionCode,
                notes: '',
            }),
        }).then(r => r.json());

        if (response.ok) {
            closeDrawer();
            alert(`Action logged for ${state.selectedSymbol}`);
        }
    } catch (e) {
        console.error('Failed to log action:', e);
        alert('Error logging action');
    }
}

// Expose closeDrawer for onclick handlers
window.closeDrawer = closeDrawer;
window.openDrawer = openDrawer;
window.logAction = logAction;
