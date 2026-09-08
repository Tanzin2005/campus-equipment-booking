from alembic import context
from app.database import make_engine, transaction
from app.models import metadata


def run(connection):
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.config.attributes.get("connection") is not None:
    run(context.config.attributes["connection"])
else:
    engine = make_engine()
    try:
        with transaction(engine, write=True) as connection:
            run(connection)
    finally:
        engine.dispose()
