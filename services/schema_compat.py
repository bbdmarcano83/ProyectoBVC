"""Compatibilidad de esquema para instalaciones legacy SQLite/PostgreSQL.

`Base.metadata.create_all()` crea tablas nuevas pero no agrega columnas faltantes
a tablas ya existentes. Este módulo inspecciona explícitamente las columnas
legacy requeridas y agrega sólo las ausentes con tipos válidos por dialecto.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


REQUIRED_COLUMNS = {
    "usuarios": {
        "telegram_chat_id": "VARCHAR(50)",
        "telegram_codigo": "VARCHAR(10)",
        "broker": "VARCHAR(50)",
        "token_recuperacion": "VARCHAR(100)",
        "token_expira": "TIMESTAMP",
    },
    "transacciones": {
        "motivo": "VARCHAR(50)",
        "tasa_bcv": "FLOAT",
        "score": "INTEGER",
        "fee_total": "FLOAT",
        "neto": "FLOAT",
    },
}


def ensure_legacy_columns(db: Session) -> dict:
    """Agrega sólo columnas faltantes; no borra ni transforma datos existentes."""
    bind = db.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    added: list[str] = []
    skipped_tables: list[str] = []
    errors: list[str] = []

    for table, required in REQUIRED_COLUMNS.items():
        if table not in tables:
            skipped_tables.append(table)
            continue
        existing = {str(c["name"]) for c in inspector.get_columns(table)}
        for column, ddl_type in required.items():
            if column in existing:
                continue
            # Nombres/tipos provienen exclusivamente de constantes internas.
            statement = f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl_type}'
            try:
                db.execute(text(statement))
                db.commit()
                added.append(f"{table}.{column}")
            except Exception as exc:
                db.rollback()
                errors.append(f"{table}.{column}:{type(exc).__name__}")

    return {
        "ok": not errors,
        "dialect": bind.dialect.name,
        "added": added,
        "skipped_tables": skipped_tables,
        "errors": errors,
    }
