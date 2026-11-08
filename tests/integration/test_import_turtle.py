"""The web import stores Turtle whatever the format of the source
(web/services/ontology_import.py over utils.rdf_conversion)."""

import io
from pathlib import Path

import pytest
from rdflib import Graph, OWL, RDF, URIRef
from sqlalchemy import select

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'external'


def _upload(client, filename, name, fmt=''):
    data = {'source_type': 'upload', 'name': name, 'description': 'Upload test', 'format': fmt,
            'ontology_file': (io.BytesIO((FIXTURES / filename).read_bytes()), filename)}
    return client.post('/import', data=data, content_type='multipart/form-data')


def _stored(app, name):
    from web.models import db, Ontology
    with app.app_context():
        row = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one()
        version = row.current_version
        return version.content, dict(version.meta_data or {}), {e.uri for e in row.entities}, dict(row.meta_data)


def _remove(app, name):
    from web.models import db, Ontology
    with app.app_context():
        row = db.session.execute(select(Ontology).where(Ontology.name == name)).scalar_one_or_none()
        if row is not None:
            db.session.delete(row)
            db.session.commit()


@pytest.mark.integration
@pytest.mark.parametrize('filename, name, source_format, uri', [
    ('gripper.ofn', 'upload-gripper-ofn', 'ofn', 'http://example.org/gripper#Gripper'),
    ('arm.owx', 'upload-arm-owx', 'owx', 'http://example.org/arm#Arm'),
    ('sensor.rdf', 'upload-sensor-rdf', 'xml', 'http://example.org/sensor#Sensor'),
])
def test_upload_is_stored_as_turtle(app, logged_in_client, filename, name, source_format, uri):
    _remove(app, name)
    try:
        r = _upload(logged_in_client, filename, name)
        assert r.status_code == 302 and r.headers['Location'].endswith(f'/ontology/{name}')
        content, version_md, uris, row_md = _stored(app, name)
        g = Graph()
        g.parse(data=content, format='turtle')
        assert (URIRef(uri), RDF.type, OWL.Class) in g
        assert uri in uris
        assert (version_md['format'], version_md['source_format']) == ('turtle', source_format)
        assert row_md['source'] == f'uploaded://{filename}' and 'source_file' not in row_md
    finally:
        _remove(app, name)


@pytest.mark.integration
def test_owl_file_in_functional_syntax(app, logged_in_client, tmp_path):
    """A .owl upload holding functional syntax (as SOMA writes it) is detected from its content."""
    name = 'upload-gripper-owl'
    _remove(app, name)
    try:
        data = {'source_type': 'upload', 'name': name, 'format': '',
                'ontology_file': (io.BytesIO((FIXTURES / 'gripper.ofn').read_bytes()), 'gripper.owl')}
        assert logged_in_client.post('/import', data=data, content_type='multipart/form-data').status_code == 302
        content, version_md, _, _ = _stored(app, name)
        assert version_md['source_format'] == 'ofn' and content.lstrip().startswith('@prefix')
    finally:
        _remove(app, name)


@pytest.mark.integration
def test_unreadable_upload_is_reported(app, logged_in_client):
    data = {'source_type': 'upload', 'name': 'upload-broken', 'format': 'ofn',
            'ontology_file': (io.BytesIO(b'Ontology(<http://x> SubClassOf('), 'broken.ofn')}
    r = logged_in_client.post('/import', data=data, content_type='multipart/form-data')
    assert r.status_code == 200 and b'py-horned-owl could not read' in r.data
    from web.models import db, Ontology
    with app.app_context():
        assert db.session.execute(select(Ontology).where(Ontology.name == 'upload-broken')).scalar_one_or_none() is None


@pytest.mark.integration
def test_url_import_records_the_url(app, logged_in_client, monkeypatch):
    """A URL import converts the fetched RDF/XML once, and the metadata names the URL,
    not the temporary file the importers read."""
    from web.services import ontology_import

    url = 'https://example.org/onto/sensor.rdf'

    class Response:
        text = (FIXTURES / 'sensor.rdf').read_text()

        def raise_for_status(self):
            return None

    monkeypatch.setattr(ontology_import.http_requests, 'get', lambda *a, **kw: Response())
    name = 'url-sensor'
    _remove(app, name)
    try:
        data = {'source_type': 'url', 'name': name, 'format': '', 'source_url': url}
        assert logged_in_client.post('/import', data=data).status_code == 302
        content, version_md, uris, row_md = _stored(app, name)
        Graph().parse(data=content, format='turtle')
        assert 'http://example.org/sensor#Sensor' in uris
        assert (version_md['source'], version_md['source_format']) == (url, 'xml')
        assert row_md['source_url'] == url and row_md['source'] == url
        assert 'source_file' not in row_md
    finally:
        _remove(app, name)
