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

const factorState = {
    rows: [],
    sortBy: 'avg_fwd_20d',
    sortDir: 'desc',
};

const DOM = {
    perfTableBody: document.getElementById('perfTableBody'),
    atomicTableBody: document.getElementById('atomicTableBody'),
    agreementTableBody: document.getElementById('agreementTableBody'),
    factorTableBody: document.getElementById('factorTableBody'),
};

const agreementState = {
    rows: [],
    sortBy: 'avg_fwd_20d',
    sortDir: 'desc',
};

document.addEventListener('DOMContentLoaded', () => {
    loadEdgeReport();
    loadScorecard();
    loadMyActions();
    loadAtomicScorecard();
    loadAgreementScorecard();
    loadFactorScorecard();
});

// ---- Edge Report — live summary of scorecard + factor + my-actions data ----
async function loadEdgeReport() {
    try {
        const [scorecard, factors, myActions] = await Promise.all([
            fetch('/api/rules/scorecard?min_fires=20&limit=1000').then(r => r.json()),
            fetch('/api/rules/factor-scorecard?min_n=0&limit=1000').then(r => r.json()),
            fetch('/api/rules/my-actions?limit=1').then(r => r.json()),
        ]);
        renderEdgeStats(scorecard);
        renderEdgeRulesChart(scorecard);
        renderEdgeFactorsChart(factors);
        renderEdgeMyTrades(myActions);
        const meta = document.getElementById('edgeReportMeta');
        if (meta) meta.textContent = `Updated ${new Date().toLocaleString()}`;
    } catch (e) {
        console.error('Failed to load edge report:', e);
        const meta = document.getElementById('edgeReportMeta');
        if (meta) meta.textContent = 'Error loading';
    }
}

function renderEdgeStats(scorecard) {
    const rows = Array.isArray(scorecard) ? scorecard : [];
    const buy = rows.filter(r => r.direction === 'BUY');
    const sell = rows.filter(r => r.direction === 'SELL');

    const setRuleStat = (valId, subId, work, total, label) => {
        const val = document.getElementById(valId);
        const sub = document.getElementById(subId);
        if (val) {
            // Fixed-width number columns so the "/" lines up with the
            // adjacent Sell/Buy rules box, whatever the digit counts are.
            val.innerHTML = `<span class="edge-stance-count big"><span>${work}</span><span class="slash">/</span><span>${total}</span></span>`;
            val.className = 'edge-stat-value ' + (total === 0 ? '' : work === total ? 'er-good' : work === 0 ? 'er-critical' : '');
        }
        if (sub) sub.textContent = total === 0
            ? 'No rules with ≥20 fires yet'
            : work === total ? `Every ${label} rule shows a real edge`
            : work === 0 ? 'Not one has proven out yet'
            : `${work} of ${total} show a real edge`;
    };
    setRuleStat('edgeBuyRulesWork', 'edgeBuyRulesSub', buy.filter(r => r.edge_20d > 0).length, buy.length, 'buy');
    setRuleStat('edgeSellRulesWork', 'edgeSellRulesSub', sell.filter(r => r.edge_20d > 0).length, sell.length, 'sell');
}

function renderDivergingChart(container, rows) {
    if (!container) return;
    if (!rows.length) {
        container.innerHTML = '<div class="edge-loading">Not enough data yet.</div>';
        return;
    }
    const maxAbs = Math.max(...rows.map(r => Math.abs(r.value)), 0.01);
    const axis = '<div class="edge-axis"><div class="tick"></div><div class="tick-label">0%</div></div>';
    const body = rows.map(r => {
        const pct = Math.min(36, (Math.abs(r.value) / maxAbs) * 36);
        const isPos = r.value >= 0;
        const barCls = isPos ? 'pos' : 'neg';
        const valStyle = isPos
            ? `left:calc(50% + ${pct}% + 6px)`
            : `right:calc(50% + ${pct}% + 6px)`;
        return `<div class="edge-row">
            <div class="edge-label">${r.label}${r.tagHtml || ''}</div>
            <div class="edge-bar-track"><div class="mid"></div>
                <div class="bar ${barCls}" style="width:${pct}%"></div>
                <div class="val ${barCls}" style="${valStyle}">${isPos ? '+' : ''}${r.value.toFixed(2)}%</div>
            </div>
        </div>`;
    }).join('');
    container.innerHTML = axis + body;
}

