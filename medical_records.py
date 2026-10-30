"""Medical records and nursing vitals (PB-04, PB-08)."""
import audit
from auth import current_user
from db import get_db


def for_patient(patient_id):
    db = get_db()
    return db.execute(
        """SELECT mr.*, u.name AS doctor_name FROM medical_records mr
           JOIN users u ON u.id = mr.doctor_id
           WHERE mr.patient_id = ? ORDER BY mr.created_at DESC, mr.id DESC""",
        (patient_id,),
    ).fetchall()


def create(patient_id, doctor_id, appointment_id, data):
    db = get_db()
    cur = db.execute(
        """INSERT INTO medical_records
           (patient_id, doctor_id, appointment_id, diagnosis, notes, temperature, blood_pressure, pulse)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            patient_id,
            doctor_id,
            appointment_id,
            data["diagnosis"],
            data.get("notes") or None,
            data.get("temperature") or None,
            data.get("blood_pressure") or None,
            data.get("pulse") or None,
        ),
    )
    db.commit()
    user = current_user()
    audit.record(
        user["id"] if user else doctor_id,
        "create",
        "medical_records",
        cur.lastrowid,
        f"Added medical record for patient #{patient_id}",
    )
    return cur.lastrowid


def record_vitals(patient_id, data):
    user = current_user()
    if not user:
        raise RuntimeError("A logged-in nurse is required to record vitals.")
    return create(
        patient_id,
        user["id"],
        None,
        {
            "diagnosis": "Nursing vitals",
            "notes": data.get("notes"),
            "temperature": data.get("temperature"),
            "blood_pressure": data.get("blood_pressure"),
            "pulse": data.get("pulse"),
        },
    )


def recent_vitals(limit=15):
    db = get_db()
    return db.execute(
        """SELECT mr.*, p.full_name AS patient_name, u.name AS doctor_name
           FROM medical_records mr
           JOIN patients p ON p.id = mr.patient_id
           JOIN users u ON u.id = mr.doctor_id
           WHERE mr.diagnosis = 'Nursing vitals'
           ORDER BY mr.created_at DESC, mr.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()