"""Staff account management (PB-13)."""
import sqlite3
import audit
from auth import current_user
from db import get_db
from werkzeug.security import generate_password_hash


def doctors():
    db = get_db()
    return db.execute(
        """SELECT id, name, specialty FROM users
           WHERE role = 'doctor' AND is_active = 1 ORDER BY name"""
    ).fetchall()


def all_accounts():
    db = get_db()
    return db.execute("SELECT * FROM users ORDER BY name").fetchall()


def create(name, email, password, role, specialty=None, phone=None):
    db = get_db()
    try:
        cur = db.execute(
            """INSERT INTO users (name, email, password_hash, role, specialty, phone)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                name,
                email.lower(),
                generate_password_hash(password),
                role,
                specialty,
                phone,
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return False, "An account with that email already exists or the selected role is invalid."
    user = current_user()
    audit.record(
        user["id"] if user else None,
        "create",
        "users",
        cur.lastrowid,
        f"Created {role} account for {email}",
    )
    return True, "Account created successfully."


def set_active(user_id, is_active):
    db = get_db()
    cur = db.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, user_id),
    )
    db.commit()
    user = current_user()
    if cur.rowcount:
        action = "Activated" if is_active else "Deactivated"
        audit.record(
            user["id"] if user else None,
            "update",
            "users",
            user_id,
            f"{action} account",
        )
    return cur.rowcount > 0