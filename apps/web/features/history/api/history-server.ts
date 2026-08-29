import { type AlertPage, alertPageSchema } from "@/features/alerts/schemas/alert"
import {
  type HistoryFilters,
  historyListPath,
  type RangeBounds,
} from "@/features/history/api/history-keys"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export function fetchHistoryPage(
  filters: HistoryFilters,
  cursor: string | null,
  bounds: RangeBounds,
): Promise<AlertPage> {
  return serverRead(historyListPath(filters, cursor, bounds), { schema: alertPageSchema })
}
