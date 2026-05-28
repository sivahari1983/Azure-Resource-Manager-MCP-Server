resource "azurerm_container_app_environment" "env" {
  name                = "${var.aca_name}-env"
  resource_group_name = data.azurerm_resource_group.main.name
  location            = data.azurerm_resource_group.main.location

  tags = local.common_tags
}

resource "azurerm_container_app" "arm_mcp" {
  name                         = var.aca_name
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.env.id
  revision_mode                = "Single"

  # OBO client secret — only present when var.entra_app_client_secret is set.
  # Enables per-user Azure access for human callers (scp token claim).
  # Leave empty to keep the current behaviour (all callers use the server MI).
  dynamic "secret" {
    for_each = var.entra_app_client_secret != "" ? [1] : []
    content {
      name  = "entra-client-secret"
      value = var.entra_app_client_secret
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.mcp_mi.id]
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.mcp_mi.id
  }

  ingress {
    # SECURITY: HTTPS-only external access; Container Apps Envoy terminates TLS
    # at the ingress boundary and routes to the container over HTTP within the
    # pod network (never exposed externally as plain HTTP).
    allow_insecure_connections = false
    external_enabled           = true
    target_port                = 8080
    transport                  = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.aca_min_replicas
    max_replicas = var.aca_max_replicas

    container {
      name   = var.aca_name
      image  = local.container_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AZURE_SUBSCRIPTION_ID"
        value = var.subscription_id
      }
      env {
        # Tells DefaultAzureCredential which user-assigned MI to use
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.mcp_mi.client_id
      }
      env {
        name  = "AZURE_TENANT_ID"
        value = var.tenant_id
      }
      env {
        # Used by EntraAuthMiddleware to validate incoming Bearer tokens
        name  = "ENTRA_APP_CLIENT_ID"
        value = var.entra_app_client_id
      }
      # OBO client secret — only injected when the variable is set.
      dynamic "env" {
        for_each = var.entra_app_client_secret != "" ? [1] : []
        content {
          name        = "ENTRA_APP_CLIENT_SECRET"
          secret_name = "entra-client-secret"
        }
      }
      env {
        name  = "PORT"
        value = "8080"
      }
    }

    http_scale_rule {
      name                = "http-scaler"
      concurrent_requests = "100"
    }
  }

  tags = local.common_tags

  # Ensure the MI has AcrPull before the app tries to pull its image
  depends_on = [azurerm_role_assignment.mcp_acr_pull]
}
