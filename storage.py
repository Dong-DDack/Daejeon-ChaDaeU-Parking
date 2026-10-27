"""성공한 snapshot과 KST 날짜별 마지막 성공값을 트랜잭션으로 보존."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect():
    url = os.getenv('DATABASE_URL')
    if url:
        import psycopg
        connection = psycopg.connect(url, connect_timeout=8)
    else:
        if os.getenv('VERCEL'):
            raise RuntimeError('DATABASE_URL required')
        connection = sqlite3.connect(Path(__file__).parent / 'parking.db', timeout=10)
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS daily (day TEXT NOT NULL, parking_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(day, parking_id))')
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def sql(statement):
    return statement.replace('?', '%s') if os.getenv('DATABASE_URL') else statement


def latest():
    with connect() as db:
        row = db.execute("SELECT payload FROM snapshots WHERE id='latest'").fetchone()
        return json.loads(row[0]) if row else None


def save(snapshot):
    with connect() as db:
        db.execute(sql("INSERT INTO snapshots(id,payload) VALUES('latest',?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload"), (json.dumps(snapshot, ensure_ascii=False),))
        for item in snapshot['items']:
            record = dict(item, fetched_at=snapshot['fetched_at'], day=snapshot['day'], source_url=snapshot['source_url'])
            db.execute(sql('INSERT INTO daily(day,parking_id,payload) VALUES(?,?,?) ON CONFLICT(day,parking_id) DO UPDATE SET payload=excluded.payload'),
                       (snapshot['day'], item['id'], json.dumps(record, ensure_ascii=False)))


def history(parking_id):
    with connect() as db:
        rows = db.execute(sql('SELECT payload FROM daily WHERE parking_id=? ORDER BY day DESC LIMIT 30'), (parking_id,)).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]
