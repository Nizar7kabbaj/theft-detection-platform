import { type AlertFilters, alertListPath } from "@/features/alerts/api/alert-keys"
import {
  type Alert,
  type AlertPage,
  alertPageSchema,
  alertResponseSchema,
} from "@/features/alerts/schemas/alert"
import { apiRequest } from "@/lib/api/client"
import "client-only"

export function fetchAlertPageClient(
  filters: AlertFilters,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<AlertPage> {
  const path = alertListPath(filters, cursor)
  if (signal === undefined) {
    return apiRequest(path, { schema: alertPageSchema })
  }
  return apiRequest(path, { schema: alertPageSchema, signal })
}

export function acknowledgeAlert(id: string): Promise<Alert> {
  return apiRequest(`/api/v1/alerts/${encodeURIComponent(id)}/acknowledge`, {
    method: "PATCH",
    schema: alertResponseSchema,
  })
}
