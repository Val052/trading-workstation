/* Trading Terminal — Shell JS: module routing, sidebar nav, shared utilities */

const API = '';
let currentModuleId = null;

// ── Module Discovery & Navigation ──

async function initShell() {
    try {
        const resp = await fetch(`${API}/api/modules`);
        const modules = await resp.json();
        renderSidebar(modules);

        // Auto-load the first module
        if (modules.length > 0) {
            loadModule(modules[0].id);
        }
    } catch (err) {
        console.error('Failed to load modules:', err);
        document.getElementById('content-area').innerHTML =
            '<div class="welcome-screen"><h1>Connection Error</h1><p>Could not reach the server.</p></div>';
    }
}

function renderSidebar(modules) {
    const nav = document.getElementById('module-nav');
    nav.innerHTML = '';
    modules.forEach(mod => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = '#';
        a.className = 'nav-link';
        a.dataset.moduleId = mod.id;
        a.innerHTML = `<span class="module-icon">${getIcon(mod.icon)}</span> ${mod.name}`;
        a.addEventListener('click', (e) => {
            e.preventDefault();
            loadModule(mod.id);
        });
        li.appendChild(a);
        nav.appendChild(li);
    });
}

function getIcon(iconName) {
    const icons = {
        'radar': '\u25CE',       // Scanner
        'briefcase': '\u25A0',   // Portfolio
        'chart': '\u25B2',       // Charts
        'book': '\u25A3',        // Journal
    };
    return icons[iconName] || '\u25CF';
}

async function loadModule(moduleId) {
    // Update sidebar active state
    document.querySelectorAll('.nav-link').forEach(a => {
        a.classList.toggle('active', a.dataset.moduleId === moduleId);
    });

    currentModuleId = moduleId;
    const area = document.getElementById('content-area');

    try {
        // Fetch panel HTML
        const htmlResp = await fetch(`/panels/${moduleId}.html`);
        if (!htmlResp.ok) {
            area.innerHTML = `<div class="welcome-screen"><h1>Module not found</h1><p>No panel for "${moduleId}"</p></div>`;
            return;
        }
        area.innerHTML = await htmlResp.text();

        // Remove old module script
        const old = document.getElementById('module-script');
        if (old) old.remove();

        // Load module JS
        const script = document.createElement('script');
        script.id = 'module-script';
        script.src = `/panels/${moduleId}.js?t=${Date.now()}`;
        document.body.appendChild(script);
    } catch (err) {
        console.error(`Failed to load module ${moduleId}:`, err);
        area.innerHTML = `<div class="welcome-screen"><h1>Load Error</h1><p>${err.message}</p></div>`;
    }
}

// ── Shared Utilities (available to all module JS) ──

function formatCurrency(value, currency = 'USD') {
    if (value == null || isNaN(value)) return '--';
    const symbol = currency === 'EUR' ? '\u20AC' : '$';
    return `${symbol}${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPercent(value, decimals = 2) {
    if (value == null || isNaN(value)) return '--';
    return `${Number(value).toFixed(decimals)}%`;
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

async function fetchAPI(path, options = {}) {
    const resp = await fetch(`${API}${path}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    return resp.json();
}

// ── Initialize ──
initShell();
