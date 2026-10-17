# Azure footprint for the agent service (demo).
#
# Provisions: resource group, Container Registry, AKS (workload identity),
# Key Vault, Log Analytics + Application Insights, a user-assigned managed
# identity federated to the AKS service account, an Azure AI Services
# (Foundry) account with an Azure OpenAI model deployment, and the RBAC
# wiring between them. No secrets in code — Key Vault is RBAC-only and the
# service authenticates with managed/workload identity.

locals {
  name_prefix = "${var.prefix}-${var.environment}"
  common_tags = merge(var.tags, { environment = var.environment })
}

resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}

# ---------------------------------------------------------------------------
# Foundation: resource group, monitoring, registry, vault
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "main" {
  name     = "${local.name_prefix}-rg"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.name_prefix}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

resource "azurerm_application_insights" "main" {
  name                = "${local.name_prefix}-appi"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.common_tags
}

resource "azurerm_container_registry" "main" {
  name                = "${var.prefix}${var.environment}acr${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"
  admin_enabled       = false # RBAC / managed identity only
  tags                = local.common_tags
}

resource "azurerm_key_vault" "main" {
  name                       = "${local.name_prefix}-kv-${random_string.suffix.result}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true # no access policies; RBAC assignments below
  soft_delete_retention_days = 7
  tags                       = local.common_tags
}

data "azurerm_client_config" "current" {}

# ---------------------------------------------------------------------------
# AKS with OIDC issuer + workload identity
# ---------------------------------------------------------------------------

resource "azurerm_kubernetes_cluster" "main" {
  name                = "${local.name_prefix}-aks"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "${local.name_prefix}-aks"

  default_node_pool {
    name       = "system"
    node_count = var.aks_node_count
    vm_size    = var.aks_vm_size
    # Reliability: spread nodes across availability zones so a zone outage
    # can't take down the whole pool (pairs with pod anti-affinity in
    # infra/k8s/deployment.yaml). See docs/reliability.md.
    zones = var.aks_availability_zones
  }

  identity {
    type = "SystemAssigned"
  }

  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  tags = local.common_tags
}

# AKS kubelet pulls images from ACR (no admin keys).
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
}

# ---------------------------------------------------------------------------
# Workload identity for the agent service (AKS -> Azure, no secrets)
# ---------------------------------------------------------------------------

resource "azurerm_user_assigned_identity" "svc" {
  name                = "${local.name_prefix}-svc-id"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_federated_identity_credential" "svc" {
  name                = "${local.name_prefix}-svc-federated"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.svc.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:${var.k8s_namespace}:${var.k8s_service_account}"
}

# ---------------------------------------------------------------------------
# Azure AI Services (Foundry) + Azure OpenAI model deployment
#
# Reliability note: the service treats the model deployment as a *fallible*
# dependency, not a hard requirement. The app retries transient failures
# (exponential backoff + jitter), trips a circuit breaker after repeated
# failures, and gracefully degrades to the offline fake client — the API
# stays up and keeps serving deterministic demo results, flagged with
# `degraded: true` + `X-Service-Degraded`. See docs/reliability.md and
# food_ingredients_ai/service/reliability.py. For production, add a second model
# deployment (different region) and fail over at the client layer.
# ---------------------------------------------------------------------------

resource "azurerm_cognitive_account" "foundry" {
  name                = "${local.name_prefix}-ai-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "AIServices"
  sku_name            = "S0"

  identity {
    type = "SystemAssigned"
  }

  tags = local.common_tags
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.openai_model_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.openai_model_name
    version = var.openai_model_version
  }

  sku {
    name     = "Standard"
    capacity = var.openai_sku_capacity
  }
}

# ---------------------------------------------------------------------------
# RBAC: what the workload identity may do (least privilege)
# ---------------------------------------------------------------------------

# Service reads secrets from Key Vault (e.g. optional API-key fallback).
resource "azurerm_role_assignment" "svc_keyvault_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.svc.principal_id
}

# Service calls Azure OpenAI via managed identity (primary auth path).
resource "azurerm_role_assignment" "svc_openai_user" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.svc.principal_id
}
