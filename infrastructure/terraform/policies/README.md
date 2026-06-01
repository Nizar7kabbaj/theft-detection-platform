# Policies

Policy-as-code guardrails for the Terraform stack in this repo.

## What's here

Two folders, same three rule sets in each.

`opa/` holds Rego policies that run via conftest against `terraform plan -json` output. These are the executable policies.

`sentinel/` holds Sentinel files that document the same rules in HashiCorp's policy language. Spec only. They don't run anywhere today because this project does not use Terraform Cloud or Terraform Enterprise.

The three rule sets:

- **cost-control** keeps the stack on the zero-cost-on-destroy path. No management locks, no key vault purge protection, no premium key vault SKU outside prod.
- **security-baseline** sets the minimum security floor. Key vault stays closed to the public internet, network ACLs default to Deny, RBAC authorization is mandatory, project tags are required on every taggable resource.
- **naming-conventions** requires every project resource to start with the right type prefix and live in spaincentral. Key vault names cap at 24 characters.

## Running the OPA policies

Install conftest:

    brew install conftest

or pull the binary from the OPA release page.

From an environment directory:

    terraform plan -out=tfplan.binary
    terraform show -json tfplan.binary > tfplan.json
    conftest test --policy ../../policies/opa tfplan.json
    rm tfplan.binary tfplan.json

The pre-commit wiring in a follow-up ticket will run this automatically.

## Running the Sentinel policies

Not wired. The files are reference in case this stack ever moves onto Terraform Cloud, where Sentinel runs natively. Local execution would need a Sentinel CLI license, which is not part of this project.

## Layout

    policies/
    ├── opa/
    │   ├── cost-control.rego
    │   ├── naming-conventions.rego
    │   └── security-baseline.rego
    └── sentinel/
        ├── cost-control.sentinel
        ├── naming-conventions.sentinel
        └── security-baseline.sentinel