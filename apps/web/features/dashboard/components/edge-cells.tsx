import { Activity, Thermometer, Wifi } from "lucide-react"
import { fetchEdgeStats } from "@/features/analytics/api/edge-stats-server"
import { Cell } from "@/features/dashboard/components/command-strip"

type Tone = "default" | "success" | "warning" | "destructive" | "muted"

const GPU_WARM_C = 75
const GPU_HOT_C = 85
const LATENCY_SLOW_MS = 150
const LATENCY_STALLED_MS = 400

function fpsNote(reporting: number, total: number): string {
  if (total === 0) {
    return "no cameras registered"
  }
  return `${reporting} of ${total} reporting`
}

function temperatureTone(celsius: number): Tone {
  if (celsius >= GPU_HOT_C) {
    return "destructive"
  }
  if (celsius >= GPU_WARM_C) {
    return "warning"
  }
  return "success"
}

function latencyTone(ms: number): Tone {
  if (ms >= LATENCY_STALLED_MS) {
    return "destructive"
  }
  if (ms >= LATENCY_SLOW_MS) {
    return "warning"
  }
  return "success"
}

function EdgeFallback({ note }: { note: string }) {
  return (
    <>
      <Cell
        icon={<Activity aria-hidden="true" className="size-4" />}
        label="average fps"
        value="no reading"
        note={note}
        tone="muted"
      />
      <Cell
        icon={<Wifi aria-hidden="true" className="size-4" />}
        label="edge latency"
        value="no reading"
        note={note}
        tone="muted"
      />
      <Cell
        icon={<Thermometer aria-hidden="true" className="size-4" />}
        label="edge temperature"
        value="no reading"
        note={note}
        tone="muted"
      />
    </>
  )
}

export async function EdgeCells() {
  let stats: Awaited<ReturnType<typeof fetchEdgeStats>>
  try {
    stats = await fetchEdgeStats()
  } catch {
    return <EdgeFallback note="edge metrics unavailable" />
  }
  return (
    <>
      <Cell
        icon={<Activity aria-hidden="true" className="size-4" />}
        label="average fps"
        value={stats.average_fps === null ? "no reading" : stats.average_fps.toFixed(1)}
        note={
          stats.average_fps === null
            ? "no camera publishing"
            : fpsNote(stats.reporting_cameras, stats.total_cameras)
        }
        tone={stats.average_fps === null ? "muted" : "default"}
      />
      <Cell
        icon={<Wifi aria-hidden="true" className="size-4" />}
        label="edge latency"
        value={stats.latency_ms === null ? "no reading" : `${stats.latency_ms.toFixed(0)} ms`}
        note={stats.latency_ms === null ? "no inference round trip" : "analyze round trip"}
        tone={stats.latency_ms === null ? "muted" : latencyTone(stats.latency_ms)}
      />
      <Cell
        icon={<Thermometer aria-hidden="true" className="size-4" />}
        label="edge temperature"
        value={
          stats.gpu_temperature_c === null ? "no reading" : `${stats.gpu_temperature_c} \u00b0C`
        }
        note={
          stats.gpu_temperature_c === null ? "gpu sensor unavailable" : (stats.gpu_name ?? "gpu")
        }
        tone={stats.gpu_temperature_c === null ? "muted" : temperatureTone(stats.gpu_temperature_c)}
      />
    </>
  )
}
