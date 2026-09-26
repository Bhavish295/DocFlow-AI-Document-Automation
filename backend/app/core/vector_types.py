from __future__ import annotations

import json
from typing import Any

from sqlalchemy.types import TEXT, TypeDecorator


class EmbeddingVector(TypeDecorator):
    """Store embeddings as JSON text.

    Compatible with PostgreSQL (with or without pgvector) and SQLite tests.
    When the DB column is upgraded to pgvector, values are still written in
    bracket-list form that PostgreSQL can cast.
    """

    cache_ok = True
    impl = TEXT

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        values = [float(item) for item in value]
        if dialect.name == "postgresql":
            # Compatible with both text and vector columns.
            return "[" + ",".join(str(item) for item in values) + "]"
        return json.dumps(values)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, list):
            return [float(item) for item in value]
        text = str(value).strip()
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            if not inner:
                return []
            return [float(item.strip()) for item in inner.split(",")]
        return [float(item) for item in json.loads(text)]
