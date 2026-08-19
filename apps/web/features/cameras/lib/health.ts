"use client"
import { useEffect, useState } from "react"
import type { HealthState } from "@/features/cameras/schemas/camera"

export const DEGRADED_AFTER_SECONDS = 5
export const OFFLINE_AFTER_SECONDS = 15

export const HEALTH_LABEL: Record<HealthState, string> = {
  online: "online",
  degraded: "degraded",
  offline: "offline",
  unknown: "unknown",
}

export const HEALTH_DETAIL: Record<HealthState, string> = {
  online: "frames arriving",
  degraded: "frames delayed",
  offline: "no recent frames",
  unknown: "state unknown",
}

export const HEALTH_TEXT: Record<HealthState, string> = {
  online: "text-success",
  degraded: "text-warning",
  offline: "text-destructive",
  unknown: "text-muted-foreground",
}

export const HEALTH_DOT: Record<HealthState, string> = {
  online: "bg-success",
  degraded: "bg-warning",
  offline: "bg-destructive",
  unknown: "bg-muted-foreground/50",
}

export const HEALTH_STROKE: Record<HealthState, string> = {
  online: "stroke-success",
  degraded: "stroke-warning",
  offline: "stroke-destructive",
  unknown: "stroke-muted-foreground/50",
}

export function elapsedLabel(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds))
  if (whole < 60) {
    return `${whole}s`
  }
  const minutes = Math.floor(whole / 60)
  if (minutes < 60) {
    return `${minutes}m`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h`
  }
  return `${Math.floor(hours / 24)}d`
}

export function useElapsedSeconds(since: string | null | undefined): number | null {
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

  if (since === null || since === undefined || now === null) {
    return null
  }
  const parsed = new Date(since).getTime()
  if (Number.isNaN(parsed)) {
    return null
  }
  return Math.max(0, (now - parsed) / 1000)
}

export function freshnessFraction(seconds: number | null): number {
  if (seconds === null) {
    return 0
  }
  return Math.min(1, Math.max(0, 1 - seconds / OFFLINE_AFTER_SECONDS))
}