// One bar (the direction-adjusted edge) per row, plus a BUY/SELL pill and
// the actual (unflipped) return as a plain number -- both in their own
// columns next to the label, ahead of the bar.
function renderRulesChart(container, rows) {
    if (!container) return;
    if (!rows.length) {
        container.innerHTML = '<div class="edge-loading">Not enough data yet.</div>';
        return;
    }
    const maxAbs = Math.max(...rows.map(r => Math.abs(r.value)), 0.01);
    const axis = '<div class="edge-axis"><div class="tick"></div><div class="tick-label">0%</div></div>';
    const head = `<div class="edge-row edge-row-rules edge-row-head">
            <div class="edge-label"></div><div></div>
            <div class="edge-col-head">Actual</div>
            <div class="edge-col-head">${axis}</div>
        </div>`;
    const body = rows.map(r => {
        const pct = Math.min(36, (Math.abs(r.value) / maxAbs) * 36);
        const isPos = r.value >= 0;
        const barCls = isPos ? 'pos' : 'neg';
        const valStyle = isPos
            ? `left:calc(50% + ${pct}% + 6px)`
            : `right:calc(50% + ${pct}% + 6px)`;
        const rawIsPos = r.rawValue >= 0;
        const rawCls = rawIsPos ? 'pos' : 'neg';
        return `<div class="edge-row edge-row-rules">
            <div class="edge-label">${r.label}</div>
            <span class="edge-tag ${r.dir === 'BUY' ? 'buy' : 'sell'}">${r.dir || '—'}</span>
            <span class="edge-raw-val ${rawCls}">${rawIsPos ? '+' : ''}${r.rawValue.toFixed(2)}%</span>
            <div class="edge-bar-track"><div class="mid"></div>
                <div class="bar ${barCls}" style="width:${pct}%"></div>
                <div class="val ${barCls}" style="${valStyle}">${isPos ? '+' : ''}${r.value.toFixed(2)}%</div>
            </div>
        </div>`;
    }).join('');
    container.innerHTML = head + body;
}

function _bestWorst(rows, sortKey) {
    const sorted = [...rows].sort((a, b) => b[sortKey] - a[sortKey]);
    const best = sorted.slice(0, 5);
    const worst = sorted.slice(Math.max(best.length, sorted.length - 5));
    return [...best, ...worst];
}

function renderEdgeRulesChart(scorecard) {
    const el = document.getElementById('edgeRulesChart');
    if (!el) return;
    const rows = (Array.isArray(scorecard) ? scorecard : []).filter(r => r.edge_20d != null);
    // The bar is edge_20d, direction-adjusted (SELL sign flipped, ">0 =
    // called it right"). "Actual" is raw_avg_fwd20, the same rule's real,
    // unflipped price move -- on a SELL rule these can point opposite ways.
    const items = _bestWorst(rows, 'edge_20d').map(r => ({
        label: r.rule_id,
        dir: r.direction,
        value: Number(r.edge_20d),
        rawValue: Number(r.raw_avg_fwd20),
    }));
    renderRulesChart(el, items);
}

function renderEdgeFactorsChart(factors) {
    const el = document.getElementById('edgeFactorsChart');
    if (!el) return;
    const rows = (Array.isArray(factors) ? factors : [])
        .filter(r => r.factor !== 'Baseline' && r.avg_fwd_20d != null && (r.n_symbols ?? 0) >= 5);
    const label = r => `${r.factor.charAt(0).toUpperCase()}${r.factor.slice(1)}: ${r.bucket}`;
    const items = _bestWorst(rows, 'avg_fwd_20d').map(r => ({
        label: label(r),
        value: Number(r.avg_fwd_20d),
    }));
    renderDivergingChart(el, items);
}

