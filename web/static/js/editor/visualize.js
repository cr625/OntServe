        // Global variables
        let cy; // Cytoscape instance
        let ontologyData;
        let currentEntityData;
        let originalElements; // Store original elements for filtering
        let hidePropertyNodes = false; // Classes Only quick filter state
        const ontologyId = window.VISUALIZE.ontologyId;

        // Use hierarchical layout by default for hierarchical ontologies
        const isHierarchicalOntology = ontologyId.includes('prov-o') || ontologyId.includes('bfo');
        let currentLayout = isHierarchicalOntology ? 'dagre' : 'cose';

        // Initialize button text on page load
        document.addEventListener('DOMContentLoaded', function () {
            // Simple initialization without template expressions
        });

        function overlayInferredEdges(data) {
            // Fold inferred relations into originalElements (marked 'inferred')
            // so the Show Inferred Relations filter governs them, then re-apply
            // filters. Only relations whose endpoints are on the graph render.
            if (!originalElements) return 0;
            originalElements = originalElements.filter(el =>
                !(el.group === 'edges' && el.data && el.data.is_inferred));
            const nodeIds = new Set(originalElements
                .filter(el => el.group === 'nodes').map(el => el.data.id));
            let added = 0;
            (data.inferred_subclasses || []).forEach((rel, i) => {
                if (nodeIds.has(rel.child) && nodeIds.has(rel.parent)) {
                    originalElements.push({
                        group: 'edges',
                        data: {
                            id: `inferred_sub_${i}`,
                            source: rel.child,
                            target: rel.parent,
                            type: 'subClassOf',
                            is_inferred: true
                        },
                        classes: 'inferred'
                    });
                    added++;
                }
            });
            (data.inferred_types || []).forEach((rel, i) => {
                if (nodeIds.has(rel.individual) && nodeIds.has(rel.type)) {
                    originalElements.push({
                        group: 'edges',
                        data: {
                            id: `inferred_type_${i}`,
                            source: rel.individual,
                            target: rel.type,
                            type: 'rdf:type',
                            is_inferred: true
                        },
                        classes: 'inferred'
                    });
                    added++;
                }
            });
            if (added > 0) applyFilters();
            return added;
        }

        function runInference() {
            const button = document.getElementById('inferenceBtn');
            const originalText = button.innerHTML;
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Running Inference...';

            // Read-only merged-graph Pellet run (shared reasoning harness).
            fetch(`/editor/api/simple/reasoning/${ontologyId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ reasoner_type: 'pellet' })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        let message = `${data.message}\n\n`;
                        message += `📊 Results:\n`;
                        message += `• Consistent: ${data.consistent ? 'yes' : 'NO'}\n`;
                        message += `• ${data.inferred_subclass_count || 0} inferred subclass relations\n`;
                        message += `• ${data.inferred_type_count || 0} inferred type assertions\n`;

                        if ((data.nothing_entities || []).length > 0) {
                            message += `\n⚠️ ${data.nothing_entities.length} entities forced to owl:Nothing (disjointness violations):\n`;
                            data.nothing_entities.slice(0, 5).forEach(uri => {
                                message += `• ${uri}\n`;
                            });
                        }
                        if (!data.consistent && data.error_explanation) {
                            message += `\n⚠️ ${data.error_explanation}\n`;
                        }

                        const overlaid = overlayInferredEdges(data);
                        if (overlaid > 0) {
                            message += `\n🟢 ${overlaid} inferred relations overlaid on the graph `;
                            message += `(green dashed; toggle "Show Inferred Relations").\n`;
                        }
                        if (data.truncated) {
                            message += `\nResult lists were truncated by the server cap.\n`;
                        }
                        if (data.note) {
                            message += `\n${data.note}\n`;
                        }

                        showInferenceResultsModal(data, message);
                    } else {
                        showInferenceErrorModal(data.error || 'Unknown error');
                    }
                })
                .catch(error => {
                    console.error('Inference error:', error);
                    alert('Inference failed. Check console for details.');
                })
                .finally(() => {
                    button.disabled = false;
                    button.innerHTML = originalText;
                });
        }

        function showHierarchy() {
            const button = document.getElementById('hierarchyBtn');
            const originalText = button.innerHTML;
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Loading Hierarchy...';

            // Fetch hierarchical visualization data
            fetch(`/editor/api/hierarchy/visualization/${ontologyId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Replace current visualization with hierarchical view
                        const elements = [...data.visualization.nodes, ...data.visualization.edges];
                        originalElements = elements;

                        loadDataIntoGraph(elements);
                        updateStatistics(data.statistics);

                        // Use hierarchical layout
                        currentLayout = 'dagre';
                        applyLayout();

                        alert(`Hierarchical view loaded!\n\n📊 ${data.statistics.classes} classes with ${data.statistics.hierarchical_relationships} subClassOf relationships\n\n🏗️ This shows the true PROV-O class hierarchy.`);
                    } else {
                        alert('Failed to load hierarchy: ' + (data.error || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Hierarchy loading error:', error);
                    alert('Failed to load hierarchy. Check console for details.');
                })
                .finally(() => {
                    button.disabled = false;
                    button.innerHTML = originalText;
                });
        }

        // Initialize visualization on load
        document.addEventListener('DOMContentLoaded', function () {
            setupEventListeners();
            initializeCytoscape();
            loadOntologyData();
        });

        function setupEventListeners() {
            document.getElementById('filterType').addEventListener('change', applyFilters);
            document.getElementById('showInferred').addEventListener('change', applyFilters);
            document.getElementById('showRestrictions').addEventListener('change', applyFilters);
            document.getElementById('hideUnconnected').addEventListener('change', applyFilters);
            document.getElementById('layoutSelector').addEventListener('change', function () {
                currentLayout = this.value;
                applyLayout(); // Apply the layout immediately when changed
            });

            // Set the dropdown to match the current default layout
            document.getElementById('layoutSelector').value = currentLayout;

            document.getElementById('searchBox').addEventListener('keyup', function (e) {
                if (e.key === 'Enter') {
                    performSemanticSearch();
                }
            });
        }

        function initializeCytoscape() {
            // Register dagre layout extension
            try {
                if (typeof cytoscape !== 'undefined' && typeof cytoscapeDagre !== 'undefined') {
                    cytoscape.use(cytoscapeDagre);
                }
            } catch (e) {
                console.warn('Dagre layout extension failed to register:', e);
            }

            cy = cytoscape({
                container: document.getElementById('cy'),

                style: [
                    {
                        selector: 'node',
                        style: {
                            'background-color': '#4A90E2',
                            'label': 'data(label)',
                            'width': 60,
                            'height': 60,
                            'color': '#333',
                            'text-valign': 'center',
                            'text-halign': 'center',
                            'font-size': '10px',
                            'font-weight': 'bold',
                            'border-width': 2,
                            'border-color': '#fff',
                            'text-wrap': 'wrap',
                            'text-max-width': '80px'
                        }
                    },
                    {
                        selector: 'node.inferred',
                        style: {
                            'background-color': '#7ED321',
                            'border-style': 'dashed',
                            'border-width': 3
                        }
                    },
                    {
                        selector: 'node.has-restrictions',
                        style: {
                            'border-color': '#F5A623',
                            'border-width': 3
                        }
                    },
                    {
                        selector: 'node:selected',
                        style: {
                            'border-color': '#ff6b6b',
                            'border-width': 4
                        }
                    },
                    {
                        selector: 'edge',
                        style: {
                            'width': 2,
                            'line-color': '#999',
                            'target-arrow-color': '#999',
                            'target-arrow-shape': 'triangle',
                            'curve-style': 'bezier',
                            'arrow-scale': 1.2
                        }
                    },
                    {
                        selector: 'edge.inferred',
                        style: {
                            'line-color': '#7ED321',
                            'target-arrow-color': '#7ED321',
                            'line-style': 'dashed',
                            'width': 3
                        }
                    },
                    {
                        selector: 'edge.property-edge',
                        style: {
                            'line-color': '#8e44ad',
                            'target-arrow-color': '#8e44ad',
                            'line-style': 'dashed',
                            'label': 'data(label)',
                            'font-size': '8px',
                            'color': '#8e44ad',
                            'text-rotation': 'autorotate',
                            'text-background-color': '#ffffff',
                            'text-background-opacity': 0.85,
                            'text-background-padding': '1px'
                        }
                    },
                    {
                        selector: 'edge:selected',
                        style: {
                            'line-color': '#ff6b6b',
                            'target-arrow-color': '#ff6b6b',
                            'width': 4
                        }
                    },
                    // Namespace-based colors
                    {
                        selector: 'node.ns-bfo',
                        style: {
                            'background-color': '#8E24AA'
                        }
                    },
                    {
                        selector: 'node.ns-prov',
                        style: {
                            'background-color': '#F57F17'
                        }
                    },
                    {
                        selector: 'node.ns-proethica',
                        style: {
                            'background-color': '#D32F2F'
                        }
                    }
                ],

                layout: {
                    name: 'dagre',
                    rankDir: 'TB',
                    animate: true,
                    animationDuration: 500
                },

                // Interaction options
                zoomingEnabled: true,
                userZoomingEnabled: true,
                panningEnabled: true,
                userPanningEnabled: true,
                boxSelectionEnabled: true,
                selectionType: 'single',

                // Performance
                textureOnViewport: false,
                motionBlur: true,
                wheelSensitivity: 0.2
            });

            // Event handlers
            cy.on('tap', 'node', function (evt) {
                const node = evt.target;
                showNodeDetails(node);
                highlightConnectedNodes(node);
            });

            cy.on('tap', function (evt) {
                if (evt.target === cy) {
                    // Clicked on background - clear selection
                    clearHighlights();
                    hideEntityDetails();
                }
            });

            cy.on('mouseover', 'node', function (evt) {
                const node = evt.target;
                showTooltip(evt, node);
            });

            cy.on('mouseout', 'node', function (evt) {
                hideTooltip();
            });
        }

        function loadOntologyData() {
            const entityType = document.getElementById('filterType').value;
            const includeReasoning = document.getElementById('showInferred')?.checked || false;

            // Use hierarchical view by default for ontologies with hierarchical structure
            const useHierarchical = isHierarchicalOntology;
            const url = useHierarchical
                ? `/editor/api/hierarchy/visualization/${ontologyId}`
                : `/editor/api/enhanced/visualization/${ontologyId}?include_reasoning=${includeReasoning}&limit=1000`;

            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Failed to load ontology hierarchy');
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success && data.visualization) {
                        ontologyData = data;
                        // Both endpoints provide cytoscape-ready format
                        const elements = [...data.visualization.nodes, ...data.visualization.edges];
                        originalElements = elements;

                        if (elements.length === 0) {
                            // No entities to visualize
                            document.getElementById('loadingIndicator').innerHTML = `
                                <div class="alert alert-info">
                                    <i class="fas fa-info-circle"></i>
                                    <strong>No entities found for visualization</strong>
                                    <p class="mb-0">Entities are populated by the ontology sync service on startup or by saving a new version through the editor.</p>
                                </div>
                            `;
                        } else {
                            loadDataIntoGraph(elements);
                            updateStatistics(data.stats || data.statistics);

                            // Use hierarchical layout by default for hierarchical ontologies
                            if (useHierarchical) {
                                currentLayout = 'dagre';
                                applyLayout();
                            }

                            // Hide loading indicator and show graph
                            document.getElementById('loadingIndicator').style.display = 'none';
                            document.getElementById('cy').style.display = 'block';
                        }
                    } else {
                        throw new Error(data.error || 'No visualization data available');
                    }
                })
                .catch(error => {
                    console.error('Error loading ontology hierarchy:', error);
                    document.getElementById('loadingIndicator').innerHTML = `
                        <div class="alert alert-danger">
                            Error loading ontology hierarchy: ${error.message}
                        </div>
                    `;
                });
        }

        function convertHierarchyToCytoscape(hierarchy) {
            const elements = [];
            const processedNodes = new Set();

            function processNode(node, parentId = null) {
                if (!node || processedNodes.has(node.uri || node.name)) return;

                const nodeId = node.uri || node.name;
                processedNodes.add(nodeId);

                // Add node
                const nodeData = {
                    group: 'nodes',
                    data: {
                        id: nodeId,
                        label: node.label || node.name,
                        name: node.name,
                        uri: node.uri,
                        type: node.entity_type || node.type || 'class',
                        description: node.description || node.comment,
                        is_inferred: node.is_inferred || false,
                        restrictions: node.restrictions || 0,
                        namespace: getNamespaceFromURI(node.uri)
                    },
                    classes: getNodeClasses(node)
                };
                elements.push(nodeData);

                // Add edge to parent
                if (parentId && parentId !== nodeId) {
                    const edgeData = {
                        group: 'edges',
                        data: {
                            id: `${nodeId}_${parentId}`,
                            source: nodeId,
                            target: parentId,
                            type: 'subClassOf',
                            is_inferred: node.is_inferred || false
                        },
                        classes: node.is_inferred ? 'inferred' : 'explicit'
                    };
                    elements.push(edgeData);
                }

                // Process children
                if (node.children && Array.isArray(node.children)) {
                    node.children.forEach(child => processNode(child, nodeId));
                }
            }

            processNode(hierarchy);
            return elements;
        }

        function getNamespaceFromURI(uri) {
            if (!uri) return '';

            if (uri.includes('bfo')) return 'bfo';
            if (uri.includes('prov')) return 'prov';
            if (uri.includes('proethica')) return 'proethica';

            // Extract domain from URI
            const match = uri.match(/https?:\/\/([^\/]+)/);
            return match ? match[1].replace(/\./g, '-') : '';
        }

        function getNodeClasses(node) {
            const classes = ['class-node'];

            if (node.is_inferred) {
                classes.push('inferred');
            }

            if (node.restrictions && node.restrictions > 0) {
                classes.push('has-restrictions');
            }

            const namespace = getNamespaceFromURI(node.uri);
            if (namespace) {
                classes.push(`ns-${namespace}`);
            }

            return classes.join(' ');
        }

        function loadDataIntoGraph(elements) {
            // Clear existing elements
            cy.elements().remove();

            // Add new elements
            cy.add(elements);

            // Apply initial layout
            applyLayout();
        }

        function applyLayout() {
            const layoutName = currentLayout;
            const nodeCount = cy.nodes().length;

            let layoutConfig = { name: layoutName, animate: true, animationDuration: 1000 };

            // Configure layout based on type and size
            switch (layoutName) {
                case 'dagre':
                    layoutConfig = {
                        ...layoutConfig,
                        rankDir: 'TB',
                        spacingFactor: 1.2,
                        nodeSep: 50,
                        edgeSep: 10,
                        rankSep: 100
                    };
                    break;

                case 'cose':
                    layoutConfig = {
                        ...layoutConfig,
                        nodeRepulsion: nodeCount < 100 ? 400000 : 800000,
                        nodeOverlap: 20,
                        idealEdgeLength: 80,
                        edgeElasticity: 200
                    };
                    break;

                case 'breadthfirst':
                    layoutConfig = {
                        ...layoutConfig,
                        directed: true,
                        spacingFactor: 1.5
                    };
                    break;

                case 'circle':
                    layoutConfig = {
                        ...layoutConfig,
                        radius: Math.min(300, nodeCount * 10),
                        spacingFactor: 1.2
                    };
                    break;

                case 'grid':
                    layoutConfig = {
                        ...layoutConfig,
                        rows: Math.ceil(Math.sqrt(nodeCount)),
                        spacingFactor: 1.2
                    };
                    break;

                case 'concentric':
                    layoutConfig = {
                        ...layoutConfig,
                        minNodeSpacing: 50,
                        spacingFactor: 1.5
                    };
                    break;
            }

            const layout = cy.layout(layoutConfig);
            layout.run();
        }

        // New Cytoscape-based functions
        function showNodeDetails(node) {
            const nodeData = node.data();
            currentEntityData = nodeData;

            const detailsElement = document.getElementById('entityDetails');
            const detailsCard = document.getElementById('entityDetailsCard');
            const findSimilarBtn = document.getElementById('findSimilarBtn');

            let html = `<div class="entity-header">${nodeData.label || nodeData.name}</div>`;

            if (nodeData.uri) {
                html += `<div class="entity-uri">${nodeData.uri}</div>`;
            }

            if (nodeData.description) {
                html += `
                    <div class="entity-property">
                        <span class="entity-property-name">Description:</span>
                        <div class="entity-property-value">${nodeData.description}</div>
                    </div>
                `;
            }

            if (nodeData.type) {
                html += `
                    <div class="entity-property">
                        <span class="entity-property-name">Type:</span>
                        <div class="entity-property-value">
                            <span class="badge bg-secondary entity-${nodeData.type}">
                                ${nodeData.type}
                            </span>
                        </div>
                    </div>
                `;
            }

            if (nodeData.is_inferred) {
                html += `
                    <div class="entity-property">
                        <span class="entity-property-name">Inferred:</span>
                        <div class="entity-property-value">
                            <span class="badge bg-success">Yes</span>
                        </div>
                    </div>
                `;
            }

            if (nodeData.restrictions > 0) {
                html += `
                    <div class="entity-property">
                        <span class="entity-property-name">Restrictions:</span>
                        <div class="entity-property-value">${nodeData.restrictions}</div>
                    </div>
                `;
            }

            // Show connections
            const connectedEdges = node.connectedEdges();
            const parents = connectedEdges.filter(edge => edge.target().id() === node.id()).sources();
            const children = connectedEdges.filter(edge => edge.source().id() === node.id()).targets();

            if (parents.length > 0) {
                html += `
                    <div class="entity-property">
                        <span class="entity-property-name">Parents:</span>
                        <div class="entity-property-value">
                            ${parents.map(p => `<small class="d-block">${p.data('label')}</small>`).join('')}
                        </div>
                    </div>
                `;
            }

            if (children.length > 0) {
                html += `
                    <div class="entity-property">
                        <span class="entity-property-name">Children:</span>
                        <div class="entity-property-value">
                            ${children.map(c => `<small class="d-block">${c.data('label')}</small>`).join('')}
                        </div>
                    </div>
                `;
            }

            detailsElement.innerHTML = html;
            detailsCard.style.display = 'block';
            findSimilarBtn.style.display = nodeData.uri ? 'block' : 'none';
        }

        function highlightConnectedNodes(node) {
            // Reset all styling
            clearHighlights();

            // Highlight the selected node
            node.addClass('highlighted');

            // Highlight connected nodes and edges
            const connectedEdges = node.connectedEdges();
            const connectedNodes = connectedEdges.connectedNodes();

            connectedEdges.addClass('highlighted');
            connectedNodes.addClass('connected');

            // Dim non-connected elements
            cy.elements().not(node).not(connectedNodes).not(connectedEdges).addClass('dimmed');
        }

        function clearHighlights() {
            cy.elements().removeClass('highlighted connected dimmed');
        }

        function hideEntityDetails() {
            document.getElementById('entityDetailsCard').style.display = 'none';
        }

        function showTooltip(evt, node) {
            // Create or update tooltip
            let tooltip = document.getElementById('node-tooltip');
            if (!tooltip) {
                tooltip = document.createElement('div');
                tooltip.id = 'node-tooltip';
                tooltip.className = 'tooltip';
                document.body.appendChild(tooltip);
            }

            const nodeData = node.data();
            tooltip.innerHTML = `
                <strong>${nodeData.label || nodeData.name}</strong><br>
                <small>${nodeData.type}</small>
                ${nodeData.is_inferred ? '<br><small class="text-success">Inferred</small>' : ''}
            `;

            // Position tooltip
            const pos = node.renderedPosition();
            tooltip.style.left = (pos.x + 10) + 'px';
            tooltip.style.top = (pos.y - 10) + 'px';
            tooltip.style.display = 'block';
        }

        function hideTooltip() {
            const tooltip = document.getElementById('node-tooltip');
            if (tooltip) {
                tooltip.style.display = 'none';
            }
        }

        // Control functions
        function zoomIn() {
            cy.zoom(cy.zoom() * 1.2);
        }

        function zoomOut() {
            cy.zoom(cy.zoom() * 0.8);
        }

        function fitToScreen() {
            cy.fit();
        }

        function resetZoom() {
            cy.fit();
            cy.center();
        }

        function centerGraph() {
            cy.center();
        }

        // Global fullscreen state
        let isFullscreen = false;

        function toggleFullscreen() {
            const container = document.querySelector('.container-fluid');
            const btn = document.getElementById('fullscreenBtn');
            const btnIcon = btn.querySelector('i');

            isFullscreen = !isFullscreen;

            if (isFullscreen) {
                // Enter fullscreen mode
                container.classList.add('visualization-fullscreen');
                btnIcon.className = 'fas fa-compress-arrows-alt me-1';
                btn.innerHTML = '<i class="fas fa-compress-arrows-alt me-1"></i>Exit Full Width';

                // Resize Cytoscape after DOM changes
                setTimeout(() => {
                    if (cy) {
                        cy.resize();
                        cy.fit();
                    }
                }, 100);
            } else {
                // Exit fullscreen mode
                container.classList.remove('visualization-fullscreen');
                btnIcon.className = 'fas fa-expand-arrows-alt me-1';
                btn.innerHTML = '<i class="fas fa-expand-arrows-alt me-1"></i>Expand to Full Width';

                // Resize Cytoscape after DOM changes
                setTimeout(() => {
                    if (cy) {
                        cy.resize();
                        cy.fit();
                    }
                }, 100);
            }
        }

        function performSemanticSearch() {
            const query = document.getElementById('searchBox').value.trim();
            if (!query) {
                alert('Please enter a search term');
                return;
            }

            // Search in current graph first (client-side)
            searchInGraph(query);

            // Also perform server-side semantic search
            const url = `/editor/api/entities/search?query=${encodeURIComponent(query)}&ontology_id=${ontologyId}&limit=10`;

            fetch(url)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        displaySearchResults(data.results, query);
                    } else {
                        console.warn('Server search failed: ' + data.error);
                    }
                })
                .catch(error => {
                    console.error('Search error:', error);
                });
        }

        function searchInGraph(query) {
            clearHighlights();

            const matchingNodes = cy.nodes().filter(node => {
                const data = node.data();
                const searchString = (data.label + ' ' + data.name + ' ' + (data.description || '')).toLowerCase();
                return searchString.includes(query.toLowerCase());
            });

            if (matchingNodes.length > 0) {
                // Highlight matching nodes
                matchingNodes.addClass('search-match');

                // Fit to matching nodes
                cy.fit(matchingNodes, 50);

                // Show details of first match
                showNodeDetails(matchingNodes[0]);
            } else {
                alert('No matching entities found in current view');
            }
        }

        function displaySearchResults(results, query) {
            const resultsPanel = document.getElementById('searchResultsPanel');
            const resultsContainer = document.getElementById('searchResults');

            if (results.length === 0) {
                resultsContainer.innerHTML = '<div class="text-muted">No server results found</div>';
            } else {
                let html = '';
                results.forEach(result => {
                    html += `
                        <div class="search-result-item" onclick="highlightEntity('${result.uri}')">
                            <div class="fw-bold">${result.label || 'Unnamed'}</div>
                            <div class="small text-muted">${result.entity_type}</div>
                            ${result.comment ? `<div class="small">${result.comment.substring(0, 100)}...</div>` : ''}
                            <div class="similarity-score">Similarity: ${(result.similarity_score * 100).toFixed(1)}%</div>
                        </div>
                    `;
                });
                resultsContainer.innerHTML = html;
            }

            resultsPanel.style.display = 'block';
        }

        function highlightEntity(uri) {
            // Find and highlight entity in Cytoscape graph
            const targetNode = cy.nodes().filter(node => node.data('uri') === uri);

            if (targetNode.length > 0) {
                clearHighlights();
                targetNode.addClass('search-highlight');
                cy.animate({
                    center: { eles: targetNode },
                    zoom: 1.5
                }, {
                    duration: 500
                });
                showNodeDetails(targetNode[0]);
            } else {
                console.warn('Entity not found in current graph:', uri);
            }
        }

        function findSimilarEntities() {
            if (!currentEntityData || !currentEntityData.uri) {
                return;
            }

            const searchQuery = currentEntityData.name || currentEntityData.uri;
            document.getElementById('searchBox').value = searchQuery;
            performSemanticSearch();
        }

        function toggleClassesOnly() {
            hidePropertyNodes = !hidePropertyNodes;
            const btn = document.getElementById('classesOnlyBtn');
            if (hidePropertyNodes) {
                // Set dropdown to "All Types" so the quick filter has something to act on
                document.getElementById('filterType').value = 'all';
                btn.classList.remove('btn-outline-secondary');
                btn.classList.add('btn-secondary', 'text-white');
            } else {
                btn.classList.remove('btn-secondary', 'text-white');
                btn.classList.add('btn-outline-secondary');
            }
            applyFilters();
        }

        function applyFilters() {
            const filterType = document.getElementById('filterType').value;
            const showInferred = document.getElementById('showInferred').checked;
            const showRestrictions = document.getElementById('showRestrictions').checked;

            if (!originalElements) {
                // If no data loaded yet, reload
                loadOntologyData();
                return;
            }

            // Filter elements based on criteria
            let filteredElements = [...originalElements];

            // Filter by entity type
            if (filterType !== 'all') {
                filteredElements = filteredElements.filter(element => {
                    if (element.group === 'edges') return true; // Keep all edges for now
                    return element.data.type === filterType;
                });

                // Remove edges where either source or target is filtered out
                const nodeIds = new Set(filteredElements.filter(e => e.group === 'nodes').map(e => e.data.id));
                filteredElements = filteredElements.filter(element => {
                    if (element.group === 'nodes') return true;
                    return nodeIds.has(element.data.source) && nodeIds.has(element.data.target);
                });
            }

            // Filter inferred relationships
            if (!showInferred) {
                filteredElements = filteredElements.filter(element => {
                    return !element.data.is_inferred;
                });
            }

            // Classes Only quick filter: remove property-type nodes and any edges touching them
            if (hidePropertyNodes) {
                filteredElements = filteredElements.filter(element => {
                    if (element.group === 'edges') return true;
                    return element.data.type !== 'property';
                });
                const keepIds = new Set(filteredElements.filter(e => e.group === 'nodes').map(e => e.data.id));
                filteredElements = filteredElements.filter(element => {
                    if (element.group === 'nodes') return true;
                    return keepIds.has(element.data.source) && keepIds.has(element.data.target);
                });
            }

            // Hide unconnected nodes (nodes with zero edges in the current filtered set)
            const hideUnconnected = document.getElementById('hideUnconnected').checked;
            if (hideUnconnected) {
                const connectedIds = new Set();
                filteredElements.forEach(element => {
                    if (element.group === 'edges') {
                        connectedIds.add(element.data.source);
                        connectedIds.add(element.data.target);
                    }
                });
                filteredElements = filteredElements.filter(element => {
                    if (element.group === 'edges') return true;
                    return connectedIds.has(element.data.id);
                });
            }

            // Apply filters to graph
            cy.elements().remove();
            cy.add(filteredElements);

            // Update styling based on restrictions filter
            if (showRestrictions) {
                cy.nodes().forEach(node => {
                    if (node.data('restrictions') > 0) {
                        node.addClass('highlight-restrictions');
                    }
                });
            }

            // Re-apply layout
            applyLayout();
        }

        function updateStatistics(stats) {
            if (stats) {
                document.getElementById('totalNodes').textContent = cy ? cy.nodes().length : (stats.total_entities || 0);
                document.getElementById('totalEdges').textContent = cy ? cy.edges().length : 0;
                document.getElementById('classCount').textContent = stats.entity_type_counts?.class || 0;
                document.getElementById('propertyCount').textContent = stats.entity_type_counts?.property || 0;
                document.getElementById('inferredCount').textContent = stats.inferred_count || 0;
                document.getElementById('consistencyStatus').textContent = stats.consistency_check !== undefined ?
                    (stats.consistency_check ? 'Yes' : 'No') : 'Unknown';
            }
        }

        function exportVisualization() {
            if (!cy) {
                alert('No visualization loaded to export');
                return;
            }

            // Export as PNG
            const pngBlob = cy.png({
                output: 'blob',
                bg: '#ffffff',
                full: true,
                scale: 2 // High resolution
            });

            // Create download link
            const url = URL.createObjectURL(pngBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${ontologyId}_visualization.png`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }

        // Modal functions for inference results
        function showInferenceResultsModal(data, message) {
            const modal = document.getElementById('inferenceResultsModal');
            const modalBody = document.getElementById('inferenceResultsContent');
            const loadVersionBtn = document.getElementById('loadVersionBtn');
            // Read-only reasoning: no version is ever created from this page.
            if (loadVersionBtn) loadVersionBtn.style.display = 'none';

            const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const nothing = data.nothing_entities || [];

            let htmlContent = `
                <div class="row">
                    <div class="col-md-6">
                        <h6><i class="fas fa-sitemap text-primary"></i> Inferred (merged graph)</h6>
                        <ul class="list-unstyled">
                            <li><strong>Subclass relations:</strong> ${data.inferred_subclass_count || 0}</li>
                            <li><strong>Type assertions:</strong> ${data.inferred_type_count || 0}</li>
                            ${data.truncated ? '<li class="text-muted small">(lists truncated by server cap)</li>' : ''}
                        </ul>
                    </div>
                    <div class="col-md-6">
                        <h6><i class="fas fa-check-circle text-success"></i> Status</h6>
                        <ul class="list-unstyled">
                            <li><strong>Consistent:</strong> ${data.consistent ? '✅ Yes' : '❌ No'}</li>
                            <li><strong>Reasoner:</strong> Pellet</li>
                            <li><strong>Mode:</strong> read-only</li>
                        </ul>
                    </div>
                </div>
            `;

            const sample = (data.inferred_subclasses || []).slice(0, 8);
            if (sample.length > 0) {
                htmlContent += `<h6 class="mt-2"><i class="fas fa-project-diagram text-success"></i> Inferred subclass relations</h6><ul class="small">`;
                sample.forEach(rel => {
                    htmlContent += `<li>${esc(rel.child.split('#').pop())} &rarr; ${esc(rel.parent.split('#').pop())}</li>`;
                });
                htmlContent += `</ul><p class="small text-muted mb-0">Overlaid on the graph as green dashed edges (toggle "Show Inferred Relations").</p>`;
            }

            if (!data.consistent) {
                htmlContent += `
                    <div class="alert alert-danger mt-3">
                        <strong>The merged ontology is inconsistent.</strong>
                        ${data.error_explanation ? `<div class="small mt-1">${esc(data.error_explanation)}</div>` : ''}
                    </div>`;
            }
            if (nothing.length > 0) {
                htmlContent += `
                    <div class="alert alert-warning mt-3">
                        <strong>${nothing.length} entities forced to owl:Nothing</strong> (disjointness violations)
                        <ul class="small mb-0">${nothing.slice(0, 5).map(u => `<li>${esc(u)}</li>`).join('')}</ul>
                    </div>`;
            }
            if (data.note) {
                htmlContent += `<p class="small text-muted mt-2 mb-0">${esc(data.note)}</p>`;
            }

            modalBody.innerHTML = htmlContent;

            // Show the modal
            const bootstrapModal = new bootstrap.Modal(modal);
            bootstrapModal.show();
        }

        function showInferenceErrorModal(error) {
            const modal = document.getElementById('inferenceResultsModal');
            const modalBody = document.getElementById('inferenceResultsContent');
            const loadVersionBtn = document.getElementById('loadVersionBtn');

            modalBody.innerHTML = `
                <div class="alert alert-danger">
                    <h6><i class="fas fa-exclamation-triangle"></i> Inference Failed</h6>
                    <p class="mb-0">${error}</p>
                </div>
            `;

            loadVersionBtn.style.display = 'none';

            // Show the modal
            const bootstrapModal = new bootstrap.Modal(modal);
            bootstrapModal.show();
        }

        function loadNewVersion(versionId) {
            // First make the version current
            fetch(`/api/versions/${versionId}/make-current`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Close the modal
                        const modal = bootstrap.Modal.getInstance(document.getElementById('inferenceResultsModal'));
                        modal.hide();

                        // Show loading indicator
                        const loadingIndicator = document.getElementById('loadingIndicator');
                        loadingIndicator.innerHTML = `
                        <div class="d-flex align-items-center">
                            <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
                            Loading reasoned version...
                        </div>
                    `;
                        loadingIndicator.style.display = 'block';

                        // Reload the page to show the new current version with entities
                        setTimeout(() => {
                            location.reload();
                        }, 1500);
                    } else {
                        alert('Failed to load new version: ' + (data.error || 'Unknown error'));
                    }
                })
                .catch(error => {
                    console.error('Error loading new version:', error);
                    alert('Failed to load new version. Check console for details.');
                });
        }

        // Initialize visualization when page loads
        document.addEventListener('DOMContentLoaded', function () {
            // Load ontology data on page load
            loadOntologyData();
        });
    
