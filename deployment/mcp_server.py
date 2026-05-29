#!/usr/bin/env python3
"""
Azure Resource Manager MCP Server

Exposes ARM tools over HTTP so AI agents (Foundry, Copilot) can query
and manage Azure resources via the Model Context Protocol.

Authentication: Entra ID Bearer tokens are validated when AZURE_TENANT_ID
and ENTRA_APP_CLIENT_ID env vars are set.

Authorization (per-caller Azure access):
  - Human user tokens (scp claim) + ENTRA_APP_CLIENT_SECRET set
      → On-Behalf-Of flow: each user only sees what their own Azure RBAC allows.
  - Managed identity / app tokens (roles claim) or no client secret
      → Falls back to the server's User-Assigned MI (subscription-wide Reader).

OBO pre-requisites (only needed when human users call this server):
  1. Add "Azure Service Management – user_impersonation" to the Entra App's
     API permissions and grant admin consent.
  2. Create a client secret for the Entra App and set ENTRA_APP_CLIENT_SECRET
     in the Container App environment (see terraform/aca.tf).
"""

import contextvars
import json
import logging
import os
import sys
import time
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

try:
    from azure.identity import DefaultAzureCredential, OnBehalfOfCredential
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest
    from azure.mgmt.resource import ResourceManagementClient
except ImportError as e:
    logger.error(f"Azure SDK not found: {e}")
    sys.exit(1)

ComputeManagementClient = None
StorageManagementClient = None
KeyVaultManagementClient = None
KvSecretClient = None
ContainerServiceClient = None
SecurityCenter = None
AdvisorManagementClient = None

_svc_import_errors: list[str] = []

for _pkg, _sym, _mod in [
    ("azure-mgmt-compute",          "ComputeManagementClient",   "azure.mgmt.compute"),
    ("azure-mgmt-storage",          "StorageManagementClient",   "azure.mgmt.storage"),
    ("azure-mgmt-keyvault",         "KeyVaultManagementClient",  "azure.mgmt.keyvault"),
    ("azure-keyvault-secrets",      "KvSecretClient",            "azure.keyvault.secrets"),
    ("azure-mgmt-containerservice", "ContainerServiceClient",    "azure.mgmt.containerservice"),
    ("azure-mgmt-security",         "SecurityCenter",            "azure.mgmt.security"),
    ("azure-mgmt-advisor",          "AdvisorManagementClient",   "azure.mgmt.advisor"),
]:
    try:
        import importlib as _il
        _m = _il.import_module(_mod)
        _cls_name = "SecretClient" if _sym == "KvSecretClient" else _sym
        globals()[_sym] = getattr(_m, _cls_name)
        logger.info(f"Loaded: {_sym}")
    except Exception as _e:
        _svc_import_errors.append(f"{_pkg}: {_e}")
        logger.warning(f"Optional SDK not available — {_pkg}: {_e}")

try:
    import httpx
    import jwt
    from jwt.algorithms import RSAAlgorithm
    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route
except ImportError as e:
    logger.error(f"Required packages not found: {e}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Module-level MI clients (fallback for agent / M2M callers)
# ---------------------------------------------------------------------------
_credential: Any = None
_rg_client: Any = None


def _init_azure_clients() -> None:
    global _credential, _rg_client
    try:
        _credential = DefaultAzureCredential()
        sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
        if sub_id:
            _rg_client = ResourceGraphClient(_credential)
            logger.info(f"Azure clients initialized for subscription: {sub_id}")
        else:
            logger.warning("AZURE_SUBSCRIPTION_ID not set — query tools will be unavailable")
    except Exception as e:
        logger.error(f"Failed to init Azure clients: {e}")


# ---------------------------------------------------------------------------
# Per-request credential context vars (set in mcp_endpoint, read by tools)
# contextvars are safe for async: each request coroutine has its own context.
# ---------------------------------------------------------------------------
_ctx_credential: contextvars.ContextVar[Any] = contextvars.ContextVar("credential")
_ctx_rg_client: contextvars.ContextVar[Any] = contextvars.ContextVar("rg_client")


def _make_request_credential(caller_token: str | None) -> tuple[Any, Any]:
    """Return (credential, rg_client) for this request.

    OBO path: caller token has 'scp' (delegated) claim AND
              ENTRA_APP_CLIENT_SECRET is configured.
    Fallback:  server's User-Assigned MI — all callers share the same view.
    """
    client_secret = os.environ.get("ENTRA_APP_CLIENT_SECRET", "")
    tenant_id     = os.environ.get("AZURE_TENANT_ID", "")
    client_id     = os.environ.get("ENTRA_APP_CLIENT_ID", "")
    sub_id        = os.environ.get("AZURE_SUBSCRIPTION_ID", "")

    if caller_token and client_secret and tenant_id and client_id:
        try:
            # Decode without signature verification — already validated upstream.
            claims = jwt.decode(caller_token, options={"verify_signature": False})
            if "scp" in claims:
                # Delegated (human user) token — use OBO so Azure enforces the
                # caller's own RBAC instead of the server MI's permissions.
                obo_cred = OnBehalfOfCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                    user_assertion=caller_token,
                )
                obo_rg = ResourceGraphClient(obo_cred) if sub_id else None
                logger.info(f"OBO credential active for oid={claims.get('oid', '?')!r}")
                return obo_cred, obo_rg
        except Exception as e:
            logger.warning(f"OBO setup failed, falling back to MI credential: {e}")

    # App token (managed identity / client-credentials) or no secret configured.
    return _credential, _rg_client


