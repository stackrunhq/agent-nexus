from alembic import context

from agent_nexus.storage.database import metadata

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=metadata)
with context.begin_transaction():
    context.run_migrations()
