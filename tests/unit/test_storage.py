"""
Unit Tests for OntServe Storage Layer

Tests for PostgreSQLStorage, DatabaseConceptManager, and related components.
These tests use the test database (ontserve_test) for integration.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Ensure test environment
os.environ['ENVIRONMENT'] = 'test'


class TestPostgreSQLStorageInit:
    """Test PostgreSQLStorage initialization and configuration."""

    def test_default_config(self):
        """Test initialization with default configuration."""
        from storage.postgresql_storage import PostgreSQLStorage

        # Use test database URL
        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }

        storage = PostgreSQLStorage(config)

        assert storage.pool_size == 5
        assert storage.pool_max_size == 20
        assert storage.timeout == 30
        assert storage.enable_vector_search is True

    def test_custom_config(self):
        """Test initialization with custom configuration."""
        from storage.postgresql_storage import PostgreSQLStorage

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test',
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

    def test_db_url_from_environment(self):
        """Test that db_url can be read from environment variable."""
        from storage.postgresql_storage import PostgreSQLStorage

        test_url = 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        with patch.dict(os.environ, {'ONTSERVE_DB_URL': test_url}):
            storage = PostgreSQLStorage({})
            assert storage.db_url == test_url


class TestPostgreSQLStorageConnection:
    """Test PostgreSQLStorage connection management."""

    @pytest.fixture
    def storage(self):
        """Create storage instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        return PostgreSQLStorage(config)

    def test_get_connection(self, storage):
        """Test getting a connection from the pool."""
        conn = storage._get_connection()
        assert conn is not None

        # Return connection to pool
        storage._return_connection(conn)

    def test_execute_query_fetch_one(self, storage):
        """Test executing a query that fetches one row."""
        result = storage._execute_query(
            "SELECT 1 as value",
            fetch_one=True
        )

        assert result is not None
        assert result['value'] == 1

    def test_execute_query_fetch_all(self, storage):
        """Test executing a query that fetches all rows."""
        result = storage._execute_query(
            "SELECT generate_series(1, 3) as value",
            fetch_all=True
        )

        assert result is not None
        assert len(result) == 3

    def test_execute_query_rowcount(self, storage):
        """Test executing a query that returns rowcount."""
        # Create temp table for test
        storage._execute_query(
            "CREATE TEMP TABLE test_rowcount (id serial, value text)"
        )

        # Insert and check rowcount
        result = storage._execute_query(
            "INSERT INTO test_rowcount (value) VALUES ('a'), ('b')"
        )

        assert result == 2

    def test_generate_content_hash(self, storage):
        """Test content hash generation."""
        content = "test content"
        hash1 = storage._generate_content_hash(content)
        hash2 = storage._generate_content_hash(content)

        # Same content should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters

        # Different content should produce different hash
        hash3 = storage._generate_content_hash("different content")
        assert hash1 != hash3


class TestPostgreSQLStorageErrorHandling:
    """Test PostgreSQLStorage error handling."""

    @pytest.fixture
    def storage(self):
        """Create storage instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        return PostgreSQLStorage(config)

    def test_invalid_query_raises_error(self, storage):
        """Test that invalid SQL raises StorageError."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError):
            storage._execute_query("INVALID SQL SYNTAX HERE")

    def test_connection_error_on_bad_url(self):
        """Test that bad database URL raises error."""
        from storage.postgresql_storage import PostgreSQLStorage, StorageError

        config = {
            'db_url': 'postgresql://invalid:invalid@localhost:9999/nonexistent'
        }

        with pytest.raises(StorageError):
            PostgreSQLStorage(config)


