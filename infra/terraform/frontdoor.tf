# Azure Front Door (Standard) in front of API Management: global load
# balancing, anycast entry point, TLS termination and WAF.
#
# Traffic path: Client -> Front Door -> APIM gateway -> AKS ingress -> agent service.
# Upgrade path: Front Door Premium for Private Link origins and
# advanced bot protection; multi-origin groups for multi-region AKS.

resource "azurerm_cdn_frontdoor_profile" "main" {
  name                = "${local.name_prefix}-fd"
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = var.frontdoor_sku # "Standard_AzureFrontDoor" for demo
  tags                = local.common_tags
}

resource "azurerm_cdn_frontdoor_endpoint" "main" {
  name                     = "${local.name_prefix}-fd-ep"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id
  tags                     = local.common_tags
}

resource "azurerm_cdn_frontdoor_origin_group" "apim" {
  name                     = "apim-origin-group"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id
  session_affinity_enabled = false

  load_balancing {
    sample_size                 = 4
    successful_samples_required = 2
  }

  # APIM exposes a built-in unauthenticated status probe.
  health_probe {
    path                = "/status-0123456789abcdef"
    protocol            = "Https"
    interval_in_seconds = 30
  }
}

resource "azurerm_cdn_frontdoor_origin" "apim" {
  name                          = "apim-origin"
  cdn_frontdoor_origin_group_id = azurerm_cdn_frontdoor_origin_group.apim.id
  host_name                     = azurerm_api_management.main.gateway_url
  certificate_name_check_enabled = true
  enabled                       = true

  http_port  = 80
  https_port = 443
}

resource "azurerm_cdn_frontdoor_route" "api" {
  name                          = "api-route"
  cdn_frontdoor_endpoint_id     = azurerm_cdn_frontdoor_endpoint.main.id
  cdn_frontdoor_origin_group_id = azurerm_cdn_frontdoor_origin_group.apim.id
  patterns_to_match             = ["/*"]
  supported_protocols           = ["Http", "Https"]
  https_redirect_enabled        = true
  forwarding_protocol           = "HttpsOnly"
  link_to_default_domain        = true
}

# WAF: OWASP default ruleset + bot manager, Prevention mode.
resource "azurerm_cdn_frontdoor_firewall_policy" "main" {
  name                = "${var.prefix}${var.environment}waf${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = var.frontdoor_sku
  enabled             = true
  mode                = "Prevention"

  managed_rule {
    type    = "DefaultRuleSet"
    version = "1.0"
    action  = "Block"
  }

  managed_rule {
    type    = "Microsoft_BotManagerRuleSet"
    version = "1.0"
    action  = "Block"
  }

  tags = local.common_tags
}

resource "azurerm_cdn_frontdoor_security_policy" "main" {
  name                     = "${local.name_prefix}-waf-policy"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id

  security_policies {
    firewall {
      cdn_frontdoor_firewall_policy_id = azurerm_cdn_frontdoor_firewall_policy.main.id

      association {
        domain {
          cdn_frontdoor_domain_id = azurerm_cdn_frontdoor_endpoint.main.id
        }
        patterns_to_match = ["/*"]
      }
    }
  }
}
