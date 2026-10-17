# Azure API Management in front of the AKS-hosted agent service.
#
# Traffic path: Client -> Azure Front Door -> APIM gateway -> AKS ingress -> agent service.
#
# SKU choice: Developer_1 keeps demo costs sane. It has NO SLA, no VNET
# integration, no availability zones and no multi-region support — so for
# this tier APIM reaches the service over the public AKS ingress hostname
# (var.app_host). Production upgrade path: Premium_1 (or Premiumv2),
# which unlocks VNET injection, Private Link to the AKS ingress via an
# *internal* ingress class, availability zones, and multi-region
# deployment. See docs/stack-alignment.md.

locals {
  apim_name = "${var.prefix}${var.environment}apim${random_string.suffix.result}"
}

resource "azurerm_api_management" "main" {
  name                = local.apim_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  publisher_name      = var.apim_publisher_name
  publisher_email     = var.apim_publisher_email
  sku_name            = var.apim_sku # "Developer_1" for demo; "Premium_1" for prod
  tags                = local.common_tags
}

# Import the agent service API from the FastAPI-generated OpenAPI document.
# Regenerate infra/apim/openapi.json after changing service routes:
#   python -c "import json; from food_ingredients_ai.service.app import app;
#              json.dump(app.openapi(), open('infra/apim/openapi.json','w'), indent=2)"
resource "azurerm_api_management_api" "agents" {
  name                  = "food-ingredients-agent-api"
  resource_group_name   = azurerm_resource_group.main.name
  api_management_name   = azurerm_api_management.main.name
  revision              = "1"
  display_name          = "food-ingredients agentic AI"
  description           = "Multi-agent reformulation service (R&D, supply chain, ESG, customer advisor)."
  path                  = "v1"
  protocols             = ["https"]
  subscription_required = true

  import {
    content_format = "openapi+json"
    content_value  = file("${path.module}/../apim/openapi.json")
  }
}

# Backend pool: the AKS ingress. The service keeps its own bearer-token
# check (defense in depth); APIM is the edge policy enforcement point.
resource "azurerm_api_management_backend" "aks" {
  name                = "aks-ingress"
  resource_group_name = azurerm_resource_group.main.name
  api_management_name = azurerm_api_management.main.name
  protocol            = "http"
  url                 = "https://${var.app_host}"
  description         = "AKS nginx ingress fronting the agent service."

  tls {
    validate_certificate_chain = true
    validate_certificate_name  = true
  }
}

resource "azurerm_api_management_product" "agents" {
  product_id            = "agent-apis"
  api_management_name   = azurerm_api_management.main.name
  resource_group_name   = azurerm_resource_group.main.name
  display_name          = "Agent APIs"
  description           = "Reformulation workflow and per-agent run endpoints."
  subscription_required = true
  approval_required     = false # demo; require approval in production
  published             = true
}

resource "azurerm_api_management_product_api" "agents" {
  api_name            = azurerm_api_management_api.agents.name
  product_id          = azurerm_api_management_product.agents.product_id
  api_management_name = azurerm_api_management.main.name
  resource_group_name = azurerm_resource_group.main.name
}

# Inbound policies: Entra ID JWT validation at the edge, rate limiting,
# CORS for the demo UI, then route to the AKS backend.
resource "azurerm_api_management_api_policy" "agents" {
  api_name            = azurerm_api_management_api.agents.name
  api_management_name = azurerm_api_management.main.name
  resource_group_name = azurerm_resource_group.main.name

  xml_content = <<XML
<policies>
  <inbound>
    <base />
    <validate-jwt header-name="Authorization" failed-validation-httpcode="401" require-scheme="Bearer">
      <openid-config url="https://login.microsoftonline.com/${var.entra_tenant_id}/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>${var.entra_api_audience}</audience>
      </audiences>
    </validate-jwt>
    <rate-limit-by-key calls="100" renewal-period="60" counter-key="@(context.Request.IpAddress)" retry-after-header-name="Retry-After" />
    <cors allow-credentials="false">
      <allowed-origins><origin>*</origin></allowed-origins>
      <allowed-methods><method>*</method></allowed-methods>
      <allowed-headers><header>*</header></allowed-headers>
    </cors>
    <set-backend-service backend-id="${azurerm_api_management_backend.aks.name}" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
XML
}
