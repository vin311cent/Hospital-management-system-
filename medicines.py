"""Pharmacy inventory operations (PB-07)."""
import audit
from auth import current_user
from db import get_db


def all_medicines():
    db = get_db()
    return db.execute("SELECT * FROM medicines ORDER BY name").fetchall()


def low_stock():
    db = get_db()
    return db.execute(
        "SELECT * FROM medicines WHERE stock_qty <= reorder_level ORDER BY name"
    ).fetchall()


def restock(medicine_id, quantity):
    if quantity <= 0:
        raise ValueError("Restock quantity must be positive.")
    db = get_db()
    cur = db.execute(
        "UPDATE medicines SET stock_qty = stock_qty + ? WHERE id = ?",
        (quantity, medicine_id),
    )
    db.commit()
    if cur.rowcount:
        user = current_user()
        audit.record(
            user["id"] if user else None,
            "update",
            "medicines",
            medicine_id,
            f"Restocked by {quantity}",
        )
    return cur.rowcount > 0


def create(name, stock_qty, reorder_level, unit_price):
    if not name.strip():
        raise ValueError("Medicine name is required.")
    if stock_qty < 0 or reorder_level < 0 or unit_price < 0:
        raise ValueError("Medicine stock, reorder level, and price cannot be negative.")
    db = get_db()
    cur = db.execute(
        "INSERT INTO medicines (name, stock_qty, reorder_level, unit_price) VALUES (?,?,?,?)",
        (name.strip(), stock_qty, reorder_level, unit_price),
    )
    db.commit()
    user = current_user()
    audit.record(
        user["id"] if user else None,
        "create",
        "medicines",
        cur.lastrowid,
        f"Added medicine '{name.strip()}'",
    )
    return cur.lastrowid