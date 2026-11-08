"""
Source and credit of an ontology: who made it, under which license, where its
content comes from and what OntServe changed.

The credit block is stored on the ontology row at ``meta_data['credit']``.
tools/import_external_collection.py writes it from the ``credit`` mapping of a
collection manifest, after ``normalize_credit`` has checked it:

    title: str
    creators: [str]
    publisher: str                # organisation or project
    license: {id: SPDX id or "none stated", url: str or null}
    source: {repository: url, commit: sha or null, paths: [str], url: str or null}
    homepage: url or null
    citation: {text: str, doi: str or null, url: str or null}
    retrieved: YYYY-MM-DD
    modifications: str            # what OntServe changed
    used_in: [{text: str, reasoner: str}]
    redistribution: hosted | reference-only
    version: str or null          # owl:versionInfo, filled by the header fallback

A row without a credit block takes its credit from the owl:Ontology header of
its current version when its category sets ``header_credit`` (the two
collection categories of services.ontology_categories): dcterms:title,
dcterms:creator or dc:creator, dcterms:license or dc:rights,
dcterms:bibliographicCitation, owl:versionInfo and rdfs:seeAlso. The headers
of the ProEthica ontologies carry dc:creator and owl:versionInfo, so the
fallback is limited to those categories and the ProEthica pages render
without the panel.
"""

import datetime as _dt
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from rdflib import Graph, OWL, RDF, RDFS, URIRef
from rdflib.namespace import DC, DCTERMS

from services import ontology_categories as categories

logger = logging.getLogger(__name__)

CREDIT_KEY = 'credit'
HOSTED = 'hosted'
REFERENCE_ONLY = 'reference-only'
REDISTRIBUTION = (HOSTED, REFERENCE_ONLY)
NO_LICENSE = 'none stated'

_FIELDS = ('title', 'creators', 'publisher', 'license', 'source', 'homepage', 'citation',
           'retrieved', 'modifications', 'used_in', 'redistribution', 'version')
