# RSR SmartStock – Enterprise Inventory & Warehouse Management System (WMS)

**Lead Architect & Developer:** Harish  
**Architecture:** Full-Stack Enterprise WMS (MVC / Layered Architecture)  
**Technology Stack:** Python 3.10+, Flask, SQLite 3 (ACID, Atomic Transactions), Gunicorn, HTML5, CSS3, Vanilla JS, Chart.js, JsBarcode, QRCode.js, openpyxl  
**Deployment Platforms:** Local Windows (Bat scripts), Linux, Render Cloud, Docker/Heroku  

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Harishsiddgonda/RSR_SmartStock)

---

## 🌟 Executive Overview & Premium UX

**RSR SmartStock** is a fully functional, production-ready Inventory and Warehouse Management System engineered for multi-location storage facilities, barcode-driven logistics, procurement tracking, and executive asset valuation audits.

### Key Capabilities

- **✨ Premium UI/UX:** Built with a modern SaaS aesthetic (glassmorphic topbar, soft card lift shadows, high-contrast badges, smooth modal transitions, responsive drawer navigation, and dark slate tones).
- **🔐 Role-Based Access Control (RBAC):** Dedicated permission tiers for **Administrator**, **Warehouse Manager**, and **Operations Staff** with PBKDF2:SHA256 password encryption and 30-day "Remember Me" persistent cookies.
- **📊 Executive Dashboard:** Real-time financial KPI metrics (SKU Count, Total Units, Asset Cost Valuation, Retail Value, Potential Gross Margin), low-stock warnings, live Chart.js category distribution, and movement trend graphs.
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

## 🔑 Default Login Credentials

The system initializes with four pre-configured accounts:

| Role | Username | Password | Access Scope |
|---|---|---|---|
| **Harish (You)** | `harish` | `harish123` | **Full Lead Developer & Admin Control** |
| **Administrator** | `admin` | `admin123` | System Administrator |
| **Warehouse Manager** | `manager` | `manager123` | Master Data, GRN, Transfer, Dispatch, Returns, Adjustments, Reports & Exports |
| **Operations Staff** | `staff` | `staff123` | Daily Logistics: Barcode Scanner, Live Balances, GRN, Transfers, Dispatch |

*(Tip: On the Sign-In page, click any of the "Autofill Demo Credentials" pills for instant one-click login).*

---

## 🚀 Pushing Code to GitHub

The local Git repository is already initialized and all source code is committed to the `main` branch.

### Option 1: Using the Automated Batch Script
1. In the project folder, double-click **`push_to_github.bat`**.
2. Paste your GitHub repository URL (e.g. `https://github.com/Harishsiddgonda/RSR_SmartStock.git`).
3. Press Enter to push!

### Option 2: Using Terminal / Command Prompt
```bash
# 1. Add your GitHub remote repository
git remote add origin https://github.com/Harishsiddgonda/RSR_SmartStock.git

# 2. Push to main branch
git push -u origin main
```

---

## ☁️ Deploying to Render (Free Cloud Hosting)

The repository includes a ready-to-use **`render.yaml`** and **`Procfile`** for instant deployment on [Render](https://render.com).

### Step-by-Step Render Deployment:
1. Log in to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** and select **Web Service**.
3. Connect your GitHub account and select your **`RSR_SmartStock`** repository.
4. Render will auto-detect Python. Verify the following settings:
   - **Name:** `rsr-smartstock`
   - **Environment:** `Python`
   - **Region:** Any (e.g. Oregon or Singapore)
   - **Branch:** `main`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Plan:** Free
5. Click **Create Web Service**.
6. Render will install dependencies and start the app. Once finished, Render gives you a live public URL (e.g., `https://rsr-smartstock.onrender.com`)!

---

## 🖥 Local Startup (Windows)

1. Double-click **`run_windows.bat`** in the project folder.
2. The script checks Python, creates/activates `.venv`, installs requirements, opens your browser to `http://127.0.0.1:5000`, and launches the web application.

---

## 🧪 Automated Test Verification

Run the full end-to-end test suite:
```powershell
.\.venv\Scripts\python.exe test_app.py
```
Output:
```
Ran 10 tests in 2.38s
OK
```
All 10 test modules pass with 0 errors.

---
*Developed for RSR SmartStock Warehouse Control System.*
