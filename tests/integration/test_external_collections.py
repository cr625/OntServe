"""External collections end to end on the test app: the import of a small
manifest (services.external_collection), the Source and credit panel of the
generic ontology page, the two categories on the home page and in the flat
list, and the ProEthica pages, which render without the panel."""

import shutil
from pathlib import Path
from urllib.parse import quote

import pytest
from rdflib import Graph
from sqlalchemy import select

from services import external_collection as ec

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'external'
HTML = {'Accept': 'text/html', 'User-Agent': 'Mozilla/5.0'}
NS = 'https://ontserve.example/ontology/'
NAMES = ('ext-gripper', 'ext-sensor', 'ext-arm-ref')

CREDIT = {
    'title': 'Gripper Ontology',
    'creators': ['Ada Lovelace', 'Charles Babbage'],
    'publisher': 'Example Robotics Lab',
    'license': {'id': 'CC-BY-4.0', 'url': 'https://creativecommons.org/licenses/by/4.0/'},
    'source': {'repository': 'https://github.com/example/gripper', 'commit': '0123456789abcdef0123',
               'paths': ['gripper.ofn', 'device.ttl'], 'url': None},
    'homepage': 'https://example.org/gripper',
    'citation': {'text': 'Lovelace, A. (2026). A gripper ontology.', 'doi': '10.1234/gripper', 'url': None},
    'modifications': 'Converted from OWL functional syntax to Turtle and merged with the device module.',
    'used_in': [{'text': 'Grasp planning with ontologies (2026)', 'reasoner': 'HermiT'}],
    'redistribution': 'hosted',
}


def manifest_data(gripper_files=None):
    return {
        'category': 'Robotics and Automation',
        'retrieved': '2026-11-07',
        'ontologies': [
            {'name': 'ext-gripper', 'display_name': 'Gripper (test)', 'subcategory': 'Grasping',
             'files': gripper_files or [{'path': 'gripper.ofn', 'format': 'ofn'}, {'path': 'device.ttl'}],
             'drop_imports': ['http://example.org/device'], 'credit': CREDIT},
            {'name': 'ext-sensor', 'display_name': 'Sensor (test)', 'subcategory': 'Perception',
             'files': [{'path': 'sensor.rdf'}],
             'credit': {'title': 'Sensor Ontology', 'license': 'MIT',
                        'source': {'repository': 'https://github.com/example/sensor'}}},
            {'name': 'ext-arm-ref', 'display_name': 'Arm (test, by reference)', 'subcategory': 'Grasping',
             'files': [{'path': 'arm.owx'}],
             'credit': {'title': 'Arm Ontology', 'creators': ['Grace Hopper'], 'license': 'none stated',
                        'source': {'repository': 'https://github.com/example/arm',
                                   'url': 'https://raw.example.org/arm.owx'},
                        'redistribution': 'reference-only'}},
        ],
    }


def _remove_rows(names):
    from web.models import db, Ontology
    for o in db.session.execute(select(Ontology).where(Ontology.name.in_(names))).scalars().all():
        db.session.delete(o)
    db.session.commit()


@pytest.fixture(scope='module')
def workspace(tmp_path_factory):
    src = tmp_path_factory.mktemp('sources')
    for name in ('gripper.ofn', 'device.ttl', 'sensor.rdf', 'arm.owx'):
        shutil.copy(FIXTURES / name, src / name)
    return src, tmp_path_factory.mktemp('ontologies')


@pytest.fixture(scope='module')
def imported(app, workspace):
    """The manifest imported once per module (other modules wipe the tables)."""
    from web.models import db
    src, onts = workspace
    manifest = ec.parse_manifest(manifest_data())
    with app.app_context():
        _remove_rows(NAMES)
        results = ec.import_collection(db.session, manifest, src, onts, NS, report=lambda line: None)
    yield {r['name']: r for r in results}
    with app.app_context():
        _remove_rows(NAMES)


