variable "subscription_id" {
  type        = string
  description = "Azure subscription ID where the ARM MCP Server will be deployed (az account show --query id -o tsv)"
}

variable "tenant_id" {
  type        = string
  description = "Azure AD / Entra ID tenant ID (az account show --query tenantId -o tsv)"
}

variable "resource_group_name" {
  type        = string
  description = "Existing resource group name where all resources will be created"
}

variable "location" {
  type        = string
  description = "Azure region for new resources (e.g. eastus, westeurope, swedencentral)"
}

# ---------------------------------------------------------------------------
# Container App
# ---------------------------------------------------------------------------

variable "aca_name" {
  type        = string
  description = "Name for the ARM MCP Server Container App"
  default     = "arm-mcp-server"
}

variable "aca_min_replicas" {
  type        = number
  description = "Minimum replicas (0 = scale to zero when idle)"
  default     = 0
}

variable "aca_max_replicas" {
  type        = number
  description = "Maximum replicas"
  default     = 3
}

variable "container_image" {
  type        = string
  description = "Full container image reference (overrides the ACR-built image when set)"
  default     = ""
}

# ---------------------------------------------------------------------------
# Azure Container Registry
# ---------------------------------------------------------------------------

variable "acr_name" {
  type        = string
  description = "Globally unique Azure Container Registry name (3-50 alphanumeric chars, no hyphens)"
}

# ---------------------------------------------------------------------------
# Entra App Registration (protects the /mcp endpoint)
# ---------------------------------------------------------------------------

variable "entra_app_client_secret" {
  type        = string
  sensitive   = true
  description = "Client secret for the Entra App. Set to enable the OBO flow so human users only see their own Azure resources. Leave empty to keep all callers using the server MI."
  default     = ""
}

variable "entra_app_client_id" {
  type        = string
  description = "Client ID (Application ID) of the Entra App Registration used to authenticate MCP clients"
}

variable "entra_app_service_principal_object_id" {
  type        = string
  description = "Object ID of the Entra App's service principal (visible in Enterprise Applications in the portal)"
}

variable "entra_app_role_id" {
  type        = string
  description = "App role ID defined on the Entra App that grants MCP tool access (a GUID you assign when creating the role)"
}

# ---------------------------------------------------------------------------
# Foundry project (the AI agent that will call this MCP server)
# ---------------------------------------------------------------------------

variable "foundry_project_resource_id" {
  type        = string
  description = "Full resource ID of the Azure AI Foundry project whose managed identity gets the Entra App role. Format: /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.CognitiveServices/accounts/<ACCOUNT>/projects/<PROJECT>"
}

# ---------------------------------------------------------------------------
# Storage account (data-plane Reader role)
# ---------------------------------------------------------------------------

variable "storage_resource_id" {
  type        = string
  description = "Full resource ID of the storage account the MCP server should be able to read. Format: /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.Storage/storageAccounts/<ACCOUNT>"
}
