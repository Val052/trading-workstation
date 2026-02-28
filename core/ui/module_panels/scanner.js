/* Scanner Module — Panel JS */

(function() {
    'use strict';

    // API base for scanner module (all routes under /api/scanner/)
    const SAPI = '/api/scanner';

    // State
    let currentResults = [];
    let currentNearMisses = [];
    let selectedResult = null;

    // ── Tab Navigation ──
    document.querySelectorAll('#scanner-panel .module-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#scanner-panel .module-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('#scanner-panel .tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');

            if (tab.dataset.tab === 'strategies') loadStrategies();
            if (tab.dataset.tab === 'watchlist') loadWatchlist();
            if (tab.dataset.tab === 'outcomes') loadOutcomes();
            if (tab.dataset.tab === 'settings') loadSettings();
        });
    });

    // ── Dashboard: Run Scan ──
    document.getElementById('btn-run-scan').addEventListener('click', async () => {
        const btn = document.getElementById('btn-run-scan');
        const status = document.getElementById('scan-status');

        btn.disabled = true;
        btn.textContent = 'Scanning...';
        status.className = 'status-bar loading';
        status.textContent = 'Fetching market data and running strategies (this may take a few minutes for full S&P 500)...';

        try {
            const resp = await fetch(`${SAPI}/scan/run`, { method: 'POST' });
            const data = await resp.json();

            currentResults = data.results || [];
            currentNearMisses = data.near_misses || [];

            renderResults(currentResults);
            renderNearMisses(currentNearMisses);
            populateStrategyFilter(currentResults.concat(currentNearMisses));

            const nmText = data.near_miss_count ? `, ${data.near_miss_count} near-miss${data.near_miss_count !== 1 ? 'es' : ''}` : '';
            status.className = 'status-bar success';
            status.textContent = `Scan complete: ${data.count} hit${data.count !== 1 ? 's' : ''}${nmText}`;
        } catch (err) {
            status.className = 'status-bar error';
            status.textContent = `Scan failed: ${err.message}`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Run Scan';
        }
    });

    // ── Dashboard: Filter ──
    document.getElementById('btn-filter').addEventListener('click', loadFilteredResults);

    async function loadFilteredResults() {
        const strategyId = document.getElementById('filter-strategy').value;
        const dateVal = document.getElementById('filter-date').value;

        let url = `${SAPI}/scan/results?`;
        if (strategyId) url += `strategy_id=${strategyId}&`;
        if (dateVal) url += `scan_date=${dateVal}&`;

        try {
            const resp = await fetch(url);
            const data = await resp.json();
            currentResults = data.map(r => ({
                ...r,
                price: r.price_at_scan,
                strategy_name: r.strategy_id,
            }));
            renderResults(currentResults);
            document.getElementById('near-misses-section').classList.add('hidden');
        } catch (err) {
            console.error('Filter failed:', err);
        }
    }

    // ── Render scan results ──
    function renderResults(results) {
        const tbody = document.querySelector('#results-table tbody');
        tbody.innerHTML = '';

        if (!results.length) {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted)">No results. Click "Run Scan" to scan the universe.</td></tr>';
            return;
        }

        const tickerCounts = {};
        results.forEach(r => { tickerCounts[r.ticker] = (tickerCounts[r.ticker] || 0) + 1; });

        results.forEach((r, idx) => {
            const tr = document.createElement('tr');
            const sig = r.signal_data || {};
            const isConvergent = tickerCounts[r.ticker] > 1;

            const wc = sig.weekly_context || {};
            const alignLabel = wc.alignment_label || '-';
            const alignClass = alignLabel === 'STRONG' ? 'positive' : alignLabel === 'CONFLICTING' ? 'negative' : alignLabel === 'WEAK' ? 'align-weak' : '';

            tr.innerHTML = `
                <td>${r.ticker}${isConvergent ? ' <span style="color:var(--accent)" title="Multiple strategies">&#9733;</span>' : ''}</td>
                <td>${r.strategy_name || r.strategy_id}</td>
                <td>$${(r.price || r.price_at_scan || 0).toFixed(2)}</td>
                <td>${sig.rs_ratio != null ? sig.rs_ratio : (sig.rs_vs_spy_20d != null ? sig.rs_vs_spy_20d : (sig.sector_rs != null ? sig.sector_rs : '-'))}</td>
                <td>${formatKeyMetric(sig)}</td>
                <td>${sig.volume_ratio || (sig.sector ? sig.sector : '-')}</td>
                <td>${sig.atr_14 ? '$' + sig.atr_14 : (sig.atr ? '$' + sig.atr : '-')}</td>
                <td class="${alignClass}">${alignLabel}</td>
                <td>${r.scan_date || '-'}</td>
            `;

            tr.addEventListener('click', () => showDetail(r, idx));
            tbody.appendChild(tr);
        });
    }

    function formatKeyMetric(sig) {
        if (sig.dist_to_ema8_pct != null) return sig.dist_to_ema8_pct + '% EMA8';
        if (sig.dist_to_avwap_pct != null) return sig.dist_to_avwap_pct + '% AVWAP';
        if (sig.breakout_type != null) return sig.breakout_type.replace(/_/g, ' ');
        if (sig.sector_rank != null) return '#' + sig.sector_rank + ' sector';
        return '-';
    }

    // ── Render near misses ──
    function renderNearMisses(nearMisses) {
        const section = document.getElementById('near-misses-section');
        const tbody = document.querySelector('#near-misses-table tbody');
        const countBadge = document.getElementById('near-miss-count');

        if (!nearMisses.length) {
            section.classList.add('hidden');
            return;
        }

        section.classList.remove('hidden');
        countBadge.textContent = nearMisses.length;
        tbody.innerHTML = '';

        nearMisses.forEach((r) => {
            const tr = document.createElement('tr');
            const sig = r.signal_data || {};
            tr.innerHTML = `
                <td>${r.ticker}</td>
                <td>${r.strategy_name || r.strategy_id}</td>
                <td>$${(r.price || 0).toFixed(2)}</td>
                <td><span class="failed-filter">${r.failed_filter || '?'}</span></td>
                <td>${sig.rs_ratio != null ? sig.rs_ratio : '-'}</td>
                <td style="font-size:12px">${formatKeyMetric(sig)}</td>
            `;
            tr.addEventListener('click', () => showDetail(r, -1));
            tbody.appendChild(tr);
        });
    }

    // Near-miss toggle
    document.getElementById('near-misses-toggle').addEventListener('click', function() {
        this.classList.toggle('collapsed');
        const table = document.getElementById('near-misses-table');
        table.style.display = this.classList.contains('collapsed') ? 'none' : '';
    });

    function populateStrategyFilter(results) {
        const sel = document.getElementById('filter-strategy');
        const strategies = [...new Set(results.map(r => r.strategy_id))];
        sel.innerHTML = '<option value="">All</option>';
        strategies.forEach(s => {
            sel.innerHTML += `<option value="${s}">${s}</option>`;
        });
    }

    // ── Detail panel ──
    function showDetail(result, idx) {
        selectedResult = result;
        const panel = document.getElementById('detail-panel');
        panel.classList.remove('hidden');

        document.querySelectorAll('#results-table tbody tr').forEach((tr, i) => {
            tr.classList.toggle('selected', i === idx);
        });

        const sig = result.signal_data || {};
        const price = result.price || result.price_at_scan || 0;

        let titleExtra = '';
        if (result.near_miss) titleExtra = ` [near miss: ${result.failed_filter}]`;

        document.getElementById('detail-ticker').textContent = `${result.ticker} \u2014 $${price.toFixed(2)}${titleExtra}`;
        document.getElementById('detail-tv-link').href = `https://www.tradingview.com/chart/?symbol=${result.ticker}`;

        // Signal details
        let signalHtml = '<table>';
        if (sig.rs_ratio != null) signalHtml += `<tr><td>RS Ratio vs SPY</td><td>${sig.rs_ratio}</td></tr>`;
        if (sig.stock_return_pct != null) signalHtml += `<tr><td>Stock Return</td><td>${sig.stock_return_pct}%</td></tr>`;
        if (sig.spy_return_pct != null) signalHtml += `<tr><td>SPY Return</td><td>${sig.spy_return_pct}%</td></tr>`;
        if (sig.volume_ratio != null) signalHtml += `<tr><td>Volume Ratio</td><td>${sig.volume_ratio}</td></tr>`;
        if (sig.sector) signalHtml += `<tr><td>Sector</td><td>${sig.sector} (${sig.sector_etf})</td></tr>`;
        if (sig.sector_rs != null) signalHtml += `<tr><td>Sector RS</td><td>${sig.sector_rs}</td></tr>`;
        if (sig.sector_rank != null) signalHtml += `<tr><td>Sector Rank</td><td>#${sig.sector_rank}</td></tr>`;
        if (sig.anchor_type) signalHtml += `<tr><td>AVWAP Anchor</td><td>${sig.anchor_type} (${sig.anchor_date})</td></tr>`;
        if (sig.avwap != null) signalHtml += `<tr><td>AVWAP Level</td><td>$${sig.avwap}</td></tr>`;
        if (sig.dist_to_avwap_pct != null) signalHtml += `<tr><td>Dist to AVWAP</td><td>${sig.dist_to_avwap_pct}%</td></tr>`;
        if (sig.price_vs_avwap) signalHtml += `<tr><td>Price vs AVWAP</td><td>${sig.price_vs_avwap}</td></tr>`;
        if (result.description) signalHtml += `<tr><td colspan="2" style="font-size:12px;padding-top:8px">${result.description}</td></tr>`;
        signalHtml += '</table>';
        document.getElementById('detail-signal').innerHTML = signalHtml;

        // Key levels
        let levelsHtml = '<table>';
        if (sig.ema_fast != null) levelsHtml += `<tr><td>EMA 8</td><td>$${sig.ema_fast}</td></tr>`;
        if (sig.ema_slow != null) levelsHtml += `<tr><td>EMA 21</td><td>$${sig.ema_slow}</td></tr>`;
        if (sig.dma_50 != null) levelsHtml += `<tr><td>50 DMA</td><td>$${sig.dma_50}</td></tr>`;
        if (sig.dma_200 != null) levelsHtml += `<tr><td>200 DMA</td><td>$${sig.dma_200}</td></tr>`;
        if (sig.avwap != null) levelsHtml += `<tr><td>AVWAP</td><td>$${sig.avwap}</td></tr>`;
        if (sig.atr_14 != null) levelsHtml += `<tr><td>ATR(14)</td><td>$${sig.atr_14}</td></tr>`;
        if (sig.swing_low_10 != null) levelsHtml += `<tr><td>Swing Low (10)</td><td>$${sig.swing_low_10}</td></tr>`;
        if (sig.suggested_stop != null) levelsHtml += `<tr><td>Suggested Stop</td><td>$${sig.suggested_stop}</td></tr>`;
        levelsHtml += '</table>';
        document.getElementById('detail-levels').innerHTML = levelsHtml;

        // Pre-fill risk calculator
        document.getElementById('rc-entry').value = price.toFixed(2);
        document.getElementById('rc-stop').value = sig.suggested_stop || '';
        const risk = price - (sig.suggested_stop || price);
        document.getElementById('rc-target').value = risk > 0 ? (price + 2 * risk).toFixed(2) : '';

        document.getElementById('risk-result').innerHTML = '';
    }

    document.getElementById('detail-close').addEventListener('click', () => {
        document.getElementById('detail-panel').classList.add('hidden');
        document.querySelectorAll('#results-table tbody tr').forEach(tr => tr.classList.remove('selected'));
        selectedResult = null;
    });

    // ── Risk Calculator ──
    document.getElementById('btn-calc-risk').addEventListener('click', async () => {
        const entry = parseFloat(document.getElementById('rc-entry').value);
        const stop = parseFloat(document.getElementById('rc-stop').value);
        const target = parseFloat(document.getElementById('rc-target').value);

        if (isNaN(entry) || isNaN(stop) || isNaN(target)) {
            document.getElementById('risk-result').innerHTML = '<span class="negative">Fill in entry, stop, and target.</span>';
            return;
        }

        try {
            const resp = await fetch(`${SAPI}/candidates/calculate-risk`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entry_price: entry, stop_loss: stop, target_1: target }),
            });
            const calc = await resp.json();
            const targets = calc.r_targets || {};
            document.getElementById('risk-result').innerHTML = `
                <table>
                    <tr><td>Risk/Share</td><td class="negative">$${calc.risk_per_share}</td></tr>
                    <tr><td>Reward/Share</td><td class="positive">$${calc.reward_per_share}</td></tr>
                    <tr><td>R-Multiple</td><td>${calc.r_multiple}R</td></tr>
                    <tr><td>Position Size</td><td>${calc.position_size} shares</td></tr>
                    <tr><td>$ at Risk</td><td class="negative">$${calc.dollar_risk}</td></tr>
                    <tr><td>$ Reward</td><td class="positive">$${calc.dollar_reward}</td></tr>
                    <tr><td>Account Risk</td><td>${(calc.account_risk_pct * 100).toFixed(2)}%</td></tr>
                    <tr><td>1R Target</td><td>$${targets['1R'] || '-'}</td></tr>
                    <tr><td>2R Target</td><td>$${targets['2R'] || '-'}</td></tr>
                    <tr><td>3R Target</td><td>$${targets['3R'] || '-'}</td></tr>
                </table>
            `;
        } catch (err) {
            document.getElementById('risk-result').innerHTML = `<span class="negative">Error: ${err.message}</span>`;
        }
    });

    // ── Bookmark ──
    document.getElementById('btn-bookmark').addEventListener('click', async () => {
        if (!selectedResult) return;

        const stop = parseFloat(document.getElementById('rc-stop').value);
        const target = parseFloat(document.getElementById('rc-target').value);
        const scanResultId = selectedResult.id;
        const structure = document.getElementById('bookmark-structure').value;

        if (isNaN(stop) || isNaN(target) || !scanResultId) {
            alert('Set stop and target first, then bookmark. (Near misses cannot be bookmarked.)');
            return;
        }

        try {
            const endpoint = structure === 'stock' ? `${SAPI}/candidates/bookmark` : `${SAPI}/options/bookmark`;
            const body = structure === 'stock'
                ? { scan_result_id: scanResultId, stop_loss: stop, target_1: target, trade_structure: 'stock' }
                : { scan_result_id: scanResultId, stop_loss: stop, target_1: target, structure_type: structure };

            const resp = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json();

            if (structure === 'stock') {
                alert(`Bookmarked as Stock! Position: ${data.risk_calc.position_size} shares, R: ${data.risk_calc.r_multiple}`);
            } else {
                alert(`Bookmarked as ${structure.replace(/_/g, ' ')}! Contracts: ${data.options_analysis?.contracts || '?'}`);
            }
        } catch (err) {
            alert(`Bookmark failed: ${err.message}`);
        }
    });

    // ── Compare Structures ──
    document.getElementById('btn-compare-structures').addEventListener('click', async () => {
        if (!selectedResult) return;

        const entry = parseFloat(document.getElementById('rc-entry').value);
        const stop = parseFloat(document.getElementById('rc-stop').value);
        const target = parseFloat(document.getElementById('rc-target').value);

        if (isNaN(entry) || isNaN(stop) || isNaN(target)) {
            alert('Fill in entry, stop, and target first.');
            return;
        }

        const panel = document.getElementById('options-comparison');
        const loading = document.getElementById('options-loading');
        const cardsEl = document.getElementById('structure-cards');
        const warningsEl = document.getElementById('options-warnings');

        panel.classList.remove('hidden');
        loading.classList.remove('hidden');
        cardsEl.innerHTML = '';
        warningsEl.innerHTML = '';

        try {
            const resp = await fetch(`${SAPI}/options/compare`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticker: selectedResult.ticker,
                    entry_price: entry,
                    stop_loss: stop,
                    target_1: target,
                    scan_result_id: selectedResult.id,
                }),
            });
            const data = await resp.json();
            loading.classList.add('hidden');

            renderStructureCards(data.structures || [], data.recommendation);
            renderOptionsWarnings(data.warnings || []);
        } catch (err) {
            loading.classList.add('hidden');
            cardsEl.innerHTML = `<p class="negative">Failed to load options data: ${err.message}</p>`;
        }
    });

    function renderStructureCards(structures, recommendation) {
        const container = document.getElementById('structure-cards');
        container.innerHTML = '';

        if (!structures.length) {
            container.innerHTML = '<p style="color:var(--text-muted)">No structures available.</p>';
            return;
        }

        const bestType = recommendation?.best;

        structures.forEach(s => {
            const isBest = s.structure_type === bestType;
            const card = document.createElement('div');
            const scoreClass = s.score > 65 ? 'score-high' : s.score > 40 ? 'score-mid' : 'score-low';

            card.className = `structure-card ${isBest ? 'structure-best' : ''}`;
            card.innerHTML = `
                <div class="structure-header">
                    <span class="structure-name">${s.display_name}${isBest ? ' ★' : ''}</span>
                    <span class="structure-score ${scoreClass}">${s.score}</span>
                </div>
                <div class="structure-body">
                    <div class="struct-row"><span>Risk</span><span class="negative">$${fmtNum(s.max_risk)}</span></div>
                    <div class="struct-row"><span>Reward</span><span class="positive">$${s.max_reward != null ? fmtNum(s.max_reward) : '∞'}</span></div>
                    <div class="struct-row"><span>R:R</span><span>${s.risk_reward_ratio ? s.risk_reward_ratio.toFixed(1) + ':1' : '—'}</span></div>
                    <div class="struct-row"><span>Breakeven</span><span>${s.breakeven ? '$' + s.breakeven.toFixed(2) : '—'}</span></div>
                    <div class="struct-row"><span>Capital</span><span>$${fmtNum(s.capital_required)}</span></div>
                    ${s.contracts ? `<div class="struct-row"><span>${s.contract_size === 1 ? 'Shares' : 'Contracts'}</span><span>${s.contracts}</span></div>` : ''}
                    ${s.prob_profit != null ? `<div class="struct-row"><span>PoP</span><span>${(s.prob_profit * 100).toFixed(0)}%</span></div>` : ''}
                    ${s.prob_target != null ? `<div class="struct-row"><span>P(target)</span><span>${(s.prob_target * 100).toFixed(0)}%</span></div>` : ''}
                    ${s.position_theta ? `<div class="struct-row"><span>Θ/day</span><span class="${s.position_theta > 0 ? 'positive' : 'negative'}">$${s.position_theta.toFixed(2)}</span></div>` : ''}
                    ${s.position_delta ? `<div class="struct-row"><span>Δ</span><span>${s.position_delta.toFixed(0)}</span></div>` : ''}
                    ${s.dte != null ? `<div class="struct-row"><span>DTE</span><span>${s.dte}</span></div>` : ''}
                </div>
                ${s.legs && s.legs.length > 0 && s.structure_type !== 'stock' ? `
                <details class="structure-legs">
                    <summary>Leg Details</summary>
                    ${s.legs.map(l => `
                        <div class="leg-detail">
                            <span>${l.action.toUpperCase()} ${l.strike ? '$' + l.strike : ''} ${l.type}</span>
                            <span>@ $${l.price?.toFixed(2) || '?'} ${l.iv ? '(IV: ' + (l.iv * 100).toFixed(0) + '%)' : ''}</span>
                        </div>
                    `).join('')}
                </details>` : ''}
                ${s.score_rationale ? `<div class="structure-rationale">${s.score_rationale}</div>` : ''}
            `;
            container.appendChild(card);
        });
    }

    function renderOptionsWarnings(warnings) {
        const el = document.getElementById('options-warnings');
        if (!warnings.length) { el.innerHTML = ''; return; }
        el.innerHTML = warnings.map(w => `<div class="options-warning">${w}</div>`).join('');
    }

    function fmtNum(n) {
        if (n == null) return '—';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
        return n.toFixed(0);
    }

    // ── Strategies tab ──
    async function loadStrategies() {
        try {
            const resp = await fetch(`${SAPI}/strategies`);
            const data = await resp.json();
            const container = document.getElementById('strategies-list');
            container.innerHTML = '';

            data.forEach(s => {
                const card = document.createElement('div');
                card.className = 'strategy-card';
                card.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <h3>${s.name}</h3>
                        <span class="badge ${s.is_active ? 'badge-active' : 'badge-inactive'}">
                            ${s.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </div>
                    <p class="meta">${s.source || ''}</p>
                    <p>${s.description}</p>
                    <p class="params">${JSON.stringify(s.parameters, null, 1)}</p>
                `;
                // Toggle button
                const btn = document.createElement('button');
                btn.className = 'btn btn-small';
                btn.style.marginTop = '8px';
                btn.textContent = s.is_active ? 'Deactivate' : 'Activate';
                btn.addEventListener('click', async () => {
                    await fetch(`${SAPI}/strategies/${s.id}/toggle`, { method: 'PATCH' });
                    loadStrategies();
                });
                card.appendChild(btn);
                container.appendChild(card);
            });
        } catch (err) {
            console.error('Failed to load strategies:', err);
        }
    }

    // ── Watchlist tab ──
    async function loadWatchlist() {
        try {
            const resp = await fetch(`${SAPI}/candidates`);
            const data = await resp.json();
            const tbody = document.querySelector('#watchlist-table tbody');
            tbody.innerHTML = '';

            if (!data.length) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted)">No bookmarked candidates yet.</td></tr>';
                return;
            }

            data.forEach(c => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${c.ticker}</td>
                    <td>$${c.entry_price.toFixed(2)}</td>
                    <td>$${c.stop_loss.toFixed(2)}</td>
                    <td>$${c.target_1.toFixed(2)}</td>
                    <td>${c.r_multiple.toFixed(2)}R</td>
                    <td>${c.position_size}</td>
                    <td>$${(c.risk_per_share * c.position_size).toFixed(2)}</td>
                    <td>${c.status}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error('Failed to load watchlist:', err);
        }
    }

    // ── Settings tab ──
    async function loadSettings() {
        try {
            const resp = await fetch(`${SAPI}/settings/account`);
            const data = await resp.json();
            document.getElementById('set-account-size').value = data.account_size;
            document.getElementById('set-risk-pct').value = (data.risk_per_trade * 100).toFixed(1);
            document.getElementById('set-max-pos').value = data.max_positions;
        } catch (err) {
            console.error('Failed to load settings:', err);
        }
    }

    document.getElementById('btn-save-settings').addEventListener('click', async () => {
        const size = parseFloat(document.getElementById('set-account-size').value);
        const riskPct = parseFloat(document.getElementById('set-risk-pct').value) / 100;
        const maxPos = parseInt(document.getElementById('set-max-pos').value);

        try {
            await fetch(`${SAPI}/settings/account`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ account_size: size, risk_per_trade: riskPct, max_positions: maxPos }),
            });
            document.getElementById('settings-status').innerHTML =
                `<span style="color:var(--green)">Saved! Account: $${size.toLocaleString()}</span>`;
        } catch (err) {
            document.getElementById('settings-status').innerHTML =
                `<span class="negative">Save failed: ${err.message}</span>`;
        }
    });

    // ── Outcomes tab ──
    document.getElementById('btn-update-outcomes').addEventListener('click', async () => {
        const btn = document.getElementById('btn-update-outcomes');
        const status = document.getElementById('outcomes-status');

        btn.disabled = true;
        btn.textContent = 'Updating...';
        status.className = 'status-bar loading';
        status.textContent = 'Fetching forward prices for tracked outcomes...';

        try {
            const resp = await fetch(`${SAPI}/outcomes/update`, { method: 'POST' });
            const data = await resp.json();
            status.className = 'status-bar success';
            status.textContent = `Updated: ${data.updated}, Completed: ${data.completed}, Errors: ${data.errors}, Skipped: ${data.skipped}`;
            loadOutcomes();
        } catch (err) {
            status.className = 'status-bar error';
            status.textContent = `Update failed: ${err.message}`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Update Outcomes';
        }
    });

    document.getElementById('btn-filter-outcomes').addEventListener('click', () => loadOutcomeTable());

    async function loadOutcomes() {
        await Promise.all([loadEdgeSummary(), loadStrategyCards(), loadOutcomeTable()]);
    }

    async function loadEdgeSummary() {
        try {
            const resp = await fetch(`${SAPI}/analytics/edge`);
            const data = await resp.json();

            const badge = document.getElementById('edge-verdict-badge');
            badge.textContent = data.verdict.replace(/_/g, ' ');
            badge.className = 'badge ' + (data.verdict === 'POSITIVE_EDGE' ? 'badge-active' :
                data.verdict === 'NO_EDGE' ? 'badge-danger' : 'badge-inactive');

            const exp = document.getElementById('edge-expectancy');
            if (data.system_expectancy != null) {
                exp.textContent = (data.system_expectancy >= 0 ? '+' : '') + data.system_expectancy + 'R';
                exp.className = 'edge-big-number ' + (data.system_expectancy >= 0 ? 'positive' : 'negative');
            } else {
                exp.textContent = '—';
                exp.className = 'edge-big-number';
            }

            let detailsHtml = '';
            if (data.total_trades != null) {
                detailsHtml += `<span>Trades: ${data.total_trades}</span>`;
            }
            if (data.system_win_rate != null) {
                detailsHtml += `<span>Win Rate: ${(data.system_win_rate * 100).toFixed(1)}%</span>`;
            }
            if (data.best_strategy) {
                detailsHtml += `<span class="positive">Best: ${data.best_strategy.id} (${data.best_strategy.expectancy}R)</span>`;
            }
            if (data.worst_strategy) {
                detailsHtml += `<span class="negative">Worst: ${data.worst_strategy.id} (${data.worst_strategy.expectancy}R)</span>`;
            }
            if (data.regime_impact && data.regime_impact.recommendation) {
                detailsHtml += `<span>${data.regime_impact.recommendation}</span>`;
            }
            document.getElementById('edge-details').innerHTML = detailsHtml;
        } catch (err) {
            console.error('Failed to load edge summary:', err);
        }
    }

    async function loadStrategyCards() {
        try {
            const resp = await fetch(`${SAPI}/analytics`);
            const data = await resp.json();
            const container = document.getElementById('strategy-report-cards');
            container.innerHTML = '';

            if (!data.strategies || !data.strategies.length) {
                container.innerHTML = '<p style="color:var(--text-muted)">No strategy data yet. Run a scan and update outcomes to see analytics.</p>';
                return;
            }

            // Populate strategy filter
            const sel = document.getElementById('outcome-filter-strategy');
            sel.innerHTML = '<option value="">All</option>';
            data.strategies.forEach(s => {
                sel.innerHTML += `<option value="${s.strategy_id}">${s.strategy_id}</option>`;
            });

            data.strategies.forEach(s => {
                const card = document.createElement('div');
                const expClass = s.expectancy == null ? '' : s.expectancy > 0 ? 'card-positive' : 'card-negative';
                const confClass = s.confidence === 'HIGH' ? 'badge-active' :
                    s.confidence === 'MODERATE' ? 'badge-warning' :
                    s.confidence === 'LOW' ? 'badge-inactive' : 'badge-danger';

                card.className = `strategy-report-card ${expClass}`;
                card.innerHTML = `
                    <div class="card-header">
                        <h3>${s.strategy_id}</h3>
                        <span class="badge ${confClass}">${s.confidence}</span>
                    </div>
                    <div class="card-stats">
                        <div class="stat">
                            <span class="stat-value ${s.expectancy != null && s.expectancy >= 0 ? 'positive' : 'negative'}">${s.expectancy != null ? s.expectancy + 'R' : '—'}</span>
                            <span class="stat-label">Expectancy</span>
                        </div>
                        <div class="stat">
                            <span class="stat-value">${s.win_rate != null ? (s.win_rate * 100).toFixed(0) + '%' : '—'}</span>
                            <span class="stat-label">Win Rate</span>
                        </div>
                        <div class="stat">
                            <span class="stat-value">${s.avg_r_multiple != null ? s.avg_r_multiple + 'R' : '—'}</span>
                            <span class="stat-label">Avg R</span>
                        </div>
                        <div class="stat">
                            <span class="stat-value">${s.mfe_mae_ratio != null ? s.mfe_mae_ratio : '—'}</span>
                            <span class="stat-label">MFE/MAE</span>
                        </div>
                    </div>
                    <div class="card-meta">
                        <span>${s.tracked_outcomes} tracked / ${s.total_scans} total</span>
                        ${s.avg_return_day_5 != null ? '<span>Day 5: ' + (s.avg_return_day_5 >= 0 ? '+' : '') + s.avg_return_day_5 + '%</span>' : ''}
                    </div>
                `;
                container.appendChild(card);
            });
        } catch (err) {
            console.error('Failed to load strategy cards:', err);
        }
    }

    async function loadOutcomeTable() {
        const strategyId = document.getElementById('outcome-filter-strategy').value;
        const status = document.getElementById('outcome-filter-status').value;

        let url = `${SAPI}/outcomes?days_back=90`;
        if (strategyId) url += `&strategy_id=${strategyId}`;
        if (status) url += `&status=${status}`;

        try {
            const resp = await fetch(url);
            const data = await resp.json();
            const tbody = document.querySelector('#outcomes-table tbody');
            tbody.innerHTML = '';

            if (!data.length) {
                tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-muted)">No outcomes yet. Run a scan to create tracking records.</td></tr>';
                return;
            }

            data.forEach(o => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${o.entry_date || '—'}</td>
                    <td>${o.ticker}</td>
                    <td>${o.strategy_id}</td>
                    <td>$${o.entry_price ? o.entry_price.toFixed(2) : '—'}</td>
                    <td class="${returnClass(o.day5_return_pct)}">${fmtReturn(o.day5_return_pct)}</td>
                    <td class="${returnClass(o.day10_return_pct)}">${fmtReturn(o.day10_return_pct)}</td>
                    <td class="positive">${o.max_favorable_pct != null ? '+' + o.max_favorable_pct + '%' : '—'}</td>
                    <td class="negative">${o.max_adverse_pct != null ? '-' + o.max_adverse_pct + '%' : '—'}</td>
                    <td class="${returnClass(o.theoretical_r_multiple)}">${o.theoretical_r_multiple != null ? o.theoretical_r_multiple + 'R' : '—'}</td>
                    <td><span class="badge ${o.status === 'complete' ? 'badge-active' : o.status === 'partial' ? 'badge-warning' : o.status === 'error' ? 'badge-danger' : 'badge-inactive'}">${o.status}</span></td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error('Failed to load outcomes:', err);
        }
    }

    function fmtReturn(val) {
        if (val == null) return '—';
        return (val >= 0 ? '+' : '') + val.toFixed(2) + '%';
    }

    function returnClass(val) {
        if (val == null) return '';
        return val > 0 ? 'positive' : val < 0 ? 'negative' : '';
    }

    // ── Load last results on panel load ──
    loadFilteredResults();

})();
