import argparse
import functools
import json
import os
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import tools
from .client import PicnicClient
from .config import from_env
from .errors import PicnicError

server = MCPServer(
    "picnic",
    instructions=(
        "Picnic-boodschappentools. Zoek producten, vul de winkelwagen, kies een bez moment en start de checkout. "
        "Vraag de gebruiker altijd om expliciete bevestiging voordat je start_checkout met confirm=true aanroept; "
        "betaling wordt afgerond in de Picnic-app."
    ),
)

_client: PicnicClient | None = None


def get_client() -> PicnicClient:
    global _client
    if _client is None:
        settings = from_env()
        _client = PicnicClient(
            country_code=settings.country_code,
            api_version=settings.api_version,
            auth_token=settings.auth_token,
            token_file=settings.token_file,
        )
        _client.ensure_authenticated()
    return _client


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _json_guard(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return _json(fn(*args, **kwargs))
        except PicnicError as exc:
            return _json({"error": str(exc), "code": exc.code})
        except Exception as exc:
            return _json({"error": f"{type(exc).__name__}: {exc}"})

    return wrapper


@server.tool(description="Geef de ingelogde Picnic-gebruiker terug (controleer of de sessie werkt).")
@_json_guard
def picnic_get_user() -> Any:
    return get_client().get_user()


@server.tool(description="Zoek producten in de Picnic-winkel. Geeft per product id, naam, prijs en eenheid terug.")
@_json_guard
def picnic_search_products(query: str, limit: int = 8) -> Any:
    return tools.search_products(get_client(), query, limit)


@server.tool(
    description=(
        "Voeg een product toe aan de winkelwagen op basis van een vrije zoekterm (bijv. 'volle melk 1L'). "
        "Als de zoekterm ondubbelzinnig is wordt het beste product toegevoegd; anders worden de beste 3 kandidaten teruggegeben."
    )
)
@_json_guard
def picnic_add_to_cart(query: str, count: int = 1) -> Any:
    return tools.add_to_cart(get_client(), query, count)


@server.tool(
    description=(
        "Voeg meerdere producten in een keer toe. items is een lijst van {\"query\": \"...\", \"count\": 2}. "
        " Elk item wordt omgezet naar een product via de zoekfunctie."
    )
)
@_json_guard
def picnic_add_products(items: list[dict[str, Any]]) -> Any:
    return tools.add_products(get_client(), items)


@server.tool(description="Toon de winkelwagen: producten, aantallen, prijzen, totaal en bezorgmoment.")
@_json_guard
def picnic_get_cart() -> Any:
    return tools.get_cart(get_client())


@server.tool(description="Verwijder een product (op product_id) uit de winkelwagen.")
@_json_guard
def picnic_remove_from_cart(product_id: str, count: int = 1) -> Any:
    return tools.remove_from_cart(get_client(), product_id, count)


@server.tool(description="Maak de winkelwagen leeg.")
@_json_guard
def picnic_clear_cart() -> Any:
    return tools.clear_cart(get_client())


@server.tool(description="Toon beschikbare bezorgmomenten (delivery slots) voor de winkelwagen.")
@_json_guard
def picnic_get_delivery_slots() -> Any:
    return tools.list_delivery_slots(get_client())


@server.tool(description="Kies een bezorgmoment (slot_id) voor de winkelwagen.")
@_json_guard
def picnic_select_delivery_slot(slot_id: str) -> Any:
    return tools.select_delivery_slot(get_client(), slot_id)


@server.tool(
    description=(
        "Start de checkout van de winkelwagen. Vereist confirm=true; vraag de gebruiker DAAROM altijd eerst expliciet om toestemming. "
        "De betaling zelf wordt afgerond in de Picnic-app."
    )
)
@_json_guard
def picnic_start_checkout(confirm: bool = False) -> Any:
    return tools.start_checkout(get_client(), confirm)


@server.tool(description="Controleer de status van een lopende checkout (transaction_id/order_id).")
@_json_guard
def picnic_get_checkout_status(transaction_id: str) -> Any:
    return tools.get_checkout_status(get_client(), transaction_id)


@server.tool(description="Toon de huidige/actuele bestellingen (leveringen).")
@_json_guard
def picnic_list_orders() -> Any:
    return tools.list_orders(get_client())


def main() -> None:
    parser = argparse.ArgumentParser(prog="picnic-mcp", description="Picnic MCP-server (stdio of streamable-http).")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.environ.get("PICNIC_MCP_TRANSPORT", "stdio"),
        help="stdio (default, voor lokale MCP-clients) of streamable-http (voor een connector via een URL)",
    )
    parser.add_argument("--host", default=os.environ.get("PICNIC_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PICNIC_MCP_PORT", "8000")))
    args = parser.parse_args()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port, streamable_http_path="/mcp")


if __name__ == "__main__":
    main()
