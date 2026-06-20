    function createNewOntology() {
        window.location.href = window.OntServeEditorMain.importOntologyUrl;
    }

    function refreshOntologies() {
        window.location.reload();
    }

    function extractEntities(ontologyId) {
        console.log('Extract entities for:', ontologyId);
        // Implement extract entities functionality
    }

    function deleteOntology(ontologyId) {
        if (confirm('Are you sure you want to delete this ontology?')) {
            console.log('Delete ontology:', ontologyId);
            // Implement delete functionality
        }
    }

    // Search functionality
    document.getElementById('searchOntologies').addEventListener('input', function (e) {
        const searchTerm = e.target.value.toLowerCase();
        const ontologyItems = document.querySelectorAll('.ontology-item');

        ontologyItems.forEach(item => {
            const name = item.dataset.name;
            if (name.includes(searchTerm)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    });
