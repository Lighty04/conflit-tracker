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
