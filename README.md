# ARM MCP Server — Azure AI Foundry Agent

A custom Python **Model Context Protocol (MCP) server** that exposes Azure Resource Manager (ARM) tools to an Azure AI Foundry agent. Deployed as an Azure Container App with Entra ID authentication.

---

## How it works

### Architecture flow diagram

```mermaid
flowchart TB
    subgraph Foundry["Azure AI Foundry"]
        Agent["Foundry Agent\n<your-agent-name>"]
        ProjectMI["Project Managed Identity"]
    end

    subgraph EntraID["Entra ID"]
        EntraApp["Entra App\napi://<YOUR_ENTRA_APP_CLIENT_ID>"]
        JWKS["JWKS Endpoint\nlogin.microsoftonline.com\n/discovery/v2.0/keys"]
    end

    subgraph ACA["Azure Container App — arm-mcp-server"]
        Envoy["Envoy Proxy\nTLS termination\nHTTPS → HTTP:8080"]

        subgraph PythonServer["mcp_server.py"]
            Middleware["EntraAuthMiddleware\nJWT validation\nJWKS cached 1 h"]
            Route["POST /mcp\nStreamable HTTP endpoint"]
            Dispatch["_dispatch_message()\nMCP JSON-RPC router"]

            subgraph MCPMethods["MCP methods"]
                M1["initialize\n→ server capabilities"]
                M2["tools/list\n→ 26 tool schemas"]
                M3["tools/call\n→ tool dispatch"]
            end

            subgraph ToolFns["Tool functions (26)"]
                F1["Resource Graph\ngenerate_query · validate_query · execute_query\nlist_subscriptions · list_sql_servers · list_sql_databases"]
                F2["ARM Deployments\ncreate · status · cancel"]
                F3["Subscriptions (ARM)\nlist_resource_groups · get_resource · update_resource_tags"]
                F4["Virtual Machines\nget · start · stop · restart"]
                F5["Storage\nlist_storage_accounts · list_storage_containers"]
                F6["Key Vault\nlist_key_vaults · list_key_vault_secrets · get_key_vault_secret"]
                F7["AKS\nlist_aks_clusters"]
                F8["Defender for Cloud\nlist_defender_alerts · get_defender_secure_score\nlist_defender_recommendations"]
                F9["Azure Advisor\nlist_advisor_recommendations"]
            end
        end
    end

    subgraph AzureServices["Azure Services"]
        MI_Cred["User-Assigned MI\nDefaultAzureCredential"]
        ARG["Azure Resource Graph\nResourceGraphClient"]
        ARM["Azure Resource Manager\nResourceManagementClient"]
        Compute["Azure Compute\nComputeManagementClient"]
        Storage["Azure Storage\nStorageManagementClient"]
        KV["Azure Key Vault\nKeyVaultManagementClient\nSecretClient"]
        AKS["Azure AKS\nContainerServiceClient"]
        Defender["Defender for Cloud\nSecurityCenter"]
        Advisor["Azure Advisor\nAdvisorManagementClient"]
    end

    ProjectMI -- "1 · request token\naudience: api://<YOUR_ENTRA_APP_CLIENT_ID>" --> EntraApp
    EntraApp -- "2 · Bearer token" --> Agent
    Agent -- "3 · POST /mcp\nAuthorization: Bearer ..." --> Envoy
    Envoy -- "4 · HTTP:8080" --> Middleware
    Middleware -. "cache miss:\nfetch public keys" .-> JWKS
    Middleware -- "5 · JWT valid → forward" --> Route
    Route --> Dispatch
    Dispatch --> M1
    Dispatch --> M2
    Dispatch --> M3
    M3 --> F1
    M3 --> F2
    M3 --> F3
    M3 --> F4
    M3 --> F5
    M3 --> F6
    M3 --> F7
    M3 --> F8
    M3 --> F9
    F1 --> ARG
    F2 --> ARM
    F3 --> ARM
    F4 --> Compute
    F5 --> Storage
    F6 --> KV
    F7 --> AKS
    F8 --> Defender
    F9 --> Advisor
    ARG --> MI_Cred
    ARM --> MI_Cred
    Compute --> MI_Cred
    Storage --> MI_Cred
    KV --> MI_Cred
    AKS --> MI_Cred
    Defender --> MI_Cred
    Advisor --> MI_Cred
```

