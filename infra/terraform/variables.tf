# Input variables. No secrets here — secrets live in Key Vault / env only.

variable "prefix" {
  description = "Naming prefix for all resources (lowercase, alphanumeric)."
  type        = string
  default     = "ingai"
}

variable "environment" {
  description = "Deployment environment label (dev | staging | prod)."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "eastus2"
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project = "jagadish-food-ingredients-agentic-ai"
    owner   = "demo"
  }
}

variable "openai_model_name" {
  description = "Azure OpenAI chat model deployment name."
  type        = string
  default     = "gpt-4o-mini"
}

variable "openai_model_version" {
  description = "Model version for the Azure OpenAI deployment."
  type        = string
  default     = "2024-07-18"
}

variable "openai_sku_capacity" {
  description = "Throughput capacity (k TPM) for the model deployment."
  type        = number
  default     = 10
}

variable "aks_node_count" {
  description = "AKS system node-pool size."
  type        = number
  default     = 2
}

variable "aks_vm_size" {
  description = "AKS node VM SKU."
  type        = string
  default     = "Standard_D4s_v5"
}

variable "aks_availability_zones" {
  description = "Availability zones for the AKS node pool (zone-redundant nodes)."
  type        = list(string)
  default     = ["1", "2", "3"]
}

variable "k8s_namespace" {
  description = "Kubernetes namespace the service deploys into."
  type        = string
  default     = "food-ingredients-ai"
}

variable "k8s_service_account" {
  description = "Kubernetes ServiceAccount federated to the workload identity."
  type        = string
  default     = "food-ingredients-svc"
}

variable "apim_sku" {
  description = "APIM SKU. Developer_1 keeps demo costs sane; use Premium_1 for production (VNET, zones, SLA)."
  type        = string
  default     = "Developer_1"
}

variable "apim_publisher_name" {
  description = "APIM publisher display name."
  type        = string
  default     = "Food-ingredients AI demo"
}

variable "apim_publisher_email" {
  description = "APIM publisher contact email."
  type        = string
  default     = "demo@example.com"
}

variable "entra_tenant_id" {
  description = "Entra ID tenant ID used by the APIM validate-jwt policy. Leave empty only if you strip that policy."
  type        = string
  default     = ""

  validation {
    condition     = var.entra_tenant_id != ""
    error_message = "entra_tenant_id is required: pass -var entra_tenant_id=<tenant-id> (the APIM validate-jwt policy needs it)."
  }
}

variable "entra_api_audience" {
  description = "Entra ID application (client) ID that APIM accepts as the JWT audience."
  type        = string
  default     = ""

  validation {
    condition     = var.entra_api_audience != ""
    error_message = "entra_api_audience is required: pass -var entra_api_audience=<app-client-id>."
  }
}

variable "app_host" {
  description = "Public DNS hostname served by the AKS ingress (APIM backend target). Must match __APP_HOST__ in infra/k8s/ingress.yaml."
  type        = string
  default     = "agents.example.com"
}

variable "frontdoor_sku" {
  description = "Front Door SKU. Standard_AzureFrontDoor for demo; Premium_AzureFrontDoor for Private Link origins."
  type        = string
  default     = "Standard_AzureFrontDoor"
}
