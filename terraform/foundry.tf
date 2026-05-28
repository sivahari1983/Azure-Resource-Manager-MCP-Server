# ── Foundry project → Entra App role assignment ────────────────────────────
#
# Mirrors foundry-role-assignment-entraapp.bicep.
#
# Grants the Foundry project's managed identity the Entra App role so it can
# obtain Bearer tokens scoped to api://<entra_app_client_id> and call this
# MCP server's /mcp endpoint.
#
# The azapi data source reads the Foundry project to extract its MI principal ID
# (Microsoft.CognitiveServices/accounts/projects has its own identity in
# API version 2025-04-01-preview, matching the Bicep template).

data "azapi_resource" "foundry_project" {
  resource_id = var.foundry_project_resource_id
  type        = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"

  # Export only the fields we need; azapi v2 exposes these via .output
  response_export_values = ["identity.principalId"]
}

resource "azuread_app_role_assignment" "foundry_to_arm_mcp" {
  # The app role defined on the Entra App that permits MCP tool access
  app_role_id = var.entra_app_role_id

  # The Foundry project's managed identity principal that receives the role
  principal_object_id = data.azapi_resource.foundry_project.output.identity.principalId

  # The service principal of the Entra App (resource where the role is defined)
  resource_object_id = var.entra_app_service_principal_object_id
}
