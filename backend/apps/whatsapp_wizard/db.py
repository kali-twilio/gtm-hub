"""
WhatsApp Wizard — SQLite persistence layer.
One DB file shared across all users; every table is keyed by user email.
"""
from __future__ import annotations
import base64
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "outputs" / "whatsapp_wizard.db"


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS wa_accounts (
                email           TEXT PRIMARY KEY,
                account_sid     TEXT,
                auth_token_enc  TEXT,
                friendly_name   TEXT,
                connected_at    TEXT
            );
            CREATE TABLE IF NOT EXISTS wa_steps (
                email        TEXT    NOT NULL,
                step         INTEGER NOT NULL,
                status       TEXT    DEFAULT 'pending',
                metadata     TEXT,
                completed_at TEXT,
                PRIMARY KEY (email, step)
            );
            CREATE TABLE IF NOT EXISTS wa_senders (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                twilio_sid   TEXT,
                waba_id      TEXT,
                status       TEXT DEFAULT 'pending',
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(email, phone_number)
            );
            CREATE TABLE IF NOT EXISTS wa_profiles (
                email        TEXT PRIMARY KEY,
                display_name TEXT,
                description  TEXT,
                logo_url     TEXT,
                address      TEXT,
                updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS wa_templates (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT NOT NULL,
                name         TEXT,
                category     TEXT,
                language     TEXT,
                body         TEXT,
                meta_status  TEXT DEFAULT 'pending',
                twilio_sid   TEXT,
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Encryption (Fernet, key derived from Flask SECRET_KEY) ────────────────────

def _fernet(secret_key: str):
    try:
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
        return Fernet(key)
    except ImportError:
        return None


def encrypt_token(value: str, secret_key: str) -> str:
    f = _fernet(secret_key)
    if f:
        return f.encrypt(value.encode()).decode()
    # Fallback: base64 only (dev without cryptography installed)
    log.warning("cryptography not installed — storing token as base64 only")
    return base64.b64encode(value.encode()).decode()


def decrypt_token(value: str, secret_key: str) -> str:
    f = _fernet(secret_key)
    if f:
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            pass
    return base64.b64decode(value.encode()).decode()


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_account(email: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM wa_accounts WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None


def upsert_account(email: str, sid: str, token_enc: str, name: str | None) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO wa_accounts (email, account_sid, auth_token_enc, friendly_name, connected_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
                account_sid=excluded.account_sid,
                auth_token_enc=excluded.auth_token_enc,
                friendly_name=excluded.friendly_name,
                connected_at=excluded.connected_at
        """, (email, sid, token_enc, name, now_iso()))


def get_step(email: str, step: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM wa_steps WHERE email=? AND step=?", (email, step)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
        return d


def upsert_step(email: str, step: int, status: str, metadata: dict | None = None) -> None:
    meta_json = json.dumps(metadata or {})
    completed = now_iso() if status == "complete" else None
    with get_db() as conn:
        conn.execute("""
            INSERT INTO wa_steps (email, step, status, metadata, completed_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(email, step) DO UPDATE SET
                status=excluded.status,
                metadata=excluded.metadata,
                completed_at=COALESCE(excluded.completed_at, wa_steps.completed_at)
        """, (email, step, status, meta_json, completed))


def get_steps(email: str) -> dict[int, dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM wa_steps WHERE email=? ORDER BY step", (email,)
        ).fetchall()
    result = {}
    for row in rows:
        d = dict(row)
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
        result[d["step"]] = d
    return result


def upsert_sender(email: str, phone: str, sid: str, waba_id: str, status: str) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO wa_senders (email, phone_number, twilio_sid, waba_id, status)
            VALUES (?,?,?,?,?)
            ON CONFLICT(email, phone_number) DO UPDATE SET
                twilio_sid=excluded.twilio_sid,
                waba_id=excluded.waba_id,
                status=excluded.status
        """, (email, phone, sid, waba_id, status))


def get_senders(email: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM wa_senders WHERE email=? ORDER BY created_at DESC", (email,)
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_profile(email: str, display_name: str, description: str,
                   logo_url: str | None, address: str) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO wa_profiles (email, display_name, description, logo_url, address, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(email) DO UPDATE SET
                display_name=excluded.display_name,
                description=excluded.description,
                logo_url=COALESCE(excluded.logo_url, wa_profiles.logo_url),
                address=excluded.address,
                updated_at=excluded.updated_at
        """, (email, display_name, description, logo_url, address, now_iso()))


def get_profile(email: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM wa_profiles WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None


def insert_template(email: str, name: str, category: str, language: str,
                    body: str, meta_status: str, twilio_sid: str | None) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO wa_templates (email, name, category, language, body, meta_status, twilio_sid)
            VALUES (?,?,?,?,?,?,?)
        """, (email, name, category, language, body, meta_status, twilio_sid))


def get_templates(email: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM wa_templates WHERE email=? ORDER BY created_at DESC", (email,)
        ).fetchall()
    return [dict(r) for r in rows]


def all_users_summary() -> list[dict]:
    """Admin: return all users with their completed step count."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                a.email,
                a.friendly_name,
                a.connected_at,
                COUNT(CASE WHEN s.status='complete' THEN 1 END) AS completed_steps
            FROM wa_accounts a
            LEFT JOIN wa_steps s ON s.email = a.email
            GROUP BY a.email
            ORDER BY a.connected_at DESC
        """).fetchall()
    return [dict(r) for r in rows]
