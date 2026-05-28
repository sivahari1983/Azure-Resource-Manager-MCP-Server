# User-assigned managed identity for the Container App.
# Using user-assigned (rather than system-assigned) solves the chicken-and-egg
# problem: we can assign AcrPull before the Container App is created, so the
# first `terraform apply` both provisions the app and grants it registry access.

resource "azurerm_user_assigned_identity" "mcp_mi" {
  name                = "${var.aca_name}-mi"
  resource_group_name = data.azurerm_resource_group.main.name
  location            = data.azurerm_resource_group.main.location

  tags = local.common_tags
}

# Allow the MI to pull images from the ACR (must exist before the Container App starts)
resource "azurerm_role_assignment" "mcp_acr_pull" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.mcp_mi.principal_id
}
