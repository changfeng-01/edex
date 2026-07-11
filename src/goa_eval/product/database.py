from __future__ import annotations

from sqlalchemy import Engine, create_engine, event

from goa_eval.product.orm import Base


def make_engine(database_url: str) -> Engine:
    engine = create_engine(database_url)
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
