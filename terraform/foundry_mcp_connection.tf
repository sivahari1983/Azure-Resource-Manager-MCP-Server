# ── Foundry project MCP connection ────────────────────────────────────────
#
# Creates the MCP server connection inside the Foundry project so that
# agents in the project can add it as a tool.
#
# Portal equivalent (ai.azure.com/nextgen):
#   Build → Agent → Tools → Add → Custom → Model Context Protocol
#     Remote MCP Server endpoint : <container_app_url output>
#     Authentication              : Microsoft Entra → Project Managed Identity
#     Audience                    : <entra_app_client_id output>
#
# The azapi resource below automates the same step. If the exact API schema
# changes, verify the expected body with:
#   az rest --method GET \
#     --url "https://management.azure.com${var.foundry_project_resource_id}/connections?api-version=2025-04-01-preview"
# after creating one connection manually in the portal.
#
# NOTE: The Container App must be running before applying this resource so
# that the `fqdn` attribute is available.

resource "azapi_resource" "arm_mcp_connection" {
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name      = "arm-mcp-server"
  parent_id = var.foundry_project_resource_id

  # Disable embedded schema validation — the connections API schema for
  # CognitiveServices projects is not fully reflected in the azapi provider yet.
  # The actual properties are verified via the REST API after apply.
  schema_validation_enabled = false

  body = {
    properties = {
      # RemoteTool + custom_MCP metadata = MCP connection in Foundry portal
      category = "RemoteTool"

      # ProjectManagedIdentity = Foundry project MI obtains a token for the audience below
      authType = "ProjectManagedIdentity"

      # Streamable HTTP endpoint — single POST/GET endpoint avoids the SSE
      # two-phase flow where Foundry's HTTP/2 client adds :443 to the derived
      # messages URL, causing 421 from Azure Container Apps Envoy.
      target = "https://${azurerm_container_app.arm_mcp.ingress[0].fqdn}/mcp"

      # Audience for the Bearer token the Foundry project MI will request
      audience = "api://${var.entra_app_client_id}"

      metadata = {
        type = "custom_MCP"
      }
    }
  }

  # Wait for the Container App to be provisioned before creating the connection
  depends_on = [azurerm_container_app.arm_mcp]
}