function renderEdgeMyTrades(myActions) {
    const fam = myActions.by_action_family || [];
    const buy = fam.find(f => f.family === 'BUY');
    const sell = fam.find(f => f.family === 'SELL');
    const byStanceAction = myActions.by_stance_action || [];
    // For a sell, this is the STOCK's own forward return, not your P&L --
    // a decline after you sold means you got out ahead of it (good timing),
    // a rise means the stock kept going without you (bad timing). So the
    // good/bad color logic is inverted vs. a buy. `invert` flips it.
    const stanceBreakdown = family => {
        const order = [
            ['FOLLOWED', 'Followed', 'rt-followed'],
            ['CONTRADICTED', 'Contradicted', 'rt-contradicted'],
            ['NO_SIGNAL', 'No signal', 'rt-nosignal'],
        ];
        const parts = order.map(([stance, label, cls]) => {
            const row = byStanceAction.find(r => r.stance === stance && r.family === family);
            const nr = row ? Number(row.n_right) : 0;
            const nw = row ? Number(row.n_wrong) : 0;
            if (!row || nr + nw === 0) return '';
            const pct = Math.round(100 * nr / (nr + nw));
            const pctCls = pct >= 50 ? 'er-pos' : 'er-neg';
            return `<div class="edge-stance-row"><span class="edge-stance-label ${cls}">${label}</span>`
                + `<span class="edge-stance-nums">`
                + `<span class="edge-stance-pct ${pctCls}">${pct}%</span>`
                + `<span class="edge-stance-count"><span>${nr}</span><span class="slash">/</span><span>${nw}</span></span>`
                + `</span></div>`;
        }).filter(Boolean);
        return parts.length ? `<div class="edge-stance-breakdown">${parts.join('')}</div>` : '';
    };
    const tile = (label, r, invert, family) => {
        if (!r || !r.n) {
            return `<div class="edge-stat-label-row"><span class="edge-stat-label">${label}</span><span class="edge-stat-sub">No inferred trades yet</span></div>`;
        }
        const avg = Number(r.avg_fwd_20d);
        const good = invert ? avg < 0 : avg > 0;
        const bad = invert ? avg > 0 : avg < 0;
        const cls = good ? 'er-pos' : bad ? 'er-neg' : '';
        const barColor = bad ? '#e34948' : '#0ca30c';
        // win_rate from the API is always "% that rose afterward" -- for a
        // sell that's the BAD outcome, so invert it here to "% good exits"
        // (fell afterward) so higher-is-always-better and the bar fill
        // matches the color, instead of a raw number that reads backwards.
        const rawWr = r.win_rate != null ? Number(r.win_rate) : null;
        const wr = rawWr != null ? (invert ? Math.round((100 - rawWr) * 10) / 10 : rawWr) : null;
        const wrLabel = invert ? 'good exits' : 'win';
        const title = invert ? ' title="Negative = the stock fell after you sold (good timing); positive = it kept rising without you"' : '';
        return `<div class="edge-tile-flex">
            <div class="edge-tile-main">
                <div class="edge-stat-label-row">
                    <span class="edge-stat-label">${label}</span>
                    <span class="edge-stat-sub">${r.n} trades${wr != null ? ` · ${wr}% ${wrLabel}` : ''}</span>
                </div>
                <div class="edge-stat-value-row">
                    <span class="edge-stat-value ${cls}"${title}>${avg >= 0 ? '+' : ''}${avg.toFixed(2)}%</span>
                    ${wr != null ? `<span class="edge-mini-meter" title="${wr}% ${wrLabel}"><span style="width:${wr}%;background:${barColor};"></span></span>` : ''}
                </div>
            </div>
            ${stanceBreakdown(family)}
        </div>`;
    };
    const buyEl = document.getElementById('edgeTradeBuy');
    const sellEl = document.getElementById('edgeTradeSell');
    if (buyEl) buyEl.innerHTML = tile('When you buy', buy, false, 'BUY');
    if (sellEl) sellEl.innerHTML = tile('When you reduce or sell', sell, true, 'SELL');
}

window.loadEdgeReport = loadEdgeReport;

