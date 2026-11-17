from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "smartstock.db"


def get_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def column_exists(db: sqlite3.Connection, table: str, column: str) -> bool:
    cursor = db.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]
    return column in columns


def init_db() -> None:
    """Initialize database schema, apply migrations safely without losing data, and seed initial records."""
    with get_db() as db:
        # 1. Users table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'staff' CHECK(role IN ('admin', 'manager', 'staff')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT
            );
            """
        )

        # 2. Categories table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # 3. Suppliers table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL UNIQUE,
                contact_person TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # 4. Customers table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL UNIQUE,
                contact_person TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # 5. Warehouses table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS warehouses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                capacity INTEGER NOT NULL DEFAULT 10000,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if not column_exists(db, "warehouses", "code"):
            db.execute("ALTER TABLE warehouses ADD COLUMN code TEXT NOT NULL DEFAULT ''")
        if not column_exists(db, "warehouses", "capacity"):
            db.execute("ALTER TABLE warehouses ADD COLUMN capacity INTEGER NOT NULL DEFAULT 10000")
        if not column_exists(db, "warehouses", "is_active"):
            db.execute("ALTER TABLE warehouses ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

        # 6. Products table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                barcode TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                unit TEXT NOT NULL DEFAULT 'pcs',
                cost_price REAL NOT NULL DEFAULT 0.0,
                selling_price REAL NOT NULL DEFAULT 0.0,
                reorder_level INTEGER NOT NULL DEFAULT 10,
                description TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if not column_exists(db, "products", "category_id"):
            db.execute("ALTER TABLE products ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")
        if not column_exists(db, "products", "cost_price"):
            db.execute("ALTER TABLE products ADD COLUMN cost_price REAL NOT NULL DEFAULT 0.0")
        if not column_exists(db, "products", "selling_price"):
            db.execute("ALTER TABLE products ADD COLUMN selling_price REAL NOT NULL DEFAULT 0.0")
        if not column_exists(db, "products", "description"):
            db.execute("ALTER TABLE products ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if not column_exists(db, "products", "is_active"):
            db.execute("ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

        # 7. Stock table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
                quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
                UNIQUE(product_id, warehouse_id)
            );
            """
        )

        # 8. Movements table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_no TEXT NOT NULL,
                movement_type TEXT NOT NULL,
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                from_warehouse_id INTEGER REFERENCES warehouses(id),
                to_warehouse_id INTEGER REFERENCES warehouses(id),
                supplier_id INTEGER REFERENCES suppliers(id),
                customer_id INTEGER REFERENCES customers(id),
                unit_price REAL NOT NULL DEFAULT 0.0,
                total_price REAL NOT NULL DEFAULT 0.0,
                remarks TEXT NOT NULL DEFAULT '',
                user_id INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if not column_exists(db, "movements", "supplier_id"):
            db.execute("ALTER TABLE movements ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id)")
        if not column_exists(db, "movements", "customer_id"):
            db.execute("ALTER TABLE movements ADD COLUMN customer_id INTEGER REFERENCES customers(id)")
        if not column_exists(db, "movements", "unit_price"):
            db.execute("ALTER TABLE movements ADD COLUMN unit_price REAL NOT NULL DEFAULT 0.0")
        if not column_exists(db, "movements", "total_price"):
            db.execute("ALTER TABLE movements ADD COLUMN total_price REAL NOT NULL DEFAULT 0.0")
        if not column_exists(db, "movements", "user_id"):
            db.execute("ALTER TABLE movements ADD COLUMN user_id INTEGER REFERENCES users(id)")

        # 9. Activity Logs table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                username TEXT NOT NULL DEFAULT 'System',
                action TEXT NOT NULL,
                module TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                ip_address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # 10. Settings table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        # Seed initial settings
        default_settings = [
            ("company_name", "RSR SmartStock Enterprises"),
            ("company_tagline", "Inventory Clarity. Warehouse Control."),
            ("currency_symbol", "₹"),
            ("currency_code", "INR"),
            ("contact_email", "support@rsrsmartstock.local"),
            ("contact_phone", "+91 98765 43210"),
            ("company_address", "42 Industrial Tech Park, Electronic City, Bengaluru, Karnataka 560100"),
            ("tax_number", "GSTIN29AAACR1234F1Z5"),
            ("default_reorder_level", "15"),
            ("low_stock_alert_threshold", "10"),
        ]
        for key, val in default_settings:
            db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

        # Seed default users (Admin, Manager, Staff)
        user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            users = [
                ("admin", generate_password_hash("admin123"), "System Administrator", "admin@rsrsmartstock.local", "admin"),
                ("manager", generate_password_hash("manager123"), "Warehouse Manager", "manager@rsrsmartstock.local", "manager"),
                ("staff", generate_password_hash("staff123"), "Operations Staff", "staff@rsrsmartstock.local", "staff"),
            ]
            db.executemany(
                """INSERT INTO users (username, password_hash, full_name, email, role)
                   VALUES (?, ?, ?, ?, ?)""",
                users,
            )

        # Seed default categories
        cat_count = db.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if cat_count == 0:
            sample_cats = [
                ("Electronics", "CAT-ELEC", "Computer hardware, microcontrollers, and electronic devices"),
                ("Accessories", "CAT-ACCS", "Cables, converters, chargers, and peripheral accessories"),
                ("Stationery", "CAT-STAT", "Paper reams, pens, filing, and office supplies"),
                ("Furniture", "CAT-FURN", "Desks, ergonomic office chairs, and modular storage"),
                ("Networking", "CAT-NETW", "Routers, switches, patch panels, and optical gear"),
                ("Packaging", "CAT-PACK", "Carton boxes, bubble wraps, and protective tape"),
            ]
            db.executemany(
                "INSERT INTO categories (name, code, description) VALUES (?, ?, ?)",
                sample_cats,
            )

        # Seed default suppliers
        sup_count = db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
        if sup_count == 0:
            sample_suppliers = [
                ("Apex Electronics Ltd", "SUP-101", "Vikram Sharma", "vikram@apexelectronics.com", "+91 98450 11223", "Plot 14, Peenya Industrial Area, Bengaluru"),
                ("Global Office Supplies", "SUP-102", "Ananya Deshmukh", "sales@globaloffice.in", "+91 98220 44556", "302 Commerce Towers, Andheri East, Mumbai"),
                ("Prime Cable & Network Dist", "SUP-103", "Rajesh Nair", "contact@primenet.co.in", "+91 97410 77889", "88 Ring Road, Mysore Highway, Mandya"),
                ("Zenith Ergonomics Corp", "SUP-104", "Sunita Rao", "orders@zenithergo.com", "+91 99001 22334", "12 SIPCOT Industrial Park, Hosur, TN"),
            ]
            db.executemany(
                """INSERT INTO suppliers (name, code, contact_person, email, phone, address)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                sample_suppliers,
            )

        # Seed default customers
        cust_count = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        if cust_count == 0:
            sample_customers = [
                ("TechSolutions Pvt Ltd", "CUST-501", "Kavita Reddy", "procurement@techsolutions.in", "+91 99887 11223", "Level 4, IT Park, Whitefield, Bengaluru"),
                ("Metro Retailers & Stores", "CUST-502", "Arjun Patel", "merchandise@metroretail.com", "+91 98770 33445", "12 Main Market, Malleshwaram, Bengaluru"),
                ("RSR Enterprise Corp", "CUST-503", "Harish R", "supplychain@rsrenterprise.com", "+91 97660 55667", "55 Koramangala 4th Block, Bengaluru"),
                ("Apex Institute of Technology", "CUST-504", "Dr. Satish Kumar", "admin@apexinstitute.edu.in", "+91 98441 99887", "Campus Road, Vijayanagar, Mysuru"),
            ]
            db.executemany(
                """INSERT INTO customers (name, code, contact_person, email, phone, address)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                sample_customers,
            )

        # Seed warehouses if not present or update code
        wh_count = db.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0]
        if wh_count == 0:
            sample_wh = [
                ("Main Warehouse", "WH-BLR-01", "Bengaluru, Karnataka (HQ)", 25000),
                ("Branch Warehouse", "WH-MYS-02", "Mysuru, Karnataka", 15000),
                ("Distribution Hub", "WH-CHN-03", "Chennai, Tamil Nadu", 20000),
            ]
            db.executemany(
                "INSERT INTO warehouses (name, code, location, capacity) VALUES (?, ?, ?, ?)",
                sample_wh,
            )
        else:
            # Update warehouse codes if empty
            db.execute("UPDATE warehouses SET code = 'WH-01' WHERE code = '' AND name = 'Main Warehouse'")
            db.execute("UPDATE warehouses SET code = 'WH-02' WHERE code = '' AND name = 'Branch Warehouse'")
            wh3 = db.execute("SELECT id FROM warehouses WHERE name = 'Distribution Hub'").fetchone()
            if not wh3:
                db.execute(
                    "INSERT INTO warehouses (name, code, location, capacity) VALUES (?, ?, ?, ?)",
                    ("Distribution Hub", "WH-03", "Chennai, Tamil Nadu", 20000),
                )

        # Link categories and update product pricing
        products = db.execute("SELECT id, name, category, cost_price, selling_price FROM products").fetchall()
        if len(products) == 0:
            cat_map = {row["name"]: row["id"] for row in db.execute("SELECT name, id FROM categories").fetchall()}
            sample_products = [
                ("RSR-1001", "8901000001001", "Wireless Optical Mouse", "Electronics", cat_map.get("Electronics"), "pcs", 450.0, 799.0, 15, "2.4GHz USB wireless optical mouse with ergonomic grip"),
                ("RSR-1002", "8901000001002", "Mechanical USB Keyboard", "Electronics", cat_map.get("Electronics"), "pcs", 1100.0, 1899.0, 12, "RGB backlit mechanical keyboard with blue tactile switches"),
                ("RSR-1003", "8901000001003", "HDMI 2.1 Cable 2m", "Accessories", cat_map.get("Accessories"), "pcs", 180.0, 399.0, 20, "Ultra high speed 8K @ 60Hz 48Gbps braided cable"),
                ("RSR-1004", "8901000001004", "A4 Copier Paper Ream 75gsm", "Stationery", cat_map.get("Stationery"), "ream", 220.0, 340.0, 10, "500 sheets bright white multi-purpose photocopy paper"),
                ("RSR-1005", "8901000001005", "Ergonomic Mesh Office Chair", "Furniture", cat_map.get("Furniture"), "pcs", 4200.0, 6800.0, 8, "High-back breathable mesh chair with adjustable lumbar support"),
                ("RSR-1006", "8901000001006", "Cat6 UTP Ethernet Cable 5m", "Accessories", cat_map.get("Accessories"), "pcs", 120.0, 250.0, 18, "Snagless molded RJ45 patch cord Gigabit ready"),
                ("RSR-1007", "8901000001007", "Dual-Band Wi-Fi 6 Router", "Networking", cat_map.get("Networking"), "pcs", 2100.0, 3499.0, 10, "AX1800 Gigabit wireless router with 4 high-gain antennas"),
                ("RSR-1008", "8901000001008", "Heavy Duty Corrugated Box (L)", "Packaging", cat_map.get("Packaging"), "pcs", 45.0, 90.0, 25, "3-ply strong brown corrugated box 40x30x30 cm"),
            ]
            db.executemany(
                """INSERT INTO products (sku, barcode, name, category, category_id, unit, cost_price, selling_price, reorder_level, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                sample_products,
            )
            main_id = db.execute("SELECT id FROM warehouses WHERE name LIKE '%Main%' LIMIT 1").fetchone()[0]
            branch_id = db.execute("SELECT id FROM warehouses WHERE name LIKE '%Branch%' LIMIT 1").fetchone()[0]
            hub_id = db.execute("SELECT id FROM warehouses WHERE name LIKE '%Hub%' or name LIKE '%Distribution%' LIMIT 1").fetchone()[0]
            
            p_ids = [r["id"] for r in db.execute("SELECT id FROM products ORDER BY id").fetchall()]
            stock_seeds = [
                (p_ids[0], main_id, 75), (p_ids[0], branch_id, 15), (p_ids[0], hub_id, 20),
                (p_ids[1], main_id, 45), (p_ids[1], branch_id, 8),  (p_ids[1], hub_id, 12),
                (p_ids[2], main_id, 90), (p_ids[2], branch_id, 25), (p_ids[2], hub_id, 30),
                (p_ids[3], main_id, 30), (p_ids[3], branch_id, 5),  (p_ids[3], hub_id, 10),
                (p_ids[4], main_id, 10), (p_ids[4], branch_id, 2),  (p_ids[4], hub_id, 4),
                (p_ids[5], main_id, 40), (p_ids[5], branch_id, 12), (p_ids[5], hub_id, 15),
                (p_ids[6], main_id, 22), (p_ids[6], branch_id, 6),  (p_ids[6], hub_id, 8),
                (p_ids[7], main_id, 150),(p_ids[7], branch_id, 40), (p_ids[7], hub_id, 60),
            ]
            db.executemany("INSERT OR REPLACE INTO stock (product_id, warehouse_id, quantity) VALUES (?, ?, ?)", stock_seeds)
        else:
            # Existing products: backfill cost_price / selling_price / category_id if zero
            cat_map = {row["name"]: row["id"] for row in db.execute("SELECT name, id FROM categories").fetchall()}
            for p in products:
                updates = []
                params = []
                c_id = cat_map.get(p["category"])
                if c_id:
                    updates.append("category_id = ?")
                    params.append(c_id)
                if not p["cost_price"] or p["cost_price"] == 0.0:
                    # reasonable default cost based on name
                    cost = 250.0
                    sell = 450.0
                    if "Mouse" in p["name"]:
                        cost, sell = 450.0, 799.0
                    elif "Keyboard" in p["name"]:
                        cost, sell = 1100.0, 1899.0
                    elif "Cable" in p["name"]:
                        cost, sell = 180.0, 399.0
                    elif "Paper" in p["name"]:
                        cost, sell = 220.0, 340.0
                    elif "Chair" in p["name"]:
                        cost, sell = 4200.0, 6800.0
                    updates.append("cost_price = ?")
                    params.append(cost)
                    updates.append("selling_price = ?")
                    params.append(sell)
                if updates:
                    params.append(p["id"])
                    db.execute(f"UPDATE products SET {', '.join(updates)} WHERE id = ?", params)

        db.commit()


def get_setting(key: str, default: str = "") -> str:
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def update_settings(data: dict[str, str]) -> None:
    with get_db() as db:
        for key, val in data.items():
            db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, val))
        db.commit()


def log_activity(user_id: int | None, username: str, action: str, module: str, details: str = "", ip_address: str = "") -> None:
    try:
        with get_db() as db:
            db.execute(
                """INSERT INTO activity_logs (user_id, username, action, module, details, ip_address)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, username or "System", action, module, details, ip_address),
            )
            db.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
