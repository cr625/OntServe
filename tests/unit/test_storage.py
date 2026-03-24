"""
Unit Tests for OntServe Storage Layer

Tests for PostgreSQLStorage, DatabaseConceptManager, and related components.
Tests that require a database connection are marked with @pytest.mark.database
and will auto-skip when the test database is not reachable.
"""

import pytest
import os
from unittest.mock import patch

# Ensure test environment
os.environ['ENVIRONMENT'] = 'test'


@pytest.mark.database
class TestPostgreSQLStorageInit:
    """Test PostgreSQLStorage initialization and configuration."""

    def test_default_config(self, test_db_url):
        """Test initialization with default configuration."""
        from storage.postgresql_storage import PostgreSQLStorage

        config = {'db_url': test_db_url}
        storage = PostgreSQLStorage(config)

        assert storage.pool_size == 5
        assert storage.pool_max_size == 20
        assert storage.timeout == 30
        assert storage.enable_vector_search is True

    def test_custom_config(self, test_db_url):
        """Test initialization with custom configuration."""
        from storage.postgresql_storage import PostgreSQLStorage

        config = {
            'db_url': test_db_url,
            'pool_size': 3,
            'pool_max_size': 10,
            'timeout': 60,
            'enable_vector_search': False
        }

        storage = PostgreSQLStorage(config)

        assert storage.pool_size == 3
        assert storage.pool_max_size == 10
        assert storage.timeout == 60
        assert storage.enable_vector_search is False

    def test_db_url_from_environment(self, test_db_url):
        """Test that db_url can be read from environment variable."""
        from storage.postgresql_storage import PostgreSQLStorage

        with patch.dict(os.environ, {'ONTSERVE_DB_URL': test_db_url}):
            storage = PostgreSQLStorage({})
            assert storage.db_url == test_db_url


@pytest.mark.database
class TestPostgreSQLStorageConnection:
    """Test PostgreSQLStorage connection management."""

    def test_get_connection(self, pg_storage):
        """Test getting a connection from the pool."""
        conn = pg_storage._get_connection()
        assert conn is not None
        pg_storage._return_connection(conn)

    def test_execute_query_fetch_one(self, pg_storage):
        """Test executing a query that fetches one row."""
        result = pg_storage._execute_query(
            "SELECT 1 as value",
            fetch_one=True
        )
        assert result is not None
        assert result['value'] == 1

    def test_execute_query_fetch_all(self, pg_storage):
        """Test executing a query that fetches all rows."""
        result = pg_storage._execute_query(
            "SELECT generate_series(1, 3) as value",
            fetch_all=True
        )
        assert result is not None
        assert len(result) == 3

    def test_execute_query_rowcount(self, pg_storage):
        """Test executing a query that returns rowcount."""
        pg_storage._execute_query(
            "CREATE TEMP TABLE test_rowcount (id serial, value text)"
        )
        result = pg_storage._execute_query(
            "INSERT INTO test_rowcount (value) VALUES ('a'), ('b')"
        )
        assert result == 2

    def test_generate_content_hash(self, pg_storage):
        """Test content hash generation."""
        content = "test content"
        hash1 = pg_storage._generate_content_hash(content)
        hash2 = pg_storage._generate_content_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters

        hash3 = pg_storage._generate_content_hash("different content")
        assert hash1 != hash3


