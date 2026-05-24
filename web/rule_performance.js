/**
 * Rule Performance — View rule hit rates and effectiveness
 */

const state = {
    rules: [],
    sortBy: 'hit_rate',
    sortDir: 'desc',
};

const DOM = {
    perfTableBody: document.getElementById('perfTableBody'),
};

document.addEventListener('DOMContentLoaded', async () => {
    await loadPerformance();
});

async function loadPerformance() {
    try {
        const data = await fetch('/api/rules/performance?sort=hit_rate&limit=500').then(r => r.json());
        state.rules = data;
        renderTable();
    } catch (e) {
        console.error('Failed to load performance:', e);
        DOM.perfTableBody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-3);">Error loading data</td></tr>';
    }
}

function renderTable() {
    if (state.rules.length === 0) {
        DOM.perfTableBody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 20px; color: var(--text-3);">No performance data</td></tr>';
        return;
    }

    DOM.perfTableBody.innerHTML = state.rules.map(r => {
        const hitRate = (r.hit_rate || 0) * 100;
        const hitClass = hitRate > 60 ? 'high' : hitRate > 40 ? 'medium' : 'low';

        return `
            <tr onclick="viewRuleDetails('${r.rule_id}')">
                <td><strong>${r.rule_id}</strong></td>
                <td>${r.rule_kind || '—'}</td>
                <td>${r.sample_size || 0}</td>
                <td><span class="hit-rate ${hitClass}">${hitRate.toFixed(1)}%</span></td>
                <td>${((r.false_positive_rate || 0) * 100).toFixed(1)}%</td>
                <td>${r.avg_fwd_5d ? r.avg_fwd_5d.toFixed(2) + '%' : '—'}</td>
                <td>${r.avg_fwd_20d ? r.avg_fwd_20d.toFixed(2) + '%' : '—'}</td>
                <td>${r.last_seen || '—'}</td>
            </tr>
        `;
    }).join('');
}

function changeSortBy(value) {
    state.sortBy = value;
    // In a real app, would re-fetch with new sort parameter
    console.log('Sort by:', value);
}

function sortBy(column) {
    if (state.sortBy === column) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortBy = column;
        state.sortDir = 'desc';
    }
    // Re-render or reload
    renderTable();
}

function viewRuleDetails(ruleId) {
    console.log('Viewing rule details:', ruleId);
    // Open detail view
    alert(`Viewing details for rule: ${ruleId}\n(Detail view coming soon)`);
}

// Expose functions
window.changeSortBy = changeSortBy;
window.sortBy = sortBy;
window.viewRuleDetails = viewRuleDetails;