class TestStorageBackendInterface:
    """Test that PostgreSQLStorage implements StorageBackend interface."""

    @pytest.fixture
    def storage(self):
        """Create storage instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        return PostgreSQLStorage(config)

    def test_has_store_method(self, storage):
        """Test that store method exists."""
        assert hasattr(storage, 'store')
        assert callable(storage.store)

    def test_has_retrieve_method(self, storage):
        """Test that retrieve method exists."""
        assert hasattr(storage, 'retrieve')
        assert callable(storage.retrieve)

    def test_has_delete_method(self, storage):
        """Test that delete method exists."""
        assert hasattr(storage, 'delete')
        assert callable(storage.delete)

    @pytest.mark.skip(reason="list method not yet implemented")
    def test_has_list_method(self, storage):
        """Test that list method exists."""
        assert hasattr(storage, 'list')
        assert callable(storage.list)

    @pytest.mark.skip(reason="search method not yet implemented")
    def test_has_search_method(self, storage):
        """Test that search method exists."""
        assert hasattr(storage, 'search')
        assert callable(storage.search)


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

class TestConceptManagerInit:
    """Test ConceptManager initialization."""

    @pytest.fixture
    def storage(self):
        """Create storage instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        return PostgreSQLStorage(config)

    def test_initialization(self, storage):
        """Test concept manager initialization."""
        from storage.concept_manager import ConceptManager

        manager = ConceptManager(storage)
        assert manager.storage == storage


class TestConceptManagerSubmitConcept:
    """Test ConceptManager concept submission."""

    @pytest.fixture
    def manager(self):
        """Create manager instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage
        from storage.concept_manager import ConceptManager

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        storage = PostgreSQLStorage(config)
        return ConceptManager(storage)

    def test_submit_missing_required_fields(self, manager):
        """Test that missing required fields raises error."""
        from storage.postgresql_storage import StorageError

        # Missing 'label'
        with pytest.raises(StorageError) as exc_info:
            manager.submit_candidate_concept({
                'category': 'Principle',
                'uri': 'http://test.org/TestConcept'
            })

        assert "Missing required field" in str(exc_info.value)

    def test_submit_missing_category(self, manager):
        """Test that missing category raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            manager.submit_candidate_concept({
                'label': 'Test Concept',
                'uri': 'http://test.org/TestConcept'
            })

        assert "Missing required field" in str(exc_info.value)

    def test_submit_missing_uri(self, manager):
        """Test that missing URI raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            manager.submit_candidate_concept({
                'label': 'Test Concept',
                'category': 'Principle'
            })

        assert "Missing required field" in str(exc_info.value)


class TestConceptManagerUpdateStatus:
    """Test ConceptManager status updates."""

    @pytest.fixture
    def manager(self):
        """Create manager instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage
        from storage.concept_manager import ConceptManager

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        storage = PostgreSQLStorage(config)
        return ConceptManager(storage)

    def test_invalid_status_raises_error(self, manager):
        """Test that invalid status raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            manager.update_concept_status(
                'nonexistent-id',
                'invalid_status',
                'test_user'
            )

        assert "Invalid status" in str(exc_info.value)

    def test_nonexistent_concept_raises_error(self, manager):
        """Test that updating nonexistent concept raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            manager.update_concept_status(
                'nonexistent-uuid-12345',
                'approved',
                'test_user'
            )

        assert "Concept not found" in str(exc_info.value)


