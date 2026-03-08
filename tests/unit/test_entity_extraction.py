"""
Unit tests for entity extraction from ontology content.

Tests the 5-pass extraction: classes, object properties, datatype properties,
named individuals, and catch-all for domain-typed/bare resources.
"""

import pytest
from datetime import datetime, timezone


SAMPLE_CLASS_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix test: <http://test.org/ontology#> .

test:Engineer a owl:Class ;
    rdfs:label "Engineer" ;
    rdfs:comment "A professional engineer" ;
    rdfs:subClassOf test:Role .

test:Principle a owl:Class ;
    rdfs:label "Principle" ;
    rdfs:comment "An ethical principle" .
"""

SAMPLE_PROPERTY_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix test: <http://test.org/ontology#> .

test:hasRole a owl:ObjectProperty ;
    rdfs:label "has role" ;
    rdfs:comment "Links an agent to their role" ;
    rdfs:domain test:Agent ;
    rdfs:range test:Role .

test:hasName a owl:DatatypeProperty ;
    rdfs:label "has name" ;
    rdfs:comment "The name of an entity" .
"""

SAMPLE_INDIVIDUAL_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix proeth: <http://proethica.org/ontology/intermediate#> .
@prefix case7: <http://proethica.org/ontology/case/7#> .

case7:EngineerA a owl:NamedIndividual, proeth:ProfessionalEngineerRole ;
    rdfs:label "Engineer A" ;
    rdfs:comment "The primary engineer in the case" ;
    proeth:conceptCategory "roles" ;
    proeth:confidence "0.95" ;
    proeth:sourcetext "Engineer A was retained by Client W" ;
    prov:generatedAtTime "2026-01-01T00:00:00" .
"""

SAMPLE_CATCH_ALL_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix proeth: <http://proethica.org/ontology/intermediate#> .
@prefix asce: <http://proethica.org/ontology/asce#> .

<http://proethica.org/ontology/asce> a owl:Ontology ;
    rdfs:label "ASCE Code of Ethics" .

asce:Canon1 a proeth:Principle ;
    rdfs:label "Canon 1" ;
    rdfs:comment "Hold paramount the safety, health, and welfare of the public" .

asce:Canon2 a proeth:Obligation ;
    rdfs:label "Canon 2" ;
    rdfs:comment "Perform services only in areas of competence" .
"""

SAMPLE_MIXED_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix proeth: <http://proethica.org/ontology/intermediate#> .
@prefix case1: <http://proethica.org/ontology/case/1#> .

proeth:Role a owl:Class ;
    rdfs:label "Role" ;
    rdfs:comment "A role in the case" .

proeth:hasRole a owl:ObjectProperty ;
    rdfs:label "has role" .

case1:EngineerA a owl:NamedIndividual, proeth:Role ;
    rdfs:label "Engineer A" ;
    proeth:conceptCategory "roles" .

case1:Canon1 a proeth:Principle ;
    rdfs:label "Canon 1" ;
    rdfs:comment "Safety first" .
