"""lab.py — lab test requests and results (PB-10)."""
from db import get_db
import audit
import billing
from auth import current_user


def request_test(patient_id, doctor_id, test_name):
    db = get_db()
    cur = db.execute(
        "INSERT INTO lab_requests (patient_id, doctor_id, test_name) VALUES (?,?,?)",
        (patient_id, doctor_id, test_name),
    )
    db.commit()
    billing.add_lab_fee(patient_id, test_name)
    u = current_user()
    audit.record(u["id"] if u else None, "create", "lab_requests", cur.lastrowid,
                 f"Requested lab test '{test_name}' for patient #{patient_id}")
    return cur.lastrowid


def complete(request_id, result):
    db = get_db()
    cur = db.execute(
        """UPDATE lab_requests SET status='completed', result=?, completed_at=datetime('now')
           WHERE id=? AND status='requested'""",
        (result, request_id),
    )
    db.commit()
    u = current_user()
    if cur.rowcount:
        audit.record(u["id"] if u else None, "update", "lab_requests", request_id, "Uploaded lab result")
    return cur.rowcount > 0


def pending():
    db = get_db()
    return db.execute(
        """SELECT lr.*, p.full_name AS patient_name, u.name AS doctor_name
           FROM lab_requests lr
           JOIN patients p ON p.id = lr.patient_id
           JOIN users u ON u.id = lr.doctor_id
           WHERE lr.status = 'requested' ORDER BY lr.requested_at"""
    ).fetchall()


def for_doctor(doctor_id):
    db = get_db()
    return db.execute(
        """SELECT lr.*, p.full_name AS patient_name FROM lab_requests lr
           JOIN patients p ON p.id = lr.patient_id
           WHERE lr.doctor_id = ? AND lr.status = 'completed'
           ORDER BY lr.completed_at DESC""",
        (doctor_id,),
    ).fetchall()


def find(request_id):
    db = get_db()
    return db.execute(
        """SELECT lr.*, p.user_id AS patient_user_id FROM lab_requests lr
           JOIN patients p ON p.id = lr.patient_id WHERE lr.id=?""",
        (request_id,),
    ).fetchone()


def for_patient(patient_id):
    db = get_db()
    return db.execute(
        """SELECT lr.*, u.name AS doctor_name FROM lab_requests lr
           JOIN users u ON u.id = lr.doctor_id
           WHERE lr.patient_id = ? ORDER BY lr.requested_at DESC""",
        (patient_id,),
    ).fetchall()
