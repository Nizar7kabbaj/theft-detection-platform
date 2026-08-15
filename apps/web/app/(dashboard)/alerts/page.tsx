import { ShieldAlert } from "lucide-react"
import type { Metadata } from "next"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/ui/empty-state"

export const metadata: Metadata = { title: "alerts" }
export const dynamic = "force-dynamic"

export default function AlertsPage() {
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="alerts" description="detections escalated for human review" />
      <EmptyState
        icon={ShieldAlert}
        title="no alerts yet"
        description="alerts appear here once the detection pipeline escalates an event"
      />
    </section>
  )
}
