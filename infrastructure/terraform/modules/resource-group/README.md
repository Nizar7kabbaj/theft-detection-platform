# resource-group

Creates one Azure resource group and, if asked, a delete lock on it. This is the
base module the other modules build on, so the tag and naming choices here set the
pattern for networking and security too.

## Usage

```hcl
module "rg" {
  source = "../../modules/resource-group"

  name        = "rg-theft-detection"
  location    = "francecentral"
  environment = "dev"

  tags = {
    owner = "nizar"
  }
}
```

## Inputs

| Name | Type | Default | Required |
|------|------|---------|----------|
| `name` | string | — | yes |
| `location` | string | `francecentral` | no |
| `environment` | string | — | yes |
| `project` | string | `theft-detection` | no |
| `tags` | map(string) | `{}` | no |
| `enable_delete_lock` | bool | `false` | no |

Every resource group gets three tags by default: `project`, `environment`, and
`managed_by = terraform`. Anything you pass in `tags` is merged on top and wins on
a key clash.

`enable_delete_lock` stays off on purpose. A `CanNotDelete` lock blocks
`terraform destroy`, and destroy-on-idle is how this project keeps the student
credit from bleeding. Turn it on only for something you never want destroyed.

## Outputs

| Name | Description |
|------|-------------|
| `id` | Resource group ID |
| `name` | Resource group name |
| `location` | Resource group region |

## Notes

The module declares its provider requirement in `versions.tf` but holds no
`provider` block. The provider gets configured once in the environment that calls
the module, not in the module itself.

The group `rg-theft-detection` already exists in France Central from earlier CLI
work. Adopting it into Terraform happens at environment wire-up with
`terraform import`, after the remote state backend is in place. This module only
defines the resource, so the check here is `fmt` plus `validate`, not a deploy.