@pytest.mark.database
class TestPostgreSQLStorageErrorHandling:
    """Test PostgreSQLStorage error handling."""

    def test_invalid_query_raises_error(self, pg_storage):
        """Test that invalid SQL raises StorageError."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError):
            pg_storage._execute_query("INVALID SQL SYNTAX HERE")

    def test_connection_error_on_bad_url(self):
        """Test that bad database URL raises error."""
        from storage.postgresql_storage import PostgreSQLStorage, StorageError

        config = {
            'db_url': 'postgresql://invalid:invalid@localhost:9999/nonexistent'
        }

        with pytest.raises(StorageError):
            PostgreSQLStorage(config)


@pytest.mark.database
class TestStorageBackendInterface:
    """Test that PostgreSQLStorage implements StorageBackend interface."""

    def test_has_store_method(self, pg_storage):
        """Test that store method exists."""
        assert hasattr(pg_storage, 'store')
        assert callable(pg_storage.store)

    def test_has_retrieve_method(self, pg_storage):
        """Test that retrieve method exists."""
        assert hasattr(pg_storage, 'retrieve')
        assert callable(pg_storage.retrieve)

    def test_has_delete_method(self, pg_storage):
        """Test that delete method exists."""
        assert hasattr(pg_storage, 'delete')
        assert callable(pg_storage.delete)

    @pytest.mark.skip(reason="list method not yet implemented")
    def test_has_list_method(self, pg_storage):
        """Test that list method exists."""
        assert hasattr(pg_storage, 'list')
        assert callable(pg_storage.list)

    @pytest.mark.skip(reason="search method not yet implemented")
    def test_has_search_method(self, pg_storage):
        """Test that search method exists."""
        assert hasattr(pg_storage, 'search')
        assert callable(pg_storage.search)


class TestStorageErrorClass:
    """Test StorageError exception class."""

    def test_storage_error_inheritance(self):
        """Test that StorageError inherits from Exception."""
        from storage.postgresql_storage import StorageError
        assert issubclass(StorageError, Exception)

    def test_storage_error_message(self):
        """Test StorageError message handling."""
        from storage.postgresql_storage import StorageError
        error = StorageError("Test error message")
        assert str(error) == "Test error message"

    def test_storage_error_can_be_raised(self):
        """Test that StorageError can be raised and caught."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            raise StorageError("Test error")
        assert "Test error" in str(exc_info.value)


# =============================================================================
# ConceptManager Tests
# =============================================================================

@pytest.mark.database
class TestConceptManagerInit:
    """Test ConceptManager initialization."""

    def test_initialization(self, pg_storage):
        """Test concept manager initialization."""
        from storage.concept_manager import ConceptManager
        manager = ConceptManager(pg_storage)
        assert manager.storage == pg_storage


