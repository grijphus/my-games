import argparse
import json
import sys
from typing import Any

from . import tools
from .client import PicnicClient
from .config import from_env
from .errors import Picnic2FARequired, PicnicError


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _client(settings, authenticate: bool = True) -> PicnicClient:
    client = PicnicClient(
        country_code=settings.country_code,
        api_version=settings.api_version,
        auth_token=settings.auth_token,
        token_file=settings.token_file,
    )
    if authenticate:
        client.ensure_authenticated()
    return client


def _cmd_login(args) -> int:
    settings = from_env()
    client = _client(settings, authenticate=False)
    try:
        client.login(args.email, args.password)
    except Picnic2FARequired as exc:
        print(f"2FA vereist: {exc}")
        channel = args.channel or input("Verstuur code via (SMS/EMAIL) [SMS]: ").strip().upper() or "SMS"
        client.generate_2fa_code(channel)
        print(f"Code verstuurd via {channel}.")
        code = args.code or input("Voer de ontvangen code in: ").strip()
        client.verify_2fa_code(code)
    if client.auth_token:
        print("Ingelogd; token opgeslagen.")
        return 0
    print("Inloggen mislukt.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="picnic", description="Picnic boodschappen doen via CLI of AI (MCP).")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="Log in bij Picnic (afhandelen incl. 2FA) en sla het token op")
    p.add_argument("--email")
    p.add_argument("--password")
    p.add_argument("--channel", choices=["SMS", "EMAIL"])
    p.add_argument("--code")
    p.set_defaults(func=_cmd_login)

    p = sub.add_parser("user", help="Toon de ingelogde gebruiker")
    p.set_defaults(func=lambda a: _print(_client(from_env()).get_user()))

    p = sub.add_parser("search", help="Zoek producten")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=lambda a: _print(tools.search_products(_client(from_env()), a.query, a.limit)))

    p = sub.add_parser("add", help="Voeg een product toe op zoekterm")
    p.add_argument("query")
    p.add_argument("count", type=int, nargs="?", default=1)
    p.set_defaults(func=lambda a: _print(tools.add_to_cart(_client(from_env()), a.query, a.count)))

    p = sub.add_parser("add-list", help='Voeg een JSON-lijst toe, bijv. \'[{"query": "melk", "count": 2}]\'')
    p.add_argument("items", help="JSON array van {query, count}")
    p.set_defaults(func=lambda a: _print(tools.add_products(_client(from_env()), json.loads(a.items))))

    p = sub.add_parser("cart", help="Toon de winkelwagen")
    p.set_defaults(func=lambda a: _print(tools.get_cart(_client(from_env()))))

    p = sub.add_parser("remove", help="Verwijder product uit winkelwagen")
    p.add_argument("product_id")
    p.add_argument("count", type=int, nargs="?", default=1)
    p.set_defaults(func=lambda a: _print(tools.remove_from_cart(_client(from_env()), a.product_id, a.count)))

    p = sub.add_parser("clear", help="Maak de winkelwagen leeg")
    p.set_defaults(func=lambda a: _print(tools.clear_cart(_client(from_env()))))

    p = sub.add_parser("slots", help="Toon beschikbare bezorgmomenten")
    p.set_defaults(func=lambda a: _print(tools.list_delivery_slots(_client(from_env()))))

    p = sub.add_parser("slot", help="Kies een bezorgmoment")
    p.add_argument("slot_id")
    p.set_defaults(func=lambda a: _print(tools.select_delivery_slot(_client(from_env()), a.slot_id)))

    p = sub.add_parser("checkout", help="Start de checkout (betaling afronden in de Picnic-app)")
    p.add_argument("--yes", action="store_true", help="Bevestig dat de bestelling geplaatst mag worden")
    p.set_defaults(func=lambda a: _print(tools.start_checkout(_client(from_env()), confirm=a.yes)))

    p = sub.add_parser("status", help="Checkout-status opvragen")
    p.add_argument("transaction_id")
    p.set_defaults(func=lambda a: _print(tools.get_checkout_status(_client(from_env()), a.transaction_id)))

    p = sub.add_parser("orders", help="Toon actuele bestellingen")
    p.set_defaults(func=lambda a: _print(tools.list_orders(_client(from_env()))))

    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except PicnicError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
