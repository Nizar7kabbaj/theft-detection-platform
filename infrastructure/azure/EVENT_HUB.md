# Azure Event Hub — pose-events stream

## Resources

| Resource | Name | Tier | Region |
|---|---|---|---|
| Resource group | `rg-theft-detection` | — | Spain Central |
| Event Hub namespace | `theft-detection-eh-nk` | Basic, 1 TU | Spain Central |
| Event hub | `pose-events` | 2 partitions, 1-day retention | — |
| SAS policy | `send-only` | Send claim only | — |

## Connection

The send-only connection string lives in `backend/.env` as
`EVENTHUB_CONNECTION_STRING`. NOT committed to Git, NOT baked into Docker images.

## Consumers

- AI script publishes pose events to `pose-events` on every inferred frame.
- Backend consumes alerts from `pose-events` and writes them to MongoDB.
- Databricks reads `pose-events` into the Bronze layer (planned, post-meeting).

## Notes

- Region choice driven by Azure for Students policy: France Central and
  West Europe blocked, Spain Central allowed.
- Basic tier picked for cost (~$11/month, ~$130 across 12-month student credit).
- Send-only policy enforces least privilege: a leaked key cannot read data,
  delete the hub, or create resources.

---

## Cost discipline (2026-05-12)

Destroyed the Event Hub namespace `theft-detection-eh-nk` on 2026-05-12 to stop
idle costs ($0.36/day).

- Reason: Phase 5 streaming work paused. Client demo done. No active use case
  for a running Event Hub until the Terraform tickets in Epic 6 begin.
- Re-provisioning: the planned Terraform module for Event Hub and Service Bus
  will recreate identical resources from code.
- Total cost while running (2026-05-02 → 2026-05-12): ~$3.60.
- Resource group `rg-theft-detection` kept (empty resource groups are free).
- Verified empty via `az resource list --resource-group rg-theft-detection`.
- Budget alert set at $50 (50%/75%/90% thresholds) for the rest of the project.

Lesson: cloud resources cost money even when idle. Practice destroy + re-apply
discipline early on cheap services so it becomes instinct on expensive ones.
