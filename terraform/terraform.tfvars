# Copy this file to terraform.tfvars and fill in your values.
# Values with defaults in variables.tf only need to be set here if you want to override them.

subscription_id     = "0f524912-b0f4-4d41-92b2-db557f74e0e7"
tenant_id           = "05764a73-8c6f-4538-83cd-413f1e1b5665"  # az account show --query tenantId -o tsv

resource_group_name = "RG_AI_Agent_MCP"
location            = "swedencentral"

# ACR name must be globally unique (3-50 alphanumeric, no hyphens)
acr_name = "armmcpacr"

aca_name         = "arm-mcp-server"
aca_min_replicas = 0
aca_max_replicas = 3

# All Entra App values below match the hardcoded vars in main.bicep — leave unchanged
entra_app_client_id                   = "3fbf7d06-e265-4c2a-8abe-38184c70c6aa"
# Optional: set to enable OBO so human users only see their own Azure resources.
# Create a secret under the Entra App (portal: App registrations → Certificates & secrets).
# Also grant the app "Azure Service Management – user_impersonation" API permission.
# entra_app_client_secret = ""
entra_app_service_principal_object_id = "8dc1ea05-0eb8-4aa6-941b-ca13e6bb4863"
entra_app_role_id                     = "38880a45-4205-421f-9c21-831a2b14b2d6"

foundry_project_resource_id = "/subscriptions/0f524912-b0f4-4d41-92b2-db557f74e0e7/resourceGroups/RG_AI_Agent_MCP/providers/Microsoft.CognitiveServices/accounts/mcp-agent-azure/projects/mcp-agent-azure"

storage_resource_id = "/subscriptions/0f524912-b0f4-4d41-92b2-db557f74e0e7/resourceGroups/RG_AI_Agent_MCP/providers/Microsoft.Storage/storageAccounts/aimcpstorageacct"
