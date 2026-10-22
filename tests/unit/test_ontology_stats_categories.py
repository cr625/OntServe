"""Category counts and Concepts entities must agree (banner vs tab).

Regression: the banner counted classes whose local name contained the
category prefix (EventType, a Principle with Action in its name), while
the Concepts tab listed only direct subclasses, so Events showed 1 in
the banner and "No events found" in the tab. Action and Event keep
their categories in the core layer, merged here as extra TTL.
"""
from web.ontology_stats import compute_category_counts, compute_category_entities

CORE = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix proeth-core: <http://proethica.org/ontology/core#> .

proeth-core:Action a owl:Class ; rdfs:label "Action" .
proeth-core:Event a owl:Class ; rdfs:label "Event" .
proeth-core:AgentCausedEvent a owl:Class ; rdfs:subClassOf proeth-core:Event ; rdfs:label "Agent-Caused Event" .
proeth-core:ExogenousEvent a owl:Class ; rdfs:subClassOf proeth-core:Event ; rdfs:label "Exogenous Event" .
proeth-core:Role a owl:Class ; rdfs:label "Role" .
"""

INTERMEDIATE = """@prefix : <http://proethica.org/ontology/intermediate#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix proeth-core: <http://proethica.org/ontology/core#> .

:EventType a owl:Class ; rdfs:subClassOf :EntityType ; rdfs:label "Event Type" .
:ActionType a owl:Class ; rdfs:subClassOf :EntityType ; rdfs:label "Action Type" .
:CorrectiveActionMonitoringPrinciple a owl:Class ; rdfs:subClassOf proeth-core:Principle ; rdfs:label "Corrective Action Monitoring Principle" .
:ProfessionalRole a owl:Class ; rdfs:subClassOf proeth-core:Role ; rdfs:label "Professional Role" .
"""

CATS = [
    {"label": "Roles", "prefix": "Role"},
    {"label": "Actions", "prefix": "Action"},
    {"label": "Events", "prefix": "Event"},
]


def test_banner_and_concepts_agree_with_core_merged():
    counts = compute_category_counts(INTERMEDIATE, CATS, extra_ttl_content=CORE)
    entities = compute_category_entities(INTERMEDIATE, CATS, extra_ttl_content=CORE)
    for label in counts:
        assert counts[label] == entities[label]["count"]


def test_events_come_from_core_origin_subclasses():
    entities = compute_category_entities(INTERMEDIATE, CATS, extra_ttl_content=CORE)
    labels = {e["label"] for e in entities["Events"]["entities"]}
    assert labels == {"Agent-Caused Event", "Exogenous Event"}
    assert entities["Events"]["count"] == 2


def test_action_category_is_the_core_action_class():
    entities = compute_category_entities(INTERMEDIATE, CATS, extra_ttl_content=CORE)
    labels = {e["label"] for e in entities["Actions"]["entities"]}
    assert labels == {"Action"}


def test_name_containing_classes_are_not_counted():
    counts = compute_category_counts(INTERMEDIATE, CATS, extra_ttl_content=CORE)
    # EventType / ActionType meta-classes and the Action-named Principle
    # must not inflate Events or Actions.
    assert counts["Events"] == 2
    assert counts["Actions"] == 1
    assert counts["Roles"] == 1