# ---------------------------------------------------------------------------
# Helper: auto-detect latest stable API version for a resource type
# ---------------------------------------------------------------------------
def _detect_api_version(credential: Any, subscription_id: str, resource_type: str) -> str:
    try:
        client = ResourceManagementClient(credential, subscription_id)
        parts = resource_type.split("/")
        namespace = parts[0]
        type_name = "/".join(parts[1:])
        provider = client.providers.get(namespace)
        for rt in (provider.resource_types or []):
            if rt.resource_type and rt.resource_type.lower() == type_name.lower():
                versions = [v for v in (rt.api_versions or []) if "preview" not in v.lower()]
                if versions:
                    return sorted(versions)[-1]
    except Exception:
        pass
    return "2021-04-01"


# ---------------------------------------------------------------------------
# Tool implementations — Resource Graph / KQL
# ---------------------------------------------------------------------------
async def _generate_query(requirement: str) -> str:
    """Convert natural language to an Azure Resource Graph KQL query."""
    templates = {
        "virtual machine":  'Resources | where type == "microsoft.compute/virtualmachines"',
        "storage account":  'Resources | where type == "microsoft.storage/storageaccounts"',
        "resource group":   'ResourceContainers | where type == "microsoft.resources/subscriptions/resourcegroups"',
        "stopped":          'Resources | where type == "microsoft.compute/virtualmachines" | where properties.extended.instanceView.powerState.displayStatus == "VM deallocated"',
        "public ip":        'Resources | where type == "microsoft.network/publicipaddresses"',
        "key vault":        'Resources | where type == "microsoft.keyvault/vaults"',
        "sql":              'Resources | where type contains "microsoft.sql"',
        "web app":          'Resources | where type == "microsoft.web/sites" | where kind !contains "functionapp"',
        "function":         'Resources | where type == "microsoft.web/sites" | where kind contains "functionapp"',
        "aks":              'Resources | where type == "microsoft.containerservice/managedclusters"',
        "network":          'Resources | where type startswith "microsoft.network"',
        "container":        'Resources | where type startswith "microsoft.containerinstance" or type startswith "microsoft.containerservice"',
    }
    req = requirement.lower()
    for key, query in templates.items():
        if key in req:
            return query
    return "Resources | limit 10"


async def _validate_query(query: str) -> str:
    """Check KQL syntax before execution."""
    if not query.strip():
        return "Error: Query cannot be empty"
    if not query.strip().lower().startswith(("resources", "resourcecontainers")):
        return "Error: Query must start with 'Resources' or 'ResourceContainers'"
    return "Valid: Query syntax is correct"


async def _execute_query(query: str, subscription_ids: list | None = None) -> str:
    """Run an Azure Resource Graph KQL query across subscriptions."""
    validation = await _validate_query(query)
    if validation.startswith("Error"):
        return validation

    rg_client = _ctx_rg_client.get(None) or _rg_client
    if not rg_client:
        return "Error: Azure Resource Graph client not initialized. Ensure AZURE_SUBSCRIPTION_ID is set."
    try:
        request = QueryRequest(query=query, subscriptions=subscription_ids or None)
        result = rg_client.resources(request)
        data = result.data if hasattr(result, "data") else []
        return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Query execution failed: {e}", exc_info=True)
        return f"Error executing query: {e}"


# ---------------------------------------------------------------------------
# Tool implementations — ARM Template Deployments
# ---------------------------------------------------------------------------
async def _create_template_deployment(
    subscription_id: str,
    resource_group: str,
    deployment_name: str,
    template: dict,
) -> str:
    """Deploy an ARM template into a resource group."""
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ResourceManagementClient(credential, subscription_id)
        poller = client.deployments.begin_create_or_update(
            resource_group,
            deployment_name,
            {"properties": {"mode": "Incremental", "template": template}},
        )
        result = poller.result()
        return json.dumps({
            "id": result.id,
            "name": result.name,
            "provisioning_state": result.properties.provisioning_state,
        }, indent=2)
    except Exception as e:
        logger.error(f"Deployment failed: {e}", exc_info=True)
        return f"Error creating deployment: {e}"


async def _get_arm_template_deployment_status(
    subscription_id: str,
    resource_group: str,
    deployment_name: str,
) -> str:
    """Poll the status of an ARM template deployment."""
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ResourceManagementClient(credential, subscription_id)
        deployment = client.deployments.get(resource_group, deployment_name)
        return json.dumps({
            "id": deployment.id,
            "name": deployment.name,
            "provisioning_state": deployment.properties.provisioning_state,
        }, indent=2)
    except Exception as e:
        return f"Error getting deployment status: {e}"


async def _cancel_arm_template_deployment(
    subscription_id: str,
    resource_group: str,
    deployment_name: str,
) -> str:
    """Cancel an in-progress ARM template deployment."""
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ResourceManagementClient(credential, subscription_id)
        client.deployments.cancel(resource_group, deployment_name)
        return json.dumps({"status": "Deployment cancelled"}, indent=2)
    except Exception as e:
        return f"Error cancelling deployment: {e}"


