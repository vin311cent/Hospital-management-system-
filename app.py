"""
app.py — MediCare HMS, a Flask + SQLite port of the Hospital Management
System designed in the Scrum report. Mirrors the PHP OOP version feature
for feature.

Run with:
    python app.py
Then open http://127.0.0.1:5000
"""
import os
import secrets
import sqlite3
from datetime import date
from flask import Flask, abort, render_template, request, redirect, url_for, flash, g, session

import db as db_module
import auth
import audit
import patients as patients_mod
import appointments as appointments_mod
import medical_records as records_mod
import medicines as medicines_mod
import prescriptions as prescriptions_mod
import wards as wards_mod
import lab as lab_mod
import billing as billing_mod
import user_accounts
import notifications as notifications_mod
import triage as triage_mod

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("HMS_SECRET_KEY") or secrets.token_hex(32)
app.config["DATABASE"] = os.path.join(BASE_DIR, "data", "hms.sqlite")

# Dedicated session cookie name so this app's login session can never
# collide with another Flask/PHP project also running on localhost.
app.config["SESSION_COOKIE_NAME"] = "hms_flask_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("HMS_COOKIE_SECURE") == "1"

db_module.init_app(app)

APP_NAME = "MediCare HMS"


@app.context_processor
def inject_globals():
    user = auth.current_user()
    token = session.setdefault("_csrf_token", secrets.token_hex(32))
    return {
        "app_name": APP_NAME,
        "current_user": user,
        "current_role": user["role"] if user else None,
        "today": date.today().isoformat(),
        "csrf_token": token,
        "unread_notifications": notifications_mod.unread_count(user["id"]) if user else 0,
    }


@app.before_request
def protect_state_changes():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        token = session.get("_csrf_token")
        submitted = request.form.get("_csrf_token", "")
        if not token or not secrets.compare_digest(token, submitted):
            abort(400, description="Invalid or missing CSRF token.")


def money(amount):
    return f"K{amount:,.2f}"


app.jinja_env.filters["money"] = money


with app.app_context():
    db_module.init_db(app)


# ---------------------------------------------------------------
# Auth
# ---------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("dashboard") if auth.current_user() else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if auth.current_user():
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if auth.attempt_login(email, password):
            return redirect(url_for("dashboard"))
        error = "Incorrect email or password."
    return render_template("login.html", error=error, app_name=APP_NAME)


