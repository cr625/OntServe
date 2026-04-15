"""
Integration tests for SPARQLService loading behavior.

The KI2026 paper claims that OntServe's SPARQL endpoint serves the full
134-ontology graph. Historically the service hardcoded five TTL files
and ignored the database, which silently broke that claim. These tests
guard both paths:

1. Filesystem fallback loads at least the core + intermediate + cases
   ontologies that ship in the repository, and SPARQL queries against
   proethica-core.ttl return results.
2. Database loading (simulated via a duck-typed storage stub) pulls
   every current ``ontology_versions`` row and merges their contents
   into the graph. The Case 72 fixture flows through exactly the same
   SQL column shape the real database uses, so a reviewer can verify
   that the path that runs in production actually parses case
   ontologies.
"""

from pathlib import Path

import pytest

from services.sparql_service import SPARQLService


PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURE_CASE_72 = PROJECT_ROOT / "fixtures" / "cases" / "case_072.ttl"
ONTOLOGIES_DIR = PROJECT_ROOT / "ontologies"


class _StubConnection:
    """Minimal psycopg2 connection stub that returns canned rows."""

    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _StubCursor(self._rows)


class _StubCursor:
    def __init__(self, rows):
        self._rows = rows
        self._executed = False

    def execute(self, query, params=None):
        self._executed = True

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _StubStorage:
    """Duck-typed PostgreSQLStorage that hands SPARQLService canned rows.

    Matches the subset of the real API SPARQLService calls:
    ``_get_connection()`` and ``_return_connection()``.
    """

    def __init__(self, rows):
        self._conn = _StubConnection(rows)

    def _get_connection(self):
        return self._conn

    def _return_connection(self, conn):
        pass


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.integration
def test_filesystem_fallback_loads_core_ontology():
    """Without a DB, the service falls back to the bundled TTL files."""
    service = SPARQLService(ontology_storage_path=str(ONTOLOGIES_DIR))
    status = service.get_service_status()

    assert status["load_source"] == "filesystem"
    assert status["ontology_count"] >= 1
    assert "proethica-core.ttl" in status["loaded_ontologies"]
    assert status["total_triples"] > 0


@pytest.mark.integration
def test_filesystem_fallback_exposes_defeasibility_properties():
    """The three defeasibility object properties from the core ontology
    must be queryable against the filesystem-fallback graph."""
    service = SPARQLService(ontology_storage_path=str(ONTOLOGIES_DIR))

    result = service.execute_query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT ?p WHERE {
            VALUES ?p { core:competesWith core:prevailsOver core:defeasibleUnder }
            ?p a owl:ObjectProperty .
        }
        """
    )
    bindings = result["results"]["bindings"]
    found = {b["p"]["value"] for b in bindings}
    assert found == {
        "http://proethica.org/ontology/core#competesWith",
        "http://proethica.org/ontology/core#prevailsOver",
        "http://proethica.org/ontology/core#defeasibleUnder",
    }


@pytest.mark.integration
def test_database_loader_merges_case_ontology_into_graph():
    """Simulate the DB path by handing the service a case TTL row.

    Uses the same column order the real SQL JOIN returns:
    (name, domain_name, base_uri, content).
    """
    core_content = _read(ONTOLOGIES_DIR / "proethica-core.ttl")
    intermediate_content = _read(ONTOLOGIES_DIR / "proethica-intermediate.ttl")
    case_72_content = _read(FIXTURE_CASE_72)

    # Remove owl:imports from the case content before handing it to the
    # service so parsing does not try to fetch network imports.
    stub_rows = [
        ("proethica-core", "engineering-ethics", "http://proethica.org/ontology/core#", core_content),
        ("proethica-intermediate", "engineering-ethics", "http://proethica.org/ontology/intermediate#", intermediate_content),
        ("proethica-case-72", "engineering-ethics", "http://proethica.org/ontology/case/72#", case_72_content),
    ]

    service = SPARQLService(db_storage=_StubStorage(stub_rows))
    status = service.get_service_status()

    assert status["load_source"] == "database"
    assert status["ontology_count"] == 3

    result = service.execute_query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        SELECT ?a ?b WHERE { ?a core:competesWith ?b }
        """
    )
    bindings = result["results"]["bindings"]
    assert len(bindings) >= 1
    assert any(
        b["a"]["value"] == "http://proethica.org/ontology/case/72#Obl_FaithfulAgent"
        for b in bindings
    )