# ---------------------------------------------------------------------------
# Tool implementations — Subscriptions & Resource Groups
# ---------------------------------------------------------------------------
async def _list_subscriptions() -> str:
    """List all Azure subscriptions accessible to the caller via Resource Graph."""
    rg_client = _ctx_rg_client.get(None) or _rg_client
    if not rg_client:
        return "Error: Resource Graph client not initialized."
    try:
        request = QueryRequest(
            query=(
                "ResourceContainers"
                " | where type == 'microsoft.resources/subscriptions'"
                " | project subscriptionId=name,"
                "   displayName=tostring(properties.displayName),"
                "   state=tostring(properties.state),"
                "   tenantId=tostring(properties.tenantId)"
            )
        )
        result = rg_client.resources(request)
        return json.dumps(result.data or [], indent=2, default=str)
    except Exception as e:
        return f"Error listing subscriptions: {e}"


async def _list_resource_groups(subscription_id: str) -> str:
    """List all resource groups in a subscription."""
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ResourceManagementClient(credential, subscription_id)
        groups = list(client.resource_groups.list())
        return json.dumps([{
            "name": g.name,
            "location": g.location,
            "id": g.id,
            "provisioning_state": g.properties.provisioning_state if g.properties else None,
            "tags": g.tags,
        } for g in groups], indent=2, default=str)
    except Exception as e:
        return f"Error listing resource groups: {e}"


async def _get_resource(resource_id: str, api_version: str | None = None) -> str:
    """Get full details of a specific Azure resource by its resource ID."""
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        parts = resource_id.split("/")
        sub_idx = next((i for i, p in enumerate(parts) if p.lower() == "subscriptions"), -1)
        if sub_idx == -1:
            return "Error: Invalid resource ID — must contain /subscriptions/{id}/..."
        subscription_id = parts[sub_idx + 1]

        if not api_version:
            prov_idx = next((i for i, p in enumerate(parts) if p.lower() == "providers"), -1)
            if prov_idx != -1 and len(parts) > prov_idx + 2:
                resource_type = f"{parts[prov_idx + 1]}/{parts[prov_idx + 2]}"
                api_version = _detect_api_version(credential, subscription_id, resource_type)
            else:
                api_version = "2021-04-01"

        client = ResourceManagementClient(credential, subscription_id)
        resource = client.resources.get_by_id(resource_id, api_version)
        return json.dumps({
            "id": resource.id,
            "name": resource.name,
            "type": resource.type,
            "location": resource.location,
            "tags": resource.tags,
            "properties": resource.properties,
        }, indent=2, default=str)
    except Exception as e:
        return f"Error getting resource: {e}"


async def _update_resource_tags(resource_id: str, tags: dict) -> str:
    """Merge or replace tags on any Azure resource by its resource ID."""
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        parts = resource_id.split("/")
        sub_idx = next((i for i, p in enumerate(parts) if p.lower() == "subscriptions"), -1)
        if sub_idx == -1:
            return "Error: Invalid resource ID — must contain /subscriptions/{id}/..."
        subscription_id = parts[sub_idx + 1]
        client = ResourceManagementClient(credential, subscription_id)
        result = client.tags.update_at_scope(
            resource_id,
            {"operation": "Merge", "properties": {"tags": tags}},
        )
        return json.dumps({
            "status": "Tags updated",
            "tags": result.properties.tags if result.properties else tags,
        }, indent=2, default=str)
    except Exception as e:
        return f"Error updating tags: {e}"


# ---------------------------------------------------------------------------
# Tool implementations — Virtual Machines
# ---------------------------------------------------------------------------
async def _get_virtual_machine(subscription_id: str, resource_group: str, vm_name: str) -> str:
    """Get details and power state of a virtual machine."""
    if ComputeManagementClient is None:
        return "Error: azure-mgmt-compute package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ComputeManagementClient(credential, subscription_id)
        vm = client.virtual_machines.get(resource_group, vm_name, expand="instanceView")
        power_state = next(
            (s.display_status for s in (vm.instance_view.statuses or [])
             if s.code and s.code.startswith("PowerState/")),
            "Unknown",
        )
        return json.dumps({
            "id": vm.id,
            "name": vm.name,
            "location": vm.location,
            "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
            "os_type": str(vm.storage_profile.os_disk.os_type)
                if vm.storage_profile and vm.storage_profile.os_disk else None,
            "power_state": power_state,
            "tags": vm.tags,
        }, indent=2, default=str)
    except Exception as e:
        return f"Error getting VM: {e}"


async def _start_virtual_machine(subscription_id: str, resource_group: str, vm_name: str) -> str:
    """Start a stopped or deallocated virtual machine."""
    if ComputeManagementClient is None:
        return "Error: azure-mgmt-compute package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ComputeManagementClient(credential, subscription_id)
        poller = client.virtual_machines.begin_start(resource_group, vm_name)
        poller.result()
        return json.dumps({"status": "success", "message": f"VM '{vm_name}' started"}, indent=2)
    except Exception as e:
        return f"Error starting VM: {e}"


async def _stop_virtual_machine(subscription_id: str, resource_group: str, vm_name: str) -> str:
    """Stop and deallocate a virtual machine (stops compute billing)."""
    if ComputeManagementClient is None:
        return "Error: azure-mgmt-compute package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ComputeManagementClient(credential, subscription_id)
        poller = client.virtual_machines.begin_deallocate(resource_group, vm_name)
        poller.result()
        return json.dumps({"status": "success", "message": f"VM '{vm_name}' stopped and deallocated"}, indent=2)
    except Exception as e:
        return f"Error stopping VM: {e}"


