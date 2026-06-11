"""One-time migration: copy finance.db (SQLite) into the Postgres DATABASE_URL.

Applies schema.pg.sql if the tables don't exist yet, copies all rows with
their original ids, then resets the identity sequences. Safe to re-run only
against an empty database — it refuses to run if users already has rows.

Usage: python scripts/migrate_sqlite_to_pg.py
"""
import os
import sqlite3
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TABLES = {
    "users": ["id", "username", "hash", "cash"],
    "portfolio": ["id", "user_id", "symbol", "shares", "bought_price", "current_price"],
    "snapshots": ["id", "user_id", "date", "total_value"],
    "history": ["id", "user_id", "symbol", "shares", "method", "price", "timestamp"],
}

database_url = os.environ.get("DATABASE_URL")
if not database_url or not database_url.startswith("postgres"):
    sys.exit("DATABASE_URL is not set to a Postgres URL; see .env")

lite = sqlite3.connect(os.path.join(ROOT, "finance.db"))
pg = psycopg2.connect(database_url)
cur = pg.cursor()

# create tables on first run
cur.execute("SELECT to_regclass('users')")
if cur.fetchone()[0] is None:
    with open(os.path.join(ROOT, "schema.pg.sql")) as f:
        cur.execute(f.read())
    print("applied schema.pg.sql")

cur.execute("SELECT COUNT(*) FROM users")
if cur.fetchone()[0] > 0:
    sys.exit("Target database already has users — refusing to migrate on top of data.")

for table, columns in TABLES.items():
    rows = lite.execute(
        f"SELECT {', '.join(columns)} FROM {table} ORDER BY id"
    ).fetchall()
    placeholders = ", ".join(["%s"] * len(columns))
    quoted = ", ".join(f'"{c}"' for c in columns)
    for row in rows:
        cur.execute(f'INSERT INTO {table} ({quoted}) VALUES ({placeholders})', row)
    # future inserts must not collide with the ids we just copied
    cur.execute(
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
        f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
    )
    print(f"{table}: {len(rows)} rows")

pg.commit()

for table in TABLES:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    expected = lite.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    actual = cur.fetchone()[0]
    status = "OK" if actual == expected else "MISMATCH"
    print(f"verify {table}: sqlite={expected} pg={actual} {status}")

cur.close()
pg.close()
lite.close()
