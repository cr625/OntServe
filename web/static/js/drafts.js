function deleteDraft(ontologyName) {
    if (confirm(`Are you sure you want to delete the draft ontology "${ontologyName}"? This action cannot be undone.`)) {
        fetch(`/editor/api/ontologies/${ontologyName}/draft`, {
            method: 'DELETE',
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Reload the page to show updated list
                window.location.reload();
            } else {
                alert(`Error deleting draft: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error deleting draft');
        });
    }
}
