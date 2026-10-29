import os
import time

import psycopg2
from flask import Flask, jsonify, request
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "notesdb")
DB_USER = os.getenv("DB_USER", "appuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "change-me")


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=3,
    )


def initialize_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)


@app.get("/health")
def health():
    try:
        initialize_table()
        return jsonify(status="ok", database="connected")
    except Exception:
        app.logger.exception("Database health check failed")
        return jsonify(status="error", database="unavailable"), 503


@app.get("/notes")
def list_notes():
    try:
        initialize_table()
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, content, created_at FROM notes ORDER BY id"
                )
                rows = cur.fetchall()
        return jsonify(rows)
    except Exception:
        app.logger.exception("Unable to read notes")
        return jsonify(error="Database unavailable"), 503


@app.post("/notes")
def create_note():
    body = request.get_json(silent=True) or {}
    content = body.get("content")

    if not isinstance(content, str) or not content.strip():
        return jsonify(error="Provide a non-empty content field"), 400

    try:
        initialize_table()
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO notes (content) VALUES (%s) "
                    "RETURNING id, content, created_at",
                    (content.strip(),),
                )
                row = cur.fetchone()
        return jsonify(row), 201
    except Exception:
        app.logger.exception("Unable to create note")
        return jsonify(error="Database unavailable"), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
