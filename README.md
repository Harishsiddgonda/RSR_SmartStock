# RSR SmartStock – Enterprise Inventory & Warehouse Management System (WMS)

**Lead Architect & Developer:** Harish  
**Architecture:** Full-Stack Enterprise WMS (MVC / Layered Architecture)  
**Technology Stack:** Python 3.10+, Flask, SQLite 3 (ACID, Atomic Transactions), HTML5, CSS3, Vanilla JS, Chart.js, JsBarcode, QRCode.js, openpyxl  
**Platform:** Windows 10/11, macOS, Linux  

---

## 🌟 Executive Overview

**RSR SmartStock** is a fully functional, production-ready Inventory and Warehouse Management System engineered for multi-location storage facilities, barcode-driven logistics, procurement tracking, and executive asset valuation audits.

### Key Capabilities

- **🔐 Role-Based Access Control (RBAC):** Dedicated permission tiers for **Administrator**, **Warehouse Manager**, and **Operations Staff** with PBKDF2:SHA256 password hashing.
- **📊 Executive Dashboard:** High-contrast financial KPI metrics (SKU Count, Total Units, Asset Cost Valuation, Retail Value, Potential Gross Margin), low-stock warnings, live Chart.js category distribution, and movement trend graphs.
- **📦 Multi-Warehouse Control:** Real-time stock distribution across facilities (e.g. Bengaluru HQ, Mysuru Branch, Chennai Hub) with visual capacity meters.
- **🏷 Barcode & QR Label Engine:** Live camera scanning (via HTML5-QRCode), USB hardware scanner support, Code-128 and QR-code preview generation, and single-click print-ready thermal label tags.
- **📥 Goods Received Note (GRN):** Full procurement receipt workflow linked to registered suppliers with PO tracking, unit cost verification, and automated stock increments.
- **⇄ Inter-Warehouse Transfer:** Atomic location-to-location rebalancing with zero-loss transaction safety and real-time source-stock verification.
- **↗ Outbound Dispatch & Sales:** Customer order fulfillment with invoice tagging, selling price verification, and strict insufficient-stock guardrails.
- **↩ Reverse Logistics (Returns):** Support for both **Customer Returns** (stock added back to facility) and **Supplier Returns** (defective stock debited to vendor).
- **⚖ Cycle Count & Stock Adjustments:** Formal inventory audit reconciliation with mandatory reason categories (Damaged, Expired, Surplus Found, Write-off).
- **♧ Automatic Replenishment Alerts:** Intelligent reorder watchlist highlighting item shortages, deficit counts, and estimated replenishment investment.
- **📑 Financial Reports & Exports:** Multi-tab reports for Asset Valuation, Movements Audit, Purchases, and Sales with one-click **Excel (.xlsx)**, **CSV**, and **Print-Ready PDF** exports.
- **📝 Security Audit Trail:** Chronological activity logging tracking operator logins, master data edits, and stock adjustments.
- **⚙ System Settings & Backups:** Dynamic business profile customisation (Company Name, Address, Tax ID, Currency Symbol: ₹, $, €, £) and single-click SQLite `.db` snapshot download.

---

## 🔑 Default Demo Login Credentials

The system initializes with three pre-configured accounts:

| Role | Username | Password | Access Scope |
|---|---|---|---|
| **Administrator** | `admin` | `admin123` | Full access: Master Data, User Management, Settings, Database Backup, Deactivations |
| **Warehouse Manager** | `manager` | `manager123` | Operational + Management: Master Data, GRN, Transfer, Dispatch, Returns, Adjustments, Reports & Exports |
| **Operations Staff** | `staff` | `staff123` | Daily Logistics: Barcode Scanner, Live Balances, GRN, Transfers, Dispatch |

*(Tip: On the Sign-In page, click any of the "Autofill Demo Credentials" pills for instant one-click login).*

---

## 📋 System Requirements

- **Operating System:** Windows 10/11 (or macOS / Linux)
- **Python:** Python 3.10, 3.11, 3.12, 3.13, or 3.14
- **Browser:** Google Chrome, Microsoft Edge, Brave, or Mozilla Firefox
- **Optional Hardware:** Webcam / Mobile camera for scanning, or standard USB handheld barcode scanner

---

## 🚀 Quick Start Guide (Windows)

### Option 1: Automated Launch (Easiest)

1. Open PowerShell or Command Prompt in the `RSR_SmartStock` project folder.
2. Run the Windows launcher:
   ```cmd
   run_windows.bat
   ```
3. The script automatically detects Python on your system, creates a virtual environment (`.venv`), installs dependencies, runs database migrations, and boots the local web server.
4. Open your browser and navigate to:
   ```
   http://127.0.0.1:5000
   ```
