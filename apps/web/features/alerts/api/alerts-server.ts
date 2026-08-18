import { type AlertFilters, alertListPath } from "@/features/alerts/api/alert-keys"
import {
  type AlertDetail,
  type AlertPage,
  alertDetailSchema,
  alertPageSchema,
} from "@/features/alerts/schemas/alert"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export function fetchAlertPage(filters: AlertFilters, cursor: string | null): Promise<AlertPage> {
  return serverRead(alertListPath(filters, cursor), { schema: alertPageSchema })
}

export function fetchAlertDetail(id: string): Promise<AlertDetail> {
  return serverRead(`/api/v1/alerts/${encodeURIComponent(id)}`, { schema: alertDetailSchema })
}
