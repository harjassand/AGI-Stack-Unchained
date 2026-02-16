/**
 * Mission Control v18.0 - Frontend Application
 * 
 * Vanilla JavaScript for API integration and panel rendering.
 */

// =============================================================================
// State
// =============================================================================

let currentRunId = null;
let eventRefreshInterval = null;

// =============================================================================
// API Helpers
// =============================================================================

async function apiGet(path) {
    const response = await fetch(path);
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

// =============================================================================
// Formatting Helpers
// =============================================================================

function formatHash(hash, maxLen = 16) {
    if (!hash) return '—';
    if (hash.startsWith('sha256:')) {
        const hex = hash.slice(7);
        return `sha256:${hex.slice(0, maxLen)}…`;
    }
    return hash.length > maxLen ? `${hash.slice(0, maxLen)}…` : hash;
}

function formatNumber(num) {
    if (num === null || num === undefined) return '—';
    return num.toLocaleString();
}

function formatRatio(num, den) {
    if (num === null || num === undefined || den === null || den === undefined) return '—';
    if (den === 0) return '0.00';
    return (num / den).toFixed(4);
}

function formatTimestamp(isoStr) {
    if (!isoStr) return '—';
    try {
        const date = new Date(isoStr);
        return date.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
    } catch {
        return isoStr;
    }
}

function createBadge(text, type) {
    const span = document.createElement('span');
    span.className = `badge badge-${type}`;
    span.textContent = text;
    return span;
}

function createTypeBadge(type) {
    if (type === 'OMEGA_V4_0') {
        return createBadge('Omega v4.0', 'omega');
    } else if (type === 'SAS_VAL_V17_0') {
        return createBadge('SAS-VAL v17.0', 'sasval');
    }
    return createBadge(type, 'info');
}

function createHealthBadge(health) {
    if (health === 'OK') {
        return createBadge('OK', 'ok');
    }
    return createBadge('MISSING', 'missing');
}

function createGateBadge(pass) {
    if (pass === true) return createBadge('PASS', 'pass');
    if (pass === false) return createBadge('FAIL', 'fail');
    return '—';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// Run Chooser
// =============================================================================

async function fetchRuns() {
    const loading = document.getElementById('runs-loading');
    const tableContainer = document.getElementById('runs-table-container');
    const emptyState = document.getElementById('runs-empty');
    const tbody = document.getElementById('runs-table-body');
    const runsRootPath = document.getElementById('runs-root-path');
    
    loading.style.display = 'flex';
    tableContainer.style.display = 'none';
    emptyState.style.display = 'none';
    
    try {
        const data = await apiGet('/api/v1/runs');
        
        runsRootPath.textContent = data.runs_root || '';
        
        if (!data.runs || data.runs.length === 0) {
            loading.style.display = 'none';
            emptyState.style.display = 'block';
            return;
        }
        
        tbody.innerHTML = '';
        
        for (const run of data.runs) {
            const tr = document.createElement('tr');
            tr.className = 'clickable';
            tr.onclick = () => showRunDetail(run.run_id);
            
            // Run ID
            const tdId = document.createElement('td');
            tdId.textContent = run.run_id;
            tr.appendChild(tdId);
            
            // Types
            const tdTypes = document.createElement('td');
            const typeBadges = document.createElement('div');
            typeBadges.className = 'type-badges';
            for (const type of run.detected_types || []) {
                typeBadges.appendChild(createTypeBadge(type));
            }
            tdTypes.appendChild(typeBadges);
            tr.appendChild(tdTypes);
            
            // Last Seen
            const tdLastSeen = document.createElement('td');
            tdLastSeen.textContent = formatTimestamp(run.last_seen_utc);
            tr.appendChild(tdLastSeen);
            
            // Health
            const tdHealth = document.createElement('td');
            tdHealth.appendChild(createHealthBadge(run.health));
            tr.appendChild(tdHealth);
            
            tbody.appendChild(tr);
        }
        
        loading.style.display = 'none';
        tableContainer.style.display = 'block';
        
    } catch (error) {
        console.error('Failed to fetch runs:', error);
        loading.innerHTML = `<span style="color: var(--status-fail);">Error: ${escapeHtml(error.message)}</span>`;
    }
}

function showRunChooser() {
    stopEventRefresh();
    currentRunId = null;
    
    document.getElementById('page-runs').style.display = 'block';
    document.getElementById('page-detail').style.display = 'none';
    
    // Update URL
    history.pushState(null, '', '/');
    
    fetchRuns();
}

// =============================================================================
// Run Detail
// =============================================================================

async function showRunDetail(runId) {
    currentRunId = runId;
    
    document.getElementById('page-runs').style.display = 'none';
    document.getElementById('page-detail').style.display = 'block';
    document.getElementById('detail-run-id').textContent = runId;
    
    // Update URL
    history.pushState(null, '', `/?run=${encodeURIComponent(runId)}`);
    
    try {
        const data = await apiGet(`/api/v1/runs/${encodeURIComponent(runId)}/snapshot`);
        
        // Update type badges
        const typesContainer = document.getElementById('detail-types');
        typesContainer.innerHTML = '';
        for (const type of data.detected_types || []) {
            typesContainer.appendChild(createTypeBadge(type));
        }
        
        // Show/hide tabs based on detected types
        const hasOmega = (data.detected_types || []).includes('OMEGA_V4_0');
        const hasSasVal = (data.detected_types || []).includes('SAS_VAL_V17_0');
        
        document.getElementById('tab-omega').style.display = hasOmega ? 'block' : 'none';
        document.getElementById('tab-sasval').style.display = hasSasVal ? 'block' : 'none';
        
        // Activate first available tab
        if (hasOmega) {
            activateTab('omega');
        } else if (hasSasVal) {
            activateTab('sasval');
        }
        
        // Render Omega data
        if (hasOmega && data.omega) {
            renderOmegaData(data.omega);
            startEventRefresh();
        }
        
        // Render SAS-VAL data
        if (hasSasVal && data.sas_val) {
            renderSasValData(data.sas_val);
        }
        
    } catch (error) {
        console.error('Failed to fetch snapshot:', error);
        document.getElementById('detail-types').innerHTML = 
            `<span style="color: var(--status-fail);">Error: ${escapeHtml(error.message)}</span>`;
    }
}

// =============================================================================
// Tab Management
// =============================================================================

function activateTab(tabName) {
    // Update tab styling
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    
    // Show correct content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `content-${tabName}`);
    });
}

