# my-games — Picnic AI-integratie

Boodschappen doen bij [Picnic](https://picnic.app) met AI. Deze repo bevat een Python-package (`picnic_ai`) met:

- een client voor de (onofficiële) Picnic-app-API: inloggen incl. 2FA, zoeken, winkelwagen, bezorgmomenten, checkout en bestellingen;
- een **MCP-server** (`picnic-mcp`) waarmee een AI-assistent (Le Chat, Claude Desktop, etc.) direct boodschappen kan doen;
- een **CLI** (`picnic`) om hetzelfde vanaf de command line te doen.

## Installatie

```bash
pip install -r requirements.txt
pip install -e .   # installeert de commando's `picnic` en `picnic-mcp`
```

## Configuratie

Zet je gegevens in de environment of in een `.env`-bestand (wordt niet gecommit, zie `.gitignore`):

```bash
PICNIC_EMAIL=jouw@email.nl
PICNIC_PASSWORD=jouw_wachtwoord
PICNIC_COUNTRY_CODE=NL        # NL (default), DE of FR
PICNIC_TOKEN_FILE=.picnic_token  # default; bewaar hier het sessietoken
# of gebruik direct een bestaand sessietoken:
# PICNIC_AUTH_TOKEN=...
```

Eerste keer inloggen (sessietoken wordt opgeslagen in `.picnic_token`):

```bash
picnic login
# bij 2FA: kies SMS/EMAIL en voer de ontvangen code in
```

## CLI-gebruik

```bash
picnic search "volle melk 1L"
picnic add "volle melk 1L" 2            # voeg 2x toe op zoekterm
picnic add-list '[{"query": "eieren", "count": 1}, {"query": "brood"}]'
picnic cart                              # winkelwagen met totaal
picnic slots                             # beschikbare bezorgmomenten
picnic slot <slot_id>                    # kies een moment
picnic checkout --yes                    # start checkout (betaling in de Picnic-app afronden)
picnic status <transaction_id>           # checkout-status
picnic orders                            # actuele bestellingen
picnic remove <product_id> [aantal]
picnic clear
```

## AI koppelen via MCP

Voeg de server toe aan je MCP-client, bijvoorbeeld:

```json
{
  "mcpServers": {
    "picnic": {
      "command": "picnic-mcp",
      "env": {
        "PICNIC_EMAIL": "jouw@email.nl",
        "PICNIC_PASSWORD": "jouw_wachtwoord"
      }
    }
  }
}
```

Daarna kun je tegen je AI-assistent zeggen: *"Zoek in Picnic naar havermelk, voeg 2 pakken toe aan mijn winkelwagen, kies het eerstvolgende bezorgmoment en start de checkout."*

Beschikbare tools: `picnic_get_user`, `picnic_search_products`, `picnic_add_to_cart`, `picnic_add_products`, `picnic_get_cart`, `picnic_remove_from_cart`, `picnic_clear_cart`, `picnic_get_delivery_slots`, `picnic_select_delivery_slot`, `picnic_start_checkout`, `picnic_get_checkout_status`, `picnic_list_orders`.

## Gebruiken als connector (Mistral Studio / Le Chat)

Ja: de MCP-server is een standaard MCP-server, en Studio ondersteunt **Custom MCP Connectors** op basis van een server-URL. De server draait nu in twee modi:

```bash
picnic-mcp                                        # stdio (lokale MCP-clients)
picnic-mcp --transport streamable-http --port 8000   # HTTP op /mcp (voor een connector)
```

Stappen:

1. Draai de server zelf op een locatie met een **HTTPS-URL met geldig certificaat** (Studio controleert de server via HTTPS; streamable HTTP op `/mcp` is de standaard). Bijvoorbeeld op je eigen server/VPS achter een reverse proxy. De Picnic-inloggegevens zet je als env vars (`PICNIC_EMAIL`/`PICNIC_PASSWORD` of `PICNIC_AUTH_TOKEN`) in de omgeving van de server — die gaan nooit via de connector mee.
2. In Studio/Le Chat: **Connectors → + Add Connector → Custom MCP Connector**. Vul in: naam `picnic`, server-URL `https://<jouw-server>/mcp`.
3. Staat de server niet publiek? Beveilig de endpoint dan met een Bearer-token (Studio detecteert automatisch `Authorization`-header-authenticatie).
4. Zet bij de connector-permissies de schrijf-acties (`picnic_add_to_cart`, `picnic_start_checkout`, ...) op **handmatige Genehmigung** — alleen lees-acties pre-autoriseren.

Daarna kun je in Le Chat/Studio zeggen: *"Zoek bij Picnic naar havermelk, voeg 2 toe aan mijn winkelwagen en kies het eerste bezorgmoment."*

## Veiligheid

- `picnic_start_checkout` vereist expliciet `confirm=true`; de tool-beschrijving instrueert de AI om de gebruiker altijd eerst om toestemming te vragen. De betaling zelf wordt **nooit** automatisch uitgevoerd — die rond je af in de Picnic-app.
- Inloggegevens gaan via environment-variabelen of `.env`; `.env` en `.picnic_token` staan in `.gitignore` en worden nooit gecommit.
- De Picnic-API is **onofficieel** (afgeleid van de app) en kan zonder aankondiging wijzigen. Gebruik op eigen risico.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests draaien volledig lokaal met een gemockte HTTP-transport; er is geen Picnic-account nodig.