def _row(name):
    from web.models import db, Ontology
    return db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()


def _page(client, path):
    r = client.get(path, headers=HTML)
    assert r.status_code == 200, path
    html = r.get_data(as_text=True)
    return html[html.index('<main'):html.index('</main>')]


@pytest.mark.integration
class TestImport:

    def test_rows(self, app, imported):
        assert all(r['ok'] for r in imported.values()), imported
        with app.app_context():
            row = _row('ext-gripper')
            assert row.source_system == 'external' and row.base_uri == 'http://example.org/gripper'
            md = row.meta_data
            assert (md['category'], md['subcategory'], md['collection'], md['display_name']) == (
                'Robotics and Automation', 'Grasping', 'robotics', 'Gripper (test)')
            assert md['credit']['retrieved'] == '2026-11-07' and md['credit']['creators'][0] == 'Ada Lovelace'
            assert row.category == 'Robotics and Automation'

    def test_versions_hold_turtle_and_entities(self, app, imported):
        with app.app_context():
            row = _row('ext-gripper')
            version = row.current_version
            assert version.version_number == 1 and version.created_by == ec.CREATED_BY
            g = Graph()
            g.parse(data=version.content, format='turtle')
            assert len(g) == imported['ext-gripper']['triples']
            uris = {e.uri for e in row.entities}
            assert {'http://example.org/gripper#Gripper', 'http://example.org/device#Device'} <= uris
            assert imported['ext-gripper']['entities'] == len(row.entities)

    def test_files_written(self, workspace, imported):
        _, onts = workspace
        path = onts / 'external' / 'robotics-and-automation' / 'ext-gripper.ttl'
        assert Path(imported['ext-gripper']['file']) == path and path.is_file()
        stub = (onts / 'external' / 'robotics-and-automation' / 'ext-arm-ref.ttl').read_text()
        assert 'Joint' not in stub and 'Arm Ontology' in stub

    def test_rerun_changes_nothing(self, app, workspace, imported):
        from web.models import db, OntologyVersion
        src, onts = workspace
        path = onts / 'external' / 'robotics-and-automation' / 'ext-gripper.ttl'
        mtime = path.stat().st_mtime_ns
        with app.app_context():
            again = ec.import_collection(db.session, ec.parse_manifest(manifest_data()), src, onts, NS,
                                         report=lambda line: None)
            assert [r['changes'] for r in again] == [[], [], []]
            assert not any(r['file_changed'] for r in again)
            ids = [_row(n).id for n in NAMES]
            count = db.session.execute(select(OntologyVersion).where(
                OntologyVersion.ontology_id.in_(ids))).scalars().all()
            assert len(count) == 3
        assert path.stat().st_mtime_ns == mtime

    def test_changed_source_adds_a_version(self, app, workspace, imported):
        from web.models import db
        src, onts = workspace
        manifest = ec.parse_manifest(manifest_data(gripper_files=[{'path': 'gripper.ofn', 'format': 'ofn'}]))
        with app.app_context():
            [result] = ec.import_collection(db.session, manifest, src, onts, NS, only=['ext-gripper'],
                                            report=lambda line: None)
            assert result['changes'] == ['version 2']
            row = _row('ext-gripper')
            assert row.current_version.version_number == 2
            assert 'http://example.org/device#Device' not in {e.uri for e in row.entities}
            # back to the module state
            ec.import_collection(db.session, ec.parse_manifest(manifest_data()), src, onts, NS,
                                 only=['ext-gripper'], report=lambda line: None)

    def test_dry_run_writes_nothing(self, app, workspace, imported):
        from web.models import db, Ontology
        src, onts = workspace
        data = manifest_data()
        data['ontologies'][1]['name'] = 'ext-dry'
        with app.app_context():
            [result] = ec.import_collection(db.session, ec.parse_manifest(data), src, onts, NS,
                                            only=['ext-dry'], dry_run=True, report=lambda line: None)
            assert result['ok'] and 'created' in result['changes'] and result['file_changed']
            assert db.session.execute(select(Ontology).where(Ontology.name == 'ext-dry')).scalar_one_or_none() is None
        assert not (onts / 'external' / 'robotics-and-automation' / 'ext-dry.ttl').exists()

    def test_name_outside_the_collection_is_refused(self, app, workspace, imported):
        from web.models import db, Ontology
        src, onts = workspace
        data = manifest_data()
        data['ontologies'][1]['name'] = 'ext-taken'
        with app.app_context():
            db.session.add(Ontology(name='ext-taken', base_uri='http://example.org/taken#',
                                    source_system='proethica', meta_data={}))
            db.session.commit()
            try:
                [result] = ec.import_collection(db.session, ec.parse_manifest(data), src, onts, NS,
                                                only=['ext-taken'], report=lambda line: None)
                assert not result['ok'] and 'outside the collection' in result['error']
                assert _row('ext-taken').source_system == 'proethica'
            finally:
                _remove_rows(['ext-taken'])


