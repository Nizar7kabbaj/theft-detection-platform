import type { Metadata, Route } from "next"
import { cookies } from "next/headers"
import {
  ALERT_FILTERS_COOKIE_NAME,
  hasFilterParams,
  parseStoredFilters,
} from "@/features/alerts/api/alert-cookie"
import { alertFiltersToSearch, parseAlertFilters } from "@/features/alerts/api/alert-keys"
import { fetchAlertDetail, fetchAlertPage } from "@/features/alerts/api/alerts-server"
import { AcknowledgeButton } from "@/features/alerts/components/acknowledge-button"
import { AuditTrail } from "@/features/alerts/components/audit-trail"
import { DecisionControls } from "@/features/alerts/components/decision-controls"
import { DetailHeader } from "@/features/alerts/components/detail-header"
import { DetailNav } from "@/features/alerts/components/detail-nav"
import { EvidenceFrame } from "@/features/alerts/components/evidence-frame"
import { EvidencePanel } from "@/features/alerts/components/evidence-panel"
import { FactStrip } from "@/features/alerts/components/fact-strip"
import { VerdictPanel } from "@/features/alerts/components/verdict-panel"
import { fetchIdentity } from "@/features/auth/api/identity-server"

export const metadata: Metadata = { title: "alert" }
export const dynamic = "force-dynamic"

export default async function AlertDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const { id } = await params
  const [query, cookieStore] = await Promise.all([searchParams, cookies()])
  const stored = hasFilterParams(query)
    ? null
    : parseStoredFilters(cookieStore.get(ALERT_FILTERS_COOKIE_NAME)?.value)
  const filters = stored ?? parseAlertFilters(query)
  const search = alertFiltersToSearch(filters)
  const [alert, identity, queue] = await Promise.all([
    fetchAlertDetail(id),
    fetchIdentity(),
    fetchAlertPage(filters, null).catch(() => null),
  ])
  const items = queue?.items ?? []
  const position = items.findIndex((item) => item._id === alert._id)
  const previous = position > 0 ? items[position - 1] : undefined
  const next = position >= 0 ? items[position + 1] : undefined
  const canDecide = identity.permissions.includes("alert:acknowledge")
  return (
    <section className="flex flex-1 flex-col gap-5 pb-4">
      <DetailNav
        backHref={`/alerts${search}` as Route}
        nextHref={next === undefined ? null : (`/alerts/${next._id}${search}` as Route)}
        previousHref={previous === undefined ? null : (`/alerts/${previous._id}${search}` as Route)}
      />
      <DetailHeader action={<AcknowledgeButton alert={alert} />} alert={alert} />
      <FactStrip alert={alert} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <EvidenceFrame alert={alert} />
        <div className="flex flex-col gap-4">
          <EvidencePanel alertType={alert.alert_type} concealment={alert.concealment} />
          <VerdictPanel score={alert.classifier_score} state={alert.classifier_state} />
          <AuditTrail alert={alert} />
        </div>
      </div>
      {canDecide ? <DecisionControls alert={alert} /> : null}
    </section>
  )
}
