import type { Metadata } from "next"
import { Suspense } from "react"
import { PageHeader } from "@/components/layout/page-header"
import { AbsentPanel } from "@/features/alerts/components/absent-panel"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import { fetchAlertCameras } from "@/features/history/api/camera-facet"
import { parseHistoryCursor, parseHistoryFilters } from "@/features/history/api/history-keys"
import { fetchHistoryPage } from "@/features/history/api/history-server"
import { HistoryFilterControls } from "@/features/history/components/history-filters"
import { HistoryPager } from "@/features/history/components/history-pager"
import { HistorySummary } from "@/features/history/components/history-summary"
import { HistoryTable } from "@/features/history/components/history-table"

export const metadata: Metadata = { title: "history" }
export const dynamic = "force-dynamic"

const DESCRIPTION = "past alerts and the decisions taken on them"

async function cameraNames(canRead: boolean): Promise<ReadonlyMap<string, string>> {
  if (!canRead) {
    return new Map()
  }
  try {
    const cameras = await fetchCameras()
    return new Map(cameras.map((camera) => [camera.camera_id, camera.name]))
  } catch {
    return new Map()
  }
}

function cameraOptions(
  facet: readonly string[],
  names: ReadonlyMap<string, string>,
): readonly (readonly [string, string])[] {
  return facet
    .map((id) => [id, names.get(id) ?? id] as const)
    .sort((left, right) => left[1].localeCompare(right[1]))
}

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const [params, identity] = await Promise.all([searchParams, fetchIdentity()])
  if (!identity.permissions.includes("alert:read")) {
    return (
      <section className="flex flex-1 flex-col gap-5">
        <PageHeader title="history" description={DESCRIPTION} />
        <AbsentPanel
          title="history is not available to this account"
          reason="reading review history needs the alert:read permission"
        />
      </section>
    )
  }
  const filters = parseHistoryFilters(params)
  const cursor = parseHistoryCursor(params)
  const [page, names, facet] = await Promise.all([
    fetchHistoryPage(filters, cursor),
    cameraNames(identity.permissions.includes("camera:read")),
    fetchAlertCameras(),
  ])
  const nextCursor = page.next_cursor ?? null
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="history" description={DESCRIPTION} />
      <Suspense fallback={null}>
        <HistoryFilterControls cameras={cameraOptions(facet, names)} filters={filters} />
      </Suspense>
      <HistorySummary rows={page.items} />
      <HistoryTable cameraNames={names} rows={page.items} sort={filters.sort} />
      <HistoryPager
        count={page.items.length}
        cursor={cursor}
        filters={filters}
        nextCursor={nextCursor}
      />
      <AbsentPanel
        title="delivery outcome"
        reason="whether each alert reached telegram is held by the notification service and there is no read path to it yet"
      />
    </section>
  )
}
