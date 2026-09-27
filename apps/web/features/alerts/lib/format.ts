import type { AlertDetail, Decision } from "@/features/alerts/schemas/alert"
import { storeFormatter } from "@/lib/time/zone"

export const SEVERITY_LABEL: Record<AlertDetail["severity"], string> = {
  SEVERITY_UNSPECIFIED: "unspecified",
  SEVERITY_INFO: "info",
  SEVERITY_NOTICE: "notice",
  SEVERITY_WARNING: "warning",
  SEVERITY_CRITICAL: "critical",
}

export const SEVERITY_CLASS: Record<AlertDetail["severity"], string> = {
  SEVERITY_UNSPECIFIED: "text-muted-foreground",
  SEVERITY_INFO: "text-muted-foreground",
  SEVERITY_NOTICE: "text-chart-2",
  SEVERITY_WARNING: "text-warning",
  SEVERITY_CRITICAL: "text-destructive",
}

export const DECISION_LABEL: Record<Decision, string> = {
  DECISION_UNSPECIFIED: "no decision recorded",
  DECISION_CONFIRMED: "confirmed",
  DECISION_DISMISSED: "dismissed",
  DECISION_UNSURE: "unsure",
}

export function alertTypeLabel(value: string | null | undefined): string {
  if (value === null || value === undefined) {
    return "unspecified"
  }
  return value.replace("ALERT_TYPE_", "").toLowerCase().replace(/_/g, " ")
}

export function classifierStateLabel(value: string | null | undefined): string {
  if (value === null || value === undefined) {
    return "no state recorded"
  }
  return value.replace("INFERENCE_STATE_", "").toLowerCase().replace(/_/g, " ")
}

export function formatTimestamp(value: string): string {
  return storeFormatter("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value))
}

export function clockTime(value: string): string {
  return storeFormatter("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value))
}

export function relativeAge(value: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - new Date(value).getTime()) / 1000))
  if (seconds < 60) {
    return `${seconds}s ago`
  }
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.round(minutes / 60)
  if (hours < 48) {
    return `${hours}h ago`
  }
  return `${Math.round(hours / 24)}d ago`
}

export function objectLabel(alert: AlertDetail): string {
  return alert.object?.class_name ?? alert.concealment?.object_class ?? "unidentified"
}
