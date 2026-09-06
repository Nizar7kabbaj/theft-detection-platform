"use client"
import { Collapsible } from "@base-ui/react/collapsible"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, Cpu, HardDrive, MonitorCog, Wifi } from "lucide-react"
import { type ComponentType, useCallback, useEffect, useId, useState } from "react"
import {
  fetchSystemHistoryClient,
  systemHistoryQueryKey,
} from "@/features/analytics/api/system-history-client"
import {
  fetchSystemStatsClient,
  systemStatsQueryKey,
} from "@/features/analytics/api/system-stats-client"
import type { ServiceMemory, SystemStats } from "@/features/analytics/schemas/system-stats"
import { readCookie, writeCookie } from "@/lib/cookies/write"
import { STORE_TIME_ZONE } from "@/lib/time/zone"

const TILE_CLASS = "flex flex-col gap-2 border-border border-b p-3 odd:border-r"
const THERMAL_CLASS = "flex flex-col gap-1.5 p-3 odd:border-r"
const SPARK_CLASS = "h-8 w-full"
const THERMAL_SPARK_CLASS = "h-10 w-full"
const ROW_CLASS = "flex items-center gap-3 px-3 py-1.5"
const TRACK_CLASS = "h-1 flex-1 overflow-hidden rounded-full bg-muted"
const VALUE_CLASS = "shrink-0 text-xs tabular-nums"
const MUTED_VALUE_CLASS = `${VALUE_CLASS} text-muted-foreground/70`
const TRIGGER_CLASS =
  "flex w-full items-center gap-1.5 px-3 py-1 text-left text-muted-foreground text-xs uppercase tracking-wider outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
const CHEVRON_CLASS =
  "size-3.5 shrink-0 transition-transform duration-200 group-data-[panel-open]/services:rotate-0 -rotate-90"
const DOT_CLASS = "size-1.5 shrink-0 rounded-full"

const REFETCH_MS = 15_000
const KEEP_MS = 5 * 60_000
const SERVICES_COOKIE_NAME = "system_panel_services"
const SERVICES_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
const MEMORY_CEILING_BYTES = 2 * 1024 * 1024 * 1024
const SPARK_WIDTH = 100
const SPARK_HEIGHT = 32

type MetricKey = "cpu" | "gpu" | "memory" | "network"
type ThermalKey = "cpu_temperature" | "gpu_temperature"

const METRICS: readonly {
  key: MetricKey
  label: string
  icon: ComponentType<{ className?: string }>
  tone: string
  stroke: string
}[] = [
  { key: "cpu", label: "cpu", icon: Cpu, tone: "text-chart-2", stroke: "var(--chart-2)" },
  { key: "gpu", label: "gpu", icon: MonitorCog, tone: "text-success", stroke: "var(--success)" },
  {
    key: "memory",
    label: "memory",
    icon: HardDrive,
    tone: "text-destructive",
    stroke: "var(--destructive)",
  },
  { key: "network", label: "network", icon: Wifi, tone: "text-chart-1", stroke: "var(--chart-1)" },
]

const THERMALS: readonly {
  key: ThermalKey
  label: string
  tone: string
  stroke: string
}[] = [
  { key: "cpu_temperature", label: "cpu temp", tone: "text-chart-2", stroke: "var(--chart-2)" },
  { key: "gpu_temperature", label: "gpu temp", tone: "text-success", stroke: "var(--success)" },
]

const SERVICES: readonly { key: keyof ServiceMemory; label: string; tone: string }[] = [
  { key: "camera", label: "camera", tone: "bg-chart-2" },
  { key: "gate", label: "detect gate", tone: "bg-success" },
  { key: "inference", label: "inference", tone: "bg-destructive" },
  { key: "notification", label: "notification", tone: "bg-chart-1" },
]