async def _restart_virtual_machine(subscription_id: str, resource_group: str, vm_name: str) -> str:
    """Restart a running virtual machine."""
    if ComputeManagementClient is None:
        return "Error: azure-mgmt-compute package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ComputeManagementClient(credential, subscription_id)
        poller = client.virtual_machines.begin_restart(resource_group, vm_name)
        poller.result()
        return json.dumps({"status": "success", "message": f"VM '{vm_name}' restarted"}, indent=2)
    except Exception as e:
        return f"Error restarting VM: {e}"


# ---------------------------------------------------------------------------
# Tool implementations — Storage
# ---------------------------------------------------------------------------
async def _list_storage_accounts(subscription_id: str, resource_group: str | None = None) -> str:
    """List storage accounts in a subscription or resource group."""
    if StorageManagementClient is None:
        return "Error: azure-mgmt-storage package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = StorageManagementClient(credential, subscription_id)
        accounts = (
            list(client.storage_accounts.list_by_resource_group(resource_group))
            if resource_group else list(client.storage_accounts.list())
        )
        return json.dumps([{
            "name": a.name,
            "location": a.location,
            "id": a.id,
            "sku": a.sku.name if a.sku else None,
            "kind": str(a.kind),
            "access_tier": str(a.access_tier) if a.access_tier else None,
            "tags": a.tags,
        } for a in accounts], indent=2, default=str)
    except Exception as e:
        return f"Error listing storage accounts: {e}"


async def _list_storage_containers(
    subscription_id: str, resource_group: str, account_name: str
) -> str:
    """List blob containers in a storage account."""
    if StorageManagementClient is None:
        return "Error: azure-mgmt-storage package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = StorageManagementClient(credential, subscription_id)
        containers = list(client.blob_containers.list(resource_group, account_name))
        return json.dumps([{
            "name": c.name,
            "public_access": str(c.public_access),
            "last_modified": str(c.last_modified_time),
            "lease_state": str(c.lease_state) if c.lease_state else None,
        } for c in containers], indent=2, default=str)
    except Exception as e:
        return f"Error listing containers: {e}"


# ---------------------------------------------------------------------------
# Tool implementations — Key Vault
# ---------------------------------------------------------------------------
async def _list_key_vaults(subscription_id: str, resource_group: str | None = None) -> str:
    """List key vaults in a subscription or resource group."""
    if KeyVaultManagementClient is None:
        return "Error: azure-mgmt-keyvault package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = KeyVaultManagementClient(credential, subscription_id)
        vaults = (
            list(client.vaults.list_by_resource_group(resource_group))
            if resource_group else list(client.vaults.list_by_subscription())
        )
        return json.dumps([{
            "name": v.name,
            "location": v.location,
            "id": v.id,
            "vault_uri": v.properties.vault_uri if v.properties else None,
            "sku": v.properties.sku.name if (v.properties and v.properties.sku) else None,
            "tags": v.tags,
        } for v in vaults], indent=2, default=str)
    except Exception as e:
        return f"Error listing key vaults: {e}"


async def _list_key_vault_secrets(vault_name: str) -> str:
    """List secret names (not values) stored in a key vault."""
    if KvSecretClient is None:
        return "Error: azure-keyvault-secrets package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        vault_url = f"https://{vault_name}.vault.azure.net"
        client = KvSecretClient(vault_url=vault_url, credential=credential)
        secrets = list(client.list_properties_of_secrets())
        return json.dumps([{
            "name": s.name,
            "enabled": s.enabled,
            "expires_on": str(s.expires_on) if s.expires_on else None,
            "created_on": str(s.created_on) if s.created_on else None,
            "updated_on": str(s.updated_on) if s.updated_on else None,
        } for s in secrets], indent=2, default=str)
    except Exception as e:
        return f"Error listing secrets: {e}"


async def _get_key_vault_secret(vault_name: str, secret_name: str) -> str:
    """Retrieve the value of a secret from a key vault. Requires Key Vault Secrets User role."""
    if KvSecretClient is None:
        return "Error: azure-keyvault-secrets package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        vault_url = f"https://{vault_name}.vault.azure.net"
        client = KvSecretClient(vault_url=vault_url, credential=credential)
        secret = client.get_secret(secret_name)
        return json.dumps({
            "name": secret.name,
            "value": secret.value,
            "version": secret.properties.version,
            "enabled": secret.properties.enabled,
            "expires_on": str(secret.properties.expires_on) if secret.properties.expires_on else None,
        }, indent=2, default=str)
    except Exception as e:
        return f"Error getting secret: {e}"


# ---------------------------------------------------------------------------
# Tool implementations — Azure SQL
# ---------------------------------------------------------------------------
async def _list_sql_servers(subscription_id: str, resource_group: str | None = None) -> str:
    """List Azure SQL servers via Resource Graph."""
    query = "Resources | where type =~ 'microsoft.sql/servers'"
    if resource_group:
        query += f" | where resourceGroup =~ '{resource_group}'"
    query += (
        " | project name, location, id, resourceGroup,"
        " fqdn=tostring(properties.fullyQualifiedDomainName),"
        " version=tostring(properties.version),"
        " state=tostring(properties.state), tags"
    )
    return await _execute_query(query, [subscription_id])


