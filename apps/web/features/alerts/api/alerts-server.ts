import { type AlertFilters, alertListPath } from "@/features/alerts/api/alert-keys"
import { type AlertPage, alertPageSchema } from "@/features/alerts/schemas/alert"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export function fetchAlertPage(filters: AlertFilters, cursor: string | null): Promise<AlertPage> {
  return serverRead(alertListPath(filters, cursor), { schema: alertPageSchema })
}