function formatBytesPerSecond(value: number): string {
  if (value < 1024) {
    return `${Math.round(value)} B/s`
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB/s`
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB/s`
}

function formatMegabytes(value: number): string {
  return `${Math.round(value / (1024 * 1024))} MB`
}

function metricValue(key: MetricKey, stats: SystemStats | undefined): string {
  if (stats === undefined) {
    return "--"
  }
  if (key === "network") {
    const bytes = stats.network_bytes_per_second
    return bytes === null || bytes === undefined ? "--" : formatBytesPerSecond(bytes)
  }
  const percent =
    key === "cpu" ? stats.cpu_percent : key === "gpu" ? stats.gpu_percent : stats.memory_percent
  return percent === null || percent === undefined ? "--" : `${percent.toFixed(1)}%`
}

function thermalValue(key: ThermalKey, stats: SystemStats | undefined): string {
  if (stats === undefined) {
    return "--"
  }
  const celsius = key === "cpu_temperature" ? stats.cpu_temperature_c : stats.gpu_temperature_c
  return celsius === null || celsius === undefined ? "--" : `${celsius} c`
}

function buildPath(points: readonly number[]): { line: string; area: string } | null {
  if (points.length < 2) {
    return null
  }
  let low = Math.min(...points)
  let high = Math.max(...points)
  if (high === low) {
    high = low + 1
    low = Math.max(0, low - 1)
  }
  const span = high - low
  const step = SPARK_WIDTH / (points.length - 1)
  const coordinates = points.map((value, index) => {
    const x = index * step
    const y = SPARK_HEIGHT - ((value - low) / span) * SPARK_HEIGHT
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })
  const line = `M ${coordinates.join(" L ")}`
  const first = coordinates[0]
  const last = coordinates[coordinates.length - 1]
  if (first === undefined || last === undefined) {
    return null
  }
  const startX = first.split(",")[0] ?? "0"
  const endX = last.split(",")[0] ?? "0"
  return { line, area: `${line} L ${endX},${SPARK_HEIGHT} L ${startX},${SPARK_HEIGHT} Z` }
}

function Sparkline({
  points,
  stroke,
  className,
}: {
  points: readonly number[]
  stroke: string
  className: string
}) {
  const gradientId = useId()
  const path = buildPath(points)
  if (path === null) {
    return <div aria-hidden="true" className={`${className} rounded-sm bg-muted/60`} />
  }
  return (
    <svg
      aria-hidden="true"
      className={className}
      preserveAspectRatio="none"
      viewBox={`0 0 ${SPARK_WIDTH} ${SPARK_HEIGHT}`}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={path.area} fill={`url(#${gradientId})`} />
      <path
        d={path.line}
        fill="none"
        stroke={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

function useClock(): string {
  const [now, setNow] = useState<string>("")
  useEffect(() => {
    const tick = () => {
      setNow(
        new Date().toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          timeZone: STORE_TIME_ZONE,
        }),
      )
    }
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

function useServicesOpen(): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState<boolean>(() => readCookie(SERVICES_COOKIE_NAME) !== "0")
  const change = useCallback((next: boolean) => {
    setOpen(next)
    writeCookie(SERVICES_COOKIE_NAME, next ? "1" : "0", SERVICES_COOKIE_MAX_AGE)
  }, [])
  return [open, change]
}

export function SystemPanel() {
  const now = useClock()
  const [servicesOpen, setServicesOpen] = useServicesOpen()
  const { data } = useQuery({
    queryKey: systemStatsQueryKey,
    queryFn: ({ signal }) => fetchSystemStatsClient(signal),
    refetchInterval: REFETCH_MS,
    staleTime: REFETCH_MS,
    gcTime: KEEP_MS,
  })
  const { data: history } = useQuery({
    queryKey: systemHistoryQueryKey,
    queryFn: ({ signal }) => fetchSystemHistoryClient(signal),
    refetchInterval: REFETCH_MS,
    staleTime: REFETCH_MS,
  })

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-3 py-2.5">
        <span className="font-medium text-foreground text-sm">system monitor</span>
        <span className={MUTED_VALUE_CLASS}>{now}</span>
      </div>
      <div className="grid grid-cols-2 border-border border-t">
        {METRICS.map((metric) => (
          <div key={metric.key} className={TILE_CLASS}>
            <div className="flex items-center gap-1.5">
              <metric.icon className={`size-3.5 shrink-0 ${metric.tone}`} />
              <span className="text-muted-foreground text-xs">{metric.label}</span>
              <span className={`ml-auto ${VALUE_CLASS} ${metric.tone}`}>
                {metricValue(metric.key, data)}
              </span>
            </div>
            <Sparkline
              className={SPARK_CLASS}
              points={history?.[metric.key] ?? []}
              stroke={metric.stroke}
            />
          </div>
        ))}
      </div>
      <Collapsible.Root
        className="flex flex-col py-2"
        onOpenChange={setServicesOpen}
        open={servicesOpen}
      >
        <Collapsible.Trigger className={`group/services ${TRIGGER_CLASS}`}>
          <ChevronDown aria-hidden="true" className={CHEVRON_CLASS} />
          per service memory
        </Collapsible.Trigger>
        <Collapsible.Panel className="flex flex-col">
          {SERVICES.map((service) => {
            const bytes = data?.service_memory_bytes[service.key] ?? null
            const ratio = bytes === null ? 0 : Math.min(100, (bytes / MEMORY_CEILING_BYTES) * 100)
            return (
              <div key={service.key} className={ROW_CLASS}>
                <span aria-hidden="true" className={`${DOT_CLASS} ${service.tone}`} />
                <span className="w-24 shrink-0 truncate text-foreground text-xs">
                  {service.label}
                </span>
                <span aria-hidden="true" className={TRACK_CLASS}>
                  <span
                    className={`block h-full rounded-full transition-[width] duration-500 ${service.tone}`}
                    style={{ width: `${ratio}%` }}
                  />
                </span>
                <span className={`w-12 text-right ${MUTED_VALUE_CLASS}`}>
                  {bytes === null ? "--" : formatMegabytes(bytes)}
                </span>
              </div>
            )
          })}
        </Collapsible.Panel>
      </Collapsible.Root>
      <div className="grid grid-cols-2 border-border border-t">
        {THERMALS.map((thermal) => (
          <div key={thermal.key} className={THERMAL_CLASS}>
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground text-xs">{thermal.label}</span>
              <span className={`ml-auto ${VALUE_CLASS} ${thermal.tone}`}>
                {thermalValue(thermal.key, data)}
              </span>
            </div>
            <Sparkline
              className={THERMAL_SPARK_CLASS}
              points={history?.[thermal.key] ?? []}
              stroke={thermal.stroke}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
