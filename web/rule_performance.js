/**
 * Rule Performance — direction-adjusted rule scorecard (Phase 4).
 * Reads /api/rules/scorecard (v_rule_scorecard). edge_20d > 0 = the rule's
 * signal was right on average. No wall-clock window — covers all loaded history.
 */

const state = {
    rules: [],
    sortBy: 'edge_20d',
    sortDir: 'desc',
};

const atomicState = {
    rules: [],
    sortBy: 'avg_fwd_20d',
    sortDir: 'desc',
};

const DOM = {
    perfTableBody: document.getElementById('perfTableBody'),
    atomicTableBody: document.getElementById('atomicTableBody'),
};

document.addEventListener('DOMContentLoaded', () => {
    loadScorecard();
    loadMyActions();
    loadAtomicScorecard();
});

async function loadMyActions() {
    const body = document.getElementById('myActionsBody');
    const summ = document.getElementById('myActionsSummary');
    try {
        const data = await fetch('/api/rules/my-actions?limit=200').then(r => r.json());
        const recent = data.recent || [];
        const s = data.summary || {};
        if (s.n_actions) {
            const avg = s.avg_fwd_20d != null ? `${Number(s.avg_fwd_20d).toFixed(2)}%` : '—';
            summ.textContent = `${s.n_actions} actions · ${s.n_scored || 0} scored · avg 20d ${avg}`;
        } else {
            summ.textContent = '';
        }
        if (!recent.length) {
            body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:14px;color:var(--text-3);">'
                + 'No actions logged yet. Act on a recommendation in the Actionable screen — once 20 trading days pass, your result shows here.</td></tr>';
            return;
        }
        const num = v => (v === null || v === undefined) ? '—'
            : `<span class="${v >= 0 ? 'act-buy-strong' : 'act-sell-strong'}">${Number(v).toFixed(2)}%</span>`;
        body.innerHTML = recent.map(r => `
            <tr>
                <td style="font-size:11px;">${(r.acted_at || r.as_of_date || '').toString().slice(0,10)}</td>
                <td><strong>${r.tos_symbol || ''}</strong></td>
                <td title="${r.consolidated_action || ''}">${r.consolidated_action ? actionText(actionDisplay(r.consolidated_action)) : '—'}</td>
                <td>${r.user_action || '—'}</td>
                <td>${num(r.fwd_5d_pct)}</td>
                <td>${num(r.fwd_20d_pct)}</td>
            </tr>`).join('');
    } catch (e) {
        console.error('Failed to load my-actions:', e);
        body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#b91c1c;">Error loading actions</td></tr>';
    }
}

async function loadScorecard() {
    const minFires = document.getElementById('minFires')?.value ?? 30;
    DOM.perfTableBody.innerHTML =
        '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--text-3);">Loading scorecard…</td></tr>';
    try {
        const data = await fetch(`/api/rules/scorecard?min_fires=${minFires}&limit=1000`)
            .then(r => r.json());
        state.rules = Array.isArray(data) ? data : [];
        renderTable();
    } catch (e) {
        console.error('Failed to load scorecard:', e);
        DOM.perfTableBody.innerHTML =
            '<tr><td colspan="8" style="text-align:center;color:#b91c1c;">Error loading scorecard</td></tr>';
    }
}

function renderTable() {
    if (!state.rules.length) {
        DOM.perfTableBody.innerHTML =
            '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--text-3);">' +
            'No scorecard data. Run the outcome ETL: <code>python -m etl.compute_firing_outcomes --truncate</code></td></tr>';
        return;
    }

    const dir = state.sortDir === 'asc' ? 1 : -1;
    const rows = [...state.rules].sort((a, b) => {
        let va = a[state.sortBy], vb = b[state.sortBy];
        if (typeof va === 'string') return va.localeCompare(vb) * dir;
        return ((va ?? 0) - (vb ?? 0)) * dir;
    });

    const num = (v, d = 2) => (v === null || v === undefined) ? '—' : Number(v).toFixed(d);
    const edgeCls = v => v > 0.5 ? 'edge-pos' : v < -0.5 ? 'edge-neg' : 'edge-neu';

    DOM.perfTableBody.innerHTML = rows.map(r => {
        const span = (r.first_seen && r.last_seen)
            ? `${r.first_seen} → ${r.last_seen}` : '—';
        const dirCls  = r.direction === 'BUY' ? 'dir-buy' : 'dir-sell';
        const conf    = r.confidence || 'unproven';
        const unproven = conf === 'unproven';
        const rowStyle = unproven ? ' style="opacity:0.55;"' : '';
        const confBadge = conf === 'proven'
            ? `<span style="color:#15803d;font-weight:700;font-size:10px;"> ✓proven</span>`
            : conf === 'promising'
            ? `<span style="color:#92400e;font-size:10px;"> promising</span>`
            : `<span style="color:#94a3b8;font-size:10px;"> unproven</span>`;
        const ciLow  = r.edge_20d_ci_low  != null ? Number(r.edge_20d_ci_low).toFixed(2)  : '—';
        const ciHigh = r.edge_20d_ci_high != null ? Number(r.edge_20d_ci_high).toFixed(2) : '—';
        const ciStr  = (ciLow !== '—' && ciHigh !== '—') ? `[${ciLow}%, ${ciHigh}%]` : '—';
        return `
            <tr${rowStyle}>
                <td><strong>${r.rule_id}</strong>${confBadge}</td>
                <td class="${dirCls}">${r.direction || '—'}</td>
                <td>${r.n_fires ?? r.fires ?? 0}</td>
                <td class="${edgeCls(r.edge_20d)}">${num(r.edge_20d)}%</td>
                <td style="color:var(--text-3);font-size:11px;" title="95% CI for edge_20d">${ciStr}</td>
                <td>${num((r.win_rate ?? 0) * 100, 1)}%</td>
                <td style="color:var(--text-3)">${num(r.raw_avg_fwd20)}%</td>
                <td style="color:var(--text-3);font-size:11px;">${span}</td>
            </tr>`;
    }).join('');
}