async def _list_sql_databases(
    subscription_id: str, resource_group: str, server_name: str
) -> str:
    """List databases on an Azure SQL server via Resource Graph."""
    query = (
        "Resources"
        " | where type =~ 'microsoft.sql/servers/databases'"
        f" | where resourceGroup =~ '{resource_group}'"
        f" | where id contains '/servers/{server_name}/'"
        " | project name, location, id, sku=tostring(sku.name),"
        "   status=tostring(properties.status),"
        "   maxSizeBytes=tolong(properties.maxSizeBytes), tags"
    )
    return await _execute_query(query, [subscription_id])


# ---------------------------------------------------------------------------
# Tool implementations — AKS
# ---------------------------------------------------------------------------
async def _list_aks_clusters(subscription_id: str, resource_group: str | None = None) -> str:
    """List AKS (Azure Kubernetes Service) clusters in a subscription or resource group."""
    if ContainerServiceClient is None:
        return "Error: azure-mgmt-containerservice package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = ContainerServiceClient(credential, subscription_id)
        clusters = (
            list(client.managed_clusters.list_by_resource_group(resource_group))
            if resource_group else list(client.managed_clusters.list())
        )
        return json.dumps([{
            "name": c.name,
            "location": c.location,
            "id": c.id,
            "kubernetes_version": c.kubernetes_version,
            "provisioning_state": c.provisioning_state,
            "power_state": str(c.power_state.code) if c.power_state else None,
            "node_count": sum(p.count or 0 for p in (c.agent_pool_profiles or [])),
            "fqdn": c.fqdn,
            "tags": c.tags,
        } for c in clusters], indent=2, default=str)
    except Exception as e:
        return f"Error listing AKS clusters: {e}"


# ---------------------------------------------------------------------------
# Tool implementations — Microsoft Defender for Cloud
# ---------------------------------------------------------------------------
async def _list_defender_alerts(subscription_id: str, severity: str | None = None) -> str:
    """List Microsoft Defender for Cloud security alerts, optionally filtered by severity."""
    if SecurityCenter is None:
        return "Error: azure-mgmt-security package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = SecurityCenter(credential=credential, subscription_id=subscription_id)
        alerts = list(client.alerts.list())
        result = []
        for a in alerts:
            sev = str(a.severity) if a.severity else "Unknown"
            if severity and sev.lower() != severity.lower():
                continue
            result.append({
                "name": a.name,
                "display_name": getattr(a, "alert_display_name", None) or getattr(a, "display_name", None),
                "severity": sev,
                "status": str(a.status) if a.status else None,
                "compromised_entity": getattr(a, "compromised_entity", None),
                "time_generated": str(a.time_generated_utc) if getattr(a, "time_generated_utc", None) else None,
                "description": getattr(a, "description", None),
                "resource_ids": [
                    getattr(r, "azure_resource_id", None) or getattr(r, "id", None)
                    for r in (getattr(a, "resource_identifiers", None) or [])
                ],
            })
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return f"Error listing Defender alerts: {e}"


async def _get_defender_secure_score(subscription_id: str) -> str:
    """Get the Microsoft Defender for Cloud secure score for a subscription."""
    if SecurityCenter is None:
        return "Error: azure-mgmt-security package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = SecurityCenter(credential=credential, subscription_id=subscription_id)
        scores = list(client.secure_scores.list())
        result = []
        for s in scores:
            result.append({
                "name": s.name,
                "display_name": getattr(s, "display_name", None),
                "current_score": getattr(s, "current", None),
                "max_score": getattr(s, "max", None),
                "percentage": getattr(s, "percentage", None),
                "weight": getattr(s, "weight", None),
            })
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return f"Error getting Defender secure score: {e}"


async def _list_defender_recommendations(subscription_id: str) -> str:
    """List unhealthy Microsoft Defender for Cloud security assessment results."""
    if SecurityCenter is None:
        return "Error: azure-mgmt-security package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = SecurityCenter(credential=credential, subscription_id=subscription_id)
        scope = f"/subscriptions/{subscription_id}"
        assessments = list(client.assessments.list(scope=scope))
        result = []
        for a in assessments:
            status = getattr(a, "status", None)
            code = str(status.code) if status and status.code else None
            if code == "Healthy":
                continue
            resource_details = getattr(a, "resource_details", None)
            result.append({
                "name": a.name,
                "display_name": getattr(a, "display_name", None) or a.name,
                "status": code,
                "cause": getattr(status, "cause", None),
                "description": getattr(status, "description", None),
                "resource_id": getattr(resource_details, "id", None),
            })
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return f"Error listing Defender recommendations: {e}"


