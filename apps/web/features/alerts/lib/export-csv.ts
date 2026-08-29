import { alertTypeLabel, DECISION_LABEL, SEVERITY_LABEL } from "@/features/alerts/lib/format"
import type { Alert } from "@/features/alerts/schemas/alert"
import "client-only"

const HEADERS = [
  "alert time",
  "decided at",
  "reviewer",
  "camera",
  "severity",
  "type",
  "object",
  "state",
  "outcome",
  "id",
] as const

const RISKY = new Set(["=", "+", "-", "@", "\t", "\r"])

function safe(value: string): string {
  const first = value.slice(0, 1)
  const guarded = RISKY.has(first) ? `'${value}` : value
  return `"${guarded.replaceAll('"', '""')}"`
}

function stateOf(alert: Alert): string {
  if (alert.decision !== "DECISION_UNSPECIFIED") {
    return "closed"
  }
  return alert.acknowledged ? "seen" : "open"
}

export function buildCsv(rows: readonly Alert[], cameraNames: ReadonlyMap<string, string>): string {
  const lines = [HEADERS.map(safe).join(",")]
  for (const alert of rows) {
    lines.push(
      [
        alert.created_at,
        alert.decided_at ?? "",
        alert.decided_by ?? "",
        cameraNames.get(alert.camera_id) ?? alert.camera_id,
        SEVERITY_LABEL[alert.severity],
        alertTypeLabel(alert.alert_type),
        alert.object_name,
        stateOf(alert),
        DECISION_LABEL[alert.decision],
        alert._id,
      ]
        .map((value) => safe(String(value)))
        .join(","),
    )
  }
  return `${lines.join("\r\n")}\r\n`
}

export function downloadCsv(content: string, name: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = name
  anchor.rel = "noopener"
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