"""


@pytest.mark.unit
class TestClassExtraction:
    """Test Pass 1: OWL class extraction."""

    def test_extracts_classes(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content

        ontology = helpers.create_test_ontology(db_session, name='test-classes')
        counts = extract_entities_from_content(ontology, SAMPLE_CLASS_TTL)
        db_session.commit()

        assert counts['class'] == 2
        assert counts['property'] == 0
        assert counts['individual'] == 0

    def test_class_has_parent_uri(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-class-parent')
        extract_entities_from_content(ontology, SAMPLE_CLASS_TTL)
        db_session.commit()

        engineer = OntologyEntity.query.filter_by(
            ontology_id=ontology.id, label='Engineer'
        ).first()
        assert engineer is not None
        assert engineer.parent_uri == 'http://test.org/ontology#Role'

    def test_class_has_content_hash(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-class-hash')
        extract_entities_from_content(ontology, SAMPLE_CLASS_TTL)
        db_session.commit()

        engineer = OntologyEntity.query.filter_by(
            ontology_id=ontology.id, label='Engineer'
        ).first()
        assert engineer.content_hash is not None
        assert len(engineer.content_hash) == 64  # SHA-256 hex


@pytest.mark.unit
class TestPropertyExtraction:
    """Test Passes 2-3: OWL property extraction."""

    def test_extracts_both_property_types(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content

        ontology = helpers.create_test_ontology(db_session, name='test-props')
        counts = extract_entities_from_content(ontology, SAMPLE_PROPERTY_TTL)
        db_session.commit()

        assert counts['property'] == 2

    def test_object_property_has_domain_range(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-prop-dr')
        extract_entities_from_content(ontology, SAMPLE_PROPERTY_TTL)
        db_session.commit()

        has_role = OntologyEntity.query.filter_by(
            ontology_id=ontology.id, label='has role'
        ).first()
        assert has_role.domain is not None
        assert has_role.range is not None


@pytest.mark.unit
class TestIndividualExtraction:
    """Test Pass 4: Named individual extraction with property collection."""

    def test_extracts_individuals(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content

        ontology = helpers.create_test_ontology(db_session, name='test-indiv')
        counts = extract_entities_from_content(ontology, SAMPLE_INDIVIDUAL_TTL)
        db_session.commit()

        assert counts['individual'] == 1

    def test_individual_has_parent_uri_from_type(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-indiv-parent')
        extract_entities_from_content(ontology, SAMPLE_INDIVIDUAL_TTL)
        db_session.commit()

        eng = OntologyEntity.query.filter_by(
            ontology_id=ontology.id, label='Engineer A'
        ).first()
        assert eng is not None
        assert eng.parent_uri == 'http://proethica.org/ontology/intermediate#ProfessionalEngineerRole'

    def test_individual_properties_json(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-indiv-props')
        extract_entities_from_content(ontology, SAMPLE_INDIVIDUAL_TTL)
        db_session.commit()

        eng = OntologyEntity.query.filter_by(
            ontology_id=ontology.id, label='Engineer A'
        ).first()
        assert eng.properties is not None
        assert eng.properties.get('conceptCategory') == 'roles'
        assert eng.properties.get('confidence') == '0.95'
        assert 'sourcetext' in eng.properties
        assert 'generatedAtTime' in eng.properties

    def test_individual_has_content_hash(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-indiv-hash')
        extract_entities_from_content(ontology, SAMPLE_INDIVIDUAL_TTL)
        db_session.commit()

        eng = OntologyEntity.query.filter_by(
            ontology_id=ontology.id, label='Engineer A'
        ).first()
        expected = OntologyEntity.compute_content_hash(
            eng.uri, 'Engineer A', 'The primary engineer in the case'
        )
        assert eng.content_hash == expected


@pytest.mark.unit
class TestCatchAllExtraction:
    """Test Pass 5: Catch-all for domain-typed and bare resources."""

    def test_extracts_domain_typed_entities(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content

        ontology = helpers.create_test_ontology(db_session, name='test-catchall')
        counts = extract_entities_from_content(ontology, SAMPLE_CATCH_ALL_TTL)
        db_session.commit()

        # 2 domain-typed entities (Canon1, Canon2), ontology declaration skipped
        assert counts['individual'] == 2

    def test_skips_ontology_declaration(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-skip-ont')
        extract_entities_from_content(ontology, SAMPLE_CATCH_ALL_TTL)
        db_session.commit()

        # Should not extract the owl:Ontology declaration as an entity
        ont_entity = OntologyEntity.query.filter_by(
            ontology_id=ontology.id, label='ASCE Code of Ethics'
        ).first()
        assert ont_entity is None

    def test_domain_typed_has_parent_uri(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-catchall-parent')
        extract_entities_from_content(ontology, SAMPLE_CATCH_ALL_TTL)
        db_session.commit()

        canon1 = OntologyEntity.query.filter_by(
            ontology_id=ontology.id, label='Canon 1'
        ).first()
        assert canon1 is not None
        assert canon1.parent_uri == 'http://proethica.org/ontology/intermediate#Principle'


@pytest.mark.unit
class TestMixedExtraction:
    """Test extraction with all entity types in one ontology."""

    def test_extracts_all_types(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content

        ontology = helpers.create_test_ontology(db_session, name='test-mixed')
        counts = extract_entities_from_content(ontology, SAMPLE_MIXED_TTL)
        db_session.commit()

        assert counts['class'] == 1      # Role
        assert counts['property'] == 1   # hasRole
        assert counts['individual'] == 2  # EngineerA (NamedIndividual) + Canon1 (catch-all)

    def test_no_duplicates_across_passes(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-no-dupes')
        extract_entities_from_content(ontology, SAMPLE_MIXED_TTL)
        db_session.commit()

        total = OntologyEntity.query.filter_by(ontology_id=ontology.id).count()
        assert total == 4  # 1 class + 1 property + 2 individuals

    def test_clears_existing_before_extract(self, app, db_session, helpers):
        from web.entity_extraction import extract_entities_from_content
        from web.models import OntologyEntity

        ontology = helpers.create_test_ontology(db_session, name='test-clear')

        # Extract twice -- second should replace, not accumulate
        extract_entities_from_content(ontology, SAMPLE_MIXED_TTL)
        db_session.commit()
        extract_entities_from_content(ontology, SAMPLE_MIXED_TTL)
        db_session.commit()

        total = OntologyEntity.query.filter_by(ontology_id=ontology.id).count()
        assert total == 4


@pytest.mark.unit
class TestContentHash:
    """Test content hash computation."""

    def test_hash_deterministic(self):
        from web.models import OntologyEntity

        h1 = OntologyEntity.compute_content_hash('http://test.org#A', 'Label', 'Comment')
        h2 = OntologyEntity.compute_content_hash('http://test.org#A', 'Label', 'Comment')
        assert h1 == h2

    def test_hash_changes_with_label(self):
        from web.models import OntologyEntity

        h1 = OntologyEntity.compute_content_hash('http://test.org#A', 'Label1', 'Comment')
        h2 = OntologyEntity.compute_content_hash('http://test.org#A', 'Label2', 'Comment')
        assert h1 != h2

    def test_hash_changes_with_comment(self):
        from web.models import OntologyEntity

        h1 = OntologyEntity.compute_content_hash('http://test.org#A', 'Label', 'Comment1')
        h2 = OntologyEntity.compute_content_hash('http://test.org#A', 'Label', 'Comment2')
        assert h1 != h2

    def test_hash_handles_none(self):
        from web.models import OntologyEntity

        h = OntologyEntity.compute_content_hash('http://test.org#A', None, None)
        assert len(h) == 64

    def test_hash_is_sha256_hex(self):
        import hashlib
        from web.models import OntologyEntity

        uri = 'http://test.org#A'
        label = 'TestLabel'
        comment = 'TestComment'

        expected = hashlib.sha256(f"{uri}|{label}|{comment}".encode('utf-8')).hexdigest()
        actual = OntologyEntity.compute_content_hash(uri, label, comment)
        assert actual == expected
