"""
Serialization formats of ontology content and their conversion to Turtle.

Every OntologyVersion holds Turtle: the ontology page, the SPARQL loader and
the extractors parse version content with ``format='turtle'``. The web import
(web/services/ontology_import.py) and tools/import_external_collection.py
convert what they receive with the functions below.

rdflib parses RDF/XML, Turtle, N-Triples, N3 and JSON-LD. OWL functional
syntax and OWL/XML go through py-horned-owl (``pip install py-horned-owl``,
listed in requirements.txt), which writes RDF/XML for rdflib to read. Its
RDF/XML types every plain literal as xsd:string and declares none of the
prefixes of the source, so the conversion turns those literals back into
plain literals (the RDF 1.1 equivalent) and binds the prefixes declared in the
source text.

``graph_to_turtle(graph, canonical=True)`` relabels blank nodes from the graph
structure (rdflib.compare.to_canonical_graph), so equal graphs give equal
Turtle text and equal content hashes.
"""

import re
from typing import Iterable, Optional, Tuple, Union
from urllib.parse import urlparse

from rdflib import Graph, Literal, XSD
from rdflib.compare import to_canonical_graph

TURTLE = 'turtle'
RDFXML = 'xml'
NTRIPLES = 'nt'
N3 = 'n3'
JSONLD = 'json-ld'
OFN = 'ofn'
OWX = 'owx'

RDFLIB_FORMATS = (TURTLE, RDFXML, NTRIPLES, N3, JSONLD)
HORNED_FORMATS = (OFN, OWX)
FORMATS = RDFLIB_FORMATS + HORNED_FORMATS

_ALIASES = {
    'turtle': TURTLE, 'ttl': TURTLE, 'text/turtle': TURTLE,
    'xml': RDFXML, 'rdf': RDFXML, 'rdfxml': RDFXML, 'rdf/xml': RDFXML, 'rdf-xml': RDFXML,
    'application/rdf+xml': RDFXML,
    'nt': NTRIPLES, 'ntriples': NTRIPLES, 'n-triples': NTRIPLES,
    'n3': N3,
    'json-ld': JSONLD, 'jsonld': JSONLD, 'json': JSONLD,
    'ofn': OFN, 'functional': OFN, 'owl-functional': OFN,
    'owx': OWX, 'owl/xml': OWX, 'owl-xml': OWX, 'owlxml': OWX,
}

# Extensions that name one format. .owl and .xml carry RDF/XML, OWL/XML or
# functional syntax (SOMA writes functional syntax to .owl files), so for
# those the content decides.
_EXTENSIONS = {
    '.ttl': TURTLE, '.rdf': RDFXML, '.nt': NTRIPLES, '.n3': N3,
    '.jsonld': JSONLD, '.json': JSONLD, '.ofn': OFN, '.owx': OWX,
}
_AMBIGUOUS_EXTENSIONS = ('.owl', '.xml')

_OFN_PREFIX = re.compile(r'Prefix\(\s*([A-Za-z_][\w.-]*)?:=<([^>]*)>\s*\)')
_OWX_PREFIX = re.compile(r'<(?:\w+:)?Prefix\s+name="([^"]*)"\s+IRI="([^"]*)"')
_XML_ROOT = re.compile(r'<([A-Za-z_][\w.:-]*)')


class ConversionError(ValueError):
    """Content that cannot be read in the stated or detected format."""


def normalize_format(name: Optional[str]) -> Optional[str]:
    """The rdflib or py-horned-owl name of a format given by name, alias or
    media type, or None for an empty value."""
    if name is None or not str(name).strip():
        return None
    fmt = _ALIASES.get(str(name).strip().lower())
    if fmt is None:
        raise ConversionError(f"Unknown serialization format: {name}")
    return fmt


def _text(content: Union[str, bytes]) -> str:
    return content.decode('utf-8', errors='replace') if isinstance(content, bytes) else content


def sniff_format(content: Union[str, bytes]) -> Optional[str]:
    """The format the opening text of ``content`` shows, or None when it shows none."""
    head = _text(content[:8192])
    body = '\n'.join(line for line in head.splitlines()
                     if line.strip() and not line.lstrip().startswith('#'))
    start = body.lstrip()
    if start.startswith(('Prefix(', 'Ontology(')):
        return OFN
    if start.startswith(('{', '[')):
        return JSONLD
    if start.startswith('<'):
        # The first element after the XML declaration, comments and DOCTYPE
        stripped = re.sub(r'<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^\[>]*(\[.*?\])?\s*>', '', start, flags=re.S)
        root = _XML_ROOT.search(stripped)
        if root:
            name = root.group(1)
            if name == 'RDF' or name.endswith(':RDF'):
                return RDFXML
            if (name == 'Ontology' or name.endswith(':Ontology')) and 'ontologyIRI' in stripped[:2000]:
                return OWX
            if '=' in stripped[:200] or 'xmlns' in stripped[:2000]:
                return RDFXML
        return None
    if re.match(r'(@prefix|@base|PREFIX|BASE)\b', start):
        return TURTLE
    return None


