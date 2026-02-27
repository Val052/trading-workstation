/* Portfolio Module — Panel JS */

(function() {
    'use strict';

    const PAPI = '/api/portfolio';

    // State
    let holdings = [];
    let enrichedHoldings = [];
    let selectedHolding = null;
    let sortColumn = 'name';
    let sortAsc = true;
    let isEnriched = false;

    // ── Tab Navigation ──
    document.querySelectorAll('#portfolio-panel .module-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#portfolio-panel .module-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('#portfolio-panel .tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');

            if (tab.dataset.tab === 'analytics') loadAnalytics();
            if (tab.dataset.tab === 'snapshots') loadSnapshots();
        });
    });

    // ── Holdings: Load (fast, no enrichment) ──
    async function loadHoldings() {
        try {
            const resp = await fetch(`${PAPI}/holdings`);
            holdings = await resp.json();
            isEnriched = false;
            renderHoldings(holdings);
            updateSummaryBar(null);
        } catch (err) {
            setStatus('portfolio-status', 'error', `Failed to load holdings: ${err.message}`);
        }
    }

    // ── Holdings: Refresh Prices (full enrichment) ──
    document.getElementById('btn-refresh-prices').addEventListener('click', async () => {
        const btn = document.getElementById('btn-refresh-prices');
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
        setStatus('portfolio-status', 'loading', 'Fetching live prices (this may take a minute)...');

        try {
            const resp = await fetch(`${PAPI}/refresh`, { method: 'POST' });
            const data = await resp.json();
            enrichedHoldings = data.holdings || [];
            isEnriched = true;
            renderHoldings(enrichedHoldings);

            // Also fetch summary
            const summResp = await fetch(`${PAPI}/summary`);
            const summary = await summResp.json();
            updateSummaryBar(summary);

            setStatus('portfolio-status', 'success',
                `Refreshed ${data.refreshed_count} holdings in ${data.duration_seconds}s`);
        } catch (err) {
            setStatus('portfolio-status', 'error', `Refresh failed: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Refresh Prices';
        }
    });

    // ── Holdings: Take Snapshot ──
    document.getElementById('btn-take-snapshot').addEventListener('click', async () => {
        const btn = document.getElementById('btn-take-snapshot');
        btn.disabled = true;
        btn.textContent = 'Saving...';

        try {
            const resp = await fetch(`${PAPI}/snapshot`, { method: 'POST' });
            const data = await resp.json();
            setStatus('portfolio-status', 'success',
                `Snapshot saved: ${data.snapshot_date}, value: ${formatCurrency(data.total_value)}`);
        } catch (err) {
            setStatus('portfolio-status', 'error', `Snapshot failed: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Take Snapshot';
        }
    });

    // ── Render Holdings Table ──
    function renderHoldings(data) {
        const tbody = document.querySelector('#holdings-table tbody');
        tbody.innerHTML = '';

        if (!data.length) {
            tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;color:var(--text-muted)">No holdings. Use "Add Holding" to get started.</td></tr>';
            return;
        }

        // Sort
        const sorted = [...data].sort((a, b) => {
            let va = a[sortColumn], vb = b[sortColumn];
            if (va == null) va = '';
            if (vb == null) vb = '';
            if (typeof va === 'string') va = va.toLowerCase();
            if (typeof vb === 'string') vb = vb.toLowerCase();
            if (va < vb) return sortAsc ? -1 : 1;
            if (va > vb) return sortAsc ? 1 : -1;
            return 0;
        });

        sorted.forEach(h => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${h.name || h.ticker || h.instrument_id}</strong>${h.ticker && h.name !== h.ticker ? '<br><span style="font-size:11px;color:var(--text-muted)">' + h.ticker + '</span>' : ''}</td>
                <td>${h.asset_class || '--'}</td>
                <td>${h.shares != null ? h.shares : '--'}</td>
                <td>${h.current_price != null ? formatCurrency(h.current_price) : '--'}</td>
                <td>${h.market_value != null ? formatCurrency(h.market_value) : '--'}</td>
                <td class="${pnlClass(h.unrealized_pnl)}">${h.unrealized_pnl != null ? formatCurrency(h.unrealized_pnl) : '--'}</td>
                <td class="${pnlClass(h.unrealized_pnl_pct)}">${h.unrealized_pnl_pct != null ? formatPercent(h.unrealized_pnl_pct) : '--'}</td>
                <td class="${dmaClass(h.vs_50dma_pct)}">${h.vs_50dma_pct != null ? formatPercent(h.vs_50dma_pct) : '--'}</td>
                <td class="${dmaClass(h.vs_200dma_pct)}">${h.vs_200dma_pct != null ? formatPercent(h.vs_200dma_pct) : '--'}</td>
                <td>${h.rs_vs_spy != null ? h.rs_vs_spy : '--'}</td>
                <td>${renderTrend(h.trend)}</td>
                <td>${h.account_label || '--'}</td>
            `;
            tr.addEventListener('click', () => showHoldingDetail(h));
            tbody.appendChild(tr);
        });
    }

    // ── Column Sorting ──
    document.querySelectorAll('#holdings-table th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.sort;
            if (sortColumn === col) {
                sortAsc = !sortAsc;
            } else {
                sortColumn = col;
                sortAsc = true;
            }
            // Update header indicators
            document.querySelectorAll('#holdings-table th[data-sort]').forEach(h => {
                h.textContent = h.textContent.replace(/ [▲▼]$/, '');
            });
            th.textContent += sortAsc ? ' ▲' : ' ▼';
            renderHoldings(isEnriched ? enrichedHoldings : holdings);
        });
    });

    // ── Holding Detail ──
    function showHoldingDetail(h) {
        selectedHolding = h;
        const panel = document.getElementById('holding-detail');
        panel.classList.remove('hidden');

        document.getElementById('holding-detail-title').textContent =
            `${h.name || h.ticker} — ${h.ticker || ''}`;

        // Position info
        document.getElementById('holding-position-info').innerHTML = `
            <table>
                <tr><td>Shares</td><td>${h.shares}</td></tr>
                <tr><td>Cost Basis</td><td>${formatCurrency(h.cost_basis, h.cost_basis_currency)}</td></tr>
                <tr><td>Total Cost</td><td>${formatCurrency(h.shares * h.cost_basis, h.cost_basis_currency)}</td></tr>
                <tr><td>Currency</td><td>${h.cost_basis_currency || '--'}</td></tr>
                <tr><td>Account</td><td>${h.account_label || '--'}</td></tr>
                <tr><td>Asset Class</td><td>${h.asset_class || '--'}</td></tr>
                <tr><td>Date Acquired</td><td>${h.date_acquired || '--'}</td></tr>
                ${h.notes ? `<tr><td>Notes</td><td>${h.notes}</td></tr>` : ''}
            </table>
        `;

        // Market info
        document.getElementById('holding-market-info').innerHTML = `
            <table>
                <tr><td>Current Price</td><td>${h.current_price != null ? formatCurrency(h.current_price) : '--'}</td></tr>
                <tr><td>Market Value</td><td>${h.market_value != null ? formatCurrency(h.market_value) : '--'}</td></tr>
                ${h.market_value_eur ? `<tr><td>Value (EUR)</td><td>${formatCurrency(h.market_value_eur, 'EUR')}</td></tr>` : ''}
                <tr><td>Unrealized P&L</td><td class="${pnlClass(h.unrealized_pnl)}">${h.unrealized_pnl != null ? formatCurrency(h.unrealized_pnl) : '--'}</td></tr>
                <tr><td>P&L %</td><td class="${pnlClass(h.unrealized_pnl_pct)}">${h.unrealized_pnl_pct != null ? formatPercent(h.unrealized_pnl_pct) : '--'}</td></tr>
                <tr><td>Daily Change</td><td class="${pnlClass(h.daily_change_pct)}">${h.daily_change_pct != null ? formatPercent(h.daily_change_pct) : '--'}</td></tr>
                <tr><td>Sector</td><td>${h.sector || '--'}</td></tr>
            </table>
        `;

        // Technicals
        document.getElementById('holding-tech-info').innerHTML = `
            <table>
                <tr><td>vs 50 DMA</td><td class="${dmaClass(h.vs_50dma_pct)}">${h.vs_50dma_pct != null ? formatPercent(h.vs_50dma_pct) : '--'}</td></tr>
                <tr><td>vs 200 DMA</td><td class="${dmaClass(h.vs_200dma_pct)}">${h.vs_200dma_pct != null ? formatPercent(h.vs_200dma_pct) : '--'}</td></tr>
                <tr><td>50 DMA Slope</td><td>${h.dma50_slope || '--'}</td></tr>
                <tr><td>200 DMA Slope</td><td>${h.dma200_slope || '--'}</td></tr>
                <tr><td>RS vs SPY</td><td>${h.rs_vs_spy != null ? h.rs_vs_spy : '--'}</td></tr>
                <tr><td>52w Range</td><td>${h.range_52w_pct != null ? formatPercent(h.range_52w_pct) : '--'}</td></tr>
                <tr><td>ATR(14)</td><td>${h.atr_14 != null ? '$' + h.atr_14 : '--'}</td></tr>
                <tr><td>Trend</td><td>${renderTrend(h.trend)}</td></tr>
            </table>
        `;
    }

    document.getElementById('holding-detail-close').addEventListener('click', () => {
        document.getElementById('holding-detail').classList.add('hidden');
        selectedHolding = null;
    });

    // ── Edit Holding ──
    document.getElementById('btn-edit-holding').addEventListener('click', () => {
        if (!selectedHolding) return;
        const h = selectedHolding;

        const newShares = prompt('Shares:', h.shares);
        if (newShares === null) return;
        const newCost = prompt('Cost per share:', h.cost_basis);
        if (newCost === null) return;

        fetch(`${PAPI}/holdings/${h.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                shares: parseFloat(newShares),
                cost_basis: parseFloat(newCost),
            }),
        })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                setStatus('portfolio-status', 'error', data.error);
            } else {
                setStatus('portfolio-status', 'success', `Holding #${h.id} updated`);
                document.getElementById('holding-detail').classList.add('hidden');
                loadHoldings();
            }
        })
        .catch(err => setStatus('portfolio-status', 'error', err.message));
    });

    // ── Delete Holding ──
    document.getElementById('btn-delete-holding').addEventListener('click', () => {
        if (!selectedHolding) return;
        if (!confirm(`Remove ${selectedHolding.name || selectedHolding.ticker} from portfolio?`)) return;

        fetch(`${PAPI}/holdings/${selectedHolding.id}`, { method: 'DELETE' })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    setStatus('portfolio-status', 'error', data.error);
                } else {
                    setStatus('portfolio-status', 'success', `Holding removed`);
                    document.getElementById('holding-detail').classList.add('hidden');
                    selectedHolding = null;
                    loadHoldings();
                }
            })
            .catch(err => setStatus('portfolio-status', 'error', err.message));
    });

    // ── Summary Bar ──
    function updateSummaryBar(summary) {
        if (!summary) {
            document.getElementById('total-value').textContent = '--';
            document.getElementById('total-cost').textContent = '--';
            document.getElementById('total-pnl').textContent = '--';
            document.getElementById('total-pnl-pct').textContent = '--';
            document.getElementById('holdings-count').textContent = (isEnriched ? enrichedHoldings : holdings).length || '--';
            return;
        }

        document.getElementById('total-value').textContent = formatCurrency(summary.total_value);
        document.getElementById('total-cost').textContent = formatCurrency(summary.total_cost);

        const pnlEl = document.getElementById('total-pnl');
        pnlEl.textContent = formatCurrency(summary.total_pnl);
        pnlEl.className = 'metric-value ' + pnlClass(summary.total_pnl);

        const pnlPctEl = document.getElementById('total-pnl-pct');
        pnlPctEl.textContent = formatPercent(summary.total_pnl_pct);
        pnlPctEl.className = 'metric-value ' + pnlClass(summary.total_pnl_pct);

        document.getElementById('holdings-count').textContent = summary.holdings_count;
    }

    // ── Analytics Tab ──
    async function loadAnalytics() {
        setStatus('analytics-status', 'loading', 'Loading portfolio analytics...');
        try {
            const resp = await fetch(`${PAPI}/summary`);
            const summary = await resp.json();
            updateSummaryBar(summary);

            renderAllocation('alloc-asset-class', summary.allocation.by_asset_class);
            renderAllocation('alloc-sector', summary.allocation.by_sector);
            renderAllocation('alloc-account', summary.allocation.by_account);
            renderAllocation('alloc-currency', summary.allocation.by_currency);

            renderConcentration(summary.concentration);
            renderBreadth(summary.breadth);

            setStatus('analytics-status', 'success', 'Analytics loaded');
        } catch (err) {
            setStatus('analytics-status', 'error', `Failed: ${err.message}`);
        }
    }

    function renderAllocation(containerId, allocData) {
        const container = document.getElementById(containerId);
        if (!allocData || Object.keys(allocData).length === 0) {
            container.innerHTML = '<div style="color:var(--text-muted);font-size:13px">No data</div>';
            return;
        }

        const entries = Object.entries(allocData).sort((a, b) => b[1] - a[1]);
        const colors = ['var(--accent)', 'var(--green)', 'var(--orange)', 'var(--red)', '#a371f7', '#79c0ff', '#d2a8ff', '#7ee787'];

        let html = '';
        entries.forEach(([label, pct], idx) => {
            const color = colors[idx % colors.length];
            html += `
                <div class="alloc-row">
                    <div class="alloc-label">${label}</div>
                    <div class="alloc-bar-bg">
                        <div class="alloc-bar" style="width:${Math.min(pct, 100)}%;background:${color}"></div>
                    </div>
                    <div class="alloc-pct">${pct}%</div>
                </div>
            `;
        });
        container.innerHTML = html;
    }

    function renderConcentration(data) {
        if (!data) return;
        document.getElementById('concentration-info').innerHTML = `
            <table>
                <tr><td>Largest Position</td><td>${formatPercent(data.max_weight_pct, 1)}</td></tr>
                <tr><td>Top 5 Weight</td><td>${formatPercent(data.top5_weight_pct, 1)}</td></tr>
                <tr><td>Herfindahl Index</td><td>${data.herfindahl}</td></tr>
            </table>
        `;
    }

    function renderBreadth(data) {
        if (!data) return;
        document.getElementById('breadth-info').innerHTML = `
            <table>
                <tr><td>Above 50 DMA</td><td>${data.above_50dma} / ${data.marketable_count} (${formatPercent(data.pct_above_50dma, 1)})</td></tr>
                <tr><td>Above 200 DMA</td><td>${data.above_200dma} / ${data.marketable_count} (${formatPercent(data.pct_above_200dma, 1)})</td></tr>
            </table>
        `;
    }

    // ── Snapshots Tab ──
    async function loadSnapshots() {
        try {
            const resp = await fetch(`${PAPI}/snapshots`);
            const snapshots = await resp.json();
            const tbody = document.querySelector('#snapshots-table tbody');
            tbody.innerHTML = '';

            if (!snapshots.length) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No snapshots yet. Click "Take Snapshot" to save current state.</td></tr>';
                return;
            }

            snapshots.forEach(s => {
                const tr = document.createElement('tr');
                const pnl = s.total_pnl || 0;
                tr.innerHTML = `
                    <td>${s.snapshot_date}</td>
                    <td>${formatCurrency(s.total_value)}</td>
                    <td>${formatCurrency(s.total_cost)}</td>
                    <td class="${pnlClass(pnl)}">${formatCurrency(pnl)}</td>
                    <td>${s.created_at ? formatDate(s.created_at) : '--'}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error('Failed to load snapshots:', err);
        }
    }

    // ── Add Holding ──
    document.getElementById('btn-add-holding').addEventListener('click', async () => {
        const instrument = document.getElementById('input-instrument').value.trim();
        const shares = parseFloat(document.getElementById('input-shares').value);
        const cost = parseFloat(document.getElementById('input-cost').value);

        if (!instrument || isNaN(shares) || isNaN(cost)) {
            document.getElementById('add-holding-status').innerHTML =
                '<span class="negative">Fill in ticker/ISIN, shares, and cost basis.</span>';
            return;
        }

        const body = {
            instrument_input: instrument,
            shares: shares,
            cost_basis: cost,
            cost_basis_currency: document.getElementById('input-currency').value,
            asset_class: document.getElementById('input-asset-class').value,
            account_label: document.getElementById('input-account').value || 'default',
            name: document.getElementById('input-name').value || null,
            date_acquired: document.getElementById('input-date-acquired').value || null,
            notes: document.getElementById('input-notes').value || '',
        };

        const btn = document.getElementById('btn-add-holding');
        btn.disabled = true;
        btn.textContent = 'Adding...';

        try {
            const resp = await fetch(`${PAPI}/holdings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json();

            if (data.error) {
                document.getElementById('add-holding-status').innerHTML =
                    `<span class="negative">${data.error}</span>`;
            } else {
                document.getElementById('add-holding-status').innerHTML =
                    `<span class="positive">Added: ${data.name} (${data.ticker})</span>`;
                // Clear form
                document.getElementById('input-instrument').value = '';
                document.getElementById('input-name').value = '';
                document.getElementById('input-shares').value = '';
                document.getElementById('input-cost').value = '';
                document.getElementById('input-notes').value = '';
                document.getElementById('input-date-acquired').value = '';
                // Refresh holdings
                loadHoldings();
            }
        } catch (err) {
            document.getElementById('add-holding-status').innerHTML =
                `<span class="negative">Failed: ${err.message}</span>`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Add Holding';
        }
    });

    // ── Helper Functions ──

    function setStatus(elementId, type, message) {
        const el = document.getElementById(elementId);
        if (!el) return;
        el.className = 'status-bar ' + type;
        el.textContent = message;
    }

    function pnlClass(value) {
        if (value == null) return '';
        return value > 0 ? 'positive' : value < 0 ? 'negative' : '';
    }

    function dmaClass(value) {
        if (value == null) return '';
        return value > 0 ? 'positive' : 'negative';
    }

    function renderTrend(trend) {
        if (!trend || trend === 'N/A' || trend === 'No data') return '<span style="color:var(--text-muted)">--</span>';
        const colors = { bullish: 'var(--green)', bearish: 'var(--red)', neutral: 'var(--orange)' };
        return `<span style="color:${colors[trend] || 'var(--text-muted)'}">${trend}</span>`;
    }

    // ── Initialize ──
    loadHoldings();

})();