### Component summary

| Component | Role |
|---|---|
| **Foundry Agent** | Sends MCP JSON-RPC requests; obtains Bearer token via its project managed identity |
| **Envoy Proxy** | Terminates TLS at the Container App ingress; forwards plain HTTP to port 8080 |
| **EntraAuthMiddleware** | Pure ASGI middleware; validates Entra Bearer tokens using cached JWKS public keys; bypassed when env vars unset (local dev) |
| **`_dispatch_message()`** | Routes JSON-RPC methods: `initialize`, `tools/list`, `tools/call`, `ping` |
| **Tool functions (26)** | `generate_query`/`validate_query` are pure Python; SQL and subscription tools use Resource Graph; VM/Storage/Key Vault/AKS/Defender/Advisor use dedicated Azure SDK clients |
| **DefaultAzureCredential** | Picks up the container's user-assigned MI (`AZURE_CLIENT_ID`) for all Azure SDK calls |

### MCP tools exposed

| Namespace | Tools | Description |
|---|---|---|
| **Resource Graph** | `generate_query` | Converts natural language to Azure Resource Graph KQL |
| | `validate_query` | Checks KQL syntax |
| | `execute_query` | Runs ARG KQL queries across subscriptions |
| **ARM Deployments** | `create_template_deployment` | Deploys an ARM template |
| | `get_arm_template_deployment_status` | Polls deployment status |
| | `cancel_arm_template_deployment` | Cancels an in-progress deployment |
| **Subscriptions** | `list_subscriptions` | Lists all accessible subscriptions (via Resource Graph) |
| | `list_resource_groups` | Lists resource groups in a subscription |
| | `get_resource` | Gets full details of any resource by resource ID |
| | `update_resource_tags` | Merges tags onto any resource |
| **Virtual Machines** | `get_virtual_machine` | Gets VM details and power state |
| | `start_virtual_machine` | Starts a stopped/deallocated VM |
| | `stop_virtual_machine` | Stops and deallocates a VM (stops billing) |
| | `restart_virtual_machine` | Restarts a running VM |
| **Storage** | `list_storage_accounts` | Lists storage accounts |
| | `list_storage_containers` | Lists blob containers in a storage account |
| **Key Vault** | `list_key_vaults` | Lists key vaults |
| | `list_key_vault_secrets` | Lists secret names in a vault (not values) |
| | `get_key_vault_secret` | Gets a secret value (requires Key Vault Secrets User role) |
| **Azure SQL** | `list_sql_servers` | Lists SQL servers (via Resource Graph) |
| | `list_sql_databases` | Lists databases on a SQL server (via Resource Graph) |
| **AKS** | `list_aks_clusters` | Lists AKS clusters |
| **Defender for Cloud** | `list_defender_alerts` | Lists security alerts, optionally filtered by severity (High/Medium/Low) |
| | `get_defender_secure_score` | Gets the current/max secure score and percentage for a subscription |
| | `list_defender_recommendations` | Lists unhealthy security assessment results (non-Healthy only) |
| **Azure Advisor** | `list_advisor_recommendations` | Lists Advisor recommendations, optionally filtered by category (Cost, Security, Reliability, Performance, OperationalExcellence) |

---

## Repository structure

```
├── deployment/
│   ├── mcp_server.py       # MCP server — Streamable HTTP transport + Entra auth middleware
│   ├── requirements.txt    # Python dependencies
│   └── Dockerfile          # Python 3.11-slim container, port 8080
│
└── terraform/
    ├── providers.tf              # azurerm + azuread + azapi providers
    ├── variables.tf              # All input variables (with descriptions)
    ├── locals.tf                 # Computed values
    ├── acr.tf                    # Azure Container Registry
    ├── identity.tf               # User-assigned managed identity + AcrPull
    ├── aca.tf                    # Container Apps Environment + Container App
    ├── rbac.tf                   # 18 role assignments across all Azure services (incl. Security Reader for Defender)
    ├── foundry.tf                # Foundry project MI → Entra App role assignment
    ├── foundry_mcp_connection.tf # MCP connection in the Foundry project
    ├── outputs.tf                # URLs, client IDs, build commands
    ├── terraform.tfvars.example  # Template — copy to terraform.tfvars and fill in values
    └── backend.hcl.example       # Template — copy to backend.hcl for local Terraform init
```

