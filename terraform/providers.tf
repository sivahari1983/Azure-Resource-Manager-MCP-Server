terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.50"
    }
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.0"
    }
  }

  # Remote state in the existing storage account — values supplied via
  # -backend-config flags in CI (deploy.yml) or terraform init locally.
  backend "azurerm" {
    resource_group_name  = "RG_AI_Agent_MCP"
    storage_account_name = "aimcpstorageacct"
    container_name       = "tfstate"
    key                  = "arm-mcp-server.tfstate"
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

provider "azuread" {
  tenant_id = var.tenant_id
}

provider "azapi" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

data "azurerm_client_config" "current" {}
