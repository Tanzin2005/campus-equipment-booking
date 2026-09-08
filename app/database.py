"""Database configuration and transaction boundaries for SQLite/PostgreSQL."""
import os
from contextlib import contextmanager
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parent.parent


def database_url():
    url = os.getenv('DATABASE_URL')
    if url:
        if url.startswith('postgres://'):
            url = 'postgresql+psycopg://' + url[len('postgres://'):]
        elif url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
        return url
    path = Path(os.getenv('BOOKING_DB', str(ROOT / 'data/bookings.db'))).resolve()
    return 'sqlite:///' + path.as_posix()


def make_engine(url=None):
    url = url or database_url()
    if url.startswith('sqlite'):
        from sqlalchemy.engine import make_url
        database = make_url(url).database
        if database and database != ':memory:':
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        options = {'connect_args': {'check_same_thread': False, 'timeout': 10}}
        if database == ':memory:':
            options['poolclass'] = StaticPool
        engine = create_engine(url, **options)

        @event.listens_for(engine, 'connect')
        def configure(dbapi, _):
            dbapi.isolation_level = None
            dbapi.execute('PRAGMA foreign_keys=ON')

        @event.listens_for(engine, 'begin')
        def begin(connection):
            mode = 'BEGIN IMMEDIATE' if connection.get_execution_options().get('write_lock') else 'BEGIN'
            connection.exec_driver_sql(mode)
        return engine
    return create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 10})


@contextmanager
def transaction(engine, write=False):
    with engine.connect().execution_options(write_lock=write) as db:
        with db.begin():
            yield db


def migrate(engine):
    # Back up the original SQLite schema before its first upgrade.
    if engine.dialect.name == 'sqlite' and engine.url.database not in {None, ':memory:'}:
        import sqlite3
        source = Path(engine.url.database)
        if source.exists() and source.stat().st_size:
            with sqlite3.connect(source) as legacy:
                columns = {row[1] for row in legacy.execute('PRAGMA table_info(bookings)')}
                backup = source.with_name(source.stem + '.pre-v1.db')
                if columns and 'user_id' not in columns and not backup.exists():
                    with sqlite3.connect(backup) as destination:
                        legacy.backup(destination)
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'migrations'))
    with transaction(engine, write=True) as db:
        if engine.dialect.name == 'postgresql':
            db.exec_driver_sql('SELECT pg_advisory_xact_lock(910001)')
        config.attributes['connection'] = db
        command.upgrade(config, 'head')