---

## Prerequisites

Install these tools before proceeding:

| Tool | Minimum version | Install |
|---|---|---|
| [Terraform](https://developer.hashicorp.com/terraform/install) | 1.5 | `winget install Hashicorp.Terraform` |
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) | 2.60 | `winget install Microsoft.AzureCLI` |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 24 | Required to build the container image locally |

Verify:

```powershell
terraform -version   # Terraform v1.5+
az --version         # azure-cli 2.60+
docker --version     # Docker 24+
```

### Required Azure permissions

Your account needs the following on the target subscription:

- **Owner** or **User Access Administrator** + **Contributor** — to create resources and role assignments

---

## Step 1 — Authenticate to Azure

```powershell
az login

# If you have multiple subscriptions, pin the correct one
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"

# Confirm
az account show --query "{name:name, id:id, tenantId:tenantId}"
```

---

## Step 2 — Set up the Entra App Registration

This server validates Bearer tokens issued for a specific Entra App Registration. You need to create one (or use an existing one) and note the following values for `terraform.tfvars`:

1. Go to [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID → App registrations → New registration**
2. Give it a name (e.g. `arm-mcp-server`) and click **Register**
3. Note the **Application (client) ID** → `entra_app_client_id`
4. Go to **Enterprise applications**, find your app, note the **Object ID** → `entra_app_service_principal_object_id`
5. In the App registration, go to **App roles → Create app role**:
   - Display name: `MCP.Access`
   - Allowed member types: `Applications`
   - Value: `MCP.Access`
   - Note the generated GUID → `entra_app_role_id`
6. Under **Expose an API**, set the Application ID URI to `api://<YOUR_ENTRA_APP_CLIENT_ID>`

---

## Step 3 — Configure `terraform.tfvars`

```powershell
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform/terraform.tfvars` and fill in your values:

```hcl
subscription_id = "<YOUR_SUBSCRIPTION_ID>"   # az account show --query id -o tsv
tenant_id       = "<YOUR_TENANT_ID>"         # az account show --query tenantId -o tsv

resource_group_name = "<YOUR_RESOURCE_GROUP>"
location            = "<YOUR_AZURE_REGION>"  # e.g. "eastus"

acr_name = "<YOUR_ACR_NAME>"                 # globally unique, e.g. "myarmmcpacr"

aca_name         = "arm-mcp-server"
aca_min_replicas = 0
aca_max_replicas = 3

# Optional: set to a management group name/ID to scope all RBAC roles at MG level
# so the server can query resources across ALL child subscriptions.
# Leave empty ("") to scope roles to the single subscription_id above.
management_group_id = ""

entra_app_client_id                   = "<YOUR_ENTRA_APP_CLIENT_ID>"
entra_app_service_principal_object_id = "<YOUR_ENTRA_APP_SP_OBJECT_ID>"
entra_app_role_id                     = "<YOUR_ENTRA_APP_ROLE_ID>"

foundry_project_resource_id = "/subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.CognitiveServices/accounts/<ACCOUNT>/projects/<PROJECT>"

storage_resource_id = "/subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.Storage/storageAccounts/<ACCOUNT>"
```

> **Note:** `terraform.tfvars` is gitignored — your real values will never be committed.

> **ACR name** must be globally unique across all Azure accounts. Append a short suffix if needed (e.g. `myarmmcp01`).

---

## Step 4 — Configure Terraform remote state (optional but recommended)

Terraform state is stored remotely in an Azure Blob container. Create the backend config:

```powershell
cp terraform/backend.hcl.example terraform/backend.hcl
```

Fill in `terraform/backend.hcl`:

```hcl
resource_group_name  = "<YOUR_RESOURCE_GROUP>"
storage_account_name = "<YOUR_STORAGE_ACCOUNT>"
container_name       = "tfstate"
key                  = "arm-mcp-server.tfstate"
```

Create the blob container if it doesn't exist:

```powershell
az storage container create `
  --name tfstate `
  --account-name <YOUR_STORAGE_ACCOUNT> `
  --auth-mode login
```

---

## Step 5 — Initialise Terraform

```powershell
cd terraform

# With remote state (recommended)
terraform init -backend-config=backend.hcl

# Without remote state (local state only)
terraform init -backend=false
```

Expected output:
```
Terraform has been successfully initialized!
```

---

## Step 6 — Preview the deployment plan

```powershell
terraform plan -out=tfplan
```

Review the plan. You should see approximately **23 resources** to create:

| Resource | Count |
|---|---|
| `azurerm_container_registry` | 1 |
| `azurerm_user_assigned_identity` | 1 |
| `azurerm_container_app_environment` | 1 |
| `azurerm_container_app` | 1 |
| `azurerm_role_assignment` | 17 |
| `azuread_app_role_assignment` | 1 |
| `azapi_resource` (Foundry connection) | 1 |

If you see errors in `plan`, the most common causes are:

- **ACR name already taken** — change `acr_name` in `terraform.tfvars`
- **Insufficient permissions** — ensure your account has Owner/UAA on the subscription
- **Resource group does not exist** — create it first:
  ```powershell
  az group create --name <YOUR_RESOURCE_GROUP> --location <YOUR_AZURE_REGION>
  ```

---

## Step 7 — Apply the infrastructure

```powershell
terraform apply tfplan
```

This takes approximately **3–5 minutes**. When complete, Terraform prints the outputs:

```
Outputs:

acr_login_server      = "<YOUR_ACR_NAME>.azurecr.io"
container_app_name    = "arm-mcp-server"
docker_build_command  = "az acr build --registry <YOUR_ACR_NAME> --image arm-mcp:latest ./deployment"
foundry_mcp_audience  = "api://<YOUR_ENTRA_APP_CLIENT_ID>"
foundry_mcp_endpoint  = "https://arm-mcp-server.<env-id>.<region>.azurecontainerapps.io/mcp"
mcp_endpoint          = "https://arm-mcp-server.<env-id>.<region>.azurecontainerapps.io/mcp"
health_endpoint       = "https://arm-mcp-server.<env-id>.<region>.azurecontainerapps.io/health"
```

Save these — you need them in later steps.

---

## Step 8 — Build and push the container image

The Container App was provisioned but has no image yet (it will show `Provisioning` until the image exists). Build and push from the **repository root**:

```powershell
# From the repo root (one level above terraform/)
cd ..

# Build and push directly to ACR (no local Docker daemon needed)
az acr build `
  --registry <YOUR_ACR_NAME> `
  --image arm-mcp:latest `
  ./deployment
```

Expected output ends with:
```
Run ID: ca1 was successful after Xs
```

---

## Step 9 — Restart the Container App to pull the new image

```powershell
az containerapp update `
  --name arm-mcp-server `
  --resource-group <YOUR_RESOURCE_GROUP> `
  --image <YOUR_ACR_NAME>.azurecr.io/arm-mcp:latest
```

---

## Step 10 — Verify the server is running

```powershell
# Get the health URL from Terraform output
$healthUrl = (terraform -chdir=terraform output -raw health_endpoint)

# Should return {"status":"ok","server":"azure-resource-manager","version":"2.0.0","tools":22}
Invoke-RestMethod $healthUrl

# Check Container App logs
az containerapp logs show `
  --name arm-mcp-server `
  --resource-group <YOUR_RESOURCE_GROUP> `
  --follow
```

---

## Step 11 — Connect the MCP server to your Foundry agent

The Terraform `foundry_mcp_connection.tf` creates the connection automatically. To confirm it exists:

```powershell
az rest `
  --method GET `
  --url "https://management.azure.com<YOUR_FOUNDRY_PROJECT_RESOURCE_ID>/connections?api-version=2025-04-01-preview"
```

If the `azapi` schema needs adjusting, add the connection manually in the portal:

1. Go to **[ai.azure.com/nextgen](https://ai.azure.com/nextgen)**
2. Open your Foundry project
3. **Build → Agent → Tools → Add → Custom → Model Context Protocol**
4. Fill in:

   | Field | Value |
   |---|---|
   | Remote MCP Server endpoint | value of `foundry_mcp_endpoint` output |
   | Authentication | **Microsoft Entra → Project Managed Identity** |
   | Audience | value of `foundry_mcp_audience` output (`api://<YOUR_ENTRA_APP_CLIENT_ID>`) |

5. Click **Connect**

---

## Step 12 — Test from the Foundry agent

In the Foundry agent chat, try these prompts:

```
What subscriptions do I have access to?
List all resource groups in my subscription
Show all virtual machines and their power state
Start the VM named "my-vm" in resource group "my-rg"
Stop and deallocate all VMs in resource group "dev-rg"
List all storage accounts and their containers
Show all Key Vaults and list the secrets in vault "my-vault"
List all AKS clusters and their node counts
Find all Azure SQL servers and list their databases
Show all resources with the tag environment=production
```

---

## Optional — Enable On-Behalf-Of (OBO) for per-user Azure access

By default every caller (including the Foundry agent) uses the server's User-Assigned Managed Identity, so everyone sees the same subscription-wide view.

The OBO flow changes this for **human users**: instead of the server MI, the caller's own Entra identity is used to query Azure. Each person only sees the resources their own Azure RBAC allows.

> **Foundry agent (managed identity) is unaffected** — agent tokens never carry an `scp` claim, so the server always falls back to the MI path for them regardless of whether OBO is enabled.

### When to enable OBO

| Scenario | Recommended setting |
|---|---|
| Only the Foundry agent calls this server | Default (OBO disabled) — no action needed |
| Human users also call the server directly | Enable OBO so each user sees only their own resources |

### How it works

```
Human user token  (scp claim present + ENTRA_APP_CLIENT_SECRET set)
  → OnBehalfOfCredential  → Azure enforces the user's own RBAC

Foundry agent MI token  (roles claim, no scp)
  → falls back to server User-Assigned MI  → subscription-wide view
```

### Step A — Create a client secret for the Entra App

1. Go to [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID → App registrations**
2. Open your App Registration
3. **Certificates & secrets → New client secret**
4. Set a description and expiry, then click **Add**
5. **Copy the secret value immediately** — it is only shown once

### Step B — Grant the API permission

1. In the same App registration, go to **API permissions → Add a permission**
2. Choose **Azure Service Management → Delegated permissions → user_impersonation**
3. Click **Add permissions**
4. Click **Grant admin consent for \<your tenant\>** and confirm

### Step C — Set the secret in Terraform and deploy

Open `terraform/terraform.tfvars` and uncomment the last line:

```hcl
entra_app_client_secret = "<paste secret value here>"
```

Apply the Terraform change (adds the secret to the Container App):

```powershell
cd terraform
terraform plan -out=tfplan   # should show ~1 change: secret + env var on the Container App
terraform apply tfplan
```

Then rebuild and push the container image to activate the updated code:

```powershell
# From the repo root
az acr build --registry <YOUR_ACR_NAME> --image arm-mcp:latest ./deployment

# Get the new image digest and update the Container App
$digest = az acr manifest list-metadata --registry <YOUR_ACR_NAME> --name arm-mcp `
  --orderby time_desc --top 1 --query "[0].digest" -o tsv

az containerapp update `
  --name arm-mcp-server `
  --resource-group <YOUR_RESOURCE_GROUP> `
  --image "<YOUR_ACR_NAME>.azurecr.io/arm-mcp@$digest"
```

### Step D — Verify OBO is active

The health endpoint reports whether OBO is enabled:

```powershell
Invoke-RestMethod "<YOUR_HEALTH_URL>"
# Expected: { "status": "ok", "server": "azure-resource-manager", "version": "2.0.0", "tools": 22, "obo_enabled": true }
```

The startup log also confirms:

```
OBO flow     : enabled (human users get per-user Azure access)
```

### Step E — Revoke OBO (revert to MI)

Remove the secret value from `terraform.tfvars` (set back to `""`), then re-apply and rebuild.

---

## CI/CD with GitHub Actions

The repository includes a workflow at [.github/workflows/deploy.yml](.github/workflows/deploy.yml) that automates every deployment step.

### How the pipeline works

```
push to main  ──►  changes job   detect which paths changed
                       │
                       ├── terraform job   (only when terraform/** changed)
                       │     terraform init  (Azure Blob remote state)
                       │     terraform validate → plan → apply
                       │
                       └── deploy job   (when deployment/** changed OR terraform just ran)
                             az acr build  →  wait  →  get digest
                             az containerapp update @sha256:…
                             curl /health  →  assert 26 tools loaded
```

Alternatively, trigger it manually from **Actions → Deploy ARM MCP Server → Run workflow** with per-phase checkboxes.

### One-time Azure setup

Run these commands once before the first workflow execution:

```bash
# 1. Create a service principal for GitHub Actions
az ad sp create-for-rbac --name "arm-mcp-github-actions" --skip-assignment

# 2. Grant Owner on the subscription (required for rbac.tf role assignments)
az role assignment create \
  --assignee <clientId> \
  --role Owner \
  --scope /subscriptions/<YOUR_SUBSCRIPTION_ID>

# 3. Add a federated credential for OIDC (replace <org>/<repo>)
az ad app federated-credential create \
  --id <appObjectId> \
  --parameters '{
    "name": "github-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:<org>/<repo>:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'

# 4. Create the Terraform remote state container
az storage container create \
  --name tfstate \
  --account-name <YOUR_STORAGE_ACCOUNT> \
  --auth-mode login

# 5. Grant the SP Storage Blob Data Contributor for Terraform state
az role assignment create \
  --assignee <clientId> \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/<YOUR_SUBSCRIPTION_ID>/resourceGroups/<YOUR_RESOURCE_GROUP>/providers/Microsoft.Storage/storageAccounts/<YOUR_STORAGE_ACCOUNT>
```

### Required GitHub secrets and variables

Go to **Settings → Secrets and variables → Actions** and add:

**Secrets** (encrypted):

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | Service principal client ID (from step 1 above) |
| `AZURE_TENANT_ID` | Your Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Your Azure subscription ID |

**Variables** (plain text — visible in logs):

| Variable | Value |
|---|---|
| `AZURE_RESOURCE_GROUP` | Resource group name (e.g. `rg-arm-mcp-server`) |
| `ACR_NAME` | Azure Container Registry name |
| `ACA_NAME` | Container App name (e.g. `arm-mcp-server`) |
| `TF_BACKEND_RESOURCE_GROUP` | Resource group containing the state storage account |
| `TF_BACKEND_STORAGE_ACCOUNT` | Storage account name for Terraform state |
| `HEALTH_URL` | Full `/health` URL (set this after the first deploy) |

> No client secret is stored — the workflow uses **OIDC federated credentials** to exchange a short-lived GitHub token for an Azure access token.

### What triggers each job

| Event | Terraform job | Deploy job |
|---|---|---|
| Push — only `terraform/**` changed | Runs | Runs (new infra needs fresh image) |
| Push — only `deployment/**` changed | Skipped | Runs |
| Push — both changed | Runs | Runs |
| Manual dispatch (`run_terraform=true`) | Runs | Skipped unless `run_deploy=true` |
| Manual dispatch (`run_deploy=true`) | Skipped | Runs |

---

## Updating the server code

The easiest way is to push to `main` — the GitHub Actions workflow detects changes in `deployment/` and runs the build + deploy automatically.

To update manually:

```powershell
az acr build --registry <YOUR_ACR_NAME> --image arm-mcp:latest ./deployment

$digest = az acr manifest list-metadata --registry <YOUR_ACR_NAME> --name arm-mcp `
  --orderby time_desc --top 1 --query "[0].digest" -o tsv

az containerapp update `
  --name arm-mcp-server `
  --resource-group <YOUR_RESOURCE_GROUP> `
  --image "<YOUR_ACR_NAME>.azurecr.io/arm-mcp@$digest"
```

---

## Updating Terraform infrastructure

The easiest way is to push to `main` — the workflow detects changes in `terraform/` and runs plan + apply automatically.

To update manually:

```powershell
cd terraform
terraform plan -out=tfplan   # review changes
terraform apply tfplan
```

---

## Destroying the infrastructure

```powershell
cd terraform
terraform destroy
```

> This removes the Container App, ACR, managed identity, and all role assignments. It does **not** delete the resource group, storage account, Foundry project, or Entra App registration (those are pre-existing shared resources).

---

## Troubleshooting

### GitHub Actions workflow fails on Azure login

Ensure the federated credential subject exactly matches:
```
repo:<org>/<repo>:ref:refs/heads/main
```
And that `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` are all set in repository secrets (not environment secrets).

### GitHub Actions workflow fails on `terraform init`

The `tfstate` container must exist in your storage account before the first run, and the service principal needs `Storage Blob Data Contributor` on that storage account. Run steps 4 and 5 from the one-time setup above. Also confirm the GitHub Variables `TF_BACKEND_RESOURCE_GROUP` and `TF_BACKEND_STORAGE_ACCOUNT` are set.

### Container App not starting

```powershell
az containerapp logs show --name arm-mcp-server --resource-group <YOUR_RESOURCE_GROUP>
```

Common causes:
- Image not yet pushed to ACR — run Step 8
- `AZURE_SUBSCRIPTION_ID` not set in the Container App environment — check `terraform/aca.tf`
- ACR name mismatch — verify `acr_name` in `terraform.tfvars` matches what was created

### `terraform apply` fails on role assignments

Role assignment conflicts occur when a role + scope + principal combination already exists from a previous apply. Run:

```powershell
terraform state list | Select-String "role_assignment"
```

Import conflicting assignments or remove them from state:

```powershell
terraform state rm azurerm_role_assignment.<name>
terraform import azurerm_role_assignment.<name> /subscriptions/.../roleAssignments/<guid>
```

### Foundry agent gets 401 from MCP server

The Entra App role assignment for the Foundry project MI may not have propagated yet (can take up to 5 minutes). Check:

```powershell
az ad app permission list-grants --id <YOUR_ENTRA_APP_CLIENT_ID>
```

### `az acr build` fails — ACR not found

The ACR name must match exactly. Get the actual name:

```powershell
terraform -chdir=terraform output acr_login_server
```

---

## Infrastructure overview

```
<YOUR_RESOURCE_GROUP>  (existing resource group)
│
├── <YOUR_ACR_NAME>               Azure Container Registry (Basic)
│
├── arm-mcp-server-mi             User-Assigned Managed Identity
│   ├── AcrPull                       → <YOUR_ACR_NAME>
│   ├── Reader                        → subscription (covers all ARM namespaces)
│   ├── Virtual Machine Contributor   → subscription (start/stop/restart VMs)
│   ├── Tag Contributor               → subscription (update resource tags)
│   ├── Storage Blob Data Reader      → <YOUR_STORAGE_ACCOUNT>
│   ├── Storage Queue/Table Data Reader → <YOUR_STORAGE_ACCOUNT>
│   ├── Key Vault Secrets User        → subscription
│   ├── Key Vault Reader              → subscription
│   ├── Cognitive Services User       → subscription
│   ├── Azure Service Bus Data Receiver → subscription
│   ├── EventGrid Data Reader         → subscription
│   ├── Azure Event Hubs Data Receiver  → subscription
│   ├── Cosmos DB Account Reader      → subscription
│   ├── Log Analytics Reader          → subscription
│   └── Monitoring Reader             → subscription
│
├── arm-mcp-server-env            Container Apps Environment
│
└── arm-mcp-server                Container App
    ├── Image: <YOUR_ACR_NAME>.azurecr.io/arm-mcp:latest
    ├── Port: 8080 (HTTPS external)
    ├── /mcp    — MCP Streamable HTTP endpoint
    ├── /health — health probe
    └── Identity: arm-mcp-server-mi

Foundry project: <YOUR_FOUNDRY_PROJECT>
└── connections/arm-mcp-server    MCP connection → Container App URL
    └── Entra App role assignment → Foundry project MI can obtain tokens
```
