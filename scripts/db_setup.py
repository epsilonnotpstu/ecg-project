import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "ecg_system.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            age         INTEGER,
            gender      TEXT,
            symptoms    TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS recordings (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id        INTEGER REFERENCES patients(id),
            session_name      TEXT,
            duration_sec      INTEGER,
            source_type       TEXT DEFAULT 'esp',
            raw_file          TEXT,
            filtered_file     TEXT,
            compare_plot      TEXT,
            bpm_plot          TEXT,
            num_peaks         INTEGER,
            bpm               REAL,
            status            TEXT,
            rr_intervals_json TEXT,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            recording_id INTEGER REFERENCES recordings(id),
            pdf_file     TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database ready at: {DB_PATH}")
