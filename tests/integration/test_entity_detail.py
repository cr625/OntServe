"""
Integration tests for entity detail routes.

Tests the /entity/<name>/<fragment> route including cross-ontology fallback.
"""

import pytest


@pytest.mark.integration
class TestEntityDetailRoute:
    """Test entity detail page routes."""

    def test_entity_detail_found(self, client, db_session, helpers):
        """Entity detail page returns 200 for existing entity."""
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-detail')
        entity = OntologyEntity(
            ontology_id=ontology.id,
            entity_type='class',
            uri='http://test.org/test-detail#Engineer',
            label='Engineer',
            comment='A professional engineer',
            content_hash=OntologyEntity.compute_content_hash(
                'http://test.org/test-detail#Engineer', 'Engineer', 'A professional engineer'
            )
        )
        db_session.add(entity)
        db_session.commit()

        response = client.get('/entity/test-detail/Engineer')
        assert response.status_code == 200

    def test_entity_detail_not_found(self, client, db_session, helpers):
        """Entity detail page returns 404 for missing entity."""
        helpers.create_test_ontology(db_session, name='test-404')

        response = client.get('/entity/test-404/NonExistent')
        assert response.status_code == 404

    def test_entity_detail_missing_ontology(self, client, db_session):
        """Entity detail page returns 404 for missing ontology (falls through to cross-search)."""
        response = client.get('/entity/no-such-ontology/SomeEntity')
        assert response.status_code == 404


@pytest.mark.integration
class TestCrossOntologyFallback:
    """Test cross-ontology entity lookup fallback.

    When an entity isn't found in the named ontology, the route should
    search across all ontologies by URI fragment. This handles the case
    where ProEthica targets 'proethica-intermediate' but entities live
    in 'proethica-intermediate-extended'.
    """

    def test_fallback_finds_entity_in_other_ontology(self, client, db_session, helpers):
        """Entity found via cross-ontology search when not in named ontology."""
        from web.models import OntologyEntity

        # Create two ontologies -- entity lives in 'extended', not 'primary'
        helpers.create_test_ontology(db_session, name='primary')
        extended = helpers.create_test_ontology(db_session, name='extended')

        entity = OntologyEntity(
            ontology_id=extended.id,
            entity_type='class',
            uri='http://test.org/extended#SharedEntity',
            label='SharedEntity',
            comment='Lives in extended only',
            content_hash=OntologyEntity.compute_content_hash(
                'http://test.org/extended#SharedEntity', 'SharedEntity', 'Lives in extended only'
            )
        )
        db_session.add(entity)
        db_session.commit()

        # Request via 'primary' ontology name -- should fallback to extended
        response = client.get('/entity/primary/SharedEntity')
        assert response.status_code == 200

    def test_fallback_prefers_named_ontology(self, client, db_session, helpers):
        """When entity exists in both ontologies, named ontology takes precedence."""
        from web.models import OntologyEntity

        primary = helpers.create_test_ontology(db_session, name='ont-primary')
        secondary = helpers.create_test_ontology(db_session, name='ont-secondary')

        # Same fragment in both
        for ont, comment in [(primary, 'From primary'), (secondary, 'From secondary')]:
            entity = OntologyEntity(
                ontology_id=ont.id,
                entity_type='class',
                uri=f'http://test.org/{ont.name}#DualEntity',
                label='DualEntity',
                comment=comment,
                content_hash=OntologyEntity.compute_content_hash(
                    f'http://test.org/{ont.name}#DualEntity', 'DualEntity', comment
                )
            )
            db_session.add(entity)
        db_session.commit()

        response = client.get('/entity/ont-primary/DualEntity')
        assert response.status_code == 200
        # Should show the primary ontology's version
        assert b'From primary' in response.data
