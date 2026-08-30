import { Camera, ShieldCheck } from "lucide-react"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import { cameraHealth } from "@/features/cameras/schemas/camera"
import { Cell } from "@/features/dashboard/components/command-strip"

type FleetTone = "success" | "warning" | "destructive" | "muted"

const HEALTH_ORDER: FleetTone[] = ["success", "warning", "destructive"]

const SYSTEM_LABEL: Record<FleetTone, string> = {
  success: "healthy",
  warning: "watch",
  destructive: "degraded",
  muted: "unknown",
}

const SYSTEM_NOTE: Record<FleetTone, string> = {
  success: "all feeds arriving",
  warning: "one or more feeds delayed",
  destructive: "one or more feeds down",
  muted: "fleet state unknown",
}

function pad(count: number): string {
  return String(count).padStart(2, "0")
}

export async function FleetCells() {
  let cameras: Awaited<ReturnType<typeof fetchCameras>>
  try {
    cameras = await fetchCameras()
  } catch {
    return (
      <>
        <Cell
          icon={<Camera aria-hidden="true" className="size-4" />}
          label="cameras online"
          value="no reading"
          note="fleet unavailable"
          tone="muted"
        />
        <Cell
          icon={<ShieldCheck aria-hidden="true" className="size-4" />}
          label="system health"
          value="no reading"
          note="fleet unavailable"
          tone="muted"
        />
      </>
    )
  }

  const total = cameras.length
  const states = cameras.map((camera) => cameraHealth(camera).state)
  const online = states.filter((state) => state === "online").length
  const degraded = states.filter((state) => state === "degraded").length
  const offline = states.filter((state) => state === "offline").length

  let tone: FleetTone = "muted"
  if (total > 0) {
    if (offline > 0) {
      tone = "destructive"
    } else if (degraded > 0) {
      tone = "warning"
    } else if (online === total) {
      tone = "success"
    }
  }

  let fleetNote = "fleet empty"
  if (total > 0) {
    if (offline > 0) {
      fleetNote = `${offline} feed${offline === 1 ? "" : "s"} offline`
    } else if (degraded > 0) {
      fleetNote = `${degraded} feed${degraded === 1 ? "" : "s"} delayed`
    } else {
      fleetNote = "all feeds arriving"
    }
  }

  const fleetTone = HEALTH_ORDER.includes(tone) ? tone : "muted"

  return (
    <>
      <Cell
        icon={<Camera aria-hidden="true" className="size-4" />}
        label="cameras online"
        value={`${pad(online)} / ${pad(total)}`}
        note={fleetNote}
        tone={fleetTone}
      />
      <Cell
        icon={<ShieldCheck aria-hidden="true" className="size-4" />}
        label="system health"
        value={SYSTEM_LABEL[tone]}
        note={SYSTEM_NOTE[tone]}
        tone={tone}
      />
    </>
  )
}
