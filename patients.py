"""Patient records and self-service account operations."""
import audit
from auth import current_user
from db import get_db
from werkzeug.security import generate_password_hash


def all_patients():
    db = get_db()
    return db.execute(
        "SELECT * FROM patients WHERE is_active = 1 ORDER BY full_name"
    ).fetchall()


def search(term):
    db = get_db()
    pattern = f"%{term.strip()}%"
    return db.execute(
        """SELECT * FROM patients
           WHERE is_active = 1
             AND (full_name LIKE ? COLLATE NOCASE OR phone LIKE ? OR CAST(id AS TEXT) = ?)
           ORDER BY full_name""",
        (pattern, pattern, term.strip()),
    ).fetchall()


def find(patient_id):
    db = get_db()
    return db.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()


def find_by_user_id(user_id):
    db = get_db()
    return db.execute("SELECT * FROM patients WHERE user_id = ?", (user_id,)).fetchone()


def create(data):
    db = get_db()
    cur = db.execute(
        """INSERT INTO patients
           (full_name, dob, gender, phone, address, next_of_kin_name, next_of_kin_phone)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data["full_name"],
            data.get("dob"),
            data.get("gender"),
            data.get("phone"),
            data.get("address"),
            data.get("next_of_kin_name"),
            data.get("next_of_kin_phone"),
        ),
    )
    db.commit()
    user = current_user()
    audit.record(
        user["id"] if user else None,
        "create",
        "patients",
        cur.lastrowid,
        f"Registered patient '{data['full_name']}'",
    )
    return cur.lastrowid


def register_account(data):
    db = get_db()
    cur = db.execute(
        """INSERT INTO users (name, email, password_hash, role, phone)
           VALUES (?, ?, ?, 'patient', ?)""",
        (
            data["full_name"],
            data["email"].lower(),
            generate_password_hash(data["password"]),
            data.get("phone"),
        ),
    )
    user_id = cur.lastrowid
    patient_cur = db.execute(
        """INSERT INTO patients
           (user_id, full_name, dob, gender, phone, address, next_of_kin_name, next_of_kin_phone)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            data["full_name"],
            data.get("dob") or None,
            data.get("gender") or None,
            data.get("phone"),
            data.get("address"),
            data.get("next_of_kin_name"),
            data.get("next_of_kin_phone"),
        ),
    )
    db.commit()
    audit.record(user_id, "create", "patients", patient_cur.lastrowid, "Patient account registered")
    return patient_cur.lastrowid


def deactivate(patient_id):
    db = get_db()
    cur = db.execute("UPDATE patients SET is_active = 0 WHERE id = ?", (patient_id,))
    db.commit()
    user = current_user()
    if cur.rowcount:
        audit.record(user["id"] if user else None, "update", "patients", patient_id, "Deactivated patient")
    return cur.rowcount > 0


def update_own_profile(user_id, data):
    db = get_db()
    db.execute(
        """UPDATE patients
           SET full_name = ?, dob = ?, gender = ?, phone = ?, address = ?,
               next_of_kin_name = ?, next_of_kin_phone = ?
           WHERE user_id = ?""",
        (
            data["full_name"],
            data.get("dob") or None,
            data.get("gender") or None,
            data.get("phone") or None,
            data.get("address") or None,
            data.get("next_of_kin_name") or None,
            data.get("next_of_kin_phone") or None,
            user_id,
        ),
    )
    db.execute("UPDATE users SET name = ?, phone = ? WHERE id = ?", (data["full_name"], data.get("phone") or None, user_id))
    db.commit()
    audit.record(user_id, "update", "patients", user_id, "Updated patient profile")