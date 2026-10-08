"""
auth.py — session-based authentication and role guards.

Uses its own namespaced session key and a dedicated session cookie name
(set in app.py) so this app's login session can never collide with a
different Flask/PHP project also running on localhost.
"""
import functools
from flask import session, redirect, url_for, request, flash, g
from werkzeug.security import check_password_hash

from db import get_db
import audit

SESSION_KEY = "hms_auth_user"
REQUIRED_FIELDS = {"id", "name", "email", "role"}


def attempt_login(email, password):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)
    ).fetchone()

    if user and check_password_hash(user["password_hash"], password):
        session[SESSION_KEY] = {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
        }
        audit.record(user["id"], "login", "users", user["id"], "Successful login")
        return True
    return False


def logout():
    if current_user():
        u = current_user()
        audit.record(u["id"], "logout", "users", u["id"], "User logged out")
    session.pop(SESSION_KEY, None)


def current_user():
    """Return the logged-in user's dict, or None if the session is absent
    or malformed (defensive against any unexpected session shape)."""
    data = session.get(SESSION_KEY)
    if not isinstance(data, dict) or not REQUIRED_FIELDS.issubset(data.keys()):
        return None
    return data


def current_role():
    u = current_user()
    return u["role"] if u else None


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        g.user = current_user()
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user():
                return redirect(url_for("login"))
            if current_role() not in roles:
                flash("You do not have access to that page.", "error")
                return redirect(url_for("dashboard"))
            g.user = current_user()
            return view(*args, **kwargs)
        return wrapped
    return decorator
