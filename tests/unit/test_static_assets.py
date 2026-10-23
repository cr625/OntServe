"""Static URLs carry a content version, so a deploy replaces the copies that
Cloudflare and browsers keep under the 7-day max-age nginx sends for /static/."""

from flask import url_for

from web.static_assets import asset_version


def test_version_follows_the_content(tmp_path):
    asset = tmp_path / 'site.css'
    asset.write_text('a { color: red; }')
    first = asset_version(str(tmp_path), 'site.css')
    assert first is not None and len(first) == 10
    assert asset_version(str(tmp_path), 'site.css') == first
    asset.write_text('a { color: purple; }')
    assert asset_version(str(tmp_path), 'site.css') != first


def test_missing_file_has_no_version(tmp_path):
    assert asset_version(str(tmp_path), 'absent.css') is None


def test_static_urls_carry_the_version(app):
    with app.test_request_context():
        stylesheet = url_for('static', filename='css/style.css')
        missing = url_for('static', filename='css/absent.css')
    version = asset_version(app.static_folder, 'css/style.css')
    assert stylesheet == f'/static/css/style.css?v={version}'
    assert missing == '/static/css/absent.css'
