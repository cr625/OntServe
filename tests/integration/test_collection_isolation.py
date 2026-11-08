"""Isolation of the ProEthica scope (services.collections, web.collection_scope).

A fixture ontology of the robotics collection (tests/fixtures/external/
aaa-robot-case-study.ttl) shares fragments, labels and one IRI with
proethica-core, links a class and a property into the core hierarchy, carries
individuals typed Argument and DecisionPoint and has "-case-" in its name.
With it loaded, the entity pages of core, the fragment fallback, the case
page, /resolve, the hash check and the MCP lookups answer exactly as without
it, and its own page is the generic page without the case view or the
ProEthica reasoning panel.
"""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from services import external_collection as ec

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'external'
CASE = ROOT / 'tests' / 'fixtures' / 'level_pages' / 'proethica-case-9901.ttl'
HTML = {'Accept': 'text/html', 'User-Agent': 'Mozilla/5.0'}
NAME = 'aaa-robot-case-study'
CORE = 'http://proethica.org/ontology/core#'
URIS = [CORE + f for f in ('Action', 'Agent', 'Role', 'State')]
PAGES = [
    '/entity/proethica-core/Action', '/entity/proethica-core/Agent', '/entity/proethica-core/Role',
    '/entity/proethica-core/State', '/entity/no-such-ontology/Action', '/entity/no-such-ontology/Agent',
    '/ontology/proethica-core', '/ontology/proethica-case-9901', '/ontology/proethica-case-9901?view=standard',
]
MANIFEST = {
    'category': 'Robotics and Automation',
    'retrieved': '2026-11-07',
    'ontologies': [{
        'name': NAME, 'display_name': 'Robot case study (fixture)',
        'files': [{'path': f'{NAME}.ttl'}],
        'credit': {'title': 'Robot case study', 'license': 'MIT',
                   'source': {'repository': 'https://example.org/robot-case-study'}},
    }],
}


def _remove(name):
    from web.models import db, Ontology
    for o in db.session.execute(select(Ontology).where(Ontology.name == name)).scalars().all():
        db.session.delete(o)
    db.session.commit()


@pytest.fixture(scope='module')
def seeded(app):
    from services.ontology_sync_service import OntologySyncService
    from web.models import db
    with app.app_context():
        _remove(NAME)
        service = OntologySyncService(db.session, ROOT / 'ontologies')
        for name in ('proethica-core', 'proethica-cases'):
            service._sync_single_ontology(ROOT / 'ontologies' / f'{name}.ttl', force=True)
        OntologySyncService(db.session, CASE.parent)._sync_single_ontology(CASE, force=True)
    return True


def _snapshot(client):
    pages = {p: client.get(p, headers=HTML) for p in PAGES}
    for path, r in pages.items():
        assert r.status_code == 200, path
    resolved = {u: client.get('/resolve', query_string={'uri': u}, headers={'Accept': 'application/json'}).get_json()
                for u in URIS}
    hashes = client.post('/api/entity-hash-check', json={'entity_uris': URIS}).get_json()
    return {p: r.get_data(as_text=True) for p, r in pages.items()}, resolved, hashes


@pytest.mark.integration
def test_web_paths_answer_as_without_the_fixture(app, client, seeded, tmp_path):
    from web.models import db, OntologyEntity
    pages, resolved, hashes = _snapshot(client)
    with app.app_context():
        [result] = ec.import_collection(db.session, ec.parse_manifest(MANIFEST), FIXTURES, tmp_path,
                                        'https://ontserve.example/ontology/', report=lambda line: None)
        assert result['ok'], result
    try:
        with app.app_context():
            # Without the scope the fixture would answer: a second row with the IRI of core:Action
            assert len(db.session.execute(select(OntologyEntity).where(
                OntologyEntity.uri == CORE + 'Action')).scalars().all()) == 2
        after_pages, after_resolved, after_hashes = _snapshot(client)
        for path in PAGES:
            assert after_pages[path] == pages[path], path
        assert after_resolved == resolved
        assert after_hashes == hashes and after_hashes['checked_count'] == 4

        # The fixture's own page: the generic page, no case view, no ProEthica reasoning panel
        html = client.get(f'/ontology/{NAME}', headers=HTML).get_data(as_text=True)
        assert 'id="ontologyTabs"' in html and 'id="reasoning-panel"' not in html
        assert client.get(f'/ontology/{NAME}/case-section/roles', headers=HTML).status_code == 404
        r = client.post(f'/editor/api/simple/reasoning/{NAME}', json={})
        assert r.status_code == 400 and not r.get_json()['success']
        # Its own entity page sees its collection: the fallback finds its Agent
        page = client.get(f'/entity/{NAME}/GraspAction', headers=HTML).get_data(as_text=True)
        assert 'http://example.org/robot-case-study#GraspAction' in page
    finally:
        with app.app_context():
            _remove(NAME)