5. Sign in using `admin` / `admin123`.

---

### Option 2: Manual Terminal Commands

In PowerShell or Command Prompt:

```powershell
# 1. Navigate to project root
cd C:\Users\HarishRuler\Downloads\RSR_SmartStock

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
.\.venv\Scripts\activate

# 4. Install requirements
python -m pip install -r requirements.txt

# 5. Run automated test suite to verify all modules
python test_app.py

# 6. Launch the server
python app.py
```

Then visit `http://127.0.0.1:5000` in Chrome or Edge.

---

## 🗄 Database Configuration & Architecture

- **Engine:** SQLite 3 with WAL (Write-Ahead Logging) compatibility and `PRAGMA foreign_keys = ON`.
- **Database File:** `smartstock.db` in project root.
- **Relational Schema:**
  - `users`: Operator accounts, passwords (PBKDF2), role (`admin`, `manager`, `staff`), status.
  - `categories`: Taxonomy codes, names, descriptions.
  - `suppliers`: Vendor codes, contacts, tax numbers, procurement history.
  - `customers`: Client codes, delivery addresses, dispatch orders.
  - `warehouses`: Storage facilities, addresses, capacity quotas.
  - `products`: Master catalogue with SKU, Barcode, unit, cost price, selling price, reorder thresholds.
  - `stock`: Composite key `(product_id, warehouse_id)` with `CHECK(quantity >= 0)` constraint.
  - `movements`: Historical immutable ledger (Reference, Type, Product, Qty, From/To, Party, Pricing, Operator).
  - `activity_logs`: Telemetry audit trail of user sessions and actions.
  - `settings`: Key-value application and enterprise configuration.

### How to Reset / Backup Database:
- **Download Backup:** Navigate to **Settings & Backup** (`/settings`) as Admin and click **Download Full .db Backup**.
- **Reset to Clean Seed:** Stop the application (`Ctrl + C`), delete `smartstock.db`, and run `python app.py`. The system will automatically recreate the entire schema and seed fresh sample data.

---

## 🔌 REST API Documentation

All API endpoints require active session authentication (`@login_required`):

### 1. Product Barcode & SKU Lookup
- **Endpoint:** `GET /api/product-lookup?code={SKU_OR_BARCODE}`
- **Response:**
  ```json
  {
    "id": 1,
    "sku": "RSR-1001",
    "barcode": "8901000001001",
    "name": "Wireless Optical Mouse",
    "category": "Electronics",
    "unit": "pcs",
    "cost_price": 450.0,
    "selling_price": 799.0,
    "total_stock": 110,
    "stocks": [
      { "warehouse_id": 1, "warehouse_name": "Main Warehouse", "quantity": 75 },
      { "warehouse_id": 2, "warehouse_name": "Branch Warehouse", "quantity": 15 },
      { "warehouse_id": 3, "warehouse_name": "Distribution Hub", "quantity": 20 }
    ]
  }
  ```

### 2. Live Dashboard Analytics
- **Endpoint:** `GET /api/chart-data`
- **Response:**
  ```json
  {
    "categories": {
      "labels": ["Electronics", "Accessories", "Packaging"],
      "values": [120, 155, 250]
    },
    "trends": {
      "labels": ["2026-11-10", "2026-11-11", "2026-11-12"],
      "inbound": [50, 80, 20],
      "outbound": [15, 40, 25]
    }
  }
  ```

---

## 🛠 Troubleshooting

1. **"Port 5000 is already in use"**  
   Change the port in `app.py` line `app.run(host="127.0.0.1", port=5001)` or terminate the lingering process:
   ```powershell
   Get-Process -Id (Get-NetTCPConnection -LocalPort 5000).OwningProcess | Stop-Process -Force
   ```

2. **"Camera Scanner does not start"**  
   - Browser camera access requires `localhost` or `127.0.0.1` and explicit permission in your browser prompt.
   - If using a USB handheld scanner, camera permission is not required: simply click in the scan box and pull the trigger on your scanner.

3. **"Permission Denied / Access Restricted"**  
   Certain administrative features (User Management, Settings, Product Deletion) are restricted to the `admin` role. Sign out and sign in using `admin` / `admin123`.

---

## 🧪 Automated Test Suite Verification

Run the full end-to-end unit and integration test suite:

```powershell
.\.venv\Scripts\python.exe test_app.py
```

Expected output:
```
Ran 10 tests in 2.66s
OK
```

All 10 test modules (Authentication, RBAC, Dashboard, Products, Categories, Suppliers, Customers, Warehouses, Operations & Stock Constraints, Returns & Adjustments, Reports & Excel Exports) execute and pass with zero errors.

---
*Developed for RSR SmartStock Warehouse Control System.*
