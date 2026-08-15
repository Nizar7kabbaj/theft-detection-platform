import { TrendingUp } from "lucide-react"
import type { Metadata } from "next"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/ui/empty-state"

export const metadata: Metadata = { title: "analytics" }

export default function AnalyticsPage() {
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="analytics" description="detection rates and review throughput over time" />
      <EmptyState
        icon={TrendingUp}
        title="not enough data"
        description="charts render once the pipeline has recorded a full reporting period"
      />
    </section>
  )
}
