"""Notification helpers for patient/staff messaging."""
from db import get_db


def send(user_id, title, message):
    if user_id is None:
        return None
    db = get_db()
    cursor = db.execute(
        "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
        (user_id, title, message),
    )
    db.commit()
    return cursor.lastrowid


def broadcast(title, message):
    db = get_db()
    users = db.execute("SELECT id FROM users WHERE is_active = 1").fetchall()
    for user in users:
        send(user["id"], title, message)
    return len(users)


def for_user(user_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()


def unread_count(user_id):
    if user_id is None:
        return 0
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
        (user_id,),
    ).fetchone()
    return row["n"] if row else 0


def mark_read(notification_id, user_id):
    db = get_db()
    db.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
        (notification_id, user_id),
    )
    db.commit()
