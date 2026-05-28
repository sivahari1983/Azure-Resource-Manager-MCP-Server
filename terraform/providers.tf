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

  # Remote state backend — all values are supplied externally so nothing
  # environment-specific is hard-coded here.
  #
  # Local:  terraform init -backend-config=backend.hcl
  #         (copy backend.hcl.example → backend.hcl and fill in your values)
  #
  # CI:     deploy.yml passes -backend-config flags from GitHub Variables.
  backend "azurerm" {}
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
