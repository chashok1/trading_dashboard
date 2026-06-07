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

const DOM = {
    perfTableBody: document.getElementById('perfTableBody'),
};

document.addEventListener('DOMContentLoaded', loadScorecard);

async function loadScorecard() {
    const minFires = document.getElementById('minFires')?.value ?? 30;
    DOM.perfTableBody.innerHTML =
        '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-3);">Loading scorecard…</td></tr>';
    try {
        const data = await fetch(`/api/rules/scorecard?min_fires=${minFires}&limit=1000`)
            .then(r => r.json());
        state.rules = Array.isArray(data) ? data : [];
        renderTable();
    } catch (e) {
        console.error('Failed to load scorecard:', e);
        DOM.perfTableBody.innerHTML =
            '<tr><td colspan="7" style="text-align:center;color:#b91c1c;">Error loading scorecard</td></tr>';
    }
}

function renderTable() {
    if (!state.rules.length) {
        DOM.perfTableBody.innerHTML =
            '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-3);">' +
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
        const dirCls = r.direction === 'BUY' ? 'dir-buy' : 'dir-sell';
        return `
            <tr>
                <td><strong>${r.rule_id}</strong></td>
                <td class="${dirCls}">${r.direction || '—'}</td>
                <td>${r.fires ?? 0}</td>
                <td class="${edgeCls(r.edge_20d)}">${num(r.edge_20d)}%</td>
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
