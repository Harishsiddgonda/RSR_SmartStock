from __future__ import annotations

import os
import time
import unittest
from app import app
import db as database


class RSRSmartStockComprehensiveTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        database.init_db()

    def login(self, username="harish", password="harish123"):
        return self.client.post(
            "/login",
            data={"username": username, "password": password, "remember": "1"},
            follow_redirects=True,
        )

    def logout(self):
        return self.client.get("/logout", follow_redirects=True)

    # 1. Authentication Tests
    def test_01_authentication_flows(self):
        # Invalid login
        res = self.client.post("/login", data={"username": "wrong", "password": "bad"}, follow_redirects=True)
        self.assertIn(b"Invalid username or password", res.data)

        # Valid Harish Login
        res_admin = self.login("harish", "harish123")
        self.assertIn(b"Welcome back", res_admin.data)
        self.assertIn(b"Dashboard", res_admin.data)

        # Logout
        res_logout = self.logout()
        self.assertIn(b"signed out successfully", res_logout.data)

        # Valid Manager Login
        res_mgr = self.login("manager", "manager123")
        self.assertIn(b"Welcome back", res_mgr.data)
        self.logout()

        # Valid Staff Login
        res_staff = self.login("staff", "staff123")
        self.assertIn(b"Welcome back", res_staff.data)
        self.logout()

    # 2. Role-Based Access Control
    def test_02_rbac_restrictions(self):
        self.login("staff", "staff123")
        res_users = self.client.get("/users", follow_redirects=True)
        self.assertIn(b"Access restricted", res_users.data)

        res_settings = self.client.get("/settings", follow_redirects=True)
        self.assertIn(b"Access restricted", res_settings.data)
        self.logout()

        self.login("harish", "harish123")
        res_users = self.client.get("/users", follow_redirects=True)
        self.assertEqual(res_users.status_code, 200)
        self.assertIn(b"User & Role Management", res_users.data)
        self.logout()

    # 3. Dashboard & Chart APIs
    def test_03_dashboard_and_api(self):
        self.login("harish", "harish123")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Total Active SKUs", res.data)
        self.assertIn(b"Total Stock Units", res.data)
        self.assertIn(b"Asset Valuation", res.data)

        chart_res = self.client.get("/api/chart-data")
        self.assertEqual(chart_res.status_code, 200)
        json_data = chart_res.get_json()
        self.assertIn("categories", json_data)
        self.assertIn("trends", json_data)
        self.logout()

    # 4. Products & Inventory CRUD
    def test_04_product_management(self):
        self.login("harish", "harish123")
        res = self.client.get("/inventory")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Products & Inventory", res.data)

        ts = int(time.time())
        test_sku = f"TEST-{ts}"
        res_add = self.client.post(
            "/inventory",
            data={
                "name": f"Test Product {ts}",
                "sku": test_sku,
                "barcode": f"890{ts}",
                "unit": "pcs",
                "cost_price": "150.00",
                "selling_price": "299.00",
                "reorder_level": "10",
                "opening_qty": "50",
                "warehouse_id": "1",
                "description": "Automated unit test product",
            },
            follow_redirects=True,
        )
        self.assertIn(b"added successfully", res_add.data)

        lookup = self.client.get(f"/api/product-lookup?code={test_sku}")
        self.assertEqual(lookup.status_code, 200)
        lookup_data = lookup.get_json()
        self.assertEqual(lookup_data["sku"], test_sku)
        prod_id = lookup_data["id"]

        res_edit = self.client.post(
            f"/products/{prod_id}/edit",
            data={
                "name": f"Test Product {ts} (Updated)",
                "sku": test_sku,
                "barcode": f"890{ts}",
                "unit": "pcs",
                "cost_price": "160.00",
                "selling_price": "310.00",
                "reorder_level": "12",
                "description": "Updated description",
            },
            follow_redirects=True,
        )
        self.assertIn(b"updated successfully", res_edit.data)
        self.logout()

    # 5. Categories Management
    def test_05_category_management(self):
        self.login("harish", "harish123")
        ts = int(time.time())
        cat_code = f"CAT-{ts}"
        res_add = self.client.post(
            "/categories",
            data={
                "name": f"Category {ts}",
                "code": cat_code,
                "description": "Testing category",
            },
            follow_redirects=True,
        )
        self.assertIn(b"created successfully", res_add.data)
        self.logout()

    # 6. Suppliers & Customers
    def test_06_suppliers_and_customers(self):
        self.login("harish", "harish123")
        ts = int(time.time())
        res_sup = self.client.post(
            "/suppliers",
            data={
                "name": f"Supplier {ts}",
                "code": f"SUP-{ts}",
                "contact_person": "Robert Tester",
                "email": f"sup_{ts}@test.com",
                "phone": "+91 99000 11111",
                "address": "Peenya, BLR",
            },
            follow_redirects=True,
        )
        self.assertIn(b"registered successfully", res_sup.data)

        res_cust = self.client.post(
            "/customers",
            data={
                "name": f"Customer {ts}",
                "code": f"CUST-{ts}",
                "contact_person": "Sara Buyer",
                "email": f"cust_{ts}@test.com",
                "phone": "+91 98000 22222",
                "address": "Indiranagar, BLR",
            },
            follow_redirects=True,
        )
        self.assertIn(b"registered successfully", res_cust.data)
        self.logout()

    # 7. Warehouses
    def test_07_warehouse_management(self):
        self.login("harish", "harish123")
        ts = int(time.time())
        res_wh = self.client.post(
            "/warehouses",
            data={
                "name": f"Warehouse {ts}",
                "code": f"WH-{ts}",
                "location": "Whitefield, Bengaluru",
                "capacity": "18000",
            },
            follow_redirects=True,
        )
        self.assertIn(b"added successfully", res_wh.data)

        res_detail = self.client.get("/warehouses/1/stock")
        self.assertEqual(res_detail.status_code, 200)
        self.assertIn(b"Stored Products", res_detail.data)
        self.logout()

    # 8. Operations: GRN, Transfer, Dispatch
    def test_08_operations_and_stock_validation(self):
        self.login("staff", "staff123")
        res_grn = self.client.post(
            "/grn",
            data={
                "product_id": "1",
                "warehouse_id": "1",
                "quantity": "20",
                "supplier_id": "1",
                "unit_price": "450.00",
                "po_ref": "PO-UNIT-01",
                "remarks": "Unit test receipt",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Goods received successfully", res_grn.data)

        res_trf = self.client.post(
            "/transfer",
            data={
                "product_id": "1",
                "from_warehouse_id": "1",
                "to_warehouse_id": "2",
                "quantity": "5",
                "remarks": "Unit test transfer",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Stock transfer completed", res_trf.data)

        res_fail = self.client.post(
            "/transfer",
            data={
                "product_id": "1",
                "from_warehouse_id": "1",
                "to_warehouse_id": "2",
                "quantity": "999999",
                "remarks": "Should fail",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Insufficient stock", res_fail.data)

        res_dsp = self.client.post(
            "/dispatch",
            data={
                "product_id": "1",
                "warehouse_id": "1",
                "quantity": "4",
                "customer_id": "1",
                "unit_price": "799.00",
                "invoice_ref": "INV-UNIT-01",
                "remarks": "Unit test dispatch",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Dispatch recorded successfully", res_dsp.data)
        self.logout()

    # 9. Returns & Adjustments
    def test_09_returns_and_adjustments(self):
        self.login("manager", "manager123")
        res_ret = self.client.post(
            "/returns",
            data={
                "return_type": "customer",
                "product_id": "1",
                "warehouse_id": "1",
                "quantity": "2",
                "party_id": "1",
                "reason": "Customer exchange",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Customer return recorded", res_ret.data)

        res_adj = self.client.post(
            "/adjustments",
            data={
                "adj_type": "ADD",
                "product_id": "1",
                "warehouse_id": "1",
                "quantity": "3",
                "reason_category": "Physical Cycle Count Correction",
                "notes": "Verified count discrepancy",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Stock adjusted", res_adj.data)
        self.logout()

    # 10. Reports & Excel Exports
    def test_10_reports_and_exports(self):
        self.login("harish", "harish123")
        res_val = self.client.get("/reports?tab=valuation")
        self.assertEqual(res_val.status_code, 200)
        self.assertIn(b"TOTAL COST VALUATION", res_val.data)

        res_xlsx = self.client.get("/reports/export/excel?type=valuation")
        self.assertEqual(res_xlsx.status_code, 200)
        self.assertEqual(
            res_xlsx.headers.get("Content-Type"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(len(res_xlsx.data) > 1000)

        res_csv = self.client.get("/reports/export/csv?type=valuation")
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn(b"Product Name,SKU,Barcode", res_csv.data)
        self.logout()


if __name__ == "__main__":
    unittest.main()
