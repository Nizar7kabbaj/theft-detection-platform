"use client"
import type { Route } from "next"
import Link from "next/link"
import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { type Camera, cameraHealth, type HealthState } from "@/features/cameras/schemas/camera"

const HEALTH_LABEL: Record<HealthState, string> = {
  online: "online",
  degraded: "degraded",
  offline: "offline",
  unknown: "unknown",
}

const HEALTH_DOT: Record<HealthState, string> = {
  online: "bg-success",
  degraded: "bg-warning",
  offline: "bg-destructive",
  unknown: "bg-muted-foreground/50",
}

const HEALTH_TEXT: Record<HealthState, string> = {
  online: "text-success",
  degraded: "text-warning",
  offline: "text-destructive",
  unknown: "text-muted-foreground",
}

function frameAge(lastFrameAt: string | null | undefined, now: number): string {
  if (lastFrameAt === null || lastFrameAt === undefined) {
    return "no frames yet"
  }
  const seconds = Math.max(0, Math.round((now - new Date(lastFrameAt).getTime()) / 1000))
  if (seconds < 60) {
    return `last frame ${seconds}s ago`
  }
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `last frame ${minutes}m ago`
  }
  const hours = Math.floor(minutes / 60)
  return `last frame ${hours}h ago`
}

function useFrameAge(lastFrameAt: string | null | undefined): string {
  const [now, setNow] = useState<number | null>(null)

  useEffect(() => {
    setNow(Date.now())
    const id = window.setInterval(() => {
      setNow(Date.now())
    }, 1000)
    return () => {
      window.clearInterval(id)
    }
  }, [])

  if (lastFrameAt === null || lastFrameAt === undefined) {
    return "no frames yet"
  }
  if (now === null) {
    return "measuring frame age"
  }
  return frameAge(lastFrameAt, now)
}

export function CameraTile({ camera }: { camera: Camera }) {
  const health = cameraHealth(camera)
  const state = health.state
  const label = `${camera.name}, ${camera.location}, ${HEALTH_LABEL[state]}`
  const age = useFrameAge(health.last_frame_at)
  const href = `/cameras/${encodeURIComponent(camera.camera_id)}` as Route

  return (
    <Card
      aria-label={label}
      className="relative gap-3 transition-shadow focus-within:ring-2 focus-within:ring-ring hover:ring-foreground/20"
    >
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="min-w-0 text-pretty">
            <Link
              className="block truncate rounded-sm outline-none after:absolute after:inset-0 after:content-[''] focus-visible:underline"
              href={href}
            >
              {camera.name}
            </Link>
          </CardTitle>
          <span className={`flex shrink-0 items-center gap-1.5 text-xs ${HEALTH_TEXT[state]}`}>
            <span
              aria-hidden="true"
              className={`size-2 rounded-full ${HEALTH_DOT[state]} ${
                state === "online" ? "animate-pulse" : ""
              }`}
            />
            {HEALTH_LABEL[state]}
          </span>
        </div>
        <p className="truncate text-sm text-muted-foreground">{camera.location}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-xs text-muted-foreground">
        <p className="tabular-nums">{age}</p>
        <div className="flex items-center justify-between gap-2">
          <span className="truncate">
            {camera.stream_url === null || camera.stream_url === undefined
              ? "no stream url"
              : camera.stream_url}
          </span>
          <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-muted-foreground">
            {camera.status}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
