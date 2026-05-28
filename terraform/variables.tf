variable "subscription_id" {
  type        = string
  description = "Azure subscription ID where the ARM MCP Server will be deployed"
  default     = "0f524912-b0f4-4d41-92b2-db557f74e0e7"
}

variable "tenant_id" {
  type        = string
  description = "Azure AD / Entra ID tenant ID"
}

variable "resource_group_name" {
  type        = string
  description = "Existing resource group name"
  default     = "RG_AI_Agent_MCP"
}

variable "location" {
  type        = string
  description = "Azure region for new resources"
  default     = "swedencentral"
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
  description = "Globally unique Azure Container Registry name (3-50 alphanumeric chars)"
}

# ---------------------------------------------------------------------------
# Pre-existing Entra App (hardcoded in main.bicep — do not change)
# ---------------------------------------------------------------------------

variable "entra_app_client_secret" {
  type        = string
  sensitive   = true
  description = "Client secret for the Entra App. Set to enable the OBO flow so human users only see their own Azure resources. Leave empty to keep all callers using the server MI."
  default     = ""
}

variable "entra_app_client_id" {
  type        = string
  description = "Client ID of the pre-provisioned Entra App used to authenticate MCP clients"
  default     = "3fbf7d06-e265-4c2a-8abe-38184c70c6aa"
}

variable "entra_app_service_principal_object_id" {
  type        = string
  description = "Object ID of the Entra App's service principal (resourceId in MS Graph)"
  default     = "8dc1ea05-0eb8-4aa6-941b-ca13e6bb4863"
}

variable "entra_app_role_id" {
  type        = string
  description = "App role ID on the Entra App that grants MCP tool access"
  default     = "38880a45-4205-421f-9c21-831a2b14b2d6"
}

# ---------------------------------------------------------------------------
# Foundry project (the agent that will call this MCP server)
# ---------------------------------------------------------------------------

variable "foundry_project_resource_id" {
  type        = string
  description = "Full resource ID of the Azure AI Foundry project whose MI gets the Entra App role"
  default     = "/subscriptions/0f524912-b0f4-4d41-92b2-db557f74e0e7/resourceGroups/RG_AI_Agent_MCP/providers/Microsoft.CognitiveServices/accounts/mcp-agent-azure/projects/mcp-agent-azure"
}

# ---------------------------------------------------------------------------
# Storage (for Reader role — mirrors the Bicep setup)
# ---------------------------------------------------------------------------

variable "storage_resource_id" {
  type        = string
  description = "Full resource ID of the storage account the MCP server should be able to read"
  default     = "/subscriptions/0f524912-b0f4-4d41-92b2-db557f74e0e7/resourceGroups/RG_AI_Agent_MCP/providers/Microsoft.Storage/storageAccounts/aimcpstorageacct"
}