# ---------------------------------------------------------------------------
# MCP lookups (the database of ONTSERVE_DB_URL, populated by the MCP lifespan)
# ---------------------------------------------------------------------------

MCP_CALLS = [
    ('get_entity_by_uri', {'uri': CORE + 'Action'}),
    ('get_entity_by_uri', {'uri': CORE + 'Action', 'include_properties': True}),
    ('get_entity_by_uri', {'uri': 'http://example.org/elsewhere#Agent'}),
    ('get_entity_by_uri', {'uri': 'http://example.org/elsewhere#State'}),
    ('get_entity_by_uri', {'uri': 'http://example.org/robot-case-study#GraspAction'}),
    ('get_entity_by_label', {'label': 'Agent'}),
    ('get_entity_by_label', {'label': 'Action'}),
    ('get_entity_by_label', {'label': 'Role'}),
    ('get_entity_by_label', {'label': 'State'}),
    ('get_entity_by_label', {'label': 'Grasp action'}),
    ('get_entities_by_uris', {'uris': [CORE + 'Action', CORE + 'Role', 'http://example.org/elsewhere#Agent',
                                      'http://example.org/robot-case-study#Argument']}),
]

FIXTURE_ROWS = [
    ('class', 'http://example.org/robot-case-study#Agent', 'Agent', None),
    ('class', 'http://example.org/robot-case-study#Action', 'Action', None),
    ('class', 'http://example.org/robot-case-study#Role', 'Role', None),
    ('class', 'http://example.org/robot-case-study#State', 'State', None),
    ('class', 'http://example.org/robot-case-study#Argument', 'Argument', None),
    ('class', CORE + 'Action', 'Redeclared action', None),
    ('class', 'http://example.org/robot-case-study#GraspAction', 'Grasp action', CORE + 'Action'),
]


async def _answers(mcp_client):
    out = []
    for tool, args in MCP_CALLS:
        result = await mcp_client.call_tool(tool, args)
        out.append(json.loads(result.content[0].text))
    return out


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.asyncio
async def test_mcp_lookups_answer_as_without_the_fixture(mcp_client, pg_storage):
    from psycopg2.extras import Json
    before = await _answers(mcp_client)
    assert before[0].get('found') is True, 'proethica-core is not in the MCP database'
    row = pg_storage._execute_query(
        "INSERT INTO ontologies (uuid, name, base_uri, description, ontology_type, source_system, "
        "is_editable, metadata, created_at) VALUES (%s, %s, %s, %s, 'base', 'external', false, %s, now()) "
        "RETURNING id",
        (str(uuid.uuid4()), NAME, 'http://example.org/robot-case-study', 'Robot case study fixture.',
         Json({'collection': 'robotics', 'category': 'Robotics and Automation'})), fetch_one=True)
    oid = row['id']
    try:
        for etype, uri, label, parent in FIXTURE_ROWS:
            pg_storage._execute_query(
                "INSERT INTO ontology_entities (ontology_id, entity_type, uri, label, parent_uri, created_at) "
                "VALUES (%s, %s, %s, %s, %s, now())", (oid, etype, uri, label, parent))
        # Without the scope the fixture would answer the fragment and label lookups
        raw = pg_storage._execute_query(
            "SELECT o.name FROM ontology_entities e JOIN ontologies o ON e.ontology_id = o.id "
            "WHERE e.uri LIKE %s ORDER BY o.name LIMIT 1", ('%#Agent',), fetch_one=True)
        assert raw['name'] == NAME
        after = await _answers(mcp_client)
        for (tool, args), b, a in zip(MCP_CALLS, before, after):
            assert a == b, (tool, args)
    finally:
        pg_storage._execute_query("DELETE FROM ontology_entities WHERE ontology_id = %s", (oid,))
        pg_storage._execute_query("DELETE FROM ontologies WHERE id = %s", (oid,))
