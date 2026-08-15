import { dehydrate, HydrationBoundary } from "@tanstack/react-query"
import type { Metadata } from "next"
import { Suspense } from "react"
import { PageHeader } from "@/components/layout/page-header"
import { alertKeys, parseAlertFilters } from "@/features/alerts/api/alert-keys"
import { fetchAlertPage } from "@/features/alerts/api/alerts-server"
import { AlertFilterControls } from "@/features/alerts/components/alert-filters"
import { AlertStream } from "@/features/alerts/components/alert-stream"
import { AlertTable } from "@/features/alerts/components/alert-table"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import { createServerQueryClient } from "@/lib/api/query-server"

export const metadata: Metadata = { title: "alerts" }
export const dynamic = "force-dynamic"

export default async function AlertsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const [params, identity] = await Promise.all([searchParams, fetchIdentity()])
  const filters = parseAlertFilters(params)
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Suspense fallback={null}>
          <AlertFilterControls filters={filters} />
        </Suspense>
        <AlertStream />
      </div>
      <HydrationBoundary state={dehydrate(queryClient)}>
        <AlertTable canAcknowledge={canAcknowledge} filters={filters} />
      </HydrationBoundary>
    </section>
  )
}