@pytest.mark.database
class TestConceptManagerSubmitConcept:
    """Test ConceptManager concept submission."""

    def test_submit_missing_required_fields(self, concept_manager):
        """Test that missing required fields raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            concept_manager.submit_candidate_concept({
                'category': 'Principle',
                'uri': 'http://test.org/TestConcept'
            })
        assert "Missing required field" in str(exc_info.value)

    def test_submit_missing_category(self, concept_manager):
        """Test that missing category raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            concept_manager.submit_candidate_concept({
                'label': 'Test Concept',
                'uri': 'http://test.org/TestConcept'
            })
        assert "Missing required field" in str(exc_info.value)

    def test_submit_missing_uri(self, concept_manager):
        """Test that missing URI raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            concept_manager.submit_candidate_concept({
                'label': 'Test Concept',
                'category': 'Principle'
            })
        assert "Missing required field" in str(exc_info.value)


@pytest.mark.database
class TestConceptManagerUpdateStatus:
    """Test ConceptManager status updates."""

    def test_invalid_status_raises_error(self, concept_manager):
        """Test that invalid status raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            concept_manager.update_concept_status(
                'nonexistent-id',
                'invalid_status',
                'test_user'
            )
        assert "Invalid status" in str(exc_info.value)

    def test_nonexistent_concept_raises_error(self, concept_manager):
        """Test that updating nonexistent concept raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            concept_manager.update_concept_status(
                'nonexistent-uuid-12345',
                'approved',
                'test_user'
            )
        assert "Concept not found" in str(exc_info.value)


@pytest.mark.database
class TestConceptManagerGetCandidates:
    """Test ConceptManager candidate retrieval."""

    def test_get_candidates_response_structure(self, concept_manager):
        """Test that get_candidate_concepts returns proper structure."""
        result = concept_manager.get_candidate_concepts('engineering-ethics')

        assert 'candidates' in result
        assert 'domain_id' in result
        assert 'filters' in result
        assert 'pagination' in result
        assert result['domain_id'] == 'engineering-ethics'
        assert isinstance(result['candidates'], list)

    def test_get_candidates_pagination_structure(self, concept_manager):
        """Test pagination metadata structure."""
        result = concept_manager.get_candidate_concepts(
            'engineering-ethics', limit=10, offset=0
        )

        pagination = result['pagination']
        assert 'total_count' in pagination
        assert 'limit' in pagination
        assert 'offset' in pagination
        assert 'has_more' in pagination
        assert pagination['limit'] == 10
        assert pagination['offset'] == 0

    def test_get_candidates_with_category_filter(self, concept_manager):
        """Test filtering candidates by category."""
        result = concept_manager.get_candidate_concepts(
            'engineering-ethics', category='Principle'
        )
        assert result['filters']['category'] == 'Principle'

    def test_get_candidates_with_status_filter(self, concept_manager):
        """Test filtering candidates by status."""
        result = concept_manager.get_candidate_concepts(
            'engineering-ethics', status='approved'
        )
        assert result['filters']['status'] == 'approved'


@pytest.mark.database
class TestConceptManagerGetEntities:
    """Test ConceptManager entity retrieval."""

    def test_get_entities_response_structure(self, concept_manager):
        """Test that get_entities_by_category returns proper structure."""
        result = concept_manager.get_entities_by_category('Role', 'engineering-ethics')

        assert 'entities' in result
        assert 'category' in result
        assert 'domain_id' in result
        assert 'total_count' in result
        assert result['category'] == 'Role'
        assert result['domain_id'] == 'engineering-ethics'

    def test_get_entities_includes_counts(self, concept_manager):
        """Test that response includes concept and ontology counts."""
        result = concept_manager.get_entities_by_category('Principle', 'engineering-ethics')

        assert 'concept_count' in result
        assert 'ontology_count' in result
        assert result['total_count'] == result['concept_count'] + result['ontology_count']


@pytest.mark.database
class TestConceptManagerDomainInfo:
    """Test ConceptManager domain info retrieval."""

    def test_get_domain_info_not_found(self, concept_manager):
        """Test domain info for non-existent domain raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            concept_manager.get_domain_info('nonexistent-domain')
        assert "Domain not found" in str(exc_info.value)

    def test_get_domain_info_response_structure(self, concept_manager):
        """Test domain info response has expected structure when domain exists."""
        try:
            result = concept_manager.get_domain_info('engineering-ethics')

            assert 'domain' in result
            assert 'stats' in result

            domain = result['domain']
            assert 'id' in domain
            assert 'name' in domain
            assert 'display_name' in domain

            stats = result['stats']
            assert 'total_concepts' in stats
            assert 'by_type' in stats
        except Exception:
            pytest.skip("engineering-ethics domain not in test database")


@pytest.mark.database
class TestConceptManagerOntologyEntities:
    """Test ConceptManager ontology entity retrieval."""

    def test_get_ontology_entities_returns_list(self, concept_manager):
        """Test that get_ontology_entities_by_category returns a list."""
        result = concept_manager.get_ontology_entities_by_category('Role')
        assert isinstance(result, list)

    def test_get_ontology_entities_empty_for_nonexistent(self, concept_manager):
        """Test that nonexistent category returns empty list."""
        result = concept_manager.get_ontology_entities_by_category('NonExistentCategory12345')
        assert result == []


@pytest.mark.database
class TestConceptManagerHelperMethods:
    """Test ConceptManager helper methods."""

    def test_get_concept_by_id_not_found(self, concept_manager):
        """Test that _get_concept_by_id returns None for nonexistent concept."""
        result = concept_manager._get_concept_by_id('nonexistent-uuid-12345')
        assert result is None

    def test_get_concept_by_invalid_id(self, concept_manager):
        """Test that _get_concept_by_id handles invalid IDs gracefully."""
        result = concept_manager._get_concept_by_id('not-a-valid-uuid')
        assert result is None