def detect_format(filename: Optional[str] = None, content: Union[str, bytes, None] = None,
                  hint: Optional[str] = None) -> str:
    """The format of a file: the hint when given, else the extension when it
    names one format, else the opening text, else RDF/XML for .owl/.xml and
    Turtle for anything else."""
    fmt = normalize_format(hint)
    if fmt:
        return fmt
    ext = ''
    if filename:
        path = urlparse(filename).path if '://' in filename else filename
        dot = path.rfind('.')
        ext = path[dot:].lower() if dot > path.rfind('/') else ''
    if ext in _EXTENSIONS:
        return _EXTENSIONS[ext]
    sniffed = sniff_format(content) if content else None
    if sniffed:
        return sniffed
    return RDFXML if ext in _AMBIGUOUS_EXTENSIONS else TURTLE


def declared_prefixes(content: Union[str, bytes], fmt: str) -> Iterable[Tuple[str, str]]:
    """(prefix, namespace) pairs declared in functional syntax or OWL/XML text,
    in source order. py-horned-owl drops them from its RDF/XML."""
    pattern = _OFN_PREFIX if fmt == OFN else _OWX_PREFIX
    for prefix, namespace in pattern.findall(_text(content)):
        yield (prefix or ''), namespace


def _prefix_from_namespace(namespace: str) -> Optional[str]:
    """A prefix name for a namespace declared with the empty prefix: the last
    path segment without its extension (.../ont/SOMA-ACT.owl# -> SOMA-ACT)."""
    segment = urlparse(namespace).path.rstrip('/#').rsplit('/', 1)[-1]
    segment = re.sub(r'\.(owl|rdf|ttl|ofn|owx|xml)$', '', segment)
    segment = re.sub(r'[^A-Za-z0-9_-]', '', segment)
    return segment if re.match(r'[A-Za-z]', segment or '') else None


def bind_prefixes(graph: Graph, pairs: Iterable[Tuple[str, str]]) -> Graph:
    """Bind source prefixes on ``graph``, first binding of a namespace or a
    prefix wins. The empty prefix is bound under a name derived from its
    namespace, so merged sources do not compete for it."""
    bound_ns = {str(ns) for _, ns in graph.namespaces()}
    bound_prefix = {p: str(ns) for p, ns in graph.namespaces()}
    for prefix, namespace in pairs:
        namespace = str(namespace)
        if not namespace or namespace in bound_ns:
            continue
        name = prefix or _prefix_from_namespace(namespace)
        if not name or bound_prefix.get(name, namespace) != namespace:
            continue
        graph.bind(name, namespace, override=False, replace=False)
        bound_ns.add(namespace)
        bound_prefix[name] = namespace
    return graph


def plain_string_literals(graph: Graph) -> Graph:
    """Replace xsd:string typed literals with plain literals, in place."""
    typed = [t for t in graph if isinstance(t[2], Literal) and t[2].datatype == XSD.string]
    for s, p, o in typed:
        graph.remove((s, p, o))
        graph.add((s, p, Literal(str(o))))
    return graph


def _graph_via_horned_owl(content: Union[str, bytes], fmt: str) -> Graph:
    try:
        import pyhornedowl
    except ImportError as exc:
        raise ConversionError(
            "OWL functional syntax and OWL/XML need the py-horned-owl package "
            "(pip install py-horned-owl)") from exc
    text = _text(content)
    try:
        rdfxml = pyhornedowl.open_ontology_from_string(text, fmt).save_to_string('owl')
    except Exception as exc:  # py-horned-owl raises ValueError with the parser position
        raise ConversionError(f"py-horned-owl could not read the {fmt} content: {exc}") from exc
    graph = Graph()
    graph.parse(data=rdfxml, format=RDFXML)
    plain_string_literals(graph)
    return bind_prefixes(graph, declared_prefixes(text, fmt))


def graph_from_content(content: Union[str, bytes], fmt: str, public_id: Optional[str] = None) -> Graph:
    """Parse ``content`` in format ``fmt`` (any name normalize_format accepts)
    into a new graph. ``public_id`` is the base IRI for relative references."""
    fmt = normalize_format(fmt) or TURTLE
    if fmt in HORNED_FORMATS:
        return _graph_via_horned_owl(content, fmt)
    graph = Graph()
    try:
        graph.parse(data=content, format=fmt, publicID=public_id)
    except Exception as exc:  # rdflib raises parser-specific exception types
        raise ConversionError(f"Could not parse the content as {fmt}: {exc}") from exc
    return graph


def graph_to_turtle(graph: Graph, canonical: bool = False) -> str:
    """Turtle text of ``graph``. With ``canonical``, blank nodes are relabelled
    from the graph structure first, so the text depends only on the triples
    and the prefix bindings."""
    if canonical:
        out = Graph()
        for prefix, namespace in graph.namespaces():
            out.bind(prefix, namespace, override=True, replace=True)
        for triple in to_canonical_graph(graph):
            out.add(triple)
        graph = out
    return graph.serialize(format=TURTLE)


def to_turtle(content: Union[str, bytes], fmt: str, public_id: Optional[str] = None,
              canonical: bool = False) -> str:
    """Turtle text of ``content``. Turtle input is checked by parsing and kept
    as written (comments and layout included). Other formats are parsed and
    serialized."""
    fmt = normalize_format(fmt) or TURTLE
    graph = graph_from_content(content, fmt, public_id)
    if fmt == TURTLE and not canonical:
        return _text(content)
    return graph_to_turtle(graph, canonical=canonical)
