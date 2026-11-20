from __future__ import annotations

import io
import os
import sqlite3
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import db as database
from auth import current_user, login_required, role_required
import reports

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "smartstock.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SMARTSTOCK_SECRET", "rsr-smartstock-enterprise-security-key-2026")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)  # 30 days persistent session for Remember Me

# Register database connection teardown
app.teardown_appcontext(database.close_db)


def get_db() -> sqlite3.Connection:
    return database.get_db()


def read_positive_int(value: str | None, field_name: str) -> int:
    try:
        number = int(value or "")
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid whole number for {field_name}.")
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return number


def read_positive_float(value: str | None, field_name: str, allow_zero: bool = True) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid decimal number for {field_name}.")
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    if not allow_zero and number == 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return number


def next_reference(prefix: str, db: sqlite3.Connection) -> str:
    date_part = datetime.now().strftime("%Y%m%d")
    pattern = f"{prefix}-{date_part}-%"
    count = db.execute(
        "SELECT COUNT(*) FROM movements WHERE ref_no LIKE ?", (pattern,)
    ).fetchone()[0]
    return f"{prefix}-{date_part}-{count + 1:04d}"


def update_stock(db: sqlite3.Connection, product_id: int, warehouse_id: int, change: int) -> None:
    product = db.execute("SELECT id, name FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        raise ValueError("Selected product does not exist.")

    warehouse = db.execute("SELECT id, name FROM warehouses WHERE id = ?", (warehouse_id,)).fetchone()
    if not warehouse:
        raise ValueError("Selected warehouse does not exist.")

    current = db.execute(
        "SELECT quantity FROM stock WHERE product_id = ? AND warehouse_id = ?",
        (product_id, warehouse_id),
    ).fetchone()

    if current:
        new_quantity = current["quantity"] + change
        if new_quantity < 0:
            raise ValueError(
                f"Insufficient stock in '{warehouse['name']}' for '{product['name']}'. "
                f"Available: {current['quantity']}, Requested change: {change}"
            )
        db.execute(
            "UPDATE stock SET quantity = ? WHERE product_id = ? AND warehouse_id = ?",
            (new_quantity, product_id, warehouse_id),
        )
    else:
        if change < 0:
            raise ValueError(f"No stock is available in '{warehouse['name']}' for '{product['name']}'.")
        db.execute(
            "INSERT INTO stock (product_id, warehouse_id, quantity) VALUES (?, ?, ?)",
            (product_id, warehouse_id, change),
        )


def get_warehouses(active_only: bool = True) -> list[sqlite3.Row]:
    with get_db() as db:
        if active_only:
            return db.execute("SELECT * FROM warehouses WHERE is_active = 1 ORDER BY name").fetchall()
        return db.execute("SELECT * FROM warehouses ORDER BY name").fetchall()


def get_products(active_only: bool = True) -> list[sqlite3.Row]:
    with get_db() as db:
        if active_only:
            return db.execute(
                """SELECT p.*, c.name AS category_name
                   FROM products p LEFT JOIN categories c ON c.id = p.category_id
                   WHERE p.is_active = 1 ORDER BY p.name"""
            ).fetchall()
        return db.execute(
            """SELECT p.*, c.name AS category_name
               FROM products p LEFT JOIN categories c ON c.id = p.category_id
               ORDER BY p.name"""
        ).fetchall()


def get_categories() -> list[sqlite3.Row]:
    with get_db() as db:
        return db.execute("SELECT * FROM categories ORDER BY name").fetchall()


def get_suppliers() -> list[sqlite3.Row]:
    with get_db() as db:
        return db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()


def get_customers() -> list[sqlite3.Row]:
    with get_db() as db:
        return db.execute("SELECT * FROM customers ORDER BY name").fetchall()


def inventory_rows(category_id: int | None = None, search: str = "") -> list[dict[str, Any]]:
    with get_db() as db:
        query = """
            SELECT p.*, c.name AS category_name, COALESCE(SUM(s.quantity), 0) AS total_stock
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            LEFT JOIN stock s ON s.product_id = p.id
            WHERE p.is_active = 1
        """
        params: list[Any] = []
        if category_id:
            query += " AND p.category_id = ?"
            params.append(category_id)
        if search:
            query += " AND (lower(p.name) LIKE ? OR lower(p.sku) LIKE ? OR lower(p.barcode) LIKE ?)"
            term = f"%{search.lower()}%"
            params.extend([term, term, term])

        query += " GROUP BY p.id ORDER BY p.name"
        products = db.execute(query, params).fetchall()
        warehouses = db.execute("SELECT * FROM warehouses WHERE is_active = 1 ORDER BY name").fetchall()

        rows: list[dict[str, Any]] = []
        for product in products:
            levels = db.execute(
                """SELECT w.id, w.name, COALESCE(s.quantity, 0) AS quantity
                   FROM warehouses w LEFT JOIN stock s
                   ON s.warehouse_id = w.id AND s.product_id = ?
                   WHERE w.is_active = 1 ORDER BY w.name""",
                (product["id"],),
            ).fetchall()

            item = dict(product)
            item["levels"] = [dict(level) for level in levels]
            total_stock = item["total_stock"]
            reorder_level = item["reorder_level"]
            cost = item["cost_price"] or 0.0
            retail = item["selling_price"] or 0.0

            item["cost_valuation"] = total_stock * cost
            item["retail_valuation"] = total_stock * retail
            item["potential_profit"] = item["retail_valuation"] - item["cost_valuation"]

            if total_stock == 0:
                item["status"] = "Out of stock"
                item["status_class"] = "status-out"
            elif total_stock <= reorder_level:
                item["status"] = "Low stock"
                item["status_class"] = "status-low"
            else:
                item["status"] = "In stock"
                item["status_class"] = "status-good"

            rows.append(item)
        return rows


# -------------------------------------------------------------
# Context Processors (Injected into every Jinja2 template)
# -------------------------------------------------------------
@app.context_processor
def inject_globals():
    user = current_user()
    settings = database.get_all_settings()
    return {
        "current_user": user,
        "current_year": datetime.now().year,
        "currency_symbol": settings.get("currency_symbol", "₹"),
        "company_name": settings.get("company_name", "RSR SmartStock"),
        "company_tagline": settings.get("company_tagline", "Inventory Clarity. Warehouse Control."),
        "company_address": settings.get("company_address", "Industrial Tech Park, Bengaluru"),
        "tax_number": settings.get("tax_number", "GSTIN29AAACR1234F1Z5"),
    }


# -------------------------------------------------------------
# Authentication Routes
# -------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Enter both username and password.", "error")
            return render_template("login.html", username=username)

        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()
            if not user or not check_password_hash(user["password_hash"], password):
                flash("Invalid username or password.", "error")
                return render_template("login.html", username=username)

            if not user["is_active"]:
                flash("Your account is deactivated. Contact an administrator.", "error")
                return render_template("login.html", username=username)

            # Valid credentials
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]

            remember = request.form.get("remember")
            session.permanent = bool(remember)

            # Update last_login
            db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
            db.commit()

            database.log_activity(
                user["id"], user["username"], "LOGIN", "AUTH",
                f"User logged in from {request.remote_addr}", request.remote_addr
            )

            flash(f"Welcome back, {user['full_name']}! You are signed in as {user['role'].upper()}.", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    user = current_user()
    if user:
        database.log_activity(
            user["id"], user["username"], "LOGOUT", "AUTH",
            "User logged out", request.remote_addr
        )
    session.clear()
    flash("You have been signed out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        old_password = request.form.get("old_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        with get_db() as db:
            db_user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
            if not full_name:
                flash("Full name cannot be blank.", "error")
                return redirect(url_for("profile"))

            db.execute("UPDATE users SET full_name = ?, email = ? WHERE id = ?", (full_name, email, user["id"]))

            if new_password:
                if not old_password or not check_password_hash(db_user["password_hash"], old_password):
                    flash("Current password is incorrect.", "error")
                    return redirect(url_for("profile"))
                if len(new_password) < 6:
                    flash("New password must be at least 6 characters.", "error")
                    return redirect(url_for("profile"))
                if new_password != confirm_password:
                    flash("New password and confirmation do not match.", "error")
                    return redirect(url_for("profile"))

                new_hash = generate_password_hash(new_password)
                db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
                flash("Password updated successfully.", "success")

            db.commit()
            session["full_name"] = full_name
            database.log_activity(user["id"], user["username"], "UPDATE_PROFILE", "USER", "User updated profile info")
            flash("Profile details updated successfully.", "success")
            return redirect(url_for("profile"))

    return render_template("profile.html")


# -------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    with get_db() as db:
        stats_row = db.execute(
            """SELECT
                COUNT(DISTINCT p.id) AS sku_count,
                COALESCE(SUM(s.quantity), 0) AS total_units,
                COALESCE(SUM(s.quantity * p.cost_price), 0.0) AS total_cost_value,
                COALESCE(SUM(s.quantity * p.selling_price), 0.0) AS total_retail_value,
                (SELECT COUNT(*) FROM movements WHERE date(created_at) = date('now', 'localtime')) AS today_moves,
                (SELECT COUNT(*) FROM (
                    SELECT p2.id FROM products p2
                    LEFT JOIN stock s2 ON s2.product_id = p2.id
                    WHERE p2.is_active = 1
                    GROUP BY p2.id HAVING COALESCE(SUM(s2.quantity), 0) <= p2.reorder_level
                )) AS low_stock_count,
                (SELECT COUNT(*) FROM (
                    SELECT p3.id FROM products p3
                    LEFT JOIN stock s3 ON s3.product_id = p3.id
                    WHERE p3.is_active = 1
                    GROUP BY p3.id HAVING COALESCE(SUM(s3.quantity), 0) = 0
                )) AS out_of_stock_count
               FROM products p
               LEFT JOIN stock s ON s.product_id = p.id
               WHERE p.is_active = 1"""
        ).fetchone()

        stats = {
            "sku_count": (stats_row["sku_count"] or 0) if stats_row else 0,
            "total_units": (stats_row["total_units"] or 0) if stats_row else 0,
            "total_cost_value": (stats_row["total_cost_value"] or 0.0) if stats_row else 0.0,
            "total_retail_value": (stats_row["total_retail_value"] or 0.0) if stats_row else 0.0,
            "today_moves": (stats_row["today_moves"] or 0) if stats_row else 0,
            "low_stock_count": (stats_row["low_stock_count"] or 0) if stats_row else 0,
            "out_of_stock_count": (stats_row["out_of_stock_count"] or 0) if stats_row else 0,
        }

        low_stock = db.execute(
            """SELECT p.id, p.sku, p.name, p.reorder_level, p.unit,
                      c.name AS category_name, COALESCE(SUM(s.quantity), 0) AS total_stock
               FROM products p
               LEFT JOIN categories c ON c.id = p.category_id
               LEFT JOIN stock s ON s.product_id = p.id
               WHERE p.is_active = 1
               GROUP BY p.id HAVING total_stock <= p.reorder_level
               ORDER BY total_stock ASC LIMIT 6"""
        ).fetchall()

        recent = db.execute(
            """SELECT m.*, p.name AS product_name, p.sku,
                      fw.name AS from_name, tw.name AS to_name,
                      u.username AS recorded_by
               FROM movements m
               JOIN products p ON p.id = m.product_id
               LEFT JOIN warehouses fw ON fw.id = m.from_warehouse_id
               LEFT JOIN warehouses tw ON tw.id = m.to_warehouse_id
               LEFT JOIN users u ON u.id = m.user_id
               ORDER BY m.id DESC LIMIT 8"""
        ).fetchall()

        warehouse_totals = db.execute(
            """SELECT w.id, w.name, w.code, w.capacity,
                      COALESCE(SUM(s.quantity), 0) AS units,
                      COUNT(DISTINCT CASE WHEN s.quantity > 0 THEN s.product_id END) AS active_skus
               FROM warehouses w
               LEFT JOIN stock s ON s.warehouse_id = w.id
               WHERE w.is_active = 1
               GROUP BY w.id ORDER BY w.name"""
        ).fetchall()

        category_distribution = db.execute(
            """SELECT COALESCE(c.name, 'General') AS cat_name,
                      COUNT(p.id) AS sku_count,
                      COALESCE(SUM(s.quantity), 0) AS total_qty
               FROM products p
               LEFT JOIN categories c ON c.id = p.category_id
               LEFT JOIN stock s ON s.product_id = p.id
               WHERE p.is_active = 1
               GROUP BY cat_name ORDER BY total_qty DESC LIMIT 6"""
        ).fetchall()

    return render_template(
        "dashboard.html",
        stats=stats,
        low_stock=low_stock,
        recent=recent,
        warehouse_totals=warehouse_totals,
        category_distribution=category_distribution,
    )


# -------------------------------------------------------------
# Products & Inventory
# -------------------------------------------------------------
@app.route("/inventory", methods=["GET", "POST"])
@app.route("/products", methods=["GET", "POST"])
@login_required
def inventory():
    user = current_user()
    if request.method == "POST":
        if user["role"] not in ["admin", "manager"]:
            flash("Staff accounts cannot add new products. Contact a Manager.", "error")
            return redirect(url_for("inventory"))

        try:
            sku = request.form.get("sku", "").strip().upper()
            barcode = request.form.get("barcode", "").strip()
            name = request.form.get("name", "").strip()
            category_id = int(request.form.get("category_id") or 0) or None
            unit = request.form.get("unit", "pcs").strip() or "pcs"
            cost_price = read_positive_float(request.form.get("cost_price"), "cost price")
            selling_price = read_positive_float(request.form.get("selling_price"), "selling price")
            reorder_level = int(request.form.get("reorder_level", "10"))
            description = request.form.get("description", "").strip()
            opening_qty = int(request.form.get("opening_qty", "0"))
            warehouse_id = int(request.form.get("warehouse_id", "0"))

            if not sku or not name:
                raise ValueError("SKU and product name are mandatory.")
            if reorder_level < 0 or opening_qty < 0:
                raise ValueError("Reorder level and opening stock cannot be negative.")
            if not barcode:
                barcode = sku

            with get_db() as db:
                category_name = "General"
                if category_id:
                    cat_row = db.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
                    if cat_row:
                        category_name = cat_row["name"]

                cursor = db.execute(
                    """INSERT INTO products
                       (sku, barcode, name, category, category_id, unit, cost_price, selling_price, reorder_level, description)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sku, barcode, name, category_name, category_id, unit, cost_price, selling_price, reorder_level, description),
                )
                product_id = cursor.lastrowid

                if opening_qty > 0:
                    warehouse = db.execute("SELECT id FROM warehouses WHERE id = ?", (warehouse_id,)).fetchone()
                    if not warehouse:
                        raise ValueError("Select a valid warehouse for opening stock.")

                    update_stock(db, product_id, warehouse_id, opening_qty)
                    ref = next_reference("OPENING", db)
                    db.execute(
                        """INSERT INTO movements
                           (ref_no, movement_type, product_id, quantity, to_warehouse_id, unit_price, total_price, remarks, user_id)
                           VALUES (?, 'OPENING', ?, ?, ?, ?, ?, 'Opening stock recorded during product creation', ?)""",
                        (ref, product_id, opening_qty, warehouse_id, cost_price, opening_qty * cost_price, user["id"]),
                    )

                db.commit()

            database.log_activity(
                user["id"], user["username"], "ADD_PRODUCT", "PRODUCTS",
                f"Created product '{name}' (SKU: {sku}, Opening Qty: {opening_qty})"
            )
            flash(f"Product '{name}' added successfully.", "success")
        except sqlite3.IntegrityError:
            flash("A product with this SKU or Barcode already exists. Please use unique values.", "error")
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")

        return redirect(url_for("inventory"))

    cat_filter = request.args.get("category", type=int)
    search_query = request.args.get("q", "").strip()
    rows = inventory_rows(category_id=cat_filter, search=search_query)

    return render_template(
        "inventory.html",
        rows=rows,
        warehouses=get_warehouses(),
        categories=get_categories(),
        selected_category=cat_filter,
        search_query=search_query,
    )


@app.route("/products/<int:id>/edit", methods=["POST"])
@login_required
@role_required(["admin", "manager"])
def edit_product(id: int):
    user = current_user()
    try:
        name = request.form.get("name", "").strip()
        sku = request.form.get("sku", "").strip().upper()
        barcode = request.form.get("barcode", "").strip() or sku
        category_id = int(request.form.get("category_id") or 0) or None
        unit = request.form.get("unit", "pcs").strip()
        cost_price = read_positive_float(request.form.get("cost_price"), "cost price")
        selling_price = read_positive_float(request.form.get("selling_price"), "selling price")
        reorder_level = int(request.form.get("reorder_level", "10"))
        description = request.form.get("description", "").strip()

        if not name or not sku:
            raise ValueError("Product name and SKU cannot be blank.")

        with get_db() as db:
            cat_name = "General"
            if category_id:
                cat_row = db.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
                if cat_row:
                    cat_name = cat_row["name"]

            db.execute(
                """UPDATE products
                   SET name = ?, sku = ?, barcode = ?, category = ?, category_id = ?,
                       unit = ?, cost_price = ?, selling_price = ?, reorder_level = ?, description = ?
                   WHERE id = ?""",
                (name, sku, barcode, cat_name, category_id, unit, cost_price, selling_price, reorder_level, description, id),
            )
            db.commit()

        database.log_activity(user["id"], user["username"], "EDIT_PRODUCT", "PRODUCTS", f"Updated product #{id} ({name})")
        flash(f"Product '{name}' updated successfully.", "success")
    except sqlite3.IntegrityError:
        flash("SKU or Barcode conflict with another existing product.", "error")
    except Exception as e:
        flash(str(e), "error")

    return redirect(url_for("inventory"))


@app.route("/products/<int:id>/delete", methods=["POST"])
@login_required
@role_required(["admin"])
def delete_product(id: int):
    user = current_user()
    with get_db() as db:
        prod = db.execute("SELECT name, sku FROM products WHERE id = ?", (id,)).fetchone()
        if not prod:
            flash("Product not found.", "error")
            return redirect(url_for("inventory"))

        # Check total stock
        stock_sum = db.execute("SELECT COALESCE(SUM(quantity), 0) FROM stock WHERE product_id = ?", (id,)).fetchone()[0]
        if stock_sum > 0:
            flash(f"Cannot delete '{prod['name']}' because {stock_sum} units are still in stock across warehouses. Adjust stock to 0 first.", "error")
            return redirect(url_for("inventory"))

        # Soft delete by setting is_active = 0 to preserve movement history integrity
        db.execute("UPDATE products SET is_active = 0 WHERE id = ?", (id,))
        db.commit()

        database.log_activity(user["id"], user["username"], "DELETE_PRODUCT", "PRODUCTS", f"Deactivated product '{prod['name']}' ({prod['sku']})")
        flash(f"Product '{prod['name']}' was deactivated from catalogue.", "success")

    return redirect(url_for("inventory"))


# -------------------------------------------------------------
# Categories
# -------------------------------------------------------------
@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    user = current_user()
    if request.method == "POST":
        if user["role"] not in ["admin", "manager"]:
            flash("Staff accounts cannot add categories.", "error")
            return redirect(url_for("categories"))

        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()
        description = request.form.get("description", "").strip()

        if not name or not code:
            flash("Category name and code are required.", "error")
            return redirect(url_for("categories"))

        try:
            with get_db() as db:
                db.execute(
                    "INSERT INTO categories (name, code, description) VALUES (?, ?, ?)",
                    (name, code, description),
                )
                db.commit()
            database.log_activity(user["id"], user["username"], "ADD_CATEGORY", "CATEGORIES", f"Created category '{name}' ({code})")
            flash(f"Category '{name}' created successfully.", "success")
        except sqlite3.IntegrityError:
            flash("A category with this name or code already exists.", "error")

        return redirect(url_for("categories"))

    with get_db() as db:
        rows = db.execute(
            """SELECT c.*, COUNT(p.id) AS product_count,
                      COALESCE(SUM(s.quantity), 0) AS total_units
               FROM categories c
               LEFT JOIN products p ON p.category_id = c.id AND p.is_active = 1
               LEFT JOIN stock s ON s.product_id = p.id
               GROUP BY c.id ORDER BY c.name"""
        ).fetchall()

    return render_template("categories.html", categories=rows)


@app.route("/categories/<int:id>/edit", methods=["POST"])
@login_required
@role_required(["admin", "manager"])
def edit_category(id: int):
    user = current_user()
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    description = request.form.get("description", "").strip()

    try:
        with get_db() as db:
            db.execute("UPDATE categories SET name = ?, code = ?, description = ? WHERE id = ?", (name, code, description, id))
            # Also update string category column in products
            db.execute("UPDATE products SET category = ? WHERE category_id = ?", (name, id))
            db.commit()
        database.log_activity(user["id"], user["username"], "EDIT_CATEGORY", "CATEGORIES", f"Edited category #{id} ({name})")
        flash(f"Category '{name}' updated successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Name or Code already in use by another category.", "error")
    return redirect(url_for("categories"))


@app.route("/categories/<int:id>/delete", methods=["POST"])
@login_required
@role_required(["admin"])
def delete_category(id: int):
    user = current_user()
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM products WHERE category_id = ?", (id,)).fetchone()[0]
        if count > 0:
            flash(f"Cannot delete category: {count} product(s) are assigned to it. Reassign them first.", "error")
            return redirect(url_for("categories"))
        db.execute("DELETE FROM categories WHERE id = ?", (id,))
        db.commit()
    database.log_activity(user["id"], user["username"], "DELETE_CATEGORY", "CATEGORIES", f"Deleted category #{id}")
    flash("Category deleted successfully.", "success")
    return redirect(url_for("categories"))


# -------------------------------------------------------------
# Suppliers
# -------------------------------------------------------------
@app.route("/suppliers", methods=["GET", "POST"])
@login_required
def suppliers():
    user = current_user()
    if request.method == "POST":
        if user["role"] not in ["admin", "manager"]:
            flash("Staff accounts cannot add suppliers.", "error")
            return redirect(url_for("suppliers"))

        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()
        contact_person = request.form.get("contact_person", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not name or not code:
            flash("Supplier name and code are required.", "error")
            return redirect(url_for("suppliers"))

        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO suppliers (name, code, contact_person, email, phone, address)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (name, code, contact_person, email, phone, address),
                )
                db.commit()
            database.log_activity(user["id"], user["username"], "ADD_SUPPLIER", "SUPPLIERS", f"Added supplier '{name}' ({code})")
            flash(f"Supplier '{name}' registered successfully.", "success")
        except sqlite3.IntegrityError:
            flash("A supplier with this name or code already exists.", "error")
        return redirect(url_for("suppliers"))

    with get_db() as db:
        rows = db.execute(
            """SELECT s.*, COUNT(m.id) AS grn_count,
                      COALESCE(SUM(m.total_price), 0.0) AS total_purchased
               FROM suppliers s
               LEFT JOIN movements m ON m.supplier_id = s.id AND m.movement_type = 'GRN'
               GROUP BY s.id ORDER BY s.name"""
        ).fetchall()

    return render_template("suppliers.html", suppliers=rows)


@app.route("/suppliers/<int:id>/edit", methods=["POST"])
@login_required
@role_required(["admin", "manager"])
def edit_supplier(id: int):
    user = current_user()
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    contact_person = request.form.get("contact_person", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()

    try:
        with get_db() as db:
            db.execute(
                """UPDATE suppliers
                   SET name = ?, code = ?, contact_person = ?, email = ?, phone = ?, address = ?
                   WHERE id = ?""",
                (name, code, contact_person, email, phone, address, id),
            )
            db.commit()
        database.log_activity(user["id"], user["username"], "EDIT_SUPPLIER", "SUPPLIERS", f"Updated supplier #{id} ({name})")
        flash(f"Supplier '{name}' updated successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Supplier name or code already exists.", "error")
    return redirect(url_for("suppliers"))


@app.route("/suppliers/<int:id>/delete", methods=["POST"])
@login_required
@role_required(["admin"])
def delete_supplier(id: int):
    user = current_user()
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM movements WHERE supplier_id = ?", (id,)).fetchone()[0]
        if count > 0:
            flash(f"Cannot delete supplier: {count} historical goods receipt note(s) reference this supplier.", "error")
            return redirect(url_for("suppliers"))
        db.execute("DELETE FROM suppliers WHERE id = ?", (id,))
        db.commit()
    database.log_activity(user["id"], user["username"], "DELETE_SUPPLIER", "SUPPLIERS", f"Deleted supplier #{id}")
    flash("Supplier deleted successfully.", "success")
    return redirect(url_for("suppliers"))


# -------------------------------------------------------------
# Customers
# -------------------------------------------------------------
@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    user = current_user()
    if request.method == "POST":
        if user["role"] not in ["admin", "manager"]:
            flash("Staff accounts cannot add customers.", "error")
            return redirect(url_for("customers"))

        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()
        contact_person = request.form.get("contact_person", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not name or not code:
            flash("Customer name and code are required.", "error")
            return redirect(url_for("customers"))

        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO customers (name, code, contact_person, email, phone, address)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (name, code, contact_person, email, phone, address),
                )
                db.commit()
            database.log_activity(user["id"], user["username"], "ADD_CUSTOMER", "CUSTOMERS", f"Added customer '{name}' ({code})")
            flash(f"Customer '{name}' registered successfully.", "success")
        except sqlite3.IntegrityError:
            flash("A customer with this name or code already exists.", "error")
        return redirect(url_for("customers"))

    with get_db() as db:
        rows = db.execute(
            """SELECT c.*, COUNT(m.id) AS dispatch_count,
                      COALESCE(SUM(m.total_price), 0.0) AS total_dispatched
               FROM customers c
               LEFT JOIN movements m ON m.customer_id = c.id AND m.movement_type = 'DISPATCH'
               GROUP BY c.id ORDER BY c.name"""
        ).fetchall()

    return render_template("customers.html", customers=rows)


@app.route("/customers/<int:id>/edit", methods=["POST"])
@login_required
@role_required(["admin", "manager"])
def edit_customer(id: int):
    user = current_user()
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    contact_person = request.form.get("contact_person", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()

    try:
        with get_db() as db:
            db.execute(
                """UPDATE customers
                   SET name = ?, code = ?, contact_person = ?, email = ?, phone = ?, address = ?
                   WHERE id = ?""",
                (name, code, contact_person, email, phone, address, id),
            )
            db.commit()
        database.log_activity(user["id"], user["username"], "EDIT_CUSTOMER", "CUSTOMERS", f"Updated customer #{id} ({name})")
        flash(f"Customer '{name}' updated successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Customer name or code already exists.", "error")
    return redirect(url_for("customers"))


@app.route("/customers/<int:id>/delete", methods=["POST"])
@login_required
@role_required(["admin"])
def delete_customer(id: int):
    user = current_user()
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM movements WHERE customer_id = ?", (id,)).fetchone()[0]
        if count > 0:
            flash(f"Cannot delete customer: {count} dispatch record(s) reference this customer.", "error")
            return redirect(url_for("customers"))
        db.execute("DELETE FROM customers WHERE id = ?", (id,))
        db.commit()
    database.log_activity(user["id"], user["username"], "DELETE_CUSTOMER", "CUSTOMERS", f"Deleted customer #{id}")
    flash("Customer deleted successfully.", "success")
    return redirect(url_for("customers"))


# -------------------------------------------------------------
# Warehouses
# -------------------------------------------------------------
@app.route("/warehouses", methods=["GET", "POST"])
@login_required
def warehouses():
    user = current_user()
    if request.method == "POST":
        if user["role"] not in ["admin", "manager"]:
            flash("Staff accounts cannot add warehouses.", "error")
            return redirect(url_for("warehouses"))

        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()
        location = request.form.get("location", "").strip()
        capacity = int(request.form.get("capacity", "10000") or 10000)

        if not name:
            flash("Warehouse name is required.", "error")
            return redirect(url_for("warehouses"))
        if not code:
            code = f"WH-{len(get_warehouses(False)) + 1:02d}"

        try:
            with get_db() as db:
                db.execute(
                    "INSERT INTO warehouses (name, code, location, capacity) VALUES (?, ?, ?, ?)",
                    (name, code, location, capacity),
                )
                db.commit()
            database.log_activity(user["id"], user["username"], "ADD_WAREHOUSE", "WAREHOUSES", f"Created warehouse '{name}' ({code})")
            flash(f"Warehouse '{name}' added successfully.", "success")
        except sqlite3.IntegrityError:
            flash("A warehouse with this name already exists.", "error")

        return redirect(url_for("warehouses"))

    with get_db() as db:
        data = db.execute(
            """SELECT w.*, COALESCE(SUM(s.quantity), 0) AS total_units,
                      COUNT(DISTINCT CASE WHEN s.quantity > 0 THEN s.product_id END) AS active_skus
               FROM warehouses w
               LEFT JOIN stock s ON s.warehouse_id = w.id
               WHERE w.is_active = 1
               GROUP BY w.id ORDER BY w.name"""
        ).fetchall()

    return render_template("warehouses.html", warehouses=data)


@app.route("/warehouses/<int:id>/edit", methods=["POST"])
@login_required
@role_required(["admin", "manager"])
def edit_warehouse(id: int):
    user = current_user()
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    location = request.form.get("location", "").strip()
    capacity = int(request.form.get("capacity", "10000") or 10000)

    try:
        with get_db() as db:
            db.execute("UPDATE warehouses SET name = ?, code = ?, location = ?, capacity = ? WHERE id = ?", (name, code, location, capacity, id))
            db.commit()
        database.log_activity(user["id"], user["username"], "EDIT_WAREHOUSE", "WAREHOUSES", f"Updated warehouse #{id} ({name})")
        flash(f"Warehouse '{name}' updated successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Warehouse name already exists.", "error")
    return redirect(url_for("warehouses"))


@app.route("/warehouses/<int:id>/stock")
@login_required
def warehouse_stock_detail(id: int):
    with get_db() as db:
        warehouse = db.execute("SELECT * FROM warehouses WHERE id = ?", (id,)).fetchone()
        if not warehouse:
            flash("Warehouse not found.", "error")
            return redirect(url_for("warehouses"))

        stock_items = db.execute(
            """SELECT p.*, s.quantity, c.name AS category_name,
                      (s.quantity * p.cost_price) AS cost_valuation,
                      (s.quantity * p.selling_price) AS retail_valuation
               FROM stock s
               JOIN products p ON p.id = s.product_id
               LEFT JOIN categories c ON c.id = p.category_id
               WHERE s.warehouse_id = ? AND s.quantity > 0
               ORDER BY p.name""",
            (id,),
        ).fetchall()

    return render_template("warehouse_stock.html", warehouse=warehouse, items=stock_items)


# -------------------------------------------------------------
# Operations: GRN, Transfer, Dispatch
# -------------------------------------------------------------
@app.route("/grn", methods=["GET", "POST"])
@login_required
def grn():
    user = current_user()
    if request.method == "POST":
        try:
            product_id = read_positive_int(request.form.get("product_id"), "product")
            warehouse_id = read_positive_int(request.form.get("warehouse_id"), "destination warehouse")
            quantity = read_positive_int(request.form.get("quantity"), "quantity")
            supplier_id = int(request.form.get("supplier_id") or 0) or None
            unit_price = read_positive_float(request.form.get("unit_price"), "unit cost price")
            po_ref = request.form.get("po_ref", "").strip()
            remarks = request.form.get("remarks", "").strip()

            if po_ref:
                remarks = f"PO #{po_ref} | {remarks}".strip(" |")

            with get_db() as db:
                product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
                if not product:
                    raise ValueError("Select a valid product.")

                if unit_price == 0.0 and product["cost_price"]:
                    unit_price = product["cost_price"]

                total_cost = quantity * unit_price
                ref = next_reference("GRN", db)

                update_stock(db, product_id, warehouse_id, quantity)

                db.execute(
                    """INSERT INTO movements
                       (ref_no, movement_type, product_id, quantity, to_warehouse_id, supplier_id, unit_price, total_price, remarks, user_id)
                       VALUES (?, 'GRN', ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ref, product_id, quantity, warehouse_id, supplier_id, unit_price, total_cost, remarks, user["id"]),
                )
                db.commit()

            database.log_activity(
                user["id"], user["username"], "GRN_RECEIVED", "INVENTORY",
                f"Received {quantity} {product['unit']} of '{product['name']}'. Ref: {ref}"
            )
            flash(f"Goods received successfully. Reference: {ref} ({quantity} units added).", "success")
            return redirect(url_for("grn"))
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")

    return render_template(
        "operation.html",
        mode="grn",
        products=get_products(),
        warehouses=get_warehouses(),
        suppliers=get_suppliers(),
    )


@app.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    user = current_user()
    if request.method == "POST":
        try:
            product_id = read_positive_int(request.form.get("product_id"), "product")
            from_id = read_positive_int(request.form.get("from_warehouse_id"), "source warehouse")
            to_id = read_positive_int(request.form.get("to_warehouse_id"), "destination warehouse")
            quantity = read_positive_int(request.form.get("quantity"), "quantity")
            remarks = request.form.get("remarks", "").strip()

            if from_id == to_id:
                raise ValueError("Source and destination warehouses must be different.")

            with get_db() as db:
                product = db.execute("SELECT name, unit, cost_price FROM products WHERE id = ?", (product_id,)).fetchone()
                if not product:
                    raise ValueError("Select a valid product.")

                ref = next_reference("TRF", db)
                update_stock(db, product_id, from_id, -quantity)
                update_stock(db, product_id, to_id, quantity)

                db.execute(
                    """INSERT INTO movements
                       (ref_no, movement_type, product_id, quantity, from_warehouse_id, to_warehouse_id, unit_price, total_price, remarks, user_id)
                       VALUES (?, 'TRANSFER', ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ref, product_id, quantity, from_id, to_id, product["cost_price"], quantity * product["cost_price"], remarks, user["id"]),
                )
                db.commit()

            database.log_activity(
                user["id"], user["username"], "STOCK_TRANSFER", "INVENTORY",
                f"Transferred {quantity} {product['unit']} of '{product['name']}'. Ref: {ref}"
            )
            flash(f"Stock transfer completed successfully. Reference: {ref}", "success")
            return redirect(url_for("transfer"))
        except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
            flash(str(exc), "error")

    return render_template(
        "operation.html",
        mode="transfer",
        products=get_products(),
        warehouses=get_warehouses(),
    )


@app.route("/dispatch", methods=["GET", "POST"])
@login_required
def dispatch():
    user = current_user()
    if request.method == "POST":
        try:
            product_id = read_positive_int(request.form.get("product_id"), "product")
            warehouse_id = read_positive_int(request.form.get("warehouse_id"), "source warehouse")
            quantity = read_positive_int(request.form.get("quantity"), "quantity")
            customer_id = int(request.form.get("customer_id") or 0) or None
            unit_price = read_positive_float(request.form.get("unit_price"), "unit selling price")
            invoice_ref = request.form.get("invoice_ref", "").strip()
            remarks = request.form.get("remarks", "").strip()

            if invoice_ref:
                remarks = f"Invoice #{invoice_ref} | {remarks}".strip(" |")

            with get_db() as db:
                product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
                if not product:
                    raise ValueError("Select a valid product.")

                if unit_price == 0.0 and product["selling_price"]:
                    unit_price = product["selling_price"]

                ref = next_reference("DSP", db)
                update_stock(db, product_id, warehouse_id, -quantity)

                db.execute(
                    """INSERT INTO movements
                       (ref_no, movement_type, product_id, quantity, from_warehouse_id, customer_id, unit_price, total_price, remarks, user_id)
                       VALUES (?, 'DISPATCH', ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ref, product_id, quantity, warehouse_id, customer_id, unit_price, quantity * unit_price, remarks, user["id"]),
                )
                db.commit()

            database.log_activity(
                user["id"], user["username"], "STOCK_DISPATCH", "INVENTORY",
                f"Dispatched {quantity} {product['unit']} of '{product['name']}'. Ref: {ref}"
            )
            flash(f"Dispatch recorded successfully. Reference: {ref} ({quantity} units deducted).", "success")
            return redirect(url_for("dispatch"))
        except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
            flash(str(exc), "error")

    return render_template(
        "operation.html",
        mode="dispatch",
        products=get_products(),
        warehouses=get_warehouses(),
        customers=get_customers(),
    )


# -------------------------------------------------------------
# Returns & Stock Adjustments
# -------------------------------------------------------------
@app.route("/returns", methods=["GET", "POST"])
@login_required
@role_required(["admin", "manager"])
def returns():
    user = current_user()
    if request.method == "POST":
        try:
            return_type = request.form.get("return_type", "customer")  # 'customer' or 'supplier'
            product_id = read_positive_int(request.form.get("product_id"), "product")
            warehouse_id = read_positive_int(request.form.get("warehouse_id"), "warehouse")
            quantity = read_positive_int(request.form.get("quantity"), "quantity")
            party_id = int(request.form.get("party_id") or 0) or None
            reason = request.form.get("reason", "").strip()

            with get_db() as db:
                product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
                if not product:
                    raise ValueError("Product not found.")

                if return_type == "customer":
                    # Customer return: stock comes BACK into the warehouse (+qty)
                    ref = next_reference("RET-IN", db)
                    update_stock(db, product_id, warehouse_id, quantity)
                    db.execute(
                        """INSERT INTO movements
                           (ref_no, movement_type, product_id, quantity, to_warehouse_id, customer_id, unit_price, total_price, remarks, user_id)
                           VALUES (?, 'RETURN_IN', ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (ref, product_id, quantity, warehouse_id, party_id, product["selling_price"], quantity * product["selling_price"], f"Customer Return: {reason}", user["id"]),
                    )
                    flash(f"Customer return recorded ({quantity} units returned to warehouse). Ref: {ref}", "success")
                else:
                    # Supplier return: defective/excess stock returned to supplier (-qty)
                    ref = next_reference("RET-OUT", db)
                    update_stock(db, product_id, warehouse_id, -quantity)
                    db.execute(
                        """INSERT INTO movements
                           (ref_no, movement_type, product_id, quantity, from_warehouse_id, supplier_id, unit_price, total_price, remarks, user_id)
                           VALUES (?, 'RETURN_OUT', ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (ref, product_id, quantity, warehouse_id, party_id, product["cost_price"], quantity * product["cost_price"], f"Supplier Return: {reason}", user["id"]),
                    )
                    flash(f"Supplier return recorded ({quantity} units sent back to vendor). Ref: {ref}", "success")

                db.commit()

            database.log_activity(user["id"], user["username"], f"RETURN_{return_type.upper()}", "INVENTORY", f"Ref: {ref}")
            return redirect(url_for("returns"))
        except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
            flash(str(exc), "error")

    with get_db() as db:
        history = db.execute(
            """SELECT m.*, p.name AS product_name, p.sku,
                      w.name AS warehouse_name, u.username AS recorded_by
               FROM movements m
               JOIN products p ON p.id = m.product_id
               LEFT JOIN warehouses w ON w.id = COALESCE(m.to_warehouse_id, m.from_warehouse_id)
               LEFT JOIN users u ON u.id = m.user_id
               WHERE m.movement_type IN ('RETURN_IN', 'RETURN_OUT')
               ORDER BY m.id DESC LIMIT 50"""
        ).fetchall()

    return render_template(
        "returns.html",
        products=get_products(),
        warehouses=get_warehouses(),
        suppliers=get_suppliers(),
        customers=get_customers(),
        history=history,
    )


@app.route("/adjustments", methods=["GET", "POST"])
@login_required
@role_required(["admin", "manager"])
def adjustments():
    user = current_user()
    if request.method == "POST":
        try:
            adj_type = request.form.get("adj_type", "ADD")  # 'ADD' or 'SUB'
            product_id = read_positive_int(request.form.get("product_id"), "product")
            warehouse_id = read_positive_int(request.form.get("warehouse_id"), "warehouse")
            quantity = read_positive_int(request.form.get("quantity"), "quantity")
            reason_category = request.form.get("reason_category", "Inventory Audit Correction")
            notes = request.form.get("notes", "").strip()

            combined_remarks = f"[{reason_category}] {notes}".strip()

            with get_db() as db:
                product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
                if not product:
                    raise ValueError("Product not found.")

                ref = next_reference("ADJ", db)
                if adj_type == "ADD":
                    update_stock(db, product_id, warehouse_id, quantity)
                    db.execute(
                        """INSERT INTO movements
                           (ref_no, movement_type, product_id, quantity, to_warehouse_id, unit_price, total_price, remarks, user_id)
                           VALUES (?, 'ADJUSTMENT_ADD', ?, ?, ?, ?, ?, ?, ?)""",
                        (ref, product_id, quantity, warehouse_id, product["cost_price"], quantity * product["cost_price"], combined_remarks, user["id"]),
                    )
                    flash(f"Stock adjusted: +{quantity} units added. Ref: {ref}", "success")
                else:
                    update_stock(db, product_id, warehouse_id, -quantity)
                    db.execute(
                        """INSERT INTO movements
                           (ref_no, movement_type, product_id, quantity, from_warehouse_id, unit_price, total_price, remarks, user_id)
                           VALUES (?, 'ADJUSTMENT_SUB', ?, ?, ?, ?, ?, ?, ?)""",
                        (ref, product_id, quantity, warehouse_id, product["cost_price"], quantity * product["cost_price"], combined_remarks, user["id"]),
                    )
                    flash(f"Stock adjusted: -{quantity} units removed. Ref: {ref}", "success")

                db.commit()

            database.log_activity(user["id"], user["username"], f"STOCK_ADJUSTMENT_{adj_type}", "AUDIT", f"Ref: {ref}")
            return redirect(url_for("adjustments"))
        except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
            flash(str(exc), "error")

    with get_db() as db:
        history = db.execute(
            """SELECT m.*, p.name AS product_name, p.sku,
                      w.name AS warehouse_name, u.username AS recorded_by
               FROM movements m
               JOIN products p ON p.id = m.product_id
               LEFT JOIN warehouses w ON w.id = COALESCE(m.to_warehouse_id, m.from_warehouse_id)
               LEFT JOIN users u ON u.id = m.user_id
               WHERE m.movement_type IN ('ADJUSTMENT_ADD', 'ADJUSTMENT_SUB')
               ORDER BY m.id DESC LIMIT 50"""
        ).fetchall()

    return render_template(
        "adjustments.html",
        products=get_products(),
        warehouses=get_warehouses(),
        history=history,
    )


# -------------------------------------------------------------
# Stock Alerts & Transactions
# -------------------------------------------------------------
@app.route("/alerts")
@login_required
def alerts():
    rows = inventory_rows()
    low_stock = [row for row in rows if row["total_stock"] <= row["reorder_level"]]
    return render_template("alerts.html", rows=low_stock)


@app.route("/transactions")
@login_required
def transactions():
    type_filter = request.args.get("type", "").strip()
    warehouse_filter = request.args.get("warehouse_id", type=int)

    query = """
        SELECT m.*, p.name AS product_name, p.sku, p.unit,
               fw.name AS from_name, tw.name AS to_name,
               s.name AS supplier_name, c.name AS customer_name,
               u.username AS recorded_by
        FROM movements m
        JOIN products p ON p.id = m.product_id
        LEFT JOIN warehouses fw ON fw.id = m.from_warehouse_id
        LEFT JOIN warehouses tw ON tw.id = m.to_warehouse_id
        LEFT JOIN suppliers s ON s.id = m.supplier_id
        LEFT JOIN customers c ON c.id = m.customer_id
        LEFT JOIN users u ON u.id = m.user_id
        WHERE 1=1
    """
    params: list[Any] = []
    if type_filter:
        query += " AND m.movement_type = ?"
        params.append(type_filter)
    if warehouse_filter:
        query += " AND (m.from_warehouse_id = ? OR m.to_warehouse_id = ?)"
        params.extend([warehouse_filter, warehouse_filter])

    query += " ORDER BY m.id DESC LIMIT 300"

    with get_db() as db:
        rows = db.execute(query, params).fetchall()

    return render_template(
        "transactions.html",
        rows=rows,
        warehouses=get_warehouses(False),
        selected_type=type_filter,
        selected_warehouse=warehouse_filter,
    )


# -------------------------------------------------------------
# Reports & Exports
# -------------------------------------------------------------
@app.route("/reports")
@login_required
def report_dashboard():
    report_type = request.args.get("tab", "valuation")

    with get_db() as db:
        if report_type == "valuation":
            rows = inventory_rows()
            total_units = sum(r["total_stock"] for r in rows)
            total_cost = sum(r["cost_valuation"] for r in rows)
            total_retail = sum(r["retail_valuation"] for r in rows)
            summary = {
                "total_skus": len(rows),
                "total_units": total_units,
                "total_cost": total_cost,
                "total_retail": total_retail,
                "gross_margin": total_retail - total_cost,
            }
            return render_template("reports.html", tab="valuation", rows=rows, summary=summary)

        elif report_type == "movements":
            movements = db.execute(
                """SELECT m.*, p.name AS product_name, p.sku,
                          fw.name AS from_name, tw.name AS to_name,
                          s.name AS supplier_name, c.name AS customer_name,
                          u.username AS user_name
                   FROM movements m
                   JOIN products p ON p.id = m.product_id
                   LEFT JOIN warehouses fw ON fw.id = m.from_warehouse_id
                   LEFT JOIN warehouses tw ON tw.id = m.to_warehouse_id
                   LEFT JOIN suppliers s ON s.id = m.supplier_id
                   LEFT JOIN customers c ON c.id = m.customer_id
                   LEFT JOIN users u ON u.id = m.user_id
                   ORDER BY m.id DESC LIMIT 200"""
            ).fetchall()
            return render_template("reports.html", tab="movements", rows=movements)

        elif report_type == "purchases":
            purchases = db.execute(
                """SELECT m.*, p.name AS product_name, p.sku, s.name AS supplier_name,
                          tw.name AS warehouse_name, u.username AS user_name
                   FROM movements m
                   JOIN products p ON p.id = m.product_id
                   JOIN suppliers s ON s.id = m.supplier_id
                   LEFT JOIN warehouses tw ON tw.id = m.to_warehouse_id
                   LEFT JOIN users u ON u.id = m.user_id
                   WHERE m.movement_type = 'GRN'
                   ORDER BY m.id DESC LIMIT 150"""
            ).fetchall()
            total_spent = sum(r["total_price"] for r in purchases)
            return render_template("reports.html", tab="purchases", rows=purchases, total_spent=total_spent)

        elif report_type == "sales":
            sales = db.execute(
                """SELECT m.*, p.name AS product_name, p.sku, c.name AS customer_name,
                          fw.name AS warehouse_name, u.username AS user_name
                   FROM movements m
                   JOIN products p ON p.id = m.product_id
                   JOIN customers c ON c.id = m.customer_id
                   LEFT JOIN warehouses fw ON fw.id = m.from_warehouse_id
                   LEFT JOIN users u ON u.id = m.user_id
                   WHERE m.movement_type = 'DISPATCH'
                   ORDER BY m.id DESC LIMIT 150"""
            ).fetchall()
            total_revenue = sum(r["total_price"] for r in sales)
            return render_template("reports.html", tab="sales", rows=sales, total_revenue=total_revenue)

    return redirect(url_for("report_dashboard", tab="valuation"))


@app.route("/reports/export/excel")
@login_required
def export_excel():
    export_type = request.args.get("type", "valuation")
    if export_type == "valuation":
        excel_stream = reports.generate_inventory_valuation_excel()
        filename = f"SmartStock_Valuation_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(
            excel_stream,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    elif export_type == "movements":
        with get_db() as db:
            rows = db.execute(
                """SELECT m.*, p.name AS product_name, p.sku,
                          fw.name AS from_name, tw.name AS to_name,
                          s.name AS supplier_name, c.name AS customer_name,
                          u.username AS user_name
                   FROM movements m
                   JOIN products p ON p.id = m.product_id
                   LEFT JOIN warehouses fw ON fw.id = m.from_warehouse_id
                   LEFT JOIN warehouses tw ON tw.id = m.to_warehouse_id
                   LEFT JOIN suppliers s ON s.id = m.supplier_id
                   LEFT JOIN customers c ON c.id = m.customer_id
                   LEFT JOIN users u ON u.id = m.user_id
                   ORDER BY m.id DESC"""
            ).fetchall()
            excel_stream = reports.generate_movements_excel([dict(r) for r in rows])
            filename = f"SmartStock_Movements_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            return send_file(
                excel_stream,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=filename,
            )
    return redirect(url_for("report_dashboard"))


@app.route("/reports/export/csv")
@login_required
def export_csv():
    export_type = request.args.get("type", "valuation")
    if export_type == "valuation":
        rows = inventory_rows()
        headers = ["Product Name", "SKU", "Barcode", "Category", "Unit", "Total Stock", "Unit Cost", "Selling Price", "Total Cost Value", "Total Retail Value", "Status"]
        csv_data = [
            [r["name"], r["sku"], r["barcode"], r.get("category_name") or r["category"], r["unit"], r["total_stock"], r["cost_price"], r["selling_price"], r["cost_valuation"], r["retail_valuation"], r["status"]]
            for r in rows
        ]
        stream = reports.generate_csv(headers, csv_data)
        mem = io.BytesIO(stream.getvalue().encode("utf-8-sig"))
        filename = f"SmartStock_Valuation_{datetime.now().strftime('%Y%m%d')}.csv"
        return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=filename)
    return redirect(url_for("report_dashboard"))


# -------------------------------------------------------------
# User Management (Admin only)
# -------------------------------------------------------------
@app.route("/users", methods=["GET", "POST"])
@login_required
@role_required(["admin"])
def user_management():
    curr = current_user()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "staff").strip().lower()

        if not username or not full_name or not password:
            flash("Username, full name, and initial password are required.", "error")
            return redirect(url_for("user_management"))

        if role not in ["admin", "manager", "staff"]:
            role = "staff"

        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO users (username, password_hash, full_name, email, role)
                       VALUES (?, ?, ?, ?, ?)""",
                    (username, generate_password_hash(password), full_name, email, role),
                )
                db.commit()
            database.log_activity(curr["id"], curr["username"], "ADD_USER", "SECURITY", f"Created user '{username}' with role '{role}'")
            flash(f"User account '{username}' created successfully.", "success")
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")

        return redirect(url_for("user_management"))

    with get_db() as db:
        users_list = db.execute("SELECT id, username, full_name, email, role, is_active, created_at, last_login FROM users ORDER BY username").fetchall()

    return render_template("users.html", users=users_list)


@app.route("/users/<int:id>/toggle-status", methods=["POST"])
@login_required
@role_required(["admin"])
def toggle_user_status(id: int):
    curr = current_user()
    if curr["id"] == id:
        flash("You cannot deactivate your own administrative account.", "error")
        return redirect(url_for("user_management"))

    with get_db() as db:
        user = db.execute("SELECT username, is_active FROM users WHERE id = ?", (id,)).fetchone()
        if user:
            new_status = 0 if user["is_active"] else 1
            db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, id))
            db.commit()
            database.log_activity(curr["id"], curr["username"], "TOGGLE_USER_STATUS", "SECURITY", f"Changed status of '{user['username']}' to {'Active' if new_status else 'Inactive'}")
            flash(f"User '{user['username']}' is now {'active' if new_status else 'inactive'}.", "success")
    return redirect(url_for("user_management"))


@app.route("/users/<int:id>/reset-password", methods=["POST"])
@login_required
@role_required(["admin"])
def reset_user_password(id: int):
    curr = current_user()
    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 6:
        flash("Password must be at least 6 characters long.", "error")
        return redirect(url_for("user_management"))

    with get_db() as db:
        user = db.execute("SELECT username FROM users WHERE id = ?", (id,)).fetchone()
        if user:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), id))
            db.commit()
            database.log_activity(curr["id"], curr["username"], "RESET_PASSWORD", "SECURITY", f"Reset password for '{user['username']}'")
            flash(f"Password reset successfully for '{user['username']}'.", "success")
    return redirect(url_for("user_management"))


# -------------------------------------------------------------
# System Settings & Backup
# -------------------------------------------------------------
@app.route("/settings", methods=["GET", "POST"])
@login_required
@role_required(["admin", "manager"])
def settings():
    curr = current_user()
    if request.method == "POST":
        data = {
            "company_name": request.form.get("company_name", "").strip(),
            "company_tagline": request.form.get("company_tagline", "").strip(),
            "currency_symbol": request.form.get("currency_symbol", "₹").strip(),
            "contact_email": request.form.get("contact_email", "").strip(),
            "contact_phone": request.form.get("contact_phone", "").strip(),
            "company_address": request.form.get("company_address", "").strip(),
            "tax_number": request.form.get("tax_number", "").strip(),
            "default_reorder_level": request.form.get("default_reorder_level", "15").strip(),
        }
        database.update_settings(data)
        database.log_activity(curr["id"], curr["username"], "UPDATE_SETTINGS", "SYSTEM", "Saved application configuration")
        flash("System and company settings updated successfully.", "success")
        return redirect(url_for("settings"))

    settings_dict = {}
    with get_db() as db:
        for r in db.execute("SELECT key, value FROM settings").fetchall():
            settings_dict[r["key"]] = r["value"]

        db_stats = {
            "db_size_kb": round(os.path.getsize(DATABASE_PATH) / 1024, 2) if os.path.exists(DATABASE_PATH) else 0,
            "total_products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "total_movements": db.execute("SELECT COUNT(*) FROM movements").fetchone()[0],
            "total_users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        }

    return render_template("settings.html", settings=settings_dict, db_stats=db_stats)


@app.route("/settings/backup")
@login_required
@role_required(["admin"])
def download_backup():
    curr = current_user()
    if os.path.exists(DATABASE_PATH):
        database.log_activity(curr["id"], curr["username"], "DB_BACKUP_DOWNLOAD", "SYSTEM", "Downloaded SQLite database backup")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(DATABASE_PATH, as_attachment=True, download_name=f"smartstock_backup_{timestamp}.db")
    flash("Database file not found on disk.", "error")
    return redirect(url_for("settings"))


# -------------------------------------------------------------
# Activity & Audit Logs
# -------------------------------------------------------------
@app.route("/logs")
@login_required
@role_required(["admin", "manager"])
def activity_logs():
    with get_db() as db:
        logs = db.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT 200").fetchall()
    return render_template("logs.html", logs=logs)


# -------------------------------------------------------------
# REST APIs for Real-Time Scanner, Charting & Autocomplete
# -------------------------------------------------------------
@app.route("/api/product-lookup")
@login_required
def product_lookup():
    code = request.args.get("code", "").strip()
    if not code:
        return jsonify({"error": "Enter or scan a product SKU or barcode."}), 400

    with get_db() as db:
        product = db.execute(
            """SELECT p.*, c.name AS category_name
               FROM products p
               LEFT JOIN categories c ON c.id = p.category_id
               WHERE (lower(p.sku) = lower(?) OR lower(p.barcode) = lower(?)) AND p.is_active = 1""",
            (code, code),
        ).fetchone()

        if not product:
            return jsonify({"error": f"No active product found matching '{code}'."}), 404

        stocks = db.execute(
            """SELECT w.id AS warehouse_id, w.name AS warehouse_name,
                      COALESCE(s.quantity, 0) AS quantity
               FROM warehouses w
               LEFT JOIN stock s ON s.warehouse_id = w.id AND s.product_id = ?
               WHERE w.is_active = 1
               ORDER BY w.name""",
            (product["id"],),
        ).fetchall()

        total_stock = sum(s["quantity"] for s in stocks)

    return jsonify({
        "id": product["id"],
        "sku": product["sku"],
        "barcode": product["barcode"],
        "name": product["name"],
        "category": product["category_name"] or product["category"],
        "unit": product["unit"],
        "cost_price": product["cost_price"],
        "selling_price": product["selling_price"],
        "total_stock": total_stock,
        "stocks": [dict(row) for row in stocks],
    })


@app.route("/api/chart-data")
@login_required
def chart_data():
    """Return JSON metrics for dashboard Chart.js widgets."""
    with get_db() as db:
        # Category breakdown
        cat_data = db.execute(
            """SELECT COALESCE(c.name, 'General') AS label,
                      COALESCE(SUM(s.quantity), 0) AS value
               FROM products p
               LEFT JOIN categories c ON c.id = p.category_id
               LEFT JOIN stock s ON s.product_id = p.id
               WHERE p.is_active = 1
               GROUP BY label
               HAVING value > 0
               ORDER BY value DESC LIMIT 6"""
        ).fetchall()

        # Last 7 days movement counts
        trend_data = db.execute(
            """SELECT date(created_at) AS day,
                      SUM(CASE WHEN movement_type IN ('GRN', 'OPENING', 'RETURN_IN', 'ADJUSTMENT_ADD') THEN quantity ELSE 0 END) AS inbound,
                      SUM(CASE WHEN movement_type IN ('DISPATCH', 'RETURN_OUT', 'ADJUSTMENT_SUB') THEN quantity ELSE 0 END) AS outbound
               FROM movements
               WHERE date(created_at) >= date('now', '-7 days')
               GROUP BY day ORDER BY day ASC"""
        ).fetchall()

    return jsonify({
        "categories": {
            "labels": [r["label"] for r in cat_data],
            "values": [r["value"] for r in cat_data],
        },
        "trends": {
            "labels": [r["day"] for r in trend_data],
            "inbound": [r["inbound"] for r in trend_data],
            "outbound": [r["outbound"] for r in trend_data],
        },
    })


@app.route("/favicon.ico")
def favicon():
    return "", 204


# -------------------------------------------------------------
# Global Error Handlers (Prevents unhandled 500 white screen)
# -------------------------------------------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template(
        "error.html",
        code=404,
        title="Page Not Found",
        message="The page or record you requested could not be located in RSR SmartStock.",
    ), 404


@app.errorhandler(403)
def access_forbidden(e):
    return render_template(
        "error.html",
        code=403,
        title="Access Forbidden",
        message="You do not have administrative permission to view or modify this resource.",
    ), 403


@app.errorhandler(500)
def internal_server_error(e):
    tb = traceback.format_exc()
    app.logger.error(f"Internal Server Error encountered: {e}\n{tb}")
    print(f"[ERROR 500] {e}\n{tb}")
    return render_template(
        "error.html",
        code=500,
        title="System Error Recovered",
        message="An unexpected error occurred during this request. The system has safely logged the diagnostic details. Please return to the dashboard or try your action again.",
    ), 500


# -------------------------------------------------------------
# Database Startup Initialization
# -------------------------------------------------------------
database.init_db()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=False)
