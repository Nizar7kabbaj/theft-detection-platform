# scripts

Bootstrap and helper scripts for the Terraform setup.

## bootstrap-backend.sh

Creates the Azure storage account that holds Terraform remote state.
Run it once per workstation. Re-running is safe: the script checks
what already exists and re-applies the hardened settings without
recreating resources.

### What it creates

| Resource | Name | Notes |
|---|---|---|
| Resource group | `rg-tfstate-theft` | Separate from `rg-theft-detection` so `terraform destroy` on project resources never touches state |
| Storage account | `sttfstatetheft` | `Standard_LRS`, TLS 1.2 floor, public blob access off, shared-key auth off (AAD only) |
| Blob container | `tfstate` | Private (`publicAccess = None`) |
| Blob versioning | on | Recover from corrupted state pushes |
| Soft delete | 7 days | Both blobs and containers |
| RBAC | `Storage Blob Data Contributor` | Granted to the user running the script |

### Region

Default is `spaincentral`. The Azure for Students region allowlist
blocks `francecentral` for `Microsoft.Storage` resources, so the
state account lives in a different region from `rg-theft-detection`.
State has no latency requirement, so this is fine.

Override with `LOCATION=<region>` if needed:

```bash
LOCATION=westeurope ./bootstrap-backend.sh
```

### Prerequisites

- `az login` against the target subscription.
- `Microsoft.Storage` resource provider registered:
  `az provider register --namespace Microsoft.Storage`.
- `Microsoft.Authorization` resource provider registered (the role
  assignment step needs it).

### Running it

```bash
./infrastructure/terraform/scripts/bootstrap-backend.sh
```

Takes about 90 seconds. The slow step is a 30-second sleep after the
RBAC role assignment. AAD propagation needs that window before the
container create call can use the new permission.

### Verifying

```bash
az storage account show -n sttfstatetheft -g rg-tfstate-theft \
  --query "{tls:minimumTlsVersion, publicBlob:allowBlobPublicAccess, sharedKey:allowSharedKeyAccess}" \
  -o table
```

Expect `TLS1_2`, `False`, `False`.

### Tearing it down

The state backend is the one piece of infrastructure that does NOT
get destroyed by `terraform destroy`. It's bootstrap infra. By
definition it has to outlive the resources it tracks.

To delete it manually for true zero cost:

```bash
az group delete -n rg-tfstate-theft --yes
```

That destroys the storage account and all state history with it.
Only do this if you're abandoning the project, or you've already
exported state somewhere else.