@pytest.mark.integration
class TestCreditPanel:

    def test_hosted_panel(self, client, imported):
        main = _page(client, '/ontology/ext-gripper')
        panel = main[main.index('id="credit"'):]
        panel = panel[:panel.index('</section>')]
        assert 'Source and credit' in panel
        assert 'Ada Lovelace, Charles Babbage' in panel and 'Example Robotics Lab' in panel
        assert '<a href="https://creativecommons.org/licenses/by/4.0/">CC-BY-4.0</a>' in panel
        assert 'href="https://github.com/example/gripper"' in panel and '<code>0123456789ab</code>' in panel
        assert '<code>gripper.ofn</code>, <code>device.ttl</code>' in panel
        assert 'href="https://doi.org/10.1234/gripper"' in panel
        assert 'Grasp planning with ontologies (2026) (reasoner HermiT)' in panel
        assert 'Changes in OntServe' in panel and '2026-11-07' in panel
        assert 'does not host' not in panel
        assert 'Gripper (test)' in main[main.index('<h1'):main.index('</h1>')]

    def test_reference_only_panel(self, client, imported):
        main = _page(client, '/ontology/ext-arm-ref')
        assert ('OntServe does not host the content of this ontology, which is available at '
                '<a href="https://raw.example.org/arm.owx">https://raw.example.org/arm.owx</a>.') in main
        assert 'No license stated in the source' in main

    def test_schema_view_keeps_the_panel(self, client, imported):
        assert 'id="credit"' in _page(client, '/ontology/ext-sensor?view=standard')

    def test_turtle_served(self, client, imported):
        r = client.get('/ontology/ext-sensor', headers={'Accept': 'text/turtle'})
        assert r.status_code == 200 and r.mimetype == 'text/turtle'
        Graph().parse(data=r.get_data(as_text=True), format='turtle')


@pytest.fixture(scope='module')
def proethica_rows(app):
    """Two ProEthica rows: proethica-cases (its header carries dc:creator and
    owl:versionInfo) and the bfo fixture of the level pages."""
    from services.ontology_sync_service import OntologySyncService
    from web.models import db
    with app.app_context():
        service = OntologySyncService(db.session, ROOT / 'ontologies')
        service._sync_single_ontology(ROOT / 'ontologies' / 'proethica-cases.ttl', force=True)
        service._sync_single_ontology(ROOT / 'tests' / 'fixtures' / 'level_pages' / 'bfo.ttl', force=True)
    return True


