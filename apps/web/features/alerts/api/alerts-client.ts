import { type AlertFilters, alertCountPath, alertListPath } from "@/features/alerts/api/alert-keys"
import {
  type Alert,
  type AlertDetail,
  type AlertPage,
  alertCountSchema,
  alertDetailSchema,
  alertPageSchema,
  alertResponseSchema,
  type Decision,
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

export async function fetchAlertCountClient(
  filters: AlertFilters,
  signal?: AbortSignal,
): Promise<number> {
  const path = alertCountPath(filters)
  const result =
    signal === undefined
      ? await apiRequest(path, { schema: alertCountSchema })
      : await apiRequest(path, { schema: alertCountSchema, signal })
  return result.total
}

export function acknowledgeAlert(id: string): Promise<Alert> {
  return apiRequest(`/api/v1/alerts/${encodeURIComponent(id)}/acknowledge`, {
    method: "PATCH",
    schema: alertResponseSchema,
  })
}

export function decideAlert(id: string, decision: Decision): Promise<AlertDetail> {
  return apiRequest(`/api/v1/alerts/${encodeURIComponent(id)}/decision`, {
    method: "PATCH",
    body: { decision },
    schema: alertDetailSchema,
  })
}

export function fetchAlertDetailClient(id: string, signal?: AbortSignal): Promise<AlertDetail> {
  const path = `/api/v1/alerts/${encodeURIComponent(id)}`
  if (signal === undefined) {
    return apiRequest(path, { schema: alertDetailSchema })
  }
  return apiRequest(path, { schema: alertDetailSchema, signal })
}
