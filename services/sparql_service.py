"""
SPARQL Service for OntServe.

Serves a single in-memory ``rdflib.Graph`` that aggregates every
published ontology known to OntServe. On startup the service prefers
loading current ontology versions directly from PostgreSQL (matching
the paper's claim that the SPARQL endpoint serves the full graph of
134 ontologies). When no database backend is available -- e.g. the
unit-test environment or a DB-less dev run -- it falls back to the
small set of TTL files under ``ontologies/``.

Wiring: ``servers/mcp_server.py`` constructs ``SPARQLService`` after
``PostgreSQLStorage`` has come up and passes ``db_storage=storage`` so
the SPARQL endpoint sees every published case ontology, external
ontology, and domain ontology in the database.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

logger = logging.getLogger(__name__)

# Namespaces bound on the shared graph for cleaner queries
PROETHICA_CORE = Namespace("http://proethica.org/ontology/core#")
PROETHICA_INTERMEDIATE = Namespace("http://proethica.org/ontology/intermediate#")
PROETHICA_CASES = Namespace("http://proethica.org/ontology/cases#")
ENGINEERING_ETHICS = Namespace("http://proethica.org/ontology/engineering-ethics#")

# Fallback file list (used only when no DB storage is attached)
_FALLBACK_TTL_FILES = (
    "proethica-core.ttl",
    "proethica-intermediate.ttl",
    "proethica-cases.ttl",
    "proethica-provenance.ttl",
    "engineering-ethics.ttl",
)


class SPARQLService:
    """Execute SPARQL queries over every ontology OntServe knows about.

    The graph is populated either from the PostgreSQL ``ontology_versions``
    table (preferred, production path) or from the TTL files in the
    repository's ``ontologies/`` directory (fallback, dev/test path).
    """

    def __init__(
        self,
        ontology_storage_path: Optional[str] = None,
        db_storage=None,
    ):
        """Initialize the service and load the graph.

        Args:
            ontology_storage_path: Filesystem directory holding TTL files
                for the fallback loader. Defaults to ``<project>/ontologies``.
            db_storage: Optional ``PostgreSQLStorage`` instance. When
                provided, the service loads every current ontology version
                directly from the database and ignores the filesystem.
        """
        self.graph = Graph()
        self.db_storage = db_storage
        self.ontology_path = ontology_storage_path or self._default_ontology_path()
        self.loaded_ontologies: List[str] = []
        self.load_source: str = "unloaded"

        # Bind namespaces once; reload() re-uses the same graph instance
        # so these stay live.
        self.graph.bind("proeth-core", PROETHICA_CORE)
        self.graph.bind("proeth", PROETHICA_INTERMEDIATE)
        self.graph.bind("proeth-cases", PROETHICA_CASES)
        self.graph.bind("eng-ethics", ENGINEERING_ETHICS)
        self.graph.bind("rdfs", RDFS)
        self.graph.bind("skos", SKOS)
        self.graph.bind("dcterms", DCTERMS)

        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _default_ontology_path(self) -> str:
        return str(Path(__file__).parent.parent / "ontologies")

    def _load(self) -> None:
        """Load ontologies into ``self.graph`` using the best available source."""
        if self.db_storage is not None:
            try:
                self._load_from_database()
                return
            except Exception as exc:
                logger.warning(
                    "Database ontology load failed (%s); falling back to filesystem",
                    exc,
                )
        self._load_from_filesystem()

    def _load_from_database(self) -> None:
        """Load every current ontology version from PostgreSQL.

        Issues a single JOIN query so 134 ontologies cost one round-trip
        rather than 134. Uses the psycopg2 connection pool already owned
        by ``PostgreSQLStorage``.
        """
        conn = self.db_storage._get_connection()
        try:
            cursor = conn.cursor()
            # LEFT JOIN on domains: domain_name is used only as a label in
            # logs and the loaded_ontologies list, not for query semantics,
            # so ontologies without a domain must still be served.
            cursor.execute(
                """
                SELECT o.name, d.name AS domain_name, o.base_uri, ov.content
                FROM ontologies o
                LEFT JOIN domains d ON o.domain_id = d.id
                JOIN ontology_versions ov ON ov.ontology_id = o.id
                WHERE ov.is_current = TRUE
                ORDER BY d.name NULLS LAST, o.name
                """
            )
            rows = cursor.fetchall()
        finally:
            self.db_storage._return_connection(conn)

        loaded: List[str] = []
        parse_errors: List[str] = []

        for row in rows:
            # psycopg2 cursor returns tuples; defensive index access keeps
            # us compatible with RealDictCursor if it ever gets swapped in.
            if isinstance(row, dict):
                name = row['name']
                domain = row['domain_name']
                content = row['content']
            else:
                name, domain, _base, content = row

            if not content:
                continue

            fmt = _detect_format(content)
            label = f"{domain}:{name}" if domain else name
            try:
                self.graph.parse(data=content, format=fmt)
                loaded.append(label)
            except Exception as exc:
                parse_errors.append(f"{label} ({fmt}): {exc}")
                logger.warning("Failed to parse ontology %s as %s: %s", label, fmt, exc)

        self.loaded_ontologies = loaded
        self.load_source = "database"
        logger.info(
            "SPARQL service loaded %d ontologies from database (%d parse errors); "
            "graph now has %d triples",
            len(loaded),
            len(parse_errors),
            len(self.graph),
        )

    def _load_from_filesystem(self) -> None:
        """Parse the repository's bundled TTL files into the graph."""
        if not os.path.exists(self.ontology_path):
            logger.warning("Ontology path does not exist: %s", self.ontology_path)
            self.load_source = "unloaded"
            return

        loaded: List[str] = []
        for filename in _FALLBACK_TTL_FILES:
            filepath = os.path.join(self.ontology_path, filename)
            if not os.path.exists(filepath):
                continue
            try:
                self.graph.parse(filepath, format="turtle")
                loaded.append(filename)
            except Exception as exc:
                logger.error("Failed to load ontology %s: %s", filename, exc)

        self.loaded_ontologies = loaded
        self.load_source = "filesystem"
        logger.info(
            "SPARQL service loaded %d ontologies from filesystem; graph has %d triples",
            len(loaded),
            len(self.graph),
        )

    def reload(self) -> Dict[str, Any]:
        """Reset the graph and reload from the configured source.

        Call after the editor writes a new ontology version so the SPARQL
        endpoint reflects the change without a process restart.
        """
        self.graph.remove((None, None, None))
        self._load()
        return {
            "source": self.load_source,
            "ontologies_loaded": len(self.loaded_ontologies),
            "triples": len(self.graph),
        }

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def execute_query(self, query: str) -> Dict[str, Any]:
        """Execute a SPARQL query and return SPARQL JSON results.

        SELECT returns the standard ``{head: {vars}, results: {bindings}}``
        envelope. ASK returns ``{head: {}, boolean: bool}`` per the SPARQL
        1.1 JSON Results spec. CONSTRUCT and DESCRIBE return the graph
        serialized as turtle under ``results.graph`` (non-standard but
        JSON-serializable; consumers that want raw RDF should use a
        content-negotiating endpoint instead).
        """
        try:
            logger.debug("Executing SPARQL query: %s...", query[:200])
            results = self.graph.query(query)

            if results.type == "ASK":
                return {"head": {}, "boolean": bool(results.askAnswer)}

            if results.type in ("CONSTRUCT", "DESCRIBE"):
                return {
                    "head": {},
                    "results": {
                        "graph": results.serialize(format="turtle").decode("utf-8"),
                    },
                }

            bindings = []
            for row in results:
                binding: Dict[str, Dict[str, str]] = {}
                for var_name, value in zip(results.vars, row):
                    var_key = str(var_name)
                    if value is None:
                        continue
                    if isinstance(value, URIRef):
                        binding[var_key] = {"type": "uri", "value": str(value)}
                    elif isinstance(value, Literal):
                        b: Dict[str, str] = {"type": "literal", "value": str(value)}
                        if value.datatype:
                            b["datatype"] = str(value.datatype)
                        if value.language:
                            b["xml:lang"] = str(value.language)
                        binding[var_key] = b
                    else:
                        binding[var_key] = {"type": "literal", "value": str(value)}
                bindings.append(binding)

            return {
                "head": {"vars": [str(v) for v in results.vars]},
                "results": {"bindings": bindings},
            }
        except Exception as exc:
            logger.error("SPARQL query execution failed: %s", exc)
            raise ValueError(f"SPARQL query error: {exc}")

    def get_service_status(self) -> Dict[str, Any]:
        """Return service status information (for /health and diagnostics)."""
        return {
            "service": "SPARQL",
            "status": "available" if self.loaded_ontologies else "no_ontologies",
            "load_source": self.load_source,
            "loaded_ontologies": list(self.loaded_ontologies),
            "ontology_count": len(self.loaded_ontologies),
            "total_triples": len(self.graph),
            "ontology_path": self.ontology_path,
            "available_namespaces": [
                (prefix, str(uri)) for prefix, uri in self.graph.namespaces()
            ],
        }

    def validate_query(self, query: str) -> Dict[str, Any]:
        """Validate SPARQL syntax without executing."""
        try:
            self.graph.query(query, dryrun=True)
            return {"valid": True, "message": "Query syntax is valid"}
        except Exception as exc:
            return {"valid": False, "error": str(exc)}


def _detect_format(content: str) -> str:
    """Best-effort RDF format detection from serialized content."""
    if not content:
        return "turtle"
    stripped = content.lstrip()
    if stripped.startswith("<?xml") or stripped.startswith("<rdf:RDF"):
        return "xml"
    if stripped.startswith("{") or stripped.startswith("["):
        return "json-ld"
    return "turtle"
