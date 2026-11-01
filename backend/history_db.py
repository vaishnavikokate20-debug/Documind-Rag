
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "pdf_history.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS pdf_history (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                pages INTEGER NOT NULL,
                chunks INTEGER NOT NULL
            )
        """)


def add_pdf(record):
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO pdf_history
            (id, filename, stored_path, uploaded_at, pages, chunks)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            record["id"],
            record["filename"],
            record["stored_path"],
            record["uploaded_at"],
            record["pages"],
            record["chunks"],
        ))


def list_pdfs():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, filename, uploaded_at, pages, chunks
            FROM pdf_history
            ORDER BY uploaded_at DESC
        """).fetchall()

    return [dict(row) for row in rows]


def get_pdf(pdf_id):
    with get_connection() as connection:
        row = connection.execute("""
            SELECT *
            FROM pdf_history
            WHERE id = ?
        """, (pdf_id,)).fetchone()

    return dict(row) if row else None
def delete_pdf(pdf_id):
    with get_connection() as connection:
        cursor = connection.execute("""
            DELETE FROM pdf_history
            WHERE id = ?
        """, (pdf_id,))

        return cursor.rowcount > 0