async function loadMyActions() {
    const body = document.getElementById('myActionsBody');
    const summ = document.getElementById('myActionsSummary');
    const stanceEl = document.getElementById('myActionsStance');
    try {
        // limit bumped from 200: trade volume can exceed 200 within just the
        // last 30 days, which would otherwise cut off Recent Trades early.
        const data = await fetch('/api/rules/my-actions?limit=400').then(r => r.json());
        const recent = data.recent || [];
        const s = data.summary || {};
        if (s.n_actions) {
            const avg = s.avg_fwd_20d != null ? `${Number(s.avg_fwd_20d).toFixed(2)}%` : '—';
            const dollars = s.total_est_dollar != null ? ` · $${Number(s.total_est_dollar).toLocaleString(undefined, {maximumFractionDigits:0})} at stake` : '';
            summ.textContent = `${s.n_actions} inferred trades · ${s.n_scored || 0} scored · avg 20d ${avg}${dollars}`;
        } else {
            summ.textContent = '';
        }
        // TASK_121 + 2026-09-13: FOLLOWED / CONTRADICTED / NO_SIGNAL headline,
        // above the table -- right/wrong counts (summed across BUY+SELL,
        // direction-aware) instead of just an average, and now includes
        // NO_SIGNAL so all three stances are visible, not just two.
        if (stanceEl) {
            const bsa = data.by_stance_action || [];
            const totals = st => {
                const rows = bsa.filter(r => r.stance === st);
                return rows.reduce((a, r) => ({
                    right: a.right + Number(r.n_right || 0),
                    wrong: a.wrong + Number(r.n_wrong || 0),
                }), { right: 0, wrong: 0 });
            };
            const chip = (label, cls, st) => {
                const t = totals(st);
                const n = t.right + t.wrong;
                if (!n) return `<div class="rt-chip"><div class="rt-chip-label ${cls}">${label}</div><div class="rt-chip-val" style="color:var(--text-3);">no scored trades yet</div></div>`;
                const pct = Math.round(100 * t.right / n);
                const pctCls = pct >= 50 ? 'er-pos' : 'er-neg';
                return `<div class="rt-chip">
                    <div class="rt-chip-label ${cls}">${label}</div>
                    <div class="rt-chip-val"><span class="${pctCls}" style="font-size:14px;">${pct}%</span>
                        <span style="color:var(--text-3);font-weight:400;font-size:11px;">(${t.right} right / ${t.wrong} wrong)</span></div>
                </div>`;
            };
            if (bsa.length) {
                stanceEl.innerHTML = `<div class="rt-chip-row">`
                    + chip('Followed the rec', 'rt-followed', 'FOLLOWED')
                    + chip('Contradicted it', 'rt-contradicted', 'CONTRADICTED')
                    + chip('No signal active', 'rt-nosignal', 'NO_SIGNAL')
                    + `</div>`;
            } else {
                stanceEl.innerHTML = '';
            }
        }
        if (!recent.length) {
            body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:14px;color:var(--text-3);">'
                + 'No inferred trades yet. Real position changes (CS/F snapshot deltas) will appear here automatically once the derive runs.</td></tr>';
            return;
        }
        const num = v => (v === null || v === undefined) ? '—'
            : `<span class="${v >= 0 ? 'act-buy-strong' : 'act-sell-strong'}">${Number(v).toFixed(2)}%</span>`;
        // Stance badge: FOLLOWED = green, CONTRADICTED = red, NO_SIGNAL = grey
        const stanceBadge = r => {
            const st = r.stance || 'NO_SIGNAL';
            const style = st === 'FOLLOWED'
                ? 'background:#dcfce7;color:#166534;'
                : st === 'CONTRADICTED'
                ? 'background:#fceeee;color:#d03b3b;'
                : 'background:#f1f5f9;color:#64748b;';
            return `<span style="font-size:9px;${style}border-radius:3px;padding:1px 4px;font-weight:700;">${st}</span>`;
        };
        const tradeBadge = r => {
            const disp = actionDisplay(r.inferred_action === 'BUY' ? 'BM' : 'SA');
            const cls = (disp.colorCls || 'act-neutral') + '-tint';
            return `<span class="act-badge act-badge-sm ${cls}" style="font-size:10px;">${r.inferred_action || ''}</span>`;
        };
        body.innerHTML = recent.map(r => `
            <tr>
                <td style="font-size:11px;">${(r.as_of_date || '').toString().slice(0,10)}</td>
                <td><strong>${r.tos_symbol || ''}</strong></td>
                <td title="qty ${r.qty_delta ?? ''} · $${r.est_dollar ?? ''}">${tradeBadge(r)}</td>
                <td>${r.rec_action ? actionText(actionDisplay(r.rec_action)) : '—'}</td>
                <td>${stanceBadge(r)}</td>
                <td>${num(r.fwd_5d_pct)}</td>
                <td>${num(r.fwd_20d_pct)}</td>
            </tr>`).join('');

        renderRecentTrades(recent);
    } catch (e) {
        console.error('Failed to load my-actions:', e);
        body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#d03b3b;">Error loading actions</td></tr>';
        const rtBody = document.getElementById('recentTradesBody');
        if (rtBody) rtBody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#d03b3b;">Error loading trades</td></tr>';
    }
}

