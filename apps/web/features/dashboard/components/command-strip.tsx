import { Activity, Camera, Clock, ShieldCheck, Thermometer, Wifi } from "lucide-react"
import type { ReactNode } from "react"
import { Suspense } from "react"
import { FleetCells } from "@/features/dashboard/components/fleet-cells"
import { StoreClock } from "@/features/dashboard/components/store-clock"
import { cn } from "@/lib/utils"

type Tone = "default" | "success" | "warning" | "destructive" | "muted"

type CellProps = {
  icon: ReactNode
  label: string
  value: ReactNode
  note: string
  tone?: Tone
}

const TONE: Record<Tone, string> = {
  default: "text-foreground",
  success: "text-success",
  warning: "text-warning",
  destructive: "text-destructive",
  muted: "text-muted-foreground",
}

const ICON_BOX =
  "flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-secondary text-muted-foreground"

const VALUE_CLASS = "truncate font-mono text-lg leading-none tabular-nums"

export function Cell({ icon, label, value, note, tone = "default" }: CellProps) {
  return (
    <div className="flex min-w-0 items-center gap-3 border-border border-l px-4 py-3 first:border-l-0">
      <span aria-hidden="true" className={ICON_BOX}>
        {icon}
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <span className="font-mono text-[9px] text-muted-foreground uppercase leading-none tracking-[0.09em]">
          {label}
        </span>
        <span className={cn(VALUE_CLASS, tone === "muted" && "text-base", TONE[tone])}>
          {value}
        </span>
        <span className="truncate font-mono text-[10px] text-muted-foreground leading-none">
          {note}
        </span>
      </div>
    </div>
  )
}

function FleetFallback() {
  return (
    <>
      <Cell
        icon={<Camera aria-hidden="true" className="size-4" />}
        label="cameras online"
        value="reading"
        note="fleet state loading"
        tone="muted"
      />
      <Cell
        icon={<ShieldCheck aria-hidden="true" className="size-4" />}
        label="system health"
        value="reading"
        note="fleet state loading"
        tone="muted"
      />
    </>
  )
}

export function CommandStrip() {
  return (
    <div className="grid grid-cols-2 rounded-lg border border-border bg-card shadow-panel md:grid-cols-3 xl:grid-cols-6">
      <Cell
        icon={<Clock aria-hidden="true" className="size-4" />}
        label="store clock"
        value={<StoreClock />}
        note="utc · live"
      />
      <Suspense fallback={<FleetFallback />}>
        <FleetCells />
      </Suspense>
      <Cell
        icon={<Activity aria-hidden="true" className="size-4" />}
        label="average fps"
        value="no reading"
        note="metric not published"
        tone="muted"
      />
      <Cell
        icon={<Wifi aria-hidden="true" className="size-4" />}
        label="edge latency"
        value="no reading"
        note="metric not published"
        tone="muted"
      />
      <Cell
        icon={<Thermometer aria-hidden="true" className="size-4" />}
        label="edge temperature"
        value="no reading"
        note="metric not published"
        tone="muted"
      />
    </div>
  )
}
