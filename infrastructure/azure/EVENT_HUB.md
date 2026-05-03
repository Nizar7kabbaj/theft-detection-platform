# Azure Event Hub — pose-events stream

## Resources

| Resource | Name | Tier | Region |
|---|---|---|---|
| Resource group | `rg-theft-detection` | — | Spain Central |
| Event Hub namespace | `theft-detection-eh-nk` | Basic, 1 TU | Spain Central |
| Event hub | `pose-events` | 2 partitions, 1-day retention | — |
| SAS policy | `send-only` | Send claim only | — |

## Connection

The send-only connection string is stored in `backend/.env` as
`EVENTHUB_CONNECTION_STRING`. NOT committed to Git, NOT baked into Docker images.

## Consumers

- **TDP-43:** AI script publishes pose events to `pose-events`
- **TDP-44:** backend consumes alerts from `pose-events`
- **TDP-45+:** Databricks reads `pose-events` into Bronze layer

## Notes

- Region choice driven by Azure for Students policy: France Central and
  West Europe blocked, Spain Central allowed.
- Basic tier chosen for cost (~$11/month, ~$130 across 12-month student credit).
- Send-only policy enforces principle of least privilege: a leaked key
  cannot read data, delete the hub, or create resources.