// "Recent trades" -- last 30 days, with an early 5-day read where it's
// ready instead of a blank dash, since the full 20-day verdict needs about
// a month. Reuses the same fetch as "Your actions", just filtered/labeled
// differently -- no extra API call.
// A trade "looks right" when the early read agrees with what you were
// trying to do -- price up after a buy, price down after a sell (sell
// semantics invert: falling after you sold is the good outcome).
function _tradeLooksRight(v, isSell) {
    if (v == null) return null;
    v = Number(v);
    if (v === 0) return null;
    return isSell ? v < 0 : v > 0;
}

function renderRecentTrades(recent) {
    const body = document.getElementById('recentTradesBody');
    const summ = document.getElementById('recentTradesSummary');
    const tallyEl = document.getElementById('recentTradesTally');
    if (!body) return;
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 30);
    const rows = (recent || []).filter(r => r.as_of_date && new Date(r.as_of_date) >= cutoff);
    if (summ) {
        const withRead = rows.filter(r => r.fwd_5d_pct != null || r.fwd_20d_pct != null).length;
        summ.textContent = rows.length ? `${rows.length} trades · ${withRead} with an early read so far` : '';
    }
    if (tallyEl) {
        // Prefer the 20d verdict once it exists, otherwise fall back to the
        // 5d early read -- for a 30-day-old window this is almost always 5d.
        // Broken out by stance -- FOLLOWED (you did what the system said),
        // CONTRADICTED (you did the opposite), NO_SIGNAL (nothing active to
        // follow or not) -- so "did I do this right" is visible per stance,
        // not just as one blended number.
        const byStance = {
            FOLLOWED:     { right: 0, wrong: 0 },
            CONTRADICTED: { right: 0, wrong: 0 },
            NO_SIGNAL:    { right: 0, wrong: 0 },
        };
        for (const r of rows) {
            const isSell = r.inferred_action === 'SELL';
            const v = r.fwd_20d_pct != null ? r.fwd_20d_pct : r.fwd_5d_pct;
            const ok = _tradeLooksRight(v, isSell);
            if (ok === null) continue;
            const bucket = byStance[r.stance || 'NO_SIGNAL'];
            if (!bucket) continue;
            if (ok) bucket.right++; else bucket.wrong++;
        }
        const totalScored = Object.values(byStance).reduce((s, b) => s + b.right + b.wrong, 0);
        if (totalScored > 0) {
            const chip = (label, cls, b) => {
                const n = b.right + b.wrong;
                if (!n) return `<div class="rt-chip"><div class="rt-chip-label ${cls}">${label}</div><div class="rt-chip-val" style="color:var(--text-3);">no scored trades yet</div></div>`;
                const pct = Math.round(100 * b.right / n);
                const pctCls = pct >= 50 ? 'er-pos' : 'er-neg';
                return `<div class="rt-chip">
                    <div class="rt-chip-label ${cls}">${label}</div>
                    <div class="rt-chip-val"><span class="${pctCls}" style="font-size:14px;">${pct}%</span>
                        <span style="color:var(--text-3);font-weight:400;font-size:11px;">(${b.right} right / ${b.wrong} wrong)</span></div>
                </div>`;
            };
            tallyEl.innerHTML = `<div class="rt-chip-row">`
                + chip('Followed the rec', 'rt-followed', byStance.FOLLOWED)
                + chip('Contradicted it', 'rt-contradicted', byStance.CONTRADICTED)
                + chip('No signal active', 'rt-nosignal', byStance.NO_SIGNAL)
                + `</div>`;
        } else {
            tallyEl.innerHTML = '';
        }
    }
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:14px;color:var(--text-3);">No trades in the last 30 days.</td></tr>';
        return;
    }
    const daysAgo = dateStr => Math.floor((Date.now() - new Date(dateStr)) / 86400000);
    // Sell semantics invert: a stock falling after you sold is the GOOD
    // outcome -- same rule as the Edge Report trade tiles above.
    const fmtReturn = (v, isSell, minDaysForThis, elapsed) => {
        if (v != null) {
            const good = isSell ? v < 0 : v > 0;
            const bad = isSell ? v > 0 : v < 0;
            const cls = good ? 'er-pos' : bad ? 'er-neg' : '';
            return `<span class="${cls}">${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%</span>`;
        }
        if (elapsed < minDaysForThis) {
            return `<span style="color:var(--text-3);font-style:italic;">too soon (${minDaysForThis - elapsed}d)</span>`;
        }
        return '<span style="color:var(--text-3);">—</span>';
    };
    const stanceBadge = r => {
        const st = r.stance || 'NO_SIGNAL';
        const style = st === 'FOLLOWED' ? 'background:#dcfce7;color:#166534;'
            : st === 'CONTRADICTED' ? 'background:#fceeee;color:#d03b3b;'
            : 'background:#f1f5f9;color:#64748b;';
        return `<span style="font-size:9px;${style}border-radius:3px;padding:1px 4px;font-weight:700;">${st}</span>`;
    };
    const tradeBadge = r => {
        const disp = actionDisplay(r.inferred_action === 'BUY' ? 'BM' : 'SA');
        const cls = (disp.colorCls || 'act-neutral') + '-tint';
        return `<span class="act-badge act-badge-sm ${cls}" style="font-size:10px;">${r.inferred_action || ''}</span>`;
    };
    body.innerHTML = rows.map(r => {
        const isSell = r.inferred_action === 'SELL';
        const elapsed = daysAgo(r.as_of_date);
        return `<tr>
            <td style="font-size:11px;">${(r.as_of_date || '').toString().slice(0,10)}</td>
            <td><strong>${r.tos_symbol || ''}</strong></td>
            <td title="qty ${r.qty_delta ?? ''} · $${r.est_dollar ?? ''}">${tradeBadge(r)}</td>
            <td>${stanceBadge(r)}</td>
            <td>${fmtReturn(r.fwd_5d_pct, isSell, 7, elapsed)}</td>
            <td>${fmtReturn(r.fwd_20d_pct, isSell, 28, elapsed)}</td>
        </tr>`;
    }).join('');
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
            '<tr><td colspan="8" style="text-align:center;color:#d03b3b;">Error loading scorecard</td></tr>';
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
            '<tr><td colspan="9" style="text-align:center;color:#d03b3b;">Error loading individual rules</td></tr>';
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

