import type { Metadata } from "next"
import { cookies } from "next/headers"
import { Suspense } from "react"
import { PageHeader } from "@/components/layout/page-header"
import { Card } from "@/components/ui/card"
import { AbsentPanel } from "@/features/alerts/components/absent-panel"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import { fetchArchiveSummary } from "@/features/history/api/archive-summary"
import { fetchAlertCameras } from "@/features/history/api/camera-facet"
import {
  HISTORY_FILTERS_COOKIE_NAME,
  hasFilterParams,
  parseStoredFilters,
} from "@/features/history/api/history-cookie"
import {
  parseHistoryCursor,
  parseHistoryFilters,
  rangeBounds,
} from "@/features/history/api/history-keys"
import { fetchHistoryPage } from "@/features/history/api/history-server"
import { ArchiveCards } from "@/features/history/components/archive-cards"
import { EventList } from "@/features/history/components/event-list"
import { HistoryFilterControls } from "@/features/history/components/history-filters"
import { HistoryPager } from "@/features/history/components/history-pager"
import { RestoredNotice } from "@/features/history/components/restored-notice"
import { SeveritySpread } from "@/features/history/components/severity-spread"

export const metadata: Metadata = { title: "history" }
export const dynamic = "force-dynamic"

const DESCRIPTION =
  "past alerts, operator decisions, and archive movement across the selected range"

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

  const fromUrl = hasFilterParams(params)
  const stored = fromUrl
    ? null
    : parseStoredFilters((await cookies()).get(HISTORY_FILTERS_COOKIE_NAME)?.value)
  const filters = stored ?? parseHistoryFilters(params)
  const restored = stored !== null
  const cursor = parseHistoryCursor(params)
  const bounds = rangeBounds(filters.range, new Date())

  const [page, summary, names, facet] = await Promise.all([
    fetchHistoryPage(filters, cursor, bounds),
    fetchArchiveSummary(filters, bounds),
    cameraNames(identity.permissions.includes("camera:read")),
    fetchAlertCameras(),
  ])

  const nextCursor = page.next_cursor ?? null

  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="history" description={DESCRIPTION} />

      {restored ? <RestoredNotice /> : null}

      <Card className="flex flex-col gap-4 p-5">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          archive controls
        </p>
        <Suspense fallback={null}>
          <HistoryFilterControls cameras={cameraOptions(facet, names)} filters={filters} />
        </Suspense>
      </Card>

      <ArchiveCards summary={summary} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <EventList cameraNames={names} rows={page.items}>
          <HistoryPager
            count={page.items.length}
            cursor={cursor}
            filters={filters}
            nextCursor={nextCursor}
          />
        </EventList>

        <div className="flex flex-col gap-4">
          <SeveritySpread tally={summary.severity} />
          <AbsentPanel
            title="delivery outcome"
            reason="whether each alert reached telegram is held by the notification service and there is no read path to it yet"
          />
        </div>
      </div>
    </section>
  )
}
