import { dehydrate, HydrationBoundary } from "@tanstack/react-query"
import type { Metadata } from "next"
import { cookies } from "next/headers"
import { Suspense } from "react"
import { PageHeader } from "@/components/layout/page-header"
import {
  ALERT_FILTERS_COOKIE_NAME,
  hasFilterParams,
  parseStoredFilters,
} from "@/features/alerts/api/alert-cookie"
import { alertKeys, parseAlertFilters } from "@/features/alerts/api/alert-keys"
import { fetchAlertPage } from "@/features/alerts/api/alerts-server"
import { fetchCameraOptions } from "@/features/alerts/api/camera-options"
import { AlertsWorkspace } from "@/features/alerts/components/alerts-workspace"
import { fetchStats } from "@/features/analytics/api/stats-server"
import type { Stats } from "@/features/analytics/schemas/stats"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import { createServerQueryClient } from "@/lib/api/query-server"

export const metadata: Metadata = { title: "alerts" }
export const dynamic = "force-dynamic"

export default async function AlertsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const [params, cookieStore, identity, cameras, stats] = await Promise.all([
    searchParams,
    cookies(),
    fetchIdentity(),
    fetchCameraOptions(),
    fetchStats().catch((): Stats | null => null),
  ])

  const fromUrl = hasFilterParams(params)
  const stored = fromUrl
    ? null
    : parseStoredFilters(cookieStore.get(ALERT_FILTERS_COOKIE_NAME)?.value)
  const filters = stored ?? parseAlertFilters(params)
  const restored = stored !== null

  const canAcknowledge = identity.permissions.includes("alert:acknowledge")
  const queryClient = createServerQueryClient()
  await queryClient.prefetchInfiniteQuery({
    queryKey: alertKeys.list(filters),
    queryFn: () => fetchAlertPage(filters, null),
    initialPageParam: null,
  })
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="alerts" description="detections escalated for human review" />
      <HydrationBoundary state={dehydrate(queryClient)}>
        <Suspense fallback={null}>
          <AlertsWorkspace
            cameras={cameras}
            canAcknowledge={canAcknowledge}
            filters={filters}
            restored={restored}
            stats={stats}
          />
        </Suspense>
      </HydrationBoundary>
    </section>
  )
}