// ---- Factor scorecard (2026-08-01) ----
let _factorSelPopulated = false;

async function loadFactorScorecard() {
    const minN = document.getElementById('factorMinN')?.value ?? 0;
    DOM.factorTableBody.innerHTML =
        '<tr><td colspan="10" style="text-align:center;padding:20px;color:var(--text-3);">Loading factor scorecard…</td></tr>';
    try {
        const data = await fetch(`/api/rules/factor-scorecard?min_n=${minN}&limit=1000`)
            .then(r => r.json());
        factorState.rows = Array.isArray(data) ? data : [];
        if (!_factorSelPopulated) {
            const sel = document.getElementById('factorSel');
            const factors = [...new Set(factorState.rows.map(r => r.factor))].sort();
            for (const f of factors) {
                if (f === 'Baseline') continue;
                const opt = document.createElement('option');
                opt.value = f; opt.textContent = f;
                sel.appendChild(opt);
            }
            _factorSelPopulated = true;
        }
        renderFactorTable();
    } catch (e) {
        console.error('Failed to load factor scorecard:', e);
        DOM.factorTableBody.innerHTML =
            '<tr><td colspan="10" style="text-align:center;color:#d03b3b;">Error loading factor scorecard</td></tr>';
    }
}

function renderFactorTable() {
    if (!factorState.rows.length) {
        DOM.factorTableBody.innerHTML =
            '<tr><td colspan="10" style="text-align:center;padding:20px;color:var(--text-3);">' +
            'No data. Run the outcome ETL: <code>python -m etl.compute_factor_outcomes --truncate</code></td></tr>';
        return;
    }

    const factorFilter = document.getElementById('factorSel')?.value ?? 'all';
    const baseline = factorState.rows.find(r => r.factor === 'Baseline');
    const baselineAvg20 = baseline ? Number(baseline.avg_fwd_20d) : null;

    let rows = factorState.rows.filter(r =>
        factorFilter === 'all' ? r.factor !== 'Baseline' : r.factor === factorFilter);
    if (factorFilter === 'all' && baseline) rows = [baseline, ...rows];

    const dir = factorState.sortDir === 'asc' ? 1 : -1;
    rows = [...rows].sort((a, b) => {
        let va = a[factorState.sortBy], vb = b[factorState.sortBy];
        if (typeof va === 'string' || typeof vb === 'string') {
            return ((va || '').localeCompare(vb || '')) * dir;
        }
        return ((va ?? 0) - (vb ?? 0)) * dir;
    });

    const num = (v, d = 2) => (v === null || v === undefined) ? '—' : Number(v).toFixed(d);
    const edgeCls = v => v > 0.5 ? 'edge-pos' : v < -0.5 ? 'edge-neg' : 'edge-neu';

    DOM.factorTableBody.innerHTML = rows.map(r => {
        const span = (r.first_seen && r.last_seen)
            ? `${r.first_seen} → ${r.last_seen}` : '—';
        const conf = r.confidence || 'unproven';
        const isBaseline = r.factor === 'Baseline';
        const unproven = conf === 'unproven' && !isBaseline;
        const rowStyle = unproven ? ' style="opacity:0.55;"' : (isBaseline ? ' style="font-weight:600;background:var(--bg-2);"' : '');
        const confBadge = isBaseline ? ''
            : conf === 'proven'
            ? `<span style="color:#15803d;font-weight:700;font-size:10px;">proven</span>`
            : conf === 'promising'
            ? `<span style="color:#92400e;font-size:10px;">promising</span>`
            : `<span style="color:#94a3b8;font-size:10px;">unproven</span>`;
        const ciLow  = r.ci_low  != null ? Number(r.ci_low).toFixed(2)  : '—';
        const ciHigh = r.ci_high != null ? Number(r.ci_high).toFixed(2) : '—';
        const ciStr  = (ciLow !== '—' && ciHigh !== '—') ? `[${ciLow}%, ${ciHigh}%]` : '—';
        // Color by DELTA vs baseline, not raw sign — this data covers a rising
        // market where the baseline itself is positive (avg 20d +1.27%), so
        // most buckets are nominally positive even when they underperform the
        // average stock. Coloring on raw sign made almost every row look
        // green regardless of whether it actually beat the average; fixed
        // 2026-08-01 (same fix as the Actionable grid's RSI/IV tags).
        const delta = (baselineAvg20 != null && r.avg_fwd_20d != null) ? r.avg_fwd_20d - baselineAvg20 : null;
        const deltaCls = isBaseline ? 'edge-neu' : delta == null ? 'edge-neu' : edgeCls(delta);
        const deltaStr = (!isBaseline && delta != null)
            ? ` <span style="font-size:10px;color:var(--text-3);" title="vs baseline avg 20d ${num(baselineAvg20)}%">(${delta >= 0 ? '+' : ''}${num(delta)}pp)</span>`
            : '';
        return `
            <tr${rowStyle}>
                <td>${r.factor}</td>
                <td><strong>${r.bucket}</strong></td>
                <td>${r.n ?? 0}</td>
                <td>${r.n_symbols ?? 0}</td>
                <td class="${deltaCls}">${num(r.avg_fwd_20d)}%${deltaStr}</td>
                <td style="color:var(--text-3)">${num(r.avg_fwd_5d)}%</td>
                <td style="color:var(--text-3);font-size:11px;" title="95% CI">${ciStr}</td>
                <td>${num((r.win_rate ?? 0) * 100, 1)}%</td>
                <td>${confBadge}</td>
                <td style="color:var(--text-3);font-size:11px;">${span}</td>
            </tr>`;
    }).join('');
}

