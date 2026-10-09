"""appointments.py — booking, scheduling, status updates (PB-02, PB-03)."""
import sqlite3
from datetime import date as Date, time as Time
from db import get_db
import audit
from auth import current_user


def book(patient_id, doctor_id, date, time, reason):
    """Returns (success: bool, message: str). Prevents double-booking a
    doctor for two overlapping scheduled appointments (PB-02 acceptance
    criterion)."""
    db = get_db()
    try:
        parsed_date = Date.fromisoformat(date)
        Time.fromisoformat(time)
    except (TypeError, ValueError):
        return False, "Enter a valid appointment date and time.", None
    if parsed_date < Date.today():
        return False, "Appointments cannot be booked in the past.", None

    patient = db.execute(
        "SELECT id FROM patients WHERE id=? AND is_active=1", (patient_id,)
    ).fetchone()
    doctor = db.execute(
        "SELECT id FROM users WHERE id=? AND role='doctor' AND is_active=1", (doctor_id,)
    ).fetchone()
    if not patient or not doctor:
        return False, "Select an active patient and doctor.", None

    db.execute("BEGIN IMMEDIATE")
    clash = db.execute(
        """SELECT COUNT(*) AS n FROM appointments
           WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ? AND status = 'scheduled'""",
        (doctor_id, date, time),
    ).fetchone()["n"]

    if clash > 0:
        db.rollback()
        return False, "This doctor already has a scheduled appointment at that date and time. Please choose another slot.", None

    try:
        cur = db.execute(
            "INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason) VALUES (?,?,?,?,?)",
            (patient_id, doctor_id, date, time, reason),
        )
        db.commit()
    except sqlite3.Error:
        db.rollback()
        raise
    u = current_user()
    audit.record(u["id"] if u else None, "create", "appointments", cur.lastrowid,
                 f"Booked appointment for patient #{patient_id} with doctor #{doctor_id}")
    return True, "Appointment booked successfully.", cur.lastrowid


def get(appointment_id):
    db = get_db()
    return db.execute(
        """SELECT a.*, p.full_name AS patient_name, p.user_id AS patient_user_id,
                  u.name AS doctor_name, u.id AS doctor_user_id
           FROM appointments a
           JOIN patients p ON p.id = a.patient_id
           JOIN users u ON u.id = a.doctor_id
           WHERE a.id=?""",
        (appointment_id,),
    ).fetchone()


def cancel(appointment_id):
    db = get_db()
    cur = db.execute(
        "UPDATE appointments SET status = 'cancelled' WHERE id = ? AND status='scheduled'",
        (appointment_id,),
    )
    db.commit()
    u = current_user()
    if cur.rowcount:
        audit.record(u["id"] if u else None, "update", "appointments", appointment_id, "Cancelled appointment")
    return cur.rowcount > 0


def reschedule(appointment_id, appointment_date, appointment_time):
    try:
        parsed_date = Date.fromisoformat(appointment_date)
        Time.fromisoformat(appointment_time)
    except (TypeError, ValueError):
        return False, "Enter a valid appointment date and time."
    if parsed_date < Date.today():
        return False, "Appointments cannot be moved into the past."

    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    appointment = db.execute(
        "SELECT doctor_id, status FROM appointments WHERE id=?", (appointment_id,)
    ).fetchone()
    if not appointment or appointment["status"] != "scheduled":
        db.rollback()
        return False, "Only scheduled appointments can be rescheduled."

    clash = db.execute(
        """SELECT 1 FROM appointments
           WHERE doctor_id=? AND appointment_date=? AND appointment_time=?
             AND status='scheduled' AND id<>?""",
        (appointment["doctor_id"], appointment_date, appointment_time, appointment_id),
    ).fetchone()
    if clash:
        db.rollback()
        return False, "This doctor already has a scheduled appointment at that date and time."
    cur = db.execute(
        "UPDATE appointments SET appointment_date=?, appointment_time=? WHERE id=? AND status='scheduled'",
        (appointment_date, appointment_time, appointment_id),
    )
    db.commit()
    if not cur.rowcount:
        return False, "Only scheduled appointments can be rescheduled."
    u = current_user()
    audit.record(u["id"] if u else None, "update", "appointments", appointment_id, "Rescheduled appointment")
    return True, "Appointment rescheduled successfully."


def complete(appointment_id):
    db = get_db()
    cur = db.execute(
        "UPDATE appointments SET status = 'completed' WHERE id = ? AND status = 'scheduled'",
        (appointment_id,),
    )
    db.commit()
    u = current_user()
    if cur.rowcount:
        audit.record(u["id"] if u else None, "update", "appointments", appointment_id, "Marked appointment completed")
    return cur.rowcount > 0


def for_doctor(doctor_id, date=None):
    db = get_db()
    if date:
        return db.execute(
            """SELECT a.*, p.full_name AS patient_name FROM appointments a
               JOIN patients p ON p.id = a.patient_id
               WHERE a.doctor_id = ? AND a.appointment_date = ?
               ORDER BY a.appointment_date, a.appointment_time""",
            (doctor_id, date),
        ).fetchall()
    return db.execute(
        """SELECT a.*, p.full_name AS patient_name FROM appointments a
           JOIN patients p ON p.id = a.patient_id
           WHERE a.doctor_id = ? ORDER BY a.appointment_date, a.appointment_time""",
        (doctor_id,),
    ).fetchall()


def for_patient(patient_id):
    db = get_db()
    return db.execute(
        """SELECT a.*, u.name AS doctor_name FROM appointments a
           JOIN users u ON u.id = a.doctor_id
           WHERE a.patient_id = ? ORDER BY a.appointment_date DESC, a.appointment_time DESC""",
        (patient_id,),
    ).fetchall()


def all_appointments():
    db = get_db()
    return db.execute(
        """SELECT a.*, p.full_name AS patient_name, u.name AS doctor_name FROM appointments a
           JOIN patients p ON p.id = a.patient_id
           JOIN users u ON u.id = a.doctor_id
           ORDER BY a.appointment_date DESC, a.appointment_time DESC"""
    ).fetchall()