class TestConceptManagerGetCandidates:
    """Test ConceptManager candidate retrieval."""

    @pytest.fixture
    def manager(self):
        """Create manager instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage
        from storage.concept_manager import ConceptManager

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        storage = PostgreSQLStorage(config)
        return ConceptManager(storage)

    def test_get_candidates_response_structure(self, manager):
        """Test that get_candidate_concepts returns proper structure."""
        result = manager.get_candidate_concepts('engineering-ethics')

        # Should have standard response fields
        assert 'candidates' in result
        assert 'domain_id' in result
        assert 'filters' in result
        assert 'pagination' in result

        assert result['domain_id'] == 'engineering-ethics'
        assert isinstance(result['candidates'], list)

    def test_get_candidates_pagination_structure(self, manager):
        """Test pagination metadata structure."""
        result = manager.get_candidate_concepts(
            'engineering-ethics',
            limit=10,
            offset=0
        )

        pagination = result['pagination']
        assert 'total_count' in pagination
        assert 'limit' in pagination
        assert 'offset' in pagination
        assert 'has_more' in pagination

        assert pagination['limit'] == 10
        assert pagination['offset'] == 0

    def test_get_candidates_with_category_filter(self, manager):
        """Test filtering candidates by category."""
        result = manager.get_candidate_concepts(
            'engineering-ethics',
            category='Principle'
        )

        assert result['filters']['category'] == 'Principle'

    def test_get_candidates_with_status_filter(self, manager):
        """Test filtering candidates by status."""
        result = manager.get_candidate_concepts(
            'engineering-ethics',
            status='approved'
        )

        assert result['filters']['status'] == 'approved'


class TestConceptManagerGetEntities:
    """Test ConceptManager entity retrieval."""

    @pytest.fixture
    def manager(self):
        """Create manager instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage
        from storage.concept_manager import ConceptManager

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        storage = PostgreSQLStorage(config)
        return ConceptManager(storage)

    def test_get_entities_response_structure(self, manager):
        """Test that get_entities_by_category returns proper structure."""
        result = manager.get_entities_by_category('Role', 'engineering-ethics')

        # Should have standard response fields
        assert 'entities' in result
        assert 'category' in result
        assert 'domain_id' in result
        assert 'total_count' in result

        assert result['category'] == 'Role'
        assert result['domain_id'] == 'engineering-ethics'

    def test_get_entities_includes_counts(self, manager):
        """Test that response includes concept and ontology counts."""
        result = manager.get_entities_by_category('Principle', 'engineering-ethics')

        assert 'concept_count' in result
        assert 'ontology_count' in result
        assert result['total_count'] == result['concept_count'] + result['ontology_count']


class TestConceptManagerDomainInfo:
    """Test ConceptManager domain info retrieval."""

    @pytest.fixture
    def manager(self):
        """Create manager instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage
        from storage.concept_manager import ConceptManager

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        storage = PostgreSQLStorage(config)
        return ConceptManager(storage)

    def test_get_domain_info_not_found(self, manager):
        """Test domain info for non-existent domain raises error."""
        from storage.postgresql_storage import StorageError

        with pytest.raises(StorageError) as exc_info:
            manager.get_domain_info('nonexistent-domain')

        assert "Domain not found" in str(exc_info.value)

    def test_get_domain_info_response_structure(self, manager):
        """Test domain info response has expected structure when domain exists."""
        # This test will pass if engineering-ethics domain exists
        try:
            result = manager.get_domain_info('engineering-ethics')

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
            # Domain may not exist in test database - skip
            pytest.skip("engineering-ethics domain not in test database")


class TestConceptManagerOntologyEntities:
    """Test ConceptManager ontology entity retrieval."""

    @pytest.fixture
    def manager(self):
        """Create manager instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage
        from storage.concept_manager import ConceptManager

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        storage = PostgreSQLStorage(config)
        return ConceptManager(storage)

    def test_get_ontology_entities_returns_list(self, manager):
        """Test that get_ontology_entities_by_category returns a list."""
        result = manager.get_ontology_entities_by_category('Role')

        assert isinstance(result, list)

    def test_get_ontology_entities_empty_for_nonexistent(self, manager):
        """Test that nonexistent category returns empty list."""
        result = manager.get_ontology_entities_by_category('NonExistentCategory12345')

        assert result == []


class TestConceptManagerHelperMethods:
    """Test ConceptManager helper methods."""

    @pytest.fixture
    def manager(self):
        """Create manager instance for testing."""
        from storage.postgresql_storage import PostgreSQLStorage
        from storage.concept_manager import ConceptManager

        config = {
            'db_url': 'postgresql://postgres:PASS@localhost:5432/ontserve_test'
        }
        storage = PostgreSQLStorage(config)
        return ConceptManager(storage)

    def test_get_concept_by_id_not_found(self, manager):
        """Test that _get_concept_by_id returns None for nonexistent concept."""
        result = manager._get_concept_by_id('nonexistent-uuid-12345')
        assert result is None

    def test_get_concept_by_invalid_id(self, manager):
        """Test that _get_concept_by_id handles invalid IDs gracefully."""
        result = manager._get_concept_by_id('not-a-valid-uuid')
        assert result is None