# ---------------------------------------------------------------------------
# Tool implementations — Azure Advisor
# ---------------------------------------------------------------------------
async def _list_advisor_recommendations(
    subscription_id: str, category: str | None = None
) -> str:
    """List Azure Advisor recommendations, optionally filtered by category."""
    if AdvisorManagementClient is None:
        return "Error: azure-mgmt-advisor package not available."
    credential = _ctx_credential.get(None) or _credential
    if not credential:
        return "Error: Azure credentials not initialized."
    try:
        client = AdvisorManagementClient(credential=credential, subscription_id=subscription_id)
        recs = list(client.recommendations.list())
        result = []
        for r in recs:
            cat = str(r.category) if getattr(r, "category", None) else None
            if category and cat and cat.lower() != category.lower():
                continue
            desc = getattr(r, "short_description", None)
            result.append({
                "id": r.id,
                "name": r.name,
                "category": cat,
                "impact": str(r.impact) if getattr(r, "impact", None) else None,
                "impacted_field": getattr(r, "impacted_field", None),
                "impacted_value": getattr(r, "impacted_value", None),
                "problem": getattr(desc, "problem", None),
                "solution": getattr(desc, "solution", None),
                "potential_benefits": getattr(r, "potential_benefits", None),
                "last_updated": str(r.last_updated) if getattr(r, "last_updated", None) else None,
            })
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return f"Error listing Advisor recommendations: {e}"


# ---------------------------------------------------------------------------
# MCP tool registry
# ---------------------------------------------------------------------------
_TOOLS = [
    # --- Resource Graph ---
    {
        "name": "generate_query",
        "description": "Convert a natural language requirement into an Azure Resource Graph KQL query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "requirement": {
                    "type": "string",
                    "description": "Natural language description of what to query",
                }
            },
            "required": ["requirement"],
        },
    },
    {
        "name": "validate_query",
        "description": "Check KQL syntax before execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "KQL query to validate"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "execute_query",
        "description": "Run an Azure Resource Graph KQL query to list or filter any Azure resources across subscriptions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "KQL query to execute"},
                "subscription_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of subscription IDs to scope the query",
                },
            },
            "required": ["query"],
        },
    },
    # --- ARM Deployments ---
    {
        "name": "create_template_deployment",
        "description": "Deploy an ARM template into a resource group.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "deployment_name": {"type": "string"},
                "template": {"type": "object", "description": "ARM template JSON object"},
            },
            "required": ["subscription_id", "resource_group", "deployment_name", "template"],
        },
    },
    {
        "name": "get_arm_template_deployment_status",
        "description": "Poll the status of an ARM template deployment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "deployment_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "deployment_name"],
        },
    },
    {
        "name": "cancel_arm_template_deployment",
        "description": "Cancel an in-progress ARM template deployment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "deployment_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "deployment_name"],
        },
    },
    # --- Subscriptions & Resource Groups ---
    {
        "name": "list_subscriptions",
        "description": "List all Azure subscriptions accessible to the caller.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_resource_groups",
        "description": "List all resource groups in a subscription.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string", "description": "Azure subscription ID"},
            },
            "required": ["subscription_id"],
        },
    },
    {
        "name": "get_resource",
        "description": "Get full details (properties, tags, location) of a specific Azure resource by its resource ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "Full Azure resource ID (e.g. /subscriptions/{sub}/resourceGroups/{rg}/providers/...)",
                },
                "api_version": {
                    "type": "string",
                    "description": "API version override — omit to auto-detect",
                },
            },
            "required": ["resource_id"],
        },
    },
    {
        "name": "update_resource_tags",
        "description": "Merge tags onto any Azure resource by its resource ID. Requires Tag Contributor role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "Full Azure resource ID",
                },
                "tags": {
                    "type": "object",
                    "description": "Key-value pairs to merge onto the resource",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["resource_id", "tags"],
        },
    },
    # --- Virtual Machines ---
    {
        "name": "get_virtual_machine",
        "description": "Get details and current power state of a virtual machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
    },
    {
        "name": "start_virtual_machine",
        "description": "Start a stopped or deallocated virtual machine. Requires Virtual Machine Contributor role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
    },
    {
        "name": "stop_virtual_machine",
        "description": "Stop and deallocate a virtual machine (stops compute billing). Requires Virtual Machine Contributor role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
    },
    {
        "name": "restart_virtual_machine",
        "description": "Restart a running virtual machine. Requires Virtual Machine Contributor role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "vm_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "vm_name"],
        },
    },
    # --- Storage ---
    {
        "name": "list_storage_accounts",
        "description": "List storage accounts in a subscription, optionally filtered by resource group.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {
                    "type": "string",
                    "description": "Optional — omit to list across the whole subscription",
                },
            },
            "required": ["subscription_id"],
        },
    },
    {
        "name": "list_storage_containers",
        "description": "List blob containers in a storage account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "account_name": {"type": "string", "description": "Storage account name"},
            },
            "required": ["subscription_id", "resource_group", "account_name"],
        },
    },
    # --- Key Vault ---
    {
        "name": "list_key_vaults",
        "description": "List key vaults in a subscription, optionally filtered by resource group.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {
                    "type": "string",
                    "description": "Optional — omit to list across the whole subscription",
                },
            },
            "required": ["subscription_id"],
        },
    },
    {
        "name": "list_key_vault_secrets",
        "description": "List the names (not values) of secrets stored in a key vault. Requires Key Vault Reader role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Key vault name (not the full URI)"},
            },
            "required": ["vault_name"],
        },
    },
    {
        "name": "get_key_vault_secret",
        "description": "Retrieve the value of a secret from a key vault. Requires Key Vault Secrets User role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Key vault name (not the full URI)"},
                "secret_name": {"type": "string", "description": "Name of the secret to retrieve"},
            },
            "required": ["vault_name", "secret_name"],
        },
    },
    # --- Azure SQL ---
    {
        "name": "list_sql_servers",
        "description": "List Azure SQL servers in a subscription, optionally filtered by resource group.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {
                    "type": "string",
                    "description": "Optional — omit to list across the whole subscription",
                },
            },
            "required": ["subscription_id"],
        },
    },
    {
        "name": "list_sql_databases",
        "description": "List databases on an Azure SQL server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {"type": "string"},
                "server_name": {"type": "string"},
            },
            "required": ["subscription_id", "resource_group", "server_name"],
        },
    },
    # --- AKS ---
    {
        "name": "list_aks_clusters",
        "description": "List AKS (Azure Kubernetes Service) clusters in a subscription, optionally filtered by resource group.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {
                    "type": "string",
                    "description": "Optional — omit to list across the whole subscription",
                },
            },
            "required": ["subscription_id"],
        },
    },
    # --- Defender for Cloud ---
    {
        "name": "list_defender_alerts",
        "description": "List Microsoft Defender for Cloud security alerts, optionally filtered by severity (High, Medium, Low, Informational).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "severity": {
                    "type": "string",
                    "description": "Optional severity filter: High, Medium, Low, or Informational",
                    "enum": ["High", "Medium", "Low", "Informational"],
                },
            },
            "required": ["subscription_id"],
        },
    },
    {
        "name": "get_defender_secure_score",
        "description": "Get the Microsoft Defender for Cloud secure score (current score, max score, and percentage) for a subscription.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
            },
            "required": ["subscription_id"],
        },
    },
    {
        "name": "list_defender_recommendations",
        "description": "List unhealthy Microsoft Defender for Cloud security assessment results (security recommendations) for a subscription.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
            },
            "required": ["subscription_id"],
        },
    },
    # --- Azure Advisor ---
    {
        "name": "list_advisor_recommendations",
        "description": "List Azure Advisor recommendations, optionally filtered by category (Cost, Security, Reliability, Performance, OperationalExcellence).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "category": {
                    "type": "string",
                    "description": "Optional category filter",
                    "enum": ["Cost", "Security", "Reliability", "Performance", "OperationalExcellence"],
                },
            },
            "required": ["subscription_id"],
        },
    },
]

