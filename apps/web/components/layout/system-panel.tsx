"use client"
import { Collapsible } from "@base-ui/react/collapsible"
import { ChevronDown, Cpu, HardDrive, MonitorCog, Wifi } from "lucide-react"
import { type ComponentType, useEffect, useState } from "react"

const TILE_CLASS = "flex flex-col gap-2 border-border border-b p-3 odd:border-r"
const SPARK_CLASS = "h-8 w-full rounded-sm bg-muted/60"
const ROW_CLASS = "flex items-center gap-3 px-3 py-1.5"
const TRACK_CLASS = "h-1 flex-1 rounded-full bg-muted"
const VALUE_CLASS = "shrink-0 text-xs text-muted-foreground/70 tabular-nums"
const TRIGGER_CLASS =
  "flex w-full items-center gap-1.5 px-3 py-1 text-left text-muted-foreground text-xs uppercase tracking-wider outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
const CHEVRON_CLASS =
  "size-3.5 shrink-0 transition-transform duration-200 group-data-[panel-open]/services:rotate-0 -rotate-90"
const DOT_CLASS = "size-1.5 shrink-0 rounded-full"
const METRICS: readonly {
  key: string
  label: string
  icon: ComponentType<{ className?: string }>
  tone: string
}[] = [
  { key: "cpu", label: "cpu", icon: Cpu, tone: "text-chart-2" },
  { key: "gpu", label: "gpu", icon: MonitorCog, tone: "text-success" },
  { key: "memory", label: "memory", icon: HardDrive, tone: "text-destructive" },
  { key: "network", label: "network", icon: Wifi, tone: "text-chart-1" },
]
const SERVICES: readonly { key: string; label: string; tone: string }[] = [
  { key: "camera", label: "camera", tone: "bg-chart-2" },
  { key: "gate", label: "detect gate", tone: "bg-success" },
  { key: "inference", label: "inference", tone: "bg-destructive" },
  { key: "notification", label: "notification", tone: "bg-chart-1" },
]
function useClock(): string {
  const [now, setNow] = useState<string>("")
  useEffect(() => {
    const tick = () => {
      setNow(
        new Date().toLocaleTimeString(undefined, {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
      )
    }
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [])
  return now
}
export function SystemPanel() {
  const now = useClock()
  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-3 py-2.5">
        <span className="font-medium text-foreground text-sm">system monitor</span>
        <span className={VALUE_CLASS}>{now}</span>
      </div>
      <div className="grid grid-cols-2 border-border border-t">
        {METRICS.map((metric) => (
          <div key={metric.key} className={TILE_CLASS}>
            <div className="flex items-center gap-1.5">
              <metric.icon className={`size-3.5 shrink-0 ${metric.tone}`} />
              <span className="text-muted-foreground text-xs">{metric.label}</span>
              <span className={`ml-auto ${VALUE_CLASS}`}>--</span>
            </div>
            <div aria-hidden="true" className={SPARK_CLASS} />
          </div>
        ))}
      </div>
      <Collapsible.Root defaultOpen className="flex flex-col py-2">
        <Collapsible.Trigger className={`group/services ${TRIGGER_CLASS}`}>
          <ChevronDown aria-hidden="true" className={CHEVRON_CLASS} />
          per service memory
        </Collapsible.Trigger>
        <Collapsible.Panel className="flex flex-col">
          {SERVICES.map((service) => (
            <div key={service.key} className={ROW_CLASS}>
              <span aria-hidden="true" className={`${DOT_CLASS} ${service.tone}`} />
              <span className="w-24 shrink-0 truncate text-foreground text-xs">
                {service.label}
              </span>
              <span aria-hidden="true" className={TRACK_CLASS} />
              <span className={`w-12 text-right ${VALUE_CLASS}`}>--</span>
            </div>
          ))}
        </Collapsible.Panel>
      </Collapsible.Root>
      <p className="border-border border-t px-3 py-2 text-muted-foreground text-xs">
        awaiting telemetry
      </p>
    </div>
  )
}
