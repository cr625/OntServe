"""tools/backfill_base_uri.py (case 24-1 review, lesson L2; review fix).

The rows the dry run lists for a change are exactly the case rows whose
base_uri is the file-name pattern http://proethica.org/ontology/<name># and
whose current content declares another owl:Ontology IRI. A value set by hand
is reported and kept, as the sync keeps it on re-sync; a row without a
declaration is reported and left as is. The dry run writes nothing.

The script runs against a fake session: no database, no app factory.
"""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[2]

CASE_IRI_8 = "http://proethica.org/ontology/case/8"
PATTERN_8 = "http://proethica.org/ontology/proethica-case-8#"


def _header(iri):
    return f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
<{iri}> a owl:Ontology .
"""


NO_HEADER = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://proethica.org/ontology/case/10#Engineer_L> a owl:NamedIndividual ; rdfs:label "Engineer L" .
"""


@pytest.fixture(scope="module")
def backfill():
    """The script as a module, imported with a placeholder database URL
    (web.app_config reads ONTSERVE_DB_URL at import; nothing connects, every
    test replaces make_app). Its own sys.path setup and the app_config module
    it imports for the URL are reverted, so the rest of the suite sees the same
    environment as before."""
    saved_path = list(sys.path)
    had_app_config = "web.app_config" in sys.modules
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ONTSERVE_DB_URL", "postgresql://placeholder:placeholder@localhost:1/placeholder")
        spec = importlib.util.spec_from_file_location("backfill_base_uri", ROOT / "tools" / "backfill_base_uri.py")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = saved_path
            if not had_app_config:
                sys.modules.pop("web.app_config", None)
    return module


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False
        self.rolled_back = False

    def execute(self, stmt):
        return _Scalars(self.rows)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _row(name, base_uri, content, ontology_type="case"):
    return SimpleNamespace(name=name, base_uri=base_uri, current_content=content, ontology_type=ontology_type)


def _rows():
    return [
        _row("proethica-case-10", "http://proethica.org/ontology/proethica-case-10#", NO_HEADER),
        _row("proethica-case-11", "http://proethica.org/ontology/case/11", _header("http://proethica.org/ontology/case/11")),
        _row("proethica-case-8", PATTERN_8, _header(CASE_IRI_8)),
        _row("proethica-case-9", "http://example.org/custom#", _header("http://proethica.org/ontology/case/9")),
        _row("proethica-core", "http://proethica.org/ontology/proethica-core#",
             _header("http://proethica.org/ontology/core"), ontology_type="domain"),
    ]


def _run(backfill, monkeypatch, capsys, argv, rows):
    session = _Session(rows)
    monkeypatch.setattr(backfill, "make_app", lambda: Flask("backfill-test"))
    monkeypatch.setattr(backfill, "db", SimpleNamespace(session=session))
    code = backfill.main(argv)
    return code, session, capsys.readouterr().out.splitlines()


def test_dry_run_lists_exactly_the_pattern_valued_case_rows(backfill, monkeypatch, capsys):
    rows = _rows()
    code, session, out = _run(backfill, monkeypatch, capsys, ["--dry-run"], rows)
    assert code == 0
    assert out == [
        "proethica-case-10: no owl:Ontology declaration",
        "proethica-case-11: unchanged",
        f"proethica-case-8: {PATTERN_8} -> {CASE_IRI_8}",
        "proethica-case-9: hand-set base_uri kept",
        "dry run: 1 of 4 would change",
    ]
    # nothing written, nothing changed on the rows
    assert session.rolled_back and not session.committed
    assert [r.base_uri for r in rows] == [
        "http://proethica.org/ontology/proethica-case-10#", "http://proethica.org/ontology/case/11",
        PATTERN_8, "http://example.org/custom#", "http://proethica.org/ontology/proethica-core#"]


def test_write_run_rewrites_the_pattern_valued_rows_only(backfill, monkeypatch, capsys):
    rows = _rows()
    code, session, out = _run(backfill, monkeypatch, capsys, [], rows)
    assert code == 0
    assert out[-1] == "committed: 1 of 4 changed"
    assert session.committed and not session.rolled_back
    by_name = {r.name: r for r in rows}
    assert by_name["proethica-case-8"].base_uri == CASE_IRI_8
    assert by_name["proethica-case-9"].base_uri == "http://example.org/custom#"
    assert by_name["proethica-case-10"].base_uri == "http://proethica.org/ontology/proethica-case-10#"
    assert by_name["proethica-core"].base_uri == "http://proethica.org/ontology/proethica-core#"


def test_all_examines_every_row(backfill, monkeypatch, capsys):
    rows = _rows()
    _, _, out = _run(backfill, monkeypatch, capsys, ["--all", "--dry-run"], rows)
    assert "proethica-core: http://proethica.org/ontology/proethica-core# -> http://proethica.org/ontology/core" in out
    assert out[-1] == "dry run: 2 of 5 would change"


def test_name_selects_one_row_and_reports_a_missing_one(backfill, monkeypatch, capsys):
    code, _, out = _run(backfill, monkeypatch, capsys, ["--name", "proethica-case-9", "--dry-run"], _rows())
    assert code == 0 and out == ["proethica-case-9: hand-set base_uri kept", "dry run: 0 of 1 would change"]
    code, _, out = _run(backfill, monkeypatch, capsys, ["--name", "proethica-case-99"], _rows())
    assert code == 1 and out == ["proethica-case-99: NOT FOUND"]


def test_select_rows_default_is_the_case_rows(backfill):
    rows = _rows()
    session = _Session(rows)
    names = [r.name for r in backfill.select_rows(session, None, False)]
    assert names == ["proethica-case-10", "proethica-case-11", "proethica-case-8", "proethica-case-9"]
    assert [r.name for r in backfill.select_rows(session, None, True)] == [r.name for r in rows]
    assert [r.name for r in backfill.select_rows(session, "proethica-core", False)] == ["proethica-core"]
