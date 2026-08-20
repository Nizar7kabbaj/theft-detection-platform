import { type AlertPage, alertPageSchema } from "@/features/alerts/schemas/alert"
import { type HistoryFilters, historyListPath } from "@/features/history/api/history-keys"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export function fetchHistoryPage(
  filters: HistoryFilters,
  cursor: string | null,
): Promise<AlertPage> {
  return serverRead(historyListPath(filters, cursor), { schema: alertPageSchema })
}
