const API_BASE = '/api';

let svg, g, simulation, link, node, label;
let currentZoom = d3.zoomIdentity;
let selectedNode = null;
let allNodes = new Map();
let allEdges = [];

const COLORS = {
    person: '#3b82f6',
    association: '#10b981',
    institution: '#f59e0b'
};

const SIZES = {
    person: 8,
    association: 16,
    institution: 24
};

async function init() {
    const container = document.getElementById('graph-container');
    const width = container.clientWidth;
    const height = container.clientHeight;
    
    svg = d3.select('#graph-svg')
        .attr('width', width)
        .attr('height', height);
    
    g = svg.append('g');
    
    // Zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
            currentZoom = event.transform;
            g.attr('transform', event.transform);
        });
    
    svg.call(zoom);
    
    // Setup controls
    document.getElementById('btn-zoom-in').onclick = () => {
        svg.transition().call(zoom.scaleBy, 1.3);
    };
    document.getElementById('btn-zoom-out').onclick = () => {
        svg.transition().call(zoom.scaleBy, 0.7);
    };
    document.getElementById('btn-reset').onclick = () => {
        svg.transition().call(zoom.transform, d3.zoomIdentity);
        loadInitialGraph();
    };
    
    // Search
    setupSearch();
    
    // Load stats
    loadStats();
    
    // Load initial graph (Ville de Paris neighborhood)
    loadInitialGraph();
    
    // Handle window resize
    window.addEventListener('resize', () => {
        const w = container.clientWidth;
        const h = container.clientHeight;
        svg.attr('width', w).attr('height', h);
        if (simulation) {
            simulation.force('center', d3.forceCenter(w / 2, h / 2));
            simulation.alpha(0.3).restart();
        }
    });
}

