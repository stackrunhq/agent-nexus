import sqlite3
from pathlib import Path

from .schemas import ModelConfig


class ModelStore:
    """Bootstrap configuration storage; never stores provider secrets."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS models (alias TEXT PRIMARY KEY, config TEXT NOT NULL)"
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def list(self) -> list[ModelConfig]:
        with self.connect() as db:
            return [
                ModelConfig.model_validate_json(row[0])
                for row in db.execute("SELECT config FROM models ORDER BY alias")
            ]

    def get(self, alias: str) -> ModelConfig | None:
        with self.connect() as db:
            row = db.execute("SELECT config FROM models WHERE alias = ?", (alias,)).fetchone()
        return ModelConfig.model_validate_json(row[0]) if row else None

    def put(self, config: ModelConfig):
        with self.connect() as db:
            db.execute(
                "INSERT INTO models VALUES (?, ?) ON CONFLICT(alias) DO UPDATE SET config=excluded.config",
                (config.alias, config.model_dump_json()),
            )
