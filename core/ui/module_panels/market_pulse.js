/* Market Pulse Module — Panel JS */

(function () {
    'use strict';

    const MAPI = '/api/market_pulse';

    // ── Load current data on panel open ──
    loadCurrent();

    // ── Refresh button ──
    document.getElementById('btn-refresh-pulse').addEventListener('click', async () => {
        const btn = document.getElementById('btn-refresh-pulse');
        const status = document.getElementById('pulse-status');

        btn.disabled = true;
        btn.textContent = 'Analyzing...';
        status.className = 'status-bar loading';
        status.textContent = 'Fetching intermarket data, computing breadth, analyzing sectors...';

        try {
            const resp = await fetch(`${MAPI}/refresh`, { method: 'POST' });
            const result = await resp.json();

            if (result.data) {
                renderPulse(result.data);
                status.className = 'status-bar success';
                status.textContent = `Analysis complete. Regime: ${result.data.regime}`;
            } else {
                status.className = 'status-bar error';
                status.textContent = 'Analysis returned no data.';
            }
        } catch (err) {
            status.className = 'status-bar error';
            status.textContent = `Analysis failed: ${err.message}`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Refresh';
        }
    });

    // ── Load current snapshot ──
    async function loadCurrent() {
        try {
            const resp = await fetch(`${MAPI}/current`);
            const result = await resp.json();
            if (result.data) {
                renderPulse(result.data);
                if (result.stale) {
                    const status = document.getElementById('pulse-status');
                    status.className = 'status-bar loading';
                    status.textContent = `Data is ${result.age_hours}h old. Consider refreshing.`;
                }
            }
        } catch (err) {
            console.error('Failed to load pulse data:', err);
        }
    }

    // ── Master render ──
    function renderPulse(data) {
        renderRegimeHeader(data);
        renderRatios(data.intermarket_data);
        renderVolatility(data.volatility_data);
        renderBreadth(data.breadth_data);
        renderSectors(data.sector_data);
        renderSignals(data.signals);
    }

    // ── Regime Header ──
    function renderRegimeHeader(data) {
        const badge = document.getElementById('regime-badge');
        badge.textContent = data.regime.replace('_', ' ');
        badge.className = 'regime-badge regime-' + data.regime.toLowerCase();

        document.getElementById('regime-score').textContent = (data.regime_score >= 0 ? '+' : '') + data.regime_score.toFixed(2);
        document.getElementById('regime-description').textContent = data.regime_description || '';

        const meta = document.getElementById('regime-meta');
        meta.innerHTML = `
            <span>IM: ${data.intermarket_score >= 0 ? '+' : ''}${data.intermarket_score.toFixed(2)}</span>
            <span>Breadth: ${data.breadth_score >= 0 ? '+' : ''}${data.breadth_score.toFixed(2)}</span>
            <span>Vol: ${data.volatility_score >= 0 ? '+' : ''}${data.volatility_score.toFixed(2)}</span>
            <span class="regime-date">${formatDate(data.snapshot_date)}</span>
        `;
    }

    // ── Intermarket Ratios ──
    function renderRatios(im) {
        if (!im || !im.ratios) return;
        const tbody = document.querySelector('#ratios-table tbody');
        tbody.innerHTML = '';

        const labels = {
            stocks_vs_bonds: 'Stocks vs Bonds',
            credit_stress: 'Credit Stress',
            growth_vs_value: 'Growth vs Value',
            copper_vs_gold: 'Copper vs Gold',
            intl_vs_us: 'Intl vs US',
            consumer_risk: 'Consumer Risk',
            inflation_expectations: 'Inflation Exp.',
            speculative_vs_defensive: 'Spec. vs Defensive',
        };

        for (const [key, ratio] of Object.entries(im.ratios)) {
            const tr = document.createElement('tr');
            const score = ratio.trend_score || 0;
            const arrow = score > 0 ? '\u25B2' : score < 0 ? '\u25BC' : '\u25CF';
            const cls = score > 0 ? 'positive' : score < 0 ? 'negative' : '';

            tr.innerHTML = `
                <td>${labels[key] || key}</td>
                <td class="mono">${ratio.pair || ''}</td>
                <td class="${cls}">${arrow}</td>
                <td class="${cls}">${score >= 0 ? '+' : ''}${score}</td>
            `;
            tbody.appendChild(tr);
        }
    }

    // ── Volatility ──
    function renderVolatility(vol) {
        if (!vol) return;

        document.getElementById('vix-level').textContent = vol.vix_level != null ? vol.vix_level.toFixed(1) : '--';
        document.getElementById('vix3m-level').textContent = vol.vix3m_level != null ? vol.vix3m_level.toFixed(1) : '--';
        document.getElementById('vix-ma50').textContent = vol.vix_ma_50 != null ? vol.vix_ma_50.toFixed(1) : '--';
        document.getElementById('vix-pct').textContent = vol.vix_percentile != null ? vol.vix_percentile.toFixed(0) + '%' : '--';

        const zoneBadge = document.getElementById('vix-zone');
        zoneBadge.textContent = vol.vix_zone;
        zoneBadge.className = 'badge vix-' + vol.vix_zone.toLowerCase();

        document.getElementById('term-structure').textContent = vol.term_structure + ' (' + vol.term_structure_ratio.toFixed(2) + ')';
        document.getElementById('vix-trend').textContent = vol.vix_trend;

        const contrarian = document.getElementById('vol-contrarian');
        if (vol.contrarian_signal) {
            contrarian.classList.remove('hidden');
            contrarian.textContent = vol.contrarian_signal === 'EXTREME_FEAR'
                ? 'CONTRARIAN BULLISH: Extreme fear + backwardation'
                : 'WARNING: Extreme complacency';
            contrarian.className = 'contrarian-alert ' +
                (vol.contrarian_signal === 'EXTREME_FEAR' ? 'contrarian-bullish' : 'contrarian-bearish');
        } else {
            contrarian.classList.add('hidden');
        }
    }

    // ── Breadth ──
    function renderBreadth(br) {
        if (!br) return;

        // Gauge bars
        setGauge('gauge-50dma', 'gauge-50dma-val', br.pct_above_50dma);
        setGauge('gauge-200dma', 'gauge-200dma-val', br.pct_above_200dma);

        // Stats
        const momentum = document.getElementById('breadth-momentum');
        momentum.textContent = br.breadth_momentum;
        momentum.className = br.breadth_momentum === 'EXPANDING' ? 'positive' : br.breadth_momentum === 'CONTRACTING' ? 'negative' : '';

        document.getElementById('new-highs').textContent = br.new_highs_50d;
        document.getElementById('new-lows').textContent = br.new_lows_50d;
        document.getElementById('hi-lo-ratio').textContent = br.hi_lo_ratio.toFixed(1);
        document.getElementById('breadth-score').textContent = (br.breadth_score >= 0 ? '+' : '') + br.breadth_score.toFixed(2);
        document.getElementById('total-stocks').textContent = br.total_stocks;

        // Thrust alert
        const thrust = document.getElementById('thrust-alert');
        if (br.thrust_signal) {
            thrust.classList.remove('hidden');
        } else {
            thrust.classList.add('hidden');
        }
    }

    function setGauge(barId, valId, pct) {
        const bar = document.getElementById(barId);
        const val = document.getElementById(valId);
        const clamped = Math.max(0, Math.min(100, pct));
        bar.style.width = clamped + '%';
        val.textContent = pct.toFixed(1) + '%';

        // Color: green if >60, red if <40, orange otherwise
        if (clamped > 60) bar.style.background = 'var(--green)';
        else if (clamped < 40) bar.style.background = 'var(--red)';
        else bar.style.background = 'var(--orange)';
    }

    // ── Sectors ──
    function renderSectors(sec) {
        if (!sec || !sec.rankings) return;

        const pattern = document.getElementById('rotation-pattern');
        pattern.textContent = (sec.rotation_pattern || 'MIXED').replace(/_/g, ' ');

        const tbody = document.querySelector('#sectors-table tbody');
        tbody.innerHTML = '';

        sec.rankings.forEach((s, i) => {
            const tr = document.createElement('tr');
            const retClass = (v) => v > 0 ? 'positive' : v < 0 ? 'negative' : '';
            const isLeader = sec.leaders && sec.leaders.includes(s.ticker);
            const isLaggard = sec.laggards && sec.laggards.includes(s.ticker);

            tr.className = isLeader ? 'sector-leader' : isLaggard ? 'sector-laggard' : '';
            tr.innerHTML = `
                <td>${i + 1}</td>
                <td><strong>${s.ticker}</strong> <span class="text-muted">${s.name}</span></td>
                <td class="${retClass(s.return_1w)}">${s.return_1w >= 0 ? '+' : ''}${s.return_1w.toFixed(1)}%</td>
                <td class="${retClass(s.return_1m)}">${s.return_1m >= 0 ? '+' : ''}${s.return_1m.toFixed(1)}%</td>
                <td class="${retClass(s.return_3m)}">${s.return_3m >= 0 ? '+' : ''}${s.return_3m.toFixed(1)}%</td>
                <td>${s.rs_vs_spy.toFixed(2)}x</td>
                <td class="${s.rs_trend === 'IMPROVING' ? 'positive' : s.rs_trend === 'DECLINING' ? 'negative' : ''}">${s.rs_trend}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    // ── Signals ──
    function renderSignals(signals) {
        const section = document.getElementById('signals-section');
        const list = document.getElementById('signals-list');

        if (!signals || signals.length === 0) {
            section.classList.add('hidden');
            return;
        }

        section.classList.remove('hidden');
        list.innerHTML = '';
        signals.forEach(s => {
            const li = document.createElement('li');
            li.className = 'signal-item';
            // Highlight important signals
            if (s.includes('CONTRARIAN') || s.includes('THRUST') || s.includes('WARNING')) {
                li.classList.add('signal-important');
            }
            li.textContent = s;
            list.appendChild(li);
        });
    }
})();