_TOOL_DISPATCH = {
    # Resource Graph
    "generate_query":                     lambda args: _generate_query(**args),
    "validate_query":                     lambda args: _validate_query(**args),
    "execute_query":                      lambda args: _execute_query(**args),
    # ARM Deployments
    "create_template_deployment":         lambda args: _create_template_deployment(**args),
    "get_arm_template_deployment_status": lambda args: _get_arm_template_deployment_status(**args),
    "cancel_arm_template_deployment":     lambda args: _cancel_arm_template_deployment(**args),
    # Subscriptions & Resource Groups
    "list_subscriptions":                 lambda args: _list_subscriptions(),
    "list_resource_groups":               lambda args: _list_resource_groups(**args),
    "get_resource":                       lambda args: _get_resource(**args),
    "update_resource_tags":               lambda args: _update_resource_tags(**args),
    # Virtual Machines
    "get_virtual_machine":                lambda args: _get_virtual_machine(**args),
    "start_virtual_machine":              lambda args: _start_virtual_machine(**args),
    "stop_virtual_machine":               lambda args: _stop_virtual_machine(**args),
    "restart_virtual_machine":            lambda args: _restart_virtual_machine(**args),
    # Storage
    "list_storage_accounts":              lambda args: _list_storage_accounts(**args),
    "list_storage_containers":            lambda args: _list_storage_containers(**args),
    # Key Vault
    "list_key_vaults":                    lambda args: _list_key_vaults(**args),
    "list_key_vault_secrets":             lambda args: _list_key_vault_secrets(**args),
    "get_key_vault_secret":               lambda args: _get_key_vault_secret(**args),
    # SQL
    "list_sql_servers":                   lambda args: _list_sql_servers(**args),
    "list_sql_databases":                 lambda args: _list_sql_databases(**args),
    # AKS
    "list_aks_clusters":                  lambda args: _list_aks_clusters(**args),
    # Defender for Cloud
    "list_defender_alerts":               lambda args: _list_defender_alerts(**args),
    "get_defender_secure_score":          lambda args: _get_defender_secure_score(**args),
    "list_defender_recommendations":      lambda args: _list_defender_recommendations(**args),
    # Azure Advisor
    "list_advisor_recommendations":       lambda args: _list_advisor_recommendations(**args),
}


# ---------------------------------------------------------------------------
# MCP JSON-RPC protocol handler
# ---------------------------------------------------------------------------
async def _dispatch_message(msg: dict) -> dict | None:
    """Handle one JSON-RPC message; returns response dict or None for notifications."""
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if msg_id is None:
        logger.info(f"MCP notification: {method}")
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "azure-resource-manager", "version": "2.0.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": _TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = _TOOL_DISPATCH.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            }
        try:
            text = await handler(arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            }
        except Exception as e:
            logger.error(f"Tool '{tool_name}' failed: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


async def mcp_endpoint(request: Request) -> Response:
    """POST /mcp — MCP Streamable HTTP transport endpoint."""
    if request.method == "GET":
        return JSONResponse({"status": "ok", "server": "azure-resource-manager", "protocol": "MCP"})

    # Set per-request credential in context vars so tool functions pick it up.
    caller_token = request.scope.get("caller_token")
    cred, rg_c = _make_request_credential(caller_token)
    _ctx_credential.set(cred)
    _ctx_rg_client.set(rg_c)

    try:
        body = await request.body()
        if not body:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Empty request body"}},
                status_code=400,
            )
        data = json.loads(body)
        logger.info(f"MCP << {json.dumps(data)[:300]}")
    except json.JSONDecodeError as e:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}},
            status_code=400,
        )

    if isinstance(data, list):
        responses = [r for r in [await _dispatch_message(m) for m in data] if r is not None]
        if not responses:
            return Response(status_code=202)
        logger.info(f"MCP >> batch({len(responses)})")
        return JSONResponse(responses)

    resp = await _dispatch_message(data)
    if resp is None:
        return Response(status_code=202)
    logger.info(f"MCP >> {json.dumps(resp)[:300]}")
    return JSONResponse(resp)


