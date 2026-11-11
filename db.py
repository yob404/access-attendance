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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            card_no    TEXT NOT NULL,
            door_id    TEXT NOT NULL,
            punch_time TEXT NOT NULL,
            result     TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS door_permission (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            door_id     TEXT NOT NULL,
            start_time  TEXT NOT NULL,
            end_time    TEXT NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS device (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id      TEXT UNIQUE NOT NULL,
            door_id        TEXT NOT NULL,
            ip             TEXT,
            last_heartbeat TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    print("[db] 四张表已就绪")
