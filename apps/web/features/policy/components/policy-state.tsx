import { Card } from "@/components/ui/card"
import { relativeTime } from "@/features/policy/lib/format"
import type { PolicyRuntime } from "@/features/policy/schemas/policy"
import { cn } from "@/lib/utils"

function edgeLabel(runtime: PolicyRuntime, version: number): string {
  if (runtime.version === null || runtime.version === undefined) {
    return "not reporting"
  }
  if (runtime.version === version) {
    return "in step"
  }
  const behind = version - runtime.version
  return behind > 0 ? `${behind} behind` : "ahead of saved"
}

export function PolicyState({
  version,
  changedBy,
  changedAt,
  runtime,
  renderedAt,
}: {
  version: number
  changedBy: string
  changedAt: string
  runtime: PolicyRuntime
  renderedAt: number
}) {
  const matched = runtime.version === version
  return (
    <Card
      className={cn(
        "grid grid-cols-1 gap-4 border-l-2 p-4 sm:grid-cols-2",
        matched ? "border-l-primary" : "border-l-destructive",
      )}
    >
      <div className="flex flex-col gap-1">
        <span className="text-[10px] text-muted-foreground uppercase tracking-widest">saved</span>
        <span className="font-mono text-foreground text-lg tabular-nums">version {version}</span>
        <span className="text-muted-foreground text-xs">
          {version === 0
            ? "no change recorded, running on service defaults"
            : `changed ${relativeTime(changedAt, renderedAt)} by ${changedBy}`}
        </span>
      </div>
      <div className="flex flex-col gap-1 sm:border-border/50 sm:border-l sm:pl-4">
        <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
          running on edge
        </span>
        <span className="font-mono text-foreground text-lg tabular-nums">
          {runtime.version === null || runtime.version === undefined
            ? "none"
            : `version ${runtime.version}`}
        </span>
        <span className="text-muted-foreground text-xs">
          {runtime.version === null || runtime.version === undefined
            ? "the detector has not reported a policy"
            : `applied ${relativeTime(runtime.applied_at, renderedAt)} on ${runtime.device ?? "unknown device"}, ${edgeLabel(runtime, version)}`}
        </span>
      </div>
    </Card>
  )
}
