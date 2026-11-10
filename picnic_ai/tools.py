import re
from typing import Any

from .client import PicnicClient
from .errors import PicnicError

PRODUCT_TYPES = {"SINGLE_ARTICLE", "MULTI_ARTICLE"}


def format_eur(cents: int | None) -> str | None:
    if cents is None:
        return None
    return f"€ {cents / 100:.2f}".replace(".", ",")


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _score(query: str, name: str) -> float:
    q_tokens = set(_normalize(query).split())
    n_text = _normalize(name)
    n_tokens = set(n_text.split())
    if not q_tokens or not n_tokens:
        return 0.0
    score = len(q_tokens & n_tokens) / len(q_tokens)
    if _normalize(query) in n_text:
        score += 0.5
    if n_text.startswith(_normalize(query)):
        score += 0.25
    return score


def _product_from_item(item: dict) -> dict:
    price = item.get("display_price", item.get("price"))
    return {
        "id": str(item.get("id")),
        "name": item.get("name"),
        "price_cents": price,
        "price_eur": format_eur(price),
        "unit": item.get("unit_quantity"),
        "unit_price": item.get("unit_quantity_sub"),
        "max_count": item.get("max_count"),
    }


def search_products(client: PicnicClient, query: str, limit: int = 8) -> list[dict]:
    results = client.search(query)
    products: list[dict] = []
    for group in results or []:
        for item in group.get("items", []):
            if item.get("type") in PRODUCT_TYPES:
                products.append(_product_from_item(item))
    return products[:limit]


def resolve_product(client: PicnicClient, query: str, limit: int = 10) -> dict:
    results = client.search(query)
    scored: list[tuple[float, dict]] = []
    for group in results or []:
        for item in group.get("items", []):
            if item.get("type") in PRODUCT_TYPES:
                product = _product_from_item(item)
                scored.append((_score(query, product.get("name") or ""), product))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    candidates = [product for _, product in scored[:3]]
    chosen = None
    if scored:
        best_score, best = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if best_score >= 0.5 and best_score - second_score >= 0.15:
            chosen = best
        elif len(scored) == 1 and best_score >= 0.3:
            chosen = best
    return {"query": query, "chosen": chosen, "candidates": candidates}


def add_to_cart(client: PicnicClient, query: str, count: int = 1) -> dict:
    resolved = resolve_product(client, query)
    chosen = resolved["chosen"]
    if chosen is None:
        return {"status": "ambiguous", "query": query, "candidates": resolved["candidates"]}
    cart = client.add_product(chosen["id"], count)
    return {"status": "added", "product": chosen, "count": count, "cart": summarize_cart(cart)}


def add_products(client: PicnicClient, items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        query = str(item.get("query", "")).strip()
        count = int(item.get("count", 1))
        if not query:
            results.append({"status": "skipped", "reason": "leeg query"})
            continue
        results.append(add_to_cart(client, query, count))
    return results


def _line_count(line: dict) -> int:
    for decorator in line.get("decorators", []):
        if decorator.get("type") == "QUANTITY":
            return int(decorator.get("quantity", 0))
    articles = line.get("items") or []
    return int(articles[0].get("count", 0)) if articles else 0


def summarize_cart(cart: dict) -> dict:
    items = []
    for line in cart.get("items", []):
        articles = line.get("items") or []
        first = articles[0] if articles else {}
        line_total = line.get("display_price", line.get("price"))
        items.append(
            {
                "product_id": str(line.get("id")),
                "name": first.get("name"),
                "count": _line_count(line),
                "unit": first.get("unit_quantity"),
                "line_total_cents": line_total,
                "line_total_eur": format_eur(line_total),
            }
        )
    total = cart.get("checkout_total_price", cart.get("total_price"))
    return {
        "items": items,
        "total_count": cart.get("total_count"),
        "total_cents": total,
        "total_eur": format_eur(total),
        "total_savings_eur": format_eur(cart.get("total_savings")),
        "total_deposit_eur": format_eur(cart.get("total_deposit")),
        "status": cart.get("status"),
        "selected_slot": cart.get("selected_slot"),
    }


def get_cart(client: PicnicClient) -> dict:
    return summarize_cart(client.get_cart())


def remove_from_cart(client: PicnicClient, product_id: str, count: int = 1) -> dict:
    return summarize_cart(client.remove_product(product_id, count))


def clear_cart(client: PicnicClient) -> dict:
    return summarize_cart(client.clear_cart())


def list_delivery_slots(client: PicnicClient) -> dict:
    data = client.get_delivery_slots()
    slots = []
    for slot in data.get("delivery_slots", []):
        slots.append(
            {
                "slot_id": slot.get("slot_id"),
                "window_start": slot.get("window_start"),
                "window_end": slot.get("window_end"),
                "available": slot.get("is_available"),
                "selected": slot.get("selected"),
                "reserved": slot.get("reserved"),
                "minimum_order_value_eur": format_eur(slot.get("minimum_order_value")),
                "unavailability_reason": slot.get("unavailability_reason"),
            }
        )
    return {"slots": slots, "selected_slot": data.get("selected_slot")}


def select_delivery_slot(client: PicnicClient, slot_id: str) -> dict:
    return summarize_cart(client.set_delivery_slot(slot_id))


def start_checkout(client: PicnicClient, confirm: bool = False) -> dict:
    if not confirm:
        raise PicnicError(
            "Bevestiging vereist: roep start_checkout aan met confirm=true nadat de gebruiker expliciet akkoord heeft gegeven.",
            code="CONFIRMATION_REQUIRED",
        )
    cart = client.get_cart()
    if not cart.get("items"):
        raise PicnicError("De winkelwagen is leeg; voeg eerst producten toe.", code="EMPTY_CART")
    checkout = client.start_checkout()
    return {
        "order_id": checkout.get("order_id"),
        "total_cents": checkout.get("total_price"),
        "total_eur": format_eur(checkout.get("total_price")),
        "total_count": checkout.get("total_count"),
        "total_deposit_eur": format_eur(checkout.get("total_deposit")),
        "transaction_expiry": checkout.get("transaction_expiry"),
        "note": (
            "Checkout gestart. Rond de betaling af in de Picnic-app (iDEAL/wallet) om de bestelling definitief te maken."
        ),
    }


def get_checkout_status(client: PicnicClient, transaction_id: str) -> dict:
    return client.get_checkout_status(transaction_id)


def list_orders(client: PicnicClient) -> list[dict]:
    deliveries = client.get_current_deliveries()
    orders = []
    for delivery in deliveries or []:
        if not isinstance(delivery, dict):
            continue
        orders.append(
            {
                "delivery_id": delivery.get("id") or delivery.get("delivery_id"),
                "status": delivery.get("status"),
                "window_start": delivery.get("window_start"),
                "window_end": delivery.get("window_end"),
                "total_price_eur": format_eur(delivery.get("total_price")),
                "total_count": delivery.get("total_count"),
            }
        )
    return orders
