# =============================================================================
# RBAC role assignments for the ARM MCP Server managed identity
#
# Role strategy (mirrors the Bicep role-assignment modules in azmcp-foundry-aca-mi):
#
#   Subscription-level Reader  →  covers all ARM metadata for:
#                                  Cosmos DB, SQL Server, Azure OpenAI,
#                                  Azure Search, Data Factory, Synapse,
#                                  Log Analytics, Logic Apps, Azure Monitor,
#                                  Application Insights, Resource Graph,
#                                  Virtual Machines, Virtual Networks,
#                                  App Service, Functions, AKS, Key Vault,
#                                  Event Hubs, and any other ARM resource type
#
#   Service-specific data-plane roles  →  added individually below for services
#                                         that need access beyond ARM metadata
#
# Role definition IDs sourced from:
#   https://learn.microsoft.com/azure/role-based-access-control/built-in-roles
# =============================================================================

# =============================================================================
# 1. SUBSCRIPTION-LEVEL READER
#    Covers ARM metadata for every resource type in the subscription.
#    Mirrors acaSubscriptionReaderRole in main.bicep.
# =============================================================================

resource "azurerm_role_assignment" "mcp_subscription_reader" {
  scope                = local.rbac_scope
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 2. STORAGE
#    Blob, Queue, Table, File data-plane read access.
#    Mirrors aca-role-assignment-resource-storage.bicep.
# =============================================================================

resource "azurerm_role_assignment" "mcp_storage_blob_reader" {
  scope                = var.storage_resource_id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

resource "azurerm_role_assignment" "mcp_storage_reader" {
  scope                = var.storage_resource_id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

resource "azurerm_role_assignment" "mcp_storage_queue_reader" {
  scope                = var.storage_resource_id
  role_definition_name = "Storage Queue Data Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

resource "azurerm_role_assignment" "mcp_storage_table_reader" {
  scope                = var.storage_resource_id
  role_definition_name = "Storage Table Data Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 3. KEY VAULT
#    Secrets User = read secret values; Key Vault Reader = read metadata.
#    Subscription-level Reader (above) covers Key Vault metadata,
#    but secrets/keys/certs data-plane access requires dedicated roles.
# =============================================================================

resource "azurerm_role_assignment" "mcp_keyvault_secrets_user" {
  scope                = local.rbac_scope
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

resource "azurerm_role_assignment" "mcp_keyvault_reader" {
  scope                = local.rbac_scope
  role_definition_name = "Key Vault Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 4. COGNITIVE SERVICES / AZURE OPENAI
#    Cognitive Services User allows the server to call AI endpoints.
#    Mirrors cognitive-services-reader-role-assignment.bicep.
# =============================================================================

resource "azurerm_role_assignment" "mcp_cognitive_services_user" {
  scope                = local.rbac_scope
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 5. SERVICE BUS
#    Data Receiver = peek/read messages without consuming them.
#    Mirrors service-bus-reader-role-assignment.bicep.
# =============================================================================

resource "azurerm_role_assignment" "mcp_servicebus_data_receiver" {
  scope                = local.rbac_scope
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 6. EVENT GRID
#    EventGrid Data Reader = list/read topics, subscriptions, and event data.
#    Mirrors event-grid-reader-role-assignment.bicep.
# =============================================================================

resource "azurerm_role_assignment" "mcp_eventgrid_subscription_reader" {
  scope                = local.rbac_scope
  role_definition_name = "EventGrid EventSubscription Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 7. EVENT HUBS
#    Data Receiver = read event stream data.
# =============================================================================

resource "azurerm_role_assignment" "mcp_eventhub_data_receiver" {
  scope                = local.rbac_scope
  role_definition_name = "Azure Event Hubs Data Receiver"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 8. REDIS CACHE
#    Redis Cache Data Reader = read-only access to cache data.
#    Mirrors redis-cache-reader-role-assignment.bicep.
# =============================================================================

# =============================================================================
# 9. COSMOS DB
#    Cosmos DB Account Reader = read account properties and list databases.
#    Mirrors cosmos-db-reader-role-assignment.bicep.
#    (Data-plane document access requires a separate Cosmos RBAC assignment
#     via azurerm_cosmosdb_sql_role_assignment if needed per account.)
# =============================================================================

resource "azurerm_role_assignment" "mcp_cosmosdb_account_reader" {
  scope                = local.rbac_scope
  role_definition_name = "Cosmos DB Account Reader Role"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 10. LOG ANALYTICS / AZURE MONITOR
#     Log Analytics Reader = query workspace logs (KQL).
#     Monitoring Reader   = read all monitoring data (metrics, alerts, etc.).
#     Mirrors azure-monitor-reader and log-analytics-reader bicep modules.
# =============================================================================

resource "azurerm_role_assignment" "mcp_log_analytics_reader" {
  scope                = local.rbac_scope
  role_definition_name = "Log Analytics Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

resource "azurerm_role_assignment" "mcp_monitoring_reader" {
  scope                = local.rbac_scope
  role_definition_name = "Monitoring Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 11. VIRTUAL MACHINE OPERATIONS
#     Virtual Machine Contributor grants start / stop / restart / deallocate.
#     Required by: start_virtual_machine, stop_virtual_machine,
#                  restart_virtual_machine MCP tools.
# =============================================================================

resource "azurerm_role_assignment" "mcp_vm_contributor" {
  scope                = local.rbac_scope
  role_definition_name = "Virtual Machine Contributor"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 12. TAG MANAGEMENT
#     Tag Contributor allows adding / updating tags on any resource.
#     Required by: update_resource_tags MCP tool.
# =============================================================================

resource "azurerm_role_assignment" "mcp_tag_contributor" {
  scope                = local.rbac_scope
  role_definition_name = "Tag Contributor"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# 13. DEFENDER FOR CLOUD
#     Security Reader grants read access to security alerts, secure scores,
#     and assessment results (recommendations).
#     Required by: list_defender_alerts, get_defender_secure_score,
#                  list_defender_recommendations MCP tools.
# =============================================================================

resource "azurerm_role_assignment" "mcp_security_reader" {
  scope                = local.rbac_scope
  role_definition_name = "Security Reader"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}

# =============================================================================
# Services covered by the subscription-level Reader above (no extra role needed)
# -----------------------------------------------------------------------------
# SQL Server / Azure SQL Database   → Reader (ARM metadata + query via ARG)
# Azure Search                      → Reader (list indexes, indexers)
# Azure Data Factory                → Reader (list pipelines, datasets)
# Azure Synapse Analytics           → Reader (list workspaces, pools)
# Logic Apps                        → Reader (list workflows, runs)
# Application Insights              → Reader (list components)
# Azure Container Apps              → Reader (list apps, environments)
# Azure Kubernetes Service (AKS)    → Reader (list clusters, node pools)
# Azure App Service / Functions     → Reader (list sites, slots)
# Azure Virtual Machines            → Reader (list VMs, disks) + VM Contributor (above) for operations
# Azure Virtual Networks            → Reader (list VNets, subnets, NSGs)
# Azure Firewall                    → Reader
# Azure Load Balancer               → Reader
# Azure DNS                         → Reader
# Azure Container Registry          → Reader
# Azure Batch                       → Reader
# Azure API Management              → Reader
# Azure SignalR                     → Reader
# =============================================================================