function factorSortBy(column) {
    if (factorState.sortBy === column) {
        factorState.sortDir = factorState.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        factorState.sortBy = column;
        factorState.sortDir = (column === 'factor' || column === 'bucket') ? 'asc' : 'desc';
    }
    renderFactorTable();
}

window.loadFactorScorecard = loadFactorScorecard;
window.factorSortBy = factorSortBy;

// ---- TASK_69: Agreement scorecard ----
const _AGR_COLOR_PERF = {
    agree_bull:      '#16a34a',
    agree_bear:      '#e34948',
    split_tech_bull: '#d97706',
    split_tech_bear: '#ea580c',
    neutral:         '#94a3b8',
};

async function loadAgreementScorecard() {
    if (!DOM.agreementTableBody) return;
    DOM.agreementTableBody.innerHTML =
        '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-3);">Loading…</td></tr>';
    try {
        const data = await fetch('/api/rules/agreement-scorecard').then(r => r.json());
        agreementState.rows = Array.isArray(data) ? data : [];
        renderAgreementTable();
    } catch (e) {
        console.error('Failed to load agreement scorecard:', e);
        DOM.agreementTableBody.innerHTML =
            '<tr><td colspan="7" style="text-align:center;color:#d03b3b;">Error loading agreement scorecard</td></tr>';
    }
}

