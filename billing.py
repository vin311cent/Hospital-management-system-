"""billing.py — itemised, auto-generated billing (PB-11)."""
from db import get_db
import audit
from auth import current_user


def _open_bill_id(patient_id):
    db = get_db()
    row = db.execute(
        "SELECT id FROM bills WHERE patient_id = ? AND status = 'unpaid' ORDER BY id DESC LIMIT 1",
        (patient_id,),
    ).fetchone()
    if row:
        return row["id"]
    cur = db.execute("INSERT INTO bills (patient_id) VALUES (?)", (patient_id,))
    db.commit()
    return cur.lastrowid


def add_charge(patient_id, description, amount):
    db = get_db()
    bill_id = _open_bill_id(patient_id)
    db.execute(
        "INSERT INTO bill_items (bill_id, description, amount) VALUES (?,?,?)",
        (bill_id, description, amount),
    )
    db.commit()


def add_consultation_fee(patient_id, fee=50.0):
    add_charge(patient_id, "Consultation fee", fee)


def add_lab_fee(patient_id, test_name, fee=30.0):
    add_charge(patient_id, f"Lab test: {test_name}", fee)


def mark_paid(bill_id):
    db = get_db()
    db.execute("UPDATE bills SET status='paid' WHERE id=?", (bill_id,))
    db.commit()
    u = current_user()
    audit.record(u["id"] if u else None, "update", "bills", bill_id, "Marked bill as paid")


def _attach_items(db, bills):
    out = []
    for bill in bills:
        bill = dict(bill)
        line_items = db.execute("SELECT * FROM bill_items WHERE bill_id = ?", (bill["id"],)).fetchall()
        bill["line_items"] = [dict(i) for i in line_items]
        bill["total"] = sum(i["amount"] for i in line_items)
        out.append(bill)
    return out


def for_patient(patient_id):
    db = get_db()
    bills = db.execute(
        "SELECT * FROM bills WHERE patient_id = ? ORDER BY id DESC", (patient_id,)
    ).fetchall()
    return _attach_items(db, bills)


def all_bills():
    db = get_db()
    bills = db.execute(
        """SELECT b.*, p.full_name AS patient_name FROM bills b
           JOIN patients p ON p.id = b.patient_id ORDER BY b.id DESC"""
    ).fetchall()
    out = _attach_items(db, bills)
    for bill in out:
        bill["item_count"] = len(bill["line_items"])
    return out
