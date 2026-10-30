"""Ward bed occupancy and admission operations (PB-09, PB-14)."""
import audit
from auth import current_user
from db import get_db


def beds_with_occupant():
    db = get_db()
    return db.execute(
        """SELECT b.*, w.name AS ward_name, p.full_name AS patient_name
           FROM beds b
           JOIN wards w ON w.id = b.ward_id
           LEFT JOIN patients p ON p.id = b.patient_id
           ORDER BY w.name, b.bed_number"""
    ).fetchall()


def admit(bed_id, patient_id):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    bed = db.execute("SELECT status FROM beds WHERE id = ?", (bed_id,)).fetchone()
    patient = db.execute(
        "SELECT id FROM patients WHERE id = ? AND is_active = 1", (patient_id,)
    ).fetchone()
    if not bed or bed["status"] != "vacant":
        db.rollback()
        return False, "That bed is not available."
    if not patient:
        db.rollback()
        return False, "Select an active patient."
    db.execute(
        """UPDATE beds SET status = 'occupied', patient_id = ?,
           admitted_at = datetime('now'), discharged_at = NULL WHERE id = ?""",
        (patient_id, bed_id),
    )
    db.commit()
    user = current_user()
    audit.record(
        user["id"] if user else None,
        "update",
        "beds",
        bed_id,
        f"Admitted patient #{patient_id}",
    )
    return True, "Patient admitted successfully."


def discharge(bed_id):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    bed = db.execute(
        "SELECT status, patient_id FROM beds WHERE id = ?", (bed_id,)
    ).fetchone()
    if not bed or bed["status"] != "occupied":
        db.rollback()
        return False, "That bed is not occupied."
    db.execute(
        """UPDATE beds SET status = 'vacant', patient_id = NULL,
           discharged_at = datetime('now') WHERE id = ?""",
        (bed_id,),
    )
    db.commit()
    user = current_user()
    audit.record(
        user["id"] if user else None,
        "update",
        "beds",
        bed_id,
        f"Discharged patient #{bed['patient_id']}",
    )
    return True, "Patient discharged successfully."