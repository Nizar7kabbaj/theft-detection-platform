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
get destroyed by `terraform destroy`. It's bootstrap infra — it has
to outlive the resources it tracks.

To delete it manually for true zero cost:

```bash
az group delete -n rg-tfstate-theft --yes
```

That destroys the storage account and all state history with it.
Only do this if you're abandoning the project, or you've already
exported state somewhere else.

## tf.sh

One script, every terraform command you actually run. The wrapper exists
because typing `cd infrastructure/terraform/environments/dev && terraform plan`
fifteen times a day gets old, and forgetting which subscription you're pointed
at is how people accidentally apply to prod.

### Usage

```bash
./tf.sh <env> <action> [terraform-args...]
```

`<env>` is a directory name under `environments/`. Right now: `dev` and `prod`.

Actions:

| Action | What it does |
|---|---|
| `init` | `terraform init` in the env directory |
| `fmt` | `terraform fmt -recursive` |
| `validate` | `terraform validate` |
| `plan` | Saves the plan to a `tfplan` file in the env directory |
| `apply` | Applies the saved `tfplan`. Refuses to run without one |
| `destroy` | Makes you type the env name back, then destroys |
| `output` | `terraform output` |
| `console` | `terraform console` |

Anything after the action is passed straight to terraform:

```bash
./tf.sh dev plan -var=enable_logs=true
```

### Wrappers

Three one-liners next to `tf.sh` that just forward arguments:

- `plan.sh dev` → `tf.sh dev plan`
- `apply.sh dev` → `tf.sh dev apply`
- `destroy.sh dev` → `tf.sh dev destroy`

Pick whichever reads better in your shell history.

### Plan-then-apply

`apply` only works against a saved plan file. The two-step is the point:

```bash
./tf.sh dev plan      # writes tfplan
# read the diff
./tf.sh dev apply     # applies that exact tfplan, then deletes it
```

No surprises between "what I reviewed" and "what got applied". It's slightly
more annoying than `terraform apply -auto-approve`. That's the trade. If
the plan is more than 30 minutes old, apply asks before using it, because
state can drift while you're at lunch.

### Guardrails

The script exits early if:

- Azure CLI isn't installed
- You're not logged in (`az login`)
- The current subscription doesn't match `AZURE_SUBSCRIPTION_ID` in `.tf-env`
- The environment directory doesn't exist

`destroy` won't run unless the confirmation string matches the env name.
Typing `dev` to destroy `prod` fails on purpose.

### Local config

The subscription check reads `.tf-env` at the repo root. It's gitignored.
Copy the example, drop your subscription ID in:

```bash
cp .tf-env.example .tf-env
# get your id:
az account show --query id -o tsv
# paste it into .tf-env
```

Without `.tf-env` the script still runs, just without the subscription
guard, and prints a warning so you know. Fine for a one-off, not what
you want as a habit.
