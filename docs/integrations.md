# Enterprise Integrations

> **Disclaimer.** Independent portfolio demo; all data synthetic. The
> adapters below are **demo doubles** — no real CRM/SAP systems, no real
> credentials, no network.

## Pattern

Each integration is a **clean adapter interface** with three parts:

1. **Abstract interface** (`CRMAdapter`, `SAPAdapter`) — the contract agents
   code against.
2. **Synthetic implementation** (`DemoCRMAdapter`, `DemoSAPAdapter`) —
   fixed demo records, clearly marked `"demo": True`, used offline and in
   tests.
3. **Extension point** — subclass the interface for the real connector
   (Salesforce/Dynamics 365, SAP S/4HANA OData/RFC); select via env
   (`CRM_ADAPTER`, `SAP_ADAPTER`; anything but `demo` raises with guidance).

Config is **env-only** (`governance/security.py::require_env`); secrets never
appear in code.

## CRM (`integrations/crm.py`)

Used by the **customer advisor** agent (`estimate_pricing` with
`account_id`): account tier/segment, open opportunities, recent cases →
personalized proposals and tier-aware pricing notes. Demo accounts:
`ACME-001` (gold, bakery), `BEVCO-002` (silver, beverage).

Wiring a real CRM: implement `get_account`, `list_contacts`,
`list_opportunities`, `list_cases` against your CRM's REST API; read the
client id/secret from env; set `CRM_ADAPTER=salesforce` (or your name) and
extend `crm_from_env()`.

## SAP (`integrations/sap.py`)

Used by the **supply chain** agent (`optimize_inventory` with `plant_id`):
material masters, plant inventory levels, open purchase orders. Demo plants:
`PLANT-NA-01`, `PLANT-NA-02`.

Wiring real SAP: implement `get_material`, `get_inventory`,
`list_purchase_orders`, `list_plants` against S/4HANA OData services;
authenticate with the service's managed identity / OAuth client from env;
set `SAP_ADAPTER=s4hana` and extend `sap_from_env()`.

## Interop protocols

- **A2A** (`interop/a2a.py`): agent cards + JSON-RPC task endpoints so
  external agents can discover and invoke the four domain agents — with
  bearer-token auth and per-skill scope enforcement (`interop/auth.py`).
- **MCP** (`interop/mcp.py`): the domain tools as an MCP server
  (`tools/list`, `tools/call`, `initialize` handshake); stdio transport
  today, Streamable HTTP/SSE later by wrapping `handle_message`. External
  MCP clients (IDEs, orchestrators) can call `analyze_ingredients`,
  `validate_claims`, `optimize_inventory`, etc. directly.

## Production notes

Real deployments put these adapters behind the API service's managed
identity (Entra ID workload identity in AKS), with Azure Key Vault holding
any third-party secrets and RBAC scoping each adapter's access. See
`docs/identity.md` and `docs/foundry-deployment.md`.
