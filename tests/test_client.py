import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from picnic_ai.client import PicnicClient
from picnic_ai.errors import CheckoutError, Picnic2FARequired, PicnicAuthError, PicnicError


def make_client(handler, token_file=None, **kwargs):
    kwargs.setdefault("auth_token", "tok-1")
    return PicnicClient(token_file=token_file, transport=httpx.MockTransport(handler), **kwargs)


class LoginTests(unittest.TestCase):
    def test_login_posts_credentials_and_stores_token_from_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / ".picnic_token"

            def handler(request: httpx.Request) -> httpx.Response:
                assert request.url.path == "/api/15/user/login"
                body = json.loads(request.content)
                assert body["key"] == "user@example.com"
                assert body["secret"] == hashlib.md5(b"wachtwoord").hexdigest()
                assert body["client_id"] == 30100
                return httpx.Response(200, json={"ok": True}, headers={"x-picnic-auth": "tok-2"})

            client = make_client(handler, token_file=token_file, auth_token=None)
            client.login("user@example.com", "wachtwoord")
            self.assertEqual(client.auth_token, "tok-2")
            self.assertEqual(token_file.read_text().strip(), "tok-2")

    def test_login_requires_credentials(self):
        client = make_client(lambda r: httpx.Response(200, json={}), auth_token=None)
        with self.assertRaises(PicnicAuthError):
            client.login()

    def test_login_2fa_required(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"second_factor_authentication_required": True, "error": {"message": "2FA nodig"}},
            )

        client = make_client(handler, auth_token=None)
        with self.assertRaises(Picnic2FARequired):
            client.login("user@example.com", "wachtwoord")

    def test_login_invalid_credentials(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"code": "AUTH_INVALID_CRED", "message": "Onjuist wachtwoord"}})

        client = make_client(handler, auth_token=None)
        with self.assertRaises(PicnicAuthError):
            client.login("user@example.com", "fout")

    def test_2fa_generate_and_verify_payloads(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.url.path, json.loads(request.content)))
            return httpx.Response(204)

        client = make_client(handler)
        client.generate_2fa_code("sms")
        client.verify_2fa_code("123456")
        self.assertEqual(seen[0], ("/api/15/user/2fa/generate", {"channel": "SMS"}))
        self.assertEqual(seen[1], ("/api/15/user/2fa/verify", {"otp": "123456"}))


class RequestTests(unittest.TestCase):
    def test_token_refreshed_from_response_header(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True}, headers={"x-picnic-auth": "tok-9"})

        client = make_client(handler)
        client.get_user()
        self.assertEqual(client.auth_token, "tok-9")

    def test_auth_error_code_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"code": "AUTH_ERROR", "message": "sessie verlopen"}})

        client = make_client(handler)
        with self.assertRaises(PicnicAuthError):
            client.get_cart()

    def test_http_error_raises_picnic_error_with_code(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"code": "SOME_ERROR", "message": "foute invoer"}})

        client = make_client(handler)
        with self.assertRaises(PicnicError) as ctx:
            client.get_cart()
        self.assertEqual(ctx.exception.code, "SOME_ERROR")
        self.assertIn("foute invoer", str(ctx.exception))

    def test_search_url_encodes_term(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/15/search"
            assert request.url.params["search_term"] == "volle melk & hagelslag"
            return httpx.Response(200, json=[])

        client = make_client(handler)
        self.assertEqual(client.search("volle melk & hagelslag"), [])

    def test_cart_mutations_send_product_payload(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
            return httpx.Response(200, json={"items": []})

        client = make_client(handler)
        client.add_product("10511523", 2)
        client.remove_product("10511523", 1)
        client.clear_cart()
        client.set_delivery_slot("slot-1")
        self.assertEqual(seen[0], ("POST", "/api/15/cart/add_product", {"product_id": "10511523", "count": 2}))
        self.assertEqual(seen[1], ("POST", "/api/15/cart/remove_product", {"product_id": "10511523", "count": 1}))
        self.assertEqual(seen[2], ("POST", "/api/15/cart/clear", None))
        self.assertEqual(seen[3], ("POST", "/api/15/cart/set_delivery_slot", {"slot_id": "slot-1"}))

    def test_start_checkout_sends_cart_mts(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/15/cart":
                return httpx.Response(200, json={"mts": 42, "items": [{"id": "1"}]})
            seen.append(json.loads(request.content))
            return httpx.Response(200, json={"order_id": "order-1", "total_price": 1234})

        client = make_client(handler)
        result = client.start_checkout()
        self.assertEqual(seen, [{"mts": 42}])
        self.assertEqual(result["order_id"], "order-1")

    def test_start_checkout_cart_error_becomes_checkout_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/15/cart":
                return httpx.Response(200, json={"mts": 42, "items": [{"id": "1"}]})
            return httpx.Response(400, json={"error": {"code": "CART_ALCOHOL_AGE_CHECK", "message": "18+ vereist"}})

        client = make_client(handler)
        with self.assertRaises(CheckoutError) as ctx:
            client.start_checkout()
        self.assertEqual(ctx.exception.code, "CART_ALCOHOL_AGE_CHECK")

    def test_checkout_status_and_cancel(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
            if request.url.path.endswith("/status"):
                return httpx.Response(200, json={"checkout_status": "PAID"})
            return httpx.Response(200, json={})

        client = make_client(handler)
        self.assertEqual(client.get_checkout_status("tx-1"), {"checkout_status": "PAID"})
        client.cancel_checkout("tx-1")
        self.assertEqual(seen[0], ("GET", "/api/15/cart/checkout/tx-1/status", None))
        self.assertEqual(seen[1], ("POST", "/api/15/cart/checkout/cancel", {"transaction_id": "tx-1"}))


if __name__ == "__main__":
    unittest.main()
