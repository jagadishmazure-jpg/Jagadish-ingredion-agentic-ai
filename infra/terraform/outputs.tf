# Outputs consumed by the Docker/K8s/CI steps (see docs/deployment-runbook.md).

output "resource_group_name" {
  description = "Resource group holding the deployment."
  value       = azurerm_resource_group.main.name
}

output "acr_login_server" {
  description = "ACR login server for docker push / image references."
  value       = azurerm_container_registry.main.login_server
}

output "aks_name" {
  description = "AKS cluster name (for az aks get-credentials)."
  value       = azurerm_kubernetes_cluster.main.name
}

output "aks_oidc_issuer_url" {
  description = "AKS OIDC issuer (federated identity trust anchor)."
  value       = azurerm_kubernetes_cluster.main.oidc_issuer_url
}

output "key_vault_uri" {
  description = "Key Vault URI (for the CSI SecretProviderClass)."
  value       = azurerm_key_vault.main.vault_uri
}

output "key_vault_name" {
  description = "Key Vault name (for the CSI SecretProviderClass)."
  value       = azurerm_key_vault.main.name
}

output "workload_identity_client_id" {
  description = "Client ID for the K8s ServiceAccount workload-identity annotation."
  value       = azurerm_user_assigned_identity.svc.client_id
}

output "openai_endpoint" {
  description = "Azure AI Services (Foundry) endpoint for AZURE_OPENAI_ENDPOINT."
  value       = azurerm_cognitive_account.foundry.endpoint
}

output "openai_deployment_name" {
  description = "Chat model deployment name for AZURE_OPENAI_CHAT_DEPLOYMENT."
  value       = azurerm_cognitive_deployment.chat.name
}

output "app_insights_connection_string" {
  description = "Application Insights connection string (secret — handle accordingly)."
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "apim_gateway_url" {
  description = "APIM gateway base URL (Front Door origin target)."
  value       = "https://${azurerm_api_management.main.gateway_url}"
}

output "apim_name" {
  description = "APIM service name (for az apim commands)."
  value       = azurerm_api_management.main.name
}

output "frontdoor_endpoint_hostname" {
  description = "Public Front Door endpoint hostname — the client-facing entry point."
  value       = azurerm_cdn_frontdoor_endpoint.main.host_name
}