// Tab click handlers
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
        e.preventDefault();
        activateTab(tab.dataset.tab);
    });
});

// =============================================================================
// Omega Rendering
// =============================================================================

function renderOmegaData(omega) {
    // Current Focus
    const focus = omega.current_focus || {};
    const focusState = focus.focus_state || 'UNKNOWN';
    const focusDot = document.querySelector('#omega-focus .focus-dot');
    focusDot.className = `focus-dot ${focusState.toLowerCase().replace('_', '-')}`;
    
    document.getElementById('omega-focus-state').textContent = focusState.replace(/_/g, ' ');
    document.getElementById('omega-focus-detail').textContent = `Last: ${focus.last_event_type || '—'}`;
    document.getElementById('omega-last-epoch').textContent = formatNumber(focus.last_epoch_index);
    document.getElementById('omega-last-hash').textContent = formatHash(focus.last_event_ref_hash, 24);
    document.getElementById('omega-last-hash').title = focus.last_event_ref_hash || '';
    
    // Performance Metrics
    const metrics = omega.performance_metrics || {};
    document.getElementById('omega-checkpoint-label').textContent = 
        metrics.checkpoint_index !== undefined ? `Checkpoint #${metrics.checkpoint_index}` : 'from latest checkpoint';
    document.getElementById('omega-tasks-attempted').textContent = formatNumber(metrics.tasks_attempted);
    document.getElementById('omega-tasks-passed').textContent = formatNumber(metrics.tasks_passed);
    document.getElementById('omega-compute').textContent = formatNumber(metrics.compute_used_total);
    document.getElementById('omega-accel-windows').textContent = formatNumber(metrics.accel_consecutive_windows);
    document.getElementById('omega-accel-ratio').textContent = formatRatio(metrics.accel_ratio_num, metrics.accel_ratio_den);
    document.getElementById('omega-meta-epoch').textContent = formatNumber(metrics.meta_epoch_index);
    
    // Ignition Status
    const ignition = omega.ignition_status;
    const ignitionContainer = document.getElementById('omega-ignition');
    if (ignition) {
        ignitionContainer.innerHTML = `
            <div class="metrics-grid">
                <div class="metric">
                    <span class="metric-label">Trigger Checkpoint</span>
                    <span class="metric-value">${formatNumber(ignition.trigger_checkpoint_index)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">New Solves</span>
                    <span class="metric-value">${formatNumber(ignition.new_solves_over_baseline)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Passrate Gain</span>
                    <span class="metric-value">${formatRatio(ignition.passrate_gain_num, ignition.passrate_gain_den)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Accel Ratio</span>
                    <span class="metric-value">${formatRatio(ignition.accel_ratio_num, ignition.accel_ratio_den)}</span>
                </div>
            </div>
        `;
    } else {
        ignitionContainer.innerHTML = '<div class="empty-state"><p>No ignition detected</p></div>';
    }
    
    // Verified Discoveries (Promotions)
    const promotions = omega.verified_discoveries || [];
    document.getElementById('omega-promotion-count').textContent = promotions.length;
    const promotionsBody = document.getElementById('omega-promotions-body');
    promotionsBody.innerHTML = '';
    
    for (const p of promotions.slice(-20).reverse()) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${formatNumber(p.epoch_index)}</td>
            <td class="hash" title="${escapeHtml(p.proposal_id)}">${escapeHtml(formatHash(p.proposal_id))}</td>
            <td class="hash" title="${escapeHtml(p.promotion_bundle_id)}">${escapeHtml(formatHash(p.promotion_bundle_id))}</td>
            <td>${escapeHtml(p.meta_core_verdict || '—')}</td>
        `;
        promotionsBody.appendChild(tr);
    }
    
    if (promotions.length === 0) {
        promotionsBody.innerHTML = '<tr><td colspan="4" class="empty-state">No promotions yet</td></tr>';
    }
    
    // Proposals Emit
    const proposalsEmit = omega.proposals_emit || [];
    const emitBody = document.getElementById('omega-proposals-emit-body');
    emitBody.innerHTML = '';
    
    for (const p of proposalsEmit.slice(-10).reverse()) {
        const triggers = (p.trigger_failed_task_ids || []).length;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${formatNumber(p.epoch_index)}</td>
            <td class="hash" title="${escapeHtml(p.proposal_id)}">${escapeHtml(formatHash(p.proposal_id))}</td>
            <td>${escapeHtml(p.proposal_kind || '—')}</td>
            <td>${triggers}</td>
        `;
        emitBody.appendChild(tr);
    }
    
    if (proposalsEmit.length === 0) {
        emitBody.innerHTML = '<tr><td colspan="4" class="empty-state">No proposals emitted</td></tr>';
    }
    
    // Proposals Eval
    const proposalsEval = omega.proposals_eval || [];
    const evalBody = document.getElementById('omega-proposals-eval-body');
    evalBody.innerHTML = '';
    
    for (const p of proposalsEval.slice(-10).reverse()) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${formatNumber(p.epoch_index)}</td>
            <td class="hash" title="${escapeHtml(p.proposal_id)}">${escapeHtml(formatHash(p.proposal_id))}</td>
            <td>${escapeHtml(p.decision || '—')}</td>
            <td>${formatRatio(p.delta_score_num, p.delta_score_den)}</td>
            <td>${escapeHtml(p.reason || '—')}</td>
        `;
        evalBody.appendChild(tr);
    }
    
    if (proposalsEval.length === 0) {
        evalBody.innerHTML = '<tr><td colspan="5" class="empty-state">No evaluations yet</td></tr>';
    }
    
    // Event Stream
    renderEventStream(omega.event_stream || [], omega.event_count || 0);
}

function renderEventStream(events, totalCount) {
    document.getElementById('omega-event-count').textContent = `(${formatNumber(totalCount)} events)`;
    
    const eventsBody = document.getElementById('omega-events-body');
    eventsBody.innerHTML = '';
    
    for (const e of events) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${formatNumber(e.epoch_index)}</td>
            <td>${escapeHtml(e.event_type)}</td>
            <td>${escapeHtml(e.payload_summary)}</td>
        `;
        eventsBody.appendChild(tr);
    }
    
    if (events.length === 0) {
        eventsBody.innerHTML = '<tr><td colspan="3" class="empty-state">No events</td></tr>';
    }
    
    // Scroll to bottom to show newest events
    const container = eventsBody.closest('.table-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

// =============================================================================
// SAS-VAL Rendering
// =============================================================================

function renderSasValData(sasVal) {
    // VAL Gates
    const gates = sasVal.val_gates || {};
    document.getElementById('sasval-bundle-id').textContent = formatHash(gates.bundle_id, 20);
    document.getElementById('sasval-bundle-id').title = gates.bundle_id || '';
    document.getElementById('sasval-cycles-baseline').textContent = formatNumber(gates.val_cycles_baseline);
    document.getElementById('sasval-cycles-candidate').textContent = formatNumber(gates.val_cycles_candidate);
    
    // Gate badges
    const gateValcycles = document.getElementById('sasval-gate-valcycles');
    const gateWallclock = document.getElementById('sasval-gate-wallclock');
    const gateWork = document.getElementById('sasval-gate-work');
    
    gateValcycles.innerHTML = '';
    gateWallclock.innerHTML = '';
    gateWork.innerHTML = '';
    
    const vcBadge = createGateBadge(gates.valcycles_gate_pass);
    const wcBadge = createGateBadge(gates.wallclock_gate_pass);
    const wkBadge = createGateBadge(gates.work_conservation_pass);
    
    if (vcBadge instanceof Element) gateValcycles.appendChild(vcBadge);
    else gateValcycles.textContent = vcBadge;
    
    if (wcBadge instanceof Element) gateWallclock.appendChild(wcBadge);
    else gateWallclock.textContent = wcBadge;
    
    if (wkBadge instanceof Element) gateWork.appendChild(wkBadge);
    else gateWork.textContent = wkBadge;
    
    // Hotloops
    const hotloops = sasVal.hotloops || {};
    document.getElementById('sasval-pilot-loop').textContent = hotloops.pilot_loop_id || '—';
    document.getElementById('sasval-dominant-loop').textContent = hotloops.dominant_loop_id || '—';
    
    const hotloopsBody = document.getElementById('sasval-hotloops-body');
    hotloopsBody.innerHTML = '';
    
    const topLoops = hotloops.top_loops || [];
    for (const loop of topLoops) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(loop.loop_id || '—')}</td>
            <td>${formatNumber(loop.iters)}</td>
            <td>${formatNumber(loop.bytes)}</td>
            <td>${formatNumber(loop.ops_add)}</td>
            <td>${formatNumber(loop.ops_mul)}</td>
            <td>${formatNumber(loop.ops_load)}</td>
            <td>${formatNumber(loop.ops_store)}</td>
        `;
        hotloopsBody.appendChild(tr);
    }
    
    if (topLoops.length === 0) {
        hotloopsBody.innerHTML = '<tr><td colspan="7" class="empty-state">No hotloop data</td></tr>';
    }
}

// =============================================================================
// Event Stream Auto-Refresh
// =============================================================================

function startEventRefresh() {
    stopEventRefresh();
    
    if (!currentRunId) return;
    
    eventRefreshInterval = setInterval(async () => {
        if (!currentRunId) {
            stopEventRefresh();
            return;
        }
        
        try {
            const data = await apiGet(`/api/v1/runs/${encodeURIComponent(currentRunId)}/snapshot`);
            if (data.omega) {
                renderEventStream(data.omega.event_stream || [], data.omega.event_count || 0);
                
                // Update focus state
                const focus = data.omega.current_focus || {};
                const focusState = focus.focus_state || 'UNKNOWN';
                const focusDot = document.querySelector('#omega-focus .focus-dot');
                focusDot.className = `focus-dot ${focusState.toLowerCase().replace('_', '-')}`;
                document.getElementById('omega-focus-state').textContent = focusState.replace(/_/g, ' ');
                document.getElementById('omega-focus-detail').textContent = `Last: ${focus.last_event_type || '—'}`;
            }
        } catch (error) {
            console.error('Event refresh failed:', error);
        }
    }, 1000);
}

function stopEventRefresh() {
    if (eventRefreshInterval) {
        clearInterval(eventRefreshInterval);
        eventRefreshInterval = null;
    }
}

// =============================================================================
// URL Routing
// =============================================================================

function handleRoute() {
    const params = new URLSearchParams(window.location.search);
    const runId = params.get('run');
    
    if (runId) {
        showRunDetail(runId);
    } else {
        showRunChooser();
    }
}

// Handle browser back/forward
window.addEventListener('popstate', handleRoute);

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    handleRoute();
});
