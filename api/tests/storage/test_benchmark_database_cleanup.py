from contextlib import contextmanager
import re

import pytest
from sqlalchemy.engine import make_url

from agent_nexus_cli.postgres_pipeline import disposable_database


@pytest.mark.parametrize("create_fails", [False, True])
def test_disposable_database_only_drops_owned_name_on_failure(monkeypatch, create_fails):
    statements = []
    disposed = []

    class Engine:
        @contextmanager
        def connect(self):
            yield self

        def execute(self, statement):
            statements.append(str(statement))
            if create_fails and str(statement).startswith("CREATE"):
                raise RuntimeError("creation failed")

        def dispose(self):
            disposed.append(True)

    monkeypatch.setattr("agent_nexus_cli.postgres_pipeline.create_engine", lambda *a, **k: Engine())
    with (
        pytest.raises(RuntimeError),
        disposable_database("postgresql+psycopg://localhost/original") as target,
    ):
        name = make_url(target).database
        assert re.fullmatch(r"nexus_pipeline_[a-f0-9]{32}", name)
        raise RuntimeError("scenario failed")
    assert disposed == [True]
    if create_fails:
        assert len(statements) == 1
    else:
        assert statements == [f"CREATE DATABASE {name}", f"DROP DATABASE {name} WITH (FORCE)"]
