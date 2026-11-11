import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "app.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS employee (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL,
            dept     TEXT NOT NULL,
            card_no  TEXT UNIQUE NOT NULL,
            status   TEXT NOT NULL DEFAULT '在职'
        )
    """)
    conn.commit()
    conn.close()
    print("[db] 员工表已就绪")
