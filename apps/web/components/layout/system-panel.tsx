"use client"

import { Cpu, HardDrive, MonitorCog, Wifi } from "lucide-react"
import type { ComponentType } from "react"

const TILE_CLASS = "flex flex-col gap-2 border-border border-r border-b p-3 last:border-r-0"

const SPARK_CLASS = "h-8 w-full rounded-sm bg-muted/60"

const ROW_CLASS = "flex items-center gap-3 px-3 py-1.5"

const TRACK_CLASS = "h-1 flex-1 rounded-full bg-muted"

const METRICS: readonly {
  key: string
  label: string
  icon: ComponentType<{ className?: string }>
  tone: string
}[] = [
  { key: "cpu", label: "cpu", icon: Cpu, tone: "text-chart-1" },
  { key: "gpu", label: "gpu", icon: MonitorCog, tone: "text-chart-2" },
  { key: "memory", label: "memory", icon: HardDrive, tone: "text-chart-4" },
  { key: "network", label: "network", icon: Wifi, tone: "text-chart-5" },
]

const SERVICES: readonly string[] = ["camera", "detect gate", "inference", "notification"]

export function SystemPanel({ connection }: { connection: string }) {
  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-3 py-2.5">
        <span className="font-medium text-[0.8125rem]/5 text-foreground">system monitor</span>
        <span className="text-[0.6875rem]/4 text-muted-foreground">{connection}</span>
      </div>
      <div className="grid grid-cols-2 border-border border-t">
        {METRICS.map((metric) => (
          <div key={metric.key} className={TILE_CLASS}>
            <div className="flex items-center gap-1.5">
              <metric.icon className={`size-3.5 shrink-0 ${metric.tone}`} />
              <span className="text-[0.6875rem]/4 text-muted-foreground">{metric.label}</span>
              <span className="ml-auto text-[0.6875rem]/4 text-muted-foreground/70">--</span>
            </div>
            <div aria-hidden="true" className={SPARK_CLASS} />
          </div>
        ))}
      </div>
      <div className="flex flex-col py-2">
        <span className="px-3 pb-1 text-[0.6875rem]/4 text-muted-foreground uppercase tracking-wider">
          per service memory
        </span>
        {SERVICES.map((service) => (
          <div key={service} className={ROW_CLASS}>
            <span className="w-28 shrink-0 truncate text-[0.75rem]/5 text-foreground">
              {service}
            </span>
            <span aria-hidden="true" className={TRACK_CLASS} />
            <span className="w-12 shrink-0 text-right text-[0.6875rem]/4 text-muted-foreground/70">
              --
            </span>
          </div>
        ))}
      </div>
      <p className="border-border border-t px-3 py-2 text-[0.6875rem]/4 text-muted-foreground">
        awaiting telemetry
      </p>
    </div>
  )
}
