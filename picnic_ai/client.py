import hashlib
import os
from pathlib import Path
from typing import Any

import httpx

from .errors import CheckoutError, Picnic2FAError, Picnic2FARequired, PicnicAuthError, PicnicError

AUTH_HEADER = "x-picnic-auth"
CLIENT_ID = 30100
AGENT_HEADERS = {
    "x-picnic-agent": "30100;1.15.183-14941;",
    "x-picnic-did": "00DE6414C744E7CB",
}
AUTH_ERROR_CODES = {"AUTH_ERROR", "AUTH_INVALID_CRED"}


class PicnicClient:
    def __init__(
        self,
        country_code: str = "NL",
        api_version: str = "15",
        auth_token: str | None = None,
        token_file: str | Path | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ):
        self.country_code = country_code.upper()
        self.base_url = (
            f"https://storefront-prod.{self.country_code.lower()}.picnicinternational.com"
            f"/api/{api_version}"
        )
        self._token = auth_token
        self._token_file = Path(token_file) if token_file else None
        if not self._token and self._token_file and self._token_file.exists():
            self._token = self._token_file.read_text(encoding="utf-8").strip() or None
        headers = {
            "User-Agent": "okhttp/3.9.0",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if self._token:
            headers[AUTH_HEADER] = self._token
        self._http = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout, transport=transport)

    @property
    def auth_token(self) -> str | None:
        return self._token

    def _update_token(self, token: str | None) -> None:
        if token and token != self._token:
            self._token = token
            self._http.headers[AUTH_HEADER] = token
            self._persist_token()

    def _persist_token(self) -> None:
        if self._token_file and self._token:
            self._token_file.write_text(self._token + "\n", encoding="utf-8")
            os.chmod(self._token_file, 0o600)

    def _request(self, method: str, path: str, payload: Any = None, agent: bool = False) -> Any:
        headers = dict(AGENT_HEADERS) if agent else None
        response = self._http.request(method, path, json=payload, headers=headers)
        self._update_token(response.headers.get(AUTH_HEADER))
        body: Any = {}
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = {}
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict) and error.get("code") in AUTH_ERROR_CODES:
            raise PicnicAuthError(error.get("message", "Picnic-authenticatie mislukt"), code=error.get("code"))
        if response.status_code == 401:
            raise PicnicAuthError("Niet geauthenticeerd bij Picnic (401)", code="AUTH_ERROR")
        if response.status_code >= 400:
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else (response.text or None)
            raise PicnicError(message or f"Picnic API-fout (HTTP {response.status_code})", code=code)
        return body

    def login(self, email: str | None = None, password: str | None = None) -> Any:
        email = email or os.environ.get("PICNIC_EMAIL")
        password = password or os.environ.get("PICNIC_PASSWORD")
        if not email or not password:
            raise PicnicAuthError("Stel PICNIC_EMAIL en PICNIC_PASSWORD in om in te loggen")
        secret = hashlib.md5(password.encode("utf-8")).hexdigest()
        payload = {"key": email, "secret": secret, "client_id": CLIENT_ID}
        response = self._http.post("/user/login", json=payload, headers=AGENT_HEADERS)
        self._update_token(response.headers.get(AUTH_HEADER))
        body: Any = {}
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = {}
        if isinstance(body, dict) and body.get("second_factor_authentication_required") is True:
            message = body.get("error", {}).get("message", "Tweestapsverificatie (2FA) vereist")
            raise Picnic2FARequired(message, code="2FA_REQUIRED")
        error = body.get("error") if isinstance(body, dict) else None
        if response.status_code >= 400 or (isinstance(error, dict) and error.get("code") in AUTH_ERROR_CODES):
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else (response.text or None)
            raise PicnicAuthError(message or f"Inloggen mislukt (HTTP {response.status_code})", code=code)
        return body

    def generate_2fa_code(self, channel: str = "SMS") -> Any:
        try:
            return self._request("POST", "/user/2fa/generate", {"channel": channel.upper()}, agent=True)
        except PicnicError as exc:
            raise Picnic2FAError(str(exc), code=exc.code) from exc

    def verify_2fa_code(self, code: str) -> Any:
        try:
            return self._request("POST", "/user/2fa/verify", {"otp": code}, agent=True)
        except PicnicError as exc:
            raise Picnic2FAError(str(exc), code=exc.code) from exc

    def logout(self) -> None:
        self._request("POST", "/user/logout", agent=True)
        self._token = None
        self._http.headers.pop(AUTH_HEADER, None)
        if self._token_file and self._token_file.exists():
            self._token_file.unlink()

    def ensure_authenticated(self) -> None:
        if not self._token:
            self.login()

    def get_user(self) -> Any:
        return self._request("GET", "/user", agent=True)

    def search(self, term: str) -> Any:
        from urllib.parse import quote

        return self._request("GET", f"/search?search_term={quote(term)}", agent=True)

    def get_article(self, article_id: str) -> Any:
        return self._request("GET", f"/articles/{article_id}", agent=True)

    def get_cart(self) -> Any:
        return self._request("GET", "/cart", agent=True)

    def add_product(self, product_id: str, count: int = 1) -> Any:
        return self._request("POST", "/cart/add_product", {"product_id": str(product_id), "count": count}, agent=True)

    def remove_product(self, product_id: str, count: int = 1) -> Any:
        return self._request("POST", "/cart/remove_product", {"product_id": str(product_id), "count": count}, agent=True)

    def clear_cart(self) -> Any:
        return self._request("POST", "/cart/clear", agent=True)

    def get_delivery_slots(self) -> Any:
        return self._request("GET", "/cart/delivery_slots", agent=True)

    def set_delivery_slot(self, slot_id: str) -> Any:
        return self._request("POST", "/cart/set_delivery_slot", {"slot_id": slot_id}, agent=True)

    def start_checkout(self) -> Any:
        cart = self.get_cart()
        mts = cart.get("mts", 0) if isinstance(cart, dict) else 0
        try:
            return self._request("POST", "/cart/checkout/start", {"mts": mts}, agent=True)
        except PicnicError as exc:
            if exc.code and str(exc.code).startswith("CART"):
                raise CheckoutError(str(exc), code=exc.code) from exc
            raise

    def get_checkout_status(self, transaction_id: str) -> Any:
        return self._request("GET", f"/cart/checkout/{transaction_id}/status", agent=True)

    def cancel_checkout(self, transaction_id: str) -> Any:
        return self._request("POST", "/cart/checkout/cancel", {"transaction_id": transaction_id}, agent=True)

    def get_current_deliveries(self) -> Any:
        return self._request("POST", "/deliveries/summary", ["CURRENT"], agent=True)

    def get_delivery(self, delivery_id: str) -> Any:
        return self._request("GET", f"/deliveries/{delivery_id}", agent=True)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "PicnicClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