async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/stats`);
        const stats = await res.json();
        document.getElementById('stat-nodes').textContent = stats.total_nodes;
        document.getElementById('stat-edges').textContent = stats.total_edges;
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

async function loadInitialGraph() {
    document.getElementById('loading').style.display = 'block';
    try {
        // Load Paris city and its neighbors
        const res = await fetch(`${API_BASE}/graph/neighbors?node_id=inst_paris_ville&hops=1`);
        const data = await res.json();
        
        allNodes.clear();
        allEdges = [];
        
        data.nodes.forEach(n => allNodes.set(n.id, n));
        data.edges.forEach(e => allEdges.push(e));
        
        renderGraph(Array.from(allNodes.values()), allEdges);
        document.getElementById('loading').style.display = 'none';
    } catch (e) {
        console.error('Failed to load graph:', e);
        document.getElementById('loading').textContent = 'Erreur de chargement';
    }
}

async function expandNode(nodeId) {
    if (!nodeId) return;
    
    document.getElementById('loading').style.display = 'block';
    try {
        const res = await fetch(`${API_BASE}/graph/neighbors?node_id=${nodeId}&hops=1`);
        const data = await res.json();
        
        let added = false;
        
        data.nodes.forEach(n => {
            if (!allNodes.has(n.id)) {
                allNodes.set(n.id, n);
                added = true;
            }
        });
        
        data.edges.forEach(e => {
            const exists = allEdges.some(
                ex => (ex.source === e.source && ex.target === e.target) ||
                      (ex.source === e.target && ex.target === e.source)
            );
            if (!exists) {
                allEdges.push(e);
                added = true;
            }
        });
        
        if (added) {
            renderGraph(Array.from(allNodes.values()), allEdges);
        }
        
        document.getElementById('loading').style.display = 'none';
    } catch (e) {
        console.error('Failed to expand node:', e);
        document.getElementById('loading').style.display = 'none';
    }
}

function renderGraph(nodes, edges) {
    const container = document.getElementById('graph-container');
    const width = container.clientWidth;
    const height = container.clientHeight;
    
    // Process edges to use node objects
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const processedEdges = edges.map(e => ({
        source: nodeMap.get(e.source) || e.source,
        target: nodeMap.get(e.target) || e.target,
        ...e
    })).filter(e => {
        const s = typeof e.source === 'object' ? e.source.id : e.source;
        const t = typeof e.target === 'object' ? e.target.id : e.target;
        return nodeMap.has(s) && nodeMap.has(t);
    });
    
    // Clear previous
    g.selectAll('*').remove();
    
    // Create arrow marker
    g.append('defs').append('marker')
        .attr('id', 'arrowhead')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#475569');
    
    // Create simulation
    simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(processedEdges).id(d => d.id).distance(100))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => (SIZES[d.type] || 10) + 5));
    
    // Draw edges
    link = g.append('g')
        .selectAll('line')
        .data(processedEdges)
        .enter().append('line')
        .attr('stroke', '#475569')
        .attr('stroke-width', d => d.type === 'subsidizes' ? 2 : 1)
        .attr('stroke-opacity', 0.6)
        .attr('marker-end', d => d.type === 'member_of' ? null : 'url(#arrowhead)');
    
    // Draw nodes
    node = g.append('g')
        .selectAll('circle')
        .data(nodes)
        .enter().append('circle')
        .attr('r', d => SIZES[d.type] || 10)
        .attr('fill', d => COLORS[d.type] || '#94a3b8')
        .attr('stroke', '#0f172a')
        .attr('stroke-width', 2)
        .attr('cursor', 'pointer')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended))
        .on('click', (event, d) => {
            event.stopPropagation();
            selectNode(d);
        })
        .on('dblclick', (event, d) => {
            event.stopPropagation();
            expandNode(d.id);
        });
    
    // Draw labels
    label = g.append('g')
        .selectAll('text')
        .data(nodes)
        .enter().append('text')
        .text(d => d.name.length > 20 ? d.name.substring(0, 20) + '...' : d.name)
        .attr('font-size', d => d.type === 'institution' ? 14 : 10)
        .attr('font-weight', d => d.type === 'institution' ? 600 : 400)
        .attr('fill', '#e2e8f0')
        .attr('text-anchor', 'middle')
        .attr('dy', d => -(SIZES[d.type] || 10) - 8)
        .attr('pointer-events', 'none');
    
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        
        node
            .attr('cx', d => d.x)
            .attr('cy', d => d.y);
        
        label
            .attr('x', d => d.x)
            .attr('y', d => d.y);
    });
}

function selectNode(d) {
    selectedNode = d;
    
    // Highlight selected
    node.attr('stroke', n => n.id === d.id ? '#f8fafc' : '#0f172a')
        .attr('stroke-width', n => n.id === d.id ? 4 : 2);
    
    // Show info
    const info = document.getElementById('node-info');
    info.style.display = 'block';
    
    document.getElementById('info-name').textContent = d.name;
    document.getElementById('info-type').textContent = {
        person: 'Personne',
        association: 'Association',
        institution: 'Institution'
    }[d.type] || d.type;
    
    const budgetEl = document.getElementById('info-budget');
    if (d.total_budget) {
        budgetEl.textContent = new Intl.NumberFormat('fr-FR', {
            style: 'currency',
            currency: 'EUR',
            maximumFractionDigits: 0
        }).format(d.total_budget);
    } else {
        budgetEl.textContent = '—';
    }
    
    document.getElementById('info-role').textContent = d.role || '—';
    document.getElementById('info-source').textContent = d.source || '—';
}

function setupSearch() {
    const input = document.getElementById('search-input');
    const results = document.getElementById('search-results');
    let debounceTimer;
    
    input.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const query = e.target.value.trim();
        
        if (query.length < 2) {
            results.innerHTML = '';
            return;
        }
        
        debounceTimer = setTimeout(() => performSearch(query), 200);
    });
    
    // Hide results on click outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box')) {
            results.innerHTML = '';
        }
    });
}

async function performSearch(query) {
    const results = document.getElementById('search-results');
    
    try {
        const res = await fetch(`${API_BASE}/graph/search?q=${encodeURIComponent(query)}&limit=10`);
        const nodes = await res.json();
        
        results.innerHTML = nodes.map(n => `
            <div class="search-result" data-id="${n.id}">
                <div class="name">${escapeHtml(n.name)}</div>
                <div class="type">${n.type}</div>
            </div>
        `).join('');
        
        results.querySelectorAll('.search-result').forEach(el => {
            el.addEventListener('click', () => {
                const nodeId = el.dataset.id;
                const nodeData = allNodes.get(nodeId);
                if (nodeData) {
                    selectNode(nodeData);
                    // Center on node
                    const container = document.getElementById('graph-container');
                    svg.transition().duration(750).call(
                        d3.zoom().transform,
                        d3.zoomIdentity
                            .translate(container.clientWidth / 2, container.clientHeight / 2)
                            .scale(1.5)
                            .translate(-nodeData.x, -nodeData.y)
                    );
                } else {
                    // Node not in graph, fetch and add
                    expandNode(nodeId);
                }
                results.innerHTML = '';
            });
        });
    } catch (e) {
        console.error('Search failed:', e);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function switchPanel(panelId) {
    // Update tabs
    document.querySelectorAll('.nav-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.panel === panelId);
    });
    // Update panels
    document.querySelectorAll('.panel').forEach(p => {
        p.classList.toggle('active', p.id === panelId);
    });
    
    if (panelId === 'leaderboard-panel') loadLeaderboard();
    if (panelId === 'alerts-panel') loadAlerts();
}

async function loadLeaderboard() {
    const metric = document.getElementById('leaderboard-metric').value;
    const list = document.getElementById('leaderboard-list');
    list.innerHTML = '<div style="color:#64748b;text-align:center;padding:20px;">Chargement...</div>';
    
    try {
        const res = await fetch(`${API_BASE}/leaderboard?metric=${metric}&limit=30`);
        const data = await res.json();
        
        const metricLabels = {
            'conflict_score': 'Score',
            'total_subventions_controlled': '€',
            'board_count': 'CA'
        };
        
        list.innerHTML = data.map(p => `
            <div class="leaderboard-item" onclick="showPersonDetail('${p.id}')">
                <div style="display:flex;align-items:center;gap:12px;">
                    <div class="rank">${p.rank}</div>
                    <div style="flex:1;">
                        <div class="name">${escapeHtml(p.name)} ${p.is_membre_de_droit ? '<span class="badge badge-danger">membre de droit</span>' : ''}</div>
                        <div class="meta">${p.board_count} CA · €${(p.total_subventions_controlled||0).toLocaleString('fr-FR')}</div>
                    </div>
                    <div class="score">${metric === 'total_subventions_controlled' ? '€' + Math.round(p[metric]).toLocaleString('fr-FR') : p[metric]}</div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        list.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">Erreur de chargement</div>';
    }
}

