"""audit.py — PB-17: records who did what, to which record, and when."""
from db import get_db


def record(user_id, action, entity, entity_id, details=""):
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (user_id, action, entity, entity_id, details) VALUES (?,?,?,?,?)",
        (user_id, action, entity, entity_id, details),
    )
    db.commit()


def recent(limit=100):
    db = get_db()
    rows = db.execute(
        """SELECT al.*, u.name AS user_name
           FROM audit_log al
           LEFT JOIN users u ON u.id = al.user_id
           ORDER BY al.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return rows
