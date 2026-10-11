# Provider pins for the Azure deployment track.
#
# Azure-first, structured for multi-cloud later: provider blocks live only
# in this directory (infra/terraform/azure/). A future AWS/GCP port adds a
# sibling directory (infra/terraform/aws/, ...) reusing variables.tf and
# outputs.tf shapes.

terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Remote state is intentionally NOT configured here: the operator wires
  # their own backend (e.g. azurerm backend with a storage account) before
  # the first apply. See README.md.
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
  # subscription_id = var.subscription_id  # uncomment to pin explicitly
}
