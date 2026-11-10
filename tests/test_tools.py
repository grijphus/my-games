import json
import unittest

import httpx

from picnic_ai import tools
from picnic_ai.client import PicnicClient
from picnic_ai.errors import PicnicError

SEARCH_RESPONSE = [
    {
        "type": "CATEGORY",
        "id": "melk",
        "name": "Melk",
        "items": [
            {
                "type": "SINGLE_ARTICLE",
                "id": "1001",
                "name": "Volle melk 1L",
                "display_price": 129,
                "price": 129,
                "unit_quantity": "1 liter",
                "unit_quantity_sub": "€1,29/l",
                "max_count": 20,
            },
            {
                "type": "SINGLE_ARTICLE",
                "id": "1002",
                "name": "Halfvolle melk 1L",
                "display_price": 119,
                "price": 119,
                "unit_quantity": "1 liter",
            },
            {
                "type": "SINGLE_ARTICLE",
                "id": "1003",
                "name": "Melkchocolade 200g",
                "display_price": 249,
                "price": 249,
                "unit_quantity": "200 gram",
            },
        ],
    }
]

CART_RESPONSE = {
    "type": "ORDER",
    "id": "shopping_cart",
    "items": [
        {
            "type": "ORDER_LINE",
            "id": "1001",
            "display_price": 258,
            "price": 258,
            "decorators": [{"type": "QUANTITY", "quantity": 2}],
            "items": [{"type": "ARTICLE", "id": "1001", "name": "Volle melk 1L", "unit_quantity": "1 liter"}],
        }
    ],
    "total_count": 2,
    "total_price": 258,
    "checkout_total_price": 258,
    "mts": 7,
    "total_savings": 10,
    "total_deposit": 50,
    "status": "OPEN",
    "selected_slot": {"slot_id": "slot-1"},
}

SLOTS_RESPONSE = {
    "delivery_slots": [
        {
            "slot_id": "slot-1",
            "window_start": "2026-01-01T18:00:00Z",
            "window_end": "2026-01-01T19:00:00Z",
            "is_available": True,
            "selected": True,
            "reserved": False,
            "minimum_order_value": 3500,
            "unavailability_reason": None,
        },
        {
            "slot_id": "slot-2",
            "window_start": "2026-01-01T19:00:00Z",
            "window_end": "2026-01-01T20:00:00Z",
            "is_available": False,
            "selected": False,
            "reserved": False,
            "minimum_order_value": 3500,
            "unavailability_reason": "VOL",
        },
    ],
    "selected_slot": {"slot_id": "slot-1"},
}


def make_client(handler):
    return PicnicClient(auth_token="tok", transport=httpx.MockTransport(handler))


def search_then_cart_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/15/search":
        return httpx.Response(200, json=SEARCH_RESPONSE)
    if request.url.path == "/api/15/cart/add_product":
        return httpx.Response(200, json=CART_RESPONSE)
    if request.url.path == "/api/15/cart":
        return httpx.Response(200, json=CART_RESPONSE)
    if request.url.path == "/api/15/cart/delivery_slots":
        return httpx.Response(200, json=SLOTS_RESPONSE)
    if request.url.path == "/api/15/cart/checkout/start":
        return httpx.Response(200, json={"order_id": "order-1", "total_price": 258, "total_count": 2, "transaction_expiry": "2026-01-01T19:00:00Z"})
    return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": request.url.path}})


class FormatTests(unittest.TestCase):
    def test_format_eur(self):
        self.assertEqual(tools.format_eur(1234), "€ 12,34")
        self.assertEqual(tools.format_eur(0), "€ 0,00")
        self.assertIsNone(tools.format_eur(None))


class ResolveTests(unittest.TestCase):
    def test_resolve_picks_best_match(self):
        client = make_client(search_then_cart_handler)
        resolved = tools.resolve_product(client, "volle melk 1L")
        self.assertIsNotNone(resolved["chosen"])
        self.assertEqual(resolved["chosen"]["id"], "1001")

    def test_resolve_ambiguous_returns_candidates(self):
        client = make_client(search_then_cart_handler)
        resolved = tools.resolve_product(client, "melk")
        self.assertIsNone(resolved["chosen"])
        self.assertTrue(resolved["candidates"])


class CartFlowTests(unittest.TestCase):
    def test_add_to_cart_adds_resolved_product(self):
        client = make_client(search_then_cart_handler)
        result = tools.add_to_cart(client, "volle melk 1L", 2)
        self.assertEqual(result["status"], "added")
        self.assertEqual(result["product"]["id"], "1001")
        self.assertEqual(result["cart"]["total_eur"], "€ 2,58")

    def test_add_to_cart_ambiguous(self):
        client = make_client(search_then_cart_handler)
        result = tools.add_to_cart(client, "melk")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len(result["candidates"]), 3)

    def test_summarize_cart(self):
        summary = tools.summarize_cart(CART_RESPONSE)
        self.assertEqual(summary["items"][0]["name"], "Volle melk 1L")
        self.assertEqual(summary["items"][0]["count"], 2)
        self.assertEqual(summary["items"][0]["line_total_eur"], "€ 2,58")
        self.assertEqual(summary["total_eur"], "€ 2,58")
        self.assertEqual(summary["total_savings_eur"], "€ 0,10")
        self.assertEqual(summary["total_deposit_eur"], "€ 0,50")

    def test_list_delivery_slots(self):
        client = make_client(search_then_cart_handler)
        data = tools.list_delivery_slots(client)
        self.assertEqual(len(data["slots"]), 2)
        self.assertEqual(data["slots"][0]["slot_id"], "slot-1")
        self.assertEqual(data["slots"][0]["minimum_order_value_eur"], "€ 35,00")
        self.assertFalse(data["slots"][1]["available"])

    def test_start_checkout_requires_confirm(self):
        client = make_client(search_then_cart_handler)
        with self.assertRaises(PicnicError) as ctx:
            tools.start_checkout(client, confirm=False)
        self.assertEqual(ctx.exception.code, "CONFIRMATION_REQUIRED")

    def test_start_checkout_empty_cart(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": [], "mts": 1})

        client = make_client(handler)
        with self.assertRaises(PicnicError) as ctx:
            tools.start_checkout(client, confirm=True)
        self.assertEqual(ctx.exception.code, "EMPTY_CART")

    def test_start_checkout_ok(self):
        client = make_client(search_then_cart_handler)
        result = tools.start_checkout(client, confirm=True)
        self.assertEqual(result["order_id"], "order-1")
        self.assertEqual(result["total_eur"], "€ 2,58")
        self.assertIn("Picnic-app", result["note"])

    def test_add_products_bulk(self):
        client = make_client(search_then_cart_handler)
        results = tools.add_products(client, [{"query": "volle melk", "count": 2}, {"count": 1}])
        self.assertEqual(results[0]["status"], "added")
        self.assertEqual(results[1]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