_LICENSE_FIELDS = ('id', 'url')
_SOURCE_FIELDS = ('repository', 'commit', 'paths', 'url')
_CITATION_FIELDS = ('text', 'doi', 'url')
_USED_IN_FIELDS = ('text', 'reasoner')
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_DOI_PREFIX = re.compile(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', re.IGNORECASE)


class CreditError(ValueError):
    """A credit block that does not follow the schema."""


def _str(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _str_list(value: Any) -> List[str]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    return [s for s in (_str(v) for v in items) if s]


def _mapping(value: Any, fields: Tuple[str, ...], main: str, where: str, strict: bool) -> Optional[Dict]:
    """A sub-mapping with exactly ``fields``. A plain string stands for its ``main`` field."""
    if value is None or value == '' or value == {}:
        return None
    if not isinstance(value, dict):
        value = {main: value}
    unknown = sorted(set(value) - set(fields))
    if unknown and strict:
        raise CreditError(f"unknown keys in credit.{where}: {', '.join(unknown)}")
    return {f: (_str_list(value.get(f)) if f == 'paths' else _str(value.get(f))) for f in fields}


def normalize_date(value: Any, strict: bool = True) -> Optional[str]:
    """A YYYY-MM-DD string from a date, a datetime or a string (YAML reads an
    unquoted 2026-11-07 as a date)."""
    if value is None or value == '':
        return None
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()[:10]
    value = str(value).strip()
    if not _DATE.match(value):
        if strict:
            raise CreditError(f"credit.retrieved is not a YYYY-MM-DD date: {value}")
        return value or None
    return value


def normalize_credit(raw: Any, retrieved: Any = None, strict: bool = True) -> Dict[str, Any]:
    """The credit block in its stored shape: every key present, absent values
    None or empty lists. ``retrieved`` applies when the block has none (the
    manifest-wide date). With ``strict``, unknown keys, a missing title or
    license, an unknown redistribution value and a reference-only block
    without a source link raise CreditError. Without it, the block is coerced
    for display."""
    if not isinstance(raw, dict):
        raise CreditError('the credit block is not a mapping')
    unknown = sorted(set(raw) - set(_FIELDS))
    if unknown and strict:
        raise CreditError(f"unknown credit keys: {', '.join(unknown)}")

    items = raw.get('used_in') or []
    if isinstance(items, (str, dict)):
        items = [items]
    used_in = []
    for item in items:
        entry = _mapping(item, _USED_IN_FIELDS, 'text', 'used_in', strict)
        if entry and entry['text']:
            used_in.append(entry)

    redistribution = _str(raw.get('redistribution')) or HOSTED
    if redistribution not in REDISTRIBUTION:
        if strict:
            raise CreditError(f"credit.redistribution must be one of {', '.join(REDISTRIBUTION)}: {redistribution}")
        redistribution = HOSTED

    credit = {
        'title': _str(raw.get('title')),
        'creators': _str_list(raw.get('creators')),
        'publisher': _str(raw.get('publisher')),
        'license': _mapping(raw.get('license'), _LICENSE_FIELDS, 'id', 'license', strict),
        'source': _mapping(raw.get('source'), _SOURCE_FIELDS, 'repository', 'source', strict),
        'homepage': _str(raw.get('homepage')),
        'citation': _mapping(raw.get('citation'), _CITATION_FIELDS, 'text', 'citation', strict),
        'retrieved': normalize_date(raw.get('retrieved') or retrieved, strict),
        'modifications': _str(raw.get('modifications')),
        'used_in': used_in,
        'redistribution': redistribution,
        'version': _str(raw.get('version')),
    }
    if credit['citation'] and credit['citation']['doi']:
        credit['citation']['doi'] = _DOI_PREFIX.sub('', credit['citation']['doi'])
    if strict:
        if not credit['title']:
            raise CreditError('credit.title is required')
        if not (credit['license'] and credit['license']['id']):
            raise CreditError(f'credit.license.id is required (an SPDX id or "{NO_LICENSE}")')
        if redistribution == REFERENCE_ONLY and not source_link(credit):
            raise CreditError('a reference-only credit block needs source.url, source.repository or homepage')
    return credit


def source_link(credit: Optional[Dict[str, Any]]) -> Optional[str]:
    """The address a reader follows to the content: the source file URL, else
    the repository, else the homepage."""
    if not credit:
        return None
    source = credit.get('source') or {}
    return source.get('url') or source.get('repository') or credit.get('homepage')


# ---------------------------------------------------------------------------
# Fallback: the owl:Ontology header
# ---------------------------------------------------------------------------

def _header_subject(graph: Graph, iri: Optional[str]) -> Optional[URIRef]:
    if iri:
        for candidate in (iri, iri.rstrip('#/')):
            if (URIRef(candidate), RDF.type, OWL.Ontology) in graph:
                return URIRef(candidate)
    declared = sorted(str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef))
    return URIRef(declared[0]) if declared else None


def _values(graph: Graph, subject: URIRef, *predicates) -> List[Any]:
    out = []
    for predicate in predicates:
        out.extend(sorted(graph.objects(subject, predicate), key=str))
    return out


def credit_from_graph(graph: Graph, iri: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Credit read from the owl:Ontology header (the one with IRI ``iri`` when
    it is declared, else the first declared). None when the header carries
    none of the fields."""
    subject = _header_subject(graph, iri)
    if subject is None:
        return None
    titles = _values(graph, subject, DCTERMS.title)
    licenses = _values(graph, subject, DCTERMS.license) or _values(graph, subject, DC.rights)
    citations = _values(graph, subject, DCTERMS.bibliographicCitation)
    versions = _values(graph, subject, OWL.versionInfo)
    see_also = [v for v in _values(graph, subject, RDFS.seeAlso) if isinstance(v, URIRef)]
    license_value = licenses[0] if licenses else None
    raw = {
        'title': str(titles[0]) if titles else None,
        'creators': [str(v) for v in _values(graph, subject, DCTERMS.creator, DC.creator)],
        'license': ({'id': str(license_value),
                     'url': str(license_value) if isinstance(license_value, URIRef) else None}
                    if license_value is not None else None),
        'citation': {'text': str(citations[0])} if citations else None,
        'version': str(versions[0]) if versions else None,
        'homepage': str(see_also[0]) if see_also else None,
    }
    if not any(raw.values()):
        return None
    return normalize_credit(raw, strict=False)


def credit_from_content(content: Optional[str], iri: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """credit_from_graph over Turtle text, or None for empty or unparsable content."""
    if not content:
        return None
    graph = Graph()
    try:
        graph.parse(data=content, format='turtle')
    except Exception as exc:  # noqa: BLE001 - a malformed version must not break the page
        logger.warning('Could not parse ontology content for its credit: %s', exc)
        return None
    return credit_from_graph(graph, iri)


_HEADER_CACHE: Dict[Tuple[int, str], Optional[Dict[str, Any]]] = {}
_HEADER_CACHE_SIZE = 256


def credit_for(ontology: Any) -> Optional[Dict[str, Any]]:
    """The credit the ontology page shows: the stored block, else the header
    fallback for a category with ``header_credit``, else None. The fallback is
    kept per process for each version, since it parses the version content."""
    md = ontology.meta_data if isinstance(getattr(ontology, 'meta_data', None), dict) else {}
    stored = md.get(CREDIT_KEY)
    if stored:
        try:
            return normalize_credit(stored, strict=False)
        except CreditError:
            return None
    category = categories.category_info(categories.resolve(ontology).category)
    if not category.header_credit:
        return None
    version = ontology.current_version
    if version is None or not version.content:
        return None
    key = (version.id, version.content_hash or '')
    if key not in _HEADER_CACHE:
        if len(_HEADER_CACHE) >= _HEADER_CACHE_SIZE:
            _HEADER_CACHE.clear()
        _HEADER_CACHE[key] = credit_from_content(version.content, ontology.base_uri)
    return _HEADER_CACHE[key]
