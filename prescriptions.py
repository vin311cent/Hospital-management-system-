"""Prescription issuing and dispensing (PB-05, PB-06)."""
import audit
import billing
from auth import current_user
from db import get_db


def for_patient(patient_id):
    db = get_db()
    return db.execute(
        """SELECT rx.*, u.name AS doctor_name, m.name AS medicine_name
           FROM prescriptions rx
           JOIN users u ON u.id = rx.doctor_id
           JOIN medicines m ON m.id = rx.medicine_id
           WHERE rx.patient_id = ? ORDER BY rx.created_at DESC, rx.id DESC""",
        (patient_id,),
    ).fetchall()


def pending_queue():
    db = get_db()
    return db.execute(
        """SELECT rx.*, p.full_name AS patient_name, u.name AS doctor_name,
                  m.name AS medicine_name
           FROM prescriptions rx
           JOIN patients p ON p.id = rx.patient_id
           JOIN users u ON u.id = rx.doctor_id
           JOIN medicines m ON m.id = rx.medicine_id
           WHERE rx.status = 'pending'
           ORDER BY rx.created_at, rx.id"""
    ).fetchall()


def issue(patient_id, doctor_id, medical_record_id, medicine_id, dosage, frequency, duration, quantity):
    if quantity < 1:
        raise ValueError("Prescription quantity must be positive.")
    db = get_db()
    cur = db.execute(
        """INSERT INTO prescriptions
           (patient_id, doctor_id, medical_record_id, medicine_id, dosage, frequency, duration, quantity)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            patient_id,
            doctor_id,
            medical_record_id,
            medicine_id,
            dosage,
            frequency,
            duration,
            quantity,
        ),
    )
    db.commit()
    user = current_user()
    audit.record(
        user["id"] if user else doctor_id,
        "create",
        "prescriptions",
        cur.lastrowid,
        f"Issued prescription for patient #{patient_id}",
    )
    return cur.lastrowid


def dispense(prescription_id):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        """SELECT rx.*, m.name AS medicine_name, m.stock_qty, m.unit_price
           FROM prescriptions rx
           JOIN medicines m ON m.id = rx.medicine_id
           WHERE rx.id = ?""",
        (prescription_id,),
    ).fetchone()
    if not row or row["status"] != "pending":
        db.rollback()
        return False, "Prescription not found or already dispensed."
    if row["stock_qty"] < row["quantity"]:
        db.rollback()
        return False, f"Insufficient stock of {row['medicine_name']}."
    user = current_user()
    if not user:
        db.rollback()
        raise RuntimeError("A logged-in pharmacist is required to dispense prescriptions.")
    db.execute(
        "UPDATE medicines SET stock_qty = stock_qty - ? WHERE id = ?",
        (row["quantity"], row["medicine_id"]),
    )
    db.execute(
        """UPDATE prescriptions
           SET status = 'dispensed', dispensed_by = ?, dispensed_at = datetime('now')
           WHERE id = ? AND status = 'pending'""",
        (user["id"], prescription_id),
    )
    db.commit()
    billing.add_charge(
        row["patient_id"],
        f"Medication: {row['medicine_name']} × {row['quantity']}",
        row["unit_price"] * row["quantity"],
    )
    audit.record(
        user["id"],
        "update",
        "prescriptions",
        prescription_id,
        "Dispensed prescription",
    )
    return True, "Prescription dispensed successfully."