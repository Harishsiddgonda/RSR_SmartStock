import unittest
from app import app
import db as database

class TestAllRoutesAudit(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()

    def test_all_routes_render_cleanly(self):
        # 1. Login as admin
        login_resp = self.client.post("/login", data={
            "username": "harish",
            "password": "harish123",
            "remember": "1"
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        # 2. Check all GET routes
        routes = [
            "/",
            "/inventory",
            "/categories",
            "/suppliers",
            "/customers",
            "/warehouses",
            "/warehouses/1/stock",
            "/grn",
            "/transfer",
            "/dispatch",
            "/returns",
            "/adjustments",
            "/alerts",
            "/transactions",
            "/reports",
            "/reports?tab=movements",
            "/reports?tab=valuation",
            "/reports?tab=purchases",
            "/reports?tab=sales",
            "/users",
            "/settings",
            "/logs",
            "/profile",
            "/api/chart-data",
            "/reports/export/csv?tab=movements",
            "/reports/export/excel?tab=movements",
        ]

        for route in routes:
            with self.subTest(route=route):
                resp = self.client.get(route)
                self.assertNotEqual(
                    resp.status_code, 500,
                    f"Route {route} returned 500 Internal Server Error!"
                )
                self.assertIn(
                    resp.status_code, [200, 302],
                    f"Route {route} returned unexpected status code {resp.status_code}"
                )

    def test_error_handlers(self):
        # 404 test
        resp404 = self.client.get("/non-existent-page-xyz-12345")
        self.assertEqual(resp404.status_code, 404)
        self.assertIn(b"404", resp404.data)
        self.assertIn(b"Page Not Found", resp404.data)

if __name__ == "__main__":
    unittest.main()
