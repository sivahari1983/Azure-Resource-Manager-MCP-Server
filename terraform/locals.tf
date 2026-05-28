locals {
  # Use explicit container image if provided, otherwise default to the ACR image.
  # The image must be built and pushed before `terraform apply` (see README).
  container_image = var.container_image != "" ? var.container_image : "${azurerm_container_registry.acr.login_server}/arm-mcp:latest"

  # Parsed components from the storage resource ID (for cross-RG role assignment)
  storage_id_parts           = split("/", var.storage_resource_id)
  storage_resource_group     = local.storage_id_parts[4]
  storage_subscription_id    = local.storage_id_parts[2]

  # Parsed components from the Foundry project resource ID
  foundry_id_parts            = split("/", var.foundry_project_resource_id)
  foundry_account_name        = local.foundry_id_parts[8]
  foundry_project_name        = local.foundry_id_parts[10]

  common_tags = {
    product     = "arm-mcp-server"
    managed_by  = "terraform"
  }
}