function renderAgreementTable() {
    if (!DOM.agreementTableBody) return;
    if (!agreementState.rows.length) {
        DOM.agreementTableBody.innerHTML =
            '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-3);">'
            + 'No data yet — agreement_class is populated after derive_bull_prob runs with an active model, and outcome ETL must have computed forward returns.</td></tr>';
        return;
    }
    const dir = agreementState.sortDir === 'asc' ? 1 : -1;
    const rows = [...agreementState.rows].sort((a, b) => {
        let va = a[agreementState.sortBy], vb = b[agreementState.sortBy];
        if (typeof va === 'string' || typeof vb === 'string') {
            return ((va || '').localeCompare(vb || '')) * dir;
        }
        return ((va ?? 0) - (vb ?? 0)) * dir;
    });
    const num = (v, d = 2) => (v === null || v === undefined) ? '—' : Number(v).toFixed(d);
    const edgeCls = v => v > 0.5 ? 'edge-pos' : v < -0.5 ? 'edge-neg' : 'edge-neu';
    DOM.agreementTableBody.innerHTML = rows.map(r => {
        const cls = r.agreement_class || '';
        const color = _AGR_COLOR_PERF[cls] || '#64748b';
        const conf = r.confidence || 'unproven';
        const confBadge = conf === 'proven'
            ? `<span style="color:#15803d;font-weight:700;font-size:10px;">proven</span>`
            : conf === 'promising'
            ? `<span style="color:#92400e;font-size:10px;">promising</span>`
            : `<span style="color:#94a3b8;font-size:10px;">unproven</span>`;
        const ciLow  = r.ci_low  != null ? Number(r.ci_low).toFixed(2)  : '—';
        const ciHigh = r.ci_high != null ? Number(r.ci_high).toFixed(2) : '—';
        const ciStr  = (ciLow !== '—' && ciHigh !== '—') ? `[${ciLow}%, ${ciHigh}%]` : '—';
        return `
            <tr>
                <td><strong style="color:${color};">${cls}</strong></td>
                <td>${r.n ?? 0}</td>
                <td class="${edgeCls(r.avg_fwd_20d)}">${num(r.avg_fwd_20d)}%</td>
                <td style="color:var(--text-3)">${num(r.avg_fwd_5d)}%</td>
                <td>${num((r.win_rate ?? 0) * 100, 1)}%</td>
                <td style="color:var(--text-3);font-size:11px;" title="95% CI for avg_fwd_20d">${ciStr}</td>
                <td>${confBadge}</td>
            </tr>`;
    }).join('');
}

function agSortBy(column) {
    if (agreementState.sortBy === column) {
        agreementState.sortDir = agreementState.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        agreementState.sortBy = column;
        agreementState.sortDir = column === 'agreement_class' ? 'asc' : 'desc';
    }
    renderAgreementTable();
}

window.loadAgreementScorecard = loadAgreementScorecard;
window.agSortBy = agSortBy;
