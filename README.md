# MediCare HMS — Flask + SQLite Edition

A Python/Flask port of the same Hospital Management System designed in the
Scrum report and originally built in PHP OOP. Same features, same look,
same SQLite database file — just a different backend, the same way the
SRMS project got a Flask port alongside its PHP version.

## Requirements
- Python 3.9+
- Flask (see `requirements.txt`)

No MySQL, no phpMyAdmin, no external services — the database is a single
SQLite file created automatically on first run.

## Running it

```bash
cd hms_flask
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in a browser. The database
(`data/hms.sqlite`) is created and seeded with demo accounts automatically
on first run.

To reset to a clean demo state, stop the server, delete
`data/hms.sqlite`, and start it again.

### Windows
```powershell
cd hms_flask
pip install -r requirements.txt
python app.py
```
(Use `py` instead of `python` if that's how Python is aliased on your system.)

## Demo accounts
All demo accounts use the password `password123`.

| Role            | Email                              |
|-----------------|-------------------------------------|
| Admin           | admin@medicare.zm                  |
| Doctor          | chanda.mwansa@medicare.zm           |
| Doctor          | bwalya.phiri@medicare.zm            |
| Nurse           | grace.tembo@medicare.zm             |
| Receptionist    | mercy.banda@medicare.zm             |
| Pharmacist      | joseph.lungu@medicare.zm            |
| Lab Technician  | patricia.mulenga@medicare.zm        |
| Patient         | john.zulu@medicare.zm               |

## Project structure
```
hms_flask/
├── app.py               Flask app: config, routes, view logic
├── db.py                SQLite connection handling, schema + seed data
├── auth.py              Session-based login, role-guard decorators
├── audit.py             Audit trail (PB-17)
├── patients.py          Patient registration/search (PB-01, PB-02)
├── appointments.py      Booking with double-booking prevention (PB-02, PB-03)
├── medical_records.py   Diagnoses, notes, nurse vitals (PB-04, PB-08)
├── medicines.py         Pharmacy inventory, reorder alerts (PB-07)
├── prescriptions.py     Issuing and dispensing medication (PB-05, PB-06)
├── wards.py             Bed admission/discharge (PB-09, PB-14)
├── lab.py               Lab test requests and results (PB-10)
├── billing.py           Itemised, auto-generated billing (PB-11)
├── user_accounts.py     Staff account management (PB-13)
├── templates/           Jinja2 templates (one per page, extending base.html)
├── static/css/          Stylesheet (identical to the PHP version)
└── data/                hms.sqlite lives here (created on first run)
```

## Backlog traceability
| Story | Feature | Where |
|-------|---------|-------|
| PB-01 | Register new patient | `patients.py`, `/patients` |
| PB-02 | Book appointment, no double-booking | `appointments.py: book()` |
| PB-03 | Doctor's daily schedule | `/dashboard`, `/appointments` |
| PB-04 | Diagnosis / consultation notes | `medical_records.py`, `/records` |
| PB-05 | Electronic prescriptions | `prescriptions.py: issue()` |
| PB-06 | Pharmacist dispensing | `prescriptions.py: dispense()`, `/pharmacy` |
| PB-07 | Low-stock reorder alert | `medicines.py: low_stock()` |
| PB-08 | Nurse vitals capture | `medical_records.py: record_vitals()`, `/vitals` |
| PB-09 | Ward / bed occupancy | `wards.py`, `/wards` |
| PB-10 | Lab requests & results | `lab.py`, `/lab` |
| PB-11 | Itemised billing | `billing.py` (auto-charges from consults, Rx, labs, bed-stay) |
| PB-12 | Patient self-service portal | `/my-records`, `/my-bills` |
| PB-13 | Role-based accounts | `auth.py: role_required()`, `/users` |
| PB-14 | Discharge & bed billing | `wards.py: discharge()` |
| PB-15 | Management reports | `/reports` |
| PB-17 | Audit log | `audit.py`, `/audit-log` |
| PB-18 | Nightly backup | SQLite is a single file — schedule a cron/cloud sync job |

## Notes on the port
- **Sessions**: uses a dedicated cookie name (`hms_flask_session`) so it
  can never collide with another Flask or PHP project's session data if
  you run several projects on `localhost` at once — the exact bug we
  hit and fixed in the PHP version.
- **Passwords**: hashed with Werkzeug's `generate_password_hash`
  (PBKDF2), the Python-world equivalent of PHP's `password_hash()`.
- **One Jinja2 gotcha worth knowing**: a bill's list of line items is
  exposed as `bill.line_items`, not `bill.items` — because Jinja2
  resolves `dict.items` to Python's built-in `.items()` *method*
  before it falls back to a dictionary key of the same name. If you
  ever add a new dict key for a template, avoid naming it `items`,
  `keys`, or `values`.
- **Debug mode**: `app.run(debug=True)` is fine for local development
  (and gives you auto-reload + readable tracebacks) but should be
  turned off (`debug=False`) before deploying anywhere public.
