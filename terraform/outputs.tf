output "container_app_url" {
  description = "HTTPS base URL of the ARM MCP Server"
  value       = "https://${azurerm_container_app.arm_mcp.ingress[0].fqdn}"
}

output "mcp_endpoint" {
  description = "Full MCP endpoint (Streamable HTTP) to configure in VS Code or Foundry agent"
  value       = "https://${azurerm_container_app.arm_mcp.ingress[0].fqdn}/mcp"
}

output "health_endpoint" {
  description = "Health check URL"
  value       = "https://${azurerm_container_app.arm_mcp.ingress[0].fqdn}/health"
}

output "acr_login_server" {
  description = "ACR login server — used when building and pushing the container image"
  value       = azurerm_container_registry.acr.login_server
}

output "mcp_mi_client_id" {
  description = "Client ID of the user-assigned MI (set as AZURE_CLIENT_ID in the container)"
  value       = azurerm_user_assigned_identity.mcp_mi.client_id
}

output "mcp_mi_principal_id" {
  description = "Principal ID of the user-assigned MI (for additional role assignments)"
  value       = azurerm_user_assigned_identity.mcp_mi.principal_id
}

output "container_app_name" {
  description = "Container App resource name"
  value       = azurerm_container_app.arm_mcp.name
}

output "entra_app_client_id" {
  description = "Entra App client ID — used by MCP clients to obtain Bearer tokens"
  value       = var.entra_app_client_id
}

output "entra_app_identifier_uri" {
  description = "Audience for tokens targeting this MCP server"
  value       = "api://${var.entra_app_client_id}"
}

output "docker_build_command" {
  description = "Command to build and push the container image after terraform apply"
  value       = "az acr build --registry ${azurerm_container_registry.acr.name} --image arm-mcp:latest ./deployment"
}

# ── Foundry portal connection values ──────────────────────────────────────
# Use these when connecting via ai.azure.com/nextgen:
#   Build → Agent → Tools → Add → Custom → Model Context Protocol

output "foundry_mcp_endpoint" {
  description = "Paste this as 'Remote MCP Server endpoint' in the Foundry portal (includes /mcp path)"
  value       = "https://${azurerm_container_app.arm_mcp.ingress[0].fqdn}/mcp"
}

output "foundry_mcp_audience" {
  description = "Paste this as the 'Audience' when selecting Microsoft Entra → Project Managed Identity"
  value       = "api://${var.entra_app_client_id}"
}

output "foundry_connection_name" {
  description = "Name of the MCP connection created in the Foundry project"
  value       = azapi_resource.arm_mcp_connection.name
}