async function loadAlerts() {
    const list = document.getElementById('alerts-list');
    list.innerHTML = '<div style="color:#64748b;text-align:center;padding:20px;">Chargement...</div>';
    
    try {
        const res = await fetch(`${API_BASE}/alerts`);
        const alerts = await res.json();
        
        list.innerHTML = alerts.slice(0, 20).map(a => `
            <div class="alert-item ${a.severity.toLowerCase()}" onclick="showPersonDetail('${a.person_id}')">
                <div class="alert-type">${a.type.replace(/_/g, ' ')}</div>
                <div class="alert-msg">${escapeHtml(a.message)}</div>
            </div>
        `).join('');
    } catch (e) {
        list.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">Erreur de chargement</div>';
    }
}

async function showPersonDetail(personId) {
    switchPanel('person-panel');
    const detail = document.getElementById('person-detail');
    detail.innerHTML = '<div style="color:#64748b;text-align:center;padding:20px;">Chargement...</div>';
    
    try {
        const res = await fetch(`${API_BASE}/person/${personId}`);
        const p = await res.json();
        
        const boardsHtml = p.boards && p.boards.length 
            ? p.boards.map(b => `
                <div class="board-item">
                    <div class="board-name">${escapeHtml(b.name)}</div>
                    <div class="board-role">${escapeHtml(b.role || '')} · ${b.siret || ''}</div>
                    <div class="board-amount">Subventions reçues: €${(b.subventions_received||0).toLocaleString('fr-FR')}</div>
                </div>
            `).join('')
            : '<div style="color:#64748b;font-size:0.875rem;">Aucun conseil d\'administration connu</div>';
        
        const coMembersHtml = p.co_members && p.co_members.length
            ? `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:8px;">` + 
              p.co_members.map(m => `<span style="padding:2px 8px;background:#334155;border-radius:12px;font-size:0.75rem;color:#e0e6ed;">${escapeHtml(m.name)}</span>`).join('') +
              `</div>`
            : '';
        
        detail.innerHTML = `
            <div class="detail-section">
                <div style="font-size:1.125rem;font-weight:600;color:#f8fafc;margin-bottom:4px;">${escapeHtml(p.name)}</div>
                <div style="font-size:0.875rem;color:#64748b;">${escapeHtml(p.role || '')}</div>
                ${p.is_membre_de_droit ? '<span class="badge badge-danger" style="margin-top:8px;">membre de droit</span>' : ''}
            </div>
            
            <div class="detail-section">
                <div class="section-title">Métriques</div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                    <div class="stat-card">
                        <div class="number">${p.conflict_score || 0}</div>
                        <div class="label">Score conflit</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">€${(p.total_subventions_controlled||0).toLocaleString('fr-FR')}</div>
                        <div class="label">Subventions contrôlées</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">${p.board_count || 0}</div>
                        <div class="label">Conseils</div>
                    </div>
                </div>
            </div>
            
            <div class="detail-section">
                <div class="section-title">Conseils d'administration (${p.boards ? p.boards.length : 0})</div>
                ${boardsHtml}
            </div>
            
            ${coMembersHtml ? `
            <div class="detail-section">
                <div class="section-title">Co-membres de CA</div>
                ${coMembersHtml}
            </div>
            ` : ''}
            
            <div style="margin-top:12px;">
                <button onclick="loadGraphForPerson('${p.id}')" style="width:100%;padding:10px;background:#3b82f6;border:none;border-radius:8px;color:#fff;cursor:pointer;font-size:0.875rem;font-weight:500;">Voir le réseau graphique</button>
            </div>
        `;
    } catch (e) {
        detail.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">Erreur de chargement</div>';
    }
}

async function loadGraphForPerson(personId) {
    switchPanel('graph-panel');
    document.getElementById('loading').style.display = 'block';
    
    try {
        // Clear and load person + 2-hop neighborhood
        allNodes.clear();
        allEdges = [];
        
        const res = await fetch(`${API_BASE}/graph/neighbors?node_id=${personId}&hops=2`);
        const data = await res.json();
        
        data.nodes.forEach(n => allNodes.set(n.id, n));
        data.edges.forEach(e => allEdges.push(e));
        
        renderGraph(Array.from(allNodes.values()), allEdges);
        document.getElementById('loading').style.display = 'none';
        
        // Show info for person
        const personNode = allNodes.get(personId);
        if (personNode) {
            selectNode(personNode);
        }
    } catch (e) {
        document.getElementById('loading').textContent = 'Erreur de chargement';
    }
}

function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

// Initialize
init();