@app.route("/logout", methods=["POST"])
def logout():
    auth.logout()
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register_patient():
    if auth.current_user():
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        data = {
            "full_name": request.form.get("full_name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "password": request.form.get("password", ""),
            "dob": request.form.get("dob", ""),
            "gender": request.form.get("gender", ""),
            "phone": request.form.get("phone", "").strip(),
            "address": request.form.get("address", "").strip(),
            "next_of_kin_name": request.form.get("next_of_kin_name", "").strip(),
            "next_of_kin_phone": request.form.get("next_of_kin_phone", "").strip(),
        }
        if not data["full_name"] or not data["email"] or not data["phone"]:
            error = "Name, email, and phone are required."
        elif len(data["password"]) < 8:
            error = "Password must be at least 8 characters."
        else:
            try:
                patients_mod.register_account(data)
            except sqlite3.IntegrityError:
                error = "An account with that email already exists."
            else:
                flash("Registration complete. Please sign in.", "success")
                return redirect(url_for("login"))
    return render_template("register.html", error=error)


# ---------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------
@app.route("/dashboard")
@auth.login_required
def dashboard():
    db = db_module.get_db()
    role = g.user["role"]
    ctx = {}

    if role == "admin":
        ctx["total_patients"] = db.execute("SELECT COUNT(*) AS n FROM patients WHERE is_active=1").fetchone()["n"]
        ctx["today_appts"] = db.execute("SELECT COUNT(*) AS n FROM appointments WHERE appointment_date = date('now')").fetchone()["n"]
        ctx["occupied_beds"] = db.execute("SELECT COUNT(*) AS n FROM beds WHERE status='occupied'").fetchone()["n"]
        ctx["total_beds"] = db.execute("SELECT COUNT(*) AS n FROM beds").fetchone()["n"]
        ctx["low_stock"] = len(medicines_mod.low_stock())
        ctx["unpaid_total"] = sum(b["total"] for b in billing_mod.all_bills() if b["status"] == "unpaid")
        ctx["recent_logs"] = audit.recent(10)

    elif role == "doctor":
        ctx["today_appts"] = appointments_mod.for_doctor(g.user["id"], date.today().isoformat())

    elif role == "receptionist":
        ctx["today_appts"] = db.execute("SELECT COUNT(*) AS n FROM appointments WHERE appointment_date = date('now')").fetchone()["n"]

    elif role == "nurse":
        ctx["active_triage_count"] = len(triage_mod.active_queue())

    elif role == "pharmacist":
        ctx["pending"] = prescriptions_mod.pending_queue()
        ctx["low_stock"] = medicines_mod.low_stock()

    elif role == "lab_technician":
        ctx["pending"] = lab_mod.pending()

    elif role == "patient":
        patient = patients_mod.find_by_user_id(g.user["id"])
        ctx["patient"] = patient
        ctx["upcoming_count"] = 0
        if patient:
            appts = appointments_mod.for_patient(patient["id"])
            ctx["upcoming_count"] = len([a for a in appts if a["status"] == "scheduled"])

    return render_template("dashboard.html", **ctx)


# ---------------------------------------------------------------
# Patients (PB-01, PB-02, PB-16)
# ---------------------------------------------------------------
@app.route("/patients", methods=["GET", "POST"])
@auth.role_required("admin", "receptionist", "doctor", "nurse")
def patients_page():
    if request.method == "POST" and g.user["role"] not in ("admin", "receptionist"):
        abort(403)
    if request.method == "POST" and request.form.get("action") == "create":
        patients_mod.create({
            "full_name": request.form["full_name"].strip(),
            "dob": request.form.get("dob") or None,
            "gender": request.form.get("gender") or None,
            "phone": request.form["phone"].strip(),
            "address": request.form.get("address", "").strip(),
            "next_of_kin_name": request.form.get("next_of_kin_name", "").strip(),
            "next_of_kin_phone": request.form.get("next_of_kin_phone", "").strip(),
        })
        flash("Patient registered successfully.", "success")
        return redirect(url_for("patients_page"))

    term = request.args.get("q", "").strip()
    plist = patients_mod.search(term) if term else patients_mod.all_patients()
    return render_template("patients.html", patients=plist, term=term)


@app.route("/patients/<int:patient_id>/deactivate", methods=["POST"])
@auth.role_required("admin", "receptionist")
def deactivate_patient(patient_id):
    patients_mod.deactivate(patient_id)
    flash("Patient record deactivated.", "success")
    return redirect(url_for("patients_page"))


@app.route("/patients/<int:patient_id>")
@auth.role_required("admin", "receptionist", "doctor", "nurse", "pharmacist")
def patient_view(patient_id):
    patient = patients_mod.find(patient_id)
    if not patient:
        flash("Patient not found.", "error")
        return redirect(url_for("patients_page"))
    return render_template(
        "patient_view.html",
        patient=patient,
        records=records_mod.for_patient(patient_id),
        prescriptions=prescriptions_mod.for_patient(patient_id),
        labs=lab_mod.for_patient(patient_id),
        bills=billing_mod.for_patient(patient_id),
        triage=triage_mod.for_patient(patient_id),
    )


@app.route("/profile", methods=["GET", "POST"])
@auth.role_required("patient")
def patient_profile():
    patient = patients_mod.find_by_user_id(g.user["id"])
    if not patient:
        abort(404, description="Patient profile not found.")
    if request.method == "POST":
        data = {
            "full_name": request.form.get("full_name", "").strip(),
            "dob": request.form.get("dob", "").strip(),
            "gender": request.form.get("gender", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "address": request.form.get("address", "").strip(),
            "next_of_kin_name": request.form.get("next_of_kin_name", "").strip(),
            "next_of_kin_phone": request.form.get("next_of_kin_phone", "").strip(),
        }
        if not data["full_name"] or not data["phone"]:
            flash("Name and phone are required.", "error")
        else:
            patients_mod.update_own_profile(g.user["id"], data)
            flash("Profile updated.", "success")
            return redirect(url_for("patient_profile"))
    return render_template("profile.html", patient=patient)


# ---------------------------------------------------------------
# Appointments (PB-02, PB-03)
# ---------------------------------------------------------------
@app.route("/appointments", methods=["GET", "POST"])
@auth.role_required("admin", "receptionist", "doctor", "patient")
def appointments_page():
    role = g.user["role"]
    my_patient = patients_mod.find_by_user_id(g.user["id"]) if role == "patient" else None

    if request.method == "POST" and request.form.get("action") == "book":
        if role == "patient" and not my_patient:
            flash("Complete your patient profile before booking.", "error")
            return redirect(url_for("appointments_page"))
        patient_id = (
            my_patient["id"] if role == "patient" and my_patient
            else request.form.get("patient_id", type=int)
        )
        doctor_id = request.form.get("doctor_id", type=int)
        if not patient_id or not doctor_id:
            flash("Select a patient and doctor.", "error")
            return redirect(url_for("appointments_page"))
        ok, message, appointment_id = appointments_mod.book(
            patient_id, doctor_id,
            request.form.get("appointment_date", ""), request.form.get("appointment_time", ""),
            request.form.get("reason", "").strip(),
        )
        if ok:
            appointment = appointments_mod.get(appointment_id)
            if appointment:
                message_text = (
                    f"Appointment booked for {appointment['appointment_date']} "
                    f"at {appointment['appointment_time']} with {appointment['doctor_name']}."
                )
                if appointment["patient_user_id"]:
                    notifications_mod.send(appointment["patient_user_id"], "Appointment booked", message_text)
                notifications_mod.send(appointment["doctor_user_id"], "Appointment booked", message_text)
        flash(message, "success" if ok else "error")
        return redirect(url_for("appointments_page"))

    doctors = user_accounts.doctors()
    plist = patients_mod.all_patients() if role in ("admin", "receptionist", "doctor") else []

    if role == "doctor":
        appts = appointments_mod.for_doctor(g.user["id"])
    elif role == "patient":
        appts = appointments_mod.for_patient(my_patient["id"]) if my_patient else []
    else:
        appts = appointments_mod.all_appointments()

    return render_template("appointments.html", doctors=doctors, patients=plist, appointments=appts, role=role)


@app.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@auth.role_required("admin", "receptionist", "doctor", "patient")
def cancel_appointment(appointment_id):
    appointment = appointments_mod.get(appointment_id)
    if not appointment:
        abort(404)
    role = g.user["role"]
    if role == "patient" and appointment["patient_user_id"] != g.user["id"]:
        abort(403)
    if role == "doctor" and appointment["doctor_user_id"] != g.user["id"]:
        abort(403)
    if appointments_mod.cancel(appointment_id):
        message = f"Appointment #{appointment_id} has been cancelled."
        if appointment["patient_user_id"]:
            notifications_mod.send(appointment["patient_user_id"], "Appointment cancelled", message)
        notifications_mod.send(appointment["doctor_user_id"], "Appointment cancelled", message)
        flash("Appointment cancelled.", "success")
    else:
        flash("Only scheduled appointments can be cancelled.", "error")
    return redirect(url_for("appointments_page"))


@app.route("/appointments/<int:appointment_id>/reschedule", methods=["POST"])
@auth.role_required("admin", "receptionist", "doctor", "patient")
def reschedule_appointment(appointment_id):
    appointment = appointments_mod.get(appointment_id)
    if not appointment:
        abort(404)
    role = g.user["role"]
    if role == "patient" and appointment["patient_user_id"] != g.user["id"]:
        abort(403)
    if role == "doctor" and appointment["doctor_user_id"] != g.user["id"]:
        abort(403)
    ok, message = appointments_mod.reschedule(
        appointment_id, request.form.get("appointment_date", ""),
        request.form.get("appointment_time", ""),
    )
    if ok:
        message_text = (
            f"Appointment #{appointment_id} was rescheduled to "
            f"{request.form['appointment_date']} at {request.form['appointment_time']}."
        )
        if appointment["patient_user_id"]:
            notifications_mod.send(appointment["patient_user_id"], "Appointment rescheduled", message_text)
        notifications_mod.send(appointment["doctor_user_id"], "Appointment rescheduled", message_text)
    flash(message, "success" if ok else "error")
    return redirect(url_for("appointments_page"))


@app.route("/appointments/<int:appointment_id>/complete", methods=["POST"])
@auth.role_required("doctor")
def complete_appointment(appointment_id):
    appointment = appointments_mod.get(appointment_id)
    if not appointment:
        abort(404)
    if appointment["doctor_user_id"] != g.user["id"]:
        abort(403)
    if not appointments_mod.complete(appointment_id):
        flash("Only scheduled appointments can be completed.", "error")
        return redirect(url_for("appointments_page"))
    if appointment["patient_user_id"]:
        notifications_mod.send(
            appointment["patient_user_id"], "Appointment completed",
            f"Your appointment #{appointment_id} has been marked completed.",
        )
    flash("Appointment marked as completed.", "success")
    return redirect(url_for("appointments_page"))


# ---------------------------------------------------------------
# Medical records + prescribing (PB-04, PB-05)
# ---------------------------------------------------------------
@app.route("/records", methods=["GET", "POST"])
@auth.role_required("doctor")
def records_page():
    doctor_id = g.user["id"]

    if request.method == "POST":
        action = request.form.get("action")
        patient_id = int(request.form["patient_id"])

        if action == "add_record":
            records_mod.create(patient_id, doctor_id, None, {
                "diagnosis": request.form["diagnosis"].strip(),
                "notes": request.form.get("notes", "").strip(),
                "temperature": request.form.get("temperature", "").strip(),
                "blood_pressure": request.form.get("blood_pressure", "").strip(),
                "pulse": request.form.get("pulse", "").strip(),
            })
            billing_mod.add_consultation_fee(patient_id)
            flash("Medical record saved and consultation fee billed.", "success")

        elif action == "prescribe":
            mr_id = request.form.get("medical_record_id") or None
            prescriptions_mod.issue(
                patient_id, doctor_id, int(mr_id) if mr_id else None,
                int(request.form["medicine_id"]), request.form["dosage"].strip(),
                request.form["frequency"].strip(), request.form["duration"].strip(),
                max(1, int(request.form["quantity"])),
            )
            flash("Prescription issued and sent to the pharmacy queue.", "success")

        return redirect(url_for("records_page", patient_id=patient_id))

    patient_id = request.args.get("patient_id", type=int)
    patient = patients_mod.find(patient_id) if patient_id else None
    records = records_mod.for_patient(patient_id) if patient_id else []

    return render_template(
        "records.html",
        patients=patients_mod.all_patients(), patient=patient, patient_id=patient_id,
        records=records, medicines=medicines_mod.all_medicines(),
    )


# ---------------------------------------------------------------
# Nurse vitals (PB-08)
# ---------------------------------------------------------------
@app.route("/vitals", methods=["GET", "POST"])
@auth.role_required("nurse")
def vitals_page():
    if request.method == "POST":
        records_mod.record_vitals(int(request.form["patient_id"]), {
            "temperature": request.form.get("temperature", "").strip(),
            "blood_pressure": request.form.get("blood_pressure", "").strip(),
            "pulse": request.form.get("pulse", "").strip(),
            "notes": request.form.get("notes", "").strip(),
        })
        flash("Vitals recorded and added to the patient's chart.", "success")
        return redirect(url_for("vitals_page"))

    return render_template(
        "vitals.html", patients=patients_mod.all_patients(), recent=records_mod.recent_vitals(15)
    )


@app.route("/triage", methods=["GET", "POST"])
@auth.role_required("nurse")
def triage_page():
    if request.method == "POST":
        action = request.form.get("action", "record")
        if action == "resolve":
            if not triage_mod.resolve(request.form.get("triage_id", type=int)):
                flash("Triage entry not found or already resolved.", "error")
            else:
                flash("Triage entry resolved.", "success")
        else:
            patient_id = request.form.get("patient_id", type=int)
            priority = request.form.get("priority", "")
            assessment = request.form.get("assessment", "").strip()
            patient = patients_mod.find(patient_id) if patient_id else None
            if not patient or not patient["is_active"] or not assessment:
                flash("Select a patient and enter an assessment.", "error")
            else:
                try:
                    triage_mod.record(
                        patient_id, g.user["id"], priority, assessment,
                        request.form.get("temperature", "").strip() or None,
                        request.form.get("blood_pressure", "").strip() or None,
                        request.form.get("pulse", "").strip() or None,
                    )
                except ValueError as exc:
                    flash(str(exc), "error")
                else:
                    flash("Triage assessment recorded.", "success")
        return redirect(url_for("triage_page"))
    return render_template(
        "triage.html", patients=patients_mod.all_patients(),
        triage_queue=triage_mod.active_queue(), priorities=triage_mod.PRIORITIES,
    )


@app.route("/notifications", methods=["GET", "POST"])
@auth.login_required
def notifications_page():
    if request.method == "POST":
        if g.user["role"] != "admin":
            abort(403)
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        if not title or not message:
            flash("Enter both a title and message for the announcement.", "error")
        else:
            count = notifications_mod.broadcast(title, message)
            flash(f"Announcement sent to {count} active users.", "success")
        return redirect(url_for("notifications_page"))
    return render_template(
        "notifications.html", notifications=notifications_mod.for_user(g.user["id"])
    )


@app.route("/notifications/<int:notification_id>/read", methods=["POST"])
@auth.login_required
def mark_notification_read(notification_id):
    notifications_mod.mark_read(notification_id, g.user["id"])
    return redirect(url_for("notifications_page"))


# ---------------------------------------------------------------
# Lab requests (PB-10)
# ---------------------------------------------------------------
@app.route("/lab", methods=["GET", "POST"])
@auth.role_required("doctor", "lab_technician")
def lab_page():
    role = g.user["role"]

    if request.method == "POST":
        action = request.form.get("action")
        if action == "request" and role == "doctor":
            lab_mod.request_test(int(request.form["patient_id"]), g.user["id"], request.form["test_name"].strip())
            patient = patients_mod.find(int(request.form["patient_id"]))
            if patient and patient["user_id"]:
                notifications_mod.send(
                    patient["user_id"], "Lab test requested",
                    f"A lab test ({request.form['test_name'].strip()}) has been requested for you.",
                )
            flash("Lab test requested and billed to the patient.", "success")
        elif action == "complete" and role == "lab_technician":
            request_id = request.form.get("request_id", type=int)
            lab_request = lab_mod.find(request_id) if request_id else None
            if not lab_request or not lab_mod.complete(request_id, request.form.get("result", "").strip()):
                flash("Lab request not found or already completed.", "error")
            else:
                result_message = f"Results are available for lab request #{request_id}."
                notifications_mod.send(lab_request["doctor_id"], "Lab result available", result_message)
                if lab_request["patient_user_id"]:
                    notifications_mod.send(lab_request["patient_user_id"], "Lab result available", result_message)
                flash("Result uploaded — the requesting doctor can now view it.", "success")
        return redirect(url_for("lab_page"))

    return render_template(
        "lab.html", patients=patients_mod.all_patients(), pending=lab_mod.pending(),
        results=lab_mod.for_doctor(g.user["id"]) if role == "doctor" else [], role=role
    )


# ---------------------------------------------------------------
# Pharmacy (PB-06, PB-07)
# ---------------------------------------------------------------
@app.route("/pharmacy", methods=["GET", "POST"])
@auth.role_required("admin", "pharmacist")
def pharmacy_page():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "dispense":
            ok, message = prescriptions_mod.dispense(int(request.form["prescription_id"]))
            flash(message, "success" if ok else "error")
        elif action == "restock":
            medicines_mod.restock(int(request.form["medicine_id"]), max(1, int(request.form["quantity"])))
            flash("Stock updated.", "success")
        elif action == "add_medicine":
            medicines_mod.create(
                request.form["name"].strip(), int(request.form["stock_qty"]),
                int(request.form["reorder_level"]), float(request.form["unit_price"]),
            )
            flash("Medicine added to inventory.", "success")
        return redirect(url_for("pharmacy_page"))

    return render_template(
        "pharmacy.html",
        pending=prescriptions_mod.pending_queue(),
        medicines=medicines_mod.all_medicines(),
        low_stock=medicines_mod.low_stock(),
    )


# ---------------------------------------------------------------
# Wards & beds (PB-09, PB-14)
# ---------------------------------------------------------------
@app.route("/wards", methods=["GET", "POST"])
@auth.role_required("admin", "nurse", "receptionist")
def wards_page():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "admit":
            ok, message = wards_mod.admit(int(request.form["bed_id"]), int(request.form["patient_id"]))
            flash(message, "success" if ok else "error")
        elif action == "discharge":
            ok, message = wards_mod.discharge(int(request.form["bed_id"]))
            flash(message, "success" if ok else "error")
        return redirect(url_for("wards_page"))

    beds = wards_mod.beds_with_occupant()
    occupied = len([b for b in beds if b["status"] == "occupied"])
    return render_template("wards.html", beds=beds, occupied=occupied, patients=patients_mod.all_patients())


# ---------------------------------------------------------------
# Billing (PB-11)
# ---------------------------------------------------------------
@app.route("/billing")
@auth.role_required("admin", "receptionist")
def billing_page():
    bills = billing_mod.all_bills()
    total_unpaid = sum(b["total"] for b in bills if b["status"] == "unpaid")
    return render_template("billing.html", bills=bills, total_unpaid=total_unpaid)


@app.route("/billing/<int:bill_id>/mark-paid", methods=["POST"])
@auth.role_required("admin", "receptionist")
def mark_bill_paid(bill_id):
    billing_mod.mark_paid(bill_id)
    flash("Bill marked as paid.", "success")
    return redirect(url_for("billing_page"))


# ---------------------------------------------------------------
# Patient self-service (PB-12)
# ---------------------------------------------------------------
@app.route("/my-records")
@auth.role_required("patient")
def my_records():
    patient = patients_mod.find_by_user_id(g.user["id"])
    if not patient:
        return render_template("my_records.html", patient=None)
    return render_template(
        "my_records.html", patient=patient,
        records=records_mod.for_patient(patient["id"]),
        prescriptions=prescriptions_mod.for_patient(patient["id"]),
        labs=lab_mod.for_patient(patient["id"]),
        triage=triage_mod.for_patient(patient["id"]),
    )


@app.route("/my-bills")
@auth.role_required("patient")
def my_bills():
    patient = patients_mod.find_by_user_id(g.user["id"])
    if not patient:
        return render_template("my_bills.html", patient=None, bills=[], total_owed=0)
    bills = billing_mod.for_patient(patient["id"])
    total_owed = sum(b["total"] for b in bills if b["status"] == "unpaid")
    return render_template("my_bills.html", patient=patient, bills=bills, total_owed=total_owed)


# ---------------------------------------------------------------
# Admin: staff accounts, reports, audit log (PB-13, PB-15, PB-17)
# ---------------------------------------------------------------
@app.route("/users", methods=["GET", "POST"])
@auth.role_required("admin")
def users_page():
    if request.method == "POST" and request.form.get("action") == "create":
        ok, message = user_accounts.create(
            request.form["name"].strip(), request.form["email"].strip(), request.form["password"],
            request.form["role"], request.form.get("specialty", "").strip() or None,
            request.form.get("phone", "").strip() or None,
        )
        flash(message, "success" if ok else "error")
        return redirect(url_for("users_page"))

    return render_template("users.html", users=user_accounts.all_accounts())


@app.route("/users/<int:user_id>/deactivate", methods=["POST"])
@auth.role_required("admin")
def deactivate_user(user_id):
    if user_id == g.user["id"]:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("users_page"))
    user_accounts.set_active(user_id, False)
    flash("Account deactivated.", "success")
    return redirect(url_for("users_page"))


@app.route("/users/<int:user_id>/activate", methods=["POST"])
@auth.role_required("admin")
def activate_user(user_id):
    user_accounts.set_active(user_id, True)
    flash("Account reactivated.", "success")
    return redirect(url_for("users_page"))


@app.route("/reports")
@auth.role_required("admin")
def reports_page():
    db = db_module.get_db()
    admissions_30 = db.execute("SELECT COUNT(*) AS n FROM beds WHERE admitted_at >= datetime('now','-30 days')").fetchone()["n"]
    total_beds = db.execute("SELECT COUNT(*) AS n FROM beds").fetchone()["n"]
    occupied_beds = db.execute("SELECT COUNT(*) AS n FROM beds WHERE status='occupied'").fetchone()["n"]
    occupancy_rate = round((occupied_beds / total_beds) * 100) if total_beds else 0

    revenue = db.execute(
        "SELECT COALESCE(SUM(bi.amount),0) AS s FROM bill_items bi JOIN bills b ON b.id=bi.bill_id WHERE b.status='paid'"
    ).fetchone()["s"]
    outstanding = db.execute(
        "SELECT COALESCE(SUM(bi.amount),0) AS s FROM bill_items bi JOIN bills b ON b.id=bi.bill_id WHERE b.status='unpaid'"
    ).fetchone()["s"]

    by_doctor = db.execute(
        """SELECT u.name, COUNT(a.id) AS appt_count FROM users u
           LEFT JOIN appointments a ON a.doctor_id = u.id
           WHERE u.role='doctor' GROUP BY u.id ORDER BY appt_count DESC"""
    ).fetchall()
    by_ward = db.execute(
        """SELECT w.name, COUNT(b.id) AS total, SUM(CASE WHEN b.status='occupied' THEN 1 ELSE 0 END) AS occupied
           FROM wards w LEFT JOIN beds b ON b.ward_id = w.id GROUP BY w.id"""
    ).fetchall()

    return render_template(
        "reports.html", admissions_30=admissions_30, occupancy_rate=occupancy_rate,
        revenue=revenue, outstanding=outstanding, by_doctor=by_doctor, by_ward=by_ward,
    )


@app.route("/audit-log")
@auth.role_required("admin")
def audit_log_page():
    return render_template("audit_log.html", logs=audit.recent(200))


if __name__ == "__main__":
    app.run(debug=os.environ.get("HMS_DEBUG") == "1", host="127.0.0.1", port=5000)
