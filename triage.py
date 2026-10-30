"""Triage queue helpers for nurse screening."""
from db import get_db

PRIORITIES = ["routine", "priority", "urgent", "immediate"]


def active_queue():
    db = get_db()
    return db.execute(
        """
        SELECT tr.*, p.full_name AS patient_name, u.name AS nurse_name
        FROM triage_records tr
        JOIN patients p ON p.id = tr.patient_id
        JOIN users u ON u.id = tr.nurse_id
        WHERE tr.status = 'active'
        ORDER BY
            CASE tr.priority
                WHEN 'immediate' THEN 1
                WHEN 'urgent' THEN 2
                WHEN 'priority' THEN 3
                ELSE 4
            END,
            tr.created_at DESC
        """
    ).fetchall()


def for_patient(patient_id):
    db = get_db()
    return db.execute(
        """
        SELECT tr.*, u.name AS nurse_name
        FROM triage_records tr
        JOIN users u ON u.id = tr.nurse_id
        WHERE tr.patient_id = ?
        ORDER BY tr.created_at DESC
        """,
        (patient_id,),
    ).fetchall()


def record(patient_id, nurse_id, priority, assessment, temperature=None, blood_pressure=None, pulse=None):
    if priority not in PRIORITIES:
        raise ValueError("Invalid triage priority selected.")
    db = get_db()
    db.execute(
        """
        INSERT INTO triage_records (
            patient_id, nurse_id, priority, assessment, temperature, blood_pressure, pulse, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (patient_id, nurse_id, priority, assessment, temperature, blood_pressure, pulse),
    )
    db.commit()


def resolve(triage_id):
    db = get_db()
    row = db.execute(
        "SELECT id FROM triage_records WHERE id = ? AND status = 'active'",
        (triage_id,),
    ).fetchone()
    if not row:
        return False
    db.execute(
        "UPDATE triage_records SET status = 'resolved', resolved_at = datetime('now') WHERE id = ?",
        (triage_id,),
    )
    db.commit()
    return True