@pytest.mark.integration
class TestProEthicaPages:

    @pytest.mark.parametrize('path', ['/ontology/proethica-cases', '/ontology/proethica-cases?view=standard',
                                      '/ontology/bfo'])
    def test_no_panel(self, client, proethica_rows, imported, path):
        main = _page(client, path)
        assert 'id="credit"' not in main and 'Source and credit' not in main

    def test_entity_fallback_stays_out_of_collections(self, app, client, imported):
        """A link to an entity missing from the named ontology resolves among the
        rows outside external collections only."""
        from web.models import db, Ontology, OntologyEntity
        with app.app_context():
            hosted = _row('ext-gripper')
            db.session.add(OntologyEntity(ontology_id=hosted.id, entity_type='class',
                                          uri='http://example.org/gripper#Widget', label='Hosted widget'))
            home = Ontology(name='ext-test-home', base_uri='http://proethica.org/ontology/home#',
                            source_system='proethica', meta_data={})
            db.session.add(home)
            db.session.flush()
            db.session.add(OntologyEntity(ontology_id=home.id, entity_type='class',
                                          uri='http://proethica.org/ontology/home#Widget', label='Home widget'))
            db.session.commit()
        try:
            html = client.get('/entity/proethica-intermediate/Widget', headers=HTML).get_data(as_text=True)
            assert 'Home widget' in html and 'Hosted widget' not in html
            html = client.get('/entity/ext-sensor/Widget', headers=HTML).get_data(as_text=True)
            assert 'Hosted widget' in html or 'Home widget' in html
        finally:
            with app.app_context():
                _remove_rows(['ext-test-home'])
                db.session.execute(OntologyEntity.__table__.delete().where(
                    OntologyEntity.uri == 'http://example.org/gripper#Widget'))
                db.session.commit()


@pytest.mark.integration
class TestComponentBadge:
    """The D-tuple component badge of the entity page belongs to the nine
    ProEthica classes, not to a hosted class of the same name."""

    @pytest.fixture()
    def roles(self, app, imported):
        from web.models import db, Ontology, OntologyEntity
        with app.app_context():
            hosted = _row('ext-gripper')
            db.session.add(OntologyEntity(ontology_id=hosted.id, entity_type='class',
                                          uri='http://example.org/gripper#Role', label='Role'))
            core = Ontology(name='ext-test-core', base_uri='http://proethica.org/ontology/core#',
                            source_system='proethica', meta_data={})
            db.session.add(core)
            db.session.flush()
            db.session.add(OntologyEntity(ontology_id=core.id, entity_type='class',
                                          uri='http://proethica.org/ontology/core#Role', label='Role'))
            db.session.commit()
        yield
        with app.app_context():
            _remove_rows(['ext-test-core'])
            db.session.execute(OntologyEntity.__table__.delete().where(
                OntologyEntity.uri == 'http://example.org/gripper#Role'))
            db.session.commit()

    def test_badge_on_the_proethica_class_only(self, client, roles):
        proethica = client.get('/entity/ext-test-core/Role', headers=HTML).get_data(as_text=True)
        hosted = client.get('/entity/ext-gripper/Role', headers=HTML).get_data(as_text=True)
        assert 'D-tuple component' in proethica
        assert 'http://example.org/gripper#Role' in hosted and 'D-tuple component' not in hosted


@pytest.mark.integration
class TestCategoryListings:

    def test_flat_list(self, client, imported):
        main = _page(client, '/?category=' + quote('Robotics and Automation'))
        for name in NAMES:
            assert f'href="/ontology/{name}"' in main
        assert 'Grasping' in main and 'Perception' in main

    def test_subcategory_filter(self, client, imported):
        main = _page(client, '/?category=' + quote('Robotics and Automation') + '&subcategory=Perception')
        assert 'href="/ontology/ext-sensor"' in main and 'href="/ontology/ext-gripper"' not in main

    def test_stack_page_and_landing(self, client, imported):
        # The landing page of the collection lists the rows, the ProEthica stack page does not
        assert 'href="/ontology/ext-gripper"' not in _page(client, '/collections/proethica')
        landing = _page(client, '/collections/robotics')
        for name in NAMES:
            assert f'href="/ontology/{name}"' in landing
