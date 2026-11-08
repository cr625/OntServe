"""
Import of an external ontology collection from a manifest.

A manifest (YAML) names one category and its ontologies:

    category: Robotics and Automation
    collection: robotics                  # optional, by default the collection of config/collections.yaml
                                          # whose categories list names the category
    retrieved: 2026-11-07                 # credit.retrieved of entries that give none
    ontologies:
      - name: soma                        # row name and file name
        display_name: SOMA (Socio-physical Model of Activities)
        subcategory: Activities and manipulation
        description: ...                  # optional, else the header rdfs:comment or dcterms:description
        iri: ...                          # optional, else the owl:Ontology IRI of the first file
        files:                            # path relative to the source directory
          - {path: soma/owl/SOMA.owl, url: <pinned raw URL>, format: ofn, sha256: ...}
        drop_imports: [<IRI>, ...]
        credit: {...}                     # schema of services.ontology_credit

For each entry, build_entry reads the files (the copy under the source
directory, else the pinned URL, whose bytes must match a given sha256),
converts each to an rdflib graph (utils.rdf_conversion), merges them, removes
the owl:imports listed in ``drop_imports`` and serializes canonical Turtle.
An entry whose credit says ``redistribution: reference-only`` gets a stub
instead: the owl:Ontology header with dcterms annotations from its credit
block and no axioms of the source. import_collection writes the Turtle to
``ontologies/external/<category-slug>/<name>.ttl`` when it differs from the file
there, and upsert_ontology creates or updates the row: source_system
'external', display_name, category, subcategory, collection and credit in
the metadata, and a new OntologyVersion with re-extracted entities only when
the content hash differs from the current version. An unchanged entry changes
neither the file nor the database. The import sets those fields on every run,
so an edit made on the settings page is replaced by the next run.

The startup sync reads only the top level of ontologies/, so the files under
ontologies/external/ reach the database through this import alone.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests
import yaml
from rdflib import Graph, Literal, OWL, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from services import collections as coll
from services import ontology_categories as categories
from services.ontology_credit import (
    CREDIT_KEY, NO_LICENSE, REFERENCE_ONLY, CreditError, normalize_credit, normalize_date)
from services.ontology_sync_service import OntologySyncService, ontology_iri_from_graph
from utils.rdf_conversion import (
    ConversionError, bind_prefixes, detect_format, graph_from_content, graph_to_turtle,
    normalize_format)

EXTERNAL_DIR = 'external'
CREATED_BY = 'import_external_collection'
SOURCE_SYSTEM = 'external'

_NAME = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
_MANIFEST_KEYS = {'category', 'collection', 'retrieved', 'ontologies'}
_ENTRY_KEYS = {'name', 'display_name', 'subcategory', 'description', 'iri', 'files',
               'drop_imports', 'credit'}
_FILE_KEYS = {'path', 'url', 'format', 'sha256'}


class ManifestError(ValueError):
    """A manifest, or an entry of one, that cannot be imported."""


@dataclass(frozen=True)
class SourceFile:
    path: Optional[str]
    url: Optional[str]
    format: Optional[str]
    sha256: Optional[str] = None


@dataclass
class Entry:
    name: str
    display_name: str
    subcategory: Optional[str]
    description: Optional[str]
    iri: Optional[str]
    files: List[SourceFile]
    drop_imports: List[str]
    credit: Dict[str, Any]

    @property
    def reference_only(self) -> bool:
        return self.credit.get('redistribution') == REFERENCE_ONLY


@dataclass
class Manifest:
    category: str
    collection: str                # a key of config/collections.yaml
    retrieved: Optional[str]
    entries: List[Entry]

    @property
    def folder(self) -> str:
        """The folder of the Turtle files under ontologies/external/: the slug of the category."""
        return categories.slugify(self.category)


@dataclass
class BuiltEntry:
    """The Turtle of one entry and what the row needs from it."""
    entry: Entry
    turtle: str
    iri: str
    description: Optional[str]
    triples: int
    sources: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        """SHA-256 of the UTF-8 Turtle, the value OntologySyncService.calculate_file_hash
        gives for the written file."""
        return hashlib.sha256(self.turtle.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _unknown(data: Dict, allowed: set, where: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise ManifestError(f"{where}: unknown keys {', '.join(extra)}")


def _file(raw: Any, where: str) -> SourceFile:
    if isinstance(raw, str):
        raw = {'path': raw}
    if not isinstance(raw, dict):
        raise ManifestError(f'{where}: a file is a mapping with path, url, format and sha256')
    _unknown(raw, _FILE_KEYS, where)
    spec = SourceFile(path=_clean(raw.get('path')), url=_clean(raw.get('url')),
                      format=_clean(raw.get('format')), sha256=_clean(raw.get('sha256')))
    if not (spec.path or spec.url):
        raise ManifestError(f'{where}: a file needs a path or a url')
    try:
        normalize_format(spec.format)
    except ConversionError as exc:
        raise ManifestError(f'{where}: {exc}') from exc
    return spec


def parse_manifest(data: Any) -> Manifest:
    """Check a loaded manifest and return it with every credit block normalized."""
    if not isinstance(data, dict):
        raise ManifestError('the manifest is not a mapping')
    _unknown(data, _MANIFEST_KEYS, 'manifest')
    category = _clean(data.get('category'))
    if not category:
        raise ManifestError('manifest: category is required')
    collection = _clean(data.get('collection')) or coll.collection_for_category(category)
    if not collection:
        raise ManifestError(f'manifest: no collection of config/collections.yaml lists the category '
                            f'{category}, and the manifest names none')
    if coll.get_config().get(collection) is None:
        raise ManifestError(f'manifest: {collection} is not a collection of config/collections.yaml')
    if collection in coll.proethica_scope():
        raise ManifestError(f'manifest: {collection} belongs to the ProEthica scope')
    try:
        retrieved = normalize_date(data.get('retrieved'))
    except CreditError as exc:
        raise ManifestError(f'manifest: retrieved is not a YYYY-MM-DD date: {data.get("retrieved")}') from exc
    raw_entries = data.get('ontologies') or []
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ManifestError('manifest: ontologies must be a non-empty list')

    entries, seen = [], set()
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise ManifestError(f'ontologies[{i}]: an entry is a mapping')
        name = _clean(raw.get('name'))
        where = name or f'ontologies[{i}]'
        _unknown(raw, _ENTRY_KEYS, where)
        if not name or not _NAME.match(name):
            raise ManifestError(f'{where}: name must be lower case letters, digits, ".", "_" or "-"')
        if name.startswith('proethica-'):
            raise ManifestError(f'{where}: names starting with proethica- belong to the ProEthica ontologies')
        if name in seen:
            raise ManifestError(f'{where}: the name occurs twice')
        seen.add(name)
        try:
            credit = normalize_credit(raw.get('credit') or {}, retrieved=retrieved, strict=True)
        except CreditError as exc:
            raise ManifestError(f'{where}: {exc}') from exc
        files = [_file(f, f'{where}.files[{j}]') for j, f in enumerate(raw.get('files') or [])]
        if not files and credit['redistribution'] != REFERENCE_ONLY:
            raise ManifestError(f'{where}: a hosted entry needs at least one file')
        drop_imports = raw.get('drop_imports') or []
        if not isinstance(drop_imports, list):
            raise ManifestError(f'{where}: drop_imports must be a list of IRIs')
        entries.append(Entry(
            name=name,
            display_name=_clean(raw.get('display_name')) or credit['title'] or name,
            subcategory=_clean(raw.get('subcategory')),
            description=_clean(raw.get('description')),
            iri=_clean(raw.get('iri')),
            files=files,
            drop_imports=[str(i).strip() for i in drop_imports if _clean(i)],
            credit=credit,
        ))
    return Manifest(category=category, collection=collection, retrieved=retrieved, entries=entries)


def load_manifest(path: Path) -> Manifest:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(f'{path}: {exc}') from exc
    return parse_manifest(data)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

def http_get(url: str) -> bytes:
    response = requests.get(url, timeout=120,
                            headers={'User-Agent': 'OntServe/1.0 (external collection import)'})
    response.raise_for_status()
    return response.content


def read_file(spec: SourceFile, source_dir: Path,
              fetch: Callable[[str], bytes] = http_get) -> Tuple[bytes, str]:
    """(bytes, origin) of a source file: the copy under ``source_dir`` when it
    exists, else the content at the pinned URL. A given sha256 must match."""
    data, origin = None, None
    if spec.path:
        root = Path(source_dir).resolve()
        local = (root / spec.path).resolve()
        if root not in local.parents:
            raise ManifestError(f'{spec.path}: the path leaves the source directory')
        if local.is_file():
            data, origin = local.read_bytes(), str(local)
    if data is None:
        if not spec.url:
            raise ManifestError(f'{spec.path}: not under {source_dir} and the entry gives no url')
        try:
            data, origin = fetch(spec.url), spec.url
        except requests.RequestException as exc:
            raise ManifestError(f'{spec.url}: {exc}') from exc
    if spec.sha256 and hashlib.sha256(data).hexdigest() != spec.sha256.lower():
        raise ManifestError(f'{origin}: the SHA-256 differs from the manifest')
    return data, origin


def file_graph(spec: SourceFile, data: bytes) -> Graph:
    fmt = detect_format(filename=spec.path or spec.url, content=data, hint=spec.format)
    try:
        return graph_from_content(data, fmt, public_id=spec.url)
    except ConversionError as exc:
        raise ManifestError(f'{spec.path or spec.url}: {exc}') from exc


def _header_text(graph: Graph, iri: Optional[str]) -> Optional[str]:
    if not iri:
        return None
    for predicate in (DCTERMS.description, RDFS.comment):
        value = graph.value(URIRef(iri), predicate)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _iri_or_literal(value: str):
    return URIRef(value) if re.match(r'^https?://\S+$', value) else Literal(value)


def stub_graph(iri: str, entry: Entry) -> Graph:
    """The owl:Ontology header of a reference-only entry, written from its credit block."""
    credit = entry.credit
    graph = Graph()
    for prefix, namespace in (('owl', OWL), ('rdfs', RDFS), ('dcterms', DCTERMS)):
        graph.bind(prefix, namespace)
    subject = URIRef(iri)
    graph.add((subject, RDF.type, OWL.Ontology))
    if credit['title']:
        graph.add((subject, DCTERMS.title, Literal(credit['title'])))
    for creator in credit['creators']:
        graph.add((subject, DCTERMS.creator, Literal(creator)))
    if credit['publisher']:
        graph.add((subject, DCTERMS.publisher, Literal(credit['publisher'])))
    license_ = credit['license'] or {}
    if license_.get('url'):
        graph.add((subject, DCTERMS.license, _iri_or_literal(license_['url'])))
    elif license_.get('id') and license_['id'] != NO_LICENSE:
        graph.add((subject, DCTERMS.license, Literal(license_['id'])))
    source = credit['source'] or {}
    for value in (source.get('repository'), source.get('url')):
        if value:
            graph.add((subject, DCTERMS.source, _iri_or_literal(value)))
    if credit['homepage']:
        graph.add((subject, RDFS.seeAlso, _iri_or_literal(credit['homepage'])))
    citation = credit['citation'] or {}
    if citation.get('text'):
        graph.add((subject, DCTERMS.bibliographicCitation, Literal(citation['text'])))
    if credit['version']:
        graph.add((subject, OWL.versionInfo, Literal(credit['version'])))
    if entry.description:
        graph.add((subject, DCTERMS.description, Literal(entry.description)))
    return graph


def build_entry(entry: Entry, source_dir: Path, default_namespace: str,
                fetch: Callable[[str], bytes] = http_get) -> BuiltEntry:
    """Read, convert and merge the files of an entry, or build its stub."""
    warnings: List[str] = []
    sources: List[str] = []
    iri = entry.iri

    if entry.reference_only:
        if not iri and entry.files:
            # The source names the ontology. Only its IRI is read, no axiom is kept.
            try:
                data, origin = read_file(entry.files[0], source_dir, fetch)
                iri = ontology_iri_from_graph(file_graph(entry.files[0], data), preferred_name=entry.name)
                sources.append(origin)
            except ManifestError as exc:
                warnings.append(f'IRI not read from the source: {exc}')
        iri = iri or default_namespace + entry.name
        graph = stub_graph(iri, entry)
        description = entry.description
    else:
        graph = Graph()
        for i, spec in enumerate(entry.files):
            data, origin = read_file(spec, source_dir, fetch)
            sources.append(origin)
            part = file_graph(spec, data)
            if i == 0 and not iri:
                iri = ontology_iri_from_graph(part, preferred_name=entry.name)
            for triple in part:
                graph.add(triple)
            bind_prefixes(graph, part.namespaces())
        for target in entry.drop_imports:
            imports = list(graph.triples((None, OWL.imports, URIRef(target))))
            if not imports:
                warnings.append(f'drop_imports: no merged file imports {target}')
            for triple in imports:
                graph.remove(triple)
        iri = iri or default_namespace + entry.name
        description = entry.description or _header_text(graph, iri)

    return BuiltEntry(entry=entry, turtle=graph_to_turtle(graph, canonical=True), iri=iri,
                      description=description or entry.credit['title'], triples=len(graph),
                      sources=sources, warnings=warnings)


def target_path(ontologies_dir: Path, manifest: Manifest, entry: Entry) -> Path:
    return Path(ontologies_dir) / EXTERNAL_DIR / manifest.folder / f'{entry.name}.ttl'


def write_if_changed(path: Path, text: str) -> bool:
    """Write ``text`` as UTF-8 unless the file already holds exactly those bytes."""
    data = text.encode('utf-8')
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def row_metadata(manifest: Manifest, entry: Entry, current: Optional[Dict] = None) -> Dict[str, Any]:
    """The row metadata after the import: the current keys, with the keys the
    manifest owns set from it (a missing subcategory clears the key)."""
    md = dict(current or {})
    md[categories.DISPLAY_NAME_KEY] = entry.display_name
    md[categories.CATEGORY_KEY] = manifest.category
    categories.set_explicit(md, categories.SUBCATEGORY_KEY, entry.subcategory)
    md[categories.COLLECTION_KEY] = manifest.collection
    md[CREDIT_KEY] = entry.credit
    return md


def upsert_ontology(session, manifest: Manifest, built: BuiltEntry, dry_run: bool = False,
                    ontologies_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Create or update the row of one entry and return the changes made.

    A row of the same name outside this collection is refused, so an entry
    cannot overwrite a ProEthica ontology or a row of another collection."""
    from web.models import Ontology, OntologyVersion

    entry = built.entry
    changes: List[str] = []
    ontology = session.execute(select(Ontology).where(Ontology.name == entry.name)).scalar_one_or_none()
    if ontology is not None and coll.resolve(ontology) != manifest.collection:
        raise ManifestError(f'{entry.name}: an ontology of that name exists outside the '
                            f'collection {manifest.collection}')

    if ontology is None:
        ontology = Ontology(name=entry.name, base_uri=built.iri, description=built.description,
                            ontology_type='base', source_system=SOURCE_SYSTEM, is_editable=False,
                            meta_data=row_metadata(manifest, entry))
        session.add(ontology)
        session.flush()
        changes.append('created')
    else:
        md = row_metadata(manifest, entry, ontology.meta_data)
        if md != (ontology.meta_data or {}):
            ontology.meta_data = md   # reassign: db.JSON is not mutation-tracked
            changes.append('metadata')
        for attr, value in (('base_uri', built.iri), ('description', built.description),
                            ('source_system', SOURCE_SYSTEM)):
            if getattr(ontology, attr) != value:
                setattr(ontology, attr, value)
                changes.append(attr)

    versions = session.execute(
        select(OntologyVersion).where(OntologyVersion.ontology_id == ontology.id)
        .order_by(OntologyVersion.version_number.desc())).scalars().all()
    current = next((v for v in versions if v.is_current), versions[0] if versions else None)
    entities = None
    if current is None or current.content_hash != built.content_hash:
        number = versions[0].version_number + 1 if versions else 1
        session.execute(update(OntologyVersion)
                        .where(OntologyVersion.ontology_id == ontology.id, OntologyVersion.is_current.is_(True))
                        .values(is_current=False))
        session.add(OntologyVersion(
            ontology_id=ontology.id,
            version_number=number,
            content=built.turtle,
            content_hash=built.content_hash,
            change_summary=f'Imported from the {manifest.collection} collection manifest',
            created_by=CREATED_BY,
            is_current=True,
            is_draft=False,
            workflow_status='published',
            meta_data={'sources': [f.path or f.url for f in entry.files],
                       'redistribution': entry.credit['redistribution']},
        ))
        session.flush()
        if not dry_run:
            sync = OntologySyncService(session, Path(ontologies_dir or '.'))
            entities = sync._extract_and_store_entities(ontology, built.turtle)
        changes.append(f'version {number}')

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return {'name': entry.name, 'changes': changes, 'entities': entities}


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def import_collection(session, manifest: Manifest, source_dir: Path, ontologies_dir: Path,
                      default_namespace: str, only: Optional[Iterable[str]] = None,
                      dry_run: bool = False, fetch: Callable[[str], bytes] = http_get,
                      report: Callable[[str], None] = print) -> List[Dict[str, Any]]:
    """Import the entries of a manifest (those named in ``only``, when given).
    An entry that fails is reported and rolled back, the others go on."""
    names = set(only or [])
    unknown = names - {e.name for e in manifest.entries}
    if unknown:
        raise ManifestError(f"not in the manifest: {', '.join(sorted(unknown))}")
    results = []
    for entry in manifest.entries:
        if names and entry.name not in names:
            continue
        result: Dict[str, Any] = {'name': entry.name, 'ok': False}
        try:
            built = build_entry(entry, source_dir, default_namespace, fetch)
            path = target_path(ontologies_dir, manifest, entry)
            if dry_run:
                written = not (path.is_file() and path.read_bytes() == built.turtle.encode('utf-8'))
            else:
                written = write_if_changed(path, built.turtle)
            db_result = upsert_ontology(session, manifest, built, dry_run=dry_run,
                                        ontologies_dir=ontologies_dir)
            result.update(db_result, ok=True, file=str(path), file_changed=written,
                          triples=built.triples, iri=built.iri, warnings=built.warnings)
        except (ManifestError, ConversionError, SQLAlchemyError) as exc:
            session.rollback()
            result['error'] = str(exc).splitlines()[0]
        results.append(result)
        report(format_result(result, dry_run))
    return results


def format_result(result: Dict[str, Any], dry_run: bool = False) -> str:
    if not result.get('ok'):
        return f"{result['name']}: ERROR {result.get('error')}"
    parts = list(result.get('changes') or [])
    if result.get('file_changed'):
        parts.append(f"{'would write' if dry_run else 'wrote'} {result['file']}")
    if result.get('entities') is not None:
        parts.append(f"{result['entities']} entities")
    summary = ', '.join(parts) if parts else 'unchanged'
    if dry_run and parts:
        summary = 'would change: ' + summary
    line = f"{result['name']}: {summary} ({result['triples']} triples, {result['iri']})"
    for warning in result.get('warnings') or []:
        line += f"\n  warning: {warning}"
    return line