@pytest.mark.integration
def test_reload_clears_and_repopulates_graph():
    """reload() must zero the graph and re-run the loader."""
    service = SPARQLService(ontology_storage_path=str(ONTOLOGIES_DIR))
    baseline_triples = len(service.graph)
    assert baseline_triples > 0

    reload_status = service.reload()
    assert reload_status["source"] == "filesystem"
    assert reload_status["triples"] == baseline_triples


# ---------------------------------------------------------------------------
# ASK / CONSTRUCT result envelopes
#
# The paper-claim verifier posts an ASK query, and several downstream clients
# (including the KI2026 review workflow) will consume ASK. rdflib's Result
# for ASK has vars=None, which the SELECT-only binding loop trips over.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ask_query_returns_sparql_json_boolean_envelope():
    """ASK must return the SPARQL 1.1 ``{head: {}, boolean: bool}`` shape."""
    service = SPARQLService(ontology_storage_path=str(ONTOLOGIES_DIR))
    result = service.execute_query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        ASK { core:competesWith a owl:ObjectProperty }
        """
    )
    assert result == {"head": {}, "boolean": True}


@pytest.mark.integration
def test_ask_query_returns_false_for_missing_triple():
    """ASK must return boolean False when the pattern doesn't match."""
    service = SPARQLService(ontology_storage_path=str(ONTOLOGIES_DIR))
    result = service.execute_query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        ASK { core:thisPredicateDoesNotExist <http://example.org/x> <http://example.org/y> }
        """
    )
    assert result == {"head": {}, "boolean": False}


@pytest.mark.integration
def test_construct_query_returns_turtle_serialization():
    """CONSTRUCT must return the resulting graph as a turtle string."""
    service = SPARQLService(ontology_storage_path=str(ONTOLOGIES_DIR))
    result = service.execute_query(
        """
        PREFIX core: <http://proethica.org/ontology/core#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        CONSTRUCT { ?p a owl:ObjectProperty }
        WHERE {
            VALUES ?p { core:competesWith core:prevailsOver core:defeasibleUnder }
            ?p a owl:ObjectProperty .
        }
        """
    )
    assert "graph" in result["results"]
    turtle = result["results"]["graph"]
    assert "competesWith" in turtle
    assert "prevailsOver" in turtle
    assert "defeasibleUnder" in turtle


# ---------------------------------------------------------------------------
# Real-database loader shape
#
# Guards the commit message "serve the full graph from PostgreSQL, not five
# hardcoded files." The stub-based test above exercises row parsing but
# bypasses the SQL JOIN that silently dropped 129/134 ontologies when the
# loader required a non-null domain_id. This test runs the real SQL against
# the local ontserve DB (gated on ONTSERVE_DB_URL like the rest of the DB
# tests) and asserts the loader picks up every current ontology version.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.database
def test_database_loader_picks_up_every_current_version(pg_storage):
    """SPARQLService must load one ontology per current ontology_versions row."""
    conn = pg_storage._get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT count(*) FROM ontology_versions WHERE is_current = TRUE"
        )
        expected_count = cursor.fetchone()[0]
    finally:
        pg_storage._return_connection(conn)

    service = SPARQLService(db_storage=pg_storage)
    status = service.get_service_status()

    assert status["load_source"] == "database"
    assert status["ontology_count"] == expected_count, (
        f"Expected {expected_count} ontologies from the real DB, "
        f"got {status['ontology_count']}. A missing LEFT JOIN on domains "
        "is the usual culprit."
    )
    assert status["total_triples"] > 0
