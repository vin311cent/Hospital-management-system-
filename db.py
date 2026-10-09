"""
db.py — SQLite connection handling, schema creation and demo seed data
for the MediCare HMS Flask port.
"""
import sqlite3
import os
from flask import g, current_app


def get_db():
    """Return a request-scoped SQLite connection (rows behave like dicts)."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','doctor','nurse','receptionist','pharmacist','lab_technician','patient')),
    specialty TEXT,
    phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    full_name TEXT NOT NULL,
    dob TEXT,
    gender TEXT,
    phone TEXT,
    address TEXT,
    next_of_kin_name TEXT,
    next_of_kin_phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES users(id),
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled','completed','cancelled')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE medical_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES users(id),
    appointment_id INTEGER REFERENCES appointments(id),
    diagnosis TEXT NOT NULL,
    notes TEXT,
    temperature TEXT,
    blood_pressure TEXT,
    pulse TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE medicines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    stock_qty INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 10,
    unit_price REAL NOT NULL DEFAULT 0
);

CREATE TABLE prescriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES users(id),
    medical_record_id INTEGER REFERENCES medical_records(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    dosage TEXT NOT NULL,
    frequency TEXT NOT NULL,
    duration TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','dispensed','cancelled')),
    dispensed_by INTEGER REFERENCES users(id),
    dispensed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE wards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE beds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ward_id INTEGER NOT NULL REFERENCES wards(id) ON DELETE CASCADE,
    bed_number TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'vacant' CHECK(status IN ('vacant','occupied')),
    patient_id INTEGER REFERENCES patients(id),
    admitted_at TEXT,
    discharged_at TEXT
);

CREATE TABLE lab_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES users(id),
    test_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested' CHECK(status IN ('requested','completed')),
    result TEXT,
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'unpaid' CHECK(status IN ('unpaid','paid')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE bill_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount REAL NOT NULL
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE triage_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    nurse_id INTEGER NOT NULL REFERENCES users(id),
    priority TEXT NOT NULL CHECK(priority IN ('routine','priority','urgent','immediate')),
    assessment TEXT NOT NULL,
    temperature TEXT,
    blood_pressure TEXT,
    pulse TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','resolved')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _seed(db):
    from werkzeug.security import generate_password_hash
    pwd = generate_password_hash("password123")

    users = [
        ("Admin User", "admin@medicare.zm", pwd, "admin", None, "0970000001"),
        ("Dr. Chanda Mwansa", "chanda.mwansa@medicare.zm", pwd, "doctor", "General Medicine", "0970000002"),
        ("Dr. Bwalya Phiri", "bwalya.phiri@medicare.zm", pwd, "doctor", "Paediatrics", "0970000003"),
        ("Nurse Grace Tembo", "grace.tembo@medicare.zm", pwd, "nurse", None, "0970000004"),
        ("Mercy Banda", "mercy.banda@medicare.zm", pwd, "receptionist", None, "0970000005"),
        ("Joseph Lungu", "joseph.lungu@medicare.zm", pwd, "pharmacist", None, "0970000006"),
        ("Patricia Mulenga", "patricia.mulenga@medicare.zm", pwd, "lab_technician", None, "0970000008"),
        ("John Zulu", "john.zulu@medicare.zm", pwd, "patient", None, "0970000007"),
    ]
    db.executemany(
        "INSERT INTO users (name, email, password_hash, role, specialty, phone) VALUES (?,?,?,?,?,?)",
        users,
    )

    # John Zulu is the 8th inserted user -> id 8
    db.execute(
        "INSERT INTO patients (user_id, full_name, dob, gender, phone, address, next_of_kin_name, next_of_kin_phone) "
        "VALUES (8,'John Zulu','1994-03-12','Male','0970000007','Kabwata, Lusaka','Mary Zulu','0970000099')"
    )
    db.execute(
        "INSERT INTO patients (full_name, dob, gender, phone, address, next_of_kin_name, next_of_kin_phone) "
        "VALUES ('Esther Mumba','2001-07-02','Female','0961111111','Chilenje, Lusaka','Peter Mumba','0961111100')"
    )
    db.execute(
        "INSERT INTO patients (full_name, dob, gender, phone, address, next_of_kin_name, next_of_kin_phone) "
        "VALUES ('Kelvin Sakala','1988-11-20','Male','0962222222','Kalingalinga, Lusaka','Ruth Sakala','0962222200')"
    )

    meds = [
        ("Paracetamol 500mg", 500, 50, 1.50),
        ("Amoxicillin 250mg", 200, 30, 4.20),
        ("Ibuprofen 200mg", 8, 20, 2.00),  # deliberately low, to demo the reorder alert
        ("ORS Sachets", 150, 40, 0.80),
        ("Metformin 500mg", 120, 25, 3.10),
    ]
    db.executemany(
        "INSERT INTO medicines (name, stock_qty, reorder_level, unit_price) VALUES (?,?,?,?)", meds
    )

    wards = ["General Ward", "Maternity Ward", "ICU"]
    db.executemany("INSERT INTO wards (name) VALUES (?)", [(w,) for w in wards])

    bed_plan = {1: 4, 2: 4, 3: 2}
    for ward_id, count in bed_plan.items():
        for i in range(1, count + 1):
            db.execute(
                "INSERT INTO beds (ward_id, bed_number) VALUES (?,?)",
                (ward_id, f"B{ward_id}-{i:02d}"),
            )

    db.execute(
        "INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status) "
        "VALUES (1,2,date('now'),'09:00','Routine checkup','scheduled')"
    )
    db.execute(
        "UPDATE beds SET status='occupied', patient_id=2, admitted_at=datetime('now') WHERE id=1"
    )


def init_db(app):
    """Create/seed new databases and apply additive schema upgrades."""
    db_path = app.config["DATABASE"]
    is_new = not os.path.exists(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    if is_new:
        conn.executescript(SCHEMA)
        _seed(conn)
    else:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS triage_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                nurse_id INTEGER NOT NULL REFERENCES users(id),
                priority TEXT NOT NULL CHECK(priority IN ('routine','priority','urgent','immediate')),
                assessment TEXT NOT NULL,
                temperature TEXT,
                blood_pressure TEXT,
                pulse TEXT,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','resolved')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
    conn.commit()
    conn.close()