function sortBy(column) {
    if (state.sortBy === column) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortBy = column;
        state.sortDir = column === 'rule_id' || column === 'direction' ? 'asc' : 'desc';
    }
    renderTable();
}

window.loadScorecard = loadScorecard;
window.sortBy = sortBy;

async function loadAtomicScorecard() {
    const minN = document.getElementById('atomicMinN')?.value ?? 0;
    DOM.atomicTableBody.innerHTML =
        '<tr><td colspan="9" style="text-align:center;padding:20px;color:var(--text-3);">Loading individual rules…</td></tr>';
    try {
        const data = await fetch(`/api/rules/atomic-scorecard?min_n=${minN}&limit=1000`)
            .then(r => r.json());
        atomicState.rules = Array.isArray(data) ? data : [];
        renderAtomicTable();
    } catch (e) {
        console.error('Failed to load atomic scorecard:', e);
        DOM.atomicTableBody.innerHTML =
            '<tr><td colspan="9" style="text-align:center;color:#b91c1c;">Error loading individual rules</td></tr>';
    }
}

function renderAtomicTable() {
    if (!atomicState.rules.length) {
        DOM.atomicTableBody.innerHTML =
            '<tr><td colspan="9" style="text-align:center;padding:20px;color:var(--text-3);">' +
            'No data. Run outcome ETL: <code>python -m etl.compute_firing_outcomes --truncate</code></td></tr>';
        return;
    }

    const dir = atomicState.sortDir === 'asc' ? 1 : -1;
    const rows = [...atomicState.rules].sort((a, b) => {
        let va = a[atomicState.sortBy], vb = b[atomicState.sortBy];
        if (typeof va === 'string' || typeof vb === 'string') {
            return ((va || '').localeCompare(vb || '')) * dir;
        }
        return ((va ?? 0) - (vb ?? 0)) * dir;
    });

    const num = (v, d = 2) => (v === null || v === undefined) ? '—' : Number(v).toFixed(d);
    const edgeCls = v => v > 0.5 ? 'edge-pos' : v < -0.5 ? 'edge-neg' : 'edge-neu';

    DOM.atomicTableBody.innerHTML = rows.map(r => {
        const span = (r.first_seen && r.last_seen)
            ? `${r.first_seen} → ${r.last_seen}` : '—';
        const conf = r.confidence || 'unproven';
        const unproven = conf === 'unproven';
        const rowStyle = unproven ? ' style="opacity:0.55;"' : '';
        const confBadge = conf === 'proven'
            ? `<span style="color:#15803d;font-weight:700;font-size:10px;">proven</span>`
            : conf === 'promising'
            ? `<span style="color:#92400e;font-size:10px;">promising</span>`
            : `<span style="color:#94a3b8;font-size:10px;">unproven</span>`;
        const ciLow  = r.ci_low  != null ? Number(r.ci_low).toFixed(2)  : '—';
        const ciHigh = r.ci_high != null ? Number(r.ci_high).toFixed(2) : '—';
        const ciStr  = (ciLow !== '—' && ciHigh !== '—') ? `[${ciLow}%, ${ciHigh}%]` : '—';
        return `
            <tr${rowStyle}>
                <td><strong>${r.rule_id}</strong></td>
                <td style="max-width:180px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                    title="${r.rule_name || ''}">${r.rule_name || '—'}</td>
                <td>${r.n ?? 0}</td>
                <td class="${edgeCls(r.avg_fwd_20d)}">${num(r.avg_fwd_20d)}%</td>
                <td style="color:var(--text-3)">${num(r.avg_fwd_5d)}%</td>
                <td style="color:var(--text-3);font-size:11px;" title="95% CI">${ciStr}</td>
                <td>${num((r.win_rate ?? 0) * 100, 1)}%</td>
                <td>${confBadge}</td>
                <td style="color:var(--text-3);font-size:11px;">${span}</td>
            </tr>`;
    }).join('');
}

function atomicSortBy(column) {
    if (atomicState.sortBy === column) {
        atomicState.sortDir = atomicState.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        atomicState.sortBy = column;
        atomicState.sortDir = (column === 'rule_id' || column === 'rule_name') ? 'asc' : 'desc';
    }
    renderAtomicTable();
}

window.loadAtomicScorecard = loadAtomicScorecard;
window.atomicSortBy = atomicSortBy;
