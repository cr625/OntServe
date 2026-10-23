"""Database pool resilience against server-side connection loss.

Regression coverage for the ontserve-web 500s of 2026-10-21 and 2026-10-22.
gunicorn runs the app with --preload and --max-requests 1000, so every
replacement worker inherits the pooled connection the master opened at
startup, which the previous worker closed on exit. The first query of the new
worker then failed with ``psycopg2.OperationalError: SSL SYSCALL error: EOF
detected`` (once ``SSL error: decryption failed or bad record mac``), on / and
on entity pages, seconds after each "Booting worker" line.

The pool must discard a dead connection at checkout (pool_pre_ping) and retire
connections on a bounded lifetime (pool_recycle), so a closed connection is a
transparent reconnect rather than a user-visible 500. The in-memory SQLite
database of TestingConfig lives in its one pooled connection, so that
configuration keeps pre_ping without recycle.
"""
from flask import Flask
from sqlalchemy import create_engine, text

from web.app_config import Config, DevelopmentConfig, ProductionConfig, TestingConfig


def _postgres_app(db_url):
    """A Flask app on the PostgreSQL test database with the base Config."""
    from web.models import db

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    db.init_app(app)
    return app


def test_engine_options_enable_pre_ping_and_recycle():
    """The served configurations carry the pool resilience options."""
    for config_class in (Config, DevelopmentConfig, ProductionConfig):
        options = config_class.SQLALCHEMY_ENGINE_OPTIONS
        assert options['pool_pre_ping'] is True
        assert options['pool_recycle'] == 300


def test_testing_config_keeps_pre_ping_without_recycle(app):
    """Recycling the in-memory SQLite connection would drop the test schema."""
    from web.models import db

    assert TestingConfig.SQLALCHEMY_ENGINE_OPTIONS == {'pool_pre_ping': True}
    with app.app_context():
        pool = db.engine.pool
        assert pool._pre_ping is True
        assert pool._recycle == -1


def test_engine_pool_applies_pre_ping_and_recycle(test_db_url):
    """Flask-SQLAlchemy builds the PostgreSQL engine with those options."""
    from web.models import db

    app = _postgres_app(test_db_url)
    with app.app_context():
        pool = db.engine.pool
        assert pool._pre_ping is True
        assert pool._recycle == 300
        db.engine.dispose()


def test_dead_pooled_connection_is_discarded_at_checkout(test_db_url):
    """A connection closed server-side while pooled must not fail the next query.

    Reproduces the incident mechanics: check out a connection, return it to
    the pool, terminate its backend from a separate connection (the exit of
    the previous worker), then run the first query of the next request.
    """
    from web.models import db

    app = _postgres_app(test_db_url)
    with app.app_context():
        with db.engine.connect() as conn:
            backend_pid = conn.execute(text("SELECT pg_backend_pid()")).scalar()

        admin_engine = create_engine(test_db_url)
        try:
            with admin_engine.connect() as admin_conn:
                terminated = admin_conn.execute(
                    text("SELECT pg_terminate_backend(:pid)"),
                    {'pid': backend_pid},
                ).scalar()
                admin_conn.commit()
        finally:
            admin_engine.dispose()
        assert terminated is True

        # First query of the next request: without pre_ping this raises
        # OperationalError (SSL SYSCALL error: EOF detected on production).
        with db.engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
        db.engine.dispose()