# ---------------------------------------------------------------------------
# Entra ID Bearer token validation middleware (pure ASGI)
# ---------------------------------------------------------------------------
class EntraAuthMiddleware:
    """Pure ASGI middleware — validates Entra ID Bearer tokens on all endpoints
    except /health.  After successful validation the raw token is stored in
    scope["caller_token"] so mcp_endpoint can use it for the OBO flow.
    Disabled when AZURE_TENANT_ID or ENTRA_APP_CLIENT_ID is not set.
    JWKS keys are cached for one hour.
    """

    _jwks_keys: dict[str, Any] = {}
    _jwks_fetched_at: float = 0.0
    _JWKS_TTL: int = 3600

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/health":
            await self.app(scope, receive, send)
            return

        tenant_id = os.environ.get("AZURE_TENANT_ID", "")
        client_id = os.environ.get("ENTRA_APP_CLIENT_ID", "")
        if not tenant_id or not client_id:
            logger.warning("Auth disabled — AZURE_TENANT_ID/ENTRA_APP_CLIENT_ID not set")
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth_header = headers.get(b"authorization", b"").decode("latin-1")
        if not auth_header.startswith("Bearer "):
            await JSONResponse({"error": "Bearer token required"}, status_code=401)(scope, receive, send)
            return

        token = auth_header.removeprefix("Bearer ")
        try:
            header = jwt.get_unverified_header(token)
            public_key = await self._get_public_key(header.get("kid", ""), tenant_id)
            jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=[f"api://{client_id}", client_id],
                issuer=[
                    f"https://sts.windows.net/{tenant_id}/",
                    f"https://login.microsoftonline.com/{tenant_id}/v2.0",
                ],
            )
            # Store the validated token for the OBO flow in mcp_endpoint.
            scope["caller_token"] = token
            await self.app(scope, receive, send)
        except jwt.ExpiredSignatureError:
            await JSONResponse({"error": "Token has expired"}, status_code=401)(scope, receive, send)
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: {e}")
            await JSONResponse({"error": "Invalid token"}, status_code=401)(scope, receive, send)
        except Exception as e:
            logger.error(f"Auth error: {e}")
            await JSONResponse({"error": "Authentication error"}, status_code=500)(scope, receive, send)

    @classmethod
    async def _get_public_key(cls, kid: str, tenant_id: str) -> Any:
        now = time.monotonic()
        if now - cls._jwks_fetched_at > cls._JWKS_TTL or kid not in cls._jwks_keys:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
                    timeout=10.0,
                )
                resp.raise_for_status()
                jwks = resp.json()
            cls._jwks_keys = {
                k["kid"]: RSAAlgorithm.from_jwk(json.dumps(k))
                for k in jwks.get("keys", [])
                if k.get("kty") == "RSA"
            }
            cls._jwks_fetched_at = now
        if kid not in cls._jwks_keys:
            raise jwt.InvalidTokenError(f"No public key for kid={kid!r}")
        return cls._jwks_keys[kid]


# ---------------------------------------------------------------------------
# ASGI application
# ---------------------------------------------------------------------------
def build_app() -> Any:
    """Custom MCP Streamable HTTP transport at /mcp — no FastMCP transport layer."""
    _init_azure_clients()

    async def health(_request: Request) -> JSONResponse:
        obo_enabled = bool(os.environ.get("ENTRA_APP_CLIENT_SECRET"))
        payload: dict = {
            "status": "ok",
            "server": "azure-resource-manager",
            "version": "2.0.0",
            "tools": len(_TOOLS),
            "obo_enabled": obo_enabled,
        }
        if _svc_import_errors:
            payload["sdk_warnings"] = _svc_import_errors
        return JSONResponse(payload)

    starlette_app = Starlette(
        routes=[
            Route("/health", health),
            Route("/mcp", mcp_endpoint, methods=["GET", "POST"]),
        ]
    )
    return EntraAuthMiddleware(starlette_app)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    logger.info(f"Starting ARM MCP Server v2.0 on port {port} ({len(_TOOLS)} tools)")
    auth_status = (
        "enabled" if (os.environ.get("AZURE_TENANT_ID") and os.environ.get("ENTRA_APP_CLIENT_ID"))
        else "disabled (local dev)"
    )
    obo_status = (
        "enabled (human users get per-user Azure access)"
        if os.environ.get("ENTRA_APP_CLIENT_SECRET")
        else "disabled (all callers use server MI)"
    )
    logger.info(f"  Entra auth   : {auth_status}")
    logger.info(f"  OBO flow     : {obo_status}")
    app = build_app()
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
