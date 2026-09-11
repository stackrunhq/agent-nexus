import json
import os
from uuid import uuid4
import pytest
from sqlalchemy import text
from agent_nexus.core.errors import GatewayError
from agent_nexus.knowledge import pgvector_backend as backend
from agent_nexus.storage.database import Database


def test_backend_explicit_opt_in_and_sqlite_rejection(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "test.db"))
    try:
        monkeypatch.delenv("NEXUS_VECTOR_BACKEND", raising=False)
        assert not backend.enabled(database)
        monkeypatch.setenv("NEXUS_VECTOR_BACKEND", "pgvector")
        with pytest.raises(GatewayError) as error:
            backend.enabled(database)
        assert error.value.code == "vector_backend_unavailable"
        monkeypatch.setenv("NEXUS_VECTOR_BACKEND", "typo")
        with pytest.raises(RuntimeError):
            backend.enabled(database)
    finally:
        database.close()


def test_snapshot_signature_binds_vector_values():
    assert backend.signature("[[1,0]]") != backend.signature("[[0,1]]")


@pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_PGVECTOR_URL"), reason="Requires dedicated pgvector test database"
)
def test_native_exact_ranking_scope_and_rebuild():
    database = Database(os.environ["NEXUS_TEST_PGVECTOR_URL"], prepare=False)
    version = str(uuid4())
    payload = json.dumps([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
    try:
        backend.setup(database)
        with database.write("test-pgvector") as db:
            backend.save(db, version, "test", payload)
        ranked = backend.rank(database, version, "test", payload, [1.0, 0.0], 3)
        assert [row["ordinal"] for row in ranked] == [0, 1, 2]
        assert [row["score"] for row in ranked] == pytest.approx([1, 0, -1], abs=1e-6)
        for other_version, other_model, other_payload in [
            ("missing", "test", payload),
            (version, "missing", payload),
            (version, "test", "[[0,1]]"),
        ]:
            with pytest.raises(GatewayError) as error:
                backend.rank(database, other_version, other_model, other_payload, [1, 0], 3)
            assert error.value.code == "pgvector_rebuild_required"
    finally:
        with database.write("test-pgvector") as db:
            db.execute(
                text("DELETE FROM nexus_vectors.entries WHERE version_id=:version"),
                {"version": version},
            )
        database.close()
